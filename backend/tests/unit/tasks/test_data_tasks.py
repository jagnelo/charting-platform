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
