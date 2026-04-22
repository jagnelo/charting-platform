"""Scheduled/operator tasks for provider-backed instrument universe maintenance."""

import logging

from app.config import settings
from app.database import AsyncSessionLocal
from app.services.instrument_sync import run_tracked_sync

logger = logging.getLogger(__name__)


async def seed_universe_task(ctx: dict) -> dict:
    """Weekly broad discovery pass using the configured universe provider."""
    async with AsyncSessionLocal() as db:
        return await run_tracked_sync(db, "seed-universe")


async def sync_instruments_task(ctx: dict, limit: int | None = None) -> dict:
    """Daily capped metadata refresh across the stalest known instruments."""
    async with AsyncSessionLocal() as db:
        cap = limit if limit is not None else settings.INSTRUMENT_DAILY_METADATA_CAP
        return await run_tracked_sync(db, "sync-instruments", limit=cap)


async def bootstrap_ids_task(ctx: dict, limit: int | None = None) -> dict:
    """Daily capped stable identifier enrichment for instruments missing external IDs."""
    async with AsyncSessionLocal() as db:
        cap = limit if limit is not None else settings.INSTRUMENT_DAILY_IDENTIFIER_CAP
        return await run_tracked_sync(db, "bootstrap-ids", limit=cap)


async def scheduled_weekly_seed(ctx: dict) -> dict:
    if not settings.INSTRUMENT_SYNC_SCHEDULE_ENABLED:
        logger.info("Instrument sync schedule disabled; skipping weekly seed")
        return {"skipped": True, "reason": "schedule disabled"}
    return await seed_universe_task(ctx)


async def scheduled_daily_metadata_sync(ctx: dict) -> dict:
    if not settings.INSTRUMENT_SYNC_SCHEDULE_ENABLED:
        logger.info("Instrument sync schedule disabled; skipping metadata sync")
        return {"skipped": True, "reason": "schedule disabled"}
    return await sync_instruments_task(ctx)


async def scheduled_daily_id_bootstrap(ctx: dict) -> dict:
    if not settings.INSTRUMENT_SYNC_SCHEDULE_ENABLED:
        logger.info("Instrument sync schedule disabled; skipping stable ID bootstrap")
        return {"skipped": True, "reason": "schedule disabled"}
    return await bootstrap_ids_task(ctx)
