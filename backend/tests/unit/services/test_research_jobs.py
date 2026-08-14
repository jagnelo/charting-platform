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
