"""Process-wide arq Redis pool for best-effort enqueue hints.

Request handlers must not open a Redis pool per call: every connect can wait
through retries while the request still holds a database transaction. One lazy
pool is shared for the process, with a short connect bound and no retries. The
durable database queue stays authoritative; a missing hint is only a delay.
"""

from __future__ import annotations

import asyncio
import logging

from arq.connections import RedisSettings, create_pool

from app.config import settings

logger = logging.getLogger(__name__)

SHARED_POOL_CONNECT_TIMEOUT_SECONDS = 1.0
_pool = None
_pool_lock = asyncio.Lock()


async def get_shared_arq_pool():
    """Create the shared pool on first use and reuse it afterwards."""

    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
                redis_settings.conn_timeout = SHARED_POOL_CONNECT_TIMEOUT_SECONDS
                redis_settings.conn_retries = 0
                redis_settings.conn_retry_delay = 0
                _pool = await create_pool(redis_settings)
    return _pool


async def close_shared_arq_pool() -> None:
    """Close the shared pool at application shutdown, if one exists."""

    global _pool
    pool = _pool
    _pool = None
    if pool is None:
        return
    try:
        await pool.aclose()
    except Exception as exc:  # shutdown must not fail on an optional hint
        logger.warning("Could not close shared arq pool: %s", type(exc).__name__)
