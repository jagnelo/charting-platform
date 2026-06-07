"""
ARQ worker — async task queue backed by Redis.
Run with: python -m app.workers.arq_worker
Or via the dedicated Docker container.

Tasks defined here are enqueued by routers/services and executed here
in separate worker processes, keeping the FastAPI server non-blocking.
"""

import logging
from datetime import UTC

from arq import cron
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


async def scheduled_weekly_seed(ctx: dict):
    if not settings.INSTRUMENT_SYNC_SCHEDULE_ENABLED:
        logger.info("Instrument sync schedule disabled; skipping weekly seed")
        return {"skipped": True, "reason": "schedule disabled"}
    from app.tasks.instrument_sync_tasks import seed_universe_task

    return await seed_universe_task(ctx)


async def scheduled_daily_metadata_sync(ctx: dict):
    if not settings.INSTRUMENT_SYNC_SCHEDULE_ENABLED:
        logger.info("Instrument sync schedule disabled; skipping metadata sync")
        return {"skipped": True, "reason": "schedule disabled"}
    from app.tasks.instrument_sync_tasks import sync_instruments_task

    return await sync_instruments_task(ctx)


async def scheduled_daily_id_bootstrap(ctx: dict):
    if not settings.INSTRUMENT_SYNC_SCHEDULE_ENABLED:
        logger.info("Instrument sync schedule disabled; skipping stable ID bootstrap")
        return {"skipped": True, "reason": "schedule disabled"}
    from app.tasks.instrument_sync_tasks import bootstrap_ids_task

    return await bootstrap_ids_task(ctx)


async def scheduled_etf_holdings_refresh(ctx: dict):
    from app.tasks.etf_holdings_tasks import refresh_etf_holdings_task

    return await refresh_etf_holdings_task(ctx)


async def scheduled_etf_holdings_sec_backfill(ctx: dict):
    from app.tasks.etf_holdings_tasks import backfill_sec_nport_holdings_task

    return await backfill_sec_nport_holdings_task(ctx)


# ── Worker settings ───────────────────────────────────────────────────────────


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    functions = [
        task_bulk_fetch_instrument,
        task_run_screener,
        task_refresh_instrument_data,
        scheduled_weekly_seed,
        scheduled_daily_metadata_sync,
        scheduled_daily_id_bootstrap,
        scheduled_etf_holdings_refresh,
        scheduled_etf_holdings_sec_backfill,
    ]
    cron_jobs = (
        [
            cron(scheduled_weekly_seed, weekday=6, hour=2, minute=0),
            cron(scheduled_daily_metadata_sync, hour=3, minute=0),
            cron(scheduled_daily_id_bootstrap, hour=4, minute=0),
            cron(scheduled_etf_holdings_refresh, weekday=6, hour=5, minute=0),
            cron(scheduled_etf_holdings_sec_backfill, weekday=6, hour=6, minute=0),
        ]
        if (
            settings.INSTRUMENT_SYNC_SCHEDULE_ENABLED
            or settings.ETF_HOLDINGS_REFRESH_ENABLED
            or settings.ETF_HOLDINGS_SEC_BACKFILL_ENABLED
        )
        else []
    )
    max_jobs = 4
    job_timeout = 600  # 10 minutes max per job
    keep_result = 3600  # keep results for 1 hour


if __name__ == "__main__":
    from arq import run_worker

    run_worker(WorkerSettings)
