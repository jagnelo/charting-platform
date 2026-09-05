"""Stable identity helpers for provider reconciliation.

The service never guesses a merge from a ticker alone.  A candidate without a
stable identifier is explicitly quarantined for review, which keeps provider
symbol changes and delistings auditable.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instrument import Instrument
from app.models.instrument_identity import InstrumentIdentifier, InstrumentIdentifierType
from app.models.market_data_foundation import IdentityStatus, InstrumentIdentityQuarantine

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
        kind = identifier_type if isinstance(identifier_type, InstrumentIdentifierType) else InstrumentIdentifierType(str(identifier_type).lower())
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
            kind = key if isinstance(key, InstrumentIdentifierType) else InstrumentIdentifierType(str(key).lower())
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
    if existing is not None:
        existing.reason = reason
        existing.exchange_mic = exchange_mic
        existing.candidate_payload = candidate_payload or existing.candidate_payload or {}
        return existing
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
    return row


def identity_observed_at() -> datetime:
    return datetime.now(UTC)
