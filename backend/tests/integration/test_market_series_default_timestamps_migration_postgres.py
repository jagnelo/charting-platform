from __future__ import annotations

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.market_data_foundation import MarketSeriesDefault

_VERSIONS = Path(__file__).parents[2] / "alembic" / "versions"
_LEGACY_MIGRATION = _VERSIONS / "a0b1c2d3e4f5_add_market_series_default_mapping.py"
_REPAIR_MIGRATION = _VERSIONS / "d4a5b6c7e812_add_market_series_default_timestamps.py"


def _load_migration(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load migration {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.integration
def test_market_series_default_timestamp_repair_fresh_and_existing_rows(
    pg_container,
    test_database_url: str | None,
) -> None:
    if test_database_url is not None:
        pytest.skip("migration DDL test requires its own disposable PostgreSQL container")

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    engine = sa.create_engine(pg_container.get_connection_url(), pool_pre_ping=True)
    legacy_migration = _load_migration(_LEGACY_MIGRATION, "legacy_market_series_default")
    repair_migration = _load_migration(_REPAIR_MIGRATION, "market_series_default_timestamps")
    schemas = [f"market_series_default_{uuid4().hex[:12]}" for _ in range(2)]

    try:
        for schema, preserve_existing_row in zip(schemas, (False, True), strict=True):
            with engine.begin() as connection:
                connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
                connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
                connection.exec_driver_sql("CREATE TABLE instrument (id INTEGER PRIMARY KEY)")
                connection.exec_driver_sql("CREATE TABLE market_series (id BIGINT PRIMARY KEY)")
                connection.exec_driver_sql("INSERT INTO instrument (id) VALUES (7), (8)")
                connection.exec_driver_sql("INSERT INTO market_series (id) VALUES (91)")

                operations = Operations(MigrationContext.configure(connection))
                legacy_migration.op = operations
                legacy_migration.upgrade()

                if preserve_existing_row:
                    connection.execute(
                        sa.text(
                            """
                            INSERT INTO market_series_default (
                                instrument_id, timeframe, is_adjusted,
                                market_series_id, selection_reason, selected_at, provenance
                            ) VALUES (
                                7, 'D1', true, 91, 'operator_override',
                                '2026-10-22T14:30:00+00:00', '{"source":"retained"}'
                            )
                            """
                        )
                    )

                repair_migration.op = operations
                repair_migration.upgrade()

                columns = {
                    column["name"]
                    for column in sa.inspect(connection).get_columns("market_series_default")
                }
                assert {"created_at", "updated_at"}.issubset(columns)

                with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                    rows = session.query(MarketSeriesDefault).all()
                    if preserve_existing_row:
                        assert len(rows) == 1
                        row = rows[0]
                        assert row.instrument_id == 7
                        assert row.timeframe == "D1"
                        assert row.is_adjusted is True
                        assert row.market_series_id == 91
                        assert row.selection_reason == "operator_override"
                        assert row.selected_at.isoformat().startswith("2026-10-22T14:30:00")
                        assert row.provenance == {"source": "retained"}
                        assert row.created_at is not None
                        assert row.updated_at is not None
                    else:
                        assert rows == []
                        session.execute(
                            sa.text(
                                """
                                INSERT INTO market_series_default (
                                    instrument_id, timeframe, is_adjusted, market_series_id,
                                    selection_reason, provenance
                                ) VALUES (8, 'D1', false, NULL, 'first_canonical', '{}')
                                """
                            )
                        )
                        session.expire_all()
                        row = session.query(MarketSeriesDefault).one()
                        assert row.instrument_id == 8
                        assert row.created_at is not None
                        assert row.updated_at is not None
    finally:
        with engine.begin() as connection:
            for schema in schemas:
                connection.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
