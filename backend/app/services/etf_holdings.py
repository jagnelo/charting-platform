from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.etf_holdings import (
    ETFHolding,
    ETFHoldingsAdapterState,
    ETFHoldingsRawArtifact,
    ETFHoldingsSnapshot,
    ETFProfile,
)
from app.models.instrument import EquityDetail, Instrument
from app.models.instrument_identity import InstrumentIdentifier, InstrumentIdentifierType
from app.providers import (
    ensure_data_source,
    get_default_metadata_provider,
    get_identifier_providers,
)
from app.providers.base import IdentifierRecord, InstrumentProfile, ListingRecord
from app.schemas.etf_holdings import (
    ETFConstituentTimelinePoint,
    ETFHoldingIngestRow,
    ETFHoldingOut,
    ETFHoldingsCoverageRow,
    ETFHoldingsCoverageSummary,
    ETFHoldingsDateOut,
    ETFHoldingsDiffOut,
    ETFHoldingsDiffRowOut,
    ETFHoldingsDiffSummaryOut,
    ETFHoldingsOverlapConstituentOut,
    ETFHoldingsOverlapMatrixCellOut,
    ETFHoldingsOverlapMatrixOut,
    ETFHoldingsOverlapMatrixRowOut,
    ETFHoldingsOverlapPairOut,
    ETFHoldingsOverlapSummaryOut,
    ETFHoldingsPageOut,
    ETFHoldingsSnapshotOut,
    ETFHoldingsTransitionOut,
    ETFHoldingsTransitionTimelineOut,
    ETFHoldingsWeightEvolutionOut,
    ETFHoldingsWeightEvolutionPointOut,
    ETFHoldingsWeightEvolutionSeriesOut,
    ETFProfileOut,
    ETFUnresolvedHoldingOut,
)
from app.services.etf_holdings_adapters import (
    CanonicalHoldingRow,
    get_holdings_adapter,
    infer_adapter_key,
)
from app.services.etf_holdings_capability import evaluate_capability
from app.services.instrument_mastering import (
    ingest_provider_profile,
    register_identifier,
    store_profile_snapshot,
)

ETF_HOLDINGS_INTERNAL_PROVIDER = "etf_holdings_internal"


def _now() -> datetime:
    return datetime.now(UTC)


def _visible_snapshot_conditions() -> list[Any]:
    """Limit seeded browser reads to the deterministic holdings fixture.

    The application database may retain canonical/provider snapshots from
    earlier refreshes.  During a seeded visual run those rows must not win
    latest-date selection or leak into derived lists.  Outside seeded runs the
    normal provider-neutral visibility remains unchanged.
    """
    if not settings.E2E_SEED_MARKET_DATA:
        return []
    return [
        ETFHoldingsSnapshot.provenance == "controlled_fixture",
        ETFHoldingsSnapshot.source_provider == "e2e_reference",
    ]


def _apply_snapshot_visibility(statement):
    return statement.where(*_visible_snapshot_conditions())


def _hash_payload(payload: Any) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _payload_schema_shape(value: Any) -> Any:
    """Return a value-free structural shape suitable for drift detection."""

    if isinstance(value, dict):
        return {
            "object": {str(key): _payload_schema_shape(item) for key, item in sorted(value.items())}
        }
    if isinstance(value, list):
        return {"array": _payload_schema_shape(value[0]) if value else None}
    if value is None:
        return "null"
    return type(value).__name__


def _schema_fingerprint(
    *,
    raw_payload_text: str | None = None,
    raw_payload_json: dict | None = None,
) -> str | None:
    if raw_payload_json is not None:
        return _hash_payload(_payload_schema_shape(raw_payload_json))
    if raw_payload_text:
        first_line = next(
            (line.strip() for line in raw_payload_text.splitlines() if line.strip()), ""
        )
        if not first_line:
            return None
        delimiter = next(
            (candidate for candidate in (",", "\t", "|", ";") if candidate in first_line), None
        )
        header = (
            [part.strip().lower() for part in first_line.split(delimiter)]
            if delimiter
            else [first_line.lower()]
        )
        return _hash_payload({"text_header": header})
    return None


def _capability_source_tier(
    *,
    provenance: str,
    source_provider: str,
    legal_metadata: dict[str, Any] | None = None,
) -> str:
    legal_metadata = legal_metadata or {}
    explicit = str(legal_metadata.get("source_tier") or "").strip().lower()
    if explicit in {
        "issuer_native",
        "successor_native",
        "licensed_vendor",
        "sec_filing",
        "none",
    }:
        return explicit
    text = " ".join(
        str(value or "").lower()
        for value in (
            provenance,
            source_provider,
            legal_metadata.get("route_resolution"),
            legal_metadata.get("issuer_route_fallback"),
        )
    )
    if "sec" in text or "filing" in text:
        return "sec_filing"
    if legal_metadata.get("successor_publisher") or legal_metadata.get("publisher_relationship"):
        return "successor_native"
    if any(token in text for token in ("vendor", "licensed", "aggregator")):
        return "licensed_vendor"
    if any(token in text for token in ("issuer", "native", "self_snapshotted")):
        return "issuer_native"
    return "none"


def _capability_transport_kind(*, source_url: str | None, legal_metadata: dict[str, Any]) -> str:
    source_format = str(legal_metadata.get("source_format") or "").lower()
    if source_format in {"csv", "xls", "xlsx", "pdf", "zip"}:
        return "file_export"
    if source_format in {"json", "api"}:
        return "structured_api"
    if source_format in {"html", "javascript_embedded_html_rows", "pipe_delimited_text"}:
        return "web_page"
    if str(source_url or "").lower().startswith(("http://", "https://")):
        return "structured_or_page"
    return "stored_artifact"


def _date_start(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=UTC)


def _date_end(value: date) -> datetime:
    return datetime.combine(value, time.max, tzinfo=UTC)


def _normalize_symbol(symbol: str | None) -> str | None:
    if not symbol:
        return None
    normalized = symbol.strip().upper()
    return normalized or None


def _normalize_currency_code(value: str | None) -> str | None:
    text = str(value or "").strip().upper()
    return text if len(text) == 3 and text.isalpha() else None


def _normalize_holding_identifier_value(value: str | None) -> str | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    if text in {"N/A", "NA", "NONE", "NULL", "UNKNOWN", "-", "—", "--"}:
        return None
    return text


def _normalize_holding_currency(value: str | None) -> str | None:
    code = _normalize_currency_code(value)
    if code:
        return code
    text = str(value or "").strip().lower()
    if not text:
        return None
    aliases = {
        "united states dollar": "USD",
        "us dollar": "USD",
        "canada dollar": "CAD",
        "canadian dollar": "CAD",
        "euro": "EUR",
        "british pound": "GBP",
        "japanese yen": "JPY",
        "swiss franc": "CHF",
        "australian dollar": "AUD",
        "hong kong dollar": "HKD",
    }
    return aliases.get(text)


def _is_placeholder_symbol(symbol: str | None) -> bool:
    normalized = _normalize_symbol(symbol)
    return bool(normalized and normalized.startswith("HOLDING-"))


def _identifier_type(name: str) -> InstrumentIdentifierType | None:
    try:
        return InstrumentIdentifierType[name.upper()]
    except KeyError:
        return None


def _normalized_name_tokens(value: str | None) -> set[str]:
    if not value:
        return set()
    noise = {
        "inc",
        "incorporated",
        "corp",
        "corporation",
        "co",
        "company",
        "ltd",
        "limited",
        "plc",
        "sa",
        "ag",
        "nv",
        "spa",
        "se",
        "holdings",
        "holding",
        "group",
        "class",
        "common",
        "stock",
        "ordinary",
        "ord",
        "sponsored",
        "adr",
        "the",
        "pt",
        "tbk",
        "persero",
        "berhad",
        "spolka",
        "akcyjna",
    }
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in value)
    return {token for token in cleaned.split() if token and token not in noise}


def _names_look_compatible(reported_name: str | None, provider_name: str | None) -> bool:
    if not reported_name or not provider_name:
        return True
    left = _normalized_name_tokens(reported_name)
    right = _normalized_name_tokens(provider_name)
    if not left or not right:
        return True
    overlap = left & right
    if overlap:
        left_ratio = len(overlap) / len(left)
        right_ratio = len(overlap) / len(right)
        if len(overlap) >= 2 and (left_ratio >= 0.5 or right_ratio >= 0.5):
            return True
        if len(overlap) == 1 and (left_ratio >= 0.75 or right_ratio >= 0.75):
            return True
    left_text = "".join(sorted(left))
    right_text = "".join(sorted(right))
    return left_text in right_text or right_text in left_text


async def _find_instrument_for_identifier_records(
    db: AsyncSession,
    identifiers: list[IdentifierRecord],
) -> Instrument | None:
    priority = {
        "COMPOSITE_FIGI": 0,
        "FIGI": 1,
        "ISIN": 2,
        "CUSIP": 3,
        "SEDOL": 4,
    }
    ordered = sorted(
        identifiers,
        key=lambda record: priority.get(record.identifier_type.strip().upper(), 99),
    )
    for record in ordered:
        found = await _find_instrument_by_identifier(
            db,
            record.identifier_type,
            record.identifier_value,
        )
        if found is not None:
            return found
    return None


def _merged_identifier_records(
    base: list[IdentifierRecord],
    extra: list[IdentifierRecord],
) -> list[IdentifierRecord]:
    merged: list[IdentifierRecord] = []
    seen: set[tuple[str, str]] = set()
    for record in [*base, *extra]:
        key = (
            record.identifier_type.strip().upper(),
            record.identifier_value.strip().upper(),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(record)
    return merged


def _constituent_quote_type_allowed(profile: InstrumentProfile | None) -> bool:
    if profile is None:
        return False
    return (profile.quote_type or "EQUITY").upper() in {"EQUITY", "ETF", "MUTUALFUND", "INDEX"}


async def _provider_enriched_constituent_instrument(
    db: AsyncSession,
    row: CanonicalHoldingRow,
    *,
    source_provider: str,
    existing_instrument: Instrument | None = None,
) -> tuple[Instrument | None, Decimal | None, str | None]:
    if settings.APP_ENV == "test":
        return None, None, None

    for provider in get_identifier_providers():
        resolve_profile = getattr(provider, "resolve_instrument_profile", None)
        if not callable(resolve_profile):
            continue
        try:
            profile = resolve_profile(
                isin=row.isin,
                cusip=row.cusip,
                sedol=row.sedol,
            )
        except Exception:
            continue
        if profile is None:
            continue
        if not _constituent_quote_type_allowed(profile):
            continue
        if not _names_look_compatible(row.name, profile.name):
            continue

        instrument = existing_instrument
        if instrument is None:
            instrument = await _find_instrument_for_identifier_records(db, profile.identifiers)
        if instrument is None and profile.canonical_symbol:
            instrument = await _load_instrument_by_symbol_or_id(db, profile.canonical_symbol)

        if (
            existing_instrument is not None
            and profile.canonical_symbol
            and not _is_placeholder_symbol(existing_instrument.symbol)
            and _normalize_symbol(existing_instrument.symbol)
            != _normalize_symbol(profile.canonical_symbol)
        ):
            instrument = existing_instrument

        instrument = await ingest_provider_profile(db, profile, instrument=instrument)
        for identifier_type, value in [
            ("isin", row.isin),
            ("cusip", row.cusip),
            ("sedol", row.sedol),
        ]:
            normalized_value = _normalize_holding_identifier_value(value)
            if normalized_value:
                await register_identifier(
                    db,
                    instrument,
                    ETF_HOLDINGS_INTERNAL_PROVIDER,
                    IdentifierRecord(
                        identifier_type=identifier_type,
                        identifier_value=normalized_value,
                        is_primary=identifier_type == "isin",
                        source=source_provider,
                    ),
                )
        return (
            instrument,
            Decimal("0.9400"),
            "Matched through stable identifier profile enrichment.",
        )

    symbol = _normalize_symbol(row.symbol)
    if not symbol:
        return None, None, None

    extra_identifiers: list[IdentifierRecord] = []
    for provider in get_identifier_providers():
        try:
            extra_identifiers.extend(provider.fetch_stable_identifiers(symbol) or [])
        except Exception:
            continue

    matched_existing = await _find_instrument_for_identifier_records(db, extra_identifiers)
    if matched_existing is not None:
        for record in extra_identifiers:
            await register_identifier(
                db, matched_existing, record.source or source_provider, record
            )
        for identifier_type, value in [
            ("isin", row.isin),
            ("cusip", row.cusip),
            ("sedol", row.sedol),
        ]:
            normalized_value = _normalize_holding_identifier_value(value)
            if normalized_value:
                await register_identifier(
                    db,
                    matched_existing,
                    ETF_HOLDINGS_INTERNAL_PROVIDER,
                    IdentifierRecord(
                        identifier_type=identifier_type,
                        identifier_value=normalized_value,
                        is_primary=identifier_type == "isin",
                        source=source_provider,
                    ),
                )
        return matched_existing, Decimal("0.9200"), "Matched by stable identifier enrichment."

    try:
        profile = get_default_metadata_provider().get_instrument_profile(symbol)
    except Exception:
        profile = None
    if not _constituent_quote_type_allowed(profile):
        return None, None, None
    if profile is None or not _names_look_compatible(row.name, profile.name):
        return None, None, None

    profile.identifiers = _merged_identifier_records(profile.identifiers, extra_identifiers)
    existing = await _find_instrument_for_identifier_records(db, profile.identifiers)
    if existing is None and profile.canonical_symbol:
        existing = await _load_instrument_by_symbol_or_id(db, profile.canonical_symbol)

    instrument = await ingest_provider_profile(db, profile, instrument=existing)
    for identifier_type, value in [
        ("isin", row.isin),
        ("cusip", row.cusip),
        ("sedol", row.sedol),
    ]:
        normalized_value = _normalize_holding_identifier_value(value)
        if normalized_value:
            await register_identifier(
                db,
                instrument,
                ETF_HOLDINGS_INTERNAL_PROVIDER,
                IdentifierRecord(
                    identifier_type=identifier_type,
                    identifier_value=normalized_value,
                    is_primary=identifier_type == "isin",
                    source=source_provider,
                ),
            )
    # `ingest_provider_profile` stores the SEC SIC-derived classification on a
    # newly materialised constituent. Existing identity-only instruments are
    # handled by the bounded enrichment above.
    return instrument, Decimal("0.9000"), "Matched through provider-backed enrichment."


async def _enrich_existing_constituent_classification(
    db: AsyncSession,
    instrument: Instrument,
    *,
    reported_name: str | None,
    source_provider: str,
) -> None:
    """Fill missing issuer classification without changing canonical identity.

    ETF issuer files provide membership, but commonly omit an industry.  When a
    resolved constituent lacks one, use the configured free metadata provider
    (SEC EDGAR by default) to persist its source-labelled classification.  This
    is deliberately bounded to missing fields and never replaces an existing
    classification or infers an industry from the security name.
    """

    detail = (
        await db.execute(select(EquityDetail).where(EquityDetail.instrument_id == instrument.id))
    ).scalar_one_or_none()
    # This enrichment exists to fill the industry field used by the
    # top-down taxonomy.  A sector-only detail is not sufficient: treating it
    # as complete would preserve the very sector->industry promotion bug this
    # path is supposed to avoid.
    if detail is not None and detail.industry:
        return

    symbol = _normalize_symbol(instrument.symbol)
    if not symbol or _is_placeholder_symbol(symbol):
        return
    try:
        profile = get_default_metadata_provider().get_instrument_profile(symbol)
    except Exception:
        return
    if profile is None or not _constituent_quote_type_allowed(profile):
        return
    if reported_name and not _names_look_compatible(reported_name, profile.name):
        return

    industry = str(profile.extra.get("industry") or "").strip()
    if not industry:
        return
    if detail is None:
        detail = EquityDetail(instrument_id=instrument.id)
        db.add(detail)
    observed_at = _now().isoformat()
    classification_system = profile.extra.get("classification_system") or "provider_native"
    detail.industry = industry
    field_provenance = {
        **(detail.field_provenance or {}),
        "industry": {
            "source": profile.provider,
            "observed_at": observed_at,
            "selection_reason": "free metadata enrichment for ETF constituent classification",
            "classification_system": classification_system,
            "source_provider": source_provider,
        },
    }
    sector = str(profile.extra.get("sector") or "").strip()
    if sector and not detail.sector:
        detail.sector = sector
        field_provenance["sector"] = {
            "source": profile.provider,
            "observed_at": observed_at,
            "selection_reason": "free metadata enrichment for ETF constituent classification",
            "classification_system": classification_system,
            "source_provider": source_provider,
        }
    detail.field_provenance = field_provenance
    # Retain the immutable raw provider observation as well as the current
    # flattened detail.  Historical reads can then select the latest profile
    # known by their cutoff instead of treating today's metadata as timeless.
    await store_profile_snapshot(
        db,
        instrument,
        profile,
        observed_at=datetime.fromisoformat(observed_at),
        fetched_at=datetime.fromisoformat(observed_at),
    )
    await db.flush()


async def _load_instrument_by_symbol_or_id(
    db: AsyncSession, symbol_or_id: str | int
) -> Instrument | None:
    if isinstance(symbol_or_id, int) or str(symbol_or_id).isdigit():
        return await db.get(Instrument, int(symbol_or_id))
    symbol = str(symbol_or_id).strip().upper()
    return (
        await db.execute(select(Instrument).where(func.upper(Instrument.symbol) == symbol).limit(1))
    ).scalar_one_or_none()


async def get_etf_profile_for_instrument(db: AsyncSession, instrument_id: int) -> ETFProfile | None:
    return (
        await db.execute(
            select(ETFProfile)
            .options(selectinload(ETFProfile.instrument))
            .where(ETFProfile.instrument_id == instrument_id)
        )
    ).scalar_one_or_none()


async def ensure_etf_profile(
    db: AsyncSession,
    instrument: Instrument,
    *,
    issuer: str | None = None,
    sponsor: str | None = None,
    fund_family: str | None = None,
    index_name: str | None = None,
    product_url: str | None = None,
    sec_cik: str | None = None,
    sec_series_id: str | None = None,
    sec_class_id: str | None = None,
    provider_aliases: dict | None = None,
    legal_metadata: dict | None = None,
) -> ETFProfile:
    profile = await get_etf_profile_for_instrument(db, instrument.id)
    if profile is None:
        profile = ETFProfile(instrument_id=instrument.id)
        db.add(profile)
        await db.flush()

    for field, value in {
        "issuer": issuer,
        "sponsor": sponsor,
        "fund_family": fund_family,
        "index_name": index_name,
        "product_url": product_url,
        "sec_cik": sec_cik,
        "sec_series_id": sec_series_id,
        "sec_class_id": sec_class_id,
        "provider_aliases": provider_aliases,
        "legal_metadata": legal_metadata,
    }.items():
        if value is not None:
            setattr(profile, field, value)

    explicit_adapter = (
        str((profile.provider_aliases or {}).get("holdings_adapter") or "").strip().lower()
    )
    if explicit_adapter and get_holdings_adapter(explicit_adapter) is not None:
        # Curated issuer metadata is stronger than an older name/fund-family
        # inference (for example, an SMH profile carrying an obsolete ARK
        # classification). Preserve the explicit route on every hydration,
        # including the ingest path used by scheduled refreshes.
        profile.adapter_key = explicit_adapter
        profile.adapter_status = "candidate"
        profile.adapter_confidence = Decimal("0.9000")
    else:
        probe = infer_adapter_key(
            issuer=profile.issuer,
            fund_family=profile.fund_family,
            name=instrument.name,
            product_url=profile.product_url,
            provider_aliases=profile.provider_aliases,
        )
        if (
            profile.adapter_key in (None, "", "unresolved")
            or probe.status != "holdings_adapter_unresolved"
        ):
            profile.adapter_key = probe.adapter_key
            profile.adapter_status = probe.status
            profile.adapter_confidence = probe.confidence
        elif profile.adapter_status in (None, "pending"):
            profile.adapter_status = "unresolved"
    return profile


async def ensure_lightweight_etf_instrument(
    db: AsyncSession,
    *,
    symbol: str,
    name: str | None = None,
    currency: str | None = "USD",
) -> Instrument:
    symbol = symbol.strip().upper()
    instrument = await _load_instrument_by_symbol_or_id(db, symbol)
    if instrument is not None:
        return instrument

    from app.services.instrument_mastering import ensure_instrument_type

    instrument_type_id = await ensure_instrument_type(db, "Equity", "ETF")
    profile = InstrumentProfile(
        provider=ETF_HOLDINGS_INTERNAL_PROVIDER,
        symbol=symbol,
        canonical_symbol=symbol,
        name=name or symbol,
        currency=_normalize_currency_code(currency),
        quote_type="ETF",
        identifiers=[],
        listings=[
            ListingRecord(
                provider_symbol=symbol,
                provider_instrument_type="ETF",
                currency=_normalize_currency_code(currency),
                is_primary=True,
            )
        ],
        raw_payload={"source": ETF_HOLDINGS_INTERNAL_PROVIDER},
    )
    instrument = await ingest_provider_profile(db, profile)
    instrument.instrument_type_id = instrument_type_id
    return instrument


async def _find_instrument_by_identifier(
    db: AsyncSession, identifier_type: str, identifier_value: str | None
) -> Instrument | None:
    normalized_value = _normalize_holding_identifier_value(identifier_value)
    if not normalized_value:
        return None
    enum_type = _identifier_type(identifier_type)
    if enum_type is None:
        return None
    row = (
        await db.execute(
            select(Instrument)
            .join(InstrumentIdentifier, InstrumentIdentifier.instrument_id == Instrument.id)
            .where(
                InstrumentIdentifier.identifier_type == enum_type,
                InstrumentIdentifier.identifier_value == normalized_value,
                InstrumentIdentifier.is_active.is_(True),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return row


async def _deactivate_incompatible_internal_identifier(
    db: AsyncSession,
    *,
    identifier_type: str,
    identifier_value: str | None,
    reported_name: str | None,
) -> bool:
    normalized_value = _normalize_holding_identifier_value(identifier_value)
    enum_type = _identifier_type(identifier_type)
    if not normalized_value or enum_type is None or not reported_name:
        return False

    internal_source = await ensure_data_source(db, ETF_HOLDINGS_INTERNAL_PROVIDER)
    matches = (
        await db.execute(
            select(InstrumentIdentifier, Instrument)
            .join(Instrument, InstrumentIdentifier.instrument_id == Instrument.id)
            .where(
                InstrumentIdentifier.identifier_type == enum_type,
                InstrumentIdentifier.identifier_value == normalized_value,
                InstrumentIdentifier.is_active.is_(True),
                InstrumentIdentifier.data_source_id == internal_source.id,
            )
        )
    ).all()

    changed = False
    for identifier_row, instrument in matches:
        if _names_look_compatible(reported_name, instrument.name):
            continue
        identifier_row.is_active = False
        changed = True

    if changed:
        await db.flush()
    return changed


async def _resolve_or_create_constituent(
    db: AsyncSession,
    row: CanonicalHoldingRow,
    *,
    source_provider: str,
    allow_provider_enrichment: bool = True,
) -> tuple[Instrument | None, Decimal | None, str | None]:
    if row.row_type != "security" or row.holding_type in {"cash", "currency", "collateral"}:
        return None, None, None

    for identifier_type, value in [
        ("isin", row.isin),
        ("cusip", row.cusip),
        ("sedol", row.sedol),
    ]:
        found = await _find_instrument_by_identifier(db, identifier_type, value)
        if found is not None and not _names_look_compatible(row.name, found.name):
            changed = await _deactivate_incompatible_internal_identifier(
                db,
                identifier_type=identifier_type,
                identifier_value=value,
                reported_name=row.name,
            )
            if changed:
                found = await _find_instrument_by_identifier(db, identifier_type, value)
        if found is not None and not _names_look_compatible(row.name, found.name):
            found = None
        if found is not None:
            if allow_provider_enrichment:
                await _enrich_existing_constituent_classification(
                    db,
                    found,
                    reported_name=row.name,
                    source_provider=source_provider,
                )
            if allow_provider_enrichment and _is_placeholder_symbol(found.symbol):
                (
                    promoted,
                    promoted_confidence,
                    promoted_note,
                ) = await _provider_enriched_constituent_instrument(
                    db,
                    row,
                    source_provider=source_provider,
                    existing_instrument=found,
                )
                if promoted is not None:
                    return (
                        promoted,
                        promoted_confidence or Decimal("0.9500"),
                        promoted_note or f"Matched by {identifier_type.upper()}.",
                    )
            return found, Decimal("0.9500"), f"Matched by {identifier_type.upper()}."

    symbol = _normalize_symbol(row.symbol)
    if symbol:
        found = (
            await db.execute(
                select(Instrument).where(func.upper(Instrument.symbol) == symbol).limit(1)
            )
        ).scalar_one_or_none()
        if found is not None:
            if allow_provider_enrichment:
                await _enrich_existing_constituent_classification(
                    db,
                    found,
                    reported_name=row.name,
                    source_provider=source_provider,
                )
            if allow_provider_enrichment and _is_placeholder_symbol(found.symbol):
                (
                    promoted,
                    promoted_confidence,
                    promoted_note,
                ) = await _provider_enriched_constituent_instrument(
                    db,
                    row,
                    source_provider=source_provider,
                    existing_instrument=found,
                )
                if promoted is not None:
                    return (
                        promoted,
                        promoted_confidence or Decimal("0.8000"),
                        promoted_note or "Matched by canonical symbol.",
                    )
            return found, Decimal("0.8000"), "Matched by canonical symbol."

    if allow_provider_enrichment:
        (
            enriched_instrument,
            enriched_confidence,
            enriched_note,
        ) = await _provider_enriched_constituent_instrument(
            db,
            row,
            source_provider=source_provider,
        )
        if enriched_instrument is not None:
            return enriched_instrument, enriched_confidence, enriched_note

    if not symbol and not row.name:
        return None, None, "No symbol/name/identifier was available to resolve this holding."

    from app.services.instrument_mastering import ensure_instrument_type

    instrument_type_id = await ensure_instrument_type(db, "Equity", "Stock")
    symbol = symbol or f"HOLDING-{_hash_payload({'name': row.name, 'isin': row.isin})[:10].upper()}"
    instrument = (
        await db.execute(select(Instrument).where(func.upper(Instrument.symbol) == symbol).limit(1))
    ).scalar_one_or_none()
    if instrument is None:
        instrument = Instrument(
            instrument_type_id=instrument_type_id,
            symbol=symbol,
            name=row.name or symbol,
            currency=_normalize_currency_code(row.currency),
            is_active=True,
            field_provenance={
                "name": {
                    "source": source_provider,
                    "fetched_at": _now().isoformat(),
                    "note": "Lightweight instrument materialized from ETF holdings.",
                }
            },
        )
        db.add(instrument)
        await db.flush()

    for identifier_type, value in [
        ("isin", row.isin),
        ("cusip", row.cusip),
        ("sedol", row.sedol),
    ]:
        normalized_value = _normalize_holding_identifier_value(value)
        if normalized_value:
            await register_identifier(
                db,
                instrument,
                ETF_HOLDINGS_INTERNAL_PROVIDER,
                IdentifierRecord(
                    identifier_type=identifier_type,
                    identifier_value=normalized_value,
                    is_primary=identifier_type == "isin",
                    source=source_provider,
                ),
            )

    if allow_provider_enrichment and symbol and settings.APP_ENV != "test":
        for provider in get_identifier_providers():
            try:
                for record in provider.fetch_stable_identifiers(symbol) or []:
                    await register_identifier(
                        db,
                        instrument,
                        record.source or source_provider,
                        record,
                    )
            except Exception:
                continue

    return instrument, Decimal("0.5000"), None


async def _reconcile_existing_snapshot_rows(
    db: AsyncSession,
    *,
    snapshot: ETFHoldingsSnapshot,
    canonical_rows: list[CanonicalHoldingRow],
    source_provider: str,
    allow_provider_enrichment: bool = True,
) -> ETFHoldingsSnapshot:
    existing_rows = {row.source_row_hash: row for row in snapshot.rows}
    resolved = 0
    unresolved = 0

    for position, canonical_row in enumerate(canonical_rows, start=1):
        source_row_hash = _row_hash(canonical_row, position)
        existing = existing_rows.get(source_row_hash)
        if existing is None:
            continue

        existing.cusip = _normalize_holding_identifier_value(canonical_row.cusip)
        existing.isin = _normalize_holding_identifier_value(canonical_row.isin)
        existing.sedol = _normalize_holding_identifier_value(canonical_row.sedol)

        needs_reconcile = (
            not existing.is_resolved
            or existing.constituent_instrument is None
            or _is_placeholder_symbol(existing.constituent_instrument.symbol)
            or (
                existing.constituent_instrument is not None
                and (
                    existing.constituent_instrument.equity_detail is None
                    or not existing.constituent_instrument.equity_detail.industry
                )
            )
        )
        if needs_reconcile:
            instrument, confidence, note = await _resolve_or_create_constituent(
                db,
                canonical_row,
                source_provider=source_provider,
                allow_provider_enrichment=allow_provider_enrichment,
            )
            existing.constituent_instrument_id = instrument.id if instrument is not None else None
            existing.is_resolved = instrument is not None
            existing.resolution_confidence = confidence
            existing.resolution_note = note

        if existing.is_resolved:
            resolved += 1
        else:
            unresolved += 1

    snapshot.resolved_count = resolved
    snapshot.unresolved_count = unresolved
    await db.flush()
    return snapshot


def _row_hash(row: CanonicalHoldingRow, position: int) -> str:
    return _hash_payload(
        {
            "position": position,
            "symbol": row.symbol,
            "name": row.name,
            "cusip": row.cusip,
            "isin": row.isin,
            "sedol": row.sedol,
            "weight": row.weight,
            "shares": row.shares,
            "market_value": row.market_value,
            "currency": row.currency,
            "holding_type": row.holding_type,
            "row_type": row.row_type,
            "source_row_id": row.source_row_id,
        }
    )


def _snapshot_hash(rows: list[CanonicalHoldingRow]) -> str:
    return _hash_payload([_row_hash(row, idx) for idx, row in enumerate(rows, start=1)])


async def ingest_holdings_snapshot(
    db: AsyncSession,
    *,
    etf_instrument: Instrument,
    rows: list[CanonicalHoldingRow | ETFHoldingIngestRow],
    composition_date: date,
    as_of_date: date | None = None,
    known_at: datetime | None = None,
    published_at: datetime | None = None,
    provenance: str,
    source_provider: str,
    source_url: str | None = None,
    source_identifier: str | None = None,
    source_quality: str = "unknown",
    completeness_status: str = "unknown",
    parser_version: str = "v1",
    raw_payload_text: str | None = None,
    raw_payload_json: dict | None = None,
    legal_metadata: dict | None = None,
    notes: str | None = None,
    allow_provider_enrichment: bool = True,
) -> ETFHoldingsSnapshot:
    profile = await ensure_etf_profile(db, etf_instrument, legal_metadata=legal_metadata)
    canonical_rows = [
        row
        if isinstance(row, CanonicalHoldingRow)
        else CanonicalHoldingRow(
            symbol=row.symbol,
            name=row.name,
            cusip=_normalize_holding_identifier_value(row.cusip),
            isin=_normalize_holding_identifier_value(row.isin),
            sedol=_normalize_holding_identifier_value(row.sedol),
            weight=row.weight,
            shares=row.shares,
            market_value=row.market_value,
            currency=_normalize_holding_currency(row.currency),
            country=row.country,
            exchange=row.exchange,
            holding_type=row.holding_type,
            row_type=row.row_type,
            source_row_id=row.source_row_id,
            extra_data=row.extra_data or {},
        )
        for row in rows
    ]
    now = _now()
    known_at = known_at or published_at or _date_end(composition_date)
    data_source = await ensure_data_source(db, ETF_HOLDINGS_INTERNAL_PROVIDER)
    snapshot_hash = _snapshot_hash(canonical_rows)
    legal_metadata = dict(legal_metadata or {})
    capability_metadata = {
        "source_tier": _capability_source_tier(
            provenance=provenance,
            source_provider=source_provider,
            legal_metadata=legal_metadata,
        ),
        "transport_kind": _capability_transport_kind(
            source_url=source_url,
            legal_metadata=legal_metadata,
        ),
        "expected_cadence": legal_metadata.get("expected_cadence"),
        "schema_fingerprint": _schema_fingerprint(
            raw_payload_text=raw_payload_text,
            raw_payload_json=raw_payload_json,
        ),
    }

    raw_artifact: ETFHoldingsRawArtifact | None = None
    if raw_payload_text is not None or raw_payload_json is not None:
        raw_payload = raw_payload_json if raw_payload_json is not None else raw_payload_text
        content_hash = _hash_payload(raw_payload)
        raw_artifact = (
            await db.execute(
                select(ETFHoldingsRawArtifact).where(
                    ETFHoldingsRawArtifact.etf_profile_id == profile.id,
                    ETFHoldingsRawArtifact.source_kind == provenance,
                    ETFHoldingsRawArtifact.content_hash == content_hash,
                )
            )
        ).scalar_one_or_none()
        if raw_artifact is None:
            raw_artifact = ETFHoldingsRawArtifact(
                etf_profile_id=profile.id,
                data_source_id=data_source.id,
                source_kind=provenance,
                source_url=source_url,
                source_identifier=source_identifier,
                content_type="application/json" if raw_payload_json is not None else "text/plain",
                content_hash=content_hash,
                composition_date=composition_date,
                as_of_date=as_of_date,
                published_at=published_at,
                fetched_at=now,
                parser_version=parser_version,
                payload_text=raw_payload_text,
                payload_json=raw_payload_json,
                legal_metadata=legal_metadata,
            )
            db.add(raw_artifact)
            await db.flush()

    existing = (
        await db.execute(
            _apply_snapshot_visibility(select(ETFHoldingsSnapshot))
            .options(
                selectinload(ETFHoldingsSnapshot.rows).selectinload(
                    ETFHolding.constituent_instrument
                )
            )
            .where(
                ETFHoldingsSnapshot.etf_profile_id == profile.id,
                ETFHoldingsSnapshot.composition_date == composition_date,
                ETFHoldingsSnapshot.provenance == provenance,
                ETFHoldingsSnapshot.source_provider == source_provider,
                ETFHoldingsSnapshot.snapshot_hash == snapshot_hash,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return await _reconcile_existing_snapshot_rows(
            db,
            snapshot=existing,
            canonical_rows=canonical_rows,
            source_provider=source_provider,
            allow_provider_enrichment=allow_provider_enrichment,
        )

    snapshot = ETFHoldingsSnapshot(
        etf_profile_id=profile.id,
        source_artifact_id=raw_artifact.id if raw_artifact else None,
        data_source_id=data_source.id,
        composition_date=composition_date,
        as_of_date=as_of_date,
        known_at=known_at,
        published_at=published_at,
        provenance=provenance,
        source_provider=source_provider,
        source_url=source_url,
        source_identifier=source_identifier,
        source_quality=source_quality,
        completeness_status=completeness_status,
        row_count=len(canonical_rows),
        resolved_count=0,
        unresolved_count=0,
        total_weight=sum((row.weight or Decimal("0")) for row in canonical_rows),
        parser_version=parser_version,
        snapshot_hash=snapshot_hash,
        notes=notes,
        extra_data={
            "legal_metadata": legal_metadata,
            **{key: value for key, value in capability_metadata.items() if value is not None},
        },
    )
    db.add(snapshot)
    await db.flush()

    resolved = 0
    unresolved = 0
    for idx, row in enumerate(canonical_rows, start=1):
        instrument, confidence, resolution_note = await _resolve_or_create_constituent(
            db,
            row,
            source_provider=source_provider,
            allow_provider_enrichment=allow_provider_enrichment,
        )
        is_resolved = instrument is not None
        if is_resolved:
            resolved += 1
        else:
            unresolved += 1
        db.add(
            ETFHolding(
                snapshot_id=snapshot.id,
                constituent_instrument_id=instrument.id if instrument else None,
                position=idx,
                reported_symbol=_normalize_symbol(row.symbol),
                reported_name=row.name,
                cusip=_normalize_holding_identifier_value(row.cusip),
                isin=_normalize_holding_identifier_value(row.isin),
                sedol=_normalize_holding_identifier_value(row.sedol),
                weight=row.weight,
                shares=row.shares,
                market_value=row.market_value,
                currency=_normalize_holding_currency(row.currency),
                country=row.country,
                exchange=row.exchange,
                holding_type=row.holding_type,
                row_type=row.row_type,
                source_row_id=row.source_row_id,
                source_row_hash=_row_hash(row, idx),
                is_resolved=is_resolved,
                resolution_confidence=confidence,
                resolution_note=resolution_note,
                extra_data=row.extra_data or None,
            )
        )

    snapshot.resolved_count = resolved
    snapshot.unresolved_count = unresolved
    await _record_adapter_success(
        db,
        profile=profile,
        data_source_id=data_source.id,
        adapter_key=profile.adapter_key or source_provider,
        source_url=source_url,
        source_identifier=source_identifier,
        parser_version=parser_version,
        row_count=len(canonical_rows),
        resolved_count=resolved,
        unresolved_count=unresolved,
        composition_date=composition_date,
        published_at=published_at,
        completeness_status=completeness_status,
        observation_metadata=snapshot.extra_data,
    )
    await db.flush()
    await db.refresh(snapshot)
    return snapshot


def _holding_needs_reconcile(row: ETFHolding) -> bool:
    if row.row_type != "security" or row.holding_type in {"cash", "currency", "collateral"}:
        return False
    if not row.is_resolved or row.constituent_instrument is None:
        return True
    if _is_placeholder_symbol(row.constituent_instrument.symbol):
        return True
    if not _names_look_compatible(row.reported_name, row.constituent_instrument.name):
        return True
    detail = row.constituent_instrument.equity_detail
    if detail is None or not detail.industry:
        return True
    if (
        not _normalize_holding_identifier_value(row.cusip)
        and not _normalize_holding_identifier_value(row.isin)
        and not _normalize_holding_identifier_value(row.sedol)
        and not _normalize_symbol(row.reported_symbol)
        and not _names_look_compatible(row.reported_name, row.constituent_instrument.name)
    ):
        return True
    return False


def _holding_to_canonical_row(row: ETFHolding) -> CanonicalHoldingRow:
    return CanonicalHoldingRow(
        symbol=row.reported_symbol,
        name=row.reported_name,
        cusip=_normalize_holding_identifier_value(row.cusip),
        isin=_normalize_holding_identifier_value(row.isin),
        sedol=_normalize_holding_identifier_value(row.sedol),
        weight=row.weight,
        shares=row.shares,
        market_value=row.market_value,
        currency=_normalize_holding_currency(row.currency),
        country=row.country,
        exchange=row.exchange,
        holding_type=row.holding_type,
        row_type=row.row_type,
        source_row_id=row.source_row_id,
        extra_data=row.extra_data or {},
    )


async def reconcile_snapshot_constituents(
    db: AsyncSession,
    snapshot: ETFHoldingsSnapshot,
    *,
    max_classification_enrichment: int = 32,
) -> ETFHoldingsSnapshot:
    resolved = 0
    unresolved = 0
    source_provider = snapshot.source_provider or ETF_HOLDINGS_INTERNAL_PROVIDER
    classification_attempts = 0

    for row in snapshot.rows:
        row.cusip = _normalize_holding_identifier_value(row.cusip)
        row.isin = _normalize_holding_identifier_value(row.isin)
        row.sedol = _normalize_holding_identifier_value(row.sedol)
        needs_reconcile = _holding_needs_reconcile(row)
        missing_classification = bool(
            row.constituent_instrument is not None
            and (
                row.constituent_instrument.equity_detail is None
                or not row.constituent_instrument.equity_detail.industry
            )
        )
        if missing_classification and classification_attempts >= max_classification_enrichment:
            # Keep this snapshot usable and honest. A later scheduled pass can
            # continue the bounded enrichment without making an interactive
            # bootstrap fan out across hundreds of SEC submissions.
            needs_reconcile = False
        if needs_reconcile:
            if missing_classification:
                classification_attempts += 1
            instrument, confidence, note = await _resolve_or_create_constituent(
                db,
                _holding_to_canonical_row(row),
                source_provider=source_provider,
            )
            row.constituent_instrument_id = instrument.id if instrument is not None else None
            row.is_resolved = instrument is not None
            row.resolution_confidence = confidence
            row.resolution_note = note

        if row.is_resolved:
            resolved += 1
        else:
            unresolved += 1

    snapshot.resolved_count = resolved
    snapshot.unresolved_count = unresolved
    await db.flush()
    await db.refresh(snapshot)
    return snapshot


async def _record_adapter_success(
    db: AsyncSession,
    *,
    profile: ETFProfile,
    data_source_id: int | None,
    adapter_key: str,
    source_url: str | None,
    source_identifier: str | None,
    parser_version: str,
    row_count: int,
    resolved_count: int,
    unresolved_count: int,
    composition_date: date,
    published_at: datetime | None,
    completeness_status: str,
    observation_metadata: dict[str, Any] | None = None,
) -> None:
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
    state.data_source_id = data_source_id
    state.status = "success"
    state.last_success_at = _now()
    state.last_checked_at = state.last_success_at
    state.failure_reason = None
    state.source_url = source_url
    state.source_identifier = source_identifier
    state.parser_version = parser_version
    state.row_count = row_count
    state.resolved_count = resolved_count
    state.unresolved_count = unresolved_count
    state.composition_date = composition_date
    state.published_at = published_at
    state.completeness_status = completeness_status
    snapshot_metadata = observation_metadata or {}
    state.extra_data = {
        **(state.extra_data or {}),
        **{
            key: snapshot_metadata.get(key)
            for key in (
                "source_tier",
                "transport_kind",
                "expected_cadence",
                "schema_fingerprint",
            )
            if snapshot_metadata.get(key) is not None
        },
        "consecutive_failures": 0,
    }


async def list_etfs_with_holdings(db: AsyncSession, q: str | None = None) -> list[ETFProfileOut]:
    stmt = (
        select(ETFProfile)
        .join(Instrument, Instrument.id == ETFProfile.instrument_id)
        .options(selectinload(ETFProfile.instrument), selectinload(ETFProfile.snapshots))
    )
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(Instrument.symbol.ilike(pattern), Instrument.name.ilike(pattern)))
    rows = (await db.execute(stmt.order_by(Instrument.symbol.asc()).limit(100))).scalars().all()
    return [await profile_to_out(db, row) for row in rows]


async def profile_to_out(db: AsyncSession, profile: ETFProfile) -> ETFProfileOut:
    latest = await get_latest_snapshot(db, profile.instrument_id, include_holdings=False)
    state = (
        await db.execute(
            select(ETFHoldingsAdapterState)
            .where(ETFHoldingsAdapterState.etf_profile_id == profile.id)
            .order_by(
                ETFHoldingsAdapterState.last_checked_at.desc().nullslast(),
                ETFHoldingsAdapterState.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    instrument = profile.instrument or await db.get(Instrument, profile.instrument_id)
    capability = evaluate_capability(profile, latest, state).as_dict()
    return ETFProfileOut(
        id=profile.id,
        instrument_id=profile.instrument_id,
        symbol=instrument.symbol if instrument else "",
        name=instrument.name if instrument else "",
        issuer=profile.issuer,
        sponsor=profile.sponsor,
        fund_family=profile.fund_family,
        index_name=profile.index_name,
        product_url=profile.product_url,
        sec_cik=profile.sec_cik,
        sec_series_id=profile.sec_series_id,
        sec_class_id=profile.sec_class_id,
        adapter_key=profile.adapter_key,
        adapter_confidence=profile.adapter_confidence,
        adapter_status=profile.adapter_status,
        provider_aliases=profile.provider_aliases,
        legal_metadata=profile.legal_metadata,
        latest_composition_date=latest.composition_date if latest else None,
        latest_snapshot_id=latest.id if latest else None,
        resolved_count=latest.resolved_count if latest else 0,
        unresolved_count=latest.unresolved_count if latest else 0,
        holdings_capability=capability,
    )


async def holdings_capability_for_profile(
    db: AsyncSession,
    profile: ETFProfile,
    *,
    snapshot: ETFHoldingsSnapshotOut | None = None,
) -> dict[str, Any]:
    """Return operational capability without contacting an external source."""

    latest = snapshot or await get_latest_snapshot(
        db,
        profile.instrument_id,
        include_holdings=False,
        include_controlled_fixture=False,
    )
    state = (
        await db.execute(
            select(ETFHoldingsAdapterState)
            .where(ETFHoldingsAdapterState.etf_profile_id == profile.id)
            .order_by(
                ETFHoldingsAdapterState.last_checked_at.desc().nullslast(),
                ETFHoldingsAdapterState.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return evaluate_capability(profile, latest, state).as_dict()


async def get_latest_snapshot(
    db: AsyncSession,
    symbol_or_id: str | int,
    *,
    include_holdings: bool = True,
    include_controlled_fixture: bool = True,
) -> ETFHoldingsSnapshotOut | None:
    instrument = await _load_instrument_by_symbol_or_id(db, symbol_or_id)
    if instrument is None:
        return None
    profile = await get_etf_profile_for_instrument(db, instrument.id)
    if profile is None:
        return None
    options = [selectinload(ETFHoldingsSnapshot.etf_profile)]
    if include_holdings:
        options.append(
            selectinload(ETFHoldingsSnapshot.rows).selectinload(ETFHolding.constituent_instrument)
        )
    statement = (
        _apply_snapshot_visibility(select(ETFHoldingsSnapshot))
        .options(*options)
        .where(ETFHoldingsSnapshot.etf_profile_id == profile.id)
    )
    if not include_controlled_fixture:
        statement = statement.where(
            or_(
                ETFHoldingsSnapshot.provenance != "controlled_fixture",
                ETFHoldingsSnapshot.source_provider != "e2e_reference",
            )
        )
    snapshot = (
        await db.execute(
            statement.order_by(
                ETFHoldingsSnapshot.composition_date.desc(),
                ETFHoldingsSnapshot.known_at.desc().nullslast(),
                ETFHoldingsSnapshot.id.desc(),
            ).limit(1)
        )
    ).scalar_one_or_none()
    if snapshot is None:
        return None
    return snapshot_to_out(snapshot, instrument=instrument, include_holdings=include_holdings)


def snapshot_to_out(
    snapshot: ETFHoldingsSnapshot,
    *,
    instrument: Instrument,
    include_holdings: bool = True,
) -> ETFHoldingsSnapshotOut:
    holdings: list[ETFHoldingOut] = []
    if include_holdings:
        holdings = [
            ETFHoldingOut(
                id=row.id,
                snapshot_id=row.snapshot_id,
                constituent_instrument_id=row.constituent_instrument_id,
                constituent_symbol=row.constituent_instrument.symbol
                if row.constituent_instrument
                else None,
                constituent_name=row.constituent_instrument.name
                if row.constituent_instrument
                else None,
                position=row.position,
                reported_symbol=row.reported_symbol,
                reported_name=row.reported_name,
                cusip=row.cusip,
                isin=row.isin,
                sedol=row.sedol,
                weight=row.weight,
                shares=row.shares,
                market_value=row.market_value,
                currency=_normalize_holding_currency(row.currency),
                country=row.country,
                exchange=row.exchange,
                holding_type=row.holding_type,
                row_type=row.row_type,
                source_row_id=row.source_row_id,
                source_row_hash=row.source_row_hash,
                is_resolved=row.is_resolved,
                resolution_confidence=row.resolution_confidence,
                resolution_note=row.resolution_note,
                extra_data=row.extra_data,
            )
            for row in snapshot.rows
        ]
    return ETFHoldingsSnapshotOut(
        id=snapshot.id,
        etf_profile_id=snapshot.etf_profile_id,
        etf_instrument_id=instrument.id,
        etf_symbol=instrument.symbol,
        etf_name=instrument.name,
        composition_date=snapshot.composition_date,
        as_of_date=snapshot.as_of_date,
        known_at=snapshot.known_at,
        published_at=snapshot.published_at,
        provenance=snapshot.provenance,
        source_provider=snapshot.source_provider,
        source_url=snapshot.source_url,
        source_identifier=snapshot.source_identifier,
        source_quality=snapshot.source_quality,
        completeness_status=snapshot.completeness_status,
        row_count=snapshot.row_count,
        resolved_count=snapshot.resolved_count,
        unresolved_count=snapshot.unresolved_count,
        total_weight=snapshot.total_weight,
        parser_version=snapshot.parser_version,
        notes=snapshot.notes,
        extra_data=snapshot.extra_data,
        holdings=holdings,
    )


def holding_to_out(row: ETFHolding) -> ETFHoldingOut:
    return ETFHoldingOut(
        id=row.id,
        snapshot_id=row.snapshot_id,
        constituent_instrument_id=row.constituent_instrument_id,
        constituent_symbol=row.constituent_instrument.symbol
        if row.constituent_instrument
        else None,
        constituent_name=row.constituent_instrument.name if row.constituent_instrument else None,
        position=row.position,
        reported_symbol=row.reported_symbol,
        reported_name=row.reported_name,
        cusip=row.cusip,
        isin=row.isin,
        sedol=row.sedol,
        weight=row.weight,
        shares=row.shares,
        market_value=row.market_value,
        currency=row.currency,
        country=row.country,
        exchange=row.exchange,
        holding_type=row.holding_type,
        row_type=row.row_type,
        source_row_id=row.source_row_id,
        source_row_hash=row.source_row_hash,
        is_resolved=row.is_resolved,
        resolution_confidence=row.resolution_confidence,
        resolution_note=row.resolution_note,
        extra_data=row.extra_data,
    )


def _holding_identity_key(row: ETFHolding) -> str:
    for value in [
        row.isin,
        row.cusip,
        row.sedol,
        row.reported_symbol,
        row.reported_name,
        str(row.id),
    ]:
        normalized = str(value or "").strip().upper()
        if normalized:
            return normalized
    return str(row.id)


def _holding_label(row: ETFHolding) -> tuple[str, str]:
    symbol = (
        row.constituent_instrument.symbol
        if row.constituent_instrument
        else row.reported_symbol or row.isin or row.cusip or row.sedol or "—"
    )
    name = (
        row.constituent_instrument.name
        if row.constituent_instrument
        else row.reported_name or symbol
    )
    return symbol, name


async def _resolve_snapshot_entity(
    db: AsyncSession,
    *,
    profile_id: int,
    snapshot_id: int | None = None,
    snapshot_date: date | None = None,
    point_in_time: bool = True,
    index: int = 0,
) -> ETFHoldingsSnapshot | None:
    stmt = (
        _apply_snapshot_visibility(select(ETFHoldingsSnapshot))
        .options(
            selectinload(ETFHoldingsSnapshot.rows).selectinload(ETFHolding.constituent_instrument)
        )
        .where(ETFHoldingsSnapshot.etf_profile_id == profile_id)
    )
    if snapshot_id is not None:
        return (
            await db.execute(stmt.where(ETFHoldingsSnapshot.id == snapshot_id).limit(1))
        ).scalar_one_or_none()
    if snapshot_date is not None:
        if point_in_time:
            stmt = stmt.where(
                or_(
                    ETFHoldingsSnapshot.known_at.is_(None),
                    ETFHoldingsSnapshot.known_at <= _date_end(snapshot_date),
                ),
                ETFHoldingsSnapshot.composition_date <= snapshot_date,
            ).order_by(
                ETFHoldingsSnapshot.composition_date.desc(),
                ETFHoldingsSnapshot.known_at.desc().nullslast(),
                ETFHoldingsSnapshot.id.desc(),
            )
            return (await db.execute(stmt.limit(1))).scalar_one_or_none()
        snapshots = (await db.execute(stmt)).scalars().all()
        return min(
            snapshots,
            key=lambda row: (
                abs((row.composition_date - snapshot_date).days),
                -row.composition_date.toordinal(),
                -row.id,
            ),
            default=None,
        )
    stmt = stmt.order_by(
        ETFHoldingsSnapshot.composition_date.desc(),
        ETFHoldingsSnapshot.known_at.desc().nullslast(),
        ETFHoldingsSnapshot.id.desc(),
    ).offset(index)
    return (await db.execute(stmt.limit(1))).scalar_one_or_none()


async def get_holdings_page(
    db: AsyncSession,
    symbol_or_id: str | int,
    *,
    snapshot_id: int | None = None,
    snapshot_date: date | None = None,
    point_in_time: bool = True,
    q: str | None = None,
    sort: str = "position",
    direction: str = "asc",
    limit: int = 100,
    offset: int = 0,
) -> ETFHoldingsPageOut | None:
    instrument = await _load_instrument_by_symbol_or_id(db, symbol_or_id)
    if instrument is None:
        return None
    profile = await get_etf_profile_for_instrument(db, instrument.id)
    if profile is None:
        return None

    snapshot_stmt = _apply_snapshot_visibility(
        select(ETFHoldingsSnapshot).where(ETFHoldingsSnapshot.etf_profile_id == profile.id)
    )
    if snapshot_id is not None:
        snapshot_stmt = snapshot_stmt.where(ETFHoldingsSnapshot.id == snapshot_id)
    elif snapshot_date is not None:
        if point_in_time:
            snapshot_stmt = snapshot_stmt.where(
                or_(
                    ETFHoldingsSnapshot.known_at.is_(None),
                    ETFHoldingsSnapshot.known_at <= _date_end(snapshot_date),
                ),
                ETFHoldingsSnapshot.composition_date <= snapshot_date,
            ).order_by(
                ETFHoldingsSnapshot.composition_date.desc(),
                ETFHoldingsSnapshot.known_at.desc().nullslast(),
                ETFHoldingsSnapshot.id.desc(),
            )
        else:
            snapshots = (await db.execute(snapshot_stmt)).scalars().all()
            snapshot = min(
                snapshots,
                key=lambda row: (
                    abs((row.composition_date - snapshot_date).days),
                    -row.composition_date.toordinal(),
                    -row.id,
                ),
                default=None,
            )
            if snapshot is None:
                return None
            snapshot_stmt = _apply_snapshot_visibility(
                select(ETFHoldingsSnapshot).where(ETFHoldingsSnapshot.id == snapshot.id)
            )
    else:
        snapshot_stmt = snapshot_stmt.order_by(
            ETFHoldingsSnapshot.composition_date.desc(),
            ETFHoldingsSnapshot.known_at.desc().nullslast(),
            ETFHoldingsSnapshot.id.desc(),
        )

    snapshot = (await db.execute(snapshot_stmt.limit(1))).scalar_one_or_none()
    if snapshot is None:
        return None

    filters = [ETFHolding.snapshot_id == snapshot.id]
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(
                ETFHolding.reported_symbol.ilike(pattern),
                ETFHolding.reported_name.ilike(pattern),
                ETFHolding.cusip.ilike(pattern),
                ETFHolding.isin.ilike(pattern),
                ETFHolding.sedol.ilike(pattern),
                Instrument.symbol.ilike(pattern),
                Instrument.name.ilike(pattern),
            )
        )

    total = (
        await db.execute(
            select(func.count(ETFHolding.id))
            .outerjoin(Instrument, Instrument.id == ETFHolding.constituent_instrument_id)
            .where(*filters)
        )
    ).scalar_one()

    sort_key = sort.lower().strip()
    sort_expr = {
        "position": ETFHolding.position,
        "weight": ETFHolding.weight,
        "market_value": ETFHolding.market_value,
        "shares": ETFHolding.shares,
        "symbol": func.coalesce(Instrument.symbol, ETFHolding.reported_symbol, ""),
        "name": func.coalesce(Instrument.name, ETFHolding.reported_name, ""),
        "resolved": ETFHolding.is_resolved,
    }.get(sort_key, ETFHolding.position)
    if direction.lower().strip() == "desc":
        primary_order = sort_expr.desc().nullslast()
    else:
        primary_order = sort_expr.asc().nullslast()

    rows = (
        (
            await db.execute(
                select(ETFHolding)
                .outerjoin(Instrument, Instrument.id == ETFHolding.constituent_instrument_id)
                .options(selectinload(ETFHolding.constituent_instrument))
                .where(*filters)
                .order_by(primary_order, ETFHolding.position.asc(), ETFHolding.id.asc())
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    return ETFHoldingsPageOut(
        snapshot=snapshot_to_out(snapshot, instrument=instrument, include_holdings=False),
        holdings=[holding_to_out(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
        has_next=offset + len(rows) < total,
    )


async def get_holdings_diff(
    db: AsyncSession,
    symbol_or_id: str | int,
    *,
    left_snapshot_id: int | None = None,
    right_snapshot_id: int | None = None,
    left_date: date | None = None,
    right_date: date | None = None,
    point_in_time: bool = True,
    include_unchanged: bool = False,
) -> ETFHoldingsDiffOut | None:
    instrument = await _load_instrument_by_symbol_or_id(db, symbol_or_id)
    if instrument is None:
        return None
    profile = await get_etf_profile_for_instrument(db, instrument.id)
    if profile is None:
        return None

    right_snapshot = await _resolve_snapshot_entity(
        db,
        profile_id=profile.id,
        snapshot_id=right_snapshot_id,
        snapshot_date=right_date,
        point_in_time=point_in_time,
        index=0,
    )
    if right_snapshot is None:
        return None

    left_snapshot = await _resolve_snapshot_entity(
        db,
        profile_id=profile.id,
        snapshot_id=left_snapshot_id,
        snapshot_date=left_date,
        point_in_time=point_in_time,
        index=1 if left_snapshot_id is None and left_date is None else 0,
    )
    if left_snapshot is None:
        return None

    return _build_holdings_diff(
        instrument=instrument,
        left_snapshot=left_snapshot,
        right_snapshot=right_snapshot,
        include_unchanged=include_unchanged,
    )


def _build_holdings_diff(
    *,
    instrument: Instrument,
    left_snapshot: ETFHoldingsSnapshot,
    right_snapshot: ETFHoldingsSnapshot,
    include_unchanged: bool = False,
) -> ETFHoldingsDiffOut:
    left_rows = {_holding_identity_key(row): row for row in left_snapshot.rows}
    right_rows = {_holding_identity_key(row): row for row in right_snapshot.rows}
    all_keys = sorted(set(left_rows) | set(right_rows))

    diff_rows: list[ETFHoldingsDiffRowOut] = []
    added_rows: list[ETFHoldingsDiffRowOut] = []
    removed_rows: list[ETFHoldingsDiffRowOut] = []
    changed_rows: list[ETFHoldingsDiffRowOut] = []
    added = removed = changed = unchanged = 0
    gross_weight_churn = Decimal("0")
    total_added_weight = Decimal("0")
    total_removed_weight = Decimal("0")
    total_increased_weight = Decimal("0")
    total_decreased_weight = Decimal("0")

    def _append_row(row: ETFHoldingsDiffRowOut) -> None:
        diff_rows.append(row)
        if row.status == "added":
            added_rows.append(row)
        elif row.status == "removed":
            removed_rows.append(row)
        elif row.status == "changed":
            changed_rows.append(row)

    for key in all_keys:
        left_row = left_rows.get(key)
        right_row = right_rows.get(key)
        if left_row is None and right_row is not None:
            added += 1
            symbol, name = _holding_label(right_row)
            row = ETFHoldingsDiffRowOut(
                key=key,
                symbol=symbol,
                name=name,
                status="added",
                weight_after=right_row.weight,
                market_value_after=right_row.market_value,
                shares_after=right_row.shares,
                holding_type_after=right_row.holding_type,
                row_type_after=right_row.row_type,
                resolved_after=right_row.is_resolved,
            )
            added_weight = right_row.weight or Decimal("0")
            gross_weight_churn += abs(added_weight)
            total_added_weight += added_weight
            _append_row(row)
            continue
        if left_row is not None and right_row is None:
            removed += 1
            symbol, name = _holding_label(left_row)
            row = ETFHoldingsDiffRowOut(
                key=key,
                symbol=symbol,
                name=name,
                status="removed",
                weight_before=left_row.weight,
                market_value_before=left_row.market_value,
                shares_before=left_row.shares,
                holding_type_before=left_row.holding_type,
                row_type_before=left_row.row_type,
                resolved_before=left_row.is_resolved,
            )
            removed_weight = left_row.weight or Decimal("0")
            gross_weight_churn += abs(removed_weight)
            total_removed_weight += removed_weight
            _append_row(row)
            continue
        if left_row is None or right_row is None:
            continue

        weight_before = left_row.weight
        weight_after = right_row.weight
        weight_delta = None
        if weight_before is not None or weight_after is not None:
            weight_delta = (weight_after or Decimal("0")) - (weight_before or Decimal("0"))
        row_changed = any(
            [
                (weight_delta or Decimal("0")) != Decimal("0"),
                left_row.market_value != right_row.market_value,
                left_row.shares != right_row.shares,
                left_row.holding_type != right_row.holding_type,
                left_row.row_type != right_row.row_type,
                left_row.is_resolved != right_row.is_resolved,
            ]
        )
        if row_changed:
            changed += 1
            gross_weight_churn += abs(weight_delta or Decimal("0"))
            if (weight_delta or Decimal("0")) > 0:
                total_increased_weight += weight_delta or Decimal("0")
            elif (weight_delta or Decimal("0")) < 0:
                total_decreased_weight += abs(weight_delta or Decimal("0"))
        else:
            unchanged += 1
            if not include_unchanged:
                continue
        symbol, name = _holding_label(right_row)
        _append_row(
            ETFHoldingsDiffRowOut(
                key=key,
                symbol=symbol,
                name=name,
                status="changed" if row_changed else "unchanged",
                weight_before=weight_before,
                weight_after=weight_after,
                weight_delta=weight_delta,
                market_value_before=left_row.market_value,
                market_value_after=right_row.market_value,
                shares_before=left_row.shares,
                shares_after=right_row.shares,
                holding_type_before=left_row.holding_type,
                holding_type_after=right_row.holding_type,
                row_type_before=left_row.row_type,
                row_type_after=right_row.row_type,
                resolved_before=left_row.is_resolved,
                resolved_after=right_row.is_resolved,
            )
        )

    order_rank = {"added": 0, "removed": 1, "changed": 2, "unchanged": 3}
    diff_rows.sort(
        key=lambda row: (
            order_rank.get(row.status, 99),
            -abs(float(row.weight_delta or Decimal("0"))),
            row.symbol,
            row.name,
        )
    )

    def _rows_by_weight_after(rows: list[ETFHoldingsDiffRowOut]) -> list[ETFHoldingsDiffRowOut]:
        return sorted(
            rows,
            key=lambda row: (
                -abs(float(row.weight_after or Decimal("0"))),
                row.symbol,
                row.name,
            ),
        )[:5]

    def _rows_by_weight_before(rows: list[ETFHoldingsDiffRowOut]) -> list[ETFHoldingsDiffRowOut]:
        return sorted(
            rows,
            key=lambda row: (
                -abs(float(row.weight_before or Decimal("0"))),
                row.symbol,
                row.name,
            ),
        )[:5]

    def _rows_by_delta(rows: list[ETFHoldingsDiffRowOut]) -> list[ETFHoldingsDiffRowOut]:
        return sorted(
            rows,
            key=lambda row: (
                -abs(float(row.weight_delta or Decimal("0"))),
                row.symbol,
                row.name,
            ),
        )[:5]

    return ETFHoldingsDiffOut(
        left_snapshot=snapshot_to_out(left_snapshot, instrument=instrument, include_holdings=False),
        right_snapshot=snapshot_to_out(
            right_snapshot, instrument=instrument, include_holdings=False
        ),
        total_rows=len(diff_rows),
        added=added,
        removed=removed,
        changed=changed,
        unchanged=unchanged,
        summary=ETFHoldingsDiffSummaryOut(
            gross_weight_churn=gross_weight_churn,
            total_added_weight=total_added_weight,
            total_removed_weight=total_removed_weight,
            total_increased_weight=total_increased_weight,
            total_decreased_weight=total_decreased_weight,
            largest_additions=_rows_by_weight_after(added_rows),
            largest_removals=_rows_by_weight_before(removed_rows),
            largest_reweights=_rows_by_delta(changed_rows),
        ),
        rows=diff_rows,
    )


async def get_holdings_transition_timeline(
    db: AsyncSession,
    symbol_or_id: str | int,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 24,
) -> ETFHoldingsTransitionTimelineOut | None:
    instrument = await _load_instrument_by_symbol_or_id(db, symbol_or_id)
    if instrument is None:
        return None
    profile = await get_etf_profile_for_instrument(db, instrument.id)
    if profile is None:
        return None

    stmt = (
        _apply_snapshot_visibility(select(ETFHoldingsSnapshot))
        .options(
            selectinload(ETFHoldingsSnapshot.rows).selectinload(ETFHolding.constituent_instrument)
        )
        .where(ETFHoldingsSnapshot.etf_profile_id == profile.id)
        .order_by(ETFHoldingsSnapshot.composition_date.asc(), ETFHoldingsSnapshot.id.asc())
    )
    if start_date is not None:
        stmt = stmt.where(ETFHoldingsSnapshot.composition_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(ETFHoldingsSnapshot.composition_date <= end_date)
    snapshots = (await db.execute(stmt)).scalars().all()
    if len(snapshots) < 2:
        return ETFHoldingsTransitionTimelineOut(
            etf_symbol=instrument.symbol,
            etf_name=instrument.name or instrument.symbol,
            snapshot_count=len(snapshots),
            transition_count=0,
            from_date=snapshots[0].composition_date if snapshots else None,
            to_date=snapshots[-1].composition_date if snapshots else None,
            transitions=[],
        )

    transition_pairs = list(zip(snapshots, snapshots[1:], strict=False))
    transition_pairs = transition_pairs[-limit:]
    transitions: list[ETFHoldingsTransitionOut] = []
    for left_snapshot, right_snapshot in transition_pairs:
        diff = _build_holdings_diff(
            instrument=instrument,
            left_snapshot=left_snapshot,
            right_snapshot=right_snapshot,
            include_unchanged=False,
        )
        transitions.append(
            ETFHoldingsTransitionOut(
                left_snapshot=diff.left_snapshot,
                right_snapshot=diff.right_snapshot,
                added=diff.added,
                removed=diff.removed,
                changed=diff.changed,
                unchanged=diff.unchanged,
                gross_weight_churn=diff.summary.gross_weight_churn,
                total_added_weight=diff.summary.total_added_weight,
                total_removed_weight=diff.summary.total_removed_weight,
                total_increased_weight=diff.summary.total_increased_weight,
                total_decreased_weight=diff.summary.total_decreased_weight,
                largest_additions=diff.summary.largest_additions,
                largest_removals=diff.summary.largest_removals,
                largest_reweights=diff.summary.largest_reweights,
            )
        )

    return ETFHoldingsTransitionTimelineOut(
        etf_symbol=instrument.symbol,
        etf_name=instrument.name or instrument.symbol,
        snapshot_count=len(snapshots),
        transition_count=max(0, len(snapshots) - 1),
        from_date=snapshots[0].composition_date,
        to_date=snapshots[-1].composition_date,
        transitions=transitions,
    )


async def get_holdings_overlap_summary(
    db: AsyncSession,
    *,
    etf_symbols: list[str] | None = None,
    etf_instrument_ids: list[int] | None = None,
    snapshot_date: date | None = None,
    point_in_time: bool = True,
    top_n: int = 10,
) -> ETFHoldingsOverlapSummaryOut:
    identifiers: list[str | int] = [*(etf_symbols or []), *(etf_instrument_ids or [])]
    loaded: list[tuple[Instrument, ETFHoldingsSnapshot]] = []
    missing: list[str] = []

    for identifier in identifiers:
        instrument = await _load_instrument_by_symbol_or_id(db, identifier)
        if instrument is None:
            missing.append(str(identifier))
            continue
        profile = await get_etf_profile_for_instrument(db, instrument.id)
        if profile is None:
            missing.append(instrument.symbol)
            continue
        snapshot = await _resolve_snapshot_entity(
            db,
            profile_id=profile.id,
            snapshot_date=snapshot_date,
            point_in_time=point_in_time,
        )
        if snapshot is None:
            missing.append(instrument.symbol)
            continue
        loaded.append((instrument, snapshot))

    pairs: list[ETFHoldingsOverlapPairOut] = []
    for left_index, (left_instrument, left_snapshot) in enumerate(loaded):
        left_rows = {_holding_identity_key(row): row for row in left_snapshot.rows}
        left_keys = set(left_rows)
        for right_instrument, right_snapshot in loaded[left_index + 1 :]:
            right_rows = {_holding_identity_key(row): row for row in right_snapshot.rows}
            right_keys = set(right_rows)
            shared_keys = left_keys & right_keys
            union_count = len(left_keys | right_keys)
            shared_constituents: list[ETFHoldingsOverlapConstituentOut] = []
            shared_weight_left = Decimal("0")
            shared_weight_right = Decimal("0")
            overlap_weight_min = Decimal("0")
            for key in shared_keys:
                left_row = left_rows[key]
                right_row = right_rows[key]
                left_weight = left_row.weight
                right_weight = right_row.weight
                if left_weight is not None:
                    shared_weight_left += left_weight
                if right_weight is not None:
                    shared_weight_right += right_weight
                min_weight = None
                if left_weight is not None or right_weight is not None:
                    min_weight = min(left_weight or Decimal("0"), right_weight or Decimal("0"))
                    overlap_weight_min += min_weight
                symbol, name = _holding_label(right_row)
                shared_constituents.append(
                    ETFHoldingsOverlapConstituentOut(
                        key=key,
                        symbol=symbol,
                        name=name,
                        weight_left=left_weight,
                        weight_right=right_weight,
                        min_weight=min_weight,
                    )
                )
            shared_constituents.sort(
                key=lambda row: (
                    -float(row.min_weight or Decimal("0")),
                    row.symbol,
                    row.name,
                )
            )
            pairs.append(
                ETFHoldingsOverlapPairOut(
                    left_symbol=left_instrument.symbol,
                    right_symbol=right_instrument.symbol,
                    left_snapshot=snapshot_to_out(
                        left_snapshot,
                        instrument=left_instrument,
                        include_holdings=False,
                    ),
                    right_snapshot=snapshot_to_out(
                        right_snapshot,
                        instrument=right_instrument,
                        include_holdings=False,
                    ),
                    left_count=len(left_keys),
                    right_count=len(right_keys),
                    shared_count=len(shared_keys),
                    left_unique_count=len(left_keys - right_keys),
                    right_unique_count=len(right_keys - left_keys),
                    jaccard_overlap=(
                        Decimal(len(shared_keys)) / Decimal(union_count)
                        if union_count
                        else Decimal("0")
                    ),
                    shared_weight_left=shared_weight_left,
                    shared_weight_right=shared_weight_right,
                    overlap_weight_min=overlap_weight_min,
                    top_shared=shared_constituents[:top_n],
                )
            )

    pairs.sort(
        key=lambda pair: (
            -pair.jaccard_overlap,
            -pair.shared_count,
            pair.left_symbol,
            pair.right_symbol,
        )
    )
    return ETFHoldingsOverlapSummaryOut(
        requested_symbols=[str(identifier) for identifier in identifiers],
        snapshot_date=snapshot_date,
        point_in_time=point_in_time,
        etf_count=len(loaded),
        pair_count=len(pairs),
        pairs=pairs,
        missing=missing,
    )


async def _expand_overlap_matrix_symbols(
    db: AsyncSession,
    *,
    etf_symbols: list[str] | None,
    issuer: str | None,
    fund_family: str | None,
    q: str | None,
    limit: int,
) -> list[str]:
    symbols = [symbol.strip().upper() for symbol in etf_symbols or [] if symbol.strip()]
    if not any([issuer, fund_family, q]):
        return symbols

    stmt = (
        select(ETFProfile)
        .join(Instrument, Instrument.id == ETFProfile.instrument_id)
        .join(ETFHoldingsSnapshot, ETFHoldingsSnapshot.etf_profile_id == ETFProfile.id)
        .options(selectinload(ETFProfile.instrument))
    )
    stmt = stmt.where(*_visible_snapshot_conditions())
    if issuer:
        stmt = stmt.where(ETFProfile.issuer.ilike(f"%{issuer.strip()}%"))
    if fund_family:
        stmt = stmt.where(ETFProfile.fund_family.ilike(f"%{fund_family.strip()}%"))
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Instrument.symbol.ilike(pattern),
                Instrument.name.ilike(pattern),
                ETFProfile.issuer.ilike(pattern),
                ETFProfile.fund_family.ilike(pattern),
                ETFProfile.index_name.ilike(pattern),
            )
        )
    profiles = (
        (await db.execute(stmt.order_by(Instrument.symbol.asc()).limit(limit)))
        .scalars()
        .unique()
        .all()
    )

    seen = set(symbols)
    for profile in profiles:
        instrument = profile.instrument
        if instrument is None:
            continue
        symbol = instrument.symbol.upper()
        if symbol not in seen:
            symbols.append(symbol)
            seen.add(symbol)
    return symbols[:limit]


def _overlap_matrix_value(pair: ETFHoldingsOverlapPairOut, metric: str) -> Decimal:
    if metric == "shared_count":
        return Decimal(pair.shared_count)
    if metric == "overlap_weight_min":
        return pair.overlap_weight_min or Decimal("0")
    return pair.jaccard_overlap


async def get_holdings_overlap_matrix(
    db: AsyncSession,
    *,
    etf_symbols: list[str] | None = None,
    etf_instrument_ids: list[int] | None = None,
    snapshot_date: date | None = None,
    point_in_time: bool = True,
    top_n: int = 10,
    metric: str = "jaccard",
    issuer: str | None = None,
    fund_family: str | None = None,
    q: str | None = None,
    limit: int = 25,
) -> ETFHoldingsOverlapMatrixOut:
    expanded_symbols = await _expand_overlap_matrix_symbols(
        db,
        etf_symbols=etf_symbols,
        issuer=issuer,
        fund_family=fund_family,
        q=q,
        limit=limit,
    )
    summary = await get_holdings_overlap_summary(
        db,
        etf_symbols=expanded_symbols,
        etf_instrument_ids=etf_instrument_ids,
        snapshot_date=snapshot_date,
        point_in_time=point_in_time,
        top_n=top_n,
    )
    snapshots_by_symbol: dict[str, ETFHoldingsSnapshotOut] = {}
    names_by_symbol: dict[str, str] = {}
    cells_by_symbol: dict[str, list[ETFHoldingsOverlapMatrixCellOut]] = defaultdict(list)
    pair_lookup: dict[tuple[str, str], ETFHoldingsOverlapPairOut] = {}
    for pair in summary.pairs:
        snapshots_by_symbol[pair.left_symbol] = pair.left_snapshot
        snapshots_by_symbol[pair.right_symbol] = pair.right_snapshot
        names_by_symbol[pair.left_symbol] = pair.left_snapshot.etf_name
        names_by_symbol[pair.right_symbol] = pair.right_snapshot.etf_name
        pair_lookup[(pair.left_symbol, pair.right_symbol)] = pair
        pair_lookup[(pair.right_symbol, pair.left_symbol)] = pair

    symbols = sorted(snapshots_by_symbol)
    for row_symbol in symbols:
        for column_symbol in symbols:
            if row_symbol == column_symbol:
                value = Decimal("1") if metric == "jaccard" else Decimal("0")
                cell = ETFHoldingsOverlapMatrixCellOut(
                    row_symbol=row_symbol,
                    column_symbol=column_symbol,
                    value=value,
                    shared_count=0,
                    jaccard_overlap=Decimal("1"),
                    overlap_weight_min=None,
                )
            else:
                pair = pair_lookup[(row_symbol, column_symbol)]
                cell = ETFHoldingsOverlapMatrixCellOut(
                    row_symbol=row_symbol,
                    column_symbol=column_symbol,
                    value=_overlap_matrix_value(pair, metric),
                    shared_count=pair.shared_count,
                    jaccard_overlap=pair.jaccard_overlap,
                    overlap_weight_min=pair.overlap_weight_min,
                )
            cells_by_symbol[row_symbol].append(cell)

    rows: list[ETFHoldingsOverlapMatrixRowOut] = []
    for symbol in symbols:
        peer_cells = [cell for cell in cells_by_symbol[symbol] if cell.column_symbol != symbol]
        overlaps = [cell.jaccard_overlap for cell in peer_cells]
        closest = max(peer_cells, key=lambda cell: cell.jaccard_overlap, default=None)
        most_distinct = min(peer_cells, key=lambda cell: cell.jaccard_overlap, default=None)
        rows.append(
            ETFHoldingsOverlapMatrixRowOut(
                symbol=symbol,
                name=names_by_symbol.get(symbol, symbol),
                snapshot=snapshots_by_symbol[symbol],
                average_overlap=(
                    sum(overlaps, Decimal("0")) / Decimal(len(overlaps))
                    if overlaps
                    else Decimal("0")
                ),
                max_overlap=max(overlaps) if overlaps else Decimal("0"),
                min_overlap=min(overlaps) if overlaps else Decimal("0"),
                closest_peer=closest.column_symbol if closest is not None else None,
                most_distinct_peer=most_distinct.column_symbol
                if most_distinct is not None
                else None,
                cells=cells_by_symbol[symbol],
            )
        )

    return ETFHoldingsOverlapMatrixOut(
        requested_symbols=summary.requested_symbols,
        snapshot_date=snapshot_date,
        point_in_time=point_in_time,
        metric=metric,
        etf_count=summary.etf_count,
        symbols=symbols,
        rows=rows,
        highest_overlap_pairs=summary.pairs[:top_n],
        lowest_overlap_pairs=sorted(
            summary.pairs,
            key=lambda pair: (
                pair.jaccard_overlap,
                pair.shared_count,
                pair.left_symbol,
                pair.right_symbol,
            ),
        )[:top_n],
        missing=summary.missing,
    )


async def list_available_dates(
    db: AsyncSession, symbol_or_id: str | int
) -> list[ETFHoldingsDateOut]:
    instrument = await _load_instrument_by_symbol_or_id(db, symbol_or_id)
    if instrument is None:
        return []
    profile = await get_etf_profile_for_instrument(db, instrument.id)
    if profile is None:
        return []
    rows = (
        (
            await db.execute(
                _apply_snapshot_visibility(
                    select(ETFHoldingsSnapshot).where(
                        ETFHoldingsSnapshot.etf_profile_id == profile.id
                    )
                ).order_by(ETFHoldingsSnapshot.composition_date.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        ETFHoldingsDateOut(
            snapshot_id=row.id,
            composition_date=row.composition_date,
            as_of_date=row.as_of_date,
            known_at=row.known_at,
            provenance=row.provenance,
            source_provider=row.source_provider,
            row_count=row.row_count,
            resolved_count=row.resolved_count,
            unresolved_count=row.unresolved_count,
            source_quality=row.source_quality,
        )
        for row in rows
    ]


async def get_nearest_snapshot(
    db: AsyncSession,
    symbol_or_id: str | int,
    requested_date: date,
    *,
    point_in_time: bool = True,
) -> ETFHoldingsSnapshotOut | None:
    instrument = await _load_instrument_by_symbol_or_id(db, symbol_or_id)
    if instrument is None:
        return None
    profile = await get_etf_profile_for_instrument(db, instrument.id)
    if profile is None:
        return None
    stmt = (
        _apply_snapshot_visibility(select(ETFHoldingsSnapshot))
        .options(
            selectinload(ETFHoldingsSnapshot.rows).selectinload(ETFHolding.constituent_instrument)
        )
        .where(ETFHoldingsSnapshot.etf_profile_id == profile.id)
    )
    if point_in_time:
        stmt = stmt.where(
            or_(
                ETFHoldingsSnapshot.known_at.is_(None),
                ETFHoldingsSnapshot.known_at <= _date_end(requested_date),
            ),
            ETFHoldingsSnapshot.composition_date <= requested_date,
        ).order_by(ETFHoldingsSnapshot.composition_date.desc())
    else:
        snapshots = (await db.execute(stmt)).scalars().all()
        snapshot = min(
            snapshots,
            key=lambda row: (
                abs((row.composition_date - requested_date).days),
                -row.composition_date.toordinal(),
                -row.id,
            ),
            default=None,
        )
        if snapshot is None:
            return None
        return snapshot_to_out(snapshot, instrument=instrument)

    snapshot = (await db.execute(stmt.limit(1))).scalar_one_or_none()
    if snapshot is None:
        return None
    return snapshot_to_out(snapshot, instrument=instrument)


async def get_unresolved_holdings(
    db: AsyncSession, symbol_or_id: str | int, *, snapshot_id: int | None = None
) -> list[ETFUnresolvedHoldingOut]:
    instrument = await _load_instrument_by_symbol_or_id(db, symbol_or_id)
    if instrument is None:
        return []
    profile = await get_etf_profile_for_instrument(db, instrument.id)
    if profile is None:
        return []
    stmt = (
        _apply_snapshot_visibility(select(ETFHolding, ETFHoldingsSnapshot))
        .join(ETFHoldingsSnapshot, ETFHoldingsSnapshot.id == ETFHolding.snapshot_id)
        .where(
            ETFHoldingsSnapshot.etf_profile_id == profile.id,
            ETFHolding.is_resolved.is_(False),
        )
    )
    if snapshot_id is not None:
        stmt = stmt.where(ETFHolding.snapshot_id == snapshot_id)
    rows = (await db.execute(stmt.order_by(ETFHoldingsSnapshot.composition_date.desc()))).all()
    return [
        ETFUnresolvedHoldingOut(
            snapshot_id=snapshot.id,
            composition_date=snapshot.composition_date,
            reported_symbol=row.reported_symbol,
            reported_name=row.reported_name,
            cusip=row.cusip,
            isin=row.isin,
            sedol=row.sedol,
            weight=row.weight,
            holding_type=row.holding_type,
            resolution_note=row.resolution_note,
        )
        for row, snapshot in rows
    ]


async def get_constituent_timeline(
    db: AsyncSession,
    symbol_or_id: str | int,
    constituent_id: int,
) -> list[ETFConstituentTimelinePoint]:
    instrument = await _load_instrument_by_symbol_or_id(db, symbol_or_id)
    if instrument is None:
        return []
    profile = await get_etf_profile_for_instrument(db, instrument.id)
    if profile is None:
        return []
    rows = (
        await db.execute(
            _apply_snapshot_visibility(select(ETFHolding, ETFHoldingsSnapshot))
            .join(ETFHoldingsSnapshot, ETFHoldingsSnapshot.id == ETFHolding.snapshot_id)
            .where(
                ETFHoldingsSnapshot.etf_profile_id == profile.id,
                ETFHolding.constituent_instrument_id == constituent_id,
            )
            .order_by(ETFHoldingsSnapshot.composition_date.asc())
        )
    ).all()
    points: list[ETFConstituentTimelinePoint] = []
    previous_weight: Decimal | None = None
    for row, snapshot in rows:
        weight_delta = None
        if row.weight is not None and previous_weight is not None:
            weight_delta = row.weight - previous_weight
        points.append(
            ETFConstituentTimelinePoint(
                snapshot_id=snapshot.id,
                composition_date=snapshot.composition_date,
                as_of_date=snapshot.as_of_date,
                known_at=snapshot.known_at,
                weight=row.weight,
                weight_delta_from_previous=weight_delta,
                shares=row.shares,
                market_value=row.market_value,
                source_provider=snapshot.source_provider,
                provenance=snapshot.provenance,
            )
        )
        if row.weight is not None:
            previous_weight = row.weight
    return points


async def get_weight_evolution(
    db: AsyncSession,
    symbol_or_id: str | int,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 12,
) -> ETFHoldingsWeightEvolutionOut | None:
    instrument = await _load_instrument_by_symbol_or_id(db, symbol_or_id)
    if instrument is None:
        return None
    profile = await get_etf_profile_for_instrument(db, instrument.id)
    if profile is None:
        return None

    stmt = (
        _apply_snapshot_visibility(select(ETFHoldingsSnapshot))
        .options(
            selectinload(ETFHoldingsSnapshot.rows).selectinload(ETFHolding.constituent_instrument)
        )
        .where(ETFHoldingsSnapshot.etf_profile_id == profile.id)
        .order_by(ETFHoldingsSnapshot.composition_date.asc(), ETFHoldingsSnapshot.id.asc())
    )
    if start_date is not None:
        stmt = stmt.where(ETFHoldingsSnapshot.composition_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(ETFHoldingsSnapshot.composition_date <= end_date)
    snapshots = (await db.execute(stmt)).scalars().all()
    if not snapshots:
        return ETFHoldingsWeightEvolutionOut(
            etf_symbol=instrument.symbol,
            etf_name=instrument.name or instrument.symbol,
            snapshot_count=0,
            from_date=None,
            to_date=None,
            series=[],
        )

    labels: dict[str, tuple[str, str]] = {}
    points_by_key: dict[str, list[ETFHoldingsWeightEvolutionPointOut]] = defaultdict(list)
    for snapshot in snapshots:
        for row in snapshot.rows:
            key = _holding_identity_key(row)
            labels[key] = _holding_label(row)
            points_by_key[key].append(
                ETFHoldingsWeightEvolutionPointOut(
                    snapshot_id=snapshot.id,
                    composition_date=snapshot.composition_date,
                    weight=row.weight,
                    shares=row.shares,
                    market_value=row.market_value,
                )
            )

    series: list[ETFHoldingsWeightEvolutionSeriesOut] = []
    for key, points in points_by_key.items():
        weights = [point.weight for point in points if point.weight is not None]
        first_weight = points[0].weight
        last_weight = points[-1].weight
        weight_delta = None
        if first_weight is not None or last_weight is not None:
            weight_delta = (last_weight or Decimal("0")) - (first_weight or Decimal("0"))
        symbol, name = labels[key]
        series.append(
            ETFHoldingsWeightEvolutionSeriesOut(
                key=key,
                symbol=symbol,
                name=name,
                first_weight=first_weight,
                last_weight=last_weight,
                weight_delta=weight_delta,
                min_weight=min(weights) if weights else None,
                max_weight=max(weights) if weights else None,
                observation_count=len(points),
                points=points,
            )
        )

    series.sort(
        key=lambda row: (
            -abs(float(row.weight_delta or Decimal("0"))),
            -row.observation_count,
            row.symbol,
            row.name,
        )
    )

    return ETFHoldingsWeightEvolutionOut(
        etf_symbol=instrument.symbol,
        etf_name=instrument.name or instrument.symbol,
        snapshot_count=len(snapshots),
        from_date=snapshots[0].composition_date,
        to_date=snapshots[-1].composition_date,
        series=series[:limit],
    )


async def coverage_summary(
    db: AsyncSession,
    *,
    etf_symbols: list[str],
    etf_instrument_ids: list[int],
    start_date: date,
    end_date: date,
) -> ETFHoldingsCoverageSummary:
    targets: list[Instrument | str] = []
    seen: set[int] = set()
    for instrument_id in etf_instrument_ids:
        instrument = await db.get(Instrument, instrument_id)
        if instrument is not None and instrument.id not in seen:
            targets.append(instrument)
            seen.add(instrument.id)
    for symbol in etf_symbols:
        instrument = await _load_instrument_by_symbol_or_id(db, symbol)
        if instrument is not None and instrument.id not in seen:
            targets.append(instrument)
            seen.add(instrument.id)
        elif instrument is None:
            targets.append(symbol.strip().upper())

    rows: list[ETFHoldingsCoverageRow] = []
    for target in targets:
        if isinstance(target, str):
            rows.append(
                ETFHoldingsCoverageRow(
                    instrument_id=None,
                    symbol=target,
                    name=target,
                    requested_start=start_date,
                    requested_end=end_date,
                    snapshot_count=0,
                    status="missing",
                    status_label="Unknown ETF",
                    notes=["No local instrument/profile could be resolved for this ETF symbol."],
                )
            )
            continue
        instrument = target
        profile = await get_etf_profile_for_instrument(db, instrument.id)
        if profile is None:
            rows.append(
                ETFHoldingsCoverageRow(
                    instrument_id=instrument.id,
                    symbol=instrument.symbol,
                    name=instrument.name,
                    requested_start=start_date,
                    requested_end=end_date,
                    snapshot_count=0,
                    status="missing",
                    status_label="Missing holdings profile",
                    notes=["No ETF holdings profile exists for this instrument."],
                )
            )
            continue
        snapshots = (
            (
                await db.execute(
                    _apply_snapshot_visibility(
                        select(ETFHoldingsSnapshot).where(
                            ETFHoldingsSnapshot.etf_profile_id == profile.id
                        )
                    ).order_by(ETFHoldingsSnapshot.composition_date.asc())
                )
            )
            .scalars()
            .all()
        )
        if not snapshots:
            rows.append(
                ETFHoldingsCoverageRow(
                    instrument_id=instrument.id,
                    symbol=instrument.symbol,
                    name=instrument.name,
                    requested_start=start_date,
                    requested_end=end_date,
                    snapshot_count=0,
                    status="none",
                    status_label="No holdings snapshots",
                    notes=["The ETF is known, but no holdings snapshots are stored yet."],
                )
            )
            continue
        first = snapshots[0].composition_date
        last = snapshots[-1].composition_date
        qualities = sorted({snapshot.source_quality for snapshot in snapshots})
        overlaps_requested_range = first <= end_date and last >= start_date
        brackets_requested_range = first <= start_date and last >= end_date
        if brackets_requested_range:
            status = "full"
            label = "Requested range has boundary coverage"
        elif overlaps_requested_range:
            status = "partial"
            label = "Partial requested-range coverage"
        else:
            status = "none"
            label = "No requested-range coverage"
        notes: list[str] = []
        if first > start_date:
            notes.append("Holdings history starts after the requested range begins.")
        if last < end_date:
            notes.append("Holdings history ends before the requested range ends.")
        if status == "full":
            notes.append("At least one snapshot brackets both ends of the requested range.")
        rows.append(
            ETFHoldingsCoverageRow(
                instrument_id=instrument.id,
                symbol=instrument.symbol,
                name=instrument.name,
                requested_start=start_date,
                requested_end=end_date,
                first_snapshot_date=first,
                last_snapshot_date=last,
                snapshot_count=len(snapshots),
                status=status,
                status_label=label,
                source_quality_levels=qualities,
                notes=notes,
            )
        )

    counts = defaultdict(int)
    for row in rows:
        counts[row.status] += 1
    return ETFHoldingsCoverageSummary(
        requested_start=start_date,
        requested_end=end_date,
        total=len(rows),
        full=counts["full"],
        partial=counts["partial"],
        none=counts["none"],
        missing=counts["missing"],
        rows=rows,
    )
