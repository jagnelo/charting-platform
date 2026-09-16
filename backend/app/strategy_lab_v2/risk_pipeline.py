"""Composition of the ordered, all-or-nothing trade-risk gates.

The pipeline is deliberately engine-neutral: routing sizes candidate orders,
then margin, stress, liquidity, and settlement gates consume adapter-supplied
evidence in that order.  The final receipt verifies the fingerprint chain and
exposes no submission or fill capability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.liquidity_risk import (
    LiquidityCapacitySnapshot,
    LiquidityRiskDecision,
    LiquidityRiskPolicy,
    apply_liquidity_risk_gate,
)
from app.strategy_lab_v2.margin_risk import (
    MarginCapacitySnapshot,
    MarginRiskDecision,
    MarginRiskPolicy,
    apply_margin_risk_gate,
)
from app.strategy_lab_v2.order_routing import OrderRoutingDecision, RoutedOrder
from app.strategy_lab_v2.settlement_risk import (
    SettlementCapacitySnapshot,
    SettlementRiskDecision,
    SettlementRiskPolicy,
    apply_settlement_risk_gate,
)
from app.strategy_lab_v2.stress_risk import (
    StressRiskDecision,
    StressRiskPolicy,
    StressScenarioSnapshot,
    apply_stress_risk_gate,
)


@dataclass(frozen=True, slots=True)
class TradeRiskAdmission:
    """Immutable receipt for the complete pre-engine risk-gate chain."""

    routing_decision: OrderRoutingDecision
    margin_decision: MarginRiskDecision
    stress_decision: StressRiskDecision
    liquidity_decision: LiquidityRiskDecision
    settlement_decision: SettlementRiskDecision
    event_time: datetime
    event_sequence: int
    risk_limits_satisfied: bool
    risk_approved_orders: tuple[RoutedOrder, ...]

    def __post_init__(self) -> None:
        for name, expected_type in (
            ("routing_decision", OrderRoutingDecision),
            ("margin_decision", MarginRiskDecision),
            ("stress_decision", StressRiskDecision),
            ("liquidity_decision", LiquidityRiskDecision),
            ("settlement_decision", SettlementRiskDecision),
        ):
            if not isinstance(getattr(self, name), expected_type):
                raise TypeError(f"{name} must be a {expected_type.__name__}")
        if self.margin_decision.routing_fingerprint != self.routing_decision.fingerprint:
            raise ValueError("margin decision is not chained to the routing decision")
        if self.stress_decision.margin_risk_fingerprint != self.margin_decision.fingerprint:
            raise ValueError("stress decision is not chained to the margin decision")
        if self.liquidity_decision.stress_risk_fingerprint != self.stress_decision.fingerprint:
            raise ValueError("liquidity decision is not chained to the stress decision")
        if self.settlement_decision.liquidity_risk_fingerprint != self.liquidity_decision.fingerprint:
            raise ValueError("settlement decision is not chained to the liquidity decision")
        if self.event_time.tzinfo is None or self.event_time.utcoffset() is None:
            raise ValueError("event_time must be timezone-aware")
        if (
            not isinstance(self.event_sequence, int)
            or isinstance(self.event_sequence, bool)
            or self.event_sequence < 0
        ):
            raise ValueError("event_sequence must be a non-negative integer")
        decision_events = (
            (self.routing_decision.event_time, self.routing_decision.event_sequence),
            (self.margin_decision.event_time, self.margin_decision.event_sequence),
            (self.stress_decision.event_time, self.stress_decision.event_sequence),
            (self.liquidity_decision.event_time, self.liquidity_decision.event_sequence),
            (self.settlement_decision.event_time, self.settlement_decision.event_sequence),
        )
        for decision_time, decision_sequence in decision_events:
            if decision_time != self.event_time:
                raise ValueError("all risk decisions must share the pipeline event time")
            if decision_sequence != self.event_sequence:
                raise ValueError("all risk decisions must share the pipeline event sequence")
        if not isinstance(self.risk_limits_satisfied, bool):
            raise TypeError("risk_limits_satisfied must be a bool")
        approved = tuple(self.risk_approved_orders)
        if any(not isinstance(item, RoutedOrder) for item in approved):
            raise TypeError("risk_approved_orders must contain RoutedOrder values")
        if approved != self.settlement_decision.risk_approved_orders:
            raise ValueError("pipeline approval must match settlement approval")
        if self.risk_limits_satisfied != self.settlement_decision.risk_limits_satisfied:
            raise ValueError("pipeline approval must match settlement risk limits")
        if self.risk_limits_satisfied and approved != self.routing_decision.proposed_orders:
            raise ValueError("approved pipeline must expose every routed order")
        if not self.risk_limits_satisfied and approved:
            raise ValueError("rejected pipeline must expose no approved orders")
        object.__setattr__(self, "event_time", self.event_time.astimezone(UTC))
        object.__setattr__(self, "risk_approved_orders", approved)

    @property
    def routing_fingerprint(self) -> str:
        return self.routing_decision.fingerprint

    @property
    def settlement_risk_fingerprint(self) -> str:
        return self.settlement_decision.fingerprint

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def evaluate_trade_risk(
    routing_decision: OrderRoutingDecision,
    margin_snapshot: MarginCapacitySnapshot,
    margin_policy: MarginRiskPolicy,
    stress_snapshot: StressScenarioSnapshot,
    stress_policy: StressRiskPolicy,
    liquidity_snapshot: LiquidityCapacitySnapshot,
    liquidity_policy: LiquidityRiskPolicy,
    settlement_snapshot: SettlementCapacitySnapshot,
    settlement_policy: SettlementRiskPolicy,
) -> TradeRiskAdmission:
    """Evaluate every pre-engine risk gate in its fixed order."""

    if not isinstance(routing_decision, OrderRoutingDecision):
        raise TypeError("routing_decision must be an OrderRoutingDecision")
    margin_decision = apply_margin_risk_gate(routing_decision, margin_snapshot, margin_policy)
    stress_decision = apply_stress_risk_gate(margin_decision, stress_snapshot, stress_policy)
    liquidity_decision = apply_liquidity_risk_gate(
        stress_decision,
        liquidity_snapshot,
        liquidity_policy,
    )
    settlement_decision = apply_settlement_risk_gate(
        liquidity_decision,
        settlement_snapshot,
        settlement_policy,
    )
    return TradeRiskAdmission(
        routing_decision=routing_decision,
        margin_decision=margin_decision,
        stress_decision=stress_decision,
        liquidity_decision=liquidity_decision,
        settlement_decision=settlement_decision,
        event_time=settlement_decision.event_time,
        event_sequence=settlement_decision.event_sequence,
        risk_limits_satisfied=settlement_decision.risk_limits_satisfied,
        risk_approved_orders=settlement_decision.risk_approved_orders,
    )
