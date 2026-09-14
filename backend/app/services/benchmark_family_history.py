"""Bounded maintenance planning for benchmark-family constituent history.

Locked benchmark-family sources are the canonical membership contract used by the
workstation.  This module deliberately keeps history hydration separate from
interactive source resolution: it plans against local membership, then queues the
existing provider-neutral bulk-fetch task for each canonical instrument.  No provider
is contacted while building a Market Map, breadth view, or watchlist response.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.lib.time_utils import wire_datetime
from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
from app.models.instrument import Instrument
from app.models.ohlcv import Timeframe
from app.services.benchmark_family_coverage import (
    assess_observed_holdings_cadence,
    assess_observed_holdings_continuity,
)
from app.services.etf_holdings import (
    is_equity_holding_type,
    is_placeholder_symbol,
    normalize_holding_type,
)
from app.services.member_dispositions import MEMBER_DISPOSITION_KEYS, member_disposition_counts
from app.services.top_down_taxonomy import BENCHMARK_FAMILY_REGISTRY
from app.services.watchlist_sources import (
    PENDING_SOURCE_AVAILABILITIES,
    resolve_watchlist_source,
)

DEFAULT_HISTORY_TIMEFRAMES = (Timeframe.MN.value, Timeframe.W1.value, Timeframe.D1.value)
MAX_HISTORY_INSTRUMENTS = 5000
MAX_HISTORY_SNAPSHOTS = 512
BENCHMARK_FAMILY_ROLES = ("cap_weight", "equal_weight", "value", "growth")


def history_end_for_date(value: date) -> datetime:
    """Return the inclusive UTC history bound for a dated composition."""

    return datetime.combine(value, time.max, tzinfo=UTC)


def history_end_iso(end: datetime | None) -> str | None:
    """Return a stable UTC ISO representation for a history queue bound."""

    return wire_datetime(end)


def canonical_history_job_id(
    instrument_id: int,
    timeframes: list[str],
    end: datetime | None = None,
) -> str:
    """Return the shared idempotence key for every canonical history request."""

    # Timeframe order is a request-detail, not part of the history identity.
    # Normalize the key so retries from callers with a different ordering
    # cannot enqueue duplicate provider work for the same instrument/bound.
    timeframe_order = {timeframe.value: index for index, timeframe in enumerate(Timeframe)}
    canonical_timeframes = sorted(
        {str(value).strip().upper() for value in timeframes if str(value).strip()},
        key=lambda value: (timeframe_order.get(value, len(timeframe_order)), value),
    )
    end_key = ""
    if end is not None:
        end_key = f":end={history_end_iso(end)}"
    return (
        f"watchlist-source-history:{int(instrument_id)}:{','.join(canonical_timeframes)}{end_key}"
    )


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


async def plan_benchmark_family_snapshot_history_refresh(
    db: AsyncSession,
    *,
    family_keys: list[str] | None = None,
    roles: list[str] | None = None,
    max_snapshots: int = MAX_HISTORY_SNAPSHOTS,
) -> dict[str, Any]:
    """Plan bounded member-history hydration for already persisted disclosures.

    The normal dated refresh path queues member bars for snapshots it creates. A
    deployment may already contain older canonical disclosures, however, and
    those rows must be queued independently of a new provider fetch. This
    planner is deliberately local-only: it selects persisted family snapshots
    with at least one canonical resolved equity row and leaves provider work to
    the existing per-instrument worker. Metadata-only and non-equity-only
    snapshots cannot produce queueable member history and therefore remain out
    of the plan.
    """

    if max_snapshots < 1 or max_snapshots > MAX_HISTORY_SNAPSHOTS:
        raise ValueError(f"max_snapshots must be between 1 and {MAX_HISTORY_SNAPSHOTS}.")

    normalized_families = normalize_family_keys(family_keys)
    normalized_roles = normalize_family_roles(roles)
    symbol_roles: dict[str, list[tuple[str, str]]] = {}
    for family in BENCHMARK_FAMILY_REGISTRY:
        family_key = str(family.get("logical_key") or "").strip().lower()
        if family_key not in normalized_families:
            continue
        for role in normalized_roles:
            mapping = family.get(role)
            if not isinstance(mapping, dict) or not mapping.get("symbol"):
                continue
            symbol = str(mapping["symbol"]).strip().upper()
            symbol_roles.setdefault(symbol, []).append((family_key, role))

    if not symbol_roles:
        return {
            "family_keys": normalized_families,
            "roles": normalized_roles,
            "max_snapshots": max_snapshots,
            "snapshots": [],
            "selected_snapshot_count": 0,
            "limited": False,
            "continuity_by_symbol": {},
            "undated_snapshot_count": 0,
        }

    snapshot_instrument = aliased(Instrument)
    canonical_member = exists(
        select(1)
        .select_from(ETFHolding)
        .join(snapshot_instrument, snapshot_instrument.id == ETFHolding.constituent_instrument_id)
        .where(
            ETFHolding.snapshot_id == ETFHoldingsSnapshot.id,
            func.lower(func.trim(ETFHolding.row_type)) == "security",
            func.lower(func.trim(ETFHolding.holding_type)).in_(
                (
                    "equity",
                    "stock",
                    "common stock",
                    "common_stock",
                    "real estate investment trust",
                    "real_estate_investment_trust",
                )
            ),
            ETFHolding.is_resolved.is_(True),
            ETFHolding.constituent_instrument_id.is_not(None),
            snapshot_instrument.symbol.is_not(None),
            ~func.upper(func.trim(snapshot_instrument.symbol)).like("HOLDING-%"),
        )
    )
    rows = (
        await db.execute(
            select(
                ETFHoldingsSnapshot.id,
                ETFHoldingsSnapshot.composition_date,
                ETFHoldingsSnapshot.resolved_count,
                Instrument.symbol,
                ETFHoldingsSnapshot.as_of_date,
                ETFHoldingsSnapshot.known_at,
                ETFHoldingsSnapshot.published_at,
                ETFHoldingsSnapshot.provenance,
                ETFHoldingsSnapshot.source_provider,
                ETFHoldingsSnapshot.source_identifier,
                ETFHoldingsSnapshot.source_quality,
                ETFHoldingsSnapshot.completeness_status,
                ETFHoldingsSnapshot.row_count,
                ETFHoldingsSnapshot.unresolved_count,
                ETFHoldingsSnapshot.parser_version,
                ETFHoldingsSnapshot.snapshot_hash,
            )
            .join(ETFProfile, ETFProfile.id == ETFHoldingsSnapshot.etf_profile_id)
            .join(Instrument, Instrument.id == ETFProfile.instrument_id)
            .where(
                Instrument.symbol.in_(tuple(symbol_roles)),
                canonical_member,
                ETFHoldingsSnapshot.provenance != "controlled_fixture",
                ETFHoldingsSnapshot.source_provider != "e2e_reference",
            )
            .order_by(
                ETFHoldingsSnapshot.composition_date.desc(),
                ETFHoldingsSnapshot.known_at.desc().nullslast(),
                ETFHoldingsSnapshot.id.desc(),
            )
        )
    ).all()
    snapshots: list[dict[str, Any]] = []
    undated_snapshot_count = 0
    seen_ids: set[int] = set()
    seen_effective_dates: set[tuple[str, date]] = set()
    observed_dates_by_symbol: dict[str, set[date]] = {}
    for row in rows:
        snapshot_id, composition_date, resolved_count, symbol = row[:4]
        normalized_symbol = str(symbol).strip().upper()
        if not isinstance(composition_date, date):
            # History bounds are derived from the publisher-declared
            # composition date. Legacy undated snapshots remain visible to
            # other audit/readiness paths but cannot safely enter backfill.
            undated_snapshot_count += 1
            continue
        observed_dates_by_symbol.setdefault(normalized_symbol, set()).add(composition_date)
        canonical_id = int(snapshot_id)
        # A corrected issuer disclosure can produce multiple persisted rows for
        # one effective composition date.  The query is ordered by
        # known_at/id descending, so retain the latest-known revision for the
        # maintenance plan.  The source history and audit rows remain intact;
        # only redundant queue work and snapshot-cap consumption are removed.
        effective_key = (normalized_symbol, composition_date)
        if canonical_id in seen_ids or effective_key in seen_effective_dates:
            continue
        seen_ids.add(canonical_id)
        seen_effective_dates.add(effective_key)
        snapshot = {
            "snapshot_id": canonical_id,
            "symbol": normalized_symbol,
            "composition_date": composition_date,
            "resolved_count": int(resolved_count or 0),
            "legs": [
                {"family_key": family_key, "role": role}
                for family_key, role in symbol_roles.get(normalized_symbol, [])
            ],
        }
        # Keep maintenance plans auditable without making older lightweight
        # query doubles (or legacy callers) provide the optional columns.
        provenance_fields = (
            "as_of_date",
            "known_at",
            "published_at",
            "provenance",
            "source_provider",
            "source_identifier",
            "source_quality",
            "completeness_status",
            "row_count",
            "unresolved_count",
            "parser_version",
            "snapshot_hash",
        )
        for index, field in enumerate(provenance_fields, start=4):
            snapshot[field] = row[index] if len(row) > index else None
        snapshots.append(snapshot)
    continuity_by_symbol: dict[str, dict[str, Any]] = {}
    for symbol, composition_dates in observed_dates_by_symbol.items():
        continuity = assess_observed_holdings_continuity(composition_dates)
        cadence = assess_observed_holdings_cadence(composition_dates)
        continuity_by_symbol[symbol] = {
            "status": continuity.status,
            "gap_count": len(continuity.gaps),
            "max_interval_days": continuity.max_interval_days,
            "gaps": [
                {
                    "from_date": gap.from_date,
                    "to_date": gap.to_date,
                    "interval_days": gap.interval_days,
                }
                for gap in continuity.gaps
            ],
            "cadence_status": cadence.status,
            "cadence_sample_count": cadence.sample_count,
            "cadence_median_interval_days": cadence.median_interval_days,
            "cadence_min_interval_days": cadence.min_interval_days,
            "cadence_max_interval_days": cadence.max_interval_days,
        }
    for snapshot in snapshots:
        snapshot["continuity"] = continuity_by_symbol.get(snapshot["symbol"], {})
    limited = len(snapshots) > max_snapshots
    selected = snapshots[:max_snapshots]
    return {
        "family_keys": normalized_families,
        "roles": normalized_roles,
        "max_snapshots": max_snapshots,
        "snapshots": selected,
        "available_snapshot_count": len(snapshots),
        "selected_snapshot_count": len(selected),
        "limited": limited,
        "continuity_by_symbol": continuity_by_symbol,
        "undated_snapshot_count": undated_snapshot_count,
    }


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
            family = next(
                family
                for family in BENCHMARK_FAMILY_REGISTRY
                if family.get("logical_key") == family_key
            )
            mapping = family.get(role) if isinstance(family.get(role), dict) else {}
            history_route = mapping.get("history_route")
            history_route = history_route if isinstance(history_route, dict) else {}
            route_evidence = {
                "history_route_status": str(history_route.get("status") or "not_reported"),
                "history_route_provider": (
                    str(history_route.get("provider")) if history_route.get("provider") else None
                ),
                "history_route_policy": (
                    str(history_route.get("policy")) if history_route.get("policy") else None
                ),
                "history_route_source_url": (
                    str(history_route.get("source_url"))
                    if history_route.get("source_url")
                    else None
                ),
            }
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
                        "member_disposition": dict.fromkeys(MEMBER_DISPOSITION_KEYS, 0),
                        **route_evidence,
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
            leg_status = (
                "ready"
                if available
                else ("pending" if availability in PENDING_SOURCE_AVAILABILITIES else "unavailable")
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
                    "member_disposition": member_disposition_counts(
                        members, resolved.descriptor, resolved.exclusions
                    ),
                    "membership_version": resolved.descriptor.membership_version,
                    **route_evidence,
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
    normalized_snapshots = list(
        dict.fromkeys(int(value) for value in snapshot_ids if int(value) > 0)
    )
    if not normalized_snapshots:
        return {
            "status": "no_snapshots",
            "snapshot_ids": [],
            "available_instrument_count": 0,
            "selected_instrument_count": 0,
            "limited": False,
            "queued": 0,
            "already_queued": 0,
            "queue_errors": [],
            "queue_error_count": 0,
            "unresolved_count": 0,
            "timeframes": normalized_timeframes,
            "history_end": history_end_iso(end),
        }

    rows = (
        await db.execute(
            select(
                ETFHolding.snapshot_id,
                ETFHolding.constituent_instrument_id,
                ETFHolding.row_type,
                ETFHolding.holding_type,
                ETFHolding.is_resolved,
                Instrument.symbol,
            )
            .outerjoin(Instrument, Instrument.id == ETFHolding.constituent_instrument_id)
            .where(ETFHolding.snapshot_id.in_(normalized_snapshots))
            .order_by(ETFHolding.snapshot_id, ETFHolding.position)
        )
    ).all()
    instrument_ids: list[int] = []
    seen: set[int] = set()
    unresolved_count = 0
    for row in rows:
        _snapshot_id, instrument_id, row_type, holding_type, is_resolved = row[:5]
        symbol = row[5] if len(row) > 5 else None
        if (
            normalize_holding_type(row_type) != "security"
            or not is_equity_holding_type(holding_type)
            or not is_resolved
            or instrument_id is None
            or is_placeholder_symbol(symbol)
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
            "queue_errors": [],
            "queue_error_count": 0,
            "unresolved_count": unresolved_count,
            "timeframes": normalized_timeframes,
            "history_end": history_end_iso(end),
        }

    queued = already_queued = 0
    queue_errors: list[dict[str, str | int]] = []
    normalized_end = history_end_iso(end)
    for instrument_id in selected_ids:
        job_args = ["task_bulk_fetch_instrument", instrument_id, normalized_timeframes]
        if normalized_end is not None:
            job_args.extend([None, normalized_end])
        try:
            job = await redis.enqueue_job(
                *job_args,
                _job_id=canonical_history_job_id(instrument_id, normalized_timeframes, end),
            )
        except Exception as exc:  # noqa: BLE001 - retain per-member queue evidence.
            queue_errors.append(
                {
                    "status": "queue_error",
                    "instrument_id": instrument_id,
                    "error": str(exc)[:500] or "Canonical history queue failed.",
                }
            )
            continue
        if job is None:
            already_queued += 1
        else:
            queued += 1
    return {
        "status": "queue_error" if queue_errors else "queued",
        "snapshot_ids": normalized_snapshots,
        "available_instrument_count": len(instrument_ids),
        "selected_instrument_count": len(selected_ids),
        "limited": len(instrument_ids) > max_instruments,
        "queued": queued,
        "already_queued": already_queued,
        "queue_errors": queue_errors,
        "queue_error_count": len(queue_errors),
        "unresolved_count": unresolved_count,
        "timeframes": normalized_timeframes,
        "history_end": history_end_iso(end),
    }
