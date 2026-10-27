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
from app.models.instrument import Instrument
from app.models.listing import InstrumentListing
from app.models.market_data_foundation import (
    AdjustmentBasis,
    MarketSeries,
    MarketSeriesDefault,
)
from app.models.ohlcv import OHLCVBar, Timeframe
from app.routers import instruments as instruments_router
from app.schemas.instrument_acquisition import HistoryAcquisitionRequest
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

    async with on_demand_history_database.begin() as db:
        db.add_all(
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
        await db.flush()
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
        db.add(instrument)
        await db.flush()
        db.add(
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
        db.add_all([selected, alternate])
        await db.flush()
        db.add(
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
            db.add(
                OHLCVBar(
                    instrument_id=instrument.id,
                    data_source_id=1,
                    market_series_id=alternate.id,
                    timeframe=Timeframe.D1,
                    ts=start + timedelta(days=offset),
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
        await db.flush()

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
