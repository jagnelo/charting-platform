from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.instrument import Instrument
from app.models.ohlcv import Timeframe
from app.models.user import User
from app.schemas.ohlcv import OHLCVBarOut
from app.services.market_data import fetch_ohlcv, fetch_ohlcv_latest, fetch_ohlcv_page_before

router = APIRouter(prefix="/ohlcv", tags=["ohlcv"])

# Number of bars returned in one page. Chosen to be comfortable for rendering
# while giving enough history context for indicators (e.g. 200-period SMA).
PAGE_SIZE = 500


@router.get("/{symbol}/{timeframe}", response_model=list[OHLCVBarOut])
async def get_ohlcv(
    symbol: str,
    timeframe: Timeframe,
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    before: datetime | None = Query(
        None, description="Return PAGE_SIZE bars strictly before this timestamp (for pagination)"
    ),
    limit: int | None = Query(None, ge=1, description="Cap the number of bars returned"),
    adjusted: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Instrument).where(Instrument.symbol == symbol.upper()))
    instrument = result.scalar_one_or_none()
    if instrument is None:
        raise HTTPException(
            404, f"Instrument '{symbol}' not found. Visit /instruments/{symbol} first."
        )

    await db.refresh(instrument, ["listings"])

    if before is not None:
        # Paginated: return the PAGE_SIZE bars immediately before `before`
        if before.tzinfo is None:
            before = before.replace(tzinfo=UTC)
        bars = await fetch_ohlcv_page_before(db, instrument, timeframe, before, PAGE_SIZE, adjusted)
        return bars[-limit:] if limit else bars

    if start is not None:
        # Explicit range query (used by alert engine, screener, sparklines, etc.)
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        if end and end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
        bars = await fetch_ohlcv(db, instrument, timeframe, start, end, adjusted)
        return bars[-limit:] if limit else bars

    # Default: initial load — return the latest N bars (capped at PAGE_SIZE)
    page = min(limit, PAGE_SIZE) if limit else PAGE_SIZE
    return await fetch_ohlcv_latest(db, instrument, timeframe, page, adjusted)
