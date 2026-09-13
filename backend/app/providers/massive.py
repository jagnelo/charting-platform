"""Massive (formerly Polygon) US reference and historical-bars provider.

The free Stocks Basic plan is deliberately treated as a bounded, supplementary
source: it exposes US reference data and split-adjustable aggregate bars, but
only five API calls per minute and two years of history.  It is therefore not
made a default price-history route merely because an API key is configured.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from math import ceil, isfinite
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import httpx

from app.config import provider_positive_integer, settings
from app.models.instrument_event import EventTimeHint, InstrumentEventType
from app.models.ohlcv import OHLCVBar, Timeframe
from app.providers.base import (
    IdentifierRecord,
    InstrumentEventRecord,
    InstrumentProfile,
    ListingRecord,
    MarketEventRecord,
    ProviderSearchResult,
)
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
_TICKER_PROFILE_PATH_TEMPLATE = "/v3/reference/tickers/{ticker}"
_IPOS_PATH = "/vX/reference/ipos"
_MARKET_HOLIDAYS_PATH = "/v1/marketstatus/upcoming"
_SPLITS_PATH = "/stocks/v1/splits"
_DIVIDENDS_PATH = "/stocks/v1/dividends"
_AGGREGATES_PATH_TEMPLATE = "/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{start}/{end}"
_PAGE_SIZE = 1000
_AGGREGATE_PAGE_SIZE = 50_000

_TF_MAP: dict[Timeframe, tuple[int, str]] = {
    Timeframe.M1: (1, "minute"),
    Timeframe.M5: (5, "minute"),
    Timeframe.M15: (15, "minute"),
    Timeframe.M30: (30, "minute"),
    Timeframe.H1: (1, "hour"),
    Timeframe.H2: (2, "hour"),
    Timeframe.H4: (4, "hour"),
    Timeframe.H12: (12, "hour"),
    Timeframe.D1: (1, "day"),
    Timeframe.W1: (1, "week"),
    Timeframe.MN: (1, "month"),
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


class MassiveProvider:
    name = "massive"
    base_url = _BASE
    description = "Massive US reference data and bounded split-adjustable aggregate bars"

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
        """Fetch and normalize one bounded Massive custom-bars range.

        Massive's ``limit`` is a cap on base aggregates used to build the
        requested bars, not merely the number of returned rows.  The adapter
        therefore follows the provider's opaque cursor and validates its host
        before every continuation request.  No API key is ever copied into
        provenance or followed from a provider-supplied URL.
        """

        normalized_symbol = str(symbol or "").strip().upper()
        mapping = _TF_MAP.get(timeframe)
        start = _as_utc(start)
        end = _as_utc(end)
        if not normalized_symbol:
            raise ProviderResponseError(self.name, "Massive aggregate request requires a symbol")
        if mapping is None:
            raise ProviderResponseError(self.name, f"Massive does not support timeframe {timeframe.value}")
        if end <= start:
            return []

        multiplier, timespan = mapping
        path = _AGGREGATES_PATH_TEMPLATE.format(
            symbol=quote(normalized_symbol, safe="._-"),
            multiplier=multiplier,
            timespan=timespan,
            start=_epoch_millis(start),
            end=_epoch_millis(end),
        )
        params = {
            "adjusted": "true" if adjusted else "false",
            "sort": "asc",
            "limit": _AGGREGATE_PAGE_SIZE,
        }
        bars: dict[datetime, OHLCVBar] = {}
        next_path = path
        next_params: dict[str, Any] = params
        seen_cursors: set[str] = set()
        while True:
            payload = self._get_path(next_path, self._params(**next_params))
            if not isinstance(payload, dict):
                raise ProviderResponseError(self.name, "Massive aggregate endpoint returned an invalid object")
            provider_adjusted = payload.get("adjusted")
            if provider_adjusted is not None and provider_adjusted is not adjusted:
                raise ProviderResponseError(
                    self.name,
                    "Massive aggregate response adjustment flag did not match the request",
                )
            for row in self._rows(payload, "aggregate bars"):
                bar = self._aggregate_bar(
                    row,
                    timeframe=timeframe,
                    symbol=normalized_symbol,
                    adjusted=adjusted,
                    instrument_id=instrument_id,
                    data_source_id=data_source_id,
                    endpoint=next_path,
                    request_id=payload.get("request_id"),
                )
                if bar.ts < start or bar.ts >= end:
                    continue
                previous = bars.get(bar.ts)
                if previous is not None and (
                    previous.open != bar.open
                    or previous.high != bar.high
                    or previous.low != bar.low
                    or previous.close != bar.close
                    or previous.volume != bar.volume
                ):
                    raise ProviderResponseError(
                        self.name,
                        "Massive aggregate pagination returned conflicting duplicate timestamps",
                    )
                bars[bar.ts] = bar

            next_url = payload.get("next_url")
            if not next_url:
                break
            next_path, cursor = _aggregate_next_page(next_url, self.name)
            if cursor in seen_cursors:
                raise ProviderResponseError(self.name, "Massive aggregate pagination repeated a cursor")
            seen_cursors.add(cursor)
            next_params = {"cursor": cursor}

        return [bars[key] for key in sorted(bars)]

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
        bars = self.fetch_ohlcv(
            symbol,
            timeframe,
            self.latest_window_start(timeframe, limit),
            datetime.now(UTC),
            adjusted=adjusted,
            instrument_id=instrument_id,
            data_source_id=data_source_id,
        )
        return bars[-limit:]

    def latest_window_start(self, timeframe: Timeframe, limit: int) -> datetime:
        seconds = _TF_SECONDS.get(timeframe)
        if seconds is None:
            raise ProviderResponseError(self.name, f"Massive does not support timeframe {timeframe.value}")
        return datetime.now(UTC) - timedelta(seconds=seconds * max(1, limit) * 1.4 + 86400)

    @staticmethod
    def _aggregate_bar(
        row: dict[str, Any],
        *,
        timeframe: Timeframe,
        symbol: str,
        adjusted: bool,
        instrument_id: int | None,
        data_source_id: int | None,
        endpoint: str,
        request_id: Any,
    ) -> OHLCVBar:
        required = ("t", "o", "h", "l", "c")
        if any(field not in row for field in required):
            raise ProviderResponseError("massive", "Massive aggregate row is missing a required field")
        try:
            timestamp_ms = float(row["t"])
            values = {field: float(row[field]) for field in ("o", "h", "l", "c")}
            volume = float(row["v"]) if row.get("v") is not None else None
            vwap = float(row["vw"]) if row.get("vw") is not None else None
        except (TypeError, ValueError, OverflowError) as exc:
            raise ProviderResponseError("massive", "Massive aggregate row contains a non-numeric value") from exc
        if not isfinite(timestamp_ms) or timestamp_ms < 0 or timestamp_ms != int(timestamp_ms):
            raise ProviderResponseError("massive", "Massive aggregate row contains an invalid timestamp")
        if any(not isfinite(value) for value in values.values()):
            raise ProviderResponseError("massive", "Massive aggregate row contains a non-finite OHLC value")
        if volume is not None and (not isfinite(volume) or volume < 0):
            raise ProviderResponseError("massive", "Massive aggregate row contains an invalid volume")
        if vwap is not None and (not isfinite(vwap) or vwap < 0):
            raise ProviderResponseError("massive", "Massive aggregate row contains an invalid VWAP")
        if values["h"] < max(values["o"], values["c"]) or values["l"] > min(values["o"], values["c"]):
            raise ProviderResponseError("massive", "Massive aggregate row violates OHLC bounds")
        try:
            timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
        except (OverflowError, OSError, ValueError) as exc:
            raise ProviderResponseError("massive", "Massive aggregate row contains an invalid timestamp") from exc
        provenance = {
            "provider": "massive",
            "endpoint": endpoint,
            "provider_symbol": symbol,
            "adjusted": adjusted,
            "request_id": request_id,
            "provider_payload": dict(row),
        }
        return OHLCVBar(
            instrument_id=instrument_id,
            data_source_id=data_source_id,
            timeframe=timeframe,
            ts=timestamp,
            open=values["o"],
            high=values["h"],
            low=values["l"],
            close=values["c"],
            volume=volume,
            vwap=vwap,
            is_adjusted=adjusted,
            adjustment_basis="provider_adjusted" if adjusted else "raw",
            adjustment_version="massive-split-adjusted" if adjusted else "provider-native",
            provenance=provenance,
        )

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

    def get_instrument_profile(self, symbol: str) -> InstrumentProfile | None:
        """Return Massive's documentation-backed single-ticker overview.

        The overview is deliberately kept separate from the paginated ticker
        catalogue: it carries issuer metadata and stable identifiers that are
        not guaranteed to be present in every discovery row.  Optional fields
        are preserved in ``extra``/``raw_payload`` without coercing missing
        provider values into fabricated defaults.
        """

        normalized_symbol = str(symbol or "").strip().upper()
        if not normalized_symbol:
            return None
        payload = self._get_path(
            _TICKER_PROFILE_PATH_TEMPLATE.format(ticker=quote(normalized_symbol, safe="._-")),
            self._params(),
        )
        if not isinstance(payload, dict):
            raise ProviderResponseError(
                self.name, "Massive ticker overview returned an invalid response object"
            )
        row = payload.get("results")
        if row is None:
            return None
        if not isinstance(row, dict):
            raise ProviderResponseError(
                self.name, "Massive ticker overview returned an invalid results object"
            )
        provider_symbol = str(row.get("ticker") or "").strip().upper()
        if not provider_symbol:
            raise ProviderResponseError(
                self.name, "Massive ticker overview returned a row without a ticker"
            )
        if provider_symbol != normalized_symbol:
            raise ProviderResponseError(
                self.name,
                "Massive ticker overview returned a different ticker than requested",
            )

        active = row.get("active")
        if active is not None and not isinstance(active, bool):
            raise ProviderResponseError(
                self.name, "Massive ticker overview returned an invalid active flag"
            )
        type_code = _optional_text(row.get("type"))
        exchange = _optional_text(row.get("primary_exchange"))
        currency = _optional_text(row.get("currency_name"))
        currency = currency.upper() if currency else None
        known_at = _parse_datetime(row.get("last_updated_utc"))
        delisted_at = _parse_datetime(row.get("delisted_utc"))

        identifiers: list[IdentifierRecord] = []
        for field, identifier_type in (
            ("cik", "CIK"),
            ("composite_figi", "COMPOSITE_FIGI"),
            ("share_class_figi", "SHARE_CLASS_FIGI"),
        ):
            value = _optional_text(row.get(field))
            if value:
                identifiers.append(
                    IdentifierRecord(
                        identifier_type=identifier_type,
                        identifier_value=value,
                        is_primary=identifier_type == "COMPOSITE_FIGI",
                        source=self.name,
                    )
                )

        listing = ListingRecord(
            provider_symbol=provider_symbol,
            exchange_code=exchange,
            currency=currency,
            provider_instrument_type=type_code,
            is_primary=True,
            known_at=known_at,
            delisted_at=delisted_at,
            extra_data={"active": active},
        )
        extra = {
            key: row[key]
            for key in (
                "market",
                "locale",
                "ticker_root",
                "ticker_suffix",
                "market_cap",
                "sic_code",
                "sic_description",
                "total_employees",
                "weighted_shares_outstanding",
                "branding",
            )
            if key in row
        }
        extra.update(
            {
                "active": active,
                "last_updated_utc": row.get("last_updated_utc"),
                "delisted_utc": row.get("delisted_utc"),
            }
        )
        return InstrumentProfile(
            provider=self.name,
            symbol=provider_symbol,
            canonical_symbol=provider_symbol,
            name=_optional_text(row.get("name")) or provider_symbol,
            description=_optional_text(row.get("description")),
            currency=currency,
            quote_type=type_code,
            exchange=exchange,
            identifiers=identifiers,
            listings=[listing],
            raw_payload=dict(row),
            extra=extra,
        )

    def fetch_instrument_events(self, symbol: str) -> list[InstrumentEventRecord]:
        """Normalize Massive's documented split and dividend history.

        The provider exposes two independently paginated endpoints, so one
        platform event read can consume up to two times the reviewed page
        bound.  A missing bound is an intentional fail-closed result; callers
        must not turn the two HTTP requests (or an opaque continuation) into a
        guessed one-request charge.
        """

        normalized_symbol = str(symbol or "").strip().upper()
        if not normalized_symbol:
            return []
        max_pages = provider_positive_integer(
            getattr(settings, "MASSIVE_CORPORATE_ACTIONS_MAX_PAGES", 0)
        )
        if max_pages is None:
            raise ProviderNotConfiguredError(
                "massive corporate actions require a positive "
                "MASSIVE_CORPORATE_ACTIONS_MAX_PAGES bound"
            )

        fetched_at = datetime.now(UTC)
        events: list[InstrumentEventRecord] = []
        for row in self._fetch_corporate_action_rows(
            _SPLITS_PATH,
            normalized_symbol,
            max_pages=max_pages,
            sort="execution_date.desc",
        ):
            events.append(self._split_event(row, normalized_symbol, fetched_at))
        for row in self._fetch_corporate_action_rows(
            _DIVIDENDS_PATH,
            normalized_symbol,
            max_pages=max_pages,
            sort="ex_dividend_date.desc",
        ):
            events.extend(self._dividend_events(row, normalized_symbol, fetched_at))
        return sorted(events, key=lambda event: (event.event_time, event.source_event_key))

    def _fetch_corporate_action_rows(
        self,
        path: str,
        symbol: str,
        *,
        max_pages: int,
        sort: str,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        next_path = path
        next_params: dict[str, Any] = self._params(
            ticker=symbol,
            limit=5000,
            sort=sort,
        )
        seen_cursors: set[str] = set()
        for page_index in range(max_pages):
            payload = self._get_path(next_path, next_params)
            if not isinstance(payload, dict):
                raise ProviderResponseError(
                    self.name, "Massive corporate-actions endpoint returned an invalid object"
                )
            rows.extend(self._rows(payload, "corporate actions"))
            next_url = payload.get("next_url")
            if not next_url:
                return rows
            next_path, cursor = _corporate_actions_next_page(next_url, self.name, path)
            if cursor in seen_cursors:
                raise ProviderResponseError(
                    self.name, "Massive corporate-actions pagination repeated a cursor"
                )
            seen_cursors.add(cursor)
            if page_index + 1 >= max_pages:
                raise ProviderResponseError(
                    self.name,
                    "Massive corporate-actions page bound reached before pagination completed",
                )
            next_params = self._params(cursor=cursor)
        raise ProviderResponseError(self.name, "Massive corporate-actions page bound is invalid")

    def _split_event(
        self, row: dict[str, Any], symbol: str, fetched_at: datetime
    ) -> InstrumentEventRecord:
        provider_symbol = _optional_text(row.get("ticker"))
        if provider_symbol and provider_symbol.upper() != symbol:
            raise ProviderResponseError(
                self.name, "Massive split returned a different ticker than requested"
            )
        execution_date = _required_action_date(row.get("execution_date"), self.name, "execution_date")
        adjustment_type = _optional_text(row.get("adjustment_type"))
        if adjustment_type not in {"forward_split", "reverse_split", "stock_dividend"}:
            raise ProviderResponseError(self.name, "Massive split returned an invalid adjustment_type")
        split_from = _optional_action_decimal(row.get("split_from"), self.name, "split_from")
        split_to = _optional_action_decimal(row.get("split_to"), self.name, "split_to")
        if (split_from is None) != (split_to is None):
            raise ProviderResponseError(self.name, "Massive split returned only one ratio component")
        if split_from is not None and (split_from <= 0 or split_to <= 0):
            raise ProviderResponseError(self.name, "Massive split returned a non-positive ratio component")
        split_ratio = split_to / split_from if split_from is not None and split_to is not None else None
        source_id = _optional_text(row.get("id"))
        source_key = source_id or (
            f"{adjustment_type}:{execution_date.isoformat()}:{split_from}:{split_to}"
        )
        return InstrumentEventRecord(
            event_type=InstrumentEventType.SPLIT,
            event_time=datetime.combine(execution_date, datetime.min.time(), tzinfo=UTC),
            time_hint=EventTimeHint.UNKNOWN,
            title=f"{adjustment_type.replace('_', ' ').title()} {symbol}",
            source_event_key=f"massive:split:{symbol}:{source_key}",
            fetched_at=fetched_at,
            split_ratio=split_ratio,
            raw_payload=str(row),
        )

    def _dividend_events(
        self, row: dict[str, Any], symbol: str, fetched_at: datetime
    ) -> list[InstrumentEventRecord]:
        provider_symbol = _optional_text(row.get("ticker"))
        if provider_symbol and provider_symbol.upper() != symbol:
            raise ProviderResponseError(
                self.name, "Massive dividend returned a different ticker than requested"
            )
        dates = {
            field: _optional_action_date(row.get(field), self.name, field)
            for field in ("declaration_date", "ex_dividend_date", "record_date", "pay_date")
        }
        if all(value is None for value in dates.values()):
            raise ProviderResponseError(self.name, "Massive dividend returned no valid date")
        amount = _optional_action_decimal(row.get("cash_amount"), self.name, "cash_amount")
        currency = _optional_text(row.get("currency"))
        source_id = _optional_text(row.get("id"))
        base_key = source_id or ":".join(
            [str(dates[field] or "") for field in ("declaration_date", "ex_dividend_date", "pay_date")]
        )
        events: list[InstrumentEventRecord] = []
        if dates["ex_dividend_date"] is not None:
            events.append(
                self._dividend_event(
                    InstrumentEventType.EX_DIVIDEND,
                    dates["ex_dividend_date"],
                    symbol,
                    base_key,
                    amount,
                    currency,
                    row,
                    fetched_at,
                )
            )
        if dates["pay_date"] is not None:
            events.append(
                self._dividend_event(
                    InstrumentEventType.DIVIDEND,
                    dates["pay_date"],
                    symbol,
                    base_key,
                    amount,
                    currency,
                    row,
                    fetched_at,
                )
            )
        if not events:
            fallback_date = dates["declaration_date"] or dates["record_date"]
            assert fallback_date is not None
            events.append(
                self._dividend_event(
                    InstrumentEventType.DIVIDEND,
                    fallback_date,
                    symbol,
                    base_key,
                    amount,
                    currency,
                    row,
                    fetched_at,
                )
            )
        return events

    def _dividend_event(
        self,
        event_type: InstrumentEventType,
        event_date: date,
        symbol: str,
        source_key: str,
        amount: Decimal | None,
        currency: str | None,
        row: dict[str, Any],
        fetched_at: datetime,
    ) -> InstrumentEventRecord:
        label = "Ex-Dividend" if event_type is InstrumentEventType.EX_DIVIDEND else "Dividend"
        return InstrumentEventRecord(
            event_type=event_type,
            event_time=datetime.combine(event_date, datetime.min.time(), tzinfo=UTC),
            time_hint=EventTimeHint.UNKNOWN,
            title=f"{label} {symbol}",
            source_event_key=f"massive:dividend:{symbol}:{source_key}:{event_type.value}",
            fetched_at=fetched_at,
            dividend_amount=amount,
            raw_payload=str(row),
        )

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


def _aggregate_next_page(next_url: Any, provider_name: str) -> tuple[str, str]:
    """Extract a safe Massive aggregate continuation path and cursor."""

    if not isinstance(next_url, str):
        raise ProviderResponseError(provider_name, "Massive aggregate returned an invalid next_url")
    parsed = urlparse(next_url)
    if parsed.scheme != "https" or parsed.netloc != "api.massive.com":
        raise ProviderResponseError(provider_name, "Massive aggregate returned an untrusted next_url host")
    if not parsed.path.startswith("/v2/aggs/ticker/"):
        raise ProviderResponseError(provider_name, "Massive aggregate returned an invalid next_url path")
    cursor_values = parse_qs(parsed.query).get("cursor", [])
    if len(cursor_values) != 1 or not cursor_values[0].strip():
        raise ProviderResponseError(
            provider_name,
            "Massive aggregate returned a next_url without one valid cursor",
        )
    return parsed.path, cursor_values[0]


def _corporate_actions_next_page(
    next_url: Any, provider_name: str, expected_path: str
) -> tuple[str, str]:
    """Validate a Massive corporate-action continuation before following it."""

    if not isinstance(next_url, str):
        raise ProviderResponseError(provider_name, "Massive corporate-actions returned an invalid next_url")
    parsed = urlparse(next_url)
    if parsed.scheme != "https" or parsed.netloc != "api.massive.com":
        raise ProviderResponseError(
            provider_name, "Massive corporate-actions returned an untrusted next_url host"
        )
    if parsed.path != expected_path:
        raise ProviderResponseError(
            provider_name, "Massive corporate-actions returned an unexpected next_url path"
        )
    cursor_values = parse_qs(parsed.query).get("cursor", [])
    if len(cursor_values) != 1 or not cursor_values[0].strip():
        raise ProviderResponseError(
            provider_name,
            "Massive corporate-actions returned a next_url without one valid cursor",
        )
    return parsed.path, cursor_values[0]


def estimate_ohlcv_request_count(
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
) -> int | None:
    """Reserve every possible custom-bars page before admitting a request.

    Massive documents a 50,000-base-aggregate page maximum.  Calendar time is
    intentionally used as a conservative upper bound because the endpoint
    returns only intervals containing eligible trades.
    """

    seconds = _TF_SECONDS.get(timeframe)
    if seconds is None:
        return None
    if end <= start:
        return 0
    candles = max(1, ceil((end - start).total_seconds() / seconds))
    return max(1, ceil(candles / _AGGREGATE_PAGE_SIZE))


def estimate_latest_ohlcv_request_count(timeframe: Timeframe, limit: int) -> int | None:
    seconds = _TF_SECONDS.get(timeframe)
    if seconds is None:
        return None
    if limit <= 0:
        return 0
    lookback_seconds = seconds * max(1, limit) * 1.4 + 86400
    candles = max(1, ceil(lookback_seconds / seconds) + 1)
    return max(1, ceil(candles / _AGGREGATE_PAGE_SIZE))


def estimate_corporate_actions_request_count(max_pages: int) -> int | None:
    """Reserve both independently paginated corporate-action endpoints."""

    bound = provider_positive_integer(max_pages)
    return bound * 2 if bound is not None else None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _epoch_millis(value: datetime) -> int:
    return int(value.timestamp() * 1000)


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


def _optional_action_date(value: Any, provider_name: str, field: str) -> date | None:
    if value in (None, ""):
        return None
    parsed = _parse_date(value)
    if parsed is None:
        raise ProviderResponseError(provider_name, f"Massive action returned an invalid {field}")
    return parsed


def _required_action_date(value: Any, provider_name: str, field: str) -> date:
    parsed = _optional_action_date(value, provider_name, field)
    if parsed is None:
        raise ProviderResponseError(provider_name, f"Massive action returned no {field}")
    return parsed


def _optional_action_decimal(value: Any, provider_name: str, field: str) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ProviderResponseError(provider_name, f"Massive action returned an invalid {field}")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ProviderResponseError(provider_name, f"Massive action returned an invalid {field}") from exc
    if not parsed.is_finite():
        raise ProviderResponseError(provider_name, f"Massive action returned a non-finite {field}")
    return parsed


def _optional_text(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    return text or None
