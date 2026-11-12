from __future__ import annotations

import asyncio
import base64
import csv
import hashlib
import json
import re
import time
import zipfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from io import BytesIO, StringIO
from typing import Any

import httpx as _httpx
from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.asset_class import InstrumentType
from app.models.data_source import DataSource
from app.models.etf_holdings import (
    ETFHolding,
    ETFHoldingsAdapterState,
    ETFHoldingsBackfillJob,
    ETFHoldingsRawArtifact,
    ETFHoldingsSnapshot,
    ETFProfile,
)
from app.models.instrument import Instrument
from app.models.provider_runtime import ProviderCapability, ProviderRequestLog
from app.providers.base import IdentifierRecord
from app.providers.errors import ProviderRateLimitError, bounded_redact_provider_message
from app.services.etf_consumer_types import (
    is_equity_holding_type,
    is_placeholder_symbol,
    normalize_holding_type,
)
from app.services.etf_holdings import (
    ETF_HOLDINGS_INTERNAL_PROVIDER,
    _ensure_holdings_dates_are_not_future,
    _hash_payload,
    _schema_fingerprint,
    ensure_etf_profile,
    ensure_lightweight_etf_instrument,
    get_etf_profile_for_instrument,
    get_latest_snapshot,
    ingest_holdings_snapshot,
    reconcile_snapshot_constituents,
)
from app.services.etf_holdings_adapters import (
    ETFNativeSourceEvidenceError,
    HoldingsAdapterProbe,
    get_holdings_adapter,
    infer_adapter_key,
    known_etf_route_metadata,
    parse_etf_discovery_csv,
    parse_etf_discovery_table,
    parse_xlsx_table,
)
from app.services.etf_holdings_capability import (
    evaluate_capability,
    freshness_deadline,
    infer_expected_cadence,
)
from app.services.etf_holdings_provider_bridge import (
    ETFHoldingsRouteHeldError,
    ProviderBackedHTTPXClient,
    _canonical_request_url,
    bind_etf_holdings_request_context,
    require_unbound_etf_holdings_context,
)
from app.services.instrument_mastering import register_identifier
from app.services.provider_quota_coordinator import ProviderQuotaAdmissionError
from app.services.top_down_taxonomy import BENCHMARK_FAMILY_REGISTRY


class _ETFRefreshHTTPXNamespace:
    """Keep discovery transports fail-closed until they have reviewed bindings."""

    def AsyncClient(self, *args, **kwargs):
        if args:
            raise ETFHoldingsRouteHeldError(
                "ETF refresh clients require keyword-only shared-admission configuration"
            )
        return ProviderBackedHTTPXClient(**kwargs)

    def __getattr__(self, name):
        return getattr(_httpx, name)


# Discovery/enrichment calls are not yet bound to an evidence-reviewed ETF
# operation. They must fail closed instead of bypassing Provider with raw HTTPX.
httpx = _ETFRefreshHTTPXNamespace()


class ETFHoldingsRouteNotReadyError(ValueError):
    """Raised when an ETF matched an adapter but lacks route metadata."""


class ETFHoldingsSchemaDriftError(ValueError):
    """Raised when an unchanged parser receives a different artifact shape."""

    def __init__(self, *, previous: str, observed: str, parser_version: str):
        self.previous_fingerprint = previous
        self.observed_fingerprint = observed
        self.parser_version = parser_version
        super().__init__(
            "ETF holdings source schema fingerprint drift detected "
            f"(previous={previous}, observed={observed}, parser={parser_version})."
        )


@dataclass(slots=True)
class ETFHoldingsBootstrapResult:
    profile: ETFProfile
    probe: HoldingsAdapterProbe
    refresh_attempted: bool
    refresh_succeeded: bool
    message: str | None = None


@dataclass(slots=True)
class ETFHoldingsAcquireResult:
    profile: ETFProfile | None
    outcome: str
    refresh: bool
    refresh_attempted: bool
    refresh_succeeded: bool
    snapshot: Any | None
    snapshot_id: int | None
    source_provider: str | None
    source_operation: str | None
    provider_request_log_ids: list[int]
    message: str | None = None
    instrument_id: int | None = None
    symbol: str | None = None
    reason_code: str | None = None
    retry_at: datetime | None = None


SEC_FUND_TICKERS_URL = "https://www.sec.gov/files/company_tickers_mf.json"

_BENCHMARK_FAMILY_ROLES = ("cap_weight", "equal_weight", "value", "growth")
USABLE_HOLDINGS_COMPLETENESS = frozenset({"complete", "filing_reconstructed"})


def _explicit_etf_acquisition_binder():
    """Return the staged Provider binder without supplying a local fallback."""

    from app.services import provider_runtime  # noqa: PLC0415

    binder = getattr(provider_runtime, "bind_explicit_etf_holdings_acquisition", None)
    return binder if callable(binder) else None


_DECLARED_HOLDINGS_COMPLETENESS_BY_SOURCE_QUALITY = {
    "filing_reconstructed_holdings": "filing_reconstructed",
    "issuer_reported_dated_complete_holdings": "complete",
    "issuer_reported_complete_daily_holdings_csv": "complete",
    "issuer_reported_full_investment_holdings": "complete",
    "issuer_page_declared_current_complete_holdings": "complete",
    "issuer_reported_product_page_holdings_table": "complete",
}


def _holdings_completeness_status(
    result_metadata: dict[str, Any] | None,
    aliases: dict[str, Any] | None,
) -> str:
    """Resolve explicit completeness and narrowly declared legacy quality labels."""

    metadata = result_metadata or {}
    configured_aliases = aliases or {}
    native_completeness = metadata.get("native_composition_completeness_evidence")
    if isinstance(native_completeness, dict):
        if (
            native_completeness.get("status") == "complete"
            and native_completeness.get("verified") is True
            and native_completeness.get("all_reported_rows_parsed") is True
        ):
            return "complete"
        return "incomplete"
    explicit = metadata.get("completeness_status") or configured_aliases.get(
        "holdings_completeness_status"
    )
    if explicit:
        return str(explicit)
    source_quality = (
        str(
            metadata.get("source_quality")
            or configured_aliases.get("holdings_source_quality")
            or ""
        )
        .strip()
        .lower()
    )
    return _DECLARED_HOLDINGS_COMPLETENESS_BY_SOURCE_QUALITY.get(source_quality, "unknown")


_NATIVE_COMPOSITION_COMPLETENESS_BASES = {
    "spdr": "spdr_fund_scoped_daily_holdings_workbook",
    "invesco": "invesco_total_number_of_holdings",
    "ishares": "blackrock_holdings_all_container",
    "amplify": "amplify_full_multi_account_csv_selected_account",
}


def _verified_native_composition_completeness(
    *, profile: ETFProfile, adapter: Any, fetch_result: Any
) -> dict[str, Any]:
    """Validate adapter row accounting before a native snapshot can be current."""

    metadata = fetch_result.legal_metadata if isinstance(fetch_result.legal_metadata, dict) else {}
    provider = str(getattr(adapter, "source_provider", "")).strip().lower()
    expected_basis = _NATIVE_COMPOSITION_COMPLETENESS_BASES.get(provider)
    evidence = metadata.get("native_composition_completeness")
    rows = fetch_result.rows if isinstance(fetch_result.rows, list) else []
    reported_rows = evidence.get("reported_rows") if isinstance(evidence, dict) else None
    parsed_rows = evidence.get("parsed_rows") if isinstance(evidence, dict) else None
    counts_match = (
        isinstance(reported_rows, int)
        and not isinstance(reported_rows, bool)
        and reported_rows > 0
        and isinstance(parsed_rows, int)
        and not isinstance(parsed_rows, bool)
        and parsed_rows == len(rows) == reported_rows
    )
    checks_pass = bool(
        expected_basis is not None
        and isinstance(evidence, dict)
        and evidence.get("status") == "complete"
        and evidence.get("basis") == expected_basis
        and evidence.get("all_reported_rows_parsed") is True
        and counts_match
    )
    if provider == "spdr":
        checks_pass = checks_pass and bool(
            evidence.get("fund_identity_present") is True
            and evidence.get("provider_date_present") is True
            and evidence.get("malformed_rows") == 0
        )
    elif provider == "invesco":
        checks_pass = checks_pass and bool(
            evidence.get("authoritative_total_matches") is True
            and evidence.get("response_rows") == parsed_rows
            and evidence.get("continuation_clear") is True
        )
    elif provider == "ishares":
        checks_pass = checks_pass and bool(
            evidence.get("core_columns_aligned") is True
            and evidence.get("all_list_columns_aligned") is True
            and evidence.get("authoritative_total_matches") is True
            and evidence.get("continuation_clear") is True
        )
    elif provider == "amplify":
        expected_symbol = (
            profile.instrument.symbol.strip().upper() if profile.instrument is not None else ""
        )
        checks_pass = checks_pass and bool(
            evidence.get("account") == expected_symbol
            and evidence.get("full_csv_parsed") is True
            and evidence.get("malformed_rows") == 0
            and evidence.get("missing_dates") == 0
            and evidence.get("composition_date_count") == 1
        )
    if not checks_pass:
        observed = evidence.get("status") if isinstance(evidence, dict) else "missing"
        reason = evidence.get("reason") if isinstance(evidence, dict) else None
        raise ETFNativeSourceEvidenceError(
            "Native holdings composition completeness is not proven "
            f"(provider={provider}, status={observed}, reason={reason or 'row accounting did not match'})."
        )
    payload = fetch_result.raw_json if fetch_result.raw_json is not None else fetch_result.raw_text
    return {
        **evidence,
        "status": "complete",
        "verified": True,
        "all_reported_rows_parsed": True,
        "reported_rows": reported_rows,
        "parsed_rows": parsed_rows,
        "source_payload_hash": _hash_payload(payload),
    }


_CANARY_HISTORY_KEY = "canary_history"
_CANARY_HISTORY_LIMIT = 90


def _state_metadata(value: Any) -> dict[str, Any]:
    """Return persisted adapter metadata in the dictionary shape we require."""

    return value if isinstance(value, dict) else {}


_VANECK_OIH_RAW_WORKBOOK_SCHEMA_FIELDS = frozenset(
    {"raw_workbook_base64", "raw_workbook_sha256", "raw_workbook_bytes"}
)
_VANECK_OIH_RETAINED_WORKBOOK_COLUMNS = (
    "Number",
    "Ticker",
    "Holding Name",
    "Identifier (FIGI)",
    "Shares",
    "Asset Class",
    "Market Value (US$)",
    "Notional Value",
    "% of Net Assets",
)


def _vaneck_oih_schema_fingerprints(
    profile: ETFProfile,
    adapter: Any,
    fetch_result: Any,
    *,
    parser_version: str,
    verified_body_identity: list[str] | None,
) -> tuple[str | None, str | None]:
    """Fingerprint OIH's parsed XLSX schema independently of retained raw diagnostics.

    The qualification response carries raw workbook diagnostics in its stored
    JSON envelope; ordinary refresh carries the same parsed workbook rows
    without those diagnostics. Only this exact, already body-verified OIH
    adapter path may normalize that envelope difference.
    """

    metadata = fetch_result.legal_metadata if isinstance(fetch_result.legal_metadata, dict) else {}
    instrument = getattr(profile, "instrument", None)
    payload = fetch_result.raw_json
    if not (
        str(getattr(adapter, "adapter_key", "")).strip().lower() == "vaneck"
        and str(getattr(adapter, "source_provider", "")).strip().lower() == "vaneck"
        and instrument is not None
        and str(getattr(instrument, "symbol", "")).strip().upper() == "OIH"
        and fetch_result.source_identifier == "oil-services-etf-oih"
        and metadata.get("source_provider") == "vaneck"
        and metadata.get("adapter_key") == "vaneck"
        and metadata.get("product_slug") == "oil-services-etf-oih"
        and metadata.get("source_format") == "xlsx"
        and metadata.get("body_identity_status") == "matched"
        and isinstance(verified_body_identity, list)
        and bool(verified_body_identity)
        and parser_version == "vaneck-xlsx-v1"
        and isinstance(payload, dict)
    ):
        return None, None

    base_fields = {"source_format", "workbook_rows"}
    payload_fields = set(payload)
    has_diagnostics = payload_fields == base_fields | _VANECK_OIH_RAW_WORKBOOK_SCHEMA_FIELDS
    if payload_fields != base_fields and not has_diagnostics:
        return None, None
    if payload.get("source_format") != "xlsx" or not isinstance(payload.get("workbook_rows"), list):
        return None, None
    if has_diagnostics and not (
        isinstance(payload.get("raw_workbook_base64"), str)
        and re.fullmatch(r"[0-9a-f]{64}", str(payload.get("raw_workbook_sha256") or ""))
        and isinstance(payload.get("raw_workbook_bytes"), int)
        and not isinstance(payload.get("raw_workbook_bytes"), bool)
        and payload["raw_workbook_bytes"] > 0
    ):
        return None, None

    workbook_rows = payload["workbook_rows"]
    header_row_index = 2
    header_row = (
        workbook_rows[header_row_index]
        if len(workbook_rows) > header_row_index
        and isinstance(workbook_rows[header_row_index], list)
        else None
    )
    parsed_schema = {
        "source_format": payload["source_format"],
        "workbook_rows": workbook_rows,
        # `_payload_schema_shape` intentionally summarizes arrays by element
        # type. Include the actual OIH column row so workbook header changes
        # remain visible to this source-specific drift contract.
        "workbook_header": {
            f"row_{header_row_index}": (
                {
                    f"{index}:{column}": "column"
                    for index, column in enumerate(header_row)
                    if isinstance(column, str)
                }
                if header_row is not None
                else None
            )
        },
    }
    observed = _schema_fingerprint(raw_payload_json=parsed_schema)
    legacy_qualification = None
    if not has_diagnostics and header_row == list(_VANECK_OIH_RETAINED_WORKBOOK_COLUMNS):
        # Existing deployed qualification rows used this exact diagnostic-
        # expanded shape. This is only a compatibility witness; the next
        # successful ordinary refresh stores `observed` in adapter state.
        legacy_payload = {
            "source_format": payload["source_format"],
            "workbook_rows": workbook_rows,
            "raw_workbook_base64": "",
            "raw_workbook_sha256": "",
            "raw_workbook_bytes": 0,
        }
        legacy_qualification = _schema_fingerprint(raw_payload_json=legacy_payload)
    return observed, legacy_qualification


def _failure_streak(value: Any) -> int:
    """Read a persisted failure streak without allowing malformed JSON to abort a run."""

    metadata = _state_metadata(value)
    try:
        return max(0, int(metadata.get("consecutive_failures") or 0))
    except (TypeError, ValueError):
        return 0


def _append_canary_observation(
    metadata: dict[str, Any], observation: dict[str, Any]
) -> dict[str, Any]:
    """Keep a bounded, JSON-safe history for shadow-gate evaluation."""

    metadata = _state_metadata(metadata)
    existing = metadata.get(_CANARY_HISTORY_KEY)
    history = (
        [item for item in existing if isinstance(item, dict)] if isinstance(existing, list) else []
    )
    return {
        **metadata,
        _CANARY_HISTORY_KEY: [*history, observation][-_CANARY_HISTORY_LIMIT:],
    }


def holdings_snapshot_is_bootstrap_ready(snapshot: ETFHoldingsSnapshot | None) -> bool:
    """Return whether a stored snapshot can suppress another provider attempt.

    Presence alone is insufficient: partial/unknown snapshots are useful
    coverage evidence but cannot make a locked source retry-ineligible.
    """

    if (
        snapshot is None
        or getattr(snapshot, "completeness_status", None) not in USABLE_HOLDINGS_COMPLETENESS
    ):
        return False

    rows = getattr(snapshot, "holdings", None)
    if rows is None:
        rows = getattr(snapshot, "rows", None)
    if rows is not None:
        return any(
            normalize_holding_type(getattr(row, "row_type", None)) == "security"
            and is_equity_holding_type(getattr(row, "holding_type", None))
            and bool(getattr(row, "is_resolved", False))
            and getattr(row, "constituent_instrument_id", None) is not None
            and (
                getattr(row, "constituent_symbol", None)
                or getattr(getattr(row, "constituent_instrument", None), "symbol", None)
            )
            and not is_placeholder_symbol(
                getattr(row, "constituent_symbol", None)
                or getattr(getattr(row, "constituent_instrument", None), "symbol", None)
            )
            for row in rows
        )

    # Metadata-only legacy snapshots have no materialized detail to inspect.
    return int(getattr(snapshot, "resolved_count", 0) or 0) > 0


@asynccontextmanager
async def _bootstrap_savepoint(db: AsyncSession):
    nested = db.begin_nested()
    if hasattr(nested, "__aenter__"):
        async with nested:
            yield
        return
    with nested:
        yield


def _parse_discovery_response(source_url: str, response) -> list:
    raw_content = getattr(response, "content", None)
    content_type = ""
    headers = getattr(response, "headers", None)
    if headers is not None:
        content_type = str(headers.get("content-type", "")).lower()
    source_format = (
        "zip"
        if (source_url.lower().endswith(".zip") or "zip" in content_type)
        else "xlsx"
        if (
            source_url.lower().endswith((".xlsx", ".xlsm"))
            or "spreadsheetml" in content_type
            or "excel" in content_type
            or (isinstance(raw_content, bytes) and raw_content.startswith(b"PK"))
        )
        else "csv"
    )

    if source_format == "zip":
        if not isinstance(raw_content, bytes):
            raw_content = response.text.encode()
        return _parse_discovery_zip(raw_content)
    if source_format == "xlsx":
        if not isinstance(raw_content, bytes):
            raw_content = response.text.encode()
        return parse_etf_discovery_table(parse_xlsx_table(raw_content))
    return parse_etf_discovery_csv(response.text)


def _parse_discovery_zip(raw_archive: bytes) -> list:
    with zipfile.ZipFile(BytesIO(raw_archive)) as archive:
        file_names = [
            name
            for name in archive.namelist()
            if not name.endswith("/")
            and name.lower().endswith((".csv", ".xlsx", ".xlsm"))
            and "__macosx/" not in name.lower()
        ]

        def score(name: str) -> tuple[int, str]:
            lowered = name.lower()
            value = 0
            if "fund" in lowered:
                value += 30
            if "etf" in lowered:
                value += 25
            if "product" in lowered:
                value += 20
            if "list" in lowered:
                value += 15
            if lowered.endswith(".csv"):
                value += 10
            return -value, name

        for file_name in sorted(file_names, key=score):
            raw_file = archive.read(file_name)
            if file_name.lower().endswith((".xlsx", ".xlsm")):
                rows = parse_etf_discovery_table(parse_xlsx_table(raw_file))
            else:
                rows = parse_etf_discovery_csv(raw_file.decode("utf-8-sig", errors="replace"))
            if rows:
                return rows
    return []


def _normalize_sec_cik(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return text.zfill(10)
    return text


def _first_row_value(row: dict[str, Any], *keys: str) -> Any:
    lowered = {str(key).strip().lower(): value for key, value in row.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value not in (None, ""):
            return value
    return None


def _rows_from_sec_fund_tickers_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []

    fields = payload.get("fields")
    data = payload.get("data")
    if isinstance(fields, list) and isinstance(data, list):
        normalized_fields = [str(field) for field in fields]
        rows: list[dict[str, Any]] = []
        for item in data:
            if isinstance(item, list):
                rows.append(dict(zip(normalized_fields, item, strict=False)))
            elif isinstance(item, dict):
                rows.append(item)
        if rows:
            return rows

    return [row for row in payload.values() if isinstance(row, dict)]


def _parse_sec_fund_ticker_rows(payload: Any) -> list[dict[str, Any]]:
    parsed_rows: list[dict[str, Any]] = []
    for raw_row in _rows_from_sec_fund_tickers_payload(payload):
        ticker = _first_row_value(raw_row, "ticker", "symbol")
        if not ticker:
            continue
        symbol = str(ticker).strip().upper()
        cik = _normalize_sec_cik(_first_row_value(raw_row, "cik_str", "cik", "cikStr"))
        series_id = _first_row_value(raw_row, "seriesId", "series_id", "series")
        class_id = _first_row_value(raw_row, "classId", "class_id", "class")
        name = _first_row_value(raw_row, "title", "name", "company_name", "fund_name")
        parsed_rows.append(
            {
                "symbol": symbol,
                "name": str(name).strip() if name else symbol,
                "sec_cik": cik,
                "sec_series_id": str(series_id).strip() if series_id else None,
                "sec_class_id": str(class_id).strip() if class_id else None,
                "raw_row": raw_row,
            }
        )
    return parsed_rows


async def _register_optional_identifier(
    db: AsyncSession,
    instrument,
    identifier_type: str,
    identifier_value: str | None,
    source_provider: str,
) -> None:
    if not identifier_value:
        return
    await register_identifier(
        db,
        instrument,
        ETF_HOLDINGS_INTERNAL_PROVIDER,
        IdentifierRecord(
            identifier_type=identifier_type,
            identifier_value=identifier_value.strip().upper(),
            is_primary=identifier_type == "isin",
            source=source_provider,
        ),
    )


async def discover_etf_profiles_from_issuer_feed(
    db: AsyncSession,
    *,
    adapter_key: str,
    source_url: str,
    issuer: str | None = None,
    fund_family: str | None = None,
) -> dict:
    """Fetch a confirmed issuer ETF list and upsert ETF profiles from it."""

    require_unbound_etf_holdings_context("ETF issuer discovery")
    adapter = get_holdings_adapter(adapter_key)
    if adapter is None:
        raise ValueError(f"No ETF holdings adapter is registered for {adapter_key}.")

    async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
        response = await client.get(
            source_url,
            headers={"User-Agent": settings.EDGAR_USER_AGENT},
            follow_redirects=True,
        )
    response.raise_for_status()

    rows = _parse_discovery_response(source_url, response)
    created = 0
    updated = 0
    skipped = 0
    symbols: list[str] = []
    for row in rows:
        if not row.symbol:
            skipped += 1
            continue
        instrument = await ensure_lightweight_etf_instrument(
            db,
            symbol=row.symbol,
            name=row.name or row.symbol,
        )
        existing_profile = await get_etf_profile_for_instrument(db, instrument.id)
        provider_aliases = {
            key: value
            for key, value in {
                "issuer_product_id": row.issuer_product_id,
                "holdings_url": row.holdings_url,
                "holdings_url_template": row.holdings_url_template,
                "dated_holdings_url_template": row.dated_holdings_url_template,
                "figi": row.figi,
                "composite_figi": row.composite_figi,
                "share_class_figi": row.share_class_figi,
                "sec_cik": row.sec_cik,
                "sec_series_id": row.sec_series_id,
                "sec_class_id": row.sec_class_id,
                "discovery_source_url": source_url,
                "discovery_adapter_key": adapter_key,
            }.items()
            if value
        }
        profile = await ensure_etf_profile(
            db,
            instrument,
            issuer=row.issuer or issuer or adapter.source_provider,
            fund_family=row.fund_family or fund_family,
            product_url=row.product_url,
            sec_cik=row.sec_cik,
            sec_series_id=row.sec_series_id,
            sec_class_id=row.sec_class_id,
            provider_aliases={
                **((existing_profile.provider_aliases or {}) if existing_profile else {}),
                **provider_aliases,
            },
            legal_metadata={
                **((existing_profile.legal_metadata or {}) if existing_profile else {}),
                "discovery_source_url": source_url,
                "discovery_source_provider": adapter.source_provider,
                "discovery_source_access": "issuer_public_fund_list",
            },
        )
        if row.extra_data:
            profile.extra_data = {
                **(profile.extra_data or {}),
                "last_discovery_row": row.extra_data,
            }
        profile.adapter_key = adapter.adapter_key
        profile.adapter_status = "candidate"
        profile.adapter_confidence = Decimal("0.8500")
        for identifier_type, value in [
            ("cusip", row.cusip),
            ("isin", row.isin),
            ("figi", row.figi),
            ("composite_figi", row.composite_figi),
            ("figi", row.share_class_figi),
        ]:
            await _register_optional_identifier(
                db, instrument, identifier_type, value, adapter.source_provider
            )
        created += 1 if existing_profile is None else 0
        updated += 0 if existing_profile is None else 1
        symbols.append(instrument.symbol)

    await db.flush()
    return {
        "adapter_key": adapter_key,
        "source_url": source_url,
        "discovered": len(rows),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "symbols": symbols,
    }


async def discover_etf_profiles_from_sec_fund_tickers(
    db: AsyncSession,
    *,
    source_url: str = SEC_FUND_TICKERS_URL,
) -> dict:
    """Upsert lightweight ETF profiles from SEC's public fund ticker mapping."""

    require_unbound_etf_holdings_context("SEC ETF fund-ticker discovery")
    async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
        response = await client.get(
            source_url,
            headers={"User-Agent": settings.EDGAR_USER_AGENT},
            follow_redirects=True,
        )
    response.raise_for_status()

    rows = _parse_sec_fund_ticker_rows(response.json())
    created = 0
    updated = 0
    skipped = 0
    symbols: list[str] = []
    for row in rows:
        symbol = row["symbol"]
        if not (row.get("sec_cik") or row.get("sec_series_id") or row.get("sec_class_id")):
            skipped += 1
            continue
        instrument = await ensure_lightweight_etf_instrument(
            db,
            symbol=symbol,
            name=row["name"],
        )
        existing_profile = await get_etf_profile_for_instrument(db, instrument.id)
        existing_aliases = (existing_profile.provider_aliases or {}) if existing_profile else {}
        existing_legal_metadata = (
            (existing_profile.legal_metadata or {}) if existing_profile else {}
        )
        profile = await ensure_etf_profile(
            db,
            instrument,
            sec_cik=row.get("sec_cik"),
            sec_series_id=row.get("sec_series_id"),
            sec_class_id=row.get("sec_class_id"),
            provider_aliases={
                **existing_aliases,
                "sec_fund_tickers_source_url": source_url,
                "sec_fund_tickers_symbol": symbol,
                **{
                    key: value
                    for key, value in {
                        "sec_cik": row.get("sec_cik"),
                        "sec_series_id": row.get("sec_series_id"),
                        "sec_class_id": row.get("sec_class_id"),
                    }.items()
                    if value
                },
            },
            legal_metadata={
                **existing_legal_metadata,
                "sec_fund_tickers_source_url": source_url,
                "sec_fund_tickers_source_access": "sec_public_file",
                "sec_fund_tickers_last_row": row["raw_row"],
            },
        )
        profile.adapter_status = profile.adapter_status or "unresolved"
        profile.adapter_confidence = profile.adapter_confidence or Decimal("0.0000")
        await _register_optional_identifier(
            db,
            instrument,
            "internal",
            f"SEC-CIK:{row['sec_cik']}",
            "sec",
        )
        created += 1 if existing_profile is None else 0
        updated += 0 if existing_profile is None else 1
        symbols.append(instrument.symbol)

    await db.flush()
    return {
        "adapter_key": "sec_company_tickers_mf",
        "source_url": source_url,
        "discovered": len(rows),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "symbols": symbols,
    }


async def enrich_etf_profile_from_sec_fund_tickers(
    db: AsyncSession,
    *,
    profile: ETFProfile,
    source_url: str = SEC_FUND_TICKERS_URL,
) -> bool:
    """Hydrate SEC identifiers for a single ETF profile from the public fund ticker map."""

    if profile.instrument is None:
        raise ValueError("ETF profile is missing its linked instrument.")

    require_unbound_etf_holdings_context("SEC ETF fund-ticker enrichment")
    symbol = profile.instrument.symbol.strip().upper()
    async with httpx.AsyncClient(timeout=settings.ETF_HOLDINGS_FETCH_TIMEOUT_SECONDS) as client:
        response = await client.get(
            source_url,
            headers={"User-Agent": settings.EDGAR_USER_AGENT},
            follow_redirects=True,
        )
    response.raise_for_status()

    target_row = next(
        (row for row in _parse_sec_fund_ticker_rows(response.json()) if row["symbol"] == symbol),
        None,
    )
    if target_row is None:
        return False

    profile = await ensure_etf_profile(
        db,
        profile.instrument,
        sec_cik=target_row.get("sec_cik"),
        sec_series_id=target_row.get("sec_series_id"),
        sec_class_id=target_row.get("sec_class_id"),
        provider_aliases={
            **(_aliases(profile)),
            "sec_fund_tickers_source_url": source_url,
            "sec_fund_tickers_symbol": symbol,
            **{
                key: value
                for key, value in {
                    "sec_cik": target_row.get("sec_cik"),
                    "sec_series_id": target_row.get("sec_series_id"),
                    "sec_class_id": target_row.get("sec_class_id"),
                }.items()
                if value
            },
        },
        legal_metadata={
            **((profile.legal_metadata or {}) if profile else {}),
            "sec_fund_tickers_source_url": source_url,
            "sec_fund_tickers_source_access": "sec_public_file",
            "sec_fund_tickers_last_row": target_row["raw_row"],
        },
    )
    await _register_optional_identifier(
        db,
        profile.instrument,
        "internal",
        f"SEC-CIK:{target_row['sec_cik']}" if target_row.get("sec_cik") else None,
        "sec",
    )
    return True


async def _bootstrap_from_sec_filings(
    db: AsyncSession,
    *,
    profile: ETFProfile,
) -> ETFHoldingsBootstrapResult | None:
    """Fallback bootstrap using the latest parseable SEC holdings filings."""

    if profile.instrument is None:
        raise ValueError("ETF profile is missing its linked instrument.")

    from app.services.etf_holdings_edgar import (
        backfill_sec_legacy_holdings,
        backfill_sec_nport_holdings,
    )

    latest = await get_latest_snapshot(
        db,
        profile.instrument_id,
        include_holdings=True,
        include_controlled_fixture=False,
    )
    if holdings_snapshot_is_bootstrap_ready(latest):
        probe = await probe_etf_holdings_adapter_route(db, profile)
        return ETFHoldingsBootstrapResult(
            profile=profile,
            probe=probe,
            refresh_attempted=False,
            refresh_succeeded=True,
            message="Loaded the latest stored ETF holdings snapshot.",
        )

    if not profile.sec_cik:
        return None

    backfill_attempts: list[tuple[str, Any]] = [
        ("SEC N-PORT", backfill_sec_nport_holdings),
        ("SEC legacy holdings", backfill_sec_legacy_holdings),
    ]
    failures: list[str] = []
    for label, loader in backfill_attempts:
        try:
            summary = await loader(
                db,
                profile=profile,
                max_filings=3,
                requested_by_user_id=None,
            )
        except Exception as exc:  # noqa: BLE001 - bootstrap should surface fallback issues cleanly.
            failures.append(f"{label}: {exc}")
            continue

        latest = await get_latest_snapshot(
            db,
            profile.instrument_id,
            include_holdings=True,
            include_controlled_fixture=False,
        )
        if holdings_snapshot_is_bootstrap_ready(latest):
            probe = await probe_etf_holdings_adapter_route(db, profile)
            return ETFHoldingsBootstrapResult(
                profile=profile,
                probe=probe,
                refresh_attempted=True,
                refresh_succeeded=True,
                message=(
                    f"Fetched ETF holdings from the latest available {label} filing."
                    if summary.get("ingested", 0)
                    else f"Loaded the latest stored ETF holdings snapshot after {label} backfill."
                ),
            )
        failures.append(
            f"{label}: discovered={summary.get('discovered', 0)}, "
            f"ingested={summary.get('ingested', 0)}, skipped={summary.get('skipped', 0)}, "
            f"failed={summary.get('failed', 0)}"
        )

    if failures:
        probe = await probe_etf_holdings_adapter_route(db, profile)
        return ETFHoldingsBootstrapResult(
            profile=profile,
            probe=probe,
            refresh_attempted=True,
            refresh_succeeded=False,
            message=" ; ".join(failures),
        )
    return None


async def refresh_all_known_etf_holdings(db: AsyncSession) -> dict:
    """Refresh ETF holdings for profiles whose free-source route is configured."""

    profiles = (
        (await db.execute(select(ETFProfile).options(selectinload(ETFProfile.instrument))))
        .scalars()
        .all()
    )
    unresolved = 0
    skipped = 0
    refreshed = 0
    failed = 0
    for profile in profiles:
        # Profiles can predate a curated issuer route and retain an obsolete
        # adapter key (for example SMH was once inferred as ARK). Reconcile
        # canonical symbol-addressable route metadata before deciding whether
        # the profile is unresolved, so scheduled refreshes converge the
        # persisted security-master state instead of permanently preserving a
        # stale provider choice.
        _apply_known_route_metadata(profile)
        if not profile.adapter_key or profile.adapter_key == "unresolved":
            unresolved += 1
            await _record_skip(db, profile, "holdings_adapter_unresolved")
            continue
        try:
            refreshed_snapshot = await _refresh_adapter_route(db, profile)
        except ETFHoldingsRouteNotReadyError as exc:
            skipped += 1
            await _record_skip(db, profile, "needs_issuer_route", str(exc))
        except Exception as exc:  # noqa: BLE001 - persisted adapter health should capture any failure.
            failed += 1
            await _record_failure(db, profile, exc)
        else:
            refreshed += 1
            await _record_success(db, profile, snapshot=refreshed_snapshot)
    await db.flush()
    return {
        "profiles": len(profiles),
        "refreshed": refreshed,
        "unresolved": unresolved,
        "skipped": skipped,
        "failed": failed,
    }


def _canary_failure_class(failure: Exception | str) -> str:
    text = str(failure).lower()
    if "future composition" in text or "future as-of" in text or "future published-at" in text:
        return "future_dated_source"
    if "issuer access challenge" in text or "cloudflare ray id" in text:
        return "issuer_access_blocked"
    if isinstance(failure, ETFHoldingsSchemaDriftError) or "schema fingerprint drift" in text:
        return "schema_drift"
    if "identity" in text or "mismatch" in text:
        return "identity_mismatch"
    if "parseable rows" in text or "complete rows" in text or "empty" in text:
        return "empty_or_partial_source"
    if isinstance(failure, httpx.HTTPStatusError):
        status_code = failure.response.status_code
        # A 401 is materially different from an arbitrary upstream HTTP
        # failure: it proves that the candidate route requires credentials or
        # an entitlement that this free/public path does not currently have.
        # Keep that distinction in the persisted capability evidence so an
        # operator can review access/terms without mistaking it for transport
        # or parser drift.
        if status_code == 401:
            return "authentication_required"
        if status_code == 403:
            return "access_denied"
        if status_code == 429:
            return "quota_rate_limited"
        return f"http_{status_code}"
    if isinstance(failure, httpx.HTTPError | TimeoutError | ConnectionError):
        return "transport_error"
    if "parse" in text or "schema" in text or "column" in text:
        return "parser_or_schema_error"
    return "provider_error"


async def _ensure_schema_fingerprint_is_stable(
    db: AsyncSession,
    profile: ETFProfile,
    *,
    parser_version: str,
    raw_payload_text: str | None = None,
    raw_payload_json: dict | None = None,
    schema_fingerprint_override: str | None = None,
    legacy_qualification_fingerprint: str | None = None,
) -> None:
    """Reject an unexplained artifact-shape change before snapshot persistence.

    A stored fingerprint is evidence about the last successful route, not a
    reason to accept a new shape silently.  A deliberate parser-version change
    is the explicit recovery mechanism: it lets an adapter release document
    the schema migration while an unchanged parser remains fail-closed.
    Lightweight unit fakes that do not expose a database execute method skip
    this persistence-boundary check; real refreshes always use AsyncSession.
    """

    execute = getattr(db, "execute", None)
    if not callable(execute):
        return
    observed = schema_fingerprint_override or _schema_fingerprint(
        raw_payload_text=raw_payload_text,
        raw_payload_json=raw_payload_json,
    )
    if not observed:
        return
    result = await execute(
        select(ETFHoldingsAdapterState).where(
            ETFHoldingsAdapterState.etf_profile_id == profile.id,
            ETFHoldingsAdapterState.adapter_key == (profile.adapter_key or "unresolved"),
        )
    )
    state = result.scalar_one_or_none()
    if state is None:
        return
    metadata = _state_metadata(state.extra_data)
    previous = metadata.get("schema_fingerprint")
    if not previous or str(previous) == observed:
        return
    previous_parser = str(getattr(state, "parser_version", None) or "")
    if previous_parser and previous_parser != parser_version:
        return
    if (
        legacy_qualification_fingerprint is not None
        and previous_parser == parser_version == "vaneck-xlsx-v1"
        and str(previous) == legacy_qualification_fingerprint
    ):
        return
    raise ETFHoldingsSchemaDriftError(
        previous=str(previous),
        observed=observed,
        parser_version=parser_version,
    )


async def run_etf_holdings_capability_canaries(
    db: AsyncSession,
    *,
    symbols: list[str],
    max_symbols: int,
    timeout_seconds: float = 60.0,
    failure_threshold: int = 3,
    cooldown_seconds: int = 3600,
) -> dict[str, Any]:
    """Run a bounded, opt-in route sweep and persist operational evidence.

    Canaries use the existing ETF adapter contract and state row. They do not
    create generic provider health or entitlement records; the shared provider
    platform bridge will consume this observation once it reaches staging.
    """

    requested = []
    for symbol in symbols:
        normalized = str(symbol).strip().upper()
        if normalized and normalized not in requested:
            requested.append(normalized)
    requested = requested[: max(0, max_symbols)]
    profiles = (
        (
            await db.execute(
                select(ETFProfile)
                .options(selectinload(ETFProfile.instrument))
                .join(Instrument, Instrument.id == ETFProfile.instrument_id)
                .where(Instrument.symbol.in_(requested))
            )
        )
        .scalars()
        .all()
    )
    by_symbol = {
        str(profile.instrument.symbol).strip().upper(): profile
        for profile in profiles
        if profile.instrument is not None
    }
    reports: list[dict[str, Any]] = []
    summary = {
        "requested": len(requested),
        "checked": 0,
        "recovered": 0,
        "skipped": 0,
        "failed": 0,
        "missing_profiles": 0,
    }
    now = datetime.now(UTC)

    for symbol in requested:
        profile = by_symbol.get(symbol)
        if profile is None:
            summary["missing_profiles"] += 1
            reports.append({"symbol": symbol, "status": "missing_profile"})
            continue
        adapter_key = profile.adapter_key or "unresolved"
        state = (
            await db.execute(
                select(ETFHoldingsAdapterState).where(
                    ETFHoldingsAdapterState.etf_profile_id == profile.id,
                    ETFHoldingsAdapterState.adapter_key == adapter_key,
                )
            )
        ).scalar_one_or_none()
        metadata = _state_metadata(state.extra_data if state is not None else None)
        open_until_text = metadata.get("circuit_open_until")
        open_until = None
        if open_until_text:
            try:
                open_until = datetime.fromisoformat(str(open_until_text))
                if open_until.tzinfo is None:
                    open_until = open_until.replace(tzinfo=UTC)
            except ValueError:
                open_until = None
        if open_until is not None and open_until > now:
            summary["skipped"] += 1
            if state is not None:
                state.status = "circuit_open"
                state.last_checked_at = now
                circuit_capability = evaluate_capability(profile, None, state, now=now)
                state.extra_data = _append_canary_observation(
                    {
                        **metadata,
                        "last_canary_at": now.isoformat(),
                        "last_canary_status": "circuit_open",
                    },
                    {
                        "observed_at": now.isoformat(),
                        "status": "circuit_open",
                        "availability": circuit_capability.availability,
                        "usable_for_current_analysis": False,
                        "source_tier": circuit_capability.source_tier,
                        "source_provider": metadata.get("source_provider"),
                        "source_url": getattr(state, "source_url", None),
                        "source_identifier": getattr(state, "source_identifier", None),
                        "transport_kind": circuit_capability.transport_kind,
                        "identity_verified": circuit_capability.identity_verified,
                        "symbol_audit_outcome": circuit_capability.symbol_audit.outcome,
                        "failure_streak": _failure_streak(metadata),
                        "failure_class": metadata.get("last_canary_failure_class"),
                        "failure_reason": state.failure_reason,
                        "circuit_state": "open",
                        "recovered": False,
                    },
                )
            reports.append(
                {
                    "symbol": symbol,
                    "status": "circuit_open",
                    "circuit_open_until": open_until.isoformat(),
                }
            )
            continue

        started = time.perf_counter()
        previous_failures = _failure_streak(metadata)
        try:
            snapshot = await asyncio.wait_for(
                _refresh_adapter_route(db, profile),
                timeout=max(float(timeout_seconds), 0.1),
            )
        except ETFHoldingsRouteNotReadyError as exc:
            summary["skipped"] += 1
            await _record_skip(db, profile, "needs_issuer_route", str(exc))
            status = "needs_issuer_route"
            failure_class = "route_not_ready"
            snapshot = None
            failure_text = str(exc)
        except Exception as exc:  # noqa: BLE001 - canary records provider-specific failure.
            summary["failed"] += 1
            await _record_failure(db, profile, exc)
            status = "failure"
            failure_class = _canary_failure_class(exc)
            snapshot = None
            failure_text = str(exc)
        else:
            summary["checked"] += 1
            await _record_success(db, profile, snapshot=snapshot)
            status = "success"
            failure_class = None
            failure_text = None

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        state = (
            await db.execute(
                select(ETFHoldingsAdapterState).where(
                    ETFHoldingsAdapterState.etf_profile_id == profile.id,
                    ETFHoldingsAdapterState.adapter_key == adapter_key,
                )
            )
        ).scalar_one_or_none()
        if state is None:
            reports.append({"symbol": symbol, "status": status})
            continue
        current_metadata = _state_metadata(state.extra_data)
        failures = _failure_streak(current_metadata)
        recovered = status == "success" and previous_failures > 0
        if recovered:
            summary["recovered"] += 1
        circuit_state = "closed"
        circuit_open_until = None
        if status != "success" and failures >= max(1, failure_threshold):
            circuit_state = "open"
            circuit_open_until = datetime.now(UTC) + timedelta(seconds=max(1, cooldown_seconds))
            state.status = "circuit_open"
        observation_now = datetime.now(UTC)
        current_metadata = dict(current_metadata)
        if status == "success":
            # This marker is written only after the bounded route fetch and
            # snapshot ingestion succeeded. It allows a newly verified route
            # to supersede an older static issuer-access challenge.
            current_metadata["symbol_audit_revalidated_at"] = observation_now.isoformat()
        else:
            current_metadata.pop("symbol_audit_revalidated_at", None)
        state.extra_data = current_metadata
        capability_snapshot = snapshot
        if capability_snapshot is None:
            # A failed refresh does not erase the stored prior composition.
            # Resolve the same visible latest snapshot used by API consumers
            # so the operational observation says degraded/last-known rather
            # than unavailable when durable holdings still exist.
            capability_snapshot = await get_latest_snapshot(
                db,
                profile.instrument_id,
                include_holdings=False,
                include_controlled_fixture=False,
            )
        capability = evaluate_capability(
            profile,
            capability_snapshot,
            state,
            now=observation_now,
        )
        observation = {
            "observed_at": observation_now.isoformat(),
            "status": status,
            "availability": capability.availability,
            "usable_for_current_analysis": capability.usable_for_current_analysis,
            "source_tier": capability.source_tier,
            "source_provider": capability.source_provider,
            "source_url": (
                snapshot.source_url if snapshot is not None else getattr(state, "source_url", None)
            ),
            "source_identifier": (
                snapshot.source_identifier
                if snapshot is not None
                else getattr(state, "source_identifier", None)
            ),
            "transport_kind": capability.transport_kind,
            "identity_verified": capability.identity_verified,
            "symbol_audit_outcome": capability.symbol_audit.outcome,
            "composition_date": (
                capability.composition_date.isoformat() if capability.composition_date else None
            ),
            "freshness_deadline": (
                capability.freshness_deadline.isoformat() if capability.freshness_deadline else None
            ),
            "row_count": capability.row_count,
            "resolved_count": capability.resolved_count,
            "unresolved_count": capability.unresolved_count,
            "completeness_status": capability.completeness_status,
            "schema_fingerprint": capability.schema_fingerprint,
            "parser_version": (
                snapshot.parser_version
                if snapshot is not None
                else getattr(state, "parser_version", None)
            ),
            "latency_ms": elapsed_ms,
            "failure_class": failure_class,
            "failure_reason": failure_text or capability.failure_reason,
            "failure_streak": failures,
            "circuit_state": circuit_state,
            "recovered": recovered,
        }
        state.extra_data = {
            **current_metadata,
            "last_canary_at": datetime.now(UTC).isoformat(),
            "last_canary_status": status,
            "last_canary_latency_ms": elapsed_ms,
            "last_canary_failure_class": failure_class,
            "last_failure_class": failure_class,
            "last_canary_failure_reason": failure_text,
            "last_canary_recovered": recovered,
            "circuit_state": circuit_state,
            "circuit_open_until": circuit_open_until.isoformat() if circuit_open_until else None,
        }
        state.extra_data = _append_canary_observation(state.extra_data, observation)
        reports.append(
            {
                "symbol": symbol,
                "status": status,
                "availability": capability.availability,
                "latency_ms": elapsed_ms,
                "failure_class": failure_class,
                "recovered": recovered,
                "circuit_state": circuit_state,
            }
        )

    await db.flush()
    return {**summary, "reports": reports}


async def reconcile_all_etf_holdings_classifications(
    db: AsyncSession,
    *,
    max_profiles: int = 50,
    max_enrichments_per_profile: int = 32,
) -> dict:
    """Resume missing free-source constituent classifications in bounded batches."""

    profiles = (
        (
            await db.execute(
                select(ETFProfile)
                .options(selectinload(ETFProfile.instrument))
                .order_by(ETFProfile.id)
            )
        )
        .scalars()
        .all()
    )
    processed = enriched = remaining = failed = 0
    candidate_profiles = 0
    for profile in profiles:
        if profile.instrument is None:
            continue
        snapshot = (
            await db.execute(
                select(ETFHoldingsSnapshot)
                .options(
                    selectinload(ETFHoldingsSnapshot.rows)
                    .selectinload(ETFHolding.constituent_instrument)
                    .selectinload(Instrument.equity_detail)
                )
                .where(
                    ETFHoldingsSnapshot.etf_profile_id == profile.id,
                    ETFHoldingsSnapshot.provenance != "controlled_fixture",
                    ETFHoldingsSnapshot.source_provider != "e2e_reference",
                )
                .order_by(
                    ETFHoldingsSnapshot.composition_date.desc(),
                    ETFHoldingsSnapshot.known_at.desc().nullslast(),
                    ETFHoldingsSnapshot.id.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if snapshot is None:
            continue
        missing_before = sum(
            1
            for row in snapshot.rows
            if row.constituent_instrument is not None
            and (
                row.constituent_instrument.equity_detail is None
                or not (
                    row.constituent_instrument.equity_detail.industry
                    or row.constituent_instrument.equity_detail.sector
                )
            )
        )
        if missing_before == 0:
            continue
        if candidate_profiles >= max(0, max_profiles):
            break
        candidate_profiles += 1
        before = sum(
            1
            for row in snapshot.rows
            if row.constituent_instrument is not None
            and row.constituent_instrument.equity_detail is not None
            and (
                row.constituent_instrument.equity_detail.industry
                or row.constituent_instrument.equity_detail.sector
            )
        )
        try:
            await reconcile_snapshot_constituents(
                db,
                snapshot,
                max_classification_enrichment=max_enrichments_per_profile,
            )
        except Exception as exc:  # noqa: BLE001 - isolate one profile's maintenance failure.
            failed += 1
            await _record_failure(db, profile, exc)
            await db.flush()
            continue
        after = sum(
            1
            for row in snapshot.rows
            if row.constituent_instrument is not None
            and row.constituent_instrument.equity_detail is not None
            and (
                row.constituent_instrument.equity_detail.industry
                or row.constituent_instrument.equity_detail.sector
            )
        )
        processed += 1
        enriched += max(0, after - before)
        remaining += sum(
            1
            for row in snapshot.rows
            if row.constituent_instrument is not None
            and (
                row.constituent_instrument.equity_detail is None
                or not (
                    row.constituent_instrument.equity_detail.industry
                    or row.constituent_instrument.equity_detail.sector
                )
            )
        )
    await db.flush()
    return {
        "profiles": candidate_profiles,
        "processed": processed,
        "enriched": enriched,
        "remaining": remaining,
        "failed": failed,
        "max_enrichments_per_profile": max_enrichments_per_profile,
    }


async def probe_etf_holdings_adapter_route(
    db: AsyncSession,
    profile: ETFProfile,
) -> HoldingsAdapterProbe:
    """Inspect and persist whether an ETF profile has a refreshable holdings route."""

    if profile.instrument is None:
        raise ValueError("ETF profile is missing its linked instrument.")

    # Profiles created by the canonical identity bootstrap predate (or may not
    # yet have materialised) the symbol-addressable issuer route metadata. Apply
    # that reviewed metadata before probing so SPDR/Invesco/iShares core ETFs do
    # not remain falsely unresolved merely because the profile row was created
    # with identity-only fields.
    _apply_known_route_metadata(profile)
    adapter_key = profile.adapter_key or "unresolved"
    adapter = get_holdings_adapter(adapter_key)
    if adapter is None:
        probe = HoldingsAdapterProbe(
            adapter_key=adapter_key,
            confidence=profile.adapter_confidence or 0,
            status="holdings_adapter_unresolved"
            if adapter_key == "unresolved"
            else "adapter_not_registered",
            reason=(
                "No configured free issuer adapter matched this ETF identity."
                if adapter_key == "unresolved"
                else f"No ETF holdings adapter is registered for {adapter_key}."
            ),
        )
    else:
        probe = adapter.probe(
            symbol=profile.instrument.symbol,
            name=profile.instrument.name,
            identifiers=_string_aliases(profile),
        )

    profile.adapter_status = probe.status
    profile.adapter_confidence = probe.confidence
    await _record_probe(db, profile, probe)
    return probe


async def _resolve_canonical_fund_instrument(
    db: AsyncSession,
    symbol: str,
) -> Instrument | None:
    """Resolve one existing, canonical ETF/fund symbol without creating identity."""

    if not symbol:
        return None
    statement = (
        select(Instrument)
        .join(Instrument.instrument_type)
        .options(
            selectinload(Instrument.instrument_type).selectinload(InstrumentType.asset_class),
            selectinload(Instrument.issuer),
        )
        .where(func.upper(Instrument.symbol) == symbol)
        .limit(2)
    )
    matches = (await db.execute(statement)).scalars().all()
    if len(matches) != 1:
        return None
    instrument = matches[0]
    instrument_type = instrument.instrument_type
    type_name = str(getattr(instrument_type, "name", "")).strip().casefold()
    asset_class = getattr(instrument_type, "asset_class", None)
    asset_class_name = str(getattr(asset_class, "name", "")).strip().casefold()
    supported_fund_type = type_name in {
        "etf",
        "index etf",
        "mutual fund",
        "closed-end fund",
    } or (type_name == "exchange traded vehicle" and asset_class_name == "exchange traded product")
    if (
        not instrument.is_active
        or instrument.is_synthetic
        or instrument.identity_status != "resolved"
        or not supported_fund_type
    ):
        return None
    return instrument


def _acquisition_validation(
    request_id: str | None,
    validation: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not request_id:
        return validation
    return {**(validation or {}), "application_request_id": request_id}


async def acquire_etf_holdings_profile(
    db: AsyncSession,
    *,
    symbol: str,
    request_id: str,
    refresh: bool,
    instrument_id: int | None = None,
) -> ETFHoldingsAcquireResult | None:
    """Acquire only the selected ETF's configured issuer route through Provider.

    Unlike bootstrap, this function never creates instrument/catalog rows,
    performs SEC ticker enrichment, or falls back to EDGAR. A missing ETF
    profile may be created only for an already-resolved canonical fund and only
    on an explicit refresh. Cache-only requests are read-only. The shared ETF
    bridge remains the admission seam for policy, quota, cost, and settlement.
    """

    normalized_symbol = str(symbol or "").strip().upper()
    instrument = await _resolve_canonical_fund_instrument(db, normalized_symbol)
    if instrument is None or (instrument_id is not None and instrument.id != instrument_id):
        return None

    route_metadata = known_etf_route_metadata(
        normalized_symbol,
        canonical_issuer=getattr(instrument, "issuer", None),
        canonical_fund_name=str(getattr(instrument, "name", "") or ""),
        allow_catalog_route=True,
    )
    route_aliases = route_metadata.get("provider_aliases") if route_metadata else None
    reviewed_adapter_key = (
        str(route_aliases.get("holdings_adapter") or "").strip().lower()
        if isinstance(route_aliases, dict)
        else ""
    )
    profile = await get_etf_profile_for_instrument(db, instrument.id)
    profile_created = False
    curated_route_applied = False
    if profile is None:
        if not refresh:
            return None
        if not reviewed_adapter_key:
            # A deliberate user selection is still useful when this fund has
            # no audited issuer route: return a typed unavailable result for
            # the exact canonical instrument rather than a 404 or another
            # fund's cached snapshot. Do not create a speculative profile.
            return ETFHoldingsAcquireResult(
                profile=None,
                outcome="unavailable",
                refresh=True,
                refresh_attempted=False,
                refresh_succeeded=False,
                snapshot=None,
                snapshot_id=None,
                source_provider=None,
                source_operation=None,
                provider_request_log_ids=[],
                message=(
                    "No exact audited issuer route or fund-specific product identifier is "
                    "available for this selection; no profile or source request was created."
                ),
                instrument_id=instrument.id,
                symbol=instrument.symbol,
                reason_code="issuer_route_unavailable",
            )
        profile = await ensure_etf_profile(db, instrument)
        # The new row was created by foreign key only. Keep the already-loaded
        # canonical instrument attached so subsequent route metadata/probing
        # never triggers async lazy loading on this explicit acquire request.
        profile.instrument = instrument
        curated_route_applied = _apply_known_route_metadata(
            profile,
            route_metadata=route_metadata,
        )
        profile_created = True
        # The shared Provider bridge validates the committed profile identity
        # before issuing a request. Persist only this explicitly requested,
        # already-canonical fund profile and curated local route state, then
        # reload it with its instrument relationship before entering that bridge.
        await db.flush()
        await db.commit()
        profile = await get_etf_profile_for_instrument(db, instrument.id)
        if profile is None:
            return None

    snapshot = await get_latest_snapshot(
        db,
        profile.instrument_id,
        include_holdings=True,
        include_controlled_fixture=False,
    )
    if not refresh:
        return ETFHoldingsAcquireResult(
            profile=profile,
            outcome="cached" if snapshot is not None else "no_data",
            refresh=False,
            refresh_attempted=False,
            refresh_succeeded=False,
            snapshot=snapshot,
            snapshot_id=snapshot.id if snapshot else None,
            source_provider=(snapshot.source_provider if snapshot else None),
            source_operation=None,
            provider_request_log_ids=[],
            message=(
                "Returned the latest stored holdings snapshot; no source request was made."
                if snapshot is not None
                else "No stored holdings snapshot exists; no source request was made. Set refresh=true to request one."
            ),
        )

    configured_adapter_key = str(profile.adapter_key or "").strip().lower()
    profile_adapter_key = str(_aliases(profile).get("holdings_adapter") or "").strip().lower()
    if not profile_created and reviewed_adapter_key:
        curated_route_applied = _apply_known_route_metadata(
            profile,
            route_metadata=route_metadata,
        )
        configured_adapter_key = str(profile.adapter_key or "").strip().lower()
        profile_adapter_key = str(_aliases(profile).get("holdings_adapter") or "").strip().lower()
    if (
        not reviewed_adapter_key
        or configured_adapter_key != reviewed_adapter_key
        or (profile_adapter_key and profile_adapter_key != configured_adapter_key)
    ):
        return ETFHoldingsAcquireResult(
            profile=profile,
            outcome="held",
            refresh=True,
            refresh_attempted=False,
            refresh_succeeded=False,
            snapshot=snapshot,
            snapshot_id=snapshot.id if snapshot else None,
            source_provider=None,
            source_operation=None,
            provider_request_log_ids=[],
            message=(
                "No exact current or curated issuer route matches this canonical ETF; "
                "no source request was made."
            ),
            reason_code="issuer_route_mismatch",
        )
    if curated_route_applied and not profile_created:
        # Explicit refresh may repair an older profile with current curated
        # issuer-route metadata. Make that specific profile state durable before
        # the shared bridge validates the committed route.
        await db.flush()
        await db.commit()
        profile = await get_etf_profile_for_instrument(db, instrument.id)
        if profile is None:
            return None
    adapter = get_holdings_adapter(profile.adapter_key)
    if adapter is None or profile.instrument is None:
        return ETFHoldingsAcquireResult(
            profile=profile,
            outcome="held",
            refresh=True,
            refresh_attempted=False,
            refresh_succeeded=False,
            snapshot=snapshot,
            snapshot_id=snapshot.id if snapshot else None,
            source_provider=None,
            source_operation=None,
            provider_request_log_ids=[],
            message="No configured issuer holdings adapter is available for this ETF profile.",
            reason_code="issuer_adapter_unavailable",
        )

    source_provider = str(getattr(adapter, "source_provider", "")).strip().lower() or None
    operation = "fetch_etf_holdings_latest"
    reviewed_source_provider = (
        str(route_aliases.get("holdings_source_provider") or source_provider or "").strip().lower()
        if isinstance(route_aliases, dict)
        else source_provider or ""
    )
    if (
        not source_provider
        or not reviewed_source_provider
        or source_provider != reviewed_source_provider
        or _aliases(profile).get("holdings_source_provider") != reviewed_source_provider
    ):
        return ETFHoldingsAcquireResult(
            profile=profile,
            outcome="held",
            refresh=True,
            refresh_attempted=False,
            refresh_succeeded=False,
            snapshot=snapshot,
            snapshot_id=snapshot.id if snapshot else None,
            source_provider=source_provider,
            source_operation=operation,
            provider_request_log_ids=[],
            message=(
                "The selected native adapter does not match the audited publisher identity; "
                "no request was made."
            ),
            reason_code="issuer_source_identity_mismatch",
        )

    if source_provider == "vaneck" and not _first_alias(_string_aliases(profile), "product_slug"):
        return ETFHoldingsAcquireResult(
            profile=profile,
            outcome="held",
            refresh=True,
            refresh_attempted=False,
            refresh_succeeded=False,
            snapshot=snapshot,
            snapshot_id=snapshot.id if snapshot else None,
            source_provider=source_provider,
            source_operation=operation,
            provider_request_log_ids=[],
            message="VanEck acquisition requires its committed fund-specific product slug.",
            reason_code="issuer_route_incomplete",
        )

    probe = adapter.probe(
        symbol=profile.instrument.symbol,
        name=profile.instrument.name,
        identifiers=_string_aliases(profile),
    )
    if probe.status != "ready":
        return ETFHoldingsAcquireResult(
            profile=profile,
            outcome="held",
            refresh=True,
            refresh_attempted=False,
            refresh_succeeded=False,
            snapshot=snapshot,
            snapshot_id=snapshot.id if snapshot else None,
            source_provider=source_provider,
            source_operation=operation,
            provider_request_log_ids=[],
            message=bounded_redact_provider_message(
                probe.reason or "The selected issuer route is not ready.", max_length=1000
            ),
            reason_code="issuer_adapter_not_ready",
        )

    if not source_provider:
        return ETFHoldingsAcquireResult(
            profile=profile,
            outcome="held",
            refresh=True,
            refresh_attempted=False,
            refresh_succeeded=False,
            snapshot=snapshot,
            snapshot_id=snapshot.id if snapshot else None,
            source_provider=None,
            source_operation=operation,
            provider_request_log_ids=[],
            message="The selected issuer route has no trusted Provider identity; no request was made.",
            reason_code="issuer_provider_identity_missing",
        )

    acquisition_binder = _explicit_etf_acquisition_binder()
    if acquisition_binder is None:
        return ETFHoldingsAcquireResult(
            profile=profile,
            outcome="held",
            refresh=True,
            refresh_attempted=False,
            refresh_succeeded=False,
            snapshot=snapshot,
            snapshot_id=snapshot.id if snapshot else None,
            source_provider=source_provider,
            source_operation=operation,
            provider_request_log_ids=[],
            message=(
                "Explicit issuer acquisition is unavailable until the reviewed "
                "Provider request scope is staged."
            ),
            reason_code="provider_admission_unavailable",
        )

    request_log_ids: list[int] = []
    try:
        with acquisition_binder(
            request_id=request_id,
            instrument_id=profile.instrument.id,
            symbol=profile.instrument.symbol,
            issuer_provider_name=source_provider,
        ):
            acquired = await _refresh_adapter_route(
                db,
                profile,
                probe=probe,
                acquisition_request_id=request_id,
                atomic_ingest_savepoint=True,
                request_log_ids_out=request_log_ids,
            )
        await _record_success(db, profile, snapshot=acquired)
        await db.flush()
        return ETFHoldingsAcquireResult(
            profile=profile,
            outcome="acquired",
            refresh=True,
            refresh_attempted=True,
            refresh_succeeded=True,
            snapshot=None,
            snapshot_id=acquired.id,
            source_provider=source_provider,
            source_operation=operation,
            provider_request_log_ids=request_log_ids,
            message="Fetched and stored the selected ETF issuer snapshot through shared Provider admission.",
        )
    except (ETFHoldingsRouteHeldError, ETFHoldingsRouteNotReadyError) as exc:
        return ETFHoldingsAcquireResult(
            profile=profile,
            outcome="held",
            refresh=True,
            refresh_attempted=True,
            refresh_succeeded=False,
            snapshot=snapshot,
            snapshot_id=snapshot.id if snapshot else None,
            source_provider=source_provider,
            source_operation=operation,
            provider_request_log_ids=request_log_ids,
            message=bounded_redact_provider_message(exc, max_length=1000)
            or "The shared Provider route held this request.",
            reason_code="issuer_request_held",
        )
    except (ProviderQuotaAdmissionError, ProviderRateLimitError) as exc:
        return ETFHoldingsAcquireResult(
            profile=profile,
            outcome="held",
            refresh=True,
            refresh_attempted=True,
            refresh_succeeded=False,
            snapshot=snapshot,
            snapshot_id=snapshot.id if snapshot else None,
            source_provider=source_provider,
            source_operation=operation,
            provider_request_log_ids=request_log_ids,
            message=bounded_redact_provider_message(exc, max_length=1000)
            or "The issuer request is held by the provider quota gate.",
            reason_code=(
                "provider_quota_admission_held"
                if isinstance(exc, ProviderQuotaAdmissionError)
                else "provider_rate_limited"
            ),
            retry_at=(
                exc.retry_at
                if isinstance(getattr(exc, "retry_at", None), datetime)
                and exc.retry_at.tzinfo is not None
                and exc.retry_at.utcoffset() is not None
                else None
            ),
        )
    except Exception as exc:
        await _record_failure(db, profile, exc)
        await db.flush()
        return ETFHoldingsAcquireResult(
            profile=profile,
            outcome="failed",
            refresh=True,
            refresh_attempted=True,
            refresh_succeeded=False,
            snapshot=snapshot,
            snapshot_id=snapshot.id if snapshot else None,
            source_provider=source_provider,
            source_operation=operation,
            provider_request_log_ids=request_log_ids,
            message=bounded_redact_provider_message(exc, max_length=1000)
            or "The selected issuer request failed; prior stored evidence was preserved.",
            reason_code=(
                "future_dated_source"
                if _canary_failure_class(exc) == "future_dated_source"
                else None
            ),
        )


async def bootstrap_etf_holdings_profile(
    db: AsyncSession,
    *,
    symbol: str,
    name: str | None = None,
) -> ETFHoldingsBootstrapResult:
    instrument = await ensure_lightweight_etf_instrument(
        db,
        symbol=symbol,
        name=name or symbol,
    )
    preferred_name = (name or "").strip()
    if preferred_name and (
        not instrument.name or instrument.name.strip().upper() == instrument.symbol.strip().upper()
    ):
        instrument.name = preferred_name

    profile = await ensure_etf_profile(db, instrument)
    _apply_known_route_metadata(profile)

    if not profile.sec_cik:
        try:
            await enrich_etf_profile_from_sec_fund_tickers(db, profile=profile)
        except Exception:
            # SEC enrichment is opportunistic during bootstrap and should not block
            # issuer-route bootstrap attempts when the SEC endpoint is unavailable.
            pass

    latest_snapshot = await get_latest_snapshot(
        db,
        instrument.id,
        include_holdings=True,
        include_controlled_fixture=False,
    )
    if holdings_snapshot_is_bootstrap_ready(latest_snapshot):
        # The public snapshot schema is intentionally read-only. Re-load the
        # ORM record here so existing issuer snapshots can receive missing SEC
        # classifications through the same bounded reconciliation path used by
        # newly ingested snapshots.
        execute = getattr(db, "execute", None)
        if callable(execute):
            statement = (
                select(ETFHoldingsSnapshot)
                .options(
                    selectinload(ETFHoldingsSnapshot.rows)
                    .selectinload(ETFHolding.constituent_instrument)
                    .selectinload(Instrument.equity_detail)
                )
                .where(ETFHoldingsSnapshot.id == latest_snapshot.id)
            )
            stored_snapshot = (await execute(statement)).scalar_one_or_none()
            if stored_snapshot is not None:
                await reconcile_snapshot_constituents(db, stored_snapshot)
        probe = await probe_etf_holdings_adapter_route(db, profile)
        if probe.status == "ready":
            profile.adapter_status = "success"
        await db.flush()
        return ETFHoldingsBootstrapResult(
            profile=profile,
            probe=probe,
            refresh_attempted=False,
            refresh_succeeded=True,
            message="Loaded the latest stored ETF holdings snapshot.",
        )

    probe = await probe_etf_holdings_adapter_route(db, profile)
    if probe.status != "ready":
        sec_fallback = await _bootstrap_from_sec_filings(db, profile=profile)
        if sec_fallback is not None and sec_fallback.refresh_succeeded:
            await db.flush()
            return sec_fallback
        await db.flush()
        return ETFHoldingsBootstrapResult(
            profile=profile,
            probe=probe,
            refresh_attempted=False,
            refresh_succeeded=False,
            message=(
                sec_fallback.message
                if sec_fallback is not None and sec_fallback.message
                else probe.reason or "No free holdings route is configured for this ETF yet."
            ),
        )

    try:
        async with _bootstrap_savepoint(db):
            snapshot = await _refresh_adapter_route(db, profile)
        await _record_success(db, profile, snapshot=snapshot)
        await db.flush()
        return ETFHoldingsBootstrapResult(
            profile=profile,
            probe=probe,
            refresh_attempted=True,
            refresh_succeeded=True,
            message="Fetched the latest ETF holdings snapshot.",
        )
    except Exception as exc:
        sec_fallback = await _bootstrap_from_sec_filings(db, profile=profile)
        if sec_fallback is not None and sec_fallback.refresh_succeeded:
            await db.flush()
            return sec_fallback
        await db.flush()
        return ETFHoldingsBootstrapResult(
            profile=profile,
            probe=probe,
            refresh_attempted=True,
            refresh_succeeded=False,
            message=(
                sec_fallback.message
                if sec_fallback is not None and sec_fallback.message
                else str(exc) or "ETF holdings refresh failed."
            ),
        )


async def refresh_etf_holdings_for_date(
    db: AsyncSession,
    profile: ETFProfile,
    *,
    requested_date: date,
):
    """Fetch and persist a dated issuer holdings snapshot from an explicit template route."""

    if profile.instrument is None:
        raise ValueError("ETF profile is missing its linked instrument.")
    adapter = get_holdings_adapter(profile.adapter_key)
    if adapter is None:
        raise ETFHoldingsRouteNotReadyError(
            f"No ETF holdings adapter is registered for {profile.adapter_key}."
        )

    aliases = _aliases(profile)
    identifiers = _string_aliases(profile)
    symbol = profile.instrument.symbol
    issuer_product_id = _issuer_product_identifier(identifiers)
    fetch_result = None
    try:
        with bind_etf_holdings_request_context(
            db=db,
            adapter=adapter,
            profile_id=profile.id,
            instrument_id=profile.instrument.id,
            provider_symbol=symbol,
            operation="fetch_etf_holdings_for_date",
        ) as request_binding:
            try:
                fetch_result = await adapter.fetch_for_date(
                    symbol=symbol,
                    requested_date=requested_date,
                    issuer_product_id=issuer_product_id,
                    identifiers=identifiers,
                )
            except BaseException as exc:
                await _retain_rejected_fetch_artifact(
                    db,
                    profile,
                    adapter,
                    request_binding,
                    failure=exc,
                    validation={"requested_date": requested_date.isoformat()},
                    requested_date=requested_date,
                )
                raise
        if not fetch_result.rows:
            failure = ValueError("Issuer dated holdings route returned no parseable rows.")
            await _retain_rejected_fetch_artifact(
                db,
                profile,
                adapter,
                request_binding,
                fetch_result=fetch_result,
                failure=failure,
                validation={"status": "no_parseable_rows"},
                requested_date=requested_date,
            )
            raise failure
        artifact_identity_validation = _validate_artifact_identity(profile, fetch_result.raw_text)
        try:
            _ensure_artifact_identity_is_safe(artifact_identity_validation)
        except ValueError as exc:
            await _retain_rejected_fetch_artifact(
                db,
                profile,
                adapter,
                request_binding,
                fetch_result=fetch_result,
                failure=exc,
                validation=artifact_identity_validation,
                requested_date=requested_date,
            )
            raise

        result_metadata = {
            **(fetch_result.legal_metadata or {}),
            "provider_request_log_ids": request_binding.request_log_ids,
            "provider_request_attempts": _provider_request_attempts(request_binding),
        }
        result_metadata = {
            **result_metadata,
            "expected_cadence": result_metadata.get("expected_cadence")
            or infer_expected_cadence(
                source_access=getattr(getattr(adapter, "config", None), "source_access", None),
                metadata=result_metadata,
            ),
        }
        source_format = str(result_metadata.get("source_format") or "csv")
        source_provider = (
            _first_alias(aliases, "holdings_source_provider", "source_provider")
            or result_metadata.get("source_provider")
            or adapter.source_provider
        )
        composition_date = _date_from_value(result_metadata.get("composition_date"))
        if composition_date is None:
            composition_date = requested_date
        published_at = _datetime_from_value(result_metadata.get("published_at"))
        known_at = (
            _datetime_from_value(result_metadata.get("known_at"))
            or published_at
            or datetime.now(UTC)
        )
        if composition_date > requested_date:
            failure = ValueError(
                "Issuer dated holdings route returned a composition date after the requested "
                f"date ({composition_date.isoformat()} > {requested_date.isoformat()})."
            )
            await _retain_rejected_fetch_artifact(
                db,
                profile,
                adapter,
                request_binding,
                fetch_result=fetch_result,
                failure=failure,
                validation={
                    "status": "composition_after_requested_date",
                    "reported_composition_date": composition_date.isoformat(),
                },
                requested_date=requested_date,
            )
            raise failure
        try:
            _ensure_holdings_dates_are_not_future(
                composition_date,
                requested_date,
            )
        except ValueError as exc:
            await _retain_rejected_fetch_artifact(
                db,
                profile,
                adapter,
                request_binding,
                fetch_result=fetch_result,
                failure=exc,
                validation={
                    "status": "future_dated",
                    "reported_composition_date": composition_date.isoformat(),
                },
                requested_date=requested_date,
            )
            raise
        try:
            snapshot = await ingest_holdings_snapshot(
                db,
                etf_instrument=profile.instrument,
                rows=fetch_result.rows,
                composition_date=composition_date,
                as_of_date=requested_date,
                known_at=known_at,
                published_at=published_at,
                provenance=str(
                    result_metadata.get("snapshot_provenance") or "issuer_self_snapshotted_holdings"
                ),
                source_provider=str(source_provider),
                source_url=fetch_result.source_url,
                source_identifier=fetch_result.source_identifier or issuer_product_id,
                source_quality=str(
                    result_metadata.get("source_quality")
                    or aliases.get("holdings_source_quality")
                    or "self_snapshotted_holdings"
                ),
                completeness_status=_holdings_completeness_status(result_metadata, aliases),
                parser_version=str(
                    result_metadata.get("parser_version")
                    or f"{adapter.adapter_key}-{source_format}-v1"
                ),
                raw_payload_text=fetch_result.raw_text,
                raw_payload_json=fetch_result.raw_json,
                legal_metadata={
                    **result_metadata,
                    "terms_note": aliases.get("terms_note"),
                    "artifact_identity_validation": artifact_identity_validation,
                    "timing_provenance": {
                        "composition_date": (
                            "provider_reported"
                            if _date_from_value(result_metadata.get("composition_date"))
                            else "requested_date_fallback"
                        ),
                        "as_of_date": "requested_date",
                        "known_at": (
                            "provider_reported"
                            if result_metadata.get("known_at")
                            else "published_at_fallback"
                            if published_at
                            else "ingestion_time_fallback"
                        ),
                        "published_at": "provider_reported" if published_at else "not_reported",
                    },
                },
                notes=(
                    "Reconstructed from SEC EDGAR holdings filings through the ETF profile's "
                    "provider-specific adapter."
                    if result_metadata.get("route_resolution") == "sec_edgar_filing_fallback"
                    else "Fetched through the ETF profile's dated issuer holdings adapter route."
                ),
                # Issuer artifacts already carry their canonical symbol/identifier
                # evidence.  Do not fan out synchronously to optional metadata
                # providers for every row; unresolved rows remain explicit and can
                # be reconciled by a bounded background job later.
                allow_provider_enrichment=False,
            )
        except BaseException as exc:
            await _retain_rejected_fetch_artifact(
                db,
                profile,
                adapter,
                request_binding,
                fetch_result=fetch_result,
                failure=exc,
                validation={
                    "status": "ingest_rejected",
                    "requested_date": requested_date.isoformat(),
                    "composition_date": composition_date.isoformat(),
                },
                requested_date=requested_date,
            )
            raise
    except Exception as exc:
        # An ingest flush can invalidate the caller's transaction. Keep the
        # original exception intact and let its owner roll back; never use the
        # failed caller session to record diagnostics after independent raw
        # retention has already preserved the fetched evidence.
        if db.is_active:
            await _record_failure(db, profile, exc)
            await db.flush()
        raise

    await _record_success(db, profile, snapshot=snapshot)
    await db.flush()
    return snapshot


async def refresh_benchmark_family_holdings_for_date(
    db: AsyncSession,
    *,
    family_key: str,
    requested_date: date,
    roles: list[str] | None = None,
) -> dict[str, Any]:
    """Refresh every selected mapped family leg for one historical date.

    This is an administrative/backfill operation, not an interactive provider fan-out.  Each
    role is reported independently so an unavailable style leg or one issuer failure cannot be
    represented as a family-wide success or silently substituted with another proxy.
    """

    normalized_family_key = family_key.strip().lower()
    family = next(
        (
            item
            for item in BENCHMARK_FAMILY_REGISTRY
            if str(item.get("logical_key", "")).strip().lower() == normalized_family_key
        ),
        None,
    )
    if family is None:
        raise ValueError(f"Unknown benchmark family: {family_key}.")

    requested_roles = _normalize_benchmark_family_roles(roles)

    legs: list[dict[str, Any]] = []
    refreshed = unavailable = failed = 0
    for role in requested_roles:
        mapping = family.get(role) if isinstance(family.get(role), dict) else None
        symbol = (
            str(mapping.get("symbol")).strip().upper()
            if mapping and mapping.get("symbol")
            else None
        )
        if not symbol:
            unavailable += 1
            legs.append(
                {
                    "role": role,
                    "symbol": None,
                    "status": "unavailable",
                    "message": "No verified mapped proxy is configured for this family role.",
                }
            )
            continue

        try:
            instrument = await ensure_lightweight_etf_instrument(
                db,
                symbol=symbol,
                name=str(mapping.get("label") or symbol),
            )
            profile = await ensure_etf_profile(db, instrument)
            _apply_known_route_metadata(profile)
            probe = await probe_etf_holdings_adapter_route(db, profile)
            if probe.status != "ready":
                unavailable += 1
                legs.append(
                    {
                        "role": role,
                        "symbol": symbol,
                        "status": "route_not_ready",
                        "message": probe.reason or "No usable free holdings route is configured.",
                    }
                )
                continue
            snapshot = await refresh_etf_holdings_for_date(
                db,
                profile,
                requested_date=requested_date,
            )
        except ETFHoldingsRouteNotReadyError as exc:
            unavailable += 1
            legs.append(
                {
                    "role": role,
                    "symbol": symbol,
                    "status": "route_not_ready",
                    "message": str(exc),
                }
            )
        except Exception as exc:  # noqa: BLE001 - isolate one family leg's backfill failure.
            failed += 1
            legs.append(
                {
                    "role": role,
                    "symbol": symbol,
                    "status": "failed",
                    "message": str(exc) or "Dated family holdings refresh failed.",
                }
            )
        else:
            refreshed += 1
            legs.append(
                {
                    "role": role,
                    "symbol": symbol,
                    "status": "refreshed",
                    "snapshot_id": snapshot.id,
                    "composition_date": snapshot.composition_date,
                }
            )

    await db.flush()
    return {
        "family_key": normalized_family_key,
        "requested_date": requested_date,
        "roles": requested_roles,
        "refreshed": refreshed,
        "unavailable": unavailable,
        "failed": failed,
        "legs": legs,
    }


def _normalize_benchmark_family_roles(roles: list[str] | None) -> list[str]:
    requested_roles = roles or list(_BENCHMARK_FAMILY_ROLES)
    normalized_roles: list[str] = []
    for role in requested_roles:
        normalized_role = str(role).strip().lower()
        if normalized_role not in _BENCHMARK_FAMILY_ROLES:
            raise ValueError(
                f"Unsupported benchmark family role {role!r}; expected one of "
                f"{', '.join(_BENCHMARK_FAMILY_ROLES)}."
            )
        if normalized_role not in normalized_roles:
            normalized_roles.append(normalized_role)
    return normalized_roles


def _normalize_benchmark_family_keys(family_keys: list[str] | None) -> list[str]:
    available = {
        str(item.get("logical_key", "")).strip().lower()
        for item in BENCHMARK_FAMILY_REGISTRY
        if item.get("logical_key")
    }
    requested = {str(value).strip().lower() for value in (family_keys or []) if str(value).strip()}
    unknown = sorted(requested - available)
    if unknown:
        raise ValueError(f"Unknown benchmark family key(s): {', '.join(unknown)}.")
    if not requested:
        return [str(item["logical_key"]).strip().lower() for item in BENCHMARK_FAMILY_REGISTRY]
    return [
        str(item["logical_key"]).strip().lower()
        for item in BENCHMARK_FAMILY_REGISTRY
        if str(item["logical_key"]).strip().lower() in requested
    ]


async def refresh_all_benchmark_family_holdings_for_date(
    db: AsyncSession,
    *,
    requested_date: date,
    family_keys: list[str] | None = None,
    roles: list[str] | None = None,
) -> dict[str, Any]:
    """Refresh every selected benchmark family for one date.

    This is an administrative orchestration contract for populating the locked watchlist
    universes. Family order is deterministic and each family delegates to the existing role-
    isolated operation, so unavailable or failed legs remain explicit instead of being replaced.
    """

    normalized_family_keys = _normalize_benchmark_family_keys(family_keys)
    normalized_roles = _normalize_benchmark_family_roles(roles)
    families: list[dict[str, Any]] = []
    refreshed = unavailable = failed = 0
    for family_key in normalized_family_keys:
        try:
            async with _bootstrap_savepoint(db):
                summary = await refresh_benchmark_family_holdings_for_date(
                    db,
                    family_key=family_key,
                    requested_date=requested_date,
                    roles=normalized_roles,
                )
        except Exception as exc:  # noqa: BLE001 - retain one-family failure and continue.
            failed += 1
            summary = {
                "family_key": family_key,
                "requested_date": requested_date,
                "roles": normalized_roles,
                "refreshed": 0,
                "unavailable": 0,
                "failed": 1,
                "legs": [],
                "error": str(exc) or "Benchmark family holdings refresh failed.",
            }
        else:
            refreshed += int(summary.get("refreshed", 0))
            unavailable += int(summary.get("unavailable", 0))
            failed += int(summary.get("failed", 0))
        families.append(summary)

    await db.flush()
    return {
        "requested_date": requested_date,
        "family_keys": normalized_family_keys,
        "roles": normalized_roles,
        "refreshed": refreshed,
        "unavailable": unavailable,
        "failed": failed,
        "families": families,
    }


async def refresh_benchmark_family_holdings_for_dates(
    db: AsyncSession,
    *,
    family_key: str,
    requested_dates: list[date],
    roles: list[str] | None = None,
) -> dict[str, Any]:
    """Backfill a bounded set of family dates without collapsing role failures.

    Dates are de-duplicated and processed in chronological order.  The existing single-date
    operation owns role routing and failure isolation; this wrapper only provides a durable,
    bounded range contract for scheduled maintenance and historical acceptance.
    """

    normalized_dates = sorted({value for value in requested_dates})
    if not normalized_dates:
        raise ValueError("At least one requested family holdings date is required.")
    runs: list[dict[str, Any]] = []
    refreshed = unavailable = failed = 0
    normalized_roles: list[str] | None = None
    for requested_date in normalized_dates:
        summary = await refresh_benchmark_family_holdings_for_date(
            db,
            family_key=family_key,
            requested_date=requested_date,
            roles=roles,
        )
        normalized_roles = list(summary["roles"])
        refreshed += int(summary["refreshed"])
        unavailable += int(summary["unavailable"])
        failed += int(summary["failed"])
        runs.append(summary)
    return {
        "family_key": str(family_key).strip().lower(),
        "requested_dates": normalized_dates,
        "roles": normalized_roles or [],
        "refreshed": refreshed,
        "unavailable": unavailable,
        "failed": failed,
        "runs": runs,
    }


async def refresh_all_benchmark_family_holdings_for_dates(
    db: AsyncSession,
    *,
    requested_dates: list[date],
    family_keys: list[str] | None = None,
    roles: list[str] | None = None,
) -> dict[str, Any]:
    """Backfill every selected family over bounded dates with independent run summaries."""

    normalized_dates = sorted({value for value in requested_dates})
    if not normalized_dates:
        raise ValueError("At least one requested benchmark family holdings date is required.")
    normalized_family_keys = _normalize_benchmark_family_keys(family_keys)
    normalized_roles = _normalize_benchmark_family_roles(roles)
    runs: list[dict[str, Any]] = []
    refreshed = unavailable = failed = 0
    for requested_date in normalized_dates:
        summary = await refresh_all_benchmark_family_holdings_for_date(
            db,
            requested_date=requested_date,
            family_keys=normalized_family_keys,
            roles=normalized_roles,
        )
        refreshed += int(summary["refreshed"])
        unavailable += int(summary["unavailable"])
        failed += int(summary["failed"])
        runs.append(summary)
    return {
        "requested_dates": normalized_dates,
        "family_keys": normalized_family_keys,
        "roles": normalized_roles,
        "refreshed": refreshed,
        "unavailable": unavailable,
        "failed": failed,
        "runs": runs,
    }


def _aliases(profile: ETFProfile) -> dict[str, Any]:
    aliases = profile.provider_aliases or {}
    return aliases if isinstance(aliases, dict) else {}


def _apply_known_route_metadata(
    profile: ETFProfile,
    *,
    route_metadata: dict[str, Any] | None = None,
) -> bool:
    """Apply curated symbol-to-issuer routing to an existing ETF profile.

    A profile may have been created before a curated route was added, or may
    have been inferred from a weaker provider/name match. The explicit
    ``holdings_adapter`` alias in canonical route metadata is stronger than
    that historical inference and must win during both bootstrap and bulk
    refresh. Returning whether metadata was found keeps callers simple while
    leaving unresolved/unknown profiles untouched.
    """

    instrument = getattr(profile, "instrument", None)
    symbol = str(getattr(instrument, "symbol", "") or "").strip().upper()
    if not symbol:
        return False

    route_metadata = route_metadata or known_etf_route_metadata(
        symbol,
        canonical_issuer=getattr(instrument, "issuer", None),
    )
    if not route_metadata:
        return False

    issuer = route_metadata.get("issuer")
    if issuer:
        profile.issuer = issuer

    seeded_aliases = route_metadata.get("provider_aliases")
    if isinstance(seeded_aliases, dict):
        profile.provider_aliases = {
            **_aliases(profile),
            **seeded_aliases,
        }
        profile.sec_cik = (
            str(seeded_aliases.get("sec_cik") or getattr(profile, "sec_cik", None) or "").strip()
            or None
        )
        profile.sec_series_id = (
            str(
                seeded_aliases.get("sec_series_id") or getattr(profile, "sec_series_id", None) or ""
            ).strip()
            or None
        )
        profile.sec_class_id = (
            str(
                seeded_aliases.get("sec_class_id") or getattr(profile, "sec_class_id", None) or ""
            ).strip()
            or None
        )

        explicit_adapter = str(seeded_aliases.get("holdings_adapter") or "").strip().lower()
        explicit_adapter_impl = get_holdings_adapter(explicit_adapter) if explicit_adapter else None
        if explicit_adapter_impl is not None:
            aliases = _aliases(profile)
            source_provider = (
                str(getattr(explicit_adapter_impl, "source_provider", "")).strip().lower()
            )
            if source_provider:
                # The adapter registry is the native route's publisher
                # identity. Persist it beside the curated adapter key so the
                # shared Provider bridge can verify the exact same identity;
                # this does not create or enable a Provider source/policy.
                profile.provider_aliases = {
                    **aliases,
                    "holdings_source_provider": aliases.get("holdings_source_provider")
                    or source_provider,
                }
            profile.adapter_key = explicit_adapter
            profile.adapter_status = "candidate"
            profile.adapter_confidence = Decimal("0.9000")
            return True

    probe = infer_adapter_key(
        issuer=getattr(profile, "issuer", None),
        fund_family=getattr(profile, "fund_family", None),
        name=getattr(instrument, "name", None) or symbol,
        product_url=getattr(profile, "product_url", None),
        provider_aliases=_aliases(profile),
    )
    if probe.status != "holdings_adapter_unresolved":
        profile.adapter_key = probe.adapter_key
        profile.adapter_status = probe.status
        profile.adapter_confidence = probe.confidence
    return True


def _first_alias(aliases: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = aliases.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _provider_request_attempts(request_binding: Any) -> list[dict[str, Any]]:
    """Persist each request-log ID with the exact redacted effective URL."""

    return [
        {
            "request_log_id": request_id,
            "request_url": bounded_redact_provider_message(
                request_binding.request_urls_by_log_id.get(request_id, ""), max_length=2000
            ),
        }
        for request_id in request_binding.request_log_ids
    ]


def _issuer_product_identifier(identifiers: dict[str, Any]) -> str | None:
    """Choose issuer route identity before weaker SEC series metadata.

    Issuer-native routes such as VanEck require a product slug. SEC enrichment
    can add ``sec_series_id`` later, so that value must not shadow an explicit
    issuer route identifier when refreshing a profile.
    """

    return _first_alias(
        identifiers,
        "product_slug",
        "issuer_product_id",
        "fund_id",
        "product_id",
        "sec_series_id",
    )


def _string_aliases(profile: ETFProfile) -> dict[str, str]:
    aliases = _aliases(profile)
    identifiers: dict[str, str] = {}
    for key, value in aliases.items():
        if isinstance(value, str) and value.strip():
            identifiers[key] = value.strip()
    for key, value in {
        "issuer": profile.issuer,
        "sponsor": profile.sponsor,
        "fund_family": profile.fund_family,
        "product_url": profile.product_url,
        "sec_cik": profile.sec_cik,
        "sec_series_id": profile.sec_series_id,
        "sec_class_id": profile.sec_class_id,
    }.items():
        if value:
            identifiers.setdefault(key, value)
    return identifiers


def _alias_date(aliases: dict[str, Any], key: str) -> date | None:
    return _date_from_value(aliases.get(key))


def _date_from_value(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        return date.fromisoformat(value.strip())
    return None


def _datetime_from_value(value: Any) -> datetime | None:
    """Parse an optional provider timestamp and normalize it to UTC."""

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _bool_alias(aliases: dict[str, Any], key: str) -> bool:
    value = aliases.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


def _artifact_identity_expectations(profile: ETFProfile) -> list[dict[str, str]]:
    aliases = _aliases(profile)
    candidates = {
        "expected_symbol": [
            "expected_etf_symbol",
            "expected_fund_symbol",
            "expected_symbol",
            "expected_ticker",
        ],
        "expected_name": [
            "expected_etf_name",
            "expected_fund_name",
            "expected_name",
        ],
        "expected_cusip": ["expected_cusip", "etf_cusip", "fund_cusip"],
        "expected_isin": ["expected_isin", "etf_isin", "fund_isin"],
    }
    expectations: list[dict[str, str]] = []
    for label, keys in candidates.items():
        value = _first_alias(aliases, *keys)
        if value:
            expectations.append({"type": label, "value": value})
    return expectations


def _normalize_identity_text(value: str) -> str:
    return "".join(char for char in value.upper() if char.isalnum())


def _identity_key(value: str) -> str:
    return _normalize_identity_text(value).lower()


def _identity_type_for_key(key: str, *, preamble: bool) -> str | None:
    normalized = _identity_key(key)
    name_keys = {
        "fund",
        "fundname",
        "fundfullname",
        "etf",
        "etfname",
        "etffullname",
        "productname",
        "portfolioname",
    }
    symbol_keys = {
        "fundticker",
        "fundsymbol",
        "etfticker",
        "etfsymbol",
        "productticker",
        "productsymbol",
        "tickersymbol",
    }
    if preamble:
        symbol_keys |= {"ticker", "symbol"}
    if normalized in name_keys:
        return "artifact_name"
    if normalized in symbol_keys:
        return "artifact_symbol"
    if normalized in {"cusip", "fundcusip", "etfcusip"}:
        return "artifact_cusip"
    if normalized in {"isin", "fundisin", "etfisin"}:
        return "artifact_isin"
    return None


def _add_artifact_identity(
    identities: list[dict[str, str]],
    *,
    identity_type: str | None,
    value: Any,
) -> None:
    if identity_type is None:
        return
    text = str(value).strip() if value is not None else ""
    if not text:
        return
    candidate = {"type": identity_type, "value": text}
    if candidate not in identities:
        identities.append(candidate)


def _extract_artifact_identities(raw_text: str | None) -> list[dict[str, str]]:
    if not raw_text:
        return []
    lines = [line for line in raw_text.splitlines() if line.strip()]
    identities: list[dict[str, str]] = []
    for row in csv.reader(StringIO("\n".join(lines[:25]))):
        if len(row) != 2:
            continue
        identity_type = _identity_type_for_key(row[0], preamble=True)
        _add_artifact_identity(identities, identity_type=identity_type, value=row[1])

    for header_index, line in enumerate(lines[:25]):
        header = next(csv.reader(StringIO(line)), [])
        if len(header) < 2:
            continue
        explicit_columns = [
            (index, _identity_type_for_key(column, preamble=False))
            for index, column in enumerate(header)
        ]
        explicit_columns = [(index, kind) for index, kind in explicit_columns if kind]
        if not explicit_columns:
            continue
        body = "\n".join(lines[header_index : header_index + 12])
        for row in csv.DictReader(StringIO(body)):
            for index, identity_type in explicit_columns:
                key = header[index]
                _add_artifact_identity(
                    identities,
                    identity_type=identity_type,
                    value=row.get(key),
                )
        break
    return identities


def _profile_identity_expectations(profile: ETFProfile) -> list[dict[str, str]]:
    if profile.instrument is None:
        return []
    expectations = [{"type": "profile_symbol", "value": profile.instrument.symbol}]
    if profile.instrument.name and _normalize_identity_text(
        profile.instrument.name
    ) != _normalize_identity_text(profile.instrument.symbol):
        expectations.append({"type": "profile_name", "value": profile.instrument.name})
    return expectations


def _identity_matches(actual: str, expected: str) -> bool:
    return _normalize_identity_text(actual) == _normalize_identity_text(expected)


def _validate_extracted_artifact_identity(
    profile: ETFProfile,
    extracted: list[dict[str, str]],
) -> dict[str, Any] | None:
    profile_expectations = _profile_identity_expectations(profile)
    symbol_expectation = next(
        (item for item in profile_expectations if item["type"] == "profile_symbol"),
        None,
    )
    name_expectation = next(
        (item for item in profile_expectations if item["type"] == "profile_name"),
        None,
    )
    symbol_identities = [
        item
        for item in extracted
        if item["type"] in {"artifact_symbol", "artifact_cusip", "artifact_isin"}
    ]
    name_identities = [item for item in extracted if item["type"] == "artifact_name"]
    if symbol_expectation is not None and symbol_identities:
        matched = [
            item
            for item in symbol_identities
            if _identity_matches(item["value"], symbol_expectation["value"])
        ]
        if matched:
            return {
                "status": "matched_inferred",
                "required": True,
                "matched": matched,
                "expected": [symbol_expectation],
                "artifact_identity": extracted,
            }
        return {
            "status": "mismatch",
            "required": True,
            "matched": [],
            "expected": [symbol_expectation],
            "artifact_identity": extracted,
            "reason": "Fetched holdings artifact declares a different ETF symbol/identifier.",
        }
    if name_expectation is not None and name_identities:
        matched = [
            item
            for item in name_identities
            if _identity_matches(item["value"], name_expectation["value"])
        ]
        if matched:
            return {
                "status": "matched_inferred",
                "required": True,
                "matched": matched,
                "expected": [name_expectation],
                "artifact_identity": extracted,
            }
        return {
            "status": "mismatch",
            "required": True,
            "matched": [],
            "expected": [name_expectation],
            "artifact_identity": extracted,
            "reason": "Fetched holdings artifact declares a different ETF name.",
        }
    return None


def _validate_artifact_identity(
    profile: ETFProfile,
    raw_text: str | None,
    *,
    verified_body_identity: list[str] | None = None,
) -> dict[str, Any]:
    expectations = _artifact_identity_expectations(profile)
    extracted = _extract_artifact_identities(raw_text)
    required = bool(expectations) or _bool_alias(
        _aliases(profile), "require_artifact_identity_match"
    )
    # A strict adapter may validate identity from a structured source artifact
    # that is not represented in the normalized holdings table text (for
    # example, an XLSX worksheet title). The caller supplies this only after
    # checking the registered VanEck OIH adapter and its matched body evidence.
    if verified_body_identity:
        profile_expectations = _profile_identity_expectations(profile)
        symbol_expectations = [
            item["value"]
            for item in (*profile_expectations, *expectations)
            if item["type"] in {"profile_symbol", "expected_symbol"}
        ]
        name_expectations = [
            item["value"]
            for item in (*profile_expectations, *expectations)
            if item["type"] in {"profile_name", "expected_name"}
        ]
        identifier_expectations = {
            "artifact_cusip": [
                item["value"] for item in expectations if item["type"] == "expected_cusip"
            ],
            "artifact_isin": [
                item["value"] for item in expectations if item["type"] == "expected_isin"
            ],
        }
        for identity in extracted:
            expected_values = (
                symbol_expectations
                if identity["type"] == "artifact_symbol"
                else name_expectations
                if identity["type"] == "artifact_name"
                else identifier_expectations.get(identity["type"], [])
            )
            if expected_values and not all(
                _identity_matches(identity["value"], expected) for expected in expected_values
            ):
                return {
                    "status": "mismatch",
                    "required": True,
                    "matched": [],
                    "expected": expectations or profile_expectations,
                    "artifact_identity": extracted,
                    "body_identity_evidence": verified_body_identity,
                    "reason": "Structured workbook identity conflicts with explicit fund identity.",
                }
        return {
            "status": "matched",
            "required": required,
            "matched": [
                {"type": "verified_body_identity", "value": evidence}
                for evidence in verified_body_identity
            ],
            "expected": expectations,
            "artifact_identity": extracted,
            "body_identity_evidence": verified_body_identity,
        }
    if not raw_text:
        status = "missing_raw_artifact" if required else "unverified"
        return {
            "status": status,
            "required": required,
            "matched": [],
            "expected": expectations,
            "artifact_identity": extracted,
            "reason": "No raw text artifact was available for identity validation.",
        }

    normalized_artifact = _normalize_identity_text(raw_text)
    matched = [
        expectation
        for expectation in expectations
        if _normalize_identity_text(expectation["value"]) in normalized_artifact
    ]
    if matched:
        return {
            "status": "matched",
            "required": required,
            "matched": matched,
            "expected": expectations,
            "artifact_identity": extracted,
        }
    if required:
        return {
            "status": "mismatch",
            "required": True,
            "matched": [],
            "expected": expectations,
            "artifact_identity": extracted,
            "reason": "Fetched holdings artifact did not contain any configured ETF identity.",
        }
    extracted_validation = _validate_extracted_artifact_identity(profile, extracted)
    if extracted_validation is not None:
        return extracted_validation
    return {
        "status": "unverified",
        "required": False,
        "matched": [],
        "expected": expectations,
        "artifact_identity": extracted,
        "reason": "No explicit ETF artifact identity expectations were configured.",
    }


def _verified_vaneck_oih_body_identity(
    profile: ETFProfile,
    adapter: Any,
    fetch_result: Any,
) -> list[str] | None:
    """Return strict OIH workbook identity only from the registered adapter result."""

    instrument = profile.instrument
    metadata = fetch_result.legal_metadata if isinstance(fetch_result.legal_metadata, dict) else {}
    aliases = _string_aliases(profile)
    evidence = metadata.get("body_identity_evidence")
    composition_date = _date_from_value(metadata.get("composition_date"))
    if (
        str(getattr(adapter, "adapter_key", "")).strip().lower() != "vaneck"
        or str(getattr(adapter, "source_provider", "")).strip().lower() != "vaneck"
        or instrument is None
        or instrument.symbol.strip().upper() != "OIH"
        or _first_alias(aliases, "product_slug", "issuer_product_id", "fund_slug")
        != "oil-services-etf-oih"
        or metadata.get("source_provider") != "vaneck"
        or metadata.get("product_slug") != "oil-services-etf-oih"
        or metadata.get("body_identity_status") != "matched"
        or composition_date is None
        or not isinstance(evidence, list)
        or not evidence
        or any(
            not isinstance(item, str) or not item.strip() or len(item) > 240 for item in evidence
        )
    ):
        return None
    return [item.strip() for item in evidence]


def _ensure_artifact_identity_is_safe(validation: dict[str, Any]) -> None:
    if validation["status"] in {"mismatch", "missing_raw_artifact"}:
        expected = ", ".join(
            f"{item['type']}={item['value']}" for item in validation.get("expected", [])
        )
        raise ValueError(
            "Fetched holdings artifact failed ETF identity validation"
            + (f" ({expected})." if expected else ".")
        )


async def _refresh_adapter_route(
    db: AsyncSession,
    profile: ETFProfile,
    *,
    probe: HoldingsAdapterProbe | None = None,
    acquisition_request_id: str | None = None,
    atomic_ingest_savepoint: bool = False,
    request_log_ids_out: list[int] | None = None,
    vaneck_initial_qualification_job_id: int | None = None,
    vaneck_initial_qualification_budget: Any | None = None,
    vaneck_initial_qualification_authority: Any | None = None,
    native_initial_qualification_job_id: int | None = None,
    native_initial_qualification_scope: dict[str, Any] | None = None,
):
    aliases = _aliases(profile)
    if profile.instrument is None:
        raise ValueError("ETF profile is missing its linked instrument.")

    adapter = get_holdings_adapter(profile.adapter_key)
    if adapter is None:
        raise ValueError(f"No ETF holdings adapter is registered for {profile.adapter_key}.")

    symbol = profile.instrument.symbol
    identifiers = _string_aliases(profile)
    if identifiers.get("issuer_product_catalog_key") == "ishares_us_etf_products_v1":
        # This value comes from the already-resolved canonical Instrument row,
        # never a request field or profile alias. It is an identity check for
        # the official catalog row, not a source/product identity by itself.
        identifiers["canonical_fund_name"] = str(profile.instrument.name or "")
    issuer_product_id = _issuer_product_identifier(identifiers)
    probe = probe or adapter.probe(
        symbol=symbol, name=profile.instrument.name, identifiers=identifiers
    )
    if probe.status != "ready":
        required = ", ".join(probe.required_identifiers) or "provider-specific route"
        raise ETFHoldingsRouteNotReadyError(
            f"{probe.reason or probe.status} Required route metadata: {required}."
        )

    with bind_etf_holdings_request_context(
        db=db,
        adapter=adapter,
        profile_id=profile.id,
        instrument_id=profile.instrument.id,
        provider_symbol=symbol,
        operation="fetch_etf_holdings_latest",
        vaneck_initial_qualification_budget=vaneck_initial_qualification_budget,
        vaneck_initial_qualification_job_id=vaneck_initial_qualification_job_id,
        vaneck_initial_qualification_authority=vaneck_initial_qualification_authority,
        native_initial_qualification_job_id=native_initial_qualification_job_id,
        native_initial_qualification_scope=native_initial_qualification_scope,
    ) as request_binding:
        try:
            if vaneck_initial_qualification_job_id is not None:
                if (
                    vaneck_initial_qualification_job_id <= 0
                    or profile.instrument.symbol.strip().upper() != "OIH"
                    or str(getattr(adapter, "source_provider", "")).strip().lower() != "vaneck"
                    or not callable(getattr(adapter, "fetch_initial_qualification", None))
                ):
                    raise ETFHoldingsRouteHeldError(
                        "VanEck initial qualification is restricted to its reviewed OIH adapter."
                    )
                fetch_result = await adapter.fetch_initial_qualification(
                    symbol=symbol,
                    issuer_product_id=issuer_product_id,
                    identifiers=identifiers,
                    reviewed_request_url=(
                        vaneck_initial_qualification_budget.expected_url
                        if vaneck_initial_qualification_budget is not None
                        else None
                    ),
                )
            else:
                fetch_result = await adapter.fetch_latest(
                    symbol=symbol,
                    issuer_product_id=issuer_product_id,
                    identifiers=identifiers,
                )
        except BaseException as exc:
            if request_log_ids_out is not None:
                request_log_ids_out.extend(
                    request_log_id
                    for request_log_id in request_binding.request_log_ids
                    if request_log_id not in request_log_ids_out
                )
            await _retain_rejected_fetch_artifact(
                db,
                profile,
                adapter,
                request_binding,
                failure=exc,
                validation=_acquisition_validation(acquisition_request_id),
            )
            raise
    if request_log_ids_out is not None:
        request_log_ids_out.extend(
            request_log_id
            for request_log_id in request_binding.request_log_ids
            if request_log_id not in request_log_ids_out
        )
    if not fetch_result.rows:
        failure = ValueError("Issuer holdings route returned no parseable rows.")
        await _retain_rejected_fetch_artifact(
            db,
            profile,
            adapter,
            request_binding,
            fetch_result=fetch_result,
            failure=failure,
            validation=_acquisition_validation(acquisition_request_id),
        )
        raise failure
    verified_body_identity = _verified_vaneck_oih_body_identity(profile, adapter, fetch_result)
    artifact_identity_validation = _validate_artifact_identity(
        profile,
        fetch_result.raw_text,
        verified_body_identity=verified_body_identity,
    )
    native_qualification_evidence: dict[str, Any] | None = None
    native_source_evidence: dict[str, Any] | None = None
    if native_initial_qualification_job_id is not None:
        try:
            native_qualification_evidence = _native_initial_qualification_fetch_evidence(
                profile,
                adapter,
                fetch_result,
                request_binding=request_binding,
            )
            fund_identity = native_qualification_evidence["fund_identity"]
            if fund_identity.get("basis") in {
                "issuer_product_catalog",
                "invesco_product_catalog",
            }:
                from app.services.etf_holdings_native_qualification import (  # noqa: PLC0415
                    _verify_invesco_catalog_identity_evidence,
                    _verify_issuer_catalog_identity_evidence,
                )

                qualification_job = await db.get(
                    ETFHoldingsBackfillJob,
                    native_initial_qualification_job_id,
                )
                catalog_source = await db.scalar(
                    select(DataSource)
                    .where(DataSource.name == adapter.source_provider)
                    .execution_options(populate_existing=True)
                )
                if qualification_job is None or catalog_source is None:
                    raise ValueError(
                        "Native catalog qualification is missing its committed source or attempt"
                    )
                await db.refresh(qualification_job, attribute_names=["extra_data"])
                verifier = (
                    _verify_invesco_catalog_identity_evidence
                    if fund_identity.get("basis") == "invesco_product_catalog"
                    else _verify_issuer_catalog_identity_evidence
                )
                await verifier(
                    db,
                    evidence=fund_identity,
                    profile=profile,
                    source=catalog_source,
                    job=qualification_job,
                )
            native_source_evidence = native_qualification_evidence
            artifact_identity_validation = _native_artifact_identity_validation(
                profile,
                artifact_identity_validation,
                native_qualification_evidence,
            )
        except (ETFHoldingsRouteHeldError, ValueError) as exc:
            await _retain_rejected_fetch_artifact(
                db,
                profile,
                adapter,
                request_binding,
                fetch_result=fetch_result,
                failure=exc,
                validation={"status": "native_initial_qualification_evidence_rejected"},
            )
            raise
    else:
        try:
            result_provider = (
                str((fetch_result.legal_metadata or {}).get("source_provider") or "")
                .strip()
                .lower()
            )
            route_resolution = (
                str((fetch_result.legal_metadata or {}).get("route_resolution") or "")
                .strip()
                .lower()
            )
            if (
                result_provider == str(getattr(adapter, "source_provider", "")).strip().lower()
                and result_provider
                in {
                    "spdr",
                    "invesco",
                    "ishares",
                    "amplify",
                }
                and route_resolution != "issuer_product_page_discovery"
            ):
                # Native adapter responses carry their own dated/completeness
                # contract. Product-page discovery is the older explicit
                # issuer-file route: keep its parser/identity behavior, but do
                # not promote alias dates or inferred row counts to native proof.
                native_source_evidence = _native_adapter_fetch_evidence(
                    profile,
                    adapter,
                    fetch_result,
                    request_binding=request_binding,
                    require_body_witness=False,
                )
                fund_identity = native_source_evidence.get("fund_identity")
                if isinstance(fund_identity, dict) and fund_identity.get("basis") in {
                    "issuer_product_catalog",
                    "invesco_product_catalog",
                }:
                    from types import SimpleNamespace  # noqa: PLC0415

                    from app.services.etf_holdings_native_qualification import (  # noqa: PLC0415
                        _verify_invesco_catalog_identity_evidence,
                        _verify_issuer_catalog_identity_evidence,
                    )

                    catalog_source = await db.scalar(
                        select(DataSource)
                        .where(DataSource.name == adapter.source_provider)
                        .execution_options(populate_existing=True)
                    )
                    lineage_ids = list(request_binding.request_log_ids)
                    lineage_urls = [
                        request_binding.request_urls_by_log_id.get(request_id)
                        for request_id in lineage_ids
                    ]
                    if (
                        catalog_source is None
                        or not lineage_ids
                        or len(lineage_ids) != len(set(lineage_ids))
                        or any(not isinstance(url, str) or not url.strip() for url in lineage_urls)
                    ):
                        raise ValueError("Native catalog request lineage is incomplete")
                    lineage_job = SimpleNamespace(
                        extra_data={
                            "provider_request_log_ids": lineage_ids,
                            "request_urls": lineage_urls,
                        }
                    )
                    verifier = (
                        _verify_invesco_catalog_identity_evidence
                        if fund_identity.get("basis") == "invesco_product_catalog"
                        else _verify_issuer_catalog_identity_evidence
                    )
                    await verifier(
                        db,
                        evidence=fund_identity,
                        profile=profile,
                        source=catalog_source,
                        job=lineage_job,
                    )
                artifact_identity_validation = _native_artifact_identity_validation(
                    profile,
                    artifact_identity_validation,
                    native_source_evidence,
                )
            _ensure_artifact_identity_is_safe(artifact_identity_validation)
        except (ETFHoldingsRouteHeldError, ValueError) as exc:
            await _retain_rejected_fetch_artifact(
                db,
                profile,
                adapter,
                request_binding,
                fetch_result=fetch_result,
                failure=exc,
                validation=_acquisition_validation(
                    acquisition_request_id,
                    artifact_identity_validation,
                ),
            )
            raise

    result_metadata = {
        **(fetch_result.legal_metadata or {}),
        **({"application_request_id": acquisition_request_id} if acquisition_request_id else {}),
        "provider_request_log_ids": request_binding.request_log_ids,
        "provider_request_attempts": _provider_request_attempts(request_binding),
    }
    if native_qualification_evidence is not None:
        # Native qualification may use an issuer's documented business-date
        # field rather than a field literally named composition_date (for
        # example Invesco effectiveBusinessDate). Keep that provider field in
        # the immutable evidence and use its normalized value for persistence.
        result_metadata["composition_date"] = native_qualification_evidence["composition_date"]
        result_metadata["composition_date_source_field"] = native_qualification_evidence[
            "composition_date_source_field"
        ]
        result_metadata["native_composition_completeness_evidence"] = native_qualification_evidence[
            "composition_completeness"
        ]
    elif native_source_evidence is not None:
        result_metadata["composition_date"] = native_source_evidence["composition_date"]
        result_metadata["composition_date_source_field"] = native_source_evidence[
            "composition_date_source_field"
        ]
        result_metadata["native_composition_completeness_evidence"] = native_source_evidence[
            "composition_completeness"
        ]
    if vaneck_initial_qualification_job_id is not None and (
        result_metadata.get("initial_qualification") is not True
        or result_metadata.get("source_provider") != "vaneck"
        or result_metadata.get("product_slug") != "oil-services-etf-oih"
        or not result_metadata.get("composition_date")
        or not (fetch_result.raw_json or {}).get("raw_workbook_sha256")
    ):
        failure = ValueError("VanEck OIH qualification response lacks exact workbook provenance.")
        await _retain_rejected_fetch_artifact(
            db,
            profile,
            adapter,
            request_binding,
            fetch_result=fetch_result,
            failure=failure,
            validation={"status": "qualification_provenance_incomplete"},
        )
        raise failure
    if (
        vaneck_initial_qualification_job_id is not None
        and result_metadata.get("body_identity_status") != "matched"
    ):
        identity_status = result_metadata.get("body_identity_status") or "unverified"
        failure = ValueError(
            f"VanEck OIH workbook body identity is {identity_status}; qualification denied."
        )
        await _retain_rejected_fetch_artifact(
            db,
            profile,
            adapter,
            request_binding,
            fetch_result=fetch_result,
            failure=failure,
            validation={
                "status": "fund_identity_rejected",
                "body_identity_status": identity_status,
                "body_identity_evidence": result_metadata.get("body_identity_evidence"),
            },
        )
        raise failure
    result_metadata = {
        **result_metadata,
        "expected_cadence": result_metadata.get("expected_cadence")
        or infer_expected_cadence(
            source_access=getattr(getattr(adapter, "config", None), "source_access", None),
            metadata=result_metadata,
        ),
    }
    source_format = str(result_metadata.get("source_format") or "csv")
    source_provider = (
        _first_alias(aliases, "holdings_source_provider", "source_provider")
        or result_metadata.get("source_provider")
        or adapter.source_provider
    )
    composition_date = (
        _date_from_value(result_metadata.get("composition_date"))
        if native_source_evidence is not None
        else _alias_date(aliases, "holdings_composition_date")
        or _date_from_value(result_metadata.get("composition_date"))
        or datetime.now(UTC).date()
    )
    as_of_date = _alias_date(aliases, "holdings_as_of_date") or _date_from_value(
        result_metadata.get("as_of_date")
    )
    try:
        _ensure_holdings_dates_are_not_future(composition_date, as_of_date)
    except ValueError as exc:
        await _retain_rejected_fetch_artifact(
            db,
            profile,
            adapter,
            request_binding,
            fetch_result=fetch_result,
            failure=exc,
            validation=_acquisition_validation(
                acquisition_request_id,
                {"status": "future_dated"},
            ),
        )
        raise
    cadence = result_metadata.get("expected_cadence")
    deadline = freshness_deadline(composition_date, str(cadence or "unspecified"))
    if deadline is not None and datetime.now(UTC).date() > deadline:
        failure = ValueError(
            f"Issuer holdings composition {composition_date.isoformat()} is stale "
            f"for the reviewed {cadence or 'unspecified'} cadence."
        )
        await _retain_rejected_fetch_artifact(
            db,
            profile,
            adapter,
            request_binding,
            fetch_result=fetch_result,
            failure=failure,
            validation=_acquisition_validation(
                acquisition_request_id,
                {"status": "stale", "freshness_deadline": deadline.isoformat()},
            ),
        )
        raise failure
    parser_version = str(
        result_metadata.get("parser_version") or f"{adapter.adapter_key}-{source_format}-v1"
    )
    vaneck_oih_schema_fingerprint, legacy_qualification_fingerprint = (
        _vaneck_oih_schema_fingerprints(
            profile,
            adapter,
            fetch_result,
            parser_version=parser_version,
            verified_body_identity=verified_body_identity,
        )
    )
    try:
        await _ensure_schema_fingerprint_is_stable(
            db,
            profile,
            parser_version=parser_version,
            raw_payload_text=fetch_result.raw_text,
            raw_payload_json=fetch_result.raw_json,
            schema_fingerprint_override=vaneck_oih_schema_fingerprint,
            legacy_qualification_fingerprint=legacy_qualification_fingerprint,
        )
    except ETFHoldingsSchemaDriftError as exc:
        await _retain_rejected_fetch_artifact(
            db,
            profile,
            adapter,
            request_binding,
            fetch_result=fetch_result,
            failure=exc,
            validation=_acquisition_validation(
                acquisition_request_id,
                {"status": "schema_drift"},
            ),
        )
        raise

    published_at = _datetime_from_value(result_metadata.get("published_at"))
    known_at = (
        _datetime_from_value(result_metadata.get("known_at")) or published_at or datetime.now(UTC)
    )
    timing_provenance = {
        "composition_date": (
            f"provider_reported:{native_source_evidence['composition_date_source_field']}"
            if native_source_evidence is not None
            else "provider_reported"
            if _date_from_value(result_metadata.get("composition_date"))
            else "profile_alias_fallback"
            if _alias_date(aliases, "holdings_composition_date")
            else "ingestion_date_fallback"
        ),
        "as_of_date": "provider_reported"
        if result_metadata.get("as_of_date")
        else "profile_alias_fallback",
        "known_at": (
            "provider_reported"
            if result_metadata.get("known_at")
            else "published_at_fallback"
            if published_at
            else "ingestion_time_fallback"
        ),
        "published_at": "provider_reported" if published_at else "not_reported",
    }

    try:

        async def ingest_selected_result():
            return await ingest_holdings_snapshot(
                db,
                etf_instrument=profile.instrument,
                rows=fetch_result.rows,
                composition_date=composition_date,
                as_of_date=as_of_date,
                known_at=known_at,
                published_at=published_at,
                provenance=str(
                    result_metadata.get("snapshot_provenance") or "issuer_self_snapshotted_holdings"
                ),
                source_provider=str(source_provider),
                source_url=fetch_result.source_url,
                source_identifier=(
                    native_qualification_evidence["source_identifier"]
                    if native_qualification_evidence is not None
                    else fetch_result.source_identifier or issuer_product_id
                ),
                source_quality=str(
                    result_metadata.get("source_quality")
                    or aliases.get("holdings_source_quality")
                    or "self_snapshotted_holdings"
                ),
                completeness_status=_holdings_completeness_status(result_metadata, aliases),
                parser_version=parser_version,
                raw_payload_text=fetch_result.raw_text,
                raw_payload_json=fetch_result.raw_json,
                schema_fingerprint_override=vaneck_oih_schema_fingerprint,
                legal_metadata={
                    **(fetch_result.legal_metadata or {}),
                    **(
                        {"native_initial_qualification_evidence": native_qualification_evidence}
                        if native_qualification_evidence is not None
                        else {}
                    ),
                    **(
                        {"application_request_id": acquisition_request_id}
                        if acquisition_request_id
                        else {}
                    ),
                    "provider_request_log_ids": request_binding.request_log_ids,
                    "provider_request_attempts": _provider_request_attempts(request_binding),
                    "composition_date": composition_date.isoformat(),
                    **(
                        {
                            "composition_date_source_field": native_source_evidence[
                                "composition_date_source_field"
                            ]
                        }
                        if native_source_evidence is not None
                        else {}
                    ),
                    **(
                        {
                            "native_composition_completeness_evidence": native_source_evidence[
                                "composition_completeness"
                            ]
                        }
                        if native_source_evidence is not None
                        else {}
                    ),
                    "terms_note": aliases.get("terms_note"),
                    "probe_status": probe.status,
                    "probe_confidence": str(probe.confidence),
                    "artifact_identity_validation": artifact_identity_validation,
                    "timing_provenance": timing_provenance,
                },
                notes=(
                    "Reconstructed from SEC EDGAR holdings filings through the ETF profile's "
                    "provider-specific adapter."
                    if result_metadata.get("route_resolution") == "sec_edgar_filing_fallback"
                    else "Fetched through the ETF profile's issuer holdings adapter route."
                ),
                # Keep refresh bounded and provider-neutral.  Constituent resolution
                # uses canonical symbols/identifiers first; optional enrichment is a
                # separate job, never part of the issuer download transaction.
                allow_provider_enrichment=False,
            )

        if atomic_ingest_savepoint:
            async with _bootstrap_savepoint(db):
                snapshot = await ingest_selected_result()
        else:
            snapshot = await ingest_selected_result()
    except BaseException as exc:
        await _retain_rejected_fetch_artifact(
            db,
            profile,
            adapter,
            request_binding,
            fetch_result=fetch_result,
            failure=exc,
            validation=_acquisition_validation(
                acquisition_request_id,
                {
                    "status": "ingest_rejected",
                    "composition_date": composition_date.isoformat(),
                    "as_of_date": as_of_date.isoformat() if as_of_date else None,
                },
            ),
        )
        raise
    profile.adapter_status = "success"
    profile.adapter_confidence = probe.confidence
    return snapshot


def _native_holdings_response_parse_evidence(
    profile: ETFProfile,
    adapter: Any,
    fetch_result: Any,
    *,
    request_binding: Any | None,
) -> dict[str, Any]:
    """Require a captured physical body linked to the exact adapter parse."""

    metadata = fetch_result.legal_metadata
    witness = (
        metadata.get("native_holdings_response_witness") if isinstance(metadata, dict) else None
    )
    capture = witness.get("provider_capture") if isinstance(witness, dict) else None
    raw_payload = (
        fetch_result.raw_json if fetch_result.raw_json is not None else fetch_result.raw_text
    )
    if (
        not isinstance(witness, dict)
        or not isinstance(capture, dict)
        or not isinstance(fetch_result.source_url, str)
        or not fetch_result.source_url.strip()
        or not isinstance(raw_payload, str | dict)
        or not raw_payload
    ):
        raise ETFNativeSourceEvidenceError(
            "Native qualification has no linked holdings response body witness"
        )

    body_hash = capture.get("response_body_sha256")
    parser_hash = witness.get("parser_input_sha256")
    normalized_hash = witness.get("normalized_payload_sha256")
    body_size = capture.get("response_body_bytes")
    parser_size = witness.get("parser_input_bytes")
    request_log_id = capture.get("request_log_id")
    url_hash = hashlib.sha256(
        _canonical_request_url(fetch_result.source_url).encode("utf-8")
    ).hexdigest()
    raw_hash = _hash_payload(raw_payload)
    digest_pattern = re.compile(r"[0-9a-f]{64}")
    if (
        not isinstance(body_hash, str)
        or not digest_pattern.fullmatch(body_hash)
        or parser_hash != body_hash
        or normalized_hash != raw_hash
        or body_size != parser_size
        or isinstance(body_size, bool)
        or not isinstance(body_size, int)
        or body_size <= 0
        or capture.get("physical_request_url_sha256") != url_hash
        or isinstance(request_log_id, bool)
        or not isinstance(request_log_id, int)
        or request_log_id <= 0
        or not isinstance(witness.get("parser"), str)
        or not witness["parser"].strip()
    ):
        raise ETFNativeSourceEvidenceError(
            "Native qualification holdings body, parser input, and retained artifact do not match"
        )

    instrument = profile.instrument
    expected_capture = {
        "profile_id": profile.id,
        "instrument_id": profile.instrument_id,
        "provider": str(getattr(adapter, "source_provider", "")).strip().lower(),
        "provider_symbol": instrument.symbol.strip().upper() if instrument is not None else None,
        "capability": ProviderCapability.ETF_HOLDINGS.value,
        "operation": "fetch_etf_holdings_latest",
    }
    if any(capture.get(field) != value for field, value in expected_capture.items()):
        raise ETFNativeSourceEvidenceError(
            "Native qualification body witness has a mismatched fund or operation"
        )
    if request_binding is not None:
        scope = request_binding.native_initial_qualification_scope
        bound_url = request_binding.request_urls_by_log_id.get(request_log_id)
        if (
            request_binding.native_initial_qualification_job_id != capture.get("attempt_id")
            or not isinstance(scope, dict)
            or request_log_id not in request_binding.request_log_ids
            or capture not in request_binding.response_body_witnesses
            or not isinstance(bound_url, str)
            or hashlib.sha256(_canonical_request_url(bound_url).encode("utf-8")).hexdigest()
            != capture.get("physical_request_url_sha256")
            or capture.get("data_source_id") != scope.get("data_source_id")
            or capture.get("account_scope") != scope.get("account_scope")
            or capture.get("review_revision") != scope.get("review_revision")
            or capture.get("provider_review_fingerprint")
            != scope.get("provider_review_fingerprint")
            or capture.get("attempt_id") != scope.get("attempt_id")
        ):
            raise ETFNativeSourceEvidenceError(
                "Native qualification body witness is outside its committed request scope"
            )
    return {
        **witness,
        "logical_source_url_sha256": url_hash,
        "normalized_payload_sha256": raw_hash,
    }


def _native_adapter_fetch_evidence(
    profile: ETFProfile,
    adapter: Any,
    fetch_result: Any,
    *,
    request_binding: Any | None = None,
    require_body_witness: bool = True,
) -> dict[str, Any]:
    """Validate native fund/date evidence and optionally its sealed body witness.

    Initial qualification requires the Provider-captured response-body witness.
    Ordinary refresh reuses the same source identity and date checks while
    relying on ordinary admission and request lineage, not qualification scope.
    """

    instrument = profile.instrument
    if instrument is None or not isinstance(fetch_result.legal_metadata, dict):
        raise ETFNativeSourceEvidenceError(
            "Native qualification requires committed fund and adapter metadata"
        )
    metadata = fetch_result.legal_metadata
    provider_name = str(getattr(adapter, "source_provider", "")).strip().lower()
    adapter_key = str(getattr(adapter, "adapter_key", "")).strip().lower()
    profile_aliases = _aliases(profile)
    bound_provider = (
        str(
            profile_aliases.get("holdings_source_provider")
            or profile_aliases.get("source_provider")
            or ""
        )
        .strip()
        .lower()
    )
    if (
        not provider_name
        or not adapter_key
        or bound_provider != provider_name
        or str(profile.adapter_key or "").strip().lower() != adapter_key
        or metadata.get("source_provider", provider_name) != provider_name
        or metadata.get("adapter_key", adapter_key) != adapter_key
    ):
        raise ETFNativeSourceEvidenceError(
            "Native qualification adapter identity does not match the ETF profile"
        )

    raw_text = fetch_result.raw_text
    raw_json = fetch_result.raw_json
    if (not isinstance(raw_text, str) or not raw_text.strip()) and not (
        isinstance(raw_json, dict) and bool(raw_json)
    ):
        raise ETFNativeSourceEvidenceError(
            "Native qualification requires the actual nonempty raw source artifact"
        )
    source_identifier = str(fetch_result.source_identifier or "").strip()
    source_url = str(fetch_result.source_url or "").strip()
    if not source_url:
        raise ETFNativeSourceEvidenceError("Native qualification requires the provider source URL")
    if not source_identifier and provider_name not in {"spdr", "amplify"}:
        raise ETFNativeSourceEvidenceError(
            "Native qualification requires its provider source identifier"
        )

    identity_evidence: dict[str, Any] | None = None
    if provider_name == "invesco":
        identity_evidence = _native_invesco_catalog_identity(
            profile=profile,
            adapter=adapter,
            metadata=metadata,
            source_url=source_url,
            source_identifier=source_identifier,
        )
    elif provider_name == "amplify":
        identity_evidence = _native_amplify_account_identity(
            profile=profile,
            adapter=adapter,
            fetch_result=fetch_result,
        )
    elif provider_name == "spdr":
        identity_evidence = _native_spdr_workbook_identity(
            profile=profile,
            adapter=adapter,
            raw_text=raw_text,
            source_url=source_url,
            request_binding=request_binding,
        )
    raw_identity = _native_fund_preamble_identity(profile, raw_text)
    if raw_identity is not None:
        if raw_identity.get("status") == "mismatch":
            raise ETFNativeSourceEvidenceError(
                "Native qualification raw body conflicts with the selected fund identity"
            )
        if identity_evidence is None and provider_name not in {
            "spdr",
            "invesco",
            "ishares",
            "amplify",
        }:
            identity_evidence = {
                "basis": "raw_source_identity",
                "matched": raw_identity.get("matched"),
                "artifact_identity": raw_identity.get("artifact_identity"),
            }
    if provider_name == "ishares":
        body_identity = _native_ishares_holdings_identity(
            profile=profile,
            adapter=adapter,
            raw_json=raw_json,
            source_url=source_url,
        )
    else:
        body_identity = None
    if provider_name == "ishares" and identity_evidence is None:
        from app.services.etf_holdings_native_qualification import (  # noqa: PLC0415
            _issuer_catalog_identity_claim,
        )

        identity_evidence = _issuer_catalog_identity_claim(
            profile,
            metadata.get("issuer_product_catalog"),
        )
        if identity_evidence is None and (
            not isinstance(body_identity, dict)
            or body_identity.get("basis") != "ishares_holdings_product_metadata"
        ):
            identity_evidence = body_identity
    if provider_name == "ishares" and isinstance(body_identity, dict):
        if body_identity.get("basis") == "ishares_holdings_product_metadata":
            if (
                not isinstance(identity_evidence, dict)
                or identity_evidence.get("basis") != "issuer_product_catalog"
                or body_identity.get("product_id") != identity_evidence.get("product_id")
                or body_identity.get("fund_name") != identity_evidence.get("name")
            ):
                raise ETFNativeSourceEvidenceError(
                    "Native iShares product response does not match its exact catalog identity"
                )
        elif isinstance(identity_evidence, dict) and identity_evidence.get("basis") == (
            "issuer_product_catalog"
        ):
            if body_identity.get("symbol") != profile.instrument.symbol.strip().upper() or any(
                _normalize_identity_text(value)
                != _normalize_identity_text(identity_evidence.get("name"))
                for value in body_identity.get("fund_names", [])
                if value
            ):
                raise ETFNativeSourceEvidenceError(
                    "Native iShares holdings rows conflict with the exact catalog identity"
                )
    fund_identity = metadata.get("fund_identity")
    if (
        identity_evidence is None
        and provider_name not in {"spdr", "invesco", "ishares", "amplify"}
        and isinstance(fund_identity, dict)
    ):
        observed_id = fund_identity.get("instrument_id")
        observed_symbol = str(fund_identity.get("symbol") or "").strip().upper()
        observed_name = _normalize_identity_text(str(fund_identity.get("name") or ""))
        expected_name = _normalize_identity_text(str(instrument.name or ""))
        if (
            isinstance(observed_id, int)
            and not isinstance(observed_id, bool)
            and observed_id == instrument.id
            and observed_symbol == instrument.symbol.strip().upper()
            and expected_name
            and observed_name == expected_name
        ):
            identity_evidence = {
                "basis": "adapter_fund_identity",
                "instrument_id": observed_id,
                "symbol": observed_symbol,
                "name": str(fund_identity.get("name")),
            }
    if identity_evidence is None and provider_name not in {
        "spdr",
        "invesco",
        "ishares",
        "amplify",
    }:
        from app.services.etf_holdings_native_qualification import (  # noqa: PLC0415
            _issuer_catalog_identity_claim,
        )

        identity_evidence = _issuer_catalog_identity_claim(
            profile,
            metadata.get("issuer_product_catalog"),
        )
    if identity_evidence is None:
        raise ETFNativeSourceEvidenceError(
            "Native qualification source body does not prove the selected fund identity"
        )

    if provider_name == "amplify" and identity_evidence is not None:
        date_field = "selected_account_rows.date"
        date_value = identity_evidence.get("source_date")
    else:
        date_field = next(
            (
                field
                for field in (
                    "composition_date",
                    "effective_business_date",
                    "effective_date",
                    "as_of_date",
                )
                if metadata.get(field) not in (None, "")
            ),
            None,
        )
        date_value = metadata.get(date_field) if date_field else None
    try:
        composition_date = _date_from_value(date_value) if date_field else None
    except (TypeError, ValueError):
        composition_date = None
    if composition_date is None:
        raise ETFNativeSourceEvidenceError(
            "Native qualification requires a provider-reported composition date"
        )
    cadence = metadata.get("expected_cadence") or infer_expected_cadence(
        source_access=metadata.get("source_access"), metadata=metadata
    )
    freshness_limit = freshness_deadline(composition_date, str(cadence or "unspecified"))
    if freshness_limit is not None and datetime.now(UTC).date() > freshness_limit:
        raise ETFNativeSourceEvidenceError(
            f"Native qualification provider-reported composition {composition_date.isoformat()} "
            f"is stale for the reviewed {cadence} cadence."
        )
    if not source_identifier:
        if not (
            provider_name == "spdr"
            and identity_evidence is not None
            and identity_evidence.get("basis") == "spdr_fund_workbook_preamble"
        ) and not (
            provider_name == "amplify"
            and identity_evidence is not None
            and identity_evidence.get("basis") == "amplify_selected_account_csv"
        ):
            raise ETFNativeSourceEvidenceError(
                "Native qualification requires its provider source identifier"
            )
    source_format = str(metadata.get("source_format") or "csv").strip()
    composition_completeness = _verified_native_composition_completeness(
        profile=profile,
        adapter=adapter,
        fetch_result=fetch_result,
    )
    parser_version = str(
        metadata.get("parser_version") or f"{adapter_key}-{source_format}-v1"
    ).strip()
    try:
        body_parse_evidence = (
            _native_holdings_response_parse_evidence(
                profile,
                adapter,
                fetch_result,
                request_binding=request_binding,
            )
            if require_body_witness
            else None
        )
    except ValueError as exc:
        raise ETFNativeSourceEvidenceError(str(exc)) from exc
    schema_fingerprint = _schema_fingerprint(
        raw_payload_text=raw_text,
        raw_payload_json=raw_json,
    )
    if not parser_version or not isinstance(schema_fingerprint, str) or not schema_fingerprint:
        raise ETFNativeSourceEvidenceError(
            "Native qualification requires raw schema and parser evidence"
        )
    evidence = {
        "provider": provider_name,
        "adapter_key": adapter_key,
        "instrument_id": instrument.id,
        "symbol": instrument.symbol.strip().upper(),
        "fund_identity": identity_evidence,
        "source_identifier": (
            None if provider_name in {"spdr", "amplify"} else source_identifier or None
        ),
        "source_identifier_basis": (
            "fund_scoped_spdr_workbook_route"
            if provider_name == "spdr"
            else "selected_account_rows"
            if provider_name == "amplify"
            else "adapter_reported"
        ),
        "source_url": source_url,
        "composition_date": composition_date.isoformat(),
        "composition_date_source_field": (
            metadata.get("composition_date_source_field") or date_field
        ),
        "composition_completeness": composition_completeness,
        "source_format": source_format,
        "parser_version": parser_version,
        "schema_fingerprint": schema_fingerprint,
        "raw_payload_hash": _hash_payload(raw_json if raw_json is not None else raw_text),
    }
    if body_parse_evidence is not None:
        evidence["holdings_response_body_witness"] = body_parse_evidence
    return evidence


def _native_initial_qualification_fetch_evidence(
    profile: ETFProfile,
    adapter: Any,
    fetch_result: Any,
    *,
    request_binding: Any | None = None,
) -> dict[str, Any]:
    """Require strict source evidence plus the sealed initial response witness."""

    return _native_adapter_fetch_evidence(
        profile,
        adapter,
        fetch_result,
        request_binding=request_binding,
        require_body_witness=True,
    )


def _native_artifact_identity_validation(
    profile: ETFProfile,
    prior_validation: dict[str, Any],
    native_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Promote only independently checked native fund evidence to identity proof."""

    instrument = profile.instrument
    identity = native_evidence.get("fund_identity")
    symbol = str(instrument.symbol or "").strip().upper() if instrument is not None else ""
    if (
        instrument is None
        or not symbol
        or not isinstance(identity, dict)
        or identity.get("basis")
        not in {
            "spdr_fund_workbook_preamble",
            "invesco_product_catalog",
            "issuer_product_catalog",
            "ishares_holdings_response",
            "amplify_selected_account_csv",
        }
        or native_evidence.get("instrument_id") != instrument.id
        or native_evidence.get("symbol") != symbol
    ):
        return prior_validation
    return {
        "status": "matched",
        "required": True,
        "matched": [{"type": "verified_native_fund_identity", "value": symbol}],
        "expected": _artifact_identity_expectations(profile),
        "artifact_identity": prior_validation.get("artifact_identity", []),
        "native_fund_identity_evidence": identity,
    }


def _native_ishares_holdings_identity(
    *, profile: ETFProfile, adapter: Any, raw_json: Any, source_url: str
) -> dict[str, Any] | None:
    """Prove iShares fund identity from the actual holdings response arrays."""

    instrument = profile.instrument
    if instrument is None or not isinstance(raw_json, dict):
        return None
    data_points_reader = getattr(adapter, "_blackrock_holdings_data_points", None)
    values_reader = getattr(adapter, "_blackrock_values", None)
    if not callable(data_points_reader) or not callable(values_reader):
        return None
    data_points = data_points_reader(raw_json)
    tickers = [str(value).strip().upper() for value in values_reader(data_points, "fundTicker")]
    names = [str(value).strip() for value in values_reader(data_points, "fundName")]
    expected_symbol = instrument.symbol.strip().upper()
    expected_name = _normalize_identity_text(str(instrument.name or ""))
    product_id_raw = raw_json.get("productId")
    product_id = str(product_id_raw).strip() if product_id_raw not in (None, "") else None
    product_name = str(raw_json.get("fundName") or "").strip()
    has_product_metadata = product_id is not None or product_name != ""
    if has_product_metadata:
        if (
            not product_id
            or not product_id.isdigit()
            or int(product_id) <= 0
            or not product_name
            or not expected_name
            or _normalize_identity_text(product_name) != expected_name
        ):
            raise ETFNativeSourceEvidenceError(
                "Native qualification raw body conflicts with the selected iShares product identity"
            )
    normalized_names = {_normalize_identity_text(value) for value in names if value}
    supplied_tickers = [ticker for ticker in tickers if ticker]
    supplied_names = [name for name in normalized_names if name]
    if any(ticker != expected_symbol for ticker in supplied_tickers) or (
        supplied_names and (not expected_name or supplied_names != [expected_name])
    ):
        raise ETFNativeSourceEvidenceError(
            "Native qualification raw body conflicts with the selected iShares fund identity"
        )
    if not source_url or not expected_symbol:
        return None
    if has_product_metadata:
        if supplied_tickers and any(ticker != expected_symbol for ticker in supplied_tickers):
            raise ETFNativeSourceEvidenceError(
                "Native qualification raw body conflicts with the selected iShares fund identity"
            )
        if supplied_names and supplied_names != [expected_name]:
            raise ETFNativeSourceEvidenceError(
                "Native qualification raw body conflicts with the selected iShares fund identity"
            )
        return {
            "basis": "ishares_holdings_product_metadata",
            "instrument_id": instrument.id,
            "symbol": expected_symbol,
            "product_id": product_id,
            "fund_name": product_name,
            "source_url": source_url,
        }
    if not supplied_names or not supplied_tickers or len(supplied_names) != 1:
        return None
    return {
        "basis": "ishares_holdings_response",
        "instrument_id": instrument.id,
        "symbol": expected_symbol,
        "fund_tickers": tickers,
        "fund_names": names,
        "source_url": source_url,
    }


def _native_fund_preamble_identity(
    profile: ETFProfile, raw_text: str | None
) -> dict[str, Any] | None:
    """Read fund-level key/value preamble fields, excluding holdings rows."""

    instrument = profile.instrument
    if instrument is None or not raw_text:
        return None
    allowed = {
        "fundticker",
        "fundsymbol",
        "etfticker",
        "etfsymbol",
        "productticker",
        "productsymbol",
        "tickersymbol",
        "fundname",
        "fundfullname",
        "etfname",
        "etffullname",
        "productname",
        "portfolioname",
    }
    found: list[dict[str, str]] = []
    for row in csv.reader(StringIO(raw_text)):
        if len(row) != 2:
            continue
        key = _identity_key(row[0])
        value = row[1].strip()
        if key not in allowed or not value:
            continue
        identity_type = "artifact_symbol" if "ticker" in key or "symbol" in key else "artifact_name"
        found.append({"type": identity_type, "value": value})
    if not found:
        return None
    expected_symbol = instrument.symbol.strip().upper()
    expected_name = _normalize_identity_text(str(instrument.name or ""))
    conflicts = [
        value
        for item in found
        for value in [item["value"]]
        if (
            item["type"] == "artifact_symbol"
            and _normalize_identity_text(value) != _normalize_identity_text(expected_symbol)
        )
        or (
            item["type"] == "artifact_name"
            and expected_name
            and _normalize_identity_text(value) != expected_name
        )
    ]
    if conflicts:
        return {"status": "mismatch", "artifact_identity": found, "conflicts": conflicts}
    return {
        "status": "matched",
        "matched": found,
        "artifact_identity": found,
    }


def _native_spdr_workbook_identity(
    *,
    profile: ETFProfile,
    adapter: Any,
    raw_text: str | None,
    source_url: str,
    request_binding: Any | None = None,
) -> dict[str, Any] | None:
    instrument = profile.instrument
    if instrument is None or not callable(getattr(adapter, "_workbook_url", None)):
        return None
    expected_url = adapter._workbook_url(instrument.symbol.strip().upper())
    identity = _native_fund_preamble_identity(profile, raw_text)
    from urllib.parse import urlparse

    expected = urlparse(expected_url)
    observed = urlparse(source_url)
    bound_urls = (
        set(request_binding.request_urls_by_log_id.values())
        if request_binding is not None
        else set()
    )
    source_is_bound_redirect = bool(
        request_binding is not None
        and expected_url in bound_urls
        and source_url in bound_urls
        and observed.scheme == "https"
        and observed.hostname == expected.hostname == "www.ssga.com"
        and observed.path.rsplit("/", 1)[-1] == expected.path.rsplit("/", 1)[-1]
        and not observed.username
        and not observed.password
        and not observed.port
        and not observed.query
        and not observed.fragment
    )
    if (
        (source_url != expected_url and not source_is_bound_redirect)
        or identity is None
        or identity.get("status") != "matched"
    ):
        return None
    symbol_rows = [
        row
        for row in identity["matched"]
        if row["type"] == "artifact_symbol"
        and _normalize_identity_text(row["value"]) == _normalize_identity_text(instrument.symbol)
    ]
    if not symbol_rows:
        return None
    return {
        "basis": "spdr_fund_workbook_preamble",
        "symbol": instrument.symbol.strip().upper(),
        "source_url": source_url,
        "requested_source_url": expected_url,
        "matched": symbol_rows,
    }


def _native_invesco_catalog_identity(
    *,
    profile: ETFProfile,
    adapter: Any,
    metadata: dict[str, Any],
    source_url: str,
    source_identifier: str,
) -> dict[str, Any] | None:
    instrument = profile.instrument
    catalog = metadata.get("issuer_product_catalog")
    if instrument is None or not isinstance(catalog, dict):
        return None
    request_url = catalog.get("request_url")
    body_base64 = catalog.get("response_body_base64")
    body_hash = catalog.get("response_sha256")
    matched = catalog.get("matched_product")
    if (
        request_url != getattr(adapter, "_PRODUCT_CATALOG_URL", None)
        or not isinstance(body_base64, str)
        or not isinstance(body_hash, str)
        or not isinstance(matched, dict)
    ):
        return None
    try:
        body = base64.b64decode(body_base64, validate=True)
        if hashlib.sha256(body).hexdigest() != body_hash:
            return None
        payload = json.loads(body)
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    docs = payload.get("response", {}).get("docs") if isinstance(payload, dict) else None
    symbol = instrument.symbol.strip().upper()
    products = (
        [
            item
            for item in docs
            if isinstance(item, dict) and str(item.get("ticker") or "").strip().upper() == symbol
        ]
        if isinstance(docs, list)
        else []
    )
    if len(products) != 1:
        return None
    product = products[0]
    cusip = str(product.get("cusip") or "").strip()
    account_name = str(product.get("accountName") or "").strip()
    if (
        not cusip
        or not account_name
        or matched.get("ticker") != symbol
        or matched.get("cusip") != cusip
        or matched.get("account_name") != account_name
        or source_identifier != cusip
        or source_url != adapter._holdings_url(cusip)
        or not isinstance(getattr(profile, "instrument_id", None), int)
    ):
        return None
    return {
        "basis": "invesco_product_catalog",
        "ticker": symbol,
        "cusip": cusip,
        "source_identifier": cusip,
        "account_name": account_name,
        "catalog_request_url": request_url,
        "catalog_response_body_base64": body_base64,
        "catalog_response_sha256": body_hash,
        "holdings_source_url": source_url,
    }


def _native_amplify_account_identity(
    *, profile: ETFProfile, adapter: Any, fetch_result: Any
) -> dict[str, Any] | None:
    instrument = profile.instrument
    metadata = fetch_result.legal_metadata if isinstance(fetch_result.legal_metadata, dict) else {}
    if instrument is None or not isinstance(fetch_result.raw_text, str):
        return None
    symbol = instrument.symbol.strip().upper()
    selected_account = str(metadata.get("selected_account") or "").strip().upper()
    if selected_account != symbol or not callable(getattr(adapter, "_parse_amplify_csv", None)):
        return None
    rows, parsed_date = adapter._parse_amplify_csv(fetch_result.raw_text, symbol=symbol)
    if not rows:
        return None
    expected_ids = [str(row.source_row_id) for row in rows]
    actual_ids = [str(row.source_row_id) for row in fetch_result.rows]
    if (
        expected_ids != actual_ids
        or any(
            str(
                next(
                    (
                        value
                        for key, value in (row.extra_data or {}).items()
                        if str(key).strip().casefold() == "account"
                    ),
                    "",
                )
                or ""
            )
            .strip()
            .upper()
            != symbol
            for row in fetch_result.rows
        )
        or metadata.get("selected_account_row_count") != len(rows)
    ):
        return None
    return {
        "basis": "amplify_selected_account_csv",
        "account": symbol,
        "row_count": len(rows),
        "source_date": parsed_date.isoformat() if parsed_date is not None else None,
        "source_url": str(fetch_result.source_url or "").strip(),
    }


async def _retain_rejected_fetch_artifact(
    db: AsyncSession,
    profile: ETFProfile,
    adapter: Any,
    request_binding: Any,
    *,
    failure: BaseException,
    fetch_result: Any | None = None,
    validation: dict[str, Any] | None = None,
    requested_date: date | None = None,
) -> ETFHoldingsRawArtifact | None:
    """Persist rejected response evidence using only committed parent rows."""

    profile_identity = inspect(profile).identity
    if not profile_identity:
        return None
    profile_id = int(profile_identity[0])
    artifact_db = AsyncSession(bind=db.bind, expire_on_commit=False)
    try:
        if await artifact_db.get(ETFProfile, profile_id) is None:
            # The request bridge rejects uncommitted profiles before transport;
            # never create an artifact against caller-owned uncommitted state.
            await artifact_db.rollback()
            return None
        artifact = await _retain_rejected_fetch_artifact_in_session(
            artifact_db,
            profile_id=profile_id,
            adapter=adapter,
            request_binding=request_binding,
            failure=failure,
            fetch_result=fetch_result,
            validation=validation,
            requested_date=requested_date,
        )
        await artifact_db.commit()
        return artifact
    except BaseException:
        await artifact_db.rollback()
        raise
    finally:
        await artifact_db.close()


async def _retain_rejected_fetch_artifact_in_session(
    db: AsyncSession,
    *,
    profile_id: int,
    adapter: Any,
    request_binding: Any,
    failure: BaseException,
    fetch_result: Any | None = None,
    validation: dict[str, Any] | None = None,
    requested_date: date | None = None,
) -> ETFHoldingsRawArtifact | None:
    """Build canonical rejected evidence in its dedicated owner session."""

    request_log_ids = list(dict.fromkeys(request_binding.request_log_ids))
    logs_by_id = {}
    if request_log_ids:
        logs = list(
            (
                await db.scalars(
                    select(ProviderRequestLog).where(ProviderRequestLog.id.in_(request_log_ids))
                )
            ).all()
        )
        logs_by_id = {row.id: row for row in logs}
    logs = [logs_by_id[log_id] for log_id in request_log_ids if log_id in logs_by_id]
    raw_text = getattr(fetch_result, "raw_text", None)
    raw_json = getattr(fetch_result, "raw_json", None)
    upstream_response_diagnostic = _vaneck_initial_response_diagnostic(failure)
    if upstream_response_diagnostic is None:
        fetch_metadata = getattr(fetch_result, "legal_metadata", None)
        if isinstance(fetch_metadata, dict):
            upstream_response_diagnostic = _vaneck_initial_response_diagnostic(
                fetch_metadata.get("upstream_response_diagnostic")
            )
    response_evidence = [
        {
            "request_log_id": row.id,
            "request_url": bounded_redact_provider_message(
                request_binding.request_urls_by_log_id.get(row.id, ""), max_length=2000
            )
            or None,
            "success": row.success,
            "error_type": row.error_type,
            "error_message": bounded_redact_provider_message(row.error_message, max_length=1000)
            if row.error_message
            else None,
            "response_headers": row.response_headers,
            "response_payloads": row.response_payloads,
        }
        for row in logs
    ]
    if raw_text is None and raw_json is None:
        last_response_payloads = next(
            (row.response_payloads for row in reversed(logs) if row.response_payloads), None
        )
        last_response = last_response_payloads[-1] if last_response_payloads else None
        if isinstance(last_response, str):
            raw_text = last_response
        elif isinstance(last_response, dict | list):
            raw_json = last_response
    content_payload = raw_json if raw_json is not None else raw_text
    if upstream_response_diagnostic is not None and content_payload in (None, ""):
        # Keep status/body facts attributed to the adapter's actual response and
        # make this attempt's diagnostic content-addressed without changing an
        # older identical empty-body artifact's metadata.
        content_payload = {
            "failure_type": type(failure).__name__,
            "failure_message": bounded_redact_provider_message(failure, max_length=1000),
            "validation": validation,
            "upstream_response_diagnostic": upstream_response_diagnostic,
            "request_log_id": request_log_ids[-1] if request_log_ids else None,
        }
        raw_text = None
        raw_json = content_payload
    if content_payload is None:
        # When no response body exists (for example a connect timeout), retain
        # a compact diagnostic as an explicit JSON evidence payload. Attempt
        # lineage remains separate and does not affect response-body hashes.
        content_payload = {
            "failure_type": type(failure).__name__,
            "failure_message": bounded_redact_provider_message(failure, max_length=1000),
            "validation": validation,
        }
        raw_json = content_payload
    content_hash = _hash_payload(content_payload)
    source_kind = "issuer_adapter_rejected_fetch"
    existing = await db.scalar(
        select(ETFHoldingsRawArtifact).where(
            ETFHoldingsRawArtifact.etf_profile_id == profile_id,
            ETFHoldingsRawArtifact.source_kind == source_kind,
            ETFHoldingsRawArtifact.content_hash == content_hash,
        )
    )
    current_attempt_evidence = {
        "provider_request_log_ids": request_log_ids,
        "request_urls": [
            bounded_redact_provider_message(
                request_binding.request_urls_by_log_id.get(log_id, ""), max_length=2000
            )
            for log_id in request_log_ids
        ],
        "request_attempts": response_evidence,
        "upstream_response_diagnostics": (
            [
                {
                    "request_log_id": request_log_ids[-1] if request_log_ids else None,
                    **upstream_response_diagnostic,
                }
            ]
            if upstream_response_diagnostic is not None
            else []
        ),
    }
    if existing is not None:
        # Keep the content-addressed payload/provenance stable, but do not lose
        # the distinct Provider attempts that returned identical rejected bytes.
        metadata = dict(existing.legal_metadata or {})
        prior_ids = list(metadata.get("provider_request_log_ids") or [])
        prior_urls = list(metadata.get("request_urls") or [])
        prior_attempts = list(metadata.get("request_attempts") or [])
        urls_by_id = dict(zip(prior_ids, prior_urls, strict=False))
        attempts_by_id = {
            item.get("request_log_id"): item
            for item in prior_attempts
            if isinstance(item, dict) and item.get("request_log_id") is not None
        }
        for log_id, url in zip(
            current_attempt_evidence["provider_request_log_ids"],
            current_attempt_evidence["request_urls"],
            strict=False,
        ):
            urls_by_id.setdefault(log_id, url)
        attempts_by_id.update(
            {
                item["request_log_id"]: item
                for item in current_attempt_evidence["request_attempts"]
                if item.get("request_log_id") is not None
            }
        )
        prior_diagnostics = list(metadata.get("upstream_response_diagnostics") or [])
        diagnostics_by_id = {
            item.get("request_log_id"): item
            for item in prior_diagnostics
            if isinstance(item, dict) and item.get("request_log_id") is not None
        }
        diagnostics_by_id.update(
            {
                item["request_log_id"]: item
                for item in current_attempt_evidence["upstream_response_diagnostics"]
                if item.get("request_log_id") is not None
            }
        )
        merged_ids = list(dict.fromkeys([*prior_ids, *request_log_ids]))
        metadata.update(
            {
                "provider_request_log_ids": merged_ids,
                "request_urls": [urls_by_id.get(log_id) for log_id in merged_ids],
                "request_attempts": [
                    attempts_by_id[log_id] for log_id in merged_ids if log_id in attempts_by_id
                ],
                "upstream_response_diagnostics": [
                    diagnostics_by_id[log_id]
                    for log_id in merged_ids
                    if log_id in diagnostics_by_id
                ],
            }
        )
        if requested_date is not None:
            requested_dates = list(metadata.get("rejected_requested_dates") or [])
            metadata["rejected_requested_dates"] = list(
                dict.fromkeys([*requested_dates, requested_date.isoformat()])
            )
        existing.legal_metadata = metadata
        await db.flush()
        return existing
    provider_name = str(getattr(adapter, "source_provider", "")).strip().lower()
    source = await db.scalar(select(DataSource).where(DataSource.name == provider_name))
    first_log = logs[0] if logs else None
    artifact = ETFHoldingsRawArtifact(
        etf_profile_id=profile_id,
        data_source_id=source.id if source is not None else None,
        source_kind=source_kind,
        source_url=bounded_redact_provider_message(
            getattr(fetch_result, "source_url", None)
            or (
                request_binding.request_urls_by_log_id.get(request_log_ids[-1])
                if request_log_ids
                else ""
            ),
            max_length=2000,
        ),
        source_identifier=getattr(fetch_result, "source_identifier", None),
        content_type=("text/plain" if raw_text is not None else "application/json"),
        content_hash=content_hash,
        composition_date=None,
        as_of_date=None,
        published_at=None,
        fetched_at=(
            first_log.completed_at if first_log and first_log.completed_at else datetime.now(UTC)
        ),
        parser_version=str(getattr(adapter, "adapter_key", "unknown"))[:40],
        payload_text=raw_text,
        payload_json=raw_json,
        legal_metadata={
            **current_attempt_evidence,
            "failure_type": type(failure).__name__,
            "failure_message": bounded_redact_provider_message(failure, max_length=1000),
            "validation": validation,
            "request_attempts": response_evidence,
            "evidence_source": "shared_provider_request_log_and_refresh_rejection",
            **(
                {"rejected_requested_dates": [requested_date.isoformat()]}
                if requested_date is not None
                else {}
            ),
        },
    )
    db.add(artifact)
    await db.flush()
    return artifact


def _vaneck_initial_response_diagnostic(value: object) -> dict[str, Any] | None:
    """Accept only the adapter's bounded, allowlisted initial-response metadata."""

    if isinstance(value, BaseException):
        value = getattr(value, "vaneck_initial_response_diagnostic", None)
    if not isinstance(value, dict) or set(value) != {
        "upstream_http_status",
        "response_body_bytes",
        "response_body_sha256",
        "allowlisted_response_headers",
    }:
        return None
    status = value.get("upstream_http_status")
    body_bytes = value.get("response_body_bytes")
    digest = value.get("response_body_sha256")
    headers = value.get("allowlisted_response_headers")
    if (
        isinstance(status, bool)
        or not isinstance(status, int)
        or not 100 <= status <= 599
        or isinstance(body_bytes, bool)
        or not isinstance(body_bytes, int)
        or body_bytes < 0
        or not isinstance(digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
        or not isinstance(headers, dict)
        or set(headers) - {"content-type", "content-length"}
    ):
        return None
    normalized_headers = {}
    for key, header_value in headers.items():
        if (
            not isinstance(header_value, str)
            or len(header_value) > 160
            or any(ord(character) < 32 for character in header_value)
        ):
            return None
        normalized_headers[key] = header_value
    return {
        "upstream_http_status": status,
        "response_body_bytes": body_bytes,
        "response_body_sha256": digest,
        "allowlisted_response_headers": normalized_headers,
    }


async def _record_skip(
    db: AsyncSession,
    profile: ETFProfile,
    status: str,
    failure_reason: str | None = None,
) -> None:
    adapter_key = profile.adapter_key or "unresolved"
    state = (
        await db.execute(
            select(ETFHoldingsAdapterState).where(
                ETFHoldingsAdapterState.etf_profile_id == profile.id,
                ETFHoldingsAdapterState.adapter_key == adapter_key,
            )
        )
    ).scalar_one_or_none()
    if state is None:
        state = ETFHoldingsAdapterState(etf_profile_id=profile.id, adapter_key=adapter_key)
        db.add(state)
    state.status = status
    state.failure_reason = failure_reason or "No concrete free issuer adapter route is configured."
    now = datetime.now(UTC)
    state.last_checked_at = now
    state.last_failure_at = now
    state_metadata = _state_metadata(state.extra_data)
    state.extra_data = {
        **state_metadata,
        "consecutive_failures": _failure_streak(state_metadata) + 1,
        "last_error_class": "RouteNotReady",
        "last_failure_class": "route_not_ready",
    }


async def _record_probe(
    db: AsyncSession,
    profile: ETFProfile,
    probe: HoldingsAdapterProbe,
) -> None:
    state = (
        await db.execute(
            select(ETFHoldingsAdapterState).where(
                ETFHoldingsAdapterState.etf_profile_id == profile.id,
                ETFHoldingsAdapterState.adapter_key == probe.adapter_key,
            )
        )
    ).scalar_one_or_none()
    if state is None:
        state = ETFHoldingsAdapterState(
            etf_profile_id=profile.id,
            adapter_key=probe.adapter_key,
        )
        db.add(state)
    state.status = probe.status
    state.failure_reason = None if probe.status == "ready" else probe.reason
    state.source_url = probe.source_url
    state.source_identifier = probe.issuer_product_id
    state.last_checked_at = datetime.now(UTC)
    state_metadata = _state_metadata(state.extra_data)
    state.extra_data = {
        **state_metadata,
        "probe_confidence": str(probe.confidence),
        "required_identifiers": probe.required_identifiers,
        "consecutive_failures": 0
        if probe.status == "ready"
        else _failure_streak(state_metadata) + 1,
        "last_failure_class": None if probe.status == "ready" else "route_not_ready",
    }


async def _record_success(db: AsyncSession, profile: ETFProfile, snapshot=None) -> None:
    adapter_key = profile.adapter_key or "unresolved"
    state = (
        await db.execute(
            select(ETFHoldingsAdapterState).where(
                ETFHoldingsAdapterState.etf_profile_id == profile.id,
                ETFHoldingsAdapterState.adapter_key == adapter_key,
            )
        )
    ).scalar_one_or_none()
    if state is None:
        state = ETFHoldingsAdapterState(etf_profile_id=profile.id, adapter_key=adapter_key)
        db.add(state)
    now = datetime.now(UTC)
    profile.adapter_status = "success"
    state.status = "success"
    state.failure_reason = None
    state.rate_limit_state = None
    state.last_success_at = now
    state.last_checked_at = now
    observation_metadata = _state_metadata(snapshot.extra_data if snapshot is not None else None)
    state_metadata = _state_metadata(state.extra_data)
    state.extra_data = {
        **state_metadata,
        **{
            key: observation_metadata.get(key)
            for key in (
                "source_tier",
                "source_provider",
                "transport_kind",
                "expected_cadence",
                "schema_fingerprint",
            )
            if observation_metadata.get(key) is not None
        },
        "consecutive_failures": 0,
        "last_failure_class": None,
        "last_canary_failure_class": None,
    }
    state.extra_data.pop("last_schema_drift", None)
    if snapshot is not None and snapshot.source_provider:
        state.extra_data["source_provider"] = snapshot.source_provider
    if snapshot is not None:
        state.source_url = snapshot.source_url
        state.source_identifier = snapshot.source_identifier
        state.parser_version = snapshot.parser_version
        state.row_count = snapshot.row_count
        state.resolved_count = snapshot.resolved_count
        state.unresolved_count = snapshot.unresolved_count
        state.composition_date = snapshot.composition_date
        state.published_at = snapshot.published_at
        state.completeness_status = snapshot.completeness_status


def _rate_limit_state_for_failure(exc: Exception | str) -> str | None:
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        if status_code == 429:
            return "http_429"
        if status_code == 403:
            return "http_403"
        if status_code in {408, 425} or 500 <= status_code <= 599:
            return f"http_{status_code}"
    return None


async def _record_failure(db: AsyncSession, profile: ETFProfile, failure: Exception | str) -> None:
    adapter_key = profile.adapter_key or "unresolved"
    state = (
        await db.execute(
            select(ETFHoldingsAdapterState).where(
                ETFHoldingsAdapterState.etf_profile_id == profile.id,
                ETFHoldingsAdapterState.adapter_key == adapter_key,
            )
        )
    ).scalar_one_or_none()
    if state is None:
        state = ETFHoldingsAdapterState(etf_profile_id=profile.id, adapter_key=adapter_key)
        db.add(state)
    state.status = "failure"
    state.failure_reason = str(failure)
    state.rate_limit_state = _rate_limit_state_for_failure(failure)
    state.last_failure_at = datetime.now(UTC)
    state.last_checked_at = state.last_failure_at
    state_metadata = _state_metadata(state.extra_data)
    failure_class = _canary_failure_class(failure)
    state.extra_data = {
        **state_metadata,
        "consecutive_failures": _failure_streak(state_metadata) + 1,
        "last_error_class": type(failure).__name__ if isinstance(failure, Exception) else "Error",
        "last_failure_class": failure_class,
    }
    if isinstance(failure, ETFHoldingsSchemaDriftError):
        state.extra_data["last_schema_drift"] = {
            "previous_fingerprint": failure.previous_fingerprint,
            "observed_fingerprint": failure.observed_fingerprint,
            "parser_version": failure.parser_version,
            "observed_at": state.last_failure_at.isoformat(),
        }
