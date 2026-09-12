"""SQLite smoke coverage for the provider-bar session migration."""

import importlib.util
from pathlib import Path

from sqlalchemy import Column, Integer, MetaData, Table, create_engine, inspect

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = Path(__file__).parents[3] / "alembic" / "versions" / (
        "8e9f0a1b2c3d_add_market_bar_observation_session.py"
    )
    spec = importlib.util.spec_from_file_location("market_bar_session", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_market_bar_observation_session_migration_adds_default_and_reverses():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table(
        "market_bar_observation",
        metadata,
        Column("id", Integer, primary_key=True),
    )
    metadata.create_all(engine)
    module = _migration_module()

    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        module.op = operations
        module.upgrade()

        connection.exec_driver_sql(
            "INSERT INTO market_bar_observation (id) VALUES (1)"
        )
        assert connection.exec_driver_sql(
            "SELECT session FROM market_bar_observation WHERE id = 1"
        ).scalar_one() == "regular"
        assert "session" in {
            column["name"] for column in inspect(connection).get_columns("market_bar_observation")
        }

        module.downgrade()
        assert "session" not in {
            column["name"] for column in inspect(connection).get_columns("market_bar_observation")
        }
