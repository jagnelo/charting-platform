"""Provider-neutral options response contracts."""

from datetime import date, datetime

from pydantic import BaseModel, Field, field_serializer

from app.lib.time_utils import wire_datetime


class OptionExpirationResponse(BaseModel):
    symbol: str
    expirations: list[date]


class OptionChainRowOut(BaseModel):
    instrument_id: int
    symbol: str
    name: str
    currency: str | None = None
    right: str
    style: str
    strike: float
    expiry_date: date
    contract_size: float | None = None
    contract_key: str | None = None
    bid: float | None = None
    ask: float | None = None
    mark: float | None = None
    last: float | None = None
    volume: float | None = None
    open_interest: float | None = None
    implied_vol: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    rho: float | None = None
    observed_at: datetime | None = None
    provider_symbol: str | None = None
    provenance: dict[str, object] = Field(default_factory=dict)

    @field_serializer("observed_at")
    def serialize_observed_at(self, value: datetime | None) -> str | None:
        return wire_datetime(value)


class OptionChainSnapshotSummaryOut(BaseModel):
    id: int
    observed_at: datetime
    fetched_at: datetime
    provider: str | None = None
    contract_count: int

    @field_serializer("observed_at", "fetched_at")
    def serialize_timestamps(self, value: datetime) -> str:
        return wire_datetime(value) or ""


class OptionChainResponse(BaseModel):
    symbol: str
    expiration: date | None = None
    available_expirations: list[date]
    snapshot: OptionChainSnapshotSummaryOut | None = None
    rows: list[OptionChainRowOut]


class OptionContractSummaryOut(BaseModel):
    id: int
    symbol: str
    name: str
    currency: str | None = None
    contract_key: str | None = None
    right: str
    style: str
    strike: float
    expiry_date: date
    contract_size: float | None = None
    underlying_instrument_id: int
    provenance: dict[str, object] = Field(default_factory=dict)


class OptionQuotePointOut(BaseModel):
    observed_at: datetime
    bid: float | None = None
    ask: float | None = None
    mark: float | None = None
    last: float | None = None
    volume: float | None = None
    open_interest: float | None = None
    implied_vol: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    rho: float | None = None
    provider_symbol: str | None = None

    @field_serializer("observed_at")
    def serialize_observed_at(self, value: datetime) -> str:
        return wire_datetime(value) or ""
