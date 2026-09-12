from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.models.ohlcv import Timeframe
from app.tasks import data_tasks
from app.workers import arq_worker


class _AsyncNested:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class _RefreshRunSession:
    def __init__(self, run):
        self.run = run
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, _model, _run_id):
        return self.run

    def begin_nested(self):
        return _AsyncNested()

    async def commit(self):
        self.commits += 1


class _RefreshQueueSession:
    def __init__(self):
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, _model, _instrument_id):
        return SimpleNamespace(id=_instrument_id, symbol="AAPL")

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_daily_history_refresh_is_explicitly_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "MARKET_DATA_REFRESH_SCHEDULE_ENABLED", False)

    result = await arq_worker.scheduled_daily_history_refresh({})

    assert result == {"skipped": True, "reason": "schedule disabled"}


@pytest.mark.asyncio
async def test_daily_history_refresh_delegates_to_canonical_batch_task(monkeypatch):
    monkeypatch.setattr(settings, "MARKET_DATA_REFRESH_SCHEDULE_ENABLED", True)
    calls = []

    async def fake_enqueue(ctx):
        calls.append(ctx)
        return {"queued": 3, "mode": "enqueue_only"}

    monkeypatch.setattr(data_tasks, "enqueue_core_refresh_jobs", fake_enqueue)

    result = await arq_worker.scheduled_daily_history_refresh({"redis": "test"})

    assert result == {"queued": 3, "mode": "enqueue_only"}
    assert calls == [{"redis": "test"}]


@pytest.mark.asyncio
async def test_refresh_queue_process_delegates_to_bounded_worker_task(monkeypatch):
    monkeypatch.setattr(settings, "MARKET_DATA_REFRESH_SCHEDULE_ENABLED", True)
    calls = []

    async def fake_process(ctx):
        calls.append(ctx)
        return {"claimed": 4, "completed": 3, "retried": 1}

    monkeypatch.setattr(data_tasks, "process_refresh_jobs", fake_process)

    result = await arq_worker.scheduled_refresh_queue_process({"redis": "test"})

    assert result == {"claimed": 4, "completed": 3, "retried": 1}
    assert calls == [{"redis": "test"}]


@pytest.mark.asyncio
async def test_refresh_queue_does_not_retry_after_lease_is_lost(monkeypatch):
    from app.services.market_refresh_queue import RefreshLeaseLostError

    session = _RefreshQueueSession()
    job = SimpleNamespace(
        id=7,
        instrument_id=42,
        timeframe="D1",
        start_at=None,
        end_at=None,
    )
    monkeypatch.setattr(data_tasks, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(data_tasks, "claim_refresh_jobs", AsyncMock(return_value=[job]))
    monkeypatch.setattr(data_tasks, "fetch_ohlcv", AsyncMock(return_value=[]))
    complete = AsyncMock(side_effect=RefreshLeaseLostError("reclaimed"))
    retry = AsyncMock()
    monkeypatch.setattr(data_tasks, "complete_refresh_job", complete)
    monkeypatch.setattr(data_tasks, "retry_refresh_job", retry)

    result = await data_tasks.process_refresh_jobs({})

    assert result == {"claimed": 1, "completed": 0, "retried": 0, "lease_lost": 1}
    complete.assert_awaited_once_with(session, job)
    retry.assert_not_awaited()
    assert session.commits == 1


@pytest.mark.asyncio
async def test_single_instrument_refresh_forwards_worker_redis_to_canonical_fetch(monkeypatch):
    session = _RefreshQueueSession()
    redis = object()
    calls = []

    async def fake_fetch(db, instrument, timeframe, start, **kwargs):
        calls.append((db, instrument.id, timeframe, start, kwargs))
        return ["bar-1", "bar-2"]

    monkeypatch.setattr("app.database.AsyncSessionLocal", lambda: session)
    monkeypatch.setattr("app.services.market_data.fetch_ohlcv", fake_fetch)

    result = await arq_worker.task_refresh_instrument_data({"redis": redis}, 42, "D1")

    assert result == {"bars_fetched": 2}
    assert len(calls) == 1
    assert calls[0][1:3] == (42, Timeframe.D1)
    assert calls[0][4] == {"redis": redis}


@pytest.mark.asyncio
async def test_tokenized_asset_refresh_is_explicitly_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "TOKENIZED_ASSET_REFRESH_ENABLED", False)

    result = await arq_worker.scheduled_tokenized_asset_refresh({})

    assert result == {"skipped": True, "reason": "tokenized refresh disabled"}


@pytest.mark.asyncio
async def test_tokenized_asset_refresh_delegates_to_bounded_task(monkeypatch):
    monkeypatch.setattr(settings, "TOKENIZED_ASSET_REFRESH_ENABLED", True)
    calls = []

    async def fake_refresh(ctx):
        calls.append(ctx)
        return {"status": "refreshed", "refreshed": 2}

    monkeypatch.setattr(data_tasks, "refresh_tokenized_asset_prices", fake_refresh)
    result = await arq_worker.scheduled_tokenized_asset_refresh({"redis": "test"})

    assert result == {"status": "refreshed", "refreshed": 2}
    assert calls == [{"redis": "test"}]


@pytest.mark.asyncio
async def test_tokenized_event_refresh_is_explicitly_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "TOKENIZED_EVENT_REFRESH_ENABLED", False)

    result = await arq_worker.scheduled_tokenized_event_refresh({})

    assert result == {"skipped": True, "reason": "tokenized event refresh disabled"}


@pytest.mark.asyncio
async def test_tokenized_event_refresh_delegates_to_bounded_task(monkeypatch):
    monkeypatch.setattr(settings, "TOKENIZED_EVENT_REFRESH_ENABLED", True)
    calls = []

    async def fake_refresh(ctx):
        calls.append(ctx)
        return {"status": "refreshed", "events": 3}

    monkeypatch.setattr(data_tasks, "refresh_tokenized_corporate_actions", fake_refresh)
    result = await arq_worker.scheduled_tokenized_event_refresh({"redis": "test"})

    assert result == {"status": "refreshed", "events": 3}
    assert calls == [{"redis": "test"}]


@pytest.mark.asyncio
async def test_market_event_prelisting_is_explicitly_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "MARKET_EVENTS_PRELISTING_ENABLED", False)

    result = await arq_worker.scheduled_market_event_prelisting({})

    assert result == {"skipped": True, "reason": "pre-listing materialization disabled"}


@pytest.mark.asyncio
async def test_market_event_prelisting_delegates_to_bounded_task(monkeypatch):
    monkeypatch.setattr(settings, "MARKET_EVENTS_PRELISTING_ENABLED", True)
    calls = []

    async def fake_materialize(ctx):
        calls.append(ctx)
        return {"materialized": {"created": 2}, "promoted": {"promoted": 1}}

    monkeypatch.setattr(data_tasks, "materialize_market_event_prelisting", fake_materialize)

    result = await arq_worker.scheduled_market_event_prelisting({"redis": "test"})

    assert result == {"materialized": {"created": 2}, "promoted": {"promoted": 1}}
    assert calls == [{"redis": "test"}]


@pytest.mark.asyncio
async def test_edgar_issuer_universe_scan_is_explicitly_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_ENABLED", False)

    result = await arq_worker.scheduled_edgar_ipo_universe_scan({})

    assert result == {"skipped": True, "reason": "EDGAR issuer-universe scan disabled"}


@pytest.mark.asyncio
async def test_edgar_issuer_universe_scan_delegates_to_bounded_task(monkeypatch):
    monkeypatch.setattr(settings, "MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_ENABLED", True)
    calls = []

    async def fake_scan(ctx):
        calls.append(ctx)
        return {"status": "partial", "issuers_considered": 50}

    monkeypatch.setattr(data_tasks, "refresh_edgar_ipo_pipeline_for_issuer_universe", fake_scan)

    result = await arq_worker.scheduled_edgar_ipo_universe_scan({"redis": "test"})

    assert result == {"status": "partial", "issuers_considered": 50}
    assert calls == [{"redis": "test"}]


def test_edgar_issuer_universe_scan_is_registered_in_worker_functions():
    assert arq_worker.scheduled_edgar_ipo_universe_scan in arq_worker.WorkerSettings.functions


@pytest.mark.asyncio
async def test_edgar_directory_scan_is_explicitly_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ENABLED", False)

    result = await arq_worker.scheduled_edgar_ipo_directory_scan({})

    assert result == {"skipped": True, "reason": "EDGAR SEC directory scan disabled"}


@pytest.mark.asyncio
async def test_edgar_directory_scan_delegates_to_bounded_task(monkeypatch):
    monkeypatch.setattr(settings, "MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ENABLED", True)
    calls = []

    async def fake_scan(ctx):
        calls.append(ctx)
        return {"status": "partial", "directory_offset": 50}

    monkeypatch.setattr(data_tasks, "refresh_edgar_ipo_pipeline_for_sec_directory", fake_scan)

    result = await arq_worker.scheduled_edgar_ipo_directory_scan({"redis": "test"})

    assert result == {"status": "partial", "directory_offset": 50}
    assert calls == [{"redis": "test"}]


@pytest.mark.asyncio
async def test_edgar_scan_tasks_are_mutually_exclusive(monkeypatch):
    monkeypatch.setattr(settings, "MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_ENABLED", True)
    monkeypatch.setattr(settings, "MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ENABLED", True)

    issuer_result = await data_tasks.refresh_edgar_ipo_pipeline_for_issuer_universe({})
    directory_result = await data_tasks.refresh_edgar_ipo_pipeline_for_sec_directory({})

    assert issuer_result == {
        "skipped": True,
        "reason": "EDGAR issuer and SEC directory scans are mutually exclusive",
    }
    assert directory_result == issuer_result


@pytest.mark.asyncio
async def test_edgar_directory_scan_requires_reviewed_submissions_budget(monkeypatch):
    monkeypatch.setattr(settings, "MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ENABLED", True)
    monkeypatch.setattr(settings, "MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_ENABLED", False)
    monkeypatch.setattr(settings, "MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_SUBMISSIONS_REQUESTS", 0)

    result = await data_tasks.refresh_edgar_ipo_pipeline_for_sec_directory({})

    assert result == {
        "skipped": True,
        "reason": "EDGAR SEC directory submissions request budget not reviewed",
    }


def test_edgar_directory_scan_is_registered_in_worker_functions():
    assert arq_worker.scheduled_edgar_ipo_directory_scan in arq_worker.WorkerSettings.functions


def test_market_event_prelisting_is_registered_in_worker_functions():
    assert arq_worker.scheduled_market_event_prelisting in arq_worker.WorkerSettings.functions


@pytest.mark.asyncio
async def test_market_events_refresh_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "MARKET_EVENTS_REFRESH_ENABLED", False)
    result = await arq_worker.scheduled_market_events_refresh({"redis": "test"})
    assert result == {"skipped": True, "reason": "market-events refresh disabled"}


@pytest.mark.asyncio
async def test_market_events_refresh_delegates_to_bounded_task(monkeypatch):
    monkeypatch.setattr(settings, "MARKET_EVENTS_REFRESH_ENABLED", True)
    calls = []

    async def fake_refresh(ctx):
        calls.append(ctx)
        return {"status": "refreshed", "events": 4}

    monkeypatch.setattr(data_tasks, "refresh_market_events", fake_refresh)
    result = await arq_worker.scheduled_market_events_refresh({"redis": "test"})

    assert result == {"status": "refreshed", "events": 4}
    assert calls == [{"redis": "test"}]


def test_worker_registers_history_refresh_function():
    assert arq_worker.scheduled_daily_history_refresh in arq_worker.WorkerSettings.functions
    assert arq_worker.scheduled_refresh_queue_process in arq_worker.WorkerSettings.functions
    assert arq_worker.scheduled_tokenized_asset_refresh in arq_worker.WorkerSettings.functions
    assert arq_worker.scheduled_tokenized_event_refresh in arq_worker.WorkerSettings.functions
    assert arq_worker.scheduled_market_events_refresh in arq_worker.WorkerSettings.functions


@pytest.mark.asyncio
async def test_benchmark_family_dated_refresh_delegates_to_bounded_task(monkeypatch):
    from app.tasks import etf_holdings_tasks

    calls = []

    async def fake_refresh(ctx):
        calls.append(ctx)
        return {"refreshed": 8}

    monkeypatch.setattr(etf_holdings_tasks, "refresh_benchmark_family_holdings_task", fake_refresh)

    result = await arq_worker.scheduled_benchmark_family_holdings_refresh({"redis": "r"})

    assert result == {"refreshed": 8}
    assert calls == [{"redis": "r"}]


def test_worker_registers_benchmark_family_dated_refresh_function():
    assert (
        arq_worker.scheduled_benchmark_family_holdings_refresh
        in arq_worker.WorkerSettings.functions
    )


@pytest.mark.asyncio
async def test_scheduled_family_unit_refreshes_one_family_and_queues_history(monkeypatch):
    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def begin_nested(self):
            return _AsyncNested()

        async def commit(self):
            return None

    refresh_calls = []
    queue_calls = []

    async def fake_refresh(_db, *, family_key, requested_date, roles):
        refresh_calls.append((family_key, requested_date.isoformat(), roles))
        return {
            "family_key": family_key,
            "requested_date": requested_date,
            "roles": roles,
            "refreshed": 1,
            "unavailable": 0,
            "failed": 0,
            "legs": [{"status": "refreshed", "snapshot_id": 12}],
        }

    async def fake_queue(_db, redis, snapshot_ids):
        queue_calls.append((redis, snapshot_ids))
        return {"status": "queued", "queued": 4, "already_queued": 0}

    monkeypatch.setattr("app.database.AsyncSessionLocal", lambda: Session())
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.refresh_benchmark_family_holdings_for_date",
        fake_refresh,
    )
    monkeypatch.setattr(
        "app.services.benchmark_family_history.queue_snapshot_member_history",
        fake_queue,
    )

    result = await arq_worker.task_refresh_scheduled_benchmark_family_holdings_unit(
        {"redis": "redis"}, "sp500", "2026-07-31", ["cap_weight", "equal_weight"]
    )

    assert refresh_calls == [("sp500", "2026-07-31", ["cap_weight", "equal_weight"])]
    assert queue_calls == [("redis", [12])]
    assert result["requested_date"] == "2026-07-31"
    assert result["snapshot_ids"] == [12]
    assert result["history_queue"]["queued"] == 4


def test_worker_registers_scheduled_family_unit_function():
    assert (
        arq_worker.task_refresh_scheduled_benchmark_family_holdings_unit
        in arq_worker.WorkerSettings.functions
    )


@pytest.mark.asyncio
async def test_family_holdings_refresh_worker_persists_each_unit_and_aggregates_results(
    monkeypatch,
):
    from types import SimpleNamespace

    run = SimpleNamespace(
        id=7,
        family_keys=["sp500", "nasdaq100"],
        roles=["cap_weight"],
        requested_dates=["2026-03-31", "2026-06-30"],
        total_units=4,
        completed_units=0,
        refreshed_count=0,
        unavailable_count=0,
        failed_count=0,
        status="queued",
        cancel_requested=False,
        progress={"units": []},
        started_at=None,
        finished_at=None,
    )
    session = _RefreshRunSession(run)
    calls = []

    async def fake_refresh(_db, *, family_key, requested_date, roles):
        calls.append((family_key, requested_date.isoformat(), roles))
        if family_key == "nasdaq100" and requested_date.isoformat() == "2026-03-31":
            return {
                "refreshed": 0,
                "unavailable": 0,
                "failed": 1,
                "legs": [],
                "error": "route unavailable",
            }
        return {"refreshed": 1, "unavailable": 0, "failed": 0, "legs": []}

    class SessionFactory:
        def __call__(self):
            return session

    monkeypatch.setattr("app.database.AsyncSessionLocal", SessionFactory())
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.refresh_benchmark_family_holdings_for_date",
        fake_refresh,
    )

    result = await arq_worker.task_refresh_benchmark_family_holdings_run({}, run.id)

    assert result == {
        "status": "completed",
        "run_id": 7,
        "completed_units": 4,
        "refreshed": 3,
        "unavailable": 0,
        "failed": 1,
    }
    assert run.status == "completed"
    assert run.completed_units == 4
    assert run.refreshed_count == 3
    assert run.failed_count == 1
    assert run.progress["status"] == "completed"
    assert len(run.progress["units"]) == 4
    assert calls == [
        ("sp500", "2026-03-31", ["cap_weight"]),
        ("nasdaq100", "2026-03-31", ["cap_weight"]),
        ("sp500", "2026-06-30", ["cap_weight"]),
        ("nasdaq100", "2026-06-30", ["cap_weight"]),
    ]
    assert session.commits == 6


@pytest.mark.asyncio
async def test_family_holdings_refresh_worker_honours_durable_cancellation(monkeypatch):
    from types import SimpleNamespace

    run = SimpleNamespace(
        id=8,
        family_keys=["sp500"],
        roles=["cap_weight"],
        requested_dates=["2026-06-30"],
        total_units=1,
        completed_units=0,
        refreshed_count=0,
        unavailable_count=0,
        failed_count=0,
        status="queued",
        cancel_requested=True,
        progress={"units": []},
        started_at=None,
        finished_at=None,
    )
    session = _RefreshRunSession(run)
    monkeypatch.setattr("app.database.AsyncSessionLocal", lambda: session)

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("canceled runs must not call the provider-backed refresh")

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.refresh_benchmark_family_holdings_for_date",
        fail_if_called,
    )

    result = await arq_worker.task_refresh_benchmark_family_holdings_run({}, run.id)

    assert result == {"status": "canceled", "run_id": 8}
    assert run.status == "canceled"
    assert run.progress["cancel_requested"] is True


@pytest.mark.asyncio
async def test_family_holdings_refresh_worker_handoffs_refreshed_snapshots_to_member_history(
    monkeypatch,
):
    from types import SimpleNamespace

    run = SimpleNamespace(
        id=9,
        family_keys=["sp500"],
        roles=["cap_weight"],
        requested_dates=["2026-06-30"],
        total_units=1,
        completed_units=0,
        refreshed_count=0,
        unavailable_count=0,
        failed_count=0,
        status="queued",
        cancel_requested=False,
        progress={"units": []},
        started_at=None,
        finished_at=None,
    )
    session = _RefreshRunSession(run)
    queue_calls = []

    async def fake_refresh(_db, *, family_key, requested_date, roles):
        assert (family_key, requested_date.isoformat(), roles) == (
            "sp500",
            "2026-06-30",
            ["cap_weight"],
        )
        return {
            "refreshed": 1,
            "unavailable": 0,
            "failed": 0,
            "legs": [{"role": "cap_weight", "status": "refreshed", "snapshot_id": 101}],
        }

    async def fake_queue(_db, redis, snapshot_ids):
        queue_calls.append((redis, snapshot_ids))
        return {"status": "queued", "queued": 3, "already_queued": 1}

    monkeypatch.setattr("app.database.AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.refresh_benchmark_family_holdings_for_date",
        fake_refresh,
    )
    monkeypatch.setattr(
        "app.services.benchmark_family_history.queue_snapshot_member_history",
        fake_queue,
    )

    redis = object()
    result = await arq_worker.task_refresh_benchmark_family_holdings_run({"redis": redis}, run.id)

    assert result["status"] == "completed"
    assert queue_calls == [(redis, [101])]
    assert run.progress["units"][0]["history_queue"] == {
        "status": "queued",
        "queued": 3,
        "already_queued": 1,
    }


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

    monkeypatch.setattr(
        etf_holdings_tasks, "reconcile_etf_holdings_classifications_task", fake_refresh
    )

    result = await arq_worker.scheduled_etf_holdings_classification_refresh({"redis": "test"})

    assert result["processed"] == 2
    assert calls == [{"redis": "test"}]


def test_worker_registers_etf_classification_refresh_function():
    assert (
        arq_worker.scheduled_etf_holdings_classification_refresh
        in arq_worker.WorkerSettings.functions
    )


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


@pytest.mark.asyncio
async def test_provider_availability_schedules_are_disabled_without_explicit_live_flags(
    monkeypatch,
):
    monkeypatch.setattr(settings, "PROVIDER_AVAILABILITY_MONITOR_ENABLED", False)
    monkeypatch.setattr(settings, "PROVIDER_AVAILABILITY_LIVE_ENABLED", False)

    assert await arq_worker.scheduled_daily_provider_availability({}) == {"status": "disabled"}
    assert await arq_worker.scheduled_weekly_provider_availability({}) == {"status": "disabled"}


@pytest.mark.asyncio
async def test_provider_availability_schedules_delegate_to_the_expected_mode(monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_AVAILABILITY_MONITOR_ENABLED", True)
    monkeypatch.setattr(settings, "PROVIDER_AVAILABILITY_LIVE_ENABLED", True)
    calls = []

    class SessionContext:
        async def __aenter__(self):
            return "db"

        async def __aexit__(self, *_args):
            return None

    async def fake_run(db, mode, *, application_version):
        calls.append((db, mode, application_version))
        return {"mode": mode}

    from app.services import provider_availability

    monkeypatch.setattr("app.database.AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(provider_availability, "run_availability_probes", fake_run)

    assert await arq_worker.scheduled_daily_provider_availability({}) == {"mode": "daily_core"}
    assert await arq_worker.scheduled_weekly_provider_availability({}) == {
        "mode": "weekly_supported_sweep"
    }
    assert calls == [
        ("db", "daily_core", settings.APP_ENV),
        ("db", "weekly_supported_sweep", settings.APP_ENV),
    ]
