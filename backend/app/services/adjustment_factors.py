"""Deterministic adjustment-factor provenance derived from persisted events.

Provider OHLCV adapters commonly return an adjusted series without exposing the
event-level factors used to produce it. When a source has persisted complete
split events, however, those events are enough to identify a reproducible
split-adjustment input set. This module fingerprints that input set without
claiming that dividend-adjusted prices can be rebuilt from dividend amounts
alone.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.adjustment_factor import AdjustmentFactorObservation
from app.models.instrument_event import InstrumentEvent, InstrumentEventType


@dataclass(frozen=True, slots=True)
class AdjustmentFactorSnapshot:
    """A reproducible adjustment-input snapshot, or an explicit limitation."""

    version: str | None
    status: str
    event_count: int


@dataclass(frozen=True, slots=True)
class PersistedAdjustmentFactorProvenance:
    """The durable factor evidence available for one instrument/source pair."""

    version: str | None
    status: str
    observation_count: int
    distinct_versions: tuple[str, ...] = ()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.normalize(), "f")


def build_adjustment_factor_snapshot(
    events: Iterable[InstrumentEvent],
) -> AdjustmentFactorSnapshot:
    """Fingerprint a complete split-event set without fabricating factors.

    Split ratios are rebuildable inputs for a split-adjusted series. Dividend
    amounts are intentionally treated as incomplete: converting them into a
    price factor requires the contemporaneous reference price and the provider
    adjustment convention, neither of which this event table guarantees.
    """

    relevant = [
        event
        for event in events
        if event.event_type in {InstrumentEventType.SPLIT, InstrumentEventType.DIVIDEND}
    ]
    if not relevant:
        return AdjustmentFactorSnapshot(version=None, status="not_observed", event_count=0)

    if any(
        event.event_type is InstrumentEventType.DIVIDEND
        or event.split_ratio is None
        or event.split_ratio <= 0
        or not event.source_event_key
        for event in relevant
    ):
        return AdjustmentFactorSnapshot(
            version=None,
            status="provider_native_opaque_incomplete_factor_set",
            event_count=len(relevant),
        )

    ordered = sorted(
        relevant,
        key=lambda event: (
            _as_utc(event.event_time).isoformat(),
            event.source,
            event.source_event_key,
        ),
    )
    payload = [
        {
            "effective_at": _as_utc(event.event_time).isoformat(),
            "factor": _decimal_text(event.split_ratio),
            "source": event.source,
            "source_event_key": event.source_event_key,
        }
        for event in ordered
    ]
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return AdjustmentFactorSnapshot(
        version=f"afv1-{hashlib.sha256(encoded).hexdigest()}",
        status="rebuildable_split_factors",
        event_count=len(ordered),
    )


def summarize_persisted_adjustment_factor_provenance(
    observations: Iterable[AdjustmentFactorObservation],
) -> PersistedAdjustmentFactorProvenance:
    """Summarize normalized factor rows without inventing missing factors.

    A persisted version is usable only when every split observation is valid
    and all rows agree on the same version. Dividend amounts remain explicit
    opaque evidence because they are not sufficient to rebuild a provider's
    price-adjustment convention.
    """

    relevant = [
        observation
        for observation in observations
        if observation.factor_type
        in {InstrumentEventType.SPLIT.value, InstrumentEventType.DIVIDEND.value}
    ]
    if not relevant:
        return PersistedAdjustmentFactorProvenance(
            version=None,
            status="not_observed",
            observation_count=0,
        )

    if any(
        observation.factor_type == InstrumentEventType.DIVIDEND.value
        or observation.factor is None
        or observation.factor <= 0
        or not observation.source_event_key
        or not observation.factor_version
        for observation in relevant
    ):
        return PersistedAdjustmentFactorProvenance(
            version=None,
            status="provider_native_opaque_incomplete_factor_set",
            observation_count=len(relevant),
            distinct_versions=tuple(
                sorted(
                    {
                        observation.factor_version
                        for observation in relevant
                        if observation.factor_version
                    }
                )
            ),
        )

    versions = tuple(
        sorted(
            {observation.factor_version for observation in relevant if observation.factor_version}
        )
    )
    if len(versions) != 1:
        return PersistedAdjustmentFactorProvenance(
            version=None,
            status="provider_native_opaque_inconsistent_factor_set",
            observation_count=len(relevant),
            distinct_versions=versions,
        )
    return PersistedAdjustmentFactorProvenance(
        version=versions[0],
        status="rebuildable_split_factors",
        observation_count=len(relevant),
        distinct_versions=versions,
    )


async def persist_adjustment_factor_observations(
    db: AsyncSession,
    *,
    instrument_id: int,
    data_source_id: int,
    provider_symbol: str | None,
    events: Iterable[InstrumentEvent],
) -> int:
    """Persist normalized split/dividend evidence for one provider response.

    The operation is intentionally portable across the unit-test SQLite
    adapter and production Postgres. It updates the same natural key in place,
    preserving one durable observation per source event while allowing a later
    provider response to fill corrected payload values.
    """

    relevant = [
        event
        for event in events
        if event.event_type in {InstrumentEventType.SPLIT, InstrumentEventType.DIVIDEND}
        and event.source_event_key
    ]
    if not relevant:
        return 0
    snapshot = build_adjustment_factor_snapshot(relevant)
    persisted = 0
    for event in relevant:
        factor_type = event.event_type.value
        effective_at = _as_utc(event.event_time)
        existing = (
            await db.execute(
                select(AdjustmentFactorObservation).where(
                    AdjustmentFactorObservation.instrument_id == instrument_id,
                    AdjustmentFactorObservation.data_source_id == data_source_id,
                    AdjustmentFactorObservation.factor_type == factor_type,
                    AdjustmentFactorObservation.effective_at == effective_at,
                    AdjustmentFactorObservation.source_event_key == event.source_event_key,
                )
            )
        ).scalar_one_or_none()
        values = {
            "instrument_id": instrument_id,
            "data_source_id": data_source_id,
            "provider_symbol": provider_symbol,
            "factor_type": factor_type,
            "effective_at": effective_at,
            "factor": event.split_ratio if factor_type == InstrumentEventType.SPLIT.value else None,
            "amount": event.dividend_amount
            if factor_type == InstrumentEventType.DIVIDEND.value
            else None,
            "source_event_key": event.source_event_key,
            "observed_at": _as_utc(event.fetched_at),
            "factor_version": snapshot.version,
            "raw_payload": event.raw_payload,
        }
        if existing is None:
            db.add(AdjustmentFactorObservation(**values))
        else:
            for key, value in values.items():
                setattr(existing, key, value)
        persisted += 1
    await db.flush()
    return persisted
