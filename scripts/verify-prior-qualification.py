#!/usr/bin/env python3
"""Check whether an exact parent SHA has full product CI qualification."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request

PRODUCT_JOBS = {
    "Backend Tests",
    "Frontend Unit Tests",
    "E2E Tests (Playwright)",
}
STAGING_JOB = "Exhaustive Integration Gate"
BRANCH_JOB = "Branch-declared Tests"


def qualifies(run: dict, jobs: list[dict], sha: str, workflow_id: int) -> bool:
    if (
        run.get("head_sha") != sha
        or run.get("event") != "push"
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or run.get("workflow_id") != workflow_id
        or run.get("head_branch") not in {"staging", "master"}
        and not str(run.get("head_branch", "")).startswith(
            ("feat/", "fix/", "chore/", "docs/", "test/")
        )
    ):
        return False
    required = PRODUCT_JOBS | (
        {STAGING_JOB}
        if run.get("head_branch") in {"staging", "master"}
        else {BRANCH_JOB}
    )
    for name in required:
        matches = [job for job in jobs if job.get("name") == name]
        if (
            len(matches) != 1
            or matches[0].get("status") != "completed"
            or matches[0].get("conclusion") != "success"
        ):
            return False
    return True


def api(repository: str, token: str, endpoint: str) -> dict:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/{endpoint}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GH_TOKEN", "")
    if len(args.sha) != 40 or not repository or not token:
        print("prior qualification unavailable; broad validation required")
        return 1
    try:
        workflow = api(repository, token, "actions/workflows/ci.yml")
        workflow_id = workflow.get("id")
        query = urllib.parse.urlencode(
            {"event": "push", "head_sha": args.sha, "per_page": 100}
        )
        runs = api(repository, token, f"actions/workflows/ci.yml/runs?{query}").get(
            "workflow_runs", []
        )
        for run in runs:
            if run.get("head_sha") != args.sha or run.get("event") != "push":
                continue
            jobs = api(
                repository, token, f"actions/runs/{run['id']}/jobs?per_page=100"
            ).get("jobs", [])
            if qualifies(run, jobs, args.sha, workflow_id):
                print(f"exact prior full product qualification verified for {args.sha}")
                return 0
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        ValueError,
        KeyError,
        TypeError,
    ) as exc:
        print(f"prior qualification unavailable ({exc}); broad validation required")
        return 1
    print(f"no successful full product qualification found for exact parent {args.sha}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
