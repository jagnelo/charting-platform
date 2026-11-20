"""Later maintenance passes join an instrument's waiting children.

Production (2026-11-20): identity and history child keys carry an hour or a
published-session bucket, so every new maintenance parent forked fresh
children while the previous ones still waited. The queue held 45,948 identity
jobs for 32,472 instruments and 55,951 history jobs for 34,421 instruments; one
instrument had ~100 waiting identity lookups, one per hour.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models.market_data_foundation import MarketRefreshJob
from app.models.ohlcv import Timeframe
from app.schemas.data_preparation import DataEnsureRequest
from app.services.data_preparation import (
    _enqueue_history_dependency,
    _enqueue_identity_profile_job,
)
from tests.unit.conftest import AsyncSessionAdapter

pytestmark = pytest.mark.asyncio

HOUR_10 = datetime(2026, 11, 20, 10, 5, tzinfo=UTC)
HOUR_11 = HOUR_10 + timedelta(hours=1)
SESSION_1 = datetime(2026, 11, 18, 21, tzinfo=UTC)
SESSION_2 = datetime(2026, 11, 19, 21, tzinfo=UTC)


def _parent(db, name: str) -> MarketRefreshJob:
    parent = MarketRefreshJob(
        request_key=f"data-preparation:maintenance:{name}",
        capability="data_preparation_request",
        priority=100,
        status="tracking",
        attempts=0,
        next_attempt_at=HOUR_10,
        metadata_payload={},
    )
    db.add(parent)
    db.flush()
    return parent


def _parent_ids(job: MarketRefreshJob) -> set[int]:
    refs = (job.metadata_payload or {}).get("data_preparation_child", {}).get("parent_refs") or []
    return {int(ref["parent_job_id"]) for ref in refs}


async def _identity(async_db, parent, *, now, instrument, required=(), symbol=None):
    return await _enqueue_identity_profile_job(
        async_db,
        parent_job_id=parent.id,
        request_id=f"request-{parent.id}",
        symbol=symbol or instrument.symbol,
        instrument_id=None if instrument is None else instrument.id,
        required_profile_fields=list(required),
        owner_user_id=None,
        priority=100,
        now=now,
    )


async def _open_count(async_db, capability: str) -> int:
    return (
        await async_db.execute(
            select(func.count())
            .select_from(MarketRefreshJob)
            .where(
                MarketRefreshJob.capability == capability,
                MarketRefreshJob.status.in_(["queued", "deferred", "retry", "leased"]),
            )
        )
    ).scalar_one()


async def test_later_hour_identity_ensure_joins_the_waiting_child(db, instrument):
    async_db = AsyncSessionAdapter(db)
    first_parent, second_parent = _parent(db, "a"), _parent(db, "b")
    waiting = await _identity(async_db, first_parent, now=HOUR_10, instrument=instrument)
    waiting.status = "deferred"
    waiting.next_attempt_at = HOUR_11 + timedelta(minutes=30)
    db.flush()

    joined = await _identity(async_db, second_parent, now=HOUR_11, instrument=instrument)

    assert joined.id == waiting.id
    assert _parent_ids(joined) == {first_parent.id, second_parent.id}
    # A live provider deferral is kept rather than pulled forward.
    assert joined.status == "deferred"
    assert await _open_count(async_db, "instrument_metadata") == 1


async def test_symbol_only_identity_ensure_joins_the_waiting_child(db):
    async_db = AsyncSessionAdapter(db)
    first_parent, second_parent = _parent(db, "a"), _parent(db, "b")

    waiting = await _identity(async_db, first_parent, now=HOUR_10, instrument=None, symbol="newco")
    joined = await _identity(async_db, second_parent, now=HOUR_11, instrument=None, symbol="NEWCO")
    other = await _identity(async_db, second_parent, now=HOUR_11, instrument=None, symbol="OTHER")

    assert joined.id == waiting.id
    assert other.id != waiting.id


async def test_identity_with_different_profile_fields_is_not_joined(db, instrument):
    async_db = AsyncSessionAdapter(db)
    first_parent, second_parent = _parent(db, "a"), _parent(db, "b")

    waiting = await _identity(async_db, first_parent, now=HOUR_10, instrument=instrument)
    other = await _identity(
        async_db, second_parent, now=HOUR_11, instrument=instrument, required=["sector"]
    )

    assert other.id != waiting.id


async def test_leased_identity_child_is_not_joined(db, instrument):
    async_db = AsyncSessionAdapter(db)
    first_parent, second_parent = _parent(db, "a"), _parent(db, "b")
    running = await _identity(async_db, first_parent, now=HOUR_10, instrument=instrument)
    running.status = "leased"
    running.lease_token = "lease"
    db.flush()

    fresh = await _identity(async_db, second_parent, now=HOUR_11, instrument=instrument)

    assert fresh.id != running.id
    assert _parent_ids(fresh) == {second_parent.id}
    assert _parent_ids(running) == {first_parent.id}


async def test_completed_negative_identity_keeps_the_hourly_recovery_key(db, instrument):
    async_db = AsyncSessionAdapter(db)
    first_parent, second_parent = _parent(db, "a"), _parent(db, "b")
    finished = await _identity(async_db, first_parent, now=HOUR_10, instrument=instrument)
    finished.status = "completed"
    finished.result_summary = {
        "preparation_status": "no_match",
        "reason_code": "exact_symbol_profile_not_found",
    }
    db.flush()

    recovery = await _identity(async_db, second_parent, now=HOUR_10, instrument=instrument)

    assert recovery.id != finished.id
    assert recovery.request_key == f"{finished.request_key}:recovery"
    assert recovery.status == "queued"


async def test_completed_positive_identity_in_the_same_hour_is_still_reused(db, instrument):
    async_db = AsyncSessionAdapter(db)
    first_parent, second_parent = _parent(db, "a"), _parent(db, "b")
    finished = await _identity(async_db, first_parent, now=HOUR_10, instrument=instrument)
    finished.status = "completed"
    finished.result_summary = {"preparation_status": "ready"}
    db.flush()
    # An older waiting duplicate (from before this change) must not steal a
    # same-hour request away from the completed result.
    stale = MarketRefreshJob(
        request_key="prep-identity:legacy-duplicate",
        instrument_id=instrument.id,
        capability="instrument_metadata",
        priority=100,
        status="queued",
        attempts=0,
        next_attempt_at=HOUR_10,
        metadata_payload=dict(finished.metadata_payload),
    )
    db.add(stale)
    db.flush()

    reused = await _identity(async_db, second_parent, now=HOUR_10, instrument=instrument)

    assert reused.id == finished.id
    assert reused.status == "completed"


def _history_request(instrument, *, end_at=None, start_at=None, adjusted=True):
    payload = {
        "target": {"kind": "instrument", "instrument_id": instrument.id},
        "datasets": ["history"],
        "timeframe": "D1",
        "adjusted": adjusted,
    }
    if end_at is not None:
        payload["end_at"] = end_at.isoformat()
    if start_at is not None:
        payload["start_at"] = start_at.isoformat()
    return DataEnsureRequest.model_validate(payload)


async def _history(async_db, parent, instrument, *, now, wait_for=None, derived_only=False, **kw):
    return await _enqueue_history_dependency(
        async_db,
        parent_job_id=parent.id,
        request_id=f"request-{parent.id}",
        dependency_id=f"dependency-{parent.id}",
        instrument_id=instrument.id,
        request=_history_request(instrument, **kw),
        priority=100,
        timeframe=Timeframe.D1,
        wait_for_job_ids=wait_for,
        derived_only=derived_only,
        now=now,
    )


def _end(job: MarketRefreshJob) -> datetime | None:
    if job.end_at is None:
        return None
    return job.end_at if job.end_at.tzinfo else job.end_at.replace(tzinfo=UTC)


async def test_later_session_joins_and_widens_the_waiting_history_child(db, instrument):
    async_db = AsyncSessionAdapter(db)
    first_parent, second_parent = _parent(db, "a"), _parent(db, "b")
    waiting = await _history(
        async_db, first_parent, instrument, now=HOUR_10, end_at=SESSION_1, wait_for=[7]
    )

    joined = await _history(
        async_db, second_parent, instrument, now=HOUR_11, end_at=SESSION_2, wait_for=[9]
    )

    assert joined.id == waiting.id
    assert _end(joined) == SESSION_2
    child = joined.metadata_payload["data_preparation_child"]
    assert child["range_end"] == SESSION_2.isoformat()
    assert child["range_mode"] == "deepest_admitted"
    assert child["wait_for_job_ids"] == [7, 9]
    assert _parent_ids(joined) == {first_parent.id, second_parent.id}
    assert await _open_count(async_db, "price_history") == 1


async def test_sibling_with_a_later_end_is_reused_unchanged(db, instrument):
    async_db = AsyncSessionAdapter(db)
    first_parent, second_parent = _parent(db, "a"), _parent(db, "b")
    waiting = await _history(async_db, first_parent, instrument, now=HOUR_11, end_at=SESSION_2)

    joined = await _history(async_db, second_parent, instrument, now=HOUR_11, end_at=SESSION_1)

    assert joined.id == waiting.id
    assert _end(joined) == SESSION_2
    assert joined.metadata_payload["data_preparation_child"]["range_end"] == SESSION_2.isoformat()


async def test_open_ended_request_widens_the_sibling_to_latest(db, instrument):
    async_db = AsyncSessionAdapter(db)
    first_parent, second_parent = _parent(db, "a"), _parent(db, "b")
    waiting = await _history(async_db, first_parent, instrument, now=HOUR_10, end_at=SESSION_1)

    joined = await _history(async_db, second_parent, instrument, now=HOUR_11)

    assert joined.id == waiting.id
    assert joined.end_at is None
    assert joined.metadata_payload["data_preparation_child"]["range_end"] is None


async def test_repeating_the_original_key_never_narrows_a_widened_child(db, instrument):
    async_db = AsyncSessionAdapter(db)
    first, second, third = _parent(db, "a"), _parent(db, "b"), _parent(db, "c")
    waiting = await _history(async_db, first, instrument, now=HOUR_10, end_at=SESSION_1)
    await _history(async_db, second, instrument, now=HOUR_11, end_at=SESSION_2)

    repeated = await _history(async_db, third, instrument, now=HOUR_11, end_at=SESSION_1)

    assert repeated.id == waiting.id
    assert _end(repeated) == SESSION_2
    assert _parent_ids(repeated) == {first.id, second.id, third.id}


@pytest.mark.parametrize("status", ["leased", "completed"])
async def test_running_or_finished_history_child_is_not_joined(db, instrument, status):
    async_db = AsyncSessionAdapter(db)
    first_parent, second_parent = _parent(db, "a"), _parent(db, "b")
    earlier = await _history(async_db, first_parent, instrument, now=HOUR_10, end_at=SESSION_1)
    earlier.status = status
    db.flush()

    fresh = await _history(async_db, second_parent, instrument, now=HOUR_11, end_at=SESSION_2)

    assert fresh.id != earlier.id
    assert _end(earlier) == SESSION_1


async def test_explicit_start_ranges_and_other_adjustments_are_not_joined(db, instrument):
    async_db = AsyncSessionAdapter(db)
    parent = _parent(db, "a")
    deepest = await _history(async_db, parent, instrument, now=HOUR_10, end_at=SESSION_1)

    bounded = await _history(
        async_db,
        parent,
        instrument,
        now=HOUR_11,
        start_at=SESSION_1 - timedelta(days=30),
        end_at=SESSION_2,
    )
    unadjusted = await _history(
        async_db, parent, instrument, now=HOUR_11, end_at=SESSION_2, adjusted=False
    )

    assert len({deepest.id, bounded.id, unadjusted.id}) == 3
    assert _end(deepest) == SESSION_1


async def test_acquisition_never_joins_a_waiting_derived_only_child(db, instrument):
    async_db = AsyncSessionAdapter(db)
    parent = _parent(db, "a")
    derived = await _history(
        async_db, parent, instrument, now=HOUR_10, end_at=SESSION_1, derived_only=True
    )

    acquisition = await _history(async_db, parent, instrument, now=HOUR_11, end_at=SESSION_2)

    assert acquisition.id != derived.id
    assert derived.metadata_payload["data_preparation_child"]["derived_only"] is True
    assert _end(derived) == SESSION_1
