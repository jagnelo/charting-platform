"""Materialise coarse history from one selected persisted D1 series.

Derived rows retain a series identity tied to their D1 source. Provider rows
remain separately stored and are not spliced into the derived series.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import TypeVar

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instrument import Instrument
from app.models.market_data_foundation import (
    MarketSeries,
    MarketSeriesDefault,
)
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_observation import DatasetStatus, InstrumentDatasetState

DERIVATION_METHOD = "d1_ohlcv_xnys_calendar_aggregation"
_BarLike = TypeVar("_BarLike", bound=OHLCVBar)


def _state_has_historical_provenance(
    state: InstrumentDatasetState,
    end: datetime | None,
) -> bool:
    """Return whether factor state can certify a dated coarse-timeframe view."""

    if end is None:
        return True
    for value in (state.coverage_end, state.fetched_at):
        if value is None:
            return False
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        if normalized.astimezone(UTC) > end:
            return False
    return True


async def _canonical_d1_factor_version(
    db: AsyncSession,
    instrument_id: int,
    *,
    adjusted: bool,
    end: datetime | None = None,
) -> str | None:
    """Return one verified D1 factor version suitable for derived lineage.

    Coarse rows inherit the canonical adjusted D1 contract, but must not claim
    a rebuildable factor version when the contributing provider sources disagree
    or any source lacks explicit provenance. Raw rows never carry adjustment
    provenance.
    """

    if not adjusted:
        return None
    from app.services.market_data import _default_series_bar_condition

    d1_source_statement = select(OHLCVBar.data_source_id).where(
        OHLCVBar.instrument_id == instrument_id,
        OHLCVBar.timeframe == Timeframe.D1,
        OHLCVBar.is_adjusted.is_(True),
        OHLCVBar.is_derived.is_(False),
        OHLCVBar.data_source_id.is_not(None),
        _default_series_bar_condition(instrument_id, Timeframe.D1, True),
    )
    if end is not None:
        normalized_end = end if end.tzinfo is not None else end.replace(tzinfo=UTC)
        normalized_end = normalized_end.astimezone(UTC)
        d1_source_statement = d1_source_statement.where(OHLCVBar.ts <= normalized_end)
    else:
        normalized_end = None
    source_ids = set((await db.execute(d1_source_statement)).scalars().all())
    versions: set[str] = set()
    if source_ids:
        states = (
            (
                await db.execute(
                    select(InstrumentDatasetState).where(
                        InstrumentDatasetState.instrument_id == instrument_id,
                        InstrumentDatasetState.data_source_id.in_(source_ids),
                        InstrumentDatasetState.dataset_type == "ohlcv",
                        InstrumentDatasetState.dataset_key == "D1:adj",
                    )
                )
            )
            .scalars()
            .all()
        )
        if len(states) != len(source_ids):
            return None

        for state in states:
            if not _state_has_historical_provenance(state, normalized_end):
                # A provider state whose factor evidence extends beyond a
                # historical cutoff, or lacks fetch/coverage timestamps, cannot
                # safely certify the earlier slice.
                return None
            provenance = (state.extra_data or {}).get("adjustment_provenance")
            if not isinstance(provenance, dict):
                return None
            status = provenance.get("factor_status")
            version = provenance.get("factor_version")
            if status not in {"rebuildable_split_factors", "rebuildable_provider_factors"}:
                return None
            if not isinstance(version, str) or not version:
                return None
            versions.add(version)

    local_row_statement = select(OHLCVBar.derivation_method).where(
        OHLCVBar.instrument_id == instrument_id,
        OHLCVBar.timeframe == Timeframe.D1,
        OHLCVBar.is_adjusted.is_(True),
        OHLCVBar.is_derived.is_(True),
        OHLCVBar.derivation_method.in_(("local_split_ratio", "provider_adjustment_factor")),
        _default_series_bar_condition(instrument_id, Timeframe.D1, True),
    )
    if normalized_end is not None:
        local_row_statement = local_row_statement.where(OHLCVBar.ts <= normalized_end)
    local_methods = {row for row in (await db.execute(local_row_statement)).scalars().all() if row}
    if local_methods:
        local_state_statement = select(InstrumentDatasetState).where(
            InstrumentDatasetState.instrument_id == instrument_id,
            InstrumentDatasetState.data_source_id.is_(None),
            InstrumentDatasetState.dataset_type == "ohlcv",
            InstrumentDatasetState.dataset_key.in_(
                (
                    "D1:adj:local_split_ratio",
                    "D1:adj:provider_adjustment_factor",
                )
            ),
        )
        local_states = (await db.execute(local_state_statement)).scalars().all()
        expected_local_keys = {
            f"D1:adj:{method}"
            for method in local_methods
            if method in {"local_split_ratio", "provider_adjustment_factor"}
        }
        if (
            not expected_local_keys
            or {state.dataset_key for state in local_states} != expected_local_keys
        ):
            return None
        for local_state in local_states:
            if not _state_has_historical_provenance(local_state, normalized_end):
                # The local factor state may include a later event than the
                # dated view, or may lack temporal proof. Without a historical
                # state version, keep lineage explicitly unversioned rather than
                # claiming future evidence.
                return None
            provenance = (local_state.extra_data or {}).get("adjustment_provenance")
            if not isinstance(provenance, dict):
                return None
            if provenance.get("factor_status") not in {
                "rebuildable_split_factors",
                "rebuildable_provider_factors",
            }:
                return None
            local_version = provenance.get("factor_version")
            if not isinstance(local_version, str) or not local_version:
                return None
            versions.add(local_version)

    if not versions:
        return None
    return versions.pop() if len(versions) == 1 else None


def _period_key(ts: datetime, timeframe: Timeframe) -> tuple[int, int]:
    value = ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)
    value = value.astimezone(UTC)
    if timeframe == Timeframe.W1:
        iso = value.date().isocalendar()
        return (iso.year, iso.week)
    if timeframe == Timeframe.MN:
        return (value.year, value.month)
    raise ValueError(f"Unsupported derived timeframe: {timeframe.value}")


def _signature_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.astimezone(UTC).isoformat()


async def _canonical_d1_signature(
    db: AsyncSession,
    instrument_id: int,
    *,
    adjusted: bool,
) -> dict[str, object]:
    """Return a cheap persisted-input watermark for lazy coarse-view refresh.

    The signature uses aggregate bounds/count, the represented series/source
    identities, and their dataset observation watermarks. It does not load or
    re-aggregate the D1 rows on a normal W1/MN read.
    """

    from app.services.market_data import _default_series_bar_condition

    selected_d1 = _default_series_bar_condition(instrument_id, Timeframe.D1, adjusted)
    statement = select(
        func.count(OHLCVBar.id),
        func.min(OHLCVBar.ts),
        func.max(OHLCVBar.ts),
    ).where(
        OHLCVBar.instrument_id == instrument_id,
        OHLCVBar.timeframe == Timeframe.D1,
        OHLCVBar.is_adjusted.is_(adjusted),
        selected_d1,
    )
    count, coverage_start, coverage_end = (await db.execute(statement)).one()
    source_statement = (
        select(OHLCVBar.data_source_id, OHLCVBar.market_series_id)
        .where(
            OHLCVBar.instrument_id == instrument_id,
            OHLCVBar.timeframe == Timeframe.D1,
            OHLCVBar.is_adjusted.is_(adjusted),
            selected_d1,
        )
        .distinct()
    )
    identities = (await db.execute(source_statement)).all()
    source_ids = sorted({int(source_id) for source_id, _ in identities if source_id is not None})
    series_ids = sorted({int(series_id) for _, series_id in identities if series_id is not None})
    state_key = f"D1:{'adj' if adjusted else 'raw'}"
    state_statement = select(InstrumentDatasetState).where(
        InstrumentDatasetState.instrument_id == instrument_id,
        InstrumentDatasetState.dataset_type == "ohlcv",
        InstrumentDatasetState.data_source_id.in_(source_ids)
        if source_ids
        else InstrumentDatasetState.data_source_id.is_(None),
        InstrumentDatasetState.dataset_key == state_key,
    )
    states = (await db.execute(state_statement)).scalars().all()
    watermarks = sorted(
        (
            {
                "data_source_id": state.data_source_id,
                "version": state.version,
                "status": getattr(state.status, "value", state.status),
                "fetched_at": _signature_timestamp(state.fetched_at),
                "coverage_start": _signature_timestamp(state.coverage_start),
                "coverage_end": _signature_timestamp(state.coverage_end),
            }
            for state in states
        ),
        key=lambda item: (-1 if item["data_source_id"] is None else int(item["data_source_id"])),
    )
    return {
        "adjusted": adjusted,
        "bar_count": int(count or 0),
        "coverage_start": _signature_timestamp(coverage_start),
        "coverage_end": _signature_timestamp(coverage_end),
        "data_source_ids": source_ids,
        "market_series_ids": series_ids,
        "source_watermarks": watermarks,
    }


async def derived_timeframe_needs_refresh(
    db: AsyncSession,
    instrument_id: int,
    timeframe: Timeframe,
    *,
    adjusted: bool = True,
) -> bool:
    """Check whether persisted W1/MN outputs still match the D1 source.

    Legacy derived rows lack an input signature, so the first local read after
    this check was added refreshes them once. Subsequent reads compare only a
    small D1 aggregate and dataset watermarks; they do not aggregate bars or
    call a provider.
    """

    if timeframe not in (Timeframe.W1, Timeframe.MN):
        return False
    signature = await _canonical_d1_signature(db, instrument_id, adjusted=adjusted)
    if signature["bar_count"] == 0:
        return False
    derived_count_result = await db.execute(
        select(func.count(OHLCVBar.id)).where(
            OHLCVBar.instrument_id == instrument_id,
            OHLCVBar.timeframe == timeframe,
            OHLCVBar.is_adjusted.is_(adjusted),
            OHLCVBar.is_derived.is_(True),
        )
    )
    derived_count = int(derived_count_result.scalar_one() or 0)
    if derived_count == 0:
        return True
    state = (
        await db.execute(
            select(InstrumentDatasetState).where(
                InstrumentDatasetState.instrument_id == instrument_id,
                InstrumentDatasetState.data_source_id.is_(None),
                InstrumentDatasetState.dataset_type == "ohlcv",
                InstrumentDatasetState.dataset_key
                == f"{timeframe.value}:{'adj' if adjusted else 'raw'}",
            )
        )
    ).scalar_one_or_none()
    stored_signature = (state.extra_data or {}).get("source_d1_signature") if state else None
    if state is not None:
        stored_bar_count = (state.extra_data or {}).get("derived_bar_count")
        if (
            state.status in {DatasetStatus.PENDING, DatasetStatus.FAILED}
            or isinstance(stored_bar_count, bool)
            or not isinstance(stored_bar_count, int)
            or stored_bar_count != derived_count
        ):
            return True
    if stored_signature is not None:
        return stored_signature != signature
    if state is None:
        return True

    # States written before source signatures were introduced can still be
    # checked without rebuilding every complete cache. A newer D1 observation
    # means bars may have been added or corrected; changed source bounds catch
    # backfills even when an older producer did not advance fetched_at.
    source_watermarks = signature["source_watermarks"]
    newest_source_fetch = max(
        (
            watermark["fetched_at"]
            for watermark in source_watermarks
            if watermark["fetched_at"] is not None
        ),
        default=None,
    )
    if newest_source_fetch is not None and state.fetched_at is not None:
        if newest_source_fetch > _signature_timestamp(state.fetched_at):
            return True

    source_bounds = await db.execute(
        select(func.min(OHLCVBar.source_start), func.max(OHLCVBar.source_end)).where(
            OHLCVBar.instrument_id == instrument_id,
            OHLCVBar.timeframe == timeframe,
            OHLCVBar.is_adjusted.is_(adjusted),
            OHLCVBar.is_derived.is_(True),
        )
    )
    derived_source_start, derived_source_end = source_bounds.one()
    current_source_start = signature["coverage_start"]
    current_source_end = signature["coverage_end"]
    return (
        derived_source_start is None
        or derived_source_end is None
        or (
            current_source_start is not None
            and current_source_start < _signature_timestamp(derived_source_start)
        )
        or (
            current_source_end is not None
            and current_source_end > _signature_timestamp(derived_source_end)
        )
    )


def aggregate_d1_bars(bars: Iterable[_BarLike], timeframe: Timeframe) -> list[dict[str, object]]:
    """Aggregate D1 bars into deterministic W1 or MN payloads.

    The first and last observed sessions define the output bounds.  Missing
    sessions remain missing; they are not forward-filled or invented.
    """

    if timeframe not in (Timeframe.W1, Timeframe.MN):
        raise ValueError("Only W1 and MN can be derived from D1 bars")
    groups: dict[tuple[int, int], list[_BarLike]] = defaultdict(list)
    for bar in bars:
        groups[_period_key(bar.ts, timeframe)].append(bar)

    payloads: list[dict[str, object]] = []
    for members in groups.values():
        ordered = sorted(
            members,
            key=lambda item: (
                item.ts if item.ts.tzinfo is not None else item.ts.replace(tzinfo=UTC)
            ).astimezone(UTC),
        )
        first_ts = (
            ordered[0].ts if ordered[0].ts.tzinfo is not None else ordered[0].ts.replace(tzinfo=UTC)
        ).astimezone(UTC)
        last_ts = (
            ordered[-1].ts
            if ordered[-1].ts.tzinfo is not None
            else ordered[-1].ts.replace(tzinfo=UTC)
        ).astimezone(UTC)
        volumes = [bar.volume for bar in ordered if bar.volume is not None]
        vwap = None
        if volumes and len(volumes) == len(ordered) and sum(volumes) > 0:
            vwap = sum((bar.vwap or bar.close) * bar.volume for bar in ordered) / sum(volumes)
        payloads.append(
            {
                "ts": first_ts,
                "open": ordered[0].open,
                "high": max(bar.high for bar in ordered),
                "low": min(bar.low for bar in ordered),
                "close": ordered[-1].close,
                "volume": sum(volumes) if len(volumes) == len(ordered) else None,
                "vwap": vwap,
                "source_bar_count": len(ordered),
                "source_start": first_ts,
                "source_end": last_ts,
                "period_key": _period_key(ordered[0].ts, timeframe),
            }
        )
    return sorted(payloads, key=lambda item: item["ts"])


async def materialize_derived_timeframes(
    db: AsyncSession,
    instrument_id: int,
    *,
    adjusted: bool = True,
    end: datetime | None = None,
) -> dict[str, int]:
    """Rebuild one coherent derived W1/MN series from selected D1 rows.

    Provider-supplied coarse rows and derived rows are stored in distinct
    series. Ordinary reads choose one complete series; they never splice feeds
    at individual timestamps.

    When ``end`` is supplied, only D1 evidence through that inclusive UTC bound
    is rebuilt.  Derived rows after the bound remain untouched; this is required
    for dated history jobs, where a newer local cache must not be rewritten as if
    it were part of the historical point-in-time view.
    """

    normalized_end = None
    if end is not None:
        normalized_end = end if end.tzinfo is not None else end.replace(tzinfo=UTC)
        normalized_end = normalized_end.astimezone(UTC)

    from app.services.market_data import _default_series_bar_condition
    from app.services.market_series import (
        SeriesScope,
        adjustment_scope_predicate,
        effective_series_adjustment_basis,
        get_or_create_series,
        normalize_adjustment_basis,
    )

    d1_statement = select(OHLCVBar).where(
        OHLCVBar.instrument_id == instrument_id,
        OHLCVBar.timeframe == Timeframe.D1,
        OHLCVBar.is_adjusted.is_(adjusted),
        _default_series_bar_condition(instrument_id, Timeframe.D1, adjusted),
    )
    if normalized_end is not None:
        d1_statement = d1_statement.where(OHLCVBar.ts <= normalized_end)
    d1_bars = (await db.execute(d1_statement.order_by(OHLCVBar.ts))).scalars().all()
    if not d1_bars:
        return {Timeframe.W1.value: 0, Timeframe.MN.value: 0}
    selected_series_ids = {
        int(bar.market_series_id) for bar in d1_bars if bar.market_series_id is not None
    }
    if len(selected_series_ids) > 1:
        raise ValueError("selected daily history spans multiple market series")
    source_series = (
        await db.get(MarketSeries, next(iter(selected_series_ids))) if selected_series_ids else None
    )
    source_data_source_ids = {
        int(bar.data_source_id) for bar in d1_bars if bar.data_source_id is not None
    }
    if len(source_data_source_ids) > 1:
        raise ValueError("selected daily history spans multiple data sources")
    source_data_source_id = (
        source_series.data_source_id
        if source_series is not None
        else next(iter(source_data_source_ids), None)
    )
    if source_series is not None:
        adjustment_basis = effective_series_adjustment_basis(source_series, adjusted)
        adjustment_version = source_series.adjustment_version
        session_code = source_series.session_code
    else:
        basis_values = {bar.adjustment_basis for bar in d1_bars if bar.adjustment_basis is not None}
        version_values = {bar.adjustment_version for bar in d1_bars if bar.adjustment_version}
        if len(basis_values) > 1 or len(version_values) > 1:
            raise ValueError("selected daily history has inconsistent adjustment lineage")
        adjustment_version = next(iter(version_values), "legacy-unversioned")
        adjustment_basis = normalize_adjustment_basis(
            next(iter(basis_values), None), adjustment_version, adjusted
        )
        session_code = d1_bars[0].session if d1_bars else "regular"
    source_identity = (
        str(source_series.id)
        if source_series is not None
        else str(source_data_source_id)
        if source_data_source_id is not None
        else "legacy"
    )

    canonical_factor_version = await _canonical_d1_factor_version(
        db,
        instrument_id,
        adjusted=adjusted,
        end=normalized_end,
    )
    source_d1_signature = (
        await _canonical_d1_signature(db, instrument_id, adjusted=adjusted)
        if normalized_end is None
        else None
    )
    result: dict[str, int] = {}
    for timeframe in (Timeframe.W1, Timeframe.MN):
        derived_series = None
        if d1_bars:
            existing_default = (
                await db.execute(
                    select(MarketSeriesDefault).where(
                        MarketSeriesDefault.instrument_id == instrument_id,
                        MarketSeriesDefault.timeframe == timeframe.value,
                        MarketSeriesDefault.is_adjusted == adjusted,
                    )
                )
            ).scalar_one_or_none()
            existing_canonical = (
                await db.execute(
                    select(MarketSeries.id).where(
                        MarketSeries.instrument_id == instrument_id,
                        MarketSeries.timeframe == timeframe.value,
                        MarketSeries.is_canonical.is_(True),
                        MarketSeries.is_active.is_(True),
                        adjustment_scope_predicate(adjusted),
                    )
                )
            ).first()
            derived_series = await get_or_create_series(
                db,
                SeriesScope(
                    instrument_id=instrument_id,
                    exchange_id=source_series.exchange_id if source_series is not None else None,
                    data_source_id=source_data_source_id,
                    feed_scope=f"derived-d1-{source_identity}",
                    session_code=session_code,
                    timeframe=timeframe.value,
                    adjustment_basis=adjustment_basis,
                    adjustment_version=adjustment_version,
                ),
                canonical=(existing_default is None and existing_canonical is None),
                source_series_key=f"derived-from-d1:{source_identity}",
                provenance={
                    "derived_from_timeframe": Timeframe.D1.value,
                    "derived_from_market_series_id": (
                        source_series.id if source_series is not None else None
                    ),
                    "derived_from_data_source_id": source_data_source_id,
                    "derivation_method": DERIVATION_METHOD,
                },
            )
        delete_statement = delete(OHLCVBar).where(
            OHLCVBar.instrument_id == instrument_id,
            OHLCVBar.timeframe == timeframe,
            OHLCVBar.is_adjusted.is_(adjusted),
            OHLCVBar.is_derived.is_(True),
            OHLCVBar.market_series_id == derived_series.id
            if derived_series is not None
            else OHLCVBar.market_series_id.is_(None),
        )
        if normalized_end is not None:
            delete_statement = delete_statement.where(OHLCVBar.ts <= normalized_end)
        await db.execute(delete_statement.execution_options(synchronize_session=False))
        payloads = [payload for payload in aggregate_d1_bars(d1_bars, timeframe)]
        now = datetime.now(UTC)
        effective_adjustment_basis = (
            adjustment_basis.value if hasattr(adjustment_basis, "value") else str(adjustment_basis)
        )
        effective_adjustment_version = adjustment_version or "legacy-unversioned"
        db.add_all(
            [
                OHLCVBar(
                    instrument_id=instrument_id,
                    data_source_id=source_data_source_id,
                    market_series_id=derived_series.id if derived_series is not None else None,
                    timeframe=timeframe,
                    ts=payload["ts"],
                    open=payload["open"],
                    high=payload["high"],
                    low=payload["low"],
                    close=payload["close"],
                    volume=payload["volume"],
                    vwap=payload["vwap"],
                    is_adjusted=adjusted,
                    adjustment_basis=effective_adjustment_basis,
                    adjustment_version=effective_adjustment_version,
                    provenance={
                        "derivation_method": DERIVATION_METHOD,
                        "source_timeframe": Timeframe.D1.value,
                        "source_data_source_id": source_data_source_id,
                        "source_market_series_id": (
                            source_series.id if source_series is not None else None
                        ),
                        "adjustment_basis": effective_adjustment_basis,
                        "adjustment_version": effective_adjustment_version,
                    },
                    is_derived=True,
                    source_timeframe=Timeframe.D1.value,
                    derivation_method=DERIVATION_METHOD,
                    derived_at=now,
                    source_bar_count=payload["source_bar_count"],
                    source_start=payload["source_start"],
                    source_end=payload["source_end"],
                    session=session_code,
                    scope_key=(
                        f"series:{derived_series.id}:{session_code}"
                        if derived_series is not None
                        else "legacy:regular"
                    ),
                )
                for payload in payloads
            ]
        )
        # The application AsyncSession disables autoflush. Read the just-added
        # derived rows explicitly before projecting their count and coverage.
        await db.flush()
        # Keep coverage/freshness state aligned with derived rows. A
        # provider-neutral state makes the local coverage API explicit about
        # source timeframe, derivation method, adjustment mode, and version.
        dataset_key = f"{timeframe.value}:{'adj' if adjusted else 'raw'}"
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
        state_was_new = state is None
        if state is None:
            state = InstrumentDatasetState(
                instrument_id=instrument_id,
                data_source_id=None,
                dataset_type="ohlcv",
                dataset_key=dataset_key,
                version=1,
            )
            db.add(state)
        source_state = None
        if source_data_source_id is not None:
            source_dataset_key = f"D1:{'adj' if adjusted else 'raw'}"
            source_state = (
                await db.execute(
                    select(InstrumentDatasetState).where(
                        InstrumentDatasetState.instrument_id == instrument_id,
                        InstrumentDatasetState.data_source_id == source_data_source_id,
                        InstrumentDatasetState.dataset_type == "ohlcv",
                        InstrumentDatasetState.dataset_key == source_dataset_key,
                    )
                )
            ).scalar_one_or_none()
        derived_rows = (
            (
                await db.execute(
                    select(OHLCVBar)
                    .where(
                        OHLCVBar.instrument_id == instrument_id,
                        OHLCVBar.timeframe == timeframe,
                        OHLCVBar.is_adjusted.is_(adjusted),
                        OHLCVBar.is_derived.is_(True),
                        OHLCVBar.market_series_id == derived_series.id,
                    )
                    .order_by(OHLCVBar.ts)
                )
            )
            .scalars()
            .all()
        )
        preserve_existing_state = (
            not state_was_new
            and normalized_end is not None
            and any(
                (row.ts if row.ts.tzinfo is not None else row.ts.replace(tzinfo=UTC)).astimezone(
                    UTC
                )
                > normalized_end
                for row in derived_rows
            )
        )
        if not preserve_existing_state:
            if not state_was_new:
                state.version = max(1, state.version) + 1
            source_stale_after = source_state.stale_after if source_state is not None else None
            if source_stale_after is not None:
                source_stale_after = (
                    source_stale_after
                    if source_stale_after.tzinfo is not None
                    else source_stale_after.replace(tzinfo=UTC)
                ).astimezone(UTC)
            source_state_is_fresh = bool(
                source_state is not None
                and source_state.status == DatasetStatus.FRESH
                and source_stale_after is not None
                and source_stale_after > now
            )
            if not derived_rows:
                state.status = DatasetStatus.PENDING
            elif source_state is not None and not source_state_is_fresh:
                state.status = DatasetStatus.STALE
            else:
                state.status = DatasetStatus.FRESH
            state.observed_at = source_state.observed_at if source_state is not None else now
            state.fetched_at = source_state.fetched_at if source_state is not None else now
            state.stale_after = source_state.stale_after if source_state is not None else None
            state.coverage_start = derived_rows[0].ts if derived_rows else None
            state.coverage_end = derived_rows[-1].ts if derived_rows else None
            state_extra_data = {
                "source_timeframe": Timeframe.D1.value,
                "derivation_method": DERIVATION_METHOD,
                "adjusted": adjusted,
                "derived_bar_count": len(derived_rows),
                "provider_periods_excluded": 0,
                "source_d1_signature": source_d1_signature,
                "source_market_series_id": source_series.id if source_series is not None else None,
                "adjustment_provenance": {
                    "mode": "split_adjusted" if adjusted else "raw",
                    "source_kind": "derived_from_canonical_d1",
                    "factor_status": "inherited_from_canonical_d1",
                    "factor_version": canonical_factor_version,
                    "contract_version": 1,
                },
            }
            if source_state is not None:
                state_extra_data.update(
                    {
                        "source_data_source_id": source_data_source_id,
                        "source_dataset_fetched_at": (
                            source_state.fetched_at.isoformat()
                            if source_state.fetched_at is not None
                            else None
                        ),
                        "source_dataset_stale_after": (
                            source_state.stale_after.isoformat()
                            if source_state.stale_after is not None
                            else None
                        ),
                    }
                )
            state.extra_data = state_extra_data
        result[timeframe.value] = len(payloads)
        if normalized_end is None and derived_series is not None:
            from app.services.market_series import select_default_series_for_complete_range
            from app.services.ohlcv_coverage import assess_ohlcv_coverage

            await db.flush()
            current_derived = (
                (
                    await db.execute(
                        select(OHLCVBar)
                        .where(
                            OHLCVBar.instrument_id == instrument_id,
                            OHLCVBar.market_series_id == derived_series.id,
                            OHLCVBar.timeframe == timeframe,
                            OHLCVBar.is_adjusted.is_(adjusted),
                            OHLCVBar.is_derived.is_(True),
                        )
                        .order_by(OHLCVBar.ts)
                    )
                )
                .scalars()
                .all()
            )
            if current_derived:
                start_at = current_derived[0].ts
                end_at = current_derived[-1].ts
                instrument = await db.get(Instrument, instrument_id)
                coverage = assess_ohlcv_coverage(
                    current_derived,
                    timeframe,
                    start_at,
                    end_at,
                    calendar="XNYS"
                    if instrument is not None and (instrument.currency or "").upper() == "USD"
                    else None,
                )
                if coverage.status.value == "ready":
                    derived_series.is_canonical = True
                    await select_default_series_for_complete_range(
                        db,
                        instrument_id=instrument_id,
                        timeframe=timeframe.value,
                        adjusted=adjusted,
                        market_series_id=derived_series.id,
                        start=start_at,
                        end=end_at,
                    )
    await db.flush()
    return result
