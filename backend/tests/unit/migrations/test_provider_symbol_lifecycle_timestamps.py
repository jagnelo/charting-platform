"""SQLite coverage for provider-symbol lifecycle columns."""

import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, inspect

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = Path(__file__).parents[3] / "alembic" / "versions" / (
        "fa1b2c3d4e5f_add_provider_symbol_lifecycle_timestamps.py"
    )
    spec = importlib.util.spec_from_file_location("provider_symbol_lifecycle", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_provider_symbol_lifecycle_migration_is_additive_and_reversible():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE instrument_provider_symbol "
            "(id INTEGER PRIMARY KEY, provider_symbol VARCHAR(80) NOT NULL)"
        )
        module = _migration_module()
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()

        columns = {column["name"] for column in inspect(connection).get_columns("instrument_provider_symbol")}
        assert {"effective_at", "known_at", "retired_at"} <= columns
        indexes = {index["name"] for index in inspect(connection).get_indexes("instrument_provider_symbol")}
        assert {
            "ix_instrument_provider_symbol_effective_at",
            "ix_instrument_provider_symbol_known_at",
            "ix_instrument_provider_symbol_retired_at",
        } <= indexes

        module.downgrade()
        columns = {column["name"] for column in inspect(connection).get_columns("instrument_provider_symbol")}
        assert not {"effective_at", "known_at", "retired_at"} & columns
