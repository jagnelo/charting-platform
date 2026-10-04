"""Bind verified Nautilus OOS metrics and reports into the canonical result."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from app.strategy_lab_v2.contracts import (
    ArtifactManifest,
    DataSnapshot,
    PortfolioComposition,
    RunAttempt,
    RunResultManifest,
    ScientificTrial,
    StrategyPackage,
)
from app.strategy_lab_v2.nautilus_equity_trace import (
    NautilusAccountEquityTraceReference,
    iter_verified_nautilus_account_equity_marks,
)
from app.strategy_lab_v2.nautilus_native_reports import NautilusNativeReportsReference
from app.strategy_lab_v2.nautilus_result_metrics import build_nautilus_oos_metric_set
from app.strategy_lab_v2.result_materialization import (
    EngineResultEvidence,
    ResultMaterializationResolution,
    materialize_run_result,
)


def materialize_nautilus_oos_run_result(
    trial: ScientificTrial,
    attempt: RunAttempt,
    strategy_packages: Sequence[StrategyPackage],
    portfolio: PortfolioComposition,
    snapshot: DataSnapshot,
    evidence: EngineResultEvidence,
    equity_reference: NautilusAccountEquityTraceReference,
    equity_trace_path: str | Path,
    equity_expected_events: Iterable[Mapping[str, Any]],
    native_reports_reference: NautilusNativeReportsReference,
    native_reports_path: str | Path,
    output_artifacts: Sequence[ArtifactManifest],
    *,
    created_at: datetime,
    existing: RunResultManifest | None = None,
) -> ResultMaterializationResolution:
    """Create a reproducible Nautilus OOS manifest from verified run evidence.

    The two native Parquet references are made mandatory result artifacts and
    the execution evidence is rebound to the metric set calculated from them.
    Existing output artifacts are preserved; a digest collision or mismatched
    trial/attempt/portfolio/snapshot binding fails closed.
    """

    if not isinstance(evidence, EngineResultEvidence):
        raise TypeError("evidence must be an EngineResultEvidence")
    if evidence.engine_name.lower() != "nautilus":
        raise ValueError("Nautilus result materialization requires Nautilus evidence")
    if not isinstance(equity_reference, NautilusAccountEquityTraceReference):
        raise TypeError("equity_reference must be a NautilusAccountEquityTraceReference")
    if not isinstance(native_reports_reference, NautilusNativeReportsReference):
        raise TypeError("native_reports_reference must be a NautilusNativeReportsReference")
    if not isinstance(trial, ScientificTrial):
        raise TypeError("trial must be a ScientificTrial")
    if not isinstance(attempt, RunAttempt):
        raise TypeError("attempt must be a RunAttempt")
    if not isinstance(portfolio, PortfolioComposition):
        raise TypeError("portfolio must be a PortfolioComposition")
    if not isinstance(snapshot, DataSnapshot):
        raise TypeError("snapshot must be a DataSnapshot")

    if (
        equity_reference.trial_id != trial.trial_id
        or equity_reference.attempt_id != attempt.attempt_id
        or equity_reference.portfolio_fingerprint != portfolio.fingerprint
        or equity_reference.snapshot_fingerprint != snapshot.fingerprint
        or evidence.trial_id != trial.trial_id
        or evidence.attempt_id != attempt.attempt_id
    ):
        raise ValueError("Nautilus OOS result references do not match the result identities")

    metric_set = build_nautilus_oos_metric_set(
        equity_reference,
        iter_verified_nautilus_account_equity_marks(
            equity_reference,
            equity_trace_path,
            expected_events=equity_expected_events,
        ),
        native_reports_reference,
        native_reports_path,
        created_at=created_at,
        portfolio=portfolio,
    )

    artifacts_by_digest: dict[str, ArtifactManifest] = {}
    for artifact in (
        *tuple(output_artifacts),
        equity_reference.artifact,
        native_reports_reference.artifact,
    ):
        if not isinstance(artifact, ArtifactManifest):
            raise TypeError("output_artifacts must contain ArtifactManifest values")
        prior = artifacts_by_digest.get(artifact.content_digest)
        if prior is not None and prior != artifact:
            raise ValueError("Nautilus result artifact digest has conflicting manifests")
        artifacts_by_digest[artifact.content_digest] = artifact
    missing_evidence_artifacts = set(evidence.artifact_content_digests) - set(artifacts_by_digest)
    if missing_evidence_artifacts:
        raise ValueError("Nautilus result evidence references an unpublished output artifact")
    artifacts = tuple(artifacts_by_digest.values())
    bound_evidence = replace(
        evidence,
        metric_set_fingerprint=metric_set.fingerprint,
        artifact_content_digests=tuple(artifact.content_digest for artifact in artifacts),
    )
    return materialize_run_result(
        trial,
        attempt,
        strategy_packages,
        portfolio,
        snapshot,
        bound_evidence,
        metric_set,
        artifacts,
        created_at=created_at,
        existing=existing,
    )


__all__ = ["materialize_nautilus_oos_run_result"]
