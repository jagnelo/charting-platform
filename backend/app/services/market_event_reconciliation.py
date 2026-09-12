"""Conservative reconciliation of persisted market-event observations.

Provider rows are never replaced by a guessed winner.  Reconciliation creates a
durable candidate group only when an observation has an exact canonical target
(instrument, issuer, or an explicitly supplied venue MIC) and an occurrence
date.  Providers are compared on a small semantic field allow-list; differing
values remain visible as a ``conflicted`` group for operator review.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data_foundation import MarketEvent, MarketEventConsensus

_VENUE_MIC = re.compile(r"^[A-Z0-9]{4}$")
_PAYLOAD_ALIASES: dict[str, tuple[str, ...]] = {
    "title": ("title", "name"),
    "status": ("status", "ipo_status", "state"),
    "form": ("form", "filing_form"),
    "report_date": ("report_date", "reportDate", "fiscal_date_ending"),
    "event_time": ("event_time", "eventTime", "scheduled_at", "scheduledAt"),
    "time": ("time", "time_hint", "timeHint"),
    "eps_estimate": ("eps_estimate", "epsEstimate"),
    "eps_actual": ("eps_actual", "epsActual"),
    "revenue_estimate": ("revenue_estimate", "revenueEstimate"),
    "revenue_actual": ("revenue_actual", "revenueActual"),
    "dividend_amount": ("dividend_amount", "dividendAmount"),
    "split_ratio": ("split_ratio", "splitRatio"),
    "currency": ("currency",),
    "exchange_mic": ("exchange_mic", "mic", "exchangeMic"),
}
_NUMERIC_FIELDS = frozenset(
    {
        "eps_estimate",
        "eps_actual",
        "revenue_estimate",
        "revenue_actual",
        "dividend_amount",
        "split_ratio",
    }
)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _normalise_value(field: str, value: Any) -> str | None:
    if value is None:
        return None
    if field in _NUMERIC_FIELDS:
        try:
            return str(Decimal(str(value)).normalize())
        except (InvalidOperation, ValueError):
            pass
    if isinstance(value, datetime):
        normalised = _utc(value)
        return normalised.isoformat() if normalised is not None else None
    if isinstance(value, date):
        return value.isoformat()
    text = " ".join(str(value).strip().split())
    return text.casefold() if text else None


def _payload_value(payload: dict[str, Any], aliases: Iterable[str]) -> Any:
    for key in aliases:
        value = payload.get(key)
        if value is not None and value != "":
            return value
    return None


def _venue_mic(event: MarketEvent) -> str | None:
    payload = event.payload or {}
    value = _payload_value(payload, _PAYLOAD_ALIASES["exchange_mic"])
    if value is None:
        return None
    mic = str(value).strip().upper()
    return mic if _VENUE_MIC.fullmatch(mic) else None


def _target(event: MarketEvent) -> str | None:
    if event.instrument_id is not None:
        return f"instrument:{event.instrument_id}"
    if event.issuer_id is not None:
        return f"issuer:{event.issuer_id}"
    mic = _venue_mic(event)
    return f"venue:{mic}" if mic else None


def _anchor_date(event: MarketEvent) -> date | None:
    if event.effective_date is not None:
        return event.effective_date
    event_time = _utc(event.event_time)
    return event_time.date() if event_time is not None else None


def _consensus_key(event: MarketEvent) -> str | None:
    target = _target(event)
    anchor = _anchor_date(event)
    event_type = str(event.event_type or "").strip().casefold()
    if not target or not anchor or not event_type:
        return None
    material = f"v1|{event_type}|{target}|{anchor.isoformat()}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"market-event-consensus:v1:{digest}"


def _semantic_values(event: MarketEvent) -> dict[str, Any]:
    payload = event.payload or {}
    values: dict[str, Any] = {
        "event_type": event.event_type,
        "effective_date": event.effective_date,
        "event_time": _utc(event.event_time),
        "announced_at": _utc(event.announced_at),
    }
    for field, aliases in _PAYLOAD_ALIASES.items():
        value = _payload_value(payload, aliases)
        if value is not None:
            values[field] = value
    return values


def _group_comparison(events: list[MarketEvent]) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
    fields = sorted({field for event in events for field in _semantic_values(event)})
    canonical: dict[str, Any] = {}
    agreement_fields: list[str] = []
    conflicts: list[dict[str, Any]] = []
    for field in fields:
        present = [
            (event, _semantic_values(event).get(field))
            for event in events
            if _semantic_values(event).get(field) is not None
        ]
        if not present:
            continue
        normalised = {_normalise_value(field, value) for _, value in present}
        if len(normalised) == 1:
            canonical[field] = _json_value(present[0][1])
            agreement_fields.append(field)
            continue
        conflicts.append(
            {
                "field": field,
                "values": [
                    {
                        "event_id": event.id,
                        "source": event.source,
                        "event_key": event.event_key,
                        "value": _json_value(value),
                    }
                    for event, value in present
                ],
            }
        )
    return canonical, agreement_fields, conflicts


def _event_observation(event: MarketEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "source": event.source,
        "event_key": event.event_key,
        "source_version": event.source_version,
        "is_provisional": event.is_provisional,
    }


def _observed_at(event: MarketEvent, fallback: datetime) -> datetime:
    return _utc(event.updated_at or event.created_at) or fallback


async def reconcile_market_events(
    db: AsyncSession,
    *,
    start: date | None = None,
    end: date | None = None,
    max_events: int = 5000,
) -> dict[str, Any]:
    """Build/update bounded consensus groups without selecting a provider winner."""

    if not isinstance(max_events, int) or isinstance(max_events, bool) or not 1 <= max_events <= 50_000:
        raise ValueError("max_events must be between 1 and 50000")
    if start is not None and end is not None and end < start:
        raise ValueError("end must be on or after start")

    filters = []
    if start is not None:
        start_at = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
        filters.append(
            or_(
                MarketEvent.effective_date >= start,
                and_(
                    MarketEvent.effective_date.is_(None),
                    MarketEvent.event_time >= start_at,
                ),
            )
        )
    if end is not None:
        end_at = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
        filters.append(
            or_(
                MarketEvent.effective_date <= end,
                and_(
                    MarketEvent.effective_date.is_(None),
                    MarketEvent.event_time < end_at,
                ),
            )
        )
    query = select(MarketEvent).order_by(MarketEvent.id).limit(max_events + 1)
    if filters:
        query = query.where(*filters)
    rows = (await db.execute(query)).scalars().all()
    truncated = len(rows) > max_events
    events = rows[:max_events]
    groups: dict[str, list[MarketEvent]] = defaultdict(list)
    unresolved = 0
    for event in events:
        key = _consensus_key(event)
        if key is None:
            event.consensus_id = None
            unresolved += 1
            continue
        groups[key].append(event)

    now = datetime.now(UTC)
    status_counts: dict[str, int] = defaultdict(int)
    created = 0
    updated = 0
    for key, grouped in groups.items():
        grouped.sort(key=lambda event: (event.source, event.event_key, event.id))
        first = grouped[0]
        canonical, agreement_fields, conflicts = _group_comparison(grouped)
        source_count = len({event.source for event in grouped})
        duplicate_source = source_count < len(grouped)
        if duplicate_source and not conflicts:
            conflicts.append(
                {
                    "field": "multiple_observations_same_source",
                    "values": [event.event_key for event in grouped],
                }
            )
        if len(grouped) == 1:
            status = "single_source"
        elif conflicts or source_count < 2:
            status = "conflicted"
        else:
            status = "corroborated"

        observed_times = [_observed_at(event, now) for event in grouped]
        first_observed = min(observed_times)
        last_observed = max(observed_times)
        consensus = (
            await db.execute(
                select(MarketEventConsensus).where(
                    MarketEventConsensus.consensus_key == key
                )
            )
        ).scalar_one_or_none()
        if consensus is None:
            consensus = MarketEventConsensus(
                consensus_key=key,
                event_type=first.event_type,
                instrument_id=first.instrument_id,
                issuer_id=first.issuer_id,
                effective_date=first.effective_date or _anchor_date(first),
                event_time=first.event_time,
                announced_at=first.announced_at,
                first_observed_at=first_observed,
                last_observed_at=last_observed,
            )
            db.add(consensus)
            await db.flush()
            created += 1
        else:
            updated += 1
            consensus.event_type = first.event_type
            consensus.instrument_id = first.instrument_id
            consensus.issuer_id = first.issuer_id
            consensus.effective_date = first.effective_date or _anchor_date(first)
            consensus.event_time = first.event_time
            consensus.announced_at = first.announced_at
            prior_first = _utc(consensus.first_observed_at) or first_observed
            prior_last = _utc(consensus.last_observed_at) or last_observed
            consensus.first_observed_at = min(prior_first, first_observed)
            consensus.last_observed_at = max(prior_last, last_observed)

        # A future human resolution is never overwritten by an automated pass.
        if consensus.status != "resolved":
            consensus.status = status
        consensus.observation_count = len(grouped)
        consensus.source_count = source_count
        consensus.agreement_fields = agreement_fields
        consensus.conflict_fields = conflicts
        consensus.canonical_payload = {
            "fields": canonical,
            "observations": [_event_observation(event) for event in grouped],
            "target": _target(first),
            "anchor_date": _anchor_date(first).isoformat() if _anchor_date(first) else None,
        }
        consensus.provenance = {
            "algorithm": "market_event_consensus_v1",
            "grouping": "exact event_type + canonical target + occurrence date",
            "provider_values_are_not_overwritten": True,
        }
        for event in grouped:
            event.consensus_id = consensus.id
        status_counts[consensus.status] += 1

    await db.flush()
    return {
        "status": "partial" if truncated else "complete",
        "events_considered": len(events),
        "groups_created": created,
        "groups_updated": updated,
        "groups": len(groups),
        "unresolved": unresolved,
        "truncated": truncated,
        "status_counts": dict(sorted(status_counts.items())),
        "window": {"start": start, "end": end},
    }
