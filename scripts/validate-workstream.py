#!/usr/bin/env python3
"""Validate one branch-local workstream record without external dependencies."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


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


def parse_keys(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):(?:\s*)(.*)$", line)
        if match:
            values[match.group(1)] = match.group(2).strip().strip("'\"")
    return values


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
        values = parse_keys(plan_path)
        schema = values.get("schema")
        required = (
            REQUIRED_V3
            if schema == "3"
            else REQUIRED_V2
            if schema == "2"
            else REQUIRED_V1
        )
        missing = sorted(required - values.keys())
        if missing:
            errors.append(f"{plan_path}: missing keys: {', '.join(missing)}")
        if schema not in {"1", "2", "3"}:
            errors.append(f"{plan_path}: schema must be 1, 2, or 3")
        if values.get("status") not in STATUSES:
            errors.append(f"{plan_path}: unsupported status {values.get('status')!r}")
        if schema in {"2", "3"} and not values.get("human_intent_authorization"):
            errors.append(f"{plan_path}: human_intent_authorization must not be empty")
        if schema in {"2", "3"} and values.get("validation_tier") not in {
            "pending_human_decision",
            "full_integration",
            "focused_only",
        }:
            errors.append(
                f"{plan_path}: unsupported validation_tier {values.get('validation_tier')!r}"
            )
        if not re.fullmatch(r"[0-9a-f]{40}", values.get("base_sha", "")):
            errors.append(f"{plan_path}: base_sha must be a full lowercase Git SHA")
        if (
            values.get("branch")
            and stream.name
            != re.sub(r"[^a-zA-Z0-9]+", "-", values["branch"]).strip("-").lower()
        ):
            errors.append(f"{plan_path}: directory does not match the branch slug")
        for file_name in ("handoff.md", "validation.jsonl"):
            if not (stream / file_name).exists():
                errors.append(f"{stream}: missing {file_name}")
        if schema == "3" and not (stream / "session.json").exists():
            errors.append(f"{stream}: missing session.json")
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
