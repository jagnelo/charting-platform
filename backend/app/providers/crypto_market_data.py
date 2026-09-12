"""Keyless public crypto adapters for Coinbase Exchange and Kraken."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import ceil, isfinite
from typing import Any

import httpx

from app.models.ohlcv import OHLCVBar, Timeframe
from app.providers.errors import (
    ProviderRateLimitError,
    ProviderResponseError,
    provider_response_headers,
    provider_retry_at_from_headers,
    raise_for_provider_error_envelope,
)
from app.providers.telemetry import observe_response

_TF_SECONDS = {
    Timeframe.M1: 60,
    Timeframe.M5: 300,
    Timeframe.M15: 900,
    Timeframe.M30: 1800,
    Timeframe.H1: 3600,
    Timeframe.H2: 7200,
    Timeframe.H4: 14400,
    Timeframe.H12: 43200,
    Timeframe.D1: 86400,
    Timeframe.W1: 604800,
}


def _require_raw_history(provider_name: str, adjusted: bool) -> None:
    """Reject adjusted requests for exchange candles with no adjustment feed."""

    if adjusted:
        raise ProviderResponseError(
            provider_name,
            f"{provider_name} exchange candles are raw; request adjusted=False",
        )

_COINBASE_CANDLES_PER_REQUEST = 300
_KRAKEN_CANDLES_PER_REQUEST = 720


def _estimate_request_count(
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    *,
    candles_per_request: int,
) -> int | None:
    seconds = _TF_SECONDS.get(timeframe)
    if seconds is None or end <= start:
        return 0 if end <= start else None
    span_seconds = max(0.0, (end - start).total_seconds())
    return max(1, ceil(span_seconds / (seconds * candles_per_request)))


def estimate_coinbase_ohlcv_request_count(
    timeframe: Timeframe, start: datetime, end: datetime
) -> int | None:
    """Estimate Coinbase candle calls for its documented 300-candle page cap."""

    return _estimate_request_count(
        timeframe,
        start,
        end,
        candles_per_request=_COINBASE_CANDLES_PER_REQUEST,
    )


def estimate_coinbase_latest_ohlcv_request_count(timeframe: Timeframe, limit: int) -> int | None:
    if limit <= 0:
        return 0
    if timeframe not in _TF_SECONDS:
        return None
    return max(1, ceil(limit / _COINBASE_CANDLES_PER_REQUEST))


def estimate_kraken_ohlcv_request_count(
    timeframe: Timeframe, start: datetime, end: datetime
) -> int | None:
    """Estimate Kraken OHLC calls for its documented 720-candle page cap."""

    return _estimate_request_count(
        timeframe,
        start,
        end,
        candles_per_request=_KRAKEN_CANDLES_PER_REQUEST,
    )


def estimate_kraken_latest_ohlcv_request_count(timeframe: Timeframe, limit: int) -> int | None:
    if limit <= 0:
        return 0
    if timeframe not in _TF_SECONDS:
        return None
    return max(1, ceil(limit / _KRAKEN_CANDLES_PER_REQUEST))


def _json_payload(response: httpx.Response, provider_name: str) -> Any:
    try:
        payload = response.json()
    except (TypeError, ValueError) as exc:
        raise ProviderResponseError(provider_name, "provider returned invalid JSON") from exc
    raise_for_provider_error_envelope(
        provider_name, payload, response.status_code, headers=provider_response_headers(response)
    )
    return payload


def _get_json(
    provider_name: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float,
) -> Any:
    try:
        response = httpx.get(url, params=params, timeout=timeout)
        observe_response(response)
        response.raise_for_status()
        return _json_payload(response, provider_name)
    except httpx.HTTPStatusError as exc:
        headers = provider_response_headers(exc.response)
        if exc.response.status_code in {418, 429}:
            raise ProviderRateLimitError(
                provider_name,
                f"provider request rejected for capacity (HTTP {exc.response.status_code})",
                retry_at=provider_retry_at_from_headers(headers),
                status_code=exc.response.status_code,
                headers=headers,
            ) from exc
        raise ProviderResponseError(
            provider_name,
            f"provider request failed with HTTP {exc.response.status_code}",
            status_code=exc.response.status_code,
        ) from exc
    except httpx.RequestError as exc:
        raise ProviderResponseError(provider_name, str(exc)) from exc


def _required_candle_rows(payload: Any, provider_name: str, width: int) -> list[list[Any]]:
    if not isinstance(payload, list):
        raise ProviderResponseError(provider_name, "provider returned an invalid candle array")
    if any(not isinstance(row, list) or len(row) < width for row in payload):
        raise ProviderResponseError(provider_name, "provider returned an invalid candle row")
    return payload


def _candle_float(value: Any, provider_name: str, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ProviderResponseError(
            provider_name, f"provider returned an invalid candle {field}"
        ) from exc
    if not isfinite(parsed):
        raise ProviderResponseError(provider_name, f"provider returned an invalid candle {field}")
    return parsed


def _candle_timestamp(value: Any, provider_name: str, field: str) -> datetime:
    """Parse a provider epoch value without leaking platform conversion errors."""

    epoch = _candle_float(value, provider_name, field)
    try:
        return datetime.fromtimestamp(epoch, tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise ProviderResponseError(
            provider_name, f"provider returned an invalid candle {field}"
        ) from exc


class CoinbaseProvider:
    name = "coinbase"
    base_url = "https://api.exchange.coinbase.com"
    description = "Coinbase Exchange public crypto candles, ticker, and products"

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
        _require_raw_history(self.name, adjusted)
        seconds = _TF_SECONDS.get(timeframe)
        if seconds is None:
            raise ProviderResponseError(self.name, f"unsupported crypto timeframe: {timeframe}")
        if end <= start:
            return []
        product = _coinbase_product(symbol)
        # Coinbase caps each response at 300 candles. Page the requested range
        # explicitly and deduplicate boundary candles; the caller's runtime
        # reservation is computed by ``estimate_coinbase_ohlcv_request_count``.
        bars_by_timestamp: dict[datetime, OHLCVBar] = {}
        cursor = start
        while cursor < end:
            limit_end = min(
                end,
                cursor + timedelta(seconds=seconds * _COINBASE_CANDLES_PER_REQUEST),
            )
            rows = _get_json(
                self.name,
                f"{self.base_url}/products/{product}/candles",
                params={
                    "granularity": seconds,
                    "start": cursor.isoformat(),
                    "end": limit_end.isoformat(),
                },
                timeout=30,
            )
            for row in _required_candle_rows(rows, self.name, 6):
                ts = _candle_timestamp(row[0], self.name, "timestamp")
                if not start <= ts < end:
                    continue
                bars_by_timestamp[ts] = OHLCVBar(
                    instrument_id=instrument_id,
                    data_source_id=data_source_id,
                    timeframe=timeframe,
                    ts=ts,
                    low=_candle_float(row[1], self.name, "low"),
                    high=_candle_float(row[2], self.name, "high"),
                    open=_candle_float(row[3], self.name, "open"),
                    close=_candle_float(row[4], self.name, "close"),
                    volume=_candle_float(row[5], self.name, "volume"),
                    is_adjusted=False,
                    adjustment_basis="raw",
                    adjustment_version="provider-native",
                    provenance={
                        "provider": self.name,
                        "endpoint": f"/products/{product}/candles",
                        "provider_symbol": product,
                        "provider_payload": row,
                    },
                )
            cursor = limit_end
        return [bars_by_timestamp[ts] for ts in sorted(bars_by_timestamp)]

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
        if limit <= 0:
            return []
        seconds = _TF_SECONDS.get(timeframe)
        if seconds is None:
            raise ProviderResponseError(self.name, f"unsupported crypto timeframe: {timeframe}")
        end = datetime.now(UTC)
        return self.fetch_ohlcv(
            symbol,
            timeframe,
            end - timedelta(seconds=seconds * limit),
            end,
            adjusted=adjusted,
            instrument_id=instrument_id,
            data_source_id=data_source_id,
        )[-limit:]

    def latest_window_start(self, timeframe: Timeframe, limit: int) -> datetime:
        seconds = _TF_SECONDS.get(timeframe)
        if seconds is None:
            raise ProviderResponseError(self.name, f"unsupported crypto timeframe: {timeframe}")
        return datetime.now(UTC) - timedelta(
            seconds=seconds * max(limit, 1)
        )

    def get_current_price(self, symbol: str) -> float | None:
        payload = _get_json(
            self.name,
            f"{self.base_url}/products/{_coinbase_product(symbol)}/ticker",
            timeout=15,
        )
        if not isinstance(payload, dict) or payload.get("price") in (None, ""):
            raise ProviderResponseError(self.name, "Coinbase returned an invalid ticker object")
        return _candle_float(payload["price"], self.name, "ticker price")

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        if quote_type.upper() != "CRYPTOCURRENCY":
            return {"total": 0, "quotes": []}
        products_payload = _get_json(self.name, f"{self.base_url}/products", timeout=30)
        if not isinstance(products_payload, list):
            raise ProviderResponseError(self.name, "Coinbase returned an invalid products array")
        if any(not isinstance(item, dict) for item in products_payload):
            raise ProviderResponseError(self.name, "Coinbase returned a non-object product row")
        products = [
            item
            for item in products_payload
            if item.get("quote_currency") == "USD" and item.get("status") == "online"
        ]
        page = products[offset : offset + 500]
        for item in page:
            base_currency = str(item.get("base_currency") or "").strip()
            product_id = str(item.get("id") or "").strip()
            if not base_currency or not product_id:
                raise ProviderResponseError(self.name, "Coinbase returned an incomplete product identity")
        return {
            "total": len(products),
            "quotes": [
                {
                    "symbol": f"{item['base_currency']}-USD",
                    "longName": str(item.get("display_name") or item["id"]),
                    "exchange": "Coinbase",
                    "quoteType": "CRYPTOCURRENCY",
                    "status": "active",
                    "source_record": item,
                }
                for item in page
            ],
        }

    def supported_discovery_types(self) -> list[str]:
        return ["CRYPTOCURRENCY"]


class KrakenProvider:
    name = "kraken"
    base_url = "https://api.kraken.com/0/public"
    description = "Kraken public crypto OHLC, ticker, and asset-pair metadata"

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
        _require_raw_history(self.name, adjusted)
        seconds = _TF_SECONDS.get(timeframe)
        if seconds is None:
            raise ProviderResponseError(self.name, f"unsupported crypto timeframe: {timeframe}")
        interval = max(1, seconds // 60)
        if end <= start:
            return []
        provider_pair = _kraken_pair(symbol)
        bars_by_timestamp: dict[datetime, OHLCVBar] = {}
        cursor = start
        seen_cursors: set[int] = set()
        while cursor < end:
            cursor_seconds = int(cursor.timestamp())
            if cursor_seconds in seen_cursors:
                break
            seen_cursors.add(cursor_seconds)
            payload = _get_json(
                self.name,
                f"{self.base_url}/OHLC",
                params={
                    "pair": provider_pair,
                    "interval": interval,
                    "since": cursor_seconds,
                },
                timeout=30,
            )
            if not isinstance(payload, dict):
                raise ProviderResponseError(self.name, "Kraken returned an invalid OHLC JSON object")
            result = payload.get("result")
            if not isinstance(result, dict):
                raise ProviderResponseError(self.name, "Kraken returned an invalid OHLC result")
            row_lists = [value for key, value in result.items() if key != "last"]
            if not row_lists or any(not isinstance(value, list) for value in row_lists):
                raise ProviderResponseError(self.name, "Kraken returned an invalid OHLC row container")
            rows = _required_candle_rows(row_lists[0], self.name, 7)
            max_timestamp: datetime | None = None
            for row in rows:
                ts = _candle_timestamp(row[0], self.name, "timestamp")
                max_timestamp = max(max_timestamp, ts) if max_timestamp else ts
                if not start <= ts < end:
                    continue
                bars_by_timestamp[ts] = OHLCVBar(
                    instrument_id=instrument_id,
                    data_source_id=data_source_id,
                    timeframe=timeframe,
                    ts=ts,
                    open=_candle_float(row[1], self.name, "open"),
                    high=_candle_float(row[2], self.name, "high"),
                    low=_candle_float(row[3], self.name, "low"),
                    close=_candle_float(row[4], self.name, "close"),
                    volume=_candle_float(row[6], self.name, "volume"),
                    is_adjusted=False,
                    adjustment_basis="raw",
                    adjustment_version="provider-native",
                    provenance={
                        "provider": self.name,
                        "endpoint": "/0/public/OHLC",
                        "provider_symbol": provider_pair,
                        "provider_payload": row,
                    },
                )
            provider_last = result.get("last")
            try:
                provider_last_dt = (
                    _candle_timestamp(provider_last, self.name, "OHLC cursor")
                    if provider_last is not None
                    else None
                )
            except (TypeError, ValueError, OverflowError) as exc:
                raise ProviderResponseError(
                    self.name, "Kraken returned an invalid OHLC cursor"
                ) from exc
            next_cursor = cursor + timedelta(seconds=seconds)
            if max_timestamp is not None:
                next_cursor = max(next_cursor, max_timestamp + timedelta(seconds=seconds))
            if provider_last_dt is not None:
                next_cursor = max(next_cursor, provider_last_dt + timedelta(seconds=seconds))
            if not rows or next_cursor <= cursor:
                break
            cursor = next_cursor
        return [bars_by_timestamp[ts] for ts in sorted(bars_by_timestamp)]

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
        if limit <= 0:
            return []
        seconds = _TF_SECONDS.get(timeframe)
        if seconds is None:
            raise ProviderResponseError(self.name, f"unsupported crypto timeframe: {timeframe}")
        end = datetime.now(UTC)
        return self.fetch_ohlcv(
            symbol,
            timeframe,
            end - timedelta(seconds=seconds * limit),
            end,
            adjusted=adjusted,
            instrument_id=instrument_id,
            data_source_id=data_source_id,
        )[-limit:]

    def latest_window_start(self, timeframe: Timeframe, limit: int) -> datetime:
        seconds = _TF_SECONDS.get(timeframe)
        if seconds is None:
            raise ProviderResponseError(self.name, f"unsupported crypto timeframe: {timeframe}")
        return datetime.now(UTC) - timedelta(
            seconds=seconds * max(limit, 1)
        )

    def get_current_price(self, symbol: str) -> float | None:
        payload = _get_json(
            self.name,
            f"{self.base_url}/Ticker",
            params={"pair": _kraken_pair(symbol)},
            timeout=15,
        )
        body = payload if isinstance(payload, dict) else None
        result = body.get("result") if body is not None else None
        if not isinstance(result, dict) or not result:
            raise ProviderResponseError(self.name, "Kraken returned an invalid ticker result")
        row = next(iter(result.values()))
        if not isinstance(row, dict) or not isinstance(row.get("c"), list) or not row["c"]:
            raise ProviderResponseError(self.name, "Kraken returned an invalid ticker row")
        return _candle_float(row["c"][0], self.name, "ticker price")

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        if quote_type.upper() != "CRYPTOCURRENCY":
            return {"total": 0, "quotes": []}
        payload = _get_json(self.name, f"{self.base_url}/AssetPairs", timeout=30)
        if not isinstance(payload, dict):
            raise ProviderResponseError(self.name, "Kraken returned an invalid asset-pairs JSON object")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ProviderResponseError(self.name, "Kraken returned an invalid asset-pairs result")
        if any(not isinstance(item, dict) for item in result.values()):
            raise ProviderResponseError(self.name, "Kraken returned a non-object asset-pair row")
        products = [
            item for item in result.values() if str(item.get("quote", "")).upper() in {"ZUSD", "USD"}
        ]
        page = products[offset : offset + 500]
        for item in page:
            base = str(item.get("base") or "").strip()
            pair_name = str(item.get("wsname") or item.get("altname") or "").strip()
            if not base or not pair_name:
                raise ProviderResponseError(self.name, "Kraken returned an incomplete asset-pair identity")
        return {
            "total": len(products),
            "quotes": [
                {
                    "symbol": f"{str(item['base']).replace('X', '')}-USD",
                    "longName": str(item.get("wsname") or item["altname"]),
                    "exchange": "Kraken",
                    "quoteType": "CRYPTOCURRENCY",
                    "status": "active",
                    "source_record": item,
                }
                for item in page
            ],
        }

    def supported_discovery_types(self) -> list[str]:
        return ["CRYPTOCURRENCY"]


def _coinbase_product(symbol: str) -> str:
    normalized = symbol.upper().replace("/", "-")
    return normalized if "-" in normalized else f"{normalized}-USD"


def _kraken_pair(symbol: str) -> str:
    base = symbol.upper().replace("/", "-").split("-", 1)[0]
    return f"{base}USD".replace("BTC", "XBT")
