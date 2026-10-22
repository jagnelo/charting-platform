from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.api_router import create_strategy_lab_router
from app.strategy_lab_v2.application import PostgresStrategyLabV2Adapter
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.postgres_resources import PostgresResourceReader
from app.strategy_lab_v2.postgres_storage import PostgresAggregateStore, PostgresStorageSchema

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


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
async def test_resource_api_mutations_are_durable_idempotent_and_owner_scoped(
    pg_container,
    test_database_url: str | None,
) -> None:
    raw_url = test_database_url or pg_container.get_connection_url()
    engine = create_async_engine(_async_postgres_url(raw_url), pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex
    schema = PostgresStorageSchema(
        aggregate_table=f"slv2_api_aggregates_{suffix}",
        receipt_table=f"slv2_api_receipts_{suffix}",
    )
    tables = (schema.receipt_table, schema.aggregate_table)

    try:
        async with engine.begin() as connection:
            for statement in schema.statements:
                await connection.execute(text(statement))

        aggregate_store = PostgresAggregateStore(session_factory, schema=schema)
        persistence = replace(
            PostgresStrategyLabV2Persistence.build(session_factory),
            aggregate_store=aggregate_store,
            resources=PostgresResourceReader(aggregate_store),
        )

        def build_adapter() -> PostgresStrategyLabV2Adapter:
            return PostgresStrategyLabV2Adapter(
                session_factory,
                persistence=persistence,
                clock=lambda: NOW,
            )

        adapter_holder = {"current": build_adapter()}

        async def adapter_dependency() -> PostgresStrategyLabV2Adapter:
            return adapter_holder["current"]

        async def principal_dependency(request: Request) -> str:
            return request.headers.get("X-Test-Owner", "strategy-lab-api-owner")

        app = FastAPI()
        app.include_router(
            create_strategy_lab_router(
                adapter_dependency=adapter_dependency,
                principal_dependency=principal_dependency,
                request_id_factory=lambda: "postgres-resource-api-request",
                clock=lambda: NOW,
            ),
            prefix="/api/v1",
        )

        body = {
            "attributes": {
                "resource_id": "strategy-api-version-1",
                "strategy_id": "postgres-api-strategy",
                "version_id": "v1",
                "sdk_version": "strategy-sdk.v2",
                "source_digest": content_digest("postgres-api-strategy-source"),
                "default_parameters": {"lookback": 20},
            }
        }
        path = "/api/v1/strategy-lab/v2/strategies"
        headers = {"Idempotency-Key": "postgres-api-strategy-create"}
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://strategy-lab.test",
        ) as client:
            created = await client.post(path, headers=headers, json=body)
            assert created.status_code == 202
            assert created.json()["data"]["id"] == "strategy-api-version-1"
            assert created.json()["meta"]["decision"] == "accept"

            # Reconstruct the application adapter to prove replay is backed by
            # the PostgreSQL receipt rather than process-local route state.
            adapter_holder["current"] = build_adapter()
            replayed = await client.post(path, headers=headers, json=body)
            assert replayed.status_code == 202
            assert replayed.json() == created.json() | {
                "meta": created.json()["meta"] | {"decision": "replay_existing"}
            }

            changed_body = {
                "attributes": body["attributes"] | {"default_parameters": {"lookback": 30}}
            }
            conflict = await client.post(path, headers=headers, json=changed_body)
            assert conflict.status_code == 409
            assert conflict.json()["errors"][0]["code"] == "idempotency_conflict"

            detail = await client.get(f"{path}/strategy-api-version-1")
            assert detail.status_code == 200
            assert detail.json()["data"]["attributes"]["default_parameters"] == {"lookback": 20}

            collection = await client.get(path, params={"limit": 1})
            assert collection.status_code == 200
            assert [item["id"] for item in collection.json()["data"]] == ["strategy-api-version-1"]

            foreign_detail = await client.get(
                f"{path}/strategy-api-version-1",
                headers={"X-Test-Owner": "different-owner"},
            )
            assert foreign_detail.status_code == 404

        writes = await adapter_holder["current"].get_resource(
            principal="strategy-lab-api-owner",
            resource_type=ApiResourceType.STRATEGY,
            resource_id="strategy-api-version-1",
        )
        assert writes is not None
        assert writes.attributes["default_parameters"] == {"lookback": 20}
    finally:
        async with engine.begin() as connection:
            for table in tables:
                await connection.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
        await engine.dispose()
