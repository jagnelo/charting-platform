#!/usr/bin/env python3
"""Human-readable inventory for the persistent staging integration queue."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import yaml


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


def values(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        result = yaml.safe_load(path.read_text())
    except yaml.YAMLError:
        return {}
    return result if isinstance(result, dict) else {}


def exact_ci(branch: str, sha: str) -> tuple[str, str]:
    """Return exact push CI state without treating an API error as green."""
    gh_error = ""
    runs: list[dict[str, object]] = []
    gh_lookup_succeeded = False
    if shutil.which("gh"):
        result = subprocess.run(
            [
                "gh",
                "run",
                "list",
                "--workflow",
                "ci.yml",
                "--branch",
                branch,
                "--commit",
                sha,
                "--event",
                "push",
                "--limit",
                "10",
                "--json",
                "headSha,headBranch,status,conclusion,runAttempt",
            ],
            text=True,
            capture_output=True,
        )
        if result.returncode == 0:
            try:
                payload = json.loads(result.stdout or "[]")
                runs = payload if isinstance(payload, list) else []
                gh_lookup_succeeded = isinstance(payload, list)
            except json.JSONDecodeError:
                gh_error = "GitHub CLI returned invalid JSON"
        else:
            gh_error = result.stderr.strip() or "GitHub CLI lookup failed"
    else:
        gh_error = "GitHub CLI unavailable"
    if not runs and not gh_lookup_succeeded:
        remote = git("remote", "get-url", "origin", check=False)
        match = re.search(
            r"(?:github\.com|github-[^/:]+)[:/]([^/]+)/([^/]+?)(?:\.git)?$", remote
        )
        if not match:
            return "unknown", gh_error or "origin is not a GitHub repository"
        repository = f"{match.group(1)}/{match.group(2)}"
        query = urllib.parse.urlencode(
            {"branch": branch, "event": "push", "head_sha": sha, "per_page": 10}
        )
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "charting-platform-workflow",
        }
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(
            f"https://api.github.com/repos/{repository}/actions/runs?{query}",
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read())
            runs = [
                {
                    "headSha": item.get("head_sha"),
                    "headBranch": item.get("head_branch"),
                    "status": item.get("status"),
                    "conclusion": item.get("conclusion"),
                    "runAttempt": item.get("run_attempt") or 1,
                }
                for item in payload.get("workflow_runs", [])
            ]
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            json.JSONDecodeError,
        ) as exc:
            return "unknown", f"{gh_error}; read-only public API unavailable: {exc}"
    matching = [
        item
        for item in runs
        if item.get("headSha") == sha and item.get("headBranch", branch) == branch
    ]
    if not matching:
        return "missing", "no exact push CI run exists"
    run = max(matching, key=lambda item: int(item.get("runAttempt") or 1))
    if run.get("status") != "completed":
        return "pending", "exact push CI run is still running"
    return (
        ("green", "exact push CI is green")
        if run.get("conclusion") == "success"
        else ("red", "exact push CI is not green")
    )


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


def docker_disposition(identifier: str, projects: set[str]) -> tuple[str, str]:
    if not shutil.which("docker"):
        return "unknown", "Docker CLI unavailable"
    result = subprocess.run(
        ["docker", "ps", "-aq", "--filter", f"label=charting.worktree.id={identifier}"],
        text=True,
        capture_output=True,
    )
    if result.returncode:
        return "unknown", result.stderr.strip() or "Docker daemon unavailable"
    owned = {line for line in result.stdout.splitlines() if line}
    for project in projects:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "-aq",
                "--filter",
                f"label=com.docker.compose.project={project}",
            ],
            text=True,
            capture_output=True,
        )
        if result.returncode:
            return "unknown", result.stderr.strip() or "Docker daemon unavailable"
        owned.update(line for line in result.stdout.splitlines() if line)
    return (
        ("clean", "no owned containers")
        if not owned
        else ("present", f"{len(owned)} owned container(s)")
    )


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
            reason = "create a schema-4 branch-owned workstream"
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
        ci_state, ci_reason = (
            exact_ci(branch, remote)
            if remote
            else ("missing", "remote SHA is unavailable")
        )
        worktree_identifier = (
            f"{slug(branch)}-{hashlib.sha256(str(path).encode()).hexdigest()[:10]}"
        )
        dirty = bool(git("status", "--porcelain", cwd=path)) if path.exists() else True
        docker_state, docker_reason = docker_disposition(
            worktree_identifier,
            {
                f"charting-dev-{slug(branch)}-{hashlib.sha256(str(path).encode()).hexdigest()[:8]}",
                f"charting-stack-{slug(branch)}-{hashlib.sha256(str(path).encode()).hexdigest()[:8]}",
            },
        )
        claim_path = (
            common_root() / ".ai" / "session-claims" / f"{worktree_identifier}.json"
        )
        claim = None
        if claim_path.exists():
            try:
                claim = json.loads(claim_path.read_text())
            except json.JSONDecodeError:
                claim = {"invalid": True}
        ahead_behind = None
        if remote:
            counts = git(
                "rev-list",
                "--left-right",
                "--count",
                f"staging...{remote}",
                check=False,
            )
            if counts:
                left, right = counts.split()[:2]
                ahead_behind = {
                    "behind_staging": int(left),
                    "ahead_of_staging": int(right),
                }
        retained = []
        retained_path = common_root() / ".ai" / "runtime" / "retained-volumes.json"
        if retained_path.exists():
            try:
                retained = [
                    name
                    for name, item in json.loads(retained_path.read_text()).items()
                    if item.get("worktree_id") == worktree_identifier
                ]
            except (OSError, json.JSONDecodeError):
                retained = ["unknown"]
        if state == "ready" and (ci_state != "green" or dirty):
            state = "blocked"
            reason = (
                f"exact branch CI: {ci_reason}"
                if ci_state != "green"
                else "source worktree is dirty"
            )
        elif claim:
            state = "in-progress"
            reason = f"active writer session {claim.get('session_id', 'unknown')}"
        output.append(
            {
                "branch": branch,
                "path": str(path),
                "head": head or None,
                "remote": remote or None,
                "synchronized": bool(head and head == remote),
                "dirty": dirty,
                "status": status,
                "validation_tier": tier,
                "state": state,
                "reason": reason,
                "ci_state": ci_state,
                "ci_reason": ci_reason,
                "ahead_behind_staging": ahead_behind,
                "active_claim": claim,
                "retained_docker_resources": retained,
                "docker_state": docker_state,
                "docker_reason": docker_reason,
                "worktree_mtime": datetime.fromtimestamp(
                    path.stat().st_mtime, UTC
                ).isoformat()
                if path.exists()
                else None,
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
        degraded = common_root() / ".ai" / "staging-degraded.json"
        if degraded.exists():
            raise SystemExit(
                "staging is marked degraded; repair it before integrating ready branches"
            )
        items = queue()
        full = sorted(
            (
                item
                for item in items
                if item["state"] == "ready"
                and item["validation_tier"] != "focused_only"
            ),
            key=lambda item: (
                str(item.get("worktree_mtime") or "9999"),
                str(item["branch"]),
            ),
        )
        if not full:
            print(
                "no closure-ready full_integration branch is available; focused-only branches wait"
            )
            return 0
        focused = sorted(
            (
                item
                for item in items
                if item["state"] == "ready"
                and item["validation_tier"] == "focused_only"
            ),
            key=lambda item: str(item["branch"]),
        )
        selected = [full[0]] + focused
        if any(item.get("active_claim") for item in selected):
            raise SystemExit("a selected branch has an active writer claim")
        if any(item.get("retained_docker_resources") for item in selected):
            raise SystemExit(
                "a selected branch retains Docker resources; account for them before integration"
            )
        if any(item.get("docker_state") != "clean" for item in selected):
            raise SystemExit(
                "every selected branch must have a clean, inspectable Docker disposition"
            )
        if any(item.get("ci_state") != "green" for item in selected):
            raise SystemExit("every selected branch must have exact green branch CI")
        receipt_dir = common_root() / ".ai" / "staging-attempts"
        receipt_dir.mkdir(parents=True, exist_ok=True)
        receipt = (
            receipt_dir / f"queue-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
        )
        receipt.write_text(
            json.dumps(
                {
                    "selected": [
                        {"branch": item["branch"], "sha": item["remote"]}
                        for item in selected
                    ]
                },
                indent=2,
            )
            + "\n"
        )
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
