from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.instrument_identity import InstrumentIdentifier, InstrumentIdentifierType
from app.services.etf_holdings import ensure_lightweight_etf_instrument
from app.services.instrument_mastering import ensure_internal_identifier


class AsyncSessionAdapter:
    def __init__(self, session):
        self._session = session

    async def execute(self, *args, **kwargs):
        return self._session.execute(*args, **kwargs)

    async def flush(self, *args, **kwargs):
        self._session.flush(*args, **kwargs)

    async def refresh(self, *args, **kwargs):
        self._session.refresh(*args, **kwargs)

    def add(self, *args, **kwargs):
        return self._session.add(*args, **kwargs)

    def __getattr__(self, item):
        return getattr(self._session, item)


@pytest.mark.asyncio
async def test_ensure_lightweight_etf_instrument_only_creates_one_internal_identifier(db):
    async_db = AsyncSessionAdapter(db)

    instrument = await ensure_lightweight_etf_instrument(
        async_db,
        symbol="XLE",
        name="SPDR Select Sector Fund - Energy Select Sector",
    )
    db.flush()

    identifiers = (
        db.execute(
            select(InstrumentIdentifier).where(
                InstrumentIdentifier.instrument_id == instrument.id,
                InstrumentIdentifier.identifier_type == InstrumentIdentifierType.INTERNAL,
            )
        )
        .scalars()
        .all()
    )

    assert len(identifiers) == 1
    assert identifiers[0].identifier_value == f"instrument:{instrument.id}"
    assert instrument.primary_identifier_type == InstrumentIdentifierType.INTERNAL.value
    assert instrument.primary_identifier_value == f"instrument:{instrument.id}"


@pytest.mark.asyncio
async def test_ensure_internal_identifier_repairs_duplicate_internal_rows(db, instrument):
    async_db = AsyncSessionAdapter(db)

    stale_one = InstrumentIdentifier(
        instrument_id=instrument.id,
        data_source_id=None,
        identifier_type=InstrumentIdentifierType.INTERNAL,
        identifier_value="etf:AAPL",
        is_primary=True,
        is_active=True,
    )
    stale_two = InstrumentIdentifier(
        instrument_id=instrument.id,
        data_source_id=None,
        identifier_type=InstrumentIdentifierType.INTERNAL,
        identifier_value="legacy:AAPL",
        is_primary=False,
        is_active=True,
    )
    db.add_all([stale_one, stale_two])
    db.flush()

    instrument.primary_identifier_type = None
    instrument.primary_identifier_value = None

    await ensure_internal_identifier(async_db, instrument)
    db.flush()

    identifiers = (
        db.execute(
            select(InstrumentIdentifier).where(
                InstrumentIdentifier.instrument_id == instrument.id,
                InstrumentIdentifier.identifier_type == InstrumentIdentifierType.INTERNAL,
            )
        )
        .scalars()
        .all()
    )

    active = [row for row in identifiers if row.is_active]
    assert len(active) == 1
    assert active[0].identifier_value == f"instrument:{instrument.id}"
    assert active[0].is_primary is True
    assert any("__superseded__" in row.identifier_value for row in identifiers if row.id != active[0].id)
    assert instrument.primary_identifier_type == InstrumentIdentifierType.INTERNAL.value
    assert instrument.primary_identifier_value == f"instrument:{instrument.id}"
