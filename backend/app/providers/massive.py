"""Massive (formerly Polygon) reference-data provider.

This adapter is deliberately limited to the free-source reference role: ticker
search, paged US ticker discovery, and one-page IPO-calendar reads.  It is
supplementary evidence for the canonical security master, not a default
market-data path and not a promise of consolidated real-time data.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from app.config import settings
from app.providers.base import MarketEventRecord, ProviderSearchResult
from app.providers.errors import (
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
    provider_response_headers,
    raise_for_provider_error_envelope,
)
from app.providers.telemetry import observe_response

logger = logging.getLogger(__name__)

_BASE = "https://api.massive.com"
_TICKERS_PATH = "/v3/reference/tickers"
_IPOS_PATH = "/vX/reference/ipos"
_MARKET_HOLIDAYS_PATH = "/v1/marketstatus/upcoming"
_PAGE_SIZE = 1000


class MassiveProvider:
    name = "massive"
    base_url = _BASE
    description = "Massive reference tickers for US security-master corroboration"

    def __init__(self) -> None:
        self._cursor_by_page: dict[int, str] = {}

    def _api_key(self) -> str:
        # MARKETDATA_API_KEY is retained as a deployment-compatible alias.
        return settings.MASSIVE_API_KEY or settings.MARKETDATA_API_KEY

    def _params(self, **values: Any) -> dict[str, Any]:
        return {
            key: value
            for key, value in {"apiKey": self._api_key(), **values}.items()
            if value is not None
        }

    def _get_path(self, path: str, params: dict[str, Any]) -> dict[str, Any] | list[Any] | None:
        if not self._api_key():
            raise ProviderNotConfiguredError(
                "massive requires MASSIVE_API_KEY (or MARKETDATA_API_KEY)"
            )
        try:
            response = httpx.get(f"{_BASE}{path}", params=params, timeout=20)
        except httpx.RequestError as exc:
            raise ProviderResponseError(self.name, str(exc)) from exc
        observe_response(response)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            message = f"HTTP {response.status_code}: {exc}"
            if response.status_code == 429:
                raise ProviderRateLimitError(
                    self.name,
                    message,
                    status_code=response.status_code,
                    headers=provider_response_headers(response),
                ) from exc
            raise ProviderResponseError(
                self.name, message, status_code=response.status_code
            ) from exc
        try:
            payload = response.json()
        except (TypeError, ValueError) as exc:
            raise ProviderResponseError(self.name, "Massive returned invalid JSON") from exc
        raise_for_provider_error_envelope(
            self.name, payload, response.status_code, headers=provider_response_headers(response)
        )
        if not isinstance(payload, dict | list):
            raise ProviderResponseError(self.name, "Massive returned an invalid response container")
        return payload

    def _get(self, params: dict[str, Any]) -> dict[str, Any] | None:
        """Read the legacy ticker endpoint (kept for compatibility with callers/tests)."""

        payload = self._get_path(_TICKERS_PATH, params)
        if not isinstance(payload, dict):
            raise ProviderResponseError(self.name, "Massive ticker endpoint returned an invalid object")
        return payload

    @staticmethod
    def _rows(payload: dict[str, Any], operation: str) -> list[dict[str, Any]]:
        rows = payload.get("results", [])
        if not isinstance(rows, list):
            raise ProviderResponseError("massive", f"Massive {operation} returned an invalid results array")
        if any(not isinstance(row, dict) for row in rows):
            raise ProviderResponseError("massive", f"Massive {operation} returned a malformed row")
        return rows

    def search_instruments(self, query: str, *, limit: int = 10) -> list[ProviderSearchResult]:
        needle = query.strip()
        if not needle or limit <= 0:
            return []
        payload = self._get(
            self._params(
                search=needle,
                market="stocks",
                locale="us",
                active="true",
                limit=min(limit, 100),
                sort="ticker",
                order="asc",
            )
        )
        return [self._result(row) for row in self._rows(payload, "search")[:limit]]

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        if quote_type.strip().upper() not in {"EQUITY", "EQUITIES", "STOCK", "STOCKS"}:
            return {"total": 0, "quotes": []}
        page = max(offset, 0) // _PAGE_SIZE
        cursor = self._cursor_by_page.get(page)
        payload = self._get(
            self._params(
                market="stocks",
                locale="us",
                active="true",
                limit=_PAGE_SIZE,
                sort="ticker",
                order="asc",
                cursor=cursor,
            )
        )
        rows = self._rows(payload, "ticker discovery")
        quotes = [
            {
                "symbol": result.symbol,
                "name": result.name,
                "exchange": result.exchange,
                "instrument_type": result.instrument_type,
            }
            for result in (self._result(row) for row in rows)
        ]
        next_url = (payload or {}).get("next_url")
        next_cursor = _require_next_cursor(next_url, self.name, "ticker discovery")
        if next_cursor:
            self._cursor_by_page[page + 1] = next_cursor
        return {
            # Massive exposes cursor pagination rather than a global result
            # count. Do not mislabel each page length as the universe total;
            # the reconciliation worker follows ``next_url`` and accepts the
            # explicit final-page marker below.
            "total": None,
            "quotes": quotes,
            "next_url": next_url,
            "next_offset": offset + _PAGE_SIZE if next_url else None,
            "complete": not bool(next_url),
        }

    def supported_discovery_types(self) -> list[str]:
        return ["EQUITY"]

    def fetch_market_events(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
        status: str | None = None,
    ) -> list[MarketEventRecord]:
        """Return one bounded IPO-calendar page as normalized market events.

        Massive exposes cursor pagination.  The provider runtime charges one
        request for this operation, so this method intentionally does not
        follow ``next_url`` internally.  Callers that need a complete backfill
        should use :meth:`fetch_market_events_page` and account for every
        cursor page separately.
        """

        page = self.fetch_market_events_page(start=start, end=end, status=status)
        return page["events"]

    def fetch_market_events_page(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
        status: str | None = None,
        cursor: str | None = None,
        limit: int = _PAGE_SIZE,
    ) -> dict[str, Any]:
        """Fetch one Massive IPO page and expose its continuation cursor.

        Date bounds are applied locally because the endpoint's ``listing_date``
        filter is an exact-date filter, not a range filter.  The provider row
        is retained verbatim in each event's provenance payload.
        """

        if start and end and start > end:
            return {"events": [], "next_url": None, "complete": True}
        bounded_limit = max(1, min(int(limit), _PAGE_SIZE))
        params = self._params(
            limit=bounded_limit,
            sort="listing_date",
            order="asc",
            cursor=cursor,
            ipo_status=status.strip().lower() if status and status.strip() else None,
        )
        raw_payload = self._get_path(_IPOS_PATH, params)
        if not isinstance(raw_payload, dict):
            raise ProviderResponseError(self.name, "Massive IPO endpoint returned an invalid object")
        payload = raw_payload
        events = []
        for row in self._rows(payload, "IPO calendar"):
            event = self._ipo_event(row)
            if (start is None or event.effective_date >= start) and (
                end is None or event.effective_date <= end
            ):
                events.append(event)
        next_url = payload.get("next_url")
        _require_next_cursor(next_url, self.name, "IPO calendar")
        return {
            "events": events,
            "next_url": next_url,
            "complete": not isinstance(next_url, str) or not next_url,
        }

    def fetch_market_holidays(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[MarketEventRecord]:
        """Fetch Massive's forward market-holiday/early-close calendar.

        This is its own metered operation rather than being folded into the
        IPO call, so an IPO read never silently triggers a second upstream
        request.
        """

        if start and end and start > end:
            return []
        raw_payload = self._get_path(_MARKET_HOLIDAYS_PATH, self._params())
        if isinstance(raw_payload, list):
            rows = raw_payload
        elif isinstance(raw_payload, dict):
            rows = raw_payload.get("results", [])
        else:
            raise ProviderResponseError(self.name, "Massive market-holiday endpoint returned an invalid container")
        if not isinstance(rows, list):
            raise ProviderResponseError(self.name, "Massive market-holiday endpoint returned an invalid results array")
        if any(not isinstance(row, dict) for row in rows):
            raise ProviderResponseError(self.name, "Massive market-holiday endpoint returned a malformed row")
        events: list[MarketEventRecord] = []
        for row in rows:
            event_date = _parse_date(row.get("date"))
            if event_date is None:
                raise ProviderResponseError(
                    self.name, "Massive market-holiday endpoint returned an invalid date"
                )
            if (start and event_date < start) or (end and event_date > end):
                continue
            exchange = str(row.get("exchange") or "market").strip().upper()
            status = str(row.get("status") or "unknown").strip().lower()
            events.append(
                MarketEventRecord(
                    event_type="market_holiday",
                    event_key=f"massive:market_holiday:{exchange}:{event_date.isoformat()}:{status}",
                    event_time=_parse_datetime(row.get("open"))
                    or datetime.combine(event_date, datetime.min.time(), tzinfo=UTC),
                    effective_date=event_date,
                    title=str(row.get("name") or f"{exchange} {status}"),
                    source_version="v1/marketstatus/upcoming",
                    is_provisional=True,
                    raw_payload=dict(row),
                )
            )
        return events

    @staticmethod
    def _ipo_event(row: dict[str, Any]) -> MarketEventRecord:
        symbol = str(row.get("ticker") or "").strip().upper()
        stable_key = symbol or str(row.get("isin") or row.get("us_code") or "").strip()
        if not stable_key:
            raise ProviderResponseError("massive", "Massive IPO endpoint returned a row without an identity")
        effective_date = _parse_date(
            row.get("listing_date")
            or row.get("issue_start_date")
            or row.get("announced_date")
        )
        if effective_date is None:
            raise ProviderResponseError("massive", "Massive IPO endpoint returned a row without a valid date")
        status = str(row.get("ipo_status") or "").strip().lower()
        event_time = _parse_datetime(row.get("last_updated")) or datetime.combine(
            effective_date, datetime.min.time(), tzinfo=UTC
        )
        return MarketEventRecord(
            event_type="ipo",
            event_key=f"massive:ipo:{stable_key}:{effective_date.isoformat()}",
            event_time=event_time,
            effective_date=effective_date,
            title=str(row.get("issuer_name") or row.get("security_description") or stable_key),
            source_version="vX/reference/ipos",
            is_provisional=status not in {"history", "completed", "listed"},
            raw_payload=dict(row),
        )

    @staticmethod
    def _result(row: dict[str, Any]) -> ProviderSearchResult:
        if not isinstance(row, dict):
            raise ProviderResponseError("massive", "Massive ticker endpoint returned a malformed row")
        symbol = str(row.get("ticker") or "").strip().upper()
        if not symbol:
            raise ProviderResponseError("massive", "Massive ticker endpoint returned a row without a ticker")
        return ProviderSearchResult(
            symbol=symbol,
            name=str(row.get("name") or symbol),
            exchange=str(row.get("primary_exchange") or row.get("exchange") or ""),
            instrument_type=str(row.get("type") or "EQUITY").upper(),
        )


def _require_next_cursor(
    next_url: Any, provider_name: str, operation: str
) -> str | None:
    """Validate Massive's continuation URL and return its sole cursor.

    Massive's reference endpoints expose an opaque continuation URL, but the
    discovery adapter advances through it by extracting the documented
    ``cursor`` query parameter.  Treat a malformed URL or missing/ambiguous
    cursor as a provider-response failure instead of silently replaying the
    first page or claiming completion.
    """

    if next_url is None or next_url == "":
        return None
    if not isinstance(next_url, str):
        raise ProviderResponseError(
            provider_name, f"Massive {operation} returned an invalid next_url"
        )
    cursor_values = parse_qs(urlparse(next_url).query).get("cursor", [])
    if len(cursor_values) != 1 or not cursor_values[0].strip():
        raise ProviderResponseError(
            provider_name,
            f"Massive {operation} returned a next_url without one valid cursor",
        )
    return cursor_values[0]


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
