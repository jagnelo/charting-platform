from __future__ import annotations

from copy import copy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.application import PostgresStrategyLabV2Adapter
from app.strategy_lab_v2.canonical import content_digest, freeze_json
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.postgres_resources import PostgresResourceReader
from app.strategy_lab_v2.postgres_result_materialization import (
    PostgresResultMaterializationAdapter,
    PostgresResultMaterializationSchema,
)
from app.strategy_lab_v2.postgres_search_state import (
    PostgresSearchStateAdapter,
    PostgresSearchStateSchema,
)
from app.strategy_lab_v2.postgres_storage import PostgresAggregateStore, PostgresStorageSchema
from app.strategy_lab_v2.postgres_walk_forward_plan import PostgresWalkForwardPlanAdapter
from app.strategy_lab_v2.resource_mutations import ResourceMutationRequest
from app.strategy_lab_v2.search_state import (
    SearchCandidatePhase,
    SearchCandidateState,
    SearchExecutionState,
    SearchStateDecision,
)
from app.strategy_lab_v2.walk_forward_queue import initialize_walk_forward_training_queue
from app.strategy_lab_v2.walk_forward_search import select_walk_forward_oos_tasks
from app.strategy_lab_v2.walk_forward_trials import (
    materialize_walk_forward_oos_trials,
    materialize_walk_forward_training_trials,
    training_score_from_result_manifest,
)

NOW = datetime(2026, 10, 6, 18, 0, tzinfo=UTC)
_WALK_FORWARD_FIXTURES = import_module("app.strategy_lab_v2.tests.test_walk_forward_application")
User = cast(Any, getattr(_WALK_FORWARD_FIXTURES, "User"))
_setup = cast(Any, getattr(_WALK_FORWARD_FIXTURES, "_setup"))
_inputs = cast(
    Any, getattr(import_module("app.strategy_lab_v2.tests.test_nautilus_trial_assembly"), "_inputs")
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
async def test_postgres_composed_walk_forward_training_selection_and_append_restart(
    pg_container,
    test_database_url: str | None,
) -> None:
    """Reload all phase inputs from PostgreSQL after an OOS append interruption."""

    raw_url = test_database_url or pg_container.get_connection_url()
    engine = create_async_engine(_async_postgres_url(raw_url), pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex
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
    tables = (
        search_schema.search_table,
        search_schema.candidate_table,
        aggregate_schema.aggregate_table,
        aggregate_schema.receipt_table,
        manifest_schema.manifest_table,
    )
    try:
        async with engine.begin() as connection:
            statements = (
                *search_schema.statements,
                *aggregate_schema.statements,
                *manifest_schema.statements,
            )
            for statement in statements:
                await connection.execute(text(statement))

        graph = _inputs()
        _fixture, source_reader, _unused_plans, definition, first, second = _setup()
        aggregate_store = PostgresAggregateStore(session_factory, schema=aggregate_schema)

        def build_persistence():
            return replace(
                PostgresStrategyLabV2Persistence.build(session_factory),
                aggregate_store=aggregate_store,
                resources=PostgresResourceReader(aggregate_store),
                walk_forward_plans=PostgresWalkForwardPlanAdapter(aggregate_store),
                search_state=PostgresSearchStateAdapter(session_factory, schema=search_schema),
                result_materialization=PostgresResultMaterializationAdapter(
                    session_factory,
                    schema=manifest_schema,
                ),
            )

        phase_time = datetime.now(UTC) - timedelta(minutes=5)
        adapter = PostgresStrategyLabV2Adapter(
            session_factory,
            persistence=build_persistence(),
            clock=lambda: phase_time + timedelta(minutes=1),
        )
        owner = "42"
        contracts = (
            (ApiResourceType.STRATEGY, graph["strategy_manifest"].strategy),
            (ApiResourceType.PACKAGE, graph["strategy_package"]),
            (ApiResourceType.PORTFOLIO, graph["portfolio"]),
            (
                ApiResourceType.SNAPSHOT,
                graph["snapshot"],
            ),
            (
                ApiResourceType.EXPERIMENT,
                source_reader.contracts[
                    (ApiResourceType.EXPERIMENT, definition.experiment_fingerprint)
                ],
            ),
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
                snapshot=source_reader.contracts[
                    (ApiResourceType.SNAPSHOT, first.snapshot_fingerprint)
                ],
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
    finally:
        async with engine.begin() as connection:
            for table in tables:
                await connection.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
        await engine.dispose()
