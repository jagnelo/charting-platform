"""
Background data tasks — bulk historical fetches.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.services.derived_timeframes import materialize_derived_timeframes
from app.services.market_data import fetch_ohlcv

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
        derived_bars = {Timeframe.W1.value: 0, Timeframe.MN.value: 0}

        for instrument in instruments:
            has_daily_history = False
            for tf in NIGHTLY_REFRESH_TIMEFRAMES:
                try:
                    newest = await _get_newest_bar_ts(db, instrument.id, tf)
                    if newest is None:
                        # No data for this TF yet — bulk fetch handles this, skip
                        continue
                    if tf == Timeframe.D1:
                        has_daily_history = True
                    # Small overlap buffer to catch any late-arriving bars
                    start = newest - timedelta(hours=1)
                    bars = await fetch_ohlcv(db, instrument, tf, start)
                    total_bars += len(bars)
                except Exception as e:
                    logger.error(f"Refresh failed {instrument.symbol} {tf.value}: {e}")

            # Public providers often expose D1 while omitting W1/MN.  The
            # per-timeframe loop intentionally skips a missing coarse cache,
            # so rebuild those views from the complete persisted D1 history
            # after the refresh.  This keeps the scheduled path aligned with
            # the canonical bulk-fetch contract without issuing extra provider
            # requests or inventing observations.
            if has_daily_history:
                try:
                    derived = await materialize_derived_timeframes(db, instrument.id)
                    for timeframe in (Timeframe.W1.value, Timeframe.MN.value):
                        derived_bars[timeframe] += int(derived.get(timeframe, 0))
                    await db.commit()
                except Exception as e:
                    await db.rollback()
                    logger.error(f"Coarse history materialization failed {instrument.symbol}: {e}")

        return {
            "instruments_refreshed": len(instruments),
            "total_bars": total_bars,
            "derived_bars": derived_bars,
        }
