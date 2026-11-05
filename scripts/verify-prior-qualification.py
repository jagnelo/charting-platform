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
SINGLE_GATE_PROFILE = "full_staging_single_gate_v1"
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
    if run.get("head_branch") == "staging":
        required = PRODUCT_JOBS | {STAGING_JOB}
        matches_by_name = {
            name: [job for job in jobs if job.get("name") == name] for name in required
        }
        if any(len(matches_by_name[name]) != 1 for name in required):
            return False
        if any(
            matches_by_name[name][0].get("status") != "completed"
            or matches_by_name[name][0].get("conclusion") != "success"
            for name in (STAGING_JOB,)
        ):
            return False
        changed_scope = [
            job for job in jobs if job.get("name") == "Changed-path validation scope"
        ]
        if len(changed_scope) > 1 or (
            changed_scope
            and (
                changed_scope[0].get("status") != "completed"
                or changed_scope[0].get("conclusion") != "success"
            )
        ):
            return False
        product_results = [matches_by_name[name][0] for name in PRODUCT_JOBS]
        legacy_full = all(
            job.get("status") == "completed" and job.get("conclusion") == "success"
            for job in product_results
        )
        single_gate_full = bool(changed_scope) and all(
            job.get("status") == "completed" and job.get("conclusion") == "skipped"
            for job in product_results
        )
        return legacy_full or single_gate_full
    if run.get("head_branch") == "master":
        # Old master full-replay runs did not include changed-scope and
        # Branch-declared was skipped by the master workflow. Require the actual
        # product matrix and exhaustive gate; provenance-only master runs fail.
        required = PRODUCT_JOBS | {STAGING_JOB}
        for name in required:
            matches = [job for job in jobs if job.get("name") == name]
            if (
                len(matches) != 1
                or matches[0].get("status") != "completed"
                or matches[0].get("conclusion") != "success"
            ):
                return False
        changed_scope = [
            job for job in jobs if job.get("name") == "Changed-path validation scope"
        ]
        if len(changed_scope) > 1 or (
            changed_scope
            and (
                changed_scope[0].get("status") != "completed"
                or changed_scope[0].get("conclusion") != "success"
            )
        ):
            return False
        return True
    required = PRODUCT_JOBS | {BRANCH_JOB}
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
