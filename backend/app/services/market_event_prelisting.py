"""Bounded materialization and conservative promotion of future listings."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_class import InstrumentType
from app.models.data_source import DataSource
from app.models.instrument import Instrument
from app.models.instrument_identity import (
    InstrumentIdentifier,
    InstrumentIdentifierType,
    InstrumentProviderSymbol,
)
from app.models.market_data_foundation import (
    IdentityStatus,
    MarketEvent,
    MarketEventConsensus,
    MarketEventPrelistingCandidate,
)

_SYMBOL_FIELDS = ("symbol", "ticker", "proposed_ticker", "provider_symbol")
_NAME_FIELDS = ("issuer_name", "company_name", "company", "name", "title")
_MIC_FIELDS = ("exchange_mic", "mic", "exchangeMic")
_IDENTIFIER_FIELDS = {
    "figi": ("figi", "security_figi"),
    "isin": ("isin",),
    "cusip": ("cusip",),
}
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,49}$")
_MIC_PATTERN = re.compile(r"^[A-Z0-9]{4}$")


def _first_text(payload: dict[str, Any], fields: Iterable[str]) -> str | None:
    for field in fields:
        value = payload.get(field)
        if value is None:
            continue
        text = " ".join(str(value).strip().split())
        if text:
            return text
    return None


def _symbol(payload: dict[str, Any]) -> str | None:
    value = _first_text(payload, _SYMBOL_FIELDS)
    if value is None:
        return None
    candidate = value.upper()
    return candidate if _SYMBOL_PATTERN.fullmatch(candidate) else None


def _mic(payload: dict[str, Any]) -> str | None:
    value = _first_text(payload, _MIC_FIELDS)
    if value is None:
        return None
    candidate = value.upper()
    return candidate if _MIC_PATTERN.fullmatch(candidate) else None


def _stable_identifiers(payload: dict[str, Any]) -> dict[str, str]:
    identifiers: dict[str, str] = {}
    for kind, fields in _IDENTIFIER_FIELDS.items():
        value = _first_text(payload, fields)
        if value:
            identifiers[kind] = "".join(value.upper().split())
    return identifiers


def _candidate_key(event: MarketEvent) -> str:
    if event.consensus_id is not None:
        return f"consensus:{event.consensus_id}"
    material = f"event:{event.source}:{event.event_key}"
    return "event:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _observed_at(event: MarketEvent, fallback: datetime) -> datetime:
    value = event.updated_at or event.created_at
    if value is None:
        return fallback
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _utc(value: datetime) -> datetime:
    """Normalize database-returned timestamps before comparing them."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _date_filters(start: date | None, end: date | None):
    filters = []
    if start is not None:
        start_at = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
        filters.append(
            or_(
                MarketEvent.effective_date >= start,
                and_(MarketEvent.effective_date.is_(None), MarketEvent.event_time >= start_at),
            )
        )
    if end is not None:
        end_at = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
        filters.append(
            or_(
                MarketEvent.effective_date <= end,
                and_(MarketEvent.effective_date.is_(None), MarketEvent.event_time < end_at),
            )
        )
    return filters


async def materialize_prelisting_candidates(
    db: AsyncSession,
    *,
    start: date | None = None,
    end: date | None = None,
    max_events: int = 500,
) -> dict[str, Any]:
    """Create bounded inactive provisional instruments from IPO observations.

    Candidate records are keyed by a reconciled consensus when available, so
    several provider rows do not create several provisional instruments. A
    conflicted consensus is retained as ``quarantined`` without creating an
    instrument until an operator reviews the disagreement.
    """

    if not isinstance(max_events, int) or isinstance(max_events, bool) or not 1 <= max_events <= 10_000:
        raise ValueError("max_events must be between 1 and 10000")
    if start is not None and end is not None and end < start:
        raise ValueError("end must be on or after start")

    query = (
        select(MarketEvent)
        .where(
            MarketEvent.event_type.in_(("ipo", "ipo_pipeline")),
            MarketEvent.instrument_id.is_(None),
        )
        .order_by(MarketEvent.id)
        .limit(max_events + 1)
    )
    filters = _date_filters(start, end)
    if filters:
        query = query.where(*filters)
    rows = (await db.execute(query)).scalars().all()
    truncated = len(rows) > max_events
    rows = rows[:max_events]
    grouped: dict[str, list[MarketEvent]] = defaultdict(list)
    for event in rows:
        grouped[_candidate_key(event)].append(event)

    stock_type = (
        await db.execute(
            select(InstrumentType)
            .where(func.lower(InstrumentType.name).in_(("stock", "equity")))
            .order_by(InstrumentType.id)
        )
    ).scalars().first()
    now = datetime.now(UTC)
    created = 0
    updated = 0
    instruments_created = 0
    quarantined = 0
    skipped = 0
    for key, events in grouped.items():
        events.sort(key=lambda event: (event.source, event.event_key, event.id))
        payloads = [(event, dict(event.payload or {})) for event in events]
        anchor, payload = next(
            ((event, row) for event, row in payloads if _symbol(row)),
            payloads[0],
        )
        symbol = _symbol(payload)
        if symbol is None:
            skipped += 1
            continue
        name = next(
            (_first_text(row, _NAME_FIELDS) for _event, row in payloads if _first_text(row, _NAME_FIELDS)),
            None,
        ) or symbol
        name = name[:300]
        exchange_mic = next((_mic(row) for _event, row in payloads if _mic(row)), None)
        identifiers: dict[str, str] = {}
        for _event, row in payloads:
            identifiers.update(_stable_identifiers(row))
        provider_sources = sorted({event.source for event in events})
        observed_times = [_observed_at(event, now) for event in events]
        consensus = None
        if anchor.consensus_id is not None:
            consensus = await db.get(MarketEventConsensus, anchor.consensus_id)
        status = "quarantined" if consensus is not None and consensus.status == "conflicted" else "pending"
        candidate = (
            await db.execute(
                select(MarketEventPrelistingCandidate).where(
                    MarketEventPrelistingCandidate.candidate_key == key
                )
            )
        ).scalar_one_or_none()
        if candidate is None:
            candidate = MarketEventPrelistingCandidate(
                candidate_key=key,
                consensus_id=anchor.consensus_id,
                anchor_event_id=anchor.id,
                issuer_id=anchor.issuer_id,
                proposed_symbol=symbol,
                proposed_name=name,
                exchange_mic=exchange_mic,
                expected_listing_date=anchor.effective_date
                or (anchor.event_time.date() if anchor.event_time else None),
                status=status,
                stable_identifiers=identifiers,
                provider_sources=provider_sources,
                first_seen_at=min(observed_times),
                last_seen_at=max(observed_times),
                provenance={
                    "algorithm": "market_event_prelisting_v1",
                    "provider_event_keys": [event.event_key for event in events],
                    "provider_rows_are_immutable": True,
                },
            )
            db.add(candidate)
            await db.flush()
            created += 1
        else:
            updated += 1
            candidate.proposed_symbol = symbol
            candidate.proposed_name = name
            candidate.exchange_mic = exchange_mic
            candidate.issuer_id = candidate.issuer_id or anchor.issuer_id
            candidate.expected_listing_date = (
                candidate.expected_listing_date
                or anchor.effective_date
                or (anchor.event_time.date() if anchor.event_time else None)
            )
            candidate.stable_identifiers = {**(candidate.stable_identifiers or {}), **identifiers}
            candidate.provider_sources = sorted(
                set(candidate.provider_sources or []).union(provider_sources)
            )
            candidate.first_seen_at = min(_utc(candidate.first_seen_at), min(observed_times))
            candidate.last_seen_at = max(_utc(candidate.last_seen_at), max(observed_times))
            if candidate.status == "pending" and status == "quarantined":
                candidate.status = status

        if status == "quarantined":
            quarantined += 1
            candidate.resolution = {
                "status": "operator_review_required",
                "reason": "provider event fields conflict in consensus group",
            }
            continue
        if candidate.status == "quarantined":
            # Quarantine is an explicit operator boundary; never silently
            # revive a candidate after its evidence or reference taxonomy has
            # been rejected.
            quarantined += 1
            continue
        if candidate.instrument_id is not None:
            continue
        if stock_type is None:
            candidate.status = "quarantined"
            candidate.resolution = {
                "status": "operator_review_required",
                "reason": "no Stock/Equity instrument type is configured",
            }
            quarantined += 1
            continue
        instrument = Instrument(
            instrument_type_id=stock_type.id,
            symbol=symbol,
            name=name,
            currency=str(payload.get("currency") or "USD")[:3].upper(),
            is_active=False,
            identity_status=IdentityStatus.PROVISIONAL.value,
            issuer_id=anchor.issuer_id,
            field_provenance={
                "source": "market_event_prelisting_v1",
                "candidate_key": key,
                "provider_sources": provider_sources,
                "stable_identifiers": identifiers,
            },
        )
        db.add(instrument)
        await db.flush()
        candidate.instrument_id = instrument.id
        instruments_created += 1

    await db.flush()
    return {
        "status": "partial" if truncated else "complete",
        "events_considered": len(rows),
        "candidates": len(grouped),
        "created": created,
        "updated": updated,
        "instruments_created": instruments_created,
        "quarantined": quarantined,
        "skipped": skipped,
        "truncated": truncated,
        "window": {"start": start, "end": end},
    }


async def promote_prelisting_candidates(
    db: AsyncSession,
    *,
    max_candidates: int = 500,
) -> dict[str, Any]:
    """Promote only candidates with a unique stable/venue-qualified match."""

    if not isinstance(max_candidates, int) or isinstance(max_candidates, bool) or not 1 <= max_candidates <= 10_000:
        raise ValueError("max_candidates must be between 1 and 10000")
    rows = (
        await db.execute(
            select(MarketEventPrelistingCandidate)
            .where(MarketEventPrelistingCandidate.status == "pending")
            .order_by(MarketEventPrelistingCandidate.expected_listing_date, MarketEventPrelistingCandidate.id)
            .limit(max_candidates)
        )
    ).scalars().all()
    promoted = 0
    ambiguous = 0
    for candidate in rows:
        matches: set[int] = set()
        for kind, value in (candidate.stable_identifiers or {}).items():
            try:
                identifier_type = InstrumentIdentifierType(kind)
            except ValueError:
                continue
            matches.update(
                int(row[0])
                for row in (
                    await db.execute(
                        select(InstrumentIdentifier.instrument_id).where(
                            InstrumentIdentifier.identifier_type == identifier_type,
                            InstrumentIdentifier.identifier_value == value,
                            InstrumentIdentifier.is_active.is_(True),
                        )
                    )
                ).all()
            )
        if not matches and candidate.exchange_mic:
            source_names = list(candidate.provider_sources or [])
            query = (
                select(Instrument.id)
                .join(InstrumentProviderSymbol, InstrumentProviderSymbol.instrument_id == Instrument.id)
                .join(DataSource, DataSource.id == InstrumentProviderSymbol.data_source_id)
                .where(
                    Instrument.is_active.is_(True),
                    func.upper(InstrumentProviderSymbol.provider_symbol)
                    == candidate.proposed_symbol.upper(),
                    func.upper(InstrumentProviderSymbol.provider_exchange_code)
                    == candidate.exchange_mic.upper(),
                    DataSource.name.in_(source_names),
                )
            )
            matches.update(int(row[0]) for row in (await db.execute(query)).all())
        if len(matches) != 1:
            if len(matches) > 1:
                ambiguous += 1
            continue
        instrument_id = next(iter(matches))
        candidate.instrument_id = instrument_id
        candidate.status = "listed"
        candidate.promoted_at = datetime.now(UTC)
        candidate.resolution = {
            "method": "unique_stable_or_exchange_qualified_match",
            "instrument_id": instrument_id,
        }
        event_filter = (
            MarketEvent.consensus_id == candidate.consensus_id
            if candidate.consensus_id is not None
            else MarketEvent.id == candidate.anchor_event_id
        )
        events = (await db.execute(select(MarketEvent).where(event_filter))).scalars().all()
        for event in events:
            event.instrument_id = instrument_id
            if event.issuer_id is None:
                event.issuer_id = candidate.issuer_id
        promoted += 1
    await db.flush()
    return {
        "status": "complete",
        "candidates_considered": len(rows),
        "promoted": promoted,
        "ambiguous": ambiguous,
    }
