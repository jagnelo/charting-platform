#!/usr/bin/env python3
"""Describe the repository role an automatically-discovered agent may assume."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


PREFIXES = ("feat/", "fix/", "chore/", "docs/", "test/")


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], text=True, capture_output=True)
    if result.returncode:
        raise SystemExit(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower() or "detached-head"


def main() -> int:
    root = Path(git("rev-parse", "--show-toplevel")).resolve()
    branch = git("branch", "--show-current")
    common = Path(git("rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = root / common
    common_root = common.resolve().parent
    expected = (common_root / ".ai" / "worktrees" / slug(branch)).resolve()
    if not branch:
        role = "invalid"
        next_action = "stop: detached HEAD is not an implementation role"
    elif branch == "master" and root == common_root:
        role = "control"
        next_action = "inspect or create an authorized staging-based worktree; do not implement product code here"
    elif branch == "staging":
        role = "staging_coordinator"
        next_action = "process the integration queue or use the explicitly authorized workflow-maintenance exception"
    elif branch.startswith(PREFIXES) and root == expected:
        role = "implementation"
        next_action = f"run make agent-session-start BRANCH={branch} and resume the branch-owned workstream"
    else:
        role = "invalid"
        next_action = "stop: checkout path and branch do not match a supported role"
    print(
        json.dumps(
            {
                "role": role,
                "branch": branch or None,
                "worktree": str(root),
                "expected_worktree": str(expected),
                "protected": branch in {"master", "staging"},
                "next_action": next_action,
                "automatic_entry": "AGENTS.md",
                "canonical_policy": "docs/agent-orchestration.md",
            },
            indent=2,
        )
    )
    return 0 if role != "invalid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
