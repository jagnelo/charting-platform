"""Application-owned Redis client lifecycle for Strategy Lab v2 transport."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from importlib import import_module
from typing import Any

from app.strategy_lab_v2.dispatch_payload import DispatchPayloadLoader
from app.strategy_lab_v2.outbox_application import OutboxPersistence, OutboxRelayService
from app.strategy_lab_v2.redis_transport import RedisDispatchTransport
from app.strategy_lab_v2.worker_consumer import (
    RedisDispatchWorker,
    RedisDispatchWorkerScheduler,
)
from app.strategy_lab_v2.worker_process import SerialWorkerProcessExecutor
from app.strategy_lab_v2.worker_service import (
    DedicatedStrategyWorkerService,
    WorkerCompletionWriter,
    WorkerHandoffMaterializer,
)


class RedisDispatchRuntime:
    """Own one concrete Redis client and its v2 transport adapters.

    The package transport remains client-agnostic. This application seam is
    responsible only for constructing the configured ``redis.asyncio`` client,
    exposing relay/worker factories, and closing that client exactly once.
    """

    def __init__(self, client: Any, transport: RedisDispatchTransport) -> None:
        if not callable(getattr(client, "aclose", None)):
            raise TypeError("client must provide an async aclose method")
        if not isinstance(transport, RedisDispatchTransport):
            raise TypeError("transport must be a RedisDispatchTransport")
        self._client = client
        self._transport = transport
        self._closed = False

    @classmethod
    async def connect(
        cls,
        url: str,
        *,
        namespace: str = "strategy-lab:v2",
        **client_options: Any,
    ) -> RedisDispatchRuntime:
        """Create a runtime from a ``redis://`` or ``rediss://`` URL.

        Connection establishment is left to the first Redis operation, which
        keeps construction non-blocking and lets callers control health checks.
        The URL is passed directly to the official client and never included in
        resolution evidence or logs by this module.
        """

        if not isinstance(url, str) or not url.strip():
            raise ValueError("Redis URL must not be empty")
        if not url.startswith(("redis://", "rediss://")):
            raise ValueError("Redis URL must use redis:// or rediss://")
        if "decode_responses" in client_options and client_options["decode_responses"] is not True:
            raise ValueError("Redis client decode_responses must be true")
        options = dict(client_options)
        options["decode_responses"] = True
        redis_module = import_module("redis.asyncio")
        client_factory = getattr(redis_module, "Redis", None)
        if client_factory is None or not callable(getattr(client_factory, "from_url", None)):
            raise TypeError("redis.asyncio.Redis.from_url is unavailable")
        client = client_factory.from_url(url, **options)
        if inspect.isawaitable(client):
            client = await client
        return cls(client, RedisDispatchTransport(client, namespace=namespace))

    @property
    def transport(self) -> RedisDispatchTransport:
        """Return the transport bound to this runtime's client."""

        return self._transport

    def outbox_relay(self, persistence: OutboxPersistence) -> OutboxRelayService:
        """Build an outbox relay over the shared Redis transport."""

        return OutboxRelayService(persistence, self._transport)

    def worker(
        self,
        *,
        queue_name: str,
        group_name: str,
        consumer_name: str,
        reclaim_idle_ms: int = 30_000,
        batch_size: int = 1,
        block_ms: int = 0,
    ) -> RedisDispatchWorker:
        """Build one bounded Redis worker pump over this runtime."""

        return RedisDispatchWorker(
            self._transport,
            queue_name=queue_name,
            group_name=group_name,
            consumer_name=consumer_name,
            reclaim_idle_ms=reclaim_idle_ms,
            batch_size=batch_size,
            block_ms=block_ms,
        )

    def worker_scheduler(
        self,
        worker: RedisDispatchWorker,
        *,
        interval_seconds: float = 1.0,
        sleep: Callable[[float], Awaitable[None]],
    ) -> RedisDispatchWorkerScheduler:
        """Build a cancellable scheduler for one bounded worker pump."""

        return RedisDispatchWorkerScheduler(
            worker,
            interval_seconds=interval_seconds,
            sleep=sleep,
        )

    def worker_service(
        self,
        worker: RedisDispatchWorker,
        *,
        payload_loader: DispatchPayloadLoader,
        materializer: WorkerHandoffMaterializer,
        completion_writer: WorkerCompletionWriter,
        interval_seconds: float = 1.0,
        sleep: Callable[[float], Awaitable[None]],
        process_executor: SerialWorkerProcessExecutor | None = None,
    ) -> DedicatedStrategyWorkerService:
        """Compose the dedicated Redis-to-process worker service."""

        scheduler = self.worker_scheduler(
            worker,
            interval_seconds=interval_seconds,
            sleep=sleep,
        )
        return DedicatedStrategyWorkerService(
            scheduler,
            payload_loader,
            materializer,
            completion_writer,
            process_executor=process_executor,
        )

    async def aclose(self) -> None:
        """Close the concrete Redis client idempotently."""

        if self._closed:
            return
        self._closed = True
        result = self._client.aclose()
        if isinstance(result, Awaitable) or inspect.isawaitable(result):
            await result


__all__ = ["RedisDispatchRuntime"]
