"""Keyless public crypto adapters for Coinbase Exchange and Kraken."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.models.ohlcv import OHLCVBar, Timeframe

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


class CoinbaseProvider:
    name = "coinbase"
    base_url = "https://api.exchange.coinbase.com"
    description = "Coinbase Exchange public crypto candles, ticker, and products"

    def fetch_ohlcv(self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime, *, adjusted: bool = True, instrument_id: int | None = None, data_source_id: int | None = None) -> list[OHLCVBar]:
        seconds = _TF_SECONDS.get(timeframe)
        if seconds is None:
            return []
        product = _coinbase_product(symbol)
        # Coinbase caps each response at 300 candles. One request per call is
        # intentional; callers must page through the queue and remain within
        # the documented 10 req/sec/IP budget.
        limit_end = min(end, start + timedelta(seconds=seconds * 300))
        response = httpx.get(
            f"{self.base_url}/products/{product}/candles",
            params={"granularity": seconds, "start": start.isoformat(), "end": limit_end.isoformat()},
            timeout=30,
        )
        response.raise_for_status()
        rows = response.json()
        bars: list[OHLCVBar] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, list) or len(row) < 6:
                continue
            ts = datetime.fromtimestamp(float(row[0]), tz=UTC)
            bars.append(OHLCVBar(instrument_id=instrument_id, data_source_id=data_source_id, timeframe=timeframe, ts=ts, low=float(row[1]), high=float(row[2]), open=float(row[3]), close=float(row[4]), volume=float(row[5]), is_adjusted=False))
        return sorted((bar for bar in bars if start <= bar.ts < end), key=lambda bar: bar.ts)

    def fetch_latest_ohlcv(self, symbol: str, timeframe: Timeframe, limit: int, *, adjusted: bool = True, instrument_id: int | None = None, data_source_id: int | None = None) -> list[OHLCVBar]:
        seconds = _TF_SECONDS.get(timeframe, 86400)
        return self.fetch_ohlcv(symbol, timeframe, datetime.now(UTC) - timedelta(seconds=seconds * min(limit, 300)), datetime.now(UTC), adjusted=adjusted, instrument_id=instrument_id, data_source_id=data_source_id)[-limit:]

    def latest_window_start(self, timeframe: Timeframe, limit: int) -> datetime:
        return datetime.now(UTC) - timedelta(seconds=_TF_SECONDS.get(timeframe, 86400) * min(limit, 300))

    def get_current_price(self, symbol: str) -> float | None:
        response = httpx.get(f"{self.base_url}/products/{_coinbase_product(symbol)}/ticker", timeout=15)
        response.raise_for_status()
        payload = response.json()
        return float(payload["price"]) if isinstance(payload, dict) and payload.get("price") else None

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        if quote_type.upper() != "CRYPTOCURRENCY":
            return {"total": 0, "quotes": []}
        response = httpx.get(f"{self.base_url}/products", timeout=30)
        response.raise_for_status()
        products = [item for item in response.json() if isinstance(item, dict) and item.get("quote_currency") == "USD" and item.get("status") == "online"]
        page = products[offset : offset + 500]
        return {"total": len(products), "quotes": [{"symbol": f"{item.get('base_currency')}-USD", "longName": item.get("display_name"), "exchange": "Coinbase", "quoteType": "CRYPTOCURRENCY", "status": "active", "source_record": item} for item in page]}

    def supported_discovery_types(self) -> list[str]:
        return ["CRYPTOCURRENCY"]


class KrakenProvider:
    name = "kraken"
    base_url = "https://api.kraken.com/0/public"
    description = "Kraken public crypto OHLC, ticker, and asset-pair metadata"

    def fetch_ohlcv(self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime, *, adjusted: bool = True, instrument_id: int | None = None, data_source_id: int | None = None) -> list[OHLCVBar]:
        interval = max(1, _TF_SECONDS.get(timeframe, 86400) // 60)
        response = httpx.get(f"{self.base_url}/OHLC", params={"pair": _kraken_pair(symbol), "interval": interval, "since": int(start.timestamp())}, timeout=30)
        response.raise_for_status()
        payload = response.json()
        result = payload.get("result", {}) if isinstance(payload, dict) else {}
        rows = next((value for key, value in result.items() if key != "last" and isinstance(value, list)), [])
        bars: list[OHLCVBar] = []
        for row in rows:
            if not isinstance(row, list) or len(row) < 7:
                continue
            ts = datetime.fromtimestamp(float(row[0]), tz=UTC)
            if not start <= ts < end:
                continue
            bars.append(OHLCVBar(instrument_id=instrument_id, data_source_id=data_source_id, timeframe=timeframe, ts=ts, open=float(row[1]), high=float(row[2]), low=float(row[3]), close=float(row[4]), volume=float(row[6]), is_adjusted=False))
        return bars

    def fetch_latest_ohlcv(self, symbol: str, timeframe: Timeframe, limit: int, *, adjusted: bool = True, instrument_id: int | None = None, data_source_id: int | None = None) -> list[OHLCVBar]:
        end = datetime.now(UTC)
        return self.fetch_ohlcv(symbol, timeframe, end - timedelta(seconds=_TF_SECONDS.get(timeframe, 86400) * min(limit, 720)), end, adjusted=adjusted, instrument_id=instrument_id, data_source_id=data_source_id)[-limit:]

    def latest_window_start(self, timeframe: Timeframe, limit: int) -> datetime:
        return datetime.now(UTC) - timedelta(seconds=_TF_SECONDS.get(timeframe, 86400) * min(limit, 720))

    def get_current_price(self, symbol: str) -> float | None:
        response = httpx.get(f"{self.base_url}/Ticker", params={"pair": _kraken_pair(symbol)}, timeout=15)
        response.raise_for_status()
        result = response.json().get("result", {})
        row = next(iter(result.values()), {})
        return float(row["c"][0]) if isinstance(row, dict) and row.get("c") else None

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        if quote_type.upper() != "CRYPTOCURRENCY":
            return {"total": 0, "quotes": []}
        response = httpx.get(f"{self.base_url}/AssetPairs", timeout=30)
        response.raise_for_status()
        result = response.json().get("result", {})
        products = [item for item in result.values() if isinstance(item, dict) and str(item.get("quote", "")).upper() in {"ZUSD", "USD"}]
        page = products[offset : offset + 500]
        return {"total": len(products), "quotes": [{"symbol": f"{item.get('base', '').replace('X', '')}-USD", "longName": item.get("wsname"), "exchange": "Kraken", "quoteType": "CRYPTOCURRENCY", "status": "active", "source_record": item} for item in page]}

    def supported_discovery_types(self) -> list[str]:
        return ["CRYPTOCURRENCY"]


def _coinbase_product(symbol: str) -> str:
    normalized = symbol.upper().replace("/", "-")
    return normalized if "-" in normalized else f"{normalized}-USD"


def _kraken_pair(symbol: str) -> str:
    base = symbol.upper().replace("/", "-").split("-", 1)[0]
    return f"{base}USD".replace("BTC", "XBT")
