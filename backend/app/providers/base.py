from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

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
    effective_at: datetime | None = None
    known_at: datetime | None = None
    delisted_at: datetime | None = None
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


@dataclass(slots=True)
class OptionContractRecord:
    provider_symbol: str
    underlying_symbol: str
    expiry_date: date
    strike: Decimal
    right: str
    currency: str | None = None
    contract_size: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    mark: Decimal | None = None
    last_price: Decimal | None = None
    volume: Decimal | None = None
    open_interest: Decimal | None = None
    implied_vol: Decimal | None = None
    delta: Decimal | None = None
    gamma: Decimal | None = None
    theta: Decimal | None = None
    vega: Decimal | None = None
    rho: Decimal | None = None
    observed_at: datetime | None = None
    extra_greeks: dict[str, Decimal | None] | None = None
    raw_payload: dict[str, Any] | None = None


@dataclass(slots=True)
class OptionQuotePointRecord:
    provider_symbol: str
    observed_at: datetime
    bid: Decimal | None = None
    ask: Decimal | None = None
    mark: Decimal | None = None
    last: Decimal | None = None
    volume: Decimal | None = None
    open_interest: Decimal | None = None
    implied_vol: Decimal | None = None
    delta: Decimal | None = None
    gamma: Decimal | None = None
    theta: Decimal | None = None
    vega: Decimal | None = None
    rho: Decimal | None = None
    extra_greeks: dict[str, Decimal | None] | None = None
    raw_payload: dict[str, Any] | None = None


@runtime_checkable
class ProviderDescriptor(Protocol):
    name: str
    base_url: str | None
    description: str | None


@runtime_checkable
class InstrumentSearchProvider(ProviderDescriptor, Protocol):
    def search_instruments(self, query: str, *, limit: int = 10) -> list[ProviderSearchResult]: ...


@runtime_checkable
class InstrumentMetadataProvider(ProviderDescriptor, Protocol):
    def get_instrument_profile(self, symbol: str) -> InstrumentProfile | None: ...


@runtime_checkable
class PriceHistoryProvider(ProviderDescriptor, Protocol):
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

    def latest_window_start(self, timeframe: Timeframe, limit: int) -> datetime: ...


@runtime_checkable
class LatestPriceProvider(ProviderDescriptor, Protocol):
    def get_current_price(self, symbol: str) -> float | None: ...


@runtime_checkable
class EventProvider(ProviderDescriptor, Protocol):
    def fetch_instrument_events(self, symbol: str) -> list[InstrumentEventRecord]: ...


@runtime_checkable
class IdentifierProvider(ProviderDescriptor, Protocol):
    def fetch_stable_identifiers(self, symbol: str) -> list[IdentifierRecord]: ...


@runtime_checkable
class DiscoveryProvider(ProviderDescriptor, Protocol):
    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]: ...

    def supported_discovery_types(self) -> list[str]: ...


@runtime_checkable
class OptionChainProvider(ProviderDescriptor, Protocol):
    def list_option_expirations(self, symbol: str) -> list[date]: ...

    def fetch_option_chain(
        self,
        symbol: str,
        *,
        expiration: date | None = None,
    ) -> list[OptionContractRecord]: ...


@runtime_checkable
class OptionQuoteHistoryProvider(ProviderDescriptor, Protocol):
    def fetch_option_quote_history(
        self,
        symbol: str,
        *,
        start: datetime,
        end: datetime,
    ) -> list[OptionQuotePointRecord]: ...


class MarketDataProvider(
    InstrumentSearchProvider,
    InstrumentMetadataProvider,
    PriceHistoryProvider,
    LatestPriceProvider,
    EventProvider,
    IdentifierProvider,
    DiscoveryProvider,
    Protocol,
):
    """Convenience composite used by all-in-one providers such as yfinance."""

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
