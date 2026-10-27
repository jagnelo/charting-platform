import json
import os
from copy import deepcopy
from datetime import UTC, datetime
from typing import cast

from pydantic import Field, field_validator
from pydantic_core import PydanticUseDefault
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    SettingsConfigDict,
)

_SETTINGS_USE_CODE_DEFAULT = "__CODE_DEFAULT__"
FMP_PUBLIC_QUOTA_EVIDENCE = (
    "https://site.financialmodelingprep.com/developer/docs/pricing; "
    "https://site.financialmodelingprep.com/faqs"
)
DINARI_SANDBOX_MAX_SERVER_RETRIES = 2
DINARI_SANDBOX_OPERATION_HTTP_REQUESTS = {
    "discover_tokenized_assets": 1,
    "get_tokenized_asset": 1,
    "get_tokenized_price": 2,
    "get_tokenized_quote": 2,
    "fetch_tokenized_historical_prices": 2,
    "fetch_tokenized_news": 2,
    "fetch_tokenized_dividends": 2,
    "fetch_tokenized_splits": 2,
    # Symbol-scoped corporate actions resolve metadata and read both the
    # dividend and split feeds; the global split path is deliberately
    # over-reserved to this worst case.
    "fetch_tokenized_corporate_actions": 3,
}
DINARI_SANDBOX_OPERATION_MINIMUM_REQUEST_COSTS = {
    operation: request_count * (DINARI_SANDBOX_MAX_SERVER_RETRIES + 1)
    for operation, request_count in DINARI_SANDBOX_OPERATION_HTTP_REQUESTS.items()
}
_JSON_SEED_OVERRIDE_FIELDS = {
    "PROVIDER_RATE_LIMIT_SEEDS",
    "PROVIDER_FRESHNESS_SEEDS",
    "PROVIDER_USAGE_PROFILE_SEEDS",
    "PROVIDER_CHECKPOINT_OPERATION_HOLDS",
    "DINARI_SANDBOX_QUOTA_PROFILE",
    "TIINGO_OPERATION_BYTE_BOUNDS",
    "FMP_OPERATION_BYTE_BOUNDS",
}


class _CodeDefaultSentinelSourceMixin:
    """Let the Settings validator handle the non-JSON defaults sentinel."""

    def prepare_field_value(self, field_name, field, value, value_is_complex):
        if field_name in _JSON_SEED_OVERRIDE_FIELDS and value == _SETTINGS_USE_CODE_DEFAULT:
            return value
        return super().prepare_field_value(field_name, field, value, value_is_complex)


class _EnvironmentSettingsSource(_CodeDefaultSentinelSourceMixin, EnvSettingsSource):
    pass


class _DotEnvSettingsSource(_CodeDefaultSentinelSourceMixin, DotEnvSettingsSource):
    pass


class Settings(BaseSettings):
    # Application
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    E2E_SEED_INSTRUMENTS: bool = False
    E2E_SEED_MARKET_DATA: bool = False
    # Optional controlled dense-universe identities for the network-scale
    # workstation performance oracle. Disabled by default and never presented
    # as canonical provider data.
    E2E_SEED_LARGE_UNIVERSE: bool = False
    E2E_SEED_LARGE_UNIVERSE_COUNT: int = 10_000
    RESEARCH_JOB_DIR: str = "/tmp/charting-research/jobs"
    RESEARCH_RESULT_DIR: str = "/tmp/charting-research/results"

    # Security
    SECRET_KEY: str = "dev-secret-change-me-at-least-32-chars-long"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/chartingdb"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/chartingdb"
    STRATEGY_LAB_V2_MIGRATIONS_ENABLED: bool = False
    STRATEGY_LAB_V2_MIGRATION_TARGET: str = "head"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    # Optional cross-host OHLCV refresh coalescing. PostgreSQL advisory locks
    # remain the primary path when workers share one database. Enable this only
    # when a shared Redis coordinator is available and set the TTL above the
    # slowest permitted refresh; failed acquisition is fail-closed.
    OHLCV_DISTRIBUTED_LOCK_ENABLED: bool = False
    OHLCV_DISTRIBUTED_LOCK_TTL_SECONDS: int = 900
    OHLCV_DISTRIBUTED_LOCK_WAIT_SECONDS: float = 30.0
    OHLCV_DISTRIBUTED_LOCK_RETRY_SECONDS: float = 0.25

    # OneSignal
    ONESIGNAL_APP_ID: str = ""
    ONESIGNAL_REST_API_KEY: str = ""
    PROVIDER_AVAILABILITY_MONITOR_ENABLED: bool = False
    PROVIDER_AVAILABILITY_LIVE_ENABLED: bool = False
    PROVIDER_AVAILABILITY_NOTIFICATIONS_ENABLED: bool = True
    PROVIDER_AVAILABILITY_NOTIFICATION_COOLDOWN_SECONDS: int = 86400
    PROVIDER_AVAILABILITY_PROBE_TIMEOUT_SECONDS: float = 20.0

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:4173"]

    # Alert engine
    ALERT_POLL_INTERVAL: int = 60

    # Proxy
    PROXY_FILE: str = "proxies.txt"
    PROXY_ENABLED: bool = False

    # Provider-backed universe maintenance
    INSTRUMENT_SYNC_SCHEDULE_ENABLED: bool = False
    MARKET_DATA_REFRESH_SCHEDULE_ENABLED: bool = False
    # Number of durable core-refresh jobs claimed by each 15-minute worker
    # tick. The worker clamps this to the queue's safe 1..500 range so a
    # deployment can tune throughput without bypassing provider quotas.
    MARKET_DATA_REFRESH_QUEUE_BATCH_SIZE: int = 100
    MARKET_DATA_SHADOW_REPORT_ENABLED: bool = False
    MARKET_UNIVERSE_RECONCILIATION_ENABLED: bool = True
    # Provider-native account usage is opt-in because each poll consumes the
    # provider's own account quota. The provider list is explicit; an empty
    # list never means "all providers" and therefore cannot create surprise
    # external traffic when a deployment enables unrelated schedules.
    PROVIDER_ACCOUNT_USAGE_REFRESH_ENABLED: bool = False
    PROVIDER_ACCOUNT_USAGE_REFRESH_PROVIDERS: list[str] = []
    MARKET_UNIVERSE_MISSING_CONFIRMATIONS: int = 3
    # Forward market-event ingestion is opt-in. The worker persists a bounded
    # window from every eligible market_events provider; provider routing and
    # quotas remain the final authority for whether a source is called.
    MARKET_EVENTS_REFRESH_ENABLED: bool = False
    MARKET_EVENTS_REFRESH_LOOKAHEAD_DAYS: int = 90
    MARKET_EVENTS_REFRESH_MAX_PROVIDERS: int = 8
    MARKET_EVENTS_PRELISTING_ENABLED: bool = False
    MARKET_EVENTS_PRELISTING_LOOKAHEAD_DAYS: int = 90
    MARKET_EVENTS_PRELISTING_MAX_EVENTS: int = 500
    MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_ENABLED: bool = False
    MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_LOOKBACK_DAYS: int = 365
    MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_MAX_ISSUERS: int = 50
    MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_MAX_EVENTS_PER_ISSUER: int = 100
    # The SEC directory-backed IPO scan is a separate, more complete source
    # path. It is disabled independently so deployments can choose whether
    # to spend submissions requests on every SEC issuer rather than only
    # issuers already materialized in the canonical table.
    MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ENABLED: bool = False
    MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_ISSUERS: int = 50
    MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_EVENTS_PER_ISSUER: int = 100
    # One SEC submissions request is attempted per CIK and worker invocation.
    # This is a per-invocation ceiling, not an SEC daily allowance. A positive
    # reviewed value is required before enabling fan-out; zero fails closed.
    MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_SUBMISSIONS_REQUESTS: int = 0
    # Issuer rows are never created by the directory scan unless this explicit
    # policy is selected. ``create_missing`` creates only CIK/name issuer rows;
    # it never creates instruments/listings or mutates existing legal names.
    MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ISSUER_MATERIALIZATION_MODE: str = "disabled"
    # Must be set to the exact cycle number of the latest complete, clean,
    # disabled-mode review after an operator inspects its candidate report.
    MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_REVIEWED_CYCLE_COUNT: int = 0
    # Tokenized catalogue discovery is separate from quote polling so a
    # deployment can budget metadata requests independently. It is disabled
    # until provider quotas/terms are reviewed and bounded values are set.
    TOKENIZED_CATALOG_REFRESH_ENABLED: bool = False
    TOKENIZED_CATALOG_REFRESH_MAX_PAGES: int = 1
    TOKENIZED_CATALOG_REFRESH_PAGE_SIZE: int = 100
    # Historical tokenized candles are a separate, provider-specific budget
    # from catalog and quote polling. Keep the Dinari/Ondo aggregate-history
    # paths disabled until their account/terms contracts are reviewed.
    TOKENIZED_HISTORICAL_REFRESH_ENABLED: bool = False
    TOKENIZED_HISTORICAL_REFRESH_MAX_ASSETS: int = 100
    TOKENIZED_HISTORICAL_REFRESH_TIMESPAN: str = "DAY"
    TOKENIZED_ASSET_REFRESH_ENABLED: bool = False
    TOKENIZED_ASSET_REFRESH_MAX_ASSETS: int = 100
    TOKENIZED_EVENT_REFRESH_ENABLED: bool = False
    TOKENIZED_EVENT_REFRESH_MAX_PROVIDERS: int = 2
    TOKENIZED_EVENT_REFRESH_MAX_PAGES: int = 1
    TOKENIZED_EVENT_REFRESH_PAGE_SIZE: int = 100
    ETF_HOLDINGS_REFRESH_ENABLED: bool = False
    ETF_HOLDINGS_CAPABILITY_CANARY_ENABLED: bool = False
    ETF_HOLDINGS_CAPABILITY_CANARY_SYMBOLS: str = (
        "DXJ,NTSX,MINT,BOND,GEME,TBIL,XBIL,OBIL,UTWO,UTRE,UFIV,USVN,UTEN,UTWY,UTHY"
    )
    ETF_HOLDINGS_CAPABILITY_CANARY_MAX_SYMBOLS: int = 20
    ETF_HOLDINGS_CAPABILITY_CANARY_TIMEOUT_SECONDS: float = 60.0
    ETF_HOLDINGS_CAPABILITY_CANARY_FAILURE_THRESHOLD: int = 3
    ETF_HOLDINGS_CAPABILITY_CANARY_COOLDOWN_SECONDS: int = 3600
    ETF_HOLDINGS_CLASSIFICATION_REFRESH_ENABLED: bool = False
    ETF_HOLDINGS_CLASSIFICATION_MAX_PROFILES: int = 50
    ETF_HOLDINGS_CLASSIFICATION_MAX_ENRICHMENTS_PER_PROFILE: int = 32
    ETF_HOLDINGS_SEC_BACKFILL_ENABLED: bool = False
    # Bounded dated family maintenance is opt-in. It refreshes completed
    # month-end candidates through the existing provider adapters and queues
    # canonical member history; interactive source reads never fan out.
    BENCHMARK_FAMILY_HOLDINGS_REFRESH_ENABLED: bool = False
    BENCHMARK_FAMILY_HOLDINGS_REFRESH_LOOKBACK_DATES: int = 1
    # A fresh deployment should hydrate the small immutable workstation
    # universe through the normal canonical provider services.  The worker
    # performs this asynchronously; API startup remains non-blocking.
    # Identity bootstrap runs during API startup; provider-backed history and
    # holdings hydration is an explicit maintenance operation. Keeping the
    # latter opt-in prevents a cold provider sweep from competing with the
    # authenticated workstation's first-load request budget.
    CORE_WORKSTATION_BOOTSTRAP_ENABLED: bool = False
    CORE_WORKSTATION_BOOTSTRAP_TIMEOUT_SECONDS: float = 45.0
    CORE_WORKSTATION_BOOTSTRAP_LOOKBACK_DAYS: int = 730
    ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS: float = 20.0
    ETF_HOLDINGS_HTTP_USER_AGENT: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    )
    ETF_HOLDINGS_SEC_BACKFILL_MAX_PROFILES: int = 50
    ETF_HOLDINGS_SEC_BACKFILL_MAX_FILINGS_PER_ETF: int = 20
    # Free-source-first defaults for the new workstation.  yfinance is not a
    # normal read path; it remains available only when explicitly selected as
    # a legacy/options fallback in deployment configuration.
    DEFAULT_MARKET_DATA_PROVIDER: str = "alpaca"
    DEFAULT_METADATA_PROVIDER: str = "edgar"
    DEFAULT_EVENT_PROVIDER: str = "alpaca"
    DEFAULT_DISCOVERY_PROVIDER: str = "alpaca"
    # MarketData.app is the API-first options candidate. Its account-plan and
    # response-priced-chain controls keep it fail-closed until reviewed;
    # yfinance remains available only through explicit legacy configuration.
    DEFAULT_OPTIONS_PROVIDER: str = "marketdata_app"
    # yfinance remains available for explicitly enabled legacy/options flows,
    # but must not be appended automatically to new workstation capability
    # chains. This keeps the default platform path free-source/API-first.
    ENABLE_LEGACY_YFINANCE_FALLBACK: bool = False
    # Shared integration-checkpoint boundary: provider calls are restricted to
    # reviewed, non-trial free plans even if the full-roadmap paid-routing
    # switch is enabled. Set false only when intentionally leaving the
    # checkpoint mode; paid plans still require ALLOW_PAID_PROVIDER_ROUTING.
    PROVIDER_FREE_ONLY_CHECKPOINT: bool = True
    # Operation-level checkpoint exclusions are independent from provider
    # entitlement and quota math. They keep an operation non-routable when the
    # accepted checkpoint has no exact-source live evidence for it, even if a
    # smaller request could fit the provider's current quota. Reasons are
    # operator-visible; ``*`` holds every operation for that provider. An
    # environment may replace this complete map after the corresponding
    # operations have been reviewed and validated.
    PROVIDER_CHECKPOINT_OPERATION_HOLDS: dict[str, dict[str, str]] = {
        "alpha_vantage": {
            "*": "Alpha Vantage daily headroom is below the reviewed checkpoint manifest reservation",
        },
        "cta_plan": {
            "*": "complete daily CTA directory read is quota-held and unavailable in this checkpoint",
        },
        "eodhd": {
            "fetch_ohlcv": "ordinary EODHD history is not live-verified for this checkpoint",
            "fetch_latest_ohlcv": "ordinary EODHD history is not live-verified for this checkpoint",
            "get_current_price": "ordinary EODHD quote data is not live-verified for this checkpoint",
            "get_instrument_profile": "EODHD Free does not entitle Fundamentals/profile data",
            "discover_universe_page": "ordinary EODHD discovery is not live-verified for this checkpoint",
        },
        "marketstack": {
            "*": "Marketstack operation cost or monthly headroom is unresolved for this checkpoint",
        },
        "nasdaq": {
            "*": "Nasdaq directory daily headroom is exhausted for this checkpoint",
        },
        "tiingo": {
            "*": "Tiingo plan or active hourly/daily usage baseline is unresolved for this checkpoint",
        },
        "dinari": {
            "*": "Dinari Sandbox quota resets and operation costs are unreviewed; canary-only data is excluded from normal routing",
        },
        "bybit_xstocks": {
            "*": "Bybit deployment-egress eligibility is unresolved for this checkpoint",
        },
    }
    # A reviewed paid entitlement participates only when explicitly enabled.
    # This opt-in is not an aggregate recurring-subscription cost budget; paid
    # activation still requires separate authorization and cost governance.
    ALLOW_PAID_PROVIDER_ROUTING: bool = False
    # Deployment-wide emergency switch. Provider descriptors and usage remain
    # visible when off, but no provider adapter may be selected for a call.
    PROVIDER_ROUTING_ENABLED: bool = True
    # When enabled, provider transport is possible only inside a server-owned
    # explicit acquisition context. This is independent from the global
    # emergency routing switch and never bypasses per-capability admission.
    PROVIDER_REQUEST_DRIVEN_ONLY: bool = False
    # Application workload ceilings for one explicit history request. The
    # response cap matches the existing bounded 2,000-row API pattern; limiting
    # repair work to eight missing slices prevents one click from fanning into
    # an unbounded request loop. These are not provider quota/entitlement claims;
    # native admission remains authoritative for every physical operation.
    PROVIDER_ON_DEMAND_MAX_REQUESTED_BARS: int = Field(default=2000, ge=1, le=2000)
    PROVIDER_ON_DEMAND_MAX_MISSING_SLICES: int = Field(default=8, ge=0, le=8)
    IDENTIFIER_PROVIDER_PRIORITY: list[str] = ["openfigi"]
    OPTION_QUOTE_HISTORY_PROVIDER_PRIORITY: list[str] = []
    TOKENIZED_PROVIDER_PRIORITY: list[str] = [
        "robinhood_tokens",
        "xstocks",
        "bybit_xstocks",
        "gate_tradfi",
        "kraken_xstocks",
        "dinari",
        "ondo_global_markets",
    ]
    PROVIDER_CHAIN_SEEDS: dict[str, list[str]] = {
        # No issuer is routable by default. ETF publishers are added only
        # after source/account/terms/quota evidence has been reviewed and a
        # concrete per-operation policy has been configured.
        "etf_holdings": [],
        # Provider-native usage surfaces are selected by the same exact
        # capability/quota gates as data reads. These adapters remain opt-in
        # at the worker level; this list only makes them resolvable when an
        # operator explicitly requests a snapshot.
        "account_usage": [
            "marketdata_app",
            "twelve_data",
            "eodhd",
            "binance",
            "alpaca",
            "openfigi",
            "coingecko",
            "marketstack",
        ],
        # Alpaca exposes an assets/discovery endpoint but no instrument-search
        # operation. Keep it out of this chain; stale policies from older
        # configurations are filtered by provider capability at runtime too.
        "instrument_search": ["edgar", "massive", "alpha_vantage"],
        # SEC remains the default issuer/profile source; Massive's ticker
        # overview is the preferred supplementary metadata route with stable
        # FIGI/CIK and listing lifecycle fields. Alpaca is last because its
        # authenticated asset object is provider-native listing metadata and
        # does not itself establish a cross-provider identity.
        "instrument_metadata": ["edgar", "massive", "alpaca"],
        "price_history": ["alpaca", "alpha_vantage"],
        "latest_price": ["alpaca", "alpha_vantage"],
        # Alpha Vantage's EARNINGS endpoint is a final corroborating fallback;
        # its free key is deliberately last because the allowance is only
        # 25 requests/day and the earlier providers cover richer US event
        # semantics when their reviewed entitlements are available.
        "instrument_events": ["alpaca", "massive", "edgar", "finnhub", "alpha_vantage"],
        # SEC adds official US issuer/ticker/exchange evidence across venues;
        # CTA covers Tape A/B, Nasdaq Trader is an independent cross-check, and
        # the explicitly
        # configured FINRA directory is the fail-closed OTC counterpart. The
        # latter has no inferred quota and therefore remains non-routable until
        # its source, terms, and quota contract are operator-approved.
        "universe_discovery": [
            "alpaca",
            "edgar",
            "massive",
            "nasdaq",
            "cta_plan",
            "finra_otc_directory",
            "alpha_vantage",
        ],
        "tokenized_assets": [
            "robinhood_tokens",
            "xstocks",
            "bybit_xstocks",
            "gate_tradfi",
            "kraken_xstocks",
            "dinari",
            "ondo_global_markets",
        ],
        # Historical tokenized aggregates are a distinct quota/terms surface
        # from catalogue and indicative-quote traffic. Dinari exposes native
        # windows; Ondo exposes documented daily OHLC and deterministic local
        # rollups. Their unknown partner/onboarding contracts keep this chain
        # fail-closed until operations approve each entitlement.
        "tokenized_historical_prices": ["dinari", "ondo_global_markets"],
        # Dinari exposes global splits and per-stock dividends/splits. Keep it
        # in the capability chain so reviewed quota/terms can admit it later;
        # its currently unknown partner quota still makes runtime resolution
        # fail closed.
        "tokenized_corporate_actions": ["robinhood_tokens", "xstocks", "dinari"],
    }
    # Provider-specific, documentation-backed budgets.  An omitted provider
    # (or omitted dimension) is intentionally unknown and therefore not
    # routable.  Never add a generic fallback here: several vendors publish
    # endpoint-, key-, IP-, or plan-specific limits.
    # These optional JSON overrides use a non-JSON sentinel to select the
    # reviewed code defaults. The custom Settings sources pass only that exact
    # sentinel through to the before-validator; explicit JSON still decodes.
    PROVIDER_RATE_LIMIT_SEEDS: dict[str, dict] = {
        "alpaca": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "market_data_requests_per_minute",
                        "limit": 200,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "account",
                        "quota_group": "account",
                        # Alpaca returns reset as integer Unix seconds. A
                        # response can cross that second while transport is
                        # in flight; accept at most two seconds of that
                        # provider-specific precision/transport skew when
                        # seeding the rolling safety baseline.
                        "native_reset_skew_seconds": 2,
                        "source": "https://docs.alpaca.markets/us/v1.1/docs/about-market-data-api",
                    },
                    {
                        "name": "account_usage_probe_concurrency",
                        "limit": 1,
                        "window_seconds": 1,
                        "unit": "concurrent_requests",
                        "scope": "deployment",
                        "quota_group": "account_usage_probe",
                        "source": "application_policy:provider_native_baseline_bootstrap",
                        "reset": "rolling",
                        "applies_to_operations": ["fetch_account_usage"],
                    },
                ],
                # Alpaca documents a 200-requests/minute pool and exposes a
                # native reset epoch for the next quota change, but does not
                # publish a fixed calendar-minute boundary. Use the
                # conservative rolling 60-second envelope for durable
                # admission; native limit/remaining/reset headers establish
                # the active account baseline and remain authoritative
                # telemetry. This is an application safety envelope, not a
                # claim that Alpaca uses a rolling window internally.
                "reset": "rolling",
                "account_usage_bootstrap": {
                    "enabled": True,
                    "source": "application_policy:provider_native_baseline_bootstrap",
                    "reconciled_dimensions": [
                        "market_data_requests_per_minute",
                    ],
                },
            },
            "tokens_per_minute": 200,
            "quota_scope": "account",
            "quota_source": "Alpaca market data API documentation",
        },
        "massive": {
            # Massive's public rate-limit guidance tells clients to wait after
            # 429 but gives no reset instant. If a response has no usable
            # Retry-After/reset header, hold this provider for one complete
            # documented minute. This is client recovery behavior, not a
            # claim about Massive's reset rule.
            "cooldown_seconds": 60,
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "requests_per_minute",
                        "limit": 5,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "account",
                        "quota_group": "stocks",
                        # Massive's current Basic-plan FAQ says the 5/minute
                        # allowance applies per asset class and that reference
                        # data and corporate actions work on Basic. These
                        # adapter operations are all in the Stocks asset class
                        # and share this same account bucket.
                        "applies_to_operations": [
                            "search_instruments",
                            "discover_universe_page",
                            "reconcile_universe_page",
                            "get_instrument_profile",
                            "fetch_ohlcv",
                            "fetch_latest_ohlcv",
                            "fetch_instrument_events",
                            "fetch_market_events",
                            "fetch_market_events_page",
                            "fetch_market_holidays",
                        ],
                        "source": "https://massive.com/knowledge-base/article/how-quickly-can-i-access-massives-market-date",
                        # The documented quota is independent per asset-class
                        # subscription and shared across keys on the account.
                        # Its minute boundary remains unspecified, so enforce
                        # a rolling client-side safety window without
                        # claiming that Massive itself uses one.
                        "safety_reset": "rolling",
                        # Massive does not expose a current-use endpoint.
                        # Every request made by this platform is coordinated
                        # through the host-private ledger shared by managed
                        # local worktrees; record app-observed use only rather
                        # than inventing an account-wide provider counter.
                        "baseline_mode": "local_zero",
                        "application_usage_only": True,
                    },
                ],
                # The exact limit is known (5 requests per minute per asset
                # class); Massive does not publish the provider-side minute
                # reset instant or a current-use endpoint. The client enforces
                # a rolling 60-second envelope and reconciles all local calls
                # in the durable shared ledger.
                "reset": "provider_defined",
                "unknown_dimensions": ["requests_per_minute_reset_boundary"],
            },
            "tokens_per_minute": 5,
            "quota_scope": "account",
            "quota_source": (
                "Massive Stocks Basic: 5 REST requests/minute per asset-class account bucket"
            ),
        },
        "alpha_vantage": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "requests_per_second",
                        "limit": 1,
                        "window_seconds": 1,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "Alpha Vantage current-key live rate-limit response (2026-10-06)",
                        "reset": "provider_defined",
                        # The provider response recommends one request per
                        # second; keep a strict rolling one-second envelope.
                        "safety_reset": "rolling",
                        # The shared owner-only coordinator tracks this
                        # platform's key-scoped usage across worktrees and
                        # workers. Alpha Vantage exposes no live short-window
                        # counter; this initializes only application usage,
                        # not provider-reported total usage. The separately
                        # enforced daily pool below uses the same durable
                        # application ledger with its own rolling window.
                        "baseline_mode": "local_zero",
                        "application_usage_only": True,
                    },
                    {
                        "name": "requests_per_minute",
                        "limit": 5,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "Alpha Vantage current-key live capacity response (2026-10-06; owner-private evidence)",
                        "reset": "provider_defined",
                        # The current key's provider response indicated this
                        # per-minute ceiling; the current public support page
                        # confirms 25/day but does not publish a minute cap.
                        # Preserve this key-specific observed cap and enforce
                        # a rolling safety window without claiming a vendor
                        # bucket boundary.
                        "safety_reset": "rolling",
                        "baseline_mode": "local_zero",
                        "application_usage_only": True,
                    },
                    {
                        "name": "requests_per_day",
                        "limit": 25,
                        "window_seconds": 86400,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://www.alphavantage.co/support/",
                        # The 25/day allowance is exact; the reset anchor is
                        # not published.  A rolling 24-hour envelope is a
                        # conservative application policy, not a vendor claim.
                        "safety_reset": "rolling",
                        # This account's platform usage is persisted by the
                        # shared quota coordinator across local worktrees and
                        # sessions. Count from that durable application ledger
                        # rather than requiring a provider usage endpoint that
                        # Alpha Vantage does not expose.
                        "baseline_mode": "local_zero",
                        "application_usage_only": True,
                    },
                ],
                # Alpha Vantage's public support page publishes the daily
                # ceiling; the current key's live response supplies the
                # observed minute ceiling and recommends 1/sec pacing. None
                # of the response sources publishes reset anchors.
                # Use explicit rolling safety windows without claiming the
                # vendor's native reset model.
                "reset": "provider_defined",
                "unknown_dimensions": [
                    "requests_per_second_reset_boundary",
                    "requests_per_minute_reset_boundary",
                    "requests_per_day_reset_boundary",
                ],
            },
            "quota_scope": "api_key",
            "quota_source": "Alpha Vantage official support page for 25/day plus current-key live capacity response for minute ceiling and pacing (2026-10-06)",
        },
        "nasdaq": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "directory_requests_per_market_day",
                        "limit": 2,
                        "window_seconds": 86400,
                        "unit": "requests",
                        "scope": "deployment",
                        "quota_group": "nasdaq_symbol_directory",
                        "source": "application_policy:one conditional request per official directory file per market day",
                        "reset": "calendar_day_est",
                        # This is a client-imposed deployment ceiling, not a
                        # vendor allowance. The first local window may be
                        # initialized explicitly at zero because no external
                        # account can have spent this application-owned pool.
                        "baseline_mode": "local_zero",
                        "application_usage_only": True,
                    }
                ],
                "reset": "calendar_day_est",
            },
            "quota_scope": "deployment",
            "quota_source": "client-imposed one-refresh-per-market-day ceiling; Nasdaq does not publish a numeric quota",
        },
        "cta_plan": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "local_directory_requests_per_market_day",
                        "limit": 2,
                        "window_seconds": 86400,
                        "unit": "requests",
                        "scope": "deployment",
                        "quota_group": "cta_plan_symbol_directory",
                        "source": "application_policy:one public index request plus one dated symbol-file request per market day",
                        "reset": "calendar_day_est",
                        "baseline_mode": "local_zero",
                        "application_usage_only": True,
                    }
                ],
                "reset": "calendar_day_est",
            },
            "quota_scope": "deployment",
            "quota_source": "local two-request daily ceiling for index plus symbol file; CTA publishes no numeric HTTP quota",
        },
        "openfigi": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "mapping_requests_per_minute",
                        "limit": 25,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "ip_or_api_key",
                        "quota_group": "ip_or_api_key",
                        "source": "https://www.openfigi.com/api/documentation",
                    },
                    {
                        "name": "account_usage_probe_concurrency",
                        "limit": 1,
                        "window_seconds": 1,
                        "unit": "concurrent_requests",
                        "scope": "deployment",
                        "quota_group": "account_usage_probe",
                        "source": "application_policy:provider_native_baseline_bootstrap",
                        "reset": "rolling",
                        "applies_to_operations": ["fetch_account_usage"],
                    },
                ],
                "reset": "rolling",
                "account_usage_bootstrap": {
                    "enabled": True,
                    "source": "application_policy:provider_native_baseline_bootstrap",
                    "reconciled_dimensions": [
                        "mapping_requests_per_minute",
                    ],
                },
                "endpoint_constraints": {
                    "mapping": {
                        "max_jobs_per_request": 5,
                        "source": "https://www.openfigi.com/api/documentation",
                    }
                },
            },
            "tokens_per_minute": 25,
            "quota_scope": "ip_or_api_key",
            "quota_source": "OpenFIGI API documentation",
        },
        "edgar": {
            # SEC's public security policy says access may be limited after
            # exceeding the aggregate request ceiling and may resume only
            # after the rate remains below the threshold for ten minutes.
            # This is provider-specific recovery behavior, not a generic
            # cooldown fallback.
            "cooldown_seconds": 600,
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "requests_per_second",
                        "limit": 10,
                        "window_seconds": 1,
                        "unit": "requests",
                        "scope": "ip",
                        "quota_group": "ip",
                        "source": "https://www.sec.gov/about/privacy-information",
                        # SEC says access resumes below the threshold but does
                        # not publish a bucket boundary.  Enforce a strict
                        # rolling one-second application envelope.
                        "safety_reset": "rolling",
                        # SEC exposes a hard IP-level rate ceiling, not an
                        # account-usage counter. Every EDGAR request issued by
                        # this platform is serialized and persisted in the
                        # shared coordinator, so initialize this application's
                        # measured IP-rate window at zero rather than blocking
                        # forever on a nonexistent native counter. This is the
                        # platform's tracked usage, not SEC-reported headroom.
                        "baseline_mode": "local_zero",
                        "application_usage_only": True,
                    }
                ],
                # SEC publishes the 10-requests/second ceiling but does not
                # define whether the enforcement window is fixed or rolling.
                # Keep the provider-defined label auditable while the
                # dimension's explicit rolling safety envelope controls
                # admission.
                "reset": "provider_defined",
                "unknown_dimensions": ["requests_per_second_reset_boundary"],
            },
            "quota_scope": "ip",
            "quota_source": "SEC fair-access policy",
        },
        "fred": {
            "quota_contract": {
                # FRED v1 documents a 120-requests/minute threshold before HTTP 429,
                # but does not publish its enforcement scope. FRED v2's separate
                # 2-requests/second rule must not be applied to this v1 adapter.
                "dimensions": [
                    {
                        "name": "requests_per_minute",
                        "limit": 120,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "provider_defined",
                        "source": "https://fred.stlouisfed.org/docs/api/fred/errors.html",
                        "reset": "provider_defined",
                        # FRED does not expose a current calls/minute
                        # counter. Initialize only this application's durable
                        # usage window; deployments sharing the same key must
                        # share the quota coordinator or reconcile external
                        # calls before use.
                        "baseline_mode": "local_zero",
                        "application_usage_only": True,
                    }
                ],
                "unknown_dimensions": [
                    "v1_enforcement_scope",
                    "provider_adjustable_limits",
                    "series_terms_and_redistribution",
                    "requests_per_minute_reset_boundary",
                ],
                # FRED publishes a threshold before HTTP 429 but does not
                # establish the reset boundary. Keep it provider-defined
                # until current provider/account evidence is reviewed.
                "reset": "provider_defined",
                "source": "https://fred.stlouisfed.org/docs/api/fred/errors.html",
            },
            "quota_scope": "provider_defined",
            "quota_source": "FRED v1 errors and API terms",
        },
        "finra": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "synchronous_requests_per_minute",
                        "limit": 1200,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "ip",
                        "quota_group": "ip",
                        "source": "https://developer.finra.org/docs",
                        "reset": "rolling",
                    },
                    {
                        "name": "asynchronous_requests_per_minute_dataset",
                        "limit": 20,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "api_account_and_dataset",
                        "quota_group": "api_account_and_dataset",
                        "source": "https://developer.finra.org/node/1146",
                        "reset": "rolling",
                    },
                    {
                        "name": "download_bytes_per_calendar_month",
                        # FINRA publishes "10 GB" and says public keys stay
                        # disabled until the first day of the following month
                        # if exhausted, but does not state the reset timezone
                        # or byte convention. Keep the decimal magnitude
                        # explicit; retain the provider-defined label for audit
                        # while enforcing a conservative provider-scoped
                        # rolling 31-day safety envelope.
                        "limit": 10_000_000_000,
                        "window_seconds": 2678400,
                        "unit": "bytes",
                        "scope": "public_credential",
                        "quota_group": "public_credential",
                        "source": "https://developer.finra.org/support",
                        "reset": "provider_defined",
                        "safety_reset": "rolling_31_days",
                        "safety_resolves_unknown_dimensions": [
                            "download_bytes_per_calendar_month_reset_boundary"
                        ],
                        "limit_basis": "decimal_bytes_conservative_for_published_GB",
                    },
                ],
                "reset": "provider_defined",
                "unknown_dimensions": ["download_bytes_per_calendar_month_reset_boundary"],
                "dimension_costs_required": True,
                # FINRA publishes a decimal 3 MB maximum but does not specify
                # the byte convention. Reserve 3,000,000 bytes to stay below
                # both decimal and binary interpretations.
                "maximum_synchronous_response_bytes": 3_000_000,
            },
            "tokens_per_minute": 1200,
            "quota_scope": "ip",
            "quota_source": "FINRA API Platform usage limits",
        },
        "finra_otc_directory": {
            "quota_contract": {
                # The OTC Symbol Directory uses FINRA's synchronous Query API.
                # Each logical page makes at most one partition read plus one
                # 5,000-row data read; subsequent pages reuse the partition.
                "dimensions": [
                    {
                        "name": "synchronous_requests_per_minute",
                        "limit": 1200,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "ip",
                        "quota_group": "ip",
                        "source": "https://developer.finra.org/node/1146",
                        "reset": "rolling",
                    },
                    {
                        "name": "download_bytes_per_calendar_month",
                        "limit": 10_000_000_000,
                        "window_seconds": 2678400,
                        "unit": "bytes",
                        "scope": "public_credential",
                        "quota_group": "public_credential",
                        "source": "https://developer.finra.org/support",
                        "reset": "provider_defined",
                        "safety_reset": "rolling_31_days",
                        "safety_resolves_unknown_dimensions": [
                            "download_bytes_per_calendar_month_reset_boundary"
                        ],
                        "limit_basis": "decimal_bytes_conservative_for_published_GB",
                    },
                ],
                "unknown_dimensions": ["download_bytes_per_calendar_month_reset_boundary"],
                "reset": "provider_defined",
                "dimension_costs_required": True,
                "maximum_synchronous_response_bytes": 3_000_000,
                "source": "https://developer.finra.org/node/1146",
            },
            "tokens_per_minute": 1200,
            "quota_scope": "ip",
            "quota_source": "FINRA synchronous Query API platform limits",
        },
        "coingecko": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "calls_per_minute",
                        "limit": 100,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "demo_api_key",
                        "quota_group": "demo_api_key",
                        "source": "https://www.coingecko.com/en/api/pricing",
                        # CoinGecko specifies calls per minute without
                        # publishing fixed-versus-rolling window mechanics.
                        # A rolling 60-second app envelope is strictly
                        # conservative and handles either boundary safely.
                        "reset": "provider_defined",
                        "safety_reset": "rolling",
                        # /key reports the limit but not active minute use.
                        # Persist only this application's measured requests;
                        # it is not a provider-wide remaining counter.
                        "baseline_mode": "local_zero",
                        "application_usage_only": True,
                    },
                    {
                        "name": "account_usage_probe_concurrency",
                        "limit": 1,
                        "window_seconds": 1,
                        "unit": "concurrent_requests",
                        "scope": "deployment",
                        "quota_group": "account_usage_probe",
                        "source": "application_policy:provider_native_baseline_bootstrap",
                        "reset": "rolling",
                        "applies_to_operations": ["fetch_account_usage"],
                    },
                    {
                        "name": "calls_per_month",
                        "limit": 10000,
                        "window_seconds": 2678400,
                        # Demo-plan pricing defines one monthly credit per
                        # successful API request. The provider documents /key
                        # as its account-usage endpoint; the adapter validates
                        # the exact monthly counters before baseline seeding.
                        "unit": "credits",
                        "scope": "demo_api_key",
                        "quota_group": "demo_api_key",
                        "source": "https://www.coingecko.com/en/api/pricing",
                        # Demo `/key` usage introspection is Pro-only. The
                        # free Demo key's successful monthly requests are
                        # counted by this application's durable coordinator.
                        "baseline_mode": "local_zero",
                        "application_usage_only": True,
                        # CoinGecko explicitly documents that monthly call
                        # credits reset on the first day of each month,
                        # regardless of subscription/billing date.
                        "reset": "calendar_month_utc",
                    },
                ],
                "reset": "per_dimension",
                "unknown_dimensions": ["calls_per_minute_reset_boundary"],
                "account_usage_bootstrap": {
                    "enabled": True,
                    "source": "https://docs.coingecko.com/reference/api-usage",
                    "reconciled_dimensions": ["calls_per_month"],
                    "allowed_unknown_dimensions": ["calls_per_minute_reset_boundary"],
                },
            },
            "tokens_per_minute": 100,
            "quota_scope": "demo_api_key",
            "quota_source": "CoinGecko Demo plan documentation",
        },
        "binance": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "request_weight_per_minute",
                        "limit": 6000,
                        "window_seconds": 60,
                        "unit": "weight",
                        "scope": "ip",
                        "quota_group": "ip",
                        "source": "https://developers.binance.com/en/docs/products/spot/rest-api",
                        "reset": "fixed_minute",
                    },
                    {
                        "name": "account_usage_probe_concurrency",
                        "limit": 1,
                        "window_seconds": 1,
                        "unit": "concurrent_requests",
                        "scope": "deployment",
                        "quota_group": "account_usage_probe",
                        "source": "application_policy:provider_native_baseline_bootstrap",
                        "reset": "rolling",
                        "applies_to_operations": ["fetch_account_usage"],
                    },
                ],
                "reset": "per_dimension",
                "dynamic_endpoint_weights": True,
                "account_usage_bootstrap": {
                    "enabled": True,
                    "source": "application_policy:provider_native_baseline_bootstrap",
                    "reconciled_dimensions": [
                        "request_weight_per_minute",
                    ],
                },
            },
            "tokens_per_minute": 6000,
            "quota_scope": "ip",
            "quota_source": "Binance Spot REST API documentation",
        },
        "coinbase": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "public_requests_per_second",
                        "limit": 10,
                        "window_seconds": 1,
                        "unit": "requests",
                        "scope": "ip",
                        "quota_group": "ip",
                        "source": "https://docs.cdp.coinbase.com/exchange/rest-api/rate-limits",
                        # Coinbase reports its static IP-scoped token-bucket
                        # ceiling but does not expose current bucket use. The
                        # durable coordinator tracks every request made by
                        # this application across its worktrees and processes;
                        # this zero is explicitly application usage only, not
                        # a claim about unrelated traffic sharing the IP.
                        "baseline_mode": "local_zero",
                        "application_usage_only": True,
                    }
                ],
                "reset": "rolling",
            },
            # Coinbase documents a lazy-fill public token bucket: 10 requests
            # per second with a burst capacity of 15. Keep the local bucket
            # aligned with that provider-native burst instead of leaving a
            # process-local limiter unspecified.
            "tokens_per_minute": 600,
            "burst_capacity": 15,
            "quota_scope": "ip",
            "quota_source": "Coinbase Exchange REST rate-limit documentation",
        },
        "kraken": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "public_requests_per_second",
                        "limit": 1,
                        "window_seconds": 1,
                        "unit": "requests",
                        "scope": "ip",
                        "quota_group": "ip",
                        "source": "https://support.kraken.com/articles/206548367-what-are-the-api-rate-limits-",
                        "limit_basis": "provider_recommended_safe_frequency",
                        # Kraken publishes a safe public-call frequency but
                        # no usage counter. The durable quota coordinator
                        # tracks this application's calls only; this is not a
                        # claim that unrelated callers sharing the egress IP
                        # have consumed zero capacity.
                        "baseline_mode": "local_zero",
                        "application_usage_only": True,
                    }
                ],
                "reset": "rolling",
            },
            "quota_scope": "ip",
            "quota_source": "Kraken REST rate-limit documentation",
        },
        "xstocks": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "public_requests_per_minute",
                        "limit": 1000,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "public_api",
                        "quota_group": "public_api",
                        "source": "https://docs.xstocks.fi/apis/openapi",
                        "evidence": "The public assets and corporate-actions endpoints returned the same X-RateLimit-Limit/Remaining/Reset window (limit 1000) during bounded live validation on 2026-09-14.",
                        "verified_at": "2026-09-14",
                    },
                    {
                        "name": "account_usage_probe_concurrency",
                        "limit": 1,
                        "window_seconds": 1,
                        "unit": "concurrent_requests",
                        "scope": "deployment",
                        "quota_group": "account_usage_probe",
                        "source": "application_policy:provider_native_baseline_bootstrap",
                        "reset": "rolling",
                        "applies_to_operations": ["fetch_account_usage"],
                    },
                ],
                "reset": "rolling",
                "account_usage_bootstrap": {
                    "enabled": True,
                    "source": "application_policy:provider_native_baseline_bootstrap",
                    "reconciled_dimensions": ["public_requests_per_minute"],
                },
            },
            "quota_scope": "public_api",
            "quota_source": "xStocks public API response headers, cross-checked against the public API reference",
        },
        "robinhood_tokens": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "public_requests_per_second",
                        "limit": 60,
                        "window_seconds": 1,
                        "unit": "requests",
                        "scope": "ip",
                        "quota_group": "ip",
                        "source": "https://docs.robinhood.com/chain/stock-token-apis/",
                        # Robinhood publishes a per-IP ceiling but no current
                        # usage counter. Persist only calls made through this
                        # platform's shared coordinator; do not claim the
                        # baseline represents unrelated traffic on the IP.
                        "baseline_mode": "local_zero",
                        "application_usage_only": True,
                    }
                ],
                "reset": "rolling",
            },
            "quota_scope": "ip",
            "quota_source": "Robinhood Chain Stock Token API documentation",
        },
        "bybit_xstocks": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "http_requests_per_five_seconds",
                        "limit": 600,
                        "window_seconds": 5,
                        "unit": "requests",
                        "scope": "ip",
                        "quota_group": "ip",
                        "source": "https://bybit-exchange.github.io/docs/v5/rate-limit",
                        # The adapter uses anonymous public endpoints, so its
                        # applicable published ceiling is the broad IP pool;
                        # Bybit's X-Bapi remaining/reset headers are for the
                        # separate authenticated UID/endpoint pool. Bybit has
                        # no public counter for anonymous IP usage. Track every
                        # request made by this platform in the shared durable
                        # coordinator, but label the zero baseline as
                        # application-only rather than provider/IP-wide usage.
                        "baseline_mode": "local_zero",
                        "application_usage_only": True,
                    }
                ],
                "reset": "rolling",
            },
            "quota_scope": "ip",
            "quota_source": "Bybit V5 rate-limit documentation",
        },
        "gate_tradfi": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "stock_public_requests_per_second",
                        "limit": 5,
                        "window_seconds": 1,
                        "unit": "requests",
                        "scope": "ip",
                        "quota_group": "ip",
                        "source": "https://www.gate.com/docs/developers/apiv4/en/",
                        # Gate exposes native remaining/limit headers but not
                        # a trustworthy current pre-call counter; track this
                        # platform's calls in the shared coordinator and label
                        # the starting point application-only.
                        "baseline_mode": "local_zero",
                        "application_usage_only": True,
                    }
                ],
                "reset": "rolling",
            },
            "quota_scope": "ip",
            "quota_source": "Gate API v4 stock public endpoint rate-limit documentation",
        },
        "kraken_xstocks": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "public_requests_per_second",
                        "limit": 1,
                        "window_seconds": 1,
                        "unit": "requests",
                        "scope": "ip",
                        "quota_group": "ip",
                        "source": "https://support.kraken.com/articles/206548367-what-are-the-api-rate-limits-",
                        "limit_basis": "provider_recommended_safe_frequency",
                        # This adapter shares the exact Kraken public-IP pool
                        # and durable account scope with the Kraken crypto
                        # adapter; only platform-observed calls are counted.
                        "baseline_mode": "local_zero",
                        "application_usage_only": True,
                    }
                ],
                "reset": "rolling",
            },
            "quota_scope": "ip",
            "quota_source": "Kraken public API rate-limit documentation",
        },
        "dinari": {
            "quota_contract": {
                "dimensions": [],
                "unknown_dimensions": [
                    "account/partner request limits and commercial data entitlements"
                ],
                "source": "https://docs.dinari.com/reference",
            },
            "quota_scope": "api_key_id_and_partner_account",
            "quota_source": (
                "Dinari Enterprise API documentation; its June 11, 2024 API License with SLA "
                "states a 1,000,000-call rolling-30-day ceiling, but applicability to this "
                "free Sandbox key is unverified"
            ),
        },
        "ondo_global_markets": {
            "quota_contract": {
                "dimensions": [],
                "unknown_dimensions": ["account rate limit and endpoint cache/usage terms"],
                "source": "https://docs.ondo.finance/api-reference/overview",
            },
            "quota_scope": "api_key_and_account",
            "quota_source": "Ondo Stocks API OpenAPI (429 is documented; numeric limit not published)",
        },
        "tiingo": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "unique_symbols_per_month",
                        "limit": 500,
                        "window_seconds": 2678400,
                        "unit": "symbols",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://www.tiingo.com/pricing",
                        # Tiingo publishes the distinct-symbol pool but does
                        # not state its reset anchor. Keep the provider-defined
                        # label for audit and enforce a provider-scoped rolling
                        # 31-day safety envelope; a reviewed native reset may
                        # replace it through configuration.
                        "reset": "provider_defined",
                        "safety_reset": "rolling_31_days",
                        "safety_resolves_unknown_dimensions": ["unique_symbols_reset_anchor"],
                    },
                    {
                        "name": "requests_per_hour",
                        "limit": 50,
                        "window_seconds": 3600,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://www.tiingo.com/documentation/",
                        # Tiingo documents that the hourly pool resets every
                        # hour, but does not identify whether the boundary is
                        # fixed/calendar or rolling. Keep the provider-defined
                        # label for audit and enforce a provider-scoped rolling
                        # one-hour safety envelope until native evidence is
                        # reviewed.
                        "reset": "provider_defined",
                        "safety_reset": "rolling",
                        "safety_resolves_unknown_dimensions": [
                            "requests_per_hour_reset_boundary_model"
                        ],
                    },
                    {
                        "name": "requests_per_day",
                        "limit": 1000,
                        "window_seconds": 86400,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://www.tiingo.com/pricing",
                        # Tiingo's general API documentation states that the
                        # daily pool resets at midnight Eastern time.
                        "reset": "calendar_day_est",
                    },
                ],
                "unknown_dimensions": [
                    "unique_symbols_reset_anchor",
                    "requests_per_hour_reset_boundary_model",
                ],
                "reset": "provider_defined",
                "untracked_constraints": [
                    {
                        "name": "bandwidth_bytes_per_month",
                        # Tiingo publishes "1 GB"; decimal bytes are the
                        # conservative interpretation when the vendor does
                        # not state a binary unit.
                        "limit": 1_000_000_000,
                        "window_seconds": 2678400,
                        "unit": "bytes",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://www.tiingo.com/pricing",
                        # Tiingo's general API documentation states that the
                        # monthly bandwidth pool resets on the first day of
                        # each month at midnight Eastern time.
                        "reset": "calendar_month_est",
                        "limit_basis": "decimal_bytes_conservative_for_published_GB",
                    }
                ],
            },
            "quota_scope": "api_key",
            "quota_source": "Tiingo Starter pricing documentation",
        },
        "twelve_data": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "credits_per_minute",
                        "limit": 8,
                        "window_seconds": 60,
                        "unit": "credits",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://twelvedata.com/pricing",
                        "reset": "fixed_minute",
                    },
                    {
                        "name": "requests_per_day",
                        "limit": 800,
                        "window_seconds": 86400,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://twelvedata.com/pricing",
                        # Basic publishes a separate 800-requests/day
                        # allowance; the native usage body reports this in
                        # request units, separate from weighted minute credits.
                        "reset": "calendar_day_utc",
                    },
                    {
                        "name": "account_usage_probe_concurrency",
                        "limit": 1,
                        "window_seconds": 1,
                        "unit": "concurrent_requests",
                        "scope": "deployment",
                        "quota_group": "account_usage_probe",
                        "source": "application_policy:provider_native_baseline_bootstrap",
                        "reset": "rolling",
                        "applies_to_operations": ["fetch_account_usage"],
                    },
                ],
                "reset": "per_dimension",
                "operation_costs_required": True,
                "account_usage_bootstrap": {
                    "enabled": True,
                    "source": "application_policy:provider_native_baseline_bootstrap",
                    "reconciled_dimensions": [
                        "credits_per_minute",
                        "requests_per_day",
                    ],
                },
            },
            "tokens_per_minute": 8,
            "quota_scope": "api_key",
            "quota_source": (
                "Twelve Data Basic pricing and credits documentation: "
                "https://support.twelvedata.com/en/articles/5615854-credits"
            ),
        },
        "finnhub": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "calls_per_minute",
                        "limit": 60,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "operator_account_dashboard_2026-09-07",
                        # The account ceiling is exact, but its minute
                        # boundary is not documented.  Enforce a strict
                        # rolling envelope until native reset evidence exists.
                        "safety_reset": "rolling",
                    },
                    {
                        "name": "hard_calls_per_second",
                        "limit": 30,
                        "window_seconds": 1,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://finnhub.io/docs/api",
                        "safety_reset": "rolling",
                        # Finnhub publishes the 30-call ceiling but exposes no
                        # independent second-window usage counter. The shared
                        # coordinator starts at zero for this application's
                        # own calls only; the minute counter is bootstrapped
                        # separately from Finnhub's response headers.
                        "baseline_mode": "local_zero",
                        "application_usage_only": True,
                    },
                ],
                # The free account exposes two independent request-rate
                # dimensions. Record the operation map for both instead of
                # leaving the hard per-second reservation implicit.
                "dimension_costs_required": True,
                "account_usage_bootstrap": {
                    "enabled": True,
                    "reconciled_dimensions": ["calls_per_minute"],
                },
                "reset": "provider_defined_minute_and_rolling_second",
            },
            "tokens_per_minute": 60,
            "quota_scope": "api_key",
            "quota_source": "Finnhub account dashboard plus API documentation",
        },
        "eodhd": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "requests_per_minute",
                        # The detailed API-limits page documents 1,000
                        # requests/minute; the Free-plan pricing card conflicts
                        # at 20/minute. Use the documented API ceiling unless an
                        # operator supplies a key-specific native-header limit.
                        "limit": 1000,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://eodhd.com/financial-apis/api-limits",
                        "reset": "rolling",
                        "limit_basis": "published API-limits request ceiling; key-specific native limit is observation-only unless reviewed",
                    },
                    {
                        "name": "calls_per_day",
                        "limit": 20,
                        "window_seconds": 86400,
                        "unit": "calls",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://eodhd.com/financial-apis/api-limits",
                        "reset": "calendar_day_gmt",
                        "reset_source": "https://eodhd.com/financial-apis/api-limits",
                    },
                    {
                        "name": "account_usage_probe_concurrency",
                        "limit": 1,
                        "window_seconds": 1,
                        "unit": "concurrent_requests",
                        "scope": "deployment",
                        "quota_group": "account_usage_probe",
                        "source": "application_policy:provider_native_baseline_bootstrap",
                        "reset": "rolling",
                        "applies_to_operations": ["fetch_account_usage"],
                    },
                ],
                "reset": "per_dimension",
                "operation_costs_required": True,
                "account_usage_bootstrap": {
                    "enabled": True,
                    "source": "application_policy:provider_native_baseline_bootstrap",
                    "reconciled_dimensions": [
                        "requests_per_minute",
                        "calls_per_day",
                    ],
                    "allowed_unknown_dimensions": [],
                    "checkpoint_unreviewed_zero_billing": {
                        "operation": "fetch_account_usage",
                        "dimension": "calls_per_day",
                        "cost": 0,
                        "source": "https://eodhd.com/financial-apis/api-limits",
                        "evidence": (
                            "The Usage endpoint /api/user costs zero daily API-call credits; "
                            "the separate requests_per_minute dimension still charges one HTTP request."
                        ),
                    },
                },
                "source_conflicts": [
                    {
                        "dimension": "requests_per_minute",
                        "source": "https://eodhd.com/pricing",
                        "claim": "Free plan allows 20 requests per minute",
                        "conflicting_source": "https://eodhd.com/financial-apis/api-limits",
                        "conflicting_claim": "1,000 requests per minute on every plan",
                        "observed_key_header": {
                            "observed_at": "2026-10-14T16:27:48Z",
                            "limit": 1200,
                            "remaining": 1199,
                        },
                        "resolution": "Use the detailed API-limits page's 1,000/minute default. The configured key returned 1,200/1,199 native headers; preserve them as key-specific evidence and apply 1,200 only through the explicit reviewed account override, never dynamic widening.",
                    }
                ],
                "unknown_dimensions": [],
            },
            "tokens_per_minute": 1000,
            "quota_scope": "api_key",
            "quota_source": (
                "EODHD API limits documentation (1,000 requests/minute) with a "
                "documented Free-plan pricing-card conflict and current-key "
                "native header observation: "
                "https://eodhd.com/financial-apis/api-limits; "
                "https://eodhd.com/pricing"
            ),
        },
        "fmp": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "calls_per_day",
                        "limit": 250,
                        "window_seconds": 86400,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": (
                            "FMP Basic pricing (250 API calls/day); official sources "
                            "conflict on whether the daily reset has a universal fixed "
                            "time, so use a rolling safety window unless account-specific "
                            "reset evidence is configured: "
                            "https://site.financialmodelingprep.com/pricing-plans; "
                            "https://site.financialmodelingprep.com/faqs; "
                            "https://site.financialmodelingprep.com/de/insights/platform/what-happens-when-you-hit-your-fmp-api-limit"
                        ),
                        "reset": "provider_defined",
                        "safety_reset": "rolling",
                    },
                    {
                        "name": "bandwidth_bytes_per_30_days",
                        "limit": 500_000_000,
                        "window_seconds": 2_592_000,
                        "unit": "bytes",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://site.financialmodelingprep.com/developer/docs/pricing",
                        "reset": "rolling_30_days",
                        "limit_basis": "decimal_bytes_conservative_for_published_MB",
                    },
                    {
                        "name": "account_usage_probe_concurrency",
                        "limit": 1,
                        "window_seconds": 1,
                        "unit": "concurrent_requests",
                        "scope": "deployment",
                        "quota_group": "account_usage_probe",
                        "source": "application_policy:provider_native_baseline_bootstrap",
                        "reset": "rolling",
                        "applies_to_operations": ["fetch_account_usage"],
                    },
                ],
                "reset": "provider_defined",
                "untracked_constraints": [
                    {
                        "name": "bandwidth_bytes_per_30_days",
                        # FMP publishes 500 MB. Use decimal bytes as the
                        # conservative interpretation of the published unit.
                        "limit": 500_000_000,
                        "unit": "bytes",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://site.financialmodelingprep.com/developer/docs/pricing",
                        "window_seconds": 2_592_000,
                        # The current official pricing page explicitly calls
                        # this a trailing 30-day pool. Preserve that provider
                        # semantics instead of requiring an invented calendar
                        # anchor or an otherwise redundant manual reset.
                        "reset": "rolling_30_days",
                        "limit_basis": "decimal_bytes_conservative_for_published_MB",
                    }
                ],
                "unknown_dimensions": [],
                "account_usage_bootstrap": {
                    "enabled": True,
                    "source": "first-party FMP dashboard usage counters; internal endpoint, schema-validated and credential-redacted",
                    "reconciled_dimensions": [
                        "calls_per_day",
                        "bandwidth_bytes_per_30_days",
                    ],
                },
            },
            "quota_scope": "api_key",
            "quota_source": (
                "FMP official pricing bandwidth contract plus operator account evidence"
            ),
        },
        "marketdata_app": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "credits_per_day",
                        "limit": 100,
                        "window_seconds": 86400,
                        "unit": "credits",
                        "scope": "api_key",
                        # Both documented limits are charged to the same
                        # account/key. Keep one explicit bucket across all
                        # capabilities instead of multiplying the allowance.
                        "quota_group": "account",
                        "source": "https://www.marketdata.app/docs/api/rate-limiting/",
                    },
                    {
                        "name": "concurrent_requests",
                        "limit": 50,
                        "window_seconds": 1,
                        "unit": "concurrent_requests",
                        "scope": "api_key",
                        "quota_group": "account",
                        "source": "https://www.marketdata.app/docs/api/rate-limiting/",
                        "reset": "rolling",
                    },
                ],
                "reset": "09:30 America/New_York",
                "operation_costs_required": True,
                "account_usage_bootstrap": {
                    "enabled": True,
                    "source": (
                        "https://www.marketdata.app/docs/api/rate-limiting/ and "
                        "https://www.marketdata.app/docs/sdk/go/utilities/user/; "
                        "successful /user/ response reports its own credit usage"
                    ),
                    "reconciled_dimensions": ["credits_per_day"],
                    "allowed_unknown_dimensions": [],
                },
            },
            "quota_scope": "api_key",
            "quota_source": "MarketData.app rate-limiting documentation",
        },
        "tradier": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "market_data_requests_per_minute",
                        "limit": 120,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "production_token",
                        "quota_group": "production_token",
                        "source": "https://docs.tradier.com/docs/rate-limiting",
                    },
                ],
                "reset": "rolling",
            },
            "tokens_per_minute": 120,
            "quota_scope": "production_token",
            "quota_source": "Tradier rate-limiting documentation",
        },
        "marketstack": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "requests_per_month",
                        "limit": 100,
                        "window_seconds": 2592000,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://marketstack.com/pricing",
                        "reset": "provider_defined",
                        "limit_basis": (
                            "published Free-plan limit; conservatively enforced against conflicting FAQ text"
                        ),
                        # Marketstack calls the allowance monthly but does not
                        # document the exact reset anchor. The stricter
                        # provider-specific rolling safety window never assumes
                        # a calendar boundary or increases the published cap.
                        "safety_reset": "rolling_30_days",
                        "safety_resolves_unknown_dimensions": ["monthly_cap_reset_boundary"],
                    },
                    {
                        "name": "requests_per_second",
                        "limit": 5,
                        "window_seconds": 1,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://marketstack-wp.apilayer.green/documentation/",
                        "limit_basis": "provider documentation states the API is limited to five requests per second",
                        "reset": "provider_defined",
                        # The vendor publishes the rate but not the exact
                        # bucket boundary. Use a rolling one-second client
                        # envelope without claiming the provider's reset model.
                        "safety_reset": "rolling",
                        "safety_resolves_unknown_dimensions": [
                            "requests_per_second_reset_boundary"
                        ],
                        # The strict one-second application coordinator is
                        # shared across all worktrees and workers. There is no
                        # native provider counter for this short window.
                        "baseline_mode": "local_zero",
                        "application_usage_only": True,
                    },
                ],
                # The current pricing page states 100/month while the FAQ
                # also contains a stale/inconsistent 1,000/month answer. Use
                # the lower explicit Free-plan ceiling, preserve the conflict
                # below, and resolve only the unknown reset boundary through
                # the strict rolling envelope on the dimension.
                "unknown_dimensions": [
                    "monthly_cap_reset_boundary",
                    "requests_per_second_reset_boundary",
                ],
                "source_conflicts": [
                    {
                        "source": "https://marketstack.com/faq",
                        "claim": "1,000 requests per month",
                        "conflicts_with": "https://marketstack.com/pricing",
                        "resolution": "enforce the lower Free-plan ceiling of 100 requests per 30 rolling days",
                    }
                ],
                # Marketstack meters each ticker in a multi-symbol request as
                # one monthly request, does not count API errors, and may
                # permit account-configured overages.  Preserve these
                # provider-specific semantics as audit metadata without
                # treating them as a safe entitlement or reset boundary.
                "usage_semantics": {
                    "multi_symbol_request": "one_request_per_symbol",
                    "api_errors_counted": False,
                    "notifications_at_fraction": [0.75, 0.90, 1.00],
                    "maximum_overdraft_fraction": 0.05,
                    "disable_at_fraction_without_overage_billing": 1.20,
                    "overage_billing": "account_configurable",
                    "source": "https://marketstack.com/faq",
                },
                "reset": "per_dimension",
            },
            "quota_scope": "api_key",
            "quota_source": "Marketstack Free-plan pricing (100 requests per rolling 30 days) plus provider-documented 5 requests/second; strict local rolling safety envelopes preserve unpublished reset boundaries",
        },
        "ibkr": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "global_requests_per_second",
                        "limit": 10,
                        "window_seconds": 1,
                        "unit": "requests",
                        "scope": "authenticated_session",
                        "quota_group": "authenticated_session",
                        "source": "https://ibkrcampus.com/docs/web-api/v1/pacing-limitations",
                    },
                    {
                        "name": "historical_requests_per_minute",
                        "limit": 50,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "authenticated_session",
                        "quota_group": "authenticated_session",
                        "source": "https://ibkrcampus.com/docs/web-api/v1/endpoints/market-data/historical-market-data",
                    },
                ],
                # IBKR's five-concurrent limit applies to WebSocket `smh`
                # historical streaming subscriptions, not this adapter's
                # REST /iserver/marketdata/history endpoint.
                "reset": "rolling",
                "endpoint_specific_limits": True,
                "endpoint_constraints": {
                    "iserver/marketdata/history": {
                        "max_response_points": 1000,
                        "source": "https://ibkrcampus.com/docs/web-api/v1/endpoints/market-data/historical-market-data",
                    }
                },
            },
            "quota_scope": "authenticated_session",
            "quota_source": "IBKR Web API historical market-data and pacing documentation",
        },
    }
    PROVIDER_FRESHNESS_SEEDS: dict[str, int] = {}
    PROVIDER_USAGE_PROFILE_SEEDS: dict[str, dict] = {
        # These adapters use one upstream request for each listed operation.
        # Historical operations whose request count depends on range/paging
        # are intentionally omitted and receive a caller-supplied estimate
        # from the market-data service instead of a guessed one-request cost.
        "alpaca": {
            "mode": "call_count",
            "unit_label": "requests",
            "operation_costs": {
                "get_current_price": 1,
                "fetch_rfr_ohlcv": 1,
                "discover_universe_page": 1,
                "get_instrument_profile": 1,
                # The native usage snapshot is one bounded market-data read;
                # its provider request pool is excluded during bootstrap and
                # only the local concurrency lease is charged.
                "fetch_account_usage": 1,
            },
        },
        "massive": {
            "mode": "call_count",
            "unit_label": "requests",
            "operation_costs": {
                "search_instruments": 1,
                "discover_universe_page": 1,
                "get_instrument_profile": 1,
                # One event read includes one split request and one dividend
                # request; a positive page-bound override reserves the actual
                # worst case before the adapter follows either cursor.
                "fetch_instrument_events": 2,
                "fetch_market_events": 1,
                "fetch_market_holidays": 1,
            },
        },
        "fred": {
            "mode": "call_count",
            "unit_label": "requests",
            "operation_costs": {
                "fetch_ohlcv": 1,
                "fetch_latest_ohlcv": 1,
                "get_current_price": 1,
                "bulk_fetch": 1,
                "fetch_rfr_ohlcv": 1,
            },
        },
        "openfigi": {
            "mode": "call_count",
            "unit_label": "requests",
            "operation_costs": {
                "fetch_stable_identifiers": 1,
                "resolve_instrument_profile": 1,
                "fetch_account_usage": 1,
            },
        },
        # Binance publishes exact weights for the two single-request adapter
        # operations below.  ``fetch_ohlcv`` is intentionally absent: one
        # adapter call may page through an arbitrary historical range and
        # cannot be safely charged as one weight before execution.
        "binance": {
            "mode": "weighted_request",
            "unit_label": "request_weight",
            "operation_costs": {
                "get_current_price": 2,
                "discover_universe_page": 20,
                "reconcile_universe_page": 20,
                # /api/v3/time is a one-weight native account-usage probe.
                "fetch_account_usage": 1,
            },
        },
        "twelve_data": {
            "mode": "credit_count",
            "unit_label": "credits",
            "operation_costs": {
                "fetch_ohlcv": 1,
                "fetch_latest_ohlcv": 1,
                "get_current_price": 1,
                "search_instruments": 1,
                "discover_universe_page": 1,
                # Twelve Data documents /api_usage as a one-credit API call;
                # its response headers expose the post-call minute pool.
                "fetch_account_usage": 1,
            },
        },
        # Alpha Vantage's adapter performs exactly one ``query`` request for
        # each of these operation families.  Keep the mapping explicit even
        # though the provider uses a simple daily request allowance: a future
        # adapter change that adds pagination or a compound lookup must update
        # this reviewed contract instead of silently falling back to one.
        "alpha_vantage": {
            "mode": "call_count",
            "unit_label": "requests",
            "operation_costs": {
                "search_instruments": 1,
                "fetch_ohlcv": 1,
                "fetch_latest_ohlcv": 1,
                "get_current_price": 1,
                "bulk_fetch": 1,
                "fetch_rfr_ohlcv": 1,
                "discover_universe_page": 1,
                "fetch_market_events": 1,
                "fetch_earnings_calendar": 1,
                "fetch_instrument_events": 1,
            },
        },
        # IBKR's account-context snapshot is two HTTP requests (accounts
        # initialization plus snapshot); history/search/profile are one page
        # per adapter operation before the range-aware service override is
        # applied. Historical page counts are never guessed here.
        "ibkr": {
            "mode": "call_count",
            "unit_label": "requests",
            "operation_costs": {
                "search_instruments": 1,
                "get_instrument_profile": 1,
                "fetch_ohlcv": 1,
                "fetch_latest_ohlcv": 1,
                "get_current_price": 2,
            },
            "dimension_costs": {
                # This endpoint-specific dimension applies only to history.
                # Empty maps are explicit zero-cost exclusions; the runtime
                # supplies the dynamic page cost for history operations.
                "historical_requests_per_minute": {
                    "search_instruments": {},
                    "get_instrument_profile": {},
                    "get_current_price": {},
                },
            },
        },
        "marketdata_app": {
            "mode": "credit_count",
            "unit_label": "credits",
            "operation_costs": {
                "get_current_price": 1,
                # Stock-candle and bulk-history costs are response-dependent:
                # callers must supply the documented one-credit-per-1,000
                # candle estimate before the provider can be admitted.
                # The provider documents one credit per expiration lookup.
                # ``fetch_option_chain`` and ``fetch_option_quote_history`` are
                # intentionally absent: current chains/quotes are billed per
                # returned contract/symbol (historical responses per 1,000),
                # so a fixed request cost would under-account the
                # response-dependent charge.
                "list_option_expirations": 1,
                # Account introspection is a provider request and the current
                # API documentation says a successful response consumes at
                # least one credit; its native counter includes this request.
                # The explicit bootstrap mapping permits one bounded native
                # snapshot to establish an unknown daily baseline, after
                # which each usage read is reserved against that same pool.
                "fetch_account_usage": 1,
            },
        },
        "coinbase": {
            "mode": "call_count",
            "unit_label": "requests",
            "operation_costs": {
                "fetch_ohlcv": 1,
                "fetch_latest_ohlcv": 1,
                "get_current_price": 1,
                "discover_universe_page": 1,
            },
        },
        "kraken": {
            "mode": "call_count",
            "unit_label": "requests",
            "operation_costs": {
                "get_current_price": 1,
                "discover_universe_page": 1,
            },
        },
        "finra": {
            "mode": "multi_dimensional",
            "unit_label": "requests",
            # A cold OAuth token cache adds one token request before an
            # authenticated dataset request. Short interest then uses one
            # Query API request; Daily List uses its authoritative partition
            # index plus one data page. Reserve those distinct worst cases
            # even when a warm process reuses the token.
            "operation_costs": {
                "fetch_short_interest": 2,
                "fetch_market_events": 3,
            },
            # FINRA documents a 3 MB maximum per synchronous response. Short
            # interest has one data response; Daily List reads both the
            # partition index and a data page, so reserve two response maxima.
            # OAuth bytes are not market-data downloads. Settle every operation
            # to the total measured response bytes after execution.
            "dimension_costs": {
                "asynchronous_requests_per_minute_dataset": {},
                "download_bytes_per_calendar_month": {
                    "fetch_short_interest": 3_000_000,
                    "fetch_market_events": 6_000_000,
                },
            },
        },
        # A cold SEC metadata/event lookup resolves the ticker through the
        # cached public directory and then fetches submissions. Reserve both
        # requests even when a warm process can reuse the directory cache.
        "edgar": {
            "mode": "call_count",
            "unit_label": "requests",
            "operation_costs": {
                "search_instruments": 1,
                "discover_universe_page": 1,
                "discover_issuer_ciks_page": 1,
                "get_instrument_profile": 2,
                "fetch_instrument_events": 2,
                "fetch_fundamental_facts": 1,
                "fetch_ipo_pipeline_events": 1,
            },
        },
        # A cold Nasdaq refresh reads both official directory files. ETag and
        # Last-Modified revalidation still perform one conditional request per
        # file, so reserve both transport calls whenever the cache is refreshed.
        "nasdaq": {
            "mode": "call_count",
            "unit_label": "requests",
            "operation_costs": {
                "discover_universe_page": 2,
                "reconcile_universe_page": 2,
            },
        },
        # A complete CTA refresh reads the directory index and one dated CSV.
        "cta_plan": {
            "mode": "call_count",
            "unit_label": "requests",
            "operation_costs": {
                "discover_universe_page": 2,
                "reconcile_universe_page": 2,
            },
        },
        # One logical Query API page performs at most the partition request and
        # one synchronous data request. The runtime settles the reservation to
        # observed request/byte telemetry, so cached partitions and smaller
        # responses immediately release unused capacity.
        "finra_otc_directory": {
            "mode": "multi_dimensional",
            "unit_label": "provider_units",
            "operation_costs": {
                "discover_universe_page": 2,
                "reconcile_universe_page": 2,
            },
            "dimension_costs": {
                "synchronous_requests_per_minute": {
                    "discover_universe_page": 2,
                    "reconcile_universe_page": 2,
                },
                "download_bytes_per_calendar_month": {
                    "discover_universe_page": 6_000_000,
                    "reconcile_universe_page": 6_000_000,
                },
            },
        },
        "eodhd": {
            "mode": "credit_count",
            "unit_label": "calls",
            "operation_costs": {
                "fetch_ohlcv": 1,
                "fetch_latest_ohlcv": 1,
                "get_current_price": 1,
                "bulk_fetch": 1,
                "get_instrument_profile": 10,
                "discover_universe_page": 1,
                # Keep the usage read visible as one HTTP operation. EODHD
                # explicitly prices /api/user at zero daily API-call credits;
                # its request still consumes the separate per-minute pool.
                "fetch_account_usage": 1,
            },
            # EODHD's endpoint rate limit is measured in HTTP requests, while
            # Fundamentals endpoints consume provider-call credits. Keep the
            # two units separate: one profile request consumes one RPM unit
            # and ten daily API-call credits.
            "dimension_costs": {
                "requests_per_minute": {
                    "fetch_ohlcv": 1,
                    "fetch_latest_ohlcv": 1,
                    "get_current_price": 1,
                    "bulk_fetch": 1,
                    "get_instrument_profile": 1,
                    "discover_universe_page": 1,
                    "fetch_account_usage": 1,
                },
                "calls_per_day": {
                    "fetch_ohlcv": 1,
                    "fetch_latest_ohlcv": 1,
                    "get_current_price": 1,
                    "bulk_fetch": 1,
                    "get_instrument_profile": 10,
                    "discover_universe_page": 1,
                    # Empty operation value is an explicit exclusion from
                    # this weighted daily-credit dimension, not a missing cost.
                    "fetch_account_usage": {},
                },
            },
        },
        "tiingo": {
            "mode": "multi_dimensional",
            "unit_label": "provider_units",
            "operation_costs": {
                "fetch_ohlcv": 1,
                "fetch_latest_ohlcv": 1,
                "get_current_price": 1,
                "bulk_fetch": 1,
                "search_instruments": 1,
                "get_instrument_profile": 1,
            },
            "dimension_costs": {
                "unique_symbols_per_month": {
                    # These operations address one known security identity.
                    # The durable coordinator deduplicates identities inside
                    # the active provider window, so repeated history pages
                    # for one symbol do not consume additional symbol slots.
                    "fetch_ohlcv": 1,
                    "fetch_latest_ohlcv": 1,
                    "get_current_price": 1,
                    "bulk_fetch": 1,
                    "get_instrument_profile": 1,
                    # Search resolves a free-text query rather than requesting
                    # data for a known symbol. It still consumes request and
                    # bandwidth budgets; the symbol-count unit is inapplicable.
                    "search_instruments": {},
                },
            },
        },
        "finnhub": {
            "mode": "call_count",
            "unit_label": "requests",
            "operation_costs": {
                "fetch_account_usage": 1,
                "fetch_ohlcv": 1,
                "fetch_latest_ohlcv": 1,
                "get_current_price": 1,
                "search_instruments": 1,
                "get_instrument_profile": 1,
                "fetch_instrument_events": 1,
                "fetch_market_events": 1,
                "bulk_fetch": 1,
                "discover_universe_page": 1,
            },
            # Every adapter operation is one provider request in each
            # Finnhub rate window. Keep both maps explicit so the durable
            # reservation and admin usage view expose both provider limits.
            "dimension_costs": {
                "calls_per_minute": {
                    "fetch_account_usage": 1,
                    "fetch_ohlcv": 1,
                    "fetch_latest_ohlcv": 1,
                    "get_current_price": 1,
                    "search_instruments": 1,
                    "get_instrument_profile": 1,
                    "fetch_instrument_events": 1,
                    "fetch_market_events": 1,
                    "bulk_fetch": 1,
                    "discover_universe_page": 1,
                },
                "hard_calls_per_second": {
                    "fetch_account_usage": 1,
                    "fetch_ohlcv": 1,
                    "fetch_latest_ohlcv": 1,
                    "get_current_price": 1,
                    "search_instruments": 1,
                    "get_instrument_profile": 1,
                    "fetch_instrument_events": 1,
                    "fetch_market_events": 1,
                    "bulk_fetch": 1,
                    "discover_universe_page": 1,
                },
            },
        },
        "marketstack": {
            "mode": "call_count",
            "unit_label": "requests",
            "operation_costs": {
                "get_current_price": 1,
            },
        },
        "fmp": {
            "mode": "multi_dimensional",
            "unit_label": "provider_units",
            "operation_costs": {
                "fetch_ohlcv": 1,
                "fetch_latest_ohlcv": 1,
                "get_current_price": 1,
                "bulk_fetch": 1,
                "get_instrument_profile": 1,
                "fetch_market_events": 1,
                "discover_universe_page": 1,
                "fetch_account_usage": 1,
            },
        },
        "tradier": {
            "mode": "call_count",
            "unit_label": "requests",
            "operation_costs": {
                "fetch_ohlcv": 1,
                "fetch_latest_ohlcv": 1,
                "get_current_price": 1,
                "search_instruments": 1,
                "bulk_fetch": 1,
                "list_option_expirations": 1,
                "fetch_option_chain": 1,
            },
        },
        # A metadata lookup resolves the provider-native coin id through
        # /search and then fetches /coins/{id}. Reserve both HTTP calls so
        # quota accounting cannot under-report this compound operation.
        "coingecko": {
            "mode": "call_count",
            "unit_label": "requests",
            "operation_costs": {
                "search_instruments": 1,
                "discover_universe_page": 1,
                "get_instrument_profile": 2,
                # CoinGecko's successful /key snapshot consumes one monthly
                # credit and participates in its normal minute rate limit.
                "fetch_account_usage": 1,
            },
        },
        # Every tokenized quote adapter first resolves the provider asset and
        # then performs its quote/order-book read.  Reserve both HTTP calls;
        # charging one call here would under-report provider usage and could
        # admit a second request into a full provider window.
        "xstocks": {
            "mode": "call_count",
            "unit_label": "requests",
            "operation_costs": {
                "discover_tokenized_assets": 1,
                "get_tokenized_asset": 1,
                "get_tokenized_price": 2,
                "fetch_tokenized_corporate_actions": 1,
                "fetch_account_usage": 1,
            },
        },
        "robinhood_tokens": {
            "mode": "call_count",
            "unit_label": "requests",
            "operation_costs": {
                "discover_tokenized_assets": 1,
                "get_tokenized_asset": 1,
                # The asset lookup costs one request and the bounded
                # provider-specific quote retry may consume up to three
                # attempts after HTTP 429, so reserve the four-request
                # worst-case operation rather than undercharging throttles.
                "get_tokenized_price": 4,
                "fetch_tokenized_corporate_actions": 1,
            },
        },
        "bybit_xstocks": {
            "mode": "call_count",
            "unit_label": "requests",
            "operation_costs": {
                "discover_tokenized_assets": 1,
                "discover_tokenized_page": 1,
                "get_tokenized_asset": 1,
                "get_tokenized_price": 2,
            },
        },
        "gate_tradfi": {
            "mode": "call_count",
            "unit_label": "requests",
            "operation_costs": {
                "discover_tokenized_assets": 1,
                "get_tokenized_asset": 1,
                "get_tokenized_price": 2,
            },
        },
        "kraken_xstocks": {
            "mode": "call_count",
            "unit_label": "requests",
            "operation_costs": {
                "discover_tokenized_assets": 1,
                "get_tokenized_asset": 1,
                "get_tokenized_price": 1,
            },
        },
        "dinari": {
            "mode": "call_count",
            "unit_label": "requests",
            # Dinari Sandbox reads retry a transient HTTP 500 twice. Reserve
            # every possible transport attempt, not only the logical request
            # count, so the coordinator cannot undercount the provider calls.
            "operation_costs": DINARI_SANDBOX_OPERATION_MINIMUM_REQUEST_COSTS,
        },
        "ondo_global_markets": {
            "mode": "call_count",
            "unit_label": "requests",
            "operation_costs": {
                "discover_tokenized_assets": 1,
                "get_tokenized_asset": 1,
                "get_tokenized_price": 2,
                "fetch_tokenized_market_data": 2,
                "fetch_tokenized_ohlc": 2,
                # Metadata resolution plus the provider's daily OHLC read;
                # quota/terms admission remains fail-closed until reviewed.
                "fetch_tokenized_historical_prices": 2,
            },
        },
    }
    # A capability is not usable merely because an adapter exists. These
    # explicit defaults describe the free/public plans that the workstation
    # may use; any provider omitted here remains unreviewed and disabled until
    # an operator supplies an entitlement through the governance API.
    PROVIDER_ENTITLEMENT_SEEDS: dict[str, dict] = {
        "alpaca": {
            "configured_plan": "free-iex",
            "is_free": True,
            "authentication_required": True,
            "usage_terms": "Free IEX feed with plan/quota and redistribution restrictions; review before deployment.",
            "history_depth": "Basic stock/ETF history since 2016; latest data is limited to the documented delayed feed",
            "quota_policy": {
                "history_constraints": {
                    "earliest_date": "2016-01-01",
                    "source": "https://docs.alpaca.markets/us/v1.1/docs/about-market-data-api",
                },
                "latest_data_delay_seconds": 900,
                "latest_data_delay_source": "https://docs.alpaca.markets/us/docs/about-market-data-api",
                "websocket_symbol_limit": 30,
                "websocket_symbol_limit_source": "https://docs.alpaca.markets/us/docs/about-market-data-api",
            },
            "venue_coverage": "IEX US equities; provider-defined universe",
            "freshness_semantics": "IEX free feed; historical/latest equity data limited to latest 15 minutes",
        },
        "edgar": {
            "configured_plan": "sec-public",
            "is_free": True,
            "authentication_required": True,
            "usage_terms": "SEC public data subject to fair-access policy and user-agent identification.",
            "history_depth": "SEC filing history",
            "venue_coverage": "US issuers represented in SEC filings",
            "freshness_semantics": "Filing publication time; not quote data",
        },
        "massive": {
            "configured_plan": "free-stocks-basic",
            "is_free": True,
            "authentication_required": True,
            "usage_terms": "Stocks Basic has 5 REST requests/minute per asset-class account bucket; reference data and corporate actions are included on Basic. Individual Market Data Terms restrict use to display; express prior written consent is required for persistent storage/non-display use, and Business licensing is required if anyone else can see the data.",
            "history_depth": "Two years on Stocks Basic; plan-dependent beyond that",
            "quota_policy": {
                "history_constraints": {
                    "max_lookback_years": 2,
                    "source": "https://massive.com/stocks",
                }
            },
            "venue_coverage": "Provider-supported US reference universe",
            "freshness_semantics": "Plan-dependent delayed/EOD",
        },
        "alpha_vantage": {
            "configured_plan": "free-key",
            "is_free": True,
            "authentication_required": True,
            "usage_terms": "Free API key with documented quota limits.",
            "history_depth": (
                "Latest 100 daily points on the free compact endpoint; documented "
                "weekly/monthly raw series expose long historical ranges; adjusted "
                "daily history is premium"
            ),
            "venue_coverage": "Provider-supported US symbols",
            "freshness_semantics": "EOD/delayed",
        },
        "nasdaq": {
            "configured_plan": "public-directory",
            "is_free": True,
            "authentication_required": False,
            "usage_terms": "Public Nasdaq Trader symbol-directory files; no redistribution entitlement inferred.",
            "history_depth": "Directory snapshots and lifecycle evidence only",
            "venue_coverage": "Supplementary Nasdaq-listed and other-exchange evidence; not sole whole-NMS absence authority",
            "freshness_semantics": "Directory publication/update time",
        },
        "cta_plan": {
            "configured_plan": "public-daily-symbol-file",
            "is_free": True,
            "authentication_required": False,
            "usage_terms": "Anonymous CTA Plan Tape A/B symbol file. No numeric HTTP quota is published; the two-request daily ceiling is application policy, not a vendor limit.",
            "history_depth": "Daily listing snapshots; prior symbol field supports observed symbol changes",
            "venue_coverage": "CTA Network A/B; complements Nasdaq-listed Tape C and does not alone authorize whole-NMS absence",
            "freshness_semantics": "Daily file published by midnight ET with data as of 20:00 ET",
            "live_probe_status": "not_run",
        },
        "finra_otc_directory": {
            "configured_plan": "public-query-api",
            "is_free": True,
            "authentication_required": True,
            "usage_terms": (
                "FINRA public Query API credentials; the owner has approved private persistent "
                "storage, while FINRA equity/API terms remain recorded provider facts."
            ),
            "history_depth": (
                "Current OTC security-master plus FINRA's rolling recent partitions; retained "
                "daily snapshots and Daily List deltas build durable history"
            ),
            "venue_coverage": "All OTCBB and other OTC issues exposed by FINRA Symbol Directory",
            "freshness_semantics": "Latest available FINRA asOfDate partition",
            "live_probe_status": "credentialed_live_verified",
        },
        "openfigi": {
            "configured_plan": "free-api",
            "is_free": True,
            "authentication_required": False,
            "usage_terms": "Free mapping API subject to published rate limits.",
            "history_depth": "Identifier mapping only",
            "venue_coverage": "Global identifier mapping coverage",
            "freshness_semantics": "Lookup response time",
        },
        "fred": {
            "configured_plan": "unreviewed",
            "is_free": True,
            "authentication_required": True,
            "usage_terms": (
                "FRED API terms permit the provider to change bandwidth/transaction limits; "
                "third-party series copyrights and redistribution restrictions remain the "
                "operator's responsibility, and the required non-endorsement notice applies."
            ),
            "history_depth": "Series-dependent macro history",
            "venue_coverage": "FRED series",
            "freshness_semantics": "Series publication/update time",
        },
        "binance": {
            "configured_plan": "public-market-data",
            "is_free": True,
            "authentication_required": False,
            "usage_terms": "Public market-data endpoints; exchange terms apply.",
            "history_depth": "Exchange endpoint depth",
            "venue_coverage": "Binance crypto markets",
            "freshness_semantics": "Delayed/current endpoint response",
        },
        "coinbase": {
            "configured_plan": "public-exchange-api",
            "is_free": True,
            "authentication_required": False,
            "usage_terms": "Coinbase Exchange public REST API limits; no redistribution entitlement implied.",
            "history_depth": "Endpoint candle retention; maximum 300 candles per request",
            "venue_coverage": "Coinbase Exchange crypto products",
            "freshness_semantics": "Public exchange endpoint response",
        },
        "kraken": {
            "configured_plan": "public-exchange-api",
            "is_free": True,
            "authentication_required": False,
            "usage_terms": "Kraken public API safe-frequency and pair limits apply.",
            "history_depth": "OHLC endpoint returns recent 720 entries",
            "venue_coverage": "Kraken crypto pairs",
            "freshness_semantics": "Public exchange endpoint response",
        },
        "coingecko": {
            "configured_plan": "free-demo",
            "is_free": True,
            "authentication_required": False,
            "usage_terms": (
                "Demo is for testing/exploration and requires attribution; do not persist "
                "without current written authority covering automation, audience, attribution, "
                "and retention/deletion after access ends."
            ),
            "history_depth": "Plan-dependent crypto history",
            "venue_coverage": "CoinGecko asset universe",
            "freshness_semantics": "Delayed/current endpoint response",
        },
        "tiingo": {
            "configured_plan": "starter-free",
            "is_free": True,
            "authentication_required": True,
            "usage_terms": "Individual internal use under Tiingo Starter terms; request, symbol, and bandwidth limits apply.",
            "history_depth": "30+ years of price history; five years of fundamentals per current Starter pricing",
            "venue_coverage": "Provider-supported US and global securities",
            "freshness_semantics": "Historical/EOD for the implemented adapter",
        },
        "twelve_data": {
            "configured_plan": "basic-free",
            "is_free": True,
            "authentication_required": True,
            "usage_terms": "Twelve Data Basic credits and licensing terms apply; no redistribution permission inferred.",
            "history_depth": "Plan and endpoint dependent",
            "venue_coverage": "Provider-supported US securities",
            "freshness_semantics": "Plan-dependent delayed/current data",
        },
        "finnhub": {
            "configured_plan": "free-api-key",
            "is_free": True,
            "authentication_required": True,
            "usage_terms": "Finnhub free plan and endpoint-specific licensing terms apply.",
            "history_depth": "Endpoint and free-plan dependent",
            "venue_coverage": "Provider-supported US securities",
            "freshness_semantics": "Plan-dependent delayed/current data",
            "capabilities": {
                "price_history": {
                    "configured_plan": "unreviewed",
                    "is_free": False,
                    "usage_terms": "The observed free key returned HTTP 403 for stock/candle; do not route historical candles without a supporting entitlement.",
                    "history_depth": None,
                }
            },
        },
        "marketstack": {
            "configured_plan": "free-100-month",
            "is_free": True,
            "authentication_required": True,
            "usage_terms": "Marketstack free plan; 100 monthly requests and a separate documented maximum of 5 HTTP requests/second apply.",
            "history_depth": "Plan dependent",
            "quota_policy": {
                "history_constraints": {
                    "max_lookback_years": 1,
                    "source": "https://marketstack.com/pricing",
                }
            },
            "venue_coverage": "Provider-supported US securities",
            "freshness_semantics": "EOD/delayed on the free plan",
        },
        "eodhd": {
            "configured_plan": "free-20-calls-day",
            "is_free": True,
            "authentication_required": True,
            "usage_terms": (
                "EODHD Free: 20 weighted API-call credits/day, resetting at midnight GMT, "
                "with conflicting official per-minute limits: the pricing table says "
                "20 requests/minute while the API-limits page says 1,000/minute on "
                "every plan. Runtime conservatively enforces 20/minute until account-native "
                "evidence is reviewed; endpoint credit costs are accounted separately. "
                "The /api/user usage endpoint costs zero daily credits. Free historical "
                "EOD depth is one year."
            ),
            "history_depth": "Plan and endpoint dependent",
            "quota_policy": {
                "history_constraints": {
                    "max_lookback_years": 1,
                    "source": "https://eodhd.com/pricing",
                }
            },
            "venue_coverage": "Provider-supported US securities",
            "freshness_semantics": "Historical/EOD",
            "capabilities": {
                "instrument_metadata": {
                    # Free Starter does not include Fundamental API access.
                    # An unreviewed capability stays blocked even if the
                    # legacy paid-routing switch is enabled; a reviewed plan
                    # and explicit switch are both required.
                    "configured_plan": "unreviewed",
                    "is_free": False,
                    "usage_terms": (
                        "EODHD Free Starter does not include Fundamentals/profile access; "
                        "configure an operator-reviewed plan with this endpoint entitlement "
                        "before routing."
                    ),
                    "live_probe_status": "not_run",
                }
            },
        },
        "fmp": {
            "configured_plan": "basic-free",
            "is_free": True,
            "authentication_required": True,
            "usage_terms": "FMP Basic/free account limits and licensing terms apply; bandwidth accounting is required before routing.",
            "history_depth": "Plan and endpoint dependent",
            "venue_coverage": "Provider-supported US securities",
            "freshness_semantics": "Historical/EOD for the implemented adapter",
        },
        "tradier": {
            "configured_plan": "individual-production-token",
            "is_free": True,
            "authentication_required": True,
            "usage_terms": "Individual Tradier Brokerage token; consolidated market-data terms apply.",
            "history_depth": "Endpoint dependent",
            "venue_coverage": "US equities, ETFs, indices, and options as entitled",
            "freshness_semantics": "Production real-time; sandbox delayed 15 minutes",
        },
        "marketdata_app": {
            # The public 100-credit Free Forever contract is a provider seed,
            # not an assertion about the operator's account.  The account
            # plan is supplied only through the explicit reviewed settings.
            "configured_plan": "unreviewed",
            "is_free": True,
            "authentication_required": True,
            "usage_terms": "MarketData.app plan, credits, and licensing terms require explicit account review.",
            "history_depth": "Free-plan endpoint dependent",
            "quota_policy": {
                "history_constraints": {
                    "max_lookback_years": 1,
                    "source": "https://www.marketdata.app/docs/account/free-accounts/",
                }
            },
            "venue_coverage": "Provider-supported US equities and options",
            "freshness_semantics": "Plan-dependent delayed/current data",
        },
        "finra": {
            "configured_plan": "public-dataset",
            "is_free": True,
            "authentication_required": True,
            "usage_terms": (
                "FINRA public Query API dataset; API credential, OAuth, usage limits, and "
                "dataset-specific terms apply. The current API Terms of Service restrict "
                "licensed materials to authorized users/permitted uses, prohibit bulk "
                "distributor or service-bureau use and non-API extraction, and do not "
                "grant redistribution by possession of a credential: "
                "https://developer.finra.org/finra-api-terms-service"
            ),
            "history_depth": "Publication-dependent short-interest history",
            "venue_coverage": "US securities covered by FINRA consolidated short interest",
            "freshness_semantics": "Periodic publication; not real-time",
        },
        "yfinance": {
            "configured_plan": "legacy-explicit",
            "is_free": True,
            "authentication_required": False,
            "usage_terms": "Personal-use legacy compatibility only; never an implicit workstation path.",
            "history_depth": "Legacy adapter dependent",
            "venue_coverage": "Legacy adapter dependent",
            "freshness_semantics": "Unofficial/delayed",
        },
        "xstocks": {
            "configured_plan": "public-read",
            "is_free": True,
            "authentication_required": False,
            "usage_terms": "Public API guide documents unauthenticated metadata reads and observed shared 1000/minute native headers are enforced. Public read access alone does not prove permission for automated continuous collection: current xStocks terms include automated-retrieval restrictions for the Site/Services and partner integrations are eligibility-reviewed. Keep non-routable until API-specific permission and deployment jurisdiction/data-use eligibility are established.",
            "history_depth": "Current metadata, price, supply, multiplier and corporate-action observations",
            "venue_coverage": "xStocks tokenized equities and ETFs across published chain deployments",
            "freshness_semantics": "Cached/current provider endpoint response",
        },
        "robinhood_tokens": {
            "configured_plan": "public-read",
            "is_free": True,
            "authentication_required": False,
            "usage_terms": "Public read-only Stock Token API; endpoint cache windows and 60 requests/second limit apply.",
            "history_depth": "Current assets, prices and processed corporate actions",
            "venue_coverage": "Robinhood Chain Stock Tokens",
            "freshness_semantics": "Cached live quote and issuer action response",
        },
        "bybit_xstocks": {
            "configured_plan": "public-market-data",
            "is_free": True,
            "authentication_required": False,
            "usage_terms": "Anonymous public market endpoints are bounded by the 600 requests per 5 seconds per IP outer limit. Separate rolling UID/endpoint limits apply to authenticated API traffic. Bybit restricts requests from U.S. and Mainland-China IP addresses.",
            "history_depth": "Current instrument and ticker metadata",
            "venue_coverage": "Bybit xStocks symbols",
            "freshness_semantics": "Public exchange endpoint response",
        },
        "gate_tradfi": {
            "configured_plan": "public-market-data",
            "is_free": True,
            "authentication_required": False,
            "usage_terms": "Gate public TradFi market-data endpoints; stock endpoint limits apply.",
            "history_depth": "Current symbols and order-book observations",
            "venue_coverage": "Gate TradFi/xStocks symbols",
            "freshness_semantics": "Public exchange endpoint response",
        },
        "kraken_xstocks": {
            "configured_plan": "public-market-data",
            "is_free": True,
            "authentication_required": False,
            "usage_terms": "Kraken public market-data endpoints and safe-frequency guidance apply. Kraken describes xStocks API access through its API Partner Program; public material reviewed does not establish a standalone read-only xStocks entitlement. EEA clients cannot access xStocks order-book trading through Kraken API; verify the actual environment and partner entitlement before claiming API availability (https://blog.kraken.com/product/api/kraken-api-partner-program-xstocks; https://support.kraken.com/articles/xstocks-availability).",
            "history_depth": "Current pair and ticker observations",
            "venue_coverage": "Kraken xStocks pairs only where exposed by the public API; the 2026-10-09 live AssetPairs read from Portugal returned no xStocks pairs, so asset/price API coverage is unproven for this region",
            "freshness_semantics": "Public exchange endpoint response",
        },
        "ondo_global_markets": {
            "configured_plan": "onboarding-required",
            "is_free": False,
            "authentication_required": True,
            "usage_terms": "Ondo Stocks API access requires onboarding and an API key; the OpenAPI documents HTTP 429 but no numeric quota. Price feeds are display-only, and jurisdiction/redistribution terms require review before routing.",
            "history_depth": "Published OHLC 1min-1day intervals with finite ranges through all history; adapter exposes metadata, current price, and OHLC.",
            "venue_coverage": "Ondo Global Markets tokenized US stocks and ETFs",
            "freshness_semantics": "Provider-dependent",
        },
        "ibkr": {
            "configured_plan": "account-session",
            "is_free": False,
            "authentication_required": True,
            "usage_terms": "IBKR account, market-data entitlements, and Client Portal Gateway session required.",
            "history_depth": "Up to the documented 15-year history-period parameter, subject to entitlements and endpoint bar limits.",
            "quota_policy": {
                "history_constraints": {
                    "max_lookback_years": 15,
                    "source": "https://ibkrcampus.com/docs/web-api/v1/endpoints/market-data/historical-market-data",
                }
            },
            "venue_coverage": "Account-entitled stocks, ETFs, options, futures, forex, and crypto instruments; adapter currently routes only generic metadata/history/latest price.",
            "freshness_semantics": "Gateway/session and exchange-entitlement dependent; no real-time guarantee.",
        },
        "dinari": {
            "configured_plan": "partner-access-required",
            "is_free": False,
            "authentication_required": True,
            "usage_terms": "Dinari Enterprise API requires partner API-key ID/secret and commercial/redistribution review; the published market-data API is best-effort and does not publish a numeric quota. US NBBO quote usage may incur a per-query fee and display-only restrictions.",
            "history_depth": "Published DAY/WEEK/MONTH/YEAR aggregate history; adapter exposes metadata, price, quote, and history.",
            "venue_coverage": "Dinari dShares tokenized US stocks and ETFs",
            "freshness_semantics": "Provider-dependent",
        },
        "alpaca_itn": {
            "configured_plan": "authorized-participant-required",
            "is_free": False,
            "authentication_required": True,
            "usage_terms": "Authorized-participant tokenization integration; not enabled by ordinary Alpaca market-data credentials.",
            "history_depth": "Provider-dependent",
            "venue_coverage": "Alpaca tokenization network products",
            "freshness_semantics": "Provider-dependent",
        },
    }
    # Provider-native bounded probe evidence. A configured credential and a
    # reviewed plan still do not admit a provider whose probe has not passed.
    PROVIDER_LIVE_PROBE_STATUS_SEEDS: dict[str, str] = {
        # Credentialed history/latest/assets/corporate-actions probes passed on
        # 2026-09-12; event cursors are now persisted and resumed page by page.
        "alpaca": "passed",
        "massive": "passed",
        "alpha_vantage": "passed",
        "openfigi": "passed",
        "edgar": "passed",
        "finra": "passed",
        "coingecko": "passed",
        "binance": "passed",
        "coinbase": "passed",
        "kraken": "passed",
        "nasdaq": "passed",
        "cta_plan": "not_run",
        "fred": "passed",
        "tiingo": "passed",
        "twelve_data": "passed",
        "finnhub": "passed",
        "marketstack": "passed",
        "eodhd": "passed",
        "fmp": "passed",
        "tradier": "not_run",
        # Credentialed daily/options probes passed on 2026-09-12; account-plan
        # and response-priced option-chain controls remain separate gates.
        "marketdata_app": "passed",
        "xstocks": "passed",
        "robinhood_tokens": "passed",
        "bybit_xstocks": "passed",
        "gate_tradfi": "passed",
        "kraken_xstocks": "passed",
        "ondo_global_markets": "not_run",
        # The replacement Sandbox credential pair passed the bounded compound
        # market-data probe on 2026-09-12; partner quota/terms review still
        # keeps this paid provider out of routing.
        "dinari": "passed",
        "alpaca_itn": "not_run",
        "ibkr": "not_run",
        "yfinance": "not_required",
    }
    OPENFIGI_API_KEY: str = ""
    OPENFIGI_TIMEOUT_SECONDS: float = 10.0
    MASSIVE_API_KEY: str = ""
    ALPHA_VANTAGE_API_KEY: str = ""
    # Alpha Vantage publishes the free-key 25-requests/day allowance but does
    # not publish a reset boundary/timezone. The seed enforces a rolling
    # 24-hour application envelope; these optional settings replace it only
    # when a future plan supplies provider-native reset evidence.
    ALPHA_VANTAGE_REVIEWED_RESET: str = ""
    ALPHA_VANTAGE_QUOTA_EVIDENCE: str = ""
    # Alpha Vantage grants personal/non-commercial platform use but the
    # reviewed terms do not explicitly cover this app's permanent provider
    # response archive or retention when access ends.
    ALPHA_VANTAGE_PERSISTENT_STORAGE_AUTHORIZED: bool = False
    ALPHA_VANTAGE_PERSISTENT_STORAGE_AUTHORITY_REFERENCE: str = ""
    ALPHA_VANTAGE_PERSISTENT_STORAGE_AUTHORITY_SCOPE: str = ""
    ALPHA_VANTAGE_PERSISTENT_STORAGE_REVIEWED_AT: datetime | None = None
    ALPHA_VANTAGE_PERSISTENT_STORAGE_EXPIRES_AT: datetime | None = None
    MARKETDATA_API_KEY: str = ""
    FMP_API_KEY: str = ""
    TIINGO_API_KEY: str = ""
    # FMP requires provider-written approval for copying/downloading content;
    # persistent application storage is not implied by the API key or plan.
    FMP_PERSISTENT_STORAGE_AUTHORIZED: bool = False
    FMP_PERSISTENT_STORAGE_AUTHORITY_REFERENCE: str = ""
    FMP_PERSISTENT_STORAGE_AUTHORITY_SCOPE: str = ""
    FMP_PERSISTENT_STORAGE_REVIEWED_AT: datetime | None = None
    FMP_PERSISTENT_STORAGE_EXPIRES_AT: datetime | None = None
    # Separate from owner consent: FMP's current terms require provider
    # permission before copying/downloading data into an application archive.
    FMP_PROVIDER_ARCHIVE_TERMS_AUTHORIZED: bool = False
    FMP_PROVIDER_ARCHIVE_TERMS_EVIDENCE: str = ""
    # Tiingo Starter/Trial explicitly prohibits durable storage. Standard paid
    # plans still require data deletion at plan end, so only written retention
    # rights that survive subscription termination admit the archive route.
    TIINGO_PERSISTENT_STORAGE_AUTHORIZED: bool = False
    TIINGO_PERSISTENT_STORAGE_AUTHORITY_REFERENCE: str = ""
    TIINGO_PERSISTENT_STORAGE_AUTHORITY_SCOPE: str = ""
    TIINGO_PERSISTENT_STORAGE_REVIEWED_AT: datetime | None = None
    TIINGO_PERSISTENT_STORAGE_EXPIRES_AT: datetime | None = None
    # Starter/Trial explicitly forbids durable storage; paid plans still
    # require deletion at plan end unless a separate agreement says otherwise.
    TIINGO_PROVIDER_ARCHIVE_TERMS_AUTHORIZED: bool = False
    TIINGO_PROVIDER_ARCHIVE_TERMS_EVIDENCE: str = ""
    # Twelve Data's public Terms make storage tier-limited and require data
    # deletion after expiration/termination. The app needs durable observations
    # and single-user display, so only an explicit written scope that survives
    # plan/account end can admit provider data into canonical storage.
    TWELVE_DATA_PERSISTENT_STORAGE_AUTHORIZED: bool = False
    TWELVE_DATA_PERSISTENT_STORAGE_AUTHORITY_REFERENCE: str = ""
    TWELVE_DATA_PERSISTENT_STORAGE_AUTHORITY_SCOPE: str = ""
    TWELVE_DATA_PERSISTENT_STORAGE_REVIEWED_AT: datetime | None = None
    TWELVE_DATA_PERSISTENT_STORAGE_EXPIRES_AT: datetime | None = None
    # Separate from owner consent: the reviewed self-service terms require
    # deleting downloaded data when subscription access ends.
    TWELVE_DATA_PROVIDER_ARCHIVE_TERMS_AUTHORIZED: bool = False
    TWELVE_DATA_PROVIDER_ARCHIVE_TERMS_EVIDENCE: str = ""
    # Tiingo does not publish per-response byte ceilings. These are explicit
    # application reservation budgets, not claims about Tiingo's API limits.
    # Historical requests are split into one calendar year each so one bound
    # never reserves an unbounded multi-decade response. Operators may tighten
    # or widen each operation independently; setting an empty/partial map
    # intentionally disables the bandwidth-constrained route.
    TIINGO_OPERATION_BYTE_BOUNDS: dict[str, int] = {
        "fetch_ohlcv": 1_048_576,
        "fetch_latest_ohlcv": 1_048_576,
        "get_current_price": 65_536,
        "bulk_fetch": 1_048_576,
        "search_instruments": 4_194_304,
        "get_instrument_profile": 1_048_576,
    }
    # The published Starter and Power plans have different quota pools. Keep
    # the selection explicit so a plan upgrade changes runtime admission
    # without code edits. Custom/enterprise accounts must provide every exact
    # quota and non-secret evidence; partial values remain fail-closed.
    TIINGO_REVIEWED_PLAN: str = "starter"
    TIINGO_CUSTOM_UNIQUE_SYMBOLS_PER_MONTH: int = 0
    TIINGO_CUSTOM_REQUESTS_PER_HOUR: int = 0
    TIINGO_CUSTOM_REQUESTS_PER_DAY: int = 0
    TIINGO_CUSTOM_BANDWIDTH_BYTES_PER_MONTH: int = 0
    TIINGO_CUSTOM_QUOTA_EVIDENCE: str = ""
    # Tiingo leaves the 500-unique-symbol reset anchor and 50/hour boundary
    # unspecified in the reviewed sources. The seed applies explicit,
    # provider-scoped rolling safety envelopes for both pools; these optional
    # settings replace them only with provider-native reset evidence.
    TIINGO_REVIEWED_UNIQUE_SYMBOL_RESET: str = ""
    TIINGO_REVIEWED_HOURLY_RESET: str = ""
    TIINGO_UNIQUE_SYMBOL_QUOTA_EVIDENCE: str = ""
    TIINGO_HOURLY_QUOTA_EVIDENCE: str = ""
    # FMP does not publish response-size ceilings. These per-response values
    # are explicit application reservation budgets, not vendor limits. The
    # history adapter partitions EOD into <=4,500 calendar-day requests and
    # the earnings adapter pages at the documented 4,000-row maximum; each
    # bound is multiplied by its exact planned request count before transport.
    # The full stock-list endpoint has no documented page parameter, so give
    # that one response a deliberately larger budget. An over-budget body is
    # retained intact in the private request archive and the operation fails;
    # it is never truncated or silently dropped.
    FMP_OPERATION_BYTE_BOUNDS: dict[str, int] = {
        "fetch_ohlcv": 1_048_576,
        "fetch_latest_ohlcv": 1_048_576,
        "get_current_price": 65_536,
        "bulk_fetch": 1_048_576,
        "get_instrument_profile": 262_144,
        "fetch_market_events": 8_388_608,
        "discover_universe_page": 33_554_432,
        "fetch_account_usage": 65_536,
    }
    # FMP's published personal-use tiers use different request pools and
    # trailing-30-day bandwidth limits. Keep the account's selected tier
    # configuration-only so a plan upgrade does not leave the Basic quota
    # hard-coded in the running application.
    FMP_REVIEWED_PLAN: str = "basic"
    # The configured Basic key returned HTTP 402 from the stable stock-list
    # endpoint. Keep universe discovery unavailable until this account's
    # endpoint entitlement is independently confirmed.
    FMP_STOCK_LIST_ENTITLED: bool = False
    # FMP publishes separate daily-call and trailing-30-day bandwidth pools,
    # but current first-party guidance does not promise a universal daily-call
    # reset time. Keep this provider-specific reset unset until account-side
    # evidence is reviewed; the override remains configurable for plan changes.
    FMP_REVIEWED_DAILY_RESET: str = ""
    FMP_REVIEWED_CALL_RESET: str = ""
    FMP_REVIEWED_BANDWIDTH_RESET: str = ""
    FMP_CALL_QUOTA_EVIDENCE: str = ""
    FMP_DAILY_QUOTA_EVIDENCE: str = ""
    FMP_BANDWIDTH_QUOTA_EVIDENCE: str = ""
    TWELVE_DATA_API_KEY: str = ""
    FINNHUB_API_KEY: str = ""
    # Finnhub publishes independent minute and second request ceilings. The
    # seed enforces separate rolling application envelopes for each pool; these
    # optional settings replace them only with provider-native evidence.
    FINNHUB_REVIEWED_MINUTE_RESET: str = ""
    FINNHUB_REVIEWED_SECOND_RESET: str = ""
    FINNHUB_MINUTE_QUOTA_EVIDENCE: str = ""
    FINNHUB_SECOND_QUOTA_EVIDENCE: str = ""
    # Public plans describe Finnhub access as personal-use and do not settle
    # this application's automated display or post-termination archive rights.
    FINNHUB_PERSISTENT_STORAGE_AUTHORIZED: bool = False
    FINNHUB_PERSISTENT_STORAGE_AUTHORITY_REFERENCE: str = ""
    FINNHUB_PERSISTENT_STORAGE_AUTHORITY_SCOPE: str = ""
    FINNHUB_PERSISTENT_STORAGE_REVIEWED_AT: datetime | None = None
    FINNHUB_PERSISTENT_STORAGE_EXPIRES_AT: datetime | None = None
    MARKETSTACK_API_KEY: str = ""
    # The published Free cap is 100/month; enforce a stricter rolling 30-day
    # safety window because the provider does not state its exact reset anchor.
    # Change the cap/reset only with current account-plan evidence.
    MARKETSTACK_REVIEWED_MONTHLY_LIMIT: int = 100
    MARKETSTACK_REVIEWED_MONTHLY_RESET: str = ""
    MARKETSTACK_QUOTA_EVIDENCE: str = ""
    # Marketstack documents per-ticker billing for symbol queries, but the
    # reviewed sources do not establish the charge for exchange-wide listing
    # pages. Keep discovery non-routable until that operation cost is evidenced.
    MARKETSTACK_DISCOVERY_MAX_PAGE_COST: int = 0
    MARKETSTACK_DISCOVERY_COST_EVIDENCE: str = ""
    # Marketstack's service licence terminates with the contract, prohibits
    # further Content use after termination, and its US feed is sourced from
    # Tiingo. Require written archive rights covering both providers.
    MARKETSTACK_PERSISTENT_STORAGE_AUTHORIZED: bool = False
    MARKETSTACK_PERSISTENT_STORAGE_AUTHORITY_REFERENCE: str = ""
    MARKETSTACK_PERSISTENT_STORAGE_AUTHORITY_SCOPE: str = ""
    MARKETSTACK_PERSISTENT_STORAGE_REVIEWED_AT: datetime | None = None
    MARKETSTACK_PERSISTENT_STORAGE_EXPIRES_AT: datetime | None = None
    # Vendor contract/upstream-feed restrictions, not owner data permission.
    MARKETSTACK_PROVIDER_ARCHIVE_TERMS_AUTHORIZED: bool = False
    MARKETSTACK_PROVIDER_ARCHIVE_TERMS_EVIDENCE: str = ""
    # Marketstack ticker discovery is venue-scoped. Do not silently default
    # to one exchange or claim a whole-US universe without operator scope.
    MARKETSTACK_DISCOVERY_EXCHANGE: str = ""
    EODHD_API_KEY: str = ""
    TRADIER_API_KEY: str = ""
    MARKETDATA_APP_API_KEY: str = ""
    # Self-service terms require downloaded data to be deleted when the
    # subscription ends. Canonical provider ingestion must not rely on the
    # account remaining active forever; written perpetual archive permission
    # is required before persistent routing.
    MARKETDATA_APP_PERSISTENT_STORAGE_AUTHORIZED: bool = False
    MARKETDATA_APP_PERSISTENT_STORAGE_AUTHORITY_REFERENCE: str = ""
    MARKETDATA_APP_PERSISTENT_STORAGE_AUTHORITY_SCOPE: str = ""
    MARKETDATA_APP_PERSISTENT_STORAGE_REVIEWED_AT: datetime | None = None
    MARKETDATA_APP_PERSISTENT_STORAGE_EXPIRES_AT: datetime | None = None
    # The published subscription terms require deletion when access ends.
    MARKETDATA_APP_PROVIDER_RETENTION_TERMS_AUTHORIZED: bool = False
    MARKETDATA_APP_PROVIDER_RETENTION_TERMS_EVIDENCE: str = ""
    # The owner has explicitly directed this private, single-user research
    # deployment to retain data and automate API access even where a provider's
    # contract terms would otherwise require separate written permission.
    # This records the operator's risk decision; it does not claim that a
    # provider granted an exception. Credentials, account entitlements, quota
    # limits, and geographic access restrictions remain independently enforced.
    # Final owner decision for this private, single-user deployment: provider
    # contract restrictions on private automation/retention are accepted as a
    # risk and must not be re-requested as approval. Entitlement, quota, and
    # geographic-access checks remain independent and fail closed.
    PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK: bool = True
    # MarketData.app exposes materially different credit pools by account
    # plan.  Keep the provider's public Free Forever seed conservative, but
    # require an operator-reviewed plan/limit pair before widening it to a
    # Starter or Trader account.  Quant/Prime use a different per-minute
    # contract and are intentionally not accepted by this daily-limit gate.
    MARKETDATA_APP_REVIEWED_PLAN: str = ""
    MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT: int = 0
    # Trial entitlements must carry an explicit timezone-aware expiry. A
    # missing/invalid expiry keeps trial capacity fail-closed; an elapsed,
    # valid expiry automatically falls back to Free Forever/100 daily credits.
    MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT: datetime | None = None
    # MarketData.app current option-chain responses are billed per returned
    # contract.  A chain call may therefore be admitted only when operations
    # supplies a positive, conservative maximum contract count for the exact
    # filters used by the caller.  Zero keeps option-chain routing
    # fail-closed; ordinary stock candles and expiration lookups are not
    # affected.
    MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS: int = 0
    XSTOCKS_API_KEY: str = ""
    # Optional per-environment override after current account-specific EODHD
    # headers establish the effective key limit. The reviewed documented
    # 1,000/minute cap is the default; any override must include its reset and
    # exact evidence reference.
    EODHD_REVIEWED_MINUTE_LIMIT: int = 0
    EODHD_REVIEWED_MINUTE_RESET: str = ""
    EODHD_MINUTE_QUOTA_EVIDENCE: str = ""
    # EODHD personal terms allow private storage/analysis but prohibit display;
    # require an explicit grant for this application's UI and archive lifetime.
    EODHD_PERSISTENT_STORAGE_AUTHORIZED: bool = False
    EODHD_PERSISTENT_STORAGE_AUTHORITY_REFERENCE: str = ""
    EODHD_PERSISTENT_STORAGE_AUTHORITY_SCOPE: str = ""
    EODHD_PERSISTENT_STORAGE_REVIEWED_AT: datetime | None = None
    EODHD_PERSISTENT_STORAGE_EXPIRES_AT: datetime | None = None
    # EODHD personal terms allow private analysis but prohibit data display.
    EODHD_PROVIDER_DISPLAY_TERMS_AUTHORIZED: bool = False
    EODHD_PROVIDER_DISPLAY_TERMS_EVIDENCE: str = ""
    # Retained for legacy deployments. The owner has authorized private,
    # single-user automated persistence; public xStocks read endpoints no
    # longer require separate terms or product-distribution jurisdiction flags.
    XSTOCKS_MARKET_DATA_USE_AUTHORIZED: bool = False
    XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE: str = ""
    XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE: str = ""
    XSTOCKS_MARKET_DATA_USE_REVIEWED_AT: datetime | None = None
    XSTOCKS_MARKET_DATA_USE_EXPIRES_AT: datetime | None = None
    XSTOCKS_MARKET_DATA_USE_JURISDICTION_AUTHORIZED: bool = False
    XSTOCKS_MARKET_DATA_USE_JURISDICTION_EVIDENCE: str = ""
    # Bybit's product/user trading eligibility does not gate this read-only
    # public market-data integration. Its published API IP restriction still
    # applies, so request-egress jurisdiction remains independently required.
    BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORIZED: bool = False
    BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE: str = ""
    BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE: str = ""
    BYBIT_XSTOCKS_MARKET_DATA_USE_REVIEWED_AT: datetime | None = None
    BYBIT_XSTOCKS_MARKET_DATA_USE_EXPIRES_AT: datetime | None = None
    BYBIT_XSTOCKS_MARKET_DATA_USE_USER_JURISDICTION_AUTHORIZED: bool = False
    BYBIT_XSTOCKS_MARKET_DATA_USE_USER_JURISDICTION_EVIDENCE: str = ""
    BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_AUTHORIZED: bool = False
    BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_EVIDENCE: str = ""
    DINARI_API_KEY_ID: str = ""
    DINARI_API_SECRET_KEY: str = ""
    # Dinari publishes no numeric Sandbox quota. Keep the profile empty by
    # default; a live canary needs a complete account-reviewed contract and
    # per-operation cost upper bounds supplied from a trusted environment.
    DINARI_SANDBOX_QUOTA_PROFILE: dict = {}
    # Dinari Sandbox is the safe default for the operator-provided Sandbox
    # credentials. Production keys must override this explicitly per
    # deployment; never infer an environment from the secret itself.
    DINARI_API_BASE_URL: str = "https://api-enterprise.sandbox.dinari.com/api/v2"
    ONDO_GLOBAL_MARKETS_API_KEY: str = ""
    IBKR_READ_ONLY_URL: str = ""
    IBKR_READ_ONLY_SESSION_COOKIE: str = ""
    IBKR_READ_ONLY_VERIFY_TLS: bool = True
    IBKR_READ_ONLY_TIMEOUT_SECONDS: float = 30.0
    # Optional symbol -> IBKR conid map.  It avoids an ambiguous security
    # search when a ticker is listed in multiple venues.  Values are provider
    # identifiers, not canonical platform identity keys.
    IBKR_CONID_MAP: dict[str, int] = {}
    COINBASE_API_KEY: str = ""
    # Coinbase terms bar use by an AI/automated system absent prior express
    # written consent and restrict redistribution. Keep all normal routes
    # blocked until the exact internal, persisted/automated use is reviewed.
    COINBASE_MARKET_DATA_USE_AUTHORIZED: bool = False
    COINBASE_MARKET_DATA_USE_AUTHORITY_REFERENCE: str = ""
    COINBASE_MARKET_DATA_USE_AUTHORITY_SCOPE: str = ""
    COINBASE_MARKET_DATA_USE_REVIEWED_AT: datetime | None = None
    COINBASE_MARKET_DATA_USE_EXPIRES_AT: datetime | None = None
    # The public Binance API documentation supports applications, automated
    # workflows, dashboards, and internal services, but the reviewed sources
    # do not expressly grant this application's permanent local archive rights.
    BINANCE_PERSISTENT_STORAGE_AUTHORIZED: bool = False
    BINANCE_PERSISTENT_STORAGE_AUTHORITY_REFERENCE: str = ""
    BINANCE_PERSISTENT_STORAGE_AUTHORITY_SCOPE: str = ""
    BINANCE_PERSISTENT_STORAGE_REVIEWED_AT: datetime | None = None
    BINANCE_PERSISTENT_STORAGE_EXPIRES_AT: datetime | None = None
    KRAKEN_API_KEY: str = ""
    # Kraken's API terms require prior written consent for third-party apps
    # interacting with its content. Keep both public market-data adapters
    # closed until this consent covers the single-user automated archive.
    KRAKEN_MARKET_DATA_USE_AUTHORIZED: bool = False
    KRAKEN_MARKET_DATA_USE_AUTHORITY_REFERENCE: str = ""
    KRAKEN_MARKET_DATA_USE_AUTHORITY_SCOPE: str = ""
    KRAKEN_MARKET_DATA_USE_REVIEWED_AT: datetime | None = None
    KRAKEN_MARKET_DATA_USE_EXPIRES_AT: datetime | None = None
    # Compatibility-only owner-storage fields; owner consent is already final.
    KRAKEN_PERSISTENT_STORAGE_AUTHORIZED: bool = False
    KRAKEN_PERSISTENT_STORAGE_AUTHORITY_REFERENCE: str = ""
    KRAKEN_PERSISTENT_STORAGE_AUTHORITY_SCOPE: str = ""
    KRAKEN_PERSISTENT_STORAGE_REVIEWED_AT: datetime | None = None
    KRAKEN_PERSISTENT_STORAGE_EXPIRES_AT: datetime | None = None
    # Robinhood Stock Token endpoints explicitly support portfolio-tracker
    # displays, but their license is revocable/terminable and does not grant
    # this application's permanent archive after access ends.
    ROBINHOOD_TOKENS_PERSISTENT_STORAGE_AUTHORIZED: bool = False
    ROBINHOOD_TOKENS_PERSISTENT_STORAGE_AUTHORITY_REFERENCE: str = ""
    ROBINHOOD_TOKENS_PERSISTENT_STORAGE_AUTHORITY_SCOPE: str = ""
    ROBINHOOD_TOKENS_PERSISTENT_STORAGE_REVIEWED_AT: datetime | None = None
    ROBINHOOD_TOKENS_PERSISTENT_STORAGE_EXPIRES_AT: datetime | None = None
    # Gate US permits API integrations and Content display while its API terms
    # are active; those terms terminate all licenses and require destruction
    # of received information on termination.
    GATE_TRADFI_PERSISTENT_STORAGE_AUTHORIZED: bool = False
    GATE_TRADFI_PERSISTENT_STORAGE_AUTHORITY_REFERENCE: str = ""
    GATE_TRADFI_PERSISTENT_STORAGE_AUTHORITY_SCOPE: str = ""
    GATE_TRADFI_PERSISTENT_STORAGE_REVIEWED_AT: datetime | None = None
    GATE_TRADFI_PERSISTENT_STORAGE_EXPIRES_AT: datetime | None = None
    # These optional adapters stay blocked until the account/partner and
    # upstream exchange rights cover an automated, durable archive.
    TRADIER_PERSISTENT_STORAGE_AUTHORIZED: bool = False
    TRADIER_PERSISTENT_STORAGE_AUTHORITY_REFERENCE: str = ""
    TRADIER_PERSISTENT_STORAGE_AUTHORITY_SCOPE: str = ""
    TRADIER_PERSISTENT_STORAGE_REVIEWED_AT: datetime | None = None
    TRADIER_PERSISTENT_STORAGE_EXPIRES_AT: datetime | None = None
    IBKR_PERSISTENT_STORAGE_AUTHORIZED: bool = False
    IBKR_PERSISTENT_STORAGE_AUTHORITY_REFERENCE: str = ""
    IBKR_PERSISTENT_STORAGE_AUTHORITY_SCOPE: str = ""
    IBKR_PERSISTENT_STORAGE_REVIEWED_AT: datetime | None = None
    IBKR_PERSISTENT_STORAGE_EXPIRES_AT: datetime | None = None
    ONDO_GLOBAL_MARKETS_PERSISTENT_STORAGE_AUTHORIZED: bool = False
    ONDO_GLOBAL_MARKETS_PERSISTENT_STORAGE_AUTHORITY_REFERENCE: str = ""
    ONDO_GLOBAL_MARKETS_PERSISTENT_STORAGE_AUTHORITY_SCOPE: str = ""
    ONDO_GLOBAL_MARKETS_PERSISTENT_STORAGE_REVIEWED_AT: datetime | None = None
    ONDO_GLOBAL_MARKETS_PERSISTENT_STORAGE_EXPIRES_AT: datetime | None = None
    # yfinance accesses Yahoo Finance through undocumented/nonofficial
    # endpoints. Yahoo's US terms prohibit automated data collection absent
    # prior express permission, so explicit legacy compatibility alone is not
    # a data-use grant.
    YFINANCE_PERSISTENT_STORAGE_AUTHORIZED: bool = False
    YFINANCE_PERSISTENT_STORAGE_AUTHORITY_REFERENCE: str = ""
    YFINANCE_PERSISTENT_STORAGE_AUTHORITY_SCOPE: str = ""
    YFINANCE_PERSISTENT_STORAGE_REVIEWED_AT: datetime | None = None
    YFINANCE_PERSISTENT_STORAGE_EXPIRES_AT: datetime | None = None
    # Alpaca Markets — US equity + crypto OHLCV, corporate actions, universe
    ALPACA_API_KEY: str = ""
    ALPACA_SECRET_KEY: str = ""
    # Alpaca's free/basic market-data license is personal/non-commercial and
    # does not expressly resolve permanent server-side archival/retention.
    # Keep data routes closed until the actual single-user or business scope is
    # covered by provider-specific written authority.
    ALPACA_PERSISTENT_STORAGE_AUTHORIZED: bool = False
    ALPACA_PERSISTENT_STORAGE_AUTHORITY_REFERENCE: str = ""
    ALPACA_PERSISTENT_STORAGE_AUTHORITY_SCOPE: str = ""
    ALPACA_PERSISTENT_STORAGE_REVIEWED_AT: datetime | None = None
    ALPACA_PERSISTENT_STORAGE_EXPIRES_AT: datetime | None = None
    ALPACA_DATA_FEED: str = "iex"  # "iex" (free) or "sip" (paid consolidated)
    # Optional plan-change overrides. The current Basic Trading API contract
    # is source-backed in the checked-in provider seed and is admitted from
    # the native response headers; these settings are only needed when an
    # operator changes the plan or its documented semantics.
    ALPACA_REVIEWED_RESET: str = ""
    ALPACA_QUOTA_EVIDENCE: str = ""
    # Paper accounts use the paper trading host for the authenticated assets
    # directory. Production credentials must opt into the live host explicitly;
    # market-data history/latest endpoints continue to use data.alpaca.markets.
    ALPACA_TRADING_BASE_URL: str = "https://paper-api.alpaca.markets/v2"
    # Corporate-actions responses are cursor-paginated. This is a per-job
    # fairness budget only; continuation state is persisted and requeued until
    # every page is ingested. It is never a permanent retention limit.
    # Compatibility-only setting retained for older deployments.  The adapter
    # and event worker follow every provider cursor; zero means no local page
    # cap and is the only safe default because a cap must never become a data
    # retention boundary.
    ALPACA_CORPORATE_ACTIONS_MAX_PAGES: int = 0
    ALPACA_CORPORATE_ACTIONS_START_DATE: str = "1900-01-01"
    # Massive's free Basic REST allowance is five requests/minute per
    # unsubscribed asset class. Reference/cross-asset endpoints use a separate
    # bucket whose numeric limit is not published; never copy the stock limit
    # onto that bucket without account-specific evidence. The reset boundary
    # and native current-use counter are also unpublished, so the client uses
    # a rolling 60-second safety window and durable reservations when a valid
    # reference limit is configured.
    MASSIVE_REVIEWED_RESET: str = ""
    MASSIVE_QUOTA_EVIDENCE: str = ""
    # Massive's split and dividend endpoints are independently cursor-paginated;
    # this bound applies to each endpoint and the runtime reserves twice it.
    MASSIVE_CORPORATE_ACTIONS_MAX_PAGES: int = 0
    # Massive's Individual Market Data Terms restrict use to personal display,
    # prohibit copying/non-display use absent express written consent, and
    # require deletion on account termination/restriction/suspension. Keep all
    # routes fail-closed until written authority covers the actual audience,
    # automated durable storage, and required retention/deletion behavior.
    MASSIVE_MARKET_DATA_USE_AUTHORIZED: bool = False
    MASSIVE_MARKET_DATA_USE_AUTHORITY_REFERENCE: str = ""
    MASSIVE_MARKET_DATA_USE_AUTHORITY_SCOPE: str = ""
    MASSIVE_MARKET_DATA_USE_REVIEWED_AT: datetime | None = None
    MASSIVE_MARKET_DATA_USE_EXPIRES_AT: datetime | None = None
    NASDAQ_USER_AGENT: str = "charting-platform market-data-universe"
    # Nasdaq Trader symbol-directory information is restricted to internal
    # non-commercial use unless separately licensed. The daily permanent
    # universe archive needs an explicit grant covering database retention.
    NASDAQ_DIRECTORY_PERSISTENT_STORAGE_AUTHORIZED: bool = False
    NASDAQ_DIRECTORY_PERSISTENT_STORAGE_AUTHORITY_REFERENCE: str = ""
    NASDAQ_DIRECTORY_PERSISTENT_STORAGE_AUTHORITY_SCOPE: str = ""
    NASDAQ_DIRECTORY_PERSISTENT_STORAGE_REVIEWED_AT: datetime | None = None
    NASDAQ_DIRECTORY_PERSISTENT_STORAGE_EXPIRES_AT: datetime | None = None
    # FRED (Federal Reserve Economic Data) — rates, macro, forex series
    FRED_API_KEY: str = ""
    # The provider-native enforcement scope is unpublished. The owner may use
    # the documented v1 ceiling with the app's shared per-key rolling cap;
    # account-specific overrides remain available when this flag is false.
    FRED_REVIEWED_LIMIT_SCOPE: str = ""
    FRED_REVIEWED_REQUESTS_PER_MINUTE: int = 0
    FRED_REVIEWED_QUOTA_EVIDENCE: str = ""
    FRED_REVIEWED_RESET: str = ""
    FRED_RESET_EVIDENCE: str = ""
    # FRED requires each user of an application to use their own API key.
    # This integration has only a server-configured key, so it may be admitted
    # only for an explicitly owner-only personal deployment until per-user
    # credentials and user-facing FRED terms are implemented.
    FRED_APPLICATION_USER_SCOPE: str = ""
    FRED_APPLICATION_USER_SCOPE_EVIDENCE: str = ""
    FRED_PERSISTED_STORAGE_AUTHORIZED: bool = False
    FRED_PERSISTED_STORAGE_AUTHORITY_EVIDENCE: str = ""
    FRED_AUTOMATED_USE_AUTHORIZED: bool = False
    FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE: str = ""
    FRED_SERIES_RIGHTS_EVIDENCE: dict[str, str] = {}
    # CoinGecko Demo credentials authorize only the selected API plan's
    # contract. Durable archival use requires explicit written authority that
    # covers automated collection, the intended audience, attribution, and
    # retention/deletion after access ends.
    COINGECKO_API_KEY: str = ""
    COINGECKO_REVIEWED_PLAN: str = "demo"
    COINGECKO_MARKET_DATA_USE_AUTHORIZED: bool = False
    COINGECKO_MARKET_DATA_USE_AUTHORITY_REFERENCE: str = ""
    COINGECKO_MARKET_DATA_USE_AUTHORITY_SCOPE: str = ""
    COINGECKO_MARKET_DATA_USE_REVIEWED_AT: datetime | None = None
    COINGECKO_MARKET_DATA_USE_EXPIRES_AT: datetime | None = None
    # SEC EDGAR — no key required; User-Agent identifies your app to SEC servers
    EDGAR_USER_AGENT: str = ""
    # SEC publishes the 10-requests/second ceiling but not a fixed reset
    # boundary. The seed enforces a rolling one-second application envelope;
    # these optional settings replace it only with native reviewed evidence.
    EDGAR_REVIEWED_RESET: str = ""
    EDGAR_QUOTA_EVIDENCE: str = ""
    FINRA_CLIENT_ID: str = ""
    FINRA_CLIENT_SECRET: str = ""
    FINRA_TOKEN_URL: str = "https://ews.fip.finra.org/fip/rest/ews/oauth2/access_token"
    # ORF security-master files use the separate TRAQS refresh-token flow;
    # Gateway client credentials above are not valid for this file API.
    FINRA_ORF_USERNAME: str = ""
    FINRA_ORF_REFRESH_TOKEN: str = ""
    FINRA_ORF_REFRESH_TOKEN_STATE_FILE: str = ""
    FINRA_ORF_TOKEN_URL: str = "https://apidownload.finratraqs.org/refresh"
    FINRA_API_BASE_URL: str = "https://api.finra.org"
    FINRA_SHORT_INTEREST_URL: str = ""
    FINRA_OTC_DAILY_LIST_URL: str = ""
    # The public FINRA Symbol Directory is backed by this official Query API
    # dataset. It uses the same public client credentials and quota pools as
    # the other FINRA Query API datasets. Separately entitled deployments may
    # still select ``finra_orf_security_master`` and configure the ORF pair.
    FINRA_OTC_SOURCE_KIND: str = "finra_otc_query_api"
    FINRA_OTC_SYMBOL_DIRECTORY_URL: str = (
        "https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster"
    )
    FINRA_OTC_INACTIVE_SECURITY_MASTER_URL: str = (
        "https://apidownload.finratraqs.org/DownloadHandler.ashx"
        "?action=DOWNLOAD&file=EQUITYMASTERIN&facility=ORF"
    )
    # Optional operation-cost overrides are retained for separately entitled
    # ORF delivery. Query API mode has an exact built-in two-request worst case
    # per logical page and settles to observed transport usage.
    FINRA_OTC_OPERATION_COSTS: dict[str, int] = {}
    # Source availability/authorization is independently gated by a non-secret
    # evidence reference. Terms, completeness, redistribution, and polling are
    # further separate reviews of the exact configured source.
    FINRA_OTC_SOURCE_REVIEWED: bool = False
    FINRA_OTC_SOURCE_EVIDENCE: str = ""
    # Must exactly identify the URL whose availability and rights were reviewed.
    FINRA_OTC_REVIEWED_SOURCE_URL: str = ""
    FINRA_OTC_REVIEWED_INACTIVE_SOURCE_URL: str = ""
    FINRA_OTC_TERMS_REVIEWED: bool = False
    FINRA_OTC_COMPLETENESS_REVIEWED: bool = False
    FINRA_OTC_REDISTRIBUTION_REVIEWED: bool = False
    FINRA_OTC_POLL_INTERVAL_SECONDS: int = 86400
    # Compatibility-only legacy fields. The owner granted global private
    # persistent-storage permission on 2026-10-05; these values are not read
    # by routing. FINRA source access, exact product terms, and third-party
    # CUSIP licensing remain separate controls.
    FINRA_OTC_PERSISTENT_STORAGE_AUTHORIZED: bool = False
    FINRA_OTC_PERSISTENT_STORAGE_AUTHORITY_REFERENCE: str = ""
    FINRA_OTC_PERSISTENT_STORAGE_AUTHORITY_SCOPE: str = ""
    FINRA_OTC_PERSISTENT_STORAGE_REVIEWED_AT: datetime | None = None
    FINRA_OTC_PERSISTENT_STORAGE_EXPIRES_AT: datetime | None = None
    # ORF rows may contain CUSIP only under a separate CGS license. Reject
    # non-empty CUSIP data unless that exact license is recorded.
    FINRA_ORF_CUSIP_LICENSED: bool = False
    FINRA_ORF_CUSIP_LICENSE_EVIDENCE: str = ""
    # Compatibility-only legacy fields. The owner granted global private
    # persistent-storage permission on 2026-10-05; these values are not read
    # by routing. FINRA API credentials, quotas, provider terms, and any
    # redistribution limits remain independent provider-side requirements.
    FINRA_EQUITY_DATA_USE_AUTHORIZED: bool = False
    FINRA_EQUITY_DATA_USE_AUTHORITY_REFERENCE: str = ""
    FINRA_EQUITY_DATA_USE_AUTHORITY_SCOPE: str = ""
    FINRA_EQUITY_DATA_USE_REVIEWED_AT: datetime | None = None
    FINRA_EQUITY_DATA_USE_EXPIRES_AT: datetime | None = None
    # Async FINRA results are provider-unbounded; keep zero until an
    # operator selects a safe per-download adapter bound. This does not make
    # the async capability routable without durable monthly accounting.
    FINRA_ASYNC_MAX_RESULT_BYTES: int = 0
    INSTRUMENT_DISCOVERY_PAGE_DELAY_SECONDS: float = 0.75
    INSTRUMENT_METADATA_DELAY_SECONDS: float = 1.0
    INSTRUMENT_IDENTIFIER_DELAY_SECONDS: float = 1.0
    INSTRUMENT_DAILY_METADATA_CAP: int = 750
    INSTRUMENT_DAILY_IDENTIFIER_CAP: int = 250
    # Process-local instrument-sync guard only. This is not an external
    # provider entitlement and is never copied into ProviderPolicy defaults.
    PROVIDER_MAX_CONCURRENCY: int = 2
    OPTION_CHAIN_REFRESH_HORIZON_DAYS: int = 45
    # Provider request logs are append-only quota/audit evidence. This legacy
    # setting remains readable for configuration compatibility, but
    # provider_maintenance deliberately ignores it for destructive deletion.
    PROVIDER_REQUEST_LOG_RETENTION_DAYS: int = 0
    # Optional read-only view of the direct live-probe usage ledger.  The
    # ledger is outside the application database and is never required for
    # routing; an absent/unmounted file is reported as unavailable.
    PROVIDER_LIVE_USAGE_LEDGER: str = ""
    # Non-secret environment/account label carried by direct live-test receipts
    # so operators cannot silently merge usage from different environments.
    PROVIDER_LIVE_USAGE_SCOPE: str = ""
    # Provider quota admission uses a separate durable coordinator so local
    # worktrees and direct live probes sharing a provider account do not each
    # receive a fresh copy of that account's allowance. Local development uses
    # an owner-only SQLite file; CI/multi-host deployments may point at a
    # separately provisioned PostgreSQL coordinator database. The URL may
    # contain credentials and must never be logged or copied into receipts.
    PROVIDER_QUOTA_LEDGER_PATH: str = "~/.config/charting-platform/provider-quota/usage.sqlite3"
    PROVIDER_QUOTA_LEDGER_DATABASE_URL: str = ""
    # Keep settled per-window diagnostics for a bounded period. Pending and
    # ambiguous reservations are never pruned automatically.
    PROVIDER_QUOTA_LEDGER_RETENTION_DAYS: int = 180
    # Non-secret aliases identify the provider account/key/IP scope that owns
    # each native quota. Matching aliases share usage; distinct aliases isolate
    # genuinely separate accounts. Empty mappings use a provider-specific
    # default alias, never an API-key-derived value.
    PROVIDER_QUOTA_ACCOUNT_SCOPES: dict[str, str] = {}
    # A scope may be marked exclusive only when every caller of that provider
    # account uses this same durable coordinator. This permits safe zero-based
    # rollover after a verified starting baseline; it is not a rate-limit
    # policy and must not be enabled for accounts used by uncoordinated clients.
    PROVIDER_QUOTA_EXCLUSIVE_ACCOUNT_SCOPES: dict[str, bool] = {}
    # Crash recovery releases only in-flight concurrency reservations. This is
    # added to each adapter's documented transport timeout and is not an API
    # rate/cooldown assumption.
    PROVIDER_QUOTA_CONCURRENCY_LEASE_GRACE_SECONDS: int = 10
    # Provider observations are append-only evidence and are never pruned.
    # These legacy settings remain readable for configuration compatibility,
    # but provider_maintenance deliberately ignores them for destructive
    # deletion; only operational request logs may be retention-pruned.
    LATEST_PRICE_SNAPSHOT_RETENTION_DAYS: int = 0
    INSTRUMENT_SEARCH_SNAPSHOT_RETENTION_DAYS: int = 0
    UNIVERSE_DISCOVERY_SNAPSHOT_RETENTION_DAYS: int = 0
    INSTRUMENT_PROFILE_SNAPSHOT_RETENTION_DAYS: int = 0
    INSTRUMENT_IDENTIFIER_SNAPSHOT_RETENTION_DAYS: int = 0
    PROVIDER_SUPPORT_SUPPORTED_TTL_SECONDS: int = 2592000
    PROVIDER_SUPPORT_UNSUPPORTED_TTL_SECONDS: int = 604800
    RFR_INSTRUMENT_SYMBOL: str = "^IRX"
    RFR_INSTRUMENT_NAME: str = "US 3-Month T-Bill Rate"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        # Preserve pydantic-settings 2.2.1's source configuration while
        # bypassing its eager JSON decoding for our exact non-JSON sentinel.
        env_source = _EnvironmentSettingsSource(
            settings_cls,
            case_sensitive=env_settings.case_sensitive,
            env_prefix=env_settings.env_prefix,
            env_nested_delimiter=env_settings.env_nested_delimiter,
            env_ignore_empty=env_settings.env_ignore_empty,
            env_parse_none_str=env_settings.env_parse_none_str,
        )
        dotenv_source = _DotEnvSettingsSource(
            settings_cls,
            env_file=dotenv_settings.env_file,
            env_file_encoding=dotenv_settings.env_file_encoding,
            case_sensitive=dotenv_settings.case_sensitive,
            env_prefix=dotenv_settings.env_prefix,
            env_nested_delimiter=dotenv_settings.env_nested_delimiter,
            env_ignore_empty=dotenv_settings.env_ignore_empty,
            env_parse_none_str=dotenv_settings.env_parse_none_str,
        )
        return init_settings, env_source, dotenv_source, file_secret_settings

    @field_validator("IDENTIFIER_PROVIDER_PRIORITY", mode="before")
    @classmethod
    def parse_identifier_provider_priority(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator("TOKENIZED_PROVIDER_PRIORITY", mode="before")
    @classmethod
    def parse_tokenized_provider_priority(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator("MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT", mode="before")
    @classmethod
    def parse_optional_marketdata_trial_expiry(cls, v):
        # Compose and GitHub environment mappings deliberately pass an empty
        # value when no trial entitlement has been reviewed. Treat that as
        # unset so Settings can boot and the routing layer can fail closed.
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator(
        "COINBASE_MARKET_DATA_USE_REVIEWED_AT",
        "COINBASE_MARKET_DATA_USE_EXPIRES_AT",
        "KRAKEN_MARKET_DATA_USE_REVIEWED_AT",
        "KRAKEN_MARKET_DATA_USE_EXPIRES_AT",
        "XSTOCKS_MARKET_DATA_USE_REVIEWED_AT",
        "XSTOCKS_MARKET_DATA_USE_EXPIRES_AT",
        "BYBIT_XSTOCKS_MARKET_DATA_USE_REVIEWED_AT",
        "BYBIT_XSTOCKS_MARKET_DATA_USE_EXPIRES_AT",
        "MASSIVE_MARKET_DATA_USE_REVIEWED_AT",
        "MASSIVE_MARKET_DATA_USE_EXPIRES_AT",
        "FINRA_EQUITY_DATA_USE_REVIEWED_AT",
        "FINRA_EQUITY_DATA_USE_EXPIRES_AT",
        "FINRA_OTC_PERSISTENT_STORAGE_REVIEWED_AT",
        "FINRA_OTC_PERSISTENT_STORAGE_EXPIRES_AT",
        "FMP_PERSISTENT_STORAGE_REVIEWED_AT",
        "FMP_PERSISTENT_STORAGE_EXPIRES_AT",
        "TIINGO_PERSISTENT_STORAGE_REVIEWED_AT",
        "TIINGO_PERSISTENT_STORAGE_EXPIRES_AT",
        "TWELVE_DATA_PERSISTENT_STORAGE_REVIEWED_AT",
        "TWELVE_DATA_PERSISTENT_STORAGE_EXPIRES_AT",
        "MARKETDATA_APP_PERSISTENT_STORAGE_REVIEWED_AT",
        "MARKETDATA_APP_PERSISTENT_STORAGE_EXPIRES_AT",
        "ROBINHOOD_TOKENS_PERSISTENT_STORAGE_REVIEWED_AT",
        "ROBINHOOD_TOKENS_PERSISTENT_STORAGE_EXPIRES_AT",
        "GATE_TRADFI_PERSISTENT_STORAGE_REVIEWED_AT",
        "GATE_TRADFI_PERSISTENT_STORAGE_EXPIRES_AT",
        "TRADIER_PERSISTENT_STORAGE_REVIEWED_AT",
        "TRADIER_PERSISTENT_STORAGE_EXPIRES_AT",
        "IBKR_PERSISTENT_STORAGE_REVIEWED_AT",
        "IBKR_PERSISTENT_STORAGE_EXPIRES_AT",
        "ONDO_GLOBAL_MARKETS_PERSISTENT_STORAGE_REVIEWED_AT",
        "ONDO_GLOBAL_MARKETS_PERSISTENT_STORAGE_EXPIRES_AT",
        "YFINANCE_PERSISTENT_STORAGE_REVIEWED_AT",
        "YFINANCE_PERSISTENT_STORAGE_EXPIRES_AT",
        mode="before",
    )
    @classmethod
    def parse_optional_market_data_use_authority_timestamps(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator(
        "OPTION_QUOTE_HISTORY_PROVIDER_PRIORITY",
        "PROVIDER_CHAIN_SEEDS",
        "PROVIDER_RATE_LIMIT_SEEDS",
        "PROVIDER_FRESHNESS_SEEDS",
        "PROVIDER_USAGE_PROFILE_SEEDS",
        "PROVIDER_CHECKPOINT_OPERATION_HOLDS",
        "DINARI_SANDBOX_QUOTA_PROFILE",
        "PROVIDER_QUOTA_ACCOUNT_SCOPES",
        "PROVIDER_QUOTA_EXCLUSIVE_ACCOUNT_SCOPES",
        "PROVIDER_LIVE_PROBE_STATUS_SEEDS",
        "PROVIDER_ACCOUNT_USAGE_REFRESH_PROVIDERS",
        "TIINGO_OPERATION_BYTE_BOUNDS",
        "FMP_OPERATION_BYTE_BOUNDS",
        "FINRA_OTC_OPERATION_COSTS",
        "IBKR_CONID_MAP",
        "FRED_SERIES_RIGHTS_EVIDENCE",
        mode="before",
    )
    @classmethod
    def parse_jsonish(cls, v):
        if isinstance(v, str):
            # Compose uses an explicit sentinel when an optional JSON override
            # is absent. Preserve the reviewed in-code seed; an explicit ``{}``
            # remains a deliberate empty override that can quarantine routes.
            if v.strip() == _SETTINGS_USE_CODE_DEFAULT:
                raise PydanticUseDefault
            return json.loads(v)
        return v

    @field_validator("PROVIDER_CHECKPOINT_OPERATION_HOLDS")
    @classmethod
    def validate_provider_checkpoint_operation_holds(cls, value):
        """Reject ambiguous hold maps at startup instead of failing open."""

        for provider_name, operation_holds in value.items():
            if not str(provider_name).strip() or not isinstance(operation_holds, dict):
                raise ValueError("provider checkpoint hold entries must be named mappings")
            for operation, reason in operation_holds.items():
                if not str(operation).strip() or not str(reason).strip():
                    raise ValueError(
                        "provider checkpoint hold operation and reason must be non-empty"
                    )
        return value

    model_config = SettingsConfigDict(
        env_file=os.environ.get("ENV_FILE", ".env.dev"),
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()


_BYTE_BOUND_OPERATIONS: dict[str, tuple[str, ...]] = {
    "tiingo": (
        "fetch_ohlcv",
        "fetch_latest_ohlcv",
        "get_current_price",
        "bulk_fetch",
        "search_instruments",
        "get_instrument_profile",
    ),
    "fmp": (
        "fetch_ohlcv",
        "fetch_latest_ohlcv",
        "get_current_price",
        "bulk_fetch",
        "get_instrument_profile",
        "fetch_market_events",
        "discover_universe_page",
        "fetch_account_usage",
    ),
}

_MARKETDATA_APP_DAILY_CREDIT_LIMITS: dict[str, int] = {
    "free_forever": 100,
    "starter": 10_000,
    "trader": 100_000,
    # The provider exposes separate 30-day trial plans whose daily credit
    # pools match their named paid plans. Keep them distinct so an operator
    # cannot mistake a time-limited trial for perpetual entitlement.
    "starter_trial": 10_000,
    "trader_trial": 100_000,
}

FRED_MAPPED_SERIES_IDS = frozenset(
    {
        "DTB3",
        "DGS5",
        "DGS10",
        "DGS30",
        "FEDFUNDS",
        "DEXUSEU",
        "DEXUSUK",
        "DEXJPUS",
        "DEXCAUS",
        "DEXMXUS",
        "DEXSZUS",
        "DEXUSAL",
        "DEXCHUS",
        "CPIAUCSL",
        "UNRATE",
        "GDP",
        "T10YIE",
        "VIXCLS",
        "DCOILWTICO",
    }
)


def provider_required_operation_byte_bounds(provider_name: str) -> tuple[str, ...]:
    """Return the complete reviewed byte-bound operation set for a provider."""

    return _BYTE_BOUND_OPERATIONS.get(provider_name, ())


def provider_positive_integer(value: object) -> int | None:
    """Return a reviewed positive integer without coercing booleans or floats."""

    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


_KNOWN_PROVIDER_QUOTA_RESETS = frozenset(
    {
        "09:30 America/New_York",
        "15:00 America/New_York",
        "15:00 UTC-05:00",
        "calendar_day_est",
        "calendar_day_gmt",
        "calendar_day_utc",
        "calendar_month",
        "calendar_month_est",
        "calendar_month_utc",
        "fixed_second",
        "fixed_minute",
        "per_dimension",
        "provider_defined",
        "provider_defined_daily",
        "provider_defined_minute_and_rolling_second",
        "rolling",
        "rolling_30_days",
        "rolling_31_days",
        "rolling_or_provider_defined",
    }
)

_UNRESOLVED_PROVIDER_QUOTA_RESETS = frozenset(
    {
        "per_dimension",
        "provider_defined",
        "provider_defined_daily",
        "provider_defined_minute_and_rolling_second",
        "rolling_or_provider_defined",
    }
)


def provider_quota_reset_is_known(value: object) -> bool:
    """Return whether a quota reset name has reviewed window semantics.

    A non-empty reset label is not enough: the coordinator must know which
    boundary to calculate.  New provider-specific reset semantics must be
    added to this reviewed set before they can participate in routing; an
    unknown label therefore remains non-routable instead of silently becoming
    an invented fixed window.
    """

    candidate = str(value or "").strip()
    return candidate in _KNOWN_PROVIDER_QUOTA_RESETS


def provider_quota_reset_is_admission_safe(value: object) -> bool:
    """Return whether a reset label identifies a calculable boundary.

    ``provider_defined`` is intentionally a valid audit/schema label, but it
    is not a runtime window.  The provider must either document the boundary
    or an operator must replace it with an explicit calendar/fixed/rolling
    contract before reservation code may calculate a window.
    """

    candidate = str(value or "").strip()
    return (
        provider_quota_reset_is_known(candidate)
        and candidate not in _UNRESOLVED_PROVIDER_QUOTA_RESETS
    )


def provider_quota_admission_reset(provider_reset: object, safety_reset: object = "") -> str:
    """Return the reset label the coordinator may safely calculate.

    A provider may publish an exact numeric ceiling without publishing the
    enforcement boundary.  In that case a contract can retain the
    provider-facing ``provider_defined`` label for audit while declaring an
    explicit, provider-scoped application safety envelope (for example,
    ``rolling``).  No global fallback is implied: the safety label must be
    present in that individual provider dimension and must itself be one of
    the reviewed calculable reset models.
    """

    primary = str(provider_reset or "").strip()
    if provider_quota_reset_is_admission_safe(primary):
        return primary
    safety = str(safety_reset or "").strip()
    if provider_quota_reset_is_admission_safe(safety):
        return safety
    return primary


def marketdata_app_reviewed_plan_pair() -> tuple[str, int] | None:
    """Return the exact operator-reviewed plan/limit pair, without expiry."""

    plan = str(getattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "") or "").strip().lower()
    expected_limit = _MARKETDATA_APP_DAILY_CREDIT_LIMITS.get(plan)
    configured_limit = provider_positive_integer(
        getattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 0)
    )
    if expected_limit is None or configured_limit != expected_limit:
        return None
    return plan, expected_limit


def _marketdata_app_policy_now_utc() -> datetime:
    """Clock seam for precise plan-expiry boundaries and deterministic tests."""

    return datetime.now(UTC)


def marketdata_app_trial_expiry_is_valid(plan: str) -> bool:
    """Return whether a trial plan has a future timezone-aware expiry."""

    if not plan.endswith("_trial"):
        return True
    expires_at = getattr(settings, "MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT", None)
    return bool(
        isinstance(expires_at, datetime)
        and expires_at.tzinfo is not None
        and expires_at.astimezone(UTC) > _marketdata_app_policy_now_utc()
    )


def marketdata_app_trial_expiry_has_elapsed() -> bool:
    """Return whether a configured, timezone-aware trial expiry is in the past."""

    expires_at = getattr(settings, "MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT", None)
    return bool(
        isinstance(expires_at, datetime)
        and expires_at.tzinfo is not None
        and expires_at.astimezone(UTC) <= _marketdata_app_policy_now_utc()
    )


def marketdata_app_reviewed_plan() -> tuple[str, int] | None:
    """Return a documented MarketData.app daily plan only when reviewed.

    The provider's response headers describe the current account entitlement,
    but a runtime observation must not silently rewrite durable policy.  An
    operator therefore records both the named plan and its documented daily
    credit limit.  Requiring the exact pair prevents a typo or an expired
    trial entitlement from widening admission by accident.
    """

    reviewed_pair = marketdata_app_reviewed_plan_pair()
    if reviewed_pair is None:
        return None
    plan, _ = reviewed_pair
    if not plan.endswith("_trial"):
        return reviewed_pair
    if marketdata_app_trial_expiry_is_valid(plan):
        return reviewed_pair
    if marketdata_app_trial_expiry_has_elapsed():
        # Trial capacity is temporary. When the configured trial window ends,
        # automatically fall back to the documented Free Forever pool rather
        # than either retaining 10k/100k credits or disabling this provider.
        return "free_forever", _MARKETDATA_APP_DAILY_CREDIT_LIMITS["free_forever"]
    # A trial without an explicit, valid end time is not an entitlement.
    return None


def provider_reviewed_flag(value: object) -> bool:
    """Accept only an actual boolean ``True`` for operator review gates."""

    return isinstance(value, bool) and value


def provider_terms_exception_missing(
    authorized_name: str, evidence_name: str, *, source: object | None = None
) -> list[str]:
    """Check a terms gate, honoring the owner's explicit private-use decision."""
    source = source or settings
    if provider_reviewed_flag(getattr(source, "PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", False)):
        return []
    missing: list[str] = []
    if not provider_reviewed_flag(getattr(source, authorized_name, False)):
        missing.append(authorized_name)
    if not str(getattr(source, evidence_name, "") or "").strip():
        missing.append(evidence_name)
    return missing


def provider_contract_exception_missing(prefix: str, *, source: object | None = None) -> list[str]:
    """Require evidence only where published provider terms block this use.

    The owner globally authorized private persistent storage. This separate
    control records a provider-contract exception, not owner consent.
    """

    return provider_terms_exception_missing(
        f"{prefix}_PROVIDER_ARCHIVE_TERMS_AUTHORIZED",
        f"{prefix}_PROVIDER_ARCHIVE_TERMS_EVIDENCE",
        source=source,
    )


def eodhd_provider_display_terms_missing(*, source: object | None = None) -> list[str]:
    """Require provider permission because the personal plan prohibits display."""

    return provider_terms_exception_missing(
        "EODHD_PROVIDER_DISPLAY_TERMS_AUTHORIZED",
        "EODHD_PROVIDER_DISPLAY_TERMS_EVIDENCE",
        source=source,
    )


def coingecko_market_data_use_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Require written permission for the Demo API's durable archive use.

    The free Demo plan is presented for testing/exploration and requires
    attribution. The API terms also require stored data to be deleted when
    access terminates. A key or self-attestation is therefore not authority
    for this application's persistent archive; written permission must cover
    collection, audience, attribution, and the retention/deletion behavior.
    """

    now = now or datetime.now(UTC)
    source = source or settings
    if provider_reviewed_flag(getattr(source, "PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", False)):
        return []
    missing: list[str] = []
    if not provider_reviewed_flag(getattr(source, "COINGECKO_MARKET_DATA_USE_AUTHORIZED", False)):
        missing.append("COINGECKO_MARKET_DATA_USE_AUTHORIZED")
    if not str(getattr(source, "COINGECKO_MARKET_DATA_USE_AUTHORITY_REFERENCE", "") or "").strip():
        missing.append("COINGECKO_MARKET_DATA_USE_AUTHORITY_REFERENCE")
    if (
        str(getattr(source, "COINGECKO_MARKET_DATA_USE_AUTHORITY_SCOPE", "") or "").strip()
        != "written_api_use_archive_audience_attribution_and_retention_after_termination"
    ):
        missing.append("COINGECKO_MARKET_DATA_USE_AUTHORITY_SCOPE")
    reviewed_at = getattr(source, "COINGECKO_MARKET_DATA_USE_REVIEWED_AT", None)
    if not isinstance(reviewed_at, datetime) or reviewed_at.tzinfo is None:
        missing.append("COINGECKO_MARKET_DATA_USE_REVIEWED_AT")
    elif reviewed_at > now:
        missing.append("COINGECKO_MARKET_DATA_USE_REVIEWED_AT")
    expires_at = getattr(source, "COINGECKO_MARKET_DATA_USE_EXPIRES_AT", None)
    if expires_at is not None:
        if not isinstance(expires_at, datetime) or expires_at.tzinfo is None:
            missing.append("COINGECKO_MARKET_DATA_USE_EXPIRES_AT")
        elif expires_at <= now:
            missing.append("COINGECKO_MARKET_DATA_USE_EXPIRES_AT")
    return missing


def coinbase_market_data_use_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Require current written authority covering AI automation and archive use."""

    now = now or datetime.now(UTC)
    source = source or settings
    if provider_reviewed_flag(getattr(source, "PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", False)):
        return []
    missing: list[str] = []
    if not provider_reviewed_flag(getattr(source, "COINBASE_MARKET_DATA_USE_AUTHORIZED", False)):
        missing.append("COINBASE_MARKET_DATA_USE_AUTHORIZED")
    if not str(getattr(source, "COINBASE_MARKET_DATA_USE_AUTHORITY_REFERENCE", "") or "").strip():
        missing.append("COINBASE_MARKET_DATA_USE_AUTHORITY_REFERENCE")
    if (
        str(getattr(source, "COINBASE_MARKET_DATA_USE_AUTHORITY_SCOPE", "") or "").strip()
        != "internal_ai_automated_persistent_nonredistributed"
    ):
        missing.append("COINBASE_MARKET_DATA_USE_AUTHORITY_SCOPE")
    reviewed_at = getattr(source, "COINBASE_MARKET_DATA_USE_REVIEWED_AT", None)
    if not isinstance(reviewed_at, datetime) or reviewed_at.tzinfo is None:
        missing.append("COINBASE_MARKET_DATA_USE_REVIEWED_AT")
    elif reviewed_at > now:
        missing.append("COINBASE_MARKET_DATA_USE_REVIEWED_AT")
    expires_at = getattr(source, "COINBASE_MARKET_DATA_USE_EXPIRES_AT", None)
    if expires_at is not None:
        if not isinstance(expires_at, datetime) or expires_at.tzinfo is None:
            missing.append("COINBASE_MARKET_DATA_USE_EXPIRES_AT")
        elif expires_at <= now:
            missing.append("COINBASE_MARKET_DATA_USE_EXPIRES_AT")
    return missing


def kraken_market_data_use_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Require Kraken's prior written consent for this automated third-party app."""

    now = now or datetime.now(UTC)
    source = source or settings
    if provider_reviewed_flag(getattr(source, "PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", False)):
        return []
    missing: list[str] = []
    if not provider_reviewed_flag(getattr(source, "KRAKEN_MARKET_DATA_USE_AUTHORIZED", False)):
        missing.append("KRAKEN_MARKET_DATA_USE_AUTHORIZED")
    if not str(getattr(source, "KRAKEN_MARKET_DATA_USE_AUTHORITY_REFERENCE", "") or "").strip():
        missing.append("KRAKEN_MARKET_DATA_USE_AUTHORITY_REFERENCE")
    if (
        str(getattr(source, "KRAKEN_MARKET_DATA_USE_AUTHORITY_SCOPE", "") or "").strip()
        != "single_user_personal_automated_internal_persistent_archive_nonredistributed"
    ):
        missing.append("KRAKEN_MARKET_DATA_USE_AUTHORITY_SCOPE")
    reviewed_at = getattr(source, "KRAKEN_MARKET_DATA_USE_REVIEWED_AT", None)
    if not isinstance(reviewed_at, datetime) or reviewed_at.tzinfo is None:
        missing.append("KRAKEN_MARKET_DATA_USE_REVIEWED_AT")
    elif reviewed_at > now:
        missing.append("KRAKEN_MARKET_DATA_USE_REVIEWED_AT")
    expires_at = getattr(source, "KRAKEN_MARKET_DATA_USE_EXPIRES_AT", None)
    if expires_at is not None:
        if not isinstance(expires_at, datetime) or expires_at.tzinfo is None:
            missing.append("KRAKEN_MARKET_DATA_USE_EXPIRES_AT")
        elif expires_at <= now:
            missing.append("KRAKEN_MARKET_DATA_USE_EXPIRES_AT")
    return missing


def massive_market_data_use_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Require written rights for Massive's automated persistent archive.

    The current Individual Market Data Terms limit the grant to personal,
    non-business/non-commercial display use; they prohibit copying and
    non-display use absent express written consent and require deletion if the
    account is terminated, restricted, or suspended. A key or self-attestation
    does not authorize the feature's durable data model. The recorded written
    authority must cover the actual audience, persistent storage, and the
    retention/deletion obligation.
    """

    now = now or datetime.now(UTC)
    source = source or settings
    if provider_reviewed_flag(getattr(source, "PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", False)):
        return []
    missing: list[str] = []
    if not provider_reviewed_flag(getattr(source, "MASSIVE_MARKET_DATA_USE_AUTHORIZED", False)):
        missing.append("MASSIVE_MARKET_DATA_USE_AUTHORIZED")
    if not str(getattr(source, "MASSIVE_MARKET_DATA_USE_AUTHORITY_REFERENCE", "") or "").strip():
        missing.append("MASSIVE_MARKET_DATA_USE_AUTHORITY_REFERENCE")
    if (
        str(getattr(source, "MASSIVE_MARKET_DATA_USE_AUTHORITY_SCOPE", "") or "").strip()
        != "written_automated_persistent_archive_and_audience"
    ):
        missing.append("MASSIVE_MARKET_DATA_USE_AUTHORITY_SCOPE")
    reviewed_at = getattr(source, "MASSIVE_MARKET_DATA_USE_REVIEWED_AT", None)
    if not isinstance(reviewed_at, datetime) or reviewed_at.tzinfo is None:
        missing.append("MASSIVE_MARKET_DATA_USE_REVIEWED_AT")
    elif reviewed_at > now:
        missing.append("MASSIVE_MARKET_DATA_USE_REVIEWED_AT")
    expires_at = getattr(source, "MASSIVE_MARKET_DATA_USE_EXPIRES_AT", None)
    if expires_at is not None:
        if not isinstance(expires_at, datetime) or expires_at.tzinfo is None:
            missing.append("MASSIVE_MARKET_DATA_USE_EXPIRES_AT")
        elif expires_at <= now:
            missing.append("MASSIVE_MARKET_DATA_USE_EXPIRES_AT")
    return missing


def finra_equity_data_use_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Compatibility shim: the owner approved private persistent storage.

    FINRA's published Equity Data terms already allow internal non-commercial
    personal or professional use and impose no special retention condition.
    The application currently does not redistribute FINRA data. Keep actual
    credentials, quotas, and endpoint access checks independent of this shim.
    """

    del now, source
    return []


def finra_otc_persistent_storage_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Compatibility shim; global private-storage approval is final."""

    del now, source
    return []


def fmp_persistent_storage_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Compatibility name; private persistence has global owner approval."""

    del now, source
    return []


def _provider_written_archive_authority_missing(
    provider: str,
    *,
    allowed_scopes: set[str],
    now: datetime | None = None,
    source: object | None = None,
) -> list[str]:
    """No per-provider owner attestation is required for private persistence.

    The owner granted this globally on 2026-10-05. Provider access, quotas,
    and explicit restrictions in provider/embedded-data terms remain separate
    routing facts and are checked by their own controls.
    """

    del provider, allowed_scopes, now, source
    return []


def alpaca_persistent_storage_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Compatibility shim; global private-storage approval is final."""

    return _provider_written_archive_authority_missing(
        "alpaca",
        allowed_scopes={
            "written_single_user_automated_internal_display_perpetual_archive",
            "written_licensed_business_automated_internal_display_perpetual_archive",
        },
        now=now,
        source=source,
    )


def alpha_vantage_persistent_storage_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Compatibility shim; global private-storage approval is final."""

    return _provider_written_archive_authority_missing(
        "alpha_vantage",
        allowed_scopes={
            "written_single_user_automated_internal_display_perpetual_archive",
            "written_licensed_business_automated_internal_display_perpetual_archive",
        },
        now=now,
        source=source,
    )


def nasdaq_directory_persistent_storage_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Compatibility name; private persistence has global owner approval."""

    del now, source
    return []


def finnhub_persistent_storage_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Compatibility shim; global private-storage approval is final."""

    return _provider_written_archive_authority_missing(
        "finnhub",
        allowed_scopes={
            "written_single_user_automated_internal_display_perpetual_archive",
            "written_licensed_business_internal_display_perpetual_archive",
        },
        now=now,
        source=source,
    )


def binance_persistent_storage_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Compatibility shim; global private-storage approval is final."""

    return _provider_written_archive_authority_missing(
        "binance",
        allowed_scopes={
            "written_single_user_automated_internal_display_perpetual_archive",
            "written_licensed_business_automated_internal_display_perpetual_archive",
        },
        now=now,
        source=source,
    )


def kraken_persistent_storage_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Compatibility shim; global private-storage approval is final."""

    return _provider_written_archive_authority_missing(
        "kraken",
        allowed_scopes={
            "written_single_user_automated_internal_display_perpetual_archive",
            "written_licensed_business_automated_internal_display_perpetual_archive",
        },
        now=now,
        source=source,
    )


def robinhood_tokens_persistent_storage_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Compatibility shim; global private-storage approval is final."""

    return _provider_written_archive_authority_missing(
        "robinhood_tokens",
        allowed_scopes={
            "written_single_user_automated_internal_display_perpetual_archive",
            "written_licensed_business_automated_internal_display_perpetual_archive",
        },
        now=now,
        source=source,
    )


def gate_tradfi_persistent_storage_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Compatibility shim; global private-storage approval is final."""

    return _provider_written_archive_authority_missing(
        "gate_tradfi",
        allowed_scopes={
            "written_single_user_automated_internal_display_perpetual_archive",
            "written_licensed_business_automated_internal_display_perpetual_archive",
        },
        now=now,
        source=source,
    )


def tradier_persistent_storage_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Compatibility shim; global private-storage approval is final."""

    return _provider_written_archive_authority_missing(
        "tradier",
        allowed_scopes={
            "written_single_user_automated_internal_display_perpetual_archive_with_upstream_market_data_rights",
            "written_licensed_business_automated_internal_display_perpetual_archive_with_upstream_market_data_rights",
        },
        now=now,
        source=source,
    )


def ibkr_persistent_storage_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Compatibility shim; global private-storage approval is final."""

    return _provider_written_archive_authority_missing(
        "ibkr",
        allowed_scopes={
            "written_single_user_automated_internal_display_perpetual_archive_with_exchange_rights",
            "written_licensed_business_automated_internal_display_perpetual_archive_with_exchange_rights",
        },
        now=now,
        source=source,
    )


def ondo_global_markets_persistent_storage_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Compatibility shim; global private-storage approval is final."""

    return _provider_written_archive_authority_missing(
        "ondo_global_markets",
        allowed_scopes={
            "written_approved_api_client_automated_internal_display_perpetual_archive",
            "written_licensed_business_approved_api_client_automated_internal_display_perpetual_archive",
        },
        now=now,
        source=source,
    )


def yfinance_persistent_storage_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Compatibility shim; global private-storage approval is final."""

    return _provider_written_archive_authority_missing(
        "yfinance",
        allowed_scopes={
            "written_yahoo_automated_collection_internal_display_perpetual_archive",
            "written_yahoo_licensed_business_automated_collection_internal_display_perpetual_archive",
        },
        now=now,
        source=source,
    )


def marketstack_persistent_storage_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Compatibility shim; global private-storage approval is final."""

    return _provider_written_archive_authority_missing(
        "marketstack",
        allowed_scopes={
            "written_single_user_automated_internal_display_perpetual_archive",
            "written_licensed_business_internal_display_perpetual_archive",
        },
        now=now,
        source=source,
    )


def eodhd_persistent_storage_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Compatibility shim; provider display terms are tracked separately."""

    return _provider_written_archive_authority_missing(
        "eodhd",
        allowed_scopes={
            "written_single_user_automated_internal_display_perpetual_archive",
            "written_licensed_business_internal_display_perpetual_archive",
        },
        now=now,
        source=source,
    )


def tiingo_persistent_storage_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Compatibility name; private persistence has global owner approval."""

    del now, source
    return []


def twelve_data_persistent_storage_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Compatibility name; private persistence has global owner approval."""

    del now, source
    return []


def marketdata_app_persistent_storage_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Compatibility name; private persistence has global owner approval."""

    del now, source
    return []


def xstocks_market_data_use_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Apply the final private-use decision to xStocks public market data."""

    now = now or datetime.now(UTC)
    source = source or settings
    missing: list[str] = []
    if provider_reviewed_flag(getattr(source, "PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", False)):
        return []
    if not provider_reviewed_flag(getattr(source, "XSTOCKS_MARKET_DATA_USE_AUTHORIZED", False)):
        missing.append("XSTOCKS_MARKET_DATA_USE_AUTHORIZED")
    if not str(getattr(source, "XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE", "") or "").strip():
        missing.append("XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE")
    if (
        str(getattr(source, "XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE", "") or "").strip()
        != "internal_automated_persistent_nonredistributed"
    ):
        missing.append("XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE")
    reviewed_at = getattr(source, "XSTOCKS_MARKET_DATA_USE_REVIEWED_AT", None)
    if not isinstance(reviewed_at, datetime) or reviewed_at.tzinfo is None:
        missing.append("XSTOCKS_MARKET_DATA_USE_REVIEWED_AT")
    elif reviewed_at > now:
        missing.append("XSTOCKS_MARKET_DATA_USE_REVIEWED_AT")
    expires_at = getattr(source, "XSTOCKS_MARKET_DATA_USE_EXPIRES_AT", None)
    if expires_at is not None:
        if not isinstance(expires_at, datetime) or expires_at.tzinfo is None:
            missing.append("XSTOCKS_MARKET_DATA_USE_EXPIRES_AT")
        elif expires_at <= now:
            missing.append("XSTOCKS_MARKET_DATA_USE_EXPIRES_AT")
    return missing


def bybit_xstocks_market_data_use_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Require Bybit public-data authorization and technically safe egress.

    Bybit's API documentation states that IPs located in the US and Mainland
    China receive 403 responses. Product trading eligibility is not applied to
    this anonymous, read-only market-data client.
    """

    now = now or datetime.now(UTC)
    source = source or settings
    missing: list[str] = []
    owner_accepts_private_use = provider_reviewed_flag(
        getattr(source, "PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", False)
    )
    if not owner_accepts_private_use:
        if not provider_reviewed_flag(
            getattr(source, "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORIZED", False)
        ):
            missing.append("BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORIZED")
        if not str(
            getattr(source, "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE", "") or ""
        ).strip():
            missing.append("BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE")
        if (
            str(getattr(source, "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE", "") or "").strip()
            != "internal_automated_persistent_nonredistributed"
        ):
            missing.append("BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE")
        reviewed_at = getattr(source, "BYBIT_XSTOCKS_MARKET_DATA_USE_REVIEWED_AT", None)
        if not isinstance(reviewed_at, datetime) or reviewed_at.tzinfo is None:
            missing.append("BYBIT_XSTOCKS_MARKET_DATA_USE_REVIEWED_AT")
        elif reviewed_at > now:
            missing.append("BYBIT_XSTOCKS_MARKET_DATA_USE_REVIEWED_AT")
        expires_at = getattr(source, "BYBIT_XSTOCKS_MARKET_DATA_USE_EXPIRES_AT", None)
        if expires_at is not None:
            if not isinstance(expires_at, datetime) or expires_at.tzinfo is None:
                missing.append("BYBIT_XSTOCKS_MARKET_DATA_USE_EXPIRES_AT")
            elif expires_at <= now:
                missing.append("BYBIT_XSTOCKS_MARKET_DATA_USE_EXPIRES_AT")
    if not provider_reviewed_flag(
        getattr(source, "BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_AUTHORIZED", False)
    ):
        missing.append("BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_AUTHORIZED")
    if not str(
        getattr(source, "BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_EVIDENCE", "") or ""
    ).strip():
        missing.append("BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_EVIDENCE")
    return missing


def fred_data_use_controls_missing(source: object | None = None) -> list[str]:
    """Require FRED's provider-specific automated-use and API-key boundaries."""

    source = source or settings
    if provider_reviewed_flag(getattr(source, "PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", False)):
        return []
    missing: list[str] = []
    user_scope = str(getattr(source, "FRED_APPLICATION_USER_SCOPE", "") or "")
    if user_scope.strip().lower() != "owner_personal_only":
        missing.append("FRED_APPLICATION_USER_SCOPE")
    if not str(getattr(source, "FRED_APPLICATION_USER_SCOPE_EVIDENCE", "") or "").strip():
        missing.append("FRED_APPLICATION_USER_SCOPE_EVIDENCE")
    if not provider_reviewed_flag(getattr(source, "FRED_AUTOMATED_USE_AUTHORIZED", False)):
        missing.append("FRED_AUTOMATED_USE_AUTHORIZED")
    if not str(getattr(source, "FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE", "") or "").strip():
        missing.append("FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE")
    return missing


def fred_series_rights_authorized(series_id: str, source: object | None = None) -> bool:
    """Return whether this exact provider series has recorded rights evidence."""

    source = source or settings
    if provider_reviewed_flag(getattr(source, "PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", False)):
        return True
    rights = getattr(source, "FRED_SERIES_RIGHTS_EVIDENCE", {})
    if not isinstance(rights, dict):
        return False
    evidence = rights.get(series_id)
    return isinstance(evidence, str) and bool(evidence.strip())


def fred_series_rights_missing(source: object | None = None) -> list[str]:
    """Return missing rights records for every series exposed by the adapter."""

    source = source or settings
    if provider_reviewed_flag(getattr(source, "PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", False)):
        return []
    rights = getattr(source, "FRED_SERIES_RIGHTS_EVIDENCE", {})
    if not isinstance(rights, dict):
        return ["FRED_SERIES_RIGHTS_EVIDENCE"]
    return (
        ["FRED_SERIES_RIGHTS_EVIDENCE"]
        if any(
            not isinstance(rights.get(series_id), str) or not rights[series_id].strip()
            for series_id in FRED_MAPPED_SERIES_IDS
        )
        else []
    )


def provider_operation_byte_bounds(provider_name: str) -> dict[str, int]:
    """Return only positive, explicitly configured operation byte bounds."""

    setting_name = f"{provider_name.upper()}_OPERATION_BYTE_BOUNDS"
    raw = getattr(settings, setting_name, {})
    if not isinstance(raw, dict):
        return {}
    result: dict[str, int] = {}
    for operation, value in raw.items():
        bound = provider_positive_integer(value)
        if str(operation).strip() and bound is not None:
            result[str(operation).strip()] = bound
    return result


def provider_rate_limit_seed(provider_name: str) -> dict:
    """Return a provider quota seed with reviewed provider controls applied.

    Tiingo and FMP publish bandwidth pools but not a universal response-size
    ceiling.  The base seed therefore remains explicitly untracked.  An
    operator can promote the provider only by supplying a positive bound for
    every operation exposed by its adapter; the helper then moves that
    documented pool into the normal multidimensional reservation contract.
    MarketData.app similarly requires an exact, operator-reviewed account
    plan/limit pair before the documented Free Forever seed is widened. The
    Starter Trial and Trader Trial plans are accepted as separate, explicitly
    time-limited plan identifiers with their provider-published daily pools.
    """

    seed = deepcopy(settings.PROVIDER_RATE_LIMIT_SEEDS.get(provider_name, {}))
    if (
        provider_name == "finra_otc_directory"
        and str(getattr(settings, "FINRA_OTC_SOURCE_KIND", "") or "").strip().lower()
        == "finra_orf_security_master"
    ):
        # ORF file delivery is a different product and credential system. Its
        # published file specification does not define a numeric request quota,
        # so it must never inherit the Query API's 1,200/minute contract.
        return {
            "quota_contract": {
                "dimensions": [],
                "unknown_dimensions": [
                    "orf_product_entitlement_and_mfa",
                    "file_download_quota_and_reset",
                ],
                "reset": "provider_defined",
                "operation_costs_required": True,
                "source": "https://www.finra.org/sites/default/files/2024-08/Equity_API_File_Downloads_ORF.pdf",
            },
            "quota_scope": "unknown",
            "quota_source": (
                "FINRA ORF file-download specification; entitlement and account limits unresolved"
            ),
        }
    if provider_name == "dinari":
        if os.getenv("DINARI_SANDBOX_CANARY_RUN", "").strip() == "1":
            # This is an application-only, live-test safety ceiling. It is
            # deliberately not asserted to be Dinari's quota and exists only
            # in the opt-in test subprocess. The one-request/day reservation
            # survives worktree/process restarts in the shared quota ledger.
            seed["quota_scope"] = "local_dinari_sandbox_canary"
            seed["quota_source"] = (
                "local canary policy: one read-only catalogue request per UTC day; "
                "not a Dinari provider quota"
            )
            seed["quota_contract"] = {
                "reset": "calendar_day_utc",
                "dimensions": [
                    {
                        "name": "local_canary_requests_per_utc_day",
                        "limit": 1,
                        "window_seconds": 86400,
                        "unit": "requests",
                        "scope": "public_api",
                        "quota_group": "dinari_sandbox_canary",
                        "baseline_mode": "local_zero",
                        "application_usage_only": True,
                        "applies_to_operations": ["discover_tokenized_assets"],
                        "source": "owner-authorized one-request Sandbox connectivity canary",
                    }
                ],
                "operation_costs": {"discover_tokenized_assets": 1},
            }
            return seed
        # Only an explicit account-reviewed profile may replace the unknown
        # Sandbox contract. The unrelated June 2024 License cap is never
        # inherited as a Sandbox default.
        reviewed_profile = getattr(settings, "DINARI_SANDBOX_QUOTA_PROFILE", {})
        if isinstance(reviewed_profile, dict):
            for key in ("quota_scope", "quota_source", "quota_contract"):
                if key in reviewed_profile:
                    seed[key] = deepcopy(reviewed_profile[key])
    if provider_name == "openfigi":
        # OpenFIGI publishes separate request and payload limits for
        # anonymous and API-key traffic. Select the exact contract for the
        # current environment; never approximate the keyed six-second burst
        # as a generic per-minute fallback.
        authenticated = bool(str(getattr(settings, "OPENFIGI_API_KEY", "") or "").strip())
        contract = seed.get("quota_contract")
        if isinstance(contract, dict):
            account_usage_probe = next(
                (
                    item
                    for item in contract.get("dimensions", [])
                    if isinstance(item, dict)
                    and item.get("name") == "account_usage_probe_concurrency"
                ),
                None,
            )
            if authenticated:
                contract["dimensions"] = [
                    {
                        "name": "mapping_requests_per_6_seconds",
                        "limit": 25,
                        "window_seconds": 6,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://www.openfigi.com/api/documentation",
                    }
                ]
                contract["endpoint_constraints"] = {
                    "mapping": {
                        "max_jobs_per_request": 100,
                        "source": "https://www.openfigi.com/api/documentation",
                    }
                }
                # Keep the policy-level provenance stable so an existing
                # anonymous row refreshes to the keyed contract on restart;
                # the dimension itself carries the exact API-key scope.
                seed["quota_scope"] = "ip_or_api_key"
                seed["quota_source"] = "OpenFIGI API documentation"
                # Durable reservations enforce the exact six-second window;
                # the legacy minute bucket cannot represent its burst safely.
                seed.pop("tokens_per_minute", None)
            else:
                contract["dimensions"] = [
                    {
                        "name": "mapping_requests_per_minute",
                        "limit": 25,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "ip",
                        "quota_group": "ip",
                        "source": "https://www.openfigi.com/api/documentation",
                    }
                ]
                contract["endpoint_constraints"] = {
                    "mapping": {
                        "max_jobs_per_request": 5,
                        "source": "https://www.openfigi.com/api/documentation",
                    }
                }
                seed["quota_scope"] = "ip_or_api_key"
                seed["quota_source"] = "OpenFIGI API documentation"
                seed["tokens_per_minute"] = 25
            if account_usage_probe is not None:
                contract["dimensions"].append(account_usage_probe)
            seed["quota_contract"] = contract
        return seed
    if provider_name == "marketdata_app":
        reviewed_plan = marketdata_app_reviewed_plan()
        if reviewed_plan is not None:
            plan, daily_limit = reviewed_plan
            trial_expiry = getattr(settings, "MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT", None)
            account_plan_metadata = {
                "account_plan": plan,
                "account_limit_reviewed": True,
            }
            # Keep the active trial boundary visible to admin diagnostics and
            # quota receipts without treating it as a credential or silently
            # carrying an expired trial into the Free Forever fallback.
            if (
                plan.endswith("_trial")
                and isinstance(trial_expiry, datetime)
                and trial_expiry.tzinfo is not None
            ):
                account_plan_metadata["account_plan_expires_at"] = trial_expiry.astimezone(
                    UTC
                ).isoformat()
            contract = seed.get("quota_contract")
            if isinstance(contract, dict):
                contract["dimensions"] = [
                    {
                        **dimension,
                        "limit": daily_limit,
                        **account_plan_metadata,
                    }
                    if isinstance(dimension, dict) and dimension.get("name") == "credits_per_day"
                    else dimension
                    for dimension in contract.get("dimensions") or []
                ]
                seed["quota_contract"] = contract
        return seed
    if provider_name == "eodhd":
        # The detailed API-limits page documents 1,000 requests/minute; the
        # Free-plan pricing card says 20/minute, while this key's native header
        # reported 1,200. Only complete account-specific evidence may override
        # the reviewed seed, and partial overrides remain blocked.
        reviewed_limit = provider_positive_integer(
            getattr(settings, "EODHD_REVIEWED_MINUTE_LIMIT", 0)
        )
        reviewed_reset = str(getattr(settings, "EODHD_REVIEWED_MINUTE_RESET", "") or "").strip()
        quota_evidence = str(getattr(settings, "EODHD_MINUTE_QUOTA_EVIDENCE", "") or "").strip()
        contract = seed.get("quota_contract")
        if reviewed_limit is not None and isinstance(contract, dict):
            if not provider_quota_reset_is_admission_safe(reviewed_reset) or not quota_evidence:
                contract["unknown_dimensions"] = ["operator_minute_override_incomplete"]
                return seed
            for dimension in contract.get("dimensions") or []:
                if isinstance(dimension, dict) and dimension.get("name") == "requests_per_minute":
                    dimension["limit"] = reviewed_limit
                    dimension["reset"] = reviewed_reset
                    dimension["limit_basis"] = "operator-reviewed account-specific override"
            contract["source"] = (
                f"{contract.get('source', 'EODHD API documentation')} plus "
                "operator-reviewed account-specific override"
            )
            seed["tokens_per_minute"] = reviewed_limit
            seed["quota_source"] = (
                "EODHD published contract plus operator-reviewed account-specific override"
            )
        return seed
    if provider_name == "alpha_vantage":
        # Alpha Vantage documents the free-key daily allowance but does not
        # publish the reset boundary/timezone. The base dimension therefore
        # keeps the provider-defined label for audit and carries its explicit
        # rolling 24-hour application envelope. An operator may replace that
        # envelope only after recording a reviewed, calculable native reset
        # label and evidence; the setting remains provider-specific so plan
        # changes are configuration-only.
        reviewed_reset = str(getattr(settings, "ALPHA_VANTAGE_REVIEWED_RESET", "") or "").strip()
        quota_evidence = str(getattr(settings, "ALPHA_VANTAGE_QUOTA_EVIDENCE", "") or "").strip()
        contract = seed.get("quota_contract")
        if (
            provider_quota_reset_is_admission_safe(reviewed_reset)
            and quota_evidence
            and isinstance(contract, dict)
        ):
            contract["reset"] = reviewed_reset
            contract["unknown_dimensions"] = [
                item
                for item in contract.get("unknown_dimensions", [])
                if item != "requests_per_day_reset_boundary"
            ]
            for dimension in contract.get("dimensions") or []:
                if isinstance(dimension, dict) and dimension.get("name") == "requests_per_day":
                    dimension["reset"] = reviewed_reset
            contract["source"] = (
                f"{contract.get('source', 'Alpha Vantage support documentation')} plus "
                "operator-reviewed reset-boundary evidence"
            )
            seed["quota_scope"] = "api_key"
            seed["quota_source"] = (
                "Alpha Vantage support allowance plus operator-reviewed reset evidence"
            )
        return seed
    if provider_name == "massive":
        # The Stocks Basic limit applies to all requests in the Stocks asset
        # class, including its reference-data and corporate-action endpoints.
        # Do not split those calls into a fictitious second quota bucket.
        contract = seed.get("quota_contract")
        reviewed_reset = str(getattr(settings, "MASSIVE_REVIEWED_RESET", "") or "").strip()
        quota_evidence = str(getattr(settings, "MASSIVE_QUOTA_EVIDENCE", "") or "").strip()
        if (
            provider_quota_reset_is_admission_safe(reviewed_reset)
            and quota_evidence
            and isinstance(contract, dict)
        ):
            contract["reset"] = reviewed_reset
            contract["unknown_dimensions"] = [
                item
                for item in contract.get("unknown_dimensions", [])
                if item != "requests_per_minute_reset_boundary"
            ]
            for dimension in contract.get("dimensions") or []:
                if isinstance(dimension, dict) and str(dimension.get("name") or "").startswith(
                    "requests_per_minute"
                ):
                    dimension["reset"] = reviewed_reset
            contract["source"] = (
                f"{contract.get('source', 'Massive Stocks Basic documentation')} plus "
                "operator-reviewed reset-boundary evidence"
            )
            seed["quota_scope"] = "account"
            seed["quota_source"] = (
                "Massive Stocks Basic allowance plus operator-reviewed reset evidence"
            )
        return seed
    if provider_name == "edgar":
        # EDGAR publishes a 10-requests/second fair-access ceiling, but the
        # source does not establish the reset boundary. The base dimension
        # retains the provider-defined label and enforces its explicit rolling
        # one-second safety envelope; an operator may replace it only with a
        # reviewed native reset and current evidence.
        reviewed_reset = str(getattr(settings, "EDGAR_REVIEWED_RESET", "") or "").strip()
        quota_evidence = str(getattr(settings, "EDGAR_QUOTA_EVIDENCE", "") or "").strip()
        contract = seed.get("quota_contract")
        if (
            provider_quota_reset_is_admission_safe(reviewed_reset)
            and quota_evidence
            and isinstance(contract, dict)
        ):
            contract["reset"] = reviewed_reset
            contract["unknown_dimensions"] = []
            for dimension in contract.get("dimensions") or []:
                if isinstance(dimension, dict) and dimension.get("name") == "requests_per_second":
                    dimension["reset"] = reviewed_reset
            contract["source"] = (
                f"{contract.get('source', 'SEC fair-access policy')} plus "
                "operator-reviewed reset-boundary evidence"
            )
            seed["quota_source"] = "SEC fair-access ceiling plus operator-reviewed reset evidence"
        return seed
    if provider_name == "alpaca":
        # The current Trading API Basic contract is source-backed by the
        # Market Data documentation/OpenAPI and the provider's native
        # X-RateLimit-* headers. Optional settings remain available for a
        # future plan change, but ordinary routing must not wait for a human
        # to restate a reset model that Alpaca already defines as per-minute.
        reviewed_reset = str(getattr(settings, "ALPACA_REVIEWED_RESET", "") or "").strip()
        quota_evidence = str(getattr(settings, "ALPACA_QUOTA_EVIDENCE", "") or "").strip()
        contract = seed.get("quota_contract")
        if isinstance(contract, dict):
            for dimension in contract.get("dimensions") or []:
                if (
                    isinstance(dimension, dict)
                    and dimension.get("name") == "market_data_requests_per_minute"
                ):
                    dimension["reset"] = contract.get("reset", "fixed_minute")
            if reviewed_reset:
                if not provider_quota_reset_is_admission_safe(reviewed_reset) or not quota_evidence:
                    contract["unknown_dimensions"] = ["operator_reset_override_invalid"]
                    return seed
                contract["reset"] = reviewed_reset
                contract["source"] = (
                    f"{contract.get('source', 'Alpaca market data API documentation')} plus "
                    "operator-reviewed reset-boundary evidence"
                )
                for dimension in contract.get("dimensions") or []:
                    if (
                        isinstance(dimension, dict)
                        and dimension.get("name") == "market_data_requests_per_minute"
                    ):
                        dimension["reset"] = reviewed_reset
            contract["unknown_dimensions"] = []
            seed["quota_scope"] = "account"
            seed["quota_source"] = "Alpaca Market Data API allowance and native reset headers"
        return seed
    if provider_name == "finnhub":
        # Finnhub's free account exposes separate minute and second request
        # ceilings. The base dimensions retain their provider-defined labels
        # and enforce independent rolling safety envelopes. An operator may
        # replace both envelopes only with explicit, calculable reset labels
        # and independent evidence; no generic or cross-dimension window is
        # invented.
        minute_reset = str(getattr(settings, "FINNHUB_REVIEWED_MINUTE_RESET", "") or "").strip()
        second_reset = str(getattr(settings, "FINNHUB_REVIEWED_SECOND_RESET", "") or "").strip()
        minute_evidence = str(getattr(settings, "FINNHUB_MINUTE_QUOTA_EVIDENCE", "") or "").strip()
        second_evidence = str(getattr(settings, "FINNHUB_SECOND_QUOTA_EVIDENCE", "") or "").strip()
        contract = seed.get("quota_contract")
        if (
            provider_quota_reset_is_admission_safe(minute_reset)
            and provider_quota_reset_is_admission_safe(second_reset)
            and minute_evidence
            and second_evidence
            and isinstance(contract, dict)
        ):
            contract["reset"] = "per_dimension"
            contract["unknown_dimensions"] = []
            for dimension in contract.get("dimensions") or []:
                if not isinstance(dimension, dict):
                    continue
                if dimension.get("name") == "calls_per_minute":
                    dimension["reset"] = minute_reset
                elif dimension.get("name") == "hard_calls_per_second":
                    dimension["reset"] = second_reset
            contract["source"] = (
                f"{contract.get('source', 'Finnhub API documentation')} plus "
                "independent operator-reviewed minute/second reset evidence"
            )
            seed["quota_scope"] = "api_key"
            seed["quota_source"] = (
                "Finnhub account limits plus independent operator-reviewed reset evidence"
            )
        return seed
    if provider_name == "tiingo":
        # Tiingo publishes the distinct-symbol pool without a monthly anchor
        # and says the hourly pool resets every hour, but does not identify the
        # hourly boundary model (fixed/calendar versus rolling). The seed
        # carries provider-scoped rolling safety envelopes for both pools;
        # reviewed native reset labels/evidence may replace them. No generic
        # cross-provider fallback is introduced.
        plan = str(getattr(settings, "TIINGO_REVIEWED_PLAN", "starter") or "").strip().lower()
        plan_profiles = {
            # Tiingo's official pricing table: Starter is the current free
            # individual tier; Power is the published $30/month individual
            # tier. The public table does not publish one fixed Commercial /
            # enterprise allowance, so such accounts use the evidence-backed
            # custom profile below rather than inheriting a published tier.
            "starter": (500, 50, 1_000, 1_000_000_000),
            "power": (110_237, 10_000, 100_000, 40_000_000_000),
        }
        contract = seed.get("quota_contract")
        if not isinstance(contract, dict):
            return seed
        plan_evidence = str(getattr(settings, "TIINGO_CUSTOM_QUOTA_EVIDENCE", "") or "").strip()
        if plan == "custom":
            custom_values = (
                provider_positive_integer(
                    getattr(settings, "TIINGO_CUSTOM_UNIQUE_SYMBOLS_PER_MONTH", 0)
                ),
                provider_positive_integer(getattr(settings, "TIINGO_CUSTOM_REQUESTS_PER_HOUR", 0)),
                provider_positive_integer(getattr(settings, "TIINGO_CUSTOM_REQUESTS_PER_DAY", 0)),
                provider_positive_integer(
                    getattr(settings, "TIINGO_CUSTOM_BANDWIDTH_BYTES_PER_MONTH", 0)
                ),
            )
            if any(value is None for value in custom_values) or not plan_evidence:
                contract["dimensions"] = []
                contract["untracked_constraints"] = []
                contract["unknown_dimensions"] = ["custom_account_quota_values_or_evidence"]
                contract["operation_costs_required"] = True
                contract["source"] = "Tiingo custom account quota profile (incomplete)"
                seed.pop("tokens_per_minute", None)
                seed["quota_source"] = (
                    "Tiingo custom plan is non-routable until every quota is reviewed"
                )
                return seed
            unique_limit, hourly_limit, daily_limit, bandwidth_limit = cast(
                tuple[int, int, int, int], custom_values
            )
            quota_provenance = "operator-reviewed custom account plan evidence"
        elif plan in plan_profiles:
            unique_limit, hourly_limit, daily_limit, bandwidth_limit = plan_profiles[plan]
            quota_provenance = f"Tiingo published {plan.title()} plan"
        else:
            contract["dimensions"] = []
            contract["untracked_constraints"] = []
            contract["unknown_dimensions"] = ["tiingo_account_plan_unrecognized"]
            seed.pop("tokens_per_minute", None)
            seed["quota_source"] = "Tiingo plan is unrecognized and therefore non-routable"
            return seed
        limits_by_dimension = {
            "unique_symbols_per_month": unique_limit,
            "requests_per_hour": hourly_limit,
            "requests_per_day": daily_limit,
        }
        for dimension in contract.get("dimensions") or []:
            if isinstance(dimension, dict) and dimension.get("name") in limits_by_dimension:
                dimension["limit"] = limits_by_dimension[dimension["name"]]
        for constraint in contract.get("untracked_constraints") or []:
            if (
                isinstance(constraint, dict)
                and constraint.get("name") == "bandwidth_bytes_per_month"
            ):
                constraint["limit"] = bandwidth_limit
                constraint["limit_basis"] = (
                    "decimal_bytes_published_plan_or_reviewed_custom_account_value"
                )
        contract["account_plan"] = plan
        contract["plan_evidence"] = plan_evidence if plan == "custom" else ""
        contract["source"] = (
            f"{contract.get('source', 'Tiingo pricing and API documentation')} plus {quota_provenance}"
        )
        unique_reset = str(
            getattr(settings, "TIINGO_REVIEWED_UNIQUE_SYMBOL_RESET", "") or ""
        ).strip()
        hourly_reset = str(getattr(settings, "TIINGO_REVIEWED_HOURLY_RESET", "") or "").strip()
        unique_evidence = str(
            getattr(settings, "TIINGO_UNIQUE_SYMBOL_QUOTA_EVIDENCE", "") or ""
        ).strip()
        hourly_evidence = str(getattr(settings, "TIINGO_HOURLY_QUOTA_EVIDENCE", "") or "").strip()
        dimensions = contract.get("dimensions", [])
        unique_dimension = next(
            (
                item
                for item in dimensions
                if isinstance(item, dict) and item.get("name") == "unique_symbols_per_month"
            ),
            None,
        )
        hourly_dimension = next(
            (
                item
                for item in dimensions
                if isinstance(item, dict) and item.get("name") == "requests_per_hour"
            ),
            None,
        )
        unique_safety_reset = (
            str(unique_dimension.get("safety_reset") or "").strip()
            if isinstance(unique_dimension, dict)
            else ""
        )
        hourly_safety_reset = (
            str(hourly_dimension.get("safety_reset") or "").strip()
            if isinstance(hourly_dimension, dict)
            else ""
        )
        native_override_valid = (
            provider_quota_reset_is_admission_safe(unique_reset)
            and provider_quota_reset_is_admission_safe(hourly_reset)
            and unique_evidence
            and hourly_evidence
        )
        safety_default_valid = (
            not unique_reset
            and not hourly_reset
            and not unique_evidence
            and not hourly_evidence
            and provider_quota_reset_is_admission_safe(unique_safety_reset)
            and provider_quota_reset_is_admission_safe(hourly_safety_reset)
        )
        if not (native_override_valid or safety_default_valid):
            return seed
        required = _BYTE_BOUND_OPERATIONS.get(provider_name)
        if not required:
            return seed
        bounds = provider_operation_byte_bounds(provider_name)
        if any(operation not in bounds for operation in required):
            return seed
        if not isinstance(contract, dict):
            return seed
        untracked = list(contract.get("untracked_constraints") or [])
        byte_constraint = next(
            (
                item
                for item in untracked
                if isinstance(item, dict)
                and str(item.get("unit") or "").lower() in {"byte", "bytes"}
            ),
            None,
        )
        if byte_constraint is None:
            return seed
        contract["untracked_constraints"] = [
            item for item in untracked if item is not byte_constraint
        ]
        dimensions = list(contract.get("dimensions") or [])
        if not any(
            item.get("name") == byte_constraint.get("name")
            for item in dimensions
            if isinstance(item, dict)
        ):
            dimensions.append(dict(byte_constraint))
        contract["dimensions"] = dimensions
        contract["reset"] = "per_dimension"
        if native_override_valid:
            contract["unknown_dimensions"] = [
                item
                for item in (contract.get("unknown_dimensions") or [])
                if item
                not in {
                    "unique_symbols_reset_anchor",
                    "requests_per_hour_reset_boundary_model",
                }
            ]
        for dimension in dimensions:
            if not isinstance(dimension, dict):
                continue
            if dimension.get("name") == "unique_symbols_per_month":
                if native_override_valid:
                    dimension["reset"] = unique_reset
                else:
                    dimension.pop("reset", None)
                    dimension["safety_reset"] = unique_safety_reset
            elif dimension.get("name") == "requests_per_hour":
                if native_override_valid:
                    dimension["reset"] = hourly_reset
                else:
                    dimension.pop("reset", None)
                    dimension["safety_reset"] = hourly_safety_reset
        contract["dimension_costs_required"] = True
        contract["operation_costs_required"] = True
        contract["source"] = (
            f"{contract.get('source', 'Tiingo pricing and API documentation')} plus "
            + (
                "provider-scoped rolling distinct-symbol/hourly safety envelopes"
                if not native_override_valid
                else "operator-reviewed distinct-symbol/hourly reset evidence"
            )
        )
        seed["quota_contract"] = contract
        seed["quota_source"] = f"Tiingo {plan} plan allowance plus " + (
            "provider-scoped rolling distinct-symbol/hourly safety envelopes"
            if not native_override_valid
            else "operator-reviewed distinct-symbol/hourly reset evidence"
        )
        seed["_byte_reservation_bounds"] = bounds
        return seed
    if provider_name == "marketstack":
        reviewed_limit = provider_positive_integer(
            getattr(settings, "MARKETSTACK_REVIEWED_MONTHLY_LIMIT", 0)
        )
        reviewed_reset = str(
            getattr(settings, "MARKETSTACK_REVIEWED_MONTHLY_RESET", "") or ""
        ).strip()
        quota_evidence = str(getattr(settings, "MARKETSTACK_QUOTA_EVIDENCE", "") or "").strip()
        contract = seed.get("quota_contract")
        if reviewed_limit is not None and isinstance(contract, dict):
            base_limit = 100
            custom_account_policy = reviewed_limit != base_limit or bool(reviewed_reset)
            reset_override_valid = not reviewed_reset or provider_quota_reset_is_admission_safe(
                reviewed_reset
            )
            evidence_valid = not custom_account_policy or bool(quota_evidence)
            if not (reset_override_valid and evidence_valid):
                return seed
            if reviewed_reset:
                contract["reset"] = "per_dimension"
                contract["unknown_dimensions"] = [
                    item
                    for item in (contract.get("unknown_dimensions") or [])
                    if item != "monthly_cap_reset_boundary"
                ]
            for dimension in contract.get("dimensions") or []:
                if isinstance(dimension, dict) and dimension.get("name") == "requests_per_month":
                    dimension["limit"] = reviewed_limit
                    if reviewed_reset:
                        dimension["reset"] = reviewed_reset
                        dimension.pop("safety_reset", None)
                        dimension.pop("safety_resolves_unknown_dimensions", None)
            if custom_account_policy:
                contract["source"] = (
                    f"{contract.get('source', 'Marketstack pricing/FAQ')} plus "
                    "operator-reviewed account limit/reset evidence"
                )
            seed["quota_contract"] = contract
            seed["quota_source"] = (
                "Marketstack account allowance plus reviewed account-specific quota evidence"
                if custom_account_policy
                else "Marketstack Free-plan allowance, enforced through a provider-specific rolling 30-day safety window"
            )
        return seed
    if provider_name == "fmp":
        # FMP publishes four personal-use plans with different request pools
        # and 30-day bandwidth limits. The default is the owner's confirmed
        # Basic plan; changing the plan is configuration-only. FMP's official
        # material conflicts on whether Basic has a universally fixed daily
        # reset, so use a rolling safety window unless an account-reviewed
        # boundary is configured and evidenced.
        plan = str(getattr(settings, "FMP_REVIEWED_PLAN", "basic") or "").strip().lower()
        reviewed_daily_reset = str(getattr(settings, "FMP_REVIEWED_DAILY_RESET", "") or "").strip()
        reviewed_call_reset = str(getattr(settings, "FMP_REVIEWED_CALL_RESET", "") or "").strip()
        native_call_reset = reviewed_call_reset or (reviewed_daily_reset if plan == "basic" else "")
        fmp_plan_profiles: dict[str, tuple[str, int, int, int]] = {
            "basic": ("calls_per_day", 250, 86_400, 500_000_000),
            "starter": ("calls_per_minute", 300, 60, 20_000_000_000),
            "premium": ("calls_per_minute", 750, 60, 50_000_000_000),
            "ultimate": ("calls_per_minute", 3_000, 60, 150_000_000_000),
        }
        contract = seed.get("quota_contract")
        if plan not in fmp_plan_profiles:
            if isinstance(contract, dict):
                contract["unknown_dimensions"] = list(
                    dict.fromkeys([*(contract.get("unknown_dimensions") or []), "fmp_account_plan"])
                )
            return seed
        call_dimension, call_limit, call_window, bandwidth_limit = fmp_plan_profiles[plan]
        if isinstance(contract, dict):
            contract["dimensions"] = [
                item
                for item in (contract.get("dimensions") or [])
                if not isinstance(item, dict)
                or item.get("name") not in {"calls_per_day", "calls_per_minute"}
            ]
            contract["dimensions"].append(
                {
                    "name": call_dimension,
                    "limit": call_limit,
                    "window_seconds": call_window,
                    "unit": "requests",
                    "scope": "api_key",
                    "quota_group": "api_key",
                    "source": (
                        "https://site.financialmodelingprep.com/pricing-plans; "
                        "https://site.financialmodelingprep.com/faqs"
                    ),
                    "reset": native_call_reset or "provider_defined",
                    **({} if native_call_reset else {"safety_reset": "rolling"}),
                }
            )
            bootstrap = contract.get("account_usage_bootstrap")
            if isinstance(bootstrap, dict) and bootstrap.get("enabled") is True:
                bootstrap["reconciled_dimensions"] = [
                    call_dimension,
                    "bandwidth_bytes_per_30_days",
                ]
            for constraint in contract.get("untracked_constraints") or []:
                if (
                    isinstance(constraint, dict)
                    and constraint.get("name") == "bandwidth_bytes_per_30_days"
                ):
                    constraint["limit"] = bandwidth_limit
                    constraint["limit_basis"] = "decimal_bytes_conservative_for_published_MB_or_GB"
        seed["configured_plan"] = plan

        daily_reset = reviewed_daily_reset
        call_reset = reviewed_call_reset
        if not call_reset and plan == "basic":
            call_reset = daily_reset
        reviewed_bandwidth_reset = str(
            getattr(settings, "FMP_REVIEWED_BANDWIDTH_RESET", "") or ""
        ).strip()
        bandwidth_reset = reviewed_bandwidth_reset or "rolling_30_days"
        daily_evidence = str(
            getattr(settings, "FMP_CALL_QUOTA_EVIDENCE", "")
            or getattr(settings, "FMP_DAILY_QUOTA_EVIDENCE", "")
            or FMP_PUBLIC_QUOTA_EVIDENCE
            or ""
        ).strip()
        bandwidth_evidence = str(
            getattr(settings, "FMP_BANDWIDTH_QUOTA_EVIDENCE", "") or FMP_PUBLIC_QUOTA_EVIDENCE or ""
        ).strip()
        if call_reset and not provider_quota_reset_is_admission_safe(call_reset):
            return seed
        if call_reset and not daily_evidence:
            return seed
        if not daily_evidence:
            return seed
        if not (provider_quota_reset_is_admission_safe(bandwidth_reset) and bandwidth_evidence):
            return seed
        required = _BYTE_BOUND_OPERATIONS.get(provider_name)
        if not required:
            return seed
        bounds = provider_operation_byte_bounds(provider_name)
        if any(operation not in bounds for operation in required):
            return seed
        if not isinstance(contract, dict):
            return seed
        untracked = list(contract.get("untracked_constraints") or [])
        byte_constraint = next(
            (
                item
                for item in untracked
                if isinstance(item, dict)
                and str(item.get("unit") or "").lower() in {"byte", "bytes"}
            ),
            None,
        )
        if byte_constraint is None:
            return seed
        contract["untracked_constraints"] = [
            item for item in untracked if item is not byte_constraint
        ]
        dimensions = list(contract.get("dimensions") or [])
        if not any(
            item.get("name") == byte_constraint.get("name")
            for item in dimensions
            if isinstance(item, dict)
        ):
            dimensions.append(dict(byte_constraint))
        contract["dimensions"] = dimensions
        contract["reset"] = call_reset or "provider_defined"
        contract["unknown_dimensions"] = []
        for dimension in dimensions:
            if not isinstance(dimension, dict):
                continue
            if dimension.get("name") in {"calls_per_day", "calls_per_minute"}:
                dimension["reset"] = call_reset or "provider_defined"
                if call_reset:
                    dimension.pop("safety_reset", None)
                else:
                    dimension["safety_reset"] = "rolling"
            elif dimension.get("name") == byte_constraint.get("name"):
                dimension["reset"] = bandwidth_reset
        contract["dimension_costs_required"] = True
        contract["operation_costs_required"] = True
        contract["source"] = (
            f"{contract.get('source', 'FMP account and pricing evidence')} plus "
            + (
                "the documented 3 PM EST (UTC-05:00) daily reset and rolling-30-day bandwidth window"
                if plan == "basic" and call_reset == "15:00 UTC-05:00"
                else "the reviewed provider call reset and rolling-30-day bandwidth window"
            )
        )
        seed["quota_contract"] = contract
        seed["quota_source"] = (
            "FMP Basic 3 PM EST (UTC-05:00) daily reset and rolling-30-day bandwidth contract"
            if plan == "basic" and call_reset == "15:00 UTC-05:00"
            else "FMP account allowance plus provider-specific reviewed safety windows"
        )
        seed["_byte_reservation_bounds"] = bounds
        return seed
    if provider_name == "fred":
        # FRED v1 publishes a 120/minute threshold but does not publish its
        # counter scope or reset boundary. For the owner's explicitly
        # accepted private-use deployment, enforce that exact ceiling with a
        # shared application API-key bucket and a rolling 60-second envelope.
        # Keep the provider's scope/reset uncertainty visible as metadata; a
        # 429 remains a provider-wide stop signal. Other deployments retain
        # the explicit reviewed-controls path below.
        if provider_reviewed_flag(
            getattr(settings, "PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", False)
        ):
            contract = seed.get("quota_contract")
            if isinstance(contract, dict):
                contract["unknown_dimensions"] = []
                contract["provider_enforcement_scope"] = "unpublished"
                contract["provider_reset_boundary"] = "unpublished"
                contract["unresolved_provider_facts"] = [
                    "v1_enforcement_scope",
                    "provider_adjustable_limits",
                    "requests_per_minute_reset_boundary",
                ]
                contract["application_admission_policy"] = (
                    "shared api-key bucket with a rolling 60-second cap at the "
                    "published 120-requests/minute ceiling; stop on provider 429"
                )
                for dimension in contract.get("dimensions") or []:
                    if not isinstance(dimension, dict):
                        continue
                    if dimension.get("name") == "requests_per_minute":
                        dimension["scope"] = "api_key"
                        dimension["quota_group"] = "api_key"
                        dimension["safety_reset"] = "rolling"
                seed["quota_scope"] = "api_key"
                seed["quota_source"] = (
                    "FRED v1 published 120/minute threshold plus shared-key "
                    "rolling application safety envelope"
                )
            return seed

        scope = str(getattr(settings, "FRED_REVIEWED_LIMIT_SCOPE", "") or "").strip()
        reviewed_limit = provider_positive_integer(
            getattr(settings, "FRED_REVIEWED_REQUESTS_PER_MINUTE", 0)
        )
        quota_evidence = str(getattr(settings, "FRED_REVIEWED_QUOTA_EVIDENCE", "") or "").strip()
        reviewed_reset = str(getattr(settings, "FRED_REVIEWED_RESET", "") or "").strip()
        reset_evidence = str(getattr(settings, "FRED_RESET_EVIDENCE", "") or "").strip()
        allowed_scopes = {"api_key", "account", "ip", "deployment"}
        if (
            scope in allowed_scopes
            and reviewed_limit is not None
            and reviewed_limit <= 120
            and quota_evidence
            and provider_quota_reset_is_admission_safe(reviewed_reset)
            and reset_evidence
            and not fred_data_use_controls_missing()
            and not fred_series_rights_missing()
            and isinstance(seed.get("quota_contract"), dict)
        ):
            contract = seed["quota_contract"]
            contract["unknown_dimensions"] = []
            for dimension in contract.get("dimensions") or []:
                if isinstance(dimension, dict) and dimension.get("name") == "requests_per_minute":
                    dimension["limit"] = reviewed_limit
                    dimension["scope"] = scope
                    dimension["quota_group"] = scope
                    dimension["reset"] = reviewed_reset
            contract["reset"] = reviewed_reset
            contract["unknown_dimensions"] = []
            contract["source"] = (
                f"{contract.get('source', 'FRED v1 errors')} plus separately reviewed "
                "quota-scope, reset, and persisted-storage authority evidence"
            )
            seed["quota_scope"] = scope
            seed["quota_source"] = (
                "FRED v1 threshold plus provider-confirmed quota and storage-rights evidence"
            )
        return seed
    required = _BYTE_BOUND_OPERATIONS.get(provider_name)
    if not required:
        return seed
    bounds = provider_operation_byte_bounds(provider_name)
    if any(operation not in bounds for operation in required):
        return seed
    contract = seed.get("quota_contract")
    if not isinstance(contract, dict):
        return seed
    untracked = list(contract.get("untracked_constraints") or [])
    byte_constraint = next(
        (
            item
            for item in untracked
            if isinstance(item, dict) and str(item.get("unit") or "").lower() in {"byte", "bytes"}
        ),
        None,
    )
    if byte_constraint is None:
        return seed
    contract["untracked_constraints"] = [item for item in untracked if item is not byte_constraint]
    dimensions = list(contract.get("dimensions") or [])
    if not any(
        item.get("name") == byte_constraint.get("name")
        for item in dimensions
        if isinstance(item, dict)
    ):
        dimensions.append(dict(byte_constraint))
    contract["dimensions"] = dimensions
    contract["dimension_costs_required"] = True
    contract["operation_costs_required"] = True
    seed["quota_contract"] = contract
    seed["_byte_reservation_bounds"] = bounds
    return seed
