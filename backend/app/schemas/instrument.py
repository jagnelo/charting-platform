from datetime import date

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


class InstrumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    symbol: str
    name: str
    description: str | None = None
    currency: str | None = None
    is_active: bool
    equity_detail: EquityDetailOut | None = None


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
