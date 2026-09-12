from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    marketdata_app_reviewed_plan,
    provider_positive_integer,
    provider_rate_limit_seed,
    provider_required_operation_byte_bounds,
    provider_reviewed_flag,
    settings,
)
from app.models.data_source import DataSource
from app.models.instrument import Instrument
from app.providers.alpaca import AlpacaProvider
from app.providers.alpha_vantage import AlphaVantageProvider
from app.providers.base import (
    DiscoveryProvider,
    EventProvider,
    FundamentalsProvider,
    IdentifierProvider,
    InstrumentMetadataProvider,
    InstrumentSearchProvider,
    LatestPriceProvider,
    MarketEventProvider,
    OptionChainProvider,
    OptionQuoteHistoryProvider,
    PriceHistoryProvider,
    ProviderDescriptor,
    ShortInterestProvider,
    TokenizedAssetProvider,
    TokenizedCorporateActionProvider,
)
from app.providers.binance import BinanceProvider
from app.providers.coingecko import CoinGeckoProvider
from app.providers.configured import OPTIONAL_PROVIDER_DESCRIPTORS
from app.providers.crypto_market_data import CoinbaseProvider, KrakenProvider
from app.providers.edgar import EdgarProvider, is_valid_edgar_user_agent
from app.providers.etf_holdings_internal import ETFHoldingsInternalProvider
from app.providers.finra import FINRAProvider
from app.providers.finra_otc_directory import FINRAOTCDirectoryProvider
from app.providers.fred import FREDProvider
from app.providers.ibkr import IBKRProvider
from app.providers.massive import MassiveProvider
from app.providers.nasdaq import NasdaqProvider
from app.providers.openfigi import OpenFigiProvider
from app.providers.optional_market_data import (
    EODHDProvider,
    FinnhubProvider,
    FMPProvider,
    MarketDataAppProvider,
    MarketstackProvider,
    TiingoProvider,
    TradierProvider,
    TwelveDataProvider,
)
from app.providers.tokenized import (
    BybitXStocksProvider,
    DinariTokenProvider,
    GateTradfiProvider,
    KrakenXStocksProvider,
    OndoGlobalMarketsProvider,
    RobinhoodTokenProvider,
    XStocksProvider,
)
from app.providers.yfinance import YFinanceProvider

ProviderT = TypeVar("ProviderT", bound=ProviderDescriptor)

_PROVIDERS: dict[str, ProviderDescriptor] = {
    # Primary free providers
    "alpaca": AlpacaProvider(),  # US equity + crypto OHLCV, splits, dividends, universe
    "fred": FREDProvider(),  # Interest rates, forex series, macro indicators
    "binance": BinanceProvider(),  # Crypto OHLCV and universe
    "coingecko": CoinGeckoProvider(),  # Crypto metadata and discovery
    "coinbase": CoinbaseProvider(),  # Keyless public crypto exchange data
    "kraken": KrakenProvider(),  # Keyless public crypto exchange data
    "edgar": EdgarProvider(),  # US company profile and earnings history
    "etf_holdings_internal": ETFHoldingsInternalProvider(),
    # Fallback / supplementary
    "yfinance": YFinanceProvider(),  # Broad fallback — options chains, futures, forward earnings
    "openfigi": OpenFigiProvider(),  # Stable identifier enrichment (FIGI, ISIN)
    "massive": MassiveProvider(),  # Reference ticker universe corroboration
    "nasdaq": NasdaqProvider(),  # Official US NMS listing/lifecycle directory evidence
    "alpha_vantage": AlphaVantageProvider(),  # Quota-limited daily-history corroboration
    "finra": FINRAProvider(),  # Consolidated short-interest datasets (endpoint configurable)
    "finra_otc_directory": FINRAOTCDirectoryProvider(),  # Explicitly configured OTC directory evidence
    # Optional low-cost adapters. They remain absent from default chains and
    # entitlement seeds until credentials, quotas, and redistribution terms
    # are reviewed by operations.
    "tiingo": TiingoProvider(),
    "twelve_data": TwelveDataProvider(),
    "finnhub": FinnhubProvider(),
    "marketstack": MarketstackProvider(),
    "eodhd": EODHDProvider(),
    "fmp": FMPProvider(),
    "tradier": TradierProvider(),
    "marketdata_app": MarketDataAppProvider(),
    "ibkr": IBKRProvider(),
    "xstocks": XStocksProvider(),
    "robinhood_tokens": RobinhoodTokenProvider(),
    "bybit_xstocks": BybitXStocksProvider(),
    "gate_tradfi": GateTradfiProvider(),
    "kraken_xstocks": KrakenXStocksProvider(),
    "dinari": DinariTokenProvider(),
    "ondo_global_markets": OndoGlobalMarketsProvider(),
}

# Provider capability is not enough to route an instrument safely.  Several
# public adapters expose a method with the same shape as equity OHLCV while
# accepting only crypto (Coinbase/Kraken/Binance are the important examples).
# Keep this allow-list explicit and fail closed when an instrument class is
# known.  The values intentionally use both top-level asset classes and
# instrument-type aliases because the database models distinguish, for
# example, Equity/ETF from Derivative/Option.
_PROVIDER_INSTRUMENT_KINDS: dict[str, frozenset[str]] = {
    "alpaca": frozenset({"equity", "stock", "etf", "crypto", "cryptocurrency", "crypto_spot"}),
    "alpha_vantage": frozenset({"equity", "stock", "etf", "forex", "currency", "crypto", "cryptocurrency"}),
    "massive": frozenset({"equity", "stock", "etf"}),
    "edgar": frozenset({"equity", "stock", "etf", "reit", "mutual_fund", "closed_end_fund"}),
    "nasdaq": frozenset({"equity", "stock", "etf", "reit", "mutual_fund", "closed_end_fund"}),
    "finra": frozenset({"equity", "stock", "etf", "reit", "mutual_fund", "closed_end_fund"}),
    "finra_otc_directory": frozenset({"equity", "stock", "etf", "reit", "mutual_fund", "closed_end_fund"}),
    "tiingo": frozenset({"equity", "stock", "etf", "forex", "currency", "crypto", "cryptocurrency"}),
    "twelve_data": frozenset({"equity", "stock", "etf", "forex", "currency", "crypto", "cryptocurrency", "future"}),
    "finnhub": frozenset({"equity", "stock", "etf", "forex", "currency", "crypto", "cryptocurrency"}),
    "marketstack": frozenset({"equity", "stock", "etf"}),
    "eodhd": frozenset({"equity", "stock", "etf", "forex", "currency", "crypto", "cryptocurrency", "future"}),
    "fmp": frozenset({"equity", "stock", "etf", "forex", "currency", "crypto", "cryptocurrency", "future"}),
    "tradier": frozenset({"equity", "stock", "etf", "option", "options"}),
    "marketdata_app": frozenset({"equity", "stock", "etf", "option", "options"}),
    # Tokenized assets are first-class instruments created by
    # ``tokenized_assets.upsert_tokenized_asset``.  Keep their provider
    # adapters admissible when a caller routes by the stored instrument ID;
    # the provider symbol remains distinct from the economic underlying.
    "xstocks": frozenset({"tokenized_securities", "tokenized_security", "tokenized"}),
    "robinhood_tokens": frozenset({"tokenized_securities", "tokenized_security", "tokenized"}),
    "bybit_xstocks": frozenset({"tokenized_securities", "tokenized_security", "tokenized"}),
    "gate_tradfi": frozenset({"tokenized_securities", "tokenized_security", "tokenized"}),
    "kraken_xstocks": frozenset({"tokenized_securities", "tokenized_security", "tokenized"}),
    "dinari": frozenset({"tokenized_securities", "tokenized_security", "tokenized"}),
    "ondo_global_markets": frozenset({"tokenized_securities", "tokenized_security", "tokenized"}),
    "ibkr": frozenset({"equity", "stock", "etf", "option", "options", "future", "forex", "currency", "crypto", "cryptocurrency"}),
    "yfinance": frozenset({"equity", "stock", "etf", "option", "options", "future", "forex", "currency", "crypto", "cryptocurrency", "index"}),
    "binance": frozenset({"crypto", "cryptocurrency", "crypto_spot"}),
    "coinbase": frozenset({"crypto", "cryptocurrency", "crypto_spot"}),
    "kraken": frozenset({"crypto", "cryptocurrency", "crypto_spot", "future"}),
    "coingecko": frozenset({"crypto", "cryptocurrency", "crypto_spot"}),
    "fred": frozenset({"macro", "currency", "forex", "fixed_income"}),
    "openfigi": frozenset({
        "equity", "stock", "etf", "option", "options", "future", "forex", "currency",
        "crypto", "cryptocurrency", "index", "fixed_income", "commodity",
    }),
    "etf_holdings_internal": frozenset({"equity", "etf"}),
}


def _instrument_kind(value: str | None) -> str:
    """Normalize model/provider class labels into stable routing tokens."""

    return "".join(character for character in str(value or "").strip().lower() if character.isalnum())


def provider_supports_instrument(
    provider_name: str,
    *,
    asset_class: str | None,
    instrument_type: str | None = None,
) -> bool:
    """Return whether a provider is explicitly admitted for an instrument kind.

    A known instrument must never be sent to an unmapped provider.  Unknown
    providers therefore fail closed instead of silently inheriting a broad
    method-level capability such as ``fetch_ohlcv``.
    """

    supported = _PROVIDER_INSTRUMENT_KINDS.get(provider_name, frozenset())
    if not supported:
        return False
    return any(
        _instrument_kind(value) in {_instrument_kind(item) for item in supported}
        for value in (asset_class, instrument_type)
        if value
    )
# Keep descriptor-only entries visible for broker/crypto integrations that do
# not yet have a concrete adapter. ``setdefault`` preserves concrete classes.
for _name, _descriptor in OPTIONAL_PROVIDER_DESCRIPTORS.items():
    _PROVIDERS.setdefault(_name, _descriptor)

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

# Keep the admin usage view and runtime reservation contract sourced from the
# same provider-specific declarations.  Unknown providers intentionally retain
# ``limit_kind=unknown`` and are not routable.
for _provider_name in settings.PROVIDER_RATE_LIMIT_SEEDS:
    if _provider_name not in _DEFAULT_PROVIDER_USAGE_PROFILES:
        continue
    _profile = _DEFAULT_PROVIDER_USAGE_PROFILES[_provider_name]
    _rate_seed = provider_rate_limit_seed(_provider_name)
    _contract = _rate_seed.get("quota_contract") if isinstance(_rate_seed, dict) else None
    _dimensions = (_contract or {}).get("dimensions") if isinstance(_contract, dict) else None
    if isinstance(_dimensions, list) and _dimensions:
        _profile["limit_kind"] = "multi_dimensional"
        _profile["quota_dimensions"] = _dimensions
        _profile["quota_window_seconds"] = min(
            int(item["window_seconds"])
            for item in _dimensions
            if isinstance(item, dict) and str(item.get("window_seconds", "")).isdigit()
        )
        _profile["quota_limit"] = min(
            int(item["limit"])
            for item in _dimensions
            if isinstance(item, dict) and str(item.get("limit", "")).isdigit()
        )


def _capability_names(provider: ProviderDescriptor) -> list[str]:
    capabilities: list[tuple[tuple[str, ...], str]] = [
        (("search_instruments",), "instrument_search"),
        (("get_instrument_profile",), "instrument_metadata"),
        (("fetch_ohlcv", "fetch_latest_ohlcv", "latest_window_start"), "price_history"),
        (("get_current_price",), "latest_price"),
        (("fetch_instrument_events",), "instrument_events"),
        (("fetch_stable_identifiers",), "instrument_identifiers"),
        (("fetch_fundamental_facts",), "fundamentals"),
        (("fetch_short_interest",), "short_interest"),
        (("fetch_market_events",), "market_events"),
        (("discover_universe_page", "supported_discovery_types"), "universe_discovery"),
        (("list_option_expirations", "fetch_option_chain"), "option_chain"),
        (("fetch_option_quote_history",), "option_quote_history"),
        (("discover_tokenized_assets", "get_tokenized_asset", "get_tokenized_price"), "tokenized_assets"),
        (("fetch_tokenized_corporate_actions",), "tokenized_corporate_actions"),
    ]
    capabilities = [
        name for required_methods, name in capabilities if _supports(provider, *required_methods)
    ]
    provider_name = str(getattr(provider, "name", "")).lower()
    if "price_history" in capabilities and provider_name in {
        "binance",
        "coingecko",
        "coinbase",
        "kraken",
    }:
        capabilities.append("crypto_history")
    if "price_history" in capabilities and (
        provider_name == "yfinance" or bool(getattr(provider, "supports_futures_history", False))
    ):
        capabilities.append("futures_history")
    if "option_chain" in capabilities:
        capabilities.append("options_current")
    if "instrument_events" in capabilities:
        if provider_name in {"alpaca", "yfinance"}:
            capabilities.append("corporate_actions")
        if provider_name in {"alpha_vantage", "edgar", "finnhub", "yfinance"}:
            capabilities.append("earnings")
    return capabilities


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


def get_fundamentals_provider(name: str) -> FundamentalsProvider:
    return _require_capability(name, ("fetch_fundamental_facts",), "fundamental facts")


def get_short_interest_provider(name: str) -> ShortInterestProvider:
    return _require_capability(name, ("fetch_short_interest",), "short interest")


def get_market_event_provider(name: str) -> MarketEventProvider:
    return _require_capability(name, ("fetch_market_events",), "market events")


def get_tokenized_asset_provider(name: str) -> TokenizedAssetProvider:
    return _require_capability(
        name,
        ("discover_tokenized_assets", "get_tokenized_asset", "get_tokenized_price"),
        "tokenized assets",
    )


def get_tokenized_corporate_action_provider(name: str) -> TokenizedCorporateActionProvider:
    return _require_capability(
        name,
        ("fetch_tokenized_corporate_actions",),
        "tokenized corporate actions",
    )


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


_AUTH_SETTINGS: dict[str, tuple[str, ...]] = {
    "alpaca": ("ALPACA_API_KEY", "ALPACA_SECRET_KEY"),
    "massive": ("MASSIVE_API_KEY",),
    "alpha_vantage": ("ALPHA_VANTAGE_API_KEY",),
    "fred": ("FRED_API_KEY",),
    "coingecko": ("COINGECKO_API_KEY",),
    "tiingo": ("TIINGO_API_KEY",),
    "twelve_data": ("TWELVE_DATA_API_KEY",),
    "finnhub": ("FINNHUB_API_KEY",),
    "marketstack": ("MARKETSTACK_API_KEY",),
    "eodhd": ("EODHD_API_KEY",),
    "fmp": ("FMP_API_KEY",),
    "tradier": ("TRADIER_API_KEY",),
    "marketdata_app": ("MARKETDATA_APP_API_KEY",),
    "ibkr": ("IBKR_READ_ONLY_SESSION_COOKIE",),
    "finra": ("FINRA_CLIENT_ID", "FINRA_CLIENT_SECRET"),
    "dinari": ("DINARI_API_KEY_ID", "DINARI_API_SECRET_KEY"),
    "ondo_global_markets": ("ONDO_GLOBAL_MARKETS_API_KEY",),
}

# Some adapters need an operator-approved source/configuration value even
# though they do not authenticate with that source. Keep these separate from
# credential settings so a missing URL is visible as ``not configured`` rather
# than being mistaken for a valid keyless provider.
_CONFIGURATION_SETTINGS: dict[str, tuple[str, ...]] = {
    "finra_otc_directory": ("FINRA_OTC_SYMBOL_DIRECTORY_URL",),
    # A Marketstack ticker read must be explicitly scoped to a provider MIC.
    # Without this, a single-venue default could be mistaken for US coverage.
    "marketstack": ("MARKETSTACK_API_KEY", "MARKETSTACK_DISCOVERY_EXCHANGE"),
    "ibkr": ("IBKR_READ_ONLY_URL",),
}

# These controls do not authenticate a provider. They bound provider-specific
# response/usage dimensions before the runtime can admit a route. Keep them
# separate from credential diagnostics so an operator can distinguish
# "credential missing" from "credential present but quota safety incomplete".
_ROUTING_CONTROL_SETTINGS: dict[str, tuple[str, ...]] = {
    # Corporate actions follow a provider cursor, so operation cost is the
    # reviewed maximum number of pages rather than an invented one-request
    # default. The adapter remains directly testable while routing is closed
    # until this non-secret bound is configured.
    "alpaca": ("ALPACA_CORPORATE_ACTIONS_MAX_PAGES",),
    "finra": ("FINRA_ASYNC_MAX_RESULT_BYTES",),
    "finra_otc_directory": (
        "FINRA_OTC_OPERATION_COSTS",
        "FINRA_OTC_TERMS_REVIEWED",
        "FINRA_OTC_COMPLETENESS_REVIEWED",
        "FINRA_OTC_REDISTRIBUTION_REVIEWED",
        "FINRA_OTC_POLL_INTERVAL_SECONDS",
    ),
    "fred": (
        "FRED_REVIEWED_LIMIT_SCOPE",
        "FRED_REVIEWED_REQUESTS_PER_MINUTE",
        "FRED_SERIES_TERMS_REVIEWED",
    ),
    "tiingo": ("TIINGO_OPERATION_BYTE_BOUNDS",),
    "fmp": ("FMP_OPERATION_BYTE_BOUNDS",),
    # MarketData.app account plans have distinct daily credit pools.  Native
    # response headers are telemetry; admission uses only this explicit
    # operator-reviewed plan/limit pair.
    "marketdata_app": (
        "MARKETDATA_APP_REVIEWED_PLAN",
        "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT",
    ),
}


def provider_configuration_required(name: str) -> bool:
    """Return whether the adapter needs explicit non-credential configuration."""

    return name in _CONFIGURATION_SETTINGS


def _marketstack_requires_discovery_scope(operation: str | None) -> bool:
    """Whether a Marketstack operation needs an explicit venue/MIC scope.

    Marketstack's ticker catalogue is venue-scoped, while EOD history and
    quote reads use only the API key.  Keep the discovery guard narrow so a
    missing catalogue scope cannot disable otherwise valid history routing.
    Provider-level diagnostics pass ``None`` and therefore report the full
    configuration requirement.
    """

    if operation is None:
        return True
    family = str(operation).strip().split(":", 1)[0]
    return family in {"discover_universe_page", "reconcile_universe_page"}


def provider_required_settings(name: str, operation: str | None = None) -> tuple[str, ...]:
    """Return required environment-setting names without exposing values.

    ``operation`` is used only for provider-specific configuration that
    applies to one capability (currently Marketstack discovery's exchange
    scope).  Omitting it retains the provider-level diagnostic view.
    """

    configured = _CONFIGURATION_SETTINGS.get(name, ())
    if name == "marketstack" and not _marketstack_requires_discovery_scope(operation):
        configured = tuple(
            setting_name
            for setting_name in configured
            if setting_name != "MARKETSTACK_DISCOVERY_EXCHANGE"
        )
    required = list(configured)
    required.extend(_AUTH_SETTINGS.get(name, ()))
    if name == "massive":
        required.append("MARKETDATA_API_KEY")
    if name == "edgar":
        required.append("EDGAR_USER_AGENT")
    return tuple(dict.fromkeys(required))


def provider_missing_settings(name: str, operation: str | None = None) -> list[str]:
    """Return missing required setting names for operator diagnostics only."""

    missing = []
    if name == "massive" and any(
        bool(str(getattr(settings, setting_name, "") or "").strip())
        for setting_name in ("MASSIVE_API_KEY", "MARKETDATA_API_KEY")
    ):
        return missing
    for setting_name in provider_required_settings(name, operation):
        value = str(getattr(settings, setting_name, "") or "").strip()
        if not value or (setting_name == "EDGAR_USER_AGENT" and not is_valid_edgar_user_agent(value)):
            missing.append(setting_name)
    return missing


def provider_routing_control_settings(
    name: str, operation: str | None = None
) -> tuple[str, ...]:
    """Return non-secret routing-safety setting names for operator diagnostics.

    Alpaca's page bound is specific to corporate actions; it is not a
    prerequisite for the provider's history, latest-price, or discovery
    operations.
    """

    if name == "alpaca" and operation is not None and operation != "fetch_instrument_events":
        return ()

    return _ROUTING_CONTROL_SETTINGS.get(name, ())


def provider_missing_routing_controls(
    name: str, operation: str | None = None
) -> list[str]:
    """Return missing provider-specific routing controls without their values.

    Some controls apply to one response-priced operation rather than every
    capability exposed by a provider. ``operation`` lets runtime routing keep
    unrelated Alpaca surfaces (history, latest price, discovery) eligible while
    still fail-closing corporate-actions calls without a reviewed page bound.
    The provider-level diagnostics call omits it and therefore reports the
    outstanding control for operator visibility.
    """

    required = provider_routing_control_settings(name, operation)
    if not required:
        return []
    if name == "finra":
        configured = provider_positive_integer(
            getattr(settings, "FINRA_ASYNC_MAX_RESULT_BYTES", 0)
        )
        return [] if configured is not None else list(required)
    if name == "alpaca":
        if operation is not None and operation != "fetch_instrument_events":
            return []
        configured = provider_positive_integer(
            getattr(settings, "ALPACA_CORPORATE_ACTIONS_MAX_PAGES", 0)
        )
        return [] if configured is not None else list(required)
    if name == "finra_otc_directory":
        configured_map = getattr(settings, "FINRA_OTC_OPERATION_COSTS", {}) or {}
        operations = ("discover_universe_page", "reconcile_universe_page")
        missing: list[str] = []
        if not isinstance(configured_map, dict):
            missing.append("FINRA_OTC_OPERATION_COSTS")
        elif not all(
            isinstance(configured_map.get(operation), int)
            and not isinstance(configured_map.get(operation), bool)
            and configured_map[operation] > 0
            for operation in operations
        ):
            missing.append("FINRA_OTC_OPERATION_COSTS")
        if not provider_reviewed_flag(
            getattr(settings, "FINRA_OTC_TERMS_REVIEWED", False)
        ):
            missing.append("FINRA_OTC_TERMS_REVIEWED")
        if not provider_reviewed_flag(
            getattr(settings, "FINRA_OTC_COMPLETENESS_REVIEWED", False)
        ):
            missing.append("FINRA_OTC_COMPLETENESS_REVIEWED")
        if not provider_reviewed_flag(
            getattr(settings, "FINRA_OTC_REDISTRIBUTION_REVIEWED", False)
        ):
            missing.append("FINRA_OTC_REDISTRIBUTION_REVIEWED")
        poll_interval = provider_positive_integer(
            getattr(settings, "FINRA_OTC_POLL_INTERVAL_SECONDS", 0)
        )
        if poll_interval is None:
            missing.append("FINRA_OTC_POLL_INTERVAL_SECONDS")
        return list(dict.fromkeys(missing))
    if name == "fred":
        scope = str(getattr(settings, "FRED_REVIEWED_LIMIT_SCOPE", "") or "").strip()
        reviewed_limit = provider_positive_integer(
            getattr(settings, "FRED_REVIEWED_REQUESTS_PER_MINUTE", 0)
        )
        terms_reviewed = provider_reviewed_flag(
            getattr(settings, "FRED_SERIES_TERMS_REVIEWED", False)
        )
        missing: list[str] = []
        if scope not in {"api_key", "account", "ip", "deployment"}:
            missing.append("FRED_REVIEWED_LIMIT_SCOPE")
        if reviewed_limit is None or reviewed_limit > 120:
            missing.append("FRED_REVIEWED_REQUESTS_PER_MINUTE")
        if not terms_reviewed:
            missing.append("FRED_SERIES_TERMS_REVIEWED")
        return missing
    if name == "marketdata_app":
        return [] if marketdata_app_reviewed_plan() is not None else list(required)
    configured_map = getattr(settings, required[0], {}) or {}
    if not isinstance(configured_map, dict):
        return list(required)
    operations = provider_required_operation_byte_bounds(name)
    if not operations:
        return list(required)
    return (
        []
        if all(
            isinstance(configured_map.get(operation), int)
            and not isinstance(configured_map.get(operation), bool)
            and configured_map[operation] > 0
            for operation in operations
        )
        else list(required)
    )


def provider_is_configured(name: str, operation: str | None = None) -> bool:
    """Return whether the deployment supplied required adapter inputs.

    Configuration requirements may be operation-specific.  In particular,
    Marketstack history/quote reads require only the API key; its universe
    discovery operations additionally require an explicit exchange scope.
    """

    if name in _CONFIGURATION_SETTINGS:
        return not provider_missing_settings(name, operation)

    required = _AUTH_SETTINGS.get(name)
    if required is None:
        if name == "edgar":
            user_agent = str(getattr(settings, "EDGAR_USER_AGENT", "") or "").strip()
            return is_valid_edgar_user_agent(user_agent)
        return True
    if name == "massive":
        return any(
            bool(str(getattr(settings, key, "") or "").strip())
            for key in ("MASSIVE_API_KEY", "MARKETDATA_API_KEY")
        )
    return all(bool(str(getattr(settings, key, "") or "").strip()) for key in required)


def get_provider_usage_profile(name: str) -> dict:
    profile = dict(_DEFAULT_PROVIDER_USAGE_PROFILES.get(name, {}))
    override = settings.PROVIDER_USAGE_PROFILE_SEEDS.get(name) or {}
    merged = dict(profile)
    if isinstance(override, dict):
        for key, value in override.items():
            if key == "operation_costs" and isinstance(value, dict):
                merged[key] = dict(profile.get(key) or {}) | value
            else:
                merged[key] = value
    rate_seed = provider_rate_limit_seed(name)
    byte_bounds = dict(rate_seed.get("_byte_reservation_bounds") or {})
    if byte_bounds:
        bandwidth_dimensions = [
            dimension
            for dimension in rate_seed
            .get("quota_contract", {})
            .get("dimensions", [])
            if isinstance(dimension, dict)
            and str(dimension.get("unit") or "").lower() in {"byte", "bytes"}
        ]
        if bandwidth_dimensions:
            dimension_name = str(bandwidth_dimensions[0]["name"])
            merged["mode"] = "multi_dimensional"
            merged["unit_label"] = "provider_units"
            merged["operation_costs"] = {
                **dict(merged.get("operation_costs") or {}),
                **{operation: 1 for operation in byte_bounds},
            }
            merged["dimension_costs"] = {
                **dict(merged.get("dimension_costs") or {}),
                dimension_name: byte_bounds,
            }
    if name == "finra":
        async_result_bound = provider_positive_integer(
            settings.FINRA_ASYNC_MAX_RESULT_BYTES
        )
        if async_result_bound is not None:
            bandwidth_dimension = "download_bytes_per_calendar_month"
            merged["operation_costs"] = {
                **dict(merged.get("operation_costs") or {}),
                "download_async_result": 1,
            }
            merged["dimension_costs"] = {
                **dict(merged.get("dimension_costs") or {}),
                # The signed result leg does not consume FINRA's API request
                # minute dimensions; its only provider budget is downloaded
                # bytes.  An operation-specific empty map is intentional and
                # is interpreted as "do not charge this dimension".
                "synchronous_requests_per_minute": {
                    "download_async_result": {},
                },
                bandwidth_dimension: {
                    **dict(
                        (merged.get("dimension_costs") or {}).get(bandwidth_dimension) or {}
                    ),
                    "download_async_result": async_result_bound,
                },
            }
    if name == "finra_otc_directory":
        operation_costs = getattr(settings, "FINRA_OTC_OPERATION_COSTS", {}) or {}
        if isinstance(operation_costs, dict):
            reviewed_costs = {
                str(operation).strip(): cost
                for operation, cost in operation_costs.items()
                if str(operation).strip()
                and provider_positive_integer(cost) is not None
            }
            if reviewed_costs:
                merged["operation_costs"] = {
                    **dict(merged.get("operation_costs") or {}),
                    **reviewed_costs,
                }
    if name == "marketdata_app":
        # Current option chains are billed per returned option symbol.  The
        # adapter applies this same reviewed bound as ``strikeLimit`` and
        # rejects a larger response, so the reservation cannot silently
        # under-account a bulk chain.  Keep the default absent: stock candles
        # remain usable while option-chain routing stays fail-closed until an
        # operator chooses a budget appropriate for the deployment.
        max_symbols = provider_positive_integer(
            getattr(settings, "MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS", 0)
        )
        if max_symbols is not None and max_symbols >= 2:
            merged["operation_costs"] = {
                **dict(merged.get("operation_costs") or {}),
                "fetch_option_chain": max_symbols,
            }
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
