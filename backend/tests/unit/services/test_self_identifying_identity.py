from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models.asset_class import AssetClass, InstrumentType
from app.models.data_source import DataSource
from app.models.exchange import Exchange
from app.models.instrument import Instrument
from app.models.listing import InstrumentListing
from app.models.market_data_foundation import (
    InstrumentIdentityQuarantine,
    MarketRefreshJob,
    MarketUniverseReconciliationRun,
)
from app.schemas.data_preparation import DataEnsureRequest
from app.services.data_preparation import create_data_preparation_request
from app.services.market_data_identity import (
    apply_domain_identity,
    instrument_identity_is_qualified,
    self_identifying_pair_key,
)
from app.services.market_universe import _find_instrument, _reconcile_rows
from tests.unit.conftest import AsyncSessionAdapter

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


def _type(db, asset_class: str, type_name: str) -> InstrumentType:
    asset = db.query(AssetClass).filter(AssetClass.name == asset_class).one_or_none()
    if asset is None:
        asset = AssetClass(name=asset_class, description=asset_class)
        db.add(asset)
        db.flush()
    instrument_type = InstrumentType(name=type_name, asset_class_id=asset.id)
    db.add(instrument_type)
    db.flush()
    return instrument_type


def _crypto(db, symbol: str = "BTC-USD", **values) -> Instrument:
    crypto_type = db.query(InstrumentType).filter(
        InstrumentType.name == "Crypto Spot"
    ).one_or_none() or _type(db, "Cryptocurrency", "Crypto Spot")
    instrument = Instrument(
        symbol=symbol,
        name=symbol,
        currency="USD",
        instrument_type_id=crypto_type.id,
        is_active=True,
        **values,
    )
    db.add(instrument)
    db.flush()
    return instrument


def test_pair_key_is_limited_to_crypto_and_fx_pairs():
    assert self_identifying_pair_key("Cryptocurrency", "btc-usd") == "crypto-pair:BTC-USD"
    assert self_identifying_pair_key("Cryptocurrency", "ETH/BTC") == "crypto-pair:ETH-BTC"
    assert self_identifying_pair_key("Currency", "EURUSD=X") == "fx-pair:EUR-USD"
    assert self_identifying_pair_key("Currency", "EUR/USD") == "fx-pair:EUR-USD"
    assert self_identifying_pair_key("Equity", "BTC-USD") is None
    assert self_identifying_pair_key("Exchange Traded Product", "BITO") is None
    assert self_identifying_pair_key("Cryptocurrency", "BTC") is None
    assert self_identifying_pair_key("Cryptocurrency", "USD-USD") is None


@pytest.mark.asyncio
async def test_mastering_resolves_a_spot_pair_without_equity_identifiers(db):
    session = AsyncSessionAdapter(db)
    pair = _crypto(db)

    key = await apply_domain_identity(session, pair, identifiers={}, provider_name="coinbase")

    assert key == "crypto-pair:BTC-USD"
    assert pair.identity_status == "resolved"
    assert pair.domain_key == "crypto-pair:BTC-USD"
    assert await instrument_identity_is_qualified(session, pair)
    assert db.query(InstrumentIdentityQuarantine).count() == 0


@pytest.mark.asyncio
async def test_equity_without_security_identifier_is_still_quarantined(db, instrument):
    session = AsyncSessionAdapter(db)

    key = await apply_domain_identity(session, instrument, identifiers={}, provider_name="edgar")

    assert key is None
    assert instrument.identity_status == "quarantined"
    assert instrument.domain_key is None
    assert not await instrument_identity_is_qualified(session, instrument)


@pytest.mark.asyncio
async def test_a_pair_key_owned_by_another_row_is_quarantined_not_reassigned(db):
    session = AsyncSessionAdapter(db)
    owner = _crypto(db, identity_status="resolved", domain_key="crypto-pair:BTC-USD")
    duplicate = _crypto(db)

    key = await apply_domain_identity(session, duplicate, identifiers={}, provider_name="kraken")

    assert key is None
    assert duplicate.identity_status == "quarantined"
    assert duplicate.domain_key is None
    assert owner.domain_key == "crypto-pair:BTC-USD"
    quarantine = db.query(InstrumentIdentityQuarantine).one()
    assert quarantine.proposed_domain_key == "crypto-pair:BTC-USD"
    assert f"instrument {owner.id}" in quarantine.reason


@pytest.mark.asyncio
async def test_history_for_a_legacy_quarantined_pair_is_not_gated_on_identity(db, instrument):
    session = AsyncSessionAdapter(db)
    pair = _crypto(db, identity_status="quarantined")
    instrument.identity_status = "quarantined"
    db.flush()

    jobs_by_symbol = {}
    for target in (pair, instrument):
        parent = await create_data_preparation_request(
            session,
            owner_user_id=None,
            system_maintenance=True,
            request=DataEnsureRequest.model_validate(
                {
                    "target": {"kind": "instrument", "instrument_id": target.id},
                    "timeframe": "D1",
                    "datasets": ["history"],
                    "start_at": "2026-01-01T00:00:00Z",
                    "end_at": "2026-11-01T00:00:00Z",
                }
            ),
            now=NOW,
        )
        dependency = parent.metadata_payload["data_preparation"]["dependencies"][0]
        jobs_by_symbol[target.symbol] = (
            db.execute(
                select(MarketRefreshJob).where(MarketRefreshJob.id.in_(dependency["job_ids"]))
            )
            .scalars()
            .all()
        )

    identity_children = (
        db.execute(
            select(MarketRefreshJob).where(MarketRefreshJob.capability == "instrument_metadata")
        )
        .scalars()
        .all()
    )
    # The pair is repaired locally from its canonical symbol; the equity
    # still waits on a real identity child.
    assert pair.identity_status == "resolved"
    assert pair.domain_key == "crypto-pair:BTC-USD"
    assert [job.instrument_id for job in identity_children] == [instrument.id]
    pair_history = jobs_by_symbol["BTC-USD"]
    assert pair_history and all(
        not (job.metadata_payload["data_preparation_child"].get("wait_for_job_ids"))
        for job in pair_history
    )
    equity_history = jobs_by_symbol["AAPL"]
    assert equity_history and all(
        job.metadata_payload["data_preparation_child"]["wait_for_job_ids"]
        == [identity_children[0].id]
        for job in equity_history
    )


@pytest.mark.asyncio
async def test_explicit_history_acquisition_accepts_a_resolved_pair_without_a_mic(db):
    from app.routers.instruments import _qualified_identity

    session = AsyncSessionAdapter(db)
    pair = _crypto(db, identity_status="resolved", domain_key="crypto-pair:BTC-USD")
    db.add(
        InstrumentListing(instrument_id=pair.id, ticker="BTC-USD", is_primary=True, is_active=True)
    )
    db.flush()

    identity = await _qualified_identity(session, pair)

    assert identity is not None
    assert identity.domain_key == "crypto-pair:BTC-USD"
    assert identity.primary_listing_mic is None


@pytest.mark.asyncio
async def test_universe_reconciliation_backfills_an_existing_quarantined_pair(db):
    session = AsyncSessionAdapter(db)
    source = DataSource(name="coinbase", base_url="https://example.test")
    db.add(source)
    db.flush()
    run = MarketUniverseReconciliationRun(
        data_source_id=source.id, quote_type="CRYPTOCURRENCY", observed_at=NOW
    )
    db.add(run)
    db.flush()
    row = {"symbol": "ETH-USD", "name": "ETH/USD", "quoteType": "CRYPTOCURRENCY"}
    await _reconcile_rows(
        session,
        run=run,
        provider_name="coinbase",
        rows=[row],
        quote_type="CRYPTOCURRENCY",
        observed_at=NOW,
    )
    created = db.query(Instrument).filter(Instrument.symbol == "ETH-USD").one()
    assert created.domain_key == "crypto-pair:ETH-USD"
    # Simulate a row mastered before pair identities existed.
    created.domain_key = None
    created.identity_status = "quarantined"
    db.flush()

    await _reconcile_rows(
        session,
        run=run,
        provider_name="coinbase",
        rows=[row],
        quote_type="CRYPTOCURRENCY",
        observed_at=NOW,
    )

    assert db.query(Instrument).filter(Instrument.symbol == "ETH-USD").count() == 1
    assert created.identity_status == "resolved"
    assert created.domain_key == "crypto-pair:ETH-USD"


@pytest.mark.asyncio
async def test_cik_row_reuses_the_issuerless_listing_at_the_exact_ticker_and_venue(db, instrument):
    session = AsyncSessionAdapter(db)
    xnas = Exchange(mic="XNAS", name="Nasdaq", country_code="US")
    db.add(xnas)
    db.flush()
    instrument.symbol = "CSX"
    instrument.identity_status = "resolved"
    instrument.domain_key = "composite-figi:BBG000BGJRC8"
    db.add(
        InstrumentListing(
            instrument_id=instrument.id,
            ticker="CSX",
            exchange_id=xnas.id,
            is_primary=True,
            is_active=True,
        )
    )
    db.flush()

    # Before the fix an issuer key with no issuer row always returned None and
    # discovery created a second, quarantined CSX next to the resolved one.
    assert (
        await _find_instrument(session, symbol="CSX", exchange_id=xnas.id, sec_cik="277948")
        is instrument
    )
    # Never across venues, and never into a row that belongs to an issuer.
    assert await _find_instrument(session, symbol="CSX", exchange_id=None, sec_cik="277948") is None
    from app.models.market_data_foundation import Issuer

    other_issuer = Issuer(domain_key="cik:0000000001", legal_name="Other", cik="0000000001")
    db.add(other_issuer)
    db.flush()
    instrument.issuer_id = other_issuer.id
    db.flush()
    assert (
        await _find_instrument(session, symbol="CSX", exchange_id=xnas.id, sec_cik="277948") is None
    )


@pytest.mark.asyncio
async def test_symbol_lookup_tolerates_duplicate_tickers_and_honours_exact_row(db, instrument):
    from app.routers.instruments import _local_instrument_by_symbol, _local_instrument_for_acquire

    session = AsyncSessionAdapter(db)
    instrument.identity_status = "resolved"
    instrument.domain_key = "composite-figi:BBG000B9XRY4"
    instrument.primary_identifier_type = "composite_figi"
    instrument.primary_identifier_value = "BBG000B9XRY4"
    duplicate = Instrument(
        symbol="AAPL",
        name="Apple Inc.",
        currency="USD",
        instrument_type_id=instrument.instrument_type_id,
        is_active=True,
        identity_status="quarantined",
    )
    db.add(duplicate)
    db.flush()

    # This raised MultipleResultsFound ("Multiple rows were found when one or
    # none was required") for every identity child of a duplicated ticker.
    assert await _local_instrument_by_symbol(session, "AAPL") is instrument
    assert await _local_instrument_for_acquire(session, "AAPL", duplicate.id) is duplicate
    assert await _local_instrument_for_acquire(session, "AAPL", None) is instrument


@pytest.mark.asyncio
async def test_profile_owner_lookup_does_not_fail_on_duplicate_tickers(db, instrument):
    from app.providers.base import InstrumentProfile
    from app.routers.instruments import _find_existing_instrument_for_profile

    session = AsyncSessionAdapter(db)
    duplicate = Instrument(
        symbol="AAPL",
        name="Apple Inc.",
        currency="USD",
        instrument_type_id=instrument.instrument_type_id,
        is_active=True,
        identity_status="quarantined",
    )
    db.add(duplicate)
    db.flush()
    profile = InstrumentProfile(
        provider="edgar", symbol="AAPL", canonical_symbol="AAPL", name="Apple Inc."
    )

    # Two unresolved rows: the ticker is no evidence of which one is meant.
    assert await _find_existing_instrument_for_profile(session, profile) is None

    instrument.identity_status = "resolved"
    instrument.domain_key = "composite-figi:BBG000B9XRY4"
    instrument.primary_identifier_type = "composite_figi"
    instrument.primary_identifier_value = "BBG000B9XRY4"
    db.flush()
    assert await _find_existing_instrument_for_profile(session, profile) is instrument


@pytest.mark.asyncio
async def test_queued_identity_child_for_a_pair_resolves_without_provider_search(db, monkeypatch):
    from app.routers.instruments import acquire_instrument
    from app.schemas.instrument_acquisition import InstrumentAcquireRequest

    session = AsyncSessionAdapter(db)
    pair = _crypto(db, "SOL-USD", identity_status="quarantined")
    db.add(
        InstrumentListing(instrument_id=pair.id, ticker="SOL-USD", is_primary=True, is_active=True)
    )
    db.flush()

    async def forbidden_search(*_args, **_kwargs):
        raise AssertionError("a self-identifying pair must not search providers")

    monkeypatch.setattr(
        "app.routers.instruments.search_provider_instruments_async", forbidden_search
    )

    response = await acquire_instrument(
        InstrumentAcquireRequest(symbol="SOL-USD", request_id="pair-child", instrument_id=pair.id),
        session,
    )

    assert response.status == "resolved"
    assert response.instrument.domain_key == "crypto-pair:SOL-USD"
    assert pair.identity_status == "resolved"
