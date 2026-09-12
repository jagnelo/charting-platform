"""SQLite smoke coverage for tokenized underlying identifier columns."""

import importlib.util
from pathlib import Path

from sqlalchemy import Column, Integer, MetaData, Table, create_engine, inspect

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = Path(__file__).parents[3] / "alembic" / "versions" / (
        "b4c5d6e7f8a9_add_tokenized_underlying_identifiers.py"
    )
    spec = importlib.util.spec_from_file_location("tokenized_underlying_identifiers", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tokenized_underlying_identifier_migration_adds_and_removes_columns():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("tokenized_asset_detail", metadata, Column("id", Integer, primary_key=True))
    metadata.create_all(engine)
    module = _migration_module()

    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        module.op = operations
        module.upgrade()
        columns = {column["name"] for column in inspect(connection).get_columns("tokenized_asset_detail")}
        assert {"underlying_figi", "underlying_composite_figi", "underlying_cusip"} <= columns

        module.downgrade()
        columns = {column["name"] for column in inspect(connection).get_columns("tokenized_asset_detail")}
        assert not {"underlying_figi", "underlying_composite_figi", "underlying_cusip"} & columns
