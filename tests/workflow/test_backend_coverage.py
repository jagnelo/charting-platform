import importlib.util
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "backend_coverage_under_test", ROOT / "scripts" / "backend_coverage.py"
)
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


def test_default_unit_shards_fit_the_test_process_memory_ceiling():
    assert RUNNER.DEFAULT_UNIT_SHARD_SIZE == 50


def test_partition_preserves_every_test_once_and_respects_boundaries():
    test_ids = [f"tests/unit/test_{index}.py::test_case" for index in range(7)]

    shards = RUNNER.partition(test_ids, 3)

    assert [len(shard) for shard in shards] == [3, 3, 1]
    assert [item for shard in shards for item in shard] == test_ids


@pytest.mark.parametrize("size", [0, -1])
def test_partition_rejects_nonpositive_size(size):
    with pytest.raises(ValueError, match="positive"):
        RUNNER.partition(["tests/unit/test_one.py::test_case"], size)


def test_parse_collected_nodeids_separates_the_complete_test_roots():
    output = "\n".join(
        (
            "tests/unit/test_one.py::test_unit",
            "tests/integration/api/test_two.py::test_integration",
            "================ 2 tests collected ================",
        )
    )

    assert RUNNER.parse_collected_nodeids(output) == {
        "tests/unit": ["tests/unit/test_one.py::test_unit"],
        "tests/integration": ["tests/integration/api/test_two.py::test_integration"],
    }


def test_pytest_args_keep_coverage_append_enabled_without_per_shard_reports():
    args = RUNNER.pytest_args(["tests/unit/test_one.py::test_unit"])

    assert "--cov=app" in args
    assert "--cov-append" in args
    assert "--cov-report=" in args

    assert "--cov-fail-under=0" not in args


def test_backend_pytest_defaults_do_not_enable_implicit_coverage_reports():
    config = (ROOT / "backend" / "pytest.ini").read_text()
    addopts = config.split("addopts =", 1)[1].split("markers =", 1)[0]
    assert "--cov" not in addopts


def test_ci_preserves_unit_coverage_and_enforces_combined_backend_threshold():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    integration = workflow.split(
        "- name: Run integration tests (with testcontainers)", 1
    )[1]
    integration = integration.split("- name: Enforce combined backend coverage", 1)[0]
    assert "--cov-append" in integration
    assert "uv run coverage report --fail-under=75" in workflow


def test_runner_streams_subprocess_output_instead_of_buffering(monkeypatch, tmp_path):
    observed = {}

    def fake_run(command, **kwargs):
        observed.update(kwargs)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(RUNNER.subprocess, "run", fake_run)

    assert RUNNER.run(["example"], cwd=tmp_path, env={}, timeout=3) == 0
    assert "capture_output" not in observed
    assert observed["timeout"] == 3


def test_collection_has_visible_progress_and_a_bounded_timeout(monkeypatch, capsys):
    observed = {}

    def timeout(command, **kwargs):
        observed.update(kwargs)
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], output="partial")

    monkeypatch.setattr(RUNNER.subprocess, "run", timeout)

    assert RUNNER.main(["--shard-size", "1"]) == 124
    assert observed["timeout"] == RUNNER.COLLECTION_TIMEOUT_SECONDS
    assert "Collecting backend test IDs" in capsys.readouterr().out
