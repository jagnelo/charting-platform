from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.ohlcv import Timeframe
from app.tasks import data_tasks


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
