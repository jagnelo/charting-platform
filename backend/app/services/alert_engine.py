"""
Alert engine — evaluates both PriceAlerts and IndicatorAlerts.
Runs as a scheduled job via APScheduler every ALERT_POLL_INTERVAL seconds.
"""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.indicator_alert import IndicatorAlert
from app.models.instrument import Instrument
from app.models.ohlcv import Timeframe
from app.models.price_alert import AlertCondition, AlertStatus, PriceAlert
from app.services.indicators import OHLCVSeries, get_latest_value
from app.services.market_data import _ticker_for_instrument, fetch_ohlcv, get_current_price
from app.services.onesignal import send_alert_notification, send_indicator_alert_notification
from app.websocket.manager import ws_manager

logger = logging.getLogger(__name__)

INDICATOR_LOOKBACK = 300  # bars to load for indicator computation

# Approximate wall-clock duration of one bar per timeframe — used to compute
# the lookback start time for `fetch_ohlcv` so it always has fresh data.
_TF_BAR_DURATION: dict[Timeframe, timedelta] = {
    Timeframe.M1: timedelta(minutes=1),
    Timeframe.M5: timedelta(minutes=5),
    Timeframe.M15: timedelta(minutes=15),
    Timeframe.M30: timedelta(minutes=30),
    Timeframe.H1: timedelta(hours=1),
    Timeframe.H2: timedelta(hours=2),
    Timeframe.H4: timedelta(hours=4),
    Timeframe.H12: timedelta(hours=12),
    Timeframe.D1: timedelta(days=1),
    Timeframe.W1: timedelta(weeks=1),
    Timeframe.MN: timedelta(days=31),
}


# ── Price alert evaluation ────────────────────────────────────────────────────


def _price_condition_met(
    condition, threshold, last_price, current_price, within_percent=None
) -> bool:
    cp = float(current_price)
    tp = float(threshold)
    lp = float(last_price) if last_price is not None else None

    if condition == AlertCondition.TOUCHES:
        return abs(cp - tp) / max(tp, 1e-9) < 0.001
    if condition == AlertCondition.CROSSES_ABOVE:
        return (lp is None and cp > tp) or (lp is not None and lp <= tp < cp)
    if condition == AlertCondition.CROSSES_BELOW:
        return (lp is None and cp < tp) or (lp is not None and lp >= tp > cp)
    if condition in (AlertCondition.PERCENT_CHANGE_UP, AlertCondition.PERCENT_CHANGE_DOWN):
        return cp >= tp if condition == AlertCondition.PERCENT_CHANGE_UP else cp <= tp
    if condition == AlertCondition.WITHIN_PERCENT:
        if tp == 0 or within_percent is None:
            return False
        return abs((cp - tp) / tp) * 100 <= float(within_percent)
    return False


# ── Indicator alert evaluation ────────────────────────────────────────────────


def _indicator_condition_met(
    condition: str,
    val_a: float,
    last_val_a: float | None,
    threshold: float | None,
    val_b: float | None,
    last_val_b: float | None,
) -> bool:
    if condition == "gt":
        return val_a > (threshold if threshold is not None else val_b)
    if condition == "lt":
        return val_a < (threshold if threshold is not None else val_b)
    if condition == "gte":
        return val_a >= (threshold if threshold is not None else val_b)
    if condition == "lte":
        return val_a <= (threshold if threshold is not None else val_b)
    if condition == "crosses_above":
        if last_val_a is None:
            return False
        ref_prev = threshold if threshold is not None else last_val_b
        ref_cur = threshold if threshold is not None else val_b
        if ref_prev is None or ref_cur is None:
            return False
        return last_val_a <= ref_prev and val_a > ref_cur
    if condition == "crosses_below":
        if last_val_a is None:
            return False
        ref_prev = threshold if threshold is not None else last_val_b
        ref_cur = threshold if threshold is not None else val_b
        if ref_prev is None or ref_cur is None:
            return False
        return last_val_a >= ref_prev and val_a < ref_cur
    return False


async def _load_ohlcv_series(
    db: AsyncSession, instrument: Instrument, timeframe: Timeframe
) -> OHLCVSeries:
    """Fetch (and refresh if stale) the OHLCV series used for indicator evaluation."""
    bar_dur = _TF_BAR_DURATION.get(timeframe, timedelta(days=1))
    # Request enough history for the lookback window with a small buffer
    start = datetime.now(UTC) - bar_dur * INDICATOR_LOOKBACK * 2
    bars = await fetch_ohlcv(db, instrument, timeframe, start)
    bars = bars[-INDICATOR_LOOKBACK:] if len(bars) > INDICATOR_LOOKBACK else bars
    return OHLCVSeries.from_orm_bars(bars)


async def _fire_price_alert(db: AsyncSession, alert: PriceAlert, current_price: float):
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
            "alert_kind": "price",
            "alert_id": alert.id,
            "symbol": alert.instrument.symbol,
            "condition": alert.condition.value,
            "threshold": float(alert.threshold_price),
            "current_price": current_price,
            "triggered_at": now.isoformat(),
        }
    )
    logger.info(f"Price alert {alert.id} fired: {alert.instrument.symbol} @ {current_price}")


async def _fire_indicator_alert(
    db: AsyncSession, alert: IndicatorAlert, val_a: float, val_b: float | None
):
    now = datetime.now(UTC)
    alert.triggered_at = now
    alert.trigger_count = (alert.trigger_count or 0) + 1
    alert.last_value_a = Decimal(str(val_a))
    if val_b is not None:
        alert.last_value_b = Decimal(str(val_b))
    alert.status = AlertStatus.ACTIVE if alert.repeat else AlertStatus.TRIGGERED

    notif_id = await send_indicator_alert_notification(
        symbol=alert.instrument.symbol,
        indicator_type=alert.indicator_a_type,
        condition=alert.condition,
        value=val_a,
        threshold=float(alert.threshold_value) if alert.threshold_value else val_b,
        alert_id=alert.id,
    )
    if notif_id:
        alert.last_notification_id = notif_id

    await db.commit()
    await ws_manager.broadcast(
        {
            "type": "alert_triggered",
            "alert_kind": "indicator",
            "alert_id": alert.id,
            "symbol": alert.instrument.symbol,
            "indicator": alert.indicator_a_type,
            "condition": alert.condition,
            "value_a": val_a,
            "value_b": val_b,
            "triggered_at": now.isoformat(),
        }
    )
    logger.info(
        f"Indicator alert {alert.id} fired: {alert.instrument.symbol} {alert.indicator_a_type}={val_a:.4f}"
    )


async def run_alert_check():
    async with AsyncSessionLocal() as db:
        # ── Price alerts ──────────────────────────────────────────────────────
        price_alerts = list(
            (await db.execute(select(PriceAlert).where(PriceAlert.status == AlertStatus.ACTIVE)))
            .scalars()
            .all()
        )

        # Group by instrument to minimise API calls
        by_instrument: dict[int, list] = {}
        for a in price_alerts:
            by_instrument.setdefault(a.instrument_id, []).append(a)

        for inst_id, alerts in by_instrument.items():
            instrument = await db.get(Instrument, inst_id)
            if not instrument:
                continue
            await db.refresh(instrument, ["listings"])
            ticker = _ticker_for_instrument(instrument)
            current_price = get_current_price(ticker)
            if current_price is None:
                continue
            current_dec = Decimal(str(current_price))
            for alert in alerts:
                await db.refresh(alert, ["instrument"])
                if _price_condition_met(
                    alert.condition,
                    alert.threshold_price,
                    alert.last_known_price,
                    current_dec,
                    alert.within_percent,
                ):
                    await _fire_price_alert(db, alert, current_price)
                else:
                    alert.last_known_price = current_dec
            await db.commit()

        # ── Indicator alerts ──────────────────────────────────────────────────
        ind_alerts = list(
            (
                await db.execute(
                    select(IndicatorAlert).where(IndicatorAlert.status == AlertStatus.ACTIVE)
                )
            )
            .scalars()
            .all()
        )

        for alert in ind_alerts:
            try:
                await db.refresh(alert, ["instrument"])
                data = await _load_ohlcv_series(db, alert.instrument, alert.timeframe)
                if len(data.closes) < 2:
                    continue

                val_a = get_latest_value(alert.indicator_a_type, data, alert.indicator_a_params)
                if val_a is None:
                    continue

                val_b = None
                if alert.indicator_b_type:
                    val_b = get_latest_value(
                        alert.indicator_b_type, data, alert.indicator_b_params or {}
                    )

                threshold = (
                    float(alert.threshold_value) if alert.threshold_value is not None else None
                )
                last_a = float(alert.last_value_a) if alert.last_value_a is not None else None
                last_b = float(alert.last_value_b) if alert.last_value_b is not None else None

                if _indicator_condition_met(
                    alert.condition, val_a, last_a, threshold, val_b, last_b
                ):
                    await _fire_indicator_alert(db, alert, val_a, val_b)

                # Always persist latest values for display in UI
                alert.last_value_a = Decimal(str(val_a))
                if val_b is not None:
                    alert.last_value_b = Decimal(str(val_b))

            except Exception as e:
                logger.error(f"Indicator alert {alert.id} evaluation failed: {e}")

        await db.commit()
