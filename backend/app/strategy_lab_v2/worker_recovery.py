"""Atomic worker-release and attempt-recovery planning semantics."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.admission import ExecutionAdmissionLedger
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import RunAttempt
from app.strategy_lab_v2.lease_observations import LeaseObservationState
from app.strategy_lab_v2.lifecycle import AttemptLeaseStatus
from app.strategy_lab_v2.recovery import (
    RecoveryDisposition,
    RecoveryPlan,
    RecoveryReason,
    RetryPolicy,
    plan_attempt_recovery,
)
from app.strategy_lab_v2.workers import WorkerPoolState, release_worker_slot


class WorkerRecoveryDecision(StrEnum):
    RETRY_SCHEDULED = "retry_scheduled"
    TERMINAL = "terminal"
    NOOP = "noop"
    REPLAY_EXISTING = "replay_existing"
    CONFLICT = "conflict"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class WorkerRecoveryRecord:
    """Receipt binding one recovery decision to the released reservation."""

    recovery_fingerprint: str
    attempt_id: str
    reservation_id: str
    decision: WorkerRecoveryDecision
    plan_fingerprint: str
    next_attempt_id: str | None
    released_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "recovery_fingerprint",
            "reservation_id",
            "plan_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        for name in ("attempt_id",):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        if not isinstance(self.decision, WorkerRecoveryDecision):
            raise TypeError("decision must be a WorkerRecoveryDecision")
        if self.next_attempt_id is not None and (
            not isinstance(self.next_attempt_id, str) or not self.next_attempt_id.strip()
        ):
            raise ValueError("next_attempt_id must be non-empty when provided")
        if self.released_at.tzinfo is None or self.released_at.utcoffset() is None:
            raise ValueError("released_at must be timezone-aware")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class WorkerRecoveryLedger:
    """Deterministically ordered, one recovery receipt per attempt."""

    records: tuple[WorkerRecoveryRecord, ...] = ()

    def __post_init__(self) -> None:
        records = tuple(self.records)
        if any(not isinstance(item, WorkerRecoveryRecord) for item in records):
            raise TypeError("records must contain WorkerRecoveryRecord values")
        fingerprints = [item.recovery_fingerprint for item in records]
        if len(fingerprints) != len(set(fingerprints)):
            raise ValueError("recovery fingerprints must be unique")
        attempts = [item.attempt_id for item in records]
        if len(attempts) != len(set(attempts)):
            raise ValueError("an attempt may have only one recovery receipt")
        reservations = [item.reservation_id for item in records]
        if len(reservations) != len(set(reservations)):
            raise ValueError("a reservation may have only one recovery receipt")
        object.__setattr__(self, "records", tuple(sorted(records, key=lambda item: item.recovery_fingerprint)))

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class WorkerRecoveryResolution:
    """Recovery plan plus the pool state after releasing the failed worker."""

    decision: WorkerRecoveryDecision
    plan: RecoveryPlan | None
    pool: WorkerPoolState
    next_attempt: RunAttempt | None = None
    released_reservation_id: str | None = None
    rejection_reason: str | None = None
    ledger: WorkerRecoveryLedger = WorkerRecoveryLedger()

    def __post_init__(self) -> None:
        if not isinstance(self.decision, WorkerRecoveryDecision):
            raise TypeError("decision must be a WorkerRecoveryDecision")
        if self.plan is not None and not isinstance(self.plan, RecoveryPlan):
            raise TypeError("plan must be a RecoveryPlan")
        if not isinstance(self.pool, WorkerPoolState):
            raise TypeError("pool must be a WorkerPoolState")
        if not isinstance(self.ledger, WorkerRecoveryLedger):
            raise TypeError("ledger must be a WorkerRecoveryLedger")
        if self.next_attempt is not None and not isinstance(self.next_attempt, RunAttempt):
            raise TypeError("next_attempt must be a RunAttempt")
        if self.released_reservation_id is not None:
            require_sha256_digest(
                self.released_reservation_id,
                field_name="released_reservation_id",
            )
        if self.decision is WorkerRecoveryDecision.RETRY_SCHEDULED:
            if self.plan is None or self.plan.disposition is not RecoveryDisposition.RETRY:
                raise ValueError("retry decisions require a retry plan")
            if self.next_attempt is None or self.released_reservation_id is None:
                raise ValueError("retry decisions require a queued attempt and released reservation")
        elif self.decision in {
            WorkerRecoveryDecision.TERMINAL,
            WorkerRecoveryDecision.NOOP,
            WorkerRecoveryDecision.REPLAY_EXISTING,
        }:
            if self.plan is None:
                raise ValueError("terminal/replay decisions require a recovery plan")
            if self.plan.disposition not in {
                RecoveryDisposition.TERMINAL,
                RecoveryDisposition.NOOP,
                RecoveryDisposition.RETRY,
            }:
                raise ValueError("terminal/no-op/replay decisions require a matching recovery plan")
            if self.decision in {WorkerRecoveryDecision.TERMINAL, WorkerRecoveryDecision.NOOP}:
                if self.plan.disposition is RecoveryDisposition.RETRY or self.next_attempt is not None:
                    raise ValueError("terminal/no-op decisions cannot create an attempt")
            elif self.plan.disposition is RecoveryDisposition.RETRY:
                if self.next_attempt is None or self.released_reservation_id is None:
                    raise ValueError("replayed retry decisions require a queued attempt and released reservation")
        elif self.decision is WorkerRecoveryDecision.CONFLICT:
            if self.plan is not None or self.next_attempt is not None:
                raise ValueError("conflicting recovery cannot contain a plan or next attempt")
        elif self.plan is not None or self.next_attempt is not None:
            raise ValueError("rejected recovery cannot contain a plan or next attempt")
        if self.decision in {WorkerRecoveryDecision.REJECT, WorkerRecoveryDecision.CONFLICT} and not self.rejection_reason:
            raise ValueError("rejected/conflicting recovery requires a reason")
        if self.decision not in {WorkerRecoveryDecision.REJECT, WorkerRecoveryDecision.CONFLICT} and self.rejection_reason:
            raise ValueError("successful recovery cannot contain a rejection reason")


def resolve_worker_recovery(
    prior_attempts: Sequence[RunAttempt],
    *,
    admission_ledger: ExecutionAdmissionLedger,
    lease_state: LeaseObservationState,
    pool: WorkerPoolState,
    ledger: WorkerRecoveryLedger,
    reason: RecoveryReason,
    observed_at: datetime,
    policy: RetryPolicy = RetryPolicy(),
    next_attempt_id: str | None = None,
) -> WorkerRecoveryResolution:
    """Release a worker reservation and plan infrastructure retry atomically.

    The latest attempt must match a recorded admission, lease, and active pool
    reservation. The recovery plan remains infrastructure-only: a retry keeps
    the same scientific trial identity and never invokes an execution engine.
    """

    if not isinstance(admission_ledger, ExecutionAdmissionLedger):
        raise TypeError("admission_ledger must be an ExecutionAdmissionLedger")
    if not isinstance(lease_state, LeaseObservationState):
        raise TypeError("lease_state must be a LeaseObservationState")
    if not isinstance(pool, WorkerPoolState):
        raise TypeError("pool must be a WorkerPoolState")
    if not isinstance(ledger, WorkerRecoveryLedger):
        raise TypeError("ledger must be a WorkerRecoveryLedger")
    if not isinstance(reason, RecoveryReason):
        raise TypeError("reason must be a RecoveryReason")
    if not isinstance(policy, RetryPolicy):
        raise TypeError("policy must be a RetryPolicy")
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("recovery observation time must be timezone-aware")
    attempts = tuple(prior_attempts)
    if not attempts or any(not isinstance(item, RunAttempt) for item in attempts):
        raise TypeError("prior_attempts must contain RunAttempt values")
    latest = max(attempts, key=lambda item: item.ordinal)
    admission = next(
        (item for item in admission_ledger.admissions if item.attempt_id == latest.attempt_id),
        None,
    )
    if admission is None:
        return _reject(pool, ledger, "latest attempt has no execution admission receipt")
    if latest.attempt_id != lease_state.lease.attempt_id:
        return _reject(pool, ledger, "latest attempt does not match the lease")
    if admission.worker_id != lease_state.lease.worker_id:
        return _reject(pool, ledger, "admission and lease reference different workers")
    if lease_state.lease.worker_id != pool.profile.worker_id:
        return _reject(pool, ledger, "lease is bound to a different worker pool")
    reservation = next(
        (
            item
            for item in pool.reservations
            if item.reservation_id == admission.reservation_id
            and item.attempt_id == latest.attempt_id
        ),
        None,
    )
    if reservation is None:
        return _reject(pool, ledger, "admission has no active worker reservation")
    if reason is RecoveryReason.LEASE_EXPIRED:
        status = lease_state.lease.status_at(observed_at)
        if status is not AttemptLeaseStatus.EXPIRED:
            return _reject(pool, ledger, "lease-expired recovery requires an expired lease")

    plan = plan_attempt_recovery(
        attempts,
        reason=reason,
        observed_at=observed_at,
        policy=policy,
    )
    next_attempt: RunAttempt | None = None
    if plan.disposition is RecoveryDisposition.RETRY:
        if not next_attempt_id or not next_attempt_id.strip():
            return _reject(pool, ledger, "retry recovery requires a next attempt identity")
        next_attempt = plan.materialize_retry_attempt(attempts, attempt_id=next_attempt_id)
    recovery_fingerprint = content_digest(
        {
            "next_attempt_id": next_attempt.attempt_id if next_attempt is not None else None,
            "plan_fingerprint": plan.fingerprint,
            "prior_attempt_id": latest.attempt_id,
            "reason": reason,
            "reservation_id": reservation.reservation_id,
        }
    )
    existing = next(
        (item for item in ledger.records if item.attempt_id == latest.attempt_id),
        None,
    )
    if existing is not None:
        if existing.recovery_fingerprint != recovery_fingerprint:
            return WorkerRecoveryResolution(
                WorkerRecoveryDecision.CONFLICT,
                None,
                pool,
                rejection_reason="attempt is already bound to different recovery content",
                ledger=ledger,
            )
        if reservation.active:
            return _reject(
                pool,
                ledger,
                "recovery receipt exists but worker reservation is still active",
            )
        if reservation.released_at != existing.released_at:
            return _reject(
                pool,
                ledger,
                "worker reservation release time differs from recovery receipt",
            )
        replay_attempt = None
        if existing.next_attempt_id is not None:
            replay_attempt = plan.materialize_retry_attempt(
                attempts,
                attempt_id=existing.next_attempt_id,
            )
        replay_decision = WorkerRecoveryDecision.REPLAY_EXISTING
        return WorkerRecoveryResolution(
            replay_decision,
            plan,
            pool,
            replay_attempt,
            existing.reservation_id,
            ledger=ledger,
        )
    if not reservation.active:
        return _reject(
            pool,
            ledger,
            "worker reservation is already released without a recovery receipt",
        )
    released_pool = release_worker_slot(
        pool,
        reservation_id=reservation.reservation_id,
        released_at=observed_at,
    )
    if plan.disposition is RecoveryDisposition.RETRY:
        decision = WorkerRecoveryDecision.RETRY_SCHEDULED
    else:
        decision = (
            WorkerRecoveryDecision.NOOP
            if plan.disposition is RecoveryDisposition.NOOP
            else WorkerRecoveryDecision.TERMINAL
        )
    record = WorkerRecoveryRecord(
        recovery_fingerprint=recovery_fingerprint,
        attempt_id=latest.attempt_id,
        reservation_id=reservation.reservation_id,
        decision=decision,
        plan_fingerprint=plan.fingerprint,
        next_attempt_id=next_attempt.attempt_id if next_attempt is not None else None,
        released_at=observed_at,
    )
    return WorkerRecoveryResolution(
        decision,
        plan,
        released_pool,
        next_attempt,
        reservation.reservation_id,
        ledger=WorkerRecoveryLedger(ledger.records + (record,)),
    )


def _reject(
    pool: WorkerPoolState,
    ledger: WorkerRecoveryLedger,
    reason: str,
) -> WorkerRecoveryResolution:
    return WorkerRecoveryResolution(
        WorkerRecoveryDecision.REJECT,
        None,
        pool,
        rejection_reason=reason,
        ledger=ledger,
    )
