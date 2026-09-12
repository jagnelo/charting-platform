"""Coalesced refresh queue primitives for broad and high-alert polling."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data_foundation import MarketRefreshJob
from app.providers.errors import redact_provider_message


class RefreshLeaseLostError(RuntimeError):
    """Raised when a worker tries to mutate a job it no longer owns."""


async def _acquire_enqueue_lock(db: AsyncSession, request_key: str) -> None:
    """Serialize same-key enqueue admission across PostgreSQL workers.

    The unique request-key constraint remains the durable backstop. The
    transaction-scoped advisory lock prevents the common select-then-insert
    race before that constraint has to abort a worker's surrounding
    transaction. SQLite and lightweight unit adapters intentionally remain
    lock-free; their database constraint still preserves uniqueness.
    """

    bind = getattr(db, "bind", None)
    if bind is None:
        bind = getattr(getattr(db, "sync_session", None), "bind", None)
    if getattr(getattr(bind, "dialect", None), "name", None) != "postgresql":
        return
    digest = hashlib.sha256(request_key.encode("utf-8")).digest()
    advisory_key = int.from_bytes(digest[:8], byteorder="big", signed=True)
    await db.execute(select(func.pg_advisory_xact_lock(advisory_key)))


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
    await _acquire_enqueue_lock(db, request_key)
    job = (
        await db.execute(
            select(MarketRefreshJob).where(MarketRefreshJob.request_key == request_key)
        )
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
        job.lease_token = uuid4().hex
        job.attempts += 1
        if job.started_at is None:
            job.started_at = current
        job.finished_at = None
    if jobs:
        await db.flush()
    return list(jobs)


async def complete_refresh_job(
    db: AsyncSession,
    job: MarketRefreshJob,
    *,
    now: datetime | None = None,
    lease_token: str | None = None,
    result_summary: dict | None = None,
) -> None:
    """Complete a job only while the caller's durable lease is still valid."""

    token = lease_token or job.lease_token
    current = now or datetime.now(UTC)
    summary = {"outcome": "completed", **(result_summary or {})}
    if not token:
        raise RefreshLeaseLostError(f"refresh job {job.id} has no lease token")
    result = await db.execute(
        update(MarketRefreshJob)
        .where(
            MarketRefreshJob.id == job.id,
            MarketRefreshJob.status == "leased",
            MarketRefreshJob.lease_token == token,
            or_(
                MarketRefreshJob.leased_until.is_(None),
                MarketRefreshJob.leased_until >= current,
            ),
        )
        .values(
            status="completed",
            leased_until=None,
            lease_token=None,
            last_error=None,
            finished_at=current,
            result_summary=summary,
        )
    )
    if getattr(result, "rowcount", None) != 1:
        raise RefreshLeaseLostError(f"refresh job {job.id} lease is no longer valid")
    job.status = "completed"
    job.leased_until = None
    job.lease_token = None
    job.last_error = None
    job.finished_at = current
    job.result_summary = summary


async def retry_refresh_job(
    db: AsyncSession,
    job: MarketRefreshJob,
    error: str,
    *,
    now: datetime | None = None,
    max_backoff_seconds: int = 3600,
    retry_at: datetime | None = None,
    lease_token: str | None = None,
    result_summary: dict | None = None,
) -> None:
    current = now or datetime.now(UTC)
    backoff = min(max_backoff_seconds, 2 ** min(job.attempts, 10))
    is_quota_defer = retry_at is not None
    backoff_at = current + timedelta(seconds=backoff)
    next_attempt_at = max(backoff_at, retry_at) if retry_at is not None else backoff_at
    metadata_payload = {
        **(job.metadata_payload or {}),
        "defer_reason": "provider_reset" if is_quota_defer else None,
        "provider_retry_at": retry_at.isoformat() if retry_at else None,
    }
    safe_error = redact_provider_message(error)[:2000]
    summary = {
        "outcome": "deferred" if is_quota_defer else "retry",
        "error": safe_error,
        "provider_retry_at": retry_at.isoformat() if retry_at else None,
        **(result_summary or {}),
    }
    token = lease_token or job.lease_token
    if not token:
        raise RefreshLeaseLostError(f"refresh job {job.id} has no lease token")
    result = await db.execute(
        update(MarketRefreshJob)
        .where(
            MarketRefreshJob.id == job.id,
            MarketRefreshJob.status == "leased",
            MarketRefreshJob.lease_token == token,
            or_(
                MarketRefreshJob.leased_until.is_(None),
                MarketRefreshJob.leased_until >= current,
            ),
        )
        .values(
            status="deferred" if is_quota_defer else "retry",
            leased_until=None,
            lease_token=None,
            last_error=safe_error,
            next_attempt_at=next_attempt_at,
            metadata_payload=metadata_payload,
            finished_at=current,
            result_summary=summary,
        )
    )
    if getattr(result, "rowcount", None) != 1:
        raise RefreshLeaseLostError(f"refresh job {job.id} lease is no longer valid")
    job.status = "deferred" if is_quota_defer else "retry"
    job.leased_until = None
    job.lease_token = None
    job.last_error = safe_error
    job.next_attempt_at = next_attempt_at
    job.metadata_payload = metadata_payload
    job.finished_at = current
    job.result_summary = summary
