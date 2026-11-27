"""Instrument sync-run closing and reaping against real PostgreSQL.

Production (2026-11-27) held 12 instrument_sync_run rows stuck in 'running':
arq cancels timed-out jobs with CancelledError (a BaseException) and deploys
kill the worker, so the old ``except Exception`` close never ran.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.services import instrument_sync

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _async_database_url(raw_url: str) -> str:
    return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1).replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://", 1
    )


@pytest_asyncio.fixture
async def sessions(request, test_database_url):
    raw_url = test_database_url or request.getfixturevalue("pg_container").get_connection_url()
    schema = f"sync_run_reaper_{uuid4().hex}"
    import app.models  # noqa: F401
    from app.database import Base

    bootstrap = create_async_engine(_async_database_url(raw_url))
    scoped = None
    created = False
    try:
        async with bootstrap.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            created = True
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection.execution_options(schema_translate_map={None: schema})
                )
            )
        scoped = create_async_engine(
            _async_database_url(raw_url),
            connect_args={"server_settings": {"search_path": schema}},
        )
        yield async_sessionmaker(scoped, expire_on_commit=False)
    finally:
        if scoped is not None:
            await scoped.dispose()
        if created:
            async with bootstrap.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await bootstrap.dispose()


async def _insert_run(session, *, status, started_at, finished_at=None):
    return (
        await session.execute(
            text(
                "INSERT INTO instrument_sync_run (operation, source, status, started_at,"
                " finished_at, created_count, updated_count, skipped_count, total_count)"
                " VALUES ('sync-instruments', 'test', :status, :started, :finished, 0, 0, 0, 0)"
                " RETURNING id"
            ),
            {"status": status, "started": started_at, "finished": finished_at},
        )
    ).scalar_one()


async def _row(session, run_id):
    return (
        await session.execute(
            text("SELECT status, finished_at, error FROM instrument_sync_run WHERE id = :id"),
            {"id": run_id},
        )
    ).one()


async def test_reaper_closes_only_stale_running_rows_and_is_idempotent(sessions, monkeypatch):
    monkeypatch.setattr(instrument_sync.settings, "INSTRUMENT_SYNC_RUN_STALE_AFTER_SECONDS", 21600)
    now = datetime.now(UTC)
    async with sessions() as session:
        stale = await _insert_run(session, status="running", started_at=now - timedelta(days=3))
        fresh = await _insert_run(session, status="running", started_at=now - timedelta(minutes=5))
        done = await _insert_run(
            session,
            status="completed",
            started_at=now - timedelta(days=3),
            finished_at=now - timedelta(days=3) + timedelta(minutes=8),
        )
        await session.commit()

        assert await instrument_sync.reap_stale_sync_runs(session) == 1
        assert await instrument_sync.reap_stale_sync_runs(session) == 0

        status, finished_at, error = await _row(session, stale)
        assert status == "failed" and finished_at is not None
        assert error.startswith("abandoned:")
        assert (await _row(session, fresh))[0] == "running"
        assert (await _row(session, done))[0] == "completed"


async def test_real_task_cancellation_closes_the_row_as_cancelled(sessions, monkeypatch):
    monkeypatch.setattr(instrument_sync, "_run_close_session", lambda: sessions())
    started = asyncio.Event()

    async def slow_bootstrap(*_args, **_kwargs):
        started.set()
        await asyncio.sleep(3600)

    monkeypatch.setattr(instrument_sync, "bootstrap_isins", slow_bootstrap)

    async with sessions() as session:
        task = asyncio.create_task(instrument_sync.run_tracked_sync(session, "bootstrap-ids"))
        await asyncio.wait_for(started.wait(), timeout=10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    async with sessions() as session:
        status, finished_at, error = (
            await session.execute(
                text("SELECT status, finished_at, error FROM instrument_sync_run")
            )
        ).one()
    assert status == "cancelled"
    assert finished_at is not None
    assert "CancelledError" in error
