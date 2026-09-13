"""
Alert engine — evaluates both PriceAlerts and IndicatorAlerts.
Runs as a scheduled job via APScheduler every ALERT_POLL_INTERVAL seconds.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.alert_firing_event import AlertFiringEvent
from app.models.indicator_alert import IndicatorAlert
from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.price_alert import AlertCondition, AlertStatus, PriceAlert
from app.providers.errors import bounded_redact_provider_message
from app.services.evaluator_preflight import preflight_ohlcv
from app.services.indicators import OHLCVSeries, get_latest_value, required_bars_for_indicator
from app.services.market_data import fetch_ohlcv, get_current_price_async
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
) -> tuple[OHLCVSeries, list[OHLCVBar]]:
    """Fetch (and refresh if stale) the OHLCV series used for indicator evaluation."""
    bar_dur = _TF_BAR_DURATION.get(timeframe, timedelta(days=1))
    # Request enough history for the lookback window with a small buffer
    start = datetime.now(UTC) - bar_dur * INDICATOR_LOOKBACK * 2
    bars = await fetch_ohlcv(db, instrument, timeframe, start)
    bars = bars[-INDICATOR_LOOKBACK:] if len(bars) > INDICATOR_LOOKBACK else bars
    return OHLCVSeries.from_orm_bars(bars), bars


async def _preflight_price_alerts(
    db: AsyncSession,
    alerts_by_instrument: dict[int, list[PriceAlert]],
) -> dict[int, float | None]:
    """Acquire each high-alert instrument price once before evaluation.

    Price alerts are an intentionally narrow, high-alert workload, so they may
    poll the latest-price capability.  The polling belongs to this preflight
    phase rather than the per-alert evaluation loop: every alert for an
    instrument evaluates against the same provider observation and a provider
    failure cannot cause a second request for the next alert.
    """

    prices: dict[int, float | None] = {}
    for instrument_id in sorted(alerts_by_instrument):
        instrument = await db.get(Instrument, instrument_id)
        if instrument is None:
            prices[instrument_id] = None
            continue
        await db.refresh(instrument, ["listings", "provider_symbols"])
        try:
            prices[instrument_id] = await get_current_price_async(db, instrument)
        except Exception as exc:  # noqa: BLE001 - retain per-instrument preflight failure.
            logger.debug(
                "Latest price unavailable for %s: %s",
                instrument.symbol,
                bounded_redact_provider_message(exc),
            )
            prices[instrument_id] = None
    return prices


async def _preflight_indicator_alerts(
    db: AsyncSession,
    alerts: list[IndicatorAlert],
) -> dict[tuple[int, Timeframe], OHLCVSeries | None]:
    """Refresh one OHLCV series per instrument/timeframe before evaluation.

    Multiple indicator alerts commonly share the same underlying series.  A
    grouped preflight prevents each alert from independently discovering stale
    data and spending provider quota.  Missing/failed groups remain ``None``;
    the evaluation phase then skips them rather than evaluating stale data.
    """

    grouped_alerts: dict[tuple[int, Timeframe], list[IndicatorAlert]] = {}
    for alert in alerts:
        grouped_alerts.setdefault((alert.instrument_id, alert.timeframe), []).append(alert)
    prepared: dict[tuple[int, Timeframe], OHLCVSeries | None] = {}
    for instrument_id, timeframe in sorted(
        grouped_alerts, key=lambda item: (item[0], str(item[1]))
    ):
        instrument = await db.get(Instrument, instrument_id)
        key = (instrument_id, timeframe)
        if instrument is None:
            prepared[key] = None
            continue
        await db.refresh(instrument, ["listings", "provider_symbols"])
        try:
            loaded = await _load_ohlcv_series(db, instrument, timeframe)
            # Keep compatibility with narrow test doubles and third-party
            # callers that still return only an OHLCVSeries. Production returns
            # the persisted bars alongside the normalized series.
            if isinstance(loaded, tuple) and len(loaded) == 2:
                series, bars = loaded
            else:
                series, bars = loaded, []
            if bars:
                minimum_bars = max(
                    max(
                        required_bars_for_indicator(
                            alert.indicator_a_type, alert.indicator_a_params
                        )
                        for alert in grouped_alerts[key]
                    ),
                    max(
                        (
                            required_bars_for_indicator(
                                alert.indicator_b_type, alert.indicator_b_params
                            )
                            for alert in grouped_alerts[key]
                            if alert.indicator_b_type
                        ),
                        default=2,
                    ),
                )
                coverage = await preflight_ohlcv(
                    db,
                    evaluator=f"indicator_alert:{instrument_id}:{timeframe.value}",
                    instrument_ids=[instrument_id],
                    timeframe=timeframe,
                    date_from=None,
                    date_to=None,
                    adjusted=True,
                    cached_bars={instrument_id: bars},
                    minimum_bars=minimum_bars,
                )
                if instrument_id not in coverage.ready_instrument_ids:
                    logger.debug(
                        "Indicator alert history deferred for instrument %s (%s): %s",
                        instrument_id,
                        timeframe,
                        coverage.to_dict(),
                    )
                    prepared[key] = None
                    continue
            prepared[key] = series
        except Exception as exc:  # noqa: BLE001 - retain per-group preflight failure.
            logger.debug(
                "Indicator OHLCV unavailable for instrument %s (%s): %s",
                instrument_id,
                timeframe,
                bounded_redact_provider_message(exc),
            )
            prepared[key] = None
    return prepared


async def _fire_price_alert(db: AsyncSession, alert: PriceAlert, current_price: float):
    now = datetime.now(UTC)
    # Capture fields that will be needed after commit (commit expires ORM attributes)
    symbol = alert.instrument.symbol
    condition_val = alert.condition.value
    threshold = float(alert.threshold_price)
    alert_id = alert.id
    user_id = alert.user_id
    instrument_id = alert.instrument_id

    alert.triggered_at = now
    alert.trigger_count = (alert.trigger_count or 0) + 1
    alert.last_known_price = Decimal(str(current_price))
    alert.status = AlertStatus.ACTIVE if alert.repeat else AlertStatus.TRIGGERED

    firing = AlertFiringEvent(
        user_id=user_id,
        instrument_id=instrument_id,
        alert_type="price",
        alert_id=alert_id,
        fired_at=now,
        trigger_value=Decimal(str(current_price)),
        condition_snapshot=json.dumps(
            {"condition": condition_val, "threshold": threshold, "symbol": symbol}
        ),
    )
    db.add(firing)
    await db.flush()
    firing_id = firing.id

    notif_id = await send_alert_notification(
        symbol=symbol,
        condition=condition_val,
        threshold=threshold,
        current_price=current_price,
        alert_id=alert_id,
    )
    if notif_id:
        alert.last_notification_id = notif_id

    await db.commit()
    await ws_manager.broadcast_to_user(
        alert.user_id,
        {
            "type": "alert_triggered",
            "alert_kind": "price",
            "alert_id": alert_id,
            "firing_event_id": firing_id,
            "symbol": symbol,
            "condition": condition_val,
            "threshold": threshold,
            "current_price": current_price,
            "triggered_at": now.isoformat(),
        },
    )
    logger.info(f"Price alert {alert_id} fired: {symbol} @ {current_price}")


async def _fire_indicator_alert(
    db: AsyncSession, alert: IndicatorAlert, val_a: float, val_b: float | None
):
    now = datetime.now(UTC)
    # Capture fields before commit (commit expires ORM attributes, lazy-load fails in async)
    symbol = alert.instrument.symbol
    indicator_type = alert.indicator_a_type
    condition = alert.condition
    alert_id = alert.id
    user_id = alert.user_id
    instrument_id = alert.instrument_id
    threshold_value = float(alert.threshold_value) if alert.threshold_value else val_b

    alert.triggered_at = now
    alert.trigger_count = (alert.trigger_count or 0) + 1
    alert.last_value_a = Decimal(str(val_a))
    if val_b is not None:
        alert.last_value_b = Decimal(str(val_b))
    alert.status = AlertStatus.ACTIVE if alert.repeat else AlertStatus.TRIGGERED

    firing = AlertFiringEvent(
        user_id=user_id,
        instrument_id=instrument_id,
        alert_type="indicator",
        alert_id=alert_id,
        fired_at=now,
        trigger_value=Decimal(str(val_a)),
        condition_snapshot=json.dumps(
            {
                "indicator": indicator_type,
                "condition": condition,
                "value_a": val_a,
                "value_b": val_b,
                "threshold": threshold_value,
                "symbol": symbol,
            }
        ),
    )
    db.add(firing)
    await db.flush()
    firing_id = firing.id

    notif_id = await send_indicator_alert_notification(
        symbol=symbol,
        indicator_type=indicator_type,
        condition=condition,
        value=val_a,
        threshold=threshold_value,
        alert_id=alert_id,
    )
    if notif_id:
        alert.last_notification_id = notif_id

    await db.commit()
    await ws_manager.broadcast_to_user(
        alert.user_id,
        {
            "type": "alert_triggered",
            "alert_kind": "indicator",
            "alert_id": alert_id,
            "firing_event_id": firing_id,
            "symbol": symbol,
            "indicator": indicator_type,
            "condition": condition,
            "value_a": val_a,
            "value_b": val_b,
            "triggered_at": now.isoformat(),
        },
    )
    logger.info(f"Indicator alert {alert_id} fired: {symbol} {indicator_type}={val_a:.4f}")


async def run_alert_check():
    async with AsyncSessionLocal() as db:
        # Load both alert classes first. Provider access is deliberately kept in
        # the grouped preflight below; the evaluation loops only consume these
        # immutable-in-run observations and local indicator values.
        price_alerts = list(
            (await db.execute(select(PriceAlert).where(PriceAlert.status == AlertStatus.ACTIVE)))
            .scalars()
            .all()
        )
        ind_alerts = list(
            (
                await db.execute(
                    select(IndicatorAlert).where(IndicatorAlert.status == AlertStatus.ACTIVE)
                )
            )
            .scalars()
            .all()
        )

        # ── Coverage/latest-price preflight ───────────────────────────────────
        by_instrument: dict[int, list[PriceAlert]] = {}
        for a in price_alerts:
            by_instrument.setdefault(a.instrument_id, []).append(a)
        prices = await _preflight_price_alerts(db, by_instrument)
        indicator_series = await _preflight_indicator_alerts(db, ind_alerts)

        # ── Price alert evaluation (DB/preflight data only) ───────────────────
        for inst_id, alerts in by_instrument.items():
            current_price = prices.get(inst_id)
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

        # ── Indicator alert evaluation (DB/preflight data only) ──────────────
        for alert in ind_alerts:
            try:
                await db.refresh(alert, ["instrument"])
                data = indicator_series.get((alert.instrument_id, alert.timeframe))
                if data is None:
                    continue
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
                logger.error(
                    "Indicator alert %s evaluation failed: %s",
                    alert.id,
                    bounded_redact_provider_message(e),
                )

        await db.commit()
