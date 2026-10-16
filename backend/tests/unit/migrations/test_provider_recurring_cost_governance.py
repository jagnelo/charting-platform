"""SQLite smoke coverage for the additive recurring-cost migration."""

import importlib.util
from pathlib import Path

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = (
        Path(__file__).parents[3]
        / "alembic"
        / "versions"
        / "c5d6e7f8a9b0_add_provider_recurring_cost_governance.py"
    )
    spec = importlib.util.spec_from_file_location("provider_recurring_cost_governance", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_provider_recurring_cost_migration_is_additive_and_reversible():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("data_source", metadata, Column("id", Integer, primary_key=True), Column("name", String))
    metadata.create_all(engine)
    migration = _migration_module()

    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        migration.op = operations
        connection.exec_driver_sql("INSERT INTO data_source (id, name) VALUES (1, 'existing')")
        migration.upgrade()

        assert set(inspect(connection).get_table_names()) >= {
            "data_source",
            "provider_recurring_cost_budget",
            "provider_recurring_cost_budget_revision",
            "provider_recurring_cost_commitment",
            "provider_recurring_cost_commitment_revision",
        }
        assert (
            connection.exec_driver_sql("SELECT name FROM data_source WHERE id = 1").scalar_one()
            == "existing"
        )

        migration.downgrade()
        assert not inspect(connection).has_table("provider_recurring_cost_budget")
        assert not inspect(connection).has_table("provider_recurring_cost_budget_revision")
        assert not inspect(connection).has_table("provider_recurring_cost_commitment")
        assert not inspect(connection).has_table("provider_recurring_cost_commitment_revision")
        assert (
            connection.exec_driver_sql("SELECT name FROM data_source WHERE id = 1").scalar_one()
            == "existing"
        )

    engine.dispose()
