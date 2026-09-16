"""Restart-safe progress checkpoints with explicit gap/conflict decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.progress import (
    ExecutionProgressState,
    ExecutionProgressUpdate,
    apply_progress_update,
)


@dataclass(frozen=True, slots=True)
class ProgressCheckpoint:
    """Latest progress state plus update identities retained for replay."""

    state: ExecutionProgressState
    applied_update_fingerprints: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.state, ExecutionProgressState):
            raise TypeError("checkpoint state must be an ExecutionProgressState")
        fingerprints = frozenset(self.applied_update_fingerprints)
        for fingerprint in fingerprints:
            require_sha256_digest(fingerprint, field_name="applied_update_fingerprint")
        if len(fingerprints) < self.state.sequence:
            raise ValueError("checkpoint must retain every applied progress update identity")
        object.__setattr__(self, "applied_update_fingerprints", fingerprints)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class ProgressCheckpointDecision(StrEnum):
    APPLY = "apply"
    REPLAY_EXISTING = "replay_existing"
    GAP = "gap"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class ProgressCheckpointResolution:
    decision: ProgressCheckpointDecision
    checkpoint: ProgressCheckpoint
    expected_sequence: int

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ProgressCheckpointDecision):
            raise TypeError("decision must be a ProgressCheckpointDecision")
        if not isinstance(self.checkpoint, ProgressCheckpoint):
            raise TypeError("checkpoint must be a ProgressCheckpoint")
        if not isinstance(self.expected_sequence, int) or isinstance(
            self.expected_sequence, bool
        ):
            raise ValueError("expected_sequence must be an integer")
        if self.expected_sequence < 1:
            raise ValueError("expected_sequence must be positive")


def apply_progress_checkpoint(
    checkpoint: ProgressCheckpoint,
    update: ExecutionProgressUpdate,
) -> ProgressCheckpointResolution:
    """Resolve one ordered progress update without mutating the checkpoint."""

    if not isinstance(checkpoint, ProgressCheckpoint):
        raise TypeError("checkpoint must be a ProgressCheckpoint")
    if not isinstance(update, ExecutionProgressUpdate):
        raise TypeError("update must be an ExecutionProgressUpdate")
    if update.attempt_id != checkpoint.state.attempt_id:
        raise ValueError("progress update must reference the checkpoint attempt")
    expected = checkpoint.state.sequence + 1
    if update.fingerprint in checkpoint.applied_update_fingerprints:
        return ProgressCheckpointResolution(
            ProgressCheckpointDecision.REPLAY_EXISTING,
            checkpoint,
            expected,
        )
    if update.sequence < expected:
        return ProgressCheckpointResolution(
            ProgressCheckpointDecision.CONFLICT,
            checkpoint,
            expected,
        )
    if update.sequence > expected:
        return ProgressCheckpointResolution(
            ProgressCheckpointDecision.GAP,
            checkpoint,
            expected,
        )
    next_state = apply_progress_update(checkpoint.state, update)
    next_checkpoint = ProgressCheckpoint(
        state=next_state,
        applied_update_fingerprints=checkpoint.applied_update_fingerprints
        | {update.fingerprint},
    )
    return ProgressCheckpointResolution(
        ProgressCheckpointDecision.APPLY,
        next_checkpoint,
        expected,
    )
