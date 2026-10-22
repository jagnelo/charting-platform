from __future__ import annotations

from decimal import ROUND_DOWN, Decimal, localcontext

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.liquidity_risk import (
    InstrumentLiquidityCapacity,
    LiquidityBreach,
    LiquidityCapacitySnapshot,
    LiquidityRiskDecisionKind,
    LiquidityRiskPolicy,
    apply_liquidity_risk_gate,
)
from app.strategy_lab_v2.margin_risk import MarginRiskPolicy, apply_margin_risk_gate
from app.strategy_lab_v2.stress_risk import (
    StressRiskPolicy,
    StressScenarioObservation,
    StressScenarioSnapshot,
    apply_stress_risk_gate,
)
from app.strategy_lab_v2.tests.test_margin_risk import _margin, _routing


def _liquidity(stress_decision, **kwargs):
    values = {
        "portfolio_fingerprint": stress_decision.portfolio_fingerprint,
        "exposure_snapshot_fingerprint": stress_decision.exposure_snapshot_fingerprint,
        "event_time": stress_decision.event_time,
        "event_sequence": stress_decision.event_sequence,
        "base_currency": "USD",
        "capacities": (
            InstrumentLiquidityCapacity(
                "US.AAPL",
                Decimal("1000"),
                Decimal("100000"),
                Decimal("5"),
                content_digest("liquidity-values"),
            ),
        ),
    }
    values.update(kwargs)
    return LiquidityCapacitySnapshot(**values)


def _gated_stress():
    _, routing = _routing()
    margin = apply_margin_risk_gate(routing, _margin(routing), MarginRiskPolicy())
    stress = StressScenarioSnapshot(
        margin.portfolio_fingerprint,
        margin.exposure_snapshot_fingerprint,
        margin.event_time,
        margin.event_sequence,
        "USD",
        (
            StressScenarioObservation(
                "base",
                content_digest("shock"),
                Decimal("100000"),
                Decimal("95000"),
                content_digest("stress"),
            ),
        ),
    )
    return routing, apply_stress_risk_gate(
        margin,
        stress,
        StressRiskPolicy(max_loss_fraction=Decimal("0.1")),
    )


def test_liquidity_gate_approves_when_capacity_and_slippage_limits_fit() -> None:
    routing, stress = _gated_stress()
    decision = apply_liquidity_risk_gate(
        stress,
        _liquidity(stress),
        LiquidityRiskPolicy(
            max_quantity_participation=Decimal("0.1"),
            max_notional_participation=Decimal("0.1"),
            max_estimated_slippage_bps=Decimal("10"),
        ),
    )

    assert decision.kind is LiquidityRiskDecisionKind.APPROVED
    assert decision.risk_limits_satisfied
    assert decision.risk_approved_orders == routing.proposed_orders
    assert decision.max_quantity_participation == Decimal("0.01")
    assert decision.max_notional_participation == Decimal("0.01")
    assert decision.max_estimated_slippage_bps == Decimal("5")


def test_liquidity_gate_withholds_all_orders_for_participation_or_slippage() -> None:
    _, stress = _gated_stress()
    decision = apply_liquidity_risk_gate(
        stress,
        _liquidity(
            stress,
            capacities=(
                InstrumentLiquidityCapacity(
                    "US.AAPL",
                    Decimal("10"),
                    Decimal("100"),
                    Decimal("20"),
                    content_digest("liquidity-values"),
                ),
            ),
        ),
        LiquidityRiskPolicy(
            max_quantity_participation=Decimal("0.5"),
            max_notional_participation=Decimal("0.5"),
            max_estimated_slippage_bps=Decimal("10"),
        ),
    )

    assert decision.kind is LiquidityRiskDecisionKind.RISK_REJECTED
    assert decision.risk_approved_orders == ()
    assert decision.liquidity_breaches == (
        LiquidityBreach.QUANTITY_PARTICIPATION,
        LiquidityBreach.NOTIONAL_PARTICIPATION,
        LiquidityBreach.ESTIMATED_SLIPPAGE,
    )


def test_missing_capacity_and_upstream_rejection_are_explicit() -> None:
    _, stress = _gated_stress()
    missing = apply_liquidity_risk_gate(
        stress,
        _liquidity(stress, capacities=()),
        LiquidityRiskPolicy(),
    )
    assert missing.liquidity_breaches == (LiquidityBreach.MISSING_CAPACITY,)
    _, rejected_routing = _routing()
    # The stress decision itself is rejected by a loss ceiling.
    margin = apply_margin_risk_gate(rejected_routing, _margin(rejected_routing), MarginRiskPolicy())
    rejected_stress = apply_stress_risk_gate(
        margin,
        StressScenarioSnapshot(
            margin.portfolio_fingerprint,
            margin.exposure_snapshot_fingerprint,
            margin.event_time,
            margin.event_sequence,
            "USD",
            (
                StressScenarioObservation(
                    "downside",
                    content_digest("shock-downside"),
                    Decimal("100000"),
                    Decimal("90000"),
                    content_digest("stress-downside"),
                ),
            ),
        ),
        StressRiskPolicy(max_loss_fraction=Decimal("0.05")),
    )
    upstream = apply_liquidity_risk_gate(
        rejected_stress,
        _liquidity(rejected_stress),
        LiquidityRiskPolicy(),
    )
    assert not upstream.upstream_risk_limits_satisfied
    assert not upstream.risk_limits_satisfied
    assert upstream.liquidity_breaches == ()


def test_liquidity_gate_requires_event_identity_and_strict_inputs() -> None:
    _, stress = _gated_stress()
    with pytest.raises(ValueError, match="event sequence"):
        apply_liquidity_risk_gate(
            stress,
            _liquidity(stress, event_sequence=11),
            LiquidityRiskPolicy(),
        )
    with pytest.raises(ValueError, match="available_quantity"):
        InstrumentLiquidityCapacity(
            "US.AAPL", Decimal("0"), Decimal("1"), Decimal("1"), content_digest("evidence")
        )
    with pytest.raises(ValueError, match="max_quantity_participation"):
        LiquidityRiskPolicy(max_quantity_participation=Decimal("0"))


def test_liquidity_math_is_independent_of_decimal_context() -> None:
    _, stress = _gated_stress()
    policy = LiquidityRiskPolicy()
    baseline = apply_liquidity_risk_gate(stress, _liquidity(stress), policy)
    with localcontext() as decimal_context:
        decimal_context.prec = 6
        decimal_context.rounding = ROUND_DOWN
        constrained = apply_liquidity_risk_gate(stress, _liquidity(stress), policy)
    assert constrained == baseline

