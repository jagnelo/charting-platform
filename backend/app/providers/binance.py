"""
Binance public market data provider.

Capabilities:
  - PriceHistoryProvider : crypto OHLCV (all timeframes)
  - LatestPriceProvider  : current price via ticker endpoint
  - DiscoveryProvider    : crypto universe (USDT-quoted pairs)

Auth: None required — all endpoints used here are public.
Rate limits: the current Spot REST documentation exposes a 6,000
request-weight/minute IP ceiling. The adapter records the exact documented
weights for single-symbol price (2) and exchange-info discovery (20).
Historical OHLCV calculates its potentially multi-page request count before
execution so the runtime can reserve the full documented weight; it must never
be charged as one request by default.

Symbol convention:
  Platform canonical : BTC-USD
  Binance internal   : BTCUSDT
Conversion is handled transparently in _to_binance / _from_binance.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from math import isfinite
from typing import Any

import httpx

from app.models.ohlcv import OHLCVBar, Timeframe
from app.providers.errors import (
    ProviderRateLimitError,
    ProviderResponseError,
    provider_response_headers,
    raise_for_provider_error_envelope,
    redact_provider_message,
)
from app.providers.telemetry import observe_response

logger = logging.getLogger(__name__)

_BASE = "https://api.binance.com/api/v3"
_PAGE_SIZE = 250
_ASSET_CACHE_TTL = 3600 * 6  # 6 hours

_TF_MAP: dict[Timeframe, str] = {
    Timeframe.M1: "1m",
    Timeframe.M5: "5m",
    Timeframe.M15: "15m",
    Timeframe.M30: "30m",
    Timeframe.H1: "1h",
    Timeframe.H2: "2h",
    Timeframe.H4: "4h",
    Timeframe.H12: "12h",
    Timeframe.D1: "1d",
    Timeframe.W1: "1w",
    Timeframe.MN: "1M",
}

_TF_SECONDS: dict[Timeframe, int] = {
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
    Timeframe.MN: 2592000,
}

_KLINES_LIMIT = 1000
_KLINES_WEIGHT = 2

# Module-level universe cache
_usdt_pairs: list[dict] = []
_usdt_pairs_ts: float = 0.0


class BinanceProvider:
    name = "binance"
    base_url = "https://api.binance.com"
    description = (
        "Binance public API — crypto OHLCV (all timeframes), "
        "current prices, and USDT-quoted universe discovery"
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
        if adjusted:
            raise ProviderResponseError(
                self.name,
                "Binance exchange candles are raw; request adjusted=False",
            )
        tf_str = _TF_MAP.get(timeframe)
        binance_sym = _to_binance(symbol)
        if tf_str is None or binance_sym is None:
            return []

        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        bars: list[OHLCVBar] = []
        previous_last_open_ms: int | None = None

        while start_ms < end_ms:
            try:
                r = httpx.get(
                    f"{_BASE}/klines",
                    params={
                        "symbol": binance_sym,
                        "interval": tf_str,
                        "startTime": start_ms,
                        "endTime": end_ms,
                        "limit": 1000,
                    },
                    timeout=30,
                )
                observe_response(r)
                r.raise_for_status()
                klines = r.json()
                raise_for_provider_error_envelope(
                    "binance", klines, r.status_code, headers=provider_response_headers(r)
                )
            except httpx.HTTPStatusError as exc:
                if r.status_code in {418, 429}:
                    raise ProviderRateLimitError(
                        self.name,
                        f"Binance request rejected for capacity (HTTP {r.status_code})",
                        status_code=r.status_code,
                        headers=provider_response_headers(r),
                    ) from exc
                raise ProviderResponseError(
                    self.name,
                    f"Binance request failed with HTTP {r.status_code}",
                    status_code=r.status_code,
                ) from exc
            except httpx.RequestError as exc:
                logger.warning(
                    "binance fetch_ohlcv %s: %s", symbol, redact_provider_message(exc)[:1000]
                )
                raise ProviderResponseError("binance", f"transport failure: {exc}") from exc
            except (TypeError, ValueError, IndexError, KeyError, OverflowError, OSError) as exc:
                raise ProviderResponseError("binance", f"malformed klines response: {exc}") from exc

            if not isinstance(klines, list):
                raise ProviderResponseError("binance", "malformed klines response: expected a list")

            if not klines:
                break

            parsed_rows = _parse_kline_rows(klines)
            if not parsed_rows:
                raise ProviderResponseError("binance", "malformed klines response: empty page")
            if previous_last_open_ms is not None and parsed_rows[0][0] <= previous_last_open_ms:
                raise ProviderResponseError(
                    "binance", "malformed klines response: pagination did not advance"
                )
            for open_ms, open_price, high, low, close, volume in parsed_rows:
                bars.append(
                    OHLCVBar(
                        instrument_id=instrument_id,
                        data_source_id=data_source_id,
                        timeframe=timeframe,
                        ts=_open_time_datetime(open_ms),
                        open=open_price,
                        high=high,
                        low=low,
                        close=close,
                        volume=volume,
                        vwap=None,
                        is_adjusted=False,
                        adjustment_basis="raw",
                        adjustment_version="provider-native",
                        provenance={
                            "provider": self.name,
                            "endpoint": "/api/v3/klines",
                            "provider_symbol": binance_sym,
                            "interval": tf_str,
                            "provider_payload": {
                                "open_time": open_ms,
                                "open": open_price,
                                "high": high,
                                "low": low,
                                "close": close,
                                "volume": volume,
                            },
                        },
                    )
                )

            # Advance cursor past the last returned open_time
            last_open_ms = parsed_rows[-1][0]
            if last_open_ms <= start_ms:
                if last_open_ms < start_ms or len(parsed_rows) > 1:
                    raise ProviderResponseError(
                        "binance", "malformed klines response: non-progressing pagination"
                    )
                break
            previous_last_open_ms = last_open_ms
            start_ms = last_open_ms + 1

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
        seconds = _TF_SECONDS.get(timeframe, 86400)
        lookback = timedelta(seconds=seconds * limit * 1.4 + 86400)
        return datetime.now(UTC) - lookback

    # ── Latest Price ──────────────────────────────────────────────────────────

    def get_current_price(self, symbol: str) -> float | None:
        binance_sym = _to_binance(symbol)
        if binance_sym is None:
            return None
        try:
            r = httpx.get(
                f"{_BASE}/ticker/price",
                params={"symbol": binance_sym},
                timeout=10,
            )
            observe_response(r)
            r.raise_for_status()
            payload = r.json()
            raise_for_provider_error_envelope(
                "binance", payload, r.status_code, headers=provider_response_headers(r)
            )
        except httpx.HTTPStatusError as exc:
            if r.status_code in {418, 429}:
                raise ProviderRateLimitError(
                    self.name,
                    f"Binance request rejected for capacity (HTTP {r.status_code})",
                    status_code=r.status_code,
                    headers=provider_response_headers(r),
                ) from exc
            raise ProviderResponseError(
                self.name,
                f"Binance request failed with HTTP {r.status_code}",
                status_code=r.status_code,
            ) from exc
        except httpx.RequestError as exc:
            logger.debug(
                "binance get_current_price %s: %s", symbol, redact_provider_message(exc)[:1000]
            )
            raise ProviderResponseError("binance", f"transport failure: {exc}") from exc
        except (TypeError, ValueError, KeyError, OverflowError) as exc:
            raise ProviderResponseError("binance", f"malformed ticker response: {exc}") from exc
        if not isinstance(payload, dict):
            raise ProviderResponseError("binance", "malformed ticker response: expected an object")
        try:
            return _finite_float(payload["price"], "ticker price")
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ProviderResponseError("binance", f"malformed ticker response: {exc}") from exc

    # ── Universe Discovery ────────────────────────────────────────────────────

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        if quote_type != "CRYPTOCURRENCY":
            return {"total": 0, "quotes": []}

        pairs = _cached_usdt_pairs()
        page = pairs[offset : offset + _PAGE_SIZE]
        return {
            "total": len(pairs),
            "quotes": [_pair_to_quote(p) for p in page],
        }

    def supported_discovery_types(self) -> list[str]:
        return ["CRYPTOCURRENCY"]


def estimate_ohlcv_request_weight(
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
) -> int | None:
    """Return the exact conservative `/klines` weight before execution.

    Binance permits at most 1,000 candles per `/klines` request and the
    documented endpoint weight for this adapter is two per request.  The
    estimate intentionally rounds up: a short final page is still a request,
    and a provider returning fewer rows can never make the reservation unsafe.
    """
    seconds = _TF_SECONDS.get(timeframe)
    if seconds is None or end <= start:
        return None
    candles = max(1, int((end - start).total_seconds() + seconds - 1) // seconds)
    requests = (candles + _KLINES_LIMIT - 1) // _KLINES_LIMIT
    return requests * _KLINES_WEIGHT


def estimate_latest_ohlcv_request_weight(timeframe: Timeframe, limit: int) -> int | None:
    seconds = _TF_SECONDS.get(timeframe)
    if limit <= 0 or seconds is None:
        return None
    # ``fetch_latest_ohlcv`` deliberately asks for a 1.4x lookback plus one
    # day, then trims to ``limit`` bars. Reserve against that actual request
    # range (with one extra candle for the clock advancing between estimation
    # and invocation), not merely against the number returned to the caller.
    requested_candles = int((int(limit) * 1.4) + (86400 / seconds)) + 1
    return max(1, (requested_candles + _KLINES_LIMIT - 1) // _KLINES_LIMIT) * _KLINES_WEIGHT


# ── Module helpers ────────────────────────────────────────────────────────────


def _to_binance(symbol: str) -> str | None:
    """BTC-USD → BTCUSDT; returns None if not a USD crypto pair."""
    if isinstance(symbol, str) and "-" in symbol:
        base, quote = symbol.split("-", 1)
        if quote.upper() == "USD":
            return base.upper() + "USDT"
    return None


def _from_binance(binance_sym: str) -> str | None:
    """BTCUSDT → BTC-USD; returns None if not a USDT pair."""
    if isinstance(binance_sym, str) and binance_sym.endswith("USDT"):
        return binance_sym[:-4] + "-USD"
    return None


def _cached_usdt_pairs() -> list[dict]:
    global _usdt_pairs, _usdt_pairs_ts
    now = time.monotonic()
    if _usdt_pairs and (now - _usdt_pairs_ts) < _ASSET_CACHE_TTL:
        return _usdt_pairs
    try:
        r = httpx.get(f"{_BASE}/exchangeInfo", timeout=30)
        observe_response(r)
        r.raise_for_status()
        payload = r.json()
        raise_for_provider_error_envelope(
            "binance", payload, r.status_code, headers=provider_response_headers(r)
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
            raise ProviderResponseError(
                "binance", "malformed exchange-info response: expected symbols list"
            )
        symbols = payload["symbols"]
        if any(not isinstance(symbol, dict) for symbol in symbols):
            raise ProviderResponseError(
                "binance", "malformed exchange-info response: invalid symbol row"
            )
        for symbol in symbols:
            for field in ("symbol", "baseAsset", "quoteAsset", "status"):
                if not isinstance(symbol.get(field), str) or not symbol[field].strip():
                    raise ProviderResponseError(
                        "binance", f"malformed exchange-info response: invalid {field}"
                    )
            if not isinstance(symbol.get("isSpotTradingAllowed"), bool):
                raise ProviderResponseError(
                    "binance", "malformed exchange-info response: invalid spot-trading flag"
                )
        pairs = [
            s
            for s in symbols
            if isinstance(s, dict)
            and s.get("quoteAsset") == "USDT"
            and s.get("status") == "TRADING"
            and s.get("isSpotTradingAllowed")
        ]
        _usdt_pairs = pairs
        _usdt_pairs_ts = now
        return pairs
    except httpx.HTTPStatusError as exc:
        if r.status_code in {418, 429}:
            raise ProviderRateLimitError(
                "binance",
                f"Binance request rejected for capacity (HTTP {r.status_code})",
                status_code=r.status_code,
                headers=provider_response_headers(r),
            ) from exc
        raise ProviderResponseError(
            "binance",
            f"Binance request failed with HTTP {r.status_code}",
            status_code=r.status_code,
        ) from exc
    except httpx.RequestError as exc:
        logger.warning("binance _cached_usdt_pairs: %s", redact_provider_message(exc)[:1000])
        raise ProviderResponseError("binance", f"transport failure: {exc}") from exc
    except (TypeError, ValueError, KeyError) as exc:
        raise ProviderResponseError("binance", f"malformed exchange-info response: {exc}") from exc


def _pair_to_quote(pair: dict) -> dict[str, Any]:
    base = pair.get("baseAsset", "")
    return {
        "symbol": f"{base}-USD",
        "shortName": f"{base} / USD",
        "displayName": pair.get("symbol", ""),
        "quoteType": "CRYPTOCURRENCY",
        "exchange": "Binance",
        "currency": "USD",
    }


def _finite_float(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} is boolean")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} is not numeric") from exc
    if not isfinite(result):
        raise ValueError(f"{field} is non-finite")
    return result


def _open_time_ms(value: Any) -> int:
    numeric = _finite_float(value, "kline open time")
    if not numeric.is_integer():
        raise ValueError("kline open time is not an integer")
    result = int(numeric)
    if result < 0:
        raise ValueError("kline open time is negative")
    return result


def _open_time_datetime(open_ms: int) -> datetime:
    try:
        return datetime.fromtimestamp(open_ms / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise ProviderResponseError("binance", "malformed klines row: invalid open time") from exc


def _parse_kline_rows(
    klines: list[Any],
) -> list[tuple[int, float, float, float, float, float]]:
    parsed: list[tuple[int, float, float, float, float, float]] = []
    previous_open_ms: int | None = None
    for row in klines:
        if not isinstance(row, list | tuple) or len(row) < 6:
            raise ProviderResponseError("binance", "malformed klines row: expected six values")
        try:
            open_ms = _open_time_ms(row[0])
            values = tuple(
                _finite_float(row[index], f"kline field {index}") for index in range(1, 6)
            )
        except (TypeError, ValueError, OverflowError) as exc:
            raise ProviderResponseError("binance", f"malformed klines row: {exc}") from exc
        if previous_open_ms is not None and open_ms <= previous_open_ms:
            raise ProviderResponseError(
                "binance", "malformed klines response: rows are not increasing"
            )
        parsed.append((open_ms, *values))
        previous_open_ms = open_ms
    return parsed
