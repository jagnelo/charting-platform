"""External usage receipts for quota-consuming live provider probes.

This ledger is deliberately outside Git and outside the application database:
the live suite runs direct adapters and therefore consumes provider accounts
without going through the runtime reservation path.  It records only observed
provider/request/byte counts and never credentials or response bodies.
"""

from __future__ import annotations

import fcntl
import json
import os
from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

DEFAULT_LEDGER = Path.home() / ".config" / "charting-platform" / "provider-live-usage.jsonl"
_CAPACITY_HEADERS = {
    "api-credits-left",
    "api-credits-request",
    "api-credits-used",
    "x-api-ratelimit-limit",
    "x-api-ratelimit-remaining",
    "x-api-ratelimit-reset",
    "x-api-ratelimit-consumed",
    "content-length",
    "record-limit",
    "record-max-limit",
    "record-offset",
    "record-total",
    "total-records-on-page",
    "response-payload-max-size",
    "retry-after",
    "x-bapi-limit",
    "x-bapi-limit-reset-timestamp",
    "x-bapi-limit-status",
    "x-mbx-order-count-1m",
    "x-mbx-used-weight-1m",
    "x-rate-limit-limit",
    "x-rate-limit-remaining",
    "x-rate-limit-reset",
    "x-ratelimit-allowed",
    "x-ratelimit-available",
    "x-ratelimit-expiry",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "x-ratelimit-used",
}
_observations: list[tuple[str, int, int, dict[str, str]]] = []
_PROCESS_RUN_ID = str(uuid4())


def ledger_path() -> Path:
    """Return the owner-managed live-usage ledger path."""

    return Path(os.getenv("PROVIDER_LIVE_USAGE_LEDGER", str(DEFAULT_LEDGER))).expanduser()


def ensure_ledger_writable() -> Path:
    """Verify the live ledger can be opened before any provider calls run.

    Direct live tests consume external quota outside the application runtime.
    A teardown-only write check can otherwise allow calls to happen and then
    lose their usage receipt to a permissions error.  This preflight performs
    only a zero-byte append/open and never writes credentials or payloads.
    """

    path = ledger_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8"):
            pass
    except OSError as exc:
        raise RuntimeError(f"provider live usage ledger is not writable: {path}") from exc
    return path


def _safe_headers(headers: Mapping[str, object] | None) -> dict[str, str]:
    """Keep only bounded provider-capacity headers, never auth/payload data."""

    if not headers:
        return {}
    result: dict[str, str] = {}
    for raw_name, raw_value in headers.items():
        name = str(raw_name).strip().lower()
        value = str(raw_value).strip()
        if (
            name in _CAPACITY_HEADERS
            and name.isprintable()
            and value
            and len(value) <= 256
            and value.isprintable()
        ):
            result[name] = value
    return result


def record_observation(
    provider: str,
    *,
    http_requests: int,
    response_bytes: int,
    response_headers: Mapping[str, object] | None = None,
) -> None:
    """Accumulate one measured live operation without retaining payload data."""

    _observations.append(
        (
            str(provider).strip() or "unknown",
            max(0, int(http_requests)),
            max(0, int(response_bytes)),
            _safe_headers(response_headers),
        )
    )


def flush_observations(exit_status: int) -> Path | None:
    """Append this pytest process's aggregate usage receipt and clear memory."""

    if not _observations:
        return None
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, dict[str, object]] = defaultdict(
        lambda: {
            "http_requests": 0,
            "response_bytes": 0,
            "operations": 0,
            "response_headers": {},
        }
    )
    for provider, requests, response_bytes, response_headers in _observations:
        grouped[provider]["http_requests"] += requests
        grouped[provider]["response_bytes"] += response_bytes
        grouped[provider]["operations"] += 1
        grouped[provider]["response_headers"].update(response_headers)

    # The wrapper supplies an explicit run ID for CI/local manifest runs. A
    # direct pytest invocation must still get a fresh identity: process IDs can
    # be reused across sessions, and merging those rows would corrupt cross-day
    # usage attribution. Keep the generated value process-local and never
    # derive it from a credential or filesystem path.
    run_id = os.getenv("PROVIDER_LIVE_RUN_ID", "").strip() or _PROCESS_RUN_ID
    now = datetime.now(UTC).isoformat()
    usage_scope = os.getenv("PROVIDER_LIVE_USAGE_SCOPE", "").strip() or "unspecified"
    rows = [
        {
            "at": now,
            "run_id": run_id,
            "usage_scope": usage_scope,
            "provider": provider,
            "operations": values["operations"],
            "http_requests": values["http_requests"],
            "response_bytes": values["response_bytes"],
            "exit_status": int(exit_status),
            "response_headers": dict(values["response_headers"]),
        }
        for provider, values in sorted(grouped.items())
    ]
    with path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
            handle.flush()
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    _observations.clear()
    return path


def _reset_for_test() -> None:
    """Clear process-local observations for unit tests."""

    _observations.clear()
