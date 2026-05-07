"""Scheduled/operator tasks for technical radar scans."""

from app.database import AsyncSessionLocal
from app.services.radar_engine import run_radar_scan


async def run_radar_scan_task(ctx: dict) -> dict:
    async with AsyncSessionLocal() as db:
        run = await run_radar_scan(db)
        return {
            "run_id": run.id,
            "status": run.status.value,
            "evaluated_count": run.evaluated_count,
            "detection_count": run.detection_count,
        }
