import json
import os
from copy import deepcopy

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    MARKET_DATA_SHADOW_REPORT_ENABLED: bool = False
    MARKET_UNIVERSE_RECONCILIATION_ENABLED: bool = False
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
    DEFAULT_OPTIONS_PROVIDER: str = "yfinance"
    # yfinance remains available for explicitly enabled legacy/options flows,
    # but must not be appended automatically to new workstation capability
    # chains. This keeps the default platform path free-source/API-first.
    ENABLE_LEGACY_YFINANCE_FALLBACK: bool = False
    # Paid adapters may be configured and audited without entering normal
    # routing.  An explicit deployment setting is required to opt them in.
    ALLOW_PAID_PROVIDER_ROUTING: bool = False
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
        # Alpaca exposes an assets/discovery endpoint but no instrument-search
        # operation. Keep it out of this chain; stale policies from older
        # configurations are filtered by provider capability at runtime too.
        "instrument_search": ["edgar", "massive", "alpha_vantage"],
        "instrument_metadata": ["edgar"],
        "price_history": ["alpaca", "alpha_vantage"],
        "latest_price": ["alpaca", "alpha_vantage"],
        # Alpha Vantage's EARNINGS endpoint is a final corroborating fallback;
        # its free key is deliberately last because the allowance is only
        # 25 requests/day and the earlier providers cover richer US event
        # semantics when their reviewed entitlements are available.
        "instrument_events": ["alpaca", "edgar", "finnhub", "alpha_vantage"],
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
    PROVIDER_RATE_LIMIT_SEEDS: dict[str, dict] = {
        "alpaca": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "historical_api_calls",
                        "limit": 200,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "account",
                        "quota_group": "account",
                        "source": "https://docs.alpaca.markets/us/v1.1/docs/about-market-data-api",
                    }
                ],
                "reset": "rolling_or_provider_defined",
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
                "reset": "rolling_or_provider_defined",
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
                # The provider publishes the daily allowance but not a reset
                # timezone. A rolling 24-hour reservation is conservative and
                # avoids assuming an undocumented calendar boundary.
                "reset": "rolling",
            },
            "quota_scope": "api_key",
            "quota_source": "Alpha Vantage support documentation",
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
                    }
                ],
                "reset": "rolling",
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
                "reset": "rolling",
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
                        "reset": "rolling",
                    }
                ],
                "unknown_dimensions": [
                    "v1_enforcement_scope",
                    "provider_adjustable_limits",
                    "series_terms_and_redistribution",
                ],
                "reset": "rolling",
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
                        # FINRA publishes "10 GB" without defining binary
                        # versus decimal units. Use the decimal-byte ceiling
                        # so the local guard cannot exceed either reading.
                        "limit": 10_000_000_000,
                        "window_seconds": 2678400,
                        "unit": "bytes",
                        "scope": "public_credential",
                        "quota_group": "public_credential",
                        "source": "https://developer.finra.org/support",
                        "reset": "calendar_month",
                        "limit_basis": "decimal_bytes_conservative_for_published_GB",
                    }
                ],
                "reset": "rolling_or_provider_defined",
                "dimension_costs_required": True,
                "maximum_synchronous_response_bytes": 3145728,
            },
            "tokens_per_minute": 1200,
            "quota_scope": "ip",
            "quota_source": "FINRA API Platform usage limits",
        },
        "finra_otc_directory": {
            "quota_contract": {
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
                    }
                ],
                "reset": "rolling",
                "maximum_synchronous_response_bytes": 3 * 1024**2,
                # A cold snapshot requires the partition lookup plus a
                # response-dependent number of DAPI pages. Do not charge one
                # request when the page count cannot be known before the
                # provider response; the adapter remains fail-closed until an
                # operator supplies a reviewed bound/profile.
                "operation_costs_required": True,
            },
            "tokens_per_minute": 1200,
            "quota_scope": "ip",
            "quota_source": "FINRA API Platform usage limits",
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
                        # CoinGecko publishes a monthly cap but does not
                        # define the reset boundary in the pricing contract.
                        # Keep admission conservative until the account's
                        # provider-native usage endpoint proves the boundary.
                        "reset": "provider_defined",
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
                    }
                ],
                "reset": "fixed_minute",
                "dynamic_endpoint_weights": True,
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
                        "name": "public_safe_frequency",
                        "limit": 1,
                        "window_seconds": 1,
                        "unit": "requests",
                        "scope": "ip_or_pair",
                        "source": "https://support.kraken.com/articles/206548367-what-are-the-api-rate-limits-",
                    }
                ],
                "reset": "rolling",
            },
            "quota_scope": "ip_or_pair",
            "quota_source": "Kraken REST rate-limit documentation",
        },
        "xstocks": {
            "quota_contract": {
                "dimensions": [],
                "unknown_dimensions": ["public provider quota/rate limit"],
                "source": "https://docs.xstocks.fi/apis/openapi",
            },
            "quota_scope": "public_endpoint",
            "quota_source": "xStocks API documentation (numeric public limit not published)",
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
                "provider_headers_required": True,
                "untracked_constraints": ["provider_response_headers", "endpoint_and_uid_limits"],
            },
            "quota_scope": "ip_and_endpoint",
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
                        "name": "public_safe_frequency",
                        "limit": 1,
                        "window_seconds": 1,
                        "unit": "requests",
                        "scope": "ip_or_pair",
                        "source": "https://support.kraken.com/articles/206548367-what-are-the-api-rate-limits-",
                    }
                ],
                "reset": "rolling",
            },
            "quota_scope": "ip_or_pair",
            "quota_source": "Kraken public API rate-limit documentation",
        },
        "dinari": {
            "quota_contract": {
                "dimensions": [],
                "unknown_dimensions": ["account/partner request limits and commercial data entitlements"],
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
                        "reset": "calendar_month_est",
                    },
                    {
                        "name": "requests_per_hour",
                        "limit": 50,
                        "window_seconds": 3600,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://www.tiingo.com/about/pricing",
                    },
                    {
                        "name": "requests_per_day",
                        "limit": 1000,
                        "window_seconds": 86400,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://www.tiingo.com/about/pricing",
                        "reset": "calendar_day_est",
                    },
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
                ],
                "reset": "per_dimension",
                "operation_costs_required": True,
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
                        "limit": 1000,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://eodhd.com/financial-apis/api-limits",
                        "reset": "rolling",
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
                    },
                ],
                "reset": "per_dimension",
                "operation_costs_required": True,
            },
            "tokens_per_minute": 1000,
            "quota_scope": "api_key",
            "quota_source": "EODHD API limits documentation",
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
                    }
                ],
                "reset": "provider_defined_daily",
                "untracked_constraints": [
                    {
                        "name": "bandwidth_bytes_per_30_days",
                        # The operator account reports "512 MB" without a
                        # binary-unit declaration. Keep the hard ceiling at
                        # the decimal-byte value rather than overestimating.
                        "limit": 512_000_000,
                        "unit": "bytes",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "operator_account_dashboard_2026-09-07",
                        "window_seconds": 2_592_000,
                        "reset": "rolling_30_days",
                        "limit_basis": "decimal_bytes_conservative_for_published_MB",
                    }
                ],
            },
            "quota_scope": "api_key",
            "quota_source": "FMP operator account dashboard",
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
                        "window_seconds": 2678400,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "https://marketstack.com/pricing",
                    }
                ],
                "reset": "calendar_month",
            },
            "quota_scope": "api_key",
            "quota_source": "Marketstack free-plan pricing",
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
                    {
                        "name": "historical_requests_concurrent",
                        "limit": 5,
                        "window_seconds": 1,
                        "unit": "concurrent_requests",
                        "scope": "authenticated_session",
                        "quota_group": "authenticated_session",
                        "source": "https://ibkrcampus.com/docs/web-api/v1/pacing-limitations",
                    },
                ],
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
            },
        },
        "massive": {
            "mode": "call_count",
            "unit_label": "requests",
            "operation_costs": {
                "search_instruments": 1,
                "discover_universe_page": 1,
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
                # These endpoint-specific dimensions apply only to history.
                # Empty maps are explicit zero-cost exclusions; the runtime
                # supplies the dynamic page cost for history operations.
                "historical_requests_per_minute": {
                    "search_instruments": {},
                    "get_instrument_profile": {},
                    "get_current_price": {},
                },
                "historical_requests_concurrent": {
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
                "fetch_ohlcv": 1,
                "fetch_latest_ohlcv": 1,
                "get_current_price": 1,
                "bulk_fetch": 1,
                # The provider documents one credit per expiration lookup.
                # ``fetch_option_chain`` and ``fetch_option_quote_history`` are
                # intentionally absent: current chains/quotes are billed per
                # returned contract/symbol (historical responses per 1,000),
                # so a fixed request cost would under-account the
                # response-dependent charge.
                "list_option_expirations": 1,
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
                    "fetch_short_interest": 3145728,
                    "fetch_market_events": 3145728,
                }
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
            "history_depth": "Plan-dependent historical bars",
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
            "configured_plan": "free-reference",
            "is_free": True,
            "authentication_required": True,
            "usage_terms": "Free reference/aggregate tier; confirm plan limits before production use.",
            "history_depth": "Plan-dependent",
            "venue_coverage": "Provider-supported US reference universe",
            "freshness_semantics": "Plan-dependent delayed/EOD",
        },
        "alpha_vantage": {
            "configured_plan": "free-key",
            "is_free": True,
            "authentication_required": True,
            "usage_terms": "Free API key with documented quota limits.",
            "history_depth": "Latest 100 daily points on the observed free entitlement; full daily output is premium",
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
            "authentication_required": False,
            "usage_terms": (
                "Public FINRA OTC Security Master DAPI; current FINRA API Terms of Service "
                "restrict licensed materials to authorized users/permitted uses and prohibit "
                "bulk-distributor/service-bureau use. Source terms, polling allowance, "
                "completeness/retention, and redistribution boundary require operator review: "
                "https://developer.finra.org/finra-api-terms-service"
            ),
            "history_depth": "Current as-of-date OTC security-master snapshot",
            "venue_coverage": "FINRA OTC securities represented by the configured DAPI source",
            "freshness_semantics": "Provider as-of-date partition and response time",
            "live_probe_status": "passed",
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
            "venue_coverage": "Provider-supported US securities",
            "freshness_semantics": "EOD/delayed on the free plan",
        },
        "eodhd": {
            "configured_plan": "free-20-day",
            "is_free": True,
            "authentication_required": True,
            "usage_terms": "EODHD free plan; daily and minute request ceilings and provider terms apply.",
            "history_depth": "Plan and endpoint dependent",
            "venue_coverage": "Provider-supported US securities",
            "freshness_semantics": "Historical/EOD",
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
            "usage_terms": "Public xStocks read endpoints; numeric public quota is not published. xStocks' official legal materials state they are not available in the United States or to U.S. persons; quota verification and jurisdiction/redistribution review are required before any routing.",
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
            "usage_terms": "Bybit public market-data endpoints; IP and endpoint limits apply.",
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
        # 2026-09-12; the event-only page bound remains a separate routing gate.
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
    MARKETDATA_API_KEY: str = ""
    FMP_API_KEY: str = ""
    TIINGO_API_KEY: str = ""
    # Provider-specific byte ceilings are deliberately empty by default.  A
    # deployment may set these as JSON maps (operation -> maximum response
    # bytes) only after reviewing the provider's current endpoint contract.
    # Without a complete map the corresponding bandwidth-constrained provider
    # remains fail-closed and non-routable.
    TIINGO_OPERATION_BYTE_BOUNDS: dict[str, int] = {}
    FMP_OPERATION_BYTE_BOUNDS: dict[str, int] = {}
    TWELVE_DATA_API_KEY: str = ""
    FINNHUB_API_KEY: str = ""
    MARKETSTACK_API_KEY: str = ""
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
    # MarketData.app current option-chain responses are billed per returned
    # contract.  A chain call may therefore be admitted only when operations
    # supplies a positive, conservative maximum contract count for the exact
    # filters used by the caller.  Zero keeps option-chain routing
    # fail-closed; ordinary stock candles and expiration lookups are not
    # affected.
    MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS: int = 0
    XSTOCKS_API_KEY: str = ""
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
    KRAKEN_API_KEY: str = ""
    # Alpaca Markets — US equity + crypto OHLCV, corporate actions, universe
    ALPACA_API_KEY: str = ""
    ALPACA_SECRET_KEY: str = ""
    ALPACA_DATA_FEED: str = "iex"  # "iex" (free) or "sip" (paid consolidated)
    # Paper accounts use the paper trading host for the authenticated assets
    # directory. Production credentials must opt into the live host explicitly;
    # market-data history/latest endpoints continue to use data.alpaca.markets.
    ALPACA_TRADING_BASE_URL: str = "https://paper-api.alpaca.markets/v2"
    # Corporate-actions responses are cursor-paginated and the request count
    # depends on the provider response. Keep event routing fail-closed until
    # operations records a positive conservative page bound for this account.
    ALPACA_CORPORATE_ACTIONS_MAX_PAGES: int = 0
    NASDAQ_USER_AGENT: str = "charting-platform market-data-universe"
    # FRED (Federal Reserve Economic Data) — rates, macro, forex series
    FRED_API_KEY: str = ""
    # FRED v1 publishes a 120-requests/minute threshold but leaves the
    # enforcement scope and adjustable account limit subject to provider
    # control. Keep the adapter fail-closed until operations records the
    # deployment's reviewed conservative scope/limit and confirms the series
    # copyright/redistribution terms for the configured use.
    FRED_REVIEWED_LIMIT_SCOPE: str = ""
    FRED_REVIEWED_REQUESTS_PER_MINUTE: int = 0
    FRED_SERIES_TERMS_REVIEWED: bool = False
    # CoinGecko — crypto universe discovery and metadata (free demo key)
    COINGECKO_API_KEY: str = ""
    # SEC EDGAR — no key required; User-Agent identifies your app to SEC servers
    EDGAR_USER_AGENT: str = ""
    FINRA_CLIENT_ID: str = ""
    FINRA_CLIENT_SECRET: str = ""
    FINRA_TOKEN_URL: str = "https://ews.fip.finra.org/fip/rest/ews/oauth2/access_token"
    FINRA_API_BASE_URL: str = "https://api.finra.org"
    FINRA_SHORT_INTEREST_URL: str = ""
    FINRA_OTC_DAILY_LIST_URL: str = ""
    # Official current OTC Security Master DAPI URL is documented in
    # docs/data-providers.md; keep this empty until operations explicitly
    # approves the source, terms, and polling contract.
    FINRA_OTC_SYMBOL_DIRECTORY_URL: str = ""
    # The DAPI directory's cold refresh is response/page-count dependent. A
    # deployment must provide a reviewed conservative request charge for each
    # runtime operation instead of inheriting a one-request default.
    FINRA_OTC_OPERATION_COSTS: dict[str, int] = {}
    # These are independent governance gates: source terms, complete-universe
    # interpretation, redistribution, and the chosen polling interval must be
    # reviewed for the exact configured source before routing is admitted.
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

    @field_validator(
        "OPTION_QUOTE_HISTORY_PROVIDER_PRIORITY",
        "PROVIDER_CHAIN_SEEDS",
        "PROVIDER_RATE_LIMIT_SEEDS",
        "PROVIDER_FRESHNESS_SEEDS",
        "PROVIDER_USAGE_PROFILE_SEEDS",
        "PROVIDER_LIVE_PROBE_STATUS_SEEDS",
        "TIINGO_OPERATION_BYTE_BOUNDS",
        "FMP_OPERATION_BYTE_BOUNDS",
        "FINRA_OTC_OPERATION_COSTS",
        "IBKR_CONID_MAP",
        mode="before",
    )
    @classmethod
    def parse_jsonish(cls, v):
        if isinstance(v, str):
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
}


def provider_required_operation_byte_bounds(provider_name: str) -> tuple[str, ...]:
    """Return the complete reviewed byte-bound operation set for a provider."""

    return _BYTE_BOUND_OPERATIONS.get(provider_name, ())


def provider_positive_integer(value: object) -> int | None:
    """Return a reviewed positive integer without coercing booleans or floats."""

    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def marketdata_app_reviewed_plan() -> tuple[str, int] | None:
    """Return a documented MarketData.app daily plan only when reviewed.

    The provider's response headers describe the current account entitlement,
    but a runtime observation must not silently rewrite durable policy.  An
    operator therefore records both the named plan and its documented daily
    credit limit.  Requiring the exact pair prevents a typo or an expired
    trial entitlement from widening admission by accident.
    """

    plan = str(getattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "") or "").strip().lower()
    expected_limit = _MARKETDATA_APP_DAILY_CREDIT_LIMITS.get(plan)
    configured_limit = provider_positive_integer(
        getattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 0)
    )
    if expected_limit is None or configured_limit != expected_limit:
        return None
    return plan, expected_limit


def provider_reviewed_flag(value: object) -> bool:
    """Accept only an actual boolean ``True`` for operator review gates."""

    return isinstance(value, bool) and value


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
    plan/limit pair before the documented Free Forever seed is widened.
    """

    seed = deepcopy(settings.PROVIDER_RATE_LIMIT_SEEDS.get(provider_name, {}))
    if provider_name == "marketdata_app":
        reviewed_plan = marketdata_app_reviewed_plan()
        if reviewed_plan is not None:
            plan, daily_limit = reviewed_plan
            contract = seed.get("quota_contract")
            if isinstance(contract, dict):
                contract["dimensions"] = [
                    {
                        **dimension,
                        "limit": daily_limit,
                        "account_plan": plan,
                        "account_limit_reviewed": True,
                    }
                    if isinstance(dimension, dict)
                    and dimension.get("name") == "credits_per_day"
                    else dimension
                    for dimension in contract.get("dimensions") or []
                ]
                seed["quota_contract"] = contract
        return seed
    if provider_name == "fred":
        # The public v1 error contract gives a numeric threshold, but not a
        # durable enforcement scope and permits the provider to adjust limits.
        # Only an operator-reviewed conservative scope/limit plus an explicit
        # series-rights review may remove those unknown dimensions. This is a
        # configuration-controlled admission gate, never a guessed fallback.
        scope = str(getattr(settings, "FRED_REVIEWED_LIMIT_SCOPE", "") or "").strip()
        reviewed_limit = provider_positive_integer(
            getattr(settings, "FRED_REVIEWED_REQUESTS_PER_MINUTE", 0)
        )
        terms_reviewed = provider_reviewed_flag(
            getattr(settings, "FRED_SERIES_TERMS_REVIEWED", False)
        )
        allowed_scopes = {"api_key", "account", "ip", "deployment"}
        if (
            scope in allowed_scopes
            and reviewed_limit is not None
            and reviewed_limit <= 120
            and terms_reviewed
            and isinstance(seed.get("quota_contract"), dict)
        ):
            contract = seed["quota_contract"]
            contract["unknown_dimensions"] = []
            for dimension in contract.get("dimensions") or []:
                if isinstance(dimension, dict) and dimension.get("name") == "requests_per_minute":
                    dimension["limit"] = reviewed_limit
                    dimension["scope"] = scope
                    dimension["quota_group"] = scope
            contract["source"] = (
                f"{contract.get('source', 'FRED v1 errors')} plus operator-reviewed "
                "deployment admission controls"
            )
            seed["quota_scope"] = scope
            seed["quota_source"] = "FRED v1 documented threshold plus operator-reviewed controls"
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
    contract["untracked_constraints"] = [item for item in untracked if item is not byte_constraint]
    dimensions = list(contract.get("dimensions") or [])
    if not any(item.get("name") == byte_constraint.get("name") for item in dimensions if isinstance(item, dict)):
        dimensions.append(dict(byte_constraint))
    contract["dimensions"] = dimensions
    contract["dimension_costs_required"] = True
    contract["operation_costs_required"] = True
    seed["quota_contract"] = contract
    seed["_byte_reservation_bounds"] = bounds
    return seed
