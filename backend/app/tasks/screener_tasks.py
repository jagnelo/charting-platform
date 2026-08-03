"""Background tasks for screener execution."""

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models.screener import ScreenerDefinition, ScreenerResult
from app.services.screener_engine import (
    collect_python_screener_result,
    queue_python_screener_run,
    run_screener,
)


async def _run_screener_or_queue(db, screener):
    if isinstance(screener.conditions, dict) and screener.conditions.get("type") == "python_condition":
        return await queue_python_screener_run(db, screener)
    return await run_screener(db, screener)


async def _collect_pending_python_results(db, screener):
    if not isinstance(screener.conditions, dict) or screener.conditions.get("type") != "python_condition":
        return
    results = (
        await db.execute(
            select(ScreenerResult)
            .where(ScreenerResult.screener_id == screener.id)
            .order_by(ScreenerResult.run_at.desc())
            .limit(10)
        )
    ).scalars().all()
    for result in results:
        await collect_python_screener_result(db, result)

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

        if screener is None:
            return {"error": f"Screener {screener_id} not found"}
        result = await _run_screener_or_queue(db, screener)
        coverage = result.result_data.get("_coverage", {}) if isinstance(result.result_data, dict) else {}
        return {
            "screener_id": screener_id,
            "matched": len(result.matched_ids),
            "total_scanned": coverage.get("universe_count", len(result.matched_ids)),
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
                            ScreenerDefinition.schedule.isnot(None),
                        )
                    )
                )
                .scalars()
                .all()
            )

            ran = 0
            for screener in screeners:
                try:
                    await _collect_pending_python_results(db, screener)
                    latest_run = (
                        await db.execute(
                            select(func.max(ScreenerResult.run_at)).where(
                                ScreenerResult.screener_id == screener.id
                            )
                        )
                    ).scalar_one()
                    cron = croniter(
                        screener.schedule, latest_run or datetime(2000, 1, 1)
                    )
                    if cron.get_next(datetime) <= datetime.now(UTC):
                        await _run_screener_or_queue(db, screener)
                        ran += 1
                except Exception as e:
                    logger.error(f"Scheduled screener {screener.id} failed: {e}")

            return {"ran": ran}
        except ImportError:
            logger.debug("croniter not installed — scheduled screeners skipped")
            return {"ran": 0, "note": "croniter not installed"}
