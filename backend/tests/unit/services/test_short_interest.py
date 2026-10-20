from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.market_data_foundation import (
    ProviderPaginationState,
    ShortInterestObservation,
    ShortInterestProviderObservation,
)
from app.models.provider_runtime import ProviderCapability
from app.providers.base import ShortInterestRecord
from app.services import short_interest
from tests.unit.conftest import AsyncSessionAdapter


def _record(day: int) -> ShortInterestRecord:
    row = {
        "settlementDate": f"2026-08-{day:02d}",
        "symbolCode": "AAPL",
        "currentShortPositionQuantity": str(day),
        "vendor_extension": {"kept": True},
    }
    return ShortInterestRecord(
        settlement_date=date(2026, 8, day),
        publication_date=date(2026, 8, day),
        short_position=Decimal(day),
        short_percent_float=None,
        days_to_cover=None,
        source_identifier="AAPL",
        raw_payload=row,
    )


class _PagedProvider:
    name = "finra"

    def __init__(self, pages):
        self.pages = pages
        self.cursors = []

    def fetch_short_interest_page(self, symbol, *, start=None, end=None, cursor=None):
        assert symbol == "AAPL"
        self.cursors.append(cursor)
        return self.pages[len(self.cursors) - 1]


@pytest.mark.asyncio
async def test_short_interest_persists_each_page_and_resumes_without_refetching(
    db, instrument, monkeypatch
):
    instrument.domain_key = "figi:BBG000B9XRY4"
    provider = _PagedProvider(
        [
            {"records": [_record(1)], "next_cursor": "offset:1", "complete": False},
            {"records": [_record(2)], "next_cursor": None, "complete": True},
        ]
    )
    calls = []

    async def execute(_db, capability, operation, **kwargs):
        assert capability is ProviderCapability.SHORT_INTEREST
        assert operation == "fetch_short_interest"
        calls.append(kwargs["provider_symbol"])
        page = kwargs["invoke"](provider, kwargs["provider_symbol"])
        return SimpleNamespace(provider_name="finra", result=page)

    monkeypatch.setattr(short_interest, "get_provider", lambda _name: provider)
    monkeypatch.setattr(short_interest, "execute_provider_call", execute)
    async_db = AsyncSessionAdapter(db)

    first = await short_interest.refresh_short_interest_for_instrument(
        async_db, instrument.id, max_pages=1
    )
    assert first["status"] == "pending"
    assert first["next_page_pending"] is True
    assert first["records_fetched"] == 1
    assert provider.cursors == [None]
    first_page_observations = db.execute(select(ShortInterestProviderObservation)).scalars().all()
    assert len(first_page_observations) == 1
    assert first_page_observations[0].payload["vendor_extension"] == {"kept": True}
    state = db.execute(select(ProviderPaginationState)).scalar_one()
    assert len(state.cursor_history) == 1

    second = await short_interest.refresh_short_interest_for_instrument(
        async_db, instrument.id, max_pages=1
    )
    assert second["status"] == "complete"
    assert second["records_fetched"] == 1
    assert provider.cursors == [None, "offset:1"]
    assert len(db.execute(select(ShortInterestObservation)).scalars().all()) == 2
    assert len(db.execute(select(ShortInterestProviderObservation)).scalars().all()) == 2
    state = db.execute(select(ProviderPaginationState)).scalar_one()
    assert state.status == "complete"
    assert state.cursor is None

    already_complete = await short_interest.refresh_short_interest_for_instrument(
        async_db, instrument.id, max_pages=1
    )
    assert already_complete["status"] == "already_complete"
    assert len(calls) == 2
    assert state.cursor_history == []


@pytest.mark.asyncio
async def test_short_interest_repeated_cursor_persists_page_and_stops_retries(
    db, instrument, monkeypatch
):
    instrument.domain_key = "figi:BBG000B9XRY4"
    provider = _PagedProvider(
        [
            {"records": [_record(1)], "next_cursor": "offset:1", "complete": False},
            {"records": [_record(2)], "next_cursor": "offset:1", "complete": False},
        ]
    )

    async def execute(_db, _capability, _operation, **kwargs):
        page = kwargs["invoke"](provider, kwargs["provider_symbol"])
        return SimpleNamespace(provider_name="finra", result=page)

    monkeypatch.setattr(short_interest, "get_provider", lambda _name: provider)
    monkeypatch.setattr(short_interest, "execute_provider_call", execute)
    async_db = AsyncSessionAdapter(db)

    result = await short_interest.refresh_short_interest_for_instrument(
        async_db, instrument.id, max_pages=10
    )
    assert result["status"] == "failed"
    assert result["pages_fetched"] == 2
    assert "repeated" in result["failures"][0]["error"]
    assert provider.cursors == [None, "offset:1"]
    assert len(db.execute(select(ShortInterestProviderObservation)).scalars().all()) == 2

    state = db.execute(select(ProviderPaginationState)).scalar_one()
    assert state.cursor == "offset:1"
    assert state.status == "failed"
    assert len(state.cursor_history) == 1
    retry = await short_interest.refresh_short_interest_for_instrument(
        async_db, instrument.id, max_pages=10
    )
    assert retry["status"] == "failed"
    assert provider.cursors == [None, "offset:1"]


@pytest.mark.asyncio
async def test_short_interest_persists_rows_from_blocked_terminal_page(db, instrument, monkeypatch):
    instrument.domain_key = "figi:BBG000B9XRY4"
    provider = _PagedProvider(
        [
            {
                "records": [_record(1)],
                "next_cursor": "resume",
                "complete": False,
                "blocked_error": "explicit smaller date windows required",
            },
            {"records": [], "next_cursor": None, "complete": True},
        ]
    )

    async def execute(_db, _capability, _operation, **kwargs):
        return SimpleNamespace(
            provider_name="finra",
            result=kwargs["invoke"](provider, kwargs["provider_symbol"]),
        )

    monkeypatch.setattr(short_interest, "get_provider", lambda _name: provider)
    monkeypatch.setattr(short_interest, "execute_provider_call", execute)
    async_db = AsyncSessionAdapter(db)

    result = await short_interest.refresh_short_interest_for_instrument(
        async_db, instrument.id, max_pages=2
    )
    assert result["status"] == "failed"
    assert result["records_fetched"] == 1
    observation = db.execute(select(ShortInterestProviderObservation)).scalar_one()
    assert observation.payload["vendor_extension"] == {"kept": True}
    state = db.execute(select(ProviderPaginationState)).scalar_one()
    assert state.status == "failed"
    assert state.cursor == "resume"
    assert "explicit smaller date windows" in state.last_error

    skipped = await short_interest.refresh_short_interest_for_instrument(
        async_db, instrument.id, max_pages=2
    )
    assert skipped["status"] == "failed"
    assert provider.cursors == [None]

    resumed = await short_interest.refresh_short_interest_for_instrument(
        async_db, instrument.id, max_pages=2, retry_blocked=True
    )
    assert resumed["status"] == "complete"
    assert provider.cursors == [None, "resume"]

    repeated = await short_interest.refresh_short_interest_for_instrument(
        async_db, instrument.id, max_pages=2
    )
    assert repeated["status"] == "already_complete"
    assert provider.cursors == [None, "resume"]


@pytest.mark.asyncio
async def test_short_interest_requires_resolved_domain_identity_before_provider_call(
    db, instrument, monkeypatch
):
    calls = []
    monkeypatch.setattr(short_interest, "get_provider", lambda _name: calls.append("provider"))
    result = await short_interest.refresh_short_interest_for_instrument(
        AsyncSessionAdapter(db), instrument.id
    )
    assert result["status"] == "identity_unresolved"
    assert calls == []


@pytest.mark.asyncio
async def test_short_interest_rejects_nonpositive_page_budget(db, instrument):
    with pytest.raises(ValueError, match="max_pages must be a positive integer"):
        await short_interest.refresh_short_interest_for_instrument(
            AsyncSessionAdapter(db), instrument.id, max_pages=0
        )
