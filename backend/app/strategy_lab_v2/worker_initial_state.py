"""Idempotent durable bootstrap for authenticated search worker attempts."""

from __future__ import annotations

from typing import Any, Protocol

from app.strategy_lab_v2.outcomes import new_execution_outcome
from app.strategy_lab_v2.progress import new_progress_state
from app.strategy_lab_v2.runtime_execution import RuntimeExecutionState
from app.strategy_lab_v2.submissions import SubmissionReceipt
from app.strategy_lab_v2.worker_process import WorkerExecutionRequest


class ExecutionStateBootstrap(Protocol):
    async def read_context(self, *, principal: Any, attempt_id: str) -> Any: ...

    async def initialize(self, *, principal: Any, outcome: Any, progress: Any) -> Any: ...


class RuntimeStateBootstrap(Protocol):
    async def load(self, *, principal: Any, attempt_id: str) -> RuntimeExecutionState | None: ...

    async def initialize(self, *, principal: Any, state: RuntimeExecutionState) -> Any: ...


async def ensure_worker_initial_state(
    *,
    execution_state: ExecutionStateBootstrap,
    runtime_execution: RuntimeStateBootstrap,
    principal: Any,
    request: WorkerExecutionRequest,
    submission: SubmissionReceipt,
) -> None:
    """Ensure public and sandbox initial state exists before native execution.

    Search dispatch and its outbox commit before a dedicated worker consumes
    Redis. This idempotent preflight repairs a crash between those boundaries
    and makes retries safe: a worker does not launch Nautilus until both
    owner-scoped sequence-zero records have been registered or authenticated.
    """

    if not callable(getattr(execution_state, "read_context", None)) or not callable(
        getattr(execution_state, "initialize", None)
    ):
        raise TypeError("execution_state must expose read_context() and initialize()")
    if not callable(getattr(runtime_execution, "load", None)) or not callable(
        getattr(runtime_execution, "initialize", None)
    ):
        raise TypeError("runtime_execution must expose load() and initialize()")
    if not isinstance(request, WorkerExecutionRequest):
        raise TypeError("request must be a WorkerExecutionRequest")
    if not isinstance(submission, SubmissionReceipt):
        raise TypeError("submission must be a SubmissionReceipt")
    attempt_id = request.runtime_request.attempt_id
    if (
        request.admission.attempt_id != attempt_id
        or request.runtime_state.attempt_id != attempt_id
        or submission.request.attempt_id != attempt_id
    ):
        raise ValueError("worker bootstrap identities reference different attempts")

    execution = await execution_state.read_context(principal=principal, attempt_id=attempt_id)
    if execution is None:
        outcome = new_execution_outcome(
            submission.submission_id,
            attempt_id,
            accepted_at=submission.accepted_at,
        )
        progress = new_progress_state(attempt_id, total_units=1, now=submission.accepted_at)
        resolution = await execution_state.initialize(
            principal=principal,
            outcome=outcome,
            progress=progress,
        )
        if resolution.decision.value not in {"applied", "replay_existing"}:
            raise ValueError(resolution.rejection_reason or "worker execution state was rejected")
        execution = await execution_state.read_context(principal=principal, attempt_id=attempt_id)
    if execution is None:
        raise ValueError("worker execution state could not be loaded after initialization")
    if (
        execution.outcome.attempt_id != attempt_id
        or execution.outcome.submission_id != submission.submission_id
    ):
        raise ValueError("persisted execution state differs from its authenticated submission")

    runtime_state = await runtime_execution.load(principal=principal, attempt_id=attempt_id)
    if runtime_state is None:
        resolution = await runtime_execution.initialize(
            principal=principal,
            state=request.runtime_state,
        )
        if resolution.decision.value not in {"registered", "replay_existing"}:
            raise ValueError(resolution.rejection_reason or "worker runtime state was rejected")
        runtime_state = await runtime_execution.load(principal=principal, attempt_id=attempt_id)
    if runtime_state is None:
        raise ValueError("worker runtime state could not be loaded after initialization")
    if (
        runtime_state.attempt_id != attempt_id
        or runtime_state.request_fingerprint != request.runtime_state.request_fingerprint
        or runtime_state.profile_fingerprint != request.runtime_state.profile_fingerprint
        or runtime_state.output_limit_bytes != request.runtime_state.output_limit_bytes
    ):
        raise ValueError("persisted runtime state differs from its authenticated worker request")


__all__ = ["ensure_worker_initial_state"]
