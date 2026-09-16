"""Typed asynchronous execution outcomes and idempotent status transitions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.api_contracts import ApiError
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest


class OutcomeStatus(StrEnum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OutcomeDecision(StrEnum):
    APPLY = "apply"
    REPLAY_EXISTING = "replay_existing"
    CONFLICT = "conflict"


_ALLOWED_TRANSITIONS: dict[OutcomeStatus, frozenset[OutcomeStatus]] = {
    OutcomeStatus.ACCEPTED: frozenset(
        {
            OutcomeStatus.ACCEPTED,
            OutcomeStatus.RUNNING,
            OutcomeStatus.SUCCEEDED,
            OutcomeStatus.FAILED,
            OutcomeStatus.CANCELLED,
        }
    ),
    OutcomeStatus.RUNNING: frozenset(
        {OutcomeStatus.RUNNING, OutcomeStatus.SUCCEEDED, OutcomeStatus.FAILED, OutcomeStatus.CANCELLED}
    ),
    OutcomeStatus.SUCCEEDED: frozenset({OutcomeStatus.SUCCEEDED}),
    OutcomeStatus.FAILED: frozenset({OutcomeStatus.FAILED}),
    OutcomeStatus.CANCELLED: frozenset({OutcomeStatus.CANCELLED}),
}


@dataclass(frozen=True, slots=True)
class OutcomeUpdate:
    """One ordered worker/API status observation."""

    submission_id: str
    attempt_id: str
    sequence: int
    status: OutcomeStatus
    observed_at: datetime
    result_digest: str | None = None
    error: ApiError | None = None

    def __post_init__(self) -> None:
        for name in ("submission_id", "attempt_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"outcome {name} must not be empty")
        require_sha256_digest(self.submission_id, field_name="submission_id")
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 1:
            raise ValueError("outcome sequence must be a positive integer")
        if not isinstance(self.status, OutcomeStatus):
            raise TypeError("status must be an OutcomeStatus")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("outcome observed_at must be timezone-aware")
        if self.result_digest is not None:
            require_sha256_digest(self.result_digest, field_name="result_digest")
        if self.error is not None and not isinstance(self.error, ApiError):
            raise TypeError("error must be an ApiError")
        if self.status is OutcomeStatus.SUCCEEDED:
            if self.result_digest is None or self.error is not None:
                raise ValueError("successful outcomes require a result and no error")
        elif self.status in {OutcomeStatus.FAILED, OutcomeStatus.CANCELLED}:
            if self.result_digest is not None:
                raise ValueError("terminal non-success outcomes must not include a result")
        elif self.result_digest is not None or self.error is not None:
            raise ValueError("non-terminal outcomes cannot include a result or error")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    """Latest outcome checkpoint for one accepted submission."""

    submission_id: str
    attempt_id: str
    sequence: int
    status: OutcomeStatus
    updated_at: datetime
    result_digest: str | None = None
    error: ApiError | None = None

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("outcome state sequence must be non-negative")
        if self.sequence == 0:
            if self.status is not OutcomeStatus.ACCEPTED:
                raise ValueError("sequence-zero outcomes must be accepted")
            if self.result_digest is not None or self.error is not None:
                raise ValueError("sequence-zero outcomes cannot contain a result or error")
            if not isinstance(self.submission_id, str) or not self.submission_id.strip():
                raise ValueError("outcome submission_id must not be empty")
            require_sha256_digest(self.submission_id, field_name="submission_id")
            if not isinstance(self.attempt_id, str) or not self.attempt_id.strip():
                raise ValueError("outcome attempt_id must not be empty")
            if self.updated_at.tzinfo is None or self.updated_at.utcoffset() is None:
                raise ValueError("outcome updated_at must be timezone-aware")
            return
        OutcomeUpdate(
            submission_id=self.submission_id,
            attempt_id=self.attempt_id,
            sequence=self.sequence,
            status=self.status,
            observed_at=self.updated_at,
            result_digest=self.result_digest,
            error=self.error,
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class OutcomeResolution:
    decision: OutcomeDecision
    state: ExecutionOutcome

    def __post_init__(self) -> None:
        if not isinstance(self.decision, OutcomeDecision):
            raise TypeError("decision must be an OutcomeDecision")
        if not isinstance(self.state, ExecutionOutcome):
            raise TypeError("state must be an ExecutionOutcome")


def new_execution_outcome(
    submission_id: str, attempt_id: str, *, accepted_at: datetime
) -> ExecutionOutcome:
    """Create a sequence-zero accepted outcome checkpoint."""

    if accepted_at.tzinfo is None or accepted_at.utcoffset() is None:
        raise ValueError("accepted_at must be timezone-aware")
    return ExecutionOutcome(
        submission_id=submission_id,
        attempt_id=attempt_id,
        sequence=0,
        status=OutcomeStatus.ACCEPTED,
        updated_at=accepted_at,
    )


def apply_outcome_update(
    state: ExecutionOutcome, update: OutcomeUpdate
) -> OutcomeResolution:
    """Apply a monotonic status update and make exact repeats idempotent."""

    if not isinstance(state, ExecutionOutcome):
        raise TypeError("state must be an ExecutionOutcome")
    if not isinstance(update, OutcomeUpdate):
        raise TypeError("update must be an OutcomeUpdate")
    if update.submission_id != state.submission_id or update.attempt_id != state.attempt_id:
        raise ValueError("outcome update must reference the same submission and attempt")
    if update.observed_at < state.updated_at:
        raise ValueError("outcome time cannot move backwards")
    if update.sequence <= state.sequence:
        same = (
            update.sequence == state.sequence
            and update.status is state.status
            and update.observed_at == state.updated_at
            and update.result_digest == state.result_digest
            and update.error == state.error
        )
        if same:
            return OutcomeResolution(OutcomeDecision.REPLAY_EXISTING, state)
        raise ValueError("outcome sequence conflicts with the existing state")
    if update.status not in _ALLOWED_TRANSITIONS[state.status]:
        raise ValueError(f"illegal outcome transition: {state.status} -> {update.status}")
    next_state = ExecutionOutcome(
        submission_id=update.submission_id,
        attempt_id=update.attempt_id,
        sequence=update.sequence,
        status=update.status,
        updated_at=update.observed_at,
        result_digest=update.result_digest,
        error=update.error,
    )
    return OutcomeResolution(OutcomeDecision.APPLY, next_state)
