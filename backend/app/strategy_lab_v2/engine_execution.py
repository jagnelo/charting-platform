"""Nautilus-only execution planning after exact-build conformance gates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.conformance import (
    ConformanceCheck,
    EngineConformanceEvidence,
    EngineConformanceReport,
    EngineReleaseChannel,
    evaluate_engine_conformance,
)
from app.strategy_lab_v2.execution import ExecutionAuthorization
from app.strategy_lab_v2.runtime_execution import StrategyRuntimePreflight
from app.strategy_lab_v2.sandbox import (
    SandboxCommandPlan,
    sandbox_runtime_image_digest,
    validate_sandbox_command_plan,
)


class EngineExecutionDecision(StrEnum):
    READY = "ready"
    REJECT = "reject"


class NautilusExecutionScope(StrEnum):
    """Conformance scope required before one isolated Nautilus process runs."""

    FULL = "full"
    BACKTEST_COMPATIBILITY = "backtest_compatibility"
    BACKTEST_AUTHORITATIVE = "backtest_authoritative"
    FORWARD_COMPATIBILITY = "forward_compatibility"

    @property
    def required_checks(self) -> frozenset[ConformanceCheck]:
        if self in {
            NautilusExecutionScope.BACKTEST_COMPATIBILITY,
            NautilusExecutionScope.BACKTEST_AUTHORITATIVE,
        }:
            return frozenset(
                {
                    ConformanceCheck.MULTI_INSTRUMENT_ACCOUNTING,
                    ConformanceCheck.NATIVE_ORDER_FILL_COST,
                    ConformanceCheck.DETERMINISTIC_REPLAY,
                    ConformanceCheck.ENGINE_LIFECYCLE,
                }
            )
        return frozenset(ConformanceCheck)


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
    execution_scope: NautilusExecutionScope = NautilusExecutionScope.FULL

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
        if not isinstance(self.execution_scope, NautilusExecutionScope):
            raise TypeError("execution_scope must be a NautilusExecutionScope")
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
        if self.authoritative and self.execution_scope not in {
            NautilusExecutionScope.FULL,
            NautilusExecutionScope.BACKTEST_AUTHORITATIVE,
        }:
            raise ValueError("authoritative engine plans require an authoritative execution scope")
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
    execution_scope: NautilusExecutionScope = NautilusExecutionScope.FULL,
) -> NautilusExecutionPlan:
    """Resolve the final engine invocation gate without starting Nautilus.

    Backtest scopes intentionally exclude forward event-tape parity. Stable
    v2 or an exact-pinned release candidate may publish authoritative local
    backtests after the four simulator checks pass, without waiting for the
    separate forward adapter. Either channel may authorize broker-free full
    simulation after all five checks, including forward event-tape parity, pass.
    Prereleases never connect to brokers or control real capital.
    """

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
    if not isinstance(execution_scope, NautilusExecutionScope):
        raise TypeError("execution_scope must be a NautilusExecutionScope")
    require_sha256_digest(data_snapshot_fingerprint, field_name="data_snapshot_fingerprint")
    if not isinstance(requested_authoritative, bool):
        raise TypeError("requested_authoritative must be a boolean")

    reasons: list[str] = []
    try:
        validate_sandbox_command_plan(sandbox_plan)
    except ValueError:
        reasons.append("sandbox_plan_not_hardened")
    if authorization.trial_id.strip() == "" or authorization.attempt_id.strip() == "":
        reasons.append("authorization_identity_missing")
    if not runtime_preflight.accepted:
        reasons.append("runtime_isolation_not_accepted")
    if sandbox_plan.request_fingerprint != runtime_preflight.request_fingerprint:
        reasons.append("sandbox_runtime_request_mismatch")
    expected_conformance_report = evaluate_engine_conformance(conformance_evidence)
    if (
        conformance_evidence.fingerprint != conformance_report.evidence_fingerprint
        or expected_conformance_report.fingerprint != conformance_report.fingerprint
    ):
        reasons.append("conformance_evidence_report_mismatch")
    if conformance_evidence.engine_id.lower() != "nautilus":
        reasons.append("only_nautilus_engine_is_supported")
    required_checks = execution_scope.required_checks
    missing_required_checks = required_checks - conformance_evidence.passed_checks
    if missing_required_checks:
        reasons.append("required_engine_conformance_failed")
    if not conformance_report.release_pin_valid:
        reasons.append("isolated_v2_release_pin_required")
    if execution_scope is NautilusExecutionScope.FULL and not conformance_report.compatible:
        reasons.append("engine_conformance_failed")
    if requested_authoritative and not authorization.authoritative:
        reasons.append("authorization_is_not_authoritative")
    if requested_authoritative and execution_scope not in {
        NautilusExecutionScope.FULL,
        NautilusExecutionScope.BACKTEST_AUTHORITATIVE,
    }:
        reasons.append("authoritative_execution_scope_required")
    if (
        requested_authoritative
        and execution_scope is NautilusExecutionScope.FULL
        and not conformance_report.authoritative
    ):
        reasons.append("authoritative_conformance_required")
    if requested_authoritative and execution_scope is NautilusExecutionScope.BACKTEST_AUTHORITATIVE:
        if conformance_evidence.release_channel not in {
            EngineReleaseChannel.STABLE,
            EngineReleaseChannel.RELEASE_CANDIDATE,
        }:
            reasons.append("authoritative_backtest_release_channel_not_supported")
    if requested_authoritative:
        release_pin = conformance_evidence.release_pin
        if release_pin is None:
            reasons.append("isolated_release_pin_missing")
        else:
            try:
                runtime_image_digest = sandbox_runtime_image_digest(sandbox_plan)
            except (TypeError, ValueError):
                reasons.append("sandbox_runtime_image_unreadable")
            else:
                if runtime_image_digest != release_pin.runtime_image_digest:
                    reasons.append("nautilus_runtime_image_mismatch")
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
        execution_scope=execution_scope,
    )
