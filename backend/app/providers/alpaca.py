"""
Alpaca Markets data provider.

Capabilities:
  - PriceHistoryProvider  : US equity + crypto OHLCV (all timeframes)
  - LatestPriceProvider   : current price via latest bar
  - EventProvider         : corporate actions (splits, dividends)
  - DiscoveryProvider     : US equity + crypto universe

Auth: ALPACA_API_KEY + ALPACA_SECRET_KEY (free account sufficient).
Data feed: ALPACA_DATA_FEED = "iex" (free) | "sip" (paid consolidated).

Rate limits (free IEX feed): 200 req/min on data endpoints.
Assets endpoint: single call returns all tradeable symbols (~9 000 equities).
"""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx

from app.config import settings
from app.models.instrument_event import EventTimeHint, InstrumentEventType
from app.models.ohlcv import OHLCVBar, Timeframe
from app.providers.base import InstrumentEventRecord

logger = logging.getLogger(__name__)

_DATA_BASE = "https://data.alpaca.markets/v2"
_BROKER_BASE = "https://api.alpaca.markets/v2"
_PAGE_SIZE = 250

_TF_MAP: dict[Timeframe, str] = {
    Timeframe.M1: "1Min",
    Timeframe.M5: "5Min",
    Timeframe.M15: "15Min",
    Timeframe.M30: "30Min",
    Timeframe.H1: "1Hour",
    Timeframe.H2: "2Hour",
    Timeframe.H4: "4Hour",
    Timeframe.H12: "12Hour",
    Timeframe.D1: "1Day",
    Timeframe.W1: "1Week",
    Timeframe.MN: "1Month",
}

_TF_SECONDS: dict[Timeframe, int] = {
    Timeframe.M1: 60, Timeframe.M5: 300, Timeframe.M15: 900,
    Timeframe.M30: 1800, Timeframe.H1: 3600, Timeframe.H2: 7200,
    Timeframe.H4: 14400, Timeframe.H12: 43200, Timeframe.D1: 86400,
    Timeframe.W1: 604800, Timeframe.MN: 2592000,
}

# Module-level asset cache: keyed by asset_class string
_asset_cache: dict[str, list[dict]] = {}
_asset_cache_ts: float = 0.0
_ASSET_CACHE_TTL = 3600 * 4  # 4 hours



class AlpacaProvider:
    name = "alpaca"
    base_url = "https://data.alpaca.markets"
    description = (
        "Alpaca Markets free data API — US equity + crypto OHLCV, "
        "corporate actions (splits/dividends), universe discovery"
    )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": settings.ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": settings.ALPACA_SECRET_KEY,
        }

    def _ok(self) -> bool:
        has_creds = bool(settings.ALPACA_API_KEY and settings.ALPACA_SECRET_KEY)
        if not has_creds:
            logger.warning(
                "alpaca: ALPACA_API_KEY / ALPACA_SECRET_KEY are not set — "
                "skipping this call and falling back to next provider. "
                "Set these in .env.dev to enable Alpaca."
            )
        return has_creds

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
        if not self._ok():
            return []
        tf_str = _TF_MAP.get(timeframe)
        if tf_str is None:
            return []

        is_crypto = _is_crypto(symbol)
        alpaca_sym = _to_alpaca_crypto(symbol) if is_crypto else symbol
        url = f"{_DATA_BASE}/{'crypto' if is_crypto else 'stocks'}/bars"
        params: dict[str, Any] = {
            "symbols": alpaca_sym,
            "timeframe": tf_str,
            "start": _fmt_dt(start),
            "end": _fmt_dt(end),
            "limit": 1000,
            "adjustment": "all" if adjusted else "raw",
        }
        if not is_crypto:
            params["feed"] = settings.ALPACA_DATA_FEED

        bars: list[OHLCVBar] = []
        page_token: str | None = None

        while True:
            if page_token:
                params["page_token"] = page_token
            try:
                r = httpx.get(url, params=params, headers=self._headers(), timeout=30)
                r.raise_for_status()
                data = r.json()
            except Exception as exc:
                logger.warning("alpaca fetch_ohlcv %s: %s", symbol, exc)
                break

            for b in data.get("bars", {}).get(alpaca_sym, []):
                try:
                    ts = datetime.fromisoformat(b["t"].replace("Z", "+00:00"))
                    bars.append(OHLCVBar(
                        instrument_id=instrument_id,
                        data_source_id=data_source_id,
                        timeframe=timeframe,
                        ts=ts,
                        open=b["o"],
                        high=b["h"],
                        low=b["l"],
                        close=b["c"],
                        volume=b.get("v"),
                        vwap=b.get("vw"),
                        is_adjusted=adjusted,
                    ))
                except (KeyError, ValueError):
                    continue

            page_token = data.get("next_page_token")
            if not page_token:
                break

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
            symbol, timeframe, start, datetime.now(UTC),
            adjusted=adjusted, instrument_id=instrument_id, data_source_id=data_source_id,
        )
        return bars[-limit:]

    def latest_window_start(self, timeframe: Timeframe, limit: int) -> datetime:
        seconds = _TF_SECONDS.get(timeframe, 86400)
        lookback = timedelta(seconds=seconds * limit * 1.4 + 86400)
        return datetime.now(UTC) - lookback

    # ── Latest Price ──────────────────────────────────────────────────────────

    def get_current_price(self, symbol: str) -> float | None:
        if not self._ok():
            return None
        is_crypto = _is_crypto(symbol)
        alpaca_sym = _to_alpaca_crypto(symbol) if is_crypto else symbol
        url = f"{_DATA_BASE}/{'crypto' if is_crypto else 'stocks'}/bars/latest"
        params: dict[str, Any] = {"symbols": alpaca_sym}
        if not is_crypto:
            params["feed"] = settings.ALPACA_DATA_FEED
        try:
            r = httpx.get(url, params=params, headers=self._headers(), timeout=10)
            r.raise_for_status()
            bar = r.json().get("bars", {}).get(alpaca_sym)
            return float(bar["c"]) if bar else None
        except Exception as exc:
            logger.debug("alpaca get_current_price %s: %s", symbol, exc)
            return None

    # ── Corporate Actions (Events) ────────────────────────────────────────────

    def fetch_instrument_events(self, symbol: str) -> list[InstrumentEventRecord]:
        if not self._ok():
            return []
        now = datetime.now(UTC)
        since = (now - timedelta(days=365 * 10)).strftime("%Y-%m-%d")
        until = (now + timedelta(days=90)).strftime("%Y-%m-%d")
        try:
            r = httpx.get(
                f"{_DATA_BASE}/corporate_actions/announcements",
                params={
                    "ca_types": "forward_split,reverse_split,cash_dividend",
                    "symbol": symbol,
                    "since": since,
                    "until": until,
                },
                headers=self._headers(),
                timeout=30,
            )
            r.raise_for_status()
            raw = r.json()
        except Exception as exc:
            logger.warning("alpaca fetch_instrument_events %s: %s", symbol, exc)
            return []

        ca = raw.get("corporate_actions") or raw
        events: list[InstrumentEventRecord] = []
        fetched = now

        for s in ca.get("forward_splits") or []:
            dt = _parse_date(s.get("ex_date") or s.get("effective_date") or "")
            if dt is None:
                continue
            events.append(InstrumentEventRecord(
                event_type=InstrumentEventType.SPLIT,
                event_time=dt,
                time_hint=EventTimeHint.UNKNOWN,
                title=f"Forward Split {symbol}",
                source_event_key=f"alpaca_fwd_split_{s.get('id', dt.date())}",
                fetched_at=fetched,
                split_ratio=_safe_ratio(s.get("new_rate"), s.get("old_rate")),
                raw_payload=str(s),
            ))

        for s in ca.get("reverse_splits") or []:
            dt = _parse_date(s.get("ex_date") or s.get("effective_date") or "")
            if dt is None:
                continue
            events.append(InstrumentEventRecord(
                event_type=InstrumentEventType.SPLIT,
                event_time=dt,
                time_hint=EventTimeHint.UNKNOWN,
                title=f"Reverse Split {symbol}",
                source_event_key=f"alpaca_rev_split_{s.get('id', dt.date())}",
                fetched_at=fetched,
                split_ratio=_safe_ratio(s.get("new_rate"), s.get("old_rate")),
                raw_payload=str(s),
            ))

        for d in ca.get("cash_dividends") or []:
            ex_dt = _parse_date(d.get("ex_date") or "")
            pay_dt = _parse_date(d.get("pay_date") or "")
            amount = _safe_decimal(d.get("rate"))
            raw = str(d)
            if ex_dt:
                events.append(InstrumentEventRecord(
                    event_type=InstrumentEventType.EX_DIVIDEND,
                    event_time=ex_dt,
                    time_hint=EventTimeHint.UNKNOWN,
                    title=f"Ex-Dividend {symbol}",
                    source_event_key=f"alpaca_exdiv_{d.get('id', ex_dt.date())}",
                    fetched_at=fetched,
                    dividend_amount=amount,
                    raw_payload=raw,
                ))
            if pay_dt:
                events.append(InstrumentEventRecord(
                    event_type=InstrumentEventType.DIVIDEND,
                    event_time=pay_dt,
                    time_hint=EventTimeHint.UNKNOWN,
                    title=f"Dividend {symbol}",
                    source_event_key=f"alpaca_div_{d.get('id', pay_dt.date())}",
                    fetched_at=fetched,
                    dividend_amount=amount,
                    raw_payload=raw,
                ))

        return events

    # ── Universe Discovery ────────────────────────────────────────────────────

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        if not self._ok():
            return {"total": 0, "quotes": []}
        asset_class = {"EQUITY": "us_equity", "CRYPTOCURRENCY": "crypto"}.get(quote_type)
        if asset_class is None:
            return {"total": 0, "quotes": []}

        assets = _cached_assets(self._headers(), asset_class)
        page = assets[offset: offset + _PAGE_SIZE]
        return {
            "total": len(assets),
            "quotes": [_asset_to_quote(a, quote_type) for a in page],
        }

    def supported_discovery_types(self) -> list[str]:
        return ["EQUITY", "CRYPTOCURRENCY"]


# ── Module-level helpers ──────────────────────────────────────────────────────

def _is_crypto(symbol: str) -> bool:
    return "/" in symbol or (
        "-" in symbol
        and symbol.split("-", 1)[1].upper() in ("USD", "USDT", "BTC", "ETH")
    )


def _to_alpaca_crypto(symbol: str) -> str:
    """BTC-USD → BTC/USD (Alpaca crypto format)."""
    return symbol.replace("-", "/", 1) if "-" in symbol else symbol


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_date(s: str) -> datetime | None:
    if not s:
        return None
    try:
        if "T" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None


def _safe_decimal(v: Any) -> Decimal | None:
    try:
        return Decimal(str(v)) if v is not None else None
    except Exception:
        return None


def _safe_ratio(new_rate: Any, old_rate: Any) -> Decimal | None:
    try:
        if new_rate is not None and old_rate is not None:
            return Decimal(str(new_rate)) / Decimal(str(old_rate))
    except Exception:
        pass
    return None


def _cached_assets(headers: dict, asset_class: str) -> list[dict]:
    global _asset_cache, _asset_cache_ts
    now = time.monotonic()
    if asset_class in _asset_cache and (now - _asset_cache_ts) < _ASSET_CACHE_TTL:
        return _asset_cache[asset_class]
    try:
        r = httpx.get(
            f"{_BROKER_BASE}/assets",
            params={"status": "active", "asset_class": asset_class},
            headers=headers,
            timeout=30,
        )
        r.raise_for_status()
        assets = [a for a in r.json() if a.get("tradable")]
        _asset_cache[asset_class] = assets
        _asset_cache_ts = now
        return assets
    except Exception as exc:
        logger.warning("alpaca _cached_assets %s: %s", asset_class, exc)
        return _asset_cache.get(asset_class, [])


def _asset_to_quote(asset: dict, quote_type: str) -> dict[str, Any]:
    symbol = asset.get("symbol", "")
    if quote_type == "CRYPTOCURRENCY" and "/" in symbol:
        symbol = symbol.replace("/", "-", 1)
    return {
        "symbol": symbol,
        "shortName": asset.get("name", ""),
        "displayName": asset.get("name", ""),
        "quoteType": quote_type,
        "exchange": asset.get("exchange", ""),
        "currency": "USD",
    }
