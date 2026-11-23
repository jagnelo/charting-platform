"""Duplicate deepest-range history children fold into the oldest sibling.

Children forked before enqueue-time joining existed (or by a race it skipped)
each spent a provider request on the same series. A drain now hands such a
duplicate's parents to the oldest waiting sibling and lets the duplicate copy
that sibling's outcome instead of fetching.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.models.market_data_foundation import MarketRefreshJob
from app.models.ohlcv import Timeframe
from app.tasks import data_tasks
from tests.unit.conftest import AsyncSessionAdapter

NOW = datetime(2026, 11, 23, 18, tzinfo=UTC)


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False


def _parent(db, name: str, child_ids: list[int]) -> MarketRefreshJob:
    parent = MarketRefreshJob(
        request_key=f"data-preparation:maintenance:{name}",
        capability="data_preparation_request",
        priority=100,
        status="tracking",
        attempts=0,
        next_attempt_at=NOW,
        metadata_payload={
            "data_preparation": {
                "role": "system_maintenance_tracking",
                "version": 1,
                "dependencies": [
                    {
                        "dependency_id": f"history-{name}",
                        "dataset": "history",
                        "job_ids": list(child_ids),
                    }
                ],
            }
        },
    )
    db.add(parent)
    db.flush()
    return parent


def _history_child(
    db,
    instrument,
    key: str,
    *,
    status: str,
    parent_ids: list[int] | None = None,
    adjusted: bool = True,
    source_provider: str | None = None,
    priority: int = 100,
    end_at: datetime | None = None,
) -> MarketRefreshJob:
    job = MarketRefreshJob(
        request_key=f"prep-history:{key}",
        instrument_id=instrument.id,
        capability="price_history",
        timeframe=Timeframe.D1.value,
        start_at=None,
        end_at=end_at,
        priority=priority,
        status=status,
        attempts=0,
        next_attempt_at=NOW,
        lease_token="lease-" + key if status == "leased" else None,
        metadata_payload={
            "data_preparation_child": {
                "dataset": "history",
                "instrument_id": instrument.id,
                "adjusted": adjusted,
                "range_mode": "deepest_admitted",
                "range_start": None,
                "range_end": end_at.isoformat() if end_at else None,
                "source_provider": source_provider,
                "wait_for_job_ids": [],
                "derived_only": False,
                "parent_refs": [
                    {"parent_job_id": parent_id, "dependency_id": f"dep-{parent_id}"}
                    for parent_id in parent_ids or []
                ],
            }
        },
    )
    db.add(job)
    db.flush()
    return job


def _child(job: MarketRefreshJob) -> dict:
    return job.metadata_payload["data_preparation_child"]


def _reload(db, *jobs: MarketRefreshJob) -> list[MarketRefreshJob]:
    db.expire_all()
    ids = [job.id for job in jobs]
    by_id = {
        job.id: job
        for job in db.execute(select(MarketRefreshJob).where(MarketRefreshJob.id.in_(ids)))
        .scalars()
        .all()
    }
    return [by_id[job_id] for job_id in ids]


async def _drain(monkeypatch, session, job, fetch: AsyncMock) -> dict:
    monkeypatch.setattr(data_tasks, "AsyncSessionLocal", lambda: _SessionContext(session))
    monkeypatch.setattr(data_tasks, "claim_refresh_jobs", AsyncMock(side_effect=[[job], []]))
    monkeypatch.setattr(data_tasks, "_plan_and_fetch_history_chunk", fetch)
    return await data_tasks.process_refresh_jobs({})


@pytest.mark.asyncio
async def test_duplicate_waits_on_oldest_sibling_then_copies_its_outcome_without_fetching(
    db, instrument, monkeypatch
):
    survivor = _history_child(db, instrument, "survivor", status="queued", priority=100)
    duplicate = _history_child(db, instrument, "duplicate", status="leased", priority=40)
    survivor_parent = _parent(db, "survivor", [survivor.id])
    duplicate_parent = _parent(db, "duplicate", [duplicate.id])
    survivor.metadata_payload = {
        "data_preparation_child": {
            **_child(survivor),
            "parent_refs": [{"parent_job_id": survivor_parent.id, "dependency_id": "a"}],
        }
    }
    duplicate.metadata_payload = {
        "data_preparation_child": {
            **_child(duplicate),
            "derive_coarse_timeframes": True,
            "parent_refs": [{"parent_job_id": duplicate_parent.id, "dependency_id": "b"}],
        }
    }
    db.flush()
    session = AsyncSessionAdapter(db)
    fetch = AsyncMock(side_effect=AssertionError("a duplicate must not reach the provider"))

    first = await _drain(monkeypatch, session, duplicate, fetch)

    fetch.assert_not_awaited()
    assert first["retried"] == 1
    survivor, duplicate, duplicate_parent = _reload(db, survivor, duplicate, duplicate_parent)
    assert duplicate.status == "deferred"
    assert duplicate.last_error == data_tasks.DEPENDENCY_PENDING_ERROR
    assert _child(duplicate)["coalesced_into"] == survivor.id
    assert survivor.id in _child(duplicate)["wait_for_job_ids"]
    assert _child(duplicate)["parent_refs"] == []
    # The duplicate's parent now tracks the survivor, which carries its ref.
    assert {int(ref["parent_job_id"]) for ref in _child(survivor)["parent_refs"]} == {
        survivor_parent.id,
        duplicate_parent.id,
    }
    dependency = duplicate_parent.metadata_payload["data_preparation"]["dependencies"][0]
    assert dependency["job_ids"] == [survivor.id]
    # The more urgent request and its coarse derivation are kept.
    assert survivor.priority == 40
    assert _child(survivor)["derive_coarse_timeframes"] is True
    assert survivor.status == "queued"

    survivor.status = "completed"
    survivor.result_summary = {
        "outcome": "completed",
        "preparation_status": "ready",
        "instrument_id": instrument.id,
        "timeframe": "D1",
    }
    duplicate.status = "leased"
    duplicate.lease_token = "lease-duplicate-2"
    duplicate.leased_until = None
    db.flush()
    derive = AsyncMock()
    monkeypatch.setattr(data_tasks, "refresh_derived_timeframe_if_needed", derive)

    second = await _drain(monkeypatch, AsyncSessionAdapter(db), duplicate, fetch)

    fetch.assert_not_awaited()
    assert second["completed"] == 1
    (duplicate,) = _reload(db, duplicate)
    assert duplicate.status == "completed"
    assert duplicate.result_summary == {
        "outcome": "completed",
        "preparation_status": "ready",
        "instrument_id": instrument.id,
        "timeframe": "D1",
        "coalesced_into": survivor.id,
    }
    assert derive.await_count == 2  # W1 and MN from the cached daily bars.


@pytest.mark.asyncio
async def test_the_oldest_sibling_is_never_coalesced(db, instrument):
    from app.services.data_preparation import coalesce_history_duplicate

    oldest = _history_child(db, instrument, "oldest", status="leased")
    _history_child(db, instrument, "newer", status="queued")

    survivor = await coalesce_history_duplicate(AsyncSessionAdapter(db), job=oldest, now=NOW)

    assert survivor is None
    assert "coalesced_into" not in _child(oldest)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "older",
    [
        {"adjusted": False},
        {"source_provider": "tiingo"},
        {"status": "completed"},
        {"status": "leased"},
    ],
    ids=["other-adjustment", "other-feed-pin", "finished", "being-drained"],
)
async def test_only_a_matching_waiting_sibling_absorbs_a_duplicate(db, instrument, older):
    from app.services.data_preparation import coalesce_history_duplicate

    _history_child(db, instrument, "older", **{"status": "queued", **older})
    job = _history_child(db, instrument, "job", status="leased")

    survivor = await coalesce_history_duplicate(AsyncSessionAdapter(db), job=job, now=NOW)

    assert survivor is None
    assert "coalesced_into" not in _child(job)


@pytest.mark.asyncio
async def test_coalescing_widens_a_narrower_survivor_end(db, instrument):
    from app.services.data_preparation import coalesce_history_duplicate

    earlier = datetime(2026, 11, 20, 21, tzinfo=UTC)
    later = datetime(2026, 11, 22, 21, tzinfo=UTC)
    older = _history_child(db, instrument, "older", status="deferred", end_at=earlier)
    job = _history_child(db, instrument, "job", status="leased", end_at=later)

    survivor = await coalesce_history_duplicate(AsyncSessionAdapter(db), job=job, now=NOW)

    assert survivor is not None and survivor.id == older.id
    assert survivor.end_at.replace(tzinfo=UTC) == later
    assert _child(survivor)["range_end"] == later.isoformat()


@pytest.mark.parametrize(
    ("status", "survivor_end", "expected"),
    [
        ("deferred", None, False),
        ("completed", datetime(2026, 11, 20, tzinfo=UTC), False),
        ("completed", datetime(2026, 11, 22, tzinfo=UTC), True),
        ("completed", None, True),
    ],
    ids=["unfinished", "narrower", "covering", "open-ended"],
)
def test_a_coalesced_duplicate_copies_only_a_finished_covering_outcome(
    status, survivor_end, expected
):
    from app.services.data_preparation import coalesced_history_summary

    survivor = MarketRefreshJob(
        id=7,
        status=status,
        end_at=survivor_end,
        result_summary={"outcome": "completed", "preparation_status": "unavailable"},
    )
    duplicate = MarketRefreshJob(
        id=9,
        end_at=datetime(2026, 11, 21, tzinfo=UTC),
        metadata_payload={"data_preparation_child": {"coalesced_into": 7}},
    )

    summary = coalesced_history_summary(duplicate, survivor)

    if expected:
        assert summary == {"preparation_status": "unavailable", "coalesced_into": 7}
    else:
        assert summary is None


@pytest.mark.asyncio
async def test_later_requests_join_the_survivor_not_the_folded_duplicate(db, instrument):
    from app.schemas.data_preparation import DataEnsureRequest
    from app.services.data_preparation import (
        _enqueue_history_dependency,
        coalesce_history_duplicate,
    )

    session = AsyncSessionAdapter(db)
    survivor = _history_child(db, instrument, "survivor", status="deferred")
    duplicate = _history_child(db, instrument, "duplicate", status="leased")
    assert (await coalesce_history_duplicate(session, job=duplicate, now=NOW)).id == survivor.id
    # Folded duplicates stay open while they wait; make it the lowest id the
    # enqueue-time join would see if it did not skip folded rows.
    duplicate.status = "deferred"
    survivor.status = "retry"
    db.flush()
    parent = _parent(db, "later", [])

    joined = await _enqueue_history_dependency(
        session,
        parent_job_id=parent.id,
        request_id="request-later",
        dependency_id="dependency-later",
        instrument_id=instrument.id,
        request=DataEnsureRequest.model_validate(
            {
                "target": {"kind": "instrument", "instrument_id": instrument.id},
                "datasets": ["history"],
                "timeframe": "D1",
                "adjusted": True,
            }
        ),
        priority=100,
        timeframe=Timeframe.D1,
        now=NOW,
    )

    assert joined.id == survivor.id
