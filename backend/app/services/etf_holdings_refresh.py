from __future__ import annotations

import csv
import zipfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from io import BytesIO, StringIO
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.etf_holdings import (
    ETFHolding,
    ETFHoldingsAdapterState,
    ETFHoldingsSnapshot,
    ETFProfile,
)
from app.models.instrument import Instrument
from app.providers.base import IdentifierRecord
from app.services.etf_holdings import (
    ETF_HOLDINGS_INTERNAL_PROVIDER,
    ensure_etf_profile,
    ensure_lightweight_etf_instrument,
    get_etf_profile_for_instrument,
    get_latest_snapshot,
    ingest_holdings_snapshot,
    reconcile_snapshot_constituents,
)
from app.services.etf_holdings_adapters import (
    HoldingsAdapterProbe,
    get_holdings_adapter,
    infer_adapter_key,
    known_etf_route_metadata,
    parse_etf_discovery_csv,
    parse_etf_discovery_table,
    parse_xlsx_table,
)
from app.services.instrument_mastering import register_identifier
from app.services.top_down_taxonomy import BENCHMARK_FAMILY_REGISTRY


class ETFHoldingsRouteNotReadyError(ValueError):
    """Raised when an ETF matched an adapter but lacks route metadata."""


@dataclass(slots=True)
class ETFHoldingsBootstrapResult:
    profile: ETFProfile
    probe: HoldingsAdapterProbe
    refresh_attempted: bool
    refresh_succeeded: bool
    message: str | None = None


SEC_FUND_TICKERS_URL = "https://www.sec.gov/files/company_tickers_mf.json"


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
        include_holdings=False,
        include_controlled_fixture=False,
    )
    if latest is not None:
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
            include_holdings=False,
            include_controlled_fixture=False,
        )
        if latest is not None:
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
    if latest_snapshot is not None:
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
        composition_date = _date_from_value(result_metadata.get("composition_date"))
        if composition_date is None:
            composition_date = requested_date
        if composition_date > requested_date:
            raise ValueError(
                "Issuer dated holdings route returned a composition date after the requested "
                f"date ({composition_date.isoformat()} > {requested_date.isoformat()})."
            )
        snapshot = await ingest_holdings_snapshot(
            db,
            etf_instrument=profile.instrument,
            rows=fetch_result.rows,
            composition_date=composition_date,
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
            # Issuer artifacts already carry their canonical symbol/identifier
            # evidence.  Do not fan out synchronously to optional metadata
            # providers for every row; unresolved rows remain explicit and can
            # be reconciled by a bounded background job later.
            allow_provider_enrichment=False,
        )
    except Exception as exc:
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

    supported_roles = ("cap_weight", "equal_weight", "value", "growth")
    requested_roles = roles or list(supported_roles)
    normalized_roles: list[str] = []
    for role in requested_roles:
        normalized_role = str(role).strip().lower()
        if normalized_role not in supported_roles:
            raise ValueError(
                f"Unsupported benchmark family role {role!r}; expected one of "
                f"{', '.join(supported_roles)}."
            )
        if normalized_role not in normalized_roles:
            normalized_roles.append(normalized_role)

    legs: list[dict[str, Any]] = []
    refreshed = unavailable = failed = 0
    for role in normalized_roles:
        mapping = family.get(role) if isinstance(family.get(role), dict) else None
        symbol = str(mapping.get("symbol")).strip().upper() if mapping and mapping.get("symbol") else None
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
        "roles": normalized_roles,
        "refreshed": refreshed,
        "unavailable": unavailable,
        "failed": failed,
        "legs": legs,
    }


def _aliases(profile: ETFProfile) -> dict[str, Any]:
    aliases = profile.provider_aliases or {}
    return aliases if isinstance(aliases, dict) else {}


def _apply_known_route_metadata(profile: ETFProfile) -> bool:
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

    route_metadata = known_etf_route_metadata(symbol)
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
        if explicit_adapter and get_holdings_adapter(explicit_adapter) is not None:
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
) -> dict[str, Any]:
    expectations = _artifact_identity_expectations(profile)
    extracted = _extract_artifact_identities(raw_text)
    required = bool(expectations) or _bool_alias(
        _aliases(profile), "require_artifact_identity_match"
    )
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


async def _refresh_adapter_route(db: AsyncSession, profile: ETFProfile):
    aliases = _aliases(profile)
    if profile.instrument is None:
        raise ValueError("ETF profile is missing its linked instrument.")

    adapter = get_holdings_adapter(profile.adapter_key)
    if adapter is None:
        raise ValueError(f"No ETF holdings adapter is registered for {profile.adapter_key}.")

    symbol = profile.instrument.symbol
    identifiers = _string_aliases(profile)
    issuer_product_id = _issuer_product_identifier(identifiers)
    probe = adapter.probe(symbol=symbol, name=profile.instrument.name, identifiers=identifiers)
    if probe.status != "ready":
        required = ", ".join(probe.required_identifiers) or "provider-specific route"
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
    composition_date = (
        _alias_date(aliases, "holdings_composition_date")
        or _date_from_value(result_metadata.get("composition_date"))
        or datetime.now(UTC).date()
    )
    as_of_date = _alias_date(aliases, "holdings_as_of_date") or _date_from_value(
        result_metadata.get("as_of_date")
    )

    snapshot = await ingest_holdings_snapshot(
        db,
        etf_instrument=profile.instrument,
        rows=fetch_result.rows,
        composition_date=composition_date,
        as_of_date=as_of_date,
        known_at=datetime.now(UTC),
        provenance=str(
            result_metadata.get("snapshot_provenance") or "issuer_self_snapshotted_holdings"
        ),
        source_provider=str(source_provider),
        source_url=fetch_result.source_url,
        source_identifier=fetch_result.source_identifier or issuer_product_id,
        source_quality=str(result_metadata.get("source_quality") or "self_snapshotted_holdings"),
        completeness_status=str(
            result_metadata.get("completeness_status")
            or aliases.get("holdings_completeness_status")
            or "unknown"
        ),
        parser_version=str(
            result_metadata.get("parser_version") or f"{adapter.adapter_key}-{source_format}-v1"
        ),
        raw_payload_text=fetch_result.raw_text,
        raw_payload_json=fetch_result.raw_json,
        legal_metadata={
            **(fetch_result.legal_metadata or {}),
            "terms_note": aliases.get("terms_note"),
            "probe_status": probe.status,
            "probe_confidence": str(probe.confidence),
            "artifact_identity_validation": artifact_identity_validation,
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
    profile.adapter_status = "success"
    profile.adapter_confidence = probe.confidence
    return snapshot


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
