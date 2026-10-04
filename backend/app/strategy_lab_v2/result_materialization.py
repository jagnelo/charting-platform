"""Engine-neutral construction of immutable run-result manifests.

Workers may obtain native metrics and output artifacts from an engine adapter,
but those observations must be bound to the already frozen scientific trial
before publication.  This module performs that binding without importing an
engine, writing artifacts, or publishing a result.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.conformance import (
    EngineConformanceEvidence,
    EngineConformanceReport,
    EngineReleaseChannel,
    NautilusResultProvenance,
    evaluate_engine_conformance,
)
from app.strategy_lab_v2.contracts import (
    ArtifactManifest,
    AttemptState,
    DataSnapshot,
    MetricSet,
    PortfolioComposition,
    RunAttempt,
    RunResultManifest,
    ScientificTrial,
    StrategyPackage,
)
from app.strategy_lab_v2.engine_execution import (
    EngineExecutionDecision,
    NautilusExecutionPlan,
    NautilusExecutionScope,
)
from app.strategy_lab_v2.sandbox import SandboxCommandPlan, sandbox_runtime_image_digest


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def build_nautilus_result_provenance(
    execution_plan: NautilusExecutionPlan,
    conformance_evidence: EngineConformanceEvidence,
    conformance_report: EngineConformanceReport,
    sandbox_plan: SandboxCommandPlan,
) -> NautilusResultProvenance:
    """Build result provenance only from a matching gated Nautilus invocation."""

    if not isinstance(execution_plan, NautilusExecutionPlan):
        raise TypeError("execution_plan must be a NautilusExecutionPlan")
    if not isinstance(conformance_evidence, EngineConformanceEvidence):
        raise TypeError("conformance_evidence must be an EngineConformanceEvidence")
    if not isinstance(conformance_report, EngineConformanceReport):
        raise TypeError("conformance_report must be an EngineConformanceReport")
    if not isinstance(sandbox_plan, SandboxCommandPlan):
        raise TypeError("sandbox_plan must be a SandboxCommandPlan")
    if execution_plan.decision is not EngineExecutionDecision.READY:
        raise ValueError("result provenance requires a ready Nautilus execution plan")
    if execution_plan.engine_id.lower() != "nautilus":
        raise ValueError("result provenance requires a Nautilus execution plan")
    expected_report = evaluate_engine_conformance(conformance_evidence)
    if (
        conformance_evidence.fingerprint != conformance_report.evidence_fingerprint
        or expected_report.fingerprint != conformance_report.fingerprint
        or execution_plan.conformance_report_fingerprint != conformance_report.fingerprint
    ):
        raise ValueError("result provenance conformance evidence does not match its plan")
    if (
        execution_plan.engine_version != conformance_evidence.engine_version
        or execution_plan.engine_build_digest != conformance_evidence.build_digest
        or execution_plan.engine_id.lower() != conformance_evidence.engine_id.lower()
    ):
        raise ValueError("result provenance engine identity does not match conformance evidence")
    if execution_plan.sandbox_plan_fingerprint != sandbox_plan.fingerprint:
        raise ValueError("result provenance sandbox plan does not match execution plan")
    if not conformance_report.release_pin_valid or conformance_evidence.release_pin is None:
        raise ValueError("result provenance requires a valid isolated v2 release pin")
    if (
        sandbox_runtime_image_digest(sandbox_plan)
        != conformance_evidence.release_pin.runtime_image_digest
    ):
        raise ValueError("result provenance sandbox image does not match the release pin")
    if execution_plan.execution_scope.required_checks - conformance_evidence.passed_checks:
        raise ValueError("result provenance is missing required scope conformance checks")
    if execution_plan.authoritative:
        if execution_plan.execution_scope not in {
            NautilusExecutionScope.FULL,
            NautilusExecutionScope.BACKTEST_AUTHORITATIVE,
        }:
            raise ValueError("authoritative result provenance requires an authoritative scope")
        if (
            execution_plan.execution_scope is NautilusExecutionScope.FULL
            and not conformance_report.authoritative
        ):
            raise ValueError("full-scope authority requires complete conformance")
        if conformance_evidence.release_channel is not EngineReleaseChannel.STABLE:
            raise ValueError("stable Nautilus v2 is required for authoritative result provenance")
    return NautilusResultProvenance(
        release_pin=conformance_evidence.release_pin,
        release_channel=conformance_evidence.release_channel,
        conformance_evidence_fingerprint=conformance_evidence.fingerprint,
        conformance_report_fingerprint=conformance_report.fingerprint,
        execution_plan_fingerprint=execution_plan.fingerprint,
        execution_scope=execution_plan.execution_scope.value,
    )


@dataclass(frozen=True, slots=True)
class EngineResultEvidence:
    """Typed provenance emitted by an engine adapter for one attempt."""

    trial_id: str
    attempt_id: str
    engine_name: str
    engine_version: str
    engine_build_digest: str
    allocation_definition_version: str
    dependency_catalog_digest: str
    assumptions_digest: str
    metric_set_fingerprint: str
    artifact_content_digests: tuple[str, ...]
    observed_at: datetime
    authoritative: bool = False
    engine_provenance: NautilusResultProvenance | None = None

    def __post_init__(self) -> None:
        require_sha256_digest(self.trial_id, field_name="trial_id")
        _nonempty(self.attempt_id, "attempt_id")
        for name in (
            "engine_name",
            "engine_version",
            "allocation_definition_version",
        ):
            _nonempty(getattr(self, name), name)
        for name in (
            "engine_build_digest",
            "dependency_catalog_digest",
            "assumptions_digest",
            "metric_set_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        artifacts = tuple(self.artifact_content_digests)
        if not artifacts:
            raise ValueError("engine result evidence requires output artifacts")
        for digest in artifacts:
            require_sha256_digest(digest, field_name="artifact_content_digest")
        if len(artifacts) != len(set(artifacts)):
            raise ValueError("engine result artifact digests must be unique")
        _aware(self.observed_at, "observed_at")
        if not isinstance(self.authoritative, bool):
            raise TypeError("engine result authoritative must be a boolean")
        if self.engine_name.lower() == "nautilus":
            if not isinstance(self.engine_provenance, NautilusResultProvenance):
                raise ValueError("Nautilus result evidence requires exact execution provenance")
            if self.engine_provenance.release_pin.package_version != self.engine_version:
                raise ValueError("Nautilus result version must match its release pin")
            if self.authoritative and self.engine_provenance.execution_scope not in {
                "full",
                "backtest_authoritative",
            }:
                raise ValueError("authoritative Nautilus evidence requires an authoritative scope")
            if self.authoritative and self.engine_provenance.release_channel.value != "stable":
                raise ValueError("stable Nautilus v2 is required for authoritative result evidence")
        elif self.engine_provenance is not None:
            raise ValueError("Nautilus provenance cannot be attached to another engine")
        object.__setattr__(self, "observed_at", self.observed_at.astimezone(UTC))
        object.__setattr__(self, "artifact_content_digests", tuple(sorted(artifacts)))

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class ResultMaterializationDecision(StrEnum):
    MATERIALIZE = "materialize"
    REPLAY_EXISTING = "replay_existing"
    CONFLICT = "conflict"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class ResultMaterializationResolution:
    """Candidate manifest and decision for a storage adapter."""

    decision: ResultMaterializationDecision
    candidate_fingerprint: str
    manifest: RunResultManifest | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ResultMaterializationDecision):
            raise TypeError("decision must be a ResultMaterializationDecision")
        require_sha256_digest(self.candidate_fingerprint, field_name="candidate_fingerprint")
        if self.manifest is not None and not isinstance(self.manifest, RunResultManifest):
            raise TypeError("manifest must be a RunResultManifest")
        if (
            self.decision
            in {
                ResultMaterializationDecision.MATERIALIZE,
                ResultMaterializationDecision.REPLAY_EXISTING,
            }
            and self.manifest is None
        ):
            raise ValueError("successful materialization requires a manifest")
        if (
            self.decision
            in {
                ResultMaterializationDecision.CONFLICT,
                ResultMaterializationDecision.REJECT,
            }
            and not self.rejection_reason
        ):
            raise ValueError("conflicts and rejections require a reason")
        if (
            self.decision
            in {
                ResultMaterializationDecision.MATERIALIZE,
                ResultMaterializationDecision.REPLAY_EXISTING,
            }
            and self.rejection_reason
        ):
            raise ValueError("successful materialization cannot contain a rejection reason")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def materialize_run_result(
    trial: ScientificTrial,
    attempt: RunAttempt,
    strategy_packages: Sequence[StrategyPackage],
    portfolio: PortfolioComposition,
    snapshot: DataSnapshot,
    evidence: EngineResultEvidence,
    metric_set: MetricSet,
    output_artifacts: Sequence[ArtifactManifest],
    *,
    created_at: datetime,
    existing: RunResultManifest | None = None,
) -> ResultMaterializationResolution:
    """Bind engine evidence to a reproducible result manifest.

    The returned manifest is still unpublished.  Exact retries replay an
    existing identical manifest; a changed candidate for the same attempt is
    a conflict and cannot overwrite the prior result.
    """

    values = (
        trial,
        attempt,
        strategy_packages,
        portfolio,
        snapshot,
        evidence,
        metric_set,
        output_artifacts,
    )
    expected = (
        ScientificTrial,
        RunAttempt,
        Sequence,
        PortfolioComposition,
        DataSnapshot,
        EngineResultEvidence,
        MetricSet,
        Sequence,
    )
    names = (
        "trial",
        "attempt",
        "strategy_packages",
        "portfolio",
        "snapshot",
        "evidence",
        "metric_set",
        "output_artifacts",
    )
    for name, value, expected_type in zip(names, values, expected, strict=True):
        if not isinstance(value, expected_type):
            raise TypeError(f"{name} must be a {expected_type.__name__}")
    if existing is not None and not isinstance(existing, RunResultManifest):
        raise TypeError("existing must be a RunResultManifest")
    packages = tuple(strategy_packages)
    artifacts = tuple(output_artifacts)
    if any(not isinstance(item, StrategyPackage) for item in packages):
        raise TypeError("strategy_packages must contain StrategyPackage values")
    if any(not isinstance(item, ArtifactManifest) for item in artifacts):
        raise TypeError("output_artifacts must contain ArtifactManifest values")
    packages = tuple(sorted(packages, key=lambda item: item.fingerprint))
    artifacts = tuple(sorted(artifacts, key=lambda item: item.content_digest))
    _aware(created_at, "created_at")
    created_at = created_at.astimezone(UTC)

    candidate_fingerprint = content_digest(
        {
            "attempt_id": attempt.attempt_id,
            "created_at": created_at,
            "evidence": evidence,
            "engine_authoritative": evidence.authoritative,
            "metric_set": metric_set,
            "output_artifacts": artifacts,
            "portfolio": portfolio,
            "snapshot": snapshot,
            "strategy_packages": packages,
            "trial": trial,
        }
    )
    reasons: list[str] = []
    if attempt.state is not AttemptState.SUCCEEDED:
        reasons.append("result_attempt_not_succeeded")
    if attempt.trial_id != trial.trial_id or evidence.trial_id != trial.trial_id:
        reasons.append("result_trial_identity_mismatch")
    if evidence.attempt_id != attempt.attempt_id:
        reasons.append("result_attempt_identity_mismatch")
    if metric_set.trial_id != trial.trial_id:
        reasons.append("result_metric_trial_mismatch")
    if metric_set.attempt_id != attempt.attempt_id:
        reasons.append("result_metric_attempt_mismatch")
    if metric_set.fingerprint != evidence.metric_set_fingerprint:
        reasons.append("result_metric_evidence_mismatch")
    artifact_digests = tuple(item.content_digest for item in artifacts)
    if artifact_digests != evidence.artifact_content_digests:
        reasons.append("result_artifact_evidence_mismatch")
    if snapshot.fingerprint != trial.snapshot_fingerprint:
        reasons.append("result_snapshot_identity_mismatch")
    if snapshot.preflight_report.fingerprint != trial.preflight_fingerprint:
        reasons.append("result_snapshot_preflight_mismatch")
    if reasons:
        return _reject(candidate_fingerprint, reasons)

    manifest = RunResultManifest(
        trial=trial,
        attempt=attempt,
        strategy_packages=packages,
        portfolio=portfolio,
        snapshot=snapshot,
        engine_name=evidence.engine_name,
        engine_version=evidence.engine_version,
        engine_build_digest=evidence.engine_build_digest,
        allocation_definition_version=evidence.allocation_definition_version,
        dependency_catalog_digest=evidence.dependency_catalog_digest,
        assumptions_digest=evidence.assumptions_digest,
        metric_set=metric_set,
        output_artifacts=artifacts,
        created_at=created_at,
        engine_authoritative=evidence.authoritative,
        engine_provenance=evidence.engine_provenance,
    )
    candidate_fingerprint = manifest.fingerprint
    if existing is None:
        return ResultMaterializationResolution(
            ResultMaterializationDecision.MATERIALIZE,
            candidate_fingerprint,
            manifest,
        )
    if existing.attempt_id != attempt.attempt_id:
        return _reject(candidate_fingerprint, ("existing_result_attempt_mismatch",))
    if existing.fingerprint != candidate_fingerprint:
        return ResultMaterializationResolution(
            ResultMaterializationDecision.CONFLICT,
            candidate_fingerprint,
            rejection_reason="attempt is already bound to different result content",
        )
    return ResultMaterializationResolution(
        ResultMaterializationDecision.REPLAY_EXISTING,
        candidate_fingerprint,
        existing,
    )


def _reject(candidate_fingerprint: str, reasons: Sequence[str]) -> ResultMaterializationResolution:
    reason = ", ".join(sorted(set(reasons)))
    return ResultMaterializationResolution(
        ResultMaterializationDecision.REJECT,
        candidate_fingerprint,
        rejection_reason=reason,
    )
