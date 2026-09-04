from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ExchangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    mic: str
    name: str
    country_code: str | None = None
    timezone: str | None = None
    market_open: str | None = None
    market_close: str | None = None
    currency: str | None = None


class EquityDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    exchange_mic: str | None = None
    ipo_date: date | None = None
    market_cap_tier: str | None = None
    employees: int | None = None
    website: str | None = None
    logo_url: str | None = None
    field_provenance: dict | None = None


class InstrumentStatsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    week52_high: Decimal | None = None
    week52_low: Decimal | None = None
    avg_volume_30d: Decimal | None = None
    pe_ratio: Decimal | None = None
    market_cap: Decimal | None = None
    beta: Decimal | None = None
    dividend_yield: Decimal | None = None
    computed_at: datetime | None = None
    field_provenance: dict | None = None


class FieldProvenanceOut(BaseModel):
    source: str
    fetched_at: datetime | str | None = None
    observed_at: datetime | str | None = None
    provider_symbol: str | None = None
    selection_reason: str | None = None
    quality_score: float | None = None
    note: str | None = None


class InstrumentIdentifierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    identifier_type: str
    identifier_value: str
    is_primary: bool
    is_active: bool
    effective_at: datetime | None = None
    known_at: datetime | None = None
    retired_at: datetime | None = None
    extra_data: dict | None = None


class InstrumentListingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ticker: str
    currency: str | None = None
    is_primary: bool
    is_active: bool
    effective_at: datetime | None = None
    known_at: datetime | None = None
    delisted_at: datetime | None = None
    exchange: ExchangeOut | None = None


class OptionDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    underlying_instrument_id: int
    right: str
    style: str
    contract_key: str | None = None
    venue_code: str | None = None
    strike: Decimal
    expiry_date: date
    contract_size: Decimal | None = None
    delta: Decimal | None = None
    gamma: Decimal | None = None
    theta: Decimal | None = None
    vega: Decimal | None = None
    rho: Decimal | None = None
    implied_vol: Decimal | None = None
    field_provenance: dict | None = None


class SyntheticConstituentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ticker_alias: str
    constituent_instrument_id: int


class InstrumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    symbol: str
    name: str
    description: str | None = None
    currency: str | None = None
    is_active: bool
    domain_key: str | None = None
    identity_status: str = "provisional"
    issuer_id: int | None = None
    is_synthetic: bool = False
    expression: str | None = None
    primary_identifier_type: str | None = None
    primary_identifier_value: str | None = None
    field_provenance: dict | None = None
    equity_detail: EquityDetailOut | None = None
    option_detail: OptionDetailOut | None = None
    stats: InstrumentStatsOut | None = None
    identifiers: list[InstrumentIdentifierOut] = []
    listings: list[InstrumentListingOut] = []
    synthetic_constituents: list[SyntheticConstituentOut] = []


class InstrumentCreate(BaseModel):
    symbol: str
    name: str
    description: str | None = None
    currency: str | None = None
    instrument_type_id: int


class InstrumentSearchResult(BaseModel):
    symbol: str
    name: str
    exchange: str
    type: str
    is_synthetic: bool = False
    instrument_id: int | None = None
    domain_key: str | None = None
    identity_status: str | None = None


class InstrumentMembership(BaseModel):
    """Which watchlists and screeners the current instrument belongs to."""

    watchlists: list[dict] = []  # {id, name, is_managed}
    screeners: list[dict] = []  # {id, name, last_run_at, in_current_results}
