from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models.exchange import Exchange
from app.models.listing import InstrumentListing
from app.services.exchange_catalog import (
    coerce_listing_lifecycle_at,
    normalize_exchange_mic,
    upsert_instrument_listing,
)
from tests.unit.conftest import AsyncSessionAdapter


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("NASDAQ", "XNAS"),
        ("NMS", "XNAS"),
        ("NYSE", "XNYS"),
        ("PCX", "ARCX"),
        ("AMEX", "XASE"),
        ("XNAS", "XNAS"),
        ("unverified venue", None),
        (None, None),
    ],
)
def test_normalize_exchange_mic(value, expected):
    assert normalize_exchange_mic(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2010-01-04", datetime(2010, 1, 4, tzinfo=UTC)),
        ("2026-07-31T12:30:00+00:00", datetime(2026, 7, 31, 12, 30, tzinfo=UTC)),
        (datetime(2026, 8, 11, 12, 30), datetime(2026, 8, 11, 12, 30, tzinfo=UTC)),
        (None, None),
        ("not-a-date", None),
    ],
)
def test_coerce_listing_lifecycle_at(value, expected):
    assert coerce_listing_lifecycle_at(value) == expected


@pytest.mark.asyncio
async def test_listing_persistence_links_canonical_exchange_and_preserves_distinct_venues(
    db, instrument
):
    async_db = AsyncSessionAdapter(db)
    instrument.symbol = "DUAL"
    instrument.name = "Dual venue fixture"

    await upsert_instrument_listing(
        async_db, instrument, "DUAL", exchange_code="NASDAQ", is_primary=True
    )
    await upsert_instrument_listing(async_db, instrument, "DUAL", exchange_code="NYSE")
    await upsert_instrument_listing(async_db, instrument, "DUAL", exchange_code="NASDAQ")
    await async_db.flush()

    listings = (
        db.execute(
            select(InstrumentListing).where(InstrumentListing.instrument_id == instrument.id)
        )
        .scalars()
        .all()
    )
    exchanges = (
        db.execute(select(Exchange).where(Exchange.mic.in_(["XNAS", "XNYS"]))).scalars().all()
    )
    assert {(row.ticker, row.exchange_id) for row in listings} == {
        ("DUAL", next(item.id for item in exchanges if item.mic == "XNAS")),
        ("DUAL", next(item.id for item in exchanges if item.mic == "XNYS")),
    }
    assert len(listings) == 2


@pytest.mark.asyncio
async def test_listing_persistence_retains_lifecycle_timestamps(db, instrument):
    async_db = AsyncSessionAdapter(db)
    effective_at = datetime(2010, 1, 4, tzinfo=UTC)
    known_at = datetime(2026, 8, 11, 12, 30, tzinfo=UTC)
    delisted_at = datetime(2026, 7, 31, tzinfo=UTC)

    await upsert_instrument_listing(
        async_db,
        instrument,
        instrument.symbol,
        exchange_code="NASDAQ",
        effective_at=effective_at,
        known_at=known_at,
        delisted_at=delisted_at,
        reactivate_existing=False,
    )
    await async_db.flush()

    listing = db.execute(
        select(InstrumentListing).where(InstrumentListing.instrument_id == instrument.id)
    ).scalar_one()

    def as_utc(value):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    assert as_utc(listing.effective_at) == effective_at
    assert as_utc(listing.known_at) == known_at
    assert as_utc(listing.delisted_at) == delisted_at
    assert listing.is_active is True
