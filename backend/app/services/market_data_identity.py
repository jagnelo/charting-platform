"""Stable identity helpers for provider reconciliation.

The service never guesses a merge from a ticker alone.  A candidate without a
stable identifier is explicitly quarantined for review, which keeps provider
symbol changes and delistings auditable.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_class import AssetClass, InstrumentType
from app.models.instrument import Instrument
from app.models.instrument_identity import InstrumentIdentifier, InstrumentIdentifierType
from app.models.market_data_foundation import (
    IdentityStatus,
    InstrumentIdentityQuarantine,
    InstrumentIdentityQuarantineObservation,
)

# A spot crypto pair or an FX pair is self-identifying: its asset class plus
# the canonical BASE-QUOTE pair *is* the instrument. There is no issuer,
# share class, or corporate action that a FIGI/ISIN would disambiguate, so
# requiring an equity-style security identifier only blocks these instruments
# forever. Only these asset classes may use the pair key below.
_SELF_IDENTIFYING_PAIR_PREFIXES = {
    "cryptocurrency": "crypto-pair",
    "currency": "fx-pair",
}
_CRYPTO_PAIR_RE = re.compile(r"^([A-Z0-9]{1,20})[-/]([A-Z0-9]{2,10})$")
_FX_PAIR_RE = re.compile(r"^([A-Z]{3})[-/]?([A-Z]{3})(?:=X)?$")
_NON_EXTERNAL_PRIMARY_TYPES = {
    InstrumentIdentifierType.INTERNAL.value,
    InstrumentIdentifierType.CIK.value,
}


def _asset_class_token(value: str | None) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def self_identifying_pair_key(asset_class: str | None, symbol: str | None) -> str | None:
    """Return the canonical pair domain key for a self-identifying instrument.

    Returns ``None`` for every asset class other than cryptocurrency/currency
    and for any symbol that is not an unambiguous BASE-QUOTE pair, so equity
    identity rules are never relaxed through this path.
    """

    prefix = _SELF_IDENTIFYING_PAIR_PREFIXES.get(_asset_class_token(asset_class))
    if prefix is None:
        return None
    text = str(symbol or "").strip().upper()
    pattern = _FX_PAIR_RE if prefix == "fx-pair" else _CRYPTO_PAIR_RE
    match = pattern.fullmatch(text)
    if match is None:
        return None
    base, quote = match.group(1), match.group(2)
    if base == quote or not any(character.isalpha() for character in base):
        return None
    return f"{prefix}:{base}-{quote}"


def has_stable_external_identity(instrument: Instrument) -> bool:
    """Resolved identity backed by a security-level external identifier."""

    return bool(
        instrument.identity_status == IdentityStatus.RESOLVED.value
        and instrument.domain_key
        and instrument.primary_identifier_type
        and instrument.primary_identifier_type not in _NON_EXTERNAL_PRIMARY_TYPES
        and instrument.primary_identifier_value
    )


def has_self_identifying_identity(instrument: Instrument, asset_class: str | None) -> bool:
    """Resolved pair identity whose key still matches the current class/symbol."""

    key = self_identifying_pair_key(asset_class, instrument.symbol)
    return bool(
        key
        and not instrument.is_synthetic
        and instrument.identity_status == IdentityStatus.RESOLVED.value
        and instrument.domain_key == key
    )


async def instrument_asset_class_name(db: AsyncSession, instrument: Instrument) -> str | None:
    if instrument.instrument_type_id is None:
        return None
    return (
        await db.execute(
            select(AssetClass.name)
            .join(InstrumentType, InstrumentType.asset_class_id == AssetClass.id)
            .where(InstrumentType.id == instrument.instrument_type_id)
        )
    ).scalar_one_or_none()


async def instrument_identity_is_qualified(db: AsyncSession, instrument: Instrument) -> bool:
    """Whether dependent data (history, profile) may proceed without an identity job.

    Equities require a resolved, security-level external identifier (FIGI,
    ISIN, CUSIP, SEDOL, LEI); a CIK or internal key never qualifies. A crypto or
    FX spot pair qualifies through its resolved canonical pair key only.
    """

    if has_stable_external_identity(instrument):
        return True
    if instrument.identity_status != IdentityStatus.RESOLVED.value or not instrument.domain_key:
        return False
    return has_self_identifying_identity(
        instrument, await instrument_asset_class_name(db, instrument)
    )


async def _apply_self_identifying_identity(
    db: AsyncSession,
    instrument: Instrument,
    *,
    provider_name: str,
    provider_symbol: str | None,
    exchange_mic: str | None,
    candidate_payload: dict[str, Any] | None,
    record_conflict: bool,
) -> tuple[bool, str | None]:
    """Return (applicable, domain_key) for a pair instrument."""

    if instrument.is_synthetic:
        return False, None
    key = self_identifying_pair_key(
        await instrument_asset_class_name(db, instrument), instrument.symbol
    )
    if key is None:
        return False, None
    if instrument.domain_key:
        if instrument.domain_key != key:
            # Never overwrite an existing stable key with a derived pair key.
            return True, None
        if instrument.identity_status in {
            IdentityStatus.PROVISIONAL.value,
            IdentityStatus.QUARANTINED.value,
        }:
            instrument.identity_status = IdentityStatus.RESOLVED.value
        return True, key if instrument.identity_status == IdentityStatus.RESOLVED.value else None
    if instrument.identity_status not in {
        IdentityStatus.PROVISIONAL.value,
        IdentityStatus.QUARANTINED.value,
    }:
        return True, None
    owner = (
        await db.execute(
            select(Instrument.id).where(
                Instrument.domain_key == key,
                Instrument.id != instrument.id,
            )
        )
    ).scalar_one_or_none()
    if owner is not None:
        # Two canonical rows claim the same pair: a real conflict for review.
        if record_conflict:
            instrument.identity_status = IdentityStatus.QUARANTINED.value
            await _record_quarantine(
                db,
                instrument=instrument,
                proposed_domain_key=key,
                provider_name=provider_name,
                provider_symbol=provider_symbol,
                exchange_mic=exchange_mic,
                reason=f"self-identifying pair key is already owned by instrument {owner}",
                candidate_payload=candidate_payload,
            )
        return True, None
    instrument.domain_key = key
    instrument.identity_status = IdentityStatus.RESOLVED.value
    return True, key


async def apply_self_identifying_identity(
    db: AsyncSession,
    instrument: Instrument,
    *,
    provider_name: str = "self_identifying_pair",
    provider_symbol: str | None = None,
    exchange_mic: str | None = None,
    candidate_payload: dict[str, Any] | None = None,
    record_conflict: bool = True,
) -> str | None:
    """Resolve a crypto/FX spot pair from its canonical BASE-QUOTE symbol.

    No-op (returns ``None``) for any other asset class. The pair key is never
    reassigned from another instrument; that collision is quarantined.
    """

    _applicable, key = await _apply_self_identifying_identity(
        db,
        instrument,
        provider_name=provider_name,
        provider_symbol=provider_symbol,
        exchange_mic=exchange_mic,
        candidate_payload=candidate_payload,
        record_conflict=record_conflict,
    )
    return key


_DOMAIN_PREFIXES = {
    InstrumentIdentifierType.FIGI: "figi",
    InstrumentIdentifierType.COMPOSITE_FIGI: "composite-figi",
    InstrumentIdentifierType.ISIN: "isin",
    InstrumentIdentifierType.CUSIP: "cusip",
    InstrumentIdentifierType.SEDOL: "sedol",
    InstrumentIdentifierType.LEI: "lei",
}

# FIGI is preferred for a security. CIK is intentionally absent: it identifies
# an SEC registrant/issuer and must never become a security domain key. Issuer
# records carry the CIK separately.
_IDENTIFIER_PRIORITY = (
    InstrumentIdentifierType.FIGI,
    InstrumentIdentifierType.COMPOSITE_FIGI,
    InstrumentIdentifierType.ISIN,
    InstrumentIdentifierType.CUSIP,
    InstrumentIdentifierType.SEDOL,
    InstrumentIdentifierType.LEI,
)


def normalize_identifier_value(value: str) -> str:
    return "".join(str(value).strip().upper().split())


def make_domain_key(identifier_type: InstrumentIdentifierType | str, value: str) -> str | None:
    """Return a stable, namespaced key or ``None`` for internal identifiers."""

    try:
        kind = (
            identifier_type
            if isinstance(identifier_type, InstrumentIdentifierType)
            else InstrumentIdentifierType(str(identifier_type).lower())
        )
    except ValueError:
        return None
    prefix = _DOMAIN_PREFIXES.get(kind)
    normalized = normalize_identifier_value(value)
    if not prefix or not normalized:
        return None
    return f"{prefix}:{normalized}"


def choose_domain_key(identifiers: Mapping[InstrumentIdentifierType | str, str]) -> str | None:
    """Select the strongest available external identifier deterministically."""

    normalized: dict[InstrumentIdentifierType, str] = {}
    for key, value in identifiers.items():
        try:
            kind = (
                key
                if isinstance(key, InstrumentIdentifierType)
                else InstrumentIdentifierType(str(key).lower())
            )
        except ValueError:
            continue
        normalized[kind] = value
    for kind in _IDENTIFIER_PRIORITY:
        value = normalized.get(kind)
        if value:
            return make_domain_key(kind, value)
    return None


async def apply_domain_identity(
    db: AsyncSession,
    instrument: Instrument,
    *,
    identifiers: Mapping[InstrumentIdentifierType | str, str] | None = None,
    provider_name: str = "unknown",
    provider_symbol: str | None = None,
    exchange_mic: str | None = None,
    candidate_payload: dict[str, Any] | None = None,
) -> str | None:
    """Attach a stable key when safe, otherwise create a quarantine row.

    A key already owned by another instrument is never reassigned.  The caller
    receives ``None`` and can continue ingesting the candidate as provisional.
    """

    values = dict(identifiers or {})
    if not values:
        rows = (
            await db.execute(
                select(InstrumentIdentifier).where(
                    InstrumentIdentifier.instrument_id == instrument.id,
                    InstrumentIdentifier.is_active.is_(True),
                )
            )
        ).scalars()
        values = {row.identifier_type: row.identifier_value for row in rows}
    domain_key = choose_domain_key(values)
    if domain_key is None:
        applicable, pair_key = await _apply_self_identifying_identity(
            db,
            instrument,
            provider_name=provider_name,
            provider_symbol=provider_symbol,
            exchange_mic=exchange_mic,
            candidate_payload=candidate_payload,
            record_conflict=True,
        )
        if applicable:
            return pair_key
        instrument.identity_status = IdentityStatus.QUARANTINED.value
        await _record_quarantine(
            db,
            instrument=instrument,
            proposed_domain_key=None,
            provider_name=provider_name,
            provider_symbol=provider_symbol,
            exchange_mic=exchange_mic,
            reason="no stable external identifier was supplied",
            candidate_payload=candidate_payload,
        )
        return None

    owner = (
        await db.execute(
            select(Instrument).where(
                Instrument.domain_key == domain_key,
                Instrument.id != instrument.id,
            )
        )
    ).scalar_one_or_none()
    if owner is not None:
        instrument.identity_status = IdentityStatus.QUARANTINED.value
        await _record_quarantine(
            db,
            instrument=instrument,
            proposed_domain_key=domain_key,
            provider_name=provider_name,
            provider_symbol=provider_symbol,
            exchange_mic=exchange_mic,
            reason=f"stable key is already owned by instrument {owner.id}",
            candidate_payload=candidate_payload,
        )
        return None

    instrument.domain_key = domain_key
    instrument.identity_status = IdentityStatus.RESOLVED.value
    return domain_key


async def quarantine_identity_candidate(
    db: AsyncSession,
    instrument: Instrument,
    *,
    proposed_domain_key: str | None,
    provider_name: str,
    provider_symbol: str | None,
    exchange_mic: str | None,
    reason: str,
    candidate_payload: dict[str, Any] | None,
) -> InstrumentIdentityQuarantine:
    """Keep an unresolved instrument quarantined with an auditable reason."""

    if instrument.identity_status != IdentityStatus.RESOLVED.value:
        instrument.identity_status = IdentityStatus.QUARANTINED.value
    return await _record_quarantine(
        db,
        instrument=instrument,
        proposed_domain_key=proposed_domain_key,
        provider_name=provider_name,
        provider_symbol=provider_symbol,
        exchange_mic=exchange_mic,
        reason=reason,
        candidate_payload=candidate_payload,
    )


async def _record_quarantine(
    db: AsyncSession,
    *,
    instrument: Instrument,
    proposed_domain_key: str | None,
    provider_name: str,
    provider_symbol: str | None,
    exchange_mic: str | None,
    reason: str,
    candidate_payload: dict[str, Any] | None,
) -> InstrumentIdentityQuarantine:
    """Keep one pending row per provider candidate instead of growing duplicates."""

    symbol = provider_symbol or instrument.symbol
    existing = (
        await db.execute(
            select(InstrumentIdentityQuarantine).where(
                InstrumentIdentityQuarantine.instrument_id == instrument.id,
                InstrumentIdentityQuarantine.provider_name == provider_name,
                InstrumentIdentityQuarantine.provider_symbol == symbol,
                InstrumentIdentityQuarantine.proposed_domain_key == proposed_domain_key,
                InstrumentIdentityQuarantine.status == "pending",
            )
        )
    ).scalar_one_or_none()
    observed_at = identity_observed_at()
    if existing is not None:
        existing.reason = reason
        existing.exchange_mic = exchange_mic
        # An explicitly empty provider envelope is still evidence.  Only a
        # missing payload may retain the previous projection.
        existing.candidate_payload = (
            candidate_payload if candidate_payload is not None else existing.candidate_payload or {}
        )
        row = existing
    else:
        row = InstrumentIdentityQuarantine(
            proposed_domain_key=proposed_domain_key,
            provider_name=provider_name,
            provider_symbol=symbol,
            exchange_mic=exchange_mic,
            reason=reason,
            status="pending",
            candidate_payload=candidate_payload or {},
            instrument_id=instrument.id,
        )
        db.add(row)
        await db.flush()
    db.add(
        InstrumentIdentityQuarantineObservation(
            quarantine_id=row.id,
            instrument_id=instrument.id,
            proposed_domain_key=proposed_domain_key,
            provider_name=provider_name,
            provider_symbol=symbol,
            exchange_mic=exchange_mic,
            reason=reason,
            status=row.status,
            observed_at=observed_at,
            candidate_payload=candidate_payload or {},
        )
    )
    await db.flush()
    return row


def identity_observed_at() -> datetime:
    return datetime.now(UTC)
