"""Migration coverage for durable availability-probe response evidence."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, text

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = Path(__file__).parents[3] / "alembic" / "versions" / (
        "e8f9a0b1c2e5_add_provider_availability_response_payload.py"
    )
    spec = importlib.util.spec_from_file_location("availability_response_payload", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_adds_response_payload_and_downgrade_refuses_data_loss():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table(
        "provider_availability_observation",
        metadata,
        Column("id", Integer, primary_key=True),
    )
    metadata.create_all(engine)
    module = _migration_module()

    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        module.op = operations
        module.upgrade()
        connection.execute(
            text(
                "INSERT INTO provider_availability_observation "
                "(id, response_payload) VALUES (1, '{\"rows\": [1]}')"
            )
        )
        with pytest.raises(RuntimeError, match="response evidence exists"):
            module.downgrade()
