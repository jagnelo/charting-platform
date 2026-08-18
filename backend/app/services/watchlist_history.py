"""Bounded history hydration planning for canonical watchlist sources.

Interactive workstation tools consume local canonical bars.  This module owns
the explicit maintenance boundary used to hydrate those bars for any source
that the requesting user can resolve.  It deliberately only resolves local
membership and returns a queueable plan; provider calls remain inside the
existing isolated bulk-history worker.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ohlcv import Timeframe
from app.services.watchlist_sources import resolve_watchlist_source

DEFAULT_HISTORY_TIMEFRAMES = (Timeframe.MN.value, Timeframe.W1.value, Timeframe.D1.value)
MAX_HISTORY_INSTRUMENTS = 5000
MAX_HISTORY_SOURCES = 256


def normalize_source_ids(source_ids: list[str] | None) -> list[str]:
    """Deduplicate explicit source IDs while preserving the caller's order."""

    normalized: list[str] = []
    seen: set[str] = set()
    for value in source_ids or []:
        source_id = str(value).strip()
        if not source_id or source_id in seen:
            continue
        seen.add(source_id)
        normalized.append(source_id)
    if not normalized:
        raise ValueError("At least one watchlist source is required.")
    if len(normalized) > MAX_HISTORY_SOURCES:
        raise ValueError(f"At most {MAX_HISTORY_SOURCES} watchlist sources may be requested.")
    return normalized


def normalize_history_timeframes(timeframes: list[str] | None) -> list[str]:
    """Validate supported bulk-fetch resolutions and retain deterministic order."""

    requested = timeframes or list(DEFAULT_HISTORY_TIMEFRAMES)
    normalized: list[str] = []
    for value in requested:
        try:
            timeframe = Timeframe(str(value).strip().upper())
        except ValueError as exc:
            raise ValueError(f"Unsupported history timeframe: {value!r}.") from exc
        if timeframe.value not in normalized:
            normalized.append(timeframe.value)
    if not normalized:
        raise ValueError("At least one history timeframe is required.")
    return normalized


async def plan_watchlist_source_history_refresh(
    db: AsyncSession,
    user_id: int,
    *,
    source_ids: list[str] | None,
    as_of: datetime | None = None,
    max_instruments: int = MAX_HISTORY_INSTRUMENTS,
    timeframes: list[str] | None = None,
) -> dict[str, Any]:
    """Resolve a bounded, user-authorized source set into canonical IDs.

    All source kinds intentionally go through ``resolve_watchlist_source`` so
    user-owned membership isolation, point-in-time filtering, locked-source
    semantics, and exclusions remain identical to Market Map and breadth.
    Unknown or unavailable sources are retained as per-source evidence rather
    than replaced by another universe.
    """

    if max_instruments < 1 or max_instruments > MAX_HISTORY_INSTRUMENTS:
        raise ValueError(f"max_instruments must be between 1 and {MAX_HISTORY_INSTRUMENTS}.")

    normalized_sources = normalize_source_ids(source_ids)
    normalized_timeframes = normalize_history_timeframes(timeframes)
    instrument_ids: list[int] = []
    seen_instruments: set[int] = set()
    sources: list[dict[str, Any]] = []

    for source_id in normalized_sources:
        try:
            resolved = await resolve_watchlist_source(db, user_id, source_id, as_of=as_of)
        except (LookupError, ValueError) as exc:
            sources.append(
                {
                    "source_id": source_id,
                    "source_kind": None,
                    "name": source_id,
                    "locked": False,
                    "status": "unavailable",
                    "member_count": 0,
                    "selected_count": 0,
                    "deduplicated_count": 0,
                    "excluded_count": 0,
                    "membership_version": None,
                    "message": str(exc),
                }
            )
            continue

        members = list(resolved.members)
        selected_count = 0
        for member in members:
            if member.instrument_id in seen_instruments:
                continue
            seen_instruments.add(member.instrument_id)
            instrument_ids.append(member.instrument_id)
            selected_count += 1

        sources.append(
            {
                "source_id": resolved.descriptor.source_id,
                "source_kind": resolved.descriptor.source_kind,
                "name": resolved.descriptor.name,
                "locked": resolved.descriptor.locked,
                "status": "ready" if members else "unavailable",
                "member_count": len(members),
                "selected_count": selected_count,
                "deduplicated_count": len(members) - selected_count,
                "excluded_count": len(resolved.exclusions),
                "membership_version": resolved.descriptor.membership_version,
                "message": (
                    None
                    if members
                    else next(
                        (
                            str(exclusion.get("reason"))
                            for exclusion in resolved.exclusions
                            if exclusion.get("reason")
                        ),
                        "No resolved local members are available.",
                    )
                ),
            }
        )

    limited = len(instrument_ids) > max_instruments
    selected_ids = instrument_ids[:max_instruments]
    return {
        "source_ids": normalized_sources,
        "timeframes": normalized_timeframes,
        "as_of": as_of,
        "max_instruments": max_instruments,
        "instrument_ids": selected_ids,
        "available_instrument_count": len(instrument_ids),
        "selected_instrument_count": len(selected_ids),
        "limited": limited,
        "sources": sources,
    }
