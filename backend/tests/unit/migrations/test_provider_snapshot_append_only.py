"""Migration coverage for repeated provider snapshot evidence."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import (
    Column,
    Date,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    inspect,
    text,
)

from alembic.migration import MigrationContext
from alembic.operations import Operations

_TABLES = {
    "instrument_profile_snapshot": ("instrument_id", "data_source_id", "profile_hash"),
    "instrument_identifier_snapshot": ("instrument_id", "data_source_id", "snapshot_hash"),
    "instrument_search_snapshot": ("data_source_id", "query", "result_hash"),
    "universe_discovery_snapshot": ("data_source_id", "quote_type", "offset", "snapshot_hash"),
    "option_chain_snapshot": (
        "underlying_instrument_id",
        "data_source_id",
        "expiration_date",
        "snapshot_hash",
    ),
}


def _migration_module():
    path = Path(__file__).parents[3] / "alembic" / "versions" / (
        "e8f9a0b1c2d3_make_provider_snapshots_append_only.py"
    )
    spec = importlib.util.spec_from_file_location("provider_snapshot_append_only", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_provider_snapshot_migration_allows_repeated_payloads_and_guards_downgrade():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    for table_name, columns in _TABLES.items():
        column_defs = [Column("id", Integer, primary_key=True)]
        for name in columns:
            column_type = Date if name == "expiration_date" else String
            column_defs.append(Column(name, column_type, nullable=False))
        Table(
            table_name,
            metadata,
            *column_defs,
            UniqueConstraint(*columns, name={
                "instrument_profile_snapshot": "uq_instrument_profile_snapshot_hash",
                "instrument_identifier_snapshot": "uq_instrument_identifier_snapshot_hash",
                "instrument_search_snapshot": "uq_instrument_search_snapshot_hash",
                "universe_discovery_snapshot": "uq_universe_discovery_snapshot_hash",
                "option_chain_snapshot": "uq_option_chain_snapshot_hash",
            }[table_name]),
        )
    metadata.create_all(engine)
    module = _migration_module()

    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        module.op = operations
        module.upgrade()
        for table_name in _TABLES:
            assert not inspect(connection).get_unique_constraints(table_name)
        connection.execute(
            text(
                "INSERT INTO instrument_search_snapshot "
                "(id, data_source_id, query, result_hash) VALUES "
                "(1, 'source', 'AAPL', 'same'), (2, 'source', 'AAPL', 'same')"
            )
        )
        with pytest.raises(RuntimeError, match="repeated provider evidence"):
            module.downgrade()
