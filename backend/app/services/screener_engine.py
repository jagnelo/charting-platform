"""
Screener evaluation engine.

Takes a ScreenerDefinition and evaluates its condition tree against
every instrument in the defined universe, returning matching instruments
and their computed indicator values at evaluation time.

Indicator results are cached in the `indicator_cache` table so subsequent
runs only need to compute bars added since the last cache entry.
"""

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.indicator_cache import IndicatorCache
from app.models.instrument import EquityDetail, Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.screener import ScreenerDefinition, ScreenerResult
from app.models.screener_alert import ScreenerAlert
from app.models.watchlist import Watchlist, WatchlistItem
from app.services.indicators import OHLCVSeries, compute_indicator

GRACE_PERIOD_DAYS = 7

# Global semaphore: caps concurrent yfinance fetches during screener Pass 2.
_FETCH_SEMAPHORE = asyncio.Semaphore(3)

logger = logging.getLogger(__name__)

SCREENER_LOOKBACK_BARS = 300


# ── Helpers ───────────────────────────────────────────────────────────────────


def _params_hash(indicator_type: str, params: dict) -> str:
    canonical = json.dumps({"type": indicator_type, "params": params}, sort_keys=True)
    return hashlib.md5(canonical.encode()).hexdigest()


async def _load_bars(db: AsyncSession, instrument_id: int, timeframe: Timeframe) -> OHLCVSeries:
    stmt = (
        select(OHLCVBar)
        .where(OHLCVBar.instrument_id == instrument_id, OHLCVBar.timeframe == timeframe)
        .order_by(OHLCVBar.ts.desc())
        .limit(SCREENER_LOOKBACK_BARS)
    )
    bars = list((await db.execute(stmt)).scalars().all())
    bars.reverse()
    return OHLCVSeries.from_orm_bars(bars)


async def _get_cached_indicator(
    db: AsyncSession,
    instrument_id: int,
    timeframe: Timeframe,
    indicator_type: str,
    params: dict,
) -> dict[str, list] | None:
    """Return cached series dict {key: [float|None, ...]} or None if no valid cache."""
    phash = _params_hash(indicator_type, params)
    result = await db.execute(
        select(IndicatorCache).where(
            IndicatorCache.instrument_id == instrument_id,
            IndicatorCache.timeframe == timeframe.value,
            IndicatorCache.indicator_type == indicator_type,
            IndicatorCache.params_hash == phash,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        return None
    # Check if cache is still fresh: is last_ts within 2 bar periods of now?
    # If not, caller should recompute (the fresh bars will be appended).
    return json.loads(entry.series_json)


async def _save_indicator_cache(
    db: AsyncSession,
    instrument_id: int,
    timeframe: Timeframe,
    indicator_type: str,
    params: dict,
    series: dict[str, list],
    last_ts: datetime | None,
) -> None:
    phash = _params_hash(indicator_type, params)
    await db.execute(
        pg_insert(IndicatorCache)
        .values(
            instrument_id=instrument_id,
            timeframe=timeframe.value,
            indicator_type=indicator_type,
            params_hash=phash,
            params_json=json.dumps(params, sort_keys=True),
            computed_at=datetime.now(UTC),
            last_ts=last_ts,
            series_json=json.dumps(series),
        )
        .on_conflict_do_update(
            constraint="uq_indicator_cache_key",
            set_={
                "computed_at": datetime.now(UTC),
                "last_ts": last_ts,
                "series_json": json.dumps(series),
            },
        )
    )


def _series_to_cacheable(result: dict[str, np.ndarray]) -> dict[str, list]:
    """Convert numpy arrays to JSON-serialisable lists (NaN → None)."""
    out = {}
    for key, arr in result.items():
        out[key] = [None if np.isnan(v) else float(v) for v in arr]
    return out


async def _compute_indicator_cached(
    db: AsyncSession,
    instrument_id: int,
    timeframe: Timeframe,
    indicator_type: str,
    params: dict,
    data: OHLCVSeries,
) -> dict[str, np.ndarray]:
    """Compute an indicator, using the DB cache when available."""
    cached = await _get_cached_indicator(db, instrument_id, timeframe, indicator_type, params)
    if cached is not None:
        # Reconstruct numpy arrays from cache
        return {
            k: np.array([np.nan if v is None else v for v in vals], dtype=np.float64)
            for k, vals in cached.items()
        }

    # Cache miss — compute fresh
    result = compute_indicator(indicator_type, data, params)
    last_ts = (
        datetime.fromtimestamp(int(data.timestamps[-1]), tz=UTC)
        if len(data.timestamps) > 0
        else None
    )
    cacheable = _series_to_cacheable(result)
    try:
        await _save_indicator_cache(
            db, instrument_id, timeframe, indicator_type, params, cacheable, last_ts
        )
    except Exception as e:
        logger.warning(f"Failed to save indicator cache for {instrument_id}: {e}")

    return result


# ── Universe loading ──────────────────────────────────────────────────────────


async def _get_universe(db: AsyncSession, screener: ScreenerDefinition) -> list[int]:
    if screener.universe_type == "custom" and screener.universe_instrument_ids:
        return screener.universe_instrument_ids

    if screener.universe_type == "watchlist" and screener.universe_watchlist_id:
        wl = await db.get(Watchlist, screener.universe_watchlist_id)
        if wl:
            items_result = await db.execute(
                select(WatchlistItem.instrument_id).where(WatchlistItem.watchlist_id == wl.id)
            )
            return list(items_result.scalars().all())

    if screener.universe_type == "asset_class" and screener.universe_asset_class_id:
        from app.models.asset_class import InstrumentType

        stmt = (
            select(Instrument.id)
            .join(InstrumentType)
            .where(
                InstrumentType.asset_class_id == screener.universe_asset_class_id,
                Instrument.is_active.is_(True),
                Instrument.is_synthetic.is_(False),
            )
        )
        return list((await db.execute(stmt)).scalars().all())

    stmt = select(Instrument.id).where(
        Instrument.is_active.is_(True),
        Instrument.is_synthetic.is_(False),  # synthetics are excluded from screeners
    )
    return list((await db.execute(stmt)).scalars().all())


# ── Calendar-aware price-change period lookback ───────────────────────────────


def _period_start(period: str) -> datetime:
    """Return the UTC start datetime for a named price-change period."""
    now = datetime.now(UTC)
    today = now.date()
    if period == "1D":
        return datetime(today.year, today.month, today.day, tzinfo=UTC) - timedelta(days=1)
    if period == "1W":
        return now - timedelta(weeks=1)
    if period == "1M":
        month = today.month - 1 or 12
        year = today.year - (1 if today.month == 1 else 0)
        d = date(year, month, min(today.day, 28))
        return datetime(d.year, d.month, d.day, tzinfo=UTC)
    if period == "3M":
        month = today.month - 3
        year = today.year
        if month <= 0:
            month += 12
            year -= 1
        d = date(year, month, min(today.day, 28))
        return datetime(d.year, d.month, d.day, tzinfo=UTC)
    if period == "6M":
        month = today.month - 6
        year = today.year
        if month <= 0:
            month += 12
            year -= 1
        d = date(year, month, min(today.day, 28))
        return datetime(d.year, d.month, d.day, tzinfo=UTC)
    if period == "MTD":
        return datetime(today.year, today.month, 1, tzinfo=UTC)
    if period == "QTD":
        # Start of current quarter: Q1=Jan, Q2=Apr, Q3=Jul, Q4=Oct
        q_start_month = ((today.month - 1) // 3) * 3 + 1
        return datetime(today.year, q_start_month, 1, tzinfo=UTC)
    if period == "YTD":
        return datetime(today.year, 1, 1, tzinfo=UTC)
    if period == "1Y":
        return datetime(today.year - 1, today.month, today.day, tzinfo=UTC)
    # Fallback: 1 day
    return now - timedelta(days=1)


# ── Condition evaluator ───────────────────────────────────────────────────────


async def _evaluate_condition(
    condition: dict,
    data: OHLCVSeries,
    instrument: Instrument,
    timeframe: Timeframe,
    db: AsyncSession,
) -> tuple[bool, dict]:
    """
    Recursively evaluate a condition node against a single instrument's data.
    Returns (matched: bool, computed_values: dict).
    """
    computed: dict[str, float] = {}

    ctype = condition.get("type")

    # ── Logical groups ───────────────────────────────────────────────────────
    if "operator" in condition and "conditions" in condition:
        op = condition["operator"].upper()
        sub_conditions = condition["conditions"]
        sub_results = [
            await _evaluate_condition(c, data, instrument, timeframe, db) for c in sub_conditions
        ]
        all_computed: dict = {}
        for _, vals in sub_results:
            all_computed.update(vals)
        booleans = [r for r, _ in sub_results]
        if op == "AND":
            return all(booleans), all_computed
        if op == "OR":
            return any(booleans), all_computed
        if op == "NOT":
            return not booleans[0], all_computed
        return False, all_computed

    # ── Fundamental filter ───────────────────────────────────────────────────
    if ctype == "fundamental_filter":
        field = condition.get("field")
        op = condition.get("op", "eq")
        value = condition.get("value")

        eq: EquityDetail | None = instrument.equity_detail
        if eq is None:
            return False, computed

        actual = getattr(eq, field, None) if field else None
        if actual is None:
            return False, computed

        computed[f"fundamental_{field}"] = actual

        # String comparison (sector, industry, country, exchange_mic)
        if isinstance(actual, str):
            if op == "eq":
                return actual.lower() == str(value).lower(), computed
            if op == "contains":
                return str(value).lower() in actual.lower(), computed
            return False, computed

        # Numeric comparison (market_cap, employees)
        try:
            numeric = float(actual)
            threshold = float(value)
            return _compare(numeric, op, threshold), computed
        except (TypeError, ValueError):
            return False, computed

    # ── Indicator vs fixed threshold ─────────────────────────────────────────
    if ctype == "indicator_threshold":
        ind_type = condition["indicator"]
        ind_params = condition.get("params", {})
        op = condition["op"]
        threshold = float(condition["value"])

        result = await _compute_indicator_cached(
            db, instrument.id, timeframe, ind_type, ind_params, data
        )
        key = list(result.keys())[0]
        series = result[key]
        val = None
        for v in reversed(series):
            if not np.isnan(v):
                val = float(v)
                break
        computed[f"{ind_type}_{key}"] = val
        if val is None:
            return False, computed
        return _compare(val, op, threshold), computed

    # ── Indicator vs indicator ───────────────────────────────────────────────
    if ctype == "indicator_cross":
        a = condition["indicator_a"]
        b = condition["indicator_b"]
        op = condition["op"]

        res_a = await _compute_indicator_cached(
            db, instrument.id, timeframe, a["type"], a.get("params", {}), data
        )
        res_b = await _compute_indicator_cached(
            db, instrument.id, timeframe, b["type"], b.get("params", {}), data
        )
        key_a = list(res_a.keys())[0]
        key_b = list(res_b.keys())[0]
        arr_a = res_a[key_a]
        arr_b = res_b[key_b]

        n = min(len(arr_a), len(arr_b))
        if n < 2:
            return False, computed

        cur_a, cur_b = arr_a[n - 1], arr_b[n - 1]
        prev_a, prev_b = arr_a[n - 2], arr_b[n - 2]
        computed[f"{a['type']}_latest"] = float(cur_a) if not np.isnan(cur_a) else None
        computed[f"{b['type']}_latest"] = float(cur_b) if not np.isnan(cur_b) else None

        if any(np.isnan(v) for v in [cur_a, cur_b, prev_a, prev_b]):
            return False, computed

        if op == "crosses_above":
            return (prev_a <= prev_b) and (cur_a > cur_b), computed
        if op == "crosses_below":
            return (prev_a >= prev_b) and (cur_a < cur_b), computed
        if op == "gt":
            return cur_a > cur_b, computed
        if op == "lt":
            return cur_a < cur_b, computed

    # ── Price threshold ──────────────────────────────────────────────────────
    if ctype == "price_threshold":
        field = condition.get("field", "close")
        op = condition["op"]
        value = float(condition["value"])

        field_map = {
            "open": data.opens,
            "high": data.highs,
            "low": data.lows,
            "close": data.closes,
            "volume": data.volumes,
        }
        arr = field_map.get(field, data.closes)
        if len(arr) == 0:
            return False, computed
        val = float(arr[-1])
        computed[field] = val
        return _compare(val, op, value), computed

    # ── Price % change over named calendar period ────────────────────────────
    if ctype == "price_change_period":
        period = condition.get("period", "1D")
        op = condition["op"]
        value = float(condition["value"])

        if len(data.closes) < 2 or len(data.timestamps) < 2:
            return False, computed

        period_start_ts = _period_start(period).timestamp()
        # Find the first bar at or after the period start
        ref_idx = None
        for i, ts in enumerate(data.timestamps):
            if ts >= period_start_ts:
                ref_idx = i
                break
        if ref_idx is None or ref_idx == len(data.closes) - 1:
            return False, computed

        ref = float(data.closes[ref_idx])
        cur = float(data.closes[-1])
        change = (cur - ref) / ref if ref != 0 else 0.0
        computed["price_change"] = change
        return _compare(change, op, value), computed

    # ── Price % change over N bars (legacy) ──────────────────────────────────
    if ctype == "price_change":
        lookback = int(condition.get("lookback_bars", 1))
        op = condition["op"]
        value = float(condition["value"])

        if len(data.closes) < lookback + 1:
            return False, computed
        ref = data.closes[-(lookback + 1)]
        cur = data.closes[-1]
        change = (cur - ref) / ref if ref != 0 else 0
        computed["price_change"] = change
        return _compare(change, op, value), computed

    # ── Performance over calendar period (always uses D1 bars) ───────────────
    if ctype == "performance":
        period = condition.get("period", "1D")
        op = condition["op"]
        value = float(condition["value"])

        # Load D1 bars if we're not already on D1
        if timeframe == Timeframe.D1:
            d1_data = data
        else:
            d1_data = await _load_bars(db, instrument.id, Timeframe.D1)

        if len(d1_data.closes) < 2 or len(d1_data.timestamps) < 2:
            return False, computed

        period_start_ts = _period_start(period).timestamp()
        ref_idx = None
        for i, ts in enumerate(d1_data.timestamps):
            if ts >= period_start_ts:
                ref_idx = i
                break
        if ref_idx is None or ref_idx == len(d1_data.closes) - 1:
            return False, computed

        ref = float(d1_data.closes[ref_idx])
        cur = float(d1_data.closes[-1])
        change = (cur - ref) / ref if ref != 0 else 0.0
        computed["performance"] = change
        return _compare(change, op, value), computed

    # ── 52-week new high / new low (uses W1 bars regardless of screener TF) ──
    if ctype in ("week52_new_high", "week52_new_low"):
        if timeframe == Timeframe.W1:
            w1_data = data
        else:
            w1_data = await _load_bars(db, instrument.id, Timeframe.W1)

        if len(w1_data.closes) < 2:
            return False, computed

        closes_52 = w1_data.closes[-52:] if len(w1_data.closes) >= 52 else w1_data.closes
        cur = float(w1_data.closes[-1])

        if ctype == "week52_new_high":
            high_52 = float(np.max(closes_52[:-1])) if len(closes_52) > 1 else cur
            result_val = 1.0 if cur >= high_52 else 0.0
            computed["week52_new_high"] = result_val
            return cur >= high_52, computed
        else:
            low_52 = float(np.min(closes_52[:-1])) if len(closes_52) > 1 else cur
            result_val = 1.0 if cur <= low_52 else 0.0
            computed["week52_new_low"] = result_val
            return cur <= low_52, computed

    # ── % distance from 52-week high / low ───────────────────────────────────
    if ctype in ("pct_from_52w_high", "pct_from_52w_low"):
        op = condition["op"]
        value = float(condition["value"])

        if timeframe == Timeframe.W1:
            w1_data = data
        else:
            w1_data = await _load_bars(db, instrument.id, Timeframe.W1)

        if len(w1_data.closes) < 2:
            return False, computed

        closes_52 = w1_data.closes[-52:] if len(w1_data.closes) >= 52 else w1_data.closes
        cur = float(w1_data.closes[-1])

        if ctype == "pct_from_52w_high":
            high_52 = float(np.max(closes_52))
            pct = (high_52 - cur) / high_52 if high_52 != 0 else 0.0
            computed["pct_from_52w_high"] = pct
            return _compare(pct, op, value), computed
        else:
            low_52 = float(np.min(closes_52))
            pct = (cur - low_52) / low_52 if low_52 != 0 else 0.0
            computed["pct_from_52w_low"] = pct
            return _compare(pct, op, value), computed

    # ── Stats filter (market_cap, pe_ratio, beta, avg_volume_30d, etc.) ──────
    if ctype == "stats_filter":
        field = condition.get("field")
        op = condition.get("op", "gt")
        value = condition.get("value")

        stats = instrument.stats
        if stats is None or field is None:
            return False, computed

        actual = getattr(stats, field, None)
        if actual is None:
            return False, computed

        try:
            numeric = float(actual)
            threshold = float(value)
            computed[f"stats_{field}"] = numeric
            return _compare(numeric, op, threshold), computed
        except (TypeError, ValueError):
            return False, computed

    logger.warning(f"Unknown screener condition type: {ctype}")
    return False, computed


def _compare(val: float, op: str, threshold: float) -> bool:
    ops = {
        "gt": val > threshold,
        "lt": val < threshold,
        "gte": val >= threshold,
        "lte": val <= threshold,
        "eq": abs(val - threshold) < 1e-9,
    }
    return ops.get(op, False)


# ── Main entry point ──────────────────────────────────────────────────────────


async def run_screener(
    db: AsyncSession,
    screener: ScreenerDefinition,
) -> ScreenerResult:
    t_start = time.monotonic()
    run_at = datetime.now(UTC)

    instrument_ids = await _get_universe(db, screener)
    logger.info(f"Screener '{screener.name}' running on {len(instrument_ids)} instruments")

    matched_ids: list[int] = []
    result_data: dict[str, dict] = {}
    error: str | None = None

    try:
        # Bulk-load instruments with equity_detail and stats so filters don't N+1
        instr_result = await db.execute(
            select(Instrument)
            .options(
                selectinload(Instrument.equity_detail),
                selectinload(Instrument.stats),
            )
            .where(Instrument.id.in_(instrument_ids))
        )
        instruments = {i.id: i for i in instr_result.scalars().all()}

        for inst_id in instrument_ids:
            inst = instruments.get(inst_id)
            if inst is None:
                continue
            try:
                data = await _load_bars(db, inst_id, screener.timeframe)
                if len(data.closes) < 2:
                    continue
                matched, computed = await _evaluate_condition(
                    screener.conditions, data, inst, screener.timeframe, db
                )
                if matched:
                    matched_ids.append(inst_id)
                    result_data[str(inst_id)] = {k: v for k, v in computed.items() if v is not None}
            except Exception as e:
                logger.warning(f"Screener error on instrument {inst_id}: {e}")

        # Flush cache writes
        await db.commit()

    except Exception as e:
        error = str(e)
        logger.error(f"Screener '{screener.name}' failed: {e}", exc_info=True)

    duration_ms = int((time.monotonic() - t_start) * 1000)
    logger.info(
        f"Screener '{screener.name}' matched {len(matched_ids)}/{len(instrument_ids)} in {duration_ms}ms"
    )

    result = ScreenerResult(
        screener_id=screener.id,
        run_at=run_at,
        duration_ms=duration_ms,
        matched_ids=matched_ids,
        result_data=result_data,
        error=error,
    )
    db.add(result)
    await db.commit()
    await db.refresh(result)

    # Post-run: fire screener alerts and sync managed watchlists
    if not error:
        await process_screener_post_run(db, screener, result)

    return result


# ── Post-run: screener alerts + managed watchlist updates ────────────────────


async def process_screener_post_run(
    db: AsyncSession,
    screener: ScreenerDefinition,
    result: ScreenerResult,
) -> None:
    """
    Called after every successful screener run to:
      1. Diff matched_ids against the previous run and fire ScreenerAlerts.
      2. Sync managed watchlists linked to this screener.

    This is intentionally fire-and-forget and should not raise; errors are
    logged and swallowed so the main screener result is always persisted.
    """
    try:
        await _process_screener_alerts(db, screener, result)
    except Exception as e:
        logger.error("screener alert processing failed for screener %d: %s", screener.id, e)

    try:
        await _sync_managed_watchlists(db, screener, result)
    except Exception as e:
        logger.error("managed watchlist sync failed for screener %d: %s", screener.id, e)


async def _process_screener_alerts(
    db: AsyncSession,
    screener: ScreenerDefinition,
    result: ScreenerResult,
) -> None:
    """Diff current vs previous run and dispatch ScreenerAlert events."""
    # Load all active screener alerts for this screener
    alerts_result = await db.execute(
        select(ScreenerAlert).where(
            ScreenerAlert.screener_id == screener.id,
            ScreenerAlert.status == "active",
        )
    )
    alerts = list(alerts_result.scalars().all())
    if not alerts:
        return

    current_ids = set(result.matched_ids)

    for alert in alerts:
        # Determine previous matched set
        if alert.last_checked_run_id is None:
            prev_ids: set[int] = set()
        else:
            prev_result = await db.get(ScreenerResult, alert.last_checked_run_id)
            prev_ids = set(prev_result.matched_ids) if prev_result else set()

        entered = current_ids - prev_ids
        left = prev_ids - current_ids

        should_fire = (alert.trigger_type in ("entered", "both") and entered) or (
            alert.trigger_type in ("left", "both") and left
        )

        alert.last_checked_run_id = result.id

        if should_fire:
            alert.triggered_at = result.run_at
            if not alert.repeat:
                alert.status = "triggered"

            # Dispatch in-app notification
            _dispatch_screener_alert_event(alert, screener, entered, left)

    await db.commit()


def _dispatch_screener_alert_event(
    alert: ScreenerAlert,
    screener: ScreenerDefinition,
    entered: set[int],
    left: set[int],
) -> None:
    """Publish a screener_alert_triggered event via the WebSocket manager."""
    try:
        import asyncio

        from app.websocket.manager import manager

        payload = {
            "type": "screener_alert_triggered",
            "alert_id": alert.id,
            "screener_id": screener.id,
            "screener_name": screener.name,
            "trigger_type": alert.trigger_type,
            "entered_ids": list(entered),
            "left_ids": list(left),
            "triggered_at": alert.triggered_at.isoformat() if alert.triggered_at else None,
        }
        # manager.broadcast_to_user is a coroutine; schedule it onto the running loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(manager.broadcast_to_user(alert.user_id, payload))
    except Exception as e:
        logger.warning("Failed to dispatch screener alert event: %s", e)


async def _sync_managed_watchlists(
    db: AsyncSession,
    screener: ScreenerDefinition,
    result: ScreenerResult,
) -> None:
    """
    Update managed watchlists linked to this screener:
      - Add instruments that newly entered the screener results.
      - Mark instruments that left as departed (left_screener_at).
      - Remove items whose grace period has expired.
    """
    wl_result = await db.execute(
        select(Watchlist).where(
            Watchlist.screener_id == screener.id,
            Watchlist.is_managed.is_(True),
        )
    )
    watchlists = list(wl_result.scalars().all())
    if not watchlists:
        return

    current_ids = set(result.matched_ids)
    now = result.run_at
    grace_deadline = timedelta(days=GRACE_PERIOD_DAYS)

    for wl in watchlists:
        # Reload items fresh
        items_result = await db.execute(
            select(WatchlistItem).where(WatchlistItem.watchlist_id == wl.id)
        )
        items = list(items_result.scalars().all())
        item_map = {item.instrument_id: item for item in items}
        existing_ids = set(item_map)

        # Add newly matched instruments
        for inst_id in current_ids - existing_ids:
            new_item = WatchlistItem(
                watchlist_id=wl.id,
                instrument_id=inst_id,
                position=0,
                added_at=now,
            )
            db.add(new_item)

        # Handle departed and grace-period expiry
        for inst_id, item in item_map.items():
            if inst_id in current_ids:
                # Back in screener — clear any departed mark
                if item.left_screener_at is not None:
                    item.left_screener_at = None
            else:
                if item.left_screener_at is None:
                    # Just left — mark departure time
                    item.left_screener_at = now
                elif (now - item.left_screener_at) > grace_deadline:
                    # Grace period expired — remove
                    await db.delete(item)

        wl.last_screener_run_at = now

    await db.commit()


# ── Streaming entry point ─────────────────────────────────────────────────────


async def stream_screener(
    db: AsyncSession,
    screener: ScreenerDefinition,
) -> AsyncIterator[dict]:
    """
    Two-pass screener that yields events as results arrive.

    Pass 1 — instruments with OHLCV already in the DB: fast, emits matches
              immediately without any outbound network calls.
    Pass 2 — instruments with no cached OHLCV: fetches from yfinance
              (rate-limited via _FETCH_SEMAPHORE), then evaluates.

    Yielded event shapes:
      {"type": "progress", "evaluated": int, "total": int, "matches": int}
      {"type": "match",    "instrument_id": int, "computed": dict}
      {"type": "done",     "evaluated": int, "total": int, "matches": int,
                           "duration_ms": int, "result_id": int}
    """
    from app.services.market_data import fetch_ohlcv_latest  # avoid circular at module level

    t_start = time.monotonic()
    run_at = datetime.now(UTC)

    instrument_ids = await _get_universe(db, screener)
    total = len(instrument_ids)

    # Bulk-load instruments (with equity_detail and stats) to avoid N+1
    instr_result = await db.execute(
        select(Instrument)
        .options(
            selectinload(Instrument.equity_detail),
            selectinload(Instrument.stats),
        )
        .where(Instrument.id.in_(instrument_ids))
    )
    instruments: dict[int, Instrument] = {i.id: i for i in instr_result.scalars().all()}

    # Single query: which instrument_ids already have ≥2 bars for this timeframe?
    has_data_stmt = (
        select(OHLCVBar.instrument_id)
        .where(
            OHLCVBar.instrument_id.in_(instrument_ids),
            OHLCVBar.timeframe == screener.timeframe,
        )
        .group_by(OHLCVBar.instrument_id)
        .having(func.count(OHLCVBar.id) >= 2)
    )
    has_data_set = set((await db.execute(has_data_stmt)).scalars().all())

    has_data_ids = [iid for iid in instrument_ids if iid in has_data_set]
    needs_fetch_ids = [iid for iid in instrument_ids if iid not in has_data_set]

    evaluated = 0
    matched = 0
    matched_ids: list[int] = []
    result_data: dict[str, dict] = {}

    # ── Pass 1: evaluate instruments with cached OHLCV ────────────────────────
    for inst_id in has_data_ids:
        inst = instruments.get(inst_id)
        if inst is None:
            evaluated += 1
            continue
        try:
            data = await _load_bars(db, inst_id, screener.timeframe)
            if len(data.closes) >= 2:
                ok, computed = await _evaluate_condition(
                    screener.conditions, data, inst, screener.timeframe, db
                )
                if ok:
                    matched += 1
                    matched_ids.append(inst_id)
                    result_data[str(inst_id)] = {k: v for k, v in computed.items() if v is not None}
                    yield {
                        "type": "match",
                        "instrument_id": inst_id,
                        "computed": result_data[str(inst_id)],
                    }
        except Exception as exc:
            logger.warning("Screener Pass 1 error on %d: %s", inst_id, exc)

        evaluated += 1
        if evaluated % 20 == 0:
            yield {"type": "progress", "evaluated": evaluated, "total": total, "matches": matched}

    # Flush indicator cache writes accumulated during Pass 1
    try:
        await db.commit()
    except Exception:
        pass

    yield {"type": "progress", "evaluated": evaluated, "total": total, "matches": matched}

    # ── Pass 2: fetch-then-evaluate instruments with no cached OHLCV ──────────
    for inst_id in needs_fetch_ids:
        inst = instruments.get(inst_id)
        if inst is None:
            evaluated += 1
            yield {"type": "progress", "evaluated": evaluated, "total": total, "matches": matched}
            continue
        try:
            async with _FETCH_SEMAPHORE:
                bars = await fetch_ohlcv_latest(
                    db, inst, screener.timeframe, SCREENER_LOOKBACK_BARS
                )
            if len(bars) >= 2:
                data = OHLCVSeries.from_orm_bars(bars)
                ok, computed = await _evaluate_condition(
                    screener.conditions, data, inst, screener.timeframe, db
                )
                if ok:
                    matched += 1
                    matched_ids.append(inst_id)
                    result_data[str(inst_id)] = {k: v for k, v in computed.items() if v is not None}
                    yield {
                        "type": "match",
                        "instrument_id": inst_id,
                        "computed": result_data[str(inst_id)],
                    }
        except Exception as exc:
            logger.warning("Screener Pass 2 error on %d: %s", inst_id, exc)

        evaluated += 1
        yield {"type": "progress", "evaluated": evaluated, "total": total, "matches": matched}

    # Flush final cache writes from Pass 2
    try:
        await db.commit()
    except Exception:
        pass

    duration_ms = int((time.monotonic() - t_start) * 1000)
    logger.info(
        "Screener '%s' (stream) matched %d/%d in %dms",
        screener.name,
        matched,
        total,
        duration_ms,
    )

    result = ScreenerResult(
        screener_id=screener.id,
        run_at=run_at,
        duration_ms=duration_ms,
        matched_ids=matched_ids,
        result_data=result_data,
        error=None,
    )
    db.add(result)
    await db.commit()
    await db.refresh(result)

    # Post-run: fire screener alerts and sync managed watchlists
    await process_screener_post_run(db, screener, result)

    yield {
        "type": "done",
        "evaluated": evaluated,
        "total": total,
        "matches": matched,
        "duration_ms": duration_ms,
        "result_id": result.id,
    }
