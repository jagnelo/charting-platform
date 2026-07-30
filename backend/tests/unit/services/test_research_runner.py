from research_runner.runner import execute_job


def test_runner_executes_only_validated_output_contract_in_its_own_process_module():
    result = execute_job({"source": "output.scalar('sample_size', 4)", "dataset": {}})
    assert result["status"] == "completed"
    assert result["artifacts"]["sample_size"] == {"type": "scalar", "value": 4}


def test_runner_emits_typed_boolean_artifacts():
    result = execute_job({"source": "output.boolean('qualifies', 2 > 1)", "dataset": {}})
    assert result["status"] == "completed"
    assert result["artifacts"]["qualifies"] == {"type": "boolean", "value": True}


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
