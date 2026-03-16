"""
Indicators router — serves pre-computed indicator data and the indicator registry.
"""

import numpy as np
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.user import User
from app.services.indicators import (
    OHLCVSeries,
    compute_indicator,
    list_indicators,
)

router = APIRouter(prefix="/indicators", tags=["indicators"])


@router.get("/registry")
async def get_registry():
    """
    Return the full indicator registry — all available indicators with their
    parameters, output keys, and default styles. Used by the frontend to
    dynamically build the indicator picker UI.
    """
    return list_indicators()


@router.get("/compute/{symbol}/{timeframe}")
async def compute_for_chart(
    symbol: str,
    timeframe: Timeframe,
    indicator: str = Query(..., description="Indicator type, e.g. 'rsi'"),
    params: str = Query("{}", description="JSON params, e.g. '{\"period\":14}'"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Compute and return indicator values for a symbol+timeframe.
    The frontend can use this to get server-computed values
    (ensures consistency with the alert/screener engine).
    """
    import json

    instrument = (
        await db.execute(select(Instrument).where(Instrument.symbol == symbol.upper()))
    ).scalar_one_or_none()

    if instrument is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"Instrument '{symbol}' not found")

    try:
        parsed_params = json.loads(params)
    except Exception:
        parsed_params = {}

    stmt = (
        select(OHLCVBar)
        .where(OHLCVBar.instrument_id == instrument.id, OHLCVBar.timeframe == timeframe)
        .order_by(OHLCVBar.ts.desc())
        .limit(500)
    )
    bars = list((await db.execute(stmt)).scalars().all())
    bars.reverse()

    data = OHLCVSeries.from_orm_bars(bars)
    result = compute_indicator(indicator, data, parsed_params)

    # Convert numpy arrays to lists, replacing NaN with null
    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe.value,
        "indicator": indicator,
        "params": parsed_params,
        "timestamps": data.timestamps.tolist(),
        "values": {
            k: [None if np.isnan(v) else float(v) for v in arr] for k, arr in result.items()
        },
    }
