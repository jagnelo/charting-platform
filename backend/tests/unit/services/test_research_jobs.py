import json
import stat
from pathlib import Path
from types import SimpleNamespace

from app.services import research_jobs


def test_prepare_shared_directory_is_writable_for_the_isolated_runner(tmp_path: Path):
    directory = tmp_path / "jobs"

    research_jobs._prepare_shared_directory(directory)

    assert stat.S_IMODE(directory.stat().st_mode) == 0o777


def test_enqueue_prepares_both_shared_volumes_and_job_file(tmp_path, monkeypatch):
    job_directory = tmp_path / "jobs"
    result_directory = tmp_path / "results"
    result_directory.mkdir()
    monkeypatch.setattr(research_jobs.settings, "RESEARCH_JOB_DIR", str(job_directory))
    monkeypatch.setattr(research_jobs.settings, "RESEARCH_RESULT_DIR", str(result_directory))
    run = SimpleNamespace(
        id=7,
        dataset_manifest={"symbol": "SPY"},
        run_config={"parameters": {"lookback": 20}},
        code_version=SimpleNamespace(
            source="output.scalar('value', 1)", output_contract="scalar", output_name=None
        ),
    )

    research_jobs.enqueue_research_run(run)

    assert stat.S_IMODE(job_directory.stat().st_mode) == 0o777
    assert stat.S_IMODE(result_directory.stat().st_mode) == 0o777
    job = job_directory / "7.json"
    assert stat.S_IMODE(job.stat().st_mode) == 0o666


def test_collect_projects_breadth_history_occurrences_into_persisted_artifact(
    tmp_path, monkeypatch
):
    result_directory = tmp_path / "results"
    result_directory.mkdir()
    monkeypatch.setattr(research_jobs.settings, "RESEARCH_RESULT_DIR", str(result_directory))
    points = [
        {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "percentage": 0.0,
            "pass_count": 0,
            "eligible_count": 1,
            "cells": [
                {"instrument_id": 7, "symbol": "SPY", "name": "SPY", "value": False, "metric": 0.0}
            ],
        },
        {
            "timestamp": "2026-01-02T00:00:00+00:00",
            "percentage": 1.0,
            "pass_count": 1,
            "eligible_count": 1,
            "cells": [
                {"instrument_id": 7, "symbol": "SPY", "name": "SPY", "value": True, "metric": 0.04}
            ],
        },
    ]
    (result_directory / "12.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "artifacts": {
                    "breadth_history": {
                        "type": "breadth_history",
                        "value": {"points": points},
                    }
                },
            }
        )
    )
    run = SimpleNamespace(id=12, artifacts=[])

    assert research_jobs.collect_research_result(run) is True
    artifact = run.artifacts[0]
    occurrences = artifact.payload["value"]["occurrences"]
    assert len(occurrences) == 1
    assert occurrences[0]["kind"] == "member_entered"
    assert occurrences[0]["instrument_id"] == 7
    assert occurrences[0]["metric"] == 0.04
