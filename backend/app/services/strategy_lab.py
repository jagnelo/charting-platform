from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.radar import (
    RadarDetection,
    RadarSetupType,
    RadarState,
)
from app.models.screener import ScreenerDefinition, ScreenerResult
from app.models.strategy import (
    StrategyDefinition,
    StrategyEngineType,
    StrategyRun,
    StrategyRunStatus,
    StrategyVersion,
)
from app.models.watchlist import Watchlist, WatchlistItem
from app.services.strategy_lab_nautilus import (
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

    watchlist_id = universe_config.get("watchlist_id")
    screener_id = universe_config.get("screener_id")
    if watchlist_id is not None:
        watchlist = await db.get(Watchlist, int(watchlist_id))
        if watchlist is None:
            warnings.append(f"Watchlist {watchlist_id} could not be found.")
            return []
        stmt = (
            select(Instrument)
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
        stmt = select(Instrument).where(Instrument.id.in_(matched_ids)).order_by(Instrument.symbol)
        return list((await db.execute(stmt)).scalars().all())

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


def _apply_portfolio_constraints(
    trades: list[NautilusTrade],
    *,
    initial_capital: float,
    max_concurrent_positions: int,
    max_portfolio_risk_pct: float,
    max_symbol_allocation_pct: float,
    fallback_ts: str,
) -> dict[str, Any]:
    accepted: list[NautilusTrade] = []
    rejected: list[dict[str, Any]] = []
    open_positions: list[dict[str, Any]] = []
    peak_concurrent = 0

    for trade in sorted(
        trades, key=lambda item: (_parse_iso_datetime(item.entry_at), item.instrument_symbol)
    ):
        entry_dt = _parse_iso_datetime(trade.entry_at)
        open_positions = [
            position
            for position in open_positions
            if _parse_iso_datetime(position["exit_at"]) > entry_dt
        ]

        notional = abs(float(trade.quantity) * float(trade.entry_price))
        risk_amount = abs(float(trade.entry_price) - float(trade.stop_price)) * float(
            trade.quantity
        )
        risk_pct = (risk_amount / initial_capital * 100.0) if initial_capital > 0 else 0.0
        allocation_pct = (notional / initial_capital * 100.0) if initial_capital > 0 else 0.0
        reserved_notional = sum(float(position["notional"]) for position in open_positions)
        reserved_risk_pct = sum(float(position["risk_pct"]) for position in open_positions)

        rejection_reason = None
        if len(open_positions) >= max(1, max_concurrent_positions):
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
                    "instrument_symbol": trade.instrument_symbol,
                    "entry_at": trade.entry_at,
                    "reason": rejection_reason,
                    "risk_pct": round(risk_pct, 4),
                    "allocation_pct": round(allocation_pct, 4),
                }
            )
            continue

        accepted.append(trade)
        open_positions.append(
            {
                "exit_at": trade.exit_at,
                "risk_pct": risk_pct,
                "notional": notional,
            }
        )
        peak_concurrent = max(peak_concurrent, len(open_positions))

    return {
        "accepted_trades": accepted,
        "rejected_trades": rejected,
        "equity_curve": _build_portfolio_equity_curve(
            accepted,
            initial_capital=initial_capital,
            fallback_ts=fallback_ts,
        ),
        "summary": {
            "accepted_trade_count": len(accepted),
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

    definition = dict(version.definition_snapshot or {})
    effective_universe = dict(version.universe_config or {})
    effective_universe.update(run.universe_config or {})
    warnings: list[str] = []

    timeframe_value = run.timeframe or definition.get("timeframe") or Timeframe.D1.value
    try:
        timeframe = Timeframe(str(timeframe_value))
    except ValueError:
        timeframe = Timeframe.D1
        warnings.append(f"Unknown timeframe '{timeframe_value}' requested; defaulted to D1.")

    instrument_rows = await _resolve_universe_instruments(db, effective_universe, warnings)
    trades: list[NautilusTrade] = []
    coverage_total_bars = 0
    covered_symbols: list[str] = []

    initial_capital = float(run.execution_assumptions.get("initial_capital", 100000))
    risk_per_trade_pct = float(run.execution_assumptions.get("risk_per_trade_pct", 1.0))
    slippage_bps = float(run.execution_assumptions.get("slippage_bps", 5))
    commission_per_trade = float(run.execution_assumptions.get("commission_per_trade", 0))
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
    stop_loss_pct = float(definition.get("risk", {}).get("stop_loss_pct", 3))
    take_profit_rr = float(definition.get("risk", {}).get("take_profit_rr", 2))
    max_bars_in_trade = int(definition.get("risk", {}).get("max_bars_in_trade", 20))
    break_even_rr = float(definition.get("risk", {}).get("break_even_rr", 0))
    trailing_stop_rr = float(definition.get("risk", {}).get("trailing_stop_rr", 0))
    pyramiding_max_entries = int(definition.get("risk", {}).get("pyramiding_max_entries", 1))
    direction = str(definition.get("direction", "long")).lower()
    logic = str(definition.get("entry_logic", "all")).lower()
    conditions = list(definition.get("conditions", []))
    condition_tree = definition.get("condition_tree")
    condition_types = _condition_types_used(conditions, condition_tree if isinstance(condition_tree, dict) else None)
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
        if len(bars) < 3:
            warnings.append(f"{instrument.symbol} does not have enough bars for simulation.")
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
        covered_symbols.append(instrument.symbol)
        coverage_total_bars += len(bars)
        instrument_result = run_single_instrument_nautilus_backtest(
            instrument=instrument,
            bars=bars,
            timeframe=timeframe,
            direction=direction,
            entry_logic=logic,
            conditions=conditions,
            condition_tree=condition_tree if isinstance(condition_tree, dict) else None,
            signal_events=None,
            stop_loss_pct=stop_loss_pct,
            take_profit_rr=take_profit_rr,
            max_bars_in_trade=max_bars_in_trade,
            capital_base=capital_slice,
            risk_per_trade_pct=risk_per_trade_pct,
            slippage_bps=slippage_bps,
            commission_per_trade=commission_per_trade,
            break_even_rr=break_even_rr,
            trailing_stop_rr=trailing_stop_rr,
            pyramiding_max_entries=pyramiding_max_entries,
            daily_bars=daily_bars,
            weekly_bars=weekly_bars,
            instrument_context=_build_instrument_context(instrument),
        )
        trades.extend(instrument_result.trades)
        warnings.extend(instrument_result.warnings)

    portfolio_view = _apply_portfolio_constraints(
        trades,
        initial_capital=initial_capital,
        max_concurrent_positions=max_concurrent_positions,
        max_portfolio_risk_pct=max_portfolio_risk_pct,
        max_symbol_allocation_pct=max_symbol_allocation_pct,
        fallback_ts=run.date_from.isoformat() if run.date_from else datetime.now(UTC).isoformat(),
    )
    trades = list(portfolio_view["accepted_trades"])
    rejected_trades = list(portfolio_view["rejected_trades"])
    equity_curve = list(portfolio_view["equity_curve"])
    if rejected_trades:
        warnings.append(f"{len(rejected_trades)} trades were rejected by portfolio controls.")

    wins = [trade for trade in trades if trade.pnl > 0]
    losses = [trade for trade in trades if trade.pnl <= 0]
    total_wins = sum(trade.pnl for trade in wins)
    total_losses = abs(sum(trade.pnl for trade in losses))
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
        commission_per_trade=commission_per_trade,
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
            "instruments_with_data": len(covered_symbols),
            "instrument_count": len(instrument_rows),
            "total_bars": coverage_total_bars,
            "requested_date_from": run.date_from.isoformat() if run.date_from else None,
            "requested_date_to": run.date_to.isoformat() if run.date_to else None,
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
            "slippage_bps": slippage_bps,
            "commission_per_trade": commission_per_trade,
            "stop_loss_pct": stop_loss_pct,
            "take_profit_rr": take_profit_rr,
            "max_bars_in_trade": max_bars_in_trade,
            "break_even_rr": break_even_rr,
            "trailing_stop_rr": trailing_stop_rr,
            "pyramiding_max_entries": pyramiding_max_entries,
            "max_concurrent_positions": max_concurrent_positions,
            "max_portfolio_risk_pct": max_portfolio_risk_pct,
            "max_symbol_allocation_pct": max_symbol_allocation_pct,
        },
        "equity_curve": equity_curve,
        "analytics": analytics,
        "portfolio": portfolio_view["summary"],
        "symbol_performance": _symbol_performance_snapshot(trades),
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
    definition = dict(version.definition_snapshot or {})
    effective_universe = dict(version.universe_config or {})
    effective_universe.update(run.universe_config or {})
    warnings: list[str] = []

    radar_filters = dict(definition.get("radar_filters") or {})
    timeframe_value = run.timeframe or radar_filters.get("timeframe") or Timeframe.D1.value
    try:
        timeframe = Timeframe(str(timeframe_value))
    except ValueError:
        timeframe = Timeframe.D1
        warnings.append(f"Unknown timeframe '{timeframe_value}' requested; defaulted to D1.")

    setup_types = _normalize_radar_filter_values(radar_filters.get("setup_types"), RadarSetupType)
    states = _normalize_radar_filter_values(radar_filters.get("states"), RadarState)
    min_score = float(radar_filters.get("min_score", 0.0) or 0.0)

    explicit_universe = any(
        effective_universe.get(key) not in (None, [], "")
        for key in ("instrument_ids", "symbols", "watchlist_id", "screener_id")
    )
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
                    .order_by(Instrument.symbol.asc())
                )
            )
            .scalars()
            .all()
        )
        instrument_rows = list(loaded_instruments)

    initial_capital = float(run.execution_assumptions.get("initial_capital", 100000))
    risk_per_trade_pct = float(run.execution_assumptions.get("risk_per_trade_pct", 1.0))
    slippage_bps = float(run.execution_assumptions.get("slippage_bps", 5))
    commission_per_trade = float(run.execution_assumptions.get("commission_per_trade", 0))
    stop_loss_pct = float(definition.get("risk", {}).get("stop_loss_pct", 3))
    take_profit_rr = float(definition.get("risk", {}).get("take_profit_rr", 2))
    max_bars_in_trade = int(definition.get("risk", {}).get("max_bars_in_trade", 20))
    break_even_rr = float(definition.get("risk", {}).get("break_even_rr", 0))
    trailing_stop_rr = float(definition.get("risk", {}).get("trailing_stop_rr", 0))
    pyramiding_max_entries = int(definition.get("risk", {}).get("pyramiding_max_entries", 1))
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
    coverage_total_bars = 0
    covered_symbols: list[str] = []

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
        coverage_total_bars += len(bars)
        covered_symbols.append(instrument.symbol)
        instrument_result = run_single_instrument_nautilus_backtest(
            instrument=instrument,
            bars=bars,
            timeframe=timeframe,
            direction="long",
            entry_logic="all",
            conditions=[],
            condition_tree=None,
            stop_loss_pct=stop_loss_pct,
            take_profit_rr=take_profit_rr,
            max_bars_in_trade=max_bars_in_trade,
            capital_base=capital_slice,
            risk_per_trade_pct=risk_per_trade_pct,
            slippage_bps=slippage_bps,
            commission_per_trade=commission_per_trade,
            break_even_rr=break_even_rr,
            trailing_stop_rr=trailing_stop_rr,
            pyramiding_max_entries=pyramiding_max_entries,
            signal_events=signal_events,
        )
        trades.extend(instrument_result.trades)
        warnings.extend(instrument_result.warnings)

    portfolio_view = _apply_portfolio_constraints(
        trades,
        initial_capital=initial_capital,
        max_concurrent_positions=max_concurrent_positions,
        max_portfolio_risk_pct=max_portfolio_risk_pct,
        max_symbol_allocation_pct=max_symbol_allocation_pct,
        fallback_ts=run.date_from.isoformat() if run.date_from else datetime.now(UTC).isoformat(),
    )
    trades = list(portfolio_view["accepted_trades"])
    rejected_trades = list(portfolio_view["rejected_trades"])
    equity_curve = list(portfolio_view["equity_curve"])
    if rejected_trades:
        warnings.append(
            f"{len(rejected_trades)} replayed signals were rejected by portfolio controls."
        )
    wins = [trade for trade in trades if trade.pnl > 0]
    losses = [trade for trade in trades if trade.pnl <= 0]
    total_wins = sum(trade.pnl for trade in wins)
    total_losses = abs(sum(trade.pnl for trade in losses))
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
            "instruments_with_data": len(covered_symbols),
            "instrument_count": len(instrument_rows),
            "total_bars": coverage_total_bars,
            "requested_date_from": run.date_from.isoformat() if run.date_from else None,
            "requested_date_to": run.date_to.isoformat() if run.date_to else None,
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
            "slippage_bps": slippage_bps,
            "commission_per_trade": commission_per_trade,
            "stop_loss_pct": stop_loss_pct,
            "take_profit_rr": take_profit_rr,
            "max_bars_in_trade": max_bars_in_trade,
            "break_even_rr": break_even_rr,
            "trailing_stop_rr": trailing_stop_rr,
            "pyramiding_max_entries": pyramiding_max_entries,
            "max_concurrent_positions": max_concurrent_positions,
            "max_portfolio_risk_pct": max_portfolio_risk_pct,
            "max_symbol_allocation_pct": max_symbol_allocation_pct,
        },
        "equity_curve": equity_curve,
        "analytics": analytics,
        "portfolio": portfolio_view["summary"],
        "symbol_performance": _symbol_performance_snapshot(trades),
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
    commission_per_trade: float,
) -> dict | None:
    config = dict(run.execution_assumptions.get("optimization") or {})
    if not config.get("enabled"):
        return None
    stop_values = config.get("stop_loss_pct_values") or [
        definition.get("risk", {}).get("stop_loss_pct", 3)
    ]
    target_values = config.get("take_profit_rr_values") or [
        definition.get("risk", {}).get("take_profit_rr", 2)
    ]
    bar_values = config.get("max_bars_in_trade_values") or [
        definition.get("risk", {}).get("max_bars_in_trade", 20)
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
    condition_types = _condition_types_used(
        conditions,
        condition_tree if isinstance(condition_tree, dict) else None,
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
                signal_events=None,
                stop_loss_pct=combo["stop_loss_pct"],
                take_profit_rr=combo["take_profit_rr"],
                max_bars_in_trade=combo["max_bars_in_trade"],
                capital_base=capital_slice,
                risk_per_trade_pct=risk_per_trade_pct,
                slippage_bps=slippage_bps,
                commission_per_trade=commission_per_trade,
                break_even_rr=float(definition.get("risk", {}).get("break_even_rr", 0)),
                trailing_stop_rr=float(definition.get("risk", {}).get("trailing_stop_rr", 0)),
                pyramiding_max_entries=int(
                    definition.get("risk", {}).get("pyramiding_max_entries", 1)
                ),
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
) -> list[dict[str, float | int | str | None]]:
    grouped: dict[str, list[NautilusTrade]] = {}
    for trade in trades:
        grouped.setdefault(trade.instrument_symbol, []).append(trade)

    snapshot: list[dict[str, float | int | str | None]] = []
    for symbol, symbol_trades in sorted(grouped.items()):
        wins = [trade for trade in symbol_trades if trade.pnl > 0]
        snapshot.append(
            {
                "symbol": symbol,
                "trade_count": len(symbol_trades),
                "net_pnl": round(sum(trade.pnl for trade in symbol_trades), 4),
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
        return {"symbol": None, "net_return_pct": None, "equity_curve": []}

    warnings: list[str] = []
    instruments = await _resolve_universe_instruments(db, {"symbols": [benchmark_symbol]}, warnings)
    if not instruments:
        return {"symbol": benchmark_symbol, "net_return_pct": None, "equity_curve": []}

    bars = await _load_bars_for_strategy(
        db,
        instrument_id=instruments[0].id,
        timeframe=timeframe,
        date_from=date_from,
        date_to=date_to,
    )
    if len(bars) < 2:
        return {"symbol": benchmark_symbol, "net_return_pct": None, "equity_curve": []}

    first_close = float(bars[0].close)
    if first_close <= 0:
        return {"symbol": benchmark_symbol, "net_return_pct": None, "equity_curve": []}

    curve = [
        {
            "ts": bar.ts.isoformat(),
            "equity": round(initial_capital * (float(bar.close) / first_close), 4),
        }
        for bar in bars
    ]
    ending = float(curve[-1]["equity"])
    return {
        "symbol": benchmark_symbol,
        "net_return_pct": round(((ending - initial_capital) / initial_capital * 100.0), 4),
        "equity_curve": curve,
    }
