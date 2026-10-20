"""SQLite smoke coverage for the additive recurring-cost migration."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

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


def _zero_budget_migration_module():
    path = (
        Path(__file__).parents[3]
        / "alembic"
        / "versions"
        / "b6e9a42d1c73_allow_zero_recurring_cost_budget.py"
    )
    spec = importlib.util.spec_from_file_location("provider_zero_cost_budget", path)
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


def test_zero_cost_budget_migration_allows_zero_rejects_negative_and_preserves_rows():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("data_source", metadata, Column("id", Integer, primary_key=True), Column("name", String))
    metadata.create_all(engine)
    initial = _migration_module()
    zero_budget = _zero_budget_migration_module()

    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        initial.op = operations
        zero_budget.op = operations
        connection.exec_driver_sql("INSERT INTO data_source (id, name) VALUES (1, 'existing')")
        initial.upgrade()
        zero_budget.upgrade()
        connection.execute(
            text(
                "INSERT INTO provider_recurring_cost_budget "
                "(id, currency, monthly_ceiling, evidence_source, evidence_version, "
                "reviewed_at, revision) "
                "VALUES (1, 'USD', 0, 'reviewed zero', 'test-v1', CURRENT_TIMESTAMP, 1)"
            )
        )
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(
                    text(
                        "UPDATE provider_recurring_cost_budget SET monthly_ceiling = -1 "
                        "WHERE id = 1"
                    )
                )

        assert (
            connection.execute(
                text("SELECT monthly_ceiling FROM provider_recurring_cost_budget WHERE id = 1")
            ).scalar_one()
            == 0
        )
        connection.execute(
            text("UPDATE provider_recurring_cost_budget SET monthly_ceiling = 0 WHERE id = 1")
        )
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                connection.execute(
                    text(
                        "UPDATE provider_recurring_cost_budget SET monthly_ceiling = -1 "
                        "WHERE id = 1"
                    )
                )
        assert (
            connection.execute(text("SELECT name FROM data_source WHERE id = 1")).scalar_one()
            == "existing"
        )

    engine.dispose()
