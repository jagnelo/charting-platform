"""Scheduled maintenance task: merge provable duplicate instruments."""

from __future__ import annotations

import logging

from app.config import settings
from app.database import AsyncSessionLocal
from app.services.instrument_dedup import merge_duplicate_instruments

logger = logging.getLogger(__name__)


async def merge_duplicate_instruments_task(ctx: dict | None = None) -> dict:
    if not settings.INSTRUMENT_DUPLICATE_MERGE_ENABLED:
        return {"skipped": True, "reason": "duplicate instrument merge disabled"}
    summary = await merge_duplicate_instruments(
        AsyncSessionLocal,
        max_pairs=int(settings.INSTRUMENT_DUPLICATE_MERGE_MAX_PAIRS),
        max_seconds=float(settings.INSTRUMENT_DUPLICATE_MERGE_MAX_SECONDS),
        evidence=str(settings.INSTRUMENT_DUPLICATE_MERGE_EVIDENCE).split(","),
    )
    if summary["merged"] or summary["failed"] or summary["skipped"]:
        logger.info("duplicate instrument merge pass: %s", summary)
    return summary


async def prune_refresh_tracking_task(ctx: dict | None = None) -> dict:
    """Delete finished data-preparation tracking parents (bounded, idempotent)."""

    from app.services.market_refresh_retention import prune_finished_tracking_parents

    if not settings.MARKET_REFRESH_TRACKING_RETENTION_ENABLED:
        return {"skipped": True, "reason": "tracking retention disabled"}
    summary = await prune_finished_tracking_parents(
        AsyncSessionLocal,
        retention_days=float(settings.MARKET_REFRESH_TRACKING_RETENTION_DAYS),
        batch_size=int(settings.MARKET_REFRESH_TRACKING_RETENTION_BATCH_SIZE),
        max_seconds=float(settings.MARKET_REFRESH_TRACKING_RETENTION_MAX_SECONDS),
    )
    if summary["deleted"]:
        logger.info("refresh tracking retention pass: %s", summary)
    return summary
