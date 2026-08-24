#!/usr/bin/env python3
"""Create and, after a green gate, publish one exact integration candidate."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path


def run(
    args: list[str], cwd: Path, check: bool = True, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, env=env)
    if check and result.returncode:
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        raise SystemExit(result.returncode)
    return result


def out(args: list[str], cwd: Path) -> str:
    return run(args, cwd).stdout.strip()


def has_source_changes(repo: Path) -> bool:
    """Ignore only the generated degraded marker when checking source cleanliness."""
    status = run(
        ["git", "status", "--porcelain", "--untracked-files=all"], repo
    ).stdout.splitlines()
    return any(line and line[3:] != ".ai/master-degraded.json" for line in status)


def root() -> Path:
    return Path(out(["git", "rev-parse", "--show-toplevel"], Path.cwd())).resolve()


def common_root(repo: Path) -> Path:
    common = Path(out(["git", "rev-parse", "--git-common-dir"], repo))
    if not common.is_absolute():
        common = repo / common
    return common.resolve().parent


def degraded_marker(repo: Path) -> Path:
    return common_root(repo) / ".ai" / "master-degraded.json"


@contextlib.contextmanager
def integration_lock(repo: Path):
    path = common_root(repo) / ".ai" / "integration.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        yield
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def branch_worktree(repo: Path, branch: str) -> Path:
    result = out(["git", "worktree", "list", "--porcelain"], repo).splitlines()
    current: Path | None = None
    for line in result + [""]:
        if line.startswith("worktree "):
            current = Path(line.removeprefix("worktree ")).resolve()
        elif line == "" and current is not None:
            record = out(["git", "-C", str(current), "branch", "--show-current"], repo)
            if record == branch:
                return current
            current = None
    raise SystemExit(f"source branch is not checked out in a worktree: {branch}")


def branch_slug(branch: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", branch).strip("-").lower()


def workstream_values(source: Path, branch: str) -> dict[str, str]:
    plan = source / "ops" / "workstreams" / branch_slug(branch) / "plan.yaml"
    if not plan.exists():
        raise SystemExit(f"source branch has no workstream plan: {plan}")
    values: dict[str, str] = {}
    for line in plan.read_text().splitlines():
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):(?:\s*)(.*)$", line)
        if match:
            values[match.group(1)] = match.group(2).strip().strip("'\"")
    return values


def require_human_closure(source: Path, branch: str) -> str:
    values = workstream_values(source, branch)
    if values.get("schema") != "2":
        raise SystemExit(
            "integration requires a schema-2 workstream with recorded human intent and closure authorization"
        )
    if not values.get("human_intent_authorization"):
        raise SystemExit("workstream does not record the human request that authorized this work")
    closure = values.get("human_closure_authorization", "").strip().lower()
    if not closure or closure in {"pending", "none", "false", "no"}:
        raise SystemExit(
            "integration requires explicit human closure authorization recorded in "
            "ops/workstreams/<branch>/plan.yaml"
        )
    summary = values.get("closure_summary", "").strip().lower()
    if not summary or summary in {"pending", "none", "n/a"}:
        raise SystemExit(
            "integration requires a completed PR-equivalent closure_summary in the workstream"
        )
    if values.get("status") != "ready_for_integration":
        raise SystemExit(
            "integration requires workstream status ready_for_integration; green tests alone are only ready for human review"
        )
    tier = values.get("validation_tier", "")
    if tier == "full_integration":
        return tier
    if tier != "focused_only":
        raise SystemExit(
            "integration requires an explicit human validation decision: full_integration or focused_only"
        )
    validation = values.get("human_validation_authorization", "").strip().lower()
    if not validation or validation in {"pending", "none", "false", "no"}:
        raise SystemExit(
            "focused-only integration requires explicit human validation authorization recorded in the workstream"
        )
    changed = out(["git", "diff", "--name-only", "master...HEAD"], source).splitlines()
    allowed = ("docs/", "scripts/", "ops/workstreams/", "AGENTS.md", "Makefile")
    disallowed = [path for path in changed if not path.startswith(allowed)]
    if disallowed:
        raise SystemExit(
            "focused-only validation is limited to documentation/workflow helpers; "
            f"full integration is required for: {', '.join(disallowed)}"
        )
    return tier


def assert_clean_synchronized(
    repo: Path, branch: str, *, remediate_degraded: bool = False
) -> Path:
    if out(["git", "branch", "--show-current"], repo) != "master":
        raise SystemExit("integration must run from the root master checkout")
    if has_source_changes(repo):
        raise SystemExit("root master is dirty")
    if out(["git", "rev-parse", "HEAD"], repo) != out(
        ["git", "rev-parse", "origin/master"], repo
    ):
        raise SystemExit("root master is not synchronized with origin/master")
    marker = degraded_marker(repo)
    if marker.exists():
        if not remediate_degraded:
            raise SystemExit(
                "master is degraded because its independent GitHub replay failed; inspect "
                f"{marker} before integrating another branch, or use "
                "--remediate-degraded only for a repair branch based on this exact master SHA"
            )
        try:
            degraded = json.loads(marker.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"cannot read degraded master marker: {marker}: {exc}") from exc
        current = out(["git", "rev-parse", "HEAD"], repo)
        if degraded.get("master") != current:
            raise SystemExit(
                "degraded master marker does not describe the current synchronized master; "
                "refresh the marker through the publish/replay workflow"
            )
    source = branch_worktree(repo, branch)
    if has_source_changes(source):
        raise SystemExit(f"source worktree is dirty: {source}")
    if marker.exists() and remediate_degraded:
        current = out(["git", "rev-parse", "HEAD"], repo)
        merge_base = out(["git", "merge-base", "master", branch], repo)
        if merge_base != current:
            raise SystemExit(
                "degraded-master remediation branch must be based directly on the "
                "current degraded master SHA"
            )
    return source


def candidate_path(repo: Path, branch: str, source_sha: str) -> Path:
    token = hashlib.sha256(f"{branch}:{source_sha}".encode()).hexdigest()[:12]
    return (
        common_root(repo)
        / ".ai"
        / "integration"
        / f"{branch.replace('/', '-')}-{token}"
    )


def make_candidate(repo: Path, branch: str, source_sha: str) -> tuple[Path, str]:
    candidate = candidate_path(repo, branch, source_sha)
    if candidate.exists():
        raise SystemExit(
            f"candidate path already exists; inspect or remove it explicitly: {candidate}"
        )
    candidate.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "worktree", "add", "--detach", str(candidate), "master"], repo)
    merge = run(
        [
            "git",
            "merge",
            "--no-ff",
            source_sha,
            "-m",
            f"Integrate {branch} at {source_sha}",
        ],
        candidate,
        check=False,
    )
    if merge.returncode:
        conflicts = out(["git", "diff", "--name-only", "--diff-filter=U"], candidate)
        report = candidate / "ops" / "integration-conflicts.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            f"# Integration conflicts\n\nSource: `{branch}` at `{source_sha}`\n\n"
            "Resolve semantically; preserve both behaviours unless the workstream documents a superseding decision.\n\n"
            "Conflicted paths:\n"
            + "\n".join(f"- `{path}`" for path in conflicts.splitlines())
            + "\n"
        )
        print(merge.stdout, end="")
        print(merge.stderr, end="", file=sys.stderr)
        raise SystemExit(
            f"candidate has merge conflicts; resolve them in {candidate} and rerun with --continue"
        )
    return candidate, out(["git", "rev-parse", "HEAD"], candidate)


def continue_candidate(repo: Path, branch: str, source_sha: str) -> tuple[Path, str]:
    """Resume a conflict candidate after semantic edits were made in place."""
    candidate = candidate_path(repo, branch, source_sha)
    if not candidate.exists():
        raise SystemExit(f"no paused candidate exists at {candidate}")
    conflicts = out(["git", "diff", "--name-only", "--diff-filter=U"], candidate)
    if conflicts:
        raise SystemExit(
            "candidate still has unresolved paths; resolve and stage every conflict:\n"
            + conflicts
        )
    merge_head = Path(out(["git", "rev-parse", "--git-path", "MERGE_HEAD"], candidate))
    if not merge_head.is_absolute():
        merge_head = candidate / merge_head
    report = candidate / "ops" / "integration-conflicts.md"
    if merge_head.exists():
        # The report is part of the durable conflict record. Only that known
        # generated path is staged automatically; semantic source changes must
        # have been reviewed and staged by the resolving agent.
        if report.exists():
            run(["git", "add", str(report)], candidate)
        env = {**os.environ, "GIT_EDITOR": ":"}
        run(["git", "merge", "--continue"], candidate, env=env)
    if (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", source_sha, "HEAD"],
            cwd=candidate,
            capture_output=True,
        ).returncode
        != 0
    ):
        raise SystemExit("paused candidate does not contain the captured source SHA")
    return candidate, out(["git", "rev-parse", "HEAD"], candidate)


def validate(repo: Path, candidate: Path, branch: str, source_sha: str, tier: str) -> None:
    if out(["git", "rev-parse", "HEAD"], repo) != out(
        ["git", "rev-parse", "origin/master"], repo
    ):
        raise SystemExit("master advanced while the candidate was being validated")
    if out(["git", "rev-parse", "HEAD"], branch_worktree(repo, branch)) != source_sha:
        raise SystemExit(
            "source branch no longer resolves to the captured candidate SHA"
        )
    run(
        ["make", "validate-integration" if tier == "full_integration" else "validate-focused-integration"],
        candidate,
        env={**os.environ, "INTEGRATION_BRANCH": branch},
    )
    if out(["git", "rev-parse", "HEAD"], branch_worktree(repo, branch)) != source_sha:
        raise SystemExit(
            "source branch advanced while the candidate was being validated"
        )
    github_replay(repo, source_sha)
    if out(["git", "status", "--porcelain"], candidate):
        raise SystemExit(
            "integration gate changed the candidate; generated changes must be reviewed explicitly"
        )


def github_replay(repo: Path, commit: str) -> dict[str, str]:
    """Require the independent push-triggered GitHub workflow to pass."""
    if shutil.which("gh") is None:
        raise SystemExit("gh CLI is required to verify the independent GitHub replay")
    wait_seconds = max(0.0, float(os.environ.get("INTEGRATION_GITHUB_REPLAY_WAIT_SECONDS", "120")))
    deadline = time.monotonic() + wait_seconds
    matching: list[dict[str, object]] = []
    while True:
        listed = run(
            [
                "gh",
                "run",
                "list",
                "--workflow",
                "ci.yml",
                "--commit",
                commit,
                "--event",
                "push",
                "--limit",
                "20",
                "--json",
                "databaseId,headSha,status,conclusion,createdAt,url",
            ],
            repo,
            check=False,
        )
        if listed.returncode:
            raise SystemExit(
                listed.stderr.strip() or "could not query GitHub Actions replay"
            )
        try:
            runs = json.loads(listed.stdout)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"GitHub Actions returned invalid replay data: {exc}") from exc
        matching = [item for item in runs if item.get("headSha") == commit]
        if matching or time.monotonic() >= deadline:
            break
        time.sleep(min(2.0, max(0.1, deadline - time.monotonic())))
    if not matching:
        raise SystemExit(
            f"no push-triggered GitHub Actions replay exists for {commit} "
            f"after waiting {wait_seconds:.0f}s"
        )
    replay = matching[0]
    if replay.get("status") != "completed":
        watched = run(
            ["gh", "run", "watch", str(replay["databaseId"]), "--exit-status"],
            repo,
            check=False,
        )
        if watched.returncode:
            raise SystemExit(
                f"GitHub Actions replay failed for {commit}: {replay.get('url', replay['databaseId'])}"
            )
        refreshed = run(
            [
                "gh",
                "run",
                "view",
                str(replay["databaseId"]),
                "--json",
                "status,conclusion",
            ],
            repo,
        )
        replay.update(json.loads(refreshed.stdout))
    if replay.get("status") != "completed" or replay.get("conclusion") != "success":
        raise SystemExit(
            f"GitHub Actions replay is not green for {commit}: {replay.get('url', replay['databaseId'])}"
        )
    return {
        "run_id": str(replay["databaseId"]),
        "url": str(replay.get("url", "")),
        "conclusion": "success",
    }


def publish(repo: Path, candidate: Path, candidate_sha: str, source_sha: str) -> None:
    before = out(["git", "rev-parse", "HEAD"], repo)
    run(["git", "merge", "--ff-only", candidate_sha], repo)
    if out(["git", "rev-parse", "HEAD"], repo) != candidate_sha:
        raise SystemExit("master did not advance to the tested candidate")
    run(["git", "push", "origin", "master"], repo)
    if out(["git", "rev-parse", "origin/master"], repo) != candidate_sha:
        raise SystemExit("origin/master does not match the tested candidate")
    try:
        replay = github_replay(repo, candidate_sha)
    except SystemExit as exc:
        marker = degraded_marker(repo)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            json.dumps(
                {
                    "master": candidate_sha,
                    "source_sha": source_sha,
                    "reason": str(exc),
                    "recorded_at": datetime.now(UTC).isoformat(),
                },
                indent=2,
            )
            + "\n"
        )
        raise
    receipt = common_root(repo) / ".ai" / "validation" / f"{candidate_sha}.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(
        json.dumps(
            {
                "source_sha": source_sha,
                "candidate_sha": candidate_sha,
                "source_tree": out(
                    ["git", "rev-parse", f"{source_sha}^{{tree}}"], repo
                ),
                "tree": out(["git", "rev-parse", f"{candidate_sha}^{{tree}}"], repo),
                "published_from": before,
                "master": candidate_sha,
                "github_replay": "pass",
                "github_run_id": replay["run_id"],
                "github_run_url": replay["url"],
                "validated_at": datetime.now(UTC).isoformat(),
            },
            indent=2,
        )
        + "\n"
    )
    degraded_marker(repo).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("branch")
    parser.add_argument("--continue", dest="continue_candidate", action="store_true")
    parser.add_argument(
        "--publish", action="store_true", help="publish only after the full gate passes"
    )
    parser.add_argument(
        "--remediate-degraded",
        action="store_true",
        help="allow only a repair branch based directly on the current degraded master SHA",
    )
    args = parser.parse_args()
    repo = root()
    with integration_lock(repo):
        source = assert_clean_synchronized(
            repo, args.branch, remediate_degraded=args.remediate_degraded
        )
        tier = require_human_closure(source, args.branch)
        source_sha = out(["git", "rev-parse", "HEAD"], source)
        if args.continue_candidate:
            candidate, candidate_sha = continue_candidate(repo, args.branch, source_sha)
        else:
            candidate, candidate_sha = make_candidate(repo, args.branch, source_sha)
        validate(repo, candidate, args.branch, source_sha, tier)
        print(
            json.dumps(
                {
                    "branch": args.branch,
                    "source_sha": source_sha,
                    "candidate": str(candidate),
                    "candidate_sha": candidate_sha,
                },
                indent=2,
            )
        )
        if args.publish:
            publish(repo, candidate, candidate_sha, source_sha)
            run(["git", "worktree", "remove", str(candidate)], repo)
            print(f"published master at {candidate_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
