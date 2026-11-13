from datetime import UTC, date, datetime, timedelta

from app.models.instrument_event import EventTimeHint, InstrumentEvent, InstrumentEventType
from app.models.market_data_foundation import MarketEvent
from app.models.provider_observation import DatasetStatus, InstrumentDatasetState


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

    async def _unexpected_identity_enrichment(*_args, **_kwargs):
        raise AssertionError("a calendar cache read must not request stable identifiers")

    # The identity helper now lives in instrument_mastering and is re-exported by
    # instrument_sync; guard both so any read-path enrichment is caught.
    monkeypatch.setattr(
        "app.services.instrument_mastering.ensure_external_identifier",
        _unexpected_identity_enrichment,
    )
    monkeypatch.setattr(
        "app.services.instrument_sync.ensure_external_identifier",
        _unexpected_identity_enrichment,
    )

    response = client.get(
        f"/api/v1/calendar/instruments/{instrument.symbol}/calendar",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert [event["title"] for event in response.json()] == ["Retained earnings event"]
