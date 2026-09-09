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
from typing import Any

import httpx

from app.models.ohlcv import OHLCVBar, Timeframe
from app.providers.errors import raise_for_provider_error_envelope
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
        tf_str = _TF_MAP.get(timeframe)
        binance_sym = _to_binance(symbol)
        if tf_str is None or binance_sym is None:
            return []

        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        bars: list[OHLCVBar] = []

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
                raise_for_provider_error_envelope("binance", klines, r.status_code)
            except httpx.HTTPStatusError:
                raise
            except httpx.RequestError as exc:
                logger.warning("binance fetch_ohlcv %s: %s", symbol, exc)
                raise

            if not klines:
                break

            for k in klines:
                try:
                    # klines: [open_time, open, high, low, close, volume, close_time, ...]
                    ts = datetime.fromtimestamp(k[0] / 1000, tz=UTC)
                    bars.append(
                        OHLCVBar(
                            instrument_id=instrument_id,
                            data_source_id=data_source_id,
                            timeframe=timeframe,
                            ts=ts,
                            open=float(k[1]),
                            high=float(k[2]),
                            low=float(k[3]),
                            close=float(k[4]),
                            volume=float(k[5]) if k[5] else None,
                            vwap=None,
                            is_adjusted=True,
                        )
                    )
                except (IndexError, ValueError):
                    continue

            # Advance cursor past the last returned open_time
            last_open_ms = klines[-1][0]
            if last_open_ms <= start_ms:
                break
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
            raise_for_provider_error_envelope("binance", payload, r.status_code)
            return float(payload["price"])
        except httpx.HTTPStatusError:
            raise
        except httpx.RequestError as exc:
            logger.debug("binance get_current_price %s: %s", symbol, exc)
            raise

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
    if "-" in symbol:
        base, quote = symbol.split("-", 1)
        if quote.upper() == "USD":
            return base.upper() + "USDT"
    return None


def _from_binance(binance_sym: str) -> str | None:
    """BTCUSDT → BTC-USD; returns None if not a USDT pair."""
    if binance_sym.endswith("USDT"):
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
        raise_for_provider_error_envelope("binance", payload, r.status_code)
        symbols = payload.get("symbols", [])
        pairs = [
            s
            for s in symbols
            if s.get("quoteAsset") == "USDT"
            and s.get("status") == "TRADING"
            and s.get("isSpotTradingAllowed")
        ]
        _usdt_pairs = pairs
        _usdt_pairs_ts = now
        return pairs
    except httpx.HTTPStatusError:
        raise
    except httpx.RequestError as exc:
        logger.warning("binance _cached_usdt_pairs: %s", exc)
        raise


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
