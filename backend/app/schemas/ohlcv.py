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
    is_derived: bool = False
    source_timeframe: str | None = None
    derivation_method: str | None = None
    derived_at: datetime | None = None
    source_bar_count: int | None = None
    source_start: datetime | None = None
    source_end: datetime | None = None


class OHLCVRequest(BaseModel):
    symbol: str
    timeframe: Timeframe
    start: datetime
    end: datetime | None = None
    adjusted: bool = True


class LocalSplitMaterializationOut(BaseModel):
    """Receipt for an explicit local split-adjusted derived-view build."""

    status: str
    factor_version: str | None = None
    raw_bar_count: int = 0
    persisted_bar_count: int = 0
    updated_bar_count: int = 0
    skipped_provider_bar_count: int = 0
    reason: str | None = None
