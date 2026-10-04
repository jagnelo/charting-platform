from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    CASH_EQUITY_NOTIONAL_RISK_MODEL,
    PortfolioComponent,
    PortfolioComposition,
    SharedRiskPolicy,
)
from app.strategy_lab_v2.nautilus_portfolio_wire import (
    portfolio_composition_from_wire,
    portfolio_composition_to_wire,
)
from app.strategy_lab_v2.nautilus_runtime_data import NautilusRuntimeDataError
from app.strategy_lab_v2.nautilus_target_allocation import (
    resolve_nautilus_target_position_intents,
)
from app.strategy_lab_v2.sdk import OrderSide, TargetPositionIntent

EVENT_TIME = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)


def _portfolio(*, max_gross: Decimal = Decimal("1")) -> PortfolioComposition:
    return PortfolioComposition(
        portfolio_id="portfolio-1",
        version_id="portfolio-v1",
        initial_capital=Decimal("100000"),
        base_currency="USD",
        components=(
            PortfolioComponent(
                component_id="core",
                strategy_fingerprint=content_digest("strategy"),
                instrument_ids=("US.AAPL",),
                capital_weight=Decimal("1"),
            ),
        ),
        shared_risk_policy=SharedRiskPolicy(
            max_gross_exposure_fraction=max_gross,
            risk_models=(CASH_EQUITY_NOTIONAL_RISK_MODEL,),
        ),
    )


def _instruments(*, quote_currency: str = "USD") -> dict[str, dict[str, object]]:
    return {
        "US.AAPL": {
            "instrument_id": "US.AAPL",
            "product_class": "equity",
            "quote_currency": quote_currency,
            "multiplier": "1",
            "size_increment": "1",
            "size_precision": 0,
            "min_quantity": "1",
            "max_quantity": None,
        }
    }


def _resolve(
    *,
    portfolio: PortfolioComposition | None = None,
    fraction: Decimal = Decimal("0.5"),
    current_quantity: Decimal = Decimal(0),
    current_exposure: Decimal = Decimal(0),
    quote_currency: str = "USD",
):
    selected_portfolio = portfolio or _portfolio()
    return resolve_nautilus_target_position_intents(
        portfolio=selected_portfolio,
        component_id="core",
        intents=(TargetPositionIntent("US.AAPL", fraction),),
        run_attempt_id="attempt-1",
        event_time=EVENT_TIME,
        event_sequence=4,
        account_equity=Decimal("100000"),
        account_cash_balance=Decimal("100000"),
        current_base_exposures=({} if current_exposure == 0 else {"US.AAPL": current_exposure}),
        current_quantities={"US.AAPL": current_quantity},
        mark_prices={"US.AAPL": Decimal("200")},
        instruments=_instruments(quote_currency=quote_currency),
    )


def test_portfolio_allocation_policy_round_trips_with_exact_fingerprint() -> None:
    portfolio = _portfolio()
    restored = portfolio_composition_from_wire(portfolio_composition_to_wire(portfolio))

    assert restored == portfolio
    tampered = portfolio_composition_to_wire(portfolio)
    tampered["shared_risk_policy"]["max_gross_exposure_fraction"] = "2"
    with pytest.raises(ValueError, match="fingerprint"):
        portfolio_composition_from_wire(tampered)


def test_target_fraction_is_allocated_then_translated_to_a_lot_sized_market_order() -> None:
    result = _resolve()

    assert result.allocation.risk_limits_satisfied is True
    assert result.allocation.risk_approved_instrument_targets[0].target_signed_base_notional == (
        Decimal("50000")
    )
    assert len(result.order_intents) == 1
    assert result.order_intents[0].side is OrderSide.BUY
    assert result.order_intents[0].quantity == Decimal("250")


def test_target_allocation_submits_only_the_delta_from_native_position() -> None:
    result = _resolve(current_quantity=Decimal("50"), current_exposure=Decimal("10000"))

    assert len(result.order_intents) == 1
    assert result.order_intents[0].side is OrderSide.BUY
    assert result.order_intents[0].quantity == Decimal("200")


def test_target_allocation_fails_closed_on_shared_risk_breach() -> None:
    with pytest.raises(NautilusRuntimeDataError, match="breaches shared portfolio risk"):
        _resolve(fraction=Decimal("1.5"))


def test_target_sizing_fails_closed_when_quote_currency_needs_conversion() -> None:
    with pytest.raises(NautilusRuntimeDataError, match="base-quoted linear spot"):
        _resolve(quote_currency="EUR")


def test_target_allocation_fails_closed_on_short_without_policy_permission() -> None:
    with pytest.raises(NautilusRuntimeDataError, match="breaches shared portfolio risk"):
        _resolve(fraction=Decimal("-0.1"))
