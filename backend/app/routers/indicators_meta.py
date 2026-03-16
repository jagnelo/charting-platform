"""
Endpoint that exposes the indicator registry to the frontend.
The frontend uses this to build its indicator picker dynamically —
no hardcoded list, new indicators appear automatically.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.user import User
from app.services import indicators as ind_engine
from app.services.auth import get_current_user

router = APIRouter(prefix="/indicators", tags=["indicators"])


@router.get("")
def list_indicators():
    """Return all registered indicators with their metadata."""
    return ind_engine.list_indicators()


@router.get("/compute/{symbol}/{timeframe}")
def compute_indicator(
    symbol: str,
    timeframe: Timeframe,
    indicator: str = Query(...),
    params: str = Query("{}"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Compute an indicator for a symbol and return the values as a list
    parallel to the OHLCV bars. Frontend can overlay these directly.
    """
    import json

    parsed_params = json.loads(params)

    instrument = db.execute(
        select(Instrument).where(Instrument.symbol == symbol.upper())
    ).scalar_one_or_none()
    if instrument is None:
        return {"error": f"Instrument {symbol} not found"}

    bars = (
        db.execute(
            select(OHLCVBar)
            .where(OHLCVBar.instrument_id == instrument.id, OHLCVBar.timeframe == timeframe)
            .order_by(OHLCVBar.ts)
        )
        .scalars()
        .all()
    )

    if not bars:
        return {"timestamps": [], "values": {}}

    bars_df = ind_engine.bars_to_dataframe(bars)
    try:
        result_df = ind_engine.compute(indicator, bars_df, parsed_params)
    except ValueError as e:
        return {"error": str(e)}

    timestamps = [int(b.ts.timestamp()) for b in bars]
    values = {
        col: [
            None if (v != v or v is None) else float(v)  # NaN → None
            for v in result_df[col].tolist()
        ]
        for col in result_df.columns
    }
    return {"timestamps": timestamps, "values": values}
