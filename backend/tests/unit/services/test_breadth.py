from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.services.breadth import (
    BreadthMember,
    build_equal_reference_series,
    definition_hash,
    detect_breadth_occurrences,
    evaluate_breadth,
    evaluate_breadth_history,
    evaluate_condition,
    evaluate_condition_with_diagnostics,
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


def test_prior_high_low_excludes_current_bar_and_supports_signed_distance_operator():
    high_value, high_metric, high_warning = evaluate_condition(
        _bars([100, 102, 105, 106]),
        {
            "kind": "prior_high_low",
            "params": {
                "lookback": 3,
                "direction": "high",
                "operator": "gte",
                "threshold": 0.0,
            },
        },
    )
    low_value, low_metric, low_warning = evaluate_condition(
        _bars([100, 98, 95, 94]),
        {
            "kind": "prior_high_low",
            "params": {
                "lookback": 3,
                "direction": "low",
                "operator": "lte",
                "threshold": 0.0,
            },
        },
    )

    assert high_value is True
    assert high_metric is not None and abs(high_metric - (106 / 105 - 1)) < 1e-12
    assert high_warning is None
    assert low_value is True
    assert low_metric is not None and abs(low_metric - (94 / 95 - 1)) < 1e-12
    assert low_warning is None


def test_prior_high_low_history_preserves_exclusions_and_state_changes():
    points = evaluate_breadth_history(
        [BreadthMember(1, "A", "A")],
        {1: _bars([100, 101, 103, 102, 105])},
        {
            "kind": "prior_high_low",
            "params": {
                "lookback": 2,
                "direction": "high",
                "operator": "gte",
                "threshold": 0.0,
            },
        },
        limit=10,
    )

    assert points[0]["members"][0].exclusion_code == "insufficient_history"
    assert points[-1]["members"][0].value is True
    assert points[-1]["members"][0].diagnostics[0].kind == "prior_high_low"


def test_series_comparison_compares_member_and_reference_fields_without_forward_fill():
    member = _bars([100, 110])
    reference = _bars([100, 105])
    value, metric, warning = evaluate_condition(
        member,
        {
            "kind": "series_comparison",
            "params": {
                "field": "return",
                "target_field": "return",
                "relation": "difference",
                "operator": "gte",
                "threshold": 0.04,
            },
        },
        benchmark_bars=reference,
    )

    assert value is True
    assert metric is not None and abs(metric - (0.10 - 0.05)) < 1e-12
    assert warning is None

    reference[-1].ts = member[-1].ts - timedelta(days=1)
    _, _, warning = evaluate_condition(
        member,
        {"kind": "series_comparison", "params": {"field": "close"}},
        benchmark_bars=reference,
    )
    assert warning == "unaligned_reference"


def test_series_comparison_history_requires_reference_at_each_timestamp():
    member = _bars([100, 101, 103, 102])
    reference = _bars([100, 100.5, 101, 101.5])
    reference[-1].ts = member[-1].ts - timedelta(days=1)
    points = evaluate_breadth_history(
        [BreadthMember(1, "A", "A")],
        {1: member},
        {
            "kind": "series_comparison",
            "params": {"field": "return", "target_field": "return", "operator": "gte", "threshold": 0},
        },
        limit=10,
        benchmark_bars=reference,
    )

    assert points[-1]["members"][0].exclusion_code == "benchmark_missing_at_timestamp"
    assert points[-1]["members"][0].diagnostics[0].code == "benchmark_missing_at_timestamp"


def test_equal_reference_series_is_normalized_and_never_forward_fills_members():
    first = _bars([100, 110, 99])
    second = _bars([200, 210, 231])
    second[-1].ts = second[-1].ts + timedelta(days=1)
    series, summary = build_equal_reference_series({1: first, 2: second})

    # The first aligned return averages 10% and 5%; the later timestamp only has
    # the first member, so it remains a valid partial aggregate rather than using
    # the second member's stale prior bar.
    assert [point.ts for point in series] == [first[1].ts, first[2].ts, second[2].ts]
    assert abs(series[0].close - 107.5) < 1e-12
    assert summary["method"] == "derived_equal_weight_return_index"
    assert summary["alignment"] == "exact_timestamp_no_forward_fill"
    assert summary["member_count"] == 2


def test_event_condition_targets_local_events_and_distinguishes_unavailable_data():
    bars = _bars([100, 101])
    event_time = bars[-1].ts
    events = [SimpleNamespace(event_type="dividend", event_time=event_time)]
    value, metric, warning = evaluate_condition(
        bars,
        {
            "kind": "event",
            "params": {
                "event_type": "dividend",
                "lookback_days": 0,
                "operator": "gte",
                "threshold": 1,
            },
        },
        events=events,
    )
    assert value is True
    assert metric == 1.0
    assert warning is None

    missing_value, _, missing_warning = evaluate_condition(
        bars,
        {"kind": "event", "params": {"event_type": "any"}},
        events=None,
    )
    assert missing_value is None
    assert missing_warning == "event_data_unavailable"


def test_event_breadth_history_is_point_in_time_and_never_forward_fills_events():
    bars = _bars([100, 101, 102])
    events = [SimpleNamespace(event_type="split", event_time=bars[1].ts)]
    points = evaluate_breadth_history(
        [BreadthMember(1, "A", "A")],
        {1: bars},
        {"kind": "event", "params": {"event_type": "split"}},
        limit=10,
        events_by_instrument={1: events},
    )
    assert points[0]["members"][0].value is False
    assert points[1]["members"][0].value is True
    assert points[2]["members"][0].value is False


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


def test_history_clause_diagnostics_use_the_benchmark_missing_code_after_alignment():
    member_bars = _bars([100, 101, 102])
    benchmark_bars = _bars([100, 101])
    points = evaluate_breadth_history(
        [BreadthMember(1, "A", "A")],
        {1: member_bars},
        {
            "kind": "relative_strength",
            "params": {"lookback": 1, "operator": ">", "threshold": 0},
        },
        limit=10,
        benchmark_bars=benchmark_bars,
    )

    result = points[-1]["members"][0]
    assert result.exclusion_code == "benchmark_missing_at_timestamp"
    assert result.diagnostics[0].code == "benchmark_missing_at_timestamp"


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


def test_composite_condition_returns_structured_clause_diagnostics():
    condition = {
        "kind": "all",
        "params": {
            "conditions": [
                {"kind": "comparison", "params": {"field": "close", "threshold": 100}},
                {
                    "kind": "any",
                    "params": {
                        "conditions": [
                            {"kind": "comparison", "params": {"field": "return", "threshold": 0}},
                            {"kind": "comparison", "params": {"field": "close", "threshold": 200}},
                        ]
                    },
                },
            ]
        },
    }

    value, metric, warning, diagnostics = evaluate_condition_with_diagnostics(
        _bars([100, 102]), condition
    )

    assert value is True
    assert metric is not None
    assert warning is None
    assert [item.path for item in diagnostics] == [
        "$",
        "$.conditions[0]",
        "$.conditions[1]",
        "$.conditions[1].conditions[0]",
        "$.conditions[1].conditions[1]",
    ]
    assert [item.status for item in diagnostics] == ["pass", "pass", "pass", "pass", "fail"]
    assert diagnostics[-1].kind == "comparison"


def test_clause_diagnostics_preserve_exclusion_code_and_path():
    results, _ = evaluate_breadth(
        [BreadthMember(1, "A", "A")],
        {1: _bars([100])},
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

    assert results[0].diagnostics[0].status == "excluded"
    assert results[0].diagnostics[0].code == "condition_clause_excluded:0:insufficient_history"
    assert results[0].diagnostics[1].path == "$.conditions[0]"
    assert results[0].diagnostics[1].code == "insufficient_history"


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


def test_cross_sectional_percentile_ranks_members_before_aggregation():
    members = [
        BreadthMember(1, "LOW", "Low"),
        BreadthMember(2, "MID", "Mid"),
        BreadthMember(3, "HIGH", "High"),
    ]
    results, aggregate = evaluate_breadth(
        members,
        {1: _bars([1]), 2: _bars([2]), 3: _bars([3])},
        {
            "kind": "percentile",
            "target_scope": "cross_sectional",
            "params": {"field": "close", "percentile": 0.5, "operator": "gte"},
        },
    )

    assert [result.metric for result in results] == [1 / 3, 2 / 3, 1.0]
    assert [result.value for result in results] == [False, True, True]
    assert aggregate["eligible_count"] == 3
    assert aggregate["pass_count"] == 2
    assert aggregate["percentage"] == 2 / 3


def test_cross_sectional_history_ranks_only_members_with_a_current_bar():
    first = _bars([1, 2, 3])
    second = _bars([3, 2, 1])
    second = second[:2]
    points = evaluate_breadth_history(
        [BreadthMember(1, "A", "A"), BreadthMember(2, "B", "B")],
        {1: first, 2: second},
        {
            "kind": "percentile",
            "target_scope": "cross_sectional",
            "params": {"field": "close", "percentile": 0.5, "operator": "gte"},
        },
        limit=10,
    )

    latest = points[-1]
    assert latest["timestamp"] == first[-1].ts
    assert latest["eligible_count"] == 1
    by_symbol = {result.symbol: result for result in latest["members"]}
    assert by_symbol["A"].value is True
    assert by_symbol["B"].value is None
    assert by_symbol["B"].exclusion_code == "missing_bar_at_timestamp"


def test_cross_sectional_scope_never_silently_falls_back_to_member_evaluation():
    results, aggregate = evaluate_breadth(
        [BreadthMember(1, "A", "A")],
        {1: _bars([1, 2])},
        {
            "kind": "comparison",
            "target_scope": "cross_sectional",
            "params": {"field": "close", "operator": "gte", "threshold": 1},
        },
    )

    assert results[0].value is None
    assert results[0].exclusion_code == "cross_sectional_unsupported_condition"
    assert aggregate["eligible_count"] == 0
