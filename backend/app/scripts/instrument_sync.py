"""
Operator-only instrument universe maintenance.

Examples:
  uv run python -m app.scripts.instrument_sync seed-universe
  uv run python -m app.scripts.instrument_sync sync-instruments
  uv run python -m app.scripts.instrument_sync bootstrap-ids
"""

import argparse
import asyncio
import logging

from app.database import AsyncSessionLocal
from app.services.instrument_sync import run_tracked_sync

logger = logging.getLogger(__name__)


async def _run(action: str, limit: int | None) -> dict:
    async with AsyncSessionLocal() as db:
        return await run_tracked_sync(db, action, limit=limit)
    raise ValueError(f"Unknown action: {action}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Instrument universe maintenance")
    parser.add_argument(
        "action",
        choices=("seed-universe", "sync-instruments", "bootstrap-ids"),
        help="Maintenance action to run",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum instruments to process for capped operations",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    result = asyncio.run(_run(args.action, args.limit))
    logger.info("%s complete: %s", args.action, result)


if __name__ == "__main__":
    main()
