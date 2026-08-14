"""Canonical local-database analysis endpoints for workstation tools."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_observation import DatasetStatus, InstrumentDatasetState
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
from app.schemas.analysis import (
    AnalysisCell,
    AnalysisPoint,
    AnalysisWarning,
    BreadthConditionRequest,
    BreadthDefinitionHistoryOut,
    BreadthDefinitionHistoryPointOut,
    BreadthDefinitionOut,
    BreadthDefinitionRequest,
    BreadthHistoryOut,
    BreadthHistoryPoint,
    BreadthHistoryRequest,
    BreadthMemberResultOut,
    BreadthOut,
    BreadthPythonResultOut,
    BreadthPythonResultPointOut,
    BreadthPythonRunOut,
    BreadthPythonRunRequest,
    ETFConstituentSnapshotOut,
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
from app.services.breadth import (
    BreadthMember,
    definition_hash,
    evaluate_breadth,
    evaluate_breadth_history,
)
from app.services.indicators import OHLCVSeries, get_latest_value
from app.services.parameter_validation import validate_parameter_values
from app.services.research_jobs import (
    collect_research_result,
    enqueue_research_run,
    read_research_progress,
)

router = APIRouter(prefix="/analysis", tags=["analysis"])

_PERIODS = {"1D": 1, "1W": 5, "1M": 21, "3M": 63, "6M": 126, "YTD": None, "1Y": 252}
_CALENDAR_YEAR_LOOKBACK = 5

_HOLDING_EXCLUSION_MESSAGES = {
    "cash_holding": "Cash, collateral, or currency exposure is excluded from equity analysis.",
    "derivative_holding": "Derivative exposure is excluded from equity analysis.",
    "unresolved_holding": "The holding has no resolved canonical equity instrument.",
    "non_equity_holding": "The holding is not a supported equity security.",
}


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
    current_year = [item for item in values if item[0].year == latest_timestamp.year]
    cells: dict[str, AnalysisCell] = {}
    for period, offset in _PERIODS.items():
        base: float | None
        if period == "YTD":
            base = current_year[0][1] if len(current_year) >= 2 else None
            code = "insufficient_ytd_history"
            message = (
                "YTD requires at least two aligned constituent observations in the current year."
            )
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
    if value.tzinfo is None and as_of.tzinfo is not None:
        value = value.replace(tzinfo=as_of.tzinfo)
    return value <= as_of


def _wire_datetime(value: datetime | None) -> str | None:
    """Use one canonical UTC spelling in provenance fields and cache identities."""
    if value is None:
        return None
    encoded = value.isoformat()
    return encoded.replace("+00:00", "Z")


def _group_members_at(group: MarketGroup, as_of: datetime | None) -> list[MarketGroupMember]:
    """Select a group's versioned members without admitting future membership."""
    # Root groups created before lifecycle timestamps were introduced may have
    # no group-level known_at.  Their members still carry the authoritative
    # point-in-time boundary, so retain the static-root compatibility rule while
    # requiring each member's known_at below.
    if not _is_known_at(group.effective_at, as_of) or not _is_known_at(group.known_at, as_of):
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
    current_year_bars = [bar for bar in bars if bar.ts.year == latest.ts.year]
    cells: dict[str, AnalysisCell] = {}
    for period, offset in _PERIODS.items():
        if period == "YTD":
            if len(current_year_bars) < 2 or current_year_bars[0].close == 0:
                cells[period] = _cell(
                    None,
                    latest,
                    AnalysisWarning(
                        code="insufficient_ytd_history",
                        message="YTD requires at least two non-zero bars in the current calendar year.",
                        instrument_id=instrument_id,
                    ),
                )
            else:
                cells[period] = _cell(float(latest.close / current_year_bars[0].close - 1), latest)
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
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return local, reproducible technical values without a provider fetch."""
    instrument = await _instrument(db, symbol)
    bars = (await _bars_by_instrument(db, [instrument.id], timeframe, adjusted)).get(
        instrument.id, []
    )
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
            as_of=None,
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
        as_of=latest.ts,
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
        sampled = _sample_aligned_points(aligned, sampling)
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
                    warnings=warnings,
                )
            )
            continue
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
        rows.append(
            RelativeRotationRow(
                instrument_id=instrument.id,
                symbol=instrument.symbol,
                name=instrument.name,
                trend=latest.trend,
                momentum=latest.momentum,
                state=state,
                heading=math.degrees(math.atan2(latest.momentum, latest.trend)),
                distance=math.hypot(latest.trend, latest.momentum),
                velocity=velocity,
                transition=f"{previous_state}->{state}"
                if previous_state and previous_state != state
                else None,
                time_in_state=time_in_state,
                coverage=len(aligned) / maximum,
                tail=coordinates[-tail_length:],
                warnings=warnings,
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
    rows: list[GroupSnapshotRow] = []
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
                GroupSnapshotRow(
                    instrument_id=instrument.id,
                    symbol=instrument.symbol,
                    name=instrument.name,
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
            GroupSnapshotRow(
                instrument_id=instrument.id,
                symbol=instrument.symbol,
                name=instrument.name,
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
    "invalid_condition_params": "The condition parameters are invalid.",
    "unsupported_field": "The requested comparison field is not supported by this runtime.",
    "condition_clause_excluded": "A nested breadth condition could not be evaluated for this member.",
    "missing_bar_at_timestamp": "The member has no bar at this timestamp and was excluded without forward-fill.",
    "benchmark_missing_at_timestamp": "The benchmark has no bar at this timestamp.",
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
    if kind == "comparison" and str(params.get("field", "")).lower() in {
        "relative_strength",
        "relative_return",
    }:
        return True
    children = params.get("conditions")
    return isinstance(children, list) and any(
        isinstance(child, Mapping) and _generic_condition_requires_benchmark(child)
        for child in children
    )


def _generic_membership_version(payload: object) -> int:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return int(hashlib.sha256(encoded.encode()).hexdigest()[:15], 16)


async def _resolve_generic_breadth_universe(
    definition: BreadthDefinitionRequest, db: AsyncSession
) -> tuple[list[BreadthMember], list[int], list[AnalysisWarning], dict[str, object], object]:
    """Resolve one breadth universe without provider fan-out."""

    universe_kind = definition.universe.kind
    members: list[BreadthMember] = []
    member_ids: list[int] = []
    universe_warnings: list[AnalysisWarning] = []
    universe_provenance: dict[str, object]
    membership_version_payload: object

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
            detail={"code": "condition_required", "message": "A condition or condition asset is required."},
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
    version: CodeVersion, parameters: Mapping[str, object]
) -> dict[str, object]:
    asset = version.asset
    return {
        "kind": "python",
        "code_version_id": version.id,
        "asset_key": asset.stable_key if asset is not None else None,
        "asset_version": version.version_number,
        "output_contract": version.output_contract,
        "sdk_version": version.sdk_version,
        "runtime_version": version.runtime_version,
        "lookback": version.lookback,
        "parameters": dict(parameters),
    }


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
    return BreadthPythonResultPointOut(
        timestamp=timestamp,
        requested_count=requested,
        eligible_count=eligible,
        pass_count=passed,
        excluded_count=max(requested - eligible, 0),
        percentage=passed / eligible if eligible else None,
        coverage=eligible / requested if requested else 0,
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


def _python_breadth_run_out(run: ResearchRun) -> BreadthPythonRunOut:
    config = run.run_config if isinstance(run.run_config, dict) else {}
    return BreadthPythonRunOut(
        run_id=run.id,
        code_version_id=run.code_version_id,
        status=run.status,
        execution_mode=config.get("execution_mode", "breadth_current"),
        definition_hash=str(config.get("definition_hash") or ""),
        universe=config.get("universe", {}),
        condition=config.get("condition", {}),
        dataset_manifest=run.dataset_manifest if isinstance(run.dataset_manifest, dict) else {},
        progress=run.progress if isinstance(getattr(run, "progress", {}), dict) else {},
        diagnostics=run.diagnostics if isinstance(run.diagnostics, list) else [],
    )


@router.post("/breadth/python", response_model=BreadthPythonRunOut, status_code=202)
async def queue_python_breadth(
    body: BreadthPythonRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Queue an arbitrary Boolean breadth predicate in the isolated runner."""
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
    if version is None or version.output_contract != "boolean":
        raise HTTPException(
            422,
            detail={
                "code": "python_breadth_condition_unavailable",
                "message": "The selected user-owned code version must be an active Boolean condition.",
            },
        )
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
    members, member_ids, universe_warnings, universe_provenance, membership_payload = (
        await _resolve_generic_breadth_universe(placeholder, db)
    )
    membership_version = _generic_membership_version(membership_payload)
    parameters = dict(version.default_parameters or {})
    parameters.update(body.parameters)
    parameter_errors = validate_parameter_values(version.parameter_schema, parameters)
    if parameter_errors:
        raise HTTPException(
            422,
            detail={"code": "parameter_validation_failed", "errors": parameter_errors},
        )
    condition_metadata = _python_breadth_condition_metadata(version, parameters)
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
            if item.name == ("breadth_history" if execution_mode == "breadth_history" else "batch_cells")
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
    manifest_warnings = _manifest_exclusion_warnings(
        run.dataset_manifest if isinstance(run.dataset_manifest, dict) else {}
    )
    if manifest_warnings:
        if current is not None:
            current = current.model_copy(
                update={
                    "excluded_count": current.excluded_count + len(manifest_warnings),
                    "exclusions": [*current.exclusions, *manifest_warnings],
                    "coverage": current.eligible_count / requested_count
                    if requested_count
                    else 0,
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
        definition_hash=str(config.get("definition_hash") or ""),
        universe=config.get("universe", {}),
        condition=config.get("condition", {}),
        dataset_manifest=run.dataset_manifest if isinstance(run.dataset_manifest, dict) else {},
        current=current,
        points=points,
        progress=run.progress if isinstance(getattr(run, "progress", {}), dict) else {},
        diagnostics=run.diagnostics if isinstance(run.diagnostics, list) else [],
    )


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
    benchmark_bars = None
    if _generic_condition_requires_benchmark(condition_definition.model_dump()):
        if not definition.benchmark:
            raise HTTPException(422, detail={"code": "benchmark_required"})
        benchmark = await _instrument(db, definition.benchmark)
        benchmark_bars = _truncate_bars_at(
            await _bars_by_instrument(db, [benchmark.id], timeframe, definition.adjusted),
            definition.as_of,
        ).get(benchmark.id, [])

    condition = {
        "kind": condition_definition.kind,
        "params": condition_definition.params,
        **condition_metadata,
    }
    results, aggregate = evaluate_breadth(
        members, bars_by_id, condition, benchmark_bars=benchmark_bars
    )
    warnings = list(universe_warnings)
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
            )
        )
    membership_version = _generic_membership_version(membership_version_payload)
    definition_payload = definition.model_dump(mode="json")
    definition_payload["condition"] = condition_definition.model_dump(mode="json")
    definition_payload["condition_asset"] = condition_metadata
    if definition.benchmark:
        definition_payload["benchmark"] = definition.benchmark.upper()
    freshness, freshness_detail = await _batch_freshness(
        db, member_ids, timeframe, definition.adjusted
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
    ) = await _resolve_generic_breadth_universe(definition, db)
    bars_by_id = await _bars_by_instrument(db, member_ids, timeframe, definition.adjusted)
    bars_by_id = _truncate_bars_at(bars_by_id, definition.as_of)
    benchmark_bars = None
    if _generic_condition_requires_benchmark(condition_definition.model_dump()):
        if not definition.benchmark:
            raise HTTPException(422, detail={"code": "benchmark_required"})
        benchmark = await _instrument(db, definition.benchmark)
        benchmark_bars = _truncate_bars_at(
            await _bars_by_instrument(db, [benchmark.id], timeframe, definition.adjusted),
            definition.as_of,
        ).get(benchmark.id, [])
    condition = {
        "kind": condition_definition.kind,
        "params": condition_definition.params,
        **condition_metadata,
    }
    raw_points = evaluate_breadth_history(
        members,
        bars_by_id,
        condition,
        limit=definition.limit,
        benchmark_bars=benchmark_bars,
    )
    warnings = list(universe_warnings)
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
        db, member_ids, timeframe, definition.adjusted
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
        exclusions=warnings,
    )
