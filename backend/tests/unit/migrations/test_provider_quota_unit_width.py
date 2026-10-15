"""Quota window migration must preserve large byte-based allowances."""

import importlib.util
from pathlib import Path

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    inspect,
)

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = (
        Path(__file__).parents[3]
        / "alembic"
        / "versions"
        / ("c1d2e3f4a5b6_widen_provider_quota_units.py")
    )
    spec = importlib.util.spec_from_file_location("provider_quota_unit_width", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_provider_quota_migration_preserves_large_limits_and_usage():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table(
        "provider_quota_window",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("data_source_id", Integer, nullable=False),
        Column("capability", String(80), nullable=False),
        Column("dimension", String(80), nullable=False),
        Column("window_started_at", DateTime, nullable=False),
        Column("window_seconds", Integer, nullable=False),
        Column("limit_units", Integer, nullable=False),
        Column("reserved_units", Integer, nullable=False),
        Column("consumed_units", Integer, nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO provider_quota_window VALUES "
            "(1, 1, 'finra', 'bytes_per_month', '2026-10-01', 2592000, 100, 20, 30)"
        )
        module = _migration_module()
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        connection.exec_driver_sql(
            "UPDATE provider_quota_window SET limit_units = 10000000000, "
            "reserved_units = 6000000000, consumed_units = 3000000000 WHERE id = 1"
        )
        assert connection.exec_driver_sql(
            "SELECT limit_units, reserved_units, consumed_units FROM provider_quota_window WHERE id = 1"
        ).one() == (10_000_000_000, 6_000_000_000, 3_000_000_000)
        assert all(
            column["type"].__class__.__name__.lower().startswith("bigint")
            for column in inspect(connection).get_columns("provider_quota_window")
            if column["name"] in {"limit_units", "reserved_units", "consumed_units"}
        )

        try:
            module.downgrade()
        except RuntimeError as exc:
            assert "exceed 32-bit range" in str(exc)
        else:
            raise AssertionError("downgrade must not truncate a large quota value")
