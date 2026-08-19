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
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any


@dataclass(frozen=True)
class BreadthMember:
    instrument_id: int
    symbol: str
    name: str


@dataclass(frozen=True)
class BreadthConditionDiagnostic:
    """One clause-level explanation for a breadth member evaluation."""

    path: str
    kind: str
    status: str
    value: bool | None
    metric: float | None
    code: str | None = None


@dataclass(frozen=True)
class BreadthMemberResult:
    instrument_id: int
    symbol: str
    name: str
    value: bool | None
    metric: float | None
    observation_time: datetime | None
    exclusion_code: str | None = None
    diagnostics: tuple[BreadthConditionDiagnostic, ...] = ()


def build_equal_reference_series(
    bars_by_instrument: Mapping[int, list[Any]],
) -> tuple[list[Any], dict[str, int | float | str]]:
    """Materialize an aligned, equal-weight reference index from local member bars.

    This is deliberately a derived target series, not a claim that the group is an
    official index. Each timestamp contributes the simple mean of member returns for
    members with an exact current bar and a prior bar. No bar is carried forward. The
    resulting normalized index can therefore be compared using the existing ``close``
    or ``return`` field semantics while retaining explicit coverage metadata at the
    router boundary.
    """

    by_timestamp: dict[datetime, list[tuple[float, float]]] = {}
    member_count = 0
    for raw_bars in bars_by_instrument.values():
        bars = sorted(
            [bar for bar in raw_bars if getattr(bar, "ts", None) is not None],
            key=lambda bar: getattr(bar, "ts"),
        )
        if not bars:
            continue
        member_count += 1
        for previous, current in zip(bars, bars[1:]):
            previous_close = getattr(previous, "close", None)
            current_close = getattr(current, "close", None)
            if not _finite(previous_close) or not _finite(current_close):
                continue
            previous_value = float(previous_close)
            current_value = float(current_close)
            if previous_value <= 0 or current_value <= 0:
                continue
            timestamp = getattr(current, "ts")
            by_timestamp.setdefault(timestamp, []).append((current_value / previous_value) - 1)

    index_value = 100.0
    points: list[Any] = []
    covered_counts: list[int] = []
    for timestamp in sorted(by_timestamp):
        returns = by_timestamp[timestamp]
        if not returns:
            continue
        index_value *= 1 + (sum(returns) / len(returns))
        points.append(SimpleNamespace(ts=timestamp, close=index_value, volume=None))
        covered_counts.append(len(returns))

    summary: dict[str, int | float | str] = {
        "method": "derived_equal_weight_return_index",
        "membership_semantics": "reference_universe_member_returns",
        "member_count": member_count,
        "point_count": len(points),
        "covered_member_points": sum(covered_counts),
        "mean_covered_members": (
            sum(covered_counts) / len(covered_counts) if covered_counts else 0.0
        ),
        "supported_fields": "close,return",
        "alignment": "exact_timestamp_no_forward_fill",
    }
    return points, summary


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


def _series_comparison_metric(
    bars: list[Any],
    reference_bars: list[Any] | None,
    params: Mapping[str, Any],
) -> tuple[float | None, str | None]:
    """Compare one member field with an aligned benchmark/peer field.

    ``reference_bars`` is already resolved by the router from the canonical local
    database.  The latest observations must share an exact timestamp; this keeps
    peer comparisons honest instead of silently carrying a stale reference forward.
    ``relation=ratio`` returns member/reference - 1, while ``difference`` returns
    member - reference.
    """

    if reference_bars is None:
        return None, "benchmark_required"
    if not bars or not reference_bars:
        return None, "no_bars"
    member_timestamp = getattr(bars[-1], "ts", None)
    reference_timestamp = getattr(reference_bars[-1], "ts", None)
    if member_timestamp is None or reference_timestamp is None:
        return None, "invalid_reference"
    if member_timestamp != reference_timestamp:
        return None, "unaligned_reference"
    field = params.get("field", "close")
    target_field = params.get("target_field", field)
    if not isinstance(field, str) or not isinstance(target_field, str):
        return None, "invalid_condition_params"
    member_metric, member_warning = _comparison_metric(bars, field, params, benchmark_bars=None)
    if member_warning or member_metric is None:
        return None, member_warning or "invalid_condition_params"
    target_metric, target_warning = _comparison_metric(
        reference_bars, target_field, params, benchmark_bars=None
    )
    if target_warning or target_metric is None:
        return None, target_warning or "invalid_condition_params"
    relation = str(params.get("relation", "difference")).lower()
    if relation == "difference":
        metric = member_metric - target_metric
    elif relation == "ratio":
        if target_metric == 0:
            return None, "invalid_reference"
        metric = member_metric / target_metric - 1
    else:
        return None, "invalid_condition_params"
    return (metric if _finite(metric) else None), (None if _finite(metric) else "invalid_reference")


def _event_condition_metric(
    events: list[Any] | None,
    params: Mapping[str, Any],
    as_of: datetime | None,
) -> tuple[bool | None, float | None, str | None]:
    """Evaluate whether a declared event occurred in the trailing window.

    ``None`` events means the local event dataset is unavailable; an empty list is
    a known event-free observation.  This distinction keeps missing calendar data
    out of the eligible denominator instead of turning it into a false signal.
    Event timestamps are compared in UTC and are never forward-filled.
    """

    if events is None:
        return None, None, "event_data_unavailable"
    if as_of is None:
        return None, None, "invalid_condition_params"
    event_type = str(params.get("event_type", "any")).strip().lower()
    if not event_type:
        event_type = "any"
    include_estimates = bool(params.get("include_estimates", False))
    try:
        lookback_days = int(params.get("lookback_days", 0))
    except (TypeError, ValueError):
        return None, None, "invalid_condition_params"
    if lookback_days < 0 or lookback_days > 3_660:
        return None, None, "invalid_condition_params"
    as_of_utc = as_of if as_of.tzinfo is not None else as_of.replace(tzinfo=UTC)
    as_of_utc = as_of_utc.astimezone(UTC)
    start = as_of_utc - timedelta(days=lookback_days)
    matching = False
    for event in events:
        raw_time = getattr(event, "event_time", None)
        if not isinstance(raw_time, datetime):
            continue
        event_time = raw_time if raw_time.tzinfo is not None else raw_time.replace(tzinfo=UTC)
        event_time = event_time.astimezone(UTC)
        if event_time < start or event_time > as_of_utc:
            continue
        raw_type = getattr(getattr(event, "event_type", None), "value", None)
        raw_type = raw_type or getattr(event, "event_type", None)
        actual_type = str(raw_type or "").lower()
        if not include_estimates and actual_type.endswith("_estimate"):
            continue
        if event_type != "any" and actual_type != event_type:
            continue
        matching = True
        break
    metric = 1.0 if matching else 0.0
    try:
        value = _comparison(
            metric,
            {
                "operator": params.get("operator", "gte"),
                "threshold": params.get("threshold", 1),
            },
        )
    except (TypeError, ValueError):
        return None, None, "invalid_condition_params"
    return value, metric, None


def _field_series(
    bars: list[Any],
    field: str,
    params: Mapping[str, Any],
    *,
    benchmark_bars: list[Any] | None,
) -> tuple[list[float] | None, str | None]:
    """Build a deterministic member-level series for rolling target tests.

    The series is intentionally derived from already materialised local bars.  It
    is not a second programming language or a provider access path; Python-defined
    fields continue to use the isolated runner.  Keeping the supported vocabulary
    here makes the persisted breadth definition explicit and reproducible.
    """

    normalized = str(field).lower().strip()
    closes = _close_values(bars)
    if closes is None or not closes:
        return None, "invalid_close"
    if normalized in {"close", "price", "last"}:
        return closes, None
    if normalized in {"return", "return_1"}:
        if len(closes) < 2 or any(closes[index - 1] == 0 for index in range(1, len(closes))):
            return None, "invalid_reference"
        return [closes[index] / closes[index - 1] - 1 for index in range(1, len(closes))], None
    if normalized == "volume":
        volumes = [getattr(bar, "volume", None) for bar in bars]
        if any(not _finite(value) for value in volumes):
            return None, "missing_volume"
        return [float(value) for value in volumes], None
    if normalized in {"moving_average_distance", "ma_distance"}:
        period = int(params.get("period", 200))
        if period < 2 or len(closes) < period:
            return None, "insufficient_history"
        return [
            closes[index] / _mean(closes[index - period + 1 : index + 1]) - 1
            for index in range(period - 1, len(closes))
        ], None
    # Relative strength is inherently a two-series operation and is already
    # exposed as a direct condition; a rolling percentile of it belongs in the
    # isolated Python path until aligned pair-series support is declared.
    if normalized in {"relative_strength", "relative_return"} and benchmark_bars is None:
        return None, "benchmark_required"
    return None, "unsupported_field"


def _percentile_rank(values: list[float], target: float) -> float:
    """Return the inclusive empirical percentile rank in [0, 1]."""

    if not values:
        return math.nan
    return sum(value <= target for value in values) / len(values)


def _target_scope(condition: Mapping[str, Any]) -> str:
    params = condition.get("params", {})
    if not isinstance(params, Mapping):
        params = {}
    return str(condition.get("target_scope", params.get("target_scope", "member"))).lower()


def _is_cross_sectional(condition: Mapping[str, Any]) -> bool:
    return _target_scope(condition) == "cross_sectional"


def _contains_cross_sectional(condition: Mapping[str, Any]) -> bool:
    """Return whether a condition tree contains a cross-sectional target.

    Scope belongs to the individual AST node.  A compound condition may therefore
    combine member-level leaves with a cross-sectional percentile leaf; treating
    only the root as scoped would either reject a valid tree or silently evaluate
    the scoped leaf as a member condition.
    """

    if _is_cross_sectional(condition):
        return True
    params = condition.get("params", {})
    if not isinstance(params, Mapping):
        return False
    children = _nested_conditions(params)
    return bool(children and any(_contains_cross_sectional(child) for child in children))


def _condition_requires_benchmark(condition: Mapping[str, Any]) -> bool:
    kind = str(condition.get("kind", "")).lower()
    params = condition.get("params", {})
    if not isinstance(params, Mapping):
        return False
    if kind == "relative_strength":
        return True
    if kind in {"comparison", "percentile"} and str(params.get("field", "")).lower() in {
        "relative_strength",
        "relative_return",
    }:
        return True
    if kind == "series_comparison":
        return True
    children = params.get("conditions")
    return isinstance(children, list) and any(
        isinstance(child, Mapping) and _condition_requires_benchmark(child) for child in children
    )


def evaluate_cross_sectional_percentile(
    members: list[BreadthMember],
    bars_by_instrument: Mapping[int, list[Any]],
    condition: Mapping[str, Any],
    *,
    benchmark_bars: list[Any] | None = None,
    forced_exclusions: Mapping[int, str] | None = None,
) -> tuple[list[BreadthMemberResult], dict[str, int | float]]:
    """Rank one declared scalar field across the eligible members.

    Cross-sectional ranking is deliberately a separate target scope from a
    member's rolling percentile.  Each member first produces a scalar at the
    same observation timestamp; only valid scalars participate in the rank
    denominator.  Ties use the inclusive empirical rank so the result remains
    deterministic and explainable.
    """

    params = condition.get("params", condition)
    if not isinstance(params, Mapping) or str(condition.get("kind", "")).lower() != "percentile":
        return [
            BreadthMemberResult(
                instrument_id=member.instrument_id,
                symbol=member.symbol,
                name=member.name,
                value=None,
                metric=None,
                observation_time=None,
                exclusion_code="cross_sectional_unsupported_condition",
                diagnostics=(
                    BreadthConditionDiagnostic(
                        path="$",
                        kind=str(condition.get("kind", "")),
                        status="excluded",
                        value=None,
                        metric=None,
                        code="cross_sectional_unsupported_condition",
                    ),
                ),
            )
            for member in members
        ], {
            "requested_count": len(members),
            "eligible_count": 0,
            "pass_count": 0,
            "excluded_count": len(members),
            "coverage": 0.0,
            "percentage": None,
        }
    field = params.get("field")
    if not isinstance(field, str) or not field.strip():
        invalid_code = "invalid_condition_params"
    else:
        invalid_code = None
    try:
        percentile = float(params.get("percentile", 0.8))
    except (TypeError, ValueError):
        percentile = math.nan
    if invalid_code is None and (not _finite(percentile) or not 0 <= percentile <= 1):
        invalid_code = "invalid_condition_params"

    metrics: dict[int, float] = {}
    exclusions: dict[int, str] = {}
    for member in members:
        bars = list(bars_by_instrument.get(member.instrument_id, []))
        if forced_exclusions and member.instrument_id in forced_exclusions:
            exclusions[member.instrument_id] = forced_exclusions[member.instrument_id]
            continue
        if invalid_code:
            exclusions[member.instrument_id] = invalid_code
            continue
        metric, warning = _comparison_metric(bars, field, params, benchmark_bars=benchmark_bars)
        if warning or metric is None:
            exclusions[member.instrument_id] = warning or "invalid_condition_params"
        else:
            metrics[member.instrument_id] = metric

    ranks = list(metrics.values())
    results: list[BreadthMemberResult] = []
    for member in members:
        bars = list(bars_by_instrument.get(member.instrument_id, []))
        warning = exclusions.get(member.instrument_id)
        if warning:
            results.append(
                BreadthMemberResult(
                    instrument_id=member.instrument_id,
                    symbol=member.symbol,
                    name=member.name,
                    value=None,
                    metric=None,
                    observation_time=None,
                    exclusion_code=warning,
                    diagnostics=(
                        BreadthConditionDiagnostic(
                            path="$",
                            kind=str(condition.get("kind", "")),
                            status="excluded",
                            value=None,
                            metric=None,
                            code=warning,
                        ),
                    ),
                )
            )
            continue
        rank = _percentile_rank(ranks, metrics[member.instrument_id])
        value = _comparison(
            rank,
            {"operator": params.get("operator", "gte"), "threshold": percentile},
        )
        results.append(
            BreadthMemberResult(
                instrument_id=member.instrument_id,
                symbol=member.symbol,
                name=member.name,
                value=value,
                metric=rank,
                observation_time=getattr(bars[-1], "ts", None) if bars else None,
                diagnostics=(
                    BreadthConditionDiagnostic(
                        path="$",
                        kind=str(condition.get("kind", "")),
                        status="pass" if value else "fail",
                        value=value,
                        metric=rank,
                    ),
                ),
            )
        )
    eligible = sum(result.value is not None for result in results)
    passed = sum(result.value is True for result in results)
    requested = len(results)
    return results, {
        "requested_count": requested,
        "eligible_count": eligible,
        "pass_count": passed,
        "excluded_count": requested - eligible,
        "coverage": eligible / requested if requested else 0.0,
        "percentage": passed / eligible if eligible else None,
    }


def evaluate_cross_sectional_statistic(
    members: list[BreadthMember],
    bars_by_instrument: Mapping[int, list[Any]],
    condition: Mapping[str, Any],
    *,
    benchmark_bars: list[Any] | None = None,
    forced_exclusions: Mapping[int, str] | None = None,
) -> tuple[list[BreadthMemberResult], dict[str, int | float]]:
    """Compare each member scalar with one same-timestamp group statistic.

    ``metric`` is the member scalar minus the selected group statistic, making
    the decision and its magnitude transparent.  The supported statistic set is
    deliberately small and deterministic; richer derived/Python series remain
    an explicitly separate capability.
    """

    params = condition.get("params", condition)
    if (
        not isinstance(params, Mapping)
        or str(condition.get("kind", "")).lower() != "cross_sectional_statistic"
    ):
        return [
            _excluded_member_result(member, condition, "cross_sectional_unsupported_condition")
            for member in members
        ], {
            "requested_count": len(members),
            "eligible_count": 0,
            "pass_count": 0,
            "excluded_count": len(members),
            "coverage": 0.0,
            "percentage": None,
        }
    field = params.get("field")
    statistic = str(params.get("statistic", "mean")).lower()
    if (
        not isinstance(field, str)
        or not field.strip()
        or statistic
        not in {
            "mean",
            "median",
            "min",
            "max",
            "std",
        }
    ):
        code = "invalid_condition_params"
        return [_excluded_member_result(member, condition, code) for member in members], {
            "requested_count": len(members),
            "eligible_count": 0,
            "pass_count": 0,
            "excluded_count": len(members),
            "coverage": 0.0,
            "percentage": None,
        }
    try:
        threshold = float(params.get("threshold", 0.0))
    except (TypeError, ValueError):
        threshold = math.nan
    if not _finite(threshold):
        code = "invalid_condition_params"
        return [_excluded_member_result(member, condition, code) for member in members], {
            "requested_count": len(members),
            "eligible_count": 0,
            "pass_count": 0,
            "excluded_count": len(members),
            "coverage": 0.0,
            "percentage": None,
        }
    metrics: dict[int, float] = {}
    exclusions: dict[int, str] = {}
    for member in members:
        if forced_exclusions and member.instrument_id in forced_exclusions:
            exclusions[member.instrument_id] = forced_exclusions[member.instrument_id]
            continue
        scalar, warning = _comparison_metric(
            list(bars_by_instrument.get(member.instrument_id, [])),
            field,
            params,
            benchmark_bars=benchmark_bars,
        )
        if warning or scalar is None or not _finite(scalar):
            exclusions[member.instrument_id] = warning or "invalid_condition_params"
            continue
        metrics[member.instrument_id] = float(scalar)
    values = list(metrics.values())
    if not values:
        group_value = math.nan
    elif statistic == "mean":
        group_value = sum(values) / len(values)
    elif statistic == "median":
        ordered = sorted(values)
        middle = len(ordered) // 2
        group_value = (
            ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
        )
    elif statistic == "min":
        group_value = min(values)
    elif statistic == "max":
        group_value = max(values)
    else:
        mean = sum(values) / len(values)
        group_value = math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))
    results: list[BreadthMemberResult] = []
    for member in members:
        warning = exclusions.get(member.instrument_id)
        if warning or not _finite(group_value):
            code = warning or "invalid_reference"
            results.append(_excluded_member_result(member, condition, code))
            continue
        delta = metrics[member.instrument_id] - group_value
        value = _comparison(delta, params)
        results.append(
            BreadthMemberResult(
                instrument_id=member.instrument_id,
                symbol=member.symbol,
                name=member.name,
                value=value,
                metric=delta,
                observation_time=(
                    getattr(bars_by_instrument.get(member.instrument_id, [])[-1], "ts", None)
                    if bars_by_instrument.get(member.instrument_id)
                    else None
                ),
                diagnostics=(
                    BreadthConditionDiagnostic(
                        path="$",
                        kind="cross_sectional_statistic",
                        status="pass" if value else "fail",
                        value=value,
                        metric=delta,
                    ),
                ),
            )
        )
    eligible = sum(result.value is not None for result in results)
    passed = sum(result.value is True for result in results)
    requested = len(results)
    return results, {
        "requested_count": requested,
        "eligible_count": eligible,
        "pass_count": passed,
        "excluded_count": requested - eligible,
        "coverage": eligible / requested if requested else 0.0,
        "percentage": passed / eligible if eligible else None,
        "group_value": group_value if _finite(group_value) else math.nan,
    }


def evaluate_cross_sectional_target(
    members: list[BreadthMember],
    bars_by_instrument: Mapping[int, list[Any]],
    condition: Mapping[str, Any],
    *,
    benchmark_bars: list[Any] | None = None,
    forced_exclusions: Mapping[int, str] | None = None,
) -> tuple[list[BreadthMemberResult], dict[str, int | float]]:
    """Dispatch one explicit cross-sectional target without scope fallback."""

    if str(condition.get("kind", "")).lower() == "cross_sectional_statistic":
        return evaluate_cross_sectional_statistic(
            members,
            bars_by_instrument,
            condition,
            benchmark_bars=benchmark_bars,
            forced_exclusions=forced_exclusions,
        )
    return evaluate_cross_sectional_percentile(
        members,
        bars_by_instrument,
        condition,
        benchmark_bars=benchmark_bars,
        forced_exclusions=forced_exclusions,
    )


def _excluded_member_result(
    member: BreadthMember,
    condition: Mapping[str, Any],
    code: str,
    *,
    observation_time: datetime | None = None,
) -> BreadthMemberResult:
    return BreadthMemberResult(
        instrument_id=member.instrument_id,
        symbol=member.symbol,
        name=member.name,
        value=None,
        metric=None,
        observation_time=observation_time,
        exclusion_code=code,
        diagnostics=(
            BreadthConditionDiagnostic(
                path="$",
                kind=str(condition.get("kind", "")),
                status="excluded",
                value=None,
                metric=None,
                code=code,
            ),
        ),
    )


def _prefix_diagnostics(
    diagnostics: tuple[BreadthConditionDiagnostic, ...], path: str
) -> tuple[BreadthConditionDiagnostic, ...]:
    """Move a scoped leaf's diagnostic paths under its AST location."""

    prefixed: list[BreadthConditionDiagnostic] = []
    for diagnostic in diagnostics:
        suffix = diagnostic.path[1:] if diagnostic.path.startswith("$") else diagnostic.path
        prefixed.append(replace(diagnostic, path=f"{path}{suffix}"))
    return tuple(prefixed)


def _evaluate_cross_sectional_tree(
    members: list[BreadthMember],
    bars_by_instrument: Mapping[int, list[Any]],
    condition: Mapping[str, Any],
    *,
    benchmark_bars: list[Any] | None = None,
    events_by_instrument: Mapping[int, list[Any] | None] | None = None,
    forced_exclusions: Mapping[int, str] | None = None,
) -> tuple[list[BreadthMemberResult], dict[str, int | float]]:
    """Evaluate a mixed member/cross-sectional condition tree.

    Cross-sectional leaves are materialised once for the complete eligible
    universe, then composed with ordinary member leaves using the same tri-state
    AND/OR/NOT semantics as ``evaluate_condition``.  This preserves the strict
    denominator and lets a user author, for example, ``ALL(member above SMA,
    member in the top return percentile)`` without a second condition language.
    """

    scoped_results: dict[str, dict[int, BreadthMemberResult]] = {}
    scoped_aggregates: dict[str, dict[str, int | float]] = {}

    def collect(node: Mapping[str, Any], path: str) -> None:
        if _is_cross_sectional(node):
            leaf_results, aggregate = evaluate_cross_sectional_target(
                members,
                bars_by_instrument,
                node,
                benchmark_bars=benchmark_bars,
                forced_exclusions=forced_exclusions,
            )
            scoped_results[path] = {result.instrument_id: result for result in leaf_results}
            scoped_aggregates[path] = aggregate
        params = node.get("params", {})
        if not isinstance(params, Mapping):
            return
        children = _nested_conditions(params)
        if children:
            for index, child in enumerate(children):
                collect(child, f"{path}.conditions[{index}]")

    collect(condition, "$")

    def visit(
        member: BreadthMember,
        bars: list[Any],
        node: Mapping[str, Any],
        path: str,
    ) -> tuple[bool | None, float | None, str | None, tuple[BreadthConditionDiagnostic, ...]]:
        if forced_exclusions and member.instrument_id in forced_exclusions:
            code = forced_exclusions[member.instrument_id]
            return (
                None,
                None,
                code,
                _prefix_diagnostics(_excluded_member_result(member, node, code).diagnostics, path),
            )

        if _is_cross_sectional(node):
            result = scoped_results.get(path, {}).get(member.instrument_id)
            if result is None:
                code = "cross_sectional_member_missing"
                return (
                    None,
                    None,
                    code,
                    _prefix_diagnostics(
                        _excluded_member_result(member, node, code).diagnostics, path
                    ),
                )
            return (
                result.value,
                result.metric,
                result.exclusion_code,
                _prefix_diagnostics(result.diagnostics, path),
            )

        kind = str(node.get("kind", "")).lower()
        params = node.get("params", {})
        children = _nested_conditions(params) if isinstance(params, Mapping) else None
        if (
            kind in {"all", "any", "not"}
            and children
            and any(_contains_cross_sectional(child) for child in children)
        ):
            evaluated = [
                visit(member, bars, child, f"{path}.conditions[{index}]")
                for index, child in enumerate(children)
            ]
            values = [item[0] for item in evaluated]
            metrics = [item[1] for item in evaluated if item[1] is not None]
            exclusion: str | None = None
            if kind == "all":
                missing = next((index for index, value in enumerate(values) if value is None), None)
                value = None if missing is not None else all(item is True for item in values)
                if missing is not None:
                    exclusion = (
                        f"condition_clause_excluded:{missing}:"
                        f"{evaluated[missing][2] or 'unknown'}"
                    )
                metric = min(metrics) if metrics else None
            elif kind == "any":
                if any(item is True for item in values):
                    value = True
                    metric = (
                        max(
                            item[1] for item in evaluated if item[0] is True and item[1] is not None
                        )
                        if any(item[0] is True and item[1] is not None for item in evaluated)
                        else None
                    )
                elif all(item is False for item in values):
                    value = False
                    metric = max(metrics) if metrics else None
                else:
                    missing = next(index for index, item in enumerate(values) if item is None)
                    value = None
                    metric = None
                    exclusion = (
                        f"condition_clause_excluded:{missing}:"
                        f"{evaluated[missing][2] or 'unknown'}"
                    )
            else:
                if len(evaluated) != 1:
                    return None, None, "invalid_condition_params", ()
                value, metric, child_exclusion = evaluated[0][:3]
                exclusion = (
                    f"condition_clause_excluded:0:{child_exclusion}" if child_exclusion else None
                )
                value = (not value) if value is not None and not exclusion else None
            diagnostics: list[BreadthConditionDiagnostic] = [
                item for evaluated_item in evaluated for item in evaluated_item[3]
            ]
            diagnostics.insert(
                0,
                BreadthConditionDiagnostic(
                    path=path,
                    kind=kind,
                    status=(
                        "excluded" if exclusion or value is None else "pass" if value else "fail"
                    ),
                    value=value,
                    metric=metric,
                    code=exclusion,
                ),
            )
            return value, metric, exclusion, tuple(diagnostics)

        value, metric, exclusion, diagnostics = evaluate_condition_with_diagnostics(
            bars,
            node,
            benchmark_bars=benchmark_bars,
            events=(events_by_instrument or {}).get(member.instrument_id)
            if events_by_instrument is not None
            else None,
        )
        return value, metric, exclusion, _prefix_diagnostics(diagnostics, path)

    results: list[BreadthMemberResult] = []
    for member in members:
        bars = list(bars_by_instrument.get(member.instrument_id, []))
        value, metric, exclusion, diagnostics = visit(member, bars, condition, "$")
        results.append(
            BreadthMemberResult(
                instrument_id=member.instrument_id,
                symbol=member.symbol,
                name=member.name,
                value=value,
                metric=metric,
                observation_time=getattr(bars[-1], "ts", None) if value is not None else None,
                exclusion_code=exclusion,
                diagnostics=diagnostics,
            )
        )
    eligible = sum(result.value is not None for result in results)
    passed = sum(result.value is True for result in results)
    requested = len(results)
    aggregate: dict[str, int | float] = {
        "requested_count": requested,
        "eligible_count": eligible,
        "pass_count": passed,
        "excluded_count": requested - eligible,
        "coverage": eligible / requested if requested else 0.0,
        "percentage": passed / eligible if eligible else None,
    }
    root_aggregate = scoped_aggregates.get("$", {})
    if "group_value" in root_aggregate:
        aggregate["group_value"] = root_aggregate["group_value"]
    return results, aggregate


def evaluate_condition(
    bars: list[Any],
    condition: Mapping[str, Any],
    *,
    benchmark_bars: list[Any] | None = None,
    events: list[Any] | None = None,
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

    if _is_cross_sectional(condition):
        return None, None, "cross_sectional_requires_universe"

    if kind in {"all", "any"}:
        children = _nested_conditions(params)
        if children is None:
            return None, None, "invalid_condition_params"
        evaluated = [
            evaluate_condition(bars, child, benchmark_bars=benchmark_bars, events=events)
            for child in children
        ]
        if kind == "all":
            for index, (value, _, warning) in enumerate(evaluated):
                if value is None:
                    return None, None, f"condition_clause_excluded:{index}:{warning or 'unknown'}"
            metrics = [metric for _, metric, _ in evaluated if metric is not None]
            return (
                all(value is True for value, _, _ in evaluated),
                min(metrics) if metrics else None,
                None,
            )
        if any(value is True for value, _, _ in evaluated):
            metrics = [
                metric for value, metric, _ in evaluated if value is True and metric is not None
            ]
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
            bars, children[0], benchmark_bars=benchmark_bars, events=events
        )
        if warning:
            return None, None, f"condition_clause_excluded:0:{warning}"
        return (not value) if value is not None else None, metric, None

    if kind == "comparison":
        field = params.get("field")
        if not isinstance(field, str) or not field.strip():
            return None, None, "invalid_condition_params"
        metric, warning = _comparison_metric(bars, field, params, benchmark_bars=benchmark_bars)
        if warning or metric is None:
            return None, metric, warning or "invalid_condition_params"
        return _comparison(metric, params), metric, None

    if kind == "series_comparison":
        metric, warning = _series_comparison_metric(bars, benchmark_bars, params)
        if warning or metric is None:
            return None, metric, warning or "invalid_condition_params"
        try:
            return _comparison(metric, params), metric, None
        except (TypeError, ValueError):
            return None, None, "invalid_condition_params"

    if kind == "event":
        as_of = getattr(bars[-1], "ts", None) if bars else None
        return _event_condition_metric(events, params, as_of)

    if kind == "range":
        field = params.get("field")
        if not isinstance(field, str) or not field.strip():
            return None, None, "invalid_condition_params"
        metric, warning = _comparison_metric(bars, field, params, benchmark_bars=benchmark_bars)
        if warning or metric is None:
            return None, metric, warning or "invalid_condition_params"
        try:
            lower = float(params["lower"])
            upper = float(params["upper"])
        except (KeyError, TypeError, ValueError):
            return None, None, "invalid_condition_params"
        if not _finite(lower) or not _finite(upper) or lower > upper:
            return None, None, "invalid_condition_params"
        inclusive = bool(params.get("inclusive", True))
        value = lower <= metric <= upper if inclusive else lower < metric < upper
        return value, metric, None

    if kind == "percentile":
        field = params.get("field")
        if not isinstance(field, str) or not field.strip():
            return None, None, "invalid_condition_params"
        period = int(params.get("period", 252))
        percentile = float(params.get("percentile", 0.8))
        if period < 2 or period > 5_000 or not 0 <= percentile <= 1:
            return None, None, "invalid_condition_params"
        series, warning = _field_series(bars, field, params, benchmark_bars=benchmark_bars)
        if warning or series is None:
            return None, None, warning or "invalid_condition_params"
        if len(series) < period:
            return None, None, "insufficient_history"
        window = series[-period:]
        rank = _percentile_rank(window, window[-1])
        comparison_params = {
            "operator": params.get("operator", "gte"),
            "threshold": percentile,
        }
        return _comparison(rank, comparison_params), rank, None

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

    if kind == "prior_high_low":
        # The current bar is deliberately excluded from the reference window.
        # The signed percentage distance lets the same operator contract express
        # breakouts, breakdowns, retests, and rejection thresholds.
        lookback = int(params.get("lookback", 20))
        direction = str(params.get("direction", "high")).lower()
        if direction not in {"high", "low"}:
            return None, None, "invalid_condition_params"
        if lookback < 2 or lookback > 5_000 or len(closes) <= lookback:
            return None, None, "insufficient_history"
        previous = closes[-(lookback + 1) : -1]
        reference = max(previous) if direction == "high" else min(previous)
        if not _finite(reference) or reference <= 0:
            return None, None, "invalid_reference"
        metric = latest / reference - 1
        if not _finite(metric):
            return None, None, "invalid_reference"
        default_operator = "gte" if direction == "high" else "lte"
        comparison_params = {
            "operator": params.get("operator", default_operator),
            "threshold": params.get("threshold", 0),
        }
        try:
            value = _comparison(metric, comparison_params)
        except (TypeError, ValueError):
            return None, None, "invalid_condition_params"
        return value, metric, None

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


def evaluate_condition_with_diagnostics(
    bars: list[Any],
    condition: Mapping[str, Any],
    *,
    benchmark_bars: list[Any] | None = None,
    events: list[Any] | None = None,
) -> tuple[bool | None, float | None, str | None, tuple[BreadthConditionDiagnostic, ...]]:
    """Evaluate a condition and retain a deterministic trace for every clause.

    The existing evaluator remains the semantic authority. This wrapper walks
    the same immutable AST after evaluation, so diagnostics cannot change the
    Boolean result or denominator semantics while explaining nested groups and
    leaf outcomes to the workstation.
    """

    value, metric, exclusion = evaluate_condition(
        bars, condition, benchmark_bars=benchmark_bars, events=events
    )
    diagnostics: list[BreadthConditionDiagnostic] = []

    def visit(node: Mapping[str, Any], path: str) -> None:
        node_value, node_metric, node_exclusion = evaluate_condition(
            bars, node, benchmark_bars=benchmark_bars, events=events
        )
        diagnostics.append(
            BreadthConditionDiagnostic(
                path=path,
                kind=str(node.get("kind", "")),
                status=(
                    "excluded"
                    if node_exclusion or node_value is None
                    else "pass"
                    if node_value
                    else "fail"
                ),
                value=node_value,
                metric=node_metric,
                code=node_exclusion,
            )
        )
        kind = str(node.get("kind", "")).lower()
        params = node.get("params")
        if kind not in {"all", "any", "not"} or not isinstance(params, Mapping):
            return
        children = _nested_conditions(params)
        if children is None:
            return
        for index, child in enumerate(children):
            visit(child, f"{path}.conditions[{index}]")

    if isinstance(condition, Mapping):
        visit(condition, "$")
    return value, metric, exclusion, tuple(diagnostics)


def evaluate_breadth(
    members: list[BreadthMember],
    bars_by_instrument: Mapping[int, list[Any]],
    condition: Mapping[str, Any],
    *,
    benchmark_bars: list[Any] | None = None,
    events_by_instrument: Mapping[int, list[Any] | None] | None = None,
) -> tuple[list[BreadthMemberResult], dict[str, int | float]]:
    """Evaluate one condition across a universe and return aggregate metadata."""

    if _contains_cross_sectional(condition):
        return _evaluate_cross_sectional_tree(
            members,
            bars_by_instrument,
            condition,
            benchmark_bars=benchmark_bars,
            events_by_instrument=events_by_instrument,
        )
    results: list[BreadthMemberResult] = []
    for member in members:
        bars = list(bars_by_instrument.get(member.instrument_id, []))
        value, metric, exclusion, diagnostics = evaluate_condition_with_diagnostics(
            bars,
            condition,
            benchmark_bars=benchmark_bars,
            events=(events_by_instrument or {}).get(member.instrument_id)
            if events_by_instrument is not None
            else None,
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
                diagnostics=diagnostics,
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
    events_by_instrument: Mapping[int, list[Any] | None] | None = None,
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
        snapshot_bars_by_instrument: dict[int, list[Any]] = {}
        snapshot_exclusions: dict[int, str] = {}
        member_results: list[BreadthMemberResult] = []
        for member in members:
            member_bars = list(bars_by_instrument.get(member.instrument_id, []))
            observed = [bar for bar in member_bars if getattr(bar, "ts", None) <= timestamp]
            has_current_bar = bool(observed and getattr(observed[-1], "ts", None) == timestamp)
            if not has_current_bar:
                exclusion = "missing_bar_at_timestamp" if observed else "no_bars"
                snapshot_exclusions[member.instrument_id] = exclusion
                member_results.append(
                    BreadthMemberResult(
                        instrument_id=member.instrument_id,
                        symbol=member.symbol,
                        name=member.name,
                        value=None,
                        metric=None,
                        observation_time=None,
                        exclusion_code=exclusion,
                        diagnostics=(
                            BreadthConditionDiagnostic(
                                path="$",
                                kind=str(condition.get("kind", "")),
                                status="excluded",
                                value=None,
                                metric=None,
                                code=exclusion,
                            ),
                        ),
                    )
                )
                continue
            snapshot_bars_by_instrument[member.instrument_id] = observed
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
            if _contains_cross_sectional(condition):
                # The second pass below ranks all members at this timestamp;
                # retain the observed bars here only to preserve the strict
                # no-forward-fill membership boundary.
                continue
            value, metric, exclusion, diagnostics = evaluate_condition_with_diagnostics(
                observed,
                condition,
                benchmark_bars=benchmark_at_timestamp,
                events=(events_by_instrument or {}).get(member.instrument_id)
                if events_by_instrument is not None
                else None,
            )
            if (
                benchmark_bars is not None
                and not benchmark_at_timestamp
                and _condition_requires_benchmark(condition)
            ):
                exclusion = "benchmark_missing_at_timestamp"
                diagnostics = tuple(
                    replace(item, code="benchmark_missing_at_timestamp")
                    if item.code
                    in {
                        "benchmark_required",
                        "insufficient_history",
                        "no_bars",
                        "unaligned_reference",
                    }
                    else item
                    for item in diagnostics
                )
            member_results.append(
                BreadthMemberResult(
                    instrument_id=member.instrument_id,
                    symbol=member.symbol,
                    name=member.name,
                    value=value,
                    metric=metric,
                    observation_time=timestamp if value is not None else None,
                    exclusion_code=exclusion,
                    diagnostics=diagnostics,
                )
            )
        if _contains_cross_sectional(condition):
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
            member_results, _ = _evaluate_cross_sectional_tree(
                members,
                snapshot_bars_by_instrument,
                condition,
                benchmark_bars=benchmark_at_timestamp,
                events_by_instrument=events_by_instrument,
                forced_exclusions=snapshot_exclusions,
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
                occurrence_timestamp = (
                    timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp)
                )
                occurrences.append(
                    {
                        "occurrence_id": (
                            f"{instrument_id}:{occurrence_timestamp if timestamp else 'unknown'}:{kind}"
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
