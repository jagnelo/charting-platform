"""Massive (formerly Polygon) reference-data provider.

This adapter is deliberately limited to the free-source reference role: ticker
search and paged US ticker discovery.  It is supplementary evidence for the
canonical security master, not a default market-data path and not a promise of
consolidated real-time data.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from app.config import settings
from app.providers.base import ProviderSearchResult

logger = logging.getLogger(__name__)

_BASE = "https://api.massive.com"
_TICKERS_PATH = "/v3/reference/tickers"
_PAGE_SIZE = 1000


class MassiveProvider:
    name = "massive"
    base_url = _BASE
    description = "Massive reference tickers for US security-master corroboration"

    def __init__(self) -> None:
        self._cursor_by_page: dict[int, str] = {}

    def _api_key(self) -> str:
        # MARKETDATA_API_KEY is retained as a deployment-compatible alias.
        return settings.MASSIVE_API_KEY or settings.MARKETDATA_API_KEY

    def _params(self, **values: Any) -> dict[str, Any]:
        return {
            key: value
            for key, value in {"apiKey": self._api_key(), **values}.items()
            if value is not None
        }

    def _get(self, params: dict[str, Any]) -> dict[str, Any] | None:
        if not self._api_key():
            logger.warning("massive: MASSIVE_API_KEY is not set; skipping reference request")
            return None
        try:
            response = httpx.get(f"{_BASE}{_TICKERS_PATH}", params=params, timeout=20)
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else None
        except Exception as exc:
            logger.warning("massive reference request failed: %s", exc)
            return None

    def search_instruments(self, query: str, *, limit: int = 10) -> list[ProviderSearchResult]:
        needle = query.strip()
        if not needle or limit <= 0:
            return []
        payload = self._get(
            self._params(
                search=needle,
                market="stocks",
                locale="us",
                active="true",
                limit=min(limit, 100),
                sort="ticker",
                order="asc",
            )
        )
        return [self._result(row) for row in (payload or {}).get("results", [])[:limit]]

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        if quote_type.strip().upper() not in {"EQUITY", "EQUITIES", "STOCK", "STOCKS"}:
            return {"total": 0, "quotes": []}
        page = max(offset, 0) // _PAGE_SIZE
        cursor = self._cursor_by_page.get(page)
        payload = self._get(
            self._params(
                market="stocks",
                locale="us",
                active="true",
                limit=_PAGE_SIZE,
                sort="ticker",
                order="asc",
                cursor=cursor,
            )
        )
        rows = (payload or {}).get("results", [])
        quotes = [
            {
                "symbol": result.symbol,
                "name": result.name,
                "exchange": result.exchange,
                "instrument_type": result.instrument_type,
            }
            for result in (self._result(row) for row in rows)
        ]
        next_url = (payload or {}).get("next_url")
        if isinstance(next_url, str):
            next_cursor = parse_qs(urlparse(next_url).query).get("cursor", [None])[0]
            if next_cursor:
                self._cursor_by_page[page + 1] = next_cursor
        return {"total": len(quotes), "quotes": quotes, "next_url": next_url}

    def supported_discovery_types(self) -> list[str]:
        return ["EQUITY"]

    @staticmethod
    def _result(row: dict[str, Any]) -> ProviderSearchResult:
        return ProviderSearchResult(
            symbol=str(row.get("ticker") or "").upper(),
            name=str(row.get("name") or row.get("ticker") or ""),
            exchange=str(row.get("primary_exchange") or row.get("exchange") or ""),
            instrument_type=str(row.get("type") or "EQUITY").upper(),
        )
