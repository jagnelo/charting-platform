"""
Background data tasks — bulk historical fetches.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.services.market_data import fetch_ohlcv
from app.services.market_data_monitoring import build_shadow_report
from app.services.market_refresh_queue import (
    claim_refresh_jobs,
    complete_refresh_job,
    enqueue_refresh_job,
    retry_refresh_job,
)

logger = logging.getLogger(__name__)

# Timeframes to refresh nightly (recent bars only, not full re-fetch)
NIGHTLY_REFRESH_TIMEFRAMES: list[Timeframe] = [
    Timeframe.MN,
    Timeframe.W1,
    Timeframe.D1,
    Timeframe.H4,
    Timeframe.H1,
]


async def _get_newest_bar_ts(db, instrument_id: int, tf: Timeframe) -> datetime | None:
    from sqlalchemy import func

    result = await db.execute(
        select(func.max(OHLCVBar.ts)).where(
            OHLCVBar.instrument_id == instrument_id,
            OHLCVBar.timeframe == tf,
            OHLCVBar.is_adjusted.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def fetch_instrument_history(ctx: dict, instrument_id: int) -> dict:
    """Legacy entry-point — delegates to bulk_fetch_instrument."""
    async with AsyncSessionLocal() as db:
        instrument = await db.get(Instrument, instrument_id)
        if instrument is None:
            return {"error": f"Instrument {instrument_id} not found"}

        from app.services.bulk_fetch import bulk_fetch_instrument

        results = await bulk_fetch_instrument(db, instrument, redis=ctx.get("redis"))
        return {"instrument_id": instrument_id, "symbol": instrument.symbol, "results": results}


async def fetch_all_instruments_history(ctx: dict) -> dict:
    """
    Refresh OHLCV data for all active instruments in the DB.
    Intended to be run as a nightly scheduled task.
    Only fetches recent data (not full history) for efficiency.
    """
    async with AsyncSessionLocal() as db:
        instruments = (
            (
                await db.execute(
                    __import__("sqlalchemy", fromlist=["select"])
                    .select(Instrument)
                    .where(Instrument.is_active.is_(True))
                )
            )
            .scalars()
            .all()
        )

        logger.info(f"Refreshing data for {len(instruments)} instruments")
        total_bars = 0

        for instrument in instruments:
            for tf in NIGHTLY_REFRESH_TIMEFRAMES:
                try:
                    newest = await _get_newest_bar_ts(db, instrument.id, tf)
                    if newest is None:
                        # No data for this TF yet — bulk fetch handles this, skip
                        continue
                    # Small overlap buffer to catch any late-arriving bars
                    start = newest - timedelta(hours=1)
                    bars = await fetch_ohlcv(db, instrument, tf, start)
                    total_bars += len(bars)
                except Exception as e:
                    logger.error(f"Refresh failed {instrument.symbol} {tf.value}: {e}")

        return {"instruments_refreshed": len(instruments), "total_bars": total_bars}


async def enqueue_core_refresh_jobs(ctx: dict) -> dict:
    """Queue whole-universe D1 work without doing provider I/O in an evaluator."""

    async with AsyncSessionLocal() as db:
        instruments = (
            await db.execute(select(Instrument).where(Instrument.is_active.is_(True)))
        ).scalars().all()
        for instrument in instruments:
            await enqueue_refresh_job(
                db,
                request_key=f"d1:{instrument.id}",
                capability="price_history",
                instrument_id=instrument.id,
                timeframe=Timeframe.D1.value,
                priority=100,
                metadata_payload={"schedule": "core_session_daily"},
            )
        await db.commit()
        return {"queued": len(instruments), "mode": "enqueue_only"}


async def process_refresh_jobs(ctx: dict, limit: int = 50) -> dict:
    """Process queued requests with lease/retry telemetry and bounded fan-out."""

    async with AsyncSessionLocal() as db:
        jobs = await claim_refresh_jobs(db, limit=max(1, min(limit, 500)))
        completed = 0
        retried = 0
        for job in jobs:
            try:
                if job.instrument_id is None or not job.timeframe:
                    raise ValueError("refresh job has no instrument/timeframe")
                instrument = await db.get(Instrument, job.instrument_id)
                if instrument is None:
                    raise ValueError(f"instrument {job.instrument_id} no longer exists")
                timeframe = Timeframe(job.timeframe)
                start = job.start_at or (datetime.now(UTC) - timedelta(days=7))
                await fetch_ohlcv(db, instrument, timeframe, start, end=job.end_at)
                await complete_refresh_job(db, job)
                completed += 1
            except Exception as exc:
                await retry_refresh_job(db, job, str(exc))
                retried += 1
        await db.commit()
        return {"claimed": len(jobs), "completed": completed, "retried": retried}


async def run_market_data_shadow_report(ctx: dict) -> dict:
    """Produce the daily operator report without changing routing behavior."""

    async with AsyncSessionLocal() as db:
        report = await build_shadow_report(db)
        logger.info(
            "market-data shadow report: observations=%s discrepancies=%s rate=%.4f",
            report["observations"],
            report["discrepancies"],
            report["discrepancy_rate"],
        )
        return report
