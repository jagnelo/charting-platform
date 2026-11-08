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
from app.models.market_data_foundation import MarketRefreshJob
from app.models.provider_observation import DatasetStatus, InstrumentDatasetState
from app.models.provider_runtime import ProviderCapability
from app.providers.base import InstrumentEventPage, InstrumentEventRecord
from app.providers.errors import ProviderRateLimitError, ProviderResponseError
from app.services import instrument_events
from app.services.instrument_events import (
    EVENT_FETCH_VERSION,
    enqueue_instrument_events_refresh,
    ensure_instrument_events_loaded,
    fetch_and_store_instrument_events,
    instrument_events_refresh_status,
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
async def test_stale_calendar_refresh_requeues_one_completed_durable_job(db, instrument):
    async_db = AsyncSessionAdapter(db)
    first_now = datetime(2026, 11, 8, 12, tzinfo=UTC)

    assert await enqueue_instrument_events_refresh(async_db, instrument, now=first_now)
    first = db.query(MarketRefreshJob).one()
    first_id = first.id
    first.status = "completed"
    first.attempts = 3
    first.finished_at = first_now
    first.result_summary = {"preparation_status": "unavailable"}
    db.flush()

    assert not await enqueue_instrument_events_refresh(
        async_db,
        instrument,
        now=first_now + timedelta(minutes=1),
    )

    assert await enqueue_instrument_events_refresh(
        async_db,
        instrument,
        refresh=True,
        now=first_now + timedelta(minutes=2),
    )

    db.expire_all()
    requeued = db.query(MarketRefreshJob).one()
    assert requeued.id == first_id
    assert requeued.status == "queued"
    assert requeued.attempts == 3
    assert requeued.finished_at is None
    assert requeued.result_summary is None


@pytest.mark.asyncio
async def test_manual_calendar_refresh_preserves_a_live_provider_deadline(db, instrument):
    async_db = AsyncSessionAdapter(db)
    now = datetime(2026, 11, 8, 12, tzinfo=UTC)
    retry_at = now + timedelta(minutes=8)

    await enqueue_instrument_events_refresh(async_db, instrument, now=now)
    job = db.query(MarketRefreshJob).one()
    job.status = "deferred"
    # Simulate the naive timestamp returned by SQLite for a timezone-aware
    # PostgreSQL DateTime column; the comparison still uses canonical UTC.
    job.next_attempt_at = retry_at.replace(tzinfo=None)
    job.result_summary = {
        "outcome": "deferred",
        "preparation_status": "held",
        "reason_code": "native_quota_wait",
        "retry_at": retry_at.isoformat(),
    }
    job.metadata_payload = {**job.metadata_payload, "defer_reason": "provider_reset"}
    db.flush()

    assert not await enqueue_instrument_events_refresh(
        async_db,
        instrument,
        now=now + timedelta(minutes=1),
    )
    await enqueue_instrument_events_refresh(
        async_db,
        instrument,
        refresh=True,
        now=now + timedelta(minutes=1),
    )

    assert job.status == "deferred"
    assert job.next_attempt_at.replace(tzinfo=UTC) == retry_at
    status = await instrument_events_refresh_status(
        async_db,
        instrument,
        now=now + timedelta(minutes=1),
    )
    assert status["status"] == "deferred"
    assert status["has_pending_work"] is True
    assert status["retry_at"] == retry_at
    assert status["reason_code"] == "provider_reset"
    assert status["updated_at"] is not None


@pytest.mark.asyncio
async def test_calendar_status_reports_explicit_refresh_while_fresh_cache_exists(db, instrument):
    async_db = AsyncSessionAdapter(db)
    now = datetime(2026, 11, 8, 12, tzinfo=UTC)
    db.add(
        InstrumentDatasetState(
            instrument_id=instrument.id,
            data_source_id=None,
            dataset_type="events",
            dataset_key="calendar",
            status=DatasetStatus.FRESH,
            fetched_at=now,
            observed_at=now,
            stale_after=now + timedelta(hours=1),
        )
    )
    db.flush()

    assert await enqueue_instrument_events_refresh(
        async_db,
        instrument,
        refresh=True,
        now=now,
    )
    queued = await instrument_events_refresh_status(async_db, instrument, now=now)
    assert queued["status"] == "queued"
    assert queued["has_pending_work"] is True
    assert queued["retry_at"] == now

    job = db.query(MarketRefreshJob).one()
    job.status = "completed"
    job.finished_at = now + timedelta(seconds=5)
    job.result_summary = {"preparation_status": "ready"}
    db.flush()
    ready = await instrument_events_refresh_status(
        async_db,
        instrument,
        now=now + timedelta(seconds=6),
    )
    assert ready["status"] == "ready"
    assert ready["has_pending_work"] is False
    assert ready["updated_at"] == now


@pytest.mark.asyncio
async def test_fresh_other_provider_does_not_hide_calendar_continuation(db, instrument):
    async_db = AsyncSessionAdapter(db)
    now = datetime(2026, 11, 8, 12, tzinfo=UTC)
    source = DataSource(name="edgar", is_active=True)
    db.add(source)
    db.flush()
    db.add_all(
        [
            InstrumentDatasetState(
                instrument_id=instrument.id,
                data_source_id=source.id,
                dataset_type="events",
                dataset_key="calendar",
                status=DatasetStatus.FRESH,
                fetched_at=now - timedelta(minutes=2),
                observed_at=now - timedelta(minutes=2),
                stale_after=now + timedelta(hours=1),
            ),
            InstrumentEventFetchState(
                instrument_id=instrument.id,
                source="alpaca",
                fetched_at=now - timedelta(minutes=1),
                fetch_version=EVENT_FETCH_VERSION,
                continuation_token="page-2",
                query_fingerprint="query-fingerprint",
                page_count=1,
                complete=False,
            ),
        ]
    )
    db.flush()
    state = db.query(InstrumentEventFetchState).one()
    request_key = instrument_events.instrument_events_refresh_request_key(
        instrument.id,
        state,
    )
    job = MarketRefreshJob(
        request_key=request_key,
        instrument_id=instrument.id,
        capability=ProviderCapability.INSTRUMENT_EVENTS.value,
        priority=10,
        status="queued",
        attempts=0,
        next_attempt_at=now,
        metadata_payload={},
    )
    db.add(job)
    db.flush()

    queued = await instrument_events_refresh_status(async_db, instrument, now=now)
    assert queued["status"] == "queued"
    assert queued["has_pending_work"] is True
    assert queued["updated_at"] is not None

    job.status = "completed"
    job.finished_at = now + timedelta(seconds=10)
    job.result_summary = {
        "preparation_status": "partial",
        "reason_code": "event_page_incomplete",
    }
    state.continuation_token = None
    db.flush()
    partial = await instrument_events_refresh_status(
        async_db,
        instrument,
        now=now + timedelta(seconds=11),
    )
    assert partial["status"] == "partial"
    assert partial["has_pending_work"] is False
    assert partial["reason_code"] == "event_page_incomplete"


@pytest.mark.asyncio
async def test_alpaca_corporate_actions_charge_one_durable_page(db, instrument, monkeypatch):
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
            raw_payload={
                "corporate_actions": {"cash_dividends": [{"id": "one"}]},
                "next_page_token": "page-2",
            },
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


@pytest.mark.asyncio
async def test_empty_successful_event_page_is_retained_as_raw_evidence(db, instrument, monkeypatch):
    """An empty provider envelope is still a successful, quota-consuming read."""

    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="alpaca", is_active=True)
    db.add(source)
    db.flush()

    class _Provider:
        name = "alpaca"

        def fetch_instrument_events_page(self, _symbol, page_token=None, **_kwargs):
            return InstrumentEventPage(
                events=[],
                next_page_token=None,
                request_page_token=page_token,
                raw_payload={},
            )

    async def _execute(_db, _capability, _operation, **kwargs):
        return ProviderExecutionResult(
            provider_name="alpaca",
            data_source=source,
            policy=object(),
            health=object(),
            result=kwargs["invoke"](_Provider(), "AAPL"),
        )

    monkeypatch.setattr(instrument_events, "execute_provider_call", _execute)

    await fetch_and_store_instrument_events(async_db, instrument)

    snapshot = db.query(InstrumentEventPageSnapshot).one()
    assert snapshot.payload == {}
