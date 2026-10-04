"""Authoritative result publication gate over engine, runtime, and artifacts."""

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
from app.strategy_lab_v2.contracts import RunResultManifest
from app.strategy_lab_v2.engine_execution import (
    EngineExecutionDecision,
    NautilusExecutionPlan,
    NautilusExecutionScope,
)
from app.strategy_lab_v2.result_integrity import ResultIntegrityReceipt
from app.strategy_lab_v2.runtime import RuntimeIsolationReport


class ResultPublicationDecision(StrEnum):
    PUBLISH = "publish"
    REPLAY_EXISTING = "replay_existing"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class ResultPublicationPlan:
    """Storage-neutral decision for one authoritative result manifest."""

    result_fingerprint: str
    reproduction_fingerprint: str
    attempt_id: str
    engine_build_digest: str
    decision: ResultPublicationDecision
    rejection_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "result_fingerprint",
            "reproduction_fingerprint",
            "engine_build_digest",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        if not isinstance(self.attempt_id, str) or not self.attempt_id.strip():
            raise ValueError("attempt_id must not be empty")
        if not isinstance(self.decision, ResultPublicationDecision):
            raise TypeError("decision must be a ResultPublicationDecision")
        reasons = tuple(self.rejection_reasons)
        if len(reasons) != len(set(reasons)) or any(not reason.strip() for reason in reasons):
            raise ValueError("rejection reasons must be unique and non-empty")
        if self.decision is ResultPublicationDecision.REJECT and not reasons:
            raise ValueError("rejected publication plans require rejection reasons")
        if self.decision is not ResultPublicationDecision.REJECT and reasons:
            raise ValueError("accepted publication plans cannot contain rejection reasons")
        object.__setattr__(self, "rejection_reasons", reasons)

    @property
    def accepted(self) -> bool:
        return self.decision is not ResultPublicationDecision.REJECT

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def plan_result_publication(
    result: RunResultManifest,
    conformance_evidence: EngineConformanceEvidence,
    conformance_report: EngineConformanceReport,
    runtime_report: RuntimeIsolationReport,
    integrity: ResultIntegrityReceipt,
    *,
    execution_plan: NautilusExecutionPlan | None = None,
    already_published: bool = False,
) -> ResultPublicationPlan:
    """Gate result publication without writing artifacts or invoking an engine."""

    if not isinstance(result, RunResultManifest):
        raise TypeError("result must be a RunResultManifest")
    if not isinstance(conformance_evidence, EngineConformanceEvidence):
        raise TypeError("conformance_evidence must be an EngineConformanceEvidence")
    if not isinstance(conformance_report, EngineConformanceReport):
        raise TypeError("conformance_report must be an EngineConformanceReport")
    if not isinstance(runtime_report, RuntimeIsolationReport):
        raise TypeError("runtime_report must be a RuntimeIsolationReport")
    if not isinstance(integrity, ResultIntegrityReceipt):
        raise TypeError("integrity must be a ResultIntegrityReceipt")
    if execution_plan is not None and not isinstance(execution_plan, NautilusExecutionPlan):
        raise TypeError("execution_plan must be a NautilusExecutionPlan")
    if not isinstance(already_published, bool):
        raise TypeError("already_published must be a bool")

    reasons: list[str] = []
    if conformance_evidence.fingerprint != conformance_report.evidence_fingerprint:
        reasons.append("conformance_evidence_report_mismatch")
    expected_report = evaluate_engine_conformance(conformance_evidence)
    if expected_report.fingerprint != conformance_report.fingerprint:
        reasons.append("conformance_report_not_reproducible")
    if conformance_evidence.build_digest != result.engine_build_digest:
        reasons.append("engine_build_mismatch")
    if not result.engine_authoritative:
        reasons.append("result_manifest_not_authoritative")
    if (
        execution_plan is not None
        and execution_plan.execution_scope is NautilusExecutionScope.FULL
        and result.engine_authoritative is not conformance_report.authoritative
    ):
        reasons.append("result_engine_authority_mismatch")
    provenance = result.engine_provenance
    if result.engine_authoritative:
        if provenance is None:
            reasons.append("nautilus_result_provenance_missing")
        else:
            if provenance.release_channel is EngineReleaseChannel.DEVELOPMENT:
                reasons.append("development_release_channel_not_authoritative")
            if execution_plan is None:
                reasons.append("authoritative_execution_plan_missing")
            else:
                if execution_plan.decision is not EngineExecutionDecision.READY:
                    reasons.append("authoritative_execution_plan_rejected")
                if not execution_plan.authoritative:
                    reasons.append("authoritative_execution_plan_not_authoritative")
                if execution_plan.execution_scope not in {
                    NautilusExecutionScope.FULL,
                    NautilusExecutionScope.BACKTEST_AUTHORITATIVE,
                }:
                    reasons.append("authoritative_execution_scope_required")
                if execution_plan.execution_scope.value != provenance.execution_scope:
                    reasons.append("result_execution_scope_mismatch")
                if execution_plan.fingerprint != provenance.execution_plan_fingerprint:
                    reasons.append("result_execution_plan_mismatch")
                if execution_plan.trial_id != result.trial_id:
                    reasons.append("execution_plan_trial_mismatch")
                if execution_plan.attempt_id != result.attempt_id:
                    reasons.append("execution_plan_attempt_mismatch")
                if execution_plan.data_snapshot_fingerprint != result.snapshot_fingerprint:
                    reasons.append("execution_plan_snapshot_mismatch")
                if execution_plan.engine_id.lower() != result.engine_name.lower():
                    reasons.append("execution_plan_engine_mismatch")
                if execution_plan.engine_version != result.engine_version:
                    reasons.append("execution_plan_version_mismatch")
                if execution_plan.engine_build_digest != result.engine_build_digest:
                    reasons.append("execution_plan_build_mismatch")
                if (
                    execution_plan.conformance_report_fingerprint
                    != provenance.conformance_report_fingerprint
                ):
                    reasons.append("execution_plan_conformance_mismatch")
            pin = conformance_evidence.release_pin
            if pin is None:
                reasons.append("nautilus_release_pin_missing")
            else:
                if provenance.release_pin != pin:
                    reasons.append("result_release_pin_mismatch")
                if provenance.release_channel is not conformance_evidence.release_channel:
                    reasons.append("result_release_channel_mismatch")
                if provenance.conformance_evidence_fingerprint != conformance_evidence.fingerprint:
                    reasons.append("result_conformance_evidence_mismatch")
                if provenance.conformance_report_fingerprint != conformance_report.fingerprint:
                    reasons.append("result_conformance_report_mismatch")
            if conformance_report.release_channel is EngineReleaseChannel.DEVELOPMENT:
                reasons.append("authoritative_release_channel_not_supported")
            if not conformance_report.release_pin_valid:
                reasons.append("isolated_v2_release_pin_required")
            if execution_plan is not None:
                missing_scope_checks = (
                    execution_plan.execution_scope.required_checks
                    - conformance_evidence.passed_checks
                )
                if missing_scope_checks:
                    reasons.append("required_engine_conformance_failed")
                if (
                    execution_plan.execution_scope is NautilusExecutionScope.FULL
                    and not conformance_report.authoritative
                ):
                    reasons.append("engine_conformance_not_authoritative")
                if (
                    execution_plan.execution_scope is NautilusExecutionScope.BACKTEST_AUTHORITATIVE
                    and conformance_report.missing_checks
                    - {ConformanceCheck.FORWARD_EVENT_TAPE_PARITY}
                ):
                    reasons.append("backtest_conformance_has_unapproved_gaps")
    if not runtime_report.accepted:
        reasons.append("runtime_isolation_not_accepted")
    if integrity.result_fingerprint != result.fingerprint:
        reasons.append("result_integrity_receipt_mismatch")
    if not integrity.accepted:
        reasons.append("result_artifacts_not_integrity_verified")
    decision = (
        ResultPublicationDecision.REJECT
        if reasons
        else (
            ResultPublicationDecision.REPLAY_EXISTING
            if already_published
            else ResultPublicationDecision.PUBLISH
        )
    )
    return ResultPublicationPlan(
        result_fingerprint=result.fingerprint,
        reproduction_fingerprint=result.reproduction_fingerprint,
        attempt_id=result.attempt_id,
        engine_build_digest=result.engine_build_digest,
        decision=decision,
        rejection_reasons=tuple(dict.fromkeys(reasons)),
    )
