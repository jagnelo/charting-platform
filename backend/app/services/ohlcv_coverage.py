"""Provider-neutral OHLCV coverage and freshness planning primitives."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from statistics import median
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_

from app.models.ohlcv import TIMEFRAME_SECONDS, OHLCVBar, Timeframe
from app.models.provider_observation import MarketBarObservation


class CoverageStatus(StrEnum):
    READY = "ready"
    PARTIAL = "partial"
    MISSING = "missing"
    STALE = "stale"


CoverageMode = Literal["historical", "latest"]
CalendarName = Literal["XNYS"]
_XNYS_TZ = ZoneInfo("America/New_York")
_XNYS_AD_HOC_CLOSURES = {
    # NYSE closed on Jan 9, 2025 for the National Day of Mourning.
    2025: {date(2025, 1, 9)},
}


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
    provider_keys = {
        (
            bar.instrument_id,
            bar.data_source_id,
            bar.timeframe,
            _as_utc(bar.ts),
            bar.is_adjusted,
        )
        for bar in provider_bars
    }
    matched = missing = mismatched = 0
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
    # Compare observations with a precomputed provider identity set.  The
    # previous nested scan was O(observations × provider_bars), which made a
    # large-range reconciliation prohibitively expensive even though the
    # identity itself is already fully hashable.
    orphan = sum(1 for key in observation_by_key if key not in provider_keys)
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
    local_split_count = sum(
        1 for bar in bars if bar.is_derived is True and bar.derivation_method == "local_split_ratio"
    )
    local_provider_factor_count = sum(
        1
        for bar in bars
        if bar.is_derived is True and bar.derivation_method == "provider_adjustment_factor"
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
        if local_split_count == derived_count:
            source_kind = "local_split_ratio"
            factor_status = "rebuildable_split_factors"
        elif local_provider_factor_count == derived_count:
            source_kind = "provider_adjustment_factor"
            factor_status = "rebuildable_provider_factors"
        else:
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


def bar_visible_through_clause(cutoff: datetime):
    """Keep derived coarse bars out of a cutoff until their source closes.

    Derived W1/MN rows use the first source session as ``ts`` but aggregate
    through ``source_end``. Comparing only ``ts`` would expose a partially
    observed period to a historical caller. Provider rows retain their
    observation-timestamp contract; derived rows need explicit source-end
    evidence to be visible at the cutoff.
    """

    normalized_cutoff = _as_utc(cutoff)
    return or_(
        OHLCVBar.is_derived.is_(False),
        and_(
            OHLCVBar.is_derived.is_(True),
            OHLCVBar.source_end.is_not(None),
            OHLCVBar.source_end <= normalized_cutoff,
        ),
    )


def bar_visible_through(bar: OHLCVBar, cutoff: datetime) -> bool:
    """Return whether one ORM bar has complete source evidence by cutoff."""

    if not bar.is_derived:
        return True
    if bar.source_end is None:
        return False
    return _as_utc(bar.source_end) <= _as_utc(cutoff)


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
    holidays.update(_XNYS_AD_HOC_CLOSURES.get(year, set()))
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
) -> list[tuple[datetime, datetime]] | None:
    """Plan missing completed XNYS sessions or calendar periods.

    ``None`` means this calendar/timeframe pair has no explicit grid and must
    use the conservative interval fallback. It must never be interpreted as a
    gap-free range.
    """
    if calendar != "XNYS" or timeframe not in {Timeframe.D1, Timeframe.W1, Timeframe.MN}:
        return None

    start = _as_utc(start)
    end = _as_utc(end)
    periods: list[tuple[date, datetime, datetime]] = []

    if timeframe == Timeframe.D1:
        local_start = start.astimezone(_XNYS_TZ)
        local_end = end.astimezone(_XNYS_TZ)
        close_label_count = sum(13 <= value.astimezone(_XNYS_TZ).hour < 18 for value in ordered)
        close_labelled = bool(ordered) and close_label_count * 2 >= len(ordered)
        for session in sorted(_xnys_session_days(local_start.date(), local_end.date())):
            bar_start = datetime.combine(session, time.min, tzinfo=_XNYS_TZ).astimezone(UTC)
            session_close = datetime.combine(session, time(16), tzinfo=_XNYS_TZ).astimezone(UTC)
            # Daily bars represent completed sessions. Do not manufacture a
            # missing tail for a session that has not closed yet.
            if close_labelled:
                if session_close < start or session_close > end:
                    continue
            elif bar_start < start or session_close > end:
                continue
            next_midnight = datetime.combine(
                session + timedelta(days=1), time.min, tzinfo=_XNYS_TZ
            ).astimezone(UTC)
            periods.append(
                (
                    session,
                    session_close if close_labelled else bar_start,
                    min(next_midnight - timedelta(microseconds=1), end),
                )
            )

        # Both canonical UTC-midnight labels and native NY-midnight labels
        # (04:00/05:00 UTC across DST) keep the exchange date in UTC's date
        # component. Converting a canonical 00:00 UTC label to New York would
        # incorrectly move it to the prior session.
        present = {value.date() for value in ordered}
    else:
        first_date = start.date()
        if timeframe == Timeframe.W1:
            bucket = first_date - timedelta(days=first_date.weekday())
            if datetime.combine(bucket, time.min, tzinfo=UTC) < start:
                bucket += timedelta(days=7)
        else:
            bucket = date(first_date.year, first_date.month, 1)
            if datetime.combine(bucket, time.min, tzinfo=UTC) < start:
                bucket = date(
                    first_date.year + (first_date.month == 12), first_date.month % 12 + 1, 1
                )

        while True:
            bucket_start = datetime.combine(bucket, time.min, tzinfo=UTC)
            if timeframe == Timeframe.W1:
                next_bucket = bucket + timedelta(days=7)
            else:
                next_bucket = date(bucket.year + (bucket.month == 12), bucket.month % 12 + 1, 1)
            bucket_end = datetime.combine(next_bucket, time.min, tzinfo=UTC) - timedelta(
                microseconds=1
            )
            if bucket_start > end:
                break

            sessions = _xnys_session_days(bucket, next_bucket - timedelta(days=1))
            if sessions:
                last_session_close = datetime.combine(
                    max(sessions), time(16), tzinfo=_XNYS_TZ
                ).astimezone(UTC)
                if last_session_close > end:
                    break
                periods.append((bucket, bucket_start, min(bucket_end, end)))
            bucket = next_bucket

        if timeframe == Timeframe.W1:
            present = {value.date() - timedelta(days=value.date().weekday()) for value in ordered}
        else:
            present = {date(value.year, value.month, 1) for value in ordered}

    present_periods = set(present)
    missing = [
        (index, period) for index, period in enumerate(periods) if period[0] not in present_periods
    ]
    if not missing:
        return []

    slices: list[tuple[datetime, datetime]] = []
    first_index, first = missing[0]
    previous_index, previous = first_index, first
    for current_index, current in missing[1:]:
        if current_index != previous_index + 1:
            slice_start, slice_end = max(first[1], start), min(previous[2], end)
            slices.append(
                (slice_start, slice_end) if slice_start < slice_end else (first[1], previous[2])
            )
            first_index, first = current_index, current
        previous = current
        previous_index = current_index
    slice_start, slice_end = max(first[1], start), min(previous[2], end)
    slices.append((slice_start, slice_end) if slice_start < slice_end else (first[1], previous[2]))
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

    When an explicit calendar is supplied, supported daily and calendar-period
    gaps are evaluated against completed exchange sessions. Missing expected
    periods are coalesced across closed days; present periods split the ranges.
    Unsupported calendar/timeframe pairs retain the conservative interval
    fallback rather than being assumed complete.
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
        calendar_slices = _calendar_missing_slices(ordered, timeframe, start, end, calendar)
        if calendar_slices is not None:
            return calendar_slices

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
