"""Instrument sync run rows must never be left 'running' (production 2026-11-27)."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.models.instrument_sync_run import InstrumentSyncRun
from app.services import instrument_sync
from tests.unit.conftest import AsyncSessionAdapter


class _SessionCtx:
    """Async context manager handing out the shared sqlite fixture session."""

    def __init__(self, db):
        self._adapter = AsyncSessionAdapter(db)

    async def __aenter__(self):
        return self._adapter

    async def __aexit__(self, *_exc):
        return False


def _run(db, operation="sync-instruments", *, age_seconds=0, status="running"):
    row = InstrumentSyncRun(
        operation=operation,
        source="fixture",
        status=status,
        started_at=datetime.now(UTC) - timedelta(seconds=age_seconds),
    )
    db.add(row)
    db.commit()
    return row


@pytest.fixture(autouse=True)
def _fixture_label(monkeypatch):
    monkeypatch.setattr(instrument_sync, "_provider_chain_label", AsyncMock(return_value="fixture"))


@pytest.mark.asyncio
async def test_cancelled_job_closes_row_as_cancelled(db, monkeypatch):
    monkeypatch.setattr(instrument_sync, "_run_close_session", lambda: _SessionCtx(db))

    async def hang(*_a, **_k):
        raise asyncio.CancelledError

    monkeypatch.setattr(instrument_sync, "bootstrap_isins", hang)

    with pytest.raises(asyncio.CancelledError):
        await instrument_sync.run_tracked_sync(AsyncSessionAdapter(db), "bootstrap-ids")

    db.expire_all()
    run = db.query(InstrumentSyncRun).one()
    assert run.status == "cancelled"
    assert run.finished_at is not None
    assert "CancelledError" in run.error


@pytest.mark.asyncio
async def test_failed_commit_still_closes_row_via_fresh_session(db, monkeypatch):
    monkeypatch.setattr(instrument_sync, "_run_close_session", lambda: _SessionCtx(db))

    async def boom(*_a, **_k):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(instrument_sync, "sync_instruments", boom)

    class BrokenSession(AsyncSessionAdapter):
        broken = False

        async def commit(self):
            if self.broken:
                raise RuntimeError("PendingRollbackError")
            await super().commit()

        async def rollback(self):
            raise RuntimeError("connection lost")

    session = BrokenSession(db)
    original = instrument_sync.sync_instruments

    async def break_then_fail(*_a, **_k):
        session.broken = True
        return await original()

    monkeypatch.setattr(instrument_sync, "sync_instruments", break_then_fail)

    with pytest.raises(RuntimeError, match="provider exploded"):
        await instrument_sync.run_tracked_sync(session, "sync-instruments")

    db.expire_all()
    run = db.query(InstrumentSyncRun).one()
    assert run.status == "failed"
    assert run.finished_at is not None
    assert "provider exploded" in run.error


@pytest.mark.asyncio
async def test_bootstrap_stops_at_deadline(db, instrument):
    result = await instrument_sync.bootstrap_isins(AsyncSessionAdapter(db), deadline=0.0)
    assert result["updated"] == 0
    assert result["skipped"] == 0


@pytest.mark.asyncio
async def test_reaper_closes_only_stale_running_rows(db, monkeypatch):
    monkeypatch.setattr(instrument_sync.settings, "INSTRUMENT_SYNC_RUN_STALE_AFTER_SECONDS", 3600)
    stale = _run(db, age_seconds=7200)
    fresh = _run(db, age_seconds=60)
    done = _run(db, age_seconds=9000, status="completed")
    stale_id, fresh_id, done_id = stale.id, fresh.id, done.id

    assert await instrument_sync.reap_stale_sync_runs(AsyncSessionAdapter(db)) == 1
    # Idempotent: nothing left to close.
    assert await instrument_sync.reap_stale_sync_runs(AsyncSessionAdapter(db)) == 0

    db.expire_all()
    rows = {r.id: r for r in db.query(InstrumentSyncRun).all()}
    assert rows[stale_id].status == "failed"
    assert rows[stale_id].finished_at is not None
    assert rows[stale_id].error.startswith("abandoned:")
    assert rows[fresh_id].status == "running"
    assert rows[fresh_id].finished_at is None
    assert rows[done_id].status == "completed"


@pytest.mark.asyncio
async def test_stale_running_row_does_not_block_new_run(db, monkeypatch):
    monkeypatch.setattr(instrument_sync.settings, "INSTRUMENT_SYNC_RUN_STALE_AFTER_SECONDS", 3600)
    _run(db, "bootstrap-ids", age_seconds=86400)
    monkeypatch.setattr(
        instrument_sync, "bootstrap_isins", AsyncMock(return_value={"updated": 1, "total": 1})
    )

    out = await instrument_sync.run_tracked_sync(AsyncSessionAdapter(db), "bootstrap-ids")

    db.expire_all()
    statuses = sorted(r.status for r in db.query(InstrumentSyncRun).all())
    assert out["updated"] == 1
    assert statuses == ["completed", "failed"]


@pytest.mark.asyncio
async def test_worker_startup_runs_the_reaper(monkeypatch):
    from app.config import settings
    from app.workers import arq_worker

    reaper = AsyncMock(return_value=0)
    monkeypatch.setattr(instrument_sync, "reap_stale_sync_runs_safely", reaper)
    monkeypatch.setattr(settings, "CORE_WORKSTATION_BOOTSTRAP_ENABLED", False)

    await arq_worker.worker_startup({})

    reaper.assert_awaited_once()
