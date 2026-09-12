"""SQLite smoke coverage for scoped OHLCV conflict-key migration."""

import importlib.util
from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
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
        "9f0a1b2c3d4e_add_scoped_ohlcv_conflict_keys.py"
    )
    spec = importlib.util.spec_from_file_location("scoped_ohlcv_keys", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_scoped_ohlcv_conflict_key_migration_backfills_and_reverses():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table(
        "ohlcv_bar",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("instrument_id", Integer, nullable=False),
        Column("timeframe", String(12), nullable=False),
        Column("ts", DateTime, nullable=False),
        Column("is_adjusted", Boolean, nullable=False),
        Column("session", String(16), nullable=False, server_default="regular"),
        Column("market_series_id", Integer, nullable=True),
        Index(
            "uq_ohlcv_bar",
            "instrument_id",
            "timeframe",
            "ts",
            "is_adjusted",
            unique=True,
        ),
    )
    Table(
        "market_bar_observation",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("instrument_id", Integer, nullable=False),
        Column("data_source_id", Integer, nullable=False),
        Column("timeframe", String(12), nullable=False),
        Column("ts", DateTime, nullable=False),
        Column("is_adjusted", Boolean, nullable=False),
        Column("session", String(16), nullable=False, server_default="regular"),
        Column("market_series_id", Integer, nullable=True),
        UniqueConstraint(
            "instrument_id",
            "data_source_id",
            "timeframe",
            "ts",
            "is_adjusted",
            name="uq_market_bar_observation",
        ),
    )
    metadata.create_all(engine)
    module = _migration_module()

    with engine.begin() as connection:
        connection.execute(
            metadata.tables["ohlcv_bar"].insert(),
            {
                "id": 1,
                "instrument_id": 42,
                "timeframe": "D1",
                "ts": datetime(2026, 1, 2),
                "is_adjusted": False,
                "session": "regular",
                "market_series_id": None,
            },
        )
        connection.execute(
            metadata.tables["market_bar_observation"].insert(),
            {
                "id": 1,
                "instrument_id": 42,
                "data_source_id": 7,
                "timeframe": "D1",
                "ts": datetime(2026, 1, 2),
                "is_adjusted": False,
                "session": "extended",
                "market_series_id": 99,
            },
        )
        operations = Operations(MigrationContext.configure(connection))
        module.op = operations
        module.upgrade()

        assert connection.exec_driver_sql(
            "SELECT scope_key FROM ohlcv_bar WHERE id = 1"
        ).scalar_one() == "legacy:regular"
        assert connection.exec_driver_sql(
            "SELECT scope_key FROM market_bar_observation WHERE id = 1"
        ).scalar_one() == "series:99:extended"
        assert "scope_key" in {
            column["name"] for column in inspect(connection).get_columns("ohlcv_bar")
        }

        module.downgrade()
        assert "scope_key" not in {
            column["name"] for column in inspect(connection).get_columns("ohlcv_bar")
        }
        assert "uq_ohlcv_bar" in {
            index["name"] for index in inspect(connection).get_indexes("ohlcv_bar")
        }
