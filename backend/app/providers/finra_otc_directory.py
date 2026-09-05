"""Configurable FINRA OTC Security Master adapter.

FINRA's current OTC site uses the public DAPI ``otcSecurityMaster`` dataset;
the adapter also accepts the documented legacy pipe-delimited directory shape
for an operator-approved mirror or archive. The source URL is still explicit
configuration and this provider has no inferred quota, so it remains
non-routable until terms, completeness, and a quota contract are recorded.
"""

from __future__ import annotations

import csv
import io
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.config import settings
from app.providers.errors import ProviderNotConfiguredError

_PAGE_SIZE = 1000
_DAPI_PAGE_SIZE = 5000
_CACHE_TTL_SECONDS = 900
_cache: tuple[float, list[dict[str, Any]]] | None = None


class FINRAOTCDirectoryProvider:
    name = "finra_otc_directory"
    base_url = "https://api.finra.org"
    description = "FINRA OTC Security Master DAPI or approved directory evidence"

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
    if _is_dapi_source(url):
        rows = _fetch_dapi_rows(url)
    else:
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


def _is_dapi_source(url: str) -> bool:
    return urlsplit(url).path.rstrip("/").lower() == (
        "/data/group/otcmarket/name/otcsecuritymaster"
    )


def _dapi_partitions_url(url: str) -> str:
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("FINRA OTC DAPI source URL must be absolute")
    return f"{parsed.scheme}://{parsed.netloc}/partitions/group/otcMarket/name/otcSecurityMaster"


def _fetch_dapi_rows(url: str) -> list[dict[str, Any]]:
    headers = {"User-Agent": settings.NASDAQ_USER_AGENT, "Accept": "application/json"}
    partitions_response = httpx.get(_dapi_partitions_url(url), headers=headers, timeout=30)
    partitions_response.raise_for_status()
    partitions_payload = partitions_response.json()
    partitions = [
        str(partition)
        for item in partitions_payload.get("availablePartitions", [])
        if isinstance(item, dict)
        for partition in item.get("partitions", [])
        if str(partition).strip()
    ]
    if not partitions:
        raise ValueError("FINRA OTC DAPI returned no available asOfDate partitions")
    as_of_date = max(partitions)

    rows: list[dict[str, Any]] = []
    offset = 0
    total: int | None = None
    while True:
        response = httpx.post(
            url,
            headers={**headers, "Content-Type": "application/json"},
            json={
                "compareFilters": [
                    {
                        "fieldName": "asOfDate",
                        "fieldValue": as_of_date,
                        "compareType": "EQUAL",
                    }
                ],
                "sortFields": ["+issueSymbolIdentifier"],
                "limit": _DAPI_PAGE_SIZE,
                "offset": offset,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("FINRA OTC DAPI returned a non-array page")
        if total is None:
            try:
                total = int(response.headers["record-total"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("FINRA OTC DAPI omitted record-total") from exc
            if total < 1:
                raise ValueError("FINRA OTC DAPI returned an empty current security master")
        if not payload:
            raise ValueError("FINRA OTC DAPI ended before record-total was reached")
        rows.extend(_normalize_dapi_row(row) for row in payload if isinstance(row, dict))
        offset += len(payload)
        if offset >= total:
            break
        if len(payload) < _DAPI_PAGE_SIZE:
            raise ValueError("FINRA OTC DAPI page ended before record-total was reached")
    if len(rows) != total:
        raise ValueError(f"FINRA OTC DAPI returned {len(rows)} rows, expected {total}")
    return rows


def _normalize_dapi_row(row: dict[str, Any]) -> dict[str, Any]:
    symbol = str(row.get("issueSymbolIdentifier") or "").strip().upper()
    if not symbol:
        raise ValueError("FINRA OTC DAPI row omitted issueSymbolIdentifier")
    name = str(row.get("securityDescription") or row.get("issuerName") or symbol).strip()
    return {
        "symbol": symbol,
        "longName": name,
        "shortName": name,
        "exchange": "OTC",
        "exchange_mic": "OTC",
        "currency": "USD",
        "quoteType": "EQUITY",
        "instrument_type": "EQUITY",
        "status": "active",
        "financial_status": None,
        "market_category": "OTC Equity",
        "oats_reportable": None,
        "as_of_date": row.get("asOfDate"),
        "finra_issuer_identifier": row.get("finraIssuerIdentifier"),
        "source_record": dict(row),
    }


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
