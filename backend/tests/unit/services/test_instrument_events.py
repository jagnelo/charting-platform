from datetime import UTC, datetime, timedelta

import pytest

from app.models.instrument_event import (
    EventTimeHint,
    InstrumentEvent,
    InstrumentEventFetchState,
    InstrumentEventType,
)
from app.models.provider_observation import DatasetStatus, InstrumentDatasetState
from app.services.instrument_events import (
    EVENT_FETCH_VERSION,
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
