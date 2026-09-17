from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.migration_startup import (
    MigrationDecision,
    MigrationResolution,
)
from app.strategy_lab_v2.redis_application import RedisDispatchRuntime
from app.strategy_lab_v2.redis_transport import RedisDispatchTransport
from app.strategy_lab_v2.tests.test_worker_consumer import FakeRedis
from app.strategy_lab_v2.worker_entrypoint import (
    WorkerEntrypointConfig,
    WorkerEntrypointDecision,
    WorkerEntrypointStartupError,
    _load_callback_factory,
    run_strategy_lab_v2_worker,
)


def _migration(decision: MigrationDecision) -> MigrationResolution:
    return MigrationResolution(
        content_digest("migration-request"),
        decision,
        "head",
        content_digest("migration-error") if decision is MigrationDecision.FAILED else None,
    )


class _Migration:
    def __init__(self, decision: MigrationDecision) -> None:
        self.decision = decision

    async def upgrade(self) -> MigrationResolution:
        return _migration(self.decision)


def _config(**overrides: Any) -> WorkerEntrypointConfig:
    values: dict[str, Any] = {
        "redis_url": "redis://localhost:6379/0",
        "database_url_sync": "postgresql+psycopg2://localhost/chartingdb",
        "artifact_root": Path("/tmp/strategy-lab-v2-artifacts"),
    }
    values.update(overrides)
    return WorkerEntrypointConfig(**values)


def test_worker_config_reads_namespaced_environment_and_fails_closed() -> None:
    config = WorkerEntrypointConfig.from_env(
        {
            "REDIS_URL": "redis://legacy:6379/0",
            "DATABASE_URL_SYNC": "postgresql+psycopg2://legacy/chartingdb",
            "STRATEGY_LAB_V2_ARTIFACT_ROOT": "/var/lib/strategy-lab/artifacts",
            "STRATEGY_LAB_V2_CALLBACK_FACTORY": "callbacks:create",
            "STRATEGY_LAB_V2_BATCH_SIZE": "3",
            "STRATEGY_LAB_V2_MIGRATIONS_ENABLED": "false",
        }
    )

    assert config.redis_url == "redis://legacy:6379/0"
    assert config.database_url_sync.startswith("postgresql+")
    assert config.artifact_root == Path("/var/lib/strategy-lab/artifacts")
    assert config.callback_factory == "callbacks:create"
    assert config.batch_size == 3
    assert config.migration_enabled is False

    with pytest.raises(ValueError, match="boolean"):
        WorkerEntrypointConfig.from_env({"STRATEGY_LAB_V2_MIGRATIONS_ENABLED": "maybe"})
    with pytest.raises(ValueError, match="absolute"):
        _config(artifact_root=Path("relative"))


def test_callback_factory_loader_requires_module_attribute_syntax() -> None:
    with pytest.raises(ValueError, match="module:attribute"):
        _load_callback_factory("callbacks.create")
    with pytest.raises(ModuleNotFoundError):
        _load_callback_factory("missing_strategy_lab_callbacks:create")


async def test_failed_startup_migration_never_opens_redis() -> None:
    opened = False

    async def runtime_factory(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal opened
        opened = True
        raise AssertionError("Redis must not open after a failed migration")

    class FailedMigration:
        async def upgrade(self) -> MigrationResolution:
            return _migration(MigrationDecision.FAILED)

    result = await run_strategy_lab_v2_worker(
        _config(),
        migration_service=FailedMigration(),  # type: ignore[arg-type]
        runtime_factory=runtime_factory,
    )

    assert result.decision is WorkerEntrypointDecision.MIGRATION_FAILED
    assert result.migration is not None
    assert result.migration.error_digest == content_digest("migration-error")
    assert opened is False

    with pytest.raises(WorkerEntrypointStartupError) as error:
        raise WorkerEntrypointStartupError(result)
    assert error.value.error_digest == content_digest("migration-error")


async def test_successful_worker_owns_runtime_close_and_signal_cleanup() -> None:
    class ClosableFakeRedis(FakeRedis):
        async def aclose(self) -> None:
            return None

    redis_client = ClosableFakeRedis()
    runtime = RedisDispatchRuntime(redis_client, RedisDispatchTransport(redis_client))
    events: list[str] = []
    stop_event = asyncio.Event()
    stop_event.set()

    class Persistence:
        class submissions:
            async def load_payload(self, _payload_digest: str) -> None:
                return None

    def persistence_factory(_session_factory: Any) -> Persistence:
        return Persistence()

    async def materializer(*_args: Any) -> Any:
        raise AssertionError("a pre-stopped worker must not materialize work")

    async def completion(*_args: Any) -> Any:
        raise AssertionError("a pre-stopped worker must not complete work")

    def callback_factory(_persistence: Any, root: Path):
        assert root == Path("/tmp/strategy-lab-v2-artifacts")
        return materializer, completion

    async def runtime_factory(*_args: Any, **_kwargs: Any) -> RedisDispatchRuntime:
        return runtime

    def install(event: asyncio.Event):
        assert event is stop_event
        events.append("install")

        def cleanup() -> None:
            events.append("cleanup")

        return cleanup

    result = await run_strategy_lab_v2_worker(
        _config(),
        callback_factory=callback_factory,
        migration_service=_Migration(MigrationDecision.APPLIED),  # type: ignore[arg-type]
        session_factory=lambda: object(),
        persistence_factory=persistence_factory,  # type: ignore[arg-type]
        runtime_factory=runtime_factory,
        signal_installer=install,
        stop_event=stop_event,
        sleep=lambda _seconds: asyncio.sleep(0),
    )

    assert result.decision is WorkerEntrypointDecision.STOPPED
    assert result.migration is not None
    assert result.migration.decision is MigrationDecision.APPLIED
    assert result.cycles == ()
    assert result.runtime_closed is True
    assert events == ["install", "cleanup"]
    assert redis_client is not None


async def test_runtime_composition_receives_worker_limits_and_process_executor() -> None:
    calls: dict[str, Any] = {}
    stop_event = asyncio.Event()
    stop_event.set()

    class Runtime:
        def worker(self, **kwargs: Any) -> object:
            calls["worker"] = kwargs
            return object()

        def worker_service(self, worker: object, **kwargs: Any) -> Any:
            calls["service"] = (worker, kwargs)
            return _StoppedService()

        async def aclose(self) -> None:
            calls["closed"] = True

    class Persistence:
        submissions = object()

    class _Executor:
        pass

    class _StoppedService:
        async def run(self, event: asyncio.Event, *, max_cycles: int | None = None):
            assert event is stop_event
            assert max_cycles == 2
            return ()

    async def runtime_factory(*_args: Any, **_kwargs: Any) -> Runtime:
        return Runtime()

    result = await run_strategy_lab_v2_worker(
        _config(
            reclaim_idle_ms=11,
            batch_size=2,
            block_ms=7,
            interval_seconds=2,
            process_timeout_seconds=13,
        ),
        callback_factory=lambda *_args: (lambda *_a: None, lambda *_a: None),  # type: ignore[arg-type]
        migration_service=_Migration(MigrationDecision.APPLIED),  # type: ignore[arg-type]
        session_factory=lambda: object(),
        persistence_factory=lambda _factory: Persistence(),  # type: ignore[arg-type,return-value]
        runtime_factory=runtime_factory,
        signal_installer=lambda _event: lambda: None,
        stop_event=stop_event,
        process_executor=_Executor(),  # type: ignore[arg-type]
        max_cycles=2,
    )

    assert result.cycles == ()
    assert calls["worker"] == {
        "queue_name": "backtest",
        "group_name": "strategy-lab-v2",
        "consumer_name": "local-worker",
        "reclaim_idle_ms": 11,
        "batch_size": 2,
        "block_ms": 7,
    }
    assert calls["service"][1]["interval_seconds"] == 2
    assert calls["service"][1]["process_executor"] is not None
    assert calls["closed"] is True
