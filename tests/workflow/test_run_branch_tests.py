"""Tests for explicit workstream-plan to branch-CI command mappings."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "run_branch_tests_under_test", ROOT / "scripts" / "run-branch-tests.py"
)
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)

BRANCH = "feat/example"
DESCRIPTIONS = ["unit suites", "integration and live acceptance"]


def make_plan(directory: Path, descriptions: list[str] = DESCRIPTIONS) -> Path:
    workstream = directory / "ops" / "workstreams" / "feat-example"
    workstream.mkdir(parents=True)
    rows = ["branch_tests:"]
    rows.extend(f"  - {description}" for description in descriptions)
    plan = workstream / "plan.yaml"
    plan.write_text("\n".join(rows) + "\n")
    return plan


def make_manifest(
    plan: Path,
    *,
    branch: str = BRANCH,
    plan_tests: list[str] | None = None,
    commands: list[dict] | None = None,
    external_gates: list[dict] | None = None,
) -> Path:
    manifest = {
        "schema": 1,
        "branch": branch,
        "plan_tests": plan_tests if plan_tests is not None else DESCRIPTIONS,
        "commands": commands
        if commands is not None
        else [{"id": "unit", "command": "make test-unit", "covers": [1]}],
        "external_gates": external_gates
        if external_gates is not None
        else [
            {
                "id": "live",
                "covers": [2],
                "reason": "requires explicitly admitted provider credentials",
            }
        ],
        "ci_covered_commands": {"unit": "Backend Tests"},
    }
    target = plan.with_name("branch-tests.json")
    target.write_text(json.dumps(manifest))
    return target


def test_manifest_maps_plan_descriptions_to_commands_and_external_gates(tmp_path):
    plan = make_plan(tmp_path)
    make_manifest(plan)

    result = RUNNER.execution_manifest(plan, BRANCH)

    assert result["commands"][0]["command"] == "make test-unit"
    assert result["external_gates"][0]["id"] == "live"
    assert result["ci_covered_commands"] == {"unit": "Backend Tests"}


def test_github_ci_only_reuses_the_backend_job_after_declaring_dependency():
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    branch_job = workflow["jobs"]["branch-declared"]
    assert branch_job["needs"] == ["backend"]
    backend_job_name = workflow["jobs"]["backend"]["name"]
    assert backend_job_name == "Backend Tests"
    run_step = next(
        step
        for step in branch_job["steps"]
        if step.get("name") == "Run tests declared by this branch"
    )
    manifest = json.loads(
        (
            ROOT
            / "ops"
            / "workstreams"
            / "feat-market-data-provider-platform"
            / "branch-tests.json"
        ).read_text()
    )
    assert manifest["ci_covered_commands"]["full-backend-suite"] == backend_job_name
    assert run_step["env"]["BRANCH_TESTS_CI_COVERED_COMMANDS"] == "full-backend-suite"
    assert run_step["env"]["INTEGRATION_BASE_SHA"] == "origin/master"


def test_actual_workstream_ci_mapping_runs_migrations_and_leaves_live_gate_open(
    monkeypatch, capsys
):
    calls: list[list[str]] = []
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(
        sys,
        "argv",
        ["run-branch-tests.py", "feat/market-data-provider-platform"],
    )
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("BRANCH_TESTS_CI_COVERED_COMMANDS", "full-backend-suite")

    class Result:
        returncode = 0

    monkeypatch.setattr(
        RUNNER.subprocess,
        "run",
        lambda command, **_kwargs: calls.append(command) or Result(),
    )

    assert RUNNER.main() == 0
    output = capsys.readouterr().out
    assert calls == [
        [
            "/bin/sh",
            "-lc",
            "INTEGRATION_BASE_SHA=origin/master make test-migration-compatibility",
        ]
    ]
    assert "successful upstream GitHub CI job: Backend Tests" in output
    assert (
        "External acceptance gate NOT RUN: current-source-provider-live-matrix"
        in output
    )
    assert "not full workstream acceptance" in output


@pytest.mark.parametrize(
    ("manifest_values", "error"),
    [
        ({"plan_tests": ["stale", DESCRIPTIONS[1]]}, "do not exactly match"),
        ({"branch": "feat/other"}, "not 'feat/example'"),
        (
            {
                "commands": [
                    {"id": "unit", "command": "make test-unit", "covers": [1]}
                ],
                "external_gates": [],
            },
            "unmapped: 2",
        ),
        (
            {"commands": [{"id": "unit", "command": "make test-unit", "covers": [0]}]},
            "1-based",
        ),
    ],
)
def test_invalid_manifest_is_rejected(tmp_path, manifest_values, error):
    plan = make_plan(tmp_path)
    values = {
        "plan_tests": DESCRIPTIONS,
        "commands": [{"id": "unit", "command": "make test-unit", "covers": [1]}],
        "external_gates": [
            {"id": "live", "covers": [2], "reason": "not run in ordinary CI"}
        ],
    }
    values.update(manifest_values)
    make_manifest(
        plan,
        branch=values.get("branch", BRANCH),
        plan_tests=values["plan_tests"],
        commands=values["commands"],
        external_gates=values["external_gates"],
    )

    with pytest.raises(ValueError, match=error):
        RUNNER.execution_manifest(plan, BRANCH)


def test_runner_executes_local_commands_but_never_claims_external_gate_passed(
    tmp_path, monkeypatch, capsys
):
    plan = make_plan(tmp_path)
    make_manifest(plan)
    calls: list[list[str]] = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["run-branch-tests.py", BRANCH])

    class Result:
        returncode = 0

    def fake_run(command, **_kwargs):
        calls.append(command)
        return Result()

    monkeypatch.setattr(RUNNER.subprocess, "run", fake_run)

    assert RUNNER.main() == 0
    output = capsys.readouterr().out
    assert calls == [["/bin/sh", "-lc", "make test-unit"]]
    assert "External acceptance gate NOT RUN: live" in output
    assert "not full workstream acceptance" in output


def test_runner_uses_only_declared_successful_github_job_coverage(
    tmp_path, monkeypatch, capsys
):
    plan = make_plan(tmp_path)
    make_manifest(plan)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["run-branch-tests.py", BRANCH])
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("BRANCH_TESTS_CI_COVERED_COMMANDS", "unit")

    def unexpected_run(*_args, **_kwargs):
        raise AssertionError("upstream-covered backend suite must not run twice")

    monkeypatch.setattr(RUNNER.subprocess, "run", unexpected_run)

    assert RUNNER.main() == 0
    output = capsys.readouterr().out
    assert "successful upstream GitHub CI job: Backend Tests" in output
    assert "External acceptance gate NOT RUN: live" in output
    assert "not full workstream acceptance" in output


def test_runner_rejects_ci_coverage_bypass_outside_github_actions(
    tmp_path, monkeypatch, capsys
):
    plan = make_plan(tmp_path)
    make_manifest(plan)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["run-branch-tests.py", BRANCH])
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("BRANCH_TESTS_CI_COVERED_COMMANDS", "unit")

    assert RUNNER.main() == 2
    assert "only accepted in GitHub Actions" in capsys.readouterr().err
