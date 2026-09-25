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
    ProviderPaginationState,
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
_STRONG_CONSENSUS_STATUSES = frozenset({"corroborated", "resolved"})


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


def _normalised_name(payload: dict[str, Any]) -> str | None:
    value = _first_text(payload, _NAME_FIELDS)
    return value.casefold() if value else None


def _strong_evidence_reason(
    *,
    consensus: MarketEventConsensus | None,
    events: list[MarketEvent],
    payloads: list[dict[str, Any]],
    symbol: str,
    exchange_mic: str | None,
) -> str | None:
    """Return a quarantine reason unless future-listing evidence is strong.

    A valid-looking ticker is not enough to create a provisional security.  A
    future listing must have a reconciled multi-provider consensus, one exact
    symbol/name, and either an exact venue-qualified observation from every
    source or the same stable security identifier observed by at least two
    sources.  This is deliberately stricter than the later promotion step:
    weak or contradictory observations remain reviewable candidates without
    becoming instruments that downstream jobs could accidentally consume.
    """

    if consensus is None:
        return "future-listing evidence has no reconciled provider consensus"
    status = str(consensus.status or "").strip().lower()
    if status not in _STRONG_CONSENSUS_STATUSES:
        return f"future-listing consensus status {status or 'unknown'} is not corroborated"
    sources = {str(event.source or "").strip().lower() for event in events if event.source}
    if len(sources) < 2 or len(events) < 2:
        return "future-listing evidence requires at least two distinct provider observations"
    if consensus.conflict_fields:
        return "future-listing consensus retains unresolved field conflicts"

    symbols = [_symbol(payload) for payload in payloads]
    if any(value is None for value in symbols):
        return "every future-listing observation must provide a valid symbol"
    if len(set(symbols)) != 1 or symbols[0] != symbol:
        return "future-listing observations disagree on the proposed symbol"

    names = [_normalised_name(payload) for payload in payloads]
    if any(value is None for value in names):
        return "every future-listing observation must provide a company name"
    if len(set(names)) != 1:
        return "future-listing observations disagree on the company name"

    identifier_observations: dict[str, dict[str, set[str]]] = {}
    for event, payload in zip(events, payloads, strict=True):
        source = str(event.source or "").strip().lower()
        for kind, value in _stable_identifiers(payload).items():
            identifier_observations.setdefault(kind, {}).setdefault(value, set()).add(source)
    for kind, values in identifier_observations.items():
        if len(values) > 1:
            return f"future-listing observations disagree on {kind}"

    venue_values = [_mic(payload) for payload in payloads]
    exact_venue = (
        all(value is not None for value in venue_values)
        and len(set(venue_values)) == 1
        and venue_values[0] == exchange_mic
    )
    shared_identifier = any(
        len(source_names) >= 2
        for values in identifier_observations.values()
        for source_names in values.values()
    )
    if not exact_venue and not shared_identifier:
        return (
            "future-listing evidence requires one exact venue MIC across providers "
            "or a shared stable security identifier"
        )
    return None


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

    scan_key = "market-event-prelisting:" + ":".join(
        (value.isoformat() if value is not None else "*") for value in (start, end)
    )
    state = (
        await db.execute(
            select(ProviderPaginationState)
            .where(ProviderPaginationState.state_key == scan_key)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if state is None:
        state = ProviderPaginationState(
            state_key=scan_key,
            provider="internal",
            capability="market_event_prelisting",
            operation="materialize_prelisting_candidates",
            page_size=max_events,
            metadata_payload={
                "window": {
                    "start": start.isoformat() if start else None,
                    "end": end.isoformat() if end else None,
                }
            },
        )
        db.add(state)
        await db.flush()

    cursor_id: int | None = None
    if state.cursor is not None:
        try:
            cursor_id = int(state.cursor)
        except (TypeError, ValueError):
            state.last_error = "invalid persisted market-event prelisting cursor"
            state.status = "failed"
            raise ValueError("invalid persisted market-event prelisting cursor")

    query = (
        select(MarketEvent)
        .where(
            MarketEvent.event_type.in_(("ipo", "ipo_pipeline")),
            MarketEvent.instrument_id.is_(None),
        )
        .order_by(MarketEvent.id)
    )
    if cursor_id is not None:
        query = query.where(MarketEvent.id > cursor_id)
    filters = _date_filters(start, end)
    if filters:
        query = query.where(*filters)
    query = query.limit(max_events + 1)
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
        quarantine_reason = _strong_evidence_reason(
            consensus=consensus,
            events=events,
            payloads=[row for _event, row in payloads],
            symbol=symbol,
            exchange_mic=exchange_mic,
        )
        status = "quarantined" if quarantine_reason is not None else "pending"
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
                    "evidence_policy": "corroborated_exact_symbol_name_venue_or_shared_identifier_v2",
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
                candidate.resolution = {
                    "status": "operator_review_required",
                    "reason": quarantine_reason,
                }

        if status == "quarantined":
            quarantined += 1
            candidate.resolution = {
                "status": "operator_review_required",
                "reason": quarantine_reason or "provider event evidence is ambiguous",
            }
            # A prior implementation could have attached a provisional
            # instrument before this stricter evidence policy was applied.
            # Keep that row inactive and quarantine it rather than allowing a
            # newly observed contradiction to remain routable.
            if candidate.instrument_id is not None:
                prior_instrument = await db.get(Instrument, candidate.instrument_id)
                if (
                    prior_instrument is not None
                    and prior_instrument.identity_status == IdentityStatus.PROVISIONAL.value
                ):
                    prior_instrument.is_active = False
                    prior_instrument.identity_status = IdentityStatus.QUARANTINED.value
                    prior_instrument.field_provenance = {
                        **(prior_instrument.field_provenance or {}),
                        "quarantine_reason": quarantine_reason
                        or "provider event evidence is ambiguous",
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

    state.page_number += 1
    state.pages_fetched += 1
    state.page_size = max_events
    state.last_page_count = len(rows)
    state.last_success_at = now
    state.last_error = None
    state.status = "partial" if truncated else "complete"
    state.cursor = str(rows[-1].id) if truncated and rows else None
    state.metadata_payload = {
        **(state.metadata_payload or {}),
        "last_event_ids": [event.id for event in rows],
        "events_considered": len(rows),
        "truncated": truncated,
    }
    await db.flush()
    return {
        "status": state.status,
        "events_considered": len(rows),
        "candidates": len(grouped),
        "created": created,
        "updated": updated,
        "instruments_created": instruments_created,
        "quarantined": quarantined,
        "skipped": skipped,
        "truncated": truncated,
        "cursor": state.cursor,
        "cycle_complete": state.cursor is None,
        "scan_key": scan_key,
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
    scan_key = "market-event-prelisting-promotion"
    state = (
        await db.execute(
            select(ProviderPaginationState)
            .where(ProviderPaginationState.state_key == scan_key)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if state is None:
        state = ProviderPaginationState(
            state_key=scan_key,
            provider="internal",
            capability="market_event_prelisting",
            operation="promote_prelisting_candidates",
            page_size=max_candidates,
            metadata_payload={"algorithm": "prelisting_promotion_v1"},
        )
        db.add(state)
        await db.flush()

    cursor_id: int | None = None
    if state.cursor is not None:
        try:
            cursor_id = int(state.cursor)
        except (TypeError, ValueError):
            state.last_error = "invalid persisted prelisting promotion cursor"
            state.status = "failed"
            raise ValueError("invalid persisted prelisting promotion cursor")

    query = (
        select(MarketEventPrelistingCandidate)
        .where(MarketEventPrelistingCandidate.status == "pending")
        .order_by(MarketEventPrelistingCandidate.id)
    )
    if cursor_id is not None:
        query = query.where(MarketEventPrelistingCandidate.id > cursor_id)
    rows = (await db.execute(query.limit(max_candidates + 1))).scalars().all()
    truncated = len(rows) > max_candidates
    rows = rows[:max_candidates]
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
    now = datetime.now(UTC)
    state.page_number += 1
    state.pages_fetched += 1
    state.page_size = max_candidates
    state.last_page_count = len(rows)
    state.last_success_at = now
    state.last_error = None
    state.status = "partial" if truncated else "complete"
    state.cursor = str(rows[-1].id) if truncated and rows else None
    state.metadata_payload = {
        **(state.metadata_payload or {}),
        "last_candidate_ids": [candidate.id for candidate in rows],
        "candidates_considered": len(rows),
        "truncated": truncated,
    }
    await db.flush()
    return {
        "status": state.status,
        "candidates_considered": len(rows),
        "promoted": promoted,
        "ambiguous": ambiguous,
        "truncated": truncated,
        "cursor": state.cursor,
        "cycle_complete": state.cursor is None,
        "scan_key": scan_key,
    }
