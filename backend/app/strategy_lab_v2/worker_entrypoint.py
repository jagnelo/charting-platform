"""Explicit local Strategy Lab v2 worker entrypoint.

The package owns the lifecycle boundary for a dedicated local worker, while
the concrete handoff and completion adapters remain application-owned
callables.  Importing this module never opens a database or Redis connection,
runs migrations, installs signal handlers, or starts a worker.  The executable
entrypoint is :func:`main` (``python -m app.strategy_lab_v2.worker_entrypoint``)
and all lifecycle work is kept behind the testable async runner.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import signal
import socket
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.migration_startup import (
    MigrationDecision,
    MigrationResolution,
    StrategyLabV2MigrationService,
    create_strategy_lab_v2_migration_service,
)
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.redis_application import RedisDispatchRuntime
from app.strategy_lab_v2.worker_consumer import (
    WorkerCycleResolution,
)
from app.strategy_lab_v2.worker_process import SerialWorkerProcessExecutor
from app.strategy_lab_v2.worker_service import (
    WorkerCompletionWriter,
    WorkerHandoffMaterializer,
    WorkerLeaseHeartbeatWriter,
    WorkerServiceCallbacks,
    WorkerTerminalWriter,
)


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if any(character in value for character in "\x00\r\n"):
        raise ValueError(f"{field_name} must not contain control characters")
    return value.strip()


def _positive_float(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field_name} must be a positive number")
    number = float(value)
    if number <= 0 or not number < float("inf"):
        raise ValueError(f"{field_name} must be a finite positive number")
    return number


def _non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _env_text(environment: Mapping[str, str], name: str, default: str | None = None) -> str:
    value = environment.get(name, default)
    if value is None:
        raise ValueError(f"{name} must be configured")
    return _text(value, name)


def _env_bool(environment: Mapping[str, str], name: str, default: bool) -> bool:
    raw = environment.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _env_int(environment: Mapping[str, str], name: str, default: int) -> int:
    raw = environment.get(name)
    if raw is None:
        return default
    try:
        return int(raw, 10)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be an integer") from error


def _env_float(environment: Mapping[str, str], name: str, default: float) -> float:
    raw = environment.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number") from error


@dataclass(frozen=True, slots=True)
class WorkerEntrypointConfig:
    """Validated, non-secret configuration for one local worker process."""

    redis_url: str
    database_url_sync: str
    artifact_root: Path
    callback_factory: str | None = None
    redis_namespace: str = "strategy-lab:v2"
    queue_name: str = "backtest"
    group_name: str = "strategy-lab-v2"
    consumer_name: str = "local-worker"
    migration_enabled: bool = True
    migration_target: str = "head"
    reclaim_idle_ms: int = 30_000
    batch_size: int = 1
    block_ms: int = 0
    interval_seconds: float = 1.0
    process_timeout_seconds: float = 300.0
    heartbeat_interval_seconds: float = 5.0
    heartbeat_extension_seconds: float = 30.0
    docker_binary: str = "docker"

    def __post_init__(self) -> None:
        _text(self.redis_url, "redis_url")
        if not self.redis_url.startswith(("redis://", "rediss://")):
            raise ValueError("redis_url must use redis:// or rediss://")
        _text(self.database_url_sync, "database_url_sync")
        if not self.database_url_sync.startswith(("postgresql://", "postgresql+")):
            raise ValueError("database_url_sync must use a PostgreSQL URL")
        if not isinstance(self.artifact_root, Path) or not self.artifact_root.is_absolute():
            raise ValueError("artifact_root must be an absolute path")
        if self.callback_factory is not None:
            _text(self.callback_factory, "callback_factory")
        for name in ("redis_namespace", "queue_name", "group_name", "consumer_name", "docker_binary"):
            _text(getattr(self, name), name)
        _text(self.migration_target, "migration_target")
        if any(not (character.isalnum() or character in "_.-") for character in self.migration_target):
            raise ValueError("migration_target contains unsafe characters")
        _non_negative_int(self.reclaim_idle_ms, "reclaim_idle_ms")
        _positive_int(self.batch_size, "batch_size")
        _non_negative_int(self.block_ms, "block_ms")
        _positive_float(self.interval_seconds, "interval_seconds")
        _positive_float(self.process_timeout_seconds, "process_timeout_seconds")
        _positive_float(self.heartbeat_interval_seconds, "heartbeat_interval_seconds")
        _positive_float(self.heartbeat_extension_seconds, "heartbeat_extension_seconds")

    @classmethod
    def from_env(cls, environment: Mapping[str, str] | None = None) -> WorkerEntrypointConfig:
        """Read the explicit local-worker environment contract.

        The existing ``REDIS_URL`` and ``DATABASE_URL_SYNC`` names are accepted
        as fallbacks for local Compose compatibility; all Strategy Lab-specific
        knobs use a namespaced variable.  Secret-bearing values are retained in
        memory only and are never included in fingerprints or error messages.
        """

        env = os.environ if environment is None else environment
        artifact_root = Path(
            _env_text(env, "STRATEGY_LAB_V2_ARTIFACT_ROOT", "/tmp/charting-strategy-lab-v2/artifacts")
        )
        consumer = env.get("STRATEGY_LAB_V2_CONSUMER_NAME")
        if consumer is None:
            consumer = f"{env.get('HOSTNAME', socket.gethostname())}-{os.getpid()}"
        return cls(
            redis_url=_env_text(env, "STRATEGY_LAB_V2_REDIS_URL", env.get("REDIS_URL", "redis://localhost:6379/0")),
            database_url_sync=_env_text(
                env,
                "STRATEGY_LAB_V2_DATABASE_URL_SYNC",
                env.get(
                    "DATABASE_URL_SYNC",
                    "postgresql+psycopg2://postgres:postgres@localhost:5432/chartingdb",
                ),
            ),
            artifact_root=artifact_root,
            callback_factory=env.get("STRATEGY_LAB_V2_CALLBACK_FACTORY"),
            redis_namespace=env.get("STRATEGY_LAB_V2_REDIS_NAMESPACE", "strategy-lab:v2"),
            queue_name=env.get("STRATEGY_LAB_V2_QUEUE", "backtest"),
            group_name=env.get("STRATEGY_LAB_V2_GROUP", "strategy-lab-v2"),
            consumer_name=consumer,
            migration_enabled=_env_bool(env, "STRATEGY_LAB_V2_MIGRATIONS_ENABLED", True),
            migration_target=env.get("STRATEGY_LAB_V2_MIGRATION_TARGET", "head"),
            reclaim_idle_ms=_env_int(env, "STRATEGY_LAB_V2_RECLAIM_IDLE_MS", 30_000),
            batch_size=_env_int(env, "STRATEGY_LAB_V2_BATCH_SIZE", 1),
            block_ms=_env_int(env, "STRATEGY_LAB_V2_BLOCK_MS", 0),
            interval_seconds=_env_float(env, "STRATEGY_LAB_V2_INTERVAL_SECONDS", 1.0),
            process_timeout_seconds=_env_float(
                env, "STRATEGY_LAB_V2_PROCESS_TIMEOUT_SECONDS", 300.0
            ),
            heartbeat_interval_seconds=_env_float(
                env, "STRATEGY_LAB_V2_HEARTBEAT_INTERVAL_SECONDS", 5.0
            ),
            heartbeat_extension_seconds=_env_float(
                env, "STRATEGY_LAB_V2_HEARTBEAT_EXTENSION_SECONDS", 30.0
            ),
            docker_binary=env.get("STRATEGY_LAB_V2_DOCKER_BINARY", "docker"),
        )


class WorkerEntrypointDecision(StrEnum):
    STOPPED = "stopped"
    MIGRATION_FAILED = "migration_failed"


@dataclass(frozen=True, slots=True)
class WorkerEntrypointResolution:
    """Lifecycle evidence from one worker invocation."""

    decision: WorkerEntrypointDecision
    migration: MigrationResolution | None
    cycles: tuple[WorkerCycleResolution, ...] = ()
    runtime_closed: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.decision, WorkerEntrypointDecision):
            raise TypeError("decision must be a WorkerEntrypointDecision")
        if self.migration is not None and not isinstance(self.migration, MigrationResolution):
            raise TypeError("migration must be a MigrationResolution or None")
        if not isinstance(self.cycles, tuple) or any(
            not isinstance(cycle, WorkerCycleResolution) for cycle in self.cycles
        ):
            raise TypeError("cycles must contain WorkerCycleResolution values")
        if not isinstance(self.runtime_closed, bool):
            raise TypeError("runtime_closed must be a bool")
        if self.decision is WorkerEntrypointDecision.MIGRATION_FAILED:
            if self.migration is None or self.migration.decision is not MigrationDecision.FAILED:
                raise ValueError("migration failures require failed migration evidence")
            if self.cycles:
                raise ValueError("migration failures cannot contain worker cycles")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class WorkerEntrypointStartupError(RuntimeError):
    """Fail-closed startup error containing only stable typed evidence."""

    def __init__(self, resolution: WorkerEntrypointResolution) -> None:
        if resolution.decision is not WorkerEntrypointDecision.MIGRATION_FAILED:
            raise ValueError("startup errors require a failed migration resolution")
        self.resolution = resolution
        assert resolution.migration is not None
        self.error_digest = resolution.migration.error_digest
        super().__init__("Strategy Lab v2 worker startup migration failed")


WorkerCallbackFactory = Callable[
    [PostgresStrategyLabV2Persistence, Path],
    WorkerServiceCallbacks
    | tuple[WorkerHandoffMaterializer, WorkerCompletionWriter]
    | tuple[WorkerHandoffMaterializer, WorkerCompletionWriter, WorkerLeaseHeartbeatWriter]
    | tuple[
        WorkerHandoffMaterializer,
        WorkerCompletionWriter,
        WorkerLeaseHeartbeatWriter,
        WorkerTerminalWriter,
    ],
]
RuntimeFactory = Callable[..., Awaitable[Any]]
PersistenceFactory = Callable[[Callable[[], Any]], PostgresStrategyLabV2Persistence]
SignalInstaller = Callable[[asyncio.Event], Callable[[], None]]


async def run_strategy_lab_v2_worker(
    config: WorkerEntrypointConfig,
    *,
    callback_factory: WorkerCallbackFactory | None = None,
    migration_service: StrategyLabV2MigrationService | None = None,
    session_factory: Callable[[], Any] | None = None,
    persistence_factory: PersistenceFactory = PostgresStrategyLabV2Persistence.build,
    runtime_factory: RuntimeFactory = RedisDispatchRuntime.connect,
    signal_installer: SignalInstaller | None = None,
    stop_event: asyncio.Event | None = None,
    process_executor: SerialWorkerProcessExecutor | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    max_cycles: int | None = None,
) -> WorkerEntrypointResolution:
    """Run one dedicated worker lifecycle until signal cancellation.

    Startup migrations complete before Redis is opened.  The persistence bundle
    and callback factory are created once, while the runtime is always closed in
    ``finally``.  Callback factories may be synchronous or return an awaitable,
    but must return a ``WorkerServiceCallbacks`` value or a two/three/four-item
    ``(materializer, completion_writer[, heartbeat_writer[, terminal_writer]])``
    tuple.
    """

    if not isinstance(config, WorkerEntrypointConfig):
        raise TypeError("config must be a WorkerEntrypointConfig")
    if callback_factory is not None and not callable(callback_factory):
        raise TypeError("callback_factory must be callable")
    if not callable(persistence_factory):
        raise TypeError("persistence_factory must be callable")
    if not callable(runtime_factory):
        raise TypeError("runtime_factory must be callable")
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
            return WorkerEntrypointResolution(
                WorkerEntrypointDecision.MIGRATION_FAILED,
                migration_resolution,
            )

    if session_factory is None:
        database_module = import_module("app.database")
        session_factory = getattr(database_module, "AsyncSessionLocal", None)
        if not callable(session_factory):
            raise TypeError("app.database.AsyncSessionLocal must be callable")
    persistence = persistence_factory(session_factory)
    factory = callback_factory or _load_callback_factory(config.callback_factory)
    callbacks = factory(persistence, config.artifact_root)
    if inspect.isawaitable(callbacks):
        callbacks = await callbacks
    if isinstance(callbacks, WorkerServiceCallbacks):
        callback_set = callbacks
    elif isinstance(callbacks, tuple) and len(callbacks) in {2, 3, 4}:
        if not callable(callbacks[0]) or not callable(callbacks[1]):
            raise TypeError("callback_factory tuple must contain callables")
        if len(callbacks) == 3 and not callable(callbacks[2]):
            raise TypeError("callback_factory heartbeat writer must be callable")
        if len(callbacks) == 4 and (
            not callable(callbacks[2]) or not callable(callbacks[3])
        ):
            raise TypeError("callback_factory heartbeat and terminal writers must be callable")
        callback_set = WorkerServiceCallbacks(
            cast(WorkerHandoffMaterializer, callbacks[0]),
            cast(WorkerCompletionWriter, callbacks[1]),
            cast(WorkerLeaseHeartbeatWriter, callbacks[2]) if len(callbacks) == 3 else None,
            cast(WorkerTerminalWriter, callbacks[3]) if len(callbacks) == 4 else None,
        )
    else:
        raise TypeError(
            "callback_factory must return WorkerServiceCallbacks or a two/three/four-item tuple"
        )

    runtime = await runtime_factory(config.redis_url, namespace=config.redis_namespace)
    closed = False
    try:
        worker = runtime.worker(
            queue_name=config.queue_name,
            group_name=config.group_name,
            consumer_name=config.consumer_name,
            reclaim_idle_ms=config.reclaim_idle_ms,
            batch_size=config.batch_size,
            block_ms=config.block_ms,
        )
        service = runtime.worker_service(
            worker,
            payload_loader=persistence.submissions,
            materializer=callback_set.materializer,
            completion_writer=callback_set.completion_writer,
            interval_seconds=config.interval_seconds,
            sleep=sleep,
            process_executor=process_executor
            or SerialWorkerProcessExecutor(
                timeout_seconds=config.process_timeout_seconds,
            ),
            heartbeat_writer=callback_set.heartbeat_writer,
            heartbeat_interval_seconds=config.heartbeat_interval_seconds,
            heartbeat_extension_seconds=config.heartbeat_extension_seconds,
            terminal_writer=callback_set.terminal_writer,
        )
        if not callable(getattr(service, "run", None)):
            raise TypeError("runtime.worker_service() must return a worker service")
        event = stop_event or asyncio.Event()
        cleanup = (signal_installer or install_worker_signal_handlers)(event)
        if not callable(cleanup):
            raise TypeError("signal installer must return a cleanup callable")
        try:
            cycles = await service.run(event, max_cycles=max_cycles)
        finally:
            cleanup()
    finally:
        await runtime.aclose()
        closed = True
    return WorkerEntrypointResolution(
        WorkerEntrypointDecision.STOPPED,
        migration_resolution,
        tuple(cycles),
        closed,
    )


def _migration_script_location() -> Path:
    return Path(__file__).resolve().parents[2] / "alembic"


def _load_callback_factory(spec: str | None) -> WorkerCallbackFactory:
    if spec is None:
        raise ValueError(
            "STRATEGY_LAB_V2_CALLBACK_FACTORY must be configured for the local worker"
        )
    module_name, separator, attribute = spec.partition(":")
    if not separator or not module_name.strip() or not attribute.strip():
        raise ValueError("callback_factory must use module:attribute syntax")
    module: ModuleType = import_module(module_name.strip())
    factory = getattr(module, attribute.strip(), None)
    if not callable(factory):
        raise TypeError("callback_factory target must be callable")
    return cast(WorkerCallbackFactory, factory)


def install_worker_signal_handlers(stop_event: asyncio.Event) -> Callable[[], None]:
    """Install SIGINT/SIGTERM cancellation and return an idempotent cleanup."""

    if not callable(getattr(stop_event, "set", None)):
        raise TypeError("stop_event must expose set()")
    loop = asyncio.get_running_loop()
    installed: list[signal.Signals] = []
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stop_event.set)
        except (NotImplementedError, RuntimeError, ValueError):
            continue
        installed.append(signum)
    cleaned = False

    def cleanup() -> None:
        nonlocal cleaned
        if cleaned:
            return
        cleaned = True
        for signum in installed:
            try:
                loop.remove_signal_handler(signum)
            except (NotImplementedError, RuntimeError, ValueError):
                continue

    return cleanup


async def _main_async() -> None:
    config = WorkerEntrypointConfig.from_env()
    resolution = await run_strategy_lab_v2_worker(config)
    if resolution.decision is WorkerEntrypointDecision.MIGRATION_FAILED:
        raise WorkerEntrypointStartupError(resolution)


def main() -> None:
    """Run the explicit local worker from environment configuration."""

    asyncio.run(_main_async())


__all__ = [
    "WorkerCallbackFactory",
    "WorkerEntrypointConfig",
    "WorkerEntrypointDecision",
    "WorkerEntrypointResolution",
    "WorkerEntrypointStartupError",
    "install_worker_signal_handlers",
    "main",
    "run_strategy_lab_v2_worker",
]


if __name__ == "__main__":  # pragma: no cover - exercised by local process use
    main()
