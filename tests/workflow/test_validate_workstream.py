from __future__ import annotations

import importlib.util
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "validate_workstream_under_test", ROOT / "scripts" / "validate-workstream.py"
)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def test_standard_validation_record_requires_command_and_result() -> None:
    assert VALIDATOR.validation_record_is_valid(
        {"command": "pytest", "result": "passed"}
    )
    assert not VALIDATOR.validation_record_is_valid({"command": "pytest"})
    assert not VALIDATOR.validation_record_is_valid({"result": "passed"})


def test_provider_response_archive_accepts_append_only_response_evidence() -> None:
    record = {
        "at": "2026-10-12T14:14:00Z",
        "kind": "provider_response_archive",
        "provider": "tiingo",
        "request_scope": "account_usage_only",
        "provider_http_requests": 4,
        "responses": [{"status": 301}, {"status": 404}],
        "secrets_included": False,
    }
    assert VALIDATOR.validation_record_is_valid(record)

    malformed = deepcopy(record)
    malformed["responses"] = [{"body": "missing status"}]
    assert not VALIDATOR.validation_record_is_valid(malformed)

    unsafe = deepcopy(record)
    unsafe["secrets_included"] = True
    assert not VALIDATOR.validation_record_is_valid(unsafe)


def test_known_provider_checkpoint_requires_nested_test_commands_and_results() -> None:
    record = {
        "kind": "provider_archive_rights_and_validation_checkpoint",
        "checks": {
            "focused_tests": {"command": "pytest focused", "result": "passed"},
            "docker_integration": {"command": "make test-int", "result": "passed"},
            "ruff_check_and_format": "passed",
            "workstream_validation": "passed",
            "git_diff_check": "passed",
        },
    }
    assert VALIDATOR.validation_record_is_valid(record)

    record["checks"]["docker_integration"] = {"result": "passed"}
    assert not VALIDATOR.validation_record_is_valid(record)


def test_provider_contract_research_receipt_requires_source_backed_findings() -> None:
    record = {
        "at": "2026-10-08T20:31:00Z",
        "kind": "provider_contract_research",
        "provider": "marketstack",
        "result": "dashboard_usage_and_quota_conflict_confirmed",
        "sources": ["https://marketstack.com/pricing"],
        "findings": {"free_monthly_requests_conflict": [100, 1000]},
        "decision": "retain conservative 100/month contract",
        "provider_http_requests": 0,
        "source_dirty": True,
    }
    assert VALIDATOR.validation_record_is_valid(record)

    malformed = deepcopy(record)
    malformed["sources"] = []
    assert not VALIDATOR.validation_record_is_valid(malformed)

    malformed = deepcopy(record)
    malformed["provider_http_requests"] = -1
    assert not VALIDATOR.validation_record_is_valid(malformed)


def test_provider_candidate_batch_requires_consistent_partial_live_evidence() -> None:
    record = {
        "at": "2026-10-10T13:13:00Z",
        "kind": "provider_live_candidate_batch",
        "candidate_parent_sha": "a" * 40,
        "candidate_tree_sha": "b" * 40,
        "result": "partial_exact_candidate_provider_validation",
        "live_acceptance": False,
        "providers": [
            {
                "provider": "demo",
                "passed_cases": 2,
                "failed_cases": 0,
                "skipped_cases": 0,
                "requests": 3,
                "response_bytes": 40,
            }
        ],
        "total_passed_cases": 2,
        "total_http_requests": 3,
        "total_response_bytes": 40,
    }
    assert VALIDATOR.validation_record_is_valid(record)

    malformed = deepcopy(record)
    malformed["total_http_requests"] = 4
    assert not VALIDATOR.validation_record_is_valid(malformed)


def test_candidate_receipt_compatibility_checkpoint_requires_test_and_clean_checks() -> (
    None
):
    record = {
        "at": "2026-10-10T13:21:13Z",
        "kind": "provider_candidate_receipt_compatibility_fix",
        "files": ["scripts/run-live-provider-probes.py"],
        "result": "focused regression passed",
        "test": "test_candidate_receipts_survive_only_non_contract_workstream_updates",
        "passed": 1,
        "failed": 0,
        "ruff": "passed",
        "format": "passed",
        "diff_check": "passed",
        "notes": "Routine session progress timestamp is handled without relaxing contract checks.",
    }
    assert VALIDATOR.validation_record_is_valid(record)

    malformed = deepcopy(record)
    malformed["failed"] = 1
    assert not VALIDATOR.validation_record_is_valid(malformed)


def test_full_stack_browser_receipt_requires_consistent_isolated_evidence() -> None:
    record = {
        "at": "2026-10-04T17:39:38Z",
        "kind": "full_stack_browser_validation",
        "source_sha": "a" * 40,
        "candidate_status": "dirty_worktree_not_exact_candidate",
        "provider_egress": "denied",
        "provider_http_requests": 0,
        "e2e": {
            "command": "npm run test:e2e",
            "total": 6,
            "passed": 2,
            "failed": 2,
            "skipped": 2,
            "failed_cases": ["case-a", "case-b"],
        },
        "e2e_failed_case_retry": {
            "command": "npm run test:e2e -- --grep failed-cases",
            "total": 2,
            "passed": 2,
            "failed": 0,
        },
        "visual": {
            "command": "npm run test:visual:board",
            "total": 3,
            "passed": 1,
            "failed": 2,
            "max_diff_pixel_ratio": 0.01,
            "baseline_changes": 0,
        },
        "research_runner": {"sandbox": "passed", "resource_limits": "passed"},
        "compose_cleanup": {
            "project": "branch-project",
            "completed": True,
            "host_wide_prune": False,
        },
        "focused_python_tests": 10,
        "changed_python_files_ruff_check_and_format": 5,
        "workstream_records_validated": 30,
    }
    assert VALIDATOR.validation_record_is_valid(record)

    unsafe = deepcopy(record)
    unsafe["provider_http_requests"] = 1
    assert not VALIDATOR.validation_record_is_valid(unsafe)

    inconsistent = deepcopy(record)
    inconsistent["e2e"]["failed"] = 3
    assert not VALIDATOR.validation_record_is_valid(inconsistent)

    changed_baseline = deepcopy(record)
    changed_baseline["visual"]["baseline_changes"] = 1
    assert not VALIDATOR.validation_record_is_valid(changed_baseline)


def test_unrecognized_aggregate_record_shape_remains_invalid() -> None:
    assert not VALIDATOR.validation_record_is_valid(
        {"kind": "other_checkpoint", "checks": {"focused_tests": "passed"}}
    )
