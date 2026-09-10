#!/usr/bin/env python3
"""Merge redacted provider-live usage receipts into an owner-managed ledger.

Receipts from local worktrees and GitHub artifacts are account-level evidence,
not runtime quota reservations. This utility accepts only the aggregate fields
emitted by ``tests/live/live_usage.py``, deduplicates a run/provider row under
an exclusive destination lock, and never copies unknown fields such as payloads
or credentials.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
    else:
        return None
    return parsed if parsed >= 0 else None


def _normalise_row(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    provider = str(value.get("provider") or "").strip()
    if not provider or len(provider) > 128:
        return None
    usage_scope = str(value.get("usage_scope") or "unspecified").strip()
    if not usage_scope or len(usage_scope) > 128 or not usage_scope.isprintable():
        return None
    try:
        observed = datetime.fromisoformat(str(value.get("at") or ""))
    except (TypeError, ValueError):
        return None
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=UTC)
    else:
        observed = observed.astimezone(UTC)
    values: dict[str, int | None] = {
        field: _nonnegative_int(value.get(field))
        for field in ("operations", "http_requests", "response_bytes", "exit_status")
    }
    if any(item is None for item in values.values()):
        return None
    row: dict[str, Any] = {
        "at": observed.isoformat(),
        "usage_scope": usage_scope,
        "provider": provider,
        **{field: int(item) for field, item in values.items()},
    }
    run_id = str(value.get("run_id") or "").strip()
    if run_id:
        if len(run_id) > 256:
            return None
        row["run_id"] = run_id
    return row


def _row_key(row: dict[str, Any]) -> tuple[str, ...]:
    run_id = str(row.get("run_id") or "").strip()
    if run_id:
        return (
            "run",
            run_id,
            str(row.get("usage_scope") or "unspecified"),
            str(row["provider"]),
        )
    canonical = json.dumps(row, sort_keys=True, separators=(",", ":")).encode()
    return ("row", hashlib.sha256(canonical).hexdigest())


def _read_receipt(path: Path) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    rejected = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return [], 1
    for line in lines:
        if not line.strip():
            continue
        try:
            candidate = _normalise_row(json.loads(line))
        except (json.JSONDecodeError, TypeError, ValueError):
            candidate = None
        if candidate is None:
            rejected += 1
        else:
            rows.append(candidate)
    return rows, rejected


def merge_receipts(sources: Iterable[Path], destination: Path) -> dict[str, int | str]:
    """Merge sources into ``destination`` while holding an exclusive lock."""

    destination = destination.expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_paths = [path.expanduser() for path in sources]
    destination_resolved = destination.resolve()
    if any(path.resolve() == destination_resolved for path in source_paths):
        raise ValueError("destination must not also be a receipt source")

    accepted = duplicates = rejected = 0
    with destination.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            seen: set[tuple[str, ...]] = set()
            handle.seek(0)
            for line in handle:
                if not line.strip():
                    continue
                try:
                    existing = _normalise_row(json.loads(line))
                except (json.JSONDecodeError, TypeError, ValueError):
                    existing = None
                if existing is not None:
                    seen.add(_row_key(existing))
            handle.seek(0, os.SEEK_END)
            for source in source_paths:
                rows, source_rejected = _read_receipt(source)
                rejected += source_rejected
                for row in rows:
                    key = _row_key(row)
                    if key in seen:
                        duplicates += 1
                        continue
                    handle.write(json.dumps(row, sort_keys=True) + "\n")
                    seen.add(key)
                    accepted += 1
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    try:
        os.chmod(destination, 0o600)
    except OSError:
        pass
    return {
        "destination": str(destination),
        "accepted": accepted,
        "duplicates": duplicates,
        "rejected": rejected,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("sources", nargs="+", type=Path)
    args = parser.parse_args(argv)
    try:
        result = merge_receipts(args.sources, args.destination)
    except (OSError, ValueError) as exc:
        print(f"provider live usage merge failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 2 if int(result["rejected"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
