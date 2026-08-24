#!/usr/bin/env python3
"""Report, then safely remove only proven-published integration candidates."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)


def root() -> Path:
    result = git("rev-parse", "--show-toplevel", cwd=Path.cwd())
    if result.returncode:
        raise SystemExit(result.stderr)
    return Path(result.stdout.strip()).resolve()


def common(repo: Path) -> Path:
    result = git("rev-parse", "--git-common-dir", cwd=repo)
    value = Path(result.stdout.strip())
    return (value if value.is_absolute() else repo / value).resolve().parent


def size_bytes(path: Path) -> int:
    result = subprocess.run(["du", "-sk", str(path)], text=True, capture_output=True)
    return int(result.stdout.split()[0]) * 1024 if result.returncode == 0 and result.stdout else 0


def registered(repo: Path) -> set[Path]:
    result = git("worktree", "list", "--porcelain", cwd=repo)
    return {Path(line[9:]).resolve() for line in result.stdout.splitlines() if line.startswith("worktree ")}


def candidate(repo: Path, path: Path, known: set[Path]) -> dict[str, object]:
    row: dict[str, object] = {"path": str(path), "action": "retain"}
    if path.resolve() not in known or not (path / ".git").exists():
        row["reason"] = "not a registered usable Git worktree"
        return row
    head = git("rev-parse", "HEAD", cwd=path)
    dirty = git("status", "--porcelain", cwd=path)
    merge = git("rev-parse", "--verify", "MERGE_HEAD", cwd=path)
    if head.returncode or dirty.returncode:
        row["reason"] = "Git state cannot be proven"
        return row
    sha = head.stdout.strip()
    row["head"] = sha
    if dirty.stdout.strip() or merge.returncode == 0:
        row["reason"] = "dirty or merge in progress"
        return row
    reachable = git("merge-base", "--is-ancestor", sha, "master", cwd=repo)
    if reachable.returncode:
        row["reason"] = "candidate HEAD is not published on master"
        return row
    row["action"] = "eligible_remove"
    row["reason"] = "clean detached candidate already reachable from master"
    return row


def report(repo: Path) -> dict[str, object]:
    integration = common(repo) / ".ai" / "integration"
    known = registered(repo)
    candidates = [candidate(repo, path, known) for path in sorted(integration.iterdir()) if path.is_dir()] if integration.exists() else []
    eligible = [item for item in candidates if item["action"] == "eligible_remove"]
    return {"integration_root": str(integration), "candidates": candidates, "eligible_count": len(eligible)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("report", "cleanup"))
    parser.add_argument("--confirm")
    args = parser.parse_args()
    repo = root()
    data = report(repo)
    if args.command == "report":
        print(json.dumps(data, indent=2))
        return 0
    if args.confirm != "published-integration-candidates":
        raise SystemExit("cleanup requires --confirm published-integration-candidates")
    for item in data["candidates"]:
        if item["action"] == "eligible_remove":
            result = git("worktree", "remove", item["path"], cwd=repo)
            if result.returncode:
                raise SystemExit(result.stderr)
    print(json.dumps(report(repo), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
