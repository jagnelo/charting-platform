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

_BASE = "https://www.nasdaqtrader.com/dynamic/SymDir"
_FILES = {"nasdaqlisted": f"{_BASE}/nasdaqlisted.txt", "otherlisted": f"{_BASE}/otherlisted.txt"}
_PAGE_SIZE = 1000
_CACHE_TTL_SECONDS = 900
_cache: tuple[float, list[dict[str, Any]]] | None = None


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
        response = httpx.get(
            url,
            headers={"User-Agent": settings.NASDAQ_USER_AGENT},
            timeout=30,
        )
        response.raise_for_status()
        rows.extend(_parse_file(source_name, response.text))
    _cache = (now, rows)
    return list(rows)


def _parse_file(source_name: str, text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text), delimiter="|")
    parsed: list[dict[str, Any]] = []
    for row in reader:
        first_value = next(iter(row.values()), "") if row else ""
        if not row or row.get("File Creation Time") is not None or str(first_value).strip().lower().startswith("file creation time"):
            continue
        if source_name == "nasdaqlisted":
            symbol = str(row.get("Symbol") or "").strip().upper()
            name = str(row.get("Security Name") or symbol).strip()
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
            symbol = str(row.get("ACT Symbol") or "").strip().upper()
            name = str(row.get("Security Name") or symbol).strip()
            code = str(row.get("Exchange") or "").strip().upper()
            exchange = {"A": "XASE", "N": "XNYS", "P": "ARCX", "Z": "BATS", "V": "IEXG"}.get(code, code or None)
            is_etf = str(row.get("ETF") or "N").upper() == "Y"
            financial_status = ""
            active = str(row.get("Test Issue") or "N").upper() != "Y"
        if not symbol or not active:
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
