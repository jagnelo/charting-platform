#!/usr/bin/env python3
"""Run the explicit, bounded provider live matrix.

Normal CI does not call external services. With ``RUN_LIVE_PROVIDER_TESTS=1``
this command reports every required credential, runs keyless probes, and runs
credentialed probes only when their exact environment is present. Missing
credentials return exit code 2; they are never represented as passing skips.
"""

from __future__ import annotations

import json
import importlib.util
import os
import subprocess
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

_LOCK_SPEC = importlib.util.spec_from_file_location(
    "provider_live_lock", Path(__file__).with_name("provider_live_lock.py")
)
if _LOCK_SPEC is None or _LOCK_SPEC.loader is None:  # pragma: no cover - packaging failure
    raise ImportError("provider_live_lock.py is unavailable")
_LOCK_MODULE = importlib.util.module_from_spec(_LOCK_SPEC)
_LOCK_SPEC.loader.exec_module(_LOCK_MODULE)
ProviderLiveRunAlreadyActive = _LOCK_MODULE.ProviderLiveRunAlreadyActive
provider_live_run_lock = _LOCK_MODULE.provider_live_run_lock

ROOT = Path(__file__).resolve().parents[1]
SHARED_ENV_OVERRIDE = "CHARTING_PLATFORM_SHARED_ENV_FILE"
DEFAULT_SHARED_ENV = Path.home() / ".config" / "charting-platform" / "app.env"

KEYLESS = ("EDGAR_USER_AGENT",)
CREDENTIALS = {
    "alpaca": ("ALPACA_API_KEY", "ALPACA_SECRET_KEY"),
    "massive": ("MASSIVE_API_KEY",),
    "alpha_vantage": ("ALPHA_VANTAGE_API_KEY",),
    "coingecko": ("COINGECKO_API_KEY",),
    "fred": ("FRED_API_KEY",),
    "finra": ("FINRA_CLIENT_ID", "FINRA_CLIENT_SECRET"),
    "finra_otc_directory": ("FINRA_OTC_SYMBOL_DIRECTORY_URL",),
    "tiingo": ("TIINGO_API_KEY",),
    "twelve_data": ("TWELVE_DATA_API_KEY",),
    "finnhub": ("FINNHUB_API_KEY",),
    "marketstack": ("MARKETSTACK_API_KEY",),
    "eodhd": ("EODHD_API_KEY",),
    "fmp": ("FMP_API_KEY",),
    "tradier": ("TRADIER_API_KEY",),
    "marketdata_app": ("MARKETDATA_APP_API_KEY",),
    "ibkr": ("IBKR_READ_ONLY_URL", "IBKR_READ_ONLY_SESSION_COOKIE"),
    "dinari": ("DINARI_API_KEY_ID", "DINARI_API_SECRET_KEY"),
    "ondo_global_markets": ("ONDO_GLOBAL_MARKETS_API_KEY",),
}

BYTE_BOUND_OPERATIONS = {
    "tiingo": (
        "fetch_ohlcv",
        "fetch_latest_ohlcv",
        "get_current_price",
        "bulk_fetch",
        "search_instruments",
        "get_instrument_profile",
    ),
    "fmp": (
        "fetch_ohlcv",
        "fetch_latest_ohlcv",
        "get_current_price",
        "bulk_fetch",
        "get_instrument_profile",
        "fetch_market_events",
        "discover_universe_page",
    ),
}

FINRA_OTC_OPERATION_COSTS = ("discover_universe_page", "reconcile_universe_page")


def setting_is_configured(name: str) -> bool:
    """Return whether a live-probe setting is usable, not merely non-empty.

    The checked-in examples use a placeholder SEC contact value. Treating it
    as configured would start live calls and only fail inside the adapter,
    obscuring the exact deployment input that is missing.
    """

    value = os.getenv(name, "").strip()
    if not value:
        return False
    if name == "EDGAR_USER_AGENT" and any(
        marker in value.lower() for marker in ("example.com", "myemail@", "your.email", "<", ">")
    ):
        return False
    return True


def usage_scope_is_configured() -> bool:
    """Require an attributable, bounded label for quota-consuming live runs."""

    value = os.getenv("PROVIDER_LIVE_USAGE_SCOPE", "").strip()
    return bool(value) and len(value) <= 128 and value.isprintable()


def routing_safety_preflight() -> dict[str, str]:
    """Describe safety controls that can block routing after a live read.

    Direct adapter probes intentionally remain useful even when a provider is
    non-routable. This report prevents a green adapter read from being
    mistaken for safe quota admission when a provider publishes a bandwidth
    pool without universal response-size ceilings.
    """

    result: dict[str, str] = {}
    async_bound = os.getenv("FINRA_ASYNC_MAX_RESULT_BYTES", "0").strip() or "0"
    try:
        result["finra async result bytes"] = (
            "routable"
            if int(async_bound) > 0
            else "non-routable: positive reviewed bound required"
        )
    except ValueError:
        result["finra async result bytes"] = "non-routable: bound is not an integer"

    finra_otc_missing: list[str] = []
    raw_finra_otc_costs = os.getenv("FINRA_OTC_OPERATION_COSTS", "").strip()
    try:
        finra_otc_costs = json.loads(raw_finra_otc_costs) if raw_finra_otc_costs else {}
    except json.JSONDecodeError:
        finra_otc_costs = None
    if not isinstance(finra_otc_costs, dict):
        finra_otc_missing.append("FINRA_OTC_OPERATION_COSTS")
    elif not all(
        isinstance(finra_otc_costs.get(operation), int)
        and not isinstance(finra_otc_costs.get(operation), bool)
        and finra_otc_costs[operation] > 0
        for operation in FINRA_OTC_OPERATION_COSTS
    ):
        finra_otc_missing.append("FINRA_OTC_OPERATION_COSTS")
    for variable in (
        "FINRA_OTC_TERMS_REVIEWED",
        "FINRA_OTC_COMPLETENESS_REVIEWED",
        "FINRA_OTC_REDISTRIBUTION_REVIEWED",
    ):
        if os.getenv(variable, "").strip().lower() not in {"1", "true", "yes"}:
            finra_otc_missing.append(variable)
    try:
        finra_otc_poll = int(os.getenv("FINRA_OTC_POLL_INTERVAL_SECONDS", "0").strip() or "0")
    except ValueError:
        finra_otc_poll = 0
    if finra_otc_poll <= 0:
        finra_otc_missing.append("FINRA_OTC_POLL_INTERVAL_SECONDS")
    result["finra otc directory"] = (
        "routable"
        if not finra_otc_missing
        else "non-routable: missing/invalid " + ", ".join(dict.fromkeys(finra_otc_missing))
    )

    # These providers have a useful live read but still lack one or more
    # provider-specific admission dimensions. Keep the gap visible next to
    # the byte-bound controls rather than letting a passing probe imply safe
    # routing.
    fred_scope = os.getenv("FRED_REVIEWED_LIMIT_SCOPE", "").strip()
    try:
        fred_limit = int(os.getenv("FRED_REVIEWED_REQUESTS_PER_MINUTE", "0").strip() or "0")
    except ValueError:
        fred_limit = 0
    fred_terms_reviewed = os.getenv("FRED_SERIES_TERMS_REVIEWED", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    fred_missing: list[str] = []
    if fred_scope not in {"api_key", "account", "ip", "deployment"}:
        fred_missing.append("FRED_REVIEWED_LIMIT_SCOPE")
    if not 0 < fred_limit <= 120:
        fred_missing.append("FRED_REVIEWED_REQUESTS_PER_MINUTE")
    if not fred_terms_reviewed:
        fred_missing.append("FRED_SERIES_TERMS_REVIEWED")
    result["fred"] = (
        "routable"
        if not fred_missing
        else "non-routable: missing/invalid " + ", ".join(fred_missing)
    )
    result["nasdaq"] = "non-routable: official public polling allowance is not published"
    result["xstocks"] = (
        "non-routable: numeric public quota is not published; official US-person, "
        "jurisdiction, and redistribution eligibility must be reviewed"
    )
    result["bybit_xstocks"] = (
        "non-routable: endpoint/UID limits require provider-native header state"
    )
    result["marketstack discovery"] = (
        "routable"
        if os.getenv("MARKETSTACK_DISCOVERY_EXCHANGE", "").strip()
        else "non-routable: MARKETSTACK_DISCOVERY_EXCHANGE is unset"
    )

    for provider, operations in BYTE_BOUND_OPERATIONS.items():
        variable = f"{provider.upper()}_OPERATION_BYTE_BOUNDS"
        raw = os.getenv(variable, "").strip()
        if not raw:
            result[provider] = f"non-routable: {variable} is unset"
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            result[provider] = f"non-routable: {variable} is not valid JSON"
            continue
        if not isinstance(parsed, dict):
            result[provider] = f"non-routable: {variable} must be a JSON object"
            continue
        missing = [
            operation
            for operation in operations
            if operation not in parsed
            or not isinstance(parsed[operation], int)
            or isinstance(parsed[operation], bool)
            or parsed[operation] <= 0
        ]
        result[provider] = (
            "routable"
            if not missing
            else f"non-routable: missing positive bounds for {', '.join(missing)}"
        )
    return result


def changed_provider_code() -> bool:
    if os.getenv("FORCE_LIVE_PROVIDER_PROBES") == "1":
        return True
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
    # Prefer an operator-owned source outside Git. Worktree runtime setup links
    # the usual ignored paths to this file, but loading it directly also makes
    # this command safe to run before any Make target. Explicit exports retain
    # precedence. Do not print or persist loaded secret values.
    shared_env = Path(
        os.getenv(SHARED_ENV_OVERRIDE, str(DEFAULT_SHARED_ENV))
    ).expanduser()
    if shared_env.exists():
        load_dotenv(shared_env, override=False)
    load_dotenv(ROOT / "backend" / ".env.dev", override=False)
    if not changed_provider_code():
        print("live provider probes: not applicable (no provider-related changes)")
        return 0
    if os.getenv("RUN_LIVE_PROVIDER_TESTS") != "1":
        print("live provider probes: disabled; set RUN_LIVE_PROVIDER_TESTS=1 for external calls")
        return 0
    missing: dict[str, list[str]] = {}
    for provider, names in {"keyless/config": KEYLESS, **CREDENTIALS}.items():
        absent = [name for name in names if not setting_is_configured(name)]
        if absent:
            missing[provider] = absent
    if not usage_scope_is_configured():
        missing["usage accounting"] = ["PROVIDER_LIVE_USAGE_SCOPE"]
    print("live provider credential/usage preflight:")
    if missing:
        for provider, names in missing.items():
            print(f"  BLOCKED {provider}: missing {', '.join(names)}")
    else:
        print("  all manifest credentials present")
    print("routing safety preflight:")
    for provider, status in routing_safety_preflight().items():
        print(f"  {provider}: {status}")
    try:
        with provider_live_run_lock() as lock_path:
            print(f"live provider lock: {lock_path}")
            result = subprocess.run(
                [
                    ".venv/bin/pytest",
                    "tests/live/test_market_data_providers_live.py",
                    "tests/live/test_tokenized_providers_live.py",
                    "-m",
                    "live",
                    "--no-header",
                    "-q",
                    "--no-cov",
                ],
                cwd=ROOT / "backend",
                env={
                    **os.environ,
                    "RUN_LIVE_PROVIDER_TESTS": "1",
                    "PROVIDER_LIVE_RUN_ID": str(uuid4()),
                },
            )
    except ProviderLiveRunAlreadyActive as exc:
        print(f"live provider probes: blocked by local key-use lock: {exc}")
        return 3
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
