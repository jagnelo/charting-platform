#!/usr/bin/env python3
"""Run the explicit, bounded provider live matrix.

Normal CI does not call external services. With ``RUN_LIVE_PROVIDER_TESTS=1``
this command reports every required credential, runs keyless probes, and runs
credentialed probes only when their exact environment is present. Missing
credentials return exit code 2; they are never represented as passing skips.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

KEYLESS = ("EDGAR_USER_AGENT",)
CREDENTIALS = {
    "alpaca": ("ALPACA_API_KEY", "ALPACA_SECRET_KEY"),
    "massive": ("MASSIVE_API_KEY",),
    "alpha_vantage": ("ALPHA_VANTAGE_API_KEY",),
    "coingecko": ("COINGECKO_API_KEY",),
    "fred": ("FRED_API_KEY",),
    "finra": ("FINRA_CLIENT_ID", "FINRA_CLIENT_SECRET"),
    "tiingo": ("TIINGO_API_KEY",),
    "twelve_data": ("TWELVE_DATA_API_KEY",),
    "finnhub": ("FINNHUB_API_KEY",),
    "marketstack": ("MARKETSTACK_API_KEY",),
    "eodhd": ("EODHD_API_KEY",),
    "fmp": ("FMP_API_KEY",),
    "tradier": ("TRADIER_API_KEY",),
    "marketdata_app": ("MARKETDATA_APP_API_KEY",),
}


def changed_provider_code() -> bool:
    status = subprocess.run(["git", "status", "--short"], cwd=ROOT, text=True, capture_output=True)
    if any(path.startswith(("backend/app/providers/", "backend/app/services/provider", "backend/app/models/provider", "backend/tests/live/", "backend/alembic/versions/", "scripts/run-live-provider-probes.py")) for path in (line[3:] for line in status.stdout.splitlines() if len(line) > 3)):
        return True
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
        "backend/alembic/versions/",
    )
    return any(path.startswith(relevant) for path in result.stdout.splitlines())


def main() -> int:
    if not changed_provider_code():
        print("live provider probes: not applicable (no provider-related changes)")
        return 0
    if os.getenv("RUN_LIVE_PROVIDER_TESTS") != "1":
        print("live provider probes: disabled; set RUN_LIVE_PROVIDER_TESTS=1 for external calls")
        return 0
    missing: dict[str, list[str]] = {}
    for provider, names in {"keyless/config": KEYLESS, **CREDENTIALS}.items():
        absent = [name for name in names if not os.getenv(name)]
        if absent:
            missing[provider] = absent
    print("live provider credential preflight:")
    if missing:
        for provider, names in missing.items():
            print(f"  BLOCKED {provider}: missing {', '.join(names)}")
    else:
        print("  all manifest credentials present")
    result = subprocess.run(
        [
            ".venv/bin/pytest",
            "tests/live/test_market_data_providers_live.py",
            "-m",
            "live",
            "--no-header",
            "-q",
            "--no-cov",
        ],
        cwd=ROOT / "backend",
        env={**os.environ, "RUN_LIVE_PROVIDER_TESTS": "1"},
    )
    if result.returncode:
        if missing:
            print("live provider probes: credential preflight incomplete; no acceptance claim")
            return 2
        return result.returncode
    if missing:
        print("live provider probes: credential preflight incomplete; no acceptance claim")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
