"""SQLite coverage for append-only fundamental and short-interest evidence."""

import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = Path(__file__).parents[3] / "alembic" / "versions" / (
        "d4e5f6a7b8c9_add_fundamental_short_interest_observations.py"
    )
    spec = importlib.util.spec_from_file_location("fundamental_short_observations", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fundamental_and_short_interest_observations_are_append_only():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE issuer (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE instrument (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql(
            "CREATE TABLE fundamental_fact (id INTEGER PRIMARY KEY)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE short_interest_observation (id INTEGER PRIMARY KEY)"
        )
        connection.execute(text("INSERT INTO issuer (id) VALUES (1)"))
        connection.execute(text("INSERT INTO instrument (id) VALUES (1)"))
        connection.execute(text("INSERT INTO fundamental_fact (id) VALUES (1)"))
        connection.execute(text("INSERT INTO short_interest_observation (id) VALUES (1)"))

        module = _migration_module()
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        tables = inspect(connection).get_table_names()
        assert "fundamental_fact_observation" in tables
        assert "short_interest_provider_observation" in tables

        fundamental_values = (
            "(fundamental_fact_id, issuer_id, fact_namespace, fact_key, source, observed_at, payload) "
            "VALUES (1, 1, 'us-gaap', 'Assets', 'edgar', CURRENT_TIMESTAMP, '{}')"
        )
        connection.execute(
            text("INSERT INTO fundamental_fact_observation " + fundamental_values)
        )
        connection.execute(
            text("INSERT INTO fundamental_fact_observation " + fundamental_values)
        )
        short_values = (
            "(canonical_observation_id, instrument_id, settlement_date, source, observed_at, payload) "
            "VALUES (1, 1, '2026-09-01', 'finra', CURRENT_TIMESTAMP, '{}')"
        )
        connection.execute(
            text("INSERT INTO short_interest_provider_observation " + short_values)
        )
        connection.execute(
            text("INSERT INTO short_interest_provider_observation " + short_values)
        )
        assert connection.exec_driver_sql(
            "SELECT COUNT(*) FROM fundamental_fact_observation"
        ).scalar_one() == 2
        assert connection.exec_driver_sql(
            "SELECT COUNT(*) FROM short_interest_provider_observation"
        ).scalar_one() == 2

        module.downgrade()
        tables = inspect(connection).get_table_names()
        assert "fundamental_fact_observation" not in tables
        assert "short_interest_provider_observation" not in tables
