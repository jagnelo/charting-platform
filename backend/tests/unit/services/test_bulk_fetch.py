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


def test_bars_through_end_rejects_future_provider_rows():
    end = bulk_fetch.datetime(2024, 1, 2, tzinfo=bulk_fetch.UTC)
    bars = [
        SimpleNamespace(ts=bulk_fetch.datetime(2024, 1, 1)),
        SimpleNamespace(ts=bulk_fetch.datetime(2024, 1, 2, 23, 59)),
        SimpleNamespace(ts=bulk_fetch.datetime(2024, 1, 3)),
    ]

    assert bulk_fetch._bars_through_end(bars, end) == bars[:1]


@pytest.mark.asyncio
async def test_bulk_fetch_failure_state_redacts_provider_credentials(monkeypatch):
    async def failing_fetch(**_kwargs):
        raise RuntimeError("GET https://provider.test/data?api_key=bulk-secret")

    monkeypatch.setattr(bulk_fetch, "_do_fetch_and_store", failing_fetch)

    result = await bulk_fetch._fetch_one_timeframe(
        db=object(),
        instrument=object(),
        ticker_sym="SPY",
        timeframe=Timeframe.D1,
        adjusted=True,
        end=bulk_fetch.datetime(2024, 1, 2, tzinfo=bulk_fetch.UTC),
    )

    assert isinstance(result, str)
    assert "bulk-secret" not in result
    assert "<redacted>" in result
    assert len(result) <= len("error:") + 1000


@pytest.mark.asyncio
async def test_bulk_fetch_attaches_provider_series_before_persisting(monkeypatch):
    bar = SimpleNamespace(ts=bulk_fetch.datetime(2024, 1, 1, tzinfo=bulk_fetch.UTC))
    execution = SimpleNamespace(
        provider_name="alpaca",
        data_source=SimpleNamespace(id=9),
        result=[bar],
    )
    calls: dict[str, object] = {}

    async def _fake_execute(*_args, **_kwargs):
        return execution

    async def _fake_attach(_db, _instrument, timeframe, adjusted, execution_arg, **kwargs):
        received = kwargs["bars"]
        calls["attach"] = (timeframe, adjusted, execution_arg, kwargs)
        received[0].market_series_id = 123
        return received

    async def _fake_existing(*_args, **_kwargs):
        return set()

    async def _fake_record(*_args, **_kwargs):
        calls["record"] = True

    async def _fake_touch(*_args, **_kwargs):
        calls["touch"] = True

    class _Db:
        def add_all(self, rows):
            calls["rows"] = rows

        async def commit(self):
            calls["committed"] = True

    monkeypatch.setattr(bulk_fetch, "execute_provider_call", _fake_execute)
    monkeypatch.setattr(bulk_fetch, "_attach_provider_series", _fake_attach)
    monkeypatch.setattr(bulk_fetch, "_existing_timestamps", _fake_existing)
    monkeypatch.setattr(bulk_fetch, "_record_bar_observations", _fake_record)
    monkeypatch.setattr(bulk_fetch, "_touch_ohlcv_dataset_state", _fake_touch)

    instrument = SimpleNamespace(id=42, symbol="SPY")
    result = await bulk_fetch._do_fetch_and_store(
        _Db(), instrument, "SPY", Timeframe.D1, True, bar.ts
    )

    assert result == 1
    assert calls["attach"][0:2] == (Timeframe.D1, True)
    assert calls["attach"][2] is execution
    assert calls["rows"] == [bar]
    assert bar.market_series_id == 123
    assert calls["committed"] is True
