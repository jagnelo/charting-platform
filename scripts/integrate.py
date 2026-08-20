#!/usr/bin/env python3
"""Create and, after a green gate, publish one exact integration candidate."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
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


def assert_clean_synchronized(repo: Path, branch: str) -> Path:
    if out(["git", "branch", "--show-current"], repo) != "master":
        raise SystemExit("integration must run from the root master checkout")
    if out(["git", "status", "--porcelain"], repo):
        raise SystemExit("root master is dirty")
    if out(["git", "rev-parse", "HEAD"], repo) != out(
        ["git", "rev-parse", "origin/master"], repo
    ):
        raise SystemExit("root master is not synchronized with origin/master")
    if degraded_marker(repo).exists():
        raise SystemExit(
            "master is degraded because its independent GitHub replay failed; inspect "
            f"{degraded_marker(repo)} before integrating another branch"
        )
    source = branch_worktree(repo, branch)
    if out(["git", "status", "--porcelain"], source):
        raise SystemExit(f"source worktree is dirty: {source}")
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


def validate(repo: Path, candidate: Path, branch: str, source_sha: str) -> None:
    if out(["git", "rev-parse", "HEAD"], repo) != out(
        ["git", "rev-parse", "origin/master"], repo
    ):
        raise SystemExit("master advanced while the candidate was being validated")
    if out(["git", "rev-parse", "HEAD"], branch_worktree(repo, branch)) != source_sha:
        raise SystemExit(
            "source branch no longer resolves to the captured candidate SHA"
        )
    run(["make", "validate-integration"], candidate)
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
    if not matching:
        raise SystemExit(f"no push-triggered GitHub Actions replay exists for {commit}")
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
                "source_sha": candidate_sha,
                "candidate_sha": candidate_sha,
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
    args = parser.parse_args()
    repo = root()
    with integration_lock(repo):
        source = assert_clean_synchronized(repo, args.branch)
        source_sha = out(["git", "rev-parse", "HEAD"], source)
        if args.continue_candidate:
            candidate, candidate_sha = continue_candidate(repo, args.branch, source_sha)
        else:
            candidate, candidate_sha = make_candidate(repo, args.branch, source_sha)
        validate(repo, candidate, args.branch, source_sha)
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
