from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.data_source import DataSource
from app.models.instrument import Instrument
from app.providers.alpaca import AlpacaProvider
from app.providers.base import (
    DiscoveryProvider,
    EventProvider,
    IdentifierProvider,
    InstrumentMetadataProvider,
    InstrumentSearchProvider,
    LatestPriceProvider,
    OptionChainProvider,
    OptionQuoteHistoryProvider,
    PriceHistoryProvider,
    ProviderDescriptor,
)
from app.providers.binance import BinanceProvider
from app.providers.coingecko import CoinGeckoProvider
from app.providers.edgar import EdgarProvider
from app.providers.etf_holdings_internal import ETFHoldingsInternalProvider
from app.providers.fred import FREDProvider
from app.providers.massive import MassiveProvider
from app.providers.openfigi import OpenFigiProvider
from app.providers.yfinance import YFinanceProvider

ProviderT = TypeVar("ProviderT", bound=ProviderDescriptor)

_PROVIDERS: dict[str, ProviderDescriptor] = {
    # Primary free providers
    "alpaca": AlpacaProvider(),  # US equity + crypto OHLCV, splits, dividends, universe
    "fred": FREDProvider(),  # Interest rates, forex series, macro indicators
    "binance": BinanceProvider(),  # Crypto OHLCV and universe
    "coingecko": CoinGeckoProvider(),  # Crypto metadata and discovery
    "edgar": EdgarProvider(),  # US company profile and earnings history
    "etf_holdings_internal": ETFHoldingsInternalProvider(),
    # Fallback / supplementary
    "yfinance": YFinanceProvider(),  # Broad fallback — options chains, futures, forward earnings
    "openfigi": OpenFigiProvider(),  # Stable identifier enrichment (FIGI, ISIN)
    "massive": MassiveProvider(),  # Reference ticker universe corroboration
}

_DEFAULT_PROVIDER_USAGE_PROFILES: dict[str, dict] = {
    name: {
        "mode": "call_count",
        "unit_label": "requests",
        "limit_kind": "unknown",
        "quota_limit": None,
        "quota_window_seconds": None,
        "estimated_quota_limit": None,
        "operation_costs": {},
    }
    for name in _PROVIDERS
}


def _capability_names(provider: ProviderDescriptor) -> list[str]:
    capabilities: list[tuple[tuple[str, ...], str]] = [
        (("search_instruments",), "instrument_search"),
        (("get_instrument_profile",), "instrument_metadata"),
        (("fetch_ohlcv", "fetch_latest_ohlcv", "latest_window_start"), "price_history"),
        (("get_current_price",), "latest_price"),
        (("fetch_instrument_events",), "instrument_events"),
        (("fetch_stable_identifiers",), "instrument_identifiers"),
        (("discover_universe_page", "supported_discovery_types"), "universe_discovery"),
        (("list_option_expirations", "fetch_option_chain"), "option_chain"),
        (("fetch_option_quote_history",), "option_quote_history"),
    ]
    return [
        name for required_methods, name in capabilities if _supports(provider, *required_methods)
    ]


def list_provider_capabilities(name: str) -> list[str]:
    return _capability_names(get_provider(name))


def get_provider(name: str) -> ProviderDescriptor:
    provider = _PROVIDERS.get(name)
    if provider is None:
        raise KeyError(f"Unknown provider '{name}'")
    return provider


def _require_capability(
    provider_name: str,
    required_methods: tuple[str, ...],
    capability_label: str,
) -> ProviderT:
    provider = get_provider(provider_name)
    if not _supports(provider, *required_methods):
        raise KeyError(f"Provider '{provider_name}' does not support {capability_label}")
    return cast(ProviderT, provider)


def _supports(provider: ProviderDescriptor, *method_names: str) -> bool:
    return all(callable(getattr(provider, method_name, None)) for method_name in method_names)


def get_price_history_provider(name: str) -> PriceHistoryProvider:
    return _require_capability(
        name,
        ("fetch_ohlcv", "fetch_latest_ohlcv", "latest_window_start"),
        "price history",
    )


def get_quote_provider(name: str) -> LatestPriceProvider:
    return _require_capability(name, ("get_current_price",), "latest price")


def get_metadata_provider(name: str) -> InstrumentMetadataProvider:
    return _require_capability(name, ("get_instrument_profile",), "instrument metadata")


def get_search_provider(name: str) -> InstrumentSearchProvider:
    return _require_capability(name, ("search_instruments",), "instrument search")


def get_event_provider(name: str) -> EventProvider:
    return _require_capability(name, ("fetch_instrument_events",), "instrument events")


def get_discovery_provider(name: str) -> DiscoveryProvider:
    return _require_capability(
        name,
        ("discover_universe_page", "supported_discovery_types"),
        "universe discovery",
    )


def get_identifier_provider(name: str) -> IdentifierProvider:
    return _require_capability(name, ("fetch_stable_identifiers",), "instrument identifiers")


def get_option_chain_provider(name: str) -> OptionChainProvider:
    return _require_capability(
        name,
        ("list_option_expirations", "fetch_option_chain"),
        "option chain data",
    )


def get_option_quote_history_provider(name: str) -> OptionQuoteHistoryProvider:
    return _require_capability(
        name,
        ("fetch_option_quote_history",),
        "option quote history",
    )


def get_default_market_data_provider() -> PriceHistoryProvider:
    return get_price_history_provider(settings.DEFAULT_MARKET_DATA_PROVIDER)


def get_default_quote_provider() -> LatestPriceProvider:
    return get_quote_provider(settings.DEFAULT_MARKET_DATA_PROVIDER)


def get_default_metadata_provider() -> InstrumentMetadataProvider:
    return get_metadata_provider(settings.DEFAULT_METADATA_PROVIDER)


def get_default_search_provider() -> InstrumentSearchProvider:
    return get_search_provider(settings.DEFAULT_METADATA_PROVIDER)


def get_default_event_provider() -> EventProvider:
    return get_event_provider(settings.DEFAULT_EVENT_PROVIDER)


def get_default_discovery_provider() -> DiscoveryProvider:
    return get_discovery_provider(settings.DEFAULT_DISCOVERY_PROVIDER)


def get_default_options_provider() -> OptionChainProvider:
    return get_option_chain_provider(settings.DEFAULT_OPTIONS_PROVIDER)


def get_option_quote_history_provider_chain() -> list[str]:
    providers = [name for name in settings.OPTION_QUOTE_HISTORY_PROVIDER_PRIORITY if name]
    return providers or [settings.DEFAULT_OPTIONS_PROVIDER]


def get_identifier_provider_chain() -> list[str]:
    return [name for name in settings.IDENTIFIER_PROVIDER_PRIORITY if name]


def get_identifier_providers() -> list[IdentifierProvider]:
    providers: list[IdentifierProvider] = []
    for name in get_identifier_provider_chain():
        try:
            providers.append(get_identifier_provider(name))
        except KeyError:
            continue
    return providers


def supported_provider_names() -> Sequence[str]:
    return tuple(_PROVIDERS.keys())


def get_provider_usage_profile(name: str) -> dict:
    profile = dict(_DEFAULT_PROVIDER_USAGE_PROFILES.get(name, {}))
    override = settings.PROVIDER_USAGE_PROFILE_SEEDS.get(name) or {}
    if not isinstance(override, dict):
        return profile
    merged = dict(profile)
    for key, value in override.items():
        if key == "operation_costs" and isinstance(value, dict):
            merged[key] = dict(profile.get(key) or {}) | value
        else:
            merged[key] = value
    return merged


async def ensure_data_source(db: AsyncSession, provider_name: str) -> DataSource:
    result = await db.execute(select(DataSource).where(DataSource.name == provider_name))
    src = result.scalar_one_or_none()
    provider = get_provider(provider_name)
    capabilities = _capability_names(provider)
    if src is None:
        src = DataSource(
            name=provider_name,
            base_url=provider.base_url,
            description=provider.description,
            is_active=True,
            config={
                "capabilities": capabilities,
                "usage_tracking": get_provider_usage_profile(provider_name),
            },
            supported_capabilities=capabilities,
        )
        db.add(src)
        await db.flush()
    else:
        src.base_url = provider.base_url
        src.description = provider.description
        src.supported_capabilities = capabilities
        config = dict(src.config or {})
        config["capabilities"] = capabilities
        config["usage_tracking"] = {
            **get_provider_usage_profile(provider_name),
            **dict(config.get("usage_tracking") or {}),
            "operation_costs": {
                **get_provider_usage_profile(provider_name).get("operation_costs", {}),
                **dict((config.get("usage_tracking") or {}).get("operation_costs") or {}),
            },
        }
        src.config = config
    return src


def provider_symbol_for_instrument(
    instrument: Instrument,
    provider_name: str | None = None,
) -> str:
    provider_symbols = instrument.__dict__.get("provider_symbols")
    if provider_symbols:
        primary_active: list[str] = []
        active: list[str] = []

        for provider_symbol in provider_symbols:
            data_source = provider_symbol.__dict__.get("data_source")
            extra_data = provider_symbol.extra_data or {}
            hinted_provider_name = (
                extra_data.get("provider_name") if isinstance(extra_data, dict) else None
            )
            if (
                provider_name is not None
                and data_source is not None
                and data_source.name != provider_name
            ):
                continue
            if provider_name is not None and data_source is None:
                if hinted_provider_name and hinted_provider_name != provider_name:
                    continue
                if hinted_provider_name is None and len(provider_symbols) > 1:
                    continue
            if provider_name is None or data_source is not None:
                if provider_symbol.is_active and provider_symbol.is_primary:
                    primary_active.append(provider_symbol.provider_symbol)
                elif provider_symbol.is_active:
                    active.append(provider_symbol.provider_symbol)
                continue

            # Relationship is intentionally not lazy-loaded here; if the data source
            # binding is unavailable in-memory we conservatively keep the symbol only
            # when there is a single unambiguous active candidate.
            if provider_symbol.is_active and provider_symbol.is_primary:
                primary_active.append(provider_symbol.provider_symbol)
            elif provider_symbol.is_active:
                active.append(provider_symbol.provider_symbol)

        if len(primary_active) == 1:
            return primary_active[0]
        if len(primary_active) > 1 and provider_name is None:
            return primary_active[0]
        if not primary_active and len(active) == 1:
            return active[0]
        if not primary_active and len(active) > 1 and provider_name is None:
            return active[0]

    listings = instrument.__dict__.get("listings")
    if listings:
        for listing in listings:
            if listing.is_primary and listing.is_active:
                return listing.ticker
        for listing in listings:
            if listing.is_active:
                return listing.ticker

    return instrument.symbol
