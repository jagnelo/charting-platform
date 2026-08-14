"""Provider-neutral OHLCV coverage and freshness planning primitives."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Literal

from app.models.ohlcv import TIMEFRAME_SECONDS, OHLCVBar, Timeframe


class CoverageStatus(StrEnum):
    READY = "ready"
    PARTIAL = "partial"
    MISSING = "missing"
    STALE = "stale"


CoverageMode = Literal["historical", "latest"]
CalendarName = Literal["XNYS"]


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


def _observed_fixed_holiday(year: int, month: int, day: int) -> date:
    holiday = date(year, month, day)
    if holiday.weekday() == 5:  # Saturday -> Friday
        return holiday - timedelta(days=1)
    if holiday.weekday() == 6:  # Sunday -> Monday
        return holiday + timedelta(days=1)
    return holiday


def _easter_sunday(year: int) -> date:
    """Anonymous Gregorian computus, sufficient for Good Friday."""
    century, remainder = divmod(year, 100)
    moon = (
        19 * (year % 19) + century - century // 4 - (century - (century + 8) // 25 + 1) // 3 + 15
    ) % 30
    weekday = (32 + 2 * (century % 4) + 2 * (remainder // 4) - moon - remainder % 4) % 7
    adjustment = moon + weekday - 7 * ((year % 19 + 11 * moon + 22 * weekday) // 451) + 114
    month, day = divmod(adjustment, 31)
    return date(year, month, day + 1)


def _first_weekday(year: int, month: int, weekday: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7)


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    return _first_weekday(year, month, weekday) + timedelta(days=7 * (occurrence - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    last = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _xnys_holidays(year: int) -> set[date]:
    """Major XNYS full-day closures for a deterministic local daily calendar."""
    holidays = {
        _observed_fixed_holiday(year, 1, 1),
        _nth_weekday(year, 1, 0, 3),  # Martin Luther King Jr. Day
        _nth_weekday(year, 2, 0, 3),  # Presidents' Day
        _last_weekday(year, 5, 0),  # Memorial Day
        _observed_fixed_holiday(year, 7, 4),
        _first_weekday(year, 9, 0),  # Labor Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving
        _observed_fixed_holiday(year, 12, 25),
        _easter_sunday(year) - timedelta(days=2),  # Good Friday
    }
    if year >= 2022:
        holidays.add(_observed_fixed_holiday(year, 6, 19))  # Juneteenth
    return holidays


def _xnys_session_days(start: date, end: date) -> set[date]:
    holidays: set[date] = set()
    for year in range(start.year, end.year + 1):
        holidays.update(_xnys_holidays(year))
    sessions: set[date] = set()
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5 and cursor not in holidays:
            sessions.add(cursor)
        cursor += timedelta(days=1)
    return sessions


def _calendar_missing_slices(
    ordered: list[datetime],
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    calendar: CalendarName,
) -> list[tuple[datetime, datetime]]:
    if calendar != "XNYS" or timeframe != Timeframe.D1:
        return []
    missing = sorted(
        _xnys_session_days(start.date(), end.date()) - {value.date() for value in ordered}
    )
    if not missing:
        return []
    slices: list[tuple[datetime, datetime]] = []
    first = previous = missing[0]
    for current in missing[1:]:
        if current != previous + timedelta(days=1):
            slices.append(
                (
                    datetime.combine(first, datetime.min.time(), tzinfo=UTC),
                    datetime.combine(previous, datetime.min.time(), tzinfo=UTC),
                )
            )
            first = current
        previous = current
    slices.append(
        (
            datetime.combine(first, datetime.min.time(), tzinfo=UTC),
            datetime.combine(previous, datetime.min.time(), tzinfo=UTC),
        )
    )
    return slices


def missing_range_slices(
    cached: Sequence[OHLCVBar],
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    *,
    calendar: CalendarName | None = None,
) -> list[tuple[datetime, datetime]]:
    """Return exact edge and conservative obvious internal gaps.

    When an explicit calendar is supplied, daily gaps are evaluated against its
    expected session dates. Without one, retain conservative interval-based
    behavior because exchange closures cannot be inferred safely.
    """
    if not cached:
        return [(_as_utc(start), _as_utc(end))]

    step = timedelta(seconds=TIMEFRAME_SECONDS[timeframe])
    start = _as_utc(start)
    end = _as_utc(end)
    ordered = sorted(_as_utc(bar.ts) for bar in cached if start <= _as_utc(bar.ts) <= end)
    if not ordered:
        return [(start, end)]

    if calendar is not None:
        return _calendar_missing_slices(ordered, timeframe, start, end, calendar)

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
    calendar: CalendarName | None = None,
) -> OhlcvCoverageAssessment:
    """Assess readiness without provider access or wall-clock side effects."""
    start = _as_utc(start)
    end = _as_utc(end)
    ordered = sorted(_as_utc(bar.ts) for bar in cached if start <= _as_utc(bar.ts) <= end)
    slices = tuple(missing_range_slices(cached, timeframe, start, end, calendar=calendar))
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
        if covered_end is not None and covered_end < observed_now - timedelta(
            seconds=freshness_seconds
        ):
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
