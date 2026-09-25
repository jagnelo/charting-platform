"""SQLite coverage for immutable raw market-bar observation history."""

import importlib.util
from datetime import datetime
from pathlib import Path

from sqlalchemy import (
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
        "d1e2f3a4b5c6_make_market_bar_observations_append_only.py"
    )
    spec = importlib.util.spec_from_file_location("market_bar_observation_append_only", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_market_bar_observation_migration_adds_observation_time_to_key():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table(
        "market_bar_observation",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("instrument_id", Integer, nullable=False),
        Column("data_source_id", Integer, nullable=False),
        Column("timeframe", String(12), nullable=False),
        Column("ts", DateTime, nullable=False),
        Column("is_adjusted", Integer, nullable=False),
        Column("scope_key", String(180), nullable=False),
        Column("observed_at", DateTime, nullable=False),
        UniqueConstraint(
            "instrument_id",
            "data_source_id",
            "timeframe",
            "ts",
            "is_adjusted",
            "scope_key",
            name="uq_market_bar_observation",
        ),
    )
    metadata.create_all(engine)
    module = _migration_module()

    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        module.op = operations
        module.upgrade()
        constraints = inspect(connection).get_unique_constraints("market_bar_observation")
        columns = next(item["column_names"] for item in constraints if item["name"] == "uq_market_bar_observation")
        assert columns[-1] == "observed_at"

        table = metadata.tables["market_bar_observation"]
        base = {
            "instrument_id": 42,
            "data_source_id": 7,
            "timeframe": "D1",
            "ts": datetime(2026, 1, 2),
            "is_adjusted": 0,
            "scope_key": "series:99:regular",
        }
        connection.execute(table.insert(), {**base, "observed_at": datetime(2026, 1, 3)})
        connection.execute(table.insert(), {**base, "observed_at": datetime(2026, 1, 4)})
        assert connection.exec_driver_sql(
            "SELECT COUNT(*) FROM market_bar_observation"
        ).scalar_one() == 2
