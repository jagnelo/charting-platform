"""Public Nasdaq historical daily bars for US-listed equities and ETFs.

The public quote-history endpoint is used as a free-source, EOD fallback when
credentialed providers are unavailable.  It exposes the exchange's historical
price series (including split-adjusted historical prices in the returned
series), but it is not a total-return feed and does not provide intraday bars.

The adapter intentionally supports only ``D1`` and only the platform's
``adjusted=True`` view.  Returning no rows for raw or intraday requests keeps
the adjustment contract honest and lets the provider runtime continue to an
independently entitled source where one exists.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.config import settings
from app.models.ohlcv import OHLCVBar, Timeframe

logger = logging.getLogger(__name__)

_BASE = "https://api.nasdaq.com/api/quote"
_PAGE_SIZE = 5_000
_MAX_PAGES = 4
_US_DATE = "%Y-%m-%d"
_ROW_DATE = "%m/%d/%Y"
_CACHE_TTL_SECONDS = 120.0
_history_cache: dict[tuple[str, str, str, str], tuple[float, list[dict[str, Any]]]] = {}


def _number(value: Any) -> float | None:
    """Parse Nasdaq currency/volume strings without accepting placeholders."""
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text in {"--", "-", "N/A", "n/a"}:
        return None
    text = text.replace("$", "").replace("%", "")
    # Keep a leading minus and decimal/scientific notation; reject other text.
    if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text):
        return None
    try:
        return float(text)
    except ValueError:
        return None


class NasdaqProvider:
    name = "nasdaq"
    base_url = "https://api.nasdaq.com"
    description = (
        "Nasdaq public historical quote endpoint — free US-listed EOD prices, "
        "split-adjusted price series, and volume"
    )

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": getattr(
                settings,
                "NASDAQ_USER_AGENT",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
            ),
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.nasdaq.com",
            "Referer": "https://www.nasdaq.com/",
        }

    def _rows(
        self, symbol: str, asset_class: str, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        """Fetch all bounded pages for one Nasdaq asset class."""
        rows: list[dict[str, Any]] = []
        # Nasdaq's public route can omit the newest ETF session when
        # ``fromdate`` is the requested session or only one calendar day
        # earlier. Start three calendar days earlier (enough to cross a normal
        # weekend boundary), request through today, and filter to the caller's
        # range after parsing. This preserves the canonical interval while
        # allowing the endpoint to return the boundary session.
        query_start = start - timedelta(days=3)
        query_end = max(end, datetime.now(UTC))
        cache_key = (
            symbol.upper(),
            asset_class,
            query_start.strftime(_US_DATE),
            query_end.strftime(_US_DATE),
        )
        cached = _history_cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
            return list(cached[1])
        for page in range(_MAX_PAGES):
            try:
                response = httpx.get(
                    f"{_BASE}/{symbol.upper()}/historical",
                    params={
                        "assetclass": asset_class,
                        "fromdate": query_start.strftime(_US_DATE),
                        "todate": query_end.strftime(_US_DATE),
                        "limit": _PAGE_SIZE,
                        "offset": page * _PAGE_SIZE,
                    },
                    headers=self._headers(),
                    timeout=30,
                )
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                logger.warning("nasdaq historical %s (%s) failed: %s", symbol, asset_class, exc)
                return []

            data = payload.get("data") if isinstance(payload, dict) else None
            table = data.get("tradesTable") if isinstance(data, dict) else None
            page_rows = table.get("rows") if isinstance(table, dict) else None
            if not isinstance(page_rows, list):
                _history_cache[cache_key] = (time.monotonic(), rows)
                return rows
            rows.extend(row for row in page_rows if isinstance(row, dict))
            total = data.get("totalRecords") if isinstance(data, dict) else None
            if len(rows) >= int(total or len(rows)) or len(page_rows) < _PAGE_SIZE:
                break
        _history_cache[cache_key] = (time.monotonic(), rows)
        return rows

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
        if timeframe is not Timeframe.D1 or not adjusted:
            return []
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)

        # Nasdaq uses separate asset-class routes.  Stocks first avoids the
        # ETF route returning a less useful error for ordinary equities; ETFs
        # are tried only when the stock route has no rows.
        rows = self._rows(symbol, "stocks", start, end)
        if not rows:
            rows = self._rows(symbol, "etf", start, end)

        bars: list[OHLCVBar] = []
        for row in rows:
            try:
                ts = datetime.strptime(str(row["date"]), _ROW_DATE).replace(tzinfo=UTC)
            except (KeyError, TypeError, ValueError):
                continue
            if not start <= ts < end:
                continue
            values = {
                field: _number(row.get(field))
                for field in ("open", "high", "low", "close", "volume")
            }
            if any(values[field] is None for field in ("open", "high", "low", "close")):
                continue
            bars.append(
                OHLCVBar(
                    instrument_id=instrument_id,
                    data_source_id=data_source_id,
                    timeframe=timeframe,
                    ts=ts,
                    open=values["open"],
                    high=values["high"],
                    low=values["low"],
                    close=values["close"],
                    volume=values["volume"],
                    is_adjusted=True,
                )
            )
        # The endpoint is newest-first and may overlap pages; the canonical
        # upsert key removes duplicates, while this keeps provider output clean.
        return sorted({bar.ts: bar for bar in bars}.values(), key=lambda bar: bar.ts)

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
