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
    symbol,
    indicator_type,
    condition,
    value,
    threshold,
    alert_id,
    output_a: str | None = None,
    output_b: str | None = None,
    indicator_b_type: str | None = None,
) -> str | None:
    indicator_label = indicator_type.upper()
    if output_a:
        indicator_label = f"{indicator_label} [{output_a}]"
    if output_b:
        right_label = (indicator_b_type or indicator_type).upper()
        indicator_label = f"{indicator_label} vs {right_label} [{output_b}]"
    return await _send(
        title=f"🔔 {symbol} — {indicator_label} Alert",
        message=f"{symbol} {indicator_label} {condition} {threshold:.4f} (current: {value:.4f})",
        url=f"/chart/{symbol}",
        data={
            "alert_id": alert_id,
            "alert_kind": "indicator",
            "symbol": symbol,
            **({"output_a": output_a} if output_a else {}),
            **({"output_b": output_b} if output_b else {}),
        },
    )


async def send_provider_availability_notification(
    provider: str, capability: str, classification: str, *, recovered: bool = False
) -> str | None:
    """Notify only on a confirmed failure/recovery transition.

    Cooldown and streak decisions happen in the availability service so this
    transport remains reusable and does not need database access.
    """
    if recovered:
        return await _send(
            title=f"✅ {provider} recovered",
            message=f"{provider} is healthy again for {capability}.",
            url="/legacy/settings",
            data={"provider": provider, "capability": capability, "classification": classification},
        )
    return await _send(
        title=f"⚠️ {provider} availability",
        message=f"{provider} {capability}: {classification}.",
        url="/legacy/settings",
        data={"provider": provider, "capability": capability, "classification": classification},
    )
