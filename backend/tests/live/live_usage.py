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
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_LEDGER = Path.home() / ".config" / "charting-platform" / "provider-live-usage.jsonl"
_observations: list[tuple[str, int, int]] = []


def record_observation(provider: str, *, http_requests: int, response_bytes: int) -> None:
    """Accumulate one measured live operation without retaining payload data."""

    _observations.append(
        (
            str(provider).strip() or "unknown",
            max(0, int(http_requests)),
            max(0, int(response_bytes)),
        )
    )


def flush_observations(exit_status: int) -> Path | None:
    """Append this pytest process's aggregate usage receipt and clear memory."""

    if not _observations:
        return None
    path = Path(os.getenv("PROVIDER_LIVE_USAGE_LEDGER", str(DEFAULT_LEDGER))).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, dict[str, int]] = defaultdict(
        lambda: {"http_requests": 0, "response_bytes": 0, "operations": 0}
    )
    for provider, requests, response_bytes in _observations:
        grouped[provider]["http_requests"] += requests
        grouped[provider]["response_bytes"] += response_bytes
        grouped[provider]["operations"] += 1

    run_id = os.getenv("PROVIDER_LIVE_RUN_ID", "").strip() or f"pid-{os.getpid()}"
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
