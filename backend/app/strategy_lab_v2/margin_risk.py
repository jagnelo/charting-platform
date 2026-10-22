"""Engine-neutral margin-capacity gate for routed order candidates.

The native engine or an instrument/account adapter owns margin calculation. It
must provide the complete, event-aligned requirements and capacities here. The
package only verifies identity, computes transparent utilization ratios, and
withholds a candidate batch when the supplied capacities or policy thresholds
are exceeded. It never infers margin from notional exposure and never issues a
solvency or profitability verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.decimal_math import DECIMAL_PRECISION, deterministic_decimal_math
from app.strategy_lab_v2.order_routing import (
    OrderRoutingDecision,
    RoutedOrder,
)

MARGIN_RISK_DEFINITION_VERSION = (
    f"strategy-lab.margin-risk.v1.decimal{DECIMAL_PRECISION}-half-even"
)


def _positive(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError(f"{field_name} must be a finite positive Decimal")


def _nonnegative(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError(f"{field_name} must be a finite non-negative Decimal")


def _currency(value: str, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 3
        or not value.isascii()
        or not value.isalpha()
    ):
        raise ValueError(f"{field_name} must be a three-letter currency code")
    return value.upper()


@dataclass(frozen=True, slots=True)
class MarginCapacitySnapshot:
    """Adapter-reported requirements and capacities at one event boundary."""

    portfolio_fingerprint: str
    exposure_snapshot_fingerprint: str
    event_time: datetime
    event_sequence: int
    base_currency: str
    initial_requirement: Decimal
    maintenance_requirement: Decimal
    initial_capacity: Decimal
    maintenance_capacity: Decimal
    valuation_evidence_digest: str

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
        object.__setattr__(self, "event_time", self.event_time.astimezone(UTC))
        object.__setattr__(self, "base_currency", _currency(self.base_currency, "base_currency"))
        for name in ("initial_requirement", "maintenance_requirement"):
            _nonnegative(getattr(self, name), name)
        for name in ("initial_capacity", "maintenance_capacity"):
            _positive(getattr(self, name), name)
        require_sha256_digest(
            self.valuation_evidence_digest,
            field_name="valuation_evidence_digest",
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class MarginRiskPolicy:
    """Explicit utilization ceilings for one account model."""

    max_initial_utilization: Decimal = Decimal("1")
    max_maintenance_utilization: Decimal = Decimal("1")
    definition_version: str = "strategy-lab.margin-policy.v1"

    def __post_init__(self) -> None:
        _positive(self.max_initial_utilization, "max_initial_utilization")
        _positive(self.max_maintenance_utilization, "max_maintenance_utilization")
        if not isinstance(self.definition_version, str) or not self.definition_version.strip():
            raise ValueError("definition_version must not be empty")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class MarginBreach(StrEnum):
    INITIAL_CAPACITY = "initial_capacity"
    MAINTENANCE_CAPACITY = "maintenance_capacity"
    INITIAL_UTILIZATION = "initial_utilization"
    MAINTENANCE_UTILIZATION = "maintenance_utilization"


class MarginRiskDecisionKind(StrEnum):
    APPROVED = "approved"
    RISK_REJECTED = "risk_rejected"


@dataclass(frozen=True, slots=True)
class MarginRiskDecision:
    """A margin gate layered on one immutable order-routing decision."""

    definition_version: str
    routing_fingerprint: str
    portfolio_fingerprint: str
    exposure_snapshot_fingerprint: str
    margin_snapshot_fingerprint: str
    policy_fingerprint: str
    event_time: datetime
    event_sequence: int
    kind: MarginRiskDecisionKind
    upstream_risk_limits_satisfied: bool
    risk_limits_satisfied: bool
    proposed_orders: tuple[RoutedOrder, ...]
    risk_approved_orders: tuple[RoutedOrder, ...]
    margin_breaches: tuple[MarginBreach, ...]
    initial_utilization: Decimal
    maintenance_utilization: Decimal

    def __post_init__(self) -> None:
        for name in (
            "routing_fingerprint",
            "portfolio_fingerprint",
            "exposure_snapshot_fingerprint",
            "margin_snapshot_fingerprint",
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
        if not isinstance(self.kind, MarginRiskDecisionKind):
            raise TypeError("kind must be a MarginRiskDecisionKind")
        if not isinstance(self.upstream_risk_limits_satisfied, bool):
            raise TypeError("upstream_risk_limits_satisfied must be a bool")
        if not isinstance(self.risk_limits_satisfied, bool):
            raise TypeError("risk_limits_satisfied must be a bool")
        if self.risk_limits_satisfied != (
            self.kind is MarginRiskDecisionKind.APPROVED
        ):
            raise ValueError("decision kind must match risk_limits_satisfied")
        if self.risk_limits_satisfied and not self.upstream_risk_limits_satisfied:
            raise ValueError("margin approval requires upstream order risk approval")
        proposed = tuple(self.proposed_orders)
        approved = tuple(self.risk_approved_orders)
        if any(not isinstance(item, RoutedOrder) for item in (*proposed, *approved)):
            raise TypeError("orders must contain RoutedOrder values")
        if not set(approved).issubset(set(proposed)):
            raise ValueError("approved orders must be a subset of proposed orders")
        if self.risk_limits_satisfied and approved != proposed:
            raise ValueError("an approved margin decision must expose every proposed order")
        if not self.risk_limits_satisfied and approved:
            raise ValueError("a risk-rejected margin decision must expose no approved orders")
        _nonnegative(self.initial_utilization, "initial_utilization")
        _nonnegative(self.maintenance_utilization, "maintenance_utilization")
        breaches = tuple(self.margin_breaches)
        if any(not isinstance(item, MarginBreach) for item in breaches):
            raise TypeError("margin_breaches must contain MarginBreach values")
        if self.upstream_risk_limits_satisfied and not breaches and not self.risk_limits_satisfied:
            raise ValueError("a rejected margin decision must identify a margin breach")
        object.__setattr__(self, "event_time", self.event_time.astimezone(UTC))
        object.__setattr__(self, "proposed_orders", proposed)
        object.__setattr__(self, "risk_approved_orders", approved)
        object.__setattr__(self, "margin_breaches", breaches)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@deterministic_decimal_math
def apply_margin_risk_gate(
    routing_decision: OrderRoutingDecision,
    margin_snapshot: MarginCapacitySnapshot,
    policy: MarginRiskPolicy,
) -> MarginRiskDecision:
    """Withhold routed orders when adapter-supplied margin capacity is exceeded."""

    if routing_decision.portfolio_fingerprint != margin_snapshot.portfolio_fingerprint:
        raise ValueError("margin snapshot does not belong to the routing portfolio")
    if routing_decision.exposure_snapshot_fingerprint != margin_snapshot.exposure_snapshot_fingerprint:
        raise ValueError("margin snapshot does not belong to the routing exposure snapshot")
    if routing_decision.event_time != margin_snapshot.event_time:
        raise ValueError("margin snapshot event time does not match the routing decision")
    if routing_decision.event_sequence != margin_snapshot.event_sequence:
        raise ValueError("margin snapshot event sequence does not match the routing decision")
    if not isinstance(policy, MarginRiskPolicy):
        raise TypeError("policy must be a MarginRiskPolicy")

    initial_utilization = (
        margin_snapshot.initial_requirement / margin_snapshot.initial_capacity
    )
    maintenance_utilization = (
        margin_snapshot.maintenance_requirement / margin_snapshot.maintenance_capacity
    )
    breaches: list[MarginBreach] = []
    if margin_snapshot.initial_requirement > margin_snapshot.initial_capacity:
        breaches.append(MarginBreach.INITIAL_CAPACITY)
    if margin_snapshot.maintenance_requirement > margin_snapshot.maintenance_capacity:
        breaches.append(MarginBreach.MAINTENANCE_CAPACITY)
    if initial_utilization > policy.max_initial_utilization:
        breaches.append(MarginBreach.INITIAL_UTILIZATION)
    if maintenance_utilization > policy.max_maintenance_utilization:
        breaches.append(MarginBreach.MAINTENANCE_UTILIZATION)

    upstream_ok = routing_decision.risk_limits_satisfied
    risk_ok = upstream_ok and not breaches
    return MarginRiskDecision(
        definition_version=MARGIN_RISK_DEFINITION_VERSION,
        routing_fingerprint=routing_decision.fingerprint,
        portfolio_fingerprint=routing_decision.portfolio_fingerprint,
        exposure_snapshot_fingerprint=routing_decision.exposure_snapshot_fingerprint,
        margin_snapshot_fingerprint=margin_snapshot.fingerprint,
        policy_fingerprint=policy.fingerprint,
        event_time=routing_decision.event_time,
        event_sequence=routing_decision.event_sequence,
        kind=(
            MarginRiskDecisionKind.APPROVED
            if risk_ok
            else MarginRiskDecisionKind.RISK_REJECTED
        ),
        upstream_risk_limits_satisfied=upstream_ok,
        risk_limits_satisfied=risk_ok,
        proposed_orders=routing_decision.proposed_orders,
        risk_approved_orders=routing_decision.proposed_orders if risk_ok else (),
        margin_breaches=tuple(breaches),
        initial_utilization=initial_utilization,
        maintenance_utilization=maintenance_utilization,
    )
