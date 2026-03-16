from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.ohlcv import Timeframe


class OHLCVBarOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    vwap: float | None = None
    is_adjusted: bool


class OHLCVRequest(BaseModel):
    symbol: str
    timeframe: Timeframe
    start: datetime
    end: datetime | None = None
    adjusted: bool = True
