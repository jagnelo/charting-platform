#!/usr/bin/env python3
"""Safe local worktree interface used by the Makefile."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
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


def initialise_docs(path: Path, branch: str, request: str, base: str, dependency_authorization: str) -> None:
    directory = path / "ops" / "workstreams" / branch_slug(branch)
    directory.mkdir(parents=True, exist_ok=False)
    base_sha = git("rev-parse", base, cwd=path)
    (directory / "plan.yaml").write_text(
        "schema: 2\n"
        f"branch: {branch}\n"
        f"base_sha: {base_sha}\n"
        f"parent_branch: {base}\n"
        f"parent_sha: {base_sha}\n"
        f"dependency_authorization: {json.dumps(dependency_authorization or 'not applicable: independent master-based topic')}\n"
        f"human_intent_authorization: {json.dumps(request)}\n"
        "human_closure_authorization: pending\n"
        "closure_summary: pending\n"
        "validation_tier: pending_human_decision\n"
        "human_validation_authorization: pending\n"
        'goal: "replace me with the human-requested outcome"\n'
        "scope: []\n"
        "owned_paths: []\n"
        "dependencies: []\n"
        "acceptance_criteria: []\n"
        "branch_tests: []\n"
        "live_test_impact: none\n"
        "migration_impact: none\n"
        "deployment_impact: none\n"
        "status: authorized\n"
        "remaining_gaps: []\n"
    )
    (directory / "handoff.md").write_text(
        f"# {branch}\n\nCreated from `master` at `{base_sha}`.\n\n"
        "## Human authorization\n\n"
        f"- Recorded at: {datetime.now(UTC).isoformat()}\n"
        f"- Request: {request}\n"
        "- Closure authorization: pending; do not integrate or deploy until the human explicitly authorizes closure.\n\n"
        "Update this handoff at each coherent boundary.\n"
    )
    (directory / "validation.jsonl").write_text("")


def create(branch: str, request: str, base: str, dependency_authorization: str) -> None:
    if not branch.startswith(PREFIXES) or branch.endswith("/"):
        raise SystemExit(
            "branch must use feat/, fix/, chore/, docs/, or test/ and include a name"
        )
    if ":" in branch or ".." in branch:
        raise SystemExit("branch name contains an unsafe path component")
    if not request.strip():
        raise SystemExit(
            "a recorded human request is required; pass --request with the approved intent"
        )
    ensure_master_ready()
    if base != "master":
        if not dependency_authorization.strip():
            raise SystemExit("dependent branch creation requires explicit human dependency authorization")
        parent = branch_path(base)
        if git("status", "--porcelain", cwd=parent):
            raise SystemExit(f"parent branch worktree is dirty: {parent}")
    elif dependency_authorization.strip():
        raise SystemExit("dependency authorization is valid only with a non-master base")
    if git("show-ref", "--verify", f"refs/heads/{branch}", check=False):
        raise SystemExit(f"local branch already exists: {branch}")
    if git("ls-remote", "--exit-code", "--heads", "origin", branch, check=False):
        raise SystemExit(f"remote branch already exists: {branch}")
    target = common_root() / ".ai" / "worktrees" / branch_slug(branch)
    if target.exists():
        raise SystemExit(f"worktree path already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    git("worktree", "add", "-b", branch, str(target), base)
    initialise_docs(target, branch, request.strip(), base, dependency_authorization.strip())
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


def size_bytes(path: Path) -> int:
    result = subprocess.run(["du", "-sk", str(path)], text=True, capture_output=True)
    return int(result.stdout.split()[0]) * 1024 if result.returncode == 0 and result.stdout else 0


def plan_values(path: Path, branch: str) -> dict[str, str]:
    plan = path / "ops" / "workstreams" / branch_slug(branch) / "plan.yaml"
    values: dict[str, str] = {}
    if plan.exists():
        for line in plan.read_text().splitlines():
            match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
            if match:
                values[match.group(1)] = match.group(2).strip().strip("'\"")
    return values


def closure_reasons(branch: str, path: Path) -> list[str]:
    reasons: list[str] = []
    if git("status", "--porcelain", cwd=path):
        reasons.append("dirty")
    if not git_succeeds("merge-base", "--is-ancestor", branch, "master", cwd=path):
        reasons.append("unmerged")
    try:
        slug = branch_slug(branch)
        projects = running_projects(f"charting-dev-{slug}") + running_projects(f"charting-stack-{slug}")
        if projects:
            reasons.append("running:" + ",".join(projects))
    except SystemExit:
        reasons.append("Docker status unavailable")
    return reasons


def overview() -> None:
    rows: list[dict[str, object]] = []
    for record in worktree_records():
        branch = record.get("branch", "(unknown)")
        path = Path(record["path"])
        if not path.exists() or not (path / ".git").exists():
            rows.append({"branch": branch, "path": str(path), "kind": "stale-git-worktree-record", "close": "remove with git worktree prune after inspection", "size_bytes": 0})
            continue
        if branch in {"master", "(detached)"}:
            rows.append({"branch": branch, "path": str(path), "kind": "integration-artifact" if branch == "(detached)" else "master", "size_bytes": size_bytes(path)})
            continue
        behind, ahead = git("rev-list", "--left-right", "--count", f"master...{branch}", cwd=path).split()
        plan = plan_values(path, branch)
        reasons = closure_reasons(branch, path)
        rows.append({"branch": branch, "path": str(path), "goal": plan.get("goal", "unrecorded"), "workstream_status": plan.get("status", "missing"), "ahead": int(ahead), "behind": int(behind), "dirty": bool(git("status", "--porcelain", cwd=path)), "size_bytes": size_bytes(path), "close": "safe" if not reasons else "blocked: " + "; ".join(reasons)})
    print(json.dumps(rows, indent=2))


def archive(branch: str, confirm: str) -> None:
    if confirm != branch:
        raise SystemExit("archive confirmation must exactly match BRANCH")
    path = branch_path(branch)
    if path == repo_root():
        raise SystemExit("refusing to archive the root integration checkout")
    reasons = closure_reasons(branch, path)
    if reasons:
        raise SystemExit("refusing to archive: " + "; ".join(reasons))
    values = plan_values(path, branch)
    if values.get("status") not in {"blocked", "closed"}:
        raise SystemExit("archive requires workstream status blocked or closed with its reason recorded")
    git("worktree", "remove", str(path))
    git("branch", "-D", branch)
    print(f"archived local worktree and branch {branch}; remote audit branch was retained")


def running_projects(prefix: str) -> list[str]:
    if not shutil.which("docker"):
        raise SystemExit("docker is required to prove that the worktree is not running")
    result = subprocess.run(
        ["docker", "ps", "--format", '{{.Label "com.docker.compose.project"}}'],
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
    p.add_argument("--request", required=True)
    p.add_argument("--base", default="master")
    p.add_argument("--dependency-authorization", default="")
    p = sub.add_parser("status")
    p.add_argument("branch")
    p = sub.add_parser("close")
    p.add_argument("branch")
    p = sub.add_parser("archive")
    p.add_argument("branch")
    p.add_argument("--confirm", required=True)
    sub.add_parser("list")
    sub.add_parser("overview")
    args = parser.parse_args()
    if args.command == "create":
        create(args.branch, args.request, args.base, args.dependency_authorization)
    elif args.command == "status":
        status(args.branch)
    elif args.command == "close":
        close(args.branch)
    elif args.command == "archive":
        archive(args.branch, args.confirm)
    elif args.command == "overview":
        overview()
    else:
        print(json.dumps(worktree_records(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
