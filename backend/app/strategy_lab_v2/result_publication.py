"""Authoritative result publication gate over engine, runtime, and artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.conformance import (
    EngineConformanceEvidence,
    EngineConformanceReport,
)
from app.strategy_lab_v2.contracts import RunResultManifest
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
    if not isinstance(already_published, bool):
        raise TypeError("already_published must be a bool")

    reasons: list[str] = []
    if conformance_evidence.fingerprint != conformance_report.evidence_fingerprint:
        reasons.append("conformance_evidence_report_mismatch")
    if conformance_evidence.build_digest != result.engine_build_digest:
        reasons.append("engine_build_mismatch")
    if not conformance_report.authoritative:
        reasons.append("engine_conformance_not_authoritative")
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
