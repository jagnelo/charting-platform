"""SQLite smoke coverage for durable provider-wide event scan state."""

import importlib.util
from pathlib import Path

from sqlalchemy import Column, Integer, MetaData, Table, create_engine, inspect

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = Path(__file__).parents[3] / "alembic" / "versions" / (
        "a3b4c5d6e7f8_add_market_event_scan_state.py"
    )
    spec = importlib.util.spec_from_file_location("market_event_scan_state", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_scan_state_migration_adds_durable_cursor_table_and_reverses_cleanly():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("issuer", metadata, Column("id", Integer, primary_key=True))
    metadata.create_all(engine)
    module = _migration_module()

    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        module.op = operations
        module.upgrade()

        columns = {
            column["name"] for column in inspect(connection).get_columns("market_event_scan_state")
        }
        assert {
            "scan_key",
            "cursor_issuer_id",
            "cycle_count",
            "last_batch_count",
            "provenance",
        } <= columns

        module.downgrade()
        assert "market_event_scan_state" not in inspect(connection).get_table_names()
