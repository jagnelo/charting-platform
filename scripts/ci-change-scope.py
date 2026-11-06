#!/usr/bin/env python3
"""Fail-closed CI scope for exact changed paths between two Git commits."""

from __future__ import annotations

import argparse
import subprocess
import sys

METADATA_PREFIX = "ops/workstreams/"
METADATA_FILES = {
    "plan.yaml",
    "handoff.md",
    "validation.jsonl",
    "session.json",
}
WORKFLOW_FILES = {
    ".github/workflows/ci.yml",
    "docs/agent-orchestration.md",
    "docs/development.md",
    "docs/worktree-lifecycle.md",
    "scripts/staging.py",
    "scripts/agent-session.py",
    "scripts/worktree.py",
    "scripts/run-branch-tests.py",
    "scripts/ci-change-scope.py",
    "scripts/verify-master-promotion.py",
    "scripts/verify-prior-qualification.py",
    "scripts/validation_profile.py",
    "scripts/rpi.py",
}
WORKFLOW_TESTS = {
    "tests/workflow/test_staging_workflow.py",
    "tests/workflow/test_agent_session.py",
    "tests/workflow/test_ci_change_scope.py",
    "tests/workflow/test_master_promotion_evidence.py",
    "tests/workflow/test_prior_qualification.py",
    "tests/workflow/test_run_branch_tests.py",
}


def classify(paths: list[str]) -> str:
    if not paths:
        return "broad"

    def metadata(path: str) -> bool:
        return (
            path.startswith(METADATA_PREFIX) and path.split("/")[-1] in METADATA_FILES
        )

    if all(
        metadata(path) or path in WORKFLOW_FILES or path in WORKFLOW_TESTS
        for path in paths
    ):
        return "workflow" if any(not metadata(path) for path in paths) else "metadata"
    return "broad"


def qualified_scope(paths: list[str], prior_qualified: bool) -> str:
    scope = classify(paths)
    return scope if scope == "broad" or prior_qualified else "broad"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--github-output")
    parser.add_argument(
        "--candidate",
        action="store_true",
        help="classify paths without asserting that prior qualification exists",
    )
    parser.add_argument("--prior-qualified", action="store_true")
    args = parser.parse_args()
    if args.candidate and args.prior_qualified:
        parser.error("--candidate and --prior-qualified are mutually exclusive")
    result = subprocess.run(
        [
            "git",
            "diff",
            "--no-renames",
            "--name-only",
            "--diff-filter=ACDMRT",
            args.base,
            args.head,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        print(
            result.stderr.strip() or "cannot determine changed paths", file=sys.stderr
        )
        return 2
    paths = result.stdout.splitlines()
    scope = (
        classify(paths)
        if args.candidate
        else qualified_scope(paths, args.prior_qualified)
    )
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as output:
            output.write(f"scope={scope}\n")
            output.write(f"paths={'%0A'.join(paths)}\n")
    else:
        print(scope)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
