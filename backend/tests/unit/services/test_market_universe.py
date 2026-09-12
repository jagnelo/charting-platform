from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
from app.services.exchange_catalog import upsert_instrument_listing
from app.services.market_universe import (
    _find_instrument,
    _mark_missing,
    _reconcile_rows,
    _upsert_observation,
    reconcile_us_universe,
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
                "quotes": [{"symbol": "AAPL", "exchange": "XNAS"}],
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
@pytest.mark.parametrize(
    "quotes,match",
    [
        ("not-an-array", "non-array quotes page"),
        ([{"name": "Missing symbol"}], "without a symbol"),
        ([{"symbol": "AAPL"}, "malformed"], "non-object quote row"),
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
