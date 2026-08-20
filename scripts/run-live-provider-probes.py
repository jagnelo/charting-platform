#!/usr/bin/env python3
"""Run only reviewed, explicitly enabled live provider probes.

CI never calls paid or credentialed upstreams implicitly. Provider-related
changes still leave an auditable result: deterministic provider contracts run
normally, while this command runs the allow-listed OpenFIGI probe only when
``RUN_LIVE_PROVIDER_TESTS=1`` is explicitly supplied.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def changed_provider_code() -> bool:
    base = os.getenv("INTEGRATION_BASE_SHA")
    if not base:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD^1"], cwd=ROOT, text=True, capture_output=True
        )
        base = result.stdout.strip() if result.returncode == 0 else ""
    if not base:
        return True
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}..HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    relevant = (
        "backend/app/providers/",
        "backend/app/services/provider",
        "backend/app/models/provider",
        "backend/tests/live/",
        "backend/tests/integration/provider",
        "backend/alembic/versions/fd3e2f",
    )
    return any(path.startswith(relevant) for path in result.stdout.splitlines())


def main() -> int:
    if not changed_provider_code():
        print("live provider probes: skipped (no provider-related changes)")
        return 0
    if os.getenv("RUN_LIVE_PROVIDER_TESTS") != "1":
        print(
            "live provider probes: not configured; deterministic provider contracts remain authoritative "
            "(set RUN_LIVE_PROVIDER_TESTS=1 to run the reviewed OpenFIGI probe)"
        )
        return 0
    print("live provider probes: running allow-listed OpenFIGI route")
    return subprocess.run(
        [
            ".venv/bin/pytest",
            "tests/live/test_openfigi_live.py",
            "-m",
            "live",
            "--no-header",
            "-q",
        ],
        cwd=ROOT / "backend",
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
