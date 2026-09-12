from types import SimpleNamespace

import pytest

from app.models.ohlcv import Timeframe
from app.services import alert_engine
from app.tasks import alert_tasks


class _FakeDb:
    def __init__(self, *instruments):
        self.instruments = {instrument.id: instrument for instrument in instruments}
        self.refreshes = []

    async def get(self, _model, instrument_id):
        return self.instruments.get(instrument_id)

    async def refresh(self, instrument, attributes):
        self.refreshes.append((instrument.id, tuple(attributes)))


@pytest.mark.asyncio
async def test_price_alert_preflight_polls_each_instrument_once(monkeypatch):
    instrument = SimpleNamespace(id=7, symbol="AAPL")
    db = _FakeDb(instrument)
    calls = []

    async def fake_price(_db, current_instrument):
        calls.append(current_instrument.id)
        return 210.0

    monkeypatch.setattr(alert_engine, "get_current_price_async", fake_price)
    alerts = {
        7: [SimpleNamespace(instrument_id=7), SimpleNamespace(instrument_id=7)],
    }

    prices = await alert_engine._preflight_price_alerts(db, alerts)

    assert prices == {7: 210.0}
    assert calls == [7]
    assert db.refreshes == [(7, ("listings", "provider_symbols"))]


@pytest.mark.asyncio
async def test_indicator_preflight_coalesces_alerts_by_instrument_and_timeframe(monkeypatch):
    instrument = SimpleNamespace(id=11, symbol="MSFT")
    db = _FakeDb(instrument)
    series = object()
    calls = []

    async def fake_series(_db, current_instrument, timeframe):
        calls.append((current_instrument.id, timeframe))
        return series

    monkeypatch.setattr(alert_engine, "_load_ohlcv_series", fake_series)
    alerts = [
        SimpleNamespace(instrument_id=11, timeframe=Timeframe.D1),
        SimpleNamespace(instrument_id=11, timeframe=Timeframe.D1),
    ]

    prepared = await alert_engine._preflight_indicator_alerts(db, alerts)

    assert prepared == {(11, Timeframe.D1): series}
    assert calls == [(11, Timeframe.D1)]
    assert db.refreshes == [(11, ("listings", "provider_symbols"))]


@pytest.mark.asyncio
async def test_indicator_preflight_keeps_failed_group_unavailable(monkeypatch):
    instrument = SimpleNamespace(id=13, symbol="NVDA")
    db = _FakeDb(instrument)

    async def failing_series(*_args):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(alert_engine, "_load_ohlcv_series", failing_series)
    alerts = [SimpleNamespace(instrument_id=13, timeframe=Timeframe.H1)]

    prepared = await alert_engine._preflight_indicator_alerts(db, alerts)

    assert prepared == {(13, Timeframe.H1): None}


@pytest.mark.asyncio
async def test_worker_alert_preflight_polls_each_instrument_once(monkeypatch):
    instrument = SimpleNamespace(id=17, symbol="TSLA")
    db = _FakeDb(instrument)
    calls = []

    async def fake_price(_db, current_instrument):
        calls.append(current_instrument.id)
        return 300.0

    monkeypatch.setattr(alert_tasks, "get_current_price_async", fake_price)
    alerts = {
        17: [SimpleNamespace(instrument_id=17), SimpleNamespace(instrument_id=17)],
    }

    prices = await alert_tasks._preflight_latest_prices(db, alerts)

    assert prices == {17: 300.0}
    assert calls == [17]


@pytest.mark.asyncio
async def test_worker_alert_preflight_forwards_redis_to_latest_price_gate(monkeypatch):
    instrument = SimpleNamespace(id=18, symbol="AMD")
    db = _FakeDb(instrument)
    redis = object()
    calls = []

    async def fake_price(_db, current_instrument, **kwargs):
        calls.append((current_instrument.id, kwargs))
        return 150.0

    monkeypatch.setattr(alert_tasks, "get_current_price_async", fake_price)
    prices = await alert_tasks._preflight_latest_prices(
        db,
        {18: [SimpleNamespace(instrument_id=18)]},
        redis=redis,
    )

    assert prices == {18: 150.0}
    assert calls == [(18, {"redis": redis})]


@pytest.mark.asyncio
async def test_worker_indicator_preflight_coalesces_local_bar_reads(monkeypatch):
    calls = []
    bars = [SimpleNamespace(ts="2026-09-12T00:00:00Z")]

    async def fake_recent(_db, instrument_id, timeframe):
        calls.append((instrument_id, timeframe))
        return bars

    monkeypatch.setattr(alert_tasks, "_get_recent_bars", fake_recent)
    alerts = [
        SimpleNamespace(instrument_id=23, timeframe=Timeframe.D1),
        SimpleNamespace(instrument_id=23, timeframe=Timeframe.D1),
    ]

    snapshots = await alert_tasks._preflight_recent_bars(object(), alerts)

    assert snapshots == {(23, Timeframe.D1): bars}
    assert calls == [(23, Timeframe.D1)]
