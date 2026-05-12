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
