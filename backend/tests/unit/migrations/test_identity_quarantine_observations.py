"""SQLite coverage for immutable identity-quarantine evidence."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = Path(__file__).parents[3] / "alembic" / "versions" / (
        "e9f3a4b5c6d7_add_identity_quarantine_observations.py"
    )
    spec = importlib.util.spec_from_file_location("identity_quarantine_observations", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_retains_repeated_identity_evidence_and_guards_downgrade():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE instrument (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql(
            "CREATE TABLE instrument_identity_quarantine (id INTEGER PRIMARY KEY)"
        )
        module = _migration_module()
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()

        assert "instrument_identity_quarantine_observation" in inspect(
            connection
        ).get_table_names()
        connection.execute(text("INSERT INTO instrument (id) VALUES (1)"))
        connection.execute(
            text("INSERT INTO instrument_identity_quarantine (id) VALUES (1)")
        )
        values = (
            "(id, quarantine_id, instrument_id, provider_name, reason, status, observed_at, "
            "candidate_payload) VALUES ({id}, 1, 1, 'fixture', 'ambiguous', 'pending', "
            "CURRENT_TIMESTAMP, '{{}}')"
        )
        connection.execute(
            text(
                "INSERT INTO instrument_identity_quarantine_observation "
                + values.format(id=1)
            )
        )
        connection.execute(
            text(
                "INSERT INTO instrument_identity_quarantine_observation "
                + values.format(id=2)
            )
        )
        assert connection.exec_driver_sql(
            "SELECT COUNT(*) FROM instrument_identity_quarantine_observation"
        ).scalar_one() == 2

        with pytest.raises(RuntimeError, match="identity-quarantine evidence"):
            module.downgrade()
        connection.execute(text("DELETE FROM instrument_identity_quarantine_observation"))
        module.downgrade()
        assert "instrument_identity_quarantine_observation" not in inspect(
            connection
        ).get_table_names()
