"""Test-only oracle: the pre-optimisation breadth history algorithm, verbatim.

Kept so the optimised ``evaluate_breadth_history`` can be checked for
byte-identical output on randomised inputs. Do not use in product code.
"""

from __future__ import annotations

import math  # noqa: F401 - keep the original module's names available
from collections.abc import Mapping  # noqa: F401
from dataclasses import replace  # noqa: F401
from datetime import datetime  # noqa: F401
from typing import Any

from app.services.breadth import (  # noqa: F401
    BreadthConditionDiagnostic,
    BreadthMember,
    BreadthMemberResult,
    _condition_requires_benchmark,
    _contains_cross_sectional,
    _evaluate_cross_sectional_tree,
    evaluate_condition_with_diagnostics,
)


def reference_evaluate_breadth_history(
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
