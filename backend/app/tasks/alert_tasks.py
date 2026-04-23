"""Background alert evaluation — both price and indicator alerts."""

import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.indicator_alert import IndicatorAlert
from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar
from app.models.price_alert import AlertCondition, AlertStatus, PriceAlert
from app.services import indicators as ind_engine
from app.services.market_data import get_current_price_async
from app.services.onesignal import send_alert_notification
from app.websocket.manager import ws_manager

logger = logging.getLogger(__name__)


def _price_condition_met(condition, threshold, last_price, current_price) -> bool:
    cp = float(current_price)
    tp = float(threshold)
    lp = float(last_price) if last_price is not None else None
    if condition == AlertCondition.TOUCHES:
        return abs(cp - tp) / max(tp, 1e-8) < 0.001
    if condition == AlertCondition.CROSSES_ABOVE:
        return (lp is None and cp > tp) or (lp is not None and lp <= tp < cp)
    if condition == AlertCondition.CROSSES_BELOW:
        return (lp is None and cp < tp) or (lp is not None and lp >= tp > cp)
    if condition == AlertCondition.PERCENT_CHANGE_UP:
        return cp >= tp
    if condition == AlertCondition.PERCENT_CHANGE_DOWN:
        return cp <= tp
    return False


def _indicator_condition_met(
    condition, current_val, prev_val, threshold_val, current_b, prev_b
) -> bool:
    from app.models.price_alert import AlertCondition as AC

    if threshold_val is not None:
        tv = float(threshold_val)
        cv = float(current_val)
        pv = float(prev_val) if prev_val is not None else None
        if condition == AC.CROSSES_ABOVE:
            return (pv is None and cv > tv) or (pv is not None and pv <= tv < cv)
        if condition == AC.CROSSES_BELOW:
            return (pv is None and cv < tv) or (pv is not None and pv >= tv > cv)
        if condition == AC.TOUCHES:
            return abs(cv - tv) / max(tv, 1e-8) < 0.001
        return False
    if current_b is not None:
        # Cross between two indicators
        if condition == AC.CROSSES_ABOVE:
            return (
                prev_val is not None
                and prev_b is not None
                and float(prev_val) <= float(prev_b)
                and float(current_val) > float(current_b)
            )
        if condition == AC.CROSSES_BELOW:
            return (
                prev_val is not None
                and prev_b is not None
                and float(prev_val) >= float(prev_b)
                and float(current_val) < float(current_b)
            )
    return False


async def _get_recent_bars(db, instrument_id, timeframe, limit=300):
    return (
        (
            await db.execute(
                select(OHLCVBar)
                .where(OHLCVBar.instrument_id == instrument_id, OHLCVBar.timeframe == timeframe)
                .order_by(OHLCVBar.ts.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()[::-1]
    )


async def _fire_price_alert(db, alert, current_price):
    now = datetime.now(UTC)
    alert.triggered_at = now
    alert.trigger_count = (alert.trigger_count or 0) + 1
    alert.last_known_price = Decimal(str(current_price))
    alert.status = AlertStatus.ACTIVE if alert.repeat else AlertStatus.TRIGGERED

    notif_id = await send_alert_notification(
        symbol=alert.instrument.symbol,
        condition=alert.condition.value,
        threshold=float(alert.threshold_price),
        current_price=current_price,
        alert_id=alert.id,
    )
    if notif_id:
        alert.last_notification_id = notif_id
    await db.commit()

    await ws_manager.broadcast(
        {
            "type": "alert_triggered",
            "kind": "price",
            "alert_id": alert.id,
            "user_id": alert.user_id,
            "symbol": alert.instrument.symbol,
            "condition": alert.condition.value,
            "threshold": float(alert.threshold_price),
            "current_price": current_price,
            "triggered_at": now.isoformat(),
        }
    )


async def _fire_indicator_alert(db, alert, current_val, current_b=None):
    now = datetime.now(UTC)
    alert.triggered_at = now
    alert.trigger_count = (alert.trigger_count or 0) + 1
    alert.status = AlertStatus.ACTIVE if alert.repeat else AlertStatus.TRIGGERED

    symbol = alert.instrument.symbol
    notif_id = await send_alert_notification(
        symbol=symbol,
        condition=alert.condition.value,
        threshold=float(alert.threshold_value or current_b or 0),
        current_price=current_val,
        alert_id=alert.id,
    )
    if notif_id:
        alert.last_notification_id = notif_id
    await db.commit()

    await ws_manager.broadcast(
        {
            "type": "alert_triggered",
            "kind": "indicator",
            "alert_id": alert.id,
            "user_id": alert.user_id,
            "symbol": symbol,
            "indicator": alert.indicator_type,
            "condition": alert.condition.value,
            "current_value": current_val,
            "triggered_at": now.isoformat(),
        }
    )


async def check_all_alerts(ctx: dict) -> dict:
    """Main alert evaluation task — called by APScheduler every N seconds."""
    price_fired = 0
    indicator_fired = 0

    async with AsyncSessionLocal() as db:
        try:
            # ── Price alerts ──────────────────────────────────────────────────────
            price_alerts = (
                (
                    await db.execute(
                        select(PriceAlert).where(PriceAlert.status == AlertStatus.ACTIVE)
                    )
                )
                .scalars()
                .all()
            )

            by_instrument: dict[int, list] = {}
            for a in price_alerts:
                by_instrument.setdefault(a.instrument_id, []).append(a)

            for iid, alerts in by_instrument.items():
                instrument = await db.get(Instrument, iid)
                if instrument is None:
                    continue
                await db.refresh(instrument, ["listings", "provider_symbols"])
                try:
                    price = await get_current_price_async(db, instrument)
                except Exception as exc:
                    logger.debug("Latest price unavailable for %s: %s", instrument.symbol, exc)
                    continue
                if price is None:
                    continue

                for alert in alerts:
                    if _price_condition_met(
                        alert.condition,
                        alert.threshold_price,
                        alert.last_known_price,
                        Decimal(str(price)),
                    ):
                        await _fire_price_alert(db, alert, price)
                        price_fired += 1
                    else:
                        alert.last_known_price = Decimal(str(price))
                await db.commit()

            # ── Indicator alerts ──────────────────────────────────────────────────
            ind_alerts = (
                (
                    await db.execute(
                        select(IndicatorAlert).where(IndicatorAlert.status == AlertStatus.ACTIVE)
                    )
                )
                .scalars()
                .all()
            )

            for alert in ind_alerts:
                bars = await _get_recent_bars(db, alert.instrument_id, alert.timeframe)
                if not bars:
                    continue

                current_val = ind_engine.get_last_value(
                    alert.indicator_type, bars, alert.indicator_params or {}
                )
                if current_val is None:
                    continue

                current_b = None
                prev_b = None
                if alert.compare_indicator_type:
                    current_b = ind_engine.get_last_value(
                        alert.compare_indicator_type, bars, alert.compare_indicator_params or {}
                    )
                    prev_b = (
                        ind_engine.get_last_value(
                            alert.compare_indicator_type,
                            bars[:-1],
                            alert.compare_indicator_params or {},
                        )
                        if len(bars) > 1
                        else None
                    )

                prev_val = (
                    ind_engine.get_last_value(
                        alert.indicator_type, bars[:-1], alert.indicator_params or {}
                    )
                    if len(bars) > 1
                    else None
                )

                if _indicator_condition_met(
                    alert.condition, current_val, prev_val, alert.threshold_value, current_b, prev_b
                ):
                    await _fire_indicator_alert(db, alert, current_val, current_b)
                    indicator_fired += 1
                else:
                    alert.last_indicator_value = Decimal(str(current_val))
                    if current_b is not None:
                        alert.last_compare_value = Decimal(str(current_b))
            await db.commit()

        except Exception as e:
            logger.error(f"Alert check failed: {e}", exc_info=True)
            await db.rollback()

    return {"price_fired": price_fired, "indicator_fired": indicator_fired}
