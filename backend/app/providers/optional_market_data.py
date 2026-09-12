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
from email.utils import parsedate_to_datetime
from math import ceil, isfinite
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
    OptionContractRecord,
    OptionQuotePointRecord,
    ProviderSearchResult,
)
from app.providers.errors import (
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
    provider_response_headers,
    raise_for_provider_error_envelope,
    redact_provider_message,
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


def _retry_at_from_headers(headers: dict[str, str]) -> datetime | None:
    """Parse provider reset headers without inventing a reset when absent."""

    retry_after = headers.get("retry-after") or headers.get("Retry-After")
    if retry_after:
        try:
            return datetime.now(UTC) + timedelta(seconds=max(0, float(retry_after)))
        except (TypeError, ValueError, OverflowError):
            try:
                parsed = parsedate_to_datetime(retry_after)
                return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
            except (TypeError, ValueError, OverflowError):
                pass
    now = datetime.now(UTC)
    for name in (
        "x-api-ratelimit-reset",
        "x-ratelimit-reset",
        "x-rate-limit-reset",
        "ratelimit-reset",
    ):
        value = headers.get(name) or headers.get(name.title())
        if not value:
            continue
        try:
            raw = float(value)
        except (TypeError, ValueError, OverflowError):
            continue
        return datetime.fromtimestamp(raw, tz=UTC) if raw > 1_000_000_000 else now + timedelta(seconds=max(0, raw))
    return None


def _raise_http_error(provider_name: str, exc: httpx.HTTPStatusError) -> None:
    """Convert optional-provider HTTP failures into safe typed errors.

    httpx includes the complete request URL in ``HTTPStatusError``. Query-key
    providers therefore must not re-raise that exception directly: a live-test
    traceback or an unhandled log would expose the configured credential.
    """

    response = exc.response
    status_code = getattr(response, "status_code", None)
    headers = provider_response_headers(response)
    message = redact_provider_message(str(exc))
    lowered = message.lower()
    if status_code in {418, 429} or any(
        marker in lowered
        for marker in ("rate limit", "rate_limit", "too many request", "quota", "throttl")
    ):
        raise ProviderRateLimitError(
            provider_name,
            message or f"{provider_name} request rate-limited",
            retry_at=_retry_at_from_headers(headers),
            status_code=status_code,
            headers=headers,
        ) from exc
    raise ProviderResponseError(
        provider_name,
        message or f"{provider_name} request failed",
        status_code=status_code,
    ) from exc


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
        if isinstance(value, bool) or value in (None, "", "null", "None", "-"):
            return None
        number = float(value)
        return number if isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _strict_int(value: Any, provider_name: str, field: str, *, minimum: int = 0) -> int:
    """Parse provider pagination counters without coercing booleans/floats."""

    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ProviderResponseError(provider_name, f"provider returned an invalid {field}")
    return value


def _decimal(value: Any) -> Decimal | None:
    try:
        if value in (None, ""):
            return None
        number = Decimal(str(value))
        return number if number.is_finite() else None
    except (TypeError, ValueError):
        return None


def _required_text(
    row: dict[str, Any], provider_name: str, label: str, *keys: str
) -> str:
    """Read a required provider identity field without silent row loss."""

    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            text = str(value).strip()
            if text:
                return text
    expected = ", ".join(keys) or label
    raise ProviderResponseError(
        provider_name, f"provider returned a row without required {label}: {expected}"
    )


def _checked_decimal(
    value: Any, provider_name: str, field: str
) -> Decimal | None:
    """Parse optional numeric provider fields while rejecting malformed values."""

    parsed = _decimal(value)
    if value not in (None, "", "null", "None", "-") and parsed is None:
        raise ProviderResponseError(provider_name, f"provider returned an invalid {field}")
    return parsed


def _timestamp(value: Any, *, timezone_name: str | None = None) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, int | float) and not isinstance(value, bool):
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


def _option_expiry(value: Any) -> date | None:
    """Parse provider option-expiration values without guessing a timezone."""

    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, int | float) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value, tz=UTC).date()
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _option_right(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"c", "call", "calls"}:
        return "call"
    if normalized in {"p", "put", "puts"}:
        return "put"
    return None


def _option_contract_from_row(
    row: dict[str, Any],
    *,
    underlying_symbol: str,
    fallback_expiration: date | None = None,
) -> OptionContractRecord:
    """Normalize a documented Tradier-style option row.

    Tradier's brokerage JSON uses snake-case fields and nests Greeks under
    ``greeks``.  Keeping this parser tolerant of singleton/alias fields makes
    the adapter safe for both production responses and recorded fixtures while
    retaining the complete raw row for reconciliation.
    """

    if not isinstance(row, dict):
        raise ProviderResponseError("tradier", "provider returned a non-object option contract")
    provider_symbol = str(
        row.get("symbol") or row.get("optionSymbol") or row.get("option_symbol") or ""
    ).strip()
    expiration = _option_expiry(
        row.get("expiration_date")
        or row.get("expirationDate")
        or row.get("expiration")
        or fallback_expiration
    )
    right = _option_right(
        row.get("option_type")
        or row.get("optionType")
        or row.get("type")
        or row.get("side")
    )
    if not provider_symbol or expiration is None or right is None:
        raise ProviderResponseError(
            "tradier", "provider returned an option contract without symbol, expiry, or right"
        )

    raw_greeks = row.get("greeks")
    if raw_greeks not in (None, "") and not isinstance(raw_greeks, dict):
        raise ProviderResponseError("tradier", "provider returned an invalid option Greeks object")
    greeks = raw_greeks if isinstance(raw_greeks, dict) else {}

    def value(*names: str) -> Any:
        for name in names:
            if row.get(name) is not None:
                return row[name]
            if greeks.get(name) is not None:
                return greeks[name]
        return None

    def checked_decimal(field: str, *names: str) -> Decimal | None:
        raw = value(*names)
        parsed = _decimal(raw)
        if raw not in (None, "") and parsed is None:
            raise ProviderResponseError("tradier", f"provider returned an invalid option {field}")
        return parsed

    strike = checked_decimal("strike", "strike")
    if strike is None or strike <= 0:
        raise ProviderResponseError("tradier", "provider returned an invalid option strike")
    bid = checked_decimal("bid", "bid")
    ask = checked_decimal("ask", "ask")
    mark = checked_decimal("mark", "mid", "mark")
    if mark is None and bid is not None and ask is not None:
        mark = (bid + ask) / Decimal("2")
    observed_at = _timestamp(value("updated", "last_updated", "quote_time"))
    contract_size = checked_decimal("contract size", "contract_size", "contractSize")
    last_price = checked_decimal("last price", "last", "last_price")
    volume = checked_decimal("volume", "volume")
    open_interest = checked_decimal("open interest", "open_interest", "openInterest")
    implied_vol = checked_decimal(
        "implied volatility", "iv", "mid_iv", "implied_volatility", "impliedVolatility"
    )
    delta = checked_decimal("delta", "delta")
    gamma = checked_decimal("gamma", "gamma")
    theta = checked_decimal("theta", "theta")
    vega = checked_decimal("vega", "vega")
    rho = checked_decimal("rho", "rho")
    return OptionContractRecord(
        provider_symbol=provider_symbol,
        underlying_symbol=str(
            row.get("underlying") or row.get("underlying_symbol") or underlying_symbol
        ).upper(),
        expiry_date=expiration,
        strike=strike,
        right=right,
        currency=str(row.get("currency") or "USD").upper(),
        contract_size=contract_size,
        bid=bid,
        ask=ask,
        mark=mark,
        last_price=last_price,
        volume=volume,
        open_interest=open_interest,
        implied_vol=implied_vol,
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
        rho=rho,
        observed_at=observed_at,
        raw_payload=dict(row),
    )


def _parallel_candle_rows(payload: Any, provider_name: str) -> list[dict[str, Any]]:
    """Validate providers that encode candles as parallel arrays.

    Finnhub and MarketData.app both use this shape.  A non-success status or
    mismatched array lengths is a malformed/provider response, not a valid
    empty series; silently zipping such arrays would discard observations.
    """

    if not isinstance(payload, dict):
        raise ProviderResponseError(provider_name, "provider returned an invalid candle object")
    status = str(payload.get("s") or "").strip().lower()
    if status == "no_data":
        return []
    if status != "ok":
        raise ProviderResponseError(
            provider_name, f"provider returned an invalid candle status: {status or '<missing>'}"
        )
    fields = ("t", "o", "h", "l", "c", "v")
    arrays = [payload.get(field) for field in fields]
    if any(not isinstance(values, list) for values in arrays):
        raise ProviderResponseError(provider_name, "provider returned invalid candle arrays")
    lengths = {len(values) for values in arrays}
    if len(lengths) != 1:
        raise ProviderResponseError(provider_name, "provider returned mismatched candle arrays")
    return [
        {"t": ts, "o": open_, "h": high, "l": low, "c": close, "v": volume}
        for ts, open_, high, low, close, volume in zip(*arrays)
    ]


def _parallel_option_rows(payload: Any, provider_name: str) -> list[dict[str, Any]]:
    """Expand MarketData.app's parallel option-chain arrays safely.

    The documented options endpoints return one array per field rather than a
    list of objects.  Zipping arrays of different lengths would silently
    discard contracts, so required and present optional arrays must all have
    the same length before a row is constructed.  Optional columns are filled
    with ``None`` only when the provider omits the entire column; a partially
    missing column is malformed provider data.
    """

    if not isinstance(payload, dict):
        raise ProviderResponseError(provider_name, "provider returned an invalid option-chain object")
    status = str(payload.get("s") or "").strip().lower()
    if status == "no_data":
        return []
    if status != "ok":
        raise ProviderResponseError(
            provider_name,
            f"provider returned an invalid option-chain status: {status or '<missing>'}",
        )

    required_fields = ("optionSymbol", "underlying", "expiration", "side", "strike")
    optional_fields = (
        "firstTraded",
        "dte",
        "ask",
        "askSize",
        "bid",
        "bidSize",
        "mid",
        "last",
        "volume",
        "openInterest",
        "underlyingPrice",
        "inTheMoney",
        "intrinsicValue",
        "extrinsicValue",
        "updated",
        "iv",
        "delta",
        "gamma",
        "theta",
        "vega",
        "rho",
    )
    arrays: dict[str, list[Any]] = {}
    for field in required_fields:
        value = payload.get(field)
        if not isinstance(value, list):
            raise ProviderResponseError(
                provider_name, f"provider returned an invalid option {field} array"
            )
        arrays[field] = value
    expected_length = len(arrays[required_fields[0]])
    if any(len(arrays[field]) != expected_length for field in required_fields[1:]):
        raise ProviderResponseError(provider_name, "provider returned mismatched option arrays")
    for field in optional_fields:
        value = payload.get(field)
        if value is None:
            arrays[field] = [None] * expected_length
        elif not isinstance(value, list) or len(value) != expected_length:
            raise ProviderResponseError(
                provider_name, f"provider returned a mismatched option {field} array"
            )
        else:
            arrays[field] = value

    rows: list[dict[str, Any]] = []
    for index in range(expected_length):
        row = {field: values[index] for field, values in arrays.items()}
        symbol = str(row["optionSymbol"] or "").strip()
        underlying = str(row["underlying"] or "").strip()
        if not symbol or not underlying:
            raise ProviderResponseError(
                provider_name, "provider returned an option without symbol or underlying"
            )
        if _option_expiry(row["expiration"]) is None:
            raise ProviderResponseError(provider_name, "provider returned an invalid option expiration")
        if _option_right(row["side"]) is None:
            raise ProviderResponseError(provider_name, "provider returned an invalid option side")
        strike = _checked_decimal(row["strike"], provider_name, "option strike")
        if strike is None or strike <= 0:
            raise ProviderResponseError(provider_name, "provider returned an invalid option strike")
        rows.append(row)
    return rows


def _parallel_option_quote_rows(payload: Any, provider_name: str) -> list[dict[str, Any]]:
    """Expand MarketData.app option-quote arrays without truncation.

    The quotes endpoint has a smaller shape than the chain endpoint: the
    contract identity is the OCC ``optionSymbol`` and each observation is
    timestamped by ``updated``. Historical responses legitimately return null
    Greeks, but an observation without either identity or timestamp is not
    usable by the quote-history persistence path and is rejected.
    """

    if not isinstance(payload, dict):
        raise ProviderResponseError(provider_name, "provider returned an invalid option-quote object")
    status = str(payload.get("s") or "").strip().lower()
    if status == "no_data":
        return []
    if status != "ok":
        raise ProviderResponseError(
            provider_name,
            f"provider returned an invalid option-quote status: {status or '<missing>'}",
        )
    required_fields = ("optionSymbol", "updated")
    optional_fields = (
        "bid",
        "ask",
        "mid",
        "last",
        "volume",
        "openInterest",
        "iv",
        "delta",
        "gamma",
        "theta",
        "vega",
        "rho",
        "underlyingPrice",
        "inTheMoney",
        "intrinsicValue",
        "extrinsicValue",
        "bidSize",
        "askSize",
    )
    arrays: dict[str, list[Any]] = {}
    for field in required_fields:
        value = payload.get(field)
        if not isinstance(value, list):
            raise ProviderResponseError(
                provider_name, f"provider returned an invalid option-quote {field} array"
            )
        arrays[field] = value
    expected_length = len(arrays["optionSymbol"])
    if len(arrays["updated"]) != expected_length:
        raise ProviderResponseError(provider_name, "provider returned mismatched option-quote arrays")
    for field in optional_fields:
        value = payload.get(field)
        if value is None:
            arrays[field] = [None] * expected_length
        elif not isinstance(value, list) or len(value) != expected_length:
            raise ProviderResponseError(
                provider_name, f"provider returned a mismatched option-quote {field} array"
            )
        else:
            arrays[field] = value

    rows: list[dict[str, Any]] = []
    for index in range(expected_length):
        row = {field: values[index] for field, values in arrays.items()}
        if not str(row["optionSymbol"] or "").strip() or _timestamp(
            row["updated"], timezone_name="America/New_York"
        ) is None:
            raise ProviderResponseError(
                provider_name, "provider returned an option quote without symbol or timestamp"
            )
        rows.append(row)
    return rows


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

    def _require_raw_history(self, adjusted: bool) -> None:
        """Reject adjusted requests for adapters that expose raw bars only.

        Resolver admission normally prevents this path, but provider adapters
        are also used directly by live probes and maintenance code. Failing
        before transport keeps those callers from persisting raw observations
        under the adjusted dataset.
        """

        if adjusted:
            raise ProviderResponseError(
                self.name,
                f"{self.name} historical bars are raw; request adjusted=False",
            )

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

    def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        base_url: str | None = None,
    ) -> Any:
        if self.key_setting and not self._key():
            raise ProviderNotConfiguredError(
                f"{self.name} requires {self.key_setting}; configure it before routing"
            )
        try:
            response = httpx.get(
                f"{(base_url or self.base_url).rstrip('/')}/{path.lstrip('/')}",
                params=self._auth_params(params),
                headers=self._auth_headers(),
                timeout=30,
            )
            observe_response(response)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _raise_http_error(self.name, exc)
        except httpx.RequestError as exc:
            raise ProviderResponseError(self.name, redact_provider_message(str(exc))) from exc
        try:
            payload = response.json()
        except (TypeError, ValueError) as exc:
            raise ProviderResponseError(self.name, "provider returned invalid JSON") from exc
        if not isinstance(payload, dict | list):
            raise ProviderResponseError(
                self.name, "provider returned an invalid JSON shape"
            )
        raise_for_provider_error_envelope(
            self.name, payload, response.status_code, headers=provider_response_headers(response)
        )
        return payload

    @staticmethod
    def _strict_rows(payload: Any, provider_name: str, *keys: str) -> list[dict[str, Any]]:
        """Validate a documented row-list response without silent truncation."""

        if isinstance(payload, list):
            value: Any = payload
        elif isinstance(payload, dict):
            missing = object()
            value = missing
            for key in keys:
                if key in payload:
                    value = payload[key]
                    break
            if value is missing:
                expected = ", ".join(keys) or "the documented row list"
                raise ProviderResponseError(
                    provider_name, f"provider omitted the expected row container: {expected}"
                )
        else:
            raise ProviderResponseError(provider_name, "provider returned an invalid row-list shape")
        if not isinstance(value, list):
            expected = ", ".join(keys) or "the documented row list"
            raise ProviderResponseError(
                provider_name, f"provider returned an invalid row container: {expected}"
            )
        if any(not isinstance(row, dict) for row in value):
            raise ProviderResponseError(provider_name, "provider returned a non-object row")
        return value

    def _bar(
        self,
        row: dict[str, Any],
        timeframe: Timeframe,
        *,
        instrument_id: int | None,
        data_source_id: int | None,
        timestamp_keys: tuple[str, ...] = ("timestamp", "datetime", "date", "t"),
        timestamp_timezone: str | None = None,
    ) -> OHLCVBar:
        def raw_value(*keys: str) -> Any:
            for key in keys:
                if key in row:
                    return row[key]
            return None

        def checked_number(field: str, *keys: str, required: bool = False) -> float | None:
            raw = raw_value(*keys)
            parsed = _number(raw)
            missing = raw in (None, "", "null", "None", "-")
            if required and (missing or parsed is None):
                raise ProviderResponseError(
                    self.name, f"provider returned an invalid OHLCV {field} value"
                )
            if not missing and parsed is None:
                raise ProviderResponseError(
                    self.name, f"provider returned an invalid OHLCV {field} value"
                )
            return parsed

        ts = _timestamp(raw_value(*timestamp_keys), timezone_name=timestamp_timezone)
        if ts is None:
            raise ProviderResponseError(self.name, "provider returned an invalid OHLCV timestamp")
        values = {
            "open": checked_number("open", "open", "o", "1. open", required=True),
            "high": checked_number("high", "high", "h", "2. high", required=True),
            "low": checked_number("low", "low", "l", "3. low", required=True),
            "close": checked_number("close", "close", "c", "4. close", required=True),
        }
        volume = checked_number("volume", "volume", "v", "5. volume")
        vwap = checked_number("vwap", "vwap", "vw")
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
        # These adapters expose raw history only. Current-price reads must use
        # that explicit raw contract rather than inheriting the protocol's
        # adjusted-history default and being rejected by the safety guard.
        bars = self.fetch_latest_ohlcv(symbol, Timeframe.D1, 1, adjusted=False)
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
        self._require_raw_history(adjusted)
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
        rows = self._strict_rows(payload, self.name)
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
        results: list[ProviderSearchResult] = []
        for row in self._strict_rows(payload, self.name):
            ticker = _required_text(row, self.name, "ticker", "ticker")
            results.append(
                ProviderSearchResult(
                    symbol=ticker.upper(),
                    name=str(row.get("name") or ticker),
                    exchange=str(row.get("exchangeCode") or ""),
                    instrument_type="EQUITY",
                )
            )
        return results[:limit]

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
        self._require_raw_history(adjusted)
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
            for row in self._strict_rows(payload, self.name, "values"):
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
        rows = self._strict_rows(payload, self.name, "data")
        results: list[ProviderSearchResult] = []
        for row in rows:
            symbol = _required_text(row, self.name, "symbol", "symbol")
            results.append(
                ProviderSearchResult(
                    symbol=symbol.upper(),
                    name=str(row.get("instrument_name") or symbol),
                    exchange=str(row.get("exchange") or ""),
                    instrument_type=str(row.get("instrument_type") or "EQUITY").upper(),
                )
            )
        return results[:limit]

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        normalized = quote_type.strip().upper()
        if normalized not in {"EQUITY", "ETF"} or offset < 0:
            return {"total": 0, "quotes": []}
        rows = self._strict_rows(
            self._get("stocks", {"country": "United States"}), self.name, "data"
        )
        filtered: list[dict[str, Any]] = []
        for row in rows:
            symbol = _required_text(row, self.name, "symbol", "symbol")
            kind = str(row.get("type") or row.get("instrument_type") or "EQUITY").upper()
            inferred = "ETF" if "ETF" in kind else "EQUITY"
            if inferred != normalized:
                continue
            filtered.append(
                {
                    "symbol": symbol.upper(),
                    "longName": row.get("name") or row.get("instrument_name") or symbol,
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
            if any(not isinstance(row, dict) for row in wrapped):
                raise ProviderResponseError("tradier", f"provider returned an invalid {container} row")
            return wrapped
        if not isinstance(wrapped, dict):
            if wrapped in (None, ""):
                return []
            raise ProviderResponseError(
                "tradier", f"provider returned an invalid {container} wrapper"
            )
        rows = wrapped.get(row_key)
        if row_key not in wrapped:
            if not wrapped:
                return []
            raise ProviderResponseError(
                "tradier", f"provider omitted the documented {container}.{row_key} rows"
            )
        if isinstance(rows, list):
            if any(not isinstance(row, dict) for row in rows):
                raise ProviderResponseError(
                    "tradier", f"provider returned an invalid {container}.{row_key} row"
                )
            return rows
        if isinstance(rows, dict):
            return [rows]
        if rows in (None, ""):
            return []
        raise ProviderResponseError(
            "tradier", f"provider returned an invalid {container}.{row_key} shape"
        )

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
        self._require_raw_history(adjusted)
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
            rows = self._strict_rows(payload, self.name, "history")
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
            rows = self._strict_rows(payload, self.name, "securities")
        results: list[ProviderSearchResult] = []
        for row in rows:
            symbol = _required_text(row, self.name, "symbol", "symbol")
            results.append(
                ProviderSearchResult(
                    symbol=symbol.upper(),
                    name=str(row.get("description") or symbol),
                    exchange=str(row.get("exchange") or ""),
                    instrument_type=str(row.get("type") or "EQUITY").upper(),
                )
            )
        return results[:limit]

    def list_option_expirations(self, symbol: str) -> list[date]:
        """Return Tradier's available OCC expiration dates for an underlying."""

        payload = self._get(
            "markets/options/expirations",
            {
                "symbol": symbol.upper(),
                "includeAllRoots": "false",
                "strikes": "false",
                "contractSize": "true",
            },
        )
        if not isinstance(payload, dict):
            raise ProviderResponseError("tradier", "provider returned an invalid expirations object")
        marker = object()
        wrapped = payload.get("expirations", marker)
        if wrapped is marker:
            raise ProviderResponseError("tradier", "provider omitted the expirations wrapper")
        if isinstance(wrapped, dict):
            values = wrapped.get("date")
            if "date" not in wrapped and wrapped:
                raise ProviderResponseError(
                    "tradier", "provider omitted the documented expirations.date rows"
                )
        elif isinstance(wrapped, list | str | int | float) or wrapped in (None, ""):
            values = wrapped
        else:
            raise ProviderResponseError("tradier", "provider returned an invalid expirations shape")
        if values in (None, ""):
            return []
        if not isinstance(values, list):
            values = [values]
        parsed_values: set[date] = set()
        for value in values:
            parsed = _option_expiry(value)
            if parsed is None:
                raise ProviderResponseError("tradier", "provider returned an invalid expiration date")
            parsed_values.add(parsed)
        return sorted(parsed_values)

    def fetch_option_chain(
        self,
        symbol: str,
        *,
        expiration: date | None = None,
        max_symbols: int | None = None,
    ) -> list[OptionContractRecord]:
        """Fetch one current Tradier option chain with provider Greeks."""

        if expiration is None:
            expirations = self.list_option_expirations(symbol)
            if not expirations:
                return []
            expiration = expirations[0]
        payload = self._get(
            "markets/options/chains",
            {
                "symbol": symbol.upper(),
                "expiration": expiration.isoformat(),
                "greeks": "true",
            },
        )
        rows = self._nested_rows(payload, "options", "option")
        if not rows:
            rows = self._strict_rows(payload, self.name, "options")
        contracts = [
            _option_contract_from_row(
                row,
                underlying_symbol=symbol,
                fallback_expiration=expiration,
            )
            for row in rows
        ]
        return sorted(contracts, key=lambda contract: (contract.expiry_date, contract.strike, contract.right, contract.provider_symbol))

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
        self._require_raw_history(adjusted)
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
            # MarketData.app canonicalizes candle resources with a trailing
            # slash; omitting it causes a 301 redirect that the shared REST
            # client intentionally does not follow for response-integrity
            # reasons.
            f"stocks/candles/{resolution}/{symbol.upper()}/",
            {
                "from": _bounded_datetime(start).date().isoformat(),
                "to": _bounded_datetime(end).date().isoformat(),
            },
        )
        rows = _parallel_candle_rows(payload, self.name)
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

    def list_option_expirations(self, symbol: str) -> list[date]:
        """Return the documented expiration dates for one US option root."""

        payload = self._get(f"options/expirations/{symbol.upper()}/")
        if not isinstance(payload, dict):
            raise ProviderResponseError(
                self.name, "provider returned an invalid option-expirations object"
            )
        status = str(payload.get("s") or "").strip().lower()
        if status == "no_data":
            return []
        if status != "ok":
            raise ProviderResponseError(
                self.name,
                f"provider returned an invalid option-expirations status: {status or '<missing>'}",
            )
        values = payload.get("expirations")
        if not isinstance(values, list):
            raise ProviderResponseError(
                self.name, "provider returned an invalid option-expirations array"
            )
        expirations: set[date] = set()
        for value in values:
            parsed = _option_expiry(value)
            if parsed is None:
                raise ProviderResponseError(
                    self.name, "provider returned an invalid option expiration"
                )
            expirations.add(parsed)
        return sorted(expirations)

    def fetch_option_chain(
        self,
        symbol: str,
        *,
        expiration: date | None = None,
        max_symbols: int | None = None,
    ) -> list[OptionContractRecord]:
        """Normalize a bounded MarketData.app option chain.

        MarketData.app bills current option chains per returned contract and
        historical chains per 1,000 contracts.  The adapter therefore exposes
        the documented data faithfully, while the provider policy keeps chain
        routing disabled until a response-dependent credit bound is supplied.
        """

        params: dict[str, Any] = {}
        if expiration is not None:
            params["expiration"] = expiration.isoformat()
        if max_symbols is not None:
            if (
                isinstance(max_symbols, bool)
                or not isinstance(max_symbols, int)
                or max_symbols < 2
            ):
                raise ProviderResponseError(
                    self.name,
                    "configured option-chain symbol bound must be an integer >= 2",
                )
            # Without a side filter, MarketData.app's documented
            # ``strikeLimit`` returns up to that many strikes on each side.
            # Halving the reviewed total-symbol bound keeps the request within
            # the reservation while retaining both calls and puts.
            params["strikeLimit"] = max_symbols // 2
        payload = self._get(f"options/chain/{symbol.upper()}/", params)
        rows = _parallel_option_rows(payload, self.name)
        if max_symbols is not None and len(rows) > max_symbols:
            raise ProviderResponseError(
                self.name,
                "provider returned more option symbols than the reviewed bound",
            )
        contracts: list[OptionContractRecord] = []
        for row in rows:
            parsed_expiration = _option_expiry(row["expiration"])
            right = _option_right(row["side"])
            strike = _checked_decimal(row["strike"], self.name, "option strike")
            if parsed_expiration is None or right is None or strike is None:
                # ``_parallel_option_rows`` already validates these values;
                # keep this guard local so a future helper change cannot
                # construct a partially identified contract.
                raise ProviderResponseError(self.name, "provider returned an invalid option contract")

            def checked(field: str) -> Decimal | None:
                return _checked_decimal(row.get(field), self.name, f"option {field}")

            contracts.append(
                OptionContractRecord(
                    provider_symbol=str(row["optionSymbol"]).strip(),
                    underlying_symbol=str(row["underlying"]).strip().upper(),
                    expiry_date=parsed_expiration,
                    strike=strike,
                    right=right,
                    currency="USD",
                    bid=checked("bid"),
                    ask=checked("ask"),
                    mark=checked("mid"),
                    last_price=checked("last"),
                    volume=checked("volume"),
                    open_interest=checked("openInterest"),
                    implied_vol=checked("iv"),
                    delta=checked("delta"),
                    gamma=checked("gamma"),
                    theta=checked("theta"),
                    vega=checked("vega"),
                    rho=checked("rho"),
                    observed_at=_timestamp(row.get("updated")),
                    raw_payload=dict(row),
                )
            )
        return sorted(
            contracts,
            key=lambda contract: (
                contract.expiry_date,
                contract.strike,
                contract.right,
                contract.provider_symbol,
            ),
        )

    def fetch_option_quote_history(
        self,
        symbol: str,
        *,
        start: datetime,
        end: datetime,
    ) -> list[OptionQuotePointRecord]:
        """Fetch current or end-of-day option quotes for one OCC contract.

        MarketData.app prices historical quote series per 1,000 observations
        and returns Greeks as null for historical requests. The provider's
        response-dependent charge is intentionally not assigned a guessed
        fixed operation cost; runtime routing stays fail-closed until an
        operator-reviewed reservation bound is supplied.
        """

        bounded_start = _bounded_datetime(start)
        bounded_end = _bounded_datetime(end)
        if bounded_end <= bounded_start:
            return []
        params: dict[str, Any]
        if bounded_start.date() == bounded_end.date():
            params = {"date": bounded_start.date().isoformat()}
        else:
            params = {
                "from": bounded_start.date().isoformat(),
                "to": bounded_end.date().isoformat(),
            }
        payload = self._get(f"options/quotes/{symbol.upper()}/", params)
        rows = _parallel_option_quote_rows(payload, self.name)
        points: list[OptionQuotePointRecord] = []
        for row in rows:
            observed_at = _timestamp(
                row["updated"], timezone_name="America/New_York"
            )
            if observed_at is None:
                raise ProviderResponseError(
                    self.name, "provider returned an option quote without a valid timestamp"
                )

            def checked(field: str) -> Decimal | None:
                return _checked_decimal(row.get(field), self.name, f"option quote {field}")

            if bounded_start <= observed_at < bounded_end:
                points.append(
                    OptionQuotePointRecord(
                        provider_symbol=str(row["optionSymbol"]).strip(),
                        observed_at=observed_at,
                        bid=checked("bid"),
                        ask=checked("ask"),
                        mark=checked("mid"),
                        last=checked("last"),
                        volume=checked("volume"),
                        open_interest=checked("openInterest"),
                        implied_vol=checked("iv"),
                        delta=checked("delta"),
                        gamma=checked("gamma"),
                        theta=checked("theta"),
                        vega=checked("vega"),
                        rho=checked("rho"),
                        raw_payload=dict(row),
                    )
                )
        return sorted(points, key=lambda point: point.observed_at)


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
        self._require_raw_history(adjusted)
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
        rows = _parallel_candle_rows(payload, self.name)
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
        rows = self._strict_rows(payload, self.name, "result")
        results: list[ProviderSearchResult] = []
        for row in rows:
            symbol = _required_text(row, self.name, "symbol", "symbol")
            results.append(
                ProviderSearchResult(
                    symbol=symbol.upper(),
                    name=str(row.get("description") or symbol),
                    exchange=str(row.get("mic") or ""),
                    instrument_type=str(row.get("type") or "EQUITY").upper(),
                )
            )
        return results[:limit]

    def fetch_instrument_events(self, symbol: str) -> list[InstrumentEventRecord]:
        rows = self._strict_rows(
            self._get("stock/earnings", {"symbol": symbol.upper()}), self.name
        )
        fetched_at = datetime.now(UTC)
        events: list[InstrumentEventRecord] = []
        for row in rows:
            event_time = _timestamp(row.get("date") or row.get("period"))
            if event_time is None:
                raise ProviderResponseError(
                    self.name, "provider returned an earnings row without a valid date"
                )
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
                    eps_estimate=_checked_decimal(
                        row.get("estimate", row.get("epsEstimate")), self.name, "earnings estimate"
                    ),
                    eps_actual=_checked_decimal(
                        row.get("actual", row.get("epsActual")), self.name, "earnings actual"
                    ),
                    eps_surprise=_checked_decimal(
                        row.get("surprise"), self.name, "earnings surprise"
                    ),
                    eps_surprise_pct=_checked_decimal(
                        row.get("surprisePercent"), self.name, "earnings surprise percent"
                    ),
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
        rows = self._strict_rows(
            self._get("calendar/earnings", params), self.name, "earningsCalendar"
        )
        events: list[MarketEventRecord] = []
        for row in rows:
            event_time = _timestamp(row.get("date"))
            if event_time is None:
                raise ProviderResponseError(
                    self.name, "provider returned an earnings-calendar row without a valid date"
                )
            event_date = event_time.date()
            symbol = _required_text(row, self.name, "symbol", "symbol").upper()
            if (start and event_date < start) or (end and event_date > end):
                continue
            event_key = f"finnhub:earnings_calendar:{symbol}:{event_date.isoformat()}"
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
        rows = self._strict_rows(
            self._get("stock/symbol", {"exchange": "US"}), self.name
        )
        filtered: list[dict[str, Any]] = []
        for row in rows:
            symbol = _required_text(row, self.name, "symbol", "symbol")
            kind = str(row.get("type") or "Common Stock").upper()
            inferred = "ETF" if "ETF" in kind else "EQUITY"
            if inferred != normalized:
                continue
            filtered.append(
                {
                    "symbol": symbol.upper(),
                    "longName": row.get("description") or symbol,
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
        self._require_raw_history(adjusted)
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
            rows = self._strict_rows(payload, self.name, "data")
            for row in rows:
                bar = self._bar(
                    row, timeframe, instrument_id=instrument_id, data_source_id=data_source_id
                )
                if bar and bounded_start <= bar.ts < bounded_end:
                    bars_by_timestamp[bar.ts] = bar

            pagination = payload.get("pagination") if isinstance(payload, dict) else None
            if not isinstance(pagination, dict):
                raise ProviderResponseError(
                    self.name, "provider omitted pagination metadata for an EOD page"
                )
            page_offset = _strict_int(
                pagination.get("offset", offset), self.name, "EOD pagination offset"
            )
            count = _strict_int(
                pagination.get("count", len(rows)), self.name, "EOD pagination count", minimum=1
            )
            total_value = pagination.get("total")
            total = (
                _strict_int(total_value, self.name, "EOD pagination total")
                if total_value is not None
                else None
            )
            page_limit = _strict_int(
                pagination.get("limit", _MARKETSTACK_POINTS_PER_REQUEST),
                self.name,
                "EOD pagination limit",
                minimum=1,
            )
            if total is not None and total < page_offset + count:
                raise ProviderResponseError(
                    self.name, "provider returned contradictory EOD pagination metadata"
                )
            next_offset = page_offset + count
            if next_offset <= offset:
                raise ProviderResponseError(
                    self.name, "provider returned non-progressing EOD pagination metadata"
                )
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
        exchange = str(getattr(settings, "MARKETSTACK_DISCOVERY_EXCHANGE", "") or "").strip().upper()
        if not exchange:
            raise ProviderNotConfiguredError(
                "marketstack universe discovery requires MARKETSTACK_DISCOVERY_EXCHANGE"
            )
        payload = self._get("tickers", {"exchange": exchange, "limit": 1000, "offset": offset})
        rows = self._strict_rows(payload, self.name, "data")
        quotes = []
        for row in rows:
            symbol = _required_text(row, self.name, "symbol", "symbol", "ticker").upper()
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
    _FUNDAMENTALS_BASE = "https://eodhd.com/api/v1.1"

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
        self._require_raw_history(adjusted)
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
            for row in self._strict_rows(payload, self.name)
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
        payload = self._get(
            f"fundamentals/{symbol.upper()}.US",
            {"filter": "General"},
            base_url=self._FUNDAMENTALS_BASE,
        )
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
        rows = self._strict_rows(
            self._get("exchange-symbol-list/US", {"fmt": "json"}), self.name
        )
        filtered = []
        for row in rows:
            symbol = _required_text(row, self.name, "symbol", "Code", "code").upper()
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
        self._require_raw_history(adjusted)
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
            for row in self._strict_rows(payload, self.name)
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
        rows = self._strict_rows(
            self._get("profile", {"symbol": symbol.upper()}), self.name
        )
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

    def fetch_market_events(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[MarketEventRecord]:
        """Normalize FMP's stable earnings-calendar rows.

        The stable endpoint returns one row per issuer/date and may include
        actual and estimated EPS/revenue fields.  Those provider-specific
        values remain in ``raw_payload`` because ``MarketEventRecord`` is the
        market-wide event contract; instrument-level persistence can enrich
        them later without discarding the source response.
        """

        params: dict[str, Any] = {}
        if start is not None:
            params["from"] = start.isoformat()
        if end is not None:
            params["to"] = end.isoformat()
        rows = self._strict_rows(self._get("earnings-calendar", params), self.name)
        events: list[MarketEventRecord] = []
        for row in rows:
            event_time = _timestamp(
                row.get("date")
                or row.get("earningsDate")
                or row.get("announcementDate")
            )
            if event_time is None:
                raise ProviderResponseError(
                    self.name, "provider returned an earnings-calendar row without a valid date"
                )
            event_date = event_time.date()
            symbol = _required_text(row, self.name, "symbol", "symbol").upper()
            if (start and event_date < start) or (end and event_date > end):
                continue
            events.append(
                MarketEventRecord(
                    event_type="earnings",
                    event_key=f"fmp:earnings_calendar:{symbol or 'market'}:{event_date.isoformat()}",
                    event_time=event_time,
                    effective_date=event_date,
                    title=f"FMP earnings calendar {symbol}".strip(),
                    source_version="earnings-calendar",
                    raw_payload=row,
                )
            )
        return events

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        normalized = quote_type.strip().upper()
        if normalized not in {"EQUITY", "ETF"} or offset < 0:
            return {"total": 0, "quotes": []}
        rows = self._strict_rows(self._get("stock-list"), self.name)
        filtered = []
        for row in rows:
            symbol = _required_text(row, self.name, "symbol", "symbol").upper()
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
