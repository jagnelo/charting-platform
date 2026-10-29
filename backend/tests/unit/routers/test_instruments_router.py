import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.config import settings
from app.lib.time_utils import wire_datetime
from app.models.data_source import DataSource
from app.models.exchange import Exchange
from app.models.instrument import Instrument
from app.models.instrument_identity import (
    InstrumentIdentifier,
    InstrumentIdentifierType,
    InstrumentProviderSymbol,
)
from app.models.instrument_stats import InstrumentStats
from app.models.listing import InstrumentListing
from app.models.market_data_foundation import InstrumentIdentityQuarantine
from app.models.ohlcv import OHLCVBar, Timeframe
from app.providers.base import IdentifierRecord, InstrumentProfile, ListingRecord
from app.routers.instruments import (
    _create_from_provider,
    _ensure_52w_stats,
    _instrument_search_exchange,
    _needs_52w_stats_refresh,
    acquire_instrument,
)
from app.schemas.instrument import (
    FieldProvenanceOut,
    InstrumentIdentifierOut,
    InstrumentListingOut,
    InstrumentStatsOut,
)
from app.schemas.instrument_acquisition import InstrumentAcquireRequest, ProviderCandidateBinding
from tests.unit.conftest import AsyncSessionAdapter


def test_shared_wire_datetime_normalizes_aware_and_naive_provenance_values():
    assert wire_datetime(datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)) == ("2026-01-02T03:04:05Z")
    assert wire_datetime(datetime.fromisoformat("2026-01-02T05:04:05+02:00")) == (
        "2026-01-02T03:04:05Z"
    )
    assert wire_datetime(datetime(2026, 1, 2, 3, 4, 5)) == "2026-01-02T03:04:05Z"
    assert wire_datetime(None) is None


def test_shared_wire_datetime_normalizes_offsets_to_utc_z():
    aware = datetime.fromisoformat("2026-01-02T05:04:05+02:00")
    naive = datetime(2026, 1, 2, 3, 4, 5)
    assert wire_datetime(aware) == "2026-01-02T03:04:05Z"
    assert wire_datetime(naive) == "2026-01-02T03:04:05Z"


def test_instrument_response_schemas_keep_pydantic_datetime_json_contract():
    naive = datetime(2026, 9, 12, 14, 30)
    aware = datetime(2026, 9, 12, 16, 30, tzinfo=UTC)

    stats = InstrumentStatsOut(computed_at=naive)
    provenance = FieldProvenanceOut(
        source="provider",
        fetched_at=naive,
        observed_at=aware,
    )
    listing = InstrumentListingOut(
        ticker="SPY",
        is_primary=True,
        is_active=True,
        effective_at=naive,
        known_at=aware,
        delisted_at=None,
    )
    identifier = InstrumentIdentifierOut(
        identifier_type="figi",
        identifier_value="BBG000B9XRY4",
        is_primary=True,
        is_active=True,
        effective_at=naive,
        known_at=aware,
        retired_at=None,
    )

    assert stats.model_dump(mode="json")["computed_at"] == "2026-09-12T14:30:00Z"
    assert provenance.model_dump(mode="json")["fetched_at"] == "2026-09-12T14:30:00Z"
    assert provenance.model_dump(mode="json")["observed_at"] == "2026-09-12T16:30:00Z"
    assert listing.model_dump(mode="json")["effective_at"] == "2026-09-12T14:30:00Z"
    assert listing.model_dump(mode="json")["known_at"] == "2026-09-12T16:30:00Z"
    assert identifier.model_dump(mode="json")["effective_at"] == "2026-09-12T14:30:00Z"
    assert identifier.model_dump(mode="json")["known_at"] == "2026-09-12T16:30:00Z"


def test_request_driven_mode_preserves_ordinary_local_instrument_reads(
    client, auth_headers, instrument, monkeypatch
):
    monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", True)

    def forbidden_transport(*_args, **_kwargs):
        raise AssertionError("ordinary local instrument reads must not query providers")

    monkeypatch.setattr(
        "app.routers.instruments.search_provider_instruments_async", forbidden_transport
    )
    monkeypatch.setattr("app.routers.instruments.get_provider_profile_async", forbidden_transport)
    monkeypatch.setattr("app.routers.instruments._create_from_provider", forbidden_transport)
    monkeypatch.setattr("app.routers.instruments._needs_52w_stats_refresh", lambda _row: False)

    search = client.get(
        "/api/v1/instruments/search", params={"q": instrument.symbol}, headers=auth_headers
    )
    assert search.status_code == 200, search.text
    assert any(row["symbol"] == instrument.symbol for row in search.json())

    detail = client.get(f"/api/v1/instruments/{instrument.symbol}", headers=auth_headers)
    assert detail.status_code == 200, detail.text

    unknown = client.get("/api/v1/instruments/UNKNOWN_ON_DEMAND", headers=auth_headers)
    assert unknown.status_code == 404
    unknown_search = client.get(
        "/api/v1/instruments/search",
        params={"q": "UNKNOWN_ON_DEMAND"},
        headers=auth_headers,
    )
    assert unknown_search.status_code == 200
    assert unknown_search.json() == []

    expression = client.post(
        "/api/v1/instruments/resolve-expression",
        json={"expression": f"=UNKNOWNONDEMAND/{instrument.symbol}"},
        headers=auth_headers,
    )
    assert expression.status_code == 404


def test_legacy_search_keeps_provider_discovery_when_request_driven_mode_is_disabled(
    client, auth_headers, monkeypatch
):
    monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", False)
    calls = 0

    async def _search(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return [
            {
                "symbol": "UNSEEDED_PROVIDER_SYMBOL",
                "name": "Provider Search Result",
                "exchange": "XNYS",
                "type": "EQUITY",
            }
        ]

    monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
    response = client.get(
        "/api/v1/instruments/search",
        params={"q": "UNSEEDED_PROVIDER_SYMBOL"},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()[0]["symbol"] == "UNSEEDED_PROVIDER_SYMBOL"
    assert calls == 1


class TestInstrumentAutoCreate:
    @pytest.mark.asyncio
    async def test_rejects_non_exact_provider_match(self, db, monkeypatch):
        async_db = AsyncSessionAdapter(db)

        async def _search(*_args, **_kwargs):
            return [
                {
                    "symbol": "CSCOII-USD",
                    "name": "Fake Coin",
                    "exchange": "CoinGecko",
                    "type": "CRYPTOCURRENCY",
                }
            ]

        async def _profile(*_args, **_kwargs):
            return InstrumentProfile(
                provider="coingecko",
                symbol="CSCOII-USD",
                canonical_symbol="CSCOII-USD",
                name="Fake Coin",
                quote_type="CRYPTOCURRENCY",
                listings=[ListingRecord(provider_symbol="CSCOII-USD", is_primary=True)],
            )

        async def _ingest(*_args, **_kwargs):
            raise AssertionError(
                "ingest_provider_profile should not be called for non-exact matches"
            )

        monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
        monkeypatch.setattr("app.routers.instruments.get_provider_profile_async", _profile)
        monkeypatch.setattr("app.routers.instruments.ingest_provider_profile", _ingest)

        created = await _create_from_provider("CSCOII", async_db)

        assert created is None
        assert db.query(Instrument).filter(Instrument.symbol == "CSCOII").one_or_none() is None

    @pytest.mark.asyncio
    async def test_creates_from_exact_provider_match(self, db, instrument_type, monkeypatch):
        async_db = AsyncSessionAdapter(db)
        seen_provider_name = None

        async def _search(*_args, **_kwargs):
            return [
                {
                    "symbol": "CSCO",
                    "name": "Cisco Systems",
                    "exchange": "NMS",
                    "type": "EQUITY",
                    "provider": "yfinance",
                }
            ]

        async def _profile(*_args, provider_name=None, **_kwargs):
            nonlocal seen_provider_name
            seen_provider_name = provider_name
            return InstrumentProfile(
                provider="yfinance",
                symbol="CSCO",
                canonical_symbol="CSCO",
                name="Cisco Systems",
                currency="USD",
                quote_type="EQUITY",
                exchange="NMS",
                listings=[
                    ListingRecord(provider_symbol="CSCO", exchange_code="NMS", is_primary=True)
                ],
            )

        async def _ingest(db_session, profile, **_kwargs):
            instrument = Instrument(
                symbol=profile.canonical_symbol,
                name=profile.name,
                currency=profile.currency,
                instrument_type_id=instrument_type.id,
                is_active=True,
            )
            db_session.add(instrument)
            await db_session.flush()
            return instrument

        monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
        monkeypatch.setattr("app.routers.instruments.get_provider_profile_async", _profile)
        monkeypatch.setattr("app.routers.instruments.ingest_provider_profile", _ingest)

        created = await _create_from_provider("CSCO", async_db)

        assert created is not None
        assert created.symbol == "CSCO"
        assert seen_provider_name == "yfinance"


class TestExplicitAcquireCanonicalIdentity:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("existing_scaffold", [False, True])
    async def test_promotes_scaffold_from_exact_authoritative_provider_profile(
        self, db, instrument_type, monkeypatch, existing_scaffold
    ):
        async_db = AsyncSessionAdapter(db)
        scaffold = None
        if existing_scaffold:
            scaffold = Instrument(
                symbol="OIH",
                name="OIH industry proxy ETF",
                currency="USD",
                instrument_type_id=instrument_type.id,
                is_active=True,
                identity_status="provisional",
                primary_identifier_type="composite_figi",
                primary_identifier_value="BBG000D02J82",
            )
            arca = Exchange(mic="ARCX", name="NYSE Arca")
            massive = DataSource(name="massive", is_active=True, config={})
            db.add_all([scaffold, arca, massive])
            db.flush()
            db.add_all(
                [
                    InstrumentIdentifier(
                        instrument_id=scaffold.id,
                        data_source_id=massive.id,
                        identifier_type=InstrumentIdentifierType.COMPOSITE_FIGI,
                        identifier_value="BBG000D02J82",
                        is_primary=True,
                        is_active=True,
                    ),
                    InstrumentProviderSymbol(
                        instrument_id=scaffold.id,
                        data_source_id=massive.id,
                        provider_symbol="OIH",
                        provider_exchange_code="ARCX",
                        provider_instrument_type="ETF",
                        is_primary=True,
                        is_active=True,
                    ),
                ]
            )
            db.add(
                InstrumentListing(
                    instrument_id=scaffold.id,
                    exchange_id=arca.id,
                    ticker="OIH",
                    currency="USD",
                    is_primary=True,
                    is_active=True,
                    source="massive",
                )
            )
            db.flush()

        async def _search(*_args, **_kwargs):
            return [
                {
                    "symbol": "OIH",
                    "name": "VanEck Oil Services ETF",
                    "exchange": "ARCX",
                    "type": "ETF",
                    "provider": "massive",
                }
            ]

        async def _profile(*_args, provider_name=None, **_kwargs):
            assert provider_name == "massive"
            return InstrumentProfile(
                provider="massive",
                symbol="OIH",
                canonical_symbol="OIH",
                name="VanEck Oil Services ETF",
                currency="USD",
                quote_type="ETF",
                exchange="ARCX",
                identifiers=[
                    IdentifierRecord(
                        identifier_type="composite_figi",
                        identifier_value="BBG000D02J82",
                        is_primary=True,
                    )
                ],
                listings=[
                    ListingRecord(
                        provider_symbol="OIH",
                        exchange_code="ARCX",
                        currency="USD",
                        provider_instrument_type="ETF",
                        is_primary=True,
                    )
                ],
            )

        monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
        monkeypatch.setattr("app.routers.instruments.get_provider_profile_async", _profile)
        monkeypatch.setattr(
            "app.services.instrument_mastering.ensure_external_identifier",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("explicit acquisition must not run fallback identifier lookup")
            ),
        )

        response = await acquire_instrument(
            InstrumentAcquireRequest(
                symbol="OIH",
                provider_candidate=ProviderCandidateBinding(
                    provider="massive", symbol="OIH", exchange="ARCX"
                ),
                request_id="test-oih-authoritative-profile",
            ),
            async_db,
        )

        assert response.status == "resolved"
        assert response.instrument is not None
        persisted = db.query(Instrument).filter(Instrument.symbol == "OIH").one()
        assert response.instrument.instrument_id == persisted.id
        if scaffold is not None:
            assert persisted.id == scaffold.id
        assert response.instrument.identity_status == "resolved"
        assert response.instrument.domain_key == "composite-figi:BBG000D02J82"
        assert response.instrument.primary_identifier_type == "composite_figi"
        assert response.instrument.primary_identifier_value == "BBG000D02J82"
        assert (
            db.query(InstrumentIdentifier)
            .filter(
                InstrumentIdentifier.instrument_id == response.instrument.instrument_id,
                InstrumentIdentifier.identifier_type == InstrumentIdentifierType.COMPOSITE_FIGI,
                InstrumentIdentifier.identifier_value == "BBG000D02J82",
                InstrumentIdentifier.is_active.is_(True),
            )
            .one_or_none()
            is not None
        )

    @pytest.mark.asyncio
    async def test_profile_identifier_owned_by_another_instrument_stays_quarantined(
        self, db, instrument_type, monkeypatch
    ):
        async_db = AsyncSessionAdapter(db)
        scaffold = Instrument(
            symbol="OIH",
            name="OIH industry proxy ETF",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
            identity_status="provisional",
        )
        owner = Instrument(
            symbol="OTHER",
            name="Existing owner",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
            identity_status="resolved",
            domain_key="composite-figi:BBG000D02J82",
            primary_identifier_type="composite_figi",
            primary_identifier_value="BBG000D02J82",
        )
        arca = Exchange(mic="ARCX", name="NYSE Arca")
        db.add_all([scaffold, owner, arca])
        db.flush()
        db.add(
            InstrumentListing(
                instrument_id=scaffold.id,
                exchange_id=arca.id,
                ticker="OIH",
                currency="USD",
                is_primary=True,
                is_active=True,
                source="massive",
            )
        )
        db.add(
            InstrumentIdentifier(
                instrument_id=owner.id,
                identifier_type=InstrumentIdentifierType.COMPOSITE_FIGI,
                identifier_value="BBG000D02J82",
                is_primary=True,
                is_active=True,
            )
        )
        db.flush()

        async def _search(*_args, **_kwargs):
            return [
                {
                    "symbol": "OIH",
                    "name": "VanEck Oil Services ETF",
                    "exchange": "ARCX",
                    "type": "ETF",
                    "provider": "massive",
                }
            ]

        async def _profile(*_args, **_kwargs):
            return InstrumentProfile(
                provider="massive",
                symbol="OIH",
                canonical_symbol="OIH",
                name="VanEck Oil Services ETF",
                currency="USD",
                quote_type="ETF",
                exchange="ARCX",
                identifiers=[
                    IdentifierRecord(
                        identifier_type="composite_figi",
                        identifier_value="BBG000D02J82",
                        is_primary=True,
                    )
                ],
                listings=[
                    ListingRecord(
                        provider_symbol="OIH",
                        exchange_code="ARCX",
                        currency="USD",
                        provider_instrument_type="ETF",
                        is_primary=True,
                    )
                ],
            )

        monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
        monkeypatch.setattr("app.routers.instruments.get_provider_profile_async", _profile)
        monkeypatch.setattr(
            "app.services.instrument_mastering.ensure_external_identifier",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("explicit acquisition must not run fallback identifier lookup")
            ),
        )

        response = await acquire_instrument(
            InstrumentAcquireRequest(
                symbol="OIH",
                provider_candidate=ProviderCandidateBinding(
                    provider="massive", symbol="OIH", exchange="ARCX"
                ),
                request_id="test-oih-colliding-profile",
            ),
            async_db,
        )

        db.refresh(scaffold)
        assert response.status == "identity_conflict"
        assert response.reason_code == "canonical_identity_not_fully_qualified"
        assert scaffold.identity_status == "quarantined"
        assert scaffold.domain_key is None
        assert owner.domain_key == "composite-figi:BBG000D02J82"
        assert (
            db.query(InstrumentIdentityQuarantine)
            .filter(
                InstrumentIdentityQuarantine.instrument_id == scaffold.id,
                InstrumentIdentityQuarantine.proposed_domain_key == "composite-figi:BBG000D02J82",
                InstrumentIdentityQuarantine.status == "pending",
            )
            .one_or_none()
            is not None
        )

    @pytest.mark.asyncio
    async def test_existing_conflicting_domain_key_is_preserved_before_ingestion(
        self, db, instrument_type, monkeypatch
    ):
        async_db = AsyncSessionAdapter(db)
        scaffold = Instrument(
            symbol="OIH",
            name="OIH industry proxy ETF",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
            identity_status="provisional",
            domain_key="composite-figi:BBG000OLDKEY01",
        )
        arca = Exchange(mic="ARCX", name="NYSE Arca")
        db.add_all([scaffold, arca])
        db.flush()
        db.add(
            InstrumentListing(
                instrument_id=scaffold.id,
                exchange_id=arca.id,
                ticker="OIH",
                currency="USD",
                is_primary=True,
                is_active=True,
                source="massive",
            )
        )
        db.flush()

        async def _search(*_args, **_kwargs):
            return [
                {
                    "symbol": "OIH",
                    "name": "VanEck Oil Services ETF",
                    "exchange": "ARCX",
                    "type": "ETF",
                    "provider": "massive",
                }
            ]

        async def _profile(*_args, **_kwargs):
            return InstrumentProfile(
                provider="massive",
                symbol="OIH",
                canonical_symbol="OIH",
                name="VanEck Oil Services ETF",
                currency="USD",
                quote_type="ETF",
                exchange="ARCX",
                identifiers=[
                    IdentifierRecord(
                        identifier_type="composite_figi",
                        identifier_value="BBG000D02J82",
                        is_primary=True,
                    )
                ],
                listings=[
                    ListingRecord(
                        provider_symbol="OIH",
                        exchange_code="ARCX",
                        provider_instrument_type="ETF",
                        is_primary=True,
                    )
                ],
            )

        async def _forbid_ingestion(*_args, **_kwargs):
            raise AssertionError("a conflicting canonical key must stop before profile ingestion")

        monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
        monkeypatch.setattr("app.routers.instruments.get_provider_profile_async", _profile)
        monkeypatch.setattr("app.routers.instruments.ingest_provider_profile", _forbid_ingestion)

        response = await acquire_instrument(
            InstrumentAcquireRequest(
                symbol="OIH",
                provider_candidate=ProviderCandidateBinding(
                    provider="massive", symbol="OIH", exchange="ARCX"
                ),
                request_id="test-oih-existing-domain-conflict",
            ),
            async_db,
        )

        db.refresh(scaffold)
        assert response.status == "identity_conflict"
        assert response.reason_code == "existing_placeholder_identity_conflict"
        assert scaffold.domain_key == "composite-figi:BBG000OLDKEY01"
        assert scaffold.identity_status == "provisional"

    @pytest.mark.asyncio
    async def test_missing_profile_listing_authority_does_not_promote_provisional_identity(
        self, db, instrument_type, monkeypatch
    ):
        async_db = AsyncSessionAdapter(db)
        scaffold = Instrument(
            symbol="OIH",
            name="OIH industry proxy ETF",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
            identity_status="provisional",
        )
        db.add(scaffold)
        db.flush()

        async def _search(*_args, **_kwargs):
            return [
                {
                    "symbol": "OIH",
                    "name": "VanEck Oil Services ETF",
                    "exchange": "ARCX",
                    "type": "ETF",
                    "provider": "massive",
                }
            ]

        async def _profile(*_args, **_kwargs):
            return InstrumentProfile(
                provider="massive",
                symbol="OIH",
                canonical_symbol="OIH",
                name="VanEck Oil Services ETF",
                currency="USD",
                quote_type="ETF",
                exchange="ARCX",
                identifiers=[
                    IdentifierRecord(
                        identifier_type="composite_figi",
                        identifier_value="BBG000D02J82",
                        is_primary=True,
                    )
                ],
                listings=[],
            )

        async def _forbid_ingestion(*_args, **_kwargs):
            raise AssertionError("a profile without listing authority must not be ingested")

        monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
        monkeypatch.setattr("app.routers.instruments.get_provider_profile_async", _profile)
        monkeypatch.setattr("app.routers.instruments.ingest_provider_profile", _forbid_ingestion)

        response = await acquire_instrument(
            InstrumentAcquireRequest(
                symbol="OIH",
                provider_candidate=ProviderCandidateBinding(
                    provider="massive", symbol="OIH", exchange="ARCX"
                ),
                request_id="test-oih-missing-listing-authority",
            ),
            async_db,
        )

        db.refresh(scaffold)
        assert response.status == "identity_conflict"
        assert response.reason_code == "stable_identity_or_listing_authority_missing"
        assert scaffold.identity_status == "provisional"
        assert scaffold.domain_key is None


def test_search_exchange_prefers_active_primary_listing_mic(instrument_type):
    instrument = Instrument(
        symbol="SPY",
        name="SPDR S&P 500 ETF Trust",
        instrument_type_id=instrument_type.id,
    )
    instrument.listings = [
        InstrumentListing(
            ticker="SPY",
            is_active=True,
            is_primary=True,
            exchange=Exchange(mic="ARCX", name="NYSE Arca"),
        ),
        InstrumentListing(
            ticker="SPY",
            is_active=False,
            is_primary=False,
            exchange=Exchange(mic="XNAS", name="Nasdaq"),
        ),
    ]

    assert _instrument_search_exchange(instrument) == "ARCX"


class TestInstrument52WStats:
    @pytest.mark.asyncio
    async def test_concurrent_refreshes_keep_one_stats_row(self, db, instrument):
        async_db = AsyncSessionAdapter(db)
        base = datetime.now(UTC) - timedelta(days=90)
        db.add_all(
            [
                OHLCVBar(
                    instrument_id=instrument.id,
                    timeframe=Timeframe.D1,
                    ts=base,
                    open=Decimal("150"),
                    high=Decimal("200"),
                    low=Decimal("145"),
                    close=Decimal("190"),
                    volume=Decimal("1000"),
                    is_adjusted=True,
                ),
                OHLCVBar(
                    instrument_id=instrument.id,
                    timeframe=Timeframe.D1,
                    ts=base + timedelta(days=30),
                    open=Decimal("140"),
                    high=Decimal("142"),
                    low=Decimal("120"),
                    close=Decimal("130"),
                    volume=Decimal("1000"),
                    is_adjusted=True,
                ),
            ]
        )
        db.flush()

        await asyncio.gather(
            _ensure_52w_stats(instrument, async_db),
            _ensure_52w_stats(instrument, async_db),
        )

        rows = (
            db.query(InstrumentStats).filter(InstrumentStats.instrument_id == instrument.id).all()
        )
        assert len(rows) == 1
        assert float(rows[0].week52_high) == 200.0
        assert float(rows[0].week52_low) == 120.0

    @pytest.mark.asyncio
    async def test_refreshes_provider_sourced_52w_provenance_from_ohlcv(self, db, instrument):
        async_db = AsyncSessionAdapter(db)
        stats = InstrumentStats(
            instrument_id=instrument.id,
            week52_high=Decimal("222.00"),
            week52_low=Decimal("111.00"),
            field_provenance={
                "week52_high": {"source": "yfinance", "observed_at": datetime.now(UTC).isoformat()},
                "week52_low": {"source": "yfinance", "observed_at": datetime.now(UTC).isoformat()},
            },
        )
        db.add(stats)
        instrument.stats = stats

        base = datetime.now(UTC) - timedelta(days=90)
        db.add_all(
            [
                OHLCVBar(
                    instrument_id=instrument.id,
                    timeframe=Timeframe.D1,
                    ts=base,
                    open=Decimal("150"),
                    high=Decimal("200"),
                    low=Decimal("145"),
                    close=Decimal("190"),
                    volume=Decimal("1000"),
                    is_adjusted=True,
                ),
                OHLCVBar(
                    instrument_id=instrument.id,
                    timeframe=Timeframe.D1,
                    ts=base + timedelta(days=30),
                    open=Decimal("140"),
                    high=Decimal("142"),
                    low=Decimal("120"),
                    close=Decimal("130"),
                    volume=Decimal("1000"),
                    is_adjusted=True,
                ),
            ]
        )
        db.flush()

        assert _needs_52w_stats_refresh(instrument) is True

        refreshed = await _ensure_52w_stats(instrument, async_db)

        assert float(refreshed.stats.week52_high) == 200.0
        assert float(refreshed.stats.week52_low) == 120.0
        assert refreshed.stats.field_provenance["week52_high"]["source"] == "internal_ohlcv_52w"
        fetched_at = refreshed.stats.field_provenance["week52_high"]["fetched_at"]
        fetched_at_datetime = datetime.fromisoformat(fetched_at)
        assert fetched_at_datetime.tzinfo is not None
        assert fetched_at_datetime.utcoffset() == timedelta(0)
        assert (
            refreshed.stats.field_provenance["week52_high"]["observed_at"]
            == base.date().isoformat()
        )
        assert (
            refreshed.stats.field_provenance["week52_low"]["observed_at"]
            == (base + timedelta(days=30)).date().isoformat()
        )

    def test_skips_52w_refresh_when_internal_provenance_already_has_occurrence_dates(
        self, instrument
    ):
        instrument.stats = InstrumentStats(
            instrument_id=instrument.id,
            week52_high=Decimal("222.00"),
            week52_low=Decimal("111.00"),
            field_provenance={
                "week52_high": {
                    "source": "internal_ohlcv_52w",
                    "observed_at": "2025-02-01T00:00:00+00:00",
                },
                "week52_low": {
                    "source": "internal_ohlcv_52w",
                    "observed_at": "2025-01-10T00:00:00+00:00",
                },
            },
        )

        assert _needs_52w_stats_refresh(instrument) is False
