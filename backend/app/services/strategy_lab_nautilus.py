from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.datetime import dt_to_unix_nanos
from nautilus_trader.indicators import (
    ExponentialMovingAverage,
    RelativeStrengthIndex,
    SimpleMovingAverage,
)
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AccountType, OmsType, OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Money
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.trading.strategy import Strategy

from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe


def _nanos_to_iso(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1_000_000_000, tz=UTC).isoformat()


def _money_like_to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if hasattr(value, "as_double"):
        return float(value.as_double())
    if isinstance(value, str):
        amount = value.split(" ", 1)[0].replace(",", "")
        return float(amount)
    return float(value)


def _timeframe_to_bar_spec(timeframe: Timeframe) -> str:
    mapping = {
        Timeframe.M1: "1-MINUTE",
        Timeframe.M5: "5-MINUTE",
        Timeframe.M15: "15-MINUTE",
        Timeframe.M30: "30-MINUTE",
        Timeframe.H1: "1-HOUR",
        Timeframe.H2: "2-HOUR",
        Timeframe.H4: "4-HOUR",
        Timeframe.H12: "12-HOUR",
        Timeframe.D1: "1-DAY",
        Timeframe.W1: "1-WEEK",
        Timeframe.MN: "1-MONTH",
    }
    return mapping[timeframe]


def build_nautilus_bars(
    *,
    symbol: str,
    timeframe: Timeframe,
    bars: list[OHLCVBar],
) -> tuple[Any, BarType, list[Bar], dict[int, int]]:
    venue = "SIM"
    instrument = TestInstrumentProvider.equity(symbol=symbol, venue=venue)
    bar_type = BarType.from_str(
        f"{instrument.id}-{_timeframe_to_bar_spec(timeframe)}-LAST-EXTERNAL"
    )
    converted: list[Bar] = []
    ts_index_map: dict[int, int] = {}
    for index, bar in enumerate(bars):
        ts_nanos = dt_to_unix_nanos(bar.ts.astimezone(UTC))
        ts_index_map[ts_nanos] = index
        converted.append(
            Bar.from_dict(
                {
                    "bar_type": str(bar_type),
                    "open": f"{float(bar.open):.{instrument.price_precision}f}",
                    "high": f"{float(bar.high):.{instrument.price_precision}f}",
                    "low": f"{float(bar.low):.{instrument.price_precision}f}",
                    "close": f"{float(bar.close):.{instrument.price_precision}f}",
                    "volume": f"{float(bar.volume or 0):.{instrument.size_precision}f}",
                    "ts_event": ts_nanos,
                    "ts_init": ts_nanos,
                }
            )
        )
    return instrument, bar_type, converted, ts_index_map


@dataclass
class NautilusTrade:
    instrument_id: int
    instrument_symbol: str
    side: str
    entry_at: str
    exit_at: str
    entry_price: float
    exit_price: float
    stop_price: float
    target_price: float
    quantity: float
    pnl: float
    pnl_pct: float
    r_multiple: float
    bars_held: int
    exit_reason: str


@dataclass
class SingleInstrumentBacktestResult:
    trades: list[NautilusTrade]
    equity_curve: list[dict[str, float | str]]
    warnings: list[str] = field(default_factory=list)
    total_events: int = 0
    total_orders: int = 0
    total_positions: int = 0


class StrategyLabNautilusConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    direction: str = "long"
    entry_logic: str = "all"
    conditions: tuple[dict[str, Any], ...] = ()
    stop_loss_pct: float = 2.0
    take_profit_rr: float = 2.0
    max_bars_in_trade: int = 20
    risk_per_trade_pct: float = 1.0
    capital_base: float = 100_000.0


class StrategyLabNautilusStrategy(Strategy):
    def __init__(self, config: StrategyLabNautilusConfig) -> None:
        super().__init__(config)
        self.instrument = None
        self._indicator_cache: dict[tuple[str, int], Any] = {}
        self._previous_values: list[tuple[float | None, float | None]] | None = None
        self.active_position_id: str | None = None
        self.position_plans: dict[str, dict[str, float | int | str]] = {}
        self.exit_reasons: dict[str, str] = {}
        self.equity_curve: list[tuple[int, float]] = []
        self.warnings: list[str] = []

        for condition in self.config.conditions:
            self._ensure_indicator(condition, "left")
            self._ensure_indicator(condition, "right")

    def _ensure_indicator(self, condition: dict[str, Any], side: str) -> None:
        if condition.get(f"{side}_source") != "indicator":
            return
        indicator = str(condition.get(f"{side}_indicator") or "").lower()
        period = int(condition.get(f"{side}_period") or 0)
        key = (indicator, period)
        if key in self._indicator_cache or period <= 0:
            return
        if indicator == "sma":
            self._indicator_cache[key] = SimpleMovingAverage(period)
        elif indicator == "ema":
            self._indicator_cache[key] = ExponentialMovingAverage(period)
        elif indicator == "rsi":
            self._indicator_cache[key] = RelativeStrengthIndex(period)
        else:
            self.warnings.append(f"Unsupported indicator '{indicator}' ignored.")

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.stop()
            return
        for indicator in self._indicator_cache.values():
            self.register_indicator_for_bars(self.config.bar_type, indicator)
        self.subscribe_bars(self.config.bar_type)

    def on_stop(self) -> None:
        if self.active_position_id is not None:
            self.exit_reasons[self.active_position_id] = "session_close"
            self.close_all_positions(self.config.instrument_id)
        self.cancel_all_orders(self.config.instrument_id)
        self.unsubscribe_bars(self.config.bar_type)

    def on_bar(self, bar: Bar) -> None:
        self._sync_active_position()
        condition_values = [
            self._condition_values(condition, bar) for condition in self.config.conditions
        ]

        if self.active_position_id is not None:
            if self._maybe_exit(bar):
                self._record_equity(bar.ts_event)
                self._previous_values = condition_values
                return
        elif not self._has_pending_orders() and self._should_enter(condition_values):
            self._submit_entry(bar)

        self._sync_active_position()
        self._record_equity(bar.ts_event)
        self._previous_values = condition_values

    def _has_pending_orders(self) -> bool:
        return bool(self.cache.orders_open_count() or self.cache.orders_inflight_count())

    def _sync_active_position(self) -> None:
        open_positions = self.cache.positions_open()
        if not open_positions:
            self.active_position_id = None
            return
        position = open_positions[0]
        position_id = str(position.id)
        self.active_position_id = position_id
        if position_id in self.position_plans:
            self.position_plans[position_id]["bars_elapsed"] = (
                int(self.position_plans[position_id].get("bars_elapsed", 0)) + 1
            )
            return

        entry_price = float(position.avg_px_open)
        if self.config.direction == "long":
            stop_price = entry_price * (1.0 - self.config.stop_loss_pct / 100.0)
            target_price = entry_price + (entry_price - stop_price) * self.config.take_profit_rr
        else:
            stop_price = entry_price * (1.0 + self.config.stop_loss_pct / 100.0)
            target_price = entry_price - (stop_price - entry_price) * self.config.take_profit_rr
        self.position_plans[position_id] = {
            "entry_price": entry_price,
            "stop_price": stop_price,
            "target_price": target_price,
            "bars_elapsed": 0,
        }

    def _record_equity(self, ts_event: int) -> None:
        total_pnl = sum(
            _money_like_to_float(money) for money in self.portfolio.total_pnls().values()
        )
        equity = round(self.config.capital_base + total_pnl, 4)
        if self.equity_curve and self.equity_curve[-1][0] == ts_event:
            self.equity_curve[-1] = (ts_event, equity)
        else:
            self.equity_curve.append((ts_event, equity))

    def _submit_entry(self, bar: Bar) -> None:
        reference_price = bar.close.as_double()
        risk_distance = reference_price * (self.config.stop_loss_pct / 100.0)
        if risk_distance <= 0:
            return
        risk_budget = self.config.capital_base * (self.config.risk_per_trade_pct / 100.0)
        raw_quantity = max(risk_budget / risk_distance, 1.0)
        quantity = self.instrument.make_qty(Decimal(str(raw_quantity)))
        side = OrderSide.BUY if self.config.direction == "long" else OrderSide.SELL
        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=side,
            quantity=quantity,
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order(order)

    def _maybe_exit(self, bar: Bar) -> bool:
        if self.active_position_id is None:
            return False
        plan = self.position_plans.get(self.active_position_id)
        if not plan:
            return False

        high = bar.high.as_double()
        low = bar.low.as_double()
        stop_price = float(plan["stop_price"])
        target_price = float(plan["target_price"])
        bars_elapsed = int(plan.get("bars_elapsed", 0))

        reason: str | None = None
        if self.config.direction == "long":
            if low <= stop_price:
                reason = "stop_loss"
            elif high >= target_price:
                reason = "take_profit"
        else:
            if high >= stop_price:
                reason = "stop_loss"
            elif low <= target_price:
                reason = "take_profit"

        if reason is None and bars_elapsed >= self.config.max_bars_in_trade:
            reason = "time_exit"

        if reason is None:
            return False

        self.exit_reasons[self.active_position_id] = reason
        self.close_all_positions(self.config.instrument_id)
        return True

    def _condition_values(
        self, condition: dict[str, Any], bar: Bar
    ) -> tuple[float | None, float | None]:
        return self._side_value(condition, "left", bar), self._side_value(condition, "right", bar)

    def _side_value(self, condition: dict[str, Any], side: str, bar: Bar) -> float | None:
        source = condition.get(f"{side}_source")
        if source == "price":
            return bar.close.as_double()
        if source == "value":
            raw = condition.get(f"{side}_value")
            return float(raw) if raw is not None else None
        if source == "indicator":
            indicator = str(condition.get(f"{side}_indicator") or "").lower()
            period = int(condition.get(f"{side}_period") or 0)
            instance = self._indicator_cache.get((indicator, period))
            if instance is None:
                return None
            value = getattr(instance, "value", None)
            if value is None:
                return None
            return float(value)
        return None

    def _should_enter(self, current_values: list[tuple[float | None, float | None]]) -> bool:
        if not self.config.conditions:
            return False
        if self._indicator_cache and not self.indicators_initialized():
            return False

        matches: list[bool] = []
        for index, condition in enumerate(self.config.conditions):
            left, right = current_values[index]
            prev_left = prev_right = None
            if self._previous_values is not None and index < len(self._previous_values):
                prev_left, prev_right = self._previous_values[index]
            matches.append(
                self._evaluate_condition(
                    condition=condition,
                    left=left,
                    right=right,
                    prev_left=prev_left,
                    prev_right=prev_right,
                )
            )
        if self.config.entry_logic == "any":
            return any(matches)
        return all(matches)

    def _evaluate_condition(
        self,
        *,
        condition: dict[str, Any],
        left: float | None,
        right: float | None,
        prev_left: float | None,
        prev_right: float | None,
    ) -> bool:
        if left is None or right is None:
            return False
        operator = str(condition.get("operator") or "gt").lower()
        if operator == "gt":
            return left > right
        if operator == "gte":
            return left >= right
        if operator == "lt":
            return left < right
        if operator == "lte":
            return left <= right
        if operator == "crosses_above":
            return (
                prev_left is not None
                and prev_right is not None
                and prev_left <= prev_right
                and left > right
            )
        if operator == "crosses_below":
            return (
                prev_left is not None
                and prev_right is not None
                and prev_left >= prev_right
                and left < right
            )
        return False


def run_single_instrument_nautilus_backtest(
    *,
    instrument: Instrument,
    bars: list[OHLCVBar],
    timeframe: Timeframe,
    direction: str,
    entry_logic: str,
    conditions: list[dict[str, Any]],
    stop_loss_pct: float,
    take_profit_rr: float,
    max_bars_in_trade: int,
    capital_base: float,
    risk_per_trade_pct: float,
    slippage_bps: float,
    commission_per_trade: float,
) -> SingleInstrumentBacktestResult:
    nautilus_instrument, bar_type, nautilus_bars, ts_index_map = build_nautilus_bars(
        symbol=instrument.symbol,
        timeframe=timeframe,
        bars=bars,
    )

    strategy = StrategyLabNautilusStrategy(
        StrategyLabNautilusConfig(
            instrument_id=nautilus_instrument.id,
            bar_type=bar_type,
            direction=direction,
            entry_logic=entry_logic,
            conditions=tuple(conditions),
            stop_loss_pct=stop_loss_pct,
            take_profit_rr=take_profit_rr,
            max_bars_in_trade=max_bars_in_trade,
            risk_per_trade_pct=risk_per_trade_pct,
            capital_base=capital_base,
        )
    )

    engine = BacktestEngine(
        BacktestEngineConfig(
            logging=LoggingConfig(bypass_logging=True),
            run_analysis=True,
        )
    )
    try:
        quote_currency = instrument.currency or "USD"
        venue = nautilus_instrument.id.venue
        venue_balance = Money.from_str(f"{capital_base:.2f} {quote_currency}")
        engine.add_venue(
            venue,
            OmsType.NETTING,
            AccountType.MARGIN,
            [venue_balance],
            base_currency=Money.from_str(f"1 {quote_currency}").currency,
            default_leverage=Decimal("1"),
        )
        engine.add_instrument(nautilus_instrument)
        engine.add_data(nautilus_bars)
        engine.add_strategy(strategy)
        engine.run()
        result = engine.get_result()

        trades: list[NautilusTrade] = []
        for position in engine.cache.positions_closed():
            payload = position.to_dict()
            position_id = str(payload["position_id"])
            entry_price = float(payload["avg_px_open"])
            exit_price = float(payload["avg_px_close"])
            if str(payload.get("entry") or "").upper() == "BUY":
                side = "long"
                adjusted_entry = entry_price * (1.0 + slippage_bps / 10000.0)
                adjusted_exit = exit_price * (1.0 - slippage_bps / 10000.0)
            else:
                side = "short"
                adjusted_entry = entry_price * (1.0 - slippage_bps / 10000.0)
                adjusted_exit = exit_price * (1.0 + slippage_bps / 10000.0)

            quantity = float(payload.get("peak_qty") or payload.get("quantity") or 0.0)
            plan = strategy.position_plans.get(position_id, {})
            stop_price = float(plan.get("stop_price") or 0.0)
            target_price = float(plan.get("target_price") or 0.0)
            if side == "long":
                pnl = (adjusted_exit - adjusted_entry) * quantity - commission_per_trade
            else:
                pnl = (adjusted_entry - adjusted_exit) * quantity - commission_per_trade
            risk_unit = abs(adjusted_entry - stop_price) * quantity if stop_price else 0.0
            pnl_pct = (pnl / capital_base * 100.0) if capital_base > 0 else 0.0
            entry_ts = int(payload["ts_opened"])
            exit_ts = int(payload["ts_closed"])
            entry_index = ts_index_map.get(entry_ts, 0)
            exit_index = ts_index_map.get(exit_ts, entry_index)
            trades.append(
                NautilusTrade(
                    instrument_id=instrument.id,
                    instrument_symbol=instrument.symbol,
                    side=side,
                    entry_at=_nanos_to_iso(entry_ts) or "",
                    exit_at=_nanos_to_iso(exit_ts) or "",
                    entry_price=round(adjusted_entry, 6),
                    exit_price=round(adjusted_exit, 6),
                    stop_price=round(stop_price, 6),
                    target_price=round(target_price, 6),
                    quantity=round(quantity, 4),
                    pnl=round(pnl, 4),
                    pnl_pct=round(pnl_pct, 4),
                    r_multiple=round((pnl / risk_unit), 4) if risk_unit > 0 else 0.0,
                    bars_held=max(1, exit_index - entry_index + 1),
                    exit_reason=strategy.exit_reasons.get(position_id, "session_close"),
                )
            )

        equity_curve = [
            {"ts": _nanos_to_iso(ts) or "", "equity": round(equity, 4)}
            for ts, equity in strategy.equity_curve
        ]
        if not equity_curve and nautilus_bars:
            equity_curve = [
                {
                    "ts": _nanos_to_iso(int(nautilus_bars[0].ts_event)) or "",
                    "equity": round(capital_base, 4),
                }
            ]
        return SingleInstrumentBacktestResult(
            trades=trades,
            equity_curve=equity_curve,
            warnings=list(dict.fromkeys(strategy.warnings)),
            total_events=int(result.total_events),
            total_orders=int(result.total_orders),
            total_positions=int(result.total_positions),
        )
    finally:
        engine.dispose()
