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


@pytest.mark.asyncio
async def test_etf_classification_refresh_is_explicitly_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "ETF_HOLDINGS_CLASSIFICATION_REFRESH_ENABLED", False)

    result = await arq_worker.scheduled_etf_holdings_classification_refresh({})

    assert result == {"skipped": True, "reason": "classification refresh disabled"}


@pytest.mark.asyncio
async def test_etf_classification_refresh_delegates_to_bounded_task(monkeypatch):
    monkeypatch.setattr(settings, "ETF_HOLDINGS_CLASSIFICATION_REFRESH_ENABLED", True)
    from app.tasks import etf_holdings_tasks

    calls = []

    async def fake_refresh(ctx):
        calls.append(ctx)
        return {"processed": 2, "enriched": 8, "remaining": 1}

    monkeypatch.setattr(etf_holdings_tasks, "reconcile_etf_holdings_classifications_task", fake_refresh)

    result = await arq_worker.scheduled_etf_holdings_classification_refresh({"redis": "test"})

    assert result["processed"] == 2
    assert calls == [{"redis": "test"}]


def test_worker_registers_etf_classification_refresh_function():
    assert arq_worker.scheduled_etf_holdings_classification_refresh in arq_worker.WorkerSettings.functions


@pytest.mark.asyncio
async def test_core_workstation_bootstrap_delegates_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "CORE_WORKSTATION_BOOTSTRAP_ENABLED", True)
    calls = []

    async def fake_bootstrap(ctx):
        calls.append(ctx)
        return {"skipped": False, "history": {}, "holdings": {}}

    monkeypatch.setattr(arq_worker, "task_bootstrap_core_workstation", fake_bootstrap)

    result = await arq_worker.scheduled_core_workstation_bootstrap({"redis": "test"})

    assert result["skipped"] is False
    assert calls == [{"redis": "test"}]


@pytest.mark.asyncio
async def test_core_workstation_bootstrap_is_explicitly_skippable(monkeypatch):
    monkeypatch.setattr(settings, "CORE_WORKSTATION_BOOTSTRAP_ENABLED", False)

    result = await arq_worker.scheduled_core_workstation_bootstrap({})

    assert result == {"skipped": True, "reason": "bootstrap disabled"}


@pytest.mark.asyncio
async def test_worker_startup_queues_bootstrap_without_running_it_inline(monkeypatch):
    monkeypatch.setattr(settings, "CORE_WORKSTATION_BOOTSTRAP_ENABLED", True)
    calls = []

    class FakeRedis:
        async def enqueue_job(self, function, *args, **kwargs):
            calls.append((function, args, kwargs))
            return "job-1"

    async def fail_if_called(_ctx):
        raise AssertionError("startup must not run the provider sweep inline")

    monkeypatch.setattr(arq_worker, "task_bootstrap_core_workstation", fail_if_called)
    await arq_worker.worker_startup({"redis": FakeRedis()})

    assert calls == [
        (
            "task_bootstrap_core_workstation",
            (),
            {"_job_id": "core-workstation-bootstrap-startup-v4", "_expires": 3600},
        )
    ]


@pytest.mark.asyncio
async def test_worker_startup_does_not_fail_when_redis_is_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "CORE_WORKSTATION_BOOTSTRAP_ENABLED", True)
    await arq_worker.worker_startup({})


def test_worker_registers_core_bootstrap_and_startup_hook():
    assert arq_worker.task_bootstrap_core_workstation in arq_worker.WorkerSettings.functions
    assert arq_worker.WorkerSettings.on_startup is arq_worker.worker_startup
