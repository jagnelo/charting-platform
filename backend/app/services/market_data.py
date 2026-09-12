"""
Market data service with a provider-agnostic cache boundary.

Synthetic instruments (is_synthetic=True) are routed through the expression
engine rather than fetched from an external provider. Their OHLCV is computed
from constituent bars and written to the standard ohlcv_bar table so the rest
of the system (chart, alert, indicator, screener) reads them transparently.
"""

import asyncio
import hashlib
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, TypeVar

import numpy as np
from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.config import settings
from app.models.data_source import DataSource
from app.models.instrument import Instrument
from app.models.market_data_foundation import AdjustmentBasis, MarketSeries, MarketSeriesDefault
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
from app.providers.alpaca import (
    estimate_latest_ohlcv_request_count,
    estimate_ohlcv_request_count,
)
from app.providers.base import InstrumentProfile
from app.providers.binance import (
    estimate_latest_ohlcv_request_weight,
    estimate_ohlcv_request_weight,
)
from app.providers.crypto_market_data import (
    estimate_coinbase_latest_ohlcv_request_count,
    estimate_coinbase_ohlcv_request_count,
    estimate_kraken_latest_ohlcv_request_count,
    estimate_kraken_ohlcv_request_count,
)
from app.providers.errors import bounded_redact_provider_message
from app.providers.ibkr import (
    estimate_ibkr_current_price_request_count,
    estimate_ibkr_latest_ohlcv_request_count,
    estimate_ibkr_ohlcv_request_count,
)
from app.providers.optional_market_data import (
    estimate_marketstack_latest_ohlcv_request_count,
    estimate_marketstack_ohlcv_request_count,
    estimate_twelve_data_latest_ohlcv_request_count,
    estimate_twelve_data_ohlcv_request_count,
)
from app.services.distributed_locks import (
    redis_distributed_lock,
    shared_redis_lock_client,
)
from app.services.instrument_mastering import ingest_provider_profile, reconcile_instrument_profile
from app.services.market_series import SeriesScope, get_or_create_series
from app.services.ohlcv_coverage import assess_ohlcv_coverage, missing_range_slices
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
_T = TypeVar("_T")

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_OHLCV_CONFLICT_COLUMNS = [
    "instrument_id",
    "timeframe",
    "ts",
    "is_adjusted",
    "scope_key",
]

# Process-local coalescing for identical interactive refreshes. Durable
# background refresh jobs provide cross-worker coalescing; this map prevents
# concurrent requests handled by one process from independently spending the
# same provider quota before the first transaction commits its bars.
_OHLCV_REFRESH_LOCKS: dict[tuple[int, str, datetime, datetime | None, bool], asyncio.Lock] = {}
_OHLCV_REFRESH_LOCK_USERS: dict[tuple[int, str, datetime, datetime | None, bool], int] = {}


def _ohlcv_refresh_lock_key(
    instrument: Instrument,
    timeframe: Timeframe,
    start: datetime,
    end: datetime | None,
    adjusted: bool,
) -> tuple[int, str, datetime, datetime | None, bool]:
    return (
        instrument.id,
        timeframe.value,
        _as_utc(start),
        _as_utc(end) if end is not None else None,
        adjusted,
    )


async def _acquire_database_refresh_lock(
    db: AsyncSession,
    lock_key: tuple[int, str, datetime, datetime | None, bool],
) -> None:
    """Serialize an exact refresh key across PostgreSQL workers/hosts.

    PostgreSQL transaction-scoped advisory locks are deliberately optional:
    SQLite/unit doubles have no equivalent and continue using only the local
    asyncio gate. The lock is held until the refresh transaction commits or
    rolls back, so a waiter can safely re-read the newly persisted coverage.
    """

    bind = getattr(db, "bind", None)
    if bind is None:
        bind = getattr(getattr(db, "sync_session", None), "bind", None)
    if getattr(getattr(bind, "dialect", None), "name", None) != "postgresql":
        return

    digest = hashlib.sha256(repr(lock_key).encode("utf-8")).digest()
    advisory_key = int.from_bytes(digest[:8], byteorder="big", signed=True)
    await db.execute(select(func.pg_advisory_xact_lock(advisory_key)))


def _e2e_fixture_bar_condition():
    """Return the controlled-bar predicate used by seeded visual tests.

    Seeded browser runs must be hermetic: a provider refresh must never mix
    canonical/provider bars into the deterministic e2e_reference dataset.
    Production and ordinary test runs retain the normal provider-neutral read
    path when the flag is disabled.
    """
    return (
        OHLCVBar.data_source_id
        == select(DataSource.id).where(DataSource.name == "e2e_reference").scalar_subquery()
    )


def _default_series_bar_condition(
    instrument_id: int,
    timeframe: Timeframe,
    adjusted: bool,
):
    """Restrict compatibility reads to one selected series.

    New provider writes create an explicit default mapping.  The canonical
    series fallback handles rows created before that mapping existed, while
    the legacy branch keeps old symbol-based rows readable when no series has
    ever been recorded for the scope.
    """

    mapping = select(MarketSeriesDefault.market_series_id).where(
        MarketSeriesDefault.instrument_id == instrument_id,
        MarketSeriesDefault.timeframe == timeframe.value,
        MarketSeriesDefault.is_adjusted == adjusted,
    )
    mapped_id = mapping.scalar_subquery()
    mapped_bar = aliased(OHLCVBar)
    mapping_target_has_bars = (
        select(MarketSeriesDefault.id)
        .join(MarketSeries, MarketSeries.id == MarketSeriesDefault.market_series_id)
        .join(mapped_bar, mapped_bar.market_series_id == MarketSeries.id)
        .where(
            MarketSeriesDefault.instrument_id == instrument_id,
            MarketSeriesDefault.timeframe == timeframe.value,
            MarketSeriesDefault.is_adjusted == adjusted,
            MarketSeries.is_active.is_(True),
            mapped_bar.instrument_id == instrument_id,
            mapped_bar.timeframe == timeframe,
            mapped_bar.is_adjusted == adjusted,
        )
        .exists()
    )
    adjustment_predicate = (
        MarketSeries.adjustment_basis != AdjustmentBasis.RAW
        if adjusted
        else MarketSeries.adjustment_basis == AdjustmentBasis.RAW
    )
    canonical = (
        select(MarketSeries.id)
        .where(
            MarketSeries.instrument_id == instrument_id,
            MarketSeries.timeframe == timeframe.value,
            MarketSeries.is_canonical.is_(True),
            MarketSeries.is_active.is_(True),
            adjustment_predicate,
        )
        .order_by(MarketSeries.id)
        .limit(1)
    )
    canonical_id = canonical.scalar_subquery()
    canonical_bar = aliased(OHLCVBar)
    canonical_has_bars = (
        select(canonical_bar.id)
        .where(
            canonical_bar.instrument_id == instrument_id,
            canonical_bar.timeframe == timeframe,
            canonical_bar.is_adjusted == adjusted,
            canonical_bar.market_series_id == canonical_id,
        )
        .exists()
    )
    return or_(
        and_(mapping_target_has_bars, OHLCVBar.market_series_id == mapped_id),
        and_(
            ~mapping_target_has_bars,
            canonical_has_bars,
            OHLCVBar.market_series_id == canonical_id,
        ),
        and_(
            ~mapping_target_has_bars,
            ~canonical_has_bars,
            OHLCVBar.market_series_id.is_(None),
        ),
    )


def _seeded_market_data() -> bool:
    return bool(settings.E2E_SEED_MARKET_DATA)


def _coverage_calendar(instrument: Instrument) -> str | None:
    """Use the local XNYS calendar only for explicitly USD instruments."""
    return "XNYS" if (instrument.currency or "").upper() == "USD" else None


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


def _is_positive_repair_slice(start: datetime, end: datetime) -> bool:
    """Return whether a repair interval can contain an observable time range.

    The exchange-calendar gap planner intentionally represents a single missing
    session as ``(session, session)``.  That is useful for coverage reporting,
    but it is not a provider request interval: a zero-width request can return
    no rows and incorrectly exhaust the provider chain.  Provider ingestion
    therefore skips these intervals and leaves the calendar gap eligible for a
    later session-specific repair.
    """
    return _as_utc(end) > _as_utc(start)


def _is_recoverable_provider_gap(exc: Exception) -> bool:
    """Identify provider availability failures that may leave cached data usable.

    A provider circuit can open between two repair slices (for example after a
    transient public-endpoint failure).  The runtime historically surfaced
    that state as ``RuntimeError`` rather than ``ProviderNoDataError``.  A
    non-cold range should retain its valid cached bars and continue repairing
    other slices; cold loads still re-raise below.
    """
    return isinstance(exc, ProviderNoDataError) or (
        isinstance(exc, RuntimeError)
        and str(exc).startswith("No enabled providers available for capability")
    )


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
                "market_series_id": pg_insert(MarketBarObservation).excluded.market_series_id,
                "session": pg_insert(MarketBarObservation).excluded.session,
                "scope_key": pg_insert(MarketBarObservation).excluded.scope_key,
                "observed_at": pg_insert(MarketBarObservation).excluded.observed_at,
                "open": pg_insert(MarketBarObservation).excluded.open,
                "high": pg_insert(MarketBarObservation).excluded.high,
                "low": pg_insert(MarketBarObservation).excluded.low,
                "close": pg_insert(MarketBarObservation).excluded.close,
                "volume": pg_insert(MarketBarObservation).excluded.volume,
                "vwap": pg_insert(MarketBarObservation).excluded.vwap,
                "adjustment_basis": pg_insert(MarketBarObservation).excluded.adjustment_basis,
                "adjustment_version": pg_insert(MarketBarObservation).excluded.adjustment_version,
                "source_payload": pg_insert(MarketBarObservation).excluded.source_payload,
            },
        ),
        [
            {
                "instrument_id": bar.instrument_id,
                "data_source_id": data_source_id,
                "market_series_id": bar.market_series_id,
                "provider_symbol": provider_symbol,
                "timeframe": bar.timeframe,
                "session": bar.session,
                "scope_key": _bar_scope_key(bar),
                "ts": bar.ts,
                "observed_at": observed_at,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "vwap": bar.vwap,
                "is_adjusted": bar.is_adjusted,
                "adjustment_basis": bar.adjustment_basis,
                "adjustment_version": bar.adjustment_version,
                "source_payload": bar.provenance,
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
            index_elements=_OHLCV_CONFLICT_COLUMNS,
            set_={
                "open": insert_stmt.excluded.open,
                "high": insert_stmt.excluded.high,
                "low": insert_stmt.excluded.low,
                "close": insert_stmt.excluded.close,
                "volume": insert_stmt.excluded.volume,
                "vwap": insert_stmt.excluded.vwap,
                "data_source_id": insert_stmt.excluded.data_source_id,
                "market_series_id": insert_stmt.excluded.market_series_id,
                "session": insert_stmt.excluded.session,
                "scope_key": insert_stmt.excluded.scope_key,
                "adjustment_basis": insert_stmt.excluded.adjustment_basis,
                "adjustment_version": insert_stmt.excluded.adjustment_version,
                "provenance": insert_stmt.excluded.provenance,
            },
        )
    else:
        insert_stmt = insert_stmt.on_conflict_do_nothing(
            index_elements=_OHLCV_CONFLICT_COLUMNS
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
                _default_series_bar_condition(
                    c.constituent_instrument_id, timeframe, True
                ),
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
                                index_elements=_OHLCV_CONFLICT_COLUMNS
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
                "session": "regular",
                "scope_key": "legacy:regular",
                "adjustment_basis": "derived",
                "adjustment_version": "expression-engine",
                "provenance": {
                    "provider": "synthetic_expression",
                    "expression": instrument.expression,
                    "constituent_instrument_ids": [
                        c.constituent_instrument_id for c in constituents
                    ],
                },
            }
        )

    if new_bars:
        try:
            await db.execute(
                pg_insert(OHLCVBar).on_conflict_do_update(
                    index_elements=_OHLCV_CONFLICT_COLUMNS,
                    set_={
                        "open": pg_insert(OHLCVBar).excluded.open,
                        "high": pg_insert(OHLCVBar).excluded.high,
                        "low": pg_insert(OHLCVBar).excluded.low,
                        "close": pg_insert(OHLCVBar).excluded.close,
                        "data_source_id": pg_insert(OHLCVBar).excluded.data_source_id,
                        "session": pg_insert(OHLCVBar).excluded.session,
                        "adjustment_basis": pg_insert(OHLCVBar).excluded.adjustment_basis,
                        "adjustment_version": pg_insert(OHLCVBar).excluded.adjustment_version,
                        "provenance": pg_insert(OHLCVBar).excluded.provenance,
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
        .where(
            OHLCVBar.instrument_id == instrument.id,
            OHLCVBar.timeframe == timeframe,
            OHLCVBar.is_adjusted.is_(True),
            _default_series_bar_condition(instrument.id, timeframe, True),
        )
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
    *,
    allow_provider_fetch: bool = True,
    redis: Any = None,
) -> list[OHLCVBar]:
    """Read/refresh OHLCV with identical in-process requests coalesced.

    The lock covers the complete cache-read, provider-refresh, and persistence
    transaction. A waiter therefore re-enters the implementation only after
    the first caller has committed, allowing the normal coverage check to
    return the newly persisted bars without another provider request. Local
    only and synthetic reads remain lock-free. When explicitly enabled, the
    same key is also held in Redis so deployments that do not share one
    PostgreSQL transaction boundary still coalesce refreshes safely.
    """

    return await _with_ohlcv_refresh_gate(
        instrument,
        timeframe,
        start,
        end,
        adjusted,
        allow_provider_fetch=allow_provider_fetch,
        redis=redis,
        operation=lambda: _fetch_ohlcv_impl(
            db,
            instrument,
            timeframe,
            start,
            end,
            adjusted,
            allow_provider_fetch=allow_provider_fetch,
        ),
    )


async def _with_ohlcv_refresh_gate(
    instrument: Instrument,
    timeframe: Timeframe,
    start: datetime,
    end: datetime | None,
    adjusted: bool,
    *,
    allow_provider_fetch: bool,
    redis: Any = None,
    operation: Callable[[], Awaitable[_T]],
) -> _T:
    """Coalesce one provider-capable OHLCV operation in this process.

    The operation is supplied as a coroutine factory so cache-only and
    synthetic reads avoid creating or retaining an unnecessary lock. Callers
    use stable sentinels for implicit latest/page ranges, keeping those paths
    coordinated without pretending that their provider request shape is the
    same as an explicit historical range.
    """

    if not allow_provider_fetch or instrument.is_synthetic:
        return await operation()

    lock_key = _ohlcv_refresh_lock_key(instrument, timeframe, start, end, adjusted)
    lock = _OHLCV_REFRESH_LOCKS.setdefault(lock_key, asyncio.Lock())
    _OHLCV_REFRESH_LOCK_USERS[lock_key] = _OHLCV_REFRESH_LOCK_USERS.get(lock_key, 0) + 1
    try:
        async with lock:
            distributed_redis = None
            if settings.OHLCV_DISTRIBUTED_LOCK_ENABLED:
                distributed_redis = redis or shared_redis_lock_client()
            if distributed_redis is None:
                return await operation()
            async with redis_distributed_lock(
                distributed_redis,
                namespace="ohlcv-refresh",
                identity=repr(lock_key),
                ttl_seconds=settings.OHLCV_DISTRIBUTED_LOCK_TTL_SECONDS,
                blocking_timeout_seconds=settings.OHLCV_DISTRIBUTED_LOCK_WAIT_SECONDS,
                retry_interval_seconds=settings.OHLCV_DISTRIBUTED_LOCK_RETRY_SECONDS,
            ):
                return await operation()
    finally:
        remaining = _OHLCV_REFRESH_LOCK_USERS[lock_key] - 1
        if remaining:
            _OHLCV_REFRESH_LOCK_USERS[lock_key] = remaining
        else:
            _OHLCV_REFRESH_LOCK_USERS.pop(lock_key, None)
            _OHLCV_REFRESH_LOCKS.pop(lock_key, None)


async def _fetch_ohlcv_impl(
    db: AsyncSession,
    instrument: Instrument,
    timeframe: Timeframe,
    start: datetime,
    end: datetime | None = None,
    adjusted: bool = True,
    *,
    allow_provider_fetch: bool = True,
) -> list[OHLCVBar]:
    # Synthetic instruments use computed OHLCV, not an external provider.
    if instrument.is_synthetic:
        bars = await recompute_synthetic_ohlcv(db, instrument, timeframe)
        if end is None:
            end = datetime.now(UTC)
        return [b for b in bars if b.ts >= start and b.ts <= end]

    await _acquire_database_refresh_lock(
        db,
        _ohlcv_refresh_lock_key(instrument, timeframe, start, end, adjusted),
    )

    if end is None:
        end = datetime.now(UTC)

    predicates = [
        OHLCVBar.instrument_id == instrument.id,
        OHLCVBar.timeframe == timeframe,
        OHLCVBar.ts >= start,
        OHLCVBar.ts <= end,
        OHLCVBar.is_adjusted == adjusted,
        _default_series_bar_condition(instrument.id, timeframe, adjusted),
    ]
    if _seeded_market_data():
        predicates.append(_e2e_fixture_bar_condition())
    stmt = select(OHLCVBar).where(and_(*predicates)).order_by(OHLCVBar.ts)
    cached = list((await db.execute(stmt)).scalars().all())

    # A seeded visual run is intentionally local-only.  Returning the fixture
    # range here prevents a cold or stale fixture from opening the provider
    # chain and reintroducing nondeterministic bars.
    if _seeded_market_data():
        return cached

    if not allow_provider_fetch:
        cached.sort(key=lambda b: b.ts)
        return cached

    calendar = _coverage_calendar(instrument)
    if _needs_fetch_for_range(cached, timeframe, start, end, calendar=calendar):
        repair_slices = missing_range_slices(cached, timeframe, start, end, calendar=calendar)
        # A current-window request may have no obvious bounded gap while still
        # needing a freshness refresh. In that case retain the existing range
        # fetch semantics; historical/internal gaps use only their slices.
        if not repair_slices:
            repair_slices = [(start, end)]
        new_bars: list[OHLCVBar] = []
        for repair_start, repair_end in repair_slices:
            if not _is_positive_repair_slice(repair_start, repair_end):
                continue
            try:
                new_bars.extend(
                    await _fetch_provider(
                        db, instrument, timeframe, repair_start, repair_end, adjusted
                    )
                )
            except Exception as exc:
                if not _is_recoverable_provider_gap(exc) or not cached:
                    raise
                logger.warning(
                    "Skipping unavailable provider repair slice %s to %s: %s",
                    repair_start,
                    repair_end,
                    bounded_redact_provider_message(exc),
                )
        if new_bars:
            try:
                await db.execute(
                    pg_insert(OHLCVBar).on_conflict_do_nothing(
                        index_elements=_OHLCV_CONFLICT_COLUMNS
                    ),
                    [_bar_as_dict(b) for b in new_bars],
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
    *,
    calendar: str | None = None,
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

    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)

    threshold = _TF_STALENESS.get(timeframe, timedelta(minutes=20))
    range_is_historical = end <= (datetime.now(UTC) - threshold)
    assessment = assess_ohlcv_coverage(
        cached,
        timeframe,
        start,
        end,
        mode="historical" if range_is_historical else "latest",
        freshness_seconds=int(threshold.total_seconds()),
        calendar=calendar if calendar == "XNYS" else None,
    )
    return assessment.status.value != "ready"


async def _fetch_provider(
    db: AsyncSession,
    instrument: Instrument,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    adjusted: bool,
) -> list[OHLCVBar]:
    alpaca_cost = estimate_ohlcv_request_count(timeframe, start, end)
    binance_cost = estimate_ohlcv_request_weight(timeframe, start, end)
    coinbase_cost = estimate_coinbase_ohlcv_request_count(timeframe, start, end)
    kraken_cost = estimate_kraken_ohlcv_request_count(timeframe, start, end)
    marketstack_cost = estimate_marketstack_ohlcv_request_count(timeframe, start, end)
    twelve_data_cost = estimate_twelve_data_ohlcv_request_count(timeframe, start, end)
    ibkr_cost = estimate_ibkr_ohlcv_request_count(timeframe, start, end)
    operation_cost_overrides = {
        **({"alpaca": alpaca_cost} if alpaca_cost is not None else {}),
        **({"binance": binance_cost} if binance_cost is not None else {}),
        **({"coinbase": coinbase_cost} if coinbase_cost is not None else {}),
        **({"kraken": kraken_cost} if kraken_cost is not None else {}),
        **({"marketstack": marketstack_cost} if marketstack_cost is not None else {}),
        **({"twelve_data": twelve_data_cost} if twelve_data_cost is not None else {}),
        **({"ibkr": ibkr_cost} if ibkr_cost is not None else {}),
    }
    execution = await execute_provider_call(
        db,
        ProviderCapability.PRICE_HISTORY,
        f"fetch_ohlcv:{timeframe.value}",
        instrument_id=instrument.id,
        usage_identity=lambda provider_name: provider_symbol_for_instrument(instrument, provider_name),
        operation_cost_overrides=operation_cost_overrides or None,
        adjusted=adjusted,
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
    bars = await _attach_provider_series(
        db,
        instrument,
        timeframe,
        adjusted,
        execution,
    )
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


async def _attach_provider_series(
    db: AsyncSession,
    instrument: Instrument,
    timeframe: Timeframe,
    adjusted: bool,
    execution: Any,
    *,
    bars: list[OHLCVBar] | None = None,
) -> list[OHLCVBar]:
    """Attach a deterministic canonical series to every provider bar result.

    Historical and latest-window fetches share the same persistence path. The
    helper keeps both paths from falling back to legacy ``NULL`` series IDs,
    which would otherwise be hidden once a default mapping is created.
    """

    provider_symbol = provider_symbol_for_instrument(instrument, execution.provider_name)
    bars = execution.result if bars is None else bars
    for bar in bars:
        bar.instrument_id = instrument.id
        bar.data_source_id = execution.data_source.id
    if not bars:
        return bars

    grouped: dict[tuple[str, AdjustmentBasis, str, str], list[OHLCVBar]] = {}
    for bar in bars:
        try:
            basis_value = getattr(bar.adjustment_basis, "value", bar.adjustment_basis)
            adjustment_basis = AdjustmentBasis(str(basis_value))
        except ValueError:
            adjustment_basis = AdjustmentBasis.PROVIDER_ADJUSTED if adjusted else AdjustmentBasis.RAW
        session_code = str(bar.session or "regular").strip() or "regular"
        adjustment_version = str(bar.adjustment_version or "legacy")
        feed_scope = str((bar.provenance or {}).get("feed") or "provider_native")
        grouped.setdefault(
            (session_code, adjustment_basis, adjustment_version, feed_scope), []
        ).append(bar)

    for (session_code, adjustment_basis, adjustment_version, feed_scope), scoped_bars in grouped.items():
        series = await get_or_create_series(
            db,
            SeriesScope(
                instrument_id=instrument.id,
                data_source_id=execution.data_source.id,
                feed_scope=feed_scope,
                session_code=session_code,
                timeframe=timeframe.value,
                adjustment_basis=adjustment_basis,
                adjustment_version=adjustment_version,
            ),
            canonical=True,
            source_series_key=(
                f"{execution.provider_name}:{provider_symbol}:{timeframe.value}:"
                f"{feed_scope}:{session_code}:{adjustment_basis.value}:{adjustment_version}"
            ),
            provenance={
                "provider": execution.provider_name,
                "provider_symbol": provider_symbol,
                "feed_scope": feed_scope,
                "session": session_code,
                "timeframe": timeframe.value,
                "adjustment_basis": adjustment_basis.value,
                "adjustment_version": adjustment_version,
                "bar_count": len(scoped_bars),
            },
        )
        for bar in scoped_bars:
            bar.market_series_id = series.id
    return bars


async def fetch_ohlcv_latest(
    db: AsyncSession,
    instrument: Instrument,
    timeframe: Timeframe,
    limit: int,
    adjusted: bool = True,
    *,
    allow_provider_fetch: bool = True,
    redis: Any = None,
) -> list[OHLCVBar]:
    """Return the most recent ``limit`` bars with refresh coalescing."""
    return await _with_ohlcv_refresh_gate(
        instrument,
        timeframe,
        _EPOCH,
        None,
        adjusted,
        allow_provider_fetch=allow_provider_fetch,
        redis=redis,
        operation=lambda: _fetch_ohlcv_latest_impl(
            db,
            instrument,
            timeframe,
            limit,
            adjusted,
            allow_provider_fetch=allow_provider_fetch,
        ),
    )


async def _fetch_ohlcv_latest_impl(
    db: AsyncSession,
    instrument: Instrument,
    timeframe: Timeframe,
    limit: int,
    adjusted: bool = True,
    *,
    allow_provider_fetch: bool = True,
) -> list[OHLCVBar]:
    """Implementation for :func:`fetch_ohlcv_latest` after gate admission."""
    if instrument.is_synthetic:
        bars = await recompute_synthetic_ohlcv(db, instrument, timeframe)
        return bars[-limit:] if len(bars) > limit else bars
    await _acquire_database_refresh_lock(
        db,
        _ohlcv_refresh_lock_key(instrument, timeframe, _EPOCH, None, adjusted),
    )
    predicates = [
        OHLCVBar.instrument_id == instrument.id,
        OHLCVBar.timeframe == timeframe,
        OHLCVBar.is_adjusted == adjusted,
        _default_series_bar_condition(instrument.id, timeframe, adjusted),
    ]
    if _seeded_market_data():
        predicates.append(_e2e_fixture_bar_condition())
    stmt = select(OHLCVBar).where(and_(*predicates)).order_by(OHLCVBar.ts.desc()).limit(limit)
    rows = list((await db.execute(stmt)).scalars().all())
    rows.sort(key=lambda b: b.ts)  # return chronological order

    if _seeded_market_data():
        return rows

    if not allow_provider_fetch:
        return rows

    if not rows:
        # DB is cold — fetch the full recent window from the configured provider.
        new_bars = await _fetch_provider_latest(db, instrument, timeframe, limit, adjusted)
        if new_bars:
            try:
                await db.execute(
                    pg_insert(OHLCVBar).on_conflict_do_nothing(
                        index_elements=_OHLCV_CONFLICT_COLUMNS
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
                            index_elements=_OHLCV_CONFLICT_COLUMNS,
                            set_={
                                "open": pg_insert(OHLCVBar).excluded.open,
                                "high": pg_insert(OHLCVBar).excluded.high,
                                "low": pg_insert(OHLCVBar).excluded.low,
                                "close": pg_insert(OHLCVBar).excluded.close,
                                "volume": pg_insert(OHLCVBar).excluded.volume,
                                "vwap": pg_insert(OHLCVBar).excluded.vwap,
                                "data_source_id": pg_insert(OHLCVBar).excluded.data_source_id,
                                "market_series_id": pg_insert(OHLCVBar).excluded.market_series_id,
                                "session": pg_insert(OHLCVBar).excluded.session,
                                "adjustment_basis": pg_insert(OHLCVBar).excluded.adjustment_basis,
                                "adjustment_version": pg_insert(OHLCVBar).excluded.adjustment_version,
                                "provenance": pg_insert(OHLCVBar).excluded.provenance,
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
                        index_elements=_OHLCV_CONFLICT_COLUMNS,
                        set_={
                            "open": pg_insert(OHLCVBar).excluded.open,
                            "high": pg_insert(OHLCVBar).excluded.high,
                            "low": pg_insert(OHLCVBar).excluded.low,
                            "close": pg_insert(OHLCVBar).excluded.close,
                            "volume": pg_insert(OHLCVBar).excluded.volume,
                            "vwap": pg_insert(OHLCVBar).excluded.vwap,
                            "data_source_id": pg_insert(OHLCVBar).excluded.data_source_id,
                            "market_series_id": pg_insert(OHLCVBar).excluded.market_series_id,
                            "session": pg_insert(OHLCVBar).excluded.session,
                            "adjustment_basis": pg_insert(OHLCVBar).excluded.adjustment_basis,
                            "adjustment_version": pg_insert(OHLCVBar).excluded.adjustment_version,
                            "provenance": pg_insert(OHLCVBar).excluded.provenance,
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
    *,
    allow_provider_fetch: bool = True,
    redis: Any = None,
) -> list[OHLCVBar]:
    """Return up to ``limit`` bars strictly before ``before`` with coalescing."""
    return await _with_ohlcv_refresh_gate(
        instrument,
        timeframe,
        _EPOCH,
        before,
        adjusted,
        allow_provider_fetch=allow_provider_fetch,
        redis=redis,
        operation=lambda: _fetch_ohlcv_page_before_impl(
            db,
            instrument,
            timeframe,
            before,
            limit,
            adjusted,
            allow_provider_fetch=allow_provider_fetch,
        ),
    )


async def _fetch_ohlcv_page_before_impl(
    db: AsyncSession,
    instrument: Instrument,
    timeframe: Timeframe,
    before: datetime,
    limit: int,
    adjusted: bool = True,
    *,
    allow_provider_fetch: bool = True,
) -> list[OHLCVBar]:
    """Implementation for :func:`fetch_ohlcv_page_before` after gate admission."""
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
                await fetch_ohlcv_page_before(
                    db,
                    const_instr,
                    timeframe,
                    before,
                    limit,
                    adjusted,
                    allow_provider_fetch=allow_provider_fetch,
                )

        bars = await recompute_synthetic_ohlcv(db, instrument, timeframe)
        filtered = [b for b in bars if b.ts < before]
        return filtered[-limit:] if len(filtered) > limit else filtered

    await _acquire_database_refresh_lock(
        db,
        _ohlcv_refresh_lock_key(instrument, timeframe, _EPOCH, before, adjusted),
    )

    """
    DB-first: queries the local cache. If the DB has fewer rows than requested,
    falls back to a live provider fetch for the missing historical range
    (EPOCH → before), stores the results, then re-queries. This ensures
    pagination works correctly even when the background bulk fetch hasn't
    finished writing all historical bars yet.
    """
    predicates = [
        OHLCVBar.instrument_id == instrument.id,
        OHLCVBar.timeframe == timeframe,
        OHLCVBar.is_adjusted == adjusted,
        OHLCVBar.ts < before,
        _default_series_bar_condition(instrument.id, timeframe, adjusted),
    ]
    if _seeded_market_data():
        predicates.append(_e2e_fixture_bar_condition())
    stmt = select(OHLCVBar).where(and_(*predicates)).order_by(OHLCVBar.ts.desc()).limit(limit)
    rows = list((await db.execute(stmt)).scalars().all())

    if _seeded_market_data():
        rows.sort(key=lambda b: b.ts)
        return rows

    if not allow_provider_fetch:
        rows.sort(key=lambda b: b.ts)
        return rows

    if len(rows) < limit:
        # DB doesn't have enough older bars — repair only the missing older tail,
        # with a small overlap for weekends/late provider revisions. Never request
        # the entire epoch for a bounded pagination page.
        oldest_cached = min((row.ts for row in rows), default=None)
        missing_count = max(limit - len(rows), 1)
        repair_start = _historical_repair_start(before, timeframe, missing_count, oldest_cached)
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
                        index_elements=_OHLCV_CONFLICT_COLUMNS
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


def _bar_scope_key(b: OHLCVBar) -> str:
    """Return the persisted conflict key for a scoped or legacy bar."""

    session = str(b.session or "regular").strip() or "regular"
    if b.market_series_id is None:
        return f"legacy:{session}"
    return f"series:{b.market_series_id}:{session}"


def _bar_as_dict(b: OHLCVBar) -> dict:
    return {
        "instrument_id": b.instrument_id,
        "data_source_id": b.data_source_id,
        "market_series_id": b.market_series_id,
        "timeframe": b.timeframe,
        "ts": b.ts,
        "session": b.session,
        "scope_key": _bar_scope_key(b),
        "open": b.open,
        "high": b.high,
        "low": b.low,
        "close": b.close,
        "volume": b.volume,
        "vwap": b.vwap,
        "is_adjusted": b.is_adjusted,
        "adjustment_basis": b.adjustment_basis,
        "adjustment_version": b.adjustment_version,
        "provenance": b.provenance,
    }


async def _fetch_provider_latest(
    db: AsyncSession,
    instrument: Instrument,
    timeframe: Timeframe,
    limit: int,
    adjusted: bool,
) -> list[OHLCVBar]:
    """Fetch approximately `limit` recent bars from the configured provider when DB is cold."""
    alpaca_cost = estimate_latest_ohlcv_request_count(timeframe, limit)
    binance_cost = estimate_latest_ohlcv_request_weight(timeframe, limit)
    coinbase_cost = estimate_coinbase_latest_ohlcv_request_count(timeframe, limit)
    kraken_cost = estimate_kraken_latest_ohlcv_request_count(timeframe, limit)
    marketstack_cost = estimate_marketstack_latest_ohlcv_request_count(timeframe, limit)
    twelve_data_cost = estimate_twelve_data_latest_ohlcv_request_count(timeframe, limit)
    ibkr_cost = estimate_ibkr_latest_ohlcv_request_count(timeframe, limit)
    operation_cost_overrides = {
        **({"alpaca": alpaca_cost} if alpaca_cost is not None else {}),
        **({"binance": binance_cost} if binance_cost is not None else {}),
        **({"coinbase": coinbase_cost} if coinbase_cost is not None else {}),
        **({"kraken": kraken_cost} if kraken_cost is not None else {}),
        **({"marketstack": marketstack_cost} if marketstack_cost is not None else {}),
        **({"twelve_data": twelve_data_cost} if twelve_data_cost is not None else {}),
        **({"ibkr": ibkr_cost} if ibkr_cost is not None else {}),
    }
    execution = await execute_provider_call(
        db,
        ProviderCapability.PRICE_HISTORY,
        f"fetch_latest_ohlcv:{timeframe.value}",
        instrument_id=instrument.id,
        usage_identity=lambda provider_name: provider_symbol_for_instrument(instrument, provider_name),
        operation_cost_overrides=operation_cost_overrides or None,
        adjusted=adjusted,
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
    bars = execution.result[-limit:] if len(execution.result) > limit else execution.result
    bars = await _attach_provider_series(
        db,
        instrument,
        timeframe,
        adjusted,
        execution,
        bars=bars,
    )
    provider_symbol = provider_symbol_for_instrument(instrument, execution.provider_name)
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
        operation_cost_overrides={
            "ibkr": estimate_ibkr_current_price_request_count(
                provider_symbol_for_instrument(instrument, "ibkr")
            )
        },
        usage_identity=lambda provider_name: provider_symbol_for_instrument(instrument, provider_name),
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
            usage_identity=provider_symbol,
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
