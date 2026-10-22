from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from sqlalchemy import Table, delete, inspect, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401 - register the real mapped metadata and FK targets
from app.database import Base
from app.models.research import CodeAsset, CodeVersion, ResearchArtifact, ResearchRun
from app.models.user import User
from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.api_router import create_strategy_lab_router
from app.strategy_lab_v2.application import PostgresStrategyLabV2Adapter
from app.strategy_lab_v2.canonical import content_digest, freeze_json
from app.strategy_lab_v2.contracts import (
    ExperimentDefinition,
    PortfolioComposition,
    RunAttempt,
    ScientificTrial,
    SelectedStudyArtifactReference,
    StrategyPackage,
    StrategyVersion,
)
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.postgres_resources import PostgresResourceReader
from app.strategy_lab_v2.postgres_storage import PostgresAggregateStore, PostgresStorageSchema
from app.strategy_lab_v2.provider_capability_host import CAPABILITY_SCOPE_CONFIG_ENV
from app.strategy_lab_v2.provider_preflight import ProviderLocalCapabilityEvidenceReader
from app.strategy_lab_v2.resource_mutations import ResourceMutationRequest
from app.strategy_lab_v2.search_dispatch_rpc import (
    STRATEGY_LAB_V2_ARTIFACT_ROOT_ENV,
    WALK_FORWARD_CALENDAR_FACTORY_ENV,
    UnixSocketSearchDispatchClient,
    build_api_bindings,
)
from app.strategy_lab_v2.storage import AggregateKey
from app.strategy_lab_v2.study_artifact_resolver import (
    SelectedStudyArtifactResolutionError,
    create_resolved_study_artifact_output_resolver,
    create_selected_study_artifact_resolver,
)
from app.strategy_lab_v2.tests.test_search_dispatch_preparation import _setup
from app.strategy_lab_v2.trial_hydration import (
    NautilusTrialDomainHydrator,
    TrialDomainHydrationError,
)

_NOW = datetime(2026, 10, 22, 4, 0, tzinfo=UTC)
_STUDY_TABLES: tuple[Table, ...] = (cast(Table, ResearchArtifact.__table__),)
_EXPECTED_STUDY_FK_CLOSURE = {
    "code_asset",
    "code_version",
    "research_artifact",
    "research_run",
    "user",
}


@dataclass(frozen=True, slots=True)
class StudyDatabase:
    sessions: async_sessionmaker[AsyncSession]
    storage_schema: PostgresStorageSchema
    database_url: str
    schema_name: str

    def new_engine_and_sessions(
        self,
    ) -> tuple[Any, async_sessionmaker[AsyncSession]]:
        engine = create_async_engine(
            _async_postgres_url(self.database_url),
            pool_pre_ping=True,
            connect_args={"server_settings": {"search_path": self.schema_name}},
        )
        return engine, async_sessionmaker(engine, expire_on_commit=False)


def _mapped_study_fk_closure() -> tuple[Table, ...]:
    tables_by_key: dict[str, Table] = {}
    pending = list(_STUDY_TABLES)
    while pending:
        table = pending.pop()
        if table.key in tables_by_key:
            continue
        tables_by_key[table.key] = table
        pending.extend(cast(Table, foreign_key.column.table) for foreign_key in table.foreign_keys)
    return tuple(tables_by_key.values())


def test_study_fixture_is_the_actual_mapped_foreign_key_closure() -> None:
    closure = _mapped_study_fk_closure()
    assert {table.name for table in closure} == _EXPECTED_STUDY_FK_CLOSURE


def _async_postgres_url(raw_url: str) -> str:
    if raw_url.startswith("postgresql+asyncpg://"):
        return raw_url
    if raw_url.startswith("postgresql+psycopg2://"):
        return raw_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    raise ValueError("integration database URL must use PostgreSQL")


@pytest_asyncio.fixture
async def study_database(
    request: pytest.FixtureRequest,
) -> AsyncIterator[StudyDatabase]:
    """Use an explicit bounded URL or lazily fall back to normal integration PG."""

    database_url = os.getenv("STRATEGY_STUDY_DATABASE_URL")
    if not database_url:
        database_url = request.getfixturevalue("test_database_url")
    if not database_url:
        pg_container = request.getfixturevalue("pg_container")
        database_url = pg_container.get_connection_url()
    if not database_url:
        raise RuntimeError("Study integration requires the assigned PostgreSQL URL")

    schema_name = f"strategy_study_{uuid.uuid4().hex[:12]}"
    engine = create_async_engine(
        _async_postgres_url(database_url),
        pool_pre_ping=True,
        connect_args={"server_settings": {"search_path": schema_name}},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex
    storage_schema = PostgresStorageSchema(
        aggregate_table=f"slv2_study_aggregates_{suffix}",
        receipt_table=f"slv2_study_receipts_{suffix}",
    )
    schema_created = False
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
            schema_created = True
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection.execution_options(schema_translate_map={None: schema_name}),
                    tables=_mapped_study_fk_closure(),
                )
            )
            for statement in storage_schema.statements:
                await connection.execute(text(statement))
            actual = await connection.run_sync(
                lambda sync_connection: set(
                    inspect(sync_connection).get_table_names(schema=schema_name)
                )
            )
            assert actual == _EXPECTED_STUDY_FK_CLOSURE | {
                storage_schema.aggregate_table,
                storage_schema.receipt_table,
            }
        async with sessions.begin() as session:
            session.add_all(
                (
                    User(
                        id=1,
                        username=f"study-owner-{suffix}",
                        email=f"study-owner-{suffix}@example.invalid",
                        hashed_password="test-only-not-a-credential",
                    ),
                    User(
                        id=2,
                        username=f"other-owner-{suffix}",
                        email=f"other-owner-{suffix}@example.invalid",
                        hashed_password="test-only-not-a-credential",
                    ),
                )
            )
            # CodeAsset has a database FK to User but no ORM relationship, so
            # make the owner rows durable before queuing FK-dependent records.
            await session.flush()
            session.add(
                CodeAsset(
                    id=10,
                    user_id=1,
                    stable_key=f"study-{suffix}",
                    name="Pinned Study",
                    kind="study",
                )
            )
            session.add(
                CodeVersion(
                    id=20,
                    code_asset_id=10,
                    version_number=1,
                    source="study source fixture",
                    output_contract="study",
                    output_name="signal",
                    parameter_schema={},
                    default_parameters={},
                    sdk_version="study-sdk.test",
                    runtime_version="python.test",
                    dependencies=[],
                    diagnostics=[],
                )
            )
            session.add(
                CodeVersion(
                    id=21,
                    code_asset_id=10,
                    version_number=2,
                    source="second study version fixture",
                    output_contract="study",
                    output_name="signal",
                    parameter_schema={},
                    default_parameters={},
                    sdk_version="study-sdk.test",
                    runtime_version="python.test",
                    dependencies=[],
                    diagnostics=[],
                )
            )
            session.add(
                ResearchRun(
                    id=30,
                    user_id=1,
                    code_version_id=20,
                    status="completed",
                    run_config={"output_contract": "study"},
                    dataset_manifest={"dataset": "fixture-v1", "content": "a" * 64},
                    reproducibility_hash="b" * 64,
                    resource_usage={"evaluation": {"status": "completed"}},
                )
            )
            session.add(
                ResearchArtifact(
                    id=40,
                    research_run_id=30,
                    artifact_type="series",
                    name="signal",
                    payload={"type": "series", "value": [1.0, 2.0]},
                )
            )
        yield StudyDatabase(sessions, storage_schema, database_url, schema_name)
    finally:
        try:
            if schema_created:
                async with engine.begin() as connection:
                    await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        finally:
            await engine.dispose()


async def _reference(
    sessions: async_sessionmaker[AsyncSession],
) -> SelectedStudyArtifactReference:
    async with sessions() as session:
        asset = await session.get(CodeAsset, 10)
        version = await session.get(CodeVersion, 20)
        run = await session.get(ResearchRun, 30)
        artifact = await session.get(ResearchArtifact, 40)
        assert (
            asset is not None and version is not None and run is not None and artifact is not None
        )
        assert isinstance(run.reproducibility_hash, str)
        expected_code_version_digest = content_digest(
            {
                "code_asset": {
                    "id": asset.id,
                    "user_id": asset.user_id,
                    "stable_key": asset.stable_key,
                    "name": asset.name,
                    "kind": asset.kind,
                },
                "code_version": {
                    "id": version.id,
                    "code_asset_id": version.code_asset_id,
                    "version_number": version.version_number,
                    "source": version.source,
                    "output_contract": version.output_contract,
                    "output_name": version.output_name,
                    "parameter_schema": version.parameter_schema,
                    "default_parameters": version.default_parameters,
                    "sdk_version": version.sdk_version,
                    "runtime_version": version.runtime_version,
                    "dependencies": version.dependencies,
                    "lookback": version.lookback,
                    "diagnostics": version.diagnostics,
                },
            }
        )
        return SelectedStudyArtifactReference(
            research_run_id=run.id,
            code_version_id=version.id,
            artifact_id=artifact.id,
            artifact_name=artifact.name,
            artifact_type=artifact.artifact_type,
            output_contract="study",
            run_reproducibility_hash=run.reproducibility_hash,
            code_version_digest=expected_code_version_digest,
            dataset_manifest_digest=content_digest(run.dataset_manifest),
            artifact_content_digest=content_digest(artifact.payload),
        )


def _adapter(
    sessions: async_sessionmaker[AsyncSession],
    storage_schema: PostgresStorageSchema,
    *,
    host_bindings_factory: Any | None = None,
) -> tuple[PostgresStrategyLabV2Adapter, PostgresAggregateStore]:
    store = PostgresAggregateStore(sessions, schema=storage_schema)
    persistence = replace(
        PostgresStrategyLabV2Persistence.build(sessions),
        aggregate_store=store,
        resources=PostgresResourceReader(store),
    )
    adapter_kwargs: dict[str, Any] = {"persistence": persistence}
    if host_bindings_factory is None:
        adapter_kwargs["selected_study_artifact_resolver"] = (
            create_selected_study_artifact_resolver(sessions)
        )
    else:
        adapter_kwargs["host_bindings_factory"] = host_bindings_factory
    adapter = PostgresStrategyLabV2Adapter(sessions, clock=lambda: _NOW, **adapter_kwargs)
    return adapter, store


@pytest.mark.integration
@pytest.mark.asyncio
async def test_strategy_api_authenticates_exact_study_reference_before_persistence(
    study_database: StudyDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions = study_database.sessions
    reference = await _reference(sessions)
    for variable in (
        CAPABILITY_SCOPE_CONFIG_ENV,
        "STRATEGY_LAB_V2_NAUTILUS_RC_EVIDENCE_DIRECTORY",
        "STRATEGY_LAB_V2_NAUTILUS_RC_EVIDENCE_ARTIFACT_SHA256",
        "STRATEGY_LAB_V2_NAUTILUS_RC_SOURCE_SHA256",
        "STRATEGY_LAB_V2_NAUTILUS_RC_IMAGE_SHA256",
        STRATEGY_LAB_V2_ARTIFACT_ROOT_ENV,
        WALK_FORWARD_CALENDAR_FACTORY_ENV,
        "STRATEGY_LAB_V2_FORWARD_RUNTIME_PROFILE_FINGERPRINT",
    ):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("STRATEGY_LAB_V2_PREPARATION_SOCKET_PATH", "/run/strategy/preparation.sock")
    monkeypatch.setenv("STRATEGY_LAB_V2_PREPARATION_AUTH_TOKEN", "offline-test-token-" + "x" * 32)
    calls = {"dispatch": 0, "provider": 0, "http_transport": 0}

    async def forbidden_dispatch(self: Any, **_kwargs: Any) -> Any:
        calls["dispatch"] += 1
        raise AssertionError("Study API admission must not dispatch a strategy")

    async def forbidden_provider(self: Any, **_kwargs: Any) -> Any:
        calls["provider"] += 1
        raise AssertionError("Study API admission must not acquire provider data")

    def forbidden_http_transport(*_args: Any, **_kwargs: Any) -> Any:
        calls["http_transport"] += 1
        raise AssertionError("Study API admission must not open a non-ASGI HTTP transport")

    monkeypatch.setattr(UnixSocketSearchDispatchClient, "__call__", forbidden_dispatch)
    monkeypatch.setattr(ProviderLocalCapabilityEvidenceReader, "__call__", forbidden_provider)
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", forbidden_http_transport)
    composed_bindings = []

    def production_host_bindings(
        session_factory: Any, host_persistence: PostgresStrategyLabV2Persistence
    ) -> Any:
        bindings = build_api_bindings(session_factory, host_persistence)
        composed_bindings.append(bindings)
        return bindings

    adapter, store = _adapter(
        sessions,
        study_database.storage_schema,
        host_bindings_factory=production_host_bindings,
    )
    assert len(composed_bindings) == 1
    assert composed_bindings[0].selected_study_artifact_resolver is not None
    assert composed_bindings[0].capability_preflight is None
    app = FastAPI()

    async def adapter_dependency() -> PostgresStrategyLabV2Adapter:
        return adapter

    async def principal_dependency(request: Request) -> str:
        return request.headers.get("X-Test-Owner", "1")

    app.include_router(
        create_strategy_lab_router(
            adapter_dependency=adapter_dependency,
            principal_dependency=principal_dependency,
            request_id_factory=lambda: "study-api-request",
            clock=lambda: _NOW,
        ),
        prefix="/api/v1",
    )
    body = {
        "attributes": {
            "resource_id": "strategy-with-study-input",
            "strategy_id": "study-consumer",
            "version_id": "v1",
            "sdk_version": "strategy-sdk.v2",
            "source_digest": content_digest("strategy-source"),
            "selected_study_artifact": dict(freeze_json(reference)),
        }
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://strategy-lab.test"
    ) as client:
        accepted = await client.post(
            "/api/v1/strategy-lab/v2/strategies",
            headers={"Idempotency-Key": "study-valid", "X-Test-Owner": "1"},
            json=body,
        )
        assert accepted.status_code == 202, accepted.text
        assert accepted.json()["meta"]["decision"] == "accept"
        accepted_fingerprint = accepted.json()["data"]["meta"]["revision_digest"]
        readback = await client.get(
            "/api/v1/strategy-lab/v2/strategies/strategy-with-study-input",
            headers={"X-Test-Owner": "1"},
        )
        assert readback.status_code == 200, readback.text
        assert readback.json()["data"]["attributes"]["selected_study_artifact"] == freeze_json(
            reference
        )
        assert readback.json()["data"]["meta"]["revision_digest"] == accepted_fingerprint
        stored = await adapter.get_resource(
            principal="1",
            resource_type=ApiResourceType.STRATEGY,
            resource_id="strategy-with-study-input",
        )
        assert stored is not None
        assert stored.attributes["selected_study_artifact"] == freeze_json(reference)
        assert stored.identity.revision_digest is not None
        aggregate = await store.get(
            AggregateKey(ApiResourceType.STRATEGY.value, "strategy-with-study-input")
        )
        assert aggregate is not None
        assert stored.identity.revision_digest == aggregate.state_fingerprint

        foreign = await client.post(
            "/api/v1/strategy-lab/v2/strategies",
            headers={"Idempotency-Key": "study-foreign", "X-Test-Owner": "2"},
            json=body | {"attributes": body["attributes"] | {"resource_id": "foreign-study"}},
        )
        assert foreign.status_code == 422

        changed_reference = dict(
            freeze_json(
                replace(
                    reference,
                    artifact_content_digest=content_digest({"type": "series", "value": [88.0]}),
                )
            )
        )
        drift = await client.post(
            "/api/v1/strategy-lab/v2/strategies",
            headers={"Idempotency-Key": "study-drift", "X-Test-Owner": "1"},
            json=body
            | {
                "attributes": body["attributes"]
                | {
                    "resource_id": "drifted-study",
                    "selected_study_artifact": changed_reference,
                }
            },
        )
        assert drift.status_code == 422

        async with sessions.begin() as session:
            await session.execute(
                update(ResearchArtifact)
                .where(ResearchArtifact.id == 40)
                .values(payload={"type": "series", "value": [77.0]})
            )
        after_revocation = await client.post(
            "/api/v1/strategy-lab/v2/strategies",
            headers={"Idempotency-Key": "study-after-revocation", "X-Test-Owner": "1"},
            json=body
            | {"attributes": body["attributes"] | {"resource_id": "study-after-revocation"}},
        )
        assert after_revocation.status_code == 422
        original_after_revocation = await client.get(
            "/api/v1/strategy-lab/v2/strategies/strategy-with-study-input",
            headers={"X-Test-Owner": "1"},
        )
        assert original_after_revocation.status_code == 200
        assert original_after_revocation.json()["data"]["attributes"][
            "selected_study_artifact"
        ] == freeze_json(reference)
        assert (
            original_after_revocation.json()["data"]["meta"]["revision_digest"]
            == accepted_fingerprint
        )

    assert (
        await adapter.get_resource(
            principal="2", resource_type=ApiResourceType.STRATEGY, resource_id="foreign-study"
        )
        is None
    )
    assert (
        await adapter.get_resource(
            principal="1",
            resource_type=ApiResourceType.STRATEGY,
            resource_id="study-after-revocation",
        )
        is None
    )
    original_pin = await adapter.get_resource(
        principal="1",
        resource_type=ApiResourceType.STRATEGY,
        resource_id="strategy-with-study-input",
    )
    assert original_pin is not None
    assert original_pin.attributes["selected_study_artifact"] == freeze_json(reference)
    assert calls == {"dispatch": 0, "provider": 0, "http_transport": 0}
    assert (
        await adapter.get_resource(
            principal="1", resource_type=ApiResourceType.STRATEGY, resource_id="drifted-study"
        )
        is None
    )


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "drift",
    (
        "failed_run",
        "failed_evaluation",
        "running_run",
        "queued_run",
        "malformed_run_hash",
        "changed_code_version",
        "wrong_code_asset_owner",
        "changed_code_source",
        "wrong_study_contract",
        "wrong_run_contract",
        "changed_dataset_manifest",
        "changed_artifact_payload",
        "unsupported_artifact_type",
        "malformed_artifact_payload",
        "missing_artifact",
        "duplicate_artifact_name",
    ),
)
async def test_study_resolver_rejects_persisted_run_version_and_output_drift(
    drift: str,
    study_database: StudyDatabase,
) -> None:
    sessions = study_database.sessions
    reference = await _reference(sessions)
    async with sessions.begin() as session:
        if drift == "failed_run":
            await session.execute(
                update(ResearchRun).where(ResearchRun.id == 30).values(status="failed")
            )
        elif drift == "running_run":
            await session.execute(
                update(ResearchRun).where(ResearchRun.id == 30).values(status="running")
            )
        elif drift == "queued_run":
            await session.execute(
                update(ResearchRun).where(ResearchRun.id == 30).values(status="queued")
            )
        elif drift == "failed_evaluation":
            await session.execute(
                update(ResearchRun)
                .where(ResearchRun.id == 30)
                .values(resource_usage={"evaluation": {"status": "failed"}})
            )
        elif drift == "malformed_run_hash":
            await session.execute(
                update(ResearchRun).where(ResearchRun.id == 30).values(reproducibility_hash="bad")
            )
        elif drift == "changed_code_version":
            await session.execute(
                update(ResearchRun).where(ResearchRun.id == 30).values(code_version_id=21)
            )
        elif drift == "wrong_code_asset_owner":
            await session.execute(update(CodeAsset).where(CodeAsset.id == 10).values(user_id=2))
        elif drift == "changed_code_source":
            await session.execute(
                update(CodeVersion).where(CodeVersion.id == 20).values(source="changed source")
            )
        elif drift == "wrong_study_contract":
            await session.execute(
                update(CodeVersion).where(CodeVersion.id == 20).values(output_contract="plot")
            )
        elif drift == "wrong_run_contract":
            await session.execute(
                update(ResearchRun)
                .where(ResearchRun.id == 30)
                .values(run_config={"output_contract": "plot"})
            )
        elif drift == "changed_dataset_manifest":
            await session.execute(
                update(ResearchRun)
                .where(ResearchRun.id == 30)
                .values(dataset_manifest={"dataset": "changed", "content": "d" * 64})
            )
        elif drift == "changed_artifact_payload":
            await session.execute(
                update(ResearchArtifact)
                .where(ResearchArtifact.id == 40)
                .values(payload={"type": "series", "value": [9.0]})
            )
        elif drift == "unsupported_artifact_type":
            await session.execute(
                update(ResearchArtifact)
                .where(ResearchArtifact.id == 40)
                .values(artifact_type="unregistered-output")
            )
        elif drift == "malformed_artifact_payload":
            await session.execute(
                update(ResearchArtifact)
                .where(ResearchArtifact.id == 40)
                .values(payload={"type": "series"})
            )
        elif drift == "missing_artifact":
            await session.execute(delete(ResearchArtifact).where(ResearchArtifact.id == 40))
        else:
            session.add(
                ResearchArtifact(
                    id=41,
                    research_run_id=30,
                    artifact_type="series",
                    name="signal",
                    payload={"type": "series", "value": [3.0]},
                )
            )

    resolver = create_selected_study_artifact_resolver(sessions)
    with pytest.raises(SelectedStudyArtifactResolutionError):
        await resolver(principal="1", reference=reference)


def _strategy_graph_with_reference(graph: Any, reference: SelectedStudyArtifactReference) -> Any:
    old_strategy: StrategyVersion = graph.strategies[0]
    strategy = replace(old_strategy, selected_study_artifact=reference)
    old_package: StrategyPackage = graph.packages[old_strategy.fingerprint]
    package = replace(old_package, strategy_fingerprint=strategy.fingerprint)
    portfolio: PortfolioComposition = replace(
        graph.portfolio,
        components=tuple(
            replace(component, strategy_fingerprint=strategy.fingerprint)
            for component in graph.portfolio.components
        ),
    )
    experiment: ExperimentDefinition = replace(
        graph.experiment,
        portfolio_fingerprint=portfolio.fingerprint,
        strategy_fingerprints=(strategy.fingerprint,),
        strategy_package_fingerprints={strategy.fingerprint: package.fingerprint},
    )
    old_trial: ScientificTrial = graph.trial
    trial = ScientificTrial.create(
        experiment_fingerprint=experiment.fingerprint,
        snapshot_fingerprint=old_trial.snapshot_fingerprint,
        preflight_report=old_trial.preflight_report,
        parameter_set=old_trial.parameter_set,
        scenario=old_trial.scenario,
        seed=old_trial.seed,
        randomization=old_trial.randomization,
        evaluation_window=old_trial.evaluation_window,
    )
    attempt: RunAttempt = replace(graph.attempt, trial_id=trial.trial_id)
    from app.strategy_lab_v2.trial_hydration import HydratedNautilusTrial

    return HydratedNautilusTrial(
        attempt=attempt,
        trial=trial,
        experiment=experiment,
        portfolio=portfolio,
        snapshot=graph.snapshot,
        strategies=(strategy,),
        packages={strategy.fingerprint: package},
    )


async def _persist_graph(adapter: PostgresStrategyLabV2Adapter, graph: Any, suffix: str) -> None:
    values = (
        (ApiResourceType.STRATEGY, graph.strategies[0]),
        (ApiResourceType.PACKAGE, next(iter(graph.packages.values()))),
        (ApiResourceType.PORTFOLIO, graph.portfolio),
        (ApiResourceType.SNAPSHOT, graph.snapshot),
        (ApiResourceType.EXPERIMENT, graph.experiment),
        (ApiResourceType.TRIAL, graph.trial),
        (ApiResourceType.ATTEMPT, graph.attempt),
    )
    for resource_type, contract in values:
        attributes = dict(freeze_json(contract))
        if resource_type is ApiResourceType.ATTEMPT:
            attributes["resource_id"] = graph.attempt.attempt_id
        result = await adapter.create_resource(
            principal="1",
            request_id=f"study-graph-{suffix}-{resource_type.value}",
            request=ResourceMutationRequest(
                resource_type,
                f"study-graph-{suffix}-{resource_type.value}",
                {"attributes": attributes},
                _NOW,
            ),
        )
        assert result.receipt is not None, result.resolution.rejection_reason


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "post_dispatch_drift",
    (
        "changed_dataset",
        "failed_run",
        "failed_evaluation",
        "changed_run_hash",
        "changed_code_version",
        "changed_asset_owner",
        "changed_code_source",
        "changed_artifact_payload",
        "changed_artifact_identity",
        "changed_artifact_type",
        "ambiguous_artifact_name",
        "deleted_artifact",
    ),
)
async def test_reconstructed_worker_hydrator_rechecks_study_after_persisted_drift(
    tmp_path: Path,
    study_database: StudyDatabase,
    post_dispatch_drift: str,
) -> None:
    sessions = study_database.sessions
    storage_schema = study_database.storage_schema
    reference = await _reference(sessions)
    graph, _artifacts, _package_resolver, _materializer, _context, _worker_state = _setup(
        tmp_path / "study-worker"
    )
    graph = _strategy_graph_with_reference(graph, reference)
    adapter, store = _adapter(sessions, storage_schema)
    await _persist_graph(adapter, graph, uuid.uuid4().hex)

    # Rebuild both host adapters to model a worker restart, then verify from
    # persisted owner-scoped aggregates and the actual Study ORM rows.
    fresh_engine, fresh_sessions = study_database.new_engine_and_sessions()
    try:
        _restarted_adapter, restarted_store = _adapter(fresh_sessions, storage_schema)
        assert restarted_store.schema == store.schema
        hydrator = NautilusTrialDomainHydrator(
            PostgresResourceReader(restarted_store),
            selected_study_artifact_resolver=create_resolved_study_artifact_output_resolver(
                fresh_sessions
            ),
        )
        hydrated = await hydrator.hydrate_attempt(
            principal="1", attempt_resource_id=graph.attempt.attempt_id
        )
        assert hydrated.strategies[0].selected_study_artifact == reference
        assert hydrated.study_artifacts is not None
        assert hydrated.study_artifacts[hydrated.strategies[0].fingerprint].value == (1.0, 2.0)

        async with fresh_sessions.begin() as session:
            if post_dispatch_drift == "changed_dataset":
                await session.execute(
                    update(ResearchRun)
                    .where(ResearchRun.id == 30)
                    .values(
                        dataset_manifest={
                            "dataset": "changed-after-dispatch",
                            "content": "d" * 64,
                        }
                    )
                )
            elif post_dispatch_drift == "failed_run":
                await session.execute(
                    update(ResearchRun).where(ResearchRun.id == 30).values(status="failed")
                )
            elif post_dispatch_drift == "failed_evaluation":
                await session.execute(
                    update(ResearchRun)
                    .where(ResearchRun.id == 30)
                    .values(resource_usage={"evaluation": {"status": "failed"}})
                )
            elif post_dispatch_drift == "changed_run_hash":
                await session.execute(
                    update(ResearchRun)
                    .where(ResearchRun.id == 30)
                    .values(reproducibility_hash="c" * 64)
                )
            elif post_dispatch_drift == "changed_code_version":
                await session.execute(
                    update(ResearchRun).where(ResearchRun.id == 30).values(code_version_id=21)
                )
            elif post_dispatch_drift == "changed_asset_owner":
                await session.execute(update(CodeAsset).where(CodeAsset.id == 10).values(user_id=2))
            elif post_dispatch_drift == "changed_code_source":
                await session.execute(
                    update(CodeVersion)
                    .where(CodeVersion.id == 20)
                    .values(source="changed-after-dispatch")
                )
            elif post_dispatch_drift == "changed_artifact_payload":
                await session.execute(
                    update(ResearchArtifact)
                    .where(ResearchArtifact.id == 40)
                    .values(payload={"type": "series", "value": [99.0]})
                )
            elif post_dispatch_drift == "changed_artifact_identity":
                await session.execute(
                    update(ResearchArtifact)
                    .where(ResearchArtifact.id == 40)
                    .values(name="renamed-after-dispatch")
                )
            elif post_dispatch_drift == "changed_artifact_type":
                await session.execute(
                    update(ResearchArtifact)
                    .where(ResearchArtifact.id == 40)
                    .values(artifact_type="table")
                )
            elif post_dispatch_drift == "ambiguous_artifact_name":
                session.add(
                    ResearchArtifact(
                        id=41,
                        research_run_id=30,
                        artifact_type="series",
                        name="signal",
                        payload={"type": "series", "value": [3.0]},
                    )
                )
            else:
                await session.execute(delete(ResearchArtifact).where(ResearchArtifact.id == 40))
        restarted_hydrator = NautilusTrialDomainHydrator(
            PostgresResourceReader(restarted_store),
            selected_study_artifact_resolver=create_resolved_study_artifact_output_resolver(
                fresh_sessions
            ),
        )
        with pytest.raises(TrialDomainHydrationError, match="unavailable for restart validation"):
            await restarted_hydrator.hydrate_attempt(
                principal="1", attempt_resource_id=graph.attempt.attempt_id
            )
        with pytest.raises(TrialDomainHydrationError, match="unavailable for restart validation"):
            await restarted_hydrator.hydrate_attempt(
                principal="1", attempt_resource_id=graph.attempt.attempt_id
            )
    finally:
        await fresh_engine.dispose()
