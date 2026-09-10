"""Official Nasdaq Trader symbol-directory adapter.

Nasdaq Trader publishes the authoritative, machine-readable ``nasdaqlisted``
and ``otherlisted`` files. They are used only for US listing/lifecycle
evidence; the undocumented ``api.nasdaq.com`` quote-history route is not used.
"""

from __future__ import annotations

import csv
import io
import time
from typing import Any

import httpx

from app.config import settings
from app.providers.errors import ProviderResponseError
from app.providers.telemetry import observe_response

_BASE = "https://www.nasdaqtrader.com/dynamic/SymDir"
_FILES = {"nasdaqlisted": f"{_BASE}/nasdaqlisted.txt", "otherlisted": f"{_BASE}/otherlisted.txt"}
_PAGE_SIZE = 1000
_CACHE_TTL_SECONDS = 900
_cache: tuple[float, list[dict[str, Any]]] | None = None
_file_cache: dict[str, tuple[list[dict[str, Any]], dict[str, str]]] = {}


class NasdaqProvider:
    name = "nasdaq"
    base_url = "https://www.nasdaqtrader.com"
    description = "Official Nasdaq Trader US listing and lifecycle symbol directories"

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        normalized = quote_type.strip().upper()
        if normalized not in {"EQUITY", "ETF"} or offset < 0:
            return {"total": 0, "quotes": []}
        rows = [row for row in _directory_rows() if row["quoteType"] == normalized]
        page = rows[offset : offset + _PAGE_SIZE]
        return {
            "total": len(rows),
            "quotes": page,
            "next_offset": offset + _PAGE_SIZE if offset + _PAGE_SIZE < len(rows) else None,
            "source_files": list(_FILES),
        }

    def supported_discovery_types(self) -> list[str]:
        return ["EQUITY", "ETF"]


def _directory_rows() -> list[dict[str, Any]]:
    global _cache
    now = time.monotonic()
    if _cache and now - _cache[0] < _CACHE_TTL_SECONDS:
        return list(_cache[1])
    rows: list[dict[str, Any]] = []
    for source_name, url in _FILES.items():
        cached_file = _file_cache.get(source_name)
        request_headers = {"User-Agent": settings.NASDAQ_USER_AGENT}
        if cached_file:
            validators = cached_file[1]
            if validators.get("etag"):
                request_headers["If-None-Match"] = validators["etag"]
            if validators.get("last-modified"):
                request_headers["If-Modified-Since"] = validators["last-modified"]
        try:
            response = httpx.get(
                url,
                headers=request_headers,
                timeout=30,
            )
        except httpx.RequestError as exc:
            raise ProviderResponseError("nasdaq", f"transport failure: {exc}") from exc
        observe_response(response)
        if response.status_code == 304:
            if cached_file is None:
                raise ProviderResponseError(
                    "nasdaq", f"304 response without a local {source_name} cache"
                )
            rows.extend(cached_file[0])
            continue
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            raise
        try:
            parsed = _parse_file(source_name, response.text)
        except (TypeError, ValueError, csv.Error) as exc:
            raise ProviderResponseError(
                "nasdaq", f"malformed {source_name} directory response: {exc}"
            ) from exc
        rows.extend(parsed)
        response_headers = {
            str(key).lower(): str(value)
            for key, value in response.headers.items()
            if str(key).lower() in {"etag", "last-modified"}
        }
        _file_cache[source_name] = (parsed, response_headers)
    _cache = (now, rows)
    return list(rows)


def _parse_file(source_name: str, text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text), delimiter="|")
    fieldnames = set(reader.fieldnames or ())
    if source_name == "nasdaqlisted":
        required_columns = {"Symbol", "Security Name"}
        valid_header = required_columns.issubset(fieldnames)
    else:
        # A few approved directory mirrors retain Nasdaq's ``Symbol`` header
        # while the official ``otherlisted`` file uses ``ACT Symbol``.  Both
        # are accepted; the security name is the minimum identity field and
        # exchange is optional evidence on such mirrors.
        required_columns = {"ACT Symbol", "Security Name"}
        valid_header = (
            {"Security Name"}.issubset(fieldnames)
            and ("ACT Symbol" in fieldnames or "Symbol" in fieldnames)
        )
    if not reader.fieldnames or not valid_header:
        raise ValueError(
            f"missing required columns for {source_name}: {sorted(required_columns)}"
        )
    parsed: list[dict[str, Any]] = []
    for row in reader:
        first_value = next(iter(row.values()), "") if row else ""
        if (
            not row
            or row.get("File Creation Time") is not None
            or str(first_value).strip().lower().startswith("file creation time")
        ):
            continue
        if source_name == "nasdaqlisted":
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"malformed row in {source_name}: inconsistent column count")
            symbol = str(row.get("Symbol") or "").strip().upper()
            name = str(row.get("Security Name") or "").strip()
            exchange = "XNAS"
            is_etf = str(row.get("ETF") or "N").upper() == "Y"
            test_issue = str(row.get("Test Issue") or "N").upper() == "Y"
            financial_status = str(row.get("Financial Status") or "").upper()
            # Nasdaq's Financial Status Indicator describes a listed issue's
            # compliance/bankruptcy state; it is not a delisting feed. Keep
            # those rows in the universe and retain the indicator as evidence.
            # Test issues are the only Nasdaq-listed directory rows excluded.
            active = not test_issue
        else:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"malformed row in {source_name}: inconsistent column count")
            if row.get("ACT Symbol") is None and row.get("Symbol") is None:
                raise ValueError(f"malformed row in {source_name}: missing symbol column value")
            symbol = str(row.get("ACT Symbol") or row.get("Symbol") or "").strip().upper()
            name = str(row.get("Security Name") or "").strip()
            code = str(row.get("Exchange") or "").strip().upper()
            exchange = {"A": "XASE", "N": "XNYS", "P": "ARCX", "Z": "BATS", "V": "IEXG"}.get(
                code, code or None
            )
            is_etf = str(row.get("ETF") or "N").upper() == "Y"
            financial_status = ""
            active = str(row.get("Test Issue") or "N").upper() != "Y"
        if not symbol or not name:
            raise ValueError(f"malformed row in {source_name}: missing symbol or security name")
        if not active:
            continue
        parsed.append(
            {
                "symbol": symbol,
                "longName": name,
                "shortName": name,
                "exchange": exchange,
                "exchange_mic": exchange,
                "currency": "USD",
                "quoteType": "ETF" if is_etf else "EQUITY",
                "instrument_type": "ETF" if is_etf else "EQUITY",
                "status": "active",
                "financial_status": financial_status or None,
                "source_record": row,
                "source_file": source_name,
            }
        )
    return parsed
