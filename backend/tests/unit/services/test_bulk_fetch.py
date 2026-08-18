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
