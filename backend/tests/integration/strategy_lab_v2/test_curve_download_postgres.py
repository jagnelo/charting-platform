from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.strategy_lab_v2.api_router import create_strategy_lab_router
from app.strategy_lab_v2.application import PostgresStrategyLabV2Adapter
from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    ArtifactManifest,
    ArtifactRetention,
    MetricBasis,
    MetricValue,
)
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.postgres_artifact_retention import (
    PostgresArtifactRetentionAdapter,
    PostgresArtifactRetentionSchema,
)
from app.strategy_lab_v2.postgres_storage import PostgresAggregateStore, PostgresStorageSchema
from app.strategy_lab_v2.postgres_walk_forward_summary import (
    PostgresWalkForwardNativeMetricsAdapter,
)
from app.strategy_lab_v2.walk_forward_summary import (
    WALK_FORWARD_NATIVE_EQUITY_CURVE_MEDIA_TYPE,
    WALK_FORWARD_NATIVE_EQUITY_CURVE_SCHEMA,
    WalkForwardNativeOosMetricSummary,
)

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


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
async def test_authenticated_curve_download_uses_postgres_metrics_and_active_pin(
    pg_container,
    test_database_url: str | None,
    tmp_path,
) -> None:
    raw_url = test_database_url or pg_container.get_connection_url()
    engine = create_async_engine(_async_postgres_url(raw_url), pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex
    storage_schema = PostgresStorageSchema(
        aggregate_table=f"slv2_curve_aggregates_{suffix}",
        receipt_table=f"slv2_curve_receipts_{suffix}",
    )
    retention_schema = PostgresArtifactRetentionSchema(
        retention_table=f"slv2_curve_retention_{suffix}",
        pin_table=f"slv2_curve_pins_{suffix}",
    )
    tables = (
        storage_schema.aggregate_table,
        storage_schema.receipt_table,
        retention_schema.retention_table,
        retention_schema.pin_table,
    )
    owner = "curve-download-owner"
    experiment = content_digest("postgres-authenticated-curve-download")
    payload = b"postgres-backed native out-of-sample equity curve"
    digest = artifact_content_digest(payload)
    manifest = ArtifactManifest(
        content_digest=digest,
        byte_length=len(payload),
        media_type=WALK_FORWARD_NATIVE_EQUITY_CURVE_MEDIA_TYPE,
        schema_version=WALK_FORWARD_NATIVE_EQUITY_CURVE_SCHEMA,
        storage_key=digest,
        retention_class=ArtifactRetention.PINNED_RESULT,
    )
    artifact_store = LocalArtifactStore(tmp_path / "artifacts")
    artifact_store.publish(manifest, payload)

    try:
        async with engine.begin() as connection:
            for statement in storage_schema.statements + retention_schema.statements:
                await connection.execute(text(statement))

        aggregate_store = PostgresAggregateStore(session_factory, schema=storage_schema)
        persistence = replace(
            PostgresStrategyLabV2Persistence.build(session_factory, clock=lambda: NOW),
            aggregate_store=aggregate_store,
            walk_forward_native_metrics=PostgresWalkForwardNativeMetricsAdapter(aggregate_store),
            artifact_retention=PostgresArtifactRetentionAdapter(
                session_factory,
                schema=retention_schema,
            ),
        )
        adapter = PostgresStrategyLabV2Adapter(
            session_factory,
            persistence=persistence,
            walk_forward_artifact_store=artifact_store,
            clock=lambda: NOW,
        )
        native_metrics = WalkForwardNativeOosMetricSummary(
            experiment_fingerprint=experiment,
            definition_fingerprint=content_digest("curve-definition"),
            selection_fingerprint=content_digest("curve-selection"),
            result_manifest_fingerprints=(content_digest("curve-oos-result"),),
            metrics=(
                MetricValue(
                    "total_return",
                    Decimal("0.05"),
                    "fraction",
                    "strategy-lab.metrics.v2",
                    MetricBasis.NET,
                    5,
                ),
            ),
            curve_artifact=manifest,
        )
        persisted = await persistence.walk_forward_native_metrics.persist(
            principal=owner,
            summary=native_metrics,
        )
        assert persisted.decision.value == "persisted"
        pin = await adapter._pin_walk_forward_curve(
            principal=owner,
            experiment_fingerprint=experiment,
            manifest=manifest,
        )

        async def adapter_dependency() -> PostgresStrategyLabV2Adapter:
            return adapter

        async def principal_dependency(request: Request) -> str:
            return request.headers.get("X-Test-Owner", owner)

        app = FastAPI()
        app.include_router(
            create_strategy_lab_router(
                adapter_dependency=adapter_dependency,
                principal_dependency=principal_dependency,
                request_id_factory=lambda: "postgres-curve-download",
                clock=lambda: NOW,
            ),
            prefix="/api/v1",
        )
        path = f"/api/v1/strategy-lab/v2/experiments/{experiment}/walk-forward/curve"
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://strategy-lab.test",
        ) as client:
            downloaded = await client.get(path)
            assert downloaded.status_code == 200
            assert downloaded.content == payload
            assert downloaded.headers["content-length"] == str(len(payload))
            assert downloaded.headers["x-content-digest"] == digest

            foreign_owner = await client.get(
                path,
                headers={"X-Test-Owner": "different-owner"},
            )
            assert foreign_owner.status_code == 404

            # PostgreSQL authorization must not make corrupted local bytes
            # downloadable.
            artifact_path = artifact_store.path_for(manifest.storage_key)
            os.chmod(artifact_path, 0o600)
            artifact_path.write_bytes(b"tampered")
            corrupt_bytes = await client.get(path)
            assert corrupt_bytes.status_code == 409

            manifest_fingerprint = content_digest(manifest)
            await persistence.artifact_retention.release_pin(
                manifest_fingerprint=manifest_fingerprint,
                pin_id=pin.pin_id,
                released_at=NOW,
            )
            released_pin = await client.get(path)
            assert released_pin.status_code == 404
    finally:
        async with engine.begin() as connection:
            for table in tables:
                await connection.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
        await engine.dispose()
