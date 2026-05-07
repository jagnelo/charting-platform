from datetime import UTC, datetime, timedelta

import pytest

from app.models.instrument_event import InstrumentEventFetchState
from app.models.provider_observation import DatasetStatus, InstrumentDatasetState
from app.services.instrument_events import EVENT_FETCH_VERSION, ensure_instrument_events_loaded
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
