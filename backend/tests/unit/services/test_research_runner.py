from research_runner.runner import execute_job


def test_runner_executes_only_validated_output_contract_in_its_own_process_module():
    result = execute_job({"source": "output.scalar('sample_size', 4)", "dataset": {}})
    assert result["status"] == "completed"
    assert result["artifacts"]["sample_size"] == {"type": "scalar", "value": 4}


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
