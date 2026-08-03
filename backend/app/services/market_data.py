"""
Market data service with a provider-agnostic cache boundary.

Synthetic instruments (is_synthetic=True) are routed through the expression
engine rather than fetched from an external provider. Their OHLCV is computed
from constituent bars and written to the standard ohlcv_bar table so the rest
of the system (chart, alert, indicator, screener) reads them transparently.
"""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.data_source import DataSource
from app.models.instrument import Instrument
from app.models.ohlcv import TIMEFRAME_SECONDS, OHLCVBar, Timeframe
from app.models.provider_observation import (
    DatasetStatus,
    InstrumentDatasetState,
    InstrumentProfileSnapshot,
    InstrumentSearchSnapshot,
    LatestPriceSnapshot,
    MarketBarObservation,
)
from app.models.provider_runtime import ProviderCapability
from app.providers import (
    ensure_data_source,
    provider_symbol_for_instrument,
)
from app.providers.base import InstrumentProfile
from app.services.instrument_mastering import ingest_provider_profile, reconcile_instrument_profile
from app.services.provider_observations import (
    store_latest_price_snapshot,
    store_search_snapshot,
)
from app.services.provider_runtime import (
    ProviderNoDataError,
    execute_provider_call,
    resolve_provider_chain,
)

logger = logging.getLogger(__name__)

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


async def _get_or_create_datasource(db: AsyncSession) -> DataSource:
    chain = await resolve_provider_chain(db, ProviderCapability.PRICE_HISTORY)
    if chain:
        return chain[0].data_source
    provider_name = settings.PROVIDER_CHAIN_SEEDS.get(
        "price_history", [settings.DEFAULT_MARKET_DATA_PROVIDER]
    )[0]
    return await ensure_data_source(db, provider_name)


async def _latest_window_start(
    db: AsyncSession,
    timeframe: Timeframe,
    limit: int,
) -> datetime:
    chain = await resolve_provider_chain(db, ProviderCapability.PRICE_HISTORY)
    if chain:
        return chain[0].provider.latest_window_start(timeframe, limit)
    return datetime.now(UTC) - timedelta(seconds=TIMEFRAME_SECONDS[timeframe] * limit)


def resolve_provider_symbol_for_instrument(instrument: Instrument) -> str:
    provider_names = settings.PROVIDER_CHAIN_SEEDS.get("price_history") or [
        settings.DEFAULT_MARKET_DATA_PROVIDER
    ]
    return provider_symbol_for_instrument(instrument, provider_names[0])


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _historical_repair_start(
    before: datetime,
    timeframe: Timeframe,
    missing_count: int,
    oldest_cached: datetime | None = None,
) -> datetime:
    """Return a bounded older-tail start instead of requesting the full epoch."""
    anchor = _as_utc(oldest_cached or before)
    overlap_bars = max(1, missing_count) * 2
    return anchor - timedelta(seconds=TIMEFRAME_SECONDS[timeframe] * overlap_bars)


async def _fresh_latest_price_from_cache(
    db: AsyncSession,
    instrument: Instrument,
) -> float | None:
    now = datetime.now(UTC)
    for resolved in await resolve_provider_chain(db, ProviderCapability.LATEST_PRICE):
        snapshot = (
            await db.execute(
                select(LatestPriceSnapshot)
                .where(
                    LatestPriceSnapshot.instrument_id == instrument.id,
                    LatestPriceSnapshot.data_source_id == resolved.data_source.id,
                    LatestPriceSnapshot.observed_at
                    >= now - timedelta(seconds=resolved.policy.freshness_seconds),
                )
                .order_by(LatestPriceSnapshot.observed_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if snapshot is not None:
            return float(snapshot.price)
    return None


def _search_results_from_payload(payload: dict, *, provider_name: str | None = None) -> list[dict]:
    return [
        {
            "symbol": result.get("symbol", ""),
            "name": result.get("name", ""),
            "exchange": result.get("exchange", ""),
            "type": result.get("instrument_type", ""),
            **({"provider": provider_name} if provider_name else {}),
        }
        for result in payload.get("results", [])
    ]


async def _fresh_search_from_cache(db: AsyncSession, query: str) -> list[dict] | None:
    now = datetime.now(UTC)
    merged: list[dict] = []
    seen: set[str] = set()
    for resolved in await resolve_provider_chain(db, ProviderCapability.INSTRUMENT_SEARCH):
        snapshot = (
            await db.execute(
                select(InstrumentSearchSnapshot)
                .where(
                    InstrumentSearchSnapshot.data_source_id == resolved.data_source.id,
                    InstrumentSearchSnapshot.query == query,
                    InstrumentSearchSnapshot.observed_at
                    >= now - timedelta(seconds=resolved.policy.freshness_seconds),
                )
                .order_by(InstrumentSearchSnapshot.observed_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if snapshot is None:
            return None
        for item in _search_results_from_payload(
            snapshot.payload, provider_name=resolved.provider_name
        ):
            symbol = item.get("symbol", "")
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            merged.append(item)
    return merged


def _search_priority(query: str, item: dict) -> tuple[int, int, int, int, str]:
    normalized = query.strip().upper()
    symbol = str(item.get("symbol") or "").strip().upper()
    asset_type = str(item.get("type") or "").strip().upper()
    exact = 0 if symbol == normalized else 1
    prefix = 0 if symbol.startswith(normalized) else 1
    contains = 0 if normalized and normalized in symbol else 1
    crypto_penalty = 1 if "CRYPTO" in asset_type and not normalized.endswith("-USD") else 0
    return (exact, prefix, contains, crypto_penalty, symbol)


async def _fresh_profile_from_cache(
    db: AsyncSession,
    *,
    instrument_id: int | None = None,
    provider_symbol: str | None = None,
) -> InstrumentProfile | None:
    instrument = None
    if instrument_id is not None:
        instrument = await db.get(Instrument, instrument_id)
    elif provider_symbol:
        instrument = (
            await db.execute(
                select(Instrument).where(
                    Instrument.symbol == provider_symbol,
                    Instrument.is_synthetic.is_(False),
                )
            )
        ).scalar_one_or_none()
    if instrument is None:
        return None

    now = datetime.now(UTC)
    provider_ids = {
        resolved.data_source.id: resolved.policy.freshness_seconds
        for resolved in await resolve_provider_chain(db, ProviderCapability.INSTRUMENT_METADATA)
    }
    snapshots = (
        (
            await db.execute(
                select(InstrumentProfileSnapshot)
                .where(InstrumentProfileSnapshot.instrument_id == instrument.id)
                .order_by(InstrumentProfileSnapshot.observed_at.desc())
            )
        )
        .scalars()
        .all()
    )
    for snapshot in snapshots:
        freshness = provider_ids.get(snapshot.data_source_id)
        if freshness is None:
            continue
        if _as_utc(snapshot.observed_at) >= now - timedelta(seconds=freshness):
            return await reconcile_instrument_profile(db, instrument)
    return None


async def _record_bar_observations(
    db: AsyncSession,
    bars: list[OHLCVBar],
    *,
    data_source_id: int,
    provider_symbol: str | None,
    observed_at: datetime | None = None,
) -> None:
    if not bars:
        return
    observed_at = observed_at or datetime.now(UTC)
    await db.execute(
        pg_insert(MarketBarObservation).on_conflict_do_update(
            constraint="uq_market_bar_observation",
            set_={
                "provider_symbol": pg_insert(MarketBarObservation).excluded.provider_symbol,
                "observed_at": pg_insert(MarketBarObservation).excluded.observed_at,
                "open": pg_insert(MarketBarObservation).excluded.open,
                "high": pg_insert(MarketBarObservation).excluded.high,
                "low": pg_insert(MarketBarObservation).excluded.low,
                "close": pg_insert(MarketBarObservation).excluded.close,
                "volume": pg_insert(MarketBarObservation).excluded.volume,
                "vwap": pg_insert(MarketBarObservation).excluded.vwap,
            },
        ),
        [
            {
                "instrument_id": bar.instrument_id,
                "data_source_id": data_source_id,
                "provider_symbol": provider_symbol,
                "timeframe": bar.timeframe,
                "ts": bar.ts,
                "observed_at": observed_at,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "vwap": bar.vwap,
                "is_adjusted": bar.is_adjusted,
            }
            for bar in bars
        ],
    )


async def _touch_ohlcv_dataset_state(
    db: AsyncSession,
    instrument: Instrument,
    *,
    data_source_id: int,
    timeframe: Timeframe,
    adjusted: bool,
    bars: list[OHLCVBar],
    fetched_at: datetime | None = None,
) -> None:
    fetched_at = fetched_at or datetime.now(UTC)
    dataset_key = f"{timeframe.value}:{'adj' if adjusted else 'raw'}"
    state = (
        await db.execute(
            select(InstrumentDatasetState).where(
                InstrumentDatasetState.instrument_id == instrument.id,
                InstrumentDatasetState.data_source_id == data_source_id,
                InstrumentDatasetState.dataset_type == "ohlcv",
                InstrumentDatasetState.dataset_key == dataset_key,
            )
        )
    ).scalar_one_or_none()
    if state is None:
        state = InstrumentDatasetState(
            instrument_id=instrument.id,
            data_source_id=data_source_id,
            dataset_type="ohlcv",
            dataset_key=dataset_key,
        )
        db.add(state)
    state.status = DatasetStatus.FRESH if bars else DatasetStatus.PENDING
    state.observed_at = fetched_at
    state.fetched_at = fetched_at
    state.stale_after = fetched_at + _TF_STALENESS.get(timeframe, timedelta(minutes=20))
    if bars:
        state.coverage_start = min(bar.ts for bar in bars)
        state.coverage_end = max(bar.ts for bar in bars)
        state.extra_data = {"bar_count": len(bars), "adjusted": adjusted}


async def persist_price_history_bars(
    db: AsyncSession,
    instrument: Instrument,
    *,
    data_source_id: int,
    provider_symbol: str | None,
    timeframe: Timeframe,
    adjusted: bool,
    bars: list[OHLCVBar],
    observed_at: datetime | None = None,
    use_upsert: bool = True,
) -> None:
    if not bars:
        return
    await _record_bar_observations(
        db,
        bars,
        data_source_id=data_source_id,
        provider_symbol=provider_symbol,
        observed_at=observed_at,
    )
    insert_stmt = pg_insert(OHLCVBar)
    if use_upsert:
        insert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=["instrument_id", "timeframe", "ts", "is_adjusted"],
            set_={
                "open": insert_stmt.excluded.open,
                "high": insert_stmt.excluded.high,
                "low": insert_stmt.excluded.low,
                "close": insert_stmt.excluded.close,
                "volume": insert_stmt.excluded.volume,
                "vwap": insert_stmt.excluded.vwap,
                "data_source_id": insert_stmt.excluded.data_source_id,
            },
        )
    else:
        insert_stmt = insert_stmt.on_conflict_do_nothing(
            index_elements=["instrument_id", "timeframe", "ts", "is_adjusted"]
        )
    await db.execute(insert_stmt, [_bar_as_dict(bar) for bar in bars])
    await _touch_ohlcv_dataset_state(
        db,
        instrument,
        data_source_id=data_source_id,
        timeframe=timeframe,
        adjusted=adjusted,
        bars=bars,
        fetched_at=observed_at,
    )


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

    # Fetch each constituent's bars for the timeframe, falling back to the configured
    # market-data provider if the DB is cold.
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
            # DB is cold for this constituent — bootstrap from the default provider.
            const_instr = await db.get(Instrument, c.constituent_instrument_id)
            if const_instr is not None:
                await db.refresh(const_instr, ["listings"])
                new_bars = await _fetch_provider_latest(db, const_instr, timeframe, 500, True)
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
    # Synthetic instruments use computed OHLCV, not an external provider.
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

    if _needs_fetch_for_range(cached, timeframe, start, end):
        repair_slices = _missing_range_slices(cached, timeframe, start, end)
        # A current-window request may have no obvious bounded gap while still
        # needing a freshness refresh. In that case retain the existing range
        # fetch semantics; historical/internal gaps use only their slices.
        if not repair_slices:
            repair_slices = [(start, end)]
        new_bars: list[OHLCVBar] = []
        for repair_start, repair_end in repair_slices:
            if repair_end < repair_start:
                continue
            try:
                new_bars.extend(
                    await _fetch_provider(
                        db, instrument, timeframe, repair_start, repair_end, adjusted
                    )
                )
            except ProviderNoDataError:
                if not cached:
                    raise
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


def _needs_fetch_for_range(
    cached: list[OHLCVBar],
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
) -> bool:
    """
    Decide whether an explicit range query should trigger a provider fetch.

    Historical ranges that are already covered in the local DB should not be
    considered "stale" just because their latest cached bar is old relative to
    the current wall clock. We only fall back to freshness logic when the range
    extends into the recent live window or coverage is obviously incomplete.
    """
    if not cached:
        return True

    first_cached = min(bar.ts for bar in cached)
    last_cached = max(bar.ts for bar in cached)
    if first_cached.tzinfo is None:
        first_cached = first_cached.replace(tzinfo=UTC)
    if last_cached.tzinfo is None:
        last_cached = last_cached.replace(tzinfo=UTC)
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)

    fully_covered = first_cached <= start and last_cached >= end
    threshold = _TF_STALENESS.get(timeframe, timedelta(minutes=20))
    range_is_historical = end <= (datetime.now(UTC) - threshold)
    if fully_covered and range_is_historical:
        return bool(_missing_range_slices(cached, timeframe, start, end))
    return _needs_fetch(cached, timeframe)


def _missing_range_slices(
    cached: list[OHLCVBar],
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
) -> list[tuple[datetime, datetime]]:
    """Return bounded edge/obvious internal gaps for an explicit range.

    The database stores bars, not exchange calendars.  Exact calendar-aware
    inference is therefore unsafe for daily sessions (weekends and holidays
    are legitimate gaps).  Edge gaps are exact; internal gaps are repaired
    only when their distance is materially larger than the timeframe interval,
    which avoids treating ordinary non-trading days as missing bars.
    """
    if not cached:
        return [(start, end)]

    step = timedelta(seconds=TIMEFRAME_SECONDS[timeframe])
    start = _as_utc(start)
    end = _as_utc(end)
    ordered = sorted(_as_utc(bar.ts) for bar in cached if start <= _as_utc(bar.ts) <= end)
    if not ordered:
        return [(start, end)]

    # Daily sessions can legitimately be separated by a weekend; intraday
    # and higher timeframes use a tighter threshold for obvious holes.
    tolerance = 4 if timeframe == Timeframe.D1 else 2
    slices: list[tuple[datetime, datetime]] = []

    if ordered[0] > start + step:
        slices.append((start, ordered[0] - step))
    elif ordered[0] > start:
        slices.append((start, ordered[0]))

    for previous, current in zip(ordered, ordered[1:]):
        if current - previous > step * tolerance:
            gap_start = previous + step
            gap_end = current - step
            if gap_start <= gap_end:
                slices.append((gap_start, gap_end))

    if ordered[-1] < end - step:
        slices.append((ordered[-1] + step, end))
    elif ordered[-1] < end:
        slices.append((ordered[-1], end))

    return slices


async def _fetch_provider(
    db: AsyncSession,
    instrument: Instrument,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    adjusted: bool,
) -> list[OHLCVBar]:
    execution = await execute_provider_call(
        db,
        ProviderCapability.PRICE_HISTORY,
        f"fetch_ohlcv:{timeframe.value}",
        instrument_id=instrument.id,
        invoke=lambda provider, _provider_symbol: provider.fetch_ohlcv(
            provider_symbol_for_instrument(instrument, provider.name),
            timeframe,
            start,
            end,
            adjusted=adjusted,
            instrument_id=instrument.id,
            data_source_id=0,
        ),
        response_items=lambda result: len(result),
        treat_empty_as_failure=True,
    )
    provider_symbol = provider_symbol_for_instrument(instrument, execution.provider_name)
    bars = execution.result
    for bar in bars:
        bar.instrument_id = instrument.id
        bar.data_source_id = execution.data_source.id
    await _record_bar_observations(
        db,
        bars,
        data_source_id=execution.data_source.id,
        provider_symbol=provider_symbol,
    )
    await _touch_ohlcv_dataset_state(
        db,
        instrument,
        data_source_id=execution.data_source.id,
        timeframe=timeframe,
        adjusted=adjusted,
        bars=bars,
    )
    logger.info(
        "Fetched %d bars for %s %s via %s",
        len(bars),
        provider_symbol,
        timeframe.value,
        execution.provider_name,
    )
    return bars


async def fetch_ohlcv_latest(
    db: AsyncSession,
    instrument: Instrument,
    timeframe: Timeframe,
    limit: int,
    adjusted: bool = True,
) -> list[OHLCVBar]:
    """Return the most recent `limit` bars from the DB, refreshing from the configured provider if stale.

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
        # DB is cold — fetch the full recent window from the configured provider.
        new_bars = await _fetch_provider_latest(db, instrument, timeframe, limit, adjusted)
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
        repair_start = await _latest_window_start(db, timeframe, limit)
        repair_end = oldest_ts - timedelta(seconds=1)
        if repair_end > repair_start:
            try:
                repair_bars = await _fetch_provider(
                    db,
                    instrument,
                    timeframe,
                    repair_start,
                    repair_end,
                    adjusted,
                )
            except ProviderNoDataError:
                repair_bars = []
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
        try:
            new_bars = await _fetch_provider(
                db, instrument, timeframe, latest_ts, datetime.now(UTC), adjusted
            )
        except ProviderNoDataError:
            new_bars = []
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
    hitting the external provider.
    """
    if instrument.is_synthetic:
        from app.models.synthetic_constituent import SyntheticConstituent

        constituents_result = await db.execute(
            select(SyntheticConstituent).where(
                SyntheticConstituent.synthetic_instrument_id == instrument.id
            )
        )
        constituents = list(constituents_result.scalars().all())

        # Seed historical data for each constituent before `before`.
        # Mirrors the non-synthetic on-demand fetch path so that panning left
        # past the initial window works for expression instruments.
        for c in constituents:
            const_instr = await db.get(Instrument, c.constituent_instrument_id)
            if const_instr is not None and not const_instr.is_synthetic:
                await db.refresh(const_instr, ["listings"])
                await fetch_ohlcv_page_before(db, const_instr, timeframe, before, limit, adjusted)

        bars = await recompute_synthetic_ohlcv(db, instrument, timeframe)
        filtered = [b for b in bars if b.ts < before]
        return filtered[-limit:] if len(filtered) > limit else filtered

    """
    DB-first: queries the local cache. If the DB has fewer rows than requested,
    falls back to a live provider fetch for the missing historical range
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
        # DB doesn't have enough older bars — repair only the missing older tail,
        # with a small overlap for weekends/late provider revisions. Never request
        # the entire epoch for a bounded pagination page.
        oldest_cached = min((row.ts for row in rows), default=None)
        missing_count = max(limit - len(rows), 1)
        repair_start = _historical_repair_start(
            before, timeframe, missing_count, oldest_cached
        )
        repair_end = _as_utc(oldest_cached) - timedelta(seconds=1) if oldest_cached else before
        try:
            fetched = await _fetch_provider(
                db, instrument, timeframe, repair_start, repair_end, adjusted
            )
        except ProviderNoDataError:
            fetched = []
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


async def _fetch_provider_latest(
    db: AsyncSession,
    instrument: Instrument,
    timeframe: Timeframe,
    limit: int,
    adjusted: bool,
) -> list[OHLCVBar]:
    """Fetch approximately `limit` recent bars from the configured provider when DB is cold."""
    execution = await execute_provider_call(
        db,
        ProviderCapability.PRICE_HISTORY,
        f"fetch_latest_ohlcv:{timeframe.value}",
        instrument_id=instrument.id,
        invoke=lambda provider, _provider_symbol: provider.fetch_latest_ohlcv(
            provider_symbol_for_instrument(instrument, provider.name),
            timeframe,
            limit,
            adjusted=adjusted,
            instrument_id=instrument.id,
            data_source_id=0,
        ),
        response_items=lambda result: len(result),
        treat_empty_as_failure=True,
    )
    provider_symbol = provider_symbol_for_instrument(instrument, execution.provider_name)
    bars = execution.result[-limit:] if len(execution.result) > limit else execution.result
    for bar in bars:
        bar.instrument_id = instrument.id
        bar.data_source_id = execution.data_source.id
    await _record_bar_observations(
        db,
        bars,
        data_source_id=execution.data_source.id,
        provider_symbol=provider_symbol,
    )
    await _touch_ohlcv_dataset_state(
        db,
        instrument,
        data_source_id=execution.data_source.id,
        timeframe=timeframe,
        adjusted=adjusted,
        bars=bars,
    )
    return bars


async def get_current_price_async(
    db: AsyncSession,
    instrument: Instrument,
) -> float | None:
    cached = await _fresh_latest_price_from_cache(db, instrument)
    if cached is not None:
        return cached
    execution = await execute_provider_call(
        db,
        ProviderCapability.LATEST_PRICE,
        "get_current_price",
        instrument_id=instrument.id,
        invoke=lambda provider, _provider_symbol: provider.get_current_price(
            provider_symbol_for_instrument(instrument, provider.name)
        ),
        response_items=lambda result: 1 if result is not None else 0,
        treat_empty_as_failure=True,
    )
    provider_symbol = provider_symbol_for_instrument(instrument, execution.provider_name)
    await store_latest_price_snapshot(
        db,
        instrument_id=instrument.id,
        data_source_id=execution.data_source.id,
        provider_symbol=provider_symbol,
        price=execution.result,
    )
    return execution.result


def get_current_price(provider_symbol: str) -> float | None:
    raise RuntimeError("get_current_price() is no longer used; use get_current_price_async()")


async def search_provider_instruments_async(db: AsyncSession, query: str) -> list[dict]:
    cached = await _fresh_search_from_cache(db, query)
    if cached is not None:
        return sorted(cached, key=lambda item: _search_priority(query, item))[:10]

    chain = await resolve_provider_chain(db, ProviderCapability.INSTRUMENT_SEARCH)
    merged: list[dict] = []
    seen: set[str] = set()
    for resolved in chain:
        try:
            execution = await execute_provider_call(
                db,
                ProviderCapability.INSTRUMENT_SEARCH,
                "search_instruments",
                provider_name=resolved.provider_name,
                invoke=lambda provider, _provider_symbol: provider.search_instruments(
                    query, limit=10
                ),
                response_items=lambda result: len(result),
                treat_empty_as_failure=False,
            )
        except Exception:
            continue
        await store_search_snapshot(
            db,
            data_source_id=execution.data_source.id,
            query=query,
            results=execution.result,
        )
        for item in _search_results_from_payload(
            {
                "results": [
                    {
                        "symbol": result.symbol,
                        "name": result.name,
                        "exchange": result.exchange,
                        "instrument_type": result.instrument_type,
                    }
                    for result in execution.result
                ]
            },
            provider_name=execution.provider_name,
        ):
            symbol = item.get("symbol", "")
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            merged.append(item)
    return sorted(merged, key=lambda item: _search_priority(query, item))[:10]


def search_provider_instruments(query: str) -> list[dict]:
    raise RuntimeError(
        "search_provider_instruments() is no longer used; use search_provider_instruments_async()"
    )


async def get_provider_profile_async(
    db: AsyncSession,
    provider_symbol: str,
    *,
    instrument_id: int | None = None,
    provider_name: str | None = None,
    persist: bool = True,
):
    cached = await _fresh_profile_from_cache(
        db,
        instrument_id=instrument_id,
        provider_symbol=provider_symbol,
    )
    if cached is not None:
        return cached
    try:
        execution = await execute_provider_call(
            db,
            ProviderCapability.INSTRUMENT_METADATA,
            "get_instrument_profile",
            instrument_id=instrument_id,
            provider_symbol=provider_symbol,
            provider_name=provider_name,
            invoke=lambda provider, actual_symbol: provider.get_instrument_profile(
                actual_symbol or provider_symbol
            ),
            response_items=lambda result: 1 if result is not None else 0,
            treat_empty_as_failure=True,
        )
    except Exception:
        return None
    if not persist:
        return execution.result
    instrument = None
    if instrument_id is not None:
        instrument = await db.get(Instrument, instrument_id)
    await ingest_provider_profile(db, execution.result, instrument=instrument)
    return execution.result


def get_provider_instrument_info(provider_symbol: str) -> dict:
    raise RuntimeError(
        "get_provider_instrument_info() is no longer used; use get_provider_profile_async()"
    )
