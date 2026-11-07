import asyncio
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.dialects import postgresql

from app.models.ohlcv import TIMEFRAME_SECONDS, OHLCVBar, Timeframe
from app.providers.base import InstrumentProfile
from app.services import market_data
from app.services.market_data import (
    _bar_as_dict,
    _historical_repair_start,
    _is_positive_repair_slice,
    _is_recoverable_provider_gap,
    _needs_fetch_for_range,
)
from app.services.ohlcv_coverage import (
    CoverageStatus,
    assess_ohlcv_coverage,
    missing_range_slices,
)
from app.services.provider_runtime import ProviderNoDataError


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


def test_zero_width_calendar_gap_is_not_sent_to_a_provider():
    session = datetime(2026, 1, 5, tzinfo=UTC)

    assert _is_positive_repair_slice(session, session) is False
    assert _is_positive_repair_slice(session, session + timedelta(days=1)) is True


def test_cached_ranges_tolerate_expected_provider_availability_failures():
    assert _is_recoverable_provider_gap(ProviderNoDataError("empty")) is True
    assert (
        _is_recoverable_provider_gap(
            RuntimeError("No enabled providers available for capability 'price_history'")
        )
        is True
    )


@pytest.mark.asyncio
async def test_required_industry_profile_falls_through_generic_source_to_massive_sic(
    db, monkeypatch
):
    from tests.unit.conftest import AsyncSessionAdapter

    async_db = AsyncSessionAdapter(db)
    generic = InstrumentProfile(
        provider="alpaca",
        symbol="XLB",
        canonical_symbol="XLB",
        name="Materials Select Sector SPDR",
        extra={"sector": "Materials"},
    )
    sic = InstrumentProfile(
        provider="massive",
        symbol="XLB",
        canonical_symbol="XLB",
        name="Materials Select Sector SPDR",
        extra={"sic_code": "6726", "sic_description": "Investment offices"},
    )
    monkeypatch.setattr(market_data, "_fresh_profile_from_cache", AsyncMock(return_value=generic))
    monkeypatch.setattr(
        market_data,
        "resolve_provider_chain",
        AsyncMock(
            return_value=[
                SimpleNamespace(provider_name="alpaca"),
                SimpleNamespace(provider_name="massive"),
            ]
        ),
    )
    executions = []

    async def fake_execute(*_args, provider_name, **_kwargs):
        executions.append(provider_name)
        return SimpleNamespace(result=generic if provider_name == "alpaca" else sic)

    ingested = []

    async def fake_ingest(_db, profile, **_kwargs):
        ingested.append(profile.provider)

    monkeypatch.setattr(market_data, "execute_provider_call", fake_execute)
    monkeypatch.setattr(market_data, "ingest_provider_profile", fake_ingest)

    result = await market_data.get_provider_profile_async(
        async_db,
        "XLB",
        instrument_id=55,
        required_profile_fields=["industry"],
        raise_provider_errors=True,
    )

    assert result is sic
    assert executions == ["alpaca", "massive"]
    assert ingested == ["alpaca", "massive"]


def _semantic_bar() -> OHLCVBar:
    return OHLCVBar(
        instrument_id=42,
        data_source_id=7,
        market_series_id=99,
        timeframe=Timeframe.D1,
        ts=datetime(2026, 1, 2, tzinfo=UTC),
        session="regular",
        open=100,
        high=102,
        low=99,
        close=101,
        volume=1234,
        vwap=100.5,
        is_adjusted=True,
        adjustment_basis="provider_adjusted",
        adjustment_version="alpaca-all",
        provenance={"provider": "alpaca", "provider_payload": {"t": "2026-01-02"}},
    )


def test_bar_insert_mapping_preserves_series_adjustment_and_provenance():
    mapped = _bar_as_dict(_semantic_bar())

    assert mapped == {
        "instrument_id": 42,
        "data_source_id": 7,
        "market_series_id": 99,
        "timeframe": Timeframe.D1,
        "ts": datetime(2026, 1, 2, tzinfo=UTC),
        "session": "regular",
        "scope_key": "series:99:regular",
        "open": 100,
        "high": 102,
        "low": 99,
        "close": 101,
        "volume": 1234,
        "vwap": 100.5,
        "is_adjusted": True,
        "adjustment_basis": "provider_adjusted",
        "adjustment_version": "alpaca-all",
        "provenance": {"provider": "alpaca", "provider_payload": {"t": "2026-01-02"}},
    }


@pytest.mark.asyncio
async def test_observation_insert_mapping_preserves_series_adjustment_and_payload():
    class _Db:
        def __init__(self):
            self.parameters = None

        async def execute(self, _statement, parameters):
            self.parameters = parameters

    db = _Db()
    await market_data._record_bar_observations(
        db,
        [_semantic_bar()],
        data_source_id=7,
        provider_symbol="AAPL",
        observed_at=datetime(2026, 1, 3, tzinfo=UTC),
    )

    assert db.parameters == [
        {
            "instrument_id": 42,
            "data_source_id": 7,
            "market_series_id": 99,
            "provider_symbol": "AAPL",
            "timeframe": Timeframe.D1,
            "session": "regular",
            "scope_key": "series:99:regular",
            "ts": datetime(2026, 1, 2, tzinfo=UTC),
            "observed_at": datetime(2026, 1, 3, tzinfo=UTC),
            "open": 100,
            "high": 102,
            "low": 99,
            "close": 101,
            "volume": 1234,
            "vwap": 100.5,
            "is_adjusted": True,
            "adjustment_basis": "provider_adjusted",
            "adjustment_version": "alpaca-all",
            "source_payload": {"provider": "alpaca", "provider_payload": {"t": "2026-01-02"}},
        }
    ]


@pytest.mark.asyncio
async def test_bar_observation_insert_is_append_only_for_same_observation_timestamp():
    class _Db:
        def __init__(self):
            self.statement = None

        async def execute(self, statement, _parameters):
            self.statement = statement

    db = _Db()
    await market_data._record_bar_observations(
        db,
        [_semantic_bar()],
        data_source_id=7,
        provider_symbol="AAPL",
        observed_at=datetime(2026, 1, 3, tzinfo=UTC),
    )

    assert "DO NOTHING" in str(db.statement.compile(dialect=postgresql.dialect()))
    assert _is_recoverable_provider_gap(RuntimeError("unexpected programming failure")) is False


@pytest.mark.asyncio
async def test_provider_refresh_assigns_scoped_market_series(monkeypatch):
    bar = _semantic_bar()
    execution = SimpleNamespace(
        provider_name="alpaca",
        data_source=SimpleNamespace(id=17),
        result=[bar],
    )
    captured: dict[str, object] = {}

    async def fake_execute(*_args, **_kwargs):
        captured["execute_kwargs"] = _kwargs
        return execution

    async def fake_get_or_create(_db, scope, **kwargs):
        captured["scope"] = scope
        captured["kwargs"] = kwargs
        return SimpleNamespace(id=123)

    async def fake_record(*_args, **_kwargs):
        return None

    async def fake_touch(*_args, **_kwargs):
        return None

    monkeypatch.setattr(market_data, "execute_provider_call", fake_execute)
    monkeypatch.setattr(market_data, "get_or_create_series", fake_get_or_create)
    monkeypatch.setattr(market_data, "provider_symbol_for_instrument", lambda *_args: "AAPL")
    monkeypatch.setattr(market_data, "_record_bar_observations", fake_record)
    monkeypatch.setattr(market_data, "_touch_ohlcv_dataset_state", fake_touch)

    instrument = SimpleNamespace(id=42, symbol="AAPL")
    result = await market_data._fetch_provider(
        object(),
        instrument,
        Timeframe.D1,
        datetime(2020, 1, 1, tzinfo=UTC),
        datetime(2023, 1, 1, tzinfo=UTC),
        True,
    )

    scope = captured["scope"]
    assert scope.instrument_id == 42
    assert scope.data_source_id == 17
    assert scope.feed_scope == "provider_native"
    assert scope.session_code == "regular"
    assert scope.timeframe == "D1"
    assert scope.adjustment_basis.value == "provider_adjusted"
    assert scope.adjustment_version == "alpaca-all"
    assert captured["kwargs"]["canonical"] is True
    assert captured["execute_kwargs"]["operation_cost_overrides"]["marketdata_app"] == 2
    assert captured["execute_kwargs"]["operation_cost_overrides"]["fmp"] == 1
    assert result[0].market_series_id == 123


@pytest.mark.asyncio
async def test_latest_provider_refresh_assigns_scoped_market_series(monkeypatch):
    bar = _semantic_bar()
    execution = SimpleNamespace(
        provider_name="alpaca",
        data_source=SimpleNamespace(id=17),
        result=[bar],
    )
    captured: dict[str, object] = {}

    async def fake_execute(*_args, **_kwargs):
        captured["execute_kwargs"] = _kwargs
        return execution

    async def fake_get_or_create(_db, scope, **kwargs):
        captured["scope"] = scope
        captured["kwargs"] = kwargs
        return SimpleNamespace(id=456)

    async def fake_record(*_args, **_kwargs):
        return None

    async def fake_touch(*_args, **_kwargs):
        return None

    monkeypatch.setattr(market_data, "execute_provider_call", fake_execute)
    expected_history_start = datetime(2025, 12, 1, tzinfo=UTC)
    monkeypatch.setattr(
        market_data,
        "get_provider",
        lambda _provider_name: SimpleNamespace(
            latest_window_start=lambda _timeframe, _limit: expected_history_start
        ),
    )
    monkeypatch.setattr(market_data, "get_or_create_series", fake_get_or_create)
    monkeypatch.setattr(market_data, "provider_symbol_for_instrument", lambda *_args: "AAPL")
    monkeypatch.setattr(market_data, "_record_bar_observations", fake_record)
    monkeypatch.setattr(market_data, "_touch_ohlcv_dataset_state", fake_touch)

    result = await market_data._fetch_provider_latest(
        object(),
        SimpleNamespace(id=42, symbol="AAPL"),
        Timeframe.D1,
        10,
        True,
    )

    scope = captured["scope"]
    assert scope.instrument_id == 42
    assert scope.data_source_id == 17
    assert scope.timeframe == "D1"
    assert captured["kwargs"]["canonical"] is True
    assert captured["execute_kwargs"]["history_start"]("alpaca") == expected_history_start
    assert captured["execute_kwargs"]["operation_cost_overrides"]["fmp"] == 1
    assert result[0].market_series_id == 456


@pytest.mark.asyncio
async def test_provider_refresh_splits_mixed_sessions_into_distinct_series(monkeypatch):
    regular = _semantic_bar()
    extended = _semantic_bar()
    extended.session = "extended"
    extended.provenance = {"provider": "alpaca", "feed": "iex"}
    execution = SimpleNamespace(
        provider_name="alpaca",
        data_source=SimpleNamespace(id=17),
        result=[regular, extended],
    )
    scopes = []

    async def fake_get_or_create(_db, scope, **_kwargs):
        scopes.append(scope)
        return SimpleNamespace(id=100 + len(scopes))

    monkeypatch.setattr(market_data, "get_or_create_series", fake_get_or_create)
    monkeypatch.setattr(market_data, "provider_symbol_for_instrument", lambda *_args: "AAPL")

    result = await market_data._attach_provider_series(
        object(),
        SimpleNamespace(id=42),
        Timeframe.D1,
        True,
        execution,
    )

    assert len(scopes) == 2
    assert {scope.session_code for scope in scopes} == {"regular", "extended"}
    assert {bar.market_series_id for bar in result} == {101, 102}


def _bar(ts: datetime, timeframe: Timeframe = Timeframe.D1):
    return SimpleNamespace(ts=ts, timeframe=timeframe)


_NEW_YORK = ZoneInfo("America/New_York")


def _xnys_bar_open(day: date, timeframe: Timeframe = Timeframe.D1):
    return _bar(
        datetime.combine(day, datetime.min.time(), tzinfo=_NEW_YORK).astimezone(UTC), timeframe
    )


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

    weekday_start = datetime(2026, 1, 2, tzinfo=_NEW_YORK).astimezone(UTC)
    weekday_end = datetime(2026, 1, 6, 16, tzinfo=_NEW_YORK).astimezone(UTC)
    weekday_gap = missing_range_slices(
        [_xnys_bar_open(date(2026, 1, 2)), _xnys_bar_open(date(2026, 1, 6))],
        Timeframe.D1,
        weekday_start,
        weekday_end,
        calendar="XNYS",
    )
    assert weekday_gap == [
        (
            datetime(2026, 1, 5, tzinfo=_NEW_YORK).astimezone(UTC),
            datetime(2026, 1, 6, tzinfo=_NEW_YORK).astimezone(UTC) - timedelta(microseconds=1),
        )
    ]

    holiday_start = datetime(2026, 1, 16, tzinfo=_NEW_YORK).astimezone(UTC)
    holiday_end = datetime(2026, 1, 20, 16, tzinfo=_NEW_YORK).astimezone(UTC)
    holiday_gap = missing_range_slices(
        [_xnys_bar_open(date(2026, 1, 16)), _xnys_bar_open(date(2026, 1, 20))],
        Timeframe.D1,
        holiday_start,
        holiday_end,
        calendar="XNYS",
    )
    assert holiday_gap == []


def test_xnys_daily_gap_coalesces_across_weekend_holiday_and_dst():
    start = datetime(2026, 3, 6, tzinfo=_NEW_YORK).astimezone(UTC)
    end = datetime(2026, 3, 11, 16, tzinfo=_NEW_YORK).astimezone(UTC)
    cached = [_xnys_bar_open(date(2026, 3, 6)), _xnys_bar_open(date(2026, 3, 11))]

    slices = missing_range_slices(cached, Timeframe.D1, start, end, calendar="XNYS")

    assert slices == [
        (
            datetime(2026, 3, 9, tzinfo=_NEW_YORK).astimezone(UTC),
            datetime(2026, 3, 11, tzinfo=_NEW_YORK).astimezone(UTC) - timedelta(microseconds=1),
        )
    ]
    assert slices[0][0] < slices[0][1]
    # The local-midnight bar timestamp after the DST transition is 04:00 UTC.
    assert slices[0][0] == datetime(2026, 3, 9, 4, tzinfo=UTC)
    assert _is_positive_repair_slice(*slices[0]) is True


def test_xnys_thanksgiving_closure_and_saturday_new_year_observation():
    from app.services.ohlcv_coverage import _xnys_holidays

    # Thanksgiving is not a missing trading session, while the Friday after it
    # remains a session (with its close handled by exchange_sessions).
    start = datetime(2026, 11, 25, tzinfo=_NEW_YORK).astimezone(UTC)
    end = datetime(2026, 11, 27, 16, tzinfo=_NEW_YORK).astimezone(UTC)
    gap = missing_range_slices(
        [_xnys_bar_open(date(2026, 11, 25)), _xnys_bar_open(date(2026, 11, 27))],
        Timeframe.D1,
        start,
        end,
        calendar="XNYS",
    )
    assert gap == []

    # A Saturday New Year's Day is not observed on the preceding Friday.
    assert date(2021, 12, 31) not in _xnys_holidays(2022)
    assert date(2027, 12, 31) not in _xnys_holidays(2028)


def test_xnys_daily_present_session_splits_true_interior_holes():
    start = datetime(2026, 3, 9, tzinfo=_NEW_YORK).astimezone(UTC)
    end = datetime(2026, 3, 13, 16, tzinfo=_NEW_YORK).astimezone(UTC)
    cached = [
        _xnys_bar_open(date(2026, 3, 9)),
        _xnys_bar_open(date(2026, 3, 11)),
        _xnys_bar_open(date(2026, 3, 13)),
    ]

    slices = missing_range_slices(cached, Timeframe.D1, start, end, calendar="XNYS")

    assert len(slices) == 2
    assert all(left < right for left, right in slices)
    assert slices[0][1] < slices[1][0]


def test_xnys_daily_presence_accepts_native_and_utc_midnight_labels():
    start = datetime(2026, 3, 9, tzinfo=UTC)
    end = datetime(2026, 3, 11, 23, 59, tzinfo=UTC)
    sessions = [date(2026, 3, 9), date(2026, 3, 10), date(2026, 3, 11)]
    representations = [
        [_xnys_bar_open(session) for session in sessions],
        [_bar(datetime.combine(session, datetime.min.time(), tzinfo=UTC)) for session in sessions],
    ]

    for cached in representations:
        assert missing_range_slices(cached, Timeframe.D1, start, end, calendar="XNYS") == []


def test_xnys_partial_daily_window_ignores_unopened_and_incomplete_sessions():
    start = datetime(2026, 3, 9, 12, tzinfo=_NEW_YORK).astimezone(UTC)
    end = datetime(2026, 3, 11, 15, tzinfo=_NEW_YORK).astimezone(UTC)
    cached = [_xnys_bar_open(date(2026, 3, 10)), _xnys_bar_open(date(2026, 3, 11))]

    assert missing_range_slices(cached, Timeframe.D1, start, end, calendar="XNYS") == []


def test_xnys_long_daily_cache_gap_stays_within_existing_slice_bound():
    from app.services.ohlcv_coverage import _xnys_session_days

    start = datetime(2024, 11, 8, tzinfo=UTC)
    end = datetime(2026, 11, 5, 15, tzinfo=_NEW_YORK).astimezone(UTC)
    cached = [
        _xnys_bar_open(session)
        for session in sorted(_xnys_session_days(date(2026, 5, 11), date(2026, 11, 4)))
    ]

    slices = missing_range_slices(cached, Timeframe.D1, start, end, calendar="XNYS")

    assert len(cached) == 124
    assert len(slices) == 1
    assert len(slices) <= 8
    assert slices[0][0] >= start
    assert slices[0][0] < _xnys_bar_open(date(2026, 5, 11)).ts

    # When the next requested session has closed, it is a second repair run;
    # it stays separate from the long prefix across the present cached data.
    after_close = datetime(2026, 11, 5, 17, tzinfo=_NEW_YORK).astimezone(UTC)
    with_completed_tail = missing_range_slices(
        cached, Timeframe.D1, start, after_close, calendar="XNYS"
    )
    assert len(with_completed_tail) == 2
    assert with_completed_tail[-1] == (
        _xnys_bar_open(date(2026, 11, 5)).ts,
        after_close,
    )


@pytest.mark.parametrize(
    ("timeframe", "cached_starts"),
    [
        (Timeframe.W1, [date(2026, 5, 11) + timedelta(days=7 * index) for index in range(26)]),
        (Timeframe.MN, [date(2026, month, 1) for month in range(5, 12)]),
    ],
)
def test_xnys_weekly_and_monthly_short_cache_is_partial_and_acquirable(timeframe, cached_starts):
    start = datetime(2024, 11, 8, tzinfo=UTC)
    end = datetime(2026, 11, 5, 15, tzinfo=_NEW_YORK).astimezone(UTC)
    cached = [_xnys_bar_open(day, timeframe) for day in cached_starts]

    assessment = assess_ohlcv_coverage(cached, timeframe, start, end, calendar="XNYS", now=end)

    assert assessment.status is CoverageStatus.PARTIAL
    assert assessment.bar_count == len(cached)
    assert assessment.missing_slices
    assert assessment.missing_slices[0][0] < cached[0].ts
    assert assessment.missing_slices[0][0] >= start
    assert _needs_fetch_for_range(cached, timeframe, start, end, calendar="XNYS") is True
    if timeframe == Timeframe.MN:
        # Calendar month ends are not approximated as 30-day intervals.
        assert assessment.missing_slices[0] == (
            datetime(2024, 12, 1, tzinfo=UTC),
            datetime(2026, 5, 1, tzinfo=UTC) - timedelta(microseconds=1),
        )


@pytest.mark.parametrize("timeframe", [Timeframe.W1, Timeframe.MN])
def test_xnys_complete_weekly_or_monthly_cache_does_not_replan_history(timeframe):
    start = datetime(2024, 11, 8, tzinfo=UTC)
    end = datetime(2026, 9, 30, 23, tzinfo=UTC)
    if timeframe == Timeframe.W1:
        first = date(2024, 11, 11)
        # Through the requested period. Later cached bars may exist but must
        # not change the complete historical selection.
        cached_starts = [first + timedelta(days=7 * index) for index in range(103)]
    else:
        cursor = date(2024, 12, 1)
        cached_starts = []
        while cursor < date(2026, 11, 1):
            cached_starts.append(cursor)
            cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
    cached = [_xnys_bar_open(day, timeframe) for day in cached_starts]

    assert missing_range_slices(cached, timeframe, start, end, calendar="XNYS") == []
    assert _needs_fetch_for_range(cached, timeframe, start, end, calendar="XNYS") is False


@pytest.mark.parametrize(
    ("timeframe", "start", "cached_start"),
    [
        (Timeframe.W1, datetime(2026, 10, 26, tzinfo=UTC), date(2026, 10, 26)),
        (Timeframe.MN, datetime(2026, 10, 1, tzinfo=UTC), date(2026, 10, 1)),
    ],
)
def test_xnys_unfinished_current_week_or_month_does_not_create_tail_gap(
    timeframe, start, cached_start
):
    end = datetime(2026, 11, 5, 15, tzinfo=_NEW_YORK).astimezone(UTC)

    assert (
        missing_range_slices(
            [_xnys_bar_open(cached_start, timeframe)],
            timeframe,
            start,
            end,
            calendar="XNYS",
        )
        == []
    )


def test_xnys_ad_hoc_nyse_closure_is_not_a_reselection_gap():
    start = datetime(2025, 1, 6, tzinfo=_NEW_YORK).astimezone(UTC)
    end = datetime(2025, 1, 10, 16, tzinfo=_NEW_YORK).astimezone(UTC)
    cached = [
        _xnys_bar_open(day)
        for day in (date(2025, 1, 6), date(2025, 1, 7), date(2025, 1, 8), date(2025, 1, 10))
    ]

    assert missing_range_slices(cached, Timeframe.D1, start, end, calendar="XNYS") == []
    assert _needs_fetch_for_range(cached, Timeframe.D1, start, end, calendar="XNYS") is False


def test_xnys_unsupported_intraday_grid_uses_conservative_interval_fallback():
    start = datetime(2026, 1, 5, tzinfo=UTC)
    end = start + timedelta(hours=12)
    cached = [_bar(start, Timeframe.H1)]

    assert missing_range_slices(cached, Timeframe.H1, start, end, calendar="XNYS")


def test_xnys_incomplete_current_session_does_not_create_false_tail():
    start = datetime(2026, 11, 4, tzinfo=_NEW_YORK).astimezone(UTC)
    end = datetime(2026, 11, 5, 15, tzinfo=_NEW_YORK).astimezone(UTC)
    cached = [_xnys_bar_open(date(2026, 11, 4))]

    assert missing_range_slices(cached, Timeframe.D1, start, end, calendar="XNYS") == []


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


@pytest.mark.parametrize("timeframe", [Timeframe.D1, Timeframe.W1, Timeframe.MN])
def test_coverage_planner_reports_cold_range_and_bounded_slice(timeframe):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 5, tzinfo=UTC)
    assessment = assess_ohlcv_coverage([], timeframe, start, end, calendar="XNYS")

    assert assessment.status is CoverageStatus.MISSING
    assert assessment.missing_slices == ((start, end),)
    assert assessment.bar_count == 0


@pytest.mark.asyncio
async def test_identical_provider_refreshes_are_coalesced_per_process(monkeypatch):
    active = 0
    max_active = 0
    provider_calls = 0
    cache_ready = False

    async def fake_impl(*_args, **_kwargs):
        nonlocal active, max_active, provider_calls, cache_ready
        if cache_ready:
            return ["cached"]
        provider_calls += 1
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0)
        active -= 1
        cache_ready = True
        return ["fresh"]

    monkeypatch.setattr(market_data, "_fetch_ohlcv_impl", fake_impl)
    instrument = SimpleNamespace(id=42, is_synthetic=False)
    start = datetime(2026, 1, 1, tzinfo=UTC)

    results = await asyncio.gather(
        market_data.fetch_ohlcv(object(), instrument, Timeframe.D1, start),
        market_data.fetch_ohlcv(object(), instrument, Timeframe.D1, start),
    )

    assert results == [["fresh"], ["cached"]]
    assert provider_calls == 1
    assert max_active == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["latest", "page_before"])
async def test_implicit_ohlcv_refresh_paths_are_coalesced_per_process(monkeypatch, operation):
    active = 0
    provider_calls = 0
    cache_ready = False

    async def fake_impl(*_args, **_kwargs):
        nonlocal active, provider_calls, cache_ready
        if cache_ready:
            return ["cached"]
        provider_calls += 1
        active += 1
        assert active == 1
        await asyncio.sleep(0)
        active -= 1
        cache_ready = True
        return ["fresh"]

    instrument = SimpleNamespace(id=43, is_synthetic=False)
    before = datetime(2026, 2, 1, tzinfo=UTC)
    if operation == "latest":
        monkeypatch.setattr(market_data, "_fetch_ohlcv_latest_impl", fake_impl)
        calls = [
            market_data.fetch_ohlcv_latest(object(), instrument, Timeframe.D1, 10),
            market_data.fetch_ohlcv_latest(object(), instrument, Timeframe.D1, 10),
        ]
    else:
        monkeypatch.setattr(market_data, "_fetch_ohlcv_page_before_impl", fake_impl)
        calls = [
            market_data.fetch_ohlcv_page_before(object(), instrument, Timeframe.D1, before, 10),
            market_data.fetch_ohlcv_page_before(object(), instrument, Timeframe.D1, before, 10),
        ]

    assert await asyncio.gather(*calls) == [["fresh"], ["cached"]]
    assert provider_calls == 1


@pytest.mark.asyncio
async def test_postgres_refresh_lock_uses_transaction_scoped_advisory_lock():
    executed = []

    class _Db:
        bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        async def execute(self, statement):
            executed.append(statement)

    key = (42, Timeframe.D1.value, datetime(2026, 1, 1, tzinfo=UTC), None, True)
    await market_data._acquire_database_refresh_lock(_Db(), key)

    assert len(executed) == 1


@pytest.mark.asyncio
async def test_non_postgres_refresh_lock_is_a_noop():
    class _Db:
        bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

        async def execute(self, _statement):
            raise AssertionError("SQLite must not receive PostgreSQL advisory SQL")

    key = (42, Timeframe.D1.value, datetime(2026, 1, 1, tzinfo=UTC), None, True)
    await market_data._acquire_database_refresh_lock(_Db(), key)


@pytest.mark.asyncio
async def test_redis_refresh_lock_wraps_operation_and_releases_ownership(monkeypatch):
    calls: list[tuple] = []

    class _Lock:
        async def acquire(self):
            calls.append(("acquire",))
            return True

        async def release(self):
            calls.append(("release",))

    class _Redis:
        def lock(self, *args, **kwargs):
            calls.append(("lock", args, kwargs))
            return _Lock()

    monkeypatch.setattr(market_data.settings, "OHLCV_DISTRIBUTED_LOCK_ENABLED", True)
    instrument = SimpleNamespace(id=44, is_synthetic=False)
    start = datetime(2026, 1, 1, tzinfo=UTC)

    async def operation():
        calls.append(("operation",))
        return ["fresh"]

    result = await market_data._with_ohlcv_refresh_gate(
        instrument,
        Timeframe.D1,
        start,
        None,
        True,
        allow_provider_fetch=True,
        redis=_Redis(),
        operation=operation,
    )

    assert result == ["fresh"]
    assert [call[0] for call in calls] == ["lock", "acquire", "operation", "release"]
    assert calls[0][2]["timeout"] == market_data.settings.OHLCV_DISTRIBUTED_LOCK_TTL_SECONDS


@pytest.mark.asyncio
async def test_redis_refresh_lock_timeout_fails_closed_without_operation(monkeypatch):
    called = False

    class _Lock:
        async def acquire(self):
            return False

        async def release(self):
            raise AssertionError("a lock not acquired must not be released")

    class _Redis:
        def lock(self, *_args, **_kwargs):
            return _Lock()

    monkeypatch.setattr(market_data.settings, "OHLCV_DISTRIBUTED_LOCK_ENABLED", True)
    instrument = SimpleNamespace(id=45, is_synthetic=False)
    start = datetime(2026, 1, 1, tzinfo=UTC)

    async def operation():
        nonlocal called
        called = True
        return ["unsafe"]

    from app.services.distributed_locks import DistributedLockError

    with pytest.raises(DistributedLockError, match="timed out"):
        await market_data._with_ohlcv_refresh_gate(
            instrument,
            Timeframe.D1,
            start,
            None,
            True,
            allow_provider_fetch=True,
            redis=_Redis(),
            operation=operation,
        )
    assert called is False


@pytest.mark.asyncio
async def test_redis_refresh_lock_is_not_used_until_explicitly_enabled(monkeypatch):
    class _Redis:
        def lock(self, *_args, **_kwargs):
            raise AssertionError("disabled mode must not contact Redis")

    monkeypatch.setattr(market_data.settings, "OHLCV_DISTRIBUTED_LOCK_ENABLED", False)
    instrument = SimpleNamespace(id=46, is_synthetic=False)
    start = datetime(2026, 1, 1, tzinfo=UTC)

    async def operation():
        return ["local"]

    assert await market_data._with_ohlcv_refresh_gate(
        instrument,
        Timeframe.D1,
        start,
        None,
        True,
        allow_provider_fetch=True,
        redis=_Redis(),
        operation=operation,
    ) == ["local"]


@pytest.mark.asyncio
async def test_latest_price_refresh_rechecks_cache_inside_process_gate(monkeypatch):
    instrument = SimpleNamespace(
        id=47,
        symbol="AAPL",
        listings=[],
        provider_symbols=[],
    )
    state = {"price": None}
    execute_calls = 0
    stored_payloads: list[object] = []
    stored_response_sets: list[object] = []

    async def fake_cache(_db, _instrument):
        return state["price"]

    async def fake_execute(*_args, **_kwargs):
        nonlocal execute_calls
        execute_calls += 1
        await asyncio.sleep(0)
        return SimpleNamespace(
            provider_name="yfinance",
            data_source=SimpleNamespace(id=1),
            result=123.45,
            response_payloads=({"price": 123.45, "symbol": "AAPL"},),
        )

    async def fake_store(*_args, **_kwargs):
        state["price"] = 123.45
        stored_payloads.append(_kwargs["payload"])
        stored_response_sets.append(_kwargs["payloads"])

    monkeypatch.setattr(market_data.settings, "OHLCV_DISTRIBUTED_LOCK_ENABLED", False)
    monkeypatch.setattr(market_data, "_fresh_latest_price_from_cache", fake_cache)
    monkeypatch.setattr(market_data, "execute_provider_call", fake_execute)
    monkeypatch.setattr(market_data, "store_latest_price_snapshot", fake_store)

    results = await asyncio.gather(
        market_data.get_current_price_async(object(), instrument),
        market_data.get_current_price_async(object(), instrument),
    )

    assert results == [123.45, 123.45]
    assert execute_calls == 1
    assert stored_payloads == [{"price": 123.45, "symbol": "AAPL"}]
    assert stored_response_sets == [({"price": 123.45, "symbol": "AAPL"},)]


@pytest.mark.asyncio
async def test_latest_price_refresh_uses_opt_in_redis_gate(monkeypatch):
    calls: list[tuple] = []
    instrument = SimpleNamespace(
        id=48,
        symbol="MSFT",
        listings=[],
        provider_symbols=[],
    )
    state = {"price": None}

    class _Lock:
        async def acquire(self):
            calls.append(("acquire",))
            return True

        async def release(self):
            calls.append(("release",))

    class _Redis:
        def lock(self, *args, **kwargs):
            calls.append(("lock", args, kwargs))
            return _Lock()

    async def fake_cache(_db, _instrument):
        return state["price"]

    async def fake_execute(*_args, **_kwargs):
        calls.append(("provider",))
        return SimpleNamespace(
            provider_name="yfinance",
            data_source=SimpleNamespace(id=1),
            result=234.56,
        )

    async def fake_store(*_args, **_kwargs):
        state["price"] = 234.56

    monkeypatch.setattr(market_data.settings, "OHLCV_DISTRIBUTED_LOCK_ENABLED", True)
    monkeypatch.setattr(market_data, "_fresh_latest_price_from_cache", fake_cache)
    monkeypatch.setattr(market_data, "execute_provider_call", fake_execute)
    monkeypatch.setattr(market_data, "store_latest_price_snapshot", fake_store)

    result = await market_data.get_current_price_async(object(), instrument, redis=_Redis())

    assert result == 234.56
    assert [call[0] for call in calls] == ["lock", "acquire", "provider", "release"]
    assert calls[0][2]["timeout"] == market_data.settings.OHLCV_DISTRIBUTED_LOCK_TTL_SECONDS


@pytest.mark.asyncio
async def test_latest_price_refresh_redis_timeout_fails_closed_without_provider(monkeypatch):
    instrument = SimpleNamespace(
        id=49,
        symbol="NVDA",
        listings=[],
        provider_symbols=[],
    )
    provider_called = False

    class _Lock:
        async def acquire(self):
            return False

        async def release(self):
            raise AssertionError("a lock not acquired must not be released")

    class _Redis:
        def lock(self, *_args, **_kwargs):
            return _Lock()

    async def fake_cache(_db, _instrument):
        return None

    async def fake_execute(*_args, **_kwargs):
        nonlocal provider_called
        provider_called = True
        raise AssertionError("provider must not run when latest-price lock times out")

    monkeypatch.setattr(market_data.settings, "OHLCV_DISTRIBUTED_LOCK_ENABLED", True)
    monkeypatch.setattr(market_data, "_fresh_latest_price_from_cache", fake_cache)
    monkeypatch.setattr(market_data, "execute_provider_call", fake_execute)

    from app.services.distributed_locks import DistributedLockError

    with pytest.raises(DistributedLockError, match="timed out"):
        await market_data.get_current_price_async(object(), instrument, redis=_Redis())
    assert provider_called is False
