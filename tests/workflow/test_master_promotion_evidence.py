from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "master_promotion", ROOT / "scripts" / "verify-master-promotion.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def run_payload(**updates):
    value = {
        "head_sha": "a" * 40,
        "head_branch": "staging",
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "workflow_id": 123,
    }
    return value | updates


def test_only_exact_trusted_green_staging_gate_is_accepted():
    required = [
        "Changed-path validation scope",
        "Backend Tests",
        "Frontend Unit Tests",
        "E2E Tests (Playwright)",
        "Exhaustive Integration Gate",
    ]
    MODULE.require_trusted_run(
        run_payload(),
        [
            {"name": name, "status": "completed", "conclusion": "success"}
            for name in required
        ],
        "a" * 40,
        123,
    )


def test_workflow_display_names_are_unique_and_master_has_only_release_provenance():
    import yaml

    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    display_names = [
        job.get("name", job_id) for job_id, job in workflow["jobs"].items()
    ]
    assert len(display_names) == len(set(display_names))
    assert workflow["jobs"]["platform-gate"]["if"].endswith("refs/heads/staging'")
    assert workflow["jobs"]["master-release"]["name"] == "Master Release Provenance"
    assert workflow["jobs"]["master-release"]["permissions"]["actions"] == "read"
    assert "master-gate-compatibility" not in workflow["jobs"]


def test_deployment_guard_accepts_legacy_or_explicit_reuse_receipts():
    spec = importlib.util.spec_from_file_location(
        "rpi_receipt", ROOT / "scripts" / "rpi.py"
    )
    assert spec and spec.loader
    rpi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rpi)
    sha = "a" * 40
    assert rpi.receipt_has_ci_qualification({"github_replay": "pass"}, sha)
    receipt = {
        "receipt_schema": 2,
        "validation_mode": "same_sha_staging_evidence_reuse",
        "staging_ci": {
            "sha": sha,
            "workflow_path": ".github/workflows/ci.yml",
            "event": "push",
            "run_id": 123,
            "required_job": "Exhaustive Integration Gate",
            "verified_required_jobs": [
                "Changed-path validation scope",
                "Backend Tests",
                "Frontend Unit Tests",
                "E2E Tests (Playwright)",
                "Exhaustive Integration Gate",
            ],
            "conclusion": "success",
        },
        "master_release_ci": {
            "sha": sha,
            "workflow_path": ".github/workflows/ci.yml",
            "event": "push",
            "run_id": 456,
            "required_job": "Master Release Provenance",
            "verified_required_jobs": ["Master Release Provenance"],
            "conclusion": "success",
        },
        "master_product_suite_replay": "not_run; exact staging product qualification reused",
    }
    assert rpi.receipt_has_ci_qualification(receipt, sha)
    old_schema2_receipt = {
        **receipt,
        "master_release_ci": {
            **receipt["master_release_ci"],
            "verified_required_jobs": [
                "Master Release Provenance",
                "Exhaustive Integration Gate",
            ],
        },
    }
    assert rpi.receipt_has_ci_qualification(old_schema2_receipt, sha)
    receipt["staging_ci"]["verified_required_jobs"].remove("E2E Tests (Playwright)")
    assert not rpi.receipt_has_ci_qualification(receipt, sha)
    assert not rpi.receipt_has_ci_qualification(
        {**receipt, "validation_mode": "replay"}, sha
    )
    receipt["staging_ci"].pop("run_id")
    assert not rpi.receipt_has_ci_qualification(receipt, sha)


@pytest.mark.parametrize(
    "updates",
    [
        {"head_sha": "b" * 40},
        {"head_branch": "master"},
        {"event": "pull_request"},
        {"conclusion": "failure"},
        {"workflow_id": 456},
    ],
)
def test_untrusted_run_identity_or_outcome_fails_closed(updates):
    with pytest.raises(ValueError, match="not trusted"):
        MODULE.require_trusted_run(run_payload(**updates), [], "a" * 40, 123)


@pytest.mark.parametrize(
    "jobs", [[], [{"name": "Exhaustive Integration Gate", "conclusion": "skipped"}]]
)
def test_missing_or_skipped_exhaustive_job_is_not_relabelled_green(jobs):
    required = [
        "Changed-path validation scope",
        "Backend Tests",
        "Frontend Unit Tests",
        "E2E Tests (Playwright)",
        "Exhaustive Integration Gate",
    ]
    jobs = [
        {"name": name, "status": "completed", "conclusion": "success"}
        for name in required
        if name != "Exhaustive Integration Gate"
    ] + jobs
    with pytest.raises(ValueError, match="lacks one completed successful"):
        MODULE.require_trusted_run(run_payload(), jobs, "a" * 40, 123)
