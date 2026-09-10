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
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.adjustment_factor import AdjustmentFactorObservation
from app.models.instrument_event import InstrumentEvent, InstrumentEventType
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_observation import DatasetStatus, InstrumentDatasetState


@dataclass(frozen=True, slots=True)
class AdjustmentFactorSnapshot:
    """A reproducible adjustment-input snapshot, or an explicit limitation."""

    version: str | None
    status: str
    event_count: int
    rebuildable_event_count: int = 0
    opaque_event_count: int = 0
    factor_kinds: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PersistedAdjustmentFactorProvenance:
    """The durable factor evidence available for one instrument/source pair."""

    version: str | None
    status: str
    observation_count: int
    distinct_versions: tuple[str, ...] = ()
    rebuildable_observation_count: int = 0
    opaque_observation_count: int = 0
    factor_kinds: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RebuiltOHLCVBar:
    """A pure, locally rebuilt split-adjusted bar.

    The rebuilder deliberately returns a value object instead of mutating ORM
    rows. Callers can compare or persist the result explicitly, preserving the
    raw/provider series and making the derived lineage visible to storage
    code. ``volume`` is scaled inversely to price so split-adjusted notional
    remains comparable.
    """

    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None
    vwap: Decimal | None
    is_adjusted: bool = True
    is_derived: bool = True
    derivation_method: str = "local_split_ratio"


@dataclass(frozen=True, slots=True)
class AdjustmentRebuildResult:
    """Outcome of applying a complete, explicit split-factor set."""

    status: str
    factor_version: str | None = None
    event_count: int = 0
    applied_event_count: int = 0
    bars: tuple[RebuiltOHLCVBar, ...] = ()
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class PersistedAdjustmentViewResult:
    """Receipt for an explicitly requested local derived-view materialization."""

    status: str
    factor_version: str | None = None
    raw_bar_count: int = 0
    persisted_bar_count: int = 0
    updated_bar_count: int = 0
    skipped_provider_bar_count: int = 0
    reason: str | None = None


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


def _observation_factor(observation: AdjustmentFactorObservation) -> Decimal | None:
    """Return a positive split ratio that has an explicit source identity."""

    if observation.factor_type != InstrumentEventType.SPLIT.value:
        return None
    if observation.factor_kind not in (None, "split_ratio"):
        return None
    if observation.factor is None or observation.factor <= 0:
        return None
    if not observation.source_event_key or not observation.factor_version:
        return None
    return observation.factor


def rebuild_split_adjusted_bars(
    raw_bars: Iterable[object],
    observations: Iterable[AdjustmentFactorObservation],
) -> AdjustmentRebuildResult:
    """Rebuild a split-adjusted view from raw bars and explicit split ratios.

    A provider's dividend convention cannot be inferred from a cash amount,
    and provider-labelled factors may use a convention that is not equivalent
    to a split ratio. Those inputs therefore return an explicit unsupported or
    incomplete result and no adjusted bars. For a complete split-only set,
    each bar before an effective split is divided by the cumulative ratio;
    volume is multiplied by that ratio. Events effective at or before a bar's
    timestamp are treated as already reflected in that bar.
    """

    bars = tuple(raw_bars)
    relevant = tuple(
        observation
        for observation in observations
        if observation.factor_type
        in {InstrumentEventType.SPLIT.value, InstrumentEventType.DIVIDEND.value}
    )
    if not relevant:
        return AdjustmentRebuildResult(
            status="not_observed",
            reason="no_split_or_dividend_factor_observations",
        )
    if any(
        observation.factor_type == InstrumentEventType.DIVIDEND.value for observation in relevant
    ):
        return AdjustmentRebuildResult(
            status="unsupported_dividend_factors",
            event_count=len(relevant),
            reason="dividend_adjustment_convention_requires_provider_semantics",
        )
    if any(observation.factor_kind == "provider_supplied" for observation in relevant):
        return AdjustmentRebuildResult(
            status="unsupported_provider_factors",
            event_count=len(relevant),
            reason="provider_factor_orientation_requires_source_contract",
        )

    factors = tuple(_observation_factor(observation) for observation in relevant)
    if any(factor is None for factor in factors):
        return AdjustmentRebuildResult(
            status="provider_native_opaque_incomplete_factor_set",
            factor_version=None,
            event_count=len(relevant),
            reason="every_split_observation_needs_a_positive_ratio_and_version",
        )
    versions = {observation.factor_version for observation in relevant}
    if len(versions) != 1:
        return AdjustmentRebuildResult(
            status="provider_native_opaque_inconsistent_factor_set",
            event_count=len(relevant),
            reason="all_split_observations_must_share_one_factor_version",
        )

    ordered = tuple(
        sorted(
            zip(relevant, factors, strict=True),
            key=lambda pair: (_as_utc(pair[0].effective_at).isoformat(), pair[0].source_event_key),
        )
    )
    rebuilt: list[RebuiltOHLCVBar] = []
    applied_event_keys: set[str] = set()
    for bar in bars:
        bar_ts = _as_utc(bar.ts)
        cumulative = Decimal("1")
        for observation, factor in ordered:
            assert factor is not None  # guarded above; keeps Decimal typing precise
            if _as_utc(observation.effective_at) > bar_ts:
                cumulative /= factor
                applied_event_keys.add(observation.source_event_key)
        rebuilt.append(
            RebuiltOHLCVBar(
                ts=bar.ts,
                open=Decimal(str(bar.open)) * cumulative,
                high=Decimal(str(bar.high)) * cumulative,
                low=Decimal(str(bar.low)) * cumulative,
                close=Decimal(str(bar.close)) * cumulative,
                volume=(Decimal(str(bar.volume)) / cumulative if bar.volume is not None else None),
                vwap=(Decimal(str(bar.vwap)) * cumulative if bar.vwap is not None else None),
            )
        )
    return AdjustmentRebuildResult(
        status="applied",
        factor_version=next(iter(versions)),
        event_count=len(relevant),
        applied_event_count=len(applied_event_keys),
        bars=tuple(rebuilt),
    )


def rebuild_provider_adjusted_bars(
    raw_bars: Iterable[object],
    observations: Iterable[AdjustmentFactorObservation],
) -> AdjustmentRebuildResult:
    """Apply an explicitly provider-supplied backward price-factor contract.

    ``factor_kind=provider_supplied`` means the persisted factor is the
    provider's multiplicative adjusted/raw price factor for bars before the
    event.  This orientation is intentionally separate from
    :func:`rebuild_split_adjusted_bars`, whose ``split_ratio`` inputs are raw
    share ratios and therefore use the reciprocal.  Only explicit positive
    provider factors sharing one version are applied; cash amounts, inferred
    factors, mixed factor kinds, and incomplete versions remain opaque.
    """

    bars = tuple(raw_bars)
    relevant = tuple(
        observation
        for observation in observations
        if observation.factor_type
        in {InstrumentEventType.SPLIT.value, InstrumentEventType.DIVIDEND.value}
    )
    if not relevant:
        return AdjustmentRebuildResult(
            status="not_observed",
            reason="no_split_or_dividend_factor_observations",
        )
    if any(observation.factor_kind != "provider_supplied" for observation in relevant):
        return AdjustmentRebuildResult(
            status="provider_native_opaque_mixed_factor_kinds",
            event_count=len(relevant),
            reason="provider_adjustment_application_requires_explicit_provider_factors",
        )
    factors = tuple(
        observation.factor if observation.factor is not None and observation.factor > 0 else None
        for observation in relevant
    )
    if any(
        factor is None or not observation.source_event_key or not observation.factor_version
        for observation, factor in zip(relevant, factors, strict=True)
    ):
        return AdjustmentRebuildResult(
            status="provider_native_opaque_incomplete_factor_set",
            event_count=len(relevant),
            reason="every_provider_factor_needs_a_positive_factor_and_version",
        )
    versions = {observation.factor_version for observation in relevant}
    if len(versions) != 1:
        return AdjustmentRebuildResult(
            status="provider_native_opaque_inconsistent_factor_set",
            event_count=len(relevant),
            reason="all_provider_factors_must_share_one_factor_version",
        )

    ordered = tuple(
        sorted(
            zip(relevant, factors, strict=True),
            key=lambda pair: (_as_utc(pair[0].effective_at).isoformat(), pair[0].source_event_key),
        )
    )
    rebuilt: list[RebuiltOHLCVBar] = []
    applied_event_keys: set[str] = set()
    for bar in bars:
        bar_ts = _as_utc(bar.ts)
        cumulative = Decimal("1")
        for observation, factor in ordered:
            assert factor is not None  # guarded above; keeps Decimal typing precise
            if _as_utc(observation.effective_at) > bar_ts:
                cumulative *= factor
                applied_event_keys.add(observation.source_event_key)
        rebuilt.append(
            RebuiltOHLCVBar(
                ts=bar.ts,
                open=Decimal(str(bar.open)) * cumulative,
                high=Decimal(str(bar.high)) * cumulative,
                low=Decimal(str(bar.low)) * cumulative,
                close=Decimal(str(bar.close)) * cumulative,
                volume=(Decimal(str(bar.volume)) / cumulative if bar.volume is not None else None),
                vwap=(Decimal(str(bar.vwap)) * cumulative if bar.vwap is not None else None),
                derivation_method="provider_adjustment_factor",
            )
        )
    return AdjustmentRebuildResult(
        status="applied",
        factor_version=next(iter(versions)),
        event_count=len(relevant),
        applied_event_count=len(applied_event_keys),
        bars=tuple(rebuilt),
    )


async def _materialize_local_adjusted_view(
    db: AsyncSession,
    *,
    instrument_id: int,
    timeframe: Timeframe = Timeframe.D1,
    start: datetime | None = None,
    end: datetime | None = None,
    rebuilder: Callable[
        [Iterable[object], Iterable[AdjustmentFactorObservation]], AdjustmentRebuildResult
    ] = rebuild_split_adjusted_bars,
    source_kind: str = "local_split_ratio",
    dataset_key_suffix: str = "local_split_ratio",
    adjustment_label: str = "split_adjusted",
    source_requirement_reason: str = "local_split_view_requires_one_identified_raw_provider_source",
) -> PersistedAdjustmentViewResult:
    """Persist a local adjusted view from one unadjusted source.

    This is an explicit maintenance operation, not an automatic provider
    fallback. It refuses ambiguous raw-source mixes and unsupported or
    incomplete factor evidence, preserves provider-adjusted rows when their
    identity already exists, and records the derived view's factor version in
    a provider-neutral dataset state. The rebuilder and lineage labels are
    supplied by the explicit split or provider-factor contract.
    """

    predicates = [
        OHLCVBar.instrument_id == instrument_id,
        OHLCVBar.timeframe == timeframe,
        OHLCVBar.is_adjusted.is_(False),
        OHLCVBar.is_derived.is_(False),
    ]
    if start is not None:
        predicates.append(OHLCVBar.ts >= _as_utc(start))
    if end is not None:
        predicates.append(OHLCVBar.ts <= _as_utc(end))
    raw_bars = list(
        (await db.execute(select(OHLCVBar).where(*predicates).order_by(OHLCVBar.ts)))
        .scalars()
        .all()
    )
    if not raw_bars:
        return PersistedAdjustmentViewResult(
            status="not_observed",
            reason="no_unadjusted_provider_bars_for_requested_view",
        )

    source_ids = {bar.data_source_id for bar in raw_bars}
    if len(source_ids) != 1 or None in source_ids:
        return PersistedAdjustmentViewResult(
            status="ambiguous_raw_source",
            raw_bar_count=len(raw_bars),
            reason=source_requirement_reason,
        )
    data_source_id = next(iter(source_ids))
    assert data_source_id is not None
    observations = list(
        (
            await db.execute(
                select(AdjustmentFactorObservation)
                .where(
                    AdjustmentFactorObservation.instrument_id == instrument_id,
                    AdjustmentFactorObservation.data_source_id == data_source_id,
                    AdjustmentFactorObservation.effective_at
                    <= max(_as_utc(bar.ts) for bar in raw_bars),
                )
                .order_by(
                    AdjustmentFactorObservation.effective_at,
                    AdjustmentFactorObservation.source_event_key,
                )
            )
        )
        .scalars()
        .all()
    )
    rebuilt = rebuilder(raw_bars, observations)
    if rebuilt.status != "applied":
        return PersistedAdjustmentViewResult(
            status=rebuilt.status,
            factor_version=rebuilt.factor_version,
            raw_bar_count=len(raw_bars),
            reason=rebuilt.reason,
        )

    existing = list(
        (
            await db.execute(
                select(OHLCVBar).where(
                    OHLCVBar.instrument_id == instrument_id,
                    OHLCVBar.timeframe == timeframe,
                    OHLCVBar.is_adjusted.is_(True),
                    OHLCVBar.ts.in_([bar.ts for bar in rebuilt.bars]),
                )
            )
        )
        .scalars()
        .all()
    )
    existing_by_ts = {_as_utc(bar.ts): bar for bar in existing}
    persisted = updated = skipped_provider = 0
    materialized_timestamps: list[datetime] = []
    now = datetime.now(UTC)
    for derived in rebuilt.bars:
        prior = existing_by_ts.get(_as_utc(derived.ts))
        if prior is not None:
            if prior.is_derived is False:
                # Persisted provider-adjusted evidence is authoritative and is
                # never replaced by a local reconstruction.
                skipped_provider += 1
                continue
            if not (
                prior.derivation_method == source_kind
                or (
                    source_kind == "provider_adjustment_factor"
                    and prior.derivation_method == "local_split_ratio"
                )
            ):
                # Keep a derived view from an unrelated contract intact.  The
                # explicit provider-factor view is the one deliberate upgrade
                # path: provider-declared factors outrank local split ratios,
                # while the split-only path cannot downgrade that evidence.
                skipped_provider += 1
                continue
        values = {
            "instrument_id": instrument_id,
            "data_source_id": None,
            "timeframe": timeframe,
            "ts": derived.ts,
            "open": derived.open,
            "high": derived.high,
            "low": derived.low,
            "close": derived.close,
            "volume": derived.volume,
            "vwap": derived.vwap,
            "is_adjusted": True,
            "is_derived": True,
            "source_timeframe": timeframe.value,
            "derivation_method": derived.derivation_method,
            "derived_at": now,
            "source_bar_count": 1,
            "source_start": derived.ts,
            "source_end": derived.ts,
        }
        if prior is None:
            db.add(OHLCVBar(**values))
            persisted += 1
            materialized_timestamps.append(derived.ts)
        else:
            for key, value in values.items():
                setattr(prior, key, value)
            updated += 1
            materialized_timestamps.append(derived.ts)

    if materialized_timestamps:
        dataset_key = f"{timeframe.value}:adj:{dataset_key_suffix}"
        state = (
            await db.execute(
                select(InstrumentDatasetState).where(
                    InstrumentDatasetState.instrument_id == instrument_id,
                    InstrumentDatasetState.data_source_id.is_(None),
                    InstrumentDatasetState.dataset_type == "ohlcv",
                    InstrumentDatasetState.dataset_key == dataset_key,
                )
            )
        ).scalar_one_or_none()
        if state is None:
            state = InstrumentDatasetState(
                instrument_id=instrument_id,
                data_source_id=None,
                dataset_type="ohlcv",
                dataset_key=dataset_key,
                version=1,
            )
            db.add(state)
        else:
            state.version = max(1, state.version) + 1
        state.status = DatasetStatus.FRESH
        state.observed_at = now
        state.fetched_at = now
        state.coverage_start = min(materialized_timestamps, key=_as_utc)
        state.coverage_end = max(materialized_timestamps, key=_as_utc)
        state.snapshot_hash = rebuilt.factor_version
        state.extra_data = {
            "bar_count": len(materialized_timestamps),
            "adjusted": True,
            "adjustment": adjustment_label,
            "source_kind": source_kind,
            "provider_source_id": data_source_id,
            "source_timeframe": timeframe.value,
            "derivation_method": source_kind,
            "adjustment_provenance": {
                "mode": adjustment_label,
                "source_kind": source_kind,
                "factor_status": (
                    "rebuildable_provider_factors"
                    if source_kind == "provider_adjustment_factor"
                    else "rebuildable_split_factors"
                ),
                "factor_version": rebuilt.factor_version,
                "contract_version": 1,
            },
        }
    await db.flush()
    return PersistedAdjustmentViewResult(
        status="applied",
        factor_version=rebuilt.factor_version,
        raw_bar_count=len(raw_bars),
        persisted_bar_count=persisted,
        updated_bar_count=updated,
        skipped_provider_bar_count=skipped_provider,
    )


async def materialize_local_split_adjusted_view(
    db: AsyncSession,
    *,
    instrument_id: int,
    timeframe: Timeframe = Timeframe.D1,
    start: datetime | None = None,
    end: datetime | None = None,
) -> PersistedAdjustmentViewResult:
    """Persist a local split-adjusted view from one unadjusted source."""

    return await _materialize_local_adjusted_view(
        db,
        instrument_id=instrument_id,
        timeframe=timeframe,
        start=start,
        end=end,
    )


async def materialize_local_provider_adjusted_view(
    db: AsyncSession,
    *,
    instrument_id: int,
    timeframe: Timeframe = Timeframe.D1,
    start: datetime | None = None,
    end: datetime | None = None,
) -> PersistedAdjustmentViewResult:
    """Persist a provider-factor-adjusted view from one unadjusted source.

    Provider factors are applied only when the persisted observation contract
    identifies one positive factor set and one factor version. The operation
    is explicit and never replaces a provider-adjusted row at the same
    timestamp.
    """

    return await _materialize_local_adjusted_view(
        db,
        instrument_id=instrument_id,
        timeframe=timeframe,
        start=start,
        end=end,
        rebuilder=rebuild_provider_adjusted_bars,
        source_kind="provider_adjustment_factor",
        dataset_key_suffix="provider_adjustment_factor",
        adjustment_label="provider_adjusted",
        source_requirement_reason=(
            "local_provider_view_requires_one_identified_raw_provider_source"
        ),
    )


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

    rebuildable_events = [
        event
        for event in relevant
        if _event_factor(event) is not None
        and _event_factor(event) > 0
        and bool(event.source_event_key)
    ]
    factor_kinds = tuple(
        sorted(
            {
                "provider_supplied"
                if event.adjustment_factor is not None
                else "split_ratio"
                if event.event_type is InstrumentEventType.SPLIT
                else "opaque"
                for event in relevant
            }
        )
    )

    if any(
        _event_factor(event) is None or _event_factor(event) <= 0 or not event.source_event_key
        for event in relevant
    ):
        return AdjustmentFactorSnapshot(
            version=None,
            status="provider_native_opaque_incomplete_factor_set",
            event_count=len(relevant),
            rebuildable_event_count=len(rebuildable_events),
            opaque_event_count=len(relevant) - len(rebuildable_events),
            factor_kinds=factor_kinds,
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
        rebuildable_event_count=len(rebuildable_events),
        opaque_event_count=len(relevant) - len(rebuildable_events),
        factor_kinds=factor_kinds,
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

    rebuildable_observations = [
        observation
        for observation in relevant
        if observation.factor is not None
        and observation.factor > 0
        and bool(observation.source_event_key)
        and bool(observation.factor_version)
    ]
    factor_kinds = tuple(
        sorted(
            {
                str(observation.factor_kind)
                if observation.factor_kind
                else "split_ratio"
                if observation.factor_type == InstrumentEventType.SPLIT.value
                and observation.factor is not None
                else "opaque"
                for observation in relevant
            }
        )
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
            rebuildable_observation_count=len(rebuildable_observations),
            opaque_observation_count=len(relevant) - len(rebuildable_observations),
            factor_kinds=factor_kinds,
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
            rebuildable_observation_count=len(rebuildable_observations),
            opaque_observation_count=len(relevant) - len(rebuildable_observations),
            factor_kinds=factor_kinds,
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
        rebuildable_observation_count=len(rebuildable_observations),
        opaque_observation_count=len(relevant) - len(rebuildable_observations),
        factor_kinds=factor_kinds,
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
