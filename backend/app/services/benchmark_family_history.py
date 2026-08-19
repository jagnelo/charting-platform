"""Bounded maintenance planning for benchmark-family constituent history.

Locked benchmark-family sources are the canonical membership contract used by the
workstation.  This module deliberately keeps history hydration separate from
interactive source resolution: it plans against local membership, then queues the
existing provider-neutral bulk-fetch task for each canonical instrument.  No provider
is contacted while building a Market Map, breadth view, or watchlist response.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.etf_holdings import ETFHolding
from app.models.ohlcv import Timeframe
from app.services.top_down_taxonomy import BENCHMARK_FAMILY_REGISTRY
from app.services.watchlist_sources import (
    PENDING_SOURCE_AVAILABILITIES,
    resolve_watchlist_source,
)

DEFAULT_HISTORY_TIMEFRAMES = (Timeframe.MN.value, Timeframe.W1.value, Timeframe.D1.value)
MAX_HISTORY_INSTRUMENTS = 5000
BENCHMARK_FAMILY_ROLES = ("cap_weight", "equal_weight", "value", "growth")


def canonical_history_job_id(
    instrument_id: int,
    timeframes: list[str],
    end: datetime | None = None,
) -> str:
    """Return the shared idempotence key for every canonical history request."""

    end_key = ""
    if end is not None:
        normalized = end if end.tzinfo is not None else end.replace(tzinfo=UTC)
        end_key = f":end={normalized.astimezone(UTC).isoformat()}"
    return f"watchlist-source-history:{int(instrument_id)}:{','.join(timeframes)}{end_key}"


def normalize_family_keys(family_keys: list[str] | None) -> list[str]:
    """Return registry order and reject unknown roots rather than silently dropping them."""

    available = [
        str(item.get("logical_key", "")).strip().lower()
        for item in BENCHMARK_FAMILY_REGISTRY
        if item.get("logical_key")
    ]
    requested = {str(value).strip().lower() for value in (family_keys or []) if str(value).strip()}
    unknown = sorted(requested - set(available))
    if unknown:
        raise ValueError(f"Unknown benchmark family key(s): {', '.join(unknown)}.")
    return [key for key in available if not requested or key in requested]


def normalize_family_roles(roles: list[str] | None) -> list[str]:
    """Normalize role selection while preserving the stable role matrix order."""

    requested = {str(value).strip().lower() for value in (roles or []) if str(value).strip()}
    unknown = sorted(requested - set(BENCHMARK_FAMILY_ROLES))
    if unknown:
        raise ValueError(
            f"Unsupported benchmark family role(s): {', '.join(unknown)}. "
            f"Expected one of {', '.join(BENCHMARK_FAMILY_ROLES)}."
        )
    return [role for role in BENCHMARK_FAMILY_ROLES if not requested or role in requested]


def normalize_history_timeframes(timeframes: list[str] | None) -> list[str]:
    """Validate requested bulk-fetch resolutions and keep the request deterministic."""

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


async def plan_benchmark_family_history_refresh(
    db: AsyncSession,
    *,
    family_keys: list[str] | None = None,
    roles: list[str] | None = None,
    as_of: datetime | None = None,
    max_instruments: int = MAX_HISTORY_INSTRUMENTS,
    timeframes: list[str] | None = None,
) -> dict[str, Any]:
    """Resolve local locked membership and return a bounded, queueable plan.

    The resolver is called with a non-user identity because benchmark-family sources
    are system-managed.  Its membership and exclusions are authoritative; an empty
    or unavailable leg is reported, never replaced with another ETF or provider.
    """

    if max_instruments < 1 or max_instruments > MAX_HISTORY_INSTRUMENTS:
        raise ValueError(f"max_instruments must be between 1 and {MAX_HISTORY_INSTRUMENTS}.")

    normalized_families = normalize_family_keys(family_keys)
    normalized_roles = normalize_family_roles(roles)
    normalized_timeframes = normalize_history_timeframes(timeframes)
    instrument_ids: list[int] = []
    seen_instruments: set[int] = set()
    legs: list[dict[str, Any]] = []

    for family_key in normalized_families:
        for role in normalized_roles:
            source_id = f"benchmark-family:{family_key}:{role}"
            try:
                resolved = await resolve_watchlist_source(db, 0, source_id, as_of=as_of)
            except (LookupError, ValueError) as exc:
                legs.append(
                    {
                        "source_id": source_id,
                        "family_key": family_key,
                        "role": role,
                        "status": "unavailable",
                        "member_count": 0,
                        "selected_count": 0,
                        "deduplicated_count": 0,
                        "excluded_count": 0,
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

            available = bool(members)
            descriptor_provenance = getattr(resolved.descriptor, "provenance", {}) or {}
            availability = (
                descriptor_provenance.get("availability")
                if isinstance(descriptor_provenance, dict)
                else None
            )
            # A mapped system source with no local snapshot is still a real
            # locked watchlist. Preserve its pending state for bootstrap and
            # admin progress instead of presenting it as a missing role.
            leg_status = "ready" if available else (
                "pending"
                if availability in PENDING_SOURCE_AVAILABILITIES
                else "unavailable"
            )
            legs.append(
                {
                    "source_id": source_id,
                    "family_key": family_key,
                    "role": role,
                    "status": leg_status,
                    "member_count": len(members),
                    "selected_count": selected_count,
                    "deduplicated_count": len(members) - selected_count,
                    "excluded_count": len(resolved.exclusions),
                    "membership_version": resolved.descriptor.membership_version,
                    "message": (
                        None
                        if available
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
        "family_keys": normalized_families,
        "roles": normalized_roles,
        "timeframes": normalized_timeframes,
        "as_of": as_of,
        "max_instruments": max_instruments,
        "instrument_ids": selected_ids,
        "available_instrument_count": len(instrument_ids),
        "selected_instrument_count": len(selected_ids),
        "limited": limited,
        "legs": legs,
    }


async def queue_snapshot_member_history(
    db: AsyncSession,
    redis,
    snapshot_ids: list[int],
    *,
    timeframes: list[str] | None = None,
    max_instruments: int = MAX_HISTORY_INSTRUMENTS,
    end: datetime | None = None,
) -> dict[str, Any]:
    """Queue canonical history for the exact holdings snapshots just ingested.

    A holdings refresh may target a historical composition date whose ``known_at``
    is now. Resolving the public source with that date as an ``as_of`` value would
    correctly exclude the newly ingested snapshot, so this maintenance handoff
    works from explicit snapshot IDs instead. It never calls a provider and keeps
    the source's point-in-time membership boundary intact.
    """

    normalized_timeframes = normalize_history_timeframes(timeframes)
    if max_instruments < 1 or max_instruments > MAX_HISTORY_INSTRUMENTS:
        raise ValueError(f"max_instruments must be between 1 and {MAX_HISTORY_INSTRUMENTS}.")
    normalized_snapshots = list(dict.fromkeys(int(value) for value in snapshot_ids if int(value) > 0))
    if not normalized_snapshots:
        return {
            "status": "no_snapshots",
            "snapshot_ids": [],
            "available_instrument_count": 0,
            "selected_instrument_count": 0,
            "limited": False,
            "queued": 0,
            "already_queued": 0,
            "unresolved_count": 0,
            "timeframes": normalized_timeframes,
        }

    rows = (
        await db.execute(
            select(
                ETFHolding.snapshot_id,
                ETFHolding.constituent_instrument_id,
                ETFHolding.row_type,
                ETFHolding.holding_type,
                ETFHolding.is_resolved,
            )
            .where(ETFHolding.snapshot_id.in_(normalized_snapshots))
            .order_by(ETFHolding.snapshot_id, ETFHolding.position)
        )
    ).all()
    instrument_ids: list[int] = []
    seen: set[int] = set()
    unresolved_count = 0
    for _snapshot_id, instrument_id, row_type, holding_type, is_resolved in rows:
        if (
            row_type != "security"
            or holding_type not in {"equity", "stock", "common_stock"}
            or not is_resolved
            or instrument_id is None
        ):
            unresolved_count += 1
            continue
        canonical_id = int(instrument_id)
        if canonical_id not in seen:
            seen.add(canonical_id)
            instrument_ids.append(canonical_id)
    selected_ids = instrument_ids[:max_instruments]
    if redis is None:
        return {
            "status": "not_queued",
            "reason": "Redis worker queue unavailable",
            "snapshot_ids": normalized_snapshots,
            "available_instrument_count": len(instrument_ids),
            "selected_instrument_count": len(selected_ids),
            "limited": len(instrument_ids) > max_instruments,
            "queued": 0,
            "already_queued": 0,
            "unresolved_count": unresolved_count,
            "timeframes": normalized_timeframes,
        }

    queued = already_queued = 0
    for instrument_id in selected_ids:
        job_args = ["task_bulk_fetch_instrument", instrument_id, normalized_timeframes]
        if end is not None:
            job_args.extend([None, end.isoformat()])
        job = await redis.enqueue_job(
            *job_args,
            _job_id=canonical_history_job_id(instrument_id, normalized_timeframes, end),
        )
        if job is None:
            already_queued += 1
        else:
            queued += 1
    return {
        "status": "queued",
        "snapshot_ids": normalized_snapshots,
        "available_instrument_count": len(instrument_ids),
        "selected_instrument_count": len(selected_ids),
        "limited": len(instrument_ids) > max_instruments,
        "queued": queued,
        "already_queued": already_queued,
        "unresolved_count": unresolved_count,
        "timeframes": normalized_timeframes,
    }
