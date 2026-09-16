from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.strategy_lab_v2.admission import (
    ExecutionAdmissionDecision,
    ExecutionAdmissionLedger,
    resolve_execution_admission,
)
from app.strategy_lab_v2.contracts import AttemptState, RunAttempt
from app.strategy_lab_v2.execution import authorize_execution
from app.strategy_lab_v2.lease_observations import LeaseObservationState
from app.strategy_lab_v2.lifecycle import ExecutionAttemptLease, transition_attempt
from app.strategy_lab_v2.recovery import RecoveryDisposition, RecoveryReason
from app.strategy_lab_v2.runtime_execution import preflight_strategy_runtime
from app.strategy_lab_v2.tests.test_admission import _request, _reservation
from app.strategy_lab_v2.tests.test_execution import _execution_fixture
from app.strategy_lab_v2.tests.test_runtime_execution import _profile
from app.strategy_lab_v2.worker_recovery import (
    WorkerRecoveryDecision,
    WorkerRecoveryLedger,
    resolve_worker_recovery,
)
from app.strategy_lab_v2.workers import WorkerKind, WorkerPoolState, WorkerProfile

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _admitted() -> tuple[RunAttempt, ExecutionAttemptLease, ExecutionAdmissionLedger, WorkerPoolState]:
    trial, running, validation, capability, lease = _execution_fixture()
    authorization = authorize_execution(
        trial,
        running,
        validation,
        capability,
        lease,
        now=NOW + timedelta(seconds=3),
    )
    profile = _profile()
    request = _request(running.attempt_id, profile, source_digest=authorization.source_digest)
    preflight = preflight_strategy_runtime(request, profile)
    pool = WorkerPoolState(WorkerProfile("worker-1", WorkerKind.BACKTEST, profile.fingerprint))
    admitted = resolve_execution_admission(
        ExecutionAdmissionLedger(),
        authorization,
        request,
        preflight,
        pool,
        reservation_id=_reservation("one"),
        now=NOW + timedelta(seconds=4),
    )
    assert admitted.decision is ExecutionAdmissionDecision.ADMIT
    return running, lease, admitted.ledger, admitted.pool


def test_worker_crash_releases_capacity_and_materializes_same_trial_retry() -> None:
    running, lease, ledger, pool = _admitted()
    failed = transition_attempt(running, AttemptState.FAILED, now=NOW + timedelta(seconds=5))
    resolution = resolve_worker_recovery(
        (failed,),
        admission_ledger=ledger,
        lease_state=LeaseObservationState(lease),
        pool=pool,
        ledger=WorkerRecoveryLedger(),
        reason=RecoveryReason.WORKER_CRASH,
        observed_at=NOW + timedelta(seconds=6),
        next_attempt_id="attempt-2",
    )

    assert resolution.decision is WorkerRecoveryDecision.RETRY_SCHEDULED
    assert resolution.plan is not None
    assert resolution.plan.disposition is RecoveryDisposition.RETRY
    assert resolution.next_attempt is not None
    assert resolution.next_attempt.trial_id == failed.trial_id
    assert resolution.next_attempt.ordinal == 2
    assert resolution.released_reservation_id == _reservation("one")
    assert not resolution.pool.active_reservations

    replay = resolve_worker_recovery(
        (failed,),
        admission_ledger=ledger,
        lease_state=resolution.lease_state,
        pool=resolution.pool,
        ledger=resolution.ledger,
        reason=RecoveryReason.WORKER_CRASH,
        observed_at=NOW + timedelta(seconds=6),
        next_attempt_id="attempt-2",
    )
    assert replay.decision is WorkerRecoveryDecision.REPLAY_EXISTING
    assert replay.next_attempt == resolution.next_attempt
    assert replay.pool == resolution.pool

    conflict = resolve_worker_recovery(
        (failed,),
        admission_ledger=ledger,
        lease_state=LeaseObservationState(lease),
        pool=resolution.pool,
        ledger=resolution.ledger,
        reason=RecoveryReason.WORKER_CRASH,
        observed_at=NOW + timedelta(seconds=7),
        next_attempt_id="attempt-2",
    )
    assert conflict.decision is WorkerRecoveryDecision.CONFLICT
    assert conflict.pool == resolution.pool


def test_successful_attempt_is_noop_but_still_releases_its_worker_slot() -> None:
    running, lease, ledger, pool = _admitted()
    succeeded = transition_attempt(running, AttemptState.SUCCEEDED, now=NOW + timedelta(seconds=5))
    resolution = resolve_worker_recovery(
        (succeeded,),
        admission_ledger=ledger,
        lease_state=LeaseObservationState(lease),
        pool=pool,
        ledger=WorkerRecoveryLedger(),
        reason=RecoveryReason.WORKER_CRASH,
        observed_at=NOW + timedelta(seconds=6),
    )
    assert resolution.decision is WorkerRecoveryDecision.NOOP
    assert resolution.plan is not None
    assert resolution.plan.disposition is RecoveryDisposition.NOOP
    assert not resolution.pool.active_reservations


def test_expired_lease_is_retryable_and_non_retryable_cancellation_is_terminal() -> None:
    running, lease, ledger, pool = _admitted()
    failed = transition_attempt(running, AttemptState.FAILED, now=NOW + timedelta(seconds=5))
    expired = resolve_worker_recovery(
        (failed,),
        admission_ledger=ledger,
        lease_state=LeaseObservationState(lease),
        pool=pool,
        ledger=WorkerRecoveryLedger(),
        reason=RecoveryReason.LEASE_EXPIRED,
        observed_at=NOW + timedelta(seconds=40),
        next_attempt_id="attempt-2",
    )
    assert expired.decision is WorkerRecoveryDecision.RETRY_SCHEDULED

    cancelled = transition_attempt(running, AttemptState.CANCELLED, now=NOW + timedelta(seconds=5))
    terminal = resolve_worker_recovery(
        (cancelled,),
        admission_ledger=ledger,
        lease_state=LeaseObservationState(lease),
        pool=pool,
        ledger=WorkerRecoveryLedger(),
        reason=RecoveryReason.CANCELLED,
        observed_at=NOW + timedelta(seconds=6),
    )
    assert terminal.decision is WorkerRecoveryDecision.TERMINAL
    assert terminal.plan is not None
    assert terminal.plan.disposition is RecoveryDisposition.TERMINAL
    assert not terminal.pool.active_reservations


def test_recovery_rejects_missing_receipts_mismatched_workers_and_missing_retry_ids() -> None:
    running, lease, ledger, pool = _admitted()
    failed = transition_attempt(running, AttemptState.FAILED, now=NOW + timedelta(seconds=5))
    missing = resolve_worker_recovery(
        (failed,),
        admission_ledger=ExecutionAdmissionLedger(),
        lease_state=LeaseObservationState(lease),
        pool=pool,
        ledger=WorkerRecoveryLedger(),
        reason=RecoveryReason.WORKER_CRASH,
        observed_at=NOW + timedelta(seconds=6),
        next_attempt_id="attempt-2",
    )
    assert missing.decision is WorkerRecoveryDecision.REJECT
    assert missing.rejection_reason == "latest attempt has no execution admission receipt"

    no_retry_id = resolve_worker_recovery(
        (failed,),
        admission_ledger=ledger,
        lease_state=LeaseObservationState(lease),
        pool=pool,
        ledger=WorkerRecoveryLedger(),
        reason=RecoveryReason.WORKER_CRASH,
        observed_at=NOW + timedelta(seconds=6),
    )
    assert no_retry_id.decision is WorkerRecoveryDecision.REJECT
    assert no_retry_id.rejection_reason == "retry recovery requires a next attempt identity"
    assert no_retry_id.pool == pool
