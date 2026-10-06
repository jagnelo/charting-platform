from __future__ import annotations

from copy import copy
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
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.postgres_search_state import (
    PostgresSearchStateAdapter,
    PostgresSearchStateSchema,
)
from app.strategy_lab_v2.search_state import (
    SearchCandidatePhase,
    SearchCandidateState,
    SearchExecutionState,
    SearchStateDecision,
)
from app.strategy_lab_v2.walk_forward_trials import materialize_walk_forward_training_trials

NOW = datetime(2026, 10, 6, 18, 0, tzinfo=UTC)
_WALK_FORWARD_FIXTURES = import_module("app.strategy_lab_v2.tests.test_walk_forward_application")
User = cast(Any, getattr(_WALK_FORWARD_FIXTURES, "User"))
_setup = cast(Any, getattr(_WALK_FORWARD_FIXTURES, "_setup"))
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
