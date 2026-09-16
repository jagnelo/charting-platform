"""Immutable API read model for one submission's execution status."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.api_contracts import ApiError
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.outcomes import ExecutionOutcome, OutcomeStatus
from app.strategy_lab_v2.progress import ExecutionProgressState, ProgressPhase
from app.strategy_lab_v2.result_publication import (
    ResultPublicationDecision,
    ResultPublicationPlan,
)
from app.strategy_lab_v2.submissions import SubmissionReceipt


class ExecutionSummaryDecision(StrEnum):
    READY = "ready"
    IN_PROGRESS = "in_progress"
    TERMINAL = "terminal"


@dataclass(frozen=True, slots=True)
class ExecutionSummary:
    """Stable machine-facing projection with no mutable engine handles."""

    submission_id: str
    attempt_id: str
    operation: str
    status: OutcomeStatus
    outcome_sequence: int
    progress_phase: ProgressPhase
    progress_sequence: int
    completed_units: int
    total_units: int
    cancellation_requested: bool
    updated_at: datetime
    result_digest: str | None = None
    publication_fingerprint: str | None = None
    error: ApiError | None = None

    def __post_init__(self) -> None:
        require_sha256_digest(self.submission_id, field_name="submission_id")
        if not isinstance(self.attempt_id, str) or not self.attempt_id.strip():
            raise ValueError("attempt_id must not be empty")
        if not isinstance(self.operation, str) or not self.operation.strip():
            raise ValueError("operation must not be empty")
        if not isinstance(self.status, OutcomeStatus):
            raise TypeError("status must be an OutcomeStatus")
        if not isinstance(self.progress_phase, ProgressPhase):
            raise TypeError("progress_phase must be a ProgressPhase")
        for name in ("outcome_sequence", "progress_sequence", "completed_units", "total_units"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.completed_units > self.total_units:
            raise ValueError("completed_units cannot exceed total_units")
        if not isinstance(self.cancellation_requested, bool):
            raise TypeError("cancellation_requested must be a boolean")
        if self.updated_at.tzinfo is None or self.updated_at.utcoffset() is None:
            raise ValueError("updated_at must be timezone-aware")
        if self.result_digest is not None:
            require_sha256_digest(self.result_digest, field_name="result_digest")
        if self.publication_fingerprint is not None:
            require_sha256_digest(
                self.publication_fingerprint, field_name="publication_fingerprint"
            )
        if self.error is not None and not isinstance(self.error, ApiError):
            raise TypeError("error must be an ApiError")
        if self.status is OutcomeStatus.SUCCEEDED:
            if self.result_digest is None or self.publication_fingerprint is None:
                raise ValueError("successful summaries require a published result")
            if self.progress_phase is not ProgressPhase.SUCCEEDED:
                raise ValueError("successful summaries require succeeded progress")
        elif self.status is OutcomeStatus.FAILED:
            if self.result_digest is not None or self.publication_fingerprint is not None:
                raise ValueError("failed summaries cannot contain a result")
            if self.progress_phase is not ProgressPhase.FAILED:
                raise ValueError("failed summaries require failed progress")
        elif self.status is OutcomeStatus.CANCELLED:
            if self.result_digest is not None or self.publication_fingerprint is not None:
                raise ValueError("cancelled summaries cannot contain a result")
            if self.progress_phase is not ProgressPhase.CANCELLED:
                raise ValueError("cancelled summaries require cancelled progress")
        elif self.publication_fingerprint is not None:
            raise ValueError("non-terminal summaries cannot contain publication identity")

    @property
    def decision(self) -> ExecutionSummaryDecision:
        if self.status in {
            OutcomeStatus.SUCCEEDED,
            OutcomeStatus.FAILED,
            OutcomeStatus.CANCELLED,
        }:
            return ExecutionSummaryDecision.TERMINAL
        if self.status is OutcomeStatus.RUNNING:
            return ExecutionSummaryDecision.IN_PROGRESS
        return ExecutionSummaryDecision.READY

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def build_execution_summary(
    receipt: SubmissionReceipt,
    outcome: ExecutionOutcome,
    progress: ExecutionProgressState,
    publication: ResultPublicationPlan | None = None,
) -> ExecutionSummary:
    """Project consistent submission/outcome/progress records into one view."""

    if not isinstance(receipt, SubmissionReceipt):
        raise TypeError("receipt must be a SubmissionReceipt")
    if not isinstance(outcome, ExecutionOutcome):
        raise TypeError("outcome must be an ExecutionOutcome")
    if not isinstance(progress, ExecutionProgressState):
        raise TypeError("progress must be an ExecutionProgressState")
    if publication is not None and not isinstance(publication, ResultPublicationPlan):
        raise TypeError("publication must be a ResultPublicationPlan")
    if receipt.submission_id != outcome.submission_id:
        raise ValueError("submission receipt and outcome identities must match")
    if receipt.request.attempt_id != outcome.attempt_id or progress.attempt_id != outcome.attempt_id:
        raise ValueError("submission, outcome, and progress attempts must match")
    allowed_progress = {
        OutcomeStatus.ACCEPTED: frozenset({ProgressPhase.QUEUED}),
        OutcomeStatus.RUNNING: frozenset(
            {ProgressPhase.QUEUED, ProgressPhase.PREPARING, ProgressPhase.RUNNING, ProgressPhase.FINALIZING}
        ),
        OutcomeStatus.SUCCEEDED: frozenset({ProgressPhase.SUCCEEDED}),
        OutcomeStatus.FAILED: frozenset({ProgressPhase.FAILED}),
        OutcomeStatus.CANCELLED: frozenset({ProgressPhase.CANCELLED}),
    }
    if progress.phase not in allowed_progress[outcome.status]:
        raise ValueError("outcome status and progress phase are inconsistent")
    if outcome.status is OutcomeStatus.SUCCEEDED:
        if publication is None:
            raise ValueError("successful outcome requires an accepted publication plan")
        if publication.decision not in {
            ResultPublicationDecision.PUBLISH,
            ResultPublicationDecision.REPLAY_EXISTING,
        }:
            raise ValueError("successful outcome requires an accepted publication plan")
        if outcome.result_digest != publication.result_fingerprint:
            raise ValueError("publication result must match the successful outcome")
    elif publication is not None:
        raise ValueError("publication is only valid for a successful outcome")
    return ExecutionSummary(
        submission_id=outcome.submission_id,
        attempt_id=outcome.attempt_id,
        operation=receipt.request.operation,
        status=outcome.status,
        outcome_sequence=outcome.sequence,
        progress_phase=progress.phase,
        progress_sequence=progress.sequence,
        completed_units=progress.completed_units,
        total_units=progress.total_units,
        cancellation_requested=progress.cancellation_requested,
        updated_at=max(receipt.accepted_at, outcome.updated_at, progress.updated_at),
        result_digest=outcome.result_digest,
        publication_fingerprint=publication.fingerprint if publication is not None else None,
        error=outcome.error,
    )
