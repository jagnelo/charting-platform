"""SQLite smoke coverage for the additive provider quota-group migration."""

import importlib.util
from pathlib import Path

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    inspect,
)

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = Path(__file__).parents[3] / "alembic" / "versions" / (
        "7d8e9f0a1b2c_add_provider_quota_groups.py"
    )
    spec = importlib.util.spec_from_file_location("provider_quota_groups", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _legacy_tables(engine):
    metadata = MetaData()
    Table("data_source", metadata, Column("id", Integer, primary_key=True))
    Table(
        "provider_quota_window",
        metadata,
        Column("id", BigInteger, primary_key=True),
        Column("data_source_id", Integer),
        Column("capability", String(80), nullable=False),
        Column("dimension", String(80), nullable=False),
        Column("window_started_at", DateTime, nullable=False),
        Column("window_seconds", Integer, nullable=False),
        Column("limit_units", Integer, nullable=False),
        Column("reserved_units", Integer, nullable=False),
        Column("consumed_units", Integer, nullable=False),
        UniqueConstraint(
            "data_source_id",
            "capability",
            "dimension",
            "window_started_at",
            "window_seconds",
            name="uq_provider_quota_window",
        ),
    )
    Table(
        "provider_quota_identity",
        metadata,
        Column("id", BigInteger, primary_key=True),
        Column("data_source_id", Integer),
        Column("capability", String(80), nullable=False),
        Column("dimension", String(80), nullable=False),
        Column("window_started_at", DateTime, nullable=False),
        Column("window_seconds", Integer, nullable=False),
        Column("identity_key", String(180), nullable=False),
        UniqueConstraint(
            "data_source_id",
            "capability",
            "dimension",
            "window_started_at",
            "window_seconds",
            "identity_key",
            name="uq_provider_quota_identity",
        ),
    )
    metadata.create_all(engine)


def test_provider_quota_group_migration_backfills_and_reverses():
    engine = create_engine("sqlite://")
    _legacy_tables(engine)
    module = _migration_module()
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE INDEX ix_provider_quota_identity_lookup ON provider_quota_identity "
            "(data_source_id, capability, dimension, window_started_at, window_seconds)"
        )
        connection.exec_driver_sql(
            "INSERT INTO provider_quota_window VALUES "
            "(1, 1, 'price_history', 'credits_per_day', '2026-09-01 00:00:00', 86400, 10, 2, 3)"
        )
        connection.exec_driver_sql(
            "INSERT INTO provider_quota_identity VALUES "
            "(1, 1, 'price_history', 'symbols', '2026-09-01 00:00:00', 2678400, 'AAPL')"
        )
        operations = Operations(MigrationContext.configure(connection))
        module.op = operations
        module.upgrade()

        assert (
            connection.exec_driver_sql(
                "SELECT quota_group FROM provider_quota_window"
            ).scalar_one()
            == "price_history"
        )
        assert (
            connection.exec_driver_sql(
                "SELECT quota_group FROM provider_quota_identity"
            ).scalar_one()
            == "price_history"
        )
        assert "quota_group" in {
            column["name"] for column in inspect(connection).get_columns("provider_quota_window")
        }

        module.downgrade()
        assert "quota_group" not in {
            column["name"] for column in inspect(connection).get_columns("provider_quota_window")
        }
        assert "ix_provider_quota_identity_lookup" in {
            index["name"]
            for index in inspect(connection).get_indexes("provider_quota_identity")
        }
