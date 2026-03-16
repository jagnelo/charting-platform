"""
Background data tasks — bulk historical fetches.
"""

import logging
from datetime import UTC, datetime, timedelta

from app.database import AsyncSessionLocal
from app.models.instrument import Instrument
from app.models.ohlcv import Timeframe
from app.services.market_data import fetch_ohlcv

logger = logging.getLogger(__name__)

# Timeframes to fetch for a full history pull, and their lookback periods
FULL_HISTORY_TIMEFRAMES: list[tuple[Timeframe, int]] = [
    (Timeframe.MN, 365 * 30),  # monthly — 30 years
    (Timeframe.W1, 365 * 20),  # weekly  — 20 years
    (Timeframe.D1, 365 * 20),  # daily   — 20 years
    (Timeframe.H4, 365 * 2),  # 4h      — 2 years (yfinance limit)
    (Timeframe.H1, 365 * 2),  # 1h      — 2 years
    (Timeframe.M30, 60),  # 30m     — 60 days
    (Timeframe.M15, 60),  # 15m     — 60 days
    (Timeframe.M5, 60),  # 5m      — 60 days
]


async def fetch_instrument_history(ctx: dict, instrument_id: int) -> dict:
    """
    Fetch all available historical OHLCV data for a single instrument
    across all supported timeframes.
    Called automatically when a new instrument is registered,
    and can be triggered manually.
    """
    async with AsyncSessionLocal() as db:
        instrument = await db.get(Instrument, instrument_id)
        if instrument is None:
            return {"error": f"Instrument {instrument_id} not found"}

        logger.info(f"Starting full history fetch for {instrument.symbol}")
        results = {}

        for tf, lookback_days in FULL_HISTORY_TIMEFRAMES:
            start = datetime.now(UTC) - timedelta(days=lookback_days)
            try:
                bars = await fetch_ohlcv(db, instrument, tf, start)
                results[tf.value] = len(bars)
                logger.info(f"  {instrument.symbol} {tf.value}: {len(bars)} bars")
            except Exception as e:
                logger.error(f"  {instrument.symbol} {tf.value} failed: {e}")
                results[tf.value] = f"error: {e}"

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
            for tf, _ in FULL_HISTORY_TIMEFRAMES[:5]:  # D1 and above for nightly refresh
                try:
                    start = datetime.now(UTC) - timedelta(days=30)
                    bars = await fetch_ohlcv(db, instrument, tf, start)
                    total_bars += len(bars)
                except Exception as e:
                    logger.error(f"Refresh failed {instrument.symbol} {tf.value}: {e}")

        return {"instruments_refreshed": len(instruments), "total_bars": total_bars}
