"""Concrete, opt-in adapters for low-cost market-data APIs.

The providers in this module deliberately implement only documented REST
surfaces and return an empty result when their credential is absent.  They are
registered so administrators can inspect their capabilities, but they are not
part of the default chain and have no entitlement seed until terms/quotas have
been reviewed.  This keeps adding an adapter from silently changing routing.

All adapters normalize provider-specific symbols and response shapes into the
platform's provider contracts.  Raw response fields are retained in the bar's
provenance where the API exposes them; callers can therefore reconcile a
provider adjustment policy before promoting a series to canonical data.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx

from app.config import settings
from app.models.instrument_event import EventTimeHint, InstrumentEventType
from app.models.ohlcv import OHLCVBar, Timeframe
from app.providers.base import (
    InstrumentEventRecord,
    InstrumentProfile,
    ListingRecord,
    ProviderSearchResult,
)
from app.providers.errors import ProviderNotConfiguredError

logger = logging.getLogger(__name__)


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


def _number(value: Any) -> float | None:
    try:
        if value in (None, "", "null", "None", "-"):
            return None
        number = float(value)
        return number if number == number else None
    except (TypeError, ValueError):
        return None


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _timestamp(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, int | float):
        try:
            parsed = datetime.fromtimestamp(value, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
                try:
                    parsed = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            else:
                return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _bounded_datetime(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class _RESTProvider:
    """Small shared REST/normalisation layer used by the optional adapters."""

    key_setting: str = ""
    auth_mode: str = "query"  # query, header, or none
    key_param: str = "apikey"
    key_header: str = "Authorization"

    def _key(self) -> str:
        return str(getattr(settings, self.key_setting, "") or "").strip()

    def _auth_headers(self) -> dict[str, str]:
        if self.auth_mode == "header" and self._key():
            value = self._key()
            if self.key_header.lower() == "authorization" and not value.lower().startswith(
                "bearer "
            ):
                value = f"Token {value}"
            return {self.key_header: value}
        return {}

    def _auth_params(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        result = dict(params or {})
        if self.auth_mode == "query" and self._key():
            result[self.key_param] = self._key()
        return result

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if self.key_setting and not self._key():
            raise ProviderNotConfiguredError(
                f"{self.name} requires {self.key_setting}; configure it before routing"
            )
        response = httpx.get(
            f"{self.base_url.rstrip('/')}/{path.lstrip('/')}",
            params=self._auth_params(params),
            headers=self._auth_headers(),
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _rows(payload: Any, *keys: str) -> list[dict[str, Any]]:
        value = payload
        if isinstance(payload, dict):
            for key in keys:
                candidate = payload.get(key)
                if isinstance(candidate, list):
                    value = candidate
                    break
            else:
                # A number of APIs wrap rows under a ``data`` object.
                value = payload.get("data", payload.get("results", []))
        if not isinstance(value, list):
            return []
        return [row for row in value if isinstance(row, dict)]

    @staticmethod
    def _bar(
        row: dict[str, Any],
        timeframe: Timeframe,
        *,
        instrument_id: int | None,
        data_source_id: int | None,
        timestamp_keys: tuple[str, ...] = ("timestamp", "datetime", "date", "t"),
    ) -> OHLCVBar | None:
        ts = next(
            (_timestamp(row.get(key)) for key in timestamp_keys if row.get(key) is not None), None
        )
        values = {
            "open": next(
                (
                    _number(row.get(key))
                    for key in ("open", "o", "1. open")
                    if row.get(key) is not None
                ),
                None,
            ),
            "high": next(
                (
                    _number(row.get(key))
                    for key in ("high", "h", "2. high")
                    if row.get(key) is not None
                ),
                None,
            ),
            "low": next(
                (
                    _number(row.get(key))
                    for key in ("low", "l", "3. low")
                    if row.get(key) is not None
                ),
                None,
            ),
            "close": next(
                (
                    _number(row.get(key))
                    for key in ("close", "c", "4. close")
                    if row.get(key) is not None
                ),
                None,
            ),
        }
        if ts is None or any(value is None for value in values.values()):
            return None
        volume = next(
            (
                _number(row.get(key))
                for key in ("volume", "v", "5. volume")
                if row.get(key) is not None
            ),
            None,
        )
        vwap = _number(row.get("vwap") or row.get("vw"))
        return OHLCVBar(
            instrument_id=instrument_id,
            data_source_id=data_source_id,
            timeframe=timeframe,
            ts=ts,
            open=values["open"],
            high=values["high"],
            low=values["low"],
            close=values["close"],
            volume=volume,
            vwap=vwap,
            is_adjusted=False,
            adjustment_basis="raw",
            adjustment_version="provider-native",
            provenance={"provider_payload": row},
        )

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
        return self.fetch_ohlcv(
            symbol,
            timeframe,
            self.latest_window_start(timeframe, limit),
            datetime.now(UTC),
            adjusted=adjusted,
            instrument_id=instrument_id,
            data_source_id=data_source_id,
        )[-max(0, limit) :]

    def latest_window_start(self, timeframe: Timeframe, limit: int) -> datetime:
        seconds = _TF_SECONDS.get(timeframe, 86400)
        return datetime.now(UTC) - timedelta(seconds=max(1, limit) * seconds * 1.5 + 86400)

    def get_current_price(self, symbol: str) -> float | None:
        bars = self.fetch_latest_ohlcv(symbol, Timeframe.D1, 1)
        return float(bars[-1].close) if bars else None


class TiingoProvider(_RESTProvider):
    name = "tiingo"
    base_url = "https://api.tiingo.com"
    description = "Tiingo optional EOD/IEX history and company metadata"
    key_setting = "TIINGO_API_KEY"
    auth_mode = "header"
    key_header = "Authorization"

    _RESAMPLE = {Timeframe.D1: "daily", Timeframe.W1: "weekly", Timeframe.MN: "monthly"}

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
        resample = self._RESAMPLE.get(timeframe)
        if not resample:
            return []
        payload = self._get(
            f"tiingo/daily/{symbol.upper()}/prices",
            {
                "startDate": _bounded_datetime(start).date().isoformat(),
                "endDate": _bounded_datetime(end).date().isoformat(),
                "resampleFreq": resample,
            },
        )
        rows = self._rows(payload)
        bars = [
            self._bar(row, timeframe, instrument_id=instrument_id, data_source_id=data_source_id)
            for row in rows
        ]
        return sorted(
            [
                bar
                for bar in bars
                if bar and _bounded_datetime(start) <= bar.ts < _bounded_datetime(end)
            ],
            key=lambda bar: bar.ts,
        )

    def search_instruments(self, query: str, *, limit: int = 10) -> list[ProviderSearchResult]:
        payload = self._get("tiingo/utilities/search", {"query": query, "limit": min(limit, 100)})
        return [
            ProviderSearchResult(
                symbol=str(row.get("ticker") or "").upper(),
                name=str(row.get("name") or row.get("ticker") or ""),
                exchange=str(row.get("exchangeCode") or ""),
                instrument_type="EQUITY",
            )
            for row in self._rows(payload)[:limit]
            if row.get("ticker")
        ]

    def get_instrument_profile(self, symbol: str) -> InstrumentProfile | None:
        rows = self._rows(self._get(f"tiingo/daily/{symbol.upper()}"))
        row = rows[0] if rows else None
        if not row:
            return None
        ticker = str(row.get("ticker") or symbol).upper()
        return InstrumentProfile(
            provider=self.name,
            symbol=ticker,
            canonical_symbol=ticker,
            name=str(row.get("name") or ticker),
            currency=str(row.get("currency") or "USD")[:3] or "USD",
            quote_type="EQUITY",
            exchange=str(row.get("exchangeCode") or ""),
            listings=[ListingRecord(provider_symbol=ticker, currency="USD", is_primary=True)],
            raw_payload=row,
        )


class TwelveDataProvider(_RESTProvider):
    name = "twelve_data"
    base_url = "https://api.twelvedata.com"
    description = "Twelve Data optional multi-timeframe history and quotes"
    key_setting = "TWELVE_DATA_API_KEY"
    key_param = "apikey"

    _INTERVAL = {
        Timeframe.M1: "1min",
        Timeframe.M5: "5min",
        Timeframe.M15: "15min",
        Timeframe.M30: "30min",
        Timeframe.H1: "1h",
        Timeframe.H2: "2h",
        Timeframe.H4: "4h",
        Timeframe.H12: "12h",
        Timeframe.D1: "1day",
        Timeframe.W1: "1week",
        Timeframe.MN: "1month",
    }

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
        interval = self._INTERVAL.get(timeframe)
        if not interval:
            return []
        payload = self._get(
            "time_series",
            {
                "symbol": symbol.upper(),
                "interval": interval,
                "start_date": _bounded_datetime(start).isoformat(),
                "end_date": _bounded_datetime(end).isoformat(),
                "outputsize": 5000,
                "format": "JSON",
            },
        )
        bars = [
            self._bar(
                row,
                timeframe,
                instrument_id=instrument_id,
                data_source_id=data_source_id,
                timestamp_keys=("datetime", "timestamp"),
            )
            for row in self._rows(payload, "values")
        ]
        return sorted(
            [
                bar
                for bar in bars
                if bar and _bounded_datetime(start) <= bar.ts < _bounded_datetime(end)
            ],
            key=lambda bar: bar.ts,
        )

    def get_current_price(self, symbol: str) -> float | None:
        payload = self._get("price", {"symbol": symbol.upper()})
        return _number(payload.get("price")) if isinstance(payload, dict) else None

    def search_instruments(self, query: str, *, limit: int = 10) -> list[ProviderSearchResult]:
        payload = self._get("symbol_search", {"symbol": query})
        rows = self._rows(payload, "data")
        return [
            ProviderSearchResult(
                symbol=str(row.get("symbol") or "").upper(),
                name=str(row.get("instrument_name") or row.get("symbol") or ""),
                exchange=str(row.get("exchange") or ""),
                instrument_type=str(row.get("instrument_type") or "EQUITY").upper(),
            )
            for row in rows[:limit]
            if row.get("symbol")
        ]

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        normalized = quote_type.strip().upper()
        if normalized not in {"EQUITY", "ETF"} or offset < 0:
            return {"total": 0, "quotes": []}
        rows = self._rows(self._get("stocks", {"country": "United States"}), "data")
        filtered: list[dict[str, Any]] = []
        for row in rows:
            kind = str(row.get("type") or row.get("instrument_type") or "EQUITY").upper()
            inferred = "ETF" if "ETF" in kind else "EQUITY"
            if inferred != normalized or not row.get("symbol"):
                continue
            filtered.append(
                {
                    "symbol": str(row["symbol"]).upper(),
                    "longName": row.get("name") or row.get("instrument_name"),
                    "exchange": row.get("exchange") or "",
                    "currency": row.get("currency") or "USD",
                    "quoteType": inferred,
                    "status": "active",
                }
            )
        page_size = 500
        return {"total": len(filtered), "quotes": filtered[offset : offset + page_size]}

    def supported_discovery_types(self) -> list[str]:
        return ["EQUITY", "ETF"]


class TradierProvider(_RESTProvider):
    name = "tradier"
    base_url = "https://api.tradier.com/v1"
    description = "Tradier US equities/options quotes and historical bars"
    key_setting = "TRADIER_API_KEY"
    auth_mode = "header"
    key_header = "Authorization"

    def _auth_headers(self) -> dict[str, str]:
        key = self._key()
        return {"Authorization": f"Bearer {key}", "Accept": "application/json"} if key else {}

    def fetch_ohlcv(self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime, *, adjusted: bool = True, instrument_id: int | None = None, data_source_id: int | None = None) -> list[OHLCVBar]:
        if timeframe not in {Timeframe.D1, Timeframe.W1, Timeframe.MN}:
            return []
        interval = {Timeframe.D1: "daily", Timeframe.W1: "weekly", Timeframe.MN: "monthly"}[timeframe]
        payload = self._get("markets/history", {"symbol": symbol.upper(), "interval": interval, "start": _bounded_datetime(start).date().isoformat(), "end": _bounded_datetime(end).date().isoformat()})
        rows = self._rows(payload, "history")
        return sorted([bar for bar in (self._bar(row, timeframe, instrument_id=instrument_id, data_source_id=data_source_id) for row in rows) if bar and start <= bar.ts < end], key=lambda bar: bar.ts)

    def get_current_price(self, symbol: str) -> float | None:
        payload = self._get("markets/quotes", {"symbols": symbol.upper()})
        quotes = payload.get("quotes", {}).get("quote") if isinstance(payload, dict) else None
        row = quotes[0] if isinstance(quotes, list) and quotes else quotes
        return _number(row.get("last")) if isinstance(row, dict) else None

    def search_instruments(self, query: str, *, limit: int = 10) -> list[ProviderSearchResult]:
        payload = self._get("markets/search", {"q": query, "indexes": "false"})
        rows = self._rows(payload, "securities")
        return [ProviderSearchResult(symbol=str(row.get("symbol") or "").upper(), name=str(row.get("description") or row.get("symbol") or ""), exchange=str(row.get("exchange") or ""), instrument_type=str(row.get("type") or "EQUITY").upper()) for row in rows[:limit] if row.get("symbol")]

    def latest_window_start(self, timeframe: Timeframe, limit: int) -> datetime:
        return datetime.now(UTC) - timedelta(days=max(30, limit * 2))


class MarketDataAppProvider(_RESTProvider):
    name = "marketdata_app"
    base_url = "https://api.marketdata.app/api/v1"
    description = "MarketData.app US stocks/options delayed REST data"
    key_setting = "MARKETDATA_APP_API_KEY"
    auth_mode = "header"
    key_header = "Authorization"

    def _auth_headers(self) -> dict[str, str]:
        key = self._key()
        return {"Authorization": f"Bearer {key}"} if key else {}

    def fetch_ohlcv(self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime, *, adjusted: bool = True, instrument_id: int | None = None, data_source_id: int | None = None) -> list[OHLCVBar]:
        resolution = {Timeframe.M1: "1", Timeframe.M5: "5", Timeframe.M15: "15", Timeframe.H1: "60", Timeframe.D1: "D", Timeframe.W1: "W"}.get(timeframe)
        if not resolution:
            return []
        payload = self._get(f"stocks/candles/{resolution}/{symbol.upper()}", {"from": _bounded_datetime(start).date().isoformat(), "to": _bounded_datetime(end).date().isoformat()})
        if not isinstance(payload, dict) or payload.get("s") not in {"ok", "no_data"}:
            return []
        rows = [{"t": ts, "o": o, "h": high, "l": low, "c": close, "v": volume} for ts, o, high, low, close, volume in zip(payload.get("t", []), payload.get("o", []), payload.get("h", []), payload.get("l", []), payload.get("c", []), payload.get("v", []))]
        return sorted([bar for bar in (self._bar(row, timeframe, instrument_id=instrument_id, data_source_id=data_source_id) for row in rows) if bar and start <= bar.ts < end], key=lambda bar: bar.ts)

    def latest_window_start(self, timeframe: Timeframe, limit: int) -> datetime:
        return datetime.now(UTC) - timedelta(seconds=_TF_SECONDS.get(timeframe, 86400) * max(1, limit))


class FinnhubProvider(_RESTProvider):
    name = "finnhub"
    base_url = "https://finnhub.io/api/v1"
    description = "Finnhub optional US candles, profiles, search, and earnings"
    key_setting = "FINNHUB_API_KEY"
    key_param = "token"

    _RESOLUTION = {
        Timeframe.M1: "1",
        Timeframe.M5: "5",
        Timeframe.M15: "15",
        Timeframe.M30: "30",
        Timeframe.H1: "60",
        Timeframe.D1: "D",
        Timeframe.W1: "W",
        Timeframe.MN: "M",
    }

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
        resolution = self._RESOLUTION.get(timeframe)
        if not resolution:
            return []
        payload = self._get(
            "stock/candle",
            {
                "symbol": symbol.upper(),
                "resolution": resolution,
                "from": int(_bounded_datetime(start).timestamp()),
                "to": int(_bounded_datetime(end).timestamp()),
            },
        )
        if not isinstance(payload, dict) or payload.get("s") not in {"ok", "no_data"}:
            return []
        rows = [
            {"t": ts, "o": open_, "h": high, "l": low, "c": close, "v": volume}
            for ts, open_, high, low, close, volume in zip(
                payload.get("t", []),
                payload.get("o", []),
                payload.get("h", []),
                payload.get("l", []),
                payload.get("c", []),
                payload.get("v", []),
            )
        ]
        bars = [
            self._bar(row, timeframe, instrument_id=instrument_id, data_source_id=data_source_id)
            for row in rows
        ]
        return sorted(
            [
                bar
                for bar in bars
                if bar and _bounded_datetime(start) <= bar.ts < _bounded_datetime(end)
            ],
            key=lambda bar: bar.ts,
        )

    def get_instrument_profile(self, symbol: str) -> InstrumentProfile | None:
        row = self._get("stock/profile2", {"symbol": symbol.upper()})
        if not isinstance(row, dict) or not row.get("ticker"):
            return None
        ticker = str(row["ticker"]).upper()
        return InstrumentProfile(
            provider=self.name,
            symbol=ticker,
            canonical_symbol=ticker,
            name=str(row.get("name") or ticker),
            currency=str(row.get("currency") or "USD"),
            quote_type="EQUITY",
            exchange=str(row.get("mic") or row.get("exchange") or ""),
            listings=[
                ListingRecord(
                    provider_symbol=ticker,
                    exchange_code=str(row.get("mic") or "") or None,
                    currency=str(row.get("currency") or "USD"),
                    is_primary=True,
                )
            ],
            raw_payload=row,
            extra={
                "country": row.get("country"),
                "market_cap": row.get("marketCapitalization"),
                "share_outstanding": row.get("shareOutstanding"),
            },
        )

    def search_instruments(self, query: str, *, limit: int = 10) -> list[ProviderSearchResult]:
        payload = self._get("search", {"q": query})
        rows = self._rows(payload, "result")
        return [
            ProviderSearchResult(
                symbol=str(row.get("symbol") or "").upper(),
                name=str(row.get("description") or row.get("symbol") or ""),
                exchange=str(row.get("mic") or ""),
                instrument_type=str(row.get("type") or "EQUITY").upper(),
            )
            for row in rows[:limit]
            if row.get("symbol")
        ]

    def fetch_instrument_events(self, symbol: str) -> list[InstrumentEventRecord]:
        rows = self._rows(self._get("stock/earnings", {"symbol": symbol.upper()}))
        fetched_at = datetime.now(UTC)
        events: list[InstrumentEventRecord] = []
        for row in rows:
            event_time = _timestamp(row.get("date") or row.get("period"))
            if event_time is None:
                continue
            events.append(
                InstrumentEventRecord(
                    event_type=InstrumentEventType.EARNINGS,
                    event_time=event_time,
                    time_hint=EventTimeHint.UNKNOWN,
                    title=f"Finnhub earnings {symbol.upper()}",
                    source_event_key=f"finnhub:earnings:{symbol.upper()}:{event_time.date().isoformat()}",
                    fetched_at=fetched_at,
                    eps_estimate=_decimal(row.get("epsEstimate")),
                    eps_actual=_decimal(row.get("epsActual")),
                    eps_surprise=_decimal(row.get("surprise")),
                    eps_surprise_pct=_decimal(row.get("surprisePercent")),
                    raw_payload=str(row),
                )
            )
        return events

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        normalized = quote_type.strip().upper()
        if normalized not in {"EQUITY", "ETF"} or offset < 0:
            return {"total": 0, "quotes": []}
        rows = self._rows(self._get("stock/symbol", {"exchange": "US"}))
        filtered: list[dict[str, Any]] = []
        for row in rows:
            kind = str(row.get("type") or "Common Stock").upper()
            inferred = "ETF" if "ETF" in kind else "EQUITY"
            if inferred != normalized or not row.get("symbol"):
                continue
            filtered.append(
                {
                    "symbol": str(row["symbol"]).upper(),
                    "longName": row.get("description") or row["symbol"],
                    "exchange": row.get("mic") or row.get("exchange") or "",
                    "currency": row.get("currency") or "USD",
                    "quoteType": inferred,
                    "status": "active",
                }
            )
        page_size = 500
        return {"total": len(filtered), "quotes": filtered[offset : offset + page_size]}

    def supported_discovery_types(self) -> list[str]:
        return ["EQUITY", "ETF"]


class MarketstackProvider(_RESTProvider):
    name = "marketstack"
    base_url = "https://api.marketstack.com/v1"
    description = "Marketstack optional US EOD history"
    key_setting = "MARKETSTACK_API_KEY"
    key_param = "access_key"

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
        payload = self._get(
            "eod",
            {
                "symbols": symbol.upper(),
                "date_from": _bounded_datetime(start).date().isoformat(),
                "date_to": _bounded_datetime(end).date().isoformat(),
                "limit": 1000,
            },
        )
        bars = [
            self._bar(row, timeframe, instrument_id=instrument_id, data_source_id=data_source_id)
            for row in self._rows(payload, "data")
        ]
        return sorted(
            [
                bar
                for bar in bars
                if bar and _bounded_datetime(start) <= bar.ts < _bounded_datetime(end)
            ],
            key=lambda bar: bar.ts,
        )

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        normalized = quote_type.strip().upper()
        if normalized not in {"EQUITY", "ETF"} or offset < 0:
            return {"total": 0, "quotes": []}
        payload = self._get("tickers", {"exchange": "XNYS", "limit": 1000, "offset": offset})
        rows = self._rows(payload, "data")
        quotes = []
        for row in rows:
            symbol = str(row.get("symbol") or row.get("ticker") or "").upper()
            if not symbol:
                continue
            inferred = "ETF" if "ETF" in str(row.get("name") or "").upper() else "EQUITY"
            if inferred != normalized:
                continue
            quotes.append(
                {
                    "symbol": symbol,
                    "longName": row.get("name") or symbol,
                    "exchange": row.get("exchange") or "",
                    "currency": row.get("currency") or "USD",
                    "quoteType": inferred,
                    "status": "active",
                }
            )
        pagination = payload.get("pagination") if isinstance(payload, dict) else None
        total = pagination.get("total") if isinstance(pagination, dict) else None
        return {"total": int(total or len(quotes)), "quotes": quotes}

    def supported_discovery_types(self) -> list[str]:
        return ["EQUITY", "ETF"]


class EODHDProvider(_RESTProvider):
    name = "eodhd"
    base_url = "https://eodhd.com/api"
    description = "EODHD optional long-history US EOD data"
    key_setting = "EODHD_API_KEY"
    key_param = "api_token"

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
        payload = self._get(
            f"eod/{symbol.upper()}.US",
            {
                "from": _bounded_datetime(start).date().isoformat(),
                "to": _bounded_datetime(end).date().isoformat(),
                "period": "d",
                "fmt": "json",
            },
        )
        bars = [
            self._bar(row, timeframe, instrument_id=instrument_id, data_source_id=data_source_id)
            for row in self._rows(payload)
        ]
        return sorted(
            [
                bar
                for bar in bars
                if bar and _bounded_datetime(start) <= bar.ts < _bounded_datetime(end)
            ],
            key=lambda bar: bar.ts,
        )

    def get_instrument_profile(self, symbol: str) -> InstrumentProfile | None:
        payload = self._get(f"fundamentals/{symbol.upper()}.US", {"filter": "General"})
        row = payload.get("General") if isinstance(payload, dict) else None
        if not isinstance(row, dict):
            return None
        ticker = str(row.get("Code") or symbol).upper()
        return InstrumentProfile(
            provider=self.name,
            symbol=ticker,
            canonical_symbol=ticker,
            name=str(row.get("Name") or ticker),
            currency=str(row.get("CurrencyCode") or "USD"),
            quote_type="EQUITY",
            exchange=str(row.get("Exchange") or ""),
            listings=[ListingRecord(provider_symbol=ticker, currency="USD", is_primary=True)],
            raw_payload=row,
        )

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        normalized = quote_type.strip().upper()
        if normalized not in {"EQUITY", "ETF"} or offset < 0:
            return {"total": 0, "quotes": []}
        rows = self._rows(self._get("exchange-symbol-list/US", {"fmt": "json"}))
        filtered = []
        for row in rows:
            symbol = str(row.get("Code") or row.get("code") or "").upper()
            if not symbol:
                continue
            kind = str(row.get("Type") or row.get("type") or "").upper()
            inferred = "ETF" if "ETF" in kind else "EQUITY"
            if inferred != normalized:
                continue
            filtered.append(
                {
                    "symbol": symbol,
                    "longName": row.get("Name") or row.get("name") or symbol,
                    "exchange": row.get("Exchange") or "US",
                    "currency": row.get("Currency") or "USD",
                    "quoteType": inferred,
                    "status": "active",
                }
            )
        page_size = 500
        return {"total": len(filtered), "quotes": filtered[offset : offset + page_size]}

    def supported_discovery_types(self) -> list[str]:
        return ["EQUITY", "ETF"]


class FMPProvider(_RESTProvider):
    name = "fmp"
    base_url = "https://financialmodelingprep.com/api/v3"
    description = "Financial Modeling Prep optional history, profile, and calendar data"
    key_setting = "FMP_API_KEY"
    key_param = "apikey"

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
        payload = self._get(
            f"historical-price-full/{symbol.upper()}",
            {
                "from": _bounded_datetime(start).date().isoformat(),
                "to": _bounded_datetime(end).date().isoformat(),
            },
        )
        bars = [
            self._bar(row, timeframe, instrument_id=instrument_id, data_source_id=data_source_id)
            for row in self._rows(payload, "historical")
        ]
        return sorted(
            [
                bar
                for bar in bars
                if bar and _bounded_datetime(start) <= bar.ts < _bounded_datetime(end)
            ],
            key=lambda bar: bar.ts,
        )

    def get_instrument_profile(self, symbol: str) -> InstrumentProfile | None:
        rows = self._rows(self._get(f"profile/{symbol.upper()}"))
        row = rows[0] if rows else None
        if not row:
            return None
        ticker = str(row.get("symbol") or symbol).upper()
        return InstrumentProfile(
            provider=self.name,
            symbol=ticker,
            canonical_symbol=ticker,
            name=str(row.get("companyName") or ticker),
            description=row.get("description"),
            currency=str(row.get("currency") or "USD"),
            quote_type="EQUITY",
            exchange=str(row.get("exchangeShortName") or row.get("exchange") or ""),
            listings=[ListingRecord(provider_symbol=ticker, currency="USD", is_primary=True)],
            raw_payload=row,
            extra={
                "sector": row.get("sector"),
                "industry": row.get("industry"),
                "website": row.get("website"),
                "market_cap": row.get("mktCap"),
            },
        )

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        normalized = quote_type.strip().upper()
        if normalized not in {"EQUITY", "ETF"} or offset < 0:
            return {"total": 0, "quotes": []}
        rows = self._rows(self._get("available-traded/list"))
        filtered = []
        for row in rows:
            symbol = str(row.get("symbol") or "").upper()
            if not symbol:
                continue
            kind = str(row.get("assetType") or row.get("type") or "EQUITY").upper()
            inferred = "ETF" if "ETF" in kind else "EQUITY"
            if inferred != normalized:
                continue
            filtered.append(
                {
                    "symbol": symbol,
                    "longName": row.get("name") or row.get("companyName") or symbol,
                    "exchange": row.get("exchangeShortName") or row.get("exchange") or "",
                    "currency": row.get("currency") or "USD",
                    "quoteType": inferred,
                    "status": "active",
                }
            )
        page_size = 500
        return {"total": len(filtered), "quotes": filtered[offset : offset + page_size]}

    def supported_discovery_types(self) -> list[str]:
        return ["EQUITY", "ETF"]


__all__ = [
    "EODHDProvider",
    "FMPProvider",
    "FinnhubProvider",
    "MarketstackProvider",
    "MarketDataAppProvider",
    "TradierProvider",
    "TiingoProvider",
    "TwelveDataProvider",
]
