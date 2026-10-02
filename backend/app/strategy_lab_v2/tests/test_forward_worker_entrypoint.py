from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.forward_worker_entrypoint import (
    ForwardWorkerEntrypointConfig,
    ForwardWorkerEntrypointDecision,
    ForwardWorkerEntrypointStartupError,
    _load_callback_factory,
    run_forward_strategy_lab_v2_worker,
)
from app.strategy_lab_v2.migration_startup import MigrationDecision, MigrationResolution


def _migration(decision: MigrationDecision) -> MigrationResolution:
    return MigrationResolution(
        content_digest("forward-migration-request"),
        decision,
        "head",
        content_digest("forward-migration-error") if decision is MigrationDecision.FAILED else None,
    )


class _Migration:
    def __init__(self, decision: MigrationDecision) -> None:
        self.decision = decision

    async def upgrade(self) -> MigrationResolution:
        return _migration(self.decision)


def _config(**overrides: Any) -> ForwardWorkerEntrypointConfig:
    values: dict[str, Any] = {
        "redis_url": "redis://localhost:6379/0",
        "database_url_sync": "postgresql+psycopg2://localhost/chartingdb",
    }
    values.update(overrides)
    return ForwardWorkerEntrypointConfig(**values)


def test_forward_config_reads_namespaced_environment_and_requires_callback_at_runtime() -> None:
    config = ForwardWorkerEntrypointConfig.from_env(
        {
            "REDIS_URL": "redis://legacy:6379/0",
            "DATABASE_URL_SYNC": "postgresql+psycopg2://legacy/chartingdb",
            "STRATEGY_LAB_V2_FORWARD_DATABASE_URL_SYNC": "postgresql+psycopg2://forward/chartingdb",
            "STRATEGY_LAB_V2_FORWARD_CALLBACK_FACTORY": "callbacks:create",
            "STRATEGY_LAB_V2_FORWARD_QUEUE": "forward-test",
            "STRATEGY_LAB_V2_FORWARD_BATCH_SIZE": "3",
            "STRATEGY_LAB_V2_FORWARD_MIGRATIONS_ENABLED": "false",
        }
    )

    assert config.redis_url == "redis://legacy:6379/0"
    assert config.database_url_sync == "postgresql+psycopg2://forward/chartingdb"
    assert config.callback_factory == "callbacks:create"
    assert config.queue_name == "forward-test"
    assert config.batch_size == 3
    assert config.migration_enabled is False

    with pytest.raises(ValueError, match="boolean"):
        ForwardWorkerEntrypointConfig.from_env(
            {"STRATEGY_LAB_V2_FORWARD_MIGRATIONS_ENABLED": "maybe"}
        )
    with pytest.raises(ValueError, match="configured"):
        _load_callback_factory(None)


def test_forward_callback_factory_loader_requires_module_attribute_syntax() -> None:
    with pytest.raises(ValueError, match="module:attribute"):
        _load_callback_factory("callbacks.create")
    with pytest.raises(ModuleNotFoundError):
        _load_callback_factory("missing_strategy_lab_callbacks:create")


@pytest.mark.asyncio
async def test_failed_forward_startup_migration_never_opens_redis() -> None:
    opened = False

    async def runtime_factory(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal opened
        opened = True
        raise AssertionError("Redis must not open after a failed migration")

    result = await run_forward_strategy_lab_v2_worker(
        _config(),
        migration_service=_Migration(MigrationDecision.FAILED),  # type: ignore[arg-type]
        runtime_factory=runtime_factory,
    )

    assert result.decision is ForwardWorkerEntrypointDecision.MIGRATION_FAILED
    assert result.migration is not None
    assert result.migration.error_digest == content_digest("forward-migration-error")
    assert opened is False
    with pytest.raises(ForwardWorkerEntrypointStartupError):
        raise ForwardWorkerEntrypointStartupError(result)


@pytest.mark.asyncio
async def test_forward_worker_composes_dedicated_queue_and_closes_runtime() -> None:
    calls: dict[str, Any] = {}
    stop_event = asyncio.Event()
    stop_event.set()

    class Persistence:
        forward_dispatch = object()
        execution_events = None

    class Service:
        async def run(self, event: asyncio.Event, *, max_cycles: int | None = None):
            assert event is stop_event
            assert max_cycles == 2
            return ()

    class Runtime:
        def worker(self, **kwargs: Any) -> object:
            calls["worker"] = kwargs
            return object()

        def forward_worker_service(self, worker: object, **kwargs: Any) -> Service:
            calls["service"] = (worker, kwargs)
            return Service()

        async def aclose(self) -> None:
            calls["closed"] = True

    async def runtime_factory(*_args: Any, **_kwargs: Any) -> Runtime:
        return Runtime()

    result = await run_forward_strategy_lab_v2_worker(
        _config(reclaim_idle_ms=11, batch_size=2, block_ms=7, interval_seconds=2),
        callback_factory=lambda _persistence: (lambda *_a: None, lambda *_a: None),  # type: ignore[arg-type,return-value]
        migration_service=_Migration(MigrationDecision.APPLIED),  # type: ignore[arg-type]
        session_factory=lambda: object(),
        persistence_factory=lambda _factory: Persistence(),  # type: ignore[arg-type,return-value]
        runtime_factory=runtime_factory,
        signal_installer=lambda _event: lambda: None,
        stop_event=stop_event,
        sleep=lambda _seconds: asyncio.sleep(0),
        max_cycles=2,
    )

    assert result.decision is ForwardWorkerEntrypointDecision.STOPPED
    assert result.cycles == ()
    assert result.runtime_closed is True
    assert calls["worker"] == {
        "queue_name": "forward-events",
        "group_name": "strategy-lab-v2-forward",
        "consumer_name": "local-forward-worker",
        "reclaim_idle_ms": 11,
        "batch_size": 2,
        "block_ms": 7,
    }
    assert calls["service"][1]["payload_loader"] is Persistence.forward_dispatch
    assert calls["service"][1]["interval_seconds"] == 2
    assert calls["closed"] is True
