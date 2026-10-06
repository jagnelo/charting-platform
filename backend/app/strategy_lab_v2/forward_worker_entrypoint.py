"""Explicit local entrypoint for the isolated forward-event worker.

The forward worker owns only Redis polling, payload rehydration, migration
startup, and orderly shutdown.  Event acquisition and account/engine handling
remain host callbacks, and the callback factory is mandatory so a Compose
service cannot accidentally start with a guessed provider or engine policy.
Importing this module performs no I/O; :func:`main` is the executable boundary.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import socket
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from importlib import import_module
from types import ModuleType
from typing import Any, cast

from app.strategy_lab_v2.forward_worker_authorization import (
    AuthorizedForwardEventHandler,
    ForwardWorkerAuthorizationResolver,
)
from app.strategy_lab_v2.forward_worker_service import (
    ForwardEventHandler,
    ForwardEventMaterializer,
)
from app.strategy_lab_v2.migration_startup import (
    MigrationDecision,
    MigrationResolution,
    StrategyLabV2MigrationService,
    create_strategy_lab_v2_migration_service,
)
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.redis_application import RedisDispatchRuntime
from app.strategy_lab_v2.worker_consumer import WorkerCycleResolution
from app.strategy_lab_v2.worker_entrypoint import (
    _env_bool,
    _env_float,
    _env_int,
    _env_text,
    _non_negative_int,
    _positive_float,
    _positive_int,
    _text,
    install_worker_signal_handlers,
)


@dataclass(frozen=True, slots=True)
class ForwardWorkerCallbacks:
    """Host callbacks; execution is always wrapped in persisted lease authorization."""

    materializer: ForwardEventMaterializer
    handler: ForwardEventHandler
    authorization_resolver: ForwardWorkerAuthorizationResolver
    close: Callable[[], Awaitable[None] | None] | None = None

    def __post_init__(self) -> None:
        if not callable(self.materializer):
            raise TypeError("materializer must be callable")
        if not callable(self.handler):
            raise TypeError("handler must be callable")
        if not callable(self.authorization_resolver):
            raise TypeError("authorization_resolver must be callable")
        if self.close is not None and not callable(self.close):
            raise TypeError("close must be callable or None")


@dataclass(frozen=True, slots=True)
class ForwardWorkerEntrypointConfig:
    """Validated non-secret configuration for one local forward worker."""

    redis_url: str
    database_url_sync: str
    callback_factory: str | None = None
    redis_namespace: str = "strategy-lab:v2"
    queue_name: str = "forward-events"
    group_name: str = "strategy-lab-v2-forward"
    consumer_name: str = "local-forward-worker"
    migration_enabled: bool = True
    migration_target: str = "head"
    reclaim_idle_ms: int = 30_000
    batch_size: int = 1
    block_ms: int = 0
    interval_seconds: float = 1.0

    def __post_init__(self) -> None:
        _text(self.redis_url, "redis_url")
        if not self.redis_url.startswith(("redis://", "rediss://")):
            raise ValueError("redis_url must use redis:// or rediss://")
        _text(self.database_url_sync, "database_url_sync")
        if not self.database_url_sync.startswith(("postgresql://", "postgresql+")):
            raise ValueError("database_url_sync must use a PostgreSQL URL")
        if self.callback_factory is not None:
            _text(self.callback_factory, "callback_factory")
        for name in ("redis_namespace", "queue_name", "group_name", "consumer_name"):
            _text(getattr(self, name), name)
        _text(self.migration_target, "migration_target")
        if any(
            not (character.isalnum() or character in "_.-") for character in self.migration_target
        ):
            raise ValueError("migration_target contains unsafe characters")
        _non_negative_int(self.reclaim_idle_ms, "reclaim_idle_ms")
        _positive_int(self.batch_size, "batch_size")
        _non_negative_int(self.block_ms, "block_ms")
        _positive_float(self.interval_seconds, "interval_seconds")

    @classmethod
    def from_env(
        cls, environment: Mapping[str, str] | None = None
    ) -> ForwardWorkerEntrypointConfig:
        """Read the namespaced forward-worker environment contract."""

        env = os.environ if environment is None else environment
        consumer = env.get("STRATEGY_LAB_V2_FORWARD_CONSUMER_NAME")
        if consumer is None:
            consumer = f"{env.get('HOSTNAME', socket.gethostname())}-{os.getpid()}"
        return cls(
            redis_url=_env_text(
                env,
                "STRATEGY_LAB_V2_FORWARD_REDIS_URL",
                env.get("REDIS_URL", "redis://localhost:6379/0"),
            ),
            database_url_sync=_env_text(
                env,
                "STRATEGY_LAB_V2_FORWARD_DATABASE_URL_SYNC",
                env.get(
                    "DATABASE_URL_SYNC",
                    "postgresql+psycopg2://postgres:postgres@localhost:5432/chartingdb",
                ),
            ),
            callback_factory=env.get("STRATEGY_LAB_V2_FORWARD_CALLBACK_FACTORY"),
            redis_namespace=env.get("STRATEGY_LAB_V2_FORWARD_REDIS_NAMESPACE", "strategy-lab:v2"),
            queue_name=env.get("STRATEGY_LAB_V2_FORWARD_QUEUE", "forward-events"),
            group_name=env.get("STRATEGY_LAB_V2_FORWARD_GROUP", "strategy-lab-v2-forward"),
            consumer_name=consumer,
            migration_enabled=_env_bool(env, "STRATEGY_LAB_V2_FORWARD_MIGRATIONS_ENABLED", True),
            migration_target=env.get("STRATEGY_LAB_V2_FORWARD_MIGRATION_TARGET", "head"),
            reclaim_idle_ms=_env_int(env, "STRATEGY_LAB_V2_FORWARD_RECLAIM_IDLE_MS", 30_000),
            batch_size=_env_int(env, "STRATEGY_LAB_V2_FORWARD_BATCH_SIZE", 1),
            block_ms=_env_int(env, "STRATEGY_LAB_V2_FORWARD_BLOCK_MS", 0),
            interval_seconds=_env_float(env, "STRATEGY_LAB_V2_FORWARD_INTERVAL_SECONDS", 1.0),
        )


class ForwardWorkerEntrypointDecision(StrEnum):
    STOPPED = "stopped"
    MIGRATION_FAILED = "migration_failed"


@dataclass(frozen=True, slots=True)
class ForwardWorkerEntrypointResolution:
    """Lifecycle evidence from one forward-worker invocation."""

    decision: ForwardWorkerEntrypointDecision
    migration: MigrationResolution | None
    cycles: tuple[WorkerCycleResolution, ...] = ()
    runtime_closed: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ForwardWorkerEntrypointDecision):
            raise TypeError("decision must be a ForwardWorkerEntrypointDecision")
        if self.migration is not None and not isinstance(self.migration, MigrationResolution):
            raise TypeError("migration must be a MigrationResolution or None")
        if not isinstance(self.cycles, tuple) or any(
            not isinstance(cycle, WorkerCycleResolution) for cycle in self.cycles
        ):
            raise TypeError("cycles must contain WorkerCycleResolution values")
        if not isinstance(self.runtime_closed, bool):
            raise TypeError("runtime_closed must be a bool")
        if self.decision is ForwardWorkerEntrypointDecision.MIGRATION_FAILED:
            if self.migration is None or self.migration.decision is not MigrationDecision.FAILED:
                raise ValueError("migration failures require failed migration evidence")
            if self.cycles:
                raise ValueError("migration failures cannot contain worker cycles")


class ForwardWorkerEntrypointStartupError(RuntimeError):
    """Fail-closed startup error containing only stable migration evidence."""

    def __init__(self, resolution: ForwardWorkerEntrypointResolution) -> None:
        if resolution.decision is not ForwardWorkerEntrypointDecision.MIGRATION_FAILED:
            raise ValueError("startup errors require a failed migration resolution")
        self.resolution = resolution
        assert resolution.migration is not None
        self.error_digest = resolution.migration.error_digest
        super().__init__("Strategy Lab v2 forward worker startup migration failed")


ForwardWorkerCallbackFactory = Callable[
    [PostgresStrategyLabV2Persistence],
    ForwardWorkerCallbacks
    | tuple[ForwardEventMaterializer, ForwardEventHandler, ForwardWorkerAuthorizationResolver]
    | Awaitable[
        ForwardWorkerCallbacks
        | tuple[ForwardEventMaterializer, ForwardEventHandler, ForwardWorkerAuthorizationResolver]
    ],
]
PersistenceFactory = Callable[[Callable[[], Any]], PostgresStrategyLabV2Persistence]
RuntimeFactory = Callable[..., Awaitable[Any]]
SignalInstaller = Callable[[asyncio.Event], Callable[[], None]]


async def run_forward_strategy_lab_v2_worker(
    config: ForwardWorkerEntrypointConfig,
    *,
    callback_factory: ForwardWorkerCallbackFactory | None = None,
    migration_service: StrategyLabV2MigrationService | None = None,
    session_factory: Callable[[], Any] | None = None,
    persistence_factory: PersistenceFactory = PostgresStrategyLabV2Persistence.build,
    runtime_factory: RuntimeFactory = RedisDispatchRuntime.connect,
    signal_installer: SignalInstaller | None = None,
    stop_event: asyncio.Event | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    max_cycles: int | None = None,
) -> ForwardWorkerEntrypointResolution:
    """Run one explicit forward worker until signal cancellation or a test cap."""

    if not isinstance(config, ForwardWorkerEntrypointConfig):
        raise TypeError("config must be a ForwardWorkerEntrypointConfig")
    if callback_factory is not None and not callable(callback_factory):
        raise TypeError("callback_factory must be callable")
    if not callable(persistence_factory) or not callable(runtime_factory):
        raise TypeError("persistence_factory and runtime_factory must be callable")
    if max_cycles is not None:
        _positive_int(max_cycles, "max_cycles")
    if stop_event is not None and not callable(getattr(stop_event, "is_set", None)):
        raise TypeError("stop_event must expose is_set()")
    if not callable(sleep):
        raise TypeError("sleep must be callable")

    migration_resolution: MigrationResolution | None = None
    if config.migration_enabled:
        migration_runner = migration_service or create_strategy_lab_v2_migration_service(
            config.database_url_sync,
            script_location=_migration_script_location(),
            target_revision=config.migration_target,
        )
        if not callable(getattr(migration_runner, "upgrade", None)):
            raise TypeError("migration_service must expose an async upgrade method")
        migration_resolution = await migration_runner.upgrade()
        if not isinstance(migration_resolution, MigrationResolution):
            raise TypeError("migration_service.upgrade() must return a MigrationResolution")
        if migration_resolution.decision is MigrationDecision.FAILED:
            return ForwardWorkerEntrypointResolution(
                ForwardWorkerEntrypointDecision.MIGRATION_FAILED,
                migration_resolution,
            )

    if session_factory is None:
        database_module = import_module("app.database")
        session_factory = getattr(database_module, "AsyncSessionLocal", None)
        if not callable(session_factory):
            raise TypeError("app.database.AsyncSessionLocal must be callable")
    persistence = persistence_factory(session_factory)
    factory = callback_factory or _load_callback_factory(config.callback_factory)
    callbacks = factory(persistence)
    if inspect.isawaitable(callbacks):
        callbacks = await callbacks
    callback_set = _coerce_callbacks(callbacks)

    try:
        runtime = await runtime_factory(config.redis_url, namespace=config.redis_namespace)
    except BaseException:
        if callback_set.close is not None:
            close_result = callback_set.close()
            if inspect.isawaitable(close_result):
                await close_result
        raise
    try:
        worker = runtime.worker(
            queue_name=config.queue_name,
            group_name=config.group_name,
            consumer_name=config.consumer_name,
            reclaim_idle_ms=config.reclaim_idle_ms,
            batch_size=config.batch_size,
            block_ms=config.block_ms,
        )
        service = runtime.forward_worker_service(
            worker,
            payload_loader=persistence.forward_dispatch,
            materializer=callback_set.materializer,
            handler=AuthorizedForwardEventHandler(
                callback_set.authorization_resolver,
                callback_set.handler,
                clock=lambda: datetime.now(UTC),
            ),
            interval_seconds=config.interval_seconds,
            sleep=sleep,
        )
        if not callable(getattr(service, "run", None)):
            raise TypeError("runtime.forward_worker_service() must return a worker service")
        event = stop_event or asyncio.Event()
        cleanup = (signal_installer or install_worker_signal_handlers)(event)
        if not callable(cleanup):
            raise TypeError("signal installer must return a cleanup callable")
        relay_task: asyncio.Task[None] | None = None
        try:
            outbox_scheduler_factory = getattr(runtime, "outbox_scheduler", None)
            outbox_persistence = getattr(persistence, "execution_events", None)
            if callable(outbox_scheduler_factory) and outbox_persistence is not None:
                scheduler = outbox_scheduler_factory(
                    outbox_persistence,
                    interval_seconds=config.interval_seconds,
                    limit=min(config.batch_size, 100),
                    sleep=sleep,
                )
                if not callable(getattr(scheduler, "run", None)):
                    raise TypeError("runtime.outbox_scheduler() must return a scheduler")
                relay_task = asyncio.create_task(scheduler.run(event))
            cycles = await service.run(event, max_cycles=max_cycles)
        finally:
            if relay_task is not None:
                relay_task.cancel()
                with suppress(asyncio.CancelledError):
                    await relay_task
            cleanup()
    finally:
        try:
            await runtime.aclose()
        finally:
            if callback_set.close is not None:
                close_result = callback_set.close()
                if inspect.isawaitable(close_result):
                    await close_result
    return ForwardWorkerEntrypointResolution(
        ForwardWorkerEntrypointDecision.STOPPED,
        migration_resolution,
        tuple(cycles),
        True,
    )


def _coerce_callbacks(value: Any) -> ForwardWorkerCallbacks:
    if isinstance(value, ForwardWorkerCallbacks):
        return value
    if isinstance(value, tuple) and len(value) == 3:
        return ForwardWorkerCallbacks(
            cast(ForwardEventMaterializer, value[0]),
            cast(ForwardEventHandler, value[1]),
            cast(ForwardWorkerAuthorizationResolver, value[2]),
        )
    raise TypeError(
        "callback_factory must return ForwardWorkerCallbacks or a three-item "
        "materializer/handler/authorization tuple"
    )


def _load_callback_factory(spec: str | None) -> ForwardWorkerCallbackFactory:
    if spec is None:
        raise ValueError(
            "STRATEGY_LAB_V2_FORWARD_CALLBACK_FACTORY must be configured for the local forward worker"
        )
    module_name, separator, attribute = spec.partition(":")
    if not separator or not module_name.strip() or not attribute.strip():
        raise ValueError("callback_factory must use module:attribute syntax")
    module: ModuleType = import_module(module_name.strip())
    factory = getattr(module, attribute.strip(), None)
    if not callable(factory):
        raise TypeError("callback_factory target must be callable")
    return cast(ForwardWorkerCallbackFactory, factory)


def _migration_script_location():
    from pathlib import Path

    return Path(__file__).resolve().parents[2] / "alembic"


async def _main_async() -> None:
    config = ForwardWorkerEntrypointConfig.from_env()
    resolution = await run_forward_strategy_lab_v2_worker(config)
    if resolution.decision is ForwardWorkerEntrypointDecision.MIGRATION_FAILED:
        raise ForwardWorkerEntrypointStartupError(resolution)


def main() -> None:
    """Run the explicit local forward worker from environment configuration."""

    asyncio.run(_main_async())


__all__ = [
    "ForwardWorkerCallbacks",
    "ForwardWorkerEntrypointConfig",
    "ForwardWorkerEntrypointDecision",
    "ForwardWorkerEntrypointResolution",
    "ForwardWorkerEntrypointStartupError",
    "main",
    "run_forward_strategy_lab_v2_worker",
]


if __name__ == "__main__":  # pragma: no cover
    main()
