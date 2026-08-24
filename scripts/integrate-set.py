#!/usr/bin/env python3
"""Integrate an explicitly named, exact batch through one candidate and one master replay."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import integrate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("branches", nargs="+")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if not args.publish:
        raise SystemExit("integration candidates are not preview artifacts; rerun with --publish")
    if len(set(args.branches)) != len(args.branches):
        raise SystemExit("a batch may not name a branch more than once")
    repo = integrate.root()
    with integrate.integration_lock(repo):
        master_sha = integrate.out(["git", "rev-parse", "HEAD"], repo)
        sources: list[tuple[str, Path, str]] = []
        for branch in args.branches:
            source = integrate.assert_clean_synchronized(repo, branch)
            integrate.require_human_closure(source, branch)
            sources.append((branch, source, integrate.out(["git", "rev-parse", "HEAD"], source)))
        frozen_sources = "\n".join(f"{b}:{s}" for b, _, s in sources)
        label = "batch-" + "-".join(branch.replace("/", "-") for branch, _, _ in sources)
        identity = integrate.candidate_identity(label, master_sha, frozen_sources)
        candidate = integrate.candidate_path(repo, label, master_sha, frozen_sources)
        if candidate.exists():
            raise SystemExit(f"candidate already exists; inspect or remove it explicitly: {candidate}")
        candidate.parent.mkdir(parents=True, exist_ok=True)
        integrate.write_ledger(
            repo, identity, schema=1, branch=label, master_sha=master_sha,
            sources=[{"branch": branch, "sha": sha} for branch, _, sha in sources],
            candidate=str(candidate), state="created",
        )
        integrate.run(["git", "worktree", "add", "--detach", str(candidate), master_sha], repo)
        try:
            for branch, _, sha in sources:
                merged = integrate.run(["git", "merge", "--no-ff", sha, "-m", f"Integrate {branch} at {sha}"], candidate, check=False)
                if merged.returncode:
                    conflicts = integrate.out(["git", "diff", "--name-only", "--diff-filter=U"], candidate)
                    raise SystemExit(f"batch conflict while integrating {branch}: {conflicts}")
            for branch, source, sha in sources:
                if integrate.out(["git", "rev-parse", "HEAD"], source) != sha:
                    raise SystemExit(f"source branch advanced during batch preparation: {branch}")
                integrate.run(["make", "branch-tests", f"INTEGRATION_BRANCH={branch}"], candidate)
                integrate.github_replay(repo, sha)
            integrate.run(["make", "validate-integration"], candidate)
        except SystemExit as exc:
            integrate.write_ledger(repo, identity, state="failed_discarded", reason=str(exc), disposition="removed_after_recording")
            integrate.discard_candidate(repo, candidate)
            raise
        if integrate.out(["git", "rev-parse", "HEAD"], repo) != integrate.out(["git", "rev-parse", "origin/master"], repo):
            raise SystemExit("master advanced while the batch candidate was validated")
        candidate_sha = integrate.out(["git", "rev-parse", "HEAD"], candidate)
        print(json.dumps({"branches": [b for b, _, _ in sources], "candidate": str(candidate), "candidate_sha": candidate_sha}, indent=2))
        try:
            integrate.publish(repo, candidate, candidate_sha, sources[-1][2])
            integrate.write_ledger(repo, identity, state="published", candidate_sha=candidate_sha, disposition="removed_after_publication")
            integrate.run(["git", "worktree", "remove", str(candidate)], repo)
        except SystemExit as exc:
            integrate.write_ledger(
                repo, identity, state="publication_incomplete", candidate_sha=candidate_sha,
                reason=str(exc), disposition="manual_reconciliation_required",
            )
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
