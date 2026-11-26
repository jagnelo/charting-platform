"""instrument_sync_run.source must hold long provider chains (was varchar(50))."""

import importlib.util
from pathlib import Path

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect

from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.models.instrument_sync_run import InstrumentSyncRun


def _migration_module():
    path = (
        Path(__file__).parents[3]
        / "alembic"
        / "versions"
        / "d5e6f7a8b9c0_widen_instrument_sync_run_source.py"
    )
    spec = importlib.util.spec_from_file_location("sync_run_source_width", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_model_column_matches_migration_width():
    assert InstrumentSyncRun.__table__.c.source.type.length == 255


def test_migration_widens_and_downgrade_refuses_to_truncate():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table(
        "instrument_sync_run",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("source", String(50), nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO instrument_sync_run VALUES (1, 'alpaca')")
        module = _migration_module()
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        cols = {c["name"]: c for c in inspect(connection).get_columns("instrument_sync_run")}
        assert cols["source"]["type"].length == 255
        long_chain = ",".join(f"provider{i}" for i in range(12))
        assert len(long_chain) > 50
        connection.exec_driver_sql(
            "INSERT INTO instrument_sync_run VALUES (2, :v)".replace(":v", f"'{long_chain}'")
        )
        try:
            module.downgrade()
        except RuntimeError as exc:
            assert "Cannot narrow" in str(exc)
        else:
            raise AssertionError("downgrade must not truncate long source values")
        connection.exec_driver_sql("DELETE FROM instrument_sync_run WHERE id = 2")
        module.downgrade()
        assert inspect(connection).get_columns("instrument_sync_run")[1]["type"].length == 50
