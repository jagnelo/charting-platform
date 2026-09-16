"""Nautilus-only execution planning after all authoritative release gates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.conformance import (
    EngineConformanceEvidence,
    EngineConformanceReport,
)
from app.strategy_lab_v2.execution import ExecutionAuthorization
from app.strategy_lab_v2.runtime_execution import StrategyRuntimePreflight
from app.strategy_lab_v2.sandbox import SandboxCommandPlan


class EngineExecutionDecision(StrEnum):
    READY = "ready"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class NautilusExecutionPlan:
    """Immutable evidence a worker may use to start one Nautilus process."""

    trial_id: str
    attempt_id: str
    data_snapshot_fingerprint: str
    engine_id: str
    engine_version: str
    engine_build_digest: str
    authorization_fingerprint: str
    runtime_preflight_fingerprint: str
    conformance_report_fingerprint: str
    sandbox_plan_fingerprint: str
    decision: EngineExecutionDecision
    authoritative: bool
    rejection_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("trial_id", "attempt_id", "engine_id", "engine_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        for name in (
            "data_snapshot_fingerprint",
            "engine_build_digest",
            "authorization_fingerprint",
            "runtime_preflight_fingerprint",
            "conformance_report_fingerprint",
            "sandbox_plan_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        if not isinstance(self.decision, EngineExecutionDecision):
            raise TypeError("decision must be an EngineExecutionDecision")
        if not isinstance(self.authoritative, bool):
            raise TypeError("authoritative must be a boolean")
        reasons = tuple(self.rejection_reasons)
        if len(reasons) != len(set(reasons)) or any(
            not isinstance(reason, str) or not reason.strip() for reason in reasons
        ):
            raise ValueError("engine rejection reasons must be unique and non-empty")
        if self.decision is EngineExecutionDecision.READY and reasons:
            raise ValueError("ready engine plans cannot contain rejection reasons")
        if self.decision is EngineExecutionDecision.REJECT and not reasons:
            raise ValueError("rejected engine plans require rejection reasons")
        if self.authoritative and self.decision is not EngineExecutionDecision.READY:
            raise ValueError("rejected engine plans cannot be authoritative")
        object.__setattr__(self, "rejection_reasons", reasons)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def plan_nautilus_execution(
    authorization: ExecutionAuthorization,
    runtime_preflight: StrategyRuntimePreflight,
    conformance_evidence: EngineConformanceEvidence,
    conformance_report: EngineConformanceReport,
    sandbox_plan: SandboxCommandPlan,
    *,
    data_snapshot_fingerprint: str,
    requested_authoritative: bool = True,
) -> NautilusExecutionPlan:
    """Resolve the final engine invocation gate without starting Nautilus."""

    if not isinstance(authorization, ExecutionAuthorization):
        raise TypeError("authorization must be an ExecutionAuthorization")
    if not isinstance(runtime_preflight, StrategyRuntimePreflight):
        raise TypeError("runtime_preflight must be a StrategyRuntimePreflight")
    if not isinstance(conformance_evidence, EngineConformanceEvidence):
        raise TypeError("conformance_evidence must be an EngineConformanceEvidence")
    if not isinstance(conformance_report, EngineConformanceReport):
        raise TypeError("conformance_report must be an EngineConformanceReport")
    if not isinstance(sandbox_plan, SandboxCommandPlan):
        raise TypeError("sandbox_plan must be a SandboxCommandPlan")
    require_sha256_digest(data_snapshot_fingerprint, field_name="data_snapshot_fingerprint")
    if not isinstance(requested_authoritative, bool):
        raise TypeError("requested_authoritative must be a boolean")

    reasons: list[str] = []
    if authorization.trial_id.strip() == "" or authorization.attempt_id.strip() == "":
        reasons.append("authorization_identity_missing")
    if not runtime_preflight.accepted:
        reasons.append("runtime_isolation_not_accepted")
    if sandbox_plan.request_fingerprint != runtime_preflight.request_fingerprint:
        reasons.append("sandbox_runtime_request_mismatch")
    if conformance_evidence.fingerprint != conformance_report.evidence_fingerprint:
        reasons.append("conformance_evidence_report_mismatch")
    if conformance_evidence.engine_id.lower() != "nautilus":
        reasons.append("only_nautilus_engine_is_supported")
    if not conformance_report.compatible:
        reasons.append("engine_conformance_failed")
    if requested_authoritative and not authorization.authoritative:
        reasons.append("authorization_is_not_authoritative")
    if requested_authoritative and not conformance_report.authoritative:
        reasons.append("stable_authoritative_conformance_required")
    if requested_authoritative and conformance_evidence.release_channel.value != "stable":
        reasons.append("stable_engine_release_required")
    reasons_tuple = tuple(sorted(set(reasons)))
    decision = EngineExecutionDecision.REJECT if reasons_tuple else EngineExecutionDecision.READY
    return NautilusExecutionPlan(
        trial_id=authorization.trial_id,
        attempt_id=authorization.attempt_id,
        data_snapshot_fingerprint=data_snapshot_fingerprint,
        engine_id=conformance_evidence.engine_id,
        engine_version=conformance_evidence.engine_version,
        engine_build_digest=conformance_evidence.build_digest,
        authorization_fingerprint=authorization.fingerprint,
        runtime_preflight_fingerprint=runtime_preflight.fingerprint,
        conformance_report_fingerprint=conformance_report.fingerprint,
        sandbox_plan_fingerprint=sandbox_plan.fingerprint,
        decision=decision,
        authoritative=decision is EngineExecutionDecision.READY and requested_authoritative,
        rejection_reasons=reasons_tuple,
    )
