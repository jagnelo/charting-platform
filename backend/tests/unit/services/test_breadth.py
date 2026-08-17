from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.services.breadth import (
    BreadthMember,
    definition_hash,
    detect_breadth_occurrences,
    evaluate_breadth,
    evaluate_breadth_history,
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


def test_history_does_not_forward_fill_a_member_missing_the_current_timestamp():
    first = _bars([100, 101, 102])
    second = _bars([100, 101])
    second[-1].ts = first[-1].ts - timedelta(days=1)
    points = evaluate_breadth_history(
        [BreadthMember(1, "A", "A"), BreadthMember(2, "B", "B")],
        {1: first, 2: second},
        {"kind": "above_moving_average", "params": {"period": 2}},
        limit=10,
    )

    latest = points[-1]
    assert latest["timestamp"] == first[-1].ts
    assert latest["eligible_count"] == 1
    assert latest["coverage"] == 0.5
    by_symbol = {result.symbol: result for result in latest["members"]}
    assert by_symbol["A"].value is True
    assert by_symbol["B"].exclusion_code == "missing_bar_at_timestamp"


def test_history_occurrences_report_only_known_member_state_transitions():
    points = evaluate_breadth_history(
        [BreadthMember(1, "A", "A")],
        {1: _bars([100, 102, 100])},
        {
            "kind": "comparison",
            "params": {"field": "close", "operator": ">", "threshold": 101},
        },
        limit=10,
    )

    occurrences = detect_breadth_occurrences(points)

    assert [(item["kind"], item["symbol"]) for item in occurrences] == [
        ("member_entered", "A"),
        ("member_exited", "A"),
    ]
    assert occurrences[0]["value"] is True
    assert occurrences[1]["value"] is False
    assert occurrences[0]["pass_count"] == 1
    assert occurrences[1]["pass_count"] == 0


def test_composite_conditions_and_comparison_fields_are_reusable():
    condition = {
        "kind": "all",
        "params": {
            "conditions": [
                {"kind": "comparison", "params": {"field": "return", "operator": ">", "threshold": 0}},
                {"kind": "not", "params": {"conditions": [{"kind": "rsi", "params": {"period": 2, "threshold": 50, "comparator": "below"}}]}},
            ]
        },
    }
    value, metric, warning = evaluate_condition(_bars([100, 101, 103, 105]), condition)

    assert value is True
    assert metric is not None and metric > 0
    assert warning is None


def test_composite_condition_preserves_nested_exclusion_path():
    value, metric, warning = evaluate_condition(
        _bars([100]),
        {
            "kind": "all",
            "params": {
                "conditions": [
                    {"kind": "comparison", "params": {"field": "return", "threshold": 0}},
                    {"kind": "comparison", "params": {"field": "close", "threshold": 0}},
                ]
            },
        },
    )

    assert value is None
    assert metric is None
    assert warning == "condition_clause_excluded:0:insufficient_history"


def test_range_condition_exposes_member_level_bounds_and_metric():
    value, metric, warning = evaluate_condition(
        _bars([100, 102, 105]),
        {
            "kind": "range",
            "params": {"field": "return", "lower": 0.02, "upper": 0.04},
        },
    )

    assert value is True
    assert metric == (105 / 102) - 1
    assert warning is None


def test_percentile_condition_uses_the_declared_rolling_window_and_operator():
    value, metric, warning = evaluate_condition(
        _bars([1, 2, 3, 4, 5]),
        {
            "kind": "percentile",
            "params": {"field": "close", "period": 4, "percentile": 0.75, "operator": "gte"},
        },
    )

    assert value is True
    assert metric == 1.0
    assert warning is None


def test_invalid_range_bounds_are_excluded_instead_of_becoming_false():
    value, metric, warning = evaluate_condition(
        _bars([100, 101]),
        {"kind": "range", "params": {"field": "close", "lower": 2, "upper": 1}},
    )

    assert value is None
    assert metric is None
    assert warning == "invalid_condition_params"
