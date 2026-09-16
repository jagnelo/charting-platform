"""Adapter-supplied cash-settlement gate for liquidity-approved orders.

The account/venue adapter owns settlement timing, currency conversion, and
cash-availability semantics.  This module consumes explicit per-order cash
delta estimates and per-currency available-cash evidence, then withholds the
whole candidate batch when a settlement debit or remaining-cash policy is
violated.  It does not infer cash flows from product type, side, or notional.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.decimal_math import DECIMAL_PRECISION, deterministic_decimal_math
from app.strategy_lab_v2.liquidity_risk import LiquidityRiskDecision
from app.strategy_lab_v2.order_routing import RoutedOrder

SETTLEMENT_RISK_DEFINITION_VERSION = (
    f"strategy-lab.settlement-risk.v1.decimal{DECIMAL_PRECISION}-half-even"
)


def _finite(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{field_name} must be a finite Decimal")


def _nonnegative(value: Decimal, field_name: str) -> None:
    _finite(value, field_name)
    if value < 0:
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
class SettlementOrderEstimate:
    """Adapter-reported cash movement for one exact routed order.

    ``cash_delta`` is positive when settlement adds cash and negative when it
    consumes cash.  The adapter must account for product, currency, fees,
    settlement timing, and any conversion before constructing this value.
    """

    order_fingerprint: str
    currency: str
    cash_delta: Decimal
    settlement_time: datetime
    valuation_evidence_digest: str

    def __post_init__(self) -> None:
        require_sha256_digest(self.order_fingerprint, field_name="order_fingerprint")
        object.__setattr__(self, "currency", _currency(self.currency, "currency"))
        _finite(self.cash_delta, "cash_delta")
        if self.settlement_time.tzinfo is None or self.settlement_time.utcoffset() is None:
            raise ValueError("settlement_time must be timezone-aware")
        require_sha256_digest(
            self.valuation_evidence_digest,
            field_name="valuation_evidence_digest",
        )
        object.__setattr__(self, "settlement_time", self.settlement_time.astimezone(UTC))

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class CurrencySettlementCapacity:
    """Adapter-reported free cash at the settlement boundary for one currency."""

    currency: str
    available_cash: Decimal
    valuation_evidence_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", _currency(self.currency, "currency"))
        _nonnegative(self.available_cash, "available_cash")
        require_sha256_digest(
            self.valuation_evidence_digest,
            field_name="valuation_evidence_digest",
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class SettlementCapacitySnapshot:
    """Complete cash-settlement evidence for one liquidity-approved event."""

    portfolio_fingerprint: str
    exposure_snapshot_fingerprint: str
    event_time: datetime
    event_sequence: int
    base_currency: str
    capacities: tuple[CurrencySettlementCapacity, ...]
    order_estimates: tuple[SettlementOrderEstimate, ...]

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
        capacities = tuple(self.capacities)
        estimates = tuple(self.order_estimates)
        if any(not isinstance(item, CurrencySettlementCapacity) for item in capacities):
            raise TypeError("capacities must contain CurrencySettlementCapacity values")
        if any(not isinstance(item, SettlementOrderEstimate) for item in estimates):
            raise TypeError("order_estimates must contain SettlementOrderEstimate values")
        currencies = [item.currency for item in capacities]
        if len(currencies) != len(set(currencies)):
            raise ValueError("settlement capacities must be unique per currency")
        order_fingerprints = [item.order_fingerprint for item in estimates]
        if len(order_fingerprints) != len(set(order_fingerprints)):
            raise ValueError("settlement order estimates must be unique per order")
        object.__setattr__(
            self,
            "capacities",
            tuple(sorted(capacities, key=lambda item: item.currency)),
        )
        object.__setattr__(
            self,
            "order_estimates",
            tuple(sorted(estimates, key=lambda item: item.order_fingerprint)),
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class SettlementRiskPolicy:
    """Explicit minimum remaining cash after settlement debits and credits."""

    minimum_remaining_cash: Decimal = Decimal(0)
    definition_version: str = "strategy-lab.settlement-policy.v1"

    def __post_init__(self) -> None:
        _nonnegative(self.minimum_remaining_cash, "minimum_remaining_cash")
        if not isinstance(self.definition_version, str) or not self.definition_version.strip():
            raise ValueError("definition_version must not be empty")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class SettlementBreach(StrEnum):
    MISSING_CAPACITY = "missing_capacity"
    MISSING_ORDER_ESTIMATE = "missing_order_estimate"
    SETTLEMENT_DEBIT = "settlement_debit"
    MINIMUM_REMAINING_CASH = "minimum_remaining_cash"


class SettlementRiskDecisionKind(StrEnum):
    APPROVED = "approved"
    RISK_REJECTED = "risk_rejected"


@dataclass(frozen=True, slots=True)
class SettlementRiskDecision:
    """Settlement gate result layered on liquidity, stress, margin, and routing."""

    definition_version: str
    routing_fingerprint: str
    liquidity_risk_fingerprint: str
    portfolio_fingerprint: str
    exposure_snapshot_fingerprint: str
    settlement_snapshot_fingerprint: str
    policy_fingerprint: str
    event_time: datetime
    event_sequence: int
    kind: SettlementRiskDecisionKind
    upstream_risk_limits_satisfied: bool
    risk_limits_satisfied: bool
    proposed_orders: tuple[RoutedOrder, ...]
    risk_approved_orders: tuple[RoutedOrder, ...]
    settlement_breaches: tuple[SettlementBreach, ...]
    max_gross_settlement_debit: Decimal
    minimum_remaining_cash: Decimal

    def __post_init__(self) -> None:
        for name in (
            "routing_fingerprint",
            "liquidity_risk_fingerprint",
            "portfolio_fingerprint",
            "exposure_snapshot_fingerprint",
            "settlement_snapshot_fingerprint",
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
        if not isinstance(self.kind, SettlementRiskDecisionKind):
            raise TypeError("kind must be a SettlementRiskDecisionKind")
        if not isinstance(self.upstream_risk_limits_satisfied, bool):
            raise TypeError("upstream_risk_limits_satisfied must be a bool")
        if not isinstance(self.risk_limits_satisfied, bool):
            raise TypeError("risk_limits_satisfied must be a bool")
        if self.risk_limits_satisfied != (
            self.kind is SettlementRiskDecisionKind.APPROVED
        ):
            raise ValueError("decision kind must match risk_limits_satisfied")
        if self.risk_limits_satisfied and not self.upstream_risk_limits_satisfied:
            raise ValueError("settlement approval requires upstream risk approval")
        proposed = tuple(self.proposed_orders)
        approved = tuple(self.risk_approved_orders)
        if any(not isinstance(item, RoutedOrder) for item in (*proposed, *approved)):
            raise TypeError("orders must contain RoutedOrder values")
        if not set(approved).issubset(set(proposed)):
            raise ValueError("approved orders must be a subset of proposed orders")
        if self.risk_limits_satisfied and approved != proposed:
            raise ValueError("an approved settlement decision must expose every proposed order")
        if not self.risk_limits_satisfied and approved:
            raise ValueError("a risk-rejected settlement decision must expose no approved orders")
        _nonnegative(self.max_gross_settlement_debit, "max_gross_settlement_debit")
        _nonnegative(self.minimum_remaining_cash, "minimum_remaining_cash")
        breaches = tuple(self.settlement_breaches)
        if any(not isinstance(item, SettlementBreach) for item in breaches):
            raise TypeError("settlement_breaches must contain SettlementBreach values")
        if self.upstream_risk_limits_satisfied and not breaches and not self.risk_limits_satisfied:
            raise ValueError("a rejected settlement decision must identify a settlement breach")
        object.__setattr__(self, "event_time", self.event_time.astimezone(UTC))
        object.__setattr__(self, "proposed_orders", proposed)
        object.__setattr__(self, "risk_approved_orders", approved)
        object.__setattr__(self, "settlement_breaches", breaches)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@deterministic_decimal_math
def apply_settlement_risk_gate(
    liquidity_decision: LiquidityRiskDecision,
    settlement_snapshot: SettlementCapacitySnapshot,
    policy: SettlementRiskPolicy,
) -> SettlementRiskDecision:
    """Withhold orders when explicit settlement cash evidence is insufficient."""

    if liquidity_decision.portfolio_fingerprint != settlement_snapshot.portfolio_fingerprint:
        raise ValueError("settlement snapshot does not belong to the liquidity portfolio")
    if (
        liquidity_decision.exposure_snapshot_fingerprint
        != settlement_snapshot.exposure_snapshot_fingerprint
    ):
        raise ValueError("settlement snapshot does not belong to the liquidity exposure snapshot")
    if liquidity_decision.event_time != settlement_snapshot.event_time:
        raise ValueError("settlement snapshot event time does not match the liquidity decision")
    if liquidity_decision.event_sequence != settlement_snapshot.event_sequence:
        raise ValueError("settlement snapshot event sequence does not match the liquidity decision")
    if not isinstance(policy, SettlementRiskPolicy):
        raise TypeError("policy must be a SettlementRiskPolicy")

    capacities = {item.currency: item for item in settlement_snapshot.capacities}
    estimates = {item.order_fingerprint: item for item in settlement_snapshot.order_estimates}
    debits: dict[str, Decimal] = defaultdict(Decimal)
    deltas: dict[str, Decimal] = defaultdict(Decimal)
    breaches: list[SettlementBreach] = []
    for order in liquidity_decision.proposed_orders:
        estimate = estimates.get(order.fingerprint)
        if estimate is None:
            breaches.append(SettlementBreach.MISSING_ORDER_ESTIMATE)
            continue
        if estimate.currency not in capacities:
            breaches.append(SettlementBreach.MISSING_CAPACITY)
            continue
        deltas[estimate.currency] += estimate.cash_delta
        if estimate.cash_delta < 0:
            debits[estimate.currency] -= estimate.cash_delta

    max_gross_debit = Decimal(0)
    for currency in sorted(set(deltas) | set(debits)):
        capacity = capacities[currency]
        gross_debit = debits[currency]
        max_gross_debit = max(max_gross_debit, gross_debit)
        remaining_cash = capacity.available_cash + deltas[currency]
        if gross_debit > capacity.available_cash:
            breaches.append(SettlementBreach.SETTLEMENT_DEBIT)
        if remaining_cash < policy.minimum_remaining_cash:
            breaches.append(SettlementBreach.MINIMUM_REMAINING_CASH)

    upstream_ok = liquidity_decision.risk_limits_satisfied
    risk_ok = upstream_ok and not breaches
    return SettlementRiskDecision(
        definition_version=SETTLEMENT_RISK_DEFINITION_VERSION,
        routing_fingerprint=liquidity_decision.routing_fingerprint,
        liquidity_risk_fingerprint=liquidity_decision.fingerprint,
        portfolio_fingerprint=liquidity_decision.portfolio_fingerprint,
        exposure_snapshot_fingerprint=liquidity_decision.exposure_snapshot_fingerprint,
        settlement_snapshot_fingerprint=settlement_snapshot.fingerprint,
        policy_fingerprint=policy.fingerprint,
        event_time=liquidity_decision.event_time,
        event_sequence=liquidity_decision.event_sequence,
        kind=(
            SettlementRiskDecisionKind.APPROVED
            if risk_ok
            else SettlementRiskDecisionKind.RISK_REJECTED
        ),
        upstream_risk_limits_satisfied=upstream_ok,
        risk_limits_satisfied=risk_ok,
        proposed_orders=liquidity_decision.proposed_orders,
        risk_approved_orders=liquidity_decision.proposed_orders if risk_ok else (),
        settlement_breaches=tuple(dict.fromkeys(breaches)),
        max_gross_settlement_debit=max_gross_debit,
        minimum_remaining_cash=policy.minimum_remaining_cash,
    )
