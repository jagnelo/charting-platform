from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from app.strategy_lab_v2.admission import ExecutionAdmissionLedger
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.conformance import EngineReleaseChannel
from app.strategy_lab_v2.contracts import AttemptState
from app.strategy_lab_v2.dispatch import SearchDispatchIntent
from app.strategy_lab_v2.engine_execution import NautilusExecutionScope
from app.strategy_lab_v2.execution_capabilities import ExecutionCapabilityBinding
from app.strategy_lab_v2.lease_observations import LeaseObservationState
from app.strategy_lab_v2.lifecycle import ExecutionAttemptLease, transition_attempt
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
from app.strategy_lab_v2.tests.test_engine_execution import _conformance
from app.strategy_lab_v2.tests.test_nautilus_trial_assembly import (
    BASE,
    JsonFrozenSeriesDecoder,
)
from app.strategy_lab_v2.tests.test_nautilus_trial_materializer import (
    RUNTIME_ABI,
    _build_inputs,
)
from app.strategy_lab_v2.trial_hydration import HydratedNautilusTrial
from app.strategy_lab_v2.workers import WorkerKind, WorkerPoolState, WorkerProfile

PREPARED_AT = BASE + timedelta(seconds=4)


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


def _setup(tmp_path: Path):
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
    runtime_profile = RuntimeIsolationProfile(
        runtime_image_digest=content_digest("runtime-image"),
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
    conformance, report = _conformance(
        channel=EngineReleaseChannel.RELEASE_CANDIDATE,
        checks=NautilusExecutionScope.BACKTEST_AUTHORITATIVE.required_checks,
    )
    decisions = graph.trial.preflight_report.decisions
    capability = ExecutionCapabilityBinding(
        engine_name=conformance.engine_id,
        engine_version=conformance.engine_version,
        engine_build_digest=conformance.build_digest,
        conformance_fingerprint=conformance.fingerprint,
        product_classes=frozenset(item.requirement.product_class for item in decisions),
        execution_models=frozenset(item.requirement.execution_model for item in decisions),
        account_models=frozenset(item.requirement.account_model for item in decisions),
        authoritative=True,
    )
    lease_state = LeaseObservationState(lease)
    worker_state_reader = _WorkerStateReader(pool, lease_state)
    context = NautilusTrialPreparationContext(
        market_context=NautilusTrialMarketContext(values["instruments"], values["venue"]),
        runtime_profile=runtime_profile,
        worker_profile=pool.profile,
        admission_ledger=ExecutionAdmissionLedger(),
        reservation_id=content_digest("dispatch-preparation-reservation"),
        lease_id=lease.lease_id,
        capability_binding=capability,
        conformance_evidence=conformance,
        conformance_report=report,
        image_name="nautilus-runtime",
        output_path=tmp_path / "dispatch-result.json",
        now=PREPARED_AT,
    )
    return graph, artifact_store, package_resolver, materializer, context, worker_state_reader


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
    assert evidence.worker_request.execution_plan.authoritative
    assert evidence.worker_request.execution_plan.engine_version == "2.0.0rc5"
    assert evidence.trial_runtime_evidence.runtime_request.request_id == (
        observed["request"].runtime_request_id
    )


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
