"""SQLite coverage for immutable universe lifecycle observations."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = Path(__file__).parents[3] / "alembic" / "versions" / (
        "e9f0a1b2c3d4_add_market_universe_lifecycle_observation_snapshots.py"
    )
    spec = importlib.util.spec_from_file_location("universe_lifecycle_snapshots", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_retains_repeated_universe_observations_and_guards_downgrade():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        for table in (
            "data_source",
            "market_universe_reconciliation_run",
            "instrument",
            "instrument_listing",
        ):
            connection.exec_driver_sql(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)")
        module = _migration_module()
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()

        assert "market_universe_lifecycle_observation_snapshot" in inspect(
            connection
        ).get_table_names()
        values = (
            "(data_source_id, provider_symbol, quote_type, observed_at, "
            "lifecycle_status, first_seen_at, consecutive_seen, consecutive_missing, payload) "
            "VALUES (1, 'AAPL', 'EQUITY', CURRENT_TIMESTAMP, 'active', "
            "CURRENT_TIMESTAMP, 1, 0, '{}')"
        )
        connection.execute(text("INSERT INTO data_source (id) VALUES (1)"))
        connection.execute(
            text("INSERT INTO market_universe_lifecycle_observation_snapshot " + values)
        )
        connection.execute(
            text("INSERT INTO market_universe_lifecycle_observation_snapshot " + values)
        )
        assert connection.exec_driver_sql(
            "SELECT COUNT(*) FROM market_universe_lifecycle_observation_snapshot"
        ).scalar_one() == 2

        with pytest.raises(RuntimeError, match="universe lifecycle observation evidence"):
            module.downgrade()
        connection.execute(
            text("DELETE FROM market_universe_lifecycle_observation_snapshot")
        )
        module.downgrade()
        assert "market_universe_lifecycle_observation_snapshot" not in inspect(
            connection
        ).get_table_names()
