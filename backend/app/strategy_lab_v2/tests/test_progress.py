from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.strategy_lab_v2.progress import (
    CancellationRequest,
    ExecutionProgressUpdate,
    ProgressPhase,
    apply_progress_update,
    new_progress_state,
    request_cancellation,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def test_progress_updates_are_monotonic_and_terminal_success_is_complete() -> None:
    state = new_progress_state("attempt-1", total_units=10, now=NOW)
    preparing = apply_progress_update(
        state,
        ExecutionProgressUpdate("attempt-1", 1, ProgressPhase.PREPARING, 0, 10, NOW),
    )
    running = apply_progress_update(
        preparing,
        ExecutionProgressUpdate("attempt-1", 2, ProgressPhase.RUNNING, 5, 10, NOW + timedelta(seconds=1)),
    )
    succeeded = apply_progress_update(
        running,
        ExecutionProgressUpdate("attempt-1", 3, ProgressPhase.SUCCEEDED, 10, 10, NOW + timedelta(seconds=2)),
    )
    assert succeeded.phase is ProgressPhase.SUCCEEDED
    with pytest.raises(ValueError, match="terminal"):
        apply_progress_update(
            succeeded,
            ExecutionProgressUpdate("attempt-1", 4, ProgressPhase.FAILED, 10, 10, NOW + timedelta(seconds=3)),
        )


def test_progress_lifecycle_times_normalize_to_utc_for_identity() -> None:
    offset = timezone(timedelta(hours=2))
    state = new_progress_state(
        "attempt-1",
        total_units=10,
        now=(NOW + timedelta(hours=2)).replace(tzinfo=offset),
    )
    canonical = new_progress_state("attempt-1", total_units=10, now=NOW)
    assert state.updated_at == canonical.updated_at
    update = ExecutionProgressUpdate(
        "attempt-1",
        1,
        ProgressPhase.RUNNING,
        1,
        10,
        (NOW + timedelta(hours=2, seconds=1)).replace(tzinfo=offset),
    )
    canonical_update = replace(update, emitted_at=NOW + timedelta(seconds=1))
    assert update.emitted_at == canonical_update.emitted_at
    assert update.fingerprint == canonical_update.fingerprint


def test_progress_updates_reject_reordering_totals_and_incomplete_success() -> None:
    state = new_progress_state("attempt-1", total_units=10, now=NOW)
    update = ExecutionProgressUpdate("attempt-1", 2, ProgressPhase.RUNNING, 5, 10, NOW)
    progressed = apply_progress_update(state, update)
    with pytest.raises(ValueError, match="strictly increasing"):
        apply_progress_update(progressed, update)
    with pytest.raises(ValueError, match="cannot change"):
        apply_progress_update(
            progressed,
            ExecutionProgressUpdate("attempt-1", 3, ProgressPhase.RUNNING, 6, 11, NOW),
        )
    with pytest.raises(ValueError, match="complete all"):
        apply_progress_update(
            progressed,
            ExecutionProgressUpdate("attempt-1", 3, ProgressPhase.SUCCEEDED, 9, 10, NOW),
        )


def test_cancellation_is_idempotent_and_requires_cancelled_terminal_update() -> None:
    state = new_progress_state("attempt-1", total_units=10, now=NOW)
    request = CancellationRequest("cancel-1", "attempt-1", NOW + timedelta(seconds=1), "user requested")
    cancelled = request_cancellation(state, request)
    assert cancelled.cancellation_requested
    assert request_cancellation(cancelled, request) == cancelled
    with pytest.raises(ValueError, match="cancelled terminal"):
        apply_progress_update(
            cancelled,
            ExecutionProgressUpdate("attempt-1", 1, ProgressPhase.RUNNING, 0, 10, NOW + timedelta(seconds=2)),
        )
    final = apply_progress_update(
        cancelled,
        ExecutionProgressUpdate("attempt-1", 1, ProgressPhase.CANCELLED, 0, 10, NOW + timedelta(seconds=2)),
    )
    assert final.phase is ProgressPhase.CANCELLED


def test_cancellation_and_progress_must_reference_the_same_attempt() -> None:
    state = new_progress_state("attempt-1", total_units=1, now=NOW)
    with pytest.raises(ValueError, match="same attempt"):
        request_cancellation(
            state,
            CancellationRequest("cancel-1", "attempt-2", NOW, "wrong attempt"),
        )
    with pytest.raises(ValueError, match="same attempt"):
        apply_progress_update(
            state,
            ExecutionProgressUpdate("attempt-2", 1, ProgressPhase.RUNNING, 0, 1, NOW),
        )
