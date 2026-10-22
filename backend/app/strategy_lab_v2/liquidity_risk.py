"""Adapter-supplied liquidity and participation gate for routed orders.

The market-data/engine adapter owns the venue- and product-specific liquidity
measurement. This module consumes explicit available quantity/notional and
slippage estimates, aggregates the candidate batch by instrument, and withholds
the batch when policy participation limits are exceeded. It does not infer
volume, construct fills, or promise execution quality.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.decimal_math import DECIMAL_PRECISION, deterministic_decimal_math
from app.strategy_lab_v2.order_routing import RoutedOrder
from app.strategy_lab_v2.stress_risk import StressRiskDecision

LIQUIDITY_RISK_DEFINITION_VERSION = (
    f"strategy-lab.liquidity-risk.v1.decimal{DECIMAL_PRECISION}-half-even"
)


def _finite(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{field_name} must be a finite Decimal")


def _positive(value: Decimal, field_name: str) -> None:
    _finite(value, field_name)
    if value <= 0:
        raise ValueError(f"{field_name} must be a finite positive Decimal")


def _nonnegative(value: Decimal, field_name: str) -> None:
    _finite(value, field_name)
    if value < 0:
        raise ValueError(f"{field_name} must be a finite non-negative Decimal")


@dataclass(frozen=True, slots=True)
class InstrumentLiquidityCapacity:
    """Adapter-reported capacity for one instrument at one event boundary."""

    instrument_id: str
    available_quantity: Decimal
    available_base_notional: Decimal
    estimated_slippage_bps: Decimal
    valuation_evidence_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_id, str) or not self.instrument_id.strip():
            raise ValueError("instrument_id must not be empty")
        _positive(self.available_quantity, "available_quantity")
        _positive(self.available_base_notional, "available_base_notional")
        _nonnegative(self.estimated_slippage_bps, "estimated_slippage_bps")
        require_sha256_digest(
            self.valuation_evidence_digest,
            field_name="valuation_evidence_digest",
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class LiquidityCapacitySnapshot:
    """Complete capacity evidence for a routed order event."""

    portfolio_fingerprint: str
    exposure_snapshot_fingerprint: str
    event_time: datetime
    event_sequence: int
    base_currency: str
    capacities: tuple[InstrumentLiquidityCapacity, ...]

    def __post_init__(self) -> None:
        require_sha256_digest(self.portfolio_fingerprint, field_name="portfolio_fingerprint")
        require_sha256_digest(
            self.exposure_snapshot_fingerprint,
            field_name="exposure_snapshot_fingerprint",
        )
        if self.event_time.tzinfo is None or self.event_time.utcoffset() is None:
            raise ValueError("event_time must be timezone-aware")
        if (
            not isinstance(self.event_sequence, int)
            or isinstance(self.event_sequence, bool)
            or self.event_sequence < 0
        ):
            raise ValueError("event_sequence must be a non-negative integer")
        if (
            not isinstance(self.base_currency, str)
            or len(self.base_currency) != 3
            or not self.base_currency.isascii()
            or not self.base_currency.isalpha()
        ):
            raise ValueError("base_currency must be a three-letter currency code")
        capacities = tuple(self.capacities)
        if any(not isinstance(item, InstrumentLiquidityCapacity) for item in capacities):
            raise TypeError("capacities must contain InstrumentLiquidityCapacity values")
        instrument_ids = [item.instrument_id for item in capacities]
        if len(instrument_ids) != len(set(instrument_ids)):
            raise ValueError("liquidity capacities must be unique per instrument")
        object.__setattr__(self, "event_time", self.event_time.astimezone(UTC))
        object.__setattr__(self, "base_currency", self.base_currency.upper())
        object.__setattr__(
            self,
            "capacities",
            tuple(sorted(capacities, key=lambda item: item.instrument_id)),
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class LiquidityRiskPolicy:
    """Explicit per-batch participation and slippage ceilings."""

    max_quantity_participation: Decimal = Decimal("1")
    max_notional_participation: Decimal = Decimal("1")
    max_estimated_slippage_bps: Decimal = Decimal("100")
    definition_version: str = "strategy-lab.liquidity-policy.v1"

    def __post_init__(self) -> None:
        _positive(self.max_quantity_participation, "max_quantity_participation")
        _positive(self.max_notional_participation, "max_notional_participation")
        _nonnegative(self.max_estimated_slippage_bps, "max_estimated_slippage_bps")
        if not isinstance(self.definition_version, str) or not self.definition_version.strip():
            raise ValueError("definition_version must not be empty")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class LiquidityBreach(StrEnum):
    MISSING_CAPACITY = "missing_capacity"
    QUANTITY_PARTICIPATION = "quantity_participation"
    NOTIONAL_PARTICIPATION = "notional_participation"
    ESTIMATED_SLIPPAGE = "estimated_slippage"


class LiquidityRiskDecisionKind(StrEnum):
    APPROVED = "approved"
    RISK_REJECTED = "risk_rejected"


@dataclass(frozen=True, slots=True)
class LiquidityRiskDecision:
    """Liquidity gate result layered on stress, margin, and routing decisions."""

    definition_version: str
    routing_fingerprint: str
    stress_risk_fingerprint: str
    portfolio_fingerprint: str
    exposure_snapshot_fingerprint: str
    liquidity_snapshot_fingerprint: str
    policy_fingerprint: str
    event_time: datetime
    event_sequence: int
    kind: LiquidityRiskDecisionKind
    upstream_risk_limits_satisfied: bool
    risk_limits_satisfied: bool
    proposed_orders: tuple[RoutedOrder, ...]
    risk_approved_orders: tuple[RoutedOrder, ...]
    liquidity_breaches: tuple[LiquidityBreach, ...]
    max_quantity_participation: Decimal
    max_notional_participation: Decimal
    max_estimated_slippage_bps: Decimal

    def __post_init__(self) -> None:
        for name in (
            "routing_fingerprint",
            "stress_risk_fingerprint",
            "portfolio_fingerprint",
            "exposure_snapshot_fingerprint",
            "liquidity_snapshot_fingerprint",
            "policy_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        if self.event_time.tzinfo is None or self.event_time.utcoffset() is None:
            raise ValueError("event_time must be timezone-aware")
        if (
            not isinstance(self.event_sequence, int)
            or isinstance(self.event_sequence, bool)
            or self.event_sequence < 0
        ):
            raise ValueError("event_sequence must be a non-negative integer")
        if not isinstance(self.kind, LiquidityRiskDecisionKind):
            raise TypeError("kind must be a LiquidityRiskDecisionKind")
        if not isinstance(self.upstream_risk_limits_satisfied, bool):
            raise TypeError("upstream_risk_limits_satisfied must be a bool")
        if not isinstance(self.risk_limits_satisfied, bool):
            raise TypeError("risk_limits_satisfied must be a bool")
        if self.risk_limits_satisfied != (
            self.kind is LiquidityRiskDecisionKind.APPROVED
        ):
            raise ValueError("decision kind must match risk_limits_satisfied")
        if self.risk_limits_satisfied and not self.upstream_risk_limits_satisfied:
            raise ValueError("liquidity approval requires upstream risk approval")
        proposed = tuple(self.proposed_orders)
        approved = tuple(self.risk_approved_orders)
        if any(not isinstance(item, RoutedOrder) for item in (*proposed, *approved)):
            raise TypeError("orders must contain RoutedOrder values")
        if not set(approved).issubset(set(proposed)):
            raise ValueError("approved orders must be a subset of proposed orders")
        if self.risk_limits_satisfied and approved != proposed:
            raise ValueError("an approved liquidity decision must expose every proposed order")
        if not self.risk_limits_satisfied and approved:
            raise ValueError("a risk-rejected liquidity decision must expose no approved orders")
        _nonnegative(self.max_quantity_participation, "max_quantity_participation")
        _nonnegative(self.max_notional_participation, "max_notional_participation")
        _nonnegative(self.max_estimated_slippage_bps, "max_estimated_slippage_bps")
        breaches = tuple(self.liquidity_breaches)
        if any(not isinstance(item, LiquidityBreach) for item in breaches):
            raise TypeError("liquidity_breaches must contain LiquidityBreach values")
        if self.upstream_risk_limits_satisfied and not breaches and not self.risk_limits_satisfied:
            raise ValueError("a rejected liquidity decision must identify a liquidity breach")
        object.__setattr__(self, "event_time", self.event_time.astimezone(UTC))
        object.__setattr__(self, "proposed_orders", proposed)
        object.__setattr__(self, "risk_approved_orders", approved)
        object.__setattr__(self, "liquidity_breaches", breaches)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@deterministic_decimal_math
def apply_liquidity_risk_gate(
    stress_decision: StressRiskDecision,
    liquidity_snapshot: LiquidityCapacitySnapshot,
    policy: LiquidityRiskPolicy,
) -> LiquidityRiskDecision:
    """Withhold routed orders when adapter-supplied liquidity limits are exceeded."""

    if stress_decision.portfolio_fingerprint != liquidity_snapshot.portfolio_fingerprint:
        raise ValueError("liquidity snapshot does not belong to the stress portfolio")
    if stress_decision.exposure_snapshot_fingerprint != liquidity_snapshot.exposure_snapshot_fingerprint:
        raise ValueError("liquidity snapshot does not belong to the stress exposure snapshot")
    if stress_decision.event_time != liquidity_snapshot.event_time:
        raise ValueError("liquidity snapshot event time does not match the stress decision")
    if stress_decision.event_sequence != liquidity_snapshot.event_sequence:
        raise ValueError("liquidity snapshot event sequence does not match the stress decision")
    if not isinstance(policy, LiquidityRiskPolicy):
        raise TypeError("policy must be a LiquidityRiskPolicy")

    capacities = {item.instrument_id: item for item in liquidity_snapshot.capacities}
    quantities: dict[str, Decimal] = defaultdict(Decimal)
    notionals: dict[str, Decimal] = defaultdict(Decimal)
    for order in stress_decision.proposed_orders:
        quantities[order.instrument_id] += order.quantity
        notionals[order.instrument_id] += abs(order.estimated_signed_base_notional)

    breaches: list[LiquidityBreach] = []
    quantity_participations: list[Decimal] = []
    notional_participations: list[Decimal] = []
    slippages: list[Decimal] = []
    for instrument_id in sorted(set(quantities)):
        capacity = capacities.get(instrument_id)
        if capacity is None:
            breaches.append(LiquidityBreach.MISSING_CAPACITY)
            continue
        quantity_participation = quantities[instrument_id] / capacity.available_quantity
        notional_participation = notionals[instrument_id] / capacity.available_base_notional
        quantity_participations.append(quantity_participation)
        notional_participations.append(notional_participation)
        slippages.append(capacity.estimated_slippage_bps)
        if quantity_participation > policy.max_quantity_participation:
            breaches.append(LiquidityBreach.QUANTITY_PARTICIPATION)
        if notional_participation > policy.max_notional_participation:
            breaches.append(LiquidityBreach.NOTIONAL_PARTICIPATION)
        if capacity.estimated_slippage_bps > policy.max_estimated_slippage_bps:
            breaches.append(LiquidityBreach.ESTIMATED_SLIPPAGE)

    upstream_ok = stress_decision.risk_limits_satisfied
    risk_ok = upstream_ok and not breaches
    return LiquidityRiskDecision(
        definition_version=LIQUIDITY_RISK_DEFINITION_VERSION,
        routing_fingerprint=stress_decision.routing_fingerprint,
        stress_risk_fingerprint=stress_decision.fingerprint,
        portfolio_fingerprint=stress_decision.portfolio_fingerprint,
        exposure_snapshot_fingerprint=stress_decision.exposure_snapshot_fingerprint,
        liquidity_snapshot_fingerprint=liquidity_snapshot.fingerprint,
        policy_fingerprint=policy.fingerprint,
        event_time=stress_decision.event_time,
        event_sequence=stress_decision.event_sequence,
        kind=(
            LiquidityRiskDecisionKind.APPROVED
            if risk_ok
            else LiquidityRiskDecisionKind.RISK_REJECTED
        ),
        upstream_risk_limits_satisfied=upstream_ok,
        risk_limits_satisfied=risk_ok,
        proposed_orders=stress_decision.proposed_orders,
        risk_approved_orders=stress_decision.proposed_orders if risk_ok else (),
        liquidity_breaches=tuple(dict.fromkeys(breaches)),
        max_quantity_participation=max(quantity_participations, default=Decimal(0)),
        max_notional_participation=max(notional_participations, default=Decimal(0)),
        max_estimated_slippage_bps=max(slippages, default=Decimal(0)),
    )

