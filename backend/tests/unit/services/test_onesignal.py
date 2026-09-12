import pytest

from app.services import onesignal


@pytest.mark.asyncio
async def test_indicator_alert_notification_preserves_selected_outputs(monkeypatch):
    captured = {}

    async def fake_send(**kwargs):
        captured.update(kwargs)
        return "notification-id"

    monkeypatch.setattr(onesignal, "_send", fake_send)

    result = await onesignal.send_indicator_alert_notification(
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

    assert result == "notification-id"
    assert captured["title"] == "🔔 SPY — BB [bb_upper] vs SMA [sma] Alert"
    assert "BB [bb_upper] vs SMA [sma] crosses_above" in captured["message"]
    assert captured["data"]["output_a"] == "bb_upper"
    assert captured["data"]["output_b"] == "sma"
