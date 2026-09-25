"""SQLite coverage for immutable reconciliation issue evidence."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = Path(__file__).parents[3] / "alembic" / "versions" / (
        "e9f1a2b3c4d6_add_reconciliation_issue_observations.py"
    )
    spec = importlib.util.spec_from_file_location("reconciliation_issue_observations", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_retains_repeated_issue_evidence_and_guards_downgrade():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE data_source (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql(
            "CREATE TABLE instrument_reconciliation_issue (id INTEGER PRIMARY KEY)"
        )
        module = _migration_module()
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()

        assert "instrument_reconciliation_issue_observation" in inspect(
            connection
        ).get_table_names()
        connection.execute(text("INSERT INTO data_source (id) VALUES (1)"))
        connection.execute(text("INSERT INTO instrument_reconciliation_issue (id) VALUES (1)"))
        values = (
            "(issue_id, data_source_id, provider_symbol, issue_type, fingerprint, "
            "observed_at, payload) VALUES (1, 1, 'ABC', 'ambiguous', 'fp', "
            "CURRENT_TIMESTAMP, '{}')"
        )
        connection.execute(text("INSERT INTO instrument_reconciliation_issue_observation " + values))
        connection.execute(text("INSERT INTO instrument_reconciliation_issue_observation " + values))
        assert connection.exec_driver_sql(
            "SELECT COUNT(*) FROM instrument_reconciliation_issue_observation"
        ).scalar_one() == 2

        with pytest.raises(RuntimeError, match="reconciliation issue evidence"):
            module.downgrade()
        connection.execute(text("DELETE FROM instrument_reconciliation_issue_observation"))
        module.downgrade()
        assert "instrument_reconciliation_issue_observation" not in inspect(
            connection
        ).get_table_names()
