"""SQLite smoke coverage for retained SEC directory source evidence."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = Path(__file__).parents[3] / "alembic" / "versions" / (
        "e7f8a9b0c1d2_retain_sec_directory_source_payload.py"
    )
    spec = importlib.util.spec_from_file_location("sec_directory_source_payload", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sec_directory_source_payload_migration_refuses_evidence_loss():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table(
        "sec_issuer_directory_candidate",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("cycle_number", Integer, nullable=False),
        Column("cik", String, nullable=False),
    )
    metadata.create_all(engine)
    module = _migration_module()

    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        module.op = operations
        module.upgrade()
        columns = {
            column["name"]
            for column in inspect(connection).get_columns("sec_issuer_directory_candidate")
        }
        assert "source_payload" in columns
        connection.execute(
            text(
                "INSERT INTO sec_issuer_directory_candidate "
                "(id, cycle_number, cik, source_payload) "
                "VALUES (1, 1, '0000000001', '{\"ticker\":\"ABC\"}')"
            )
        )
        with pytest.raises(RuntimeError, match="source evidence would be lost"):
            module.downgrade()
        connection.execute(text("DELETE FROM sec_issuer_directory_candidate"))
        module.downgrade()
        remaining = {
            column["name"]
            for column in inspect(connection).get_columns("sec_issuer_directory_candidate")
        }
        assert "source_payload" not in remaining
