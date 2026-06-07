import math
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.basket import Basket, BasketMember
from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.radar import (
    RadarDetection,
    RadarOutcomeStatus,
    RadarRun,
    RadarRunStatus,
    RadarSetupThread,
    RadarSetupType,
    RadarState,
)
from app.services.indicators import OHLCVSeries, compute_indicator

RADAR_LOOKBACK_BARS = 320
EMA_PERIODS = (20, 50, 200)
SWING_WINDOW = 3
MIN_ZONE_TOUCHES = 2
MAX_ZONES_PER_SIDE = 3
LINE_SAMPLE_POINTS = 120
THREAD_PRICE_TOLERANCE_FRACTION = 0.008
RECENT_GAP_LOOKBACK = 60
SQUEEZE_LOOKBACK = 120
STALE_BAR_BUDGETS: dict[Timeframe, int] = {
    Timeframe.M30: 72,
    Timeframe.H1: 56,
    Timeframe.H4: 36,
    Timeframe.D1: 20,
    Timeframe.W1: 12,
    Timeframe.MN: 8,
}
STALE_MIN_PROGRESS_RATIO: dict[Timeframe, float] = {
    Timeframe.M30: 0.28,
    Timeframe.H1: 0.26,
    Timeframe.H4: 0.22,
    Timeframe.D1: 0.18,
    Timeframe.W1: 0.14,
    Timeframe.MN: 0.10,
}
STALE_MIN_LIVE_REWARD_RISK: dict[Timeframe, float] = {
    Timeframe.M30: 0.95,
    Timeframe.H1: 1.0,
    Timeframe.H4: 1.0,
    Timeframe.D1: 1.05,
    Timeframe.W1: 1.1,
    Timeframe.MN: 1.15,
}
STALE_ENTRY_DRIFT_ATR: dict[Timeframe, float] = {
    Timeframe.M30: 2.6,
    Timeframe.H1: 2.8,
    Timeframe.H4: 3.1,
    Timeframe.D1: 3.5,
    Timeframe.W1: 4.0,
    Timeframe.MN: 4.5,
}
STALE_LEVEL_FLIP_LIMIT: dict[Timeframe, int] = {
    Timeframe.M30: 7,
    Timeframe.H1: 7,
    Timeframe.H4: 6,
    Timeframe.D1: 5,
    Timeframe.W1: 4,
    Timeframe.MN: 3,
}
STALE_LEVEL_CROSS_LIMIT: dict[Timeframe, int] = {
    Timeframe.M30: 14,
    Timeframe.H1: 12,
    Timeframe.H4: 10,
    Timeframe.D1: 8,
    Timeframe.W1: 6,
    Timeframe.MN: 4,
}
STALE_VOLATILITY_REGIME_RANGE = (0.55, 1.95)

RADAR_SETUP_SEQUENCE_PRIORITY: dict[RadarSetupType, int] = {
    RadarSetupType.APPROACHING_SUPPORT: 0,
    RadarSetupType.APPROACHING_RESISTANCE: 0,
    RadarSetupType.COMPRESSION_SUPPORT: 0,
    RadarSetupType.COMPRESSION_RESISTANCE: 0,
    RadarSetupType.REJECTION: 1,
    RadarSetupType.RECLAIM: 1,
    RadarSetupType.FAKEOUT: 1,
    RadarSetupType.FAKEDOWN: 1,
    RadarSetupType.BREAKOUT: 2,
    RadarSetupType.BREAKDOWN: 2,
    RadarSetupType.FAILED_RECLAIM: 2,
    RadarSetupType.FAILED_BREAKDOWN_RECOVERY: 2,
    RadarSetupType.BREAKOUT_RETEST: 3,
    RadarSetupType.BREAKDOWN_RETEST: 3,
}

LONG_BIASED_SETUPS = {
    RadarSetupType.APPROACHING_SUPPORT,
    RadarSetupType.BREAKOUT,
    RadarSetupType.BREAKOUT_RETEST,
    RadarSetupType.FAKEDOWN,
    RadarSetupType.RECLAIM,
    RadarSetupType.COMPRESSION_SUPPORT,
}

SHORT_BIASED_SETUPS = {
    RadarSetupType.APPROACHING_RESISTANCE,
    RadarSetupType.BREAKDOWN,
    RadarSetupType.BREAKDOWN_RETEST,
    RadarSetupType.FAKEOUT,
    RadarSetupType.FAILED_RECLAIM,
    RadarSetupType.FAILED_BREAKDOWN_RECOVERY,
    RadarSetupType.COMPRESSION_RESISTANCE,
    RadarSetupType.REJECTION,
}


@dataclass
class Pivot:
    index: int
    price: float
    ts: int


@dataclass
class Zone:
    side: str
    center: float
    low: float
    high: float
    touch_count: int
    last_touch_index: int
    first_touch_index: int
    last_touch_ts: int
    pivots: list[Pivot]
    role: str


@dataclass
class DetectionCandidate:
    setup_type: RadarSetupType
    state: RadarState
    state_reason: str
    score: float
    summary: str
    invalidation_hint: str
    key_level_price: float
    entry_price: float
    invalidation_price: float
    target_price: float
    score_factors: dict
    evidence: dict
    observed_at: datetime
    signal_at: datetime
    context_at: datetime | None
    fresh_until: datetime
    context_role: str | None


@dataclass
class SqueezeContext:
    bb_width: float | None
    bb_width_percentile: float
    inside_keltner: bool
    score: float


@dataclass
class Trendline:
    role: str
    start_index: int
    end_index: int
    start_ts: int
    end_ts: int
    start_price: float
    end_price: float
    slope: float


@dataclass
class GapZone:
    role: str
    low: float
    high: float
    start_ts: int
    end_ts: int
    kind: str


@dataclass
class AvwapAnchor:
    anchor_type: str
    ts: int
    reference_price: float
    priority: int


@dataclass
class StaleAssessment:
    is_stale: bool
    stale_at: datetime | None
    reason: str | None
    reason_code: str | None
    metrics: dict


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


async def _load_bars(db: AsyncSession, instrument_id: int, timeframe: Timeframe) -> list[OHLCVBar]:
    rows = (
        (
            await db.execute(
                select(OHLCVBar)
                .where(OHLCVBar.instrument_id == instrument_id, OHLCVBar.timeframe == timeframe)
                .order_by(OHLCVBar.ts.desc())
                .limit(RADAR_LOOKBACK_BARS)
            )
        )
        .scalars()
        .all()
    )
    rows = list(rows)
    rows.reverse()
    return rows


def _indicator_visual(
    indicator_type: str,
    *,
    params: dict,
    color: str,
    line_width: float,
    pane: str = "main",
    role: str | None = None,
    label: str | None = None,
) -> dict:
    return {
        "type": indicator_type,
        "params": params,
        "style": {
            "color": color,
            "lineWidth": line_width,
        },
        "pane": pane,
        "role": role,
        "label": label,
        "source_tag": "radar",
    }


def _drawing_point(ts: int, price: float) -> dict:
    return {"time": int(ts), "price": round(float(price), 4)}


def _drawing_style(
    *,
    color: str,
    line_width: float = 0.85,
    opacity: float = 1.0,
    filled: bool | None = None,
    dash_pattern: list[int] | None = None,
) -> dict:
    style: dict[str, object] = {
        "color": color,
        "lineWidth": line_width,
        "opacity": opacity,
    }
    if filled is not None:
        style["filled"] = filled
    if dash_pattern:
        style["dashPattern"] = dash_pattern
    return style


def _drawing_visual(
    drawing_type: str,
    *,
    points: list[dict],
    style: dict,
    label: str | None = None,
    source_role: str | None = None,
    data: dict | None = None,
    indicator_key: str | None = None,
) -> dict:
    payload = {
        "drawing_type": drawing_type,
        "indicator_key": indicator_key,
        "label": label,
        "notes": None,
        "data": {"points": points, **(data or {})},
        "style": style,
        "is_visible": True,
        "is_locked": True,
        "source_role": source_role,
        "source_tag": "radar",
    }
    return payload


def _extract_pivots(values: list[float], timestamps: list[int], highs: bool) -> list[Pivot]:
    pivots: list[Pivot] = []
    for idx in range(SWING_WINDOW, len(values) - SWING_WINDOW):
        window = values[idx - SWING_WINDOW : idx + SWING_WINDOW + 1]
        target = values[idx]
        if highs:
            if target >= max(window):
                pivots.append(Pivot(index=idx, price=target, ts=timestamps[idx]))
        else:
            if target <= min(window):
                pivots.append(Pivot(index=idx, price=target, ts=timestamps[idx]))
    return pivots


def _cluster_zones(
    pivots: list[Pivot], side: str, tolerance: float, latest_index: int
) -> list[Zone]:
    buckets: list[list[Pivot]] = []
    for pivot in pivots:
        matched = False
        for bucket in buckets:
            center = sum(p.price for p in bucket) / len(bucket)
            if abs(pivot.price - center) <= tolerance:
                bucket.append(pivot)
                matched = True
                break
        if not matched:
            buckets.append([pivot])

    zones: list[Zone] = []
    for bucket in buckets:
        if len(bucket) < MIN_ZONE_TOUCHES:
            continue
        bucket = sorted(bucket, key=lambda p: p.index)
        center = sum(p.price for p in bucket) / len(bucket)
        low = min(p.price for p in bucket)
        high = max(p.price for p in bucket)
        zones.append(
            Zone(
                side=side,
                center=center,
                low=low,
                high=high,
                touch_count=len(bucket),
                first_touch_index=bucket[0].index,
                last_touch_index=bucket[-1].index,
                last_touch_ts=bucket[-1].ts,
                pivots=bucket,
                role="support" if side == "low" else "resistance",
            )
        )

    zones.sort(
        key=lambda zone: (
            zone.touch_count,
            -(latest_index - zone.last_touch_index),
        ),
        reverse=True,
    )
    return zones[:MAX_ZONES_PER_SIDE]


def _latest_valid(series: list[float]) -> float | None:
    for value in reversed(series):
        if value is not None and not math.isnan(value):
            return float(value)
    return None


def _ema_context(data: OHLCVSeries) -> tuple[dict[str, float], list[dict]]:
    levels: dict[str, float] = {}
    visuals: list[dict] = []
    colors = {20: "#6ec6ff", 50: "#ffd166", 200: "#f4978e"}
    for period in EMA_PERIODS:
        series = compute_indicator("ema", data, {"period": period})["ema"].tolist()
        latest = _latest_valid(series)
        if latest is None:
            continue
        levels[f"ema_{period}"] = latest
        visuals.append(
            _indicator_visual(
                "ema",
                params={"period": period},
                color=colors[period],
                line_width=0.75,
                role=f"ema_{period}",
                label=f"EMA {period}",
            )
        )
    return levels, visuals


def _atr_latest(data: OHLCVSeries) -> float | None:
    series = compute_indicator("atr", data, {"period": 14})["atr"].tolist()
    return _latest_valid(series)


def _volatility_squeeze_context(data: OHLCVSeries) -> SqueezeContext:
    bb = compute_indicator("bb", data, {"period": 20, "std_dev": 2.0})
    keltner = compute_indicator(
        "keltner",
        data,
        {"period": 20, "atr_period": 10, "multiplier": 1.5},
    )
    bb_upper = bb["bb_upper"].tolist()
    bb_mid = bb["bb_mid"].tolist()
    bb_lower = bb["bb_lower"].tolist()
    kc_upper = keltner["keltner_upper"].tolist()
    kc_lower = keltner["keltner_lower"].tolist()

    widths: list[float] = []
    for upper, mid, lower in zip(bb_upper, bb_mid, bb_lower, strict=False):
        if (
            upper is None
            or mid is None
            or lower is None
            or math.isnan(upper)
            or math.isnan(mid)
            or math.isnan(lower)
            or mid == 0
        ):
            widths.append(math.nan)
            continue
        widths.append(float((upper - lower) / mid))

    latest_width = _latest_valid(widths)
    recent_widths = [
        value for value in widths[-SQUEEZE_LOOKBACK:] if value is not None and not math.isnan(value)
    ]
    if latest_width is None or not recent_widths:
        return SqueezeContext(
            bb_width=None,
            bb_width_percentile=0.0,
            inside_keltner=False,
            score=0.0,
        )

    less_or_equal = sum(1 for value in recent_widths if value <= latest_width)
    width_percentile = less_or_equal / len(recent_widths)
    latest_bb_upper = bb_upper[-1]
    latest_bb_lower = bb_lower[-1]
    latest_kc_upper = kc_upper[-1]
    latest_kc_lower = kc_lower[-1]
    inside_keltner = bool(
        latest_bb_upper is not None
        and latest_bb_lower is not None
        and latest_kc_upper is not None
        and latest_kc_lower is not None
        and not math.isnan(latest_bb_upper)
        and not math.isnan(latest_bb_lower)
        and not math.isnan(latest_kc_upper)
        and not math.isnan(latest_kc_lower)
        and latest_bb_upper <= latest_kc_upper
        and latest_bb_lower >= latest_kc_lower
    )
    score = _clamp((1 - width_percentile) * 0.75 + (0.25 if inside_keltner else 0.0))
    return SqueezeContext(
        bb_width=latest_width,
        bb_width_percentile=width_percentile,
        inside_keltner=inside_keltner,
        score=score,
    )


def _avwap_from_anchor(
    data: OHLCVSeries, anchor_ts: int, *, label: str = "AVWAP", role: str = "avwap"
) -> tuple[float | None, dict | None]:
    if anchor_ts <= 0:
        return None, None
    values = compute_indicator("avwap", data, {"anchor_timestamp": anchor_ts})["avwap"].tolist()
    latest = _latest_valid(values)
    if latest is None:
        return None, None
    overlay = _indicator_visual(
        "avwap",
        params={"anchor_timestamp": anchor_ts},
        color="#c77dff",
        line_width=0.75,
        role=role,
        label=label,
    )
    return latest, overlay


def _recent_reaction_quality(bars: list[OHLCVBar], zone: Zone) -> float:
    recent = bars[max(0, len(bars) - 10) :]
    if not recent:
        return 0.0
    hits = 0
    closes_away = 0
    for bar in recent:
        high = float(bar.high)
        low = float(bar.low)
        c = float(bar.close)
        if low <= zone.high and high >= zone.low:
            hits += 1
            if zone.role == "support" and c >= zone.center:
                closes_away += 1
            if zone.role == "resistance" and c <= zone.center:
                closes_away += 1
    if hits == 0:
        return 0.0
    return _clamp(closes_away / hits)


def _build_score(
    close: float,
    atr: float,
    zone: Zone,
    latest_index: int,
    confluence_levels: list[float],
    reaction_quality: float,
    *,
    multi_timeframe_bonus: float,
    trend_pattern_bonus: float,
    gap_bonus: float,
    avwap_anchor_quality: float,
    volatility_squeeze_score: float,
) -> dict:
    distance = abs(close - zone.center)
    atr_denom = max(atr, close * 0.005, 1e-6)
    distance_score = _clamp(1 - distance / (atr_denom * 2.2))
    touch_score = _clamp(zone.touch_count / 4)
    recency_score = _clamp(1 - (latest_index - zone.last_touch_index) / 120)
    age_score = _clamp((latest_index - zone.first_touch_index) / 180)
    confluence_hits = sum(
        1 for level in confluence_levels if abs(level - zone.center) <= atr_denom * 1.1
    )
    confluence_score = _clamp(confluence_hits / 4)
    timeframe_score = 1.0
    multi_timeframe_score = _clamp(multi_timeframe_bonus)
    trend_pattern_score = _clamp(trend_pattern_bonus)
    gap_context_score = _clamp(gap_bonus)
    avwap_anchor_score = _clamp(avwap_anchor_quality)
    total = (
        distance_score * 0.17
        + touch_score * 0.11
        + recency_score * 0.09
        + age_score * 0.07
        + confluence_score * 0.12
        + multi_timeframe_score * 0.07
        + trend_pattern_score * 0.07
        + gap_context_score * 0.05
        + avwap_anchor_score * 0.06
        + _clamp(volatility_squeeze_score) * 0.08
        + reaction_quality * 0.10
        + timeframe_score * 0.11
    )
    return {
        "distance_to_level": round(distance_score, 4),
        "touch_count": round(touch_score, 4),
        "recency": round(recency_score, 4),
        "structure_age": round(age_score, 4),
        "overlap_confluence": round(confluence_score, 4),
        "multi_timeframe_alignment": round(multi_timeframe_score, 4),
        "trend_pattern_quality": round(trend_pattern_score, 4),
        "gap_context": round(gap_context_score, 4),
        "avwap_anchor_quality": round(avwap_anchor_score, 4),
        "volatility_squeeze": round(_clamp(volatility_squeeze_score), 4),
        "recent_reaction_quality": round(reaction_quality, 4),
        "timeframe_importance": round(timeframe_score, 4),
        "normalized_score": round(_clamp(total), 4),
    }


def _make_zone_overlay(zone: Zone, timestamps: list[int], latest_ts: int, color: str) -> dict:
    start_ts = timestamps[max(0, zone.first_touch_index - 3)]
    return _drawing_visual(
        "rectangle",
        points=[
            _drawing_point(start_ts, zone.high),
            _drawing_point(latest_ts, zone.low),
        ],
        style=_drawing_style(color=color, line_width=0.75, opacity=0.62, filled=True),
        label=f"{zone.role.title()} zone",
        source_role=zone.role,
        data={"filled": True},
    )


def _make_marker(ts: int, price: float, label: str, color: str, role: str) -> dict:
    return _drawing_visual(
        "text_box",
        points=[_drawing_point(ts, price)],
        style=_drawing_style(color=color, line_width=0.75, opacity=1.0),
        label=label,
        source_role=role,
        data={"text": label},
    )


def _week52_levels(
    highs: list[float], lows: list[float], timestamps: list[int]
) -> dict[str, dict[str, float | int]]:
    window = 252 if len(highs) >= 252 else len(highs)
    if window <= 0:
        return {}
    start = len(highs) - window
    window_highs = highs[start:]
    window_lows = lows[start:]
    high_rel_index = max(range(window), key=window_highs.__getitem__)
    low_rel_index = min(range(window), key=window_lows.__getitem__)
    high_index = start + high_rel_index
    low_index = start + low_rel_index
    return {
        "week52_high": {
            "price": max(window_highs),
            "time": timestamps[high_index],
        },
        "week52_low": {
            "price": min(window_lows),
            "time": timestamps[low_index],
        },
    }


def _all_time_levels(
    highs: list[float], lows: list[float], timestamps: list[int]
) -> dict[str, dict[str, float | int]]:
    if not highs or not lows:
        return {}
    high_index = max(range(len(highs)), key=highs.__getitem__)
    low_index = min(range(len(lows)), key=lows.__getitem__)
    return {
        "all_time_high": {
            "price": highs[high_index],
            "time": timestamps[high_index],
        },
        "all_time_low": {
            "price": lows[low_index],
            "time": timestamps[low_index],
        },
    }


def _ytd_levels(
    opens: list[float], highs: list[float], lows: list[float], timestamps: list[int]
) -> dict[str, dict[str, float | int]]:
    if not timestamps:
        return {}
    current_year = datetime.fromtimestamp(timestamps[-1], tz=UTC).year
    start_index = next(
        (
            idx
            for idx, ts in enumerate(timestamps)
            if datetime.fromtimestamp(ts, tz=UTC).year == current_year
        ),
        0,
    )
    window_highs = highs[start_index:]
    window_lows = lows[start_index:]
    if not window_highs or not window_lows:
        return {}
    ytd_high_rel = max(range(len(window_highs)), key=window_highs.__getitem__)
    ytd_low_rel = min(range(len(window_lows)), key=window_lows.__getitem__)
    return {
        "ytd_open": {
            "price": opens[start_index],
            "time": timestamps[start_index],
        },
        "ytd_high": {
            "price": window_highs[ytd_high_rel],
            "time": timestamps[start_index + ytd_high_rel],
        },
        "ytd_low": {
            "price": window_lows[ytd_low_rel],
            "time": timestamps[start_index + ytd_low_rel],
        },
    }


def _rolling_window_levels(
    highs: list[float], lows: list[float], timestamps: list[int]
) -> dict[str, dict[str, float | int]]:
    levels: dict[str, dict[str, float | int]] = {}
    for label, window in (("weekly_12", 60), ("monthly_6", 126)):
        if len(highs) < 2:
            continue
        start = max(0, len(highs) - window)
        window_highs = highs[start:]
        window_lows = lows[start:]
        if not window_highs or not window_lows:
            continue
        high_rel_index = max(range(len(window_highs)), key=window_highs.__getitem__)
        low_rel_index = min(range(len(window_lows)), key=window_lows.__getitem__)
        levels[f"{label}_high"] = {
            "price": window_highs[high_rel_index],
            "time": timestamps[start + high_rel_index],
        }
        levels[f"{label}_low"] = {
            "price": window_lows[low_rel_index],
            "time": timestamps[start + low_rel_index],
        }
    return levels


def _trendline_from_pivots(
    pivots: list[Pivot], role: str, latest_index: int, latest_ts: int
) -> Trendline | None:
    if len(pivots) < 2:
        return None
    start_pivot, end_pivot = pivots[-2], pivots[-1]
    if end_pivot.index <= start_pivot.index:
        return None
    slope = (end_pivot.price - start_pivot.price) / (end_pivot.index - start_pivot.index)
    projected_end = end_pivot.price + slope * (latest_index - end_pivot.index)
    return Trendline(
        role=role,
        start_index=start_pivot.index,
        end_index=latest_index,
        start_ts=start_pivot.ts,
        end_ts=latest_ts,
        start_price=start_pivot.price,
        end_price=projected_end,
        slope=slope,
    )


def _trendline_price_at(trendline: Trendline, index: int) -> float:
    return trendline.start_price + trendline.slope * (index - trendline.start_index)


def _make_trendline_overlay(trendline: Trendline, color: str, label: str) -> dict:
    return _drawing_visual(
        "trendline",
        points=[
            _drawing_point(trendline.start_ts, trendline.start_price),
            _drawing_point(trendline.end_ts, trendline.end_price),
        ],
        style=_drawing_style(color=color, line_width=0.75, opacity=0.9, dash_pattern=[3, 2]),
        label=label,
        source_role=f"{trendline.role}_trendline",
        data={"extendRight": False, "extendLeft": False},
    )


def _pattern_structures(
    support_trendline: Trendline | None,
    resistance_trendline: Trendline | None,
) -> list[dict]:
    if support_trendline is None or resistance_trendline is None:
        return []
    start_gap = resistance_trendline.start_price - support_trendline.start_price
    end_gap = resistance_trendline.end_price - support_trendline.end_price
    if start_gap <= 0 or end_gap <= 0:
        return []
    slope_delta = abs(support_trendline.slope - resistance_trendline.slope)
    if (
        slope_delta
        <= max(abs(support_trendline.slope), abs(resistance_trendline.slope), 1e-6) * 0.4
    ):
        return [{"type": "channel", "width_change": round(end_gap - start_gap, 4)}]
    if end_gap < start_gap * 0.82:
        if support_trendline.slope > 0 and resistance_trendline.slope < 0:
            return [{"type": "triangle", "width_change": round(end_gap - start_gap, 4)}]
        return [{"type": "wedge", "width_change": round(end_gap - start_gap, 4)}]
    return []


def _gap_zones(bars: list[OHLCVBar], timestamps: list[int]) -> list[GapZone]:
    gaps: list[GapZone] = []
    start = max(1, len(bars) - RECENT_GAP_LOOKBACK)
    latest_ts = timestamps[-1] if timestamps else 0
    for idx in range(start, len(bars)):
        prev_bar = bars[idx - 1]
        bar = bars[idx]
        prev_high = float(prev_bar.high)
        prev_low = float(prev_bar.low)
        high = float(bar.high)
        low = float(bar.low)
        if low > prev_high * 1.002:
            gaps.append(
                GapZone(
                    role="support",
                    low=prev_high,
                    high=low,
                    start_ts=timestamps[idx - 1],
                    end_ts=latest_ts,
                    kind="up_gap",
                )
            )
        elif high < prev_low * 0.998:
            gaps.append(
                GapZone(
                    role="resistance",
                    low=high,
                    high=prev_low,
                    start_ts=timestamps[idx - 1],
                    end_ts=latest_ts,
                    kind="down_gap",
                )
            )
    return gaps[-3:]


def _make_gap_overlay(gap: GapZone) -> dict:
    color = "#5fa8d3" if gap.kind == "up_gap" else "#d9779b"
    return _drawing_visual(
        "rectangle",
        points=[
            _drawing_point(gap.start_ts, gap.high),
            _drawing_point(gap.end_ts, gap.low),
        ],
        style=_drawing_style(color=color, line_width=0.75, opacity=0.5, filled=True),
        label=gap.kind.replace("_", " "),
        source_role=gap.kind,
        data={"filled": True},
    )


def _choose_avwap_anchors(
    zone: Zone,
    *,
    atr: float,
    swing_lows: list[Pivot],
    swing_highs: list[Pivot],
    week52: dict[str, dict[str, float | int]],
    all_time: dict[str, dict[str, float | int]],
    ytd: dict[str, dict[str, float | int]],
) -> list[AvwapAnchor]:
    candidates: list[AvwapAnchor] = [
        AvwapAnchor("zone_pivot", zone.pivots[-1].ts, zone.pivots[-1].price, 4),
    ]
    if zone.role == "support":
        if swing_lows:
            candidates.append(
                AvwapAnchor("recent_swing_low", swing_lows[-1].ts, swing_lows[-1].price, 3)
            )
        if "week52_low" in week52:
            candidates.append(
                AvwapAnchor(
                    "week52_low",
                    int(week52["week52_low"]["time"]),
                    float(week52["week52_low"]["price"]),
                    5,
                )
            )
        if "all_time_low" in all_time:
            candidates.append(
                AvwapAnchor(
                    "all_time_low",
                    int(all_time["all_time_low"]["time"]),
                    float(all_time["all_time_low"]["price"]),
                    5,
                )
            )
        if "ytd_low" in ytd:
            candidates.append(
                AvwapAnchor(
                    "ytd_low", int(ytd["ytd_low"]["time"]), float(ytd["ytd_low"]["price"]), 4
                )
            )
    else:
        if swing_highs:
            candidates.append(
                AvwapAnchor("recent_swing_high", swing_highs[-1].ts, swing_highs[-1].price, 3)
            )
        if "week52_high" in week52:
            candidates.append(
                AvwapAnchor(
                    "week52_high",
                    int(week52["week52_high"]["time"]),
                    float(week52["week52_high"]["price"]),
                    5,
                )
            )
        if "all_time_high" in all_time:
            candidates.append(
                AvwapAnchor(
                    "all_time_high",
                    int(all_time["all_time_high"]["time"]),
                    float(all_time["all_time_high"]["price"]),
                    5,
                )
            )
        if "ytd_high" in ytd:
            candidates.append(
                AvwapAnchor(
                    "ytd_high", int(ytd["ytd_high"]["time"]), float(ytd["ytd_high"]["price"]), 4
                )
            )
    if "ytd_open" in ytd:
        candidates.append(
            AvwapAnchor(
                "ytd_open", int(ytd["ytd_open"]["time"]), float(ytd["ytd_open"]["price"]), 4
            )
        )

    candidates.sort(
        key=lambda candidate: (
            -candidate.priority,
            abs(candidate.reference_price - zone.center) > max(atr * 1.25, 1.0),
            abs(candidate.reference_price - zone.center),
            -candidate.ts,
        )
    )
    return candidates


def _candidate_summary(symbol: str, setup_type: RadarSetupType, zone: Zone, score: float) -> str:
    label = setup_type.value.replace("_", " ")
    return (
        f"{symbol} is showing a {label} setup around {zone.center:.2f} "
        f"with {zone.touch_count} swing touches and a radar score of {score:.2f}."
    )


def _candidate_invalidation(setup_type: RadarSetupType, zone: Zone) -> str:
    if setup_type in {
        RadarSetupType.APPROACHING_SUPPORT,
        RadarSetupType.COMPRESSION_SUPPORT,
        RadarSetupType.FAKEDOWN,
        RadarSetupType.RECLAIM,
        RadarSetupType.BREAKOUT_RETEST,
    }:
        return f"Invalidate on a decisive close back below {zone.low:.2f}."
    if setup_type in {
        RadarSetupType.APPROACHING_RESISTANCE,
        RadarSetupType.COMPRESSION_RESISTANCE,
        RadarSetupType.FAKEOUT,
        RadarSetupType.REJECTION,
        RadarSetupType.BREAKDOWN_RETEST,
    }:
        return f"Invalidate on a decisive close above {zone.high:.2f}."
    if setup_type == RadarSetupType.FAILED_RECLAIM:
        return f"Invalidate if price reclaims {zone.high:.2f} and holds back above the failed reclaim zone."
    if setup_type == RadarSetupType.FAILED_BREAKDOWN_RECOVERY:
        return f"Invalidate if price recovers back above {zone.high:.2f} after the failed recovery."
    if setup_type == RadarSetupType.BREAKOUT:
        return f"Invalidate if price falls back below {zone.low:.2f}."
    return f"Invalidate if price reclaims {zone.high:.2f}."


def _invalidation_price(setup_type: RadarSetupType, zone: Zone) -> float:
    if setup_type in {
        RadarSetupType.APPROACHING_SUPPORT,
        RadarSetupType.COMPRESSION_SUPPORT,
        RadarSetupType.FAKEDOWN,
        RadarSetupType.RECLAIM,
        RadarSetupType.BREAKOUT,
        RadarSetupType.BREAKOUT_RETEST,
    }:
        return round(zone.low, 4)
    return round(zone.high, 4)


def _make_invalidation_overlay(inv_price: float, timestamps: list[int], latest_ts: int) -> dict:
    return _drawing_visual(
        "horizontal_line",
        points=[_drawing_point(timestamps[0], inv_price)],
        style=_drawing_style(color="#ef5350", line_width=0.75, opacity=0.95, dash_pattern=[6, 3]),
        label="Invalidation",
        source_role="invalidation",
    )


def _make_level_overlay(
    price: float,
    timestamps: list[int],
    latest_ts: int,
    *,
    role: str,
    label: str,
    color: str,
    dash_pattern: list[int] | None = None,
) -> dict:
    return _drawing_visual(
        "horizontal_line",
        points=[_drawing_point(timestamps[0], price)],
        style=_drawing_style(
            color=color,
            line_width=0.8,
            opacity=0.92,
            dash_pattern=dash_pattern,
        ),
        label=label,
        source_role=role,
    )


def _entry_price(setup_type: RadarSetupType, zone: Zone) -> float:
    if setup_type in {
        RadarSetupType.APPROACHING_SUPPORT,
        RadarSetupType.COMPRESSION_SUPPORT,
        RadarSetupType.FAKEDOWN,
        RadarSetupType.BREAKOUT,
        RadarSetupType.BREAKOUT_RETEST,
        RadarSetupType.RECLAIM,
    }:
        return round(zone.high, 4)
    if setup_type in {
        RadarSetupType.BREAKDOWN,
        RadarSetupType.BREAKDOWN_RETEST,
        RadarSetupType.FAKEOUT,
        RadarSetupType.FAILED_RECLAIM,
        RadarSetupType.FAILED_BREAKDOWN_RECOVERY,
        RadarSetupType.REJECTION,
    }:
        return round(zone.low, 4)
    return round(zone.center, 4)


def _nearest_target_price(
    setup_type: RadarSetupType,
    *,
    entry_price: float,
    invalidation_price: float,
    zone: Zone,
    support_zones: list[Zone],
    resistance_zones: list[Zone],
) -> tuple[float, str]:
    risk = max(abs(entry_price - invalidation_price), max(zone.high - zone.low, 0.01) * 0.5, 0.01)
    if setup_type in LONG_BIASED_SETUPS:
        candidates = sorted(
            {
                round(candidate.center, 4)
                for candidate in resistance_zones
                if candidate.center > entry_price and abs(candidate.center - zone.center) > 1e-6
            }
        )
        if candidates:
            return candidates[0], "next resistance"
        return round(entry_price + risk * 2, 4), "two-risk extension"

    candidates = sorted(
        {
            round(candidate.center, 4)
            for candidate in support_zones
            if candidate.center < entry_price and abs(candidate.center - zone.center) > 1e-6
        },
        reverse=True,
    )
    if candidates:
        return candidates[0], "next support"
    return round(entry_price - risk * 2, 4), "two-risk extension"


def _state_for_setup(setup_type: RadarSetupType) -> RadarState:
    if setup_type in {
        RadarSetupType.APPROACHING_SUPPORT,
        RadarSetupType.APPROACHING_RESISTANCE,
        RadarSetupType.COMPRESSION_SUPPORT,
        RadarSetupType.COMPRESSION_RESISTANCE,
    }:
        return RadarState.DEVELOPING
    return RadarState.CONFIRMED


def _state_reason(
    setup_type: RadarSetupType,
    *,
    target_source: str,
) -> str:
    if setup_type == RadarSetupType.APPROACHING_SUPPORT:
        return "Developing near support; watch for a constructive reaction before treating it as confirmed."
    if setup_type == RadarSetupType.APPROACHING_RESISTANCE:
        return "Developing near resistance; watch for rejection or failure before treating it as confirmed."
    if setup_type == RadarSetupType.COMPRESSION_SUPPORT:
        return "Developing compression above support. A clean expansion away from the level would confirm the setup."
    if setup_type == RadarSetupType.COMPRESSION_RESISTANCE:
        return "Developing compression under resistance. A clean rejection or breakdown from the level would confirm the setup."
    if setup_type == RadarSetupType.BREAKOUT:
        return f"Confirmed breakout. The next objective is the {target_source} while price holds above the breakout zone."
    if setup_type == RadarSetupType.BREAKDOWN:
        return f"Confirmed breakdown. The next objective is the {target_source} while price stays below the breakdown zone."
    if setup_type == RadarSetupType.BREAKOUT_RETEST:
        return f"Confirmed breakout retest. The retest is holding so long as price respects the reclaimed zone on the way toward the {target_source}."
    if setup_type == RadarSetupType.BREAKDOWN_RETEST:
        return f"Confirmed breakdown retest. The retest is holding so long as price stays below the lost zone on the way toward the {target_source}."
    if setup_type == RadarSetupType.FAKEOUT:
        return f"Confirmed fakeout. Price pierced resistance and failed back below it, opening room toward the {target_source} while the fakeout high holds."
    if setup_type == RadarSetupType.FAKEDOWN:
        return f"Confirmed fakedown. Price flushed below support and recovered it, opening room toward the {target_source} while the washout low holds."
    if setup_type == RadarSetupType.FAILED_RECLAIM:
        return f"Confirmed failed reclaim. Price lost the recovered zone again and now leans toward the {target_source} unless the reclaim is recovered."
    if setup_type == RadarSetupType.FAILED_BREAKDOWN_RECOVERY:
        return f"Confirmed failed breakdown recovery. The bounce failed under the broken zone, keeping the {target_source} in play."
    if setup_type == RadarSetupType.RECLAIM:
        return f"Confirmed reclaim. Price has recovered the zone and now targets the {target_source} if the reclaim holds."
    return f"Confirmed rejection. The current move remains valid while price respects the rejection zone on the way toward the {target_source}."


def _candidate_evidence(
    base: dict,
    setup_type: RadarSetupType,
    zone: Zone,
    timestamps: list[int],
    latest_ts: int,
    *,
    state: RadarState,
    state_reason: str,
    entry_price: float,
    invalidation_price: float,
    target_price: float,
    target_source: str,
    signal_ts: int,
) -> dict:
    return {
        **base,
        "overlays": [],
        "drawing_visuals": [
            *(base.get("drawing_visuals") or []),
            _make_level_overlay(
                entry_price,
                timestamps,
                latest_ts,
                role="entry",
                label="Entry",
                color="#9be564",
                dash_pattern=[4, 2],
            ),
            _make_invalidation_overlay(invalidation_price, timestamps, latest_ts),
            _make_level_overlay(
                target_price,
                timestamps,
                latest_ts,
                role="target",
                label="Target",
                color="#f6bd60",
                dash_pattern=[8, 3],
            ),
        ],
        "metrics": {
            **base["metrics"],
            "entry_price": entry_price,
            "invalidation_price": invalidation_price,
            "target_price": target_price,
            "target_source": target_source,
            "risk_reward": round(
                abs(target_price - entry_price) / max(abs(entry_price - invalidation_price), 1e-6),
                4,
            ),
            "state": state.value,
            "state_reason": state_reason,
            "signal_time": signal_ts,
            "context_time": zone.last_touch_ts,
        },
    }


def _ts_to_datetime(ts: int | None) -> datetime | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=UTC)


def _candidate_sort_key(candidate: DetectionCandidate) -> tuple[datetime, int, int]:
    return (
        candidate.signal_at,
        RADAR_SETUP_SEQUENCE_PRIORITY.get(candidate.setup_type, 99),
        int(round(candidate.key_level_price * 10_000)),
    )


def _thread_match_tolerance(candidate: DetectionCandidate) -> float:
    atr = candidate.evidence.get("metrics", {}).get("atr_14")
    if isinstance(atr, int | float) and atr > 0:
        return max(float(atr) * 1.1, candidate.key_level_price * THREAD_PRICE_TOLERANCE_FRACTION)
    return max(candidate.key_level_price * 0.012, 1.0)


def _find_matching_thread(
    candidate: DetectionCandidate,
    threads: list[RadarSetupThread],
) -> RadarSetupThread | None:
    if candidate.context_role is None:
        return None

    tolerance = _thread_match_tolerance(candidate)
    matches = [
        thread
        for thread in threads
        if thread.context_role == candidate.context_role
        and abs(float(thread.reference_price) - candidate.key_level_price) <= tolerance
    ]
    if not matches:
        return None

    matches.sort(
        key=lambda thread: (
            abs(float(thread.reference_price) - candidate.key_level_price),
            abs((thread.last_seen_at - candidate.signal_at).total_seconds()),
            -thread.detection_count,
            -(thread.id or 0),
        )
    )
    return matches[0]


def _apply_candidate_to_thread(
    candidate: DetectionCandidate,
    thread: RadarSetupThread,
) -> int:
    next_index = int(thread.detection_count) + 1
    thread.started_at = min(thread.started_at, candidate.signal_at)
    thread.last_seen_at = max(thread.last_seen_at, candidate.signal_at)
    thread.current_setup_type = candidate.setup_type
    thread.current_state = candidate.state
    thread.state_changed_at = candidate.signal_at
    thread.detection_count = next_index
    if candidate.context_role is not None:
        thread.context_role = candidate.context_role
    if candidate.key_level_price > 0:
        prior_count = max(next_index - 1, 0)
        if prior_count <= 0:
            thread.reference_price = candidate.key_level_price
        else:
            thread.reference_price = (
                (float(thread.reference_price) * prior_count) + candidate.key_level_price
            ) / next_index
    return next_index


def _same_moment(left: datetime | None, right: datetime | None) -> bool:
    if left is None or right is None:
        return left is right
    return left == right


def _find_duplicate_thread_detection(
    candidate: DetectionCandidate,
    thread: RadarSetupThread,
) -> RadarDetection | None:
    detections = list(thread.detections or [])
    if not detections:
        return None

    tolerance = _thread_match_tolerance(candidate)
    matches = [
        detection
        for detection in detections
        if detection.setup_type == candidate.setup_type
        and _same_moment(detection.signal_at, candidate.signal_at)
        and _same_moment(detection.context_at, candidate.context_at)
        and detection.key_level_price is not None
        and abs(float(detection.key_level_price) - candidate.key_level_price) <= tolerance
    ]
    if not matches:
        return None

    matches.sort(
        key=lambda detection: (
            detection.signal_at,
            detection.observed_at,
            detection.id or 0,
        ),
        reverse=True,
    )
    return matches[0]


def _refresh_duplicate_detection(
    detection: RadarDetection,
    candidate: DetectionCandidate,
    *,
    run_id: int,
    thread: RadarSetupThread,
    thread_event_index: int,
) -> None:
    detection.run_id = run_id
    detection.thread = thread
    detection.timeframe = thread.timeframe
    detection.setup_type = candidate.setup_type
    detection.score = candidate.score
    detection.observed_at = candidate.observed_at
    detection.signal_at = candidate.signal_at
    detection.context_at = candidate.context_at
    detection.state = candidate.state
    detection.state_reason = candidate.state_reason
    detection.fresh_until = candidate.fresh_until
    detection.thread_event_index = thread_event_index
    detection.key_level_price = candidate.key_level_price
    detection.entry_price = candidate.entry_price
    detection.invalidation_price = candidate.invalidation_price
    detection.target_price = candidate.target_price
    detection.summary = candidate.summary
    detection.invalidation_hint = candidate.invalidation_hint
    detection.evidence_json = candidate.evidence
    detection.score_factors = candidate.score_factors
    detection.outcome_status = RadarOutcomeStatus.OPEN
    detection.outcome_last_evaluated_at = None
    detection.target_hit_at = None
    detection.invalidated_at = None


def _latest_thread_detection(thread: RadarSetupThread) -> RadarDetection | None:
    detections = list(thread.detections or [])
    if not detections:
        return None
    detections.sort(
        key=lambda detection: (
            detection.signal_at,
            detection.thread_event_index or 0,
            detection.id or 0,
        ),
        reverse=True,
    )
    return detections[0]


def _overlapping_current_run_detection(
    thread: RadarSetupThread,
    previous_detection: RadarDetection,
    current_run_detections: list[RadarDetection],
) -> bool:
    tolerance = max(
        float(previous_detection.key_level_price or thread.reference_price or 0.0)
        * THREAD_PRICE_TOLERANCE_FRACTION,
        1.0,
    )
    for detection in current_run_detections:
        if detection.state not in {RadarState.DEVELOPING, RadarState.CONFIRMED}:
            continue
        if detection.setup_type != previous_detection.setup_type:
            continue
        if detection.thread is None:
            continue
        if detection.thread.context_role != thread.context_role:
            continue
        if detection.key_level_price is None or previous_detection.key_level_price is None:
            continue
        if (
            abs(float(detection.key_level_price) - float(previous_detection.key_level_price))
            > tolerance
        ):
            continue
        return True
    return False


def _state_transition_reason(
    previous_detection: RadarDetection,
    next_state: RadarState,
    close: float,
) -> str:
    if next_state == RadarState.RESOLVED:
        target_price = float(
            previous_detection.target_price or previous_detection.key_level_price or close
        )
        return (
            f"The prior {previous_detection.setup_type.value.replace('_', ' ')} setup reached "
            f"its target near {target_price:.2f}, completing the thesis."
        )
    if next_state == RadarState.INVALIDATED:
        return (
            f"The prior {previous_detection.setup_type.value.replace('_', ' ')} setup was invalidated "
            f"after price closed at {close:.2f} through its invalidation level."
        )
    return (
        f"The prior {previous_detection.setup_type.value.replace('_', ' ')} setup went stale as "
        "its original thesis stopped being timely."
    )


def _state_transition_summary(
    symbol: str,
    previous_detection: RadarDetection,
    next_state: RadarState,
) -> str:
    if next_state == RadarState.RESOLVED:
        return f"{symbol} {previous_detection.setup_type.value.replace('_', ' ')} hit target."
    state_label = next_state.value.replace("_", " ")
    setup_label = previous_detection.setup_type.value.replace("_", " ")
    return f"{symbol} {setup_label} moved to {state_label}."


def _bar_timestamp_utc(bar: OHLCVBar) -> datetime:
    return bar.ts if bar.ts.tzinfo else bar.ts.replace(tzinfo=UTC)


def _bars_after_signal(bars: list[OHLCVBar], signal_at: datetime) -> list[OHLCVBar]:
    signal_at_utc = signal_at if signal_at.tzinfo else signal_at.replace(tzinfo=UTC)
    return [bar for bar in bars if _bar_timestamp_utc(bar) >= signal_at_utc]


def _pct_move(base_price: float | None, move: float | None) -> float | None:
    if base_price is None or move is None or base_price <= 0:
        return None
    return ((move - base_price) / base_price) * 100


def _latest_valid_before(values: list[float | None], index: int) -> float | None:
    for position in range(min(index, len(values) - 1), -1, -1):
        value = values[position]
        if value is None or math.isnan(value):
            continue
        return float(value)
    return None


def _close_side(close: float, level: float, tolerance: float) -> int:
    if close >= level + tolerance:
        return 1
    if close <= level - tolerance:
        return -1
    return 0


def _risk_reward_from_price(
    latest_close: float,
    *,
    target_price: float | None,
    invalidation_price: float | None,
    long_biased: bool,
    short_biased: bool,
) -> float | None:
    if target_price is None or invalidation_price is None:
        return None
    if long_biased:
        remaining_reward = target_price - latest_close
        remaining_risk = latest_close - invalidation_price
    elif short_biased:
        remaining_reward = latest_close - target_price
        remaining_risk = invalidation_price - latest_close
    else:
        return None
    if remaining_reward <= 0 or remaining_risk <= 0:
        return 0.0
    return remaining_reward / remaining_risk


def _favorable_progress_ratio(
    *,
    entry_price: float,
    target_price: float | None,
    favorable_excursion_pct: float | None,
) -> float | None:
    if target_price is None or favorable_excursion_pct is None or entry_price <= 0:
        return None
    target_distance_pct = abs((target_price - entry_price) / entry_price) * 100
    if target_distance_pct <= 0:
        return None
    return favorable_excursion_pct / target_distance_pct


def _newer_thread_detection(
    detection: RadarDetection,
    thread: RadarSetupThread | None,
) -> RadarDetection | None:
    if thread is None:
        return None
    current_index = detection.thread_event_index or 0
    current_id = detection.id or 0
    later_rows = [
        row
        for row in list(thread.detections or [])
        if (
            (row.thread_event_index or 0) > current_index
            or (
                (row.thread_event_index or 0) == current_index
                and row.signal_at > detection.signal_at
            )
            or (row.signal_at == detection.signal_at and (row.id or 0) > current_id)
        )
    ]
    if not later_rows:
        return None
    later_rows.sort(
        key=lambda row: (
            row.signal_at,
            row.thread_event_index or 0,
            row.id or 0,
        ),
    )
    return later_rows[0]


def _assess_detection_staleness(
    detection: RadarDetection,
    bars: list[OHLCVBar],
    *,
    thread: RadarSetupThread | None = None,
) -> StaleAssessment:
    if detection.state in {RadarState.INVALIDATED, RadarState.RESOLVED, RadarState.STALE}:
        return StaleAssessment(False, None, None, None, {})
    if detection.outcome_status in {
        RadarOutcomeStatus.INVALIDATED,
        RadarOutcomeStatus.TARGET_HIT,
        RadarOutcomeStatus.STALE,
    }:
        return StaleAssessment(False, None, None, None, {})

    later_detection = _newer_thread_detection(detection, thread)
    if later_detection is not None:
        return StaleAssessment(
            is_stale=True,
            stale_at=later_detection.signal_at,
            reason=(
                f"Superseded by a newer {later_detection.setup_type.value.replace('_', ' ')} "
                f"{later_detection.state.value.replace('_', ' ')} event on the same level."
            ),
            reason_code="superseded_by_thread",
            metrics={
                "superseded_by_detection_id": later_detection.id,
                "superseded_by_setup_type": later_detection.setup_type.value,
                "superseded_by_state": later_detection.state.value,
                "superseded_at": int(later_detection.signal_at.timestamp()),
            },
        )

    signal_bars = _bars_after_signal(bars, detection.signal_at)
    if not signal_bars:
        return StaleAssessment(False, None, None, None, {})

    entry_price = float(detection.entry_price or detection.key_level_price or 0)
    target_price = float(detection.target_price) if detection.target_price is not None else None
    invalidation_price = (
        float(detection.invalidation_price) if detection.invalidation_price is not None else None
    )
    key_level = float(detection.key_level_price or entry_price or 0)
    latest_close = float(signal_bars[-1].close)
    long_biased = detection.setup_type in LONG_BIASED_SETUPS
    short_biased = detection.setup_type in SHORT_BIASED_SETUPS
    if entry_price <= 0 or (not long_biased and not short_biased):
        return StaleAssessment(False, None, None, None, {})

    full_series = OHLCVSeries.from_orm_bars(bars)
    atr_values = compute_indicator("atr", full_series, {"period": 14})["atr"].tolist()
    signal_index = next(
        (index for index, bar in enumerate(bars) if _bar_timestamp_utc(bar) >= detection.signal_at),
        len(bars) - 1,
    )
    signal_atr = _latest_valid_before(atr_values, signal_index)
    latest_atr = _latest_valid(atr_values)

    tolerance = max((latest_atr or signal_atr or max(entry_price * 0.0025, 0.25)) * 0.2, 0.02)
    last_side = 0
    flip_count = 0
    zone_cross_count = 0
    for bar in signal_bars:
        close_side = _close_side(float(bar.close), key_level, tolerance)
        if close_side != 0:
            if last_side != 0 and close_side != last_side:
                flip_count += 1
            last_side = close_side
        if float(bar.low) <= key_level <= float(bar.high):
            zone_cross_count += 1

    progress_ratio = _favorable_progress_ratio(
        entry_price=entry_price,
        target_price=target_price,
        favorable_excursion_pct=detection.max_favorable_excursion_pct,
    )
    live_reward_risk = _risk_reward_from_price(
        latest_close,
        target_price=target_price,
        invalidation_price=invalidation_price,
        long_biased=long_biased,
        short_biased=short_biased,
    )
    entry_drift_atr = (
        abs(latest_close - entry_price) / latest_atr if latest_atr and latest_atr > 0 else None
    )
    volatility_regime_ratio = (
        (latest_atr / signal_atr) if latest_atr and signal_atr and signal_atr > 0 else None
    )

    timeframe = detection.timeframe
    bar_budget = STALE_BAR_BUDGETS.get(timeframe, 20)
    min_progress_ratio = STALE_MIN_PROGRESS_RATIO.get(timeframe, 0.18)
    min_live_rr = STALE_MIN_LIVE_REWARD_RISK.get(timeframe, 1.0)
    entry_drift_limit = STALE_ENTRY_DRIFT_ATR.get(timeframe, 3.5)
    flip_limit = STALE_LEVEL_FLIP_LIMIT.get(timeframe, 5)
    cross_limit = STALE_LEVEL_CROSS_LIMIT.get(timeframe, 8)

    stagnation = detection.bars_since_signal >= bar_budget and (
        progress_ratio is None or progress_ratio < min_progress_ratio
    )
    opportunity_decay = (
        detection.bars_since_signal >= max(4, bar_budget // 2)
        and live_reward_risk is not None
        and live_reward_risk < min_live_rr
        and entry_drift_atr is not None
        and entry_drift_atr >= entry_drift_limit
    )
    structure_drift = flip_count >= flip_limit or zone_cross_count >= cross_limit
    volatility_regime_change = (
        detection.bars_since_signal >= max(4, bar_budget // 2)
        and volatility_regime_ratio is not None
        and (
            volatility_regime_ratio < STALE_VOLATILITY_REGIME_RANGE[0]
            or volatility_regime_ratio > STALE_VOLATILITY_REGIME_RANGE[1]
        )
    )

    stale_signals = [
        ("range_stagnation", stagnation),
        ("opportunity_decay", opportunity_decay),
        ("structure_drift", structure_drift),
        ("volatility_regime_change", volatility_regime_change),
    ]
    triggered = [code for code, active in stale_signals if active]
    if not triggered:
        return StaleAssessment(
            False,
            None,
            None,
            None,
            {
                "bar_budget": bar_budget,
                "progress_ratio": round(progress_ratio, 4) if progress_ratio is not None else None,
                "live_reward_risk": round(live_reward_risk, 4)
                if live_reward_risk is not None
                else None,
                "entry_drift_atr": round(entry_drift_atr, 4)
                if entry_drift_atr is not None
                else None,
                "flip_count": flip_count,
                "zone_cross_count": zone_cross_count,
                "volatility_regime_ratio": round(volatility_regime_ratio, 4)
                if volatility_regime_ratio is not None
                else None,
            },
        )

    stale_due_to_context = (
        (stagnation and len(triggered) >= 2)
        or (detection.bars_since_signal >= int(bar_budget * 1.5) and len(triggered) >= 1)
        or (structure_drift and opportunity_decay)
    )
    if not stale_due_to_context:
        return StaleAssessment(
            False,
            None,
            None,
            None,
            {
                "bar_budget": bar_budget,
                "progress_ratio": round(progress_ratio, 4) if progress_ratio is not None else None,
                "live_reward_risk": round(live_reward_risk, 4)
                if live_reward_risk is not None
                else None,
                "entry_drift_atr": round(entry_drift_atr, 4)
                if entry_drift_atr is not None
                else None,
                "flip_count": flip_count,
                "zone_cross_count": zone_cross_count,
                "volatility_regime_ratio": round(volatility_regime_ratio, 4)
                if volatility_regime_ratio is not None
                else None,
                "triggered_checks": triggered,
            },
        )

    primary_reason = triggered[0]
    reason_lookup = {
        "range_stagnation": "Price has lingered too long without making enough progress toward target.",
        "opportunity_decay": "The live reward/risk has decayed too far from the original entry thesis.",
        "structure_drift": "Repeated back-and-forth through the key level has weakened the original structure.",
        "volatility_regime_change": "The volatility regime has shifted enough that the original setup framing is no longer timely.",
    }
    return StaleAssessment(
        True,
        _bar_timestamp_utc(signal_bars[-1]),
        reason_lookup[primary_reason],
        primary_reason,
        {
            "bar_budget": bar_budget,
            "bars_since_signal": detection.bars_since_signal,
            "progress_ratio": round(progress_ratio, 4) if progress_ratio is not None else None,
            "live_reward_risk": round(live_reward_risk, 4)
            if live_reward_risk is not None
            else None,
            "entry_drift_atr": round(entry_drift_atr, 4) if entry_drift_atr is not None else None,
            "flip_count": flip_count,
            "zone_cross_count": zone_cross_count,
            "volatility_regime_ratio": round(volatility_regime_ratio, 4)
            if volatility_regime_ratio is not None
            else None,
            "triggered_checks": triggered,
        },
    )


def _evaluate_detection_outcome(
    detection: RadarDetection,
    bars: list[OHLCVBar],
    *,
    thread: RadarSetupThread | None = None,
) -> None:
    signal_bars = _bars_after_signal(bars, detection.observed_at)
    detection.outcome_last_evaluated_at = (
        _bar_timestamp_utc(signal_bars[-1]) if signal_bars else detection.observed_at
    )
    detection.bars_since_signal = max(len(signal_bars) - 1, 0)
    if detection.state == RadarState.RESOLVED:
        detection.outcome_status = RadarOutcomeStatus.TARGET_HIT
        detection.target_hit_at = detection.target_hit_at or detection.signal_at
        return
    if detection.state == RadarState.INVALIDATED:
        detection.outcome_status = RadarOutcomeStatus.INVALIDATED
        detection.invalidated_at = detection.invalidated_at or detection.signal_at
        return
    if detection.state == RadarState.STALE:
        detection.outcome_status = RadarOutcomeStatus.STALE
        return

    entry_price = float(detection.entry_price or detection.key_level_price or 0)
    invalidation_price = (
        float(detection.invalidation_price) if detection.invalidation_price is not None else None
    )
    target_price = float(detection.target_price) if detection.target_price is not None else None
    if entry_price <= 0 or not signal_bars:
        return

    long_biased = detection.setup_type in LONG_BIASED_SETUPS
    short_biased = detection.setup_type in SHORT_BIASED_SETUPS
    highs = [float(bar.high) for bar in signal_bars]
    lows = [float(bar.low) for bar in signal_bars]

    if long_biased:
        max_favorable_price = max(highs) if highs else None
        max_adverse_price = min(lows) if lows else None
        detection.max_favorable_excursion_pct = _pct_move(entry_price, max_favorable_price)
        detection.max_adverse_excursion_pct = (
            ((entry_price - max_adverse_price) / entry_price) * 100
            if max_adverse_price is not None and entry_price > 0
            else None
        )
    elif short_biased:
        max_favorable_price = min(lows) if lows else None
        max_adverse_price = max(highs) if highs else None
        detection.max_favorable_excursion_pct = (
            ((entry_price - max_favorable_price) / entry_price) * 100
            if max_favorable_price is not None and entry_price > 0
            else None
        )
        detection.max_adverse_excursion_pct = _pct_move(entry_price, max_adverse_price)

    target_hit_at: datetime | None = None
    invalidated_at: datetime | None = None
    for bar in signal_bars:
        bar_ts = _bar_timestamp_utc(bar)
        high = float(bar.high)
        low = float(bar.low)
        if long_biased:
            if target_hit_at is None and target_price is not None and high >= target_price:
                target_hit_at = bar_ts
            if (
                invalidated_at is None
                and invalidation_price is not None
                and low <= invalidation_price
            ):
                invalidated_at = bar_ts
        elif short_biased:
            if target_hit_at is None and target_price is not None and low <= target_price:
                target_hit_at = bar_ts
            if (
                invalidated_at is None
                and invalidation_price is not None
                and high >= invalidation_price
            ):
                invalidated_at = bar_ts

    detection.target_hit_at = target_hit_at
    detection.invalidated_at = invalidated_at
    if target_hit_at and (invalidated_at is None or target_hit_at <= invalidated_at):
        detection.outcome_status = RadarOutcomeStatus.TARGET_HIT
        return
    if invalidated_at is not None:
        detection.outcome_status = RadarOutcomeStatus.INVALIDATED
        return
    stale_assessment = _assess_detection_staleness(detection, bars, thread=thread)
    if stale_assessment.is_stale:
        detection.outcome_status = RadarOutcomeStatus.STALE
        return
    detection.outcome_status = RadarOutcomeStatus.OPEN


def analyze_instrument(instrument: Instrument, bars: list[OHLCVBar]) -> list[DetectionCandidate]:
    if len(bars) < 80:
        return []

    data = OHLCVSeries.from_orm_bars(bars)
    opens = [float(b.open) for b in bars]
    closes = [float(b.close) for b in bars]
    highs = [float(b.high) for b in bars]
    lows = [float(b.low) for b in bars]
    timestamps = data.timestamps.tolist()
    latest_index = len(bars) - 1
    latest_bar = bars[-1]
    prev_bar = bars[-2]
    close = closes[-1]
    prev_close = closes[-2]
    latest_ts = timestamps[-1]
    atr = _atr_latest(data) or max(close * 0.01, 1.0)
    tolerance = max(atr * 0.75, close * 0.008)
    proximity = max(atr * 1.2, close * 0.015)

    swing_lows = _extract_pivots(lows, timestamps, highs=False)
    swing_highs = _extract_pivots(highs, timestamps, highs=True)
    support_zones = _cluster_zones(swing_lows, "low", tolerance, latest_index)
    resistance_zones = _cluster_zones(swing_highs, "high", tolerance, latest_index)
    ema_levels, ema_overlays = _ema_context(data)
    week52 = _week52_levels(highs, lows, timestamps)
    all_time = _all_time_levels(highs, lows, timestamps)
    ytd = _ytd_levels(opens, highs, lows, timestamps)
    rolling_levels = _rolling_window_levels(highs, lows, timestamps)
    gap_zones = _gap_zones(bars, timestamps)
    squeeze = _volatility_squeeze_context(data)
    support_trendline = _trendline_from_pivots(swing_lows, "support", latest_index, latest_ts)
    resistance_trendline = _trendline_from_pivots(
        swing_highs, "resistance", latest_index, latest_ts
    )
    pattern_structures = _pattern_structures(support_trendline, resistance_trendline)

    candidates: list[DetectionCandidate] = []
    contextual_levels = {
        **week52,
        **all_time,
        **ytd,
        **rolling_levels,
    }
    base_levels = list(ema_levels.values()) + [
        float(level["price"]) for level in contextual_levels.values()
    ]

    for zone in support_zones + resistance_zones:
        reaction_quality = _recent_reaction_quality(bars, zone)
        avwap_anchors = _choose_avwap_anchors(
            zone,
            atr=atr,
            swing_lows=swing_lows,
            swing_highs=swing_highs,
            week52=week52,
            all_time=all_time,
            ytd=ytd,
        )
        chosen_anchor = avwap_anchors[0]
        avwap_value, avwap_overlay = _avwap_from_anchor(
            data,
            chosen_anchor.ts,
            label=f"AVWAP {chosen_anchor.anchor_type.replace('_', ' ')}",
            role="avwap_primary",
        )
        secondary_anchor = avwap_anchors[1] if len(avwap_anchors) > 1 else None
        secondary_avwap_value = None
        secondary_avwap_overlay = None
        if secondary_anchor is not None and secondary_anchor.priority >= 4:
            secondary_avwap_value, secondary_avwap_overlay = _avwap_from_anchor(
                data,
                secondary_anchor.ts,
                label=f"AVWAP {secondary_anchor.anchor_type.replace('_', ' ')}",
                role="avwap_secondary",
            )
        confluence_levels = list(base_levels)
        if avwap_value is not None:
            confluence_levels.append(avwap_value)
        if secondary_avwap_value is not None:
            confluence_levels.append(secondary_avwap_value)

        nearby_context_levels = [
            name
            for name, level in contextual_levels.items()
            if abs(float(level["price"]) - zone.center) <= max(atr * 1.3, 1.0)
        ]
        multi_timeframe_bonus = _clamp(len(nearby_context_levels) / 4)
        trend_pattern_bonus = 0.0
        if support_trendline is not None and zone.role == "support":
            trend_pattern_bonus += (
                _clamp(
                    1
                    - abs(_trendline_price_at(support_trendline, latest_index) - zone.center)
                    / max(atr * 1.5, 1.0)
                )
                * 0.55
            )
        if resistance_trendline is not None and zone.role == "resistance":
            trend_pattern_bonus += (
                _clamp(
                    1
                    - abs(_trendline_price_at(resistance_trendline, latest_index) - zone.center)
                    / max(atr * 1.5, 1.0)
                )
                * 0.55
            )
        if pattern_structures:
            trend_pattern_bonus += 0.35
        nearby_gaps = [
            gap
            for gap in gap_zones
            if abs(((gap.low + gap.high) / 2) - zone.center) <= max(atr * 1.4, 1.0)
        ]
        gap_bonus = _clamp(len(nearby_gaps) / 2)
        avwap_anchor_quality = _clamp(chosen_anchor.priority / 5)
        score_factors = _build_score(
            close,
            atr,
            zone,
            latest_index,
            confluence_levels,
            reaction_quality,
            multi_timeframe_bonus=multi_timeframe_bonus,
            trend_pattern_bonus=trend_pattern_bonus,
            gap_bonus=gap_bonus,
            avwap_anchor_quality=avwap_anchor_quality,
            volatility_squeeze_score=squeeze.score,
        )
        score = float(score_factors["normalized_score"])

        drawing_visuals = [
            _make_zone_overlay(
                zone, timestamps, latest_ts, "#2ec4b6" if zone.role == "support" else "#ff9f1c"
            ),
            _make_marker(latest_ts, close, "Current", "#ffffff", "price"),
        ]
        indicator_visuals = list(ema_overlays)
        if support_trendline is not None:
            drawing_visuals.append(
                _make_trendline_overlay(support_trendline, "#4ecdc4", "Support trendline")
            )
        if resistance_trendline is not None:
            drawing_visuals.append(
                _make_trendline_overlay(resistance_trendline, "#f08a5d", "Resistance trendline")
            )
        if avwap_overlay is not None:
            indicator_visuals.append(avwap_overlay)
        if secondary_avwap_overlay is not None:
            indicator_visuals.append(secondary_avwap_overlay)
        if squeeze.score >= 0.6:
            indicator_visuals.extend(
                [
                    _indicator_visual(
                        "bb",
                        params={"period": 20, "std_dev": 2},
                        color="#80cbc4",
                        line_width=0.75,
                        role="bb_squeeze_context",
                        label="BB 20,2",
                    ),
                    _indicator_visual(
                        "keltner",
                        params={"period": 20, "atr_period": 10, "multiplier": 1.5},
                        color="#ce93d8",
                        line_width=0.75,
                        role="keltner_squeeze_context",
                        label="Keltner 20,10,1.5",
                    ),
                ]
            )
        for gap in nearby_gaps:
            drawing_visuals.append(_make_gap_overlay(gap))
        for key, level in contextual_levels.items():
            if abs(float(level["price"]) - zone.center) > max(atr * 1.5, close * 0.02):
                continue
            drawing_visuals.append(
                _make_level_overlay(
                    round(float(level["price"]), 4),
                    timestamps,
                    latest_ts,
                    role=key,
                    label=key.replace("_", " "),
                    color="#8ecae6" if "high" in key else "#5fa8d3",
                    dash_pattern=[5, 4],
                )
            )

        evidence = {
            "overlays": [],
            "indicator_visuals": indicator_visuals,
            "drawing_visuals": drawing_visuals,
            "metrics": {
                "close": round(close, 4),
                "atr_14": round(atr, 4),
                "zone_center": round(zone.center, 4),
                "distance_to_zone": round(abs(close - zone.center), 4),
                "ema_levels": {k: round(v, 4) for k, v in ema_levels.items()},
                "avwap": round(avwap_value, 4) if avwap_value is not None else None,
                "avwap_anchor_type": chosen_anchor.anchor_type,
                "avwap_anchor_time": chosen_anchor.ts,
                "avwap_anchor_price": round(chosen_anchor.reference_price, 4),
                "secondary_avwap": round(secondary_avwap_value, 4)
                if secondary_avwap_value is not None
                else None,
                "secondary_avwap_anchor_type": secondary_anchor.anchor_type
                if secondary_anchor is not None
                else None,
                "gap_count": len(nearby_gaps),
                "pattern_count": len(pattern_structures),
                "multi_timeframe_hits": len(nearby_context_levels),
                "bb_width": round(squeeze.bb_width, 6) if squeeze.bb_width is not None else None,
                "bb_width_percentile": round(squeeze.bb_width_percentile, 4),
                "inside_keltner": squeeze.inside_keltner,
                "volatility_squeeze_active": squeeze.score >= 0.6,
                **{
                    key: round(float(level["price"]), 4) for key, level in contextual_levels.items()
                },
                **{f"{key}_time": int(level["time"]) for key, level in contextual_levels.items()},
            },
            "structures": [
                {
                    "type": "horizontal_zone",
                    "role": zone.role,
                    "touch_count": zone.touch_count,
                    "first_touch_time": timestamps[zone.first_touch_index],
                    "last_touch_time": zone.last_touch_ts,
                },
                *(
                    [
                        {
                            "type": "trendline",
                            "role": "support",
                            "start_time": support_trendline.start_ts,
                            "end_time": support_trendline.end_ts,
                            "slope": round(support_trendline.slope, 6),
                        }
                    ]
                    if support_trendline is not None
                    else []
                ),
                *(
                    [
                        {
                            "type": "trendline",
                            "role": "resistance",
                            "start_time": resistance_trendline.start_ts,
                            "end_time": resistance_trendline.end_ts,
                            "slope": round(resistance_trendline.slope, 6),
                        }
                    ]
                    if resistance_trendline is not None
                    else []
                ),
                *pattern_structures,
                *(
                    [
                        {
                            "type": "volatility_squeeze",
                            "bb_width": round(squeeze.bb_width, 6)
                            if squeeze.bb_width is not None
                            else None,
                            "bb_width_percentile": round(squeeze.bb_width_percentile, 4),
                            "inside_keltner": squeeze.inside_keltner,
                            "score": round(squeeze.score, 4),
                        }
                    ]
                    if squeeze.score >= 0.6
                    else []
                ),
                *[
                    {
                        "type": "gap",
                        "role": gap.role,
                        "kind": gap.kind,
                        "price_low": round(gap.low, 4),
                        "price_high": round(gap.high, 4),
                        "start_time": gap.start_ts,
                    }
                    for gap in nearby_gaps
                ],
            ],
        }

        observed_at = latest_bar.ts if latest_bar.ts.tzinfo else latest_bar.ts.replace(tzinfo=UTC)
        fresh_until = observed_at
        context_at = _ts_to_datetime(zone.last_touch_ts)

        def append_candidate(
            setup_type: RadarSetupType,
            candidate_score: float,
            candidate_factors: dict,
            *,
            signal_ts: int,
        ) -> None:
            entry_price = _entry_price(setup_type, zone)
            invalidation_price = _invalidation_price(setup_type, zone)
            target_price, target_source = _nearest_target_price(
                setup_type,
                entry_price=entry_price,
                invalidation_price=invalidation_price,
                zone=zone,
                support_zones=support_zones,
                resistance_zones=resistance_zones,
            )
            state = _state_for_setup(setup_type)
            state_reason = _state_reason(setup_type, target_source=target_source)
            candidates.append(
                DetectionCandidate(
                    setup_type=setup_type,
                    state=state,
                    state_reason=state_reason,
                    score=candidate_score,
                    summary=_candidate_summary(
                        instrument.symbol, setup_type, zone, candidate_score
                    ),
                    invalidation_hint=_candidate_invalidation(setup_type, zone),
                    key_level_price=zone.center,
                    entry_price=entry_price,
                    invalidation_price=invalidation_price,
                    target_price=target_price,
                    score_factors=candidate_factors,
                    evidence=_candidate_evidence(
                        evidence,
                        setup_type,
                        zone,
                        timestamps,
                        latest_ts,
                        state=state,
                        state_reason=state_reason,
                        entry_price=entry_price,
                        invalidation_price=invalidation_price,
                        target_price=target_price,
                        target_source=target_source,
                        signal_ts=signal_ts,
                    ),
                    observed_at=observed_at,
                    signal_at=_ts_to_datetime(signal_ts) or observed_at,
                    context_at=context_at,
                    fresh_until=fresh_until,
                    context_role=zone.role,
                )
            )

        if zone.role == "support" and 0 <= close - zone.center <= proximity:
            append_candidate(
                RadarSetupType.APPROACHING_SUPPORT,
                score,
                score_factors,
                signal_ts=zone.last_touch_ts,
            )

        if zone.role == "resistance" and 0 <= zone.center - close <= proximity:
            append_candidate(
                RadarSetupType.APPROACHING_RESISTANCE,
                score,
                score_factors,
                signal_ts=zone.last_touch_ts,
            )

        recent_high = max(highs[max(0, latest_index - 4) : latest_index + 1])
        recent_low = min(lows[max(0, latest_index - 4) : latest_index + 1])
        recent_range = recent_high - recent_low
        if (
            zone.role == "support"
            and recent_range <= atr * 0.85
            and abs(close - zone.center) <= proximity * 0.6
            and squeeze.score >= 0.6
        ):
            compression_factors = dict(score_factors)
            compression_factors["normalized_score"] = round(
                _clamp(score + 0.04 + squeeze.score * 0.04), 4
            )
            append_candidate(
                RadarSetupType.COMPRESSION_SUPPORT,
                float(compression_factors["normalized_score"]),
                compression_factors,
                signal_ts=latest_ts,
            )

        if (
            zone.role == "resistance"
            and recent_range <= atr * 0.85
            and abs(close - zone.center) <= proximity * 0.6
            and squeeze.score >= 0.6
        ):
            compression_factors = dict(score_factors)
            compression_factors["normalized_score"] = round(
                _clamp(score + 0.04 + squeeze.score * 0.04), 4
            )
            append_candidate(
                RadarSetupType.COMPRESSION_RESISTANCE,
                float(compression_factors["normalized_score"]),
                compression_factors,
                signal_ts=latest_ts,
            )

        if zone.role == "resistance" and prev_close <= zone.high and close > zone.high:
            breakout_factors = dict(score_factors)
            breakout_factors["normalized_score"] = round(_clamp(score + 0.08), 4)
            append_candidate(
                RadarSetupType.BREAKOUT,
                float(breakout_factors["normalized_score"]),
                breakout_factors,
                signal_ts=latest_ts,
            )

        if zone.role == "support" and prev_close >= zone.low and close < zone.low:
            breakdown_factors = dict(score_factors)
            breakdown_factors["normalized_score"] = round(_clamp(score + 0.08), 4)
            append_candidate(
                RadarSetupType.BREAKDOWN,
                float(breakdown_factors["normalized_score"]),
                breakdown_factors,
                signal_ts=latest_ts,
            )

        if zone.role == "support" and float(prev_bar.low) < zone.low and close > zone.high:
            reclaim_factors = dict(score_factors)
            reclaim_factors["normalized_score"] = round(_clamp(score + 0.06), 4)
            append_candidate(
                RadarSetupType.RECLAIM,
                float(reclaim_factors["normalized_score"]),
                reclaim_factors,
                signal_ts=latest_ts,
            )

        if zone.role == "resistance" and float(latest_bar.high) > zone.high and close < zone.center:
            rejection_factors = dict(score_factors)
            rejection_factors["normalized_score"] = round(_clamp(score + 0.05), 4)
            append_candidate(
                RadarSetupType.REJECTION,
                float(rejection_factors["normalized_score"]),
                rejection_factors,
                signal_ts=latest_ts,
            )

        if zone.role == "resistance" and float(latest_bar.high) > zone.high and close < zone.high:
            fakeout_factors = dict(score_factors)
            fakeout_factors["normalized_score"] = round(_clamp(score + 0.09), 4)
            append_candidate(
                RadarSetupType.FAKEOUT,
                float(fakeout_factors["normalized_score"]),
                fakeout_factors,
                signal_ts=latest_ts,
            )

        if zone.role == "support" and float(latest_bar.low) < zone.low and close > zone.low:
            fakedown_factors = dict(score_factors)
            fakedown_factors["normalized_score"] = round(_clamp(score + 0.09), 4)
            append_candidate(
                RadarSetupType.FAKEDOWN,
                float(fakedown_factors["normalized_score"]),
                fakedown_factors,
                signal_ts=latest_ts,
            )

        if (
            zone.role == "resistance"
            and prev_close > zone.high
            and float(latest_bar.low) <= zone.high
            and close > zone.high
        ):
            retest_factors = dict(score_factors)
            retest_factors["normalized_score"] = round(_clamp(score + 0.1), 4)
            append_candidate(
                RadarSetupType.BREAKOUT_RETEST,
                float(retest_factors["normalized_score"]),
                retest_factors,
                signal_ts=latest_ts,
            )

        if zone.role == "support" and prev_close > zone.high and close < zone.low:
            failed_reclaim_factors = dict(score_factors)
            failed_reclaim_factors["normalized_score"] = round(_clamp(score + 0.1), 4)
            append_candidate(
                RadarSetupType.FAILED_RECLAIM,
                float(failed_reclaim_factors["normalized_score"]),
                failed_reclaim_factors,
                signal_ts=latest_ts,
            )

        if (
            zone.role == "support"
            and prev_close < zone.low
            and float(prev_bar.high) >= zone.low
            and close < zone.low
            and float(latest_bar.low) < float(prev_bar.low)
        ):
            failed_recovery_factors = dict(score_factors)
            failed_recovery_factors["normalized_score"] = round(_clamp(score + 0.08), 4)
            append_candidate(
                RadarSetupType.FAILED_BREAKDOWN_RECOVERY,
                float(failed_recovery_factors["normalized_score"]),
                failed_recovery_factors,
                signal_ts=latest_ts,
            )

        if (
            zone.role == "support"
            and prev_close < zone.low
            and float(latest_bar.high) >= zone.low
            and close < zone.low
        ):
            retest_factors = dict(score_factors)
            retest_factors["normalized_score"] = round(_clamp(score + 0.1), 4)
            append_candidate(
                RadarSetupType.BREAKDOWN_RETEST,
                float(retest_factors["normalized_score"]),
                retest_factors,
                signal_ts=latest_ts,
            )

    best_by_type: dict[RadarSetupType, DetectionCandidate] = {}
    for candidate in candidates:
        current = best_by_type.get(candidate.setup_type)
        if current is None or candidate.score > current.score:
            best_by_type[candidate.setup_type] = candidate
    return sorted(best_by_type.values(), key=lambda candidate: candidate.score, reverse=True)


async def run_radar_scan(
    db: AsyncSession,
    timeframe: Timeframe = Timeframe.D1,
    universe_type: str = "all",
    universe_filter: dict | None = None,
    user_id: int | None = None,
) -> RadarRun:
    run = RadarRun(
        timeframe=timeframe,
        universe_type=universe_type,
        universe_filter=universe_filter,
        status=RadarRunStatus.RUNNING,
        started_at=datetime.now(UTC),
    )
    db.add(run)
    await db.flush()

    try:
        instrument_stmt = (
            select(Instrument)
            .where(Instrument.is_active.is_(True), Instrument.is_synthetic.is_(False))
            .options(selectinload(Instrument.instrument_type))
            .order_by(Instrument.symbol)
        )
        if universe_type == "custom":
            instrument_ids = list((universe_filter or {}).get("instrument_ids") or [])
            instrument_stmt = instrument_stmt.where(Instrument.id.in_(instrument_ids or [-1]))
        elif universe_type == "basket":
            basket_id = (universe_filter or {}).get("basket_id")
            basket_member_ids = (
                select(BasketMember.instrument_id)
                .join(Basket, Basket.id == BasketMember.basket_id)
                .where(Basket.id == basket_id)
            )
            if user_id is not None:
                basket_member_ids = basket_member_ids.where(
                    (Basket.user_id == user_id) | (Basket.is_system_managed.is_(True))
                )
            else:
                basket_member_ids = basket_member_ids.where(Basket.is_system_managed.is_(True))
            instrument_stmt = instrument_stmt.where(Instrument.id.in_(basket_member_ids))

        instruments = list((await db.execute(instrument_stmt)).scalars().all())

        detections: list[RadarDetection] = []
        evaluated = 0
        for instrument in instruments:
            bars = await _load_bars(db, instrument.id, timeframe)
            if not bars:
                continue
            evaluated += 1
            instrument_run_detections: list[RadarDetection] = []
            observed_at = bars[-1].ts if bars[-1].ts.tzinfo else bars[-1].ts.replace(tzinfo=UTC)
            latest_close = float(bars[-1].close)
            thread_rows = (
                (
                    await db.execute(
                        select(RadarSetupThread)
                        .where(
                            RadarSetupThread.instrument_id == instrument.id,
                            RadarSetupThread.timeframe == timeframe,
                        )
                        .options(selectinload(RadarSetupThread.detections))
                        .order_by(
                            RadarSetupThread.last_seen_at.desc(),
                            RadarSetupThread.id.desc(),
                        )
                    )
                )
                .scalars()
                .all()
            )
            instrument_threads = list(thread_rows)
            matched_thread_ids: set[int] = set()
            for candidate in sorted(analyze_instrument(instrument, bars), key=_candidate_sort_key):
                thread = _find_matching_thread(candidate, instrument_threads)
                if thread is None:
                    thread = RadarSetupThread(
                        instrument_id=instrument.id,
                        timeframe=timeframe,
                        context_role=candidate.context_role,
                        reference_price=candidate.key_level_price,
                        current_setup_type=candidate.setup_type,
                        current_state=candidate.state,
                        state_changed_at=candidate.signal_at,
                        started_at=candidate.signal_at,
                        last_seen_at=candidate.signal_at,
                        detection_count=0,
                    )
                    db.add(thread)
                    instrument_threads.append(thread)
                if thread.id is not None:
                    matched_thread_ids.add(thread.id)
                duplicate_detection = _find_duplicate_thread_detection(candidate, thread)
                if duplicate_detection is not None:
                    thread_event_index = (
                        duplicate_detection.thread_event_index or thread.detection_count
                    )
                    thread.last_seen_at = max(thread.last_seen_at, candidate.signal_at)
                    thread.current_setup_type = candidate.setup_type
                    thread.current_state = candidate.state
                    thread.state_changed_at = candidate.signal_at
                    _refresh_duplicate_detection(
                        duplicate_detection,
                        candidate,
                        run_id=run.id,
                        thread=thread,
                        thread_event_index=thread_event_index,
                    )
                    detection = duplicate_detection
                else:
                    thread_event_index = _apply_candidate_to_thread(candidate, thread)
                    detection = RadarDetection(
                        run_id=run.id,
                        instrument_id=instrument.id,
                        thread=thread,
                        timeframe=timeframe,
                        setup_type=candidate.setup_type,
                        score=candidate.score,
                        observed_at=candidate.observed_at,
                        signal_at=candidate.signal_at,
                        context_at=candidate.context_at,
                        state=candidate.state,
                        state_reason=candidate.state_reason,
                        fresh_until=candidate.fresh_until,
                        thread_event_index=thread_event_index,
                        key_level_price=candidate.key_level_price,
                        entry_price=candidate.entry_price,
                        invalidation_price=candidate.invalidation_price,
                        target_price=candidate.target_price,
                        summary=candidate.summary,
                        invalidation_hint=candidate.invalidation_hint,
                        evidence_json=candidate.evidence,
                        score_factors=candidate.score_factors,
                    )
                    db.add(detection)
                detections.append(detection)
                instrument_run_detections.append(detection)

            for thread in instrument_threads:
                for persisted_detection in thread.detections or []:
                    _evaluate_detection_outcome(persisted_detection, bars, thread=thread)

            for thread in instrument_threads:
                if thread.id is not None and thread.id in matched_thread_ids:
                    continue
                if thread.current_state in {
                    RadarState.INVALIDATED,
                    RadarState.RESOLVED,
                    RadarState.STALE,
                }:
                    continue
                previous_detection = _latest_thread_detection(thread)
                if previous_detection is None:
                    continue
                if _overlapping_current_run_detection(
                    thread,
                    previous_detection,
                    instrument_run_detections,
                ):
                    continue

                next_state: RadarState | None = None
                transition_time = observed_at
                transition_price = latest_close
                transition_reason: str | None = None
                transition_metrics: dict = {}
                transition_outcome = previous_detection.outcome_status

                if previous_detection.outcome_status == RadarOutcomeStatus.TARGET_HIT:
                    next_state = RadarState.RESOLVED
                    transition_time = previous_detection.target_hit_at or observed_at
                    transition_price = float(
                        previous_detection.target_price
                        or previous_detection.key_level_price
                        or latest_close
                    )
                    transition_reason = _state_transition_reason(
                        previous_detection, next_state, transition_price
                    )
                elif previous_detection.outcome_status == RadarOutcomeStatus.INVALIDATED:
                    next_state = RadarState.INVALIDATED
                    transition_time = previous_detection.invalidated_at or observed_at
                    transition_reason = _state_transition_reason(
                        previous_detection, next_state, latest_close
                    )
                else:
                    stale_assessment = _assess_detection_staleness(
                        previous_detection,
                        bars,
                        thread=thread,
                    )
                    if stale_assessment.is_stale:
                        next_state = RadarState.STALE
                        transition_time = stale_assessment.stale_at or observed_at
                        transition_reason = stale_assessment.reason or _state_transition_reason(
                            previous_detection,
                            RadarState.STALE,
                            latest_close,
                        )
                        transition_metrics = stale_assessment.metrics
                        transition_outcome = RadarOutcomeStatus.STALE

                if next_state is None or transition_reason is None:
                    continue

                transition_marker_ts = int(transition_time.timestamp())
                transition_marker_color = (
                    "#56c596"
                    if next_state == RadarState.RESOLVED
                    else "#ef5350"
                    if next_state == RadarState.INVALIDATED
                    else "#94a1b2"
                )
                transition_metrics_payload = {
                    **(previous_detection.evidence_json or {}).get("metrics", {}),
                    "state": next_state.value,
                    "state_reason": transition_reason,
                    "outcome_status": transition_outcome.value,
                    **transition_metrics,
                }
                transition_candidate = DetectionCandidate(
                    setup_type=previous_detection.setup_type,
                    state=next_state,
                    state_reason=transition_reason,
                    score=float(previous_detection.score),
                    summary=_state_transition_summary(
                        instrument.symbol,
                        previous_detection,
                        next_state,
                    ),
                    invalidation_hint=previous_detection.invalidation_hint or "",
                    key_level_price=float(
                        previous_detection.key_level_price or thread.reference_price
                    ),
                    entry_price=float(previous_detection.entry_price or thread.reference_price),
                    invalidation_price=float(
                        previous_detection.invalidation_price or thread.reference_price
                    ),
                    target_price=float(previous_detection.target_price or thread.reference_price),
                    score_factors=dict(previous_detection.score_factors or {}),
                    evidence={
                        **(previous_detection.evidence_json or {}),
                        "metrics": transition_metrics_payload,
                        "overlays": [],
                        "drawing_visuals": [
                            *((previous_detection.evidence_json or {}).get("drawing_visuals", [])),
                            _make_marker(
                                transition_marker_ts,
                                transition_price,
                                next_state.value.replace("_", " "),
                                transition_marker_color,
                                f"state_{next_state.value}",
                            ),
                        ],
                    },
                    observed_at=transition_time,
                    signal_at=transition_time,
                    context_at=previous_detection.context_at,
                    fresh_until=transition_time,
                    context_role=thread.context_role,
                )
                thread_event_index = _apply_candidate_to_thread(transition_candidate, thread)
                transition_detection = RadarDetection(
                    run_id=run.id,
                    instrument_id=instrument.id,
                    thread=thread,
                    timeframe=timeframe,
                    setup_type=previous_detection.setup_type,
                    score=float(previous_detection.score),
                    observed_at=transition_time,
                    signal_at=transition_time,
                    context_at=previous_detection.context_at,
                    state=next_state,
                    state_reason=transition_reason,
                    fresh_until=transition_time,
                    thread_event_index=thread_event_index,
                    key_level_price=float(
                        previous_detection.key_level_price or thread.reference_price
                    ),
                    entry_price=float(previous_detection.entry_price or thread.reference_price),
                    invalidation_price=float(
                        previous_detection.invalidation_price or thread.reference_price
                    ),
                    target_price=float(previous_detection.target_price or thread.reference_price),
                    outcome_status=transition_outcome,
                    outcome_last_evaluated_at=transition_time,
                    bars_since_signal=previous_detection.bars_since_signal,
                    max_favorable_excursion_pct=previous_detection.max_favorable_excursion_pct,
                    max_adverse_excursion_pct=previous_detection.max_adverse_excursion_pct,
                    target_hit_at=previous_detection.target_hit_at
                    if transition_outcome == RadarOutcomeStatus.TARGET_HIT
                    else None,
                    invalidated_at=previous_detection.invalidated_at
                    if transition_outcome == RadarOutcomeStatus.INVALIDATED
                    else None,
                    summary=_state_transition_summary(
                        instrument.symbol,
                        previous_detection,
                        next_state,
                    ),
                    invalidation_hint=previous_detection.invalidation_hint,
                    evidence_json=transition_candidate.evidence,
                    score_factors=dict(previous_detection.score_factors or {}),
                )
                db.add(transition_detection)
                detections.append(transition_detection)

            for thread in instrument_threads:
                for persisted_detection in thread.detections or []:
                    _evaluate_detection_outcome(persisted_detection, bars, thread=thread)

        run.status = RadarRunStatus.COMPLETED
        run.completed_at = datetime.now(UTC)
        run.evaluated_count = evaluated
        run.detection_count = len(detections)
        await db.commit()
        await db.refresh(run)
        return run
    except Exception as exc:
        run.status = RadarRunStatus.FAILED
        run.completed_at = datetime.now(UTC)
        run.error_summary = str(exc)
        await db.commit()
        raise


async def latest_run(db: AsyncSession, timeframe: Timeframe | None = None) -> RadarRun | None:
    stmt = select(RadarRun).where(RadarRun.status == RadarRunStatus.COMPLETED)
    if timeframe is not None:
        stmt = stmt.where(RadarRun.timeframe == timeframe)
    return (
        (await db.execute(stmt.order_by(RadarRun.completed_at.desc(), RadarRun.id.desc()).limit(1)))
        .scalars()
        .first()
    )


async def get_detection_with_instrument(
    db: AsyncSession, detection_id: int
) -> RadarDetection | None:
    return (
        (
            await db.execute(
                select(RadarDetection)
                .where(RadarDetection.id == detection_id)
                .options(
                    selectinload(RadarDetection.instrument),
                    selectinload(RadarDetection.run),
                    selectinload(RadarDetection.thread).selectinload(RadarSetupThread.detections),
                )
            )
        )
        .scalars()
        .first()
    )
