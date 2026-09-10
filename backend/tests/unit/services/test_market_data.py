from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.ohlcv import TIMEFRAME_SECONDS, Timeframe
from app.services.market_data import (
    _historical_repair_start,
    _is_positive_repair_slice,
    _is_recoverable_provider_gap,
    _needs_fetch_for_range,
    _touch_ohlcv_dataset_state,
    fetch_ohlcv,
    fetch_ohlcv_latest,
    fetch_ohlcv_page_before,
    persist_price_history_bars,
)
from app.services.ohlcv_coverage import (
    CoverageStatus,
    assess_observed_ohlcv_cadence,
    assess_ohlcv_coverage,
    missing_range_slices,
)
from app.services.provider_runtime import ProviderNoDataError
from tests.unit.conftest import AsyncSessionAdapter


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
    assert _is_recoverable_provider_gap(RuntimeError("unexpected programming failure")) is False


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


def test_observed_ohlcv_cadence_uses_distinct_returned_timestamps():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    bars = [
        SimpleNamespace(ts=start),
        SimpleNamespace(ts=start + timedelta(days=1)),
        SimpleNamespace(ts=start + timedelta(days=9)),
        SimpleNamespace(ts=start + timedelta(days=9)),
    ]

    assessment = assess_observed_ohlcv_cadence(bars)

    assert assessment.status == "observed_cadence"
    assert assessment.sample_count == 2
    assert assessment.median_interval_days == 4.5
    assert assessment.min_interval_days == 1.0
    assert assessment.max_interval_days == 8.0


def test_observed_ohlcv_cadence_reports_empty_and_single_ranges():
    assert assess_observed_ohlcv_cadence([]).status == "no_observation"
    bar = SimpleNamespace(ts=datetime(2026, 1, 1))
    assert assess_observed_ohlcv_cadence([bar]).status == "single_observation"


@pytest.mark.asyncio
async def test_provider_dataset_state_marks_opaque_adjustment_factors_explicitly(db, instrument):
    from app.models.data_source import DataSource
    from app.models.ohlcv import OHLCVBar
    from app.models.provider_observation import InstrumentDatasetState

    source = DataSource(name="opaque-factor-provider")
    db.add(source)
    db.flush()
    bar = OHLCVBar(
        instrument_id=instrument.id,
        timeframe=Timeframe.D1,
        ts=datetime(2026, 1, 2, tzinfo=UTC),
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal("10"),
        is_adjusted=True,
    )
    db.add(bar)
    db.flush()

    await _touch_ohlcv_dataset_state(
        AsyncSessionAdapter(db),
        instrument,
        data_source_id=source.id,
        timeframe=Timeframe.D1,
        adjusted=True,
        bars=[bar],
        fetched_at=datetime(2026, 1, 3, tzinfo=UTC),
    )

    state = (
        db.query(InstrumentDatasetState)
        .filter(
            InstrumentDatasetState.instrument_id == instrument.id,
            InstrumentDatasetState.data_source_id == source.id,
            InstrumentDatasetState.dataset_key == "D1:adj",
        )
        .one()
    )
    assert state.extra_data["adjustment_provenance"] == {
        "mode": "split_adjusted",
        "source_kind": "provider_observation",
        "factor_status": "provider_native_opaque",
        "factor_version": None,
        "contract_version": 1,
    }


@pytest.mark.asyncio
async def test_provider_dataset_state_records_rebuildable_split_factor_version(db, instrument):
    from app.models.data_source import DataSource
    from app.models.instrument_event import EventTimeHint, InstrumentEvent, InstrumentEventType
    from app.models.ohlcv import OHLCVBar
    from app.models.provider_observation import InstrumentDatasetState

    source = DataSource(name="rebuildable-factor-provider")
    db.add(source)
    db.flush()
    event_time = datetime(2025, 6, 10, tzinfo=UTC)
    db.add(
        InstrumentEvent(
            instrument_id=instrument.id,
            event_type=InstrumentEventType.SPLIT,
            event_time=event_time,
            time_hint=EventTimeHint.UNKNOWN,
            title="Fixture split",
            source=source.name,
            source_event_key="split:2025-06-10",
            split_ratio=Decimal("2"),
            fetched_at=event_time,
        )
    )
    bar = OHLCVBar(
        instrument_id=instrument.id,
        timeframe=Timeframe.D1,
        ts=datetime(2026, 1, 2, tzinfo=UTC),
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal("10"),
        is_adjusted=True,
    )
    db.add(bar)
    db.flush()

    await _touch_ohlcv_dataset_state(
        AsyncSessionAdapter(db),
        instrument,
        data_source_id=source.id,
        timeframe=Timeframe.D1,
        adjusted=True,
        bars=[bar],
        fetched_at=datetime(2026, 1, 3, tzinfo=UTC),
    )

    state = (
        db.query(InstrumentDatasetState)
        .filter(
            InstrumentDatasetState.instrument_id == instrument.id,
            InstrumentDatasetState.data_source_id == source.id,
            InstrumentDatasetState.dataset_key == "D1:adj",
        )
        .one()
    )
    provenance = state.extra_data["adjustment_provenance"]
    assert provenance["factor_status"] == "rebuildable_split_factors"
    assert provenance["factor_version"].startswith("afv1-")


@pytest.mark.asyncio
async def test_provider_dataset_state_prefers_durable_factor_observation_provenance(db, instrument):
    from app.models.adjustment_factor import AdjustmentFactorObservation
    from app.models.data_source import DataSource
    from app.models.ohlcv import OHLCVBar
    from app.models.provider_observation import InstrumentDatasetState

    source = DataSource(name="durable-factor-provider")
    db.add(source)
    db.flush()
    event_time = datetime(2025, 6, 10, tzinfo=UTC)
    db.add(
        AdjustmentFactorObservation(
            instrument_id=instrument.id,
            data_source_id=source.id,
            provider_symbol="TEST",
            factor_type="split",
            effective_at=event_time,
            factor=Decimal("2"),
            source_event_key="split:2025-06-10",
            observed_at=event_time,
            factor_version="afv1-durable",
        )
    )
    bar = OHLCVBar(
        instrument_id=instrument.id,
        timeframe=Timeframe.D1,
        ts=datetime(2026, 1, 2, tzinfo=UTC),
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal("10"),
        is_adjusted=True,
    )
    db.add(bar)
    db.flush()

    await _touch_ohlcv_dataset_state(
        AsyncSessionAdapter(db),
        instrument,
        data_source_id=source.id,
        timeframe=Timeframe.D1,
        adjusted=True,
        bars=[bar],
        fetched_at=datetime(2026, 1, 3, tzinfo=UTC),
    )

    state = (
        db.query(InstrumentDatasetState)
        .filter(
            InstrumentDatasetState.instrument_id == instrument.id,
            InstrumentDatasetState.data_source_id == source.id,
            InstrumentDatasetState.dataset_key == "D1:adj",
        )
        .one()
    )
    assert state.extra_data["adjustment_provenance"] == {
        "mode": "split_adjusted",
        "source_kind": "provider_observation",
        "factor_status": "rebuildable_split_factors",
        "factor_version": "afv1-durable",
        "contract_version": 1,
        "factor_observation_count": 1,
        "factor_rebuildable_observation_count": 1,
        "factor_opaque_observation_count": 0,
        "factor_kinds": ["split_ratio"],
    }


@pytest.mark.asyncio
async def test_provider_dataset_state_applies_provider_dividend_factor_provenance(db, instrument):
    from app.models.adjustment_factor import AdjustmentFactorObservation
    from app.models.data_source import DataSource
    from app.models.ohlcv import OHLCVBar
    from app.models.provider_observation import InstrumentDatasetState

    source = DataSource(name="provider-dividend-factor-state")
    db.add(source)
    db.flush()
    event_time = datetime(2025, 6, 10, tzinfo=UTC)
    db.add(
        AdjustmentFactorObservation(
            instrument_id=instrument.id,
            data_source_id=source.id,
            provider_symbol="TEST",
            factor_type="dividend",
            effective_at=event_time,
            factor=Decimal("0.9975"),
            factor_kind="provider_supplied",
            amount=Decimal("0.25"),
            source_event_key="dividend:2025-06-10",
            observed_at=event_time,
            factor_version="afv1-provider-dividend",
        )
    )
    bar = OHLCVBar(
        instrument_id=instrument.id,
        timeframe=Timeframe.D1,
        ts=datetime(2026, 1, 2, tzinfo=UTC),
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal("10"),
        is_adjusted=True,
    )
    db.add(bar)
    db.flush()

    await _touch_ohlcv_dataset_state(
        AsyncSessionAdapter(db),
        instrument,
        data_source_id=source.id,
        timeframe=Timeframe.D1,
        adjusted=True,
        bars=[bar],
        fetched_at=datetime(2026, 1, 3, tzinfo=UTC),
    )

    state = (
        db.query(InstrumentDatasetState)
        .filter(
            InstrumentDatasetState.instrument_id == instrument.id,
            InstrumentDatasetState.data_source_id == source.id,
            InstrumentDatasetState.dataset_key == "D1:adj",
        )
        .one()
    )
    assert state.extra_data["adjustment_provenance"] == {
        "mode": "split_adjusted",
        "source_kind": "provider_observation",
        "factor_status": "rebuildable_provider_factors",
        "factor_version": "afv1-provider-dividend",
        "contract_version": 1,
        "factor_observation_count": 1,
        "factor_rebuildable_observation_count": 1,
        "factor_opaque_observation_count": 0,
        "factor_kinds": ["provider_supplied"],
    }


@pytest.mark.asyncio
async def test_provider_upsert_promotes_a_matching_derived_bar_to_provider_lineage(
    db, instrument, monkeypatch
):
    from app.models.data_source import DataSource
    from app.models.ohlcv import OHLCVBar

    async def _skip_observation_record(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "app.services.market_data._record_bar_observations", _skip_observation_record
    )
    source = DataSource(name="provider-lineage-source")
    db.add(source)
    db.flush()
    ts = datetime(2026, 1, 5, tzinfo=UTC)
    db.add(
        OHLCVBar(
            instrument_id=instrument.id,
            timeframe=Timeframe.W1,
            ts=ts,
            open=Decimal("90"),
            high=Decimal("95"),
            low=Decimal("89"),
            close=Decimal("92"),
            volume=Decimal("100"),
            is_adjusted=True,
            is_derived=True,
            source_timeframe=Timeframe.D1.value,
            derivation_method="d1_ohlcv_xnys_calendar_aggregation",
            derived_at=datetime(2026, 1, 6, tzinfo=UTC),
            source_bar_count=5,
            source_start=datetime(2026, 1, 1, tzinfo=UTC),
            source_end=datetime(2026, 1, 5, tzinfo=UTC),
        )
    )
    db.flush()

    await persist_price_history_bars(
        AsyncSessionAdapter(db),
        instrument,
        data_source_id=source.id,
        provider_symbol="AAPL",
        timeframe=Timeframe.W1,
        adjusted=True,
        bars=[
            OHLCVBar(
                instrument_id=instrument.id,
                data_source_id=source.id,
                timeframe=Timeframe.W1,
                ts=ts,
                open=Decimal("100"),
                high=Decimal("110"),
                low=Decimal("99"),
                close=Decimal("105"),
                volume=Decimal("200"),
                is_adjusted=True,
            )
        ],
    )
    row = (
        db.query(OHLCVBar)
        .filter(
            OHLCVBar.instrument_id == instrument.id,
            OHLCVBar.timeframe == Timeframe.W1,
            OHLCVBar.ts == ts,
        )
        .one()
    )

    assert row.close == Decimal("105")
    assert row.data_source_id == source.id
    assert row.is_derived is False
    assert row.source_timeframe is None
    assert row.derivation_method is None
    assert row.derived_at is None
    assert row.source_bar_count is None
    assert row.source_start is None
    assert row.source_end is None


def _provider_coarse_bar(instrument_id: int, ts: datetime):
    from app.models.ohlcv import OHLCVBar

    return OHLCVBar(
        instrument_id=instrument_id,
        timeframe=Timeframe.W1,
        ts=ts,
        open=Decimal("999"),
        high=Decimal("1001"),
        low=Decimal("998"),
        close=Decimal("1000"),
        volume=Decimal("1"),
        is_adjusted=True,
        is_derived=False,
    )


@pytest.mark.asyncio
async def test_provider_enabled_range_merges_partial_coarse_rows_with_derived_history(
    db, instrument, ohlcv_bars, monkeypatch
):
    from app.models.ohlcv import OHLCVBar

    provider_ts = datetime(2024, 1, 1, tzinfo=UTC)
    db.add(_provider_coarse_bar(instrument.id, provider_ts))
    db.flush()
    monkeypatch.setattr(
        "app.services.market_data._needs_fetch_for_range", lambda *_args, **_kwargs: False
    )

    rows = await fetch_ohlcv(
        AsyncSessionAdapter(db),
        instrument,
        Timeframe.W1,
        provider_ts,
        datetime(2024, 1, 31, tzinfo=UTC),
        allow_provider_fetch=True,
    )

    assert any(row.is_derived is False and row.close == Decimal("1000") for row in rows)
    assert any(row.is_derived is True for row in rows)
    assert (
        db.query(OHLCVBar)
        .filter(
            OHLCVBar.instrument_id == instrument.id,
            OHLCVBar.timeframe == Timeframe.W1,
            OHLCVBar.is_derived.is_(True),
        )
        .count()
        > 0
    )


@pytest.mark.asyncio
async def test_provider_enabled_latest_merges_partial_coarse_rows_with_derived_history(
    db, instrument, ohlcv_bars, monkeypatch
):
    provider_ts = datetime(2024, 1, 1, tzinfo=UTC)
    db.add(_provider_coarse_bar(instrument.id, provider_ts))
    db.flush()

    async def _no_provider_data(*_args, **_kwargs):
        raise ProviderNoDataError("coarse provider unavailable")

    monkeypatch.setattr("app.services.market_data._fetch_provider", _no_provider_data)
    monkeypatch.setattr("app.services.market_data._needs_fetch", lambda *_args: False)

    async def _repair_start(*_args):
        return provider_ts - timedelta(days=7)

    monkeypatch.setattr("app.services.market_data._latest_window_start", _repair_start)

    rows = await fetch_ohlcv_latest(
        AsyncSessionAdapter(db),
        instrument,
        Timeframe.W1,
        500,
        allow_provider_fetch=True,
    )

    assert any(row.is_derived is False and row.close == Decimal("1000") for row in rows)
    assert any(row.is_derived is True for row in rows)
    assert rows == sorted(rows, key=lambda row: row.ts)


@pytest.mark.asyncio
async def test_provider_enabled_historical_page_merges_partial_coarse_rows_with_derived_history(
    db, instrument, ohlcv_bars, monkeypatch
):
    provider_ts = datetime(2024, 1, 1, tzinfo=UTC)
    db.add(_provider_coarse_bar(instrument.id, provider_ts))
    db.flush()

    async def _no_provider_data(*_args, **_kwargs):
        raise ProviderNoDataError("coarse provider unavailable")

    monkeypatch.setattr("app.services.market_data._fetch_provider", _no_provider_data)

    rows = await fetch_ohlcv_page_before(
        AsyncSessionAdapter(db),
        instrument,
        Timeframe.W1,
        datetime(2024, 6, 1, tzinfo=UTC),
        500,
        allow_provider_fetch=True,
    )

    assert any(row.is_derived is False and row.close == Decimal("1000") for row in rows)
    assert any(row.is_derived is True for row in rows)
    assert all(row.ts.replace(tzinfo=UTC) < datetime(2024, 6, 1, tzinfo=UTC) for row in rows)
    assert rows == sorted(rows, key=lambda row: row.ts)
