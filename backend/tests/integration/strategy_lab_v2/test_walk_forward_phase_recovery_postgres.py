from __future__ import annotations

from copy import copy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.application import PostgresStrategyLabV2Adapter
from app.strategy_lab_v2.canonical import content_digest, freeze_json
from app.strategy_lab_v2.conformance_fixtures import resolve_nautilus_rc_conformance
from app.strategy_lab_v2.contracts import AttemptState, ProductClass, RunAttempt, ScientificTrial
from app.strategy_lab_v2.outbox_relay import OutboxRelayDecision, relay_outbox_message
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.postgres_event_transaction import (
    PostgresExecutionEventSchema,
    PostgresExecutionEventTransactionAdapter,
)
from app.strategy_lab_v2.postgres_execution_state import (
    PostgresExecutionStateAdapter,
    PostgresExecutionStateSchema,
)
from app.strategy_lab_v2.postgres_resources import PostgresResourceReader
from app.strategy_lab_v2.postgres_result_materialization import (
    PostgresResultMaterializationAdapter,
    PostgresResultMaterializationSchema,
)
from app.strategy_lab_v2.postgres_runtime_execution import (
    PostgresRuntimeExecutionAdapter,
    PostgresRuntimeExecutionSchema,
)
from app.strategy_lab_v2.postgres_search_dispatch import (
    PostgresSearchDispatchAdapter,
    PostgresSearchDispatchSchema,
)
from app.strategy_lab_v2.postgres_search_state import (
    PostgresSearchStateAdapter,
    PostgresSearchStateSchema,
)
from app.strategy_lab_v2.postgres_storage import PostgresAggregateStore, PostgresStorageSchema
from app.strategy_lab_v2.postgres_submission import (
    PostgresSubmissionDispatchAdapter,
    PostgresSubmissionSchema,
)
from app.strategy_lab_v2.postgres_walk_forward_plan import PostgresWalkForwardPlanAdapter
from app.strategy_lab_v2.postgres_worker_state import (
    PostgresWorkerStateAdapter,
    PostgresWorkerStateSchema,
)
from app.strategy_lab_v2.redis_transport import RedisDispatchTransport
from app.strategy_lab_v2.resource_mutations import ResourceMutationRequest
from app.strategy_lab_v2.search_dispatch_preparation import NautilusTrialPreparationContext
from app.strategy_lab_v2.search_preparation_composition import (
    SearchPreparationHostBindings,
    create_search_preparation_evidence_resolver,
)
from app.strategy_lab_v2.search_state import (
    SearchCandidatePhase,
    SearchCandidateState,
    SearchExecutionState,
    SearchStateDecision,
)
from app.strategy_lab_v2.walk_forward_queue import initialize_walk_forward_training_queue
from app.strategy_lab_v2.walk_forward_search import (
    WalkForwardExecutionDefinition,
    select_walk_forward_oos_tasks,
)
from app.strategy_lab_v2.walk_forward_trials import (
    materialize_walk_forward_oos_trials,
    materialize_walk_forward_training_trials,
    training_score_from_result_manifest,
)
from app.strategy_lab_v2.worker_callbacks import create_default_search_dispatch_binding_resolver
from app.strategy_lab_v2.worker_handoff import decode_worker_handoff
from app.strategy_lab_v2.worker_initial_state import ensure_worker_initial_state
from app.strategy_lab_v2.workers import WorkerKind, WorkerProfile

NOW = datetime(2026, 10, 6, 18, 0, tzinfo=UTC)
_WALK_FORWARD_FIXTURES = import_module("app.strategy_lab_v2.tests.test_walk_forward_application")
User = cast(Any, getattr(_WALK_FORWARD_FIXTURES, "User"))
_setup = cast(Any, getattr(_WALK_FORWARD_FIXTURES, "_setup"))
_PREPARATION_FIXTURES = import_module("app.strategy_lab_v2.tests.test_search_dispatch_preparation")
_preparation_setup = cast(Any, getattr(_PREPARATION_FIXTURES, "_setup"))
_CONFORMANCE_FIXTURES = import_module("app.strategy_lab_v2.tests.test_conformance_fixtures")
_rc_probe = cast(Any, getattr(_CONFORMANCE_FIXTURES, "_rc_probe"))
_rc_receipt = cast(Any, getattr(_CONFORMANCE_FIXTURES, "_rc_receipt"))
_rc_runtime = cast(Any, getattr(_CONFORMANCE_FIXTURES, "_rc_runtime"))
_RUNTIME_ABI = getattr(
    import_module("app.strategy_lab_v2.tests.test_nautilus_trial_materializer"), "RUNTIME_ABI"
)
_JsonFrozenSeriesDecoder = getattr(
    import_module("app.strategy_lab_v2.tests.test_nautilus_trial_assembly"),
    "JsonFrozenSeriesDecoder",
)
_authoritative_result = getattr(
    import_module("app.strategy_lab_v2.tests.test_walk_forward_search"),
    "_authoritative_result",
)


def _async_postgres_url(raw_url: str) -> str:
    if raw_url.startswith("postgresql+asyncpg://"):
        return raw_url
    if raw_url.startswith("postgresql+psycopg2://"):
        return raw_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    raise ValueError("integration database URL must use PostgreSQL")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_walk_forward_oos_queue_append_recovers_after_coordinator_restart(
    pg_container,
    test_database_url: str | None,
) -> None:
    raw_url = test_database_url or pg_container.get_connection_url()
    engine = create_async_engine(_async_postgres_url(raw_url), pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex
    schema = PostgresSearchStateSchema(
        search_table=f"slv2_wf_recovery_search_{suffix}",
        candidate_table=f"slv2_wf_recovery_candidates_{suffix}",
    )
    owner = "walk-forward-recovery-owner"
    experiment = content_digest("walk-forward-recovery-experiment")
    training = SearchExecutionState(
        experiment_fingerprint=experiment,
        candidates=(
            SearchCandidateState(
                0,
                content_digest("training-trial-a"),
                SearchCandidatePhase.SUCCEEDED,
                "training-attempt-a",
                1,
                content_digest("training-result-a"),
                NOW,
            ),
            SearchCandidateState(
                1,
                content_digest("training-trial-b"),
                SearchCandidatePhase.SUCCEEDED,
                "training-attempt-b",
                1,
                content_digest("training-result-b"),
                NOW,
            ),
        ),
        updated_at=NOW,
    )
    selected_oos = (content_digest("selected-oos-fold-a"), content_digest("selected-oos-fold-b"))
    try:
        async with engine.begin() as connection:
            for statement in schema.statements:
                await connection.execute(text(statement))

        first_coordinator = PostgresSearchStateAdapter(session_factory, schema=schema)
        initialized = await first_coordinator.initialize(principal=owner, state=training)
        assert initialized.decision is SearchStateDecision.APPLY

        # The atomic queue append commits, then the coordinator is assumed to
        # stop before it can publish either OOS dispatch. No Redis side effect
        # is needed to recover the immutable PostgreSQL phase boundary.
        appended = await first_coordinator.append_candidates(
            principal=owner,
            experiment_fingerprint=experiment,
            expected_state_fingerprint=training.fingerprint,
            trial_fingerprints=selected_oos,
            now=NOW,
        )
        assert appended.decision is SearchStateDecision.APPLY
        assert (
            tuple(item.trial_fingerprint for item in appended.state.candidates)
            == tuple(item.trial_fingerprint for item in training.candidates) + selected_oos
        )

        restarted_coordinator = PostgresSearchStateAdapter(session_factory, schema=schema)
        recovered = await restarted_coordinator.load(
            principal=owner,
            experiment_fingerprint=experiment,
        )
        assert recovered == appended.state
        assert recovered is not None
        assert all(
            item.phase is SearchCandidatePhase.SUCCEEDED for item in recovered.candidates[:2]
        )
        assert all(item.phase is SearchCandidatePhase.PENDING for item in recovered.candidates[2:])

        replay = await restarted_coordinator.append_candidates(
            principal=owner,
            experiment_fingerprint=experiment,
            expected_state_fingerprint=training.fingerprint,
            trial_fingerprints=selected_oos,
            now=NOW,
        )
        assert replay.decision is SearchStateDecision.REPLAY_EXISTING
        assert replay.state == recovered
        assert len(replay.state.candidates) == len(training.candidates) + len(selected_oos)
        assert (
            await restarted_coordinator.load(
                principal="different-owner",
                experiment_fingerprint=experiment,
            )
            is None
        )

        async with engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        f"SELECT candidate_index, trial_fingerprint FROM {schema.candidate_table} "
                        "WHERE owner_id = :owner_id AND experiment_fingerprint = :experiment "
                        "ORDER BY candidate_index"
                    ),
                    {"owner_id": owner, "experiment": experiment},
                )
            ).all()
        assert len(rows) == len(training.candidates) + len(selected_oos)
        assert [row.candidate_index for row in rows] == list(range(len(rows)))
        assert tuple(row.trial_fingerprint for row in rows[-2:]) == selected_oos
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f"DROP TABLE IF EXISTS {schema.candidate_table} CASCADE"))
            await connection.execute(text(f"DROP TABLE IF EXISTS {schema.search_table} CASCADE"))
        await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_application_replays_oos_publication_after_postgres_phase_append_interruption(
    pg_container,
    test_database_url: str | None,
) -> None:
    """A fresh coordinator repairs OOS publication after a pre-append crash."""

    raw_url = test_database_url or pg_container.get_connection_url()
    engine = create_async_engine(_async_postgres_url(raw_url), pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex
    schema = PostgresSearchStateSchema(
        search_table=f"slv2_wf_app_recovery_search_{suffix}",
        candidate_table=f"slv2_wf_app_recovery_candidates_{suffix}",
    )
    try:
        async with engine.begin() as connection:
            for statement in schema.statements:
                await connection.execute(text(statement))

        adapter, reader, _plan_store, definition, first, second = _setup()
        queue_store = PostgresSearchStateAdapter(session_factory, schema=schema)
        adapter._persistence.search_state = queue_store
        training_resolution = await adapter.initialize_walk_forward_training(
            principal=User(),
            request_id="initialize-training-before-restart",
            definition=definition,
        )
        assert training_resolution.decision is SearchStateDecision.APPLY
        phase_time = datetime.now(UTC) + timedelta(minutes=1)
        adapter._clock = lambda: phase_time + timedelta(minutes=1)

        training = materialize_walk_forward_training_trials(
            definition.training_plan,
            (first, second),
            definition.folds,
            definition.observation_boundaries,
        )
        trial_by_id = {trial.trial_id: trial for trial in training.trials}
        for index, candidate in enumerate(training_resolution.state.candidates):
            attempt_id = f"postgres-training-attempt-{index}"
            result_fingerprint = content_digest({"postgres-training-result": index})
            adapter._result_materialization.manifests[attempt_id] = _authoritative_result(
                trial_by_id[candidate.trial_fingerprint],
                definition.metric_id,
                Decimal(index + 1),
                attempt_id=attempt_id,
                snapshot=reader.contracts[(ApiResourceType.SNAPSHOT, first.snapshot_fingerprint)],
            )
            await queue_store.start_candidate(
                principal="42",
                experiment_fingerprint=definition.experiment_fingerprint,
                candidate_index=index,
                attempt_id=attempt_id,
                now=phase_time + timedelta(seconds=index * 2),
            )
            await queue_store.record_terminal(
                principal="42",
                experiment_fingerprint=definition.experiment_fingerprint,
                candidate_index=index,
                attempt_id=attempt_id,
                phase=SearchCandidatePhase.SUCCEEDED,
                now=phase_time + timedelta(seconds=index * 2 + 1),
                result_fingerprint=result_fingerprint,
            )

        class InterruptedSearchState:
            async def load(self, **kwargs):
                return await queue_store.load(**kwargs)

            async def append_candidates(self, **_kwargs):
                raise RuntimeError("simulated coordinator loss before OOS queue append")

        adapter._persistence.search_state = InterruptedSearchState()
        with pytest.raises(RuntimeError, match="simulated coordinator loss"):
            await adapter.append_walk_forward_oos_candidates(
                principal=User(),
                request_id="append-oos-before-crash",
                experiment_fingerprint=definition.experiment_fingerprint,
            )

        pre_append = await PostgresSearchStateAdapter(session_factory, schema=schema).load(
            principal="42",
            experiment_fingerprint=definition.experiment_fingerprint,
        )
        assert pre_append is not None
        assert len(pre_append.candidates) == len(training_resolution.state.candidates)
        published_before_restart = tuple(adapter._published_trials)

        # Rebuild the application object and search-state adapter as a new
        # process would, while the resource and result repositories continue
        # to represent their already-committed durable counterparts.
        restarted = copy(adapter)
        restarted._persistence = SimpleNamespace(**vars(adapter._persistence))
        restarted._persistence.search_state = PostgresSearchStateAdapter(
            session_factory,
            schema=schema,
        )
        resumed = await restarted.append_walk_forward_oos_candidates(
            principal=User(),
            request_id="resume-oos-after-crash",
            experiment_fingerprint=definition.experiment_fingerprint,
        )
        assert resumed.resolution.decision is SearchStateDecision.APPLY
        assert len(resumed.oos_task_bindings) == len(definition.folds)
        assert tuple(adapter._published_trials) == published_before_restart + tuple(
            binding.trial_fingerprint
            for binding in resumed.oos_task_bindings
            if binding.trial_fingerprint not in published_before_restart
        )

        replay = await restarted.append_walk_forward_oos_candidates(
            principal=User(),
            request_id="replay-oos-after-crash",
            experiment_fingerprint=definition.experiment_fingerprint,
        )
        assert replay.resolution.decision is SearchStateDecision.REPLAY_EXISTING
        assert replay.resolution.state == resumed.resolution.state
        assert len({item.trial_fingerprint for item in replay.resolution.state.candidates}) == len(
            replay.resolution.state.candidates
        )
        assert all(
            item.phase is SearchCandidatePhase.PENDING
            for item in replay.resolution.state.candidates[
                len(training_resolution.state.candidates) :
            ]
        )
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f"DROP TABLE IF EXISTS {schema.candidate_table} CASCADE"))
            await connection.execute(text(f"DROP TABLE IF EXISTS {schema.search_table} CASCADE"))
        await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_composed_walk_forward_recovery_dispatch_and_outbox_restart(
    tmp_path: Path,
    pg_container,
    redis_url: str,
    test_database_url: str | None,
) -> None:
    """Recover training selection, OOS dispatch, and outbox replay from PostgreSQL."""

    raw_url = test_database_url or pg_container.get_connection_url()
    engine = create_async_engine(_async_postgres_url(raw_url), pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex[:8]
    search_schema = PostgresSearchStateSchema(
        search_table=f"slv2_wf_full_search_{suffix}",
        candidate_table=f"slv2_wf_full_candidates_{suffix}",
    )
    aggregate_schema = PostgresStorageSchema(
        aggregate_table=f"slv2_wf_full_aggregates_{suffix}",
        receipt_table=f"slv2_wf_full_receipts_{suffix}",
    )
    manifest_schema = PostgresResultMaterializationSchema(
        manifest_table=f"slv2_wf_full_manifests_{suffix}"
    )
    worker_schema = PostgresWorkerStateSchema(
        profile_table=f"slv2_wf_full_worker_profiles_{suffix}",
        reservation_table=f"slv2_wf_full_worker_reservations_{suffix}",
        lease_table=f"slv2_wf_full_leases_{suffix}",
        observation_table=f"slv2_wf_full_lease_observations_{suffix}",
    )
    event_schema = PostgresExecutionEventSchema(
        event_table=f"slv2_wf_full_events_{suffix}",
        cursor_table=f"slv2_wf_full_event_cursors_{suffix}",
        audit_table=f"slv2_wf_full_audit_{suffix}",
        outbox_table=f"slv2_wf_full_outbox_{suffix}",
    )
    dispatch_schema = PostgresSearchDispatchSchema(
        admission_table=f"slv2_wf_full_admissions_{suffix}",
        dispatch_table=f"slv2_wf_full_dispatches_{suffix}",
        payload_table=f"slv2_wf_full_payloads_{suffix}",
        outbox_table=event_schema.outbox_table,
    )
    submission_schema = PostgresSubmissionSchema(
        submission_table=f"slv2_wf_full_submissions_{suffix}",
        dispatch_table=f"slv2_wf_full_submission_dispatches_{suffix}",
        # Production submission and search dispatch adapters share this
        # content-addressed payload table; the worker entrypoint reads through
        # the submission adapter regardless of dispatch origin.
        payload_table=dispatch_schema.payload_table,
        outbox_table=f"slv2_wf_full_submission_outbox_{suffix}",
    )
    execution_state_schema = PostgresExecutionStateSchema(
        outcome_table=f"slv2_wf_full_outcomes_{suffix}",
        progress_table=f"slv2_wf_full_progress_{suffix}",
    )
    runtime_execution_schema = PostgresRuntimeExecutionSchema(
        state_table=f"slv2_wf_full_runtime_{suffix}",
        update_table=f"slv2_wf_full_runtime_updates_{suffix}",
    )
    statements = (
        *search_schema.statements,
        *aggregate_schema.statements,
        *manifest_schema.statements,
        *worker_schema.statements,
        *event_schema.statements,
        *dispatch_schema.statements,
        submission_schema.statements[0],
        submission_schema.statements[1],
        *execution_state_schema.statements,
        *runtime_execution_schema.statements,
    )
    tables = (
        search_schema.search_table,
        search_schema.candidate_table,
        aggregate_schema.aggregate_table,
        aggregate_schema.receipt_table,
        manifest_schema.manifest_table,
        worker_schema.profile_table,
        worker_schema.reservation_table,
        worker_schema.lease_table,
        worker_schema.observation_table,
        event_schema.event_table,
        event_schema.cursor_table,
        event_schema.audit_table,
        event_schema.outbox_table,
        dispatch_schema.admission_table,
        dispatch_schema.dispatch_table,
        dispatch_schema.payload_table,
        submission_schema.submission_table,
        submission_schema.dispatch_table,
        submission_schema.outbox_table,
        execution_state_schema.outcome_table,
        execution_state_schema.progress_table,
        runtime_execution_schema.state_table,
        runtime_execution_schema.update_table,
    )
    redis_client: Redis | None = None
    try:
        async with engine.begin() as connection:
            for statement in statements:
                await connection.execute(text(statement))

        _fixture, source_reader, _unused_plans, definition, first, second = _setup()
        aggregate_store = PostgresAggregateStore(session_factory, schema=aggregate_schema)
        search_state = PostgresSearchStateAdapter(session_factory, schema=search_schema)
        worker_state = PostgresWorkerStateAdapter(session_factory, schema=worker_schema)
        dispatch_store = PostgresSearchDispatchAdapter(
            session_factory,
            schema=dispatch_schema,
            search_state=search_state,
            worker_state=worker_state,
        )

        def build_persistence():
            return replace(
                PostgresStrategyLabV2Persistence.build(session_factory),
                aggregate_store=aggregate_store,
                resources=PostgresResourceReader(aggregate_store),
                walk_forward_plans=PostgresWalkForwardPlanAdapter(aggregate_store),
                search_state=search_state,
                search_dispatch=dispatch_store,
                worker_state=worker_state,
                execution_events=PostgresExecutionEventTransactionAdapter(
                    session_factory,
                    schema=event_schema,
                ),
                result_materialization=PostgresResultMaterializationAdapter(
                    session_factory,
                    schema=manifest_schema,
                ),
                submissions=PostgresSubmissionDispatchAdapter(
                    session_factory,
                    schema=submission_schema,
                ),
                execution_state=PostgresExecutionStateAdapter(
                    session_factory,
                    schema=execution_state_schema,
                ),
                runtime_execution=PostgresRuntimeExecutionAdapter(
                    session_factory,
                    schema=runtime_execution_schema,
                ),
            )

        phase_time = datetime.now(UTC) - timedelta(minutes=5)
        (
            _preparation_graph,
            artifact_store,
            _package_resolver,
            _runtime_materializer,
            base_context,
            _worker_reader,
        ) = _preparation_setup(tmp_path / "walk-forward-dispatch")
        first = _preparation_graph.trial
        second = ScientificTrial.create(
            experiment_fingerprint=_preparation_graph.experiment.fingerprint,
            snapshot_fingerprint=first.snapshot_fingerprint,
            preflight_report=first.preflight_report,
            parameter_set={"window": 21},
            scenario=first.scenario,
            seed=first.seed,
        )
        definition = WalkForwardExecutionDefinition(
            experiment_fingerprint=_preparation_graph.experiment.fingerprint,
            candidate_fingerprints=(first.trial_id, second.trial_id),
            observation_boundaries=definition.observation_boundaries,
            spec=definition.spec,
            metric_id=definition.metric_id,
            direction=definition.direction,
        )
        runtime = _rc_runtime()
        conformance = resolve_nautilus_rc_conformance(
            runtime,
            _rc_probe(runtime),
            _rc_receipt(runtime),
            build_digest=content_digest("nautilus-v2-rc6-build"),
            tested_at=NOW,
        )
        context = NautilusTrialPreparationContext.from_authoritative_backtest_conformance(
            conformance_resolution=conformance,
            product_classes=frozenset({ProductClass.EQUITY}),
            execution_models=frozenset({"bar-close-v1"}),
            account_models=frozenset({"cash-equity-v1"}),
            market_context=base_context.market_context,
            runtime_profile=base_context.runtime_profile,
            admission_ledger=base_context.admission_ledger,
            image_name=base_context.image_name,
            output_path=base_context.output_path,
            now=phase_time + timedelta(minutes=1),
            lease_duration=base_context.lease_duration,
        )

        async def resolve_context(_request, _graph):
            return context

        persistence = build_persistence()
        evidence_resolver = create_search_preparation_evidence_resolver(
            persistence,
            artifact_store.root,
            host_bindings=SearchPreparationHostBindings(
                runtime_abi=_RUNTIME_ABI,
                series_decoder=_JsonFrozenSeriesDecoder(),
                context_resolver=resolve_context,
            ),
            conformance_resolution=conformance,
        )
        await worker_state.ensure_profile(
            WorkerProfile(
                "walk-forward-recovery-worker",
                WorkerKind.BACKTEST,
                context.runtime_profile.fingerprint,
            )
        )

        adapter = PostgresStrategyLabV2Adapter(
            session_factory,
            persistence=persistence,
            clock=lambda: phase_time + timedelta(minutes=1),
        )
        owner = "42"
        contracts = (
            (ApiResourceType.STRATEGY, _preparation_graph.strategies[0]),
            (ApiResourceType.PACKAGE, next(iter(_preparation_graph.packages.values()))),
            (ApiResourceType.PORTFOLIO, _preparation_graph.portfolio),
            (ApiResourceType.SNAPSHOT, _preparation_graph.snapshot),
            (ApiResourceType.EXPERIMENT, _preparation_graph.experiment),
            (ApiResourceType.TRIAL, first),
            (ApiResourceType.TRIAL, second),
        )
        for index, (resource_type, contract) in enumerate(contracts):
            attributes = dict(freeze_json(contract))
            if resource_type is ApiResourceType.TRIAL:
                attributes["trial_id"] = contract.trial_id
            result = await adapter.create_resource(
                principal=owner,
                request_id=f"persist-walk-forward-input-{index}",
                request=ResourceMutationRequest(
                    resource_type,
                    f"walk-forward-input-{index}",
                    {"attributes": attributes},
                    phase_time,
                ),
            )
            assert result.receipt is not None, result.resolution.rejection_reason

        plan_persisted = await adapter._persistence.walk_forward_plans.persist(
            principal=owner,
            definition=definition,
        )
        assert plan_persisted.decision.value == "apply"
        initialized = await adapter.initialize_walk_forward_training(
            principal=owner,
            request_id="postgres-wf-initialize",
            definition=definition,
        )
        assert initialized.decision is SearchStateDecision.APPLY

        training = materialize_walk_forward_training_trials(
            definition.training_plan,
            (first, second),
            definition.folds,
            definition.observation_boundaries,
        )
        initial_queue, _training_queue_bindings = initialize_walk_forward_training_queue(
            definition.training_plan,
            training,
            now=None,
        )
        assert tuple(item.trial_fingerprint for item in initial_queue.candidates) == tuple(
            item.trial_fingerprint for item in initialized.state.candidates
        )
        trial_by_id = {trial.trial_id: trial for trial in training.trials}
        persisted_training_manifests = {}
        for index, candidate in enumerate(initialized.state.candidates):
            attempt_id = f"fully-persisted-training-attempt-{index}"
            manifest = _authoritative_result(
                trial_by_id[candidate.trial_fingerprint],
                definition.metric_id,
                Decimal(index + 1),
                attempt_id=attempt_id,
                snapshot=_preparation_graph.snapshot,
            )
            ensured = await adapter._persistence.result_materialization.ensure(
                principal=owner,
                manifest=manifest,
            )
            assert ensured.decision.value == "registered"
            persisted_training_manifests[attempt_id] = manifest
            await adapter._persistence.search_state.start_candidate(
                principal=owner,
                experiment_fingerprint=definition.experiment_fingerprint,
                candidate_index=index,
                attempt_id=attempt_id,
                now=phase_time + timedelta(seconds=2 * index),
            )
            await adapter._persistence.search_state.record_terminal(
                principal=owner,
                experiment_fingerprint=definition.experiment_fingerprint,
                candidate_index=index,
                attempt_id=attempt_id,
                phase=SearchCandidatePhase.SUCCEEDED,
                now=phase_time + timedelta(seconds=2 * index + 1),
                result_fingerprint=content_digest({"persisted-training-result": index}),
            )

        expected_scores = tuple(
            training_score_from_result_manifest(
                binding,
                persisted_training_manifests[
                    f"fully-persisted-training-attempt-{queue_binding.candidate_index}"
                ],
                metric_id=definition.metric_id,
            )
            for binding, queue_binding in zip(
                training.bindings,
                initialized.state.candidates,
                strict=True,
            )
        )
        expected_selection = select_walk_forward_oos_tasks(
            definition.training_plan,
            definition.folds,
            expected_scores,
        )
        expected_oos = materialize_walk_forward_oos_trials(
            expected_selection,
            (first, second),
            definition.folds,
            definition.observation_boundaries,
        )

        real_search_state = adapter._persistence.search_state

        class InterruptedAppend:
            async def load(self, **kwargs):
                return await real_search_state.load(**kwargs)

            async def append_candidates(self, **_kwargs):
                raise RuntimeError("simulated loss after PostgreSQL OOS trial publication")

        adapter._persistence = cast(
            Any,
            replace(
                cast(Any, adapter._persistence),
                search_state=InterruptedAppend(),
            ),
        )
        with pytest.raises(
            RuntimeError,
            match="simulated loss after PostgreSQL OOS trial publication",
        ):
            await adapter.append_walk_forward_oos_candidates(
                principal=owner,
                request_id="append-oos-crash-boundary",
                experiment_fingerprint=definition.experiment_fingerprint,
            )
        queue_before_restart = await real_search_state.load(
            principal=owner,
            experiment_fingerprint=definition.experiment_fingerprint,
        )
        assert queue_before_restart is not None
        assert len(queue_before_restart.candidates) == len(initialized.state.candidates)

        restarted = PostgresStrategyLabV2Adapter(
            session_factory,
            persistence=build_persistence(),
            clock=lambda: phase_time + timedelta(minutes=1),
            search_dispatch_evidence=evidence_resolver,
        )
        resumed = await restarted.append_walk_forward_oos_candidates(
            principal=owner,
            request_id="resume-oos-after-full-postgres-restart",
            experiment_fingerprint=definition.experiment_fingerprint,
        )
        expected_ids = tuple(trial.trial_id for trial in expected_oos.trials)
        assert (
            tuple(binding.trial_fingerprint for binding in resumed.oos_task_bindings)
            == expected_ids
        )
        assert (
            tuple(
                item.trial_fingerprint
                for item in resumed.resolution.state.candidates[-len(expected_ids) :]
            )
            == expected_ids
        )

        replay = await restarted.append_walk_forward_oos_candidates(
            principal=owner,
            request_id="replay-oos-after-full-postgres-restart",
            experiment_fingerprint=definition.experiment_fingerprint,
        )
        assert replay.resolution.decision is SearchStateDecision.REPLAY_EXISTING
        assert replay.resolution.state == resumed.resolution.state
        assert len({item.trial_fingerprint for item in replay.resolution.state.candidates}) == len(
            replay.resolution.state.candidates
        )
        for trial_id in expected_ids:
            assert (
                await restarted._resources.get_domain_contract_by_fingerprint(
                    principal=SimpleNamespace(id=owner),
                    resource_type=ApiResourceType.TRIAL,
                    fingerprint=trial_id,
                )
                is not None
            )
        assert (
            await restarted._resources.get_domain_contract_by_fingerprint(
                principal=SimpleNamespace(id="foreign-owner"),
                resource_type=ApiResourceType.TRIAL,
                fingerprint=expected_ids[0],
            )
            is None
        )

        oos_candidate_index = len(initialized.state.candidates)
        dispatch_command = {
            "principal": owner,
            "request_id": "dispatch-recovered-oos-candidate",
            "idempotency_key": "walk-forward-oos-recovery-dispatch-key",
            "experiment_fingerprint": definition.experiment_fingerprint,
            "candidate_index": oos_candidate_index,
            "queue_name": "strategy-backtest",
        }
        dispatched = await restarted.dispatch_walk_forward_training_candidate(**dispatch_command)
        assert dispatched.decision.value == "enqueue"
        assert dispatched.envelope is not None
        assert (
            dispatched.search_state.candidates[oos_candidate_index].attempt_id
            == dispatched.envelope.request.attempt_id
        )
        assert (
            dispatched.search_state.candidates[oos_candidate_index].phase
            is SearchCandidatePhase.RUNNING
        )
        dispatch_record = await restarted._persistence.search_dispatch.load(
            principal=owner,
            experiment_fingerprint=definition.experiment_fingerprint,
            candidate_index=oos_candidate_index,
            attempt_id=dispatched.envelope.request.attempt_id,
        )
        assert dispatch_record is not None
        assert dispatch_record.request == dispatched.envelope.request
        shared_worker_payload = await restarted._persistence.submissions.load_payload(
            dispatch_record.request.payload_digest
        )
        assert shared_worker_payload is not None
        assert shared_worker_payload.payload_digest == dispatch_record.request.payload_digest
        worker_request = decode_worker_handoff(shared_worker_payload)
        binding_resolver = create_default_search_dispatch_binding_resolver(restarted._persistence)
        submission_binding = await cast(Any, binding_resolver)(dispatch_record)
        # Internal walk-forward submissions have no API submissions row; the
        # exact PostgreSQL search-dispatch identity supplies the terminal
        # submission binding and cannot drift from the payload or attempt.
        assert submission_binding is not None
        assert submission_binding.owner_id == owner
        assert submission_binding.receipt.request.idempotency_key == (
            dispatch_record.request.idempotency_key
        )
        assert submission_binding.receipt.request.operation == dispatch_record.request.queue_name
        assert submission_binding.receipt.request.attempt_id == dispatch_record.request.attempt_id
        assert submission_binding.receipt.request.payload_digest == (
            dispatch_record.request.payload_digest
        )
        await ensure_worker_initial_state(
            execution_state=restarted._persistence.execution_state,
            runtime_execution=restarted._persistence.runtime_execution,
            principal=owner,
            request=worker_request,
            submission=submission_binding.receipt,
        )
        restarted_execution = await restarted._persistence.execution_state.read_context(
            principal=owner,
            attempt_id=worker_request.runtime_request.attempt_id,
        )
        assert restarted_execution is not None
        assert restarted_execution.outcome.submission_id == submission_binding.receipt.submission_id
        assert restarted_execution.outcome.status.value == "accepted"
        assert restarted_execution.progress.phase.value == "queued"
        assert (
            await restarted._persistence.runtime_execution.load(
                principal=owner,
                attempt_id=worker_request.runtime_request.attempt_id,
            )
            == worker_request.runtime_state
        )
        # Reconstruct persistence once more to prove process-restart idempotency.
        post_bootstrap_restart = PostgresStrategyLabV2Adapter(
            session_factory,
            persistence=build_persistence(),
            clock=lambda: phase_time + timedelta(minutes=1),
            search_dispatch_evidence=evidence_resolver,
        )
        await ensure_worker_initial_state(
            execution_state=post_bootstrap_restart._persistence.execution_state,
            runtime_execution=post_bootstrap_restart._persistence.runtime_execution,
            principal=owner,
            request=worker_request,
            submission=submission_binding.receipt,
        )

        persisted_attempt = await restarted._resources.get_domain_contract(
            principal=SimpleNamespace(id=owner),
            resource_type=ApiResourceType.ATTEMPT,
            resource_id=dispatched.envelope.request.attempt_id,
        )
        assert persisted_attempt is not None
        assert isinstance(persisted_attempt, RunAttempt)
        assert persisted_attempt.attempt_id == dispatched.envelope.request.attempt_id
        assert persisted_attempt.state is AttemptState.RUNNING
        assert (
            await restarted._persistence.search_dispatch.load(
                principal="foreign-owner",
                experiment_fingerprint=definition.experiment_fingerprint,
                candidate_index=oos_candidate_index,
            )
            is None
        )

        post_dispatch_restart = PostgresStrategyLabV2Adapter(
            session_factory,
            persistence=build_persistence(),
            clock=lambda: phase_time + timedelta(minutes=1),
            search_dispatch_evidence=evidence_resolver,
        )
        replayed_dispatch = await post_dispatch_restart.dispatch_walk_forward_training_candidate(
            **dispatch_command
        )
        assert replayed_dispatch.decision.value == "replay_existing"
        assert replayed_dispatch.envelope == dispatched.envelope
        assert replayed_dispatch.search_state == dispatched.search_state
        assert replayed_dispatch.admission_ledger == dispatched.admission_ledger

        outbox = await post_dispatch_restart._persistence.execution_events.load_outbox()
        assert len(outbox.messages) == 1
        assert (
            outbox.messages[0].aggregate_id
            == f"{definition.experiment_fingerprint}:{oos_candidate_index}"
        )
        assert outbox.messages[0].topic == dispatched.envelope.request.queue_name
        assert outbox.messages[0].payload_digest == dispatched.envelope.request.payload_digest

        redis_instance = Redis.from_url(redis_url, decode_responses=True)
        redis_client = redis_instance
        redis_namespace = f"strategy-lab:v2:walk-forward-recovery:{suffix}"
        transport = RedisDispatchTransport(redis_instance, namespace=redis_namespace)
        outbox_message = outbox.messages[0]
        first_relay = await relay_outbox_message(outbox, outbox_message, transport)
        assert first_relay.decision is OutboxRelayDecision.PUBLISHED
        assert first_relay.envelope is not None
        # Outbox envelopes have their own event/request identity. The
        # authenticated worker handoff must resolve through its preserved
        # content digest, not conflate transport IDs with OOS attempt IDs.
        relay_request = first_relay.envelope.request
        assert relay_request.attempt_id != dispatch_record.request.attempt_id
        assert relay_request.fingerprint != dispatch_record.request.fingerprint
        dispatch_by_payload = await dispatch_store.load_by_payload_digest(
            relay_request.payload_digest
        )
        assert dispatch_by_payload == dispatch_record

        # Simulate publisher loss after Redis accepted the envelope but before
        # PostgreSQL recorded the outbox acknowledgement.
        relay_restart = PostgresStrategyLabV2Adapter(
            session_factory,
            persistence=build_persistence(),
            clock=lambda: phase_time + timedelta(minutes=1),
            search_dispatch_evidence=evidence_resolver,
        )
        still_pending = await relay_restart._persistence.execution_events.load_outbox()
        assert outbox_message.message_id not in still_pending.published_message_ids
        replayed_relay = await relay_outbox_message(still_pending, outbox_message, transport)
        assert replayed_relay.decision is OutboxRelayDecision.REPLAY_EXISTING
        assert replayed_relay.state.published_message_ids == frozenset({outbox_message.message_id})
        assert await redis_instance.xlen(transport.stream_key(outbox_message.topic)) == 1

        acknowledged = await relay_restart._persistence.execution_events.acknowledge_outbox(
            outbox_message.message_id,
            expected_state_fingerprint=still_pending.fingerprint,
        )
        assert acknowledged.decision.value == "acknowledged"
        durable_outbox = await relay_restart._persistence.execution_events.load_outbox()
        assert durable_outbox.published_message_ids == frozenset({outbox_message.message_id})

        async with engine.connect() as connection:
            for table in (
                dispatch_schema.admission_table,
                dispatch_schema.dispatch_table,
                dispatch_schema.payload_table,
                event_schema.outbox_table,
            ):
                count = await connection.scalar(text(f"SELECT count(*) FROM {table}"))
                assert count == 1, table
    finally:
        if redis_client is not None:
            await redis_client.delete(
                f"strategy-lab:v2:walk-forward-recovery:{suffix}:stream:strategy-backtest",
                f"strategy-lab:v2:walk-forward-recovery:{suffix}:idempotency",
            )
            await redis_client.aclose()
        async with engine.begin() as connection:
            for table in tables:
                await connection.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
        await engine.dispose()
