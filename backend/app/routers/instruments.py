from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.asset_class import AssetClass, InstrumentType
from app.models.instrument import EquityDetail, Instrument
from app.models.listing import InstrumentListing
from app.models.ohlcv import OHLCVBar
from app.models.user import User
from app.schemas.instrument import InstrumentOut, InstrumentSearchResult
from app.services.bulk_fetch import get_fetch_progress
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

    await db.commit()
    await db.refresh(instrument)
    await db.refresh(instrument, ["equity_detail"])
    return instrument
