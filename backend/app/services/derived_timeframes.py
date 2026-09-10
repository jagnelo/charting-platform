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


async def _canonical_d1_factor_version(
    db: AsyncSession, instrument_id: int, *, adjusted: bool
) -> str | None:
    """Return one verified D1 factor version suitable for derived lineage.

    Coarse rows inherit the canonical adjusted D1 contract, but must not claim
    a rebuildable factor version when the contributing provider sources disagree
    or any source lacks explicit provenance. Raw rows never carry adjustment
    provenance.
    """

    if not adjusted:
        return None
    source_ids = set(
        (
            await db.execute(
                select(OHLCVBar.data_source_id).where(
                    OHLCVBar.instrument_id == instrument_id,
                    OHLCVBar.timeframe == Timeframe.D1,
                    OHLCVBar.is_adjusted.is_(True),
                    OHLCVBar.is_derived.is_(False),
                    OHLCVBar.data_source_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if not source_ids:
        return None

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

    versions: set[str] = set()
    for state in states:
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
    db: AsyncSession, instrument_id: int, *, adjusted: bool = True
) -> dict[str, int]:
    """Rebuild derived W1/MN rows from the instrument's persisted D1 rows.

    Existing derived rows are replaced atomically.  Provider rows are retained
    and suppress a derived row for their calendar period, so later provider
    enrichment can safely take precedence without changing the API contract.
    """

    d1_bars = (
        (
            await db.execute(
                select(OHLCVBar)
                .where(
                    OHLCVBar.instrument_id == instrument_id,
                    OHLCVBar.timeframe == Timeframe.D1,
                    OHLCVBar.is_adjusted.is_(adjusted),
                )
                .order_by(OHLCVBar.ts)
            )
        )
        .scalars()
        .all()
    )

    canonical_factor_version = await _canonical_d1_factor_version(
        db, instrument_id, adjusted=adjusted
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
        await db.execute(
            delete(OHLCVBar).where(
                OHLCVBar.instrument_id == instrument_id,
                OHLCVBar.timeframe == timeframe,
                OHLCVBar.is_adjusted.is_(adjusted),
                OHLCVBar.is_derived.is_(True),
            )
        )
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
        state.status = DatasetStatus.FRESH if payloads else DatasetStatus.PENDING
        state.observed_at = now
        state.fetched_at = now
        state.coverage_start = payloads[0]["ts"] if payloads else None
        state.coverage_end = payloads[-1]["ts"] if payloads else None
        state.extra_data = {
            "source_timeframe": Timeframe.D1.value,
            "derivation_method": DERIVATION_METHOD,
            "adjusted": adjusted,
            "derived_bar_count": len(payloads),
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
