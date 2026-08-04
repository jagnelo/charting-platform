import pytest

from app.config import settings
from app.tasks import data_tasks
from app.workers import arq_worker


@pytest.mark.asyncio
async def test_daily_history_refresh_is_explicitly_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "MARKET_DATA_REFRESH_SCHEDULE_ENABLED", False)

    result = await arq_worker.scheduled_daily_history_refresh({})

    assert result == {"skipped": True, "reason": "schedule disabled"}


@pytest.mark.asyncio
async def test_daily_history_refresh_delegates_to_canonical_batch_task(monkeypatch):
    monkeypatch.setattr(settings, "MARKET_DATA_REFRESH_SCHEDULE_ENABLED", True)
    calls = []

    async def fake_refresh(ctx):
        calls.append(ctx)
        return {"instruments_refreshed": 3, "total_bars": 12}

    monkeypatch.setattr(data_tasks, "fetch_all_instruments_history", fake_refresh)

    result = await arq_worker.scheduled_daily_history_refresh({"redis": "test"})

    assert result == {"instruments_refreshed": 3, "total_bars": 12}
    assert calls == [{"redis": "test"}]


def test_worker_registers_history_refresh_function():
    assert arq_worker.scheduled_daily_history_refresh in arq_worker.WorkerSettings.functions
