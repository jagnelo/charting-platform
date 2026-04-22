from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from app.models.instrument_event import EventTimeHint, InstrumentEventType
from app.models.ohlcv import OHLCVBar, Timeframe


@dataclass(slots=True)
class IdentifierRecord:
    identifier_type: str
    identifier_value: str
    is_primary: bool = False
    source: str | None = None
    extra_data: dict[str, Any] | None = None


@dataclass(slots=True)
class ListingRecord:
    provider_symbol: str
    exchange_code: str | None = None
    currency: str | None = None
    provider_instrument_type: str | None = None
    is_primary: bool = False
    extra_data: dict[str, Any] | None = None


@dataclass(slots=True)
class InstrumentProfile:
    provider: str
    symbol: str
    canonical_symbol: str
    name: str
    description: str | None = None
    currency: str | None = None
    quote_type: str | None = None
    exchange: str | None = None
    identifiers: list[IdentifierRecord] = field(default_factory=list)
    listings: list[ListingRecord] = field(default_factory=list)
    raw_payload: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderSearchResult:
    symbol: str
    name: str
    exchange: str = ""
    instrument_type: str = ""


@dataclass(slots=True)
class InstrumentEventRecord:
    event_type: InstrumentEventType
    event_time: datetime
    time_hint: EventTimeHint
    title: str
    source_event_key: str
    fetched_at: datetime
    value: Decimal | None = None
    actual: Decimal | None = None
    eps_estimate: Decimal | None = None
    eps_actual: Decimal | None = None
    eps_surprise: Decimal | None = None
    eps_surprise_pct: Decimal | None = None
    dividend_amount: Decimal | None = None
    split_ratio: Decimal | None = None
    raw_payload: str | None = None


class MarketDataProvider(Protocol):
    name: str
    base_url: str | None
    description: str | None

    def search_instruments(self, query: str, *, limit: int = 10) -> list[ProviderSearchResult]: ...

    def get_instrument_profile(self, symbol: str) -> InstrumentProfile | None: ...

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        *,
        adjusted: bool = True,
        instrument_id: int | None = None,
        data_source_id: int | None = None,
    ) -> list[OHLCVBar]: ...

    def fetch_latest_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: int,
        *,
        adjusted: bool = True,
        instrument_id: int | None = None,
        data_source_id: int | None = None,
    ) -> list[OHLCVBar]: ...

    def get_current_price(self, symbol: str) -> float | None: ...

    def fetch_instrument_events(self, symbol: str) -> list[InstrumentEventRecord]: ...

    def fetch_stable_identifiers(self, symbol: str) -> list[IdentifierRecord]: ...

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]: ...
