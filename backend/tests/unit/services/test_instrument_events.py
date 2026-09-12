from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.adjustment_factor import AdjustmentFactorObservation
from app.models.data_source import DataSource
from app.models.instrument_event import (
    EventTimeHint,
    InstrumentEvent,
    InstrumentEventFetchState,
    InstrumentEventType,
)
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_observation import DatasetStatus, InstrumentDatasetState
from app.providers.base import InstrumentEventRecord
from app.services.instrument_events import (
    EVENT_FETCH_VERSION,
    _materialize_provider_adjusted_views,
    ensure_instrument_events_loaded,
    query_instrument_events,
)
from tests.unit.conftest import AsyncSessionAdapter


@pytest.mark.asyncio
async def test_ensure_instrument_events_loaded_handles_multiple_provider_states(
    db, instrument, monkeypatch
):
    async_db = AsyncSessionAdapter(db)
    now = datetime.now(UTC)
    db.add_all(
        [
            InstrumentEventFetchState(
                instrument_id=instrument.id,
                source="yfinance",
                fetched_at=now - timedelta(days=2),
                event_count=1,
                earnings_count=1,
                fetch_version=EVENT_FETCH_VERSION - 1,
            ),
            InstrumentEventFetchState(
                instrument_id=instrument.id,
                source="edgar",
                fetched_at=now - timedelta(days=1),
                event_count=2,
                earnings_count=2,
                fetch_version=EVENT_FETCH_VERSION,
            ),
            InstrumentDatasetState(
                instrument_id=instrument.id,
                data_source_id=None,
                dataset_type="events",
                dataset_key="calendar",
                status=DatasetStatus.FRESH,
                observed_at=now - timedelta(hours=1),
                fetched_at=now - timedelta(hours=1),
                stale_after=now + timedelta(hours=12),
            ),
        ]
    )
    db.commit()

    called = False

    async def _unexpected_fetch(*_args, **_kwargs):
        nonlocal called
        called = True
        return 0

    monkeypatch.setattr(
        "app.services.instrument_events.fetch_and_store_instrument_events", _unexpected_fetch
    )

    await ensure_instrument_events_loaded(async_db, instrument)

    assert called is False


@pytest.mark.asyncio
async def test_query_instrument_events_normalizes_offset_aware_range(db, instrument):
    async_db = AsyncSessionAdapter(db)
    db.add_all(
        [
            InstrumentEvent(
                instrument_id=instrument.id,
                event_type=InstrumentEventType.EARNINGS,
                event_time=datetime(2026, 1, 1, tzinfo=UTC),
                time_hint=EventTimeHint.UNKNOWN,
                title="Q1 earnings",
                source="test",
                source_event_key="q1",
                fetched_at=datetime(2026, 1, 2, tzinfo=UTC),
            ),
            InstrumentEvent(
                instrument_id=instrument.id,
                event_type=InstrumentEventType.DIVIDEND,
                event_time=datetime(2026, 1, 2, tzinfo=UTC),
                time_hint=EventTimeHint.UNKNOWN,
                title="Dividend",
                source="test",
                source_event_key="dividend",
                fetched_at=datetime(2026, 1, 3, tzinfo=UTC),
            ),
        ]
    )
    db.commit()

    events = await query_instrument_events(
        async_db,
        instrument,
        start=datetime.fromisoformat("2026-01-01T02:00:00+02:00"),
        end=datetime.fromisoformat("2026-01-02T02:00:00+02:00"),
    )

    assert [event.source_event_key for event in events] == ["dividend", "q1"]


@pytest.mark.asyncio
async def test_event_refresh_materializes_explicit_provider_factor_for_cached_raw_bars(
    db, instrument
):
    """A factor-bearing event refresh completes the local adjusted view."""

    source = DataSource(name="provider-factor-events")
    db.add(source)
    db.flush()
    before = datetime(2024, 6, 7, 21, tzinfo=UTC)
    after = datetime(2024, 6, 10, 21, tzinfo=UTC)
    db.add_all(
        [
            OHLCVBar(
                instrument_id=instrument.id,
                data_source_id=source.id,
                timeframe=Timeframe.D1,
                ts=before,
                open=Decimal("99"),
                high=Decimal("101"),
                low=Decimal("98"),
                close=Decimal("100"),
                volume=Decimal("100"),
                is_adjusted=False,
                is_derived=False,
            ),
            OHLCVBar(
                instrument_id=instrument.id,
                data_source_id=source.id,
                timeframe=Timeframe.D1,
                ts=after,
                open=Decimal("99"),
                high=Decimal("101"),
                low=Decimal("98"),
                close=Decimal("100"),
                volume=Decimal("100"),
                is_adjusted=False,
                is_derived=False,
            ),
        ]
    )
    db.flush()
    event = InstrumentEventRecord(
        event_type=InstrumentEventType.DIVIDEND,
        event_time=after,
        time_hint=EventTimeHint.UNKNOWN,
        title="Provider dividend",
        source_event_key="dividend:provider-factor-events",
        fetched_at=datetime(2024, 6, 11, tzinfo=UTC),
        dividend_amount=Decimal("0.25"),
        adjustment_factor=Decimal("0.9975"),
    )

    db.add(
        AdjustmentFactorObservation(
            instrument_id=instrument.id,
            data_source_id=source.id,
            factor_type=InstrumentEventType.DIVIDEND.value,
            effective_at=after,
            factor=Decimal("0.9975"),
            factor_kind="provider_supplied",
            amount=Decimal("0.25"),
            source_event_key=event.source_event_key,
            observed_at=event.fetched_at,
            factor_version="afv1-provider-factor-events",
        )
    )
    db.flush()

    await _materialize_provider_adjusted_views(AsyncSessionAdapter(db), instrument, [event])

    derived = (
        db.query(OHLCVBar)
        .filter(
            OHLCVBar.instrument_id == instrument.id,
            OHLCVBar.timeframe == Timeframe.D1,
            OHLCVBar.is_adjusted.is_(True),
            OHLCVBar.is_derived.is_(True),
        )
        .order_by(OHLCVBar.ts)
        .all()
    )
    assert len(derived) == 2
    assert derived[0].close == Decimal("99.75000000")
    assert derived[0].derivation_method == "provider_adjustment_factor"
    assert derived[1].close == Decimal("100.00000000")
