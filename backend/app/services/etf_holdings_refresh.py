from __future__ import annotations

import csv
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from io import BytesIO, StringIO
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.etf_holdings import ETFHoldingsAdapterState, ETFProfile
from app.providers.base import IdentifierRecord
from app.services.etf_holdings import (
    ETF_HOLDINGS_INTERNAL_PROVIDER,
    ensure_etf_profile,
    ensure_lightweight_etf_instrument,
    get_etf_profile_for_instrument,
    ingest_holdings_snapshot,
)
from app.services.etf_holdings_adapters import (
    HoldingsAdapterProbe,
    get_holdings_adapter,
    parse_etf_discovery_csv,
    parse_etf_discovery_table,
    parse_xlsx_table,
)
from app.services.instrument_mastering import register_identifier


class ETFHoldingsRouteNotReadyError(ValueError):
    """Raised when an ETF matched an adapter but lacks route metadata."""


SEC_FUND_TICKERS_URL = "https://www.sec.gov/files/company_tickers_mf.json"


def _parse_discovery_response(source_url: str, response) -> list:
    raw_content = getattr(response, "content", None)
    content_type = ""
    headers = getattr(response, "headers", None)
    if headers is not None:
        content_type = str(headers.get("content-type", "")).lower()
    source_format = "zip" if (
        source_url.lower().endswith(".zip") or "zip" in content_type
    ) else "xlsx" if (
        source_url.lower().endswith((".xlsx", ".xlsm"))
        or "spreadsheetml" in content_type
        or "excel" in content_type
        or (isinstance(raw_content, bytes) and raw_content.startswith(b"PK"))
    ) else "csv"

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
            await _register_optional_identifier(db, instrument, identifier_type, value, adapter.source_provider)
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
        existing_legal_metadata = (existing_profile.legal_metadata or {}) if existing_profile else {}
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


async def refresh_all_known_etf_holdings(db: AsyncSession) -> dict:
    """Refresh ETF holdings for profiles whose free-source route is configured."""

    profiles = (
        await db.execute(select(ETFProfile).options(selectinload(ETFProfile.instrument)))
    ).scalars().all()
    unresolved = 0
    skipped = 0
    refreshed = 0
    failed = 0
    for profile in profiles:
        aliases = _aliases(profile)
        holdings_url = _first_alias(
            aliases,
            "holdings_url",
            "issuer_holdings_url",
            "holdings_csv_url",
            "latest_holdings_url",
        )
        if holdings_url:
            try:
                await _refresh_configured_csv_url(db, profile, holdings_url=holdings_url)
            except Exception as exc:  # noqa: BLE001 - persisted adapter health should capture any failure.
                failed += 1
                await _record_failure(db, profile, exc)
            else:
                refreshed += 1
                await _record_success(db, profile)
            continue
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


async def probe_etf_holdings_adapter_route(
    db: AsyncSession,
    profile: ETFProfile,
) -> HoldingsAdapterProbe:
    """Inspect and persist whether an ETF profile has a refreshable holdings route."""

    if profile.instrument is None:
        raise ValueError("ETF profile is missing its linked instrument.")

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
        raise ValueError(f"No ETF holdings adapter is registered for {profile.adapter_key}.")

    aliases = _aliases(profile)
    identifiers = _string_aliases(profile)
    symbol = profile.instrument.symbol
    issuer_product_id = _first_alias(
        identifiers,
        "issuer_product_id",
        "fund_id",
        "product_id",
        "sec_series_id",
    )
    try:
        fetch_result = await adapter.fetch_for_date(
            symbol=symbol,
            requested_date=requested_date,
            issuer_product_id=issuer_product_id,
            identifiers=identifiers,
        )
        if not fetch_result.rows:
            raise ValueError("Issuer dated holdings route returned no parseable rows.")
        artifact_identity_validation = _validate_artifact_identity(profile, fetch_result.raw_text)
        _ensure_artifact_identity_is_safe(artifact_identity_validation)

        result_metadata = fetch_result.legal_metadata or {}
        source_format = str(result_metadata.get("source_format") or "csv")
        source_provider = (
            _first_alias(aliases, "holdings_source_provider", "source_provider")
            or result_metadata.get("source_provider")
            or adapter.source_provider
        )
        snapshot = await ingest_holdings_snapshot(
            db,
            etf_instrument=profile.instrument,
            rows=fetch_result.rows,
            composition_date=requested_date,
            as_of_date=requested_date,
            known_at=datetime.now(UTC),
            provenance="issuer_self_snapshotted_holdings",
            source_provider=str(source_provider),
            source_url=fetch_result.source_url,
            source_identifier=fetch_result.source_identifier or issuer_product_id,
            source_quality="self_snapshotted_holdings",
            completeness_status=str(aliases.get("holdings_completeness_status") or "unknown"),
            parser_version=f"{adapter.adapter_key}-{source_format}-v1",
            raw_payload_text=fetch_result.raw_text,
            raw_payload_json=fetch_result.raw_json,
            legal_metadata={
                **result_metadata,
                "terms_note": aliases.get("terms_note"),
                "artifact_identity_validation": artifact_identity_validation,
            },
            notes="Fetched through the ETF profile's dated issuer holdings adapter route.",
        )
    except Exception as exc:
        await _record_failure(db, profile, exc)
        await db.flush()
        raise

    await _record_success(db, profile, snapshot=snapshot)
    await db.flush()
    return snapshot


def _aliases(profile: ETFProfile) -> dict[str, Any]:
    aliases = profile.provider_aliases or {}
    return aliases if isinstance(aliases, dict) else {}


def _first_alias(aliases: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = aliases.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


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
    value = aliases.get(key)
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        return date.fromisoformat(value.strip())
    return None


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
    if profile.instrument.name and _normalize_identity_text(profile.instrument.name) != _normalize_identity_text(
        profile.instrument.symbol
    ):
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
        item for item in extracted if item["type"] in {"artifact_symbol", "artifact_cusip", "artifact_isin"}
    ]
    name_identities = [item for item in extracted if item["type"] == "artifact_name"]
    if symbol_expectation is not None and symbol_identities:
        matched = [
            item for item in symbol_identities if _identity_matches(item["value"], symbol_expectation["value"])
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
            item for item in name_identities if _identity_matches(item["value"], name_expectation["value"])
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
) -> dict[str, Any]:
    expectations = _artifact_identity_expectations(profile)
    extracted = _extract_artifact_identities(raw_text)
    required = bool(expectations) or _bool_alias(_aliases(profile), "require_artifact_identity_match")
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


def _ensure_artifact_identity_is_safe(validation: dict[str, Any]) -> None:
    if validation["status"] in {"mismatch", "missing_raw_artifact"}:
        expected = ", ".join(
            f"{item['type']}={item['value']}" for item in validation.get("expected", [])
        )
        raise ValueError(
            "Fetched holdings artifact failed ETF identity validation"
            + (f" ({expected})." if expected else ".")
        )


async def _refresh_configured_csv_url(
    db: AsyncSession,
    profile: ETFProfile,
    *,
    holdings_url: str,
) -> None:
    aliases = _aliases(profile)
    source_provider = (
        _first_alias(aliases, "holdings_source_provider", "source_provider")
        or profile.adapter_key
        or profile.issuer
        or "issuer_csv"
    )
    composition_date = _alias_date(aliases, "holdings_composition_date") or datetime.now(
        UTC
    ).date()
    as_of_date = _alias_date(aliases, "holdings_as_of_date")

    adapter = get_holdings_adapter(profile.adapter_key) or get_holdings_adapter("configured_csv_url")
    if adapter is None:
        raise ValueError("No ETF holdings adapter is registered for configured public CSV URLs.")
    fetch_result = await adapter.fetch_latest(
        symbol=profile.instrument.symbol if profile.instrument else "",
        issuer_product_id=_first_alias(aliases, "issuer_product_id", "fund_id", "sec_series_id"),
        source_url=holdings_url,
    )
    if not fetch_result.rows:
        raise ValueError("Configured holdings CSV returned no parseable rows.")
    if profile.instrument is None:
        raise ValueError("ETF profile is missing its linked instrument.")
    artifact_identity_validation = _validate_artifact_identity(profile, fetch_result.raw_text)
    _ensure_artifact_identity_is_safe(artifact_identity_validation)
    result_metadata = fetch_result.legal_metadata or {}
    source_format = str(result_metadata.get("source_format") or "csv")

    await ingest_holdings_snapshot(
        db,
        etf_instrument=profile.instrument,
        rows=fetch_result.rows,
        composition_date=composition_date,
        as_of_date=as_of_date,
        known_at=datetime.now(UTC),
        provenance="issuer_self_snapshotted_holdings",
        source_provider=str(source_provider),
        source_url=fetch_result.source_url or holdings_url,
        source_identifier=fetch_result.source_identifier,
        source_quality="self_snapshotted_holdings",
        completeness_status=str(aliases.get("holdings_completeness_status") or "unknown"),
        parser_version=f"{adapter.adapter_key}-{source_format}-v1",
        raw_payload_text=fetch_result.raw_text,
        raw_payload_json=fetch_result.raw_json,
        legal_metadata={
            **result_metadata,
            "terms_note": aliases.get("terms_note"),
            "artifact_identity_validation": artifact_identity_validation,
        },
        notes="Fetched from the ETF profile's configured public holdings URL.",
    )


async def _refresh_adapter_route(db: AsyncSession, profile: ETFProfile):
    aliases = _aliases(profile)
    if profile.instrument is None:
        raise ValueError("ETF profile is missing its linked instrument.")

    adapter = get_holdings_adapter(profile.adapter_key)
    if adapter is None:
        raise ValueError(f"No ETF holdings adapter is registered for {profile.adapter_key}.")

    symbol = profile.instrument.symbol
    identifiers = _string_aliases(profile)
    issuer_product_id = _first_alias(
        identifiers,
        "issuer_product_id",
        "fund_id",
        "product_id",
        "sec_series_id",
    )
    probe = adapter.probe(symbol=symbol, name=profile.instrument.name, identifiers=identifiers)
    if probe.status != "ready":
        required = ", ".join(probe.required_identifiers) or "holdings_url"
        raise ETFHoldingsRouteNotReadyError(
            f"{probe.reason or probe.status} Required route metadata: {required}."
        )

    fetch_result = await adapter.fetch_latest(
        symbol=symbol,
        issuer_product_id=issuer_product_id,
        identifiers=identifiers,
    )
    if not fetch_result.rows:
        raise ValueError("Issuer holdings route returned no parseable rows.")
    artifact_identity_validation = _validate_artifact_identity(profile, fetch_result.raw_text)
    _ensure_artifact_identity_is_safe(artifact_identity_validation)

    result_metadata = fetch_result.legal_metadata or {}
    source_format = str(result_metadata.get("source_format") or "csv")
    source_provider = (
        _first_alias(aliases, "holdings_source_provider", "source_provider")
        or result_metadata.get("source_provider")
        or adapter.source_provider
    )
    composition_date = _alias_date(aliases, "holdings_composition_date") or datetime.now(
        UTC
    ).date()
    as_of_date = _alias_date(aliases, "holdings_as_of_date")

    return await ingest_holdings_snapshot(
        db,
        etf_instrument=profile.instrument,
        rows=fetch_result.rows,
        composition_date=composition_date,
        as_of_date=as_of_date,
        known_at=datetime.now(UTC),
        provenance="issuer_self_snapshotted_holdings",
        source_provider=str(source_provider),
        source_url=fetch_result.source_url,
        source_identifier=fetch_result.source_identifier or issuer_product_id,
        source_quality="self_snapshotted_holdings",
        completeness_status=str(aliases.get("holdings_completeness_status") or "unknown"),
        parser_version=f"{adapter.adapter_key}-{source_format}-v1",
        raw_payload_text=fetch_result.raw_text,
        raw_payload_json=fetch_result.raw_json,
        legal_metadata={
            **(fetch_result.legal_metadata or {}),
            "terms_note": aliases.get("terms_note"),
            "probe_status": probe.status,
            "probe_confidence": str(probe.confidence),
            "artifact_identity_validation": artifact_identity_validation,
        },
        notes="Fetched through the ETF profile's issuer holdings adapter route.",
    )


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
    state.last_checked_at = datetime.now(UTC)


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
    state.extra_data = {
        **(state.extra_data or {}),
        "probe_confidence": str(probe.confidence),
        "required_identifiers": probe.required_identifiers,
    }


async def _record_success(db: AsyncSession, profile: ETFProfile, snapshot=None) -> None:
    adapter_key = profile.adapter_key or "configured_csv_url"
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
    state.status = "success"
    state.failure_reason = None
    state.rate_limit_state = None
    state.last_success_at = now
    state.last_checked_at = now
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
    adapter_key = profile.adapter_key or "configured_csv_url"
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
