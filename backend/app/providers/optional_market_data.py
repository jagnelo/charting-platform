"""Concrete, opt-in adapters for low-cost market-data APIs.

The providers in this module deliberately implement only documented REST
surfaces. They are registered so administrators can inspect their capabilities,
but they are not part of the default chain and have no entitlement seed until
terms/quotas have been reviewed. Missing credentials and explicit provider
error envelopes raise typed failures; they are never represented as successful
empty observations. This keeps adding an adapter from silently changing
routing.

All adapters normalize provider-specific symbols and response shapes into the
platform's provider contracts.  Raw response fields are retained in the bar's
provenance where the API exposes them; callers can therefore reconcile a
provider adjustment policy before promoting a series to canonical data.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from math import ceil
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from app.config import settings
from app.models.instrument_event import EventTimeHint, InstrumentEventType
from app.models.ohlcv import OHLCVBar, Timeframe
from app.providers.base import (
    InstrumentEventRecord,
    InstrumentProfile,
    ListingRecord,
    MarketEventRecord,
    ProviderSearchResult,
)
from app.providers.errors import (
    ProviderNotConfiguredError,
    raise_for_provider_error_envelope,
)
from app.providers.telemetry import observe_response

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
_TWELVE_DATA_POINTS_PER_REQUEST = 5000
_MARKETSTACK_POINTS_PER_REQUEST = 100


def estimate_twelve_data_ohlcv_request_count(
    timeframe: Timeframe, start: datetime, end: datetime
) -> int | None:
    """Estimate Twelve Data calls for its documented 5,000-point ceiling."""

    seconds = _TF_SECONDS.get(timeframe)
    if seconds is None:
        return None
    if end <= start:
        return 0
    span_seconds = max(0.0, (end - start).total_seconds())
    return max(1, ceil(span_seconds / (seconds * _TWELVE_DATA_POINTS_PER_REQUEST)))


def estimate_twelve_data_latest_ohlcv_request_count(timeframe: Timeframe, limit: int) -> int | None:
    """Reserve the generic REST adapter's lookback padding plus the page cap."""

    seconds = _TF_SECONDS.get(timeframe)
    if seconds is None:
        return None
    if limit <= 0:
        return 0
    span_seconds = max(1.0, limit * seconds * 1.5 + 86400)
    return max(1, ceil(span_seconds / (seconds * _TWELVE_DATA_POINTS_PER_REQUEST)))


def estimate_marketstack_ohlcv_request_count(
    timeframe: Timeframe, start: datetime, end: datetime
) -> int | None:
    """Conservatively reserve Marketstack's documented paged EOD response calls."""

    if timeframe is not Timeframe.D1 or end <= start:
        return 0 if end <= start else None
    calendar_days = max(1, (end.date() - start.date()).days + 1)
    return max(1, ceil(calendar_days / _MARKETSTACK_POINTS_PER_REQUEST))


def estimate_marketstack_latest_ohlcv_request_count(timeframe: Timeframe, limit: int) -> int | None:
    """Reserve a calendar-day upper bound for a latest Marketstack EOD read."""

    if timeframe is not Timeframe.D1:
        return None
    if limit <= 0:
        return 0
    calendar_days = max(1, ceil(limit * 1.5) + 1)
    return max(1, ceil(calendar_days / _MARKETSTACK_POINTS_PER_REQUEST))


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


def _timestamp(value: Any, *, timezone_name: str | None = None) -> datetime | None:
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
    if parsed.tzinfo is None:
        if timezone_name:
            try:
                parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
            except ZoneInfoNotFoundError:
                return None
        else:
            parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC) if timezone_name else parsed


def _bounded_datetime(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class _RESTProvider:
    """Small shared REST/normalisation layer used by the optional adapters.

    Several low-cost APIs return a JSON error envelope with HTTP 200. Treating
    those payloads as an empty dataset would make quota/auth/provider failures
    indistinguishable from a legitimate no-observation result.
    """

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
        observe_response(response)
        response.raise_for_status()
        payload = response.json()
        raise_for_provider_error_envelope(self.name, payload, response.status_code)
        return payload

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
        timestamp_timezone: str | None = None,
    ) -> OHLCVBar | None:
        ts = next(
            (
                _timestamp(row.get(key), timezone_name=timestamp_timezone)
                for key in timestamp_keys
                if row.get(key) is not None
            ),
            None,
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
        payload = self._get(f"tiingo/daily/{symbol.upper()}")
        # Tiingo's metadata endpoint returns one object, unlike its price and
        # search endpoints which return arrays. Keep this endpoint-specific
        # shape explicit rather than flattening arbitrary provider payloads.
        row = payload if isinstance(payload, dict) else None
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
        if not interval or end <= start:
            return []
        bounded_start = _bounded_datetime(start)
        bounded_end = _bounded_datetime(end)
        bars_by_timestamp: dict[datetime, OHLCVBar] = {}
        cursor = bounded_start
        while cursor < bounded_end:
            chunk_end = min(
                bounded_end,
                cursor + timedelta(seconds=_TF_SECONDS[timeframe] * _TWELVE_DATA_POINTS_PER_REQUEST),
            )
            request_params = {
                "symbol": symbol.upper(),
                "interval": interval,
                # With both boundaries present Twelve Data returns the
                # complete bounded range, up to its 5,000-point cap.
                "start_date": cursor.isoformat(),
                "end_date": chunk_end.isoformat(),
                "format": "JSON",
            }
            # Twelve Data emits intraday equity timestamps in the requested
            # timezone. Request UTC so the canonical parser has an explicit
            # boundary; daily/weekly/monthly timestamps are always exchange
            # local per the provider contract and are handled from metadata.
            request_timezone = None if timeframe in {Timeframe.D1, Timeframe.W1, Timeframe.MN} else "UTC"
            if request_timezone:
                request_params["timezone"] = request_timezone
            payload = self._get("time_series", request_params)
            metadata = payload.get("meta") if isinstance(payload, dict) else None
            exchange_timezone = (
                str(metadata.get("exchange_timezone") or "").strip()
                if isinstance(metadata, dict)
                else ""
            )
            timestamp_timezone = request_timezone or exchange_timezone or None
            for row in self._rows(payload, "values"):
                bar = self._bar(
                    row,
                    timeframe,
                    instrument_id=instrument_id,
                    data_source_id=data_source_id,
                    timestamp_keys=("datetime", "timestamp"),
                    timestamp_timezone=timestamp_timezone,
                )
                if bar and bounded_start <= bar.ts < bounded_end:
                    bars_by_timestamp[bar.ts] = bar
            cursor = chunk_end
        return [bars_by_timestamp[ts] for ts in sorted(bars_by_timestamp)]

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

    @staticmethod
    def _nested_rows(payload: Any, container: str, row_key: str) -> list[dict[str, Any]]:
        """Normalize Tradier's XML-to-JSON wrapper and singleton-object forms.

        Tradier documents responses such as ``{"history": {"day": [...]}}``
        and ``{"securities": {"security": [...]}}``. Its JSON conversion
        can also emit one object instead of an array when only one row exists.
        Do not flatten arbitrary payloads: preserving the endpoint-specific
        wrapper keeps malformed/provider-error responses distinguishable.
        """

        if not isinstance(payload, dict):
            return []
        wrapped = payload.get(container)
        if isinstance(wrapped, list):
            return [row for row in wrapped if isinstance(row, dict)]
        if not isinstance(wrapped, dict):
            return []
        rows = wrapped.get(row_key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
        if isinstance(rows, dict):
            return [rows]
        return []

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
        if timeframe not in {Timeframe.D1, Timeframe.W1, Timeframe.MN}:
            return []
        interval = {Timeframe.D1: "daily", Timeframe.W1: "weekly", Timeframe.MN: "monthly"}[
            timeframe
        ]
        payload = self._get(
            "markets/history",
            {
                "symbol": symbol.upper(),
                "interval": interval,
                "start": _bounded_datetime(start).date().isoformat(),
                "end": _bounded_datetime(end).date().isoformat(),
            },
        )
        rows = self._nested_rows(payload, "history", {"daily": "day", "weekly": "week", "monthly": "month"}[interval])
        if not rows:
            # Keep compatibility with a flat fixture/provider response while
            # still preferring the documented nested shape above.
            rows = self._rows(payload, "history")
        return sorted(
            [
                bar
                for bar in (
                    self._bar(
                        row, timeframe, instrument_id=instrument_id, data_source_id=data_source_id
                    )
                    for row in rows
                )
                if bar and start <= bar.ts < end
            ],
            key=lambda bar: bar.ts,
        )

    def get_current_price(self, symbol: str) -> float | None:
        payload = self._get("markets/quotes", {"symbols": symbol.upper()})
        rows = self._nested_rows(payload, "quotes", "quote")
        row = rows[0] if rows else None
        return _number(row.get("last")) if isinstance(row, dict) else None

    def search_instruments(self, query: str, *, limit: int = 10) -> list[ProviderSearchResult]:
        payload = self._get("markets/search", {"q": query, "indexes": "false"})
        rows = self._nested_rows(payload, "securities", "security")
        if not rows:
            rows = self._rows(payload, "securities")
        return [
            ProviderSearchResult(
                symbol=str(row.get("symbol") or "").upper(),
                name=str(row.get("description") or row.get("symbol") or ""),
                exchange=str(row.get("exchange") or ""),
                instrument_type=str(row.get("type") or "EQUITY").upper(),
            )
            for row in rows[:limit]
            if row.get("symbol")
        ]

    def latest_window_start(self, timeframe: Timeframe, limit: int) -> datetime:
        return datetime.now(UTC) - timedelta(days=max(30, limit * 2))


class MarketDataAppProvider(_RESTProvider):
    name = "marketdata_app"
    # The documented root is ``https://api.marketdata.app/`` and versioned
    # resources live directly below ``/v1``.  There is no ``/api`` segment.
    base_url = "https://api.marketdata.app/v1"
    description = "MarketData.app US stocks/options delayed REST data"
    key_setting = "MARKETDATA_APP_API_KEY"
    auth_mode = "header"
    key_header = "Authorization"

    def _auth_headers(self) -> dict[str, str]:
        key = self._key()
        return {"Authorization": f"Bearer {key}"} if key else {}

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
        resolution = {
            Timeframe.M1: "1",
            Timeframe.M5: "5",
            Timeframe.M15: "15",
            Timeframe.H1: "60",
            Timeframe.D1: "D",
            Timeframe.W1: "W",
        }.get(timeframe)
        if not resolution:
            return []
        payload = self._get(
            f"stocks/candles/{resolution}/{symbol.upper()}",
            {
                "from": _bounded_datetime(start).date().isoformat(),
                "to": _bounded_datetime(end).date().isoformat(),
            },
        )
        if not isinstance(payload, dict) or payload.get("s") not in {"ok", "no_data"}:
            return []
        rows = [
            {"t": ts, "o": o, "h": high, "l": low, "c": close, "v": volume}
            for ts, o, high, low, close, volume in zip(
                payload.get("t", []),
                payload.get("o", []),
                payload.get("h", []),
                payload.get("l", []),
                payload.get("c", []),
                payload.get("v", []),
            )
        ]
        return sorted(
            [
                bar
                for bar in (
                    self._bar(
                        row, timeframe, instrument_id=instrument_id, data_source_id=data_source_id
                    )
                    for row in rows
                )
                if bar and start <= bar.ts < end
            ],
            key=lambda bar: bar.ts,
        )

    def latest_window_start(self, timeframe: Timeframe, limit: int) -> datetime:
        return datetime.now(UTC) - timedelta(
            seconds=_TF_SECONDS.get(timeframe, 86400) * max(1, limit)
        )


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
                    # Finnhub's documented earnings-surprise payload names
                    # these fields ``estimate``/``actual``. Accept the
                    # explicit EPS aliases as a compatibility shape only;
                    # do not discard provider values when the documented
                    # names are returned.
                    eps_estimate=_decimal(row.get("estimate", row.get("epsEstimate"))),
                    eps_actual=_decimal(row.get("actual", row.get("epsActual"))),
                    eps_surprise=_decimal(row.get("surprise")),
                    eps_surprise_pct=_decimal(row.get("surprisePercent")),
                    raw_payload=str(row),
                )
            )
        return events

    def fetch_market_events(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[MarketEventRecord]:
        """Normalize Finnhub's forward/historical earnings calendar."""

        params: dict[str, Any] = {}
        if start is not None:
            params["from"] = start.isoformat()
        if end is not None:
            params["to"] = end.isoformat()
        rows = self._rows(self._get("calendar/earnings", params), "earningsCalendar")
        events: list[MarketEventRecord] = []
        for row in rows:
            event_time = _timestamp(row.get("date"))
            if event_time is None:
                continue
            event_date = event_time.date()
            if (start and event_date < start) or (end and event_date > end):
                continue
            symbol = str(row.get("symbol") or "").strip().upper()
            event_key = f"finnhub:earnings_calendar:{symbol or 'market'}:{event_date.isoformat()}"
            events.append(
                MarketEventRecord(
                    event_type="earnings",
                    event_key=event_key,
                    event_time=event_time,
                    effective_date=event_date,
                    title=f"Finnhub earnings calendar {symbol}".strip(),
                    source_version="calendar/earnings",
                    raw_payload=row,
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
        if end <= start:
            return []
        bounded_start = _bounded_datetime(start)
        bounded_end = _bounded_datetime(end)
        bars_by_timestamp: dict[datetime, OHLCVBar] = {}
        offset = 0
        seen_offsets: set[int] = set()
        while offset not in seen_offsets:
            seen_offsets.add(offset)
            payload = self._get(
                "eod",
                {
                    "symbols": symbol.upper(),
                    "date_from": bounded_start.date().isoformat(),
                    "date_to": bounded_end.date().isoformat(),
                    # Marketstack's documented pagination examples expose a
                    # 100-row page. Follow the returned metadata rather than
                    # assuming that a larger requested limit is honoured.
                    "limit": _MARKETSTACK_POINTS_PER_REQUEST,
                    "offset": offset,
                },
            )
            rows = self._rows(payload, "data")
            for row in rows:
                bar = self._bar(
                    row, timeframe, instrument_id=instrument_id, data_source_id=data_source_id
                )
                if bar and bounded_start <= bar.ts < bounded_end:
                    bars_by_timestamp[bar.ts] = bar

            pagination = payload.get("pagination") if isinstance(payload, dict) else None
            if not isinstance(pagination, dict):
                break
            try:
                page_offset = int(pagination.get("offset", offset))
                count = int(pagination.get("count", len(rows)))
                total_value = pagination.get("total")
                total = int(total_value) if total_value is not None else None
                page_limit = max(
                    1, int(pagination.get("limit", _MARKETSTACK_POINTS_PER_REQUEST))
                )
            except (TypeError, ValueError):
                break
            if count <= 0 or page_offset < 0:
                break
            next_offset = page_offset + count
            if next_offset <= offset:
                break
            if total is not None and next_offset >= total:
                break
            if total is None and count < page_limit:
                break
            offset = next_offset

        return [bars_by_timestamp[ts] for ts in sorted(bars_by_timestamp)]

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

    _PERIOD = {
        Timeframe.D1: "d",
        Timeframe.W1: "w",
        Timeframe.MN: "m",
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
        period = self._PERIOD.get(timeframe)
        if not period:
            return []
        payload = self._get(
            f"eod/{symbol.upper()}.US",
            {
                "from": _bounded_datetime(start).date().isoformat(),
                "to": _bounded_datetime(end).date().isoformat(),
                "period": period,
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
    base_url = "https://financialmodelingprep.com/stable"
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
            "historical-price-eod/full",
            {
                "symbol": symbol.upper(),
                "from": _bounded_datetime(start).date().isoformat(),
                "to": _bounded_datetime(end).date().isoformat(),
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
        rows = self._rows(self._get("profile", {"symbol": symbol.upper()}))
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
        rows = self._rows(self._get("stock-list"))
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
