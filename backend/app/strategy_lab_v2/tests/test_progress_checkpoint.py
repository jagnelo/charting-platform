from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.progress import (
    ExecutionProgressUpdate,
    ProgressPhase,
    new_progress_state,
)
from app.strategy_lab_v2.progress_checkpoint import (
    ProgressCheckpoint,
    ProgressCheckpointDecision,
    apply_progress_checkpoint,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _update(sequence: int, completed: int, phase: ProgressPhase = ProgressPhase.RUNNING) -> ExecutionProgressUpdate:
    return ExecutionProgressUpdate(
        attempt_id="attempt-1",
        sequence=sequence,
        phase=phase,
        completed_units=completed,
        total_units=10,
        emitted_at=NOW + timedelta(seconds=sequence),
    )


def test_progress_checkpoint_applies_contiguous_updates_and_replays_exact_retries() -> None:
    checkpoint = ProgressCheckpoint(new_progress_state("attempt-1", total_units=10, now=NOW))
    first = _update(1, 2)
    applied = apply_progress_checkpoint(checkpoint, first)
    assert applied.decision is ProgressCheckpointDecision.APPLY
    assert applied.checkpoint.state.sequence == 1
    replay = apply_progress_checkpoint(applied.checkpoint, first)
    assert replay.decision is ProgressCheckpointDecision.REPLAY_EXISTING
    assert replay.checkpoint == applied.checkpoint
    assert applied.checkpoint.fingerprint.startswith("sha256:")


def test_progress_checkpoint_surfaces_gaps_and_stale_conflicts_without_advancing() -> None:
    checkpoint = ProgressCheckpoint(new_progress_state("attempt-1", total_units=10, now=NOW))
    gap = apply_progress_checkpoint(checkpoint, _update(2, 2))
    assert gap.decision is ProgressCheckpointDecision.GAP
    assert gap.expected_sequence == 1
    assert gap.checkpoint == checkpoint
    applied = apply_progress_checkpoint(checkpoint, _update(1, 1)).checkpoint
    stale = apply_progress_checkpoint(applied, _update(1, 2))
    assert stale.decision is ProgressCheckpointDecision.CONFLICT
    assert stale.checkpoint == applied


def test_progress_checkpoint_requires_same_attempt_and_preserves_terminal_replay() -> None:
    checkpoint = ProgressCheckpoint(new_progress_state("attempt-1", total_units=10, now=NOW))
    with pytest.raises(ValueError, match="checkpoint attempt"):
        apply_progress_checkpoint(
            checkpoint,
            ExecutionProgressUpdate(
                "other-attempt", 1, ProgressPhase.RUNNING, 1, 10, NOW + timedelta(seconds=1)
            ),
        )
    terminal = _update(1, 10, ProgressPhase.SUCCEEDED)
    applied = apply_progress_checkpoint(checkpoint, terminal).checkpoint
    replay = apply_progress_checkpoint(applied, terminal)
    assert replay.decision is ProgressCheckpointDecision.REPLAY_EXISTING


def test_progress_checkpoint_validates_retained_update_identity_invariant() -> None:
    state = new_progress_state("attempt-1", total_units=10, now=NOW)
    with pytest.raises(ValueError, match="retain every"):
        ProgressCheckpoint(
            state=state.__class__(
                attempt_id=state.attempt_id,
                sequence=1,
                phase=ProgressPhase.RUNNING,
                completed_units=1,
                total_units=10,
                cancellation_requested=False,
                updated_at=NOW + timedelta(seconds=1),
            ),
            applied_update_fingerprints=frozenset(),
        )
