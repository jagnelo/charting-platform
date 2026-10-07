from __future__ import annotations

import asyncio
import os
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.strategy_lab_v2.admission import ExecutionAdmissionLedger
from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.application import PostgresStrategyLabV2Adapter
from app.strategy_lab_v2.artifact_application import LocalArtifactPublicationService
from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    AttemptState,
    EvaluationWindow,
    ProductClass,
    ScientificTrial,
)
from app.strategy_lab_v2.dispatch import (
    DispatchRequest,
    SearchDispatchIntent,
    build_dispatch_envelope,
)
from app.strategy_lab_v2.dispatch_payload import DispatchPayload
from app.strategy_lab_v2.lifecycle import transition_attempt
from app.strategy_lab_v2.local_conformance_source import LocalNautilusRcConformanceEvidenceSource
from app.strategy_lab_v2.nautilus_trial_materializer import (
    NautilusTrialMarketContext,
    NautilusTrialRuntimeInputMaterializer,
)
from app.strategy_lab_v2.nautilus_worker_terminal import (
    create_nautilus_oos_worker_terminal_evidence_resolver,
)
from app.strategy_lab_v2.outcomes import (
    OutcomeUpdate,
    new_execution_outcome,
)
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.postgres_artifact_commit import (
    PostgresArtifactCommitAdapter,
    PostgresArtifactCommitSchema,
)
from app.strategy_lab_v2.postgres_commands import ExecutionCommandContext
from app.strategy_lab_v2.postgres_execution_state import (
    PostgresExecutionStateAdapter,
    PostgresExecutionStateSchema,
)
from app.strategy_lab_v2.postgres_execution_summary import (
    PostgresExecutionSummaryAdapter,
    PostgresExecutionSummarySchema,
)
from app.strategy_lab_v2.postgres_metrics import PostgresMetricsAdapter, PostgresMetricsSchema
from app.strategy_lab_v2.postgres_result_completion import (
    PostgresResultCompletionAdapter,
    PostgresResultCompletionSchema,
)
from app.strategy_lab_v2.postgres_result_materialization import (
    PostgresResultMaterializationAdapter,
    PostgresResultMaterializationSchema,
)
from app.strategy_lab_v2.postgres_result_publication import (
    PostgresResultPublicationAdapter,
    PostgresResultPublicationSchema,
)
from app.strategy_lab_v2.postgres_runtime_execution import (
    PostgresRuntimeExecutionAdapter,
    PostgresRuntimeExecutionSchema,
)
from app.strategy_lab_v2.postgres_search_dispatch import SearchDispatchRecord
from app.strategy_lab_v2.postgres_worker_settlement import (
    PostgresWorkerSettlementAdapter,
    PostgresWorkerSettlementSchema,
)
from app.strategy_lab_v2.postgres_worker_state import (
    PostgresWorkerStateAdapter,
    PostgresWorkerStateSchema,
)
from app.strategy_lab_v2.progress import ExecutionProgressUpdate, ProgressPhase, new_progress_state
from app.strategy_lab_v2.redis_transport import RedisDispatchTransport, RedisStreamEntry
from app.strategy_lab_v2.resource_mutations import ResourceMutationDecision, ResourceMutationRequest
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile
from app.strategy_lab_v2.search_dispatch import SearchDispatchResolution
from app.strategy_lab_v2.search_dispatch_preparation import (
    NautilusTrialPreparationContext,
    NautilusTrialSearchDispatchEvidenceResolver,
)
from app.strategy_lab_v2.search_state import (
    SearchCandidatePhase,
    SearchCandidateState,
    SearchExecutionState,
    SearchStateDecision,
    record_search_candidate_terminal,
)
from app.strategy_lab_v2.strategy_package_resolution import StrategyPackageArtifactResolver
from app.strategy_lab_v2.submissions import SubmissionReceipt, SubmissionRequest
from app.strategy_lab_v2.tests.test_nautilus_trial_assembly import (
    BASE,
    JsonFrozenSeriesDecoder,
)
from app.strategy_lab_v2.tests.test_nautilus_trial_materializer import (
    RUNTIME_ABI,
    _build_inputs,
)
from app.strategy_lab_v2.tests.test_nautilus_worker_terminal import (
    NOW,
)
from app.strategy_lab_v2.tests.test_postgres_storage import FakeSession
from app.strategy_lab_v2.tests.test_search_dispatch_preparation import (
    _contract_attributes,
    _WorkerStateReader,
)
from app.strategy_lab_v2.tests.test_trial_hydration import MemoryDomainReader
from app.strategy_lab_v2.trial_hydration import (
    NautilusTrialDomainHydrator,
)
from app.strategy_lab_v2.worker_consumer import (
    RedisDispatchWorker,
    RedisDispatchWorkerScheduler,
    WorkerEntryDecision,
)
from app.strategy_lab_v2.worker_evidence import (
    WorkerSubmissionBinding,
    WorkerTerminalEvidenceInputs,
    WorkerTerminalEvidenceLookup,
)
from app.strategy_lab_v2.worker_process import (
    SerialWorkerProcessExecutor,
    WorkerProcessDecision,
)
from app.strategy_lab_v2.worker_recovery_application import WorkerRecoveryApplication
from app.strategy_lab_v2.worker_service import (
    DedicatedStrategyWorkerService,
    WorkerCompletionContext,
)
from app.strategy_lab_v2.worker_terminal_adapter import PostgresWorkerTerminalAdapter
from app.strategy_lab_v2.workers import WorkerKind, WorkerPoolState, WorkerProfile


def _async_postgres_url(raw_url: str) -> str:
    if raw_url.startswith("postgresql+asyncpg://"):
        return raw_url
    if raw_url.startswith("postgresql+psycopg2://"):
        return raw_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    raise ValueError("integration database URL must use PostgreSQL")


async def _exact_rc6_owner_request(tmp_path: Path):
    """Build the same owner-hydrated request used by the RC6 authority test."""

    tmp_path.mkdir(parents=True, exist_ok=True)
    evidence_source = LocalNautilusRcConformanceEvidenceSource.from_environment()
    if evidence_source is None:
        pytest.skip("exact pinned Nautilus RC6 evidence is required for this integration")
    image_name = os.environ.get("STRATEGY_LAB_V2_NAUTILUS_RC_IMAGE_NAME", "").strip()
    if not image_name:
        raise ValueError("the exact local Nautilus RC image name must be configured with evidence")

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
    conformance_resolution = evidence_source.load()
    runtime_profile = RuntimeIsolationProfile(
        runtime_image_digest=evidence_source.expected_runtime_image_digest,
        runtime_abi=RUNTIME_ABI,
        allowed_dependency_digests=frozenset(
            dependency.artifact_digest for dependency in graph.strategies[0].dependencies
        ),
    )
    worker_pool = WorkerPoolState(
        WorkerProfile(
            "dispatch-preparation-worker", WorkerKind.BACKTEST, runtime_profile.fingerprint
        )
    )
    output_path = tmp_path / "persisted-dispatch-result.json"
    preparation_context = NautilusTrialPreparationContext.from_authoritative_backtest_conformance(
        conformance_resolution=conformance_resolution,
        product_classes=frozenset({ProductClass.EQUITY}),
        execution_models=frozenset({"bar-close-v1"}),
        account_models=frozenset({"cash-equity-v1"}),
        market_context=NautilusTrialMarketContext(values["instruments"], values["venue"]),
        runtime_profile=runtime_profile,
        admission_ledger=ExecutionAdmissionLedger(),
        image_name=image_name,
        output_path=output_path,
        now=BASE + timedelta(seconds=4),
        lease_duration=timedelta(minutes=15),
    )
    owner = SimpleNamespace(id="persisted-owner")
    session = FakeSession()
    persistence = PostgresStrategyLabV2Persistence.build(
        lambda: session, clock=lambda: BASE + timedelta(seconds=4)
    )
    adapter = PostgresStrategyLabV2Adapter(
        lambda: session, clock=lambda: BASE + timedelta(seconds=4), persistence=persistence
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
            request_id=f"persisted-oos-{index}",
            request=ResourceMutationRequest(
                resource_type, f"persisted-oos-key-{index}", {"attributes": attributes}, BASE
            ),
        )
        assert response.resolution.decision is ResourceMutationDecision.ACCEPT

    hydrator = NautilusTrialDomainHydrator(persistence.resources)
    assert (
        await hydrator.hydrate_attempt(
            principal=owner, attempt_resource_id=graph.attempt.attempt_id
        )
        == graph
    )
    resolver = NautilusTrialSearchDispatchEvidenceResolver(
        domain_hydrator=hydrator,
        runtime_materializer=materializer,
        strategy_package_resolver=package_resolver,
        artifact_store=store,
        worker_state_reader=_WorkerStateReader(worker_pool),
        context_resolver=lambda _request, _graph: preparation_context,
    )
    evidence = await resolver(
        principal=owner,
        request_id="persisted-oos-worker-request",
        experiment_fingerprint=graph.experiment.fingerprint,
        candidate_index=0,
        attempt_id=graph.attempt.attempt_id,
        dispatch_intent=SearchDispatchIntent(
            "persisted-oos-intent",
            graph.attempt.attempt_id,
            "strategy-backtest",
            BASE + timedelta(seconds=4),
        ),
    )
    request = evidence.worker_request
    process_executor = SerialWorkerProcessExecutor(timeout_seconds=180)
    first_process = process_executor.run(request)
    process = process_executor.run(request)
    assert process.decision is WorkerProcessDecision.COMPLETED
    execution = process.execution
    assert execution is not None
    assert (
        first_process.execution is not None and first_process.execution.nautilus_result is not None
    ), first_process
    assert execution.decision.value == "succeeded", (
        execution.decision,
        execution.rejection_reason,
        execution.nautilus_result,
        execution.nautilus_result.status if execution.nautilus_result else None,
        execution.nautilus_result.sandbox_result
        if execution.nautilus_result
        else None,
        execution.runtime_result,
    )
    return owner, graph, request, process, persistence, store


@pytest_asyncio.fixture(scope="session")
async def exact_rc6_owner_request(tmp_path_factory):
    """Run the pinned worker before session-scoped PostgreSQL/Redis fixtures."""

    return await _exact_rc6_owner_request(tmp_path_factory.mktemp("exact-rc6-oos"))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_oos_terminal_commit_survives_worker_loss_before_real_redis_ack(
    exact_rc6_owner_request,
    pg_container,
    test_database_url: str | None,
    redis_url: str,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Production receipt-first worker reclaims a settled OOS Redis delivery."""

    owner, graph, worker_request, process_result, owner_persistence, artifact_store = (
        exact_rc6_owner_request
    )
    owner_id = str(owner.id)
    attempt_id = worker_request.admission.attempt_id
    submission = SubmissionReceipt(
        SubmissionRequest(
            "exact-rc6-oos-terminal",
            "backtest",
            attempt_id,
            content_digest({"attempt_id": attempt_id, "trial_id": graph.trial.trial_id}),
            BASE,
        ),
        BASE,
    )
    entry = RedisStreamEntry(
        "strategy-lab:v2:stream:backtest",
        "1-0",
        content_digest("exact-rc6-oos-terminal-message"),
        attempt_id,
        content_digest({"attempt_id": attempt_id}),
        worker_request.request_fingerprint,
    )
    lookup = WorkerTerminalEvidenceLookup(
        WorkerSubmissionBinding(owner_id, submission),
        WorkerTerminalEvidenceInputs(
            attempt_id,
            submission,
            ExecutionCommandContext(
                replace(
                    new_execution_outcome(submission.submission_id, attempt_id, accepted_at=BASE),
                    sequence=1,
                ),
                replace(
                    new_progress_state(attempt_id, total_units=1, now=BASE),
                    sequence=1,
                    phase=ProgressPhase.RUNNING,
                ),
            ),
            None,
        ),
    )
    context = WorkerCompletionContext(entry, worker_request, process_result, NOW)
    suffix = uuid4().hex
    schemas = (
        PostgresArtifactCommitSchema(f"slv2_oos_artifacts_{suffix}"),
        PostgresRuntimeExecutionSchema(
            f"slv2_oos_runtime_{suffix}", f"slv2_oos_runtime_updates_{suffix}"
        ),
        PostgresExecutionStateSchema(f"slv2_oos_outcomes_{suffix}", f"slv2_oos_progress_{suffix}"),
        PostgresExecutionSummarySchema(f"slv2_oos_summaries_{suffix}"),
        PostgresResultPublicationSchema(f"slv2_oos_publications_{suffix}"),
        PostgresResultCompletionSchema(f"slv2_oos_completions_{suffix}"),
        PostgresResultMaterializationSchema(f"slv2_oos_manifests_{suffix}"),
        PostgresMetricsSchema(f"slv2_oos_metrics_{suffix}"),
        PostgresWorkerStateSchema(
            f"slv2_oos_profiles_{suffix}",
            f"slv2_oos_reservations_{suffix}",
            f"slv2_oos_leases_{suffix}",
            f"slv2_oos_observations_{suffix}",
        ),
        PostgresWorkerSettlementSchema(f"slv2_oos_settlements_{suffix}"),
    )
    table_names = (
        schemas[0].commit_table,
        schemas[1].state_table,
        schemas[1].update_table,
        schemas[2].outcome_table,
        schemas[2].progress_table,
        schemas[3].summary_table,
        schemas[4].publication_table,
        schemas[5].completion_table,
        schemas[6].manifest_table,
        schemas[7].metric_table,
        schemas[8].profile_table,
        schemas[8].reservation_table,
        schemas[8].lease_table,
        schemas[8].observation_table,
        schemas[9].settlement_table,
    )
    raw_url = test_database_url or pg_container.get_connection_url()
    engine = create_async_engine(_async_postgres_url(raw_url), pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    redis = Redis.from_url(redis_url, decode_responses=True)
    namespace = f"strategy-lab:v2:oos-terminal:{suffix}"
    queue_name = "backtest"
    group_name = f"oos-terminal-{suffix}"
    transport = RedisDispatchTransport(redis, namespace=namespace)
    stream_key = transport.stream_key(queue_name)
    payload = DispatchPayload.from_mapping({"attempt_id": attempt_id})
    dispatch = DispatchRequest(
        f"oos-terminal-{suffix}",
        attempt_id,
        payload.payload_digest,
        queue_name,
        NOW,
    )
    dispatch_record = SearchDispatchRecord(
        owner_id,
        graph.experiment.fingerprint,
        0,
        dispatch,
    )

    class SearchDispatchReader:
        async def load_by_payload_digest(self, digest: str):
            return dispatch_record if digest == dispatch.payload_digest else None

    class SearchStateStore:
        def __init__(self) -> None:
            self.state = SearchExecutionState(
                graph.experiment.fingerprint,
                (
                    SearchCandidateState(
                        0,
                        graph.trial.trial_id,
                        SearchCandidatePhase.RUNNING,
                        attempt_id,
                        1,
                        updated_at=BASE,
                    ),
                ),
                updated_at=BASE,
            )

        async def load(self, *, principal: str, experiment_fingerprint: str):
            assert principal == owner_id
            assert experiment_fingerprint == graph.experiment.fingerprint
            return self.state

        async def record_terminal(
            self,
            *,
            principal: str,
            experiment_fingerprint: str,
            candidate_index: int,
            attempt_id: str,
            phase: SearchCandidatePhase,
            result_fingerprint: str | None,
            now,
        ):
            assert principal == owner_id
            assert experiment_fingerprint == graph.experiment.fingerprint
            resolution = record_search_candidate_terminal(
                self.state,
                candidate_index,
                attempt_id=attempt_id,
                phase=phase,
                result_fingerprint=result_fingerprint,
                now=now,
            )
            if resolution.decision is SearchStateDecision.APPLY:
                self.state = resolution.state
            return resolution

    search_state = SearchStateStore()

    def terminal_stack():
        artifacts = PostgresArtifactCommitAdapter(session_factory, schema=schemas[0])
        runtime = PostgresRuntimeExecutionAdapter(session_factory, schema=schemas[1])
        execution_state = PostgresExecutionStateAdapter(session_factory, schema=schemas[2])
        summaries = PostgresExecutionSummaryAdapter(session_factory, schema=schemas[3])
        publications = PostgresResultPublicationAdapter(session_factory, schema=schemas[4])
        completions = PostgresResultCompletionAdapter(session_factory, schema=schemas[5])
        manifests = PostgresResultMaterializationAdapter(session_factory, schema=schemas[6])
        metrics = PostgresMetricsAdapter(session_factory, schema=schemas[7])
        workers = PostgresWorkerStateAdapter(session_factory, schema=schemas[8])
        settlements = PostgresWorkerSettlementAdapter(session_factory, schema=schemas[9])
        artifact_publisher = LocalArtifactPublicationService(
            LocalArtifactStore(tmp_path / "published-oos-artifacts"), artifacts
        )
        domain_reader = MemoryDomainReader(
            {
                "attempt": graph.attempt,
                "trial": graph.trial,
                "experiment": graph.experiment,
                "portfolio": graph.portfolio,
                "snapshot": graph.snapshot,
                "strategies": graph.strategies,
                "packages": graph.packages,
            },
            owner=owner_id,
        )

        async def load_lookup(
            *, request_fingerprint: str, attempt_id: str, payload_digest: str | None = None
        ) -> WorkerTerminalEvidenceLookup | None:
            if (
                request_fingerprint != dispatch.fingerprint
                or attempt_id != worker_request.runtime_request.attempt_id
                or payload_digest != context.entry.payload_digest
            ):
                return None
            return lookup

        evidence_resolver = create_nautilus_oos_worker_terminal_evidence_resolver(
            load_lookup,
            artifact_publisher,
            NautilusTrialDomainHydrator(domain_reader),
        )
        terminal = PostgresWorkerTerminalAdapter(
            evidence_resolver,
            runtime_execution=runtime,
            execution_state=execution_state,
            execution_summaries=summaries,
            result_publication=publications,
            result_completion=completions,
            result_materialization=manifests,
            metrics=metrics,
            worker_state=workers,
            settlements=settlements,
        )
        return SimpleNamespace(
            terminal=terminal,
            runtime=runtime,
            execution_state=execution_state,
            summaries=summaries,
            publications=publications,
            completions=completions,
            manifests=manifests,
            metrics=metrics,
            workers=workers,
            settlements=settlements,
            artifacts=artifacts,
        )

    try:
        async with engine.begin() as connection:
            for schema in schemas:
                for statement in cast(Any, schema).statements:
                    await connection.execute(text(statement))

        stack = terminal_stack()
        runtime = stack.runtime
        execution_state = stack.execution_state
        worker_state = stack.workers
        initial_execution = lookup.inputs.execution
        assert initial_execution is not None
        await runtime.initialize(principal=owner_id, state=context.request.runtime_state)
        queued_outcome = replace(initial_execution.outcome, sequence=0)
        queued_progress = replace(
            initial_execution.progress,
            sequence=0,
            phase=ProgressPhase.QUEUED,
        )
        await execution_state.initialize(
            principal=owner_id,
            outcome=queued_outcome,
            progress=queued_progress,
        )
        await execution_state.transition(
            principal=owner_id,
            outcome_update=OutcomeUpdate(
                initial_execution.outcome.submission_id,
                attempt_id,
                queued_outcome.sequence + 1,
                initial_execution.outcome.status,
                initial_execution.outcome.updated_at,
            ),
            progress_update=ExecutionProgressUpdate(
                attempt_id,
                queued_progress.sequence + 1,
                initial_execution.progress.phase,
                initial_execution.progress.completed_units,
                initial_execution.progress.total_units,
                initial_execution.progress.updated_at,
            ),
        )
        profile = context.request.worker_pool.profile
        await worker_state.ensure_profile(profile)
        reservation = next(
            item
            for item in context.request.worker_pool.reservations
            if item.reservation_id == context.request.admission.reservation_id
        )
        await worker_state.reserve(
            profile=profile,
            attempt_id=attempt_id,
            reservation_id=reservation.reservation_id,
            acquired_at=reservation.acquired_at,
        )
        await worker_state.persist_lease(context.request.lease_state.lease)

        await transport.enqueue(build_dispatch_envelope(dispatch))
        crashed_worker = RedisDispatchWorker(
            transport,
            queue_name=queue_name,
            group_name=group_name,
            consumer_name="terminal-writer-crashed-before-ack",
            reclaim_idle_ms=0,
        )
        first_poll = await crashed_worker.poll()
        assert len(first_poll.entries) == 1
        first_entry = first_poll.entries[0]
        first_context = replace(context, entry=first_entry)
        first_terminal = await stack.terminal.write(first_context)
        assert first_terminal.decision.value == "complete", first_terminal.rejection_reason

        async def unused_dispatch(**_kwargs: Any) -> SearchDispatchResolution:
            raise AssertionError("successful terminal replay must not dispatch a retry")

        recovery_application = WorkerRecoveryApplication(
            SimpleNamespace(
                search_dispatch=SearchDispatchReader(),
                search_state=search_state,
                result_completion=stack.completions,
                worker_settlements=stack.settlements,
                worker_state=stack.workers,
            ),
            queue_name=queue_name,
            dispatch_client=unused_dispatch,
        )
        search_completion = await recovery_application.complete_terminal_if_persisted(
            entry=first_entry,
            request=context.request,
            observed_at=NOW + timedelta(days=1),
        )
        assert search_completion is not None
        assert search_completion.decision.value == "complete"
        assert await redis.xpending(stream_key, group_name) == {
            "pending": 1,
            "min": first_entry.stream_id,
            "max": first_entry.stream_id,
            "consumers": [{"name": "terminal-writer-crashed-before-ack", "pending": 1}],
        }

        # A fresh adapter graph models a process restart; the second consumer
        # can only ACK after the durable terminal receipt is replayed.
        restarted = terminal_stack()
        restarted_worker = RedisDispatchWorker(
            transport,
            queue_name=queue_name,
            group_name=group_name,
            consumer_name="terminal-writer-restarted",
            reclaim_idle_ms=0,
        )

        class PayloadLoader:
            async def load_payload(self, digest: str):
                return payload if digest == payload.payload_digest else None

        async def materialize(_entry, received_payload):
            assert received_payload.payload_digest == payload.payload_digest
            return context.request

        async def forbidden_completion(*_args, **_kwargs):
            raise AssertionError("receipt-first replay must bypass terminal process completion")

        async def replay_terminal(entry, request, observed_at):
            return await recovery_application.complete_terminal_if_persisted(
                entry=entry,
                request=request,
                observed_at=observed_at,
            )

        executor = SerialWorkerProcessExecutor()
        process_launches = 0

        async def forbidden_launch(_request):
            nonlocal process_launches
            process_launches += 1
            raise AssertionError("receipt-first replay must not launch Nautilus")

        monkeypatch.setattr(executor, "run_async", forbidden_launch)
        scheduler = RedisDispatchWorkerScheduler(restarted_worker, sleep=asyncio.sleep)
        service = DedicatedStrategyWorkerService(
            scheduler,
            PayloadLoader(),
            materialize,
            forbidden_completion,
            process_executor=executor,
            clock=lambda: NOW + timedelta(days=1),
            terminal_replay_reader=replay_terminal,
        )
        cycles = await service.run(asyncio.Event(), max_cycles=1)
        assert len(cycles) == 1
        assert len(cycles[0].entries) == 1
        assert cycles[0].entries[0].decision is WorkerEntryDecision.ACKNOWLEDGED
        assert cycles[0].entries[0].handler.decision.value == "complete"
        assert process_launches == 0
        assert await redis.xpending(stream_key, group_name) == {
            "pending": 0,
            "min": None,
            "max": None,
            "consumers": [],
        }
        assert len((await restarted.settlements.load_ledger(principal=owner_id)).records) == 1
        assert (
            len((await restarted.completions.load_completion_ledger(principal=owner_id)).records)
            == 1
        )
        assert await restarted.manifests.load_manifest(principal=owner_id, attempt_id=attempt_id)
        assert (
            len(
                await restarted.publications.load_for_attempt(
                    principal=owner_id, attempt_id=attempt_id
                )
            )
            == 1
        )
        manifest = await restarted.manifests.load_manifest(
            principal=owner_id, attempt_id=attempt_id
        )
        assert manifest is not None
        assert len((await restarted.artifacts.load_ledger()).records) == len(
            manifest.output_artifacts
        )
    finally:
        await redis.delete(
            f"{namespace}:stream:{queue_name}",
            f"{namespace}:idempotency",
        )
        await redis.aclose()
        async with engine.begin() as connection:
            for table in reversed(table_names):
                await connection.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
        await engine.dispose()
