import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)
ONESIGNAL_API_URL = "https://onesignal.com/api/v1/notifications"


async def _send(title: str, message: str, url: str = "/", data: dict | None = None) -> str | None:
    if not settings.ONESIGNAL_APP_ID or not settings.ONESIGNAL_REST_API_KEY:
        logger.warning("OneSignal not configured")
        return None
    payload = {
        "app_id": settings.ONESIGNAL_APP_ID,
        "included_segments": ["All"],
        "headings": {"en": title},
        "contents": {"en": message},
        "url": url,
    }
    if data:
        payload["data"] = data
    headers = {
        "Authorization": f"Basic {settings.ONESIGNAL_REST_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(ONESIGNAL_API_URL, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json().get("id")
    except Exception as e:
        logger.error(f"OneSignal error: {e}")
    return None


async def send_alert_notification(
    symbol, condition, threshold, current_price, alert_id
) -> str | None:
    text_map = {
        "crosses_above": "crossed above",
        "crosses_below": "dropped below",
        "touches": "touched",
        "percent_change_up": "rose to",
        "percent_change_down": "fell to",
    }
    verb = text_map.get(condition, condition)
    return await _send(
        title=f"🔔 {symbol} Alert",
        message=f"{symbol} has {verb} ${threshold:,.4f} — current: ${current_price:,.4f}",
        url=f"/chart/{symbol}",
        data={"alert_id": alert_id, "alert_kind": "price", "symbol": symbol},
    )


async def send_indicator_alert_notification(
    symbol, indicator_type, condition, value, threshold, alert_id
) -> str | None:
    return await _send(
        title=f"🔔 {symbol} — {indicator_type.upper()} Alert",
        message=f"{symbol} {indicator_type.upper()} {condition} {threshold:.4f} (current: {value:.4f})",
        url=f"/chart/{symbol}",
        data={"alert_id": alert_id, "alert_kind": "indicator", "symbol": symbol},
    )
