"""
CoinGecko public API provider.

Capabilities:
  - InstrumentSearchProvider  : coin search by name or symbol
  - InstrumentMetadataProvider: coin profile (name, platforms, links, etc.)
  - DiscoveryProvider         : market-cap-ordered crypto universe

Auth: COINGECKO_API_KEY (free Demo key — register at coingecko.com/en/api).
Rate limits: Demo plan is documented at 100 calls/minute and 10,000 calls/month;
the provider contract remains the authoritative checked-in routing declaration.

CoinGecko uses its own slug-based IDs (e.g. "bitcoin") rather than ticker
symbols.  A module-level coin list cache handles the symbol→id resolution
needed by search and metadata calls.

OHLCV note: CoinGecko's OHLC endpoint has coarse granularity and limited
history on the free tier.  Binance is the preferred OHLCV source for crypto;
CoinGecko's role here is universe discovery and rich metadata.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings
from app.providers.base import InstrumentProfile, ListingRecord, ProviderSearchResult
from app.providers.errors import (
    ProviderNotConfiguredError,
    ProviderResponseError,
    raise_for_provider_error_envelope,
)
from app.providers.telemetry import observe_response

logger = logging.getLogger(__name__)

_BASE = "https://api.coingecko.com/api/v3"
_PAGE_SIZE = 250

class CoinGeckoProvider:
    name = "coingecko"
    base_url = "https://api.coingecko.com"
    description = (
        "CoinGecko free API — crypto universe discovery, search, "
        "and instrument metadata (market cap, platforms, links)"
    )

    def __init__(self) -> None:
        # Keep the configuration warning scoped to this provider lifecycle. A module-global
        # flag lets an unrelated instance suppress diagnostics (and makes test/application
        # reconfiguration order observable).
        self._warned_no_key = False

    def _headers(self) -> dict[str, str]:
        if settings.COINGECKO_API_KEY:
            return {"x-cg-demo-api-key": settings.COINGECKO_API_KEY}
        raise ProviderNotConfiguredError("coingecko requires COINGECKO_API_KEY for the Demo plan")

    def _get(self, path: str, params: dict | None = None) -> Any:
        try:
            r = httpx.get(
                f"{_BASE}{path}",
                params=params or {},
                headers=self._headers(),
                timeout=20,
            )
        except httpx.RequestError as exc:
            raise ProviderResponseError(self.name, str(exc)) from exc
        observe_response(r)
        r.raise_for_status()
        try:
            payload = r.json()
        except (TypeError, ValueError) as exc:
            raise ProviderResponseError(self.name, "CoinGecko returned invalid JSON") from exc
        raise_for_provider_error_envelope(self.name, payload, r.status_code)
        return payload

    # ── Search ────────────────────────────────────────────────────────────────

    def search_instruments(self, query: str, *, limit: int = 10) -> list[ProviderSearchResult]:
        try:
            data = self._get("/search", {"query": query})
        except httpx.HTTPStatusError:
            raise
        results: list[ProviderSearchResult] = []
        for coin in (data.get("coins") or [])[:limit]:
            sym = coin.get("symbol", "").upper()
            results.append(
                ProviderSearchResult(
                    symbol=f"{sym}-USD",
                    name=coin.get("name", sym),
                    exchange="CoinGecko",
                    instrument_type="CRYPTOCURRENCY",
                )
            )
        return results

    # ── Metadata ──────────────────────────────────────────────────────────────

    def get_instrument_profile(self, symbol: str) -> InstrumentProfile | None:
        coin_id = _resolve_id(symbol, self._headers())
        if coin_id is None:
            return None
        try:
            data = self._get(
                f"/coins/{coin_id}",
                {
                    "localization": "false",
                    "tickers": "false",
                    "market_data": "true",
                    "community_data": "false",
                    "developer_data": "false",
                },
            )
        except httpx.HTTPStatusError:
            raise

        sym = (data.get("symbol") or "").upper()
        name = data.get("name") or sym
        market = data.get("market_data") or {}
        platforms = data.get("platforms") or {}

        return InstrumentProfile(
            provider="coingecko",
            symbol=f"{sym}-USD",
            canonical_symbol=f"{sym}-USD",
            name=name,
            description=_strip_html(data.get("description", {}).get("en")),
            currency="USD",
            quote_type="CRYPTOCURRENCY",
            exchange="",
            listings=[
                ListingRecord(
                    provider_symbol=f"{sym}-USD",
                    currency="USD",
                    provider_instrument_type="CRYPTOCURRENCY",
                    is_primary=True,
                )
            ],
            raw_payload={
                "id": coin_id,
                "symbol": sym,
                "market_cap_usd": market.get("market_cap", {}).get("usd"),
                "circulating_supply": data.get("market_data", {}).get("circulating_supply"),
                "total_supply": data.get("market_data", {}).get("total_supply"),
                "platforms": list(platforms.keys()),
                "homepage": (data.get("links") or {}).get("homepage", [None])[0],
                "coingecko_rank": data.get("market_cap_rank"),
            },
            extra={
                "coingecko_id": coin_id,
                "market_cap_rank": data.get("market_cap_rank"),
                "coingecko_score": data.get("coingecko_score"),
            },
        )

    # ── Universe Discovery ────────────────────────────────────────────────────

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        if quote_type != "CRYPTOCURRENCY":
            return {"total": 0, "quotes": []}

        page_num = offset // _PAGE_SIZE + 1
        try:
            data = self._get(
                "/coins/markets",
                {
                    "vs_currency": "usd",
                    "order": "market_cap_desc",
                    "per_page": _PAGE_SIZE,
                    "page": page_num,
                    "sparkline": "false",
                    "price_change_percentage": "",
                },
            )
        except httpx.HTTPStatusError:
            raise

        quotes = [_market_to_quote(c) for c in (data or []) if c.get("symbol")]
        return {
            "total": 10_000,  # CoinGecko does not surface exact count on this endpoint
            "quotes": quotes,
        }

    def supported_discovery_types(self) -> list[str]:
        return ["CRYPTOCURRENCY"]


# ── Module helpers ────────────────────────────────────────────────────────────


def _resolve_id(platform_symbol: str, headers: dict) -> str | None:
    """Resolve a platform symbol like BTC-USD to a CoinGecko coin ID.

    ``/coins/list`` is not ordered by market relevance, so choosing the first
    row for an ambiguous ticker can map BTC to an unrelated small token.  The
    provider's ranked search endpoint returns the canonical result first; an
    exact-symbol match is still required before accepting that result.
    """
    base = platform_symbol.split("-")[0].lower()
    try:
        r = httpx.get(
            f"{_BASE}/search",
            params={"query": base},
            headers=headers,
            timeout=20,
        )
    except httpx.RequestError as exc:
        raise ProviderResponseError("coingecko", str(exc)) from exc
    observe_response(r)
    r.raise_for_status()
    try:
        payload = r.json()
    except (TypeError, ValueError) as exc:
        raise ProviderResponseError("coingecko", "CoinGecko returned invalid JSON") from exc
    raise_for_provider_error_envelope("coingecko", payload, r.status_code)
    candidates = [
        item
        for item in (payload.get("coins") or [])
        if str(item.get("symbol") or "").lower() == base
    ]
    if not candidates:
        return None
    return candidates[0]["id"]


def _market_to_quote(coin: dict) -> dict[str, Any]:
    sym = (coin.get("symbol") or "").upper()
    return {
        "symbol": f"{sym}-USD",
        "shortName": coin.get("name", sym),
        "displayName": coin.get("name", sym),
        "quoteType": "CRYPTOCURRENCY",
        "exchange": "CoinGecko",
        "currency": "USD",
        "marketCap": coin.get("market_cap"),
    }


def _strip_html(text: str | None) -> str | None:
    if not text:
        return None
    import re

    return re.sub(r"<[^>]+>", "", text).strip() or None
