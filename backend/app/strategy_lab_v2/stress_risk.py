"""Adapter-supplied stress-scenario gate for routed order candidates.

The engine/account adapter constructs stressed equity observations from explicit
shock definitions. This module verifies their identity and applies a caller's
loss/equity ceilings; it never invents shocks, rewrites engine observations, or
issues a solvency, liquidity, or profitability verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.decimal_math import DECIMAL_PRECISION, deterministic_decimal_math
from app.strategy_lab_v2.margin_risk import MarginRiskDecision
from app.strategy_lab_v2.order_routing import RoutedOrder

STRESS_RISK_DEFINITION_VERSION = (
    f"strategy-lab.stress-risk.v1.decimal{DECIMAL_PRECISION}-half-even"
)


def _finite(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{field_name} must be a finite Decimal")


def _positive(value: Decimal, field_name: str) -> None:
    _finite(value, field_name)
    if value <= 0:
        raise ValueError(f"{field_name} must be a finite positive Decimal")


@dataclass(frozen=True, slots=True)
class StressScenarioObservation:
    """One adapter-generated stressed-equity result for a named shock."""

    scenario_id: str
    shock_definition_digest: str
    base_equity: Decimal
    stressed_equity: Decimal
    valuation_evidence_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_id, str) or not self.scenario_id.strip():
            raise ValueError("scenario_id must not be empty")
        require_sha256_digest(self.shock_definition_digest, field_name="shock_definition_digest")
        require_sha256_digest(
            self.valuation_evidence_digest,
            field_name="valuation_evidence_digest",
        )
        _positive(self.base_equity, "base_equity")
        _finite(self.stressed_equity, "stressed_equity")

    @property
    def loss_fraction(self) -> Decimal:
        return (self.base_equity - self.stressed_equity) / self.base_equity

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class StressScenarioSnapshot:
    """Complete scenario observations at one portfolio/event boundary."""

    portfolio_fingerprint: str
    exposure_snapshot_fingerprint: str
    event_time: datetime
    event_sequence: int
    base_currency: str
    observations: tuple[StressScenarioObservation, ...]

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
        observations = tuple(self.observations)
        if not observations:
            raise ValueError("stress scenario snapshots require at least one observation")
        if any(not isinstance(item, StressScenarioObservation) for item in observations):
            raise TypeError("observations must contain StressScenarioObservation values")
        scenario_ids = [item.scenario_id for item in observations]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("stress scenario ids must be unique")
        object.__setattr__(self, "event_time", self.event_time.astimezone(UTC))
        object.__setattr__(self, "base_currency", self.base_currency.upper())
        object.__setattr__(
            self,
            "observations",
            tuple(sorted(observations, key=lambda item: item.scenario_id)),
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class StressRiskPolicy:
    """Explicit ceilings over adapter-reported stressed outcomes."""

    max_loss_fraction: Decimal = Decimal("1")
    minimum_stressed_equity: Decimal | None = None
    definition_version: str = "strategy-lab.stress-policy.v1"

    def __post_init__(self) -> None:
        _finite(self.max_loss_fraction, "max_loss_fraction")
        if self.max_loss_fraction < 0:
            raise ValueError("max_loss_fraction must be non-negative")
        if self.minimum_stressed_equity is not None:
            _finite(self.minimum_stressed_equity, "minimum_stressed_equity")
        if not isinstance(self.definition_version, str) or not self.definition_version.strip():
            raise ValueError("definition_version must not be empty")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class StressBreach(StrEnum):
    LOSS_FRACTION = "loss_fraction"
    MINIMUM_EQUITY = "minimum_equity"


class StressRiskDecisionKind(StrEnum):
    APPROVED = "approved"
    RISK_REJECTED = "risk_rejected"


@dataclass(frozen=True, slots=True)
class StressRiskDecision:
    """Stress gate result layered on the margin/routing decisions."""

    definition_version: str
    routing_fingerprint: str
    margin_risk_fingerprint: str
    portfolio_fingerprint: str
    exposure_snapshot_fingerprint: str
    stress_snapshot_fingerprint: str
    policy_fingerprint: str
    event_time: datetime
    event_sequence: int
    kind: StressRiskDecisionKind
    upstream_risk_limits_satisfied: bool
    risk_limits_satisfied: bool
    proposed_orders: tuple[RoutedOrder, ...]
    risk_approved_orders: tuple[RoutedOrder, ...]
    stress_breaches: tuple[StressBreach, ...]
    scenario_count: int
    worst_loss_fraction: Decimal
    worst_stressed_equity: Decimal

    def __post_init__(self) -> None:
        for name in (
            "routing_fingerprint",
            "margin_risk_fingerprint",
            "portfolio_fingerprint",
            "exposure_snapshot_fingerprint",
            "stress_snapshot_fingerprint",
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
        if not isinstance(self.kind, StressRiskDecisionKind):
            raise TypeError("kind must be a StressRiskDecisionKind")
        if not isinstance(self.upstream_risk_limits_satisfied, bool):
            raise TypeError("upstream_risk_limits_satisfied must be a bool")
        if not isinstance(self.risk_limits_satisfied, bool):
            raise TypeError("risk_limits_satisfied must be a bool")
        if self.risk_limits_satisfied != (
            self.kind is StressRiskDecisionKind.APPROVED
        ):
            raise ValueError("decision kind must match risk_limits_satisfied")
        if self.risk_limits_satisfied and not self.upstream_risk_limits_satisfied:
            raise ValueError("stress approval requires upstream risk approval")
        proposed = tuple(self.proposed_orders)
        approved = tuple(self.risk_approved_orders)
        if any(not isinstance(item, RoutedOrder) for item in (*proposed, *approved)):
            raise TypeError("orders must contain RoutedOrder values")
        if not set(approved).issubset(set(proposed)):
            raise ValueError("approved orders must be a subset of proposed orders")
        if self.risk_limits_satisfied and approved != proposed:
            raise ValueError("an approved stress decision must expose every proposed order")
        if not self.risk_limits_satisfied and approved:
            raise ValueError("a risk-rejected stress decision must expose no approved orders")
        if (
            not isinstance(self.scenario_count, int)
            or isinstance(self.scenario_count, bool)
            or self.scenario_count < 1
        ):
            raise ValueError("scenario_count must be positive")
        _finite(self.worst_loss_fraction, "worst_loss_fraction")
        _finite(self.worst_stressed_equity, "worst_stressed_equity")
        breaches = tuple(self.stress_breaches)
        if any(not isinstance(item, StressBreach) for item in breaches):
            raise TypeError("stress_breaches must contain StressBreach values")
        if self.upstream_risk_limits_satisfied and not breaches and not self.risk_limits_satisfied:
            raise ValueError("a rejected stress decision must identify a stress breach")
        object.__setattr__(self, "event_time", self.event_time.astimezone(UTC))
        object.__setattr__(self, "proposed_orders", proposed)
        object.__setattr__(self, "risk_approved_orders", approved)
        object.__setattr__(self, "stress_breaches", breaches)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@deterministic_decimal_math
def apply_stress_risk_gate(
    margin_decision: MarginRiskDecision,
    stress_snapshot: StressScenarioSnapshot,
    policy: StressRiskPolicy,
) -> StressRiskDecision:
    """Withhold routed orders when any explicit stress ceiling is exceeded."""

    if margin_decision.portfolio_fingerprint != stress_snapshot.portfolio_fingerprint:
        raise ValueError("stress snapshot does not belong to the margin portfolio")
    if margin_decision.exposure_snapshot_fingerprint != stress_snapshot.exposure_snapshot_fingerprint:
        raise ValueError("stress snapshot does not belong to the margin exposure snapshot")
    if margin_decision.event_time != stress_snapshot.event_time:
        raise ValueError("stress snapshot event time does not match the margin decision")
    if margin_decision.event_sequence != stress_snapshot.event_sequence:
        raise ValueError("stress snapshot event sequence does not match the margin decision")
    if not isinstance(policy, StressRiskPolicy):
        raise TypeError("policy must be a StressRiskPolicy")

    observations = stress_snapshot.observations
    worst_loss = max((item.loss_fraction for item in observations), default=Decimal(0))
    worst_equity = min((item.stressed_equity for item in observations), default=Decimal(0))
    breaches: list[StressBreach] = []
    if any(item.loss_fraction > policy.max_loss_fraction for item in observations):
        breaches.append(StressBreach.LOSS_FRACTION)
    if policy.minimum_stressed_equity is not None and any(
        item.stressed_equity < policy.minimum_stressed_equity for item in observations
    ):
        breaches.append(StressBreach.MINIMUM_EQUITY)

    upstream_ok = margin_decision.risk_limits_satisfied
    risk_ok = upstream_ok and not breaches
    return StressRiskDecision(
        definition_version=STRESS_RISK_DEFINITION_VERSION,
        routing_fingerprint=margin_decision.routing_fingerprint,
        margin_risk_fingerprint=margin_decision.fingerprint,
        portfolio_fingerprint=margin_decision.portfolio_fingerprint,
        exposure_snapshot_fingerprint=margin_decision.exposure_snapshot_fingerprint,
        stress_snapshot_fingerprint=stress_snapshot.fingerprint,
        policy_fingerprint=policy.fingerprint,
        event_time=margin_decision.event_time,
        event_sequence=margin_decision.event_sequence,
        kind=(StressRiskDecisionKind.APPROVED if risk_ok else StressRiskDecisionKind.RISK_REJECTED),
        upstream_risk_limits_satisfied=upstream_ok,
        risk_limits_satisfied=risk_ok,
        proposed_orders=margin_decision.proposed_orders,
        risk_approved_orders=margin_decision.proposed_orders if risk_ok else (),
        stress_breaches=tuple(breaches),
        scenario_count=len(observations),
        worst_loss_fraction=worst_loss,
        worst_stressed_equity=worst_equity,
    )

