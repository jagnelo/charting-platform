"""SQLite smoke coverage for durable market-event consensus migration."""

import importlib.util
from pathlib import Path

from sqlalchemy import (
    Column,
    Date,
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
    path = Path(__file__).parents[3] / "alembic" / "versions" / (
        "a1b2c3d4e5f6_add_market_event_consensus.py"
    )
    spec = importlib.util.spec_from_file_location("market_event_consensus", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_market_event_consensus_migration_adds_link_and_reverses_cleanly():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("instrument", metadata, Column("id", Integer, primary_key=True))
    Table("issuer", metadata, Column("id", Integer, primary_key=True))
    Table(
        "market_event",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("instrument_id", Integer, nullable=True),
        Column("issuer_id", Integer, nullable=True),
        Column("event_type", String(80), nullable=False),
        Column("event_key", String(180), nullable=False),
        Column("event_time", DateTime, nullable=True),
        Column("effective_date", Date, nullable=True),
        Column("announced_at", DateTime, nullable=True),
        Column("source", String(80), nullable=False),
        Column("source_version", String(80), nullable=True),
        Column("payload", String, nullable=False),
        Column("is_provisional", Integer, nullable=False),
    )
    metadata.create_all(engine)
    module = _migration_module()

    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        module.op = operations
        module.upgrade()

        consensus_columns = {
            column["name"] for column in inspect(connection).get_columns("market_event_consensus")
        }
        assert {"consensus_key", "status", "conflict_fields", "provenance"} <= consensus_columns
        event_columns = {column["name"] for column in inspect(connection).get_columns("market_event")}
        assert "consensus_id" in event_columns
        connection.exec_driver_sql(
            "INSERT INTO market_event_consensus "
            "(consensus_key, event_type, first_observed_at, last_observed_at) "
            "VALUES ('test-consensus', 'earnings', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.exec_driver_sql(
            "INSERT INTO market_event "
            "(id, event_type, event_key, source, payload, is_provisional, consensus_id) "
            "VALUES (1, 'earnings', 'event-1', 'fixture', '{}', 0, "
            "(SELECT id FROM market_event_consensus WHERE consensus_key = 'test-consensus'))"
        )
        assert connection.exec_driver_sql(
            "SELECT consensus_id FROM market_event WHERE id = 1"
        ).scalar_one() is not None

        module.downgrade()
        assert "market_event_consensus" not in inspect(connection).get_table_names()
        assert "consensus_id" not in {
            column["name"] for column in inspect(connection).get_columns("market_event")
        }
