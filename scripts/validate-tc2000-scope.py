#!/usr/bin/env python3
"""Fail when changes since the TC scope checkpoint leave the approved ownership boundary."""

from __future__ import annotations

import fnmatch
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "ops/workstreams/feat-tc2000-frontend-rework/plan.yaml"
LEDGER_PATH = ROOT / "ops/workstreams/feat-tc2000-frontend-rework/ownership-reconciliation.yaml"


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def matches(path: str, pattern: str) -> bool:
    normalized = pattern.rstrip("/")
    if pattern.endswith("/"):
        return path == normalized or path.startswith(normalized + "/")
    return fnmatch.fnmatchcase(path, pattern)


def authorized(path: str, plan: dict[str, Any]) -> tuple[bool, str]:
    if any(matches(path, str(item)) for item in plan.get("excluded_paths", [])):
        return False, "excluded upstream or adjacent ownership"
    exceptions = {
        str(item.get("path")): str(item.get("reason", "shared path exception"))
        for item in plan.get("shared_path_exceptions", [])
        if isinstance(item, dict)
    }
    if path in exceptions:
        return True, f"documented shared-path exception: {exceptions[path]}"
    if any(matches(path, str(item)) for item in plan.get("owned_paths", [])):
        return True, "TC-owned path"
    return False, "not in the TC owned_paths allowlist or shared-path exceptions"


def changed_paths(baseline: str) -> set[str]:
    values: set[str] = set()
    for output in (
        git("diff", "--name-only", baseline, "--"),
        git("diff", "--cached", "--name-only", "--"),
        git("ls-files", "--others", "--exclude-standard"),
    ):
        values.update(line for line in output.splitlines() if line)
    return values


def validate_ledger() -> None:
    ledger = yaml.safe_load(LEDGER_PATH.read_text())
    if not isinstance(ledger, dict):
        raise ValueError(f"{LEDGER_PATH} is not a YAML mapping")
    intersections = ledger
    valid_dispositions = {
        "tc_owned",
        "upstream_duplicate",
        "upstream_transfer_required",
        "shared_reconciliation",
    }
    for owner, expected_count in (
        ("market_data_provider_platform", 78),
        ("etf_holdings_constituents", 35),
    ):
        group = intersections.get(owner)
        if not isinstance(group, dict) or not isinstance(group.get("paths"), list):
            raise ValueError(f"ownership ledger is missing {owner} path list")
        entries = group["paths"]
        if len(entries) != expected_count or group.get("measured_count") != expected_count:
            raise ValueError(
                f"{owner} overlap count changed: expected {expected_count}, got {len(entries)}"
            )
        names: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"{owner} paths must be mappings with disposition")
            path = str(entry.get("path", ""))
            if not path or path in names:
                raise ValueError(f"{owner} path missing or duplicated: {path!r}")
            names.add(path)
            if entry.get("disposition") not in valid_dispositions:
                raise ValueError(f"invalid {owner} disposition for {path}")
    if ledger.get("snapshot", {}).get("strategy_lab_overlap_count") != 0:
        raise ValueError("the ignored Strategy Lab branch must remain a zero-overlap record")


def self_test() -> int:
    plan = {
        "owned_paths": ["frontend/src/components/workstation/", "docs/tc2000-roadmap.md"],
        "excluded_paths": ["frontend/src/components/etf/", "docs/project-todos.md"],
        "shared_path_exceptions": [
            {"path": "frontend/src/types/index.ts", "reason": "consumer types only"}
        ],
    }
    checks = {
        "TC owned directory": authorized(
            "frontend/src/components/workstation/MarketMapTool.vue", plan
        )[0],
        "TC owned exact file": authorized("docs/tc2000-roadmap.md", plan)[0],
        "documented shared seam": authorized("frontend/src/types/index.ts", plan)[0],
        "ETF exclusion overrides broad ownership": not authorized(
            "frontend/src/components/etf/ETFHoldingsPanel.vue", plan
        )[0],
        "project todos remains outside scope": not authorized(
            "docs/project-todos.md", plan
        )[0],
        "unknown path fails closed": not authorized("backend/app/providers/new.py", plan)[0],
    }
    failed = [name for name, passed in checks.items() if not passed]
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'} {name}")
    return 1 if failed else 0


def main() -> int:
    if "--self-test" in sys.argv[1:]:
        return self_test()
    try:
        plan = yaml.safe_load(PLAN_PATH.read_text())
        if not isinstance(plan, dict):
            raise ValueError(f"{PLAN_PATH} is not a YAML mapping")
        if git("rev-parse", "--abbrev-ref", "HEAD") != "feat/tc2000-frontend-rework":
            raise ValueError("scope validation must run inside feat/tc2000-frontend-rework")
        baseline = str(plan.get("scope_guard_baseline_sha", "")).strip()
        if not baseline:
            raise ValueError("plan.yaml must declare scope_guard_baseline_sha")
        git("cat-file", "-e", f"{baseline}^{{commit}}")
        validate_ledger()
        paths = sorted(changed_paths(baseline))
        rejected: list[tuple[str, str]] = []
        for path in paths:
            allowed, reason = authorized(path, plan)
            if not allowed:
                rejected.append((path, reason))
        if rejected:
            print("TC scope guard rejected changed paths:", file=sys.stderr)
            for path, reason in rejected:
                print(f"  {path}: {reason}", file=sys.stderr)
            return 1
        print(
            f"TC scope guard passed: {len(paths)} changed paths since {baseline}; "
            "all are TC-owned or documented shared seams."
        )
        return 0
    except (OSError, RuntimeError, ValueError, yaml.YAMLError) as exc:
        print(f"TC scope guard error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
