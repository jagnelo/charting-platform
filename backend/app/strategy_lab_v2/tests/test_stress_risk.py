from __future__ import annotations

from decimal import ROUND_DOWN, Decimal, localcontext

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.margin_risk import MarginRiskPolicy, apply_margin_risk_gate
from app.strategy_lab_v2.stress_risk import (
    StressBreach,
    StressRiskDecisionKind,
    StressRiskPolicy,
    StressScenarioObservation,
    StressScenarioSnapshot,
    apply_stress_risk_gate,
)
from app.strategy_lab_v2.tests.test_margin_risk import _margin, _routing


def _stress(
    margin_decision,
    *,
    portfolio_fingerprint: str | None = None,
    observations: tuple[StressScenarioObservation, ...] | None = None,
) -> StressScenarioSnapshot:
    default_observations = (
            StressScenarioObservation(
                "base-case",
                content_digest("shock-base"),
                Decimal("100000"),
                Decimal("95000"),
                content_digest("stress-values-base"),
            ),
            StressScenarioObservation(
                "downside",
                content_digest("shock-downside"),
                Decimal("100000"),
                Decimal("90000"),
                content_digest("stress-values-downside"),
            ),
        )
    return StressScenarioSnapshot(
        portfolio_fingerprint or margin_decision.portfolio_fingerprint,
        margin_decision.exposure_snapshot_fingerprint,
        margin_decision.event_time,
        margin_decision.event_sequence,
        "USD",
        observations or default_observations,
    )


def _gated_margin():
    _, routing = _routing()
    return routing, apply_margin_risk_gate(routing, _margin(routing), MarginRiskPolicy())


def test_stress_gate_approves_complete_scenarios_within_explicit_limits() -> None:
    routing, margin = _gated_margin()
    decision = apply_stress_risk_gate(
        margin,
        _stress(margin),
        StressRiskPolicy(max_loss_fraction=Decimal("0.20"), minimum_stressed_equity=Decimal("80000")),
    )

    assert decision.kind is StressRiskDecisionKind.APPROVED
    assert decision.risk_limits_satisfied
    assert decision.upstream_risk_limits_satisfied
    assert decision.scenario_count == 2
    assert decision.worst_loss_fraction == Decimal("0.1")
    assert decision.worst_stressed_equity == Decimal("90000")
    assert decision.risk_approved_orders == routing.proposed_orders


def test_stress_gate_withholds_all_orders_for_loss_or_equity_breaches() -> None:
    _, margin = _gated_margin()
    decision = apply_stress_risk_gate(
        margin,
        _stress(margin),
        StressRiskPolicy(max_loss_fraction=Decimal("0.05"), minimum_stressed_equity=Decimal("95000")),
    )

    assert decision.kind is StressRiskDecisionKind.RISK_REJECTED
    assert decision.risk_approved_orders == ()
    assert decision.stress_breaches == (
        StressBreach.LOSS_FRACTION,
        StressBreach.MINIMUM_EQUITY,
    )


def test_upstream_margin_rejection_is_preserved_without_fabricating_stress_breaches() -> None:
    from app.strategy_lab_v2.contracts import CASH_EQUITY_NOTIONAL_RISK_MODEL, SharedRiskPolicy

    _, routing = _routing(
        SharedRiskPolicy(
            max_gross_exposure_fraction=Decimal("0.001"),
            risk_models=(CASH_EQUITY_NOTIONAL_RISK_MODEL,),
        )
    )
    rejected_margin = apply_margin_risk_gate(
        routing,
        _margin(routing),
        MarginRiskPolicy(),
    )
    decision = apply_stress_risk_gate(rejected_margin, _stress(rejected_margin), StressRiskPolicy())

    assert not decision.upstream_risk_limits_satisfied
    assert not decision.risk_limits_satisfied
    assert decision.stress_breaches == ()
    assert decision.risk_approved_orders == ()


def test_stress_snapshot_requires_exact_identity_and_unique_scenarios() -> None:
    _, margin = _gated_margin()
    with pytest.raises(ValueError, match="does not belong to the margin portfolio"):
        apply_stress_risk_gate(
            margin,
            _stress(margin, portfolio_fingerprint=content_digest("other")),
            StressRiskPolicy(),
        )
    duplicate = StressScenarioObservation(
        "base-case",
        content_digest("shock-other"),
        Decimal("100000"),
        Decimal("99000"),
        content_digest("stress-other"),
    )
    with pytest.raises(ValueError, match="scenario ids must be unique"):
        _stress(margin, observations=(duplicate, duplicate))


def test_stress_inputs_are_strict_and_math_is_context_independent() -> None:
    _, margin = _gated_margin()
    policy = StressRiskPolicy(max_loss_fraction=Decimal("0.20"))
    baseline = apply_stress_risk_gate(margin, _stress(margin), policy)
    with localcontext() as decimal_context:
        decimal_context.prec = 6
        decimal_context.rounding = ROUND_DOWN
        constrained = apply_stress_risk_gate(margin, _stress(margin), policy)
    assert constrained == baseline
    with pytest.raises(ValueError, match="stressed_equity"):
        StressScenarioObservation(
            "bad",
            content_digest("shock"),
            Decimal("100"),
            Decimal("NaN"),
            content_digest("values"),
        )
    with pytest.raises(ValueError, match="max_loss_fraction"):
        StressRiskPolicy(max_loss_fraction=Decimal("-0.1"))
