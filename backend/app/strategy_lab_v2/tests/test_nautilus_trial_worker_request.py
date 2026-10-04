from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from app.strategy_lab_v2.admission import ExecutionAdmissionLedger
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.conformance import ConformanceCheck, EngineReleaseChannel
from app.strategy_lab_v2.engine_execution import NautilusExecutionScope
from app.strategy_lab_v2.execution import ExecutionAuthorization
from app.strategy_lab_v2.lease_observations import LeaseObservationState
from app.strategy_lab_v2.lifecycle import ExecutionAttemptLease
from app.strategy_lab_v2.nautilus_trial_materializer import (
    NautilusTrialMarketContext,
    NautilusTrialRuntimeInputMaterializer,
    build_nautilus_trial_runtime_evidence,
)
from app.strategy_lab_v2.nautilus_trial_worker_request import (
    build_nautilus_trial_worker_request,
)
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile
from app.strategy_lab_v2.strategy_package_resolution import StrategyPackageArtifactResolver
from app.strategy_lab_v2.tests.test_engine_execution import _conformance
from app.strategy_lab_v2.tests.test_nautilus_trial_assembly import (
    BASE,
    JsonFrozenSeriesDecoder,
)
from app.strategy_lab_v2.tests.test_nautilus_trial_materializer import (
    RUNTIME_ABI,
    _build_inputs,
)
from app.strategy_lab_v2.workers import WorkerKind, WorkerPoolState, WorkerProfile


def _preparation_evidence(tmp_path: Path):
    values, graph, artifact_store = _build_inputs(tmp_path)
    materializer = NautilusTrialRuntimeInputMaterializer(
        artifact_store=artifact_store,
        strategy_package_resolver=StrategyPackageArtifactResolver(
            artifact_store,
            runtime_abi=RUNTIME_ABI,
        ),
        series_decoder=JsonFrozenSeriesDecoder(),
    )
    materialized = materializer.materialize(
        graph=graph,
        market_context=NautilusTrialMarketContext(values["instruments"], values["venue"]),
    )
    strategy = graph.strategies[0]
    runtime_profile = RuntimeIsolationProfile(
        runtime_image_digest=content_digest("runtime-image"),
        runtime_abi=RUNTIME_ABI,
        allowed_dependency_digests=frozenset(
            dependency.artifact_digest for dependency in strategy.dependencies
        ),
    )
    runtime_evidence = build_nautilus_trial_runtime_evidence(
        materialized,
        runtime_profile,
        request_id=content_digest("worker-request-runtime"),
        submitted_at=BASE,
    )
    authorization = ExecutionAuthorization(
        graph.trial.trial_id,
        graph.attempt.attempt_id,
        strategy.source_digest,
        graph.trial.preflight_fingerprint,
        content_digest("worker-request-capability"),
        "worker-request-lease",
        "worker-request-worker",
        BASE,
        True,
    )
    pool = WorkerPoolState(
        WorkerProfile(
            authorization.lease_worker_id,
            WorkerKind.BACKTEST,
            runtime_profile.fingerprint,
        )
    )
    lease = ExecutionAttemptLease(
        authorization.attempt_id,
        authorization.lease_worker_id,
        authorization.lease_id,
        BASE,
        BASE,
        BASE + timedelta(hours=1),
    )
    checks = NautilusExecutionScope.BACKTEST_AUTHORITATIVE.required_checks
    conformance_evidence, conformance_report = _conformance(
        channel=EngineReleaseChannel.RELEASE_CANDIDATE,
        checks=checks,
    )
    return (
        artifact_store,
        runtime_profile,
        runtime_evidence,
        authorization,
        pool,
        LeaseObservationState(lease),
        conformance_evidence,
        conformance_report,
    )


def _build_request(tmp_path: Path, **overrides):
    (
        artifact_store,
        runtime_profile,
        runtime_evidence,
        authorization,
        pool,
        lease_state,
        conformance_evidence,
        conformance_report,
    ) = _preparation_evidence(tmp_path)
    arguments = {
        "artifact_store": artifact_store,
        "runtime_profile": runtime_profile,
        "worker_pool": pool,
        "admission_ledger": ExecutionAdmissionLedger(),
        "reservation_id": content_digest("worker-request-reservation"),
        "lease_state": lease_state,
        "conformance_evidence": conformance_evidence,
        "conformance_report": conformance_report,
        "image_name": "nautilus-runtime",
        "output_path": tmp_path / "result.json",
        "now": BASE,
    }
    arguments.update(overrides)
    request = build_nautilus_trial_worker_request(
        runtime_evidence,
        authorization,
        **arguments,
    )
    return request, runtime_evidence


def test_worker_request_composes_authoritative_rc_backtest_from_trial_evidence(
    tmp_path: Path,
) -> None:
    request, runtime_evidence = _build_request(tmp_path)

    assert request.orchestration_plan.accepted
    assert request.execution_plan.engine_version == "2.0.0rc5"
    assert request.execution_plan.execution_scope is NautilusExecutionScope.BACKTEST_AUTHORITATIVE
    assert request.execution_plan.authoritative is True
    assert request.runtime_input_artifact == (
        runtime_evidence.materialized_input.assembly.runtime_input_artifact
    )
    assert request.conformance_evidence is not None
    assert request.admission.reservation_id == content_digest("worker-request-reservation")
    assert request.sandbox_plan.request_fingerprint == request.runtime_request.fingerprint


def test_worker_request_rejects_a_lease_that_expired_before_composition(tmp_path: Path) -> None:
    evidence = _preparation_evidence(tmp_path)
    lease = evidence[5].lease
    expired = replace(lease, expires_at=BASE + timedelta(seconds=1))

    with pytest.raises(ValueError, match="lease is not active"):
        _build_request(
            tmp_path,
            lease_state=LeaseObservationState(expired),
            now=BASE + timedelta(seconds=2),
        )


def test_worker_request_rejects_conformance_missing_a_backtest_check(tmp_path: Path) -> None:
    conformance, report = _conformance(
        channel=EngineReleaseChannel.RELEASE_CANDIDATE,
        checks=frozenset({ConformanceCheck.MULTI_INSTRUMENT_ACCOUNTING}),
    )

    with pytest.raises(ValueError, match="Nautilus execution plan rejected"):
        _build_request(
            tmp_path,
            conformance_evidence=conformance,
            conformance_report=report,
        )


def test_trial_worker_composer_rejects_forward_execution_scope(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="require a backtest execution scope"):
        _build_request(tmp_path, execution_scope=NautilusExecutionScope.FORWARD_COMPATIBILITY)
