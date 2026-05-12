from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.services.strategy_lab_nautilus import run_single_instrument_nautilus_backtest


def _bar(ts: datetime, open_: float, high: float, low: float, close: float) -> OHLCVBar:
    return OHLCVBar(
        instrument_id=1,
        timeframe=Timeframe.D1,
        ts=ts,
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=Decimal("1000"),
        is_adjusted=True,
    )


def test_nautilus_backtest_runs_and_returns_trades():
    instrument = Instrument(
        id=1,
        instrument_type_id=1,
        symbol="AAPL",
        name="Apple Inc.",
        currency="USD",
        is_active=True,
    )
    start = datetime(2024, 1, 1, tzinfo=UTC)
    bars = []
    price = 100.0
    for index in range(16):
        ts = start + timedelta(days=index)
        open_ = price
        high = price + 3.0
        low = price - 1.0
        close = price + 2.0
        bars.append(_bar(ts, open_, high, low, close))
        price += 1.5

    result = run_single_instrument_nautilus_backtest(
        instrument=instrument,
        bars=bars,
        timeframe=Timeframe.D1,
        direction="long",
        entry_logic="all",
        conditions=[
            {
                "left_source": "indicator",
                "left_indicator": "ema",
                "left_period": 2,
                "operator": "gt",
                "right_source": "indicator",
                "right_indicator": "sma",
                "right_period": 4,
            }
        ],
        condition_tree=None,
        signal_events=None,
        stop_loss_pct=2.0,
        take_profit_rr=1.5,
        max_bars_in_trade=4,
        capital_base=100000.0,
        risk_per_trade_pct=1.0,
        slippage_bps=5.0,
        commission_per_trade=1.0,
    )

    assert result.trades
    assert result.total_orders >= 2
    assert result.total_positions >= 1
    assert result.equity_curve
    assert result.trades[0].instrument_symbol == "AAPL"
    assert result.trades[0].exit_reason in {
        "take_profit",
        "time_exit",
        "session_close",
        "stop_loss",
    }


def test_nautilus_backtest_replays_signal_events():
    instrument = Instrument(
        id=1,
        instrument_type_id=1,
        symbol="AAPL",
        name="Apple Inc.",
        currency="USD",
        is_active=True,
    )
    start = datetime(2024, 1, 1, tzinfo=UTC)
    bars = []
    price = 100.0
    for index in range(20):
        ts = start + timedelta(days=index)
        open_ = price
        high = price + 3.5
        low = price - 1.0
        close = price + 2.5
        bars.append(_bar(ts, open_, high, low, close))
        price += 1.2

    signal_at = bars[4].ts
    result = run_single_instrument_nautilus_backtest(
        instrument=instrument,
        bars=bars,
        timeframe=Timeframe.D1,
        direction="long",
        entry_logic="all",
        conditions=[],
        condition_tree=None,
        stop_loss_pct=2.0,
        take_profit_rr=2.0,
        max_bars_in_trade=6,
        capital_base=100000.0,
        risk_per_trade_pct=1.0,
        slippage_bps=5.0,
        commission_per_trade=1.0,
        signal_events=[
            {
                "signal_at": signal_at,
                "side": "long",
                "entry_price": float(bars[4].close),
                "stop_price": float(bars[4].close) * 0.98,
                "target_price": float(bars[4].close) * 1.04,
                "setup_type": "breakout",
                "score": 0.82,
            }
        ],
    )

    assert result.trades
    assert result.trades[0].side == "long"
    assert result.trades[0].entry_at >= signal_at.isoformat()


def test_nautilus_backtest_supports_nested_condition_trees():
    instrument = Instrument(
        id=1,
        instrument_type_id=1,
        symbol="AAPL",
        name="Apple Inc.",
        currency="USD",
        is_active=True,
    )
    start = datetime(2024, 1, 1, tzinfo=UTC)
    bars = []
    price = 100.0
    for index in range(18):
        ts = start + timedelta(days=index)
        open_ = price
        high = price + 3.2
        low = price - 1.1
        close = price + 2.1
        bars.append(_bar(ts, open_, high, low, close))
        price += 1.1

    result = run_single_instrument_nautilus_backtest(
        instrument=instrument,
        bars=bars,
        timeframe=Timeframe.D1,
        direction="long",
        entry_logic="all",
        conditions=[],
        condition_tree={
            "type": "all",
            "conditions": [
                {
                    "left_source": "indicator",
                    "left_indicator": "ema",
                    "left_period": 2,
                    "operator": "gt",
                    "right_source": "indicator",
                    "right_indicator": "sma",
                    "right_period": 4,
                },
                {
                    "type": "not",
                    "condition": {
                        "left_source": "indicator",
                        "left_indicator": "rsi",
                        "left_period": 3,
                        "operator": "gt",
                        "right_source": "value",
                        "right_value": 95,
                    },
                },
            ],
        },
        stop_loss_pct=2.0,
        take_profit_rr=1.5,
        max_bars_in_trade=4,
        capital_base=100000.0,
        risk_per_trade_pct=1.0,
        slippage_bps=5.0,
        commission_per_trade=1.0,
        signal_events=None,
    )

    assert result.trades
    assert result.total_positions >= 1
