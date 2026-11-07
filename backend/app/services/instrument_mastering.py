from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_class import AssetClass, InstrumentType
from app.models.instrument import EquityDetail, ForexDetail, FutureDetail, Instrument
from app.models.instrument_identity import (
    InstrumentIdentifier,
    InstrumentIdentifierType,
    InstrumentProviderSymbol,
)
from app.models.instrument_stats import InstrumentStats
from app.models.market_data_foundation import Issuer
from app.models.provider_observation import InstrumentProfileSnapshot
from app.models.provider_runtime import ProviderCapability
from app.providers import ensure_data_source, provider_symbol_for_instrument
from app.providers.base import IdentifierRecord, InstrumentProfile
from app.services.exchange_catalog import (
    coerce_listing_lifecycle_at,
    normalize_exchange_mic,
    upsert_instrument_listing,
)
from app.services.market_data_identity import apply_domain_identity
from app.services.provider_observations import store_identifier_snapshot
from app.services.provider_runtime import execute_provider_call, resolve_provider_chain

TYPE_MAP: dict[str, tuple[str, str]] = {
    "EQUITY": ("Equity", "Stock"),
    "ETF": ("Equity", "ETF"),
    "ETN": ("Exchange Traded Product", "ETN"),
    # Massive's ETV is an exchange-traded vehicle category, not proof that the
    # instrument is specifically an ETF or an ETN.
    "ETV": ("Exchange Traded Product", "Exchange Traded Vehicle"),
    "MUTUALFUND": ("Equity", "Mutual Fund"),
    "FUTURE": ("Commodity", "Future"),
    "OPTION": ("Derivative", "Option"),
    "CURRENCY": ("Currency", "Forex Pair"),
    "CRYPTOCURRENCY": ("Cryptocurrency", "Crypto Spot"),
    "INDEX": ("Index", "Index"),
    "UNCLASSIFIED": ("Unclassified", "Unclassified"),
}


def instrument_type_for_quote_type(
    quote_type: str | None, *, missing_default: str = "EQUITY"
) -> tuple[str, str, str]:
    """Return the persisted taxonomy and normalized source type code.

    Missing metadata retains the historical equity default. An explicit but
    unsupported code is kept distinct as Unclassified rather than silently
    being promoted to Stock.
    """
    raw_code = str(quote_type or "").strip().upper()
    normalized_code = raw_code or missing_default
    if normalized_code in {"CS", "COMMON_STOCK", "COMMON STOCK", "STOCK", "EQUITIES"}:
        normalized_code = "EQUITY"
    if normalized_code in TYPE_MAP:
        asset_class, type_name = TYPE_MAP[normalized_code]
        return asset_class, type_name, normalized_code
    return "Unclassified", "Unclassified", normalized_code


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _provenance_entry(
    *,
    source: str,
    fetched_at: datetime,
    observed_at: datetime | None = None,
    provider_symbol: str | None = None,
    selection_reason: str | None = None,
    quality_score: float | None = None,
    note: str | None = None,
    classification_system: str | None = None,
    reconciled_at: datetime | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "source": source,
        "fetched_at": fetched_at.isoformat(),
        "observed_at": (observed_at or fetched_at).isoformat(),
    }
    if provider_symbol:
        entry["provider_symbol"] = provider_symbol
    if selection_reason:
        entry["selection_reason"] = selection_reason
    if quality_score is not None:
        entry["quality_score"] = quality_score
    if note:
        entry["note"] = note
    if classification_system:
        entry["classification_system"] = classification_system
    if reconciled_at:
        entry["reconciled_at"] = reconciled_at.isoformat()
    return entry


def _mark_field_provenance(
    target: Any,
    field_name: str,
    *,
    source: str,
    fetched_at: datetime,
    observed_at: datetime | None = None,
    provider_symbol: str | None = None,
    selection_reason: str | None = None,
    quality_score: float | None = None,
    note: str | None = None,
    classification_system: str | None = None,
    reconciled_at: datetime | None = None,
) -> None:
    provenance = dict(getattr(target, "field_provenance", None) or {})
    provenance[field_name] = _provenance_entry(
        source=source,
        fetched_at=fetched_at,
        observed_at=observed_at,
        provider_symbol=provider_symbol,
        selection_reason=selection_reason,
        quality_score=quality_score,
        note=note,
        classification_system=classification_system,
        reconciled_at=reconciled_at,
    )
    setattr(target, "field_provenance", provenance)


_CURRENCY_CODE_RE = re.compile(r"^[A-Z]{3}$")


def _normalize_currency_code(value: str | None) -> str | None:
    text = str(value or "").strip().upper()
    if _CURRENCY_CODE_RE.fullmatch(text):
        return text
    return None


def _utc_ordering_value(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def build_profile_snapshot_payload(profile: InstrumentProfile) -> dict[str, Any]:
    return {
        "provider": profile.provider,
        "symbol": profile.symbol,
        "canonical_symbol": profile.canonical_symbol,
        "name": profile.name,
        "description": profile.description,
        "currency": profile.currency,
        "quote_type": profile.quote_type,
        "exchange": profile.exchange,
        "identifiers": [
            {
                "identifier_type": record.identifier_type,
                "identifier_value": record.identifier_value,
                "is_primary": record.is_primary,
                "source": record.source,
                "extra_data": record.extra_data,
            }
            for record in profile.identifiers
        ],
        "listings": [
            {
                "provider_symbol": listing.provider_symbol,
                "exchange_code": listing.exchange_code,
                "currency": listing.currency,
                "provider_instrument_type": listing.provider_instrument_type,
                "is_primary": listing.is_primary,
                "effective_at": listing.effective_at.isoformat() if listing.effective_at else None,
                "known_at": listing.known_at.isoformat() if listing.known_at else None,
                "delisted_at": listing.delisted_at.isoformat() if listing.delisted_at else None,
                "extra_data": listing.extra_data,
            }
            for listing in profile.listings
        ],
        "raw_payload": profile.raw_payload or {},
        "extra": profile.extra or {},
    }


def _payload_hash(payload: dict[str, Any]) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def store_profile_snapshot(
    db: AsyncSession,
    instrument: Instrument,
    profile: InstrumentProfile,
    *,
    observed_at: datetime | None = None,
    fetched_at: datetime | None = None,
) -> InstrumentProfileSnapshot:
    observed_at = observed_at or _now_utc()
    fetched_at = fetched_at or observed_at
    payload = build_profile_snapshot_payload(profile)
    profile_hash = _payload_hash(payload)
    data_source = await ensure_data_source(db, profile.provider)
    snapshot = InstrumentProfileSnapshot(
        instrument_id=instrument.id,
        data_source_id=data_source.id,
        provider_symbol=profile.symbol,
        observed_at=observed_at,
        fetched_at=fetched_at,
        profile_hash=profile_hash,
        payload=payload,
    )
    db.add(snapshot)
    await db.flush()
    return snapshot


def _value_from_snapshot(payload: dict[str, Any], field_name: str) -> Any:
    extra = payload.get("extra") or {}
    extra = extra if isinstance(extra, dict) else {}
    has_massive_sic_fallback = (
        str(payload.get("provider") or "").strip().lower() == "massive"
        and not str(extra.get("industry") or "").strip()
        and str(extra.get("sic_code") or "").strip()
        and str(extra.get("sic_description") or "").strip()
    )
    if (
        field_name == "classification_system"
        and has_massive_sic_fallback
        and not str(payload.get("industry") or "").strip()
    ):
        return "SEC_SIC"
    if field_name in payload:
        return payload.get(field_name)
    if field_name in extra:
        return extra.get(field_name)
    if has_massive_sic_fallback and field_name == "industry":
        return extra.get("sic_description")
    return None


async def reconcile_instrument_profile(
    db: AsyncSession, instrument: Instrument
) -> InstrumentProfile | None:
    snapshots = (
        (
            await db.execute(
                select(InstrumentProfileSnapshot)
                .where(InstrumentProfileSnapshot.instrument_id == instrument.id)
                .order_by(InstrumentProfileSnapshot.observed_at.desc())
            )
        )
        .scalars()
        .all()
    )
    if not snapshots:
        return None

    provider_scores = {
        resolved.provider_name: float(resolved.policy.effective_score)
        for resolved in await resolve_provider_chain(db, ProviderCapability.INSTRUMENT_METADATA)
    }

    def pick_field(field_name: str, default: Any = None):
        candidates: list[tuple[float, datetime, Any]] = []
        for snapshot in snapshots:
            value = _value_from_snapshot(snapshot.payload, field_name)
            if value is None or value == "":
                continue
            score = provider_scores.get(snapshot.payload.get("provider", ""), 0.0)
            candidates.append((score, _utc_ordering_value(snapshot.observed_at), value))
        if not candidates:
            return default
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return candidates[0][2]

    industry_snapshot = max(
        (
            snapshot
            for snapshot in snapshots
            if _value_from_snapshot(snapshot.payload, "industry") not in (None, "")
        ),
        key=lambda snapshot: (
            provider_scores.get(snapshot.payload.get("provider", ""), 0.0),
            _utc_ordering_value(snapshot.observed_at),
        ),
        default=None,
    )
    industry_evidence_payload = (
        (industry_snapshot.payload.get("extra") or {}).get("industry_evidence")
        if industry_snapshot is not None
        else None
    )
    industry_evidence_payload = (
        industry_evidence_payload if isinstance(industry_evidence_payload, dict) else {}
    )
    industry_snapshot_provider = (
        str(industry_snapshot.payload.get("provider") or "unknown")
        if industry_snapshot is not None
        else "unknown"
    )
    industry_snapshot_extra = (
        (industry_snapshot.payload.get("extra") or {}) if industry_snapshot is not None else {}
    )
    industry_snapshot_extra = (
        industry_snapshot_extra if isinstance(industry_snapshot_extra, dict) else {}
    )
    sic_description = str(industry_snapshot_extra.get("sic_description") or "").strip()
    sic_code = str(industry_snapshot_extra.get("sic_code") or "").strip()
    industry_value = str(industry_snapshot_extra.get("industry") or "").strip()
    has_massive_sic_evidence = (
        industry_snapshot_provider.strip().lower() == "massive"
        and bool(sic_code and sic_description)
        and (not industry_value or industry_value == sic_description)
    )
    industry_evidence_matches_snapshot = (
        industry_snapshot_provider.strip().lower() == "massive"
        and str(industry_evidence_payload.get("provider") or "massive").strip().lower() == "massive"
        and industry_evidence_payload.get("source_field") == "sic_description"
        and has_massive_sic_evidence
    )
    industry_source_field = (
        "sic_description"
        if industry_evidence_matches_snapshot or (has_massive_sic_evidence and not industry_value)
        else "industry"
    )
    industry_classification_system = (
        "SEC_SIC"
        if has_massive_sic_evidence
        else _value_from_snapshot(industry_snapshot.payload, "classification_system")
        if industry_snapshot is not None
        else None
    )

    classification_snapshot = max(
        (
            snapshot
            for snapshot in snapshots
            if _value_from_snapshot(snapshot.payload, "quote_type") not in (None, "")
        ),
        key=lambda snapshot: (
            provider_scores.get(snapshot.payload.get("provider", ""), 0.0),
            _utc_ordering_value(snapshot.observed_at),
        ),
        default=None,
    )

    latest = snapshots[0].payload
    identifiers = []
    seen_identifiers: set[tuple[str, str]] = set()
    listings = []
    seen_listings: set[tuple[str, str | None]] = set()
    for snapshot in snapshots:
        for item in snapshot.payload.get("identifiers") or []:
            key = (str(item.get("identifier_type")), str(item.get("identifier_value")))
            if key in seen_identifiers:
                continue
            seen_identifiers.add(key)
            identifiers.append(
                IdentifierRecord(
                    identifier_type=item.get("identifier_type") or "internal",
                    identifier_value=item.get("identifier_value") or "",
                    is_primary=bool(item.get("is_primary")),
                    source=item.get("source"),
                    extra_data=item.get("extra_data"),
                    raw_payload=item.get("raw_payload"),
                )
            )
        for item in snapshot.payload.get("listings") or []:
            key = (str(item.get("provider_symbol")), item.get("exchange_code"))
            if key in seen_listings:
                continue
            seen_listings.add(key)
            from app.providers.base import ListingRecord

            listings.append(
                ListingRecord(
                    provider_symbol=item.get("provider_symbol") or "",
                    exchange_code=item.get("exchange_code"),
                    currency=item.get("currency"),
                    provider_instrument_type=item.get("provider_instrument_type"),
                    is_primary=bool(item.get("is_primary")),
                    extra_data=item.get("extra_data"),
                )
            )

    return InstrumentProfile(
        provider=latest.get("provider") or "unknown",
        symbol=pick_field("symbol", instrument.symbol),
        canonical_symbol=pick_field("canonical_symbol", instrument.symbol),
        name=pick_field("name", instrument.name),
        description=pick_field("description", instrument.description),
        currency=pick_field("currency", instrument.currency),
        quote_type=pick_field("quote_type", None),
        exchange=pick_field("exchange", None),
        identifiers=identifiers,
        listings=listings,
        raw_payload=latest.get("raw_payload") or {},
        extra={
            field: pick_field(field, None)
            for field in [
                "sector",
                "industry",
                "country",
                "website",
                "market_cap",
                "fifty_two_week_high",
                "fifty_two_week_low",
                "average_volume",
                "trailing_pe",
                "forward_pe",
                "beta",
                "dividend_yield",
                "employees",
                "regular_market_price",
                "current_price",
                "previous_close",
                "classification_system",
            ]
        }
        | (
            {
                "industry_evidence": {
                    "provider": industry_snapshot.payload.get("provider") or "unknown",
                    "source_field": industry_source_field,
                    "classification_system": industry_classification_system,
                    "observed_at": industry_snapshot.observed_at.isoformat(),
                    "fetched_at": industry_snapshot.fetched_at.isoformat()
                    if industry_snapshot.fetched_at
                    else None,
                    "sic_code": (industry_snapshot.payload.get("extra") or {}).get("sic_code"),
                }
            }
            if industry_snapshot is not None
            else {}
        )
        | (
            {
                "classification_evidence": {
                    "provider": classification_snapshot.payload.get("provider") or "unknown",
                    "quote_type": _value_from_snapshot(
                        classification_snapshot.payload, "quote_type"
                    ),
                    "classification_system": _value_from_snapshot(
                        classification_snapshot.payload, "classification_system"
                    ),
                    "observed_at": classification_snapshot.observed_at.isoformat(),
                    "fetched_at": classification_snapshot.fetched_at.isoformat(),
                }
            }
            if classification_snapshot is not None
            else {}
        ),
    )


async def ingest_provider_profile(
    db: AsyncSession,
    profile: InstrumentProfile,
    *,
    instrument: Instrument | None = None,
    allow_external_identifier: bool = True,
) -> Instrument:
    instrument = await apply_profile_to_instrument(
        db,
        profile,
        instrument=instrument,
        allow_external_identifier=allow_external_identifier,
    )
    await store_profile_snapshot(db, instrument, profile)
    merged_profile = await reconcile_instrument_profile(db, instrument)
    if merged_profile is not None:
        instrument = await apply_profile_to_instrument(
            db,
            merged_profile,
            instrument=instrument,
            allow_external_identifier=allow_external_identifier,
        )
    return instrument


def _cap_tier(cap: float | None) -> str | None:
    if not cap:
        return None
    if cap >= 200_000_000_000:
        return "mega"
    if cap >= 10_000_000_000:
        return "large"
    if cap >= 2_000_000_000:
        return "mid"
    if cap >= 300_000_000:
        return "small"
    if cap >= 50_000_000:
        return "micro"
    return "nano"


def _parse_forex_pair(symbol: str) -> tuple[str, str] | None:
    normalized = symbol.upper().replace("=X", "").replace("/", "")
    if len(normalized) == 6:
        return normalized[:3], normalized[3:]
    return None


def _identifier_enum(identifier_type: str) -> InstrumentIdentifierType:
    normalized = identifier_type.strip().upper()
    try:
        return InstrumentIdentifierType[normalized]
    except KeyError:
        return InstrumentIdentifierType.INTERNAL


def _normalize_cik(value: Any) -> str | None:
    digits = "".join(character for character in str(value or "") if character.isdigit())
    if not digits or len(digits) > 10:
        return None
    return digits.zfill(10)


async def ensure_profile_issuer(
    db: AsyncSession,
    instrument: Instrument,
    profile: InstrumentProfile,
) -> None:
    """Attach SEC CIK evidence to the issuer domain, never the security key."""

    cik = _normalize_cik((profile.extra or {}).get("cik"))
    if cik is None:
        return

    issuer = (await db.execute(select(Issuer).where(Issuer.cik == cik))).scalar_one_or_none()
    if issuer is None:
        issuer = (
            await db.execute(select(Issuer).where(Issuer.domain_key == f"cik:{cik}"))
        ).scalar_one_or_none()
    if issuer is None:
        issuer = Issuer(
            domain_key=f"cik:{cik}",
            legal_name=profile.name or profile.canonical_symbol or profile.symbol,
            cik=cik,
            country_code="US",
            provenance={
                "source": profile.provider,
                "provider_symbol": profile.symbol,
                "observed_at": _now_utc().isoformat(),
            },
        )
        db.add(issuer)
        await db.flush()

    # A security can be linked to one issuer, but an issuer can own many
    # share classes/listings. Never silently reassign an already-linked
    # security when conflicting provider evidence arrives.
    if instrument.issuer_id is None or instrument.issuer_id == issuer.id:
        instrument.issuer_id = issuer.id


async def ensure_instrument_type(
    db: AsyncSession,
    asset_class_name: str,
    type_name: str,
) -> int:
    asset_class = (
        await db.execute(select(AssetClass).where(AssetClass.name == asset_class_name))
    ).scalar_one_or_none()
    if asset_class is None:
        asset_class = AssetClass(name=asset_class_name, description=asset_class_name)
        db.add(asset_class)
        await db.flush()

    instrument_type = (
        await db.execute(
            select(InstrumentType).where(
                InstrumentType.asset_class_id == asset_class.id,
                InstrumentType.name == type_name,
            )
        )
    ).scalar_one_or_none()
    if instrument_type is None:
        instrument_type = InstrumentType(
            asset_class_id=asset_class.id,
            name=type_name,
            description=type_name,
        )
        db.add(instrument_type)
        await db.flush()

    return instrument_type.id


async def register_provider_symbol(
    db: AsyncSession,
    instrument: Instrument,
    provider_name: str,
    provider_symbol: str,
    *,
    provider_exchange_code: str | None = None,
    provider_instrument_type: str | None = None,
    currency: str | None = None,
    is_primary: bool = False,
    extra_data: dict[str, Any] | None = None,
    reactivate_existing: bool = True,
    effective_at: datetime | None = None,
    known_at: datetime | None = None,
    delisted_at: datetime | None = None,
) -> None:
    data_source = await ensure_data_source(db, provider_name)
    provider_symbol_filters = [
        InstrumentProviderSymbol.instrument_id == instrument.id,
        InstrumentProviderSymbol.data_source_id == data_source.id,
        InstrumentProviderSymbol.provider_symbol == provider_symbol,
    ]
    if provider_exchange_code is not None:
        provider_symbol_filters.append(
            InstrumentProviderSymbol.provider_exchange_code == provider_exchange_code
        )
    existing = (
        await db.execute(
            select(InstrumentProviderSymbol)
            .where(*provider_symbol_filters)
            .order_by(
                InstrumentProviderSymbol.is_primary.desc(),
                InstrumentProviderSymbol.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = InstrumentProviderSymbol(
            instrument_id=instrument.id,
            data_source_id=data_source.id,
            provider_symbol=provider_symbol,
        )
        db.add(existing)

    existing.provider_exchange_code = provider_exchange_code or existing.provider_exchange_code
    existing.provider_instrument_type = (
        provider_instrument_type or existing.provider_instrument_type
    )
    if delisted_at is not None:
        existing.is_active = False
        existing.retired_at = delisted_at
    elif reactivate_existing:
        existing.is_active = True
        # A provider can re-list or restore a symbol after a prior observed
        # retirement.  The append-only universe/lifecycle observations retain
        # the earlier retirement evidence; this binding represents the
        # currently active association again.
        existing.retired_at = None
    if effective_at is not None and existing.effective_at is None:
        existing.effective_at = effective_at
    if known_at is not None and existing.known_at is None:
        existing.known_at = known_at
    existing.is_primary = is_primary or existing.is_primary
    existing.extra_data = {
        **(existing.extra_data or {}),
        "provider_name": provider_name,
        **(extra_data or {}),
    } or None

    await upsert_instrument_listing(
        db,
        instrument,
        provider_symbol,
        exchange_code=provider_exchange_code,
        currency=currency,
        is_primary=is_primary,
        reactivate_existing=reactivate_existing,
        effective_at=effective_at,
        known_at=known_at,
        delisted_at=delisted_at,
        source=provider_name,
        provenance={"provider_instrument_type": provider_instrument_type},
    )


async def register_identifier(
    db: AsyncSession,
    instrument: Instrument,
    provider_name: str,
    identifier: IdentifierRecord,
) -> None:
    # SEC CIK identifies the issuer/legal entity, not a tradeable security.
    # Profile ingestion records it on ``Issuer``; legacy instrument rows may
    # still contain CIK records for lookup compatibility, but new writes must
    # never create another security-level CIK key.
    if _identifier_enum(identifier.identifier_type) == InstrumentIdentifierType.CIK:
        return

    data_source = await ensure_data_source(db, provider_name)
    existing = (
        await db.execute(
            select(InstrumentIdentifier).where(
                InstrumentIdentifier.identifier_type
                == _identifier_enum(identifier.identifier_type),
                InstrumentIdentifier.identifier_value == identifier.identifier_value,
            )
        )
    ).scalar_one_or_none()

    if existing is not None and existing.instrument_id != instrument.id:
        if provider_name != "etf_holdings_internal" or existing.data_source_id != data_source.id:
            return
        previous_instrument = (
            await db.execute(select(Instrument).where(Instrument.id == existing.instrument_id))
        ).scalar_one_or_none()
        existing.instrument_id = instrument.id
        if (
            previous_instrument is not None
            and existing.identifier_type == InstrumentIdentifierType.ISIN
            and previous_instrument.isin == existing.identifier_value
        ):
            previous_instrument.isin = None

    if existing is None:
        existing = InstrumentIdentifier(
            instrument_id=instrument.id,
            data_source_id=data_source.id,
            identifier_type=_identifier_enum(identifier.identifier_type),
            identifier_value=identifier.identifier_value,
        )
        db.add(existing)

    existing.is_active = True
    existing.is_primary = identifier.is_primary or existing.is_primary
    existing.extra_data = {
        **(existing.extra_data or {}),
        **(identifier.extra_data or {}),
    } or None

    if existing.identifier_type == InstrumentIdentifierType.ISIN:
        instrument.isin = identifier.identifier_value
        _mark_field_provenance(
            instrument,
            "isin",
            source=provider_name,
            fetched_at=_now_utc(),
            note=existing.identifier_type.value,
        )

    if identifier.is_primary or instrument.primary_identifier_value is None:
        instrument.primary_identifier_type = existing.identifier_type.value
        instrument.primary_identifier_value = identifier.identifier_value
        _mark_field_provenance(
            instrument,
            "primary_identifier_type",
            source=provider_name,
            fetched_at=_now_utc(),
            note=existing.identifier_type.value,
        )
        _mark_field_provenance(
            instrument,
            "primary_identifier_value",
            source=provider_name,
            fetched_at=_now_utc(),
            note=existing.identifier_type.value,
        )


async def ensure_internal_identifier(
    db: AsyncSession,
    instrument: Instrument,
) -> None:
    internal_value = f"instrument:{instrument.id}"
    existing_rows = (
        (
            await db.execute(
                select(InstrumentIdentifier).where(
                    InstrumentIdentifier.instrument_id == instrument.id,
                    InstrumentIdentifier.identifier_type == InstrumentIdentifierType.INTERNAL,
                )
            )
        )
        .scalars()
        .all()
    )
    existing = next(
        (row for row in existing_rows if row.identifier_value == internal_value),
        existing_rows[0] if existing_rows else None,
    )
    if existing is None:
        existing = InstrumentIdentifier(
            instrument_id=instrument.id,
            data_source_id=None,
            identifier_type=InstrumentIdentifierType.INTERNAL,
            identifier_value=internal_value,
            is_primary=instrument.primary_identifier_value is None,
            is_active=True,
        )
        db.add(existing)
    else:
        existing.identifier_value = internal_value
        existing.is_active = True
        if instrument.primary_identifier_value is None:
            existing.is_primary = True

        for duplicate in existing_rows:
            if duplicate.id == existing.id:
                continue
            duplicate.is_active = False
            duplicate.is_primary = False
            if duplicate.identifier_value == internal_value:
                continue
            duplicate.identifier_value = f"{duplicate.identifier_value}__superseded__{duplicate.id}"

    if instrument.primary_identifier_value is None:
        instrument.primary_identifier_type = InstrumentIdentifierType.INTERNAL.value
        instrument.primary_identifier_value = internal_value


def has_external_identifier(instrument: Instrument) -> bool:
    return bool(
        instrument.primary_identifier_value
        and instrument.primary_identifier_type
        and instrument.primary_identifier_type != InstrumentIdentifierType.INTERNAL.value
    )


async def ensure_external_identifier(
    db: AsyncSession,
    instrument: Instrument,
) -> bool:
    if has_external_identifier(instrument):
        if not instrument.domain_key:
            await apply_domain_identity(
                db,
                instrument,
                provider_name="existing_identifier",
                provider_symbol=instrument.symbol,
                candidate_payload={
                    "identifier_type": instrument.primary_identifier_type,
                    "identifier_value": instrument.primary_identifier_value,
                },
            )
        return False

    def _symbol_for_provider(provider_name: str) -> str:
        if "provider_symbols" in instrument.__dict__ or "listings" in instrument.__dict__:
            return provider_symbol_for_instrument(instrument, provider_name)
        return instrument.symbol

    try:
        execution = await execute_provider_call(
            db,
            ProviderCapability.INSTRUMENT_IDENTIFIERS,
            "fetch_stable_identifiers",
            instrument_id=instrument.id,
            provider_symbol=instrument.symbol,
            usage_identity=_symbol_for_provider,
            invoke=lambda provider, _ignored_provider_symbol: provider.fetch_stable_identifiers(
                _symbol_for_provider(provider.name)
            ),
            response_items=lambda result: len(result),
            treat_empty_as_failure=False,
        )
    except Exception:
        return False

    identifiers = execution.result
    if not identifiers:
        return False
    provider_symbol = _symbol_for_provider(execution.provider_name)
    await store_identifier_snapshot(
        db,
        instrument_id=instrument.id,
        data_source_id=execution.data_source.id,
        provider_symbol=provider_symbol,
        identifiers=identifiers,
    )
    identifier_added = False
    for identifier in identifiers:
        await register_identifier(db, instrument, execution.provider_name, identifier)
        identifier_added = True
    await apply_domain_identity(
        db,
        instrument,
        provider_name=execution.provider_name,
        provider_symbol=provider_symbol,
        candidate_payload={
            "identifiers": [
                {
                    "identifier_type": item.identifier_type,
                    "identifier_value": item.identifier_value,
                    "source": item.source,
                }
                for item in identifiers
            ]
        },
    )
    if has_external_identifier(instrument):
        _mark_field_provenance(
            instrument,
            "primary_identifier_value",
            source=execution.provider_name,
            fetched_at=_now_utc(),
            provider_symbol=provider_symbol,
            note=instrument.primary_identifier_type,
        )
    return identifier_added


async def upsert_instrument_stats(
    db: AsyncSession,
    instrument: Instrument,
    extra: dict[str, Any],
    *,
    source: str,
    fetched_at: datetime,
    provider_symbol: str | None = None,
) -> None:
    stats_values = {
        "week52_high": extra.get("fifty_two_week_high"),
        "week52_low": extra.get("fifty_two_week_low"),
        "avg_volume_30d": extra.get("average_volume"),
        "pe_ratio": extra.get("trailing_pe") or extra.get("forward_pe"),
        "market_cap": extra.get("market_cap"),
        "beta": extra.get("beta"),
        "dividend_yield": extra.get("dividend_yield"),
    }
    if not any(value is not None for value in stats_values.values()):
        return

    stats = (
        await db.execute(
            select(InstrumentStats).where(InstrumentStats.instrument_id == instrument.id)
        )
    ).scalar_one_or_none()
    if stats is None:
        stats = InstrumentStats(instrument_id=instrument.id)
        db.add(stats)

    for attr, value in stats_values.items():
        if value is not None:
            setattr(stats, attr, value)
            _mark_field_provenance(
                stats,
                attr,
                source=source,
                fetched_at=fetched_at,
                provider_symbol=provider_symbol,
            )
    stats.computed_at = fetched_at


async def apply_profile_to_instrument(
    db: AsyncSession,
    profile: InstrumentProfile,
    *,
    instrument: Instrument | None = None,
    allow_external_identifier: bool = True,
) -> Instrument:
    asset_class_name, type_name, quote_type = instrument_type_for_quote_type(profile.quote_type)
    instrument_type_id = await ensure_instrument_type(db, asset_class_name, type_name)
    fetched_at = _now_utc()
    normalized_currency = _normalize_currency_code(profile.currency)

    if instrument is None:
        instrument = Instrument(
            symbol=profile.canonical_symbol,
            name=profile.name,
            description=profile.description,
            currency=normalized_currency,
            instrument_type_id=instrument_type_id,
            is_active=True,
        )
        db.add(instrument)
        await db.flush()
    else:
        instrument.symbol = profile.canonical_symbol
        instrument.name = profile.name or instrument.name
        instrument.description = profile.description or instrument.description
        instrument.currency = normalized_currency or instrument.currency
        # Incomplete profile refreshes must not erase a previously supported
        # classification. Explicit unknown source codes are represented as
        # Unclassified by instrument_type_for_quote_type().
        if profile.quote_type:
            instrument.instrument_type_id = instrument_type_id
        instrument.is_active = True

    if profile.canonical_symbol:
        _mark_field_provenance(
            instrument,
            "symbol",
            source=profile.provider,
            fetched_at=fetched_at,
            provider_symbol=profile.symbol,
        )
    if profile.name:
        _mark_field_provenance(
            instrument,
            "name",
            source=profile.provider,
            fetched_at=fetched_at,
            provider_symbol=profile.symbol,
        )
    if profile.description:
        _mark_field_provenance(
            instrument,
            "description",
            source=profile.provider,
            fetched_at=fetched_at,
            provider_symbol=profile.symbol,
        )
    if normalized_currency:
        _mark_field_provenance(
            instrument,
            "currency",
            source=profile.provider,
            fetched_at=fetched_at,
            provider_symbol=profile.symbol,
        )

    if profile.quote_type:
        classification_evidence = (profile.extra or {}).get("classification_evidence") or {}
        classification_observed_at = _retained_profile_datetime(
            classification_evidence.get("observed_at")
        )
        classification_fetched_at = _retained_profile_datetime(
            classification_evidence.get("fetched_at")
        )
        classification_source = str(classification_evidence.get("provider") or profile.provider)
        _mark_field_provenance(
            instrument,
            "instrument_type",
            source=classification_source,
            fetched_at=classification_fetched_at or fetched_at,
            observed_at=classification_observed_at or fetched_at,
            provider_symbol=profile.symbol,
            classification_system=(
                str(
                    classification_evidence.get("classification_system")
                    or (profile.extra or {}).get("classification_system")
                    or ""
                ).strip()
                or f"{classification_source}.quote_type"
            ),
            note=(
                f"provider_quote_type={quote_type}"
                + ("; reconciled_from_retained_profile" if classification_evidence else "")
            ),
            reconciled_at=_now_utc() if classification_evidence else None,
        )

    for listing in profile.listings or []:
        await register_provider_symbol(
            db,
            instrument,
            profile.provider,
            listing.provider_symbol,
            provider_exchange_code=listing.exchange_code,
            provider_instrument_type=listing.provider_instrument_type,
            currency=_normalize_currency_code(listing.currency) or normalized_currency,
            is_primary=listing.is_primary,
            extra_data=listing.extra_data,
            effective_at=listing.effective_at
            or coerce_listing_lifecycle_at((listing.extra_data or {}).get("effective_at")),
            known_at=listing.known_at
            or coerce_listing_lifecycle_at((listing.extra_data or {}).get("known_at"))
            or fetched_at,
            delisted_at=listing.delisted_at
            or coerce_listing_lifecycle_at((listing.extra_data or {}).get("delisted_at")),
        )

    if not profile.listings:
        await register_provider_symbol(
            db,
            instrument,
            profile.provider,
            profile.symbol,
            provider_exchange_code=profile.exchange,
            provider_instrument_type=quote_type,
            currency=normalized_currency,
            is_primary=True,
        )

    await ensure_profile_issuer(db, instrument, profile)

    for identifier in profile.identifiers:
        await register_identifier(db, instrument, profile.provider, identifier)

    await ensure_internal_identifier(db, instrument)
    if allow_external_identifier:
        await ensure_external_identifier(db, instrument)
        await apply_domain_identity(
            db,
            instrument,
            provider_name=profile.provider,
            provider_symbol=profile.symbol,
            exchange_mic=normalize_exchange_mic(profile.exchange),
            candidate_payload=build_profile_snapshot_payload(profile),
        )
    await upsert_instrument_stats(
        db,
        instrument,
        profile.extra,
        source=profile.provider,
        fetched_at=fetched_at,
        provider_symbol=profile.symbol,
    )

    if quote_type in {"EQUITY", "ETF", "MUTUALFUND", "INDEX"}:
        detail = (
            await db.execute(
                select(EquityDetail).where(EquityDetail.instrument_id == instrument.id)
            )
        ).scalar_one_or_none()
        if detail is None:
            detail = EquityDetail(instrument_id=instrument.id)
            db.add(detail)
        normalized_exchange = normalize_exchange_mic(profile.exchange)
        detail.sector = profile.extra.get("sector") or detail.sector
        detail.industry = profile.extra.get("industry") or detail.industry
        detail.country = profile.extra.get("country") or detail.country
        detail.exchange_mic = normalized_exchange or detail.exchange_mic
        detail.website = profile.extra.get("website") or detail.website
        detail.market_cap_tier = (
            _cap_tier(profile.extra.get("market_cap")) or detail.market_cap_tier
        )
        if profile.extra.get("employees") is not None:
            detail.employees = profile.extra["employees"]
        for field_name, value in [
            ("sector", profile.extra.get("sector")),
            ("industry", profile.extra.get("industry")),
            ("country", profile.extra.get("country")),
            ("exchange_mic", normalized_exchange),
            ("website", profile.extra.get("website")),
            ("market_cap_tier", _cap_tier(profile.extra.get("market_cap"))),
            ("employees", profile.extra.get("employees")),
        ]:
            if value is not None:
                industry_evidence = (
                    profile.extra.get("industry_evidence") if field_name == "industry" else None
                )
                evidence = industry_evidence if isinstance(industry_evidence, dict) else {}
                _mark_field_provenance(
                    detail,
                    field_name,
                    source=str(evidence.get("provider") or profile.provider),
                    fetched_at=(
                        _retained_profile_datetime(evidence.get("fetched_at")) or fetched_at
                    ),
                    observed_at=_retained_profile_datetime(evidence.get("observed_at")),
                    provider_symbol=profile.symbol,
                    classification_system=(
                        evidence.get("classification_system")
                        or profile.extra.get("classification_system")
                        if field_name in {"sector", "industry"}
                        else None
                    ),
                    note=(
                        f"source_field={evidence.get('source_field')};sic_code={evidence.get('sic_code')}"
                        if field_name == "industry"
                        and evidence.get("source_field") == "sic_description"
                        else None
                    ),
                )

    elif quote_type == "CURRENCY":
        pair = _parse_forex_pair(profile.canonical_symbol)
        if pair:
            detail = (
                await db.execute(
                    select(ForexDetail).where(ForexDetail.instrument_id == instrument.id)
                )
            ).scalar_one_or_none()
            if detail is None:
                detail = ForexDetail(
                    instrument_id=instrument.id,
                    base_currency=pair[0],
                    quote_currency=pair[1],
                )
                db.add(detail)
            for field_name, value in [
                ("base_currency", pair[0]),
                ("quote_currency", pair[1]),
            ]:
                _mark_field_provenance(
                    detail,
                    field_name,
                    source=profile.provider,
                    fetched_at=fetched_at,
                    provider_symbol=profile.symbol,
                )

    elif quote_type == "FUTURE":
        detail = (
            await db.execute(
                select(FutureDetail).where(FutureDetail.instrument_id == instrument.id)
            )
        ).scalar_one_or_none()
        if detail is None:
            detail = FutureDetail(instrument_id=instrument.id)
            db.add(detail)
        detail.underlying_name = profile.name or detail.underlying_name
        detail.is_continuous = profile.canonical_symbol.endswith("=F") or detail.is_continuous
        if profile.name:
            _mark_field_provenance(
                detail,
                "underlying_name",
                source=profile.provider,
                fetched_at=fetched_at,
                provider_symbol=profile.symbol,
            )
        if profile.canonical_symbol.endswith("=F"):
            _mark_field_provenance(
                detail,
                "is_continuous",
                source=profile.provider,
                fetched_at=fetched_at,
                provider_symbol=profile.symbol,
            )

    return instrument


async def reconcile_instrument_type_from_profile(
    db: AsyncSession,
    instrument: Instrument,
    profile: InstrumentProfile,
) -> bool:
    """Reconcile only the type from retained profile evidence.

    This deliberately leaves the instrument's canonical symbol, name,
    identifiers, issuer, listings, and domain identity untouched. It is used
    when a selected instrument is served from a fresh profile snapshot.
    """
    if not profile.quote_type:
        return False
    evidence = (profile.extra or {}).get("classification_evidence") or {}
    observed_at = _retained_profile_datetime(evidence.get("observed_at"))
    fetched_at = _retained_profile_datetime(evidence.get("fetched_at"))
    source = str(evidence.get("provider") or "").strip()
    if not source or observed_at is None or fetched_at is None:
        return False
    asset_class_name, type_name, quote_type = instrument_type_for_quote_type(profile.quote_type)
    type_id = await ensure_instrument_type(db, asset_class_name, type_name)
    changed = instrument.instrument_type_id != type_id
    instrument.instrument_type_id = type_id
    _mark_field_provenance(
        instrument,
        "instrument_type",
        source=source,
        fetched_at=fetched_at,
        observed_at=observed_at,
        provider_symbol=profile.symbol,
        classification_system=(
            str(evidence.get("classification_system") or "").strip() or f"{source}.quote_type"
        ),
        note=f"provider_quote_type={quote_type}; reconciled_from_retained_profile",
        reconciled_at=_now_utc(),
    )
    return changed


def _retained_profile_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
