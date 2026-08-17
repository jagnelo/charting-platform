"""Batch calculations for arbitrary locked or user-owned watchlist sources."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.schemas.market_map import (
    MarketMapCell,
    MarketMapNode,
    MarketMapOut,
    MarketMapRequest,
    MarketMapWarning,
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


def _colour(request: MarketMapRequest, bars: list[OHLCVBar], return_value: float | None):
    metric = request.color_metric
    if metric in {"return", "relative_return"}:
        return return_value, None
    if not bars:
        return None, "no_bars"
    latest = float(bars[-1].close)
    if metric == "rsi_14":
        return _rsi(bars), None if len(bars) >= 15 else "insufficient_history"
    if metric == "relative_volume":
        values = [bar.volume for bar in bars[-51:]]
        if len(values) < 51 or any(value is None for value in values):
            return None, "insufficient_volume_history"
        average = sum(float(value) for value in values[:-1]) / 50
        return (float(values[-1]) / average if average else None), None
    window = [float(bar.close) for bar in bars[-252:]]
    if len(window) < 252:
        return None, "insufficient_history"
    if metric == "distance_52w_high":
        return latest / max(window) - 1, None
    return latest / min(window) - 1 if min(window) else None, None


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
    reference_bars: list[OHLCVBar] = []
    reference = None
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
    ref_return, _, _, _ = _return(reference_bars, request.period, period_start, period_end) if reference else (None, None, None, None)
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
        colour, colour_code = _colour(request, rows, result)
        if request.color_metric == "relative_return":
            if result is None or ref_return is None:
                colour = None
                colour_code = colour_code or "unaligned_reference"
            else:
                colour = result - ref_return
        if colour_code:
            warnings.append(_warning(colour_code, "The requested colour metric is not covered by available local data.", instrument_id=instrument_id))
        member = members_by_id[instrument_id]
        area: float | None
        if request.area_metric == "equal":
            area = 1.0
        elif request.area_metric == "weight":
            area = member.weight
            if area is None:
                warnings.append(_warning("missing_weight", "No point-in-time source weight is available.", instrument_id=instrument_id))
        elif request.area_metric == "volume":
            area = float(rows[-1].volume) if rows and rows[-1].volume is not None else None
        else:
            area = float(instrument.stats.market_cap) if instrument.stats and instrument.stats.market_cap is not None else None
            if area is None:
                warnings.append(_warning("missing_market_cap", "No market-cap value is available.", instrument_id=instrument_id))
            else:
                warnings.append(_warning("current_market_cap", "Market-cap area uses the latest stored value and is not point-in-time.", instrument_id=instrument_id))
        path = _group_path(request, instrument)
        if path and "Unclassified" in path:
            warnings.append(_warning("missing_classification", "Sector or industry classification is unavailable; grouped under Unclassified.", instrument_id=instrument_id))
        coverage = 1.0 if result is not None else 0.0
        cells.append(MarketMapCell(
            instrument_id=instrument_id,
            symbol=instrument.symbol,
            name=instrument.name,
            sector=instrument.equity_detail.sector if instrument.equity_detail else None,
            industry=instrument.equity_detail.industry if instrument.equity_detail else None,
            group_path=path,
            area_value=area,
            color_value=colour,
            return_value=result,
            observation_time=observed,
            coverage=coverage,
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
            parents.append(MarketMapNode(node_id=f"group:{sector}", parent_id="root", level="sector", label=sector, group_path=[sector], member_count=len(bucket), covered_count=sum(1 for item in bucket if item.coverage), area_total=sum(item.area_value for item in bucket if item.area_value is not None) or None, color_value=metric, coverage=sum(item.coverage for item in bucket) / max(len(bucket), 1), aggregation_method=method))
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
            aggregation_method=root_method,
        )
        nodes = [root, *nodes]
    freshness, freshness_detail = await _batch_freshness(db, member_ids, timeframe, request.adjusted)
    payload = request.model_dump(mode="json") | {"membership_version": resolved.descriptor.membership_version}
    cache_key = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    exclusions.extend(_warning(item.get("reason", "source_exclusion"), "Member excluded while resolving the source.", item.get("instrument_id")) for item in resolved.exclusions)
    return MarketMapOut(
        source=resolved.descriptor,
        group_by=request.group_by,
        period=request.period.upper(),
        period_start=period_start,
        period_end=period_end,
        timeframe=timeframe.value,
        adjustment="split_adjusted" if request.adjusted else "raw",
        area_metric=request.area_metric,
        color_metric=request.color_metric,
        reference_symbol=request.reference_symbol.upper() if request.reference_symbol else None,
        membership_version=resolved.descriptor.membership_version,
        cache_key=cache_key,
        freshness=freshness,
        freshness_detail=freshness_detail,
        requested_count=len(member_ids),
        evaluated_count=sum(1 for cell in cells if cell.coverage),
        coverage=sum(cell.coverage for cell in cells) / max(len(member_ids), 1),
        nodes=nodes,
        cells=cells,
        exclusions=exclusions,
        warnings=[_warning("current_area_not_point_in_time", "Market-cap area values are current stored metadata.")] if request.area_metric == "market_cap" else [],
    )
