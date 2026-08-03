import resource

from research_runner import runner
from research_runner.runner import execute_job


def test_runner_executes_only_validated_output_contract_in_its_own_process_module():
    result = execute_job({"source": "output.scalar('sample_size', 4)", "dataset": {}})
    assert result["status"] == "completed"
    assert result["artifacts"]["sample_size"] == {"type": "scalar", "value": 4}


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
            "dataset": {"datasets": [
                {"instrument_id": 1, "symbol": "SPY", "closes": [10, 11]},
                {"instrument_id": 2, "symbol": "XLK", "closes": [20, 22]},
            ]},
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["batch_cells"] == {
        "type": "batch",
        "value": {"cells": [
            {"instrument_id": 1, "symbol": "SPY", "status": "completed", "value": 11.0},
            {"instrument_id": 2, "symbol": "XLK", "status": "completed", "value": 22.0},
        ]},
    }


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
            "dataset": {"datasets": [
                {"instrument_id": 1, "symbol": "SPY", "closes": [1]},
                {"instrument_id": 2, "symbol": "XLK", "closes": [1]},
            ]},
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
            "dataset": {"datasets": [
                {"instrument_id": 1, "symbol": "SPY", "closes": [1]},
                {"instrument_id": 2, "symbol": "XLK", "closes": [1]},
            ]},
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
        {"event_index": 1, "event_timestamp": "2026-01-02", "horizon": 1, "outcome_timestamp": "2026-01-03", "forward_return": (12 / 11) - 1},
        {"event_index": 1, "event_timestamp": "2026-01-02", "horizon": 2, "outcome_timestamp": "2026-01-04", "forward_return": (13 / 11) - 1},
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
    assert result["artifacts"]["streaks"]["value"] == [{
        "symbol": "SPY",
        "timestamp": "2026-01-02",
        "kind": "positive_close_streak",
        "event_index": 1,
    }]


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


def test_runner_rejects_numpy_and_pandas_file_access():
    result = execute_job({"source": "pd.read_csv('/tmp/secret.csv')", "dataset": {}})
    assert result["status"] == "failed"
    assert result["diagnostics"][0]["code"] == "forbidden_data_access"


def test_runner_does_not_expose_pandas_wrapper_internals():
    result = execute_job({
        "source": "series = pd.Series([1, 2])\noutput.table('raw', series._value)",
        "dataset": {},
    })
    assert result["status"] == "failed"
    assert result["diagnostics"][0]["code"] == "runtime_error"
    assert "private wrapper attributes" in result["diagnostics"][0]["message"]


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
