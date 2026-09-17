"""Idempotent worker-capacity settlement after an execution handoff.

The worker handoff deliberately stops at process/runtime evidence.  This
module closes the worker lifecycle without publishing a result: it verifies
that the evidence belongs to the admitted attempt, releases the one serial
reservation, and returns an append-only receipt that a persistence adapter can
compare-and-set with the pool state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.admission import ExecutionAdmission
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.lease_observations import (
    LeaseObservation,
    LeaseObservationDecision,
    LeaseObservationKind,
    LeaseObservationState,
    apply_lease_observation,
)
from app.strategy_lab_v2.lifecycle import AttemptLeaseStatus
from app.strategy_lab_v2.worker_execution import WorkerExecutionResolution
from app.strategy_lab_v2.workers import WorkerPoolState, release_worker_slot


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


class WorkerSettlementDecision(StrEnum):
    RELEASED = "released"
    REPLAY_EXISTING = "replay_existing"
    CONFLICT = "conflict"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class WorkerSettlementRecord:
    """Receipt binding one worker release to immutable execution evidence."""

    settlement_fingerprint: str
    admission_fingerprint: str
    worker_execution_fingerprint: str
    attempt_id: str
    reservation_id: str
    worker_id: str
    lease_observation_fingerprint: str
    released_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "settlement_fingerprint",
            "admission_fingerprint",
            "worker_execution_fingerprint",
            "reservation_id",
            "lease_observation_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        for name in ("attempt_id", "worker_id"):
            _nonempty(getattr(self, name), name)
        if self.released_at.tzinfo is None or self.released_at.utcoffset() is None:
            raise ValueError("released_at must be timezone-aware")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class WorkerSettlementLedger:
    """Deterministically ordered, one-settlement-per-attempt receipts."""

    records: tuple[WorkerSettlementRecord, ...] = ()

    def __post_init__(self) -> None:
        records = tuple(self.records)
        if any(not isinstance(item, WorkerSettlementRecord) for item in records):
            raise TypeError("records must contain WorkerSettlementRecord values")
        settlement_ids = [item.settlement_fingerprint for item in records]
        if len(settlement_ids) != len(set(settlement_ids)):
            raise ValueError("settlement fingerprints must be unique")
        attempt_ids = [item.attempt_id for item in records]
        if len(attempt_ids) != len(set(attempt_ids)):
            raise ValueError("an attempt may have only one worker settlement")
        reservation_ids = [item.reservation_id for item in records]
        if len(reservation_ids) != len(set(reservation_ids)):
            raise ValueError("a reservation may have only one worker settlement")
        object.__setattr__(
            self,
            "records",
            tuple(sorted(records, key=lambda item: item.settlement_fingerprint)),
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class WorkerSettlementResolution:
    decision: WorkerSettlementDecision
    ledger: WorkerSettlementLedger
    pool: WorkerPoolState
    lease_state: LeaseObservationState
    settlement_fingerprint: str
    record: WorkerSettlementRecord | None = None
    rejection_reason: str | None = None
    observation: LeaseObservation | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, WorkerSettlementDecision):
            raise TypeError("decision must be a WorkerSettlementDecision")
        if not isinstance(self.ledger, WorkerSettlementLedger):
            raise TypeError("ledger must be a WorkerSettlementLedger")
        if not isinstance(self.pool, WorkerPoolState):
            raise TypeError("pool must be a WorkerPoolState")
        if not isinstance(self.lease_state, LeaseObservationState):
            raise TypeError("lease_state must be a LeaseObservationState")
        require_sha256_digest(
            self.settlement_fingerprint,
            field_name="settlement_fingerprint",
        )
        if self.record is not None and not isinstance(self.record, WorkerSettlementRecord):
            raise TypeError("record must be a WorkerSettlementRecord")
        if self.observation is not None and not isinstance(self.observation, LeaseObservation):
            raise TypeError("observation must be a LeaseObservation")
        if self.decision in {
            WorkerSettlementDecision.RELEASED,
            WorkerSettlementDecision.REPLAY_EXISTING,
        } and self.record is None:
            raise ValueError("released resolutions require a settlement record")
        if self.decision in {
            WorkerSettlementDecision.CONFLICT,
            WorkerSettlementDecision.REJECT,
        } and not self.rejection_reason:
            raise ValueError("conflicts and rejections require a reason")
        if self.decision in {
            WorkerSettlementDecision.RELEASED,
            WorkerSettlementDecision.REPLAY_EXISTING,
        } and self.rejection_reason:
            raise ValueError("released resolutions cannot contain a rejection reason")
        if self.decision in {
            WorkerSettlementDecision.RELEASED,
            WorkerSettlementDecision.REPLAY_EXISTING,
        } and self.observation is None:
            raise ValueError("released resolutions require the lease observation")


def settle_worker_execution(
    ledger: WorkerSettlementLedger,
    pool: WorkerPoolState,
    admission: ExecutionAdmission,
    execution: WorkerExecutionResolution,
    *,
    lease_state: LeaseObservationState,
    released_at: datetime,
) -> WorkerSettlementResolution:
    """Release the admitted worker slot for one completed worker handoff.

    The operation is storage-neutral and returns both immutable states.  An
    exact retry replays the existing receipt without touching the pool; a
    changed execution or release timestamp for the same attempt is a conflict.
    Rejected worker handoffs are settled too because they consumed admission
    capacity but did not start a process.
    """

    if not isinstance(ledger, WorkerSettlementLedger):
        raise TypeError("ledger must be a WorkerSettlementLedger")
    if not isinstance(pool, WorkerPoolState):
        raise TypeError("pool must be a WorkerPoolState")
    if not isinstance(admission, ExecutionAdmission):
        raise TypeError("admission must be an ExecutionAdmission")
    if not isinstance(execution, WorkerExecutionResolution):
        raise TypeError("execution must be a WorkerExecutionResolution")
    if not isinstance(lease_state, LeaseObservationState):
        raise TypeError("lease_state must be a LeaseObservationState")
    if released_at.tzinfo is None or released_at.utcoffset() is None:
        raise ValueError("released_at must be timezone-aware")

    plan = execution.orchestration_plan
    if plan.admission_fingerprint != admission.fingerprint:
        return _reject(ledger, pool, "orchestration plan is not bound to the admission", lease_state=lease_state)
    if plan.attempt_id != admission.attempt_id:
        return _reject(ledger, pool, "orchestration plan and admission reference different attempts", lease_state=lease_state)
    if plan.worker_id != admission.worker_id:
        return _reject(ledger, pool, "orchestration plan and admission reference different workers", lease_state=lease_state)
    if admission.worker_id != pool.profile.worker_id:
        return _reject(ledger, pool, "admission is bound to a different worker pool", lease_state=lease_state)
    if admission.worker_kind is not pool.profile.kind:
        return _reject(ledger, pool, "admission kind does not match the worker pool", lease_state=lease_state)
    if admission.worker_profile_fingerprint != pool.profile.runtime_profile_fingerprint:
        return _reject(ledger, pool, "admission profile does not match the worker pool", lease_state=lease_state)
    if lease_state.lease.attempt_id != admission.attempt_id:
        return _reject(ledger, pool, "lease and admission reference different attempts", lease_state=lease_state)
    if lease_state.lease.worker_id != admission.worker_id:
        return _reject(ledger, pool, "lease and admission reference different workers", lease_state=lease_state)

    reservation = next(
        (
            item
            for item in pool.reservations
            if item.reservation_id == admission.reservation_id
            and item.attempt_id == admission.attempt_id
        ),
        None,
    )
    if reservation is None:
        return _reject(ledger, pool, "admission has no matching worker reservation", lease_state=lease_state)
    if released_at < reservation.acquired_at:
        return _reject(ledger, pool, "release cannot precede reservation acquisition", lease_state=lease_state)
    settlement_fingerprint = content_digest(
        {
            "admission_fingerprint": admission.fingerprint,
            "attempt_id": admission.attempt_id,
            "released_at": released_at,
            "reservation_id": admission.reservation_id,
            "worker_execution_fingerprint": execution.fingerprint,
        }
    )
    existing = next(
        (item for item in ledger.records if item.attempt_id == admission.attempt_id),
        None,
    )
    if existing is not None:
        if existing.settlement_fingerprint != settlement_fingerprint:
            return WorkerSettlementResolution(
                WorkerSettlementDecision.CONFLICT,
                ledger,
                pool,
                lease_state,
                settlement_fingerprint,
                rejection_reason="attempt is already bound to different worker settlement content",
            )
        if reservation.active:
            return _reject(
                ledger,
                pool,
                "settlement receipt exists but worker reservation is still active",
                lease_state=lease_state,
            )
        if reservation.released_at != existing.released_at:
            return _reject(
                ledger,
                pool,
                "worker reservation release time differs from settlement receipt",
                lease_state=lease_state,
            )
        applied_observation = next(
            (
                item
                for item in lease_state.applied_observations
                if item.fingerprint == existing.lease_observation_fingerprint
            ),
            None,
        )
        if applied_observation is None:
            return _reject(
                ledger,
                pool,
                "settlement receipt exists but lease release observation is missing",
                lease_state=lease_state,
        )
        return WorkerSettlementResolution(
            WorkerSettlementDecision.REPLAY_EXISTING,
            ledger,
            pool,
            lease_state,
            settlement_fingerprint,
            existing,
            observation=applied_observation,
        )
    if not reservation.active:
        return _reject(
            ledger,
            pool,
            "worker reservation is already released without a settlement receipt",
            lease_state=lease_state,
        )

    try:
        lease_status = lease_state.lease.status_at(released_at)
    except (TypeError, ValueError) as exc:
        return _reject(ledger, pool, str(exc), lease_state=lease_state)
    if lease_status is AttemptLeaseStatus.EXPIRED:
        return _reject(ledger, pool, "expired leases require worker recovery", lease_state=lease_state)
    if lease_status is AttemptLeaseStatus.RELEASED:
        return _reject(ledger, pool, "lease is already released without a settlement receipt", lease_state=lease_state)

    release_observation = _release_observation(
        lease_state, settlement_fingerprint, released_at
    )
    lease_observation_fingerprint = release_observation.fingerprint

    lease_resolution = apply_lease_observation(lease_state, release_observation)
    if lease_resolution.decision is not LeaseObservationDecision.APPLY:
        return _reject(
            ledger,
            pool,
            lease_resolution.rejection_reason or "lease release observation was rejected",
            lease_state=lease_state,
        )

    released_pool = release_worker_slot(
        pool,
        reservation_id=reservation.reservation_id,
        released_at=released_at,
    )
    record = WorkerSettlementRecord(
        settlement_fingerprint=settlement_fingerprint,
        admission_fingerprint=admission.fingerprint,
        worker_execution_fingerprint=execution.fingerprint,
        attempt_id=admission.attempt_id,
        reservation_id=admission.reservation_id,
        worker_id=admission.worker_id,
        lease_observation_fingerprint=lease_observation_fingerprint,
        released_at=released_at,
    )
    return WorkerSettlementResolution(
        WorkerSettlementDecision.RELEASED,
        WorkerSettlementLedger(ledger.records + (record,)),
        released_pool,
        lease_resolution.state,
        settlement_fingerprint,
        record,
        observation=release_observation,
    )


def _release_observation(
    lease_state: LeaseObservationState,
    settlement_fingerprint: str,
    released_at: datetime,
) -> LeaseObservation:
    """Reconstruct the deterministic release observation for a settlement."""

    return LeaseObservation(
        observation_id=content_digest(
            {
                "kind": LeaseObservationKind.RELEASE,
                "lease_id": lease_state.lease.lease_id,
                "settlement_fingerprint": settlement_fingerprint,
            }
        ),
        lease_id=lease_state.lease.lease_id,
        worker_id=lease_state.lease.worker_id,
        attempt_id=lease_state.lease.attempt_id,
        sequence=lease_state.last_sequence + 1,
        kind=LeaseObservationKind.RELEASE,
        observed_at=released_at,
    )


def _reject(
    ledger: WorkerSettlementLedger,
    pool: WorkerPoolState,
    reason: str,
    *,
    lease_state: LeaseObservationState | None = None,
) -> WorkerSettlementResolution:
    if lease_state is None:
        raise TypeError("lease_state is required for rejected settlement resolutions")
    return WorkerSettlementResolution(
        WorkerSettlementDecision.REJECT,
        ledger,
        pool,
        lease_state,
        content_digest({"reason": reason}),
        rejection_reason=reason,
    )
