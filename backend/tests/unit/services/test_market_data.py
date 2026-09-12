import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.models.ohlcv import TIMEFRAME_SECONDS, OHLCVBar, Timeframe
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

    instrument = SimpleNamespace(id=42)
    result = await market_data._fetch_provider(
        object(),
        instrument,
        Timeframe.D1,
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 1, 3, tzinfo=UTC),
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
    assert result[0].market_series_id == 123


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
