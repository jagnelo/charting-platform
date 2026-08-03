from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.models.ohlcv import TIMEFRAME_SECONDS, Timeframe
from app.services.market_data import (
    _historical_repair_start,
    _needs_fetch_for_range,
)
from app.services.ohlcv_coverage import (
    CoverageStatus,
    assess_ohlcv_coverage,
    missing_range_slices,
)


def test_historical_repair_start_is_bounded_to_the_missing_tail():
    before = datetime(2026, 1, 31, tzinfo=UTC)
    oldest = datetime(2026, 1, 20, tzinfo=UTC)
    start = _historical_repair_start(before, Timeframe.D1, 5, oldest)

    assert start == oldest - timedelta(seconds=TIMEFRAME_SECONDS[Timeframe.D1] * 10)
    assert start > datetime(1970, 1, 1, tzinfo=UTC)


def test_cold_historical_repair_uses_minimum_bootstrap_window():
    before = datetime(2026, 1, 31, tzinfo=UTC)
    start = _historical_repair_start(before, Timeframe.W1, 10)

    assert start == before - timedelta(seconds=TIMEFRAME_SECONDS[Timeframe.W1] * 20)


def _bar(ts: datetime, timeframe: Timeframe = Timeframe.D1):
    return SimpleNamespace(ts=ts, timeframe=timeframe)


def test_historical_range_repairs_only_an_obvious_internal_gap():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 12, tzinfo=UTC)
    cached = [
        _bar(datetime(2026, 1, 1, tzinfo=UTC)),
        _bar(datetime(2026, 1, 2, tzinfo=UTC)),
        _bar(datetime(2026, 1, 10, tzinfo=UTC)),
        _bar(datetime(2026, 1, 11, tzinfo=UTC)),
        _bar(datetime(2026, 1, 12, tzinfo=UTC)),
    ]

    assert missing_range_slices(cached, Timeframe.D1, start, end) == [
        (datetime(2026, 1, 3, tzinfo=UTC), datetime(2026, 1, 9, tzinfo=UTC))
    ]
    assert _needs_fetch_for_range(cached, Timeframe.D1, start, end) is True


def test_daily_weekend_gap_is_not_treated_as_missing_history():
    start = datetime(2026, 1, 2, tzinfo=UTC)
    end = datetime(2026, 1, 5, tzinfo=UTC)
    cached = [
        _bar(datetime(2026, 1, 2, tzinfo=UTC)),
        _bar(datetime(2026, 1, 5, tzinfo=UTC)),
    ]

    assert missing_range_slices(cached, Timeframe.D1, start, end) == []
    assert _needs_fetch_for_range(cached, Timeframe.D1, start, end) is False


def test_xnys_calendar_flags_a_missing_weekday_but_not_weekend_or_holiday():
    from app.services.ohlcv_coverage import missing_range_slices

    weekday_gap = missing_range_slices(
        [_bar(datetime(2026, 1, 2, tzinfo=UTC)), _bar(datetime(2026, 1, 6, tzinfo=UTC))],
        Timeframe.D1,
        datetime(2026, 1, 2, tzinfo=UTC),
        datetime(2026, 1, 6, tzinfo=UTC),
        calendar="XNYS",
    )
    assert weekday_gap == [(datetime(2026, 1, 5, tzinfo=UTC), datetime(2026, 1, 5, tzinfo=UTC))]

    holiday_gap = missing_range_slices(
        [_bar(datetime(2026, 1, 16, tzinfo=UTC)), _bar(datetime(2026, 1, 20, tzinfo=UTC))],
        Timeframe.D1,
        datetime(2026, 1, 16, tzinfo=UTC),
        datetime(2026, 1, 20, tzinfo=UTC),
        calendar="XNYS",
    )
    assert holiday_gap == []


def test_coverage_planner_distinguishes_historical_ready_from_latest_stale():
    start = datetime(2026, 1, 2, tzinfo=UTC)
    end = datetime(2026, 1, 5, tzinfo=UTC)
    cached = [
        _bar(datetime(2026, 1, 2, tzinfo=UTC)),
        _bar(datetime(2026, 1, 5, tzinfo=UTC)),
    ]

    historical = assess_ohlcv_coverage(
        cached, Timeframe.D1, start, end, mode="historical", now=datetime(2026, 8, 3, tzinfo=UTC)
    )
    latest = assess_ohlcv_coverage(
        cached,
        Timeframe.D1,
        start,
        end,
        mode="latest",
        freshness_seconds=86_400,
        now=datetime(2026, 8, 3, tzinfo=UTC),
    )

    assert historical.status is CoverageStatus.READY
    assert latest.status is CoverageStatus.STALE
    assert historical.missing_slices == ()


def test_coverage_planner_reports_cold_range_and_bounded_slice():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 5, tzinfo=UTC)
    assessment = assess_ohlcv_coverage([], Timeframe.D1, start, end)

    assert assessment.status is CoverageStatus.MISSING
    assert assessment.missing_slices == ((start, end),)
    assert assessment.bar_count == 0
