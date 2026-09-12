"""SQLite smoke coverage for provisional pre-listing candidate migration."""

import importlib.util
from pathlib import Path

from sqlalchemy import Column, Integer, MetaData, Table, create_engine, inspect

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = Path(__file__).parents[3] / "alembic" / "versions" / (
        "a2b3c4d5e6f7_add_prelisting_candidates.py"
    )
    spec = importlib.util.spec_from_file_location("prelisting_candidates", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prelisting_candidate_migration_adds_auditable_table_and_reverses_cleanly():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("instrument", metadata, Column("id", Integer, primary_key=True))
    Table("issuer", metadata, Column("id", Integer, primary_key=True))
    Table("market_event_consensus", metadata, Column("id", Integer, primary_key=True))
    Table("market_event", metadata, Column("id", Integer, primary_key=True))
    metadata.create_all(engine)
    module = _migration_module()

    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        module.op = operations
        module.upgrade()

        columns = {
            column["name"]
            for column in inspect(connection).get_columns("market_event_prelisting_candidate")
        }
        assert {
            "candidate_key",
            "proposed_symbol",
            "expected_listing_date",
            "stable_identifiers",
            "provenance",
        } <= columns

        module.downgrade()
        assert "market_event_prelisting_candidate" not in inspect(connection).get_table_names()
