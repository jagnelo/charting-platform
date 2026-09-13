"""Read-only tokenized-security provider adapters.

Tokenized securities are not treated as alternate ticker aliases.  Every
adapter preserves the provider asset identifier, chain/network and contract
address, and records the linked economic underlying as metadata only.

The public surfaces implemented here are deliberately read-only.  Issuance,
redemption, trading and wallet-transfer APIs are outside this subsystem.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from math import isfinite
from typing import Any
from uuid import UUID

import httpx

from app.config import settings
from app.providers.base import TokenizedAssetRecord
from app.providers.errors import (
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
    raise_for_provider_error_envelope,
)
from app.providers.telemetry import observe_response


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _required_text(payload: dict[str, Any], provider_name: str, field: str, *keys: str) -> str:
    """Return a non-empty provider identity field or fail closed."""

    for key in keys:
        value = payload.get(key)
        if value is None or isinstance(value, bool):
            continue
        text = str(value).strip()
        if text:
            return text
    raise ProviderResponseError(provider_name, f"provider returned an asset without {field}")


def _checked_decimal(value: Any, provider_name: str, field: str) -> Decimal | None:
    """Reject malformed/non-finite values while preserving omitted optionals."""

    if value in (None, ""):
        return None
    parsed = _decimal(value)
    if parsed is None:
        raise ProviderResponseError(provider_name, f"provider returned an invalid {field}")
    return parsed


def _deployments(payload: dict[str, Any], provider_name: str) -> list[dict[str, Any]]:
    raw = payload.get("deployments", [])
    if raw is None:
        return []
    if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
        raise ProviderResponseError(
            provider_name, "provider returned an invalid deployment row container"
        )
    return raw


def _now() -> datetime:
    return datetime.now(UTC)


_CAPACITY_HEADER_NAMES = {
    "retry-after",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "x-bapi-limit",
    "x-bapi-limit-status",
    "x-bapi-limit-reset-timestamp",
}


def _capacity_headers(response: httpx.Response) -> dict[str, str]:
    """Keep allow-listed capacity headers, tolerating lightweight test doubles."""

    try:
        items = response.headers.items()
        return {
            str(key).lower(): str(value)
            for key, value in items
            if str(key).lower() in _CAPACITY_HEADER_NAMES
        }
    except (AttributeError, TypeError):
        return {}


def _http_json(
    url: str,
    *,
    provider_name: str | None = None,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    retry_server_errors: int = 0,
    retry_delay_seconds: float = 0.25,
) -> Any:
    attempts = max(0, min(int(retry_server_errors), 2))
    for attempt in range(attempts + 1):
        try:
            response = httpx.get(url, params=params, headers=headers, timeout=30)
        except httpx.RequestError as exc:
            raise ProviderResponseError(provider_name or url.split("/", 3)[2], str(exc)) from exc
        observe_response(response)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Dinari's Sandbox has intermittently returned a bare 500 for
            # otherwise valid read-only catalogue/market-data requests. The
            # adapter opts into only two bounded retries for that provider;
            # 4xx/rate-limit responses and all other adapters remain typed and
            # fail immediately. Every attempt is still recorded by telemetry.
            if response.status_code == 500 and attempt < attempts:
                time.sleep(max(0.0, min(float(retry_delay_seconds) * (attempt + 1), 2.0)))
                continue
            provider = provider_name or url.split("/", 3)[2]
            safe_headers = _capacity_headers(response)
            message = f"HTTP {response.status_code}: {exc}"
            if response.status_code in {418, 429}:
                raise ProviderRateLimitError(
                    provider,
                    message,
                    retry_at=_retry_at(safe_headers),
                    status_code=response.status_code,
                    headers=safe_headers,
                ) from exc
            raise ProviderResponseError(provider, message, status_code=response.status_code) from exc
        break
    try:
        payload = response.json()
    except (TypeError, ValueError) as exc:
        raise ProviderResponseError(
            provider_name or url.split("/", 3)[2], "provider returned invalid JSON"
        ) from exc
    raise_for_provider_error_envelope(
        provider_name or url.split("/", 3)[2],
        payload,
        response.status_code,
        headers=_capacity_headers(response),
    )
    return payload


def _http_json_bounded_rate_retry(
    url: str,
    *,
    provider_name: str | None = None,
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
            return _http_json(url, provider_name=provider_name, params=params, headers=headers)
        except ProviderRateLimitError as exc:
            if exc.status_code != 429 or attempt == attempts - 1:
                raise
            retry_after = exc.headers.get("retry-after")
            try:
                delay = float(str(retry_after).strip()) if retry_after else 0.0
            except (TypeError, ValueError):
                delay = 0.0
            if delay <= 0:
                delay = min(1.0 * (2**attempt), 5.0)
            time.sleep(min(delay, 5.0))


def _dinari_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    """Read Dinari with its bounded Sandbox 500 recovery policy."""

    return _http_json(
        url,
        provider_name="dinari",
        params=params,
        headers=headers,
        retry_server_errors=2,
        retry_delay_seconds=0.25,
    )


def _retry_at(headers: dict[str, str]) -> datetime | None:
    value = str(headers.get("retry-after") or "").strip()
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    if not isfinite(seconds) or seconds < 0:
        return None
    return datetime.now(UTC) + timedelta(seconds=seconds)


def _required_object(payload: Any, provider_name: str, context: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ProviderResponseError(provider_name, f"provider returned an invalid {context} object")
    return payload


def _required_rows(
    payload: Any, provider_name: str, field: str, *, context: str | None = None
) -> list[dict[str, Any]]:
    body = _required_object(payload, provider_name, context or field)
    if field not in body:
        raise ProviderResponseError(provider_name, f"provider omitted the {field} rows")
    rows = body[field]
    if not isinstance(rows, list):
        raise ProviderResponseError(
            provider_name, f"provider returned an invalid {field} row container"
        )
    if any(not isinstance(row, dict) for row in rows):
        raise ProviderResponseError(provider_name, f"provider returned a non-object {field} row")
    return rows


def _required_nested_rows(
    payload: Any, provider_name: str, path: tuple[str, ...]
) -> list[dict[str, Any]]:
    current: Any = _required_object(payload, provider_name, ".".join(path))
    for key in path:
        if not isinstance(current, dict) or key not in current:
            raise ProviderResponseError(
                provider_name, f"provider omitted the {'.'.join(path)} rows"
            )
        current = current[key]
    if not isinstance(current, list):
        raise ProviderResponseError(
            provider_name, f"provider returned an invalid {'.'.join(path)} row container"
        )
    if any(not isinstance(row, dict) for row in current):
        raise ProviderResponseError(
            provider_name, f"provider returned a non-object {'.'.join(path)} row"
        )
    return current


def _gate_orderbook_rows(payload: dict[str, Any], field: str) -> list[dict[str, Any]]:
    """Normalize Gate's documented ``null`` empty book and object rows."""

    if field not in payload:
        raise ProviderResponseError("gate_tradfi", f"provider omitted the {field} rows")
    rows = payload[field]
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise ProviderResponseError(
            "gate_tradfi", f"provider returned an invalid {field} row container"
        )
    if any(not isinstance(row, dict) for row in rows):
        raise ProviderResponseError("gate_tradfi", f"provider returned a non-object {field} row")
    return rows


def _gate_orderbook_price(rows: list[dict[str, Any]], field: str) -> Decimal | None:
    if not rows:
        return None
    value = _decimal(rows[0].get("p"))
    if value is None or not value.is_finite():
        raise ProviderResponseError("gate_tradfi", f"provider returned an invalid {field} price")
    return value


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

    def _record(
        self, payload: dict[str, Any], *, price: Decimal | None = None
    ) -> TokenizedAssetRecord:
        underlying = payload.get("underlying") or {}
        if not isinstance(underlying, dict):
            raise ProviderResponseError(self.name, "provider returned an invalid underlying object")
        deployments = _deployments(payload, self.name)
        symbol = _required_text(payload, self.name, "symbol", "symbol")
        asset_id = _required_text(payload, self.name, "asset identifier", "id", "symbol")
        name = _required_text(payload, self.name, "name", "name", "symbol")
        first = deployments[0] if deployments else {}
        network, chain_id, address = _network_chain_id(first)
        return TokenizedAssetRecord(
            provider=self.name,
            asset_id=asset_id,
            symbol=symbol,
            name=name,
            underlying_symbol=underlying.get("symbol") or payload.get("underlyingSymbol") or None,
            underlying_figi=underlying.get("figi") or payload.get("underlyingFigi") or None,
            underlying_composite_figi=(
                underlying.get("compositeFigi")
                or underlying.get("composite_figi")
                or payload.get("underlyingCompositeFigi")
                or None
            ),
            underlying_isin=underlying.get("isin") or payload.get("underlyingIsin") or None,
            underlying_cusip=underlying.get("cusip") or payload.get("underlyingCusip") or None,
            isin=payload.get("isin") or None,
            network=network,
            chain_id=chain_id,
            contract_address=address,
            price=_checked_decimal(price, self.name, "price") if price is not None else None,
            multiplier=_checked_decimal(
                payload.get("currentMultiplier")
                if payload.get("currentMultiplier") is not None
                else payload.get("multiplier"),
                self.name,
                "current multiplier",
            ),
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
            provider_name=self.name,
            params={"page": max(0, page), "pageSize": max(1, min(page_size, 100))},
            headers=self._headers(),
        )
        nodes = _required_rows(payload, self.name, "nodes")
        return [self._record(item) for item in nodes]

    def get_tokenized_asset(self, identifier: str) -> TokenizedAssetRecord | None:
        payload = _http_json(
            f"{self.base_url}/public/assets/{identifier}",
            provider_name=self.name,
            headers=self._headers(),
        )
        body = _required_object(payload, self.name, "asset")
        if not body.get("symbol"):
            raise ProviderResponseError(self.name, "provider returned an asset without a symbol")
        return self._record(body)

    def get_tokenized_price(self, identifier: str) -> TokenizedAssetRecord | None:
        payload = _http_json(
            f"{self.base_url}/public/assets/{identifier}/price-data",
            provider_name=self.name,
            headers=self._headers(),
        )
        body = _required_object(payload, self.name, "price")
        if "quote" not in body:
            raise ProviderResponseError(self.name, "provider omitted the price quote")
        quote = body["quote"]
        asset = self.get_tokenized_asset(identifier)
        if asset is None:
            return None
        asset.price = _checked_decimal(quote, self.name, "price quote")
        asset.observed_at = _now()
        asset.raw_payload = {"asset": asset.raw_payload, "price": payload}
        return asset

    def fetch_tokenized_corporate_actions(
        self,
        *,
        symbol: str | None = None,
        upcoming: bool = False,
        page: int = 1,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        endpoint = "upcoming" if upcoming else "history"
        payload = _http_json(
            f"{self.base_url}/public/corporate-actions/{endpoint}",
            provider_name=self.name,
            params={
                "page": max(1, page),
                "pageSize": max(1, min(page_size, 100)),
                **({"symbol": symbol} if symbol else {}),
            },
            headers=self._headers(),
        )
        return _required_rows(payload, self.name, "nodes")


class RobinhoodTokenProvider:
    """Robinhood Chain public Stock Token metadata, quotes and actions."""

    name = "robinhood_tokens"
    base_url = "https://api.robinhood.com/rhj"
    description = "Robinhood Stock Token read-only assets, prices and corporate actions"

    @staticmethod
    def _assets() -> list[dict[str, Any]]:
        payload = _http_json(
            f"{RobinhoodTokenProvider.base_url}/assets",
            provider_name=RobinhoodTokenProvider.name,
        )
        return _required_rows(payload, RobinhoodTokenProvider.name, "assets")

    @staticmethod
    def _record(payload: dict[str, Any], *, price: Decimal | None = None) -> TokenizedAssetRecord:
        deployments = _deployments(payload, RobinhoodTokenProvider.name)
        symbol = _required_text(
            payload, RobinhoodTokenProvider.name, "symbol", "tokenSymbol", "symbol"
        )
        asset_id = _required_text(
            payload, RobinhoodTokenProvider.name, "asset identifier", "id", "tokenSymbol", "symbol"
        )
        name = _required_text(
            payload,
            RobinhoodTokenProvider.name,
            "name",
            "tokenName",
            "name",
            "tokenSymbol",
            "symbol",
        )
        first = deployments[0] if deployments else {}
        network, chain_id, address = _network_chain_id(first)
        return TokenizedAssetRecord(
            provider=RobinhoodTokenProvider.name,
            asset_id=asset_id,
            symbol=symbol,
            name=name,
            network=network,
            chain_id=chain_id,
            contract_address=address,
            price=(
                _checked_decimal(price, RobinhoodTokenProvider.name, "price")
                if price is not None
                else None
            ),
            multiplier=_checked_decimal(
                payload.get("currentMultiplier"), RobinhoodTokenProvider.name, "current multiplier"
            ),
            status=str(payload.get("status") or "unknown").lower(),
            backing_type="economic_exposure_debt_security",
            collateral={
                "deployments": deployments,
                "trading_capabilities": payload.get("tradingCapabilities"),
            },
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
            if (
                str(row.get("id", "")).lower() == needle
                or str(row.get("tokenSymbol", "")).lower() == needle
            ):
                return self._record(row)
        return None

    def get_tokenized_price(self, identifier: str) -> TokenizedAssetRecord | None:
        asset = self.get_tokenized_asset(identifier)
        symbol = asset.symbol if asset else identifier
        payload = _http_json_bounded_rate_retry(
            f"{self.base_url}/prices/{symbol}", provider_name=self.name
        )
        quotes = _required_rows(payload, self.name, "quotes")
        quote = quotes[0] if quotes else None
        if quote is None:
            return asset
        record = asset or self._record(quote)
        record.price = _checked_decimal(quote.get("bid"), self.name, "bid price")
        record.bid = _checked_decimal(quote.get("bid"), self.name, "bid price")
        record.ask = _checked_decimal(quote.get("ask"), self.name, "ask price")
        record.observed_at = _now()
        record.raw_payload = {"asset": record.raw_payload, "price": quote}
        return record

    def fetch_tokenized_corporate_actions(
        self, *, symbol: str | None = None
    ) -> list[dict[str, Any]]:
        payload = _http_json(f"{self.base_url}/corporate-actions", provider_name=self.name)
        rows = _required_rows(payload, self.name, "corpActions")
        if symbol:
            rows = [
                row for row in rows if str(row.get("tokenSymbol", "")).upper() == symbol.upper()
            ]
        return rows


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
        return _http_json(
            f"{BybitXStocksProvider.base_url}/v5/market/instruments-info",
            provider_name=BybitXStocksProvider.name,
            params=params,
        )

    @staticmethod
    def _record(row: dict[str, Any], quote: dict[str, Any] | None = None) -> TokenizedAssetRecord:
        symbol = _required_text(row, BybitXStocksProvider.name, "symbol", "symbol", "baseCoin")
        if quote is None:
            quote = {}
        if not isinstance(quote, dict):
            raise ProviderResponseError(
                BybitXStocksProvider.name, "provider returned an invalid ticker object"
            )
        return TokenizedAssetRecord(
            provider=BybitXStocksProvider.name,
            asset_id=symbol,
            symbol=symbol,
            name=str(row.get("displayName") or row.get("baseCoin") or symbol),
            underlying_symbol=str(row.get("baseCoin") or symbol),
            currency=str(row.get("quoteCoin") or "USD"),
            price=_checked_decimal(quote.get("lastPrice"), BybitXStocksProvider.name, "last price"),
            bid=_checked_decimal(quote.get("bid1Price"), BybitXStocksProvider.name, "bid price"),
            ask=_checked_decimal(quote.get("ask1Price"), BybitXStocksProvider.name, "ask price"),
            multiplier=_checked_decimal(
                row.get("xstocksMultiplier")
                or row.get("multiplier")
                or row.get("currentMultiplier"),
                BybitXStocksProvider.name,
                "multiplier",
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
        rows = _required_nested_rows(payload, self.name, ("result", "list"))
        if page > 0:
            # Bybit uses an opaque cursor; returning an empty page here would
            # look like a completed catalogue and silently truncate discovery.
            # Callers needing subsequent pages must use discover_tokenized_page
            # and persist the provider cursor in job state.
            raise ProviderResponseError(
                self.name,
                "Bybit tokenized discovery uses opaque cursor pagination; "
                "use discover_tokenized_page for subsequent pages",
            )
        return [self._record(row) for row in rows]

    def discover_tokenized_page(
        self, *, cursor: str | None = None, page_size: int = 500
    ) -> tuple[list[TokenizedAssetRecord], str | None]:
        payload = self._instruments(cursor=cursor, limit=page_size)
        body = _required_object(payload, self.name, "instrument result")
        result = _required_object(body.get("result"), self.name, "instrument result")
        rows = _required_rows(result, self.name, "list", context="instrument result list")
        next_cursor = result.get("nextPageCursor")
        if next_cursor is not None and not isinstance(next_cursor, str):
            raise ProviderResponseError(self.name, "provider returned an invalid instrument cursor")
        return (
            [self._record(row) for row in rows],
            next_cursor or None,
        )

    def get_tokenized_asset(self, identifier: str) -> TokenizedAssetRecord | None:
        payload = self._instruments(limit=1000)
        rows = _required_nested_rows(payload, self.name, ("result", "list"))
        row = next((row for row in rows if row.get("symbol") == identifier), None)
        return self._record(row) if row is not None else None

    def get_tokenized_price(self, identifier: str) -> TokenizedAssetRecord | None:
        asset = self.get_tokenized_asset(identifier)
        payload = _http_json(
            f"{self.base_url}/v5/market/tickers",
            provider_name=self.name,
            params={"category": "spot", "symbol": identifier},
        )
        rows = _required_nested_rows(payload, self.name, ("result", "list"))
        quote = rows[0] if rows else None
        if asset is None and quote is None:
            return None
        record = asset or self._record({"symbol": identifier}, quote)
        if quote:
            record.price = _checked_decimal(quote.get("lastPrice"), self.name, "last price")
            record.bid = _checked_decimal(quote.get("bid1Price"), self.name, "bid price")
            record.ask = _checked_decimal(quote.get("ask1Price"), self.name, "ask price")
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
            provider_name=self.name,
            params={"exchange": "us", "page": max(1, page + 1)},
        )
        body = _required_object(payload, self.name, "symbol catalogue")
        data = _required_object(body.get("data"), self.name, "symbol catalogue data")
        rows = _required_rows(data, self.name, "list", context="symbol catalogue list")
        return [self._record(row) for row in rows[: max(1, page_size)]]

    @staticmethod
    def _record(row: dict[str, Any], quote: dict[str, Any] | None = None) -> TokenizedAssetRecord:
        symbol = _required_text(row, GateTradfiProvider.name, "symbol", "symbol", "name")
        if quote is None:
            quote = {}
        if not isinstance(quote, dict):
            raise ProviderResponseError(
                GateTradfiProvider.name, "provider returned an invalid quote object"
            )
        return TokenizedAssetRecord(
            provider=GateTradfiProvider.name,
            asset_id=symbol,
            symbol=symbol,
            name=str(row.get("display_name") or row.get("name") or symbol),
            underlying_symbol=str(row.get("underlying_symbol") or row.get("base") or symbol),
            currency=str(row.get("quote_currency") or "USD"),
            price=_checked_decimal(
                quote.get("last") if quote.get("last") is not None else quote.get("price"),
                GateTradfiProvider.name,
                "last price",
            ),
            bid=_checked_decimal(quote.get("bid"), GateTradfiProvider.name, "bid price"),
            ask=_checked_decimal(quote.get("ask"), GateTradfiProvider.name, "ask price"),
            status=str(row.get("status") or "unknown").lower(),
            backing_type="exchange_listed_tokenized_security",
            collateral={"venue": "gate_tradfi"},
            observed_at=_now(),
            raw_payload={"instrument": row, "quote": quote},
        )

    def get_tokenized_asset(self, identifier: str) -> TokenizedAssetRecord | None:
        payload = _http_json(
            f"{self.base_url}/stock/symbols",
            provider_name=self.name,
            params={"exchange": "us", "symbols": identifier},
        )
        body = _required_object(payload, self.name, "symbol lookup")
        data = _required_object(body.get("data"), self.name, "symbol lookup data")
        rows = _required_rows(data, self.name, "list", context="symbol lookup list")
        row = rows[0] if rows else None
        return self._record(row) if row else None

    def get_tokenized_price(self, identifier: str) -> TokenizedAssetRecord | None:
        asset = self.get_tokenized_asset(identifier)
        payload = _http_json(
            f"{self.base_url}/stock/market/{identifier}/orderbook",
            provider_name=self.name,
        )
        body = _required_object(payload, self.name, "order book")
        data = _required_object(body.get("data"), self.name, "order book data")
        bids = _gate_orderbook_rows(data, "bids")
        asks = _gate_orderbook_rows(data, "asks")
        bid = _gate_orderbook_price(bids, "bid")
        ask = _gate_orderbook_price(asks, "ask")
        row = {
            "bid": bid,
            "ask": ask,
            "price": ((bid + ask) / 2 if bid is not None and ask is not None else bid or ask),
        }
        record = asset or self._record({"symbol": identifier}, row)
        if isinstance(row, dict):
            record.bid = _checked_decimal(
                row.get("bid") if row.get("bid") is not None else row.get("best_bid"),
                self.name,
                "bid price",
            )
            record.ask = _checked_decimal(
                row.get("ask") if row.get("ask") is not None else row.get("best_ask"),
                self.name,
                "ask price",
            )
            record.price = _checked_decimal(
                row.get("last") if row.get("last") is not None else row.get("price"),
                self.name,
                "last price",
            )
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
        payload = _http_json(f"{self.base_url}/AssetPairs", provider_name=self.name)
        body = _required_object(payload, self.name, "asset-pairs response")
        rows = _required_object(body.get("result"), self.name, "asset-pairs result")
        if any(not isinstance(value, dict) for value in rows.values()):
            raise ProviderResponseError(self.name, "provider returned a non-object asset-pair row")
        candidates = [
            {"symbol": key, **value}
            for key, value in rows.items()
            if "xstock" in f"{key} {value.get('wsname', '')} {value.get('altname', '')}".lower()
        ]
        start = max(0, page) * max(1, page_size)
        return [self._record(row) for row in candidates[start : start + max(1, page_size)]]

    @staticmethod
    def _record(row: dict[str, Any], quote: dict[str, Any] | None = None) -> TokenizedAssetRecord:
        symbol = _required_text(
            row, KrakenXStocksProvider.name, "symbol", "symbol", "altname", "wsname"
        )
        if quote is None:
            quote = {}
        if not isinstance(quote, dict):
            raise ProviderResponseError(
                KrakenXStocksProvider.name, "provider returned an invalid ticker object"
            )

        def quote_value(*keys: str) -> Any:
            for key in keys:
                if key not in quote:
                    continue
                value = quote[key]
                if isinstance(value, list):
                    if not value:
                        return None
                    return value[0]
                if key in {"c", "b", "a"}:
                    raise ProviderResponseError(
                        KrakenXStocksProvider.name,
                        f"provider returned an invalid {key} quote field",
                    )
                return value
            return None

        return TokenizedAssetRecord(
            provider=KrakenXStocksProvider.name,
            asset_id=symbol,
            symbol=symbol,
            name=str(row.get("wsname") or symbol),
            underlying_symbol=str(row.get("base") or symbol),
            currency=str(row.get("quote") or "USD"),
            price=_checked_decimal(
                quote_value("c", "last"), KrakenXStocksProvider.name, "last price"
            ),
            bid=_checked_decimal(quote_value("b", "bid"), KrakenXStocksProvider.name, "bid price"),
            ask=_checked_decimal(quote_value("a", "ask"), KrakenXStocksProvider.name, "ask price"),
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
        payload = _http_json(
            f"{self.base_url}/Ticker",
            provider_name=self.name,
            params={"pair": identifier},
        )
        body = _required_object(payload, self.name, "ticker response")
        result = _required_object(body.get("result"), self.name, "ticker result")
        if not result:
            raise ProviderResponseError(self.name, "provider returned no ticker rows")
        if any(not isinstance(value, dict) for value in result.values()):
            raise ProviderResponseError(self.name, "provider returned a non-object ticker row")
        quote = next(iter(result.values()))
        record = asset or self._record({"symbol": identifier}, quote)

        def quote_value(*keys: str) -> Any:
            for key in keys:
                if key not in quote:
                    continue
                value = quote[key]
                if isinstance(value, list):
                    if not value:
                        return None
                    return value[0]
                if key in {"c", "b", "a"}:
                    raise ProviderResponseError(
                        self.name, f"provider returned an invalid {key} quote field"
                    )
                return value
            return None

        record.price = _checked_decimal(quote_value("c", "last"), self.name, "last price")
        record.bid = _checked_decimal(quote_value("b", "bid"), self.name, "bid price")
        record.ask = _checked_decimal(quote_value("a", "ask"), self.name, "ask price")
        record.raw_payload = {"asset": record.raw_payload, "ticker": quote}
        record.observed_at = _now()
        return record


def _iso_datetime(value: Any, provider_name: str, field: str) -> datetime:
    """Parse an RFC3339 value without turning malformed provider data into ``now``."""

    if not isinstance(value, str) or not value.strip():
        raise ProviderResponseError(
            provider_name, f"provider returned an invalid {field} timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ProviderResponseError(
            provider_name, f"provider returned an invalid {field} timestamp"
        ) from exc
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _dinari_token_location(tokens: list[Any]) -> tuple[str | None, int | None, str | None]:
    """Extract the first valid CAIP-10 EVM location while retaining all tokens."""

    for token in tokens:
        if not isinstance(token, str) or not token.strip():
            raise ProviderResponseError("dinari", "provider returned an invalid token address")
        value = token.strip()
        if "/" not in value or ":" not in value.split("/", 1)[0]:
            continue
        namespace, chain = value.split("/", 1)[0].split(":", 1)
        try:
            chain_id = int(chain)
        except (TypeError, ValueError):
            continue
        if chain_id > 0 and chain.strip() and value.split("/", 1)[1].strip():
            return namespace, chain_id, value.split("/", 1)[1].strip()
    return None, None, None


class DinariTokenProvider:
    """Dinari dShare read-only market-data adapter.

    Dinari publishes a partner-authenticated API with provider-native Stock
    UUIDs.  The adapter deliberately keeps those UUIDs as ``asset_id`` and
    only records composite FIGI/CIK/CUSIP values as underlying metadata.
    """

    name = "dinari"
    base_url = "https://api-enterprise.sandbox.dinari.com/api/v2"
    description = "Dinari dShare tokenized-stock metadata, prices, quotes, and history"

    def __init__(self) -> None:
        # Dinari's current v2 contract uses opaque cursors once ``limit`` is
        # supplied.  Keep cursors scoped to this adapter instance so a cursor
        # from one authenticated base URL, account, or run can never leak into
        # another.  A caller that asks for a later page without first reading
        # the preceding page fails closed instead of silently re-reading page 1
        # and under-accounting the request.
        self._stock_cursors: dict[tuple[tuple[str, ...], int, int], str] = {}
        self._stock_exhausted_pages: set[tuple[tuple[str, ...], int, int]] = set()
        self._stock_seen_cursors: dict[tuple[tuple[str, ...], int], set[str]] = {}
        self._stock_legacy_page_size: int | None = None
        # UUID-based downstream reads (price, quote, history, news, and
        # corporate actions) already receive the provider-native Stock ID in
        # their path.  Keep only the validated records observed by this
        # adapter instance so those reads do not re-enumerate the entire
        # catalogue on every operation.  The cache is intentionally
        # instance-scoped: a new provider instance still performs a fresh
        # metadata lookup, so ticker/lifecycle changes are not hidden across
        # runs or authenticated environments.
        self._stock_records_by_id: dict[str, TokenizedAssetRecord] = {}
        self._split_cursors: dict[tuple[str, int, int], str] = {}
        self._split_exhausted_pages: set[tuple[str, int, int]] = set()
        self._split_seen_cursors: dict[tuple[str, int], set[str]] = {}
        self._split_legacy_page_size: int | None = None

    def _base_url(self) -> str:
        value = str(getattr(settings, "DINARI_API_BASE_URL", "") or "").strip().rstrip("/")
        return value or self.base_url

    def _headers(self) -> dict[str, str]:
        key_id = str(getattr(settings, "DINARI_API_KEY_ID", "") or "").strip()
        secret = str(getattr(settings, "DINARI_API_SECRET_KEY", "") or "").strip()
        return {"X-API-Key-Id": key_id, "X-API-Secret-Key": secret}

    def _require_configured(self) -> None:
        if (
            not str(getattr(settings, "DINARI_API_KEY_ID", "") or "").strip()
            or not str(getattr(settings, "DINARI_API_SECRET_KEY", "") or "").strip()
        ):
            raise ProviderNotConfiguredError(
                "dinari requires DINARI_API_KEY_ID and DINARI_API_SECRET_KEY"
            )

    def _stocks(
        self,
        *,
        page: int = 0,
        page_size: int = 100,
        symbols: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        # Dinari introduced cursor pagination for this endpoint and began
        # deprecating page/page_size after the transition window.  ``page`` is
        # retained in our provider interface, but is translated into a cursor
        # chain.  Legacy list responses remain supported for older sandbox
        # deployments only; once such a response is observed we explicitly
        # continue with the documented page/page_size compatibility mode.
        self._require_configured()
        if isinstance(page, bool) or not isinstance(page, int) or page < 0:
            raise ProviderResponseError(
                self.name, "Dinari stock page must be a non-negative integer"
            )
        if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size < 1:
            raise ProviderResponseError(
                self.name, "Dinari stock page size must be a positive integer"
            )
        requested_page_size = min(page_size, 100)
        limit = max(20, requested_page_size)
        normalized_symbols: tuple[str, ...] = ()
        if symbols is not None:
            if not isinstance(symbols, tuple) or any(
                not isinstance(symbol, str) or not symbol.strip() for symbol in symbols
            ):
                raise ProviderResponseError(
                    self.name, "Dinari stock symbols must be non-empty text"
                )
            normalized_symbols = tuple(dict.fromkeys(symbol.strip() for symbol in symbols))
            if len(normalized_symbols) > 100:
                raise ProviderResponseError(
                    self.name, "Dinari stock symbols cannot exceed 100 values"
                )
        scope_key = (normalized_symbols, limit)
        if page == 0:
            self._stock_seen_cursors[scope_key] = set()
            self._stock_cursors = {
                key: value for key, value in self._stock_cursors.items() if key[:2] != scope_key
            }
            self._stock_exhausted_pages = {
                key for key in self._stock_exhausted_pages if key[:2] != scope_key
            }
        cursor_key = (normalized_symbols, limit, page)
        if self._stock_legacy_page_size is not None:
            params: dict[str, Any] = {
                "page": page + 1,
                "page_size": self._stock_legacy_page_size,
            }
        else:
            if page > 0:
                if cursor_key in self._stock_exhausted_pages:
                    return []
                cursor = self._stock_cursors.get(cursor_key)
                if cursor is None:
                    raise ProviderResponseError(
                        self.name,
                        "Dinari stock page requires the preceding page cursor",
                    )
                params = {"limit": limit, "order": "asc", "next": cursor}
            else:
                params = {"limit": limit, "order": "asc"}
        if normalized_symbols:
            params["symbols"] = list(normalized_symbols)
        payload = _dinari_json(
            f"{self._base_url()}/market_data/stocks/",
            params=params,
            headers=self._headers(),
        )
        if isinstance(payload, list):
            rows = payload
            if self._stock_legacy_page_size is None:
                self._stock_legacy_page_size = requested_page_size
        elif isinstance(payload, dict):
            rows = payload.get("data")
            metadata = payload.get("pagination_metadata")
            if not isinstance(metadata, dict):
                raise ProviderResponseError(self.name, "provider omitted pagination metadata")
            if "next" not in metadata:
                raise ProviderResponseError(self.name, "provider omitted stock pagination cursor")
            next_cursor = metadata["next"]
            if next_cursor is not None:
                if isinstance(next_cursor, bool) or not isinstance(next_cursor, str):
                    raise ProviderResponseError(
                        self.name, "provider returned an invalid stock pagination cursor"
                    )
                next_cursor = next_cursor.strip()
                if not next_cursor:
                    raise ProviderResponseError(
                        self.name, "provider returned an empty stock pagination cursor"
                    )
                previous_cursor = params.get("next")
                if previous_cursor is not None and next_cursor == previous_cursor:
                    raise ProviderResponseError(
                        self.name, "provider repeated the stock pagination cursor"
                    )
                seen_cursors = self._stock_seen_cursors.setdefault(scope_key, set())
                if next_cursor in seen_cursors:
                    raise ProviderResponseError(
                        self.name, "provider repeated the stock pagination cursor"
                    )
                seen_cursors.add(next_cursor)
                self._stock_cursors[(normalized_symbols, limit, page + 1)] = next_cursor
            else:
                self._stock_exhausted_pages.add((normalized_symbols, limit, page + 1))
        else:
            rows = None
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ProviderResponseError(
                self.name, "provider returned an invalid stock row container"
            )
        return rows

    def _record(self, payload: dict[str, Any]) -> TokenizedAssetRecord:
        asset_id = str(payload.get("id") or "").strip()
        symbol = str(payload.get("symbol") or "").strip()
        name = str(payload.get("display_name") or payload.get("name") or "").strip()
        tokens = payload.get("tokens")
        if (
            not asset_id
            or not symbol
            or not name
            or not isinstance(payload.get("is_tradable"), bool)
            or not isinstance(payload.get("is_fractionable"), bool)
            or not isinstance(tokens, list)
        ):
            raise ProviderResponseError(self.name, "provider returned an incomplete Stock record")
        network, chain_id, address = _dinari_token_location(tokens)
        record = TokenizedAssetRecord(
            provider=self.name,
            asset_id=asset_id,
            symbol=symbol,
            name=name,
            underlying_symbol=symbol,
            underlying_figi=payload.get("figi") or payload.get("underlying_figi") or None,
            underlying_composite_figi=payload.get("composite_figi") or None,
            underlying_isin=payload.get("isin") or payload.get("underlying_isin") or None,
            underlying_cusip=payload.get("cusip") or payload.get("underlying_cusip") or None,
            network=network,
            chain_id=chain_id,
            contract_address=address,
            currency="USD",
            status="active" if payload.get("is_tradable") else "inactive",
            backing_type="fully_backed_dshare",
            collateral={
                "tokens": tokens,
                "composite_figi": payload.get("composite_figi"),
                "cik": payload.get("cik"),
                "cusip": payload.get("cusip"),
                "is_fractionable": payload.get("is_fractionable"),
                "description": payload.get("description"),
            },
            observed_at=_now(),
            raw_payload=payload,
        )
        self._stock_records_by_id[asset_id.lower()] = record
        return record

    def _stock_id(self, identifier: str) -> str | None:
        asset = self.get_tokenized_asset(identifier)
        return asset.asset_id if asset is not None else None

    def discover_tokenized_assets(
        self, *, page: int = 0, page_size: int = 100
    ) -> list[TokenizedAssetRecord]:
        return [self._record(row) for row in self._stocks(page=page, page_size=page_size)]

    def get_tokenized_asset(self, identifier: str) -> TokenizedAssetRecord | None:
        needle = str(identifier or "").strip().lower()
        if not needle:
            return None
        # Dinari documents ``symbols`` as an exact server-side filter. Use it
        # for ticker-like identifiers so a symbol is not missed merely because
        # it sorts after the first catalogue page. Provider Stock IDs are UUIDs
        # and are not valid values for that filter, so retain the unfiltered
        # first-page compatibility path for those callers.
        is_uuid = False
        try:
            UUID(needle)
        except (ValueError, AttributeError):
            rows = self._stocks(
                page=0,
                page_size=100,
                symbols=(str(identifier).strip().upper(),),
            )
        else:
            is_uuid = True
            cached = self._stock_records_by_id.get(needle)
            if cached is not None:
                return cached
            rows = self._stocks(page=0, page_size=100)
        row = next(
            (
                item
                for item in rows
                if str(item.get("id") or "").strip().lower() == needle
                or str(item.get("symbol") or "").strip().lower() == needle
            ),
            None,
        )
        if row is None and is_uuid:
            continuation = self._stock_cursors.get(((), 100, 1))
            if continuation:
                raise ProviderResponseError(
                    self.name,
                    "Dinari UUID lookup requires explicit catalogue continuation",
                )
        return self._record(row) if row is not None else None

    def get_tokenized_price(self, identifier: str) -> TokenizedAssetRecord | None:
        asset = self.get_tokenized_asset(identifier)
        if asset is None:
            return None
        payload = _required_object(
            _dinari_json(
                f"{self._base_url()}/market_data/stocks/{asset.asset_id}/current_price",
                headers=self._headers(),
            ),
            self.name,
            "stock price",
        )
        if str(payload.get("stock_id") or "") != asset.asset_id:
            raise ProviderResponseError(
                self.name, "provider returned a price for a different Stock"
            )
        price = _decimal(payload.get("price"))
        if price is None or not price.is_finite():
            raise ProviderResponseError(self.name, "provider returned an invalid Stock price")
        observed_at = _iso_datetime(payload.get("timestamp"), self.name, "Stock price")
        asset.price = price
        asset.observed_at = observed_at
        asset.raw_payload = {"asset": asset.raw_payload, "price": payload}
        return asset

    def get_tokenized_quote(self, identifier: str) -> TokenizedAssetRecord | None:
        asset = self.get_tokenized_asset(identifier)
        if asset is None:
            return None
        payload = _required_object(
            _dinari_json(
                f"{self._base_url()}/market_data/stocks/{asset.asset_id}/current_quote",
                headers=self._headers(),
            ),
            self.name,
            "stock quote",
        )
        if str(payload.get("stock_id") or "") != asset.asset_id:
            raise ProviderResponseError(
                self.name, "provider returned a quote for a different Stock"
            )
        bid = _decimal(payload.get("bid_price"))
        ask = _decimal(payload.get("ask_price"))
        if bid is None or ask is None or not bid.is_finite() or not ask.is_finite():
            raise ProviderResponseError(self.name, "provider returned an invalid Stock quote")
        asset.bid = bid
        asset.ask = ask
        asset.observed_at = _iso_datetime(payload.get("timestamp"), self.name, "Stock quote")
        asset.raw_payload = {"asset": asset.raw_payload, "quote": payload}
        return asset

    def fetch_tokenized_historical_prices(
        self, identifier: str, *, timespan: str = "DAY"
    ) -> list[dict[str, Any]]:
        """Return Dinari's aggregate price points without inventing OHLCV volume."""

        allowed = {"DAY", "WEEK", "MONTH", "YEAR"}
        normalized_timespan = str(timespan or "").strip().upper()
        if normalized_timespan not in allowed:
            raise ProviderResponseError(self.name, "unsupported Dinari historical timespan")
        stock_id = self._stock_id(identifier)
        if stock_id is None:
            return []
        payload = _dinari_json(
            f"{self._base_url()}/market_data/stocks/{stock_id}/historical_prices/",
            params={"timespan": normalized_timespan},
            headers=self._headers(),
        )
        if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
            raise ProviderResponseError(
                self.name, "provider returned an invalid historical price row container"
            )
        result: list[dict[str, Any]] = []
        for row in payload:
            try:
                timestamp = int(row["timestamp"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ProviderResponseError(
                    self.name, "provider returned an invalid historical price timestamp"
                ) from exc
            if timestamp <= 0:
                raise ProviderResponseError(
                    self.name, "provider returned an invalid historical price timestamp"
                )
            values = {field: _decimal(row.get(field)) for field in ("open", "high", "low", "close")}
            if any(value is None or not value.is_finite() for value in values.values()):
                raise ProviderResponseError(
                    self.name, "provider returned an invalid historical price row"
                )
            result.append(
                {
                    "stock_id": stock_id,
                    "timespan": normalized_timespan,
                    "timestamp": datetime.fromtimestamp(timestamp, tz=UTC),
                    **values,
                    "raw_payload": row,
                }
            )
        return result

    def fetch_tokenized_news(self, identifier: str, *, limit: int = 10) -> list[dict[str, Any]]:
        stock_id = self._stock_id(identifier)
        if stock_id is None:
            return []
        payload = _dinari_json(
            f"{self._base_url()}/market_data/stocks/{stock_id}/news",
            params={"limit": max(1, min(int(limit), 25))},
            headers=self._headers(),
        )
        if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
            raise ProviderResponseError(
                self.name, "provider returned an invalid stock news row container"
            )
        result: list[dict[str, Any]] = []
        for row in payload:
            required = ("article_url", "description", "image_url", "published_dt", "publisher")
            if any(not str(row.get(field) or "").strip() for field in required):
                raise ProviderResponseError(
                    self.name, "provider returned an incomplete stock news article"
                )
            published_at = _iso_datetime(row["published_dt"], self.name, "stock news")
            result.append({**row, "published_dt": published_at})
        return result

    def _fetch_dividends_for_stock_id(self, stock_id: str) -> list[dict[str, Any]]:
        payload = _dinari_json(
            f"{self._base_url()}/market_data/stocks/{stock_id}/dividends",
            headers=self._headers(),
        )
        if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
            raise ProviderResponseError(
                self.name, "provider returned an invalid stock dividend row container"
            )
        return payload

    def fetch_tokenized_dividends(self, identifier: str) -> list[dict[str, Any]]:
        stock_id = self._stock_id(identifier)
        return self._fetch_dividends_for_stock_id(stock_id) if stock_id is not None else []

    def _fetch_split_page(
        self,
        *,
        endpoint: str,
        scope: str,
        page: int,
        page_size: int,
    ) -> list[dict[str, Any]]:
        """Read one documented split page and retain only its next cursor.

        Dinari's cursor is opaque and scoped to the exact feed/limit.  A
        caller must therefore request pages in order on the same adapter
        instance; this prevents accidental cross-feed reuse and avoids an
        unbounded loop that could consume a partner quota unexpectedly.
        """

        self._require_configured()
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ProviderResponseError(self.name, "Dinari split page must be positive")
        if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size < 1:
            raise ProviderResponseError(self.name, "Dinari split page size must be positive")
        requested_page_size = min(page_size, 100)
        limit = max(20, requested_page_size)
        scope_key = (scope, limit)
        if page == 1:
            self._split_seen_cursors[scope_key] = set()
            self._split_cursors = {
                key: value for key, value in self._split_cursors.items() if key[:2] != scope_key
            }
            self._split_exhausted_pages = {
                key for key in self._split_exhausted_pages if key[:2] != scope_key
            }
        cursor_key = (scope, limit, page)
        if self._split_legacy_page_size is not None:
            params: dict[str, Any] = {
                "page": page,
                "page_size": self._split_legacy_page_size,
            }
        elif page == 1:
            params = {"limit": limit, "order": "desc"}
        else:
            if cursor_key in self._split_exhausted_pages:
                return []
            cursor = self._split_cursors.get(cursor_key)
            if cursor is None:
                raise ProviderResponseError(
                    self.name, "Dinari split page requires the preceding page cursor"
                )
            params = {"limit": limit, "order": "desc", "next": cursor}
        payload = _dinari_json(
            endpoint,
            params=params,
            headers=self._headers(),
        )
        if isinstance(payload, list):
            rows = payload
            if self._split_legacy_page_size is None:
                self._split_legacy_page_size = requested_page_size
        elif isinstance(payload, dict):
            rows = payload.get("data")
            metadata = payload.get("pagination_metadata")
            if not isinstance(metadata, dict) or "next" not in metadata:
                raise ProviderResponseError(self.name, "provider omitted split pagination metadata")
            next_cursor = metadata["next"]
            if next_cursor is not None and (
                isinstance(next_cursor, bool)
                or not isinstance(next_cursor, str)
                or not next_cursor.strip()
            ):
                raise ProviderResponseError(
                    self.name, "provider returned an invalid split pagination cursor"
                )
            if next_cursor is not None:
                next_cursor = next_cursor.strip()
                previous_cursor = params.get("next")
                if previous_cursor is not None and next_cursor == previous_cursor:
                    raise ProviderResponseError(
                        self.name, "provider repeated the split pagination cursor"
                    )
                seen_cursors = self._split_seen_cursors.setdefault(scope_key, set())
                if next_cursor in seen_cursors:
                    raise ProviderResponseError(
                        self.name, "provider repeated the split pagination cursor"
                    )
                seen_cursors.add(next_cursor)
                self._split_cursors[(scope, limit, page + 1)] = next_cursor
            else:
                self._split_exhausted_pages.add((scope, limit, page + 1))
        else:
            rows = None
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ProviderResponseError(
                self.name, "provider returned an invalid stock split row container"
            )
        return rows

    def _fetch_splits_for_stock_id(
        self, stock_id: str, *, page: int = 1, page_size: int = 100
    ) -> list[dict[str, Any]]:
        return self._fetch_split_page(
            endpoint=f"{self._base_url()}/market_data/stocks/{stock_id}/splits",
            scope=f"stock:{stock_id}",
            page=page,
            page_size=page_size,
        )

    def fetch_tokenized_splits(
        self, identifier: str, *, page: int = 1, page_size: int = 100
    ) -> list[dict[str, Any]]:
        stock_id = self._stock_id(identifier)
        return (
            self._fetch_splits_for_stock_id(stock_id, page=page, page_size=page_size)
            if stock_id is not None
            else []
        )

    def _fetch_global_splits(self, *, page: int, page_size: int) -> list[dict[str, Any]]:
        return self._fetch_split_page(
            endpoint=f"{self._base_url()}/market_data/stocks/splits",
            scope="global",
            page=page,
            page_size=page_size,
        )

    def fetch_tokenized_corporate_actions(
        self,
        *,
        symbol: str | None = None,
        upcoming: bool = False,
        page: int = 1,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """Expose Dinari's documented split/dividend reads as one action feed.

        Dinari has no global dividend endpoint. A symbol-scoped request can
        therefore combine the two per-stock feeds, while an unscoped request
        returns only the global split catalogue. The API does not expose an
        ``upcoming`` filter for these reads; refusing that semantic is safer
        than labelling a provider-wide response as historical or upcoming.
        """

        if upcoming:
            raise ProviderResponseError(
                self.name,
                "Dinari corporate-action endpoints do not expose an upcoming filter",
            )
        if symbol is not None and not str(symbol).strip():
            raise ProviderResponseError(
                self.name, "Dinari corporate-action symbol must be non-empty"
            )
        if symbol is not None:
            stock_id = self._stock_id(str(symbol).strip())
            if stock_id is None:
                return []
            dividends = self._fetch_dividends_for_stock_id(stock_id) if page == 1 else []
            splits = self._fetch_splits_for_stock_id(stock_id, page=page, page_size=page_size)
            return [
                {**row, "action_type": "dividend", "stock_id": stock_id} for row in dividends
            ] + [{**row, "action_type": "split", "stock_id": stock_id} for row in splits]
        return [
            {**row, "action_type": "split"}
            for row in self._fetch_global_splits(page=page, page_size=page_size)
        ]


class OndoGlobalMarketsProvider:
    """Ondo Stocks (legacy GM) authenticated metadata and price adapter."""

    name = "ondo_global_markets"
    base_url = "https://api.gm.ondo.finance"
    description = "Ondo Stocks tokenized US stock/ETF metadata and indicative prices"

    def _headers(self) -> dict[str, str]:
        key = str(getattr(settings, "ONDO_GLOBAL_MARKETS_API_KEY", "") or "").strip()
        return {"x-api-key": key}

    def _require_configured(self) -> None:
        if not str(getattr(settings, "ONDO_GLOBAL_MARKETS_API_KEY", "") or "").strip():
            raise ProviderNotConfiguredError(
                "ondo_global_markets requires ONDO_GLOBAL_MARKETS_API_KEY"
            )

    @staticmethod
    def _location(addresses: list[Any]) -> tuple[str | None, int | None, str | None]:
        for item in addresses:
            if not isinstance(item, dict):
                raise ProviderResponseError(
                    "ondo_global_markets", "provider returned an invalid contract address"
                )
            chain = str(item.get("networkChainId") or "").strip()
            address = str(item.get("address") or "").strip()
            if not chain or not address:
                raise ProviderResponseError(
                    "ondo_global_markets", "provider returned an incomplete contract address"
                )
            try:
                network, chain_id_text = chain.rsplit("-", 1)
                chain_id = int(chain_id_text)
            except (TypeError, ValueError):
                continue
            if chain_id > 0:
                return network, chain_id, address
        return None, None, None

    def _metadata(self) -> list[dict[str, Any]]:
        self._require_configured()
        payload = _http_json(
            f"{self.base_url}/v1/assets/all/metadata",
            provider_name=self.name,
            headers=self._headers(),
        )
        if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
            raise ProviderResponseError(
                self.name, "provider returned an invalid metadata row container"
            )
        return payload

    def _record(self, payload: dict[str, Any]) -> TokenizedAssetRecord:
        symbol = str(payload.get("symbol") or "").strip()
        underlying_symbol = str(payload.get("ticker") or "").strip()
        name = str(payload.get("displayName") or payload.get("underlyingName") or "").strip()
        tags = payload.get("tags")
        addresses = payload.get("addresses")
        if not symbol or not underlying_symbol or not name or not isinstance(tags, dict):
            raise ProviderResponseError(self.name, "provider returned incomplete asset metadata")
        if not isinstance(addresses, list):
            raise ProviderResponseError(
                self.name, "provider returned an invalid asset address container"
            )
        network, chain_id, address = self._location(addresses)
        return TokenizedAssetRecord(
            provider=self.name,
            asset_id=symbol,
            symbol=symbol,
            name=name,
            underlying_symbol=underlying_symbol,
            underlying_isin=str(payload.get("isin") or "") or None,
            network=network,
            chain_id=chain_id,
            contract_address=address,
            currency="USD",
            status="active",
            backing_type="fully_backed_ondo_stock",
            collateral={
                "addresses": addresses,
                "tags": tags,
                "coingecko_id": payload.get("coingeckoId"),
                "coinmarketcap_id": payload.get("coinmarketCapId"),
                "logo_uri": payload.get("logoURI"),
            },
            observed_at=_now(),
            raw_payload=payload,
        )

    def discover_tokenized_assets(
        self, *, page: int = 0, page_size: int = 100
    ) -> list[TokenizedAssetRecord]:
        rows = self._metadata()
        start = max(0, page) * max(1, page_size)
        return [self._record(row) for row in rows[start : start + max(1, page_size)]]

    def get_tokenized_asset(self, identifier: str) -> TokenizedAssetRecord | None:
        needle = str(identifier or "").strip().lower()
        if not needle:
            return None
        row = next(
            (
                item
                for item in self._metadata()
                if str(item.get("symbol") or "").strip().lower() == needle
                or str(item.get("ticker") or "").strip().lower() == needle
            ),
            None,
        )
        return self._record(row) if row is not None else None

    def get_tokenized_price(self, identifier: str) -> TokenizedAssetRecord | None:
        asset = self.get_tokenized_asset(identifier)
        if asset is None:
            return None
        payload = _required_object(
            _http_json(
                f"{self.base_url}/v1/assets/{asset.symbol}/prices/latest",
                provider_name=self.name,
                headers=self._headers(),
            ),
            self.name,
            "asset price",
        )
        primary = payload.get("primaryMarket")
        underlying = payload.get("underlyingMarket")
        if not isinstance(primary, dict) or not isinstance(underlying, dict):
            raise ProviderResponseError(self.name, "provider returned an incomplete asset price")
        if str(primary.get("symbol") or "") != asset.symbol:
            raise ProviderResponseError(
                self.name, "provider returned a price for a different asset"
            )
        price = _decimal(primary.get("price"))
        if price is None or not price.is_finite():
            raise ProviderResponseError(self.name, "provider returned an invalid asset price")
        timestamp = payload.get("timestamp")
        try:
            observed_at = datetime.fromtimestamp(float(timestamp) / 1000, tz=UTC)
        except (TypeError, ValueError, OverflowError, OSError) as exc:
            raise ProviderResponseError(
                self.name, "provider returned an invalid asset price timestamp"
            ) from exc
        asset.price = price
        asset.observed_at = observed_at
        asset.raw_payload = {"asset": asset.raw_payload, "price": payload}
        return asset

    def fetch_tokenized_market_data(self, identifier: str) -> dict[str, Any] | None:
        """Return Ondo's primary-token and underlying-stock market summary.

        The endpoint is display-oriented and may be cached by Ondo. Keep the
        two market identities separate and normalize only documented numeric
        fields; omitted optional metrics remain omitted rather than becoming
        fabricated zeros.
        """

        asset = self.get_tokenized_asset(identifier)
        if asset is None:
            return None
        payload = _required_object(
            _http_json(
                f"{self.base_url}/v1/assets/{asset.symbol}/market",
                provider_name=self.name,
                headers=self._headers(),
            ),
            self.name,
            "asset market data",
        )
        primary = _required_object(payload.get("primaryMarket"), self.name, "primary market")
        underlying = _required_object(
            payload.get("underlyingMarket"), self.name, "underlying market"
        )
        if str(primary.get("symbol") or "").strip() != asset.symbol:
            raise ProviderResponseError(
                self.name, "provider returned market data for a different asset"
            )
        if str(underlying.get("ticker") or "").strip() != asset.underlying_symbol:
            raise ProviderResponseError(
                self.name, "provider returned underlying market data for a different asset"
            )

        def _required_decimal(body: dict[str, Any], field: str, context: str) -> Decimal:
            value = _decimal(body.get(field))
            if value is None or not value.is_finite():
                raise ProviderResponseError(
                    self.name, f"provider returned an invalid {context} {field}"
                )
            return value

        def _optional_decimal(body: dict[str, Any], field: str, context: str) -> Decimal | None:
            if field not in body or body.get(field) is None:
                return None
            return _required_decimal(body, field, context)

        def _optional_nonnegative_int(body: dict[str, Any], field: str, context: str) -> int | None:
            if field not in body or body.get(field) is None:
                return None
            value = body.get(field)
            if isinstance(value, bool):
                raise ProviderResponseError(
                    self.name, f"provider returned an invalid {context} {field}"
                )
            try:
                parsed = int(value)
            except (TypeError, ValueError) as exc:
                raise ProviderResponseError(
                    self.name, f"provider returned an invalid {context} {field}"
                ) from exc
            if parsed < 0 or str(value).strip() != str(parsed):
                raise ProviderResponseError(
                    self.name, f"provider returned an invalid {context} {field}"
                )
            return parsed

        primary_history: list[dict[str, Any]] = []
        if "priceHistory24h" in primary:
            rows = primary["priceHistory24h"]
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ProviderResponseError(
                    self.name, "provider returned an invalid primary price history"
                )
            for row in rows:
                try:
                    timestamp = int(row["timestamp"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise ProviderResponseError(
                        self.name, "provider returned an invalid primary price-history timestamp"
                    ) from exc
                if timestamp <= 0:
                    raise ProviderResponseError(
                        self.name, "provider returned an invalid primary price-history timestamp"
                    )
                primary_history.append(
                    {
                        "timestamp": datetime.fromtimestamp(timestamp / 1000, tz=UTC),
                        "price": _required_decimal(row, "price", "primary price history"),
                        "raw_payload": row,
                    }
                )

        sessions: list[str] | None = None
        if "tradableSessions" in primary:
            raw_sessions = primary["tradableSessions"]
            if not isinstance(raw_sessions, list) or any(
                not isinstance(session, str) or not session.strip() for session in raw_sessions
            ):
                raise ProviderResponseError(
                    self.name, "provider returned invalid tradable sessions"
                )
            sessions = [session.strip() for session in raw_sessions]

        timestamp = payload.get("timestamp")
        try:
            observed_at = datetime.fromtimestamp(float(timestamp) / 1000, tz=UTC)
        except (TypeError, ValueError, OverflowError, OSError) as exc:
            raise ProviderResponseError(
                self.name, "provider returned an invalid market-data timestamp"
            ) from exc
        if observed_at <= datetime(1970, 1, 1, tzinfo=UTC):
            raise ProviderResponseError(
                self.name, "provider returned an invalid market-data timestamp"
            )

        primary_data: dict[str, Any] = {
            "symbol": asset.symbol,
            "price": _required_decimal(primary, "price", "primary market"),
            "price_change_24h": _optional_decimal(primary, "priceChange24h", "primary market"),
            "price_change_pct_24h": _optional_decimal(
                primary, "priceChangePct24h", "primary market"
            ),
            "price_history_24h": primary_history,
            "total_holders": _optional_nonnegative_int(primary, "totalHolders", "primary market"),
            "shares_multiplier": _optional_decimal(primary, "sharesMultiplier", "primary market"),
            "tradable_sessions": sessions,
        }
        underlying_data: dict[str, Any] = {
            "ticker": asset.underlying_symbol,
            "name": str(underlying.get("name") or "").strip(),
            "price": _required_decimal(underlying, "price", "underlying market"),
        }
        if not underlying_data["name"]:
            raise ProviderResponseError(
                self.name, "provider returned an incomplete underlying market name"
            )
        for source_field, target_field in (
            ("priceHigh52w", "price_high_52w"),
            ("priceLow52w", "price_low_52w"),
            ("volume", "volume"),
            ("averageVolume", "average_volume"),
            ("sharesOutstanding", "shares_outstanding"),
            ("marketCap", "market_cap"),
        ):
            underlying_data[target_field] = _optional_decimal(
                underlying, source_field, "underlying market"
            )
        return {
            "provider": self.name,
            "symbol": asset.symbol,
            "underlying_symbol": asset.underlying_symbol,
            "observed_at": observed_at,
            "primary_market": primary_data,
            "underlying_market": underlying_data,
            "raw_payload": payload,
        }

    def fetch_tokenized_ohlc(
        self,
        identifier: str,
        *,
        interval: str = "1day",
        range_: str = "1day",
        market: str = "primary",
    ) -> list[dict[str, Any]]:
        """Return display-only Ondo OHLC candles with explicit market scope."""

        allowed_ranges = {
            "1min": {"1day"},
            "5min": {"1day"},
            "15min": {"1day"},
            "1hour": {"1month"},
            "4hour": {"1month"},
            "12hour": {"3month"},
            "1day": {"3month", "6month", "1year", "all"},
        }
        normalized_interval = str(interval or "").strip().lower()
        normalized_range = str(range_ or "").strip().lower()
        if normalized_range not in allowed_ranges.get(normalized_interval, set()):
            raise ProviderResponseError(self.name, "unsupported Ondo OHLC interval/range pair")
        normalized_market = str(market or "").strip().lower()
        if normalized_market not in {"primary", "underlying", "both"}:
            raise ProviderResponseError(self.name, "unsupported Ondo OHLC market")
        asset = self.get_tokenized_asset(identifier)
        if asset is None:
            return []
        payload = _required_object(
            _http_json(
                f"{self.base_url}/v1/assets/{asset.symbol}/prices/ohlc",
                provider_name=self.name,
                params={"interval": normalized_interval, "range": normalized_range},
                headers=self._headers(),
            ),
            self.name,
            "OHLC response",
        )
        markets = (
            ("primaryMarket", "underlyingMarket")
            if normalized_market == "both"
            else (("primaryMarket",) if normalized_market == "primary" else ("underlyingMarket",))
        )
        result: list[dict[str, Any]] = []
        for market_key in markets:
            market_body = _required_object(payload.get(market_key), self.name, market_key)
            expected_symbol = (
                asset.symbol if market_key == "primaryMarket" else asset.underlying_symbol
            )
            actual_symbol = str(
                market_body.get("symbol") or market_body.get("ticker") or ""
            ).strip()
            if not expected_symbol or actual_symbol != expected_symbol:
                raise ProviderResponseError(
                    self.name, "provider returned OHLC for a different asset"
                )
            rows = market_body.get("data")
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ProviderResponseError(
                    self.name, f"provider returned an invalid {market_key} row container"
                )
            for row in rows:
                try:
                    timestamp = int(row["timestamp"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise ProviderResponseError(
                        self.name, "provider returned an invalid OHLC timestamp"
                    ) from exc
                if timestamp <= 0:
                    raise ProviderResponseError(
                        self.name, "provider returned an invalid OHLC timestamp"
                    )
                values = {
                    field: _decimal(row.get(field)) for field in ("open", "high", "low", "close")
                }
                if any(value is None or not value.is_finite() for value in values.values()):
                    raise ProviderResponseError(self.name, "provider returned an invalid OHLC row")
                result.append(
                    {
                        "market": "primary" if market_key == "primaryMarket" else "underlying",
                        "symbol": actual_symbol,
                        "interval": normalized_interval,
                        "range": normalized_range,
                        "timestamp": datetime.fromtimestamp(timestamp / 1000, tz=UTC),
                        **values,
                        "raw_payload": row,
                    }
                )
        return result


TOKENIZED_PROVIDERS = (
    XStocksProvider,
    RobinhoodTokenProvider,
    BybitXStocksProvider,
    GateTradfiProvider,
    KrakenXStocksProvider,
    DinariTokenProvider,
    OndoGlobalMarketsProvider,
)
