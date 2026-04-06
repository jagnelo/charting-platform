from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.asset_class import AssetClass, InstrumentType
from app.models.instrument import EquityDetail, Instrument
from app.models.instrument_stats import InstrumentStats
from app.models.listing import InstrumentListing
from app.models.ohlcv import OHLCVBar
from app.models.screener import ScreenerDefinition, ScreenerResult
from app.models.synthetic_constituent import SyntheticConstituent
from app.models.user import User
from app.models.watchlist import Watchlist, WatchlistItem
from app.schemas.instrument import InstrumentMembership, InstrumentOut, InstrumentSearchResult
from app.services.bulk_fetch import get_fetch_progress
from app.services.expression_engine import (
    ExpressionError,
    extract_tickers,
    normalize_expression,
)
from app.services.market_data import get_instrument_info, search_ticker

router = APIRouter(prefix="/instruments", tags=["instruments"])


@router.get("/search", response_model=list[InstrumentSearchResult])
async def search_instruments(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Instrument)
        .options(
            selectinload(Instrument.equity_detail),
            selectinload(Instrument.instrument_type),
        )
        .where(or_(Instrument.symbol.ilike(f"%{q}%"), Instrument.name.ilike(f"%{q}%")))
        .limit(5)
    )
    local = result.scalars().all()
    out = [
        InstrumentSearchResult(
            symbol=i.symbol,
            name=i.name,
            exchange="",
            type=i.instrument_type.name if i.instrument_type else "",
        )
        for i in local
    ]
    if len(out) < 10:
        yf_results = search_ticker(q)
        existing = {r.symbol for r in out}
        for r in yf_results:
            if r["symbol"] not in existing:
                out.append(InstrumentSearchResult(**r))
    return out[:10]


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


class ResolveExpressionBody(BaseModel):
    expression: str


@router.post("/resolve-expression", response_model=InstrumentOut)
async def resolve_expression(
    body: ResolveExpressionBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create or retrieve a synthetic instrument for the given arithmetic expression
    (e.g. 'SPY/GLD', '(SPY*0.5)/QQQ').

    - Normalises the expression to a canonical upper-case form.
    - Verifies every constituent ticker exists (auto-creates from yfinance if needed).
    - If a synthetic instrument with the same normalised expression already exists,
      returns the existing row.  Otherwise creates a new one.
    """
    try:
        canonical = normalize_expression(body.expression)
        tickers = extract_tickers(canonical)
    except ExpressionError as exc:
        raise HTTPException(400, str(exc))

    if len(tickers) < 2 and not any(c in canonical for c in ('+', '-', '*', '/')):
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
            inst = await _create_from_yfinance(ticker, db)
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
        return synth

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
    return await _reload_instrument_full(synth.id, db)


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


@router.get("/{symbol}/data-coverage")
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


@router.get("/{symbol}", response_model=InstrumentOut)
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
            selectinload(Instrument.synthetic_constituents),
        )
        .where(Instrument.symbol == symbol.upper())
    )
    instrument = result.scalar_one_or_none()

    if instrument is None:
        instrument = await _create_from_yfinance(symbol.upper(), db)
        if instrument is None:
            raise HTTPException(404, f"Instrument '{symbol}' not found")
        # Auto-trigger bulk historical fetch as background task
        background_tasks.add_task(_enqueue_bulk_fetch, instrument.id)

    return instrument


async def _reload_instrument_full(instrument_id: int, db: AsyncSession) -> Instrument:
    """Re-query an instrument with all relationships needed by InstrumentOut eager-loaded."""
    result = await db.execute(
        select(Instrument)
        .options(
            selectinload(Instrument.equity_detail),
            selectinload(Instrument.instrument_type),
            selectinload(Instrument.stats),
            selectinload(Instrument.synthetic_constituents),
        )
        .where(Instrument.id == instrument_id)
    )
    return result.scalar_one()


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


async def _create_from_yfinance(symbol: str, db: AsyncSession) -> Instrument | None:
    info = get_instrument_info(symbol)
    if not info:
        return None

    quote_type = info.get("quoteType", "EQUITY").upper()
    type_map = {
        "EQUITY": ("Equity", "Stock"),
        "ETF": ("Equity", "ETF"),
        "FUTURE": ("Commodity", "Future"),
        "OPTION": ("Derivative", "Option"),
        "CURRENCY": ("Currency", "Forex Pair"),
        "CRYPTOCURRENCY": ("Cryptocurrency", "Crypto Spot"),
        "INDEX": ("Index", "Index"),
    }
    ac_name, it_name = type_map.get(quote_type, ("Equity", "Stock"))

    result = await db.execute(select(AssetClass).where(AssetClass.name == ac_name))
    asset_class = result.scalar_one_or_none()
    if asset_class is None:
        asset_class = AssetClass(name=ac_name)
        db.add(asset_class)
        await db.flush()

    result = await db.execute(select(InstrumentType).where(InstrumentType.name == it_name))
    instr_type = result.scalar_one_or_none()
    if instr_type is None:
        instr_type = InstrumentType(name=it_name, asset_class_id=asset_class.id)
        db.add(instr_type)
        await db.flush()

    instrument = Instrument(
        symbol=symbol,
        name=info.get("longName") or info.get("shortName") or symbol,
        description=info.get("longBusinessSummary"),
        currency=info.get("currency"),
        instrument_type_id=instr_type.id,
        is_active=True,
    )
    db.add(instrument)
    await db.flush()

    if quote_type in ("EQUITY", "ETF"):
        db.add(
            EquityDetail(
                instrument_id=instrument.id,
                sector=info.get("sector"),
                industry=info.get("industry"),
                country=info.get("country"),
                exchange_mic=info.get("exchange"),
                website=info.get("website"),
            )
        )

    db.add(
        InstrumentListing(
            instrument_id=instrument.id,
            ticker=symbol,
            currency=info.get("currency"),
            is_primary=True,
            is_active=True,
        )
    )

    # Populate stats from yfinance info
    stats_kwargs = {
        "week52_high":    info.get("fiftyTwoWeekHigh"),
        "week52_low":     info.get("fiftyTwoWeekLow"),
        "avg_volume_30d": info.get("averageVolume") or info.get("averageDailyVolume10Day"),
        "pe_ratio":       info.get("trailingPE") or info.get("forwardPE"),
        "market_cap":     info.get("marketCap"),
        "beta":           info.get("beta"),
        "dividend_yield": info.get("dividendYield"),
    }
    if any(v is not None for v in stats_kwargs.values()):
        db.add(InstrumentStats(instrument_id=instrument.id, **stats_kwargs))

    await db.commit()
    return await _reload_instrument_full(instrument.id, db)
