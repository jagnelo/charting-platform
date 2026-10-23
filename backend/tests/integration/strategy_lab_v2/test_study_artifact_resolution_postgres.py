from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, cast
from zipfile import ZIP_DEFLATED, ZipFile

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
from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.canonical import content_digest, freeze_json
from app.strategy_lab_v2.contracts import (
    ArtifactManifest,
    ArtifactRetention,
    CarryInMode,
    ExperimentDefinition,
    ForwardInstance,
    ForwardState,
    PortfolioComposition,
    ResolvedStudyArtifactOutput,
    RunAttempt,
    ScientificTrial,
    SelectedStudyArtifactReference,
    StrategyPackage,
    StrategyVersion,
)
from app.strategy_lab_v2.forward_account import ForwardAccountState
from app.strategy_lab_v2.forward_execution_plan import (
    ForwardComponentExecutionPlan,
    ForwardExecutionPlan,
)
from app.strategy_lab_v2.forward_warmup import ForwardWarmupReceipt
from app.strategy_lab_v2.forward_worker_composition import (
    create_authenticated_forward_worker_runtime_input_resolver,
)
from app.strategy_lab_v2.nautilus_runtime_bundle import load_materialized_nautilus_runtime_bundle
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.postgres_forward_account import (
    PostgresForwardAccountAdapter,
    PostgresForwardAccountSchema,
)
from app.strategy_lab_v2.postgres_forward_state import (
    PostgresForwardStateAdapter,
    PostgresForwardStateSchema,
)
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
from app.strategy_lab_v2.strategy_package_resolution import (
    STRATEGY_PACKAGE_LOCK_MEMBER,
    STRATEGY_PACKAGE_MANIFEST_MEMBER,
    STRATEGY_SOURCE_ARCHIVE_MEDIA_TYPE,
    STRATEGY_SOURCE_ARCHIVE_SCHEMA,
)
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
from strategy_runtime import (
    deserialize_component_invocation_context_stream,
    deserialize_strategy_manifest,
    serialize_strategy_manifest,
)

_NOW = datetime(2026, 10, 22, 4, 0, tzinfo=UTC)
_STUDY_TABLES: tuple[Table, ...] = (cast(Table, ResearchArtifact.__table__),)
_STUDY_OUTPUT_CASES = (
    ("scalar", 2.5),
    ("series", [{"time": "t1", "value": 2.5}, {"time": "t2", "value": 3.0}]),
    ("boolean", True),
    ("table", {"columns": ["time", "value"], "rows": [["t1", 4.0]]}),
    ("bar", {"time": "t1", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5}),
    ("histogram", {"bins": [{"lower": 0.0, "upper": 1.0, "count": 2}]}),
    ("range", {"low": 1.25, "high": 3.75}),
    ("scatter", {"points": [{"x": 1.0, "y": 2.0}]}),
    ("heatmap", {"x": ["x1"], "y": ["y1"], "values": [[2.0]]}),
    ("dashboard", {"panels": [{"name": "equity", "value": [1.0, 2.0]}]}),
    ("events", [{"event_id": "event-1", "timestamp": "2026-10-23T00:00:00Z"}]),
)
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


async def _strategy_graph_with_reference(
    graph: Any,
    reference: SelectedStudyArtifactReference,
    sessions: async_sessionmaker[AsyncSession],
    *,
    artifact_store: Any | None = None,
) -> Any:
    resolved_output = await create_resolved_study_artifact_output_resolver(sessions)(
        principal="1", reference=reference
    )
    old_strategy: StrategyVersion = graph.strategies[0]
    strategy = replace(old_strategy, selected_study_artifact=reference)
    old_package: StrategyPackage = graph.packages[old_strategy.fingerprint]
    package = replace(old_package, strategy_fingerprint=strategy.fingerprint)
    if artifact_store is not None:
        original_archive = artifact_store.read(old_package.archive_digest)
        with ZipFile(BytesIO(original_archive)) as archive:
            members = {name: archive.read(name) for name in archive.namelist()}
        sdk_manifest = deserialize_strategy_manifest(
            members[STRATEGY_PACKAGE_MANIFEST_MEMBER].decode("utf-8")
        )
        manifest_bytes = serialize_strategy_manifest(
            replace(sdk_manifest, strategy=strategy)
        ).encode("utf-8")
        members[STRATEGY_PACKAGE_MANIFEST_MEMBER] = manifest_bytes
        archive_stream = BytesIO()
        with ZipFile(archive_stream, mode="w", compression=ZIP_DEFLATED) as archive:
            for name, payload in members.items():
                archive.writestr(name, payload)
        archive_bytes = archive_stream.getvalue()
        package = replace(
            package,
            archive_digest=artifact_content_digest(archive_bytes),
            manifest_digest=artifact_content_digest(manifest_bytes),
            dependency_lock_digest=artifact_content_digest(members[STRATEGY_PACKAGE_LOCK_MEMBER]),
            archive_byte_length=len(archive_bytes),
        )
        artifact_store.publish(
            ArtifactManifest(
                package.archive_digest,
                len(archive_bytes),
                STRATEGY_SOURCE_ARCHIVE_MEDIA_TYPE,
                STRATEGY_SOURCE_ARCHIVE_SCHEMA,
                package.archive_digest,
                ArtifactRetention.PINNED_INPUT,
            ),
            archive_bytes,
        )
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
        study_artifacts={strategy.fingerprint: resolved_output},
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
        "foreign_restart_owner",
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
    graph = await _strategy_graph_with_reference(graph, reference, sessions)
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
            elif post_dispatch_drift == "deleted_artifact":
                await session.execute(delete(ResearchArtifact).where(ResearchArtifact.id == 40))
        restarted_hydrator = NautilusTrialDomainHydrator(
            PostgresResourceReader(restarted_store),
            selected_study_artifact_resolver=create_resolved_study_artifact_output_resolver(
                fresh_sessions
            ),
        )
        if post_dispatch_drift == "foreign_restart_owner":
            with pytest.raises(
                TrialDomainHydrationError,
                match="run attempt is missing or unavailable to this owner",
            ):
                await restarted_hydrator.hydrate_attempt(
                    principal="2", attempt_resource_id=graph.attempt.attempt_id
                )
            return

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


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(("study_artifact_type", "study_value"), _STUDY_OUTPUT_CASES)
async def test_reconstructed_backtest_worker_hydrates_each_persisted_study_type(
    tmp_path: Path,
    study_database: StudyDatabase,
    study_artifact_type: str,
    study_value: Any,
) -> None:
    sessions = study_database.sessions
    study_payload = {"type": study_artifact_type, "value": study_value}
    async with sessions.begin() as session:
        await session.execute(
            update(ResearchArtifact)
            .where(ResearchArtifact.id == 40)
            .values(artifact_type=study_artifact_type, payload=study_payload)
        )
    reference = await _reference(sessions)
    graph, artifact_store, _package_resolver, materializer, preparation_context, _worker_state = (
        _setup(tmp_path / "backtest-study-worker")
    )
    graph = await _strategy_graph_with_reference(
        graph, reference, sessions, artifact_store=artifact_store
    )
    adapter, _store = _adapter(sessions, study_database.storage_schema)
    await _persist_graph(adapter, graph, uuid.uuid4().hex)

    fresh_engine, fresh_sessions = study_database.new_engine_and_sessions()
    try:
        restarted_store = PostgresAggregateStore(
            fresh_sessions,
            schema=study_database.storage_schema,
        )
        hydrator = NautilusTrialDomainHydrator(
            PostgresResourceReader(restarted_store),
            selected_study_artifact_resolver=create_resolved_study_artifact_output_resolver(
                fresh_sessions
            ),
        )
        hydrated = await hydrator.hydrate_attempt(
            principal="1",
            attempt_resource_id=graph.attempt.attempt_id,
        )
        strategy = graph.strategies[0]
        assert hydrated.strategies[0].selected_study_artifact == reference
        assert hydrated.study_artifacts == {
            strategy.fingerprint: ResolvedStudyArtifactOutput(reference, study_payload)
        }

        # Reconstruct the worker graph after process restart, then exercise the
        # real materializer that writes typed Study outputs into the runtime
        # component-context stream consumed by the isolated bridge.
        materialized = materializer.materialize(
            graph=hydrated,
            market_context=preparation_context.market_context,
        )
        bundle = load_materialized_nautilus_runtime_bundle(
            materialized.assembly.runtime_input_artifact,
            artifact_store,
            max_input_bytes=1_000_000,
        )
        assert bundle.context_stream is not None
        context_stream_bytes = artifact_store.read(bundle.context_stream.artifact.storage_key)
        expected_counts = dict(bundle.context_stream.component_counts)
        bindings, contexts = deserialize_component_invocation_context_stream(
            BytesIO(context_stream_bytes),
            expected_component_counts=expected_counts,
        )
        expected_output = ResolvedStudyArtifactOutput(reference, study_payload)
        (component_id,) = expected_counts
        assert bindings[component_id].study_artifacts == {reference.artifact_name: expected_output}
        decoded_contexts = tuple(contexts)
        assert len(decoded_contexts) == expected_counts[component_id]
        assert all(
            decoded_component_id == component_id
            and decoded_context.study_artifacts == {reference.artifact_name: expected_output}
            for decoded_component_id, decoded_context in decoded_contexts
        )

        drifted_payload = {**study_payload, "drift_marker": "changed-after-pin"}
        async with fresh_sessions.begin() as session:
            await session.execute(
                update(ResearchArtifact)
                .where(ResearchArtifact.id == reference.artifact_id)
                .values(payload=drifted_payload)
            )
        with pytest.raises(TrialDomainHydrationError, match="unavailable for restart validation"):
            await hydrator.hydrate_attempt(
                principal="1",
                attempt_resource_id=graph.attempt.attempt_id,
            )
    finally:
        await fresh_engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(("study_artifact_type", "study_value"), _STUDY_OUTPUT_CASES)
async def test_reconstructed_forward_worker_revalidates_persisted_study_output(
    tmp_path: Path,
    study_database: StudyDatabase,
    study_artifact_type: str,
    study_value: Any,
) -> None:
    sessions = study_database.sessions
    study_payload = {"type": study_artifact_type, "value": study_value}
    async with sessions.begin() as session:
        await session.execute(
            update(ResearchArtifact)
            .where(ResearchArtifact.id == 40)
            .values(artifact_type=study_artifact_type, payload=study_payload)
        )
    reference = await _reference(sessions)
    graph, _artifact_store, package_resolver, _materializer, _context, _worker_state = _setup(
        tmp_path / "forward-study-worker"
    )
    graph = await _strategy_graph_with_reference(
        graph,
        reference,
        sessions,
        artifact_store=_artifact_store,
    )
    adapter, store = _adapter(sessions, study_database.storage_schema)
    suffix = uuid.uuid4().hex
    await _persist_graph(adapter, graph, suffix)

    instance = ForwardInstance(
        instance_id=f"forward-study-{suffix}",
        portfolio_fingerprint=graph.portfolio.fingerprint,
        warmup_snapshot_fingerprint=graph.snapshot.fingerprint,
        carry_in_mode=CarryInMode.FLAT,
        state=ForwardState.CREATED,
        last_event_id=None,
        last_event_sequence=0,
        correction_count=0,
        created_at=_NOW,
        updated_at=_NOW,
    )
    forward_state_schema = PostgresForwardStateSchema()
    forward_account_schema = PostgresForwardAccountSchema()
    schema_engine, _schema_sessions = study_database.new_engine_and_sessions()
    try:
        async with schema_engine.begin() as connection:
            for statement in (*forward_state_schema.statements, *forward_account_schema.statements):
                await connection.execute(text(statement))
    finally:
        await schema_engine.dispose()
    state_persistence = replace(
        PostgresStrategyLabV2Persistence.build(sessions),
        forward_state=PostgresForwardStateAdapter(sessions, schema=forward_state_schema),
        forward_account=PostgresForwardAccountAdapter(sessions, schema=forward_account_schema),
    )
    await state_persistence.forward_state.ensure_instance(principal="1", instance=instance)
    warming = await state_persistence.forward_state.transition(
        principal="1",
        instance_id=instance.instance_id,
        target=ForwardState.WARMING_UP,
        now=_NOW + timedelta(seconds=1),
        idempotency_key=f"study-forward-warmup-{suffix}",
    )
    assert warming.instance is not None
    receipt = ForwardWarmupReceipt(
        instance_id=instance.instance_id,
        warmup_snapshot_fingerprint=graph.snapshot.fingerprint,
        carry_in_mode=CarryInMode.FLAT,
        warmup_result_fingerprint=content_digest({"forward-study-warmup": suffix}),
        completed_at=_NOW + timedelta(seconds=2),
    )
    completed = await state_persistence.forward_state.complete_warmup(
        principal="1",
        receipt=receipt,
    )
    assert completed.decision.value == "complete"
    instance = completed.instance
    checkpoint = await state_persistence.forward_state.load_state(
        principal="1",
        instance_id=instance.instance_id,
    )
    assert checkpoint is not None
    account = await state_persistence.forward_account.initialize(
        principal="1",
        state=ForwardAccountState(instance_id=instance.instance_id, base_currency="USD"),
        admission_state=checkpoint,
    )
    assert account.state is not None
    strategy = graph.strategies[0]
    package = graph.packages[strategy.fingerprint]
    plan = ForwardExecutionPlan(
        instance_id=instance.instance_id,
        portfolio_fingerprint=graph.portfolio.fingerprint,
        components=(
            ForwardComponentExecutionPlan(
                component_id=graph.portfolio.components[0].component_id,
                strategy_fingerprint=strategy.fingerprint,
                package_fingerprint=package.fingerprint,
                parameters={},
                random_seed=7,
            ),
        ),
    )
    for resource_type, contract in (
        (ApiResourceType.FORWARD_INSTANCE, instance),
        (ApiResourceType.FORWARD_EXECUTION_PLAN, plan),
    ):
        result = await adapter.create_resource(
            principal="1",
            request_id=f"forward-study-{suffix}-{resource_type.value}",
            request=ResourceMutationRequest(
                resource_type,
                f"forward-study-{suffix}-{resource_type.value}",
                {"attributes": dict(freeze_json(contract))},
                _NOW,
            ),
        )
        assert result.receipt is not None, result.resolution.rejection_reason
        assert result.resolution.decision.value == "accept"

    # Construct a fresh aggregate reader and worker resolver as after a process
    # restart; both the execution plan and Study payload must come from persisted rows.
    fresh_engine, fresh_sessions = study_database.new_engine_and_sessions()
    try:
        fresh_store = PostgresAggregateStore(
            fresh_sessions,
            schema=study_database.storage_schema,
        )
        persistence = replace(
            PostgresStrategyLabV2Persistence.build(fresh_sessions),
            aggregate_store=fresh_store,
            resources=PostgresResourceReader(fresh_store),
            forward_state=PostgresForwardStateAdapter(
                fresh_sessions,
                schema=forward_state_schema,
            ),
            forward_account=PostgresForwardAccountAdapter(
                fresh_sessions,
                schema=forward_account_schema,
            ),
        )
        worker_resolver = create_authenticated_forward_worker_runtime_input_resolver(
            persistence,
            package_resolver,
            principal="1",
        )
        persisted_instance = await persistence.resources.get_domain_contract(
            principal="1",
            resource_type=ApiResourceType.FORWARD_INSTANCE,
            resource_id=instance.instance_id,
        )
        assert isinstance(persisted_instance, ForwardInstance)
        assert persisted_instance == instance
        resolved = await worker_resolver.resolve(
            instance_id=instance.instance_id,
            checkpoint_fingerprint=checkpoint.checkpoint.fingerprint,
        )
        component = resolved.execution_plan.components[graph.portfolio.components[0].component_id]
        assert component.study_artifacts == {
            reference.artifact_name: ResolvedStudyArtifactOutput(
                reference,
                study_payload,
            )
        }

        with pytest.raises(
            ValueError,
            match="durable forward admission checkpoint is unavailable",
        ):
            await worker_resolver.resolve(
                instance_id=instance.instance_id,
                checkpoint_fingerprint=content_digest("stale-forward-study-checkpoint"),
            )

        foreign_resolver = create_authenticated_forward_worker_runtime_input_resolver(
            persistence,
            package_resolver,
            principal="2",
        )
        with pytest.raises(ValueError, match="forward instance is unavailable"):
            await foreign_resolver.resolve(
                instance_id=instance.instance_id,
                checkpoint_fingerprint=checkpoint.checkpoint.fingerprint,
            )

        drifted_payload = {**study_payload, "drift_marker": "changed-after-pin"}
        async with fresh_sessions.begin() as session:
            await session.execute(
                update(ResearchArtifact)
                .where(ResearchArtifact.id == reference.artifact_id)
                .values(payload=drifted_payload)
            )
        with pytest.raises(SelectedStudyArtifactResolutionError):
            await worker_resolver.resolve(
                instance_id=instance.instance_id,
                checkpoint_fingerprint=checkpoint.checkpoint.fingerprint,
            )
    finally:
        await fresh_engine.dispose()
