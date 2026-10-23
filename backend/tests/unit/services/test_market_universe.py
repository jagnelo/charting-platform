from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.models.data_source import DataSource
from app.models.exchange import Exchange
from app.models.instrument import Instrument
from app.models.instrument_identity import InstrumentProviderSymbol
from app.models.instrument_reconciliation import InstrumentReconciliationIssueObservation
from app.models.listing import InstrumentListing
from app.models.market_data_foundation import (
    Issuer,
    MarketUniverseLifecycleObservation,
    MarketUniverseLifecycleObservationSnapshot,
    MarketUniverseReconciliationRun,
)
from app.models.provider_observation import UniverseDiscoverySnapshot
from app.services.exchange_catalog import ensure_exchange, upsert_instrument_listing
from app.services.instrument_mastering import register_provider_symbol
from app.services.market_universe import (
    _find_instrument,
    _mark_missing,
    _reconcile_rows,
    _upsert_observation,
    reconcile_us_universe,
)
from tests.unit.conftest import AsyncSessionAdapter


@pytest.mark.asyncio
async def test_combined_nms_and_otc_reconciliation_keeps_both_complete_source_snapshots(
    db, monkeypatch
):
    """A single configured reconciliation cycle must complete and retain NMS and OTC evidence."""

    from app.services import market_universe

    sources = {
        "nasdaq": DataSource(name="nasdaq", base_url="https://nasdaq.example.test"),
        "finra_otc_directory": DataSource(
            name="finra_otc_directory", base_url="https://finra.example.test"
        ),
    }
    db.add_all(sources.values())
    db.flush()
    resolved = [
        SimpleNamespace(provider_name=name, data_source=source) for name, source in sources.items()
    ]
    providers = {
        "nasdaq": SimpleNamespace(supported_discovery_types=lambda: ["EQUITY"]),
        "finra_otc_directory": SimpleNamespace(supported_discovery_types=lambda: ["EQUITY"]),
    }
    pages = {
        "nasdaq": {
            "total": 1,
            "quotes": [{"symbol": "NMSX", "name": "NMS Example", "exchange": "XNAS"}],
            "source_files": ["nasdaqlisted", "otherlisted"],
            "source_file_creation_times": {
                "nasdaqlisted": "2026-10-09T21:31:00",
                "otherlisted": "2026-10-09T21:31:00",
            },
        },
        "finra_otc_directory": {
            "total": 1,
            "quotes": [{"symbol": "OTCX", "name": "OTC Example", "exchange": "OTC"}],
            "source_snapshot_date": "2026-10-09",
        },
    }

    async def resolve_fixture(*_args, **kwargs):
        assert kwargs["operation"] == "reconcile_universe_page"
        return resolved

    async def execute_fixture(_db, _capability, operation, *, provider_name, invoke, **_kwargs):
        result = invoke(providers[provider_name], None)
        assert operation.endswith(":0")
        return SimpleNamespace(result=result, data_source=sources[provider_name])

    for name, page in pages.items():
        providers[name].discover_universe_page = lambda _quote_type, _offset, p=page: p

    monkeypatch.setattr(market_universe, "resolve_provider_chain", resolve_fixture)
    monkeypatch.setattr(market_universe, "get_discovery_provider", lambda name: providers[name])
    monkeypatch.setattr(market_universe, "execute_provider_call", execute_fixture)

    result = await reconcile_us_universe(AsyncSessionAdapter(db), quote_types=["EQUITY"])

    runs = (
        db.query(MarketUniverseReconciliationRun).order_by(MarketUniverseReconciliationRun.id).all()
    )
    snapshots = db.query(UniverseDiscoverySnapshot).order_by(UniverseDiscoverySnapshot.id).all()
    assert result["status"] == "complete"
    assert result["providers"] == ["finra_otc_directory", "nasdaq"]
    assert [(run.provenance["provider"], run.status) for run in runs] == [
        ("nasdaq", "complete"),
        ("finra_otc_directory", "complete"),
    ]
    assert [snapshot.data_source.name for snapshot in snapshots] == [
        "nasdaq",
        "finra_otc_directory",
    ]
    assert snapshots[0].payload["page"] == pages["nasdaq"]
    assert snapshots[1].payload["page"] == pages["finra_otc_directory"]
    assert runs[0].provenance["absence_scope"] is None
    assert runs[1].provenance["absence_scope"] == "US_OTC"


@pytest.mark.asyncio
async def test_cta_reconciliation_preserves_case_distinct_symbols(db, monkeypatch):
    """CTA-native symbol spelling is retained through listing and alias writes."""

    from app.services import market_universe

    source = DataSource(name="cta_plan", base_url="https://cta.example.test")
    db.add(source)
    db.flush()
    rows = [
        {"symbol": "TpC", "exchange": "XNYS", "quoteType": "EQUITY"},
        {"symbol": "TPC", "exchange": "XNYS", "quoteType": "EQUITY"},
    ]
    page = {
        "total": 2,
        "quotes": rows,
        "complete": True,
        "source_snapshot_date": "2026-10-12",
        "raw_source_payload": {"symbol_file_csv": "retained source"},
    }
    provider = SimpleNamespace(
        supported_discovery_types=lambda: ["EQUITY"],
        discover_universe_page=lambda _quote_type, _offset: page,
    )
    resolved = [SimpleNamespace(provider_name="cta_plan", data_source=source)]

    async def resolve_fixture(*_args, **_kwargs):
        return resolved

    async def execute_fixture(_db, _capability, operation, *, invoke, **_kwargs):
        assert operation.endswith(":0")
        return SimpleNamespace(result=invoke(provider, None), data_source=source)

    monkeypatch.setattr(market_universe, "resolve_provider_chain", resolve_fixture)
    monkeypatch.setattr(market_universe, "get_discovery_provider", lambda _name: provider)
    monkeypatch.setattr(market_universe, "execute_provider_call", execute_fixture)

    result = await reconcile_us_universe(AsyncSessionAdapter(db), quote_types=["EQUITY"])

    listings = (
        db.query(InstrumentListing)
        .filter(InstrumentListing.source == "cta_plan")
        .order_by(InstrumentListing.ticker)
        .all()
    )
    aliases = (
        db.query(InstrumentProviderSymbol)
        .filter(InstrumentProviderSymbol.data_source_id == source.id)
        .order_by(InstrumentProviderSymbol.provider_symbol)
        .all()
    )
    snapshot = db.query(UniverseDiscoverySnapshot).filter_by(data_source_id=source.id).one()

    assert result["status"] == "complete"
    assert [listing.ticker for listing in listings] == ["TPC", "TpC"]
    assert [alias.provider_symbol for alias in aliases] == ["TPC", "TpC"]
    assert snapshot.payload["page"]["raw_source_payload"] == {"symbol_file_csv": "retained source"}


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
            "source_snapshot_date": observed_at.date().isoformat(),
            "source_file_creation_times": {
                "nasdaqlisted": f"{observed_at.date().isoformat()}T17:00:00",
                "otherlisted": f"{observed_at.date().isoformat()}T17:01:00",
            },
            "absence_scope": "US_NMS",
        },
    )
    db.add(run)
    db.flush()
    return run


def _make_authoritative_otc_run(db, source, *, observed_at, snapshot_date, status="complete"):
    run = MarketUniverseReconciliationRun(
        data_source_id=source.id,
        quote_type="EQUITY",
        observed_at=observed_at,
        finished_at=observed_at,
        status=status,
        provenance={
            "provider": "finra_otc_directory",
            "quote_type": "EQUITY",
            "snapshot_complete": status == "complete",
            "source_files": [
                "https://api.finra.org/partitions/group/otcMarket/name/otcSecurityMaster",
                "https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster",
            ],
            "absence_scope": "US_OTC",
            "source_snapshot_date": snapshot_date,
        },
    )
    db.add(run)
    db.flush()
    return run


@pytest.mark.asyncio
async def test_lifecycle_observation_retains_each_provider_payload(db, instrument):
    source = DataSource(name="fixture-lifecycle-history", base_url="https://example.test")
    db.add(source)
    db.flush()
    observed_at = datetime(2026, 9, 3, 21, tzinfo=UTC)
    run = _make_authoritative_nasdaq_run(db, source, observed_at=observed_at)
    session = AsyncSessionAdapter(db)

    await _upsert_observation(
        session,
        data_source_id=source.id,
        run_id=run.id,
        symbol=instrument.symbol,
        exchange_mic="XNAS",
        quote_type="EQUITY",
        instrument_id=instrument.id,
        listing_id=None,
        payload={"symbol": instrument.symbol, "status": "active"},
        observed_at=observed_at,
    )
    second_at = observed_at + timedelta(days=1)
    await _upsert_observation(
        session,
        data_source_id=source.id,
        run_id=run.id,
        symbol=instrument.symbol,
        exchange_mic="XNAS",
        quote_type="EQUITY",
        instrument_id=instrument.id,
        listing_id=None,
        payload={"symbol": instrument.symbol, "status": "halted"},
        observed_at=second_at,
    )

    current = db.query(MarketUniverseLifecycleObservation).one()
    snapshots = (
        db.query(MarketUniverseLifecycleObservationSnapshot)
        .order_by(MarketUniverseLifecycleObservationSnapshot.observed_at)
        .all()
    )
    assert current.payload["status"] == "halted"
    assert [snapshot.payload["status"] for snapshot in snapshots] == ["active", "halted"]
    assert len(snapshots) == 2


@pytest.mark.asyncio
async def test_nasdaq_only_misses_do_not_retire_listing_before_composite_nms_snapshot(
    db, instrument
):
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
    assert row.present is True
    assert row.lifecycle_status == "active"
    assert row.consecutive_missing == 0
    assert listing.is_active is True
    assert instrument.is_active is True

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
    assert listing.is_active is True
    assert instrument.is_active is True

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
async def test_otc_missing_counts_distinct_complete_snapshot_dates(db, instrument, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_KIND", "finra_otc_query_api")
    source = DataSource(name="finra_otc_directory", base_url="https://api.finra.org")
    db.add(source)
    db.flush()
    session = AsyncSessionAdapter(db)
    exchange = await ensure_exchange(session, "OTC")
    listing = InstrumentListing(
        instrument_id=instrument.id,
        exchange_id=exchange.id,
        ticker=instrument.symbol,
        is_primary=True,
        is_active=True,
    )
    db.add(listing)
    db.flush()
    initial_at = datetime(2026, 9, 3, 21, tzinfo=UTC)
    initial_run = _make_authoritative_otc_run(
        db,
        source,
        observed_at=initial_at,
        snapshot_date="2026-09-03",
    )
    await _upsert_observation(
        session,
        data_source_id=source.id,
        run_id=initial_run.id,
        symbol=instrument.symbol,
        exchange_mic="OTC",
        quote_type="EQUITY",
        instrument_id=instrument.id,
        listing_id=listing.id,
        payload={"symbol": instrument.symbol, "status": "active"},
        observed_at=initial_at,
    )

    for observed_at, snapshot_date in (
        (datetime(2026, 9, 4, 21, tzinfo=UTC), "2026-09-04"),
        # Re-running the same provider snapshot must not count twice.
        (datetime(2026, 9, 5, 21, tzinfo=UTC), "2026-09-04"),
        (datetime(2026, 9, 8, 21, tzinfo=UTC), "2026-09-08"),
        (datetime(2026, 9, 9, 21, tzinfo=UTC), "2026-09-09"),
    ):
        run = _make_authoritative_otc_run(
            db,
            source,
            observed_at=observed_at,
            snapshot_date=snapshot_date,
        )
        await _mark_missing(
            session,
            run=run,
            provider_name="finra_otc_directory",
            quote_type="EQUITY",
            active_keys=set(),
            observed_at=observed_at,
            missing_confirmations=3,
        )

    observation = db.query(MarketUniverseLifecycleObservation).one()
    assert observation.consecutive_missing == 3
    assert observation.lifecycle_status == "missing"
    assert observation.present is False
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
    assert db.query(InstrumentReconciliationIssueObservation).count() == 1

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
    assert db.query(InstrumentReconciliationIssueObservation).count() == 2


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
async def test_reconciliation_reuses_exact_provider_binding_when_ticker_candidates_collide(
    db, instrument, instrument_b
):
    """A provider's existing scoped alias avoids a duplicate-key crash."""

    source = DataSource(name="finra_otc_directory", base_url="https://example.test")
    db.add(source)
    db.flush()
    instrument.symbol = "AAGH"
    await register_provider_symbol(
        AsyncSessionAdapter(db),
        instrument,
        "finra_otc_directory",
        "AAGH",
        provider_exchange_code="OTC",
        provider_instrument_type="EQUITY",
    )
    await upsert_instrument_listing(
        AsyncSessionAdapter(db), instrument_b, "AAGH", exchange_code="OTC", is_primary=True
    )
    run = MarketUniverseReconciliationRun(
        data_source_id=source.id,
        quote_type="EQUITY",
        observed_at=datetime(2026, 10, 14, tzinfo=UTC),
    )
    db.add(run)
    db.flush()

    await _reconcile_rows(
        AsyncSessionAdapter(db),
        run=run,
        provider_name="finra_otc_directory",
        rows=[{"symbol": "AAGH", "exchange": "OTC", "status": "active"}],
        quote_type="EQUITY",
        observed_at=run.observed_at,
    )

    bindings = (
        db.query(InstrumentProviderSymbol)
        .filter(
            InstrumentProviderSymbol.data_source_id == source.id,
            InstrumentProviderSymbol.provider_symbol == "AAGH",
            InstrumentProviderSymbol.provider_exchange_code == "OTC",
        )
        .all()
    )
    observation = db.query(MarketUniverseLifecycleObservation).filter_by(run_id=run.id).one()
    assert run.observed_count == 1
    assert run.quarantined_count == 0
    assert len(bindings) == 1
    assert bindings[0].instrument_id == instrument.id
    assert observation.instrument_id == instrument.id


@pytest.mark.asyncio
async def test_reconciliation_quarantines_unbound_ambiguous_ticker_venue(
    db, instrument, instrument_b
):
    """Without a source alias or stable key, ambiguous tickers are retained for review."""

    source = DataSource(name="finra_otc_directory", base_url="https://example.test")
    db.add(source)
    db.flush()
    instrument.symbol = "AAGH"
    await upsert_instrument_listing(
        AsyncSessionAdapter(db), instrument, "AAGH", exchange_code="OTC", is_primary=True
    )
    await upsert_instrument_listing(
        AsyncSessionAdapter(db), instrument_b, "AAGH", exchange_code="OTC", is_primary=True
    )
    run = MarketUniverseReconciliationRun(
        data_source_id=source.id,
        quote_type="EQUITY",
        observed_at=datetime(2026, 10, 14, tzinfo=UTC),
    )
    db.add(run)
    db.flush()

    await _reconcile_rows(
        AsyncSessionAdapter(db),
        run=run,
        provider_name="finra_otc_directory",
        rows=[{"symbol": "AAGH", "exchange": "OTC", "status": "active"}],
        quote_type="EQUITY",
        observed_at=run.observed_at,
    )

    assert run.observed_count == 0
    assert run.quarantined_count == 1
    assert db.query(InstrumentListing).filter(InstrumentListing.ticker == "AAGH").count() == 2
    assert db.query(InstrumentProviderSymbol).filter_by(data_source_id=source.id).count() == 0
    assert db.query(InstrumentReconciliationIssueObservation).count() == 1


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
async def test_massive_universe_scan_resumes_from_persisted_cursor_without_refetching_pages(
    db, monkeypatch
):
    from app.services import market_universe
    from app.services.provider_quota_coordinator import ProviderQuotaAdmissionError

    source = DataSource(name="massive", base_url="https://api.massive.com")
    db.add(source)
    db.flush()
    resolved = SimpleNamespace(provider_name="massive", data_source=source)
    provider_calls = []
    reconciled_rows = []
    quota_denied = [False]

    class MassiveDiscoveryFixture:
        def supported_discovery_types(self):
            return ["EQUITY"]

        def discover_universe_page(self, quote_type, offset, *, cursor=None):
            provider_calls.append((quote_type, offset, cursor))
            if offset == 0:
                return {
                    "total": None,
                    "quotes": [{"symbol": "FIRST", "name": "First", "exchange": "XNAS"}],
                    "next_url": "https://api.massive.com/v3/reference/tickers?cursor=page-two",
                    "next_offset": 1_000,
                    "complete": False,
                }
            return {
                "total": None,
                "quotes": [{"symbol": "SECOND", "name": "Second", "exchange": "XNAS"}],
                "next_url": None,
                "next_cursor": None,
                "next_offset": None,
                "complete": True,
            }

    provider = MassiveDiscoveryFixture()

    async def resolve_fixture(*_args, **_kwargs):
        return [resolved]

    async def execute_fixture(
        _db,
        _capability,
        operation,
        *,
        provider_name,
        invoke,
        **_kwargs,
    ):
        offset = int(operation.rsplit(":", 1)[1])
        if offset == 1_000 and not quota_denied[0]:
            quota_denied[0] = True
            raise ProviderQuotaAdmissionError(
                "durable provider quota admission denied for "
                "universe_discovery/reconcile_universe_page:EQUITY:1000: massive"
            )
        page = invoke(provider, None)
        return SimpleNamespace(result=page, data_source=source)

    async def capture_rows(_db, *, run, rows, **_kwargs):
        reconciled_rows.extend(rows)
        run.expected_count = len(rows)
        run.observed_count = len(rows)
        return set()

    monkeypatch.setattr(market_universe, "resolve_provider_chain", resolve_fixture)
    monkeypatch.setattr(market_universe, "get_discovery_provider", lambda _name: provider)
    monkeypatch.setattr(market_universe, "execute_provider_call", execute_fixture)
    monkeypatch.setattr(market_universe, "_reconcile_rows", capture_rows)

    session = AsyncSessionAdapter(db)
    first = await reconcile_us_universe(session, provider_name="massive")
    assert first["runs"][0]["status"] == "deferred"
    assert provider_calls == [("EQUITY", 0, None)]

    second = await reconcile_us_universe(session, provider_name="massive")
    assert second["runs"][0]["status"] == "complete"
    assert provider_calls == [("EQUITY", 0, None), ("EQUITY", 1_000, "page-two")]
    assert [row["symbol"] for row in reconciled_rows] == ["FIRST", "SECOND"]
    run = db.query(MarketUniverseReconciliationRun).one()
    assert run.status == "complete"
    assert run.provenance["continuation_count"] == 1
    assert run.provenance["snapshot_consistency"] == "resumed_provider_cursor_across_invocations"
    assert db.query(UniverseDiscoverySnapshot).count() == 2


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
        "expected_mics": ["ARCX", "BATS", "IEXG", "TXSE", "XASE", "XBOS", "XCHI", "XNAS", "XNYS"],
        "observed_mics": [],
        "missing_expected_mics": [
            "ARCX",
            "BATS",
            "IEXG",
            "TXSE",
            "XASE",
            "XBOS",
            "XCHI",
            "XNAS",
            "XNYS",
        ],
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


def test_nms_tape_c_scope_comes_from_nasdaqlisted_not_otherlisted():
    from app.services.market_universe import _REQUIRED_NMS_SCOPES, _nms_scope_key

    # Nasdaq Trader publishes both files in one validated run, but only
    # nasdaqlisted is the distinct Tape C roster. otherlisted stays useful
    # supplementary evidence and cannot satisfy the required Tape C scope.
    assert _nms_scope_key("nasdaq", "EQUITY", {"nasdaqlisted", "otherlisted"}) == (
        "nasdaq_tape_c",
        "EQUITY",
    )
    assert _nms_scope_key("nasdaq", "EQUITY", {"otherlisted"}) is None
    assert _nms_scope_key("nasdaq", "ETF", {"nasdaqlisted", "otherlisted"}) == ("nasdaq", "ETF")

    scopes = {
        _nms_scope_key("cta_plan", "EQUITY", set()),
        _nms_scope_key("nasdaq", "EQUITY", {"nasdaqlisted", "otherlisted"}),
        _nms_scope_key("nasdaq", "ETF", {"nasdaqlisted", "otherlisted"}),
    }
    assert scopes == set(_REQUIRED_NMS_SCOPES)


@pytest.mark.asyncio
async def test_nms_absence_union_uses_same_cycle_cta_and_nasdaq_listed_scopes(db, monkeypatch):
    """A real Nasdaq-listed file can satisfy Tape C without inventing a provider run."""

    from app.services import market_universe

    sources = {
        name: DataSource(name=name, base_url=f"https://{name}.example.test")
        for name in ("cta_plan", "nasdaq")
    }
    db.add_all(sources.values())
    db.flush()

    cta_page = {
        "total": 1,
        "quotes": [{"symbol": "CTA1", "name": "CTA Example", "exchange": "XNYS"}],
        "complete": True,
        "source_files": ["cta_symbol_file_index", "CTA.Symbol.File.20261020.csv"],
        "source_snapshot_date": "2026-10-20",
        "source_row_count": 1,
        "raw_source_payload": {"index_html": "index", "symbol_file_csv": "row"},
    }
    nasdaq_pages = {
        "EQUITY": {
            "total": 1,
            "quotes": [
                {
                    "symbol": "NQ1",
                    "name": "Nasdaq Listed Example",
                    "exchange": "XNAS",
                    "quoteType": "EQUITY",
                    "source_file": "nasdaqlisted",
                }
            ],
            "source_files": ["nasdaqlisted", "otherlisted"],
            "source_file_creation_times": {
                "nasdaqlisted": "2026-10-20T17:00:00",
                "otherlisted": "2026-10-20T17:00:00",
            },
        },
        "ETF": {
            "total": 1,
            "quotes": [
                {
                    "symbol": "ETF1",
                    "name": "Nasdaq ETF Example",
                    "exchange": "ARCX",
                    "quoteType": "ETF",
                    "source_file": "otherlisted",
                }
            ],
            "source_files": ["nasdaqlisted", "otherlisted"],
            "source_file_creation_times": {
                "nasdaqlisted": "2026-10-20T17:00:00",
                "otherlisted": "2026-10-20T17:00:00",
            },
        },
    }
    providers = {
        "cta_plan": SimpleNamespace(
            supported_discovery_types=lambda: ["EQUITY"],
            discover_universe_page=lambda _quote_type, _offset: cta_page,
        ),
        "nasdaq": SimpleNamespace(
            supported_discovery_types=lambda: ["EQUITY", "ETF"],
            discover_universe_page=lambda quote_type, _offset: nasdaq_pages[quote_type],
        ),
    }
    resolved = [
        SimpleNamespace(provider_name=name, data_source=source) for name, source in sources.items()
    ]

    async def resolve_fixture(*_args, **_kwargs):
        return resolved

    async def execute_fixture(_db, _capability, operation, *, provider_name, invoke, **_kwargs):
        assert operation.endswith(":0")
        return SimpleNamespace(
            result=invoke(providers[provider_name], None),
            data_source=sources[provider_name],
        )

    monkeypatch.setattr(market_universe, "resolve_provider_chain", resolve_fixture)
    monkeypatch.setattr(market_universe, "get_discovery_provider", lambda name: providers[name])
    monkeypatch.setattr(market_universe, "execute_provider_call", execute_fixture)

    result = await reconcile_us_universe(AsyncSessionAdapter(db))

    runs = (
        db.query(MarketUniverseReconciliationRun).order_by(MarketUniverseReconciliationRun.id).all()
    )
    assert result["status"] == "complete"
    assert len(runs) == 3
    assert {(run.provenance["provider"], run.quote_type) for run in runs} == {
        ("cta_plan", "EQUITY"),
        ("nasdaq", "EQUITY"),
        ("nasdaq", "ETF"),
    }
    assert all(run.provenance["absence_scope"] == "US_NMS" for run in runs)
    cycle_ids = {run.provenance["nms_union_cycle_id"] for run in runs}
    assert len(cycle_ids) == 1
    expected_union = {
        "cta_plan:EQUITY": runs[0].id,
        "nasdaq_tape_c:EQUITY": next(
            run.id
            for run in runs
            if run.provenance["provider"] == "nasdaq" and run.quote_type == "EQUITY"
        ),
        "nasdaq:ETF": next(
            run.id
            for run in runs
            if run.provenance["provider"] == "nasdaq" and run.quote_type == "ETF"
        ),
    }
    assert all(run.provenance["nms_union_provider_runs"] == expected_union for run in runs)


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
async def test_incomplete_nms_source_does_not_count_absence_for_any_listing(
    db, instrument, instrument_b
):
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

    assert nms_observation.present is True
    assert nms_observation.consecutive_missing == 0
    assert otc_observation.present is True
    assert otc_observation.consecutive_missing == 0
    assert otc_listing.is_active is True
    assert run.missing_count == 0


@pytest.mark.asyncio
async def test_provider_symbol_binding_retains_lifecycle_timestamps_and_retires_on_relisting_gap(
    db, instrument
):
    session = AsyncSessionAdapter(db)
    effective_at = datetime(2024, 1, 2, tzinfo=UTC)
    known_at = datetime(2024, 1, 3, tzinfo=UTC)
    retired_at = datetime(2026, 9, 16, 21, tzinfo=UTC)

    await register_provider_symbol(
        session,
        instrument,
        "nasdaq",
        instrument.symbol,
        provider_exchange_code="XNAS",
        effective_at=effective_at,
        known_at=known_at,
        delisted_at=retired_at,
        reactivate_existing=True,
    )

    binding = db.query(InstrumentProviderSymbol).one()
    assert binding.effective_at == effective_at.replace(tzinfo=None)
    assert binding.known_at == known_at.replace(tzinfo=None)
    assert binding.retired_at == retired_at.replace(tzinfo=None)
    assert binding.is_active is False

    # A later authoritative reappearance reactivates the same binding without
    # losing the historical lifecycle observation rows.
    await register_provider_symbol(
        session,
        instrument,
        "nasdaq",
        instrument.symbol,
        provider_exchange_code="XNAS",
        known_at=retired_at + timedelta(days=1),
        reactivate_existing=True,
    )
    binding = db.query(InstrumentProviderSymbol).one()
    assert binding.is_active is True
    assert binding.retired_at is None
    assert binding.known_at == known_at.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_nasdaq_only_absence_does_not_retire_provider_symbol_binding(db, instrument):
    source = DataSource(name="nasdaq", base_url="https://example.test")
    db.add(source)
    db.flush()
    session = AsyncSessionAdapter(db)
    exchange = await ensure_exchange(session, "XNAS")
    observed_at = datetime(2026, 9, 16, 21, tzinfo=UTC)
    listing = InstrumentListing(
        instrument_id=instrument.id,
        exchange_id=exchange.id,
        ticker=instrument.symbol,
        is_primary=True,
        is_active=True,
    )
    binding = InstrumentProviderSymbol(
        instrument_id=instrument.id,
        data_source_id=source.id,
        provider_symbol=instrument.symbol,
        provider_exchange_code="XNAS",
        is_primary=True,
        is_active=True,
    )
    db.add_all([listing, binding])
    db.flush()
    observation = MarketUniverseLifecycleObservation(
        data_source_id=source.id,
        instrument_id=instrument.id,
        listing_id=listing.id,
        provider_symbol=instrument.symbol,
        exchange_mic="XNAS",
        quote_type="EQUITY",
        observed_at=observed_at - timedelta(days=1),
        present=False,
        lifecycle_status="missing_pending",
        first_seen_at=observed_at - timedelta(days=10),
        last_missing_at=observed_at - timedelta(days=1),
        consecutive_seen=0,
        consecutive_missing=2,
        payload={"symbol": instrument.symbol},
    )
    db.add(observation)
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

    assert binding.is_active is True
    assert binding.retired_at is None
    assert listing.is_active is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source_files", "creation_times", "expected_scope", "expected_missing"),
    [
        (
            ["nasdaqlisted", "otherlisted"],
            {"nasdaqlisted": "2026-09-16T17:00:00", "otherlisted": "2026-09-16T17:01:00"},
            None,
            0,
        ),
        (
            ["nasdaqlisted", "otherlisted"],
            {"nasdaqlisted": "2026-09-15T17:00:00", "otherlisted": "2026-09-15T17:01:00"},
            None,
            0,
        ),
        (["nasdaqlisted"], {}, None, 0),
    ],
)
async def test_nasdaq_reconciliation_does_not_authorize_whole_nms_absence(
    db, instrument, monkeypatch, source_files, creation_times, expected_scope, expected_missing
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
                "source_file_creation_times": creation_times,
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
            "expected_mics": [
                "ARCX",
                "BATS",
                "IEXG",
                "TXSE",
                "XASE",
                "XBOS",
                "XCHI",
                "XNAS",
                "XNYS",
            ],
            "observed_mics": ["XNAS"],
            "missing_expected_mics": [
                "ARCX",
                "BATS",
                "IEXG",
                "TXSE",
                "XASE",
                "XBOS",
                "XCHI",
                "XNYS",
            ],
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
async def test_universe_reconciliation_defers_quota_denial_without_calling_it_a_provider_failure(
    db, monkeypatch
):
    from app.services import market_universe
    from app.services.provider_quota_coordinator import ProviderQuotaAdmissionError

    source = DataSource(name="fixture-quota-denied", base_url="https://example.test")
    db.add(source)
    db.flush()
    resolved = SimpleNamespace(provider_name=source.name, data_source=source)

    class _DiscoveryProvider:
        def supported_discovery_types(self):
            return ["EQUITY"]

    async def resolve_fixture(*_args, **_kwargs):
        return [resolved]

    async def denied_page(*_args, **_kwargs):
        raise ProviderQuotaAdmissionError("durable provider quota admission denied")

    monkeypatch.setattr(market_universe, "resolve_provider_chain", resolve_fixture)
    monkeypatch.setattr(
        market_universe, "get_discovery_provider", lambda _name: _DiscoveryProvider()
    )
    monkeypatch.setattr(market_universe, "execute_provider_call", denied_page)

    result = await reconcile_us_universe(
        AsyncSessionAdapter(db), provider_name="fixture-quota-denied"
    )

    run = db.query(MarketUniverseReconciliationRun).one()
    assert result["status"] == "deferred"
    assert result["runs"][0]["status"] == "deferred"
    assert run.status == "deferred"
    assert run.observed_count == 0
    assert "quota admission denied" in (run.error or "")


@pytest.mark.asyncio
async def test_universe_reconciliation_follows_cursor_until_explicit_completion(db, monkeypatch):
    from app.models.provider_observation import UniverseDiscoverySnapshot
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
                "raw_payload": {"results": ["first-page"]},
                "source_documents": {
                    "https://provider.example/security-master": "complete original source body"
                },
                "next_offset": 1,
                "next_url": "cursor",
            }
            if ":0" in args[2]
            else {
                "quotes": [{"symbol": "MSFT", "exchange": "XNAS"}],
                "raw_payload": {"results": ["second-page"]},
                "complete": True,
            }
        )
        return SimpleNamespace(result=page, data_source=source)

    monkeypatch.setattr(market_universe, "execute_provider_call", cursor_pages)
    result = await reconcile_us_universe(AsyncSessionAdapter(db), provider_name="massive")

    assert result["status"] == "complete"
    assert result["runs"][0]["observed"] == 2
    assert result["runs"][0]["expected"] == 2
    snapshots = (
        db.query(UniverseDiscoverySnapshot)
        .filter_by(data_source_id=source.id, quote_type="EQUITY")
        .order_by(UniverseDiscoverySnapshot.offset)
        .all()
    )
    assert [snapshot.payload["page"]["raw_payload"] for snapshot in snapshots] == [
        {"results": ["first-page"]},
        {"results": ["second-page"]},
    ]
    assert snapshots[0].payload["page"]["source_documents"] == {
        "https://provider.example/security-master": "complete original source body"
    }


@pytest.mark.asyncio
async def test_marketstack_raw_total_scope_reports_filtered_expected_count(db, monkeypatch):
    from app.services import market_universe

    source = DataSource(name="marketstack", base_url="https://example.test")
    db.add(source)
    db.flush()
    provider = SimpleNamespace(supported_discovery_types=lambda: ["EQUITY"])
    resolved = SimpleNamespace(provider_name="marketstack", data_source=source)

    async def resolve_fixture(*_args, **_kwargs):
        return [resolved]

    responses = iter(
        [
            SimpleNamespace(
                result={
                    "total": 3,
                    "total_scope": "raw",
                    "quotes": [{"symbol": "AAPL", "exchange": "XNAS"}],
                    "next_offset": 2,
                    "complete": False,
                },
                data_source=source,
            ),
            SimpleNamespace(
                result={
                    "total": 3,
                    "total_scope": "raw",
                    "quotes": [{"symbol": "MSFT", "exchange": "XNAS"}],
                    "next_offset": None,
                    "complete": True,
                },
                data_source=source,
            ),
        ]
    )

    async def raw_total_pages(*_args, **_kwargs):
        return next(responses)

    monkeypatch.setattr(market_universe, "resolve_provider_chain", resolve_fixture)
    monkeypatch.setattr(market_universe, "get_discovery_provider", lambda _name: provider)
    monkeypatch.setattr(market_universe, "execute_provider_call", raw_total_pages)

    result = await reconcile_us_universe(
        AsyncSessionAdapter(db), provider_name="marketstack", quote_types=["EQUITY"]
    )

    assert result["status"] == "complete"
    assert result["runs"][0]["observed"] == 2
    assert result["runs"][0]["expected"] == 2
    run = db.query(MarketUniverseReconciliationRun).one()
    assert run.provenance["total_scope"] == "raw"


@pytest.mark.asyncio
async def test_universe_reconciliation_does_not_discard_valid_large_offsets(db, monkeypatch):
    """A valid provider continuation beyond the old arbitrary cap is retained."""

    from app.models.provider_observation import UniverseDiscoverySnapshot
    from app.services import market_universe

    source = DataSource(name="massive", base_url="https://example.test")
    db.add(source)
    db.flush()
    provider = SimpleNamespace(supported_discovery_types=lambda: ["EQUITY"])
    resolved = SimpleNamespace(provider_name="massive", data_source=source)
    large_offset = 2_000_001

    async def resolve_fixture(*_args, **_kwargs):
        return [resolved]

    async def large_offset_pages(*args, **_kwargs):
        page = (
            {
                "quotes": [{"symbol": "AAPL", "exchange": "XNAS"}],
                "total": large_offset + 1,
                "next_offset": large_offset,
            }
            if args[2].endswith(":0")
            else {
                "quotes": [{"symbol": "MSFT", "exchange": "XNAS"}],
                "total": large_offset + 1,
            }
        )
        return SimpleNamespace(result=page, data_source=source)

    monkeypatch.setattr(market_universe, "resolve_provider_chain", resolve_fixture)
    monkeypatch.setattr(market_universe, "get_discovery_provider", lambda _name: provider)
    monkeypatch.setattr(market_universe, "execute_provider_call", large_offset_pages)

    result = await reconcile_us_universe(AsyncSessionAdapter(db), provider_name="massive")

    assert result["status"] == "complete"
    assert result["runs"][0]["observed"] == 2
    snapshots = db.query(UniverseDiscoverySnapshot).all()
    assert {snapshot.offset for snapshot in snapshots} == {0, large_offset}


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
