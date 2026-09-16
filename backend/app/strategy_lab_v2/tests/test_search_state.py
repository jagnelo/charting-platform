from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.search_state import (
    SearchCandidatePhase,
    SearchExecutionState,
    SearchStateDecision,
    new_search_execution_state,
    record_search_candidate_terminal,
    request_search_cancellation,
    start_search_candidate,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _state(count: int = 2):
    return new_search_execution_state(
        content_digest("experiment"),
        tuple(content_digest({"trial": index}) for index in range(count)),
        now=NOW,
    )


def test_candidate_start_and_exact_retry_are_resumable() -> None:
    state = _state()
    started = start_search_candidate(state, 0, attempt_id="attempt-1", now=NOW + timedelta(seconds=1))
    assert started.decision is SearchStateDecision.APPLY
    assert started.state.candidates[0].phase is SearchCandidatePhase.RUNNING
    assert started.state.candidates[0].attempt_count == 1
    replay = start_search_candidate(started.state, 0, attempt_id="attempt-1", now=NOW + timedelta(seconds=2))
    assert replay.decision is SearchStateDecision.REPLAY_EXISTING
    assert replay.state == started.state


def test_failed_candidate_can_retry_without_changing_trial_identity() -> None:
    started = start_search_candidate(_state(), 0, attempt_id="attempt-1", now=NOW + timedelta(seconds=1))
    failed = record_search_candidate_terminal(
        started.state, 0, attempt_id="attempt-1", phase=SearchCandidatePhase.FAILED, now=NOW + timedelta(seconds=2)
    )
    retried = start_search_candidate(failed.state, 0, attempt_id="attempt-2", now=NOW + timedelta(seconds=3))
    assert retried.decision is SearchStateDecision.APPLY
    assert retried.state.candidates[0].attempt_count == 2
    assert retried.state.candidates[0].trial_fingerprint == _state().candidates[0].trial_fingerprint


def test_success_requires_result_and_terminal_retry_replays() -> None:
    started = start_search_candidate(_state(), 0, attempt_id="attempt-1", now=NOW + timedelta(seconds=1))
    result_digest = content_digest("result")
    succeeded = record_search_candidate_terminal(
        started.state, 0, attempt_id="attempt-1", phase=SearchCandidatePhase.SUCCEEDED,
        result_fingerprint=result_digest, now=NOW + timedelta(seconds=2),
    )
    assert succeeded.state.complete is False
    replay = record_search_candidate_terminal(
        succeeded.state, 0, attempt_id="attempt-1", phase=SearchCandidatePhase.SUCCEEDED,
        result_fingerprint=result_digest, now=NOW + timedelta(seconds=3),
    )
    assert replay.decision is SearchStateDecision.REPLAY_EXISTING
    with pytest.raises(ValueError, match="result_fingerprint"):
        record_search_candidate_terminal(
            started.state, 0, attempt_id="attempt-1", phase=SearchCandidatePhase.SUCCEEDED,
            now=NOW + timedelta(seconds=2),
        )


def test_cancellation_is_idempotent_and_closes_new_starts() -> None:
    started = start_search_candidate(_state(), 0, attempt_id="attempt-1", now=NOW + timedelta(seconds=1))
    cancelled = request_search_cancellation(
        started.state, request_id=content_digest("cancel"), now=NOW + timedelta(seconds=2)
    )
    assert cancelled.decision is SearchStateDecision.APPLY
    replay = request_search_cancellation(
        cancelled.state, request_id=content_digest("cancel"), now=NOW + timedelta(seconds=3)
    )
    assert replay.decision is SearchStateDecision.REPLAY_EXISTING
    rejected = start_search_candidate(cancelled.state, 1, attempt_id="attempt-2", now=NOW + timedelta(seconds=3))
    assert rejected.decision is SearchStateDecision.REJECT
    assert "cancellation" in (rejected.rejection_reason or "")


def test_cancelled_search_requires_cancelled_terminal_receipts() -> None:
    started = start_search_candidate(_state(), 0, attempt_id="attempt-1", now=NOW + timedelta(seconds=1))
    cancelled = request_search_cancellation(
        started.state, request_id=content_digest("cancel"), now=NOW + timedelta(seconds=2)
    )
    rejected = record_search_candidate_terminal(
        cancelled.state, 0, attempt_id="attempt-1", phase=SearchCandidatePhase.FAILED, now=NOW + timedelta(seconds=3)
    )
    assert rejected.decision is SearchStateDecision.REJECT
    applied = record_search_candidate_terminal(
        cancelled.state, 0, attempt_id="attempt-1", phase=SearchCandidatePhase.CANCELLED, now=NOW + timedelta(seconds=3)
    )
    assert applied.decision is SearchStateDecision.APPLY


def test_active_attempt_conflict_and_terminal_conflict_are_explicit() -> None:
    started = start_search_candidate(_state(), 0, attempt_id="attempt-1", now=NOW + timedelta(seconds=1))
    conflict = start_search_candidate(started.state, 0, attempt_id="attempt-2", now=NOW + timedelta(seconds=2))
    assert conflict.decision is SearchStateDecision.REJECT
    terminal = record_search_candidate_terminal(
        started.state, 0, attempt_id="attempt-1", phase=SearchCandidatePhase.FAILED, now=NOW + timedelta(seconds=2)
    )
    changed = record_search_candidate_terminal(
        terminal.state, 0, attempt_id="attempt-2", phase=SearchCandidatePhase.SUCCEEDED,
        result_fingerprint=content_digest("changed"), now=NOW + timedelta(seconds=3),
    )
    assert changed.decision is SearchStateDecision.REJECT


def test_state_rejects_duplicate_trials_and_noncontiguous_candidates() -> None:
    with pytest.raises(ValueError, match="unique"):
        new_search_execution_state(content_digest("experiment"), (content_digest("same"), content_digest("same")))
    with pytest.raises(ValueError, match="contiguous"):
        SearchExecutionState(
            content_digest("experiment"),
            (
                _state(1).candidates[0],
                _state(1).candidates[0],
            ),
        )

