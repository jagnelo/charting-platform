from __future__ import annotations

from pathlib import Path

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.migration_startup import (
    MigrationDecision,
    StrategyLabV2MigrationService,
    create_strategy_lab_v2_migration_service,
)


async def test_migration_service_runs_off_loop_and_replays_exact_success(tmp_path: Path) -> None:
    calls: list[tuple[str, str, str]] = []

    def runner(database_url: str, script_location: str, target_revision: str) -> None:
        calls.append((database_url, script_location, target_revision))

    service = StrategyLabV2MigrationService(
        "postgresql://user:password@localhost/chartingdb",
        script_location=tmp_path,
        runner=runner,
    )
    applied = await service.upgrade()
    replay = await service.upgrade()

    assert applied.decision is MigrationDecision.APPLIED
    assert replay.decision is MigrationDecision.REPLAY_EXISTING
    assert replay.error_digest is None
    assert calls == [
        ("postgresql://user:password@localhost/chartingdb", str(tmp_path), "head")
    ]


async def test_migration_service_redacts_failure_to_stable_type_digest(tmp_path: Path) -> None:
    def runner(*_args: str) -> None:
        raise RuntimeError("database password and host must not escape")

    service = StrategyLabV2MigrationService(
        "postgresql+psycopg2://user:secret@localhost/chartingdb",
        script_location=tmp_path,
        runner=runner,
    )
    failed = await service.upgrade()
    replay = await service.upgrade()

    assert failed.decision is MigrationDecision.FAILED
    assert failed.error_digest == content_digest(
        {
            "type": "builtins.RuntimeError",
            "version": "strategy-lab.migration-startup.error.v1",
        }
    )
    assert replay.decision is MigrationDecision.REPLAY_EXISTING
    assert replay.error_digest == failed.error_digest


def test_migration_factory_and_configuration_fail_closed(tmp_path: Path) -> None:
    service = create_strategy_lab_v2_migration_service(
        "postgresql://localhost/chartingdb",
        script_location=tmp_path,
    )
    assert isinstance(service, StrategyLabV2MigrationService)
    with pytest.raises(ValueError, match="PostgreSQL"):
        StrategyLabV2MigrationService(
            "sqlite:///:memory:",
            script_location=tmp_path,
        )
    with pytest.raises(ValueError, match="absolute"):
        StrategyLabV2MigrationService(
            "postgresql://localhost/chartingdb",
            script_location="relative",
        )
    with pytest.raises(ValueError, match="unsafe"):
        StrategyLabV2MigrationService(
            "postgresql://localhost/chartingdb",
            script_location=tmp_path,
            target_revision="head;drop",
        )
