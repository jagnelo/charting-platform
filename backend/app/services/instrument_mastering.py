from __future__ import annotations

import hashlib
import json
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
from app.models.provider_observation import InstrumentProfileSnapshot
from app.models.provider_runtime import ProviderCapability
from app.models.instrument_stats import InstrumentStats
from app.models.listing import InstrumentListing
from app.providers import ensure_data_source, provider_symbol_for_instrument
from app.providers.base import IdentifierRecord, InstrumentProfile
from app.services.provider_observations import store_identifier_snapshot
from app.services.provider_runtime import execute_provider_call, resolve_provider_chain

TYPE_MAP: dict[str, tuple[str, str]] = {
    "EQUITY": ("Equity", "Stock"),
    "ETF": ("Equity", "ETF"),
    "MUTUALFUND": ("Equity", "Mutual Fund"),
    "FUTURE": ("Commodity", "Future"),
    "OPTION": ("Derivative", "Option"),
    "CURRENCY": ("Currency", "Forex Pair"),
    "CRYPTOCURRENCY": ("Cryptocurrency", "Crypto Spot"),
    "INDEX": ("Index", "Index"),
}


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
    )
    setattr(target, "field_provenance", provenance)


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
    existing = (
        await db.execute(
            select(InstrumentProfileSnapshot).where(
                InstrumentProfileSnapshot.instrument_id == instrument.id,
                InstrumentProfileSnapshot.data_source_id == data_source.id,
                InstrumentProfileSnapshot.profile_hash == profile_hash,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.observed_at = observed_at
        existing.fetched_at = fetched_at
        existing.provider_symbol = profile.symbol
        existing.payload = payload
        return existing

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
    if field_name in payload:
        return payload.get(field_name)
    extra = payload.get("extra") or {}
    if field_name in extra:
        return extra.get(field_name)
    return None


async def reconcile_instrument_profile(db: AsyncSession, instrument: Instrument) -> InstrumentProfile | None:
    snapshots = (
        await db.execute(
            select(InstrumentProfileSnapshot).where(
                InstrumentProfileSnapshot.instrument_id == instrument.id
            ).order_by(InstrumentProfileSnapshot.observed_at.desc())
        )
    ).scalars().all()
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
            candidates.append((score, snapshot.observed_at, value))
        if not candidates:
            return default
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return candidates[0][2]

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
            ]
        },
    )


async def ingest_provider_profile(
    db: AsyncSession,
    profile: InstrumentProfile,
    *,
    instrument: Instrument | None = None,
) -> Instrument:
    instrument = await apply_profile_to_instrument(db, profile, instrument=instrument)
    await store_profile_snapshot(db, instrument, profile)
    merged_profile = await reconcile_instrument_profile(db, instrument)
    if merged_profile is not None:
        instrument = await apply_profile_to_instrument(db, merged_profile, instrument=instrument)
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
) -> None:
    data_source = await ensure_data_source(db, provider_name)
    existing = (
        await db.execute(
            select(InstrumentProviderSymbol).where(
                InstrumentProviderSymbol.instrument_id == instrument.id,
                InstrumentProviderSymbol.data_source_id == data_source.id,
                InstrumentProviderSymbol.provider_symbol == provider_symbol,
            )
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
    existing.provider_instrument_type = provider_instrument_type or existing.provider_instrument_type
    existing.is_active = True
    existing.is_primary = is_primary or existing.is_primary
    existing.extra_data = {
        **(existing.extra_data or {}),
        "provider_name": provider_name,
        **(extra_data or {}),
    } or None

    listing = (
        await db.execute(
            select(InstrumentListing).where(
                InstrumentListing.instrument_id == instrument.id,
                InstrumentListing.ticker == provider_symbol,
            )
        )
    ).scalar_one_or_none()
    if listing is None:
        db.add(
            InstrumentListing(
                instrument_id=instrument.id,
                ticker=provider_symbol,
                currency=currency,
                is_primary=is_primary,
                is_active=True,
            )
        )
    else:
        listing.currency = currency or listing.currency
        listing.is_active = True
        listing.is_primary = is_primary or listing.is_primary


async def register_identifier(
    db: AsyncSession,
    instrument: Instrument,
    provider_name: str,
    identifier: IdentifierRecord,
) -> None:
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
        return

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
    existing = (
        await db.execute(
            select(InstrumentIdentifier).where(
                InstrumentIdentifier.instrument_id == instrument.id,
                InstrumentIdentifier.identifier_type == InstrumentIdentifierType.INTERNAL,
            )
        )
    ).scalar_one_or_none()
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
) -> Instrument:
    quote_type = (profile.quote_type or "EQUITY").upper()
    asset_class_name, type_name = TYPE_MAP.get(quote_type, ("Equity", "Stock"))
    instrument_type_id = await ensure_instrument_type(db, asset_class_name, type_name)
    fetched_at = _now_utc()

    if instrument is None:
        instrument = Instrument(
            symbol=profile.canonical_symbol,
            name=profile.name,
            description=profile.description,
            currency=profile.currency,
            instrument_type_id=instrument_type_id,
            is_active=True,
        )
        db.add(instrument)
        await db.flush()
    else:
        instrument.symbol = profile.canonical_symbol
        instrument.name = profile.name or instrument.name
        instrument.description = profile.description or instrument.description
        instrument.currency = profile.currency or instrument.currency
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
    if profile.currency:
        _mark_field_provenance(
            instrument,
            "currency",
            source=profile.provider,
            fetched_at=fetched_at,
            provider_symbol=profile.symbol,
        )

    for listing in profile.listings or []:
        await register_provider_symbol(
            db,
            instrument,
            profile.provider,
            listing.provider_symbol,
            provider_exchange_code=listing.exchange_code,
            provider_instrument_type=listing.provider_instrument_type,
            currency=listing.currency or profile.currency,
            is_primary=listing.is_primary,
            extra_data=listing.extra_data,
        )

    if not profile.listings:
        await register_provider_symbol(
            db,
            instrument,
            profile.provider,
            profile.symbol,
            provider_exchange_code=profile.exchange,
            provider_instrument_type=quote_type,
            currency=profile.currency,
            is_primary=True,
        )

    for identifier in profile.identifiers:
        await register_identifier(db, instrument, profile.provider, identifier)

    await ensure_internal_identifier(db, instrument)
    await ensure_external_identifier(db, instrument)
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
            await db.execute(select(EquityDetail).where(EquityDetail.instrument_id == instrument.id))
        ).scalar_one_or_none()
        if detail is None:
            detail = EquityDetail(instrument_id=instrument.id)
            db.add(detail)
        detail.sector = profile.extra.get("sector") or detail.sector
        detail.industry = profile.extra.get("industry") or detail.industry
        detail.country = profile.extra.get("country") or detail.country
        detail.exchange_mic = profile.exchange or detail.exchange_mic
        detail.website = profile.extra.get("website") or detail.website
        detail.market_cap_tier = _cap_tier(profile.extra.get("market_cap")) or detail.market_cap_tier
        if profile.extra.get("employees") is not None:
            detail.employees = profile.extra["employees"]
        for field_name, value in [
            ("sector", profile.extra.get("sector")),
            ("industry", profile.extra.get("industry")),
            ("country", profile.extra.get("country")),
            ("exchange_mic", profile.exchange),
            ("website", profile.extra.get("website")),
            ("market_cap_tier", _cap_tier(profile.extra.get("market_cap"))),
            ("employees", profile.extra.get("employees")),
        ]:
            if value is not None:
                _mark_field_provenance(
                    detail,
                    field_name,
                    source=profile.provider,
                    fetched_at=fetched_at,
                    provider_symbol=profile.symbol,
                )

    elif quote_type == "CURRENCY":
        pair = _parse_forex_pair(profile.canonical_symbol)
        if pair:
            detail = (
                await db.execute(select(ForexDetail).where(ForexDetail.instrument_id == instrument.id))
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
            await db.execute(select(FutureDetail).where(FutureDetail.instrument_id == instrument.id))
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
