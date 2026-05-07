import json
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator


class AlertFiringEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    instrument_id: int | None
    instrument_symbol: str | None = None
    alert_type: str
    alert_id: int
    fired_at: datetime
    trigger_value: Decimal | None
    condition_snapshot: dict
    is_viewed: bool
    created_at: datetime

    @field_validator("condition_snapshot", mode="before")
    @classmethod
    def parse_snapshot(cls, v: object) -> dict:
        if isinstance(v, str):
            return json.loads(v)
        if isinstance(v, dict):
            return v
        return {}
