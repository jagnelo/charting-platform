"""SQLite smoke coverage for the default market-series mapping migration."""

import importlib.util
from pathlib import Path

from sqlalchemy import Column, Integer, MetaData, Table, create_engine, inspect

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = Path(__file__).parents[3] / "alembic" / "versions" / (
        "a0b1c2d3e4f5_add_market_series_default_mapping.py"
    )
    spec = importlib.util.spec_from_file_location("market_series_default", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_market_series_default_mapping_migration_reverses_cleanly():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("instrument", metadata, Column("id", Integer, primary_key=True))
    Table("market_series", metadata, Column("id", Integer, primary_key=True))
    metadata.create_all(engine)
    module = _migration_module()

    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        module.op = operations
        module.upgrade()

        table = inspect(connection).get_columns("market_series_default")
        assert {column["name"] for column in table} >= {
            "instrument_id",
            "timeframe",
            "is_adjusted",
            "market_series_id",
            "selected_at",
        }
        connection.exec_driver_sql(
            "INSERT INTO instrument (id) VALUES (1)"
        )
        connection.exec_driver_sql(
            "INSERT INTO market_series (id) VALUES (99)"
        )
        connection.exec_driver_sql(
            """
            INSERT INTO market_series_default
              (instrument_id, timeframe, is_adjusted, market_series_id)
            VALUES (1, 'D1', 1, 99)
            """
        )
        assert connection.exec_driver_sql(
            "SELECT market_series_id FROM market_series_default"
        ).scalar_one() == 99

        module.downgrade()
        assert "market_series_default" not in inspect(connection).get_table_names()
