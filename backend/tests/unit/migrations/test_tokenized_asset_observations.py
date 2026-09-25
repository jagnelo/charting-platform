"""SQLite coverage for immutable tokenized-asset provider observations."""

import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = Path(__file__).parents[3] / "alembic" / "versions" / (
        "d3f4a5b6c7d8_add_tokenized_asset_observations.py"
    )
    spec = importlib.util.spec_from_file_location("tokenized_asset_observations", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tokenized_asset_observation_migration_creates_append_only_table():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE instrument (id INTEGER PRIMARY KEY)")
        module = _migration_module()
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()

        assert "tokenized_asset_observation" in inspect(connection).get_table_names()
        connection.execute(text("INSERT INTO instrument (id) VALUES (1)"))
        values = (
            "(instrument_id, provider_asset_id, provider_name, observed_at, fetched_at, payload) "
            "VALUES (1, 'x:AAPL', 'xstocks', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, '{}')"
        )
        connection.execute(text("INSERT INTO tokenized_asset_observation " + values))
        connection.execute(text("INSERT INTO tokenized_asset_observation " + values))
        assert connection.exec_driver_sql(
            "SELECT COUNT(*) FROM tokenized_asset_observation"
        ).scalar_one() == 2

        module.downgrade()
        assert "tokenized_asset_observation" not in inspect(connection).get_table_names()
