"""Pure progress and cancellation state for resumable execution attempts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest


class ProgressPhase(StrEnum):
    QUEUED = "queued"
    PREPARING = "preparing"
    RUNNING = "running"
    FINALIZING = "finalizing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TERMINAL_PHASES = frozenset(
    {ProgressPhase.SUCCEEDED, ProgressPhase.FAILED, ProgressPhase.CANCELLED}
)


@dataclass(frozen=True, slots=True)
class ExecutionProgressUpdate:
    """One ordered progress observation emitted by a worker."""

    attempt_id: str
    sequence: int
    phase: ProgressPhase
    completed_units: int
    total_units: int
    emitted_at: datetime
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.attempt_id, str) or not self.attempt_id.strip():
            raise ValueError("progress attempt_id must not be empty")
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 1:
            raise ValueError("progress sequence must be a positive integer")
        if not isinstance(self.phase, ProgressPhase):
            raise TypeError("progress phase must be a ProgressPhase")
        for name in ("completed_units", "total_units"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"progress {name} must be a non-negative integer")
        if self.completed_units > self.total_units:
            raise ValueError("progress completed_units cannot exceed total_units")
        if self.emitted_at.tzinfo is None or self.emitted_at.utcoffset() is None:
            raise ValueError("progress emitted_at must be timezone-aware")
        if not isinstance(self.detail, str):
            raise TypeError("progress detail must be a string")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class CancellationRequest:
    """Idempotent user cancellation intent for one attempt."""

    request_id: str
    attempt_id: str
    requested_at: datetime
    reason: str

    def __post_init__(self) -> None:
        for name in ("request_id", "attempt_id", "reason"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"cancellation {name} must not be empty")
        if self.requested_at.tzinfo is None or self.requested_at.utcoffset() is None:
            raise ValueError("cancellation requested_at must be timezone-aware")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ExecutionProgressState:
    """Latest progress checkpoint retained independently of worker transport."""

    attempt_id: str
    sequence: int
    phase: ProgressPhase
    completed_units: int
    total_units: int
    cancellation_requested: bool
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.attempt_id, str) or not self.attempt_id.strip():
            raise ValueError("progress state attempt_id must not be empty")
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 0:
            raise ValueError("progress state sequence must be non-negative")
        if not isinstance(self.phase, ProgressPhase):
            raise TypeError("progress state phase must be a ProgressPhase")
        for name in ("completed_units", "total_units"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"progress state {name} must be a non-negative integer")
        if self.completed_units > self.total_units:
            raise ValueError("progress state completed_units cannot exceed total_units")
        if not isinstance(self.cancellation_requested, bool):
            raise TypeError("progress state cancellation_requested must be a boolean")
        if self.updated_at.tzinfo is None or self.updated_at.utcoffset() is None:
            raise ValueError("progress state updated_at must be timezone-aware")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def new_progress_state(
    attempt_id: str, *, total_units: int, now: datetime
) -> ExecutionProgressState:
    """Create a sequence-zero progress state for a queued attempt."""

    return ExecutionProgressState(
        attempt_id=attempt_id,
        sequence=0,
        phase=ProgressPhase.QUEUED,
        completed_units=0,
        total_units=total_units,
        cancellation_requested=False,
        updated_at=now,
    )


def apply_progress_update(
    state: ExecutionProgressState, update: ExecutionProgressUpdate
) -> ExecutionProgressState:
    """Apply one strictly ordered update while preserving cancellation semantics."""

    if not isinstance(state, ExecutionProgressState):
        raise TypeError("progress state must be an ExecutionProgressState")
    if not isinstance(update, ExecutionProgressUpdate):
        raise TypeError("progress update must be an ExecutionProgressUpdate")
    if update.attempt_id != state.attempt_id:
        raise ValueError("progress update must reference the same attempt")
    if update.sequence <= state.sequence:
        raise ValueError("progress sequence must be strictly increasing")
    if state.phase in _TERMINAL_PHASES:
        raise ValueError("terminal progress state cannot receive updates")
    if update.total_units != state.total_units:
        raise ValueError("progress total_units cannot change")
    if update.completed_units < state.completed_units:
        raise ValueError("progress completed_units cannot move backwards")
    if state.cancellation_requested and update.phase not in {
        ProgressPhase.CANCELLED,
    }:
        raise ValueError("cancelled attempts can only publish a cancelled terminal update")
    if update.phase is ProgressPhase.SUCCEEDED and update.completed_units != update.total_units:
        raise ValueError("successful progress must complete all units")
    return replace(
        state,
        sequence=update.sequence,
        phase=update.phase,
        completed_units=update.completed_units,
        updated_at=update.emitted_at,
    )


def request_cancellation(
    state: ExecutionProgressState, request: CancellationRequest
) -> ExecutionProgressState:
    """Mark cancellation requested; repeating the same intent is idempotent."""

    if not isinstance(state, ExecutionProgressState):
        raise TypeError("progress state must be an ExecutionProgressState")
    if not isinstance(request, CancellationRequest):
        raise TypeError("cancellation request must be a CancellationRequest")
    if request.attempt_id != state.attempt_id:
        raise ValueError("cancellation must reference the same attempt")
    if state.phase in _TERMINAL_PHASES:
        return state
    if request.requested_at < state.updated_at:
        raise ValueError("cancellation time cannot move backwards")
    if state.cancellation_requested:
        return state
    return replace(state, cancellation_requested=True, updated_at=request.requested_at)
