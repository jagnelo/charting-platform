"""Keyless Frankfurter adapter for daily foreign-exchange reference rates.

Frankfurter (https://frankfurter.dev/docs) publishes daily mid-market
reference rates collected from central banks and other official sources. The
adapter uses the current v2 API (``https://api.frankfurter.dev/v2``; v1 is
deprecated upstream) and its *blended* rates, which Frankfurter documents as
its own calculation and free to use, including commercially. Direct
per-source endpoints (``/v2/providers/{key}/...``) remain subject to each
source's terms and are deliberately not used. Frankfurter publishes no
numeric quota, rate-limits only against abuse, and explicitly encourages
storing daily observations locally.

Symbol convention
    Canonical and provider symbols are the six-letter ISO 4217 pair
    ``<BASE><QUOTE>`` without a separator, for example ``EURUSD`` or
    ``USDJPY``. The value is the number of ``QUOTE`` units for one ``BASE``
    unit. This is the format parsed by
    ``instrument_mastering._parse_forex_pair``; ``EUR/USD``, ``EUR-USD`` and
    Yahoo-style ``EURUSD=X`` inputs are normalised to the same pair.

Discovery
    ``CURRENCY`` discovery emits every non-legacy fiat currency listed by
    ``/v2/currencies`` against USD, plus the 21 crosses among EUR, GBP, JPY,
    CHF, AUD, CAD and NZD. Each pair uses the interbank quoting convention
    EUR > GBP > AUD > NZD > USD > CAD > CHF > JPY > everything else, so the
    feed yields ``EURUSD``/``GBPUSD``/``AUDUSD``/``NZDUSD`` but ``USDJPY``,
    ``USDCHF``, ``USDCAD`` and ``USD<XXX>`` for every other currency.
    Metals and crypto assets in the same listing are excluded. FX has no
    exchange MIC; rows carry the non-MIC venue label ``Frankfurter`` (the
    crypto adapters use their exchange name the same way), which the listing
    catalogue intentionally does not resolve to an exchange.

History
    Only ``D1`` is served. Each bar is one daily reference fixing:
    open = high = low = close = rate, no volume. Blended rates also exist on
    Saturdays and Sundays because a few sources publish then; those are
    dropped so the series follows the Monday-Friday FX trading week. Long
    ranges are split into ten-year requests for a single pair.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta
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
    redact_provider_message,
)
from app.providers.telemetry import observe_response

FRANKFURTER_BASE_URL = "https://api.frankfurter.dev/v2"

# A single-pair ten-year range is about 3,650 JSON rows (weekends included
# upstream), a modest response. The docs state no maximum range; bounding each
# request keeps responses small and makes the reservation estimate exact.
_MAX_DAYS_PER_REQUEST = 3653
_DISCOVERY_PAGE_SIZE = 500
_CURRENCY_CODE = re.compile(r"^[A-Z]{3}$")
# Interbank quoting priority; currencies not listed rank after JPY.
_QUOTING_PRIORITY = ("EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF", "JPY")
_MAJOR_CROSS_CURRENCIES = ("EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD")
_DISCOVERY_VENUE = "Frankfurter"


def parse_frankfurter_pair(symbol: str) -> tuple[str, str] | None:
    """Return ``(base, quote)`` for a six-letter currency pair, else ``None``."""

    normalized = str(symbol or "").strip().upper()
    if normalized.endswith("=X"):
        normalized = normalized[:-2]
    for separator in ("/", "-", "_", " "):
        normalized = normalized.replace(separator, "")
    if len(normalized) != 6:
        return None
    base, quote = normalized[:3], normalized[3:]
    if not (_CURRENCY_CODE.fullmatch(base) and _CURRENCY_CODE.fullmatch(quote)):
        return None
    if base == quote:
        return None
    return base, quote


def _quoting_rank(code: str) -> int:
    try:
        return _QUOTING_PRIORITY.index(code)
    except ValueError:
        return len(_QUOTING_PRIORITY)


def market_convention_pair(first: str, second: str) -> tuple[str, str]:
    """Orient two currencies by the interbank quoting priority."""

    if _quoting_rank(second) < _quoting_rank(first):
        return second, first
    return first, second


def _requested_days(start: datetime, end: datetime) -> tuple[date, date] | None:
    """Return the inclusive dates whose 00:00 UTC bar lies in ``[start, end)``."""

    start_utc = start.astimezone(UTC) if start.tzinfo else start.replace(tzinfo=UTC)
    end_utc = end.astimezone(UTC) if end.tzinfo else end.replace(tzinfo=UTC)
    first_day = start_utc.date()
    if datetime.combine(first_day, time.min, tzinfo=UTC) < start_utc:
        first_day += timedelta(days=1)
    last_day = end_utc.date()
    if datetime.combine(last_day, time.min, tzinfo=UTC) >= end_utc:
        last_day -= timedelta(days=1)
    if last_day < first_day:
        return None
    return first_day, last_day


def _latest_window_days(limit: int) -> int:
    # Five bars per calendar week plus a fortnight of holiday/publication slack.
    return ceil(max(limit, 1) * 7 / 5) + 14


def estimate_frankfurter_ohlcv_request_count(
    timeframe: Timeframe, start: datetime, end: datetime
) -> int | None:
    """Return the exact number of ten-year ``/v2/rates`` requests for a range."""

    if timeframe != Timeframe.D1:
        return None
    days = _requested_days(start, end)
    if days is None:
        return 0
    first_day, last_day = days
    return ceil(((last_day - first_day).days + 1) / _MAX_DAYS_PER_REQUEST)


def estimate_frankfurter_latest_ohlcv_request_count(timeframe: Timeframe, limit: int) -> int | None:
    if limit <= 0:
        return 0
    if timeframe != Timeframe.D1:
        return None
    # The adapter's window spans at most ``days + 1`` calendar dates.
    return max(1, ceil((_latest_window_days(limit) + 1) / _MAX_DAYS_PER_REQUEST))


def _require_raw_history(provider_name: str, adjusted: bool) -> None:
    if adjusted:
        raise ProviderResponseError(
            provider_name,
            f"{provider_name} reference rates are raw; request adjusted=False",
        )


def _require_daily(provider_name: str, timeframe: Timeframe) -> None:
    if timeframe != Timeframe.D1:
        raise ProviderResponseError(
            provider_name, f"unsupported reference-rate timeframe: {timeframe}"
        )


def _error_message(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except (TypeError, ValueError):
        return None
    if isinstance(payload, dict) and isinstance(payload.get("message"), str):
        message = redact_provider_message(payload["message"].strip())[:200]
        return message or None
    return None


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
        try:
            payload = response.json()
        except (TypeError, ValueError) as exc:
            raise ProviderResponseError(provider_name, "provider returned invalid JSON") from exc
        raise_for_provider_error_envelope(
            provider_name,
            payload,
            response.status_code,
            headers=provider_response_headers(response),
        )
        return payload
    except httpx.HTTPStatusError as exc:
        headers = provider_response_headers(exc.response)
        status_code = exc.response.status_code
        if status_code == 429:
            raise ProviderRateLimitError(
                provider_name,
                f"provider request rejected for capacity (HTTP {status_code})",
                retry_at=provider_retry_at_from_headers(headers),
                status_code=status_code,
                headers=headers,
            ) from exc
        detail = _error_message(exc.response)
        message = f"provider request failed with HTTP {status_code}"
        raise ProviderResponseError(
            provider_name,
            f"{message}: {detail}" if detail else message,
            status_code=status_code,
        ) from exc
    except httpx.RequestError as exc:
        raise ProviderResponseError(provider_name, str(exc)) from exc


def _rate_value(value: Any, provider_name: str) -> float:
    if isinstance(value, bool):
        raise ProviderResponseError(provider_name, "provider returned an invalid rate")
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ProviderResponseError(provider_name, "provider returned an invalid rate") from exc
    if not isfinite(parsed) or parsed <= 0:
        raise ProviderResponseError(provider_name, "provider returned an invalid rate")
    return parsed


def _rate_row(
    row: Any, provider_name: str, base: str, quote: str
) -> tuple[date, float, dict[str, Any]]:
    if not isinstance(row, dict):
        raise ProviderResponseError(provider_name, "provider returned a non-object rate row")
    if str(row.get("base") or "").upper() != base or str(row.get("quote") or "").upper() != quote:
        raise ProviderResponseError(
            provider_name, "provider returned a rate row for a different currency pair"
        )
    try:
        observed = date.fromisoformat(str(row.get("date") or ""))
    except ValueError as exc:
        raise ProviderResponseError(
            provider_name, "provider returned an invalid rate date"
        ) from exc
    return observed, _rate_value(row.get("rate"), provider_name), row


class FrankfurterProvider:
    name = "frankfurter"
    base_url = FRANKFURTER_BASE_URL
    description = (
        "Frankfurter keyless daily FX reference rates (blended central-bank mid rates) "
        "and currency list"
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
        _require_raw_history(self.name, adjusted)
        _require_daily(self.name, timeframe)
        pair = parse_frankfurter_pair(symbol)
        if pair is None:
            # Not a currency pair: there is nothing to ask this source for.
            return []
        days = _requested_days(start, end)
        if days is None:
            return []
        base, quote = pair
        provider_symbol = f"{base}{quote}"
        first_day, last_day = days
        bars_by_day: dict[date, OHLCVBar] = {}
        chunk_start = first_day
        while chunk_start <= last_day:
            chunk_end = min(last_day, chunk_start + timedelta(days=_MAX_DAYS_PER_REQUEST - 1))
            payload = _get_json(
                self.name,
                f"{self.base_url}/rates",
                params={
                    "base": base,
                    "quotes": quote,
                    "from": chunk_start.isoformat(),
                    "to": chunk_end.isoformat(),
                },
                timeout=30,
            )
            if not isinstance(payload, list):
                raise ProviderResponseError(self.name, "provider returned an invalid rates array")
            for row in payload:
                observed, rate, raw = _rate_row(row, self.name, base, quote)
                # Frankfurter carries the last observation before ``from``
                # into a range response; keep only the requested dates, and
                # only Monday-Friday fixings.
                if not chunk_start <= observed <= chunk_end or observed.weekday() >= 5:
                    continue
                bars_by_day[observed] = OHLCVBar(
                    instrument_id=instrument_id,
                    data_source_id=data_source_id,
                    timeframe=timeframe,
                    ts=datetime.combine(observed, time.min, tzinfo=UTC),
                    open=rate,
                    high=rate,
                    low=rate,
                    close=rate,
                    volume=None,
                    vwap=None,
                    is_adjusted=False,
                    adjustment_basis="raw",
                    adjustment_version="provider-native",
                    provenance={
                        "provider": self.name,
                        "endpoint": "/v2/rates",
                        "provider_symbol": provider_symbol,
                        "rate_kind": "blended_daily_reference_mid",
                        "provider_payload": raw,
                    },
                )
            chunk_start = chunk_end + timedelta(days=1)
        return [bars_by_day[day] for day in sorted(bars_by_day)]

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
        _require_daily(self.name, timeframe)
        end = datetime.now(UTC)
        return self.fetch_ohlcv(
            symbol,
            timeframe,
            end - timedelta(days=_latest_window_days(limit)),
            end,
            adjusted=adjusted,
            instrument_id=instrument_id,
            data_source_id=data_source_id,
        )[-limit:]

    def latest_window_start(self, timeframe: Timeframe, limit: int) -> datetime:
        _require_daily(self.name, timeframe)
        return datetime.now(UTC) - timedelta(days=_latest_window_days(limit))

    def get_current_price(self, symbol: str) -> float | None:
        pair = parse_frankfurter_pair(symbol)
        if pair is None:
            return None
        base, quote = pair
        payload = _get_json(self.name, f"{self.base_url}/rate/{base}/{quote}", timeout=15)
        _, rate, _ = _rate_row(payload, self.name, base, quote)
        return rate

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        if quote_type.upper() != "CURRENCY":
            return {"total": 0, "quotes": []}
        payload = _get_json(self.name, f"{self.base_url}/currencies", timeout=30)
        if not isinstance(payload, list):
            raise ProviderResponseError(self.name, "provider returned an invalid currencies array")
        currencies: dict[str, dict[str, Any]] = {}
        for item in payload:
            if not isinstance(item, dict):
                raise ProviderResponseError(self.name, "provider returned a non-object currency")
            if item.get("type") != "currency":
                continue
            code = str(item.get("iso_code") or "").strip().upper()
            if not _CURRENCY_CODE.fullmatch(code):
                raise ProviderResponseError(
                    self.name, "provider returned an incomplete currency identity"
                )
            currencies[code] = item
        if "USD" not in currencies:
            raise ProviderResponseError(self.name, "provider currency list omitted USD")

        pairs: set[tuple[str, str]] = {
            market_convention_pair(code, "USD") for code in currencies if code != "USD"
        }
        majors = [code for code in _MAJOR_CROSS_CURRENCIES if code in currencies]
        for index, first in enumerate(majors):
            for second in majors[index + 1 :]:
                pairs.add(market_convention_pair(first, second))
        ordered = sorted(pairs, key=lambda pair: pair[0] + pair[1])
        page = ordered[offset : offset + _DISCOVERY_PAGE_SIZE]
        next_offset = offset + len(page) if offset + len(page) < len(ordered) else None
        return {
            "total": len(ordered),
            "next_offset": next_offset,
            "complete": next_offset is None,
            "quotes": [self._discovery_row(base, quote, currencies) for base, quote in page],
        }

    def supported_discovery_types(self) -> list[str]:
        return ["CURRENCY"]

    @staticmethod
    def _discovery_row(
        base: str, quote: str, currencies: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        base_name = str(currencies[base].get("name") or base).strip() or base
        quote_name = str(currencies[quote].get("name") or quote).strip() or quote
        return {
            "symbol": f"{base}{quote}",
            "longName": f"{base_name} / {quote_name}",
            "exchange": _DISCOVERY_VENUE,
            "quoteType": "CURRENCY",
            "currency": quote,
            "base_currency": base,
            "quote_currency": quote,
            "status": "active",
            "source_record": {"base": currencies[base], "quote": currencies[quote]},
        }
