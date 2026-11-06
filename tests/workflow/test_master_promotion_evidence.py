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
    MODULE.require_trusted_run(
        run_payload(),
        [
            {
                "name": "Changed-path validation scope",
                "status": "completed",
                "conclusion": "success",
            },
            {
                "name": "Exhaustive Integration Gate",
                "status": "completed",
                "conclusion": "success",
            },
            *[
                {"name": name, "status": "completed", "conclusion": "skipped"}
                for name in (
                    "Backend Tests",
                    "Frontend Unit Tests",
                    "E2E Tests (Playwright)",
                )
            ],
        ],
        "a" * 40,
        123,
    )


def test_master_verifier_reads_legacy_full_staging_runs():
    jobs = [
        {"name": name, "status": "completed", "conclusion": "success"}
        for name in (
            "Changed-path validation scope",
            "Backend Tests",
            "Frontend Unit Tests",
            "E2E Tests (Playwright)",
            "Exhaustive Integration Gate",
        )
    ]
    MODULE.require_trusted_run(run_payload(), jobs, "a" * 40, 123)


def test_master_verifier_reads_legacy_four_job_staging_run_without_changed_scope():
    jobs = [
        {"name": name, "status": "completed", "conclusion": "success"}
        for name in (
            "Backend Tests",
            "Frontend Unit Tests",
            "E2E Tests (Playwright)",
            "Exhaustive Integration Gate",
        )
    ]
    MODULE.require_trusted_run(run_payload(), jobs, "a" * 40, 123)


@pytest.mark.parametrize("bad_product", ["failure", "success"])
def test_master_verifier_rejects_mixed_or_failed_single_gate_evidence(bad_product):
    jobs = [
        {
            "name": "Changed-path validation scope",
            "status": "completed",
            "conclusion": "success",
        },
        {
            "name": "Exhaustive Integration Gate",
            "status": "completed",
            "conclusion": "success",
        },
        {"name": "Backend Tests", "status": "completed", "conclusion": "skipped"},
        {
            "name": "Frontend Unit Tests",
            "status": "completed",
            "conclusion": bad_product,
        },
        {
            "name": "E2E Tests (Playwright)",
            "status": "completed",
            "conclusion": "skipped",
        },
    ]
    with pytest.raises(ValueError, match="supported full-gate profile"):
        MODULE.require_trusted_run(run_payload(), jobs, "a" * 40, 123)


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


def test_staging_runs_only_the_authoritative_single_full_gate():
    import yaml

    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    jobs = workflow["jobs"]
    for job_id in ("backend", "frontend-unit", "e2e"):
        condition = jobs[job_id]["if"]
        assert "github.ref != 'refs/heads/staging'" in condition
        assert "needs.changed-scope.outputs.scope == 'broad'" in condition
        assert "github.ref != 'refs/heads/master'" in condition
    assert jobs["platform-gate"]["needs"] == ["changed-scope"]
    assert "refs/heads/staging" in jobs["platform-gate"]["if"]
    assert any(
        step.get("run") == "make validate-integration"
        for step in jobs["platform-gate"]["steps"]
    )

    makefile = (ROOT / "Makefile").read_text()
    target = makefile.split("validate-integration:", 1)[1].split(
        "validate-focused-integration:", 1
    )[0]
    phases = (
        "workstream",
        "backend-dependencies",
        "migration-head",
        "migration-compatibility",
        "frontend-dependencies",
        "lint",
        "backend-coverage",
        "frontend-tests",
        "frontend-build",
        "compose-contract",
        "provider-probes",
        "stack-up",
        "research-runner-probes",
        "e2e-functional",
        "e2e-visual",
    )
    assert all(target.count(f"stage={phase};") == 1 for phase in phases)
    assert "RUN_BOARD_VISUAL_PARITY=1" in target
    assert "tc2000_visual.spec.ts --retries=0" in target
    assert target.count("$(MAKE) test-e2e") == 1
    functional = makefile.split("test-e2e:\n", 1)[1].split("test-e2e-headed:", 1)[0]
    assert "npx playwright test --retries=0" in functional
    assert target.count("test-backend-coverage") == 1
    assert target.count("$(MAKE) test-fe") == 1


def test_e2e_job_is_independent_and_builds_its_own_stack():
    import yaml

    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    e2e = workflow["jobs"]["e2e"]
    assert e2e["needs"] == ["changed-scope"]
    assert "github.ref != 'refs/heads/master'" in e2e["if"]
    assert "github.ref != 'refs/heads/staging'" in e2e["if"]
    assert "needs.changed-scope.outputs.scope == 'broad'" in e2e["if"]
    names = [step.get("name") for step in e2e["steps"]]
    assert "Install frontend deps" in names
    assert "Install Playwright browsers" in names
    assert "Build stack images" in names
    assert "Start stack" in names
    assert "Run Playwright tests" in names
    teardown = next(step for step in e2e["steps"] if step.get("name") == "Tear down")
    assert teardown["if"] == "always()"


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
            "validation_profile": "full_staging_single_gate_v1",
            "verified_required_jobs": [
                "Changed-path validation scope",
                "Exhaustive Integration Gate",
            ],
            "unexecuted_product_jobs": [
                "Backend Tests",
                "Frontend Unit Tests",
                "E2E Tests (Playwright)",
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
    missing_skip_record = {**receipt, "staging_ci": dict(receipt["staging_ci"])}
    missing_skip_record["staging_ci"].pop("unexecuted_product_jobs")
    assert not rpi.receipt_has_ci_qualification(missing_skip_record, sha)
    false_pass_record = {**receipt, "staging_ci": dict(receipt["staging_ci"])}
    false_pass_record["staging_ci"]["unexecuted_product_jobs"] = []
    assert not rpi.receipt_has_ci_qualification(false_pass_record, sha)
    legacy_receipt = {
        **receipt,
        "staging_ci": {
            **receipt["staging_ci"],
            "verified_required_jobs": [
                "Changed-path validation scope",
                "Backend Tests",
                "Frontend Unit Tests",
                "E2E Tests (Playwright)",
                "Exhaustive Integration Gate",
            ],
        },
    }
    legacy_receipt["staging_ci"].pop("validation_profile")
    assert rpi.receipt_has_ci_qualification(legacy_receipt, sha)
    explicit_legacy_receipt = {
        **legacy_receipt,
        "staging_ci": {
            **legacy_receipt["staging_ci"],
            "validation_profile": "full_staging_integration",
        },
    }
    assert rpi.receipt_has_ci_qualification(explicit_legacy_receipt, sha)
    explicit_legacy_four_job_receipt = {
        **explicit_legacy_receipt,
        "staging_ci": {
            **explicit_legacy_receipt["staging_ci"],
            "verified_required_jobs": [
                "Backend Tests",
                "Frontend Unit Tests",
                "E2E Tests (Playwright)",
                "Exhaustive Integration Gate",
            ],
        },
    }
    assert rpi.receipt_has_ci_qualification(explicit_legacy_four_job_receipt, sha)
    unversioned_new_job_list = {**receipt, "staging_ci": dict(receipt["staging_ci"])}
    unversioned_new_job_list["staging_ci"].pop("validation_profile")
    assert not rpi.receipt_has_ci_qualification(unversioned_new_job_list, sha)
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
    receipt["staging_ci"]["verified_required_jobs"].remove(
        "Exhaustive Integration Gate"
    )
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
    with pytest.raises(ValueError, match="lacks exactly one completed success job"):
        MODULE.require_trusted_run(run_payload(), jobs, "a" * 40, 123)
