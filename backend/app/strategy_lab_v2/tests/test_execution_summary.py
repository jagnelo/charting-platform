from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.api_contracts import ApiError, ApiErrorCode
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.execution_summary import (
    ExecutionSummaryDecision,
    build_execution_summary,
)
from app.strategy_lab_v2.outcomes import (
    OutcomeStatus,
    OutcomeUpdate,
    apply_outcome_update,
    new_execution_outcome,
)
from app.strategy_lab_v2.progress import (
    ExecutionProgressUpdate,
    ProgressPhase,
    apply_progress_update,
    new_progress_state,
)
from app.strategy_lab_v2.result_publication import ResultPublicationDecision, ResultPublicationPlan
from app.strategy_lab_v2.submissions import SubmissionRequest, create_submission_receipt

NOW = datetime(2024, 1, 1, tzinfo=UTC)
ATTEMPT = "attempt-1"


def _receipt():
    request = SubmissionRequest(
        "idem-1", "backtest", ATTEMPT, content_digest("payload"), NOW
    )
    return create_submission_receipt(request, accepted_at=NOW)


def _progress(phase: ProgressPhase = ProgressPhase.QUEUED, *, sequence: int = 0):
    state = new_progress_state(ATTEMPT, total_units=10, now=NOW)
    if sequence == 0:
        return state
    return apply_progress_update(
        state,
        ExecutionProgressUpdate(
            ATTEMPT, sequence, phase, 10 if phase is ProgressPhase.SUCCEEDED else 1, 10, NOW + timedelta(seconds=sequence)
        ),
    )


def _outcome(status: OutcomeStatus = OutcomeStatus.ACCEPTED):
    state = new_execution_outcome(_receipt().submission_id, ATTEMPT, accepted_at=NOW)
    if status is OutcomeStatus.ACCEPTED:
        return state
    update = OutcomeUpdate(
        _receipt().submission_id,
        ATTEMPT,
        1,
        status,
        NOW + timedelta(seconds=1),
        result_digest=content_digest("result") if status is OutcomeStatus.SUCCEEDED else None,
        error=(
            ApiError(ApiErrorCode.INTERNAL_ERROR, "failed", "req-1", 500, True)
            if status is OutcomeStatus.FAILED
            else None
        ),
    )
    return apply_outcome_update(state, update).state


def _publication(result_digest: str):
    return ResultPublicationPlan(
        result_fingerprint=result_digest,
        reproduction_fingerprint=content_digest("reproduction"),
        attempt_id=ATTEMPT,
        engine_build_digest=content_digest("engine"),
        decision=ResultPublicationDecision.PUBLISH,
    )


def test_accepted_summary_is_ready_and_identity_bound() -> None:
    summary = build_execution_summary(_receipt(), _outcome(), _progress())
    assert summary.decision is ExecutionSummaryDecision.READY
    assert summary.status is OutcomeStatus.ACCEPTED
    assert summary.operation == "backtest"


def test_running_summary_allows_preparing_running_and_finalizing_progress() -> None:
    running = build_execution_summary(
        _receipt(), _outcome(OutcomeStatus.RUNNING), _progress(ProgressPhase.RUNNING, sequence=1)
    )
    assert running.decision is ExecutionSummaryDecision.IN_PROGRESS


def test_success_summary_requires_published_result_and_is_terminal() -> None:
    outcome = _outcome(OutcomeStatus.SUCCEEDED)
    publication = _publication(outcome.result_digest or "")
    summary = build_execution_summary(
        _receipt(), outcome, _progress(ProgressPhase.SUCCEEDED, sequence=1), publication
    )
    assert summary.decision is ExecutionSummaryDecision.TERMINAL
    assert summary.publication_fingerprint == publication.fingerprint


def test_success_without_publication_or_with_mismatched_result_fails_closed() -> None:
    outcome = _outcome(OutcomeStatus.SUCCEEDED)
    with pytest.raises(ValueError, match="publication"):
        build_execution_summary(_receipt(), outcome, _progress(ProgressPhase.SUCCEEDED, sequence=1))
    with pytest.raises(ValueError, match="match"):
        build_execution_summary(
            _receipt(),
            outcome,
            _progress(ProgressPhase.SUCCEEDED, sequence=1),
            _publication(content_digest("other-result")),
        )


def test_failed_and_cancelled_summaries_require_matching_terminal_progress() -> None:
    failed = build_execution_summary(
        _receipt(), _outcome(OutcomeStatus.FAILED), _progress(ProgressPhase.FAILED, sequence=1)
    )
    assert failed.decision is ExecutionSummaryDecision.TERMINAL
    cancelled = _outcome(OutcomeStatus.CANCELLED)
    cancelled_summary = build_execution_summary(
        _receipt(), cancelled, _progress(ProgressPhase.CANCELLED, sequence=1)
    )
    assert cancelled_summary.status is OutcomeStatus.CANCELLED


def test_status_and_progress_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="inconsistent"):
        outcome = _outcome(OutcomeStatus.SUCCEEDED)
        build_execution_summary(
            _receipt(), outcome, _progress(ProgressPhase.RUNNING, sequence=1), _publication(outcome.result_digest or "")
        )


def test_submission_and_attempt_identity_mismatch_is_rejected() -> None:
    wrong_request = SubmissionRequest(
        "idem-2", "backtest", "other-attempt", content_digest("payload"), NOW
    )
    wrong_receipt = create_submission_receipt(wrong_request, accepted_at=NOW)
    with pytest.raises(ValueError, match="identities"):
        build_execution_summary(wrong_receipt, _outcome(), _progress())


def test_summary_contract_rejects_invalid_digest_and_counts() -> None:
    from app.strategy_lab_v2.execution_summary import ExecutionSummary

    with pytest.raises(ValueError, match="submission_id"):
        ExecutionSummary(
            "bad", ATTEMPT, "backtest", OutcomeStatus.ACCEPTED, 0, ProgressPhase.QUEUED,
            0, 0, 10, False, NOW,
        )
    with pytest.raises(ValueError, match="completed_units"):
        ExecutionSummary(
            content_digest("submission"), ATTEMPT, "backtest", OutcomeStatus.ACCEPTED, 0,
            ProgressPhase.QUEUED, 0, 11, 10, False, NOW,
        )
