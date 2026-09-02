#!/usr/bin/env python3
"""Retry one completed CI run only when its failure is classified as transient infrastructure."""

from __future__ import annotations

import json
import io
import os
import re
import subprocess
import zipfile
from pathlib import Path
from typing import Any


SETUP_STEPS = {
    "Install dependencies",
    "Install frontend deps",
    "Install Playwright browsers",
    "Install frontend dependencies and browsers",
    "Install locked dependencies",
}
SUPPORTED_BRANCH = re.compile(r"^(master|staging|(feat|fix|chore|docs|test)/.+)$")
TRANSIENT_PATTERNS = (
    re.compile(
        r"(could not resolve host|name or service not known|temporary failure in name resolution)",
        re.I,
    ),
    re.compile(
        r"(connection reset|connection aborted|connection timed out|read timed out|network is unreachable)",
        re.I,
    ),
    re.compile(r"(http|status|response)[ =:]+(?:403|408|429|500|502|503|504)\b", re.I),
    re.compile(
        r"(apt|npm|pypi|pythonhosted|playwright|github).*\b(?:403|429|5\d\d)\b", re.I
    ),
    re.compile(
        r"(runner.*lost|lost communication with the server|unexpected runner termination)",
        re.I,
    ),
)


def gh(*args: str) -> Any:
    result = subprocess.run(["gh", "api", *args], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "GitHub API request failed")
    if not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return result.stdout


def gh_job_logs(repository: str, job_id: str) -> str:
    """Read the GitHub job log archive without assuming it is plain text."""
    result = subprocess.run(
        ["gh", "api", f"repos/{repository}/actions/jobs/{job_id}/logs"],
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(
            result.stderr.decode(errors="replace").strip()
            or "GitHub job log request failed"
        )
    payload = result.stdout
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            return "\n".join(
                archive.read(name).decode(errors="replace")
                for name in archive.namelist()
            )
    except zipfile.BadZipFile:
        return payload.decode(errors="replace")


def classify_step_failure(step_name: str, log: str) -> str | None:
    if step_name not in SETUP_STEPS:
        return None
    if any(pattern.search(log) for pattern in TRANSIENT_PATTERNS):
        if re.search(r"\b403\b", log) and re.search(
            r"microsoft|packages\.microsoft|apt", log, re.I
        ):
            return "dependency-host-http-403"
        if re.search(r"\b(?:429|5\d\d)\b", log):
            return "dependency-host-rate-or-upstream"
        if re.search(r"(?:resolve host|dns|connection|timed out)", log, re.I):
            return "dependency-transport"
        return "runner-or-setup-infrastructure"
    return None


def failed_jobs(repository: str, run_id: str) -> list[dict[str, Any]]:
    payload = gh(f"repos/{repository}/actions/runs/{run_id}/jobs?per_page=100")
    return [
        job for job in payload.get("jobs", []) if job.get("conclusion") == "failure"
    ]


def evaluate(
    repository: str, run_id: str, run_attempt: int, event: str, branch: str
) -> dict[str, Any]:
    decision: dict[str, Any] = {
        "repository": repository,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "event": event,
        "branch": branch,
        "action": "skip",
        "classifications": [],
    }
    if event != "push":
        decision["reason"] = "only push runs are eligible"
        return decision
    if not SUPPORTED_BRANCH.fullmatch(branch):
        decision["reason"] = "branch is outside the supported workflow namespace"
        return decision
    if run_attempt != 1:
        decision["reason"] = "the bounded retry has already been consumed"
        return decision
    eligible: list[dict[str, Any]] = []
    for job in failed_jobs(repository, run_id):
        log_text = gh_job_logs(repository, str(job["id"]))
        for step in job.get("steps", []):
            if step.get("conclusion") != "failure":
                continue
            classification = classify_step_failure(str(step.get("name", "")), log_text)
            if classification:
                item = {
                    "job": job.get("name"),
                    "job_id": job.get("id"),
                    "step": step.get("name"),
                    "classification": classification,
                }
                decision["classifications"].append(item)
                eligible.append(item)
    if not eligible:
        decision["reason"] = "no allowlisted transient setup failure"
        return decision
    gh(
        "repos/{}/actions/runs/{}/rerun-failed-jobs".format(repository, run_id),
        "--method",
        "POST",
    )
    decision["action"] = "rerun-failed-jobs"
    decision["reason"] = "allowlisted transient setup failure"
    return decision


def main() -> int:
    repository = os.environ["GITHUB_REPOSITORY"]
    run_id = os.environ["GITHUB_RUN_ID"]
    run_attempt = int(os.environ.get("GITHUB_RUN_ATTEMPT", "1"))
    event = os.environ.get("CI_RETRY_EVENT", "push")
    branch = os.environ.get("CI_RETRY_BRANCH", "")
    try:
        decision = evaluate(repository, run_id, run_attempt, event, branch)
    except (KeyError, RuntimeError, ValueError) as exc:
        decision = {
            "repository": repository,
            "run_id": run_id,
            "run_attempt": run_attempt,
            "action": "error",
            "reason": str(exc),
        }
    Path("ci-retry-decision.json").write_text(json.dumps(decision, indent=2) + "\n")
    print(json.dumps(decision, indent=2))
    return 0 if decision["action"] in {"skip", "rerun-failed-jobs"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
