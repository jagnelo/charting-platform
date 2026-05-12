from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.strategy import (
    StrategyDefinition,
    StrategyRun,
    StrategyRunStatus,
    StrategyVersion,
)
from app.services.strategy_lab_nautilus import (
    NautilusTrade,
    run_single_instrument_nautilus_backtest,
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

    try:
        if strategy.definition_type == "rules":
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
            "supports_execution_stats": result_kind == "rules_backtest",
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


async def _run_rules_backtest(
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
    symbol_curves: list[list[dict[str, float | str]]] = []

    initial_capital = float(run.execution_assumptions.get("initial_capital", 100000))
    risk_per_trade_pct = float(run.execution_assumptions.get("risk_per_trade_pct", 1.0))
    slippage_bps = float(run.execution_assumptions.get("slippage_bps", 5))
    commission_per_trade = float(run.execution_assumptions.get("commission_per_trade", 0))
    stop_loss_pct = float(definition.get("risk", {}).get("stop_loss_pct", 3))
    take_profit_rr = float(definition.get("risk", {}).get("take_profit_rr", 2))
    max_bars_in_trade = int(definition.get("risk", {}).get("max_bars_in_trade", 20))
    direction = str(definition.get("direction", "long")).lower()
    logic = str(definition.get("entry_logic", "all")).lower()
    conditions = list(definition.get("conditions", []))

    if not conditions:
        warnings.append("No entry conditions were defined; no trades can be simulated.")

    if len(instrument_rows) > 1:
        warnings.append(
            "Multi-symbol runs currently use equal capital slices per symbol before results are recombined."
        )

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
        covered_symbols.append(instrument.symbol)
        coverage_total_bars += len(bars)
        instrument_result = run_single_instrument_nautilus_backtest(
            instrument=instrument,
            bars=bars,
            timeframe=timeframe,
            direction=direction,
            entry_logic=logic,
            conditions=conditions,
            stop_loss_pct=stop_loss_pct,
            take_profit_rr=take_profit_rr,
            max_bars_in_trade=max_bars_in_trade,
            capital_base=capital_slice,
            risk_per_trade_pct=risk_per_trade_pct,
            slippage_bps=slippage_bps,
            commission_per_trade=commission_per_trade,
        )
        trades.extend(instrument_result.trades)
        symbol_curves.append(instrument_result.equity_curve)
        warnings.extend(instrument_result.warnings)

    trades.sort(key=lambda trade: (trade.exit_at, trade.instrument_symbol, trade.entry_at))
    equity_curve = _merge_equity_curves(
        symbol_curves=symbol_curves,
        initial_capital=initial_capital,
        capital_slice=capital_slice,
        fallback_ts=run.date_from.isoformat() if run.date_from else datetime.now(UTC).isoformat(),
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
        "execution_assumptions": {
            "initial_capital": initial_capital,
            "risk_per_trade_pct": risk_per_trade_pct,
            "slippage_bps": slippage_bps,
            "commission_per_trade": commission_per_trade,
            "stop_loss_pct": stop_loss_pct,
            "take_profit_rr": take_profit_rr,
            "max_bars_in_trade": max_bars_in_trade,
        },
        "equity_curve": equity_curve,
        "symbol_performance": _symbol_performance_snapshot(trades),
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


def _merge_equity_curves(
    *,
    symbol_curves: list[list[dict[str, float | str]]],
    initial_capital: float,
    capital_slice: float,
    fallback_ts: str,
) -> list[dict[str, float | str]]:
    if not symbol_curves:
        return [{"ts": fallback_ts, "equity": round(initial_capital, 4)}]

    all_timestamps = sorted({str(point["ts"]) for curve in symbol_curves for point in curve})
    merged: list[dict[str, float | str]] = []
    last_values = [capital_slice for _ in symbol_curves]
    indices = [0 for _ in symbol_curves]

    for ts in all_timestamps:
        total = 0.0
        for curve_index, curve in enumerate(symbol_curves):
            while (
                indices[curve_index] < len(curve) and str(curve[indices[curve_index]]["ts"]) <= ts
            ):
                last_values[curve_index] = float(curve[indices[curve_index]]["equity"])
                indices[curve_index] += 1
            total += last_values[curve_index]
        merged.append({"ts": ts, "equity": round(total, 4)})
    return merged


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
