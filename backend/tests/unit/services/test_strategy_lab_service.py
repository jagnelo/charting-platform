from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.research import CodeVersion, ResearchRun
from app.models.strategy import StrategyDefinition, StrategyRun, StrategyVersion
from app.services.strategy_lab import (
    _apply_portfolio_constraints,
    _build_benchmark_summary,
    _build_dense_portfolio_history,
    _extract_risk_and_exit_config,
    _queue_python_signal_research,
    _symbol_performance_snapshot,
    _trade_distributions,
)
from app.services.strategy_lab_nautilus import NautilusOpenPosition, NautilusTrade


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _ResearchQueueDB:
    def __init__(self, code_version):
        self.code_version = code_version
        self.added = []

    async def execute(self, _statement):
        return _ScalarResult(self.code_version)

    def add(self, value):
        if isinstance(value, ResearchRun):
            value.id = 77
        self.added.append(value)

    async def flush(self):
        return None


@pytest.mark.asyncio
async def test_python_signal_strategy_queues_immutable_isolated_research(monkeypatch):
    code_version = CodeVersion(
        id=10,
        code_asset_id=20,
        version_number=1,
        source="output.events('signals', [])",
        output_contract="events",
        default_parameters={"lookback": 20},
    )
    db = _ResearchQueueDB(code_version)

    async def materialize(*_args, **_kwargs):
        return {"symbols": ["SPY"], "datasets": []}

    monkeypatch.setattr("app.routers.research._materialize_declared_dataset", materialize)
    queued = []
    monkeypatch.setattr("app.services.strategy_lab.enqueue_research_run", queued.append)
    strategy = StrategyDefinition(user_id=4, name="Event signal", definition_type="python")
    version = StrategyVersion(
        strategy=strategy,
        definition_snapshot={"code_version_id": 10, "output_contract": "events"},
        default_parameters={"lookback": 5},
    )
    run = StrategyRun(
        strategy=strategy,
        strategy_version=version,
        requested_by_user_id=4,
        engine_type="nautilus",
        test_mode="backtest",
        universe_config={"symbols": ["SPY"]},
        parameter_values={"lookback": 30},
    )

    await _queue_python_signal_research(db, strategy=strategy, version=version, run=run)

    assert len(queued) == 1
    research_run = queued[0]
    assert research_run.id == 77
    assert research_run.code_version_id == 10
    assert research_run.run_config["parameters"] == {"lookback": 30}
    assert run.status == "queued"
    assert run.result_summary["research_run_id"] == 77
    assert run.result_summary["output_contract"] == "events"


@pytest.mark.asyncio
async def test_python_signal_strategy_carries_study_threshold_adapter_into_research_job(
    monkeypatch,
):
    code_version = CodeVersion(
        id=11,
        code_asset_id=21,
        version_number=1,
        source="output.series('trend', [1, 2, 3])",
        output_contract="boolean",
        output_name="trend",
        diagnostics=[
            {
                "code": "promotion_lineage",
                "lineage": {
                    "output_adapter": "series_target_to_boolean",
                    "series_target": {"operator": "gte", "threshold": 2.5},
                    "source_output_name": "trend",
                },
            }
        ],
    )
    db = _ResearchQueueDB(code_version)

    async def materialize(*_args, **_kwargs):
        return {"symbols": ["SPY"], "datasets": []}

    monkeypatch.setattr("app.routers.research._materialize_declared_dataset", materialize)
    queued = []
    monkeypatch.setattr("app.services.strategy_lab.enqueue_research_run", queued.append)
    strategy = StrategyDefinition(user_id=4, name="Threshold signal", definition_type="python")
    version = StrategyVersion(
        strategy=strategy,
        definition_snapshot={"code_version_id": 11, "output_contract": "boolean"},
    )
    run = StrategyRun(
        strategy=strategy,
        strategy_version=version,
        requested_by_user_id=4,
        engine_type="nautilus",
        test_mode="backtest",
        universe_config={"symbols": ["SPY"]},
    )

    await _queue_python_signal_research(db, strategy=strategy, version=version, run=run)

    research_run = queued[0]
    assert research_run.run_config["output_adapter"] == "series_target_to_boolean"
    assert research_run.run_config["series_target"] == {"operator": "gte", "threshold": 2.5}
    assert research_run.run_config["output_name"] == "trend"


def _trade(
    symbol: str,
    entry_at: str,
    exit_at: str,
    pnl: float,
    quantity: float = 100.0,
    instrument_id: int = 1,
) -> NautilusTrade:
    return NautilusTrade(
        instrument_id=instrument_id,
        instrument_symbol=symbol,
        side="long",
        entry_at=entry_at,
        exit_at=exit_at,
        entry_price=100.0,
        exit_price=102.0,
        stop_price=98.0,
        target_price=104.0,
        quantity=quantity,
        pnl=pnl,
        pnl_pct=pnl / 1000.0,
        r_multiple=1.0,
        bars_held=3,
        exit_reason="take_profit",
    )


def _bar(instrument_id: int, ts: datetime, close: float) -> OHLCVBar:
    return OHLCVBar(
        instrument_id=instrument_id,
        timeframe=Timeframe.D1,
        ts=ts,
        open=Decimal(str(close)),
        high=Decimal(str(close)),
        low=Decimal(str(close)),
        close=Decimal(str(close)),
        volume=Decimal("1000"),
        is_adjusted=True,
    )


def test_trade_distributions_include_bar_based_mae_and_mfe():
    trade = _trade("AAPL", "2026-01-01T00:00:00+00:00", "2026-01-03T00:00:00+00:00", 200.0)
    bars = {
        1: [
            OHLCVBar(
                instrument_id=1,
                timeframe=Timeframe.D1,
                ts=datetime(2026, 1, 1, tzinfo=UTC),
                open=Decimal("100"),
                high=Decimal("103"),
                low=Decimal("99"),
                close=Decimal("101"),
                volume=Decimal("1000"),
                is_adjusted=True,
            ),
            OHLCVBar(
                instrument_id=1,
                timeframe=Timeframe.D1,
                ts=datetime(2026, 1, 2, tzinfo=UTC),
                open=Decimal("101"),
                high=Decimal("106"),
                low=Decimal("98"),
                close=Decimal("104"),
                volume=Decimal("1000"),
                is_adjusted=True,
            ),
            OHLCVBar(
                instrument_id=1,
                timeframe=Timeframe.D1,
                ts=datetime(2026, 1, 3, tzinfo=UTC),
                open=Decimal("104"),
                high=Decimal("105"),
                low=Decimal("102"),
                close=Decimal("102"),
                volume=Decimal("1000"),
                is_adjusted=True,
            ),
        ]
    }
    distributions = _trade_distributions([trade], bars_by_instrument=bars)
    excursion = distributions["mae_mfe"]
    assert excursion["sample_size"] == 1
    assert excursion["rows"][0]["mae_pct"] == -2.0
    assert excursion["rows"][0]["mfe_pct"] == 6.0
    assert excursion["mae_histogram"]
    assert excursion["mfe_histogram"]


def test_trade_distributions_preserve_unmaterialized_rows_and_use_short_semantics():
    short_trade = NautilusTrade(
        instrument_id=2,
        instrument_symbol="TSLA",
        side="short",
        entry_at="2026-01-01T00:00:00+00:00",
        exit_at="2026-01-02T00:00:00+00:00",
        entry_price=100.0,
        exit_price=96.0,
        stop_price=103.0,
        target_price=94.0,
        quantity=1.0,
        pnl=4.0,
        pnl_pct=0.04,
        r_multiple=0.4,
        bars_held=2,
        exit_reason="target",
    )
    distributions = _trade_distributions(
        [short_trade],
        bars_by_instrument={
            2: [
                OHLCVBar(
                    instrument_id=2,
                    timeframe=Timeframe.D1,
                    ts=datetime(2026, 1, 1, tzinfo=UTC),
                    open=Decimal("100"),
                    high=Decimal("102"),
                    low=Decimal("95"),
                    close=Decimal("98"),
                    volume=Decimal("1000"),
                    is_adjusted=True,
                ),
                OHLCVBar(
                    instrument_id=2,
                    timeframe=Timeframe.D1,
                    ts=datetime(2026, 1, 2, tzinfo=UTC),
                    open=Decimal("98"),
                    high=Decimal("101"),
                    low=Decimal("96"),
                    close=Decimal("96"),
                    volume=Decimal("1000"),
                    is_adjusted=True,
                ),
            ]
        },
    )
    short_excursion = distributions["mae_mfe"]["rows"][0]
    assert short_excursion["mae_pct"] == -2.0
    assert short_excursion["mfe_pct"] == 5.0

    unavailable = _trade("MSFT", "2026-01-01T00:00:00+00:00", "2026-01-02T00:00:00+00:00", 50.0)
    unavailable_row = _trade_distributions([unavailable], bars_by_instrument={})["mae_mfe"]["rows"][
        0
    ]
    assert unavailable_row["bars_available"] == 0
    assert unavailable_row["mae_pct"] is None
    assert unavailable_row["mfe_pct"] is None


def _open_position(
    symbol: str,
    entry_at: str,
    current_at: str,
    unrealized_pnl: float,
    quantity: float = 100.0,
    instrument_id: int = 1,
) -> NautilusOpenPosition:
    return NautilusOpenPosition(
        instrument_id=instrument_id,
        instrument_symbol=symbol,
        side="long",
        entry_at=entry_at,
        current_at=current_at,
        entry_price=100.0,
        current_price=101.0,
        stop_price=98.0,
        target_price=104.0,
        quantity=quantity,
        unrealized_pnl=unrealized_pnl,
        unrealized_pnl_pct=unrealized_pnl / 1000.0,
        r_multiple=0.5,
        bars_held=3,
    )


def test_extract_risk_and_exit_config_treats_null_optional_controls_as_disabled():
    config = _extract_risk_and_exit_config(
        {
            "risk": {
                "stop_loss_pct": 2.0,
                "hard_trailing_stop_pct": None,
                "break_even_rr": None,
                "trailing_stop_rr": None,
            },
            "exits": {
                "take_profit_rr": None,
                "max_bars_in_trade": None,
            },
        }
    )

    assert config["stop_loss_pct"] == 2.0
    assert config["hard_trailing_stop_pct"] == 0
    assert config["break_even_rr"] == 0
    assert config["trailing_stop_rr"] == 0
    assert config["take_profit_rr"] == 0
    assert config["max_bars_in_trade"] == 0


def test_apply_portfolio_constraints_rejects_overlapping_trades_when_concurrency_is_limited():
    result = _apply_portfolio_constraints(
        [
            _trade("AAPL", "2026-01-01T00:00:00+00:00", "2026-01-05T00:00:00+00:00", 200.0),
            _trade("MSFT", "2026-01-02T00:00:00+00:00", "2026-01-04T00:00:00+00:00", 150.0),
        ],
        initial_capital=100000.0,
        max_concurrent_positions=1,
        max_portfolio_risk_pct=5.0,
        max_symbol_allocation_pct=100.0,
        fallback_ts="2026-01-01T00:00:00+00:00",
    )

    assert result["summary"]["accepted_trade_count"] == 1
    assert result["summary"]["rejected_trade_count"] == 1
    assert result["rejected_trades"][0]["reason"] == "max_concurrent_positions"
    rejected_events = [
        event for event in result["execution_log"] if event["event_type"] == "rejected"
    ]
    assert len(rejected_events) == 1
    assert rejected_events[0]["symbol"] == "MSFT"
    assert rejected_events[0]["reason"] == "max_concurrent_positions"


def test_apply_portfolio_constraints_builds_portfolio_equity_from_accepted_trades():
    result = _apply_portfolio_constraints(
        [
            _trade("AAPL", "2026-01-01T00:00:00+00:00", "2026-01-05T00:00:00+00:00", 200.0),
            _trade("MSFT", "2026-01-06T00:00:00+00:00", "2026-01-08T00:00:00+00:00", -50.0),
        ],
        initial_capital=100000.0,
        max_concurrent_positions=2,
        max_portfolio_risk_pct=5.0,
        max_symbol_allocation_pct=100.0,
        fallback_ts="2026-01-01T00:00:00+00:00",
    )

    assert result["summary"]["accepted_trade_count"] == 2
    assert result["equity_curve"][0]["equity"] == 100000.0
    assert result["equity_curve"][-1]["equity"] == 100150.0


def test_build_dense_portfolio_history_tracks_full_bar_timeline():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    bars_by_instrument = {
        1: [_bar(1, start + timedelta(days=index), 100.0 + index) for index in range(5)],
        2: [_bar(2, start + timedelta(days=index), 200.0 + index * 2) for index in range(5)],
    }

    history = _build_dense_portfolio_history(
        [
            _trade(
                "AAPL",
                "2026-01-02T00:00:00+00:00",
                "2026-01-04T00:00:00+00:00",
                200.0,
                quantity=10.0,
                instrument_id=1,
            ),
            _trade(
                "MSFT",
                "2026-01-03T00:00:00+00:00",
                "2026-01-05T00:00:00+00:00",
                100.0,
                quantity=5.0,
                instrument_id=2,
            ),
        ],
        bars_by_instrument=bars_by_instrument,
        initial_capital=100000.0,
        fallback_ts="2026-01-01T00:00:00+00:00",
    )

    equity_curve = history["equity_curve"]
    portfolio_timeline = history["portfolio_timeline"]

    assert len(equity_curve) == 5
    assert len(portfolio_timeline) == 5
    assert equity_curve[0]["ts"] == "2026-01-01T00:00:00+00:00"
    assert portfolio_timeline[1]["open_position_count"] == 1
    assert portfolio_timeline[2]["open_position_count"] == 2
    assert portfolio_timeline[-1]["open_position_count"] == 0
    assert float(equity_curve[-1]["equity"]) == 100300.0


def test_apply_portfolio_constraints_includes_open_positions_in_execution_log():
    result = _apply_portfolio_constraints(
        [
            _trade("AAPL", "2026-01-01T00:00:00+00:00", "2026-01-05T00:00:00+00:00", 200.0),
        ],
        open_positions=[
            _open_position(
                "MSFT",
                "2026-01-06T00:00:00+00:00",
                "2026-01-08T00:00:00+00:00",
                125.0,
                quantity=5.0,
                instrument_id=2,
            ),
        ],
        initial_capital=100000.0,
        max_concurrent_positions=2,
        max_portfolio_risk_pct=5.0,
        max_symbol_allocation_pct=100.0,
        fallback_ts="2026-01-01T00:00:00+00:00",
    )

    assert result["summary"]["accepted_trade_count"] == 1
    assert result["summary"]["accepted_open_position_count"] == 1
    assert result["summary"]["accepted_position_count"] == 2
    assert len(result["accepted_open_positions"]) == 1
    assert [event["event_type"] for event in result["execution_log"]] == [
        "entry",
        "exit",
        "entry",
        "open_at_end",
    ]
    assert result["execution_log"][-1]["symbol"] == "MSFT"
    assert result["execution_log"][-1]["pnl"] == 125.0


def test_symbol_performance_snapshot_splits_realized_and_unrealized_pnl():
    rows = _symbol_performance_snapshot(
        [
            _trade("AAPL", "2026-01-01T00:00:00+00:00", "2026-01-05T00:00:00+00:00", 200.0),
            _trade("MSFT", "2026-01-01T00:00:00+00:00", "2026-01-05T00:00:00+00:00", -50.0),
        ],
        open_positions=[
            _open_position("AAPL", "2026-01-06T00:00:00+00:00", "2026-01-08T00:00:00+00:00", 125.0),
            _open_position("NVDA", "2026-01-06T00:00:00+00:00", "2026-01-08T00:00:00+00:00", 75.0),
        ],
    )

    by_symbol = {row["symbol"]: row for row in rows}
    assert by_symbol["AAPL"]["realized_pnl"] == 200.0
    assert by_symbol["AAPL"]["unrealized_pnl"] == 125.0
    assert by_symbol["AAPL"]["net_pnl"] == 325.0
    assert by_symbol["AAPL"]["open_position_count"] == 1
    assert by_symbol["NVDA"]["trade_count"] == 0
    assert by_symbol["NVDA"]["unrealized_pnl"] == 75.0


@pytest.mark.asyncio
async def test_build_benchmark_summary_returns_buy_and_hold_artifacts(monkeypatch):
    bars = [
        _bar(1, datetime(2026, 1, 1, tzinfo=UTC), 100.0),
        _bar(1, datetime(2026, 1, 2, tzinfo=UTC), 105.0),
        _bar(1, datetime(2026, 1, 3, tzinfo=UTC), 103.0),
    ]

    async def fake_resolve(_db, _config, _warnings):
        return [type("InstrumentRow", (), {"id": 1, "symbol": "SPY", "equity_detail": None})()]

    async def fake_load_bars(db, *, instrument_id, timeframe, date_from, date_to):
        assert instrument_id == 1
        assert timeframe == Timeframe.D1
        return bars

    async def fake_benchmark_coverage(*_args, **_kwargs):
        return {
            "symbol": "SPY",
            "preview_note": None,
            "requested_status": "full",
            "available_from": bars[0].ts.isoformat(),
            "available_to": bars[-1].ts.isoformat(),
            "requested_first_bar_at": bars[0].ts.isoformat(),
            "requested_last_bar_at": bars[-1].ts.isoformat(),
            "total_bars": len(bars),
            "requested_bars": len(bars),
            "requested_fits_range": True,
        }

    monkeypatch.setattr("app.services.strategy_lab._resolve_universe_instruments", fake_resolve)
    monkeypatch.setattr("app.services.strategy_lab._load_bars_for_strategy", fake_load_bars)
    monkeypatch.setattr(
        "app.services.strategy_lab._build_benchmark_coverage_summary", fake_benchmark_coverage
    )

    summary = await _build_benchmark_summary(
        object(),
        benchmark_symbol="SPY",
        timeframe=Timeframe.D1,
        date_from=bars[0].ts,
        date_to=bars[-1].ts,
        initial_capital=100000.0,
    )

    assert summary["symbol"] == "SPY"
    assert summary["performance"]["net_return_pct"] == 3.0
    assert summary["drawdown_curve"]
    assert summary["position_timeline"]["symbol"] == "SPY"
    assert summary["execution_log"][0]["event_type"] == "entry"
    assert summary["execution_log"][-1]["event_type"] == "open_at_end"
    assert summary["portfolio_timeline"][-1]["open_position_count"] == 1
    assert summary["coverage"]["requested_status"] == "full"
