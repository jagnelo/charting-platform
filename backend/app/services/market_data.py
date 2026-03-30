"""
Market data service — async yfinance wrapper with local OHLCV cache.
"""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pandas as pd
import yfinance as yf
from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_source import DataSource
from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe

logger = logging.getLogger(__name__)

TF_TO_YF: dict[Timeframe, str] = {
    Timeframe.M1: "1m",
    Timeframe.M5: "5m",
    Timeframe.M15: "15m",
    Timeframe.M30: "30m",
    Timeframe.H1: "1h",
    Timeframe.H2: "2h",
    Timeframe.H4: "4h",
    Timeframe.H12: "1h",
    Timeframe.D1: "1d",
    Timeframe.W1: "1wk",
    Timeframe.MN: "1mo",
}
TF_MAX_LOOKBACK_DAYS: dict[Timeframe, int | None] = {
    Timeframe.M1: 7,
    Timeframe.M5: 60,
    Timeframe.M15: 60,
    Timeframe.M30: 60,
    Timeframe.H1: 730,
    Timeframe.H2: 730,
    Timeframe.H4: 730,
    Timeframe.H12: 730,
    Timeframe.D1: None,
    Timeframe.W1: None,
    Timeframe.MN: None,
}
YFINANCE_SOURCE_NAME = "yfinance"


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


# Sync version for alert engine (runs in thread)
def _get_or_create_datasource_sync(db):
    from sqlalchemy import select as sa_select

    src = db.execute(
        sa_select(DataSource).where(DataSource.name == YFINANCE_SOURCE_NAME)
    ).scalar_one_or_none()
    if src is None:
        src = DataSource(
            name=YFINANCE_SOURCE_NAME,
            base_url="https://finance.yahoo.com",
            description="Yahoo Finance via yfinance",
            is_active=True,
        )
        db.add(src)
        db.flush()
    return src


_get_or_create_datasource_async = _get_or_create_datasource


def _ticker_for_instrument(instrument: Instrument) -> str:
    for listing in instrument.listings:
        if listing.is_primary and listing.is_active:
            return listing.ticker
    return instrument.symbol


async def fetch_ohlcv(
    db: AsyncSession,
    instrument: Instrument,
    timeframe: Timeframe,
    start: datetime,
    end: datetime | None = None,
    adjusted: bool = True,
) -> list[OHLCVBar]:
    if end is None:
        end = datetime.now(UTC)

    stmt = (
        select(OHLCVBar)
        .where(
            and_(
                OHLCVBar.instrument_id == instrument.id,
                OHLCVBar.timeframe == timeframe,
                OHLCVBar.ts >= start,
                OHLCVBar.ts <= end,
                OHLCVBar.is_adjusted == adjusted,
            )
        )
        .order_by(OHLCVBar.ts)
    )
    cached = list((await db.execute(stmt)).scalars().all())

    if _needs_fetch(cached):
        new_bars = _fetch_yfinance(
            instrument, timeframe, start, end, adjusted, await _get_or_create_datasource(db)
        )
        if new_bars:
            try:
                await db.execute(
                    pg_insert(OHLCVBar).on_conflict_do_nothing(
                        index_elements=["instrument_id", "timeframe", "ts", "is_adjusted"]
                    ),
                    [
                        {
                            "instrument_id": b.instrument_id,
                            "data_source_id": b.data_source_id,
                            "timeframe": b.timeframe,
                            "ts": b.ts,
                            "open": b.open,
                            "high": b.high,
                            "low": b.low,
                            "close": b.close,
                            "volume": b.volume,
                            "vwap": b.vwap,
                            "is_adjusted": b.is_adjusted,
                        }
                        for b in new_bars
                    ],
                )
                await db.commit()
            except Exception as e:
                await db.rollback()
                logger.error(f"Failed to save bars: {e}")

        # Re-query after insert so cached reflects actual DB state with valid ORM objects
        cached = list((await db.execute(stmt)).scalars().all())

    cached.sort(key=lambda b: b.ts)
    return cached


def _needs_fetch(cached: list[OHLCVBar]) -> bool:
    if not cached:
        return True
    latest = max(b.ts for b in cached)
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=UTC)
    return (datetime.now(UTC) - latest) > timedelta(minutes=20)


def _fetch_yfinance(instrument, timeframe, start, end, adjusted, datasource) -> list[OHLCVBar]:
    ticker_sym = _ticker_for_instrument(instrument)
    yf_interval = TF_TO_YF.get(timeframe, "1d")
    try:
        t = yf.Ticker(ticker_sym)
        yf_end = (end + timedelta(days=1)).strftime("%Y-%m-%d")
        df = t.history(
            start=start.strftime("%Y-%m-%d"),
            end=yf_end,
            interval=yf_interval,
            auto_adjust=adjusted,
            actions=False,
        )
    except Exception as e:
        logger.error(f"yfinance fetch failed for {ticker_sym}: {e}")
        return []

    if df is None or df.empty:
        return []

    bars = []
    for ts, row in df.iterrows():
        if hasattr(ts, "tzinfo") and ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        bars.append(
            OHLCVBar(
                instrument_id=instrument.id,
                data_source_id=datasource.id,
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
        )
    logger.info(f"Fetched {len(bars)} bars for {ticker_sym} {timeframe.value}")
    return bars


def get_current_price(ticker: str) -> float | None:
    try:
        t = yf.Ticker(ticker)
        data = t.history(period="1d", interval="1m")
        if data is not None and not data.empty:
            return float(data["Close"].iloc[-1])
        fi = t.fast_info
        return float(fi.last_price) if hasattr(fi, "last_price") else None
    except Exception as e:
        logger.error(f"Failed to get price for {ticker}: {e}")
        return None


def search_ticker(query: str) -> list[dict]:
    try:
        results = yf.Search(query, max_results=10)
        quotes = results.quotes if hasattr(results, "quotes") else []
        return [
            {
                "symbol": q.get("symbol", ""),
                "name": q.get("longname") or q.get("shortname", ""),
                "exchange": q.get("exchange", ""),
                "type": q.get("quoteType", ""),
            }
            for q in quotes
            if q.get("symbol")
        ]
    except Exception as e:
        logger.error(f"Ticker search failed for '{query}': {e}")
        return []


def get_instrument_info(ticker: str) -> dict:
    try:
        return yf.Ticker(ticker).info or {}
    except Exception as e:
        logger.error(f"Failed to get info for {ticker}: {e}")
        return {}
