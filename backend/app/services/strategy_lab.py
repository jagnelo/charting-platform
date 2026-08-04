from __future__ import annotations

import copy
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.basket import Basket, BasketMember, BasketSnapshot
from app.models.etf_holdings import ETFHoldingsSnapshot, ETFProfile
from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.radar import (
    RadarDetection,
    RadarSetupType,
    RadarState,
)
from app.models.research import CodeVersion, ResearchRun
from app.models.screener import ScreenerDefinition, ScreenerResult
from app.models.strategy import (
    StrategyDefinition,
    StrategyEngineType,
    StrategyRun,
    StrategyRunStatus,
    StrategyVersion,
)
from app.models.watchlist import Watchlist, WatchlistItem
from app.services.research_jobs import collect_research_result, enqueue_research_run
from app.services.strategy_lab_nautilus import (
    NautilusOpenPosition,
    NautilusTrade,
    run_single_instrument_nautilus_backtest,
)

LONG_BIASED_RADAR_SETUPS = {
    RadarSetupType.APPROACHING_SUPPORT,
    RadarSetupType.BREAKOUT,
    RadarSetupType.BREAKOUT_RETEST,
    RadarSetupType.RECLAIM,
    RadarSetupType.COMPRESSION_SUPPORT,
    RadarSetupType.FAILED_BREAKDOWN_RECOVERY,
}
SHORT_BIASED_RADAR_SETUPS = {
    RadarSetupType.APPROACHING_RESISTANCE,
    RadarSetupType.BREAKDOWN,
    RadarSetupType.BREAKDOWN_RETEST,
    RadarSetupType.REJECTION,
    RadarSetupType.COMPRESSION_RESISTANCE,
    RadarSetupType.FAILED_RECLAIM,
}


@dataclass(frozen=True)
class StrategyExecutionEngine:
    public_name: str
    capability_flags: tuple[str, ...]


@dataclass(frozen=True)
class DynamicUniverseSnapshot:
    id: int
    composition_date: date
    known_at: datetime | None
    member_ids: frozenset[int]
    source_type: str


@dataclass(frozen=True)
class DynamicETFUniverse:
    profile_id: int | None
    basket_id: int | None
    kind: str
    instrument_ids: tuple[int, ...]
    snapshots: tuple[DynamicUniverseSnapshot, ...]


ENGINE_REGISTRY: dict[str, StrategyExecutionEngine] = {
    StrategyEngineType.NAUTILUS.value: StrategyExecutionEngine(
        public_name="platform_simulation",
        capability_flags=(
            "backtest",
            "walk_forward",
            "paper_forward",
            "parameter_sweep",
            "platform_signal_replay",
            "condition_trees",
        ),
    ),
    StrategyEngineType.PLATFORM.value: StrategyExecutionEngine(
        public_name="research_snapshot",
        capability_flags=("foundation_snapshot",),
    ),
}


def _resolve_engine_for_version(
    strategy: StrategyDefinition,
    version: StrategyVersion,
) -> StrategyExecutionEngine:
    if strategy.source_type == "radar":
        return ENGINE_REGISTRY[StrategyEngineType.NAUTILUS.value]
    return (
        ENGINE_REGISTRY.get(version.engine_type)
        or ENGINE_REGISTRY[StrategyEngineType.NAUTILUS.value]
    )


async def _queue_python_signal_research(
    db: AsyncSession,
    *,
    strategy: StrategyDefinition,
    version: StrategyVersion,
    run: StrategyRun,
) -> None:
    """Queue a promoted unified-Python signal in the isolated research runner.

    Strategy Lab never evaluates user source in FastAPI. Promoted Study Lab signals
    retain an immutable ``code_version_id`` in their version snapshot and reuse the
    canonical research materializer/runner protocol.
    """
    snapshot = version.definition_snapshot if isinstance(version.definition_snapshot, dict) else {}
    code_version_id = snapshot.get("code_version_id")
    if not isinstance(code_version_id, int):
        raise ValueError("Python Strategy Lab signals must reference an immutable code version")
    code_version = (await db.execute(select(CodeVersion).where(CodeVersion.id == code_version_id))).scalar_one_or_none()
    if code_version is None or code_version.output_contract not in {"boolean", "events"}:
        raise ValueError("Python Strategy Lab signal code version is unavailable or unsupported")

    # Keep dataset resolution on the same canonical path as Study Lab. The import is
    # local to avoid making the service/router import graph eager or circular.
    from app.routers.research import _materialize_declared_dataset

    run_config: dict[str, object] = {
        **(version.universe_config or {}),
        **(run.universe_config or {}),
        **(version.benchmark_config or {}),
        **(run.benchmark_config or {}),
        "parameters": {**(code_version.default_parameters or {}), **(version.default_parameters or {}), **(run.parameter_values or {})},
    }
    if run.timeframe:
        run_config["timeframe"] = run.timeframe
    if run.date_from:
        run_config["start_date"] = run.date_from.isoformat()
    if run.date_to:
        run_config["end_date"] = run.date_to.isoformat()
    manifest = await _materialize_declared_dataset(db, {}, run_config)
    research_run = ResearchRun(
        user_id=strategy.user_id,
        code_version_id=code_version.id,
        run_config={**run_config, "strategy_run_id": run.id},
        dataset_manifest=manifest,
    )
    research_run.code_version = code_version
    db.add(research_run)
    await db.flush()
    enqueue_research_run(research_run)

    now = datetime.now(UTC)
    run.status = StrategyRunStatus.QUEUED.value
    run.started_at = now
    run.completed_at = None
    run.engine_run_ref = f"research:{research_run.id}"
    run.result_summary = {
        "result_kind": "python_signal_research",
        "research_run_id": research_run.id,
        "output_contract": code_version.output_contract,
        "status": "queued",
        "strategy_name": strategy.name,
    }
    run.artifact_manifest = {
        "result_kind": "python_signal_research",
        "research_run_id": research_run.id,
        "output_contract": code_version.output_contract,
        "supports_execution_stats": False,
    }


async def _refresh_python_signal_research(db: AsyncSession, run: StrategyRun) -> bool:
    summary = run.result_summary if isinstance(run.result_summary, dict) else {}
    research_run_id = summary.get("research_run_id")
    if summary.get("result_kind") != "python_signal_research" or not isinstance(research_run_id, int):
        return False
    if run.status in {StrategyRunStatus.COMPLETED.value, StrategyRunStatus.FAILED.value, StrategyRunStatus.CANCELED.value}:
        return True
    research_run = (await db.execute(select(ResearchRun).where(ResearchRun.id == research_run_id))).scalar_one_or_none()
    if research_run is None:
        run.status = StrategyRunStatus.FAILED.value
        run.completed_at = datetime.now(UTC)
        run.error_log = "Isolated Python signal run is unavailable"
        return True
    collected = collect_research_result(research_run)
    if not collected and research_run.status not in {"completed", "failed", "canceled"}:
        return False
    run.status = research_run.status
    run.completed_at = datetime.now(UTC)
    run.warning_log = list(research_run.warnings or []) + list(research_run.diagnostics or [])
    if research_run.status == "failed":
        run.error_log = next((item.get("message") for item in research_run.diagnostics if isinstance(item, dict) and item.get("message")), "Python signal research failed")
    run.result_summary = {
        **summary,
        "status": research_run.status,
        "diagnostics": research_run.diagnostics or [],
        "warnings": research_run.warnings or [],
        "reproducibility_hash": research_run.reproducibility_hash,
        "artifact_names": [artifact.name for artifact in research_run.artifacts],
    }
    run.artifact_manifest = {
        **(run.artifact_manifest or {}),
        "status": research_run.status,
        "artifact_names": [artifact.name for artifact in research_run.artifacts],
        "reproducibility_hash": research_run.reproducibility_hash,
    }
    return True


async def execute_strategy_run(
    db: AsyncSession,
    *,
    strategy: StrategyDefinition,
    version: StrategyVersion,
    run: StrategyRun,
) -> StrategyRun:
    run.status = StrategyRunStatus.RUNNING.value
    run.started_at = datetime.now(UTC)
    await db.flush()
    engine = _resolve_engine_for_version(strategy, version)

    try:
        if strategy.definition_type == "python":
            await _queue_python_signal_research(db, strategy=strategy, version=version, run=run)
            await db.flush()
            return run
        if strategy.source_type == "radar" or strategy.definition_type == "signal_source":
            run.result_summary = await _run_radar_signal_research(
                db, strategy=strategy, version=version, run=run
            )
        elif strategy.definition_type == "rules":
            run.result_summary = await _run_rules_backtest(
                db, strategy=strategy, version=version, run=run
            )
        else:
            run.result_summary = await _run_platform_foundation(
                db, strategy=strategy, version=version, run=run
            )
        run.status = StrategyRunStatus.COMPLETED.value
        run.completed_at = datetime.now(UTC)
        run.engine_run_ref = f"{run.engine_type}:{run.id}"
        result_kind = str(run.result_summary.get("result_kind") or "foundation_research_snapshot")
        run.artifact_manifest = {
            "result_kind": result_kind,
            "supports_execution_stats": result_kind.startswith("rules_")
            or result_kind == "radar_replay",
            "capabilities": list(engine.capability_flags),
            "engine_class": engine.public_name,
        }
    except Exception as exc:
        run.status = StrategyRunStatus.FAILED.value
        run.completed_at = datetime.now(UTC)
        run.error_log = str(exc)
        raise

    await db.flush()
    return run


def _has_explicit_universe(universe_config: dict[str, Any] | None) -> bool:
    config = universe_config or {}
    return any(
        config.get(key) not in (None, [], "")
        for key in (
            "instrument_ids",
            "symbols",
            "basket_id",
            "watchlist_id",
            "screener_id",
            "etf_holdings",
        )
    )


def _parse_etf_snapshot_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _coerce_timeframe(timeframe_value: str | None, warnings: list[str]) -> Timeframe:
    raw_value = timeframe_value or Timeframe.D1.value
    try:
        return Timeframe(str(raw_value))
    except ValueError:
        warnings.append(f"Unknown timeframe '{raw_value}' requested; defaulted to D1.")
        return Timeframe.D1


def _coerce_commission_settings(execution_assumptions: dict[str, Any]) -> tuple[str, float]:
    raw_model = str(execution_assumptions.get("commission_model") or "fixed_round_trip")
    commission_model = (
        raw_model
        if raw_model in {"fixed_round_trip", "fixed_per_order", "percent_of_notional"}
        else "fixed_round_trip"
    )
    commission_value = float(
        execution_assumptions.get("commission_value", execution_assumptions.get("commission_per_trade", 0))
        or 0
    )
    return commission_model, max(commission_value, 0.0)


def _coerce_float(value: Any, default: float) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int(value: Any, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _apply_parameter_values(definition: dict[str, Any], parameter_values: dict[str, Any]) -> dict[str, Any]:
    if not parameter_values:
        return definition
    updated = copy.deepcopy(definition)
    for raw_key, value in parameter_values.items():
        key = str(raw_key or "").strip()
        if not key:
            continue
        target = updated
        parts = key.split(".")
        for part in parts[:-1]:
            existing = target.get(part)
            if not isinstance(existing, dict):
                existing = {}
                target[part] = existing
            target = existing
        target[parts[-1]] = value
    return updated


def _requested_range_fits(
    *,
    date_from: datetime | None,
    date_to: datetime | None,
    available_from: datetime | None,
    available_to: datetime | None,
) -> bool | None:
    if available_from is None or available_to is None:
        return None
    if date_from is None and date_to is None:
        return None
    starts_ok = date_from is None or available_from <= date_from
    ends_ok = date_to is None or available_to >= date_to
    return starts_ok and ends_ok


def _instrument_requested_status(
    *,
    available_from: datetime | None,
    available_to: datetime | None,
    requested_bars: int,
    date_from: datetime | None,
    date_to: datetime | None,
) -> str:
    if available_from is None or available_to is None:
        return "missing"
    if requested_bars <= 0:
        return "none"
    starts_ok = date_from is None or available_from <= date_from
    ends_ok = date_to is None or available_to >= date_to
    return "full" if starts_ok and ends_ok else "partial"


def _instrument_coverage_note(
    instrument: Instrument,
    *,
    available_from: datetime | None,
    available_to: datetime | None,
    requested_bars: int,
    date_from: datetime | None,
    date_to: datetime | None,
) -> str | None:
    if available_from is None or available_to is None:
        return "No local OHLCV history is stored for this timeframe."

    notes: list[str] = []
    ipo_date = getattr(instrument.equity_detail, "ipo_date", None)
    if date_from is not None and available_from > date_from:
        if ipo_date is not None and available_from.date() >= ipo_date >= date_from.date():
            notes.append(f"Coverage begins after IPO ({ipo_date.isoformat()}).")
        else:
            notes.append("Coverage begins after the requested start; earlier local history may be missing.")
    if date_to is not None and available_to < date_to:
        notes.append("Coverage ends before the requested end.")
    if requested_bars > 0 and requested_bars < 3:
        notes.append(f"Only {requested_bars} bars fall inside the requested window.")
    if not notes and ipo_date is not None and date_from is not None and ipo_date > date_from.date():
        notes.append(f"Instrument IPO date is {ipo_date.isoformat()}.")
    return " ".join(notes) if notes else None


async def _build_universe_coverage_summary(
    db: AsyncSession,
    *,
    instrument_rows: list[Instrument],
    timeframe: Timeframe,
    date_from: datetime | None,
    date_to: datetime | None,
    preview_mode: str = "resolved",
    preview_note: str | None = None,
) -> dict[str, Any]:
    if not instrument_rows:
        return {
            "preview_mode": preview_mode,
            "preview_note": preview_note,
            "instrument_count": 0,
            "instruments_with_data": 0,
            "instruments_with_requested_data": 0,
            "instruments_with_full_requested_coverage": 0,
            "instruments_with_partial_requested_coverage": 0,
            "instruments_without_requested_coverage": 0,
            "total_bars": 0,
            "requested_first_bar_at": None,
            "requested_last_bar_at": None,
            "any_coverage_from": None,
            "any_coverage_to": None,
            "collective_coverage_from": None,
            "collective_coverage_to": None,
            "requested_fits_collective_range": None,
            "resolved_symbols": [],
            "limiting_instruments": [],
            "instruments": [],
        }

    instrument_ids = [row.id for row in instrument_rows]
    full_stmt = (
        select(
            OHLCVBar.instrument_id,
            func.count(OHLCVBar.id),
            func.min(OHLCVBar.ts),
            func.max(OHLCVBar.ts),
        )
        .where(OHLCVBar.timeframe == timeframe, OHLCVBar.instrument_id.in_(instrument_ids))
        .group_by(OHLCVBar.instrument_id)
    )
    full_rows = (await db.execute(full_stmt)).all()
    full_map = {
        int(row[0]): {
            "total_bars": int(row[1]),
            "available_from": row[2],
            "available_to": row[3],
        }
        for row in full_rows
    }

    requested_stmt = (
        select(
            OHLCVBar.instrument_id,
            func.count(OHLCVBar.id),
            func.min(OHLCVBar.ts),
            func.max(OHLCVBar.ts),
        )
        .where(OHLCVBar.timeframe == timeframe, OHLCVBar.instrument_id.in_(instrument_ids))
    )
    if date_from is not None:
        requested_stmt = requested_stmt.where(OHLCVBar.ts >= date_from)
    if date_to is not None:
        requested_stmt = requested_stmt.where(OHLCVBar.ts <= date_to)
    requested_stmt = requested_stmt.group_by(OHLCVBar.instrument_id)
    requested_rows = (await db.execute(requested_stmt)).all()
    requested_map = {
        int(row[0]): {
            "requested_bars": int(row[1]),
            "requested_first_bar_at": row[2],
            "requested_last_bar_at": row[3],
        }
        for row in requested_rows
    }

    instrument_summaries: list[dict[str, Any]] = []
    available_starts: list[datetime] = []
    available_ends: list[datetime] = []
    requested_starts: list[datetime] = []
    requested_ends: list[datetime] = []

    for instrument in sorted(instrument_rows, key=lambda row: row.symbol):
        full = full_map.get(instrument.id, {})
        requested = requested_map.get(instrument.id, {})
        available_from = full.get("available_from")
        available_to = full.get("available_to")
        requested_first_bar_at = requested.get("requested_first_bar_at")
        requested_last_bar_at = requested.get("requested_last_bar_at")
        total_bars = int(full.get("total_bars") or 0)
        requested_bars = int(requested.get("requested_bars") or 0)
        requested_status = _instrument_requested_status(
            available_from=available_from,
            available_to=available_to,
            requested_bars=requested_bars,
            date_from=date_from,
            date_to=date_to,
        )
        note = _instrument_coverage_note(
            instrument,
            available_from=available_from,
            available_to=available_to,
            requested_bars=requested_bars,
            date_from=date_from,
            date_to=date_to,
        )
        if available_from is not None:
            available_starts.append(available_from)
        if available_to is not None:
            available_ends.append(available_to)
        if requested_first_bar_at is not None:
            requested_starts.append(requested_first_bar_at)
        if requested_last_bar_at is not None:
            requested_ends.append(requested_last_bar_at)
        instrument_summaries.append(
            {
                "instrument_id": instrument.id,
                "symbol": instrument.symbol,
                "available_from": available_from.isoformat() if available_from else None,
                "available_to": available_to.isoformat() if available_to else None,
                "requested_first_bar_at": requested_first_bar_at.isoformat()
                if requested_first_bar_at
                else None,
                "requested_last_bar_at": requested_last_bar_at.isoformat()
                if requested_last_bar_at
                else None,
                "total_bars": total_bars,
                "requested_bars": requested_bars,
                "requested_status": requested_status,
                "note": note,
                "ipo_date": instrument.equity_detail.ipo_date.isoformat()
                if instrument.equity_detail is not None and instrument.equity_detail.ipo_date is not None
                else None,
            }
        )

    instruments_with_data = sum(1 for row in instrument_summaries if row["total_bars"] > 0)
    instruments_with_requested_data = sum(1 for row in instrument_summaries if row["requested_bars"] > 0)
    instruments_with_full_requested_coverage = sum(
        1 for row in instrument_summaries if row["requested_status"] == "full"
    )
    instruments_with_partial_requested_coverage = sum(
        1 for row in instrument_summaries if row["requested_status"] == "partial"
    )
    instruments_without_requested_coverage = sum(
        1 for row in instrument_summaries if row["requested_status"] in {"none", "missing"}
    )

    any_coverage_from = min(available_starts) if available_starts else None
    any_coverage_to = max(available_ends) if available_ends else None
    collective_coverage_from = max(available_starts) if available_starts else None
    collective_coverage_to = min(available_ends) if available_ends else None
    if (
        collective_coverage_from is not None
        and collective_coverage_to is not None
        and collective_coverage_from > collective_coverage_to
    ):
        collective_coverage_from = None
        collective_coverage_to = None

    limiting_instruments = [
        row
        for row in instrument_summaries
        if row["requested_status"] != "full" or row["note"] is not None
    ]
    limiting_instruments.sort(
        key=lambda row: (
            {"missing": 0, "none": 1, "partial": 2, "full": 3}.get(str(row["requested_status"]), 4),
            row["symbol"],
        )
    )

    return {
        "preview_mode": preview_mode,
        "preview_note": preview_note,
        "instrument_count": len(instrument_summaries),
        "instruments_with_data": instruments_with_data,
        "instruments_with_requested_data": instruments_with_requested_data,
        "instruments_with_full_requested_coverage": instruments_with_full_requested_coverage,
        "instruments_with_partial_requested_coverage": instruments_with_partial_requested_coverage,
        "instruments_without_requested_coverage": instruments_without_requested_coverage,
        "total_bars": sum(int(row["requested_bars"]) for row in instrument_summaries),
        "requested_first_bar_at": min(requested_starts).isoformat() if requested_starts else None,
        "requested_last_bar_at": max(requested_ends).isoformat() if requested_ends else None,
        "any_coverage_from": any_coverage_from.isoformat() if any_coverage_from else None,
        "any_coverage_to": any_coverage_to.isoformat() if any_coverage_to else None,
        "collective_coverage_from": collective_coverage_from.isoformat()
        if collective_coverage_from
        else None,
        "collective_coverage_to": collective_coverage_to.isoformat()
        if collective_coverage_to
        else None,
        "requested_fits_collective_range": _requested_range_fits(
            date_from=date_from,
            date_to=date_to,
            available_from=collective_coverage_from,
            available_to=collective_coverage_to,
        ),
        "resolved_symbols": [row.symbol for row in instrument_rows],
        "limiting_instruments": limiting_instruments[:10],
        "instruments": instrument_summaries,
    }


async def _build_benchmark_coverage_summary(
    db: AsyncSession,
    *,
    benchmark_symbol: str,
    timeframe: Timeframe,
    date_from: datetime | None,
    date_to: datetime | None,
) -> dict[str, Any]:
    if not benchmark_symbol:
        return {
            "symbol": None,
            "preview_note": "No benchmark configured.",
            "requested_status": "unconfigured",
            "available_from": None,
            "available_to": None,
            "requested_first_bar_at": None,
            "requested_last_bar_at": None,
            "total_bars": 0,
            "requested_bars": 0,
            "requested_fits_range": None,
        }

    warnings: list[str] = []
    instruments = await _resolve_universe_instruments(db, {"symbols": [benchmark_symbol]}, warnings)
    if not instruments:
        return {
            "symbol": benchmark_symbol,
            "preview_note": warnings[0] if warnings else "Benchmark could not be resolved.",
            "requested_status": "missing",
            "available_from": None,
            "available_to": None,
            "requested_first_bar_at": None,
            "requested_last_bar_at": None,
            "total_bars": 0,
            "requested_bars": 0,
            "requested_fits_range": None,
        }

    summary = await _build_universe_coverage_summary(
        db,
        instrument_rows=[instruments[0]],
        timeframe=timeframe,
        date_from=date_from,
        date_to=date_to,
        preview_mode="resolved",
    )
    row = summary["instruments"][0] if summary["instruments"] else {}
    return {
        "symbol": benchmark_symbol,
        "preview_note": row.get("note"),
        "requested_status": row.get("requested_status", "missing"),
        "available_from": row.get("available_from"),
        "available_to": row.get("available_to"),
        "requested_first_bar_at": row.get("requested_first_bar_at"),
        "requested_last_bar_at": row.get("requested_last_bar_at"),
        "total_bars": int(row.get("total_bars") or 0),
        "requested_bars": int(row.get("requested_bars") or 0),
        "requested_fits_range": summary.get("requested_fits_collective_range"),
    }


async def preview_strategy_coverage(
    db: AsyncSession,
    *,
    source_type: str,
    timeframe_value: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    universe_config: dict[str, Any] | None,
    benchmark_config: dict[str, Any] | None,
) -> dict[str, Any]:
    warnings: list[str] = []
    timeframe = _coerce_timeframe(timeframe_value, warnings)
    effective_universe = dict(universe_config or {})
    benchmark_symbol = str((benchmark_config or {}).get("symbol") or "").upper()
    explicit_universe = _has_explicit_universe(effective_universe)

    preview_mode = "resolved"
    preview_note: str | None = None
    instrument_rows: list[Instrument] = []
    if source_type == "radar" and not explicit_universe:
        preview_mode = "signal_derived"
        preview_note = (
            "Radar outputs are signal-derived, so universe coverage cannot be previewed before a run unless you narrow it to explicit symbols, a watchlist, or a screener snapshot."
        )
    elif explicit_universe:
        if _is_dynamic_etf_holdings_universe(effective_universe):
            instrument_rows, _dynamic_universe = await _resolve_dynamic_etf_universe(
                db,
                effective_universe,
                date_to=date_to,
                warnings=warnings,
            )
        else:
            instrument_rows = await _resolve_universe_instruments(db, effective_universe, warnings)
        if not instrument_rows:
            preview_mode = "empty"
            preview_note = warnings[0] if warnings else "No instruments resolved from the current universe."
    else:
        preview_mode = "empty"
        preview_note = "Choose symbols, a watchlist, or a screener result to preview universe coverage."

    universe = await _build_universe_coverage_summary(
        db,
        instrument_rows=instrument_rows,
        timeframe=timeframe,
        date_from=date_from,
        date_to=date_to,
        preview_mode=preview_mode,
        preview_note=preview_note,
    )
    benchmark = await _build_benchmark_coverage_summary(
        db,
        benchmark_symbol=benchmark_symbol,
        timeframe=timeframe,
        date_from=date_from,
        date_to=date_to,
    )
    return {
        "timeframe": timeframe.value,
        "requested_date_from": date_from.isoformat() if date_from else None,
        "requested_date_to": date_to.isoformat() if date_to else None,
        "universe": universe,
        "benchmark": benchmark,
        "warnings": warnings,
    }


async def _run_platform_foundation(
    db: AsyncSession,
    *,
    strategy: StrategyDefinition,
    version: StrategyVersion,
    run: StrategyRun,
) -> dict:
    effective_universe = dict(version.universe_config or {})
    effective_universe.update(run.universe_config or {})

    warnings: list[str] = []
    dynamic_universe: DynamicETFUniverse | None = None
    if _is_dynamic_etf_holdings_universe(effective_universe):
        instrument_rows, dynamic_universe = await _resolve_dynamic_etf_universe(
            db,
            effective_universe,
            date_to=run.date_to,
            warnings=warnings,
        )
    else:
        instrument_rows = await _resolve_universe_instruments(db, effective_universe, warnings)
    instrument_ids = [row.id for row in instrument_rows]
    symbols = [row.symbol for row in instrument_rows]

    timeframe_value = (
        run.timeframe or version.definition_snapshot.get("timeframe") or Timeframe.D1.value
    )
    timeframe = _coerce_timeframe(str(timeframe_value), warnings)
    coverage = await _build_universe_coverage_summary(
        db,
        instrument_rows=instrument_rows,
        timeframe=timeframe,
        date_from=run.date_from,
        date_to=run.date_to,
        preview_mode="resolved" if instrument_ids else "empty",
        preview_note=None if instrument_ids else "No instruments resolved from the current universe config.",
    )

    if not instrument_ids:
        warnings.append("No instruments resolved from the current universe config.")
    if int(coverage.get("total_bars") or 0) == 0:
        warnings.append("No OHLCV coverage was found for the requested timeframe/date range.")
    if coverage.get("requested_fits_collective_range") is False:
        warnings.append(
            "The requested date range exceeds the shared local coverage window of the selected universe."
        )
    if not (version.definition_snapshot or run.parameter_values):
        warnings.append(
            "No concrete strategy logic was supplied yet; this run is a research foundation snapshot."
        )

    run.warning_log = warnings
    return {
        "result_kind": "foundation_research_snapshot",
        "strategy_source": strategy.source_type,
        "definition_type": strategy.definition_type,
        "test_mode": run.test_mode,
        "timeframe": timeframe.value,
        "universe": {
            "requested": effective_universe,
            "resolved_instrument_count": len(instrument_ids),
            "resolved_symbols": symbols[:25],
            "truncated_symbol_count": max(0, len(symbols) - 25),
        },
        "coverage": {
            **coverage,
            "requested_date_from": run.date_from.isoformat() if run.date_from else None,
            "requested_date_to": run.date_to.isoformat() if run.date_to else None,
        },
        "execution_summary": {
            "trade_count": 0,
            "win_rate": None,
            "expectancy_r": None,
            "max_drawdown_pct": None,
            "avg_holding_bars": None,
        },
        "readiness": {
            "has_definition_snapshot": bool(version.definition_snapshot),
            "has_universe": bool(instrument_ids),
            "has_coverage": int(coverage.get("total_bars") or 0) > 0,
            "requires_simulation_engine": True,
        },
        "warnings": warnings,
    }


async def _resolve_universe_instruments(
    db: AsyncSession,
    universe_config: dict,
    warnings: list[str],
) -> list[Instrument]:
    def instrument_stmt():
        return select(Instrument).options(
            selectinload(Instrument.equity_detail),
            selectinload(Instrument.stats),
        )

    instrument_ids = [
        int(value) for value in universe_config.get("instrument_ids", []) if value is not None
    ]
    symbols = [
        str(value).upper() for value in universe_config.get("symbols", []) if str(value).strip()
    ]

    etf_holdings_config = universe_config.get("etf_holdings")
    basket_id = universe_config.get("basket_id")
    watchlist_id = universe_config.get("watchlist_id")
    screener_id = universe_config.get("screener_id")
    if basket_id is not None:
        basket = await db.get(Basket, int(basket_id))
        if basket is None:
            warnings.append(f"Basket {basket_id} could not be found.")
            return []
        stmt = (
            instrument_stmt()
            .join(BasketMember, BasketMember.instrument_id == Instrument.id)
            .where(BasketMember.basket_id == basket.id)
            .order_by(BasketMember.position.asc(), Instrument.symbol.asc())
        )
        rows = list((await db.execute(stmt)).scalars().all())
        if not rows:
            warnings.append(f"Basket '{basket.name}' has no instruments.")
        return rows

    if isinstance(etf_holdings_config, dict):
        etf_symbol = str(etf_holdings_config.get("symbol") or "").strip().upper()
        etf_profile_id = etf_holdings_config.get("profile_id")
        etf_instrument_id = etf_holdings_config.get("instrument_id")
        profile_stmt = select(ETFProfile).join(
            Instrument,
            ETFProfile.instrument_id == Instrument.id,
        )
        if etf_profile_id is not None:
            profile_stmt = profile_stmt.where(ETFProfile.id == int(etf_profile_id))
        elif etf_instrument_id is not None:
            profile_stmt = profile_stmt.where(ETFProfile.instrument_id == int(etf_instrument_id))
        elif etf_symbol:
            profile_stmt = profile_stmt.where(func.upper(Instrument.symbol) == etf_symbol)
        else:
            warnings.append("ETF holdings universe is missing an ETF symbol.")
            return []
        profile = (await db.execute(profile_stmt.limit(1))).scalar_one_or_none()
        if profile is None:
            target = etf_symbol or etf_profile_id or etf_instrument_id
            warnings.append(f"ETF holdings profile {target} could not be found.")
            return []

        snapshot_date = _parse_etf_snapshot_date(
            etf_holdings_config.get("snapshot_date")
            or etf_holdings_config.get("composition_date")
            or etf_holdings_config.get("as_of_date")
        )
        snapshot_stmt = (
            select(ETFHoldingsSnapshot)
            .where(ETFHoldingsSnapshot.etf_profile_id == profile.id)
            .options(selectinload(ETFHoldingsSnapshot.rows))
        )
        if snapshot_date is not None:
            snapshot_stmt = snapshot_stmt.where(
                ETFHoldingsSnapshot.composition_date <= snapshot_date
            )
        snapshot = (
            await db.execute(
                snapshot_stmt.order_by(
                    ETFHoldingsSnapshot.composition_date.desc(),
                    ETFHoldingsSnapshot.id.desc(),
                ).limit(1)
            )
        ).scalar_one_or_none()
        if snapshot is None:
            if snapshot_date is None:
                warnings.append("ETF holdings universe has no snapshots yet.")
            else:
                warnings.append(
                    f"ETF holdings universe has no snapshot available on or before {snapshot_date.isoformat()}."
                )
            return []

        holding_ids: list[int] = []
        seen_holding_ids: set[int] = set()
        unresolved_count = 0
        non_security_count = 0
        for row in snapshot.rows:
            if row.row_type != "security":
                non_security_count += 1
                continue
            if row.constituent_instrument_id is None:
                unresolved_count += 1
                continue
            if row.constituent_instrument_id in seen_holding_ids:
                continue
            seen_holding_ids.add(row.constituent_instrument_id)
            holding_ids.append(row.constituent_instrument_id)
        if unresolved_count:
            warnings.append(
                f"ETF holdings snapshot has {unresolved_count} unresolved security rows that cannot be tested yet."
            )
        if non_security_count:
            warnings.append(
                f"ETF holdings snapshot excludes {non_security_count} non-security rows from the strategy universe."
            )
        if not holding_ids:
            warnings.append("ETF holdings snapshot did not resolve to any testable instruments.")
            return []

        stmt = instrument_stmt().where(Instrument.id.in_(holding_ids))
        instrument_rows = list((await db.execute(stmt)).scalars().all())
        instrument_by_id = {row.id: row for row in instrument_rows}
        return [instrument_by_id[instrument_id] for instrument_id in holding_ids if instrument_id in instrument_by_id]

    if watchlist_id is not None:
        watchlist = await db.get(Watchlist, int(watchlist_id))
        if watchlist is None:
            warnings.append(f"Watchlist {watchlist_id} could not be found.")
            return []
        stmt = (
            instrument_stmt()
            .join(WatchlistItem, WatchlistItem.instrument_id == Instrument.id)
            .where(WatchlistItem.watchlist_id == watchlist.id)
            .order_by(WatchlistItem.position.asc(), Instrument.symbol.asc())
        )
        rows = list((await db.execute(stmt)).scalars().all())
        if not rows:
            warnings.append(f"Watchlist '{watchlist.name}' has no active instruments.")
        return rows

    if screener_id is not None:
        screener = await db.get(ScreenerDefinition, int(screener_id))
        if screener is None:
            warnings.append(f"Screener {screener_id} could not be found.")
            return []
        latest_result = (
            await db.execute(
                select(ScreenerResult)
                .where(ScreenerResult.screener_id == screener.id)
                .order_by(ScreenerResult.run_at.desc(), ScreenerResult.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest_result is None:
            warnings.append(f"Screener '{screener.name}' has no run results yet.")
            return []
        matched_ids = [
            int(value) for value in list(latest_result.matched_ids or []) if value is not None
        ]
        if not matched_ids:
            warnings.append(
                f"Screener '{screener.name}' did not match any instruments in its latest run."
            )
            return []
        stmt = instrument_stmt().where(Instrument.id.in_(matched_ids)).order_by(Instrument.symbol)
        return list((await db.execute(stmt)).scalars().all())

    if instrument_ids:
        stmt = instrument_stmt().where(Instrument.id.in_(instrument_ids)).order_by(Instrument.symbol)
        return list((await db.execute(stmt)).scalars().all())

    if symbols:
        stmt = (
            instrument_stmt()
            .where(func.upper(Instrument.symbol).in_(symbols))
            .order_by(Instrument.symbol)
        )
        rows = list((await db.execute(stmt)).scalars().all())
        resolved = {row.symbol.upper() for row in rows}
        missing = [symbol for symbol in symbols if symbol not in resolved]
        if missing:
            warnings.append(f"Some symbols could not be resolved: {', '.join(missing[:10])}")
        return rows

    return []


async def _resolve_dynamic_etf_universe(
    db: AsyncSession,
    universe_config: dict[str, Any],
    *,
    date_to: datetime | None,
    warnings: list[str],
) -> tuple[list[Instrument], DynamicETFUniverse | None]:
    if not _is_dynamic_etf_holdings_universe(universe_config):
        return [], None
    etf_holdings_config = universe_config.get("etf_holdings")
    if not isinstance(etf_holdings_config, dict):
        basket_id = universe_config.get("basket_id")
        if basket_id is None:
            return [], None
        basket = await db.get(Basket, int(basket_id))
        if basket is None:
            warnings.append(f"Dynamic basket universe {basket_id} could not be found.")
            return [], None
        if basket.source_etf_profile_id is None:
            return await _resolve_dynamic_basket_snapshot_universe(
                db,
                basket,
                date_to=date_to,
                warnings=warnings,
            )
        profile_stmt = select(ETFProfile).where(ETFProfile.id == basket.source_etf_profile_id)
        basket_profile_id = basket.source_etf_profile_id
        basket_universe_id = basket.id
    else:
        etf_symbol = str(etf_holdings_config.get("symbol") or "").strip().upper()
        etf_profile_id = etf_holdings_config.get("profile_id")
        etf_instrument_id = etf_holdings_config.get("instrument_id")
        profile_stmt = select(ETFProfile).join(Instrument, ETFProfile.instrument_id == Instrument.id)
        basket_profile_id = None
        basket_universe_id = None
        if etf_profile_id is not None:
            profile_stmt = profile_stmt.where(ETFProfile.id == int(etf_profile_id))
        elif etf_instrument_id is not None:
            profile_stmt = profile_stmt.where(ETFProfile.instrument_id == int(etf_instrument_id))
        elif etf_symbol:
            profile_stmt = profile_stmt.where(func.upper(Instrument.symbol) == etf_symbol)
        else:
            warnings.append("Dynamic ETF holdings universe is missing an ETF symbol.")
            return [], None

    profile = (await db.execute(profile_stmt.limit(1))).scalar_one_or_none()
    if profile is None:
        target = (
            basket_profile_id
            if basket_profile_id is not None
            else etf_symbol or etf_profile_id or etf_instrument_id
        )
        warnings.append(f"Dynamic ETF holdings profile {target} could not be found.")
        return [], None

    snapshot_stmt = (
        select(ETFHoldingsSnapshot)
        .where(ETFHoldingsSnapshot.etf_profile_id == profile.id)
        .options(selectinload(ETFHoldingsSnapshot.rows))
        .order_by(
            ETFHoldingsSnapshot.composition_date.asc(),
            ETFHoldingsSnapshot.known_at.asc().nullsfirst(),
            ETFHoldingsSnapshot.id.asc(),
        )
    )
    if date_to is not None:
        snapshot_stmt = snapshot_stmt.where(
            ETFHoldingsSnapshot.composition_date <= date_to.astimezone(UTC).date()
        )
    etf_snapshots = tuple((await db.execute(snapshot_stmt)).scalars().all())
    if not etf_snapshots:
        warnings.append("Dynamic ETF holdings universe has no snapshots available for the run window.")
        return [], None

    instrument_ids: list[int] = []
    seen: set[int] = set()
    unresolved_count = 0
    non_security_count = 0
    snapshots: list[DynamicUniverseSnapshot] = []
    for snapshot in etf_snapshots:
        snapshot_member_ids: set[int] = set()
        for row in snapshot.rows:
            if row.row_type != "security":
                non_security_count += 1
                continue
            if row.constituent_instrument_id is None:
                unresolved_count += 1
                continue
            snapshot_member_ids.add(row.constituent_instrument_id)
            if row.constituent_instrument_id in seen:
                continue
            seen.add(row.constituent_instrument_id)
            instrument_ids.append(row.constituent_instrument_id)
        snapshots.append(
            DynamicUniverseSnapshot(
                id=snapshot.id,
                composition_date=snapshot.composition_date,
                known_at=snapshot.known_at,
                member_ids=frozenset(snapshot_member_ids),
                source_type="etf_holdings",
            )
        )

    if unresolved_count:
        warnings.append(
            "Dynamic ETF holdings universe has unresolved security rows that cannot be tested yet."
        )
    if non_security_count:
        warnings.append("Dynamic ETF holdings universe excludes non-security rows.")
    if not instrument_ids:
        warnings.append("Dynamic ETF holdings universe did not resolve to any testable instruments.")
        return [], None

    stmt = (
        select(Instrument)
        .options(selectinload(Instrument.equity_detail), selectinload(Instrument.stats))
        .where(Instrument.id.in_(instrument_ids))
    )
    rows = list((await db.execute(stmt)).scalars().all())
    instrument_by_id = {row.id: row for row in rows}
    instruments = [
        instrument_by_id[instrument_id]
        for instrument_id in instrument_ids
        if instrument_id in instrument_by_id
    ]
    return instruments, DynamicETFUniverse(
        profile_id=basket_profile_id or profile.id,
        basket_id=basket_universe_id,
        kind="etf_holdings",
        instrument_ids=tuple(instrument.id for instrument in instruments),
        snapshots=tuple(snapshots),
    )


async def _resolve_dynamic_basket_snapshot_universe(
    db: AsyncSession,
    basket: Basket,
    *,
    date_to: datetime | None,
    warnings: list[str],
) -> tuple[list[Instrument], DynamicETFUniverse | None]:
    snapshot_stmt = (
        select(BasketSnapshot)
        .where(BasketSnapshot.basket_id == basket.id)
        .options(selectinload(BasketSnapshot.members))
        .order_by(
            BasketSnapshot.composition_date.asc(),
            BasketSnapshot.known_at.asc().nullsfirst(),
            BasketSnapshot.id.asc(),
        )
    )
    if date_to is not None:
        snapshot_stmt = snapshot_stmt.where(
            BasketSnapshot.composition_date <= date_to.astimezone(UTC).date()
        )
    basket_snapshots = tuple((await db.execute(snapshot_stmt)).scalars().all())
    if not basket_snapshots:
        warnings.append(f"Basket '{basket.name}' has no composition snapshots for dynamic simulation.")
        return [], None

    instrument_ids: list[int] = []
    seen: set[int] = set()
    snapshots: list[DynamicUniverseSnapshot] = []
    for snapshot in basket_snapshots:
        member_ids = {member.instrument_id for member in snapshot.members}
        for instrument_id in sorted(member_ids):
            if instrument_id in seen:
                continue
            seen.add(instrument_id)
            instrument_ids.append(instrument_id)
        snapshots.append(
            DynamicUniverseSnapshot(
                id=snapshot.id,
                composition_date=snapshot.composition_date,
                known_at=snapshot.known_at,
                member_ids=frozenset(member_ids),
                source_type=snapshot.source_type,
            )
        )
    if not instrument_ids:
        warnings.append(f"Basket '{basket.name}' snapshots did not resolve to any testable instruments.")
        return [], None

    stmt = (
        select(Instrument)
        .options(selectinload(Instrument.equity_detail), selectinload(Instrument.stats))
        .where(Instrument.id.in_(instrument_ids))
    )
    rows = list((await db.execute(stmt)).scalars().all())
    instrument_by_id = {row.id: row for row in rows}
    instruments = [
        instrument_by_id[instrument_id]
        for instrument_id in instrument_ids
        if instrument_id in instrument_by_id
    ]
    return instruments, DynamicETFUniverse(
        profile_id=None,
        basket_id=basket.id,
        kind="basket",
        instrument_ids=tuple(instrument.id for instrument in instruments),
        snapshots=tuple(snapshots),
    )


async def _load_bars_for_strategy(
    db: AsyncSession,
    *,
    instrument_id: int,
    timeframe: Timeframe,
    date_from: datetime | None,
    date_to: datetime | None,
) -> list[OHLCVBar]:
    stmt = (
        select(OHLCVBar)
        .where(OHLCVBar.instrument_id == instrument_id, OHLCVBar.timeframe == timeframe)
        .order_by(OHLCVBar.ts.asc())
    )
    if date_from is not None:
        stmt = stmt.where(OHLCVBar.ts >= date_from)
    if date_to is not None:
        stmt = stmt.where(OHLCVBar.ts <= date_to)
    return list((await db.execute(stmt)).scalars().all())


def _iter_condition_nodes(node: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(node, dict):
        rows.append(node)
        for child in node.get("conditions", []) or []:
            rows.extend(_iter_condition_nodes(child))
        rows.extend(_iter_condition_nodes(node.get("condition")))
    elif isinstance(node, list):
        for child in node:
            rows.extend(_iter_condition_nodes(child))
    return rows


def _condition_types_used(
    conditions: list[dict[str, Any]],
    condition_tree: dict[str, Any] | None,
) -> set[str]:
    rows = _iter_condition_nodes(conditions) + _iter_condition_nodes(condition_tree)
    return {
        str(row.get("type") or "").lower()
        for row in rows
        if isinstance(row, dict) and row.get("type")
    }


def _extract_risk_and_exit_config(definition: dict[str, Any]) -> dict[str, Any]:
    risk = definition.get("risk", {})
    exits = definition.get("exits", {})
    if not isinstance(risk, dict):
        risk = {}
    if not isinstance(exits, dict):
        exits = {}

    take_profit_rr = (
        exits["take_profit_rr"]
        if "take_profit_rr" in exits
        else risk["take_profit_rr"]
        if "take_profit_rr" in risk
        else 2
    )
    max_bars_in_trade = (
        exits["max_bars_in_trade"]
        if "max_bars_in_trade" in exits
        else risk["max_bars_in_trade"]
        if "max_bars_in_trade" in risk
        else 20
    )

    return {
        "stop_model": str(risk.get("stop_model") or "percent").lower(),
        "stop_loss_pct": _coerce_float(risk.get("stop_loss_pct"), 3),
        "stop_atr_period": _coerce_int(risk.get("stop_atr_period"), 14),
        "stop_atr_multiple": _coerce_float(risk.get("stop_atr_multiple"), 2),
        "hard_trailing_stop_pct": _coerce_float(risk.get("hard_trailing_stop_pct"), 0),
        "hard_trailing_activation_pct": _coerce_float(risk.get("hard_trailing_activation_pct"), 0),
        "break_even_rr": _coerce_float(risk.get("break_even_rr"), 0),
        "trailing_stop_rr": _coerce_float(risk.get("trailing_stop_rr"), 0),
        "position_sizing_mode": str(risk.get("position_sizing_mode") or "percent_risk").lower(),
        "position_sizing_value": _coerce_float(risk.get("position_sizing_value"), 1),
        "pyramiding_max_entries": _coerce_int(risk.get("pyramiding_max_entries"), 1),
        "take_profit_rr": _coerce_float(take_profit_rr, 0),
        "max_bars_in_trade": _coerce_int(max_bars_in_trade, 0),
        "exit_logic": str(exits.get("logic") or exits.get("exit_logic") or "all").lower(),
        "exit_conditions": list(exits.get("conditions", [])) if isinstance(exits.get("conditions"), list) else [],
        "exit_condition_tree": exits.get("condition_tree") if isinstance(exits.get("condition_tree"), dict) else None,
    }


def _build_instrument_context(instrument: Instrument) -> dict[str, Any]:
    fundamentals: dict[str, Any] = {
        "currency": instrument.currency,
    }
    if instrument.equity_detail is not None:
        fundamentals.update(
            {
                "sector": instrument.equity_detail.sector,
                "industry": instrument.equity_detail.industry,
                "country": instrument.equity_detail.country,
                "exchange_mic": instrument.equity_detail.exchange_mic,
                "market_cap_tier": instrument.equity_detail.market_cap_tier,
                "employees": instrument.equity_detail.employees,
            }
        )
    stats: dict[str, Any] = {}
    if instrument.stats is not None:
        stats.update(
            {
                "week52_high": instrument.stats.week52_high,
                "week52_low": instrument.stats.week52_low,
                "avg_volume_30d": instrument.stats.avg_volume_30d,
                "pe_ratio": instrument.stats.pe_ratio,
                "market_cap": instrument.stats.market_cap,
                "beta": instrument.stats.beta,
                "dividend_yield": instrument.stats.dividend_yield,
            }
        )
    return {"fundamentals": fundamentals, "stats": stats}


def _etf_holdings_snapshot_mode(universe_config: dict[str, Any] | None) -> str:
    config = (universe_config or {}).get("etf_holdings")
    if not isinstance(config, dict):
        return str((universe_config or {}).get("basket_snapshot_mode") or "static").strip().lower()
    return str(config.get("snapshot_mode") or config.get("mode") or "static").strip().lower()


def _is_dynamic_etf_holdings_universe(universe_config: dict[str, Any] | None) -> bool:
    return _etf_holdings_snapshot_mode(universe_config) in {
        "dynamic",
        "point_in_time",
        "point-in-time",
        "historical",
    }


def _snapshot_known_on_or_before(snapshot: DynamicUniverseSnapshot, requested_date: date) -> bool:
    if snapshot.known_at is None:
        return True
    known_at = snapshot.known_at
    if known_at.tzinfo is None:
        known_at = known_at.replace(tzinfo=UTC)
    return known_at.astimezone(UTC) <= datetime.combine(requested_date, datetime.min.time(), tzinfo=UTC)


def _snapshot_member_ids(snapshot: DynamicUniverseSnapshot) -> set[int]:
    return set(snapshot.member_ids)


def _dynamic_member_ids_for_date(dynamic_universe: DynamicETFUniverse, requested_date: date) -> set[int]:
    usable_snapshots = [
        snapshot
        for snapshot in dynamic_universe.snapshots
        if snapshot.composition_date <= requested_date
        and _snapshot_known_on_or_before(snapshot, requested_date)
    ]
    if not usable_snapshots:
        return set()
    return _snapshot_member_ids(usable_snapshots[-1])


def _dynamic_snapshot_for_date(
    dynamic_universe: DynamicETFUniverse,
    requested_date: date,
) -> ETFHoldingsSnapshot | None:
    usable_snapshots = [
        snapshot
        for snapshot in dynamic_universe.snapshots
        if snapshot.composition_date <= requested_date
        and _snapshot_known_on_or_before(snapshot, requested_date)
    ]
    return usable_snapshots[-1] if usable_snapshots else None


def _filter_bars_for_dynamic_etf_universe(
    bars: list[OHLCVBar],
    *,
    instrument_id: int,
    dynamic_universe: DynamicETFUniverse | None,
) -> list[OHLCVBar]:
    if dynamic_universe is None:
        return bars
    return [
        bar
        for bar in bars
        if instrument_id
        in _dynamic_member_ids_for_date(dynamic_universe, bar.ts.astimezone(UTC).date())
    ]


def _dynamic_universe_exit_policy(
    *,
    run: StrategyRun,
    version: StrategyVersion,
) -> str:
    raw_policy = (
        run.execution_assumptions.get("dynamic_universe_exit_policy")
        or (version.execution_model or {}).get("dynamic_universe_exit_policy")
        or "leave_open"
    )
    policy = str(raw_policy).strip().lower()
    if policy in {"close_on_removal", "close_removed", "liquidate_on_removal"}:
        return "close_on_removal"
    return "leave_open"


def _dynamic_membership_removed_by_end(
    position: NautilusOpenPosition,
    *,
    dynamic_universe: DynamicETFUniverse | None,
    date_to: datetime | None,
) -> bool:
    if dynamic_universe is None or date_to is None:
        return False
    current_at = _parse_iso_datetime(position.current_at)
    current_date = current_at.astimezone(UTC).date()
    end_date = date_to.astimezone(UTC).date()
    if current_date >= end_date:
        return False
    current_members = _dynamic_member_ids_for_date(dynamic_universe, current_date)
    end_members = _dynamic_member_ids_for_date(dynamic_universe, end_date)
    return position.instrument_id in current_members and position.instrument_id not in end_members


def _close_positions_removed_from_dynamic_universe(
    open_positions: list[NautilusOpenPosition],
    *,
    dynamic_universe: DynamicETFUniverse | None,
    date_to: datetime | None,
    policy: str,
) -> tuple[list[NautilusTrade], list[NautilusOpenPosition]]:
    if policy != "close_on_removal" or dynamic_universe is None:
        return [], open_positions
    removal_trades: list[NautilusTrade] = []
    remaining_open_positions: list[NautilusOpenPosition] = []
    for position in open_positions:
        if not _dynamic_membership_removed_by_end(
            position,
            dynamic_universe=dynamic_universe,
            date_to=date_to,
        ):
            remaining_open_positions.append(position)
            continue
        removal_trades.append(
            NautilusTrade(
                instrument_id=position.instrument_id,
                instrument_symbol=position.instrument_symbol,
                side=position.side,
                entry_at=position.entry_at,
                exit_at=position.current_at,
                entry_price=position.entry_price,
                exit_price=position.current_price,
                stop_price=position.stop_price,
                target_price=position.target_price,
                quantity=position.quantity,
                pnl=position.unrealized_pnl,
                pnl_pct=position.unrealized_pnl_pct,
                r_multiple=position.r_multiple,
                bars_held=position.bars_held,
                exit_reason="constituent_removed",
            )
        )
    return removal_trades, remaining_open_positions


def _dynamic_snapshot_fields(snapshot: DynamicUniverseSnapshot | None) -> dict[str, Any]:
    if snapshot is None:
        return {}
    return {
        "universe_snapshot_id": snapshot.id,
        "universe_snapshot_composition_date": snapshot.composition_date.isoformat(),
        "universe_snapshot_known_at": snapshot.known_at.isoformat()
        if snapshot.known_at is not None
        else None,
        "universe_snapshot_source_type": snapshot.source_type,
    }


def _annotate_dynamic_universe_execution_log(
    execution_log: list[dict[str, Any]],
    *,
    dynamic_universe: DynamicETFUniverse | None,
    instrument_rows: list[Instrument],
    run_end: datetime | None,
) -> list[dict[str, Any]]:
    if dynamic_universe is None:
        return execution_log
    instrument_id_by_symbol = {instrument.symbol.upper(): instrument.id for instrument in instrument_rows}
    run_end_date = run_end.astimezone(UTC).date() if run_end is not None else None
    annotated: list[dict[str, Any]] = []
    for event in execution_log:
        row = dict(event)
        symbol = str(row.get("symbol") or "").upper()
        instrument_id = instrument_id_by_symbol.get(symbol)
        if instrument_id is None:
            annotated.append(row)
            continue
        event_dt = _parse_iso_datetime(str(row.get("ts") or ""))
        event_date = event_dt.astimezone(UTC).date()
        if row.get("reason") == "constituent_removed" and run_end_date is not None:
            snapshot = _dynamic_snapshot_for_date(dynamic_universe, run_end_date)
            row["universe_membership_status"] = "removed"
        else:
            snapshot = _dynamic_snapshot_for_date(dynamic_universe, event_date)
            row["universe_membership_status"] = (
                "member"
                if snapshot is not None and instrument_id in _snapshot_member_ids(snapshot)
                else "not_member"
            )
        row.update(_dynamic_snapshot_fields(snapshot))
        row["universe_profile_id"] = dynamic_universe.profile_id
        row["universe_basket_id"] = dynamic_universe.basket_id
        annotated.append(row)
    return annotated


def _max_drawdown_pct(equity_curve: list[dict[str, float | str]]) -> float:
    peak = None
    max_dd = 0.0
    for point in equity_curve:
        equity = float(point["equity"])
        if peak is None or equity > peak:
            peak = equity
        if peak and peak > 0:
            dd = (peak - equity) / peak * 100.0
            max_dd = max(max_dd, dd)
    return round(max_dd, 4)


def _drawdown_curve(equity_curve: list[dict[str, float | str]]) -> list[dict[str, float | str]]:
    peak = None
    rows: list[dict[str, float | str]] = []
    for point in equity_curve:
        equity = float(point["equity"])
        if peak is None or equity > peak:
            peak = equity
        drawdown_pct = 0.0 if not peak or peak <= 0 else ((peak - equity) / peak) * 100.0
        rows.append({"ts": str(point["ts"]), "drawdown_pct": round(drawdown_pct, 4)})
    return rows


def _monthly_returns(
    equity_curve: list[dict[str, float | str]],
) -> list[dict[str, float | str | None]]:
    grouped: dict[str, list[float]] = {}
    for point in equity_curve:
        ts = str(point["ts"])
        month_key = ts[:7]
        grouped.setdefault(month_key, []).append(float(point["equity"]))
    rows: list[dict[str, float | str | None]] = []
    for month, values in sorted(grouped.items()):
        if len(values) < 2 or values[0] == 0:
            rows.append({"period": month, "return_pct": None})
            continue
        rows.append(
            {
                "period": month,
                "return_pct": round(((values[-1] - values[0]) / values[0]) * 100.0, 4),
            }
        )
    return rows


def _quarterly_returns(
    equity_curve: list[dict[str, float | str]],
) -> list[dict[str, float | str | None]]:
    grouped: dict[str, list[float]] = {}
    for point in equity_curve:
        ts = str(point["ts"])
        year = ts[:4]
        month = int(ts[5:7])
        quarter = ((month - 1) // 3) + 1
        key = f"{year}-Q{quarter}"
        grouped.setdefault(key, []).append(float(point["equity"]))
    rows: list[dict[str, float | str | None]] = []
    for period, values in sorted(grouped.items()):
        if len(values) < 2 or values[0] == 0:
            rows.append({"period": period, "return_pct": None})
            continue
        rows.append(
            {
                "period": period,
                "return_pct": round(((values[-1] - values[0]) / values[0]) * 100.0, 4),
            }
        )
    return rows


def _histogram(values: list[float], *, bucket_count: int = 8) -> list[dict[str, float | int]]:
    clean = [float(value) for value in values if np.isfinite(value)]
    if not clean:
        return []
    minimum = min(clean)
    maximum = max(clean)
    if minimum == maximum:
        return [{"lower": round(minimum, 4), "upper": round(maximum, 4), "count": len(clean)}]
    bucket_size = (maximum - minimum) / bucket_count
    rows: list[dict[str, float | int]] = []
    for index in range(bucket_count):
        lower = minimum + bucket_size * index
        upper = maximum if index == bucket_count - 1 else minimum + bucket_size * (index + 1)
        if index == bucket_count - 1:
            count = sum(1 for value in clean if lower <= value <= upper)
        else:
            count = sum(1 for value in clean if lower <= value < upper)
        rows.append({"lower": round(lower, 4), "upper": round(upper, 4), "count": count})
    return rows


def _trade_distributions(trades: list[NautilusTrade]) -> dict:
    if not trades:
        return {
            "holding_bars": [],
            "r_multiple": [],
            "pnl": [],
            "mae_mfe": {},
            "holding_histogram": [],
            "r_histogram": [],
            "pnl_histogram": [],
        }
    holding = [float(trade.bars_held) for trade in trades]
    r_multiple = [round(trade.r_multiple, 4) for trade in trades]
    pnl_values = [round(trade.pnl, 4) for trade in trades]
    return {
        "holding_bars": [trade.bars_held for trade in trades],
        "r_multiple": r_multiple,
        "pnl": pnl_values,
        "holding_histogram": _histogram(holding),
        "r_histogram": _histogram(r_multiple),
        "pnl_histogram": _histogram(pnl_values),
    }


def _parse_iso_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _build_portfolio_equity_curve(
    trades: list[NautilusTrade],
    *,
    initial_capital: float,
    fallback_ts: str,
) -> list[dict[str, float | str]]:
    if not trades:
        return [{"ts": fallback_ts, "equity": round(initial_capital, 4)}]
    running_equity = initial_capital
    grouped: dict[str, float] = defaultdict(float)
    for trade in trades:
        grouped[trade.exit_at] += float(trade.pnl)
    curve = [{"ts": trades[0].entry_at or fallback_ts, "equity": round(initial_capital, 4)}]
    for ts in sorted(grouped.keys()):
        running_equity += grouped[ts]
        curve.append({"ts": ts, "equity": round(running_equity, 4)})
    return curve


def _build_dense_portfolio_history(
    trades: list[NautilusTrade],
    *,
    open_positions: list[NautilusOpenPosition] | None = None,
    bars_by_instrument: dict[int, list[OHLCVBar]],
    initial_capital: float,
    fallback_ts: str,
) -> dict[str, list[dict[str, float | int | str]]]:
    open_positions = open_positions or []
    all_timestamps = sorted(
        {
            bar.ts.astimezone(UTC).isoformat()
            for bars in bars_by_instrument.values()
            for bar in bars
        },
        key=_parse_iso_datetime,
    )
    if not all_timestamps:
        return {
            "equity_curve": [{"ts": fallback_ts, "equity": round(initial_capital, 4)}],
            "portfolio_timeline": [
                {
                    "ts": fallback_ts,
                    "open_position_count": 0,
                    "deployed_capital": 0.0,
                    "idle_capital": round(initial_capital, 4),
                    "realized_pnl": 0.0,
                    "total_equity": round(initial_capital, 4),
                    "event_type": "baseline",
                }
            ],
        }

    bars_by_ts: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for instrument_id, bars in bars_by_instrument.items():
        for bar in bars:
            bars_by_ts[bar.ts.astimezone(UTC).isoformat()].append((instrument_id, float(bar.close)))

    entry_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    exit_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        direction = 1.0 if str(trade.side).lower() == "long" else -1.0
        event_payload = {
            "position_id": f"{trade.instrument_symbol}-{trade.entry_at}",
            "instrument_id": trade.instrument_id,
            "quantity": float(trade.quantity),
            "entry_price": float(trade.entry_price),
            "exit_price": float(trade.exit_price),
            "pnl": float(trade.pnl),
            "side": str(trade.side).lower(),
            "direction": direction,
        }
        entry_events[trade.entry_at].append(event_payload)
        exit_events[trade.exit_at].append(event_payload)

    for position in open_positions:
        direction = 1.0 if str(position.side).lower() == "long" else -1.0
        entry_events[position.entry_at].append(
            {
                "position_id": f"{position.instrument_symbol}-{position.entry_at}",
                "instrument_id": position.instrument_id,
                "quantity": float(position.quantity),
                "entry_price": float(position.entry_price),
                "exit_price": float(position.current_price),
                "pnl": float(position.unrealized_pnl),
                "side": str(position.side).lower(),
                "direction": direction,
                "status": "open",
            }
        )

    current_close_by_instrument: dict[int, float] = {}
    open_positions: dict[str, dict[str, Any]] = {}
    cash = float(initial_capital)
    realized_pnl = 0.0
    equity_curve: list[dict[str, float | str]] = []
    portfolio_timeline: list[dict[str, float | int | str]] = []

    for ts in all_timestamps:
        for instrument_id, close_price in bars_by_ts.get(ts, []):
            current_close_by_instrument[instrument_id] = float(close_price)

        event_type = "mark"
        if exit_events.get(ts):
            event_type = "exit"
            for event in exit_events[ts]:
                signed_quantity = float(event["quantity"]) * float(event["direction"])
                cash += signed_quantity * float(event["entry_price"]) + float(event["pnl"])
                realized_pnl += float(event["pnl"])
                open_positions.pop(str(event["position_id"]), None)

        if entry_events.get(ts):
            if event_type == "mark":
                event_type = "entry"
            for event in entry_events[ts]:
                signed_quantity = float(event["quantity"]) * float(event["direction"])
                cash -= signed_quantity * float(event["entry_price"])
                open_positions[str(event["position_id"])] = dict(event)

        deployed_capital = 0.0
        position_value = 0.0
        for position in open_positions.values():
            current_price = current_close_by_instrument.get(
                int(position["instrument_id"]),
                float(position["entry_price"]),
            )
            quantity = float(position["quantity"])
            direction = float(position["direction"])
            deployed_capital += abs(quantity * current_price)
            position_value += direction * quantity * current_price

        equity = cash + position_value
        equity_curve.append({"ts": ts, "equity": round(equity, 4)})
        portfolio_timeline.append(
            {
                "ts": ts,
                "open_position_count": len(open_positions),
                "deployed_capital": round(deployed_capital, 4),
                "idle_capital": round(cash, 4),
                "realized_pnl": round(realized_pnl, 4),
                "total_equity": round(equity, 4),
                "event_type": event_type,
            }
        )

    if equity_curve[0]["ts"] != fallback_ts and _parse_iso_datetime(fallback_ts) < _parse_iso_datetime(
        str(equity_curve[0]["ts"])
    ):
        baseline = {"ts": fallback_ts, "equity": round(initial_capital, 4)}
        equity_curve.insert(0, baseline)
        portfolio_timeline.insert(
            0,
            {
                "ts": fallback_ts,
                "open_position_count": 0,
                "deployed_capital": 0.0,
                "idle_capital": round(initial_capital, 4),
                "realized_pnl": 0.0,
                "total_equity": round(initial_capital, 4),
                "event_type": "baseline",
            },
        )

    return {
        "equity_curve": equity_curve,
        "portfolio_timeline": portfolio_timeline,
    }


def _build_position_timelines(
    trades: list[NautilusTrade],
    *,
    open_positions: list[NautilusOpenPosition] | None = None,
    bars_by_instrument: dict[int, list[OHLCVBar]],
) -> list[dict[str, Any]]:
    open_positions = open_positions or []
    if not trades and not open_positions:
        return []

    symbol_counts: dict[str, int] = defaultdict(int)
    timelines: list[dict[str, Any]] = []

    for trade in sorted(
        trades,
        key=lambda item: (_parse_iso_datetime(item.entry_at), item.instrument_symbol, item.exit_at),
    ):
        symbol_counts[trade.instrument_symbol] += 1
        entry_dt = _parse_iso_datetime(trade.entry_at)
        exit_dt = _parse_iso_datetime(trade.exit_at)
        bars = bars_by_instrument.get(trade.instrument_id, [])
        in_window = [bar for bar in bars if entry_dt < bar.ts.astimezone(UTC) < exit_dt]
        direction = 1.0 if str(trade.side).lower() == "long" else -1.0

        points: list[dict[str, Any]] = [
            {
                "ts": trade.entry_at,
                "value": 0.0,
                "detail": (
                    f"Entry · {trade.instrument_symbol} {trade.side.upper()} · "
                    f"{trade.quantity:.2f} @ {trade.entry_price:.2f}"
                ),
                "marker": "entry",
            }
        ]

        for bar in in_window:
            close_price = float(bar.close)
            pnl_value = (close_price - float(trade.entry_price)) * float(trade.quantity) * direction
            points.append(
                {
                    "ts": bar.ts.astimezone(UTC).isoformat(),
                    "value": round(pnl_value, 4),
                    "detail": None,
                    "marker": None,
                }
            )

        points.append(
            {
                "ts": trade.exit_at,
                "value": round(float(trade.pnl), 4),
                "detail": (
                    f"Exit · {str(trade.exit_reason).replace('_', ' ')} · "
                    f"{trade.exit_price:.2f} · {trade.r_multiple:.2f}R"
                ),
                "marker": "exit",
            }
        )

        deduped_points: list[dict[str, Any]] = []
        by_ts: dict[str, dict[str, Any]] = {}
        for point in points:
            by_ts[point["ts"]] = point
        for ts in sorted(by_ts.keys()):
            deduped_points.append(by_ts[ts])

        timelines.append(
            {
                "position_id": f"{trade.instrument_symbol}-{symbol_counts[trade.instrument_symbol]}-{trade.entry_at}",
                "label": f"{trade.instrument_symbol} #{symbol_counts[trade.instrument_symbol]}",
                "symbol": trade.instrument_symbol,
                "side": trade.side,
                "entry_at": trade.entry_at,
                "exit_at": trade.exit_at,
                "entry_price": trade.entry_price,
                "exit_price": trade.exit_price,
                "quantity": trade.quantity,
                "pnl": trade.pnl,
                "pnl_pct": trade.pnl_pct,
                "r_multiple": trade.r_multiple,
                "bars_held": trade.bars_held,
                "exit_reason": trade.exit_reason,
                "points": deduped_points,
            }
        )

    for position in sorted(
        open_positions,
        key=lambda item: (_parse_iso_datetime(item.entry_at), item.instrument_symbol, item.current_at),
    ):
        symbol_counts[position.instrument_symbol] += 1
        entry_dt = _parse_iso_datetime(position.entry_at)
        current_dt = _parse_iso_datetime(position.current_at)
        bars = bars_by_instrument.get(position.instrument_id, [])
        in_window = [bar for bar in bars if entry_dt < bar.ts.astimezone(UTC) < current_dt]
        direction = 1.0 if str(position.side).lower() == "long" else -1.0

        points: list[dict[str, Any]] = [
            {
                "ts": position.entry_at,
                "value": 0.0,
                "detail": (
                    f"Entry · {position.instrument_symbol} {position.side.upper()} · "
                    f"{position.quantity:.2f} @ {position.entry_price:.2f}"
                ),
                "marker": "entry",
            }
        ]

        for bar in in_window:
            close_price = float(bar.close)
            pnl_value = (close_price - float(position.entry_price)) * float(position.quantity) * direction
            points.append(
                {
                    "ts": bar.ts.astimezone(UTC).isoformat(),
                    "value": round(pnl_value, 4),
                    "detail": None,
                    "marker": None,
                }
            )

        points.append(
            {
                "ts": position.current_at,
                "value": round(float(position.unrealized_pnl), 4),
                "detail": (
                    f"Open · mark {position.current_price:.2f} · "
                    f"{position.r_multiple:.2f}R unrealized"
                ),
                "marker": "open",
            }
        )

        deduped_points: list[dict[str, Any]] = []
        by_ts: dict[str, dict[str, Any]] = {}
        for point in points:
            by_ts[point["ts"]] = point
        for ts in sorted(by_ts.keys()):
            deduped_points.append(by_ts[ts])

        timelines.append(
            {
                "position_id": f"{position.instrument_symbol}-{symbol_counts[position.instrument_symbol]}-{position.entry_at}",
                "label": f"{position.instrument_symbol} #{symbol_counts[position.instrument_symbol]}",
                "symbol": position.instrument_symbol,
                "side": position.side,
                "entry_at": position.entry_at,
                "exit_at": None,
                "entry_price": position.entry_price,
                "exit_price": None,
                "current_at": position.current_at,
                "current_price": position.current_price,
                "quantity": position.quantity,
                "pnl": position.unrealized_pnl,
                "pnl_pct": position.unrealized_pnl_pct,
                "r_multiple": position.r_multiple,
                "bars_held": position.bars_held,
                "exit_reason": None,
                "status": "open",
                "points": deduped_points,
            }
        )

    return timelines


def _apply_portfolio_constraints(
    trades: list[NautilusTrade],
    *,
    open_positions: list[NautilusOpenPosition] | None = None,
    initial_capital: float,
    max_concurrent_positions: int,
    max_portfolio_risk_pct: float,
    max_symbol_allocation_pct: float,
    fallback_ts: str,
) -> dict[str, Any]:
    open_positions = open_positions or []
    accepted: list[NautilusTrade] = []
    accepted_open_positions: list[NautilusOpenPosition] = []
    rejected: list[dict[str, Any]] = []
    active_positions: list[dict[str, Any]] = []
    peak_concurrent = 0

    candidates: list[dict[str, Any]] = [
        {"kind": "trade", "item": trade}
        for trade in trades
    ] + [
        {"kind": "open_position", "item": position}
        for position in open_positions
    ]

    for candidate in sorted(
        candidates,
        key=lambda item: (
            _parse_iso_datetime(item["item"].entry_at),
            item["item"].instrument_symbol,
            getattr(item["item"], "exit_at", getattr(item["item"], "current_at", "")),
        ),
    ):
        item = candidate["item"]
        kind = str(candidate["kind"])
        entry_dt = _parse_iso_datetime(item.entry_at)
        active_positions = [
            position
            for position in active_positions
            if _parse_iso_datetime(position["exit_at"]) > entry_dt
        ]

        notional = abs(float(item.quantity) * float(item.entry_price))
        risk_amount = abs(float(item.entry_price) - float(item.stop_price)) * float(
            item.quantity
        )
        risk_pct = (risk_amount / initial_capital * 100.0) if initial_capital > 0 else 0.0
        allocation_pct = (notional / initial_capital * 100.0) if initial_capital > 0 else 0.0
        reserved_notional = sum(float(position["notional"]) for position in active_positions)
        reserved_risk_pct = sum(float(position["risk_pct"]) for position in active_positions)

        rejection_reason = None
        if len(active_positions) >= max(1, max_concurrent_positions):
            rejection_reason = "max_concurrent_positions"
        elif allocation_pct > max_symbol_allocation_pct:
            rejection_reason = "max_symbol_allocation_pct"
        elif reserved_risk_pct + risk_pct > max_portfolio_risk_pct:
            rejection_reason = "max_portfolio_risk_pct"
        elif reserved_notional + notional > initial_capital:
            rejection_reason = "capital_exhausted"

        if rejection_reason is not None:
            rejected.append(
                {
                    "instrument_symbol": item.instrument_symbol,
                    "side": item.side,
                    "entry_at": item.entry_at,
                    "entry_price": float(item.entry_price),
                    "quantity": float(item.quantity),
                    "notional": round(notional, 4),
                    "reason": rejection_reason,
                    "risk_pct": round(risk_pct, 4),
                    "allocation_pct": round(allocation_pct, 4),
                }
            )
            continue

        if kind == "trade":
            accepted.append(item)
        else:
            accepted_open_positions.append(item)

        active_positions.append(
            {
                "position_id": f"{item.instrument_symbol}-{item.entry_at}",
                "exit_at": getattr(item, "exit_at", getattr(item, "current_at", "")),
                "risk_pct": risk_pct,
                "notional": notional,
                "symbol": item.instrument_symbol,
                "side": item.side,
                "entry_at": item.entry_at,
                "entry_price": float(item.entry_price),
                "quantity": float(item.quantity),
            }
        )
        peak_concurrent = max(peak_concurrent, len(active_positions))

    def event_sort_key(event: dict[str, Any]) -> tuple[datetime, int, str]:
        ts = _parse_iso_datetime(event["ts"])
        event_order = {"entry": 0, "exit": 1, "open_at_end": 2, "rejected": 3}.get(
            str(event["event_type"]), 4
        )
        return ts, event_order, str(event.get("symbol") or "")

    accepted_rows = sorted(
        accepted,
        key=lambda item: (
            _parse_iso_datetime(item.entry_at),
            _parse_iso_datetime(item.exit_at),
            item.instrument_symbol,
        ),
    )

    execution_events: list[dict[str, Any]] = []
    for trade in accepted_rows:
        position_id = f"{trade.instrument_symbol}-{trade.entry_at}"
        quantity = float(trade.quantity)
        entry_price = float(trade.entry_price)
        exit_price = float(trade.exit_price)
        execution_events.append(
            {
                "ts": trade.entry_at,
                "event_type": "entry",
                "position_id": position_id,
                "symbol": trade.instrument_symbol,
                "side": trade.side,
                "quantity": quantity,
                "price": entry_price,
                "notional": abs(quantity * entry_price),
                "pnl": None,
                "pnl_pct": None,
                "r_multiple": None,
                "reason": "entry_signal",
            }
        )
        execution_events.append(
            {
                "ts": trade.exit_at,
                "event_type": "exit",
                "position_id": position_id,
                "symbol": trade.instrument_symbol,
                "side": trade.side,
                "quantity": quantity,
                "price": exit_price,
                "notional": abs(quantity * entry_price),
                "pnl": float(trade.pnl),
                "pnl_pct": float(trade.pnl_pct),
                "r_multiple": float(trade.r_multiple),
                "reason": trade.exit_reason,
            }
        )

    accepted_open_rows = sorted(
        accepted_open_positions,
        key=lambda item: (
            _parse_iso_datetime(item.entry_at),
            item.instrument_symbol,
            _parse_iso_datetime(item.current_at),
        ),
    )
    for position in accepted_open_rows:
        position_id = f"{position.instrument_symbol}-{position.entry_at}"
        quantity = float(position.quantity)
        entry_price = float(position.entry_price)
        current_price = float(position.current_price)
        execution_events.append(
            {
                "ts": position.entry_at,
                "event_type": "entry",
                "position_id": position_id,
                "symbol": position.instrument_symbol,
                "side": position.side,
                "quantity": quantity,
                "price": entry_price,
                "notional": abs(quantity * entry_price),
                "pnl": None,
                "pnl_pct": None,
                "r_multiple": None,
                "reason": "entry_signal",
            }
        )
        execution_events.append(
            {
                "ts": position.current_at,
                "event_type": "open_at_end",
                "position_id": position_id,
                "symbol": position.instrument_symbol,
                "side": position.side,
                "quantity": quantity,
                "price": current_price,
                "notional": abs(quantity * entry_price),
                "pnl": float(position.unrealized_pnl),
                "pnl_pct": float(position.unrealized_pnl_pct),
                "r_multiple": float(position.r_multiple),
                "reason": "run_end_mark",
            }
        )

    for row in rejected:
        execution_events.append(
            {
                "ts": row["entry_at"],
                "event_type": "rejected",
                "position_id": f"{row['instrument_symbol']}-{row['entry_at']}",
                "symbol": row["instrument_symbol"],
                "side": row.get("side"),
                "quantity": row.get("quantity"),
                "price": row.get("entry_price"),
                "notional": row.get("notional"),
                "pnl": None,
                "pnl_pct": None,
                "r_multiple": None,
                "reason": row["reason"],
            }
        )

    execution_events.sort(key=event_sort_key)

    open_by_id: dict[str, dict[str, Any]] = {}
    realized_pnl = 0.0
    portfolio_timeline: list[dict[str, Any]] = []

    for event in execution_events:
        position_id = str(event["position_id"])
        if event["event_type"] == "entry":
            open_by_id[position_id] = {
                "notional": float(event.get("notional") or 0.0),
            }
        elif event["event_type"] == "exit":
            open_by_id.pop(position_id, None)
            realized_pnl += float(event.get("pnl") or 0.0)

        deployed_capital = sum(float(item["notional"]) for item in open_by_id.values())
        idle_capital = max(initial_capital - deployed_capital, 0.0)
        portfolio_timeline.append(
            {
                "ts": event["ts"],
                "open_position_count": len(open_by_id),
                "deployed_capital": round(deployed_capital, 4),
                "idle_capital": round(idle_capital, 4),
                "realized_pnl": round(realized_pnl, 4),
                "event_type": event["event_type"],
            }
        )

    return {
        "accepted_trades": accepted,
        "accepted_open_positions": accepted_open_positions,
        "rejected_trades": rejected,
        "execution_log": execution_events,
        "portfolio_timeline": portfolio_timeline,
        "equity_curve": _build_portfolio_equity_curve(
            accepted,
            initial_capital=initial_capital,
            fallback_ts=fallback_ts,
        ),
        "summary": {
            "accepted_trade_count": len(accepted),
            "accepted_open_position_count": len(accepted_open_positions),
            "accepted_position_count": len(accepted) + len(accepted_open_positions),
            "rejected_trade_count": len(rejected),
            "peak_concurrent_positions": peak_concurrent,
            "rejection_breakdown": {
                reason: sum(1 for row in rejected if row["reason"] == reason)
                for reason in sorted({row["reason"] for row in rejected})
            },
        },
    }


def _benchmark_comparison(
    equity_curve: list[dict[str, float | str]],
    benchmark: dict,
) -> dict:
    benchmark_curve = list(benchmark.get("equity_curve") or [])
    if not equity_curve or not benchmark_curve:
        return {
            "excess_return_pct": None,
            "equity_curve": [],
        }
    by_ts = {str(point["ts"]): float(point["equity"]) for point in benchmark_curve}
    rows: list[dict[str, float | str]] = []
    for point in equity_curve:
        ts = str(point["ts"])
        if ts not in by_ts:
            continue
        rows.append(
            {
                "ts": ts,
                "strategy_equity": round(float(point["equity"]), 4),
                "benchmark_equity": round(by_ts[ts], 4),
                "spread": round(float(point["equity"]) - by_ts[ts], 4),
            }
        )
    excess_return_pct = None
    strategy_return = rows[-1]["strategy_equity"] - rows[0]["strategy_equity"] if rows else None
    benchmark_return = rows[-1]["benchmark_equity"] - rows[0]["benchmark_equity"] if rows else None
    if (
        rows
        and rows[0]["strategy_equity"] > 0
        and strategy_return is not None
        and benchmark_return is not None
    ):
        excess_return_pct = round(
            ((strategy_return - benchmark_return) / rows[0]["strategy_equity"]) * 100.0,
            4,
        )
    return {
        "excess_return_pct": excess_return_pct,
        "equity_curve": rows,
    }


async def _run_rules_backtest(
    db: AsyncSession,
    *,
    strategy: StrategyDefinition,
    version: StrategyVersion,
    run: StrategyRun,
) -> dict:
    if run.test_mode == "walk_forward":
        return await _run_rules_walk_forward(db, strategy=strategy, version=version, run=run)
    if run.test_mode == "paper_forward":
        return await _run_rules_paper_forward(db, strategy=strategy, version=version, run=run)

    definition = _apply_parameter_values(dict(version.definition_snapshot or {}), run.parameter_values or {})
    effective_universe = dict(version.universe_config or {})
    effective_universe.update(run.universe_config or {})
    warnings: list[str] = []

    timeframe_value = run.timeframe or definition.get("timeframe") or Timeframe.D1.value
    timeframe = _coerce_timeframe(str(timeframe_value), warnings)

    dynamic_universe: DynamicETFUniverse | None = None
    if _is_dynamic_etf_holdings_universe(effective_universe):
        instrument_rows, dynamic_universe = await _resolve_dynamic_etf_universe(
            db,
            effective_universe,
            date_to=run.date_to,
            warnings=warnings,
        )
    else:
        instrument_rows = await _resolve_universe_instruments(db, effective_universe, warnings)
    trades: list[NautilusTrade] = []
    open_positions: list[NautilusOpenPosition] = []
    covered_symbols: list[str] = []
    bars_by_instrument: dict[int, list[OHLCVBar]] = {}
    coverage = await _build_universe_coverage_summary(
        db,
        instrument_rows=instrument_rows,
        timeframe=timeframe,
        date_from=run.date_from,
        date_to=run.date_to,
        preview_mode="resolved" if instrument_rows else "empty",
        preview_note=None if instrument_rows else "No instruments resolved from the current universe.",
    )

    initial_capital = float(run.execution_assumptions.get("initial_capital", 100000))
    risk_per_trade_pct = _coerce_float(run.execution_assumptions.get("risk_per_trade_pct"), 1.0)
    slippage_bps = _coerce_float(
        run.execution_assumptions.get("slippage_bps"),
        0.0 if "slippage_bps" in run.execution_assumptions else 5.0,
    )
    commission_model, commission_value = _coerce_commission_settings(run.execution_assumptions)
    close_open_positions_at_end = run.execution_assumptions.get("close_open_positions_at_end") is True
    dynamic_universe_policy = _dynamic_universe_exit_policy(run=run, version=version)
    max_concurrent_positions = int(
        run.execution_assumptions.get("max_concurrent_positions")
        or (version.execution_model or {}).get("max_concurrent_positions")
        or max(len(instrument_rows), 1)
    )
    max_portfolio_risk_pct = float(
        run.execution_assumptions.get("max_portfolio_risk_pct")
        or (version.execution_model or {}).get("max_portfolio_risk_pct")
        or (risk_per_trade_pct * max(max_concurrent_positions, 1))
    )
    max_symbol_allocation_pct = float(
        run.execution_assumptions.get("max_symbol_allocation_pct")
        or (version.execution_model or {}).get("max_symbol_allocation_pct")
        or 100.0
    )
    risk_and_exits = _extract_risk_and_exit_config(definition)
    stop_loss_pct = float(risk_and_exits["stop_loss_pct"])
    stop_model = str(risk_and_exits["stop_model"])
    stop_atr_period = int(risk_and_exits["stop_atr_period"])
    stop_atr_multiple = float(risk_and_exits["stop_atr_multiple"])
    hard_trailing_stop_pct = float(risk_and_exits["hard_trailing_stop_pct"])
    hard_trailing_activation_pct = float(risk_and_exits["hard_trailing_activation_pct"])
    take_profit_rr = float(risk_and_exits["take_profit_rr"])
    max_bars_in_trade = int(risk_and_exits["max_bars_in_trade"])
    break_even_rr = float(risk_and_exits["break_even_rr"])
    trailing_stop_rr = float(risk_and_exits["trailing_stop_rr"])
    position_sizing_mode = str(risk_and_exits["position_sizing_mode"])
    position_sizing_value = float(risk_and_exits["position_sizing_value"])
    pyramiding_max_entries = int(risk_and_exits["pyramiding_max_entries"])
    direction = str(definition.get("direction", "long")).lower()
    logic = str(definition.get("entry_logic", "all")).lower()
    conditions = list(definition.get("conditions", []))
    condition_tree = definition.get("condition_tree")
    exit_logic = str(risk_and_exits["exit_logic"] or "all").lower()
    exit_conditions = list(risk_and_exits["exit_conditions"])
    exit_condition_tree = risk_and_exits["exit_condition_tree"]
    condition_types = _condition_types_used(conditions, condition_tree if isinstance(condition_tree, dict) else None)
    condition_types |= _condition_types_used(exit_conditions, exit_condition_tree if isinstance(exit_condition_tree, dict) else None)
    requires_daily_aux = "performance" in condition_types and timeframe != Timeframe.D1
    requires_weekly_aux = bool(
        {"week52_new_high", "week52_new_low", "pct_from_52w_high", "pct_from_52w_low"} & condition_types
    ) and timeframe != Timeframe.W1

    if not conditions:
        warnings.append("No entry conditions were defined; no trades can be simulated.")

    capital_slice = initial_capital / max(len(instrument_rows), 1)

    for instrument in instrument_rows:
        bars = await _load_bars_for_strategy(
            db,
            instrument_id=instrument.id,
            timeframe=timeframe,
            date_from=run.date_from,
            date_to=run.date_to,
        )
        bars = _filter_bars_for_dynamic_etf_universe(
            bars,
            instrument_id=instrument.id,
            dynamic_universe=dynamic_universe,
        )
        if len(bars) < 3:
            warnings.append(f"{instrument.symbol} does not have enough bars for simulation.")
            continue
        bars_by_instrument[instrument.id] = bars
        daily_bars = (
            await _load_bars_for_strategy(
                db,
                instrument_id=instrument.id,
                timeframe=Timeframe.D1,
                date_from=run.date_from,
                date_to=run.date_to,
            )
            if requires_daily_aux
            else []
        )
        daily_bars = _filter_bars_for_dynamic_etf_universe(
            daily_bars,
            instrument_id=instrument.id,
            dynamic_universe=dynamic_universe,
        )
        weekly_bars = (
            await _load_bars_for_strategy(
                db,
                instrument_id=instrument.id,
                timeframe=Timeframe.W1,
                date_from=run.date_from,
                date_to=run.date_to,
            )
            if requires_weekly_aux
            else []
        )
        weekly_bars = _filter_bars_for_dynamic_etf_universe(
            weekly_bars,
            instrument_id=instrument.id,
            dynamic_universe=dynamic_universe,
        )
        covered_symbols.append(instrument.symbol)
        instrument_result = run_single_instrument_nautilus_backtest(
            instrument=instrument,
            bars=bars,
            timeframe=timeframe,
            direction=direction,
            entry_logic=logic,
            conditions=conditions,
            condition_tree=condition_tree if isinstance(condition_tree, dict) else None,
            exit_logic=exit_logic,
            exit_conditions=exit_conditions,
            exit_condition_tree=exit_condition_tree if isinstance(exit_condition_tree, dict) else None,
            signal_events=None,
            stop_model=stop_model,
            stop_loss_pct=stop_loss_pct,
            stop_atr_period=stop_atr_period,
            stop_atr_multiple=stop_atr_multiple,
            take_profit_rr=take_profit_rr,
            max_bars_in_trade=max_bars_in_trade,
            capital_base=capital_slice,
            position_sizing_mode=position_sizing_mode,
            position_sizing_value=position_sizing_value,
            risk_per_trade_pct=risk_per_trade_pct,
            slippage_bps=slippage_bps,
            commission_per_trade=commission_value,
            commission_model=commission_model,
            commission_value=commission_value,
            close_open_positions_at_end=close_open_positions_at_end,
            break_even_rr=break_even_rr,
            trailing_stop_rr=trailing_stop_rr,
            hard_trailing_stop_pct=hard_trailing_stop_pct,
            hard_trailing_activation_pct=hard_trailing_activation_pct,
            pyramiding_max_entries=pyramiding_max_entries,
            daily_bars=daily_bars,
            weekly_bars=weekly_bars,
            instrument_context=_build_instrument_context(instrument),
        )
        trades.extend(instrument_result.trades)
        open_positions.extend(instrument_result.open_positions)
        warnings.extend(instrument_result.warnings)

    removal_trades, open_positions = _close_positions_removed_from_dynamic_universe(
        open_positions,
        dynamic_universe=dynamic_universe,
        date_to=run.date_to,
        policy=dynamic_universe_policy,
    )
    trades.extend(removal_trades)

    portfolio_view = _apply_portfolio_constraints(
        trades,
        open_positions=open_positions,
        initial_capital=initial_capital,
        max_concurrent_positions=max_concurrent_positions,
        max_portfolio_risk_pct=max_portfolio_risk_pct,
        max_symbol_allocation_pct=max_symbol_allocation_pct,
        fallback_ts=run.date_from.isoformat() if run.date_from else datetime.now(UTC).isoformat(),
    )
    trades = list(portfolio_view["accepted_trades"])
    open_positions = list(portfolio_view["accepted_open_positions"])
    rejected_trades = list(portfolio_view["rejected_trades"])
    execution_log = _annotate_dynamic_universe_execution_log(
        list(portfolio_view["execution_log"]),
        dynamic_universe=dynamic_universe,
        instrument_rows=instrument_rows,
        run_end=run.date_to,
    )
    dense_history = _build_dense_portfolio_history(
        trades,
        open_positions=open_positions,
        bars_by_instrument=bars_by_instrument,
        initial_capital=initial_capital,
        fallback_ts=run.date_from.isoformat() if run.date_from else datetime.now(UTC).isoformat(),
    )
    equity_curve = list(dense_history["equity_curve"])
    portfolio_timeline = list(dense_history["portfolio_timeline"])
    position_timelines = _build_position_timelines(
        trades,
        open_positions=open_positions,
        bars_by_instrument=bars_by_instrument,
    )
    if coverage.get("requested_fits_collective_range") is False:
        warnings.append(
            "The requested date range exceeds the shared local coverage window of the selected universe."
        )

    wins = [trade for trade in trades if trade.pnl > 0]
    losses = [trade for trade in trades if trade.pnl <= 0]
    total_wins = sum(trade.pnl for trade in wins)
    total_losses = abs(sum(trade.pnl for trade in losses))
    unrealized_pnl = round(sum(position.unrealized_pnl for position in open_positions), 4)
    realized_ending_capital = round(initial_capital + sum(trade.pnl for trade in trades), 4)
    ending_capital = float(equity_curve[-1]["equity"]) if equity_curve else initial_capital
    expectancy_r = float(np.mean([trade.r_multiple for trade in trades])) if trades else None
    avg_win_r = float(np.mean([trade.r_multiple for trade in wins])) if wins else None
    avg_loss_r = float(np.mean([trade.r_multiple for trade in losses])) if losses else None
    profit_factor = (total_wins / total_losses) if total_losses > 0 else None
    benchmark = await _build_benchmark_summary(
        db,
        benchmark_symbol=str(
            (run.benchmark_config or version.benchmark_config or {}).get("symbol") or ""
        ).upper(),
        timeframe=timeframe,
        date_from=run.date_from,
        date_to=run.date_to,
        initial_capital=initial_capital,
    )
    run.warning_log = warnings
    optimization = await _maybe_run_parameter_sweep(
        db,
        strategy=strategy,
        version=version,
        run=run,
        definition=definition,
        timeframe=timeframe,
        instrument_rows=instrument_rows,
        initial_capital=initial_capital,
        risk_per_trade_pct=risk_per_trade_pct,
        slippage_bps=slippage_bps,
        commission_model=commission_model,
        commission_value=commission_value,
        close_open_positions_at_end=close_open_positions_at_end,
    )
    analytics = {
        "drawdown_curve": _drawdown_curve(equity_curve),
        "monthly_returns": _monthly_returns(equity_curve),
        "quarterly_returns": _quarterly_returns(equity_curve),
        "trade_distributions": _trade_distributions(trades),
    }
    benchmark_comparison = _benchmark_comparison(equity_curve, benchmark)

    return {
        "result_kind": "rules_backtest",
        "strategy_source": strategy.source_type,
        "definition_type": strategy.definition_type,
        "test_mode": run.test_mode,
        "timeframe": timeframe.value,
        "direction": direction,
        "universe": {
            "requested": effective_universe,
            "resolved_instrument_count": len(instrument_rows),
            "resolved_symbols": covered_symbols[:25],
            "truncated_symbol_count": max(0, len(covered_symbols) - 25),
        },
        "coverage": {
            **coverage,
            "requested_date_from": run.date_from.isoformat() if run.date_from else None,
            "requested_date_to": run.date_to.isoformat() if run.date_to else None,
            "simulatable_instrument_count": len(covered_symbols),
            "simulatable_symbols": covered_symbols[:25],
        },
        "performance": {
            "initial_capital": round(initial_capital, 4),
            "ending_capital": round(ending_capital, 4),
            "net_return_pct": round(
                ((ending_capital - initial_capital) / initial_capital * 100.0), 4
            )
            if initial_capital > 0
            else None,
            "trade_count": len(trades),
            "closed_trade_count": len(trades),
            "open_position_count": len(open_positions),
            "total_position_count": len(trades) + len(open_positions),
            "realized_ending_capital": realized_ending_capital,
            "realized_net_return_pct": round(
                ((realized_ending_capital - initial_capital) / initial_capital * 100.0), 4
            )
            if initial_capital > 0
            else None,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_return_pct": round((unrealized_pnl / initial_capital) * 100.0, 4)
            if initial_capital > 0
            else None,
            "win_rate": round((len(wins) / len(trades) * 100.0), 4) if trades else None,
            "avg_win_r": round(avg_win_r, 4) if avg_win_r is not None else None,
            "avg_loss_r": round(avg_loss_r, 4) if avg_loss_r is not None else None,
            "expectancy_r": round(expectancy_r, 4) if expectancy_r is not None else None,
            "profit_factor": round(profit_factor, 4) if profit_factor is not None else None,
            "max_drawdown_pct": _max_drawdown_pct(equity_curve),
        },
        "benchmark": benchmark,
        "benchmark_comparison": benchmark_comparison,
        "execution_assumptions": {
            "initial_capital": initial_capital,
            "risk_per_trade_pct": risk_per_trade_pct,
            "stop_model": stop_model,
            "slippage_bps": slippage_bps,
            "commission_model": commission_model,
            "commission_value": commission_value,
            "commission_per_trade": commission_value,
            "close_open_positions_at_end": close_open_positions_at_end,
            "dynamic_universe_exit_policy": dynamic_universe_policy,
            "stop_loss_pct": stop_loss_pct,
            "stop_atr_period": stop_atr_period,
            "stop_atr_multiple": stop_atr_multiple,
            "hard_trailing_stop_pct": hard_trailing_stop_pct,
            "hard_trailing_activation_pct": hard_trailing_activation_pct,
            "break_even_rr": break_even_rr,
            "trailing_stop_rr": trailing_stop_rr,
            "position_sizing_mode": position_sizing_mode,
            "position_sizing_value": position_sizing_value,
            "pyramiding_max_entries": pyramiding_max_entries,
            "take_profit_rr": take_profit_rr,
            "max_bars_in_trade": max_bars_in_trade,
            "max_concurrent_positions": max_concurrent_positions,
            "max_portfolio_risk_pct": max_portfolio_risk_pct,
            "max_symbol_allocation_pct": max_symbol_allocation_pct,
            "custom_exit_condition_count": len(_iter_condition_nodes(exit_condition_tree)) + len(exit_conditions),
        },
        "dynamic_universe": {
            "kind": dynamic_universe.kind,
            "profile_id": dynamic_universe.profile_id,
            "basket_id": dynamic_universe.basket_id,
            "snapshot_count": len(dynamic_universe.snapshots),
            "exit_policy": dynamic_universe_policy,
            "snapshots": [
                {
                    "id": snapshot.id,
                    "composition_date": snapshot.composition_date.isoformat(),
                    "known_at": snapshot.known_at.isoformat()
                    if snapshot.known_at is not None
                    else None,
                    "source_type": snapshot.source_type,
                }
                for snapshot in dynamic_universe.snapshots
            ],
        }
        if dynamic_universe is not None
        else None,
        "equity_curve": equity_curve,
        "analytics": analytics,
        "portfolio": portfolio_view["summary"],
        "execution_log": execution_log,
        "portfolio_timeline": portfolio_timeline,
        "position_timelines": position_timelines,
        "open_positions": [
            {
                "instrument_id": position.instrument_id,
                "instrument_symbol": position.instrument_symbol,
                "side": position.side,
                "entry_at": position.entry_at,
                "current_at": position.current_at,
                "entry_price": position.entry_price,
                "current_price": position.current_price,
                "stop_price": position.stop_price,
                "target_price": position.target_price,
                "quantity": position.quantity,
                "unrealized_pnl": position.unrealized_pnl,
                "unrealized_pnl_pct": position.unrealized_pnl_pct,
                "r_multiple": position.r_multiple,
                "bars_held": position.bars_held,
                "status": position.status,
            }
            for position in open_positions[:100]
        ],
        "symbol_performance": _symbol_performance_snapshot(
            trades,
            open_positions=open_positions,
        ),
        "optimization": optimization,
        "rejected_trades": rejected_trades[:100],
        "trades": [
            {
                "instrument_id": trade.instrument_id,
                "instrument_symbol": trade.instrument_symbol,
                "side": trade.side,
                "entry_at": trade.entry_at,
                "exit_at": trade.exit_at,
                "entry_price": trade.entry_price,
                "exit_price": trade.exit_price,
                "stop_price": trade.stop_price,
                "target_price": trade.target_price,
                "quantity": trade.quantity,
                "pnl": trade.pnl,
                "pnl_pct": trade.pnl_pct,
                "r_multiple": trade.r_multiple,
                "bars_held": trade.bars_held,
                "exit_reason": trade.exit_reason,
            }
            for trade in trades[:100]
        ],
        "warnings": list(dict.fromkeys(warnings)),
    }


async def _run_rules_walk_forward(
    db: AsyncSession,
    *,
    strategy: StrategyDefinition,
    version: StrategyVersion,
    run: StrategyRun,
) -> dict:
    base = await _run_rules_backtest(
        db,
        strategy=strategy,
        version=version,
        run=StrategyRun(
            strategy_id=run.strategy_id,
            strategy_version_id=run.strategy_version_id,
            requested_by_user_id=run.requested_by_user_id,
            engine_type=run.engine_type,
            test_mode="backtest",
            status=run.status,
            timeframe=run.timeframe,
            date_from=run.date_from,
            date_to=run.date_to,
            parameter_values=run.parameter_values,
            universe_config=run.universe_config,
            benchmark_config=run.benchmark_config,
            execution_assumptions=run.execution_assumptions,
            result_summary={},
            artifact_manifest={},
            warning_log=[],
        ),
    )
    curve = list(base.get("equity_curve") or [])
    performance = dict(base.get("performance") or {})
    segments = int(run.execution_assumptions.get("walk_forward_segments", 3) or 3)
    training_share = float(run.execution_assumptions.get("walk_forward_training_share", 0.6) or 0.6)
    segment_rows: list[dict] = []
    if len(curve) >= segments * 2:
        chunk = max(len(curve) // segments, 1)
        for index in range(segments):
            start = index * chunk
            end = len(curve) if index == segments - 1 else min(len(curve), (index + 1) * chunk)
            window = curve[start:end]
            if len(window) < 2:
                continue
            training_cut = max(1, min(len(window) - 1, int(round(len(window) * training_share))))
            in_sample = window[:training_cut]
            out_sample = window[training_cut:]
            segment_rows.append(
                {
                    "segment": index + 1,
                    "in_sample_from": in_sample[0]["ts"],
                    "in_sample_to": in_sample[-1]["ts"],
                    "out_sample_from": out_sample[0]["ts"],
                    "out_sample_to": out_sample[-1]["ts"],
                    "in_sample_return_pct": round(
                        (
                            (float(in_sample[-1]["equity"]) - float(in_sample[0]["equity"]))
                            / float(in_sample[0]["equity"])
                        )
                        * 100.0,
                        4,
                    )
                    if float(in_sample[0]["equity"])
                    else None,
                    "out_sample_return_pct": round(
                        (
                            (float(out_sample[-1]["equity"]) - float(out_sample[0]["equity"]))
                            / float(out_sample[0]["equity"])
                        )
                        * 100.0,
                        4,
                    )
                    if float(out_sample[0]["equity"])
                    else None,
                }
            )
    base["result_kind"] = "rules_walk_forward"
    base["test_mode"] = "walk_forward"
    base["walk_forward"] = {
        "segment_count": segments,
        "training_share": training_share,
        "segments": segment_rows,
        "out_of_sample_avg_return_pct": round(
            float(
                np.mean(
                    [
                        row["out_sample_return_pct"]
                        for row in segment_rows
                        if row["out_sample_return_pct"] is not None
                    ]
                )
            ),
            4,
        )
        if any(row["out_sample_return_pct"] is not None for row in segment_rows)
        else None,
    }
    performance["walk_forward_segment_count"] = len(segment_rows)
    base["performance"] = performance
    return base


async def _run_rules_paper_forward(
    db: AsyncSession,
    *,
    strategy: StrategyDefinition,
    version: StrategyVersion,
    run: StrategyRun,
) -> dict:
    previous_summary = dict(run.result_summary or {})
    previous_paper = dict(previous_summary.get("paper_forward") or {})
    previous_snapshots = list(previous_paper.get("monitor_snapshots") or [])
    base = await _run_rules_backtest(
        db,
        strategy=strategy,
        version=version,
        run=StrategyRun(
            strategy_id=run.strategy_id,
            strategy_version_id=run.strategy_version_id,
            requested_by_user_id=run.requested_by_user_id,
            engine_type=run.engine_type,
            test_mode="backtest",
            status=run.status,
            timeframe=run.timeframe,
            date_from=run.date_from,
            date_to=run.date_to,
            parameter_values=run.parameter_values,
            universe_config=run.universe_config,
            benchmark_config=run.benchmark_config,
            execution_assumptions=run.execution_assumptions,
            result_summary={},
            artifact_manifest={},
            warning_log=[],
        ),
    )
    curve = list(base.get("equity_curve") or [])
    forward_bars = int(run.execution_assumptions.get("paper_forward_bars", 20) or 20)
    recent_curve = curve[-forward_bars:] if forward_bars > 0 else curve
    latest_equity = recent_curve[-1]["equity"] if recent_curve else None
    snapshot = {
        "snapshot_at": datetime.now(UTC).isoformat(),
        "latest_equity": latest_equity,
        "trade_count": base.get("performance", {}).get("trade_count"),
        "window_bars": forward_bars,
    }
    base["result_kind"] = "rules_paper_forward"
    base["test_mode"] = "paper_forward"
    base["paper_forward"] = {
        "window_bars": forward_bars,
        "forward_curve": recent_curve,
        "active_watchlist": (run.universe_config or version.universe_config or {}).get(
            "watchlist_id"
        ),
        "latest_equity": latest_equity,
        "monitor_snapshots": [*previous_snapshots, snapshot][-20:],
        "monitor_status": "tracking",
    }
    return base


def _radar_side_for_setup(setup_type: RadarSetupType) -> str | None:
    if setup_type in LONG_BIASED_RADAR_SETUPS:
        return "long"
    if setup_type in SHORT_BIASED_RADAR_SETUPS:
        return "short"
    return None


def _normalize_radar_filter_values(
    raw: list[str] | tuple[str, ...] | None,
    enum_type,
) -> list:
    normalized: list = []
    for value in raw or []:
        try:
            normalized.append(enum_type(str(value)))
        except ValueError:
            continue
    return normalized


async def _run_radar_signal_research(
    db: AsyncSession,
    *,
    strategy: StrategyDefinition,
    version: StrategyVersion,
    run: StrategyRun,
) -> dict:
    definition = _apply_parameter_values(dict(version.definition_snapshot or {}), run.parameter_values or {})
    effective_universe = dict(version.universe_config or {})
    effective_universe.update(run.universe_config or {})
    warnings: list[str] = []

    radar_filters = dict(definition.get("radar_filters") or {})
    timeframe_value = run.timeframe or radar_filters.get("timeframe") or Timeframe.D1.value
    timeframe = _coerce_timeframe(str(timeframe_value), warnings)

    setup_types = _normalize_radar_filter_values(radar_filters.get("setup_types"), RadarSetupType)
    states = _normalize_radar_filter_values(radar_filters.get("states"), RadarState)
    min_score = float(radar_filters.get("min_score", 0.0) or 0.0)

    explicit_universe = _has_explicit_universe(effective_universe)
    instrument_rows = (
        await _resolve_universe_instruments(db, effective_universe, warnings)
        if explicit_universe
        else []
    )
    instrument_ids = [row.id for row in instrument_rows]

    signal_stmt = (
        select(RadarDetection)
        .where(
            RadarDetection.timeframe == timeframe,
            RadarDetection.score >= min_score,
        )
        .order_by(
            RadarDetection.instrument_id.asc(),
            RadarDetection.signal_at.asc(),
            RadarDetection.id.asc(),
        )
    )
    if instrument_ids:
        signal_stmt = signal_stmt.where(RadarDetection.instrument_id.in_(instrument_ids))
    if run.date_from is not None:
        signal_stmt = signal_stmt.where(RadarDetection.signal_at >= run.date_from)
    if run.date_to is not None:
        signal_stmt = signal_stmt.where(RadarDetection.signal_at <= run.date_to)
    if setup_types:
        signal_stmt = signal_stmt.where(RadarDetection.setup_type.in_(setup_types))
    if states:
        signal_stmt = signal_stmt.where(RadarDetection.state.in_(states))

    radar_signals = list((await db.execute(signal_stmt)).scalars().all())
    if not radar_signals:
        warnings.append("No Radar detections matched the requested replay filters.")

    signal_groups: dict[int, list[RadarDetection]] = defaultdict(list)
    for detection in radar_signals:
        signal_groups[detection.instrument_id].append(detection)

    if not instrument_rows and signal_groups:
        loaded_instruments = (
            (
                await db.execute(
                    select(Instrument)
                    .where(Instrument.id.in_(list(signal_groups.keys())))
                    .options(
                        selectinload(Instrument.equity_detail),
                        selectinload(Instrument.stats),
                    )
                    .order_by(Instrument.symbol.asc())
                )
            )
            .scalars()
            .all()
        )
        instrument_rows = list(loaded_instruments)

    initial_capital = float(run.execution_assumptions.get("initial_capital", 100000))
    risk_per_trade_pct = _coerce_float(run.execution_assumptions.get("risk_per_trade_pct"), 1.0)
    slippage_bps = _coerce_float(
        run.execution_assumptions.get("slippage_bps"),
        0.0 if "slippage_bps" in run.execution_assumptions else 5.0,
    )
    commission_model, commission_value = _coerce_commission_settings(run.execution_assumptions)
    close_open_positions_at_end = run.execution_assumptions.get("close_open_positions_at_end") is True
    risk_and_exits = _extract_risk_and_exit_config(definition)
    stop_loss_pct = float(risk_and_exits["stop_loss_pct"])
    stop_model = str(risk_and_exits["stop_model"])
    stop_atr_period = int(risk_and_exits["stop_atr_period"])
    stop_atr_multiple = float(risk_and_exits["stop_atr_multiple"])
    hard_trailing_stop_pct = float(risk_and_exits["hard_trailing_stop_pct"])
    hard_trailing_activation_pct = float(risk_and_exits["hard_trailing_activation_pct"])
    take_profit_rr = float(risk_and_exits["take_profit_rr"])
    max_bars_in_trade = int(risk_and_exits["max_bars_in_trade"])
    break_even_rr = float(risk_and_exits["break_even_rr"])
    trailing_stop_rr = float(risk_and_exits["trailing_stop_rr"])
    position_sizing_mode = str(risk_and_exits["position_sizing_mode"])
    position_sizing_value = float(risk_and_exits["position_sizing_value"])
    pyramiding_max_entries = int(risk_and_exits["pyramiding_max_entries"])
    exit_logic = str(risk_and_exits["exit_logic"] or "all").lower()
    exit_conditions = list(risk_and_exits["exit_conditions"])
    exit_condition_tree = risk_and_exits["exit_condition_tree"]
    max_concurrent_positions = int(
        run.execution_assumptions.get("max_concurrent_positions")
        or (version.execution_model or {}).get("max_concurrent_positions")
        or max(len(instrument_rows), 1)
    )
    max_portfolio_risk_pct = float(
        run.execution_assumptions.get("max_portfolio_risk_pct")
        or (version.execution_model or {}).get("max_portfolio_risk_pct")
        or (risk_per_trade_pct * max(max_concurrent_positions, 1))
    )
    max_symbol_allocation_pct = float(
        run.execution_assumptions.get("max_symbol_allocation_pct")
        or (version.execution_model or {}).get("max_symbol_allocation_pct")
        or 100.0
    )

    capital_slice = initial_capital / max(len(instrument_rows), 1)
    trades: list[NautilusTrade] = []
    open_positions: list[NautilusOpenPosition] = []
    covered_symbols: list[str] = []
    bars_by_instrument: dict[int, list[OHLCVBar]] = {}
    coverage_preview_mode = "resolved"
    coverage_preview_note: str | None = None
    if not explicit_universe:
        coverage_preview_mode = "signal_derived"
        coverage_preview_note = (
            "Coverage reflects the instruments that actually produced Radar signals for this run."
        )
    elif not instrument_rows:
        coverage_preview_mode = "empty"
        coverage_preview_note = "No instruments resolved from the current universe."
    coverage = await _build_universe_coverage_summary(
        db,
        instrument_rows=instrument_rows,
        timeframe=timeframe,
        date_from=run.date_from,
        date_to=run.date_to,
        preview_mode=coverage_preview_mode,
        preview_note=coverage_preview_note,
    )

    for instrument in instrument_rows:
        detections = signal_groups.get(instrument.id, [])
        signal_events: list[dict] = []
        for detection in detections:
            side = _radar_side_for_setup(detection.setup_type)
            if side is None:
                continue
            anchor_price = float(detection.entry_price or detection.key_level_price or 0.0)
            if anchor_price <= 0:
                continue
            if side == "long":
                stop_price = float(
                    detection.invalidation_price or (anchor_price * (1.0 - stop_loss_pct / 100.0))
                )
                target_price = float(
                    detection.target_price
                    or (anchor_price + (anchor_price - stop_price) * take_profit_rr)
                )
            else:
                stop_price = float(
                    detection.invalidation_price or (anchor_price * (1.0 + stop_loss_pct / 100.0))
                )
                target_price = float(
                    detection.target_price
                    or (anchor_price - (stop_price - anchor_price) * take_profit_rr)
                )
            if stop_price <= 0 or target_price <= 0 or stop_price == anchor_price:
                continue
            signal_events.append(
                {
                    "signal_at": detection.signal_at,
                    "side": side,
                    "entry_price": anchor_price,
                    "stop_price": stop_price,
                    "target_price": target_price,
                    "setup_type": detection.setup_type.value,
                    "score": float(detection.score),
                }
            )
        if not signal_events:
            continue

        bars = await _load_bars_for_strategy(
            db,
            instrument_id=instrument.id,
            timeframe=timeframe,
            date_from=run.date_from,
            date_to=run.date_to,
        )
        if len(bars) < 3:
            warnings.append(f"{instrument.symbol} does not have enough bars for signal replay.")
            continue
        bars_by_instrument[instrument.id] = bars
        covered_symbols.append(instrument.symbol)
        instrument_result = run_single_instrument_nautilus_backtest(
            instrument=instrument,
            bars=bars,
            timeframe=timeframe,
            direction="long",
            entry_logic="all",
            conditions=[],
            condition_tree=None,
            exit_logic=exit_logic,
            exit_conditions=exit_conditions,
            exit_condition_tree=exit_condition_tree if isinstance(exit_condition_tree, dict) else None,
            stop_model=stop_model,
            stop_loss_pct=stop_loss_pct,
            stop_atr_period=stop_atr_period,
            stop_atr_multiple=stop_atr_multiple,
            take_profit_rr=take_profit_rr,
            max_bars_in_trade=max_bars_in_trade,
            capital_base=capital_slice,
            position_sizing_mode=position_sizing_mode,
            position_sizing_value=position_sizing_value,
            risk_per_trade_pct=risk_per_trade_pct,
            slippage_bps=slippage_bps,
            commission_per_trade=commission_value,
            commission_model=commission_model,
            commission_value=commission_value,
            close_open_positions_at_end=close_open_positions_at_end,
            break_even_rr=break_even_rr,
            trailing_stop_rr=trailing_stop_rr,
            hard_trailing_stop_pct=hard_trailing_stop_pct,
            hard_trailing_activation_pct=hard_trailing_activation_pct,
            pyramiding_max_entries=pyramiding_max_entries,
            signal_events=signal_events,
        )
        trades.extend(instrument_result.trades)
        open_positions.extend(instrument_result.open_positions)
        warnings.extend(instrument_result.warnings)

    portfolio_view = _apply_portfolio_constraints(
        trades,
        open_positions=open_positions,
        initial_capital=initial_capital,
        max_concurrent_positions=max_concurrent_positions,
        max_portfolio_risk_pct=max_portfolio_risk_pct,
        max_symbol_allocation_pct=max_symbol_allocation_pct,
        fallback_ts=run.date_from.isoformat() if run.date_from else datetime.now(UTC).isoformat(),
    )
    trades = list(portfolio_view["accepted_trades"])
    open_positions = list(portfolio_view["accepted_open_positions"])
    rejected_trades = list(portfolio_view["rejected_trades"])
    dense_history = _build_dense_portfolio_history(
        trades,
        open_positions=open_positions,
        bars_by_instrument=bars_by_instrument,
        initial_capital=initial_capital,
        fallback_ts=run.date_from.isoformat() if run.date_from else datetime.now(UTC).isoformat(),
    )
    equity_curve = list(dense_history["equity_curve"])
    portfolio_timeline = list(dense_history["portfolio_timeline"])
    position_timelines = _build_position_timelines(
        trades,
        open_positions=open_positions,
        bars_by_instrument=bars_by_instrument,
    )
    if coverage.get("requested_fits_collective_range") is False:
        warnings.append(
            "The requested date range exceeds the shared local coverage window of the replayed instrument set."
        )
    wins = [trade for trade in trades if trade.pnl > 0]
    losses = [trade for trade in trades if trade.pnl <= 0]
    total_wins = sum(trade.pnl for trade in wins)
    total_losses = abs(sum(trade.pnl for trade in losses))
    unrealized_pnl = round(sum(position.unrealized_pnl for position in open_positions), 4)
    realized_ending_capital = round(initial_capital + sum(trade.pnl for trade in trades), 4)
    ending_capital = float(equity_curve[-1]["equity"]) if equity_curve else initial_capital
    expectancy_r = float(np.mean([trade.r_multiple for trade in trades])) if trades else None
    avg_win_r = float(np.mean([trade.r_multiple for trade in wins])) if wins else None
    avg_loss_r = float(np.mean([trade.r_multiple for trade in losses])) if losses else None
    profit_factor = (total_wins / total_losses) if total_losses > 0 else None
    benchmark = await _build_benchmark_summary(
        db,
        benchmark_symbol=str(
            (run.benchmark_config or version.benchmark_config or {}).get("symbol") or ""
        ).upper(),
        timeframe=timeframe,
        date_from=run.date_from,
        date_to=run.date_to,
        initial_capital=initial_capital,
    )
    run.warning_log = warnings
    analytics = {
        "drawdown_curve": _drawdown_curve(equity_curve),
        "monthly_returns": _monthly_returns(equity_curve),
        "quarterly_returns": _quarterly_returns(equity_curve),
        "trade_distributions": _trade_distributions(trades),
    }
    benchmark_comparison = _benchmark_comparison(equity_curve, benchmark)

    return {
        "result_kind": "radar_replay",
        "strategy_source": strategy.source_type,
        "definition_type": strategy.definition_type,
        "test_mode": run.test_mode,
        "timeframe": timeframe.value,
        "radar_filters": {
            "setup_types": [item.value for item in setup_types],
            "states": [item.value for item in states],
            "min_score": min_score,
        },
        "universe": {
            "requested": effective_universe,
            "resolved_instrument_count": len(instrument_rows),
            "resolved_symbols": covered_symbols[:25],
            "truncated_symbol_count": max(0, len(covered_symbols) - 25),
        },
        "coverage": {
            **coverage,
            "requested_date_from": run.date_from.isoformat() if run.date_from else None,
            "requested_date_to": run.date_to.isoformat() if run.date_to else None,
            "simulatable_instrument_count": len(covered_symbols),
            "simulatable_symbols": covered_symbols[:25],
        },
        "signal_summary": {
            "signal_count": len(radar_signals),
            "replayed_signal_count": sum(len(group) for group in signal_groups.values()),
            "setup_type_breakdown": {
                setup_type.value: sum(1 for item in radar_signals if item.setup_type == setup_type)
                for setup_type in RadarSetupType
                if any(item.setup_type == setup_type for item in radar_signals)
            },
        },
        "performance": {
            "initial_capital": round(initial_capital, 4),
            "ending_capital": round(ending_capital, 4),
            "net_return_pct": round(
                ((ending_capital - initial_capital) / initial_capital * 100.0), 4
            )
            if initial_capital > 0
            else None,
            "trade_count": len(trades),
            "closed_trade_count": len(trades),
            "open_position_count": len(open_positions),
            "total_position_count": len(trades) + len(open_positions),
            "realized_ending_capital": realized_ending_capital,
            "realized_net_return_pct": round(
                ((realized_ending_capital - initial_capital) / initial_capital * 100.0), 4
            )
            if initial_capital > 0
            else None,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_return_pct": round((unrealized_pnl / initial_capital) * 100.0, 4)
            if initial_capital > 0
            else None,
            "win_rate": round((len(wins) / len(trades) * 100.0), 4) if trades else None,
            "avg_win_r": round(avg_win_r, 4) if avg_win_r is not None else None,
            "avg_loss_r": round(avg_loss_r, 4) if avg_loss_r is not None else None,
            "expectancy_r": round(expectancy_r, 4) if expectancy_r is not None else None,
            "profit_factor": round(profit_factor, 4) if profit_factor is not None else None,
            "max_drawdown_pct": _max_drawdown_pct(equity_curve),
        },
        "benchmark": benchmark,
        "benchmark_comparison": benchmark_comparison,
        "execution_assumptions": {
            "initial_capital": initial_capital,
            "risk_per_trade_pct": risk_per_trade_pct,
            "stop_model": stop_model,
            "slippage_bps": slippage_bps,
            "commission_model": commission_model,
            "commission_value": commission_value,
            "commission_per_trade": commission_value,
            "close_open_positions_at_end": close_open_positions_at_end,
            "stop_loss_pct": stop_loss_pct,
            "stop_atr_period": stop_atr_period,
            "stop_atr_multiple": stop_atr_multiple,
            "hard_trailing_stop_pct": hard_trailing_stop_pct,
            "hard_trailing_activation_pct": hard_trailing_activation_pct,
            "break_even_rr": break_even_rr,
            "trailing_stop_rr": trailing_stop_rr,
            "position_sizing_mode": position_sizing_mode,
            "position_sizing_value": position_sizing_value,
            "pyramiding_max_entries": pyramiding_max_entries,
            "take_profit_rr": take_profit_rr,
            "max_bars_in_trade": max_bars_in_trade,
            "max_concurrent_positions": max_concurrent_positions,
            "max_portfolio_risk_pct": max_portfolio_risk_pct,
            "max_symbol_allocation_pct": max_symbol_allocation_pct,
            "custom_exit_condition_count": len(_iter_condition_nodes(exit_condition_tree)) + len(exit_conditions),
        },
        "equity_curve": equity_curve,
        "analytics": analytics,
        "portfolio": portfolio_view["summary"],
        "execution_log": portfolio_view["execution_log"],
        "portfolio_timeline": portfolio_timeline,
        "position_timelines": position_timelines,
        "open_positions": [
            {
                "instrument_id": position.instrument_id,
                "instrument_symbol": position.instrument_symbol,
                "side": position.side,
                "entry_at": position.entry_at,
                "current_at": position.current_at,
                "entry_price": position.entry_price,
                "current_price": position.current_price,
                "stop_price": position.stop_price,
                "target_price": position.target_price,
                "quantity": position.quantity,
                "unrealized_pnl": position.unrealized_pnl,
                "unrealized_pnl_pct": position.unrealized_pnl_pct,
                "r_multiple": position.r_multiple,
                "bars_held": position.bars_held,
                "status": position.status,
            }
            for position in open_positions[:100]
        ],
        "symbol_performance": _symbol_performance_snapshot(
            trades,
            open_positions=open_positions,
        ),
        "rejected_trades": rejected_trades[:100],
        "trades": [
            {
                "instrument_id": trade.instrument_id,
                "instrument_symbol": trade.instrument_symbol,
                "side": trade.side,
                "entry_at": trade.entry_at,
                "exit_at": trade.exit_at,
                "entry_price": trade.entry_price,
                "exit_price": trade.exit_price,
                "stop_price": trade.stop_price,
                "target_price": trade.target_price,
                "quantity": trade.quantity,
                "pnl": trade.pnl,
                "pnl_pct": trade.pnl_pct,
                "r_multiple": trade.r_multiple,
                "bars_held": trade.bars_held,
                "exit_reason": trade.exit_reason,
            }
            for trade in trades[:100]
        ],
        "warnings": list(dict.fromkeys(warnings)),
    }


async def _maybe_run_parameter_sweep(
    db: AsyncSession,
    *,
    strategy: StrategyDefinition,
    version: StrategyVersion,
    run: StrategyRun,
    definition: dict,
    timeframe: Timeframe,
    instrument_rows: list[Instrument],
    initial_capital: float,
    risk_per_trade_pct: float,
    slippage_bps: float,
    commission_model: str,
    commission_value: float,
    close_open_positions_at_end: bool,
) -> dict | None:
    config = dict(run.execution_assumptions.get("optimization") or {})
    if not config.get("enabled"):
        return None
    risk_and_exits = _extract_risk_and_exit_config(definition)
    stop_values = config.get("stop_loss_pct_values") or [
        risk_and_exits["stop_loss_pct"]
    ]
    target_values = config.get("take_profit_rr_values") or [
        risk_and_exits["take_profit_rr"]
    ]
    bar_values = config.get("max_bars_in_trade_values") or [
        risk_and_exits["max_bars_in_trade"]
    ]
    combos: list[dict] = []
    for stop_loss_pct in stop_values[:6]:
        for take_profit_rr in target_values[:6]:
            for max_bars_in_trade in bar_values[:6]:
                combos.append(
                    {
                        "stop_loss_pct": float(stop_loss_pct),
                        "take_profit_rr": float(take_profit_rr),
                        "max_bars_in_trade": int(max_bars_in_trade),
                    }
                )
    leaderboard: list[dict] = []
    direction = str(definition.get("direction", "long")).lower()
    logic = str(definition.get("entry_logic", "all")).lower()
    conditions = list(definition.get("conditions", []))
    condition_tree = definition.get("condition_tree")
    exit_logic = str(risk_and_exits["exit_logic"] or "all").lower()
    exit_conditions = list(risk_and_exits["exit_conditions"])
    exit_condition_tree = risk_and_exits["exit_condition_tree"]
    condition_types = _condition_types_used(
        conditions,
        condition_tree if isinstance(condition_tree, dict) else None,
    )
    condition_types |= _condition_types_used(
        exit_conditions,
        exit_condition_tree if isinstance(exit_condition_tree, dict) else None,
    )
    requires_daily_aux = "performance" in condition_types and timeframe != Timeframe.D1
    requires_weekly_aux = bool(
        {"week52_new_high", "week52_new_low", "pct_from_52w_high", "pct_from_52w_low"} & condition_types
    ) and timeframe != Timeframe.W1
    capital_slice = initial_capital / max(len(instrument_rows), 1)
    for combo in combos[:20]:
        combo_trades: list[NautilusTrade] = []
        for instrument in instrument_rows[:8]:
            bars = await _load_bars_for_strategy(
                db,
                instrument_id=instrument.id,
                timeframe=timeframe,
                date_from=run.date_from,
                date_to=run.date_to,
            )
            if len(bars) < 3:
                continue
            daily_bars = (
                await _load_bars_for_strategy(
                    db,
                    instrument_id=instrument.id,
                    timeframe=Timeframe.D1,
                    date_from=run.date_from,
                    date_to=run.date_to,
                )
                if requires_daily_aux
                else []
            )
            weekly_bars = (
                await _load_bars_for_strategy(
                    db,
                    instrument_id=instrument.id,
                    timeframe=Timeframe.W1,
                    date_from=run.date_from,
                    date_to=run.date_to,
                )
                if requires_weekly_aux
                else []
            )
            result = run_single_instrument_nautilus_backtest(
                instrument=instrument,
                bars=bars,
                timeframe=timeframe,
                direction=direction,
                entry_logic=logic,
                conditions=conditions,
                condition_tree=condition_tree if isinstance(condition_tree, dict) else None,
                exit_logic=exit_logic,
                exit_conditions=exit_conditions,
                exit_condition_tree=exit_condition_tree if isinstance(exit_condition_tree, dict) else None,
                signal_events=None,
                stop_model=str(risk_and_exits["stop_model"]),
                stop_loss_pct=combo["stop_loss_pct"],
                stop_atr_period=int(risk_and_exits["stop_atr_period"]),
                stop_atr_multiple=float(risk_and_exits["stop_atr_multiple"]),
                take_profit_rr=combo["take_profit_rr"],
                max_bars_in_trade=combo["max_bars_in_trade"],
                capital_base=capital_slice,
                position_sizing_mode=str(risk_and_exits["position_sizing_mode"]),
                position_sizing_value=float(risk_and_exits["position_sizing_value"]),
                risk_per_trade_pct=risk_per_trade_pct,
                slippage_bps=slippage_bps,
                commission_per_trade=commission_value,
                commission_model=commission_model,
                commission_value=commission_value,
                close_open_positions_at_end=close_open_positions_at_end,
                break_even_rr=float(risk_and_exits["break_even_rr"]),
                trailing_stop_rr=float(risk_and_exits["trailing_stop_rr"]),
                hard_trailing_stop_pct=float(risk_and_exits["hard_trailing_stop_pct"]),
                hard_trailing_activation_pct=float(
                    risk_and_exits["hard_trailing_activation_pct"]
                ),
                pyramiding_max_entries=int(risk_and_exits["pyramiding_max_entries"]),
                daily_bars=daily_bars,
                weekly_bars=weekly_bars,
                instrument_context=_build_instrument_context(instrument),
            )
            combo_trades.extend(result.trades)
        if not combo_trades:
            continue
        leaderboard.append(
            {
                **combo,
                "trade_count": len(combo_trades),
                "net_pnl": round(sum(trade.pnl for trade in combo_trades), 4),
                "avg_r": round(float(np.mean([trade.r_multiple for trade in combo_trades])), 4),
            }
        )
    leaderboard.sort(key=lambda row: (row["net_pnl"], row["avg_r"]), reverse=True)
    return {
        "evaluated_combinations": len(leaderboard),
        "leaderboard": leaderboard[:10],
    }


def _symbol_performance_snapshot(
    trades: list[NautilusTrade],
    *,
    open_positions: list[NautilusOpenPosition] | None = None,
) -> list[dict[str, float | int | str | None]]:
    grouped: dict[str, list[NautilusTrade]] = {}
    for trade in trades:
        grouped.setdefault(trade.instrument_symbol, []).append(trade)
    open_grouped: dict[str, list[NautilusOpenPosition]] = {}
    for position in open_positions or []:
        open_grouped.setdefault(position.instrument_symbol, []).append(position)

    snapshot: list[dict[str, float | int | str | None]] = []
    for symbol in sorted(set(grouped) | set(open_grouped)):
        symbol_trades = grouped.get(symbol, [])
        symbol_open_positions = open_grouped.get(symbol, [])
        wins = [trade for trade in symbol_trades if trade.pnl > 0]
        realized_pnl = round(sum(trade.pnl for trade in symbol_trades), 4)
        unrealized_pnl = round(sum(position.unrealized_pnl for position in symbol_open_positions), 4)
        total_pnl = round(realized_pnl + unrealized_pnl, 4)
        snapshot.append(
            {
                "symbol": symbol,
                "trade_count": len(symbol_trades),
                "closed_trade_count": len(symbol_trades),
                "open_position_count": len(symbol_open_positions),
                "net_pnl": total_pnl,
                "total_pnl": total_pnl,
                "realized_pnl": realized_pnl,
                "unrealized_pnl": unrealized_pnl,
                "win_rate": round((len(wins) / len(symbol_trades) * 100.0), 4)
                if symbol_trades
                else None,
                "avg_r": round(float(np.mean([trade.r_multiple for trade in symbol_trades])), 4)
                if symbol_trades
                else None,
            }
        )
    return snapshot


async def _build_benchmark_summary(
    db: AsyncSession,
    *,
    benchmark_symbol: str,
    timeframe: Timeframe,
    date_from: datetime | None,
    date_to: datetime | None,
    initial_capital: float,
) -> dict:
    if not benchmark_symbol:
        return {
            "symbol": None,
            "net_return_pct": None,
            "equity_curve": [],
            "coverage": {
                "symbol": None,
                "preview_note": "No benchmark configured.",
                "requested_status": "unconfigured",
                "available_from": None,
                "available_to": None,
                "requested_first_bar_at": None,
                "requested_last_bar_at": None,
                "total_bars": 0,
                "requested_bars": 0,
                "requested_fits_range": None,
            },
        }

    warnings: list[str] = []
    instruments = await _resolve_universe_instruments(db, {"symbols": [benchmark_symbol]}, warnings)
    if not instruments:
        return {
            "symbol": benchmark_symbol,
            "net_return_pct": None,
            "equity_curve": [],
            "coverage": {
                "symbol": benchmark_symbol,
                "preview_note": warnings[0] if warnings else "Benchmark could not be resolved.",
                "requested_status": "missing",
                "available_from": None,
                "available_to": None,
                "requested_first_bar_at": None,
                "requested_last_bar_at": None,
                "total_bars": 0,
                "requested_bars": 0,
                "requested_fits_range": None,
            },
        }

    coverage = await _build_benchmark_coverage_summary(
        db,
        benchmark_symbol=benchmark_symbol,
        timeframe=timeframe,
        date_from=date_from,
        date_to=date_to,
    )

    bars = await _load_bars_for_strategy(
        db,
        instrument_id=instruments[0].id,
        timeframe=timeframe,
        date_from=date_from,
        date_to=date_to,
    )
    if len(bars) < 2:
        return {
            "symbol": benchmark_symbol,
            "net_return_pct": None,
            "equity_curve": [],
            "coverage": coverage,
        }

    first_close = float(bars[0].close)
    if first_close <= 0:
        return {
            "symbol": benchmark_symbol,
            "net_return_pct": None,
            "equity_curve": [],
            "coverage": coverage,
        }

    curve = [
        {
            "ts": bar.ts.isoformat(),
            "equity": round(initial_capital * (float(bar.close) / first_close), 4),
        }
        for bar in bars
    ]
    ending = float(curve[-1]["equity"])
    quantity = round(initial_capital / first_close, 8) if first_close > 0 else 0.0
    position_timeline = {
        "position_id": f"{benchmark_symbol}-buy-hold",
        "label": f"{benchmark_symbol} buy & hold",
        "symbol": benchmark_symbol,
        "side": "long",
        "entry_at": bars[0].ts.isoformat(),
        "exit_at": None,
        "current_at": bars[-1].ts.isoformat(),
        "entry_price": round(first_close, 4),
        "current_price": round(float(bars[-1].close), 4),
        "quantity": quantity,
        "pnl": round(ending - initial_capital, 4),
        "pnl_pct": round(((ending - initial_capital) / initial_capital) * 100.0, 4)
        if initial_capital > 0
        else None,
        "status": "open_at_end",
        "points": [
            {
                "ts": row["ts"],
                "value": round(float(row["equity"]) - initial_capital, 4),
                "detail": (
                    f"Entry · {benchmark_symbol} LONG · {quantity:.2f} @ {first_close:.2f}"
                    if index == 0
                    else (
                        f"Open · mark {float(bars[-1].close):.2f} · {(((ending - initial_capital) / initial_capital) * 100.0):.2f}%"
                        if index == len(curve) - 1
                        else None
                    )
                ),
                "marker": "entry" if index == 0 else ("open_at_end" if index == len(curve) - 1 else None),
            }
            for index, row in enumerate(curve)
        ],
    }
    execution_log = [
        {
            "ts": bars[0].ts.isoformat(),
            "event_type": "entry",
            "position_id": f"{benchmark_symbol}-buy-hold",
            "symbol": benchmark_symbol,
            "side": "long",
            "quantity": quantity,
            "price": round(first_close, 4),
            "notional": round(initial_capital, 4),
            "pnl": None,
            "pnl_pct": None,
            "r_multiple": None,
            "reason": "buy_and_hold_entry",
        },
        {
            "ts": bars[-1].ts.isoformat(),
            "event_type": "open_at_end",
            "position_id": f"{benchmark_symbol}-buy-hold",
            "symbol": benchmark_symbol,
            "side": "long",
            "quantity": quantity,
            "price": round(float(bars[-1].close), 4),
            "notional": round(float(curve[-1]["equity"]), 4),
            "pnl": round(ending - initial_capital, 4),
            "pnl_pct": round(((ending - initial_capital) / initial_capital) * 100.0, 4)
            if initial_capital > 0
            else None,
            "r_multiple": None,
            "reason": "buy_and_hold_mark",
        },
    ]
    portfolio_timeline = [
        {
            "ts": row["ts"],
            "equity": row["equity"],
            "deployed_capital": row["equity"],
            "idle_capital": 0.0,
            "open_position_count": 1,
        }
        for row in curve
    ]
    drawdown_curve = _drawdown_curve(curve)
    return {
        "symbol": benchmark_symbol,
        "net_return_pct": round(((ending - initial_capital) / initial_capital * 100.0), 4),
        "equity_curve": curve,
        "drawdown_curve": drawdown_curve,
        "position_timeline": position_timeline,
        "execution_log": execution_log,
        "portfolio_timeline": portfolio_timeline,
        "performance": {
            "initial_capital": round(initial_capital, 4),
            "ending_capital": round(ending, 4),
            "net_return_pct": round(((ending - initial_capital) / initial_capital * 100.0), 4),
            "max_drawdown_pct": _max_drawdown_pct(curve),
        },
        "coverage": coverage,
    }
