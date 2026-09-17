"""Apply calendar rebalance boundaries to the engine-neutral allocator.

``rebalance.py`` plans immutable calendar occurrences while ``allocation.py``
resolves target positions at one event.  This module is the narrow composition
boundary between them: target intents are allocated only at the exact UTC
instant represented by a scheduled occurrence.  A later event never silently
"catches up" a missed rebalance; the occurrence's declared misfire policy
classifies that case explicitly.

The module does not create orders, fills, or calendar data.  Engine adapters
remain responsible for mapping their event tape to the scheduled boundary and
for executing any risk-approved targets.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.strategy_lab_v2.allocation import (
    AllocationDecision,
    PortfolioExposureSnapshot,
    allocate_component_targets,
    component_targets_from_intents,
)
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import PortfolioComposition
from app.strategy_lab_v2.rebalance import (
    RebalanceMisfirePolicy,
    ScheduledRebalance,
)
from app.strategy_lab_v2.sdk import StrategyIntent

REBALANCE_ALLOCATION_DEFINITION_VERSION = "strategy-lab.rebalance-allocation.v1"


class RebalanceApplicationKind(StrEnum):
    """Classification of a scheduled occurrence against an event snapshot."""

    APPLIED = "applied"
    NOT_DUE = "not_due"
    MISFIRED = "misfired"
    SKIPPED = "skipped"


class RebalanceApplicationReason(StrEnum):
    EXACT_BOUNDARY = "exact_boundary"
    BEFORE_BOUNDARY = "before_boundary"
    AFTER_BOUNDARY_FAIL_RUN = "after_boundary_fail_run"
    AFTER_BOUNDARY_SKIP_OCCURRENCE = "after_boundary_skip_occurrence"


@dataclass(frozen=True, slots=True)
class RebalanceAllocationDecision:
    """Immutable schedule gate result and, only when due, allocation decision."""

    definition_version: str
    portfolio_fingerprint: str
    exposure_snapshot_fingerprint: str
    occurrence_id: str
    event_time: datetime
    event_sequence: int
    kind: RebalanceApplicationKind
    reason: RebalanceApplicationReason
    request_count: int
    allocation: AllocationDecision | None = None

    def __post_init__(self) -> None:
        if self.definition_version != REBALANCE_ALLOCATION_DEFINITION_VERSION:
            raise ValueError("unsupported rebalance-allocation definition version")
        require_sha256_digest(self.portfolio_fingerprint, field_name="portfolio_fingerprint")
        require_sha256_digest(
            self.exposure_snapshot_fingerprint,
            field_name="exposure_snapshot_fingerprint",
        )
        require_sha256_digest(self.occurrence_id, field_name="occurrence_id")
        if self.event_time.tzinfo is None or self.event_time.utcoffset() is None:
            raise ValueError("event_time must be timezone-aware")
        object.__setattr__(self, "event_time", self.event_time.astimezone(UTC))
        if (
            not isinstance(self.event_sequence, int)
            or isinstance(self.event_sequence, bool)
            or self.event_sequence < 0
        ):
            raise ValueError("event_sequence must be a non-negative integer")
        if not isinstance(self.kind, RebalanceApplicationKind):
            raise TypeError("kind must be a RebalanceApplicationKind")
        if not isinstance(self.reason, RebalanceApplicationReason):
            raise TypeError("reason must be a RebalanceApplicationReason")
        if (
            not isinstance(self.request_count, int)
            or isinstance(self.request_count, bool)
            or self.request_count < 0
        ):
            raise ValueError("request_count must be a non-negative integer")
        if self.kind is RebalanceApplicationKind.APPLIED:
            if self.reason is not RebalanceApplicationReason.EXACT_BOUNDARY:
                raise ValueError("applied rebalances must use the exact-boundary reason")
            if not isinstance(self.allocation, AllocationDecision):
                raise TypeError("applied rebalances require an AllocationDecision")
            if (
                self.allocation.portfolio_fingerprint != self.portfolio_fingerprint
                or self.allocation.exposure_snapshot_fingerprint
                != self.exposure_snapshot_fingerprint
                or self.allocation.event_time != self.event_time
                or self.allocation.event_sequence != self.event_sequence
            ):
                raise ValueError("allocation identity does not match the rebalance event")
        elif self.allocation is not None:
            raise ValueError("non-applied rebalances must not include an allocation")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def apply_scheduled_rebalance(
    portfolio: PortfolioComposition,
    exposure_snapshot: PortfolioExposureSnapshot,
    scheduled: ScheduledRebalance,
    intents_by_component: Mapping[str, Iterable[StrategyIntent]],
) -> RebalanceAllocationDecision:
    """Gate target allocation on one exact scheduled occurrence.

    The snapshot is the adapter's event-aligned account state.  Before the
    boundary, intents are withheld as ``NOT_DUE``.  If the event tape advances
    past the boundary, ``FAIL_RUN`` yields ``MISFIRED`` and ``SKIP_OCCURRENCE``
    yields ``SKIPPED``.  Neither policy catches up by allocating at a later
    event.  At the exact boundary, typed intents are normalized and passed to
    the existing all-or-nothing allocation/risk implementation.
    """

    if not isinstance(portfolio, PortfolioComposition):
        raise TypeError("portfolio must be a PortfolioComposition")
    if not isinstance(exposure_snapshot, PortfolioExposureSnapshot):
        raise TypeError("exposure_snapshot must be a PortfolioExposureSnapshot")
    if not isinstance(scheduled, ScheduledRebalance):
        raise TypeError("scheduled must be a ScheduledRebalance")
    policy = portfolio.rebalance_policy
    if policy is None:
        raise ValueError("portfolio has no calendar rebalance policy")
    if scheduled.policy_fingerprint != policy.fingerprint:
        raise ValueError("scheduled rebalance policy is stale or mismatched")
    if scheduled.calendar_fingerprint != policy.calendar_fingerprint:
        raise ValueError("scheduled rebalance calendar is stale or mismatched")

    requests = component_targets_from_intents(
        portfolio,
        intents_by_component,
        event_time=exposure_snapshot.event_time,
        event_sequence=exposure_snapshot.event_sequence,
    )
    event_time = exposure_snapshot.event_time
    if event_time < scheduled.event_time:
        kind = RebalanceApplicationKind.NOT_DUE
        reason = RebalanceApplicationReason.BEFORE_BOUNDARY
        allocation = None
    elif event_time > scheduled.event_time:
        if scheduled.misfire_policy is RebalanceMisfirePolicy.FAIL_RUN:
            kind = RebalanceApplicationKind.MISFIRED
            reason = RebalanceApplicationReason.AFTER_BOUNDARY_FAIL_RUN
        else:
            kind = RebalanceApplicationKind.SKIPPED
            reason = RebalanceApplicationReason.AFTER_BOUNDARY_SKIP_OCCURRENCE
        allocation = None
    else:
        kind = RebalanceApplicationKind.APPLIED
        reason = RebalanceApplicationReason.EXACT_BOUNDARY
        allocation = allocate_component_targets(portfolio, exposure_snapshot, requests)

    return RebalanceAllocationDecision(
        definition_version=REBALANCE_ALLOCATION_DEFINITION_VERSION,
        portfolio_fingerprint=portfolio.fingerprint,
        exposure_snapshot_fingerprint=exposure_snapshot.fingerprint,
        occurrence_id=scheduled.occurrence_id,
        event_time=event_time,
        event_sequence=exposure_snapshot.event_sequence,
        kind=kind,
        reason=reason,
        request_count=len(requests),
        allocation=allocation,
    )
