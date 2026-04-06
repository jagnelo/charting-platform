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
    is_synthetic: bool = False
    expression: str | None = None
    equity_detail: EquityDetailOut | None = None
    stats: InstrumentStatsOut | None = None
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


class InstrumentMembership(BaseModel):
    """Which watchlists and screeners the current instrument belongs to."""

    watchlists: list[dict] = []  # {id, name, is_managed}
    screeners: list[dict] = []  # {id, name, last_run_at, in_current_results}
