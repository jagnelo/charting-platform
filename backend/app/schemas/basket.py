from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BasketMemberInput(BaseModel):
    instrument_id: int | None = None
    symbol: str | None = None
    weight: Decimal | None = None
    label: str | None = None
    notes: str | None = None
    metadata: dict | None = None

    @model_validator(mode="after")
    def has_instrument_reference(self):
        if self.instrument_id is None and not (self.symbol or "").strip():
            raise ValueError("Each basket member needs an instrument_id or symbol.")
        return self


class BasketCreateRequest(BaseModel):
    name: str
    description: str | None = None
    weighting_scheme: str = "equal"
    rebalance_frequency: str | None = None
    classification_mode: str | None = "auto"
    sector: str | None = None
    industry: str | None = None
    metadata: dict | None = None
    members: list[BasketMemberInput] = Field(default_factory=list)


class BasketUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    weighting_scheme: str | None = None
    rebalance_frequency: str | None = None
    classification_mode: str | None = None
    sector: str | None = None
    industry: str | None = None
    metadata: dict | None = None
    members: list[BasketMemberInput] | None = None


class BasketMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    instrument_id: int
    symbol: str | None = None
    name: str | None = None
    source_holding_id: int | None = None
    position: int
    weight: Decimal | None = None
    label: str | None = None
    notes: str | None = None
    metadata: dict | None = None
    created_at: datetime
    updated_at: datetime


class BasketSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    basket_id: int
    composition_date: date
    known_at: datetime | None = None
    source_type: str
    source_snapshot_id: int | None = None
    member_count: int
    metadata: dict | None = None
    created_at: datetime
    updated_at: datetime


class BasketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None = None
    name: str
    description: str | None = None
    source_type: str
    weighting_scheme: str
    rebalance_frequency: str | None = None
    classification_mode: str | None = None
    sector: str | None = None
    industry: str | None = None
    source_etf_profile_id: int | None = None
    source_snapshot_id: int | None = None
    composition_date: date | None = None
    snapshot_count: int = 0
    latest_snapshot_date: date | None = None
    is_system_managed: bool
    is_read_only: bool
    metadata: dict | None = None
    members: list[BasketMemberOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
