import logging
import math
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.database import AsyncSessionLocal, get_db
from app.models.asset_class import AssetClass, InstrumentType
from app.models.instrument import EquityDetail, Instrument
from app.models.instrument_identity import InstrumentProviderSymbol
from app.models.provider_observation import (
    InstrumentDatasetState,
    InstrumentIdentifierSnapshot,
    InstrumentProfileSnapshot,
    LatestPriceSnapshot,
)
from app.models.instrument_stats import InstrumentStats
from app.models.provider_runtime import ProviderCapability
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.screener import ScreenerDefinition, ScreenerResult
from app.models.synthetic_constituent import SyntheticConstituent
from app.models.user import User
from app.models.watchlist import Watchlist, WatchlistItem
from app.providers import ensure_data_source
from app.providers.base import InstrumentProfile
from app.schemas.instrument import InstrumentMembership, InstrumentOut, InstrumentSearchResult
from app.services.bulk_fetch import get_fetch_progress
from app.services.expression_engine import (
    ExpressionError,
    extract_tickers,
    is_expression,
    normalize_expression,
)
from app.services.instrument_events import ensure_instrument_events_loaded
from app.services.instrument_mastering import (
    ensure_external_identifier,
    has_external_identifier,
    ingest_provider_profile,
)
from app.services.market_data import (
    fetch_ohlcv_latest,
    get_provider_profile_async,
    search_provider_instruments_async,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/instruments", tags=["instruments"])


def _search_result_priority(query: str, *, symbol: str, name: str, type_name: str) -> tuple[int, int, int, int, int, int, int, str]:
    normalized = query.strip().upper()
    normalized_symbol = symbol.strip().upper()
    normalized_name = name.strip().upper()
    normalized_type = type_name.strip().upper()
    exact_symbol = 0 if normalized_symbol == normalized else 1
    exact_name = 0 if normalized_name == normalized else 1
    prefix_symbol = 0 if normalized and normalized_symbol.startswith(normalized) else 1
    contains_symbol = 0 if normalized and normalized in normalized_symbol else 1
    contains_name = 0 if normalized and normalized in normalized_name else 1

    if any(token in normalized_type for token in ("STOCK", "EQUITY", "ETF", "INDEX", "ADR", "FUND")):
        type_penalty = 0
    elif "CRYPTO" in normalized_type:
        type_penalty = 1
    elif any(token in normalized_type for token in ("FOREX", "FUTURE", "BOND", "RATE", "MACRO")):
        type_penalty = 2
    elif any(token in normalized_type for token in ("OPTION", "WARRANT", "RIGHT")):
        type_penalty = 3
    else:
        type_penalty = 2

    return (
        exact_symbol,
        exact_name,
        prefix_symbol,
        contains_symbol,
        contains_name,
        type_penalty,
        len(normalized_symbol),
        normalized_symbol,
    )


@router.get("/search", response_model=list[InstrumentSearchResult])
async def search_instruments(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if is_expression(q):
        return []

    result = await db.execute(
        select(Instrument)
        .options(
            selectinload(Instrument.equity_detail),
            selectinload(Instrument.instrument_type),
        )
        .where(
            Instrument.is_synthetic.is_(False),
            or_(Instrument.symbol.ilike(f"%{q}%"), Instrument.name.ilike(f"%{q}%")),
        )
        .limit(25)
    )
    local = result.scalars().all()
    merged: dict[str, InstrumentSearchResult] = {}
    for item in [
        InstrumentSearchResult(
            symbol=i.symbol,
            name=i.name,
            exchange="",
            type=i.instrument_type.name if i.instrument_type else "",
        )
        for i in local
    ]:
        merged[item.symbol] = item
    provider_results = await search_provider_instruments_async(db, q)
    for r in provider_results:
        symbol = r.get("symbol", "")
        if not symbol or symbol in merged:
            continue
        merged[symbol] = InstrumentSearchResult(
            symbol=symbol,
            name=r.get("name", ""),
            exchange=r.get("exchange", ""),
            type=r.get("type", ""),
        )
    ranked = sorted(
        merged.values(),
        key=lambda item: _search_result_priority(
            q,
            symbol=item.symbol,
            name=item.name,
            type_name=item.type,
        ),
    )
    return ranked[:10]


@router.get("/browse")
async def browse_instruments(
    q: str | None = Query(None),
    instrument_type: str | None = Query(None),
    sector: str | None = Query(None),
    industry: str | None = Query(None),
    market_cap_tier: str | None = Query(None),
    country: str | None = Query(None),
    currency: str | None = Query(None),
    exchange: str | None = Query(None),
    ids: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Browse/filter instruments by fundamental criteria with pagination.
    Returns instruments with basic info + equity_detail for sector/industry.
    """
    stmt = (
        select(Instrument)
        .options(
            selectinload(Instrument.equity_detail),
            selectinload(Instrument.instrument_type),
        )
        .where(Instrument.is_active.is_(True))
        .where(Instrument.is_synthetic.is_(False))
    )

    if ids:
        id_list = [int(i) for i in ids.split(",") if i.strip().isdigit()]
        if id_list:
            stmt = stmt.where(Instrument.id.in_(id_list))

    if q:
        stmt = stmt.where(or_(Instrument.symbol.ilike(f"%{q}%"), Instrument.name.ilike(f"%{q}%")))

    if instrument_type:
        stmt = stmt.join(Instrument.instrument_type).where(
            InstrumentType.name.ilike(f"%{instrument_type}%")
        )

    if currency:
        stmt = stmt.where(Instrument.currency == currency.upper())

    # EquityDetail filters — only join when needed
    needs_equity_join = any(
        f is not None for f in [sector, industry, market_cap_tier, country, exchange]
    )
    if needs_equity_join:
        stmt = stmt.join(EquityDetail, EquityDetail.instrument_id == Instrument.id, isouter=True)
        if sector:
            stmt = stmt.where(EquityDetail.sector.ilike(f"%{sector}%"))
        if industry:
            # industry filter implicitly covers its sector — no separate sector filter needed
            stmt = stmt.where(EquityDetail.industry.ilike(f"%{industry}%"))
        if market_cap_tier:
            stmt = stmt.where(EquityDetail.market_cap_tier == market_cap_tier)
        if country:
            stmt = stmt.where(EquityDetail.country.ilike(f"%{country}%"))
        if exchange:
            stmt = stmt.where(EquityDetail.exchange_mic.ilike(f"%{exchange}%"))

    # Count total for pagination metadata
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(stmt)).scalars().all()

    items = []
    for inst in rows:
        eq = inst.equity_detail
        items.append(
            {
                "id": inst.id,
                "symbol": inst.symbol,
                "name": inst.name,
                "currency": inst.currency,
                "type": inst.instrument_type.name if inst.instrument_type else None,
                "sector": eq.sector if eq else None,
                "industry": eq.industry if eq else None,
                "market_cap_tier": eq.market_cap_tier if eq else None,
                "country": eq.country if eq else None,
                "exchange": eq.exchange_mic if eq else None,
            }
        )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


@router.get("/filter-options")
async def get_filter_options(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return distinct values for screener/browse dropdown filters."""
    from sqlalchemy import distinct

    sectors = (
        (
            await db.execute(
                select(distinct(EquityDetail.sector)).where(EquityDetail.sector.isnot(None))
            )
        )
        .scalars()
        .all()
    )
    industries = (
        (
            await db.execute(
                select(distinct(EquityDetail.industry)).where(EquityDetail.industry.isnot(None))
            )
        )
        .scalars()
        .all()
    )
    countries = (
        (
            await db.execute(
                select(distinct(EquityDetail.country)).where(EquityDetail.country.isnot(None))
            )
        )
        .scalars()
        .all()
    )
    exchanges = (
        (
            await db.execute(
                select(distinct(EquityDetail.exchange_mic)).where(
                    EquityDetail.exchange_mic.isnot(None)
                )
            )
        )
        .scalars()
        .all()
    )
    currencies = (
        (
            await db.execute(
                select(distinct(Instrument.currency)).where(Instrument.currency.isnot(None))
            )
        )
        .scalars()
        .all()
    )

    return {
        "sectors": sorted(sectors),
        "industries": sorted(industries),
        "countries": sorted(countries),
        "exchanges": sorted(exchanges),
        "currencies": sorted(currencies),
    }


class HeatmapRequest(BaseModel):
    instrument_ids: list[int]
    timeframe: Timeframe = Timeframe.D1
    sparkline_bars: int = Field(20, ge=2, le=120)
    include_sparklines: bool = True


class SeasonalityRecord(BaseModel):
    year: int
    month: int
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    performance: float
    high_low_range: float
    volatility: float
    volume_change: float | None = None


class SeasonalityMonth(BaseModel):
    month: int
    label: str
    sample_count: int
    avg_performance: float | None
    median_performance: float | None
    win_rate: float | None
    best: float | None
    worst: float | None
    avg_high_low_range: float | None
    avg_volatility: float | None
    avg_volume_change: float | None
    records: list[SeasonalityRecord]


class SeasonalityResponse(BaseModel):
    symbol: str
    months: list[SeasonalityMonth]


class ResolveExpressionBody(BaseModel):
    expression: str


class ResolveExpressionOut(BaseModel):
    symbol: str


@router.post("/resolve-expression", response_model=ResolveExpressionOut)
async def resolve_expression(
    body: ResolveExpressionBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create or retrieve a synthetic instrument for the given arithmetic expression
    (e.g. 'SPY/GLD', '(SPY*0.5)/QQQ').

    - Normalises the expression to a canonical upper-case form.
    - Verifies every constituent ticker exists (auto-creates from the configured provider if needed).
    - If a synthetic instrument with the same normalised expression already exists,
      returns the existing row.  Otherwise creates a new one.
    """
    try:
        canonical = normalize_expression(body.expression)
        tickers = extract_tickers(canonical)
    except ExpressionError as exc:
        raise HTTPException(400, str(exc))

    if len(tickers) < 2 and not any(c in canonical for c in ("+", "-", "*", "/")):
        raise HTTPException(400, "Input does not look like an arithmetic expression")

    # Resolve / auto-create every constituent instrument
    constituents: dict[str, Instrument] = {}
    for ticker in tickers:
        result = await db.execute(
            select(Instrument).where(
                Instrument.symbol == ticker, Instrument.is_synthetic.is_(False)
            )
        )
        inst = result.scalar_one_or_none()
        if inst is None:
            inst = await _create_from_provider(ticker, db)
            if inst is None:
                raise HTTPException(404, f"Constituent instrument '{ticker}' not found")
        constituents[ticker] = inst

    # Return existing synthetic if already stored
    existing = await db.execute(
        select(Instrument)
        .options(
            selectinload(Instrument.synthetic_constituents),
            selectinload(Instrument.equity_detail),
            selectinload(Instrument.stats),
            selectinload(Instrument.instrument_type),
        )
        .where(Instrument.expression == canonical, Instrument.is_synthetic.is_(True))
    )
    synth = existing.scalar_one_or_none()
    if synth is not None:
        return ResolveExpressionOut(symbol=synth.symbol)

    # Determine instrument type (reuse "Synthetic" type or create it)
    type_result = await db.execute(select(InstrumentType).where(InstrumentType.name == "Synthetic"))
    synth_type = type_result.scalar_one_or_none()
    if synth_type is None:
        ac_result = await db.execute(select(AssetClass).where(AssetClass.name == "Synthetic"))
        synth_ac = ac_result.scalar_one_or_none()
        if synth_ac is None:
            synth_ac = AssetClass(name="Synthetic")
            db.add(synth_ac)
            await db.flush()
        synth_type = InstrumentType(name="Synthetic", asset_class_id=synth_ac.id)
        db.add(synth_type)
        await db.flush()

    synth = Instrument(
        symbol=canonical,
        name=canonical,
        is_active=True,
        is_synthetic=True,
        expression=canonical,
        instrument_type_id=synth_type.id,
    )
    db.add(synth)
    await db.flush()

    for ticker, inst in constituents.items():
        db.add(
            SyntheticConstituent(
                synthetic_instrument_id=synth.id,
                constituent_instrument_id=inst.id,
                ticker_alias=ticker,
            )
        )

    await db.commit()
    return ResolveExpressionOut(symbol=synth.symbol)


@router.post("/heatmap-data")
async def get_heatmap_data(
    body: HeatmapRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Batch-compute heatmap metrics for a list of instrument IDs.
    Returns one row per instrument with daily performance, RSI, relative-volume,
    distance to 52w high/low, and a timeframe-aware sparkline.
    """
    from collections import defaultdict

    if not body.instrument_ids:
        return []

    instrument_ids = list(dict.fromkeys(body.instrument_ids))[:500]  # dedup, cap at 500

    # ── 1. Load instrument metadata ──────────────────────────────────────────
    instr_result = await db.execute(
        select(Instrument)
        .options(
            selectinload(Instrument.equity_detail),
            selectinload(Instrument.stats),
        )
        .where(Instrument.id.in_(instrument_ids))
    )
    instruments: dict[int, Instrument] = {i.id: i for i in instr_result.scalars().all()}

    # ── 2. Batch-fetch D1 bars for calendar-style metrics ──────────────────
    cutoff = datetime.now(UTC) - timedelta(days=400)
    bars_result = await db.execute(
        select(OHLCVBar)
        .where(
            OHLCVBar.instrument_id.in_(instrument_ids),
            OHLCVBar.timeframe == Timeframe.D1,
            OHLCVBar.ts >= cutoff,
            OHLCVBar.is_adjusted.is_(True),
        )
        .order_by(OHLCVBar.instrument_id, OHLCVBar.ts)
    )
    bars_by_id: dict[int, list[OHLCVBar]] = defaultdict(list)
    for bar in bars_result.scalars().all():
        bars_by_id[bar.instrument_id].append(bar)

    # ── 2b. Fetch selected timeframe bars through the normal OHLCV cache path.
    # This keeps heatmap sparklines DB-first but still populates missing W1/MN
    # bars instead of silently reusing daily data.
    sparkline_bars_by_id: dict[int, list[OHLCVBar]] = defaultdict(list)
    if body.include_sparklines:
        for instr_id in instrument_ids:
            inst = instruments.get(instr_id)
            if inst is None:
                continue
            try:
                sparkline_bars_by_id[instr_id] = await fetch_ohlcv_latest(
                    db,
                    inst,
                    body.timeframe,
                    body.sparkline_bars,
                    True,
                )
            except Exception:
                if body.timeframe == Timeframe.D1:
                    sparkline_bars_by_id[instr_id] = bars_by_id.get(instr_id, [])[-body.sparkline_bars :]

    # ── 3. Compute metrics per instrument ─────────────────────────────────────
    today_utc = datetime.now(UTC).date()
    month_start = today_utc.replace(day=1)
    year_start = today_utc.replace(month=1, day=1)

    def _pct(base: float | None, end: float | None) -> float | None:
        if base and end and base > 0:
            return (end - base) / base
        return None

    def _find_base_before(bars: list[OHLCVBar], cutoff_date) -> float | None:
        """Return the close of the last bar whose date is strictly before cutoff_date."""
        for bar in reversed(bars):
            bar_date = bar.ts.date() if hasattr(bar.ts, "date") else bar.ts
            if bar_date < cutoff_date:
                return float(bar.close)
        return None

    def _sparkline_for(instr_id: int) -> list[float]:
        """Return raw selected-timeframe closes; the client scales per tile."""
        spark_bars = sparkline_bars_by_id.get(instr_id, [])
        spark_closes = [float(b.close) for b in spark_bars]
        spark_raw = spark_closes[-body.sparkline_bars :]
        return [round(v, 6) for v in spark_raw]

    rows = []
    for instr_id in instrument_ids:
        inst = instruments.get(instr_id)
        if inst is None:
            continue

        bars = bars_by_id.get(instr_id, [])
        eq = inst.equity_detail
        stats = inst.stats
        n = len(bars)

        # Base metadata
        market_cap = float(stats.market_cap) if stats and stats.market_cap else None
        avg_vol_30d = float(stats.avg_volume_30d) if stats and stats.avg_volume_30d else None
        week52_high = float(stats.week52_high) if stats and stats.week52_high else None
        week52_low = float(stats.week52_low) if stats and stats.week52_low else None

        if not bars:
            rows.append({
                "instrument_id": instr_id,
                "symbol": inst.symbol,
                "name": inst.name or inst.symbol,
                "sector": eq.sector if eq else None,
                "industry": eq.industry if eq else None,
                "market_cap": market_cap,
                "avg_volume_30d": avg_vol_30d,
                "current_price": None,
                "perf_1d": None, "perf_1w": None, "perf_1m": None,
                "perf_mtd": None, "perf_ytd": None, "perf_1y": None,
                "rsi_14": None, "rel_volume": None,
                "dist_52w_high": None, "dist_52w_low": None,
                "sparkline": _sparkline_for(instr_id),
            })
            continue

        closes = [float(b.close) for b in bars]
        volumes = [float(b.volume) if b.volume is not None else 0.0 for b in bars]
        current_price = closes[-1]

        # Performance
        perf_1d = _pct(closes[-2], closes[-1]) if n >= 2 else None
        perf_1w = _pct(closes[-6], closes[-1]) if n >= 6 else None
        perf_1m = _pct(closes[-22], closes[-1]) if n >= 22 else None
        perf_1y = _pct(closes[-252], closes[-1]) if n >= 252 else None
        perf_mtd = _pct(_find_base_before(bars, month_start), current_price)
        perf_ytd = _pct(_find_base_before(bars, year_start), current_price)

        # RSI-14 (Wilder smoothing) — need at least 15 price changes
        rsi_14: float | None = None
        if n >= 15:
            changes = [closes[i] - closes[i - 1] for i in range(1, n)]
            gains = [max(c, 0.0) for c in changes]
            losses = [max(-c, 0.0) for c in changes]
            avg_gain = sum(gains[:14]) / 14.0
            avg_loss = sum(losses[:14]) / 14.0
            for i in range(14, len(changes)):
                avg_gain = (avg_gain * 13.0 + gains[i]) / 14.0
                avg_loss = (avg_loss * 13.0 + losses[i]) / 14.0
            if avg_loss == 0.0:
                rsi_14 = 100.0
            else:
                rsi_14 = round(100.0 - 100.0 / (1.0 + avg_gain / avg_loss), 2)

        # Relative volume (today's volume vs 30-day avg)
        rel_volume: float | None = None
        if avg_vol_30d and avg_vol_30d > 0 and volumes:
            rel_volume = round(volumes[-1] / avg_vol_30d, 3)

        # Distance to 52-week high / low
        dist_52w_high: float | None = None
        dist_52w_low: float | None = None
        if week52_high and week52_high > 0:
            dist_52w_high = round((current_price - week52_high) / week52_high, 4)
        if week52_low and week52_low > 0:
            dist_52w_low = round((current_price - week52_low) / week52_low, 4)

        rows.append({
            "instrument_id": instr_id,
            "symbol": inst.symbol,
            "name": inst.name or inst.symbol,
            "sector": eq.sector if eq else None,
            "industry": eq.industry if eq else None,
            "market_cap": market_cap,
            "avg_volume_30d": avg_vol_30d,
            "current_price": current_price,
            "perf_1d": perf_1d,
            "perf_1w": perf_1w,
            "perf_1m": perf_1m,
            "perf_mtd": perf_mtd,
            "perf_ytd": perf_ytd,
            "perf_1y": perf_1y,
            "rsi_14": rsi_14,
            "rel_volume": rel_volume,
            "dist_52w_high": dist_52w_high,
            "dist_52w_low": dist_52w_low,
            "sparkline": _sparkline_for(instr_id),
        })

    return rows


MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


@router.get("/{symbol:path}/seasonality/monthly", response_model=SeasonalityResponse)
async def get_monthly_seasonality(
    symbol: str,
    limit: int = Query(480, ge=24, le=1200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Instrument).where(Instrument.symbol == symbol.upper()))
    instrument = result.scalar_one_or_none()
    if instrument is None:
        raise HTTPException(404, f"Instrument '{symbol}' not found")
    await db.refresh(instrument, ["listings"])

    bars = await fetch_ohlcv_latest(db, instrument, Timeframe.MN, limit, True)
    records_by_month: dict[int, list[SeasonalityRecord]] = {m: [] for m in range(1, 13)}

    previous_volume: float | None = None
    for bar in bars:
        open_ = float(bar.open)
        high = float(bar.high)
        low = float(bar.low)
        close = float(bar.close)
        volume = float(bar.volume) if bar.volume is not None else None
        if open_ <= 0:
            previous_volume = volume
            continue
        performance = (close - open_) / open_
        high_low_range = (high - low) / open_ if open_ else 0.0
        volatility = abs(math.log(close / open_)) if close > 0 else abs(performance)
        volume_change = (
            (volume - previous_volume) / previous_volume
            if volume is not None and previous_volume not in (None, 0)
            else None
        )
        month = bar.ts.month
        records_by_month[month].append(
            SeasonalityRecord(
                year=bar.ts.year,
                month=month,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
                performance=performance,
                high_low_range=high_low_range,
                volatility=volatility,
                volume_change=volume_change,
            )
        )
        previous_volume = volume

    months: list[SeasonalityMonth] = []
    for month in range(1, 13):
        records = sorted(records_by_month[month], key=lambda r: r.year, reverse=True)
        performances = [r.performance for r in records]
        ranges = [r.high_low_range for r in records]
        vols = [r.volatility for r in records]
        volume_changes = [r.volume_change for r in records if r.volume_change is not None]
        months.append(
            SeasonalityMonth(
                month=month,
                label=MONTH_LABELS[month - 1],
                sample_count=len(records),
                avg_performance=_avg(performances),
                median_performance=_median(performances),
                win_rate=_avg([1.0 if v > 0 else 0.0 for v in performances]),
                best=max(performances) if performances else None,
                worst=min(performances) if performances else None,
                avg_high_low_range=_avg(ranges),
                avg_volatility=_avg(vols),
                avg_volume_change=_avg(volume_changes),
                records=records,
            )
        )

    return SeasonalityResponse(symbol=instrument.symbol, months=months)


@router.get("/{instrument_id}/membership", response_model=InstrumentMembership)
async def get_instrument_membership(
    instrument_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return which of the current user's watchlists and screeners contain this instrument."""
    # Watchlists
    wl_rows = (
        (
            await db.execute(
                select(Watchlist)
                .join(WatchlistItem, WatchlistItem.watchlist_id == Watchlist.id)
                .where(
                    Watchlist.user_id == current_user.id,
                    WatchlistItem.instrument_id == instrument_id,
                    WatchlistItem.left_screener_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )

    watchlists = [{"id": wl.id, "name": wl.name, "is_managed": wl.is_managed} for wl in wl_rows]

    # Screeners: membership means the latest result's matched_ids contains this instrument_id
    screener_rows = (
        (
            await db.execute(
                select(ScreenerDefinition).where(ScreenerDefinition.user_id == current_user.id)
            )
        )
        .scalars()
        .all()
    )

    screeners = []
    for sd in screener_rows:
        latest_result = (
            await db.execute(
                select(ScreenerResult)
                .where(ScreenerResult.screener_id == sd.id)
                .order_by(ScreenerResult.run_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        in_current = latest_result is not None and instrument_id in (
            latest_result.matched_ids or []
        )
        screeners.append(
            {
                "id": sd.id,
                "name": sd.name,
                "last_run_at": latest_result.run_at.isoformat() if latest_result else None,
                "in_current_results": in_current,
            }
        )

    return InstrumentMembership(watchlists=watchlists, screeners=screeners)


@router.get("/{symbol:path}/data-coverage")
async def get_data_coverage(
    symbol: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Instrument).where(Instrument.symbol == symbol.upper()))
    instrument = result.scalar_one_or_none()
    if instrument is None:
        raise HTTPException(404, f"Instrument '{symbol}' not found")

    rows = (
        await db.execute(
            select(
                OHLCVBar.timeframe,
                func.min(OHLCVBar.ts).label("oldest"),
                func.max(OHLCVBar.ts).label("newest"),
                func.count().label("bar_count"),
            )
            .where(OHLCVBar.instrument_id == instrument.id, OHLCVBar.is_adjusted.is_(True))
            .group_by(OHLCVBar.timeframe)
        )
    ).all()

    coverage = {
        row.timeframe.value: {
            "oldest": row.oldest.isoformat() if row.oldest else None,
            "newest": row.newest.isoformat() if row.newest else None,
            "bar_count": row.bar_count,
        }
        for row in rows
    }

    progress: dict | None = None
    try:
        from arq.connections import RedisSettings, create_pool

        from app.config import settings

        redis = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        progress = await get_fetch_progress(instrument.id, redis)
        await redis.aclose()
    except Exception:
        pass

    return {
        "instrument_id": instrument.id,
        "symbol": symbol.upper(),
        "coverage": coverage,
        "is_fetching": progress is not None and progress.get("status") == "in_progress",
        "fetch_progress": progress,
    }


@router.get("/{symbol:path}/provenance")
async def get_instrument_provenance(
    symbol: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Instrument)
        .options(
            selectinload(Instrument.equity_detail),
            selectinload(Instrument.stats),
            selectinload(Instrument.option_detail),
            selectinload(Instrument.identifiers),
            selectinload(Instrument.listings),
        )
        .where(Instrument.symbol == symbol.upper())
    )
    instrument = result.scalar_one_or_none()
    if instrument is None:
        raise HTTPException(404, f"Instrument '{symbol}' not found")

    snapshots = (
        await db.execute(
            select(InstrumentProfileSnapshot)
            .where(InstrumentProfileSnapshot.instrument_id == instrument.id)
            .order_by(InstrumentProfileSnapshot.observed_at.desc())
            .limit(10)
        )
    ).scalars().all()
    dataset_states = (
        await db.execute(
            select(InstrumentDatasetState)
            .where(InstrumentDatasetState.instrument_id == instrument.id)
            .order_by(InstrumentDatasetState.updated_at.desc())
        )
    ).scalars().all()
    identifier_snapshots = (
        await db.execute(
            select(InstrumentIdentifierSnapshot)
            .where(InstrumentIdentifierSnapshot.instrument_id == instrument.id)
            .order_by(InstrumentIdentifierSnapshot.observed_at.desc())
            .limit(10)
        )
    ).scalars().all()
    latest_price_snapshots = (
        await db.execute(
            select(LatestPriceSnapshot)
            .where(LatestPriceSnapshot.instrument_id == instrument.id)
            .order_by(LatestPriceSnapshot.observed_at.desc())
            .limit(10)
        )
    ).scalars().all()

    return {
        "instrument_id": instrument.id,
        "symbol": instrument.symbol,
        "field_provenance": instrument.field_provenance or {},
        "equity_detail": instrument.equity_detail.field_provenance if instrument.equity_detail else {},
        "stats": instrument.stats.field_provenance if instrument.stats else {},
        "option_detail": instrument.option_detail.field_provenance if instrument.option_detail else {},
        "identifiers": [
            {
                "identifier_type": row.identifier_type.value,
                "identifier_value": row.identifier_value,
                "is_primary": row.is_primary,
                "is_active": row.is_active,
                "data_source_id": row.data_source_id,
                "extra_data": row.extra_data,
            }
            for row in instrument.identifiers
        ],
        "listings": [
            {
                "ticker": row.ticker,
                "currency": row.currency,
                "is_primary": row.is_primary,
                "is_active": row.is_active,
            }
            for row in instrument.listings
        ],
        "profile_snapshots": [
            {
                "provider_symbol": row.provider_symbol,
                "observed_at": row.observed_at,
                "fetched_at": row.fetched_at,
                "profile_hash": row.profile_hash,
                "payload": row.payload,
            }
            for row in snapshots
        ],
        "identifier_snapshots": [
            {
                "provider_symbol": row.provider_symbol,
                "observed_at": row.observed_at,
                "fetched_at": row.fetched_at,
                "snapshot_hash": row.snapshot_hash,
                "payload": row.payload,
            }
            for row in identifier_snapshots
        ],
        "latest_price_snapshots": [
            {
                "provider_symbol": row.provider_symbol,
                "observed_at": row.observed_at,
                "fetched_at": row.fetched_at,
                "price": float(row.price),
                "payload": row.payload,
            }
            for row in latest_price_snapshots
        ],
        "dataset_states": [
            {
                "dataset_type": row.dataset_type,
                "dataset_key": row.dataset_key,
                "status": row.status.value,
                "coverage_start": row.coverage_start,
                "coverage_end": row.coverage_end,
                "observed_at": row.observed_at,
                "fetched_at": row.fetched_at,
                "stale_after": row.stale_after,
                "extra_data": row.extra_data,
            }
            for row in dataset_states
        ],
    }


@router.get("/{symbol:path}", response_model=InstrumentOut)
async def get_instrument(
    symbol: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Instrument)
        .options(
            selectinload(Instrument.equity_detail),
            selectinload(Instrument.instrument_type),
            selectinload(Instrument.stats),
            selectinload(Instrument.identifiers),
            selectinload(Instrument.listings),
            selectinload(Instrument.option_detail),
            selectinload(Instrument.synthetic_constituents),
        )
        .where(Instrument.symbol == symbol.upper())
    )
    instrument = result.scalar_one_or_none()

    created = False
    if instrument is None:
        instrument = await _create_from_provider(symbol.upper(), db)
        if instrument is None:
            raise HTTPException(404, f"Instrument '{symbol}' not found")
        created = True
        background_tasks.add_task(_enqueue_bulk_fetch, instrument.id)
        background_tasks.add_task(_sync_instrument_events, instrument.id)

    if not instrument.is_synthetic and _needs_metadata_refresh(instrument):
        instrument = await _refresh_instrument_metadata(instrument, db)

    if not instrument.is_synthetic and (
        instrument.stats is None
        or instrument.stats.week52_high is None
        or instrument.stats.week52_low is None
    ):
        instrument = await _ensure_52w_stats(instrument, db)

    if not created and not instrument.is_synthetic:
        background_tasks.add_task(_sync_instrument_events, instrument.id)
        if not has_external_identifier(instrument):
            background_tasks.add_task(_sync_instrument_identifier, instrument.id)

    return instrument


async def _sync_instrument_events(instrument_id: int) -> None:
    try:
        async with AsyncSessionLocal() as session:
            instrument = await session.get(Instrument, instrument_id)
            if instrument is None:
                return
            await ensure_instrument_events_loaded(session, instrument)
            await session.commit()
    except Exception as exc:
        logger.warning("Background instrument event sync failed for %s: %s", instrument_id, exc)


async def _sync_instrument_identifier(instrument_id: int) -> None:
    try:
        async with AsyncSessionLocal() as session:
            instrument = await session.get(Instrument, instrument_id)
            if instrument is None:
                return
            await ensure_external_identifier(session, instrument)
            await session.commit()
    except Exception as exc:
        logger.warning("Background identifier sync failed for %s: %s", instrument_id, exc)


def _needs_metadata_refresh(instrument: Instrument) -> bool:
    stats = instrument.stats
    if stats and stats.computed_at:
        computed_at = stats.computed_at
        if computed_at.tzinfo is None:
            computed_at = computed_at.replace(tzinfo=UTC)
        if computed_at > datetime.now(UTC) - timedelta(days=7):
            return False
    return (
        instrument.currency is None
        or stats is None
        or stats.market_cap is None
        or stats.pe_ratio is None
        or stats.beta is None
        or stats.week52_high is None
        or stats.week52_low is None
    )


async def _reload_instrument_full(instrument_id: int, db: AsyncSession) -> Instrument:
    """Re-query an instrument with all relationships needed by InstrumentOut eager-loaded."""
    result = await db.execute(
        select(Instrument)
        .options(
            selectinload(Instrument.equity_detail),
            selectinload(Instrument.instrument_type),
            selectinload(Instrument.stats),
            selectinload(Instrument.identifiers),
            selectinload(Instrument.listings),
            selectinload(Instrument.option_detail),
            selectinload(Instrument.synthetic_constituents),
        )
        .where(Instrument.id == instrument_id)
    )
    return result.scalar_one()


async def _refresh_instrument_metadata(instrument: Instrument, db: AsyncSession) -> Instrument:
    """
    Fill missing metadata for existing instruments from the current market-data source.

    This is intentionally conservative: it only patches blank fields so user-visible
    catalogue data seeded earlier is not churned on every dashboard/widget load.
    """
    profile = await get_provider_profile_async(db, instrument.symbol, instrument_id=instrument.id)
    if profile is None:
        return instrument
    await db.flush()
    return await _reload_instrument_full(instrument.id, db)


async def _ensure_52w_stats(instrument: Instrument, db: AsyncSession) -> Instrument:
    """
    Compute 52-week high/low from D1 OHLCV bars (last 252 bars ≈ 1 trading year)
    and persist to InstrumentStats synchronously so the first page load always has data.
    Other stats fields (market_cap, pe_ratio, etc.) remain None until a separate backfill.
    """
    import logging

    log = logging.getLogger(__name__)
    symbol = instrument.__dict__.get("symbol", "?")
    try:
        cutoff = datetime.now(UTC) - timedelta(days=366)
        row = (
            await db.execute(
                select(
                    func.max(OHLCVBar.close).label("week52_high"),
                    func.min(OHLCVBar.close).label("week52_low"),
                ).where(
                    OHLCVBar.instrument_id == instrument.id,
                    OHLCVBar.timeframe == "D1",
                    OHLCVBar.ts >= cutoff,
                    OHLCVBar.is_adjusted.is_(True),
                )
            )
        ).one_or_none()

        if row is None or row.week52_high is None:
            return instrument

        week52_high = float(row.week52_high)
        week52_low = float(row.week52_low)

        fetched_at = datetime.now(UTC).isoformat()
        stats = (
            await db.execute(
                select(InstrumentStats).where(InstrumentStats.instrument_id == instrument.id)
            )
        ).scalar_one_or_none()
        if stats is None:
            stats = InstrumentStats(instrument_id=instrument.id)
            db.add(stats)
        stats.week52_high = week52_high
        stats.week52_low = week52_low
        field_provenance = dict(stats.field_provenance or {})
        field_provenance["week52_high"] = {
            "source": "internal_ohlcv_52w",
            "fetched_at": fetched_at,
            "provider_symbol": instrument.symbol,
        }
        field_provenance["week52_low"] = {
            "source": "internal_ohlcv_52w",
            "fetched_at": fetched_at,
            "provider_symbol": instrument.symbol,
        }
        stats.field_provenance = field_provenance
        await db.commit()
        log.info("Computed 52w stats for %s: high=%.4f low=%.4f", symbol, week52_high, week52_low)
    except Exception as exc:
        await db.rollback()
        log.warning("Failed to compute 52w stats for %s: %s", symbol, exc)
        return instrument

    return await _reload_instrument_full(instrument.id, db)


async def _enqueue_bulk_fetch(instrument_id: int):
    """Enqueue bulk historical fetch via ARQ when a new instrument is first seen."""
    try:
        from arq.connections import RedisSettings, create_pool

        from app.config import settings

        redis = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        await redis.enqueue_job("task_bulk_fetch_instrument", instrument_id)
        await redis.aclose()
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning(f"Could not enqueue bulk fetch: {e}")


def _normalized_symbol_key(value: str | None) -> str:
    return (value or "").strip().upper()


def _profile_exact_match(profile: InstrumentProfile, requested_symbol: str) -> bool:
    requested = _normalized_symbol_key(requested_symbol)
    if not requested:
        return False
    candidates = {
        _normalized_symbol_key(profile.symbol),
        _normalized_symbol_key(profile.canonical_symbol),
        *{
            _normalized_symbol_key(listing.provider_symbol)
            for listing in (profile.listings or [])
        },
    }
    return requested in candidates


def _search_results_exact_match(results: list[dict], requested_symbol: str) -> bool:
    requested = _normalized_symbol_key(requested_symbol)
    return any(_normalized_symbol_key(item.get("symbol")) == requested for item in results)


def _exact_search_provider(results: list[dict], requested_symbol: str) -> str | None:
    requested = _normalized_symbol_key(requested_symbol)
    for item in results:
        if _normalized_symbol_key(item.get("symbol")) == requested:
            provider_name = item.get("provider")
            if isinstance(provider_name, str) and provider_name.strip():
                return provider_name.strip()
    return None


async def _find_existing_instrument_for_profile(
    db: AsyncSession,
    profile: InstrumentProfile,
) -> Instrument | None:
    for candidate in (
        _normalized_symbol_key(profile.canonical_symbol),
        _normalized_symbol_key(profile.symbol),
    ):
        if not candidate:
            continue
        instrument = (
            await db.execute(select(Instrument).where(Instrument.symbol == candidate))
        ).scalar_one_or_none()
        if instrument is not None:
            return instrument

    data_source = await ensure_data_source(db, profile.provider)
    provider_bindings = [
        (_normalized_symbol_key(listing.provider_symbol), listing.exchange_code)
        for listing in (profile.listings or [])
        if _normalized_symbol_key(listing.provider_symbol)
    ]
    if not provider_bindings and _normalized_symbol_key(profile.symbol):
        provider_bindings.append((_normalized_symbol_key(profile.symbol), profile.exchange))

    for provider_symbol, exchange_code in provider_bindings:
        instrument = (
            await db.execute(
                select(Instrument)
                .join(InstrumentProviderSymbol, InstrumentProviderSymbol.instrument_id == Instrument.id)
                .where(
                    InstrumentProviderSymbol.data_source_id == data_source.id,
                    InstrumentProviderSymbol.provider_symbol == provider_symbol,
                    InstrumentProviderSymbol.provider_exchange_code == exchange_code,
                )
            )
        ).scalar_one_or_none()
        if instrument is not None:
            return instrument

    return None


async def _create_from_provider(symbol: str, db: AsyncSession) -> Instrument | None:
    provider_results = await search_provider_instruments_async(db, symbol)
    if not _search_results_exact_match(provider_results, symbol):
        return None

    preferred_provider = _exact_search_provider(provider_results, symbol)
    profile = await get_provider_profile_async(
        db,
        symbol,
        provider_name=preferred_provider,
        persist=False,
    )
    if profile is None and preferred_provider is not None:
        profile = await get_provider_profile_async(db, symbol, persist=False)
    if profile is None:
        return None
    if not _profile_exact_match(profile, symbol):
        return None

    instrument = await _find_existing_instrument_for_profile(db, profile)
    try:
        instrument = await ingest_provider_profile(db, profile, instrument=instrument)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        instrument = await _find_existing_instrument_for_profile(db, profile)
        if instrument is None:
            raise

    if instrument is None:
        return None
    return await _reload_instrument_full(instrument.id, db)
