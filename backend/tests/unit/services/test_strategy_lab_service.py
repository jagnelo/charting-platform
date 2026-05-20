from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.ohlcv import OHLCVBar, Timeframe
from app.services.strategy_lab import (
    _apply_portfolio_constraints,
    _build_benchmark_summary,
    _build_dense_portfolio_history,
)
from app.services.strategy_lab_nautilus import NautilusOpenPosition, NautilusTrade


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


@pytest.mark.asyncio
async def test_build_benchmark_summary_returns_buy_and_hold_artifacts(monkeypatch):
    bars = [
        _bar(1, datetime(2026, 1, 1, tzinfo=UTC), 100.0),
        _bar(1, datetime(2026, 1, 2, tzinfo=UTC), 105.0),
        _bar(1, datetime(2026, 1, 3, tzinfo=UTC), 103.0),
    ]

    async def fake_resolve(_db, _config, _warnings):
        return [type('InstrumentRow', (), {'id': 1, 'symbol': 'SPY'})()]

    async def fake_load_bars(db, *, instrument_id, timeframe, date_from, date_to):
        assert instrument_id == 1
        assert timeframe == Timeframe.D1
        return bars

    monkeypatch.setattr('app.services.strategy_lab._resolve_universe_instruments', fake_resolve)
    monkeypatch.setattr('app.services.strategy_lab._load_bars_for_strategy', fake_load_bars)

    summary = await _build_benchmark_summary(
        object(),
        benchmark_symbol='SPY',
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
