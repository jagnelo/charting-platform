from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.strategy import (
    StrategyDefinition,
    StrategyEngineType,
    StrategyRun,
    StrategyRunStatus,
    StrategyVersion,
)
from app.schemas.strategy import StrategyEngineCapabilityOut

ENGINE_CAPABILITIES: dict[str, StrategyEngineCapabilityOut] = {
    StrategyEngineType.PLATFORM.value: StrategyEngineCapabilityOut(
        key=StrategyEngineType.PLATFORM.value,
        label="Platform Engine",
        is_available=True,
        supports_walk_forward=True,
        supports_paper_forward=True,
        notes="Initial in-platform engine for persisted runs, research bookkeeping, and data-coverage validation.",
    ),
    StrategyEngineType.NAUTILUS.value: StrategyEngineCapabilityOut(
        key=StrategyEngineType.NAUTILUS.value,
        label="Nautilus Trader",
        is_available=False,
        supports_walk_forward=True,
        supports_paper_forward=True,
        notes="Planned integration target for richer simulation and execution modeling.",
    ),
}


def list_strategy_engines() -> list[StrategyEngineCapabilityOut]:
    return list(ENGINE_CAPABILITIES.values())


def get_strategy_engine(engine_type: str) -> StrategyEngineCapabilityOut:
    capability = ENGINE_CAPABILITIES.get(engine_type)
    if capability is None:
        raise ValueError(f"Unknown strategy engine '{engine_type}'")
    return capability


async def execute_strategy_run(
    db: AsyncSession,
    *,
    strategy: StrategyDefinition,
    version: StrategyVersion,
    run: StrategyRun,
) -> StrategyRun:
    capability = get_strategy_engine(run.engine_type)
    if not capability.is_available:
        raise ValueError(f"Engine '{run.engine_type}' is not available yet")

    run.status = StrategyRunStatus.RUNNING.value
    run.started_at = datetime.now(UTC)
    await db.flush()

    try:
        run.result_summary = await _run_platform_foundation(
            db, strategy=strategy, version=version, run=run
        )
        run.status = StrategyRunStatus.COMPLETED.value
        run.completed_at = datetime.now(UTC)
        run.engine_run_ref = f"{run.engine_type}:{run.id}"
        run.artifact_manifest = {
            "result_kind": "foundation_research_snapshot",
            "supports_execution_stats": False,
        }
    except Exception as exc:
        run.status = StrategyRunStatus.FAILED.value
        run.completed_at = datetime.now(UTC)
        run.error_log = str(exc)
        raise

    await db.flush()
    return run


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
    instrument_rows = await _resolve_universe_instruments(db, effective_universe, warnings)
    instrument_ids = [row.id for row in instrument_rows]
    symbols = [row.symbol for row in instrument_rows]

    timeframe_value = (
        run.timeframe or version.definition_snapshot.get("timeframe") or Timeframe.D1.value
    )
    try:
        timeframe = Timeframe(str(timeframe_value))
    except ValueError:
        timeframe = Timeframe.D1
        warnings.append(f"Unknown timeframe '{timeframe_value}' requested; defaulted to D1.")
    bars_stmt = select(
        OHLCVBar.instrument_id,
        func.count(OHLCVBar.id),
        func.min(OHLCVBar.ts),
        func.max(OHLCVBar.ts),
    ).where(OHLCVBar.timeframe == timeframe)
    if instrument_ids:
        bars_stmt = bars_stmt.where(OHLCVBar.instrument_id.in_(instrument_ids))
    else:
        bars_stmt = bars_stmt.where(False)
    if run.date_from is not None:
        bars_stmt = bars_stmt.where(OHLCVBar.ts >= run.date_from)
    if run.date_to is not None:
        bars_stmt = bars_stmt.where(OHLCVBar.ts <= run.date_to)
    bars_stmt = bars_stmt.group_by(OHLCVBar.instrument_id)

    coverage_rows = (await db.execute(bars_stmt)).all()
    total_bars = sum(int(row[1]) for row in coverage_rows)
    instruments_with_data = len(coverage_rows)
    first_bar_at = min((row[2] for row in coverage_rows if row[2] is not None), default=None)
    last_bar_at = max((row[3] for row in coverage_rows if row[3] is not None), default=None)

    if not instrument_ids:
        warnings.append("No instruments resolved from the current universe config.")
    if total_bars == 0:
        warnings.append("No OHLCV coverage was found for the requested timeframe/date range.")
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
        "engine_type": run.engine_type,
        "universe": {
            "requested": effective_universe,
            "resolved_instrument_count": len(instrument_ids),
            "resolved_symbols": symbols[:25],
            "truncated_symbol_count": max(0, len(symbols) - 25),
        },
        "coverage": {
            "instruments_with_data": instruments_with_data,
            "instrument_count": len(instrument_ids),
            "total_bars": total_bars,
            "first_bar_at": first_bar_at.isoformat() if first_bar_at else None,
            "last_bar_at": last_bar_at.isoformat() if last_bar_at else None,
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
            "has_coverage": total_bars > 0,
            "requires_simulation_engine": True,
        },
        "warnings": warnings,
    }


async def _resolve_universe_instruments(
    db: AsyncSession,
    universe_config: dict,
    warnings: list[str],
) -> list[Instrument]:
    instrument_ids = [
        int(value) for value in universe_config.get("instrument_ids", []) if value is not None
    ]
    symbols = [
        str(value).upper() for value in universe_config.get("symbols", []) if str(value).strip()
    ]

    if universe_config.get("watchlist_id") is not None:
        warnings.append("Watchlist-backed strategy universes are not wired into Strategy Lab yet.")

    if instrument_ids:
        stmt = (
            select(Instrument).where(Instrument.id.in_(instrument_ids)).order_by(Instrument.symbol)
        )
        return list((await db.execute(stmt)).scalars().all())

    if symbols:
        stmt = (
            select(Instrument)
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
