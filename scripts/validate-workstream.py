#!/usr/bin/env python3
"""Validate branch-local workstream records through the repository runtime."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from validation_profile import profile_is_sufficient

REQUIRED_V1 = {
    "schema",
    "branch",
    "base_sha",
    "goal",
    "scope",
    "owned_paths",
    "dependencies",
    "acceptance_criteria",
    "branch_tests",
    "live_test_impact",
    "migration_impact",
    "deployment_impact",
    "status",
    "remaining_gaps",
}
REQUIRED_V2 = REQUIRED_V1 | {
    "human_intent_authorization",
    "human_closure_authorization",
    "closure_summary",
    "validation_tier",
    "human_validation_authorization",
}
REQUIRED_V3 = REQUIRED_V2 | {"goal_budget_policy", "human_goal_budget_authorization"}
REQUIRED_V4 = REQUIRED_V3 | {
    "parent_branch",
    "parent_sha",
    "planning_state",
    "local_validation_profile",
    "local_validation_reason",
    "branch_tests_reason",
    "progress",
}
STATUSES = {
    "planned",
    "authorized",
    "in_progress",
    "ready",
    "ready_for_human_review",
    "ready_for_integration",
    "integrated",
    "closed",
    "superseded",
    "blocked",
}


def parse_plan(path: Path) -> dict[str, Any]:
    try:
        values = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ValueError(str(exc)) from exc
    if not isinstance(values, dict):
        raise ValueError("top-level document must be a mapping")
    return values


def is_nonempty_sequence(value: Any) -> bool:
    return isinstance(value, list) and bool(value)


def validation_record_is_valid(item: Any) -> bool:
    """Accept standard receipts and the supported structured aggregate forms.

    Provider and browser checkpoints store detailed outcomes in domain-shaped
    fields rather than top-level command/result. Keep the validation ledger
    append-only while validating those exact schemas; all ordinary records
    still require top-level command/result.
    """

    if not isinstance(item, dict):
        return False
    if item.get("command") and item.get("result"):
        return True
    if item.get("kind") == "provider_response_archive":
        responses = item.get("responses")
        return (
            bool(item.get("at"))
            and bool(item.get("provider"))
            and bool(item.get("request_scope"))
            and isinstance(item.get("provider_http_requests"), int)
            and item["provider_http_requests"] >= 0
            and isinstance(responses, list)
            and bool(responses)
            and all(
                isinstance(response, dict)
                and isinstance(response.get("status"), int)
                for response in responses
            )
            and item.get("secrets_included") is False
        )
    if item.get("kind") == "provider_contract_research":
        return (
            bool(item.get("at"))
            and bool(item.get("provider"))
            and bool(item.get("result"))
            and is_nonempty_sequence(item.get("sources"))
            and isinstance(item.get("findings"), dict)
            and bool(item.get("decision"))
            and isinstance(item.get("provider_http_requests"), int)
            and item["provider_http_requests"] >= 0
            and isinstance(item.get("source_dirty"), bool)
        )
    if item.get("kind") == "provider_archive_rights_and_validation_checkpoint":
        checks = item.get("checks")
        if not isinstance(checks, dict) or not checks:
            return False
        for name in ("focused_tests", "docker_integration"):
            detail = checks.get(name)
            if (
                not isinstance(detail, dict)
                or not detail.get("command")
                or not detail.get("result")
            ):
                return False
        return all(
            isinstance(value, str) and bool(value.strip())
            for name, value in checks.items()
            if name not in {"focused_tests", "docker_integration"}
        )
    if item.get("kind") == "provider_live_candidate_batch":
        providers = item.get("providers")
        if (
            not item.get("at")
            or not re.fullmatch(
                r"[0-9a-f]{40}", str(item.get("candidate_parent_sha", ""))
            )
            or not re.fullmatch(
                r"[0-9a-f]{40}", str(item.get("candidate_tree_sha", ""))
            )
            or not isinstance(providers, list)
            or not providers
        ):
            return False
        counts = {
            "passed_cases": 0,
            "failed_cases": 0,
            "skipped_cases": 0,
            "requests": 0,
            "response_bytes": 0,
        }
        for provider in providers:
            if not isinstance(provider, dict) or not isinstance(
                provider.get("provider"), str
            ):
                return False
            for field in counts:
                value = provider.get(field)
                if not isinstance(value, int) or value < 0:
                    return False
                counts[field] += value
        return (
            item.get("result") == "partial_exact_candidate_provider_validation"
            and item.get("live_acceptance") is False
            and item.get("total_passed_cases") == counts["passed_cases"]
            and counts["failed_cases"] == 0
            and counts["skipped_cases"] == 0
            and item.get("total_http_requests") == counts["requests"]
            and item.get("total_response_bytes") == counts["response_bytes"]
        )
    if item.get("kind") == "provider_candidate_receipt_compatibility_fix":
        return (
            bool(item.get("at"))
            and item.get("result") == "focused regression passed"
            and item.get("test")
            == "test_candidate_receipts_survive_only_non_contract_workstream_updates"
            and isinstance(item.get("files"), list)
            and all(isinstance(path, str) and path for path in item["files"])
            and item.get("passed") == 1
            and item.get("failed") == 0
            and item.get("ruff") == "passed"
            and item.get("format") == "passed"
            and item.get("diff_check") == "passed"
            and isinstance(item.get("notes"), str)
            and bool(item["notes"].strip())
        )
    if item.get("kind") != "full_stack_browser_validation":
        return False

    e2e = item.get("e2e")
    retry = item.get("e2e_failed_case_retry")
    visual = item.get("visual")
    runner = item.get("research_runner")
    cleanup = item.get("compose_cleanup")
    if (
        not item.get("at")
        or not isinstance(item.get("source_sha"), str)
        or len(item["source_sha"]) != 40
        or item.get("candidate_status") != "dirty_worktree_not_exact_candidate"
        or item.get("provider_egress") != "denied"
        or item.get("provider_http_requests") != 0
        or not isinstance(e2e, dict)
        or not e2e.get("command")
        or not isinstance(retry, dict)
        or not retry.get("command")
        or not isinstance(visual, dict)
        or not visual.get("command")
        or not isinstance(runner, dict)
        or runner.get("sandbox") != "passed"
        or runner.get("resource_limits") != "passed"
        or not isinstance(cleanup, dict)
        or cleanup.get("completed") is not True
        or cleanup.get("host_wide_prune") is not False
    ):
        return False

    e2e_counts = tuple(e2e.get(key) for key in ("total", "passed", "failed", "skipped"))
    retry_counts = tuple(retry.get(key) for key in ("total", "passed", "failed"))
    visual_counts = tuple(visual.get(key) for key in ("total", "passed", "failed"))
    counts = (*e2e_counts, *retry_counts, *visual_counts)
    if not all(isinstance(value, int) and value >= 0 for value in counts):
        return False
    if (
        e2e_counts[0] != sum(e2e_counts[1:])
        or retry_counts[0] != retry_counts[1] + retry_counts[2]
        or retry_counts[2] != 0
        or visual_counts[0] != visual_counts[1] + visual_counts[2]
        or not isinstance(e2e.get("failed_cases"), list)
        or len(e2e["failed_cases"]) != e2e_counts[2]
        or visual.get("baseline_changes") != 0
        or not isinstance(visual.get("max_diff_pixel_ratio"), float | int)
        or not all(
            isinstance(item.get(key), int) and item[key] > 0
            for key in (
                "focused_python_tests",
                "changed_python_files_ruff_check_and_format",
                "workstream_records_validated",
            )
        )
    ):
        return False
    return True


def validate_v4(values: dict[str, Any], plan_path: Path, errors: list[str]) -> None:
    planning_state = values.get("planning_state")
    if planning_state not in {"draft", "ready"}:
        errors.append(f"{plan_path}: planning_state must be draft or ready")
        return
    profile = values.get("local_validation_profile")
    if profile not in {
        "none",
        "unit",
        "docker_integration",
        "full_stack_browser",
        "pending_agent_assessment",
    }:
        errors.append(f"{plan_path}: unsupported local_validation_profile {profile!r}")
    elif not profile_is_sufficient(str(profile), values):
        errors.append(
            f"{plan_path}: local_validation_profile {profile!r} is weaker than the "
            "minimum implied by the declared paths/impacts; record a human-authorized "
            "remote-only exception to weaken it"
        )
    progress = values.get("progress")
    if not isinstance(progress, dict):
        errors.append(f"{plan_path}: progress must be a mapping")
    elif not isinstance(progress.get("completed", []), list) or not isinstance(
        progress.get("total", 0), int
    ):
        errors.append(
            f"{plan_path}: progress.completed must be a list and progress.total an integer"
        )
    elif progress.get("total") != len(values.get("acceptance_criteria") or []):
        errors.append(
            f"{plan_path}: progress.total must equal acceptance_criteria count"
        )
    if planning_state != "ready":
        return
    for key in ("scope", "owned_paths", "acceptance_criteria"):
        if not is_nonempty_sequence(values.get(key)):
            errors.append(f"{plan_path}: ready workstreams require non-empty {key}")
    branch_tests = values.get("branch_tests")
    if (
        not is_nonempty_sequence(branch_tests)
        and not str(values.get("branch_tests_reason", "")).strip()
    ):
        errors.append(
            f"{plan_path}: ready workstreams need branch_tests or branch_tests_reason"
        )
    criteria = values.get("acceptance_criteria") or []
    ids: set[str] = set()
    for index, criterion in enumerate(criteria, 1):
        if (
            not isinstance(criterion, dict)
            or not str(criterion.get("id", "")).strip()
            or not str(criterion.get("text", "")).strip()
        ):
            errors.append(
                f"{plan_path}: acceptance_criteria[{index}] needs id and text"
            )
            continue
        criterion_id = str(criterion["id"])
        if criterion_id in ids:
            errors.append(
                f"{plan_path}: duplicate acceptance criterion id {criterion_id!r}"
            )
        ids.add(criterion_id)
    if profile == "pending_agent_assessment":
        errors.append(
            f"{plan_path}: ready workstreams must select a local validation profile"
        )


def main() -> int:
    directory = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("ops/workstreams")
    if directory.is_file():
        directories = [directory]
    elif (directory / "plan.yaml").exists():
        directories = [directory / "plan.yaml"]
    else:
        directories = sorted(directory.glob("*/plan.yaml"))
    if not directories:
        print(f"no workstream plan found under {directory}", file=sys.stderr)
        return 1
    errors: list[str] = []
    for plan_path in directories:
        stream = plan_path.parent
        try:
            values = parse_plan(plan_path)
        except ValueError as exc:
            errors.append(f"{plan_path}: invalid YAML: {exc}")
            continue
        schema = str(values.get("schema", ""))
        required = (
            REQUIRED_V4
            if schema == "4"
            else REQUIRED_V3
            if schema == "3"
            else REQUIRED_V2
            if schema == "2"
            else REQUIRED_V1
        )
        missing = sorted(required - values.keys())
        if missing:
            errors.append(f"{plan_path}: missing keys: {', '.join(missing)}")
        if schema not in {"1", "2", "3", "4"}:
            errors.append(f"{plan_path}: schema must be 1, 2, 3, or 4")
        if values.get("status") not in STATUSES:
            errors.append(f"{plan_path}: unsupported status {values.get('status')!r}")
        if schema in {"2", "3"} and not values.get("human_intent_authorization"):
            errors.append(f"{plan_path}: human_intent_authorization must not be empty")
        if schema in {"2", "3", "4"} and values.get("validation_tier") not in {
            "pending_human_decision",
            "full_integration",
            "focused_only",
        }:
            errors.append(
                f"{plan_path}: unsupported validation_tier {values.get('validation_tier')!r}"
            )
        import re

        if not re.fullmatch(r"[0-9a-f]{40}", str(values.get("base_sha", ""))):
            errors.append(f"{plan_path}: base_sha must be a full lowercase Git SHA")
        if (
            values.get("branch")
            and stream.name
            != re.sub(r"[^a-zA-Z0-9]+", "-", str(values["branch"])).strip("-").lower()
        ):
            errors.append(f"{plan_path}: directory does not match the branch slug")
        for file_name in ("handoff.md", "validation.jsonl"):
            if not (stream / file_name).exists():
                errors.append(f"{stream}: missing {file_name}")
        if schema in {"3", "4"} and not (stream / "session.json").exists():
            errors.append(f"{stream}: missing session.json")
        if schema == "4":
            validate_v4(values, plan_path, errors)
        validation = stream / "validation.jsonl"
        if validation.exists():
            for number, line in enumerate(validation.read_text().splitlines(), 1):
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append(f"{validation}:{number}: invalid JSON: {exc}")
                    continue
                if not validation_record_is_valid(item):
                    errors.append(
                        f"{validation}:{number}: entries need command and result"
                    )
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"validated {len(directories)} workstream record(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
