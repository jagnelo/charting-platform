from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models.instrument import EquityDetail, Instrument
from app.models.instrument_stats import InstrumentStats
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

    assert result.trades or result.open_positions
    assert result.total_orders >= 2
    assert result.total_positions >= 1
    assert result.equity_curve
    first_position = result.trades[0] if result.trades else result.open_positions[0]
    assert first_position.instrument_symbol == "AAPL"
    if result.trades:
        assert result.trades[0].exit_reason in {
            "take_profit",
            "time_exit",
            "stop_loss",
            "condition_exit",
        }


def test_nautilus_backtest_supports_multiple_commission_models():
    instrument = Instrument(
        id=1,
        instrument_type_id=1,
        symbol="AAPL",
        name="Apple Inc.",
        currency="USD",
        is_active=True,
    )
    start = datetime(2024, 1, 1, tzinfo=UTC)
    bars = [
        _bar(start, 100.0, 101.0, 99.0, 100.0),
        _bar(start + timedelta(days=1), 100.0, 104.0, 99.5, 103.0),
        _bar(start + timedelta(days=2), 103.0, 105.0, 102.0, 104.0),
    ]

    common_kwargs = dict(
        instrument=instrument,
        bars=bars,
        timeframe=Timeframe.D1,
        direction="long",
        entry_logic="all",
        conditions=[],
        condition_tree=None,
        stop_loss_pct=2.0,
        take_profit_rr=0.0,
        max_bars_in_trade=1,
        capital_base=100000.0,
        position_sizing_mode="fixed_quantity",
        position_sizing_value=1.0,
        risk_per_trade_pct=1.0,
        slippage_bps=0.0,
        signal_events=[
            {
                "signal_at": bars[0].ts,
                "side": "long",
                "entry_price": float(bars[0].close),
            }
        ],
    )

    no_fee = run_single_instrument_nautilus_backtest(
        **common_kwargs,
        commission_per_trade=0.0,
        commission_model="fixed_round_trip",
        commission_value=0.0,
    )
    round_trip_fee = run_single_instrument_nautilus_backtest(
        **common_kwargs,
        commission_per_trade=1.0,
        commission_model="fixed_round_trip",
        commission_value=1.0,
    )
    per_order_fee = run_single_instrument_nautilus_backtest(
        **common_kwargs,
        commission_per_trade=1.0,
        commission_model="fixed_per_order",
        commission_value=1.0,
    )
    percent_fee = run_single_instrument_nautilus_backtest(
        **common_kwargs,
        commission_per_trade=0.1,
        commission_model="percent_of_notional",
        commission_value=0.1,
    )

    assert (
        no_fee.open_positions
        and round_trip_fee.open_positions
        and per_order_fee.open_positions
        and percent_fee.open_positions
    )

    no_fee_trade = no_fee.open_positions[0]
    round_trip_trade = round_trip_fee.open_positions[0]
    per_order_trade = per_order_fee.open_positions[0]
    percent_trade = percent_fee.open_positions[0]

    assert round(abs(no_fee_trade.unrealized_pnl - round_trip_trade.unrealized_pnl), 4) == 1.0
    assert round(abs(round_trip_trade.unrealized_pnl - per_order_trade.unrealized_pnl), 4) == 1.0

    expected_percent_commission = (
        abs(no_fee_trade.entry_price * no_fee_trade.quantity)
        + abs(no_fee_trade.current_price * no_fee_trade.quantity)
    ) * 0.001
    assert (
        abs(
            (no_fee_trade.unrealized_pnl - percent_trade.unrealized_pnl)
            - expected_percent_commission
        )
        < 0.01
    )


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

    assert result.trades or result.open_positions
    assert result.total_positions >= 1


def test_nautilus_backtest_supports_hard_percent_trailing_stop():
    instrument = Instrument(
        id=1,
        instrument_type_id=1,
        symbol="AAPL",
        name="Apple Inc.",
        currency="USD",
        is_active=True,
    )
    start = datetime(2024, 1, 1, tzinfo=UTC)
    bars = [
        _bar(start, 100.0, 101.0, 99.0, 100.0),
        _bar(start + timedelta(days=1), 100.0, 110.0, 100.0, 109.0),
        _bar(start + timedelta(days=2), 109.0, 111.0, 104.0, 105.0),
        _bar(start + timedelta(days=3), 105.0, 106.0, 103.0, 104.0),
    ]

    result = run_single_instrument_nautilus_backtest(
        instrument=instrument,
        bars=bars,
        timeframe=Timeframe.D1,
        direction="long",
        entry_logic="all",
        conditions=[],
        condition_tree=None,
        stop_loss_pct=2.0,
        take_profit_rr=0.0,
        max_bars_in_trade=0,
        capital_base=100000.0,
        risk_per_trade_pct=1.0,
        slippage_bps=0.0,
        commission_per_trade=0.0,
        hard_trailing_stop_pct=3.0,
        hard_trailing_activation_pct=5.0,
        signal_events=[
            {
                "signal_at": bars[0].ts,
                "side": "long",
                "entry_price": float(bars[0].close),
                "stop_price": 98.0,
                "target_price": 130.0,
            }
        ],
    )

    assert result.trades
    assert result.trades[0].exit_reason == "trailing_stop"
    assert result.trades[0].stop_price > result.trades[0].entry_price


def test_nautilus_backtest_supports_fixed_cash_position_sizing():
    instrument = Instrument(
        id=1,
        instrument_type_id=1,
        symbol="AAPL",
        name="Apple Inc.",
        currency="USD",
        is_active=True,
    )
    start = datetime(2024, 1, 1, tzinfo=UTC)
    bars = [
        _bar(start, 100.0, 101.0, 99.0, 100.0),
        _bar(start + timedelta(days=1), 100.0, 103.0, 99.5, 102.0),
        _bar(start + timedelta(days=2), 102.0, 104.0, 101.0, 103.0),
    ]

    result = run_single_instrument_nautilus_backtest(
        instrument=instrument,
        bars=bars,
        timeframe=Timeframe.D1,
        direction="long",
        entry_logic="all",
        conditions=[],
        condition_tree=None,
        stop_loss_pct=2.0,
        take_profit_rr=1.0,
        max_bars_in_trade=0,
        capital_base=100000.0,
        position_sizing_mode="fixed_cash",
        position_sizing_value=1000.0,
        risk_per_trade_pct=1.0,
        slippage_bps=0.0,
        commission_per_trade=0.0,
        signal_events=[
            {
                "signal_at": bars[0].ts,
                "side": "long",
                "entry_price": float(bars[0].close),
            }
        ],
    )

    assert result.trades
    assert abs(result.trades[0].quantity - 10.0) < 0.05


def test_nautilus_backtest_supports_atr_stop_model():
    instrument = Instrument(
        id=1,
        instrument_type_id=1,
        symbol="AAPL",
        name="Apple Inc.",
        currency="USD",
        is_active=True,
    )
    start = datetime(2024, 1, 1, tzinfo=UTC)
    bars = [_bar(start + timedelta(days=index), 100.0, 102.0, 98.0, 100.0) for index in range(15)]
    bars.extend(
        [
            _bar(start + timedelta(days=15), 100.0, 101.0, 99.0, 100.0),
            _bar(start + timedelta(days=16), 100.0, 101.0, 93.0, 94.0),
            _bar(start + timedelta(days=17), 94.0, 95.0, 92.0, 93.0),
        ]
    )

    result = run_single_instrument_nautilus_backtest(
        instrument=instrument,
        bars=bars,
        timeframe=Timeframe.D1,
        direction="long",
        entry_logic="all",
        conditions=[],
        condition_tree=None,
        stop_model="atr",
        stop_loss_pct=2.0,
        stop_atr_period=14,
        stop_atr_multiple=1.5,
        take_profit_rr=0.0,
        max_bars_in_trade=0,
        capital_base=100000.0,
        position_sizing_mode="fixed_quantity",
        position_sizing_value=1.0,
        risk_per_trade_pct=1.0,
        slippage_bps=0.0,
        commission_per_trade=0.0,
        signal_events=[
            {
                "signal_at": bars[14].ts,
                "side": "long",
                "entry_price": float(bars[14].close),
            }
        ],
    )

    assert result.trades
    assert result.trades[0].exit_reason == "stop_loss"
    assert abs(result.trades[0].stop_price - 94.0) < 0.5


def test_nautilus_backtest_supports_shared_condition_payloads():
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
    for index in range(30):
        ts = start + timedelta(days=index)
        open_ = price
        high = price + 3.0
        low = price - 1.0
        close = price + 2.0
        bars.append(_bar(ts, open_, high, low, close))
        price += 1.0

    result = run_single_instrument_nautilus_backtest(
        instrument=instrument,
        bars=bars,
        timeframe=Timeframe.D1,
        direction="long",
        entry_logic="all",
        conditions=[
            {
                "type": "price_indicator",
                "field": "close",
                "op": "gt",
                "indicator": "sma",
                "params": {"period": 3},
            },
            {
                "type": "price_change",
                "lookback_bars": 3,
                "op": "gt",
                "value": 0.01,
            },
        ],
        condition_tree={
            "type": "all",
            "conditions": [
                {
                    "type": "price_indicator",
                    "field": "close",
                    "op": "gt",
                    "indicator": "ema",
                    "params": {"period": 3},
                },
                {
                    "type": "price_change_period",
                    "period": "1W",
                    "op": "gt",
                    "value": 0.01,
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

    assert result.equity_curve
    assert result.total_positions >= 1


def test_nautilus_backtest_supports_broader_indicator_catalog_in_shared_conditions():
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
    for index in range(40):
        ts = start + timedelta(days=index)
        open_ = price
        high = price + 3.0
        low = price - 1.0
        close = price + 1.5
        bars.append(_bar(ts, open_, high, low, close))
        price += 1.1

    result = run_single_instrument_nautilus_backtest(
        instrument=instrument,
        bars=bars,
        timeframe=Timeframe.D1,
        direction="long",
        entry_logic="all",
        conditions=[
            {
                "type": "price_indicator",
                "field": "close",
                "op": "gt",
                "indicator": "wma",
                "params": {"period": 5},
            },
        ],
        condition_tree=None,
        stop_loss_pct=2.0,
        take_profit_rr=1.5,
        max_bars_in_trade=4,
        capital_base=100000.0,
        risk_per_trade_pct=1.0,
        slippage_bps=5.0,
        commission_per_trade=1.0,
        signal_events=None,
    )

    assert result.equity_curve
    assert result.total_positions >= 1


def test_nautilus_backtest_supports_fundamental_stats_and_performance_filters():
    instrument = Instrument(
        id=1,
        instrument_type_id=1,
        symbol="AAPL",
        name="Apple Inc.",
        currency="USD",
        is_active=True,
    )
    instrument.equity_detail = EquityDetail(
        instrument_id=1,
        sector="Technology",
        industry="Consumer Electronics",
        country="US",
        exchange_mic="XNAS",
        market_cap_tier="mega",
        employees=100000,
    )
    instrument.stats = InstrumentStats(
        instrument_id=1,
        market_cap=Decimal("2500000000000"),
        avg_volume_30d=Decimal("80000000"),
        pe_ratio=Decimal("28"),
        beta=Decimal("1.2"),
        dividend_yield=Decimal("0.005"),
    )
    start = datetime(2024, 1, 1, tzinfo=UTC)
    daily_bars = []
    price = 100.0
    for index in range(25):
        ts = start + timedelta(days=index)
        daily_bars.append(_bar(ts, price, price + 2.0, price - 1.0, price + 1.5))
        price += 1.0
    weekly_bars = [daily_bars[index] for index in range(0, len(daily_bars), 5)]

    result = run_single_instrument_nautilus_backtest(
        instrument=instrument,
        bars=weekly_bars,
        daily_bars=daily_bars,
        weekly_bars=weekly_bars,
        instrument_context={
            "fundamentals": {
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "country": "US",
                "exchange_mic": "XNAS",
                "market_cap_tier": "mega",
                "currency": "USD",
                "employees": 100000,
            },
            "stats": {
                "market_cap": 2500000000000,
                "avg_volume_30d": 80000000,
                "pe_ratio": 28,
                "beta": 1.2,
                "dividend_yield": 0.005,
            },
        },
        timeframe=Timeframe.W1,
        direction="long",
        entry_logic="all",
        conditions=[
            {"type": "fundamental_filter", "field": "sector", "op": "eq", "value": "Technology"},
            {"type": "stats_filter", "field": "market_cap", "op": "gt", "value": 1_000_000},
            {"type": "performance", "period": "1M", "op": "gt", "value": 0.01},
        ],
        condition_tree=None,
        stop_loss_pct=2.0,
        take_profit_rr=1.5,
        max_bars_in_trade=4,
        capital_base=100000.0,
        risk_per_trade_pct=1.0,
        slippage_bps=5.0,
        commission_per_trade=1.0,
        signal_events=None,
    )

    assert result.equity_curve
    assert result.total_positions >= 1


def test_nautilus_backtest_supports_condition_based_exits():
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
    closes = [100.0, 101.0, 102.0, 104.5, 105.0, 105.5]
    for index, close in enumerate(closes):
        ts = start + timedelta(days=index)
        bars.append(_bar(ts, close - 0.5, close + 1.0, close - 1.0, close))

    result = run_single_instrument_nautilus_backtest(
        instrument=instrument,
        bars=bars,
        timeframe=Timeframe.D1,
        direction="long",
        entry_logic="all",
        conditions=[],
        condition_tree=None,
        exit_logic="all",
        exit_conditions=[
            {"type": "price_threshold", "field": "close", "op": "gt", "value": 103.0},
        ],
        exit_condition_tree=None,
        stop_loss_pct=2.0,
        take_profit_rr=0.0,
        max_bars_in_trade=0,
        capital_base=100000.0,
        risk_per_trade_pct=1.0,
        slippage_bps=5.0,
        commission_per_trade=1.0,
        signal_events=[
            {
                "signal_at": bars[1].ts,
                "side": "long",
                "entry_price": float(bars[1].close),
                "stop_price": float(bars[1].close) * 0.98,
                "target_price": 0.0,
            }
        ],
    )

    assert result.trades
    assert result.trades[0].exit_reason == "condition_exit"


def test_nautilus_backtest_reports_open_positions_with_unrealized_pnl():
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
    closes = [100.0, 101.0, 102.5, 103.0, 104.0]
    for index, close in enumerate(closes):
        ts = start + timedelta(days=index)
        bars.append(_bar(ts, close - 0.5, close + 1.0, close - 1.0, close))

    result = run_single_instrument_nautilus_backtest(
        instrument=instrument,
        bars=bars,
        timeframe=Timeframe.D1,
        direction="long",
        entry_logic="all",
        conditions=[],
        condition_tree=None,
        exit_logic="all",
        exit_conditions=[],
        exit_condition_tree=None,
        stop_loss_pct=2.0,
        take_profit_rr=0.0,
        max_bars_in_trade=0,
        capital_base=100000.0,
        risk_per_trade_pct=1.0,
        slippage_bps=5.0,
        commission_per_trade=1.0,
        signal_events=[
            {
                "signal_at": bars[1].ts,
                "side": "long",
                "entry_price": float(bars[1].close),
                "stop_price": float(bars[1].close) * 0.98,
                "target_price": 0.0,
            }
        ],
    )

    assert not result.trades
    assert result.open_positions
    assert result.open_positions[0].status == "open"
    assert result.open_positions[0].unrealized_pnl > 0


def test_nautilus_backtest_can_force_close_open_positions_at_run_end():
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
    closes = [100.0, 101.0, 102.5, 103.0, 104.0]
    for index, close in enumerate(closes):
        ts = start + timedelta(days=index)
        bars.append(_bar(ts, close - 0.5, close + 1.0, close - 1.0, close))

    result = run_single_instrument_nautilus_backtest(
        instrument=instrument,
        bars=bars,
        timeframe=Timeframe.D1,
        direction="long",
        entry_logic="all",
        conditions=[],
        condition_tree=None,
        exit_logic="all",
        exit_conditions=[],
        exit_condition_tree=None,
        stop_loss_pct=2.0,
        take_profit_rr=0.0,
        max_bars_in_trade=0,
        capital_base=100000.0,
        risk_per_trade_pct=1.0,
        slippage_bps=5.0,
        commission_per_trade=1.0,
        close_open_positions_at_end=True,
        signal_events=[
            {
                "signal_at": bars[1].ts,
                "side": "long",
                "entry_price": float(bars[1].close),
                "stop_price": float(bars[1].close) * 0.98,
                "target_price": 0.0,
            }
        ],
    )

    assert not result.open_positions
    assert result.trades
    assert result.trades[0].exit_reason == "run_end_close"
    assert result.trades[0].pnl > 0
