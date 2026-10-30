import importlib.util
import signal
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


def test_integration_batches_use_the_reviewed_bounded_size():
    assert RUNNER.DEFAULT_INTEGRATION_BATCH_SIZE == 25


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
            "app/strategy_lab_v2/tests/test_adapter.py::test_strategy_unit",
            "tests/integration/api/test_two.py::test_integration",
            "================ 3 tests collected ================",
        )
    )

    assert RUNNER.parse_collected_nodeids(output) == {
        "tests/unit": ["tests/unit/test_one.py::test_unit"],
        "app/strategy_lab_v2/tests": [
            "app/strategy_lab_v2/tests/test_adapter.py::test_strategy_unit"
        ],
        "tests/integration": ["tests/integration/api/test_two.py::test_integration"],
    }


def test_duplicate_collected_nodeids_are_rejected_before_coverage_or_tests(
    monkeypatch, capsys
):
    nodeid = "tests/integration/test_same.py::test_case"
    collected = [
        f"{root}/test_present.py::test_case"
        for root in RUNNER.TEST_ROOTS
        if root != "tests/integration"
    ]
    collected.extend((nodeid, nodeid))

    def fake_run(command, **_kwargs):
        if "--collect-only" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="\n".join(collected),
                stderr="",
            )
        raise AssertionError("coverage and test commands must not run")

    monkeypatch.setattr(RUNNER.subprocess, "run", fake_run)

    assert RUNNER.main([]) == 2
    assert "duplicate test IDs" in capsys.readouterr().err


def test_strategy_package_is_included_in_bounded_unit_shards():
    assert "app/strategy_lab_v2/tests" in RUNNER.UNIT_TEST_ROOTS
    suites = {
        "tests/unit": ["tests/unit/test_one.py::test_unit"],
        "app/strategy_lab_v2/tests": [
            "app/strategy_lab_v2/tests/test_adapter.py::test_strategy_unit"
        ],
        "tests/integration": ["tests/integration/test_db.py::test_integration"],
    }

    assert RUNNER.combined_unit_nodeids(suites) == [
        "tests/unit/test_one.py::test_unit",
        "app/strategy_lab_v2/tests/test_adapter.py::test_strategy_unit",
    ]


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
    unit = workflow.split("- name: Run unit tests", 1)[1].split(
        "- name: Run integration tests", 1
    )[0]
    integration = workflow.split(
        "- name: Run integration tests (with testcontainers)", 1
    )[1]
    integration = integration.split("- name: Enforce combined backend coverage", 1)[0]
    assert "app/strategy_lab_v2/tests" in unit
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


def _nodeids_from_pytest_command(command):
    assert command[1:3] == ["-m", "pytest"]
    return command[3 : command.index("--override-ini")]


def _is_pytest_execution(command):
    return command[1:3] == ["-m", "pytest"] and "--collect-only" not in command


def _strategy_nodeids():
    if "app/strategy_lab_v2/tests" in RUNNER.UNIT_TEST_ROOTS:
        return ["app/strategy_lab_v2/tests/test_adapter.py::test_strategy"]
    return []


def test_main_runs_every_integration_id_once_in_ordered_batches_and_appends_coverage(
    monkeypatch, capsys
):
    commands = []
    timeouts = []
    unit_ids = [
        *(f"tests/unit/test_{index}.py::test_case" for index in range(3)),
        *_strategy_nodeids(),
    ]
    integration_ids = [
        f"tests/integration/test_{index}.py::test_case" for index in range(52)
    ]

    def fake_run(command, **kwargs):
        commands.append(command)
        timeouts.append(kwargs.get("timeout"))
        if "--collect-only" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="\n".join([*unit_ids, *integration_ids]),
                stderr="",
            )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(RUNNER.subprocess, "run", fake_run)

    assert RUNNER.main(["--shard-size", "2"]) == 0

    erase = [c for c in commands if c[1:3] == ["-m", "coverage"] and c[3] == "erase"]
    pytest_commands = [c for c in commands if _is_pytest_execution(c)]
    coverage_reports = [
        c for c in commands if c[1:3] == ["-m", "coverage"] and c[3] != "erase"
    ]
    assert len(erase) == 1
    expected_unit_runs = len(RUNNER.partition(unit_ids, 2))
    assert len(pytest_commands) == expected_unit_runs + 3
    unit_runs = [
        _nodeids_from_pytest_command(c) for c in pytest_commands[:expected_unit_runs]
    ]
    integration_runs = [
        _nodeids_from_pytest_command(c) for c in pytest_commands[expected_unit_runs:]
    ]
    assert [len(batch) for batch in integration_runs] == [25, 25, 2]
    assert [nodeid for batch in unit_runs for nodeid in batch] == unit_ids
    assert [nodeid for batch in integration_runs for nodeid in batch] == integration_ids
    assert len(set(nodeid for batch in integration_runs for nodeid in batch)) == 52
    assert all("--cov-append" in c for c in pytest_commands)
    assert all("--cov-report=" in c for c in pytest_commands)
    assert [c[3:] for c in coverage_reports] == [
        ["report", "--fail-under=75"],
        ["xml", "-o", "coverage-combined.xml"],
    ]
    assert commands.index(erase[0]) < commands.index(pytest_commands[0])
    assert commands.index(coverage_reports[0]) > commands.index(pytest_commands[-1])
    assert timeouts[0] == RUNNER.COLLECTION_TIMEOUT_SECONDS
    pytest_timeouts = [
        timeout
        for command, timeout in zip(commands, timeouts, strict=True)
        if _is_pytest_execution(command)
    ]
    assert pytest_timeouts == [
        *([RUNNER.UNIT_SHARD_TIMEOUT_SECONDS] * expected_unit_runs),
        *([RUNNER.INTEGRATION_TIMEOUT_SECONDS] * 3),
    ]
    assert "Docker integration batch 3/3: 2 tests" in capsys.readouterr().out


def _run_main_with_integration_outcome(monkeypatch, outcome):
    commands = []
    integration_ids = [
        f"tests/integration/test_{index}.py::test_case" for index in range(51)
    ]
    integration_batch_number = 0

    def fake_run(command, **kwargs):
        nonlocal integration_batch_number
        commands.append(command)
        if "--collect-only" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="\n".join(
                    [
                        "tests/unit/test_one.py::test_unit",
                        *_strategy_nodeids(),
                        *integration_ids,
                    ]
                ),
                stderr="",
            )
        if command[1:3] == ["-m", "pytest"]:
            nodeids = _nodeids_from_pytest_command(command)
            if nodeids and nodeids[0].startswith("tests/integration/"):
                integration_batch_number += 1
                if outcome == "timeout" and integration_batch_number == 1:
                    raise subprocess.TimeoutExpired(command, kwargs["timeout"])
                if outcome == "nonzero" and integration_batch_number == 2:
                    return subprocess.CompletedProcess(command, 17)
                if outcome == "signal" and integration_batch_number == 2:
                    return subprocess.CompletedProcess(command, -signal.SIGTERM)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(RUNNER.subprocess, "run", fake_run)
    return RUNNER.main([]), commands


@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    [("nonzero", 17), ("timeout", 124), ("signal", 128 + signal.SIGTERM)],
)
def test_integration_failure_timeout_or_signal_aborts_later_batches_and_coverage_success(
    monkeypatch, outcome, expected_status
):
    status, commands = _run_main_with_integration_outcome(monkeypatch, outcome)

    integration_commands = [
        c
        for c in commands
        if _is_pytest_execution(c)
        and _nodeids_from_pytest_command(c)[0].startswith("tests/integration/")
    ]
    coverage_reports = [
        c
        for c in commands
        if c[1:3] == ["-m", "coverage"] and c[3] in {"report", "xml"}
    ]
    assert status == expected_status
    expected_batches = 1 if outcome == "timeout" else 2
    assert len(integration_commands) == expected_batches
    assert all(len(_nodeids_from_pytest_command(c)) == 25 for c in integration_commands)
    assert not coverage_reports
