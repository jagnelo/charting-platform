import json
import os

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    APP_ENV: str = "development"

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
    DEFAULT_MARKET_DATA_PROVIDER: str = "yfinance"
    DEFAULT_METADATA_PROVIDER: str = "yfinance"
    DEFAULT_EVENT_PROVIDER: str = "yfinance"
    DEFAULT_DISCOVERY_PROVIDER: str = "yfinance"
    DEFAULT_OPTIONS_PROVIDER: str = "yfinance"
    IDENTIFIER_PROVIDER_PRIORITY: list[str] = ["yfinance", "openfigi"]
    OPENFIGI_API_KEY: str = ""
    OPENFIGI_TIMEOUT_SECONDS: float = 10.0
    MARKETDATA_API_KEY: str = ""
    FMP_API_KEY: str = ""
    INSTRUMENT_DISCOVERY_PAGE_DELAY_SECONDS: float = 0.75
    INSTRUMENT_METADATA_DELAY_SECONDS: float = 1.0
    INSTRUMENT_IDENTIFIER_DELAY_SECONDS: float = 1.0
    INSTRUMENT_DAILY_METADATA_CAP: int = 750
    INSTRUMENT_DAILY_IDENTIFIER_CAP: int = 250
    PROVIDER_MAX_CONCURRENCY: int = 2

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

    class Config:
        env_file = os.environ.get("ENV_FILE", ".env.dev")
        case_sensitive = True
        extra = "ignore"


settings = Settings()
