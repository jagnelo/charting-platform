from __future__ import annotations

import asyncio
import socket
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
import uvicorn
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.application import PostgresStrategyLabV2Adapter
from app.strategy_lab_v2.canonical import content_digest, freeze_json
from app.strategy_lab_v2.conformance_fixtures import resolve_nautilus_rc_conformance
from app.strategy_lab_v2.contracts import (
    CarryInMode,
    ForwardInstance,
    ForwardState,
    MetricBasis,
    MetricSet,
    MetricValue,
    ProductClass,
)
from app.strategy_lab_v2.dispatch import SearchDispatchIntent
from app.strategy_lab_v2.engine_execution import NautilusExecutionScope
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.postgres_event_transaction import PostgresExecutionEventSchema
from app.strategy_lab_v2.postgres_resources import PostgresResourceReader
from app.strategy_lab_v2.postgres_search_dispatch import PostgresSearchDispatchSchema
from app.strategy_lab_v2.postgres_search_state import (
    PostgresSearchStateAdapter,
    PostgresSearchStateSchema,
)
from app.strategy_lab_v2.postgres_storage import PostgresAggregateStore, PostgresStorageSchema
from app.strategy_lab_v2.postgres_worker_state import (
    PostgresWorkerStateAdapter,
    PostgresWorkerStateSchema,
)
from app.strategy_lab_v2.resource_domains import rehydrate_resource_contract
from app.strategy_lab_v2.resource_mutations import ResourceMutationRequest
from app.strategy_lab_v2.search_dispatch_preparation import NautilusTrialPreparationContext
from app.strategy_lab_v2.search_dispatch_rpc import UnixSocketSearchDispatchClient
from app.strategy_lab_v2.search_preparation_composition import (
    SearchPreparationHostBindings,
    create_search_preparation_evidence_resolver,
)
from app.strategy_lab_v2.search_preparation_service import create_search_preparation_app
from app.strategy_lab_v2.search_state import new_search_execution_state
from app.strategy_lab_v2.tests.test_conformance_fixtures import (
    _rc_probe,
    _rc_receipt,
    _rc_runtime,
)
from app.strategy_lab_v2.tests.test_nautilus_trial_assembly import (
    BASE,
    JsonFrozenSeriesDecoder,
)
from app.strategy_lab_v2.tests.test_nautilus_trial_materializer import RUNTIME_ABI
from app.strategy_lab_v2.tests.test_search_dispatch_preparation import _setup
from app.strategy_lab_v2.trial_hydration import TrialDomainHydrationError
from app.strategy_lab_v2.workers import WorkerKind, WorkerProfile


async def _persist_trial_domain_graph(
    adapter: PostgresStrategyLabV2Adapter,
    *,
    principal: str,
    suffix: str,
    graph,
) -> None:
    resources = (
        (ApiResourceType.STRATEGY, graph.strategies[0]),
        (ApiResourceType.PACKAGE, next(iter(graph.packages.values()))),
        (ApiResourceType.PORTFOLIO, graph.portfolio),
        (ApiResourceType.SNAPSHOT, graph.snapshot),
        (ApiResourceType.EXPERIMENT, graph.experiment),
        (ApiResourceType.TRIAL, graph.trial),
        (ApiResourceType.ATTEMPT, graph.attempt),
    )
    for resource_type, contract in resources:
        attributes = dict(freeze_json(contract))
        if resource_type is ApiResourceType.ATTEMPT:
            # The worker contract addresses this resource by its attempt identity;
            # the domain fingerprint remains independently content-derived.
            attributes["resource_id"] = graph.attempt.attempt_id
        result = await adapter.create_resource(
            principal=principal,
            request_id=f"persist-{suffix}-{resource_type.value}",
            request=ResourceMutationRequest(
                resource_type,
                f"persist-{suffix}-{resource_type.value}",
                {"attributes": attributes},
                BASE,
            ),
        )
        assert result.receipt is not None, result.resolution.rejection_reason
        assert result.resolution.decision.value == "accept"


def _conformance_resolution():
    runtime = _rc_runtime()
    return resolve_nautilus_rc_conformance(
        runtime,
        _rc_probe(runtime),
        _rc_receipt(runtime),
        build_digest=content_digest("nautilus-v2-rc6-build"),
        tested_at=BASE,
    )


AUTH_TOKEN = "postgres-rpc-integration-token-0123456789abcdef"


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
async def test_search_dispatch_rpc_persists_and_replays_against_postgres(
    tmp_path: Path,
    pg_container,
    test_database_url: str | None,
) -> None:
    raw_url = test_database_url or pg_container.get_connection_url()
    engine = create_async_engine(_async_postgres_url(raw_url), pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex
    search_schema = PostgresSearchStateSchema(
        search_table=f"slv2_search_{suffix}",
        candidate_table=f"slv2_candidates_{suffix}",
    )
    worker_schema = PostgresWorkerStateSchema(
        profile_table=f"slv2_worker_profiles_{suffix}",
        reservation_table=f"slv2_worker_reservations_{suffix}",
        lease_table=f"slv2_leases_{suffix}",
        observation_table=f"slv2_lease_observations_{suffix}",
    )
    event_schema = PostgresExecutionEventSchema(
        event_table=f"slv2_events_{suffix}",
        cursor_table=f"slv2_event_cursors_{suffix}",
        audit_table=f"slv2_audit_{suffix}",
        outbox_table=f"slv2_outbox_{suffix}",
    )
    dispatch_schema = PostgresSearchDispatchSchema(
        admission_table=f"slv2_admissions_{suffix}",
        dispatch_table=f"slv2_dispatches_{suffix}",
        payload_table=f"slv2_payloads_{suffix}",
        outbox_table=event_schema.outbox_table,
    )
    aggregate_schema = PostgresStorageSchema(
        aggregate_table=f"slv2_aggregates_{suffix}",
        receipt_table=f"slv2_storage_receipts_{suffix}",
    )
    schemas = (search_schema, worker_schema, event_schema, dispatch_schema, aggregate_schema)
    created_tables = tuple(
        dict.fromkeys(
            (
                search_schema.search_table,
                search_schema.candidate_table,
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
                aggregate_schema.aggregate_table,
                aggregate_schema.receipt_table,
            )
        )
    )

    try:
        async with engine.begin() as connection:
            for schema in schemas:
                for statement in schema.statements:
                    await connection.execute(text(statement))

        search_state = PostgresSearchStateAdapter(session_factory, schema=search_schema)
        worker_state = PostgresWorkerStateAdapter(session_factory, schema=worker_schema)
        from app.strategy_lab_v2.postgres_search_dispatch import PostgresSearchDispatchAdapter

        dispatch_store = PostgresSearchDispatchAdapter(
            session_factory,
            schema=dispatch_schema,
            search_state=search_state,
            worker_state=worker_state,
        )
        aggregate_store = PostgresAggregateStore(session_factory, schema=aggregate_schema)
        persistence = replace(
            PostgresStrategyLabV2Persistence.build(session_factory),
            aggregate_store=aggregate_store,
            resources=PostgresResourceReader(aggregate_store),
            search_state=search_state,
            search_dispatch=dispatch_store,
            worker_state=worker_state,
        )

        (
            graph,
            artifact_store,
            _package_resolver,
            _materializer,
            context,
            _preparation_worker_state,
        ) = _setup(tmp_path / "trial")
        conformance_resolution = _conformance_resolution()
        context = NautilusTrialPreparationContext.from_authoritative_backtest_conformance(
            conformance_resolution=conformance_resolution,
            product_classes=frozenset({ProductClass.EQUITY}),
            execution_models=frozenset({"bar-close-v1"}),
            account_models=frozenset({"cash-equity-v1"}),
            market_context=context.market_context,
            runtime_profile=context.runtime_profile,
            admission_ledger=context.admission_ledger,
            image_name=context.image_name,
            output_path=context.output_path,
            now=context.now,
            lease_duration=context.lease_duration,
        )
        resource_adapter = PostgresStrategyLabV2Adapter(
            session_factory,
            persistence=persistence,
            clock=lambda: BASE + timedelta(days=1),
        )
        owner = "rpc-integration-owner"
        await _persist_trial_domain_graph(
            resource_adapter,
            principal=owner,
            suffix=suffix,
            graph=graph,
        )
        await search_state.initialize(
            principal=owner,
            state=new_search_execution_state(
                graph.experiment.fingerprint,
                (graph.trial.trial_id,),
                now=BASE,
            ),
        )
        await worker_state.ensure_profile(
            WorkerProfile(
                "rpc-integration-worker",
                WorkerKind.BACKTEST,
                context.runtime_profile.fingerprint,
            )
        )

        durable_domain_contracts = (
            (
                ApiResourceType.METRIC_SET,
                MetricSet(
                    metric_set_id=f"metrics-{suffix}",
                    trial_id=graph.trial.trial_id,
                    attempt_id=graph.attempt.attempt_id,
                    definition_version="strategy-lab.metrics.v1",
                    values=(
                        MetricValue(
                            name="cumulative_net_return",
                            value=Decimal("0.05"),
                            unit="fraction",
                            definition_version="strategy-lab.metrics.v1",
                            basis=MetricBasis.NET,
                            sample_size=1,
                            calculation_basis="native_equity_trace",
                        ),
                    ),
                    created_at=BASE,
                ),
            ),
            (
                ApiResourceType.FORWARD_INSTANCE,
                ForwardInstance(
                    instance_id=f"forward-{suffix}",
                    portfolio_fingerprint=graph.portfolio.fingerprint,
                    warmup_snapshot_fingerprint=graph.snapshot.fingerprint,
                    carry_in_mode=CarryInMode.FLAT,
                    state=ForwardState.CREATED,
                    last_event_id=None,
                    last_event_sequence=0,
                    correction_count=0,
                    created_at=BASE,
                    updated_at=BASE,
                ),
            ),
        )
        for resource_type, contract in durable_domain_contracts:
            attributes = dict(freeze_json(contract))
            mutation = ResourceMutationRequest(
                resource_type,
                f"persist-{suffix}-{resource_type.value}",
                {"attributes": attributes},
                BASE,
            )
            created = await resource_adapter.create_resource(
                principal=owner,
                request_id=f"create-{suffix}-{resource_type.value}",
                request=mutation,
            )
            assert created.receipt is not None, created.resolution.rejection_reason
            assert created.resolution.decision.value == "accept"
            domain_fingerprint = created.receipt.resource.meta["domain_fingerprint"]
            restored = rehydrate_resource_contract(
                resource_type,
                created.receipt.resource.attributes,
                expected_domain_fingerprint=domain_fingerprint,
            )
            assert restored == contract

            replay = await resource_adapter.create_resource(
                principal=owner,
                request_id=f"replay-{suffix}-{resource_type.value}",
                request=mutation,
            )
            assert replay.receipt == created.receipt
            assert replay.resolution.decision.value == "replay_existing"
            assert (
                await resource_adapter.get_resource(
                    principal="foreign-owner",
                    resource_type=resource_type,
                    resource_id=created.receipt.resource.id,
                )
                is None
            )

        hydrated_graphs = []

        def resolve_context(_request, hydrated_graph):
            hydrated_graphs.append(hydrated_graph)
            return context

        assert context.execution_scope is NautilusExecutionScope.BACKTEST_AUTHORITATIVE
        assert context.requested_authoritative
        preparation = create_search_preparation_evidence_resolver(
            persistence,
            artifact_store.root,
            host_bindings=SearchPreparationHostBindings(
                runtime_abi=RUNTIME_ABI,
                series_decoder=JsonFrozenSeriesDecoder(),
                context_resolver=resolve_context,
            ),
            conformance_resolution=conformance_resolution,
        )
        preparation_calls = 0

        async def evidence_resolver(**kwargs):
            nonlocal preparation_calls
            preparation_calls += 1
            return await preparation(**kwargs)

        adapter = PostgresStrategyLabV2Adapter(
            session_factory,
            persistence=persistence,
            search_dispatch_evidence=evidence_resolver,
            clock=lambda: BASE + timedelta(days=1),
        )
        with pytest.raises(TrialDomainHydrationError, match="attempt is missing"):
            await preparation(
                principal="foreign-owner",
                request_id="foreign-owner-request",
                experiment_fingerprint=graph.experiment.fingerprint,
                candidate_index=0,
                attempt_id=graph.attempt.attempt_id,
                dispatch_intent=SearchDispatchIntent(
                    "foreign-owner-idempotency-key",
                    graph.attempt.attempt_id,
                    "strategy-backtest",
                    context.now,
                ),
            )
        assert hydrated_graphs == []

        socket_path = tmp_path / "search-preparation.sock"
        app = create_search_preparation_app(
            adapter,
            auth_token=AUTH_TOKEN,
            socket_path=socket_path,
        )
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(socket_path))
        listener.listen(8)
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                log_level="critical",
                access_log=False,
                proxy_headers=False,
                ws="none",
            )
        )
        server_task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            for _ in range(500):
                if server.started:
                    break
                await asyncio.sleep(0.01)
            else:
                raise AssertionError("PostgreSQL-backed preparation RPC did not start")

            client = UnixSocketSearchDispatchClient(socket_path, AUTH_TOKEN)
            intent = SearchDispatchIntent(
                "postgres-rpc-integration-key",
                graph.attempt.attempt_id,
                "strategy-backtest",
                context.now,
            )
            command = {
                "principal": owner,
                "request_id": "postgres-rpc-integration-request",
                "experiment_fingerprint": graph.experiment.fingerprint,
                "candidate_index": 0,
                "attempt_id": graph.attempt.attempt_id,
                "dispatch_intent": intent,
            }
            first = await client(**command)
            replay = await client(**command)
        finally:
            server.should_exit = True
            await asyncio.wait_for(server_task, timeout=5)
            listener.close()

        assert first.decision.value == "enqueue"
        assert replay.decision.value == "replay_existing"
        assert first.envelope is not None
        assert replay.envelope == first.envelope
        assert replay.search_state == first.search_state
        assert replay.admission_ledger == first.admission_ledger
        assert replay.pool == first.pool
        assert preparation_calls == 1
        assert hydrated_graphs == [graph]
        assert (
            await search_state.load(
                principal=owner,
                experiment_fingerprint=graph.experiment.fingerprint,
            )
        ).candidates[0].attempt_id == graph.attempt.attempt_id

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
        async with engine.begin() as connection:
            for table in reversed(created_tables):
                await connection.execute(text(f"DROP TABLE IF EXISTS {table}"))
        await engine.dispose()
