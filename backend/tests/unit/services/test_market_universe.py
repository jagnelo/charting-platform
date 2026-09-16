from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.models.data_source import DataSource
from app.models.exchange import Exchange
from app.models.instrument import Instrument
from app.models.listing import InstrumentListing
from app.models.market_data_foundation import (
    Issuer,
    MarketUniverseLifecycleObservation,
    MarketUniverseReconciliationRun,
)
from app.services.exchange_catalog import ensure_exchange, upsert_instrument_listing
from app.services.market_universe import (
    _find_instrument,
    _mark_missing,
    _reconcile_rows,
    _upsert_observation,
    reconcile_us_universe,
)
from tests.unit.conftest import AsyncSessionAdapter


def _make_authoritative_nasdaq_run(
    db, source, *, quote_type="EQUITY", observed_at, status="complete"
):
    run = MarketUniverseReconciliationRun(
        data_source_id=source.id,
        quote_type=quote_type,
        observed_at=observed_at,
        finished_at=observed_at,
        status=status,
        provenance={
            "provider": "nasdaq",
            "quote_type": quote_type,
            "snapshot_complete": status == "complete",
            "source_files": ["nasdaqlisted", "otherlisted"],
            "absence_scope": "US_NMS",
        },
    )
    db.add(run)
    db.flush()
    return run


@pytest.mark.asyncio
async def test_missing_listing_counts_distinct_completed_sessions_and_reactivates(db, instrument):
    source = DataSource(name="nasdaq", base_url="https://example.test")
    db.add(source)
    db.flush()
    session = AsyncSessionAdapter(db)
    exchange = await ensure_exchange(session, "XNAS")
    listing = InstrumentListing(
        instrument_id=instrument.id,
        exchange_id=exchange.id,
        ticker=instrument.symbol,
        is_primary=True,
        is_active=True,
    )
    db.add(listing)
    db.flush()
    observed = datetime(2026, 9, 3, 21, tzinfo=UTC)
    initial_run = _make_authoritative_nasdaq_run(db, source, observed_at=observed)
    await _upsert_observation(
        session,
        data_source_id=source.id,
        run_id=initial_run.id,
        symbol=instrument.symbol,
        exchange_mic="XNAS",
        quote_type="EQUITY",
        instrument_id=instrument.id,
        listing_id=listing.id,
        payload={"symbol": instrument.symbol},
        observed_at=observed,
    )

    first_session = datetime(2026, 9, 4, 21, tzinfo=UTC)
    first_miss = _make_authoritative_nasdaq_run(db, source, observed_at=first_session)
    await _mark_missing(
        session,
        run=first_miss,
        provider_name="nasdaq",
        quote_type="EQUITY",
        active_keys=set(),
        observed_at=first_session,
        missing_confirmations=3,
    )
    duplicate_same_session = datetime(2026, 9, 4, 22, tzinfo=UTC)
    duplicate_run = _make_authoritative_nasdaq_run(db, source, observed_at=duplicate_same_session)
    await _mark_missing(
        session,
        run=duplicate_run,
        provider_name="nasdaq",
        quote_type="EQUITY",
        active_keys=set(),
        observed_at=duplicate_same_session,
        missing_confirmations=3,
    )
    assert duplicate_run.missing_count == 0

    for session_day in (8, 9):
        session_at = datetime(2026, 9, session_day, 21, tzinfo=UTC)
        run = _make_authoritative_nasdaq_run(db, source, observed_at=session_at)
        await _mark_missing(
            session,
            run=run,
            provider_name="nasdaq",
            quote_type="EQUITY",
            active_keys=set(),
            observed_at=session_at,
            missing_confirmations=3,
        )

    row = db.query(MarketUniverseLifecycleObservation).one()
    assert row.present is False
    assert row.lifecycle_status == "missing"
    assert row.consecutive_missing == 3
    assert listing.is_active is False
    assert instrument.is_active is False

    supplemental_source = DataSource(name="massive", base_url="https://example.test")
    db.add(supplemental_source)
    db.flush()
    supplemental_run = MarketUniverseReconciliationRun(
        data_source_id=supplemental_source.id,
        quote_type="EQUITY",
        observed_at=datetime(2026, 9, 10, 20, tzinfo=UTC),
        status="complete",
    )
    db.add(supplemental_run)
    db.flush()
    await _reconcile_rows(
        session,
        run=supplemental_run,
        provider_name="massive",
        rows=[
            {
                "symbol": instrument.symbol,
                "name": instrument.name,
                "exchange": "XNAS",
                "currency": "USD",
                "quoteType": "EQUITY",
            }
        ],
        quote_type="EQUITY",
        observed_at=supplemental_run.observed_at,
    )
    assert listing.is_active is False
    assert instrument.is_active is False

    reappearance_at = datetime(2026, 9, 10, 21, tzinfo=UTC)
    reappearance_run = _make_authoritative_nasdaq_run(db, source, observed_at=reappearance_at)
    await _reconcile_rows(
        session,
        run=reappearance_run,
        provider_name="nasdaq",
        rows=[
            {
                "symbol": instrument.symbol,
                "name": instrument.name,
                "exchange": "XNAS",
                "currency": "USD",
                "quoteType": "EQUITY",
            }
        ],
        quote_type="EQUITY",
        observed_at=reappearance_at,
        authoritative_lifecycle=True,
    )
    assert row.present is True
    assert row.consecutive_missing == 0
    assert row.lifecycle_status == "active"
    assert listing.is_active is True
    assert instrument.is_active is True
    assert instrument.identity_status == "provisional"


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
async def test_exchange_qualified_symbol_does_not_merge_across_venues(db, instrument):
    session = AsyncSessionAdapter(db)
    instrument.symbol = "DUAL"
    await upsert_instrument_listing(
        session, instrument, "DUAL", exchange_code="NYSE", is_primary=True
    )
    xnas = db.query(Exchange).filter(Exchange.mic == "XNAS").one_or_none()
    if xnas is None:
        xnas = Exchange(mic="XNAS", name="Nasdaq")
        db.add(xnas)
        db.flush()

    assert await _find_instrument(session, symbol="DUAL", exchange_id=xnas.id) is None


@pytest.mark.asyncio
async def test_reconciliation_reuses_stable_owner_across_ticker_change(db, instrument):
    from app.models.instrument_identity import InstrumentIdentifier, InstrumentIdentifierType

    source = DataSource(name="massive", base_url="https://example.test")
    db.add(source)
    db.flush()
    instrument.domain_key = "figi:BBG000B9XRY4"
    db.add(
        InstrumentIdentifier(
            instrument_id=instrument.id,
            identifier_type=InstrumentIdentifierType.FIGI,
            identifier_value="BBG000B9XRY4",
            is_primary=True,
            is_active=True,
        )
    )
    run = MarketUniverseReconciliationRun(
        data_source_id=source.id,
        quote_type="EQUITY",
        observed_at=datetime(2026, 9, 4, tzinfo=UTC),
    )
    db.add(run)
    db.flush()

    await _reconcile_rows(
        AsyncSessionAdapter(db),
        run=run,
        provider_name="massive",
        rows=[
            {
                "symbol": "NEW",
                "name": "Renamed Security",
                "exchange": "NASDAQ",
                "currency": "USD",
                "figi": "bbg000b9xry4",
            }
        ],
        quote_type="EQUITY",
        observed_at=run.observed_at,
    )

    assert run.new_count == 0
    assert run.updated_count == 1
    assert db.query(Instrument).count() == 1
    listing = db.query(InstrumentListing).one()
    assert listing.instrument_id == instrument.id
    assert listing.ticker == "NEW"
    assert instrument.domain_key == "figi:BBG000B9XRY4"


@pytest.mark.asyncio
async def test_reconciliation_does_not_merge_unresolved_stable_key_by_ticker(db, instrument):
    from app.models.instrument import Instrument

    source = DataSource(name="massive", base_url="https://example.test")
    db.add(source)
    db.flush()
    db.add(
        InstrumentListing(
            instrument_id=instrument.id,
            ticker="AAPL",
            is_primary=True,
            is_active=True,
        )
    )
    run = MarketUniverseReconciliationRun(
        data_source_id=source.id,
        quote_type="EQUITY",
        observed_at=datetime(2026, 9, 4, tzinfo=UTC),
    )
    db.add(run)
    db.flush()

    await _reconcile_rows(
        AsyncSessionAdapter(db),
        run=run,
        provider_name="massive",
        rows=[
            {
                "symbol": "AAPL",
                "name": "New Stable Security",
                "exchange": "NASDAQ",
                "currency": "USD",
                "figi": "BBG000B9XRY4",
            }
        ],
        quote_type="EQUITY",
        observed_at=run.observed_at,
    )

    assert run.new_count == 1
    assert db.query(Instrument).count() == 2
    assert (
        db.query(Instrument).filter(Instrument.domain_key == "figi:BBG000B9XRY4").one().id
        != instrument.id
    )


@pytest.mark.asyncio
async def test_reconciliation_quarantines_conflicting_stable_owners(db, instrument, instrument_b):
    from app.models.instrument_identity import InstrumentIdentifier, InstrumentIdentifierType

    source = DataSource(name="massive", base_url="https://example.test")
    db.add(source)
    db.flush()
    db.add_all(
        [
            InstrumentIdentifier(
                instrument_id=instrument.id,
                identifier_type=InstrumentIdentifierType.FIGI,
                identifier_value="BBG000B9XRY4",
            ),
            InstrumentIdentifier(
                instrument_id=instrument_b.id,
                identifier_type=InstrumentIdentifierType.ISIN,
                identifier_value="US0378331005",
            ),
        ]
    )
    run = MarketUniverseReconciliationRun(
        data_source_id=source.id,
        quote_type="EQUITY",
        observed_at=datetime(2026, 9, 4, tzinfo=UTC),
    )
    db.add(run)
    db.flush()

    await _reconcile_rows(
        AsyncSessionAdapter(db),
        run=run,
        provider_name="massive",
        rows=[
            {
                "symbol": "AAPL",
                "name": "Conflicting Security",
                "exchange": "NASDAQ",
                "currency": "USD",
                "figi": "BBG000B9XRY4",
                "isin": "US0378331005",
            }
        ],
        quote_type="EQUITY",
        observed_at=run.observed_at,
    )

    assert run.quarantined_count == 1
    assert run.observed_count == 0
    assert db.query(InstrumentListing).count() == 0


@pytest.mark.asyncio
async def test_reconciliation_quarantines_ticker_venue_collision_with_stable_owner(
    db, instrument, instrument_b
):
    from app.models.instrument_identity import InstrumentIdentifier, InstrumentIdentifierType

    source = DataSource(name="massive", base_url="https://example.test")
    db.add(source)
    db.flush()
    db.add(
        InstrumentIdentifier(
            instrument_id=instrument.id,
            identifier_type=InstrumentIdentifierType.FIGI,
            identifier_value="BBG000B9XRY4",
        )
    )
    await upsert_instrument_listing(
        AsyncSessionAdapter(db), instrument_b, "NEW", exchange_code="NASDAQ", is_primary=True
    )
    run = MarketUniverseReconciliationRun(
        data_source_id=source.id,
        quote_type="EQUITY",
        observed_at=datetime(2026, 9, 4, tzinfo=UTC),
    )
    db.add(run)
    db.flush()

    await _reconcile_rows(
        AsyncSessionAdapter(db),
        run=run,
        provider_name="massive",
        rows=[
            {
                "symbol": "NEW",
                "name": "Stable Owner",
                "exchange": "NASDAQ",
                "currency": "USD",
                "figi": "BBG000B9XRY4",
            }
        ],
        quote_type="EQUITY",
        observed_at=run.observed_at,
    )

    assert run.quarantined_count == 1
    assert run.observed_count == 0
    assert db.query(InstrumentListing).count() == 1


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
    assert db.query(Issuer).filter(Issuer.id == created.issuer_id).one().country_code is None
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


@pytest.mark.asyncio
async def test_universe_reconciliation_rejects_page_without_completion_evidence(db, monkeypatch):
    from app.services import market_universe

    source = DataSource(name="fixture-pagination", base_url="https://example.test")
    db.add(source)
    db.flush()
    provider = SimpleNamespace(supported_discovery_types=lambda: ["EQUITY"])
    resolved = SimpleNamespace(provider_name="fixture-pagination", data_source=source)

    async def resolve_fixture(*_args, **_kwargs):
        return [resolved]

    monkeypatch.setattr(market_universe, "resolve_provider_chain", resolve_fixture)
    monkeypatch.setattr(market_universe, "get_discovery_provider", lambda _name: provider)

    async def incomplete_page(*_args, **_kwargs):
        return SimpleNamespace(
            result={"quotes": [{"symbol": "AAPL", "exchange": "XNAS"}]},
            data_source=source,
        )

    monkeypatch.setattr(market_universe, "execute_provider_call", incomplete_page)
    result = await reconcile_us_universe(
        AsyncSessionAdapter(db), provider_name="fixture-pagination"
    )

    assert result["status"] == "failed"
    assert result["runs"][0]["status"] == "failed"
    run = db.query(MarketUniverseReconciliationRun).one()
    assert "completion evidence" in (run.error or "")


@pytest.mark.asyncio
async def test_nasdaq_reconciliation_rejects_declared_total_gaps(db, monkeypatch):
    """A jumping cursor cannot turn a partial NMS snapshot into absence evidence."""

    from app.services import market_universe

    source = DataSource(name="nasdaq", base_url="https://example.test")
    db.add(source)
    db.flush()
    provider = SimpleNamespace(supported_discovery_types=lambda: ["EQUITY"])
    resolved = SimpleNamespace(provider_name="nasdaq", data_source=source)

    async def resolve_fixture(*_args, **_kwargs):
        return [resolved]

    responses = iter(
        [
            SimpleNamespace(
                result={
                    "total": 2,
                    "quotes": [{"symbol": "AAPL", "exchange": "XNAS"}],
                    "next_offset": 2,
                    "source_files": ["nasdaqlisted", "otherlisted"],
                },
                data_source=source,
            ),
            SimpleNamespace(
                result={
                    "total": 2,
                    "quotes": [],
                    "source_files": ["nasdaqlisted", "otherlisted"],
                },
                data_source=source,
            ),
        ]
    )

    async def sparse_pages(*_args, **_kwargs):
        return next(responses)

    monkeypatch.setattr(market_universe, "resolve_provider_chain", resolve_fixture)
    monkeypatch.setattr(market_universe, "get_discovery_provider", lambda _name: provider)
    monkeypatch.setattr(market_universe, "execute_provider_call", sparse_pages)

    result = await reconcile_us_universe(
        AsyncSessionAdapter(db), provider_name="nasdaq", quote_types=["EQUITY"]
    )

    assert result["status"] == "failed"
    run = db.query(MarketUniverseReconciliationRun).one()
    assert run.status == "failed"
    assert "declared total 2" in (run.error or "")
    assert run.observed_count == 0


@pytest.mark.asyncio
async def test_nasdaq_reconciliation_reports_and_rejects_unknown_venue(db, monkeypatch):
    from app.services import market_universe

    source = DataSource(name="nasdaq", base_url="https://example.test")
    db.add(source)
    db.flush()
    provider = SimpleNamespace(supported_discovery_types=lambda: ["EQUITY"])
    resolved = SimpleNamespace(provider_name="nasdaq", data_source=source)

    async def resolve_fixture(*_args, **_kwargs):
        return [resolved]

    async def unknown_venue_page(*_args, **_kwargs):
        return SimpleNamespace(
            result={
                "total": 1,
                "quotes": [{"symbol": "AAPL", "exchange": "NOT_A_MIC"}],
                "complete": True,
                "source_files": ["nasdaqlisted", "otherlisted"],
            },
            data_source=source,
        )

    monkeypatch.setattr(market_universe, "resolve_provider_chain", resolve_fixture)
    monkeypatch.setattr(market_universe, "get_discovery_provider", lambda _name: provider)
    monkeypatch.setattr(market_universe, "execute_provider_call", unknown_venue_page)

    result = await reconcile_us_universe(
        AsyncSessionAdapter(db), provider_name="nasdaq", quote_types=["EQUITY"]
    )

    assert result["status"] == "failed"
    run = db.query(MarketUniverseReconciliationRun).one()
    assert run.status == "failed"
    assert "unknown/unsupported venues" in (run.error or "")
    assert run.provenance["venue_coverage"] == {
        "expected_mics": ["ARCX", "BATS", "IEXG", "XASE", "XNAS", "XNYS"],
        "observed_mics": [],
        "missing_expected_mics": ["ARCX", "BATS", "IEXG", "XASE", "XNAS", "XNYS"],
        "row_counts": {},
        "unknown_mics": ["NOT_A_MIC"],
    }


@pytest.mark.asyncio
async def test_reconciliation_rejects_rows_for_a_different_requested_type(db, monkeypatch):
    from app.services import market_universe

    source = DataSource(name="nasdaq", base_url="https://example.test")
    db.add(source)
    db.flush()
    provider = SimpleNamespace(supported_discovery_types=lambda: ["EQUITY"])
    resolved = SimpleNamespace(provider_name="nasdaq", data_source=source)

    async def resolve_fixture(*_args, **_kwargs):
        return [resolved]

    async def wrong_type_page(*_args, **_kwargs):
        return SimpleNamespace(
            result={
                "total": 1,
                "quotes": [{"symbol": "SPY", "exchange": "ARCX", "quoteType": "ETF"}],
                "complete": True,
                "source_files": ["nasdaqlisted", "otherlisted"],
            },
            data_source=source,
        )

    monkeypatch.setattr(market_universe, "resolve_provider_chain", resolve_fixture)
    monkeypatch.setattr(market_universe, "get_discovery_provider", lambda _name: provider)
    monkeypatch.setattr(market_universe, "execute_provider_call", wrong_type_page)

    result = await reconcile_us_universe(
        AsyncSessionAdapter(db), provider_name="nasdaq", quote_types=["EQUITY"]
    )

    assert result["status"] == "failed"
    run = db.query(MarketUniverseReconciliationRun).one()
    assert "quote type ETF while reconciling EQUITY" in (run.error or "")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_name", "quote_type", "status", "absence_scope", "source_files"),
    [
        ("nasdaq", "EQUITY", "failed", "US_NMS", ["nasdaqlisted", "otherlisted"]),
        ("nasdaq", "EQUITY", "complete", "US_NMS", ["nasdaqlisted"]),
        ("massive", "EQUITY", "complete", None, []),
        ("finra_otc_directory", "OTC", "complete", None, []),
    ],
)
async def test_incomplete_or_non_authoritative_sources_do_not_count_absence(
    db, instrument, provider_name, quote_type, status, absence_scope, source_files
):
    source = DataSource(name=provider_name, base_url="https://example.test")
    db.add(source)
    db.flush()
    session = AsyncSessionAdapter(db)
    exchange = await ensure_exchange(session, "XNAS")
    listing = InstrumentListing(
        instrument_id=instrument.id,
        exchange_id=exchange.id,
        ticker=instrument.symbol,
        is_primary=True,
        is_active=True,
    )
    db.add(listing)
    db.flush()
    observed_at = datetime(2026, 9, 16, 21, tzinfo=UTC)
    observation = MarketUniverseLifecycleObservation(
        data_source_id=source.id,
        instrument_id=instrument.id,
        listing_id=listing.id,
        provider_symbol=instrument.symbol,
        exchange_mic="XNAS",
        quote_type=quote_type,
        observed_at=observed_at,
        present=True,
        lifecycle_status="active",
        first_seen_at=observed_at,
        last_seen_at=observed_at,
        consecutive_seen=1,
        consecutive_missing=0,
        payload={},
    )
    db.add(observation)
    run = MarketUniverseReconciliationRun(
        data_source_id=source.id,
        quote_type=quote_type,
        observed_at=observed_at,
        finished_at=observed_at,
        status=status,
        provenance={
            "provider": provider_name,
            "quote_type": quote_type,
            "snapshot_complete": status == "complete",
            "source_files": source_files,
            "absence_scope": absence_scope,
        },
    )
    db.add(run)
    db.flush()

    await _mark_missing(
        session,
        run=run,
        provider_name=provider_name,
        quote_type=quote_type,
        active_keys=set(),
        observed_at=observed_at,
        missing_confirmations=3,
    )

    assert observation.present is True
    assert observation.consecutive_missing == 0
    assert listing.is_active is True
    assert run.missing_count == 0


@pytest.mark.asyncio
async def test_nms_snapshot_absence_does_not_touch_otc_venue_rows(db, instrument, instrument_b):
    source = DataSource(name="nasdaq", base_url="https://example.test")
    db.add(source)
    db.flush()
    session = AsyncSessionAdapter(db)
    xnas = await ensure_exchange(session, "XNAS")
    otcm = await ensure_exchange(session, "OTCM")
    observed_at = datetime(2026, 9, 16, 21, tzinfo=UTC)
    nms_listing = InstrumentListing(
        instrument_id=instrument.id,
        exchange_id=xnas.id,
        ticker=instrument.symbol,
        is_primary=True,
        is_active=True,
    )
    otc_listing = InstrumentListing(
        instrument_id=instrument_b.id,
        exchange_id=otcm.id,
        ticker=instrument_b.symbol,
        is_primary=True,
        is_active=True,
    )
    db.add_all([nms_listing, otc_listing])
    db.flush()
    nms_observation = MarketUniverseLifecycleObservation(
        data_source_id=source.id,
        instrument_id=instrument.id,
        listing_id=nms_listing.id,
        provider_symbol=instrument.symbol,
        exchange_mic="XNAS",
        quote_type="EQUITY",
        observed_at=observed_at,
        present=True,
        lifecycle_status="active",
        first_seen_at=observed_at,
        last_seen_at=observed_at,
        consecutive_seen=1,
        consecutive_missing=0,
        payload={},
    )
    otc_observation = MarketUniverseLifecycleObservation(
        data_source_id=source.id,
        instrument_id=instrument_b.id,
        listing_id=otc_listing.id,
        provider_symbol=instrument_b.symbol,
        exchange_mic="OTCM",
        quote_type="EQUITY",
        observed_at=observed_at,
        present=True,
        lifecycle_status="active",
        first_seen_at=observed_at,
        last_seen_at=observed_at,
        consecutive_seen=1,
        consecutive_missing=0,
        payload={},
    )
    db.add_all([nms_observation, otc_observation])
    run = _make_authoritative_nasdaq_run(db, source, observed_at=observed_at)

    await _mark_missing(
        session,
        run=run,
        provider_name="nasdaq",
        quote_type="EQUITY",
        active_keys=set(),
        observed_at=observed_at,
        missing_confirmations=3,
    )

    assert nms_observation.present is False
    assert nms_observation.consecutive_missing == 1
    assert otc_observation.present is True
    assert otc_observation.consecutive_missing == 0
    assert otc_listing.is_active is True
    assert run.missing_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source_files", "expected_scope", "expected_missing"),
    [
        (["nasdaqlisted", "otherlisted"], "US_NMS", 1),
        (["nasdaqlisted"], None, 0),
    ],
)
async def test_nasdaq_reconciliation_requires_both_official_files_for_absence(
    db, instrument, monkeypatch, source_files, expected_scope, expected_missing
):
    from app.services import market_universe

    source = DataSource(name="nasdaq", base_url="https://example.test")
    db.add(source)
    db.flush()
    session = AsyncSessionAdapter(db)
    exchange = await ensure_exchange(session, "XNAS")
    listing = InstrumentListing(
        instrument_id=instrument.id,
        exchange_id=exchange.id,
        ticker=instrument.symbol,
        is_primary=True,
        is_active=True,
    )
    db.add(listing)
    db.flush()
    observed_at = datetime(2026, 9, 16, 21, tzinfo=UTC)
    db.add(
        MarketUniverseLifecycleObservation(
            data_source_id=source.id,
            run_id=None,
            instrument_id=instrument.id,
            listing_id=listing.id,
            provider_symbol=instrument.symbol,
            exchange_mic="XNAS",
            quote_type="EQUITY",
            observed_at=observed_at,
            present=True,
            lifecycle_status="active",
            first_seen_at=observed_at,
            last_seen_at=observed_at,
            consecutive_seen=1,
            consecutive_missing=0,
            payload={"symbol": instrument.symbol},
        )
    )
    db.flush()
    provider = SimpleNamespace(supported_discovery_types=lambda: ["EQUITY"])
    resolved = SimpleNamespace(provider_name="nasdaq", data_source=source)

    async def resolve_fixture(*_args, **_kwargs):
        return [resolved]

    async def complete_page(*_args, **_kwargs):
        return SimpleNamespace(
            result={
                "total": 1,
                "quotes": [{"symbol": "ZZZ", "exchange": "XNAS", "quoteType": "EQUITY"}],
                "complete": True,
                "source_files": source_files,
            },
            data_source=source,
        )

    monkeypatch.setattr(market_universe, "resolve_provider_chain", resolve_fixture)
    monkeypatch.setattr(market_universe, "get_discovery_provider", lambda _name: provider)
    monkeypatch.setattr(market_universe, "execute_provider_call", complete_page)
    monkeypatch.setattr(market_universe, "_utc", lambda value=None: value or observed_at)

    result = await reconcile_us_universe(session, provider_name="nasdaq")

    run = db.query(MarketUniverseReconciliationRun).one()
    observation = (
        db.query(MarketUniverseLifecycleObservation)
        .filter(MarketUniverseLifecycleObservation.provider_symbol == instrument.symbol)
        .one()
    )
    assert result["status"] == "complete"
    assert run.provenance["absence_scope"] == expected_scope
    assert run.missing_count == expected_missing
    assert observation.consecutive_missing == expected_missing
    if expected_scope == "US_NMS":
        assert run.provenance["venue_coverage"] == {
            "expected_mics": ["ARCX", "BATS", "IEXG", "XASE", "XNAS", "XNYS"],
            "observed_mics": ["XNAS"],
            "missing_expected_mics": ["ARCX", "BATS", "IEXG", "XASE", "XNYS"],
            "row_counts": {"XNAS": 1},
            "unknown_mics": [],
        }


@pytest.mark.asyncio
async def test_universe_reconciliation_redacts_run_error(db, monkeypatch):
    from app.services import market_universe

    source = DataSource(name="fixture-error-redaction", base_url="https://example.test")
    db.add(source)
    db.flush()
    resolved = SimpleNamespace(provider_name="fixture-error-redaction", data_source=source)

    class _DiscoveryProvider:
        def supported_discovery_types(self):
            return ["EQUITY"]

    async def resolve_fixture(*_args, **_kwargs):
        return [resolved]

    async def failing_page(*_args, **_kwargs):
        raise RuntimeError("GET https://provider.test/data?api_key=universe-secret")

    monkeypatch.setattr(market_universe, "resolve_provider_chain", resolve_fixture)
    monkeypatch.setattr(
        market_universe, "get_discovery_provider", lambda _name: _DiscoveryProvider()
    )
    monkeypatch.setattr(market_universe, "execute_provider_call", failing_page)

    result = await reconcile_us_universe(
        AsyncSessionAdapter(db), provider_name="fixture-error-redaction"
    )

    assert result["status"] == "failed"
    run = db.query(MarketUniverseReconciliationRun).one()
    assert "universe-secret" not in (run.error or "")
    assert "<redacted>" in (run.error or "")


@pytest.mark.asyncio
async def test_universe_reconciliation_follows_cursor_until_explicit_completion(db, monkeypatch):
    from app.services import market_universe

    source = DataSource(name="fixture-cursor", base_url="https://example.test")
    db.add(source)
    db.flush()
    provider = SimpleNamespace(supported_discovery_types=lambda: ["EQUITY"])
    resolved = SimpleNamespace(provider_name="massive", data_source=source)

    async def resolve_fixture(*_args, **_kwargs):
        return [resolved]

    monkeypatch.setattr(market_universe, "resolve_provider_chain", resolve_fixture)
    monkeypatch.setattr(market_universe, "get_discovery_provider", lambda _name: provider)

    async def cursor_pages(*args, **_kwargs):
        page = (
            {
                "quotes": [{"symbol": "AAPL", "exchange": "XNAS"}],
                "next_offset": 1,
                "next_url": "cursor",
            }
            if ":0" in args[2]
            else {"quotes": [{"symbol": "MSFT", "exchange": "XNAS"}], "complete": True}
        )
        return SimpleNamespace(result=page, data_source=source)

    monkeypatch.setattr(market_universe, "execute_provider_call", cursor_pages)
    result = await reconcile_us_universe(AsyncSessionAdapter(db), provider_name="massive")

    assert result["status"] == "complete"
    assert result["runs"][0]["observed"] == 2
    assert result["runs"][0]["expected"] == 2


@pytest.mark.asyncio
async def test_universe_reconciliation_rejects_repeated_pagination_next_url(db, monkeypatch):
    from app.services import market_universe

    source = DataSource(name="fixture-repeated-cursor", base_url="https://example.test")
    db.add(source)
    db.flush()
    provider = SimpleNamespace(supported_discovery_types=lambda: ["EQUITY"])
    resolved = SimpleNamespace(provider_name="fixture-repeated-cursor", data_source=source)

    async def resolve_fixture(*_args, **_kwargs):
        return [resolved]

    async def repeated_cursor(*_args, **_kwargs):
        return SimpleNamespace(
            result={
                "quotes": [
                    {
                        "symbol": "AAPL" if ":0" in _args[2] else "MSFT",
                        "exchange": "XNAS",
                    }
                ],
                "next_url": "https://provider.example/page?cursor=stuck",
            },
            data_source=source,
        )

    monkeypatch.setattr(market_universe, "resolve_provider_chain", resolve_fixture)
    monkeypatch.setattr(market_universe, "get_discovery_provider", lambda _name: provider)
    monkeypatch.setattr(market_universe, "execute_provider_call", repeated_cursor)

    result = await reconcile_us_universe(
        AsyncSessionAdapter(db), provider_name="fixture-repeated-cursor"
    )

    assert result["status"] == "failed"
    run = db.query(MarketUniverseReconciliationRun).one()
    assert "repeated a pagination next_url" in (run.error or "")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "next_offset",
    [True, "1", 0, -1],
)
async def test_universe_reconciliation_rejects_invalid_next_offset(db, monkeypatch, next_offset):
    from app.services import market_universe

    source = DataSource(name="fixture-invalid-next-offset", base_url="https://example.test")
    db.add(source)
    db.flush()
    provider = SimpleNamespace(supported_discovery_types=lambda: ["EQUITY"])
    resolved = SimpleNamespace(provider_name="fixture-invalid-next-offset", data_source=source)

    async def resolve_fixture(*_args, **_kwargs):
        return [resolved]

    async def malformed_cursor(*_args, **_kwargs):
        return SimpleNamespace(
            result={
                "quotes": [{"symbol": "AAPL", "exchange": "XNAS"}],
                "next_offset": next_offset,
                "complete": True,
            },
            data_source=source,
        )

    monkeypatch.setattr(market_universe, "resolve_provider_chain", resolve_fixture)
    monkeypatch.setattr(market_universe, "get_discovery_provider", lambda _name: provider)
    monkeypatch.setattr(market_universe, "execute_provider_call", malformed_cursor)

    result = await reconcile_us_universe(
        AsyncSessionAdapter(db), provider_name="fixture-invalid-next-offset"
    )

    assert result["status"] == "failed"
    run = db.query(MarketUniverseReconciliationRun).one()
    assert "invalid next_offset" in (run.error or "") or "non-progressing next_offset" in (
        run.error or ""
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("total", [True, "1", 1.5, -1])
async def test_universe_reconciliation_rejects_invalid_total(db, monkeypatch, total):
    from app.services import market_universe

    source = DataSource(name="fixture-invalid-total", base_url="https://example.test")
    db.add(source)
    db.flush()
    provider = SimpleNamespace(supported_discovery_types=lambda: ["EQUITY"])
    resolved = SimpleNamespace(provider_name="fixture-invalid-total", data_source=source)

    async def resolve_fixture(*_args, **_kwargs):
        return [resolved]

    async def malformed_total(*_args, **_kwargs):
        return SimpleNamespace(
            result={
                "quotes": [{"symbol": "AAPL", "exchange": "XNAS"}],
                "total": total,
                "complete": True,
            },
            data_source=source,
        )

    monkeypatch.setattr(market_universe, "resolve_provider_chain", resolve_fixture)
    monkeypatch.setattr(market_universe, "get_discovery_provider", lambda _name: provider)
    monkeypatch.setattr(market_universe, "execute_provider_call", malformed_total)

    result = await reconcile_us_universe(
        AsyncSessionAdapter(db), provider_name="fixture-invalid-total"
    )

    assert result["status"] == "failed"
    run = db.query(MarketUniverseReconciliationRun).one()
    assert "invalid total" in (run.error or "") or "negative total" in (run.error or "")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "quotes,match",
    [
        ("not-an-array", "non-array quotes page"),
        ([{"name": "Missing symbol"}], "without a symbol"),
        ([{"symbol": "AAPL"}, "malformed"], "non-object quote row"),
        ([{"symbol": "AAPL"}, {"symbol": "AAPL"}], "duplicate listing row"),
    ],
)
async def test_universe_reconciliation_rejects_malformed_quote_pages(
    db, monkeypatch, quotes, match
):
    from app.services import market_universe

    source = DataSource(name="fixture-malformed-page", base_url="https://example.test")
    db.add(source)
    db.flush()
    provider = SimpleNamespace(supported_discovery_types=lambda: ["EQUITY"])
    resolved = SimpleNamespace(provider_name="fixture-malformed-page", data_source=source)

    async def resolve_fixture(*_args, **_kwargs):
        return [resolved]

    async def malformed_page(*_args, **_kwargs):
        return SimpleNamespace(
            result={"quotes": quotes, "complete": True},
            data_source=source,
        )

    monkeypatch.setattr(market_universe, "resolve_provider_chain", resolve_fixture)
    monkeypatch.setattr(market_universe, "get_discovery_provider", lambda _name: provider)
    monkeypatch.setattr(market_universe, "execute_provider_call", malformed_page)

    result = await reconcile_us_universe(
        AsyncSessionAdapter(db), provider_name="fixture-malformed-page"
    )

    assert result["status"] == "failed"
    run = db.query(MarketUniverseReconciliationRun).one()
    assert match in (run.error or "")
