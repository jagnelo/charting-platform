"""
Market data service — async yfinance wrapper with local OHLCV cache.

Synthetic instruments (is_synthetic=True) are routed through the expression
engine rather than fetched from yfinance.  Their OHLCV is computed from
constituent bars and written to the standard ohlcv_bar table so the rest of
the system (chart, alert, indicator, screener) reads them transparently.
"""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
import yfinance as yf
from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_source import DataSource
from app.models.instrument import Instrument
from app.models.ohlcv import TIMEFRAME_SECONDS, OHLCVBar, Timeframe

logger = logging.getLogger(__name__)

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

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


async def recompute_synthetic_ohlcv(
    db: AsyncSession,
    instrument: Instrument,
    timeframe: Timeframe,
) -> list[OHLCVBar]:
    """
    Recompute and persist the full OHLCV cache for a synthetic instrument by
    fetching all constituent bars, aligning them to common timestamps, evaluating
    the expression, and upserting the results into ohlcv_bar.

    Called after any constituent's OHLCV is updated.
    """
    from app.models.synthetic_constituent import SyntheticConstituent
    from app.services.expression_engine import compute_synthetic_ohlcv

    if not instrument.is_synthetic or not instrument.expression:
        return []

    datasource = await _get_or_create_datasource(db)

    # Load constituent rows
    constituents_result = await db.execute(
        select(SyntheticConstituent).where(
            SyntheticConstituent.synthetic_instrument_id == instrument.id
        )
    )
    constituents = list(constituents_result.scalars().all())
    if not constituents:
        return []

    # Fetch each constituent's bars for the timeframe, falling back to yfinance if DB is cold
    constituent_bars: dict[str, list[OHLCVBar]] = {}
    datasource = await _get_or_create_datasource(db)
    for c in constituents:
        stmt = (
            select(OHLCVBar)
            .where(
                OHLCVBar.instrument_id == c.constituent_instrument_id,
                OHLCVBar.timeframe == timeframe,
                OHLCVBar.is_adjusted.is_(True),
            )
            .order_by(OHLCVBar.ts)
        )
        bars = list((await db.execute(stmt)).scalars().all())
        if not bars:
            # DB is cold for this constituent — bootstrap from yfinance
            const_instr = await db.get(Instrument, c.constituent_instrument_id)
            if const_instr is not None:
                await db.refresh(const_instr, ["listings"])
                new_bars = _fetch_yfinance_latest(const_instr, timeframe, 500, True, datasource)
                if new_bars:
                    try:
                        await db.execute(
                            pg_insert(OHLCVBar).on_conflict_do_nothing(
                                index_elements=["instrument_id", "timeframe", "ts", "is_adjusted"]
                            ),
                            [_bar_as_dict(b) for b in new_bars],
                        )
                        await db.commit()
                        bars = list((await db.execute(stmt)).scalars().all())
                    except Exception as e:
                        await db.rollback()
                        logger.error(
                            f"Failed to bootstrap bars for constituent {const_instr.symbol}: {e}"
                        )
        constituent_bars[c.ticker_alias.upper()] = bars

    if not constituent_bars:
        return []

    # Build timestamp intersection across all constituents
    ts_sets = [
        {b.ts.replace(tzinfo=UTC) if b.ts.tzinfo is None else b.ts for b in bars}
        for bars in constituent_bars.values()
    ]
    common_ts = sorted(ts_sets[0].intersection(*ts_sets[1:]))
    if not common_ts:
        return []

    ts_index = {ts: i for i, ts in enumerate(common_ts)}

    def align(bars: list[OHLCVBar]) -> dict[str, np.ndarray]:
        n = len(common_ts)
        opens = np.full(n, np.nan)
        highs = np.full(n, np.nan)
        lows = np.full(n, np.nan)
        closes = np.full(n, np.nan)
        for b in bars:
            ts = b.ts.replace(tzinfo=UTC) if b.ts.tzinfo is None else b.ts
            idx = ts_index.get(ts)
            if idx is not None:
                opens[idx] = float(b.open)
                highs[idx] = float(b.high)
                lows[idx] = float(b.low)
                closes[idx] = float(b.close)
        return {"open": opens, "high": highs, "low": lows, "close": closes}

    constituent_ohlcv = {ticker: align(bars) for ticker, bars in constituent_bars.items()}

    synthetic = compute_synthetic_ohlcv(instrument.expression, constituent_ohlcv)

    # Build OHLCVBar objects
    new_bars = []
    for i, ts in enumerate(common_ts):
        o = synthetic["open"][i]
        h = synthetic["high"][i]
        lv = synthetic["low"][i]
        c = synthetic["close"][i]
        if any(np.isnan(v) for v in [o, h, lv, c]):
            continue
        new_bars.append(
            {
                "instrument_id": instrument.id,
                "data_source_id": datasource.id,
                "timeframe": timeframe,
                "ts": ts,
                "open": Decimal(str(round(o, 8))),
                "high": Decimal(str(round(h, 8))),
                "low": Decimal(str(round(lv, 8))),
                "close": Decimal(str(round(c, 8))),
                "volume": None,
                "vwap": None,
                "is_adjusted": True,
            }
        )

    if new_bars:
        try:
            await db.execute(
                pg_insert(OHLCVBar).on_conflict_do_update(
                    index_elements=["instrument_id", "timeframe", "ts", "is_adjusted"],
                    set_={
                        "open": pg_insert(OHLCVBar).excluded.open,
                        "high": pg_insert(OHLCVBar).excluded.high,
                        "low": pg_insert(OHLCVBar).excluded.low,
                        "close": pg_insert(OHLCVBar).excluded.close,
                    },
                ),
                new_bars,
            )
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to upsert synthetic bars for {instrument.symbol}: {e}")

    # Return ORM objects
    stmt = (
        select(OHLCVBar)
        .where(OHLCVBar.instrument_id == instrument.id, OHLCVBar.timeframe == timeframe)
        .order_by(OHLCVBar.ts)
    )
    return list((await db.execute(stmt)).scalars().all())


async def fetch_ohlcv(
    db: AsyncSession,
    instrument: Instrument,
    timeframe: Timeframe,
    start: datetime,
    end: datetime | None = None,
    adjusted: bool = True,
) -> list[OHLCVBar]:
    # Synthetic instruments use computed OHLCV, not yfinance
    if instrument.is_synthetic:
        bars = await recompute_synthetic_ohlcv(db, instrument, timeframe)
        if end is None:
            end = datetime.now(UTC)
        return [b for b in bars if b.ts >= start and b.ts <= end]

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

    if _needs_fetch(cached, timeframe):
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


_TF_STALENESS: dict[Timeframe, timedelta] = {
    Timeframe.M1: timedelta(minutes=1),
    Timeframe.M5: timedelta(minutes=5),
    Timeframe.M15: timedelta(minutes=15),
    Timeframe.M30: timedelta(minutes=30),
    Timeframe.H1: timedelta(hours=1),
    Timeframe.H2: timedelta(hours=2),
    Timeframe.H4: timedelta(hours=4),
    Timeframe.H12: timedelta(hours=12),
    Timeframe.D1: timedelta(days=1),
    Timeframe.W1: timedelta(weeks=1),
    Timeframe.MN: timedelta(days=31),
}


def _needs_fetch(cached: list[OHLCVBar], timeframe: Timeframe) -> bool:
    if not cached:
        return True
    latest = max(b.ts for b in cached)
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=UTC)
    threshold = _TF_STALENESS.get(timeframe, timedelta(minutes=20))
    return (datetime.now(UTC) - latest) > threshold


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


async def fetch_ohlcv_latest(
    db: AsyncSession,
    instrument: Instrument,
    timeframe: Timeframe,
    limit: int,
    adjusted: bool = True,
) -> list[OHLCVBar]:
    """Return the most recent `limit` bars from the DB, refreshing from yfinance if stale.

    For synthetic instruments the full computed series is returned (limit applied).
    """
    if instrument.is_synthetic:
        bars = await recompute_synthetic_ohlcv(db, instrument, timeframe)
        return bars[-limit:] if len(bars) > limit else bars
    stmt = (
        select(OHLCVBar)
        .where(
            OHLCVBar.instrument_id == instrument.id,
            OHLCVBar.timeframe == timeframe,
            OHLCVBar.is_adjusted == adjusted,
        )
        .order_by(OHLCVBar.ts.desc())
        .limit(limit)
    )
    rows = list((await db.execute(stmt)).scalars().all())
    rows.sort(key=lambda b: b.ts)  # return chronological order

    if not rows:
        # DB is cold — fetch the full recent window from yfinance
        new_bars = _fetch_yfinance_latest(
            instrument, timeframe, limit, adjusted, await _get_or_create_datasource(db)
        )
        if new_bars:
            try:
                await db.execute(
                    pg_insert(OHLCVBar).on_conflict_do_nothing(
                        index_elements=["instrument_id", "timeframe", "ts", "is_adjusted"]
                    ),
                    [_bar_as_dict(b) for b in new_bars],
                )
                await db.commit()
                rows = list((await db.execute(stmt)).scalars().all())
                rows.sort(key=lambda b: b.ts)
            except Exception as e:
                await db.rollback()
                logger.error(f"Failed to save bars: {e}")
    elif len(rows) < limit:
        # DB has a fresh but incomplete latest page. This can happen if an
        # earlier background fetch only inserted a small recent slice; without
        # this repair the frontend assumes those few bars are the full history.
        oldest_ts = min(b.ts for b in rows)
        if oldest_ts.tzinfo is None:
            oldest_ts = oldest_ts.replace(tzinfo=UTC)
        repair_start = _latest_window_start(timeframe, limit)
        repair_end = oldest_ts - timedelta(seconds=1)
        if repair_end > repair_start:
            datasource = await _get_or_create_datasource(db)
            repair_bars = _fetch_yfinance(
                instrument,
                timeframe,
                repair_start,
                repair_end,
                adjusted,
                datasource,
            )
            if repair_bars:
                try:
                    await db.execute(
                        pg_insert(OHLCVBar).on_conflict_do_update(
                            index_elements=["instrument_id", "timeframe", "ts", "is_adjusted"],
                            set_={
                                "open": pg_insert(OHLCVBar).excluded.open,
                                "high": pg_insert(OHLCVBar).excluded.high,
                                "low": pg_insert(OHLCVBar).excluded.low,
                                "close": pg_insert(OHLCVBar).excluded.close,
                                "volume": pg_insert(OHLCVBar).excluded.volume,
                                "vwap": pg_insert(OHLCVBar).excluded.vwap,
                            },
                        ),
                        [_bar_as_dict(b) for b in repair_bars],
                    )
                    await db.commit()
                    rows = list((await db.execute(stmt)).scalars().all())
                    rows.sort(key=lambda b: b.ts)
                except Exception as e:
                    await db.rollback()
                    logger.error(f"Failed to repair incomplete latest bars: {e}")
    if rows and _needs_fetch(rows, timeframe):
        # DB has data but it's stale — fetch from the latest DB bar onwards
        latest_ts = max(b.ts for b in rows)
        if latest_ts.tzinfo is None:
            latest_ts = latest_ts.replace(tzinfo=UTC)
        datasource = await _get_or_create_datasource(db)
        new_bars = _fetch_yfinance(
            instrument, timeframe, latest_ts, datetime.now(UTC), adjusted, datasource
        )
        if new_bars:
            try:
                await db.execute(
                    pg_insert(OHLCVBar).on_conflict_do_update(
                        index_elements=["instrument_id", "timeframe", "ts", "is_adjusted"],
                        set_={
                            "open": pg_insert(OHLCVBar).excluded.open,
                            "high": pg_insert(OHLCVBar).excluded.high,
                            "low": pg_insert(OHLCVBar).excluded.low,
                            "close": pg_insert(OHLCVBar).excluded.close,
                            "volume": pg_insert(OHLCVBar).excluded.volume,
                            "vwap": pg_insert(OHLCVBar).excluded.vwap,
                        },
                    ),
                    [_bar_as_dict(b) for b in new_bars],
                )
                await db.commit()
                rows = list((await db.execute(stmt)).scalars().all())
                rows.sort(key=lambda b: b.ts)
            except Exception as e:
                await db.rollback()
                logger.error(f"Failed to save refreshed bars: {e}")

    return rows


async def fetch_ohlcv_page_before(
    db: AsyncSession,
    instrument: Instrument,
    timeframe: Timeframe,
    before: datetime,
    limit: int,
    adjusted: bool = True,
) -> list[OHLCVBar]:
    """
    Return up to `limit` bars strictly before `before`.

    For synthetic instruments the full computed series is filtered instead of
    hitting yfinance.
    """
    if instrument.is_synthetic:
        bars = await recompute_synthetic_ohlcv(db, instrument, timeframe)
        filtered = [b for b in bars if b.ts < before]
        return filtered[-limit:] if len(filtered) > limit else filtered

    """
    DB-first: queries the local cache. If the DB has fewer rows than requested,
    falls back to a live yfinance fetch for the missing historical range
    (EPOCH → before), stores the results, then re-queries. This ensures
    pagination works correctly even when the background bulk fetch hasn't
    finished writing all historical bars yet.
    """
    stmt = (
        select(OHLCVBar)
        .where(
            OHLCVBar.instrument_id == instrument.id,
            OHLCVBar.timeframe == timeframe,
            OHLCVBar.is_adjusted == adjusted,
            OHLCVBar.ts < before,
        )
        .order_by(OHLCVBar.ts.desc())
        .limit(limit)
    )
    rows = list((await db.execute(stmt)).scalars().all())

    if len(rows) < limit:
        # DB doesn't have enough older bars — attempt a live fetch for the
        # full historical range up to `before`. The bulk fetch may still be
        # running, but fetching on-demand here is safe: the upsert uses
        # on_conflict_do_nothing so there are no duplicates.
        datasource = await _get_or_create_datasource(db)
        fetched = _fetch_yfinance(instrument, timeframe, _EPOCH, before, adjusted, datasource)
        if fetched:
            try:
                await db.execute(
                    pg_insert(OHLCVBar).on_conflict_do_nothing(
                        index_elements=["instrument_id", "timeframe", "ts", "is_adjusted"]
                    ),
                    [_bar_as_dict(b) for b in fetched],
                )
                await db.commit()
            except Exception as e:
                await db.rollback()
                logger.error(f"fetch_ohlcv_page_before: failed to save bars: {e}")

            # Re-query so we return proper ORM objects and pick up any bars
            # written by the concurrent bulk fetch as well
            rows = list((await db.execute(stmt)).scalars().all())

    rows.sort(key=lambda b: b.ts)
    return rows


def _bar_as_dict(b: OHLCVBar) -> dict:
    return {
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


def _fetch_yfinance_latest(instrument, timeframe, limit, adjusted, datasource) -> list[OHLCVBar]:
    """Fetch approximately `limit` recent bars from yfinance when DB is cold."""
    start = _latest_window_start(timeframe, limit)
    bars = _fetch_yfinance(instrument, timeframe, start, datetime.now(UTC), adjusted, datasource)
    return bars[-limit:] if len(bars) > limit else bars


def _latest_window_start(timeframe: Timeframe, limit: int) -> datetime:
    """Return a conservative start date for fetching approximately `limit` recent bars."""
    tf_secs = TIMEFRAME_SECONDS.get(timeframe, 86400)
    # Request 2× to account for weekends/holidays and sparse trading calendars.
    days_needed = max(7, int(tf_secs * limit * 2 / 86400))
    max_lookback = TF_MAX_LOOKBACK_DAYS.get(timeframe)
    if max_lookback is not None:
        days_needed = min(days_needed, max_lookback)
    return datetime.now(UTC) - timedelta(days=days_needed)


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
