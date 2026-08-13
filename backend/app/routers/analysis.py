"""Canonical local-database analysis endpoints for workstation tools."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.etf_holdings import ETFHoldingsSnapshot, ETFProfile
from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_observation import DatasetStatus, InstrumentDatasetState
from app.models.screener import ScreenerDefinition, ScreenerResult
from app.models.user import User
from app.models.workstation import MarketGroup, MarketGroupMember
from app.routers.market_groups import (
    _holding_exclusion_code,
    etf_industry_composition,
    etf_industry_constituents,
    etf_industry_proxies,
    holdings_snapshot_source_filter,
)
from app.schemas.analysis import (
    AnalysisCell,
    AnalysisPoint,
    AnalysisWarning,
    BreadthHistoryOut,
    BreadthHistoryPoint,
    BreadthOut,
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
from app.services.indicators import OHLCVSeries, get_latest_value

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
        warning = AnalysisWarning(code="no_bars", message="No aligned constituent bars are available.", instrument_id=instrument_id)
        return {period: AnalysisCell(value=None, observation_time=None, warning=warning) for period in _PERIODS}
    latest_timestamp, latest_value = values[-1]
    current_year = [item for item in values if item[0].year == latest_timestamp.year]
    cells: dict[str, AnalysisCell] = {}
    for period, offset in _PERIODS.items():
        base: float | None
        if period == "YTD":
            base = current_year[0][1] if len(current_year) >= 2 else None
            code = "insufficient_ytd_history"
            message = "YTD requires at least two aligned constituent observations in the current year."
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
            cells[period] = AnalysisCell(value=latest_value / base - 1, observation_time=latest_timestamp)
    return cells


def _technical_cells_for_series(
    values: list[tuple[datetime, float]], instrument_id: int | None
) -> dict[str, AnalysisCell]:
    """Return the same transparent technical fields used by group rankings."""

    if not values:
        warning = AnalysisWarning(code="no_bars", message="No aligned constituent bars are available.", instrument_id=instrument_id)
        return {key: AnalysisCell(value=None, observation_time=None, warning=warning) for key in ("above_ma20", "above_ma50", "above_ma200", "rsi14", "position_52w")}
    latest_timestamp, latest_value = values[-1]
    closes = [value for _, value in values]
    technical: dict[str, AnalysisCell] = {}
    for period in (20, 50, 200):
        key = f"above_ma{period}"
        warning = None if len(closes) >= period else AnalysisWarning(
            code="insufficient_history",
            message=f"Price versus SMA({period}) requires {period} aligned constituent observations.",
            instrument_id=instrument_id,
        )
        technical[key] = AnalysisCell(
            value=(1.0 if latest_value > sum(closes[-period:]) / period else 0.0) if warning is None else None,
            observation_time=latest_timestamp,
            warning=warning,
        )
    if len(closes) >= 15:
        changes = [closes[index] - closes[index - 1] for index in range(len(closes) - 13, len(closes))]
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
            warning=AnalysisWarning(code="insufficient_history", message="RSI(14) requires 15 aligned constituent observations.", instrument_id=instrument_id),
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
            warning=AnalysisWarning(code="insufficient_history", message="52-week position requires 252 aligned constituent observations.", instrument_id=instrument_id),
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

    series = [_normalised_bar_series(bars_by_id.get(instrument_id, [])) for instrument_id in instrument_ids]
    series = [item for item in series if item]
    if not series:
        return []
    timestamps = sorted(set.intersection(*(set(item) for item in series)))
    return [(timestamp, _mean([item[timestamp] for item in series])) for timestamp in timestamps]


def _ratio_cell(
    values: list[tuple[datetime, float]], reference: dict[datetime, float], instrument_id: int | None
) -> AnalysisCell:
    if not values:
        return AnalysisCell(
            value=None,
            observation_time=None,
            warning=AnalysisWarning(code="no_bars", message="No aligned industry observations are available.", instrument_id=instrument_id),
        )
    timestamp, value = values[-1]
    denominator = reference.get(timestamp)
    if denominator in (None, 0):
        return AnalysisCell(
            value=None,
            observation_time=timestamp,
            warning=AnalysisWarning(code="unaligned_benchmark", message="No aligned benchmark observation is available.", instrument_id=instrument_id),
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
        raise HTTPException(422, detail={"code": "invalid_timeframe", "timeframe": body.timeframe}) from exc
    symbols = list(dict.fromkeys(symbol.upper().strip() for symbol in body.symbols if symbol.strip()))
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
            warning = AnalysisWarning(code="instrument_not_found", message="No canonical instrument exists.", instrument_id=None)
            values[symbol] = {"value": None, "observation_time": None, "warning": warning.model_dump()}
            exclusions.append(warning)
            continue
        bars = bars_by_id.get(instrument.id, [])[-500:]
        if not bars:
            warning = AnalysisWarning(code="no_bars", message="No canonical bars are available.", instrument_id=instrument.id)
            values[symbol] = {"value": None, "observation_time": None, "warning": warning.model_dump()}
            exclusions.append(warning)
            continue
        try:
            value = get_latest_value(body.indicator, OHLCVSeries.from_orm_bars(bars), body.params, str(body.params.get("output")) if body.params.get("output") else None)
        except (KeyError, IndexError) as exc:
            warning = AnalysisWarning(code="unknown_indicator", message=str(exc), instrument_id=instrument.id)
            values[symbol] = {"value": None, "observation_time": bars[-1].ts, "warning": warning.model_dump()}
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


def _group_membership_version(
    group: MarketGroup, members: list[MarketGroupMember]
) -> int:
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
                instrument_id=value.get("instrument_id") if isinstance(value.get("instrument_id"), int) else None,
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
                cells[period] = _cell(
                    float(latest.close / current_year_bars[0].close - 1), latest
                )
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
    freshness, freshness_detail = await _batch_freshness(
        db, [instrument.id], timeframe, adjusted
    )
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
                transition=f"{previous_state}->{state}" if previous_state and previous_state != state else None,
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
    composition = await etf_industry_composition(symbol=etf.symbol, as_of=as_of, _=current_user, db=db)
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
            exclusions.append(warning.model_copy(update={"message": f"{industry.industry}: {warning.message}"}))
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
        as_of=max((row.last.observation_time for row in rows if row.last.observation_time), default=None),
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
    holdings = [
        row for row in disclosed_rows if _holding_exclusion_code(row) is None
    ]
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
    market_bars = {bar.ts: bar for bar in bars_by_id.get(market_instrument.id, [])} if market_instrument else {}
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
        as_of=as_of or max(
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
    calendar_years = list(
        range(latest_year - _CALENDAR_YEAR_LOOKBACK + 1, latest_year + 1)
    )
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
    freshness, freshness_detail = await _batch_freshness(
        db, instrument_ids, timeframe, adjusted
    )
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
        await _bars_by_instrument(db, [member.instrument_id for member in members], timeframe, adjusted),
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
            previous = [float(bar.close) for bar in bars[-(new_high_lookback + 1):-1]]
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
            **{
                f"ma{period}": eligible[period] / max(len(members), 1)
                for period in eligible
            },
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
            if distance_eligible[period] else None
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
        await _bars_by_instrument(db, [member.instrument_id for member in members], timeframe, adjusted),
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
