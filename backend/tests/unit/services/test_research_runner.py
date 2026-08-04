import json
import resource

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


def test_runner_rejects_non_object_parameters():
    result = execute_job({"source": "output.scalar('x', 1)", "parameters": [1], "dataset": {}})
    assert result["status"] == "failed"
    assert result["diagnostics"][0]["code"] == "invalid_parameters"


def test_runner_executes_structured_study_over_a_prepared_universe():
    result = execute_job(
        {
            "source": "rows = [{'symbol': item['symbol'], 'last': item['closes'][-1]} for item in market.universe()]\noutput.table('ranking', rows)\noutput.histogram('distribution', [row['last'] for row in rows], 2)\noutput.events('events', [{'symbol': row['symbol'], 'timestamp': '2024-01-02T00:00:00+00:00', 'kind': 'selected'} for row in rows])",
            "output_contract": "study",
            "dataset": {"datasets": [
                {"instrument_id": 1, "symbol": "SPY", "closes": [100, 101]},
                {"instrument_id": 2, "symbol": "XLK", "closes": [200, 205]},
            ]},
        }
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["ranking"]["value"] == [{"symbol": "SPY", "last": 101}, {"symbol": "XLK", "last": 205}]
    assert result["artifacts"]["distribution"]["value"]["sample_size"] == 2
    assert len(result["artifacts"]["events"]["value"]) == 2


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
                    "opens": [100, 101], "highs": [102, 103], "lows": [99, 100],
                    "closes": [100, 101], "volumes": [1000, 1200], "vwaps": [100.5, 101.5],
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
            "dataset": {"symbol": "AAPL", "closes": [10], "benchmark_dataset": {"status": "unavailable"}},
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
        {"timestamp": "2026-01-01", "session": "regular", "open": 10, "high": 12, "low": 9, "close": 11, "volume": 1000, "vwap": 10.5},
        {"timestamp": "2026-01-02", "session": "regular", "open": 11, "high": 13, "low": 10, "close": 12, "volume": 1200, "vwap": 11.5},
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
        {"source": "output.heatmap('matrix', [[1, 2], [3, 4]], ['A', 'B'], ['X', 'Y'])", "dataset": {}}
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["matrix"] == {
        "type": "heatmap",
        "value": {"rows": ["A", "B"], "columns": ["X", "Y"], "values": [[1.0, 2.0], [3.0, 4.0]]},
    }


def test_runner_emits_typed_dashboard_composed_from_named_artifacts():
    result = execute_job(
        {"source": "output.scalar('sample_size', 4)\noutput.series('trend', [1, 2])\noutput.dashboard('overview', [{'artifact': 'sample_size', 'title': 'Sample size', 'span': 4}, {'artifact': 'trend', 'title': 'Trend', 'span': 8}])", "dataset": {"timestamps": ["2026-01-01", "2026-01-02"]}}
    )
    assert result["status"] == "completed"
    assert result["artifacts"]["overview"] == {
        "type": "dashboard",
        "value": {"panels": [
            {"artifact": "sample_size", "title": "Sample size", "span": 4},
            {"artifact": "trend", "title": "Trend", "span": 8},
        ]},
    }


def test_runner_rejects_dashboard_references_to_missing_artifacts():
    result = execute_job(
        {"source": "output.dashboard('overview', [{'artifact': 'missing'}])", "dataset": {}}
    )

    assert result["status"] == "failed"
    assert result["diagnostics"] == [{
        "code": "dashboard_reference_error",
        "message": "dashboard 'overview' references unavailable artifact 'missing'",
    }]


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


def test_runner_does_not_expose_pandas_wrapper_internals():
    result = execute_job({
        "source": "series = pd.Series([1, 2])\noutput.table('raw', series._value)",
        "dataset": {},
    })
    assert result["status"] == "failed"
    assert result["diagnostics"][0]["code"] == "runtime_error"
    assert "private wrapper attributes" in result["diagnostics"][0]["message"]


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
    jobs.mkdir()
    monkeypatch.setattr(runner, "JOB_DIR", jobs)
    (jobs / "99.running").write_text('{"source":"output.scalar(\'ok\', 1)"}')

    recover_orphaned_jobs()

    assert (jobs / "99.json").exists()
    assert not (jobs / "99.running").exists()


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
