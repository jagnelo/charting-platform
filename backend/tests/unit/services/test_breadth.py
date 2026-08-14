from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.services.breadth import (
    BreadthMember,
    definition_hash,
    evaluate_breadth,
    evaluate_condition,
)


def _bars(values: list[float], *, volume: float = 100) -> list[SimpleNamespace]:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    return [
        SimpleNamespace(
            close=value,
            volume=volume,
            ts=start + timedelta(days=index),
        )
        for index, value in enumerate(values)
    ]


def test_above_moving_average_reports_boolean_and_metric():
    value, metric, warning = evaluate_condition(
        _bars([100, 101, 102]),
        {"kind": "above_moving_average", "params": {"period": 2}},
    )

    assert value is True
    assert metric is not None and metric > 0
    assert warning is None


def test_within_one_percent_of_52_week_high_uses_the_declared_threshold():
    value, metric, warning = evaluate_condition(
        _bars([100] * 251 + [99.5]),
        {
            "kind": "within_52_week_high",
            "params": {"lookback": 252, "threshold": 0.01, "direction": "high"},
        },
    )

    assert value is True
    assert metric is not None and abs(metric - 0.005) < 1e-12
    assert warning is None


def test_breadth_keeps_insufficient_history_out_of_the_denominator():
    members = [
        BreadthMember(1, "A", "A"),
        BreadthMember(2, "B", "B"),
    ]
    results, aggregate = evaluate_breadth(
        members,
        {1: _bars([100, 101, 102]), 2: _bars([100])},
        {"kind": "above_moving_average", "params": {"period": 2}},
    )

    assert [result.value for result in results] == [True, None]
    assert aggregate["requested_count"] == 2
    assert aggregate["eligible_count"] == 1
    assert aggregate["pass_count"] == 1
    assert aggregate["coverage"] == 0.5
    assert aggregate["percentage"] == 1.0
    assert results[1].exclusion_code == "insufficient_history"


def test_definition_hash_changes_with_condition_or_membership_version():
    definition = {
        "version": 1,
        "universe": {"kind": "etf_holdings", "key": "SPY"},
        "condition": {"kind": "within_52_week_high", "params": {"threshold": 0.01}},
    }

    first = definition_hash(definition, membership_version=1)
    changed_condition = definition_hash(
        {**definition, "condition": {"kind": "within_52_week_high", "params": {"threshold": 0.02}}},
        membership_version=1,
    )
    changed_membership = definition_hash(definition, membership_version=2)

    assert first != changed_condition
    assert first != changed_membership
