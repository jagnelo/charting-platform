"""Materialise coarse canonical timeframes from local adjusted D1 bars.

This module is deliberately provider-neutral.  It only consumes persisted D1
bars, never calls a provider, never fills missing observations, and records
lineage on every derived row.  A provider-supplied W1/MN row always wins for
the same calendar period.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import TypeVar

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

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
    d1_source_statement = select(OHLCVBar.data_source_id).where(
        OHLCVBar.instrument_id == instrument_id,
        OHLCVBar.timeframe == Timeframe.D1,
        OHLCVBar.is_adjusted.is_(True),
        OHLCVBar.is_derived.is_(False),
        OHLCVBar.data_source_id.is_not(None),
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
    """Rebuild derived W1/MN rows from the instrument's persisted D1 rows.

    Existing derived rows are replaced atomically.  Provider rows are retained
    and suppress a derived row for their calendar period, so later provider
    enrichment can safely take precedence without changing the API contract.

    When ``end`` is supplied, only D1 evidence through that inclusive UTC bound
    is rebuilt.  Derived rows after the bound remain untouched; this is required
    for dated history jobs, where a newer local cache must not be rewritten as if
    it were part of the historical point-in-time view.
    """

    normalized_end = None
    if end is not None:
        normalized_end = end if end.tzinfo is not None else end.replace(tzinfo=UTC)
        normalized_end = normalized_end.astimezone(UTC)

    d1_statement = select(OHLCVBar).where(
        OHLCVBar.instrument_id == instrument_id,
        OHLCVBar.timeframe == Timeframe.D1,
        OHLCVBar.is_adjusted.is_(adjusted),
    )
    if normalized_end is not None:
        d1_statement = d1_statement.where(OHLCVBar.ts <= normalized_end)
    d1_bars = (await db.execute(d1_statement.order_by(OHLCVBar.ts))).scalars().all()

    canonical_factor_version = await _canonical_d1_factor_version(
        db,
        instrument_id,
        adjusted=adjusted,
        end=normalized_end,
    )
    result: dict[str, int] = {}
    for timeframe in (Timeframe.W1, Timeframe.MN):
        existing = (
            (
                await db.execute(
                    select(OHLCVBar).where(
                        OHLCVBar.instrument_id == instrument_id,
                        OHLCVBar.timeframe == timeframe,
                        OHLCVBar.is_adjusted.is_(adjusted),
                    )
                )
            )
            .scalars()
            .all()
        )
        provider_periods = {
            _period_key(bar.ts, timeframe) for bar in existing if not bar.is_derived
        }
        delete_statement = delete(OHLCVBar).where(
            OHLCVBar.instrument_id == instrument_id,
            OHLCVBar.timeframe == timeframe,
            OHLCVBar.is_adjusted.is_(adjusted),
            OHLCVBar.is_derived.is_(True),
        )
        if normalized_end is not None:
            delete_statement = delete_statement.where(OHLCVBar.ts <= normalized_end)
        await db.execute(delete_statement.execution_options(synchronize_session=False))
        payloads = [
            payload
            for payload in aggregate_d1_bars(d1_bars, timeframe)
            if payload["period_key"] not in provider_periods
        ]
        now = datetime.now(UTC)
        db.add_all(
            [
                OHLCVBar(
                    instrument_id=instrument_id,
                    data_source_id=None,
                    timeframe=timeframe,
                    ts=payload["ts"],
                    open=payload["open"],
                    high=payload["high"],
                    low=payload["low"],
                    close=payload["close"],
                    volume=payload["volume"],
                    vwap=payload["vwap"],
                    is_adjusted=adjusted,
                    is_derived=True,
                    source_timeframe=Timeframe.D1.value,
                    derivation_method=DERIVATION_METHOD,
                    derived_at=now,
                    source_bar_count=payload["source_bar_count"],
                    source_start=payload["source_start"],
                    source_end=payload["source_end"],
                )
                for payload in payloads
            ]
        )
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
        derived_rows = (
            (
                await db.execute(
                    select(OHLCVBar)
                    .where(
                        OHLCVBar.instrument_id == instrument_id,
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
            state.status = DatasetStatus.FRESH if derived_rows else DatasetStatus.PENDING
            state.observed_at = now
            state.fetched_at = now
            state.coverage_start = derived_rows[0].ts if derived_rows else None
            state.coverage_end = derived_rows[-1].ts if derived_rows else None
            state.extra_data = {
                "source_timeframe": Timeframe.D1.value,
                "derivation_method": DERIVATION_METHOD,
                "adjusted": adjusted,
                "derived_bar_count": len(derived_rows),
                "provider_periods_excluded": len(provider_periods),
                "adjustment_provenance": {
                    "mode": "split_adjusted" if adjusted else "raw",
                    "source_kind": "derived_from_canonical_d1",
                    "factor_status": "inherited_from_canonical_d1",
                    "factor_version": canonical_factor_version,
                    "contract_version": 1,
                },
            }
        result[timeframe.value] = len(payloads)
    await db.flush()
    return result
