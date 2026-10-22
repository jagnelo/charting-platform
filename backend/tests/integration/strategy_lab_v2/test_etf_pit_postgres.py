from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import Table, inspect, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401 - register the real mapped metadata and FK targets
from app.database import Base
from app.models.asset_class import AssetClass, InstrumentType
from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
from app.models.instrument import Instrument
from app.strategy_lab_v2.contracts import (
    DataSnapshot,
    ETFMembershipReference,
    ExperimentDefinition,
    RunAttempt,
    ScientificTrial,
)
from app.strategy_lab_v2.etf_pit import (
    LocalETFMembershipReader,
    resolve_etf_pit_membership,
)
from app.strategy_lab_v2.tests.test_nautilus_trial_assembly import _inputs
from app.strategy_lab_v2.tests.test_trial_hydration import MemoryDomainReader
from app.strategy_lab_v2.trial_hydration import (
    NautilusTrialDomainHydrator,
    TrialDomainHydrationError,
)

_READER_TABLES = (
    InstrumentType.__table__,
    Instrument.__table__,
    ETFProfile.__table__,
    ETFHoldingsSnapshot.__table__,
    ETFHolding.__table__,
)
_READER_TABLE_NAMES = {table.name for table in _READER_TABLES}
_EXPECTED_FK_CLOSURE = {
    "asset_class",
    "data_source",
    "etf_holding",
    "etf_holdings_raw_artifact",
    "etf_holdings_snapshot",
    "etf_profile",
    "instrument",
    "instrument_type",
    "issuer",
}
_DECISION = datetime(2025, 3, 3, 18, tzinfo=UTC)
_ETF_KEY = "US:ETF:SPY"


def _mapped_reader_fk_closure() -> tuple[Table, ...]:
    tables_by_key = {}
    pending = list(_READER_TABLES)
    while pending:
        table = pending.pop()
        if table.key in tables_by_key:
            continue
        tables_by_key[table.key] = table
        pending.extend(foreign_key.column.table for foreign_key in table.foreign_keys)
    return tuple(tables_by_key.values())


def test_reader_fixture_uses_only_actual_mapped_foreign_key_closure() -> None:
    closure = _mapped_reader_fk_closure()
    assert {table.name for table in closure} == _EXPECTED_FK_CLOSURE
    assert _READER_TABLE_NAMES <= {table.name for table in closure}


@pytest_asyncio.fixture
async def etf_pit_database(
    request: pytest.FixtureRequest,
) -> AsyncIterator[tuple[async_sessionmaker[AsyncSession], str]]:
    """Create the reader tables and their exact mapped FK dependency closure.

    Prefer the explicitly assigned local database. Normal backend integration
    lazily reuses TEST_DATABASE_URL or the repository's existing pg_container.
    The generated schema is unique per test and contains no unrelated tables;
    original mapped constraints, indexes, defaults and FK edges are retained.
    """

    database_url = os.getenv("STRATEGY_ETF_PIT_DATABASE_URL")
    if not database_url:
        database_url = request.getfixturevalue("test_database_url")
    if not database_url:
        pg_container = request.getfixturevalue("pg_container")
        database_url = pg_container.get_connection_url()
    if database_url.startswith("postgresql+psycopg2://"):
        database_url = database_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    schema = f"strategy_etf_pit_{uuid.uuid4().hex[:12]}"
    engine = create_async_engine(
        database_url,
        connect_args={"server_settings": {"search_path": schema}},
    )
    fixture_tables = _mapped_reader_fk_closure()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection.execution_options(schema_translate_map={None: schema}),
                    tables=fixture_tables,
                )
            )
            actual_tables = await connection.run_sync(
                lambda sync_connection: set(inspect(sync_connection).get_table_names(schema=schema))
            )
            assert actual_tables == _EXPECTED_FK_CLOSURE
        yield sessions, schema
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()


def _snapshot(
    *,
    snapshot_id: int,
    composition_date: date,
    known_at: datetime,
    constituent_id: int,
) -> tuple[ETFHoldingsSnapshot, ETFHolding]:
    snapshot = ETFHoldingsSnapshot(
        id=snapshot_id,
        etf_profile_id=1,
        composition_date=composition_date,
        known_at=known_at,
        published_at=known_at,
        provenance="issuer",
        source_provider="local-fixture",
        source_quality="issuer_reported_current_holdings",
        completeness_status="complete",
        row_count=1,
        resolved_count=1,
        unresolved_count=0,
        snapshot_hash=f"snapshot-{snapshot_id}",
        extra_data={
            "source_tier": "issuer_native",
            "artifact_identity_validation": {"status": "matched"},
        },
    )
    holding = ETFHolding(
        id=snapshot_id,
        snapshot_id=snapshot_id,
        constituent_instrument_id=constituent_id,
        position=1,
        weight=Decimal("0.25"),
        holding_type="equity",
        row_type="security",
        source_row_hash=f"row-{snapshot_id}",
        is_resolved=True,
    )
    return snapshot, holding


async def _seed(
    session: AsyncSession, snapshots: tuple[tuple[ETFHoldingsSnapshot, ETFHolding], ...]
) -> None:
    session.add_all(
        (
            AssetClass(id=1, name="Equity", description="test-only asset class"),
            InstrumentType(id=1, asset_class_id=1, name="ETF", description="test-only type"),
        )
    )
    session.add_all(
        (
            Instrument(
                id=1,
                instrument_type_id=1,
                symbol="SPY",
                name="Fixture ETF",
                domain_key=_ETF_KEY,
                identity_status="resolved",
                is_active=True,
                is_synthetic=False,
            ),
            Instrument(
                id=2,
                instrument_type_id=1,
                symbol="AAA",
                name="Fixture constituent A",
                domain_key="US:EQ:AAA",
                identity_status="resolved",
                is_active=True,
                is_synthetic=False,
            ),
            Instrument(
                id=3,
                instrument_type_id=1,
                symbol="BBB",
                name="Fixture constituent B",
                domain_key="US:EQ:BBB",
                identity_status="resolved",
                is_active=True,
                is_synthetic=False,
            ),
            ETFProfile(id=1, instrument_id=1, adapter_status="available"),
        )
    )
    for snapshot, holding in snapshots:
        session.add_all((snapshot, holding))
    await session.commit()


def _default_snapshots() -> tuple[tuple[ETFHoldingsSnapshot, ETFHolding], ...]:
    return (
        _snapshot(
            snapshot_id=10,
            composition_date=date(2025, 3, 1),
            known_at=datetime(2025, 3, 2, 12, tzinfo=UTC),
            constituent_id=2,
        ),
        _snapshot(
            snapshot_id=20,
            composition_date=date(2025, 3, 3),
            known_at=datetime(2025, 3, 3, 12, tzinfo=UTC),
            constituent_id=3,
        ),
        _snapshot(
            snapshot_id=30,
            composition_date=date(2025, 3, 3),
            known_at=datetime(2025, 3, 3, 19, tzinfo=UTC),
            constituent_id=2,
        ),
    )


def _hydrator_values(reference: ETFMembershipReference) -> dict[str, object]:
    values = _inputs()
    old_snapshot = values["snapshot"]
    assert isinstance(old_snapshot, DataSnapshot)
    snapshot = replace(old_snapshot, etf_memberships=(reference,))
    old_experiment = values["experiment"]
    assert isinstance(old_experiment, ExperimentDefinition)
    experiment = replace(old_experiment, snapshot_fingerprint=snapshot.fingerprint)
    old_trial = values["trial"]
    assert isinstance(old_trial, ScientificTrial)
    trial = ScientificTrial.create(
        experiment_fingerprint=experiment.fingerprint,
        snapshot_fingerprint=snapshot.fingerprint,
        preflight_report=old_trial.preflight_report,
        parameter_set=old_trial.parameter_set,
        scenario=old_trial.scenario,
        seed=old_trial.seed,
        randomization=old_trial.randomization,
        evaluation_window=old_trial.evaluation_window,
    )
    old_attempt = values["attempt"]
    assert isinstance(old_attempt, RunAttempt)
    values.update(
        snapshot=snapshot,
        experiment=experiment,
        trial=trial,
        attempt=replace(old_attempt, trial_id=trial.trial_id),
    )
    return values


@pytest.mark.asyncio
async def test_local_reader_selects_latest_pit_and_revalidates_exact_pinned_content(
    etf_pit_database: tuple[async_sessionmaker[AsyncSession], str],
) -> None:
    sessions, _ = etf_pit_database
    async with sessions() as session:
        await _seed(session, _default_snapshots())
        selected = await resolve_etf_pit_membership(
            session, etf_instrument_id=_ETF_KEY, decision_time=_DECISION
        )
        assert selected.snapshot_id == 20
        assert selected.constituents[0].domain_key == "US:EQ:BBB"

    reference = ETFMembershipReference(
        etf_instrument_id=_ETF_KEY,
        decision_time=_DECISION,
        snapshot_id=selected.snapshot_id,
        content_digest=selected.content_digest,
    )
    reader = LocalETFMembershipReader(sessions)
    restarted = await reader.resolve_pinned_etf_membership(reference)
    assert restarted.snapshot_id == reference.snapshot_id
    assert restarted.content_digest == reference.content_digest
    hydrator_values = _hydrator_values(reference)
    hydrated = await NautilusTrialDomainHydrator(
        MemoryDomainReader(hydrator_values), etf_membership_reader=reader
    ).hydrate_attempt(
        principal="alice",
        attempt_resource_id=hydrator_values["attempt"].attempt_id,
    )
    assert hydrated.snapshot.etf_memberships == (reference,)

    async with sessions() as session, session.begin():
        await session.execute(
            update(ETFHolding)
            .where(ETFHolding.snapshot_id == reference.snapshot_id)
            .values(weight=Decimal("0.30"))
        )
    changed = await reader.resolve_pinned_etf_membership(reference)
    assert changed.snapshot_id == reference.snapshot_id
    assert changed.content_digest != reference.content_digest
    with pytest.raises(TrialDomainHydrationError, match="digest differs"):
        await NautilusTrialDomainHydrator(
            MemoryDomainReader(hydrator_values), etf_membership_reader=reader
        ).hydrate_attempt(
            principal="alice",
            attempt_resource_id=hydrator_values["attempt"].attempt_id,
        )


@pytest.mark.asyncio
async def test_local_reader_denies_missing_late_and_ambiguous_pit_identity(
    etf_pit_database: tuple[async_sessionmaker[AsyncSession], str],
) -> None:
    sessions, _ = etf_pit_database
    async with sessions() as session:
        await _seed(session, _default_snapshots())
        with pytest.raises(ValueError, match="missing or ambiguous"):
            await resolve_etf_pit_membership(
                session, etf_instrument_id="US:ETF:MISSING", decision_time=_DECISION
            )
        with pytest.raises(ValueError, match="latest ETF point-in-time snapshot is ambiguous"):
            snapshot, holding = _snapshot(
                snapshot_id=40,
                composition_date=date(2025, 3, 3),
                known_at=datetime(2025, 3, 3, 12, tzinfo=UTC),
                constituent_id=2,
            )
            session.add_all((snapshot, holding))
            await session.commit()
            await resolve_etf_pit_membership(
                session, etf_instrument_id=_ETF_KEY, decision_time=_DECISION
            )

    async with sessions() as session, session.begin():
        await session.execute(
            update(ETFHoldingsSnapshot)
            .where(ETFHoldingsSnapshot.id.in_((10, 20, 30, 40)))
            .values(known_at=datetime(2025, 3, 3, 19, tzinfo=UTC))
        )
    async with sessions() as session:
        with pytest.raises(ValueError, match="not known at decision time"):
            await resolve_etf_pit_membership(
                session, etf_instrument_id=_ETF_KEY, decision_time=_DECISION
            )


@pytest.mark.asyncio
async def test_local_reader_denies_unresolved_constituent_identity(
    etf_pit_database: tuple[async_sessionmaker[AsyncSession], str],
) -> None:
    sessions, _ = etf_pit_database
    async with sessions() as session:
        await _seed(session, _default_snapshots())
    async with sessions() as session, session.begin():
        await session.execute(Instrument.__table__.delete().where(Instrument.id == 3))
    async with sessions() as session:
        with pytest.raises(ValueError, match="constituent identity or row evidence is invalid"):
            await resolve_etf_pit_membership(
                session, etf_instrument_id=_ETF_KEY, decision_time=_DECISION
            )
