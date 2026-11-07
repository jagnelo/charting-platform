from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.data_source import DataSource
from app.models.market_data_foundation import (
    AdjustmentBasis,
    MarketSeries,
    MarketSeriesDefault,
)
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_observation import DatasetStatus, InstrumentDatasetState
from app.services.derived_timeframes import (
    DERIVATION_METHOD,
    _canonical_d1_signature,
    aggregate_d1_bars,
    derived_timeframe_needs_refresh,
    materialize_derived_timeframes,
)
from tests.unit.conftest import AsyncSessionAdapter


def _bar(day: int, *, close: str, volume: str = "100"):
    return SimpleNamespace(
        ts=datetime(2025, 1, day, tzinfo=UTC),
        open=Decimal(close) - 1,
        high=Decimal(close) + 2,
        low=Decimal(close) - 2,
        close=Decimal(close),
        volume=Decimal(volume),
        vwap=Decimal(close),
    )


def test_aggregate_d1_bars_uses_calendar_periods_without_filling_gaps():
    payloads = aggregate_d1_bars(
        [_bar(2, close="10"), _bar(3, close="11"), _bar(9, close="13")],
        Timeframe.W1,
    )

    assert len(payloads) == 2
    assert payloads[0]["period_key"] == (2025, 1)
    assert payloads[0]["source_bar_count"] == 2
    assert payloads[0]["open"] == Decimal("9")
    assert payloads[0]["close"] == Decimal("11")
    assert payloads[1]["period_key"] == (2025, 2)


def test_aggregate_d1_bars_normalizes_offset_timestamps_to_utc_calendar():
    bar = _bar(2, close="10")
    # Sunday in the source offset is Monday in UTC.  XNYS periods must use the
    # canonical UTC timestamp, not the provider's presentation offset.
    bar.ts = datetime(2025, 1, 5, 23, tzinfo=timezone(timedelta(hours=-5)))

    payload = aggregate_d1_bars([bar], Timeframe.W1)[0]

    assert payload["period_key"] == (2025, 2)
    assert payload["ts"] == datetime(2025, 1, 6, 4, tzinfo=UTC)
    assert payload["source_start"] == payload["ts"]
    assert payload["source_end"] == payload["ts"]


@pytest.mark.asyncio
async def test_materialize_derived_timeframes_persists_lineage_and_preserves_provider_rows(
    db, instrument
):
    for day, close in ((2, "10"), (3, "11"), (9, "13"), (10, "14")):
        db.add(
            OHLCVBar(
                instrument_id=instrument.id,
                timeframe=Timeframe.D1,
                ts=datetime(2025, 1, day, tzinfo=UTC),
                open=Decimal(close) - 1,
                high=Decimal(close) + 2,
                low=Decimal(close) - 2,
                close=Decimal(close),
                volume=Decimal("100"),
                is_adjusted=True,
            )
        )
    # A provider W1 row owns the first calendar week and must not be replaced.
    db.add(
        OHLCVBar(
            instrument_id=instrument.id,
            timeframe=Timeframe.W1,
            ts=datetime(2025, 1, 2, tzinfo=UTC),
            open=Decimal("9"),
            high=Decimal("99"),
            low=Decimal("8"),
            close=Decimal("90"),
            volume=Decimal("200"),
            is_adjusted=True,
            is_derived=False,
        )
    )
    db.flush()

    result = await materialize_derived_timeframes(AsyncSessionAdapter(db), instrument.id)
    assert result == {"W1": 2, "MN": 1}

    weekly = (
        db.execute(
            select(OHLCVBar)
            .where(OHLCVBar.instrument_id == instrument.id, OHLCVBar.timeframe == Timeframe.W1)
            .order_by(OHLCVBar.ts)
        )
        .scalars()
        .all()
    )
    assert len(weekly) == 3
    assert weekly[0].is_derived is False
    assert weekly[0].close == Decimal("90")
    assert weekly[1].is_derived is True
    assert weekly[2].is_derived is True
    assert weekly[1].source_timeframe == "D1"
    assert weekly[1].derivation_method == DERIVATION_METHOD
    assert weekly[1].data_source_id is None
    assert weekly[1].source_bar_count == 2
    assert weekly[1].source_start.replace(tzinfo=UTC) == datetime(2025, 1, 2, tzinfo=UTC)
    assert weekly[1].source_end.replace(tzinfo=UTC) == datetime(2025, 1, 3, tzinfo=UTC)
    assert weekly[2].source_start.replace(tzinfo=UTC) == datetime(2025, 1, 9, tzinfo=UTC)
    assert weekly[2].source_end.replace(tzinfo=UTC) == datetime(2025, 1, 10, tzinfo=UTC)

    weekly_state = (
        db.query(InstrumentDatasetState)
        .filter(
            InstrumentDatasetState.instrument_id == instrument.id,
            InstrumentDatasetState.data_source_id.is_(None),
            InstrumentDatasetState.dataset_key == "W1:adj",
        )
        .one()
    )
    assert weekly_state.status.value == "fresh"
    assert weekly_state.version == 1
    assert weekly_state.extra_data == {
        "source_timeframe": "D1",
        "derivation_method": DERIVATION_METHOD,
        "adjusted": True,
        "derived_bar_count": 2,
        "provider_periods_excluded": 0,
        "source_d1_signature": {
            "adjusted": True,
            "bar_count": 4,
            "coverage_start": "2025-01-02T00:00:00+00:00",
            "coverage_end": "2025-01-10T00:00:00+00:00",
            "data_source_ids": [],
            "market_series_ids": [],
            "source_watermarks": [],
        },
        "source_market_series_id": None,
        "adjustment_provenance": {
            "mode": "split_adjusted",
            "source_kind": "derived_from_canonical_d1",
            "factor_status": "inherited_from_canonical_d1",
            "factor_version": None,
            "contract_version": 1,
        },
    }

    monthly = (
        db.execute(
            select(OHLCVBar).where(
                OHLCVBar.instrument_id == instrument.id, OHLCVBar.timeframe == Timeframe.MN
            )
        )
        .scalars()
        .all()
    )
    assert len(monthly) == 1
    assert monthly[0].is_derived is True
    assert monthly[0].source_timeframe == "D1"


@pytest.mark.asyncio
@pytest.mark.parametrize("stored_signature_present", [False, True])
async def test_cached_derived_state_recovers_with_autoflush_disabled_and_inherits_d1_contract(
    db, instrument, stored_signature_present
):
    db.autoflush = False
    source = DataSource(name="derived-autoflush-false-provider")
    db.add(source)
    db.flush()
    daily_series = MarketSeries(
        instrument_id=instrument.id,
        data_source_id=source.id,
        feed_scope="alpaca-iex",
        session_code="regular",
        timeframe=Timeframe.D1.value,
        adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
        adjustment_version="alpaca-split-adjusted",
        is_canonical=True,
        is_active=True,
    )
    db.add(daily_series)
    db.flush()
    db.add(
        MarketSeriesDefault(
            instrument_id=instrument.id,
            timeframe=Timeframe.D1.value,
            is_adjusted=True,
            market_series_id=daily_series.id,
            selection_reason="test-selected-daily-series",
        )
    )

    daily_times = [datetime(2025, 1, day, 21, tzinfo=UTC) for day in (2, 3)]
    for index, timestamp in enumerate(daily_times):
        close = Decimal("100") + index
        db.add(
            OHLCVBar(
                instrument_id=instrument.id,
                data_source_id=source.id,
                market_series_id=daily_series.id,
                timeframe=Timeframe.D1,
                ts=timestamp,
                open=close - 1,
                high=close + 2,
                low=close - 2,
                close=close,
                volume=Decimal("100"),
                is_adjusted=True,
                adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED.value,
                adjustment_version="alpaca-split-adjusted",
                provenance={"provider": "alpaca", "feed": "iex"},
                is_derived=False,
            )
        )
    fetched_at = datetime.now(UTC) - timedelta(minutes=5)
    stale_after = fetched_at + timedelta(minutes=20)
    db.add(
        InstrumentDatasetState(
            instrument_id=instrument.id,
            data_source_id=source.id,
            dataset_type="ohlcv",
            dataset_key="D1:adj",
            status=DatasetStatus.FRESH,
            coverage_start=daily_times[0],
            coverage_end=daily_times[-1],
            observed_at=fetched_at,
            fetched_at=fetched_at,
            stale_after=stale_after,
            version=3,
            extra_data={
                "adjustment_provenance": {
                    "mode": "split_adjusted",
                    "source_kind": "provider_observation",
                    "factor_status": "rebuildable_provider_factors",
                    "factor_version": "alpaca-split-adjusted",
                    "contract_version": 1,
                }
            },
        )
    )
    db.flush()

    source_signature = await _canonical_d1_signature(
        AsyncSessionAdapter(db), instrument.id, adjusted=True
    )
    for timeframe in (Timeframe.W1, Timeframe.MN):
        derived_series = MarketSeries(
            instrument_id=instrument.id,
            data_source_id=source.id,
            feed_scope=f"derived-d1-{daily_series.id}",
            session_code="regular",
            timeframe=timeframe.value,
            adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
            adjustment_version="alpaca-split-adjusted",
            is_canonical=True,
            is_active=True,
            source_series_key=f"derived-from-d1:{daily_series.id}",
        )
        db.add(derived_series)
        db.flush()
        db.add(
            MarketSeriesDefault(
                instrument_id=instrument.id,
                timeframe=timeframe.value,
                is_adjusted=True,
                market_series_id=derived_series.id,
                selection_reason="test-existing-derived-default",
            )
        )
        db.add(
            OHLCVBar(
                instrument_id=instrument.id,
                data_source_id=source.id,
                market_series_id=derived_series.id,
                timeframe=timeframe,
                ts=daily_times[0],
                open=Decimal("99"),
                high=Decimal("103"),
                low=Decimal("98"),
                close=Decimal("100"),
                volume=Decimal("100"),
                is_adjusted=True,
                adjustment_basis=AdjustmentBasis.RAW.value,
                adjustment_version="legacy",
                is_derived=True,
                source_timeframe=Timeframe.D1.value,
                derivation_method=DERIVATION_METHOD,
                source_bar_count=1,
                source_start=daily_times[0],
                source_end=daily_times[0],
                scope_key=f"series:{derived_series.id}:regular",
            )
        )
        db.add(
            InstrumentDatasetState(
                instrument_id=instrument.id,
                data_source_id=None,
                dataset_type="ohlcv",
                dataset_key=f"{timeframe.value}:adj",
                status=DatasetStatus.PENDING,
                coverage_start=None,
                coverage_end=None,
                extra_data={
                    "source_d1_signature": (source_signature if stored_signature_present else None),
                    "derived_bar_count": 0,
                },
            )
        )
    db.flush()

    async_db = AsyncSessionAdapter(db)
    assert await derived_timeframe_needs_refresh(
        async_db, instrument.id, Timeframe.W1, adjusted=True
    )
    assert await derived_timeframe_needs_refresh(
        async_db, instrument.id, Timeframe.MN, adjusted=True
    )

    result = await materialize_derived_timeframes(async_db, instrument.id, adjusted=True)
    assert result == {"W1": 1, "MN": 1}
    for timeframe in (Timeframe.W1, Timeframe.MN):
        row = (
            db.query(OHLCVBar)
            .filter(
                OHLCVBar.instrument_id == instrument.id,
                OHLCVBar.timeframe == timeframe,
                OHLCVBar.is_derived.is_(True),
            )
            .one()
        )
        assert row.adjustment_basis == AdjustmentBasis.SPLIT_ADJUSTED.value
        assert row.adjustment_version == "alpaca-split-adjusted"
        assert row.provenance["derivation_method"] == DERIVATION_METHOD
        assert row.provenance["source_data_source_id"] == source.id
        state = (
            db.query(InstrumentDatasetState)
            .filter_by(
                instrument_id=instrument.id,
                data_source_id=None,
                dataset_type="ohlcv",
                dataset_key=f"{timeframe.value}:adj",
            )
            .one()
        )
        assert state.status == DatasetStatus.FRESH
        assert state.extra_data["derived_bar_count"] == 1
        assert state.fetched_at.replace(tzinfo=UTC) == fetched_at
        assert state.stale_after.replace(tzinfo=UTC) == stale_after
        assert state.coverage_start == row.ts
        assert state.coverage_end == row.ts
        assert not await derived_timeframe_needs_refresh(
            async_db, instrument.id, timeframe, adjusted=True
        )


@pytest.mark.asyncio
async def test_materialize_derived_timeframes_inherits_verified_d1_factor_version(db, instrument):
    source = DataSource(name="derived-factor-lineage-provider")
    db.add(source)
    db.flush()
    for day, close in ((2, "10"), (3, "11")):
        db.add(
            OHLCVBar(
                instrument_id=instrument.id,
                data_source_id=source.id,
                timeframe=Timeframe.D1,
                ts=datetime(2025, 1, day, tzinfo=UTC),
                open=Decimal(close) - 1,
                high=Decimal(close) + 2,
                low=Decimal(close) - 2,
                close=Decimal(close),
                volume=Decimal("100"),
                is_adjusted=True,
                is_derived=False,
            )
        )
    db.add(
        InstrumentDatasetState(
            instrument_id=instrument.id,
            data_source_id=source.id,
            dataset_type="ohlcv",
            dataset_key="D1:adj",
            status=DatasetStatus.FRESH,
            version=1,
            extra_data={
                "adjustment_provenance": {
                    "mode": "split_adjusted",
                    "source_kind": "provider_observation",
                    "factor_status": "rebuildable_provider_factors",
                    "factor_version": "afv1-provider-d1",
                    "contract_version": 1,
                }
            },
        )
    )
    db.flush()

    result = await materialize_derived_timeframes(AsyncSessionAdapter(db), instrument.id)

    assert result == {"W1": 1, "MN": 1}
    weekly_state = (
        db.query(InstrumentDatasetState)
        .filter(
            InstrumentDatasetState.instrument_id == instrument.id,
            InstrumentDatasetState.data_source_id.is_(None),
            InstrumentDatasetState.dataset_key == "W1:adj",
        )
        .one()
    )
    assert weekly_state.extra_data["adjustment_provenance"]["factor_status"] == (
        "inherited_from_canonical_d1"
    )
    assert weekly_state.extra_data["adjustment_provenance"]["factor_version"] == (
        "afv1-provider-d1"
    )


@pytest.mark.asyncio
async def test_materialize_derived_timeframes_inherits_local_split_factor_version(db, instrument):
    for day, close in ((2, "10"), (3, "11")):
        db.add(
            OHLCVBar(
                instrument_id=instrument.id,
                data_source_id=None,
                timeframe=Timeframe.D1,
                ts=datetime(2025, 1, day, tzinfo=UTC),
                open=Decimal(close) - 1,
                high=Decimal(close) + 2,
                low=Decimal(close) - 2,
                close=Decimal(close),
                volume=Decimal("100"),
                is_adjusted=True,
                is_derived=True,
                source_timeframe=Timeframe.D1.value,
                derivation_method="local_split_ratio",
            )
        )
    db.add(
        InstrumentDatasetState(
            instrument_id=instrument.id,
            data_source_id=None,
            dataset_type="ohlcv",
            dataset_key="D1:adj:local_split_ratio",
            status=DatasetStatus.FRESH,
            version=1,
            extra_data={
                "adjustment_provenance": {
                    "mode": "split_adjusted",
                    "source_kind": "local_split_ratio",
                    "factor_status": "rebuildable_split_factors",
                    "factor_version": "afv1-local-split",
                    "contract_version": 1,
                }
            },
        )
    )
    db.flush()

    result = await materialize_derived_timeframes(AsyncSessionAdapter(db), instrument.id)

    assert result == {"W1": 1, "MN": 1}
    weekly_state = (
        db.query(InstrumentDatasetState)
        .filter(
            InstrumentDatasetState.instrument_id == instrument.id,
            InstrumentDatasetState.data_source_id.is_(None),
            InstrumentDatasetState.dataset_key == "W1:adj",
        )
        .one()
    )
    assert weekly_state.extra_data["adjustment_provenance"] == {
        "mode": "split_adjusted",
        "source_kind": "derived_from_canonical_d1",
        "factor_status": "inherited_from_canonical_d1",
        "factor_version": "afv1-local-split",
        "contract_version": 1,
    }


@pytest.mark.asyncio
async def test_materialize_derived_timeframes_inherits_local_provider_factor_version(
    db, instrument
):
    for day, close in ((2, "10"), (3, "11")):
        db.add(
            OHLCVBar(
                instrument_id=instrument.id,
                data_source_id=None,
                timeframe=Timeframe.D1,
                ts=datetime(2025, 1, day, tzinfo=UTC),
                open=Decimal(close) - 1,
                high=Decimal(close) + 2,
                low=Decimal(close) - 2,
                close=Decimal(close),
                volume=Decimal("100"),
                is_adjusted=True,
                is_derived=True,
                source_timeframe=Timeframe.D1.value,
                derivation_method="provider_adjustment_factor",
            )
        )
    db.add(
        InstrumentDatasetState(
            instrument_id=instrument.id,
            data_source_id=None,
            dataset_type="ohlcv",
            dataset_key="D1:adj:provider_adjustment_factor",
            status=DatasetStatus.FRESH,
            version=1,
            extra_data={
                "adjustment_provenance": {
                    "mode": "provider_adjusted",
                    "source_kind": "provider_adjustment_factor",
                    "factor_status": "rebuildable_provider_factors",
                    "factor_version": "afv1-provider-local",
                    "contract_version": 1,
                }
            },
        )
    )
    db.flush()

    result = await materialize_derived_timeframes(AsyncSessionAdapter(db), instrument.id)

    assert result == {"W1": 1, "MN": 1}
    weekly_state = (
        db.query(InstrumentDatasetState)
        .filter(
            InstrumentDatasetState.instrument_id == instrument.id,
            InstrumentDatasetState.data_source_id.is_(None),
            InstrumentDatasetState.dataset_key == "W1:adj",
        )
        .one()
    )
    assert weekly_state.extra_data["adjustment_provenance"] == {
        "mode": "split_adjusted",
        "source_kind": "derived_from_canonical_d1",
        "factor_status": "inherited_from_canonical_d1",
        "factor_version": "afv1-provider-local",
        "contract_version": 1,
    }


@pytest.mark.asyncio
async def test_materialize_derived_timeframes_rejects_provider_factor_fetched_after_cutoff(
    db, instrument
):
    source = DataSource(name="historical-provider-factor")
    db.add(source)
    db.flush()
    cutoff = datetime(2025, 1, 3, 23, 59, tzinfo=UTC)
    for day, close in ((2, "10"), (3, "11")):
        db.add(
            OHLCVBar(
                instrument_id=instrument.id,
                data_source_id=source.id,
                timeframe=Timeframe.D1,
                ts=datetime(2025, 1, day, tzinfo=UTC),
                open=Decimal(close) - 1,
                high=Decimal(close) + 2,
                low=Decimal(close) - 2,
                close=Decimal(close),
                volume=Decimal("100"),
                is_adjusted=True,
                is_derived=False,
            )
        )
    db.add(
        InstrumentDatasetState(
            instrument_id=instrument.id,
            data_source_id=source.id,
            dataset_type="ohlcv",
            dataset_key="D1:adj",
            status=DatasetStatus.FRESH,
            version=1,
            coverage_end=cutoff,
            fetched_at=cutoff + timedelta(days=1),
            extra_data={
                "adjustment_provenance": {
                    "factor_status": "rebuildable_provider_factors",
                    "factor_version": "afv1-future-fetch",
                }
            },
        )
    )
    db.flush()

    await materialize_derived_timeframes(AsyncSessionAdapter(db), instrument.id, end=cutoff)

    weekly_state = (
        db.query(InstrumentDatasetState)
        .filter(
            InstrumentDatasetState.instrument_id == instrument.id,
            InstrumentDatasetState.data_source_id.is_(None),
            InstrumentDatasetState.dataset_key == "W1:adj",
        )
        .one()
    )
    assert weekly_state.extra_data["adjustment_provenance"]["factor_version"] is None


@pytest.mark.asyncio
async def test_materialize_derived_timeframes_rejects_local_factor_without_cutoff_fetch_proof(
    db, instrument
):
    cutoff = datetime(2025, 1, 3, 23, 59, tzinfo=UTC)
    for day, close in ((2, "10"), (3, "11")):
        db.add(
            OHLCVBar(
                instrument_id=instrument.id,
                data_source_id=None,
                timeframe=Timeframe.D1,
                ts=datetime(2025, 1, day, tzinfo=UTC),
                open=Decimal(close) - 1,
                high=Decimal(close) + 2,
                low=Decimal(close) - 2,
                close=Decimal(close),
                volume=Decimal("100"),
                is_adjusted=True,
                is_derived=True,
                source_timeframe=Timeframe.D1.value,
                derivation_method="local_split_ratio",
            )
        )
    db.add(
        InstrumentDatasetState(
            instrument_id=instrument.id,
            data_source_id=None,
            dataset_type="ohlcv",
            dataset_key="D1:adj:local_split_ratio",
            status=DatasetStatus.FRESH,
            version=1,
            coverage_end=cutoff,
            fetched_at=None,
            extra_data={
                "adjustment_provenance": {
                    "factor_status": "rebuildable_split_factors",
                    "factor_version": "afv1-missing-fetch",
                }
            },
        )
    )
    db.flush()

    await materialize_derived_timeframes(AsyncSessionAdapter(db), instrument.id, end=cutoff)

    weekly_state = (
        db.query(InstrumentDatasetState)
        .filter(
            InstrumentDatasetState.instrument_id == instrument.id,
            InstrumentDatasetState.data_source_id.is_(None),
            InstrumentDatasetState.dataset_key == "W1:adj",
        )
        .one()
    )
    assert weekly_state.extra_data["adjustment_provenance"]["factor_version"] is None


@pytest.mark.asyncio
async def test_materialize_derived_timeframes_historical_end_preserves_newer_cache(db, instrument):
    for day, close in ((2, "10"), (3, "11")):
        db.add(
            OHLCVBar(
                instrument_id=instrument.id,
                timeframe=Timeframe.D1,
                ts=datetime(2025, 1, day, tzinfo=UTC),
                open=Decimal(close) - 1,
                high=Decimal(close) + 2,
                low=Decimal(close) - 2,
                close=Decimal(close),
                volume=Decimal("100"),
                is_adjusted=True,
            )
        )
    db.add(
        OHLCVBar(
            instrument_id=instrument.id,
            timeframe=Timeframe.D1,
            ts=datetime(2025, 2, 3, tzinfo=UTC),
            open=Decimal("11"),
            high=Decimal("14"),
            low=Decimal("10"),
            close=Decimal("13"),
            volume=Decimal("100"),
            is_adjusted=True,
        )
    )
    db.flush()

    # Seed the normal latest cache first, then rebuild a dated view.  The
    # historical pass must refresh only the January period and retain the
    # newer February derived rows for later unbounded reads.
    await materialize_derived_timeframes(AsyncSessionAdapter(db), instrument.id)
    state_before = (
        db.query(InstrumentDatasetState)
        .filter(
            InstrumentDatasetState.instrument_id == instrument.id,
            InstrumentDatasetState.data_source_id.is_(None),
            InstrumentDatasetState.dataset_key == "W1:adj",
        )
        .one()
    )
    state_version_before = state_before.version
    state_coverage_end_before = state_before.coverage_end
    result = await materialize_derived_timeframes(
        AsyncSessionAdapter(db),
        instrument.id,
        end=datetime(2025, 1, 31, 23, 59, tzinfo=UTC),
    )

    assert result == {"W1": 1, "MN": 1}
    weekly = (
        db.query(OHLCVBar)
        .filter(
            OHLCVBar.instrument_id == instrument.id,
            OHLCVBar.timeframe == Timeframe.W1,
            OHLCVBar.is_derived.is_(True),
        )
        .order_by(OHLCVBar.ts)
        .all()
    )
    assert [row.ts.replace(tzinfo=UTC) for row in weekly] == [
        datetime(2025, 1, 2, tzinfo=UTC),
        datetime(2025, 2, 3, tzinfo=UTC),
    ]
    state_after = (
        db.query(InstrumentDatasetState)
        .filter(
            InstrumentDatasetState.instrument_id == instrument.id,
            InstrumentDatasetState.data_source_id.is_(None),
            InstrumentDatasetState.dataset_key == "W1:adj",
        )
        .one()
    )
    assert state_after.version == state_version_before
    assert state_after.coverage_end == state_coverage_end_before
    monthly = (
        db.query(OHLCVBar)
        .filter(
            OHLCVBar.instrument_id == instrument.id,
            OHLCVBar.timeframe == Timeframe.MN,
            OHLCVBar.is_derived.is_(True),
        )
        .order_by(OHLCVBar.ts)
        .all()
    )
    assert [row.ts.replace(tzinfo=UTC) for row in monthly] == [
        datetime(2025, 1, 2, tzinfo=UTC),
        datetime(2025, 2, 3, tzinfo=UTC),
    ]


@pytest.mark.asyncio
async def test_historical_derivation_does_not_let_future_provider_period_hide_visible_period(
    db, instrument
):
    """A provider row after the cutoff cannot suppress the same historical period."""

    source = DataSource(name="future-coarse-provider")
    db.add(source)
    db.flush()
    for day, close in ((2, "10"), (3, "11")):
        db.add(
            OHLCVBar(
                instrument_id=instrument.id,
                timeframe=Timeframe.D1,
                ts=datetime(2025, 1, day, tzinfo=UTC),
                open=Decimal(close) - 1,
                high=Decimal(close) + 2,
                low=Decimal(close) - 2,
                close=Decimal(close),
                volume=Decimal("100"),
                is_adjusted=True,
            )
        )
    # Jan 5 is in the same ISO week as the visible Jan 2/3 D1 bars, but it is
    # after the historical cutoff and must not own that period yet.
    db.add(
        OHLCVBar(
            instrument_id=instrument.id,
            data_source_id=source.id,
            timeframe=Timeframe.W1,
            ts=datetime(2025, 1, 5, 21, tzinfo=UTC),
            open=Decimal("9"),
            high=Decimal("12"),
            low=Decimal("8"),
            close=Decimal("11"),
            volume=Decimal("200"),
            is_adjusted=True,
            is_derived=False,
        )
    )
    db.flush()

    await materialize_derived_timeframes(
        AsyncSessionAdapter(db),
        instrument.id,
        end=datetime(2025, 1, 3, 23, 59, tzinfo=UTC),
    )

    weekly = (
        db.query(OHLCVBar)
        .filter(
            OHLCVBar.instrument_id == instrument.id,
            OHLCVBar.timeframe == Timeframe.W1,
        )
        .order_by(OHLCVBar.ts)
        .all()
    )
    assert [(row.ts.replace(tzinfo=UTC), row.is_derived) for row in weekly] == [
        (datetime(2025, 1, 2, tzinfo=UTC), True),
        (datetime(2025, 1, 5, 21, tzinfo=UTC), False),
    ]
