"""Run the complete backend suite in bounded processes with combined coverage."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
BASE_TEST_ROOTS = ("tests/unit", "tests/integration")
STRATEGY_TEST_ROOT = "app/strategy_lab_v2/tests"
UNIT_TEST_ROOTS = (
    "tests/unit",
    *((STRATEGY_TEST_ROOT,) if (BACKEND_DIR / STRATEGY_TEST_ROOT).is_dir() else ()),
)
TEST_ROOTS = (*UNIT_TEST_ROOTS, "tests/integration")
# Keep shards small enough for the resource-limited research-runner tests.
# A few research-runner cases allocate large scientific-data fixtures; grouping
# 100 of them in one process can exhaust the 1 GiB test-process ceiling before
# pytest can emit a failure summary.  Smaller shards preserve the same complete
# test set while making each process independently bounded and diagnosable.
DEFAULT_UNIT_SHARD_SIZE = 50
COLLECTION_TIMEOUT_SECONDS = 300
UNIT_SHARD_TIMEOUT_SECONDS = 300
INTEGRATION_TIMEOUT_SECONDS = 900


def partition(items: Sequence[str], size: int) -> list[list[str]]:
    if size < 1:
        raise ValueError("shard size must be positive")
    return [list(items[start : start + size]) for start in range(0, len(items), size)]


def combined_unit_nodeids(suites: dict[str, list[str]]) -> list[str]:
    """Include every available unit-like suite in the same bounded shards."""
    return [nodeid for root in UNIT_TEST_ROOTS for nodeid in suites[root]]


def parse_collected_nodeids(output: str) -> dict[str, list[str]]:
    collected = {root: [] for root in TEST_ROOTS}
    for raw_line in output.splitlines():
        nodeid = raw_line.strip()
        for root in TEST_ROOTS:
            if nodeid.startswith(f"{root}/") and "::" in nodeid:
                collected[root].append(nodeid)
                break
    return collected


def run(
    command: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: int | None = None,
) -> int:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            check=False,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        print(f"test process exceeded its {timeout}s wall-time limit", file=sys.stderr)
        return 124
    return completed.returncode


def pytest_args(nodeids: Sequence[str]) -> list[str]:
    return [
        "-m",
        "pytest",
        *nodeids,
        "--override-ini",
        "addopts=",
        "--cov=app",
        "--cov-append",
        "--cov-report=",
        "--override-ini",
        "faulthandler_timeout=60",
        "--no-header",
        "-q",
    ]


def _run_pytest(
    nodeids: Sequence[str],
    *,
    label: str,
    env: dict[str, str],
    timeout: int,
) -> int:
    print(f"▶ {label}: {len(nodeids)} tests", flush=True)
    status = run(
        [sys.executable, *pytest_args(nodeids)],
        cwd=BACKEND_DIR,
        env=env,
        timeout=timeout,
    )
    if status:
        if status < 0:
            print(f"✗ {label} terminated by signal {-status}", flush=True)
            return min(255, 128 + -status)
        print(f"✗ {label} exited with status {status}", flush=True)
        return status
    print(f"✓ {label} passed", flush=True)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shard-size", type=int, default=DEFAULT_UNIT_SHARD_SIZE)
    args = parser.parse_args(argv)
    if args.shard_size < 1:
        parser.error("--shard-size must be positive")

    env = os.environ.copy()
    print("▶ Collecting backend test IDs...", flush=True)
    try:
        collect = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                *TEST_ROOTS,
                "--collect-only",
                "--override-ini",
                "addopts=",
                "--no-header",
                "-q",
            ],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=COLLECTION_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        for partial in (exc.stdout, exc.stderr):
            if partial:
                text = (
                    partial.decode(errors="replace")
                    if isinstance(partial, bytes)
                    else partial
                )
                sys.stderr.write(text)
        print(
            f"✗ backend test collection exceeded its "
            f"{COLLECTION_TIMEOUT_SECONDS}s wall-time limit",
            file=sys.stderr,
            flush=True,
        )
        return 124
    if collect.returncode:
        sys.stderr.write(collect.stdout)
        sys.stderr.write(collect.stderr)
        return collect.returncode

    suites = parse_collected_nodeids(collect.stdout)
    missing = [root for root, nodeids in suites.items() if not nodeids]
    if missing:
        print(
            f"collection did not return test IDs for: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    print(
        "Collected "
        + ", ".join(f"{len(suites[root])} {root} tests" for root in TEST_ROOTS),
        flush=True,
    )

    status = run([sys.executable, "-m", "coverage", "erase"], cwd=BACKEND_DIR, env=env)
    if status:
        return status

    unit_shards = partition(combined_unit_nodeids(suites), args.shard_size)
    for index, nodeids in enumerate(unit_shards, start=1):
        status = _run_pytest(
            nodeids,
            label=f"unit shard {index}/{len(unit_shards)}",
            env=env,
            timeout=UNIT_SHARD_TIMEOUT_SECONDS,
        )
        if status:
            return status

    status = _run_pytest(
        suites["tests/integration"],
        label="Docker integration suite",
        env=env,
        timeout=INTEGRATION_TIMEOUT_SECONDS,
    )
    if status:
        return status

    for command in (
        [sys.executable, "-m", "coverage", "report", "--fail-under=75"],
        [sys.executable, "-m", "coverage", "xml", "-o", "coverage-combined.xml"],
    ):
        status = run(command, cwd=BACKEND_DIR, env=env)
        if status:
            return status
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
