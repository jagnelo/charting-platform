"""
ARQ worker — async task queue backed by Redis.
Run with: python -m app.workers.arq_worker
Or via the dedicated Docker container.

Tasks defined here are enqueued by routers/services and executed here
in separate worker processes, keeping the FastAPI server non-blocking.
"""

import logging
from datetime import UTC

from arq.connections import RedisSettings

from app.config import settings

logger = logging.getLogger(__name__)


# ── Task implementations ──────────────────────────────────────────────────────


async def task_bulk_fetch_instrument(
    ctx: dict, instrument_id: int, timeframes: list[str] | None = None
):
    """
    ARQ task: pull maximum available history for one instrument.
    Enqueued automatically when a new instrument is registered.
    """
    from app.database import AsyncSessionLocal
    from app.models.instrument import Instrument
    from app.models.ohlcv import Timeframe
    from app.services.bulk_fetch import bulk_fetch_instrument

    async with AsyncSessionLocal() as db:
        instrument = await db.get(Instrument, instrument_id)
        if instrument is None:
            logger.warning(f"bulk_fetch: instrument {instrument_id} not found")
            return

        tf_list = [Timeframe(tf) for tf in timeframes] if timeframes else None
        summary = await bulk_fetch_instrument(db, instrument, tf_list, redis=ctx.get("redis"))
        logger.info(f"bulk_fetch complete for {instrument.symbol}: {summary}")
        return summary


async def task_run_screener(ctx: dict, screener_id: int):
    """ARQ task: run a screener by ID and persist results."""
    from app.database import AsyncSessionLocal
    from app.models.screener import ScreenerDefinition
    from app.services.screener_engine import run_screener

    async with AsyncSessionLocal() as db:
        screener = await db.get(ScreenerDefinition, screener_id)
        if screener is None:
            logger.warning(f"run_screener: screener {screener_id} not found")
            return
        result = await run_screener(db, screener)
        return {"matched": len(result.matched_ids), "duration_ms": result.duration_ms}


async def task_refresh_instrument_data(ctx: dict, instrument_id: int, timeframe: str):
    """ARQ task: refresh recent bars for one instrument/timeframe."""
    from datetime import datetime, timedelta

    from app.database import AsyncSessionLocal
    from app.models.instrument import Instrument
    from app.models.ohlcv import Timeframe
    from app.services.market_data import fetch_ohlcv

    async with AsyncSessionLocal() as db:
        instrument = await db.get(Instrument, instrument_id)
        if instrument is None:
            return
        tf = Timeframe(timeframe)
        start = datetime.now(UTC) - timedelta(days=7)
        bars = await fetch_ohlcv(db, instrument, tf, start)
        return {"bars_fetched": len(bars)}


# ── Scheduled tasks (cron) ───────────────────────────────────────────────────


async def scheduled_alert_check(ctx: dict):
    """Runs alert engine on a schedule via ARQ cron (alternative to APScheduler)."""
    from app.services.alert_engine import _run_async

    await _run_async()


# ── Worker settings ───────────────────────────────────────────────────────────


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    functions = [
        task_bulk_fetch_instrument,
        task_run_screener,
        task_refresh_instrument_data,
    ]
    # Optional: move alert checking entirely to ARQ cron
    # cron_jobs = [cron(scheduled_alert_check, minute=set(range(0, 60)))]
    max_jobs = 4
    job_timeout = 600  # 10 minutes max per job
    keep_result = 3600  # keep results for 1 hour


if __name__ == "__main__":
    from arq import run_worker

    run_worker(WorkerSettings)
