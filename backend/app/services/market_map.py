"""Batch calculations for arbitrary locked or user-owned watchlist sources."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.instrument import Instrument
from app.models.instrument_event import InstrumentEvent, InstrumentEventFetchState
from app.models.market_map import MarketMapCache
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.research import ResearchRun
from app.schemas.market_map import (
    MarketMapCell,
    MarketMapNode,
    MarketMapOut,
    MarketMapRequest,
    MarketMapWarning,
)
from app.services.breadth import (
    BreadthMember,
    build_equal_reference_series,
    evaluate_condition,
    evaluate_cross_sectional_percentile,
)
from app.services.watchlist_sources import resolve_watchlist_source

_OFFSETS = {"1D": 1, "1W": 5, "1M": 21, "3M": 63, "6M": 126, "1Y": 252}


def _warning(code: str, message: str, instrument_id: int | None = None, node_id: str | None = None):
    return MarketMapWarning(code=code, message=message, instrument_id=instrument_id, node_id=node_id)


def _period_bounds(request: MarketMapRequest, latest: datetime) -> tuple[datetime | None, datetime]:
    period = request.period.upper()
    end = min(item for item in (request.end, request.as_of, latest) if item is not None)
    if period == "CUSTOM":
        return request.start, end
    if period in {"YTD", "MTD"}:
        if period == "MTD":
            return datetime(end.year, end.month, 1, tzinfo=end.tzinfo or UTC), end
        return datetime(end.year, 1, 1, tzinfo=end.tzinfo or UTC), end
    offset = _OFFSETS.get(period)
    if offset is None:
        return None, end
    # Calendar subtraction is deliberately conservative; the exact base is the last
    # persisted session before the requested window, never a forward-filled value.
    days = {"1D": 7, "1W": 14, "1M": 45, "3M": 120, "6M": 240, "1Y": 450}[period]
    return end - timedelta(days=days), end


def _return(bars: list[OHLCVBar], period: str, start: datetime | None, end: datetime):
    eligible = [bar for bar in bars if bar.ts <= end]
    if not eligible:
        return None, None, "no_bars", "No local bars are available."
    latest = eligible[-1]
    if period.upper() == "CUSTOM":
        base = next((bar for bar in reversed(eligible) if start is not None and bar.ts < start), None)
    elif period.upper() in {"YTD", "MTD"}:
        base_date = (
            (latest.ts.year, latest.ts.month)
            if period.upper() == "MTD"
            else (latest.ts.year, 1)
        )
        base = next(
            (
                bar
                for bar in eligible
                if (
                    (bar.ts.year, bar.ts.month)
                    if period.upper() == "MTD"
                    else (bar.ts.year, 1)
                )
                == base_date
            ),
            None,
        )
        if base is not None and base.ts == latest.ts:
            base = eligible[-2] if len(eligible) > 1 else None
    else:
        offset = _OFFSETS.get(period.upper(), 1)
        base = eligible[-offset - 1] if len(eligible) > offset else None
    if base is None:
        return None, latest.ts, "insufficient_history", f"{period} requires more aligned history."
    if not base.close:
        return None, latest.ts, "zero_base_price", "The base close is zero."
    return float(latest.close / base.close - 1), latest.ts, None, None


def _rsi(bars: list[OHLCVBar]):
    closes = [float(bar.close) for bar in bars]
    if len(closes) < 15:
        return None
    changes = [closes[i] - closes[i - 1] for i in range(len(closes) - 14, len(closes))]
    gain = sum(max(change, 0.0) for change in changes) / len(changes)
    loss = sum(max(-change, 0.0) for change in changes) / len(changes)
    return 100.0 if loss == 0 else 100.0 - 100.0 / (1.0 + gain / loss)


def _colour(
    request: MarketMapRequest,
    bars: list[OHLCVBar],
    return_value: float | None,
    *,
    reference_bars: list[OHLCVBar] | None = None,
    events: list[InstrumentEvent] | None = None,
) -> tuple[float | None, str | None, bool | None, float | None]:
    metric = request.color_metric
    if metric in {"return", "relative_return"}:
        return return_value, None, None, None
    if metric == "breadth":
        value, condition_metric, warning = evaluate_condition(
            bars,
            request.condition or {},
            benchmark_bars=reference_bars,
            events=events,
        )
        return (1.0 if value else -1.0) if value is not None else None, warning, value, condition_metric
    if not bars:
        return None, "no_bars", None, None
    latest = float(bars[-1].close)
    if metric == "rsi_14":
        return _rsi(bars), None if len(bars) >= 15 else "insufficient_history", None, None
    if metric == "relative_volume":
        values = [bar.volume for bar in bars[-51:]]
        if len(values) < 51 or any(value is None for value in values):
            return None, "insufficient_volume_history", None, None
        average = sum(float(value) for value in values[:-1]) / 50
        return (float(values[-1]) / average if average else None), None, None, None
    window = [float(bar.close) for bar in bars[-252:]]
    if len(window) < 252:
        return None, "insufficient_history", None, None
    if metric == "distance_52w_high":
        return latest / max(window) - 1, None, None, None
    return latest / min(window) - 1 if min(window) else None, None, None, None


def _group_path(request: MarketMapRequest, instrument: Instrument) -> list[str]:
    detail = instrument.equity_detail
    sector = (detail.sector if detail else None) or "Unclassified"
    industry = (detail.industry if detail else None) or "Unclassified"
    if request.group_by == "none":
        return []
    if request.group_by == "sector":
        return [sector]
    if request.group_by == "industry":
        return [industry]
    return [sector, industry]


def _condition_requires_events(condition: object) -> bool:
    if not isinstance(condition, dict):
        return False
    if str(condition.get("kind", "")).lower() == "event":
        return True
    params = condition.get("params")
    if not isinstance(params, dict):
        return False
    children = params.get("conditions")
    return isinstance(children, list) and any(_condition_requires_events(child) for child in children)


def _is_cross_sectional_condition(condition: object) -> bool:
    if not isinstance(condition, dict):
        return False
    params = condition.get("params")
    if not isinstance(params, dict):
        params = {}
    return str(condition.get("target_scope", params.get("target_scope", "member"))).lower() == "cross_sectional"


async def _events_by_instrument(
    db: AsyncSession,
    instrument_ids: list[int],
    period_end: datetime,
) -> tuple[dict[int, list[InstrumentEvent] | None], datetime | None]:
    """Read the local event calendar with the same loaded/unavailable semantics as breadth."""

    if not instrument_ids:
        return {}, None
    rows = (
        await db.execute(
            select(InstrumentEvent)
            .where(
                InstrumentEvent.instrument_id.in_(instrument_ids),
                InstrumentEvent.event_time <= period_end,
            )
            .order_by(InstrumentEvent.instrument_id, InstrumentEvent.event_time)
        )
    ).scalars().all()
    fetch_states = (
        (
            await db.execute(
                select(InstrumentEventFetchState).where(
                    InstrumentEventFetchState.instrument_id.in_(instrument_ids)
                )
            )
        ).scalars().all()
    )
    loaded_ids = {int(state.instrument_id) for state in fetch_states}
    events: dict[int, list[InstrumentEvent] | None] = {
        instrument_id: [] if instrument_id in loaded_ids else None
        for instrument_id in instrument_ids
    }
    for event in rows:
        events.setdefault(event.instrument_id, []).append(event)
    timestamps = [
        timestamp
        for timestamp in [
            *(getattr(event, "fetched_at", None) for event in rows),
            *(getattr(state, "fetched_at", None) for state in fetch_states),
        ]
        if isinstance(timestamp, datetime)
    ]
    return events, max(timestamps, default=None)


async def _python_colour_values(
    db: AsyncSession,
    user_id: int,
    run_id: int,
) -> tuple[dict[int, tuple[float | None, str | None, bool | None, float | None]], str]:
    """Read completed isolated batch cells for one user-owned Python run.

    Python is never executed by the Market Map request. The run must already be
    completed by the dedicated research worker; this method only consumes its
    immutable artifact and preserves per-cell failures as explicit warnings.
    """

    run = (
        await db.execute(
            select(ResearchRun)
            .options(selectinload(ResearchRun.artifacts))
            .where(ResearchRun.id == run_id, ResearchRun.user_id == user_id)
        )
    ).scalar_one_or_none()
    if run is None:
        raise ValueError("python_run_not_found")
    if run.status != "completed":
        raise ValueError("python_run_not_completed")
    config = run.run_config if isinstance(run.run_config, dict) else {}
    output_contract = str(config.get("output_contract") or "series")
    artifact = next(
        (item for item in run.artifacts if item.name == "batch_cells" and isinstance(item.payload, dict)),
        None,
    )
    if artifact is None or not isinstance(artifact.payload.get("value"), dict):
        raise ValueError("python_run_artifact_unavailable")
    raw_cells = artifact.payload["value"].get("cells")
    if not isinstance(raw_cells, list):
        raise ValueError("python_run_artifact_unavailable")
    values: dict[int, tuple[float | None, str | None, bool | None, float | None]] = {}
    for raw in raw_cells:
        if not isinstance(raw, dict) or not isinstance(raw.get("instrument_id"), int):
            continue
        instrument_id = raw["instrument_id"]
        if raw.get("status") != "completed":
            values[instrument_id] = (None, "python_cell_failed", None, None)
            continue
        value = raw.get("value")
        metric = raw.get("metric")
        numeric_metric = (
            float(metric)
            if isinstance(metric, int | float) and not isinstance(metric, bool) and math.isfinite(float(metric))
            else None
        )
        if output_contract == "boolean":
            if not isinstance(value, bool):
                values[instrument_id] = (None, "python_boolean_invalid", None, numeric_metric)
                continue
            values[instrument_id] = (1.0 if value else -1.0, None, value, numeric_metric)
            continue
        numeric_value = (
            float(value)
            if isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(float(value))
            else numeric_metric
        )
        if numeric_value is None:
            values[instrument_id] = (None, "python_numeric_invalid", None, numeric_metric)
        else:
            values[instrument_id] = (numeric_value, None, None, numeric_value)
    return values, output_contract


def _node_metric(cells: list[MarketMapCell], area_metric: str) -> tuple[float | None, str]:
    values = [cell for cell in cells if cell.color_value is not None]
    if not values:
        return None, "unavailable_no_values"
    weighted = [cell for cell in values if cell.area_value is not None and cell.area_value > 0]
    if area_metric != "equal" and len(weighted) == len(values):
        total = sum(cell.area_value or 0 for cell in weighted)
        if total:
            return sum((cell.color_value or 0) * (cell.area_value or 0) for cell in weighted) / total, "area_weighted_mean"
    return sum(cell.color_value or 0 for cell in values) / len(values), "equal_mean"


def _numeric_area_field(
    instrument: Instrument,
    field: str | None,
) -> tuple[float | None, dict[str, object] | None, str | None]:
    """Read one allow-listed provider field without triggering a provider call."""

    if not field or instrument.stats is None:
        return None, None, "missing_area_field"
    value = getattr(instrument.stats, field, None)
    provenance = (instrument.stats.field_provenance or {}).get(field)
    provenance_value = provenance if isinstance(provenance, dict) else None
    if value is None:
        return None, provenance_value, "missing_area_field"
    if provenance_value is None:
        return None, None, "unproven_area_field"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None, provenance_value, "invalid_area_field"
    return numeric, provenance_value, None


def _cache_key(
    request: MarketMapRequest,
    membership_version: str | None,
    member_ids: list[int],
    bar_watermark: datetime | None,
    reference_watermark: datetime | None,
    event_watermark: datetime | None = None,
    reference_membership_version: str | None = None,
    reference_member_ids: list[int] | None = None,
) -> str:
    """Build a deterministic identity for one source/data snapshot.

    The source membership and local bar watermarks are deliberately part of the
    identity. A refreshed composition or newly ingested completed-session bar
    therefore cannot silently reuse an older map result.
    """

    payload = request.model_dump(mode="json") | {
        "calculation_version": "market-map-v1",
        "membership_version": membership_version,
        "member_ids": sorted(member_ids),
        "bar_watermark": bar_watermark.isoformat() if bar_watermark else None,
        "reference_bar_watermark": (
            reference_watermark.isoformat() if reference_watermark else None
        ),
        "event_watermark": event_watermark.isoformat() if event_watermark else None,
        "reference_membership_version": reference_membership_version,
        "reference_member_ids": sorted(reference_member_ids or []),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


async def read_market_map_cache(
    db: AsyncSession, user_id: int, cache_key: str
) -> MarketMapOut | None:
    """Read one user-isolated persisted map result without provider access."""

    cached = (
        await db.execute(
            select(MarketMapCache).where(
                MarketMapCache.user_id == user_id,
                MarketMapCache.cache_key == cache_key,
            )
        )
    ).scalar_one_or_none()
    if cached is None:
        return None
    cached.last_accessed_at = datetime.now(UTC)
    result = MarketMapOut.model_validate(cached.response_json)
    result.cache_hit = True
    result.cached_at = cached.computed_at
    return result


async def build_market_map(db: AsyncSession, user_id: int, request: MarketMapRequest) -> MarketMapOut:
    # Imported lazily to avoid the analysis router/service import cycle.  The
    # existing helper is intentionally reused so freshness semantics stay
    # identical across batch analysis surfaces.
    from app.routers.analysis import _batch_freshness

    try:
        resolved = await resolve_watchlist_source(db, user_id, request.source_id, as_of=request.as_of)
    except LookupError as exc:
        raise ValueError(str(exc)) from exc
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    members_by_id = {}
    for member in resolved.members:
        members_by_id.setdefault(member.instrument_id, member)
    member_ids = list(members_by_id)
    instruments = {
        instrument.id: instrument
        for instrument in (
            await db.execute(
                select(Instrument)
                .where(Instrument.id.in_(member_ids))
                .options(selectinload(Instrument.equity_detail), selectinload(Instrument.stats))
            )
        ).scalars()
    }
    missing_ids = set(member_ids) - set(instruments)
    exclusions = [
        _warning("missing_instrument", "Membership refers to an unavailable canonical instrument.", instrument_id=item)
        for item in sorted(missing_ids)
    ]
    end_hint = request.end or request.as_of or datetime.now(UTC)
    history_start = (request.start or end_hint) - timedelta(days=500)
    try:
        timeframe = Timeframe(request.timeframe)
    except ValueError as exc:
        raise ValueError("invalid_timeframe") from exc
    bars = (
        await db.execute(
            select(OHLCVBar)
            .where(
                OHLCVBar.instrument_id.in_(member_ids),
                OHLCVBar.timeframe == timeframe,
                OHLCVBar.is_adjusted.is_(request.adjusted),
                OHLCVBar.ts >= history_start,
                OHLCVBar.ts <= end_hint,
            )
            .order_by(OHLCVBar.instrument_id, OHLCVBar.ts)
        )
    ).scalars().all()
    bars_by_id: dict[int, list[OHLCVBar]] = defaultdict(list)
    for bar in bars:
        bars_by_id[bar.instrument_id].append(bar)
    latest = max((bar.ts for rows in bars_by_id.values() for bar in rows), default=None)
    if latest is None:
        latest = end_hint
    period_start, period_end = _period_bounds(request, latest)
    reference_bars: list[object] = []
    reference = None
    reference_source = None
    reference_source_member_ids: list[int] = []
    reference_source_membership_version: str | None = None
    reference_series_method: str | None = None
    if request.reference_symbol:
        reference = (
            await db.execute(
                select(Instrument).where(Instrument.symbol == request.reference_symbol.upper())
            )
        ).scalar_one_or_none()
        if reference:
            reference_bars = (
                await db.execute(
                    select(OHLCVBar)
                    .where(
                        OHLCVBar.instrument_id == reference.id,
                        OHLCVBar.timeframe == timeframe,
                        OHLCVBar.is_adjusted.is_(request.adjusted),
                        OHLCVBar.ts >= history_start,
                        OHLCVBar.ts <= period_end,
                    )
                    .order_by(OHLCVBar.ts)
                )
            ).scalars().all()
        else:
            exclusions.append(_warning("reference_not_found", "The relative-return reference is not canonical."))
    elif request.reference_source_id:
        try:
            reference_resolved = await resolve_watchlist_source(
                db, user_id, request.reference_source_id, as_of=request.as_of
            )
        except LookupError as exc:
            raise ValueError(str(exc)) from exc
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        reference_source = reference_resolved.descriptor
        reference_source_membership_version = reference_source.membership_version
        exclusions.extend(
            _warning(
                "reference_source_exclusion",
                str(item.get("reason", "Reference source member was excluded.")),
                item.get("instrument_id") if isinstance(item, dict) else None,
            )
            for item in reference_resolved.exclusions
        )
        reference_source_member_ids = list(
            dict.fromkeys(member.instrument_id for member in reference_resolved.members)
        )
        reference_source_bars = (
            await db.execute(
                select(OHLCVBar)
                .where(
                    OHLCVBar.instrument_id.in_(reference_source_member_ids),
                    OHLCVBar.timeframe == timeframe,
                    OHLCVBar.is_adjusted.is_(request.adjusted),
                    OHLCVBar.ts >= history_start,
                    OHLCVBar.ts <= period_end,
                )
                .order_by(OHLCVBar.instrument_id, OHLCVBar.ts)
            )
        ).scalars().all()
        reference_bars_by_id: dict[int, list[OHLCVBar]] = defaultdict(list)
        for bar in reference_source_bars:
            reference_bars_by_id[bar.instrument_id].append(bar)
        reference_bars, reference_summary = build_equal_reference_series(reference_bars_by_id)
        reference_series_method = str(reference_summary.get("method"))
        if reference_bars and reference_source_bars:
            first_timestamp = min(bar.ts for bar in reference_source_bars)
            reference_bars = [
                SimpleNamespace(ts=first_timestamp, close=100.0, volume=None),
                *reference_bars,
            ]
        if not reference_bars:
            exclusions.append(
                _warning(
                    "reference_source_no_bars",
                    "The reference source has no aligned local bars for this map.",
                )
            )
    ref_return, _, _, _ = (
        _return(reference_bars, request.period, period_start, period_end)
        if reference or reference_source
        else (None, None, None, None)
    )
    source_bar_watermark = max((bar.ts for rows in bars_by_id.values() for bar in rows), default=None)
    reference_bar_watermark = max((bar.ts for bar in reference_bars), default=None)
    events_by_id, event_watermark = (
        await _events_by_instrument(db, member_ids, period_end)
        if request.color_metric == "breadth" and _condition_requires_events(request.condition)
        else ({}, None)
    )
    cross_sectional_condition = (
        request.color_metric == "breadth"
        and _is_cross_sectional_condition(request.condition)
    )
    cross_sectional_results = {}
    if cross_sectional_condition:
        breadth_members = [
            BreadthMember(
                instrument_id=instrument_id,
                symbol=instruments[instrument_id].symbol,
                name=instruments[instrument_id].name,
            )
            for instrument_id in member_ids
            if instrument_id in instruments
        ]
        cross_sectional_results, _ = evaluate_cross_sectional_percentile(
            breadth_members,
            bars_by_id,
            request.condition or {},
            benchmark_bars=reference_bars,
        )
        cross_sectional_results = {
            item.instrument_id: item for item in cross_sectional_results
        }
    cache_key = _cache_key(
        request,
        resolved.descriptor.membership_version,
        member_ids,
        source_bar_watermark,
        reference_bar_watermark,
        event_watermark,
        reference_source_membership_version,
        reference_source_member_ids,
    )
    python_values, python_output_contract = ({}, "")
    if (
        (request.color_metric == "python" or request.area_metric == "python")
        and request.python_run_id is not None
    ):
        python_values, python_output_contract = await _python_colour_values(
            db, user_id, request.python_run_id
        )
    if request.area_metric == "python" and python_output_contract != "series":
        raise ValueError("python_area_requires_series")
    cached_result = await read_market_map_cache(db, user_id, cache_key)
    if cached_result is not None:
        return cached_result
    cells: list[MarketMapCell] = []
    for instrument_id in member_ids[: request.limit]:
        instrument = instruments.get(instrument_id)
        if instrument is None:
            continue
        rows = [bar for bar in bars_by_id.get(instrument_id, []) if bar.ts <= period_end]
        result, observed, code, message = _return(rows, request.period, period_start, period_end)
        warnings: list[MarketMapWarning] = []
        if code:
            warnings.append(_warning(code, message or code, instrument_id=instrument_id))
        if cross_sectional_condition:
            cross_sectional_result = cross_sectional_results.get(instrument_id)
            if cross_sectional_result is None:
                colour, colour_code, condition_value, condition_metric = (
                    None,
                    "cross_sectional_member_missing",
                    None,
                    None,
                )
            else:
                condition_value = cross_sectional_result.value
                condition_metric = cross_sectional_result.metric
                colour = (1.0 if condition_value else -1.0) if condition_value is not None else None
                colour_code = cross_sectional_result.exclusion_code
        elif request.color_metric == "python":
            colour, colour_code, condition_value, condition_metric = python_values.get(
                instrument_id,
                (None, "python_member_missing", None, None),
            )
        else:
            colour, colour_code, condition_value, condition_metric = _colour(
                request,
                rows,
                result,
                reference_bars=reference_bars,
                events=events_by_id.get(instrument_id),
            )
        if request.color_metric == "relative_return":
            if result is None or ref_return is None:
                colour = None
                colour_code = colour_code or "unaligned_reference"
            else:
                colour = result - ref_return
        if colour_code:
            message = (
                "The cross-sectional breadth target is unavailable for this member."
                if cross_sectional_condition
                else
                "The isolated Python colour output is unavailable for this member."
                if request.color_metric == "python"
                else "The requested colour metric is not covered by available local data."
            )
            warnings.append(_warning(colour_code, message, instrument_id=instrument_id))
        member = members_by_id[instrument_id]
        area: float | None
        area_provenance: dict[str, object] | None = None
        if request.area_metric == "equal":
            area = 1.0
        elif request.area_metric == "python":
            python_value, python_warning, _, _ = python_values.get(
                instrument_id,
                (None, "python_member_missing", None, None),
            )
            area = python_value if python_output_contract == "series" else None
            if python_warning:
                warnings.append(
                    _warning(
                        python_warning,
                        "The isolated Python area output is unavailable for this member.",
                        instrument_id=instrument_id,
                    )
                )
            if area is None or not math.isfinite(area) or area <= 0:
                area = None
                warnings.append(
                    _warning(
                        "python_area_non_positive",
                        "Python area values must be finite and greater than zero.",
                        instrument_id=instrument_id,
                    )
                )
        elif request.area_metric == "weight":
            area = member.weight
            if area is None:
                warnings.append(_warning("missing_weight", "No point-in-time source weight is available.", instrument_id=instrument_id))
        elif request.area_metric == "volume":
            area = float(rows[-1].volume) if rows and rows[-1].volume is not None else None
            if area is None:
                warnings.append(_warning("missing_volume", "No local volume is available for area sizing.", instrument_id=instrument_id))
        elif request.area_metric == "field":
            area, area_provenance, area_code = _numeric_area_field(instrument, request.area_field)
            if area_code:
                warnings.append(
                    _warning(
                        area_code,
                        f"The provider numeric field {request.area_field or 'unknown'} is unavailable or unproven.",
                        instrument_id=instrument_id,
                    )
                )
        else:
            area = float(instrument.stats.market_cap) if instrument.stats and instrument.stats.market_cap is not None else None
            if area is None:
                warnings.append(_warning("missing_market_cap", "No market-cap value is available.", instrument_id=instrument_id))
            else:
                warnings.append(_warning("current_market_cap", "Market-cap area uses the latest stored value and is not point-in-time.", instrument_id=instrument_id))
        path = _group_path(request, instrument)
        if path and "Unclassified" in path:
            warnings.append(_warning("missing_classification", "Sector or industry classification is unavailable; grouped under Unclassified.", instrument_id=instrument_id))
        color_coverage = 1.0 if colour is not None else 0.0
        area_coverage = 1.0 if area is not None and math.isfinite(area) and area > 0 else 0.0
        coverage = min(color_coverage, area_coverage)
        cells.append(MarketMapCell(
            instrument_id=instrument_id,
            symbol=instrument.symbol,
            name=instrument.name,
            sector=instrument.equity_detail.sector if instrument.equity_detail else None,
            industry=instrument.equity_detail.industry if instrument.equity_detail else None,
            group_path=path,
            area_value=area,
            area_provenance=area_provenance,
            color_value=colour,
            return_value=result,
            condition_value=condition_value,
            condition_metric=condition_metric,
            observation_time=observed,
            coverage=coverage,
            color_coverage=color_coverage,
            area_coverage=area_coverage,
            warnings=warnings,
        ))
    cells.sort(key=lambda cell: (cell.area_value is not None, cell.area_value or 0), reverse=True)
    nodes: list[MarketMapNode] = []
    buckets: dict[tuple[str, ...], list[MarketMapCell]] = defaultdict(list)
    for cell in cells:
        buckets[tuple(cell.group_path)].append(cell)
    if request.group_by == "none":
        buckets = {(): cells}
    for path, bucket in sorted(buckets.items()):
        node_id = "root" if not path else "group:" + "/".join(path)
        parent = None if not path else ("root" if len(path) == 1 else "group:" + "/".join(path[:-1]))
        metric, method = _node_metric(bucket, request.area_metric)
        node_warnings = []
        if any(any(item.code == "missing_classification" for item in cell.warnings) for cell in bucket):
            node_warnings.append(_warning("missing_classification", "At least one member lacks a verified classification.", node_id=node_id))
        nodes.append(MarketMapNode(
            node_id=node_id,
            parent_id=parent,
            level="root" if not path else ("sector" if request.group_by == "sector" or len(path) == 1 else "industry"),
            label="All members" if not path else path[-1],
            group_path=list(path),
            member_count=len(bucket),
            covered_count=sum(1 for item in bucket if item.coverage),
            area_total=sum(item.area_value for item in bucket if item.area_value is not None) or None,
            color_value=metric,
            coverage=sum(item.coverage for item in bucket) / max(len(bucket), 1),
            color_coverage=sum(item.color_coverage for item in bucket) / max(len(bucket), 1),
            area_coverage=sum(item.area_coverage for item in bucket) / max(len(bucket), 1),
            aggregation_method=method,
            warnings=node_warnings,
        ))
    if request.group_by == "sector_industry":
        # Add sector parents for the flattened child rows.
        sector_buckets: dict[str, list[MarketMapCell]] = defaultdict(list)
        for cell in cells:
            sector_buckets[cell.group_path[0] if cell.group_path else "Unclassified"].append(cell)
        parents = []
        for sector, bucket in sorted(sector_buckets.items()):
            metric, method = _node_metric(bucket, request.area_metric)
            parents.append(MarketMapNode(node_id=f"group:{sector}", parent_id="root", level="sector", label=sector, group_path=[sector], member_count=len(bucket), covered_count=sum(1 for item in bucket if item.coverage), area_total=sum(item.area_value for item in bucket if item.area_value is not None) or None, color_value=metric, coverage=sum(item.coverage for item in bucket) / max(len(bucket), 1), color_coverage=sum(item.color_coverage for item in bucket) / max(len(bucket), 1), area_coverage=sum(item.area_coverage for item in bucket) / max(len(bucket), 1), aggregation_method=method))
        nodes = [node for node in nodes if node.node_id == "root"] + parents + [node for node in nodes if node.node_id != "root"]
    if request.group_by != "none":
        root_metric, root_method = _node_metric(cells, request.area_metric)
        root = MarketMapNode(
            node_id="root",
            parent_id=None,
            level="root",
            label="All members",
            member_count=len(cells),
            covered_count=sum(1 for item in cells if item.coverage),
            area_total=sum(item.area_value for item in cells if item.area_value is not None) or None,
            color_value=root_metric,
            coverage=sum(item.coverage for item in cells) / max(len(cells), 1),
            color_coverage=sum(item.color_coverage for item in cells) / max(len(cells), 1),
            area_coverage=sum(item.area_coverage for item in cells) / max(len(cells), 1),
            aggregation_method=root_method,
        )
        nodes = [root, *nodes]
    freshness, freshness_detail = await _batch_freshness(db, member_ids, timeframe, request.adjusted)
    exclusions.extend(_warning(item.get("reason", "source_exclusion"), "Member excluded while resolving the source.", item.get("instrument_id")) for item in resolved.exclusions)
    result = MarketMapOut(
        source=resolved.descriptor,
        group_by=request.group_by,
        period=request.period.upper(),
        period_start=period_start,
        period_end=period_end,
        timeframe=timeframe.value,
        adjustment="split_adjusted" if request.adjusted else "raw",
        area_metric=request.area_metric,
        area_field=request.area_field,
        color_metric=request.color_metric,
        condition=request.condition,
        python_run_id=request.python_run_id,
        reference_symbol=request.reference_symbol.upper() if request.reference_symbol else None,
        reference_source=reference_source,
        reference_source_id=request.reference_source_id,
        reference_membership_version=reference_source_membership_version,
        reference_series_method=reference_series_method,
        membership_version=resolved.descriptor.membership_version,
        cache_key=cache_key,
        freshness=freshness,
        freshness_detail=freshness_detail,
        requested_count=len(member_ids),
        evaluated_count=sum(1 for cell in cells if cell.coverage),
        coverage=sum(cell.coverage for cell in cells) / max(len(member_ids), 1),
        color_coverage=sum(cell.color_coverage for cell in cells) / max(len(member_ids), 1),
        area_coverage=sum(cell.area_coverage for cell in cells) / max(len(member_ids), 1),
        nodes=nodes,
        cells=cells,
        exclusions=exclusions,
        warnings=[_warning("current_area_not_point_in_time", "Market-cap area values are current stored metadata.")] if request.area_metric == "market_cap" else [],
    )
    cache_row = MarketMapCache(
        user_id=user_id,
        source_id=request.source_id,
        membership_version=resolved.descriptor.membership_version,
        cache_key=cache_key,
        request_json=request.model_dump(mode="json"),
        response_json=result.model_dump(mode="json"),
        bar_watermark=source_bar_watermark,
        computed_at=datetime.now(UTC),
        last_accessed_at=datetime.now(UTC),
    )
    db.add(cache_row)
    await db.flush()
    return result
