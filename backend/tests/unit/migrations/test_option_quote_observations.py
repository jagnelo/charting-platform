"""SQLite coverage for immutable option-quote provider observations."""

import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = Path(__file__).parents[3] / "alembic" / "versions" / (
        "d5f6a7b8c9d0_add_option_quote_observations.py"
    )
    spec = importlib.util.spec_from_file_location("option_quote_observations", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_option_quote_observation_migration_is_append_only():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        for table in (
            "instrument",
            "option_chain_snapshot",
            "data_source",
        ):
            connection.exec_driver_sql(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)")
        connection.execute(text("INSERT INTO instrument (id) VALUES (1)"))
        connection.execute(text("INSERT INTO option_chain_snapshot (id) VALUES (1)"))
        connection.execute(text("INSERT INTO data_source (id) VALUES (1)"))
        module = _migration_module()
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        assert "option_quote_observation" in inspect(connection).get_table_names()
        values = (
            "(option_instrument_id, snapshot_id, data_source_id, observed_at, fetched_at, payload) "
            "VALUES (1, 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, '{}')"
        )
        connection.execute(text("INSERT INTO option_quote_observation " + values))
        connection.execute(text("INSERT INTO option_quote_observation " + values))
        assert connection.exec_driver_sql(
            "SELECT COUNT(*) FROM option_quote_observation"
        ).scalar_one() == 2
        module.downgrade()
        assert "option_quote_observation" not in inspect(connection).get_table_names()
