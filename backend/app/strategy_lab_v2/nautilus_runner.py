"""Nautilus plan execution through the bounded sandbox adapter.

This is the last process boundary before a future isolated Nautilus v2 worker.
It does not discover engines, fetch data, or bypass conformance: callers must
provide the immutable :class:`NautilusExecutionPlan` produced by the gate.
Rejected plans never reach ``subprocess``; successful execution evidence keeps
the plan and sandbox fingerprints together for result publication.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.engine_execution import (
    EngineExecutionDecision,
    NautilusExecutionPlan,
)
from app.strategy_lab_v2.sandbox import SandboxCommandPlan
from app.strategy_lab_v2.sandbox_execution import (
    SandboxRunResult,
    SandboxRunStatus,
    run_sandbox_command,
)


class NautilusRunStatus(StrEnum):
    REJECTED = "rejected"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    OUTPUT_LIMIT_EXCEEDED = "output_limit_exceeded"
    START_FAILED = "start_failed"


@dataclass(frozen=True, slots=True)
class NautilusRunResult:
    """Content-addressed outcome of one gated Nautilus process attempt."""

    execution_plan_fingerprint: str
    sandbox_plan_fingerprint: str
    status: NautilusRunStatus
    authoritative: bool
    sandbox_result: SandboxRunResult | None = None
    rejection_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_sha256_digest(
            self.execution_plan_fingerprint,
            field_name="execution_plan_fingerprint",
        )
        require_sha256_digest(
            self.sandbox_plan_fingerprint,
            field_name="sandbox_plan_fingerprint",
        )
        if not isinstance(self.status, NautilusRunStatus):
            raise TypeError("status must be a NautilusRunStatus")
        if not isinstance(self.authoritative, bool):
            raise TypeError("authoritative must be a boolean")
        if self.sandbox_result is not None and not isinstance(
            self.sandbox_result, SandboxRunResult
        ):
            raise TypeError("sandbox_result must be a SandboxRunResult")
        reasons = tuple(self.rejection_reasons)
        if len(reasons) != len(set(reasons)) or any(
            not isinstance(reason, str) or not reason.strip() for reason in reasons
        ):
            raise ValueError("Nautilus rejection reasons must be unique and non-empty")
        if self.status is NautilusRunStatus.REJECTED:
            if self.sandbox_result is not None or self.authoritative or not reasons:
                raise ValueError("rejected Nautilus runs require reasons and no process result")
        else:
            if self.sandbox_result is None or reasons:
                raise ValueError("executed Nautilus runs require a sandbox result and no rejection reasons")
            if self.authoritative and self.status is not NautilusRunStatus.SUCCEEDED:
                raise ValueError("only successful Nautilus runs can be authoritative")
        if self.sandbox_result is not None and (
            self.sandbox_result.plan_fingerprint != self.sandbox_plan_fingerprint
        ):
            raise ValueError("sandbox result does not reference the execution sandbox plan")
        object.__setattr__(self, "rejection_reasons", reasons)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def run_nautilus_plan(
    execution_plan: NautilusExecutionPlan,
    sandbox_plan: SandboxCommandPlan,
    *,
    docker_binary: str = "docker",
) -> NautilusRunResult:
    """Execute only a ready, Nautilus-bound plan through the sandbox adapter."""

    if not isinstance(execution_plan, NautilusExecutionPlan):
        raise TypeError("execution_plan must be a NautilusExecutionPlan")
    if not isinstance(sandbox_plan, SandboxCommandPlan):
        raise TypeError("sandbox_plan must be a SandboxCommandPlan")
    reasons: list[str] = []
    if execution_plan.decision is not EngineExecutionDecision.READY:
        reasons.append("execution_plan_rejected")
    if execution_plan.engine_id.lower() != "nautilus":
        reasons.append("only_nautilus_engine_is_supported")
    if execution_plan.sandbox_plan_fingerprint != sandbox_plan.fingerprint:
        reasons.append("sandbox_plan_identity_mismatch")
    if reasons:
        return NautilusRunResult(
            execution_plan.fingerprint,
            sandbox_plan.fingerprint,
            NautilusRunStatus.REJECTED,
            False,
            rejection_reasons=tuple(sorted(set(reasons))),
        )

    sandbox_result = run_sandbox_command(sandbox_plan, docker_binary=docker_binary)
    status = _status(sandbox_result.status)
    return NautilusRunResult(
        execution_plan.fingerprint,
        sandbox_plan.fingerprint,
        status,
        execution_plan.authoritative and status is NautilusRunStatus.SUCCEEDED,
        sandbox_result,
    )


def _status(status: SandboxRunStatus) -> NautilusRunStatus:
    return NautilusRunStatus(status.value)
