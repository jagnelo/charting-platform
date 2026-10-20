"""SQLite smoke coverage for durable provider pagination continuation."""

import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, inspect

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = (
        Path(__file__).parents[3]
        / "alembic"
        / "versions"
        / ("ce5f6a7b8c9d_add_provider_pagination_state.py")
    )
    spec = importlib.util.spec_from_file_location("provider_pagination_state", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _timestamp_defaults_migration_module():
    path = (
        Path(__file__).parents[3]
        / "alembic"
        / "versions"
        / ("c4d5e6f7a8b9_provider_pagination_timestamp_defaults.py")
    )
    spec = importlib.util.spec_from_file_location("provider_pagination_timestamp_defaults", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_provider_pagination_state_migration_reverses_cleanly():
    engine = create_engine("sqlite://")
    module = _migration_module()

    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        module.op = operations
        module.upgrade()

        timestamp_migration = _timestamp_defaults_migration_module()
        timestamp_migration.op = operations
        timestamp_migration.upgrade()

        columns = {
            column["name"]
            for column in inspect(connection).get_columns("provider_pagination_state")
        }
        assert {
            "state_key",
            "provider",
            "capability",
            "page_number",
            "cursor",
            "cursor_history",
            "metadata_payload",
        } <= columns

        timestamp_columns = {
            column["name"]: column
            for column in inspect(connection).get_columns("provider_pagination_state")
        }
        assert timestamp_columns["created_at"]["default"]
        assert timestamp_columns["updated_at"]["default"]
        connection.exec_driver_sql(
            "INSERT INTO provider_pagination_state "
            "(id, state_key, provider, capability, operation) "
            "VALUES (1, 'test-state', 'test', 'universe_discovery', 'discover')"
        )
        created_at, updated_at = connection.exec_driver_sql(
            "SELECT created_at, updated_at FROM provider_pagination_state "
            "WHERE state_key = 'test-state'"
        ).one()
        assert created_at is not None
        assert updated_at is not None

        timestamp_migration.downgrade()
        module.downgrade()
        assert not inspect(connection).has_table("provider_pagination_state")
