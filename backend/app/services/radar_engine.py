import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.radar import RadarDetection, RadarRun, RadarRunStatus, RadarSetupType
from app.services.indicators import OHLCVSeries, compute_indicator

RADAR_LOOKBACK_BARS = 320
EMA_PERIODS = (20, 50, 200)
SWING_WINDOW = 3
MIN_ZONE_TOUCHES = 2
MAX_ZONES_PER_SIDE = 3
LINE_SAMPLE_POINTS = 120


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
    score: float
    summary: str
    invalidation_hint: str
    key_level_price: float
    score_factors: dict
    evidence: dict
    observed_at: datetime
    fresh_until: datetime


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


def _series_points(data: OHLCVSeries, values: list[float | None], color: str, label: str) -> dict:
    pairs = [
        {"time": int(ts), "price": float(val)}
        for ts, val in zip(data.timestamps.tolist(), values, strict=False)
        if val is not None and not math.isnan(val)
    ]
    if len(pairs) > LINE_SAMPLE_POINTS:
        last_pair = pairs[-1]
        step = max(1, len(pairs) // LINE_SAMPLE_POINTS)
        pairs = pairs[::step]
        if pairs[-1] != last_pair:
            pairs.append(last_pair)
    return {"kind": "line", "label": label, "color": color, "points": pairs}


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
    overlays: list[dict] = []
    colors = {20: "#6ec6ff", 50: "#ffd166", 200: "#f4978e"}
    for period in EMA_PERIODS:
        series = compute_indicator("ema", data, {"period": period})["ema"].tolist()
        latest = _latest_valid(series)
        if latest is None:
            continue
        levels[f"ema_{period}"] = latest
        overlays.append(
            _series_points(
                data,
                [None if math.isnan(v) else float(v) for v in series],
                colors[period],
                f"EMA {period}",
            )
        )
    return levels, overlays


def _atr_latest(data: OHLCVSeries) -> float | None:
    series = compute_indicator("atr", data, {"period": 14})["atr"].tolist()
    return _latest_valid(series)


def _avwap_from_anchor(data: OHLCVSeries, anchor_ts: int) -> tuple[float | None, dict | None]:
    if anchor_ts <= 0:
        return None, None
    values = compute_indicator("avwap", data, {"anchor_timestamp": anchor_ts})["avwap"].tolist()
    latest = _latest_valid(values)
    if latest is None:
        return None, None
    overlay = _series_points(
        data,
        [None if math.isnan(v) else float(v) for v in values],
        "#c77dff",
        "AVWAP",
    )
    overlay["role"] = "avwap"
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
    total = (
        distance_score * 0.28
        + touch_score * 0.18
        + recency_score * 0.16
        + age_score * 0.08
        + confluence_score * 0.18
        + reaction_quality * 0.12
        + timeframe_score * 0.10
    )
    return {
        "distance_to_level": round(distance_score, 4),
        "touch_count": round(touch_score, 4),
        "recency": round(recency_score, 4),
        "structure_age": round(age_score, 4),
        "overlap_confluence": round(confluence_score, 4),
        "recent_reaction_quality": round(reaction_quality, 4),
        "timeframe_importance": round(timeframe_score, 4),
        "normalized_score": round(_clamp(total), 4),
    }


def _make_zone_overlay(zone: Zone, timestamps: list[int], latest_ts: int, color: str) -> dict:
    return {
        "kind": "zone",
        "role": zone.role,
        "label": f"{zone.role.title()} zone",
        "color": color,
        "start_time": timestamps[max(0, zone.first_touch_index - 3)],
        "end_time": latest_ts,
        "price_low": round(zone.low, 4),
        "price_high": round(zone.high, 4),
    }


def _make_marker(ts: int, price: float, label: str, color: str, role: str) -> dict:
    return {
        "kind": "marker",
        "role": role,
        "label": label,
        "color": color,
        "time": ts,
        "price": round(price, 4),
    }


def _week52_levels(closes: list[float], highs: list[float], lows: list[float]) -> dict[str, float]:
    window = 252 if len(closes) >= 252 else len(closes)
    if window <= 0:
        return {}
    return {
        "week52_high": max(highs[-window:]),
        "week52_low": min(lows[-window:]),
    }


def _candidate_summary(symbol: str, setup_type: RadarSetupType, zone: Zone, score: float) -> str:
    label = setup_type.value.replace("_", " ")
    return (
        f"{symbol} is showing a {label} setup around {zone.center:.2f} "
        f"with {zone.touch_count} swing touches and a radar score of {score:.2f}."
    )


def _candidate_invalidation(setup_type: RadarSetupType, zone: Zone) -> str:
    if setup_type in {RadarSetupType.APPROACHING_SUPPORT, RadarSetupType.RECLAIM}:
        return f"Invalidate on a decisive close back below {zone.low:.2f}."
    if setup_type in {RadarSetupType.APPROACHING_RESISTANCE, RadarSetupType.REJECTION}:
        return f"Invalidate on a decisive close above {zone.high:.2f}."
    if setup_type == RadarSetupType.BREAKOUT:
        return f"Invalidate if price falls back below {zone.low:.2f}."
    return f"Invalidate if price reclaims {zone.high:.2f}."


def _invalidation_price(setup_type: RadarSetupType, zone: Zone) -> float:
    if setup_type in {RadarSetupType.APPROACHING_SUPPORT, RadarSetupType.RECLAIM, RadarSetupType.BREAKOUT}:
        return round(zone.low, 4)
    return round(zone.high, 4)


def _make_invalidation_overlay(inv_price: float, timestamps: list[int], latest_ts: int) -> dict:
    return {
        "kind": "line",
        "role": "invalidation",
        "label": "Invalidation",
        "color": "#ef5350",
        "dash_pattern": [6, 3],
        "points": [
            {"time": timestamps[0], "price": inv_price},
            {"time": latest_ts, "price": inv_price},
        ],
    }


def _candidate_evidence(
    base: dict, setup_type: RadarSetupType, zone: Zone, timestamps: list[int], latest_ts: int
) -> dict:
    inv_price = _invalidation_price(setup_type, zone)
    return {
        **base,
        "overlays": [*base["overlays"], _make_invalidation_overlay(inv_price, timestamps, latest_ts)],
        "metrics": {**base["metrics"], "invalidation_price": inv_price},
    }


def analyze_instrument(instrument: Instrument, bars: list[OHLCVBar]) -> list[DetectionCandidate]:
    if len(bars) < 80:
        return []

    data = OHLCVSeries.from_orm_bars(bars)
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
    week52 = _week52_levels(closes, highs, lows)

    candidates: list[DetectionCandidate] = []
    base_levels = list(ema_levels.values()) + list(week52.values())

    for zone in support_zones + resistance_zones:
        reaction_quality = _recent_reaction_quality(bars, zone)
        avwap_anchor = zone.pivots[-1].ts
        avwap_value, avwap_overlay = _avwap_from_anchor(data, avwap_anchor)
        confluence_levels = list(base_levels)
        if avwap_value is not None:
            confluence_levels.append(avwap_value)
        score_factors = _build_score(
            close, atr, zone, latest_index, confluence_levels, reaction_quality
        )
        score = float(score_factors["normalized_score"])

        overlays = [
            _make_zone_overlay(
                zone, timestamps, latest_ts, "#2ec4b6" if zone.role == "support" else "#ff9f1c"
            ),
            _make_marker(latest_ts, close, "Current", "#ffffff", "price"),
        ]
        overlays.extend(ema_overlays)
        if avwap_overlay is not None:
            overlays.append(avwap_overlay)
        if "week52_high" in week52:
            overlays.append(
                {
                    "kind": "line",
                    "role": "week52_high",
                    "label": "52W High",
                    "color": "#8ecae6",
                    "points": [
                        {"time": timestamps[0], "price": round(week52["week52_high"], 4)},
                        {"time": latest_ts, "price": round(week52["week52_high"], 4)},
                    ],
                }
            )
        if "week52_low" in week52:
            overlays.append(
                {
                    "kind": "line",
                    "role": "week52_low",
                    "label": "52W Low",
                    "color": "#8ecae6",
                    "points": [
                        {"time": timestamps[0], "price": round(week52["week52_low"], 4)},
                        {"time": latest_ts, "price": round(week52["week52_low"], 4)},
                    ],
                }
            )

        evidence = {
            "overlays": overlays,
            "metrics": {
                "close": round(close, 4),
                "atr_14": round(atr, 4),
                "zone_center": round(zone.center, 4),
                "distance_to_zone": round(abs(close - zone.center), 4),
                "ema_levels": {k: round(v, 4) for k, v in ema_levels.items()},
                "avwap": round(avwap_value, 4) if avwap_value is not None else None,
                **{k: round(v, 4) for k, v in week52.items()},
            },
            "structures": [
                {
                    "type": "horizontal_zone",
                    "role": zone.role,
                    "touch_count": zone.touch_count,
                    "first_touch_time": timestamps[zone.first_touch_index],
                    "last_touch_time": zone.last_touch_ts,
                }
            ],
        }

        observed_at = latest_bar.ts if latest_bar.ts.tzinfo else latest_bar.ts.replace(tzinfo=UTC)
        fresh_until = observed_at + timedelta(days=5)

        if zone.role == "support" and 0 <= close - zone.center <= proximity:
            candidates.append(
                DetectionCandidate(
                    setup_type=RadarSetupType.APPROACHING_SUPPORT,
                    score=score,
                    summary=_candidate_summary(
                        instrument.symbol, RadarSetupType.APPROACHING_SUPPORT, zone, score
                    ),
                    invalidation_hint=_candidate_invalidation(
                        RadarSetupType.APPROACHING_SUPPORT, zone
                    ),
                    key_level_price=zone.center,
                    score_factors=score_factors,
                    evidence=_candidate_evidence(evidence, RadarSetupType.APPROACHING_SUPPORT, zone, timestamps, latest_ts),
                    observed_at=observed_at,
                    fresh_until=fresh_until,
                )
            )

        if zone.role == "resistance" and 0 <= zone.center - close <= proximity:
            candidates.append(
                DetectionCandidate(
                    setup_type=RadarSetupType.APPROACHING_RESISTANCE,
                    score=score,
                    summary=_candidate_summary(
                        instrument.symbol, RadarSetupType.APPROACHING_RESISTANCE, zone, score
                    ),
                    invalidation_hint=_candidate_invalidation(
                        RadarSetupType.APPROACHING_RESISTANCE, zone
                    ),
                    key_level_price=zone.center,
                    score_factors=score_factors,
                    evidence=_candidate_evidence(evidence, RadarSetupType.APPROACHING_RESISTANCE, zone, timestamps, latest_ts),
                    observed_at=observed_at,
                    fresh_until=fresh_until,
                )
            )

        if zone.role == "resistance" and prev_close <= zone.high and close > zone.high:
            breakout_factors = dict(score_factors)
            breakout_factors["normalized_score"] = round(_clamp(score + 0.08), 4)
            candidates.append(
                DetectionCandidate(
                    setup_type=RadarSetupType.BREAKOUT,
                    score=float(breakout_factors["normalized_score"]),
                    summary=_candidate_summary(
                        instrument.symbol,
                        RadarSetupType.BREAKOUT,
                        zone,
                        float(breakout_factors["normalized_score"]),
                    ),
                    invalidation_hint=_candidate_invalidation(RadarSetupType.BREAKOUT, zone),
                    key_level_price=zone.center,
                    score_factors=breakout_factors,
                    evidence=_candidate_evidence(evidence, RadarSetupType.BREAKOUT, zone, timestamps, latest_ts),
                    observed_at=observed_at,
                    fresh_until=fresh_until,
                )
            )

        if zone.role == "support" and prev_close >= zone.low and close < zone.low:
            breakdown_factors = dict(score_factors)
            breakdown_factors["normalized_score"] = round(_clamp(score + 0.08), 4)
            candidates.append(
                DetectionCandidate(
                    setup_type=RadarSetupType.BREAKDOWN,
                    score=float(breakdown_factors["normalized_score"]),
                    summary=_candidate_summary(
                        instrument.symbol,
                        RadarSetupType.BREAKDOWN,
                        zone,
                        float(breakdown_factors["normalized_score"]),
                    ),
                    invalidation_hint=_candidate_invalidation(RadarSetupType.BREAKDOWN, zone),
                    key_level_price=zone.center,
                    score_factors=breakdown_factors,
                    evidence=_candidate_evidence(evidence, RadarSetupType.BREAKDOWN, zone, timestamps, latest_ts),
                    observed_at=observed_at,
                    fresh_until=fresh_until,
                )
            )

        if zone.role == "support" and float(prev_bar.low) < zone.low and close > zone.high:
            reclaim_factors = dict(score_factors)
            reclaim_factors["normalized_score"] = round(_clamp(score + 0.06), 4)
            candidates.append(
                DetectionCandidate(
                    setup_type=RadarSetupType.RECLAIM,
                    score=float(reclaim_factors["normalized_score"]),
                    summary=_candidate_summary(
                        instrument.symbol,
                        RadarSetupType.RECLAIM,
                        zone,
                        float(reclaim_factors["normalized_score"]),
                    ),
                    invalidation_hint=_candidate_invalidation(RadarSetupType.RECLAIM, zone),
                    key_level_price=zone.center,
                    score_factors=reclaim_factors,
                    evidence=_candidate_evidence(evidence, RadarSetupType.RECLAIM, zone, timestamps, latest_ts),
                    observed_at=observed_at,
                    fresh_until=fresh_until,
                )
            )

        if zone.role == "resistance" and float(latest_bar.high) > zone.high and close < zone.center:
            rejection_factors = dict(score_factors)
            rejection_factors["normalized_score"] = round(_clamp(score + 0.05), 4)
            candidates.append(
                DetectionCandidate(
                    setup_type=RadarSetupType.REJECTION,
                    score=float(rejection_factors["normalized_score"]),
                    summary=_candidate_summary(
                        instrument.symbol,
                        RadarSetupType.REJECTION,
                        zone,
                        float(rejection_factors["normalized_score"]),
                    ),
                    invalidation_hint=_candidate_invalidation(RadarSetupType.REJECTION, zone),
                    key_level_price=zone.center,
                    score_factors=rejection_factors,
                    evidence=_candidate_evidence(evidence, RadarSetupType.REJECTION, zone, timestamps, latest_ts),
                    observed_at=observed_at,
                    fresh_until=fresh_until,
                )
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
        instruments = (
            (
                await db.execute(
                    select(Instrument)
                    .where(Instrument.is_active.is_(True), Instrument.is_synthetic.is_(False))
                    .options(selectinload(Instrument.instrument_type))
                    .order_by(Instrument.symbol)
                )
            )
            .scalars()
            .all()
        )

        detections: list[RadarDetection] = []
        evaluated = 0
        for instrument in instruments:
            bars = await _load_bars(db, instrument.id, timeframe)
            if not bars:
                continue
            evaluated += 1
            for candidate in analyze_instrument(instrument, bars):
                detections.append(
                    RadarDetection(
                        run_id=run.id,
                        instrument_id=instrument.id,
                        timeframe=timeframe,
                        setup_type=candidate.setup_type,
                        score=candidate.score,
                        observed_at=candidate.observed_at,
                        fresh_until=candidate.fresh_until,
                        key_level_price=candidate.key_level_price,
                        summary=candidate.summary,
                        invalidation_hint=candidate.invalidation_hint,
                        evidence_json=candidate.evidence,
                        score_factors=candidate.score_factors,
                    )
                )

        db.add_all(detections)
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


async def latest_run(db: AsyncSession) -> RadarRun | None:
    return (
        (
            await db.execute(
                select(RadarRun)
                .where(RadarRun.status == RadarRunStatus.COMPLETED)
                .order_by(RadarRun.completed_at.desc(), RadarRun.id.desc())
                .limit(1)
            )
        )
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
                .options(selectinload(RadarDetection.instrument), selectinload(RadarDetection.run))
            )
        )
        .scalars()
        .first()
    )
