from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.api_contracts import ApiError, ApiErrorCode
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.outcomes import (
    ExecutionOutcome,
    OutcomeDecision,
    OutcomeStatus,
    OutcomeUpdate,
    apply_outcome_update,
    new_execution_outcome,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)
SUBMISSION = content_digest({"submission": "one"})
RESULT = content_digest({"result": "parquet-manifest"})


def _running_update(sequence: int = 1) -> OutcomeUpdate:
    return OutcomeUpdate(
        submission_id=SUBMISSION,
        attempt_id="attempt-1",
        sequence=sequence,
        status=OutcomeStatus.RUNNING,
        observed_at=NOW + timedelta(seconds=sequence),
    )


def test_outcome_lifecycle_is_monotonic_and_terminal_result_is_bound() -> None:
    state = new_execution_outcome(SUBMISSION, "attempt-1", accepted_at=NOW)
    assert state.sequence == 0
    running = apply_outcome_update(state, _running_update()).state
    assert running.status is OutcomeStatus.RUNNING
    succeeded_update = OutcomeUpdate(
        submission_id=SUBMISSION,
        attempt_id="attempt-1",
        sequence=2,
        status=OutcomeStatus.SUCCEEDED,
        observed_at=NOW + timedelta(seconds=2),
        result_digest=RESULT,
    )
    succeeded = apply_outcome_update(running, succeeded_update)
    assert succeeded.decision is OutcomeDecision.APPLY
    assert succeeded.state.result_digest == RESULT


def test_exact_terminal_repeats_replay_and_different_repeats_conflict() -> None:
    state = new_execution_outcome(SUBMISSION, "attempt-1", accepted_at=NOW)
    failed_update = OutcomeUpdate(
        submission_id=SUBMISSION,
        attempt_id="attempt-1",
        sequence=1,
        status=OutcomeStatus.FAILED,
        observed_at=NOW + timedelta(seconds=1),
        error=ApiError(
            ApiErrorCode.INTERNAL_ERROR,
            "worker failed",
            "request-1",
            500,
            retryable=True,
        ),
    )
    failed = apply_outcome_update(state, failed_update).state
    replay = apply_outcome_update(failed, failed_update)
    assert replay.decision is OutcomeDecision.REPLAY_EXISTING
    different = OutcomeUpdate(
        submission_id=SUBMISSION,
        attempt_id="attempt-1",
        sequence=1,
        status=OutcomeStatus.CANCELLED,
        observed_at=NOW + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="conflicts"):
        apply_outcome_update(failed, different)


def test_outcome_transitions_reject_foreign_stale_and_illegal_updates() -> None:
    state = apply_outcome_update(
        new_execution_outcome(SUBMISSION, "attempt-1", accepted_at=NOW), _running_update()
    ).state
    with pytest.raises(ValueError, match="same submission"):
        apply_outcome_update(
            state,
            OutcomeUpdate(
                SUBMISSION,
                "other-attempt",
                2,
                OutcomeStatus.SUCCEEDED,
                NOW + timedelta(seconds=2),
                result_digest=RESULT,
            ),
        )
    with pytest.raises(ValueError, match="move backwards"):
        apply_outcome_update(
            state,
            OutcomeUpdate(
                SUBMISSION,
                "attempt-1",
                2,
                OutcomeStatus.RUNNING,
                NOW,
            ),
        )
    failed = apply_outcome_update(
        state,
        OutcomeUpdate(
            SUBMISSION,
            "attempt-1",
            2,
            OutcomeStatus.FAILED,
            NOW + timedelta(seconds=2),
            error=ApiError(ApiErrorCode.INTERNAL_ERROR, "failed", "request-1", 500),
        ),
    ).state
    with pytest.raises(ValueError, match="illegal outcome transition"):
        apply_outcome_update(failed, _running_update(3))


def test_outcome_contract_validates_terminal_payloads_and_initial_state() -> None:
    with pytest.raises(ValueError, match="successful outcomes"):
        OutcomeUpdate(SUBMISSION, "attempt-1", 1, OutcomeStatus.SUCCEEDED, NOW)
    with pytest.raises(ValueError, match="non-terminal"):
        OutcomeUpdate(
            SUBMISSION,
            "attempt-1",
            1,
            OutcomeStatus.RUNNING,
            NOW,
            result_digest=RESULT,
        )
    with pytest.raises(ValueError, match="sequence-zero"):
        ExecutionOutcome(SUBMISSION, "attempt-1", 0, OutcomeStatus.RUNNING, NOW)
    with pytest.raises(ValueError, match="submission_id"):
        new_execution_outcome("bad", "attempt-1", accepted_at=NOW)
