#!/usr/bin/env python3
"""Safe local worktree interface used by the Makefile."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


PREFIXES = ("feat/", "fix/", "chore/", "docs/", "test/")


def git(*args: str, cwd: Path | None = None, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
    if check and result.returncode:
        raise SystemExit(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def git_succeeds(*args: str, cwd: Path | None = None) -> bool:
    """Return Git's exit status without confusing it with command output."""
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
    return result.returncode == 0


def repo_root() -> Path:
    return Path(git("rev-parse", "--show-toplevel")).resolve()


def branch_slug(branch: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", branch).strip("-").lower()
    return value or "detached-head"


def common_root() -> Path:
    common = Path(git("rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = repo_root() / common
    return common.resolve().parent


def ensure_master_ready() -> None:
    if git("branch", "--show-current") != "master":
        raise SystemExit(
            "worktree creation must run from the clean root master checkout"
        )
    if git("status", "--porcelain"):
        raise SystemExit(
            "master is dirty; commit or otherwise account for changes first"
        )
    if git("diff", "--check"):
        raise SystemExit("master has whitespace errors")
    remote = git("rev-parse", "--verify", "origin/master", check=False)
    if not remote:
        raise SystemExit(
            "origin/master is unavailable; fetch before creating a worktree"
        )
    if git("rev-parse", "HEAD") != remote:
        raise SystemExit("master is not synchronized with origin/master")


def worktree_records() -> list[dict[str, str]]:
    lines = git("worktree", "list", "--porcelain").splitlines()
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in lines + [""]:
        if not line:
            if current:
                records.append(current)
                current = {}
        elif line.startswith("worktree "):
            current["path"] = line.removeprefix("worktree ")
        elif line.startswith("branch "):
            current["branch"] = line.removeprefix("branch ").removeprefix("refs/heads/")
        elif line == "detached":
            current["branch"] = "(detached)"
    return records


def branch_path(branch: str) -> Path:
    for record in worktree_records():
        if record.get("branch") == branch:
            return Path(record["path"]).resolve()
    raise SystemExit(f"branch is not checked out in a worktree: {branch}")


def initialise_docs(path: Path, branch: str) -> None:
    directory = path / "ops" / "workstreams" / branch_slug(branch)
    directory.mkdir(parents=True, exist_ok=False)
    base_sha = git("rev-parse", "master", cwd=path)
    (directory / "plan.yaml").write_text(
        "schema: 1\n"
        f"branch: {branch}\n"
        f"base_sha: {base_sha}\n"
        'goal: "replace me"\n'
        "scope: []\n"
        "owned_paths: []\n"
        "dependencies: []\n"
        "acceptance_criteria: []\n"
        "branch_tests: []\n"
        "live_test_impact: none\n"
        "migration_impact: none\n"
        "deployment_impact: none\n"
        "status: planned\n"
        "remaining_gaps: []\n"
    )
    (directory / "handoff.md").write_text(
        f"# {branch}\n\nCreated from `master` at `{base_sha}`. Update this handoff at each coherent boundary.\n"
    )
    (directory / "validation.jsonl").write_text("")


def create(branch: str) -> None:
    if not branch.startswith(PREFIXES) or branch.endswith("/"):
        raise SystemExit(
            "branch must use feat/, fix/, chore/, docs/, or test/ and include a name"
        )
    if ":" in branch or ".." in branch:
        raise SystemExit("branch name contains an unsafe path component")
    ensure_master_ready()
    if git("show-ref", "--verify", f"refs/heads/{branch}", check=False):
        raise SystemExit(f"local branch already exists: {branch}")
    if git("ls-remote", "--exit-code", "--heads", "origin", branch, check=False):
        raise SystemExit(f"remote branch already exists: {branch}")
    target = common_root() / ".ai" / "worktrees" / branch_slug(branch)
    if target.exists():
        raise SystemExit(f"worktree path already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    git("worktree", "add", "-b", branch, str(target), "master")
    initialise_docs(target, branch)
    print(target)


def status(branch: str) -> None:
    path = branch_path(branch)
    print(
        json.dumps(
            {
                "branch": branch,
                "path": str(path),
                "status": git("status", "--short", "--branch", cwd=path),
                "head": git("rev-parse", "HEAD", cwd=path),
                "master": git("rev-parse", "master", cwd=path),
            },
            indent=2,
        )
    )


def running_projects(prefix: str) -> list[str]:
    if not shutil.which("docker"):
        raise SystemExit("docker is required to prove that the worktree is not running")
    result = subprocess.run(
        ["docker", "ps", "--format", '{{{{.Label "com.docker.compose.project"}}}}'],
        text=True,
        capture_output=True,
    )
    if result.returncode:
        raise SystemExit("could not inspect Docker; refusing to close the worktree")
    return sorted(
        set(
            line for line in result.stdout.splitlines() if line.startswith(prefix + "-")
        )
    )


def close(branch: str) -> None:
    path = branch_path(branch)
    if path == repo_root():
        raise SystemExit("refusing to close the root integration checkout")
    if git("status", "--porcelain", cwd=path):
        raise SystemExit(
            "worktree is dirty; commit or account for changes before closing"
        )
    if not git_succeeds("merge-base", "--is-ancestor", branch, "master", cwd=path):
        raise SystemExit("worktree is not merged into master")
    slug = branch_slug(branch)
    projects = running_projects(f"charting-dev-{slug}") + running_projects(
        f"charting-stack-{slug}"
    )
    if projects:
        raise SystemExit(
            f"worktree has running managed Compose projects: {', '.join(projects)}"
        )
    git("worktree", "remove", str(path))
    git("branch", "-d", branch)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create")
    p.add_argument("branch")
    p = sub.add_parser("status")
    p.add_argument("branch")
    p = sub.add_parser("close")
    p.add_argument("branch")
    sub.add_parser("list")
    args = parser.parse_args()
    if args.command == "create":
        create(args.branch)
    elif args.command == "status":
        status(args.branch)
    elif args.command == "close":
        close(args.branch)
    else:
        print(json.dumps(worktree_records(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
