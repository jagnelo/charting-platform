from datetime import datetime

from pydantic import BaseModel, ConfigDict


class IndicatorPresetCreate(BaseModel):
    name: str
    description: str | None = None
    indicators: list = []
    is_default: bool = False


class IndicatorPresetUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    indicators: list | None = None
    is_default: bool | None = None


class IndicatorPresetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str | None = None
    indicators: list
    is_default: bool
    created_at: datetime
    updated_at: datetime
