from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.strategy_lab_v2.artifact_application import LocalArtifactPublicationService
from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.dispatch import DispatchRequest, build_dispatch_envelope
from app.strategy_lab_v2.dispatch_payload import DispatchPayload
from app.strategy_lab_v2.nautilus_worker_terminal import (
    create_nautilus_oos_worker_terminal_evidence_resolver,
)
from app.strategy_lab_v2.outcomes import OutcomeUpdate
from app.strategy_lab_v2.postgres_artifact_commit import (
    PostgresArtifactCommitAdapter,
    PostgresArtifactCommitSchema,
)
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
from app.strategy_lab_v2.postgres_worker_settlement import (
    PostgresWorkerSettlementAdapter,
    PostgresWorkerSettlementSchema,
)
from app.strategy_lab_v2.postgres_worker_state import (
    PostgresWorkerStateAdapter,
    PostgresWorkerStateSchema,
)
from app.strategy_lab_v2.progress import ExecutionProgressUpdate, ProgressPhase
from app.strategy_lab_v2.redis_transport import RedisDispatchTransport
from app.strategy_lab_v2.tests.test_nautilus_worker_terminal import (
    NOW,
    _successful_context_and_lookup,
)
from app.strategy_lab_v2.tests.test_trial_hydration import MemoryDomainReader
from app.strategy_lab_v2.trial_hydration import NautilusTrialDomainHydrator
from app.strategy_lab_v2.worker_consumer import (
    RedisDispatchWorker,
    WorkerEntryDecision,
)
from app.strategy_lab_v2.worker_evidence import WorkerTerminalEvidenceLookup
from app.strategy_lab_v2.worker_terminal_adapter import PostgresWorkerTerminalAdapter


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
async def test_oos_terminal_commit_survives_worker_loss_before_real_redis_ack(
    pg_container,
    test_database_url: str | None,
    redis_url: str,
    tmp_path: Path,
) -> None:
    """Real PostgreSQL terminal adapters and Redis reclaim are idempotent."""

    context, lookup, _resolver, _publisher, graph = _successful_context_and_lookup(
        tmp_path / "oos-terminal", stable=False, with_graph=True
    )
    owner_id = lookup.binding.owner_id
    attempt_id = context.request.admission.attempt_id
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
                or attempt_id != context.request.runtime_request.attempt_id
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

        async def replay(entry):
            return await restarted.terminal.write(replace(context, entry=entry))

        cycle = await restarted_worker.handle_once(replay)
        assert len(cycle.entries) == 1
        assert cycle.entries[0].decision is WorkerEntryDecision.ACKNOWLEDGED
        assert cycle.entries[0].handler.receipt_digest == first_terminal.receipt_digest
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
