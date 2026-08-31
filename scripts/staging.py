#!/usr/bin/env python3
"""Persistent staging integration and exact green promotion workflow."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

PREFIXES = ("feat/", "fix/", "chore/", "docs/", "test/")
ROOT = Path(
    subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
)
COMMON = Path(
    subprocess.check_output(
        ["git", "rev-parse", "--git-common-dir"], cwd=ROOT, text=True
    ).strip()
)
if not COMMON.is_absolute():
    COMMON = ROOT / COMMON
COMMON_ROOT = COMMON.resolve().parent
AI = COMMON_ROOT / ".ai"
STAGING_PATH = AI / "worktrees" / "staging"
DEGRADED = AI / "staging-degraded.json"
MASTER_DEGRADED = AI / "master-degraded.json"
CI_DISCOVERY_ATTEMPTS = 12
CI_DISCOVERY_DELAY_SECONDS = 5.0


def run(
    *args: str, cwd: Path = ROOT, check: bool = True
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if check and result.returncode:
        raise SystemExit(
            result.stderr.strip() or result.stdout.strip() or "command failed"
        )
    return result


def git(*args: str, cwd: Path = ROOT, check: bool = True) -> str:
    return run("git", *args, cwd=cwd, check=check).stdout.strip()


def full_sha(value: str, label: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise SystemExit(f"{label} must be a full lowercase 40-character SHA")
    return value


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


def fetch_branch(branch: str, *, cwd: Path = ROOT) -> None:
    git(
        "fetch",
        "origin",
        f"+refs/heads/{branch}:refs/remotes/origin/{branch}",
        cwd=cwd,
    )


@contextlib.contextmanager
def integration_lock():
    path = AI / "locks" / "staging-integration.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def root_master_ready() -> None:
    if git("branch", "--show-current") != "master":
        raise SystemExit("run this command from the root master checkout")
    if git("status", "--porcelain"):
        raise SystemExit("the root master checkout is dirty")
    fetch_branch("master")
    if git("rev-parse", "HEAD") != git("rev-parse", "origin/master"):
        raise SystemExit("local master is not synchronized with origin/master")


def require_healthy_master() -> None:
    """Refuse staging bootstrap while the last master replay is unresolved."""
    if MASTER_DEGRADED.exists():
        try:
            data = json.loads(MASTER_DEGRADED.read_text())
        except json.JSONDecodeError:
            data = {}
        sha = data.get("master_sha", "unknown")
        reason = data.get("reason", "the independent master CI replay did not pass")
        raise SystemExit(
            f"master is marked degraded at {sha}: {reason}; "
            "repair or rerun the exact master replay before bootstrapping staging"
        )


def synchronized(path: Path, branch: str) -> str:
    if git("branch", "--show-current", cwd=path) != branch:
        raise SystemExit(f"{path} is not the {branch} worktree")
    if git("status", "--porcelain", cwd=path):
        raise SystemExit(f"{branch} is dirty")
    local = git("rev-parse", "HEAD", cwd=path)
    remote = git("rev-parse", f"origin/{branch}", cwd=path, check=False)
    if not remote or local != remote:
        raise SystemExit(f"{branch} is not synchronized with origin/{branch}")
    return local


def worktree_path(branch: str) -> Path:
    records = git("worktree", "list", "--porcelain").splitlines()
    path: Path | None = None
    for line in records + [""]:
        if line.startswith("worktree "):
            path = Path(line.removeprefix("worktree ")).resolve()
        elif line == f"branch refs/heads/{branch}" and path:
            return path
        elif not line:
            path = None
    raise SystemExit(f"branch is not checked out in a worktree: {branch}")


def plan_values(path: Path, branch: str) -> dict[str, str]:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", branch).strip("-").lower()
    plan = path / "ops" / "workstreams" / slug / "plan.yaml"
    if not plan.exists():
        raise SystemExit(f"missing branch workstream plan: {plan}")
    values: dict[str, str] = {}
    for line in plan.read_text().splitlines():
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if match:
            values[match.group(1)] = match.group(2).strip().strip("'\"")
    return values


def require_closed_workstream(path: Path, branch: str) -> None:
    values = plan_values(path, branch)
    failures: list[str] = []
    if values.get("schema") not in {"2", "3"}:
        failures.append("schema must be 2 or 3")
    if values.get("schema") == "3" and values.get("goal_budget_policy") not in {
        "unbounded_unless_human_authorized",
    }:
        failures.append("schema-3 goal_budget_policy must be explicit")
    if values.get("status") != "ready_for_integration":
        failures.append("status must be ready_for_integration")
    for key in (
        "human_intent_authorization",
        "human_closure_authorization",
        "closure_summary",
    ):
        value = values.get(key, "").lower()
        if not value or value == "pending" or value.startswith("pending_"):
            failures.append(f"{key} must record the human-approved closure")
    if values.get("validation_tier") not in {"focused_only", "full_integration"}:
        failures.append("validation_tier must record the human-approved decision")
    source_sha = git("rev-parse", "HEAD", cwd=path)
    closure_summary = values.get("closure_summary", "")
    if (
        source_sha not in closure_summary
        and "integration_capture: exact branch head" not in closure_summary.lower()
    ):
        failures.append(
            "closure_summary must contain the exact source SHA or explicitly require integration_capture: exact branch HEAD"
        )
    if failures:
        raise SystemExit(f"{branch} cannot enter staging: " + "; ".join(failures))


def github_run(branch: str, commit: str, *, exhaustive: bool) -> dict[str, object]:
    if not shutil_which("gh"):
        raise SystemExit(
            "GitHub CLI (gh) is required to verify the exact remote CI run"
        )
    runs: list[dict[str, object]] = []
    for attempt in range(CI_DISCOVERY_ATTEMPTS):
        result = run(
            "gh",
            "run",
            "list",
            "--workflow",
            "ci.yml",
            "--branch",
            branch,
            "--commit",
            commit,
            "--event",
            "push",
            "--limit",
            "10",
            "--json",
            "databaseId,headSha,headBranch,status,conclusion,url",
        )
        runs = [
            item
            for item in json.loads(result.stdout or "[]")
            if item.get("headSha") == commit and item.get("headBranch") == branch
        ]
        if runs:
            break
        if attempt + 1 < CI_DISCOVERY_ATTEMPTS:
            # GitHub registers a push-triggered workflow asynchronously. A just-
            # pushed master commit must not be marked degraded merely because the
            # run has not appeared in the API response yet.
            time.sleep(CI_DISCOVERY_DELAY_SECONDS)
    if not runs:
        raise SystemExit(
            f"no GitHub CI push run exists for exact {branch} commit {commit}"
        )
    selected = runs[0]
    run_id = str(selected["databaseId"])
    if selected.get("status") != "completed":
        subprocess.run(
            ["gh", "run", "watch", run_id, "--exit-status"], cwd=ROOT, check=False
        )
        refreshed = run(
            "gh", "run", "view", run_id, "--json", "status,conclusion,url,jobs"
        )
        selected.update(json.loads(refreshed.stdout))
    else:
        detail = run("gh", "run", "view", run_id, "--json", "jobs")
        selected.update(json.loads(detail.stdout))
    if selected.get("conclusion") != "success":
        raise SystemExit(
            f"GitHub CI is not green for exact {branch} commit {commit}: {selected.get('url')}"
        )
    if exhaustive:
        jobs = selected.get("jobs", [])
        matches = [
            job for job in jobs if job.get("name") == "Exhaustive Integration Gate"
        ]
        if len(matches) != 1 or matches[0].get("conclusion") != "success":
            raise SystemExit(
                f"exact {branch} run did not pass the Exhaustive Integration Gate"
            )
    else:
        jobs = selected.get("jobs", [])
        matches = [job for job in jobs if job.get("name") == "Branch-declared Tests"]
        if len(matches) != 1 or matches[0].get("conclusion") != "success":
            raise SystemExit(
                f"exact {branch} run did not pass its Branch-declared Tests job"
            )
    return selected


def shutil_which(command: str) -> str | None:
    import shutil

    return shutil.which(command)


def record_attempt(payload: dict[str, object]) -> None:
    directory = AI / "staging-attempts"
    directory.mkdir(parents=True, exist_ok=True)
    token = str(payload.get("source_sha", payload.get("staging_sha", "unknown")))[:12]
    (
        directory / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{token}.json"
    ).write_text(json.dumps(payload, indent=2) + "\n")


def bootstrap(confirm: str) -> None:
    root_master_ready()
    require_healthy_master()
    current = git("rev-parse", "HEAD")
    if full_sha(confirm, "CONFIRM") != current:
        raise SystemExit(
            "CONFIRM must exactly equal the current synchronized master SHA"
        )
    local = git("rev-parse", "--verify", "refs/heads/staging", check=False)
    remote_line = git("ls-remote", "--heads", "origin", "staging", check=False)
    remote = remote_line.split()[0] if remote_line else ""
    if local and local != current:
        raise SystemExit("existing local staging does not match confirmed master")
    if remote and remote != current:
        raise SystemExit("existing origin/staging does not match confirmed master")
    if STAGING_PATH.exists() and not (STAGING_PATH / ".git").exists():
        raise SystemExit(
            f"staging path exists but is not a Git worktree: {STAGING_PATH}"
        )
    STAGING_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not local:
        git("branch", "staging", current)
    if not remote:
        git("push", "-u", "origin", "staging")
    if not STAGING_PATH.exists():
        git("worktree", "add", str(STAGING_PATH), "staging")
    fetch_branch("staging", cwd=STAGING_PATH)
    synchronized(STAGING_PATH, "staging")
    print(f"staging bootstrapped at {current}: {STAGING_PATH}")


def ensure_staging(*, remediate: bool) -> str:
    if not STAGING_PATH.exists():
        raise SystemExit(
            "staging is not bootstrapped; run make staging-bootstrap from master"
        )
    fetch_branch("staging", cwd=STAGING_PATH)
    sha = synchronized(STAGING_PATH, "staging")
    if DEGRADED.exists() and not remediate:
        data = json.loads(DEGRADED.read_text())
        raise SystemExit(
            f"staging is degraded at {data.get('staging_sha')}; only an explicit remediation integration may proceed"
        )
    return sha


def integrate(branches: list[str], *, remediate: bool) -> None:
    root_master_ready()
    if not branches or len(set(branches)) != len(branches):
        raise SystemExit("name one or more unique source branches")
    if any(not branch.startswith(PREFIXES) for branch in branches):
        raise SystemExit("source branches must use a supported work prefix")
    with integration_lock():
        start = ensure_staging(remediate=remediate)
        sources: list[tuple[str, Path, str]] = []
        for branch in branches:
            path = worktree_path(branch)
            fetch_branch(branch, cwd=path)
            sha = synchronized(path, branch)
            require_closed_workstream(path, branch)
            if (
                remediate
                and git("merge-base", "staging", sha, cwd=STAGING_PATH) != start
            ):
                raise SystemExit(
                    "a remediation branch must be based directly on the exact degraded staging SHA"
                )
            github_run(branch, sha, exhaustive=False)
            sources.append((branch, path, sha))
        merged: list[dict[str, str]] = []
        try:
            for branch, _, sha in sources:
                result = run(
                    "git",
                    "merge",
                    "--no-ff",
                    "--no-edit",
                    sha,
                    cwd=STAGING_PATH,
                    check=False,
                )
                if result.returncode:
                    conflicts = git(
                        "diff",
                        "--name-only",
                        "--diff-filter=U",
                        cwd=STAGING_PATH,
                        check=False,
                    ).splitlines()
                    git("merge", "--abort", cwd=STAGING_PATH, check=False)
                    git("reset", "--hard", start, cwd=STAGING_PATH)
                    record_attempt(
                        {
                            "state": "conflict",
                            "created_at": timestamp(),
                            "starting_staging_sha": start,
                            "source_branch": branch,
                            "source_sha": sha,
                            "conflicts": conflicts,
                        }
                    )
                    raise SystemExit(
                        "staging merge conflicted and was restored unchanged; resolve the combined behavior on the source branch, push it, and rerun its CI"
                    )
                merged.append({"branch": branch, "sha": sha})
            push = run(
                "git", "push", "origin", "staging", cwd=STAGING_PATH, check=False
            )
            if push.returncode:
                remote = git(
                    "rev-parse", "origin/staging", cwd=STAGING_PATH, check=False
                )
                if remote == start:
                    git("reset", "--hard", start, cwd=STAGING_PATH)
                record_attempt(
                    {
                        "state": "push_failed",
                        "created_at": timestamp(),
                        "starting_staging_sha": start,
                        "sources": merged,
                        "error": push.stderr.strip(),
                    }
                )
                raise SystemExit(push.stderr.strip() or "staging push failed")
            staging_sha = git("rev-parse", "HEAD", cwd=STAGING_PATH)
            try:
                ci = github_run("staging", staging_sha, exhaustive=True)
            except BaseException as exc:
                DEGRADED.parent.mkdir(parents=True, exist_ok=True)
                DEGRADED.write_text(
                    json.dumps(
                        {
                            "staging_sha": staging_sha,
                            "starting_staging_sha": start,
                            "sources": merged,
                            "recorded_at": timestamp(),
                            "reason": str(exc),
                        },
                        indent=2,
                    )
                    + "\n"
                )
                record_attempt(
                    {
                        "state": "degraded",
                        "created_at": timestamp(),
                        "staging_sha": staging_sha,
                        "sources": merged,
                        "reason": str(exc),
                    }
                )
                raise
            fetch_branch("staging", cwd=STAGING_PATH)
            if synchronized(STAGING_PATH, "staging") != staging_sha:
                raise SystemExit(
                    "staging advanced while its exact CI run was evaluated; rerun integration"
                )
            DEGRADED.unlink(missing_ok=True)
            record_attempt(
                {
                    "state": "green",
                    "created_at": timestamp(),
                    "starting_staging_sha": start,
                    "staging_sha": staging_sha,
                    "sources": merged,
                    "github_run": ci.get("url"),
                }
            )
            print(f"staging is green at {staging_sha}")
        except BaseException:
            if git("status", "--porcelain", cwd=STAGING_PATH):
                git("merge", "--abort", cwd=STAGING_PATH, check=False)
                git("reset", "--hard", start, cwd=STAGING_PATH)
            raise


def promote(commit: str, confirm: str) -> None:
    commit = full_sha(commit, "COMMIT")
    if full_sha(confirm, "CONFIRM") != commit:
        raise SystemExit("CONFIRM must exactly equal COMMIT")
    root_master_ready()
    with integration_lock():
        master_start = git("rev-parse", "master")
        staging_sha = ensure_staging(remediate=False)
        if staging_sha != commit:
            raise SystemExit(
                "COMMIT must be the exact current synchronized staging SHA"
            )
        ci = github_run("staging", commit, exhaustive=True)
        root_master_ready()
        if synchronized(STAGING_PATH, "staging") != commit:
            raise SystemExit("staging advanced during promotion verification")
        check = run("git", "merge-base", "--is-ancestor", "master", commit, check=False)
        if check.returncode:
            raise SystemExit("master is not an ancestor of the green staging commit")
        git("merge", "--ff-only", commit)
        push = run("git", "push", "origin", "master", check=False)
        if push.returncode:
            remote = git("rev-parse", "origin/master", check=False)
            if remote == master_start:
                git("reset", "--hard", master_start)
            raise SystemExit(push.stderr.strip() or "master push failed")
        try:
            master_ci = github_run("master", commit, exhaustive=True)
        except BaseException as exc:
            MASTER_DEGRADED.parent.mkdir(parents=True, exist_ok=True)
            MASTER_DEGRADED.write_text(
                json.dumps(
                    {
                        "master_sha": commit,
                        "recorded_at": timestamp(),
                        "reason": str(exc),
                    },
                    indent=2,
                )
                + "\n"
            )
            raise
        fetch_branch("master")
        if (
            git("rev-parse", "HEAD") != commit
            or git("rev-parse", "origin/master") != commit
        ):
            raise SystemExit("master advanced while its exact CI replay was evaluated")
        MASTER_DEGRADED.unlink(missing_ok=True)
        receipt = AI / "validation" / f"{commit}.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(
            json.dumps(
                {
                    "candidate_sha": commit,
                    "tree": git("rev-parse", f"{commit}^{{tree}}"),
                    "source": "green-staging-promotion",
                    "staging_github_replay": ci.get("url"),
                    "master_github_replay": master_ci.get("url"),
                    "github_replay": "pass",
                    "recorded_at": timestamp(),
                },
                indent=2,
            )
            + "\n"
        )
        print(f"master promoted and independently replayed green at {commit}")


def status() -> None:
    payload: dict[str, object] = {
        "staging_worktree": str(STAGING_PATH),
        "degraded": DEGRADED.exists(),
        "master_degraded": MASTER_DEGRADED.exists(),
    }
    master_path = worktree_path("master")
    for branch, path in (("master", master_path), ("staging", STAGING_PATH)):
        if path.exists() and git(
            "show-ref", "--verify", f"refs/heads/{branch}", check=False
        ):
            fetch_branch(branch, cwd=path)
            local = git("rev-parse", branch, cwd=path)
            remote = git("rev-parse", f"origin/{branch}", cwd=path, check=False)
            payload[branch] = {
                "local": local,
                "remote": remote or None,
                "synchronized": local == remote,
                "clean": not bool(git("status", "--porcelain", cwd=path)),
            }
    print(json.dumps(payload, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("bootstrap")
    p.add_argument("--confirm", required=True)
    p = sub.add_parser("integrate")
    p.add_argument("branches", nargs="+")
    p.add_argument("--remediate", action="store_true")
    p = sub.add_parser("promote")
    p.add_argument("--commit", required=True)
    p.add_argument("--confirm", required=True)
    sub.add_parser("status")
    args = parser.parse_args()
    if args.command == "bootstrap":
        bootstrap(args.confirm)
    elif args.command == "integrate":
        integrate(args.branches, remediate=args.remediate)
    elif args.command == "promote":
        promote(args.commit, args.confirm)
    else:
        status()
    return 0


if __name__ == "__main__":
    sys.exit(main())
