from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.instrument import Instrument
from app.models.ohlcv import Timeframe
from app.models.user import User
from app.schemas.ohlcv import OHLCVBarOut
from app.services.market_data import fetch_ohlcv

router = APIRouter(prefix="/ohlcv", tags=["ohlcv"])

TF_DEFAULT_DAYS = {
    Timeframe.M1: 5,
    Timeframe.M5: 30,
    Timeframe.M15: 60,
    Timeframe.M30: 90,
    Timeframe.H1: 180,
    Timeframe.H2: 360,
    Timeframe.H4: 365,
    Timeframe.H12: 365,
    Timeframe.D1: 365 * 5,
    Timeframe.W1: 365 * 10,
    Timeframe.MN: 365 * 20,
}


@router.get("/{symbol}/{timeframe}", response_model=list[OHLCVBarOut])
async def get_ohlcv(
    symbol: str,
    timeframe: Timeframe,
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
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

    if start is None:
        start = datetime.now(UTC) - timedelta(days=TF_DEFAULT_DAYS.get(timeframe, 365))
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end and end.tzinfo is None:
        end = end.replace(tzinfo=UTC)

    # Load listings for ticker resolution
    await db.refresh(instrument, ["listings"])
    return await fetch_ohlcv(db, instrument, timeframe, start, end, adjusted)
