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
import time
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from hashlib import sha256
from math import ceil, isfinite
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from app.config import (
    provider_operation_byte_bounds,
    provider_required_operation_byte_bounds,
    settings,
)
from app.models.instrument_event import EventTimeHint, InstrumentEventType
from app.models.ohlcv import OHLCVBar, Timeframe
from app.providers.base import (
    InstrumentEventRecord,
    InstrumentProfile,
    ListingRecord,
    MarketEventRecord,
    OptionContractRecord,
    OptionQuotePointRecord,
    ProviderAccountUsage,
    ProviderAccountUsageDimension,
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
from app.providers.telemetry import observe_response, observe_sanitized_payload

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
_FMP_EOD_MAX_ROWS_PER_RESPONSE = 5000
# Keep every FMP daily-history request below the documented 5,000-row ceiling
# even if the requested date range contains a bar on every calendar day.
_FMP_EOD_MAX_CALENDAR_DAYS_PER_REQUEST = _FMP_EOD_MAX_ROWS_PER_RESPONSE - 500


def _tiingo_year_ranges(start: datetime, end: datetime) -> list[tuple[date, date]]:
    """Split an exclusive datetime range into gapless, inclusive calendar years.

    Tiingo EOD history accepts inclusive ``startDate``/``endDate`` values but
    publishes no response-row or response-byte cap. Keeping each HTTP response
    to at most one calendar year gives the app's per-response bandwidth
    reservation a bounded, auditable input while allowing arbitrarily old
    history to be collected over multiple requests.
    """

    bounded_start = _bounded_datetime(start)
    bounded_end = _bounded_datetime(end)
    if bounded_end <= bounded_start:
        return []
    first = bounded_start.date()
    last = (bounded_end - timedelta(microseconds=1)).date()
    ranges: list[tuple[date, date]] = []
    while first <= last:
        year_end = date(first.year, 12, 31)
        current_end = min(last, year_end)
        ranges.append((first, current_end))
        first = current_end + timedelta(days=1)
    return ranges


def estimate_tiingo_ohlcv_request_count(
    timeframe: Timeframe, start: datetime, end: datetime
) -> int | None:
    """Estimate Tiingo's exact HTTP count for its one-year EOD date chunks."""

    if timeframe not in {Timeframe.D1, Timeframe.W1, Timeframe.MN}:
        return None
    ranges = _tiingo_year_ranges(start, end)
    return len(ranges) if ranges else None


_MARKETSTACK_POINTS_PER_REQUEST = 100
_MARKETDATA_APP_CANDLES_PER_CREDIT = 1000
_FULL_DISCOVERY_CACHE_TTL_SECONDS = 300
_FULL_DISCOVERY_CACHE: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}


def _cached_full_discovery_rows(
    provider_name: str,
    credential: str,
    fetch: Any,
) -> list[dict[str, Any]]:
    """Reuse one full-catalogue response across pages without retaining secrets.

    EODHD and FMP expose full US catalogues rather than offset-aware discovery
    endpoints. The reconciliation service requests successive pages, so
    refetching the same catalogue for every offset would waste quota and could
    observe inconsistent snapshots mid-run. Scope the short-lived cache by
    provider and a one-way credential digest; callers still receive copies.
    """

    cache_key = (provider_name, sha256(str(credential).encode("utf-8")).hexdigest())
    now = time.monotonic()
    cached = _FULL_DISCOVERY_CACHE.get(cache_key)
    if cached is not None and now - cached[0] < _FULL_DISCOVERY_CACHE_TTL_SECONDS:
        return list(cached[1])
    rows = [dict(row) for row in fetch()]
    _FULL_DISCOVERY_CACHE[cache_key] = (now, rows)
    return [dict(row) for row in rows]


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
        return (
            datetime.fromtimestamp(raw, tz=UTC)
            if raw > 1_000_000_000
            else now + timedelta(seconds=max(0, raw))
        )
    return None


def _account_integer(
    payload: dict[str, Any],
    headers: dict[str, str],
    *,
    body_keys: tuple[str, ...],
    header_keys: tuple[str, ...],
    field: str,
    provider_name: str = "marketdata_app",
) -> int | None:
    """Read one provider-declared account counter without coercive defaults."""

    normalized_headers = {str(key).lower(): value for key, value in headers.items()}
    raw: Any = None
    source_present = False
    for key in body_keys:
        if key in payload:
            raw = payload[key]
            source_present = True
            break
    if not source_present:
        for key in header_keys:
            if key.lower() in normalized_headers:
                raw = normalized_headers[key.lower()]
                source_present = True
                break
    if not source_present or raw in (None, ""):
        return None
    if isinstance(raw, bool):
        raise ProviderResponseError(provider_name, f"provider returned an invalid account {field}")
    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, str) and raw.strip().lstrip("+-").isdigit():
        value = int(raw.strip())
    else:
        raise ProviderResponseError(provider_name, f"provider returned an invalid account {field}")
    if value < 0:
        raise ProviderResponseError(provider_name, f"provider returned an invalid account {field}")
    return value


def _account_reset_at(payload: dict[str, Any], headers: dict[str, str]) -> datetime | None:
    """Parse only the documented account reset representations."""

    for key in ("resetAt", "reset_at", "x-api-ratelimit-reset"):
        if key not in payload:
            continue
        raw = payload[key]
        if raw in (None, ""):
            return None
        if isinstance(raw, bool):
            raise ProviderResponseError(
                "marketdata_app", "provider returned an invalid account reset time"
            )
        if isinstance(raw, int | float):
            try:
                return datetime.fromtimestamp(float(raw), tz=UTC)
            except (TypeError, ValueError, OverflowError, OSError) as exc:
                raise ProviderResponseError(
                    "marketdata_app", "provider returned an invalid account reset time"
                ) from exc
        if isinstance(raw, str):
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ProviderResponseError(
                    "marketdata_app", "provider returned an invalid account reset time"
                ) from exc
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
        raise ProviderResponseError(
            "marketdata_app", "provider returned an invalid account reset time"
        )
    return _retry_at_from_headers({str(key).lower(): str(value) for key, value in headers.items()})


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


def _marketdata_app_calendar_days(start: datetime, end: datetime) -> int | None:
    """Return the inclusive date span sent to MarketData.app candle endpoints."""

    bounded_start = _bounded_datetime(start)
    bounded_end = _bounded_datetime(end)
    if bounded_end <= bounded_start:
        return None
    # The endpoint accepts calendar dates rather than timestamps.  A request
    # for a five-minute slice therefore still admits every candle in each
    # requested date.  Use the inclusive date span so the reservation cannot
    # under-account that provider-defined response shape.
    return max(1, (bounded_end.date() - bounded_start.date()).days + 1)


def _marketdata_app_candle_upper_bound(timeframe: Timeframe, calendar_days: int) -> int | None:
    """Return a documented-resolution upper bound for one date-span request."""

    if calendar_days <= 0:
        return None
    if timeframe is Timeframe.D1:
        return calendar_days
    if timeframe is Timeframe.W1:
        # Weekly candles are aligned to provider calendar weeks; a date span
        # that crosses both endpoints can therefore include one extra bucket.
        return max(1, ceil(calendar_days / 7) + 1)
    seconds = {
        Timeframe.M1: 60,
        Timeframe.M5: 300,
        Timeframe.M15: 900,
        Timeframe.H1: 3600,
    }.get(timeframe)
    if seconds is None:
        # MarketData.app's documented stock candle adapter does not map the
        # remaining platform timeframes.  Do not invent a cost for them.
        return None
    # The provider query is date-granular.  A full UTC day is a conservative
    # bound for any intraday session, including extended-hours responses.
    return calendar_days * ceil(86400 / seconds)


def estimate_marketdata_app_ohlcv_credit_count(
    timeframe: Timeframe, start: datetime, end: datetime
) -> int | None:
    """Estimate MarketData.app stock-candle credits for one history request.

    MarketData.app charges one credit per 1,000 returned stock candles.  The
    endpoint takes ``from``/``to`` dates, not timestamps, so the estimate is
    based on the inclusive requested dates and a full-day upper bound for
    intraday resolutions.  A missing/unsupported bound returns ``None`` so
    provider admission remains fail-closed instead of reverting to one credit.
    """

    calendar_days = _marketdata_app_calendar_days(start, end)
    if calendar_days is None:
        return None
    candle_upper_bound = _marketdata_app_candle_upper_bound(timeframe, calendar_days)
    if candle_upper_bound is None:
        return None
    return max(1, ceil(candle_upper_bound / _MARKETDATA_APP_CANDLES_PER_CREDIT))


def estimate_marketdata_app_latest_ohlcv_credit_count(
    timeframe: Timeframe, limit: int, *, now: datetime | None = None
) -> int | None:
    """Estimate credits for the adapter's date-granular latest-history read."""

    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        return None
    seconds = {
        Timeframe.M1: 60,
        Timeframe.M5: 300,
        Timeframe.M15: 900,
        Timeframe.H1: 3600,
        Timeframe.D1: 86400,
        Timeframe.W1: 604800,
    }.get(timeframe)
    if seconds is None:
        return None
    bounded_end = _bounded_datetime(now or datetime.now(UTC))
    bounded_start = bounded_end - timedelta(seconds=seconds * max(1, limit))
    return estimate_marketdata_app_ohlcv_credit_count(timeframe, bounded_start, bounded_end)


def estimate_marketdata_app_option_quote_history_credit_count(
    start: datetime, end: datetime
) -> int | None:
    """Estimate one contract's historical quote credits conservatively.

    MarketData.app bills historical option quotes at one credit per 1,000
    returned observations. The request is date-granular and a single contract
    can contribute at most one end-of-day observation per inclusive calendar
    day, so the inclusive date span is the reviewed upper bound. Invalid or
    reversed ranges remain unadmitted rather than falling back to an assumed
    one-credit request.
    """

    bounded_start = _bounded_datetime(start)
    bounded_end = _bounded_datetime(end)
    if bounded_end < bounded_start:
        return None
    span_days = max(1, (bounded_end.date() - bounded_start.date()).days + 1)
    return max(1, ceil(span_days / 1000))


def estimate_fmp_ohlcv_request_count(
    timeframe: Timeframe, start: datetime, end: datetime
) -> int | None:
    """Return the number of bounded FMP daily-history requests for a range.

    FMP's stable EOD endpoint caps a response at 5,000 rows. The adapter
    partitions longer ranges into 4,500-calendar-day windows, leaving a margin
    below that cap. Returning ``None`` for unsupported/invalid ranges keeps
    provider admission fail-closed instead of pretending one request is enough.
    """

    if timeframe is not Timeframe.D1:
        return None
    bounded_start = _bounded_datetime(start)
    bounded_end = _bounded_datetime(end)
    if bounded_end <= bounded_start:
        return None
    inclusive_calendar_days = (bounded_end.date() - bounded_start.date()).days + 1
    return max(1, ceil(inclusive_calendar_days / _FMP_EOD_MAX_CALENDAR_DAYS_PER_REQUEST))


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


def _required_text(row: dict[str, Any], provider_name: str, label: str, *keys: str) -> str:
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


def _checked_decimal(value: Any, provider_name: str, field: str) -> Decimal | None:
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
        row.get("option_type") or row.get("optionType") or row.get("type") or row.get("side")
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


def _parallel_stock_quote_rows(payload: Any, provider_name: str) -> list[dict[str, Any]]:
    """Expand MarketData.app's parallel delayed-stock-quote response.

    The quotes endpoint returns one array per field.  Treat a missing or
    mismatched array as a provider response error instead of silently pairing
    the wrong symbol with a price.  Optional quote fields are filled with
    ``None`` when the provider omits the whole column.
    """

    if not isinstance(payload, dict):
        raise ProviderResponseError(
            provider_name, "provider returned an invalid stock-quote object"
        )
    status = str(payload.get("s") or "").strip().lower()
    if status == "no_data":
        return []
    if status != "ok":
        raise ProviderResponseError(
            provider_name,
            f"provider returned an invalid stock-quote status: {status or '<missing>'}",
        )
    symbols = payload.get("symbol")
    if not isinstance(symbols, list):
        raise ProviderResponseError(
            provider_name, "provider returned an invalid stock-quote symbol array"
        )
    expected_length = len(symbols)
    fields = (
        "ask",
        "askSize",
        "bid",
        "bidSize",
        "mid",
        "last",
        "change",
        "changepct",
        "volume",
        "updated",
        "52weekHigh",
        "52weekLow",
    )
    arrays: dict[str, list[Any]] = {"symbol": symbols}
    for field in fields:
        value = payload.get(field)
        if value is None:
            arrays[field] = [None] * expected_length
        elif not isinstance(value, list) or len(value) != expected_length:
            raise ProviderResponseError(
                provider_name, f"provider returned a mismatched stock-quote {field} array"
            )
        else:
            arrays[field] = value

    rows: list[dict[str, Any]] = []
    for index, raw_symbol in enumerate(symbols):
        symbol = str(raw_symbol or "").strip().upper()
        if not symbol:
            raise ProviderResponseError(
                provider_name, "provider returned a stock quote without a symbol"
            )
        rows.append({field: values[index] for field, values in arrays.items()})
    return rows


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
        raise ProviderResponseError(
            provider_name, "provider returned an invalid option-chain object"
        )
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
            raise ProviderResponseError(
                provider_name, "provider returned an invalid option expiration"
            )
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
        raise ProviderResponseError(
            provider_name, "provider returned an invalid option-quote object"
        )
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
        raise ProviderResponseError(
            provider_name, "provider returned mismatched option-quote arrays"
        )
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
        if (
            not str(row["optionSymbol"] or "").strip()
            or _timestamp(row["updated"], timezone_name="America/New_York") is None
        ):
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

    def _response_byte_bound(self, operation: str | None) -> int | None:
        if self.name not in {"fmp", "tiingo"}:
            return None
        if not operation:
            raise ProviderNotConfiguredError(
                f"{self.name} requests require an explicit operation for response-byte admission"
            )
        required = provider_required_operation_byte_bounds(self.name)
        bounds = provider_operation_byte_bounds(self.name)
        bound = bounds.get(operation)
        if operation not in required or bound is None:
            raise ProviderNotConfiguredError(
                f"{self.name}/{operation} requires a positive configured bound in "
                f"{self.name.upper()}_OPERATION_BYTE_BOUNDS"
            )
        return bound

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
        operation: str | None = None,
        not_found_is_empty: bool = False,
        not_found_payload_status: str | None = None,
    ) -> Any:
        payload, _ = self._get_with_headers(
            path,
            params,
            base_url=base_url,
            operation=operation,
            not_found_is_empty=not_found_is_empty,
            not_found_payload_status=not_found_payload_status,
        )
        return payload

    def _get_with_headers(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        base_url: str | None = None,
        operation: str | None = None,
        follow_redirects: bool = False,
        not_found_is_empty: bool = False,
        not_found_payload_status: str | None = None,
        capture_response_payload: bool | None = None,
    ) -> tuple[Any, dict[str, str]]:
        """Return one documented JSON response plus safe capacity headers.

        Most adapters only need the decoded payload, so ``_get`` preserves
        that compact contract.  Provider account endpoints are different:
        their quota snapshot is carried in response headers as well as the
        body.  Keeping this helper here makes that metadata available without
        exposing authentication headers or changing every adapter method.
        """

        response_byte_bound = self._response_byte_bound(operation)
        if self.key_setting and not self._key():
            raise ProviderNotConfiguredError(
                f"{self.name} requires {self.key_setting}; configure it before routing"
            )
        try:
            request_options: dict[str, Any] = {
                "params": self._auth_params(params),
                "headers": self._auth_headers(),
                "timeout": 30,
            }
            if follow_redirects:
                request_options["follow_redirects"] = True
            response = httpx.get(
                f"{(base_url or self.base_url).rstrip('/')}/{path.lstrip('/')}",
                **request_options,
            )
            observe_response(response, capture_response_payload=capture_response_payload)
            headers = provider_response_headers(response)
            if not_found_is_empty and response.status_code == 404:
                return None, headers
            if response.status_code == 404 and not_found_payload_status:
                try:
                    not_found_payload = response.json()
                except (TypeError, ValueError):
                    not_found_payload = None
                if (
                    isinstance(not_found_payload, dict)
                    and str(not_found_payload.get("s") or "").strip().lower()
                    == not_found_payload_status.strip().lower()
                ):
                    return not_found_payload, headers
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _raise_http_error(self.name, exc)
        except httpx.RequestError as exc:
            raise ProviderResponseError(self.name, redact_provider_message(str(exc))) from exc
        if response_byte_bound is not None:
            content = getattr(response, "content", None)
            if isinstance(content, bytes | bytearray) and len(content) > response_byte_bound:
                raise ProviderResponseError(
                    self.name,
                    f"{operation} response exceeded its configured "
                    f"{response_byte_bound}-byte bound; "
                    "the complete response was rejected without truncation",
                )
        try:
            payload = response.json()
        except (TypeError, ValueError) as exc:
            raise ProviderResponseError(self.name, "provider returned invalid JSON") from exc
        if not isinstance(payload, dict | list):
            raise ProviderResponseError(self.name, "provider returned an invalid JSON shape")
        raise_for_provider_error_envelope(self.name, payload, response.status_code, headers=headers)
        return payload, headers

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
            raise ProviderResponseError(
                provider_name, "provider returned an invalid row-list shape"
            )
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
            provenance={
                "provider": self.name,
                "provider_payload": row,
            },
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
        seconds = _TF_SECONDS.get(timeframe)
        if seconds is None:
            raise ProviderResponseError(
                self.name, f"{self.name} does not support timeframe {timeframe.value}"
            )
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

    def _fetch_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        *,
        adjusted: bool = True,
        instrument_id: int | None = None,
        data_source_id: int | None = None,
        operation: str,
    ) -> list[OHLCVBar]:
        self._require_raw_history(adjusted)
        resample = self._RESAMPLE.get(timeframe)
        if not resample:
            raise ProviderResponseError(
                self.name, f"{self.name} does not support timeframe {timeframe.value}"
            )
        bounded_start = _bounded_datetime(start)
        bounded_end = _bounded_datetime(end)
        if bounded_end <= bounded_start:
            return []
        bars: list[OHLCVBar] = []
        for first_date, last_date in _tiingo_year_ranges(bounded_start, bounded_end):
            payload = self._get(
                f"tiingo/daily/{symbol.upper()}/prices",
                {
                    "startDate": first_date.isoformat(),
                    "endDate": last_date.isoformat(),
                    "resampleFreq": resample,
                },
                operation=operation,
            )
            rows = self._strict_rows(payload, self.name)
            bars.extend(
                self._bar(
                    row,
                    timeframe,
                    instrument_id=instrument_id,
                    data_source_id=data_source_id,
                )
                for row in rows
            )
        return sorted(
            [bar for bar in bars if bar and bounded_start <= bar.ts < bounded_end],
            key=lambda bar: bar.ts,
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
        return self._fetch_ohlcv(
            symbol,
            timeframe,
            start,
            end,
            adjusted=adjusted,
            instrument_id=instrument_id,
            data_source_id=data_source_id,
            operation="fetch_ohlcv",
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
        if limit <= 0:
            return []
        bars = self._fetch_ohlcv(
            symbol,
            timeframe,
            self.latest_window_start(timeframe, limit),
            datetime.now(UTC),
            adjusted=adjusted,
            instrument_id=instrument_id,
            data_source_id=data_source_id,
            operation="fetch_latest_ohlcv",
        )
        return bars[-limit:]

    def get_current_price(self, symbol: str) -> float | None:
        bars = self._fetch_ohlcv(
            symbol,
            Timeframe.D1,
            self.latest_window_start(Timeframe.D1, 1),
            datetime.now(UTC),
            adjusted=False,
            operation="get_current_price",
        )
        return float(bars[-1].close) if bars else None

    def search_instruments(self, query: str, *, limit: int = 10) -> list[ProviderSearchResult]:
        payload = self._get(
            "tiingo/utilities/search",
            {"query": query, "limit": min(limit, 100)},
            operation="search_instruments",
        )
        results: list[ProviderSearchResult] = []
        for row in self._strict_rows(payload, self.name):
            ticker = _required_text(row, self.name, "ticker", "ticker")
            results.append(
                ProviderSearchResult(
                    symbol=ticker.upper(),
                    name=str(row.get("name") or ticker),
                    exchange=str(row.get("exchangeCode") or ""),
                    instrument_type="EQUITY",
                    raw_payload=dict(row),
                )
            )
        return results[:limit]

    def get_instrument_profile(self, symbol: str) -> InstrumentProfile | None:
        payload = self._get(f"tiingo/daily/{symbol.upper()}", operation="get_instrument_profile")
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

    @staticmethod
    def _usage_header_integer(headers: dict[str, str], name: str) -> int | None:
        raw = headers.get(name) or headers.get(name.title())
        if raw in (None, ""):
            return None
        if isinstance(raw, bool) or not str(raw).strip().lstrip("+-").isdigit():
            raise ProviderResponseError(
                "twelve_data", f"provider returned an invalid {name} account counter"
            )
        value = int(str(raw).strip())
        if value < 0:
            raise ProviderResponseError(
                "twelve_data", f"provider returned an invalid {name} account counter"
            )
        return value

    @staticmethod
    def _usage_payload_integer(payload: dict[str, Any], name: str) -> int | None:
        raw = payload.get(name)
        if raw is None:
            return None
        if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
            raise ProviderResponseError(
                "twelve_data", f"provider returned an invalid {name} account counter"
            )
        return raw

    def fetch_account_usage(self) -> ProviderAccountUsage | None:
        """Read Twelve Data's documented API-credit usage endpoint.

        Twelve Data documents ``/api_usage`` as the real-time plan/usage
        surface and documents ``api-credits-used``/``api-credits-left``
        response headers. Its usage response also reports request counts in
        ``current_usage``/``plan_limit`` and (for Basic) optional
        ``daily_usage``/``plan_daily_limit`` fields. These are stored as
        request windows, separate from the weighted minute-credit pool. The
        documented probe cost is one API credit and one API request.
        """

        payload, headers = self._get_with_headers("api_usage")
        if not isinstance(payload, dict):
            raise ProviderResponseError(self.name, "provider returned an invalid API-usage object")
        plan = payload.get("plan_category", payload.get("plan"))
        if plan is not None and not isinstance(plan, str):
            raise ProviderResponseError(self.name, "provider returned an invalid account plan")
        used = self._usage_header_integer(headers, "api-credits-used")
        remaining = self._usage_header_integer(headers, "api-credits-left")
        if used is None or remaining is None:
            raise ProviderResponseError(
                self.name,
                "provider omitted documented api-credits-used/api-credits-left headers",
            )
        observed_at = datetime.now(UTC)
        reset_at = observed_at.replace(second=0, microsecond=0) + timedelta(minutes=1)
        limit = used + remaining
        if limit <= 0:
            raise ProviderResponseError(
                self.name, "provider returned an invalid zero API-credit limit"
            )
        dimension = ProviderAccountUsageDimension(
            name="credits_per_minute",
            unit="credits",
            limit=limit,
            remaining=remaining,
            consumed=used,
            reset_at=reset_at,
        )
        dimensions = [dimension]
        for usage_name, limit_name, dimension_name in (
            ("current_usage", "plan_limit", "requests_per_minute"),
            ("daily_usage", "plan_daily_limit", "requests_per_day"),
        ):
            consumed = self._usage_payload_integer(payload, usage_name)
            request_limit = self._usage_payload_integer(payload, limit_name)
            if consumed is None and request_limit is None:
                continue
            remaining_requests = (
                request_limit - consumed
                if request_limit is not None and consumed is not None and consumed <= request_limit
                else None
            )
            dimensions.append(
                ProviderAccountUsageDimension(
                    name=dimension_name,
                    unit="requests",
                    limit=request_limit,
                    remaining=remaining_requests,
                    consumed=consumed,
                    reset_at=(
                        observed_at.replace(hour=0, minute=0, second=0, microsecond=0)
                        + timedelta(days=1)
                        if dimension_name == "requests_per_day"
                        else reset_at
                    ),
                )
            )
        return ProviderAccountUsage(
            provider=self.name,
            observed_at=observed_at,
            unit="credits",
            limit=limit,
            remaining=remaining,
            consumed=used,
            reset_at=reset_at,
            account_plan=plan.strip() if isinstance(plan, str) and plan.strip() else None,
            dimensions=tuple(dimensions),
            raw_payload=payload,
            response_headers=headers,
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
        interval = self._INTERVAL.get(timeframe)
        if not interval:
            raise ProviderResponseError(
                self.name, f"{self.name} does not support timeframe {timeframe.value}"
            )
        if end <= start:
            return []
        bounded_start = _bounded_datetime(start)
        bounded_end = _bounded_datetime(end)
        bars_by_timestamp: dict[datetime, OHLCVBar] = {}
        cursor = bounded_start
        while cursor < bounded_end:
            chunk_end = min(
                bounded_end,
                cursor
                + timedelta(seconds=_TF_SECONDS[timeframe] * _TWELVE_DATA_POINTS_PER_REQUEST),
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
            request_timezone = (
                None if timeframe in {Timeframe.D1, Timeframe.W1, Timeframe.MN} else "UTC"
            )
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
                    raw_payload=dict(row),
                )
            )
        return results[:limit]

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        normalized = quote_type.strip().upper()
        if normalized not in {"EQUITY", "ETF"} or offset < 0:
            return {"total": 0, "quotes": []}
        # Twelve Data exposes a paged ``/stocks`` catalogue.  Always pass the
        # page and output-size explicitly: requesting the country catalogue
        # without those bounds can return the entire supported-symbol list,
        # which is neither a bounded live probe nor a safe per-refresh read.
        page_size = 500
        page_number = (offset // page_size) + 1
        type_filter = "ETF" if normalized == "ETF" else "Common Stock"
        payload = self._get(
            "stocks",
            {
                "country": "United States",
                "type": type_filter,
                "page": page_number,
                "outputsize": page_size,
            },
        )
        rows = self._strict_rows(payload, self.name, "data")
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
        # ``count`` is the provider's total for the filtered catalogue.  Do
        # not infer a total from the current page, which would make a complete
        # page look like an exhausted universe.  A missing count is a
        # malformed pagination response rather than permission to guess.
        if not isinstance(payload, dict):
            raise ProviderResponseError(self.name, "provider omitted the stocks pagination count")
        total = _strict_int(payload.get("count"), self.name, "stocks pagination count")
        if total < len(rows):
            raise ProviderResponseError(
                self.name, "provider returned contradictory stocks pagination metadata"
            )
        return {"total": total, "quotes": filtered[offset % page_size :]}

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
                raise ProviderResponseError(
                    "tradier", f"provider returned an invalid {container} row"
                )
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
            raise ProviderResponseError(
                self.name, f"{self.name} does not support timeframe {timeframe.value}"
            )
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
        rows = self._nested_rows(
            payload, "history", {"daily": "day", "weekly": "week", "monthly": "month"}[interval]
        )
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
                    raw_payload=dict(row),
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
            raise ProviderResponseError(
                "tradier", "provider returned an invalid expirations object"
            )
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
                raise ProviderResponseError(
                    "tradier", "provider returned an invalid expiration date"
                )
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
        return sorted(
            contracts,
            key=lambda contract: (
                contract.expiry_date,
                contract.strike,
                contract.right,
                contract.provider_symbol,
            ),
        )

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

    def fetch_account_usage(self) -> ProviderAccountUsage | None:
        """Read the authenticated account credit window and options entitlement.

        MarketData.app documents ``GET /user/`` as the account introspection
        endpoint.  It reports credit counters and the reset timestamp in
        ``x-api-ratelimit-*`` response headers, while the response body carries
        the options-data permission.  The currently observed endpoint also
        exposes request-limit and options fields in the body; both documented
        representations are accepted without inventing a plan or window.

        A 404 is the provider's documented "no account information" response
        and therefore returns ``None``.  This observation never enables
        routing; reviewed plan/limit settings remain the admission contract.
        """

        payload, headers = self._get_with_headers(
            "user/",
            base_url="https://api.marketdata.app",
            not_found_is_empty=True,
        )
        if payload is None:
            return None
        if not isinstance(payload, dict):
            raise ProviderResponseError(
                self.name, "provider returned an invalid account-usage object"
            )

        limit = _account_integer(
            payload,
            headers,
            body_keys=(
                "x-ratelimit-requests-limit",
                "requestsLimit",
                "creditLimit",
            ),
            header_keys=("x-api-ratelimit-limit",),
            field="limit",
        )
        remaining = _account_integer(
            payload,
            headers,
            body_keys=(
                "x-ratelimit-requests-remaining",
                "requestsRemaining",
                "creditsRemaining",
            ),
            header_keys=("x-api-ratelimit-remaining",),
            field="remaining",
        )
        # MarketData.app defines X-Api-Ratelimit-Consumed as the credit cost
        # of this request, not the account's cumulative usage. The current
        # window's cumulative use is exactly limit - remaining; keep the
        # per-request value in response_headers/raw evidence, but never seed
        # the account baseline from it.
        consumed = limit - remaining if limit is not None and remaining is not None else None
        options = payload.get("x-options-data-permissions")
        if options is None:
            options = payload.get("optionsDataPermissions")
        if options is not None and not isinstance(options, str):
            raise ProviderResponseError(
                self.name,
                "provider returned invalid options-data permissions",
            )
        if limit is None and remaining is None and consumed is None and options is None:
            raise ProviderResponseError(
                self.name,
                "provider omitted documented account-usage fields",
            )
        account_plan = payload.get("plan")
        if account_plan is not None and not isinstance(account_plan, str):
            raise ProviderResponseError(self.name, "provider returned invalid account plan")
        dimension = ProviderAccountUsageDimension(
            name="credits_per_day",
            unit="credits",
            limit=limit,
            remaining=remaining,
            consumed=consumed,
            reset_at=_account_reset_at(payload, headers),
        )
        return ProviderAccountUsage(
            provider=self.name,
            observed_at=datetime.now(UTC),
            unit="credits",
            limit=limit,
            remaining=remaining,
            consumed=consumed,
            reset_at=dimension.reset_at,
            options_data_permissions=options,
            account_plan=(
                account_plan.strip()
                if isinstance(account_plan, str) and account_plan.strip()
                else None
            ),
            dimensions=(dimension,),
            raw_payload=payload,
            response_headers=headers,
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
        resolution = {
            Timeframe.M1: "1",
            Timeframe.M5: "5",
            Timeframe.M15: "15",
            Timeframe.H1: "60",
            Timeframe.D1: "D",
            Timeframe.W1: "W",
        }.get(timeframe)
        if not resolution:
            raise ProviderResponseError(
                self.name, f"{self.name} does not support timeframe {timeframe.value}"
            )
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

    def get_current_price(self, symbol: str) -> float | None:
        """Return the latest provider quote without relying on a candle date.

        MarketData.app exposes delayed stock quotes separately from historical
        candles.  Using the quote endpoint is important on weekends, holidays,
        and for plans whose candle surface is at least one day delayed: a
        one-day candle request can legitimately return ``no_data`` even though
        the latest delayed quote is available.
        """

        normalized_symbol = str(symbol or "").strip().upper()
        if not normalized_symbol:
            return None
        payload = self._get(f"stocks/quotes/{normalized_symbol}/")
        rows = _parallel_stock_quote_rows(payload, self.name)
        row = next((item for item in rows if item["symbol"] == normalized_symbol), None)
        if row is None:
            return None

        # ``last`` is the provider's most recent trade.  Fall back to the
        # documented midpoint, then a one-sided quote, without fabricating a
        # value when every price field is null.
        for field in ("last", "mid"):
            value = _number(row.get(field))
            if value is not None:
                return float(value)
        bid = _number(row.get("bid"))
        ask = _number(row.get("ask"))
        if bid is not None and ask is not None:
            return float((bid + ask) / 2)
        if bid is not None:
            return float(bid)
        if ask is not None:
            return float(ask)
        return None

    def latest_window_start(self, timeframe: Timeframe, limit: int) -> datetime:
        seconds = _TF_SECONDS.get(timeframe)
        if seconds is None:
            raise ProviderResponseError(
                self.name, f"{self.name} does not support timeframe {timeframe.value}"
            )
        return datetime.now(UTC) - timedelta(seconds=seconds * max(1, limit))

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
            if isinstance(max_symbols, bool) or not isinstance(max_symbols, int) or max_symbols < 2:
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
                raise ProviderResponseError(
                    self.name, "provider returned an invalid option contract"
                )

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
        and returns Greeks as null for historical requests. Callers must use
        ``estimate_marketdata_app_option_quote_history_credit_count`` for the
        exact inclusive date range before reserving provider quota; no fixed
        one-request fallback is permitted.
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
        payload = self._get(
            f"options/quotes/{symbol.upper()}/",
            params,
            not_found_payload_status="no_data",
        )
        rows = _parallel_option_quote_rows(payload, self.name)
        points: list[OptionQuotePointRecord] = []
        for row in rows:
            observed_at = _timestamp(row["updated"], timezone_name="America/New_York")
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

    def fetch_account_usage(self) -> ProviderAccountUsage:
        """Bootstrap Finnhub's native per-minute counter from a quote response.

        Finnhub has no separate usage endpoint. Its documented rate-limit
        headers accompany normal responses, so use one small AAPL quote and
        retain the exact header values. The second-level ceiling is accounted
        for separately as an application-only shared rolling envelope; it is
        not misrepresented as a provider-reported usage counter.
        """

        payload, headers = self._get_with_headers(
            "quote", {"symbol": "AAPL"}, operation="fetch_account_usage"
        )
        if not isinstance(payload, dict) or _number(payload.get("c")) is None:
            raise ProviderResponseError(
                self.name, "provider returned an invalid quote for quota observation"
            )
        limit = _account_integer(
            {},
            headers,
            body_keys=(),
            header_keys=("x-ratelimit-limit", "ratelimit-limit"),
            field="minute request limit",
            provider_name=self.name,
        )
        remaining = _account_integer(
            {},
            headers,
            body_keys=(),
            header_keys=("x-ratelimit-remaining", "ratelimit-remaining"),
            field="minute requests remaining",
            provider_name=self.name,
        )
        if limit is None or remaining is None or limit <= 0 or remaining > limit:
            raise ProviderResponseError(
                self.name, "provider omitted or returned invalid minute rate-limit headers"
            )
        observed_at = datetime.now(UTC)
        reset_at = _retry_at_from_headers(headers)
        if reset_at is None:
            # The header exposes remaining capacity but no reset anchor. A
            # full rolling minute from this observation is the stricter local
            # admission horizon; it is not labelled as Finnhub's reset time.
            reset_at = observed_at + timedelta(seconds=60)
        if reset_at <= observed_at:
            raise ProviderResponseError(self.name, "provider returned a stale minute reset header")
        dimension = ProviderAccountUsageDimension(
            name="calls_per_minute",
            unit="requests",
            limit=limit,
            remaining=remaining,
            consumed=limit - remaining,
            reset_at=reset_at,
        )
        return ProviderAccountUsage(
            provider=self.name,
            observed_at=observed_at,
            unit="requests",
            limit=limit,
            remaining=remaining,
            consumed=limit - remaining,
            reset_at=reset_at,
            dimensions=(dimension,),
            raw_payload=dict(payload),
            response_headers=headers,
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
        resolution = self._RESOLUTION.get(timeframe)
        if not resolution:
            raise ProviderResponseError(
                self.name, f"{self.name} does not support timeframe {timeframe.value}"
            )
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

    def get_current_price(self, symbol: str) -> float | None:
        """Read Finnhub's native quote endpoint instead of its candle API."""

        payload = self._get("quote", {"symbol": symbol.upper()})
        if not isinstance(payload, dict):
            raise ProviderResponseError(self.name, "provider returned an invalid quote object")
        price = _number(payload.get("c"))
        if price is None:
            raise ProviderResponseError(self.name, "provider returned an invalid quote price")
        # Finnhub uses zero for the current-price field when no quote is
        # available for a symbol; preserve that as a no-observation result.
        return price if price > 0 else None

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
                    raw_payload=dict(row),
                )
            )
        return results[:limit]

    def fetch_instrument_events(self, symbol: str) -> list[InstrumentEventRecord]:
        rows = self._strict_rows(self._get("stock/earnings", {"symbol": symbol.upper()}), self.name)
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
        payload, _ = self._get_with_headers(
            "stock/symbol",
            {"exchange": "US"},
            operation="discover_universe_page",
            follow_redirects=True,
        )
        rows = self._strict_rows(payload, self.name)
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
        # Finnhub returns the complete US symbol directory in this one
        # response; it does not expose a server-side offset/page token. Do not
        # re-download that entire directory once per synthetic 500-row page.
        # Returning the remainder lets the universe reconciler persist every
        # row from the same response and terminate from the declared total.
        return {"total": len(filtered), "quotes": filtered[offset:]}

    def supported_discovery_types(self) -> list[str]:
        return ["EQUITY", "ETF"]


class MarketstackProvider(_RESTProvider):
    name = "marketstack"
    base_url = "https://api.marketstack.com/v2"
    description = "Marketstack optional US EOD history and venue-scoped ticker discovery"
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
            raise ProviderResponseError(
                self.name, f"{self.name} does not support timeframe {timeframe.value}"
            )
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
                pagination.get("count", len(rows)), self.name, "EOD pagination count", minimum=0
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
            if count == 0:
                # A zero-count page is a valid terminal response for an
                # empty symbol/range query. It is not valid evidence that a
                # positive declared result set has been exhausted: accepting
                # that contradiction would silently lose the remaining rows.
                if total is not None and page_offset < total:
                    raise ProviderResponseError(
                        self.name,
                        "provider returned an empty EOD page before its declared total",
                    )
                break
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
        exchange = (
            str(getattr(settings, "MARKETSTACK_DISCOVERY_EXCHANGE", "") or "").strip().upper()
        )
        if not exchange:
            raise ProviderNotConfiguredError(
                "marketstack universe discovery requires MARKETSTACK_DISCOVERY_EXCHANGE"
            )
        # Marketstack documents exchange-scoped listings as
        # /exchanges/{mic}/tickers.  Do not substitute an undocumented
        # `exchange` query parameter on /tickers: the path is the provider's
        # actual scope selector and keeps the selected MIC explicit.
        payload = self._get(f"exchanges/{exchange}/tickers", {"limit": 1000, "offset": offset})
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise ProviderResponseError(
                self.name,
                "provider returned an invalid exchange tickers data object",
            )
        # The V2 exchange-tickers endpoint returns exchange metadata in
        # ``data`` and the paginated ticker records in ``data.tickers``.
        # Treating ``data`` as a list (the shape used by several other
        # Marketstack endpoints) rejects the documented V2 response and would
        # make live universe discovery fail before archiving any page.
        rows = self._strict_rows(data, self.name, "tickers")
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
                    "exchange": data.get("mic") or exchange,
                    "currency": data.get("currency") or "USD",
                    "quoteType": inferred,
                    "status": "active",
                }
            )
        pagination = payload.get("pagination") if isinstance(payload, dict) else None
        if not isinstance(pagination, dict) or "total" not in pagination:
            raise ProviderResponseError(
                self.name,
                "provider omitted the tickers pagination total",
            )
        total = _strict_int(pagination["total"], self.name, "tickers pagination total")
        page_offset = _strict_int(
            pagination.get("offset", offset), self.name, "tickers pagination offset"
        )
        if page_offset != offset:
            raise ProviderResponseError(
                self.name,
                "provider returned a tickers pagination offset different from requested offset",
            )
        page_count = _strict_int(
            pagination.get("count", len(rows)),
            self.name,
            "tickers pagination count",
        )
        if page_count != len(rows):
            raise ProviderResponseError(
                self.name,
                "provider returned a tickers pagination count different from the raw page length",
            )
        if page_offset + page_count > total:
            raise ProviderResponseError(
                self.name,
                "provider returned tickers pagination metadata beyond its declared total",
            )
        next_offset = page_offset + page_count if page_offset + page_count < total else None
        return {
            "total": total,
            "total_scope": "raw",
            "quotes": quotes,
            # Preserve all provider fields and all asset types. The normalized
            # quote projection above is only for reconciliation; the archive
            # stores this complete response so name-based type classification
            # can never discard information returned by Marketstack.
            "raw_payload": payload,
            "next_offset": next_offset,
            "complete": next_offset is None,
        }

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

    def fetch_account_usage(self) -> ProviderAccountUsage | None:
        """Read EODHD's documented daily API-call usage snapshot.

        The User API reports the number of calls on the latest active usage
        date and the account's daily call limit. EODHD documents a midnight
        GMT reset and lazy zeroing on the first request after midnight. When
        the endpoint still reports a past usage date, that is evidence that
        the current day's charged usage is zero; preserve the last-active-day
        amount as a separate observation instead of confusing it with today's
        budget. The separate minute headers are observed against a strict
        local rolling window because EODHD publishes no reset timestamp.
        """

        payload, headers = self._get_with_headers("user")
        if not isinstance(payload, dict):
            raise ProviderResponseError(self.name, "provider returned an invalid user usage object")

        used = _account_integer(
            payload,
            headers,
            body_keys=("apiRequests",),
            header_keys=(),
            field="calls",
            provider_name=self.name,
        )
        daily_limit = _account_integer(
            payload,
            headers,
            body_keys=("dailyRateLimit",),
            header_keys=(),
            field="daily limit",
            provider_name=self.name,
        )
        usage_date_raw = payload.get("apiRequestsDate")
        if not isinstance(usage_date_raw, str) or not usage_date_raw.strip():
            raise ProviderResponseError(
                self.name, "provider omitted the documented apiRequestsDate field"
            )
        try:
            usage_date = date.fromisoformat(usage_date_raw.strip()[:10])
        except (TypeError, ValueError) as exc:
            raise ProviderResponseError(
                self.name, "provider returned an invalid apiRequestsDate field"
            ) from exc
        if (
            used is None
            or daily_limit is None
            or daily_limit <= 0
            or used > daily_limit
            or usage_date > datetime.now(UTC).date()
        ):
            raise ProviderResponseError(
                self.name, "provider returned invalid daily account-usage counters"
            )

        observed_at = datetime.now(UTC)
        current_day_used = used if usage_date == observed_at.date() else 0
        next_day = observed_at.date() + timedelta(days=1)
        reset_at = datetime(next_day.year, next_day.month, next_day.day, tzinfo=UTC)

        dimensions = [
            ProviderAccountUsageDimension(
                name="calls_per_day",
                unit="calls",
                limit=daily_limit,
                remaining=daily_limit - current_day_used,
                consumed=current_day_used,
                reset_at=reset_at,
            )
        ]
        if usage_date < observed_at.date():
            # The API's lazy daily counter still exposes its last active
            # date. Keep that historical usage rather than dropping it, while
            # the current-window zero above follows the documented GMT reset.
            dimensions.append(
                ProviderAccountUsageDimension(
                    name="calls_per_day_last_active",
                    unit="calls",
                    limit=daily_limit,
                    remaining=daily_limit - used,
                    consumed=used,
                )
            )
        # EODHD exposes ``extraLimit`` as a separate, non-expiring buffer
        # that is consumed only after the daily call allowance is exhausted.
        # It is a remaining balance, not a second daily limit: retain it as
        # its own observation-only dimension rather than folding it into
        # ``calls_per_day`` or inventing a reset boundary.
        extra_limit = _account_integer(
            payload,
            {},
            body_keys=("extraLimit",),
            header_keys=(),
            field="extra API-call balance",
            provider_name=self.name,
        )
        if extra_limit is not None:
            dimensions.append(
                ProviderAccountUsageDimension(
                    name="extra_calls",
                    unit="calls",
                    remaining=extra_limit,
                )
            )
        minute_limit = _account_integer(
            {},
            headers,
            body_keys=(),
            header_keys=("x-ratelimit-limit",),
            field="minute limit",
            provider_name=self.name,
        )
        minute_remaining = _account_integer(
            {},
            headers,
            body_keys=(),
            header_keys=("x-ratelimit-remaining",),
            field="minute remaining",
            provider_name=self.name,
        )
        if minute_limit is not None or minute_remaining is not None:
            if (
                minute_limit is None
                or minute_remaining is None
                or minute_limit <= 0
                or minute_remaining > minute_limit
            ):
                raise ProviderResponseError(
                    self.name, "provider returned incomplete minute rate-limit headers"
                )
            dimensions.append(
                ProviderAccountUsageDimension(
                    name="requests_per_minute",
                    unit="requests",
                    limit=minute_limit,
                    remaining=minute_remaining,
                    consumed=minute_limit - minute_remaining,
                    # The public docs expose current limit/remaining but no
                    # reset timestamp. Anchor a conservative local rolling
                    # observation window at this snapshot; this is not
                    # represented as a provider-supplied reset boundary.
                    reset_at=observed_at + timedelta(seconds=60),
                )
            )

        subscription_type = payload.get("subscriptionType")
        if subscription_type is not None and not isinstance(subscription_type, str):
            raise ProviderResponseError(self.name, "provider returned an invalid subscriptionType")
        return ProviderAccountUsage(
            provider=self.name,
            observed_at=observed_at,
            unit="calls",
            limit=daily_limit,
            remaining=daily_limit - current_day_used,
            consumed=current_day_used,
            reset_at=reset_at,
            account_plan=(
                subscription_type.strip()
                if isinstance(subscription_type, str) and subscription_type.strip()
                else None
            ),
            dimensions=tuple(dimensions),
            raw_payload=payload,
            response_headers=headers,
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
        period = self._PERIOD.get(timeframe)
        if not period:
            raise ProviderResponseError(
                self.name, f"{self.name} does not support timeframe {timeframe.value}"
            )
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

    def get_current_price(self, symbol: str) -> float | None:
        """Read EODHD's documented delayed real-time quote snapshot."""

        requested = symbol.strip().upper()
        ticker = requested if requested.endswith(".US") else f"{requested}.US"
        payload = self._get(
            f"real-time/{ticker}",
            {"fmt": "json"},
            operation="get_current_price",
        )
        rows = [payload] if isinstance(payload, dict) else self._strict_rows(payload, self.name)
        if not rows:
            return None
        matching = [
            row
            for row in rows
            if str(row.get("code") or row.get("symbol") or "").strip().upper()
            in {requested, ticker}
        ]
        if not matching:
            raise ProviderResponseError(
                self.name, "provider quote response omitted the requested symbol"
            )
        price = _number(matching[0].get("close"))
        if price is None or price <= 0:
            raise ProviderResponseError(self.name, "provider returned an invalid quote price")
        return price

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
        rows = _cached_full_discovery_rows(
            self.name,
            self._key(),
            lambda: self._strict_rows(
                self._get("exchange-symbol-list/US", {"fmt": "json"}), self.name
            ),
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
    _EARNINGS_PAGE_SIZE = 4_000
    _EARNINGS_MAX_RANGE_DAYS = 90

    def fetch_account_usage(self) -> ProviderAccountUsage | None:
        """Read FMP dashboard counters without persisting its credential-keyed envelope.

        FMP's dashboard currently exposes a first-party internal usage endpoint,
        not a documented public API. Keep its response parser narrow and its
        outer API-key-indexed object out of telemetry, logs, and persistence.
        The reset timestamps below are application safety-window anchors; the
        endpoint does not report provider-native reset timestamps.
        """

        plan = str(getattr(settings, "FMP_REVIEWED_PLAN", "basic") or "").strip().lower()
        plan_profiles = {
            "basic": ("calls_per_day", 250, 86_400, 500_000_000),
            "starter": ("calls_per_minute", 300, 60, 20_000_000_000),
            "premium": ("calls_per_minute", 750, 60, 50_000_000_000),
            "ultimate": ("calls_per_minute", 3_000, 60, 150_000_000_000),
        }
        profile = plan_profiles.get(plan)
        if profile is None:
            raise ProviderNotConfiguredError("FMP_REVIEWED_PLAN is unsupported")
        call_dimension, expected_call_limit, call_window, expected_bandwidth_limit = profile

        payload, headers = self._get_with_headers(
            "statistics/my-api-usage",
            {},
            base_url="https://cloud.financialmodelingprep.com",
            operation="fetch_account_usage",
            # The dashboard response's outer object key is the API secret.
            capture_response_payload=False,
        )
        key = self._key()
        if (
            not isinstance(payload, dict)
            or len(payload) != 1
            or key not in payload
            or not isinstance(payload.get(key), dict)
        ):
            raise ProviderResponseError(
                self.name, "provider returned an invalid account-usage envelope"
            )
        counters = payload[key]

        def exact_integer(field: str) -> int:
            value = counters.get(field)
            if isinstance(value, bool) or not isinstance(value, int | float | str):
                raise ProviderResponseError(
                    self.name, "provider returned invalid account-usage counters"
                )
            try:
                parsed = Decimal(str(value))
            except (InvalidOperation, ValueError):
                raise ProviderResponseError(
                    self.name, "provider returned invalid account-usage counters"
                ) from None
            if not parsed.is_finite() or parsed != parsed.to_integral_value() or parsed < 0:
                raise ProviderResponseError(
                    self.name, "provider returned invalid account-usage counters"
                )
            return int(parsed)

        def megabytes_to_conservative_bytes(field: str) -> tuple[Decimal, int]:
            value = counters.get(field)
            if isinstance(value, bool) or not isinstance(value, int | float | str):
                raise ProviderResponseError(
                    self.name, "provider returned invalid account-bandwidth counters"
                )
            try:
                parsed = Decimal(str(value))
            except (InvalidOperation, ValueError):
                raise ProviderResponseError(
                    self.name, "provider returned invalid account-bandwidth counters"
                ) from None
            if not parsed.is_finite() or parsed < 0:
                raise ProviderResponseError(
                    self.name, "provider returned invalid account-bandwidth counters"
                )
            # The dashboard labels these values MB but does not define decimal
            # versus binary units. Convert as MiB so usage is never understated.
            byte_count = int(
                (parsed * Decimal(1_048_576)).to_integral_value(rounding=ROUND_CEILING)
            )
            return parsed, byte_count

        current_calls = exact_integer("currentAPICount")
        reported_call_limit = exact_integer("rateLimit")
        if reported_call_limit != expected_call_limit or current_calls > reported_call_limit:
            raise ProviderResponseError(
                self.name, "provider account usage does not match the configured FMP plan"
            )
        data_usage_mb, consumed_bytes = megabytes_to_conservative_bytes("dataUsage")
        data_limit_mb, reported_bandwidth_limit = megabytes_to_conservative_bytes("dataUsageLimit")
        if (
            data_limit_mb <= 0
            or data_usage_mb > data_limit_mb
            or data_limit_mb * Decimal(1_000_000) < expected_bandwidth_limit
            or reported_bandwidth_limit < expected_bandwidth_limit
        ):
            raise ProviderResponseError(
                self.name, "provider account bandwidth does not match the configured FMP plan"
            )

        observed_at = datetime.now(UTC)
        call_limit = expected_call_limit
        call_reset_at = observed_at + timedelta(seconds=call_window)
        bandwidth_reset_at = observed_at + timedelta(days=30)
        dimensions = (
            ProviderAccountUsageDimension(
                name=call_dimension,
                unit="requests",
                limit=call_limit,
                remaining=call_limit - current_calls,
                consumed=current_calls,
                reset_at=call_reset_at,
            ),
            ProviderAccountUsageDimension(
                name="bandwidth_bytes_per_30_days",
                unit="bytes",
                limit=reported_bandwidth_limit,
                remaining=max(0, reported_bandwidth_limit - consumed_bytes),
                consumed=consumed_bytes,
                reset_at=bandwidth_reset_at,
            ),
        )
        safe_payload = {
            "configured_plan": plan,
            "currentAPICount": current_calls,
            "rateLimit": reported_call_limit,
            "dataUsage": str(data_usage_mb),
            "dataUsageLimit": str(data_limit_mb),
            "bandwidth_unit_conversion": "MiB_to_bytes_conservative",
        }
        observe_sanitized_payload(safe_payload)
        return ProviderAccountUsage(
            provider=self.name,
            observed_at=observed_at,
            unit="requests",
            limit=call_limit,
            remaining=call_limit - current_calls,
            consumed=current_calls,
            reset_at=call_reset_at,
            account_plan=plan,
            dimensions=dimensions,
            # Persist only validated counters. Never retain the credential-keyed
            # outer object or arbitrary fields returned by this undocumented API.
            raw_payload=safe_payload,
            response_headers=headers,
        )

    def _fetch_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        *,
        adjusted: bool = True,
        instrument_id: int | None = None,
        data_source_id: int | None = None,
        operation: str,
    ) -> list[OHLCVBar]:
        self._require_raw_history(adjusted)
        if timeframe is not Timeframe.D1:
            raise ProviderResponseError(
                self.name, f"{self.name} does not support timeframe {timeframe.value}"
            )
        bounded_start = _bounded_datetime(start)
        bounded_end = _bounded_datetime(end)
        if bounded_end <= bounded_start:
            return []

        # FMP's stable EOD endpoint returns at most 5,000 records. A single
        # wider request can therefore look successful while omitting older
        # history. Partition by calendar days below that provider cap and make
        # each HTTP request visible to the durable operation-cost reservation
        # supplied by market_data.py.
        first_date = bounded_start.date()
        last_date = bounded_end.date()
        bars: list[OHLCVBar] = []
        while first_date <= last_date:
            chunk_last_date = min(
                last_date,
                first_date + timedelta(days=_FMP_EOD_MAX_CALENDAR_DAYS_PER_REQUEST - 1),
            )
            payload = self._get(
                "historical-price-eod/full",
                {
                    "symbol": symbol.upper(),
                    "from": first_date.isoformat(),
                    "to": chunk_last_date.isoformat(),
                },
                operation=operation,
            )
            rows = self._strict_rows(payload, self.name)
            if len(rows) >= _FMP_EOD_MAX_ROWS_PER_RESPONSE:
                raise ProviderResponseError(
                    self.name,
                    "historical EOD response reached the provider row cap; "
                    "refusing potentially incomplete history",
                )
            bars.extend(
                self._bar(
                    row,
                    timeframe,
                    instrument_id=instrument_id,
                    data_source_id=data_source_id,
                )
                for row in rows
            )
            first_date = chunk_last_date + timedelta(days=1)

        return sorted(
            [bar for bar in bars if bar and bounded_start <= bar.ts < bounded_end],
            key=lambda bar: bar.ts,
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
        return self._fetch_ohlcv(
            symbol,
            timeframe,
            start,
            end,
            adjusted=adjusted,
            instrument_id=instrument_id,
            data_source_id=data_source_id,
            operation="fetch_ohlcv",
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
        if limit <= 0:
            return []
        bars = self._fetch_ohlcv(
            symbol,
            timeframe,
            self.latest_window_start(timeframe, limit),
            datetime.now(UTC),
            adjusted=adjusted,
            instrument_id=instrument_id,
            data_source_id=data_source_id,
            operation="fetch_latest_ohlcv",
        )
        return bars[-limit:]

    def get_current_price(self, symbol: str) -> float | None:
        """Read the documented stable quote endpoint for one stock."""

        rows = self._strict_rows(
            self._get("quote", {"symbol": symbol.upper()}, operation="get_current_price"),
            self.name,
        )
        if not rows:
            return None
        matching = [
            row for row in rows if str(row.get("symbol") or "").strip().upper() == symbol.upper()
        ]
        if not matching:
            raise ProviderResponseError(
                self.name, "provider quote response omitted the requested symbol"
            )
        price = _number(matching[0].get("price"))
        if price is None or price <= 0:
            raise ProviderResponseError(self.name, "provider returned an invalid quote price")
        return price

    def get_instrument_profile(self, symbol: str) -> InstrumentProfile | None:
        rows = self._strict_rows(
            self._get("profile", {"symbol": symbol.upper()}, operation="get_instrument_profile"),
            self.name,
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
        """Read a complete one-page earnings calendar or refuse a partial one.

        Durable ingestion uses ``fetch_market_events_page`` so each HTTP page
        is independently quota-reserved and persisted before continuation.
        This compatibility method must never return only page zero as if it
        were the complete calendar.
        """

        page = self.fetch_market_events_page(start=start, end=end, cursor=None)
        if not page["complete"]:
            raise ProviderResponseError(
                self.name,
                "FMP earnings calendar has more rows; use durable market-event pagination",
            )
        return page["events"]

    def fetch_market_events_page(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Fetch one documented FMP earnings page with durable continuation.

        FMP documents a maximum 90-day date range, a 4,000-record page, and a
        zero-based ``page`` parameter. The coordinator admits each page as a
        separate one-request operation; every page's raw response is retained
        before this method's cursor can advance.
        """

        if start is None or end is None:
            raise ProviderResponseError(
                self.name,
                "FMP earnings calendar pagination requires explicit start and end dates",
            )
        if start > end:
            raise ProviderResponseError(self.name, "earnings-calendar start is after end")
        if (end - start).days > self._EARNINGS_MAX_RANGE_DAYS:
            raise ProviderResponseError(
                self.name,
                "FMP earnings-calendar range exceeds the documented 90-day maximum",
            )
        if cursor is None:
            page_number = 0
        else:
            try:
                page_number = int(cursor)
            except (TypeError, ValueError) as exc:
                raise ProviderResponseError(
                    self.name, "invalid earnings-calendar page cursor"
                ) from exc
            if page_number < 0 or str(page_number) != str(cursor).strip():
                raise ProviderResponseError(self.name, "invalid earnings-calendar page cursor")

        rows = self._strict_rows(
            self._get(
                "earnings-calendar",
                {
                    "from": start.isoformat(),
                    "to": end.isoformat(),
                    "page": page_number,
                },
                operation="fetch_market_events",
            ),
            self.name,
        )
        if len(rows) > self._EARNINGS_PAGE_SIZE:
            raise ProviderResponseError(
                self.name,
                "FMP earnings-calendar page exceeded its documented 4,000-record maximum",
            )
        events: list[MarketEventRecord] = []
        for row in rows:
            event_time = _timestamp(
                row.get("date") or row.get("earningsDate") or row.get("announcementDate")
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
        next_cursor = str(page_number + 1) if len(rows) == self._EARNINGS_PAGE_SIZE else None
        return {
            "events": events,
            "next_cursor": next_cursor,
            "complete": next_cursor is None,
        }

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        normalized = quote_type.strip().upper()
        if normalized not in {"EQUITY", "ETF"} or offset < 0:
            return {"total": 0, "quotes": []}
        if not bool(getattr(settings, "FMP_STOCK_LIST_ENTITLED", False)):
            raise ProviderNotConfiguredError(
                "FMP stock-list discovery is disabled until this account's endpoint entitlement is confirmed"
            )
        rows = _cached_full_discovery_rows(
            self.name,
            self._key(),
            lambda: self._strict_rows(
                self._get("stock-list", operation="discover_universe_page"), self.name
            ),
        )
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
