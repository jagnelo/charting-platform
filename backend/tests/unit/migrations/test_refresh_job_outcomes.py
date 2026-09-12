"""SQLite smoke coverage for durable refresh-job outcome metadata."""

import importlib.util
from pathlib import Path

from sqlalchemy import Column, Integer, MetaData, Table, create_engine, inspect

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = Path(__file__).parents[3] / "alembic" / "versions" / (
        "5f6a7b8c9d0e_add_refresh_job_outcomes.py"
    )
    spec = importlib.util.spec_from_file_location("refresh_job_outcomes", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_refresh_job_outcome_migration_reverses_cleanly():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("market_refresh_job", metadata, Column("id", Integer, primary_key=True))
    metadata.create_all(engine)
    module = _migration_module()

    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        module.op = operations
        module.upgrade()
        columns = {
            column["name"] for column in inspect(connection).get_columns("market_refresh_job")
        }
        assert {"started_at", "finished_at", "result_summary"} <= columns
        module.downgrade()
        columns = {
            column["name"] for column in inspect(connection).get_columns("market_refresh_job")
        }
        assert not {"started_at", "finished_at", "result_summary"} & columns
