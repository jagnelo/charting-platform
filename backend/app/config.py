import json
import os

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    E2E_SEED_INSTRUMENTS: bool = False
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

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:4173"]

    # Alert engine
    ALERT_POLL_INTERVAL: int = 60

    # Proxy
    PROXY_FILE: str = "proxies.txt"
    PROXY_ENABLED: bool = False

    # Provider-backed universe maintenance
    INSTRUMENT_SYNC_SCHEDULE_ENABLED: bool = False
    ETF_HOLDINGS_REFRESH_ENABLED: bool = False
    ETF_HOLDINGS_SEC_BACKFILL_ENABLED: bool = False
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
    IDENTIFIER_PROVIDER_PRIORITY: list[str] = ["openfigi"]
    OPTION_QUOTE_HISTORY_PROVIDER_PRIORITY: list[str] = []
    PROVIDER_CHAIN_SEEDS: dict[str, list[str]] = {
        # Alpaca exposes an assets/discovery endpoint but no instrument-search
        # operation. Keep it out of this chain; stale policies from older
        # configurations are filtered by provider capability at runtime too.
        "instrument_search": ["edgar", "massive", "alpha_vantage"],
        "instrument_metadata": ["edgar"],
        "price_history": ["alpaca", "alpha_vantage"],
        "latest_price": ["alpaca", "alpha_vantage"],
        "instrument_events": ["alpaca", "edgar"],
        "universe_discovery": ["alpaca", "massive", "alpha_vantage"],
    }
    PROVIDER_RATE_LIMIT_SEEDS: dict[str, dict[str, int]] = {}
    PROVIDER_FRESHNESS_SEEDS: dict[str, int] = {}
    PROVIDER_USAGE_PROFILE_SEEDS: dict[str, dict] = {}
    OPENFIGI_API_KEY: str = ""
    OPENFIGI_TIMEOUT_SECONDS: float = 10.0
    MASSIVE_API_KEY: str = ""
    ALPHA_VANTAGE_API_KEY: str = ""
    MARKETDATA_API_KEY: str = ""
    FMP_API_KEY: str = ""
    # Alpaca Markets — US equity + crypto OHLCV, corporate actions, universe
    ALPACA_API_KEY: str = ""
    ALPACA_SECRET_KEY: str = ""
    ALPACA_DATA_FEED: str = "iex"  # "iex" (free) or "sip" (paid consolidated)
    # FRED (Federal Reserve Economic Data) — rates, macro, forex series
    FRED_API_KEY: str = ""
    # CoinGecko — crypto universe discovery and metadata (free demo key)
    COINGECKO_API_KEY: str = ""
    # SEC EDGAR — no key required; User-Agent identifies your app to SEC servers
    EDGAR_USER_AGENT: str = "charting-platform contact@example.com"
    INSTRUMENT_DISCOVERY_PAGE_DELAY_SECONDS: float = 0.75
    INSTRUMENT_METADATA_DELAY_SECONDS: float = 1.0
    INSTRUMENT_IDENTIFIER_DELAY_SECONDS: float = 1.0
    INSTRUMENT_DAILY_METADATA_CAP: int = 750
    INSTRUMENT_DAILY_IDENTIFIER_CAP: int = 250
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

    @field_validator(
        "OPTION_QUOTE_HISTORY_PROVIDER_PRIORITY",
        "PROVIDER_CHAIN_SEEDS",
        "PROVIDER_RATE_LIMIT_SEEDS",
        "PROVIDER_FRESHNESS_SEEDS",
        "PROVIDER_USAGE_PROFILE_SEEDS",
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
