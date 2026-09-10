"""Read-only Interactive Brokers Client Portal Gateway market-data adapter.

The Client Portal Gateway is deliberately treated as an operator-owned
session.  IBKR requires an interactive browser login to establish the session
cookie, so this adapter never attempts to automate authentication or silently
fall back to an unauthenticated endpoint.  It exposes only documented
read-only security search, historical bars, and latest-price snapshot calls.

Historical responses are bounded by the documented 1,000-point endpoint
ceiling.  When a request spans more than one response page, the adapter uses
the documented ``startTime``/``direction`` cursor and refuses to return a
partial series if the gateway does not make forward progress.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from math import ceil, isfinite
from typing import Any

import httpx

from app.config import settings
from app.models.ohlcv import TIMEFRAME_SECONDS, OHLCVBar, Timeframe
from app.providers.base import InstrumentProfile, ListingRecord, ProviderSearchResult
from app.providers.errors import (
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
    provider_response_headers,
    provider_retry_at_from_headers,
    raise_for_provider_error_envelope,
    redact_provider_message,
)
from app.providers.telemetry import observe_response

logger = logging.getLogger(__name__)

_MAX_POINTS = 1000
_MAX_HISTORY_YEARS = 15
_TIMEFRAME_TO_BAR: dict[Timeframe, str] = {
    Timeframe.M1: "1min",
    Timeframe.M5: "5min",
    Timeframe.M15: "15min",
    Timeframe.M30: "30min",
    Timeframe.H1: "1h",
    Timeframe.H2: "2h",
    Timeframe.H4: "4h",
    Timeframe.D1: "1d",
    Timeframe.W1: "1w",
    Timeframe.MN: "1m",
}
_PERIODS: tuple[tuple[timedelta, str], ...] = (
    (timedelta(days=1), "1d"),
    (timedelta(days=7), "1w"),
    (timedelta(days=31), "1m"),
    (timedelta(days=93), "3m"),
    (timedelta(days=186), "6m"),
    (timedelta(days=366), "1y"),
    (timedelta(days=366 * 2), "2y"),
    (timedelta(days=366 * 3), "3y"),
    (timedelta(days=366 * 5), "5y"),
    (timedelta(days=366 * 10), "10y"),
    (timedelta(days=366 * 15), "15y"),
)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _period_for_span(span: timedelta) -> str:
    for boundary, period in _PERIODS:
        if span <= boundary:
            return period
    return "15y"


def estimate_ibkr_ohlcv_request_count(
    timeframe: Timeframe, start: datetime, end: datetime
) -> int | None:
    """Return the conservative number of 1,000-point history pages."""

    seconds = TIMEFRAME_SECONDS.get(timeframe)
    if seconds is None or end <= start:
        return 0 if end <= start else None
    points = ceil((_as_utc(end) - _as_utc(start)).total_seconds() / seconds)
    return max(1, ceil(points / _MAX_POINTS))


def estimate_ibkr_latest_ohlcv_request_count(timeframe: Timeframe, limit: int) -> int | None:
    if timeframe not in _TIMEFRAME_TO_BAR or limit < 0:
        return None
    return 0 if limit == 0 else max(1, ceil(limit / _MAX_POINTS))


def estimate_ibkr_current_price_request_count(symbol: str) -> int:
    """Reserve conid resolution plus the documented account/snapshot pair."""

    term = str(symbol or "").strip()
    if term.isdigit() or term.upper() in (settings.IBKR_CONID_MAP or {}):
        return 2
    return 3


def _timestamp(value: Any) -> datetime | None:
    try:
        raw = float(value)
        if not isfinite(raw):
            return None
        # IBKR uses epoch milliseconds for historical ``t`` values.  Accept
        # seconds too because gateway versions have emitted both forms.
        if abs(raw) >= 100_000_000_000:
            raw /= 1000
        elif abs(raw) >= 10_000_000_000:
            # Some gateway versions have emitted a ten-times epoch value in
            # the operator-timezone field; normalize that documented field
            # representation without accepting arbitrary date strings.
            raw /= 10
        return datetime.fromtimestamp(raw, tz=UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _finite_number(value: Any, *, non_negative: bool = False) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not isfinite(number) or (non_negative and number < 0):
        return None
    return number


def _valid_conid(value: Any) -> bool:
    number = _finite_number(value, non_negative=True)
    return number is not None and number > 0 and number.is_integer()


def _snapshot_price(value: Any) -> float | None:
    """Normalize snapshot field 31, which may carry C/H state prefixes."""

    number = _finite_number(value)
    if number is not None:
        return number
    text = str(value or "").strip()
    if text[:1].upper() in {"C", "H"}:
        return _finite_number(text[1:])
    return None


class IBKRProvider:
    name = "ibkr"
    base_url = "https://api.ibkr.com"
    description = (
        "Interactive Brokers Client Portal Gateway read-only history, security "
        "metadata, and latest-price snapshots"
    )

    def _configured(self) -> tuple[str, str]:
        base_url = str(settings.IBKR_READ_ONLY_URL or "").strip().rstrip("/")
        cookie = str(settings.IBKR_READ_ONLY_SESSION_COOKIE or "").strip()
        if not base_url or not cookie:
            raise ProviderNotConfiguredError(
                "ibkr requires IBKR_READ_ONLY_URL and "
                "IBKR_READ_ONLY_SESSION_COOKIE; authenticate the Client Portal "
                "Gateway interactively before routing"
            )
        if not base_url.endswith("/v1/api"):
            base_url = f"{base_url}/v1/api"
        if cookie.lower().startswith("api="):
            cookie = cookie[4:]
        if not cookie:
            raise ProviderNotConfiguredError(
                "ibkr requires a non-empty IBKR_READ_ONLY_SESSION_COOKIE"
            )
        return base_url, cookie

    @staticmethod
    def _request_headers(cookie: str) -> dict[str, str]:
        # The cookie value is never included in an exception message or
        # provenance payload.  IBKR's gateway uses the ``api`` cookie name.
        return {"Cookie": f"api={cookie}", "Accept": "application/json"}

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
    ) -> Any:
        base_url, cookie = self._configured()
        url = f"{base_url}/{path.lstrip('/')}"
        try:
            response = httpx.request(
                method,
                url,
                params=params,
                json=json,
                headers=self._request_headers(cookie),
                timeout=float(settings.IBKR_READ_ONLY_TIMEOUT_SECONDS),
                verify=bool(settings.IBKR_READ_ONLY_VERIFY_TLS),
            )
            observe_response(response)
        except httpx.RequestError as exc:
            raise ProviderResponseError(self.name, redact_provider_message(str(exc))) from exc
        headers = provider_response_headers(response)
        if response.status_code in {418, 429}:
            raise ProviderRateLimitError(
                self.name,
                f"IBKR request rejected for pacing/capacity (HTTP {response.status_code})",
                retry_at=provider_retry_at_from_headers(headers),
                status_code=response.status_code,
                scope="authenticated_session",
                headers=headers,
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ProviderResponseError(
                self.name,
                f"IBKR request failed with HTTP {response.status_code}",
                status_code=response.status_code,
            ) from exc
        try:
            payload = response.json()
        except (TypeError, ValueError) as exc:
            raise ProviderResponseError(self.name, "IBKR returned invalid JSON") from exc
        try:
            raise_for_provider_error_envelope(
                self.name, payload, response.status_code, headers=headers
            )
        except ProviderResponseError as exc:
            # The gateway may return pacing/penalty-box messages in a 200 JSON
            # envelope rather than using HTTP 429. Preserve that distinction
            # so the runtime opens a capacity circuit instead of retrying it as
            # an ordinary malformed response.
            if any(
                marker in str(exc).lower()
                for marker in ("pacing", "penalty box", "rate limit", "too many request")
            ):
                raise ProviderRateLimitError(
                    self.name,
                    str(exc),
                    retry_at=provider_retry_at_from_headers(headers),
                    status_code=response.status_code,
                    scope="authenticated_session",
                    headers=headers,
                ) from exc
            raise
        if not isinstance(payload, dict | list):
            raise ProviderResponseError(self.name, "IBKR returned an invalid JSON shape")
        return payload

    @staticmethod
    def _rows(payload: Any, *, context: str) -> list[dict[str, Any]]:
        rows: Any = payload
        if isinstance(payload, dict):
            rows = payload.get("data", payload.get("results"))
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ProviderResponseError("ibkr", f"IBKR returned an invalid {context} row list")
        return rows

    def search_instruments(self, query: str, *, limit: int = 10) -> list[ProviderSearchResult]:
        term = str(query or "").strip()
        if not term:
            return []
        rows = self._rows(
            self._request("GET", "/iserver/secdef/search", params={"symbol": term}),
            context="security-search",
        )
        results: list[ProviderSearchResult] = []
        for row in rows[: max(0, min(limit, 50))]:
            symbol = str(row.get("symbol") or row.get("ticker") or "").strip().upper()
            conid = row.get("conid")
            name = str(row.get("companyName") or row.get("companyHeader") or symbol).strip()
            if not symbol or not name:
                continue
            if not _valid_conid(conid):
                continue
            results.append(
                ProviderSearchResult(
                    symbol=symbol,
                    name=name,
                    exchange=str(row.get("listingExchange") or row.get("exchange") or "").strip(),
                    instrument_type=str(row.get("assetClass") or "").strip(),
                )
            )
        return results

    def _search_rows(self, symbol: str) -> list[dict[str, Any]]:
        term = str(symbol or "").strip()
        rows = self._rows(
            self._request("GET", "/iserver/secdef/search", params={"symbol": term}),
            context="security-search",
        )
        normalized = term.upper()
        return [
            row
            for row in rows
            if str(row.get("symbol") or row.get("ticker") or "").strip().upper() == normalized
            and _valid_conid(row.get("conid"))
        ]

    def get_instrument_profile(self, symbol: str) -> InstrumentProfile | None:
        term = str(symbol or "").strip().upper()
        rows = self._search_rows(term)
        if not rows:
            return None
        if len(rows) > 1:
            raise ProviderResponseError(
                self.name,
                f"IBKR security search returned multiple exact listings for {term}; "
                "provide an explicit conid mapping",
            )
        row = rows[0]
        conid = int(float(row["conid"]))
        exchange = str(row.get("listingExchange") or row.get("exchange") or "").strip() or None
        currency = str(row.get("currency") or "USD").strip() or None
        return InstrumentProfile(
            provider=self.name,
            symbol=term,
            canonical_symbol=term,
            name=str(row.get("companyName") or row.get("companyHeader") or term).strip(),
            currency=currency,
            quote_type=str(row.get("assetClass") or "").strip() or None,
            exchange=exchange,
            listings=[
                ListingRecord(
                    provider_symbol=term,
                    exchange_code=exchange,
                    currency=currency,
                    provider_instrument_type=str(row.get("assetClass") or "").strip() or None,
                    is_primary=True,
                    extra_data={"conid": conid},
                )
            ],
            raw_payload=row,
            extra={"conid": conid, "description": row.get("description")},
        )

    def _resolve_conid(self, symbol: str) -> int:
        term = str(symbol or "").strip()
        try:
            numeric = int(term)
            if numeric > 0:
                return numeric
        except (TypeError, ValueError):
            pass
        configured = settings.IBKR_CONID_MAP or {}
        if isinstance(configured, dict):
            value = configured.get(term.upper())
            if value is not None:
                try:
                    numeric = float(value)
                    conid = int(numeric)
                    if numeric.is_integer() and conid > 0:
                        return conid
                except (TypeError, ValueError):
                    raise ProviderResponseError(self.name, f"invalid IBKR conid mapping for {term}")
        rows = self._search_rows(term)
        if len(rows) != 1:
            if not rows:
                raise ProviderResponseError(self.name, f"IBKR could not resolve security {term}")
            raise ProviderResponseError(
                self.name,
                f"IBKR security {term} is ambiguous; configure IBKR_CONID_MAP",
            )
        return int(float(rows[0]["conid"]))

    @staticmethod
    def _start_time(value: datetime) -> str:
        return _as_utc(value).strftime("%Y%m%d-%H:%M:%S")

    def _history_page(
        self,
        conid: int,
        timeframe: Timeframe,
        cursor: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        return self._rows(
            self._request(
                "GET",
                "/iserver/marketdata/history",
                params={
                    "conid": conid,
                    "period": _period_for_span(max(timedelta(0), end - cursor)),
                    "bar": _TIMEFRAME_TO_BAR[timeframe],
                    "startTime": self._start_time(cursor),
                    "direction": 1,
                    "source": "Last",
                    "outsideRth": "false",
                },
            ),
            context="historical-data",
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
        if timeframe not in _TIMEFRAME_TO_BAR:
            raise ProviderResponseError(self.name, f"IBKR does not support timeframe {timeframe.value}")
        if adjusted:
            raise ProviderResponseError(
                self.name,
                "IBKR historical bars are raw; request adjusted=False and apply "
                "the platform adjustment pipeline",
            )
        start = _as_utc(start)
        end = _as_utc(end)
        if end <= start:
            return []
        if end - start > timedelta(days=366 * _MAX_HISTORY_YEARS):
            raise ProviderResponseError(
                self.name,
                f"IBKR history request exceeds the documented {_MAX_HISTORY_YEARS}-year period ceiling",
            )
        conid = self._resolve_conid(symbol)
        cursor = start
        bars: dict[datetime, OHLCVBar] = {}
        max_pages = estimate_ibkr_ohlcv_request_count(timeframe, start, end) or 1
        # Weekends/holidays can make a page cover less wall-clock time than its
        # nominal point count; allow a bounded amount of extra cursor pages,
        # but never loop indefinitely on a broken gateway response.
        max_pages = max(1, max_pages + 10)
        for _ in range(max_pages):
            rows = self._history_page(conid, timeframe, cursor, end)
            if not rows:
                break
            page_bars: list[OHLCVBar] = []
            for row in rows:
                ts = _timestamp(row.get("t"))
                values = {
                    key: _finite_number(row.get(key), non_negative=key == "v")
                    for key in ("o", "h", "l", "c", "v")
                }
                if ts is None or any(value is None for value in values.values()):
                    raise ProviderResponseError(self.name, "IBKR returned a malformed historical bar")
                if not start <= ts < end:
                    continue
                page_bars.append(
                    OHLCVBar(
                        instrument_id=instrument_id,
                        data_source_id=data_source_id,
                        timeframe=timeframe,
                        ts=ts,
                        open=values["o"],
                        high=values["h"],
                        low=values["l"],
                        close=values["c"],
                        volume=values["v"],
                        is_adjusted=False,
                        adjustment_basis="raw",
                        adjustment_version="provider-native",
                        provenance={
                            "provider": self.name,
                            "endpoint": "/iserver/marketdata/history",
                            "conid": conid,
                            "provider_symbol": str(symbol).strip().upper(),
                            "raw_payload": row,
                        },
                    )
                )
            for bar in page_bars:
                bars[bar.ts] = bar
            if len(rows) < _MAX_POINTS:
                break
            latest = max((_timestamp(row.get("t")) for row in rows), default=None)
            if latest is None:
                raise ProviderResponseError(self.name, "IBKR history page has no usable timestamp")
            next_cursor = latest + timedelta(seconds=TIMEFRAME_SECONDS[timeframe])
            if next_cursor <= cursor:
                raise ProviderResponseError(self.name, "IBKR history cursor did not advance")
            cursor = next_cursor
            if cursor >= end:
                break
        else:
            raise ProviderResponseError(self.name, "IBKR history pagination exceeded its bounded page budget")
        return [bars[ts] for ts in sorted(bars)]

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
        return self.fetch_ohlcv(
            symbol,
            timeframe,
            self.latest_window_start(timeframe, limit),
            datetime.now(UTC),
            adjusted=adjusted,
            instrument_id=instrument_id,
            data_source_id=data_source_id,
        )[-limit:]

    def latest_window_start(self, timeframe: Timeframe, limit: int) -> datetime:
        seconds = TIMEFRAME_SECONDS.get(timeframe)
        if seconds is None:
            raise ProviderResponseError(self.name, f"IBKR does not support timeframe {timeframe.value}")
        return datetime.now(UTC) - timedelta(seconds=max(1, limit) * seconds * 1.5 + 86400)

    def get_current_price(self, symbol: str) -> float | None:
        conid = self._resolve_conid(symbol)
        # IBKR requires the account context to be initialized before a market
        # data snapshot.  Keep this compound operation explicit and observable.
        accounts = self._request("GET", "/iserver/accounts")
        if not isinstance(accounts, dict | list):
            raise ProviderResponseError(self.name, "IBKR returned an invalid account context")
        payload = self._request(
            "GET",
            "/iserver/marketdata/snapshot",
            params={"conids": str(conid), "fields": "31"},
        )
        if isinstance(payload, list) and payload and payload[0] is None:
            return None
        rows = self._rows(payload, context="market-snapshot")
        if not rows:
            return None
        value = _snapshot_price(rows[0].get("31"))
        if value is None:
            raise ProviderResponseError(self.name, "IBKR snapshot omitted a finite last price (field 31)")
        return value
