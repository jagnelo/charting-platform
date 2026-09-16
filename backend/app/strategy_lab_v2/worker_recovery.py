"""Atomic worker-release and attempt-recovery planning semantics."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.admission import ExecutionAdmissionLedger
from app.strategy_lab_v2.canonical import require_sha256_digest
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
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class WorkerRecoveryResolution:
    """Recovery plan plus the pool state after releasing the failed worker."""

    decision: WorkerRecoveryDecision
    plan: RecoveryPlan | None
    pool: WorkerPoolState
    next_attempt: RunAttempt | None = None
    released_reservation_id: str | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, WorkerRecoveryDecision):
            raise TypeError("decision must be a WorkerRecoveryDecision")
        if self.plan is not None and not isinstance(self.plan, RecoveryPlan):
            raise TypeError("plan must be a RecoveryPlan")
        if not isinstance(self.pool, WorkerPoolState):
            raise TypeError("pool must be a WorkerPoolState")
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
        elif self.decision in {WorkerRecoveryDecision.TERMINAL, WorkerRecoveryDecision.NOOP}:
            if self.plan is None:
                raise ValueError("terminal decisions require a recovery plan")
            if self.plan.disposition not in {
                RecoveryDisposition.TERMINAL,
                RecoveryDisposition.NOOP,
            }:
                raise ValueError("terminal/no-op decisions require a matching recovery plan")
            if self.next_attempt is not None:
                raise ValueError("terminal/no-op decisions cannot create an attempt")
        elif self.plan is not None or self.next_attempt is not None:
            raise ValueError("rejected recovery cannot contain a plan or next attempt")
        if self.decision is WorkerRecoveryDecision.REJECT and not self.rejection_reason:
            raise ValueError("rejected recovery requires a reason")
        if self.decision is not WorkerRecoveryDecision.REJECT and self.rejection_reason:
            raise ValueError("successful recovery cannot contain a rejection reason")


def resolve_worker_recovery(
    prior_attempts: Sequence[RunAttempt],
    *,
    admission_ledger: ExecutionAdmissionLedger,
    lease_state: LeaseObservationState,
    pool: WorkerPoolState,
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
        return _reject(pool, "latest attempt has no execution admission receipt")
    if latest.attempt_id != lease_state.lease.attempt_id:
        return _reject(pool, "latest attempt does not match the lease")
    if admission.worker_id != lease_state.lease.worker_id:
        return _reject(pool, "admission and lease reference different workers")
    if lease_state.lease.worker_id != pool.profile.worker_id:
        return _reject(pool, "lease is bound to a different worker pool")
    reservation = next(
        (
            item
            for item in pool.active_reservations
            if item.reservation_id == admission.reservation_id
            and item.attempt_id == latest.attempt_id
        ),
        None,
    )
    if reservation is None:
        return _reject(pool, "admission has no active worker reservation")
    if reason is RecoveryReason.LEASE_EXPIRED:
        status = lease_state.lease.status_at(observed_at)
        if status is not AttemptLeaseStatus.EXPIRED:
            return _reject(pool, "lease-expired recovery requires an expired lease")

    plan = plan_attempt_recovery(
        attempts,
        reason=reason,
        observed_at=observed_at,
        policy=policy,
    )
    released_pool = release_worker_slot(
        pool,
        reservation_id=reservation.reservation_id,
        released_at=observed_at,
    )
    if plan.disposition is RecoveryDisposition.RETRY:
        if not next_attempt_id or not next_attempt_id.strip():
            return _reject(pool, "retry recovery requires a next attempt identity")
        next_attempt = plan.materialize_retry_attempt(attempts, attempt_id=next_attempt_id)
        return WorkerRecoveryResolution(
            WorkerRecoveryDecision.RETRY_SCHEDULED,
            plan,
            released_pool,
            next_attempt,
            reservation.reservation_id,
        )
    decision = (
        WorkerRecoveryDecision.NOOP
        if plan.disposition is RecoveryDisposition.NOOP
        else WorkerRecoveryDecision.TERMINAL
    )
    return WorkerRecoveryResolution(
        decision,
        plan,
        released_pool,
        released_reservation_id=reservation.reservation_id,
    )


def _reject(pool: WorkerPoolState, reason: str) -> WorkerRecoveryResolution:
    return WorkerRecoveryResolution(
        WorkerRecoveryDecision.REJECT,
        None,
        pool,
        rejection_reason=reason,
    )
