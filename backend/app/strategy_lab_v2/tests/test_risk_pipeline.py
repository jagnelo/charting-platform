from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from app.strategy_lab_v2.liquidity_risk import LiquidityRiskPolicy, apply_liquidity_risk_gate
from app.strategy_lab_v2.margin_risk import MarginRiskPolicy, apply_margin_risk_gate
from app.strategy_lab_v2.risk_pipeline import TradeRiskAdmission, evaluate_trade_risk
from app.strategy_lab_v2.settlement_risk import SettlementRiskPolicy, apply_settlement_risk_gate
from app.strategy_lab_v2.stress_risk import StressRiskPolicy, apply_stress_risk_gate
from app.strategy_lab_v2.tests.test_liquidity_risk import _liquidity
from app.strategy_lab_v2.tests.test_margin_risk import _margin, _routing
from app.strategy_lab_v2.tests.test_settlement_risk import _settlement
from app.strategy_lab_v2.tests.test_stress_risk import _stress


def _pipeline_inputs():
    _, routing = _routing()
    margin_snapshot = _margin(routing)
    margin = apply_margin_risk_gate(routing, margin_snapshot, MarginRiskPolicy())
    stress_snapshot = _stress(margin)
    stress = apply_stress_risk_gate(margin, stress_snapshot, StressRiskPolicy())
    liquidity_snapshot = _liquidity(stress)
    liquidity = apply_liquidity_risk_gate(stress, liquidity_snapshot, LiquidityRiskPolicy())
    settlement_snapshot = _settlement(liquidity)
    return (
        routing,
        margin_snapshot,
        stress_snapshot,
        liquidity_snapshot,
        settlement_snapshot,
    )


def test_trade_risk_pipeline_evaluates_every_gate_in_order() -> None:
    routing, margin, stress, liquidity, settlement = _pipeline_inputs()
    admission = evaluate_trade_risk(
        routing,
        margin,
        MarginRiskPolicy(),
        stress,
        StressRiskPolicy(max_loss_fraction=Decimal("0.2")),
        liquidity,
        LiquidityRiskPolicy(
            max_quantity_participation=Decimal("0.1"),
            max_notional_participation=Decimal("0.1"),
            max_estimated_slippage_bps=Decimal("10"),
        ),
        settlement,
        SettlementRiskPolicy(),
    )

    assert isinstance(admission, TradeRiskAdmission)
    assert admission.risk_limits_satisfied
    assert admission.risk_approved_orders == routing.proposed_orders
    assert admission.routing_fingerprint == routing.fingerprint
    assert admission.settlement_risk_fingerprint == admission.settlement_decision.fingerprint


def test_trade_risk_pipeline_preserves_the_first_failed_gate() -> None:
    routing, margin, stress, liquidity, settlement = _pipeline_inputs()
    admission = evaluate_trade_risk(
        routing,
        margin,
        MarginRiskPolicy(max_initial_utilization=Decimal("0.5")),
        stress,
        StressRiskPolicy(max_loss_fraction=Decimal("0.2")),
        liquidity,
        LiquidityRiskPolicy(),
        settlement,
        SettlementRiskPolicy(),
    )

    assert not admission.risk_limits_satisfied
    assert admission.margin_decision.margin_breaches
    assert admission.risk_approved_orders == ()


def test_trade_risk_pipeline_can_reject_at_settlement_without_partial_approval() -> None:
    routing, margin, stress, liquidity, settlement = _pipeline_inputs()
    low_cash = replace(
        settlement,
        capacities=tuple(
            replace(capacity, available_cash=Decimal("500"))
            for capacity in settlement.capacities
        ),
    )
    admission = evaluate_trade_risk(
        routing,
        margin,
        MarginRiskPolicy(),
        stress,
        StressRiskPolicy(max_loss_fraction=Decimal("0.2")),
        liquidity,
        LiquidityRiskPolicy(),
        low_cash,
        SettlementRiskPolicy(),
    )

    assert not admission.risk_limits_satisfied
    assert admission.settlement_decision.settlement_breaches
    assert admission.risk_approved_orders == ()


def test_trade_risk_pipeline_rejects_broken_decision_chain() -> None:
    routing, margin_snapshot, stress_snapshot, liquidity_snapshot, settlement_snapshot = (
        _pipeline_inputs()
    )
    margin = apply_margin_risk_gate(routing, margin_snapshot, MarginRiskPolicy())
    stress = apply_stress_risk_gate(margin, stress_snapshot, StressRiskPolicy())
    liquidity = apply_liquidity_risk_gate(stress, liquidity_snapshot, LiquidityRiskPolicy())
    settlement = apply_settlement_risk_gate(
        liquidity,
        settlement_snapshot,
        SettlementRiskPolicy(),
    )
    with pytest.raises(ValueError, match="chained"):
        TradeRiskAdmission(
            routing,
            replace(margin, event_sequence=11),
            stress,
            liquidity,
            settlement,
            routing.event_time,
            routing.event_sequence,
            settlement.risk_limits_satisfied,
            settlement.risk_approved_orders,
        )
