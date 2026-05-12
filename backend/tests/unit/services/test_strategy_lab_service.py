from app.services.strategy_lab import _apply_portfolio_constraints
from app.services.strategy_lab_nautilus import NautilusTrade


def _trade(
    symbol: str, entry_at: str, exit_at: str, pnl: float, quantity: float = 100.0
) -> NautilusTrade:
    return NautilusTrade(
        instrument_id=1,
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
