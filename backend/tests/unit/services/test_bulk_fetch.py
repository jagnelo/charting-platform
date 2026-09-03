from types import SimpleNamespace

import pytest

from app.models.ohlcv import Timeframe
from app.services import bulk_fetch


@pytest.mark.asyncio
async def test_bulk_fetch_honours_refresh_cancellation_before_provider_work(monkeypatch):
    events = []

    class Redis:
        async def get(self, key):
            assert key == bulk_fetch.refresh_cancel_key(17)
            return "1"

    async def publish(_redis, instrument_id, status, _timeframes, _summary):
        events.append((instrument_id, status))

    monkeypatch.setattr(bulk_fetch, "_publish_progress", publish)
    result = await bulk_fetch.bulk_fetch_instrument(
        object(),
        SimpleNamespace(id=42, symbol="SPY"),
        [Timeframe.D1],
        redis=Redis(),
        cancel_key=bulk_fetch.refresh_cancel_key(17),
    )

    assert result == {}
    assert events == [(42, "canceled")]


@pytest.mark.asyncio
async def test_bulk_fetch_passes_historical_end_to_each_provider_request(monkeypatch):
    requested_ends = []

    async def fetch_one(*, end, **_kwargs):
        requested_ends.append(end)
        return 0

    monkeypatch.setattr(bulk_fetch, "_fetch_one_timeframe", fetch_one)
    await bulk_fetch.bulk_fetch_instrument(
        object(),
        SimpleNamespace(id=42, symbol="SPY"),
        [Timeframe.D1, Timeframe.W1],
        end=bulk_fetch.datetime(2024, 1, 2),
    )

    assert requested_ends == [
        bulk_fetch.datetime(2024, 1, 2, tzinfo=bulk_fetch.UTC),
        bulk_fetch.datetime(2024, 1, 2, tzinfo=bulk_fetch.UTC),
    ]


@pytest.mark.asyncio
async def test_bulk_fetch_treats_empty_provider_result_as_chain_failure(monkeypatch):
    calls = []

    async def fake_execute(*_args, **kwargs):
        calls.append(kwargs["treat_empty_as_failure"])
        return SimpleNamespace(result=[], data_source=SimpleNamespace(id=1))

    class Session:
        async def commit(self):
            return None

    async def touch_state(*_args, **_kwargs):
        return None

    monkeypatch.setattr(bulk_fetch, "execute_provider_call", fake_execute)
    monkeypatch.setattr(bulk_fetch, "_touch_ohlcv_dataset_state", touch_state)

    result = await bulk_fetch._do_fetch_and_store(
        db=Session(),
        instrument=SimpleNamespace(id=42, symbol="SPY"),
        ticker_sym="SPY",
        timeframe=Timeframe.D1,
        adjusted=True,
        end=bulk_fetch.datetime(2024, 1, 2, tzinfo=bulk_fetch.UTC),
    )

    assert result == 0
    assert calls == [True]


def test_bars_through_end_rejects_future_provider_rows():
    end = bulk_fetch.datetime(2024, 1, 2, tzinfo=bulk_fetch.UTC)
    bars = [
        SimpleNamespace(ts=bulk_fetch.datetime(2024, 1, 1)),
        SimpleNamespace(ts=bulk_fetch.datetime(2024, 1, 2, 23, 59)),
        SimpleNamespace(ts=bulk_fetch.datetime(2024, 1, 3)),
    ]

    assert bulk_fetch._bars_through_end(bars, end) == bars[:1]
