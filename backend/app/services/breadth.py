"""Provider-neutral, reusable cross-sectional breadth evaluation.

The legacy breadth endpoint exposes a useful fixed panel.  This module is the
small, deterministic engine underneath the broader workstation contract:
evaluate one declared condition for every member of a declared universe and
return an honest denominator, coverage, and exclusion ledger.  It deliberately
accepts already-materialised local bars; provider access and universe
resolution stay at the router/service boundary.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class BreadthMember:
    instrument_id: int
    symbol: str
    name: str


@dataclass(frozen=True)
class BreadthMemberResult:
    instrument_id: int
    symbol: str
    name: str
    value: bool | None
    metric: float | None
    observation_time: datetime | None
    exclusion_code: str | None = None


def normalized_definition(definition: Mapping[str, Any]) -> dict[str, Any]:
    """Return a JSON-stable definition for hashing and cache identity."""

    return json.loads(json.dumps(definition, sort_keys=True, separators=(",", ":"), default=str))


def definition_hash(
    definition: Mapping[str, Any],
    *,
    membership_version: int | str,
    dataset_version: str = "local-v1",
) -> str:
    payload = {
        "definition": normalized_definition(definition),
        "membership_version": str(membership_version),
        "dataset_version": dataset_version,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _close_values(bars: list[Any]) -> list[float] | None:
    values = [float(getattr(bar, "close", math.nan)) for bar in bars]
    return values if all(math.isfinite(value) for value in values) else None


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _ema(values: list[float], period: int) -> float:
    alpha = 2 / (period + 1)
    current = _mean(values[:period])
    for value in values[period:]:
        current = (value * alpha) + (current * (1 - alpha))
    return current


def _comparison(metric: float, params: Mapping[str, Any]) -> bool:
    comparator = str(params.get("operator", params.get("comparator", "above"))).lower()
    threshold = float(params.get("threshold", 0.0))
    if comparator in {"below", "lt", "<"}:
        return metric < threshold
    if comparator in {"at_or_below", "lte", "<="}:
        return metric <= threshold
    if comparator in {"at_or_above", "gte", ">="}:
        return metric >= threshold
    if comparator in {"equal", "eq", "=="}:
        return metric == threshold
    if comparator in {"not_equal", "neq", "ne", "!="}:
        return metric != threshold
    return metric > threshold


def _nested_conditions(params: Mapping[str, Any]) -> list[Mapping[str, Any]] | None:
    raw = params.get("conditions")
    if not isinstance(raw, list) or not raw or any(not isinstance(item, Mapping) for item in raw):
        return None
    return [item for item in raw if isinstance(item, Mapping)]


def _comparison_metric(
    bars: list[Any],
    field: str,
    params: Mapping[str, Any],
    *,
    benchmark_bars: list[Any] | None,
) -> tuple[float | None, str | None]:
    """Resolve a scalar field for the generic comparison condition.

    The field vocabulary deliberately stays platform-owned. User-authored Python
    remains in the isolated research runner; this endpoint only evaluates
    deterministic fields over already-materialised local bars.
    """

    normalized = field.lower().strip()
    closes = _close_values(bars)
    if closes is None or not closes:
        return None, "invalid_close"
    latest = closes[-1]
    if normalized in {"close", "price", "last"}:
        return latest, None
    if normalized in {"return", "return_1"}:
        if len(closes) < 2 or closes[-2] == 0:
            return None, "insufficient_history"
        return latest / closes[-2] - 1, None
    if normalized in {"distance_to_52w_high", "distance_to_52_week_high"}:
        lookback = int(params.get("lookback", 252))
        if lookback < 2 or len(closes) < lookback:
            return None, "insufficient_history"
        reference = max(closes[-lookback:])
        if reference <= 0:
            return None, "invalid_reference"
        return latest / reference - 1, None
    if normalized in {"distance_to_52w_low", "distance_to_52_week_low"}:
        lookback = int(params.get("lookback", 252))
        if lookback < 2 or len(closes) < lookback:
            return None, "insufficient_history"
        reference = min(closes[-lookback:])
        if reference <= 0:
            return None, "invalid_reference"
        return latest / reference - 1, None
    if normalized == "volume":
        volumes = [getattr(bar, "volume", None) for bar in bars]
        if not volumes or not _finite(volumes[-1]):
            return None, "missing_volume"
        return float(volumes[-1]), None
    if normalized in {"moving_average_distance", "ma_distance"}:
        _, metric, warning = evaluate_condition(
            bars,
            {
                "kind": "above_moving_average",
                "params": {
                    "period": params.get("period", 200),
                    "average": params.get("average", "sma"),
                },
            },
            benchmark_bars=benchmark_bars,
        )
        return metric, warning
    if normalized == "rsi":
        _, metric, warning = evaluate_condition(
            bars,
            {"kind": "rsi", "params": {"period": params.get("period", 14)}},
            benchmark_bars=benchmark_bars,
        )
        return metric, warning
    if normalized == "trend":
        _, metric, warning = evaluate_condition(
            bars,
            {
                "kind": "trend",
                "params": {
                    "fast_period": params.get("fast_period", 20),
                    "slow_period": params.get("slow_period", 50),
                    "direction": params.get("direction", "up"),
                },
            },
            benchmark_bars=benchmark_bars,
        )
        return metric, warning
    if normalized == "volume_ratio":
        _, metric, warning = evaluate_condition(
            bars,
            {
                "kind": "volume_ratio",
                "params": {"period": params.get("period", 50), "threshold": 0},
            },
            benchmark_bars=benchmark_bars,
        )
        return metric, warning
    if normalized in {"relative_strength", "relative_return"}:
        _, metric, warning = evaluate_condition(
            bars,
            {"kind": "relative_strength", "params": {"lookback": params.get("lookback", 20)}},
            benchmark_bars=benchmark_bars,
        )
        return metric, warning
    return None, "unsupported_field"


def evaluate_condition(
    bars: list[Any],
    condition: Mapping[str, Any],
    *,
    benchmark_bars: list[Any] | None = None,
) -> tuple[bool | None, float | None, str | None]:
    """Evaluate a supported condition at the last available bar.

    The returned metric is the transparent numeric quantity used for the
    Boolean decision.  ``None`` is never coerced to false: it is an explicit
    exclusion from the eligible denominator.
    """

    kind = str(condition.get("kind", "")).lower()
    params = condition.get("params", condition)
    if not isinstance(params, Mapping):
        return None, None, "invalid_condition_params"
    if not bars:
        return None, None, "no_bars"
    closes = _close_values(bars)
    if closes is None:
        return None, None, "invalid_close"
    latest = closes[-1]
    if not _finite(latest):
        return None, None, "invalid_close"

    if kind in {"all", "any"}:
        children = _nested_conditions(params)
        if children is None:
            return None, None, "invalid_condition_params"
        evaluated = [
            evaluate_condition(bars, child, benchmark_bars=benchmark_bars) for child in children
        ]
        if kind == "all":
            for index, (value, _, warning) in enumerate(evaluated):
                if value is None:
                    return None, None, f"condition_clause_excluded:{index}:{warning or 'unknown'}"
            metrics = [metric for _, metric, _ in evaluated if metric is not None]
            return all(value is True for value, _, _ in evaluated), min(metrics) if metrics else None, None
        if any(value is True for value, _, _ in evaluated):
            metrics = [metric for value, metric, _ in evaluated if value is True and metric is not None]
            return True, max(metrics) if metrics else None, None
        if all(value is False for value, _, _ in evaluated):
            metrics = [metric for _, metric, _ in evaluated if metric is not None]
            return False, max(metrics) if metrics else None, None
        for index, (value, _, warning) in enumerate(evaluated):
            if value is None:
                return None, None, f"condition_clause_excluded:{index}:{warning or 'unknown'}"

    if kind == "not":
        children = _nested_conditions(params)
        if children is None or len(children) != 1:
            return None, None, "invalid_condition_params"
        value, metric, warning = evaluate_condition(
            bars, children[0], benchmark_bars=benchmark_bars
        )
        if warning:
            return None, None, f"condition_clause_excluded:0:{warning}"
        return (not value) if value is not None else None, metric, None

    if kind == "comparison":
        field = params.get("field")
        if not isinstance(field, str) or not field.strip():
            return None, None, "invalid_condition_params"
        metric, warning = _comparison_metric(
            bars, field, params, benchmark_bars=benchmark_bars
        )
        if warning or metric is None:
            return None, metric, warning or "invalid_condition_params"
        return _comparison(metric, params), metric, None

    if kind == "above_moving_average":
        period = int(params.get("period", 200))
        if period < 2 or period > 252 or len(closes) < period:
            return None, None, "insufficient_history"
        window = closes[-period:]
        average_kind = str(params.get("average", "sma")).lower()
        average = _ema(window, period) if average_kind == "ema" else _mean(window)
        if not _finite(average) or average == 0:
            return None, None, "invalid_average"
        metric = latest / average - 1
        comparator = str(params.get("comparator", "above")).lower()
        return (latest > average if comparator == "above" else latest < average), metric, None

    if kind == "within_52_week_high":
        lookback = int(params.get("lookback", 252))
        threshold = float(params.get("threshold", 0.01))
        direction = str(params.get("direction", "high")).lower()
        if lookback < 2 or lookback > 504 or len(closes) < lookback:
            return None, None, "insufficient_history"
        window = closes[-lookback:]
        reference = max(window) if direction == "high" else min(window)
        if not _finite(reference) or reference <= 0:
            return None, None, "invalid_reference"
        distance = (latest / reference) - 1
        if direction == "low":
            return latest <= reference * (1 + threshold), abs(distance), None
        return latest >= reference * (1 - threshold), abs(distance), None

    if kind == "new_high_low":
        lookback = int(params.get("lookback", 20))
        direction = str(params.get("direction", "high")).lower()
        if lookback < 2 or lookback > 252 or len(closes) <= lookback:
            return None, None, "insufficient_history"
        previous = closes[-(lookback + 1) : -1]
        reference = max(previous) if direction == "high" else min(previous)
        metric = latest / reference - 1 if reference else math.nan
        if not _finite(metric):
            return None, None, "invalid_reference"
        return (latest >= reference if direction == "high" else latest <= reference), metric, None

    if kind == "trend":
        fast = int(params.get("fast_period", 20))
        slow = int(params.get("slow_period", 50))
        if fast < 2 or slow <= fast or slow > 252 or len(closes) < slow:
            return None, None, "insufficient_history"
        fast_average = _mean(closes[-fast:])
        slow_average = _mean(closes[-slow:])
        metric = latest / slow_average - 1 if slow_average else math.nan
        if not _finite(metric):
            return None, None, "invalid_average"
        direction = str(params.get("direction", "up")).lower()
        value = latest > slow_average and fast_average > slow_average
        return (value if direction in {"up", "uptrend", "above"} else not value), metric, None

    if kind == "rsi":
        period = int(params.get("period", 14))
        if period < 2 or period > 252 or len(closes) <= period:
            return None, None, "insufficient_history"
        changes = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
        gains = [max(change, 0.0) for change in changes[-period:]]
        losses = [max(-change, 0.0) for change in changes[-period:]]
        average_loss = _mean(losses)
        rsi = 100.0 if average_loss == 0 else 100 - (100 / (1 + (_mean(gains) / average_loss)))
        return _comparison(rsi, params), rsi, None

    if kind == "volume_ratio":
        period = int(params.get("period", 50))
        if period < 2 or period > 252 or len(bars) <= period:
            return None, None, "insufficient_history"
        volumes = [getattr(bar, "volume", None) for bar in bars]
        if any(not _finite(value) for value in volumes[-(period + 1) :]):
            return None, None, "missing_volume"
        baseline = _mean([float(value) for value in volumes[-(period + 1) : -1]])
        if baseline == 0:
            return None, None, "zero_average_volume"
        ratio = float(volumes[-1]) / baseline
        return _comparison(ratio, params), ratio, None

    if kind == "relative_strength":
        lookback = int(params.get("lookback", 20))
        if benchmark_bars is None:
            return None, None, "benchmark_required"
        benchmark_closes = _close_values(benchmark_bars)
        if benchmark_closes is None or len(closes) <= lookback or len(benchmark_closes) <= lookback:
            return None, None, "insufficient_history"
        member_base, benchmark_base = closes[-lookback - 1], benchmark_closes[-lookback - 1]
        if member_base == 0 or benchmark_base == 0:
            return None, None, "invalid_reference"
        metric = (latest / member_base - 1) - (benchmark_closes[-1] / benchmark_base - 1)
        return _comparison(metric, params), metric, None

    return None, None, "unsupported_condition"


def evaluate_breadth(
    members: list[BreadthMember],
    bars_by_instrument: Mapping[int, list[Any]],
    condition: Mapping[str, Any],
    *,
    benchmark_bars: list[Any] | None = None,
) -> tuple[list[BreadthMemberResult], dict[str, int | float]]:
    """Evaluate one condition across a universe and return aggregate metadata."""

    results: list[BreadthMemberResult] = []
    for member in members:
        bars = list(bars_by_instrument.get(member.instrument_id, []))
        value, metric, exclusion = evaluate_condition(
            bars, condition, benchmark_bars=benchmark_bars
        )
        results.append(
            BreadthMemberResult(
                instrument_id=member.instrument_id,
                symbol=member.symbol,
                name=member.name,
                value=value,
                metric=metric,
                observation_time=getattr(bars[-1], "ts", None) if bars else None,
                exclusion_code=exclusion,
            )
        )
    eligible = sum(result.value is not None for result in results)
    passed = sum(result.value is True for result in results)
    requested = len(results)
    exclusions = sum(result.exclusion_code is not None for result in results)
    return results, {
        "requested_count": requested,
        "eligible_count": eligible,
        "pass_count": passed,
        "excluded_count": exclusions,
        "coverage": eligible / requested if requested else 0.0,
        "percentage": passed / eligible if eligible else None,
    }


def evaluate_breadth_history(
    members: list[BreadthMember],
    bars_by_instrument: Mapping[int, list[Any]],
    condition: Mapping[str, Any],
    *,
    limit: int = 500,
    benchmark_bars: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """Evaluate one condition on aligned observed timestamps.

    A member is eligible at ``timestamp`` only when it has an actual bar at
    that timestamp.  Earlier bars are used for lookback calculations, but a
    missing current bar is never forward-filled into a historical breadth
    percentage.  This is the key distinction between a historical study and a
    current snapshot repeatedly sampled from a changing universe.
    """

    timestamps = sorted(
        {
            getattr(bar, "ts", None)
            for bars in bars_by_instrument.values()
            for bar in bars
            if getattr(bar, "ts", None) is not None
        }
    )
    if not timestamps:
        return []
    points: list[dict[str, Any]] = []
    for timestamp in timestamps:
        member_results: list[BreadthMemberResult] = []
        for member in members:
            member_bars = list(bars_by_instrument.get(member.instrument_id, []))
            observed = [bar for bar in member_bars if getattr(bar, "ts", None) <= timestamp]
            has_current_bar = bool(observed and getattr(observed[-1], "ts", None) == timestamp)
            if not has_current_bar:
                exclusion = "missing_bar_at_timestamp" if observed else "no_bars"
                member_results.append(
                    BreadthMemberResult(
                        instrument_id=member.instrument_id,
                        symbol=member.symbol,
                        name=member.name,
                        value=None,
                        metric=None,
                        observation_time=None,
                        exclusion_code=exclusion,
                    )
                )
                continue
            benchmark_at_timestamp = benchmark_bars
            if benchmark_bars is not None:
                benchmark_observed = [
                    bar for bar in benchmark_bars if getattr(bar, "ts", None) <= timestamp
                ]
                if (
                    not benchmark_observed
                    or getattr(benchmark_observed[-1], "ts", None) != timestamp
                ):
                    benchmark_at_timestamp = []
            value, metric, exclusion = evaluate_condition(
                observed,
                condition,
                benchmark_bars=benchmark_at_timestamp,
            )
            if exclusion == "benchmark_required" and benchmark_bars is not None:
                exclusion = "benchmark_missing_at_timestamp"
            member_results.append(
                BreadthMemberResult(
                    instrument_id=member.instrument_id,
                    symbol=member.symbol,
                    name=member.name,
                    value=value,
                    metric=metric,
                    observation_time=timestamp if value is not None else None,
                    exclusion_code=exclusion,
                )
            )
        eligible = sum(result.value is not None for result in member_results)
        passed = sum(result.value is True for result in member_results)
        points.append(
            {
                "timestamp": timestamp,
                "requested_count": len(member_results),
                "eligible_count": eligible,
                "pass_count": passed,
                "excluded_count": len(member_results) - eligible,
                "coverage": eligible / len(member_results) if member_results else 0.0,
                "percentage": passed / eligible if eligible else None,
                "members": member_results,
            }
        )
    return points[-max(1, min(limit, 5_000)) :]


def detect_breadth_occurrences(points: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return deterministic member enter/exit events from historical breadth points.

    An occurrence is emitted only when a member has two known Boolean observations
    and changes state.  Initial observations and excluded/missing bars do not create
    synthetic events, so a gap cannot be mistaken for a false-to-true transition.
    """

    previous: dict[int, bool | None] = {}
    occurrences: list[dict[str, Any]] = []
    for point in points:
        timestamp = point.get("timestamp")
        percentage = point.get("percentage")
        pass_count = int(point.get("pass_count", 0))
        eligible_count = int(point.get("eligible_count", 0))
        for result in point.get("members", []):
            if isinstance(result, Mapping):
                instrument_id = int(result.get("instrument_id"))
                current = result.get("value")
                symbol = str(result.get("symbol", ""))
                name = str(result.get("name", ""))
                metric = result.get("metric")
            else:
                instrument_id = int(result.instrument_id)
                current = result.value
                symbol = str(result.symbol)
                name = str(result.name)
                metric = result.metric
            prior = previous.get(instrument_id)
            if prior is not None and current is not None and prior is not current:
                kind = "member_entered" if current else "member_exited"
                occurrences.append(
                    {
                        "occurrence_id": (
                            f"{instrument_id}:{timestamp.isoformat() if timestamp else 'unknown'}:{kind}"
                        ),
                        "timestamp": timestamp,
                        "kind": kind,
                        "instrument_id": instrument_id,
                        "symbol": symbol,
                        "name": name,
                        "value": bool(current),
                        "metric": metric,
                        "percentage": percentage,
                        "pass_count": pass_count,
                        "eligible_count": eligible_count,
                    }
                )
            previous[instrument_id] = current
    return occurrences
