from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.models.ohlcv import Timeframe
from app.services import screener_engine
from app.services.indicators import OHLCVSeries


class _ScalarRows:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class _FakeDb:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, _statement):
        return _ScalarRows(self.rows)


def _bar(instrument_id: int, timeframe: Timeframe, ts: datetime, close: float):
    return SimpleNamespace(
        id=hash((instrument_id, timeframe, ts)),
        instrument_id=instrument_id,
        timeframe=timeframe,
        ts=ts,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1,
    )


def _series(closes: list[float], *, start: datetime | None = None) -> OHLCVSeries:
    start = start or datetime.now(UTC) - timedelta(days=len(closes))
    bars = [
        _bar(1, Timeframe.D1, start + timedelta(days=index), close)
        for index, close in enumerate(closes)
    ]
    return OHLCVSeries.from_orm_bars(bars)


def test_required_condition_timeframes_collects_nested_dependencies():
    required = screener_engine._required_condition_timeframes(
        {
            "operator": "AND",
            "conditions": [
                {"type": "performance", "period": "1M"},
                {
                    "operator": "OR",
                    "conditions": [{"type": "week52_new_high"}],
                },
            ],
        },
        Timeframe.H4,
    )

    assert required == {Timeframe.H4, Timeframe.D1, Timeframe.W1}


@pytest.mark.asyncio
async def test_grouped_bar_preflight_loads_each_instrument_timeframe_once():
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [
        _bar(2, Timeframe.D1, ts, 10),
        _bar(2, Timeframe.D1, ts + timedelta(days=1), 11),
        _bar(2, Timeframe.W1, ts, 10),
        _bar(2, Timeframe.W1, ts + timedelta(days=7), 12),
        _bar(3, Timeframe.D1, ts, 20),
        _bar(3, Timeframe.D1, ts + timedelta(days=1), 21),
    ]

    snapshots = await screener_engine._load_bars_by_instrument(
        _FakeDb(rows),
        [2, 3],
        {Timeframe.D1, Timeframe.W1},
    )

    assert set(snapshots) == {2, 3}
    assert set(snapshots[2]) == {Timeframe.D1, Timeframe.W1}
    assert set(snapshots[3]) == {Timeframe.D1}
    assert snapshots[2][Timeframe.D1].closes.tolist() == [10.0, 11.0]


@pytest.mark.asyncio
async def test_evaluation_uses_preflight_dependency_without_local_reload(monkeypatch):
    now = datetime.now(UTC)
    primary = _series([1.0, 1.0], start=now - timedelta(days=2))
    daily = _series(
        [100.0, 110.0, 120.0],
        start=now - timedelta(days=2),
    )

    async def unexpected_reload(*_args, **_kwargs):
        raise AssertionError("preflight dependency was reloaded during evaluation")

    monkeypatch.setattr(screener_engine, "_load_bars", unexpected_reload)
    matched, computed = await screener_engine._evaluate_condition(
        {"type": "performance", "period": "1D", "op": "gt", "value": 0.05},
        primary,
        SimpleNamespace(id=1),
        Timeframe.W1,
        object(),
        series_by_timeframe={Timeframe.W1: primary, Timeframe.D1: daily},
    )

    assert matched is True
    assert computed["performance"] > 0.05
