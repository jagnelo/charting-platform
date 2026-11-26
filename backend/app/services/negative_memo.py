"""Shared "provider definitively cannot serve this" memo.

Provider answers such as "no usable data for this slice", "this token is not
listed" (HTTP 404) or "the free plan does not cover this symbol" (HTTP 402/403)
are stable for days. Remembering them only in process memory means every worker
restart re-asks the provider and burns free-tier quota. This module keeps the
memo in Redis (the instance the app already uses for arq) with a TTL, while
callers keep their own in-process layer as a fast cache.

Redis is strictly best-effort: connection or command failures are swallowed
(and Redis is skipped for a short cool-down) so a Redis outage can only cost
extra provider requests, never a failed read or refresh.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from hashlib import sha256
from typing import Any

from redis.asyncio import Redis

from app.config import settings

logger = logging.getLogger(__name__)

_KEY_PREFIX = "charting:negmemo"
_COOLDOWN_SECONDS = 30.0
_SOCKET_TIMEOUT_SECONDS = 0.5

_client: Any = None
_client_url: str | None = None
_down_until: float = 0.0


def _get_client() -> Any:
    """Return the lazy process-local Redis client, or ``None`` when unconfigured."""

    global _client, _client_url
    url = str(getattr(settings, "REDIS_URL", "") or "").strip()
    if not url:
        return None
    if _client is None or _client_url != url:
        _client = Redis.from_url(
            url,
            decode_responses=False,
            socket_connect_timeout=_SOCKET_TIMEOUT_SECONDS,
            socket_timeout=_SOCKET_TIMEOUT_SECONDS,
        )
        _client_url = url
    return _client


def reset_shared_client() -> None:
    """Forget the cached client and failure cool-down (tests, reconfiguration)."""

    global _client, _client_url, _down_until
    _client = None
    _client_url = None
    _down_until = 0.0


def memo_redis_key(namespace: str, identity: object) -> str:
    digest = sha256(repr(identity).encode("utf-8")).hexdigest()[:40]
    return f"{_KEY_PREFIX}:{namespace}:{digest}"


def _mark_down(exc: Exception) -> None:
    global _down_until
    _down_until = time.monotonic() + _COOLDOWN_SECONDS
    logger.warning("negative memo Redis unavailable; using in-process memo only: %s", exc)


def _usable_client() -> Any:
    if time.monotonic() < _down_until:
        return None
    try:
        return _get_client()
    except Exception as exc:  # noqa: BLE001 - memo must never fail a caller.
        _mark_down(exc)
        return None


async def shared_memo_known(namespace: str, identities: Iterable[object]) -> set[object]:
    """Return the subset of ``identities`` currently remembered in Redis."""

    items = list(identities)
    if not items:
        return set()
    client = _usable_client()
    if client is None:
        return set()
    try:
        values = await client.mget([memo_redis_key(namespace, item) for item in items])
    except Exception as exc:  # noqa: BLE001
        _mark_down(exc)
        return set()
    return {item for item, value in zip(items, values, strict=True) if value is not None}


async def shared_memo_remember(
    namespace: str, identities: Iterable[object], *, ttl_seconds: int
) -> None:
    """Remember every identity in Redis for ``ttl_seconds`` (best effort)."""

    items = list(identities)
    ttl = int(ttl_seconds)
    if not items or ttl <= 0:
        return
    client = _usable_client()
    if client is None:
        return
    try:
        pipe = client.pipeline(transaction=False)
        for item in items:
            pipe.set(memo_redis_key(namespace, item), b"1", ex=ttl)
        await pipe.execute()
    except Exception as exc:  # noqa: BLE001
        _mark_down(exc)
