from unittest.mock import AsyncMock

import pytest

from app.routers import data_preparation


@pytest.mark.asyncio
async def test_committed_preparation_wakeup_targets_registered_worker(monkeypatch):
    redis = AsyncMock()
    redis.aclose = AsyncMock()
    pool_factory = AsyncMock(return_value=redis)
    monkeypatch.setattr(data_preparation, "create_pool", pool_factory)

    await data_preparation._wake_refresh_worker()

    pool_factory.assert_awaited_once()
    args, kwargs = redis.enqueue_job.await_args
    assert args[0] == "task_process_refresh_jobs"
    assert kwargs["_expires"] == 600
    assert kwargs["_job_id"].startswith("data-preparation-wakeup:")
    redis.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_wakeup_failure_does_not_replace_durable_database_queue(monkeypatch):
    pool_factory = AsyncMock(side_effect=RuntimeError("redis unavailable"))
    monkeypatch.setattr(data_preparation, "create_pool", pool_factory)

    await data_preparation._wake_refresh_worker()

    pool_factory.assert_awaited_once()
