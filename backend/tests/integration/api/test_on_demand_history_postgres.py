from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import Table, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401 - register mapped tables and foreign-key targets
from app.config import settings
from app.database import Base
from app.models.asset_class import AssetClass, InstrumentType
from app.models.data_source import DataSource
from app.models.exchange import Exchange
from app.models.instrument import EquityDetail, Instrument, OptionDetail
from app.models.instrument_identity import (
    InstrumentIdentifier,
    InstrumentIdentifierType,
    InstrumentProviderSymbol,
)
from app.models.instrument_stats import InstrumentStats
from app.models.listing import InstrumentListing
from app.models.market_data_foundation import (
    AdjustmentBasis,
    ExchangeSessionRule,
    InstrumentIdentityQuarantine,
    InstrumentIdentityQuarantineObservation,
    MarketSeries,
    MarketSeriesDefault,
)
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_observation import InstrumentProfileSnapshot
from app.models.synthetic_constituent import SyntheticConstituent
from app.routers import instruments as instruments_router
from app.schemas.instrument_acquisition import (
    HistoryAcquisitionRequest,
    InstrumentAcquireRequest,
    ProviderCandidateBinding,
)
from app.services import provider_runtime

_TABLES = (
    AssetClass.__table__,
    InstrumentType.__table__,
    Instrument.__table__,
    DataSource.__table__,
    Exchange.__table__,
    InstrumentListing.__table__,
    MarketSeries.__table__,
    MarketSeriesDefault.__table__,
    OHLCVBar.__table__,
    ExchangeSessionRule.__table__,
    InstrumentIdentifier.__table__,
    InstrumentProviderSymbol.__table__,
    InstrumentProfileSnapshot.__table__,
    InstrumentIdentityQuarantine.__table__,
    InstrumentIdentityQuarantineObservation.__table__,
    InstrumentStats.__table__,
    EquityDetail.__table__,
    OptionDetail.__table__,
    SyntheticConstituent.__table__,
)


def _table_fk_closure() -> tuple[Table, ...]:
    tables: dict[str, Table] = {}
    pending = list(_TABLES)
    while pending:
        table = pending.pop()
        if table.key in tables:
            continue
        tables[table.key] = table
        pending.extend(fk.column.table for fk in table.foreign_keys)
    return tuple(tables.values())


def _async_postgres_url(raw_url: str) -> str:
    if raw_url.startswith("postgresql+asyncpg://"):
        return raw_url
    if raw_url.startswith("postgresql+psycopg2://"):
        return raw_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    raise ValueError("integration database URL must use PostgreSQL")


@pytest_asyncio.fixture
async def on_demand_history_database(
    request: pytest.FixtureRequest,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    database_url = os.getenv("PROVIDER_ON_DEMAND_TEST_DATABASE_URL")
    if not database_url:
        database_url = request.getfixturevalue("test_database_url")
    if not database_url:
        database_url = request.getfixturevalue("pg_container").get_connection_url()

    schema = f"provider_on_demand_{uuid.uuid4().hex[:12]}"
    bootstrap_engine = create_async_engine(_async_postgres_url(database_url))
    schema_created = False
    test_engine = None
    try:
        async with bootstrap_engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            schema_created = True
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection.execution_options(schema_translate_map={None: schema}),
                    tables=_table_fk_closure(),
                )
            )
        test_engine = create_async_engine(
            _async_postgres_url(database_url),
            connect_args={"server_settings": {"search_path": schema}},
        )
        yield async_sessionmaker(test_engine, expire_on_commit=False)
    finally:
        if test_engine is not None:
            await test_engine.dispose()
        if schema_created:
            async with bootstrap_engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await bootstrap_engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_explicit_history_reads_and_returns_only_persisted_default_series(
    on_demand_history_database, monkeypatch
):
    monkeypatch.setattr(settings, "PROVIDER_ON_DEMAND_MAX_REQUESTED_BARS", 10)
    monkeypatch.setattr(settings, "PROVIDER_ON_DEMAND_MAX_MISSING_SLICES", 2)
    start = datetime(2026, 1, 5, 14, 30, tzinfo=UTC)
    end = start + timedelta(days=1)

    async with on_demand_history_database.begin() as setup_db:
        setup_db.add_all(
            [
                AssetClass(id=1, name="Equity", description="fixture"),
                InstrumentType(id=1, asset_class_id=1, name="ETF", description="fixture"),
                Exchange(
                    id=1,
                    mic="XNYS",
                    name="Test Exchange",
                    country_code="US",
                    timezone="America/New_York",
                ),
                DataSource(
                    id=1,
                    name="massive",
                    is_active=True,
                    config={},
                    supported_capabilities=["price_history"],
                ),
            ]
        )
        await setup_db.flush()
        instrument = Instrument(
            id=1,
            instrument_type_id=1,
            symbol="OIH",
            name="Synthetic test ETF",
            currency="USD",
            domain_key="TEST:ETF:ONDEMAND-OIH",
            identity_status="resolved",
            primary_identifier_type="FIGI",
            primary_identifier_value="BBG000ONDEMAND",
            is_active=True,
            is_synthetic=False,
        )
        setup_db.add(instrument)
        await setup_db.flush()
        setup_db.add(
            InstrumentListing(
                instrument_id=instrument.id,
                exchange_id=1,
                ticker="OIH",
                currency="USD",
                is_primary=True,
                is_active=True,
                source="integration-fixture",
            )
        )
        selected = MarketSeries(
            id=1,
            instrument_id=instrument.id,
            exchange_id=1,
            data_source_id=1,
            feed_scope="selected",
            session_code="regular",
            timeframe="D1",
            adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
            adjustment_version="selected-v1",
            is_canonical=True,
            is_active=True,
            source_series_key="fixture:selected:D1",
            provenance={"fixture": "selected-default"},
        )
        alternate = MarketSeries(
            id=2,
            instrument_id=instrument.id,
            exchange_id=1,
            data_source_id=1,
            feed_scope="alternate",
            session_code="regular",
            timeframe="D1",
            adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
            adjustment_version="alternate-v1",
            is_canonical=True,
            is_active=True,
            source_series_key="fixture:alternate:D1",
            provenance={"fixture": "alternate"},
        )
        setup_db.add_all([selected, alternate])
        await setup_db.flush()
        setup_db.add(
            MarketSeriesDefault(
                instrument_id=instrument.id,
                timeframe="D1",
                is_adjusted=True,
                market_series_id=selected.id,
                selection_reason="integration-test-selected-default",
                provenance={"fixture": "selected-default"},
            )
        )
        for offset in range(2):
            setup_db.add(
                OHLCVBar(
                    instrument_id=instrument.id,
                    data_source_id=1,
                    market_series_id=alternate.id,
                    timeframe=Timeframe.D1,
                    ts=start + timedelta(days=offset),
                    scope_key=f"series:{alternate.id}:regular",
                    open=Decimal("11"),
                    high=Decimal("12"),
                    low=Decimal("10"),
                    close=Decimal("11"),
                    volume=Decimal("101"),
                    is_adjusted=True,
                    adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED.value,
                    adjustment_version="alternate-v1",
                    provenance={"fixture": "alternate-only"},
                )
            )
        await setup_db.flush()

    # The real get_db dependency yields a plain request-scoped AsyncSession.
    # Setup is committed above; use a fresh session for the endpoint because
    # the production acquisition path commits before its persisted readback.
    async with on_demand_history_database() as db:
        fetch_scopes: list[frozenset[str] | None] = []

        async def persist_selected_default_rows(*_args, **_kwargs):
            scope = provider_runtime._EXPLICIT_ACQUISITION_CONTEXT.get()
            fetch_scopes.append(scope.provider_names if scope is not None else None)
            for offset in range(2):
                db.add(
                    OHLCVBar(
                        instrument_id=instrument.id,
                        data_source_id=1,
                        market_series_id=selected.id,
                        timeframe=Timeframe.D1,
                        ts=start + timedelta(days=offset),
                        scope_key=f"series:{selected.id}:regular",
                        open=Decimal("20"),
                        high=Decimal("21"),
                        low=Decimal("19"),
                        close=Decimal("20"),
                        volume=Decimal("200"),
                        is_adjusted=True,
                        adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED.value,
                        adjustment_version="selected-v1",
                        provenance={"fixture": "persisted-selected"},
                    )
                )
            await db.flush()
            # The real fetch_ohlcv implementation commits successful provider
            # rows before the acquisition endpoint performs persisted readback.
            await db.commit()
            return []

        monkeypatch.setattr(instruments_router, "fetch_ohlcv", persist_selected_default_rows)
        response = await instruments_router.acquire_instrument_history(
            instrument.id,
            HistoryAcquisitionRequest(
                timeframe=Timeframe.D1,
                adjusted=True,
                start=start,
                end=end,
                source_provider="massive",
                request_id="postgres-selected-default-integration",
            ),
            db=db,
            current_user=SimpleNamespace(id=1),
        )
        assert response.status == "complete"
        assert response.coverage.bar_count == 2
        assert [item.close for item in response.bars] == [20.0, 20.0]
        assert fetch_scopes == [frozenset({"massive"})]

    async with on_demand_history_database() as verify_db:
        persisted = (
            (
                await verify_db.execute(
                    # The alternate series remains stored, but the selected default
                    # is the only series exposed by the acquisition response.
                    select(OHLCVBar).where(
                        OHLCVBar.instrument_id == 1,
                        OHLCVBar.timeframe == Timeframe.D1,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(persisted) == 4
        assert sum(1 for bar in persisted if bar.market_series_id == 1) == 2
        assert sum(1 for bar in persisted if bar.market_series_id == 2) == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_explicit_acquire_commits_authoritative_identity_for_provisional_oih_scaffold(
    on_demand_history_database, monkeypatch
):
    from app.models.asset_class import AssetClass, InstrumentType
    from app.models.instrument import Instrument
    from app.models.instrument_identity import (
        InstrumentIdentifier,
        InstrumentProviderSymbol,
    )
    from app.models.listing import InstrumentListing
    from app.providers.base import IdentifierRecord, InstrumentProfile, ListingRecord
    from app.routers import instruments as instruments_router
    from app.services import instrument_mastering

    session_factory = on_demand_history_database
    async with session_factory.begin() as setup_db:
        setup_db.add_all(
            [
                AssetClass(id=1, name="Equity", description="fixture"),
                InstrumentType(id=1, asset_class_id=1, name="ETF", description="fixture"),
                Exchange(id=1, mic="ARCX", name="NYSE Arca", country_code="US"),
                DataSource(
                    id=1,
                    name="massive",
                    is_active=True,
                    config={},
                    supported_capabilities=["instrument_metadata", "instrument_search"],
                ),
            ]
        )
        await setup_db.flush()
        scaffold = Instrument(
            id=1,
            instrument_type_id=1,
            symbol="OIH",
            name="OIH industry proxy ETF",
            currency="USD",
            identity_status="provisional",
            primary_identifier_type="composite_figi",
            primary_identifier_value="BBG000D02J82",
            is_active=True,
            is_synthetic=False,
        )
        setup_db.add(scaffold)
        await setup_db.flush()
        setup_db.add_all(
            [
                InstrumentListing(
                    instrument_id=scaffold.id,
                    exchange_id=1,
                    ticker="OIH",
                    currency="USD",
                    is_primary=True,
                    is_active=True,
                    source="massive",
                ),
                InstrumentIdentifier(
                    instrument_id=scaffold.id,
                    data_source_id=1,
                    identifier_type=InstrumentIdentifierType.COMPOSITE_FIGI,
                    identifier_value="BBG000D02J82",
                    is_primary=True,
                    is_active=True,
                ),
                InstrumentProviderSymbol(
                    instrument_id=scaffold.id,
                    data_source_id=1,
                    provider_symbol="OIH",
                    provider_exchange_code="ARCX",
                    provider_instrument_type="ETF",
                    is_primary=True,
                    is_active=True,
                ),
            ]
        )

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

    async def _forbid_optional_identifier_lookup(*_args, **_kwargs):
        raise AssertionError("explicit acquisition must not use external identifier fallback")

    async def _no_provider_chain(*_args, **_kwargs):
        return []

    monkeypatch.setattr(instruments_router, "search_provider_instruments_async", _search)
    monkeypatch.setattr(instruments_router, "get_provider_profile_async", _profile)
    monkeypatch.setattr(
        instrument_mastering, "ensure_external_identifier", _forbid_optional_identifier_lookup
    )
    monkeypatch.setattr(instrument_mastering, "resolve_provider_chain", _no_provider_chain)

    async with session_factory() as request_db:
        response = await instruments_router.acquire_instrument(
            InstrumentAcquireRequest(
                symbol="OIH",
                provider_candidate=ProviderCandidateBinding(
                    provider="massive", symbol="OIH", exchange="ARCX"
                ),
                request_id="integration-oih-authoritative-profile",
            ),
            request_db,
            current_user=None,
        )

    assert response.status == "resolved"
    assert response.instrument is not None
    assert response.instrument.instrument_id == 1
    assert response.instrument.identity_status == "resolved"
    assert response.instrument.domain_key == "composite-figi:BBG000D02J82"
    async with session_factory() as verify_db:
        persisted = await verify_db.get(Instrument, 1)
        assert persisted is not None
        assert persisted.identity_status == "resolved"
        assert persisted.domain_key == "composite-figi:BBG000D02J82"
        assert persisted.primary_identifier_type == "composite_figi"
        assert persisted.primary_identifier_value == "BBG000D02J82"
        identifier = (
            await verify_db.execute(
                select(InstrumentIdentifier).where(
                    InstrumentIdentifier.instrument_id == persisted.id,
                    InstrumentIdentifier.identifier_type == InstrumentIdentifierType.COMPOSITE_FIGI,
                    InstrumentIdentifier.identifier_value == "BBG000D02J82",
                    InstrumentIdentifier.is_active.is_(True),
                )
            )
        ).scalar_one()
        assert identifier.is_primary is True
