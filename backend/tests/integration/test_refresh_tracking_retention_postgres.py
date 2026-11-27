"""Tracking-parent retention and targeted waiter wake on real PostgreSQL."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)
OLD = NOW - timedelta(days=9)


def _async_database_url(raw_url: str) -> str:
    return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1).replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://", 1
    )


@pytest_asyncio.fixture
async def retention_sessions(request, test_database_url):
    raw_url = test_database_url
    if not raw_url:
        raw_url = request.getfixturevalue("pg_container").get_connection_url()
    schema = f"refresh_retention_{uuid4().hex}"
    import app.models  # noqa: F401
    from app.database import Base

    bootstrap_engine = create_async_engine(_async_database_url(raw_url))
    scoped_engine = None
    created = False
    try:
        async with bootstrap_engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            created = True
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection.execution_options(schema_translate_map={None: schema})
                )
            )
        scoped_engine = create_async_engine(
            _async_database_url(raw_url),
            connect_args={"server_settings": {"search_path": schema}},
        )
        yield async_sessionmaker(scoped_engine, expire_on_commit=False)
    finally:
        if scoped_engine is not None:
            await scoped_engine.dispose()
        if created:
            async with bootstrap_engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await bootstrap_engine.dispose()


def _job(
    key, capability, status, payload=None, *, updated_at=OLD, next_attempt_at=OLD, last_error=None
):
    from app.models.market_data_foundation import MarketRefreshJob

    return MarketRefreshJob(
        request_key=key,
        capability=capability,
        status=status,
        next_attempt_at=next_attempt_at,
        updated_at=updated_at,
        last_error=last_error,
        metadata_payload=payload or {},
    )


def _parent(key, job_ids):
    return _job(
        key,
        "data_preparation_request",
        "tracking",
        {
            "data_preparation": {
                "role": "system_maintenance_tracking",
                "dependencies": [{"job_ids": job_ids}],
            }
        },
    )


async def test_prune_deletes_only_finished_old_parents(retention_sessions):
    from app.models.market_data_foundation import MarketRefreshJob
    from app.services.market_refresh_retention import prune_finished_tracking_parents

    async with retention_sessions() as db:
        done = _job("c-done", "price_history", "completed")
        open_child = _job("c-open", "price_history", "queued")
        db.add_all([done, open_child])
        await db.flush()
        db.add_all(
            [
                _parent("p-done", [done.id]),
                _parent("p-open", [done.id, open_child.id]),
                _parent("p-empty", []),
            ]
        )
        await db.commit()

    summary = await prune_finished_tracking_parents(
        retention_sessions, retention_days=7, batch_size=2, now=NOW
    )

    assert summary["deleted"] == 2  # p-done and p-empty
    async with retention_sessions() as db:
        keys = set((await db.execute(select(MarketRefreshJob.request_key))).scalars())
    assert keys == {"c-done", "c-open", "p-open"}


async def test_completion_wakes_only_waiters_listing_the_prerequisite(retention_sessions):
    from app.models.market_data_foundation import MarketRefreshJob
    from app.services.market_refresh_queue import (
        DEPENDENCY_PENDING_ERROR,
        wake_waiting_dependents,
    )

    later = NOW + timedelta(hours=1)

    def waiter(key, wait_ids):
        return _job(
            key,
            "price_history",
            "deferred",
            {"data_preparation_child": {"wait_for_job_ids": wait_ids}},
            next_attempt_at=later,
            last_error=DEPENDENCY_PENDING_ERROR,
        )

    async with retention_sessions() as db:
        db.add_all([waiter("w-hit", [41, 7]), waiter("w-miss", [8])])
        await db.commit()
    async with retention_sessions() as db:
        woken = await wake_waiting_dependents(db, prerequisite_id=7, now=NOW)
        await db.commit()
        rows = {
            r.request_key: r.next_attempt_at
            for r in (await db.execute(select(MarketRefreshJob))).scalars()
        }

    assert woken == 1
    assert rows["w-hit"] == NOW
    assert rows["w-miss"] == later
