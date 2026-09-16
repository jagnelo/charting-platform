"""Worker-side composition of execution admission, runner, and runtime state.

This adapter is deliberately still storage-neutral: it revalidates the
immutable handoff and active serial reservation immediately before process
creation, invokes only the gated Nautilus runner, and returns both process and
runtime evidence for a future compare-and-set transaction.  It never queues
work or publishes a result.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.admission import ExecutionAdmission
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.engine_execution import NautilusExecutionPlan
from app.strategy_lab_v2.execution import ExecutionAuthorization
from app.strategy_lab_v2.execution_orchestration import (
    ExecutionOrchestrationDecision,
    ExecutionOrchestrationPlan,
    plan_execution_orchestration,
)
from app.strategy_lab_v2.nautilus_runner import (
    NautilusRunResult,
    NautilusRunStatus,
    run_nautilus_plan,
)
from app.strategy_lab_v2.runtime_execution import (
    RuntimeExecutionState,
    StrategyRuntimePreflight,
    StrategyRuntimeRequest,
)
from app.strategy_lab_v2.runtime_result_adapter import (
    RuntimeResultDecision,
    RuntimeResultResolution,
    materialize_nautilus_result,
)
from app.strategy_lab_v2.sandbox import SandboxCommandPlan
from app.strategy_lab_v2.workers import WorkerPoolState


class WorkerExecutionDecision(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REPLAY_EXISTING = "replay_existing"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class WorkerExecutionResolution:
    """Evidence returned by one bounded worker handoff."""

    decision: WorkerExecutionDecision
    orchestration_plan: ExecutionOrchestrationPlan
    nautilus_result: NautilusRunResult | None = None
    runtime_result: RuntimeResultResolution | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, WorkerExecutionDecision):
            raise TypeError("decision must be a WorkerExecutionDecision")
        if not isinstance(self.orchestration_plan, ExecutionOrchestrationPlan):
            raise TypeError("orchestration_plan must be an ExecutionOrchestrationPlan")
        if self.nautilus_result is not None and not isinstance(self.nautilus_result, NautilusRunResult):
            raise TypeError("nautilus_result must be a NautilusRunResult")
        if self.runtime_result is not None and not isinstance(self.runtime_result, RuntimeResultResolution):
            raise TypeError("runtime_result must be a RuntimeResultResolution")
        if self.decision is WorkerExecutionDecision.REJECTED and not self.rejection_reason:
            raise ValueError("rejected worker executions require a reason")
        if self.decision is not WorkerExecutionDecision.REJECTED and self.rejection_reason:
            raise ValueError("accepted worker executions cannot contain a reason")
        if self.decision in {
            WorkerExecutionDecision.SUCCEEDED,
            WorkerExecutionDecision.FAILED,
            WorkerExecutionDecision.REPLAY_EXISTING,
        } and (self.nautilus_result is None or self.runtime_result is None):
            raise ValueError("completed worker executions require process and runtime evidence")
        if self.decision is not WorkerExecutionDecision.REJECTED:
            assert self.runtime_result is not None
            if self.runtime_result.decision is RuntimeResultDecision.REJECT:
                raise ValueError("completed worker executions cannot contain rejected runtime evidence")
            if self.runtime_result.decision.value != self.decision.value:
                raise ValueError("worker execution decision must match runtime result decision")
        elif self.runtime_result is not None and self.runtime_result.decision is not RuntimeResultDecision.REJECT:
            raise ValueError("rejected worker executions require rejected runtime evidence")

    @property
    def fingerprint(self) -> str:
        return content_digest(
            {
                "decision": self.decision,
                "nautilus_result": self.nautilus_result,
                "orchestration_plan": self.orchestration_plan,
                "rejection_reason": self.rejection_reason,
                "runtime_result": self.runtime_result,
            }
        )


def execute_worker_handoff(
    orchestration_plan: ExecutionOrchestrationPlan,
    authorization: ExecutionAuthorization,
    admission: ExecutionAdmission,
    runtime_request: StrategyRuntimeRequest,
    runtime_preflight: StrategyRuntimePreflight,
    runtime_state: RuntimeExecutionState,
    sandbox_plan: SandboxCommandPlan,
    execution_plan: NautilusExecutionPlan,
    *,
    worker_pool: WorkerPoolState,
    observed_at: datetime,
    docker_binary: str = "docker",
) -> WorkerExecutionResolution:
    """Revalidate and execute one immutable handoff through Nautilus only."""

    if not isinstance(orchestration_plan, ExecutionOrchestrationPlan):
        raise TypeError("orchestration_plan must be an ExecutionOrchestrationPlan")
    if not isinstance(worker_pool, WorkerPoolState):
        raise TypeError("worker_pool must be a WorkerPoolState")
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    if admission.worker_id != worker_pool.profile.worker_id:
        return WorkerExecutionResolution(
            WorkerExecutionDecision.REJECTED,
            orchestration_plan,
            rejection_reason="admission is bound to a different worker pool",
        )
    if admission.worker_kind is not worker_pool.profile.kind:
        return WorkerExecutionResolution(
            WorkerExecutionDecision.REJECTED,
            orchestration_plan,
            rejection_reason="admission kind does not match the worker pool",
        )
    if admission.worker_profile_fingerprint != worker_pool.profile.runtime_profile_fingerprint:
        return WorkerExecutionResolution(
            WorkerExecutionDecision.REJECTED,
            orchestration_plan,
            rejection_reason="admission profile does not match the worker pool",
        )
    reservation = next(
        (
            item
            for item in worker_pool.active_reservations
            if item.reservation_id == admission.reservation_id
            and item.attempt_id == admission.attempt_id
        ),
        None,
    )
    if reservation is None:
        return WorkerExecutionResolution(
            WorkerExecutionDecision.REJECTED,
            orchestration_plan,
            rejection_reason="admission has no active worker reservation",
        )
    if observed_at < reservation.acquired_at:
        return WorkerExecutionResolution(
            WorkerExecutionDecision.REJECTED,
            orchestration_plan,
            rejection_reason="worker observation time precedes reservation acquisition",
        )
    expected = plan_execution_orchestration(
        authorization,
        admission,
        runtime_request,
        runtime_preflight,
        runtime_state,
        sandbox_plan,
        execution_plan,
    )
    if expected.decision is not ExecutionOrchestrationDecision.READY:
        return WorkerExecutionResolution(
            WorkerExecutionDecision.REJECTED,
            orchestration_plan,
            rejection_reason="; ".join(expected.rejection_reasons),
        )
    if expected.fingerprint != orchestration_plan.fingerprint:
        return WorkerExecutionResolution(
            WorkerExecutionDecision.REJECTED,
            orchestration_plan,
            rejection_reason="orchestration plan fingerprint drift",
        )

    nautilus_result = run_nautilus_plan(
        execution_plan,
        sandbox_plan,
        docker_binary=docker_binary,
    )
    if nautilus_result.status is NautilusRunStatus.REJECTED:
        return WorkerExecutionResolution(
            WorkerExecutionDecision.REJECTED,
            orchestration_plan,
            nautilus_result,
            rejection_reason="Nautilus runner rejected the execution plan",
        )
    runtime_result = materialize_nautilus_result(
        runtime_state,
        execution_plan,
        sandbox_plan,
        nautilus_result,
        observed_at=observed_at,
    )
    if runtime_result.decision is RuntimeResultDecision.REJECT:
        return WorkerExecutionResolution(
            WorkerExecutionDecision.REJECTED,
            orchestration_plan,
            nautilus_result,
            runtime_result,
            rejection_reason=runtime_result.rejection_reason or "runtime result rejected",
        )
    decision = WorkerExecutionDecision(runtime_result.decision.value)
    return WorkerExecutionResolution(
        decision,
        orchestration_plan,
        nautilus_result,
        runtime_result,
    )
