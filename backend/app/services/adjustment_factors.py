"""Deterministic adjustment-factor provenance derived from persisted events.

Provider OHLCV adapters commonly return an adjusted series without exposing the
event-level factors used to produce it. When a source supplies explicit event
factors, or a source has persisted complete split events, those inputs are
enough to identify a reproducible adjustment-input set. This module fingerprints
that input set without claiming that dividend-adjusted prices can be rebuilt
from dividend amounts alone.
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


def _event_factor(event: InstrumentEvent) -> Decimal | None:
    """Return only an explicitly provider-supplied or split factor."""

    if event.adjustment_factor is not None:
        return event.adjustment_factor
    if event.event_type is InstrumentEventType.SPLIT:
        return event.split_ratio
    return None


def build_adjustment_factor_snapshot(
    events: Iterable[InstrumentEvent],
) -> AdjustmentFactorSnapshot:
    """Fingerprint complete factor-event inputs without fabricating factors.

    Split ratios and explicit provider-supplied factors are rebuildable inputs
    for a split- or dividend-adjusted series. Dividend amounts remain
    intentionally incomplete: converting them into a price factor requires the
    contemporaneous reference price and the provider adjustment convention,
    neither of which this event table guarantees.
    """

    relevant = [
        event
        for event in events
        if event.event_type in {InstrumentEventType.SPLIT, InstrumentEventType.DIVIDEND}
    ]
    if not relevant:
        return AdjustmentFactorSnapshot(version=None, status="not_observed", event_count=0)

    if any(
        _event_factor(event) is None or _event_factor(event) <= 0 or not event.source_event_key
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
    includes_provider_factors = any(event.adjustment_factor is not None for event in ordered)
    payload = []
    for event in ordered:
        entry = {
            "effective_at": _as_utc(event.event_time).isoformat(),
            "factor": _decimal_text(_event_factor(event)),
            "source": event.source,
            "source_event_key": event.source_event_key,
        }
        # Keep legacy split-only afv1 fingerprints stable. The discriminator
        # is part of the payload only when at least one explicit provider
        # factor is present and therefore changes the adjustment input set.
        if includes_provider_factors:
            entry["factor_kind"] = (
                "provider_supplied" if event.adjustment_factor is not None else "split_ratio"
            )
        payload.append(entry)
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return AdjustmentFactorSnapshot(
        version=f"afv1-{hashlib.sha256(encoded).hexdigest()}",
        status=(
            "rebuildable_provider_factors"
            if includes_provider_factors
            else "rebuildable_split_factors"
        ),
        event_count=len(ordered),
    )


def summarize_persisted_adjustment_factor_provenance(
    observations: Iterable[AdjustmentFactorObservation],
) -> PersistedAdjustmentFactorProvenance:
    """Summarize normalized factor rows without inventing missing factors.

    A persisted version is usable only when every relevant observation has a
    valid factor and all rows agree on the same version. Dividend amounts remain
    explicit opaque evidence when no provider factor accompanies them because
    amounts alone are not sufficient to rebuild a provider's price-adjustment
    convention.
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
        observation.factor is None
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
        status=(
            "rebuildable_provider_factors"
            if any(
                observation.factor_kind == "provider_supplied"
                or (
                    observation.factor_type == InstrumentEventType.DIVIDEND.value
                    and observation.factor is not None
                )
                for observation in relevant
            )
            else "rebuildable_split_factors"
        ),
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
            "factor": (
                event.adjustment_factor
                if event.adjustment_factor is not None
                else event.split_ratio
                if factor_type == InstrumentEventType.SPLIT.value
                else None
            ),
            "factor_kind": (
                "provider_supplied"
                if event.adjustment_factor is not None
                else "split_ratio"
                if factor_type == InstrumentEventType.SPLIT.value
                else None
            ),
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
