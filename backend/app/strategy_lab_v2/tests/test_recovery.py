from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.contracts import AttemptState, RunAttempt
from app.strategy_lab_v2.lifecycle import transition_attempt
from app.strategy_lab_v2.recovery import (
    RecoveryDisposition,
    RecoveryReason,
    RetryPolicy,
    plan_attempt_recovery,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _failed_attempt(*, attempt_id: str = "attempt-1", ordinal: int = 1) -> RunAttempt:
    queued = RunAttempt(attempt_id, "trial-1", ordinal, AttemptState.QUEUED, NOW)
    running = transition_attempt(queued, AttemptState.RUNNING, now=NOW + timedelta(seconds=1))
    return transition_attempt(running, AttemptState.FAILED, now=NOW + timedelta(seconds=2))


def test_recovery_plan_is_deterministic_and_materializes_same_trial_retry() -> None:
    policy = RetryPolicy(
        max_attempts=4,
        initial_backoff=timedelta(seconds=5),
        max_backoff=timedelta(seconds=20),
    )
    failed = _failed_attempt()
    plan = plan_attempt_recovery(
        (failed,),
        reason=RecoveryReason.WORKER_CRASH,
        observed_at=NOW + timedelta(seconds=3),
        policy=policy,
    )
    assert plan.disposition is RecoveryDisposition.RETRY
    assert plan.next_ordinal == 2
    assert plan.retry_at == NOW + timedelta(seconds=8)
    assert plan.fingerprint.startswith("sha256:")
    assert plan == plan_attempt_recovery(
        (failed,),
        reason=RecoveryReason.WORKER_CRASH,
        observed_at=NOW + timedelta(seconds=3),
        policy=policy,
    )
    retry = plan.materialize_retry_attempt((failed,), attempt_id="attempt-2")
    assert retry.trial_id == failed.trial_id
    assert retry.ordinal == 2
    assert retry.created_at == plan.retry_at


def test_recovery_backoff_caps_and_attempt_limit_is_terminal() -> None:
    policy = RetryPolicy(
        max_attempts=3,
        initial_backoff=timedelta(seconds=5),
        max_backoff=timedelta(seconds=10),
    )
    first = _failed_attempt()
    second = plan_attempt_recovery(
        (first,),
        reason=RecoveryReason.LEASE_EXPIRED,
        observed_at=NOW + timedelta(seconds=3),
        policy=policy,
    ).materialize_retry_attempt((first,), attempt_id="attempt-2")
    second = transition_attempt(
        transition_attempt(second, AttemptState.RUNNING, now=NOW + timedelta(seconds=9)),
        AttemptState.FAILED,
        now=NOW + timedelta(seconds=10),
    )
    plan = plan_attempt_recovery(
        (first, second),
        reason=RecoveryReason.TRANSIENT_ENGINE_ERROR,
        observed_at=NOW + timedelta(seconds=11),
        policy=policy,
    )
    assert plan.disposition is RecoveryDisposition.RETRY
    assert plan.retry_at == NOW + timedelta(seconds=21)
    third = plan.materialize_retry_attempt((first, second), attempt_id="attempt-3")
    assert third.ordinal == 3
    # The supplied chain is intentionally invalid: the latest attempt is running.
    with pytest.raises(ValueError, match="terminal"):
        plan_attempt_recovery(
            (first, second, transition_attempt(third, AttemptState.RUNNING, now=NOW + timedelta(seconds=22))),
            reason=RecoveryReason.WORKER_CRASH,
            observed_at=NOW + timedelta(seconds=23),
            policy=policy,
        )
    failed_third = transition_attempt(
        transition_attempt(third, AttemptState.RUNNING, now=NOW + timedelta(seconds=22)),
        AttemptState.FAILED,
        now=NOW + timedelta(seconds=23),
    )
    exhausted = plan_attempt_recovery(
        (first, second, failed_third),
        reason=RecoveryReason.WORKER_CRASH,
        observed_at=NOW + timedelta(seconds=24),
        policy=policy,
    )
    assert exhausted.disposition is RecoveryDisposition.TERMINAL
    assert "exhausted" in exhausted.rationale


def test_success_and_cancellation_or_non_retryable_reasons_do_not_retry() -> None:
    succeeded = RunAttempt("attempt-succeeded", "trial-1", 1, AttemptState.SUCCEEDED, NOW)
    success_plan = plan_attempt_recovery(
        (succeeded,),
        reason=RecoveryReason.WORKER_CRASH,
        observed_at=NOW + timedelta(seconds=5),
    )
    assert success_plan.disposition is RecoveryDisposition.NOOP

    cancelled = RunAttempt(
        "attempt-cancelled", "trial-1", 1, AttemptState.CANCELLED, NOW + timedelta(seconds=1)
    )
    cancelled_plan = plan_attempt_recovery(
        (cancelled,),
        reason=RecoveryReason.CANCELLED,
        observed_at=NOW + timedelta(seconds=2),
    )
    assert cancelled_plan.disposition is RecoveryDisposition.TERMINAL

    with pytest.raises(ValueError, match="cancelled"):
        RetryPolicy(retryable_reasons=frozenset({RecoveryReason.CANCELLED}))


def test_recovery_rejects_invalid_chain_and_time() -> None:
    failed = _failed_attempt()
    with pytest.raises(ValueError, match="precede"):
        plan_attempt_recovery(
            (failed,),
            reason=RecoveryReason.WORKER_CRASH,
            observed_at=NOW,
        )
    with pytest.raises(ValueError, match="at least one"):
        plan_attempt_recovery(
            (),
            reason=RecoveryReason.WORKER_CRASH,
            observed_at=NOW,
        )
