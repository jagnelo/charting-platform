"""Atomic projection of terminal runtime evidence to public execution state.

Runtime process receipts and the public API outcome/progress records are
separate monotonic streams.  This module resolves their terminal projection as
one storage-neutral decision so an adapter cannot publish a successful outcome
without an official result manifest or leave outcome and progress disagreeing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.api_contracts import ApiError
from app.strategy_lab_v2.contracts import RunResultManifest
from app.strategy_lab_v2.outcomes import (
    ExecutionOutcome,
    OutcomeStatus,
    OutcomeUpdate,
    apply_outcome_update,
)
from app.strategy_lab_v2.progress import (
    ExecutionProgressState,
    ExecutionProgressUpdate,
    ProgressPhase,
    apply_progress_update,
)
from app.strategy_lab_v2.runtime_execution import (
    RuntimeExecutionPhase,
    RuntimeExecutionState,
)
from app.strategy_lab_v2.submissions import SubmissionReceipt


class ExecutionTerminalDecision(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REPLAY_EXISTING = "replay_existing"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class ExecutionTerminalResolution:
    """Proposed public outcome and progress states for one terminal receipt."""

    decision: ExecutionTerminalDecision
    outcome: ExecutionOutcome
    progress: ExecutionProgressState
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ExecutionTerminalDecision):
            raise TypeError("decision must be an ExecutionTerminalDecision")
        if not isinstance(self.outcome, ExecutionOutcome):
            raise TypeError("outcome must be an ExecutionOutcome")
        if not isinstance(self.progress, ExecutionProgressState):
            raise TypeError("progress must be an ExecutionProgressState")
        if self.decision is ExecutionTerminalDecision.REJECT and not self.rejection_reason:
            raise ValueError("rejected terminal resolutions require a reason")
        if self.decision is not ExecutionTerminalDecision.REJECT and self.rejection_reason:
            raise ValueError("accepted terminal resolutions cannot contain a reason")

    @property
    def fingerprint(self) -> str:
        from app.strategy_lab_v2.canonical import content_digest

        return content_digest(self)


def materialize_execution_terminal(
    receipt: SubmissionReceipt,
    runtime_state: RuntimeExecutionState,
    outcome: ExecutionOutcome,
    progress: ExecutionProgressState,
    *,
    result: RunResultManifest | None = None,
    error: ApiError | None = None,
    observed_at: datetime,
) -> ExecutionTerminalResolution:
    """Project one terminal runtime state into outcome and progress together.

    A successful runtime requires a typed result manifest, while failed and
    cancelled runtimes must not carry one.  Existing matching terminal states
    replay idempotently; contradictory or half-terminal state returns the
    original state with a rejection reason.
    """

    values = (receipt, runtime_state, outcome, progress)
    expected = (
        SubmissionReceipt,
        RuntimeExecutionState,
        ExecutionOutcome,
        ExecutionProgressState,
    )
    names = ("receipt", "runtime_state", "outcome", "progress")
    for name, value, expected_type in zip(names, values, expected, strict=True):
        if not isinstance(value, expected_type):
            raise TypeError(f"{name} must be a {expected_type.__name__}")
    if result is not None and not isinstance(result, RunResultManifest):
        raise TypeError("result must be a RunResultManifest")
    if error is not None and not isinstance(error, ApiError):
        raise TypeError("error must be an ApiError")
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")

    if receipt.submission_id != outcome.submission_id:
        return _reject(outcome, progress, "submission and outcome identities differ")
    if receipt.request.attempt_id != runtime_state.attempt_id:
        return _reject(outcome, progress, "submission and runtime attempts differ")
    if outcome.attempt_id != runtime_state.attempt_id or progress.attempt_id != runtime_state.attempt_id:
        return _reject(outcome, progress, "terminal records reference different attempts")
    if observed_at < max(runtime_state.updated_at, outcome.updated_at, progress.updated_at):
        return _reject(outcome, progress, "terminal observation time cannot move backwards")
    if runtime_state.phase is RuntimeExecutionPhase.SUCCEEDED:
        desired_outcome = OutcomeStatus.SUCCEEDED
        desired_progress = ProgressPhase.SUCCEEDED
        if result is None or error is not None:
            return _reject(outcome, progress, "successful runtime requires a result and no error")
        if result.attempt_id != runtime_state.attempt_id:
            return _reject(outcome, progress, "result manifest references a different attempt")
        result_digest = result.fingerprint
        if runtime_state.phase is RuntimeExecutionPhase.SUCCEEDED and runtime_state.output_digest is None:
            return _reject(outcome, progress, "successful runtime is missing output evidence")
        if progress.cancellation_requested:
            return _reject(outcome, progress, "cancelled execution cannot succeed")
    elif runtime_state.phase is RuntimeExecutionPhase.FAILED:
        desired_outcome = OutcomeStatus.FAILED
        desired_progress = ProgressPhase.FAILED
        if error is None or result is not None:
            return _reject(outcome, progress, "failed runtime requires an error and no result")
        result_digest = None
        if progress.cancellation_requested:
            return _reject(outcome, progress, "cancelled execution cannot fail")
    elif runtime_state.phase is RuntimeExecutionPhase.CANCELLED:
        desired_outcome = OutcomeStatus.CANCELLED
        desired_progress = ProgressPhase.CANCELLED
        if error is not None or result is not None:
            return _reject(outcome, progress, "cancelled runtime cannot contain result or error")
        if not progress.cancellation_requested:
            return _reject(outcome, progress, "cancelled runtime requires a cancellation request")
        result_digest = None
    else:
        return _reject(outcome, progress, "runtime execution is not terminal")

    if outcome.status in {
        OutcomeStatus.SUCCEEDED,
        OutcomeStatus.FAILED,
        OutcomeStatus.CANCELLED,
    } or progress.phase in {
        ProgressPhase.SUCCEEDED,
        ProgressPhase.FAILED,
        ProgressPhase.CANCELLED,
    }:
        if outcome.status is desired_outcome and progress.phase is desired_progress:
            if desired_outcome is OutcomeStatus.SUCCEEDED and outcome.result_digest == result_digest:
                return ExecutionTerminalResolution(
                    ExecutionTerminalDecision.REPLAY_EXISTING, outcome, progress
                )
            if desired_outcome is OutcomeStatus.FAILED and outcome.error == error:
                return ExecutionTerminalResolution(
                    ExecutionTerminalDecision.REPLAY_EXISTING, outcome, progress
                )
            if desired_outcome is OutcomeStatus.CANCELLED and outcome.error is None:
                return ExecutionTerminalResolution(
                    ExecutionTerminalDecision.REPLAY_EXISTING, outcome, progress
                )
        return _reject(outcome, progress, "terminal outcome and progress conflict with runtime")

    try:
        outcome_resolution = apply_outcome_update(
            outcome,
            OutcomeUpdate(
                submission_id=outcome.submission_id,
                attempt_id=outcome.attempt_id,
                sequence=outcome.sequence + 1,
                status=desired_outcome,
                observed_at=observed_at,
                result_digest=result_digest,
                error=error,
            ),
        )
        progress_state = apply_progress_update(
            progress,
            ExecutionProgressUpdate(
                attempt_id=progress.attempt_id,
                sequence=progress.sequence + 1,
                phase=desired_progress,
                completed_units=(progress.total_units if desired_progress is ProgressPhase.SUCCEEDED else progress.completed_units),
                total_units=progress.total_units,
                emitted_at=observed_at,
                detail="runtime terminal materialized",
            ),
        )
    except (TypeError, ValueError) as exc:
        return _reject(outcome, progress, str(exc))
    decision = ExecutionTerminalDecision(runtime_state.phase.value)
    return ExecutionTerminalResolution(decision, outcome_resolution.state, progress_state)


def _reject(
    outcome: ExecutionOutcome,
    progress: ExecutionProgressState,
    reason: str,
) -> ExecutionTerminalResolution:
    return ExecutionTerminalResolution(
        ExecutionTerminalDecision.REJECT,
        outcome,
        progress,
        reason,
    )
