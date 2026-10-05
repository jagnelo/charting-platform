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
_RECOVERY_MIGRATION_PATH = _MIGRATION_PATH.with_name(
    "ff3a4b5c6d7e_add_strategy_lab_v2_worker_recoveries.py"
)
_SEARCH_RETRY_MIGRATION_PATH = _MIGRATION_PATH.with_name(
    "ff4a5b6c7d8e_allow_search_candidate_attempt_retries.py"
)
_FORWARD_LIFECYCLE_MIGRATION_PATH = _MIGRATION_PATH.with_name(
    "ff5a6b7c8d9e_strategy_lab_forward_lifecycle_idempotency.py"
)
_FORWARD_DISPATCH_CONTEXT_MIGRATION_PATH = _MIGRATION_PATH.with_name(
    "ff6a7b8c9d0e_bind_forward_dispatch_checkpoint.py"
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


def _recovery_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "strategy_lab_v2_worker_recovery_migration", _RECOVERY_MIGRATION_PATH
    )
    if spec is None or spec.loader is None:
        raise AssertionError("could not load the Strategy Lab worker-recovery migration")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _search_retry_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "strategy_lab_v2_search_retry_migration", _SEARCH_RETRY_MIGRATION_PATH
    )
    if spec is None or spec.loader is None:
        raise AssertionError("could not load the Strategy Lab search-retry migration")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _forward_lifecycle_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "strategy_lab_v2_forward_lifecycle_migration",
        _FORWARD_LIFECYCLE_MIGRATION_PATH,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("could not load the forward lifecycle migration")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _forward_dispatch_context_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "strategy_lab_v2_forward_dispatch_context_migration",
        _FORWARD_DISPATCH_CONTEXT_MIGRATION_PATH,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("could not load the forward dispatch context migration")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_additive_migration_covers_all_v2_adapter_tables_without_legacy_tables() -> None:
    migration = _migration()
    tables = tuple(name for name, _ in migration._DDL)

    assert migration.revision == "ff0a1b2c3d4e"
    assert len(tables) == 43
    assert len(set(tables)) == len(tables)
    assert "strategy_definition" not in tables
    assert "strategy_version" not in tables
    assert "strategy_run" not in tables
    assert "strategy_lab_v2_execution_admissions" in tables
    assert "strategy_lab_v2_search_dispatches" in tables
    assert "strategy_lab_v2_forward_event_dispatches" in tables
    assert "strategy_lab_v2_forward_accounts" in tables
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


def test_worker_recovery_migration_is_additive_and_follows_settlement_receipts() -> None:
    migration = _recovery_migration()

    assert migration.revision == "ff3a4b5c6d7e"
    assert migration.down_revision == "ff2a3b4c5d6e"
    upgrade_constants = tuple(str(value) for value in migration.upgrade.__code__.co_consts)
    assert any(
        "CREATE TABLE strategy_lab_v2_worker_recoveries" in value for value in upgrade_constants
    )
    assert any("UNIQUE (owner_id, attempt_id)" in value for value in upgrade_constants)
    assert any("reason TEXT NOT NULL" in value for value in upgrade_constants)
    downgrade_constants = tuple(str(value) for value in migration.downgrade.__code__.co_consts)
    assert any(
        "DROP TABLE strategy_lab_v2_worker_recoveries" in value for value in downgrade_constants
    )


def test_search_retry_migration_allows_attempt_lineage_per_candidate() -> None:
    migration = _search_retry_migration()

    assert migration.revision == "ff4a5b6c7d8e"
    assert migration.down_revision == "ff3a4b5c6d7e"
    upgrade_constants = tuple(str(value) for value in migration.upgrade.__code__.co_consts)
    assert any("pg_get_constraintdef" in value for value in upgrade_constants)
    assert any(
        "UNIQUE (owner_id, experiment_fingerprint, candidate_index, attempt_id)" in value
        for value in upgrade_constants
    )
    downgrade_constants = tuple(str(value) for value in migration.downgrade.__code__.co_consts)
    assert any(
        "DROP CONSTRAINT strategy_lab_v2_search_dispatch_candidate_attempt_key" in value
        for value in downgrade_constants
    )


def test_forward_lifecycle_idempotency_migration_is_additive_and_receipt_scoped() -> None:
    migration = _forward_lifecycle_migration()

    assert migration.revision == "ff5a6b7c8d9e"
    assert migration.down_revision == "ff4a5b6c7d8e"
    upgrade_constants = tuple(str(value) for value in migration.upgrade.__code__.co_consts)
    assert any(
        "CREATE TABLE strategy_lab_v2_forward_lifecycle_requests" in value
        and "PRIMARY KEY (owner_id, instance_id, idempotency_key_digest)" in value
        for value in upgrade_constants
    )
    downgrade_constants = tuple(str(value) for value in migration.downgrade.__code__.co_consts)
    assert any(
        "DROP TABLE strategy_lab_v2_forward_lifecycle_requests" in value
        for value in downgrade_constants
    )


def test_forward_dispatch_migration_binds_admission_checkpoint_and_warmup() -> None:
    migration = _forward_dispatch_context_migration()

    assert migration.revision == "ff6a7b8c9d0e"
    assert migration.down_revision == "ff5a6b7c8d9e"
    upgrade_constants = tuple(str(value) for value in migration.upgrade.__code__.co_consts)
    assert any("pre_event_checkpoint_fingerprint TEXT NULL" in value for value in upgrade_constants)
    assert any("warmup_receipt_fingerprint TEXT NULL" in value for value in upgrade_constants)
    assert any(
        "admission_decision IN ('enqueue', 'buffered', 'correction_enqueue')" in value
        for value in upgrade_constants
    )
    downgrade_constants = tuple(str(value) for value in migration.downgrade.__code__.co_consts)
    assert any(
        "DROP COLUMN pre_event_checkpoint_fingerprint" in value for value in downgrade_constants
    )
