from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import Table, delete, inspect, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401 - register the real mapped metadata and FK targets
from app.database import Base
from app.models.asset_class import AssetClass, InstrumentType
from app.models.data_source import DataSource
from app.models.exchange import Exchange
from app.models.instrument import Instrument
from app.models.market_data_foundation import AdjustmentBasis, Issuer, MarketSeries
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_observation import DatasetStatus, InstrumentDatasetState
from app.strategy_lab_v2.capabilities import CapabilityRequirement
from app.strategy_lab_v2.contracts import AdjustmentMode, EventGranularity, ProductClass
from app.strategy_lab_v2.provider_preflight import ProviderLocalCapabilityEvidenceReader
from app.strategy_lab_v2.provider_series_contract import (
    ProviderSeriesCapabilityEvidence,
    provider_series_capability_cell,
    verify_provider_series_binding,
)

_READER_TABLES = (
    InstrumentType.__table__,
    Instrument.__table__,
    MarketSeries.__table__,
    InstrumentDatasetState.__table__,
    OHLCVBar.__table__,
    DataSource.__table__,
    Exchange.__table__,
)
_EXPECTED_FK_CLOSURE = {
    "asset_class",
    "data_source",
    "exchange",
    "instrument",
    "instrument_dataset_state",
    "instrument_type",
    "issuer",
    "market_series",
    "ohlcv_bar",
}
_NOW = datetime(2026, 10, 22, 5, 0, tzinfo=UTC)
_START = datetime(2024, 1, 2, tzinfo=UTC)
_END = datetime(2024, 1, 6, tzinfo=UTC)
_INSTRUMENT_KEY = "US:EQ:STRATEGY-READER-TEST"


def _mapped_reader_fk_closure() -> tuple[Table, ...]:
    tables_by_key: dict[str, Table] = {}
    pending = list(_READER_TABLES)
    while pending:
        table = pending.pop()
        if table.key in tables_by_key:
            continue
        tables_by_key[table.key] = table
        pending.extend(foreign_key.column.table for foreign_key in table.foreign_keys)
    return tuple(tables_by_key.values())


def test_reader_fixture_is_the_actual_mapped_foreign_key_closure() -> None:
    closure = _mapped_reader_fk_closure()
    assert {table.name for table in closure} == _EXPECTED_FK_CLOSURE
    assert {table.name for table in _READER_TABLES} <= _EXPECTED_FK_CLOSURE


def _async_postgres_url(raw_url: str) -> str:
    if raw_url.startswith("postgresql+asyncpg://"):
        return raw_url
    if raw_url.startswith("postgresql+psycopg2://"):
        return raw_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    raise ValueError("integration database URL must use PostgreSQL")


@pytest_asyncio.fixture
async def provider_reader_database(
    request: pytest.FixtureRequest,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Create the actual reader tables and all mapped FK dependencies.

    A reviewed local fixture may set STRATEGY_PROVIDER_READER_DATABASE_URL.
    Normal backend integration falls back to the repository's existing
    TEST_DATABASE_URL / pg_container fixtures; this is not opt-in skipped.
    """

    database_url = os.getenv("STRATEGY_PROVIDER_READER_DATABASE_URL")
    if not database_url:
        database_url = request.getfixturevalue("test_database_url")
    if not database_url:
        pg_container = request.getfixturevalue("pg_container")
        database_url = pg_container.get_connection_url()

    schema = f"strategy_provider_reader_{uuid.uuid4().hex[:12]}"
    engine = create_async_engine(
        _async_postgres_url(database_url),
        connect_args={"server_settings": {"search_path": schema}},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    schema_created = False
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            schema_created = True
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection.execution_options(schema_translate_map={None: schema}),
                    tables=_mapped_reader_fk_closure(),
                )
            )
            actual_tables = await connection.run_sync(
                lambda sync_connection: set(inspect(sync_connection).get_table_names(schema=schema))
            )
            assert actual_tables == _EXPECTED_FK_CLOSURE
        async with sessions.begin() as session:
            session.add_all(
                (
                    AssetClass(id=1, name="Equity", description="reader integration fixture"),
                    InstrumentType(
                        id=1,
                        asset_class_id=1,
                        name="Stock",
                        description="reader integration fixture",
                    ),
                    Issuer(
                        id=1,
                        domain_key="US:ISSUER:STRATEGY-READER-TEST",
                        legal_name="Strategy reader test issuer",
                        provenance={"fixture": "local-postgres"},
                    ),
                    DataSource(
                        id=1,
                        name="strategy-reader-fixture",
                        is_active=True,
                        config={},
                        supported_capabilities=[],
                    ),
                    Exchange(
                        id=1,
                        mic="XNYS",
                        name="New York Stock Exchange",
                        country_code="US",
                        timezone="America/New_York",
                    ),
                )
            )
            await session.flush()
            session.add(
                Instrument(
                    id=1,
                    instrument_type_id=1,
                    symbol="STRAT",
                    name="Strategy reader test equity",
                    currency="USD",
                    domain_key=_INSTRUMENT_KEY,
                    identity_status="resolved",
                    issuer_id=1,
                    is_active=True,
                    is_synthetic=False,
                )
            )
            await session.flush()
            session.add(
                MarketSeries(
                    id=1,
                    instrument_id=1,
                    exchange_id=1,
                    data_source_id=1,
                    feed_scope="consolidated",
                    session_code="regular",
                    timeframe="D1",
                    adjustment_basis=AdjustmentBasis.RAW,
                    adjustment_version="raw-v1",
                    is_canonical=True,
                    is_active=True,
                    source_series_key="strategy-reader-fixture:D1:raw-v1",
                    provenance={
                        "provider": "strategy-reader-fixture",
                        "corporate_action_semantics": "raw_unadjusted",
                    },
                )
            )
            session.add(
                InstrumentDatasetState(
                    id=1,
                    instrument_id=1,
                    data_source_id=1,
                    dataset_type="ohlcv",
                    dataset_key="D1:raw",
                    status=DatasetStatus.FRESH,
                    coverage_start=_START,
                    coverage_end=datetime(2024, 1, 5, 15, tzinfo=UTC),
                    observed_at=_NOW,
                    fetched_at=_NOW,
                    stale_after=datetime(2026, 10, 23, tzinfo=UTC),
                    snapshot_hash="fixture-snapshot-v1",
                )
            )
            session.add_all(
                OHLCVBar(
                    id=index,
                    instrument_id=1,
                    data_source_id=1,
                    market_series_id=1,
                    timeframe=Timeframe.D1,
                    ts=datetime(2024, 1, day, 14, 30, tzinfo=UTC),
                    session="regular",
                    scope_key="provider:strategy-reader-fixture:D1:raw-v1",
                    open=Decimal("100.0") + day,
                    high=Decimal("102.0") + day,
                    low=Decimal("99.0") + day,
                    close=Decimal("101.0") + day,
                    volume=Decimal("1000"),
                    is_adjusted=False,
                    adjustment_basis="raw",
                    adjustment_version="raw-v1",
                    is_derived=False,
                    provenance={"fixture": "local-postgres"},
                )
                for index, day in enumerate((2, 3, 4, 5), start=1)
            )
        yield sessions
    finally:
        try:
            if schema_created:
                async with engine.begin() as connection:
                    await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        finally:
            await engine.dispose()


def _requirement(
    *,
    instrument_id: str = _INSTRUMENT_KEY,
    product_class: ProductClass = ProductClass.EQUITY,
    feed: str = "consolidated",
) -> CapabilityRequirement:
    return CapabilityRequirement(
        instrument_id=instrument_id,
        product_class=product_class,
        event_granularity=EventGranularity.BAR,
        event_type="ohlcv",
        timeframe="1d",
        start=_START,
        end=_END,
        adjustment=AdjustmentMode.RAW,
        session="regular",
        feed=feed,
        execution_model="market",
        account_model="cash",
        corporate_action_semantics="raw_unadjusted",
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_provider_local_capability_reader_reads_and_revokes_exact_persisted_evidence(
    provider_reader_database: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def forbidden_http_client(*_args: object, **_kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise AssertionError("local capability evidence must not make provider HTTP calls")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden_http_client)
    reader = ProviderLocalCapabilityEvidenceReader(
        provider_reader_database,
        execution_models=("market",),
        account_models=("cash",),
        clock=lambda: _NOW,
    )

    async def resolve(
        requirement: CapabilityRequirement,
    ) -> tuple[ProviderSeriesCapabilityEvidence, ...]:
        return await reader(
            principal="owner-1",
            request_id="provider-reader-postgres",
            idempotency_key="provider-reader-postgres",
            requirements=(requirement,),
        )

    requirement = _requirement()

    def admitted(
        evidence_rows: tuple[ProviderSeriesCapabilityEvidence, ...],
    ) -> ProviderSeriesCapabilityEvidence:
        assert len(evidence_rows) == 1
        evidence = evidence_rows[0]
        binding = verify_provider_series_binding(
            evidence.instrument,
            evidence.series,
            evidence.manifest,
        )
        assert binding.verified, f"provider binding mismatches: {binding.mismatches!r}"
        cell = provider_series_capability_cell(evidence, requirement)
        assert cell is not None, f"no capability cell; binding={binding.mismatches!r}"
        assert cell.execution_models == frozenset({"market"})
        assert cell.account_models == frozenset({"cash"})
        return evidence

    async def assert_current_evidence() -> ProviderSeriesCapabilityEvidence:
        return admitted(await resolve(requirement))

    evidence = await assert_current_evidence()
    assert evidence.instrument.domain_key == _INSTRUMENT_KEY
    assert evidence.series.id == 1
    assert evidence.manifest.coverage_evidence_digest
    assert evidence.manifest.content_digest
    assert evidence.coverage_assessment.status.value == "ready"
    original_content_digest = evidence.manifest.content_digest

    # A changed persisted bar remains readable but must produce a different
    # immutable input fingerprint; the reader never substitutes another series.
    async with provider_reader_database.begin() as session:
        await session.execute(
            update(OHLCVBar)
            .where(OHLCVBar.id == 1)
            .values(
                open=Decimal("111"),
                high=Decimal("113"),
                low=Decimal("110"),
                close=Decimal("112"),
            )
        )
    changed = await assert_current_evidence()
    assert changed.manifest.content_digest != original_content_digest
    changed_content_digest = changed.manifest.content_digest

    # Removing an exact persisted bar must revoke the range; restoring that
    # same row readmits the same immutable content fingerprint.
    async with provider_reader_database.begin() as session:
        await session.execute(delete(OHLCVBar).where(OHLCVBar.id == 4))
    assert await resolve(requirement) == ()
    async with provider_reader_database.begin() as session:
        session.add(
            OHLCVBar(
                id=4,
                instrument_id=1,
                data_source_id=1,
                market_series_id=1,
                timeframe=Timeframe.D1,
                ts=datetime(2024, 1, 5, 14, 30, tzinfo=UTC),
                session="regular",
                scope_key="provider:strategy-reader-fixture:D1:raw-v1",
                open=Decimal("105.0"),
                high=Decimal("107.0"),
                low=Decimal("104.0"),
                close=Decimal("106.0"),
                volume=Decimal("1000"),
                is_adjusted=False,
                adjustment_basis="raw",
                adjustment_version="raw-v1",
                is_derived=False,
                provenance={"fixture": "local-postgres"},
            )
        )
    restored = await assert_current_evidence()
    assert restored.manifest.content_digest == changed_content_digest

    # Isolate each denial by proving restored state admitted before applying the
    # next persisted mutation.
    async with provider_reader_database.begin() as session:
        await session.execute(update(DataSource).where(DataSource.id == 1).values(is_active=False))
    assert await resolve(requirement) == ()
    async with provider_reader_database.begin() as session:
        await session.execute(update(DataSource).where(DataSource.id == 1).values(is_active=True))
    await assert_current_evidence()

    async with provider_reader_database.begin() as session:
        await session.execute(
            update(MarketSeries).where(MarketSeries.id == 1).values(is_active=False)
        )
    assert await resolve(requirement) == ()
    async with provider_reader_database.begin() as session:
        await session.execute(
            update(MarketSeries).where(MarketSeries.id == 1).values(is_active=True)
        )
    await assert_current_evidence()

    async with provider_reader_database.begin() as session:
        await session.execute(
            update(Instrument).where(Instrument.id == 1).values(identity_status="provisional")
        )
    assert await resolve(requirement) == ()
    async with provider_reader_database.begin() as session:
        await session.execute(
            update(Instrument).where(Instrument.id == 1).values(identity_status="resolved")
        )
    await assert_current_evidence()

    async with provider_reader_database.begin() as session:
        await session.execute(update(Exchange).where(Exchange.id == 1).values(mic="XNAS"))
    assert await resolve(requirement) == ()
    async with provider_reader_database.begin() as session:
        await session.execute(update(Exchange).where(Exchange.id == 1).values(mic="XNYS"))
    await assert_current_evidence()

    async with provider_reader_database.begin() as session:
        await session.execute(
            update(OHLCVBar).where(OHLCVBar.id == 4).values(timeframe=Timeframe.M5)
        )
    assert await resolve(requirement) == ()
    async with provider_reader_database.begin() as session:
        await session.execute(
            update(OHLCVBar).where(OHLCVBar.id == 4).values(timeframe=Timeframe.D1)
        )
    await assert_current_evidence()

    async with provider_reader_database.begin() as session:
        await session.execute(
            update(InstrumentDatasetState)
            .where(InstrumentDatasetState.id == 1)
            .values(status=DatasetStatus.STALE)
        )
    assert await resolve(requirement) == ()

    async with provider_reader_database.begin() as session:
        await session.execute(
            update(InstrumentDatasetState)
            .where(InstrumentDatasetState.id == 1)
            .values(status=DatasetStatus.FRESH)
        )
    await assert_current_evidence()

    # A fresh label alone cannot admit a row whose explicit stale_after expired.
    async with provider_reader_database.begin() as session:
        await session.execute(
            update(InstrumentDatasetState)
            .where(InstrumentDatasetState.id == 1)
            .values(stale_after=_NOW)
        )
    expired = await resolve(requirement)
    assert len(expired) == 1
    assert provider_series_capability_cell(expired[0], requirement) is None
    async with provider_reader_database.begin() as session:
        await session.execute(
            update(InstrumentDatasetState)
            .where(InstrumentDatasetState.id == 1)
            .values(stale_after=datetime(2026, 10, 23, tzinfo=UTC))
        )
    await assert_current_evidence()

    # Unsupported product/feed claims do not gain evidence through a valid
    # persisted equity series.
    assert await resolve(_requirement(product_class=ProductClass.CRYPTO)) == ()
    assert await resolve(_requirement(feed="unconfigured-feed")) == ()
    assert calls == 0
