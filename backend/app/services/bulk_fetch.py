"""
Bulk historical data fetcher.

Pulls the maximum available OHLCV history for an instrument from the configured
data source and stores it in the local DB for all supported timeframes.

Design principles:
  - Source-agnostic: no hardcoded "30 year" or "yfinance limit" assumptions.
  - We always attempt to start from EPOCH (Unix timestamp 0) and let the data
    source tell us how far back it can actually go.
  - If a source returns nothing for a timeframe after coarser timeframes have
    returned data, we record that fact and stop asking, accepting the source
    simply doesn't provide that resolution that far back.
  - Progress is tracked in Redis so the frontend can surface meaningful UX.
  - Timeframes are processed one at a time with a configurable inter-request
    delay to respect data-source rate limits.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pandas as pd
import yfinance as yf
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_source import DataSource
from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.services.market_data import (
    TF_TO_YF,
    YFINANCE_SOURCE_NAME,
    _ticker_for_instrument,
)

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# The earliest timestamp we will ever request.  The data source returns whatever
# it actually has; we never assume a fixed lookback window.
EPOCH_START = datetime(1970, 1, 1, tzinfo=UTC)

# Ordered coarsest→finest.  Coarser TFs are fetched first because they carry
# deeper history and their emptiness is a reliable signal that finer TFs will
# also be empty for a given period.
BULK_FETCH_TIMEFRAMES: list[Timeframe] = [
    Timeframe.MN,
    Timeframe.W1,
    Timeframe.D1,
    Timeframe.H4,
    Timeframe.H1,
    Timeframe.M30,
    Timeframe.M15,
    Timeframe.M5,
    # M1 excluded: virtually every public source has a tiny 1m lookback window,
    # so bulk-fetching it would be near-useless.  Fetched on-demand instead.
]

# Seconds between consecutive timeframe requests within one bulk fetch job.
INTER_TF_DELAY_SECONDS: float = 1.5

# Redis keys / TTL
_REDIS_PROGRESS_KEY = "bulk_fetch:progress:{instrument_id}"
_REDIS_TTL_SECONDS = 86_400  # 24 h


# ── Public API ────────────────────────────────────────────────────────────────


async def bulk_fetch_instrument(
    db: AsyncSession,
    instrument: Instrument,
    timeframes: list[Timeframe] | None = None,
    adjusted: bool = True,
    redis=None,  # optional arq Redis pool for progress reporting
) -> dict[str, Any]:
    """
    Fetch the maximum available history for *instrument* across all timeframes.

    Returns a summary dict mapping timeframe value to one of:
      int        — number of new bars inserted (0 is valid; source was empty for TF)
      "skipped"  — skipped because coarser TF already showed source has no data
      "error:…"  — exception message
    """
    if timeframes is None:
        timeframes = BULK_FETCH_TIMEFRAMES

    ticker_sym = _ticker_for_instrument(instrument)
    datasource = await _get_or_create_datasource(db)
    summary: dict[str, Any] = {}

    await _publish_progress(redis, instrument.id, "in_progress", timeframes, summary)

    # Track whether any coarser daily+ TF returned data.  If none did, there is
    # no point querying intraday TFs at all.
    any_daily_or_coarser_returned_data = False

    for tf in timeframes:
        is_intraday = _is_intraday(tf)

        # If all daily/weekly/monthly TFs returned nothing, skip intraday ones.
        if is_intraday and not any_daily_or_coarser_returned_data:
            summary[tf.value] = "skipped"
            logger.info(
                f"Skipping {ticker_sym} {tf.value}: "
                "no daily+ data found; source unlikely to have intraday history"
            )
            await _publish_progress(redis, instrument.id, "in_progress", timeframes, summary)
            continue

        result = await _fetch_one_timeframe(
            db=db,
            instrument=instrument,
            ticker_sym=ticker_sym,
            timeframe=tf,
            datasource_id=datasource.id,
            adjusted=adjusted,
        )
        summary[tf.value] = result

        if isinstance(result, int):
            if result > 0 and not is_intraday:
                any_daily_or_coarser_returned_data = True
            logger.info(f"Bulk fetch {ticker_sym} {tf.value}: {result} bars")
        else:
            logger.info(f"Bulk fetch {ticker_sym} {tf.value}: {result}")

        await _publish_progress(redis, instrument.id, "in_progress", timeframes, summary)
        await asyncio.sleep(INTER_TF_DELAY_SECONDS)

    await _publish_progress(redis, instrument.id, "complete", timeframes, summary)
    logger.info(f"Bulk fetch complete for {ticker_sym}: {summary}")
    return summary


async def get_fetch_progress(instrument_id: int, redis) -> dict | None:
    """
    Return the current bulk-fetch progress for an instrument from Redis,
    or None if no fetch has been recorded (or Redis is unavailable).
    """
    if redis is None:
        return None
    try:
        key = _REDIS_PROGRESS_KEY.format(instrument_id=instrument_id)
        raw = await redis.get(key)
        return json.loads(raw) if raw else None
    except Exception as e:
        logger.warning(f"Could not read fetch progress from Redis: {e}")
        return None


# ── Internal helpers ──────────────────────────────────────────────────────────


async def _fetch_one_timeframe(
    db: AsyncSession,
    instrument: Instrument,
    ticker_sym: str,
    timeframe: Timeframe,
    datasource_id: int,
    adjusted: bool,
) -> int | str:
    yf_interval = TF_TO_YF.get(timeframe, "1d")
    try:
        return await _do_fetch_and_store(
            db=db,
            instrument=instrument,
            ticker_sym=ticker_sym,
            timeframe=timeframe,
            yf_interval=yf_interval,
            datasource_id=datasource_id,
            adjusted=adjusted,
        )
    except Exception as e:
        logger.error(f"Bulk fetch failed for {ticker_sym} {timeframe.value}: {e}")
        return f"error:{e}"


async def _do_fetch_and_store(
    db: AsyncSession,
    instrument: Instrument,
    ticker_sym: str,
    timeframe: Timeframe,
    yf_interval: str,
    datasource_id: int,
    adjusted: bool,
) -> int:
    """Request from EPOCH and upsert all returned bars. Returns new-bar count."""
    ticker = yf.Ticker(ticker_sym)

    df = ticker.history(
        start=EPOCH_START.strftime("%Y-%m-%d"),
        interval=yf_interval,
        auto_adjust=adjusted,
        actions=False,
    )

    if df is None or df.empty:
        return 0

    existing_ts = await _existing_timestamps(db, instrument.id, timeframe, adjusted)

    new_bars: list[OHLCVBar] = []
    for ts, row in df.iterrows():
        ts_utc = _to_utc(ts)
        if ts_utc in existing_ts:
            continue
        bar = _make_bar(row, instrument.id, datasource_id, timeframe, ts_utc, adjusted)
        if bar is not None:
            new_bars.append(bar)

    if new_bars:
        db.add_all(new_bars)
        await db.commit()

    return len(new_bars)


async def _existing_timestamps(
    db: AsyncSession, instrument_id: int, timeframe: Timeframe, adjusted: bool
) -> set[datetime]:
    stmt = select(OHLCVBar.ts).where(
        OHLCVBar.instrument_id == instrument_id,
        OHLCVBar.timeframe == timeframe,
        OHLCVBar.is_adjusted == adjusted,
    )
    rows = (await db.execute(stmt)).scalars().all()
    return {_to_utc(ts) for ts in rows}


def _make_bar(
    row: Any,
    instrument_id: int,
    datasource_id: int,
    timeframe: Timeframe,
    ts_utc: datetime,
    adjusted: bool,
) -> OHLCVBar | None:
    try:
        return OHLCVBar(
            instrument_id=instrument_id,
            data_source_id=datasource_id,
            timeframe=timeframe,
            ts=ts_utc,
            open=Decimal(str(row["Open"])),
            high=Decimal(str(row["High"])),
            low=Decimal(str(row["Low"])),
            close=Decimal(str(row["Close"])),
            volume=(
                Decimal(str(row["Volume"])) if "Volume" in row and pd.notna(row["Volume"]) else None
            ),
            is_adjusted=adjusted,
        )
    except Exception as e:
        logger.debug(f"Skipping malformed bar at {ts_utc}: {e}")
        return None


def _to_utc(ts: Any) -> datetime:
    """Coerce any timestamp-like value to a timezone-aware UTC datetime."""
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=UTC)
    if hasattr(ts, "to_pydatetime"):
        dt = ts.to_pydatetime()
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return datetime.fromtimestamp(float(ts), tz=UTC)


def _is_intraday(tf: Timeframe) -> bool:
    """True for timeframes strictly finer than one day."""
    return tf in {
        Timeframe.M1,
        Timeframe.M5,
        Timeframe.M15,
        Timeframe.M30,
        Timeframe.H1,
        Timeframe.H2,
        Timeframe.H4,
        Timeframe.H12,
    }


async def _publish_progress(
    redis,
    instrument_id: int,
    status: str,
    timeframes: list[Timeframe],
    summary: dict,
) -> None:
    """Write current progress to Redis.  Silently ignored if Redis is unavailable."""
    if redis is None:
        return
    try:
        key = _REDIS_PROGRESS_KEY.format(instrument_id=instrument_id)
        payload = json.dumps(
            {
                "instrument_id": instrument_id,
                "status": status,  # "in_progress" | "complete"
                "timeframes": [tf.value for tf in timeframes],
                "results": summary,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        await redis.set(key, payload, ex=_REDIS_TTL_SECONDS)
    except Exception as e:
        logger.warning(f"Could not write fetch progress to Redis: {e}")


async def _get_or_create_datasource(db: AsyncSession) -> DataSource:
    result = await db.execute(select(DataSource).where(DataSource.name == YFINANCE_SOURCE_NAME))
    src = result.scalar_one_or_none()
    if src is None:
        src = DataSource(
            name=YFINANCE_SOURCE_NAME,
            base_url="https://finance.yahoo.com",
            description="Yahoo Finance via yfinance",
            is_active=True,
        )
        db.add(src)
        await db.flush()
    return src


# Backward-compat alias
_get_or_create_datasource_async = _get_or_create_datasource
