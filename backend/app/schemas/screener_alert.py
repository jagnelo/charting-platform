from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_serializer

from app.lib.time_utils import wire_datetime


class ScreenerAlertCreate(BaseModel):
    screener_id: int
    trigger_type: str = "both"  # 'entered' | 'left' | 'both'
    repeat: bool = False
    notes: str | None = None


class ScreenerAlertUpdate(BaseModel):
    trigger_type: str | None = None
    repeat: bool | None = None
    notes: str | None = None
    status: str | None = None  # 'active' | 'triggered' | 'disabled'


class ScreenerAlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    screener_id: int
    screener_name: str = ""
    trigger_type: str
    status: str
    repeat: bool
    notes: str | None
    triggered_at: datetime | None
    last_checked_run_id: int | None
    created_at: datetime
    updated_at: datetime

    @field_serializer("triggered_at", "created_at", "updated_at")
    def serialize_timestamps(self, value: datetime | None) -> str | None:
        return wire_datetime(value)
