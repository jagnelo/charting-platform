"""
Screener evaluation engine.

Takes a ScreenerDefinition and evaluates its condition tree against
every instrument in the defined universe, returning matching instruments
and their computed indicator values at evaluation time.
"""

import logging
import time
from datetime import UTC, datetime

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.screener import ScreenerDefinition, ScreenerResult
from app.models.watchlist import Watchlist
from app.services.indicators import OHLCVSeries, compute_indicator

logger = logging.getLogger(__name__)

# Number of bars to load per instrument for screening
SCREENER_LOOKBACK_BARS = 300


async def _load_bars(db: AsyncSession, instrument_id: int, timeframe: Timeframe) -> OHLCVSeries:
    stmt = (
        select(OHLCVBar)
        .where(OHLCVBar.instrument_id == instrument_id, OHLCVBar.timeframe == timeframe)
        .order_by(OHLCVBar.ts.desc())
        .limit(SCREENER_LOOKBACK_BARS)
    )
    bars = list((await db.execute(stmt)).scalars().all())
    bars.reverse()  # chronological order
    return OHLCVSeries.from_orm_bars(bars)


async def _get_universe(db: AsyncSession, screener: ScreenerDefinition) -> list[int]:
    """Return list of instrument_ids for the screener's universe."""
    if screener.universe_type == "custom" and screener.universe_instrument_ids:
        return screener.universe_instrument_ids

    if screener.universe_type == "watchlist" and screener.universe_watchlist_id:
        wl = await db.get(Watchlist, screener.universe_watchlist_id)
        if wl:
            await db.refresh(wl, ["instruments"])
            return [i.id for i in wl.instruments]

    if screener.universe_type == "asset_class" and screener.universe_asset_class_id:
        from app.models.asset_class import InstrumentType

        stmt = (
            select(Instrument.id)
            .join(InstrumentType)
            .where(
                InstrumentType.asset_class_id == screener.universe_asset_class_id,
                Instrument.is_active.is_(True),
            )
        )
        return list((await db.execute(stmt)).scalars().all())

    # Default: all active instruments
    stmt = select(Instrument.id).where(Instrument.is_active.is_(True))
    return list((await db.execute(stmt)).scalars().all())


def _evaluate_condition(condition: dict, data: OHLCVSeries) -> tuple[bool, dict]:
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
        sub_results = [_evaluate_condition(c, data) for c in sub_conditions]
        all_computed = {}
        for _, vals in sub_results:
            all_computed.update(vals)
        booleans = [r for r, _ in sub_results]

        if op == "AND":
            return all(booleans), all_computed
        elif op == "OR":
            return any(booleans), all_computed
        elif op == "NOT":
            return not booleans[0], all_computed
        return False, all_computed

    # ── Indicator vs fixed threshold ─────────────────────────────────────────
    if ctype == "indicator_threshold":
        ind_type = condition["indicator"]
        ind_params = condition.get("params", {})
        op = condition["op"]
        threshold = float(condition["value"])

        result = compute_indicator(ind_type, data, ind_params)
        key = list(result.keys())[0]
        series = result[key]
        # Get most recent non-NaN
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

        res_a = compute_indicator(a["type"], data, a.get("params", {}))
        res_b = compute_indicator(b["type"], data, b.get("params", {}))
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

    # ── Price percentage change over N bars ──────────────────────────────────
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


async def run_screener(
    db: AsyncSession,
    screener: ScreenerDefinition,
) -> ScreenerResult:
    """
    Execute a screener and persist the result.
    Returns the ScreenerResult ORM object.
    """
    t_start = time.monotonic()
    run_at = datetime.now(UTC)

    instrument_ids = await _get_universe(db, screener)
    logger.info(f"Screener '{screener.name}' running on {len(instrument_ids)} instruments")

    matched_ids: list[int] = []
    result_data: dict[str, dict] = {}
    error: str | None = None

    try:
        for inst_id in instrument_ids:
            try:
                data = await _load_bars(db, inst_id, screener.timeframe)
                if len(data.closes) < 2:
                    continue
                matched, computed = _evaluate_condition(screener.conditions, data)
                if matched:
                    matched_ids.append(inst_id)
                    result_data[str(inst_id)] = {k: v for k, v in computed.items() if v is not None}
            except Exception as e:
                logger.warning(f"Screener error on instrument {inst_id}: {e}")

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
    return result
