from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal, localcontext

import pytest

from app.strategy_lab_v2.allocation import (
    ComponentPositionExposure,
    InstrumentRiskBinding,
    PortfolioExposureSnapshot,
    RiskBreach,
)
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    CASH_EQUITY_NOTIONAL_RISK_MODEL,
    OPTION_DELTA_NOTIONAL_RISK_MODEL,
    PortfolioComponent,
    PortfolioComposition,
    ProductClass,
    ProductRiskModel,
    RiskExposureMeasure,
    SharedRiskPolicy,
)
from app.strategy_lab_v2.order_routing import (
    InstrumentOrderEconomics,
    OrderRoutingDecisionKind,
    route_order_intents,
)
from app.strategy_lab_v2.sdk import OrderIntent, OrderSide, OrderType, TimeInForce

EVENT_TIME = datetime(2024, 1, 2, 15, 0, tzinfo=UTC)
VALUATION_DIGEST = content_digest("order-routing-valuation-v1")


def _portfolio(policy: SharedRiskPolicy | None = None) -> PortfolioComposition:
    return PortfolioComposition(
        "portfolio-1",
        "v1",
        Decimal("100000"),
        "USD",
        (
            PortfolioComponent(
                "alpha", content_digest("alpha-strategy"), ("US.AAPL",), Decimal("1.0")
            ),
        ),
        shared_risk_policy=policy
        or SharedRiskPolicy(risk_models=(CASH_EQUITY_NOTIONAL_RISK_MODEL,)),
    )


def _snapshot(
    portfolio: PortfolioComposition,
    *,
    position_notional: Decimal = Decimal(0),
    sequence: int = 10,
    risk_model=CASH_EQUITY_NOTIONAL_RISK_MODEL,
) -> PortfolioExposureSnapshot:
    return PortfolioExposureSnapshot(
        portfolio.fingerprint,
        "order-routing-attempt",
        EVENT_TIME,
        sequence,
        Decimal("100000"),
        Decimal("50000"),
        "USD",
        VALUATION_DIGEST,
        positions=tuple(
            ()
            if position_notional == 0
            else (
                ComponentPositionExposure("alpha", "US.AAPL", position_notional),
            )
        ),
        instrument_risk_models=(
            InstrumentRiskBinding("US.AAPL", risk_model),
        ),
    )


def _economics(
    *,
    risk_model: ProductRiskModel = CASH_EQUITY_NOTIONAL_RISK_MODEL,
    mark_price: Decimal = Decimal("100"),
    contract_multiplier: Decimal = Decimal("1"),
    underlying_mark_price: Decimal | None = None,
    option_delta: Decimal | None = None,
) -> InstrumentOrderEconomics:
    return InstrumentOrderEconomics(
        instrument_id="US.AAPL",
        risk_model=risk_model,
        mark_price=mark_price,
        contract_multiplier=contract_multiplier,
        quantity_step=Decimal("0.01"),
        minimum_quantity=Decimal("0.01"),
        quote_currency="USD",
        base_currency="USD",
        quote_to_base_rate=Decimal("1"),
        valuation_evidence_digest=VALUATION_DIGEST,
        price_tick=Decimal("0.01"),
        underlying_mark_price=underlying_mark_price,
        option_delta=option_delta,
    )


def _order(
    side: OrderSide = OrderSide.BUY,
    quantity: str = "10",
    *,
    order_type: OrderType = OrderType.MARKET,
    limit_price: str | None = None,
    stop_price: str | None = None,
    tag: str | None = "order-1",
) -> OrderIntent:
    return OrderIntent(
        "US.AAPL",
        side,
        Decimal(quantity),
        order_type,
        TimeInForce.DAY,
        None if limit_price is None else Decimal(limit_price),
        None if stop_price is None else Decimal(stop_price),
        tag,
    )


def test_cash_equity_order_is_sized_and_approved_as_an_estimate() -> None:
    portfolio = _portfolio()
    decision = route_order_intents(
        portfolio,
        _snapshot(portfolio),
        {"alpha": (_order(quantity="10"),)},
        {"US.AAPL": _economics()},
        event_time=EVENT_TIME,
        event_sequence=10,
    )

    assert decision.kind is OrderRoutingDecisionKind.APPROVED
    assert decision.risk_limits_satisfied
    assert decision.gross_exposure_fraction == Decimal("0.01")
    assert decision.net_exposure_fraction == Decimal("0.01")
    assert decision.risk_approved_orders == decision.proposed_orders
    routed = decision.proposed_orders[0]
    assert routed.estimated_signed_base_notional == Decimal("1000")
    assert routed.valuation_evidence_digest == VALUATION_DIGEST
    assert routed.fingerprint == decision.proposed_orders[0].fingerprint


def test_sell_order_closes_existing_exposure_without_opening_a_short() -> None:
    portfolio = _portfolio()
    decision = route_order_intents(
        portfolio,
        _snapshot(portfolio, position_notional=Decimal("1000")),
        {"alpha": (_order(OrderSide.SELL, quantity="10"),)},
        {"US.AAPL": _economics()},
        event_time=EVENT_TIME,
        event_sequence=10,
    )

    assert decision.risk_limits_satisfied
    assert decision.gross_exposure_fraction == Decimal(0)
    assert decision.open_instrument_count == 0
    assert decision.proposed_orders[0].estimated_signed_base_notional == Decimal("-1000")


def test_shared_risk_breach_withholds_every_order() -> None:
    portfolio = _portfolio(SharedRiskPolicy(
        max_gross_exposure_fraction=Decimal("0.50"),
        risk_models=(CASH_EQUITY_NOTIONAL_RISK_MODEL,),
    ))
    decision = route_order_intents(
        portfolio,
        _snapshot(portfolio),
        {"alpha": (_order(quantity="600"), _order(quantity="100", tag="order-2"))},
        {"US.AAPL": _economics()},
        event_time=EVENT_TIME,
        event_sequence=10,
    )

    assert decision.kind is OrderRoutingDecisionKind.RISK_REJECTED
    assert not decision.risk_limits_satisfied
    assert decision.risk_approved_orders == ()
    assert decision.proposed_orders
    assert decision.gross_exposure_fraction == Decimal("0.70")


def test_short_order_fails_closed_when_short_positions_are_disabled() -> None:
    portfolio = _portfolio()
    decision = route_order_intents(
        portfolio,
        _snapshot(portfolio),
        {"alpha": (_order(OrderSide.SELL, quantity="1"),)},
        {"US.AAPL": _economics()},
        event_time=EVENT_TIME,
        event_sequence=10,
    )

    assert decision.risk_breaches == (RiskBreach.SHORT_POSITION,)
    assert decision.risk_approved_orders == ()


def test_quantity_and_price_tick_rules_are_checked_before_risk_evaluation() -> None:
    portfolio = _portfolio()
    with pytest.raises(ValueError, match="quantity_step"):
        route_order_intents(
            portfolio,
            _snapshot(portfolio),
            {"alpha": (_order(quantity="1.001"),)},
            {"US.AAPL": _economics()},
            event_time=EVENT_TIME,
            event_sequence=10,
        )
    with pytest.raises(ValueError, match="price_tick"):
        route_order_intents(
            portfolio,
            _snapshot(portfolio),
            {
                "alpha": (
                    _order(
                        order_type=OrderType.LIMIT,
                        limit_price="100.001",
                    ),
                )
            },
            {"US.AAPL": _economics()},
            event_time=EVENT_TIME,
            event_sequence=10,
        )


def test_unsupported_product_model_is_rejected_even_with_a_digest() -> None:
    portfolio = _portfolio()
    option_model = ProductRiskModel(
        ProductClass.OPTION,
        RiskExposureMeasure.SIGNED_BASE_NOTIONAL,
        content_digest("option-model"),
    )
    with pytest.raises(ValueError, match="unsupported order risk model"):
        route_order_intents(
            portfolio,
            _snapshot(portfolio),
            {"alpha": (_order(),)},
            {"US.AAPL": _economics(risk_model=option_model)},
            event_time=EVENT_TIME,
            event_sequence=10,
        )


def test_registered_option_model_can_route_delta_adjusted_exposure() -> None:
    portfolio = _portfolio(
        SharedRiskPolicy(risk_models=(OPTION_DELTA_NOTIONAL_RISK_MODEL,))
    )
    decision = route_order_intents(
        portfolio,
        _snapshot(portfolio, risk_model=OPTION_DELTA_NOTIONAL_RISK_MODEL),
        {"alpha": (_order(OrderSide.SELL, quantity="1"),)},
        {
            "US.AAPL": _economics(
                risk_model=OPTION_DELTA_NOTIONAL_RISK_MODEL,
                mark_price=Decimal("4"),
                contract_multiplier=Decimal("100"),
                underlying_mark_price=Decimal("50"),
                option_delta=Decimal("-0.4"),
            )
        },
        event_time=EVENT_TIME,
        event_sequence=10,
    )

    assert decision.risk_limits_satisfied
    assert decision.proposed_orders[0].estimated_signed_base_notional == Decimal("2000.0")


def test_duplicate_order_identity_and_missing_economics_fail_closed() -> None:
    portfolio = _portfolio()
    duplicate = _order()
    with pytest.raises(ValueError, match="duplicate order intent"):
        route_order_intents(
            portfolio,
            _snapshot(portfolio),
            {"alpha": (duplicate, duplicate)},
            {"US.AAPL": _economics()},
            event_time=EVENT_TIME,
            event_sequence=10,
        )
    with pytest.raises(ValueError, match="no order economics"):
        route_order_intents(
            portfolio,
            _snapshot(portfolio),
            {"alpha": (_order(),)},
            {},
            event_time=EVENT_TIME,
            event_sequence=10,
        )
    mismatched = InstrumentOrderEconomics(
        instrument_id="US.MSFT",
        risk_model=CASH_EQUITY_NOTIONAL_RISK_MODEL,
        mark_price=Decimal("100"),
        contract_multiplier=Decimal("1"),
        quantity_step=Decimal("0.01"),
        minimum_quantity=Decimal("0.01"),
        quote_currency="USD",
        base_currency="USD",
        quote_to_base_rate=Decimal("1"),
        valuation_evidence_digest=VALUATION_DIGEST,
    )
    with pytest.raises(ValueError, match="economics identity"):
        route_order_intents(
            portfolio,
            _snapshot(portfolio),
            {"alpha": (_order(),)},
            {"US.AAPL": mismatched},
            event_time=EVENT_TIME,
            event_sequence=10,
        )


def test_routing_requires_matching_event_and_is_independent_of_decimal_context() -> None:
    portfolio = _portfolio()
    order = _order(quantity="0.33")
    baseline = route_order_intents(
        portfolio,
        _snapshot(portfolio),
        {"alpha": (order,)},
        {"US.AAPL": _economics()},
        event_time=EVENT_TIME,
        event_sequence=10,
    )
    with localcontext() as decimal_context:
        decimal_context.prec = 6
        decimal_context.rounding = ROUND_DOWN
        constrained = route_order_intents(
            portfolio,
            _snapshot(portfolio),
            {"alpha": (order,)},
            {"US.AAPL": _economics()},
            event_time=EVENT_TIME,
            event_sequence=10,
        )
    assert constrained == baseline
    with pytest.raises(ValueError, match="match the exposure snapshot event"):
        route_order_intents(
            portfolio,
            _snapshot(portfolio),
            {"alpha": (_order(),)},
            {"US.AAPL": _economics()},
            event_time=EVENT_TIME,
            event_sequence=11,
        )
