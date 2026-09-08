"""Read-only tokenized-security provider adapters.

Tokenized securities are not treated as alternate ticker aliases.  Every
adapter preserves the provider asset identifier, chain/network and contract
address, and records the linked economic underlying as metadata only.

The public surfaces implemented here are deliberately read-only.  Issuance,
redemption, trading and wallet-transfer APIs are outside this subsystem.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.config import settings
from app.providers.base import TokenizedAssetRecord
from app.providers.telemetry import observe_response


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _now() -> datetime:
    return datetime.now(UTC)


def _http_json(url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
    response = httpx.get(url, params=params, headers=headers, timeout=30)
    observe_response(response)
    response.raise_for_status()
    return response.json()


def _http_json_bounded_rate_retry(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    max_attempts: int = 3,
) -> Any:
    """Retry one public read after a provider 429, using bounded backoff.

    This is intentionally separate from the generic transport helper: the
    Robinhood public edge documents a per-second limit but can emit an
    occasional local throttle. Only this provider-specific read gets a small,
    finite retry budget, and every response remains observable telemetry.
    """

    attempts = max(1, min(int(max_attempts), 3))
    for attempt in range(attempts):
        try:
            return _http_json(url, params=params, headers=headers)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 429 or attempt == attempts - 1:
                raise
            retry_after = exc.response.headers.get("retry-after")
            try:
                delay = float(str(retry_after).strip()) if retry_after else 0.0
            except (TypeError, ValueError):
                delay = 0.0
            if delay <= 0:
                delay = min(1.0 * (2**attempt), 5.0)
            time.sleep(min(delay, 5.0))


def _network_chain_id(deployment: dict[str, Any]) -> tuple[str | None, int | None, str | None]:
    network = deployment.get("network") or deployment.get("networkName")
    chain_id = deployment.get("chainId") or deployment.get("chain_id")
    try:
        chain_id = int(chain_id) if chain_id is not None else None
    except (TypeError, ValueError):
        chain_id = None
    address = deployment.get("address") or deployment.get("contractAddress")
    return (str(network) if network else None, chain_id, str(address) if address else None)


class XStocksProvider:
    """Backed/xStocks public API (metadata, prices, multipliers and events)."""

    name = "xstocks"
    base_url = "https://api.xstocks.fi/api/v2"
    description = "xStocks tokenized equity/ETF metadata, prices and corporate actions"

    def _headers(self) -> dict[str, str]:
        key = str(getattr(settings, "XSTOCKS_API_KEY", "") or "").strip()
        return {"X-API-KEY": key} if key else {}

    def _record(self, payload: dict[str, Any], *, price: Decimal | None = None) -> TokenizedAssetRecord:
        underlying = payload.get("underlying") or {}
        deployments = payload.get("deployments") or []
        first = deployments[0] if deployments and isinstance(deployments[0], dict) else {}
        network, chain_id, address = _network_chain_id(first)
        return TokenizedAssetRecord(
            provider=self.name,
            asset_id=str(payload.get("id") or payload.get("symbol")),
            symbol=str(payload.get("symbol") or ""),
            name=str(payload.get("name") or payload.get("symbol") or ""),
            underlying_symbol=underlying.get("symbol") or payload.get("underlyingSymbol") or None,
            underlying_isin=underlying.get("isin") or payload.get("underlyingIsin") or None,
            isin=payload.get("isin") or None,
            network=network,
            chain_id=chain_id,
            contract_address=address,
            price=price,
            multiplier=_decimal(payload.get("currentMultiplier") or payload.get("multiplier")),
            status="halted" if payload.get("isTradingHalted") else "active",
            backing_type="fully_backed" if underlying else None,
            collateral={"underlying": underlying, "deployments": deployments},
            observed_at=_now(),
            raw_payload=payload,
        )

    def discover_tokenized_assets(
        self, *, page: int = 0, page_size: int = 100
    ) -> list[TokenizedAssetRecord]:
        payload = _http_json(
            f"{self.base_url}/public/assets",
            params={"page": max(0, page), "pageSize": max(1, min(page_size, 100))},
            headers=self._headers(),
        )
        nodes = payload.get("nodes", []) if isinstance(payload, dict) else []
        return [
            self._record(item)
            for item in nodes
            if isinstance(item, dict) and item.get("symbol")
        ]

    def get_tokenized_asset(self, identifier: str) -> TokenizedAssetRecord | None:
        payload = _http_json(
            f"{self.base_url}/public/assets/{identifier}", headers=self._headers()
        )
        return self._record(payload) if isinstance(payload, dict) and payload.get("symbol") else None

    def get_tokenized_price(self, identifier: str) -> TokenizedAssetRecord | None:
        payload = _http_json(
            f"{self.base_url}/public/assets/{identifier}/price-data", headers=self._headers()
        )
        quote = payload.get("quote") if isinstance(payload, dict) else None
        asset = self.get_tokenized_asset(identifier)
        if asset is None:
            return None
        asset.price = _decimal(quote)
        asset.observed_at = _now()
        asset.raw_payload = {"asset": asset.raw_payload, "price": payload}
        return asset

    def fetch_tokenized_corporate_actions(
        self, *, symbol: str | None = None, upcoming: bool = False, page: int = 1, page_size: int = 100
    ) -> list[dict[str, Any]]:
        endpoint = "upcoming" if upcoming else "history"
        payload = _http_json(
            f"{self.base_url}/public/corporate-actions/{endpoint}",
            params={
                "page": max(1, page),
                "pageSize": max(1, min(page_size, 100)),
                **({"symbol": symbol} if symbol else {}),
            },
            headers=self._headers(),
        )
        nodes = payload.get("nodes", []) if isinstance(payload, dict) else []
        return [row for row in nodes if isinstance(row, dict)]


class RobinhoodTokenProvider:
    """Robinhood Chain public Stock Token metadata, quotes and actions."""

    name = "robinhood_tokens"
    base_url = "https://api.robinhood.com/rhj"
    description = "Robinhood Stock Token read-only assets, prices and corporate actions"

    @staticmethod
    def _assets() -> list[dict[str, Any]]:
        payload = _http_json(f"{RobinhoodTokenProvider.base_url}/assets")
        return [row for row in (payload.get("assets", []) if isinstance(payload, dict) else []) if isinstance(row, dict)]

    @staticmethod
    def _record(payload: dict[str, Any], *, price: Decimal | None = None) -> TokenizedAssetRecord:
        deployments = payload.get("deployments") or []
        first = deployments[0] if deployments and isinstance(deployments[0], dict) else {}
        network, chain_id, address = _network_chain_id(first)
        symbol = str(payload.get("tokenSymbol") or payload.get("symbol") or "")
        return TokenizedAssetRecord(
            provider=RobinhoodTokenProvider.name,
            asset_id=str(payload.get("id") or symbol),
            symbol=symbol,
            name=str(payload.get("tokenName") or payload.get("name") or symbol),
            network=network,
            chain_id=chain_id,
            contract_address=address,
            price=price,
            multiplier=_decimal(payload.get("currentMultiplier")),
            status=str(payload.get("status") or "unknown").lower(),
            backing_type="economic_exposure_debt_security",
            collateral={"deployments": deployments, "trading_capabilities": payload.get("tradingCapabilities")},
            observed_at=_now(),
            raw_payload=payload,
        )

    def discover_tokenized_assets(
        self, *, page: int = 0, page_size: int = 100
    ) -> list[TokenizedAssetRecord]:
        rows = self._assets()
        start = max(0, page) * max(1, page_size)
        return [self._record(row) for row in rows[start : start + max(1, page_size)]]

    def get_tokenized_asset(self, identifier: str) -> TokenizedAssetRecord | None:
        needle = identifier.lower()
        for row in self._assets():
            if str(row.get("id", "")).lower() == needle or str(
                row.get("tokenSymbol", "")
            ).lower() == needle:
                return self._record(row)
        return None

    def get_tokenized_price(self, identifier: str) -> TokenizedAssetRecord | None:
        asset = self.get_tokenized_asset(identifier)
        symbol = asset.symbol if asset else identifier
        payload = _http_json_bounded_rate_retry(f"{self.base_url}/prices/{symbol}")
        quotes = payload.get("quotes", []) if isinstance(payload, dict) else []
        quote = next((row for row in quotes if isinstance(row, dict)), None)
        if quote is None:
            return asset
        record = asset or self._record(quote)
        record.price = _decimal(quote.get("bid"))
        record.bid = _decimal(quote.get("bid"))
        record.ask = _decimal(quote.get("ask"))
        record.observed_at = _now()
        record.raw_payload = {"asset": record.raw_payload, "price": quote}
        return record

    def fetch_tokenized_corporate_actions(self, *, symbol: str | None = None) -> list[dict[str, Any]]:
        payload = _http_json(f"{self.base_url}/corporate-actions")
        rows = payload.get("corpActions", []) if isinstance(payload, dict) else []
        if symbol:
            rows = [row for row in rows if str(row.get("tokenSymbol", "")).upper() == symbol.upper()]
        return [row for row in rows if isinstance(row, dict)]


class BybitXStocksProvider:
    """Bybit public xStocks instrument and ticker surface."""

    name = "bybit_xstocks"
    base_url = "https://api.bybit.com"
    description = "Bybit public xStocks instrument metadata and market tickers"

    @staticmethod
    def _instruments(cursor: str | None = None, limit: int = 500) -> dict[str, Any]:
        params: dict[str, Any] = {
            "category": "spot",
            "symbolType": "xstocks",
            "limit": max(1, min(limit, 1000)),
        }
        if cursor:
            params["cursor"] = cursor
        return _http_json(f"{BybitXStocksProvider.base_url}/v5/market/instruments-info", params=params)

    @staticmethod
    def _record(row: dict[str, Any], quote: dict[str, Any] | None = None) -> TokenizedAssetRecord:
        symbol = str(row.get("symbol") or row.get("baseCoin") or "")
        quote = quote or {}
        return TokenizedAssetRecord(
            provider=BybitXStocksProvider.name,
            asset_id=symbol,
            symbol=symbol,
            name=str(row.get("displayName") or row.get("baseCoin") or symbol),
            underlying_symbol=str(row.get("baseCoin") or symbol),
            currency=str(row.get("quoteCoin") or "USD"),
            price=_decimal(quote.get("lastPrice")),
            bid=_decimal(quote.get("bid1Price")),
            ask=_decimal(quote.get("ask1Price")),
            multiplier=_decimal(
                row.get("xstocksMultiplier")
                or row.get("multiplier")
                or row.get("currentMultiplier")
            ),
            status=str(row.get("status") or "unknown").lower(),
            backing_type="exchange_listed_tokenized_security",
            collateral={"category": "spot", "symbol_type": "xstocks"},
            observed_at=_now(),
            raw_payload={"instrument": row, "ticker": quote},
        )

    def discover_tokenized_assets(
        self, *, page: int = 0, page_size: int = 100
    ) -> list[TokenizedAssetRecord]:
        payload = self._instruments(limit=page_size)
        rows = (payload.get("result", {}).get("list", []) if isinstance(payload, dict) else [])
        if page > 0:
            # Bybit uses an opaque cursor; callers needing subsequent pages use
            # discover_tokenized_page and persist the cursor in the job state.
            return []
        return [self._record(row) for row in rows if isinstance(row, dict) and row.get("symbol")]

    def discover_tokenized_page(
        self, *, cursor: str | None = None, page_size: int = 500
    ) -> tuple[list[TokenizedAssetRecord], str | None]:
        payload = self._instruments(cursor=cursor, limit=page_size)
        result = payload.get("result", {}) if isinstance(payload, dict) else {}
        rows = result.get("list", [])
        return (
            [self._record(row) for row in rows if isinstance(row, dict) and row.get("symbol")],
            result.get("nextPageCursor") or None,
        )

    def get_tokenized_asset(self, identifier: str) -> TokenizedAssetRecord | None:
        payload = self._instruments(limit=1000)
        rows = payload.get("result", {}).get("list", []) if isinstance(payload, dict) else []
        row = next((row for row in rows if row.get("symbol") == identifier), None)
        return self._record(row) if isinstance(row, dict) else None

    def get_tokenized_price(self, identifier: str) -> TokenizedAssetRecord | None:
        asset = self.get_tokenized_asset(identifier)
        payload = _http_json(
            f"{self.base_url}/v5/market/tickers",
            params={"category": "spot", "symbol": identifier},
        )
        rows = payload.get("result", {}).get("list", []) if isinstance(payload, dict) else []
        quote = next((row for row in rows if isinstance(row, dict)), None)
        if asset is None and quote is None:
            return None
        record = asset or self._record({"symbol": identifier}, quote)
        if quote:
            record.price = _decimal(quote.get("lastPrice"))
            record.bid = _decimal(quote.get("bid1Price"))
            record.ask = _decimal(quote.get("ask1Price"))
            record.raw_payload = {"asset": record.raw_payload, "ticker": quote}
        record.observed_at = _now()
        return record


class GateTradfiProvider:
    """Gate public TradFi/xStocks symbol and order-book surface."""

    name = "gate_tradfi"
    base_url = "https://api.gateio.ws/api/v4"
    description = "Gate public TradFi stock-token symbols and market data"

    def discover_tokenized_assets(
        self, *, page: int = 0, page_size: int = 100
    ) -> list[TokenizedAssetRecord]:
        payload = _http_json(
            f"{self.base_url}/stock/symbols",
            params={"exchange": "us", "page": max(1, page + 1)},
        )
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        rows = data.get("list", []) if isinstance(data, dict) else []
        return [
            self._record(row)
            for row in rows[: max(1, page_size)]
            if isinstance(row, dict)
        ]

    @staticmethod
    def _record(row: dict[str, Any], quote: dict[str, Any] | None = None) -> TokenizedAssetRecord:
        symbol = str(row.get("symbol") or row.get("name") or "")
        quote = quote or {}
        return TokenizedAssetRecord(
            provider=GateTradfiProvider.name,
            asset_id=symbol,
            symbol=symbol,
            name=str(row.get("display_name") or row.get("name") or symbol),
            underlying_symbol=str(row.get("underlying_symbol") or row.get("base") or symbol),
            currency=str(row.get("quote_currency") or "USD"),
            price=_decimal(quote.get("last") or quote.get("price")),
            bid=_decimal(quote.get("bid")),
            ask=_decimal(quote.get("ask")),
            status=str(row.get("status") or "unknown").lower(),
            backing_type="exchange_listed_tokenized_security",
            collateral={"venue": "gate_tradfi"},
            observed_at=_now(),
            raw_payload={"instrument": row, "quote": quote},
        )

    def get_tokenized_asset(self, identifier: str) -> TokenizedAssetRecord | None:
        payload = _http_json(
            f"{self.base_url}/stock/symbols", params={"exchange": "us", "symbols": identifier}
        )
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        rows = data.get("list", []) if isinstance(data, dict) else []
        row = next((row for row in rows if isinstance(row, dict)), None)
        return self._record(row) if row else None

    def get_tokenized_price(self, identifier: str) -> TokenizedAssetRecord | None:
        asset = self.get_tokenized_asset(identifier)
        payload = _http_json(f"{self.base_url}/stock/market/{identifier}/orderbook")
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        bids = data.get("bids", []) if isinstance(data, dict) else []
        asks = data.get("asks", []) if isinstance(data, dict) else []
        bid = bids[0].get("p") if bids and isinstance(bids[0], dict) else None
        ask = asks[0].get("p") if asks and isinstance(asks[0], dict) else None
        row = {
            "bid": bid,
            "ask": ask,
            "price": (
                (float(bid) + float(ask)) / 2
                if bid is not None and ask is not None
                else bid or ask
            ),
        }
        record = asset or self._record({"symbol": identifier}, row)
        if isinstance(row, dict):
            record.bid = _decimal(row.get("bid") or row.get("best_bid"))
            record.ask = _decimal(row.get("ask") or row.get("best_ask"))
            record.price = _decimal(row.get("last") or row.get("price"))
            record.raw_payload = {"asset": record.raw_payload, "orderbook": row}
        record.observed_at = _now()
        return record


class KrakenXStocksProvider:
    """Kraken public xStocks pair discovery and ticker reads."""

    name = "kraken_xstocks"
    base_url = "https://api.kraken.com/0/public"
    description = "Kraken public xStocks pair metadata and ticker data"

    def discover_tokenized_assets(
        self, *, page: int = 0, page_size: int = 100
    ) -> list[TokenizedAssetRecord]:
        payload = _http_json(f"{self.base_url}/AssetPairs")
        rows = payload.get("result", {}) if isinstance(payload, dict) else {}
        candidates = [
            {"symbol": key, **value}
            for key, value in rows.items()
            if isinstance(value, dict)
            and "xstock" in f"{key} {value.get('wsname', '')} {value.get('altname', '')}".lower()
        ]
        start = max(0, page) * max(1, page_size)
        return [self._record(row) for row in candidates[start : start + max(1, page_size)]]

    @staticmethod
    def _record(row: dict[str, Any], quote: dict[str, Any] | None = None) -> TokenizedAssetRecord:
        symbol = str(row.get("symbol") or row.get("altname") or row.get("wsname") or "")
        quote = quote or {}
        return TokenizedAssetRecord(
            provider=KrakenXStocksProvider.name,
            asset_id=symbol,
            symbol=symbol,
            name=str(row.get("wsname") or symbol),
            underlying_symbol=str(row.get("base") or symbol),
            currency=str(row.get("quote") or "USD"),
            price=_decimal(quote.get("c", [None])[0] if isinstance(quote.get("c"), list) else quote.get("last")),
            bid=_decimal(quote.get("b", [None])[0] if isinstance(quote.get("b"), list) else quote.get("bid")),
            ask=_decimal(quote.get("a", [None])[0] if isinstance(quote.get("a"), list) else quote.get("ask")),
            status="active",
            backing_type="exchange_listed_tokenized_security",
            collateral={"venue": "kraken"},
            observed_at=_now(),
            raw_payload={"instrument": row, "ticker": quote},
        )

    def get_tokenized_asset(self, identifier: str) -> TokenizedAssetRecord | None:
        rows = self.discover_tokenized_assets(page=0, page_size=1000)
        return next((row for row in rows if row.symbol == identifier), None)

    def get_tokenized_price(self, identifier: str) -> TokenizedAssetRecord | None:
        asset = self.get_tokenized_asset(identifier)
        payload = _http_json(f"{self.base_url}/Ticker", params={"pair": identifier})
        result = payload.get("result", {}) if isinstance(payload, dict) else {}
        quote = next(iter(result.values()), {}) if isinstance(result, dict) else {}
        record = asset or self._record({"symbol": identifier}, quote)
        record.price = _decimal(quote.get("c", [None])[0] if isinstance(quote.get("c"), list) else quote.get("last"))
        record.bid = _decimal(quote.get("b", [None])[0] if isinstance(quote.get("b"), list) else quote.get("bid"))
        record.ask = _decimal(quote.get("a", [None])[0] if isinstance(quote.get("a"), list) else quote.get("ask"))
        record.raw_payload = {"asset": record.raw_payload, "ticker": quote}
        record.observed_at = _now()
        return record


TOKENIZED_PROVIDERS = (
    XStocksProvider,
    RobinhoodTokenProvider,
    BybitXStocksProvider,
    GateTradfiProvider,
    KrakenXStocksProvider,
)
