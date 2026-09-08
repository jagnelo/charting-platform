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

DERIVATION_METHOD = "d1_ohlcv_xnys_calendar_aggregation"
_BarLike = TypeVar("_BarLike", bound=OHLCVBar)


def _period_key(ts: datetime, timeframe: Timeframe) -> tuple[int, int]:
    value = ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)
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
        ordered = sorted(members, key=lambda item: item.ts)
        volumes = [bar.volume for bar in ordered if bar.volume is not None]
        vwap = None
        if volumes and len(volumes) == len(ordered) and sum(volumes) > 0:
            vwap = sum((bar.vwap or bar.close) * bar.volume for bar in ordered) / sum(volumes)
        payloads.append(
            {
                "ts": ordered[0].ts,
                "open": ordered[0].open,
                "high": max(bar.high for bar in ordered),
                "low": min(bar.low for bar in ordered),
                "close": ordered[-1].close,
                "volume": sum(volumes) if len(volumes) == len(ordered) else None,
                "vwap": vwap,
                "source_bar_count": len(ordered),
                "source_start": ordered[0].ts,
                "source_end": ordered[-1].ts,
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
        result[timeframe.value] = len(payloads)
    await db.flush()
    return result
