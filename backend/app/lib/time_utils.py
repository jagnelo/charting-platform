"""Shared timestamp wire-format helpers for provenance-facing contracts."""

from __future__ import annotations

from datetime import UTC, datetime


def wire_datetime(value: datetime | None) -> str | None:
    """Serialize an optional timestamp as canonical UTC ``Z`` text.

    SQLite-backed tests and legacy rows may contain naive values.  Treat those
    values as UTC, matching the existing persistence contract, and normalize
    offset-aware values before they cross an API boundary.
    """

    if value is None:
        return None
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.astimezone(UTC).isoformat().replace("+00:00", "Z")
