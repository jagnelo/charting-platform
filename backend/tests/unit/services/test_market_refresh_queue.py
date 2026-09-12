from datetime import UTC, datetime, timedelta

import pytest

from app.services.market_refresh_queue import (
    RefreshLeaseLostError,
    _acquire_enqueue_lock,
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
    assert jobs[0].lease_token and len(jobs[0].lease_token) == 32
    await complete_refresh_job(
        async_db,
        jobs[0],
        now=now,
        result_summary={"bars_observed": 12, "data_status": "observed"},
    )
    assert jobs[0].status == "completed"
    assert jobs[0].lease_token is None
    assert jobs[0].started_at == now
    assert jobs[0].finished_at == now
    assert jobs[0].result_summary == {
        "outcome": "completed",
        "bars_observed": 12,
        "data_status": "observed",
    }


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
    assert job.finished_at == now
    assert job.result_summary["outcome"] == "retry"
    assert "provider timeout" in job.result_summary["error"]


@pytest.mark.asyncio
async def test_failed_job_redacts_credentials_before_persisting_error(db):
    async_db = AsyncSessionAdapter(db)
    now = datetime(2026, 9, 4, 12, tzinfo=UTC)
    job = await enqueue_refresh_job(
        async_db,
        request_key="d1:redacted-error",
        capability="price_history",
        now=now,
    )
    await claim_refresh_jobs(async_db, now=now)
    await retry_refresh_job(
        async_db,
        job,
        "GET https://provider.test/data?api_key=secret-value",
        now=now,
    )
    assert "secret-value" not in job.last_error
    assert "<redacted>" in job.last_error


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
    assert job.lease_token is None
    assert job.result_summary["outcome"] == "deferred"
    assert job.result_summary["provider_retry_at"] == retry_at.isoformat()


@pytest.mark.asyncio
async def test_expired_or_wrong_refresh_lease_cannot_mutate_job(db):
    async_db = AsyncSessionAdapter(db)
    now = datetime(2026, 9, 4, 12, tzinfo=UTC)
    _ = await enqueue_refresh_job(
        async_db,
        request_key="d1:lease-safety",
        capability="price_history",
        now=now,
    )
    claimed = (await claim_refresh_jobs(async_db, now=now, lease_seconds=30))[0]
    original_token = claimed.lease_token
    assert original_token

    with pytest.raises(RefreshLeaseLostError):
        await complete_refresh_job(async_db, claimed, now=now, lease_token="wrong-token")

    claimed.leased_until = now - timedelta(seconds=1)
    await async_db.flush()
    with pytest.raises(RefreshLeaseLostError):
        await retry_refresh_job(async_db, claimed, "expired", now=now)


@pytest.mark.asyncio
async def test_postgres_enqueue_admission_uses_transaction_scoped_lock():
    executed = []

    class _Db:
        bind = type("_Bind", (), {"dialect": type("_Dialect", (), {"name": "postgresql"})()})()

        async def execute(self, statement):
            executed.append(statement)

    await _acquire_enqueue_lock(_Db(), "d1:42")

    assert len(executed) == 1


@pytest.mark.asyncio
async def test_non_postgres_enqueue_admission_is_a_noop():
    class _Db:
        bind = type("_Bind", (), {"dialect": type("_Dialect", (), {"name": "sqlite"})()})()

        async def execute(self, _statement):
            raise AssertionError("SQLite must not receive PostgreSQL advisory SQL")

    await _acquire_enqueue_lock(_Db(), "d1:42")
