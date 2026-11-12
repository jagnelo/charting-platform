from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from app.services.market_refresh_queue import (
    DEPENDENCY_PENDING_ERROR,
    RefreshLeaseLostError,
    _acquire_enqueue_lock,
    claim_refresh_jobs,
    complete_refresh_job,
    core_refresh_request_key,
    enqueue_refresh_job,
    retry_refresh_job,
)
from tests.unit.conftest import AsyncSessionAdapter


def test_core_refresh_request_key_is_idempotent_per_utc_run_date():
    first = core_refresh_request_key(42, run_date=date(2026, 9, 17))
    duplicate = core_refresh_request_key(42, run_date=date(2026, 9, 17))
    next_day = core_refresh_request_key(42, run_date=date(2026, 9, 18))

    assert first == duplicate == "d1:42:2026-09-17"
    assert next_day == "d1:42:2026-09-18"
    assert first != next_day


@pytest.mark.asyncio
async def test_completed_core_refresh_can_run_again_on_the_next_utc_date(db, instrument):
    async_db = AsyncSessionAdapter(db)
    first_date = date(2026, 9, 17)
    first_now = datetime(2026, 9, 17, 5, tzinfo=UTC)
    first = await enqueue_refresh_job(
        async_db,
        request_key=core_refresh_request_key(instrument.id, run_date=first_date),
        capability="price_history",
        instrument_id=instrument.id,
        timeframe="D1",
        metadata_payload={"schedule": "core_session_daily", "run_date": first_date.isoformat()},
        now=first_now,
    )
    claimed = (await claim_refresh_jobs(async_db, now=first_now))[0]
    await complete_refresh_job(async_db, claimed, now=first_now)

    second_date = date(2026, 9, 18)
    second_now = datetime(2026, 9, 18, 5, tzinfo=UTC)
    second = await enqueue_refresh_job(
        async_db,
        request_key=core_refresh_request_key(instrument.id, run_date=second_date),
        capability="price_history",
        instrument_id=instrument.id,
        timeframe="D1",
        metadata_payload={"schedule": "core_session_daily", "run_date": second_date.isoformat()},
        now=second_now,
    )

    assert second.id != first.id
    assert second.status == "queued"
    assert (await claim_refresh_jobs(async_db, now=second_now))[0].id == second.id


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
async def test_known_provider_retry_is_not_extended_by_generic_attempt_backoff(db):
    async_db = AsyncSessionAdapter(db)
    now = datetime(2026, 9, 4, 12, tzinfo=UTC)
    retry_at = now + timedelta(seconds=5)
    job = await enqueue_refresh_job(
        async_db,
        request_key="d1:short-known-reset",
        capability="price_history",
        now=now,
    )
    await claim_refresh_jobs(async_db, now=now)
    job.attempts = 10

    await retry_refresh_job(
        async_db,
        job,
        "known local application bucket refill",
        now=now,
        retry_at=retry_at,
    )

    assert job.status == "deferred"
    assert job.next_attempt_at == retry_at
    assert job.metadata_payload["provider_retry_at"] == retry_at.isoformat()


@pytest.mark.asyncio
async def test_preparation_join_preserves_live_provider_wait_but_legacy_join_requeues(db):
    async_db = AsyncSessionAdapter(db)
    now = datetime(2026, 9, 4, 12, tzinfo=UTC)
    retry_at = now + timedelta(minutes=7)
    job = await enqueue_refresh_job(
        async_db,
        request_key="prep-history:quota",
        capability="price_history",
        priority=100,
        now=now,
    )
    claimed = (await claim_refresh_jobs(async_db, now=now))[0]
    await retry_refresh_job(
        async_db,
        claimed,
        "provider rate limit",
        now=now,
        retry_at=retry_at,
    )

    joined = await enqueue_refresh_job(
        async_db,
        request_key="prep-history:quota",
        capability="price_history",
        priority=10,
        metadata_payload={"data_preparation_child": {"parent_refs": [{"parent_job_id": 7}]}},
        now=now + timedelta(seconds=1),
        preserve_deferred_deadline=True,
    )
    assert joined.id == job.id
    assert joined.priority == 10
    assert joined.status == "deferred"
    assert joined.next_attempt_at == retry_at
    assert joined.metadata_payload["defer_reason"] == "provider_reset"

    # Existing non-preparation callers retain their established explicit
    # requeue semantics; only shared preparation joins respect a live hold.
    legacy_join = await enqueue_refresh_job(
        async_db,
        request_key="prep-history:quota",
        capability="price_history",
        priority=1,
        now=now + timedelta(seconds=2),
    )
    assert legacy_join.id == job.id
    assert legacy_join.status == "queued"
    assert legacy_join.next_attempt_at == now + timedelta(seconds=2)


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


async def _dependency_pair(async_db, *, dependent_priority=10, prerequisite_priority=100):
    """Return (prerequisite, dependent) where dependent waits on prerequisite."""

    prerequisite = await enqueue_refresh_job(
        async_db,
        request_key=f"wake-prereq:{uuid4().hex}",
        capability="instrument_metadata",
        priority=prerequisite_priority,
        now=_WAKE_NOW,
    )
    dependent = await enqueue_refresh_job(
        async_db,
        request_key=f"wake-dependent:{uuid4().hex}",
        capability="price_history",
        timeframe="D1",
        priority=dependent_priority,
        metadata_payload={
            "data_preparation_child": {"wait_for_job_ids": [prerequisite.id]},
        },
        now=_WAKE_NOW,
    )
    return prerequisite, dependent


_WAKE_NOW = datetime(2026, 11, 10, 12, tzinfo=UTC)


@pytest.mark.asyncio
async def test_prerequisite_completion_wakes_dependent_before_fixed_recheck(db):
    async_db = AsyncSessionAdapter(db)
    prerequisite, dependent = await _dependency_pair(async_db)
    # The dependent is leased first (higher priority) and then deferred on its
    # prerequisite with the fixed 20 second recheck.
    leased_dependent = (await claim_refresh_jobs(async_db, limit=1, now=_WAKE_NOW))[0]
    assert leased_dependent.id == dependent.id
    await retry_refresh_job(
        async_db,
        leased_dependent,
        DEPENDENCY_PENDING_ERROR,
        retry_at=_WAKE_NOW + timedelta(seconds=20),
        lease_token=leased_dependent.lease_token,
        now=_WAKE_NOW,
    )
    assert dependent.status == "deferred"

    prerequisite_now = _WAKE_NOW + timedelta(seconds=3)
    leased_prerequisite = (await claim_refresh_jobs(async_db, limit=1, now=prerequisite_now))[0]
    assert leased_prerequisite.id == prerequisite.id
    await complete_refresh_job(async_db, leased_prerequisite, now=prerequisite_now)

    assert dependent.next_attempt_at == prerequisite_now
    claimed = await claim_refresh_jobs(async_db, limit=1, now=prerequisite_now)
    assert [job.id for job in claimed] == [dependent.id]


@pytest.mark.asyncio
async def test_completion_does_not_wake_quota_deferred_or_unrelated_dependents(db):
    async_db = AsyncSessionAdapter(db)
    prerequisite, dependent = await _dependency_pair(async_db)
    quota_retry_at = _WAKE_NOW + timedelta(hours=1)
    unrelated = await enqueue_refresh_job(
        async_db,
        request_key=f"wake-unrelated:{uuid4().hex}",
        capability="price_history",
        timeframe="D1",
        priority=10,
        metadata_payload={"data_preparation_child": {"wait_for_job_ids": [999_999]}},
        now=_WAKE_NOW,
    )
    leased_dependent = (await claim_refresh_jobs(async_db, limit=1, now=_WAKE_NOW))[0]
    # A provider quota reset is a deferral too, but not a dependency wait.
    await retry_refresh_job(
        async_db,
        leased_dependent,
        "provider quota reset",
        retry_at=quota_retry_at,
        lease_token=leased_dependent.lease_token,
        now=_WAKE_NOW,
    )
    leased_unrelated = (await claim_refresh_jobs(async_db, limit=1, now=_WAKE_NOW))[0]
    assert leased_unrelated.id == unrelated.id
    await retry_refresh_job(
        async_db,
        leased_unrelated,
        DEPENDENCY_PENDING_ERROR,
        retry_at=_WAKE_NOW + timedelta(seconds=20),
        lease_token=leased_unrelated.lease_token,
        now=_WAKE_NOW,
    )

    prerequisite_now = _WAKE_NOW + timedelta(seconds=3)
    leased_prerequisite = (await claim_refresh_jobs(async_db, limit=1, now=prerequisite_now))[0]
    assert leased_prerequisite.id == prerequisite.id
    await complete_refresh_job(async_db, leased_prerequisite, now=prerequisite_now)

    assert dependent.next_attempt_at == quota_retry_at
    assert unrelated.next_attempt_at == _WAKE_NOW + timedelta(seconds=20)


@pytest.mark.asyncio
async def test_visible_metadata_prerequisite_is_leased_ahead_of_background_work(db):
    async_db = AsyncSessionAdapter(db)
    await enqueue_refresh_job(
        async_db,
        request_key=f"background-scan:{uuid4().hex}",
        capability="price_history",
        timeframe="D1",
        priority=100,
        now=_WAKE_NOW - timedelta(minutes=5),
    )
    visible_metadata = await enqueue_refresh_job(
        async_db,
        request_key=f"visible-metadata:{uuid4().hex}",
        capability="instrument_metadata",
        priority=10,
        now=_WAKE_NOW,
    )

    claimed = await claim_refresh_jobs(async_db, limit=1, now=_WAKE_NOW)
    assert [job.id for job in claimed] == [visible_metadata.id]
