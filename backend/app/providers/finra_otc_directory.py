"""Configurable FINRA-described OTC symbol-directory adapter.

FINRA documents a pipe-delimited OTC/OTCBB symbol-directory shape, but the
current public delivery URL and usage terms must be confirmed by operations.
This adapter therefore has no default URL and no inferred quota.  It is
discoverable for administration, but remains non-routable until an explicit
source, quota contract, and terms entitlement are recorded.
"""

from __future__ import annotations

import csv
import io
import time
from typing import Any

import httpx

from app.config import settings
from app.providers.errors import ProviderNotConfiguredError

_PAGE_SIZE = 1000
_CACHE_TTL_SECONDS = 900
_cache: tuple[float, list[dict[str, Any]]] | None = None


class FINRAOTCDirectoryProvider:
    name = "finra_otc_directory"
    base_url = "https://otce.finra.org"
    description = "Configurable FINRA OTC/OTCBB symbol-directory evidence"

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        if quote_type.strip().upper() != "OTC" or offset < 0:
            return {"total": 0, "quotes": [], "source_files": []}
        rows = _directory_rows()
        page = rows[offset : offset + _PAGE_SIZE]
        return {
            "total": len(rows),
            "quotes": page,
            "next_offset": offset + _PAGE_SIZE if offset + _PAGE_SIZE < len(rows) else None,
            "source_files": [self._source_url()],
        }

    def supported_discovery_types(self) -> list[str]:
        return ["OTC"]

    @staticmethod
    def _source_url() -> str:
        url = str(getattr(settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", "") or "").strip()
        if not url:
            raise ProviderNotConfiguredError(
                "finra_otc_directory requires FINRA_OTC_SYMBOL_DIRECTORY_URL; "
                "the current public directory delivery URL must be operator-approved"
            )
        return url


def _directory_rows() -> list[dict[str, Any]]:
    global _cache
    now = time.monotonic()
    if _cache and now - _cache[0] < _CACHE_TTL_SECONDS:
        return list(_cache[1])
    url = FINRAOTCDirectoryProvider._source_url()
    response = httpx.get(
        url,
        headers={"User-Agent": settings.NASDAQ_USER_AGENT, "Accept": "text/plain"},
        timeout=30,
    )
    response.raise_for_status()
    rows = _parse_directory(response.text)
    if not rows:
        raise ValueError("FINRA OTC symbol directory returned no valid rows")
    _cache = (now, rows)
    return list(rows)


def _parse_directory(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text), delimiter="|")
    if not reader.fieldnames:
        return []
    fields = {str(field).strip().lower() for field in reader.fieldnames if field}
    required = {"issue_sym_id", "issue_short_nm", "status", "mkt_cat"}
    if not required.issubset(fields):
        return []
    result: list[dict[str, Any]] = []
    for row in reader:
        normalized = {
            str(key).strip().lower(): str(value or "").strip() for key, value in row.items() if key
        }
        symbol = normalized.get("issue_sym_id", "").upper()
        if not symbol:
            continue
        status = normalized.get("status", "").upper()
        market_category = normalized.get("mkt_cat", "")
        result.append(
            {
                "symbol": symbol,
                "longName": normalized.get("issue_short_nm") or symbol,
                "shortName": normalized.get("issue_short_nm") or symbol,
                "exchange": "OTC",
                "exchange_mic": "OTC",
                "currency": "USD",
                "quoteType": "EQUITY",
                "instrument_type": "EQUITY",
                "status": "active" if status in {"ACTIVE", "ELIGIBLE"} else "inactive",
                "financial_status": None,
                "market_category": market_category,
                "oats_reportable": normalized.get("oats_rptbl_fl") or None,
                "source_record": normalized,
            }
        )
    return result
