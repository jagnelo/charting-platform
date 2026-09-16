from __future__ import annotations

from datetime import datetime, timedelta
from decimal import ROUND_DOWN, Decimal, localcontext

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.liquidity_risk import LiquidityRiskPolicy, apply_liquidity_risk_gate
from app.strategy_lab_v2.settlement_risk import (
    CurrencySettlementCapacity,
    SettlementBreach,
    SettlementCapacitySnapshot,
    SettlementOrderEstimate,
    SettlementRiskDecisionKind,
    SettlementRiskPolicy,
    apply_settlement_risk_gate,
)
from app.strategy_lab_v2.tests.test_liquidity_risk import _gated_stress, _liquidity


def _settlement(liquidity_decision, **kwargs):
    order = liquidity_decision.proposed_orders[0]
    values = {
        "portfolio_fingerprint": liquidity_decision.portfolio_fingerprint,
        "exposure_snapshot_fingerprint": liquidity_decision.exposure_snapshot_fingerprint,
        "event_time": liquidity_decision.event_time,
        "event_sequence": liquidity_decision.event_sequence,
        "base_currency": "USD",
        "capacities": (
            CurrencySettlementCapacity(
                "USD",
                Decimal("100000"),
                content_digest("settlement-cash"),
            ),
        ),
        "order_estimates": (
            SettlementOrderEstimate(
                order.fingerprint,
                "USD",
                Decimal("-1000"),
                liquidity_decision.event_time + timedelta(days=2),
                content_digest("settlement-order"),
            ),
        ),
    }
    values.update(kwargs)
    return SettlementCapacitySnapshot(**values)


def _gated_liquidity():
    routing, stress = _gated_stress()
    liquidity = apply_liquidity_risk_gate(
        stress,
        _liquidity(stress),
        LiquidityRiskPolicy(
            max_quantity_participation=Decimal("0.1"),
            max_notional_participation=Decimal("0.1"),
            max_estimated_slippage_bps=Decimal("10"),
        ),
    )
    return routing, liquidity


def test_settlement_gate_approves_with_explicit_cash_evidence() -> None:
    routing, liquidity = _gated_liquidity()
    decision = apply_settlement_risk_gate(
        liquidity,
        _settlement(liquidity),
        SettlementRiskPolicy(minimum_remaining_cash=Decimal("98000")),
    )

    assert decision.kind is SettlementRiskDecisionKind.APPROVED
    assert decision.risk_limits_satisfied
    assert decision.risk_approved_orders == routing.proposed_orders
    assert decision.max_gross_settlement_debit == Decimal("1000")


def test_settlement_gate_withholds_for_gross_debit_and_cash_buffer() -> None:
    _, liquidity = _gated_liquidity()
    decision = apply_settlement_risk_gate(
        liquidity,
        _settlement(
            liquidity,
            capacities=(
                CurrencySettlementCapacity(
                    "USD", Decimal("500"), content_digest("settlement-cash-low")
                ),
            ),
        ),
        SettlementRiskPolicy(minimum_remaining_cash=Decimal("1000")),
    )

    assert decision.kind is SettlementRiskDecisionKind.RISK_REJECTED
    assert decision.risk_approved_orders == ()
    assert decision.settlement_breaches == (
        SettlementBreach.SETTLEMENT_DEBIT,
        SettlementBreach.MINIMUM_REMAINING_CASH,
    )


def test_settlement_gate_requires_every_order_estimate_and_currency_capacity() -> None:
    _, liquidity = _gated_liquidity()
    missing_estimate = apply_settlement_risk_gate(
        liquidity,
        _settlement(liquidity, order_estimates=()),
        SettlementRiskPolicy(),
    )
    assert missing_estimate.settlement_breaches == (SettlementBreach.MISSING_ORDER_ESTIMATE,)

    order = liquidity.proposed_orders[0]
    missing_capacity = apply_settlement_risk_gate(
        liquidity,
        _settlement(
            liquidity,
            capacities=(),
            order_estimates=(
                SettlementOrderEstimate(
                    order.fingerprint,
                    "USD",
                    Decimal("-1"),
                    liquidity.event_time + timedelta(days=2),
                    content_digest("settlement-order-missing-capacity"),
                ),
            ),
        ),
        SettlementRiskPolicy(),
    )
    assert missing_capacity.settlement_breaches == (SettlementBreach.MISSING_CAPACITY,)


def test_upstream_liquidity_rejection_is_preserved() -> None:
    _, stress = _gated_stress()
    rejected_liquidity = apply_liquidity_risk_gate(
        stress,
        _liquidity(stress, capacities=()),
        LiquidityRiskPolicy(),
    )
    decision = apply_settlement_risk_gate(
        rejected_liquidity,
        _settlement(rejected_liquidity),
        SettlementRiskPolicy(),
    )

    assert not decision.upstream_risk_limits_satisfied
    assert not decision.risk_limits_satisfied
    assert decision.settlement_breaches == ()


def test_settlement_gate_validates_identity_and_strict_inputs() -> None:
    _, liquidity = _gated_liquidity()
    with pytest.raises(ValueError, match="event sequence"):
        apply_settlement_risk_gate(
            liquidity,
            _settlement(liquidity, event_sequence=9),
            SettlementRiskPolicy(),
        )
    with pytest.raises(ValueError, match="available_cash"):
        CurrencySettlementCapacity("USD", Decimal("-1"), content_digest("cash"))
    with pytest.raises(ValueError, match="settlement_time"):
        SettlementOrderEstimate(
            liquidity.proposed_orders[0].fingerprint,
            "USD",
            Decimal("-1"),
            datetime(2026, 1, 1),
            content_digest("estimate"),
        )


def test_settlement_math_is_independent_of_decimal_context() -> None:
    _, liquidity = _gated_liquidity()
    policy = SettlementRiskPolicy()
    baseline = apply_settlement_risk_gate(liquidity, _settlement(liquidity), policy)
    with localcontext() as decimal_context:
        decimal_context.prec = 6
        decimal_context.rounding = ROUND_DOWN
        constrained = apply_settlement_risk_gate(liquidity, _settlement(liquidity), policy)
    assert constrained == baseline
