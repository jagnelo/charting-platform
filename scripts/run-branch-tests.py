#!/usr/bin/env python3
"""Run the executable checks declared by one branch-local workstream."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def slug(branch: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", branch).strip("-").lower()


def declared_tests(plan: Path) -> list[str]:
    """Read the plan's human-readable test declarations without executing them."""
    descriptions: list[str] = []
    in_tests = False
    for raw_line in plan.read_text().splitlines():
        line = raw_line.rstrip()
        if re.match(r"^branch_tests:\s*$", line):
            in_tests = True
            continue
        if in_tests and line and not line.startswith(" "):
            break
        if not in_tests:
            continue
        match = re.match(r'^\s*-\s*(?:"(.*)"|\'(.*)\'|(.*))\s*$', line)
        if match:
            description = next(value for value in match.groups() if value is not None)
            if description.strip():
                descriptions.append(description.strip())
    return descriptions


def _validate_entries(
    entries: Any,
    *,
    label: str,
    description_count: int,
    command_field: str | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        raise ValueError(f"{label} must be a list")
    validated: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            raise ValueError(f"{label}[{index}] must be an object")
        entry_id = entry.get("id")
        covers = entry.get("covers")
        if not isinstance(entry_id, str) or not entry_id.strip():
            raise ValueError(f"{label}[{index}] needs a non-empty id")
        if entry_id in seen_ids:
            raise ValueError(f"{label} contains duplicate id {entry_id!r}")
        seen_ids.add(entry_id)
        if not isinstance(covers, list) or not covers:
            raise ValueError(f"{label}[{index}].covers must be a non-empty list")
        if any(
            isinstance(item, bool)
            or not isinstance(item, int)
            or item < 1
            or item > description_count
            for item in covers
        ):
            raise ValueError(
                f"{label}[{index}].covers must contain 1-based branch_tests indexes"
            )
        if len(set(covers)) != len(covers):
            raise ValueError(f"{label}[{index}].covers contains duplicates")
        if command_field:
            command = entry.get(command_field)
            if not isinstance(command, str) or not command.strip():
                raise ValueError(
                    f"{label}[{index}].{command_field} must be a non-empty command"
                )
        elif not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
            raise ValueError(f"{label}[{index}] needs a reason")
        validated.append(entry)
    return validated


def execution_manifest(plan: Path, branch: str) -> dict[str, Any] | None:
    """Load and validate an optional explicit description-to-command mapping."""
    manifest_path = plan.with_name("branch-tests.json")
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid branch test manifest: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != 1:
        raise ValueError("branch test manifest must be an object with schema 1")
    if manifest.get("branch") != branch:
        raise ValueError(
            f"branch test manifest is for {manifest.get('branch')!r}, not {branch!r}"
        )
    descriptions = declared_tests(plan)
    if manifest.get("plan_tests") != descriptions:
        raise ValueError(
            "branch-tests.json plan_tests do not exactly match plan.yaml branch_tests"
        )
    commands = _validate_entries(
        manifest.get("commands"),
        label="commands",
        description_count=len(descriptions),
        command_field="command",
    )
    external_gates = _validate_entries(
        manifest.get("external_gates", []),
        label="external_gates",
        description_count=len(descriptions),
    )
    covered = {
        item for entry in (*commands, *external_gates) for item in entry["covers"]
    }
    missing = sorted(set(range(1, len(descriptions) + 1)) - covered)
    if missing:
        raise ValueError(
            "branch test manifest leaves plan test index(es) unmapped: "
            + ", ".join(map(str, missing))
        )
    ci_covered = manifest.get("ci_covered_commands", {})
    command_ids = {entry["id"] for entry in commands}
    if not isinstance(ci_covered, dict) or any(
        not isinstance(command_id, str)
        or command_id not in command_ids
        or not isinstance(job_name, str)
        or not job_name.strip()
        for command_id, job_name in ci_covered.items()
    ):
        raise ValueError(
            "ci_covered_commands must map declared command ids to non-empty CI job names"
        )
    return {
        "commands": commands,
        "external_gates": external_gates,
        "ci_covered_commands": ci_covered,
    }


def main() -> int:
    branch = (
        sys.argv[1] if len(sys.argv) > 1 else os.environ.get("INTEGRATION_BRANCH", "")
    )
    if not branch:
        print("INTEGRATION_BRANCH is required", file=sys.stderr)
        return 2
    plan = Path("ops/workstreams") / slug(branch) / "plan.yaml"
    if not plan.exists():
        print(f"no workstream plan for {branch}: {plan}", file=sys.stderr)
        return 1
    try:
        manifest = execution_manifest(plan, branch)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    list_only = "--list" in sys.argv[2:]
    if manifest is None:
        commands = declared_tests(plan)
        external_gates: list[dict[str, Any]] = []
        if not commands:
            print(f"no branch-declared tests for {branch}")
            return 0
        for index, command in enumerate(commands, 1):
            print(
                f"{'#' if list_only else '▶'} Branch test {index}/{len(commands)}: {command}"
            )
            if not list_only:
                result = subprocess.run(["/bin/sh", "-lc", command], text=True)
                if result.returncode:
                    print(
                        f"branch test failed ({result.returncode}): {command}",
                        file=sys.stderr,
                    )
                    return result.returncode
    else:
        commands = manifest["commands"]
        ci_job_coverage = manifest["ci_covered_commands"]
        requested_coverage = os.environ.get(
            "BRANCH_TESTS_CI_COVERED_COMMANDS", ""
        ).strip()
        if requested_coverage and os.environ.get("GITHUB_ACTIONS") != "true":
            print(
                "BRANCH_TESTS_CI_COVERED_COMMANDS is only accepted in GitHub Actions",
                file=sys.stderr,
            )
            return 2
        covered_command_ids = {
            item.strip() for item in requested_coverage.split(",") if item.strip()
        }
        unknown_coverage = sorted(covered_command_ids - set(ci_job_coverage))
        if unknown_coverage:
            print(
                "CI coverage references undeclared command id(s): "
                + ", ".join(unknown_coverage),
                file=sys.stderr,
            )
            return 1
        external_gates = manifest["external_gates"]
        for index, entry in enumerate(commands, 1):
            command = entry["command"].strip()
            label = f"{entry['id']} (plan tests {', '.join(map(str, entry['covers']))})"
            if entry["id"] in covered_command_ids:
                print(
                    "✓ Covered by successful upstream GitHub CI job: "
                    f"{ci_job_coverage[entry['id']]} ({entry['id']})",
                    flush=True,
                )
                continue
            print(
                f"{'#' if list_only else '▶'} Branch check {index}/{len(commands)}: {label}: {command}",
                flush=True,
            )
            if not list_only:
                result = subprocess.run(["/bin/sh", "-lc", command], text=True)
                if result.returncode:
                    print(
                        f"branch check failed ({result.returncode}): {entry['id']}: {command}",
                        file=sys.stderr,
                    )
                    return result.returncode
        for gate in external_gates:
            indexes = ", ".join(map(str, gate["covers"]))
            print(
                f"{'#' if list_only else '⏸'} External acceptance gate NOT RUN: "
                f"{gate['id']} (plan tests {indexes}) — {gate['reason']}"
            )

    if list_only:
        return 0
    if external_gates:
        print(
            "Local branch checks passed; external acceptance remains NOT RUN. "
            "This result is not full workstream acceptance."
        )
    else:
        print(f"✅  Branch-declared tests passed for {branch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
