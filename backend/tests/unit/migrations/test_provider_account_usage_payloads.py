"""SQLite smoke coverage for raw provider account-usage evidence columns."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = Path(__file__).parents[3] / "alembic" / "versions" / (
        "e6f7a8b9c0d1_add_provider_account_usage_payloads.py"
    )
    spec = importlib.util.spec_from_file_location("provider_account_usage_payloads", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_provider_account_usage_payload_migration_reverses_cleanly():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table(
        "provider_account_usage_observation",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("data_source_id", Integer, nullable=False),
        Column("unit", String, nullable=False),
    )
    metadata.create_all(engine)
    module = _migration_module()

    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        module.op = operations
        module.upgrade()
        columns = {
            column["name"]
            for column in inspect(connection).get_columns("provider_account_usage_observation")
        }
        assert {"payload", "response_headers"} <= columns
        connection.execute(
            text(
                "INSERT INTO provider_account_usage_observation "
                "(id, data_source_id, unit, payload, response_headers) "
                "VALUES (1, 2, 'requests', '{\"date\":\"2026-09-25\"}', '{}')"
            )
        )
        with pytest.raises(RuntimeError, match="evidence would be lost"):
            module.downgrade()
        connection.execute(text("DELETE FROM provider_account_usage_observation"))
        module.downgrade()
        remaining = {
            column["name"]
            for column in inspect(connection).get_columns("provider_account_usage_observation")
        }
        assert {"payload", "response_headers"}.isdisjoint(remaining)
