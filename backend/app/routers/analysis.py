"""Canonical local-database analysis endpoints for workstation tools."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.data_source import DataSource
from app.models.etf_holdings import (
    ETFHolding,
    ETFHoldingsAdapterState,
    ETFHoldingsSnapshot,
    ETFProfile,
)
from app.models.instrument import Instrument
from app.models.instrument_event import InstrumentEvent, InstrumentEventFetchState
from app.models.market_map import MarketMapSnapshot
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_observation import DatasetStatus, InstrumentDatasetState
from app.models.provider_runtime import ProviderCapability, ProviderEntitlement
from app.models.research import CodeAsset, CodeVersion, ResearchRun
from app.models.screener import ScreenerDefinition, ScreenerResult
from app.models.user import User
from app.models.workstation import MarketGroup, MarketGroupMember, WorkspaceLibraryItem
from app.routers.market_groups import (
    _holding_exclusion_code,
    _holdings_snapshot_at,
    etf_industry_composition,
    etf_industry_constituents,
    etf_industry_proxies,
    holdings_snapshot_source_filter,
)
from app.routers.screener import ScreenerOut
from app.schemas.analysis import (
    AnalysisCell,
    AnalysisPoint,
    AnalysisWarning,
    BenchmarkFamilyBreadthHistoryOut,
    BenchmarkFamilyBreadthHistoryRoleOut,
    BenchmarkFamilyBreadthMetricOut,
    BenchmarkFamilyBreadthOut,
    BenchmarkFamilyBreadthRoleOut,
    BenchmarkFamilyConcentrationHistoryOut,
    BenchmarkFamilyConcentrationHistoryPointOut,
    BenchmarkFamilyConcentrationHistoryRoleOut,
    BenchmarkFamilyConcentrationMemberOut,
    BenchmarkFamilyConcentrationOut,
    BenchmarkFamilyConcentrationRoleOut,
    BenchmarkFamilyCoverageGapOut,
    BenchmarkFamilyCoverageOut,
    BenchmarkFamilyCoverageRoleOut,
    BenchmarkFamilyCoverageSnapshotOut,
    BenchmarkFamilyDerivedEqualWeightOut,
    BenchmarkFamilyMappingOut,
    BenchmarkFamilyMemberBarHistoryOut,
    BenchmarkFamilyMemberBarHistoryTimeframeOut,
    BenchmarkFamilyOverviewOut,
    BenchmarkFamilyRankingOut,
    BenchmarkFamilyRankingRoleOut,
    BenchmarkFamilyRatioOut,
    BenchmarkFamilyRatiosOut,
    BenchmarkFamilyReadinessOut,
    BenchmarkFamilyRotationOut,
    BenchmarkFamilyRotationRoleOut,
    BenchmarkFamilyTechnicalRoleOut,
    BenchmarkFamilyTechnicalsOut,
    BreadthConditionDiagnosticOut,
    BreadthConditionRequest,
    BreadthDefinitionHistoryOccurrenceOut,
    BreadthDefinitionHistoryOut,
    BreadthDefinitionHistoryPointOut,
    BreadthDefinitionOut,
    BreadthDefinitionRequest,
    BreadthHistoryOut,
    BreadthHistoryPoint,
    BreadthHistoryRequest,
    BreadthMemberResultOut,
    BreadthOut,
    BreadthPythonColumnPromotionRequest,
    BreadthPythonPlotPromotionRequest,
    BreadthPythonPromotionRequest,
    BreadthPythonResultOut,
    BreadthPythonResultPointOut,
    BreadthPythonRunOut,
    BreadthPythonRunRequest,
    BreadthPythonStudyPromotionRequest,
    BreadthUniverseRequest,
    CrossFamilyRankingHistoryOut,
    CrossFamilyRankingHistoryPoint,
    CrossFamilyRankingHistoryRowOut,
    CrossFamilyRankingOut,
    CrossFamilyRankingRowOut,
    ETFConstituentSnapshotOut,
    ETFConstituentSnapshotRowOut,
    GroupSnapshotOut,
    GroupSnapshotRow,
    IndicatorBatchOut,
    IndicatorBatchRequest,
    IndustryProxySnapshotOut,
    IndustryProxySnapshotRow,
    IndustrySnapshotOut,
    IndustrySnapshotRow,
    MarketGaugeOut,
    RelativeRotationOut,
    RelativeRotationRow,
    RelativeRotationTailPoint,
    RelativeStrengthOut,
    TechnicalSnapshotOut,
)
from app.schemas.code import CodeAssetOut
from app.schemas.market_map import (
    MarketMapOut,
    MarketMapRequest,
    MarketMapSnapshotCreate,
    MarketMapSnapshotOut,
    MarketMapSnapshotSummary,
)
from app.services.benchmark_family_coverage import (
    OBSERVED_CONTINUITY_MAX_INTERVAL_DAYS,
    assess_observed_holdings_continuity,
)
from app.services.breadth import (
    BreadthMember,
    build_equal_reference_series,
    definition_hash,
    detect_breadth_occurrences,
    evaluate_breadth,
    evaluate_breadth_history,
)
from app.services.etf_holdings import EQUITY_HOLDING_TYPE_VALUES
from app.services.etf_holdings_adapters import get_holdings_adapter, known_etf_route_metadata
from app.services.indicators import OHLCVSeries, get_latest_value
from app.services.market_map import build_market_map, read_market_map_cache
from app.services.parameter_validation import validate_parameter_values
from app.services.provider_availability import latest_availability, provider_configured
from app.services.research_jobs import (
    collect_research_result,
    enqueue_research_run,
    read_research_progress,
)
from app.services.top_down_taxonomy import benchmark_family_registry
from app.services.watchlist_sources import resolve_watchlist_source

router = APIRouter(prefix="/analysis", tags=["analysis"])

_PERIODS = {"1D": 1, "1W": 5, "1M": 21, "3M": 63, "6M": 126, "YTD": None, "1Y": 252}
_CALENDAR_YEAR_LOOKBACK = 5
_FAMILY_MEMBER_BAR_REQUIREMENTS = {
    Timeframe.D1: 252,
    Timeframe.W1: 52,
    Timeframe.MN: 24,
}

_HOLDING_EXCLUSION_MESSAGES = {
    "cash_holding": "Cash, collateral, or currency exposure is excluded from equity analysis.",
    "derivative_holding": "Derivative exposure is excluded from equity analysis.",
    "unresolved_holding": "The holding has no resolved canonical equity instrument.",
    "non_equity_holding": "The holding is not a supported equity security.",
}


async def _family_member_bar_history(
    db: AsyncSession,
    snapshot: ETFHoldingsSnapshot | None,
    *,
    as_of: datetime | None,
) -> BenchmarkFamilyMemberBarHistoryOut:
    """Return one batched local-bar readiness report for a holdings snapshot.

    This deliberately reads only the canonical database.  ``covered`` means a
    member has at least one usable adjusted bar; ``analysis_ready`` applies the
    minimum history required by the workstation's D1/W1/MN technical surfaces.
    The two counts must remain distinct so a one-bar fixture cannot masquerade
    as enough history for a 200-day breadth study.
    """

    if snapshot is None:
        return BenchmarkFamilyMemberBarHistoryOut(status="no_snapshot")

    member_rows = (
        await db.execute(
            select(ETFHolding.constituent_instrument_id)
            .where(
                ETFHolding.snapshot_id == snapshot.id,
                ETFHolding.row_type == "security",
                ETFHolding.holding_type.in_(EQUITY_HOLDING_TYPE_VALUES),
                ETFHolding.is_resolved.is_(True),
                ETFHolding.constituent_instrument_id.is_not(None),
            )
            .distinct()
        )
    ).all()
    member_ids = [int(row[0]) for row in member_rows if row[0] is not None]
    if not member_ids:
        return BenchmarkFamilyMemberBarHistoryOut(
            status="unavailable",
            snapshot_id=snapshot.id,
            composition_date=snapshot.composition_date,
        )

    bars_query = (
        select(
            OHLCVBar.timeframe,
            OHLCVBar.instrument_id,
            func.count(OHLCVBar.id).label("bar_count"),
            func.min(OHLCVBar.ts).label("oldest"),
            func.max(OHLCVBar.ts).label("newest"),
        )
        .where(
            OHLCVBar.instrument_id.in_(member_ids),
            OHLCVBar.timeframe.in_(tuple(_FAMILY_MEMBER_BAR_REQUIREMENTS)),
            OHLCVBar.is_adjusted.is_(True),
        )
        .group_by(OHLCVBar.timeframe, OHLCVBar.instrument_id)
    )
    if as_of is not None:
        bars_query = bars_query.where(OHLCVBar.ts <= as_of)
    bar_rows = (await db.execute(bars_query)).all()

    by_timeframe: dict[Timeframe, list[tuple[int, int, datetime | None, datetime | None]]] = (
        defaultdict(list)
    )
    for timeframe, instrument_id, bar_count, oldest, newest in bar_rows:
        by_timeframe[timeframe].append((int(instrument_id), int(bar_count), oldest, newest))

    timeframes: list[BenchmarkFamilyMemberBarHistoryTimeframeOut] = []
    for timeframe, required_bar_count in _FAMILY_MEMBER_BAR_REQUIREMENTS.items():
        rows = by_timeframe.get(timeframe, [])
        covered_count = len(rows)
        ready_count = sum(
            1 for _instrument_id, count, _oldest, _newest in rows if count >= required_bar_count
        )
        oldest_values = [
            oldest for _instrument_id, _count, oldest, _newest in rows if oldest is not None
        ]
        newest_values = [
            newest for _instrument_id, _count, _oldest, newest in rows if newest is not None
        ]
        timeframes.append(
            BenchmarkFamilyMemberBarHistoryTimeframeOut(
                timeframe=timeframe.value,
                required_bar_count=required_bar_count,
                member_count=len(member_ids),
                covered_member_count=covered_count,
                coverage_percent=round((covered_count / len(member_ids)) * 100, 2),
                analysis_ready_member_count=ready_count,
                analysis_ready_percent=round((ready_count / len(member_ids)) * 100, 2),
                bar_count=sum(count for _instrument_id, count, _oldest, _newest in rows),
                oldest=min(oldest_values) if oldest_values else None,
                newest=max(newest_values) if newest_values else None,
            )
        )

    if all(item.analysis_ready_member_count == len(member_ids) for item in timeframes):
        status = "ready"
    elif any(item.covered_member_count for item in timeframes):
        status = "partial"
    else:
        status = "pending"
    return BenchmarkFamilyMemberBarHistoryOut(
        status=status,
        snapshot_id=snapshot.id,
        composition_date=snapshot.composition_date,
        timeframes=timeframes,
    )


async def _family_member_metadata_readiness(
    db: AsyncSession,
    snapshot: ETFHoldingsSnapshot | None,
    *,
    as_of: datetime | None,
) -> tuple[int, int, str, int, str]:
    """Summarize point-in-time weight and classification evidence for one snapshot."""

    # FastAPI accepts both offset-aware and offset-less ISO timestamps.  The
    # provenance timestamps are normalized to UTC below, so normalize the
    # caller cutoff as well before comparing Python datetime values.  Without
    # this boundary, a valid historical request such as ``2026-12-01T00:00:00``
    # would raise on aware/naive comparison instead of returning readiness.
    evaluation_at = _as_utc(as_of) if as_of is not None else None

    if snapshot is None:
        return 0, 0, "unavailable", 0, "unavailable"
    rows = (
        (
            await db.execute(
                select(ETFHolding)
                .options(
                    selectinload(ETFHolding.constituent_instrument).selectinload(
                        Instrument.equity_detail
                    )
                )
                .where(
                    ETFHolding.snapshot_id == snapshot.id,
                    ETFHolding.row_type == "security",
                    ETFHolding.holding_type.in_(EQUITY_HOLDING_TYPE_VALUES),
                    ETFHolding.is_resolved.is_(True),
                    ETFHolding.constituent_instrument_id.is_not(None),
                )
                .order_by(ETFHolding.position)
            )
        )
        .scalars()
        .all()
    )
    member_count = len(rows)
    if not member_count:
        return 0, 0, "unavailable", 0, "unavailable"

    weighted_count = sum(row.weight is not None for row in rows)
    classified_count = 0
    for row in rows:
        detail = row.constituent_instrument.equity_detail if row.constituent_instrument else None
        if detail is None or not detail.industry:
            continue
        if evaluation_at is None:
            classified_count += 1
            continue
        evidence = (detail.field_provenance or {}).get("industry")
        observed_text = (
            evidence.get("observed_at") or evidence.get("known_at")
            if isinstance(evidence, dict)
            else None
        )
        if not observed_text:
            continue
        try:
            observed_at = datetime.fromisoformat(str(observed_text).replace("Z", "+00:00"))
        except ValueError:
            continue
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=UTC)
        if observed_at <= evaluation_at:
            classified_count += 1

    weights_status = (
        "ready" if weighted_count == member_count else "partial" if weighted_count else "pending"
    )
    classification_status = (
        "ready"
        if classified_count == member_count
        else "partial"
        if classified_count
        else "pending"
    )
    return member_count, weighted_count, weights_status, classified_count, classification_status


def _as_utc(value: datetime) -> datetime:
    """Normalize database timestamps before entitlement cutoff comparisons."""

    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _entitlement_state(
    source: DataSource | None,
    entitlement: ProviderEntitlement | None,
    *,
    evaluation_at: datetime | None = None,
) -> str:
    """Classify persisted entitlement evidence without probing a provider."""

    if entitlement is None:
        return "unknown"
    if not entitlement.is_free or entitlement.configured_plan in {"excluded", "unreviewed"}:
        return "excluded" if entitlement.configured_plan == "excluded" else "unreviewed"
    if source is None or not provider_configured(source, entitlement):
        return "not_configured"
    evaluation = _as_utc(evaluation_at or datetime.now(UTC))
    if entitlement.effective_at and _as_utc(entitlement.effective_at) > evaluation:
        return "unreviewed"
    if entitlement.review_due_at and _as_utc(entitlement.review_due_at) <= evaluation:
        return "unreviewed"
    if entitlement.live_probe_status in {"failure", "failed", "error"}:
        return "probe_failed"
    if entitlement.live_probe_status not in {"success", "passed", "verified", "ok"}:
        return "unreviewed"
    return "verified"


def _role_readiness(
    *,
    mapping_available: bool,
    profile_loaded: bool,
    holdings_status: str,
    member_bar_status: str,
    entitlement_status: str,
    point_in_time_supported: bool,
    weights_status: str,
    classification_status: str,
) -> tuple[str, list[str]]:
    """Return conservative composite readiness and machine-readable reasons."""

    reasons: list[str] = []
    if not mapping_available:
        return "unavailable", ["mapping_unavailable"]
    if not profile_loaded:
        return "pending", ["profile_not_loaded"]
    if entitlement_status in {"excluded", "not_configured", "probe_failed"}:
        reasons.append(f"entitlement_{entitlement_status}")
    elif entitlement_status in {"unknown", "unreviewed"}:
        reasons.append(f"entitlement_{entitlement_status}")
    if holdings_status != "available":
        reasons.append(f"holdings_{holdings_status}")
    if not point_in_time_supported:
        reasons.append("point_in_time_unavailable")
    if member_bar_status != "ready":
        reasons.append(f"member_history_{member_bar_status}")
    if weights_status != "ready":
        reasons.append(f"weights_{weights_status}")
    if classification_status != "ready":
        reasons.append(f"classification_{classification_status}")
    if any(reason.startswith("entitlement_") for reason in reasons) and entitlement_status in {
        "excluded",
        "not_configured",
        "probe_failed",
    }:
        return "blocked", reasons
    if (
        holdings_status == "available"
        and member_bar_status == "ready"
        and entitlement_status == "verified"
        and weights_status == "ready"
        and classification_status == "ready"
    ):
        return "ready", reasons
    if holdings_status == "available" or member_bar_status in {"partial", "ready"}:
        return "partial", reasons
    return "pending", reasons


@router.post("/market-map", response_model=MarketMapOut)
async def market_map(
    body: MarketMapRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return one local batch map for any resolved watchlist source.

    This endpoint deliberately never calls a provider.  The source resolver and
    persisted OHLCV/metadata tables are the only inputs, so a map can expose
    exact coverage and exclusions rather than hiding per-tile provider fan-out.
    """
    try:
        return await build_market_map(db, current_user.id, body)
    except ValueError as exc:
        code = str(exc)
        if code == "invalid_timeframe":
            raise HTTPException(422, detail={"code": code, "timeframe": body.timeframe}) from exc
        if code.endswith("not_found") or code == "unsupported_watchlist_source_kind":
            raise HTTPException(404, detail={"code": code, "source_id": body.source_id}) from exc
        raise HTTPException(422, detail={"code": code}) from exc


@router.get("/market-map/cache/{cache_key}", response_model=MarketMapOut)
async def read_market_map_snapshot(
    cache_key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Restore one persisted Market Map result for the authenticated user."""

    if len(cache_key) != 64 or any(character not in "0123456789abcdef" for character in cache_key):
        raise HTTPException(422, detail={"code": "invalid_market_map_cache_key"})
    result = await read_market_map_cache(db, current_user.id, cache_key)
    if result is None:
        raise HTTPException(
            404, detail={"code": "market_map_cache_not_found", "cache_key": cache_key}
        )
    return result


@router.get("/market-map/snapshots", response_model=list[MarketMapSnapshotSummary])
async def list_market_map_snapshots(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List named Market Map snapshots owned by the authenticated user."""

    return (
        (
            await db.execute(
                select(MarketMapSnapshot)
                .where(MarketMapSnapshot.user_id == current_user.id)
                .order_by(MarketMapSnapshot.created_at.desc())
            )
        )
        .scalars()
        .all()
    )


@router.post("/market-map/snapshots", response_model=MarketMapSnapshotOut)
async def create_market_map_snapshot(
    body: MarketMapSnapshotCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save a named immutable copy of one already-materialized map result."""

    name = body.name.strip()
    if not name:
        raise HTTPException(422, detail={"code": "snapshot_name_required"})
    existing = (
        await db.execute(
            select(MarketMapSnapshot).where(
                MarketMapSnapshot.user_id == current_user.id,
                MarketMapSnapshot.name == name,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(409, detail={"code": "market_map_snapshot_name_exists"})
    cached = await read_market_map_cache(db, current_user.id, body.cache_key)
    if cached is None:
        raise HTTPException(
            404, detail={"code": "market_map_cache_not_found", "cache_key": body.cache_key}
        )
    snapshot_map = cached.model_copy(update={"cache_hit": False, "cached_at": None})
    map_json = snapshot_map.model_dump(mode="json")
    snapshot_hash = hashlib.sha256(
        json.dumps(map_json, sort_keys=True, default=str).encode()
    ).hexdigest()
    row = MarketMapSnapshot(
        user_id=current_user.id,
        name=name,
        source_id=snapshot_map.source.source_id,
        membership_version=snapshot_map.membership_version,
        cache_key=body.cache_key,
        snapshot_hash=snapshot_hash,
        map_json=map_json,
    )
    db.add(row)
    await db.flush()
    summary = MarketMapSnapshotSummary.model_validate(row)
    return MarketMapSnapshotOut(**summary.model_dump(), map=snapshot_map)


@router.get("/market-map/snapshots/{snapshot_id:int}", response_model=MarketMapSnapshotOut)
async def read_market_map_snapshot_by_id(
    snapshot_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Restore one named Market Map snapshot owned by the authenticated user."""

    row = (
        await db.execute(
            select(MarketMapSnapshot).where(
                MarketMapSnapshot.id == snapshot_id,
                MarketMapSnapshot.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, detail={"code": "market_map_snapshot_not_found"})
    snapshot_map = MarketMapOut.model_validate(row.map_json)
    summary = MarketMapSnapshotSummary.model_validate(row)
    return MarketMapSnapshotOut(**summary.model_dump(), map=snapshot_map)


@router.delete("/market-map/snapshots/{snapshot_id:int}", status_code=204)
async def delete_market_map_snapshot(
    snapshot_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete one named Market Map snapshot without deleting its cache result."""

    row = (
        await db.execute(
            select(MarketMapSnapshot).where(
                MarketMapSnapshot.id == snapshot_id,
                MarketMapSnapshot.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, detail={"code": "market_map_snapshot_not_found"})
    await db.delete(row)


def _aggregate_series_cells(
    values: list[tuple[datetime, float]], instrument_id: int | None
) -> dict[str, AnalysisCell]:
    """Calculate ranking periods for an equal-weight synthetic industry series."""

    if not values:
        warning = AnalysisWarning(
            code="no_bars",
            message="No aligned constituent bars are available.",
            instrument_id=instrument_id,
        )
        return {
            period: AnalysisCell(value=None, observation_time=None, warning=warning)
            for period in _PERIODS
        }
    latest_timestamp, latest_value = values[-1]
    prior_year_end = next(
        (item for item in reversed(values) if item[0].year < latest_timestamp.year),
        None,
    )
    cells: dict[str, AnalysisCell] = {}
    for period, offset in _PERIODS.items():
        base: float | None
        if period == "YTD":
            base = prior_year_end[1] if prior_year_end is not None else None
            code = "insufficient_ytd_history"
            message = "YTD requires an aligned observation before the current calendar year."
        else:
            base = values[-offset - 1][1] if offset is not None and len(values) > offset else None
            code = "insufficient_history"
            message = f"{period} requires more aligned constituent history."
        if base is None or base == 0:
            cells[period] = AnalysisCell(
                value=None,
                observation_time=latest_timestamp,
                warning=AnalysisWarning(code=code, message=message, instrument_id=instrument_id),
            )
        else:
            cells[period] = AnalysisCell(
                value=latest_value / base - 1, observation_time=latest_timestamp
            )
    return cells


def _historical_return_series(
    bars: list[OHLCVBar],
) -> dict[datetime, dict[str, float | None]]:
    """Calculate non-forward-filled return cells at every observed bar timestamp."""

    series: dict[datetime, dict[str, float | None]] = {}
    for index, bar in enumerate(bars):
        cells: dict[str, float | None] = {}
        for period, offset in _PERIODS.items():
            if period == "YTD":
                base_index = next(
                    (
                        candidate
                        for candidate in range(index - 1, -1, -1)
                        if bars[candidate].ts.year < bar.ts.year
                    ),
                    -1,
                )
            else:
                base_index = index - (offset + 1)  # type: ignore[operator]
            if base_index < 0 or base_index == index:
                cells[period] = None
                continue
            base = bars[base_index].close
            cells[period] = float(bar.close / base - 1) if base else None
        series[bar.ts] = cells
    return series


def _distribution_stats(values: list[float]) -> dict[str, float | None]:
    """Return deterministic finite-sample distribution statistics."""

    if not values:
        return {
            "mean_return": None,
            "median_return": None,
            "dispersion": None,
            "p10_return": None,
            "p25_return": None,
            "p75_return": None,
            "p90_return": None,
            "positive_percentage": None,
            "negative_percentage": None,
        }
    ordered = sorted(values)

    def percentile(fraction: float) -> float:
        position = (len(ordered) - 1) * fraction
        lower = math.floor(position)
        upper = math.ceil(position)
        if lower == upper:
            return ordered[lower]
        weight = position - lower
        return ordered[lower] + (ordered[upper] - ordered[lower]) * weight

    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return {
        "mean_return": mean,
        "median_return": percentile(0.5),
        "dispersion": math.sqrt(variance),
        "p10_return": percentile(0.1),
        "p25_return": percentile(0.25),
        "p75_return": percentile(0.75),
        "p90_return": percentile(0.9),
        "positive_percentage": sum(value > 0 for value in values) / len(values),
        "negative_percentage": sum(value < 0 for value in values) / len(values),
    }


def _technical_cells_for_series(
    values: list[tuple[datetime, float]], instrument_id: int | None
) -> dict[str, AnalysisCell]:
    """Return the same transparent technical fields used by group rankings."""

    if not values:
        warning = AnalysisWarning(
            code="no_bars",
            message="No aligned constituent bars are available.",
            instrument_id=instrument_id,
        )
        return {
            key: AnalysisCell(value=None, observation_time=None, warning=warning)
            for key in ("above_ma20", "above_ma50", "above_ma200", "rsi14", "position_52w")
        }
    latest_timestamp, latest_value = values[-1]
    closes = [value for _, value in values]
    technical: dict[str, AnalysisCell] = {}
    for period in (20, 50, 200):
        key = f"above_ma{period}"
        warning = (
            None
            if len(closes) >= period
            else AnalysisWarning(
                code="insufficient_history",
                message=f"Price versus SMA({period}) requires {period} aligned constituent observations.",
                instrument_id=instrument_id,
            )
        )
        technical[key] = AnalysisCell(
            value=(1.0 if latest_value > sum(closes[-period:]) / period else 0.0)
            if warning is None
            else None,
            observation_time=latest_timestamp,
            warning=warning,
        )
    if len(closes) >= 15:
        changes = [
            closes[index] - closes[index - 1] for index in range(len(closes) - 13, len(closes))
        ]
        gain = _mean([max(change, 0.0) for change in changes])
        loss = _mean([max(-change, 0.0) for change in changes])
        technical["rsi14"] = AnalysisCell(
            value=100.0 if loss == 0 else 100 - (100 / (1 + gain / loss)),
            observation_time=latest_timestamp,
        )
    else:
        technical["rsi14"] = AnalysisCell(
            value=None,
            observation_time=latest_timestamp,
            warning=AnalysisWarning(
                code="insufficient_history",
                message="RSI(14) requires 15 aligned constituent observations.",
                instrument_id=instrument_id,
            ),
        )
    if len(closes) >= 252:
        window = closes[-252:]
        spread = max(window) - min(window)
        technical["position_52w"] = AnalysisCell(
            value=(latest_value - min(window)) / spread if spread else 1.0,
            observation_time=latest_timestamp,
        )
    else:
        technical["position_52w"] = AnalysisCell(
            value=None,
            observation_time=latest_timestamp,
            warning=AnalysisWarning(
                code="insufficient_history",
                message="52-week position requires 252 aligned constituent observations.",
                instrument_id=instrument_id,
            ),
        )
    return technical


def _normalised_bar_series(bars: list[OHLCVBar]) -> dict[datetime, float]:
    """Build one non-forward-filled total-return proxy from a bar sequence."""

    if not bars:
        return {}
    first = next((float(bar.close) for bar in bars if bar.close), None)
    if first in (None, 0):
        return {}
    return {bar.ts: float(bar.close) / first for bar in bars if bar.close}


def _equal_weight_series(
    bars_by_id: dict[int, list[OHLCVBar]], instrument_ids: list[int]
) -> list[tuple[datetime, float]]:
    """Build an equal-weight industry proxy on intersecting observations only."""

    series = [
        _normalised_bar_series(bars_by_id.get(instrument_id, []))
        for instrument_id in instrument_ids
    ]
    series = [item for item in series if item]
    if not series:
        return []
    timestamps = sorted(set.intersection(*(set(item) for item in series)))
    return [(timestamp, _mean([item[timestamp] for item in series])) for timestamp in timestamps]


def _ratio_cell(
    values: list[tuple[datetime, float]],
    reference: dict[datetime, float],
    instrument_id: int | None,
) -> AnalysisCell:
    if not values:
        return AnalysisCell(
            value=None,
            observation_time=None,
            warning=AnalysisWarning(
                code="no_bars",
                message="No aligned industry observations are available.",
                instrument_id=instrument_id,
            ),
        )
    timestamp, value = values[-1]
    denominator = reference.get(timestamp)
    if denominator in (None, 0):
        return AnalysisCell(
            value=None,
            observation_time=timestamp,
            warning=AnalysisWarning(
                code="unaligned_benchmark",
                message="No aligned benchmark observation is available.",
                instrument_id=instrument_id,
            ),
        )
    return AnalysisCell(value=value / denominator, observation_time=timestamp)


@router.post("/indicator-batch", response_model=IndicatorBatchOut)
async def indicator_batch(
    body: IndicatorBatchRequest,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Evaluate one canonical indicator column across a bounded symbol universe."""
    try:
        timeframe = Timeframe(body.timeframe)
    except ValueError as exc:
        raise HTTPException(
            422, detail={"code": "invalid_timeframe", "timeframe": body.timeframe}
        ) from exc
    symbols = list(
        dict.fromkeys(symbol.upper().strip() for symbol in body.symbols if symbol.strip())
    )
    if not symbols:
        raise HTTPException(422, detail={"code": "empty_symbols"})
    instruments = {
        instrument.symbol: instrument
        for instrument in (
            await db.execute(select(Instrument).where(Instrument.symbol.in_(symbols)))
        ).scalars()
    }
    bars_by_id = await _bars_by_instrument(
        db, [instrument.id for instrument in instruments.values()], timeframe, body.adjusted
    )
    values: dict[str, dict[str, object]] = {}
    exclusions: list[AnalysisWarning] = []
    for symbol in symbols:
        instrument = instruments.get(symbol)
        if instrument is None:
            warning = AnalysisWarning(
                code="instrument_not_found",
                message="No canonical instrument exists.",
                instrument_id=None,
            )
            values[symbol] = {
                "value": None,
                "observation_time": None,
                "warning": warning.model_dump(),
            }
            exclusions.append(warning)
            continue
        bars = bars_by_id.get(instrument.id, [])[-500:]
        if not bars:
            warning = AnalysisWarning(
                code="no_bars",
                message="No canonical bars are available.",
                instrument_id=instrument.id,
            )
            values[symbol] = {
                "value": None,
                "observation_time": None,
                "warning": warning.model_dump(),
            }
            exclusions.append(warning)
            continue
        try:
            value = get_latest_value(
                body.indicator,
                OHLCVSeries.from_orm_bars(bars),
                body.params,
                str(body.params.get("output")) if body.params.get("output") else None,
            )
        except (KeyError, IndexError) as exc:
            warning = AnalysisWarning(
                code="unknown_indicator", message=str(exc), instrument_id=instrument.id
            )
            values[symbol] = {
                "value": None,
                "observation_time": bars[-1].ts,
                "warning": warning.model_dump(),
            }
            exclusions.append(warning)
            continue
        warning = None
        if value is None:
            warning = AnalysisWarning(
                code="insufficient_history",
                message="The available bars do not satisfy this indicator's lookback.",
                instrument_id=instrument.id,
            )
            exclusions.append(warning)
        values[symbol] = {
            "value": value,
            "observation_time": bars[-1].ts,
            "warning": warning.model_dump() if warning else None,
        }
    evaluated_count = sum(1 for cell in values.values() if cell.get("value") is not None)
    return IndicatorBatchOut(
        indicator=body.indicator,
        timeframe=timeframe.value,
        adjustment="split_adjusted" if body.adjusted else "raw",
        params=body.params,
        universe_provenance={"type": "explicit_symbols", "symbol_count": len(symbols)},
        values=values,
        requested_count=len(symbols),
        evaluated_count=evaluated_count,
        coverage=evaluated_count / max(len(symbols), 1),
        exclusions=exclusions,
    )


def _is_known_at(
    value: datetime | None,
    as_of: datetime | None,
    *,
    required: bool = False,
) -> bool:
    """Return whether a versioned timestamp is usable at ``as_of``.

    A missing timestamp is tolerated for latest/current views, where legacy rows
    remain readable.  An explicit point-in-time request can require the
    timestamp: admitting an observation whose known-at boundary is absent would
    make historical membership appear more certain than the data supports.
    """
    if as_of is None:
        return True
    if value is None:
        return not required
    # Query parameters may be offset-less while persisted provenance is UTC
    # aware (and legacy rows can have the inverse shape).  Compare one
    # canonical timeline so historical membership never crashes on a valid
    # ISO cutoff or silently admits a future version.
    return _as_utc(value) <= _as_utc(as_of)


def _wire_datetime(value: datetime | None) -> str | None:
    """Use one canonical UTC spelling in provenance fields and cache identities."""
    if value is None:
        return None
    encoded = value.isoformat()
    return encoded.replace("+00:00", "Z")


def _group_members_at(
    group: MarketGroup,
    as_of: datetime | None,
    *,
    allow_late_registered_group: bool = False,
) -> list[MarketGroupMember]:
    """Select a group's versioned members without admitting future membership.

    Curated benchmark-family roots can be registered after the historical member
    rows they describe.  Derived historical views may explicitly opt into using
    each member's effective/known-at boundary as the source of truth; ordinary
    group snapshots retain the stricter group-lifecycle check.
    """
    # Root groups created before lifecycle timestamps were introduced may have
    # no group-level known_at.  Their members still carry the authoritative
    # point-in-time boundary, so retain the static-root compatibility rule while
    # requiring each member's known_at below.
    if not allow_late_registered_group and (
        not _is_known_at(group.effective_at, as_of) or not _is_known_at(group.known_at, as_of)
    ):
        raise HTTPException(
            404,
            detail={"code": "market_group_not_known_at", "group_key": group.stable_key},
        )
    return [
        member
        for member in group.members
        if _is_known_at(member.effective_at, as_of)
        and _is_known_at(member.known_at, as_of, required=as_of is not None)
    ]


def _truncate_bars_at(
    bars_by_id: dict[int, list[OHLCVBar]], as_of: datetime | None
) -> dict[int, list[OHLCVBar]]:
    if as_of is None:
        return bars_by_id
    return {
        instrument_id: [bar for bar in bars if bar.ts <= as_of]
        for instrument_id, bars in bars_by_id.items()
    }


def _sample_aligned_points(
    aligned: list[tuple[datetime, float]], sampling: int
) -> list[tuple[datetime, float]]:
    """Sample aligned ratio observations while retaining the latest point."""
    sampled = aligned[::sampling]
    if sampled and sampled[-1][0] != aligned[-1][0]:
        sampled.append(aligned[-1])
    return sampled


def _rotation_state(trend: float, momentum: float) -> str:
    if trend >= 0 and momentum >= 0:
        return "leading"
    if trend >= 0:
        return "weakening"
    if momentum >= 0:
        return "improving"
    return "lagging"


def _rotation_metrics(
    aligned: list[tuple[datetime, float]],
    sampling: int,
    lookback: int,
    tail_length: int,
    history_length: int = 0,
) -> tuple[
    dict[str, object] | None,
    list[RelativeRotationTailPoint],
    list[RelativeRotationTailPoint],
    list[AnalysisWarning],
]:
    """Calculate transparent relative-rotation metrics from an aligned ratio series."""

    sampled = _sample_aligned_points(aligned, sampling)
    warnings: list[AnalysisWarning] = []
    coordinates: list[RelativeRotationTailPoint] = []
    for index in range(lookback * 2, len(sampled)):
        ratio = sampled[index][1]
        prior_ratio = sampled[index - lookback][1]
        prior_prior_ratio = sampled[index - lookback * 2][1]
        if prior_ratio == 0 or prior_prior_ratio == 0:
            continue
        trend = ratio / prior_ratio - 1
        previous_trend = prior_ratio / prior_prior_ratio - 1
        coordinates.append(
            RelativeRotationTailPoint(
                timestamp=sampled[index][0], trend=trend, momentum=trend - previous_trend
            )
        )
    if not coordinates:
        return None, [], [], warnings
    latest = coordinates[-1]
    state = _rotation_state(latest.trend, latest.momentum)
    coordinate_states = [_rotation_state(point.trend, point.momentum) for point in coordinates]
    previous_state = coordinate_states[-2] if len(coordinate_states) > 1 else None
    time_in_state = 0
    for coordinate_state in reversed(coordinate_states):
        if coordinate_state != state:
            break
        time_in_state += 1
    previous = coordinates[-2] if len(coordinates) > 1 else None
    velocity = (
        math.hypot(latest.trend - previous.trend, latest.momentum - previous.momentum)
        if previous is not None
        else None
    )
    history = coordinates[-history_length:] if history_length else []
    return (
        {
            "trend": latest.trend,
            "momentum": latest.momentum,
            "state": state,
            "heading": math.degrees(math.atan2(latest.momentum, latest.trend)),
            "distance": math.hypot(latest.trend, latest.momentum),
            "velocity": velocity,
            "transition": (
                f"{previous_state}->{state}" if previous_state and previous_state != state else None
            ),
            "time_in_state": time_in_state,
        },
        coordinates[-tail_length:],
        history,
        warnings,
    )


def _group_provenance(group: MarketGroup, as_of: datetime | None) -> dict[str, object]:
    return {
        **(group.provenance or {}),
        "membership_as_of": _wire_datetime(as_of),
        "membership_selection": "effective_at_and_known_at",
    }


def _group_membership_version(group: MarketGroup, members: list[MarketGroupMember]) -> int:
    """Return a stable cache/version identity for the selected group universe.

    A database primary key identifies the group row, not its evolving membership.
    Include the lifecycle and verification fields that affect historical selection
    so a changed membership cannot reuse a stale batch-analysis cache entry.
    """
    payload = {
        "group": group.stable_key,
        "group_effective_at": _wire_datetime(group.effective_at),
        "group_known_at": _wire_datetime(group.known_at),
        "members": [
            {
                "instrument_id": member.instrument_id,
                "relationship_type": member.relationship_type,
                "position": member.position,
                "weight": member.weight,
                "source": member.source,
                "verification_state": member.verification_state,
                "effective_at": _wire_datetime(member.effective_at),
                "known_at": _wire_datetime(member.known_at),
                "provenance": member.provenance or {},
            }
            for member in sorted(members, key=lambda item: (item.position, item.instrument_id))
        ],
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big", signed=False) & ((1 << 63) - 1)


def _gauge_exclusion_warnings(excluded: object) -> list[AnalysisWarning]:
    """Normalize legacy keyed and Python-manifest list exclusions for gauges."""
    if isinstance(excluded, dict):
        return [
            AnalysisWarning(
                code=value.get("code", "excluded"),
                message=value.get("message", "Excluded"),
                instrument_id=int(key) if str(key).isdigit() else value.get("instrument_id"),
            )
            for key, value in excluded.items()
            if isinstance(value, dict)
        ]
    if isinstance(excluded, list):
        return [
            AnalysisWarning(
                code=str(value.get("code") or "excluded"),
                message=str(value.get("message") or "Excluded"),
                instrument_id=value.get("instrument_id")
                if isinstance(value.get("instrument_id"), int)
                else None,
            )
            for value in excluded
            if isinstance(value, dict)
        ]
    return []


@router.get("/gauges/{screener_id}", response_model=MarketGaugeOut)
async def market_gauge(
    screener_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Expose a Market Gauge from a retained local-only EasyScan result."""
    screener = (
        await db.execute(
            select(ScreenerDefinition).where(
                ScreenerDefinition.id == screener_id,
                ScreenerDefinition.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if screener is None:
        raise HTTPException(404, detail={"code": "screener_not_found"})
    latest = (
        await db.execute(
            select(ScreenerResult)
            .where(ScreenerResult.screener_id == screener.id)
            .order_by(ScreenerResult.run_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest is None:
        return MarketGaugeOut(
            screener_id=screener.id,
            screener_name=screener.name,
            run_at=None,
            matched_count=0,
            evaluated_count=0,
            universe_count=0,
            percentage=None,
            exclusions=[
                AnalysisWarning(
                    code="scan_not_run", message="Run this EasyScan before using it as a gauge."
                )
            ],
        )
    coverage = latest.result_data.get("_coverage", {})
    excluded = coverage.get("excluded", {}) if isinstance(coverage, dict) else {}
    universe_count = int(coverage.get("universe_count", 0)) if isinstance(coverage, dict) else 0
    evaluated_count = int(coverage.get("evaluated_count", 0)) if isinstance(coverage, dict) else 0
    # The isolated batch manifest stores exclusions as a list of structured
    # records, while the legacy in-process evaluator stores an instrument-keyed
    # mapping.  Gauges consume both forms without turning a handled coverage
    # limitation into HTTP 500.
    warnings = _gauge_exclusion_warnings(excluded)
    return MarketGaugeOut(
        screener_id=screener.id,
        screener_name=screener.name,
        run_at=latest.run_at,
        matched_count=len(latest.matched_ids),
        evaluated_count=evaluated_count,
        universe_count=universe_count,
        percentage=(len(latest.matched_ids) / evaluated_count) if evaluated_count else None,
        exclusions=warnings,
    )


async def _instrument(db: AsyncSession, symbol: str) -> Instrument:
    result = await db.execute(select(Instrument).where(Instrument.symbol == symbol.upper()))
    instrument = result.scalar_one_or_none()
    if instrument is None:
        raise HTTPException(404, detail={"code": "instrument_not_found", "symbol": symbol.upper()})
    return instrument


async def _bars_by_instrument(
    db: AsyncSession, instrument_ids: list[int], timeframe: Timeframe, adjusted: bool
) -> dict[int, list[OHLCVBar]]:
    if not instrument_ids:
        return {}
    bars = (
        await db.execute(
            select(OHLCVBar)
            .where(
                OHLCVBar.instrument_id.in_(instrument_ids),
                OHLCVBar.timeframe == timeframe,
                OHLCVBar.is_adjusted.is_(adjusted),
            )
            .order_by(OHLCVBar.instrument_id, OHLCVBar.ts)
        )
    ).scalars()
    result: dict[int, list[OHLCVBar]] = defaultdict(list)
    for bar in bars:
        result[bar.instrument_id].append(bar)
    return result


def _cell(
    value: float | None, bar: OHLCVBar | None, warning: AnalysisWarning | None = None
) -> AnalysisCell:
    return AnalysisCell(value=value, observation_time=bar.ts if bar else None, warning=warning)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _volume_ratio_50(
    bars: list[OHLCVBar], instrument_id: int
) -> tuple[float | None, AnalysisWarning | None]:
    """Calculate volume ratio without turning missing provider volume into a 500."""
    if len(bars) < 51:
        return (
            None,
            AnalysisWarning(
                code="insufficient_history",
                message="50-day volume ratio requires 51 bars.",
                instrument_id=instrument_id,
            ),
        )
    previous = [bar.volume for bar in bars[-51:-1]]
    latest = bars[-1].volume
    if latest is None or any(value is None for value in previous):
        return (
            None,
            AnalysisWarning(
                code="missing_volume",
                message="Volume observations are incomplete for the 50-day ratio.",
                instrument_id=instrument_id,
            ),
        )
    average = _mean([float(value) for value in previous])
    if average == 0:
        return (
            None,
            AnalysisWarning(
                code="zero_average_volume",
                message="50-day average volume is zero.",
                instrument_id=instrument_id,
            ),
        )
    return float(latest) / average, None


def _calendar_year_cells(
    bars: list[OHLCVBar], instrument_id: int, years: list[int]
) -> dict[str, AnalysisCell]:
    """Return non-forward-filled calendar-year returns for a bounded year window."""
    by_year: dict[int, list[OHLCVBar]] = defaultdict(list)
    for bar in bars:
        by_year[bar.ts.year].append(bar)
    cells: dict[str, AnalysisCell] = {}
    for year in years:
        key = str(year)
        year_bars = by_year.get(year, [])
        if not year_bars:
            cells[key] = _cell(
                None,
                None,
                AnalysisWarning(
                    code="no_calendar_year_bars",
                    message=f"No local bars are available for calendar year {year}.",
                    instrument_id=instrument_id,
                ),
            )
            continue
        first, last = year_bars[0], year_bars[-1]
        if len(year_bars) < 2 or first.close == 0:
            cells[key] = _cell(
                None,
                last,
                AnalysisWarning(
                    code="insufficient_calendar_year_history",
                    message=f"Calendar year {year} requires at least two non-zero bars.",
                    instrument_id=instrument_id,
                ),
            )
            continue
        cells[key] = _cell(float(last.close / first.close - 1), last)
    return cells


def _performance_cells(bars: list[OHLCVBar], instrument_id: int) -> dict[str, AnalysisCell]:
    """Calculate period returns without treating a fixed bar count as calendar YTD."""
    if not bars:
        warning = AnalysisWarning(
            code="no_bars", message="No local bars are available.", instrument_id=instrument_id
        )
        return {period: _cell(None, None, warning) for period in _PERIODS}
    latest = bars[-1]
    prior_year_end = next((bar for bar in reversed(bars) if bar.ts.year < latest.ts.year), None)
    cells: dict[str, AnalysisCell] = {}
    for period, offset in _PERIODS.items():
        if period == "YTD":
            if prior_year_end is None or prior_year_end.close == 0:
                cells[period] = _cell(
                    None,
                    latest,
                    AnalysisWarning(
                        code="insufficient_ytd_history",
                        message="YTD requires an aligned observation before the current calendar year.",
                        instrument_id=instrument_id,
                    ),
                )
            else:
                cells[period] = _cell(float(latest.close / prior_year_end.close - 1), latest)
            continue
        assert offset is not None
        if len(bars) <= offset:
            cells[period] = _cell(
                None,
                latest,
                AnalysisWarning(
                    code="insufficient_history",
                    message=f"{period} requires more history.",
                    instrument_id=instrument_id,
                ),
            )
        else:
            base = bars[-offset - 1]
            if base.close == 0:
                cells[period] = _cell(
                    None,
                    latest,
                    AnalysisWarning(
                        code="zero_base_price",
                        message=f"{period} cannot be calculated from a zero base close.",
                        instrument_id=instrument_id,
                    ),
                )
            else:
                cells[period] = _cell(float(latest.close / base.close - 1), latest)
    return cells


async def _batch_freshness(
    db: AsyncSession,
    instrument_ids: list[int],
    timeframe: Timeframe,
    adjusted: bool = True,
) -> tuple[str, dict[str, int]]:
    """Summarise persisted OHLCV state without exposing providers or fallback order.

    Dataset state keys include the adjustment mode (for example ``D1:adj``), while
    older rows may use the legacy unqualified timeframe key.  Analysis responses
    must inspect the state matching the requested adjustment instead of silently
    reporting ``unavailable`` when bars are present.
    """
    if not instrument_ids:
        return "unavailable", {"requested": 0, "current": 0, "stale": 0, "other": 0}
    dataset_keys = [f"{timeframe.value}:{'adj' if adjusted else 'raw'}", timeframe.value]
    states = (
        (
            await db.execute(
                select(InstrumentDatasetState).where(
                    InstrumentDatasetState.instrument_id.in_(instrument_ids),
                    InstrumentDatasetState.dataset_type == "ohlcv",
                    InstrumentDatasetState.dataset_key.in_(dataset_keys),
                )
            )
        )
        .scalars()
        .all()
    )
    now = datetime.now(UTC)
    by_instrument: dict[int, list[InstrumentDatasetState]] = defaultdict(list)
    for state in states:
        by_instrument[state.instrument_id].append(state)
    current = stale = other = 0
    for instrument_id in instrument_ids:
        entries = by_instrument.get(instrument_id, [])
        if any(
            entry.status == DatasetStatus.FRESH
            and entry.stale_after is not None
            and (
                entry.stale_after
                if entry.stale_after.tzinfo
                else entry.stale_after.replace(tzinfo=UTC)
            )
            > now
            for entry in entries
        ):
            current += 1
        elif any(entry.status == DatasetStatus.FRESH for entry in entries):
            stale += 1
        else:
            other += 1
    detail = {"requested": len(instrument_ids), "current": current, "stale": stale, "other": other}
    if current == len(instrument_ids):
        return "current", detail
    if current == 0 and stale == 0:
        return "unavailable", detail
    if stale and current == 0:
        return "stale", detail
    return "partial", detail


@router.get("/instruments/{symbol}/technical", response_model=TechnicalSnapshotOut)
async def instrument_technical_snapshot(
    symbol: str,
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    as_of: datetime | None = Query(default=None),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return local, reproducible technical values without a provider fetch."""
    instrument = await _instrument(db, symbol)
    bars = (await _bars_by_instrument(db, [instrument.id], timeframe, adjusted)).get(
        instrument.id, []
    )
    if as_of is not None:
        bars = [bar for bar in bars if bar.ts <= as_of]
    latest = bars[-1] if bars else None
    warnings: list[AnalysisWarning] = []

    def required(period: int, label: str) -> bool:
        if len(bars) >= period:
            return True
        warnings.append(
            AnalysisWarning(
                code="insufficient_history",
                message=f"{label} requires {period} bars.",
                instrument_id=instrument.id,
            )
        )
        return False

    if latest is None:
        warnings.append(
            AnalysisWarning(
                code="no_bars", message="No local bars are available.", instrument_id=instrument.id
            )
        )
        freshness, freshness_detail = await _batch_freshness(
            db, [instrument.id], timeframe, adjusted
        )
        return TechnicalSnapshotOut(
            symbol=instrument.symbol,
            timeframe=timeframe.value,
            as_of=as_of,
            adjustment="split_adjusted" if adjusted else "raw",
            freshness=freshness,
            freshness_detail=freshness_detail,
            last=None,
            rsi14=None,
            sma20=None,
            sma50=None,
            sma200=None,
            position_52w=None,
            volume_ratio_50=None,
            warnings=warnings,
        )

    closes = [float(bar.close) for bar in bars]
    volume_ratio_50, volume_warning = _volume_ratio_50(bars, instrument.id)
    if volume_warning:
        warnings.append(volume_warning)
    rsi14 = None
    if required(15, "RSI(14)"):
        changes = [
            closes[index] - closes[index - 1] for index in range(len(closes) - 13, len(closes))
        ]
        average_gain = _mean([max(change, 0.0) for change in changes])
        average_loss = _mean([max(-change, 0.0) for change in changes])
        rsi14 = 100.0 if average_loss == 0 else 100 - (100 / (1 + average_gain / average_loss))

    averages: dict[int, float | None] = {}
    for period in (20, 50, 200):
        averages[period] = _mean(closes[-period:]) if required(period, f"SMA({period})") else None
    position_52w = None
    if required(252, "52-week position"):
        window = closes[-252:]
        span = max(window) - min(window)
        position_52w = (closes[-1] - min(window)) / span if span else 1.0
    freshness, freshness_detail = await _batch_freshness(db, [instrument.id], timeframe, adjusted)
    return TechnicalSnapshotOut(
        symbol=instrument.symbol,
        timeframe=timeframe.value,
        as_of=as_of or latest.ts,
        adjustment="split_adjusted" if adjusted else "raw",
        freshness=freshness,
        freshness_detail=freshness_detail,
        last=closes[-1],
        rsi14=rsi14,
        sma20=averages[20],
        sma50=averages[50],
        sma200=averages[200],
        position_52w=position_52w,
        volume_ratio_50=volume_ratio_50,
        warnings=warnings,
    )


@router.get("/relative-strength", response_model=RelativeStrengthOut)
async def relative_strength(
    symbol: str,
    benchmark: str,
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    as_of: datetime | None = Query(default=None),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    primary, comparator = await _instrument(db, symbol), await _instrument(db, benchmark)
    grouped = await _bars_by_instrument(db, [primary.id, comparator.id], timeframe, adjusted)
    grouped = _truncate_bars_at(grouped, as_of)
    primary_by_time = {bar.ts: bar for bar in grouped.get(primary.id, [])}
    comparator_by_time = {bar.ts: bar for bar in grouped.get(comparator.id, [])}
    timestamps = sorted(primary_by_time.keys() & comparator_by_time.keys())
    points = [
        AnalysisPoint(
            timestamp=timestamp,
            value=float(primary_by_time[timestamp].close / comparator_by_time[timestamp].close),
        )
        for timestamp in timestamps
        if comparator_by_time[timestamp].close != 0
    ]
    maximum = max(len(primary_by_time), len(comparator_by_time), 1)
    warnings: list[AnalysisWarning] = []
    if not points:
        warnings.append(
            AnalysisWarning(
                code="no_aligned_bars", message="No aligned bars are available for this ratio."
            )
        )
    elif len(points) < maximum:
        warnings.append(
            AnalysisWarning(
                code="partial_overlap",
                message="Only intersecting timestamps were used; gaps were not forward-filled.",
            )
        )
    freshness, freshness_detail = await _batch_freshness(
        db, [primary.id, comparator.id], timeframe, adjusted
    )
    return RelativeStrengthOut(
        symbol=primary.symbol,
        benchmark=comparator.symbol,
        timeframe=timeframe.value,
        adjustment="split_adjusted" if adjusted else "raw",
        as_of=as_of,
        freshness=freshness,
        freshness_detail=freshness_detail,
        points=points,
        overlap_start=points[0].timestamp if points else None,
        overlap_end=points[-1].timestamp if points else None,
        coverage=len(points) / maximum,
        warnings=warnings,
    )


@router.get(
    "/benchmark-families/{family_key}/relative-rotation",
    response_model=BenchmarkFamilyRotationOut,
)
async def benchmark_family_relative_rotation(
    family_key: str,
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    as_of: datetime | None = Query(default=None),
    sampling: int = Query(default=1, ge=1, le=30),
    lookback: int = Query(default=20, ge=2, le=252),
    tail_length: int = Query(default=10, ge=1, le=100),
    history_length: int = Query(default=0, ge=0, le=1000),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compare each evidenced family leg with its own cap proxy using aligned ratios."""

    group = (
        await db.execute(
            select(MarketGroup)
            .options(selectinload(MarketGroup.members))
            .where(
                MarketGroup.stable_key == family_key,
                MarketGroup.group_type == "benchmark_family",
            )
        )
    ).scalar_one_or_none()
    if group is None:
        raise HTTPException(
            404, detail={"code": "benchmark_family_not_found", "family_key": family_key}
        )
    provenance = dict(group.provenance or {})
    official = provenance.get("official_index")
    mappings = provenance.get("proxy_mappings")
    mappings = mappings if isinstance(mappings, Mapping) else {}
    cap_mapping = mappings.get("cap_weight")
    cap_mapping = cap_mapping if isinstance(cap_mapping, Mapping) else {}
    cap_symbol = cap_mapping.get("symbol")
    if not cap_symbol:
        raise HTTPException(
            409,
            detail={"code": "family_cap_proxy_unavailable", "family_key": family_key},
        )
    try:
        cap_instrument = await _instrument(db, str(cap_symbol))
    except HTTPException as error:
        if error.status_code == 404:
            raise HTTPException(
                409,
                detail={"code": "family_cap_proxy_unavailable", "family_key": family_key},
            ) from error
        raise
    role_names = ("cap_weight", "equal_weight", "value", "growth")
    role_instruments: dict[str, Instrument] = {"cap_weight": cap_instrument}
    exclusions: list[AnalysisWarning] = []
    for role in role_names[1:]:
        mapping = mappings.get(role)
        mapping = mapping if isinstance(mapping, Mapping) else {}
        symbol = mapping.get("symbol")
        if not symbol:
            continue
        try:
            role_instruments[role] = await _instrument(db, str(symbol))
        except HTTPException as error:
            if error.status_code != 404:
                raise
            exclusions.append(
                AnalysisWarning(
                    code="instrument_not_found",
                    message=f"No canonical instrument exists for {family_key} {role}.",
                )
            )
    instrument_ids = [instrument.id for instrument in role_instruments.values()]
    bars_by_id = _truncate_bars_at(
        await _bars_by_instrument(db, instrument_ids, timeframe, adjusted), as_of
    )
    benchmark_bars = bars_by_id.get(cap_instrument.id, [])
    benchmark_by_timestamp = {bar.ts: bar for bar in benchmark_bars}
    roles: list[BenchmarkFamilyRotationRoleOut] = []
    for role in role_names:
        mapping = mappings.get(role)
        mapping = mapping if isinstance(mapping, Mapping) else {}
        symbol = str(mapping.get("symbol")).upper() if mapping.get("symbol") else None
        label = str(mapping.get("label") or "No verified mapped proxy")
        verification_state = str(mapping.get("verification_state") or "not_verified")
        instrument = role_instruments.get(role)
        warnings: list[AnalysisWarning] = []
        if instrument is None:
            warnings.append(
                AnalysisWarning(
                    code="role_mapping_unavailable",
                    message=f"No verified {role} proxy is available for {family_key}.",
                )
            )
            roles.append(
                BenchmarkFamilyRotationRoleOut(
                    role=role,
                    symbol=symbol,
                    label=label,
                    verification_state=verification_state,
                    available=False,
                    coverage=0,
                    warnings=warnings,
                )
            )
            continue
        bars = bars_by_id.get(instrument.id, [])
        aligned = [
            (bar.ts, float(bar.close / benchmark_by_timestamp[bar.ts].close))
            for bar in bars
            if bar.ts in benchmark_by_timestamp and benchmark_by_timestamp[bar.ts].close != 0
        ]
        maximum = max(len(bars), len(benchmark_bars), 1)
        if not aligned:
            warnings.append(
                AnalysisWarning(
                    code="no_aligned_bars",
                    message="No aligned ratio bars are available.",
                    instrument_id=instrument.id,
                )
            )
        elif len(aligned) < maximum:
            warnings.append(
                AnalysisWarning(
                    code="partial_overlap",
                    message="Only intersecting timestamps were used; gaps were not forward-filled.",
                    instrument_id=instrument.id,
                )
            )
        metrics, tail, history, metric_warnings = _rotation_metrics(
            aligned, sampling, lookback, tail_length, history_length
        )
        if metrics is None:
            warnings.append(
                AnalysisWarning(
                    code="insufficient_history",
                    message=f"Relative rotation requires {lookback * 2 + 1} sampled observations.",
                    instrument_id=instrument.id,
                )
            )
            roles.append(
                BenchmarkFamilyRotationRoleOut(
                    role=role,
                    instrument_id=instrument.id,
                    symbol=symbol,
                    label=label,
                    verification_state=verification_state,
                    available=False,
                    coverage=len(aligned) / maximum,
                    tail=tail,
                    history=history,
                    warnings=[*warnings, *metric_warnings],
                )
            )
            continue
        roles.append(
            BenchmarkFamilyRotationRoleOut(
                role=role,
                instrument_id=instrument.id,
                symbol=symbol,
                label=label,
                verification_state=verification_state,
                available=True,
                coverage=len(aligned) / maximum,
                tail=tail,
                history=history,
                warnings=[*warnings, *metric_warnings],
                **metrics,
            )
        )
    freshness, freshness_detail = await _batch_freshness(db, instrument_ids, timeframe, adjusted)
    members = _group_members_at(group, as_of)
    return BenchmarkFamilyRotationOut(
        family_key=family_key,
        benchmark=cap_instrument.symbol,
        official_index_symbol=(
            str(official.get("symbol") or "") if isinstance(official, Mapping) else ""
        ),
        timeframe=timeframe.value,
        adjustment="split_adjusted" if adjusted else "raw",
        as_of=as_of,
        sampling=sampling,
        lookback=lookback,
        tail_length=tail_length,
        history_length=history_length,
        membership_version=_group_membership_version(group, members),
        universe_provenance=_group_provenance(group, as_of),
        roles=roles,
        exclusions=exclusions,
        freshness=freshness,
        freshness_detail=freshness_detail,
    )


@router.get("/groups/{group_key}/relative-rotation", response_model=RelativeRotationOut)
async def group_relative_rotation(
    group_key: str,
    benchmark: str,
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    as_of: datetime | None = Query(default=None),
    sampling: int = Query(default=1, ge=1, le=30),
    lookback: int = Query(default=20, ge=2, le=252),
    tail_length: int = Query(default=10, ge=1, le=100),
    history_length: int = Query(default=0, ge=0, le=1000),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Transparent relative trend/momentum states from locally aligned ratios.

    Trend is the ratio return over ``lookback`` bars. Momentum is its change from
    the preceding lookback observation. This is deliberately not a JdK calculation.
    """
    group = (
        await db.execute(
            select(MarketGroup)
            .options(selectinload(MarketGroup.members))
            .where(MarketGroup.stable_key == group_key)
        )
    ).scalar_one_or_none()
    if group is None:
        raise HTTPException(404, detail={"code": "market_group_not_found", "group_key": group_key})
    benchmark_instrument = await _instrument(db, benchmark)
    members = _group_members_at(group, as_of)
    instrument_ids = [member.instrument_id for member in members]
    instruments = {
        instrument.id: instrument
        for instrument in (
            await db.execute(select(Instrument).where(Instrument.id.in_(instrument_ids)))
        ).scalars()
    }
    bars_by_id = await _bars_by_instrument(
        db, [*instrument_ids, benchmark_instrument.id], timeframe, adjusted
    )
    bars_by_id = _truncate_bars_at(bars_by_id, as_of)
    benchmark_bars = {bar.ts: bar for bar in bars_by_id.get(benchmark_instrument.id, [])}
    rows: list[RelativeRotationRow] = []
    for member in sorted(members, key=lambda item: item.position):
        instrument = instruments.get(member.instrument_id)
        if instrument is None:
            continue
        bars = bars_by_id.get(instrument.id, [])
        aligned = [
            (bar.ts, float(bar.close / benchmark_bars[bar.ts].close))
            for bar in bars
            if bar.ts in benchmark_bars and benchmark_bars[bar.ts].close != 0
        ]
        maximum = max(len(bars), len(benchmark_bars), 1)
        warnings: list[AnalysisWarning] = []
        if not aligned:
            warnings.append(
                AnalysisWarning(
                    code="no_aligned_bars",
                    message="No aligned ratio bars are available.",
                    instrument_id=instrument.id,
                )
            )
        elif len(aligned) < maximum:
            warnings.append(
                AnalysisWarning(
                    code="partial_overlap",
                    message="Only intersecting timestamps were used; gaps were not forward-filled.",
                    instrument_id=instrument.id,
                )
            )
        metrics, tail, history, metric_warnings = _rotation_metrics(
            aligned, sampling, lookback, tail_length, history_length
        )
        if metrics is None:
            warnings.append(
                AnalysisWarning(
                    code="insufficient_history",
                    message=f"Relative rotation requires {lookback * 2 + 1} sampled observations.",
                    instrument_id=instrument.id,
                )
            )
            rows.append(
                RelativeRotationRow(
                    instrument_id=instrument.id,
                    symbol=instrument.symbol,
                    name=instrument.name,
                    coverage=len(aligned) / maximum,
                    tail=tail,
                    history=history,
                    warnings=[*warnings, *metric_warnings],
                )
            )
            continue
        rows.append(
            RelativeRotationRow(
                instrument_id=instrument.id,
                symbol=instrument.symbol,
                name=instrument.name,
                coverage=len(aligned) / maximum,
                tail=tail,
                history=history,
                warnings=[*warnings, *metric_warnings],
                **metrics,
            )
        )
    freshness, freshness_detail = await _batch_freshness(
        db, [*instrument_ids, benchmark_instrument.id], timeframe, adjusted
    )
    return RelativeRotationOut(
        group_key=group.stable_key,
        benchmark=benchmark_instrument.symbol,
        timeframe=timeframe.value,
        adjustment="split_adjusted" if adjusted else "raw",
        lookback=lookback,
        tail_length=tail_length,
        history_length=history_length,
        sampling=sampling,
        membership_version=_group_membership_version(group, members),
        universe_provenance=_group_provenance(group, as_of),
        as_of=as_of,
        freshness=freshness,
        freshness_detail=freshness_detail,
        rows=rows,
    )


@router.get(
    "/etf/{symbol}/industries/{industry}/proxies/snapshot",
    response_model=IndustryProxySnapshotOut,
)
async def industry_proxy_snapshot(
    symbol: str,
    industry: str,
    market_benchmark: str = Query(default="SPY"),
    as_of: datetime | None = Query(default=None),
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rank only independently verified industry-proxy ETFs from local bars.

    The sector ETF is the primary benchmark and ``market_benchmark`` is returned as
    a second aligned ratio.  The proxy list comes from the holdings-evidence gate;
    ticker names alone can never enter this batch universe.
    """
    sector = await _instrument(db, symbol)
    evidence = await etf_industry_proxies(
        symbol=sector.symbol, industry=industry, as_of=as_of, _=current_user, db=db
    )
    proxy_symbols = [item.symbol for item in evidence.proxies]
    market = await _instrument(db, market_benchmark)
    instruments = {
        item.symbol: item
        for item in (
            await db.execute(select(Instrument).where(Instrument.symbol.in_(proxy_symbols)))
        ).scalars()
    }
    ordered = [instruments[item.symbol] for item in evidence.proxies if item.symbol in instruments]
    bars_by_id = await _bars_by_instrument(
        db, [*(item.id for item in ordered), sector.id, market.id], timeframe, adjusted
    )
    if as_of is not None:
        bars_by_id = {
            instrument_id: [bar for bar in bars if bar.ts <= as_of]
            for instrument_id, bars in bars_by_id.items()
        }
    sector_bars = {bar.ts: bar for bar in bars_by_id.get(sector.id, [])}
    market_bars = {bar.ts: bar for bar in bars_by_id.get(market.id, [])}
    rows: list[IndustryProxySnapshotRow] = []
    exclusions: list[AnalysisWarning] = []
    covered = 0
    for instrument in ordered:
        bars = bars_by_id.get(instrument.id, [])
        latest = bars[-1] if bars else None
        if latest is None:
            warning = AnalysisWarning(
                code="no_bars", message="No local bars are available.", instrument_id=instrument.id
            )
            exclusions.append(warning)
            rows.append(
                IndustryProxySnapshotRow(
                    instrument_id=instrument.id,
                    symbol=instrument.symbol,
                    name=instrument.name,
                    last=_cell(None, None, warning),
                    performance={period: _cell(None, None, warning) for period in _PERIODS},
                )
            )
            continue
        covered += 1
        closes = [float(bar.close) for bar in bars]
        volume_ratio_50, volume_warning = _volume_ratio_50(bars, instrument.id)
        performance = _performance_cells(bars, instrument.id)
        technical: dict[str, AnalysisCell] = {}
        for period in (20, 50, 200):
            technical[f"above_ma{period}"] = _cell(
                1.0
                if closes[-1] > _mean(closes[-period:])
                else 0.0
                if len(closes) >= period
                else None,
                latest,
                None
                if len(closes) >= period
                else AnalysisWarning(
                    code="insufficient_history",
                    message=f"Price versus SMA({period}) requires {period} bars.",
                    instrument_id=instrument.id,
                ),
            )
        if len(closes) >= 15:
            changes = [
                closes[index] - closes[index - 1] for index in range(len(closes) - 13, len(closes))
            ]
            gain, loss = (
                _mean([max(change, 0.0) for change in changes]),
                _mean([max(-change, 0.0) for change in changes]),
            )
            technical["rsi14"] = _cell(
                100.0 if loss == 0 else 100 - (100 / (1 + gain / loss)), latest
            )
        else:
            technical["rsi14"] = _cell(
                None,
                latest,
                AnalysisWarning(
                    code="insufficient_history",
                    message="RSI(14) requires 15 bars.",
                    instrument_id=instrument.id,
                ),
            )
        if len(closes) >= 252:
            window = closes[-252:]
            spread = max(window) - min(window)
            technical["position_52w"] = _cell(
                (closes[-1] - min(window)) / spread if spread else 1.0, latest
            )
        else:
            technical["position_52w"] = _cell(
                None,
                latest,
                AnalysisWarning(
                    code="insufficient_history",
                    message="52-week position requires 252 bars.",
                    instrument_id=instrument.id,
                ),
            )
        technical["volume_ratio_50"] = _cell(volume_ratio_50, latest, volume_warning)

        def ratio(reference: dict) -> AnalysisCell:
            reference_bar = reference.get(latest.ts)
            return (
                _cell(float(latest.close / reference_bar.close), latest)
                if reference_bar and reference_bar.close
                else _cell(
                    None,
                    latest,
                    AnalysisWarning(
                        code="unaligned_benchmark",
                        message="No aligned benchmark bar is available.",
                        instrument_id=instrument.id,
                    ),
                )
            )

        rows.append(
            IndustryProxySnapshotRow(
                instrument_id=instrument.id,
                symbol=instrument.symbol,
                name=instrument.name,
                last=_cell(float(latest.close), latest),
                performance=performance,
                technical=technical,
                relative_to_benchmark=ratio(sector_bars),
                relative_to_market=ratio(market_bars),
            )
        )
    freshness, freshness_detail = await _batch_freshness(
        db, [*(item.id for item in ordered), sector.id, market.id], timeframe, adjusted
    )
    return IndustryProxySnapshotOut(
        group_key=f"industry-proxy:{sector.symbol}:{industry}",
        etf_symbol=sector.symbol,
        industry=industry,
        market_benchmark=market.symbol,
        timeframe=timeframe.value,
        as_of=max(
            (row.last.observation_time for row in rows if row.last.observation_time), default=None
        ),
        adjustment="split_adjusted" if adjusted else "raw",
        membership_version=sum(
            sum(ord(char) for char in f"{item.symbol}:{item.composition_date}:{item.known_at}")
            for item in evidence.proxies
        ),
        universe_provenance={
            "membership_semantics": "verified_industry_etf_proxies",
            "sector_etf": sector.symbol,
            "industry": industry,
        },
        freshness=freshness,
        freshness_detail=freshness_detail,
        coverage=covered / max(len(ordered), 1),
        exclusions=exclusions,
        rows=rows,
        proxy_evidence=[item.model_dump(mode="json") for item in evidence.proxies],
    )


@router.get("/etf/{symbol}/industries/snapshot", response_model=IndustrySnapshotOut)
async def industry_snapshot(
    symbol: str,
    market_benchmark: str = Query(default="SPY"),
    as_of: datetime | None = Query(default=None),
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rank classified industries as equal-weight synthetic series.

    Industry rows are derived from the selected ETF disclosure. They are not
    official index constituents, and each response retains the composition
    provenance and exact exclusions used to build the synthetic series.
    """

    etf = await _instrument(db, symbol)
    market = await _instrument(db, market_benchmark)
    composition = await etf_industry_composition(
        symbol=etf.symbol, as_of=as_of, _=current_user, db=db
    )
    rows: list[IndustrySnapshotRow] = []
    exclusions: list[AnalysisWarning] = []
    all_instrument_ids: set[int] = {etf.id, market.id}
    industry_members: list[tuple[object, list[int]]] = []
    for industry in composition.industries:
        constituents = await etf_industry_constituents(
            symbol=etf.symbol, industry=industry.industry, as_of=as_of, _=current_user, db=db
        )
        ids = [item.id for item in constituents.constituents]
        industry_members.append((industry, ids))
        all_instrument_ids.update(ids)
        exclusions.extend(
            AnalysisWarning(code=code, message=f"Industry {industry.industry}: {code}.")
            for code in constituents.exclusions
        )
    bars_by_id = _truncate_bars_at(
        await _bars_by_instrument(db, list(all_instrument_ids), timeframe, adjusted), as_of
    )
    benchmark_series = _normalised_bar_series(bars_by_id.get(etf.id, []))
    market_series = _normalised_bar_series(bars_by_id.get(market.id, []))
    covered = 0
    for industry, ids in industry_members:
        series = _equal_weight_series(bars_by_id, ids)
        if not series:
            warning = AnalysisWarning(
                code="no_bars",
                message="No aligned constituent bars are available for this industry.",
            )
            exclusions.append(
                warning.model_copy(update={"message": f"{industry.industry}: {warning.message}"})
            )
        else:
            covered += 1
        performance = _aggregate_series_cells(series, instrument_id=None)
        technical = _technical_cells_for_series(series, instrument_id=None)
        warnings = [
            cell.warning
            for cell in [*performance.values(), *technical.values()]
            if cell.warning is not None
        ]
        last_timestamp, last_value = series[-1] if series else (None, None)
        rows.append(
            IndustrySnapshotRow(
                industry=industry.industry,
                constituent_count=industry.constituent_count,
                resolved_count=industry.resolved_count,
                coverage=len([item for item in ids if bars_by_id.get(item)]) / max(len(ids), 1),
                last=AnalysisCell(value=last_value, observation_time=last_timestamp),
                performance=performance,
                relative_to_benchmark=_ratio_cell(series, benchmark_series, None),
                relative_to_market=_ratio_cell(series, market_series, None),
                technical=technical,
                warnings=warnings,
            )
        )
    freshness, freshness_detail = await _batch_freshness(
        db, list(all_instrument_ids), timeframe, adjusted
    )
    return IndustrySnapshotOut(
        group_key=f"industry:{etf.symbol}",
        etf_symbol=etf.symbol,
        market_benchmark=market.symbol,
        timeframe=timeframe.value,
        adjustment="split_adjusted" if adjusted else "raw",
        as_of=max(
            (row.last.observation_time for row in rows if row.last.observation_time), default=None
        ),
        composition_date=datetime.fromisoformat(composition.composition_date).date(),
        known_at=composition.known_at,
        membership_version=int(
            hashlib.sha256(
                json.dumps(
                    {
                        "composition_date": composition.composition_date,
                        "known_at": _wire_datetime(composition.known_at),
                        "industries": [(row.industry, ids) for row, ids in industry_members],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()[:12],
            16,
        ),
        universe_provenance={
            "membership_semantics": "etf_proxy_classified_industry_equal_weight",
            "etf_symbol": etf.symbol,
            "composition_date": composition.composition_date,
            "known_at": _wire_datetime(composition.known_at),
            "classification_systems": composition.classification_systems,
        },
        freshness=freshness,
        freshness_detail=freshness_detail,
        coverage=covered / max(len(industry_members), 1),
        exclusions=exclusions,
        rows=rows,
    )


@router.get("/etf/{symbol}/constituents/snapshot", response_model=ETFConstituentSnapshotOut)
async def etf_constituent_snapshot(
    symbol: str,
    benchmark: str | None = Query(default=None),
    market_benchmark: str | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Batch technical/rank values for one source-labelled ETF holdings snapshot.

    The selected snapshot is the newest local disclosure known to the platform, or the
    newest disclosure whose composition and ``known_at`` timestamps are both no later
    than ``as_of``. Its resolved rows are an ETF-proxy universe, not a claim about
    official index membership.
    """
    etf = await _instrument(db, symbol)
    profile = (
        await db.execute(select(ETFProfile).where(ETFProfile.instrument_id == etf.id))
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(404, detail={"code": "etf_profile_not_found", "symbol": etf.symbol})
    snapshot_query = holdings_snapshot_source_filter(
        select(ETFHoldingsSnapshot)
        .options(selectinload(ETFHoldingsSnapshot.rows))
        .where(ETFHoldingsSnapshot.etf_profile_id == profile.id)
    )
    if as_of is not None:
        snapshot_query = snapshot_query.where(
            ETFHoldingsSnapshot.composition_date <= as_of.date(),
            ETFHoldingsSnapshot.known_at.is_not(None),
            ETFHoldingsSnapshot.known_at <= as_of,
        )
    snapshot = (
        await db.execute(
            snapshot_query.order_by(
                ETFHoldingsSnapshot.composition_date.desc(),
                ETFHoldingsSnapshot.known_at.desc().nullslast(),
                ETFHoldingsSnapshot.id.desc(),
            ).limit(1)
        )
    ).scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(
            404, detail={"code": "etf_holdings_snapshot_not_found", "symbol": etf.symbol}
        )
    # Preserve the full disclosure universe for denominator and exclusion
    # reporting.  Filtering before this point made cash, derivatives, and
    # unresolved rows disappear from the constituent response, which could
    # overstate coverage and disagree with the industry/taxonomy endpoints.
    disclosed_rows = sorted(snapshot.rows, key=lambda item: item.position)
    holdings = [row for row in disclosed_rows if _holding_exclusion_code(row) is None]
    exclusions = [
        AnalysisWarning(
            code=code,
            message=_HOLDING_EXCLUSION_MESSAGES.get(code, "Holding excluded from equity analysis."),
            instrument_id=row.constituent_instrument_id,
        )
        for row in disclosed_rows
        for code in [_holding_exclusion_code(row)]
        if code is not None
    ]
    instrument_ids = [
        row.constituent_instrument_id for row in holdings if row.constituent_instrument_id
    ]
    instruments = {
        item.id: item
        for item in (
            await db.execute(select(Instrument).where(Instrument.id.in_(instrument_ids)))
        ).scalars()
    }
    benchmark_instrument = await _instrument(db, benchmark) if benchmark else etf
    market_instrument = await _instrument(db, market_benchmark) if market_benchmark else None
    comparison_ids = [benchmark_instrument.id]
    if market_instrument is not None and market_instrument.id not in comparison_ids:
        comparison_ids.append(market_instrument.id)
    bars_by_id = await _bars_by_instrument(
        db, [*instrument_ids, *comparison_ids], timeframe, adjusted
    )
    # A point-in-time membership snapshot must also use only observations that
    # were available by the requested cutoff.  Without this truncation a
    # historical holdings set could still be ranked using future bars.
    bars_by_id = _truncate_bars_at(bars_by_id, as_of)
    benchmark_bars = {bar.ts: bar for bar in bars_by_id.get(benchmark_instrument.id, [])}
    market_bars = (
        {bar.ts: bar for bar in bars_by_id.get(market_instrument.id, [])}
        if market_instrument
        else {}
    )
    rows: list[ETFConstituentSnapshotRowOut] = []
    covered = 0
    for holding in sorted(holdings, key=lambda item: item.position):
        instrument = instruments.get(holding.constituent_instrument_id)
        if instrument is None:
            exclusions.append(
                AnalysisWarning(
                    code="missing_instrument",
                    message="Holding refers to an unavailable canonical instrument.",
                    instrument_id=holding.constituent_instrument_id,
                )
            )
            continue
        bars = bars_by_id.get(instrument.id, [])
        latest = bars[-1] if bars else None
        if latest is None:
            warning = AnalysisWarning(
                code="no_bars", message="No local bars are available.", instrument_id=instrument.id
            )
            exclusions.append(warning)
            rows.append(
                ETFConstituentSnapshotRowOut(
                    instrument_id=instrument.id,
                    symbol=instrument.symbol,
                    name=instrument.name,
                    position=holding.position,
                    weight=holding.weight,
                    shares=holding.shares,
                    market_value=holding.market_value,
                    holding_type=holding.holding_type,
                    row_type=holding.row_type,
                    resolution_confidence=holding.resolution_confidence,
                    last=_cell(None, None, warning),
                    performance={period: _cell(None, None, warning) for period in _PERIODS},
                )
            )
            continue
        covered += 1
        performance = _performance_cells(bars, instrument.id)
        closes = [float(bar.close) for bar in bars]
        volume_ratio_50, volume_warning = _volume_ratio_50(bars, instrument.id)
        technical: dict[str, AnalysisCell] = {}
        for period in (20, 50, 200):
            technical[f"above_ma{period}"] = _cell(
                1.0
                if closes[-1] > _mean(closes[-period:])
                else 0.0
                if len(closes) >= period
                else None,
                latest,
                None
                if len(closes) >= period
                else AnalysisWarning(
                    code="insufficient_history",
                    message=f"Price versus SMA({period}) requires {period} bars.",
                    instrument_id=instrument.id,
                ),
            )
        if len(closes) >= 15:
            changes = [
                closes[index] - closes[index - 1] for index in range(len(closes) - 13, len(closes))
            ]
            gain, loss = (
                _mean([max(change, 0.0) for change in changes]),
                _mean([max(-change, 0.0) for change in changes]),
            )
            technical["rsi14"] = _cell(
                100.0 if loss == 0 else 100 - (100 / (1 + gain / loss)), latest
            )
        else:
            technical["rsi14"] = _cell(
                None,
                latest,
                AnalysisWarning(
                    code="insufficient_history",
                    message="RSI(14) requires 15 bars.",
                    instrument_id=instrument.id,
                ),
            )
        if len(closes) >= 252:
            window = closes[-252:]
            spread = max(window) - min(window)
            technical["position_52w"] = _cell(
                (closes[-1] - min(window)) / spread if spread else 1.0, latest
            )
        else:
            technical["position_52w"] = _cell(
                None,
                latest,
                AnalysisWarning(
                    code="insufficient_history",
                    message="52-week position requires 252 bars.",
                    instrument_id=instrument.id,
                ),
            )
        technical["volume_ratio_50"] = _cell(volume_ratio_50, latest, volume_warning)
        benchmark_bar = benchmark_bars.get(latest.ts)
        relative = (
            _cell(float(latest.close / benchmark_bar.close), latest)
            if benchmark_bar is not None and benchmark_bar.close != 0
            else _cell(
                None,
                latest,
                AnalysisWarning(
                    code="unaligned_benchmark",
                    message="No aligned benchmark bar is available.",
                    instrument_id=instrument.id,
                ),
            )
        )
        market_relative = None
        if market_instrument is not None:
            market_bar = market_bars.get(latest.ts)
            market_relative = (
                _cell(float(latest.close / market_bar.close), latest)
                if market_bar is not None and market_bar.close != 0
                else _cell(
                    None,
                    latest,
                    AnalysisWarning(
                        code="unaligned_market_benchmark",
                        message="No aligned market benchmark bar is available.",
                        instrument_id=instrument.id,
                    ),
                )
            )
        rows.append(
            ETFConstituentSnapshotRowOut(
                instrument_id=instrument.id,
                symbol=instrument.symbol,
                name=instrument.name,
                position=holding.position,
                weight=holding.weight,
                shares=holding.shares,
                market_value=holding.market_value,
                holding_type=holding.holding_type,
                row_type=holding.row_type,
                resolution_confidence=holding.resolution_confidence,
                last=_cell(float(latest.close), latest),
                performance=performance,
                relative_to_benchmark=relative,
                relative_to_market=market_relative,
                technical=technical,
            )
        )
    freshness, freshness_detail = await _batch_freshness(
        db, [*instrument_ids, *comparison_ids], timeframe, adjusted
    )
    return ETFConstituentSnapshotOut(
        group_key=f"etf-proxy:{etf.symbol}",
        timeframe=timeframe.value,
        as_of=as_of
        or max(
            (row.last.observation_time for row in rows if row.last.observation_time), default=None
        ),
        adjustment="split_adjusted" if adjusted else "raw",
        membership_version=snapshot.id,
        universe_provenance={
            "membership_semantics": "etf_proxy_membership",
            "etf_symbol": etf.symbol,
            "composition_date": snapshot.composition_date.isoformat(),
            "known_at": snapshot.known_at.isoformat() if snapshot.known_at else None,
            "requested_as_of": as_of.isoformat() if as_of else None,
        },
        freshness=freshness,
        freshness_detail=freshness_detail,
        coverage=covered / max(len(disclosed_rows), 1),
        exclusions=exclusions,
        rows=rows,
        etf_symbol=etf.symbol,
        benchmark=benchmark_instrument.symbol,
        market_benchmark=market_instrument.symbol if market_instrument else None,
        composition_date=snapshot.composition_date,
        known_at=snapshot.known_at,
        provenance=snapshot.provenance,
        source_provider=snapshot.source_provider,
        completeness_status=snapshot.completeness_status,
    )


@router.get(
    "/benchmark-families/{family_key}/constituents",
    response_model=ETFConstituentSnapshotOut,
)
async def benchmark_family_constituents(
    family_key: str,
    role: str = Query(default="cap_weight", pattern="^(cap_weight|equal_weight|value|growth)$"),
    market_benchmark: str | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Resolve a family leg into its source-labelled ETF-proxy holdings.

    The response retains ETF-proxy membership semantics.  A missing style/equal
    mapping or canonical identity is an explicit capability error, never a
    substitution with the family cap proxy or SPY.
    """

    group = (
        await db.execute(select(MarketGroup).where(MarketGroup.stable_key == family_key))
    ).scalar_one_or_none()
    if group is None or group.group_type != "benchmark_family":
        raise HTTPException(
            404,
            detail={"code": "benchmark_family_not_found", "family_key": family_key},
        )
    provenance = dict(group.provenance or {})
    proxy_mappings = provenance.get("proxy_mappings")
    mapping = proxy_mappings.get(role) if isinstance(proxy_mappings, Mapping) else None
    if not isinstance(mapping, Mapping) or not mapping.get("symbol"):
        raise HTTPException(
            404,
            detail={
                "code": "benchmark_mapping_unavailable",
                "family_key": family_key,
                "role": role,
            },
        )
    symbol = str(mapping["symbol"]).upper()
    instrument = (
        await db.execute(select(Instrument).where(Instrument.symbol == symbol))
    ).scalar_one_or_none()
    if instrument is None:
        raise HTTPException(
            404,
            detail={
                "code": "benchmark_proxy_unavailable",
                "family_key": family_key,
                "role": role,
                "symbol": symbol,
            },
        )
    cap_mapping = proxy_mappings.get("cap_weight") if isinstance(proxy_mappings, Mapping) else None
    cap_symbol = (
        str(cap_mapping.get("symbol")).upper()
        if isinstance(cap_mapping, Mapping) and cap_mapping.get("symbol")
        else symbol
    )
    benchmark_symbol = cap_symbol if role != "cap_weight" else symbol
    try:
        snapshot = await etf_constituent_snapshot(
            symbol=symbol,
            benchmark=benchmark_symbol,
            market_benchmark=market_benchmark,
            as_of=as_of,
            timeframe=timeframe,
            adjusted=adjusted,
            _=_,
            db=db,
        )
    except HTTPException as error:
        if error.status_code == 404:
            detail = error.detail if isinstance(error.detail, Mapping) else {}
            raise HTTPException(
                404,
                detail={
                    "code": "benchmark_holdings_unavailable",
                    "family_key": family_key,
                    "role": role,
                    "symbol": symbol,
                    "cause": detail.get("code", "etf_holdings_unavailable"),
                },
            ) from error
        raise
    return snapshot.model_copy(
        update={
            "group_key": f"benchmark-family:{family_key}:{role}",
            "universe_provenance": {
                **snapshot.universe_provenance,
                "family_key": family_key,
                "mapping_role": role,
                "mapping_label": mapping.get("label"),
                "mapping_verification_state": mapping.get("verification_state"),
                "family_official_index": (provenance.get("official_index") or {}).get("symbol"),
            },
        }
    )


@router.get(
    "/benchmark-families/{family_key}/concentration",
    response_model=BenchmarkFamilyConcentrationOut,
)
async def benchmark_family_concentration(
    family_key: str,
    rank_period: str = Query(default="1M", pattern="^(1D|1W|1M|3M|6M|YTD|1Y)$"),
    top_n: int = Query(default=10, ge=1, le=25),
    as_of: datetime | None = Query(default=None),
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Summarise reported-weight concentration and return dispersion per family leg."""

    group = (
        await db.execute(select(MarketGroup).where(MarketGroup.stable_key == family_key))
    ).scalar_one_or_none()
    if group is None or group.group_type != "benchmark_family":
        raise HTTPException(
            404,
            detail={"code": "benchmark_family_not_found", "family_key": family_key},
        )
    provenance = dict(group.provenance or {})
    official = provenance.get("official_index")
    mappings = provenance.get("proxy_mappings")
    mappings = mappings if isinstance(mappings, Mapping) else {}
    cap_mapping = mappings.get("cap_weight")
    cap_mapping = cap_mapping if isinstance(cap_mapping, Mapping) else {}
    cap_symbol = str(cap_mapping.get("symbol")).upper() if cap_mapping.get("symbol") else None
    roles: list[BenchmarkFamilyConcentrationRoleOut] = []
    exclusions: list[AnalysisWarning] = []
    for role in ("cap_weight", "equal_weight", "value", "growth"):
        mapping = mappings.get(role)
        mapping = mapping if isinstance(mapping, Mapping) else {}
        symbol = str(mapping.get("symbol")).upper() if mapping.get("symbol") else None
        label = str(mapping.get("label") or "No verified mapped proxy")
        verification_state = str(mapping.get("verification_state") or "not_verified")
        if not symbol:
            warning = AnalysisWarning(
                code="family_role_mapping_unavailable",
                message=f"No verified mapped proxy is available for the {role} leg.",
            )
            exclusions.append(warning)
            roles.append(
                BenchmarkFamilyConcentrationRoleOut(
                    role=role,
                    symbol=None,
                    label=label,
                    verification_state=verification_state,
                    available=False,
                    top_n=top_n,
                    coverage=0.0,
                    warnings=[warning],
                )
            )
            continue
        if not cap_symbol:
            warning = AnalysisWarning(
                code="family_cap_proxy_unavailable",
                message="The family cap proxy is unavailable; role-relative concentration cannot be evaluated.",
            )
            exclusions.append(warning)
            roles.append(
                BenchmarkFamilyConcentrationRoleOut(
                    role=role,
                    symbol=symbol,
                    label=label,
                    verification_state=verification_state,
                    available=False,
                    top_n=top_n,
                    coverage=0.0,
                    warnings=[warning],
                )
            )
            continue
        try:
            snapshot = await etf_constituent_snapshot(
                symbol=symbol,
                benchmark=cap_symbol,
                market_benchmark=None,
                as_of=as_of,
                timeframe=timeframe,
                adjusted=adjusted,
                _=_,
                db=db,
            )
        except HTTPException as error:
            detail = error.detail if isinstance(error.detail, Mapping) else {}
            warning = AnalysisWarning(
                code=str(detail.get("code") or "family_holdings_unavailable"),
                message=f"No usable holdings snapshot is available for {family_key} {role}.",
            )
            exclusions.append(warning)
            roles.append(
                BenchmarkFamilyConcentrationRoleOut(
                    role=role,
                    symbol=symbol,
                    label=label,
                    verification_state=verification_state,
                    available=False,
                    top_n=top_n,
                    coverage=0.0,
                    warnings=[warning],
                )
            )
            continue

        performance_rows = [
            (
                row,
                row.performance.get(rank_period).value
                if row.performance.get(rank_period)
                else None,
            )
            for row in snapshot.rows
        ]
        returns = [float(value) for _, value in performance_rows if value is not None]
        weighted_rows = [
            row for row in snapshot.rows if row.weight is not None and float(row.weight) >= 0
        ]
        reported_weight_total = sum(float(row.weight) for row in weighted_rows)
        ordered_by_weight = sorted(
            weighted_rows,
            key=lambda row: (-float(row.weight or 0), row.position),
        )
        if not ordered_by_weight:
            ordered_by_weight = sorted(snapshot.rows, key=lambda row: row.position)
        top_rows = ordered_by_weight[:top_n]
        hhi = (
            sum((float(row.weight or 0) / reported_weight_total) ** 2 for row in weighted_rows)
            if reported_weight_total > 0
            else None
        )
        stats = _distribution_stats(returns)
        member_outputs = [
            BenchmarkFamilyConcentrationMemberOut(
                instrument_id=row.instrument_id,
                symbol=row.symbol,
                name=row.name,
                position=row.position,
                weight=row.weight,
                performance=value,
                covered=value is not None,
            )
            for row, value in performance_rows
            if row in top_rows
        ]
        role_warnings = list(snapshot.exclusions)
        exclusions.extend(snapshot.exclusions)
        denominator = len(snapshot.rows) + len(snapshot.exclusions)
        roles.append(
            BenchmarkFamilyConcentrationRoleOut(
                role=role,
                symbol=symbol,
                label=label,
                verification_state=verification_state,
                available=bool(snapshot.rows),
                membership_version=snapshot.membership_version,
                composition_date=snapshot.composition_date,
                known_at=snapshot.known_at,
                weight_method=("reported_holdings_weights" if weighted_rows else "unavailable"),
                reported_weight_coverage=(
                    min(max(reported_weight_total, 0.0), 1.0) if weighted_rows else None
                ),
                top_n=top_n,
                top_n_weight=(
                    min(sum(float(row.weight or 0) for row in top_rows), 1.0)
                    if weighted_rows
                    else None
                ),
                hhi=hhi,
                effective_constituents=(1 / hhi if hhi else None),
                eligible_count=len(snapshot.rows),
                covered_count=len(returns),
                excluded_count=len(snapshot.exclusions),
                coverage=len(returns) / max(denominator, 1),
                members=member_outputs,
                warnings=role_warnings,
                **stats,
            )
        )

    freshness_ids = [
        instrument.id
        for instrument in (
            await db.execute(
                select(Instrument).where(
                    Instrument.symbol.in_([role.symbol for role in roles if role.symbol])
                )
            )
        ).scalars()
    ]
    freshness, freshness_detail = await _batch_freshness(db, freshness_ids, timeframe, adjusted)
    return BenchmarkFamilyConcentrationOut(
        family_key=family_key,
        official_index_symbol=(
            str(official.get("symbol") or "") if isinstance(official, Mapping) else ""
        ),
        timeframe=timeframe.value,
        adjustment="split_adjusted" if adjusted else "raw",
        as_of=as_of,
        rank_period=rank_period,
        top_n=top_n,
        roles=roles,
        exclusions=exclusions,
        freshness=freshness,
        freshness_detail=freshness_detail,
    )


@router.get(
    "/benchmark-families/{family_key}/concentration/history",
    response_model=BenchmarkFamilyConcentrationHistoryOut,
)
async def benchmark_family_concentration_history(
    family_key: str,
    rank_period: str = Query(default="1M", pattern="^(1D|1W|1M|3M|6M|YTD|1Y)$"),
    top_n: int = Query(default=10, ge=1, le=25),
    limit: int = Query(default=500, ge=1, le=5_000),
    as_of: datetime | None = Query(default=None),
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return point-in-time concentration and dispersion history per family role.

    Each timestamp selects the latest holdings disclosure whose composition date and
    known-at timestamp were already available at that timestamp.  Member return cells
    are calculated from observed local bars only; neither memberships nor returns are
    forward-filled across unavailable evidence.
    """

    family = (
        await db.execute(
            select(MarketGroup)
            .options(selectinload(MarketGroup.members))
            .where(MarketGroup.stable_key == family_key)
        )
    ).scalar_one_or_none()
    if family is None or family.group_type != "benchmark_family":
        raise HTTPException(
            404,
            detail={"code": "benchmark_family_not_found", "family_key": family_key},
        )
    provenance = dict(family.provenance or {})
    official = provenance.get("official_index")
    mappings = provenance.get("proxy_mappings")
    mappings = mappings if isinstance(mappings, Mapping) else {}
    derived_equal_metadata = provenance.get("derived_equal_weight")
    derived_equal_metadata = (
        derived_equal_metadata if isinstance(derived_equal_metadata, Mapping) else {}
    )
    roles: list[BenchmarkFamilyConcentrationHistoryRoleOut] = []
    exclusions: list[AnalysisWarning] = []
    freshness_ids: list[int] = []

    for role in ("cap_weight", "equal_weight", "value", "growth"):
        mapping = mappings.get(role)
        mapping = mapping if isinstance(mapping, Mapping) else {}
        symbol = str(mapping.get("symbol")).upper() if mapping.get("symbol") else None
        label = str(mapping.get("label") or "No verified mapped proxy")
        verification_state = str(mapping.get("verification_state") or "not_verified")
        if role == "equal_weight" and not symbol and derived_equal_metadata.get("allowed") is True:
            # A derived equal leg has no ETF holdings snapshot.  Select the
            # point-in-time group members at each bar instead, so membership
            # changes cannot leak backwards into earlier concentration points.
            constituent_relationships = {
                "constituent",
                "official_constituent",
                "etf_proxy_constituent",
            }
            all_constituent_members = [
                member
                for member in family.members
                if member.relationship_type in constituent_relationships
            ]
            member_ids = sorted({member.instrument_id for member in all_constituent_members})
            freshness_ids.extend(member_ids)
            bars_by_id = _truncate_bars_at(
                await _bars_by_instrument(db, member_ids, timeframe, adjusted), as_of
            )
            series_by_id = {
                instrument_id: _historical_return_series(bars)
                for instrument_id, bars in bars_by_id.items()
                if bars
            }
            timestamps = sorted(
                {timestamp for series in series_by_id.values() for timestamp in series}
            )[-limit:]
            points: list[BenchmarkFamilyConcentrationHistoryPointOut] = []
            role_exclusions: list[AnalysisWarning] = []
            for timestamp in timestamps:
                try:
                    active_members = [
                        member
                        for member in _group_members_at(
                            family, timestamp, allow_late_registered_group=True
                        )
                        if member.relationship_type in constituent_relationships
                    ]
                except HTTPException:
                    active_members = []
                active_ids = sorted({member.instrument_id for member in active_members})
                if not active_ids:
                    continue
                returns = [
                    float(series_by_id[instrument_id][timestamp][rank_period])
                    for instrument_id in active_ids
                    if instrument_id in series_by_id
                    and timestamp in series_by_id[instrument_id]
                    and series_by_id[instrument_id][timestamp].get(rank_period) is not None
                ]
                eligible_count = len(active_ids)
                covered_count = len(returns)
                hhi = 1 / eligible_count
                effective_date_values = [
                    member.effective_at.date()
                    for member in active_members
                    if member.effective_at is not None
                ]
                known_at_values = [
                    member.known_at for member in active_members if member.known_at is not None
                ]
                point_warnings: list[AnalysisWarning] = []
                if covered_count < eligible_count:
                    point_warnings.append(
                        AnalysisWarning(
                            code="derived_equal_partial_bars",
                            message=(
                                "Members without an observed local bar were excluded from "
                                "the concentration distribution at this timestamp."
                            ),
                        )
                    )
                points.append(
                    BenchmarkFamilyConcentrationHistoryPointOut(
                        timestamp=timestamp,
                        snapshot_id=None,
                        composition_date=(
                            max(effective_date_values) if effective_date_values else None
                        ),
                        known_at=max(known_at_values) if known_at_values else None,
                        membership_version=_group_membership_version(family, active_members),
                        membership_semantics="point_in_time_group_membership",
                        weight_method=str(
                            derived_equal_metadata.get("method")
                            or "equal_start_weight_point_in_time_membership"
                        ),
                        reported_weight_coverage=None,
                        top_n_weight=min(top_n / eligible_count, 1.0),
                        hhi=hhi,
                        effective_constituents=float(eligible_count),
                        eligible_count=eligible_count,
                        covered_count=covered_count,
                        excluded_count=0,
                        coverage=covered_count / max(eligible_count, 1),
                        warnings=point_warnings,
                        **_distribution_stats(returns),
                    )
                )
            if not points:
                warning = AnalysisWarning(
                    code="derived_equal_membership_unavailable",
                    message=(
                        f"No point-in-time derived equal-weight membership observations are "
                        f"available for {family_key}."
                    ),
                )
                role_exclusions.append(warning)
                exclusions.append(warning)
            roles.append(
                BenchmarkFamilyConcentrationHistoryRoleOut(
                    role=role,
                    symbol=None,
                    label=(
                        f"{family.name} derived equal-weight"
                        if label == "No verified mapped proxy"
                        else label
                    ),
                    verification_state="derived_policy",
                    available=bool(points),
                    membership_semantics="point_in_time_group_membership",
                    points=points,
                    exclusions=role_exclusions,
                )
            )
            continue
        if not symbol:
            warning = AnalysisWarning(
                code="family_role_mapping_unavailable",
                message=f"No verified mapped proxy is available for the {role} leg.",
            )
            exclusions.append(warning)
            roles.append(
                BenchmarkFamilyConcentrationHistoryRoleOut(
                    role=role,
                    symbol=None,
                    label=label,
                    verification_state=verification_state,
                    available=False,
                    exclusions=[warning],
                )
            )
            continue

        try:
            proxy = await _instrument(db, symbol)
        except HTTPException as error:
            detail = error.detail if isinstance(error.detail, Mapping) else {}
            warning = AnalysisWarning(
                code=str(detail.get("code") or "benchmark_proxy_unavailable"),
                message=f"No canonical proxy is available for {family_key} {role}.",
            )
            exclusions.append(warning)
            roles.append(
                BenchmarkFamilyConcentrationHistoryRoleOut(
                    role=role,
                    symbol=symbol,
                    label=label,
                    verification_state=verification_state,
                    available=False,
                    exclusions=[warning],
                )
            )
            continue

        profile = (
            await db.execute(select(ETFProfile).where(ETFProfile.instrument_id == proxy.id))
        ).scalar_one_or_none()
        if profile is None:
            warning = AnalysisWarning(
                code="etf_profile_not_found",
                message=f"No holdings profile is available for {family_key} {role}.",
            )
            exclusions.append(warning)
            roles.append(
                BenchmarkFamilyConcentrationHistoryRoleOut(
                    role=role,
                    symbol=symbol,
                    label=label,
                    verification_state=verification_state,
                    available=False,
                    exclusions=[warning],
                )
            )
            continue

        snapshots_statement = holdings_snapshot_source_filter(
            select(ETFHoldingsSnapshot)
            .options(selectinload(ETFHoldingsSnapshot.rows))
            .where(ETFHoldingsSnapshot.etf_profile_id == profile.id)
        ).where(ETFHoldingsSnapshot.known_at.is_not(None))
        if as_of is not None:
            snapshots_statement = snapshots_statement.where(
                ETFHoldingsSnapshot.composition_date <= as_of.date(),
                ETFHoldingsSnapshot.known_at <= as_of,
            )
        snapshots = list(
            (
                await db.execute(
                    snapshots_statement.order_by(
                        ETFHoldingsSnapshot.composition_date,
                        ETFHoldingsSnapshot.known_at,
                        ETFHoldingsSnapshot.id,
                    )
                )
            ).scalars()
        )
        if not snapshots:
            warning = AnalysisWarning(
                code="holdings_snapshot_not_found",
                message=f"No point-in-time holdings snapshots are available for {family_key} {role}.",
            )
            exclusions.append(warning)
            roles.append(
                BenchmarkFamilyConcentrationHistoryRoleOut(
                    role=role,
                    symbol=symbol,
                    label=label,
                    verification_state=verification_state,
                    available=False,
                    exclusions=[warning],
                )
            )
            continue

        instrument_ids = sorted(
            {
                holding.constituent_instrument_id
                for snapshot in snapshots
                for holding in snapshot.rows
                if holding.constituent_instrument_id and _holding_exclusion_code(holding) is None
            }
        )
        freshness_ids.extend(instrument_ids)
        bars_by_id = _truncate_bars_at(
            await _bars_by_instrument(db, instrument_ids, timeframe, adjusted), as_of
        )
        series_by_id = {
            instrument_id: _historical_return_series(bars)
            for instrument_id, bars in bars_by_id.items()
            if bars
        }
        timestamps = sorted(
            {timestamp for series in series_by_id.values() for timestamp in series}
        )[-limit:]
        points: list[BenchmarkFamilyConcentrationHistoryPointOut] = []
        role_exclusions: list[AnalysisWarning] = []
        for timestamp in timestamps:
            eligible_snapshots = [
                snapshot
                for snapshot in snapshots
                if snapshot.composition_date <= timestamp.date()
                and snapshot.known_at is not None
                and snapshot.known_at <= timestamp
            ]
            if not eligible_snapshots:
                continue
            snapshot = max(
                eligible_snapshots,
                key=lambda item: (
                    item.composition_date,
                    item.known_at,
                    item.id,
                ),
            )
            eligible_rows = [
                holding
                for holding in snapshot.rows
                if holding.constituent_instrument_id and _holding_exclusion_code(holding) is None
            ]
            excluded_count = len(snapshot.rows) - len(eligible_rows)
            performance_values = [
                series_by_id[holding.constituent_instrument_id][timestamp].get(rank_period)
                for holding in eligible_rows
                if holding.constituent_instrument_id in series_by_id
                and timestamp in series_by_id[holding.constituent_instrument_id]
            ]
            returns = [float(value) for value in performance_values if value is not None]
            weighted_rows = [
                holding
                for holding in eligible_rows
                if holding.weight is not None and float(holding.weight) >= 0
            ]
            reported_weight_total = sum(float(holding.weight) for holding in weighted_rows)
            ordered_by_weight = sorted(
                weighted_rows,
                key=lambda holding: (-float(holding.weight or 0), holding.position),
            )
            top_rows = ordered_by_weight[:top_n]
            hhi = (
                sum(
                    (float(holding.weight or 0) / reported_weight_total) ** 2
                    for holding in weighted_rows
                )
                if reported_weight_total > 0
                else None
            )
            stats = _distribution_stats(returns)
            points.append(
                BenchmarkFamilyConcentrationHistoryPointOut(
                    timestamp=timestamp,
                    snapshot_id=snapshot.id,
                    composition_date=snapshot.composition_date,
                    known_at=snapshot.known_at,
                    membership_version=snapshot.id,
                    weight_method=("reported_holdings_weights" if weighted_rows else "unavailable"),
                    reported_weight_coverage=(
                        min(max(reported_weight_total, 0.0), 1.0) if weighted_rows else None
                    ),
                    top_n_weight=(
                        min(sum(float(holding.weight or 0) for holding in top_rows), 1.0)
                        if weighted_rows
                        else None
                    ),
                    hhi=hhi,
                    effective_constituents=(1 / hhi if hhi else None),
                    eligible_count=len(eligible_rows),
                    covered_count=len(returns),
                    excluded_count=excluded_count,
                    coverage=len(returns) / max(len(eligible_rows), 1),
                    warnings=(
                        [
                            AnalysisWarning(
                                code="no_weight_data",
                                message="No reported holdings weights are available at this timestamp.",
                            )
                        ]
                        if not weighted_rows
                        else []
                    ),
                    **stats,
                )
            )
        if not points:
            warning = AnalysisWarning(
                code="no_aligned_history",
                message=f"No point-in-time concentration observations are available for {family_key} {role}.",
            )
            role_exclusions.append(warning)
            exclusions.append(warning)
        roles.append(
            BenchmarkFamilyConcentrationHistoryRoleOut(
                role=role,
                symbol=symbol,
                label=label,
                verification_state=verification_state,
                available=bool(points),
                points=points,
                exclusions=role_exclusions,
            )
        )

    freshness, freshness_detail = await _batch_freshness(
        db, sorted(set(freshness_ids)), timeframe, adjusted
    )
    return BenchmarkFamilyConcentrationHistoryOut(
        family_key=family_key,
        official_index_symbol=(
            str(official.get("symbol") or "") if isinstance(official, Mapping) else ""
        ),
        timeframe=timeframe.value,
        adjustment="split_adjusted" if adjusted else "raw",
        as_of=as_of,
        rank_period=rank_period,
        top_n=top_n,
        limit=limit,
        roles=roles,
        exclusions=exclusions,
        freshness=freshness,
        freshness_detail=freshness_detail,
    )


@router.get(
    "/benchmark-families/{family_key}/ratios",
    response_model=BenchmarkFamilyRatiosOut,
)
async def benchmark_family_ratios(
    family_key: str,
    role: str = Query(default="equal_weight", pattern="^(cap_weight|equal_weight|value|growth)$"),
    roles: str | None = Query(default=None),
    market_benchmark: str | None = Query(default=None),
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    as_of: datetime | None = Query(default=None),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return aligned family-leg ratios without substituting unavailable mappings."""

    group = (
        await db.execute(select(MarketGroup).where(MarketGroup.stable_key == family_key))
    ).scalar_one_or_none()
    if group is None or group.group_type != "benchmark_family":
        raise HTTPException(
            404,
            detail={"code": "benchmark_family_not_found", "family_key": family_key},
        )
    provenance = dict(group.provenance or {})
    official = provenance.get("official_index")
    mappings = provenance.get("proxy_mappings")
    if not isinstance(official, Mapping) or not isinstance(mappings, Mapping):
        raise HTTPException(
            422,
            detail={"code": "benchmark_family_metadata_missing", "family_key": family_key},
        )
    requested_roles = [role]
    batch_requested = roles is not None
    if roles is not None:
        requested_roles = [item.strip() for item in roles.split(",") if item.strip()]
        if not requested_roles or any(
            item not in {"cap_weight", "equal_weight", "value", "growth"}
            for item in requested_roles
        ):
            raise HTTPException(
                422,
                detail={
                    "code": "invalid_benchmark_roles",
                    "family_key": family_key,
                    "roles": roles,
                },
            )
        requested_roles = list(dict.fromkeys(requested_roles))
    selected_mappings = {
        selected_role: mappings.get(selected_role)
        for selected_role in requested_roles
        if isinstance(mappings.get(selected_role), Mapping)
        and mappings.get(selected_role, {}).get("symbol")
    }
    cap_mapping = mappings.get("cap_weight")
    exclusions: list[AnalysisWarning] = []
    missing_roles = [
        selected_role for selected_role in requested_roles if selected_role not in selected_mappings
    ]
    if missing_roles and not batch_requested:
        raise HTTPException(
            404,
            detail={
                "code": "benchmark_mapping_unavailable",
                "family_key": family_key,
                "role": missing_roles[0],
            },
        )
    for missing_role in missing_roles:
        exclusions.append(
            AnalysisWarning(
                code="benchmark_mapping_unavailable",
                message=f"No verified mapped proxy is available for the {missing_role} leg.",
            )
        )
    if not isinstance(cap_mapping, Mapping) or not cap_mapping.get("symbol"):
        if batch_requested:
            exclusions.append(
                AnalysisWarning(
                    code="benchmark_mapping_unavailable",
                    message="No verified cap-weighted proxy is available; cap-relative ratios were omitted.",
                )
            )
        else:
            raise HTTPException(
                404,
                detail={
                    "code": "benchmark_mapping_unavailable",
                    "family_key": family_key,
                    "role": "cap_weight",
                },
            )
    if not selected_mappings and batch_requested:
        members = _group_members_at(group, as_of)
        return BenchmarkFamilyRatiosOut(
            family_key=family_key,
            official_index_symbol=str(official.get("symbol") or ""),
            timeframe=timeframe.value,
            adjustment="split_adjusted" if adjusted else "raw",
            as_of=as_of,
            membership_version=_group_membership_version(group, members),
            universe_provenance={
                **_group_provenance(group, as_of),
                "requested_roles": requested_roles,
                "market_benchmark": market_benchmark.upper() if market_benchmark else None,
                "ratio_semantics": "aligned_close_ratio_without_forward_fill",
            },
            ratios=[],
            exclusions=exclusions,
            freshness="unavailable",
            freshness_detail={"ratio_count": 0},
        )
    cap_symbol = (
        str(cap_mapping["symbol"]).upper()
        if isinstance(cap_mapping, Mapping) and cap_mapping.get("symbol")
        else None
    )
    symbol_candidates = [
        str(selected_mapping["symbol"]).upper() for selected_mapping in selected_mappings.values()
    ]
    if cap_symbol:
        symbol_candidates.append(cap_symbol)
    if market_benchmark:
        symbol_candidates.append(market_benchmark.upper())
    symbols = set(symbol_candidates)
    instruments = {
        instrument.symbol.upper(): instrument
        for instrument in (
            await db.execute(select(Instrument).where(Instrument.symbol.in_(symbols)))
        ).scalars()
    }
    missing_symbols = [
        symbol for symbol in dict.fromkeys(symbol_candidates) if symbol not in instruments
    ]
    missing_market = bool(market_benchmark and market_benchmark.upper() not in instruments)
    if missing_market:
        raise HTTPException(
            404,
            detail={
                "code": "market_benchmark_unavailable",
                "family_key": family_key,
                "role": "market",
                "symbol": market_benchmark.upper(),
            },
        )
    if missing_symbols and not batch_requested:
        missing_symbol = missing_symbols[0]
        raise HTTPException(
            404,
            detail={
                "code": "benchmark_proxy_unavailable",
                "family_key": family_key,
                "role": role,
                "symbol": missing_symbol,
            },
        )
    available_roles = [
        selected_role
        for selected_role, selected_mapping in selected_mappings.items()
        if str(selected_mapping["symbol"]).upper() in instruments
    ]
    for selected_role in selected_mappings:
        if selected_role not in available_roles:
            exclusions.append(
                AnalysisWarning(
                    code="benchmark_proxy_unavailable",
                    message=f"The canonical proxy for the {selected_role} leg is unavailable.",
                )
            )
    if cap_symbol and cap_symbol not in instruments:
        exclusions.append(
            AnalysisWarning(
                code="benchmark_proxy_unavailable",
                message="The canonical cap-weighted proxy is unavailable; cap-relative ratios were omitted.",
            )
        )
    instrument_ids = [instrument.id for instrument in instruments.values()]
    bars_by_id = _truncate_bars_at(
        await _bars_by_instrument(db, instrument_ids, timeframe, adjusted), as_of
    )

    def ratio_result(
        *,
        primary_role: str,
        benchmark_role: str,
        primary_symbol: str,
        benchmark_symbol: str,
    ) -> BenchmarkFamilyRatioOut:
        primary = instruments[primary_symbol]
        benchmark = instruments[benchmark_symbol]
        primary_bars = bars_by_id.get(primary.id, [])
        benchmark_bars = bars_by_id.get(benchmark.id, [])
        primary_by_time = {bar.ts: bar for bar in primary_bars}
        benchmark_by_time = {bar.ts: bar for bar in benchmark_bars}
        timestamps = sorted(primary_by_time.keys() & benchmark_by_time.keys())
        points = [
            AnalysisPoint(
                timestamp=timestamp,
                value=float(primary_by_time[timestamp].close / benchmark_by_time[timestamp].close),
            )
            for timestamp in timestamps
            if benchmark_by_time[timestamp].close != 0
        ]
        maximum = max(len(primary_by_time), len(benchmark_by_time), 1)
        warnings: list[AnalysisWarning] = []
        if not points:
            warnings.append(
                AnalysisWarning(
                    code="no_aligned_bars",
                    message="No aligned bars are available for this family ratio.",
                )
            )
        elif len(points) < maximum:
            warnings.append(
                AnalysisWarning(
                    code="partial_overlap",
                    message="Only intersecting timestamps were used; gaps were not forward-filled.",
                )
            )
        return BenchmarkFamilyRatioOut(
            family_key=family_key,
            role=primary_role,
            symbol=primary_symbol,
            benchmark_role=benchmark_role,
            benchmark=benchmark_symbol,
            timeframe=timeframe.value,
            adjustment="split_adjusted" if adjusted else "raw",
            as_of=as_of or (points[-1].timestamp if points else None),
            points=points,
            coverage=len(points) / maximum,
            warnings=warnings,
            freshness="coverage_limited" if not points else "available",
            freshness_detail={
                "primary_bars": len(primary_bars),
                "benchmark_bars": len(benchmark_bars),
            },
        )

    ratios: list[BenchmarkFamilyRatioOut] = []
    for selected_role in available_roles:
        selected_symbol = str(selected_mappings[selected_role]["symbol"]).upper()
        if selected_role != "cap_weight" and cap_symbol and cap_symbol in instruments:
            ratios.append(
                ratio_result(
                    primary_role=selected_role,
                    benchmark_role="cap_weight",
                    primary_symbol=selected_symbol,
                    benchmark_symbol=cap_symbol,
                )
            )
        if market_benchmark:
            ratios.append(
                ratio_result(
                    primary_role=selected_role,
                    benchmark_role="market",
                    primary_symbol=selected_symbol,
                    benchmark_symbol=market_benchmark.upper(),
                )
            )
    members = _group_members_at(group, as_of)
    return BenchmarkFamilyRatiosOut(
        family_key=family_key,
        official_index_symbol=str(official.get("symbol") or ""),
        timeframe=timeframe.value,
        adjustment="split_adjusted" if adjusted else "raw",
        as_of=as_of,
        membership_version=_group_membership_version(group, members),
        universe_provenance={
            **_group_provenance(group, as_of),
            "selected_role": role if not batch_requested else None,
            "requested_roles": requested_roles,
            "selected_symbols": {
                selected_role: str(selected_mappings[selected_role]["symbol"]).upper()
                for selected_role in available_roles
            },
            "cap_symbol": cap_symbol,
            "market_benchmark": market_benchmark.upper() if market_benchmark else None,
            "ratio_semantics": "aligned_close_ratio_without_forward_fill",
        },
        ratios=ratios,
        exclusions=exclusions,
        freshness="available" if ratios and any(r.points for r in ratios) else "coverage_limited",
        freshness_detail={"ratio_count": len(ratios)},
    )


@router.get(
    "/benchmark-families/{family_key}/coverage",
    response_model=BenchmarkFamilyCoverageOut,
)
async def benchmark_family_coverage(
    family_key: str,
    as_of: datetime | None = Query(default=None),
    limit: int = Query(default=256, ge=1, le=512),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return dated holdings disclosures for each mapped family role.

    This is intentionally read-only and provider-neutral.  A missing mapping,
    canonical instrument, or dated snapshot is reported for that role only;
    another role (including SPY or QQQ) is never substituted.  When ``as_of``
    is supplied, the existing composition/known-at point-in-time policy is
    applied so a current disclosure cannot masquerade as historical evidence.
    """

    group = (
        await db.execute(
            select(MarketGroup)
            .options(selectinload(MarketGroup.members).selectinload(MarketGroupMember.instrument))
            .where(MarketGroup.stable_key == family_key)
        )
    ).scalar_one_or_none()
    if group is None or group.group_type != "benchmark_family":
        raise HTTPException(
            404,
            detail={"code": "benchmark_family_not_found", "family_key": family_key},
        )

    provenance = dict(group.provenance or {})
    official = provenance.get("official_index")
    if not isinstance(official, Mapping):
        raise HTTPException(
            422,
            detail={"code": "benchmark_family_metadata_missing", "family_key": family_key},
        )
    proxy_mappings = provenance.get("proxy_mappings")
    if not isinstance(proxy_mappings, Mapping):
        proxy_mappings = {}
    symbols = [
        str(mapping.get("symbol")).upper()
        for mapping in proxy_mappings.values()
        if isinstance(mapping, Mapping) and mapping.get("symbol")
    ]
    instruments = {
        instrument.symbol.upper(): instrument
        for instrument in (
            await db.execute(select(Instrument).where(Instrument.symbol.in_(symbols)))
        ).scalars()
    }

    profiles = {
        profile.instrument_id: profile
        for profile in (
            await db.execute(
                select(ETFProfile).where(
                    ETFProfile.instrument_id.in_(
                        [instrument.id for instrument in instruments.values()]
                    )
                )
            )
        ).scalars()
    }
    source_rows = (await db.execute(select(DataSource))).scalars().all()
    sources = {source.id: source for source in source_rows}
    sources_by_name = {
        source.name.strip().lower(): source
        for source in source_rows
        if source.name and source.name.strip()
    }
    entitlements = {
        (entitlement.data_source_id, entitlement.capability): entitlement
        for entitlement in (
            await db.execute(
                select(ProviderEntitlement).where(
                    ProviderEntitlement.capability.in_(
                        (ProviderCapability.UNIVERSE_DISCOVERY, ProviderCapability.PRICE_HISTORY)
                    )
                )
            )
        ).scalars()
    }
    adapter_states = {}
    profile_ids = [profile.id for profile in profiles.values()]
    if profile_ids:
        for state in (
            await db.execute(
                select(ETFHoldingsAdapterState)
                .where(ETFHoldingsAdapterState.etf_profile_id.in_(profile_ids))
                .order_by(
                    ETFHoldingsAdapterState.last_checked_at.desc().nullslast(),
                    ETFHoldingsAdapterState.id.desc(),
                )
            )
        ).scalars():
            adapter_states.setdefault(state.etf_profile_id, state)

    roles: list[BenchmarkFamilyCoverageRoleOut] = []
    exclusions: list[AnalysisWarning] = []
    role_count = 4
    covered_roles = 0
    for role in ("cap_weight", "equal_weight", "value", "growth"):
        mapping = proxy_mappings.get(role)
        mapping = mapping if isinstance(mapping, Mapping) else {}
        symbol = str(mapping.get("symbol")).upper() if mapping.get("symbol") else None
        instrument = instruments.get(symbol) if symbol else None
        profile = profiles.get(instrument.id) if instrument is not None else None
        adapter_state = adapter_states.get(profile.id) if profile is not None else None
        snapshots: list[BenchmarkFamilyCoverageSnapshotOut] = []
        member_bar_history = BenchmarkFamilyMemberBarHistoryOut(status="no_snapshot")
        continuity_status = "not_applicable"
        continuity_gaps: list[BenchmarkFamilyCoverageGapOut] = []
        continuity_snapshot_limit_reached = False
        selected_snapshot: ETFHoldingsSnapshot | None = None
        source: DataSource | None = None
        entitlement_source: DataSource | None = None
        holdings_entitlement: ProviderEntitlement | None = None
        price_entitlement: ProviderEntitlement | None = None
        route_adapter_key: str | None = None
        route_provider: str | None = None
        route_status = "not_configured"
        if symbol:
            route_metadata = known_etf_route_metadata(symbol)
            route_aliases = route_metadata.get("provider_aliases") or {}
            if isinstance(route_aliases, Mapping):
                route_adapter_key = str(route_aliases.get("holdings_adapter") or "").strip() or None
            route_adapter = get_holdings_adapter(route_adapter_key)
            if route_adapter is not None:
                route_provider = route_adapter.source_provider
                route_status = "configured"
            elif route_adapter_key:
                route_status = "not_registered"
        point_in_time_supported = False
        if instrument is None:
            status = "mapping_unavailable"
            exclusions.append(
                AnalysisWarning(
                    code="family_role_mapping_unavailable",
                    message=f"No canonical instrument is available for {family_key} {role}.",
                )
            )
        elif profile is None:
            # The canonical identity can exist before the ETF profile/holdings
            # route hydrates. Keep this role visible as pending, matching the
            # universal WatchlistSource contract, instead of collapsing it into
            # an apparently missing snapshot.
            status = "profile_not_loaded"
            exclusions.append(
                AnalysisWarning(
                    code="family_role_profile_unavailable",
                    message=f"No ETF profile is loaded for {family_key} {role}; holdings remain pending.",
                    instrument_id=instrument.id,
                )
            )
        else:
            statement = holdings_snapshot_source_filter(
                select(ETFHoldingsSnapshot)
                .join(ETFProfile, ETFProfile.id == ETFHoldingsSnapshot.etf_profile_id)
                .where(ETFProfile.instrument_id == instrument.id)
            )
            statement = _holdings_snapshot_at(statement, as_of)
            snapshot_rows = (
                (
                    await db.execute(
                        statement.order_by(
                            ETFHoldingsSnapshot.composition_date.desc(),
                            ETFHoldingsSnapshot.known_at.desc().nullslast(),
                            ETFHoldingsSnapshot.id.desc(),
                        ).limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            continuity_snapshot_limit_reached = len(snapshot_rows) >= limit
            snapshots = [
                BenchmarkFamilyCoverageSnapshotOut(
                    snapshot_id=row.id,
                    composition_date=row.composition_date,
                    as_of_date=row.as_of_date,
                    known_at=row.known_at,
                    provenance=row.provenance,
                    source_provider=row.source_provider,
                    source_quality=row.source_quality,
                    completeness_status=row.completeness_status,
                    row_count=row.row_count,
                    resolved_count=row.resolved_count,
                    unresolved_count=row.unresolved_count,
                )
                for row in snapshot_rows
            ]
            continuity = assess_observed_holdings_continuity(
                [snapshot.composition_date for snapshot in snapshots],
            )
            continuity_status = continuity.status
            continuity_gaps = [
                BenchmarkFamilyCoverageGapOut(
                    from_date=gap.from_date,
                    to_date=gap.to_date,
                    interval_days=gap.interval_days,
                )
                for gap in continuity.gaps
            ]
            resolved_snapshots = [snapshot for snapshot in snapshots if snapshot.resolved_count > 0]
            selected_snapshot = next(
                (row for row in snapshot_rows if row.resolved_count > 0),
                None,
            )
            source = sources.get(selected_snapshot.data_source_id) if selected_snapshot else None
            if selected_snapshot is not None:
                entitlement_source = (
                    sources_by_name.get(selected_snapshot.source_provider.strip().lower()) or source
                )
            if selected_snapshot is not None:
                holdings_entitlement = entitlements.get(
                    (
                        entitlement_source.id
                        if entitlement_source is not None
                        else selected_snapshot.data_source_id,
                        ProviderCapability.UNIVERSE_DISCOVERY,
                    )
                )
                price_entitlement = entitlements.get(
                    (
                        entitlement_source.id
                        if entitlement_source is not None
                        else selected_snapshot.data_source_id,
                        ProviderCapability.PRICE_HISTORY,
                    )
                )
            # A requested cutoff is not evidence that the role can answer it.
            # Keep point-in-time readiness false until at least one dated
            # holdings snapshot is actually available; otherwise a profile
            # with no local disclosures would be reported as historically
            # supported merely because the caller supplied ``as_of``.
            point_in_time_supported = bool(profile and resolved_snapshots)
            member_bar_history = await _family_member_bar_history(
                db,
                selected_snapshot,
                as_of=as_of,
            )
            status = (
                "available"
                if resolved_snapshots
                else "holdings_snapshot_unresolved"
                if snapshots
                else "no_snapshot"
            )
            if resolved_snapshots:
                covered_roles += 1
            elif snapshots:
                exclusions.append(
                    AnalysisWarning(
                        code="family_role_holdings_unresolved",
                        message=(
                            f"Dated holdings for {family_key} {role} contain no resolved "
                            "canonical members; the locked source remains pending."
                        ),
                        instrument_id=instrument.id,
                    )
                )
            else:
                exclusions.append(
                    AnalysisWarning(
                        code="family_role_holdings_unavailable",
                        message=f"No dated holdings snapshot is available for {family_key} {role}.",
                        instrument_id=instrument.id,
                    )
                )
            if continuity_gaps:
                exclusions.append(
                    AnalysisWarning(
                        code="family_role_holdings_continuity_gap",
                        message=(
                            f"Observed {family_key} {role} holdings disclosures contain "
                            f"{len(continuity_gaps)} interval(s) wider than "
                            f"{OBSERVED_CONTINUITY_MAX_INTERVAL_DAYS} days; this is not "
                            "proof of complete rebalance history."
                        ),
                        instrument_id=instrument.id,
                    )
                )
            if not point_in_time_supported and profile is not None:
                exclusions.append(
                    AnalysisWarning(
                        code="family_role_point_in_time_unavailable",
                        message=f"No dated holdings evidence is available for {family_key} {role}.",
                        instrument_id=instrument.id,
                    )
                )
        if source is None and adapter_state is not None:
            source = sources.get(adapter_state.data_source_id)
        if profile is not None and profile.adapter_key:
            route_adapter_key = profile.adapter_key
            route_adapter = get_holdings_adapter(route_adapter_key)
            if route_adapter is None:
                route_provider = None
                route_status = "not_registered"
            else:
                route_provider = route_adapter.source_provider
                route_status = "configured"
                if profile.adapter_status in {"success", "ready"}:
                    route_status = "ready"
                elif profile.adapter_status in {
                    "failure",
                    "needs_issuer_route",
                    "adapter_not_registered",
                    "holdings_adapter_unresolved",
                }:
                    route_status = profile.adapter_status
        if entitlement_source is None and source is not None:
            entitlement_source = source
        if entitlement_source is None and route_provider:
            entitlement_source = sources_by_name.get(route_provider.strip().lower())
        if entitlement_source is not None:
            if holdings_entitlement is None:
                holdings_entitlement = entitlements.get(
                    (entitlement_source.id, ProviderCapability.UNIVERSE_DISCOVERY)
                )
            if price_entitlement is None:
                price_entitlement = entitlements.get(
                    (entitlement_source.id, ProviderCapability.PRICE_HISTORY)
                )
        entitlement_candidates = [
            item for item in (holdings_entitlement, price_entitlement) if item
        ]
        entitlement_statuses = {
            capability.value: _entitlement_state(
                entitlement_source,
                entitlement,
                evaluation_at=as_of,
            )
            for capability, entitlement in (
                (ProviderCapability.UNIVERSE_DISCOVERY, holdings_entitlement),
                (ProviderCapability.PRICE_HISTORY, price_entitlement),
            )
            if entitlement is not None
        }
        entitlement_status = (
            "not_configured"
            if any(value == "not_configured" for value in entitlement_statuses.values())
            else "excluded"
            if any(value == "excluded" for value in entitlement_statuses.values())
            else "probe_failed"
            if any(value == "probe_failed" for value in entitlement_statuses.values())
            else "unreviewed"
            if any(value == "unreviewed" for value in entitlement_statuses.values())
            else "verified"
            if entitlement_candidates
            and all(value == "verified" for value in entitlement_statuses.values())
            else "unknown"
        )
        entitlement_record = next(
            (
                item
                for item in entitlement_candidates
                if item.capability == ProviderCapability.UNIVERSE_DISCOVERY
            ),
            next(iter(entitlement_candidates), None),
        )
        (
            member_count,
            weighted_member_count,
            weights_status,
            classified_member_count,
            classification_status,
        ) = await _family_member_metadata_readiness(db, selected_snapshot, as_of=as_of)
        composite_status, composite_reasons = _role_readiness(
            mapping_available=instrument is not None,
            profile_loaded=profile is not None,
            holdings_status=status,
            member_bar_status=member_bar_history.status,
            entitlement_status=entitlement_status,
            point_in_time_supported=point_in_time_supported,
            weights_status=weights_status,
            classification_status=classification_status,
        )
        roles.append(
            BenchmarkFamilyCoverageRoleOut(
                role=role,
                symbol=symbol,
                label=str(mapping.get("label") or "No verified mapped proxy"),
                verification_state=str(mapping.get("verification_state") or "not_verified"),
                instrument_id=instrument.id if instrument else None,
                adapter_key=profile.adapter_key if profile else None,
                adapter_status=profile.adapter_status if profile else None,
                adapter_confidence=profile.adapter_confidence if profile else None,
                holdings_route_adapter_key=route_adapter_key,
                holdings_route_provider=route_provider,
                holdings_route_status=route_status,
                available=instrument is not None,
                status=status,
                snapshots=snapshots,
                continuity_status=continuity_status,
                continuity_gap_count=len(continuity_gaps),
                continuity_max_interval_days=(
                    max((gap.interval_days for gap in continuity_gaps), default=None)
                ),
                continuity_gaps=continuity_gaps,
                continuity_snapshot_limit_reached=continuity_snapshot_limit_reached,
                member_bar_history=member_bar_history,
                entitlement_status=entitlement_status,
                entitlement_provider=entitlement_source.name if entitlement_source else None,
                entitlement_capabilities=entitlement_statuses,
                entitlement_revision=(
                    int(entitlement_record.revision) if entitlement_record else None
                ),
                entitlement_effective_at=(
                    entitlement_record.effective_at if entitlement_record else None
                ),
                entitlement_review_due_at=(
                    entitlement_record.review_due_at if entitlement_record else None
                ),
                entitlement_live_probe_status=(
                    entitlement_record.live_probe_status if entitlement_record else None
                ),
                holdings_refresh_status=(
                    adapter_state.status if adapter_state else "not_attempted"
                ),
                holdings_refresh_provider=(
                    selected_snapshot.source_provider
                    if selected_snapshot is not None
                    else adapter_state.adapter_key
                    if adapter_state is not None
                    else source.name
                    if source is not None
                    else None
                ),
                holdings_refresh_last_checked_at=(
                    adapter_state.last_checked_at if adapter_state else None
                ),
                holdings_refresh_last_success_at=(
                    adapter_state.last_success_at if adapter_state else None
                ),
                holdings_refresh_last_failure_at=(
                    adapter_state.last_failure_at if adapter_state else None
                ),
                holdings_refresh_failure_reason=(
                    adapter_state.failure_reason if adapter_state else None
                ),
                holdings_refresh_composition_date=(
                    adapter_state.composition_date if adapter_state else None
                ),
                point_in_time_supported=point_in_time_supported,
                member_count=member_count,
                weighted_member_count=weighted_member_count,
                weights_status=weights_status,
                classified_member_count=classified_member_count,
                classification_status=classification_status,
                history_ready=member_bar_history.status == "ready",
                composite_readiness_status=composite_status,
                composite_readiness_reasons=composite_reasons,
            )
        )

    selected_members = _group_members_at(group, as_of)
    return BenchmarkFamilyCoverageOut(
        family_key=family_key,
        name=group.name,
        official_index_symbol=str(official.get("symbol") or ""),
        official_index_name=str(official.get("name") or group.name),
        as_of=as_of,
        membership_version=_group_membership_version(group, selected_members),
        universe_provenance={
            **_group_provenance(group, as_of),
            "family_key": family_key,
            "coverage_semantics": "role_independent_dated_holdings_snapshots",
            "continuity_policy": "observed_snapshot_intervals_gt_45_days",
            "continuity_semantics": "diagnostic_of_returned_snapshot_dates_only",
            "point_in_time": as_of is not None,
            "snapshot_limit": limit,
        },
        coverage=covered_roles / role_count,
        roles=roles,
        exclusions=exclusions,
        freshness="available" if covered_roles else "coverage_limited",
        freshness_detail={"role_count": role_count, "covered_roles": covered_roles},
    )


@router.get(
    "/benchmark-families/readiness",
    response_model=BenchmarkFamilyReadinessOut,
)
async def benchmark_family_readiness(
    as_of: datetime | None = Query(default=None),
    limit: int = Query(default=256, ge=1, le=512),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return one bounded readiness matrix for every curated benchmark family.

    The matrix deliberately composes the existing role coverage contract.  It
    never calls a provider, invents an instrument, or substitutes a different
    family when a registry group has not yet been materialised.
    """

    families: list[BenchmarkFamilyCoverageOut] = []
    missing_families: list[str] = []
    for metadata in benchmark_family_registry():
        family_key = str(metadata["logical_key"])
        try:
            coverage = await benchmark_family_coverage(family_key, as_of, limit, None, db)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            missing_families.append(family_key)
            roles = [
                BenchmarkFamilyCoverageRoleOut(
                    role=role,
                    symbol=(mapping.get("symbol") if isinstance(mapping, Mapping) else None),
                    label=(
                        str(mapping.get("label") or "No verified mapped proxy")
                        if isinstance(mapping, Mapping)
                        else "No verified mapped proxy"
                    ),
                    verification_state=(
                        str(mapping.get("verification_state") or "not_verified")
                        if isinstance(mapping, Mapping)
                        else "not_verified"
                    ),
                    available=False,
                    status="mapping_unavailable",
                    composite_readiness_status="unavailable",
                    composite_readiness_reasons=["benchmark_family_not_materialised"],
                )
                for role in ("cap_weight", "equal_weight", "value", "growth")
                for mapping in [metadata.get(role)]
            ]
            coverage = BenchmarkFamilyCoverageOut(
                family_key=family_key,
                name=str(metadata.get("name") or family_key),
                official_index_symbol=str(metadata.get("official_index_symbol") or ""),
                official_index_name=str(
                    metadata.get("official_index_name") or metadata.get("name") or family_key
                ),
                as_of=as_of,
                membership_version=0,
                universe_provenance={
                    "family_key": family_key,
                    "registry_only": True,
                    "point_in_time": as_of is not None,
                },
                coverage=0,
                roles=roles,
                exclusions=[
                    AnalysisWarning(
                        code="benchmark_family_not_materialised",
                        message=f"No canonical market group is materialised for {family_key}.",
                    )
                ],
                freshness="coverage_limited",
                freshness_detail={"role_count": 4, "covered_roles": 0},
            )
        families.append(coverage)

    all_roles = [role for family in families for role in family.roles]
    availability = await latest_availability(db)
    provider_probe_evidence = [
        {
            "provider": item["provider"],
            "capability": item["capability"],
            "classification": item["classification"],
            "success": item["success"],
            "consecutive_failures": item["consecutive_failures"],
            "recovered": item["recovered"],
            "observed_at": item["observed_at"],
        }
        for item in availability
    ]
    ready_role_count = sum(role.composite_readiness_status == "ready" for role in all_roles)
    ready_family_count = sum(
        bool(family.roles)
        and all(role.composite_readiness_status == "ready" for role in family.roles)
        for family in families
    )
    role_count = len(all_roles)
    family_count = len(families)
    if family_count and ready_family_count == family_count:
        readiness_status = "ready"
    elif ready_role_count or any(family.coverage for family in families):
        readiness_status = "partial"
    else:
        readiness_status = "coverage_limited"
    return BenchmarkFamilyReadinessOut(
        as_of=as_of,
        snapshot_limit=limit,
        family_count=family_count,
        ready_family_count=ready_family_count,
        role_count=role_count,
        ready_role_count=ready_role_count,
        readiness_status=readiness_status,
        provider_probe_evidence=provider_probe_evidence,
        universe_provenance={
            "registry": "top_down_taxonomy",
            "family_keys": [family.family_key for family in families],
            "point_in_time": as_of is not None,
            "missing_families": missing_families,
            "coverage_semantics": "role_independent_dated_holdings_snapshots",
            "provider_calls": False,
            "provider_probe_count": len(provider_probe_evidence),
        },
        families=families,
        freshness="available" if readiness_status == "ready" else "coverage_limited",
        freshness_detail={
            "family_count": family_count,
            "ready_family_count": ready_family_count,
            "role_count": role_count,
            "ready_role_count": ready_role_count,
        },
    )


@router.get(
    "/benchmark-families/{family_key}/overview",
    response_model=BenchmarkFamilyOverviewOut,
)
async def benchmark_family_overview(
    family_key: str,
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    as_of: datetime | None = Query(default=None),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compare one family's configured cap/equal/style proxy legs.

    The cap leg is the benchmark only when its canonical identity exists.  A
    missing cap identity returns an unavailable, provenance-bearing response;
    this endpoint never substitutes SPY or QQQ for a different family.
    """

    group = (
        await db.execute(
            select(MarketGroup)
            .options(selectinload(MarketGroup.members).selectinload(MarketGroupMember.instrument))
            .where(MarketGroup.stable_key == family_key)
        )
    ).scalar_one_or_none()
    if group is None or group.group_type != "benchmark_family":
        raise HTTPException(
            404,
            detail={"code": "benchmark_family_not_found", "family_key": family_key},
        )

    provenance = dict(group.provenance or {})
    official = provenance.get("official_index")
    if not isinstance(official, Mapping):
        raise HTTPException(
            422,
            detail={"code": "benchmark_family_metadata_missing", "family_key": family_key},
        )
    proxy_mappings = provenance.get("proxy_mappings")
    if not isinstance(proxy_mappings, Mapping):
        proxy_mappings = {}
    symbols = [
        str(mapping.get("symbol")).upper()
        for mapping in proxy_mappings.values()
        if isinstance(mapping, Mapping) and mapping.get("symbol")
    ]
    instruments = {
        instrument.symbol.upper(): instrument
        for instrument in (
            await db.execute(select(Instrument).where(Instrument.symbol.in_(symbols)))
        ).scalars()
    }
    mapped_instrument_ids = [instrument.id for instrument in instruments.values()]
    holdings_statement = (
        holdings_snapshot_source_filter(
            select(ETFHoldingsSnapshot)
            .options(selectinload(ETFHoldingsSnapshot.etf_profile))
            .join(ETFProfile, ETFProfile.id == ETFHoldingsSnapshot.etf_profile_id)
            .where(ETFProfile.instrument_id.in_(mapped_instrument_ids))
        )
        if mapped_instrument_ids
        else None
    )
    if holdings_statement is not None and as_of is not None:
        holdings_statement = _holdings_snapshot_at(holdings_statement, as_of)
    holdings_snapshots = (
        (
            await db.execute(
                holdings_statement.order_by(
                    ETFHoldingsSnapshot.composition_date.desc(),
                    ETFHoldingsSnapshot.known_at.desc().nullslast(),
                    ETFHoldingsSnapshot.id.desc(),
                )
            )
        )
        .scalars()
        .all()
        if holdings_statement is not None
        else []
    )
    holdings_by_instrument: dict[int, ETFHoldingsSnapshot] = {}
    for snapshot in holdings_snapshots:
        instrument_id = snapshot.etf_profile.instrument_id if snapshot.etf_profile else None
        if instrument_id is not None and instrument_id not in holdings_by_instrument:
            holdings_by_instrument[instrument_id] = snapshot
    selected_members = _group_members_at(group, as_of)
    cap_mapping = proxy_mappings.get("cap_weight")
    cap_symbol = (
        str(cap_mapping.get("symbol")).upper()
        if isinstance(cap_mapping, Mapping) and cap_mapping.get("symbol")
        else None
    )
    cap_instrument = instruments.get(cap_symbol) if cap_symbol else None

    if cap_instrument is not None:
        snapshot = await group_snapshot(
            group_key=family_key,
            benchmark=cap_instrument.symbol,
            timeframe=timeframe,
            adjusted=adjusted,
            as_of=as_of,
            _=_,
            db=db,
        )
        rows = snapshot.rows
        membership_version = snapshot.membership_version
        snapshot_as_of = snapshot.as_of
        coverage = snapshot.coverage
        exclusions = snapshot.exclusions
        freshness = snapshot.freshness
        freshness_detail = snapshot.freshness_detail
        universe_provenance = snapshot.universe_provenance
    else:
        membership_version = _group_membership_version(group, selected_members)
        rows = []
        snapshot_as_of = None
        coverage = 0.0
        freshness = "unavailable"
        freshness_detail = {}
        universe_provenance = _group_provenance(group, as_of)
        exclusions = [
            AnalysisWarning(
                code="cap_proxy_unavailable",
                message=(
                    f"No canonical cap-weighted proxy is available for {family_key}; "
                    "no other family proxy was substituted."
                ),
            )
        ]

    mappings: list[BenchmarkFamilyMappingOut] = []
    for role in ("cap_weight", "equal_weight", "value", "growth"):
        mapping = proxy_mappings.get(role)
        mapping = mapping if isinstance(mapping, Mapping) else {}
        symbol = str(mapping.get("symbol")).upper() if mapping.get("symbol") else None
        instrument = instruments.get(symbol) if symbol else None
        holdings_snapshot = holdings_by_instrument.get(instrument.id) if instrument else None
        mappings.append(
            BenchmarkFamilyMappingOut(
                role=role,
                symbol=symbol,
                label=str(mapping.get("label") or "No verified mapped proxy"),
                verification_state=str(mapping.get("verification_state") or "not_verified"),
                source_url=str(mapping.get("source_url")) if mapping.get("source_url") else None,
                instrument_id=instrument.id if instrument else None,
                available=instrument is not None,
                holdings_snapshot_id=holdings_snapshot.id if holdings_snapshot else None,
                holdings_available=holdings_snapshot is not None,
                holdings_composition_date=(
                    holdings_snapshot.composition_date if holdings_snapshot else None
                ),
                holdings_known_at=holdings_snapshot.known_at if holdings_snapshot else None,
                holdings_source_provider=(
                    holdings_snapshot.source_provider if holdings_snapshot else None
                ),
                holdings_completeness_status=(
                    holdings_snapshot.completeness_status if holdings_snapshot else None
                ),
                holdings_row_count=holdings_snapshot.row_count if holdings_snapshot else None,
                holdings_resolved_count=holdings_snapshot.resolved_count
                if holdings_snapshot
                else None,
                holdings_unresolved_count=(
                    holdings_snapshot.unresolved_count if holdings_snapshot else None
                ),
                holdings_total_weight=holdings_snapshot.total_weight if holdings_snapshot else None,
            )
        )

    return BenchmarkFamilyOverviewOut(
        family_key=family_key,
        name=group.name,
        official_index_symbol=str(official.get("symbol") or ""),
        official_index_name=str(official.get("name") or group.name),
        timeframe=timeframe.value,
        adjustment="split_adjusted" if adjusted else "raw",
        as_of=snapshot_as_of,
        membership_version=membership_version,
        universe_provenance={
            **universe_provenance,
            "family_key": family_key,
            "cap_proxy_symbol": cap_symbol,
            "cap_proxy_available": cap_instrument is not None,
            "official_index_series_policy": official.get("series_policy"),
        },
        coverage=coverage,
        exclusions=exclusions,
        mappings=mappings,
        derived_equal_weight=dict(provenance.get("derived_equal_weight") or {}),
        rows=rows,
        freshness=freshness,
        freshness_detail=freshness_detail,
    )


@router.get(
    "/benchmark-families/{family_key}/technicals",
    response_model=BenchmarkFamilyTechnicalsOut,
)
async def benchmark_family_technicals(
    family_key: str,
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    as_of: datetime | None = Query(default=None),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return role-aware technicals without collapsing unavailable family legs.

    Each configured cap/equal/value/growth mapping is evaluated independently.  A
    missing mapping or canonical proxy remains a warning on that role; no other
    family or market symbol is substituted.
    """

    group = (
        await db.execute(select(MarketGroup).where(MarketGroup.stable_key == family_key))
    ).scalar_one_or_none()
    if group is None or group.group_type != "benchmark_family":
        raise HTTPException(
            404,
            detail={"code": "benchmark_family_not_found", "family_key": family_key},
        )
    provenance = dict(group.provenance or {})
    official = provenance.get("official_index")
    mappings = provenance.get("proxy_mappings")
    if not isinstance(official, Mapping) or not isinstance(mappings, Mapping):
        raise HTTPException(
            422,
            detail={"code": "benchmark_family_metadata_missing", "family_key": family_key},
        )

    symbols = [
        str(mapping.get("symbol")).upper()
        for mapping in mappings.values()
        if isinstance(mapping, Mapping) and mapping.get("symbol")
    ]
    instruments = {
        instrument.symbol.upper(): instrument
        for instrument in (
            await db.execute(select(Instrument).where(Instrument.symbol.in_(symbols)))
        ).scalars()
    }
    roles: list[BenchmarkFamilyTechnicalRoleOut] = []
    exclusions: list[AnalysisWarning] = []
    available_count = 0
    current_count = 0
    selected_members = _group_members_at(group, as_of)

    for role in ("cap_weight", "equal_weight", "value", "growth"):
        mapping = mappings.get(role)
        mapping = mapping if isinstance(mapping, Mapping) else {}
        symbol = str(mapping.get("symbol")).upper() if mapping.get("symbol") else None
        label = str(mapping.get("label") or "No verified mapped proxy")
        verification_state = str(mapping.get("verification_state") or "not_verified")
        instrument = instruments.get(symbol) if symbol else None
        if not symbol:
            warning = AnalysisWarning(
                code="family_role_mapping_unavailable",
                message=f"No verified mapped proxy is available for the {role} leg.",
            )
            exclusions.append(warning)
            roles.append(
                BenchmarkFamilyTechnicalRoleOut(
                    role=role,
                    symbol=None,
                    label=label,
                    verification_state=verification_state,
                    available=False,
                    warnings=[warning],
                )
            )
            continue
        if instrument is None:
            warning = AnalysisWarning(
                code="benchmark_proxy_unavailable",
                message=f"The canonical proxy for the {role} leg is unavailable.",
            )
            exclusions.append(warning)
            roles.append(
                BenchmarkFamilyTechnicalRoleOut(
                    role=role,
                    symbol=symbol,
                    label=label,
                    verification_state=verification_state,
                    available=False,
                    warnings=[warning],
                )
            )
            continue

        snapshot = await instrument_technical_snapshot(
            symbol=symbol,
            timeframe=timeframe,
            adjusted=adjusted,
            as_of=as_of,
            _=_,
            db=db,
        )
        available_count += 1
        exclusions.extend(snapshot.warnings)
        if snapshot.last is not None:
            current_count += 1
        roles.append(
            BenchmarkFamilyTechnicalRoleOut(
                role=role,
                symbol=symbol,
                label=label,
                verification_state=verification_state,
                available=True,
                as_of=snapshot.as_of,
                last=snapshot.last,
                rsi14=snapshot.rsi14,
                sma20=snapshot.sma20,
                sma50=snapshot.sma50,
                sma200=snapshot.sma200,
                position_52w=snapshot.position_52w,
                volume_ratio_50=snapshot.volume_ratio_50,
                freshness=snapshot.freshness,
                warnings=snapshot.warnings,
            )
        )

    return BenchmarkFamilyTechnicalsOut(
        family_key=family_key,
        official_index_symbol=str(official.get("symbol") or ""),
        timeframe=timeframe.value,
        adjustment="split_adjusted" if adjusted else "raw",
        as_of=as_of or max((role.as_of for role in roles if role.as_of), default=None),
        membership_version=_group_membership_version(group, selected_members),
        universe_provenance={
            **_group_provenance(group, as_of),
            "family_key": family_key,
            "technical_semantics": "role_independent_local_ohlcv_snapshot",
            "requested_roles": ["cap_weight", "equal_weight", "value", "growth"],
        },
        roles=roles,
        exclusions=exclusions,
        freshness=(
            "unavailable"
            if not available_count
            else "current"
            if current_count == available_count
            else "partial"
        ),
        freshness_detail={
            "role_count": 4,
            "available_roles": available_count,
            "roles_with_bars": current_count,
        },
    )


@router.get(
    "/benchmark-families/{family_key}/breadth",
    response_model=BenchmarkFamilyBreadthOut,
)
async def benchmark_family_breadth(
    family_key: str,
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    as_of: datetime | None = Query(default=None),
    near_threshold: float = Query(default=0.01, ge=0, le=0.5),
    new_high_lookback: int = Query(default=20, ge=2, le=252),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compare standard participation metrics across family role universes.

    This is a convenience batch view over the same point-in-time ETF-proxy
    universe and evaluator used by configurable generic breadth. It does not
    replace the user-authored breadth contract or fabricate unavailable legs.
    """

    family = (
        await db.execute(select(MarketGroup).where(MarketGroup.stable_key == family_key))
    ).scalar_one_or_none()
    if family is None or family.group_type != "benchmark_family":
        raise HTTPException(
            404,
            detail={"code": "benchmark_family_not_found", "family_key": family_key},
        )
    provenance = dict(family.provenance or {})
    official = provenance.get("official_index")
    mappings = provenance.get("proxy_mappings")
    if not isinstance(official, Mapping) or not isinstance(mappings, Mapping):
        raise HTTPException(
            422,
            detail={"code": "benchmark_family_metadata_missing", "family_key": family_key},
        )

    cap_mapping = mappings.get("cap_weight")
    cap_symbol = (
        str(cap_mapping.get("symbol")).upper()
        if isinstance(cap_mapping, Mapping) and cap_mapping.get("symbol")
        else None
    )
    cap_instrument = None
    if cap_symbol:
        try:
            cap_instrument = await _instrument(db, cap_symbol)
        except HTTPException as error:
            if error.status_code != 404:
                raise
    cap_bars = (
        _truncate_bars_at(
            await _bars_by_instrument(db, [cap_instrument.id], timeframe, adjusted), as_of
        ).get(cap_instrument.id, [])
        if cap_instrument
        else []
    )
    roles: list[BenchmarkFamilyBreadthRoleOut] = []
    exclusions: list[AnalysisWarning] = []

    def metric(
        results: list[object],
        aggregate: dict[str, int | float],
    ) -> BenchmarkFamilyBreadthMetricOut:
        metric_exclusions = [
            _generic_breadth_warning(str(result.exclusion_code), result.instrument_id)
            for result in results
            if getattr(result, "exclusion_code", None)
        ]
        return BenchmarkFamilyBreadthMetricOut(
            percentage=aggregate.get("percentage"),
            requested_count=int(aggregate.get("requested_count", 0)),
            eligible_count=int(aggregate.get("eligible_count", 0)),
            excluded_count=int(aggregate.get("excluded_count", 0)),
            coverage=float(aggregate.get("coverage", 0.0)),
            exclusions=metric_exclusions,
        )

    for role in ("cap_weight", "equal_weight", "value", "growth"):
        mapping = mappings.get(role)
        mapping = mapping if isinstance(mapping, Mapping) else {}
        symbol = str(mapping.get("symbol")).upper() if mapping.get("symbol") else None
        label = str(mapping.get("label") or "No verified mapped proxy")
        verification_state = str(mapping.get("verification_state") or "not_verified")
        if not symbol:
            warning = AnalysisWarning(
                code="family_role_mapping_unavailable",
                message=f"No verified mapped proxy is available for the {role} leg.",
            )
            exclusions.append(warning)
            roles.append(
                BenchmarkFamilyBreadthRoleOut(
                    role=role,
                    symbol=None,
                    label=label,
                    verification_state=verification_state,
                    available=False,
                    exclusions=[warning],
                )
            )
            continue

        definition = BreadthDefinitionRequest(
            universe=BreadthUniverseRequest(
                kind="benchmark_family", key=family_key, role=role, point_in_time=True
            ),
            condition=BreadthConditionRequest(kind="above_moving_average", params={"period": 20}),
            timeframe=timeframe.value,
            adjusted=adjusted,
            as_of=as_of,
        )
        try:
            (
                members,
                _,
                universe_warnings,
                universe_provenance,
                membership_payload,
            ) = await _resolve_benchmark_family_breadth_universe(definition, db)
        except HTTPException as error:
            detail = error.detail if isinstance(error.detail, Mapping) else {}
            warning = AnalysisWarning(
                code=str(detail.get("code") or "family_breadth_unavailable"),
                message=str(detail.get("message") or f"Breadth is unavailable for the {role} leg."),
            )
            exclusions.append(warning)
            roles.append(
                BenchmarkFamilyBreadthRoleOut(
                    role=role,
                    symbol=symbol,
                    label=label,
                    verification_state=verification_state,
                    available=False,
                    exclusions=[warning],
                )
            )
            continue
        instrument_ids = [member.instrument_id for member in members]
        bars_by_id = _truncate_bars_at(
            await _bars_by_instrument(db, instrument_ids, timeframe, adjusted), as_of
        )
        role_exclusions = list(universe_warnings)

        def evaluate(condition: dict[str, object]) -> BenchmarkFamilyBreadthMetricOut:
            results, aggregate = evaluate_breadth(
                members, bars_by_id, condition, benchmark_bars=cap_bars or None
            )
            return metric(results, aggregate)

        above_ma = {
            f"ma{period}": evaluate({"kind": "above_moving_average", "params": {"period": period}})
            for period in (20, 50, 200)
        }
        near_high = evaluate(
            {
                "kind": "within_52_week_high",
                "params": {"lookback": 252, "threshold": near_threshold, "direction": "high"},
            }
        )
        new_high = evaluate(
            {
                "kind": "new_high_low",
                "params": {"lookback": new_high_lookback, "direction": "high"},
            }
        )
        trend_up = evaluate(
            {
                "kind": "trend",
                "params": {"fast_period": 20, "slow_period": 50, "direction": "up"},
            }
        )
        relative = None
        if role != "cap_weight" and cap_bars:
            relative = evaluate(
                {"kind": "relative_strength", "params": {"lookback": 20, "threshold": 0}}
            )
        role_exclusions.extend(
            warning
            for item in [*above_ma.values(), near_high, new_high, trend_up, relative]
            if item is not None
            for warning in item.exclusions
        )
        membership_version = _generic_membership_version(membership_payload)
        roles.append(
            BenchmarkFamilyBreadthRoleOut(
                role=role,
                symbol=symbol,
                label=label,
                verification_state=verification_state,
                available=True,
                membership_version=membership_version,
                universe_provenance=universe_provenance,
                above_ma=above_ma,
                near_52w_high=near_high,
                new_high=new_high,
                trend_up=trend_up,
                relative_strength_to_cap=relative,
                exclusions=role_exclusions,
            )
        )

    selected_members = _group_members_at(family, as_of)
    return BenchmarkFamilyBreadthOut(
        family_key=family_key,
        official_index_symbol=str(official.get("symbol") or ""),
        timeframe=timeframe.value,
        adjustment="split_adjusted" if adjusted else "raw",
        as_of=as_of,
        near_threshold=near_threshold,
        new_high_lookback=new_high_lookback,
        membership_version=_group_membership_version(family, selected_members),
        universe_provenance={
            **_group_provenance(family, as_of),
            "family_key": family_key,
            "breadth_semantics": "standard_role_participation_batch_over_point_in_time_holdings",
            "requested_roles": ["cap_weight", "equal_weight", "value", "growth"],
        },
        roles=roles,
        exclusions=exclusions,
        freshness="available" if any(role.available for role in roles) else "unavailable",
        freshness_detail={
            "role_count": 4,
            "available_roles": sum(role.available for role in roles),
        },
    )


@router.get(
    "/benchmark-families/{family_key}/breadth/history",
    response_model=BenchmarkFamilyBreadthHistoryOut,
)
async def benchmark_family_breadth_history(
    family_key: str,
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    limit: int = Query(default=500, ge=1, le=5_000),
    as_of: datetime | None = Query(default=None),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return aligned SMA participation history for every available family role.

    Each role is evaluated against its own point-in-time holdings. Missing bars
    are excluded at each timestamp; no current membership or alternate family
    role is forward-filled into the historical series.
    """

    family = (
        await db.execute(select(MarketGroup).where(MarketGroup.stable_key == family_key))
    ).scalar_one_or_none()
    if family is None or family.group_type != "benchmark_family":
        raise HTTPException(
            404,
            detail={"code": "benchmark_family_not_found", "family_key": family_key},
        )
    provenance = dict(family.provenance or {})
    official = provenance.get("official_index")
    mappings = provenance.get("proxy_mappings")
    if not isinstance(official, Mapping) or not isinstance(mappings, Mapping):
        raise HTTPException(
            422,
            detail={"code": "benchmark_family_metadata_missing", "family_key": family_key},
        )

    roles: list[BenchmarkFamilyBreadthHistoryRoleOut] = []
    exclusions: list[AnalysisWarning] = []
    freshness_ids: list[int] = []
    for role in ("cap_weight", "equal_weight", "value", "growth"):
        mapping = mappings.get(role)
        mapping = mapping if isinstance(mapping, Mapping) else {}
        symbol = str(mapping.get("symbol")).upper() if mapping.get("symbol") else None
        label = str(mapping.get("label") or "No verified mapped proxy")
        verification_state = str(mapping.get("verification_state") or "not_verified")
        if not symbol:
            warning = AnalysisWarning(
                code="family_role_mapping_unavailable",
                message=f"No verified mapped proxy is available for the {role} leg.",
            )
            exclusions.append(warning)
            roles.append(
                BenchmarkFamilyBreadthHistoryRoleOut(
                    role=role,
                    symbol=None,
                    label=label,
                    verification_state=verification_state,
                    available=False,
                    exclusions=[warning],
                )
            )
            continue

        definition = BreadthDefinitionRequest(
            universe=BreadthUniverseRequest(
                kind="benchmark_family", key=family_key, role=role, point_in_time=True
            ),
            condition=BreadthConditionRequest(kind="above_moving_average", params={"period": 20}),
            timeframe=timeframe.value,
            adjusted=adjusted,
            as_of=as_of,
        )
        try:
            (
                members,
                member_ids,
                universe_warnings,
                universe_provenance,
                membership_payload,
            ) = await _resolve_benchmark_family_breadth_universe(definition, db)
        except HTTPException as error:
            detail = error.detail if isinstance(error.detail, Mapping) else {}
            warning = AnalysisWarning(
                code=str(detail.get("code") or "family_breadth_unavailable"),
                message=str(
                    detail.get("message") or f"Breadth history is unavailable for the {role} leg."
                ),
            )
            exclusions.append(warning)
            roles.append(
                BenchmarkFamilyBreadthHistoryRoleOut(
                    role=role,
                    symbol=symbol,
                    label=label,
                    verification_state=verification_state,
                    available=False,
                    exclusions=[warning],
                )
            )
            continue

        bars_by_id = _truncate_bars_at(
            await _bars_by_instrument(db, member_ids, timeframe, adjusted), as_of
        )
        freshness_ids.extend(member_ids)
        by_timestamp: dict[datetime, dict[str, tuple[float | None, float]]] = {}
        role_exclusions = list(universe_warnings)
        for period in (20, 50, 200):
            raw_points = evaluate_breadth_history(
                members,
                bars_by_id,
                {"kind": "above_moving_average", "params": {"period": period}},
                limit=limit,
            )
            for raw_point in raw_points:
                timestamp = raw_point["timestamp"]
                by_timestamp.setdefault(timestamp, {})[f"ma{period}"] = (
                    raw_point["percentage"],
                    raw_point["coverage"],
                )
                role_exclusions.extend(
                    warning
                    for result in raw_point["members"]
                    if result.exclusion_code
                    for warning in [
                        _generic_breadth_warning(result.exclusion_code, result.instrument_id)
                    ]
                )
        points = [
            BreadthHistoryPoint(
                timestamp=timestamp,
                above_ma={
                    period: values.get(period, (None, 0.0))[0]
                    for period in ("ma20", "ma50", "ma200")
                },
                coverage={
                    period: values.get(period, (None, 0.0))[1]
                    for period in ("ma20", "ma50", "ma200")
                },
            )
            for timestamp, values in sorted(by_timestamp.items())
        ][-limit:]
        roles.append(
            BenchmarkFamilyBreadthHistoryRoleOut(
                role=role,
                symbol=symbol,
                label=label,
                verification_state=verification_state,
                available=True,
                membership_version=_generic_membership_version(membership_payload),
                universe_provenance=universe_provenance,
                points=points,
                exclusions=role_exclusions,
            )
        )

    freshness, freshness_detail = await _batch_freshness(
        db, sorted(set(freshness_ids)), timeframe, adjusted
    )
    return BenchmarkFamilyBreadthHistoryOut(
        family_key=family_key,
        official_index_symbol=str(official.get("symbol") or ""),
        timeframe=timeframe.value,
        adjustment="split_adjusted" if adjusted else "raw",
        as_of=as_of,
        limit=limit,
        roles=roles,
        exclusions=exclusions,
        freshness=freshness,
        freshness_detail=freshness_detail,
    )


@router.get(
    "/benchmark-families/ranking/history",
    response_model=CrossFamilyRankingHistoryOut,
)
async def cross_family_ranking_history(
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    rank_period: str = Query(default="1M", pattern="^(1D|1W|1M|3M|6M|YTD|1Y)$"),
    families: str | None = Query(default=None),
    benchmark: str | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5_000),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return historical family performance/rank curves from observed local bars only."""

    requested = {item.strip() for item in (families.split(",") if families else []) if item.strip()}
    query = select(MarketGroup).where(MarketGroup.group_type == "benchmark_family")
    if requested:
        query = query.where(MarketGroup.stable_key.in_(requested))
    groups = list((await db.execute(query.order_by(MarketGroup.stable_key))).scalars())
    found = {group.stable_key for group in groups}
    if requested and found != requested:
        raise HTTPException(
            404,
            detail={
                "code": "benchmark_family_not_found",
                "family_keys": sorted(requested - found),
            },
        )
    if not groups:
        raise HTTPException(404, detail={"code": "benchmark_families_not_found"})

    benchmark_instrument = await _instrument(db, benchmark) if benchmark else None
    cap_instruments: dict[str, Instrument] = {}
    exclusions: list[AnalysisWarning] = []
    for group in groups:
        mappings = (group.provenance or {}).get("proxy_mappings", {})
        mapping = mappings.get("cap_weight") if isinstance(mappings, Mapping) else None
        symbol = mapping.get("symbol") if isinstance(mapping, Mapping) else None
        if not symbol:
            continue
        try:
            cap_instruments[group.stable_key] = await _instrument(db, str(symbol))
        except HTTPException as error:
            if error.status_code != 404:
                raise
            exclusions.append(
                AnalysisWarning(
                    code="instrument_not_found",
                    message=f"No canonical cap proxy is available for {group.stable_key}.",
                )
            )

    instrument_ids = [instrument.id for instrument in cap_instruments.values()]
    if benchmark_instrument:
        instrument_ids.append(benchmark_instrument.id)
    bars_by_id = _truncate_bars_at(
        await _bars_by_instrument(db, instrument_ids, timeframe, adjusted),
        as_of,
    )
    benchmark_series = (
        _historical_return_series(bars_by_id.get(benchmark_instrument.id, []))
        if benchmark_instrument
        else {}
    )
    rows: list[CrossFamilyRankingHistoryRowOut] = []
    rank_values: dict[datetime, dict[str, float]] = defaultdict(dict)
    pending: list[CrossFamilyRankingHistoryRowOut] = []
    for group in groups:
        provenance = dict(group.provenance or {})
        official = provenance.get("official_index")
        mappings = provenance.get("proxy_mappings")
        mapping = mappings.get("cap_weight") if isinstance(mappings, Mapping) else None
        mapping = mapping if isinstance(mapping, Mapping) else {}
        symbol = str(mapping.get("symbol")).upper() if mapping.get("symbol") else None
        label = str(mapping.get("label") or "No verified mapped proxy")
        instrument = cap_instruments.get(group.stable_key)
        bars = bars_by_id.get(instrument.id, []) if instrument else []
        series = _historical_return_series(bars) if bars else {}
        warnings: list[AnalysisWarning] = []
        if instrument is None:
            warnings.append(
                AnalysisWarning(
                    code="family_cap_unavailable",
                    message="The family has no canonical cap proxy or local bars.",
                )
            )
        elif not bars:
            warnings.append(
                AnalysisWarning(
                    code="no_bars",
                    message="No canonical cap-proxy bars are available.",
                    instrument_id=instrument.id,
                )
            )
        points: list[CrossFamilyRankingHistoryPoint] = []
        for timestamp in sorted(series)[-limit:]:
            performance = series[timestamp]
            relative = {
                period: (
                    value - benchmark_series.get(timestamp, {}).get(period)
                    if value is not None
                    and benchmark_series.get(timestamp, {}).get(period) is not None
                    else None
                )
                for period, value in performance.items()
            }
            value = performance.get(rank_period)
            if value is not None:
                rank_values[timestamp][group.stable_key] = value
            points.append(
                CrossFamilyRankingHistoryPoint(
                    timestamp=timestamp,
                    performance=performance,
                    relative_performance=relative,
                )
            )
        pending.append(
            CrossFamilyRankingHistoryRowOut(
                family_key=group.stable_key,
                family_name=group.name,
                official_index_symbol=(
                    str(official.get("symbol") or "") if isinstance(official, Mapping) else ""
                ),
                symbol=symbol,
                label=label,
                available=bool(series),
                coverage=(
                    sum(1 for cells in series.values() if cells.get(rank_period) is not None)
                    / max(len(series), 1)
                ),
                points=points,
                warnings=warnings,
            )
        )
    for row in pending:
        for point in row.points:
            ranked = sorted(
                rank_values.get(point.timestamp, {}).items(),
                key=lambda item: item[1],
                reverse=True,
            )
            rank_by_family = {family_key: index for index, (family_key, _) in enumerate(ranked, 1)}
            point.rank = rank_by_family.get(row.family_key)
        rows.append(row)
    freshness, freshness_detail = await _batch_freshness(db, instrument_ids, timeframe, adjusted)
    return CrossFamilyRankingHistoryOut(
        timeframe=timeframe.value,
        adjustment="split_adjusted" if adjusted else "raw",
        as_of=as_of,
        benchmark=benchmark_instrument.symbol if benchmark_instrument else None,
        rank_period=rank_period,
        limit=limit,
        rows=rows,
        exclusions=exclusions,
        freshness=freshness,
        freshness_detail=freshness_detail,
    )


@router.get(
    "/benchmark-families/ranking",
    response_model=CrossFamilyRankingOut,
)
async def cross_family_ranking(
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    rank_period: str = Query(default="1M", pattern="^(1D|1W|1M|3M|6M|YTD|1Y)$"),
    families: str | None = Query(default=None),
    benchmark: str | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rank all selected benchmark-family cap legs on one aligned contract."""

    requested = {item.strip() for item in (families.split(",") if families else []) if item.strip()}
    query = select(MarketGroup).where(MarketGroup.group_type == "benchmark_family")
    if requested:
        query = query.where(MarketGroup.stable_key.in_(requested))
    groups = list((await db.execute(query.order_by(MarketGroup.stable_key))).scalars())
    if requested and {group.stable_key for group in groups} != requested:
        missing = sorted(requested - {group.stable_key for group in groups})
        raise HTTPException(
            404,
            detail={"code": "benchmark_family_not_found", "family_keys": missing},
        )
    if not groups:
        raise HTTPException(404, detail={"code": "benchmark_families_not_found"})

    benchmark_instrument = None
    if benchmark:
        benchmark_instrument = await _instrument(db, benchmark)
    cap_instruments: dict[str, Instrument] = {}
    exclusions: list[AnalysisWarning] = []
    for group in groups:
        mappings = (group.provenance or {}).get("proxy_mappings", {})
        mapping = mappings.get("cap_weight") if isinstance(mappings, Mapping) else None
        symbol = mapping.get("symbol") if isinstance(mapping, Mapping) else None
        if not symbol:
            continue
        try:
            cap_instruments[group.stable_key] = await _instrument(db, str(symbol))
        except HTTPException as error:
            if error.status_code != 404:
                raise
            exclusions.append(
                AnalysisWarning(
                    code="instrument_not_found",
                    message=f"No canonical cap proxy is available for {group.stable_key}.",
                )
            )
    bars_by_id = _truncate_bars_at(
        await _bars_by_instrument(
            db,
            [
                *[instrument.id for instrument in cap_instruments.values()],
                *([benchmark_instrument.id] if benchmark_instrument else []),
            ],
            timeframe,
            adjusted,
        ),
        as_of,
    )
    benchmark_cells = (
        _aggregate_series_cells(
            [(bar.ts, float(bar.close)) for bar in bars_by_id.get(benchmark_instrument.id, [])],
            benchmark_instrument.id,
        )
        if benchmark_instrument
        else {}
    )
    rows: list[CrossFamilyRankingRowOut] = []
    for group in groups:
        provenance = dict(group.provenance or {})
        official = provenance.get("official_index")
        mappings = provenance.get("proxy_mappings")
        mapping = mappings.get("cap_weight") if isinstance(mappings, Mapping) else None
        mapping = mapping if isinstance(mapping, Mapping) else {}
        symbol = str(mapping.get("symbol")).upper() if mapping.get("symbol") else None
        label = str(mapping.get("label") or "No verified mapped proxy")
        instrument = cap_instruments.get(group.stable_key)
        if instrument is None:
            rows.append(
                CrossFamilyRankingRowOut(
                    family_key=group.stable_key,
                    family_name=group.name,
                    official_index_symbol=str(official.get("symbol") or "")
                    if isinstance(official, Mapping)
                    else "",
                    symbol=symbol,
                    label=label,
                    available=False,
                    warnings=[
                        AnalysisWarning(
                            code="family_cap_unavailable",
                            message="The family has no canonical cap proxy or local bars.",
                        )
                    ],
                )
            )
            continue
        cells = _aggregate_series_cells(
            [(bar.ts, float(bar.close)) for bar in bars_by_id.get(instrument.id, [])],
            instrument.id,
        )
        rows.append(
            CrossFamilyRankingRowOut(
                family_key=group.stable_key,
                family_name=group.name,
                official_index_symbol=str(official.get("symbol") or "")
                if isinstance(official, Mapping)
                else "",
                symbol=symbol,
                label=label,
                available=bool(cells),
                performance={period: cell.value for period, cell in cells.items()},
                relative_performance={
                    period: (
                        cell.value - benchmark_cells[period].value
                        if cell.value is not None
                        and benchmark_cells.get(period) is not None
                        and benchmark_cells[period].value is not None
                        else None
                    )
                    for period, cell in cells.items()
                },
                warnings=[cell.warning for cell in cells.values() if cell.warning is not None],
            )
        )
    ranked = sorted(
        (row for row in rows if row.available and row.performance.get(rank_period) is not None),
        key=lambda row: float(row.performance[rank_period]),  # type: ignore[arg-type]
        reverse=True,
    )
    for rank, row in enumerate(ranked, start=1):
        row.rank = rank
    freshness, freshness_detail = await _batch_freshness(
        db,
        [
            *[instrument.id for instrument in cap_instruments.values()],
            *([benchmark_instrument.id] if benchmark_instrument else []),
        ],
        timeframe,
        adjusted,
    )
    return CrossFamilyRankingOut(
        timeframe=timeframe.value,
        adjustment="split_adjusted" if adjusted else "raw",
        as_of=as_of,
        benchmark=benchmark_instrument.symbol if benchmark_instrument else None,
        rank_period=rank_period,
        rows=rows,
        exclusions=exclusions,
        freshness=freshness,
        freshness_detail=freshness_detail,
    )


@router.get(
    "/benchmark-families/{family_key}/ranking",
    response_model=BenchmarkFamilyRankingOut,
)
async def benchmark_family_ranking(
    family_key: str,
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    rank_period: str = Query(default="1M", pattern="^(1D|1W|1M|3M|6M|YTD|1Y)$"),
    as_of: datetime | None = Query(default=None),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rank mapped family roles by transparent local performance cells."""

    family = (
        await db.execute(select(MarketGroup).where(MarketGroup.stable_key == family_key))
    ).scalar_one_or_none()
    if family is None or family.group_type != "benchmark_family":
        raise HTTPException(
            404,
            detail={"code": "benchmark_family_not_found", "family_key": family_key},
        )
    provenance = dict(family.provenance or {})
    official = provenance.get("official_index")
    mappings = provenance.get("proxy_mappings")
    if not isinstance(official, Mapping) or not isinstance(mappings, Mapping):
        raise HTTPException(
            422,
            detail={"code": "benchmark_family_metadata_missing", "family_key": family_key},
        )

    cap_mapping = mappings.get("cap_weight")
    benchmark_symbol = (
        str(cap_mapping.get("symbol")).upper()
        if isinstance(cap_mapping, Mapping) and cap_mapping.get("symbol")
        else None
    )
    instrument_by_role: dict[str, Instrument] = {}
    warnings: list[AnalysisWarning] = []
    for role in ("cap_weight", "equal_weight", "value", "growth"):
        mapping = mappings.get(role)
        if not isinstance(mapping, Mapping) or not mapping.get("symbol"):
            continue
        try:
            instrument_by_role[role] = await _instrument(db, str(mapping["symbol"]))
        except HTTPException as error:
            if error.status_code != 404:
                raise
            warnings.append(
                AnalysisWarning(
                    code="instrument_not_found",
                    message=f"No canonical instrument is available for the {role} leg.",
                )
            )
    bars_by_id = _truncate_bars_at(
        await _bars_by_instrument(
            db, [instrument.id for instrument in instrument_by_role.values()], timeframe, adjusted
        ),
        as_of,
    )
    role_cells: dict[str, dict[str, AnalysisCell]] = {}
    rows: list[BenchmarkFamilyRankingRoleOut] = []
    for role in ("cap_weight", "equal_weight", "value", "growth"):
        mapping = mappings.get(role)
        mapping = mapping if isinstance(mapping, Mapping) else {}
        symbol = str(mapping.get("symbol")).upper() if mapping.get("symbol") else None
        label = str(mapping.get("label") or "No verified mapped proxy")
        verification_state = str(mapping.get("verification_state") or "not_verified")
        instrument = instrument_by_role.get(role)
        if instrument is None:
            rows.append(
                BenchmarkFamilyRankingRoleOut(
                    role=role,
                    symbol=symbol,
                    label=label,
                    verification_state=verification_state,
                    available=False,
                    warnings=[
                        AnalysisWarning(
                            code="family_role_unavailable",
                            message="The mapped role has no canonical instrument or bars.",
                        )
                    ],
                )
            )
            continue
        values = [
            (bar.ts, float(bar.close))
            for bar in bars_by_id.get(instrument.id, [])
            if bar.close is not None
        ]
        cells = _aggregate_series_cells(values, instrument.id)
        role_cells[role] = cells
        rows.append(
            BenchmarkFamilyRankingRoleOut(
                role=role,
                symbol=symbol,
                label=label,
                verification_state=verification_state,
                available=bool(values),
                performance={period: cell.value for period, cell in cells.items()},
                warnings=[cell.warning for cell in cells.values() if cell.warning is not None],
            )
        )
    cap_cells = role_cells.get("cap_weight", {})
    for row in rows:
        cells = role_cells.get(row.role, {})
        row.relative_performance = {
            period: (
                cell.value - cap_cells[period].value
                if cell.value is not None
                and cap_cells.get(period) is not None
                and cap_cells[period].value is not None
                else None
            )
            for period, cell in cells.items()
        }
    ranked = sorted(
        (row for row in rows if row.available and row.performance.get(rank_period) is not None),
        key=lambda row: float(row.performance[rank_period]),  # type: ignore[arg-type]
        reverse=True,
    )
    for rank, row in enumerate(ranked, start=1):
        row.rank = rank
    freshness, freshness_detail = await _batch_freshness(
        db, [instrument.id for instrument in instrument_by_role.values()], timeframe, adjusted
    )
    return BenchmarkFamilyRankingOut(
        family_key=family_key,
        official_index_symbol=str(official.get("symbol") or ""),
        benchmark=benchmark_symbol,
        timeframe=timeframe.value,
        adjustment="split_adjusted" if adjusted else "raw",
        as_of=as_of,
        rank_period=rank_period,
        roles=rows,
        exclusions=warnings,
        freshness=freshness,
        freshness_detail=freshness_detail,
    )


@router.get(
    "/benchmark-families/{family_key}/derived-equal-weight",
    response_model=BenchmarkFamilyDerivedEqualWeightOut,
)
async def benchmark_family_derived_equal_weight(
    family_key: str,
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    as_of: datetime | None = Query(default=None),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Build a labelled equal-weight series from point-in-time family members.

    Proxy mapping rows are never treated as constituents.  A family must have
    explicit constituent membership rows (official or clearly-labelled ETF
    proxy membership) before a derived series can be calculated.
    """

    group = (
        await db.execute(
            select(MarketGroup)
            .options(selectinload(MarketGroup.members))
            .where(MarketGroup.stable_key == family_key)
        )
    ).scalar_one_or_none()
    if group is None or group.group_type != "benchmark_family":
        raise HTTPException(
            404,
            detail={"code": "benchmark_family_not_found", "family_key": family_key},
        )

    provenance = dict(group.provenance or {})
    official = provenance.get("official_index")
    if not isinstance(official, Mapping):
        raise HTTPException(
            422,
            detail={"code": "benchmark_family_metadata_missing", "family_key": family_key},
        )
    method_metadata = provenance.get("derived_equal_weight")
    if not isinstance(method_metadata, Mapping) or not method_metadata.get("allowed"):
        raise HTTPException(
            422,
            detail={
                "code": "derived_equal_weight_not_allowed",
                "family_key": family_key,
            },
        )

    members = _group_members_at(group, as_of, allow_late_registered_group=True)
    constituent_members = [
        member
        for member in members
        if member.relationship_type
        in {"constituent", "official_constituent", "etf_proxy_constituent"}
    ]
    membership_version = _group_membership_version(group, constituent_members)
    member_ids = [member.instrument_id for member in constituent_members]
    bars_by_id = _truncate_bars_at(
        await _bars_by_instrument(db, member_ids, timeframe, adjusted), as_of
    )
    covered_member_count = sum(1 for instrument_id in member_ids if bars_by_id.get(instrument_id))
    series = _equal_weight_series(bars_by_id, member_ids)
    exclusions: list[AnalysisWarning] = []
    if not constituent_members:
        exclusions.append(
            AnalysisWarning(
                code="derived_equal_membership_unavailable",
                message=(
                    "No point-in-time constituent membership is available; proxy mapping rows "
                    "were not used as constituents."
                ),
            )
        )
    elif not series:
        exclusions.append(
            AnalysisWarning(
                code="derived_equal_no_bars",
                message="No aligned local bars are available for the eligible members.",
            )
        )
    if covered_member_count < len(constituent_members):
        exclusions.append(
            AnalysisWarning(
                code="derived_equal_partial_bars",
                message="Members without local bars were excluded from the aligned series.",
            )
        )
    freshness, freshness_detail = await _batch_freshness(db, member_ids, timeframe, adjusted)
    return BenchmarkFamilyDerivedEqualWeightOut(
        family_key=family_key,
        name=group.name,
        official_index_symbol=str(official.get("symbol") or ""),
        timeframe=timeframe.value,
        adjustment="split_adjusted" if adjusted else "raw",
        as_of=series[-1][0] if series else as_of,
        membership_version=membership_version,
        universe_provenance={
            **_group_provenance(group, as_of),
            "membership_semantics": "point_in_time_constituent_derived_equal_weight",
            "member_count": len(constituent_members),
            "covered_member_count": covered_member_count,
            "weight_method": str(method_metadata.get("method") or "declared_equal_weight"),
            "official_index_symbol": official.get("symbol"),
        },
        method=str(method_metadata.get("method") or "declared_equal_weight"),
        member_count=len(constituent_members),
        covered_member_count=covered_member_count,
        coverage=covered_member_count / max(len(constituent_members), 1),
        points=[AnalysisPoint(timestamp=timestamp, value=value) for timestamp, value in series],
        exclusions=exclusions,
        freshness=freshness,
        freshness_detail=freshness_detail,
    )


@router.get("/groups/{group_key}/snapshot", response_model=GroupSnapshotOut)
async def group_snapshot(
    group_key: str,
    benchmark: str | None = Query(default=None),
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    as_of: datetime | None = Query(default=None),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    group = (
        await db.execute(
            select(MarketGroup)
            .options(selectinload(MarketGroup.members))
            .where(MarketGroup.stable_key == group_key)
        )
    ).scalar_one_or_none()
    if group is None:
        raise HTTPException(404, detail={"code": "market_group_not_found", "group_key": group_key})
    requested_as_of = as_of
    members = _group_members_at(group, requested_as_of)
    instrument_ids = [member.instrument_id for member in members]
    instruments = {
        item.id: item
        for item in (
            await db.execute(select(Instrument).where(Instrument.id.in_(instrument_ids)))
        ).scalars()
    }
    benchmark_instrument = await _instrument(db, benchmark) if benchmark else None
    all_ids = instrument_ids + ([benchmark_instrument.id] if benchmark_instrument else [])
    bars_by_id = _truncate_bars_at(
        await _bars_by_instrument(db, all_ids, timeframe, adjusted), as_of
    )
    benchmark_bars = (
        {bar.ts: bar for bar in bars_by_id.get(benchmark_instrument.id, [])}
        if benchmark_instrument
        else {}
    )
    latest_year = max(
        (bar.ts.year for bars in bars_by_id.values() for bar in bars),
        default=datetime.now(UTC).year,
    )
    calendar_years = list(range(latest_year - _CALENDAR_YEAR_LOOKBACK + 1, latest_year + 1))
    rows: list[GroupSnapshotRow] = []
    exclusions: list[AnalysisWarning] = []
    covered = 0
    for member in sorted(members, key=lambda item: item.position):
        instrument = instruments.get(member.instrument_id)
        if instrument is None:
            exclusions.append(
                AnalysisWarning(
                    code="missing_instrument",
                    message="Membership refers to an unavailable canonical instrument.",
                    instrument_id=member.instrument_id,
                )
            )
            continue
        bars = bars_by_id.get(instrument.id, [])
        latest = bars[-1] if bars else None
        if latest is None:
            warning = AnalysisWarning(
                code="no_bars", message="No local bars are available.", instrument_id=instrument.id
            )
            exclusions.append(warning)
            rows.append(
                GroupSnapshotRow(
                    instrument_id=instrument.id,
                    symbol=instrument.symbol,
                    name=instrument.name,
                    last=_cell(None, None, warning),
                    performance={period: _cell(None, None, warning) for period in _PERIODS},
                    calendar_year_performance={
                        str(year): _cell(None, None, warning) for year in calendar_years
                    },
                )
            )
            continue
        covered += 1
        performance = _performance_cells(bars, instrument.id)
        calendar_year_performance = _calendar_year_cells(bars, instrument.id, calendar_years)
        closes = [float(bar.close) for bar in bars]
        volume_ratio_50, volume_warning = _volume_ratio_50(bars, instrument.id)
        technical: dict[str, AnalysisCell] = {}
        for period in (20, 50, 200):
            key = f"above_ma{period}"
            if len(closes) < period:
                technical[key] = _cell(
                    None,
                    latest,
                    AnalysisWarning(
                        code="insufficient_history",
                        message=f"Price versus SMA({period}) requires {period} bars.",
                        instrument_id=instrument.id,
                    ),
                )
            else:
                average = _mean(closes[-period:])
                technical[key] = _cell(1.0 if closes[-1] > average else 0.0, latest)
        if len(closes) >= 15:
            changes = [
                closes[index] - closes[index - 1] for index in range(len(closes) - 13, len(closes))
            ]
            gain = _mean([max(change, 0.0) for change in changes])
            loss = _mean([max(-change, 0.0) for change in changes])
            technical["rsi14"] = _cell(
                100.0 if loss == 0 else 100 - (100 / (1 + gain / loss)), latest
            )
        else:
            technical["rsi14"] = _cell(
                None,
                latest,
                AnalysisWarning(
                    code="insufficient_history",
                    message="RSI(14) requires 15 bars.",
                    instrument_id=instrument.id,
                ),
            )
        if len(closes) >= 252:
            window = closes[-252:]
            spread = max(window) - min(window)
            technical["position_52w"] = _cell(
                (closes[-1] - min(window)) / spread if spread else 1.0, latest
            )
        else:
            technical["position_52w"] = _cell(
                None,
                latest,
                AnalysisWarning(
                    code="insufficient_history",
                    message="52-week position requires 252 bars.",
                    instrument_id=instrument.id,
                ),
            )
        technical["volume_ratio_50"] = _cell(volume_ratio_50, latest, volume_warning)
        relative: AnalysisCell | None = None
        if benchmark_instrument:
            benchmark_bar = benchmark_bars.get(latest.ts)
            if benchmark_bar is None or benchmark_bar.close == 0:
                relative = _cell(
                    None,
                    latest,
                    AnalysisWarning(
                        code="unaligned_benchmark",
                        message="No aligned benchmark bar is available.",
                        instrument_id=instrument.id,
                    ),
                )
            else:
                relative = _cell(float(latest.close / benchmark_bar.close), latest)
        rows.append(
            GroupSnapshotRow(
                instrument_id=instrument.id,
                symbol=instrument.symbol,
                name=instrument.name,
                last=_cell(float(latest.close), latest),
                performance=performance,
                calendar_year_performance=calendar_year_performance,
                relative_to_benchmark=relative,
                technical=technical,
            )
        )
    freshness, freshness_detail = await _batch_freshness(db, instrument_ids, timeframe, adjusted)
    return GroupSnapshotOut(
        group_key=group.stable_key,
        timeframe=timeframe.value,
        as_of=max(
            (row.last.observation_time for row in rows if row.last.observation_time), default=None
        ),
        adjustment="split_adjusted" if adjusted else "raw",
        membership_version=_group_membership_version(group, members),
        universe_provenance=_group_provenance(group, as_of),
        freshness=freshness,
        freshness_detail=freshness_detail,
        coverage=covered / max(len(members), 1),
        exclusions=exclusions,
        rows=rows,
    )


@router.get("/groups/{group_key}/breadth", response_model=BreadthOut)
async def group_breadth(
    group_key: str,
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    as_of: datetime | None = Query(default=None),
    new_high_lookback: int = Query(default=20, ge=2, le=252),
    near_threshold: float = Query(default=0.05, gt=0, le=0.5),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    group = (
        await db.execute(
            select(MarketGroup)
            .options(selectinload(MarketGroup.members))
            .where(MarketGroup.stable_key == group_key)
        )
    ).scalar_one_or_none()
    if group is None:
        raise HTTPException(404, detail={"code": "market_group_not_found", "group_key": group_key})
    requested_as_of = as_of
    members = _group_members_at(group, requested_as_of)
    bars_by_id = _truncate_bars_at(
        await _bars_by_instrument(
            db, [member.instrument_id for member in members], timeframe, adjusted
        ),
        requested_as_of,
    )
    counts = {20: 0, 50: 0, 200: 0}
    eligible = {20: 0, 50: 0, 200: 0}
    near_counts = {"high": 0, "low": 0}
    near_eligible = 0
    new_counts = {"high": 0, "low": 0}
    new_eligible = 0
    trend_counts = {"uptrend": 0, "downtrend": 0}
    trend_eligible = 0
    distance_totals = {20: 0.0, 50: 0.0, 200: 0.0}
    distance_eligible = {20: 0, 50: 0, 200: 0}
    member_metrics: dict[str, dict[str, float | int | None]] = {}
    exclusions: list[AnalysisWarning] = []
    latest_as_of = None
    for member in members:
        bars = bars_by_id.get(member.instrument_id, [])
        metrics: dict[str, float | int | None] = {}
        if bars:
            latest_as_of = max(latest_as_of, bars[-1].ts) if latest_as_of else bars[-1].ts
        for period in counts:
            if len(bars) < period:
                metrics[f"above_ma{period}"] = None
                continue
            eligible[period] += 1
            close = float(bars[-1].close)
            moving_average = sum(float(bar.close) for bar in bars[-period:]) / period
            distance_totals[period] += close / moving_average - 1 if moving_average else 0.0
            distance_eligible[period] += 1
            metrics[f"above_ma{period}"] = int(close > moving_average)
            metrics[f"distance_ma{period}"] = close / moving_average - 1 if moving_average else None
            if metrics[f"above_ma{period}"]:
                counts[period] += 1
        if len(bars) >= 252:
            close = float(bars[-1].close)
            window = [float(bar.close) for bar in bars[-252:]]
            high, low = max(window), min(window)
            if high:
                near_eligible += 1
                near_high = close >= high * (1 - near_threshold)
                near_low = bool(low and close <= low * (1 + near_threshold))
                metrics["near_52w_high"] = int(near_high)
                metrics["near_52w_low"] = int(near_low)
                if near_high:
                    near_counts["high"] += 1
                if near_low:
                    near_counts["low"] += 1
        else:
            metrics["near_52w_high"] = None
            metrics["near_52w_low"] = None
        if len(bars) > new_high_lookback:
            close = float(bars[-1].close)
            previous = [float(bar.close) for bar in bars[-(new_high_lookback + 1) : -1]]
            if previous:
                new_eligible += 1
                new_high = close >= max(previous)
                new_low = close <= min(previous)
                metrics["new_high"] = int(new_high)
                metrics["new_low"] = int(new_low)
                if new_high:
                    new_counts["high"] += 1
                if new_low:
                    new_counts["low"] += 1
        else:
            metrics["new_high"] = None
            metrics["new_low"] = None
        if len(bars) >= 50:
            closes = [float(bar.close) for bar in bars]
            sma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
            sma50 = sum(closes[-50:]) / 50
            if sma20 is not None:
                trend_eligible += 1
                uptrend = closes[-1] > sma50 and sma20 > sma50
                downtrend = closes[-1] < sma50 and sma20 < sma50
                metrics["uptrend"] = int(uptrend)
                metrics["downtrend"] = int(downtrend)
                if uptrend:
                    trend_counts["uptrend"] += 1
                if downtrend:
                    trend_counts["downtrend"] += 1
        else:
            metrics["uptrend"] = None
            metrics["downtrend"] = None
        member_metrics[str(member.instrument_id)] = metrics
        if not bars:
            exclusions.append(
                AnalysisWarning(
                    code="no_bars",
                    message="No local bars are available.",
                    instrument_id=member.instrument_id,
                )
            )
    freshness, freshness_detail = await _batch_freshness(
        db, [member.instrument_id for member in members], timeframe, adjusted
    )
    return BreadthOut(
        group_key=group_key,
        timeframe=timeframe.value,
        adjustment="split_adjusted" if adjusted else "raw",
        as_of=latest_as_of,
        membership_version=_group_membership_version(group, members),
        universe_provenance=_group_provenance(group, requested_as_of),
        freshness=freshness,
        freshness_detail=freshness_detail,
        evaluated_count=len(members),
        coverage=sum(1 for bars in bars_by_id.values() if bars) / max(len(members), 1),
        coverage_detail={
            **{f"ma{period}": eligible[period] / max(len(members), 1) for period in eligible},
            "near_52w": near_eligible / max(len(members), 1),
            "new_high_low": new_eligible / max(len(members), 1),
            "trend": trend_eligible / max(len(members), 1),
            **{
                f"distance_ma{period}": distance_eligible[period] / max(len(members), 1)
                for period in distance_eligible
            },
        },
        member_metrics=member_metrics,
        above_ma={
            f"ma{period}": counts[period] / eligible[period] if eligible[period] else None
            for period in counts
        },
        near_52w={
            "high": near_counts["high"] / near_eligible if near_eligible else None,
            "low": near_counts["low"] / near_eligible if near_eligible else None,
        },
        new_highs={"lookback": new_counts["high"] / new_eligible if new_eligible else None},
        new_lows={"lookback": new_counts["low"] / new_eligible if new_eligible else None},
        trend={
            "uptrend": trend_counts["uptrend"] / trend_eligible if trend_eligible else None,
            "downtrend": trend_counts["downtrend"] / trend_eligible if trend_eligible else None,
        },
        distance_from_ma={
            f"ma{period}": distance_totals[period] / distance_eligible[period]
            if distance_eligible[period]
            else None
            for period in distance_totals
        },
        new_high_lookback=new_high_lookback,
        near_threshold=near_threshold,
        exclusions=exclusions,
    )


@router.get("/groups/{group_key}/breadth/history", response_model=BreadthHistoryOut)
async def group_breadth_history(
    group_key: str,
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
    limit: int = Query(default=500, ge=1, le=5_000),
    as_of: datetime | None = Query(default=None),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return date-aligned local breadth without filling missing constituent bars."""
    group = (
        await db.execute(
            select(MarketGroup)
            .options(selectinload(MarketGroup.members))
            .where(MarketGroup.stable_key == group_key)
        )
    ).scalar_one_or_none()
    if group is None:
        raise HTTPException(404, detail={"code": "market_group_not_found", "group_key": group_key})
    members = _group_members_at(group, as_of)
    periods = (20, 50, 200)
    buckets: dict = {}
    exclusions: list[AnalysisWarning] = []
    bars_by_id = _truncate_bars_at(
        await _bars_by_instrument(
            db, [member.instrument_id for member in members], timeframe, adjusted
        ),
        as_of,
    )
    for member in members:
        bars = bars_by_id.get(member.instrument_id, [])
        if not bars:
            exclusions.append(
                AnalysisWarning(
                    code="no_bars",
                    message="No local bars are available.",
                    instrument_id=member.instrument_id,
                )
            )
            continue
        closes = [float(bar.close) for bar in bars]
        for period in periods:
            rolling_total = sum(closes[:period])
            for index in range(period - 1, len(bars)):
                if index >= period:
                    rolling_total += closes[index] - closes[index - period]
                point = buckets.setdefault(bars[index].ts, {item: [0, 0] for item in periods})
                point[period][1] += 1
                if closes[index] > rolling_total / period:
                    point[period][0] += 1
    points = [
        BreadthHistoryPoint(
            timestamp=timestamp,
            above_ma={
                f"ma{period}": values[period][0] / values[period][1] if values[period][1] else None
                for period in periods
            },
            coverage={
                f"ma{period}": values[period][1] / max(len(members), 1) for period in periods
            },
        )
        for timestamp, values in sorted(buckets.items())
    ][-limit:]
    freshness, freshness_detail = await _batch_freshness(
        db, [member.instrument_id for member in members], timeframe, adjusted
    )
    return BreadthHistoryOut(
        group_key=group.stable_key,
        timeframe=timeframe.value,
        adjustment="split_adjusted" if adjusted else "raw",
        membership_version=_group_membership_version(group, members),
        universe_provenance=_group_provenance(group, as_of),
        freshness=freshness,
        freshness_detail=freshness_detail,
        points=points,
        exclusions=exclusions,
    )


_GENERIC_BREADTH_EXCLUSION_MESSAGES = {
    "no_bars": "No local bars are available for this member.",
    "invalid_close": "The member has a non-finite close observation.",
    "invalid_average": "The requested average could not be calculated.",
    "invalid_reference": "The requested reference value is invalid or zero.",
    "insufficient_history": "The member does not have enough history for this condition.",
    "missing_volume": "Volume observations are incomplete for this condition.",
    "zero_average_volume": "The volume baseline is zero.",
    "benchmark_required": "This condition requires a benchmark.",
    "unsupported_condition": "The requested condition is not supported by this runtime.",
    "cross_sectional_unsupported_condition": "The selected cross-sectional target is not supported for this condition kind.",
    "cross_sectional_requires_universe": "A cross-sectional condition must be evaluated with its complete universe.",
    "invalid_condition_params": "The condition parameters are invalid.",
    "unsupported_field": "The requested comparison field is not supported by this runtime.",
    "condition_clause_excluded": "A nested breadth condition could not be evaluated for this member.",
    "missing_bar_at_timestamp": "The member has no bar at this timestamp and was excluded without forward-fill.",
    "benchmark_missing_at_timestamp": "The benchmark has no bar at this timestamp.",
    "unaligned_reference": "The member and benchmark/peer have no bar at the same timestamp.",
    "event_data_unavailable": "No local event calendar has been loaded for this member.",
    "unresolved_member": "The universe member has no resolved canonical instrument.",
    "non_equity_holding": "Non-equity ETF exposure is excluded from breadth.",
    "instrument_not_found": "No canonical instrument exists for this requested symbol.",
}


def _generic_breadth_warning(code: str, instrument_id: int | None = None) -> AnalysisWarning:
    base_code = code.split(":", 1)[0]
    return AnalysisWarning(
        code=code,
        message=_GENERIC_BREADTH_EXCLUSION_MESSAGES.get(
            base_code, "The member was excluded by a nested breadth condition."
        ),
        instrument_id=instrument_id,
    )


def _generic_condition_requires_benchmark(condition: Mapping[str, object]) -> bool:
    """Detect benchmark-dependent leaves in a nested breadth definition."""

    kind = str(condition.get("kind", "")).lower()
    params = condition.get("params")
    if not isinstance(params, Mapping):
        return False
    if kind == "relative_strength":
        return True
    if kind == "percentile" and str(params.get("field", "")).lower() in {
        "relative_strength",
        "relative_return",
    }:
        return True
    if kind == "comparison" and str(params.get("field", "")).lower() in {
        "relative_strength",
        "relative_return",
    }:
        return True
    if kind == "series_comparison":
        return True
    children = params.get("conditions")
    return isinstance(children, list) and any(
        isinstance(child, Mapping) and _generic_condition_requires_benchmark(child)
        for child in children
    )


def _generic_condition_requires_events(condition: Mapping[str, object]) -> bool:
    """Detect event-calendar leaves in a nested breadth definition."""

    if str(condition.get("kind", "")).lower() == "event":
        return True
    params = condition.get("params")
    if not isinstance(params, Mapping):
        return False
    children = params.get("conditions")
    return isinstance(children, list) and any(
        isinstance(child, Mapping) and _generic_condition_requires_events(child)
        for child in children
    )


async def _breadth_events_by_instrument(
    db: AsyncSession, instrument_ids: list[int]
) -> tuple[dict[int, list[InstrumentEvent] | None], dict[str, object]]:
    """Read locally persisted event calendars without provider fan-out."""

    if not instrument_ids:
        return {}, {
            "kind": "instrument_event_calendar",
            "membership_semantics": "canonical_local_instruments",
            "loaded_member_count": 0,
            "unavailable_member_count": 0,
        }
    rows = (
        (
            await db.execute(
                select(InstrumentEvent)
                .where(InstrumentEvent.instrument_id.in_(instrument_ids))
                .order_by(InstrumentEvent.instrument_id, InstrumentEvent.event_time)
            )
        )
        .scalars()
        .all()
    )
    states = (
        (
            await db.execute(
                select(InstrumentEventFetchState.instrument_id).where(
                    InstrumentEventFetchState.instrument_id.in_(instrument_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    loaded_ids = {int(instrument_id) for instrument_id in states}
    by_id: dict[int, list[InstrumentEvent] | None] = {
        instrument_id: [] if instrument_id in loaded_ids else None
        for instrument_id in instrument_ids
    }
    for event in rows:
        by_id.setdefault(event.instrument_id, []).append(event)
    return by_id, {
        "kind": "instrument_event_calendar",
        "membership_semantics": "canonical_local_instruments",
        "loaded_member_count": sum(events is not None for events in by_id.values()),
        "unavailable_member_count": sum(events is None for events in by_id.values()),
        "event_count": len(rows),
        "alignment": "event_time_at_or_before_observation",
    }


def _generic_membership_version(payload: object) -> int:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return int(hashlib.sha256(encoded.encode()).hexdigest()[:15], 16)


def _series_reference_fields(condition: Mapping[str, object]) -> set[str]:
    """Return fields that must be materialized on a derived reference series."""

    fields: set[str] = set()
    if str(condition.get("kind", "")).lower() == "series_comparison":
        params = condition.get("params")
        if isinstance(params, Mapping):
            target = params.get("target_field", params.get("field", "close"))
            if isinstance(target, str):
                fields.add(target.lower().strip())
    params = condition.get("params")
    if isinstance(params, Mapping):
        children = params.get("conditions")
        if isinstance(children, list):
            for child in children:
                if isinstance(child, Mapping):
                    fields.update(_series_reference_fields(child))
    return fields


async def _resolve_generic_breadth_reference(
    definition: BreadthDefinitionRequest,
    condition: Mapping[str, object],
    timeframe: Timeframe,
    db: AsyncSession,
    user_id: int | None = None,
) -> tuple[list[object] | None, list[int], list[AnalysisWarning], dict[str, object]]:
    """Resolve a group/peer aggregate target without provider fan-out.

    A symbol benchmark remains the direct reference path. A ``reference_universe``
    instead resolves the same canonical local universe machinery as the member
    universe and materializes a labelled equal-weight return index. This keeps
    group comparisons point-in-time and makes missing/asynchronous bars visible.
    """

    if definition.reference_universe is None:
        return None, [], [], {}
    unsupported = _series_reference_fields(condition) - {
        "close",
        "price",
        "last",
        "return",
        "return_1",
    }
    if unsupported:
        raise HTTPException(
            422,
            detail={
                "code": "reference_aggregate_unsupported_field",
                "fields": sorted(unsupported),
                "supported_fields": ["close", "return"],
            },
        )
    reference_definition = definition.model_copy(update={"universe": definition.reference_universe})
    (
        reference_members,
        reference_ids,
        reference_warnings,
        reference_universe_provenance,
        reference_membership_payload,
    ) = await _resolve_generic_breadth_universe(reference_definition, db, user_id)
    reference_bars_by_id = _truncate_bars_at(
        await _bars_by_instrument(db, reference_ids, timeframe, definition.adjusted),
        definition.as_of,
    )
    reference_series, series_summary = build_equal_reference_series(reference_bars_by_id)
    reference_membership_version = _generic_membership_version(reference_membership_payload)
    provenance: dict[str, object] = {
        "kind": "derived_reference_series",
        "target": "equal_weight_member_return_index",
        "universe": reference_universe_provenance,
        "membership_version": reference_membership_version,
        "member_count": len(reference_members),
        **series_summary,
    }
    return reference_series, reference_ids, reference_warnings, provenance


async def _resolve_benchmark_family_breadth_universe(
    definition: BreadthDefinitionRequest, db: AsyncSession
) -> tuple[list[BreadthMember], list[int], list[AnalysisWarning], dict[str, object], object]:
    """Resolve a family/style leg through its point-in-time ETF-proxy snapshot."""

    family_key = definition.universe.key
    if not family_key:
        raise HTTPException(
            422, detail={"code": "universe_key_required", "kind": "benchmark_family"}
        )
    family = (
        await db.execute(select(MarketGroup).where(MarketGroup.stable_key == family_key))
    ).scalar_one_or_none()
    if family is None or family.group_type != "benchmark_family":
        raise HTTPException(
            404, detail={"code": "benchmark_family_not_found", "family_key": family_key}
        )
    provenance = dict(family.provenance or {})
    mappings = provenance.get("proxy_mappings")
    mapping = mappings.get(definition.universe.role) if isinstance(mappings, Mapping) else None
    if not isinstance(mapping, Mapping) or not mapping.get("symbol"):
        derived_policy = provenance.get("derived_equal_weight")
        if (
            definition.universe.role == "equal_weight"
            and isinstance(derived_policy, Mapping)
            and bool(derived_policy.get("allowed"))
        ):
            # Reuse the same locked source resolver as Market Map/watchlists so
            # derived equal-weight membership has one point-in-time lineage.
            source_id = f"benchmark-family:{family_key}:equal_weight"
            resolved = await resolve_watchlist_source(
                db,
                0,
                source_id,
                as_of=definition.as_of if definition.universe.point_in_time else None,
            )
            if not resolved.members:
                if any(
                    str(item.get("reason", "")).startswith("holdings_snapshot")
                    for item in resolved.exclusions
                    if isinstance(item, Mapping)
                ):
                    raise HTTPException(
                        404,
                        detail={
                            "code": "holdings_snapshot_not_found",
                            "family_key": family_key,
                            "role": definition.universe.role,
                            "symbol": resolved.descriptor.symbol,
                        },
                    )
                raise HTTPException(
                    404,
                    detail={
                        "code": "benchmark_mapping_unavailable",
                        "family_key": family_key,
                        "role": definition.universe.role,
                    },
                )
            instrument_rows = (
                (
                    await db.execute(
                        select(Instrument).where(
                            Instrument.id.in_([member.instrument_id for member in resolved.members])
                        )
                    )
                )
                .scalars()
                .all()
            )
            by_id = {instrument.id: instrument for instrument in instrument_rows}
            members = [
                BreadthMember(instrument.id, instrument.symbol, instrument.name)
                for member in resolved.members
                if (instrument := by_id.get(member.instrument_id)) is not None
            ]
            member_ids = [
                member.instrument_id for member in resolved.members if member.instrument_id in by_id
            ]
            warnings = [
                _generic_breadth_warning(str(item.get("reason", "membership_excluded")))
                for item in resolved.exclusions
                if isinstance(item, Mapping)
            ]
            descriptor = resolved.descriptor.model_dump(mode="json")
            membership_payload = {
                "source_id": source_id,
                "membership_version": resolved.descriptor.membership_version,
                "item_ids": sorted(member_ids),
                "excluded": list(resolved.exclusions),
            }
            return (
                members,
                member_ids,
                warnings,
                {
                    "kind": "benchmark_family",
                    "family_key": family_key,
                    "family_name": family.name,
                    "role": definition.universe.role,
                    "proxy_symbol": resolved.descriptor.symbol,
                    "membership_semantics": "derived_equal_weight_point_in_time_membership",
                    "derived_method": derived_policy.get("method"),
                    "descriptor": descriptor,
                },
                membership_payload,
            )
        raise HTTPException(
            404,
            detail={
                "code": "benchmark_mapping_unavailable",
                "family_key": family_key,
                "role": definition.universe.role,
            },
        )
    proxy_symbol = str(mapping["symbol"]).upper()
    proxy = await _instrument(db, proxy_symbol)
    profile = (
        await db.execute(select(ETFProfile).where(ETFProfile.instrument_id == proxy.id))
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            404,
            detail={
                "code": "etf_profile_not_found",
                "family_key": family_key,
                "symbol": proxy_symbol,
            },
        )
    statement = holdings_snapshot_source_filter(
        select(ETFHoldingsSnapshot).where(ETFHoldingsSnapshot.etf_profile_id == profile.id)
    )
    if definition.universe.point_in_time:
        statement = _holdings_snapshot_at(statement, definition.as_of)
    snapshot = (
        await db.execute(
            statement.options(
                selectinload(ETFHoldingsSnapshot.rows).selectinload(
                    ETFHolding.constituent_instrument
                )
            )
            .order_by(
                ETFHoldingsSnapshot.composition_date.desc(),
                ETFHoldingsSnapshot.known_at.desc().nullslast(),
                ETFHoldingsSnapshot.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(
            404,
            detail={
                "code": "holdings_snapshot_not_found",
                "family_key": family_key,
                "role": definition.universe.role,
                "symbol": proxy_symbol,
            },
        )
    members: list[BreadthMember] = []
    member_ids: list[int] = []
    warnings: list[AnalysisWarning] = []
    for holding in snapshot.rows:
        if not holding.constituent_instrument_id or holding.constituent_instrument is None:
            warnings.append(_generic_breadth_warning("unresolved_member", None))
            continue
        if holding.holding_type != "equity" or holding.row_type != "security":
            warnings.append(
                AnalysisWarning(
                    code="non_equity_holding",
                    message="Non-equity ETF exposure is excluded from benchmark-family breadth.",
                )
            )
            continue
        instrument = holding.constituent_instrument
        if instrument.id in member_ids:
            continue
        members.append(BreadthMember(instrument.id, instrument.symbol, instrument.name))
        member_ids.append(instrument.id)
    membership_payload = {
        "family_key": family_key,
        "role": definition.universe.role,
        "proxy_symbol": proxy_symbol,
        "snapshot_id": snapshot.id,
        "snapshot_hash": snapshot.snapshot_hash,
        "instrument_ids": sorted(member_ids),
    }
    universe_provenance = {
        "kind": "benchmark_family",
        "family_key": family_key,
        "family_name": family.name,
        "role": definition.universe.role,
        "proxy_symbol": proxy_symbol,
        "membership_semantics": "etf_proxy_membership",
        "composition_date": snapshot.composition_date.isoformat(),
        "known_at": snapshot.known_at.isoformat() if snapshot.known_at else None,
        "source_provider": snapshot.source_provider,
        "provenance": snapshot.provenance,
        "completeness_status": snapshot.completeness_status,
        "snapshot_hash": snapshot.snapshot_hash,
        "mapping_verification_state": mapping.get("verification_state"),
    }
    return members, member_ids, warnings, universe_provenance, membership_payload


async def _resolve_user_watchlist_breadth_universe(
    definition: BreadthDefinitionRequest,
    db: AsyncSession,
    user_id: int | None,
) -> tuple[list[BreadthMember], list[int], list[AnalysisWarning], dict[str, object], object]:
    """Resolve any selectable watchlist source without provider fan-out.

    Numeric keys remain a compatibility shorthand for personal watchlists. The
    canonical form is a source descriptor ID, allowing locked index/ETF
    universes to use the same breadth contract as editable personal lists.
    """

    if user_id is None:
        raise HTTPException(422, detail={"code": "watchlist_user_context_required"})
    key = definition.universe.key
    if not key:
        raise HTTPException(422, detail={"code": "watchlist_source_required"})
    source_id = f"watchlist:{key}" if key.isdigit() else key
    if not source_id.startswith(
        (
            "watchlist:",
            "market-group:",
            "benchmark-family:",
            "etf-holdings:",
            "combo:",
            "explicit:",
            "explicit-list:",
        )
    ):
        raise HTTPException(422, detail={"code": "unsupported_watchlist_source", "source_id": key})
    try:
        resolved = await resolve_watchlist_source(
            db,
            user_id,
            source_id,
            as_of=definition.as_of if definition.universe.point_in_time else None,
        )
    except LookupError as exc:
        raise HTTPException(404, detail={"code": str(exc), "source_id": source_id}) from exc
    except ValueError as exc:
        raise HTTPException(422, detail={"code": str(exc), "source_id": source_id}) from exc

    instrument_ids = list(dict.fromkeys(member.instrument_id for member in resolved.members))
    instruments = (
        (
            (await db.execute(select(Instrument).where(Instrument.id.in_(instrument_ids))))
            .scalars()
            .all()
        )
        if instrument_ids
        else []
    )
    by_id = {instrument.id: instrument for instrument in instruments}
    members: list[BreadthMember] = []
    member_ids: list[int] = []
    warnings: list[AnalysisWarning] = []
    for member in resolved.members:
        instrument = by_id.get(member.instrument_id)
        if instrument is None:
            warnings.append(_generic_breadth_warning("unresolved_member", member.instrument_id))
            continue
        members.append(BreadthMember(instrument.id, instrument.symbol, instrument.name))
        member_ids.append(instrument.id)
    for exclusion in resolved.exclusions:
        if isinstance(exclusion, Mapping):
            warnings.append(
                _generic_breadth_warning(str(exclusion.get("reason", "membership_excluded")))
            )
    descriptor = resolved.descriptor.model_dump(mode="json")
    membership_payload = {
        "source_id": source_id,
        "membership_version": resolved.descriptor.membership_version,
        "item_ids": sorted(member_ids),
        "excluded": list(resolved.exclusions),
    }
    provenance = {
        "kind": "watchlist",
        "source_id": source_id,
        "source_kind": resolved.descriptor.source_kind,
        "name": resolved.descriptor.name,
        "membership_semantics": "locked_source_members"
        if resolved.descriptor.locked
        else "user_watchlist_members",
        "locked": resolved.descriptor.locked,
        "member_count": len(member_ids),
        "descriptor": descriptor,
    }
    if resolved.descriptor.watchlist_id is not None:
        provenance["watchlist_id"] = resolved.descriptor.watchlist_id
        provenance["watchlist_name"] = resolved.descriptor.name
        provenance["is_managed"] = resolved.descriptor.source_kind == "screener_managed"
        provenance["is_locked"] = resolved.descriptor.locked
    return members, member_ids, warnings, provenance, membership_payload


async def _resolve_generic_breadth_universe(
    definition: BreadthDefinitionRequest, db: AsyncSession, user_id: int | None = None
) -> tuple[list[BreadthMember], list[int], list[AnalysisWarning], dict[str, object], object]:
    """Resolve one breadth universe without provider fan-out."""

    universe_kind = definition.universe.kind
    members: list[BreadthMember] = []
    member_ids: list[int] = []
    universe_warnings: list[AnalysisWarning] = []
    universe_provenance: dict[str, object]
    membership_version_payload: object

    if universe_kind == "benchmark_family":
        return await _resolve_benchmark_family_breadth_universe(definition, db)
    if universe_kind == "watchlist":
        return await _resolve_user_watchlist_breadth_universe(definition, db, user_id)
    if universe_kind == "group":
        if not definition.universe.key:
            raise HTTPException(
                422, detail={"code": "universe_key_required", "kind": universe_kind}
            )
        group = (
            await db.execute(
                select(MarketGroup)
                .options(
                    selectinload(MarketGroup.members).selectinload(MarketGroupMember.instrument)
                )
                .where(MarketGroup.stable_key == definition.universe.key)
            )
        ).scalar_one_or_none()
        if group is None:
            raise HTTPException(
                404,
                detail={"code": "market_group_not_found", "group_key": definition.universe.key},
            )
        selected_members = (
            _group_members_at(group, definition.as_of)
            if definition.universe.point_in_time
            else list(group.members)
        )
        for member in selected_members:
            if member.instrument is None:
                universe_warnings.append(
                    _generic_breadth_warning("unresolved_member", member.instrument_id)
                )
                continue
            members.append(
                BreadthMember(
                    member.instrument_id, member.instrument.symbol, member.instrument.name
                )
            )
            member_ids.append(member.instrument_id)
        membership_version_payload = _group_membership_version(group, selected_members)
        universe_provenance = {
            **_group_provenance(
                group, definition.as_of if definition.universe.point_in_time else None
            ),
            "kind": "market_group",
            "stable_key": group.stable_key,
            "membership_semantics": "curated_group_members",
        }
    elif universe_kind == "etf_holdings":
        if not definition.universe.key:
            raise HTTPException(
                422, detail={"code": "universe_key_required", "kind": universe_kind}
            )
        etf = await _instrument(db, definition.universe.key)
        profile = (
            await db.execute(select(ETFProfile).where(ETFProfile.instrument_id == etf.id))
        ).scalar_one_or_none()
        if profile is None:
            raise HTTPException(404, detail={"code": "etf_profile_not_found", "symbol": etf.symbol})
        statement = holdings_snapshot_source_filter(
            select(ETFHoldingsSnapshot).where(ETFHoldingsSnapshot.etf_profile_id == profile.id)
        )
        if definition.universe.point_in_time:
            statement = _holdings_snapshot_at(statement, definition.as_of)
        snapshot = (
            await db.execute(
                statement.options(
                    selectinload(ETFHoldingsSnapshot.rows).selectinload(
                        ETFHolding.constituent_instrument
                    )
                )
                .order_by(
                    ETFHoldingsSnapshot.composition_date.desc(),
                    ETFHoldingsSnapshot.known_at.desc().nullslast(),
                    ETFHoldingsSnapshot.id.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if snapshot is None:
            raise HTTPException(
                404, detail={"code": "holdings_snapshot_not_found", "symbol": etf.symbol}
            )
        for holding in snapshot.rows:
            if not holding.constituent_instrument_id or holding.constituent_instrument is None:
                universe_warnings.append(_generic_breadth_warning("unresolved_member", None))
                continue
            if holding.holding_type != "equity" or holding.row_type != "security":
                universe_warnings.append(
                    AnalysisWarning(
                        code="non_equity_holding",
                        message="Non-equity ETF exposure is excluded from breadth.",
                    )
                )
                continue
            instrument = holding.constituent_instrument
            members.append(BreadthMember(instrument.id, instrument.symbol, instrument.name))
            member_ids.append(instrument.id)
        membership_version_payload = {
            "snapshot_id": snapshot.id,
            "snapshot_hash": snapshot.snapshot_hash,
            "instrument_ids": sorted(member_ids),
        }
        universe_provenance = {
            "kind": "etf_holdings_proxy",
            "etf_symbol": etf.symbol,
            "membership_semantics": "etf_proxy_membership",
            "composition_date": snapshot.composition_date.isoformat(),
            "known_at": snapshot.known_at.isoformat() if snapshot.known_at else None,
            "source_provider": snapshot.source_provider,
            "provenance": snapshot.provenance,
            "completeness_status": snapshot.completeness_status,
            "snapshot_hash": snapshot.snapshot_hash,
        }
    else:
        requested_symbols = list(
            dict.fromkeys(
                symbol.strip().upper() for symbol in definition.universe.symbols if symbol.strip()
            )
        )
        if not requested_symbols:
            raise HTTPException(422, detail={"code": "symbols_required", "kind": universe_kind})
        instruments = (
            (await db.execute(select(Instrument).where(Instrument.symbol.in_(requested_symbols))))
            .scalars()
            .all()
        )
        by_symbol = {instrument.symbol.upper(): instrument for instrument in instruments}
        for symbol in requested_symbols:
            instrument = by_symbol.get(symbol)
            if instrument is None:
                universe_warnings.append(
                    AnalysisWarning(
                        code="instrument_not_found",
                        message=f"No canonical instrument exists for {symbol}.",
                    )
                )
                continue
            members.append(BreadthMember(instrument.id, instrument.symbol, instrument.name))
            member_ids.append(instrument.id)
        membership_version_payload = {
            "symbols": requested_symbols,
            "instrument_ids": sorted(member_ids),
        }
        universe_provenance = {
            "kind": "explicit_symbols",
            "membership_semantics": "canonical_local_instruments",
            "requested_symbols": requested_symbols,
        }
    return members, member_ids, universe_warnings, universe_provenance, membership_version_payload


async def _resolve_generic_breadth_condition(
    definition: BreadthDefinitionRequest,
    db: AsyncSession,
    current_user: User,
) -> tuple[BreadthConditionRequest, dict[str, object]]:
    """Resolve an inline or user-owned immutable condition asset.

    The saved asset contains the visual AST and the Boolean CodeVersion generated by the
    unified-condition compiler.  Breadth evaluation still uses the canonical evaluator here;
    the metadata makes the exact reusable asset/version part of the response and cache identity.
    Arbitrary Python source is never executed in this request path.
    """

    if definition.condition_asset_key:
        if definition.condition is not None:
            raise HTTPException(
                422,
                detail={
                    "code": "condition_asset_inline_conflict",
                    "message": "Provide either condition_asset_key or an inline condition.",
                },
            )
        item = (
            await db.execute(
                select(WorkspaceLibraryItem).where(
                    WorkspaceLibraryItem.user_id == current_user.id,
                    WorkspaceLibraryItem.kind == "condition",
                    WorkspaceLibraryItem.stable_key == definition.condition_asset_key,
                )
            )
        ).scalar_one_or_none()
        if item is None:
            raise HTTPException(
                404,
                detail={
                    "code": "condition_asset_not_found",
                    "stable_key": definition.condition_asset_key,
                },
            )
        payload = item.payload if isinstance(item.payload, dict) else {}
        raw_condition = payload.get("condition")
        if not isinstance(raw_condition, dict):
            raise HTTPException(
                422,
                detail={
                    "code": "condition_asset_invalid",
                    "stable_key": definition.condition_asset_key,
                },
            )
        try:
            condition = BreadthConditionRequest.model_validate(
                _saved_condition_to_breadth(raw_condition)
            )
        except Exception as exc:
            raise HTTPException(
                422,
                detail={
                    "code": "condition_asset_invalid",
                    "stable_key": definition.condition_asset_key,
                },
            ) from exc
        python_version_id = payload.get("python_code_version_id")
        return condition, {
            "asset_key": item.stable_key,
            "library_version": item.version,
            "python_code_version_id": python_version_id
            if isinstance(python_version_id, int)
            else None,
        }
    if definition.condition is None:
        raise HTTPException(
            422,
            detail={
                "code": "condition_required",
                "message": "A condition or condition asset is required.",
            },
        )
    return definition.condition, {}


def _saved_condition_to_breadth(node: Mapping[str, object]) -> dict[str, object]:
    """Map the supported visual-condition subset into the breadth contract."""

    if "kind" in node:
        return dict(node)
    if "operator" in node and "conditions" in node:
        operator = str(node.get("operator") or "AND").lower()
        kind = {"and": "all", "or": "any", "not": "not"}.get(operator)
        children = node.get("conditions")
        if kind is None or not isinstance(children, list):
            raise ValueError("unsupported saved condition group")
        return {
            "kind": kind,
            "params": {
                "conditions": [
                    _saved_condition_to_breadth(child)
                    for child in children
                    if isinstance(child, Mapping)
                ]
            },
        }
    if str(node.get("type") or "") == "price_indicator":
        indicator = str(node.get("indicator") or "").lower()
        field = str(node.get("field") or "close").lower()
        if indicator in {"sma", "ema"} and field == "close":
            operator = str(node.get("op") or "gt").lower()
            if operator in {"gt", "lt"}:
                params = node.get("params")
                period = params.get("period", 200) if isinstance(params, Mapping) else 200
                return {
                    "kind": "above_moving_average",
                    "params": {
                        "period": period,
                        "average": indicator,
                        "comparator": "above" if operator == "gt" else "below",
                    },
                }
    raise ValueError("saved condition is outside the supported breadth subset")


def _python_breadth_condition_metadata(
    version: CodeVersion,
    parameters: Mapping[str, object],
    *,
    output_contract: str = "boolean",
    series_target: Mapping[str, object] | None = None,
) -> dict[str, object]:
    asset = version.asset
    return {
        "kind": "python",
        "code_version_id": version.id,
        "asset_key": asset.stable_key if asset is not None else None,
        "asset_version": version.version_number,
        "output_contract": output_contract,
        "sdk_version": version.sdk_version,
        "runtime_version": version.runtime_version,
        "lookback": version.lookback,
        "parameters": dict(parameters),
        "series_target": dict(series_target) if isinstance(series_target, Mapping) else None,
    }


def _python_condition_tree_requires_benchmark(node: object) -> bool:
    """Return whether a Python comparison leaf reads the prepared benchmark dataset."""
    if not isinstance(node, Mapping):
        return False
    kind = str(node.get("kind") or "").lower()
    params = node.get("params") if isinstance(node.get("params"), Mapping) else {}
    if (
        kind == "python_series_comparison"
        and str(params.get("right_scope", "member")).lower() == "benchmark"
    ):
        return True
    children = params.get("conditions")
    return isinstance(children, list) and any(
        _python_condition_tree_requires_benchmark(child) for child in children
    )


async def _resolve_python_condition_tree(
    raw: Mapping[str, object], db: AsyncSession, user_id: int
) -> tuple[dict[str, object], list[int]]:
    """Resolve owned numeric-series CodeVersions embedded in a member condition tree."""
    resolved_ids: list[int] = []

    async def resolve(node: object) -> dict[str, object]:
        if not isinstance(node, Mapping):
            raise HTTPException(422, detail={"code": "invalid_python_condition_tree"})
        kind = str(node.get("kind") or "").lower()
        params = node.get("params") if isinstance(node.get("params"), Mapping) else {}
        if kind in {"all", "any", "not"}:
            children = params.get("conditions")
            if (
                not isinstance(children, list)
                or not children
                or any(not isinstance(child, Mapping) for child in children)
            ):
                raise HTTPException(422, detail={"code": "invalid_python_condition_tree"})
            if kind == "not" and len(children) != 1:
                raise HTTPException(422, detail={"code": "invalid_python_condition_tree"})
            return {
                "kind": kind,
                "params": {"conditions": [await resolve(child) for child in children]},
            }
        if kind == "python_series":
            code_version_id = params.get("code_version_id")
            if (
                not isinstance(code_version_id, int)
                or isinstance(code_version_id, bool)
                or code_version_id < 1
            ):
                raise HTTPException(422, detail={"code": "python_series_code_version_required"})
            version = (
                await db.execute(
                    select(CodeVersion)
                    .join(CodeAsset)
                    .where(
                        CodeVersion.id == code_version_id,
                        CodeAsset.user_id == user_id,
                        CodeAsset.kind == "condition",
                        CodeAsset.is_archived.is_(False),
                    )
                )
            ).scalar_one_or_none()
            if version is None or version.output_contract != "series":
                raise HTTPException(422, detail={"code": "python_series_condition_unavailable"})
            scope = str(params.get("scope", "member")).lower()
            if scope not in {"member", "cross_sectional"}:
                raise HTTPException(
                    422,
                    detail={
                        "code": "invalid_python_series_target_scope",
                    },
                )
            statistic = str(params.get("statistic", "mean")).lower()
            if scope == "cross_sectional" and statistic not in {
                "mean",
                "median",
                "min",
                "max",
                "std",
            }:
                raise HTTPException(422, detail={"code": "invalid_python_series_statistic"})
            operator = str(params.get("operator", "gte")).lower()
            threshold = params.get("threshold", 0)
            if (
                operator not in {"gt", "gte", "lt", "lte", "eq", "ne"}
                or not isinstance(threshold, int | float)
                or isinstance(threshold, bool)
                or not math.isfinite(float(threshold))
            ):
                raise HTTPException(422, detail={"code": "invalid_python_series_target"})
            resolved_ids.append(version.id)
            return {
                "kind": "python_series",
                "params": {
                    "code_version_id": version.id,
                    "source": version.source,
                    "output_name": version.output_name,
                    "operator": operator,
                    "threshold": float(threshold),
                    "scope": scope,
                    **({"statistic": statistic} if scope == "cross_sectional" else {}),
                    "parameters": params.get("parameters", {})
                    if isinstance(params.get("parameters"), Mapping)
                    else {},
                },
            }
        if kind == "python_series_comparison":

            async def resolve_series_version(parameter_name: str) -> CodeVersion:
                code_version_id = params.get(parameter_name)
                if (
                    not isinstance(code_version_id, int)
                    or isinstance(code_version_id, bool)
                    or code_version_id < 1
                ):
                    raise HTTPException(
                        422,
                        detail={
                            "code": "python_series_comparison_code_version_required",
                            "side": parameter_name,
                        },
                    )
                version = (
                    await db.execute(
                        select(CodeVersion)
                        .join(CodeAsset)
                        .where(
                            CodeVersion.id == code_version_id,
                            CodeAsset.user_id == user_id,
                            CodeAsset.kind == "condition",
                            CodeAsset.is_archived.is_(False),
                        )
                    )
                ).scalar_one_or_none()
                if version is None or version.output_contract != "series":
                    raise HTTPException(
                        422,
                        detail={
                            "code": "python_series_comparison_condition_unavailable",
                            "side": parameter_name,
                        },
                    )
                return version

            left_version = await resolve_series_version("left_code_version_id")
            right_version = await resolve_series_version("right_code_version_id")
            relation = str(params.get("relation", "difference")).lower()
            scope = str(params.get("scope", "member")).lower()
            right_scope = str(params.get("right_scope", "member")).lower()
            statistic = str(params.get("statistic", "mean")).lower()
            operator = str(params.get("operator", "gte")).lower()
            threshold = params.get("threshold", 0)
            if relation not in {"difference", "ratio"}:
                raise HTTPException(
                    422, detail={"code": "invalid_python_series_comparison_relation"}
                )
            if scope not in {"member", "cross_sectional"}:
                raise HTTPException(422, detail={"code": "invalid_python_series_comparison_scope"})
            if right_scope not in {"member", "benchmark"}:
                raise HTTPException(
                    422, detail={"code": "invalid_python_series_comparison_right_scope"}
                )
            if scope == "cross_sectional" and statistic not in {
                "mean",
                "median",
                "min",
                "max",
                "std",
            }:
                raise HTTPException(
                    422, detail={"code": "invalid_python_series_comparison_statistic"}
                )
            if (
                operator not in {"gt", "gte", "lt", "lte", "eq", "ne"}
                or not isinstance(threshold, int | float)
                or isinstance(threshold, bool)
                or not math.isfinite(float(threshold))
            ):
                raise HTTPException(422, detail={"code": "invalid_python_series_comparison_target"})
            resolved_ids.extend([left_version.id, right_version.id])
            left_asset = left_version.asset
            right_asset = right_version.asset
            return {
                "kind": "python_series_comparison",
                "params": {
                    "left_code_version_id": left_version.id,
                    "right_code_version_id": right_version.id,
                    "left_source": left_version.source,
                    "right_source": right_version.source,
                    "left_output_name": left_version.output_name,
                    "right_output_name": right_version.output_name,
                    "left_parameters": params.get("left_parameters", {})
                    if isinstance(params.get("left_parameters"), Mapping)
                    else {},
                    "right_parameters": params.get("right_parameters", {})
                    if isinstance(params.get("right_parameters"), Mapping)
                    else {},
                    "relation": relation,
                    "scope": scope,
                    "right_scope": right_scope,
                    "statistic": statistic,
                    "operator": operator,
                    "threshold": float(threshold),
                    "left_asset_key": left_asset.stable_key if left_asset is not None else None,
                    "right_asset_key": right_asset.stable_key if right_asset is not None else None,
                },
            }
        try:
            condition = BreadthConditionRequest.model_validate(dict(node))
        except Exception as exc:
            raise HTTPException(
                422, detail={"code": "unsupported_python_condition_tree_leaf"}
            ) from exc
        if condition.target_scope != "member":
            raise HTTPException(422, detail={"code": "cross_sectional_tree_leaf_unsupported"})
        return condition.model_dump(mode="json")

    return await resolve(raw), resolved_ids


async def _load_python_breadth_run(
    db: AsyncSession, run_id: int, current_user: User
) -> ResearchRun:
    run = (
        await db.execute(
            select(ResearchRun)
            .options(
                selectinload(ResearchRun.artifacts),
                selectinload(ResearchRun.code_version).selectinload(CodeVersion.asset),
            )
            .where(ResearchRun.id == run_id, ResearchRun.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if run is None or not str(run.run_config.get("execution_mode", "")).startswith("breadth_"):
        raise HTTPException(status_code=404, detail="Breadth Python run not found")
    collect_research_result(run)
    run.progress = read_research_progress(run.id)
    return run


def _python_breadth_warning(code: str, instrument_id: object = None) -> AnalysisWarning:
    return AnalysisWarning(
        code=code,
        message="The isolated Python predicate excluded this member from the eligible denominator.",
        instrument_id=instrument_id if isinstance(instrument_id, int) else None,
    )


def _python_breadth_point(
    raw: Mapping[str, object], requested_count: int
) -> BreadthPythonResultPointOut:
    timestamp_value = raw.get("timestamp")
    timestamp: datetime | None = None
    if isinstance(timestamp_value, str):
        try:
            timestamp = datetime.fromisoformat(timestamp_value.replace("Z", "+00:00"))
        except ValueError:
            timestamp = None
    cells = raw.get("cells")
    cells = cells if isinstance(cells, list) else []
    members: list[BreadthMemberResultOut] = []
    exclusions: list[AnalysisWarning] = []
    for cell in cells:
        if not isinstance(cell, dict) or not isinstance(cell.get("instrument_id"), int):
            continue
        value = cell.get("value") if isinstance(cell.get("value"), bool) else None
        error = cell.get("error")
        warning = _python_breadth_warning(str(error), cell.get("instrument_id")) if error else None
        if warning:
            exclusions.append(warning)
        members.append(
            BreadthMemberResultOut(
                instrument_id=cell["instrument_id"],
                symbol=str(cell.get("symbol") or "").upper(),
                name=str(cell.get("name") or cell.get("symbol") or "").strip(),
                value=value,
                metric=(
                    float(cell["metric"])
                    if isinstance(cell.get("metric"), int | float)
                    and not isinstance(cell.get("metric"), bool)
                    else None
                ),
                observation_time=timestamp,
                warning=warning,
            )
        )
    eligible = sum(member.value is not None for member in members)
    passed = sum(member.value is True for member in members)
    requested = max(requested_count, len(members))
    group_value = raw.get("group_value")
    group_value = (
        float(group_value)
        if isinstance(group_value, int | float)
        and not isinstance(group_value, bool)
        and math.isfinite(float(group_value))
        else None
    )
    return BreadthPythonResultPointOut(
        timestamp=timestamp,
        requested_count=requested,
        eligible_count=eligible,
        pass_count=passed,
        excluded_count=max(requested - eligible, 0),
        percentage=passed / eligible if eligible else None,
        coverage=eligible / requested if requested else 0,
        group_value=group_value,
        members=members,
        exclusions=exclusions,
    )


def _manifest_exclusion_warnings(manifest: Mapping[str, object]) -> list[AnalysisWarning]:
    raw = manifest.get("exclusions")
    if not isinstance(raw, list):
        return []
    return [
        AnalysisWarning(
            code=str(item.get("code") or "excluded"),
            message="The declared breadth universe member was unavailable before isolated evaluation.",
        )
        for item in raw
        if isinstance(item, dict)
    ]


def _python_breadth_occurrences(
    points: list[BreadthPythonResultPointOut],
) -> list[BreadthDefinitionHistoryOccurrenceOut]:
    """Project isolated Python history points into the shared occurrence contract."""
    rows = detect_breadth_occurrences([point.model_dump() for point in points])
    return [BreadthDefinitionHistoryOccurrenceOut(**row) for row in rows]


def _python_breadth_run_out(run: ResearchRun) -> BreadthPythonRunOut:
    config = run.run_config if isinstance(run.run_config, dict) else {}
    return BreadthPythonRunOut(
        run_id=run.id,
        code_version_id=run.code_version_id,
        status=run.status,
        execution_mode=config.get("execution_mode", "breadth_current"),
        output_contract=str(config.get("output_contract") or "boolean"),
        series_target=(
            config.get("series_target") if isinstance(config.get("series_target"), dict) else None
        ),
        condition_tree=(
            config.get("condition_tree") if isinstance(config.get("condition_tree"), dict) else None
        ),
        definition_hash=str(config.get("definition_hash") or ""),
        universe=config.get("universe", {}),
        condition=config.get("condition", {}),
        dataset_manifest=run.dataset_manifest if isinstance(run.dataset_manifest, dict) else {},
        progress=run.progress if isinstance(getattr(run, "progress", {}), dict) else {},
        diagnostics=run.diagnostics if isinstance(run.diagnostics, list) else [],
    )


def _python_breadth_manifest_fingerprint(manifest: Mapping[str, object]) -> str:
    """Hash the exact persisted dataset manifest used by the isolated run."""
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _python_breadth_manifest_summary(manifest: Mapping[str, object]) -> dict[str, object]:
    """Keep small, human-readable manifest fields beside the immutable run link."""
    keys = (
        "source",
        "timeframe",
        "adjustment",
        "session",
        "start_date",
        "end_date",
        "as_of",
        "membership_version",
        "requested_symbols",
        "batch_history_limit",
        "exclusions",
    )
    return {key: manifest[key] for key in keys if key in manifest}


async def _python_breadth_source_instrument_ids(db: AsyncSession, run: ResearchRun) -> list[int]:
    """Resolve the source run's declared symbols without falling back to a broad universe."""
    config = run.run_config if isinstance(run.run_config, dict) else {}
    raw_symbols = config.get("symbols")
    if not isinstance(raw_symbols, list):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "breadth_promotion_universe_unavailable",
                "message": "The breadth run has no declared member universe to promote.",
            },
        )
    symbols = list(
        dict.fromkeys(str(symbol).strip().upper() for symbol in raw_symbols if str(symbol).strip())
    )
    if not symbols:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "breadth_promotion_universe_unavailable",
                "message": "The breadth run declared an empty member universe.",
            },
        )
    instruments = (
        (await db.execute(select(Instrument).where(Instrument.symbol.in_(symbols)))).scalars().all()
    )
    by_symbol = {instrument.symbol.upper(): instrument for instrument in instruments}
    missing = [symbol for symbol in symbols if symbol not in by_symbol]
    if missing:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "breadth_promotion_universe_incomplete",
                "message": "The source member universe cannot be represented as a stable scan universe.",
                "missing_symbols": missing,
            },
        )
    return [by_symbol[symbol].id for symbol in symbols]


@router.post("/breadth/python", response_model=BreadthPythonRunOut, status_code=202)
async def queue_python_breadth(
    body: BreadthPythonRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Queue an isolated Boolean predicate or numeric Python-series target."""
    try:
        timeframe = Timeframe(body.timeframe)
    except ValueError as exc:
        raise HTTPException(
            422, detail={"code": "unsupported_timeframe", "timeframe": body.timeframe}
        ) from exc
    version = (
        await db.execute(
            select(CodeVersion)
            .join(CodeAsset)
            .options(selectinload(CodeVersion.asset))
            .where(
                CodeVersion.id == body.code_version_id,
                CodeAsset.user_id == current_user.id,
                CodeAsset.kind == "condition",
                CodeAsset.is_archived.is_(False),
            )
        )
    ).scalar_one_or_none()
    if version is None or version.output_contract not in {"boolean", "series"}:
        raise HTTPException(
            422,
            detail={
                "code": "python_breadth_condition_unavailable",
                "message": "The selected user-owned code version must be an active Boolean or numeric-series condition.",
            },
        )
    if body.condition_tree is None and body.output_contract != version.output_contract:
        raise HTTPException(
            422,
            detail={
                "code": "python_breadth_output_contract_mismatch",
                "declared": body.output_contract,
                "stored": version.output_contract,
            },
        )
    resolved_condition_tree: dict[str, object] | None = None
    if body.condition_tree is not None:
        if body.output_contract != "boolean":
            raise HTTPException(
                422,
                detail={"code": "python_condition_tree_requires_boolean_output"},
            )
        resolved_condition_tree, _ = await _resolve_python_condition_tree(
            body.condition_tree, db, current_user.id
        )
        if (
            _python_condition_tree_requires_benchmark(resolved_condition_tree)
            and not body.benchmark
        ):
            raise HTTPException(
                422,
                detail={
                    "code": "python_series_benchmark_required",
                    "message": "A benchmark symbol is required when a Python series comparison targets the benchmark dataset.",
                },
            )
        if body.series_target is not None:
            raise HTTPException(
                422,
                detail={"code": "python_condition_tree_series_target_conflict"},
            )
    series_target = body.series_target
    if body.output_contract == "series":
        if not isinstance(series_target, dict):
            raise HTTPException(
                422,
                detail={
                    "code": "python_series_target_required",
                    "message": "Numeric-series breadth requires an operator and threshold target.",
                },
            )
        operator = str(series_target.get("operator", "gte")).lower()
        threshold = series_target.get("threshold")
        if (
            operator not in {"gt", "gte", "lt", "lte", "eq", "ne"}
            or not isinstance(threshold, int | float)
            or isinstance(threshold, bool)
            or not math.isfinite(float(threshold))
        ):
            raise HTTPException(
                422,
                detail={"code": "invalid_python_series_target"},
            )
        scope = str(series_target.get("scope", "member")).lower()
        statistic = str(series_target.get("statistic", "mean")).lower()
        if scope not in {"member", "cross_sectional"}:
            raise HTTPException(422, detail={"code": "invalid_python_series_target_scope"})
        if scope == "cross_sectional" and statistic not in {"mean", "median", "min", "max", "std"}:
            raise HTTPException(422, detail={"code": "invalid_python_series_statistic"})
        series_target = {"operator": operator, "threshold": float(threshold)}
        if scope == "cross_sectional":
            series_target.update({"scope": scope, "statistic": statistic})
    if not isinstance(body.parameters, dict):
        raise HTTPException(422, detail={"code": "parameters_must_be_object"})

    placeholder = BreadthDefinitionRequest(
        universe=body.universe,
        condition=BreadthConditionRequest(kind="comparison", params={"field": "close"}),
        timeframe=timeframe.value,
        adjusted=body.adjusted,
        as_of=body.as_of,
        benchmark=body.benchmark,
    )
    (
        members,
        member_ids,
        universe_warnings,
        universe_provenance,
        membership_payload,
    ) = await _resolve_generic_breadth_universe(placeholder, db, current_user.id)
    membership_version = _generic_membership_version(membership_payload)
    parameters = dict(version.default_parameters or {})
    parameters.update(body.parameters)
    parameter_errors = validate_parameter_values(version.parameter_schema, parameters)
    if parameter_errors:
        raise HTTPException(
            422,
            detail={"code": "parameter_validation_failed", "errors": parameter_errors},
        )
    condition_metadata = _python_breadth_condition_metadata(
        version,
        parameters,
        output_contract=body.output_contract,
        series_target=series_target,
    )
    if resolved_condition_tree is not None:
        condition_metadata["condition_tree"] = resolved_condition_tree
    execution_mode = "breadth_history" if body.history else "breadth_current"
    definition_payload = {
        "universe": universe_provenance,
        "membership_version": membership_version,
        "condition": condition_metadata,
        "timeframe": timeframe.value,
        "adjustment": "split_adjusted" if body.adjusted else "raw",
        "session": body.session,
        "as_of": body.as_of.isoformat() if body.as_of else None,
        "benchmark": body.benchmark.upper() if body.benchmark else None,
        "execution_mode": execution_mode,
        "history_limit": body.history_limit,
        "output_contract": body.output_contract,
        "series_target": series_target,
        "condition_tree": resolved_condition_tree,
    }
    run_config = {
        "symbols": [member.symbol for member in members],
        "parameters": parameters,
        "timeframe": timeframe.value,
        "adjustment": "split_adjusted" if body.adjusted else "raw",
        "session": body.session,
        "as_of": body.as_of.isoformat() if body.as_of else None,
        "benchmark": body.benchmark.upper() if body.benchmark else None,
        "execution_mode": execution_mode,
        "history_limit": body.history_limit,
        "definition_hash": definition_hash(
            definition_payload, membership_version=membership_version
        ),
        "universe": {
            **universe_provenance,
            "membership_version": membership_version,
            "requested_count": len(members) + len(universe_warnings),
            "warnings": [warning.model_dump() for warning in universe_warnings],
        },
        "condition": condition_metadata,
        "output_contract": body.output_contract,
        "series_target": series_target,
        "condition_tree": resolved_condition_tree,
    }
    from app.routers.research import _materialize_declared_dataset

    manifest = await _materialize_declared_dataset(
        db,
        {
            "universe": universe_provenance,
            "membership_version": membership_version,
            "requested_count": len(member_ids) + len(universe_warnings),
        },
        run_config,
        lookback=version.lookback,
    )
    run = ResearchRun(
        user_id=current_user.id,
        code_version_id=version.id,
        run_config=run_config,
        dataset_manifest=manifest,
    )
    run.code_version = version
    db.add(run)
    await db.flush()
    enqueue_research_run(run)
    run.progress = {}
    return _python_breadth_run_out(run)


@router.get("/breadth/python/runs/{run_id}", response_model=BreadthPythonResultOut)
async def get_python_breadth_result(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Collect a queued Python breadth run without executing source in FastAPI."""
    run = await _load_python_breadth_run(db, run_id, current_user)
    config = run.run_config if isinstance(run.run_config, dict) else {}
    execution_mode = config.get("execution_mode", "breadth_current")
    requested_count = int(
        (config.get("universe") or {}).get("requested_count", 0)
        if isinstance(config.get("universe"), dict)
        else 0
    )
    points: list[BreadthPythonResultPointOut] = []
    current: BreadthPythonResultPointOut | None = None
    artifact = next(
        (
            item
            for item in run.artifacts
            if item.name
            == ("breadth_history" if execution_mode == "breadth_history" else "batch_cells")
        ),
        None,
    )
    if artifact and isinstance(artifact.payload, dict):
        value = artifact.payload.get("value")
        if execution_mode == "breadth_history" and isinstance(value, dict):
            raw_points = value.get("points")
            if isinstance(raw_points, list):
                points = [
                    _python_breadth_point(point, requested_count)
                    for point in raw_points
                    if isinstance(point, dict)
                ]
                current = points[-1] if points else None
        elif isinstance(value, dict):
            raw_cells = value.get("cells")
            current = _python_breadth_point(
                {
                    "timestamp": None,
                    "cells": raw_cells if isinstance(raw_cells, list) else [],
                },
                requested_count,
            )
    occurrences = _python_breadth_occurrences(points)
    manifest_warnings = _manifest_exclusion_warnings(
        run.dataset_manifest if isinstance(run.dataset_manifest, dict) else {}
    )
    if manifest_warnings:
        if current is not None:
            current = current.model_copy(
                update={
                    "excluded_count": current.excluded_count + len(manifest_warnings),
                    "exclusions": [*current.exclusions, *manifest_warnings],
                    "coverage": current.eligible_count / requested_count if requested_count else 0,
                }
            )
        points = [
            point.model_copy(
                update={
                    "excluded_count": point.excluded_count + len(manifest_warnings),
                    "exclusions": [*point.exclusions, *manifest_warnings],
                    "coverage": point.eligible_count / requested_count if requested_count else 0,
                }
            )
            for point in points
        ]
    return BreadthPythonResultOut(
        calculation_version="analysis-python-v1",
        data_provenance="canonical_local_database_then_isolated_runner",
        run_id=run.id,
        code_version_id=run.code_version_id,
        status=run.status,
        execution_mode=execution_mode,
        output_contract=str(config.get("output_contract") or "boolean"),
        series_target=(
            config.get("series_target") if isinstance(config.get("series_target"), dict) else None
        ),
        condition_tree=(
            config.get("condition_tree") if isinstance(config.get("condition_tree"), dict) else None
        ),
        definition_hash=str(config.get("definition_hash") or ""),
        universe=config.get("universe", {}),
        condition=config.get("condition", {}),
        dataset_manifest=run.dataset_manifest if isinstance(run.dataset_manifest, dict) else {},
        current=current,
        points=points,
        occurrences=occurrences,
        progress=run.progress if isinstance(getattr(run, "progress", {}), dict) else {},
        diagnostics=run.diagnostics if isinstance(run.diagnostics, list) else [],
    )


@router.post(
    "/breadth/python/runs/{run_id}/promote-scan",
    response_model=ScreenerOut,
    status_code=201,
)
async def promote_python_breadth_run_to_scan(
    run_id: int,
    body: BreadthPythonPromotionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Promote a completed breadth history without losing its source lineage.

    The resulting EasyScan is an explicitly labelled reusable current-data target over the
    source run's declared member IDs.  The source run ID and exact manifest fingerprint remain
    in the immutable conditions metadata; the promotion never claims that a current scan is a
    historical point-in-time replay.
    """
    run = await _load_python_breadth_run(db, run_id, current_user)
    config = run.run_config if isinstance(run.run_config, dict) else {}
    if config.get("execution_mode") != "breadth_history":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "breadth_promotion_requires_history",
                "message": "Only completed historical breadth runs can be promoted to a scan.",
            },
        )
    if run.status != "completed":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "breadth_promotion_requires_completed_run",
                "status": run.status,
            },
        )
    version = run.code_version
    if (
        version is None
        or version.asset is None
        or version.asset.user_id != current_user.id
        or version.asset.kind != "condition"
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "breadth_promotion_condition_unavailable",
                "message": "The source run does not reference an owned condition version.",
            },
        )
    source_contract = str(version.output_contract or "")
    output_adapter: str | None = None
    series_target = config.get("series_target")
    condition_tree = config.get("condition_tree")
    if isinstance(condition_tree, dict):
        if source_contract not in {"boolean", "series"}:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "breadth_promotion_tree_requires_boolean_source",
                    "message": "A recursive breadth tree must be anchored by a Boolean or numeric condition version.",
                },
            )
        if series_target is not None:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "breadth_promotion_tree_series_target_conflict",
                    "message": "A recursive breadth tree cannot be combined with a numeric series target.",
                },
            )
        output_adapter = "condition_tree_to_boolean"
    elif source_contract == "series":
        if (
            not isinstance(series_target, dict)
            or str(series_target.get("scope", "member")).lower() != "member"
        ):
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "breadth_promotion_scan_requires_member_series",
                    "message": "Only member-scoped numeric breadth targets can become Boolean scans.",
                },
            )
        output_adapter = "series_target_to_boolean"
    elif source_contract != "boolean":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "breadth_promotion_condition_unavailable",
                "message": "The source run does not provide a Boolean or thresholded numeric condition.",
            },
        )
    artifact = next(
        (item for item in run.artifacts if item.artifact_type == "breadth_history"),
        None,
    )
    if artifact is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "breadth_promotion_artifact_unavailable",
                "message": "The completed run has no persisted breadth history artifact.",
            },
        )
    instrument_ids = await _python_breadth_source_instrument_ids(db, run)
    name = body.name or f"Python breadth run {run.id}"
    existing = (
        await db.execute(
            select(ScreenerDefinition).where(
                ScreenerDefinition.user_id == current_user.id,
                func.lower(ScreenerDefinition.name) == name.lower(),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"A screener named '{name}' already exists")
    manifest = run.dataset_manifest if isinstance(run.dataset_manifest, dict) else {}
    universe = config.get("universe") if isinstance(config.get("universe"), dict) else {}
    source_metadata = {
        "type": "python_breadth_research_run",
        "source_run_id": run.id,
        "source_execution_mode": config.get("execution_mode"),
        "source_code_version_id": run.code_version_id,
        "source_definition_hash": str(config.get("definition_hash") or ""),
        "source_reproducibility_hash": run.reproducibility_hash,
        "source_dataset_manifest_sha256": _python_breadth_manifest_fingerprint(manifest),
        "source_dataset_manifest": _python_breadth_manifest_summary(manifest),
        "source_universe": universe,
        "target_semantics": "re_evaluate_current_data_over_source_member_ids",
        "point_in_time_source_preserved": True,
    }
    if isinstance(condition_tree, dict):
        source_metadata["condition_tree"] = condition_tree
    promoted_code_version_id = run.code_version_id
    if output_adapter is not None:
        source_metadata["output_adapter"] = output_adapter
        source_metadata["series_target"] = series_target
        stable_key = f"breadth-run-{run.id}-scan-condition"
        existing_asset = (
            await db.execute(
                select(CodeAsset).where(
                    CodeAsset.user_id == current_user.id,
                    CodeAsset.stable_key == stable_key,
                )
            )
        ).scalar_one_or_none()
        if existing_asset is not None:
            raise HTTPException(
                status_code=409, detail={"code": "breadth_promotion_already_exists"}
            )
        promoted_asset = CodeAsset(
            user_id=current_user.id,
            stable_key=stable_key,
            name=f"Breadth scan condition run {run.id}",
            kind="condition",
        )
        promoted_asset.versions.append(
            CodeVersion(
                version_number=1,
                source=version.source,
                output_contract="boolean",
                output_name="match",
                parameter_schema=dict(version.parameter_schema or {}),
                default_parameters=dict(version.default_parameters or {}),
                sdk_version=version.sdk_version,
                runtime_version=version.runtime_version,
                dependencies=list(version.dependencies or []),
                lookback=version.lookback,
                diagnostics=[
                    *(version.diagnostics or []),
                    {
                        "output_adapter": output_adapter,
                        "series_target": series_target,
                        "condition_tree": condition_tree,
                    },
                    {"promotion_lineage": source_metadata},
                ],
            )
        )
        db.add(promoted_asset)
        await db.flush()
        promoted_code_version_id = promoted_asset.versions[0].id
    timeframe_value = str(config.get("timeframe") or Timeframe.D1.value)
    try:
        timeframe = Timeframe(timeframe_value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "invalid_source_timeframe"}) from exc
    screener = ScreenerDefinition(
        user_id=current_user.id,
        name=name,
        description=body.description
        or f"Reusable current-data scan promoted from historical breadth run #{run.id}; source membership and manifest are retained.",
        universe_type="custom",
        universe_instrument_ids=instrument_ids,
        timeframe=timeframe,
        conditions={
            "type": "python_condition",
            "code_version_id": promoted_code_version_id,
            **({"condition_tree": condition_tree} if isinstance(condition_tree, dict) else {}),
            "provenance": source_metadata,
        },
        schedule=body.schedule,
        is_active=body.is_active,
    )
    db.add(screener)
    await db.flush()
    await db.refresh(screener)
    return screener


@router.post(
    "/breadth/python/runs/{run_id}/promote-plot",
    response_model=CodeAssetOut,
    status_code=201,
)
async def promote_python_breadth_run_to_plot(
    run_id: int,
    body: BreadthPythonPlotPromotionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Promote a completed breadth source into a reusable uPlot asset.

    Member-scoped numeric runs remain symbol-level plots.  An explicitly requested aggregate
    promotion instead re-evaluates the historical breadth predicate and exposes its aggregate
    percentage series, retaining cross-sectional/tree semantics rather than projecting them into a
    per-symbol value.
    """
    run = await _load_python_breadth_run(db, run_id, current_user)
    config = run.run_config if isinstance(run.run_config, dict) else {}
    if run.status != "completed":
        raise HTTPException(
            status_code=409,
            detail={"code": "breadth_promotion_requires_completed_run", "status": run.status},
        )
    execution_mode = config.get("execution_mode")
    if execution_mode not in {"breadth_current", "breadth_history"}:
        raise HTTPException(
            status_code=422, detail={"code": "breadth_plot_promotion_mode_unavailable"}
        )
    series_target = config.get("series_target")
    version = run.code_version
    if (
        version is None
        or version.asset is None
        or version.asset.user_id != current_user.id
        or version.asset.kind != "condition"
        or version.output_contract not in {"boolean", "series"}
    ):
        raise HTTPException(
            status_code=422,
            detail={"code": "breadth_plot_promotion_source_unavailable"},
        )
    condition_tree = config.get("condition_tree")
    if condition_tree is not None and not isinstance(condition_tree, dict):
        raise HTTPException(status_code=422, detail={"code": "invalid_python_condition_tree"})
    aggregate = bool(body.aggregate)
    if aggregate:
        if execution_mode != "breadth_history":
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "breadth_aggregate_plot_requires_history",
                    "message": "Aggregate breadth plots require a completed historical run.",
                },
            )
        has_cross_sectional_target = (
            isinstance(series_target, dict)
            and str(series_target.get("scope", "member")).lower() == "cross_sectional"
        )
        if condition_tree is None and not has_cross_sectional_target:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "breadth_aggregate_plot_requires_aggregate_source",
                    "message": "Aggregate plots require a cross-sectional target or condition tree.",
                },
            )
        if version.output_contract not in {"boolean", "series"}:
            raise HTTPException(
                status_code=422,
                detail={"code": "breadth_aggregate_plot_source_unavailable"},
            )
        artifact = next(
            (item for item in run.artifacts if item.artifact_type == "breadth_history"),
            None,
        )
        if artifact is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "breadth_plot_promotion_artifact_unavailable",
                    "message": "The completed run has no persisted breadth history artifact.",
                },
            )
        parameters = config.get("parameters") if isinstance(config.get("parameters"), dict) else {}
        source = "\n".join(
            [
                "study = research.breadth_python(",
                f"    dataset, {version.source!r}, {version.output_contract!r}, {parameters!r},",
                f"    {series_target!r}, {condition_tree!r}, True, {version.output_name!r}",
                ")",
                "points = study.get('points') or []",
                "timestamps = study.get('timestamps') or []",
                "output.series('percentage_history', {'timestamps': timestamps, 'values': [point.get('percentage') for point in points]})",
            ]
        )
        if len(source) > 500_000:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "breadth_plot_promotion_source_too_large",
                    "message": "The generated aggregate plot wrapper exceeds the source-size limit.",
                },
            )
        stable_key = f"breadth-run-{run.id}-aggregate-plot"
        existing = (
            await db.execute(
                select(CodeAsset).where(
                    CodeAsset.user_id == current_user.id,
                    CodeAsset.stable_key == stable_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail={"code": "breadth_aggregate_plot_promotion_already_exists"},
            )
        manifest = run.dataset_manifest if isinstance(run.dataset_manifest, dict) else {}
        lineage = {
            "promotion_lineage": {
                "source_run_id": run.id,
                "source_code_version_id": run.code_version_id,
                "source_definition_hash": str(config.get("definition_hash") or ""),
                "source_reproducibility_hash": run.reproducibility_hash,
                "source_dataset_manifest_sha256": _python_breadth_manifest_fingerprint(manifest),
                "source_universe": config.get("universe", {}),
                "source_symbols": config.get("symbols", []),
                "universe_source_id": (
                    config.get("universe", {}).get("source_id")
                    if isinstance(config.get("universe"), dict)
                    else None
                ),
                "source_condition_tree": condition_tree,
                "source_series_target": series_target,
                "semantics": "re_evaluate_breadth_as_aggregate_percentage_plot",
                "output_name": "percentage_history",
            },
            # The research job protocol carries this explicit adapter to the
            # isolated runner.  A series plot remains a normal chart asset;
            # only its prepared-universe execution mode is specialized.
            "output_adapter": "breadth_aggregate_percentage",
        }
        asset = CodeAsset(
            user_id=current_user.id,
            stable_key=stable_key,
            name=body.name or f"Breadth aggregate plot run {run.id}",
            kind="plot",
        )
        asset.versions.append(
            CodeVersion(
                version_number=1,
                source=source,
                output_contract="series",
                output_name="percentage_history",
                parameter_schema={},
                default_parameters={},
                sdk_version=version.sdk_version,
                runtime_version=version.runtime_version,
                dependencies=list(version.dependencies or []),
                lookback=version.lookback,
                diagnostics=[*(version.diagnostics or []), lineage],
            )
        )
        db.add(asset)
        await db.flush()
        await db.refresh(asset)
        return asset

    if config.get("output_contract") != "series":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "breadth_plot_promotion_requires_series",
                "message": "Only numeric-series breadth runs can be promoted to a member chart plot.",
            },
        )
    if (
        isinstance(series_target, dict)
        and str(series_target.get("scope", "member")).lower() != "member"
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "breadth_plot_promotion_requires_member_scope",
                "message": "A cross-sectional aggregate requires an explicit aggregate plot target.",
            },
        )
    if condition_tree is not None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "breadth_plot_promotion_requires_member_series",
                "message": "Recursive Boolean trees require an explicit aggregate plot target.",
            },
        )
    name = body.name or f"Breadth plot run {run.id}"
    stable_key = f"breadth-run-{run.id}-plot"
    existing = (
        await db.execute(
            select(CodeAsset).where(
                CodeAsset.user_id == current_user.id,
                CodeAsset.stable_key == stable_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409, detail={"code": "breadth_plot_promotion_already_exists"}
        )
    manifest = run.dataset_manifest if isinstance(run.dataset_manifest, dict) else {}
    lineage = {
        "promotion_lineage": {
            "source_run_id": run.id,
            "source_code_version_id": run.code_version_id,
            "source_definition_hash": str(config.get("definition_hash") or ""),
            "source_reproducibility_hash": run.reproducibility_hash,
            "source_dataset_manifest_sha256": _python_breadth_manifest_fingerprint(manifest),
            "source_universe": config.get("universe", {}),
            "semantics": "re_evaluate_member_numeric_series_on_selected_symbol",
        }
    }
    asset = CodeAsset(
        user_id=current_user.id,
        stable_key=stable_key,
        name=name,
        kind="plot",
    )
    asset.versions.append(
        CodeVersion(
            version_number=1,
            source=version.source,
            output_contract="series",
            output_name=version.output_name,
            parameter_schema=dict(version.parameter_schema or {}),
            default_parameters=dict(version.default_parameters or {}),
            sdk_version=version.sdk_version,
            runtime_version=version.runtime_version,
            dependencies=list(version.dependencies or []),
            lookback=version.lookback,
            diagnostics=[*(version.diagnostics or []), lineage],
        )
    )
    db.add(asset)
    await db.flush()
    await db.refresh(asset)
    return asset


@router.post(
    "/breadth/python/runs/{run_id}/promote-column",
    response_model=CodeAssetOut,
    status_code=201,
)
async def promote_python_breadth_run_to_column(
    run_id: int,
    body: BreadthPythonColumnPromotionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Promote a completed member-level numeric series through a scalar column adapter."""
    run = await _load_python_breadth_run(db, run_id, current_user)
    config = run.run_config if isinstance(run.run_config, dict) else {}
    if run.status != "completed":
        raise HTTPException(
            status_code=409,
            detail={"code": "breadth_promotion_requires_completed_run", "status": run.status},
        )
    if config.get("output_contract") != "series":
        raise HTTPException(
            status_code=422, detail={"code": "breadth_column_promotion_requires_series"}
        )
    series_target = config.get("series_target")
    if (
        isinstance(series_target, dict)
        and str(series_target.get("scope", "member")).lower() != "member"
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "breadth_column_promotion_requires_member_scope",
                "message": "A cross-sectional aggregate must remain a Study Lab series artifact.",
            },
        )
    if config.get("condition_tree") is not None:
        raise HTTPException(
            status_code=422, detail={"code": "breadth_column_promotion_requires_member_series"}
        )
    version = run.code_version
    if (
        version is None
        or version.asset is None
        or version.asset.user_id != current_user.id
        or version.asset.kind != "condition"
        or version.output_contract != "series"
    ):
        raise HTTPException(
            status_code=422, detail={"code": "breadth_column_promotion_source_unavailable"}
        )
    stable_key = f"breadth-run-{run.id}-column"
    existing = (
        await db.execute(
            select(CodeAsset).where(
                CodeAsset.user_id == current_user.id,
                CodeAsset.stable_key == stable_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409, detail={"code": "breadth_column_promotion_already_exists"}
        )
    manifest = run.dataset_manifest if isinstance(run.dataset_manifest, dict) else {}
    lineage = {
        "promotion_lineage": {
            "source_run_id": run.id,
            "source_code_version_id": run.code_version_id,
            "source_definition_hash": str(config.get("definition_hash") or ""),
            "source_reproducibility_hash": run.reproducibility_hash,
            "source_dataset_manifest_sha256": _python_breadth_manifest_fingerprint(manifest),
            "source_universe": config.get("universe", {}),
            "semantics": "re_evaluate_member_numeric_series_latest_value",
        },
        "output_adapter": "latest_series_to_scalar",
    }
    asset = CodeAsset(
        user_id=current_user.id,
        stable_key=stable_key,
        name=body.name or f"Breadth column run {run.id}",
        kind="column",
    )
    asset.versions.append(
        CodeVersion(
            version_number=1,
            source=version.source,
            output_contract="scalar",
            output_name=version.output_name,
            parameter_schema=dict(version.parameter_schema or {}),
            default_parameters=dict(version.default_parameters or {}),
            sdk_version=version.sdk_version,
            runtime_version=version.runtime_version,
            dependencies=list(version.dependencies or []),
            lookback=version.lookback,
            diagnostics=[*(version.diagnostics or []), lineage],
        )
    )
    db.add(asset)
    await db.flush()
    await db.refresh(asset)
    return asset


@router.post(
    "/breadth/python/runs/{run_id}/promote-study",
    response_model=CodeAssetOut,
    status_code=201,
)
async def promote_python_breadth_run_to_study(
    run_id: int,
    body: BreadthPythonStudyPromotionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Promote an isolated breadth run into a reusable structured Study Lab asset.

    Cross-sectional numeric targets are deliberately kept as aggregate studies.  They must
    not be flattened into a per-symbol plot or column, because that would erase the selected
    group statistic, denominator, and timestamp alignment.  The generated wrapper carries
    the exact source, parameters, tree, target, and source-version lineage into the isolated
    runner's ``research.breadth_python`` helper.
    """
    run = await _load_python_breadth_run(db, run_id, current_user)
    config = run.run_config if isinstance(run.run_config, dict) else {}
    if run.status != "completed":
        raise HTTPException(
            status_code=409,
            detail={"code": "breadth_promotion_requires_completed_run", "status": run.status},
        )
    if config.get("execution_mode") != "breadth_history":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "breadth_study_promotion_requires_history",
                "message": "Only completed historical breadth runs can become reusable studies.",
            },
        )
    artifact = next(
        (item for item in run.artifacts if item.artifact_type == "breadth_history"),
        None,
    )
    if artifact is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "breadth_study_promotion_artifact_unavailable",
                "message": "The completed run has no persisted breadth history artifact.",
            },
        )
    version = run.code_version
    if (
        version is None
        or version.asset is None
        or version.asset.user_id != current_user.id
        or version.asset.kind != "condition"
        or version.output_contract not in {"boolean", "series"}
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "breadth_study_promotion_source_unavailable",
                "message": "The source run does not reference an owned Boolean or numeric-series condition.",
            },
        )
    source_contract = str(version.output_contract)
    series_target = config.get("series_target")
    if series_target is not None and not isinstance(series_target, dict):
        raise HTTPException(status_code=422, detail={"code": "invalid_python_series_target"})
    condition_tree = config.get("condition_tree")
    if condition_tree is not None and not isinstance(condition_tree, dict):
        raise HTTPException(status_code=422, detail={"code": "invalid_python_condition_tree"})
    parameters = config.get("parameters") if isinstance(config.get("parameters"), dict) else {}
    # These values came from JSON/Pydantic inputs and are represented as literals in the
    # generated source.  ``repr`` keeps the wrapper data-only and prevents interpolation as
    # executable code; the original predicate is still validated again inside the runner.
    source = "\n".join(
        [
            "study = research.breadth_python(",
            f"    dataset, {version.source!r}, {source_contract!r}, {parameters!r},",
            f"    {series_target!r}, {condition_tree!r}, True, {version.output_name!r}",
            ")",
            "points = study['points']",
            "current = study.get('current') or {}",
            "timestamps = study.get('timestamps') or []",
            "output.scalar('sample_size', study.get('sample_size', 0))",
            "output.scalar('current_percentage', current.get('percentage'))",
            "output.scalar('current_pass_count', current.get('pass_count'))",
            "output.scalar('current_eligible_count', current.get('eligible_count'))",
            "output.scalar('current_group_value', current.get('group_value'))",
            "output.series('percentage_history', {'timestamps': timestamps, 'values': [point.get('percentage') for point in points]})",
            "output.series('group_value_history', {'timestamps': timestamps, 'values': [point.get('group_value') for point in points]})",
            "output.table('breadth_members', current.get('rows', []))",
            "output.table('breadth_exclusions', current.get('exclusions', []))",
            "output.table('historical_breadth', points)",
        ]
    )
    if len(source) > 500_000:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "breadth_study_promotion_source_too_large",
                "message": "The generated Study Lab wrapper exceeds the source-size limit.",
            },
        )
    stable_key = f"breadth-run-{run.id}-study"
    existing = (
        await db.execute(
            select(CodeAsset).where(
                CodeAsset.user_id == current_user.id,
                CodeAsset.stable_key == stable_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={"code": "breadth_study_promotion_already_exists"},
        )
    manifest = run.dataset_manifest if isinstance(run.dataset_manifest, dict) else {}
    lineage = {
        "promotion_lineage": {
            "source_run_id": run.id,
            "source_code_version_id": run.code_version_id,
            "source_definition_hash": str(config.get("definition_hash") or ""),
            "source_reproducibility_hash": run.reproducibility_hash,
            "source_dataset_manifest_sha256": _python_breadth_manifest_fingerprint(manifest),
            "source_universe": config.get("universe", {}),
            "source_condition_tree": condition_tree,
            "source_series_target": series_target,
            "semantics": "re_evaluate_isolated_member_predicate_as_aggregate_study",
        }
    }
    asset = CodeAsset(
        user_id=current_user.id,
        stable_key=stable_key,
        name=body.name or f"Breadth study run {run.id}",
        kind="study",
    )
    asset.versions.append(
        CodeVersion(
            version_number=1,
            source=source,
            output_contract="study",
            parameter_schema={},
            default_parameters={},
            sdk_version=version.sdk_version,
            runtime_version=version.runtime_version,
            dependencies=list(version.dependencies or []),
            lookback=version.lookback,
            diagnostics=[*(version.diagnostics or []), lineage],
        )
    )
    db.add(asset)
    await db.flush()
    await db.refresh(asset)
    return asset


@router.post("/breadth", response_model=BreadthDefinitionOut)
async def evaluate_generic_breadth(
    definition: BreadthDefinitionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Evaluate one reusable condition across a canonical local universe.

    This endpoint intentionally resolves only local canonical identities.  It
    never fans out to a provider on a user request and labels ETF holdings as
    proxy membership rather than implying official index constituents.
    """

    try:
        timeframe = Timeframe(definition.timeframe)
    except ValueError as exc:
        raise HTTPException(
            422,
            detail={"code": "unsupported_timeframe", "timeframe": definition.timeframe},
        ) from exc

    condition_definition, condition_metadata = await _resolve_generic_breadth_condition(
        definition, db, current_user
    )

    universe_kind = definition.universe.kind
    members: list[BreadthMember] = []
    member_ids: list[int] = []
    universe_warnings: list[AnalysisWarning] = []
    universe_provenance: dict[str, object]
    membership_version_payload: object

    if universe_kind == "benchmark_family":
        (
            members,
            member_ids,
            universe_warnings,
            universe_provenance,
            membership_version_payload,
        ) = await _resolve_benchmark_family_breadth_universe(definition, db)

    elif universe_kind == "group":
        if not definition.universe.key:
            raise HTTPException(
                422, detail={"code": "universe_key_required", "kind": universe_kind}
            )
        group = (
            await db.execute(
                select(MarketGroup)
                .options(
                    selectinload(MarketGroup.members).selectinload(MarketGroupMember.instrument)
                )
                .where(MarketGroup.stable_key == definition.universe.key)
            )
        ).scalar_one_or_none()
        if group is None:
            raise HTTPException(
                404,
                detail={"code": "market_group_not_found", "group_key": definition.universe.key},
            )
        selected_members = (
            _group_members_at(group, definition.as_of)
            if definition.universe.point_in_time
            else list(group.members)
        )
        for member in selected_members:
            if member.instrument is None:
                universe_warnings.append(
                    _generic_breadth_warning("unresolved_member", member.instrument_id)
                )
                continue
            members.append(
                BreadthMember(
                    member.instrument_id, member.instrument.symbol, member.instrument.name
                )
            )
            member_ids.append(member.instrument_id)
        membership_version_payload = _group_membership_version(group, selected_members)
        universe_provenance = {
            **_group_provenance(
                group, definition.as_of if definition.universe.point_in_time else None
            ),
            "kind": "market_group",
            "stable_key": group.stable_key,
            "membership_semantics": "curated_group_members",
        }

    elif universe_kind == "etf_holdings":
        if not definition.universe.key:
            raise HTTPException(
                422, detail={"code": "universe_key_required", "kind": universe_kind}
            )
        etf = await _instrument(db, definition.universe.key)
        profile = (
            await db.execute(select(ETFProfile).where(ETFProfile.instrument_id == etf.id))
        ).scalar_one_or_none()
        if profile is None:
            raise HTTPException(404, detail={"code": "etf_profile_not_found", "symbol": etf.symbol})
        statement = holdings_snapshot_source_filter(
            select(ETFHoldingsSnapshot).where(ETFHoldingsSnapshot.etf_profile_id == profile.id)
        )
        if definition.universe.point_in_time:
            statement = _holdings_snapshot_at(statement, definition.as_of)
        snapshot = (
            await db.execute(
                statement.options(
                    selectinload(ETFHoldingsSnapshot.rows).selectinload(
                        ETFHolding.constituent_instrument
                    )
                )
                .order_by(
                    ETFHoldingsSnapshot.composition_date.desc(),
                    ETFHoldingsSnapshot.known_at.desc().nullslast(),
                    ETFHoldingsSnapshot.id.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if snapshot is None:
            raise HTTPException(
                404,
                detail={"code": "holdings_snapshot_not_found", "symbol": etf.symbol},
            )
        for holding in snapshot.rows:
            if not holding.constituent_instrument_id or holding.constituent_instrument is None:
                universe_warnings.append(_generic_breadth_warning("unresolved_member", None))
                continue
            if holding.holding_type != "equity" or holding.row_type != "security":
                universe_warnings.append(
                    AnalysisWarning(
                        code="non_equity_holding",
                        message="Non-equity ETF exposure is excluded from breadth.",
                    )
                )
                continue
            instrument = holding.constituent_instrument
            members.append(BreadthMember(instrument.id, instrument.symbol, instrument.name))
            member_ids.append(instrument.id)
        membership_version_payload = {
            "snapshot_id": snapshot.id,
            "snapshot_hash": snapshot.snapshot_hash,
            "instrument_ids": sorted(member_ids),
        }
        universe_provenance = {
            "kind": "etf_holdings_proxy",
            "etf_symbol": etf.symbol,
            "membership_semantics": "etf_proxy_membership",
            "composition_date": snapshot.composition_date.isoformat(),
            "known_at": snapshot.known_at.isoformat() if snapshot.known_at else None,
            "source_provider": snapshot.source_provider,
            "provenance": snapshot.provenance,
            "completeness_status": snapshot.completeness_status,
            "snapshot_hash": snapshot.snapshot_hash,
        }

    elif universe_kind == "watchlist":
        (
            members,
            member_ids,
            universe_warnings,
            universe_provenance,
            membership_version_payload,
        ) = await _resolve_user_watchlist_breadth_universe(definition, db, current_user.id)

    else:
        requested_symbols = list(
            dict.fromkeys(
                symbol.strip().upper() for symbol in definition.universe.symbols if symbol.strip()
            )
        )
        if not requested_symbols:
            raise HTTPException(422, detail={"code": "symbols_required", "kind": universe_kind})
        instruments = (
            (await db.execute(select(Instrument).where(Instrument.symbol.in_(requested_symbols))))
            .scalars()
            .all()
        )
        by_symbol = {instrument.symbol.upper(): instrument for instrument in instruments}
        for symbol in requested_symbols:
            instrument = by_symbol.get(symbol)
            if instrument is None:
                universe_warnings.append(
                    AnalysisWarning(
                        code="instrument_not_found",
                        message=f"No canonical instrument exists for {symbol}.",
                    )
                )
                continue
            members.append(BreadthMember(instrument.id, instrument.symbol, instrument.name))
            member_ids.append(instrument.id)
        membership_version_payload = {
            "symbols": requested_symbols,
            "instrument_ids": sorted(member_ids),
        }
        universe_provenance = {
            "kind": "explicit_symbols",
            "membership_semantics": "canonical_local_instruments",
            "requested_symbols": requested_symbols,
        }

    bars_by_id = _truncate_bars_at(
        await _bars_by_instrument(db, member_ids, timeframe, definition.adjusted), definition.as_of
    )
    events_by_id: dict[int, list[InstrumentEvent] | None] | None = None
    event_provenance: dict[str, object] = {}
    if _generic_condition_requires_events(condition_definition.model_dump()):
        events_by_id, event_provenance = await _breadth_events_by_instrument(db, member_ids)
    benchmark_bars = None
    reference_member_ids: list[int] = []
    reference_warnings: list[AnalysisWarning] = []
    reference_provenance: dict[str, object] = {}
    if _generic_condition_requires_benchmark(condition_definition.model_dump()):
        if definition.reference_universe is not None:
            (
                benchmark_bars,
                reference_member_ids,
                reference_warnings,
                reference_provenance,
            ) = await _resolve_generic_breadth_reference(
                definition, condition_definition.model_dump(), timeframe, db, current_user.id
            )
        else:
            if not definition.benchmark:
                raise HTTPException(422, detail={"code": "benchmark_required"})
            benchmark = await _instrument(db, definition.benchmark)
            benchmark_bars = _truncate_bars_at(
                await _bars_by_instrument(db, [benchmark.id], timeframe, definition.adjusted),
                definition.as_of,
            ).get(benchmark.id, [])
    elif definition.reference_universe is not None:
        raise HTTPException(
            422,
            detail={
                "code": "reference_universe_requires_series_condition",
                "message": "A reference universe is only meaningful for a benchmark/peer-dependent condition.",
            },
        )

    condition = {
        "kind": condition_definition.kind,
        "target_scope": condition_definition.target_scope,
        "params": condition_definition.params,
        **condition_metadata,
    }
    if definition.benchmark:
        condition["reference_symbol"] = definition.benchmark.upper()
    if definition.reference_universe is not None:
        condition["reference_universe"] = definition.reference_universe.model_dump(mode="json")
        condition["reference_target"] = reference_provenance
    if event_provenance:
        condition["event_target"] = event_provenance
    results, aggregate = evaluate_breadth(
        members,
        bars_by_id,
        condition,
        benchmark_bars=benchmark_bars,
        events_by_instrument=events_by_id,
    )
    warnings = [*universe_warnings, *reference_warnings]
    member_outputs: list[BreadthMemberResultOut] = []
    for result in results:
        warning = (
            _generic_breadth_warning(result.exclusion_code, result.instrument_id)
            if result.exclusion_code
            else None
        )
        if warning:
            warnings.append(warning)
        member_outputs.append(
            BreadthMemberResultOut(
                instrument_id=result.instrument_id,
                symbol=result.symbol,
                name=result.name,
                value=result.value,
                metric=result.metric,
                observation_time=result.observation_time,
                warning=warning,
                diagnostics=[
                    BreadthConditionDiagnosticOut(
                        path=item.path,
                        kind=item.kind,
                        status=item.status,
                        value=item.value,
                        metric=item.metric,
                        code=item.code,
                    )
                    for item in result.diagnostics
                ],
            )
        )
    membership_version = _generic_membership_version(membership_version_payload)
    definition_payload = definition.model_dump(mode="json")
    definition_payload["condition"] = condition_definition.model_dump(mode="json")
    definition_payload["condition_asset"] = condition_metadata
    if definition.benchmark:
        definition_payload["benchmark"] = definition.benchmark.upper()
    freshness, freshness_detail = await _batch_freshness(
        db, [*member_ids, *reference_member_ids], timeframe, definition.adjusted
    )
    latest_as_of = max(
        (result.observation_time for result in results if result.observation_time), default=None
    )
    return BreadthDefinitionOut(
        definition_version=definition.version,
        definition_hash=definition_hash(definition_payload, membership_version=membership_version),
        universe={**universe_provenance, "membership_version": membership_version},
        condition=condition,
        condition_asset_key=condition_metadata.get("asset_key"),
        condition_library_version=condition_metadata.get("library_version"),
        python_code_version_id=condition_metadata.get("python_code_version_id"),
        timeframe=timeframe.value,
        adjustment="split_adjusted" if definition.adjusted else "raw",
        as_of=latest_as_of,
        freshness=freshness,
        freshness_detail=freshness_detail,
        requested_count=int(aggregate["requested_count"]) + len(universe_warnings),
        eligible_count=int(aggregate["eligible_count"]),
        pass_count=int(aggregate["pass_count"]),
        excluded_count=int(aggregate["excluded_count"]) + len(universe_warnings),
        percentage=aggregate["percentage"],
        coverage=(
            int(aggregate["eligible_count"])
            / (int(aggregate["requested_count"]) + len(universe_warnings))
            if int(aggregate["requested_count"]) + len(universe_warnings)
            else 0.0
        ),
        members=member_outputs,
        exclusions=warnings,
    )


@router.post("/breadth/history", response_model=BreadthDefinitionHistoryOut)
async def evaluate_generic_breadth_history(
    definition: BreadthHistoryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return aligned historical values for the same generic breadth definition."""

    try:
        timeframe = Timeframe(definition.timeframe)
    except ValueError as exc:
        raise HTTPException(
            422,
            detail={"code": "unsupported_timeframe", "timeframe": definition.timeframe},
        ) from exc
    condition_definition, condition_metadata = await _resolve_generic_breadth_condition(
        definition, db, current_user
    )
    (
        members,
        member_ids,
        universe_warnings,
        universe_provenance,
        membership_payload,
    ) = await _resolve_generic_breadth_universe(definition, db, current_user.id)
    bars_by_id = await _bars_by_instrument(db, member_ids, timeframe, definition.adjusted)
    bars_by_id = _truncate_bars_at(bars_by_id, definition.as_of)
    events_by_id: dict[int, list[InstrumentEvent] | None] | None = None
    event_provenance: dict[str, object] = {}
    if _generic_condition_requires_events(condition_definition.model_dump()):
        events_by_id, event_provenance = await _breadth_events_by_instrument(db, member_ids)
    benchmark_bars = None
    reference_member_ids: list[int] = []
    reference_warnings: list[AnalysisWarning] = []
    reference_provenance: dict[str, object] = {}
    if _generic_condition_requires_benchmark(condition_definition.model_dump()):
        if definition.reference_universe is not None:
            (
                benchmark_bars,
                reference_member_ids,
                reference_warnings,
                reference_provenance,
            ) = await _resolve_generic_breadth_reference(
                definition, condition_definition.model_dump(), timeframe, db, current_user.id
            )
        else:
            if not definition.benchmark:
                raise HTTPException(422, detail={"code": "benchmark_required"})
            benchmark = await _instrument(db, definition.benchmark)
            benchmark_bars = _truncate_bars_at(
                await _bars_by_instrument(db, [benchmark.id], timeframe, definition.adjusted),
                definition.as_of,
            ).get(benchmark.id, [])
    elif definition.reference_universe is not None:
        raise HTTPException(
            422,
            detail={
                "code": "reference_universe_requires_series_condition",
                "message": "A reference universe is only meaningful for a benchmark/peer-dependent condition.",
            },
        )
    condition = {
        "kind": condition_definition.kind,
        "target_scope": condition_definition.target_scope,
        "params": condition_definition.params,
        **condition_metadata,
    }
    if definition.benchmark:
        condition["reference_symbol"] = definition.benchmark.upper()
    if definition.reference_universe is not None:
        condition["reference_universe"] = definition.reference_universe.model_dump(mode="json")
        condition["reference_target"] = reference_provenance
    if event_provenance:
        condition["event_target"] = event_provenance
    raw_points = evaluate_breadth_history(
        members,
        bars_by_id,
        condition,
        limit=definition.limit,
        benchmark_bars=benchmark_bars,
        events_by_instrument=events_by_id,
    )
    occurrence_rows = detect_breadth_occurrences(raw_points)
    warnings = [*universe_warnings, *reference_warnings]
    points: list[BreadthDefinitionHistoryPointOut] = []
    for raw_point in raw_points:
        member_outputs: list[BreadthMemberResultOut] = []
        point_warnings: list[AnalysisWarning] = []
        for result in raw_point["members"]:
            warning = (
                _generic_breadth_warning(result.exclusion_code, result.instrument_id)
                if result.exclusion_code
                else None
            )
            if warning:
                point_warnings.append(warning)
            member_outputs.append(
                BreadthMemberResultOut(
                    instrument_id=result.instrument_id,
                    symbol=result.symbol,
                    name=result.name,
                    value=result.value,
                    metric=result.metric,
                    observation_time=result.observation_time,
                    warning=warning,
                    diagnostics=[
                        BreadthConditionDiagnosticOut(
                            path=item.path,
                            kind=item.kind,
                            status=item.status,
                            value=item.value,
                            metric=item.metric,
                            code=item.code,
                        )
                        for item in result.diagnostics
                    ],
                )
            )
        warnings.extend(point_warnings)
        points.append(
            BreadthDefinitionHistoryPointOut(
                timestamp=raw_point["timestamp"],
                requested_count=raw_point["requested_count"],
                eligible_count=raw_point["eligible_count"],
                pass_count=raw_point["pass_count"],
                excluded_count=raw_point["excluded_count"],
                percentage=raw_point["percentage"],
                coverage=raw_point["coverage"],
                members=member_outputs,
                exclusions=point_warnings,
            )
        )
    membership_version = _generic_membership_version(membership_payload)
    definition_payload = definition.model_dump(mode="json")
    definition_payload["condition"] = condition_definition.model_dump(mode="json")
    definition_payload["condition_asset"] = condition_metadata
    if definition.benchmark:
        definition_payload["benchmark"] = definition.benchmark.upper()
    freshness, freshness_detail = await _batch_freshness(
        db, [*member_ids, *reference_member_ids], timeframe, definition.adjusted
    )
    return BreadthDefinitionHistoryOut(
        definition_version=definition.version,
        definition_hash=definition_hash(definition_payload, membership_version=membership_version),
        universe={**universe_provenance, "membership_version": membership_version},
        condition=condition,
        condition_asset_key=condition_metadata.get("asset_key"),
        condition_library_version=condition_metadata.get("library_version"),
        python_code_version_id=condition_metadata.get("python_code_version_id"),
        timeframe=timeframe.value,
        adjustment="split_adjusted" if definition.adjusted else "raw",
        as_of=definition.as_of or (points[-1].timestamp if points else None),
        freshness=freshness,
        freshness_detail=freshness_detail,
        points=points,
        occurrences=[
            BreadthDefinitionHistoryOccurrenceOut(**occurrence) for occurrence in occurrence_rows
        ],
        exclusions=warnings,
    )
