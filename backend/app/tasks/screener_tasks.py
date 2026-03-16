"""Background tasks for screener execution."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.screener import ScreenerDefinition
from app.services.screener_engine import run_screener

logger = logging.getLogger(__name__)


async def run_screener_task(ctx: dict, screener_id: int, user_id: int) -> dict:
    """Run a specific screener and return the result summary."""
    async with AsyncSessionLocal() as db:
        screener = (
            await db.execute(
                select(ScreenerDefinition).where(
                    ScreenerDefinition.id == screener_id, ScreenerDefinition.user_id == user_id
                )
            )
        ).scalar_one_or_none()

        if screener is None:
            return {"error": f"Screener {screener_id} not found"}

        result = await run_screener(db, screener)
        return {
            "screener_id": screener_id,
            "matched": len(result.matched_instrument_ids),
            "total_scanned": result.total_scanned,
            "duration_ms": result.duration_ms,
            "result_id": result.id,
        }


async def run_all_scheduled_screeners(ctx: dict) -> dict:
    """
    Check all screeners with a schedule_cron and run any that are due.
    Called every minute by APScheduler.
    """
    from croniter import croniter  # optional dep — gracefully skip if missing

    async with AsyncSessionLocal() as db:
        try:
            screeners = (
                (
                    await db.execute(
                        select(ScreenerDefinition).where(
                            ScreenerDefinition.is_active.is_(True),
                            ScreenerDefinition.schedule_cron.isnot(None),
                        )
                    )
                )
                .scalars()
                .all()
            )

            ran = 0
            for screener in screeners:
                try:
                    cron = croniter(
                        screener.schedule_cron, screener.last_run_at or datetime(2000, 1, 1)
                    )
                    if cron.get_next(datetime) <= datetime.now(UTC):
                        await run_screener(db, screener)
                        ran += 1
                except Exception as e:
                    logger.error(f"Scheduled screener {screener.id} failed: {e}")

            return {"ran": ran}
        except ImportError:
            logger.debug("croniter not installed — scheduled screeners skipped")
            return {"ran": 0, "note": "croniter not installed"}
