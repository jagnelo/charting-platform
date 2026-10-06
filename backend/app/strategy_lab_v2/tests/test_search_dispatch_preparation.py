from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import fields, is_dataclass, replace
from datetime import timedelta
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.strategy_lab_v2.admission import ExecutionAdmissionLedger
from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.application import PostgresStrategyLabV2Adapter
from app.strategy_lab_v2.artifact_application import LocalArtifactPublicationService
from app.strategy_lab_v2.artifact_commit import ArtifactCommitLedger, finalize_artifact_commit
from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.conformance_fixtures import resolve_nautilus_rc_conformance
from app.strategy_lab_v2.contracts import (
    AttemptState,
    EvaluationWindow,
    ProductClass,
    ScientificTrial,
)
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
from app.strategy_lab_v2.nautilus_worker_terminal import (
    create_nautilus_oos_worker_terminal_evidence_resolver,
)
from app.strategy_lab_v2.outcomes import new_execution_outcome
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.postgres_commands import ExecutionCommandContext
from app.strategy_lab_v2.progress import new_progress_state
from app.strategy_lab_v2.redis_transport import RedisStreamEntry
from app.strategy_lab_v2.resource_mutations import (
    ResourceMutationDecision,
    ResourceMutationRequest,
)
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile
from app.strategy_lab_v2.search_dispatch_preparation import (
    NautilusTrialPreparationContext,
    NautilusTrialSearchDispatchEvidenceResolver,
    SearchDispatchPreparationRequest,
)
from app.strategy_lab_v2.strategy_package_resolution import StrategyPackageArtifactResolver
from app.strategy_lab_v2.submissions import SubmissionReceipt, SubmissionRequest
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
from app.strategy_lab_v2.tests.test_postgres_storage import FakeSession
from app.strategy_lab_v2.trial_hydration import (
    HydratedNautilusTrial,
    NautilusTrialDomainHydrator,
    TrialDomainHydrationError,
)
from app.strategy_lab_v2.worker_evidence import (
    WorkerSubmissionBinding,
    WorkerTerminalEvidenceInputs,
    WorkerTerminalEvidenceLookup,
)
from app.strategy_lab_v2.worker_process import SerialWorkerProcessExecutor, WorkerProcessDecision
from app.strategy_lab_v2.worker_service import WorkerCompletionContext
from app.strategy_lab_v2.workers import (
    WorkerKind,
    WorkerPoolState,
    WorkerProfile,
    reserve_worker_slot,
)

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
        admission_ledger=existing.admission_ledger,
        image_name=existing.image_name,
        output_path=existing.output_path,
        now=existing.now,
        lease_duration=existing.lease_duration,
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
        pools: WorkerPoolState | tuple[WorkerPoolState, ...],
        lease_states: LeaseObservationState | tuple[LeaseObservationState, ...] | None = None,
    ) -> None:
        pools = (pools,) if isinstance(pools, WorkerPoolState) else tuple(pools)
        self.pools = {pool.profile.worker_id: pool for pool in pools}
        lease_states = (
            ()
            if lease_states is None
            else (lease_states,)
            if isinstance(lease_states, LeaseObservationState)
            else tuple(lease_states)
        )
        self.leases = {state.lease.lease_id: state for state in lease_states}
        self.loaded_profiles: list[WorkerProfile] = []
        self.loaded_lease_ids: list[str] = []
        self.persisted_lease_ids: list[str] = []

    async def list_profiles(
        self,
        *,
        kind: WorkerKind,
        runtime_profile_fingerprint: str,
    ) -> tuple[WorkerProfile, ...]:
        return tuple(
            sorted(
                (
                    pool.profile
                    for pool in self.pools.values()
                    if pool.profile.kind is kind
                    and pool.profile.runtime_profile_fingerprint == runtime_profile_fingerprint
                ),
                key=lambda profile: profile.worker_id,
            )
        )

    async def load_pool(self, profile: WorkerProfile) -> WorkerPoolState:
        self.loaded_profiles.append(profile)
        pool = self.pools.get(profile.worker_id)
        if pool is None or profile != pool.profile:
            raise ValueError("unexpected worker profile")
        return pool

    async def load_lease(self, lease_id: str) -> LeaseObservationState | None:
        self.loaded_lease_ids.append(lease_id)
        return self.leases.get(lease_id)

    async def persist_lease(self, lease: ExecutionAttemptLease) -> LeaseObservationState:
        existing = self.leases.get(lease.lease_id)
        if existing is not None and existing.lease != lease:
            raise ValueError("worker lease identity is already bound")
        state = existing or LeaseObservationState(lease)
        self.leases[lease.lease_id] = state
        self.persisted_lease_ids.append(lease.lease_id)
        return state


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
    conformance_resolution = resolve_nautilus_rc_conformance(
        runtime,
        _rc_probe(runtime),
        _rc_receipt(runtime),
        build_digest=content_digest("nautilus-v2-rc6-build"),
        tested_at=BASE,
    )
    worker_state_reader = _WorkerStateReader(pool)
    context = NautilusTrialPreparationContext.from_compatibility_backtest_conformance(
        conformance_resolution=conformance_resolution,
        product_classes=frozenset({ProductClass.EQUITY}),
        execution_models=frozenset({"bar-close-v1"}),
        account_models=frozenset({"cash-equity-v1"}),
        market_context=NautilusTrialMarketContext(values["instruments"], values["venue"]),
        runtime_profile=runtime_profile,
        admission_ledger=ExecutionAdmissionLedger(),
        image_name="nautilus-runtime",
        output_path=tmp_path / "dispatch-result.json",
        now=PREPARED_AT,
        lease_duration=timedelta(minutes=15),
    )
    return graph, artifact_store, package_resolver, materializer, context, worker_state_reader


def _contract_attributes(value: Any) -> Any:
    """Encode a typed fixture using the API's JSON-compatible domain shape."""

    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _contract_attributes(getattr(value, field.name)) for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {key: _contract_attributes(item) for key, item in value.items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple | list | set | frozenset):
        return [_contract_attributes(item) for item in value]
    return value


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
    assert worker_state_reader.loaded_profiles == [
        worker_state_reader.pools["dispatch-preparation-worker"].profile
    ]
    assert worker_state_reader.loaded_lease_ids == [
        evidence.worker_request.lease_state.lease.lease_id
    ]
    assert worker_state_reader.persisted_lease_ids == [
        evidence.worker_request.lease_state.lease.lease_id
    ]
    assert observed["graph"] == graph
    assert observed["request"].candidate_index == 3
    assert evidence.authorization.attempt_id == graph.attempt.attempt_id
    assert evidence.authorization.trial_id == graph.trial.trial_id
    assert evidence.authorization.source_digest == graph.strategies[0].source_digest
    assert not evidence.worker_request.execution_plan.authoritative
    assert evidence.worker_request.execution_plan.execution_scope.value == (
        "backtest_compatibility"
    )
    assert evidence.worker_request.execution_plan.engine_version == "2.0.0rc6"
    assert evidence.trial_runtime_evidence.runtime_request.request_id == (
        observed["request"].runtime_request_id
    )


@pytest.mark.asyncio
async def test_resolver_selects_an_idle_fleet_profile_and_persists_its_lease(
    tmp_path: Path,
) -> None:
    graph, store, package_resolver, materializer, context, worker_state_reader = _setup(tmp_path)
    busy_pool = next(iter(worker_state_reader.pools.values()))
    busy_pool = reserve_worker_slot(
        busy_pool,
        attempt_id="other-attempt",
        reservation_id=content_digest("other-worker-reservation"),
        acquired_at=BASE,
    ).pool
    selected_profile = WorkerProfile(
        "dispatch-preparation-worker-2",
        WorkerKind.BACKTEST,
        context.runtime_profile.fingerprint,
    )
    worker_state_reader.pools = {
        busy_pool.profile.worker_id: busy_pool,
        selected_profile.worker_id: WorkerPoolState(selected_profile),
    }
    intent = SearchDispatchIntent(
        "fleet-selection-key",
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

    evidence = await resolver(
        principal="owner-1",
        request_id="fleet-selection-request",
        experiment_fingerprint=graph.experiment.fingerprint,
        candidate_index=1,
        attempt_id=graph.attempt.attempt_id,
        dispatch_intent=intent,
    )

    expected_lease_id = content_digest(
        {
            "attempt_id": graph.attempt.attempt_id,
            "idempotency_key": intent.idempotency_key,
            "purpose": "strategy-lab-v2-search-worker-lease-v1",
            "worker_id": selected_profile.worker_id,
        }
    )
    expected_reservation_id = content_digest(
        {
            "attempt_id": graph.attempt.attempt_id,
            "idempotency_key": intent.idempotency_key,
            "purpose": "strategy-lab-v2-search-worker-reservation-v1",
            "worker_id": selected_profile.worker_id,
        }
    )
    assert evidence.worker_request.worker_pool.profile == selected_profile
    assert evidence.worker_request.lease_state.lease.worker_id == selected_profile.worker_id
    assert evidence.worker_request.lease_state.lease.lease_id == expected_lease_id
    assert evidence.reservation_id == expected_reservation_id
    assert (
        worker_state_reader.leases[expected_lease_id].lease
        == evidence.worker_request.lease_state.lease
    )


@pytest.mark.asyncio
async def test_resolver_fails_closed_when_every_fleet_profile_is_busy(tmp_path: Path) -> None:
    graph, store, package_resolver, materializer, context, worker_state_reader = _setup(tmp_path)
    worker_state_reader.pools = {
        worker_id: reserve_worker_slot(
            pool,
            attempt_id=f"other-{worker_id}",
            reservation_id=content_digest({"busy": worker_id}),
            acquired_at=BASE,
        ).pool
        for worker_id, pool in worker_state_reader.pools.items()
    }
    resolver = NautilusTrialSearchDispatchEvidenceResolver(
        domain_hydrator=_Hydrator(graph),
        runtime_materializer=materializer,
        strategy_package_resolver=package_resolver,
        artifact_store=store,
        worker_state_reader=worker_state_reader,
        context_resolver=lambda _request, _graph: context,
    )
    intent = SearchDispatchIntent(
        "fleet-saturated-key",
        graph.attempt.attempt_id,
        "strategy-backtest",
        PREPARED_AT,
    )

    with pytest.raises(RuntimeError, match="no available serial backtest worker profile"):
        await resolver(
            principal="owner-1",
            request_id="fleet-saturated-request",
            experiment_fingerprint=graph.experiment.fingerprint,
            candidate_index=1,
            attempt_id=graph.attempt.attempt_id,
            dispatch_intent=intent,
        )


@pytest.mark.asyncio
async def test_persisted_owner_graph_composes_exact_authoritative_rc6_worker_request(
    tmp_path: Path,
) -> None:
    values, graph, store = _build_inputs(tmp_path)
    prior_trial = graph.trial
    trial = ScientificTrial.create(
        experiment_fingerprint=prior_trial.experiment_fingerprint,
        snapshot_fingerprint=prior_trial.snapshot_fingerprint,
        preflight_report=prior_trial.preflight_report,
        parameter_set=prior_trial.parameter_set,
        scenario=prior_trial.scenario,
        seed=prior_trial.seed,
        randomization=prior_trial.randomization,
        evaluation_window=EvaluationWindow(
            start=BASE,
            end=BASE + timedelta(days=2),
            purpose="out_of_sample",
        ),
    )
    graph = replace(
        graph,
        trial=trial,
        attempt=transition_attempt(
            replace(graph.attempt, trial_id=trial.trial_id),
            target=AttemptState.RUNNING,
            now=BASE + timedelta(seconds=1),
        ),
    )
    package_resolver = StrategyPackageArtifactResolver(store, runtime_abi=RUNTIME_ABI)
    materializer = NautilusTrialRuntimeInputMaterializer(
        artifact_store=store,
        strategy_package_resolver=package_resolver,
        series_decoder=JsonFrozenSeriesDecoder(),
    )
    runtime = _rc_runtime()
    evidence_source = LocalNautilusRcConformanceEvidenceSource.from_environment()
    image_name = os.environ.get("STRATEGY_LAB_V2_NAUTILUS_RC_IMAGE_NAME", "").strip()
    if evidence_source is not None and not image_name:
        raise ValueError("the exact local Nautilus RC image name must be configured with evidence")
    if evidence_source is None and image_name:
        raise ValueError("the local Nautilus RC image name requires pinned conformance evidence")
    conformance_resolution = (
        evidence_source.load()
        if evidence_source is not None
        else resolve_nautilus_rc_conformance(
            runtime,
            _rc_probe(runtime),
            _rc_receipt(runtime),
            build_digest=content_digest("nautilus-v2-rc6-build"),
            tested_at=BASE,
        )
    )
    runtime_image_digest = (
        evidence_source.expected_runtime_image_digest
        if evidence_source is not None
        else runtime.runtime_image_digest
    )
    runtime_profile = RuntimeIsolationProfile(
        runtime_image_digest=runtime_image_digest,
        runtime_abi=RUNTIME_ABI,
        allowed_dependency_digests=frozenset(
            dependency.artifact_digest for dependency in graph.strategies[0].dependencies
        ),
    )
    worker_pool = WorkerPoolState(
        WorkerProfile(
            "dispatch-preparation-worker",
            WorkerKind.BACKTEST,
            runtime_profile.fingerprint,
        )
    )
    worker_state_reader = _WorkerStateReader(worker_pool)
    output_path = tmp_path / "persisted-dispatch-result.json"
    context = NautilusTrialPreparationContext.from_authoritative_backtest_conformance(
        conformance_resolution=conformance_resolution,
        product_classes=frozenset({ProductClass.EQUITY}),
        execution_models=frozenset({"bar-close-v1"}),
        account_models=frozenset({"cash-equity-v1"}),
        market_context=NautilusTrialMarketContext(values["instruments"], values["venue"]),
        runtime_profile=runtime_profile,
        admission_ledger=ExecutionAdmissionLedger(),
        image_name=image_name or "nautilus-runtime",
        output_path=output_path,
        now=PREPARED_AT,
        lease_duration=timedelta(minutes=15),
    )

    owner = SimpleNamespace(id="persisted-owner")
    session = FakeSession()

    def session_factory() -> FakeSession:
        return session

    persistence = PostgresStrategyLabV2Persistence.build(
        session_factory,
        clock=lambda: PREPARED_AT,
    )
    adapter = PostgresStrategyLabV2Adapter(
        session_factory,
        clock=lambda: PREPARED_AT,
        persistence=persistence,
    )
    contracts = (
        (ApiResourceType.STRATEGY, graph.strategies[0], "strategy-resource"),
        (
            ApiResourceType.PACKAGE,
            graph.packages[graph.strategies[0].fingerprint],
            "package-resource",
        ),
        (ApiResourceType.PORTFOLIO, graph.portfolio, "portfolio-resource"),
        (ApiResourceType.SNAPSHOT, graph.snapshot, "snapshot-resource"),
        (ApiResourceType.EXPERIMENT, graph.experiment, "experiment-resource"),
        (ApiResourceType.TRIAL, graph.trial, graph.trial.trial_id),
        (ApiResourceType.ATTEMPT, graph.attempt, graph.attempt.attempt_id),
    )
    for index, (resource_type, contract, resource_id) in enumerate(contracts):
        attributes = _contract_attributes(contract)
        if resource_type is ApiResourceType.ATTEMPT and attributes["updated_at"] is None:
            attributes.pop("updated_at")
        attributes["resource_id"] = resource_id
        response = await adapter.create_resource(
            principal=owner,
            request_id=f"persisted-dispatch-{index}",
            request=ResourceMutationRequest(
                resource_type,
                f"persisted-dispatch-key-{index}",
                {"attributes": attributes},
                BASE,
            ),
        )
        assert response.resolution.decision is ResourceMutationDecision.ACCEPT

    hydrator = NautilusTrialDomainHydrator(persistence.resources)
    persisted_graph = await hydrator.hydrate_attempt(
        principal=owner,
        attempt_resource_id=graph.attempt.attempt_id,
    )
    assert persisted_graph == graph
    with pytest.raises(TrialDomainHydrationError, match="missing or unavailable"):
        await hydrator.hydrate_attempt(
            principal=SimpleNamespace(id="another-owner"),
            attempt_resource_id=graph.attempt.attempt_id,
        )

    resolver = NautilusTrialSearchDispatchEvidenceResolver(
        domain_hydrator=hydrator,
        runtime_materializer=materializer,
        strategy_package_resolver=package_resolver,
        artifact_store=store,
        worker_state_reader=worker_state_reader,
        context_resolver=lambda _request, _graph: context,
    )
    intent = SearchDispatchIntent(
        "persisted-dispatch-intent",
        graph.attempt.attempt_id,
        "strategy-backtest",
        PREPARED_AT,
    )
    evidence = await resolver(
        principal=owner,
        request_id="persisted-worker-request",
        experiment_fingerprint=graph.experiment.fingerprint,
        candidate_index=0,
        attempt_id=graph.attempt.attempt_id,
        dispatch_intent=intent,
    )

    worker_request = evidence.worker_request
    binding = worker_request.runtime_input_artifact.trial_binding
    assert binding is not None
    assert binding.attempt_id == graph.attempt.attempt_id
    assert binding.trial_fingerprint == graph.trial.trial_id
    assert binding.experiment_fingerprint == graph.experiment.fingerprint
    assert binding.portfolio_fingerprint == graph.portfolio.fingerprint
    assert binding.snapshot_fingerprint == graph.snapshot.fingerprint
    assert (
        binding.strategy_package_fingerprint == worker_request.runtime_request.package_fingerprint
    )
    assert worker_request.authorization.trial_id == graph.trial.trial_id
    assert worker_request.authorization.attempt_id == graph.attempt.attempt_id
    assert worker_request.execution_plan.data_snapshot_fingerprint == graph.snapshot.fingerprint
    assert worker_request.execution_plan.authoritative
    assert worker_request.execution_plan.execution_scope.value == "backtest_authoritative"
    assert worker_request.execution_plan.engine_version == "2.0.0rc6"
    if evidence_source is not None:
        process_executor = SerialWorkerProcessExecutor(timeout_seconds=180)
        first_process_result = process_executor.run(worker_request)
        assert first_process_result.decision is WorkerProcessDecision.COMPLETED
        assert first_process_result.execution is not None
        assert (
            first_process_result.execution.decision.value == "succeeded"
        ), first_process_result.execution
        process_result = process_executor.run(worker_request)
        assert process_result.decision is WorkerProcessDecision.COMPLETED
        assert process_result.execution is not None
        assert process_result.execution.decision.value == "succeeded", process_result.execution
        assert output_path.is_file()

        attempt_id = graph.attempt.attempt_id
        submission_request = SubmissionRequest(
            "persisted-rc6-terminal-publication",
            "backtest",
            attempt_id,
            content_digest({"attempt_id": attempt_id, "trial_id": graph.trial.trial_id}),
            PREPARED_AT,
        )
        submission = SubmissionReceipt(submission_request, PREPARED_AT)
        terminal_inputs = WorkerTerminalEvidenceInputs(
            attempt_id,
            submission,
            ExecutionCommandContext(
                new_execution_outcome(
                    submission.submission_id,
                    attempt_id,
                    accepted_at=PREPARED_AT,
                ),
                new_progress_state(attempt_id, total_units=1, now=PREPARED_AT),
            ),
            None,
        )
        terminal_lookup = WorkerTerminalEvidenceLookup(
            WorkerSubmissionBinding("persisted-owner", submission),
            terminal_inputs,
        )
        completion_entry = RedisStreamEntry(
            "strategy-lab:v2:stream:backtest",
            "1-0",
            content_digest("persisted-rc6-terminal-message"),
            attempt_id,
            content_digest({"attempt_id": attempt_id}),
            worker_request.request_fingerprint,
        )
        completion_context = WorkerCompletionContext(
            completion_entry,
            worker_request,
            process_result,
            PREPARED_AT + timedelta(seconds=1),
        )

        class ArtifactCommitter:
            def __init__(self) -> None:
                self.ledger = ArtifactCommitLedger()

            async def load_ledger(self) -> ArtifactCommitLedger:
                return self.ledger

            async def finalize(self, plan, *, committed_at):
                resolution = finalize_artifact_commit(
                    self.ledger,
                    plan,
                    committed_at=committed_at,
                )
                self.ledger = resolution.ledger
                return resolution

        artifact_committer = ArtifactCommitter()
        artifact_publisher = LocalArtifactPublicationService(
            LocalArtifactStore(tmp_path / "published-rc6-results"),
            artifact_committer,
        )

        async def load_terminal_lookup(
            *,
            request_fingerprint: str,
            attempt_id: str,
            payload_digest: str | None = None,
        ):
            if (
                request_fingerprint != worker_request.request_fingerprint
                or attempt_id != graph.attempt.attempt_id
                or payload_digest != completion_entry.payload_digest
            ):
                return None
            return terminal_lookup

        terminal_resolver = create_nautilus_oos_worker_terminal_evidence_resolver(
            load_terminal_lookup,
            artifact_publisher,
            NautilusTrialDomainHydrator(persistence.resources),
        )
        terminal_evidence = await terminal_resolver(completion_context)

        assert terminal_evidence.result is not None
        assert terminal_evidence.result.attempt_id == attempt_id
        assert terminal_evidence.result.engine_provenance is not None
        assert terminal_evidence.result.engine_provenance.release_channel.value == (
            "release_candidate"
        )
        assert trial.evaluation_window is not None
        evaluation_window_fingerprint = trial.evaluation_window.fingerprint
        assert process_result.execution.nautilus_result is not None
        assert process_result.execution.nautilus_result.account_equity_trace is not None
        assert (
            process_result.execution.nautilus_result.account_equity_trace.evaluation_window_fingerprint
            == evaluation_window_fingerprint
        )
        assert process_result.execution.nautilus_result.native_reports is not None
        assert (
            process_result.execution.nautilus_result.native_reports.evaluation_window_fingerprint
            == evaluation_window_fingerprint
        )
        assert terminal_evidence.result.metric_set.values
        assert terminal_evidence.publication is not None
        assert terminal_evidence.publication.accepted
        assert len(terminal_evidence.artifact_plans) == len(
            terminal_evidence.result.output_artifacts
        )
        assert len(artifact_committer.ledger.records) == len(terminal_evidence.artifact_plans)
        assert all(
            artifact_publisher.store.path_for(artifact.storage_key).is_file()
            for artifact in terminal_evidence.result.output_artifacts
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
async def test_resolver_persists_a_missing_lease_and_rejects_an_expired_replay(
    tmp_path: Path,
) -> None:
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

    prepared = await resolver(**arguments)
    active_lease = prepared.worker_request.lease_state.lease
    assert worker_state_reader.leases[active_lease.lease_id].lease == active_lease

    worker_state_reader.leases[active_lease.lease_id] = LeaseObservationState(
        replace(
            active_lease,
            expires_at=PREPARED_AT + timedelta(seconds=1),
        )
    )
    later_context = replace(context, now=PREPARED_AT + timedelta(seconds=2))
    resolver._context_resolver = lambda _request, _graph: later_context
    with pytest.raises(RuntimeError, match="no available serial backtest worker profile"):
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
