import json
import resource

import pytest

from research_runner import runner
from research_runner.runner import execute_job, recover_orphaned_jobs, run_once


def test_runner_executes_only_validated_output_contract_in_its_own_process_module():
    result = execute_job({"source": "output.scalar('sample_size', 4)", "dataset": {}})
    assert result["status"] == "completed"
    assert result["artifacts"]["sample_size"] == {"type": "scalar", "value": 4}


def test_runner_exposes_bounded_python_builtins_without_host_access():
    result = execute_job(
        {
            "source": "values = [1, 2, 3]\noutput.scalar('count', len(values))\noutput.scalar('total', sum(values))\noutput.scalar('largest', max(values))",
            "dataset": {},
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["count"]["value"] == 3
    assert result["artifacts"]["total"]["value"] == 6
    assert result["artifacts"]["largest"]["value"] == 3


def test_runner_injects_json_parameters_into_single_and_batch_runs():
    single = execute_job(
        {
            "source": "output.scalar('threshold', parameters['threshold'])",
            "parameters": {"threshold": 42},
            "dataset": {},
        }
    )
    assert single["status"] == "completed"
    assert single["artifacts"]["threshold"]["value"] == 42
    batch = execute_job(
        {
            "source": "output.scalar('threshold', parameters['threshold'])",
            "parameters": {"threshold": 7},
            "output_contract": "scalar",
            "dataset": {"datasets": [{"instrument_id": 1, "symbol": "SPY", "closes": [1]}]},
        }
    )
    assert batch["status"] == "completed"
    assert batch["artifacts"]["batch_cells"]["value"]["cells"][0]["value"] == 7.0


def test_runner_executes_declared_event_signals_across_prepared_universe_cells():
    result = execute_job(
        {
            "source": "output.events('signals', [{'timestamp': market.timestamps()[-1], 'kind': 'signal'}])",
            "output_contract": "events",
            "dataset": {
                "datasets": [
                    {
                        "instrument_id": 1,
                        "symbol": "SPY",
                        "timestamps": ["2024-01-01T00:00:00+00:00", "2024-01-02T00:00:00+00:00"],
                        "closes": [100, 101],
                    },
                    {
                        "instrument_id": 2,
                        "symbol": "XLK",
                        "timestamps": ["2024-01-01T00:00:00+00:00", "2024-01-02T00:00:00+00:00"],
                        "closes": [200, 202],
                    },
                ],
            },
        }
    )
    assert result["status"] == "completed"
    cells = result["artifacts"]["batch_cells"]["value"]["cells"]
    assert [cell["symbol"] for cell in cells] == ["SPY", "XLK"]
    assert cells[0]["value"][0]["timestamp"] == "2024-01-02T00:00:00+00:00"


def test_runner_rejects_non_object_parameters():
    result = execute_job({"source": "output.scalar('x', 1)", "parameters": [1], "dataset": {}})
    assert result["status"] == "failed"
    assert result["diagnostics"][0]["code"] == "invalid_parameters"


def test_runner_executes_structured_study_over_a_prepared_universe():
    result = execute_job(
        {
            "source": "rows = [{'symbol': item['symbol'], 'last': item['closes'][-1]} for item in market.universe()]\noutput.table('ranking', rows)\noutput.histogram('distribution', [row['last'] for row in rows], 2)\noutput.events('events', [{'symbol': row['symbol'], 'timestamp': '2024-01-02T00:00:00+00:00', 'kind': 'selected'} for row in rows])",
            "output_contract": "study",
            "dataset": {
                "datasets": [
                    {"instrument_id": 1, "symbol": "SPY", "closes": [100, 101]},
                    {"instrument_id": 2, "symbol": "XLK", "closes": [200, 205]},
                ]
            },
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["ranking"]["value"] == [
        {"symbol": "SPY", "last": 101},
        {"symbol": "XLK", "last": 205},
    ]
    assert result["artifacts"]["distribution"]["value"]["sample_size"] == 2
    assert len(result["artifacts"]["events"]["value"]) == 2


def test_runner_computes_cross_sectional_rank_and_breadth_from_declared_bars():
    result = execute_job(
        {
            "source": "ranking = research.cross_sectional_rank(dataset, 2)\nbreadth = research.breadth_snapshot(dataset, 2)\noutput.table('ranking', ranking)\noutput.bar('returns', [row['symbol'] for row in ranking], [row['return'] for row in ranking])\noutput.scalar('above', breadth['above_count'])\noutput.scalar('percent_above', breadth['percent_above'])",
            "output_contract": "study",
            "dataset": {
                "datasets": [
                    {"instrument_id": 1, "symbol": "SPY", "closes": [100, 101, 104]},
                    {"instrument_id": 2, "symbol": "XLK", "closes": [100, 99, 98]},
                    {"instrument_id": 3, "symbol": "XLE", "closes": [100, 101, 102]},
                ]
            },
        }
    )
    assert result["status"] == "completed"
    assert [row["symbol"] for row in result["artifacts"]["ranking"]["value"]] == [
        "SPY",
        "XLE",
        "XLK",
    ]
    assert result["artifacts"]["above"]["value"] == 2
    assert result["artifacts"]["percent_above"]["value"] == (2 / 3) * 100


def test_runner_computes_generic_breadth_snapshot_and_history_from_one_condition():
    timestamps = ["2026-01-01", "2026-01-02", "2026-01-03"]
    result = execute_job(
        {
            "source": (
                "condition = {'kind': 'above_moving_average', 'params': {'period': 2}}\n"
                "snapshot = research.breadth_condition(dataset, condition)\n"
                "history = research.breadth_condition(dataset, condition, True)\n"
                "output.scalar('snapshot_percentage', snapshot['percentage'])\n"
                "output.scalar('history_sample_size', history['sample_size'])\n"
                "output.series('history_percentage', [point['percentage'] for point in history['points']])\n"
                "output.table('current_rows', snapshot['rows'])"
            ),
            "output_contract": "study",
            "dataset": {
                "timestamps": timestamps,
                "datasets": [
                    {
                        "instrument_id": 1,
                        "symbol": "SPY",
                        "timestamps": timestamps,
                        "closes": [100, 101, 102],
                    },
                    {
                        "instrument_id": 2,
                        "symbol": "XLK",
                        "timestamps": timestamps,
                        "closes": [100, 99, 98],
                    },
                ],
            },
        }
    )

    assert result["status"] == "completed"
    assert result["artifacts"]["snapshot_percentage"]["value"] == 0.5
    assert result["artifacts"]["history_sample_size"]["value"] == 3
    assert result["artifacts"]["history_percentage"]["value"]["values"] == [None, 0.5, 0.5]
    assert result["artifacts"]["current_rows"]["value"][-1]["value"] is False


def test_runner_computes_cross_sectional_percentile_breadth_for_snapshot_and_history():
    timestamps = ["2026-01-01", "2026-01-02", "2026-01-03"]
    result = execute_job(
        {
            "source": (
                "condition = {'kind': 'percentile', 'target_scope': 'cross_sectional', 'params': "
                "{'field': 'close', 'percentile': 0.5, 'operator': 'gte'}}\n"
                "snapshot = research.breadth_condition(dataset, condition)\n"
                "history = research.breadth_condition(dataset, condition, True)\n"
                "output.scalar('snapshot_percentage', snapshot['percentage'])\n"
                "output.series('history_percentage', [point['percentage'] for point in history['points']])\n"
                "output.table('snapshot_rows', snapshot['rows'])"
            ),
            "output_contract": "study",
            "dataset": {
                "timestamps": timestamps,
                "datasets": [
                    {"instrument_id": 1, "symbol": "A", "timestamps": timestamps, "closes": [1, 2, 3]},
                    {"instrument_id": 2, "symbol": "B", "timestamps": timestamps, "closes": [3, 2, 1]},
                    {"instrument_id": 3, "symbol": "C", "timestamps": timestamps, "closes": [2, 2, 2]},
                ],
            },
        }
    )

    assert result["status"] == "completed"
    assert result["artifacts"]["snapshot_percentage"]["value"] == 2 / 3
    assert result["artifacts"]["history_percentage"]["value"]["values"] == [2 / 3, 1.0, 2 / 3]
    rows = {row["symbol"]: row for row in result["artifacts"]["snapshot_rows"]["value"]}
    assert rows["A"]["metric"] == 1.0
    assert rows["A"]["value"] is True
    assert rows["B"]["value"] is False


def test_runner_computes_cross_sectional_statistic_breadth_for_snapshot_and_history():
    timestamps = ["2026-01-01", "2026-01-02"]
    result = execute_job(
        {
            "source": (
                "condition = {'kind': 'cross_sectional_statistic', 'target_scope': 'cross_sectional', 'params': "
                "{'field': 'close', 'statistic': 'mean', 'operator': 'gte', 'threshold': 0}}\n"
                "snapshot = research.breadth_condition(dataset, condition)\n"
                "history = research.breadth_condition(dataset, condition, True)\n"
                "output.scalar('group_mean', snapshot['rows'][1]['metric'])\n"
                "output.scalar('snapshot_percentage', snapshot['percentage'])\n"
                "output.series('history_percentage', [point['percentage'] for point in history['points']])"
            ),
            "output_contract": "study",
            "dataset": {
                "timestamps": timestamps,
                "datasets": [
                    {"instrument_id": 1, "symbol": "A", "timestamps": timestamps, "closes": [1, 3]},
                    {"instrument_id": 2, "symbol": "B", "timestamps": timestamps, "closes": [2, 2]},
                    {"instrument_id": 3, "symbol": "C", "timestamps": timestamps, "closes": [3, 1]},
                ],
            },
        }
    )

    assert result["status"] == "completed"
    assert result["artifacts"]["group_mean"]["value"] == 0.0
    assert result["artifacts"]["snapshot_percentage"]["value"] == 2 / 3
    assert result["artifacts"]["history_percentage"]["value"]["values"] == [2 / 3, 2 / 3]


def test_runner_composes_nested_cross_sectional_and_member_breadth_conditions():
    timestamps = ["2026-01-01", "2026-01-02", "2026-01-03"]
    result = execute_job(
        {
            "source": (
                "condition = {'kind': 'all', 'params': {'conditions': ["
                "{'kind': 'percentile', 'target_scope': 'cross_sectional', 'params': "
                "{'field': 'close', 'percentile': 0.5, 'operator': 'gte'}},"
                "{'kind': 'comparison', 'params': {'field': 'close', 'operator': 'gte', 'threshold': 2.5}}]}}\n"
                "snapshot = research.breadth_condition(dataset, condition)\n"
                "history = research.breadth_condition(dataset, condition, True)\n"
                "output.scalar('snapshot_percentage', snapshot['percentage'])\n"
                "output.series('history_percentage', [point['percentage'] for point in history['points']])\n"
                "output.table('snapshot_rows', snapshot['rows'])"
            ),
            "output_contract": "study",
            "dataset": {
                "timestamps": timestamps,
                "datasets": [
                    {"instrument_id": 1, "symbol": "A", "timestamps": timestamps, "closes": [1, 2, 3]},
                    {"instrument_id": 2, "symbol": "B", "timestamps": timestamps, "closes": [3, 2, 1]},
                    {"instrument_id": 3, "symbol": "C", "timestamps": timestamps, "closes": [2, 2, 2]},
                ],
            },
        }
    )

    assert result["status"] == "completed"
    assert result["artifacts"]["snapshot_percentage"]["value"] == 1 / 3
    assert result["artifacts"]["history_percentage"]["value"]["values"] == [1 / 3, 0.0, 1 / 3]
    rows = {row["symbol"]: row for row in result["artifacts"]["snapshot_rows"]["value"]}
    assert rows["A"]["value"] is True
    assert rows["B"]["value"] is False
    assert rows["C"]["value"] is False


def test_runner_supports_composite_breadth_conditions_and_scalar_comparisons():
    result = execute_job(
        {
            "source": (
                "condition = {'kind': 'all', 'params': {'conditions': ["
                "{'kind': 'comparison', 'params': {'field': 'return', 'operator': '>', 'threshold': 0}},"
                "{'kind': 'not', 'params': {'conditions': [{'kind': 'comparison', 'params': {'field': 'close', 'operator': '<', 'threshold': 100}}]}}]}}\n"
                "breadth = research.breadth_condition(dataset, condition)\n"
                "output.scalar('percentage', breadth['percentage'])\n"
                "output.table('rows', breadth['rows'])"
            ),
            "output_contract": "study",
            "dataset": {
                "datasets": [
                    {"instrument_id": 1, "symbol": "A", "closes": [100, 101, 102]},
                    {"instrument_id": 2, "symbol": "B", "closes": [100, 99, 98]},
                ]
            },
        }
    )

    assert result["status"] == "completed"
    assert result["artifacts"]["percentage"]["value"] == 0.5
    assert result["artifacts"]["rows"]["value"][0]["value"] is True
    assert result["artifacts"]["rows"]["value"][1]["value"] is False


def test_runner_executes_arbitrary_python_breadth_predicate_in_current_batch_mode():
    source = (
        "condition = parameters['condition']\n"
        "snapshot = research.breadth_condition({'datasets': [dataset]}, condition)\n"
        "row = snapshot['rows'][0]\n"
        "output.boolean('match', row['value'] is True, metric=row['metric'], exclusion=row.get('exclusion'))"
    )
    result = execute_job(
        {
            "source": source,
            "output_contract": "boolean",
            "parameters": {
                "condition": {"kind": "above_moving_average", "params": {"period": 2}}
            },
            "dataset": {
                "datasets": [
                    {"instrument_id": 1, "symbol": "A", "closes": [100, 101]},
                    {"instrument_id": 2, "symbol": "B", "closes": [100, 99]},
                ]
            },
        }
    )

    assert result["status"] == "completed"
    cells = result["artifacts"]["batch_cells"]["value"]["cells"]
    assert [cell["value"] for cell in cells] == [True, False]


def test_runner_executes_arbitrary_python_breadth_predicate_over_aligned_history():
    timestamps = ["2026-01-01", "2026-01-02", "2026-01-03"]
    source = (
        "condition = parameters['condition']\n"
        "snapshot = research.breadth_condition({'datasets': [dataset]}, condition)\n"
        "row = snapshot['rows'][0]\n"
        "output.boolean('match', row['value'] is True, metric=row['metric'], exclusion=row.get('exclusion'))"
    )
    result = execute_job(
        {
            "source": source,
            "output_contract": "boolean",
            "execution_mode": "breadth_history",
            "history_limit": 3,
            "parameters": {
                "condition": {"kind": "above_moving_average", "params": {"period": 2}}
            },
            "dataset": {
                "datasets": [
                    {
                        "instrument_id": 1,
                        "symbol": "A",
                        "timestamps": timestamps,
                        "closes": [100, 101, 102],
                    },
                    {
                        "instrument_id": 2,
                        "symbol": "B",
                        "timestamps": timestamps,
                        "closes": [100, 99, 98],
                    },
                ]
            },
        }
    )

    assert result["status"] == "completed"
    points = result["artifacts"]["breadth_history"]["value"]["points"]
    assert len(points) == 3
    assert all(cell["status"] == "excluded" for cell in points[0]["cells"])
    assert [cell["value"] for cell in points[-1]["cells"]] == [True, False]


def test_runner_evaluates_numeric_python_series_target_in_current_batch_mode():
    result = execute_job(
        {
            "source": "output.series('target', market.close())",
            "output_contract": "series",
            "series_target": {"operator": "gte", "threshold": 100},
            "dataset": {
                "datasets": [
                    {"instrument_id": 1, "symbol": "A", "closes": [100, 101]},
                    {"instrument_id": 2, "symbol": "B", "closes": [99, 98]},
                ]
            },
        }
    )

    assert result["status"] == "completed"
    cells = result["artifacts"]["batch_cells"]["value"]["cells"]
    assert [cell["value"] for cell in cells] == [True, False]
    assert [cell["metric"] for cell in cells] == [101.0, 98.0]


def test_runner_evaluates_numeric_python_series_target_over_aligned_history():
    timestamps = ["2026-01-01", "2026-01-02", "2026-01-03"]
    result = execute_job(
        {
            "source": "output.series('target', market.close())",
            "output_contract": "series",
            "execution_mode": "breadth_history",
            "history_limit": 3,
            "series_target": {"operator": "gte", "threshold": 100.5},
            "dataset": {
                "datasets": [
                    {
                        "instrument_id": 1,
                        "symbol": "A",
                        "timestamps": timestamps,
                        "closes": [100, 101, 102],
                    }
                ]
            },
        }
    )

    assert result["status"] == "completed"
    points = result["artifacts"]["breadth_history"]["value"]["points"]
    assert [cell["value"] for cell in points[0]["cells"]] == [False]
    assert [cell["value"] for cell in points[1]["cells"]] == [True]
    assert [cell["metric"] for cell in points[-1]["cells"]] == [102.0]


def test_runner_applies_cross_sectional_group_statistic_to_python_series_current_batch():
    result = execute_job(
        {
            "source": "output.series('target', market.close())",
            "output_contract": "series",
            "series_target": {
                "scope": "cross_sectional",
                "statistic": "mean",
                "operator": "gte",
                "threshold": 0,
            },
            "dataset": {
                "datasets": [
                    {"instrument_id": 1, "symbol": "A", "closes": [99, 101]},
                    {"instrument_id": 2, "symbol": "B", "closes": [100, 100]},
                    {"instrument_id": 3, "symbol": "C", "closes": [101, 99]},
                ]
            },
        }
    )

    assert result["status"] == "completed"
    payload = result["artifacts"]["batch_cells"]["value"]
    assert payload["group_value"] == 100.0
    assert [cell["metric"] for cell in payload["cells"]] == [1.0, 0.0, -1.0]
    assert [cell["value"] for cell in payload["cells"]] == [True, True, False]


def test_runner_applies_cross_sectional_group_statistic_to_python_series_history():
    timestamps = ["2026-01-01", "2026-01-02"]
    result = execute_job(
        {
            "source": "output.series('target', market.close())",
            "output_contract": "series",
            "execution_mode": "breadth_history",
            "history_limit": 2,
            "series_target": {
                "scope": "cross_sectional",
                "statistic": "median",
                "operator": "gte",
                "threshold": 0,
            },
            "dataset": {
                "datasets": [
                    {"instrument_id": 1, "symbol": "A", "timestamps": timestamps, "closes": [10, 12]},
                    {"instrument_id": 2, "symbol": "B", "timestamps": timestamps, "closes": [10, 10]},
                    {"instrument_id": 3, "symbol": "C", "timestamps": timestamps, "closes": [10, 8]},
                ]
            },
        }
    )

    assert result["status"] == "completed"
    points = result["artifacts"]["breadth_history"]["value"]["points"]
    assert [point["group_value"] for point in points] == [10.0, 10.0]
    assert [[cell["value"] for cell in point["cells"]] for point in points] == [
        [True, True, True],
        [True, True, False],
    ]


def test_runner_composes_isolated_python_series_leaf_with_member_predicate_tree():
    result = execute_job(
        {
            "source": "output.scalar('unused', 1)",
            "output_contract": "boolean",
            "condition_tree": {
                "kind": "all",
                "params": {
                    "conditions": [
                        {
                            "kind": "python_series",
                            "params": {
                                "source": "output.series('target', market.close())",
                                "operator": "gte",
                                "threshold": 100,
                            },
                        },
                        {
                            "kind": "comparison",
                            "params": {"field": "return", "operator": "gte", "threshold": 0},
                        },
                    ]
                },
            },
            "dataset": {
                "datasets": [
                    {"instrument_id": 1, "symbol": "A", "closes": [100, 101]},
                    {"instrument_id": 2, "symbol": "B", "closes": [100, 99]},
                ]
            },
        }
    )

    assert result["status"] == "completed"
    cells = result["artifacts"]["batch_cells"]["value"]["cells"]
    assert [cell["value"] for cell in cells] == [True, False]


def test_runner_computes_transparent_ninety_ninety_breadth_and_exclusions():
    result = execute_job(
        {
            "source": (
                "breadth = research.breadth_thrust(dataset, 90)\n"
                "output.scalar('price', breadth['percent_price_advancing'])\n"
                "output.scalar('volume', breadth['percent_volume_advancing'])\n"
                "output.boolean('qualifies', breadth['qualifies'])\n"
                "output.table('rows', breadth['rows'])\n"
                "output.table('exclusions', breadth['exclusions'])"
            ),
            "output_contract": "study",
            "dataset": {
                "datasets": [
                    {
                        "instrument_id": 1,
                        "symbol": "SPY",
                        "closes": [100, 101],
                        "volumes": [1000, 1200],
                    },
                    {
                        "instrument_id": 2,
                        "symbol": "XLK",
                        "closes": [100, 102],
                        "volumes": [1000, 1100],
                    },
                    {
                        "instrument_id": 3,
                        "symbol": "XLE",
                        "closes": [100, 99],
                        "volumes": [1000, 1200],
                    },
                    {
                        "instrument_id": 4,
                        "symbol": "BAD",
                        "closes": [100, 101],
                        "volumes": [1000, None],
                    },
                ],
            },
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["price"]["value"] == (2 / 3) * 100
    assert result["artifacts"]["volume"]["value"] == 100.0
    assert result["artifacts"]["qualifies"]["value"] is False
    assert result["artifacts"]["exclusions"]["value"] == [
        {"symbol": "BAD", "code": "invalid_close_or_volume"}
    ]


def test_runner_rejects_invalid_ninety_ninety_threshold():
    result = execute_job(
        {
            "source": "research.breadth_thrust(dataset, 101)",
            "output_contract": "study",
            "dataset": {"datasets": []},
        }
    )
    assert result["status"] == "failed"
    assert "threshold must be between 0 and 100" in result["diagnostics"][0]["message"]


def test_runner_computes_historical_ninety_ninety_series_and_occurrences():
    timestamps = ["2026-01-01", "2026-01-02", "2026-01-03"]
    result = execute_job(
        {
            "source": (
                "breadth = research.breadth_thrust_history(dataset, 90)\n"
                "output.series('price', breadth['price_percentages'])\n"
                "output.series('volume', breadth['volume_percentages'])\n"
                "output.boolean('current', breadth['qualifies'])\n"
                "output.events('events', research.occurrences(dataset, breadth['qualifying_indices'], 'thrust'))\n"
                "output.table('rows', breadth['rows'])\n"
                "output.table('exclusions', breadth['exclusions'])"
            ),
            "output_contract": "study",
            "dataset": {
                "symbol": "SPY",
                "timestamps": timestamps,
                "datasets": [
                    {
                        "instrument_id": 1,
                        "symbol": "SPY",
                        "timestamps": timestamps,
                        "closes": [100, 101, 102],
                        "volumes": [1000, 1100, 1200],
                    },
                    {
                        "instrument_id": 2,
                        "symbol": "XLK",
                        "timestamps": timestamps,
                        "closes": [100, 101, 100],
                        "volumes": [1000, 1100, 1000],
                    },
                ],
            },
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["price"]["value"]["values"] == [None, 100.0, 50.0]
    assert result["artifacts"]["volume"]["value"]["values"] == [None, 100.0, 50.0]
    assert result["artifacts"]["current"]["value"] is False
    assert result["artifacts"]["events"]["value"] == [
        {"symbol": "SPY", "timestamp": "2026-01-02", "kind": "thrust", "event_index": 1}
    ]
    assert result["artifacts"]["rows"]["value"][-1]["coverage"] == 2


def test_runner_excludes_historical_timestamp_mismatch_and_zero_volume():
    result = execute_job(
        {
            "source": "breadth = research.breadth_thrust_history(dataset, 90)\noutput.table('exclusions', breadth['exclusions'])",
            "output_contract": "study",
            "dataset": {
                "symbol": "SPY",
                "timestamps": ["2026-01-01", "2026-01-02"],
                "datasets": [
                    {
                        "symbol": "SPY",
                        "timestamps": ["2026-01-01", "2026-01-03"],
                        "closes": [100, 101],
                        "volumes": [1000, 1100],
                    },
                    {
                        "symbol": "XLK",
                        "timestamps": ["2026-01-01", "2026-01-02"],
                        "closes": [100, 101],
                        "volumes": [0, 1100],
                    },
                ],
            },
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["exclusions"]["value"] == [
        {"timestamp": "2026-01-02", "symbol": "SPY", "index": 1, "code": "timestamp_mismatch"},
        {"timestamp": "2026-01-02", "symbol": "XLK", "index": 1, "code": "zero_previous_volume"},
    ]


def test_runner_derives_aggregate_timestamp_axis_from_declared_instrument_data():
    timestamps = ["2026-01-01", "2026-01-02"]
    result = execute_job(
        {
            "source": (
                "breadth = research.breadth_thrust_history(dataset, 90)\n"
                "output.series('price', breadth['price_percentages'])\n"
                "output.events('events', research.occurrences(dataset, breadth['qualifying_indices'], 'thrust'))"
            ),
            "output_contract": "study",
            "dataset": {
                "datasets": [
                    {
                        "symbol": "SPY",
                        "timestamps": timestamps,
                        "closes": [100, 101],
                        "volumes": [1000, 1100],
                    },
                    {
                        "symbol": "XLK",
                        "timestamps": timestamps,
                        "closes": [100, 101],
                        "volumes": [1000, 1100],
                    },
                ],
            },
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["price"]["value"]["timestamps"] == timestamps
    assert result["artifacts"]["events"]["value"][0]["timestamp"] == "2026-01-02"


def test_runner_exposes_deterministic_stats_namespace_with_edge_contracts():
    result = execute_job(
        {
            "source": (
                "values = [1, 2, 3, 4]\n"
                "output.table('summary', [{'mean': stats.mean(values), 'median': stats.median(values), 'std': stats.std(values), 'p90': stats.percentile(values, 0.9)}])\n"
                "output.table('ranks', [{'value': value, 'rank': rank} for value, rank in zip(values, stats.ranks(values), strict=True)])\n"
                "output.series('rolling', stats.rolling(values, 2))\n"
                "output.scalar('correlation', stats.correlation(values, [2, 4, 6, 8]))\n"
                "output.table('regression', [stats.regression(values, [2, 4, 6, 8])])\n"
                "output.table('distribution', stats.distribution(values, 2))"
            ),
            "output_contract": "study",
            "dataset": {"timestamps": ["2024-01-01T00:00:00+00:00"] * 4},
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["summary"]["value"] == [
        {"mean": 2.5, "median": 2.5, "std": 1.118033988749895, "p90": 3.7}
    ]
    assert result["artifacts"]["ranks"]["value"] == [
        {"value": 1, "rank": 4},
        {"value": 2, "rank": 3},
        {"value": 3, "rank": 2},
        {"value": 4, "rank": 1},
    ]
    assert result["artifacts"]["rolling"]["value"]["values"] == [None, 1.5, 2.5, 3.5]
    assert result["artifacts"]["correlation"]["value"] == 1.0
    assert result["artifacts"]["regression"]["value"][0]["r_squared"] == 1.0
    assert result["artifacts"]["distribution"]["value"]["sample_size"] == 4


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("output.scalar('x', stats.percentile([1, 2], 2))", "probability must be between 0 and 1"),
        ("output.scalar('x', stats.rolling([1, 2], 0))", "period must be a positive integer"),
        ("output.scalar('x', stats.correlation([1], [1, 2]))", "same length"),
        ("output.scalar('x', stats.distribution([1, 2], 0))", "bins must be an integer"),
    ],
)
def test_runner_stats_namespace_reports_invalid_contracts(source, message):
    result = execute_job({"source": source, "dataset": {}})
    assert result["status"] == "failed"
    assert message in result["diagnostics"][0]["message"]


def test_runner_computes_conditional_outcomes_and_point_in_time_regimes():
    result = execute_job(
        {
            "source": (
                "outcomes = research.conditional_outcomes(dataset, [1, 2], [1, 2])\n"
                "regimes = research.regimes(dataset, 2, 0.02)\n"
                "output.table('outcomes', outcomes)\n"
                "output.table('regime_rows', regimes['rows'])\n"
                "output.table('regime_summary', [regimes['counts']])\n"
                "output.scalar('current_state', regimes['current']['state'])"
            ),
            "output_contract": "study",
            "dataset": {
                "symbol": "SPY",
                "timestamps": [f"2024-01-0{index}T00:00:00+00:00" for index in range(1, 7)],
                "closes": [100, 102, 101, 106, 105, 110],
            },
        }
    )
    assert result["status"] == "completed"
    outcomes = result["artifacts"]["outcomes"]["value"]
    assert outcomes[0]["horizon"] == 1
    assert outcomes[0]["sample_size"] == 2
    assert outcomes[0]["positive_count"] == 1
    assert outcomes[1]["sample_size"] == 2
    assert len(result["artifacts"]["regime_rows"]["value"]) == 4
    assert result["artifacts"]["regime_summary"]["value"] == [{"up": 3, "flat": 1, "down": 0}]
    assert result["artifacts"]["current_state"]["value"] == "up"


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            "output.table('x', research.conditional_outcomes(dataset, [0], [0]))",
            "horizons must be positive integers",
        ),
        (
            "output.table('x', research.regimes(dataset, 0))",
            "regime lookback must be a positive integer",
        ),
        (
            "output.table('x', research.regimes(dataset, 1, -1))",
            "threshold must be a finite non-negative number",
        ),
    ],
)
def test_runner_research_outcome_helpers_report_invalid_contracts(source, message):
    result = execute_job(
        {"source": source, "dataset": {"closes": [1, 2], "timestamps": ["a", "b"]}}
    )
    assert result["status"] == "failed"
    assert message in result["diagnostics"][0]["message"]


def test_runner_places_current_value_within_historical_distribution():
    result = execute_job(
        {
            "source": (
                "comparison = research.historical_comparison([1, 2, 3, 4], 3)\n"
                "empty = research.historical_comparison([])\n"
                "flat = research.historical_comparison([5, 5], 5)\n"
                "output.table('comparison', [comparison])\n"
                "output.table('empty', [empty])\n"
                "output.table('flat', [flat])"
            ),
            "output_contract": "study",
            "dataset": {},
        }
    )
    assert result["status"] == "completed"
    comparison = result["artifacts"]["comparison"]["value"][0]
    assert comparison["sample_size"] == 4
    assert comparison["percentile_rank"] == 75.0
    assert comparison["range_position"] == (2 / 3)
    assert comparison["z_score"] is not None
    assert result["artifacts"]["empty"]["value"][0]["sample_size"] == 0
    assert result["artifacts"]["flat"]["value"][0]["z_score"] is None


def test_runner_historical_comparison_rejects_non_numeric_current_value():
    result = execute_job(
        {
            "source": "output.table('x', [research.historical_comparison([1, 2], 'now')])",
            "dataset": {},
        }
    )
    assert result["status"] == "failed"
    assert "current value must be numeric" in result["diagnostics"][0]["message"]


def test_runner_emits_typed_boolean_artifacts():
    result = execute_job({"source": "output.boolean('qualifies', 2 > 1)", "dataset": {}})
    assert result["status"] == "completed"
    assert result["artifacts"]["qualifies"] == {"type": "boolean", "value": True}


def test_runner_restores_process_resource_limits_after_execution():
    cpu_before = resource.getrlimit(resource.RLIMIT_CPU)
    memory_before = resource.getrlimit(resource.RLIMIT_AS)

    result = execute_job({"source": "output.scalar('sample_size', 4)", "dataset": {}})

    assert result["status"] == "completed"
    assert resource.getrlimit(resource.RLIMIT_CPU) == cpu_before
    assert resource.getrlimit(resource.RLIMIT_AS) == memory_before


def test_runner_executes_prepared_universe_cells_without_network_access():
    result = execute_job(
        {
            "source": "output.scalar('last_close', market.close()[-1])",
            "output_contract": "scalar",
            "dataset": {
                "datasets": [
                    {"instrument_id": 1, "symbol": "SPY", "closes": [10, 11]},
                    {"instrument_id": 2, "symbol": "XLK", "closes": [20, 22]},
                ]
            },
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["batch_cells"] == {
        "type": "batch",
        "value": {
            "cells": [
                {"instrument_id": 1, "symbol": "SPY", "status": "completed", "value": 11.0},
                {"instrument_id": 2, "symbol": "XLK", "status": "completed", "value": 22.0},
            ]
        },
    }


def test_runner_selects_one_named_output_from_a_multi_output_typed_adapter():
    result = execute_job(
        {
            "source": "output.scalar('ignored', 1)\noutput.scalar('selected', 42)",
            "output_contract": "scalar",
            "output_name": "selected",
            "dataset": {"datasets": [{"instrument_id": 1, "symbol": "SPY", "closes": [10, 11]}]},
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["batch_cells"]["value"]["cells"] == [
        {"instrument_id": 1, "symbol": "SPY", "status": "completed", "value": 42.0},
    ]


def test_runner_batch_uses_one_outer_time_budget(monkeypatch):
    calls = []

    def fake_execute_single(source, dataset, hash_input, *, manage_timeout=True):
        calls.append(manage_timeout)
        return {"status": "completed", "artifacts": {"value": {"type": "scalar", "value": 1}}}

    monkeypatch.setattr(runner, "_execute_single", fake_execute_single)
    result = execute_job(
        {
            "source": "output.scalar('value', 1)",
            "output_contract": "scalar",
            "dataset": {
                "datasets": [
                    {"instrument_id": 1, "symbol": "SPY", "closes": [1]},
                    {"instrument_id": 2, "symbol": "XLK", "closes": [1]},
                ]
            },
        }
    )
    assert result["status"] == "completed"
    assert calls == [False, False]
    assert result["resource_usage"]["cell_count"] == 2


def test_runner_batch_reports_durable_progress_and_honors_cancellation():
    progress = []
    result = execute_job(
        {
            "source": "output.boolean('qualifies', True)",
            "output_contract": "boolean",
            "dataset": {
                "datasets": [
                    {"instrument_id": 1, "symbol": "SPY", "closes": [1]},
                    {"instrument_id": 2, "symbol": "XLK", "closes": [1]},
                ]
            },
        },
        progress_callback=progress.append,
        cancellation_check=lambda: len(progress) > 0,
    )
    assert result["status"] == "canceled"
    assert result["diagnostics"][0]["code"] == "batch_canceled"
    assert progress == [{"completed_cells": 0, "total_cells": 2, "status": "running"}]


def test_runner_rejects_forbidden_source_before_execution():
    result = execute_job({"source": "import os", "dataset": {}})
    assert result["status"] == "failed"
    assert result["diagnostics"][0]["code"] == "forbidden_syntax"


def test_runner_executes_factory_positive_close_streak_study():
    result = execute_job(
        {
            "source": "streaks = stats.positive_close_streaks(dataset)\noutput.scalar('current', streaks['current'])\noutput.table('records', streaks['records'])",
            "dataset": {
                "timestamps": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
                "closes": [10, 11, 12, 11],
            },
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["current"]["value"] == 0
    assert result["artifacts"]["records"]["value"] == [
        {"end_index": 2, "end_timestamp": "2026-01-03", "length": 2}
    ]


def test_runner_generic_streaks_supports_direction_and_inclusive_contracts():
    result = execute_job(
        {
            "source": "positive = stats.streaks([1, 2, 3, 2, 2, 1], 'positive')\nnegative = stats.streaks([1, 2, 3, 2, 2, 1], 'negative', True)\noutput.table('positive', positive['records'])\noutput.table('negative', negative)",
            "dataset": {"closes": [1, 2, 3, 2, 2, 1]},
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["positive"]["value"] == [
        {"start_index": 1, "end_index": 2, "length": 2}
    ]
    assert result["artifacts"]["negative"]["value"]["inclusive"] is True
    assert result["artifacts"]["negative"]["value"]["longest"] == 3


def test_runner_generic_streaks_rejects_unknown_direction():
    result = execute_job(
        {
            "source": "output.table('streaks', stats.streaks([1, 2], 'flat'))",
            "dataset": {"closes": [1, 2]},
        }
    )
    assert result["status"] == "failed"
    assert (
        "stats streak direction must be positive or negative" in result["diagnostics"][0]["message"]
    )


def test_runner_exposes_declared_benchmark_dataset():
    result = execute_job(
        {
            "source": "output.scalar('benchmark_last', benchmark['closes'][-1])",
            "dataset": {
                "symbol": "AAPL",
                "closes": [10, 11],
                "benchmark_dataset": {"symbol": "SPY", "closes": [100, 101]},
            },
            "output_contract": "scalar",
        }
    )

    assert result["status"] == "completed"
    assert result["artifacts"]["benchmark_last"]["value"] == 101


def test_runner_exposes_benchmark_through_market_namespace():
    result = execute_job(
        {
            "source": "output.scalar('benchmark_last', market.benchmark_close()[-1])\noutput.scalar('benchmark_name', market.benchmark_metadata()['name'])",
            "dataset": {
                "symbol": "AAPL",
                "closes": [10, 11],
                "benchmark_dataset": {
                    "status": "ready",
                    "symbol": "SPY",
                    "timestamps": ["2026-01-01", "2026-01-02"],
                    "opens": [100, 101],
                    "highs": [102, 103],
                    "lows": [99, 100],
                    "closes": [100, 101],
                    "volumes": [1000, 1200],
                    "vwaps": [100.5, 101.5],
                    "metadata": {"name": "SPY"},
                },
            },
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["benchmark_last"]["value"] == 101.0
    assert result["artifacts"]["benchmark_name"]["value"] == "SPY"


def test_runner_reports_unavailable_benchmark_explicitly():
    result = execute_job(
        {
            "source": "output.scalar('benchmark_last', market.benchmark_close()[-1])",
            "dataset": {
                "symbol": "AAPL",
                "closes": [10],
                "benchmark_dataset": {"status": "unavailable"},
            },
        }
    )
    assert result["status"] == "failed"
    assert "benchmark dataset is unavailable" in result["diagnostics"][0]["message"]


def test_runner_exposes_declared_ohlcv_fields_through_market_namespace():
    result = execute_job(
        {
            "source": "rows = market.ohlcv()\noutput.table('rows', rows)\noutput.scalar('volume', market.volume()[-1])\noutput.scalar('name', market.metadata()['name'])",
            "dataset": {
                "symbol": "SPY",
                "timestamps": ["2026-01-01", "2026-01-02"],
                "sessions": ["regular", "regular"],
                "metadata": {"name": "SPY"},
                "opens": [10, 11],
                "highs": [12, 13],
                "lows": [9, 10],
                "closes": [11, 12],
                "volumes": [1000, 1200],
                "vwaps": [10.5, 11.5],
            },
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["volume"]["value"] == 1200.0
    assert result["artifacts"]["name"]["value"] == "SPY"
    assert result["artifacts"]["rows"]["value"] == [
        {
            "timestamp": "2026-01-01",
            "session": "regular",
            "open": 10,
            "high": 12,
            "low": 9,
            "close": 11,
            "volume": 1000,
            "vwap": 10.5,
        },
        {
            "timestamp": "2026-01-02",
            "session": "regular",
            "open": 11,
            "high": 13,
            "low": 10,
            "close": 12,
            "volume": 1200,
            "vwap": 11.5,
        },
    ]


def test_runner_rejects_ohlcv_access_when_a_declared_field_is_missing():
    result = execute_job(
        {
            "source": "output.scalar('high', market.high()[-1])",
            "dataset": {"symbol": "SPY", "closes": [10]},
        }
    )
    assert result["status"] == "failed"
    assert "no high series" in result["diagnostics"][0]["message"]


def test_runner_emits_typed_histogram_for_study_distributions():
    result = execute_job(
        {
            "source": "output.histogram('distribution', [1, 2, 2, 3], 2, 2)",
            "dataset": {},
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["distribution"] == {
        "type": "histogram",
        "value": {
            "bins": [
                {"start": 1.0, "end": 2.0, "count": 1},
                {"start": 2.0, "end": 3.0, "count": 3},
            ],
            "sample_size": 4,
            "min": 1.0,
            "max": 3.0,
            "current": 2,
        },
    }


def test_runner_emits_typed_categorical_bars_for_study_rankings():
    result = execute_job(
        {"source": "output.bar('ranking', ['XLK', 'XLE'], [12.5, -3])", "dataset": {}}
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["ranking"] == {
        "type": "bar",
        "value": {"labels": ["XLK", "XLE"], "values": [12.5, -3.0]},
    }


def test_runner_emits_typed_range_band_with_aligned_timestamps():
    result = execute_job(
        {
            "source": "output.range('band', [1, 2], [3, 4], [2, 3])",
            "dataset": {"timestamps": ["2026-01-01", "2026-01-02"]},
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["band"] == {
        "type": "range",
        "value": {
            "timestamps": ["2026-01-01", "2026-01-02"],
            "lower": [1.0, 2.0],
            "upper": [3.0, 4.0],
            "center": [2.0, 3.0],
        },
    }


def test_runner_emits_typed_scatter_points_for_study_relationships():
    result = execute_job(
        {"source": "output.scatter('relationship', [1, 2, 3], [2, 4, 9])", "dataset": {}}
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["relationship"] == {
        "type": "scatter",
        "value": {"x": [1.0, 2.0, 3.0], "y": [2.0, 4.0, 9.0]},
    }


def test_runner_emits_typed_heatmap_matrix_for_study_relationships():
    result = execute_job(
        {
            "source": "output.heatmap('matrix', [[1, 2], [3, 4]], ['A', 'B'], ['X', 'Y'])",
            "dataset": {},
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["matrix"] == {
        "type": "heatmap",
        "value": {"rows": ["A", "B"], "columns": ["X", "Y"], "values": [[1.0, 2.0], [3.0, 4.0]]},
    }


def test_runner_emits_typed_dashboard_composed_from_named_artifacts():
    result = execute_job(
        {
            "source": "output.scalar('sample_size', 4)\noutput.series('trend', [1, 2])\noutput.dashboard('overview', [{'artifact': 'sample_size', 'title': 'Sample size', 'span': 4}, {'artifact': 'trend', 'title': 'Trend', 'span': 8}])",
            "dataset": {"timestamps": ["2026-01-01", "2026-01-02"]},
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["overview"] == {
        "type": "dashboard",
        "value": {
            "panels": [
                {"artifact": "sample_size", "title": "Sample size", "span": 4},
                {"artifact": "trend", "title": "Trend", "span": 8},
            ]
        },
    }


def test_runner_rejects_dashboard_references_to_missing_artifacts():
    result = execute_job(
        {"source": "output.dashboard('overview', [{'artifact': 'missing'}])", "dataset": {}}
    )

    assert result["status"] == "failed"
    assert result["diagnostics"] == [
        {
            "code": "dashboard_reference_error",
            "message": "dashboard 'overview' references unavailable artifact 'missing'",
        }
    ]


def test_runner_computes_point_in_time_forward_returns_for_study_events():
    result = execute_job(
        {
            "source": "rows = research.forward_returns(dataset, [1], [1, 2])\noutput.table('outcomes', rows)",
            "dataset": {
                "timestamps": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
                "closes": [10, 11, 12, 13],
            },
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["outcomes"]["value"] == [
        {
            "event_index": 1,
            "event_timestamp": "2026-01-02",
            "horizon": 1,
            "outcome_timestamp": "2026-01-03",
            "forward_return": (12 / 11) - 1,
        },
        {
            "event_index": 1,
            "event_timestamp": "2026-01-02",
            "horizon": 2,
            "outcome_timestamp": "2026-01-04",
            "forward_return": (13 / 11) - 1,
        },
    ]


def test_runner_emits_symbol_linked_occurrences_for_study_events():
    result = execute_job(
        {
            "source": "events = research.occurrences(dataset, [1], 'positive_close_streak')\noutput.events('streaks', events)",
            "dataset": {
                "symbol": "SPY",
                "timestamps": ["2026-01-01", "2026-01-02"],
                "closes": [10, 11],
            },
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["streaks"]["value"] == [
        {
            "symbol": "SPY",
            "timestamp": "2026-01-02",
            "kind": "positive_close_streak",
            "event_index": 1,
        }
    ]


def test_runner_exposes_restricted_numpy_and_pandas_facades():
    result = execute_job(
        {
            "source": "values = np.array([1, 2, 3])\nframe = pd.DataFrame([{'value': 1}, {'value': 3}])\noutput.scalar('mean', np.mean(values))\noutput.table('rows', frame)",
            "dataset": {},
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["mean"]["value"] == 2.0
    assert result["artifacts"]["rows"]["value"] == [{"value": 1}, {"value": 3}]


def test_runner_exposes_curated_scipy_statistics_without_imports():
    result = execute_job(
        {
            "source": "score = scipy.stats.percentileofscore([1, 2, 3, 4], 3)\noutput.scalar('percentile', score)",
            "dataset": {},
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["percentile"]["value"] == 75.0


def test_runner_exposes_curated_statsmodels_ols_without_module_internals():
    result = execute_job(
        {
            "source": "model = statsmodels.api.OLS([1, 2, 3], [[1, 1], [1, 2], [1, 3]])\nfit = model.fit()\noutput.scalar('r_squared', fit.rsquared)",
            "dataset": {},
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["r_squared"]["value"] == 1.0


def test_runner_rejects_numpy_and_pandas_file_access():
    result = execute_job({"source": "pd.read_csv('/tmp/secret.csv')", "dataset": {}})
    assert result["status"] == "failed"
    assert result["diagnostics"][0]["code"] == "forbidden_data_access"


@pytest.mark.parametrize(
    "source",
    [
        "__import__('os')",
        "eval('1 + 1')",
        "compile('1 + 1', '<user>', 'eval')",
        "globals()",
        "locals()",
        "vars()",
        "getattr(market, 'close')",
        "setattr(market, 'close', None)",
        "delattr(market, 'close')",
        "socket.socket()",
        "subprocess.Popen(['id'])",
    ],
)
def test_runner_rejects_filesystem_network_process_and_reflection_attempts(source):
    result = execute_job({"source": source, "dataset": {}})
    assert result["status"] == "failed"
    assert result["diagnostics"]
    assert result["diagnostics"][0]["code"] in {
        "forbidden_name",
        "forbidden_call",
        "unapproved_namespace",
    }


@pytest.mark.parametrize(
    "source",
    [
        "market.__dict__",
        "output.scalar.__globals__",
        "values = np.array([1])\nvalues.__array_interface__",
        "series = pd.Series([1])\nseries._value",
        "model = statsmodels.api.OLS([1, 2], [[1], [1]])\nmodel.__class__",
    ],
)
def test_runner_rejects_object_graph_and_wrapper_introspection(source):
    result = execute_job({"source": source, "dataset": {}})
    assert result["status"] == "failed"
    assert result["diagnostics"]


def test_runner_enforces_wall_time_limit_and_restores_signal(monkeypatch):
    previous_handler = __import__("signal").getsignal(__import__("signal").SIGALRM)
    monkeypatch.setattr(runner, "MAX_SECONDS", 1)
    result = execute_job({"source": "while True:\n    pass", "dataset": {}})
    assert result["status"] == "failed"
    assert result["diagnostics"][0]["code"] == "wall_time_limit"
    assert __import__("signal").getsignal(__import__("signal").SIGALRM) == previous_handler


def test_runner_reports_memory_limit_diagnostic(monkeypatch):
    def fail_compile(*_args, **_kwargs):
        raise MemoryError()

    monkeypatch.setattr(runner, "compile", fail_compile, raising=False)

    result = execute_job({"source": "output.scalar('value', 1)", "dataset": {}})

    assert result["status"] == "failed"
    assert result["diagnostics"][0]["code"] == "memory_limit"


@pytest.mark.parametrize(
    "expression",
    [
        "values.tofile('/tmp/secret.bin')",
        "values.dump('/tmp/secret.npy')",
        "values.setflags(write=True)",
        "values.resize(1)",
        "values.ctypes.data",
    ],
)
def test_runner_rejects_dangerous_methods_on_numpy_values(expression):
    result = execute_job({"source": f"values = np.array([1, 2])\n{expression}", "dataset": {}})
    assert result["status"] == "failed"
    assert result["diagnostics"][0]["code"] == "forbidden_attribute"


def test_runner_does_not_expose_pandas_wrapper_internals():
    result = execute_job(
        {
            "source": "series = pd.Series([1, 2])\noutput.table('raw', series._value)",
            "dataset": {},
        }
    )
    assert result["status"] == "failed"
    assert result["diagnostics"][0]["code"] == "forbidden_attribute"
    assert "Private and dunder attributes" in result["diagnostics"][0]["message"]


def test_runner_enforces_structured_output_row_limit(monkeypatch):
    monkeypatch.setattr(runner, "MAX_OUTPUT_ROWS", 2)
    result = execute_job({"source": "output.table('rows', [1, 2, 3])", "dataset": {}})
    assert result["status"] == "failed"
    assert result["diagnostics"][0]["code"] == "runtime_error"
    assert "row limit" in result["diagnostics"][0]["message"]


def test_runner_enforces_serialized_output_byte_limit(monkeypatch):
    monkeypatch.setattr(runner, "MAX_OUTPUT_BYTES", 32)
    result = execute_job({"source": "output.scalar('value', 'this is too large')", "dataset": {}})
    assert result["status"] == "failed"
    assert result["diagnostics"][0]["code"] == "output_size_limit"


def test_runner_converts_malformed_job_to_terminal_result_and_keeps_polling(tmp_path, monkeypatch):
    jobs = tmp_path / "jobs"
    results = tmp_path / "results"
    jobs.mkdir()
    monkeypatch.setattr(runner, "JOB_DIR", jobs)
    monkeypatch.setattr(runner, "RESULT_DIR", results)
    (jobs / "42.json").write_text("not-json")

    run_once(jobs / "42.json")

    payload = json.loads((results / "42.json").read_text())
    assert payload["status"] == "failed"
    assert payload["diagnostics"][0]["code"] == "job_payload_invalid"
    assert (jobs / "42.processed").exists()


def test_runner_recovers_claimed_job_after_worker_restart(tmp_path, monkeypatch):
    jobs = tmp_path / "jobs"
    results = tmp_path / "results"
    jobs.mkdir()
    results.mkdir()
    monkeypatch.setattr(runner, "JOB_DIR", jobs)
    monkeypatch.setattr(runner, "RESULT_DIR", results)
    (jobs / "99.running").write_text('{"source":"output.scalar(\'ok\', 1)"}')
    (jobs / "99.cancel").write_text("")
    (results / "99.progress.json").write_text('{"status":"running"}')

    recover_orphaned_jobs()

    assert (jobs / "99.json").exists()
    assert not (jobs / "99.running").exists()
    assert not (jobs / "99.cancel").exists()
    assert not (results / "99.progress.json").exists()


def test_runner_exposes_only_declared_market_symbol_and_structured_ta_series():
    result = execute_job(
        {
            "source": "trend = ta.sma(market.close('SPY'), 2)\noutput.series('trend', trend)",
            "dataset": {
                "symbol": "SPY",
                "timestamps": ["2026-01-01", "2026-01-02", "2026-01-03"],
                "closes": [10, 12, 14],
            },
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["trend"] == {
        "type": "series",
        "value": {
            "timestamps": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "values": [None, 11.0, 13.0],
        },
    }


def test_runner_exposes_canonical_indicator_facade_for_visual_conditions():
    result = execute_job(
        {
            "source": "rsi = ta.indicator('rsi', {'period': 2}, 'rsi')\noutput.boolean('match', len(rsi) == 4 and rsi[-1] > 50)",
            "dataset": {
                "symbol": "SPY",
                "timestamps": [
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-02T00:00:00+00:00",
                    "2026-01-03T00:00:00+00:00",
                    "2026-01-04T00:00:00+00:00",
                ],
                "opens": [10, 11, 12, 13],
                "highs": [11, 12, 13, 14],
                "lows": [9, 10, 11, 12],
                "closes": [10, 11, 12, 13],
                "volumes": [100, 100, 100, 100],
                "vwaps": [10, 11, 12, 13],
            },
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["match"] == {"type": "boolean", "value": True}


def test_runner_rejects_market_access_outside_the_prepared_dataset():
    result = execute_job(
        {
            "source": "output.series('close', market.close('QQQ'))",
            "dataset": {"symbol": "SPY", "closes": [10]},
        }
    )
    assert result["status"] == "failed"
    assert "not declared" in result["diagnostics"][0]["message"]


def test_runner_normalizes_only_declared_symbol_events():
    result = execute_job(
        {
            "source": "output.events('signals', [{'timestamp': '2026-01-02', 'kind': 'positive_close'}])",
            "dataset": {"symbol": "SPY"},
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["signals"] == {
        "type": "events",
        "value": [{"timestamp": "2026-01-02", "kind": "positive_close", "symbol": "SPY"}],
    }


def test_runner_rejects_event_for_undeclared_symbol():
    result = execute_job(
        {
            "source": "output.events('signals', [{'timestamp': '2026-01-02', 'symbol': 'QQQ'}])",
            "dataset": {"symbol": "SPY"},
        }
    )
    assert result["status"] == "failed"
    assert "not declared" in result["diagnostics"][0]["message"]
