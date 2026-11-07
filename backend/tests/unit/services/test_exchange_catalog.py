from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest
from sqlalchemy import select

from app.models.exchange import Exchange
from app.models.listing import InstrumentListing
from app.models.market_data_foundation import (
    CalendarExceptionKind,
    ExchangeCalendarException,
    ExchangeSessionRule,
)
from app.services.exchange_catalog import (
    coerce_listing_lifecycle_at,
    normalize_exchange_mic,
    upsert_instrument_listing,
)
from app.services.exchange_sessions import resolve_session_window
from tests.unit.conftest import AsyncSessionAdapter


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("NASDAQ", "XNAS"),
        ("NASDAQ NMS - GLOBAL MARKET", "XNAS"),
        ("NMS", "XNAS"),
        ("NYSE", "XNYS"),
        ("PCX", "ARCX"),
        ("AMEX", "XASE"),
        ("Texas Stock Exchange", "TXSE"),
        ("TXSE", "TXSE"),
        ("Nasdaq Texas", "XBOS"),
        ("NYSE Texas", "XCHI"),
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


@pytest.mark.asyncio
async def test_known_exchange_gets_versioned_weekday_session_baseline(db, instrument):
    async_db = AsyncSessionAdapter(db)
    await upsert_instrument_listing(async_db, instrument, instrument.symbol, exchange_code="NASDAQ")
    exchange = db.execute(select(Exchange).where(Exchange.mic == "XNAS")).scalar_one()
    window = await resolve_session_window(async_db, exchange.id, date(2026, 9, 4))
    assert window is not None
    assert window.opens_at.hour == 13
    assert window.closes_at.hour == 20


@pytest.mark.asyncio
async def test_us_regular_session_uses_holidays_early_closes_and_explicit_overrides(db, instrument):
    async_db = AsyncSessionAdapter(db)
    await upsert_instrument_listing(async_db, instrument, instrument.symbol, exchange_code="NASDAQ")
    exchange = db.execute(select(Exchange).where(Exchange.mic == "XNAS")).scalar_one()

    # The supported US regular-session calendar applies even when the optional
    # dated-exception table has no row for Thanksgiving.
    assert await resolve_session_window(async_db, exchange.id, date(2026, 11, 26)) is None

    for early_close in (date(2026, 11, 27), date(2026, 12, 24)):
        window = await resolve_session_window(async_db, exchange.id, early_close)
        assert window is not None
        assert window.opens_at.hour == 14 and window.opens_at.minute == 30
        assert window.closes_at.hour == 18 and window.closes_at.minute == 0

    # The stored exchange timezone still controls DST conversion on ordinary days.
    dst_window = await resolve_session_window(async_db, exchange.id, date(2026, 3, 9))
    assert dst_window is not None
    assert (dst_window.opens_at.hour, dst_window.opens_at.minute) == (13, 30)
    assert dst_window.closes_at.hour == 20

    # An explicit dated exception remains authoritative over the recurring basis.
    db.add(
        ExchangeCalendarException(
            exchange_id=exchange.id,
            session_date=date(2026, 11, 27),
            session_code="regular",
            exception_kind=CalendarExceptionKind.EARLY_CLOSE,
            opens_at=time(10),
            closes_at=time(14),
            source="reviewed_test_exception",
        )
    )
    db.flush()
    overridden = await resolve_session_window(async_db, exchange.id, date(2026, 11, 27))
    assert overridden is not None
    assert overridden.source == "calendar_exception"
    assert (overridden.opens_at.hour, overridden.closes_at.hour) == (15, 19)


@pytest.mark.asyncio
async def test_us_holiday_basis_does_not_apply_to_non_us_venues_or_unknown_ids(db, instrument):
    async_db = AsyncSessionAdapter(db)
    await upsert_instrument_listing(async_db, instrument, instrument.symbol, exchange_code="NASDAQ")
    canadian = Exchange(
        mic="XTSE",
        name="Toronto Stock Exchange test venue",
        country_code="CA",
        timezone="America/Toronto",
        market_open="09:30",
        market_close="16:00",
        currency="CAD",
    )
    db.add(canadian)
    db.flush()
    db.add(
        ExchangeSessionRule(
            exchange_id=canadian.id,
            session_code="regular",
            weekday=3,
            opens_at=time(9, 30),
            closes_at=time(16),
            valid_from=date(2000, 1, 1),
            provenance={"source": "test"},
        )
    )
    db.flush()

    canadian_window = await resolve_session_window(async_db, canadian.id, date(2026, 11, 26))
    assert canadian_window is not None
    assert (canadian_window.opens_at.hour, canadian_window.closes_at.hour) == (14, 21)
    assert await resolve_session_window(async_db, 999_999, date(2026, 11, 26)) is None
