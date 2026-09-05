"""Coalesced refresh queue primitives for broad and high-alert polling."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data_foundation import MarketRefreshJob


async def enqueue_refresh_job(
    db: AsyncSession,
    *,
    request_key: str,
    capability: str,
    instrument_id: int | None = None,
    timeframe: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    priority: int = 100,
    metadata_payload: dict | None = None,
    now: datetime | None = None,
) -> MarketRefreshJob:
    """Insert or coalesce a queued job, raising priority for urgent demand."""

    current = now or datetime.now(UTC)
    job = (
        await db.execute(select(MarketRefreshJob).where(MarketRefreshJob.request_key == request_key))
    ).scalar_one_or_none()
    if job is None:
        job = MarketRefreshJob(
            request_key=request_key,
            instrument_id=instrument_id,
            capability=capability,
            timeframe=timeframe,
            start_at=start_at,
            end_at=end_at,
            priority=priority,
            status="queued",
            attempts=0,
            next_attempt_at=current,
            metadata_payload=metadata_payload or {},
        )
        db.add(job)
    else:
        job.priority = min(job.priority, priority)
        job.status = "queued" if job.status in {"failed", "deferred", "expired"} else job.status
        job.next_attempt_at = min(job.next_attempt_at, current)
        job.metadata_payload = {**(job.metadata_payload or {}), **(metadata_payload or {})}
    await db.flush()
    return job


async def claim_refresh_jobs(
    db: AsyncSession,
    *,
    limit: int = 100,
    lease_seconds: int = 300,
    now: datetime | None = None,
) -> list[MarketRefreshJob]:
    """Claim due jobs with row locks so multiple workers do not duplicate work."""

    current = now or datetime.now(UTC)
    query = (
        select(MarketRefreshJob)
        .where(
            MarketRefreshJob.next_attempt_at <= current,
            or_(
                MarketRefreshJob.status == "queued",
                MarketRefreshJob.status.in_(["retry", "deferred"]),
                (MarketRefreshJob.status == "leased") & (MarketRefreshJob.leased_until < current),
            ),
        )
        .order_by(MarketRefreshJob.priority, MarketRefreshJob.next_attempt_at, MarketRefreshJob.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    jobs = (await db.execute(query)).scalars().all()
    for job in jobs:
        job.status = "leased"
        job.leased_until = current + timedelta(seconds=lease_seconds)
        job.attempts += 1
    if jobs:
        await db.flush()
    return list(jobs)


async def complete_refresh_job(db: AsyncSession, job: MarketRefreshJob) -> None:
    job.status = "completed"
    job.leased_until = None
    job.last_error = None
    await db.flush()


async def retry_refresh_job(
    db: AsyncSession,
    job: MarketRefreshJob,
    error: str,
    *,
    now: datetime | None = None,
    max_backoff_seconds: int = 3600,
    retry_at: datetime | None = None,
) -> None:
    current = now or datetime.now(UTC)
    backoff = min(max_backoff_seconds, 2 ** min(job.attempts, 10))
    is_quota_defer = retry_at is not None
    job.status = "deferred" if is_quota_defer else "retry"
    job.leased_until = None
    job.last_error = error[:2000]
    backoff_at = current + timedelta(seconds=backoff)
    job.next_attempt_at = max(backoff_at, retry_at) if retry_at is not None else backoff_at
    job.metadata_payload = {
        **(job.metadata_payload or {}),
        "defer_reason": "provider_reset" if is_quota_defer else None,
        "provider_retry_at": retry_at.isoformat() if retry_at else None,
    }
    await db.flush()
