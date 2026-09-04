"""Alpha Vantage free-quota daily-history and symbol-search adapter."""

from __future__ import annotations

import csv
import io
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from app.config import settings
from app.models.ohlcv import OHLCVBar, Timeframe
from app.providers.base import MarketEventRecord, ProviderSearchResult

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

    def _get_text(self, function: str, **params: Any) -> str | None:
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
            return response.text
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
        return self.fetch_ohlcv(
            symbol,
            timeframe,
            start,
            datetime.now(UTC),
            adjusted=adjusted,
            instrument_id=instrument_id,
            data_source_id=data_source_id,
        )[-limit:]

    def latest_window_start(self, timeframe: Timeframe, limit: int) -> datetime:
        return datetime.now(UTC) - timedelta(days=max(limit * 2, 30))

    def get_current_price(self, symbol: str) -> float | None:
        bars = self.fetch_latest_ohlcv(symbol, Timeframe.D1, 1)
        return float(bars[-1].close) if bars else None

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        if quote_type.strip().upper() not in {"EQUITY", "EQUITIES", "STOCK", "STOCKS"}:
            return {"total": 0, "quotes": []}
        text = self._get_text("LISTING_STATUS", state="active")
        if not text:
            return {"total": 0, "quotes": []}
        try:
            rows = list(csv.DictReader(io.StringIO(text)))
        except csv.Error:
            return {"total": 0, "quotes": []}
        page_size = 1000
        page = rows[max(offset, 0) : max(offset, 0) + page_size]
        quotes = [
            {
                "symbol": str(row.get("symbol") or "").upper(),
                "name": str(row.get("name") or ""),
                "exchange": str(row.get("exchange") or ""),
                "instrument_type": str(row.get("assetType") or "EQUITY").upper(),
                "status": str(row.get("status") or "active").lower(),
                "ipo_date": row.get("ipoDate") or None,
                "delisting_date": row.get("delistingDate") or None,
            }
            for row in page
            if row.get("symbol")
        ]
        return {"total": len(rows), "quotes": quotes}

    def supported_discovery_types(self) -> list[str]:
        return ["EQUITY"]

    def fetch_market_events(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[MarketEventRecord]:
        """Fetch the provider's forward/historical IPO calendar as normalized events."""

        text = self._get_text("IPO_CALENDAR")
        if not text:
            return []
        try:
            rows = list(csv.DictReader(io.StringIO(text)))
        except csv.Error:
            return []
        result: list[MarketEventRecord] = []
        for row in rows:
            try:
                event_date = date.fromisoformat(str(row.get("ipoDate") or ""))
            except ValueError:
                continue
            if start and event_date < start or end and event_date > end:
                continue
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            result.append(
                MarketEventRecord(
                    event_type="ipo",
                    event_key=f"alpha_vantage:ipo:{symbol}:{event_date.isoformat()}",
                    event_time=datetime.combine(event_date, datetime.min.time(), tzinfo=UTC),
                    effective_date=event_date,
                    title=str(row.get("name") or symbol),
                    source_version="IPO_CALENDAR",
                    is_provisional=True,
                    raw_payload=row,
                )
            )
        return result
