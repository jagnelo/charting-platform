#!/usr/bin/env python3
"""Run the commands declared by one branch-local workstream plan."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


def slug(branch: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", branch).strip("-").lower()


def declared_commands(plan: Path) -> list[str]:
    commands: list[str] = []
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
            command = next(value for value in match.groups() if value is not None)
            if command.strip():
                commands.append(command.strip())
    return commands


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
    commands = declared_commands(plan)
    if not commands:
        print(f"no branch-declared tests for {branch}")
        return 0
    if "--list" in sys.argv[2:]:
        print("\n".join(commands))
        return 0
    for index, command in enumerate(commands, 1):
        print(f"▶  Branch test {index}/{len(commands)}: {command}", flush=True)
        result = subprocess.run(["/bin/sh", "-lc", command], text=True)
        if result.returncode:
            print(
                f"branch test failed ({result.returncode}): {command}", file=sys.stderr
            )
            return result.returncode
    print(f"✅  Branch-declared tests passed for {branch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
