"""Materialize bounded sandbox evidence into runtime execution state.

The adapter deliberately stops at runtime evidence.  A successful process
does not become an official Strategy Lab result until the future worker reads,
verifies, and publishes the result artifact through the existing result gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.engine_execution import NautilusExecutionPlan
from app.strategy_lab_v2.nautilus_runner import NautilusRunResult, NautilusRunStatus
from app.strategy_lab_v2.runtime_execution import (
    RuntimeExecutionDecision,
    RuntimeExecutionPhase,
    RuntimeExecutionResolution,
    RuntimeExecutionState,
    RuntimeExecutionUpdate,
    apply_runtime_execution_update,
)
from app.strategy_lab_v2.sandbox import SandboxCommandPlan
from app.strategy_lab_v2.sandbox_execution import SandboxRunResult, SandboxRunStatus


class RuntimeResultDecision(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REPLAY_EXISTING = "replay_existing"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class RuntimeResultResolution:
    """Runtime state proposed from one exact sandbox result."""

    decision: RuntimeResultDecision
    state: RuntimeExecutionState
    sandbox_result: SandboxRunResult
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, RuntimeResultDecision):
            raise TypeError("decision must be a RuntimeResultDecision")
        if not isinstance(self.state, RuntimeExecutionState):
            raise TypeError("state must be a RuntimeExecutionState")
        if not isinstance(self.sandbox_result, SandboxRunResult):
            raise TypeError("sandbox_result must be a SandboxRunResult")
        if self.decision is RuntimeResultDecision.REJECT and not self.rejection_reason:
            raise ValueError("rejected runtime results require a reason")
        if self.decision is not RuntimeResultDecision.REJECT and self.rejection_reason:
            raise ValueError("accepted runtime results cannot contain a reason")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def materialize_sandbox_result(
    state: RuntimeExecutionState,
    sandbox_plan: SandboxCommandPlan,
    sandbox_result: SandboxRunResult,
    *,
    observed_at: datetime,
) -> RuntimeResultResolution:
    """Apply one sandbox terminal result to runtime state without publication."""

    if not isinstance(state, RuntimeExecutionState):
        raise TypeError("state must be a RuntimeExecutionState")
    if not isinstance(sandbox_plan, SandboxCommandPlan):
        raise TypeError("sandbox_plan must be a SandboxCommandPlan")
    if not isinstance(sandbox_result, SandboxRunResult):
        raise TypeError("sandbox_result must be a SandboxRunResult")
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    if sandbox_result.plan_fingerprint != sandbox_plan.fingerprint:
        return _reject(state, sandbox_result, "sandbox result does not match its command plan")
    if sandbox_result.request_fingerprint != state.request_fingerprint:
        return _reject(state, sandbox_result, "sandbox result references a different runtime request")
    if state.phase in {
        RuntimeExecutionPhase.SUCCEEDED,
        RuntimeExecutionPhase.FAILED,
        RuntimeExecutionPhase.CANCELLED,
    }:
        same_success = (
            state.phase is RuntimeExecutionPhase.SUCCEEDED
            and sandbox_result.status is SandboxRunStatus.SUCCEEDED
            and state.output_digest == sandbox_result.stdout_digest
            and state.output_bytes == sandbox_result.stdout_bytes
        )
        same_failure = (
            state.phase is RuntimeExecutionPhase.FAILED
            and sandbox_result.status is not SandboxRunStatus.SUCCEEDED
            and state.error_digest
            == (
                sandbox_result.error_digest
                or content_digest(f"sandbox process status: {sandbox_result.status.value}")
            )
        )
        if same_success or same_failure:
            return RuntimeResultResolution(
                RuntimeResultDecision.REPLAY_EXISTING,
                state,
                sandbox_result,
            )
        return _reject(state, sandbox_result, "terminal runtime state conflicts with the sandbox result")
    if observed_at < state.updated_at:
        return _reject(state, sandbox_result, "runtime result time cannot move backwards")

    running = apply_runtime_execution_update(
        state,
        RuntimeExecutionUpdate(
            state.request_fingerprint,
            state.attempt_id,
            state.sequence + 1,
            RuntimeExecutionPhase.RUNNING,
            observed_at,
        ),
    )
    if running.decision is not RuntimeExecutionDecision.APPLY:
        return _reject(state, sandbox_result, "runtime running transition could not be applied")
    if sandbox_result.status is SandboxRunStatus.SUCCEEDED:
        terminal = RuntimeExecutionUpdate(
            state.request_fingerprint,
            state.attempt_id,
            running.state.sequence + 1,
            RuntimeExecutionPhase.SUCCEEDED,
            observed_at,
            sandbox_result.stdout_digest,
            sandbox_result.stdout_bytes,
        )
        decision = RuntimeResultDecision.SUCCEEDED
    else:
        terminal = RuntimeExecutionUpdate(
            state.request_fingerprint,
            state.attempt_id,
            running.state.sequence + 1,
            RuntimeExecutionPhase.FAILED,
            observed_at,
            error_digest=sandbox_result.error_digest
            or content_digest(f"sandbox process status: {sandbox_result.status.value}"),
        )
        decision = RuntimeResultDecision.FAILED
    resolved: RuntimeExecutionResolution = apply_runtime_execution_update(
        running.state,
        terminal,
    )
    return RuntimeResultResolution(decision, resolved.state, sandbox_result)


def materialize_nautilus_result(
    state: RuntimeExecutionState,
    execution_plan: NautilusExecutionPlan,
    sandbox_plan: SandboxCommandPlan,
    run_result: NautilusRunResult,
    *,
    observed_at: datetime,
) -> RuntimeResultResolution:
    """Materialize a gated Nautilus runner result after verifying its envelope.

    Rejected runner results represent a pre-process admission failure and must
    never transition runtime state.  The runner therefore has no sandbox
    evidence in that case; callers should retain the state and surface the
    runner's rejection rather than treating it as a strategy failure.
    """

    if not isinstance(state, RuntimeExecutionState):
        raise TypeError("state must be a RuntimeExecutionState")
    if not isinstance(execution_plan, NautilusExecutionPlan):
        raise TypeError("execution_plan must be a NautilusExecutionPlan")
    if not isinstance(sandbox_plan, SandboxCommandPlan):
        raise TypeError("sandbox_plan must be a SandboxCommandPlan")
    if not isinstance(run_result, NautilusRunResult):
        raise TypeError("run_result must be a NautilusRunResult")
    if run_result.status is NautilusRunStatus.REJECTED:
        raise ValueError("rejected Nautilus results have no runtime sandbox evidence")
    if run_result.sandbox_result is None:
        raise ValueError("executed Nautilus results require sandbox evidence")
    if run_result.execution_plan_fingerprint != execution_plan.fingerprint:
        return _reject(state, run_result.sandbox_result, "Nautilus result does not match its execution plan")
    if run_result.sandbox_plan_fingerprint != sandbox_plan.fingerprint:
        return _reject(state, run_result.sandbox_result, "Nautilus result does not match its sandbox plan")
    if run_result.sandbox_result.plan_fingerprint != sandbox_plan.fingerprint:
        return _reject(state, run_result.sandbox_result, "Nautilus sandbox evidence does not match its plan")
    if run_result.sandbox_result.status.value != run_result.status.value:
        return _reject(state, run_result.sandbox_result, "Nautilus and sandbox statuses differ")
    expected_authoritative = (
        execution_plan.authoritative and run_result.status is NautilusRunStatus.SUCCEEDED
    )
    if run_result.authoritative is not expected_authoritative:
        return _reject(state, run_result.sandbox_result, "Nautilus authority evidence is inconsistent")
    return materialize_sandbox_result(
        state,
        sandbox_plan,
        run_result.sandbox_result,
        observed_at=observed_at,
    )


def _reject(
    state: RuntimeExecutionState,
    sandbox_result: SandboxRunResult,
    reason: str,
) -> RuntimeResultResolution:
    return RuntimeResultResolution(
        RuntimeResultDecision.REJECT,
        state,
        sandbox_result,
        reason,
    )
