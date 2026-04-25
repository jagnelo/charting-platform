"""
Federal Reserve Economic Data (FRED) provider.

Capabilities:
  - PriceHistoryProvider : daily OHLCV for mapped FRED series
  - LatestPriceProvider  : latest observation for mapped series

Mapped symbols (platform canonical → FRED series ID):
  Risk-free rates : ^IRX → DTB3, ^TNX → DGS10, ^TYX → DGS30, ^FVX → DGS5
  Forex (daily)   : EURUSD=X → DEXUSEU, GBPUSD=X → DEXUSUK, etc.
  Macro           : FEDFUNDS, CPIAUCSL, UNRATE, GDP, T10YIE, VIXCLS

Auth: FRED_API_KEY (free — register at fred.stlouisfed.org/docs/api/api_key.html).
Rate limits: generous; FRED does not publish hard limits for reasonable use.

FRED returns single scalar observations, not OHLCV.  open=high=low=close=value
so bars integrate cleanly with the existing OHLCVBar model.
Only D1 timeframe is supported (FRED is a daily/lower-frequency data source).
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx

from app.config import settings
from app.models.ohlcv import OHLCVBar, Timeframe

logger = logging.getLogger(__name__)

_BASE = "https://api.stlouisfed.org/fred"

def _assert_key() -> bool:
    """Return True if FRED_API_KEY is configured, False (with a warning) if not."""
    if settings.FRED_API_KEY:
        return True
    logger.warning(
        "fred: FRED_API_KEY is not set — skipping this call and falling back to next provider. "
        "Get a free key at fred.stlouisfed.org/docs/api/api_key.html and set it in .env.dev."
    )
    return False

# Canonical platform symbol → FRED series ID
_SERIES_MAP: dict[str, str] = {
    # Risk-free rates (annual %, discount basis)
    "^IRX": "DTB3",        # 3-Month Treasury Bill
    "^FVX": "DGS5",        # 5-Year Treasury CMT
    "^TNX": "DGS10",       # 10-Year Treasury CMT
    "^TYX": "DGS30",       # 30-Year Treasury CMT
    # Effective Federal Funds Rate
    "FEDFUNDS": "FEDFUNDS",
    # Forex daily exchange rates (USD per foreign unit unless noted)
    "EURUSD=X": "DEXUSEU",  # USD per Euro
    "GBPUSD=X": "DEXUSUK",  # USD per GBP
    "JPYUSD=X": "DEXJPUS",  # JPY per USD (inverted vs platform convention)
    "CADUSD=X": "DEXCAUS",  # CAD per USD (inverted)
    "MXNUSD=X": "DEXMXUS",  # MXN per USD (inverted)
    "CHFUSD=X": "DEXSZUS",  # CHF per USD (inverted)
    "AUDUSD=X": "DEXUSAL",  # USD per AUD
    "CNYUSD=X": "DEXCHUS",  # CNY per USD (inverted)
    # US macro indicators
    "CPIAUCSL": "CPIAUCSL",  # CPI All Urban Consumers SA (monthly)
    "UNRATE": "UNRATE",      # Unemployment Rate (monthly)
    "GDP": "GDP",            # Real GDP (quarterly)
    "T10YIE": "T10YIE",      # 10-Year Breakeven Inflation Rate
    "VIXCLS": "VIXCLS",      # CBOE Volatility Index (daily)
    # Commodity proxies (daily)
    "DCOILWTICO": "DCOILWTICO",  # WTI Crude Oil price
}


class FREDProvider:
    name = "fred"
    base_url = "https://api.stlouisfed.org"
    description = (
        "Federal Reserve Economic Data (FRED) — interest rates, macro indicators, "
        "and major forex daily series"
    )

    # ── Price History ─────────────────────────────────────────────────────────

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
    ) -> list[OHLCVBar]:
        series_id = _SERIES_MAP.get(symbol)
        if series_id is None:
            return []
        if not _assert_key():
            return []
        if timeframe not in (Timeframe.D1, Timeframe.W1, Timeframe.MN):
            return []

        try:
            r = httpx.get(
                f"{_BASE}/series/observations",
                params={
                    "series_id": series_id,
                    "api_key": settings.FRED_API_KEY,
                    "file_type": "json",
                    "observation_start": start.strftime("%Y-%m-%d"),
                    "observation_end": end.strftime("%Y-%m-%d"),
                    "sort_order": "asc",
                },
                timeout=30,
            )
            r.raise_for_status()
            observations = r.json().get("observations", [])
        except Exception as exc:
            logger.warning("fred fetch_ohlcv %s (%s): %s", symbol, series_id, exc)
            return []

        bars: list[OHLCVBar] = []
        for obs in observations:
            raw_val = obs.get("value", ".")
            if raw_val == "." or not raw_val:
                continue  # FRED uses "." for missing/unreleased data
            try:
                ts = datetime.strptime(obs["date"], "%Y-%m-%d").replace(tzinfo=UTC)
                val = float(raw_val)
                bars.append(OHLCVBar(
                    instrument_id=instrument_id,
                    data_source_id=data_source_id,
                    timeframe=timeframe,
                    ts=ts,
                    open=val,
                    high=val,
                    low=val,
                    close=val,
                    volume=None,
                    vwap=None,
                    is_adjusted=True,
                ))
            except (KeyError, ValueError):
                continue

        return bars

    def fetch_latest_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: int,
        *,
        adjusted: bool = True,
        instrument_id: int | None = None,
        data_source_id: int | None = None,
    ) -> list[OHLCVBar]:
        start = self.latest_window_start(timeframe, limit)
        bars = self.fetch_ohlcv(
            symbol, timeframe, start, datetime.now(UTC),
            adjusted=adjusted, instrument_id=instrument_id, data_source_id=data_source_id,
        )
        return bars[-limit:]

    def latest_window_start(self, timeframe: Timeframe, limit: int) -> datetime:
        # FRED is daily at finest; look back generously to handle weekends/holidays
        return datetime.now(UTC) - timedelta(days=limit * 2 + 30)

    # ── Latest Price ──────────────────────────────────────────────────────────

    def get_current_price(self, symbol: str) -> float | None:
        series_id = _SERIES_MAP.get(symbol)
        if series_id is None or not _assert_key():
            return None
        try:
            r = httpx.get(
                f"{_BASE}/series/observations",
                params={
                    "series_id": series_id,
                    "api_key": settings.FRED_API_KEY,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": 5,
                },
                timeout=10,
            )
            r.raise_for_status()
            for obs in r.json().get("observations", []):
                v = obs.get("value", ".")
                if v != "." and v:
                    return float(v)
        except Exception as exc:
            logger.debug("fred get_current_price %s: %s", symbol, exc)
        return None


# ── Public helpers ────────────────────────────────────────────────────────────

def is_fred_symbol(symbol: str) -> bool:
    """Return True if the symbol is covered by the FRED series map."""
    return symbol in _SERIES_MAP


def fred_series_for(symbol: str) -> str | None:
    """Return the FRED series ID for a platform canonical symbol, or None."""
    return _SERIES_MAP.get(symbol)
