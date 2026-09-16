"""Engine-neutral construction of immutable run-result manifests.

Workers may obtain native metrics and output artifacts from an engine adapter,
but those observations must be bound to the already frozen scientific trial
before publication.  This module performs that binding without importing an
engine, writing artifacts, or publishing a result.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
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


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


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
        object.__setattr__(self, "artifact_content_digests", artifacts)

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
        if self.decision in {
            ResultMaterializationDecision.MATERIALIZE,
            ResultMaterializationDecision.REPLAY_EXISTING,
        } and self.manifest is None:
            raise ValueError("successful materialization requires a manifest")
        if self.decision in {
            ResultMaterializationDecision.CONFLICT,
            ResultMaterializationDecision.REJECT,
        } and not self.rejection_reason:
            raise ValueError("conflicts and rejections require a reason")
        if self.decision in {
            ResultMaterializationDecision.MATERIALIZE,
            ResultMaterializationDecision.REPLAY_EXISTING,
        } and self.rejection_reason:
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
    _aware(created_at, "created_at")

    candidate_fingerprint = content_digest(
        {
            "attempt_id": attempt.attempt_id,
            "created_at": created_at,
            "evidence": evidence,
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
