"""SQLite smoke coverage for named provider usage dimensions."""

import importlib.util
from datetime import datetime
from pathlib import Path

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, create_engine, inspect

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = Path(__file__).parents[3] / "alembic" / "versions" / (
        "b0c1d2e3f4a5_add_provider_usage_observation_dimensions.py"
    )
    spec = importlib.util.spec_from_file_location("provider_usage_observation_dimensions", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_provider_usage_dimension_migration_backfills_legacy_rows_and_reverses_cleanly():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("data_source", metadata, Column("id", Integer, primary_key=True), Column("name", String))
    observations = Table(
        "provider_account_usage_observation",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("data_source_id", Integer, nullable=False),
        Column("observed_at", DateTime(timezone=True), nullable=False),
        Column("unit", String(32), nullable=False),
        Column("limit", Integer),
        Column("remaining", Integer),
        Column("consumed", Integer),
        Column("reset_at", DateTime(timezone=True)),
        Column("options_data_permissions", String(80)),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            observations.insert().values(
                id=1,
                data_source_id=1,
                observed_at=datetime(2026, 9, 16, 12, 0),
                unit="credits",
                limit=100,
                remaining=90,
            )
        )
        operations = Operations(MigrationContext.configure(connection))
        module = _migration_module()
        module.op = operations
        module.upgrade()
        columns = {column["name"] for column in inspect(connection).get_columns(
            "provider_account_usage_observation"
        )}
        assert {"dimension", "account_plan"} <= columns
        row = connection.exec_driver_sql(
            "SELECT dimension FROM provider_account_usage_observation WHERE id = 1"
        ).mappings().one()
        assert row["dimension"] == "default"
        module.downgrade()
        columns = {column["name"] for column in inspect(connection).get_columns(
            "provider_account_usage_observation"
        )}
        assert "dimension" not in columns
        assert "account_plan" not in columns
