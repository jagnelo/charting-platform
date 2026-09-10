"""Configurable FINRA OTC Security Master adapter.

FINRA's current OTC site uses the public DAPI ``otcSecurityMaster`` dataset;
the adapter also accepts the documented legacy pipe-delimited directory shape
for an operator-approved mirror or archive. The source URL is still explicit
configuration; the official synchronous request/payload ceilings are recorded
in the provider contract, while source terms, completeness, polling, and
redistribution boundaries remain operator-reviewed gates.
"""

from __future__ import annotations

import csv
import io
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.config import settings
from app.providers.errors import (
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
    provider_response_headers,
    provider_retry_at_from_headers,
)
from app.providers.telemetry import observe_response

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
        try:
            rows = _fetch_dapi_rows(url)
        except ValueError as exc:
            raise ProviderResponseError("finra_otc_directory", str(exc)) from exc
    else:
        try:
            response = httpx.get(
                url,
                headers={"User-Agent": settings.NASDAQ_USER_AGENT, "Accept": "text/plain"},
                timeout=30,
            )
        except httpx.RequestError as exc:
            raise ProviderResponseError("finra_otc_directory", f"transport failure: {exc}") from exc
        observe_response(response)
        _raise_for_provider_status(response)
        try:
            rows = _parse_directory(response.text)
        except csv.Error as exc:
            raise ProviderResponseError(
                "finra_otc_directory", "legacy directory returned malformed CSV"
            ) from exc
    if not rows:
        raise ProviderResponseError("finra_otc_directory", "directory returned no valid rows")
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
    try:
        partitions_response = httpx.get(_dapi_partitions_url(url), headers=headers, timeout=30)
    except httpx.RequestError as exc:
        raise ProviderResponseError("finra_otc_directory", f"transport failure: {exc}") from exc
    observe_response(partitions_response)
    _raise_for_provider_status(partitions_response)
    try:
        partitions_payload = partitions_response.json()
    except (TypeError, ValueError) as exc:
        raise ProviderResponseError(
            "finra_otc_directory", "DAPI partitions response returned invalid JSON"
        ) from exc
    if not isinstance(partitions_payload, dict):
        raise ProviderResponseError(
            "finra_otc_directory", "DAPI partitions response returned an invalid object"
        )
    partitions = [
        str(partition)
        for item in partitions_payload.get("availablePartitions", [])
        if isinstance(item, dict)
        for partition in item.get("partitions", [])
        if str(partition).strip()
    ]
    if not partitions:
        raise ProviderResponseError("finra_otc_directory", "DAPI returned no available partitions")
    as_of_date = max(partitions)

    rows: list[dict[str, Any]] = []
    offset = 0
    total: int | None = None
    while True:
        try:
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
        except httpx.RequestError as exc:
            raise ProviderResponseError("finra_otc_directory", f"transport failure: {exc}") from exc
        observe_response(response)
        _raise_for_provider_status(response)
        try:
            payload = response.json()
        except (TypeError, ValueError) as exc:
            raise ProviderResponseError(
                "finra_otc_directory", "DAPI page returned invalid JSON"
            ) from exc
        if not isinstance(payload, list):
            raise ProviderResponseError("finra_otc_directory", "DAPI page returned a non-array")
        if total is None:
            try:
                total = int(response.headers["record-total"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ProviderResponseError("finra_otc_directory", "DAPI omitted record-total") from exc
            if total < 1:
                raise ProviderResponseError("finra_otc_directory", "DAPI returned an empty security master")
        if not payload:
            raise ProviderResponseError("finra_otc_directory", "DAPI ended before record-total")
        try:
            rows.extend(_normalize_dapi_row(row) for row in payload if isinstance(row, dict))
        except ValueError as exc:
            raise ProviderResponseError("finra_otc_directory", str(exc)) from exc
        previous_offset = offset
        offset += len(payload)
        if offset <= previous_offset or offset > total:
            raise ProviderResponseError("finra_otc_directory", "DAPI returned invalid pagination progress")
        if offset >= total:
            break
        # FINRA may return fewer rows than requested when the response-payload
        # ceiling is reached.  ``record-total`` remains authoritative; keep
        # paging from the number actually returned instead of treating a
        # short page as an incomplete universe.
    if len(rows) != total:
        raise ProviderResponseError(
            "finra_otc_directory", f"DAPI returned {len(rows)} rows, expected {total}"
        )
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
    if not isinstance(text, str):
        raise ProviderResponseError("finra_otc_directory", "legacy directory returned non-text data")
    reader = csv.DictReader(io.StringIO(text), delimiter="|", strict=True)
    if not reader.fieldnames:
        raise ProviderResponseError("finra_otc_directory", "legacy directory omitted CSV headers")
    fields = {str(field).strip().lower() for field in reader.fieldnames if field}
    required = {"issue_sym_id", "issue_short_nm", "status", "mkt_cat"}
    if not required.issubset(fields):
        raise ProviderResponseError(
            "finra_otc_directory", "legacy directory omitted required CSV columns"
        )
    result: list[dict[str, Any]] = []
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ProviderResponseError(
                "finra_otc_directory", "legacy directory returned a malformed CSV row"
            )
        normalized = {
            str(key).strip().lower(): str(value or "").strip() for key, value in row.items() if key
        }
        symbol = normalized.get("issue_sym_id", "").upper()
        if not symbol:
            raise ProviderResponseError(
                "finra_otc_directory", "legacy directory returned a row without issue_sym_id"
            )
        status = normalized.get("status", "").upper()
        market_category = normalized.get("mkt_cat", "")
        if not normalized.get("issue_short_nm") or not status or not market_category:
            raise ProviderResponseError(
                "finra_otc_directory", "legacy directory returned an incomplete CSV row"
            )
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


def _raise_for_provider_status(response: Any) -> None:
    """Convert FINRA OTC HTTP failures into typed, redacted provider errors."""

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        headers = provider_response_headers(response)
        status_code = getattr(response, "status_code", None)
        if status_code in {418, 429}:
            raise ProviderRateLimitError(
                "finra_otc_directory",
                f"FINRA OTC directory request rejected for capacity (HTTP {status_code})",
                status_code=status_code,
                retry_at=provider_retry_at_from_headers(headers),
                scope="ip",
                headers=headers,
            ) from exc
        raise ProviderResponseError(
            "finra_otc_directory",
            f"FINRA OTC directory request failed with HTTP {status_code}",
            status_code=status_code,
        ) from exc
