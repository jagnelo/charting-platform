"""Ownership-safe Redis locks for cross-process refresh coalescing.

PostgreSQL advisory locks coordinate workers that share one database
transaction boundary. Deployments that split that boundary can opt into this
shared Redis coordinator instead. Lock acquisition is fail-closed when the
coordinator is enabled, so a missing or contended lock never causes an unsafe
duplicate refresh.
"""

from __future__ import annotations

import logging
import math
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from hashlib import sha256
from typing import Any

from redis.asyncio import Redis

from app.config import settings

logger = logging.getLogger(__name__)


class DistributedLockError(RuntimeError):
    """The configured cross-process lock could not be acquired safely."""


_shared_client: Redis | None = None
_shared_client_url: str | None = None


def _lock_name(namespace: str, identity: str) -> str:
    """Return a bounded, non-sensitive Redis key for an operation identity."""

    digest = sha256(identity.encode("utf-8")).hexdigest()
    return f"charting:{namespace}:{digest}"


def shared_redis_lock_client() -> Redis:
    """Return the lazy process-local client when locking is explicitly enabled."""

    global _shared_client, _shared_client_url
    if not settings.OHLCV_DISTRIBUTED_LOCK_ENABLED:
        raise DistributedLockError("OHLCV distributed locking is disabled")
    redis_url = str(settings.REDIS_URL or "").strip()
    if not redis_url:
        raise DistributedLockError("OHLCV distributed locking requires REDIS_URL")
    if _shared_client is None or _shared_client_url != redis_url:
        _shared_client = Redis.from_url(redis_url, decode_responses=False)
        _shared_client_url = redis_url
    return _shared_client


async def close_shared_redis_lock_client() -> None:
    """Close the lazy client during application shutdown, if one was created."""

    global _shared_client, _shared_client_url
    client = _shared_client
    _shared_client = None
    _shared_client_url = None
    if client is not None:
        await client.aclose()


@asynccontextmanager
async def redis_distributed_lock(
    redis: Any,
    *,
    namespace: str,
    identity: str,
    ttl_seconds: int,
    blocking_timeout_seconds: float,
    retry_interval_seconds: float,
) -> AsyncIterator[None]:
    """Acquire and release an ownership-safe Redis lock around one operation.

    ``redis.asyncio.Lock`` stores an owner token and releases it atomically, so
    a worker that lost its TTL cannot delete a successor's lock. The TTL is an
    explicit deployment bound and must exceed the slowest permitted refresh.
    """

    if redis is None:
        raise DistributedLockError("OHLCV distributed locking requires a Redis client")
    if ttl_seconds <= 0:
        raise DistributedLockError("OHLCV distributed lock TTL must be positive")
    if not math.isfinite(blocking_timeout_seconds) or blocking_timeout_seconds < 0:
        raise DistributedLockError("OHLCV distributed lock wait timeout must be finite and non-negative")
    if not math.isfinite(retry_interval_seconds) or retry_interval_seconds <= 0:
        raise DistributedLockError("OHLCV distributed lock retry interval must be finite and positive")

    lock = redis.lock(
        _lock_name(namespace, identity),
        timeout=ttl_seconds,
        sleep=retry_interval_seconds,
        blocking_timeout=blocking_timeout_seconds,
    )
    try:
        acquired = await lock.acquire()
    except Exception as exc:  # pragma: no cover - concrete Redis transport
        raise DistributedLockError("Redis distributed lock acquisition failed") from exc
    if not acquired:
        raise DistributedLockError("Redis distributed lock acquisition timed out")
    try:
        yield
    finally:
        try:
            await lock.release()
        except Exception:
            # An overlong/crashed owner may have lost its TTL. Never mask the
            # operation's result, but retain a diagnostic for operators.
            logger.warning("Redis distributed lock release failed", exc_info=True)
