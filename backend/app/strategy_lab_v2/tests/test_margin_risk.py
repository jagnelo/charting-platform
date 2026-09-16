from __future__ import annotations

from decimal import ROUND_DOWN, Decimal, localcontext

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import CASH_EQUITY_NOTIONAL_RISK_MODEL, SharedRiskPolicy
from app.strategy_lab_v2.margin_risk import (
    MarginBreach,
    MarginCapacitySnapshot,
    MarginRiskDecisionKind,
    MarginRiskPolicy,
    apply_margin_risk_gate,
)
from app.strategy_lab_v2.order_routing import route_order_intents
from app.strategy_lab_v2.tests.test_order_routing import (
    EVENT_TIME,
    _economics,
    _order,
    _portfolio,
    _snapshot,
)


def _routing(policy: SharedRiskPolicy | None = None):
    portfolio = _portfolio(policy)
    return portfolio, route_order_intents(
        portfolio,
        _snapshot(portfolio),
        {"alpha": (_order(quantity="10"),)},
        {"US.AAPL": _economics()},
        event_time=EVENT_TIME,
        event_sequence=10,
    )


def _margin(
    routing,
    *,
    portfolio_fingerprint: str | None = None,
    event_sequence: int = 10,
    initial_requirement: Decimal = Decimal("30000"),
    maintenance_requirement: Decimal = Decimal("20000"),
    initial_capacity: Decimal = Decimal("50000"),
    maintenance_capacity: Decimal = Decimal("40000"),
) -> MarginCapacitySnapshot:
    return MarginCapacitySnapshot(
        portfolio_fingerprint or routing.portfolio_fingerprint,
        routing.exposure_snapshot_fingerprint,
        EVENT_TIME,
        event_sequence,
        "USD",
        initial_requirement,
        maintenance_requirement,
        initial_capacity,
        maintenance_capacity,
        content_digest("margin-evidence-v1"),
    )


def test_margin_gate_approves_when_requirements_fit_capacity_and_policy() -> None:
    _, routing = _routing()
    decision = apply_margin_risk_gate(routing, _margin(routing), MarginRiskPolicy())

    assert decision.kind is MarginRiskDecisionKind.APPROVED
    assert decision.risk_limits_satisfied
    assert decision.upstream_risk_limits_satisfied
    assert decision.initial_utilization == Decimal("0.6")
    assert decision.maintenance_utilization == Decimal("0.5")
    assert decision.risk_approved_orders == routing.proposed_orders
    assert decision.margin_breaches == ()


def test_margin_gate_withholds_all_orders_for_capacity_or_policy_breaches() -> None:
    _, routing = _routing()
    margin = _margin(
        routing,
        initial_requirement=Decimal("60000"),
        maintenance_requirement=Decimal("45000"),
        initial_capacity=Decimal("50000"),
        maintenance_capacity=Decimal("40000"),
    )
    decision = apply_margin_risk_gate(
        routing,
        margin,
        MarginRiskPolicy(
            max_initial_utilization=Decimal("0.9"),
            max_maintenance_utilization=Decimal("0.9"),
        ),
    )

    assert decision.kind is MarginRiskDecisionKind.RISK_REJECTED
    assert not decision.risk_limits_satisfied
    assert decision.risk_approved_orders == ()
    assert decision.margin_breaches == (
        MarginBreach.INITIAL_CAPACITY,
        MarginBreach.MAINTENANCE_CAPACITY,
        MarginBreach.INITIAL_UTILIZATION,
        MarginBreach.MAINTENANCE_UTILIZATION,
    )


def test_upstream_order_risk_rejection_is_preserved_without_fabricating_margin_breaches() -> None:
    portfolio, routing = _routing(
        SharedRiskPolicy(
            max_gross_exposure_fraction=Decimal("0.001"),
            risk_models=(CASH_EQUITY_NOTIONAL_RISK_MODEL,),
        )
    )
    assert not routing.risk_limits_satisfied
    decision = apply_margin_risk_gate(routing, _margin(routing), MarginRiskPolicy())

    assert decision.kind is MarginRiskDecisionKind.RISK_REJECTED
    assert not decision.upstream_risk_limits_satisfied
    assert decision.margin_breaches == ()
    assert decision.risk_approved_orders == ()
    assert decision.portfolio_fingerprint == portfolio.fingerprint


def test_margin_gate_requires_exact_snapshot_identity_and_event_alignment() -> None:
    _, routing = _routing()
    with pytest.raises(ValueError, match="does not belong to the routing portfolio"):
        apply_margin_risk_gate(
            routing,
            _margin(routing, portfolio_fingerprint=content_digest("other-portfolio")),
            MarginRiskPolicy(),
        )
    with pytest.raises(ValueError, match="event sequence"):
        apply_margin_risk_gate(
            routing,
            _margin(routing, event_sequence=11),
            MarginRiskPolicy(),
        )


def test_margin_inputs_are_strict_and_math_is_context_independent() -> None:
    _, routing = _routing()
    baseline = apply_margin_risk_gate(routing, _margin(routing), MarginRiskPolicy())
    with localcontext() as decimal_context:
        decimal_context.prec = 6
        decimal_context.rounding = ROUND_DOWN
        constrained = apply_margin_risk_gate(routing, _margin(routing), MarginRiskPolicy())
    assert constrained == baseline
    with pytest.raises(ValueError, match="initial_capacity"):
        MarginCapacitySnapshot(
            routing.portfolio_fingerprint,
            routing.exposure_snapshot_fingerprint,
            EVENT_TIME,
            10,
            "USD",
            Decimal("1"),
            Decimal("1"),
            Decimal("0"),
            Decimal("1"),
            content_digest("evidence"),
        )
    with pytest.raises(ValueError, match="max_initial_utilization"):
        MarginRiskPolicy(max_initial_utilization=Decimal("0"))
