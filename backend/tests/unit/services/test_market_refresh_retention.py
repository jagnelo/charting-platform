from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.market_data_foundation import MarketRefreshJob
from app.services.market_refresh_retention import prune_finished_tracking_parents
from tests.unit.conftest import AsyncSessionAdapter

NOW = datetime(2026, 11, 27, 12, tzinfo=UTC)
OLD = NOW - timedelta(days=8)
RECENT = NOW - timedelta(days=1)


def _child(key, status):
    return MarketRefreshJob(
        request_key=key,
        capability="price_history",
        status=status,
        next_attempt_at=OLD,
        updated_at=OLD,
        metadata_payload={},
    )


def _parent(key, job_ids, *, updated_at=OLD, role="system_maintenance_tracking", status="tracking"):
    return MarketRefreshJob(
        request_key=key,
        capability="data_preparation_request",
        status=status,
        next_attempt_at=updated_at,
        updated_at=updated_at,
        metadata_payload={
            "data_preparation": {
                "role": role,
                "dependencies": [{"job_ids": job_ids, "background_job_ids": []}],
            }
        },
    )


def _factory(db):
    @asynccontextmanager
    async def factory():
        yield AsyncSessionAdapter(db)

    return factory


def _keys(db):
    return set(db.execute(select(MarketRefreshJob.request_key)).scalars())


@pytest.mark.asyncio
async def test_prunes_only_old_parents_with_all_terminal_children(db):
    done = _child("c-done", "completed")
    failed = _child("c-failed", "failed")
    open_child = _child("c-open", "deferred")
    db.add_all([done, failed, open_child])
    db.flush()
    db.add_all(
        [
            _parent("p-terminal", [done.id, failed.id]),
            _parent("p-no-children", []),
            _parent("p-missing-child", [done.id, 999999]),
            _parent("p-open", [done.id, open_child.id]),
            _parent("p-recent", [done.id], updated_at=RECENT),
            _parent("p-owner", [done.id], role="owner_request_tracking"),
        ]
    )
    db.flush()

    summary = await prune_finished_tracking_parents(
        _factory(db), retention_days=7, batch_size=2, now=NOW
    )

    assert summary["deleted"] == 3
    assert _keys(db) == {
        "c-done",
        "c-failed",
        "c-open",
        "p-open",
        "p-recent",
        "p-owner",
    }

    again = await prune_finished_tracking_parents(
        _factory(db), retention_days=7, batch_size=2, now=NOW
    )
    assert again["deleted"] == 0


@pytest.mark.asyncio
async def test_parent_is_pruned_once_its_open_child_finishes(db):
    child = _child("c", "queued")
    db.add(child)
    db.flush()
    db.add(_parent("p", [child.id]))
    db.flush()
    kwargs = {"retention_days": 7, "now": NOW}

    assert (await prune_finished_tracking_parents(_factory(db), **kwargs))["deleted"] == 0
    child.status = "completed"
    db.flush()
    assert (await prune_finished_tracking_parents(_factory(db), **kwargs))["deleted"] == 1


@pytest.mark.asyncio
async def test_time_budget_stops_the_pass(db):
    db.add(_parent("p", []))
    db.flush()

    summary = await prune_finished_tracking_parents(
        _factory(db), retention_days=7, max_seconds=0, now=NOW
    )

    assert summary["budget_exhausted"] is True
    assert summary["deleted"] == 0
