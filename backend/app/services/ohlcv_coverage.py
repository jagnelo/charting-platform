"""Provider-neutral OHLCV coverage and freshness planning primitives."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal

from app.models.ohlcv import TIMEFRAME_SECONDS, OHLCVBar, Timeframe


class CoverageStatus(StrEnum):
    READY = "ready"
    PARTIAL = "partial"
    MISSING = "missing"
    STALE = "stale"


CoverageMode = Literal["historical", "latest"]


@dataclass(frozen=True, slots=True)
class OhlcvCoverageAssessment:
    """Deterministic decision for a single instrument/timeframe/range."""

    status: CoverageStatus
    covered_start: datetime | None
    covered_end: datetime | None
    bar_count: int
    missing_slices: tuple[tuple[datetime, datetime], ...]
    explanation: str


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def missing_range_slices(
    cached: Sequence[OHLCVBar],
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
) -> list[tuple[datetime, datetime]]:
    """Return exact edge and conservative obvious internal gaps.

    Exchange calendars are intentionally not inferred here. Edge gaps are exact;
    internal gaps are returned only when materially larger than the timeframe
    interval, so ordinary daily weekends do not become false missing slices.
    """
    if not cached:
        return [(_as_utc(start), _as_utc(end))]

    step = timedelta(seconds=TIMEFRAME_SECONDS[timeframe])
    start = _as_utc(start)
    end = _as_utc(end)
    ordered = sorted(_as_utc(bar.ts) for bar in cached if start <= _as_utc(bar.ts) <= end)
    if not ordered:
        return [(start, end)]

    tolerance = 4 if timeframe == Timeframe.D1 else 2
    slices: list[tuple[datetime, datetime]] = []
    if ordered[0] > start + step:
        slices.append((start, ordered[0] - step))
    elif ordered[0] > start:
        slices.append((start, ordered[0]))

    for previous, current in zip(ordered, ordered[1:]):
        if current - previous > step * tolerance:
            gap_start = previous + step
            gap_end = current - step
            if gap_start <= gap_end:
                slices.append((gap_start, gap_end))

    if ordered[-1] < end - step:
        slices.append((ordered[-1] + step, end))
    elif ordered[-1] < end:
        slices.append((ordered[-1], end))
    return slices


def assess_ohlcv_coverage(
    cached: Sequence[OHLCVBar],
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    *,
    mode: CoverageMode = "historical",
    freshness_seconds: int | None = None,
    now: datetime | None = None,
) -> OhlcvCoverageAssessment:
    """Assess readiness without provider access or wall-clock side effects."""
    start = _as_utc(start)
    end = _as_utc(end)
    ordered = sorted(_as_utc(bar.ts) for bar in cached if start <= _as_utc(bar.ts) <= end)
    slices = tuple(missing_range_slices(cached, timeframe, start, end))
    covered_start = ordered[0] if ordered else None
    covered_end = ordered[-1] if ordered else None

    if not ordered:
        return OhlcvCoverageAssessment(
            status=CoverageStatus.MISSING,
            covered_start=None,
            covered_end=None,
            bar_count=0,
            missing_slices=slices,
            explanation="No local bars cover the requested range.",
        )
    if slices:
        return OhlcvCoverageAssessment(
            status=CoverageStatus.PARTIAL,
            covered_start=covered_start,
            covered_end=covered_end,
            bar_count=len(ordered),
            missing_slices=slices,
            explanation="Local bars leave one or more bounded range slices unavailable.",
        )

    if mode == "latest" and freshness_seconds is not None:
        observed_now = _as_utc(now or datetime.now(UTC))
        if covered_end is not None and covered_end < observed_now - timedelta(seconds=freshness_seconds):
            return OhlcvCoverageAssessment(
                status=CoverageStatus.STALE,
                covered_start=covered_start,
                covered_end=covered_end,
                bar_count=len(ordered),
                missing_slices=(),
                explanation="The latest local bar is older than the requested freshness policy.",
            )

    return OhlcvCoverageAssessment(
        status=CoverageStatus.READY,
        covered_start=covered_start,
        covered_end=covered_end,
        bar_count=len(ordered),
        missing_slices=(),
        explanation="The requested range is locally covered.",
    )
