from datetime import UTC, datetime, timedelta

import pytest

from app.models.data_source import DataSource
from app.models.instrument_event import (
    EventTimeHint,
    InstrumentEvent,
    InstrumentEventFetchState,
    InstrumentEventPageSnapshot,
    InstrumentEventType,
)
from app.models.provider_observation import DatasetStatus, InstrumentDatasetState
from app.providers.base import InstrumentEventPage, InstrumentEventRecord
from app.providers.errors import ProviderRateLimitError, ProviderResponseError
from app.services import instrument_events
from app.services.instrument_events import (
    EVENT_FETCH_VERSION,
    ensure_instrument_events_loaded,
    fetch_and_store_instrument_events,
)
from app.services.provider_runtime import (
    ProviderExecutionResult,
    ProviderNoDataError,
    ProviderQuotaUnknownError,
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
async def test_ensure_instrument_events_loaded_degrades_when_no_provider_is_routable(
    db, instrument, monkeypatch
):
    async_db = AsyncSessionAdapter(db)

    async def _no_provider(*_args, **_kwargs):
        raise ProviderNoDataError("no reviewed provider is routable")

    monkeypatch.setattr(
        "app.services.instrument_events.fetch_and_store_instrument_events", _no_provider
    )

    await ensure_instrument_events_loaded(async_db, instrument)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_error",
    [
        ProviderResponseError("edgar", "provider unavailable"),
        ProviderRateLimitError("edgar", "rate limited"),
        ProviderQuotaUnknownError("provider operation charge is unknown"),
    ],
)
async def test_ensure_instrument_events_loaded_serves_cache_on_provider_failure(
    db, instrument, monkeypatch, provider_error
):
    async_db = AsyncSessionAdapter(db)

    async def _failed_fetch(*_args, **_kwargs):
        raise provider_error

    monkeypatch.setattr(
        "app.services.instrument_events.fetch_and_store_instrument_events", _failed_fetch
    )

    await ensure_instrument_events_loaded(async_db, instrument)


@pytest.mark.asyncio
async def test_alpaca_corporate_actions_charge_one_durable_page(
    db, instrument, monkeypatch
):
    async_db = AsyncSessionAdapter(db)
    captured = {}

    async def _no_provider(*_args, **kwargs):
        captured.update(kwargs)
        raise ProviderNoDataError("no reviewed provider is routable")

    monkeypatch.setattr(instrument_events, "execute_provider_call", _no_provider)
    monkeypatch.setattr(instrument_events.settings, "ALPACA_CORPORATE_ACTIONS_MAX_PAGES", 3)

    with pytest.raises(ProviderNoDataError):
        await fetch_and_store_instrument_events(async_db, instrument)

    assert captured["operation_cost_overrides"] == {"alpaca": 1}


@pytest.mark.asyncio
async def test_event_refresh_does_not_use_local_page_limits_as_quota_costs(
    db, instrument, monkeypatch
):
    async_db = AsyncSessionAdapter(db)
    captured = {}

    async def _no_provider(*_args, **kwargs):
        captured.update(kwargs)
        raise ProviderNoDataError("no reviewed provider is routable")

    monkeypatch.setattr(instrument_events, "execute_provider_call", _no_provider)
    monkeypatch.setattr(instrument_events.settings, "MASSIVE_CORPORATE_ACTIONS_MAX_PAGES", 3)

    with pytest.raises(ProviderNoDataError):
        await fetch_and_store_instrument_events(async_db, instrument)

    assert captured["operation_cost_overrides"] == {"alpaca": 1}


@pytest.mark.asyncio
async def test_event_pages_are_persisted_and_resumed_without_refetching_page_one(
    db, instrument, monkeypatch
):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="alpaca", is_active=True)
    db.add(source)
    db.flush()
    calls: list[str | None] = []
    fetched = datetime.now(UTC)

    def _event(key: str) -> InstrumentEventRecord:
        return InstrumentEventRecord(
            event_type=InstrumentEventType.DIVIDEND,
            event_time=datetime(2025, 1, 1, tzinfo=UTC),
            time_hint=EventTimeHint.UNKNOWN,
            title=key,
            source_event_key=key,
            fetched_at=fetched,
            dividend_amount=1,
            raw_payload=f'{{"id": "{key}"}}',
        )

    pages = {
        None: InstrumentEventPage(
            events=[_event("one")],
            next_page_token="page-2",
            request_page_token=None,
            raw_payload={"corporate_actions": {"cash_dividends": [{"id": "one"}]}, "next_page_token": "page-2"},
        ),
        "page-2": InstrumentEventPage(
            events=[_event("two")],
            next_page_token=None,
            request_page_token="page-2",
            raw_payload={"corporate_actions": {"cash_dividends": [{"id": "two"}]}},
        ),
    }

    class _Provider:
        name = "alpaca"

        def fetch_instrument_events_page(self, symbol, page_token=None, **_kwargs):
            calls.append(page_token)
            return pages[page_token]

    provider = _Provider()

    async def _execute(_db, _capability, _operation, **kwargs):
        page = kwargs["invoke"](provider, "AAPL")
        return ProviderExecutionResult(
            provider_name="alpaca",
            data_source=source,
            policy=object(),
            health=object(),
            result=page,
        )

    monkeypatch.setattr(instrument_events, "execute_provider_call", _execute)

    await fetch_and_store_instrument_events(async_db, instrument)
    state = db.query(InstrumentEventFetchState).one()
    assert state.complete is False
    assert state.continuation_token == "page-2"
    assert state.page_count == 1
    assert db.query(InstrumentEventPageSnapshot).count() == 1

    await fetch_and_store_instrument_events(async_db, instrument)
    db.expire_all()
    state = db.query(InstrumentEventFetchState).one()
    assert state.complete is True
    assert state.continuation_token is None
    assert state.page_count == 2
    assert db.query(InstrumentEvent).count() == 2
    assert db.query(InstrumentEventPageSnapshot).count() == 2
    assert calls == [None, "page-2"]

    # A later refresh of the same query is a new raw observation, not a
    # replacement that may erase the earlier page envelope.
    await fetch_and_store_instrument_events(async_db, instrument)
    assert db.query(InstrumentEventPageSnapshot).count() == 3
    assert calls == [None, "page-2", None]
