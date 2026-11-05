#!/usr/bin/env python3
"""Verify exact green staging provenance for a promoted master commit."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request


def require_trusted_run(
    run: dict, jobs: list[dict], sha: str, workflow_id: int
) -> None:
    if (
        run.get("head_sha") != sha
        or run.get("head_branch") != "staging"
        or run.get("event") != "push"
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or run.get("workflow_id") != workflow_id
    ):
        raise ValueError("staging run identity or conclusion is not trusted")
    required = (
        "Changed-path validation scope",
        "Backend Tests",
        "Frontend Unit Tests",
        "E2E Tests (Playwright)",
        "Exhaustive Integration Gate",
    )
    for name in required:
        matches = [job for job in jobs if job.get("name") == name]
        if (
            len(matches) != 1
            or matches[0].get("status") != "completed"
            or matches[0].get("conclusion") != "success"
        ):
            raise ValueError(
                f"staging run lacks one completed successful required job: {name}"
            )


def api(path: str, token: str) -> dict:
    request = urllib.request.Request(
        f"https://api.github.com/{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read())


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    sha = os.environ.get("GITHUB_SHA", "")
    token = os.environ.get("GH_TOKEN", "")
    if not repository or len(sha) != 40 or not token:
        print(
            "master promotion verification needs repository, exact SHA, and token",
            file=sys.stderr,
        )
        return 2
    local = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    tree = subprocess.run(
        ["git", "rev-parse", f"{sha}^{{tree}}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    staging = subprocess.run(
        ["git", "ls-remote", "origin", "refs/heads/staging"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    master = subprocess.run(
        ["git", "ls-remote", "origin", "refs/heads/master"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    if (
        local != sha
        or len(tree) != 40
        or not staging
        or staging[0] != sha
        or not master
        or master[0] != sha
    ):
        print(
            "local and remote master/staging refs must name the exact promoted SHA",
            file=sys.stderr,
        )
        return 1
    try:
        workflow = api(f"repos/{repository}/actions/workflows/ci.yml", token)
        workflow_id = workflow.get("id")
        runs = api(
            f"repos/{repository}/actions/workflows/ci.yml/runs?branch=staging&event=push&head_sha={sha}&per_page=100",
            token,
        ).get("workflow_runs", [])
        matches = [
            run
            for run in runs
            if run.get("head_sha") == sha
            and run.get("head_branch") == "staging"
            and run.get("event") == "push"
        ]
        if len(matches) != 1:
            raise ValueError(
                "expected exactly one staging CI push run for promoted SHA"
            )
        run = matches[0]
        jobs = api(
            f"repos/{repository}/actions/runs/{run['id']}/jobs?per_page=100", token
        ).get("jobs", [])
        require_trusted_run(run, jobs, sha, workflow_id)
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, KeyError) as exc:
        print(f"staging provenance verification failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"master promotion identity/provenance/release checks passed: sha={sha} tree={tree}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
