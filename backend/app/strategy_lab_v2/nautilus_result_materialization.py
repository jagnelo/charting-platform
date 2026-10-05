"""Bind verified Nautilus OOS metrics and reports into the canonical result."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from itertools import tee
from pathlib import Path
from typing import Any

from app.strategy_lab_v2.canonical import content_digest
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
    iter_verified_nautilus_account_equity_observations,
)
from app.strategy_lab_v2.nautilus_native_reports import NautilusNativeReportsReference
from app.strategy_lab_v2.nautilus_result_metrics import build_nautilus_oos_metric_set
from app.strategy_lab_v2.nautilus_session_equity import (
    NautilusSessionCloseEquityObservation,
    NautilusSessionEquityIntervalsArtifact,
    build_nautilus_session_equity_intervals_artifact,
)
from app.strategy_lab_v2.observations import (
    AccountCashBalanceObservation,
    AccountExposureObservation,
    ObservationPoint,
)
from app.strategy_lab_v2.rebalance import SessionCalendarSnapshot
from app.strategy_lab_v2.result_materialization import (
    EngineResultEvidence,
    ResultMaterializationDecision,
    ResultMaterializationResolution,
    materialize_run_result,
)


@dataclass(frozen=True, slots=True)
class NautilusOosResultMaterialization:
    """Canonical run-result resolution and any generated interval artifact bytes."""

    resolution: ResultMaterializationResolution
    generated_session_intervals: NautilusSessionEquityIntervalsArtifact | None = None

    @property
    def decision(self) -> ResultMaterializationDecision:
        return self.resolution.decision

    @property
    def manifest(self) -> RunResultManifest | None:
        return self.resolution.manifest

    @property
    def rejection_reason(self) -> str | None:
        return self.resolution.rejection_reason

    @property
    def candidate_fingerprint(self) -> str:
        return self.resolution.candidate_fingerprint


def _event_time_from_unix_nanoseconds(value: int) -> datetime:
    """Convert canonical event nanoseconds without float timestamp rounding."""

    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("event time must be non-negative integer nanoseconds")
    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(
        seconds=value // 1_000_000_000,
        microseconds=(value % 1_000_000_000) // 1_000,
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
    session_calendar: SessionCalendarSnapshot | None = None,
    session_close_observations: Sequence[NautilusSessionCloseEquityObservation] | None = None,
    session_periods_per_year: int | None = None,
) -> NautilusOosResultMaterialization:
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

    verified_observations = iter_verified_nautilus_account_equity_observations(
        equity_reference,
        equity_trace_path,
        expected_events=equity_expected_events,
    )
    (
        equity_observations,
        event_time_observations,
        session_observations,
        cash_observations_source,
        exposure_observations_source,
    ) = tee(
        verified_observations,
        5,
    )
    equity_marks = (item.account_equity for item in equity_observations)
    event_time_ns = (item.event_time_ns for item in event_time_observations)
    account_cash_observations = (
        AccountCashBalanceObservation(
            portfolio_fingerprint=equity_reference.portfolio_fingerprint,
            run_attempt_id=equity_reference.attempt_id,
            point=ObservationPoint(
                _event_time_from_unix_nanoseconds(item.event_time_ns),
                item.event_index,
            ),
            account_equity=item.account_equity,
            account_cash_balance=item.account_cash_balance,
            base_currency=equity_reference.base_currency,
            valuation_evidence_digest=equity_reference.artifact.content_digest,
        )
        for item in cash_observations_source
    )
    account_exposure_observations = (
        AccountExposureObservation(
            portfolio_fingerprint=equity_reference.portfolio_fingerprint,
            run_attempt_id=equity_reference.attempt_id,
            point=ObservationPoint(
                _event_time_from_unix_nanoseconds(item.event_time_ns),
                item.event_index,
            ),
            account_equity=item.account_equity,
            gross_base_exposure=item.gross_base_exposure,
            signed_net_base_exposure=item.signed_net_base_exposure,
            base_currency=equity_reference.base_currency,
            valuation_evidence_digest=equity_reference.artifact.content_digest,
        )
        for item in exposure_observations_source
    )
    session_intervals_artifact: NautilusSessionEquityIntervalsArtifact | None = None
    close_observations = tuple(session_close_observations or ())
    if session_calendar is not None and not isinstance(session_calendar, SessionCalendarSnapshot):
        raise TypeError("session_calendar must be a SessionCalendarSnapshot or None")
    if (session_calendar is None) != (session_periods_per_year is None):
        raise ValueError("session calendar and annualization must be supplied together")
    if session_periods_per_year is not None and (
        not isinstance(session_periods_per_year, int)
        or isinstance(session_periods_per_year, bool)
        or session_periods_per_year < 1
    ):
        raise ValueError("session_periods_per_year must be a positive integer")
    if session_calendar is not None or close_observations:
        if session_calendar is None:
            raise ValueError("native session-close observations require their frozen calendar")
        if (
            not isinstance(session_periods_per_year, int)
            or isinstance(session_periods_per_year, bool)
            or session_periods_per_year < 1
        ):
            raise ValueError("native session intervals require explicit periods_per_year")
        evidence_digest = content_digest(
            {
                "schema": "strategy-lab.nautilus-session-engine-evidence.v1",
                "trial_id": evidence.trial_id,
                "attempt_id": evidence.attempt_id,
                "engine_name": evidence.engine_name,
                "engine_version": evidence.engine_version,
                "engine_build_digest": evidence.engine_build_digest,
                "allocation_definition_version": evidence.allocation_definition_version,
                "dependency_catalog_digest": evidence.dependency_catalog_digest,
                "assumptions_digest": evidence.assumptions_digest,
                "authoritative": evidence.authoritative,
                "engine_provenance": evidence.engine_provenance,
                "equity_trace_digest": equity_reference.artifact.content_digest,
                "native_reports_digest": native_reports_reference.artifact.content_digest,
                "session_close_observations": close_observations,
            }
        )
        session_intervals_artifact = build_nautilus_session_equity_intervals_artifact(
            equity_reference,
            session_observations,
            close_observations,
            calendar=session_calendar,
            engine_evidence_digest=evidence_digest,
            session_periods_per_year=session_periods_per_year,
        )
    metric_set = build_nautilus_oos_metric_set(
        equity_reference,
        equity_marks,
        native_reports_reference,
        native_reports_path,
        event_time_ns=event_time_ns,
        account_cash_observations=account_cash_observations,
        account_exposure_observations=account_exposure_observations,
        created_at=created_at,
        portfolio=portfolio,
        session_equity_intervals=(
            None
            if session_intervals_artifact is None or not session_intervals_artifact.intervals
            else session_intervals_artifact.intervals
        ),
        session_calendar=(
            session_calendar
            if session_intervals_artifact is not None and session_intervals_artifact.intervals
            else None
        ),
        session_periods_per_year=(
            None
            if session_intervals_artifact is None or not session_intervals_artifact.intervals
            else session_intervals_artifact.session_periods_per_year
        ),
        session_label_range=(
            None
            if session_intervals_artifact is None
            or not session_intervals_artifact.intervals
            or not session_intervals_artifact.expected_session_labels
            else (
                session_intervals_artifact.expected_session_labels[0],
                session_intervals_artifact.expected_session_labels[-1],
            )
        ),
        suppress_event_sampled_risk=(
            session_intervals_artifact is not None and not session_intervals_artifact.intervals
        ),
    )

    artifacts_by_digest: dict[str, ArtifactManifest] = {}
    for artifact in (
        *tuple(output_artifacts),
        equity_reference.artifact,
        native_reports_reference.artifact,
        *(() if session_intervals_artifact is None else (session_intervals_artifact.artifact,)),
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
    return NautilusOosResultMaterialization(
        resolution=materialize_run_result(
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
        ),
        generated_session_intervals=session_intervals_artifact,
    )


__all__ = [
    "NautilusOosResultMaterialization",
    "materialize_nautilus_oos_run_result",
]
