from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_serializer

from app.lib.time_utils import wire_datetime


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

    @field_serializer("created_at", "updated_at")
    def serialize_timestamps(self, value: datetime) -> str:
        return wire_datetime(value) or ""
