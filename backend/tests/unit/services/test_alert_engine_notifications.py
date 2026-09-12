import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.price_alert import AlertStatus
from app.schemas.alert import IndicatorAlertOut, PriceAlertOut
from app.schemas.alert_history import AlertFiringEventOut
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
    assert payload["triggered_at"].endswith("Z")
    assert db.committed is True


def test_alert_history_schema_serializes_timestamps_as_canonical_utc_z():
    event = SimpleNamespace(
        id=12,
        instrument_id=42,
        instrument_symbol="SPY",
        alert_type="indicator",
        alert_id=7,
        fired_at=datetime(2026, 9, 12, 14, 30, tzinfo=UTC),
        trigger_value=501.25,
        condition_snapshot='{"indicator":"bb","output_a":"bb_upper"}',
        is_viewed=False,
        created_at=datetime(2026, 9, 12, 15, 30),
    )

    payload = AlertFiringEventOut.model_validate(event).model_dump(mode="json")

    assert payload["fired_at"] == "2026-09-12T14:30:00Z"
    assert payload["created_at"] == "2026-09-12T15:30:00Z"
    assert payload["condition_snapshot"] == {"indicator": "bb", "output_a": "bb_upper"}


def test_alert_list_schemas_serialize_timestamps_as_canonical_utc_z():
    price = SimpleNamespace(
        id=1,
        instrument_id=42,
        instrument_currency="USD",
        instrument_symbol="SPY",
        condition="crosses_above",
        threshold_price=501.25,
        reference_price=None,
        price_field="close",
        within_percent=None,
        status="active",
        repeat=False,
        show_projection=False,
        notes=None,
        triggered_at=datetime(2026, 9, 12, 14, 30),
        trigger_count=0,
        last_known_price=None,
        created_at=datetime(2026, 9, 12, 15, 30, tzinfo=UTC),
        updated_at=datetime(2026, 9, 12, 16, 30),
    )
    indicator = SimpleNamespace(
        id=2,
        instrument_id=42,
        instrument_currency="USD",
        instrument_symbol="SPY",
        timeframe="D1",
        indicator_a_type="bb",
        indicator_a_params={"period": 20, "output": "bb_upper"},
        condition="crosses_above",
        threshold_value=501.25,
        indicator_b_type=None,
        indicator_b_params=None,
        status="active",
        repeat=False,
        notes=None,
        triggered_at=None,
        trigger_count=0,
        last_value_a=None,
        last_value_b=None,
        created_at=datetime(2026, 9, 12, 15, 30, tzinfo=UTC),
        updated_at=datetime(2026, 9, 12, 16, 30),
    )

    price_payload = PriceAlertOut.model_validate(price).model_dump(mode="json")
    indicator_payload = IndicatorAlertOut.model_validate(indicator).model_dump(mode="json")

    assert price_payload["triggered_at"] == "2026-09-12T14:30:00Z"
    assert price_payload["created_at"] == "2026-09-12T15:30:00Z"
    assert price_payload["updated_at"] == "2026-09-12T16:30:00Z"
    assert indicator_payload["triggered_at"] is None
    assert indicator_payload["created_at"] == "2026-09-12T15:30:00Z"
    assert indicator_payload["updated_at"] == "2026-09-12T16:30:00Z"
