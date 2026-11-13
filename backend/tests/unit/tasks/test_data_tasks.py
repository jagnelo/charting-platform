from contextlib import nullcontext
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.ohlcv import Timeframe
from app.tasks import data_tasks


def test_maintenance_observation_bucket_matches_shared_hourly_freshness_window():
    first = datetime(2026, 11, 6, 14, 5, tzinfo=UTC)
    repeated = datetime(2026, 11, 6, 14, 59, tzinfo=UTC)
    later_same_day = datetime(2026, 11, 6, 21, 5, tzinfo=UTC)

    assert data_tasks._maintenance_observation_bucket(first) == (
        data_tasks._maintenance_observation_bucket(repeated)
    )
    assert data_tasks._maintenance_observation_bucket(first) != (
        data_tasks._maintenance_observation_bucket(later_same_day)
    )


class _Result:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class _Session:
    def __init__(self, instruments):
        self.instruments = instruments
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, *_args, **_kwargs):
        return _Result(self.instruments)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, _job):
        return None


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False


@pytest.mark.asyncio
async def test_nightly_history_refresh_materializes_coarse_views_when_provider_rows_are_missing(
    monkeypatch,
):
    instrument = SimpleNamespace(id=11, symbol="AAPL")
    session = _Session([instrument])
    newest = datetime(2026, 9, 11, tzinfo=UTC)
    fetch = AsyncMock(return_value=[])
    materialize = AsyncMock(return_value={Timeframe.W1.value: 52, Timeframe.MN.value: 24})

    monkeypatch.setattr(
        data_tasks,
        "AsyncSessionLocal",
        lambda: _SessionContext(session),
    )
    monkeypatch.setattr(
        data_tasks,
        "_get_newest_bar_ts",
        AsyncMock(
            side_effect=lambda _db, _instrument_id, timeframe: newest
            if timeframe == Timeframe.D1
            else None
        ),
    )
    monkeypatch.setattr(data_tasks, "fetch_ohlcv", fetch)
    monkeypatch.setattr(data_tasks, "materialize_derived_timeframes", materialize)

    result = await data_tasks.fetch_all_instruments_history({})

    assert result == {
        "instruments_refreshed": 1,
        "total_bars": 0,
        "derived_bars": {"W1": 52, "MN": 24},
    }
    fetch.assert_awaited_once()
    materialize.assert_awaited_once_with(session, instrument.id)
    assert session.commits == 1
    assert session.rollbacks == 0


@pytest.mark.asyncio
async def test_core_refresh_scheduler_uses_shared_workstation_maintenance_planner(monkeypatch):
    queued = []

    async def fake_maintenance(ctx, *, include_discovered):
        queued.append((ctx, include_discovered))
        return {"mode": "shared_preparation_queue", "queued": 4}

    monkeypatch.setattr(data_tasks, "enqueue_workstation_maintenance", fake_maintenance)

    result = await data_tasks.enqueue_core_refresh_jobs({"redis": "unused"})

    assert result == {"mode": "shared_preparation_queue", "queued": 4}
    assert queued == [({"redis": "unused"}, True)]


@pytest.mark.asyncio
async def test_refresh_worker_reselects_before_claiming_next_job(monkeypatch):
    session = _Session([])
    background_jobs = [
        SimpleNamespace(
            id=101 + index,
            capability=data_tasks.ProviderCapability.ACCOUNT_USAGE.value,
            priority=100,
            status="queued",
            attempts=0,
            lease_token=None,
            metadata_payload={"provider_account_usage_refresh": {"provider_name": "fmp"}},
        )
        for index in range(2)
    ]
    visible_job = SimpleNamespace(
        id=200,
        capability=data_tasks.ProviderCapability.ACCOUNT_USAGE.value,
        priority=10,
        status="pending",
        attempts=0,
        lease_token=None,
        metadata_payload={"provider_account_usage_refresh": {"provider_name": "alpaca"}},
    )
    processed = []
    claim_count = 0

    async def claim(_db, *, limit):
        nonlocal claim_count
        claim_count += 1
        assert limit == 1
        available = [job for job in [*background_jobs, visible_job] if job.status == "queued"]
        if not available:
            return []
        job = min(available, key=lambda item: (item.priority, item.id))
        job.status = "leased"
        job.lease_token = f"lease-{job.id}"
        return [job]

    async def run_native_usage(_db, request):
        provider_name = request["provider_name"]
        processed.append(provider_name)
        if provider_name == "fmp":
            visible_job.status = "queued"
        return {"status": "refreshed", "providers": [provider_name]}

    async def complete(_db, job, *, result_summary):
        job.status = "completed"
        job.result_summary = result_summary

    monkeypatch.setattr(data_tasks, "AsyncSessionLocal", lambda: _SessionContext(session))
    monkeypatch.setattr(data_tasks, "claim_refresh_jobs", claim)
    monkeypatch.setattr(data_tasks, "_run_native_usage_refresh_job", run_native_usage)
    monkeypatch.setattr(data_tasks, "complete_refresh_job", complete)

    result = await data_tasks.process_refresh_jobs({}, limit=2)

    assert result["claimed"] == 2
    assert processed == ["fmp", "alpaca"]
    assert background_jobs[1].status == "queued"
    assert claim_count == 2


@pytest.mark.asyncio
async def test_instrument_event_refresh_worker_uses_scoped_provider_and_queues_next_page(
    db, instrument, monkeypatch
):
    from app.models.instrument_event import InstrumentEventFetchState
    from app.models.market_data_foundation import MarketRefreshJob
    from app.models.provider_runtime import ProviderCapability
    from app.services import instrument_events
    from app.services.provider_runtime import _EXPLICIT_ACQUISITION_CONTEXT
    from tests.unit.conftest import AsyncSessionAdapter

    now = datetime(2026, 11, 8, 12, tzinfo=UTC)
    parent = MarketRefreshJob(
        request_key=f"instrument-events:{instrument.id}:v3:initial",
        instrument_id=instrument.id,
        capability=ProviderCapability.INSTRUMENT_EVENTS.value,
        priority=10,
        status="leased",
        attempts=1,
        next_attempt_at=now,
        lease_token="calendar-lease",
        metadata_payload={"instrument_event_refresh": {"instrument_id": instrument.id}},
    )
    db.add(parent)
    db.flush()
    async_db = AsyncSessionAdapter(db)
    calls = []

    async def fake_fetch(fetch_db, selected_instrument, *, seed_runtime):
        scope = _EXPLICIT_ACQUISITION_CONTEXT.get()
        assert fetch_db is async_db
        assert selected_instrument.id == instrument.id
        assert seed_runtime is False
        assert scope.instrument_id == instrument.id
        assert (ProviderCapability.INSTRUMENT_EVENTS, "fetch_instrument_events") in scope.operations
        calls.append(True)
        fetch_db.add(
            InstrumentEventFetchState(
                instrument_id=instrument.id,
                source="alpaca",
                fetched_at=now,
                event_count=4,
                earnings_count=0,
                fetch_version=3,
                continuation_token="opaque-next-page",
                query_fingerprint="a" * 64,
                page_count=1,
                complete=False,
            )
        )
        await fetch_db.flush()
        return 4

    monkeypatch.setattr(instrument_events, "fetch_and_store_instrument_events", fake_fetch)

    result = await data_tasks._process_instrument_events_refresh_job(async_db, parent)

    next_page = (
        db.query(MarketRefreshJob)
        .filter(
            MarketRefreshJob.capability == ProviderCapability.INSTRUMENT_EVENTS.value,
            MarketRefreshJob.id != parent.id,
        )
        .one()
    )
    assert calls == [True]
    assert result["preparation_status"] == "partial"
    assert result["reason_code"] == "event_page_continuation_pending"
    assert next_page.priority == 100
    assert next_page.request_key == f"instrument-events:{instrument.id}:alpaca:{'a' * 64}:1"


@pytest.mark.asyncio
async def test_instrument_event_refresh_worker_preserves_unknown_quota_as_terminal_hold(
    db, instrument, monkeypatch
):
    from app.models.market_data_foundation import MarketRefreshJob
    from app.models.provider_runtime import ProviderCapability
    from app.services import instrument_events
    from app.services.provider_runtime import ProviderQuotaUnknownError
    from tests.unit.conftest import AsyncSessionAdapter

    now = datetime(2026, 11, 8, 12, tzinfo=UTC)
    job = MarketRefreshJob(
        request_key=f"instrument-events:{instrument.id}:v3:initial",
        instrument_id=instrument.id,
        capability=ProviderCapability.INSTRUMENT_EVENTS.value,
        priority=10,
        status="leased",
        attempts=1,
        next_attempt_at=now,
        lease_token="calendar-lease",
        metadata_payload={"instrument_event_refresh": {"instrument_id": instrument.id}},
    )
    db.add(job)
    db.flush()

    async def unknown_quota(*_args, **_kwargs):
        raise ProviderQuotaUnknownError("native event quota state is unknown")

    monkeypatch.setattr(instrument_events, "fetch_and_store_instrument_events", unknown_quota)

    result = await data_tasks._process_instrument_events_refresh_job(AsyncSessionAdapter(db), job)

    assert result == {
        "preparation_status": "held",
        "reason_code": "provider_quota_state_unknown",
        "instrument_id": instrument.id,
    }


@pytest.mark.asyncio
async def test_workstation_maintenance_skips_controlled_e2e_market_data(monkeypatch):
    monkeypatch.setattr(data_tasks.settings, "E2E_SEED_MARKET_DATA", True)

    class NoDatabase:
        def __call__(self):
            raise AssertionError("E2E-owned fixtures must not run live maintenance planning")

    monkeypatch.setattr(data_tasks, "AsyncSessionLocal", NoDatabase())

    result = await data_tasks.enqueue_workstation_maintenance({})

    assert result == {"skipped": True, "reason": "controlled fixture mode owns workstation data"}


@pytest.mark.asyncio
async def test_refresh_worker_rolls_back_before_refreshing_and_retrying_failed_job(monkeypatch):
    class ExpiringJob:
        _expired_fields = {
            "id",
            "capability",
            "status",
            "attempts",
            "lease_token",
            "next_attempt_at",
            "metadata_payload",
        }

        def __init__(self, **values):
            self._expired = False
            self.__dict__.update(values)

        def __getattribute__(self, name):
            if name in ExpiringJob._expired_fields and object.__getattribute__(self, "_expired"):
                raise AssertionError(f"expired ORM field read without async reload: {name}")
            return object.__getattribute__(self, name)

    job = ExpiringJob(
        id=41,
        capability=data_tasks.ProviderCapability.ACCOUNT_USAGE.value,
        status="leased",
        attempts=3,
        lease_token="lease-41",
        next_attempt_at=None,
        metadata_payload={"provider_account_usage_refresh": {"provider_name": "alpaca"}},
    )
    reloaded_job = SimpleNamespace(
        id=41,
        capability=data_tasks.ProviderCapability.ACCOUNT_USAGE.value,
        status="leased",
        attempts=3,
        lease_token="lease-41",
        next_attempt_at=None,
        metadata_payload={"provider_account_usage_refresh": {"provider_name": "alpaca"}},
    )

    class Session:
        def __init__(self):
            self.commits = 0
            self.rollbacks = 0
            self.failed = False
            self.refreshes = 0
            self.no_autoflush = nullcontext()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def commit(self):
            self.commits += 1

        async def rollback(self):
            self.rollbacks += 1
            self.failed = False
            job._expired = True

        async def refresh(self, refreshed_job):
            assert refreshed_job is job
            self.refreshes += 1
            assert not self.failed
            if self.refreshes == 2:
                assert self.rollbacks == 1

        async def execute(self, statement):
            assert self.rollbacks == 1
            assert "market_refresh_job" in str(statement)
            params = statement.compile().params
            assert 41 in params.values()
            assert "leased" in params.values()
            assert "lease-41" in params.values()
            assert statement._for_update_arg is not None

            class Result:
                @staticmethod
                def scalar_one_or_none():
                    return reloaded_job

            return Result()

    session = Session()
    retry_calls = []

    async def complete_with_database_error(*_args, **_kwargs):
        session.failed = True
        raise RuntimeError("database transaction aborted while persisting outcome")

    async def retry(_db, retried_job, error, **kwargs):
        assert session.rollbacks == 1
        assert retried_job is reloaded_job
        assert retried_job.attempts == 3
        retry_calls.append((error, kwargs))
        retried_job.next_attempt_at = datetime(2026, 11, 7, 12, tzinfo=UTC)

    monkeypatch.setattr(data_tasks, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(data_tasks, "claim_refresh_jobs", AsyncMock(side_effect=[[job], []]))
    monkeypatch.setattr(
        data_tasks,
        "_run_native_usage_refresh_job",
        AsyncMock(return_value={"status": "refreshed", "providers": ["alpaca"]}),
    )
    monkeypatch.setattr(data_tasks, "complete_refresh_job", complete_with_database_error)
    monkeypatch.setattr(data_tasks, "retry_refresh_job", retry)

    result = await data_tasks.process_refresh_jobs({})

    assert result["retried"] == 1
    assert session.rollbacks == 1
    assert session.commits == 2  # Persist the lease, then persist the retry.
    assert retry_calls == [
        (
            "database transaction aborted while persisting outcome",
            {"retry_at": None, "lease_token": "lease-41"},
        )
    ]


@pytest.mark.asyncio
async def test_expected_native_usage_wait_commits_prerequisite_and_history_link(
    db, instrument, monkeypatch
):
    from sqlalchemy import select

    from app.models.market_data_foundation import MarketRefreshJob
    from tests.unit.conftest import AsyncSessionAdapter

    now = datetime(2026, 11, 7, 12, tzinfo=UTC)
    history_job = MarketRefreshJob(
        request_key="history-waits-for-native-usage",
        instrument_id=instrument.id,
        capability="price_history",
        timeframe=Timeframe.D1.value,
        priority=10,
        status="leased",
        attempts=0,
        next_attempt_at=now,
        lease_token="history-lease",
        metadata_payload={
            "data_preparation_child": {
                "range_mode": "deepest_admitted",
                "adjusted": True,
                "wait_for_job_ids": [],
            }
        },
    )
    db.add(history_job)
    db.flush()
    session = AsyncSessionAdapter(db)
    prerequisite_job_id = None
    retry_at = datetime(2030, 1, 1, tzinfo=UTC)

    async def plan_waiting_for_usage(
        plan_db, *, job, instrument, timeframe, preparation, priority, redis
    ):
        nonlocal prerequisite_job_id
        assert plan_db is session
        assert job is history_job
        usage_job = MarketRefreshJob(
            request_key="native-usage-prerequisite-history-wait",
            capability=data_tasks.ProviderCapability.ACCOUNT_USAGE.value,
            status="queued",
            attempts=0,
            next_attempt_at=now,
            metadata_payload={"provider_account_usage_refresh": {"provider_name": "alpaca"}},
        )
        session.add(usage_job)
        await session.flush()
        prerequisite_job_id = usage_job.id
        job.metadata_payload = {
            **job.metadata_payload,
            "data_preparation_child": {
                **job.metadata_payload["data_preparation_child"],
                "wait_for_job_ids": [usage_job.id],
            },
        }
        await session.flush()
        raise data_tasks.RefreshDependencyPending(retry_at=retry_at)

    monkeypatch.setattr(data_tasks, "AsyncSessionLocal", lambda: _SessionContext(session))
    monkeypatch.setattr(
        data_tasks, "claim_refresh_jobs", AsyncMock(side_effect=[[history_job], []])
    )
    monkeypatch.setattr(data_tasks, "_plan_and_fetch_history_chunk", plan_waiting_for_usage)

    result = await data_tasks.process_refresh_jobs({})

    assert result["retried"] == 1
    assert prerequisite_job_id is not None
    db.expire_all()
    persisted_jobs = list(
        db.execute(
            select(MarketRefreshJob).where(
                MarketRefreshJob.id.in_([history_job.id, prerequisite_job_id])
            )
        ).scalars()
    )
    by_id = {job.id: job for job in persisted_jobs}
    persisted_history = by_id[history_job.id]
    persisted_usage = by_id[prerequisite_job_id]
    assert persisted_usage.status == "queued"
    assert persisted_history.status == "deferred"
    assert persisted_history.next_attempt_at.replace(tzinfo=UTC) == retry_at
    assert persisted_history.metadata_payload["data_preparation_child"]["wait_for_job_ids"] == [
        prerequisite_job_id
    ]
