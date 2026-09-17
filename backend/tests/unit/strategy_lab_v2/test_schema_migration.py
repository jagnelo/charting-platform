from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

_MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "alembic"
    / "versions"
    / "ff0a1b2c3d4e_add_strategy_lab_v2_storage.py"
)
_PAYLOAD_MIGRATION_PATH = _MIGRATION_PATH.with_name(
    "ff1a2b3c4d5e_add_strategy_lab_v2_dispatch_payloads.py"
)


def _migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("strategy_lab_v2_migration", _MIGRATION_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load the Strategy Lab v2 migration")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _payload_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "strategy_lab_v2_payload_migration", _PAYLOAD_MIGRATION_PATH
    )
    if spec is None or spec.loader is None:
        raise AssertionError("could not load the Strategy Lab dispatch-payload migration")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_additive_migration_covers_all_v2_adapter_tables_without_legacy_tables() -> None:
    migration = _migration()
    tables = tuple(name for name, _ in migration._DDL)

    assert migration.revision == "ff0a1b2c3d4e"
    assert len(tables) == 39
    assert len(set(tables)) == len(tables)
    assert "strategy_definition" not in tables
    assert "strategy_version" not in tables
    assert "strategy_run" not in tables
    for table_name, statement in migration._DDL:
        assert f"CREATE TABLE {table_name}" in statement
    assert any(
        "strategy_lab_v2_worker_reservations_active_attempt_key" in str(constant)
        for constant in migration.upgrade.__code__.co_consts
    )


def test_dispatch_payload_migration_is_additive_and_follows_storage() -> None:
    migration = _payload_migration()

    assert migration.revision == "ff1a2b3c4d5e"
    assert migration.down_revision == "ff0a1b2c3d4e"
    constants = tuple(str(constant) for constant in migration.upgrade.__code__.co_consts)
    assert any("CREATE TABLE strategy_lab_v2_dispatch_payloads" in value for value in constants)
    down_constants = tuple(str(constant) for constant in migration.downgrade.__code__.co_consts)
    assert any("DROP TABLE strategy_lab_v2_dispatch_payloads" in value for value in down_constants)
