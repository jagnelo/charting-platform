#!/usr/bin/env python3
"""Integrate an explicitly named, exact batch through one candidate and one master replay."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import integrate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("branches", nargs="+")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if len(set(args.branches)) != len(args.branches):
        raise SystemExit("a batch may not name a branch more than once")
    repo = integrate.root()
    with integrate.integration_lock(repo):
        sources: list[tuple[str, Path, str]] = []
        for branch in args.branches:
            source = integrate.assert_clean_synchronized(repo, branch)
            sources.append((branch, source, integrate.out(["git", "rev-parse", "HEAD"], source)))
        token = hashlib.sha256("\n".join(f"{b}:{s}" for b, _, s in sources).encode()).hexdigest()[:12]
        candidate = integrate.common_root(repo) / ".ai" / "integration" / f"batch-{token}"
        if candidate.exists():
            raise SystemExit(f"candidate already exists; inspect or remove it explicitly: {candidate}")
        candidate.parent.mkdir(parents=True, exist_ok=True)
        integrate.run(["git", "worktree", "add", "--detach", str(candidate), "master"], repo)
        for branch, _, sha in sources:
            merged = integrate.run(["git", "merge", "--no-ff", sha, "-m", f"Integrate {branch} at {sha}"], candidate, check=False)
            if merged.returncode:
                conflicts = integrate.out(["git", "diff", "--name-only", "--diff-filter=U"], candidate)
                report = candidate / "ops" / "integration-conflicts.md"
                report.parent.mkdir(parents=True, exist_ok=True)
                report.write_text("# Batch integration conflicts\n\n" + f"Current source: `{branch}` at `{sha}`\n\n" + "Conflicted paths:\n" + "\n".join(f"- `{p}`" for p in conflicts.splitlines()) + "\n")
                raise SystemExit(f"batch candidate paused at {candidate}; resolve semantically, record intent/tests, then restart a fresh batch")
        for branch, source, sha in sources:
            if integrate.out(["git", "rev-parse", "HEAD"], source) != sha:
                raise SystemExit(f"source branch advanced during batch preparation: {branch}")
            integrate.run(["make", "branch-tests", f"INTEGRATION_BRANCH={branch}"], candidate)
            integrate.github_replay(repo, sha)
        integrate.run(["make", "validate-integration"], candidate)
        if integrate.out(["git", "rev-parse", "HEAD"], repo) != integrate.out(["git", "rev-parse", "origin/master"], repo):
            raise SystemExit("master advanced while the batch candidate was validated")
        candidate_sha = integrate.out(["git", "rev-parse", "HEAD"], candidate)
        print(json.dumps({"branches": [b for b, _, _ in sources], "candidate": str(candidate), "candidate_sha": candidate_sha}, indent=2))
        if args.publish:
            integrate.publish(repo, candidate, candidate_sha, sources[-1][2])
            integrate.run(["git", "worktree", "remove", str(candidate)], repo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
