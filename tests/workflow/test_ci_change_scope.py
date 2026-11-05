from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "ci_change_scope", ROOT / "scripts" / "ci-change-scope.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_workstream_record_changes_use_metadata_lane() -> None:
    assert (
        MODULE.classify(
            [
                "ops/workstreams/feat-example/plan.yaml",
                "ops/workstreams/feat-example/handoff.md",
            ]
        )
        == "metadata"
    )


def test_workflow_policy_and_workstream_records_use_affected_guards():
    assert (
        MODULE.classify(
            [
                ".github/workflows/ci.yml",
                "docs/agent-orchestration.md",
                "ops/workstreams/feat-example/plan.yaml",
            ]
        )
        == "workflow"
    )


def test_runtime_narrative_and_product_inputs_force_broad_lane() -> None:
    assert MODULE.classify(["backend/tests/unit/test_runtime.py"]) == "broad"
    assert MODULE.classify(["backend/app/main.py"]) == "broad"
    assert MODULE.classify(["backend/uv.lock"]) == "broad"
    assert (
        MODULE.classify(["ops/workstreams/feat-example/branch-tests.json"]) == "broad"
    )


def test_metadata_cannot_launder_an_unqualified_parent():
    paths = ["ops/workstreams/feat-example/plan.yaml"]
    assert MODULE.qualified_scope(paths, prior_qualified=True) == "metadata"
    assert MODULE.qualified_scope(paths, prior_qualified=False) == "broad"


def test_workflow_only_changes_require_workflow_regressions() -> None:
    assert MODULE.classify([".github/workflows/ci.yml"]) == "workflow"
    assert (
        MODULE.classify(
            ["scripts/staging.py", "tests/workflow/test_staging_workflow.py"]
        )
        == "workflow"
    )


def test_unknown_mixed_changes_fail_closed() -> None:
    assert (
        MODULE.classify(["docs/guide.md", "ops/workstreams/feat-example/plan.yaml"])
        == "broad"
    )
    assert (
        MODULE.classify(
            ["backend/app/main.py", "ops/workstreams/feat-example/plan.yaml"]
        )
        == "broad"
    )


def test_git_diff_disables_rename_detection_and_uses_both_paths(monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(sys, "argv", ["ci-change-scope.py", "--base", "a" * 40])
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        lambda command, **_kwargs: seen.append(command)
        or SimpleNamespace(
            returncode=0,
            stderr="",
            stdout="backend/app/x.py\nops/workstreams/feat-x/plan.yaml\n",
        ),
    )
    assert MODULE.main() == 0
    assert "--no-renames" in seen[0]
    assert seen[0][-2:] == ["a" * 40, "HEAD"]
    assert capsys.readouterr().out.strip() == "broad"


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def test_actual_ci_scope_sequence_uses_qualified_merge_base_and_direct_tree_diff():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    run_script = workflow["jobs"]["changed-scope"]["steps"][1]["run"]
    with tempfile.TemporaryDirectory() as temporary:
        repo = Path(temporary)
        (repo / "scripts").mkdir()
        shutil.copy(ROOT / "scripts" / "ci-change-scope.py", repo / "scripts")
        (repo / "scripts" / "verify-prior-qualification.py").write_text(
            "import os, sys\n"
            "open(os.environ['VERIFY_LOG'], 'w').write(sys.argv[2])\n"
            "raise SystemExit(int(os.environ.get('VERIFY_RESULT', '0')))\n"
        )
        git(repo, "init", "-b", "fix/example")
        git(repo, "config", "user.email", "ci@example.invalid")
        git(repo, "config", "user.name", "CI test")
        (repo / "backend").mkdir()
        (repo / "backend" / "app.py").write_text("qualified runtime\n")
        (repo / "ops/workstreams/example").mkdir(parents=True)
        plan = repo / "ops/workstreams/example/plan.yaml"
        plan.write_text("state: qualified-base\n")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "qualified ancestor")
        qualified_base = git(repo, "rev-parse", "HEAD")

        git(repo, "branch", "staging")
        git(repo, "checkout", "staging")
        (repo / "backend" / "app.py").write_text("new staging product code\n")
        git(repo, "add", "backend/app.py")
        git(repo, "commit", "-m", "independent staging product repair")
        staging_head = git(repo, "rev-parse", "HEAD")
        git(repo, "update-ref", "refs/remotes/origin/staging", staging_head)

        git(repo, "checkout", "fix/example")
        plan.write_text("state: metadata-only child\n")
        git(repo, "add", str(plan.relative_to(repo)))
        git(repo, "commit", "-m", "metadata-only feature child")
        feature_head = git(repo, "rev-parse", "HEAD")
        assert git(repo, "merge-base", "HEAD", "origin/staging") == qualified_base

        scope_script = str(repo / "scripts" / "ci-change-scope.py")
        verify_script = str(repo / "scripts" / "verify-prior-qualification.py")
        assert scope_script.endswith("ci-change-scope.py")
        assert verify_script.endswith("verify-prior-qualification.py")
        for verify_result, expected_scope in (("0", "metadata"), ("1", "broad")):
            output = repo / f"output-{verify_result}"
            verify_log = repo / f"verify-{verify_result}"
            environment = os.environ.copy()
            environment.update(
                {
                    "BEFORE": "0" * 40,
                    "PR_BASE": "",
                    "GITHUB_SHA": feature_head,
                    "GITHUB_OUTPUT": str(output),
                    "GITHUB_REPOSITORY": "example/repo",
                    "GH_TOKEN": "test-token",
                    "VERIFY_LOG": str(verify_log),
                    "VERIFY_RESULT": verify_result,
                }
            )
            result = subprocess.run(
                ["bash", "-e", "-c", run_script],
                cwd=repo,
                env=environment,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stderr
            values = dict(
                line.split("=", 1) for line in output.read_text().splitlines()
            )
            assert values["scope"] == expected_scope
            assert verify_log.read_text() == qualified_base

        # Diffing directly against newer staging sees its product change.
        # A three-dot merge-base diff would hide it and incorrectly say metadata.
        candidate = subprocess.run(
            [
                sys.executable,
                str(repo / "scripts" / "ci-change-scope.py"),
                "--base",
                staging_head,
                "--candidate",
            ],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert candidate.stdout.strip() == "broad"
