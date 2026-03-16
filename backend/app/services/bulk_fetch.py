"""
Bulk historical data fetcher.
Pulls the maximum available OHLCV history for an instrument from yfinance
and stores it in the local DB for all supported timeframes.

Called as an ARQ background task when a new instrument is registered,
or manually triggered via the API.
"""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pandas as pd
import yfinance as yf
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_source import DataSource
from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.services.market_data import (
    TF_MAX_LOOKBACK_DAYS,
    TF_TO_YF,
    YFINANCE_SOURCE_NAME,
    _ticker_for_instrument,
)

logger = logging.getLogger(__name__)

# Timeframes to fetch during bulk load, ordered by granularity (most granular last)
BULK_FETCH_TIMEFRAMES = [
    Timeframe.MN,
    Timeframe.W1,
    Timeframe.D1,
    Timeframe.H4,
    Timeframe.H1,
    Timeframe.M30,
    Timeframe.M15,
    Timeframe.M5,
]


async def bulk_fetch_instrument(
    db: AsyncSession,
    instrument: Instrument,
    timeframes: list[Timeframe] | None = None,
    adjusted: bool = True,
) -> dict[str, int]:
    """
    Fetch the maximum available history for an instrument across all timeframes.
    Returns a dict of {timeframe: bars_inserted}.
    """
    if timeframes is None:
        timeframes = BULK_FETCH_TIMEFRAMES

    ticker_sym = _ticker_for_instrument(instrument)
    datasource = await _get_or_create_datasource_async(db)
    summary: dict[str, int] = {}

    for tf in timeframes:
        try:
            count = await _fetch_timeframe(db, instrument, ticker_sym, tf, datasource.id, adjusted)
            summary[tf.value] = count
            logger.info(f"Bulk fetch {ticker_sym} {tf.value}: {count} bars")
        except Exception as e:
            logger.error(f"Bulk fetch failed for {ticker_sym} {tf.value}: {e}")
            summary[tf.value] = -1

    return summary


async def _fetch_timeframe(
    db: AsyncSession,
    instrument: Instrument,
    ticker_sym: str,
    timeframe: Timeframe,
    datasource_id: int,
    adjusted: bool,
) -> int:
    yf_interval = TF_TO_YF.get(timeframe, "1d")
    max_days = TF_MAX_LOOKBACK_DAYS.get(timeframe)

    start = None
    if max_days:
        start = (datetime.now(UTC) - timedelta(days=max_days)).strftime("%Y-%m-%d")

    ticker = yf.Ticker(ticker_sym)
    df = ticker.history(
        start=start,
        period="max" if max_days is None else None,
        interval=yf_interval,
        auto_adjust=adjusted,
        actions=False,
    )

    if df is None or df.empty:
        return 0

    # Get existing timestamps to skip duplicates
    existing_stmt = select(OHLCVBar.ts).where(
        OHLCVBar.instrument_id == instrument.id,
        OHLCVBar.timeframe == timeframe,
        OHLCVBar.is_adjusted == adjusted,
    )
    existing_ts = set(
        ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts
        for ts in (await db.execute(existing_stmt)).scalars().all()
    )

    new_bars = []
    for ts, row in df.iterrows():
        if hasattr(ts, "tzinfo") and ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)

        if ts in existing_ts:
            continue

        bar = OHLCVBar(
            instrument_id=instrument.id,
            data_source_id=datasource_id,
            timeframe=timeframe,
            ts=ts,
            open=Decimal(str(row["Open"])),
            high=Decimal(str(row["High"])),
            low=Decimal(str(row["Low"])),
            close=Decimal(str(row["Close"])),
            volume=Decimal(str(row["Volume"]))
            if "Volume" in row and pd.notna(row["Volume"])
            else None,
            is_adjusted=adjusted,
        )
        new_bars.append(bar)

    if new_bars:
        db.add_all(new_bars)
        await db.commit()

    return len(new_bars)


async def _get_or_create_datasource_async(db: AsyncSession) -> DataSource:
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
