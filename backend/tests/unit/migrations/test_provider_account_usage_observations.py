"""SQLite smoke coverage for provider-native account usage persistence."""

import importlib.util
from pathlib import Path

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = Path(__file__).parents[3] / "alembic" / "versions" / (
        "4e5f6a7b8c9d_add_provider_account_usage_observations.py"
    )
    spec = importlib.util.spec_from_file_location("provider_account_usage_observations", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_provider_account_usage_observation_migration_reverses_cleanly():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("data_source", metadata, Column("id", Integer, primary_key=True), Column("name", String))
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
        assert {"unit", "limit", "remaining", "consumed", "reset_at"} <= columns
        module.downgrade()
        assert not inspect(connection).has_table("provider_account_usage_observation")
