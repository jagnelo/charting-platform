"""Provider-neutral OHLCV coverage and freshness planning primitives."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from statistics import median
from typing import Literal

from app.models.ohlcv import TIMEFRAME_SECONDS, OHLCVBar, Timeframe
from app.models.provider_observation import MarketBarObservation


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


@dataclass(frozen=True, slots=True)
class OhlcvLineageSummary:
    """Explicit source and adjustment lineage for a covered bar range.

    Provider APIs expose the requested adjustment mode but do not expose the
    event-level factors used to produce adjusted prices.  Keep that limitation
    explicit, and distinguish it from locally derived coarse bars inheriting
    the canonical D1 adjustment contract.
    """

    provider_bar_count: int
    derived_bar_count: int
    unknown_bar_count: int
    source_lineage: str
    source_timeframes: tuple[str, ...]
    adjustment_provenance: dict[str, object]


@dataclass(frozen=True, slots=True)
class OhlcvStorageReconciliation:
    """Evidence that canonical provider bars still match raw observations."""

    status: str
    provider_bar_count: int
    observation_count: int
    matched_observation_count: int
    missing_observation_count: int
    mismatched_observation_count: int
    orphan_observation_count: int


@dataclass(frozen=True, slots=True)
class OhlcvCadenceAssessment:
    """Observed spacing between distinct bars returned for a range.

    This is a diagnostic of local rows in the requested range only. It is not
    a claim about a provider schedule or about missing observations outside
    the returned rows.
    """

    status: str
    sample_count: int = 0
    median_interval_days: float | None = None
    min_interval_days: float | None = None
    max_interval_days: float | None = None


def assess_observed_ohlcv_cadence(bars: Sequence[OHLCVBar]) -> OhlcvCadenceAssessment:
    """Summarise intervals between distinct timestamps in returned OHLCV rows."""

    timestamps = sorted({_as_utc(bar.ts) for bar in bars if bar.ts is not None})
    if not timestamps:
        return OhlcvCadenceAssessment(status="no_observation")
    if len(timestamps) == 1:
        return OhlcvCadenceAssessment(status="single_observation")
    intervals = tuple(
        (current - previous).total_seconds() / 86_400
        for previous, current in zip(timestamps, timestamps[1:])
        if current > previous
    )
    if not intervals:
        return OhlcvCadenceAssessment(status="no_interval")
    return OhlcvCadenceAssessment(
        status="observed_cadence",
        sample_count=len(intervals),
        median_interval_days=float(median(intervals)),
        min_interval_days=min(intervals),
        max_interval_days=max(intervals),
    )


def reconcile_ohlcv_storage(
    bars: Sequence[OHLCVBar], observations: Sequence[MarketBarObservation]
) -> OhlcvStorageReconciliation:
    """Compare provider-backed canonical bars with their raw observations.

    Derived rows intentionally have no raw observation. Provider rows with no
    source identity are reported through the existing unknown-lineage count,
    not treated as a proven mismatch.
    """

    provider_bars = [
        bar for bar in bars if bar.is_derived is False and bar.data_source_id is not None
    ]
    # A timestamp is not globally unique: the same source can expose several
    # timeframes and both raw and adjusted views for one instrument.  Keep the
    # complete storage identity here so one observation cannot satisfy a
    # different timeframe or adjustment mode by accident.
    observation_by_key = {
        (
            observation.instrument_id,
            observation.data_source_id,
            observation.timeframe,
            _as_utc(observation.ts),
            observation.is_adjusted,
        ): observation
        for observation in observations
    }
    matched = missing = mismatched = 0
    observed_keys: set[tuple[int, int, Timeframe, datetime, bool]] = set()
    for bar in provider_bars:
        key = (
            bar.instrument_id,
            bar.data_source_id,
            bar.timeframe,
            _as_utc(bar.ts),
            bar.is_adjusted,
        )
        observation = observation_by_key.get(key)
        if observation is None:
            missing += 1
            continue
        observed_keys.add(key)
        if any(
            left != right
            for left, right in (
                (bar.open, observation.open),
                (bar.high, observation.high),
                (bar.low, observation.low),
                (bar.close, observation.close),
                (bar.volume, observation.volume),
                (bar.vwap, observation.vwap),
            )
        ):
            mismatched += 1
        else:
            matched += 1
    orphan = sum(
        1
        for key in observation_by_key
        if key not in observed_keys
        and not any(
            (
                bar.instrument_id,
                bar.data_source_id,
                bar.timeframe,
                _as_utc(bar.ts),
                bar.is_adjusted,
            )
            == key
            for bar in provider_bars
        )
    )
    if not provider_bars and not observations:
        status = "not_observed"
    elif missing or mismatched or orphan:
        status = "inconsistent"
    else:
        status = "reconciled"
    return OhlcvStorageReconciliation(
        status=status,
        provider_bar_count=len(provider_bars),
        observation_count=len(observations),
        matched_observation_count=matched,
        missing_observation_count=missing,
        mismatched_observation_count=mismatched,
        orphan_observation_count=orphan,
    )


def summarize_ohlcv_lineage(bars: Sequence[OHLCVBar], *, adjusted: bool) -> OhlcvLineageSummary:
    """Summarize provider/derived lineage without naming an unknown provider."""

    provider_count = sum(1 for bar in bars if bar.is_derived is False)
    derived_count = sum(1 for bar in bars if bar.is_derived is True)
    unknown_count = len(bars) - provider_count - derived_count
    if provider_count and derived_count:
        source_lineage = "provider_and_derived"
    elif provider_count:
        source_lineage = "provider_only"
    elif derived_count:
        source_lineage = "derived_only"
    else:
        source_lineage = "unavailable"

    source_timeframes = tuple(
        sorted(
            {
                str(bar.source_timeframe)
                for bar in bars
                if bar.is_derived is True and bar.source_timeframe
            }
        )
    )
    if not bars:
        source_kind = "unavailable"
        factor_status = "not_observed"
    elif provider_count and derived_count:
        source_kind = "mixed_provider_and_derived"
        factor_status = "mixed_provider_native_opaque_and_inherited_from_canonical_d1"
    elif provider_count:
        source_kind = "provider_observation"
        factor_status = "provider_native_opaque" if adjusted else "not_applied"
    elif derived_count:
        source_kind = "derived_from_canonical_d1"
        factor_status = "inherited_from_canonical_d1"
    else:
        source_kind = "unavailable"
        factor_status = "not_observed"

    return OhlcvLineageSummary(
        provider_bar_count=provider_count,
        derived_bar_count=derived_count,
        unknown_bar_count=unknown_count,
        source_lineage=source_lineage,
        source_timeframes=source_timeframes,
        adjustment_provenance={
            "mode": "split_adjusted" if adjusted else "raw",
            "source_kind": source_kind,
            "factor_status": factor_status,
            "factor_version": None,
            "contract_version": 1,
        },
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


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
