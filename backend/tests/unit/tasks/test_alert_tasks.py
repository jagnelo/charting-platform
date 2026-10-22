from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.price_alert import AlertCondition, AlertStatus
from app.tasks import alert_tasks


class _Db:
    async def commit(self):
        return None


@pytest.mark.asyncio
async def test_price_alert_task_broadcast_uses_canonical_utc_z_timestamp(monkeypatch):
    alert = SimpleNamespace(
        id=7,
        user_id=11,
        instrument=SimpleNamespace(symbol="SPY"),
        condition=AlertCondition.CROSSES_ABOVE,
        threshold_price=Decimal("500"),
        repeat=False,
        trigger_count=0,
        last_known_price=None,
        status=AlertStatus.ACTIVE,
        last_notification_id=None,
    )
    monkeypatch.setattr(alert_tasks, "send_alert_notification", AsyncMock(return_value=None))
    broadcast = AsyncMock()
    monkeypatch.setattr(alert_tasks.ws_manager, "broadcast_to_user", broadcast)

    await alert_tasks._fire_price_alert(_Db(), alert, 501.25)

    payload = broadcast.await_args.args[1]
    assert payload["triggered_at"].endswith("Z")
    assert "+00:00" not in payload["triggered_at"]


@pytest.mark.asyncio
async def test_indicator_alert_task_broadcast_uses_canonical_utc_z_timestamp(monkeypatch):
    alert = SimpleNamespace(
        id=8,
        user_id=12,
        instrument=SimpleNamespace(symbol="QQQ"),
        indicator_a_type="rsi",
        condition=AlertCondition.CROSSES_BELOW,
        threshold_value=Decimal("30"),
        repeat=True,
        trigger_count=0,
        status=AlertStatus.ACTIVE,
        last_notification_id=None,
    )
    monkeypatch.setattr(alert_tasks, "send_alert_notification", AsyncMock(return_value=None))
    broadcast = AsyncMock()
    monkeypatch.setattr(alert_tasks.ws_manager, "broadcast_to_user", broadcast)

    await alert_tasks._fire_indicator_alert(_Db(), alert, 29.5)

    payload = broadcast.await_args.args[1]
    assert payload["triggered_at"].endswith("Z")
    assert "+00:00" not in payload["triggered_at"]
