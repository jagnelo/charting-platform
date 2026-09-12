"""Alpha Vantage free-quota history, earnings, and symbol-search adapter."""

from __future__ import annotations

import csv
import io
import logging
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import Any

import httpx

from app.config import settings
from app.models.instrument_event import EventTimeHint, InstrumentEventType
from app.models.ohlcv import OHLCVBar, Timeframe
from app.providers.base import InstrumentEventRecord, MarketEventRecord, ProviderSearchResult
from app.providers.errors import (
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
    provider_response_headers,
    raise_for_provider_error_envelope,
)
from app.providers.telemetry import observe_response

logger = logging.getLogger(__name__)
_BASE = "https://www.alphavantage.co/query"
_DAILY_CAPACITY_RE = re.compile(r"\b(?:requests?|calls?)\s+per\s+day\b", re.IGNORECASE)


class AlphaVantageProvider:
    name = "alpha_vantage"
    base_url = "https://www.alphavantage.co"
    description = "Alpha Vantage free-quota daily history, earnings, and symbol search"

    def _key(self) -> str:
        return settings.ALPHA_VANTAGE_API_KEY

    def _get(self, function: str, **params: Any) -> dict[str, Any] | None:
        if not self._key():
            raise ProviderNotConfiguredError("alpha_vantage requires ALPHA_VANTAGE_API_KEY")
        try:
            response = httpx.get(
                _BASE, params={"function": function, "apikey": self._key(), **params}, timeout=30
            )
        except httpx.RequestError as exc:
            raise ProviderResponseError(self.name, str(exc)) from exc
        observe_response(response)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if response.status_code in {418, 429}:
                raise ProviderRateLimitError(
                    self.name,
                    f"Alpha Vantage request rejected for capacity (HTTP {response.status_code})",
                    status_code=response.status_code,
                    headers=provider_response_headers(response),
                ) from exc
            raise ProviderResponseError(
                self.name, f"Alpha Vantage request failed with HTTP {response.status_code}", status_code=response.status_code
            ) from exc
        try:
            payload = response.json()
        except (TypeError, ValueError) as exc:
            raise ProviderResponseError(self.name, "Alpha Vantage returned invalid JSON") from exc
        raise_for_provider_error_envelope(
            self.name, payload, response.status_code, headers=provider_response_headers(response)
        )
        if isinstance(payload, dict) and (payload.get("Note") or payload.get("Information")):
            message = str(payload.get("Note") or payload.get("Information"))
            raise ProviderRateLimitError(
                self.name,
                message,
                retry_at=_retry_at_for_capacity_message(message),
                headers=provider_response_headers(response),
            )
        if not isinstance(payload, dict):
            raise ProviderResponseError(self.name, "Alpha Vantage returned an invalid response object")
        return payload

    def _get_text(self, function: str, **params: Any) -> str | None:
        if not self._key():
            raise ProviderNotConfiguredError("alpha_vantage requires ALPHA_VANTAGE_API_KEY")
        try:
            response = httpx.get(
                _BASE, params={"function": function, "apikey": self._key(), **params}, timeout=30
            )
        except httpx.RequestError as exc:
            raise ProviderResponseError(self.name, str(exc)) from exc
        observe_response(response)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if response.status_code in {418, 429}:
                raise ProviderRateLimitError(
                    self.name,
                    f"Alpha Vantage request rejected for capacity (HTTP {response.status_code})",
                    status_code=response.status_code,
                    headers=provider_response_headers(response),
                ) from exc
            raise ProviderResponseError(
                self.name, f"Alpha Vantage request failed with HTTP {response.status_code}", status_code=response.status_code
            ) from exc
        text = response.text
        if not isinstance(text, str):
            raise ProviderResponseError(self.name, "Alpha Vantage returned an invalid text response")
        if "Error Message" in text:
            raise ProviderResponseError(self.name, text[:240])
        lowered = text.lower()
        csv_information = _csv_information_message(text)
        if (
            "thank you for using alpha vantage" in lowered
            or "higher api call volume" in lowered
            or csv_information
        ):
            capacity_message = (
                "Alpha Vantage CSV response indicates the documented daily request capacity"
                if csv_information
                else text[:240]
            )
            raise ProviderRateLimitError(
                self.name,
                capacity_message,
                retry_at=_retry_at_for_capacity_message(
                    text,
                    assume_daily_for_csv_information=csv_information,
                ),
                headers=provider_response_headers(response),
            )
        return text
    def search_instruments(self, query: str, *, limit: int = 10) -> list[ProviderSearchResult]:
        if not query.strip() or limit <= 0:
            return []
        payload = self._get("SYMBOL_SEARCH", keywords=query.strip())
        matches = payload.get("bestMatches", [])
        if not isinstance(matches, list) or any(not isinstance(row, dict) for row in matches):
            raise ProviderResponseError(self.name, "Alpha Vantage returned malformed symbol-search rows")
        for row in matches:
            if not str(row.get("1. symbol") or "").strip() or not str(row.get("2. name") or "").strip():
                raise ProviderResponseError(self.name, "Alpha Vantage returned an incomplete symbol-search row")
        return [
            ProviderSearchResult(
                symbol=str(row.get("1. symbol") or ""),
                name=str(row.get("2. name") or ""),
                exchange=str(row.get("4. region") or ""),
                instrument_type=str(row.get("3. type") or "EQUITY").upper(),
            )
            for row in matches[:limit]
        ]

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
        # Alpha Vantage's free key currently rejects ``outputsize=full`` as a
        # premium-only feature. ``compact`` is the documented free response
        # (latest 100 daily points); older history must use another provider.
        payload = self._get("TIME_SERIES_DAILY", symbol=symbol, outputsize="compact")
        series = payload.get("Time Series (Daily)", {})
        if not isinstance(series, dict):
            raise ProviderResponseError(self.name, "Alpha Vantage returned an invalid daily-series object")
        bars: list[OHLCVBar] = []
        for date_text, row in series.items():
            if not isinstance(row, dict):
                raise ProviderResponseError(self.name, "Alpha Vantage returned a malformed daily-series row")
            try:
                ts = datetime.strptime(date_text, "%Y-%m-%d").replace(tzinfo=UTC)
                if not (start <= ts < end):
                    continue
                values = [row[f"{index}. {field}"] for index, field in ((1, "open"), (2, "high"), (3, "low"), (4, "close"), (5, "volume"))]
                numbers = [float(value) for value in values]
                if not all(isfinite(value) for value in numbers):
                    raise ValueError("non-finite Alpha Vantage daily value")
                bars.append(
                    OHLCVBar(
                        instrument_id=instrument_id,
                        data_source_id=data_source_id,
                        timeframe=timeframe,
                        ts=ts,
                        open=numbers[0],
                        high=numbers[1],
                        low=numbers[2],
                        close=numbers[3],
                        volume=numbers[4],
                        is_adjusted=False,
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ProviderResponseError(self.name, "Alpha Vantage returned an invalid daily-series row") from exc
        return sorted(bars, key=lambda bar: bar.ts)

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
        return self.fetch_ohlcv(
            symbol,
            timeframe,
            start,
            datetime.now(UTC),
            adjusted=adjusted,
            instrument_id=instrument_id,
            data_source_id=data_source_id,
        )[-limit:]

    def latest_window_start(self, timeframe: Timeframe, limit: int) -> datetime:
        return datetime.now(UTC) - timedelta(days=max(limit * 2, 30))

    def get_current_price(self, symbol: str) -> float | None:
        bars = self.fetch_latest_ohlcv(symbol, Timeframe.D1, 1)
        return float(bars[-1].close) if bars else None

    def fetch_instrument_events(self, symbol: str) -> list[InstrumentEventRecord]:
        """Normalize Alpha Vantage's documented annual/quarterly ``EARNINGS`` data.

        Alpha Vantage supplies a fiscal period and, for quarterly rows, a
        reported date. The latter is the best available event date; when it
        is absent we retain the fiscal period end rather than inventing an
        announcement timestamp. Dates have no intraday timing in this
        endpoint, so every event is explicitly marked ``UNKNOWN``.
        """

        normalized_symbol = symbol.strip().upper()
        payload = self._get("EARNINGS", symbol=normalized_symbol)
        if not isinstance(payload, dict):
            raise ProviderResponseError(self.name, "Alpha Vantage returned an invalid earnings object")

        rows: list[tuple[str, dict[str, Any]]] = []
        for section, kind in (("annualEarnings", "annual"), ("quarterlyEarnings", "quarterly")):
            raw_rows = payload.get(section)
            if not isinstance(raw_rows, list) or any(not isinstance(row, dict) for row in raw_rows):
                raise ProviderResponseError(
                    self.name, f"Alpha Vantage returned malformed {section} rows"
                )
            rows.extend((kind, row) for row in raw_rows)

        fetched_at = datetime.now(UTC)
        events: list[InstrumentEventRecord] = []
        for kind, row in rows:
            fiscal_date = _required_earnings_date(row.get("fiscalDateEnding"), "fiscalDateEnding")
            reported_date = _optional_earnings_date(row.get("reportedDate"), "reportedDate")
            event_time = reported_date or fiscal_date
            eps_actual = _checked_earnings_decimal(row.get("reportedEPS"), "reportedEPS")
            eps_estimate = _checked_earnings_decimal(row.get("estimatedEPS"), "estimatedEPS")
            eps_surprise = _checked_earnings_decimal(row.get("surprise"), "surprise")
            eps_surprise_pct = _checked_earnings_decimal(
                row.get("surprisePercentage"), "surprisePercentage"
            )
            event_type = (
                InstrumentEventType.EARNINGS
                if eps_actual is not None
                else InstrumentEventType.EARNINGS_ESTIMATE
            )
            source_event_key = (
                f"alpha_vantage:earnings:{kind}:{normalized_symbol}:"
                f"{fiscal_date.date().isoformat()}:{reported_date.date().isoformat() if reported_date else 'unknown'}"
            )
            events.append(
                InstrumentEventRecord(
                    event_type=event_type,
                    event_time=event_time,
                    time_hint=EventTimeHint.UNKNOWN,
                    title=f"Alpha Vantage {kind} earnings {normalized_symbol}",
                    source_event_key=source_event_key,
                    fetched_at=fetched_at,
                    value=eps_estimate,
                    actual=eps_actual,
                    eps_estimate=eps_estimate,
                    eps_actual=eps_actual,
                    eps_surprise=eps_surprise,
                    eps_surprise_pct=eps_surprise_pct,
                    raw_payload=str(row),
                )
            )
        return sorted(events, key=lambda event: (event.event_time, event.source_event_key))

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        if quote_type.strip().upper() not in {"EQUITY", "EQUITIES", "STOCK", "STOCKS"}:
            return {"total": 0, "quotes": []}
        text = self._get_text("LISTING_STATUS", state="active")
        if not text:
            return {"total": 0, "quotes": []}
        try:
            reader = csv.DictReader(io.StringIO(text), strict=True)
            if not reader.fieldnames or not {"symbol", "name", "exchange", "assetType", "status"}.issubset(
                set(reader.fieldnames)
            ):
                raise ValueError("Alpha Vantage listing CSV is missing required columns")
            rows = list(reader)
        except (csv.Error, TypeError, ValueError) as exc:
            raise ProviderResponseError(self.name, "Alpha Vantage returned malformed listing CSV") from exc
        if any(None in row or any(value is None for value in row.values()) for row in rows):
            raise ProviderResponseError(self.name, "Alpha Vantage returned malformed listing CSV rows")
        page_size = 1000
        page = rows[max(offset, 0) : max(offset, 0) + page_size]
        quotes = [
            {
                "symbol": str(row.get("symbol") or "").upper(),
                "name": str(row.get("name") or ""),
                "exchange": str(row.get("exchange") or ""),
                "instrument_type": str(row.get("assetType") or "EQUITY").upper(),
                "status": str(row.get("status") or "active").lower(),
                "ipo_date": row.get("ipoDate") or None,
                "delisting_date": row.get("delistingDate") or None,
            }
            for row in page
        ]
        if any(not quote["symbol"] or not quote["name"] for quote in quotes):
            raise ProviderResponseError(self.name, "Alpha Vantage returned incomplete listing rows")
        return {"total": len(rows), "quotes": quotes}

    def supported_discovery_types(self) -> list[str]:
        return ["EQUITY"]

    def fetch_market_events(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[MarketEventRecord]:
        """Fetch the provider's forward/historical IPO calendar as normalized events."""

        text = self._get_text("IPO_CALENDAR")
        if not text:
            return []
        try:
            reader = csv.DictReader(io.StringIO(text), strict=True)
            if not reader.fieldnames or not {"symbol", "name", "ipoDate"}.issubset(set(reader.fieldnames)):
                raise ValueError("Alpha Vantage IPO CSV is missing required columns")
            rows = list(reader)
        except (csv.Error, TypeError, ValueError) as exc:
            raise ProviderResponseError(self.name, "Alpha Vantage returned malformed IPO CSV") from exc
        if any(None in row or any(value is None for value in row.values()) for row in rows):
            raise ProviderResponseError(self.name, "Alpha Vantage returned malformed IPO CSV rows")
        result: list[MarketEventRecord] = []
        for row in rows:
            try:
                event_date = date.fromisoformat(str(row.get("ipoDate") or ""))
            except ValueError as exc:
                raise ProviderResponseError(self.name, "Alpha Vantage returned an invalid IPO date") from exc
            if start and event_date < start or end and event_date > end:
                continue
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol:
                raise ProviderResponseError(self.name, "Alpha Vantage returned an IPO row without a symbol")
            result.append(
                MarketEventRecord(
                    event_type="ipo",
                    event_key=f"alpha_vantage:ipo:{symbol}:{event_date.isoformat()}",
                    event_time=datetime.combine(event_date, datetime.min.time(), tzinfo=UTC),
                    effective_date=event_date,
                    title=str(row.get("name") or symbol),
                    source_version="IPO_CALENDAR",
                    is_provisional=True,
                    raw_payload=row,
                )
            )
        return result


def _csv_information_message(text: str) -> bool:
    """Recognize Alpha Vantage's quota message when returned as CSV fields."""

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2 or not lines[0].lower().startswith("symbol,"):
        return False
    message = lines[1].replace(",", "").strip().lower()
    return message.startswith(("informa", "note", "errormessage"))


def _required_earnings_date(value: Any, field: str) -> datetime:
    parsed = _optional_earnings_date(value, field)
    if parsed is None:
        raise ProviderResponseError("alpha_vantage", f"Alpha Vantage returned an invalid {field}")
    return parsed


def _optional_earnings_date(value: Any, field: str) -> datetime | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ProviderResponseError("alpha_vantage", f"Alpha Vantage returned an invalid {field}")
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ProviderResponseError("alpha_vantage", f"Alpha Vantage returned an invalid {field}") from exc


def _checked_earnings_decimal(value: Any, field: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in {"", "none", "null", "n/a", "na", "-"}:
        return None
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ProviderResponseError("alpha_vantage", f"Alpha Vantage returned an invalid {field}") from exc
    if not parsed.is_finite():
        raise ProviderResponseError("alpha_vantage", f"Alpha Vantage returned an invalid {field}")
    return parsed


def _retry_at_for_capacity_message(
    message: str,
    *,
    now: datetime | None = None,
    assume_daily_for_csv_information: bool = False,
) -> datetime | None:
    """Return Alpha Vantage's provider-specific daily-capacity retry window.

    The free-plan quota is documented as 25 requests/day, but Alpha Vantage
    does not include a reset timestamp in the observed JSON or CSV capacity
    responses.  Only an explicit daily marker (or the provider's CSV
    ``Information`` quota shape) receives the reviewed 24-hour retry window;
    other informational messages remain observable without a guessed delay.
    """

    if not _DAILY_CAPACITY_RE.search(message) and not assume_daily_for_csv_information:
        return None
    return (now or datetime.now(UTC)) + timedelta(days=1)
