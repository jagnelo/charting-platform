"""SQLite smoke coverage for the market_refresh_job partial claim index."""

import importlib.util
from pathlib import Path

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, create_engine, inspect

from alembic.migration import MigrationContext
from alembic.operations import Operations

INDEX_NAME = "ix_market_refresh_job_claimable"


def _migration_module():
    path = (
        Path(__file__).parents[3]
        / "alembic"
        / "versions"
        / "a7c3e5f9b2d4_add_refresh_job_claim_index.py"
    )
    spec = importlib.util.spec_from_file_location("refresh_job_claim_index", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _index_columns(connection):
    return {
        index["name"]: index["column_names"]
        for index in inspect(connection).get_indexes("market_refresh_job")
    }


def test_refresh_job_claim_index_migration_reverses_cleanly():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table(
        "market_refresh_job",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("priority", Integer, nullable=False),
        Column("status", String(24), nullable=False),
        Column("next_attempt_at", DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(engine)
    module = _migration_module()

    assert module.down_revision == "e6f7a8b9c012"
    with engine.begin() as connection:
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        assert _index_columns(connection)[INDEX_NAME] == ["priority", "next_attempt_at", "id"]
        module.downgrade()
        assert INDEX_NAME not in _index_columns(connection)
