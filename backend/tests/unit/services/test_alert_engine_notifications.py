import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.price_alert import AlertStatus
from app.services import alert_engine


class _FakeDb:
    def __init__(self):
        self.added = []
        self.committed = False

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        self.added[-1].id = 99

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_fire_indicator_alert_persists_and_broadcasts_output_keys(monkeypatch):
    db = _FakeDb()
    alert = SimpleNamespace(
        id=7,
        user_id=11,
        instrument_id=42,
        instrument=SimpleNamespace(symbol="SPY"),
        indicator_a_type="bb",
        indicator_a_params={"period": 20, "std_dev": 2, "output": "bb_upper"},
        indicator_b_type="sma",
        condition="crosses_above",
        threshold_value=None,
        repeat=False,
        trigger_count=0,
        status=AlertStatus.ACTIVE,
        last_value_a=None,
        last_value_b=None,
    )
    send_notification = AsyncMock(return_value="notification-id")
    broadcast = AsyncMock()
    monkeypatch.setattr(alert_engine, "send_indicator_alert_notification", send_notification)
    monkeypatch.setattr(alert_engine.ws_manager, "broadcast_to_user", broadcast)

    await alert_engine._fire_indicator_alert(
        db, alert, 501.25, 500.0, output_a="bb_upper", output_b="sma"
    )

    snapshot = json.loads(db.added[0].condition_snapshot)
    assert snapshot["output_a"] == "bb_upper"
    assert snapshot["indicator_b"] == "sma"
    assert snapshot["output_b"] == "sma"
    send_notification.assert_awaited_once_with(
        symbol="SPY",
        indicator_type="bb",
        condition="crosses_above",
        value=501.25,
        threshold=500.0,
        alert_id=7,
        output_a="bb_upper",
        output_b="sma",
        indicator_b_type="sma",
    )
    payload = broadcast.await_args.args[1]
    assert payload["output_a"] == "bb_upper"
    assert payload["indicator_b"] == "sma"
    assert payload["output_b"] == "sma"
    assert db.committed is True
