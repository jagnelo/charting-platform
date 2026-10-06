from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.search_state import (
    SearchCandidatePhase,
    SearchExecutionState,
    SearchStateDecision,
    append_search_candidates,
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
    started = start_search_candidate(
        state, 0, attempt_id="attempt-1", now=NOW + timedelta(seconds=1)
    )
    assert started.decision is SearchStateDecision.APPLY
    assert started.state.candidates[0].phase is SearchCandidatePhase.RUNNING
    assert started.state.candidates[0].attempt_count == 1
    replay = start_search_candidate(
        started.state, 0, attempt_id="attempt-1", now=NOW + timedelta(seconds=2)
    )
    assert replay.decision is SearchStateDecision.REPLAY_EXISTING
    assert replay.state == started.state


def test_failed_candidate_can_retry_without_changing_trial_identity() -> None:
    started = start_search_candidate(
        _state(), 0, attempt_id="attempt-1", now=NOW + timedelta(seconds=1)
    )
    failed = record_search_candidate_terminal(
        started.state,
        0,
        attempt_id="attempt-1",
        phase=SearchCandidatePhase.FAILED,
        now=NOW + timedelta(seconds=2),
    )
    retried = start_search_candidate(
        failed.state, 0, attempt_id="attempt-2", now=NOW + timedelta(seconds=3)
    )
    assert retried.decision is SearchStateDecision.APPLY
    assert retried.state.candidates[0].attempt_count == 2
    assert retried.state.candidates[0].trial_fingerprint == _state().candidates[0].trial_fingerprint


def test_success_requires_result_and_terminal_retry_replays() -> None:
    started = start_search_candidate(
        _state(), 0, attempt_id="attempt-1", now=NOW + timedelta(seconds=1)
    )
    result_digest = content_digest("result")
    succeeded = record_search_candidate_terminal(
        started.state,
        0,
        attempt_id="attempt-1",
        phase=SearchCandidatePhase.SUCCEEDED,
        result_fingerprint=result_digest,
        now=NOW + timedelta(seconds=2),
    )
    assert succeeded.state.complete is False
    replay = record_search_candidate_terminal(
        succeeded.state,
        0,
        attempt_id="attempt-1",
        phase=SearchCandidatePhase.SUCCEEDED,
        result_fingerprint=result_digest,
        now=NOW + timedelta(seconds=3),
    )
    assert replay.decision is SearchStateDecision.REPLAY_EXISTING
    with pytest.raises(ValueError, match="result_fingerprint"):
        record_search_candidate_terminal(
            started.state,
            0,
            attempt_id="attempt-1",
            phase=SearchCandidatePhase.SUCCEEDED,
            now=NOW + timedelta(seconds=2),
        )


def test_cancellation_is_idempotent_and_closes_new_starts() -> None:
    started = start_search_candidate(
        _state(), 0, attempt_id="attempt-1", now=NOW + timedelta(seconds=1)
    )
    cancelled = request_search_cancellation(
        started.state, request_id=content_digest("cancel"), now=NOW + timedelta(seconds=2)
    )
    assert cancelled.decision is SearchStateDecision.APPLY
    replay = request_search_cancellation(
        cancelled.state, request_id=content_digest("cancel"), now=NOW + timedelta(seconds=3)
    )
    assert replay.decision is SearchStateDecision.REPLAY_EXISTING
    rejected = start_search_candidate(
        cancelled.state, 1, attempt_id="attempt-2", now=NOW + timedelta(seconds=3)
    )
    assert rejected.decision is SearchStateDecision.REJECT
    assert "cancellation" in (rejected.rejection_reason or "")


def test_cancelled_search_requires_cancelled_terminal_receipts() -> None:
    started = start_search_candidate(
        _state(), 0, attempt_id="attempt-1", now=NOW + timedelta(seconds=1)
    )
    cancelled = request_search_cancellation(
        started.state, request_id=content_digest("cancel"), now=NOW + timedelta(seconds=2)
    )
    rejected = record_search_candidate_terminal(
        cancelled.state,
        0,
        attempt_id="attempt-1",
        phase=SearchCandidatePhase.FAILED,
        now=NOW + timedelta(seconds=3),
    )
    assert rejected.decision is SearchStateDecision.REJECT
    applied = record_search_candidate_terminal(
        cancelled.state,
        0,
        attempt_id="attempt-1",
        phase=SearchCandidatePhase.CANCELLED,
        now=NOW + timedelta(seconds=3),
    )
    assert applied.decision is SearchStateDecision.APPLY


def test_active_attempt_conflict_and_terminal_conflict_are_explicit() -> None:
    started = start_search_candidate(
        _state(), 0, attempt_id="attempt-1", now=NOW + timedelta(seconds=1)
    )
    conflict = start_search_candidate(
        started.state, 0, attempt_id="attempt-2", now=NOW + timedelta(seconds=2)
    )
    assert conflict.decision is SearchStateDecision.REJECT
    terminal = record_search_candidate_terminal(
        started.state,
        0,
        attempt_id="attempt-1",
        phase=SearchCandidatePhase.FAILED,
        now=NOW + timedelta(seconds=2),
    )
    changed = record_search_candidate_terminal(
        terminal.state,
        0,
        attempt_id="attempt-2",
        phase=SearchCandidatePhase.SUCCEEDED,
        result_fingerprint=content_digest("changed"),
        now=NOW + timedelta(seconds=3),
    )
    assert changed.decision is SearchStateDecision.REJECT


def test_state_rejects_duplicate_trials_and_noncontiguous_candidates() -> None:
    with pytest.raises(ValueError, match="unique"):
        new_search_execution_state(
            content_digest("experiment"), (content_digest("same"), content_digest("same"))
        )
    with pytest.raises(ValueError, match="contiguous"):
        SearchExecutionState(
            content_digest("experiment"),
            (
                _state(1).candidates[0],
                _state(1).candidates[0],
            ),
        )


def test_completed_search_phase_appends_stable_indices_with_exact_replay() -> None:
    state = _state()
    for index in range(len(state.candidates)):
        attempt_id = f"training-{index}"
        started = start_search_candidate(
            state, index, attempt_id=attempt_id, now=NOW + timedelta(seconds=index + 1)
        )
        terminal = record_search_candidate_terminal(
            started.state,
            index,
            attempt_id=attempt_id,
            phase=SearchCandidatePhase.SUCCEEDED,
            now=NOW + timedelta(seconds=index + 2),
            result_fingerprint=content_digest({"result": index}),
        )
        state = terminal.state

    oos_trials = (content_digest("oos-1"), content_digest("oos-2"))
    appended = append_search_candidates(state, oos_trials, now=NOW + timedelta(seconds=5))

    assert appended.decision is SearchStateDecision.APPLY
    assert appended.candidate_index == len(state.candidates)
    assert [candidate.candidate_index for candidate in appended.state.candidates] == [0, 1, 2, 3]
    assert [candidate.trial_fingerprint for candidate in appended.state.candidates[-2:]] == list(
        oos_trials
    )
    replay = append_search_candidates(appended.state, oos_trials, now=NOW + timedelta(seconds=6))
    assert replay.decision is SearchStateDecision.REPLAY_EXISTING
    assert replay.state == appended.state


def test_search_phase_append_fails_closed_before_success_or_after_cancellation() -> None:
    state = _state()
    pending = append_search_candidates(
        state, (content_digest("oos"),), now=NOW + timedelta(seconds=1)
    )
    assert pending.decision is SearchStateDecision.REJECT
    assert "succeeds" in (pending.rejection_reason or "")

    started = start_search_candidate(
        state, 0, attempt_id="attempt-1", now=NOW + timedelta(seconds=1)
    )
    failed = record_search_candidate_terminal(
        started.state,
        0,
        attempt_id="attempt-1",
        phase=SearchCandidatePhase.FAILED,
        now=NOW + timedelta(seconds=2),
    )
    # The remaining task is closed to make the prior phase complete, but a
    # failed training result can never authorize an OOS phase.
    other_start = start_search_candidate(
        failed.state, 1, attempt_id="attempt-2", now=NOW + timedelta(seconds=3)
    )
    other_done = record_search_candidate_terminal(
        other_start.state,
        1,
        attempt_id="attempt-2",
        phase=SearchCandidatePhase.SUCCEEDED,
        now=NOW + timedelta(seconds=4),
        result_fingerprint=content_digest("other-result"),
    )
    failed_phase = append_search_candidates(
        other_done.state, (content_digest("oos"),), now=NOW + timedelta(seconds=5)
    )
    assert failed_phase.decision is SearchStateDecision.REJECT

    cancelled_state = _state(1)
    active = start_search_candidate(
        cancelled_state, 0, attempt_id="active", now=NOW + timedelta(seconds=1)
    )
    cancelled = request_search_cancellation(
        active.state, request_id=content_digest("cancel"), now=NOW + timedelta(seconds=2)
    )
    rejected = append_search_candidates(
        cancelled.state, (content_digest("oos"),), now=NOW + timedelta(seconds=3)
    )
    assert rejected.decision is SearchStateDecision.REJECT
    assert "cancelled" in (rejected.rejection_reason or "")
