"""Alpha Vantage free-quota daily-history and symbol-search adapter."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.config import settings
from app.models.ohlcv import OHLCVBar, Timeframe
from app.providers.base import ProviderSearchResult

logger = logging.getLogger(__name__)
_BASE = "https://www.alphavantage.co/query"


class AlphaVantageProvider:
    name = "alpha_vantage"
    base_url = "https://www.alphavantage.co"
    description = "Alpha Vantage free-quota daily history and symbol search"

    def _key(self) -> str:
        return settings.ALPHA_VANTAGE_API_KEY

    def _get(self, function: str, **params: Any) -> dict[str, Any] | None:
        if not self._key():
            logger.warning("alpha_vantage: ALPHA_VANTAGE_API_KEY is not configured")
            return None
        try:
            response = httpx.get(
                _BASE,
                params={"function": function, "apikey": self._key(), **params},
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else None
        except Exception as exc:
            logger.warning("alpha_vantage %s failed: %s", function, exc)
            return None

    def search_instruments(self, query: str, *, limit: int = 10) -> list[ProviderSearchResult]:
        if not query.strip() or limit <= 0:
            return []
        payload = self._get("SYMBOL_SEARCH", keywords=query.strip()) or {}
        return [
            ProviderSearchResult(
                symbol=str(row.get("1. symbol") or ""),
                name=str(row.get("2. name") or ""),
                exchange=str(row.get("4. region") or ""),
                instrument_type=str(row.get("3. type") or "EQUITY").upper(),
            )
            for row in payload.get("bestMatches", [])[:limit]
        ]

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
        if timeframe is not Timeframe.D1:
            return []
        payload = self._get("TIME_SERIES_DAILY", symbol=symbol, outputsize="full") or {}
        series = payload.get("Time Series (Daily)") or {}
        bars: list[OHLCVBar] = []
        for date_text, row in series.items():
            try:
                ts = datetime.strptime(date_text, "%Y-%m-%d").replace(tzinfo=UTC)
                if not (start <= ts < end):
                    continue
                bars.append(
                    OHLCVBar(
                        instrument_id=instrument_id,
                        data_source_id=data_source_id,
                        timeframe=timeframe,
                        ts=ts,
                        open=float(row["1. open"]),
                        high=float(row["2. high"]),
                        low=float(row["3. low"]),
                        close=float(row["4. close"]),
                        volume=float(row["5. volume"]),
                        is_adjusted=False,
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return sorted(bars, key=lambda bar: bar.ts)

    def fetch_latest_ohlcv(
        self, symbol: str, timeframe: Timeframe, limit: int, *, adjusted: bool = True,
        instrument_id: int | None = None, data_source_id: int | None = None,
    ) -> list[OHLCVBar]:
        start = self.latest_window_start(timeframe, limit)
        return self.fetch_ohlcv(symbol, timeframe, start, datetime.now(UTC), adjusted=adjusted, instrument_id=instrument_id, data_source_id=data_source_id)[-limit:]

    def latest_window_start(self, timeframe: Timeframe, limit: int) -> datetime:
        return datetime.now(UTC) - timedelta(days=max(limit * 2, 30))

    def get_current_price(self, symbol: str) -> float | None:
        bars = self.fetch_latest_ohlcv(symbol, Timeframe.D1, 1)
        return float(bars[-1].close) if bars else None
