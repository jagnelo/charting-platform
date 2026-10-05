from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.postgres_worker_state import (
    PostgresWorkerStateAdapter,
    PostgresWorkerStateSchema,
)
from app.strategy_lab_v2.workers import (
    WorkerKind,
    WorkerProfile,
    WorkerReservationDecision,
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
async def test_concurrent_reservations_cannot_overbook_one_serial_worker_profile(
    pg_container,
    test_database_url: str | None,
) -> None:
    raw_url = test_database_url or pg_container.get_connection_url()
    engine = create_async_engine(_async_postgres_url(raw_url), pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex
    schema = PostgresWorkerStateSchema(
        profile_table=f"slv2_fleet_profiles_{suffix}",
        reservation_table=f"slv2_fleet_reservations_{suffix}",
        lease_table=f"slv2_fleet_leases_{suffix}",
        observation_table=f"slv2_fleet_observations_{suffix}",
    )
    tables = (
        schema.observation_table,
        schema.lease_table,
        schema.reservation_table,
        schema.profile_table,
    )
    profile = WorkerProfile(
        "postgres-concurrent-backtest-worker",
        WorkerKind.BACKTEST,
        content_digest("exact-runtime-profile"),
    )
    adapter = PostgresWorkerStateAdapter(session_factory, schema=schema)
    now = datetime(2026, 10, 5, tzinfo=UTC)

    try:
        async with engine.begin() as connection:
            for statement in schema.statements:
                await connection.execute(text(statement))
        await adapter.ensure_profile(profile)

        first, second = await asyncio.gather(
            adapter.reserve(
                profile=profile,
                attempt_id="concurrent-attempt-1",
                reservation_id=content_digest("concurrent-reservation-1"),
                acquired_at=now,
            ),
            adapter.reserve(
                profile=profile,
                attempt_id="concurrent-attempt-2",
                reservation_id=content_digest("concurrent-reservation-2"),
                acquired_at=now,
            ),
        )

        assert {first.decision, second.decision} == {
            WorkerReservationDecision.ACCEPT,
            WorkerReservationDecision.SATURATED,
        }
        persisted = await adapter.load_pool(profile)
        assert len(persisted.active_reservations) == 1
        winner = first if first.decision is WorkerReservationDecision.ACCEPT else second
        assert winner.reservation == persisted.active_reservations[0]
    finally:
        async with engine.begin() as connection:
            for table in tables:
                await connection.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
        await engine.dispose()
