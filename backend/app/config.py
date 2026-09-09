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
    TOKENIZED_ASSET_REFRESH_ENABLED: bool = False
    TOKENIZED_ASSET_REFRESH_MAX_ASSETS: int = 100
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
    ]
    PROVIDER_CHAIN_SEEDS: dict[str, list[str]] = {
        # Alpaca exposes an assets/discovery endpoint but no instrument-search
        # operation. Keep it out of this chain; stale policies from older
        # configurations are filtered by provider capability at runtime too.
        "instrument_search": ["edgar", "massive", "alpha_vantage"],
        "instrument_metadata": ["edgar"],
        "price_history": ["alpaca", "alpha_vantage"],
        "latest_price": ["alpaca", "alpha_vantage"],
        "instrument_events": ["alpaca", "edgar"],
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
        ],
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
                # FRED v1 documents that rate limiting exists and returns
                # HTTP 429, but does not publish a numeric ceiling or its
                # enforcement scope. FRED v2's separate 2-requests/second
                # rule must not be applied to this v1 adapter.
                "dimensions": [],
                "unknown_dimensions": [
                    "v1_numeric_rate_limit_and_scope",
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
                        "source": "https://developer.finra.org/docs",
                        "reset": "rolling",
                    },
                    {
                        "name": "asynchronous_requests_per_minute_dataset",
                        "limit": 20,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "api_account_and_dataset",
                        "source": "https://developer.finra.org/node/1146",
                        "reset": "rolling",
                    },
                    {
                        "name": "download_bytes_per_calendar_month",
                        "limit": 10737418240,
                        "window_seconds": 2678400,
                        "unit": "bytes",
                        "scope": "public_credential",
                        "source": "https://developer.finra.org/support",
                        "reset": "calendar_month",
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
                        "source": "https://developer.finra.org/node/1146",
                        "reset": "rolling",
                    }
                ],
                "reset": "rolling",
                "maximum_synchronous_response_bytes": 3 * 1024**2,
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
                        "source": "https://www.coingecko.com/en/api/pricing",
                        "reset": "rolling",
                    },
                    {
                        "name": "calls_per_month",
                        "limit": 10000,
                        "window_seconds": 2678400,
                        "unit": "requests",
                        "scope": "demo_api_key",
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
                        "source": "https://docs.cdp.coinbase.com/exchange/rest-api/rate-limits",
                    }
                ],
                "reset": "rolling",
            },
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
        "tiingo": {
            "quota_contract": {
                "dimensions": [
                    {
                        "name": "unique_symbols_per_month",
                        "limit": 500,
                        "window_seconds": 2678400,
                        "unit": "symbols",
                        "scope": "api_key",
                        "source": "https://www.tiingo.com/about/pricing",
                        "reset": "calendar_month_est",
                    },
                    {
                        "name": "requests_per_hour",
                        "limit": 50,
                        "window_seconds": 3600,
                        "unit": "requests",
                        "scope": "api_key",
                        "source": "https://www.tiingo.com/about/pricing",
                    },
                    {
                        "name": "requests_per_day",
                        "limit": 1000,
                        "window_seconds": 86400,
                        "unit": "requests",
                        "scope": "api_key",
                        "source": "https://www.tiingo.com/about/pricing",
                        "reset": "calendar_day_est",
                    },
                ],
                "reset": "provider_defined",
                "untracked_constraints": [
                    {
                        "name": "bandwidth_bytes_per_month",
                        "limit": 1073741824,
                        "window_seconds": 2678400,
                        "unit": "bytes",
                        "scope": "api_key",
                        "source": "https://www.tiingo.com/about/pricing",
                        "reset": "calendar_month_est",
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
                        "source": "https://twelvedata.com/pricing",
                        "reset": "fixed_minute",
                    },
                    {
                        "name": "credits_per_day",
                        "limit": 800,
                        "window_seconds": 86400,
                        "unit": "credits",
                        "scope": "api_key",
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
                        "source": "operator_account_dashboard_2026-09-07",
                    },
                    {
                        "name": "hard_calls_per_second",
                        "limit": 30,
                        "window_seconds": 1,
                        "unit": "requests",
                        "scope": "api_key",
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
                        "source": "https://eodhd.com/financial-apis/api-limits",
                        "reset": "rolling",
                    },
                    {
                        "name": "calls_per_day",
                        "limit": 20,
                        "window_seconds": 86400,
                        "unit": "calls",
                        "scope": "api_key",
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
                        "source": "operator_account_dashboard_2026-09-07",
                    }
                ],
                "reset": "provider_defined_daily",
                "untracked_constraints": [
                    {
                        "name": "bandwidth_bytes_per_30_days",
                        "limit": 536870912,
                        "unit": "bytes",
                        "scope": "api_key",
                        "source": "operator_account_dashboard_2026-09-07",
                        "window_seconds": 2_592_000,
                        "reset": "rolling_30_days",
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
                        "source": "https://www.marketdata.app/docs/api/rate-limiting/",
                    },
                    {
                        "name": "concurrent_requests",
                        "limit": 50,
                        "window_seconds": 1,
                        "unit": "concurrent_requests",
                        "scope": "api_key",
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
                        "source": "https://ibkrcampus.com/docs/web-api/v1/pacing-limitations",
                    },
                    {
                        "name": "historical_requests_concurrent",
                        "limit": 5,
                        "window_seconds": 1,
                        "unit": "concurrent_requests",
                        "scope": "authenticated_session",
                        "source": "https://ibkrcampus.com/docs/web-api/v1/pacing-limitations",
                    },
                ],
                "reset": "rolling",
                "endpoint_specific_limits": True,
            },
            "quota_scope": "authenticated_session",
            "quota_source": "IBKR Web API pacing limitations",
        },
    }
    PROVIDER_FRESHNESS_SEEDS: dict[str, int] = {}
    PROVIDER_USAGE_PROFILE_SEEDS: dict[str, dict] = {
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
        "marketdata_app": {
            "mode": "credit_count",
            "unit_label": "credits",
            "operation_costs": {
                "fetch_ohlcv": 1,
                "fetch_latest_ohlcv": 1,
                "get_current_price": 1,
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
            },
        },
        "eodhd": {
            "mode": "credit_count",
            "unit_label": "calls",
            "operation_costs": {
                "fetch_ohlcv": 1,
                "fetch_latest_ohlcv": 1,
                "get_current_price": 1,
                "get_instrument_profile": 10,
                "discover_universe_page": 1,
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
                "get_tokenized_price": 2,
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
            "configured_plan": "free-forever",
            "is_free": True,
            "authentication_required": True,
            "usage_terms": "MarketData.app Free Forever credits and licensing terms apply.",
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
            "usage_terms": "Public xStocks read endpoints; numeric public quota is not published and routing remains disabled until verified.",
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
            "usage_terms": "API access requires Ondo onboarding; terms and pricing must be reviewed before implementation.",
            "history_depth": "Provider-dependent",
            "venue_coverage": "Ondo Global Markets tokenized US stocks and ETFs",
            "freshness_semantics": "Provider-dependent",
        },
        "dinari": {
            "configured_plan": "partner-access-required",
            "is_free": False,
            "authentication_required": True,
            "usage_terms": "Partner/API access and commercial terms required.",
            "history_depth": "Provider-dependent",
            "venue_coverage": "Dinari tokenized-equity products",
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
        "alpaca": "not_run",
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
        "marketdata_app": "not_run",
        "xstocks": "passed",
        "robinhood_tokens": "passed",
        "bybit_xstocks": "passed",
        "gate_tradfi": "passed",
        "kraken_xstocks": "passed",
        "ondo_global_markets": "not_run",
        "dinari": "not_run",
        "alpaca_itn": "not_run",
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
    EODHD_API_KEY: str = ""
    TRADIER_API_KEY: str = ""
    MARKETDATA_APP_API_KEY: str = ""
    XSTOCKS_API_KEY: str = ""
    IBKR_READ_ONLY_URL: str = ""
    COINBASE_API_KEY: str = ""
    KRAKEN_API_KEY: str = ""
    # Alpaca Markets — US equity + crypto OHLCV, corporate actions, universe
    ALPACA_API_KEY: str = ""
    ALPACA_SECRET_KEY: str = ""
    ALPACA_DATA_FEED: str = "iex"  # "iex" (free) or "sip" (paid consolidated)
    NASDAQ_USER_AGENT: str = "charting-platform market-data-universe"
    # FRED (Federal Reserve Economic Data) — rates, macro, forex series
    FRED_API_KEY: str = ""
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
        "search_instruments",
        "get_instrument_profile",
    ),
    "fmp": (
        "fetch_ohlcv",
        "fetch_latest_ohlcv",
        "get_instrument_profile",
        "discover_universe_page",
    ),
}


def provider_operation_byte_bounds(provider_name: str) -> dict[str, int]:
    """Return only positive, explicitly configured operation byte bounds."""

    setting_name = f"{provider_name.upper()}_OPERATION_BYTE_BOUNDS"
    raw = getattr(settings, setting_name, {})
    if not isinstance(raw, dict):
        return {}
    result: dict[str, int] = {}
    for operation, value in raw.items():
        try:
            bound = int(value)
        except (TypeError, ValueError):
            continue
        if str(operation).strip() and bound > 0:
            result[str(operation).strip()] = bound
    return result


def provider_rate_limit_seed(provider_name: str) -> dict:
    """Return a provider quota seed with reviewed byte budgets applied.

    Tiingo and FMP publish bandwidth pools but not a universal response-size
    ceiling.  The base seed therefore remains explicitly untracked.  An
    operator can promote the provider only by supplying a positive bound for
    every operation exposed by its adapter; the helper then moves that
    documented pool into the normal multidimensional reservation contract.
    """

    seed = deepcopy(settings.PROVIDER_RATE_LIMIT_SEEDS.get(provider_name, {}))
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
