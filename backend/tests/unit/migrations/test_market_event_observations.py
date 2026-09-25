"""SQLite coverage for immutable market-event provider observations."""

import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = Path(__file__).parents[3] / "alembic" / "versions" / (
        "d2e3f4a5b6c7_add_market_event_observations.py"
    )
    spec = importlib.util.spec_from_file_location("market_event_observations", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_market_event_observation_migration_creates_append_only_table():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE market_event (id INTEGER PRIMARY KEY, event_key VARCHAR(180), source VARCHAR(80))"
        )
        module = _migration_module()
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()

        assert "market_event_observation" in inspect(connection).get_table_names()
        connection.execute(
            text(
                "INSERT INTO market_event_observation "
                "(market_event_id, event_key, source, event_type, observed_at, payload) "
                "VALUES (1, 'event:1', 'fixture', 'earnings', CURRENT_TIMESTAMP, '{}')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO market_event_observation "
                "(market_event_id, event_key, source, event_type, observed_at, payload) "
                "VALUES (1, 'event:1', 'fixture', 'earnings', CURRENT_TIMESTAMP, '{}')"
            )
        )
        assert connection.exec_driver_sql(
            "SELECT COUNT(*) FROM market_event_observation"
        ).scalar_one() == 2

        module.downgrade()
        assert "market_event_observation" not in inspect(connection).get_table_names()
