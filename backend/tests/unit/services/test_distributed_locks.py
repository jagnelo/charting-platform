import math

import pytest

from app.services.distributed_locks import DistributedLockError, redis_distributed_lock


class _Redis:
    def lock(self, *_args, **_kwargs):
        raise AssertionError("invalid lock settings must be rejected before contacting Redis")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("ttl", "wait", "retry"),
    [
        (0, 1.0, 0.1),
        (30, -1.0, 0.1),
        (30, math.nan, 0.1),
        (30, 1.0, 0),
        (30, 1.0, math.inf),
    ],
)
async def test_redis_lock_rejects_invalid_deployment_bounds(ttl, wait, retry):
    with pytest.raises(DistributedLockError):
        async with redis_distributed_lock(
            _Redis(),
            namespace="unit",
            identity="invalid",
            ttl_seconds=ttl,
            blocking_timeout_seconds=wait,
            retry_interval_seconds=retry,
        ):
            raise AssertionError("invalid settings must not enter the operation")


@pytest.mark.asyncio
async def test_redis_lock_wraps_transport_failure_without_leaking_exception():
    class _FailingLock:
        async def acquire(self):
            raise OSError("connection details must not escape")

    class _FailingRedis:
        def lock(self, *_args, **_kwargs):
            return _FailingLock()

    with pytest.raises(DistributedLockError, match="acquisition failed"):
        async with redis_distributed_lock(
            _FailingRedis(),
            namespace="unit",
            identity="transport",
            ttl_seconds=30,
            blocking_timeout_seconds=1.0,
            retry_interval_seconds=0.1,
        ):
            raise AssertionError("transport failure must not enter the operation")
