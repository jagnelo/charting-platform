"""Engine-neutral execution handoff orchestration.

The package contains several independent admission and execution contracts:
authorization, runtime isolation, worker admission, sandbox planning, and the
Nautilus execution gate.  This module binds their immutable identities into one
worker-facing plan without starting a process or persisting any state.  A
worker adapter can use the plan as its sole input, while a persistence adapter
can compare-and-set the referenced state before dispatch.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.strategy_lab_v2.admission import ExecutionAdmission, ExecutionAdmissionRequest
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.engine_execution import (
    EngineExecutionDecision,
    NautilusExecutionPlan,
)
from app.strategy_lab_v2.execution import ExecutionAuthorization
from app.strategy_lab_v2.runtime_execution import (
    RuntimeExecutionPhase,
    RuntimeExecutionState,
    StrategyRuntimePreflight,
    StrategyRuntimeRequest,
)
from app.strategy_lab_v2.sandbox import (
    SandboxCommandPlan,
    validate_sandbox_command_plan,
)


class ExecutionOrchestrationDecision(StrEnum):
    READY = "ready"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class ExecutionOrchestrationPlan:
    """Immutable, content-addressed input for one isolated worker handoff."""

    trial_id: str
    attempt_id: str
    authorization_fingerprint: str
    admission_fingerprint: str
    runtime_request_fingerprint: str
    runtime_preflight_fingerprint: str
    runtime_state_fingerprint: str
    sandbox_plan_fingerprint: str
    execution_plan_fingerprint: str
    worker_id: str
    authoritative: bool
    decision: ExecutionOrchestrationDecision
    rejection_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("trial_id", "attempt_id", "worker_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        for name in (
            "authorization_fingerprint",
            "admission_fingerprint",
            "runtime_request_fingerprint",
            "runtime_preflight_fingerprint",
            "runtime_state_fingerprint",
            "sandbox_plan_fingerprint",
            "execution_plan_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        if not isinstance(self.authoritative, bool):
            raise TypeError("authoritative must be a boolean")
        if not isinstance(self.decision, ExecutionOrchestrationDecision):
            raise TypeError("decision must be an ExecutionOrchestrationDecision")
        reasons = tuple(self.rejection_reasons)
        if len(reasons) != len(set(reasons)) or any(
            not isinstance(reason, str) or not reason.strip() for reason in reasons
        ):
            raise ValueError("orchestration rejection reasons must be unique and non-empty")
        if self.decision is ExecutionOrchestrationDecision.READY and reasons:
            raise ValueError("ready orchestration plans cannot contain rejection reasons")
        if self.decision is ExecutionOrchestrationDecision.REJECT and not reasons:
            raise ValueError("rejected orchestration plans require rejection reasons")
        if self.authoritative and self.decision is not ExecutionOrchestrationDecision.READY:
            raise ValueError("rejected orchestration plans cannot be authoritative")
        object.__setattr__(self, "rejection_reasons", reasons)

    @property
    def accepted(self) -> bool:
        return self.decision is ExecutionOrchestrationDecision.READY

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def plan_execution_orchestration(
    authorization: ExecutionAuthorization,
    admission: ExecutionAdmission,
    runtime_request: StrategyRuntimeRequest,
    runtime_preflight: StrategyRuntimePreflight,
    runtime_state: RuntimeExecutionState,
    sandbox_plan: SandboxCommandPlan,
    execution_plan: NautilusExecutionPlan,
) -> ExecutionOrchestrationPlan:
    """Bind all pre-execution evidence into one fail-closed worker plan.

    The plan is valid only while the attempt is still in its accepted runtime
    state.  Once a worker has emitted a running or terminal receipt, a second
    process handoff must be created by an explicit retry/recovery flow rather
    than silently starting another engine node.
    """

    values = (
        authorization,
        admission,
        runtime_request,
        runtime_preflight,
        runtime_state,
        sandbox_plan,
        execution_plan,
    )
    expected = (
        ExecutionAuthorization,
        ExecutionAdmission,
        StrategyRuntimeRequest,
        StrategyRuntimePreflight,
        RuntimeExecutionState,
        SandboxCommandPlan,
        NautilusExecutionPlan,
    )
    names = (
        "authorization",
        "admission",
        "runtime_request",
        "runtime_preflight",
        "runtime_state",
        "sandbox_plan",
        "execution_plan",
    )
    for name, value, expected_type in zip(names, values, expected, strict=True):
        if not isinstance(value, expected_type):
            raise TypeError(f"{name} must be a {expected_type.__name__}")

    reasons: list[str] = []
    try:
        validate_sandbox_command_plan(sandbox_plan)
    except ValueError:
        reasons.append("sandbox_plan_not_hardened")
    expected_admission_request = ExecutionAdmissionRequest(
        authorization_fingerprint=authorization.fingerprint,
        runtime_request_fingerprint=runtime_request.fingerprint,
        attempt_id=authorization.attempt_id,
        worker_id=admission.worker_id,
        worker_kind=admission.worker_kind,
        worker_profile_fingerprint=admission.worker_profile_fingerprint,
        reservation_id=admission.reservation_id,
        requested_at=admission.admitted_at,
    )
    if admission.request_fingerprint != expected_admission_request.fingerprint:
        reasons.append("admission_request_identity_mismatch")
    if admission.authorization_fingerprint != authorization.fingerprint:
        reasons.append("admission_authorization_mismatch")
    if admission.attempt_id != authorization.attempt_id:
        reasons.append("admission_attempt_mismatch")
    if admission.runtime_request_fingerprint != runtime_request.fingerprint:
        reasons.append("admission_runtime_request_mismatch")
    if authorization.attempt_id != runtime_request.attempt_id:
        reasons.append("authorization_runtime_attempt_mismatch")
    if authorization.source_digest != runtime_request.source_digest:
        reasons.append("authorization_runtime_source_mismatch")
    if not runtime_preflight.accepted:
        reasons.append("runtime_preflight_not_accepted")
    if runtime_preflight.request_fingerprint != runtime_request.fingerprint:
        reasons.append("runtime_preflight_request_mismatch")
    if runtime_preflight.profile_fingerprint != admission.worker_profile_fingerprint:
        reasons.append("runtime_preflight_worker_profile_mismatch")
    if runtime_state.request_fingerprint != runtime_request.fingerprint:
        reasons.append("runtime_state_request_mismatch")
    if runtime_state.attempt_id != authorization.attempt_id:
        reasons.append("runtime_state_attempt_mismatch")
    if runtime_state.profile_fingerprint != runtime_preflight.profile_fingerprint:
        reasons.append("runtime_state_profile_mismatch")
    if runtime_state.phase is not RuntimeExecutionPhase.ACCEPTED or runtime_state.sequence != 0:
        reasons.append("runtime_state_already_started")
    if runtime_state.output_limit_bytes != sandbox_plan.output_limit_bytes:
        reasons.append("runtime_output_limit_mismatch")
    if sandbox_plan.request_fingerprint != runtime_request.fingerprint:
        reasons.append("sandbox_request_mismatch")
    if sandbox_plan.profile_fingerprint != runtime_preflight.profile_fingerprint:
        reasons.append("sandbox_profile_mismatch")
    if execution_plan.decision is not EngineExecutionDecision.READY:
        reasons.append("execution_plan_rejected")
    if execution_plan.trial_id != authorization.trial_id:
        reasons.append("execution_plan_trial_mismatch")
    if execution_plan.attempt_id != authorization.attempt_id:
        reasons.append("execution_plan_attempt_mismatch")
    if execution_plan.authorization_fingerprint != authorization.fingerprint:
        reasons.append("execution_plan_authorization_mismatch")
    if execution_plan.runtime_preflight_fingerprint != runtime_preflight.fingerprint:
        reasons.append("execution_plan_runtime_preflight_mismatch")
    if execution_plan.sandbox_plan_fingerprint != sandbox_plan.fingerprint:
        reasons.append("execution_plan_sandbox_mismatch")
    if execution_plan.authoritative and not admission.authoritative:
        reasons.append("authoritative_execution_not_admitted")

    reasons_tuple = tuple(sorted(set(reasons)))
    decision = (
        ExecutionOrchestrationDecision.REJECT
        if reasons_tuple
        else ExecutionOrchestrationDecision.READY
    )
    return ExecutionOrchestrationPlan(
        trial_id=authorization.trial_id,
        attempt_id=authorization.attempt_id,
        authorization_fingerprint=authorization.fingerprint,
        admission_fingerprint=admission.fingerprint,
        runtime_request_fingerprint=runtime_request.fingerprint,
        runtime_preflight_fingerprint=runtime_preflight.fingerprint,
        runtime_state_fingerprint=runtime_state.fingerprint,
        sandbox_plan_fingerprint=sandbox_plan.fingerprint,
        execution_plan_fingerprint=execution_plan.fingerprint,
        worker_id=admission.worker_id,
        authoritative=(decision is ExecutionOrchestrationDecision.READY and execution_plan.authoritative),
        decision=decision,
        rejection_reasons=reasons_tuple,
    )
