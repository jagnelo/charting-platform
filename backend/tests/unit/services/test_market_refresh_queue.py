from datetime import UTC, datetime, timedelta

import pytest

from app.services.market_refresh_queue import (
    claim_refresh_jobs,
    complete_refresh_job,
    enqueue_refresh_job,
    retry_refresh_job,
)
from tests.unit.conftest import AsyncSessionAdapter


@pytest.mark.asyncio
async def test_refresh_jobs_coalesce_and_claim_in_priority_order(db, instrument):
    async_db = AsyncSessionAdapter(db)
    now = datetime(2026, 9, 4, 12, tzinfo=UTC)
    first = await enqueue_refresh_job(
        async_db,
        request_key="d1:1",
        capability="price_history",
        instrument_id=instrument.id,
        timeframe="D1",
        priority=100,
        now=now,
    )
    again = await enqueue_refresh_job(
        async_db,
        request_key="d1:1",
        capability="price_history",
        instrument_id=instrument.id,
        timeframe="D1",
        priority=1,
        metadata_payload={"demand": "high_alert"},
        now=now,
    )
    assert first.id == again.id
    assert again.priority == 1
    assert again.metadata_payload["demand"] == "high_alert"

    jobs = await claim_refresh_jobs(async_db, now=now)
    assert [job.request_key for job in jobs] == ["d1:1"]
    assert jobs[0].status == "leased"
    await complete_refresh_job(async_db, jobs[0])
    assert jobs[0].status == "completed"


@pytest.mark.asyncio
async def test_failed_job_uses_bounded_exponential_retry(db):
    async_db = AsyncSessionAdapter(db)
    now = datetime(2026, 9, 4, 12, tzinfo=UTC)
    job = await enqueue_refresh_job(
        async_db,
        request_key="d1:2",
        capability="price_history",
        now=now,
    )
    await claim_refresh_jobs(async_db, now=now)
    await retry_refresh_job(async_db, job, "provider timeout", now=now)
    assert job.status == "retry"
    assert job.next_attempt_at >= now + timedelta(seconds=2)


@pytest.mark.asyncio
async def test_provider_reset_defers_job_until_retry_at(db):
    async_db = AsyncSessionAdapter(db)
    now = datetime(2026, 9, 4, 12, tzinfo=UTC)
    retry_at = now + timedelta(minutes=7)
    job = await enqueue_refresh_job(
        async_db,
        request_key="d1:quota",
        capability="price_history",
        now=now,
    )
    await claim_refresh_jobs(async_db, now=now)
    await retry_refresh_job(
        async_db,
        job,
        "provider rate limit",
        now=now,
        retry_at=retry_at,
    )
    assert job.status == "deferred"
    assert job.next_attempt_at == retry_at
    assert job.metadata_payload["defer_reason"] == "provider_reset"
