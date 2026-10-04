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
from app.strategy_lab_v2.nautilus_order_routing import resolve_nautilus_order_intents
from app.strategy_lab_v2.nautilus_runtime_data import NautilusRuntimeDataError
from app.strategy_lab_v2.order_routing import OrderRoutingDecisionKind
from app.strategy_lab_v2.sdk import OrderIntent, OrderSide, OrderType, TimeInForce

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


def _resolve(
    *,
    quantity: str = "10",
    max_gross: Decimal = Decimal("1"),
    current_exposure: Decimal = Decimal(0),
    quote_currency: str = "USD",
):
    portfolio = _portfolio(max_gross=max_gross)
    intent = OrderIntent(
        instrument_id="US.AAPL",
        side=OrderSide.BUY,
        quantity=Decimal(quantity),
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
    )
    result = resolve_nautilus_order_intents(
        portfolio=portfolio,
        component_id="core",
        intents=(intent,),
        run_attempt_id="attempt-1",
        event_time=EVENT_TIME,
        event_sequence=4,
        account_equity=Decimal("100000"),
        account_cash_balance=Decimal("100000") - current_exposure,
        current_base_exposures=({} if current_exposure == 0 else {"US.AAPL": current_exposure}),
        current_quantities=({} if current_exposure == 0 else {"US.AAPL": current_exposure / 200}),
        mark_prices={"US.AAPL": Decimal("200")},
        instruments={
            "US.AAPL": {
                "instrument_id": "US.AAPL",
                "product_class": "equity",
                "base_currency": None,
                "quote_currency": quote_currency,
                "multiplier": "1",
                "price_increment": "0.01",
                "size_increment": "1",
                "size_precision": 0,
                "min_quantity": "1",
                "max_quantity": "1000",
            }
        },
    )
    return intent, result


def test_native_order_routes_to_shared_risk_and_preserves_approved_intent() -> None:
    intent, result = _resolve()

    assert result.decision.kind is OrderRoutingDecisionKind.APPROVED
    assert result.decision.risk_limits_satisfied is True
    assert result.decision.proposed_orders[0].estimated_signed_base_notional == Decimal("2000")
    assert result.order_intents == (intent,)


def test_native_order_risk_includes_open_native_exposure() -> None:
    with pytest.raises(NautilusRuntimeDataError, match="breaches shared portfolio risk"):
        _resolve(max_gross=Decimal("0.5"), current_exposure=Decimal("50000"))


def test_native_order_fails_closed_when_currency_conversion_is_not_bound() -> None:
    with pytest.raises(NautilusRuntimeDataError, match="base-quoted linear"):
        _resolve(quote_currency="EUR")


def test_native_order_fails_closed_when_quantity_exceeds_product_limit() -> None:
    with pytest.raises(NautilusRuntimeDataError, match="exceeds instrument maximum"):
        _resolve(quantity="1001")
