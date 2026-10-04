from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from app.strategy_lab_v2.admission import ExecutionAdmissionLedger
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.conformance_fixtures import resolve_nautilus_rc_conformance
from app.strategy_lab_v2.contracts import AttemptState, ProductClass
from app.strategy_lab_v2.dispatch import SearchDispatchIntent
from app.strategy_lab_v2.lease_observations import LeaseObservationState
from app.strategy_lab_v2.lifecycle import ExecutionAttemptLease, transition_attempt
from app.strategy_lab_v2.local_conformance_source import (
    LOCAL_NAUTILUS_RC_EVIDENCE_ENV,
    LocalNautilusRcConformanceEvidencePublisher,
    LocalNautilusRcConformanceEvidenceSource,
)
from app.strategy_lab_v2.nautilus_trial_materializer import (
    NautilusTrialMarketContext,
    NautilusTrialRuntimeInputMaterializer,
)
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile
from app.strategy_lab_v2.search_dispatch_preparation import (
    NautilusTrialPreparationContext,
    NautilusTrialSearchDispatchEvidenceResolver,
    SearchDispatchPreparationRequest,
)
from app.strategy_lab_v2.strategy_package_resolution import StrategyPackageArtifactResolver
from app.strategy_lab_v2.tests.test_conformance_fixtures import (
    _rc_evidence_artifact,
    _rc_probe,
    _rc_receipt,
    _rc_runtime,
)
from app.strategy_lab_v2.tests.test_nautilus_trial_assembly import (
    BASE,
    JsonFrozenSeriesDecoder,
    _inputs,
)
from app.strategy_lab_v2.tests.test_nautilus_trial_materializer import (
    RUNTIME_ABI,
    _add_second_strategy,
    _build_inputs,
)
from app.strategy_lab_v2.trial_hydration import HydratedNautilusTrial
from app.strategy_lab_v2.workers import WorkerKind, WorkerPoolState, WorkerProfile

PREPARED_AT = BASE + timedelta(seconds=4)


def test_host_preparation_context_loads_operator_pinned_local_rc_as_compatibility(
    tmp_path: Path,
) -> None:
    _graph, _store, _package_resolver, _materializer, existing, _worker_reader = _setup(
        tmp_path / "trial"
    )
    runtime = _rc_runtime()
    payload = _rc_evidence_artifact(runtime)
    evidence_directory = tmp_path / "rc-evidence"
    evidence_directory.mkdir()
    published = LocalNautilusRcConformanceEvidencePublisher(evidence_directory).publish(
        runtime=runtime,
        probe_payload=payload["probe"],
        fixture_payload=payload["receipt"],
        build_digest=payload["build_digest"],
        tested_at=BASE,
    )
    source = LocalNautilusRcConformanceEvidenceSource.from_environment(
        {
            LOCAL_NAUTILUS_RC_EVIDENCE_ENV["artifact_directory"]: str(evidence_directory),
            LOCAL_NAUTILUS_RC_EVIDENCE_ENV["artifact_digest"]: published.artifact_digest,
            LOCAL_NAUTILUS_RC_EVIDENCE_ENV["source_digest"]: runtime.source_digest,
            LOCAL_NAUTILUS_RC_EVIDENCE_ENV["runtime_image_digest"]: runtime.runtime_image_digest,
        }
    )
    assert source is not None

    configured = NautilusTrialPreparationContext.from_operator_pinned_local_backtest_evidence(
        conformance_source=source,
        product_classes=frozenset({ProductClass.EQUITY}),
        execution_models=frozenset({"bar-close-v1"}),
        account_models=frozenset({"cash-equity-v1"}),
        market_context=existing.market_context,
        runtime_profile=existing.runtime_profile,
        worker_profile=existing.worker_profile,
        admission_ledger=existing.admission_ledger,
        reservation_id=existing.reservation_id,
        lease_id=existing.lease_id,
        image_name=existing.image_name,
        output_path=existing.output_path,
        now=existing.now,
    )

    assert configured.conformance_evidence == published.resolution.evidence
    assert configured.conformance_report.authoritative is False
    assert configured.capability_binding.authoritative is False
    assert configured.execution_scope.value == "backtest_compatibility"
    assert configured.requested_authoritative is False


class _Hydrator:
    def __init__(self, graph: HydratedNautilusTrial) -> None:
        self.graph = graph
        self.calls: list[tuple[Any, str]] = []

    async def hydrate_attempt(
        self,
        *,
        principal: Any,
        attempt_resource_id: str,
    ) -> HydratedNautilusTrial:
        self.calls.append((principal, attempt_resource_id))
        return self.graph


class _WorkerStateReader:
    def __init__(
        self,
        pool: WorkerPoolState,
        lease_state: LeaseObservationState | None,
    ) -> None:
        self.pool = pool
        self.lease_state = lease_state
        self.loaded_profiles: list[WorkerProfile] = []
        self.loaded_lease_ids: list[str] = []

    async def load_pool(self, profile: WorkerProfile) -> WorkerPoolState:
        self.loaded_profiles.append(profile)
        if profile != self.pool.profile:
            raise ValueError("unexpected worker profile")
        return self.pool

    async def load_lease(self, lease_id: str) -> LeaseObservationState | None:
        self.loaded_lease_ids.append(lease_id)
        if self.lease_state is None or lease_id != self.lease_state.lease.lease_id:
            return None
        return self.lease_state


def _setup(tmp_path: Path, *, runtime_image_digest: str | None = None):
    values, queued_graph, artifact_store = _build_inputs(tmp_path)
    graph = replace(
        queued_graph,
        attempt=transition_attempt(
            queued_graph.attempt,
            target=AttemptState.RUNNING,
            now=BASE + timedelta(seconds=1),
        ),
    )
    package_resolver = StrategyPackageArtifactResolver(
        artifact_store,
        runtime_abi=RUNTIME_ABI,
    )
    materializer = NautilusTrialRuntimeInputMaterializer(
        artifact_store=artifact_store,
        strategy_package_resolver=package_resolver,
        series_decoder=JsonFrozenSeriesDecoder(),
    )
    strategy = graph.strategies[0]
    runtime = _rc_runtime()
    runtime_profile = RuntimeIsolationProfile(
        runtime_image_digest=runtime_image_digest or runtime.runtime_image_digest,
        runtime_abi=RUNTIME_ABI,
        allowed_dependency_digests=frozenset(
            dependency.artifact_digest for dependency in strategy.dependencies
        ),
    )
    pool = WorkerPoolState(
        WorkerProfile(
            "dispatch-preparation-worker",
            WorkerKind.BACKTEST,
            runtime_profile.fingerprint,
        )
    )
    lease = ExecutionAttemptLease(
        graph.attempt.attempt_id,
        pool.profile.worker_id,
        "dispatch-preparation-lease",
        BASE + timedelta(seconds=2),
        BASE + timedelta(seconds=2),
        BASE + timedelta(hours=1),
    )
    conformance_resolution = resolve_nautilus_rc_conformance(
        runtime,
        _rc_probe(runtime),
        _rc_receipt(runtime),
        build_digest=content_digest("nautilus-v2-rc5-build"),
        tested_at=BASE,
    )
    lease_state = LeaseObservationState(lease)
    worker_state_reader = _WorkerStateReader(pool, lease_state)
    context = NautilusTrialPreparationContext.from_compatibility_backtest_conformance(
        conformance_resolution=conformance_resolution,
        product_classes=frozenset({ProductClass.EQUITY}),
        execution_models=frozenset({"bar-close-v1"}),
        account_models=frozenset({"cash-equity-v1"}),
        market_context=NautilusTrialMarketContext(values["instruments"], values["venue"]),
        runtime_profile=runtime_profile,
        worker_profile=pool.profile,
        admission_ledger=ExecutionAdmissionLedger(),
        reservation_id=content_digest("dispatch-preparation-reservation"),
        lease_id=lease.lease_id,
        image_name="nautilus-runtime",
        output_path=tmp_path / "dispatch-result.json",
        now=PREPARED_AT,
    )
    return graph, artifact_store, package_resolver, materializer, context, worker_state_reader


def test_authoritative_backtest_context_rejects_runtime_image_drift(tmp_path: Path) -> None:
    with pytest.raises(
        ValueError, match="runtime profile differs from the exact Nautilus release pin"
    ):
        _setup(tmp_path, runtime_image_digest=content_digest("different-runtime-image"))


@pytest.mark.asyncio
async def test_resolver_hydrates_materializes_authorizes_and_composes_search_evidence(
    tmp_path: Path,
) -> None:
    graph, store, package_resolver, materializer, context, worker_state_reader = _setup(tmp_path)
    hydrator = _Hydrator(graph)
    observed: dict[str, Any] = {}

    async def resolve_context(request, hydrated_graph):
        observed["request"] = request
        observed["graph"] = hydrated_graph
        return context

    resolver = NautilusTrialSearchDispatchEvidenceResolver(
        domain_hydrator=hydrator,
        runtime_materializer=materializer,
        strategy_package_resolver=package_resolver,
        artifact_store=store,
        worker_state_reader=worker_state_reader,
        context_resolver=resolve_context,
    )
    intent = SearchDispatchIntent(
        "dispatch-preparation-key",
        graph.attempt.attempt_id,
        "strategy-backtest",
        PREPARED_AT,
    )

    evidence = await resolver(
        principal="owner-1",
        request_id="request-1",
        experiment_fingerprint=graph.experiment.fingerprint,
        candidate_index=3,
        attempt_id=graph.attempt.attempt_id,
        dispatch_intent=intent,
    )

    assert hydrator.calls == [("owner-1", graph.attempt.attempt_id)]
    assert worker_state_reader.loaded_profiles == [context.worker_profile]
    assert worker_state_reader.loaded_lease_ids == [context.lease_id]
    assert observed["graph"] == graph
    assert observed["request"].candidate_index == 3
    assert evidence.authorization.attempt_id == graph.attempt.attempt_id
    assert evidence.authorization.trial_id == graph.trial.trial_id
    assert evidence.authorization.source_digest == graph.strategies[0].source_digest
    assert not evidence.worker_request.execution_plan.authoritative
    assert evidence.worker_request.execution_plan.execution_scope.value == (
        "backtest_compatibility"
    )
    assert evidence.worker_request.execution_plan.engine_version == "2.0.0rc5"
    assert evidence.trial_runtime_evidence.runtime_request.request_id == (
        observed["request"].runtime_request_id
    )


@pytest.mark.asyncio
async def test_resolver_authorizes_the_complete_multi_strategy_source_set(
    tmp_path: Path,
) -> None:
    graph, store, package_resolver, materializer, context, worker_state_reader = _setup(tmp_path)
    graph = _add_second_strategy(_inputs(), graph, store)
    resolver = NautilusTrialSearchDispatchEvidenceResolver(
        domain_hydrator=_Hydrator(graph),
        runtime_materializer=materializer,
        strategy_package_resolver=package_resolver,
        artifact_store=store,
        worker_state_reader=worker_state_reader,
        context_resolver=lambda _request, _graph: context,
    )
    intent = SearchDispatchIntent(
        "multi-strategy-dispatch-key",
        graph.attempt.attempt_id,
        "strategy-backtest",
        PREPARED_AT,
    )

    evidence = await resolver(
        principal="owner-1",
        request_id="multi-strategy-request",
        experiment_fingerprint=graph.experiment.fingerprint,
        candidate_index=0,
        attempt_id=graph.attempt.attempt_id,
        dispatch_intent=intent,
    )

    source_set_digest = evidence.trial_runtime_evidence.runtime_request.source_digest
    assert source_set_digest != graph.strategies[0].source_digest
    assert evidence.authorization.source_digest == source_set_digest
    assert evidence.worker_request.authorization.source_digest == source_set_digest


@pytest.mark.asyncio
async def test_resolver_fails_before_context_lookup_when_experiment_does_not_match(
    tmp_path: Path,
) -> None:
    graph, store, package_resolver, materializer, _context, worker_state_reader = _setup(tmp_path)
    calls = 0

    def resolve_context(_request, _graph):
        nonlocal calls
        calls += 1
        raise AssertionError("mismatched owner graph must not resolve execution context")

    resolver = NautilusTrialSearchDispatchEvidenceResolver(
        domain_hydrator=_Hydrator(graph),
        runtime_materializer=materializer,
        strategy_package_resolver=package_resolver,
        artifact_store=store,
        worker_state_reader=worker_state_reader,
        context_resolver=resolve_context,
    )
    intent = SearchDispatchIntent(
        "dispatch-preparation-key",
        graph.attempt.attempt_id,
        "strategy-backtest",
        PREPARED_AT,
    )

    with pytest.raises(ValueError, match="experiment differs from its owner-hydrated trial"):
        await resolver(
            principal="owner-1",
            request_id="request-1",
            experiment_fingerprint=content_digest("different-experiment"),
            candidate_index=3,
            attempt_id=graph.attempt.attempt_id,
            dispatch_intent=intent,
        )
    assert calls == 0


@pytest.mark.asyncio
async def test_resolver_rejects_missing_or_expired_persisted_lease(tmp_path: Path) -> None:
    graph, store, package_resolver, materializer, context, worker_state_reader = _setup(tmp_path)
    intent = SearchDispatchIntent(
        "dispatch-preparation-key",
        graph.attempt.attempt_id,
        "strategy-backtest",
        PREPARED_AT,
    )
    resolver = NautilusTrialSearchDispatchEvidenceResolver(
        domain_hydrator=_Hydrator(graph),
        runtime_materializer=materializer,
        strategy_package_resolver=package_resolver,
        artifact_store=store,
        worker_state_reader=worker_state_reader,
        context_resolver=lambda _request, _graph: context,
    )
    arguments = {
        "principal": "owner-1",
        "request_id": "request-1",
        "experiment_fingerprint": graph.experiment.fingerprint,
        "candidate_index": 3,
        "attempt_id": graph.attempt.attempt_id,
        "dispatch_intent": intent,
    }

    if worker_state_reader.lease_state is None:  # pragma: no cover - fixture invariant
        raise AssertionError("test setup omitted its persisted lease")
    active_lease = worker_state_reader.lease_state.lease
    worker_state_reader.lease_state = None
    with pytest.raises(ValueError, match="execution lease is missing"):
        await resolver(**arguments)

    worker_state_reader.lease_state = LeaseObservationState(
        replace(
            active_lease,
            expires_at=PREPARED_AT - timedelta(seconds=1),
        )
    )
    with pytest.raises(ValueError, match="not active at preparation time"):
        await resolver(**arguments)


def test_preparation_request_identity_is_stable_across_http_request_ids(tmp_path: Path) -> None:
    graph, _store, _package_resolver, _materializer, _context, _worker_state_reader = _setup(
        tmp_path
    )
    intent = SearchDispatchIntent(
        "dispatch-preparation-key",
        graph.attempt.attempt_id,
        "strategy-backtest",
        PREPARED_AT,
    )

    first = SearchDispatchPreparationRequest(
        "owner-1", "request-a", graph.experiment.fingerprint, 3, graph.attempt.attempt_id, intent
    )
    retry = SearchDispatchPreparationRequest(
        "owner-1", "request-b", graph.experiment.fingerprint, 3, graph.attempt.attempt_id, intent
    )

    assert first.runtime_request_id == retry.runtime_request_id
