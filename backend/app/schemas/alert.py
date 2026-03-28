from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from sqlalchemy.orm import selectinload

from app.models.price_alert import AlertCondition, AlertStatus


class PriceAlertCreate(BaseModel):
    instrument_id: int
    condition: AlertCondition
    threshold_price: Decimal
    reference_price: Decimal | None = None
    price_field: str = "close"          # open | high | low | close
    within_percent: Decimal | None = None  # required when condition=within_percent
    repeat: bool = False
    notes: str | None = None


class PriceAlertUpdate(BaseModel):
    condition: AlertCondition | None = None
    threshold_price: Decimal | None = None
    status: AlertStatus | None = None
    repeat: bool | None = None
    notes: str | None = None


class PriceAlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    instrument_id: int
    instrument_symbol: str = ''
    condition: AlertCondition
    threshold_price: Decimal
    reference_price: Decimal | None = None
    price_field: str = "close"
    within_percent: Decimal | None = None
    status: AlertStatus
    repeat: bool
    notes: str | None = None
    triggered_at: datetime | None = None
    trigger_count: int
    last_known_price: Decimal | None = None
    created_at: datetime
    updated_at: datetime
