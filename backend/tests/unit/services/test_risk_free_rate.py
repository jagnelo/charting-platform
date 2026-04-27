from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.models.ohlcv import OHLCVBar, Timeframe
from app.services import risk_free_rate


@dataclass
class _ExecutionStub:
    provider_name: str
    data_source: object
    result: list[OHLCVBar]


@pytest.mark.asyncio
async def test_fetch_from_provider_persists_bars_via_market_data_helper(monkeypatch, instrument):
    bars = [
        OHLCVBar(
            instrument_id=instrument.id,
            data_source_id=1,
            timeframe=Timeframe.D1,
            ts=datetime(2026, 4, 25, tzinfo=UTC),
            open=Decimal("5.10"),
            high=Decimal("5.20"),
            low=Decimal("5.00"),
            close=Decimal("5.15"),
            volume=Decimal("1000"),
            is_adjusted=True,
        )
    ]
    calls: dict[str, object] = {}

    async def _fake_execute_provider_call(*args, **kwargs):
        return _ExecutionStub(
            provider_name="yfinance",
            data_source=type("DataSourceStub", (), {"id": 9})(),
            result=bars,
        )

    async def _fake_persist(db, instrument_arg, **kwargs):
        calls["instrument"] = instrument_arg
        calls["kwargs"] = kwargs

    monkeypatch.setattr(risk_free_rate, "execute_provider_call", _fake_execute_provider_call)
    monkeypatch.setattr(risk_free_rate, "persist_price_history_bars", _fake_persist)

    rate = await risk_free_rate._fetch_from_provider(None, instrument)  # type: ignore[arg-type]

    assert rate == pytest.approx(0.0515)
    assert calls["instrument"] == instrument
    assert calls["kwargs"]["data_source_id"] == 9
    assert calls["kwargs"]["timeframe"] == Timeframe.D1
    assert calls["kwargs"]["bars"] == bars
