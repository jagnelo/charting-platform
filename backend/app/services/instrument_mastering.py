from __future__ import annotations

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
from app.models.listing import InstrumentListing
from app.providers.base import IdentifierRecord, InstrumentProfile
from app.providers.registry import ensure_data_source

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
    existing.extra_data = extra_data or existing.extra_data

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
    existing.extra_data = identifier.extra_data or existing.extra_data

    if existing.identifier_type == InstrumentIdentifierType.ISIN:
        instrument.isin = identifier.identifier_value

    if identifier.is_primary or instrument.primary_identifier_value is None:
        instrument.primary_identifier_type = existing.identifier_type.value
        instrument.primary_identifier_value = identifier.identifier_value


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


async def upsert_instrument_stats(
    db: AsyncSession,
    instrument: Instrument,
    extra: dict[str, Any],
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
    stats.computed_at = datetime.now(UTC)


async def apply_profile_to_instrument(
    db: AsyncSession,
    profile: InstrumentProfile,
    *,
    instrument: Instrument | None = None,
) -> Instrument:
    quote_type = (profile.quote_type or "EQUITY").upper()
    asset_class_name, type_name = TYPE_MAP.get(quote_type, ("Equity", "Stock"))
    instrument_type_id = await ensure_instrument_type(db, asset_class_name, type_name)

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
    await upsert_instrument_stats(db, instrument, profile.extra)

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

    elif quote_type == "FUTURE":
        detail = (
            await db.execute(select(FutureDetail).where(FutureDetail.instrument_id == instrument.id))
        ).scalar_one_or_none()
        if detail is None:
            detail = FutureDetail(instrument_id=instrument.id)
            db.add(detail)
        detail.underlying_name = profile.name or detail.underlying_name
        detail.is_continuous = profile.canonical_symbol.endswith("=F") or detail.is_continuous

    return instrument
