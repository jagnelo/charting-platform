from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
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


def _period_start(period: str, reference_at: datetime) -> datetime:
    anchor = reference_at.astimezone(UTC)
    today = anchor.date()
    if period == "1D":
        return datetime(today.year, today.month, today.day, tzinfo=UTC) - timedelta(days=1)
    if period == "1W":
        return anchor - timedelta(weeks=1)
    if period == "1M":
        month = today.month - 1 or 12
        year = today.year - (1 if today.month == 1 else 0)
        d = date(year, month, min(today.day, 28))
        return datetime(d.year, d.month, d.day, tzinfo=UTC)
    if period == "3M":
        month = today.month - 3
        year = today.year
        if month <= 0:
            month += 12
            year -= 1
        d = date(year, month, min(today.day, 28))
        return datetime(d.year, d.month, d.day, tzinfo=UTC)
    if period == "6M":
        month = today.month - 6
        year = today.year
        if month <= 0:
            month += 12
            year -= 1
        d = date(year, month, min(today.day, 28))
        return datetime(d.year, d.month, d.day, tzinfo=UTC)
    if period == "MTD":
        return datetime(today.year, today.month, 1, tzinfo=UTC)
    if period == "QTD":
        q_start_month = ((today.month - 1) // 3) * 3 + 1
        return datetime(today.year, q_start_month, 1, tzinfo=UTC)
    if period == "YTD":
        return datetime(today.year, 1, 1, tzinfo=UTC)
    if period == "1Y":
        return datetime(today.year - 1, today.month, min(today.day, 28), tzinfo=UTC)
    return anchor - timedelta(days=1)


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
    timeframe: str = "D1"
    direction: str = "long"
    entry_logic: str = "all"
    conditions: tuple[dict[str, Any], ...] = ()
    condition_tree: dict[str, Any] | None = None
    signal_events: tuple[dict[str, Any], ...] = ()
    stop_loss_pct: float = 2.0
    take_profit_rr: float = 2.0
    max_bars_in_trade: int = 20
    risk_per_trade_pct: float = 1.0
    capital_base: float = 100_000.0
    break_even_rr: float = 0.0
    trailing_stop_rr: float = 0.0
    pyramiding_max_entries: int = 1
    daily_closes: tuple[float, ...] = ()
    daily_timestamps: tuple[int, ...] = ()
    weekly_closes: tuple[float, ...] = ()
    weekly_timestamps: tuple[int, ...] = ()
    instrument_context: dict[str, Any] | None = None


class StrategyLabNautilusStrategy(Strategy):
    def __init__(self, config: StrategyLabNautilusConfig) -> None:
        super().__init__(config)
        self.instrument = None
        self._indicator_cache: dict[tuple[str, int], Any] = {}
        self._previous_values: list[tuple[float | None, float | None]] | None = None
        self._previous_indicator_values: dict[tuple[str, int], float] = {}
        self._bar_snapshots: list[dict[str, float]] = []
        self.active_position_id: str | None = None
        self.position_plans: dict[str, dict[str, float | int | str]] = {}
        self.exit_reasons: dict[str, str] = {}
        self.equity_curve: list[tuple[int, float]] = []
        self.warnings: list[str] = []
        self._signal_events = sorted(
            [dict(event) for event in self.config.signal_events],
            key=lambda event: event.get("signal_at", ""),
        )
        self._signal_index = 0
        self._pending_signal_plan: dict[str, Any] | None = None

        self._register_tree_indicators(self.config.condition_tree)
        for condition in self.config.conditions:
            self._ensure_condition_indicators(condition)

    def _register_tree_indicators(self, node: dict[str, Any] | None) -> None:
        if not node:
            return
        node_type = str(node.get("type") or node.get("entry_logic") or "").lower()
        if node_type in {"all", "any", "not"}:
            for child in node.get("conditions", []) or []:
                if isinstance(child, dict):
                    self._register_tree_indicators(child)
            child = node.get("condition")
            if isinstance(child, dict):
                self._register_tree_indicators(child)
            return
        self._ensure_condition_indicators(node)

    def _ensure_condition_indicators(self, condition: dict[str, Any]) -> None:
        if self._is_shared_condition(condition):
            indicator = condition.get("indicator")
            params = condition.get("params") or {}
            if isinstance(indicator, str):
                self._ensure_indicator_ref(indicator, int(params.get("period") or 0))
            indicator_a = condition.get("indicator_a") or {}
            if isinstance(indicator_a, dict):
                self._ensure_indicator_ref(
                    str(indicator_a.get("type") or ""),
                    int((indicator_a.get("params") or {}).get("period") or 0),
                )
            indicator_b = condition.get("indicator_b") or {}
            if isinstance(indicator_b, dict):
                self._ensure_indicator_ref(
                    str(indicator_b.get("type") or ""),
                    int((indicator_b.get("params") or {}).get("period") or 0),
                )
            return
        self._ensure_indicator(condition, "left")
        self._ensure_indicator(condition, "right")

    def _ensure_indicator(self, condition: dict[str, Any], side: str) -> None:
        if condition.get(f"{side}_source") != "indicator":
            return
        indicator = str(condition.get(f"{side}_indicator") or "").lower()
        period = int(condition.get(f"{side}_period") or 0)
        self._ensure_indicator_ref(indicator, period)

    def _ensure_indicator_ref(self, indicator: str, period: int) -> None:
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
        self._append_bar_snapshot(bar)
        condition_values = [
            self._condition_values(condition, bar)
            if not self._is_shared_condition(condition)
            else (None, None)
            for condition in self.config.conditions
        ]
        due_signal = self._next_due_signal(bar)

        if self.active_position_id is not None:
            if self._maybe_exit(bar):
                self._record_equity(bar.ts_event)
                self._previous_values = condition_values
                self._snapshot_indicator_values()
                return
            if not self._has_pending_orders() and self._should_add_to_position(
                condition_values, bar
            ):
                self._submit_entry(bar)
        elif due_signal is not None and not self._has_pending_orders():
            self._submit_entry(bar, signal_plan=due_signal)
        elif not self._has_pending_orders() and self._should_enter(condition_values, bar):
            self._submit_entry(bar)

        self._sync_active_position()
        self._record_equity(bar.ts_event)
        self._previous_values = condition_values
        self._snapshot_indicator_values()

    def _next_due_signal(self, bar: Bar) -> dict[str, Any] | None:
        while self._signal_index < len(self._signal_events):
            event = self._signal_events[self._signal_index]
            signal_ts = event.get("signal_ts")
            if signal_ts is None:
                self._signal_index += 1
                continue
            if int(signal_ts) > int(bar.ts_event):
                return None
            self._signal_index += 1
            return event
        return None

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
            self.position_plans[position_id]["entry_count"] = max(
                int(self.position_plans[position_id].get("entry_count", 1)),
                1,
            )
            return

        entry_price = float(position.avg_px_open)
        pending_plan = dict(self._pending_signal_plan or {})
        plan_direction = str(pending_plan.get("side") or self.config.direction)
        if pending_plan:
            stop_price = float(pending_plan.get("stop_price") or 0.0)
            target_price = float(pending_plan.get("target_price") or 0.0)
            planned_entry = float(pending_plan.get("entry_price") or entry_price)
            if stop_price <= 0 or target_price <= 0:
                pending_plan = {}
            else:
                self.position_plans[position_id] = {
                    "entry_price": planned_entry,
                    "stop_price": stop_price,
                    "target_price": target_price,
                    "bars_elapsed": 0,
                    "best_price": entry_price,
                    "entry_count": 1,
                    "direction": plan_direction,
                    "setup_type": pending_plan.get("setup_type"),
                    "signal_score": pending_plan.get("score"),
                }
                self._pending_signal_plan = None
                return

        if plan_direction == "long":
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
            "best_price": entry_price,
            "entry_count": 1,
            "direction": plan_direction,
        }
        self._pending_signal_plan = None

    def _record_equity(self, ts_event: int) -> None:
        total_pnl = sum(
            _money_like_to_float(money) for money in self.portfolio.total_pnls().values()
        )
        equity = round(self.config.capital_base + total_pnl, 4)
        if self.equity_curve and self.equity_curve[-1][0] == ts_event:
            self.equity_curve[-1] = (ts_event, equity)
        else:
            self.equity_curve.append((ts_event, equity))

    def _submit_entry(self, bar: Bar, signal_plan: dict[str, Any] | None = None) -> None:
        reference_price = (
            float(signal_plan.get("entry_price")) if signal_plan else bar.close.as_double()
        )
        if signal_plan and signal_plan.get("stop_price") is not None:
            risk_distance = abs(reference_price - float(signal_plan["stop_price"]))
        else:
            risk_distance = reference_price * (self.config.stop_loss_pct / 100.0)
        if risk_distance <= 0:
            return
        risk_budget = self.config.capital_base * (self.config.risk_per_trade_pct / 100.0)
        raw_quantity = max(risk_budget / risk_distance, 1.0)
        quantity = self.instrument.make_qty(Decimal(str(raw_quantity)))
        side_token = str(signal_plan.get("side") if signal_plan else self.config.direction).lower()
        side = OrderSide.BUY if side_token == "long" else OrderSide.SELL
        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=side,
            quantity=quantity,
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order(order)
        if signal_plan:
            self._pending_signal_plan = dict(signal_plan)
        if self.active_position_id is not None and self.active_position_id in self.position_plans:
            self.position_plans[self.active_position_id]["entry_count"] = (
                int(self.position_plans[self.active_position_id].get("entry_count", 1)) + 1
            )

    def _maybe_exit(self, bar: Bar) -> bool:
        if self.active_position_id is None:
            return False
        plan = self.position_plans.get(self.active_position_id)
        if not plan:
            return False

        high = bar.high.as_double()
        low = bar.low.as_double()
        entry_price = float(plan["entry_price"])
        stop_price = float(plan["stop_price"])
        target_price = float(plan["target_price"])
        bars_elapsed = int(plan.get("bars_elapsed", 0))
        best_price = float(plan.get("best_price") or entry_price)
        direction = str(plan.get("direction") or self.config.direction).lower()
        risk_distance = abs(entry_price - stop_price)

        if direction == "long":
            best_price = max(best_price, high)
        else:
            best_price = min(best_price, low)
        plan["best_price"] = best_price

        if risk_distance > 0 and self.config.break_even_rr > 0:
            if direction == "long":
                if high >= entry_price + risk_distance * self.config.break_even_rr:
                    stop_price = max(stop_price, entry_price)
            else:
                if low <= entry_price - risk_distance * self.config.break_even_rr:
                    stop_price = min(stop_price, entry_price)
            plan["stop_price"] = stop_price

        if risk_distance > 0 and self.config.trailing_stop_rr > 0:
            trail_distance = risk_distance * self.config.trailing_stop_rr
            if direction == "long":
                stop_price = max(stop_price, best_price - trail_distance)
            else:
                stop_price = min(stop_price, best_price + trail_distance)
            plan["stop_price"] = stop_price

        reason: str | None = None
        if direction == "long":
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

    def _append_bar_snapshot(self, bar: Bar) -> None:
        self._bar_snapshots.append(
            {
                "ts": float(bar.ts_event),
                "open": bar.open.as_double(),
                "high": bar.high.as_double(),
                "low": bar.low.as_double(),
                "close": bar.close.as_double(),
                "volume": bar.volume.as_double(),
            }
        )
        if len(self._bar_snapshots) > 6000:
            self._bar_snapshots = self._bar_snapshots[-4000:]

    def _snapshot_indicator_values(self) -> None:
        snapshot: dict[tuple[str, int], float] = {}
        for key, instance in self._indicator_cache.items():
            value = getattr(instance, "value", None)
            if value is not None:
                snapshot[key] = float(value)
        self._previous_indicator_values = snapshot

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

    def _is_shared_condition(self, condition: dict[str, Any]) -> bool:
        return str(condition.get("type") or "") in {
            "indicator_threshold",
            "indicator_cross",
            "price_indicator",
            "price_threshold",
            "price_change",
            "price_change_period",
            "performance",
            "week52_new_high",
            "week52_new_low",
            "pct_from_52w_high",
            "pct_from_52w_low",
            "stats_filter",
            "fundamental_filter",
        }

    def _should_enter(
        self, current_values: list[tuple[float | None, float | None]], bar: Bar
    ) -> bool:
        if not self.config.conditions and not self.config.condition_tree:
            return False
        if self._indicator_cache and not self.indicators_initialized():
            return False
        if self.config.condition_tree:
            return self._evaluate_condition_tree(self.config.condition_tree, bar)

        matches: list[bool] = []
        for index, condition in enumerate(self.config.conditions):
            if self._is_shared_condition(condition):
                matches.append(self._evaluate_shared_condition(condition, bar))
                continue
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

    def _should_add_to_position(
        self, current_values: list[tuple[float | None, float | None]], bar: Bar
    ) -> bool:
        if self.active_position_id is None:
            return False
        plan = self.position_plans.get(self.active_position_id)
        if plan is None:
            return False
        if int(plan.get("entry_count", 1)) >= max(self.config.pyramiding_max_entries, 1):
            return False
        return self._should_enter(current_values, bar)

    def _evaluate_condition_tree(self, node: dict[str, Any] | None, bar: Bar) -> bool:
        if not node:
            return False
        node_type = str(node.get("type") or node.get("entry_logic") or "").lower()
        if node_type in {"all", "any"}:
            children = [
                child for child in node.get("conditions", []) or [] if isinstance(child, dict)
            ]
            if not children:
                return False
            results = [self._evaluate_condition_tree(child, bar) for child in children]
            return all(results) if node_type == "all" else any(results)
        if node_type == "not":
            child = node.get("condition")
            return not self._evaluate_condition_tree(
                child if isinstance(child, dict) else None, bar
            )

        left, right = self._condition_values(node, bar)
        prev_left = prev_right = None
        if self._previous_values:
            prev_left, prev_right = self._previous_values[0]
        if self._is_shared_condition(node):
            return self._evaluate_shared_condition(node, bar)
        return self._evaluate_condition(
            condition=node,
            left=left,
            right=right,
            prev_left=prev_left,
            prev_right=prev_right,
        )

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

    def _evaluate_shared_condition(self, condition: dict[str, Any], bar: Bar) -> bool:
        condition_type = str(condition.get("type") or "")
        operator = str(condition.get("op") or condition.get("operator") or "gt").lower()

        if condition_type == "indicator_threshold":
            indicator = str(condition.get("indicator") or "").lower()
            period = int((condition.get("params") or {}).get("period") or 0)
            current = self._current_indicator_value(indicator, period)
            target = self._numeric(condition.get("value"))
            return self._compare_numeric(operator, current, target)

        if condition_type == "indicator_cross":
            indicator_a = condition.get("indicator_a") or {}
            indicator_b = condition.get("indicator_b") or {}
            a_key = (
                str(indicator_a.get("type") or "").lower(),
                int((indicator_a.get("params") or {}).get("period") or 0),
            )
            b_key = (
                str(indicator_b.get("type") or "").lower(),
                int((indicator_b.get("params") or {}).get("period") or 0),
            )
            current_a = self._current_indicator_value(*a_key)
            current_b = self._current_indicator_value(*b_key)
            prev_a = self._previous_indicator_values.get(a_key)
            prev_b = self._previous_indicator_values.get(b_key)
            return self._compare_numeric(operator, current_a, current_b, prev_a, prev_b)

        if condition_type == "price_indicator":
            field = str(condition.get("field") or "close").lower()
            current = self._bar_field_value(bar, field)
            indicator = str(condition.get("indicator") or "").lower()
            period = int((condition.get("params") or {}).get("period") or 0)
            target = self._current_indicator_value(indicator, period)
            prev_left = self._previous_bar_field_value(field)
            prev_right = self._previous_indicator_values.get((indicator, period))
            return self._compare_numeric(operator, current, target, prev_left, prev_right)

        if condition_type == "price_threshold":
            field = str(condition.get("field") or "close").lower()
            current = self._bar_field_value(bar, field)
            target = self._numeric(condition.get("value"))
            return self._compare_numeric(operator, current, target)

        if condition_type == "price_change":
            lookback_bars = max(1, int(condition.get("lookback_bars") or 1))
            prior_close = self._historical_close(lookback_bars)
            current_close = bar.close.as_double()
            if prior_close in {None, 0}:
                return False
            change = (current_close - prior_close) / prior_close
            return self._compare_numeric(operator, change, self._numeric(condition.get("value")))

        if condition_type == "price_change_period":
            change = self._series_change_from_period(
                timestamps=[int(row["ts"]) for row in self._bar_snapshots],
                closes=[float(row["close"]) for row in self._bar_snapshots],
                period=str(condition.get("period") or "1D"),
            )
            if change is None:
                return False
            return self._compare_numeric(operator, change, self._numeric(condition.get("value")))

        if condition_type == "performance":
            timestamps, closes = self._daily_series()
            change = self._series_change_from_period(
                timestamps=timestamps,
                closes=closes,
                period=str(condition.get("period") or "1D"),
            )
            if change is None:
                return False
            return self._compare_numeric(operator, change, self._numeric(condition.get("value")))

        if condition_type == "week52_new_high":
            closes = self._weekly_closes()
            if len(closes) < 2:
                return False
            trailing = closes[-52:] if len(closes) >= 52 else closes
            current = trailing[-1]
            prior_high = max(trailing[:-1]) if len(trailing) > 1 else current
            return current >= prior_high

        if condition_type == "week52_new_low":
            closes = self._weekly_closes()
            if len(closes) < 2:
                return False
            trailing = closes[-52:] if len(closes) >= 52 else closes
            current = trailing[-1]
            prior_low = min(trailing[:-1]) if len(trailing) > 1 else current
            return current <= prior_low

        if condition_type == "pct_from_52w_high":
            closes = self._weekly_closes()
            if not closes:
                return False
            rolling_high = max(closes[-52:] if len(closes) >= 52 else closes)
            if rolling_high == 0:
                return False
            distance = (rolling_high - closes[-1]) / rolling_high
            return self._compare_numeric(operator, distance, self._numeric(condition.get("value")))

        if condition_type == "pct_from_52w_low":
            closes = self._weekly_closes()
            if not closes:
                return False
            rolling_low = min(closes[-52:] if len(closes) >= 52 else closes)
            if rolling_low == 0:
                return False
            distance = (closes[-1] - rolling_low) / rolling_low
            return self._compare_numeric(operator, distance, self._numeric(condition.get("value")))

        if condition_type == "stats_filter":
            field = str(condition.get("field") or "")
            actual = (self.config.instrument_context or {}).get("stats", {}).get(field)
            return self._compare_numeric(operator, self._numeric(actual), self._numeric(condition.get("value")))

        if condition_type == "fundamental_filter":
            field = str(condition.get("field") or "")
            actual = (self.config.instrument_context or {}).get("fundamentals", {}).get(field)
            if actual is None:
                return False
            if isinstance(actual, str):
                expected = str(condition.get("value") or "")
                return self._compare_text(operator, actual, expected)
            return self._compare_numeric(operator, self._numeric(actual), self._numeric(condition.get("value")))

        return False

    def _current_indicator_value(self, indicator: str, period: int) -> float | None:
        instance = self._indicator_cache.get((indicator, period))
        value = getattr(instance, "value", None) if instance is not None else None
        if value is None:
            return None
        return float(value)

    def _bar_field_value(self, bar: Bar, field: str) -> float | None:
        if field == "open":
            return bar.open.as_double()
        if field == "high":
            return bar.high.as_double()
        if field == "low":
            return bar.low.as_double()
        if field == "close":
            return bar.close.as_double()
        if field == "volume":
            return bar.volume.as_double()
        return None

    def _previous_bar_field_value(self, field: str) -> float | None:
        if len(self._bar_snapshots) < 2:
            return None
        return self._bar_snapshots[-2].get(field)

    def _historical_close(self, bars_back: int) -> float | None:
        if len(self._bar_snapshots) <= bars_back:
            return None
        return self._bar_snapshots[-1 - bars_back]["close"]

    def _daily_series(self) -> tuple[list[int], list[float]]:
        if self.config.timeframe.upper() == "D1":
            return (
                [int(row["ts"]) for row in self._bar_snapshots],
                [float(row["close"]) for row in self._bar_snapshots],
            )
        return (
            [int(value) for value in self.config.daily_timestamps],
            [float(value) for value in self.config.daily_closes],
        )

    def _weekly_closes(self) -> list[float]:
        if self.config.timeframe.upper() == "W1":
            return [float(row["close"]) for row in self._bar_snapshots]
        return [float(value) for value in self.config.weekly_closes]

    def _series_change_from_period(
        self,
        *,
        timestamps: list[int],
        closes: list[float],
        period: str,
    ) -> float | None:
        if len(closes) < 2 or len(timestamps) < 2:
            return None
        reference_at = datetime.fromtimestamp(timestamps[-1] / 1_000_000_000, tz=UTC)
        period_start_ts = _period_start(period, reference_at).timestamp() * 1_000_000_000
        ref_idx = None
        for index, ts in enumerate(timestamps):
            if ts >= period_start_ts:
                ref_idx = index
                break
        if ref_idx is None or ref_idx == len(closes) - 1:
            return None
        ref = float(closes[ref_idx])
        current = float(closes[-1])
        if ref == 0:
            return 0.0
        return (current - ref) / ref

    def _numeric(self, value: Any) -> float | None:
        if value is None:
            return None
        return float(value)

    def _compare_text(self, operator: str, actual: str, expected: str) -> bool:
        lhs = actual.lower()
        rhs = expected.lower()
        if operator == "eq":
            return lhs == rhs
        if operator == "contains":
            return rhs in lhs
        return False

    def _compare_numeric(
        self,
        operator: str,
        left: float | None,
        right: float | None,
        prev_left: float | None = None,
        prev_right: float | None = None,
    ) -> bool:
        if left is None or right is None:
            return False
        if operator == "gt":
            return left > right
        if operator == "gte":
            return left >= right
        if operator == "eq":
            return abs(left - right) < 1e-9
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
    daily_bars: list[OHLCVBar] | None = None,
    weekly_bars: list[OHLCVBar] | None = None,
    instrument_context: dict[str, Any] | None = None,
    timeframe: Timeframe,
    direction: str,
    entry_logic: str,
    conditions: list[dict[str, Any]],
    condition_tree: dict[str, Any] | None,
    stop_loss_pct: float,
    take_profit_rr: float,
    max_bars_in_trade: int,
    capital_base: float,
    risk_per_trade_pct: float,
    slippage_bps: float,
    commission_per_trade: float,
    break_even_rr: float = 0.0,
    trailing_stop_rr: float = 0.0,
    pyramiding_max_entries: int = 1,
    signal_events: list[dict[str, Any]] | None = None,
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
            timeframe=timeframe.value,
            direction=direction,
            entry_logic=entry_logic,
            conditions=tuple(conditions),
            condition_tree=condition_tree,
            signal_events=tuple(
                {
                    **event,
                    "signal_ts": dt_to_unix_nanos(event["signal_at"].astimezone(UTC))
                    if isinstance(event.get("signal_at"), datetime)
                    else event.get("signal_ts"),
                }
                for event in (signal_events or [])
            ),
            stop_loss_pct=stop_loss_pct,
            take_profit_rr=take_profit_rr,
            max_bars_in_trade=max_bars_in_trade,
            risk_per_trade_pct=risk_per_trade_pct,
            capital_base=capital_base,
            break_even_rr=break_even_rr,
            trailing_stop_rr=trailing_stop_rr,
            pyramiding_max_entries=max(1, pyramiding_max_entries),
            daily_closes=tuple(float(bar.close) for bar in (daily_bars or [])),
            daily_timestamps=tuple(
                dt_to_unix_nanos(bar.ts.astimezone(UTC)) for bar in (daily_bars or [])
            ),
            weekly_closes=tuple(float(bar.close) for bar in (weekly_bars or [])),
            weekly_timestamps=tuple(
                dt_to_unix_nanos(bar.ts.astimezone(UTC)) for bar in (weekly_bars or [])
            ),
            instrument_context=instrument_context or {},
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
