from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.models.ohlcv import TIMEFRAME_SECONDS, Timeframe
from app.services.market_data import (
    _historical_repair_start,
    _missing_range_slices,
    _needs_fetch_for_range,
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

    assert _missing_range_slices(cached, Timeframe.D1, start, end) == [
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

    assert _missing_range_slices(cached, Timeframe.D1, start, end) == []
    assert _needs_fetch_for_range(cached, Timeframe.D1, start, end) is False
