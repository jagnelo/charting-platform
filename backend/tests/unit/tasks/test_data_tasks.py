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
    job = SimpleNamespace(
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

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def commit(self):
            self.commits += 1

        async def rollback(self):
            self.rollbacks += 1
            self.failed = False

        async def refresh(self, refreshed_job):
            assert refreshed_job is job
            self.refreshes += 1
            assert not self.failed
            if self.refreshes == 2:
                assert self.rollbacks == 1

    session = Session()
    retry_calls = []

    async def complete_with_database_error(*_args, **_kwargs):
        session.failed = True
        raise RuntimeError("database transaction aborted while persisting outcome")

    async def retry(_db, retried_job, error, **kwargs):
        assert session.rollbacks == 1
        assert retried_job is job
        retry_calls.append((error, kwargs))
        retried_job.next_attempt_at = datetime(2026, 11, 7, 12, tzinfo=UTC)

    monkeypatch.setattr(data_tasks, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(data_tasks, "claim_refresh_jobs", AsyncMock(return_value=[job]))
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
    monkeypatch.setattr(data_tasks, "claim_refresh_jobs", AsyncMock(return_value=[history_job]))
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
