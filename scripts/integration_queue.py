#!/usr/bin/env python3
"""Human-readable inventory for the persistent staging integration queue."""

from __future__ import annotations

import argparse
import fcntl
import json
import re
import subprocess
from pathlib import Path


def git(*args: str, cwd: Path | None = None, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
    if check and result.returncode:
        raise SystemExit(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def root() -> Path:
    return Path(git("rev-parse", "--show-toplevel")).resolve()


def common_root() -> Path:
    value = Path(git("rev-parse", "--git-common-dir"))
    if not value.is_absolute():
        value = root() / value
    return value.resolve().parent


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()


def values(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text().splitlines():
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if match:
            result[match.group(1)] = match.group(2).strip().strip("'\"")
    return result


def records() -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in git("worktree", "list", "--porcelain").splitlines() + [""]:
        if not line:
            if current:
                result.append(current)
                current = {}
        elif line.startswith("worktree "):
            current["path"] = line.removeprefix("worktree ")
        elif line.startswith("branch "):
            current["branch"] = line.removeprefix("branch ").removeprefix("refs/heads/")
    return result


def queue() -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for record in records():
        branch = record.get("branch", "")
        if not branch.startswith(("feat/", "fix/", "chore/", "docs/", "test/")):
            continue
        path = Path(record["path"])
        plan_path = path / "ops" / "workstreams" / slug(branch) / "plan.yaml"
        plan = values(plan_path)
        head = git("rev-parse", "HEAD", cwd=path, check=False)
        remote = git("rev-parse", f"origin/{branch}", cwd=path, check=False)
        status = plan.get("status", "missing")
        tier = plan.get("validation_tier", "pending")
        if not plan:
            state = "missing-workstream"
            reason = "create a schema-2 branch-owned workstream"
        elif status == "ready_for_integration" and head and head == remote:
            state = "ready"
            reason = "closure authorization and synchronized source are present"
        elif status == "ready_for_human_review":
            state = "review-required"
            reason = "await explicit human closure after review"
        elif status in {"blocked", "superseded", "closed", "integrated"}:
            state = status
            reason = "workstream is not eligible for a new merge"
        else:
            state = "in-progress"
            reason = "implementation or validation remains open"
        output.append(
            {
                "branch": branch,
                "path": str(path),
                "head": head or None,
                "remote": remote or None,
                "synchronized": bool(head and head == remote),
                "status": status,
                "validation_tier": tier,
                "state": state,
                "reason": reason,
                "batch_policy": "focused_only_with_next_full_integration"
                if tier == "focused_only"
                else "individual_full_integration",
            }
        )
    return output


def integrate_ready() -> int:
    if git("branch", "--show-current") != "master" or git("status", "--porcelain"):
        raise SystemExit(
            "integrate-ready requires a clean root master coordinator checkout"
        )
    lock_path = common_root() / ".ai" / "locks" / "staging-integration.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        items = queue()
        full = sorted(
            (
                item
                for item in items
                if item["state"] == "ready"
                and item["validation_tier"] != "focused_only"
            ),
            key=lambda item: str(item["branch"]),
        )
        if not full:
            print(
                "no closure-ready full_integration branch is available; focused-only branches wait"
            )
            return 0
        selected = [full[0]] + [
            item
            for item in items
            if item["state"] == "ready" and item["validation_tier"] == "focused_only"
        ]
        print(
            json.dumps(
                {
                    "selected": [
                        {"branch": item["branch"], "sha": item["remote"]}
                        for item in selected
                    ]
                },
                indent=2,
            )
        )
        subprocess.run(
            [
                "uv",
                "run",
                "--project",
                "backend",
                "python",
                "scripts/staging.py",
                "integrate",
                *[str(item["branch"]) for item in selected],
            ],
            check=True,
        )
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--integrate-ready", action="store_true")
    args = parser.parse_args()
    if args.integrate_ready:
        return integrate_ready()
    data = queue()
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        if not data:
            print("integration queue is empty")
        for item in data:
            print(f"{item['state']:22} {item['branch']:42} {item['head'] or 'no HEAD'}")
            print(f"  {item['reason']} ({item['batch_policy']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
