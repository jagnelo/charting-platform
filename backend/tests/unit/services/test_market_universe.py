from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.data_source import DataSource
from app.models.listing import InstrumentListing
from app.models.market_data_foundation import (
    Issuer,
    MarketUniverseLifecycleObservation,
    MarketUniverseReconciliationRun,
)
from app.services.market_universe import (
    _find_instrument,
    _mark_missing,
    _reconcile_rows,
    _upsert_observation,
)
from tests.unit.conftest import AsyncSessionAdapter


@pytest.mark.asyncio
async def test_missing_listing_requires_three_complete_observations(db, instrument):
    source = DataSource(name="fixture-discovery", base_url="https://example.test")
    db.add(source)
    db.flush()
    listing = InstrumentListing(
        instrument_id=instrument.id,
        ticker=instrument.symbol,
        is_primary=True,
        is_active=True,
    )
    db.add(listing)
    db.flush()
    session = AsyncSessionAdapter(db)
    observed = datetime(2026, 9, 4, tzinfo=UTC)
    initial_run = MarketUniverseReconciliationRun(
        data_source_id=source.id,
        quote_type="EQUITY",
        observed_at=observed,
    )
    db.add(initial_run)
    db.flush()
    await _upsert_observation(
        session,
        data_source_id=source.id,
        run_id=initial_run.id,
        symbol=instrument.symbol,
        exchange_mic=None,
        quote_type="EQUITY",
        instrument_id=instrument.id,
        listing_id=listing.id,
        payload={"symbol": instrument.symbol},
        observed_at=observed,
    )

    for index in range(1, 4):
        run = MarketUniverseReconciliationRun(
            data_source_id=source.id,
            quote_type="EQUITY",
            observed_at=observed + timedelta(days=index),
        )
        db.add(run)
        db.flush()
        await _mark_missing(
            session,
            run=run,
            provider_name="fixture-discovery",
            quote_type="EQUITY",
            active_keys=set(),
            observed_at=run.observed_at,
            missing_confirmations=3,
        )

    row = db.query(MarketUniverseLifecycleObservation).one()
    assert row.present is False
    assert row.lifecycle_status == "missing"
    assert row.consecutive_missing == 3
    assert listing.is_active is False
    assert instrument.is_active is False


@pytest.mark.asyncio
async def test_cik_does_not_merge_a_new_symbol_without_security_identifier(db, instrument):
    issuer = Issuer(
        domain_key="cik:0000123456",
        legal_name="Example Holdings",
        cik="0000123456",
    )
    db.add(issuer)
    db.flush()
    instrument.issuer_id = issuer.id
    listing = InstrumentListing(
        instrument_id=instrument.id,
        ticker=instrument.symbol,
        is_primary=True,
        is_active=True,
    )
    db.add(listing)
    db.flush()
    session = AsyncSessionAdapter(db)

    assert (
        await _find_instrument(
            session,
            symbol="AAPL",
            exchange_id=None,
            sec_cik="0000123456",
        )
    ) is instrument
    assert (
        await _find_instrument(
            session,
            symbol="AAPL-P",
            exchange_id=None,
            sec_cik="0000123456",
        )
    ) is None


@pytest.mark.asyncio
async def test_cik_only_discovery_links_issuer_but_quarantines_security_identity(db, instrument):
    source = DataSource(name="edgar", base_url="https://example.test")
    db.add(source)
    db.flush()
    run = MarketUniverseReconciliationRun(
        data_source_id=source.id,
        quote_type="EQUITY",
        observed_at=datetime(2026, 9, 4, tzinfo=UTC),
    )
    db.add(run)
    db.flush()
    session = AsyncSessionAdapter(db)

    await _reconcile_rows(
        session,
        run=run,
        provider_name="edgar",
        rows=[
            {
                "symbol": "MSFT",
                "name": "Example Holdings",
                "sec_cik": "123456",
                "exchange": "NASDAQ",
            }
        ],
        quote_type="EQUITY",
        observed_at=run.observed_at,
    )

    from app.models.instrument import Instrument
    from app.models.instrument_identity import InstrumentIdentifier, InstrumentIdentifierType

    created = db.query(Instrument).filter(Instrument.symbol == "MSFT").one()
    assert created.issuer_id is not None
    assert created.identity_status == "quarantined"
    assert (
        db.query(InstrumentIdentifier)
        .filter(
            InstrumentIdentifier.instrument_id == created.id,
            InstrumentIdentifier.identifier_type == InstrumentIdentifierType.CIK,
        )
        .count()
        == 0
    )
