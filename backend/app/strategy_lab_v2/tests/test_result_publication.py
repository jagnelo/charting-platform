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
    NAUTILUS_V2_RC_WHEEL_SHA256,
    ConformanceCheck,
    EngineConformanceEvidence,
    EngineConformanceReport,
    EngineReleaseChannel,
    NautilusReleasePin,
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
from app.strategy_lab_v2.engine_execution import (
    EngineExecutionDecision,
    NautilusExecutionPlan,
    NautilusExecutionScope,
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
from app.strategy_lab_v2.result_materialization import build_nautilus_result_provenance
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
from app.strategy_lab_v2.sandbox import SandboxCommandPlan

NOW = datetime(2024, 1, 1, tzinfo=UTC)
START = datetime(2020, 1, 1, tzinfo=UTC)
END = datetime(2022, 1, 1, tzinfo=UTC)
SOURCE = content_digest({"source": "strategy"})
EVIDENCE = content_digest({"provider": "fixture"})
BUILD = content_digest({"engine": "nautilus", "build": "stable"})
DEPENDENCY = content_digest({"dependency": "numpy-2.0.0"})
NAUTILUS_PIN = NautilusReleasePin(
    package_version="2.0.0",
    release_tag="v2.0.0",
    source_digest=content_digest("nautilus-source"),
    wheel_digest=content_digest("nautilus-wheel"),
    runtime_image_digest=content_digest("nautilus-runtime"),
    python_version="3.12.11",
    rust_version="1.88.0",
    legacy_runtime_isolated=True,
)


def _sandbox_plan(pin: NautilusReleasePin, attempt_id: str) -> SandboxCommandPlan:
    return SandboxCommandPlan(
        content_digest("runtime-request"),
        content_digest("profile"),
        (
            "docker",
            "run",
            "--rm",
            "--init",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--user=65532:65532",
            "--workdir=/workspace",
            "--memory=536870912",
            "--ulimit=cpu=300",
            "--ulimit=fsize=1024",
            "--pids-limit=256",
            "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=67108864",
            "--mount=type=bind,src=/tmp/strategy-input,dst=/inputs/bundle,readonly",
            "--mount=type=bind,src=/tmp/strategy-output,dst=/outputs/result",
            f"--env=STRATEGY_ATTEMPT_ID={attempt_id}",
            f"--env=STRATEGY_INPUT_BUNDLE_DIGEST={content_digest('inputs')}",
            f"runtime@{pin.runtime_image_digest}",
            "python",
            "runner",
        ),
        10,
        1024,
    )


def _result() -> (
    tuple[
        RunResultManifest,
        EngineConformanceEvidence,
        EngineConformanceReport,
        RuntimeIsolationReport,
        ResultIntegrityReceipt,
        NautilusExecutionPlan,
    ]
):
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
        (
            MetricValue(
                "return", Decimal("0.1"), "fraction", "strategy-lab.metrics.v2", MetricBasis.NET, 10
            ),
        ),
        NOW,
    )
    payload = b"result"
    artifact_digest = artifact_content_digest(payload)
    artifact = ArtifactManifest(
        artifact_digest, len(payload), "application/octet-stream", "1", artifact_digest
    )
    evidence = EngineConformanceEvidence(
        "nautilus",
        "2.0.0",
        BUILD,
        EngineReleaseChannel.STABLE,
        content_digest({"fixture": "all"}),
        frozenset(ConformanceCheck),
        NOW,
        NAUTILUS_PIN,
    )
    conformance = evaluate_engine_conformance(evidence)
    sandbox_plan = _sandbox_plan(NAUTILUS_PIN, attempt.attempt_id)
    execution_plan = NautilusExecutionPlan(
        trial.trial_id,
        attempt.attempt_id,
        snapshot.fingerprint,
        "nautilus",
        "2.0.0",
        BUILD,
        content_digest("authorization"),
        content_digest("runtime-preflight"),
        conformance.fingerprint,
        sandbox_plan.fingerprint,
        EngineExecutionDecision.READY,
        True,
        execution_scope=NautilusExecutionScope.FULL,
    )
    provenance = build_nautilus_result_provenance(
        execution_plan, evidence, conformance, sandbox_plan
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
        engine_authoritative=True,
        engine_provenance=provenance,
    )
    integrity = verify_run_result_artifacts(
        result,
        (verify_artifact_payload(artifact, payload),),
    )
    runtime = preflight_runtime_isolation(
        RuntimeIsolationProfile(
            BUILD, "cp312-manylinux", allowed_dependency_digests=frozenset({DEPENDENCY})
        ),
        RuntimeIsolationRequest(attempt.attempt_id, (DEPENDENCY,)),
    )
    return result, evidence, conformance, runtime, integrity, execution_plan


def test_result_publication_requires_all_authoritative_gates() -> None:
    result, evidence, conformance, runtime, integrity, execution_plan = _result()
    plan = plan_result_publication(
        result, evidence, conformance, runtime, integrity, execution_plan=execution_plan
    )
    assert plan.decision is ResultPublicationDecision.PUBLISH
    assert plan.accepted
    assert plan.attempt_id == result.attempt_id
    replay = plan_result_publication(
        result,
        evidence,
        conformance,
        runtime,
        integrity,
        execution_plan=execution_plan,
        already_published=True,
    )
    assert replay.decision is ResultPublicationDecision.REPLAY_EXISTING


def test_result_publication_rejects_non_authoritative_or_unverified_inputs() -> None:
    result, evidence, conformance, runtime, integrity, execution_plan = _result()
    candidate = evaluate_engine_conformance(
        EngineConformanceEvidence(
            evidence.engine_id,
            evidence.engine_version,
            evidence.build_digest,
            EngineReleaseChannel.RELEASE_CANDIDATE,
            evidence.fixture_digest,
            evidence.passed_checks,
            evidence.tested_at,
            evidence.release_pin,
        )
    )
    rejected = plan_result_publication(
        result, evidence, candidate, runtime, integrity, execution_plan=execution_plan
    )
    assert rejected.decision is ResultPublicationDecision.REJECT
    assert "engine_conformance_not_authoritative" in rejected.rejection_reasons
    assert "isolated_v2_release_pin_required" in rejected.rejection_reasons

    non_authoritative_manifest = replace(result, engine_authoritative=False)
    rejected_manifest = plan_result_publication(
        non_authoritative_manifest,
        evidence,
        conformance,
        runtime,
        integrity,
        execution_plan=execution_plan,
    )
    assert rejected_manifest.decision is ResultPublicationDecision.REJECT
    assert "result_manifest_not_authoritative" in rejected_manifest.rejection_reasons
    assert "result_engine_authority_mismatch" in rejected_manifest.rejection_reasons

    failed_integrity = verify_run_result_artifacts(result, ())
    rejected = plan_result_publication(result, evidence, conformance, runtime, failed_integrity)
    assert "result_artifacts_not_integrity_verified" in rejected.rejection_reasons


def test_result_publication_rejects_build_or_runtime_mismatch() -> None:
    result, evidence, conformance, runtime, integrity, execution_plan = _result()
    bad_runtime = preflight_runtime_isolation(
        RuntimeIsolationProfile(BUILD, "cp312-manylinux", network_disabled=False),
        RuntimeIsolationRequest(result.attempt_id),
    )
    rejected = plan_result_publication(
        result, evidence, conformance, bad_runtime, integrity, execution_plan=execution_plan
    )
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
        execution_plan=execution_plan,
    )
    assert "engine_build_mismatch" in rejected.rejection_reasons


def test_release_candidate_builds_backtest_authoritative_result_provenance() -> None:
    result, _stable_evidence, _, runtime, _, _ = _result()
    backtest_checks = frozenset(
        check
        for check in ConformanceCheck
        if check is not ConformanceCheck.FORWARD_EVENT_TAPE_PARITY
    )
    release_pin = replace(
        NAUTILUS_PIN,
        package_version="2.0.0rc5",
        release_tag="v2.0.0rc5",
        wheel_digest=NAUTILUS_V2_RC_WHEEL_SHA256,
    )
    evidence = EngineConformanceEvidence(
        "nautilus",
        "2.0.0rc5",
        BUILD,
        EngineReleaseChannel.RELEASE_CANDIDATE,
        content_digest("rc5-backtest-fixture"),
        backtest_checks,
        NOW,
        release_pin,
    )
    conformance = evaluate_engine_conformance(evidence)
    sandbox_plan = _sandbox_plan(release_pin, result.attempt_id)
    execution_plan = NautilusExecutionPlan(
        result.trial_id,
        result.attempt_id,
        result.snapshot_fingerprint,
        "nautilus",
        "2.0.0rc5",
        BUILD,
        content_digest("authorization"),
        content_digest("runtime-preflight"),
        conformance.fingerprint,
        sandbox_plan.fingerprint,
        EngineExecutionDecision.READY,
        True,
        execution_scope=NautilusExecutionScope.BACKTEST_AUTHORITATIVE,
    )
    assert not conformance.authoritative
    assert conformance.missing_checks == frozenset({ConformanceCheck.FORWARD_EVENT_TAPE_PARITY})
    provenance = build_nautilus_result_provenance(
        execution_plan, evidence, conformance, sandbox_plan
    )
    assert provenance.release_channel is EngineReleaseChannel.RELEASE_CANDIDATE
    assert provenance.execution_scope == NautilusExecutionScope.BACKTEST_AUTHORITATIVE.value
    rc_result = replace(
        result,
        engine_version="2.0.0rc5",
        engine_build_digest=BUILD,
        engine_provenance=provenance,
    )
    assert rc_result.engine_authoritative
    integrity = verify_run_result_artifacts(
        rc_result,
        (verify_artifact_payload(rc_result.output_artifacts[0], b"result"),),
    )
    publication = plan_result_publication(
        rc_result,
        evidence,
        conformance,
        runtime,
        integrity,
        execution_plan=execution_plan,
    )
    assert publication.decision is ResultPublicationDecision.PUBLISH
    assert publication.accepted


def test_release_candidate_with_event_tape_parity_publishes_full_local_simulation() -> None:
    result, _, _, runtime, _, stable_plan = _result()
    release_pin = replace(
        NAUTILUS_PIN,
        package_version="2.0.0rc5",
        release_tag="v2.0.0rc5",
        wheel_digest=NAUTILUS_V2_RC_WHEEL_SHA256,
    )
    evidence = EngineConformanceEvidence(
        "nautilus",
        "2.0.0rc5",
        BUILD,
        EngineReleaseChannel.RELEASE_CANDIDATE,
        content_digest("rc5-full-simulation-fixture"),
        frozenset(ConformanceCheck),
        NOW,
        release_pin,
    )
    conformance = evaluate_engine_conformance(evidence)
    sandbox_plan = _sandbox_plan(release_pin, result.attempt_id)
    execution_plan = replace(
        stable_plan,
        engine_version="2.0.0rc5",
        conformance_report_fingerprint=conformance.fingerprint,
        sandbox_plan_fingerprint=sandbox_plan.fingerprint,
    )
    assert conformance.authoritative
    provenance = build_nautilus_result_provenance(
        execution_plan, evidence, conformance, sandbox_plan
    )
    rc_result = replace(
        result,
        engine_version="2.0.0rc5",
        engine_provenance=provenance,
    )
    integrity = verify_run_result_artifacts(
        rc_result,
        (verify_artifact_payload(rc_result.output_artifacts[0], b"result"),),
    )

    publication = plan_result_publication(
        rc_result,
        evidence,
        conformance,
        runtime,
        integrity,
        execution_plan=execution_plan,
    )

    assert provenance.execution_scope == NautilusExecutionScope.FULL.value
    assert provenance.release_channel is EngineReleaseChannel.RELEASE_CANDIDATE
    assert publication.decision is ResultPublicationDecision.PUBLISH
    assert publication.accepted


def test_authoritative_publication_requires_bound_scope_and_complete_backtest_checks() -> None:
    result, evidence, conformance, runtime, integrity, execution_plan = _result()
    without_plan = plan_result_publication(result, evidence, conformance, runtime, integrity)
    assert "authoritative_execution_plan_missing" in without_plan.rejection_reasons

    backtest_plan = replace(
        execution_plan,
        execution_scope=NautilusExecutionScope.BACKTEST_AUTHORITATIVE,
    )
    wrong_scope = plan_result_publication(
        result,
        evidence,
        conformance,
        runtime,
        integrity,
        execution_plan=backtest_plan,
    )
    assert "result_execution_scope_mismatch" in wrong_scope.rejection_reasons

    partial_evidence = replace(
        evidence,
        passed_checks=frozenset(
            check
            for check in ConformanceCheck
            if check is not ConformanceCheck.MULTI_INSTRUMENT_ACCOUNTING
        ),
    )
    partial_report = evaluate_engine_conformance(partial_evidence)
    partial_plan = replace(
        execution_plan,
        conformance_report_fingerprint=partial_report.fingerprint,
        execution_scope=NautilusExecutionScope.BACKTEST_AUTHORITATIVE,
    )
    assert result.engine_provenance is not None
    partial_provenance = replace(
        result.engine_provenance,
        conformance_evidence_fingerprint=partial_evidence.fingerprint,
        conformance_report_fingerprint=partial_report.fingerprint,
        execution_plan_fingerprint=partial_plan.fingerprint,
        execution_scope=NautilusExecutionScope.BACKTEST_AUTHORITATIVE.value,
    )
    partial_result = replace(
        result,
        engine_provenance=partial_provenance,
    )
    partial_integrity = verify_run_result_artifacts(
        partial_result,
        (verify_artifact_payload(partial_result.output_artifacts[0], b"result"),),
    )
    rejected = plan_result_publication(
        partial_result,
        partial_evidence,
        partial_report,
        runtime,
        partial_integrity,
        execution_plan=partial_plan,
    )
    assert "required_engine_conformance_failed" in rejected.rejection_reasons
