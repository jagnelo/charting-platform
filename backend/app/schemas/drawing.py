from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.ohlcv import Timeframe


class ChartDrawingCreate(BaseModel):
    instrument_id: int
    timeframe: Timeframe | None = None
    pin_to_all: bool = False
    indicator_key: str | None = None
    drawing_type: str
    label: str | None = None
    notes: str | None = None
    data: dict = {}
    style: dict = {}
    is_visible: bool = True
    is_locked: bool = False


class ChartDrawingUpdate(BaseModel):
    timeframe: Timeframe | None = None
    pin_to_all: bool | None = None
    indicator_key: str | None = None
    label: str | None = None
    notes: str | None = None
    data: dict | None = None
    style: dict | None = None
    is_visible: bool | None = None
    is_locked: bool | None = None


class ChartDrawingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    instrument_id: int
    timeframe: Timeframe | None = None
    pin_to_all: bool
    indicator_key: str | None = None
    drawing_type: str
    label: str | None = None
    notes: str | None = None
    data: dict
    style: dict
    is_visible: bool
    is_locked: bool
    created_at: datetime
    updated_at: datetime
