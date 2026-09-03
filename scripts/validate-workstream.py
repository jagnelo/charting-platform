#!/usr/bin/env python3
"""Validate branch-local workstream records through the repository runtime."""

from __future__ import annotations

import json
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
                if (
                    not isinstance(item, dict)
                    or not item.get("command")
                    or not item.get("result")
                ):
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
