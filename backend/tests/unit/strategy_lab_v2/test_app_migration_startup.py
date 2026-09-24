from __future__ import annotations

import pytest

from app.config import settings
from app.main import _run_strategy_lab_v2_startup_migrations
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.migration_startup import MigrationDecision, MigrationResolution


class _MigrationService:
    def __init__(self, resolution: MigrationResolution) -> None:
        self.resolution = resolution
        self.calls = 0

    async def upgrade(self) -> MigrationResolution:
        self.calls += 1
        return self.resolution


@pytest.mark.asyncio
async def test_api_startup_migrations_are_explicit_and_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    resolution = MigrationResolution(content_digest("request"), MigrationDecision.APPLIED, "head")
    service = _MigrationService(resolution)
    captured: dict[str, object] = {}

    def factory(database_url: str, *, script_location: object, target_revision: str):
        captured.update(
            {
                "database_url": database_url,
                "script_location": script_location,
                "target_revision": target_revision,
            }
        )
        return service

    monkeypatch.setattr(settings, "STRATEGY_LAB_V2_MIGRATIONS_ENABLED", True)
    monkeypatch.setattr(settings, "STRATEGY_LAB_V2_MIGRATION_TARGET", "head")
    monkeypatch.setattr("app.main.create_strategy_lab_v2_migration_service", factory)

    await _run_strategy_lab_v2_startup_migrations()

    assert service.calls == 1
    assert captured["database_url"] == settings.DATABASE_URL_SYNC
    assert captured["target_revision"] == "head"
    assert str(captured["script_location"]).endswith("/backend/alembic")


@pytest.mark.asyncio
async def test_api_startup_migration_failure_stops_before_accepting_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolution = MigrationResolution(
        content_digest("request"),
        MigrationDecision.FAILED,
        "head",
        content_digest("failure"),
    )
    monkeypatch.setattr(settings, "STRATEGY_LAB_V2_MIGRATIONS_ENABLED", True)
    monkeypatch.setattr(
        "app.main.create_strategy_lab_v2_migration_service",
        lambda *_args, **_kwargs: _MigrationService(resolution),
    )

    with pytest.raises(RuntimeError, match="startup migrations failed"):
        await _run_strategy_lab_v2_startup_migrations()
