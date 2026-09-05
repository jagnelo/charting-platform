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

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ohlcv import OHLCVBar, Timeframe
from app.services.watchlist_sources import (
    PENDING_SOURCE_AVAILABILITIES,
    resolve_watchlist_source,
)

DEFAULT_HISTORY_TIMEFRAMES = (Timeframe.MN.value, Timeframe.W1.value, Timeframe.D1.value)
MAX_HISTORY_INSTRUMENTS = 5000
MAX_HISTORY_SOURCES = 256

# Match the technical-history floors used by benchmark-family readiness. The
# generic source contract should expose the same distinction between one usable
# observation and enough local history for the workstation's historical
# studies, while retaining its existing covered/worker status semantics.
ANALYSIS_REQUIRED_BAR_COUNTS = {
    Timeframe.D1.value: 252,
    Timeframe.W1.value: 52,
    Timeframe.MN.value: 24,
}


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

        provenance = getattr(resolved.descriptor, "provenance", None) or {}
        availability = str(provenance.get("availability") or "")
        source_status = (
            "ready"
            if members
            else ("pending" if availability in PENDING_SOURCE_AVAILABILITIES else "unavailable")
        )
        sources.append(
            {
                "source_id": resolved.descriptor.source_id,
                "source_kind": resolved.descriptor.source_kind,
                "name": resolved.descriptor.name,
                "locked": resolved.descriptor.locked,
                "status": source_status,
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


async def build_watchlist_source_history_status(
    db: AsyncSession,
    user_id: int,
    *,
    source_id: str,
    as_of: datetime | None = None,
    max_instruments: int = MAX_HISTORY_INSTRUMENTS,
    timeframes: list[str] | None = None,
    progress_by_instrument: dict[int, dict] | None = None,
) -> dict[str, Any]:
    """Summarize local bar coverage and worker progress for one canonical source.

    This is deliberately a read-only local status calculation.  It reuses the same
    resolver/planner as the history-refresh endpoint, so an arbitrary personal list,
    locked index/ETF source, combo, or explicit selection has identical membership and
    point-in-time semantics.  ``progress_by_instrument`` is supplied by the router from
    the existing Redis progress records; the service itself never contacts a provider.
    """

    plan = await plan_watchlist_source_history_refresh(
        db,
        user_id,
        source_ids=[source_id],
        as_of=as_of,
        max_instruments=max_instruments,
        timeframes=timeframes,
    )
    normalized_timeframes = [Timeframe(value) for value in plan["timeframes"]]
    instrument_ids = list(plan["instrument_ids"])
    bar_query = select(
        OHLCVBar.timeframe,
        func.count(func.distinct(OHLCVBar.instrument_id)).label("covered_count"),
        func.count(OHLCVBar.id).label("bar_count"),
        func.min(OHLCVBar.ts).label("oldest"),
        func.max(OHLCVBar.ts).label("newest"),
    ).where(
        OHLCVBar.instrument_id.in_(instrument_ids),
        OHLCVBar.timeframe.in_(normalized_timeframes),
        OHLCVBar.is_adjusted.is_(True),
    )
    if as_of is not None:
        bar_query = bar_query.where(OHLCVBar.ts <= as_of)
    bar_rows = (
        (await db.execute(bar_query.group_by(OHLCVBar.timeframe))).all() if instrument_ids else []
    )
    bars_by_timeframe = {row.timeframe.value: row for row in bar_rows}
    covered_rows = (
        (
            await db.execute(
                select(
                    OHLCVBar.instrument_id,
                    OHLCVBar.timeframe,
                    func.count(OHLCVBar.id).label("bar_count"),
                )
                .where(
                    OHLCVBar.instrument_id.in_(instrument_ids),
                    OHLCVBar.timeframe.in_(normalized_timeframes),
                    OHLCVBar.is_adjusted.is_(True),
                    *([OHLCVBar.ts <= as_of] if as_of is not None else []),
                )
                .group_by(OHLCVBar.instrument_id, OHLCVBar.timeframe)
            )
        ).all()
        if instrument_ids
        else []
    )
    covered_instruments_by_timeframe: dict[str, set[int]] = {}
    analysis_ready_instruments_by_timeframe: dict[str, set[int]] = {}
    for row in covered_rows:
        # Keep compatibility with lightweight test doubles and older callers
        # that return the pre-floor two-column shape. Production SQL returns
        # the grouped count needed for analysis readiness.
        instrument_id, timeframe = row[0], row[1]
        covered_instruments_by_timeframe.setdefault(timeframe.value, set()).add(instrument_id)
        bar_count = int(row[2]) if len(row) > 2 and row[2] is not None else None
        required = ANALYSIS_REQUIRED_BAR_COUNTS.get(timeframe.value)
        if bar_count is not None and required is not None and bar_count >= required:
            analysis_ready_instruments_by_timeframe.setdefault(timeframe.value, set()).add(
                instrument_id
            )
    progress_by_instrument = progress_by_instrument or {}
    timeframe_statuses: list[dict[str, Any]] = []
    for timeframe in normalized_timeframes:
        row = bars_by_timeframe.get(timeframe.value)
        covered_count = int(row.covered_count) if row is not None else 0
        covered_instruments = covered_instruments_by_timeframe.get(timeframe.value, set())
        analysis_ready_count = len(
            analysis_ready_instruments_by_timeframe.get(timeframe.value, set())
        )
        progress_counts = {"in_progress": 0, "complete": 0, "failed": 0, "pending": 0}
        for instrument_id in instrument_ids:
            progress = progress_by_instrument.get(instrument_id)
            result = (progress or {}).get("results", {}).get(timeframe.value)
            if (progress or {}).get("status") == "in_progress" and result is None:
                progress_counts["in_progress"] += 1
            elif isinstance(result, str) and result.startswith("error:"):
                progress_counts["failed"] += 1
            elif result is not None or (progress or {}).get("status") == "complete":
                progress_counts["complete"] += 1
            elif instrument_id not in covered_instruments:
                progress_counts["pending"] += 1
        coverage_percent = (
            round((covered_count / len(instrument_ids)) * 100, 2) if instrument_ids else 0.0
        )
        timeframe_statuses.append(
            {
                "timeframe": timeframe.value,
                "member_count": len(instrument_ids),
                "covered_member_count": covered_count,
                "coverage_percent": coverage_percent,
                "analysis_ready_member_count": analysis_ready_count,
                "analysis_ready_percent": (
                    round((analysis_ready_count / len(instrument_ids)) * 100, 2)
                    if instrument_ids
                    else 0.0
                ),
                "required_bar_count": ANALYSIS_REQUIRED_BAR_COUNTS.get(timeframe.value),
                "bar_count": int(row.bar_count) if row is not None else 0,
                "oldest": row.oldest if row is not None else None,
                "newest": row.newest if row is not None else None,
                **{f"{key}_count": value for key, value in progress_counts.items()},
            }
        )

    source = plan["sources"][0]
    if not instrument_ids:
        # A canonical index/ETF/group identity can be known before its local
        # membership snapshot is hydrated. Preserve that pending state rather
        # than presenting the same selectable source as unavailable. Empty
        # personal lists and genuinely unverified sources remain unavailable.
        overall_status = "pending" if source.get("status") == "pending" else "unavailable"
    elif all(item["covered_member_count"] == len(instrument_ids) for item in timeframe_statuses):
        overall_status = "ready"
    elif any(item["in_progress_count"] for item in timeframe_statuses):
        overall_status = "fetching"
    elif any(item["failed_count"] for item in timeframe_statuses):
        overall_status = "failed"
    elif any(item["covered_member_count"] for item in timeframe_statuses):
        overall_status = "partial"
    else:
        overall_status = "pending"

    return {
        "source_id": source_id,
        "source_kind": source.get("source_kind"),
        "name": source.get("name") or source_id,
        "locked": bool(source.get("locked")),
        "membership_version": source.get("membership_version"),
        "as_of": as_of,
        "max_instruments": max_instruments,
        "available_instrument_count": plan["available_instrument_count"],
        "selected_instrument_count": plan["selected_instrument_count"],
        "limited": plan["limited"],
        "excluded_count": source.get("excluded_count", 0),
        "overall_status": overall_status,
        "timeframes": timeframe_statuses,
        "message": source.get("message"),
    }
