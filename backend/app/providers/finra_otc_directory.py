"""FINRA-shaped OTC directory parser and discovery adapter.

The DAPI-shaped parser and delimited-file support do not establish that a
particular source URL is currently available or authorized. Runtime routing
requires independent source-evidence and governance controls.
"""

from __future__ import annotations

import csv
import io
import re
import time
from hashlib import sha256
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

from app.config import provider_reviewed_flag, settings
from app.providers.errors import (
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
    provider_response_headers,
    provider_retry_at_from_headers,
)
from app.providers.finra import _access_token, _orf_access_token
from app.providers.telemetry import observe_response

_PAGE_SIZE = 1000
_DAPI_PAGE_SIZE = 5000
_DAPI_MAX_OFFSET = 500_000
_CACHE_TTL_SECONDS = 900
_cache: (
    tuple[
        float,
        list[dict[str, Any]],
        tuple[str, str, str | None, str, str],
        dict[str, str],
    ]
    | None
) = None
_OTC_MARKETS_STATUS_VALUES = {"A", "S", "H", "I", "R"}
_ORF_SOURCE_KIND = "finra_orf_security_master"
_QUERY_API_SOURCE_KIND = "finra_otc_query_api"
_ORF_ACTIVE_STATUSES = {"A", "ACTIVE"}
_QUERY_API_HOST = "api.finra.org"
_QUERY_API_PATH = "/data/group/otcmarket/name/otcsecuritymaster"
_QUERY_API_PARTITIONS_PATH = "/partitions/group/otcmarket/name/otcsecuritymaster"
_dapi_partition_cache: tuple[float, str, str, str] | None = None


class FINRAOTCDirectoryProvider:
    name = "finra_otc_directory"
    base_url = "https://api.finra.org"
    description = "FINRA complete OTC security-master snapshots"

    def discover_universe_page(self, quote_type: str, offset: int) -> dict[str, Any]:
        if quote_type.strip().upper() not in {"EQUITY", "OTC"} or offset < 0:
            return {"total": 0, "quotes": [], "source_files": []}
        source_kind = str(getattr(settings, "FINRA_OTC_SOURCE_KIND", "") or "").strip().lower()
        if source_kind == _QUERY_API_SOURCE_KIND:
            return _fetch_dapi_page(self._source_url(), offset)
        rows = _directory_rows()
        page = rows[offset : offset + _PAGE_SIZE]
        source_documents = (
            dict(_cache[3])
            if offset == 0 and _cache is not None and _cache[2][0] == _ORF_SOURCE_KIND
            else {}
        )
        return {
            "total": len(rows),
            "quotes": page,
            "next_offset": offset + _PAGE_SIZE if offset + _PAGE_SIZE < len(rows) else None,
            "source_files": [url for url in self._source_urls() if url],
            # Persist the exact provider response once, alongside the first
            # discovery page. Later local pages do not duplicate these files.
            "source_documents": source_documents,
        }

    def supported_discovery_types(self) -> list[str]:
        # OTC is a venue scope, not an instrument type. Expose EQUITY to the
        # shared universe reconciler so lifecycle observations and listings use
        # the canonical instrument type; retain OTC as a call-level alias above.
        return ["EQUITY"]

    @staticmethod
    def _source_url() -> str:
        url = str(getattr(settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", "") or "").strip()
        if not url:
            raise ProviderNotConfiguredError(
                "finra_otc_directory requires FINRA_OTC_SYMBOL_DIRECTORY_URL; "
                "the current public directory delivery URL must be operator-approved"
            )
        return url

    @staticmethod
    def _source_urls() -> tuple[str, str | None]:
        """Return configured complete-source snapshot URLs.

        The official Query API security master is the preferred complete OTC
        snapshot. ORF's documented active/inactive file pair remains available
        for separately entitled deployments.
        """

        active = FINRAOTCDirectoryProvider._source_url()
        source_kind = str(getattr(settings, "FINRA_OTC_SOURCE_KIND", "") or "").strip().lower()
        if source_kind == _QUERY_API_SOURCE_KIND:
            _validate_dapi_source_url(active)
            return active, None
        if source_kind != _ORF_SOURCE_KIND:
            raise ProviderNotConfiguredError(
                "finra_otc_directory requires FINRA_OTC_SOURCE_KIND to select the official "
                "FINRA OTC Query API or the separately entitled ORF security-master pair"
            )
        inactive = str(
            getattr(settings, "FINRA_OTC_INACTIVE_SECURITY_MASTER_URL", "") or ""
        ).strip()
        if not inactive:
            raise ProviderNotConfiguredError(
                "finra_otc_directory ORF mode requires FINRA_OTC_INACTIVE_SECURITY_MASTER_URL"
            )
        _validate_orf_source_url(active, expected_file="EQUITYMASTERAC")
        _validate_orf_source_url(inactive, expected_file="EQUITYMASTERIN")
        return active, inactive


def _validate_orf_source_url(url: str, *, expected_file: str) -> None:
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    if parsed.scheme.lower() != "https" or parsed.netloc.lower() != "apidownload.finratraqs.org":
        raise ProviderNotConfiguredError(
            "finra_otc_directory ORF source must use FINRA's apidownload.finratraqs.org HTTPS host"
        )
    if parsed.path.lower() != "/downloadhandler.ashx":
        raise ProviderNotConfiguredError(
            "finra_otc_directory ORF source requires path=/DownloadHandler.ashx"
        )
    if str(query.get("action", [""])[0]).upper() != "DOWNLOAD":
        raise ProviderNotConfiguredError("finra_otc_directory ORF source requires action=DOWNLOAD")
    if str(query.get("facility", [""])[0]).upper() != "ORF":
        raise ProviderNotConfiguredError("finra_otc_directory ORF source requires facility=ORF")
    if str(query.get("file", [""])[0]).upper() != expected_file:
        raise ProviderNotConfiguredError(
            f"finra_otc_directory ORF source requires file={expected_file}"
        )


def _validate_dapi_source_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme.lower() != "https"
        or parsed.netloc.lower() != _QUERY_API_HOST
        or parsed.path.rstrip("/").lower() != _QUERY_API_PATH
        or parsed.query
        or parsed.fragment
    ):
        raise ProviderNotConfiguredError(
            "finra_otc_directory Query API source must be the official FINRA "
            "https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster endpoint"
        )


def _directory_rows() -> list[dict[str, Any]]:
    global _cache
    now = time.monotonic()
    url, inactive_url = FINRAOTCDirectoryProvider._source_urls()
    source_kind = str(getattr(settings, "FINRA_OTC_SOURCE_KIND", "") or "").strip().lower()
    username = str(getattr(settings, "FINRA_ORF_USERNAME", "") or "").strip()
    refresh_token = str(getattr(settings, "FINRA_ORF_REFRESH_TOKEN", "") or "").strip()
    refresh_token_digest = (
        sha256(refresh_token.encode("utf-8")).hexdigest()
        if source_kind == _ORF_SOURCE_KIND and refresh_token
        else ""
    )
    cache_key = (source_kind, url, inactive_url, username, refresh_token_digest)
    if _cache and now - _cache[0] < _CACHE_TTL_SECONDS and _cache[2] == cache_key:
        return list(_cache[1])
    source_documents: dict[str, str] = {}
    if source_kind == _ORF_SOURCE_KIND:
        rows, source_documents = _fetch_orf_rows(url, inactive_url)
    elif _is_dapi_source(url):
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
    _cache = (now, rows, cache_key, source_documents)
    return list(rows)


def _fetch_orf_rows(
    active_url: str, inactive_url: str | None
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Fetch FINRA's documented ORF active/inactive security masters."""

    if not inactive_url:
        raise ProviderNotConfiguredError(
            "finra_otc_directory ORF mode requires an inactive security-master URL"
        )
    username = str(getattr(settings, "FINRA_ORF_USERNAME", "") or "").strip()
    refresh_token = str(getattr(settings, "FINRA_ORF_REFRESH_TOKEN", "") or "").strip()
    if not username or not refresh_token:
        raise ProviderNotConfiguredError(
            "finra_otc_directory ORF mode requires FINRA_ORF_USERNAME and "
            "FINRA_ORF_REFRESH_TOKEN"
        )
    token = _orf_access_token(refresh_token, username)
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": settings.NASDAQ_USER_AGENT,
        "Accept": "text/plain",
    }
    rows: list[dict[str, Any]] = []
    source_documents: dict[str, str] = {}
    seen_keys: set[tuple[str, str]] = set()
    for url, expected_active in ((active_url, True), (inactive_url, False)):
        try:
            # The documented ORF file API is a POST endpoint. The assigned
            # TRAQS username is sent in the form body; the access token comes
            # from the separate refresh-token exchange above.
            response = httpx.post(
                url,
                data={"username": username},
                headers=headers,
                timeout=120,
            )
        except httpx.RequestError as exc:
            raise ProviderResponseError("finra_otc_directory", f"transport failure: {exc}") from exc
        observe_response(response)
        _raise_for_provider_status(response)
        source_documents[url] = response.text
        try:
            parsed = _parse_orf_security_master(response.text, expected_active=expected_active)
        except (csv.Error, ValueError) as exc:
            raise ProviderResponseError(
                "finra_otc_directory", f"ORF security master returned malformed data: {exc}"
            ) from exc
        for row in parsed:
            key = (str(row["symbol"]).upper(), str(row.get("symbol_suffix") or "").upper())
            if key in seen_keys:
                raise ProviderResponseError(
                    "finra_otc_directory",
                    "ORF active and inactive security masters returned a duplicate symbol/suffix",
                )
            seen_keys.add(key)
        rows.extend(parsed)
    if not rows:
        raise ProviderResponseError("finra_otc_directory", "ORF security masters returned no rows")
    return rows, source_documents


def _parse_orf_security_master(text: str, *, expected_active: bool) -> list[dict[str, Any]]:
    """Normalize the documented ORF pipe-delimited security-master shape."""

    if not isinstance(text, str):
        raise ValueError("ORF security master must be text")
    lines = text.splitlines()
    if not lines:
        raise ValueError("ORF security master is empty")
    footer_match = re.fullmatch(
        r"\s*Footer\s*-\s*Count:\s*(\d+)\s*,\s*Facility:\s*ORF\s*,\s*"
        r"File Created:\s*(\d{14})\s*",
        lines[-1],
        flags=re.IGNORECASE,
    )
    if footer_match is None:
        raise ValueError("ORF security master omitted its documented count/timestamp footer")
    expected_row_count = int(footer_match.group(1))
    if expected_row_count <= 0:
        raise ValueError("ORF security master footer declared no rows")
    data_text = "\n".join(lines[:-1])
    reader = csv.DictReader(io.StringIO(data_text), delimiter="|", strict=True)
    if not reader.fieldnames:
        raise ValueError("ORF security master omitted headers")
    fields = {str(field).lstrip("\ufeff").strip().upper() for field in reader.fieldnames if field}
    required = {"FINRA_OTC_ID", "SYM_CD", "SCRTY_DS", "STTS_CD"}
    if not required.issubset(fields):
        raise ValueError("ORF security master omitted required columns")
    result: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("ORF security master returned an inconsistent row")
        normalized = {
            str(key).lstrip("\ufeff").strip().upper(): str(value or "").strip()
            for key, value in row.items()
            if key
        }
        identifier = normalized.get("FINRA_OTC_ID", "")
        symbol = normalized.get("SYM_CD", "").upper()
        description = normalized.get("SCRTY_DS", "")
        status = normalized.get("STTS_CD", "").upper()
        suffix = normalized.get("SYM_SUF_CD", "").upper()
        cusip = normalized.get("CUSIP_ID", "")
        if not identifier or not symbol or not description or not status:
            raise ValueError("ORF security master returned an incomplete row")
        if cusip and not (
            provider_reviewed_flag(getattr(settings, "FINRA_ORF_CUSIP_LICENSED", False))
            and str(getattr(settings, "FINRA_ORF_CUSIP_LICENSE_EVIDENCE", "") or "").strip()
        ):
            raise ValueError(
                "ORF security master contains CUSIP data without recorded CGS license evidence"
            )
        if (status in _ORF_ACTIVE_STATUSES) is not expected_active:
            raise ValueError("ORF active/inactive file disagreed with STTS_CD")
        key = (symbol, suffix)
        if key in seen_keys:
            raise ValueError("ORF security master returned duplicate symbol/suffix")
        seen_keys.add(key)
        result.append(
            {
                "symbol": symbol,
                "symbol_suffix": suffix or None,
                "longName": description,
                "shortName": description,
                "exchange": "OTC",
                "exchange_mic": "OTC",
                "currency": "USD",
                "quoteType": "EQUITY",
                "instrument_type": "EQUITY",
                "status": "active" if expected_active else "inactive",
                "financial_status": status,
                "market_category": "OTC Equity",
                "finra_otc_id": identifier,
                "cusip": cusip or None,
                "inactive_at": normalized.get("NACTV_DT") or None,
                "effective_at": normalized.get("SCRTY_EFCTV_TS") or None,
                "source_record": normalized,
            }
        )
    if not result:
        raise ValueError("ORF security master returned no rows")
    if len(result) != expected_row_count:
        raise ValueError(
            "ORF security master footer count did not match parsed records "
            f"({expected_row_count} != {len(result)})"
        )
    return result


def _is_dapi_source(url: str) -> bool:
    return urlsplit(url).path.rstrip("/").lower() == (
        "/data/group/otcmarket/name/otcsecuritymaster"
    )


def _dapi_partitions_url(url: str) -> str:
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("FINRA OTC DAPI source URL must be absolute")
    return f"{parsed.scheme}://{parsed.netloc}/partitions/group/otcMarket/name/otcSecurityMaster"


def _dapi_auth_headers() -> tuple[dict[str, str], str]:
    client_id = str(getattr(settings, "FINRA_CLIENT_ID", "") or "").strip()
    client_secret = str(getattr(settings, "FINRA_CLIENT_SECRET", "") or "").strip()
    if not client_id or not client_secret:
        raise ProviderNotConfiguredError(
            "finra_otc_directory Query API mode requires FINRA_CLIENT_ID and " "FINRA_CLIENT_SECRET"
        )
    token = _access_token(client_id, client_secret)
    credential_scope = f"{client_id}:{sha256(client_secret.encode('utf-8')).hexdigest()}"
    return (
        {
            "Authorization": f"Bearer {token}",
            "User-Agent": settings.NASDAQ_USER_AGENT,
            "Accept": "application/json",
        },
        credential_scope,
    )


def _dapi_partition(url: str, headers: dict[str, str], credential_scope: str) -> tuple[str, str]:
    global _dapi_partition_cache
    now = time.monotonic()
    cache_key = f"{url}:{credential_scope}"
    if (
        _dapi_partition_cache is not None
        and now - _dapi_partition_cache[0] < _CACHE_TTL_SECONDS
        and _dapi_partition_cache[3] == cache_key
    ):
        return _dapi_partition_cache[1], _dapi_partition_cache[2]
    partitions_url = _dapi_partitions_url(url)
    try:
        partitions_response = httpx.get(partitions_url, headers=headers, timeout=30)
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
    _dapi_partition_cache = (now, as_of_date, partitions_response.text, cache_key)
    return as_of_date, partitions_response.text


def _dapi_header_integer(response: httpx.Response, name: str) -> int:
    try:
        value = int(response.headers[name])
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderResponseError(
            "finra_otc_directory", f"DAPI omitted or invalidated {name}"
        ) from exc
    if value < 0:
        raise ProviderResponseError("finra_otc_directory", f"DAPI returned a negative {name}")
    return value


def _fetch_dapi_page(url: str, offset: int) -> dict[str, Any]:
    """Fetch and retain one lossless FINRA OTC Query API page."""

    _validate_dapi_source_url(url)
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("FINRA OTC DAPI offset must be a non-negative integer")
    if offset > _DAPI_MAX_OFFSET:
        raise ProviderResponseError(
            "finra_otc_directory",
            "DAPI universe exceeded FINRA's 500,000 maximum offset; filtered tranches are "
            "required and the partial snapshot must not be treated as complete",
        )
    headers, credential_scope = _dapi_auth_headers()
    as_of_date, partitions_text = _dapi_partition(url, headers, credential_scope)

    request_payload = {
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
    }
    try:
        response = httpx.post(
            url,
            headers={**headers, "Content-Type": "application/json"},
            json=request_payload,
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
    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise ProviderResponseError(
            "finra_otc_directory", "DAPI page returned a non-array or non-object row"
        )
    total = _dapi_header_integer(response, "record-total")
    response_offset = _dapi_header_integer(response, "record-offset")
    record_limit = _dapi_header_integer(response, "record-limit")
    record_max_limit = _dapi_header_integer(response, "record-max-limit")
    if total < 1:
        raise ProviderResponseError("finra_otc_directory", "DAPI returned an empty security master")
    if response_offset != offset:
        raise ProviderResponseError(
            "finra_otc_directory", "DAPI response offset did not match the requested offset"
        )
    if record_limit > record_max_limit or record_limit > _DAPI_PAGE_SIZE:
        raise ProviderResponseError(
            "finra_otc_directory", "DAPI returned an invalid record-limit contract"
        )
    if not payload and offset < total:
        raise ProviderResponseError("finra_otc_directory", "DAPI ended before record-total")
    try:
        rows = [_normalize_dapi_row(row) for row in payload]
    except ValueError as exc:
        raise ProviderResponseError("finra_otc_directory", str(exc)) from exc
    symbols = [str(row["symbol"]) for row in rows]
    if len(symbols) != len(set(symbols)):
        raise ProviderResponseError(
            "finra_otc_directory", "DAPI page returned duplicate issue symbols"
        )
    if any(str(row.get("as_of_date") or "") != as_of_date for row in rows):
        raise ProviderResponseError(
            "finra_otc_directory", "DAPI row partition did not match the requested asOfDate"
        )
    next_offset = offset + len(rows)
    if next_offset > total or (next_offset <= offset and next_offset < total):
        raise ProviderResponseError(
            "finra_otc_directory", "DAPI returned invalid pagination progress"
        )
    partitions_url = _dapi_partitions_url(url)
    page_evidence_key = f"{url}?asOfDate={as_of_date}&offset={offset}&limit={_DAPI_PAGE_SIZE}"
    return {
        "total": total,
        "quotes": rows,
        "next_offset": next_offset if next_offset < total else None,
        "complete": next_offset == total,
        "source_snapshot_date": as_of_date,
        "source_files": [partitions_url, url],
        "source_documents": {
            **({partitions_url: partitions_text} if offset == 0 else {}),
            page_evidence_key: response.text,
        },
    }


def _fetch_dapi_rows(url: str) -> list[dict[str, Any]]:
    """Compatibility helper that follows every Query API page without truncation."""

    rows: list[dict[str, Any]] = []
    offset = 0
    total: int | None = None
    seen_symbols: set[str] = set()
    while True:
        page = _fetch_dapi_page(url, offset)
        page_total = int(page["total"])
        if total is None:
            total = page_total
        elif total != page_total:
            raise ProviderResponseError(
                "finra_otc_directory", "DAPI changed record-total during pagination"
            )
        page_rows = list(page["quotes"])
        for row in page_rows:
            symbol = str(row["symbol"])
            if symbol in seen_symbols:
                raise ProviderResponseError(
                    "finra_otc_directory", "DAPI returned a duplicate issue symbol across pages"
                )
            seen_symbols.add(symbol)
        rows.extend(page_rows)
        next_offset = page.get("next_offset")
        if next_offset is None:
            break
        offset = int(next_offset)
    if total is None or len(rows) != total:
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
        raise ProviderResponseError(
            "finra_otc_directory", "legacy directory returned non-text data"
        )
    reader = csv.DictReader(io.StringIO(text), delimiter="|", strict=True)
    if not reader.fieldnames:
        raise ProviderResponseError("finra_otc_directory", "legacy directory omitted CSV headers")
    fields = {str(field).lstrip("\ufeff").strip().lower() for field in reader.fieldnames if field}
    if {
        "date",
        "secid",
        "compid",
        "symbol",
        "security status",
    }.issubset(fields):
        return _parse_otc_markets_security_master(reader)
    required = {"issue_sym_id", "issue_short_nm", "status", "mkt_cat"}
    if not required.issubset(fields):
        raise ProviderResponseError(
            "finra_otc_directory", "legacy directory omitted required CSV columns"
        )
    result: list[dict[str, Any]] = []
    for row in _checked_csv_rows(reader, "legacy OTC directory"):
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


def parse_otc_markets_security_master(
    text: str,
    *,
    validation_text: str | None = None,
) -> list[dict[str, Any]]:
    """Parse an OTC Markets security-master file and its optional validation file.

    The OTC Markets specification delivers a validation file alongside each
    security-master snapshot.  The validation record count is the only source
    of completeness evidence available from the file pair, so callers that
    have both files should always provide ``validation_text``.  The network
    adapter deliberately does not fetch or infer a companion URL: source
    delivery and entitlement remain separately gated.
    """

    if not isinstance(text, str):
        raise ProviderResponseError(
            "finra_otc_directory", "OTC Markets security master must be text"
        )
    reader = csv.DictReader(io.StringIO(text), delimiter="|", strict=True)
    if not reader.fieldnames:
        raise ProviderResponseError(
            "finra_otc_directory", "OTC Markets security master omitted CSV headers"
        )
    fields = {str(field).lstrip("\ufeff").strip().lower() for field in reader.fieldnames if field}
    required_fields = {"date", "secid", "compid", "symbol", "security status"}
    if not required_fields.issubset(fields):
        raise ProviderResponseError(
            "finra_otc_directory",
            "OTC Markets security master omitted required CSV columns",
        )
    rows = _parse_otc_markets_security_master(reader)
    if validation_text is not None:
        expected_count = _parse_otc_markets_validation_file(validation_text)
        if expected_count != len(rows):
            raise ProviderResponseError(
                "finra_otc_directory",
                "OTC Markets validation record count does not match security master",
            )
    return rows


def _parse_otc_markets_validation_file(text: str) -> int:
    """Return the record count from an OTC Markets validation file.

    The specification requires one pipe-delimited record with ``Datafile``,
    ``Source``, ``Date/Time``, and ``Record Count`` fields.  Do not accept a
    bare integer or a multi-record file: that would discard the provenance
    needed to prove which snapshot was checked.
    """

    if not isinstance(text, str):
        raise ProviderResponseError(
            "finra_otc_directory", "OTC Markets validation file must be text"
        )
    reader = csv.DictReader(io.StringIO(text), delimiter="|", strict=True)
    if not reader.fieldnames:
        raise ProviderResponseError(
            "finra_otc_directory", "OTC Markets validation file omitted CSV headers"
        )
    rows = list(reader)
    if len(rows) != 1 or None in rows[0] or any(value is None for value in rows[0].values()):
        raise ProviderResponseError(
            "finra_otc_directory",
            "OTC Markets validation file must contain exactly one complete row",
        )
    normalized = {
        str(key).lstrip("\ufeff").strip().lower(): str(value or "").strip()
        for key, value in rows[0].items()
        if key
    }
    required_fields = {"datafile", "source", "date/time", "record count"}
    if not required_fields.issubset(normalized) or any(
        not normalized[field] for field in required_fields
    ):
        raise ProviderResponseError(
            "finra_otc_directory",
            "OTC Markets validation file omitted required provenance fields",
        )
    if normalized["source"].casefold() != "otc markets group":
        raise ProviderResponseError(
            "finra_otc_directory",
            "OTC Markets validation file has an unexpected source",
        )
    try:
        count = int(normalized["record count"], 10)
    except (TypeError, ValueError) as exc:
        raise ProviderResponseError(
            "finra_otc_directory", "OTC Markets validation file has an invalid record count"
        ) from exc
    if count < 1:
        raise ProviderResponseError(
            "finra_otc_directory", "OTC Markets validation file has an invalid record count"
        )
    return count


def _parse_otc_markets_security_master(reader: csv.DictReader) -> list[dict[str, Any]]:
    """Normalize the official OTC Markets pipe-delimited security-master shape.

    The OTC Markets specification defines a complete snapshot rather than a
    FINRA Daily List delta.  Keep its SecID/CompID/CUSIP and status fields in
    the raw record, reject malformed rows and duplicate symbols, and never
    silently collapse a conflicting snapshot.
    """

    result: list[dict[str, Any]] = []
    seen_symbols: set[str] = set()
    for row in _checked_csv_rows(reader, "OTC Markets security master"):
        if None in row or any(value is None for value in row.values()):
            raise ProviderResponseError(
                "finra_otc_directory",
                "OTC Markets security master returned a malformed pipe-delimited row",
            )
        normalized = {
            str(key).lstrip("\ufeff").strip().lower(): str(value or "").strip()
            for key, value in row.items()
            if key
        }
        required_values = ("date", "secid", "compid", "symbol", "security status")
        if any(not normalized.get(field) for field in required_values):
            raise ProviderResponseError(
                "finra_otc_directory",
                "OTC Markets security master returned an incomplete row",
            )
        symbol = normalized["symbol"].upper()
        if symbol in seen_symbols:
            raise ProviderResponseError(
                "finra_otc_directory",
                f"OTC Markets security master returned duplicate symbol {symbol}",
            )
        seen_symbols.add(symbol)
        status_code = normalized["security status"].upper()
        if status_code not in _OTC_MARKETS_STATUS_VALUES:
            raise ProviderResponseError(
                "finra_otc_directory",
                f"OTC Markets security master returned unknown security status {status_code}",
            )
        name = normalized.get("security name") or normalized.get("company name") or symbol
        result.append(
            {
                "symbol": symbol,
                "longName": name,
                "shortName": name,
                "exchange": "OTC",
                "exchange_mic": "OTC",
                "currency": "USD",
                "quoteType": "EQUITY",
                "instrument_type": "EQUITY",
                "status": "active" if status_code == "A" else "inactive",
                "financial_status": status_code,
                "market_category": normalized.get("otc tier") or "OTC",
                "otc_tier": normalized.get("otc tier") or None,
                "otc_tier_id": normalized.get("tier id") or None,
                "security_id": normalized["secid"],
                "company_id": normalized["compid"],
                "cusip": normalized.get("cusip") or None,
                "as_of_date": normalized["date"],
                "overnight_eligible": normalized.get("overnight eligible") or None,
                "reference_price": normalized.get("reference price") or None,
                "source_record": normalized,
            }
        )
    if not result:
        raise ProviderResponseError(
            "finra_otc_directory", "OTC Markets security master returned no rows"
        )
    return result


def _checked_csv_rows(reader: csv.DictReader, source_label: str):
    """Translate strict CSV parser errors into a typed provider response error."""

    try:
        yield from reader
    except csv.Error as exc:
        raise ProviderResponseError(
            "finra_otc_directory", f"{source_label} returned malformed CSV"
        ) from exc


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
