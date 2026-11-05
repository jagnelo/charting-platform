from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "prior_qualification", ROOT / "scripts" / "verify-prior-qualification.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def full_jobs(*, staging: bool):
    names = ["Backend Tests", "Frontend Unit Tests", "E2E Tests (Playwright)"]
    names.append("Exhaustive Integration Gate" if staging else "Branch-declared Tests")
    return [
        {"name": name, "status": "completed", "conclusion": "success"} for name in names
    ]


def test_exact_staging_or_feature_full_job_set_qualifies():
    sha = "a" * 40
    staging = {
        "head_sha": sha,
        "head_branch": "staging",
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "workflow_id": 1,
    }
    feature = staging | {"head_branch": "fix/example"}
    assert MODULE.qualifies(staging, full_jobs(staging=True), sha, 1)
    assert MODULE.qualifies(feature, full_jobs(staging=False), sha, 1)


def test_wrong_sha_event_job_or_skipped_suite_cannot_qualify():
    sha = "a" * 40
    run = {
        "head_sha": sha,
        "head_branch": "staging",
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "workflow_id": 1,
    }
    assert not MODULE.qualifies(
        run | {"head_sha": "b" * 40}, full_jobs(staging=True), sha, 1
    )
    assert not MODULE.qualifies(
        run | {"event": "pull_request"}, full_jobs(staging=True), sha, 1
    )
    assert not MODULE.qualifies(run, full_jobs(staging=True)[:-1], sha, 1)
    jobs = full_jobs(staging=True)
    jobs[0]["conclusion"] = "skipped"
    assert not MODULE.qualifies(run, jobs, sha, 1)
