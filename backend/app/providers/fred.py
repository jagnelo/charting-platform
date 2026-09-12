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
Rate limits: FRED v1 documents up to 120 requests per minute before HTTP 429,
but does not publish the enforcement scope and permits provider-adjustable
limits. FRED v2 documents a separate two-requests-per-second threshold, but
that does not automatically apply to this v1 adapter; the provider therefore
remains non-routable until the v1 scope and terms are verified and recorded.

FRED returns single scalar observations, not OHLCV.  open=high=low=close=value
so bars integrate cleanly with the existing OHLCVBar model.
Only D1 timeframe is supported (FRED is a daily/lower-frequency data source).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from math import isfinite

import httpx

from app.config import settings
from app.models.ohlcv import OHLCVBar, Timeframe
from app.providers.errors import (
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
    provider_response_headers,
    raise_for_provider_error_envelope,
)
from app.providers.telemetry import observe_response

logger = logging.getLogger(__name__)

_BASE = "https://api.stlouisfed.org/fred"


def _assert_key() -> None:
    """Require FRED credentials so missing configuration cannot look like no data."""
    if settings.FRED_API_KEY:
        return
    logger.warning(
        "fred: FRED_API_KEY is not set — refusing this call so the runtime can fall back. "
        "Get a free key at fred.stlouisfed.org/docs/api/api_key.html and set it in .env.dev."
    )
    raise ProviderNotConfiguredError("fred requires FRED_API_KEY")


def _raise_typed_rate_limit(exc: httpx.HTTPStatusError) -> None:
    """Preserve FRED capacity rejections for runtime quota accounting.

    FRED v1 documents a 120-requests/minute threshold, but its enforcement
    scope and provider-adjustable limits remain unresolved. A 429/418 response
    is still provider-native evidence that the current request must not be
    treated as an empty data set. Headers remain observational and are carried
    to the runtime without inventing a reset window.
    """

    response = exc.response
    if response.status_code not in {418, 429}:
        return
    headers = provider_response_headers(response)
    retry_at: datetime | None = None
    retry_after = headers.get("retry-after") or headers.get("Retry-After")
    if retry_after:
        try:
            retry_at = datetime.now(UTC) + timedelta(seconds=max(0, float(retry_after)))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(retry_after)
                retry_at = parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
            except (TypeError, ValueError, OverflowError):
                retry_at = None
    raise ProviderRateLimitError(
        "fred",
        f"FRED request rejected for capacity (HTTP {response.status_code})",
        retry_at=retry_at,
        status_code=response.status_code,
        headers=headers,
    ) from exc


# Canonical platform symbol → FRED series ID
_SERIES_MAP: dict[str, str] = {
    # Risk-free rates (annual %, discount basis)
    "^IRX": "DTB3",  # 3-Month Treasury Bill
    "^FVX": "DGS5",  # 5-Year Treasury CMT
    "^TNX": "DGS10",  # 10-Year Treasury CMT
    "^TYX": "DGS30",  # 30-Year Treasury CMT
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
    "UNRATE": "UNRATE",  # Unemployment Rate (monthly)
    "GDP": "GDP",  # Real GDP (quarterly)
    "T10YIE": "T10YIE",  # 10-Year Breakeven Inflation Rate
    "VIXCLS": "VIXCLS",  # CBOE Volatility Index (daily)
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
        _assert_key()
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
            observe_response(r)
            r.raise_for_status()
            payload = r.json()
            raise_for_provider_error_envelope(
                "fred", payload, r.status_code, headers=provider_response_headers(r)
            )
            observations = _observations(payload, "history")
        except httpx.HTTPStatusError as exc:
            _raise_typed_rate_limit(exc)
            raise ProviderResponseError("fred", f"FRED request failed with HTTP {exc.response.status_code}") from exc
        except (ProviderRateLimitError, ProviderResponseError):
            raise
        except httpx.RequestError as exc:
            raise ProviderResponseError("fred", str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise ProviderResponseError("fred", "FRED returned invalid JSON") from exc

        bars: list[OHLCVBar] = []
        for obs in observations:
            if "value" not in obs or "date" not in obs:
                raise ProviderResponseError("fred", "FRED returned a malformed observation row")
            raw_val = obs["value"]
            if raw_val == ".":
                continue  # FRED uses "." for missing/unreleased data
            try:
                ts = datetime.strptime(obs["date"], "%Y-%m-%d").replace(tzinfo=UTC)
                val = float(raw_val)
                if not isfinite(val):
                    raise ValueError("non-finite FRED observation")
                bars.append(
                    OHLCVBar(
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
                        adjustment_basis="provider_adjusted",
                        adjustment_version="fred-v1",
                        provenance={
                            "provider": self.name,
                            "endpoint": "/series/observations",
                            "series_id": series_id,
                            "provider_payload": obs,
                        },
                    )
                )
            except (TypeError, ValueError) as exc:
                raise ProviderResponseError("fred", "FRED returned an invalid observation row") from exc

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
            symbol,
            timeframe,
            start,
            datetime.now(UTC),
            adjusted=adjusted,
            instrument_id=instrument_id,
            data_source_id=data_source_id,
        )
        return bars[-limit:]

    def latest_window_start(self, timeframe: Timeframe, limit: int) -> datetime:
        # FRED is daily at finest; look back generously to handle weekends/holidays
        return datetime.now(UTC) - timedelta(days=limit * 2 + 30)

    # ── Latest Price ──────────────────────────────────────────────────────────

    def get_current_price(self, symbol: str) -> float | None:
        series_id = _SERIES_MAP.get(symbol)
        if series_id is None:
            return None
        _assert_key()
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
            observe_response(r)
            r.raise_for_status()
            payload = r.json()
            raise_for_provider_error_envelope(
                "fred", payload, r.status_code, headers=provider_response_headers(r)
            )
            for obs in _observations(payload, "latest price"):
                if "value" not in obs:
                    raise ProviderResponseError("fred", "FRED returned a malformed observation row")
                v = obs["value"]
                if v == ".":
                    continue
                try:
                    value = float(v)
                except (TypeError, ValueError) as exc:
                    raise ProviderResponseError("fred", "FRED returned an invalid latest observation") from exc
                if not isfinite(value):
                    raise ProviderResponseError("fred", "FRED returned a non-finite latest observation")
                return value
        except httpx.HTTPStatusError as exc:
            _raise_typed_rate_limit(exc)
            raise ProviderResponseError("fred", f"FRED request failed with HTTP {exc.response.status_code}") from exc
        except (ProviderRateLimitError, ProviderResponseError):
            raise
        except httpx.RequestError as exc:
            raise ProviderResponseError("fred", str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise ProviderResponseError("fred", "FRED returned invalid JSON") from exc
        return None


# ── Public helpers ────────────────────────────────────────────────────────────


def is_fred_symbol(symbol: str) -> bool:
    """Return True if the symbol is covered by the FRED series map."""
    return symbol in _SERIES_MAP


def fred_series_for(symbol: str) -> str | None:
    """Return the FRED series ID for a platform canonical symbol, or None."""
    return _SERIES_MAP.get(symbol)


def _observations(payload: object, operation: str) -> list[dict]:
    if not isinstance(payload, dict):
        raise ProviderResponseError("fred", f"FRED {operation} returned an invalid response object")
    observations = payload.get("observations")
    if not isinstance(observations, list):
        raise ProviderResponseError("fred", f"FRED {operation} returned an invalid observations array")
    if any(not isinstance(observation, dict) for observation in observations):
        raise ProviderResponseError("fred", f"FRED {operation} returned a malformed observation row")
    return observations
