import json
import os
from copy import deepcopy
from datetime import UTC, datetime

from pydantic import field_validator
from pydantic_core import PydanticUseDefault
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    SettingsConfigDict,
)

_SETTINGS_USE_CODE_DEFAULT = "__CODE_DEFAULT__"
_JSON_SEED_OVERRIDE_FIELDS = {
    "PROVIDER_RATE_LIMIT_SEEDS",
    "PROVIDER_FRESHNESS_SEEDS",
    "PROVIDER_USAGE_PROFILE_SEEDS",
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
    MARKET_UNIVERSE_RECONCILIATION_ENABLED: bool = False
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
    TOKENIZED_EVENT_REFRESH_PAGE_SIZE: int = 100
    ETF_HOLDINGS_REFRESH_ENABLED: bool = False
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
    # Paid adapters may be configured and audited without entering normal
    # routing.  An explicit deployment setting is required to opt them in.
    ALLOW_PAID_PROVIDER_ROUTING: bool = False
    # Deployment-wide emergency switch. Provider descriptors and usage remain
    # visible when off, but no provider adapter may be selected for a call.
    PROVIDER_ROUTING_ENABLED: bool = True
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
        # Nasdaq covers the documented NMS files, while the explicitly
        # configured FINRA directory is the fail-closed OTC counterpart. The
        # latter has no inferred quota and therefore remains non-routable until
        # its source, terms, and quota contract are operator-approved.
        "universe_discovery": [
            "alpaca",
            "edgar",
            "massive",
            "nasdaq",
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
                },
            },
            "tokens_per_minute": 200,
            "quota_scope": "account",
            "quota_source": "Alpaca market data API documentation",
        },
        "massive": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "requests_per_minute",
                        "limit": 5,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://massive.com/stocks",
                    }
                ],
                # Massive publishes five calls/minute but does not document
                # whether the minute pool is fixed or rolling. Keep the
                # conservative ceiling visible while routing remains closed
                # until the active reset boundary is evidenced.
                "reset": "provider_defined",
                "unknown_dimensions": ["requests_per_minute_reset_boundary"],
            },
            "tokens_per_minute": 5,
            "quota_scope": "api_key",
            "quota_source": "Massive Stocks Basic plan documentation",
        },
        "alpha_vantage": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "requests_per_day",
                        "limit": 25,
                        "window_seconds": 86400,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://www.alphavantage.co/support/",
                    }
                ],
                # The provider publishes the daily allowance but not its
                # reset boundary or timezone. A local rolling window would be
                # a convenient safety approximation, not a provider fact, so
                # keep the dimension explicitly fail-closed until a current
                # reset-bearing observation or provider confirmation exists.
                "reset": "provider_defined",
                "unknown_dimensions": ["requests_per_day_reset_boundary"],
            },
            "quota_scope": "api_key",
            "quota_source": "Alpha Vantage support documentation",
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
                    }
                ],
                "reset": "calendar_day_est",
            },
            "quota_scope": "deployment",
            "quota_source": "client-imposed one-refresh-per-market-day ceiling; Nasdaq does not publish a numeric quota",
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
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "requests_per_second",
                        "limit": 10,
                        "window_seconds": 1,
                        "unit": "requests",
                        "scope": "ip",
                        "quota_group": "ip",
                        "source": "https://www.sec.gov/filergroup/announcements-old/new-rate-control-limits",
                    }
                ],
                # SEC publishes the 10-requests/second ceiling but does not
                # define whether the enforcement window is fixed or rolling.
                # Keep the dimension auditable but non-admission-safe until
                # current provider/account evidence is explicitly reviewed.
                "reset": "provider_defined",
                "unknown_dimensions": ["requests_per_second_reset_boundary"],
            },
            "quota_scope": "ip",
            "quota_source": "SEC fair-access policy",
        },
        "fred": {
            "quota_contract": {
                # FRED v1 documents a 120-requests/minute threshold before
                # HTTP 429, but does not publish its enforcement scope. FRED
                # v2's separate 2-requests/second rule must not be applied to
                # this v1 adapter.
                "dimensions": [
                    {
                        "name": "requests_per_minute",
                        "limit": 120,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "provider_defined",
                        "source": "https://fred.stlouisfed.org/docs/api/fred/errors.html",
                        "reset": "provider_defined",
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
                        # explicit while refusing to turn the month into a
                        # guessed rolling 31-day window.
                        "limit": 10_000_000_000,
                        "window_seconds": 2678400,
                        "unit": "bytes",
                        "scope": "public_credential",
                        "quota_group": "public_credential",
                        "source": "https://developer.finra.org/support",
                        "reset": "provider_defined",
                        "limit_basis": "decimal_bytes_conservative_for_published_GB",
                    },
                ],
                "reset": "provider_defined",
                "unknown_dimensions": ["download_bytes_month_reset_boundary"],
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
                # ORF file downloads have a documented platform ceiling, but
                # product entitlement, MFA, file-download cadence, and the
                # exact account/credential scope remain operator-controlled.
                # Never turn the platform ceiling into a guessed operation
                # cost or reset boundary.
                "dimensions": [],
                "unknown_dimensions": [
                    "orf_product_entitlement_and_mfa",
                    "file_download_quota_and_reset",
                    "data_use_terms",
                    "redistribution_rights",
                ],
                "reset": "provider_defined",
                "operation_costs_required": True,
                "source": "https://www.finra.org/sites/default/files/2024-08/Equity_API_File_Downloads_ORF.pdf",
            },
            "quota_scope": "unknown",
            "quota_source": "FINRA ORF file-download specification; entitlement and account limits unresolved",
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
                        "reset": "rolling",
                    },
                    {
                        "name": "calls_per_month",
                        "limit": 10000,
                        "window_seconds": 2678400,
                        "unit": "requests",
                        "scope": "demo_api_key",
                        "quota_group": "demo_api_key",
                        "source": "https://www.coingecko.com/en/api/pricing",
                        # CoinGecko explicitly documents that monthly call
                        # credits reset on the first day of each month,
                        # regardless of subscription/billing date.
                        "reset": "calendar_month_utc",
                    },
                ],
                "reset": "per_dimension",
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
                    }
                ],
                "reset": "per_dimension",
                "dynamic_endpoint_weights": True,
                "account_usage_bootstrap": {
                    "enabled": True,
                    "source": "application_policy:provider_native_baseline_bootstrap",
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
                    }
                ],
                "reset": "rolling",
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
            "quota_source": "Dinari Enterprise API documentation (numeric limit not published)",
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
                        "source": "https://www.tiingo.com/about/pricing",
                        # Tiingo publishes the distinct-symbol pool but does
                        # not state its reset anchor. Do not turn that
                        # provider-defined boundary into a guessed rolling
                        # window; routing remains blocked until reviewed.
                        "reset": "provider_defined",
                    },
                    {
                        "name": "requests_per_hour",
                        "limit": 50,
                        "window_seconds": 3600,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://www.tiingo.com/documentation/general",
                        # Tiingo documents that the hourly pool resets every
                        # hour, but does not identify whether the boundary is
                        # fixed/calendar or rolling. Keep the boundary
                        # provider-defined until that admission detail is
                        # explicitly reviewed; no rolling window is inferred.
                        "reset": "provider_defined",
                    },
                    {
                        "name": "requests_per_day",
                        "limit": 1000,
                        "window_seconds": 86400,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://www.tiingo.com/about/pricing",
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
                        "source": "https://www.tiingo.com/about/pricing",
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
                        "name": "credits_per_day",
                        "limit": 800,
                        "window_seconds": 86400,
                        "unit": "credits",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://twelvedata.com/pricing",
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
                },
            },
            "tokens_per_minute": 8,
            "quota_scope": "api_key",
            "quota_source": "Twelve Data Basic pricing/credits documentation",
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
                    },
                    {
                        "name": "hard_calls_per_second",
                        "limit": 30,
                        "window_seconds": 1,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://finnhub.io/docs/api",
                    },
                ],
                # The free account exposes two independent request-rate
                # dimensions. Record the operation map for both instead of
                # leaving the hard per-second reservation implicit.
                "dimension_costs_required": True,
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
                        # The Free Starter plan card publishes a 20/min
                        # request ceiling. EODHD's general API-limits page and
                        # Quick Start claim 1,000/min for every plan, while the
                        # configured account has exposed a native 1,200/min
                        # header. Keep the conservative 20/min seed visible for
                        # audit only; the unresolved account entitlement and
                        # reset boundary make this dimension non-routable until
                        # reviewed evidence is supplied.
                        "limit": 20,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://eodhd.com/lp/historical-eod-api",
                        "reset": "provider_defined",
                        "limit_basis": "conservative seed pending account-specific review",
                    },
                    {
                        "name": "calls_per_day",
                        "limit": 20,
                        "window_seconds": 86400,
                        "unit": "calls",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://eodhd.com/lp/historical-eod-api",
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
                    # The native /user endpoint can safely establish the
                    # daily counter while the conflicting minute pool stays
                    # unresolved. These names are the only unknowns that the
                    # bootstrap path may explicitly observe without making
                    # ordinary data routing eligible.
                    "allowed_unknown_dimensions": [
                        "published_minute_limit_conflict",
                        "requests_per_minute_reset_boundary",
                    ],
                },
                "source_conflicts": [
                    {
                        "source": "https://eodhd.com/financial-apis/api-limits",
                        "claim": "1,000 requests per minute on every plan",
                        "conflicts_with": "https://eodhd.com/lp/historical-eod-api",
                    }
                ],
                "unknown_dimensions": [
                    "published_minute_limit_conflict",
                    "requests_per_minute_reset_boundary",
                ],
            },
            "tokens_per_minute": 20,
            "quota_scope": "api_key",
            "quota_source": (
                "EODHD Free Starter plan pricing and API limits documentation: "
                "https://eodhd.com/lp/historical-eod-api; "
                "https://eodhd.com/financial-apis/api-limits"
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
                        "source": "operator_account_dashboard_2026-09-07",
                        "reset": "provider_defined",
                    }
                ],
                "reset": "provider_defined",
                "untracked_constraints": [
                    {
                        "name": "bandwidth_bytes_per_30_days",
                        # The operator account reports "512 MB" without a
                        # binary-unit declaration. Keep the hard ceiling at
                        # the decimal-byte value rather than overestimating.
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
                "unknown_dimensions": [
                    "calls_daily_reset_anchor",
                ],
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
                        "limit_basis": (
                            "conservative lower published value pending provider clarification"
                        ),
                    }
                ],
                # The current pricing page states 100/month while the FAQ
                # still states 1,000/month. Keep the lower value only as a
                # conservative reservation ceiling and expose the conflict
                # explicitly; routing remains non-routable until the account
                # plan and reset boundary are clarified.
                "unknown_dimensions": [
                    "published_monthly_limit_conflict",
                    "monthly_cap_reset_boundary",
                ],
                "source_conflicts": [
                    {
                        "source": "https://marketstack.com/faq",
                        "claim": "1,000 requests per month",
                        "conflicts_with": "https://marketstack.com/pricing",
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
                "reset": "provider_defined",
            },
            "quota_scope": "api_key",
            "quota_source": (
                "Marketstack free-plan pricing and FAQ; published monthly limits conflict"
            ),
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
                # Account introspection is a provider request and must be
                # visible in the same durable coordinator as data reads. The
                # endpoint itself is not charged against the daily credit
                # pool; its request still occupies the reviewed concurrency
                # dimension below. Keep the positive operation cost so the
                # call remains explicitly routable, and exclude only the
                # provider-credit dimension with an empty per-operation map.
                "fetch_account_usage": 1,
            },
            "dimension_costs": {
                "credits_per_day": {
                    "fetch_account_usage": {},
                },
            },
        },
        "coinbase": {
            "mode": "call_count",
            "unit_label": "requests",
            "operation_costs": {
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
            # A cold OAuth token cache adds one token request before each
            # authenticated dataset request. Reserve the conservative
            # two-request upper bound even when a warm process reuses a token.
            "operation_costs": {
                "fetch_short_interest": 2,
                "fetch_market_events": 2,
            },
            # FINRA documents a 3 MB maximum synchronous response. Reserve
            # that upper bound against the credential's monthly download
            # budget before execution, then settle to measured bytes.
            "dimension_costs": {
                "asynchronous_requests_per_minute_dataset": {},
                "download_bytes_per_calendar_month": {
                    "fetch_short_interest": 3_000_000,
                    "fetch_market_events": 3_000_000,
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
        # FINRA OTC DAPI page count depends on the authoritative record-total
        # and payload-capped response sizes. An empty map is deliberate: the
        # quota contract marks operation costs required, so routing remains
        # non-routable until an operator supplies a positive reviewed bound.
        "finra_otc_directory": {
            "mode": "call_count",
            "unit_label": "requests",
            "operation_costs": {},
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
                # The documented /user endpoint itself consumes one API call
                # and one request. Keep it explicitly metered; its response
                # may then reconcile the current daily baseline.
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
                    "fetch_account_usage": 1,
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
        },
        "finnhub": {
            "mode": "call_count",
            "unit_label": "requests",
            "operation_costs": {
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
                "discover_universe_page": 1,
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
                "get_tokenized_price": 2,
            },
        },
        "dinari": {
            "mode": "call_count",
            "unit_label": "requests",
            "operation_costs": {
                "discover_tokenized_assets": 1,
                "get_tokenized_asset": 1,
                "get_tokenized_price": 2,
                "get_tokenized_quote": 2,
                "fetch_tokenized_historical_prices": 2,
                "fetch_tokenized_news": 2,
                "fetch_tokenized_dividends": 2,
                "fetch_tokenized_splits": 2,
                # Symbol-scoped corporate actions resolve metadata once and
                # then read dividends and splits. The global split path costs
                # one request but safely over-reserves this compound bound.
                "fetch_tokenized_corporate_actions": 3,
            },
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
                }
            },
            "venue_coverage": "IEX US equities; provider-defined universe",
            "freshness_semantics": "Delayed/limited free feed",
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
            "usage_terms": "Stocks Basic is listed as 5 API calls/minute and two years of historical data; confirm plan licensing and redistribution terms before production use.",
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
            "venue_coverage": "US NMS venues represented in official directory files",
            "freshness_semantics": "Directory publication/update time",
        },
        "finra_otc_directory": {
            "configured_plan": "unreviewed",
            "is_free": True,
            "authentication_required": True,
            "usage_terms": (
                "FINRA ORF active/inactive security-master files require a product entitlement, "
                "ORF Web Access Agreement, MFA, and review of the specific equity-data and "
                "API terms; redistribution and bulk-service use are not inferred. "
                "https://www.finra.org/filing-reporting/orf/technical-notices/reminder-otc-trade-reporting-facility-orf-migration"
            ),
            "history_depth": "Current active and inactive ORF security-master snapshots",
            "venue_coverage": "OTC equity securities represented by FINRA ORF files",
            "freshness_semantics": "Provider file publication time and effective/inactive timestamps",
            "live_probe_status": "blocked_until_orf_entitlement",
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
            "usage_terms": "Free demo tier with published rate limits.",
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
            "usage_terms": "Marketstack free plan; 100 monthly requests and provider licensing terms apply.",
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
            "configured_plan": "free-20-day",
            "is_free": True,
            "authentication_required": True,
            "usage_terms": (
                "EODHD Free Starter: 20 API-call credits/day, 20 requests/minute, and "
                "documented free access to EOD history (one-year range) and exchange-symbol "
                "lists. Fundamentals and other paid-plan endpoints are not included."
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
                    # global paid-routing switch is enabled; a future paid
                    # subscription must be explicitly operator-reviewed.
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
            "usage_terms": "Kraken public market-data endpoints and safe-frequency guidance apply.",
            "history_depth": "Current pair and ticker observations",
            "venue_coverage": "Kraken xStocks pairs where published",
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
    # not publish a reset boundary/timezone. Keep routing fail-closed until an
    # operator records a reviewed boundary and its evidence. This remains
    # configurable so a future plan can update the quota without code changes.
    ALPHA_VANTAGE_REVIEWED_RESET: str = ""
    ALPHA_VANTAGE_QUOTA_EVIDENCE: str = ""
    MARKETDATA_API_KEY: str = ""
    FMP_API_KEY: str = ""
    TIINGO_API_KEY: str = ""
    # Provider-specific byte ceilings are deliberately empty by default.  A
    # deployment may set these as JSON maps (operation -> maximum response
    # bytes) only after reviewing the provider's current endpoint contract.
    # Without a complete map the corresponding bandwidth-constrained provider
    # remains fail-closed and non-routable.
    TIINGO_OPERATION_BYTE_BOUNDS: dict[str, int] = {}
    # Tiingo leaves the 500-unique-symbol reset anchor and 50/hour boundary
    # unspecified in the reviewed sources. Keep both pools fail-closed until
    # independently reviewed reset semantics and evidence are configured.
    TIINGO_REVIEWED_UNIQUE_SYMBOL_RESET: str = ""
    TIINGO_REVIEWED_HOURLY_RESET: str = ""
    TIINGO_UNIQUE_SYMBOL_QUOTA_EVIDENCE: str = ""
    TIINGO_HOURLY_QUOTA_EVIDENCE: str = ""
    FMP_OPERATION_BYTE_BOUNDS: dict[str, int] = {}
    # FMP publishes separate daily-call and trailing-30-day bandwidth pools.
    # The official pricing page establishes the bandwidth window, while the
    # daily-call reset boundary remains provider-defined. Keep the bandwidth
    # reset override configurable for future plan changes, but do not require
    # a duplicate setting for the current documented contract.
    FMP_REVIEWED_DAILY_RESET: str = ""
    FMP_REVIEWED_BANDWIDTH_RESET: str = ""
    FMP_DAILY_QUOTA_EVIDENCE: str = ""
    FMP_BANDWIDTH_QUOTA_EVIDENCE: str = ""
    TWELVE_DATA_API_KEY: str = ""
    FINNHUB_API_KEY: str = ""
    # Finnhub publishes independent minute and second request ceilings. Keep
    # each reset boundary separately fail-closed until its current semantics
    # are reviewed; never collapse the two pools into one generic window.
    FINNHUB_REVIEWED_MINUTE_RESET: str = ""
    FINNHUB_REVIEWED_SECOND_RESET: str = ""
    FINNHUB_MINUTE_QUOTA_EVIDENCE: str = ""
    FINNHUB_SECOND_QUOTA_EVIDENCE: str = ""
    MARKETSTACK_API_KEY: str = ""
    # Marketstack's published monthly cap conflicts across official pages and
    # its reset boundary is not stated. Keep routing fail-closed until the
    # current account plan, monthly limit, boundary, and evidence are reviewed.
    MARKETSTACK_REVIEWED_MONTHLY_LIMIT: int = 0
    MARKETSTACK_REVIEWED_MONTHLY_RESET: str = ""
    MARKETSTACK_QUOTA_EVIDENCE: str = ""
    # Marketstack ticker discovery is venue-scoped. Do not silently default
    # to one exchange or claim a whole-US universe without operator scope.
    MARKETSTACK_DISCOVERY_EXCHANGE: str = ""
    EODHD_API_KEY: str = ""
    TRADIER_API_KEY: str = ""
    MARKETDATA_APP_API_KEY: str = ""
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
    # EODHD publishes conflicting minute-pool limits (the Free Starter card
    # says 20/min while the general limits page says 1,000/min). Keep that
    # pool non-routable until the operator records the exact account limit,
    # calculable reset boundary, and current evidence. The native /user
    # snapshot may still bootstrap the independently documented daily pool.
    EODHD_REVIEWED_MINUTE_LIMIT: int = 0
    EODHD_REVIEWED_MINUTE_RESET: str = ""
    EODHD_MINUTE_QUOTA_EVIDENCE: str = ""
    # xStocks public-read access does not by itself authorize automated,
    # persistent collection or establish deployment-jurisdiction eligibility.
    # Keep all application routes fail-closed until both dimensions have
    # current operator evidence.
    XSTOCKS_MARKET_DATA_USE_AUTHORIZED: bool = False
    XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE: str = ""
    XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE: str = ""
    XSTOCKS_MARKET_DATA_USE_REVIEWED_AT: datetime | None = None
    XSTOCKS_MARKET_DATA_USE_EXPIRES_AT: datetime | None = None
    XSTOCKS_MARKET_DATA_USE_JURISDICTION_AUTHORIZED: bool = False
    XSTOCKS_MARKET_DATA_USE_JURISDICTION_EVIDENCE: str = ""
    # Bybit's xStocks endpoints are public, but the provider documents an
    # egress restriction for US/Mainland-China IPs.  A public response is not
    # proof that this deployment may automate or persist the data.  Keep the
    # adapter fail-closed until the deployment egress and the reviewed use
    # scope are recorded explicitly.
    BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORIZED: bool = False
    BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE: str = ""
    BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE: str = ""
    BYBIT_XSTOCKS_MARKET_DATA_USE_REVIEWED_AT: datetime | None = None
    BYBIT_XSTOCKS_MARKET_DATA_USE_EXPIRES_AT: datetime | None = None
    BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_AUTHORIZED: bool = False
    BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_EVIDENCE: str = ""
    DINARI_API_KEY_ID: str = ""
    DINARI_API_SECRET_KEY: str = ""
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
    KRAKEN_API_KEY: str = ""
    # Alpaca Markets — US equity + crypto OHLCV, corporate actions, universe
    ALPACA_API_KEY: str = ""
    ALPACA_SECRET_KEY: str = ""
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
    # Massive publishes the Stocks Basic five-calls/minute ceiling but does
    # not specify whether its minute bucket is fixed or rolling. Keep the
    # provider-specific reset and evidence explicit; never infer a window
    # from the headline allowance.
    MASSIVE_REVIEWED_RESET: str = ""
    MASSIVE_QUOTA_EVIDENCE: str = ""
    # Massive's split and dividend endpoints are independently cursor-paginated;
    # this bound applies to each endpoint and the runtime reserves twice it.
    MASSIVE_CORPORATE_ACTIONS_MAX_PAGES: int = 0
    # Massive's free Stocks Basic terms grant personal, non-business,
    # non-commercial, non-redistributed use only.  Keep every Massive route
    # fail-closed until the deployment records that exact use scope.
    MASSIVE_MARKET_DATA_USE_AUTHORIZED: bool = False
    MASSIVE_MARKET_DATA_USE_AUTHORITY_REFERENCE: str = ""
    MASSIVE_MARKET_DATA_USE_AUTHORITY_SCOPE: str = ""
    MASSIVE_MARKET_DATA_USE_REVIEWED_AT: datetime | None = None
    MASSIVE_MARKET_DATA_USE_EXPIRES_AT: datetime | None = None
    NASDAQ_USER_AGENT: str = "charting-platform market-data-universe"
    # FRED (Federal Reserve Economic Data) — rates, macro, forex series
    FRED_API_KEY: str = ""
    # FRED v1's numeric threshold does not identify its quota scope. Current
    # terms prohibit persistence and specified software-development uses by
    # default; individual series can carry separate rights. All three must be
    # reviewed before the adapter can make a provider request.
    FRED_REVIEWED_LIMIT_SCOPE: str = ""
    FRED_REVIEWED_REQUESTS_PER_MINUTE: int = 0
    FRED_REVIEWED_QUOTA_EVIDENCE: str = ""
    FRED_REVIEWED_RESET: str = ""
    FRED_RESET_EVIDENCE: str = ""
    FRED_PERSISTED_STORAGE_AUTHORIZED: bool = False
    FRED_PERSISTED_STORAGE_AUTHORITY_EVIDENCE: str = ""
    FRED_AUTOMATED_USE_AUTHORIZED: bool = False
    FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE: str = ""
    FRED_SERIES_RIGHTS_EVIDENCE: dict[str, str] = {}
    # CoinGecko — crypto universe discovery and metadata (free demo key)
    COINGECKO_API_KEY: str = ""
    # SEC EDGAR — no key required; User-Agent identifies your app to SEC servers
    EDGAR_USER_AGENT: str = ""
    # SEC publishes the 10-requests/second ceiling but not its reset-window
    # semantics. Keep EDGAR routing fail-closed until both are reviewed.
    EDGAR_REVIEWED_RESET: str = ""
    EDGAR_QUOTA_EVIDENCE: str = ""
    FINRA_CLIENT_ID: str = ""
    FINRA_CLIENT_SECRET: str = ""
    FINRA_TOKEN_URL: str = "https://ews.fip.finra.org/fip/rest/ews/oauth2/access_token"
    FINRA_API_BASE_URL: str = "https://api.finra.org"
    FINRA_SHORT_INTEREST_URL: str = ""
    FINRA_OTC_DAILY_LIST_URL: str = ""
    # ``legacy_candidate`` preserves the historical DAPI/pipe-delimited
    # adapter for explicitly reviewed sources. ``finra_orf_security_master``
    # selects FINRA's currently documented ORF file-download pair and requires
    # both active and inactive snapshots plus the FINRA OAuth credentials.
    # The source remains fail-closed until the ORF Web Access Agreement, MFA,
    # terms, completeness, and redistribution reviews are recorded below.
    FINRA_OTC_SOURCE_KIND: str = "legacy_candidate"
    FINRA_OTC_SYMBOL_DIRECTORY_URL: str = ""
    FINRA_OTC_INACTIVE_SECURITY_MASTER_URL: str = ""
    # A partitioned directory source's cold refresh is response/page-count
    # dependent. A deployment must provide a reviewed conservative request
    # charge per operation instead of inheriting a one-request default.
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
    FINRA_OTC_POLL_INTERVAL_SECONDS: int = 0
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
    PROVIDER_REQUEST_LOG_RETENTION_DAYS: int = 30
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
    PROVIDER_QUOTA_LEDGER_PATH: str = (
        "~/.config/charting-platform/provider-quota/usage.sqlite3"
    )
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
    LATEST_PRICE_SNAPSHOT_RETENTION_DAYS: int = 30
    INSTRUMENT_SEARCH_SNAPSHOT_RETENTION_DAYS: int = 14
    UNIVERSE_DISCOVERY_SNAPSHOT_RETENTION_DAYS: int = 30
    INSTRUMENT_PROFILE_SNAPSHOT_RETENTION_DAYS: int = 365
    INSTRUMENT_IDENTIFIER_SNAPSHOT_RETENTION_DAYS: int = 3650
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
        "XSTOCKS_MARKET_DATA_USE_REVIEWED_AT",
        "XSTOCKS_MARKET_DATA_USE_EXPIRES_AT",
        "BYBIT_XSTOCKS_MARKET_DATA_USE_REVIEWED_AT",
        "BYBIT_XSTOCKS_MARKET_DATA_USE_EXPIRES_AT",
        mode="before",
    )
    @classmethod
    def parse_optional_coinbase_authority_timestamps(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator(
        "OPTION_QUOTE_HISTORY_PROVIDER_PRIORITY",
        "PROVIDER_CHAIN_SEEDS",
        "PROVIDER_RATE_LIMIT_SEEDS",
        "PROVIDER_FRESHNESS_SEEDS",
        "PROVIDER_USAGE_PROFILE_SEEDS",
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
    return provider_quota_reset_is_known(candidate) and candidate not in _UNRESOLVED_PROVIDER_QUOTA_RESETS


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


def coinbase_market_data_use_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Require current, scoped written authority before Coinbase requests."""

    now = now or datetime.now(UTC)
    source = source or settings
    missing: list[str] = []
    if not provider_reviewed_flag(
        getattr(source, "COINBASE_MARKET_DATA_USE_AUTHORIZED", False)
    ):
        missing.append("COINBASE_MARKET_DATA_USE_AUTHORIZED")
    if not str(
        getattr(source, "COINBASE_MARKET_DATA_USE_AUTHORITY_REFERENCE", "") or ""
    ).strip():
        missing.append("COINBASE_MARKET_DATA_USE_AUTHORITY_REFERENCE")
    if str(
        getattr(source, "COINBASE_MARKET_DATA_USE_AUTHORITY_SCOPE", "") or ""
    ).strip() != "internal_automated_persistent_nonredistributed":
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


def massive_market_data_use_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Require an explicit attestation for Massive's personal-use license.

    Massive's free Stocks Basic terms are narrower than a generic API
    entitlement: they permit personal, non-business, non-commercial use and
    prohibit redistribution/third-party application use.  The application
    cannot infer that legal scope from a configured key, so all routes remain
    quarantined until the deployment records it explicitly.
    """

    now = now or datetime.now(UTC)
    source = source or settings
    missing: list[str] = []
    if not provider_reviewed_flag(
        getattr(source, "MASSIVE_MARKET_DATA_USE_AUTHORIZED", False)
    ):
        missing.append("MASSIVE_MARKET_DATA_USE_AUTHORIZED")
    if not str(
        getattr(source, "MASSIVE_MARKET_DATA_USE_AUTHORITY_REFERENCE", "") or ""
    ).strip():
        missing.append("MASSIVE_MARKET_DATA_USE_AUTHORITY_REFERENCE")
    if str(
        getattr(source, "MASSIVE_MARKET_DATA_USE_AUTHORITY_SCOPE", "") or ""
    ).strip() != "personal_noncommercial_nonredistributed":
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


def xstocks_market_data_use_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Require current xStocks automation and jurisdiction evidence."""

    now = now or datetime.now(UTC)
    source = source or settings
    missing: list[str] = []
    if not provider_reviewed_flag(
        getattr(source, "XSTOCKS_MARKET_DATA_USE_AUTHORIZED", False)
    ):
        missing.append("XSTOCKS_MARKET_DATA_USE_AUTHORIZED")
    if not str(
        getattr(source, "XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE", "") or ""
    ).strip():
        missing.append("XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE")
    if str(
        getattr(source, "XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE", "") or ""
    ).strip() != "internal_automated_persistent_nonredistributed":
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
    if not provider_reviewed_flag(
        getattr(source, "XSTOCKS_MARKET_DATA_USE_JURISDICTION_AUTHORIZED", False)
    ):
        missing.append("XSTOCKS_MARKET_DATA_USE_JURISDICTION_AUTHORIZED")
    if not str(
        getattr(source, "XSTOCKS_MARKET_DATA_USE_JURISDICTION_EVIDENCE", "") or ""
    ).strip():
        missing.append("XSTOCKS_MARKET_DATA_USE_JURISDICTION_EVIDENCE")
    return missing


def bybit_xstocks_market_data_use_authority_missing(
    now: datetime | None = None, *, source: object | None = None
) -> list[str]:
    """Require current Bybit xStocks use and non-restricted egress evidence.

    Bybit's public xStocks surface is not automatically a permitted source for
    an automated/persistent deployment.  The egress control is separate from
    the generic xStocks authority because Bybit documents provider-specific
    IP-jurisdiction restrictions (US/Mainland China).
    """

    now = now or datetime.now(UTC)
    source = source or settings
    missing: list[str] = []
    if not provider_reviewed_flag(
        getattr(source, "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORIZED", False)
    ):
        missing.append("BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORIZED")
    if not str(
        getattr(source, "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE", "") or ""
    ).strip():
        missing.append("BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE")
    if str(
        getattr(source, "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE", "") or ""
    ).strip() != "internal_automated_persistent_nonredistributed":
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
        getattr(source, "BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_EVIDENCE", "")
        or ""
    ).strip():
        missing.append("BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_EVIDENCE")
    return missing


def fred_data_use_controls_missing(source: object | None = None) -> list[str]:
    """Require reviewed persisted-data and automated-use authority for FRED."""

    source = source or settings
    missing: list[str] = []
    if not provider_reviewed_flag(
        getattr(source, "FRED_PERSISTED_STORAGE_AUTHORIZED", False)
    ):
        missing.append("FRED_PERSISTED_STORAGE_AUTHORIZED")
    if not str(
        getattr(source, "FRED_PERSISTED_STORAGE_AUTHORITY_EVIDENCE", "") or ""
    ).strip():
        missing.append("FRED_PERSISTED_STORAGE_AUTHORITY_EVIDENCE")
    if not provider_reviewed_flag(
        getattr(source, "FRED_AUTOMATED_USE_AUTHORIZED", False)
    ):
        missing.append("FRED_AUTOMATED_USE_AUTHORIZED")
    if not str(
        getattr(source, "FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE", "") or ""
    ).strip():
        missing.append("FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE")
    return missing


def fred_series_rights_authorized(series_id: str, source: object | None = None) -> bool:
    """Return whether this exact provider series has recorded rights evidence."""

    source = source or settings
    rights = getattr(source, "FRED_SERIES_RIGHTS_EVIDENCE", {})
    if not isinstance(rights, dict):
        return False
    evidence = rights.get(series_id)
    return isinstance(evidence, str) and bool(evidence.strip())


def fred_series_rights_missing(source: object | None = None) -> list[str]:
    """Return missing rights records for every series exposed by the adapter."""

    source = source or settings
    rights = getattr(source, "FRED_SERIES_RIGHTS_EVIDENCE", {})
    if not isinstance(rights, dict):
        return ["FRED_SERIES_RIGHTS_EVIDENCE"]
    return (
        ["FRED_SERIES_RIGHTS_EVIDENCE"]
        if any(
            not isinstance(rights.get(series_id), str)
            or not rights[series_id].strip()
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
                account_plan_metadata["account_plan_expires_at"] = (
                    trial_expiry.astimezone(UTC).isoformat()
                )
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
        # EODHD's published minute pools conflict (20/min on the Free Starter
        # card versus 1,000/min on the general limits page), and the configured
        # account has exposed a native 1,200/min header. Keep the conservative
        # seed audit-visible but non-routable until an operator supplies the
        # exact account limit, reset semantics, and current evidence. There is
        # deliberately no arbitrary upper bound here: a positive, reviewed
        # provider-native entitlement is valid even when it exceeds a stale
        # published seed. The separately documented daily pool remains eligible
        # for native /user bootstrap.
        reviewed_limit = provider_positive_integer(
            getattr(settings, "EODHD_REVIEWED_MINUTE_LIMIT", 0)
        )
        reviewed_reset = str(
            getattr(settings, "EODHD_REVIEWED_MINUTE_RESET", "") or ""
        ).strip()
        quota_evidence = str(
            getattr(settings, "EODHD_MINUTE_QUOTA_EVIDENCE", "") or ""
        ).strip()
        contract = seed.get("quota_contract")
        if (
            reviewed_limit is not None
            and provider_quota_reset_is_admission_safe(reviewed_reset)
            and quota_evidence
            and isinstance(contract, dict)
        ):
            unresolved = {
                "published_minute_limit_conflict",
                "requests_per_minute_reset_boundary",
            }
            contract["unknown_dimensions"] = [
                item
                for item in (contract.get("unknown_dimensions") or [])
                if item not in unresolved
            ]
            for dimension in contract.get("dimensions") or []:
                if (
                    isinstance(dimension, dict)
                    and dimension.get("name") == "requests_per_minute"
                ):
                    dimension["limit"] = reviewed_limit
                    dimension["reset"] = reviewed_reset
                    dimension["limit_basis"] = "operator-reviewed account entitlement"
            contract["source"] = (
                f"{contract.get('source', 'EODHD API documentation')} plus "
                "operator-reviewed minute-limit and reset evidence"
            )
            seed["tokens_per_minute"] = reviewed_limit
            seed["quota_source"] = (
                "EODHD account allowance plus operator-reviewed minute quota evidence"
            )
        return seed
    if provider_name == "alpha_vantage":
        # Alpha Vantage documents the free-key daily allowance but does not
        # publish the reset boundary/timezone. Never reinterpret that as a
        # rolling 24-hour window. An operator may promote the seed only after
        # recording a reviewed, calculable reset label and evidence; the
        # setting is intentionally provider-specific so plan changes remain
        # configuration-only.
        reviewed_reset = str(
            getattr(settings, "ALPHA_VANTAGE_REVIEWED_RESET", "") or ""
        ).strip()
        quota_evidence = str(
            getattr(settings, "ALPHA_VANTAGE_QUOTA_EVIDENCE", "") or ""
        ).strip()
        contract = seed.get("quota_contract")
        if (
            provider_quota_reset_is_admission_safe(reviewed_reset)
            and quota_evidence
            and isinstance(contract, dict)
        ):
            contract["reset"] = reviewed_reset
            contract["unknown_dimensions"] = []
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
        # Massive publishes the free Stocks Basic five-calls/minute ceiling,
        # but its current plan documentation does not establish the minute
        # reset boundary. Promote only after the operator records an explicit
        # calculable reset label and current evidence for this account.
        reviewed_reset = str(
            getattr(settings, "MASSIVE_REVIEWED_RESET", "") or ""
        ).strip()
        quota_evidence = str(
            getattr(settings, "MASSIVE_QUOTA_EVIDENCE", "") or ""
        ).strip()
        contract = seed.get("quota_contract")
        if (
            provider_quota_reset_is_admission_safe(reviewed_reset)
            and quota_evidence
            and isinstance(contract, dict)
        ):
            contract["reset"] = reviewed_reset
            contract["unknown_dimensions"] = []
            for dimension in contract.get("dimensions") or []:
                if (
                    isinstance(dimension, dict)
                    and dimension.get("name") == "requests_per_minute"
                ):
                    dimension["reset"] = reviewed_reset
            contract["source"] = (
                f"{contract.get('source', 'Massive Stocks Basic documentation')} plus "
                "operator-reviewed reset-boundary evidence"
            )
            seed["quota_scope"] = "api_key"
            seed["quota_source"] = (
                "Massive Stocks Basic allowance plus operator-reviewed reset evidence"
            )
        return seed
    if provider_name == "edgar":
        # EDGAR publishes a 10-requests/second fair-access ceiling, but the
        # source does not establish the reset boundary. Promote only after an
        # operator records an explicit calculable label and current evidence.
        reviewed_reset = str(
            getattr(settings, "EDGAR_REVIEWED_RESET", "") or ""
        ).strip()
        quota_evidence = str(
            getattr(settings, "EDGAR_QUOTA_EVIDENCE", "") or ""
        ).strip()
        contract = seed.get("quota_contract")
        if (
            provider_quota_reset_is_admission_safe(reviewed_reset)
            and quota_evidence
            and isinstance(contract, dict)
        ):
            contract["reset"] = reviewed_reset
            contract["unknown_dimensions"] = []
            for dimension in contract.get("dimensions") or []:
                if (
                    isinstance(dimension, dict)
                    and dimension.get("name") == "requests_per_second"
                ):
                    dimension["reset"] = reviewed_reset
            contract["source"] = (
                f"{contract.get('source', 'SEC fair-access policy')} plus "
                "operator-reviewed reset-boundary evidence"
            )
            seed["quota_source"] = (
                "SEC fair-access ceiling plus operator-reviewed reset evidence"
            )
        return seed
    if provider_name == "alpaca":
        # The current Trading API Basic contract is source-backed by the
        # Market Data documentation/OpenAPI and the provider's native
        # X-RateLimit-* headers. Optional settings remain available for a
        # future plan change, but ordinary routing must not wait for a human
        # to restate a reset model that Alpaca already defines as per-minute.
        reviewed_reset = str(
            getattr(settings, "ALPACA_REVIEWED_RESET", "") or ""
        ).strip()
        quota_evidence = str(
            getattr(settings, "ALPACA_QUOTA_EVIDENCE", "") or ""
        ).strip()
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
        # ceilings. Promote the seed only when both dimensions have explicit,
        # calculable reset labels and independent evidence. The provider's
        # unresolved combined label remains visible in the default contract;
        # no rolling/fixed interpretation is invented here.
        minute_reset = str(
            getattr(settings, "FINNHUB_REVIEWED_MINUTE_RESET", "") or ""
        ).strip()
        second_reset = str(
            getattr(settings, "FINNHUB_REVIEWED_SECOND_RESET", "") or ""
        ).strip()
        minute_evidence = str(
            getattr(settings, "FINNHUB_MINUTE_QUOTA_EVIDENCE", "") or ""
        ).strip()
        second_evidence = str(
            getattr(settings, "FINNHUB_SECOND_QUOTA_EVIDENCE", "") or ""
        ).strip()
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
        # hourly boundary model (fixed/calendar versus rolling). Promote only
        # when those independent boundaries and the response-byte map have all
        # been explicitly reviewed; never infer a rolling window from the
        # phrase "every hour".
        unique_reset = str(
            getattr(settings, "TIINGO_REVIEWED_UNIQUE_SYMBOL_RESET", "") or ""
        ).strip()
        hourly_reset = str(
            getattr(settings, "TIINGO_REVIEWED_HOURLY_RESET", "") or ""
        ).strip()
        unique_evidence = str(
            getattr(settings, "TIINGO_UNIQUE_SYMBOL_QUOTA_EVIDENCE", "") or ""
        ).strip()
        hourly_evidence = str(
            getattr(settings, "TIINGO_HOURLY_QUOTA_EVIDENCE", "") or ""
        ).strip()
        if not (
            provider_quota_reset_is_admission_safe(unique_reset)
            and provider_quota_reset_is_admission_safe(hourly_reset)
            and unique_evidence
            and hourly_evidence
        ):
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
        contract["unknown_dimensions"] = []
        for dimension in dimensions:
            if not isinstance(dimension, dict):
                continue
            if dimension.get("name") == "unique_symbols_per_month":
                dimension["reset"] = unique_reset
            elif dimension.get("name") == "requests_per_hour":
                dimension["reset"] = hourly_reset
        contract["dimension_costs_required"] = True
        contract["operation_costs_required"] = True
        contract["source"] = (
            f"{contract.get('source', 'Tiingo pricing and API documentation')} plus "
            "operator-reviewed distinct-symbol/hourly reset evidence"
        )
        seed["quota_contract"] = contract
        seed["quota_source"] = (
            "Tiingo plan allowance plus operator-reviewed distinct-symbol/hourly reset evidence"
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
        quota_evidence = str(
            getattr(settings, "MARKETSTACK_QUOTA_EVIDENCE", "") or ""
        ).strip()
        contract = seed.get("quota_contract")
        if (
            reviewed_limit is not None
            and provider_quota_reset_is_admission_safe(reviewed_reset)
            and quota_evidence
            and isinstance(contract, dict)
        ):
            contract["reset"] = reviewed_reset
            contract["unknown_dimensions"] = []
            for dimension in contract.get("dimensions") or []:
                if (
                    isinstance(dimension, dict)
                    and dimension.get("name") == "requests_per_month"
                ):
                    dimension["limit"] = reviewed_limit
                    dimension["reset"] = reviewed_reset
            contract["source"] = (
                f"{contract.get('source', 'Marketstack pricing/FAQ')} plus "
                "operator-reviewed account limit/reset evidence"
            )
            seed["quota_contract"] = contract
            seed["quota_source"] = (
                "Marketstack account allowance plus operator-reviewed monthly reset evidence"
            )
        return seed
    if provider_name == "fmp":
        # FMP exposes independent daily-call and bandwidth pools. The current
        # official pricing contract defines bandwidth as a trailing 30-day
        # pool; the daily-call reset remains provider-defined. An operator may
        # override the bandwidth boundary for a future plan, but a blank value
        # retains the documented rolling-30-day semantics.
        daily_reset = str(
            getattr(settings, "FMP_REVIEWED_DAILY_RESET", "") or ""
        ).strip()
        reviewed_bandwidth_reset = str(
            getattr(settings, "FMP_REVIEWED_BANDWIDTH_RESET", "") or ""
        ).strip()
        bandwidth_reset = reviewed_bandwidth_reset or "rolling_30_days"
        daily_evidence = str(
            getattr(settings, "FMP_DAILY_QUOTA_EVIDENCE", "") or ""
        ).strip()
        bandwidth_evidence = str(
            getattr(settings, "FMP_BANDWIDTH_QUOTA_EVIDENCE", "") or ""
        ).strip()
        if not (
            provider_quota_reset_is_admission_safe(daily_reset)
            and provider_quota_reset_is_admission_safe(bandwidth_reset)
            and daily_evidence
            and bandwidth_evidence
        ):
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
        contract["unknown_dimensions"] = []
        for dimension in dimensions:
            if not isinstance(dimension, dict):
                continue
            if dimension.get("name") == "calls_per_day":
                dimension["reset"] = daily_reset
            elif dimension.get("name") == byte_constraint.get("name"):
                dimension["reset"] = bandwidth_reset
        contract["dimension_costs_required"] = True
        contract["operation_costs_required"] = True
        contract["source"] = (
            f"{contract.get('source', 'FMP account and pricing evidence')} plus "
            "operator-reviewed daily/bandwidth reset evidence"
        )
        seed["quota_contract"] = contract
        seed["quota_source"] = (
            "FMP account allowance plus operator-reviewed daily/bandwidth reset evidence"
        )
        seed["_byte_reservation_bounds"] = bounds
        return seed
    if provider_name == "fred":
        # A reviewed API limit alone is not enough: this application persists
        # observations and automated use must be covered by evidence. The
        # adapter separately checks the exact series-rights record before each
        # provider request.
        scope = str(getattr(settings, "FRED_REVIEWED_LIMIT_SCOPE", "") or "").strip()
        reviewed_limit = provider_positive_integer(
            getattr(settings, "FRED_REVIEWED_REQUESTS_PER_MINUTE", 0)
        )
        quota_evidence = str(
            getattr(settings, "FRED_REVIEWED_QUOTA_EVIDENCE", "") or ""
        ).strip()
        reviewed_reset = str(
            getattr(settings, "FRED_REVIEWED_RESET", "") or ""
        ).strip()
        reset_evidence = str(
            getattr(settings, "FRED_RESET_EVIDENCE", "") or ""
        ).strip()
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
