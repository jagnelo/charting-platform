from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

from app.strategy_lab_v2.allocation import ALLOCATION_DEFINITION_VERSION
from app.strategy_lab_v2.artifacts import artifact_content_digest, verify_artifact_payload
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import (
    CapabilityCell,
    CapabilityRequirement,
    preflight_capabilities,
)
from app.strategy_lab_v2.conformance import (
    ConformanceCheck,
    EngineConformanceEvidence,
    EngineConformanceReport,
    EngineReleaseChannel,
    evaluate_engine_conformance,
)
from app.strategy_lab_v2.contracts import (
    AdjustmentMode,
    ArtifactManifest,
    AttemptState,
    DataSeriesManifest,
    DataSnapshot,
    EventGranularity,
    MetricBasis,
    MetricSet,
    MetricValue,
    PortfolioComponent,
    PortfolioComposition,
    ProductClass,
    RunAttempt,
    RunResultManifest,
    ScientificTrial,
    SharedRiskPolicy,
    StrategyPackage,
    StrategyPackageFormat,
    StrategyVersion,
)
from app.strategy_lab_v2.rebalance import (
    CalendarRebalancePolicy,
    RebalanceCadence,
    RebalanceTrigger,
)
from app.strategy_lab_v2.result_integrity import (
    ResultIntegrityReceipt,
    verify_run_result_artifacts,
)
from app.strategy_lab_v2.result_publication import (
    ResultPublicationDecision,
    plan_result_publication,
)
from app.strategy_lab_v2.runtime import (
    RuntimeIsolationProfile,
    RuntimeIsolationReport,
    RuntimeIsolationRequest,
    preflight_runtime_isolation,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)
START = datetime(2020, 1, 1, tzinfo=UTC)
END = datetime(2022, 1, 1, tzinfo=UTC)
SOURCE = content_digest({"source": "strategy"})
EVIDENCE = content_digest({"provider": "fixture"})
BUILD = content_digest({"engine": "nautilus", "build": "stable"})
DEPENDENCY = content_digest({"dependency": "numpy-2.0.0"})


def _result() -> tuple[
    RunResultManifest,
    EngineConformanceEvidence,
    EngineConformanceReport,
    RuntimeIsolationReport,
    ResultIntegrityReceipt,
]:
    requirement = CapabilityRequirement(
        instrument_id="US.AAPL",
        product_class=ProductClass.EQUITY,
        event_granularity=EventGranularity.BAR,
        event_type="ohlcv",
        timeframe="1d",
        start=START,
        end=END,
        adjustment=AdjustmentMode.SPLIT_ADJUSTED,
        session="regular",
        feed="consolidated",
        execution_model="bar-close-v1",
        account_model="cash-equity-v1",
        corporate_action_semantics="split-adjusted-v1",
    )
    cell = CapabilityCell(
        instrument_id="US.AAPL",
        product_class=ProductClass.EQUITY,
        event_granularities=frozenset({EventGranularity.BAR}),
        event_types=frozenset({"ohlcv"}),
        timeframes=frozenset({"1d"}),
        adjustments=frozenset({AdjustmentMode.SPLIT_ADJUSTED}),
        sessions=frozenset({"regular"}),
        feeds=frozenset({"consolidated"}),
        execution_models=frozenset({"bar-close-v1"}),
        account_models=frozenset({"cash-equity-v1"}),
        corporate_action_semantics=frozenset({"split-adjusted-v1"}),
        history_start=START,
        history_end=END,
        evidence_digest=EVIDENCE,
    )
    report = preflight_capabilities((requirement,), (cell,))
    series = DataSeriesManifest(
        instrument_id="US.AAPL",
        event_type="ohlcv",
        event_granularity=EventGranularity.BAR,
        timeframe="1d",
        session="regular",
        feed="consolidated",
        start=START,
        end=END,
        adjustment=AdjustmentMode.SPLIT_ADJUSTED,
        corporate_action_semantics="split-adjusted-v1",
        coverage_evidence_digest=content_digest({"coverage": "verified"}),
        content_digest=content_digest({"bars": 1}),
        row_count=100,
    )
    snapshot = DataSnapshot("snapshot-1", "provider-snapshot-1", report, (series,), NOW)
    strategy = StrategyVersion("strategy-1", "v1", "2.0", SOURCE)
    component = PortfolioComponent(
        "component-1", strategy.fingerprint, ("US.AAPL",), Decimal("1.0")
    )
    portfolio = PortfolioComposition(
        "portfolio-1",
        "v1",
        Decimal("100000"),
        "USD",
        (component,),
        rebalance_policy=CalendarRebalancePolicy(
            calendar_id="XNYS",
            calendar_fingerprint=content_digest("XNYS"),
            cadence=RebalanceCadence.MONTHLY,
            trigger=RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS,
        ),
        shared_risk_policy=SharedRiskPolicy(),
    )
    package = StrategyPackage(
        "package-1",
        strategy.fingerprint,
        StrategyPackageFormat.SOURCE_ARCHIVE,
        content_digest({"archive": 1}),
        content_digest({"manifest": 1}),
        content_digest({"lock": 1}),
        10,
        "strategy.main:Strategy",
        "2.0",
        "cp312-manylinux",
    )
    trial = ScientificTrial.create(
        experiment_fingerprint=content_digest({"experiment": 1}),
        snapshot_fingerprint=snapshot.fingerprint,
        preflight_report=report,
        parameter_set={"lookback": 20},
        seed=1,
    )
    attempt = RunAttempt("attempt-1", trial.trial_id, 1, AttemptState.SUCCEEDED, NOW)
    metric_set = MetricSet(
        "metrics-1",
        trial.trial_id,
        attempt.attempt_id,
        "strategy-lab.metrics.v2",
        (MetricValue("return", Decimal("0.1"), "fraction", "strategy-lab.metrics.v2", MetricBasis.NET, 10),),
        NOW,
    )
    payload = b"result"
    artifact_digest = artifact_content_digest(payload)
    artifact = ArtifactManifest(
        artifact_digest, len(payload), "application/octet-stream", "1", artifact_digest
    )
    result = RunResultManifest(
        trial=trial,
        attempt=attempt,
        strategy_packages=(package,),
        portfolio=portfolio,
        snapshot=snapshot,
        engine_name="nautilus",
        engine_version="2.0.0",
        engine_build_digest=BUILD,
        allocation_definition_version=ALLOCATION_DEFINITION_VERSION,
        dependency_catalog_digest=content_digest({"catalog": 1}),
        assumptions_digest=content_digest({"assumptions": 1}),
        metric_set=metric_set,
        output_artifacts=(artifact,),
        created_at=NOW,
    )
    integrity = verify_run_result_artifacts(
        result,
        (verify_artifact_payload(artifact, payload),),
    )
    evidence = EngineConformanceEvidence(
        "nautilus",
        "2.0.0",
        BUILD,
        EngineReleaseChannel.STABLE,
        content_digest({"fixture": "all"}),
        frozenset(ConformanceCheck),
        NOW,
    )
    conformance = evaluate_engine_conformance(evidence)
    runtime = preflight_runtime_isolation(
        RuntimeIsolationProfile(BUILD, "cp312-manylinux", allowed_dependency_digests=frozenset({DEPENDENCY})),
        RuntimeIsolationRequest(attempt.attempt_id, (DEPENDENCY,)),
    )
    return result, evidence, conformance, runtime, integrity


def test_result_publication_requires_all_authoritative_gates() -> None:
    result, evidence, conformance, runtime, integrity = _result()
    plan = plan_result_publication(result, evidence, conformance, runtime, integrity)
    assert plan.decision is ResultPublicationDecision.PUBLISH
    assert plan.accepted
    assert plan.attempt_id == result.attempt_id
    replay = plan_result_publication(
        result, evidence, conformance, runtime, integrity, already_published=True
    )
    assert replay.decision is ResultPublicationDecision.REPLAY_EXISTING


def test_result_publication_rejects_non_authoritative_or_unverified_inputs() -> None:
    result, evidence, conformance, runtime, integrity = _result()
    candidate = evaluate_engine_conformance(
        EngineConformanceEvidence(
            evidence.engine_id,
            evidence.engine_version,
            evidence.build_digest,
            EngineReleaseChannel.RELEASE_CANDIDATE,
            evidence.fixture_digest,
            evidence.passed_checks,
            evidence.tested_at,
        )
    )
    rejected = plan_result_publication(result, evidence, candidate, runtime, integrity)
    assert rejected.decision is ResultPublicationDecision.REJECT
    assert "engine_conformance_not_authoritative" in rejected.rejection_reasons

    failed_integrity = verify_run_result_artifacts(result, ())
    rejected = plan_result_publication(result, evidence, conformance, runtime, failed_integrity)
    assert "result_artifacts_not_integrity_verified" in rejected.rejection_reasons


def test_result_publication_rejects_build_or_runtime_mismatch() -> None:
    result, evidence, conformance, runtime, integrity = _result()
    bad_runtime = preflight_runtime_isolation(
        RuntimeIsolationProfile(BUILD, "cp312-manylinux", network_disabled=False),
        RuntimeIsolationRequest(result.attempt_id),
    )
    rejected = plan_result_publication(result, evidence, conformance, bad_runtime, integrity)
    assert rejected.decision is ResultPublicationDecision.REJECT
    assert "runtime_isolation_not_accepted" in rejected.rejection_reasons
    mismatched = replace(
        result,
        engine_build_digest=content_digest({"other": "build"}),
    )
    rejected = plan_result_publication(
        mismatched,
        evidence,
        conformance,
        runtime,
        integrity,
    )
    assert "engine_build_mismatch" in rejected.rejection_reasons
