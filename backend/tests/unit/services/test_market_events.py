from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.config import settings
from app.models.data_source import DataSource
from app.models.instrument import Instrument
from app.models.instrument_identity import InstrumentProviderSymbol
from app.models.market_data_foundation import Issuer, MarketEvent
from app.models.provider_runtime import ProviderCapability
from app.providers.base import MarketEventRecord
from app.services import market_events
from app.tasks import data_tasks
from tests.unit.conftest import AsyncSessionAdapter


def _record(*, event_key: str, payload: dict) -> MarketEventRecord:
    return MarketEventRecord(
        event_type="ipo",
        event_key=event_key,
        event_time=datetime(2026, 9, 12, tzinfo=UTC),
        effective_date=date(2026, 9, 12),
        title="Example event",
        source_version="fixture-v1",
        is_provisional=True,
        raw_payload=payload,
    )


@pytest.mark.asyncio
async def test_refresh_market_events_persists_and_exactly_links_provider_symbol(
    db, instrument, monkeypatch
):
    source = DataSource(name="massive", base_url="https://api.massive.com")
    db.add(source)
    db.flush()
    db.add(
        InstrumentProviderSymbol(
            instrument_id=instrument.id,
            data_source_id=source.id,
            provider_symbol="AAPL",
            is_active=True,
        )
    )
    db.flush()

    async def fake_execute(_db, capability, operation, **kwargs):
        assert capability is ProviderCapability.MARKET_EVENTS
        assert operation == "fetch_market_events"
        return SimpleNamespace(
            provider_name=kwargs["provider_name"],
            result=[_record(event_key="ipo:aapl:2026-09-12", payload={"ticker": "aapl"})],
        )

    monkeypatch.setattr(market_events, "execute_provider_call", fake_execute)
    result = await market_events.refresh_market_events(
        AsyncSessionAdapter(db), provider_names=["massive"]
    )

    assert result["status"] == "refreshed"
    assert result["events"] == 1
    assert result["persisted"] == 1
    assert result["linked"] == 1
    assert result["unlinked"] == 0
    row = db.execute(select(MarketEvent)).scalar_one()
    assert row.instrument_id == instrument.id
    assert row.source == "massive"
    assert row.payload["ticker"] == "aapl"

    # The provider event key is the durable idempotency boundary.
    second = await market_events.refresh_market_events(
        AsyncSessionAdapter(db), provider_names=["massive"]
    )
    assert second["events"] == 1
    assert len(db.execute(select(MarketEvent)).scalars().all()) == 1


@pytest.mark.asyncio
async def test_refresh_market_events_runs_additional_provider_calendar_operation(
    db, monkeypatch
):
    operations = []

    async def fake_execute(_db, capability, operation, **kwargs):
        assert capability is ProviderCapability.MARKET_EVENTS
        operations.append(operation)
        event_type = "earnings" if operation == "fetch_earnings_calendar" else "ipo"
        return SimpleNamespace(
            provider_name=kwargs["provider_name"],
            result=[
                _record(
                    event_key=f"alpha:{event_type}",
                    payload={"symbol": "AAPL", "event_type": event_type},
                )
            ],
        )

    monkeypatch.setattr(market_events, "execute_provider_call", fake_execute)
    result = await market_events.refresh_market_events(
        AsyncSessionAdapter(db), provider_names=["alpha_vantage"]
    )

    assert operations == ["fetch_market_events", "fetch_earnings_calendar"]
    assert result["status"] == "refreshed"
    assert result["events"] == 2
    assert result["failures"] == 0
    assert len(db.execute(select(MarketEvent)).scalars().all()) == 2


@pytest.mark.asyncio
async def test_refresh_market_events_leaves_ambiguous_symbol_unlinked(
    db, instrument, instrument_type, monkeypatch
):
    duplicate = Instrument(
        symbol="AAPL-ALT",
        name="Alternate Apple listing",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
    )
    source = DataSource(name="massive", base_url="https://api.massive.com")
    db.add_all([duplicate, source])
    db.flush()
    db.add_all(
        [
            InstrumentProviderSymbol(
                instrument_id=instrument.id,
                data_source_id=source.id,
                provider_symbol="AAPL",
                provider_exchange_code="XNAS",
                is_active=True,
            ),
            InstrumentProviderSymbol(
                instrument_id=duplicate.id,
                data_source_id=source.id,
                provider_symbol="AAPL",
                provider_exchange_code="XNYS",
                is_active=True,
            ),
        ]
    )
    db.flush()

    async def fake_execute(_db, _capability, _operation, **kwargs):
        return SimpleNamespace(
            provider_name=kwargs["provider_name"],
            result=[_record(event_key="ipo:aapl:ambiguous", payload={"ticker": "AAPL"})],
        )

    monkeypatch.setattr(market_events, "execute_provider_call", fake_execute)
    result = await market_events.refresh_market_events(
        AsyncSessionAdapter(db), provider_names=["massive"]
    )

    assert result["linked"] == 0
    assert result["unlinked"] == 1
    assert db.execute(select(MarketEvent)).scalar_one().instrument_id is None


@pytest.mark.asyncio
async def test_refresh_market_events_links_exact_issuer_cik_and_retains_other_failures(
    db, monkeypatch
):
    source = DataSource(name="fmp", base_url="https://financialmodelingprep.com")
    issuer = Issuer(
        domain_key="cik:0000320193",
        legal_name="Apple Inc.",
        cik="0000320193",
        country_code="US",
    )
    db.add_all([source, issuer])
    db.flush()

    async def fake_execute(_db, _capability, _operation, **kwargs):
        if kwargs["provider_name"] == "fmp":
            return SimpleNamespace(
                provider_name="fmp",
                result=[_record(event_key="earnings:apple:2026-09-12", payload={"cik": "320193"})],
            )
        raise RuntimeError("provider deliberately unavailable")

    monkeypatch.setattr(market_events, "execute_provider_call", fake_execute)
    result = await market_events.refresh_market_events(
        AsyncSessionAdapter(db), provider_names=["massive", "fmp"]
    )

    assert result["status"] == "refreshed"
    assert result["failures"] == 1
    assert result["linked"] == 1
    assert result["providers"][0]["status"] == "failed"
    row = db.execute(select(MarketEvent)).scalar_one()
    assert row.issuer_id == issuer.id
    assert row.instrument_id is None


@pytest.mark.asyncio
async def test_refresh_edgar_ipo_pipeline_uses_explicit_ciks_and_links_issuer(
    db, monkeypatch
):
    source = DataSource(name="edgar", base_url="https://data.sec.gov")
    issuer = Issuer(
        domain_key="cik:0000320193",
        legal_name="Apple Inc.",
        cik="0000320193",
        country_code="US",
    )
    db.add_all([source, issuer])
    db.flush()

    calls = []

    async def fake_execute(_db, capability, operation, **kwargs):
        assert capability is ProviderCapability.MARKET_EVENTS
        assert operation == "fetch_ipo_pipeline_events"
        calls.append(kwargs["usage_identity"])
        return SimpleNamespace(
            provider_name="edgar",
            result=[
                MarketEventRecord(
                    event_type="ipo_pipeline",
                    event_key="edgar:ipo_pipeline:0000320193:000032019324000001",
                    event_time=datetime(2026, 9, 12, tzinfo=UTC),
                    effective_date=date(2026, 9, 12),
                    title="SEC S-1 IPO pipeline filing",
                    source_version="submissions:recent",
                    is_provisional=True,
                    raw_payload={"cik": "0000320193", "form": "S-1"},
                )
            ],
        )

    monkeypatch.setattr(market_events, "execute_provider_call", fake_execute)
    result = await market_events.refresh_edgar_ipo_pipeline(
        AsyncSessionAdapter(db),
        ["320193", "320193", "not-a-cik"],
        max_ciks=10,
    )

    assert calls == ["cik:0000320193"]
    assert result["status"] == "refreshed"
    assert result["requested_ciks"] == 1
    assert result["invalid_ciks"] == 1
    assert result["failures"] == 1
    assert result["linked"] == 1
    row = db.execute(select(MarketEvent)).scalar_one()
    assert row.issuer_id == issuer.id
    assert row.event_type == "ipo_pipeline"
    assert row.is_provisional is True


@pytest.mark.asyncio
async def test_market_events_task_uses_bounded_forward_window(monkeypatch):
    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    calls = []

    async def fake_refresh(db, **kwargs):
        calls.append((db, kwargs))
        return {"status": "no_events"}

    monkeypatch.setattr(settings, "MARKET_EVENTS_REFRESH_ENABLED", True)
    monkeypatch.setattr(settings, "MARKET_EVENTS_REFRESH_LOOKAHEAD_DAYS", 14)
    monkeypatch.setattr(settings, "MARKET_EVENTS_REFRESH_MAX_PROVIDERS", 3)
    monkeypatch.setattr(data_tasks, "AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr("app.services.market_events.refresh_market_events", fake_refresh)

    result = await data_tasks.refresh_market_events({})

    assert result == {"status": "no_events"}
    assert len(calls) == 1
    _, kwargs = calls[0]
    assert kwargs["end"] >= kwargs["start"]
    assert (kwargs["end"] - kwargs["start"]).days == 14
    assert kwargs["max_providers"] == 3
