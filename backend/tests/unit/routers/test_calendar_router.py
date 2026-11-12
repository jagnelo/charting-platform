from datetime import UTC, date, datetime, timedelta

from app.models.instrument_event import EventTimeHint, InstrumentEvent, InstrumentEventType
from app.models.market_data_foundation import MarketEvent, MarketRefreshJob
from app.models.provider_observation import DatasetStatus, InstrumentDatasetState
from app.models.provider_runtime import ProviderCapability


def test_market_events_calendar_read_is_authenticated_and_database_only(
    client, auth_headers, db, instrument
):
    db.add_all(
        [
            MarketEvent(
                event_type="earnings",
                event_key="calendar:earnings:aapl:2026-09-15",
                event_time=datetime(2026, 9, 15, 20, 0, tzinfo=UTC),
                effective_date=date(2026, 9, 15),
                source="alpha_vantage",
                source_version="EARNINGS_CALENDAR:3month",
                instrument_id=instrument.id,
                payload={"symbol": instrument.symbol, "name": "Example issuer"},
                is_provisional=True,
            ),
            MarketEvent(
                event_type="earnings",
                event_key="calendar:earnings:unlinked:2026-10-01",
                event_time=None,
                effective_date=date(2026, 10, 1),
                source="fmp",
                payload={"symbol": "UNLINKED", "title": "FMP earnings"},
            ),
        ]
    )
    db.flush()

    assert client.get("/api/v1/calendar/market-events").status_code == 401

    response = client.get(
        "/api/v1/calendar/market-events",
        params={
            "start": "2026-09-15",
            "end": "2026-09-15",
            "event_type": "EARNINGS",
            "source": "ALPHA_VANTAGE",
            "instrument_id": instrument.id,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["event_key"] == "calendar:earnings:aapl:2026-09-15"
    assert body[0]["title"] == "Example issuer"
    assert body[0]["is_provisional"] is True
    assert body[0]["instrument_id"] == instrument.id


def test_market_events_calendar_keeps_timestamp_only_events_and_rejects_reversed_range(
    client, auth_headers, db
):
    db.add(
        MarketEvent(
            event_type="exchange_holiday",
            event_key="calendar:holiday:2026-09-20",
            event_time=datetime(2026, 9, 20, 0, 0, tzinfo=UTC),
            effective_date=None,
            source="exchange",
            payload={"title": "Exchange holiday"},
        )
    )
    db.flush()

    reversed_response = client.get(
        "/api/v1/calendar/market-events",
        params={"start": "2026-09-21", "end": "2026-09-20"},
        headers=auth_headers,
    )
    assert reversed_response.status_code == 422

    response = client.get(
        "/api/v1/calendar/market-events",
        params={"start": "2026-09-20", "end": "2026-09-20"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()[0]["title"] == "Exchange holiday"


def test_instrument_calendar_reads_do_not_create_unknown_instruments(
    client, auth_headers, monkeypatch
):
    async def _unexpected_instrument_creation(*_args, **_kwargs):
        raise AssertionError("calendar reads must not perform provider discovery")

    monkeypatch.setattr(
        "app.routers.instruments._create_from_provider",
        _unexpected_instrument_creation,
    )

    response = client.get(
        "/api/v1/calendar/instruments/UNCACHED-CALENDAR/calendar",
        headers=auth_headers,
    )

    assert response.status_code == 404


def test_cached_instrument_calendar_does_not_enrich_identity_on_read(
    client, auth_headers, db, instrument, monkeypatch
):
    now = datetime.now(UTC)
    db.add_all(
        [
            InstrumentEvent(
                instrument_id=instrument.id,
                event_type=InstrumentEventType.EARNINGS,
                event_time=now,
                time_hint=EventTimeHint.UNKNOWN,
                title="Retained earnings event",
                source="alpha_vantage",
                source_event_key="calendar:earnings:cached",
                fetched_at=now,
            ),
            InstrumentDatasetState(
                instrument_id=instrument.id,
                data_source_id=None,
                dataset_type="events",
                dataset_key="calendar",
                status=DatasetStatus.FRESH,
                observed_at=now,
                fetched_at=now,
                stale_after=now + timedelta(hours=1),
            ),
        ]
    )
    db.flush()

    async def _unexpected_provider_fetch(*_args, **_kwargs):
        raise AssertionError("a calendar cache read must not wait for provider work")

    monkeypatch.setattr(
        "app.services.instrument_events.fetch_and_store_instrument_events",
        _unexpected_provider_fetch,
    )

    response = client.get(
        f"/api/v1/calendar/instruments/{instrument.symbol}/calendar",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert [event["title"] for event in response.json()] == ["Retained earnings event"]
    status = client.get(
        f"/api/v1/calendar/instruments/{instrument.symbol}/calendar/status",
        headers=auth_headers,
    )
    assert status.status_code == 200
    assert status.json()["version"] == 1
    assert status.json()["status"] == "ready"
    assert status.json()["has_pending_work"] is False
    assert status.json()["retry_at"] is None
    assert status.json()["reason_code"] is None
    assert status.json()["updated_at"] is not None


def test_calendar_cache_miss_returns_cached_rows_and_queues_durable_refresh(
    client, auth_headers, db, instrument, monkeypatch
):
    now = datetime.now(UTC)
    db.add(
        InstrumentEvent(
            instrument_id=instrument.id,
            event_type=InstrumentEventType.EARNINGS,
            event_time=now,
            time_hint=EventTimeHint.UNKNOWN,
            title="Retained calendar event",
            source="edgar",
            source_event_key="calendar:earnings:retained",
            fetched_at=now,
        )
    )
    db.flush()

    async def _unexpected_inline_fetch(*_args, **_kwargs):
        raise AssertionError("a calendar GET must not wait for provider work")

    monkeypatch.setattr(
        "app.services.instrument_events.fetch_and_store_instrument_events",
        _unexpected_inline_fetch,
    )
    wakes = []

    async def _wake():
        wakes.append(True)

    monkeypatch.setattr("app.routers.calendar._wake_refresh_worker", _wake)

    response = client.get(
        f"/api/v1/calendar/instruments/{instrument.symbol}/calendar",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert [event["title"] for event in response.json()] == ["Retained calendar event"]
    job = (
        db.query(MarketRefreshJob)
        .filter(
            MarketRefreshJob.capability == ProviderCapability.INSTRUMENT_EVENTS.value,
            MarketRefreshJob.instrument_id == instrument.id,
        )
        .one()
    )
    assert job.status == "queued"
    assert job.priority == 10
    assert job.metadata_payload["instrument_event_refresh"]["instrument_id"] == instrument.id
    assert wakes == [True]
    status = client.get(
        f"/api/v1/calendar/instruments/{instrument.symbol}/calendar/status",
        headers=auth_headers,
    )
    assert status.status_code == 200
    assert status.json()["status"] == "queued"
    assert status.json()["has_pending_work"] is True
    assert status.json()["updated_at"] is not None

    job.status = "completed"
    job.result_summary = {
        "outcome": "completed",
        "preparation_status": "unavailable",
        "reason_code": "event_source_unavailable",
    }
    db.flush()
    held_status = client.get(
        f"/api/v1/calendar/instruments/{instrument.symbol}/calendar/status",
        headers=auth_headers,
    )
    assert held_status.status_code == 200
    assert held_status.json()["status"] == "unavailable"
    assert held_status.json()["has_pending_work"] is False
    assert held_status.json()["reason_code"] == "event_source_unavailable"
    assert held_status.json()["updated_at"] is not None

    repeated = client.get(
        f"/api/v1/calendar/instruments/{instrument.symbol}/calendar",
        headers=auth_headers,
    )
    assert repeated.status_code == 200
    assert [event["title"] for event in repeated.json()] == ["Retained calendar event"]
    db.expire_all()
    assert db.query(MarketRefreshJob).filter_by(instrument_id=instrument.id).one().status == (
        "completed"
    )


def test_empty_calendar_cache_is_reported_as_pending_not_confirmed_empty(
    client, auth_headers, db, instrument, monkeypatch
):
    async def _wake():
        return None

    monkeypatch.setattr("app.routers.calendar._wake_refresh_worker", _wake)

    response = client.get(
        f"/api/v1/calendar/instruments/{instrument.symbol}/calendar",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == []
    status = client.get(
        f"/api/v1/calendar/instruments/{instrument.symbol}/calendar/status",
        headers=auth_headers,
    )
    assert status.status_code == 200
    assert status.json()["status"] == "queued"
    assert status.json()["has_pending_work"] is True
