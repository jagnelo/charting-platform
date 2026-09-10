"""Bounded history hydration planning for canonical watchlist sources.

Interactive workstation tools consume local canonical bars.  This module owns
the explicit maintenance boundary used to hydrate those bars for any source
that the requesting user can resolve.  It deliberately only resolves local
membership and returns a queueable plan; provider calls remain inside the
existing isolated bulk-history worker.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_observation import InstrumentDatasetState
from app.services.member_dispositions import MEMBER_DISPOSITION_KEYS, member_disposition_counts
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


def adjustment_provenance_for_lineage(
    provider_member_count: int, derived_member_count: int
) -> dict[str, object]:
    """Return explicit adjustment lineage without inventing provider factors."""

    if provider_member_count and derived_member_count:
        source_kind = "mixed_provider_and_derived"
        factor_status = "mixed_provider_native_opaque_and_inherited_from_canonical_d1"
    elif provider_member_count:
        source_kind = "provider_observation"
        factor_status = "provider_native_opaque"
    elif derived_member_count:
        source_kind = "derived_from_canonical_d1"
        factor_status = "inherited_from_canonical_d1"
    else:
        source_kind = "unavailable"
        factor_status = "not_observed"
    return {
        "mode": "split_adjusted",
        "source_kind": source_kind,
        "factor_status": factor_status,
        "factor_version": None,
        "contract_version": 1,
    }


def _as_utc(value: datetime) -> datetime:
    """Normalize persisted or caller timestamps before point-in-time checks."""

    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.astimezone(UTC)


def state_factor_evidence(
    lineage_rows: list[dict[str, Any]],
    state_rows: list[tuple[Any, ...]],
    timeframe_key: str,
    *,
    as_of: datetime | None = None,
) -> dict[str, object] | None:
    """Summarize durable factor evidence for covered members.

    A family-level factor version is meaningful only when every observed
    provider/derived leg for every covered member points at a dataset state
    with one rebuildable version.  The helper deliberately returns ``None``
    when no state rows are available so legacy fixtures and older datasets
    retain the pre-existing opaque contract.
    """

    if not state_rows or not lineage_rows:
        return None

    states: dict[tuple[int, int | None, str], tuple[str | None, str]] = {}
    cutoff = _as_utc(as_of) if as_of is not None else None
    for row in state_rows:
        if len(row) < 4:
            continue
        instrument_id, data_source_id, dataset_key, extra_data = row[:4]
        if cutoff is not None and len(row) >= 6:
            coverage_end, fetched_at = row[4], row[5]
            # Dataset state is a point-in-time claim, not just a current cache
            # label. A state fetched after the requested historical cutoff, or
            # whose covered range extends beyond it, cannot certify that dated
            # slice. Treat it as absent so the caller reports unavailable
            # evidence rather than projecting future provenance backwards.
            if (
                coverage_end is None
                or fetched_at is None
                or _as_utc(coverage_end) > cutoff
                or _as_utc(fetched_at) > cutoff
            ):
                continue
        valid_dataset_keys = {f"{timeframe_key}:adj"}
        if timeframe_key == Timeframe.D1.value:
            valid_dataset_keys.update(
                {
                    "D1:adj:local_split_ratio",
                    "D1:adj:provider_adjustment_factor",
                }
            )
        if dataset_key not in valid_dataset_keys:
            continue
        if not isinstance(instrument_id, int):
            continue
        provenance = (
            extra_data.get("adjustment_provenance") if isinstance(extra_data, dict) else None
        )
        if not isinstance(provenance, dict):
            states[(instrument_id, data_source_id, dataset_key)] = (None, "not_observed")
            continue
        version = provenance.get("factor_version")
        status = str(provenance.get("factor_status") or "not_observed")
        states[(instrument_id, data_source_id, dataset_key)] = (
            version.strip() if isinstance(version, str) and version.strip() else None,
            status,
        )

    if not states:
        return None

    rebuildable_statuses = {
        "rebuildable_split_factors",
        "rebuildable_provider_factors",
    }
    versioned_count = 0
    opaque_count = 0
    unavailable_count = 0
    versions: set[str] = set()
    statuses: set[str] = set()
    covered_count = 0

    for member in lineage_rows:
        instrument_id = int(member["instrument_id"])
        source_ids = set(member.get("provider_source_ids") or ())
        if member.get("derived_bar_count", 0) > 0:
            source_ids.add(None)
        if not source_ids:
            continue
        covered_count += 1
        member_evidence: list[tuple[str | None, str] | None] = []
        derived_methods = {
            str(method) for method in (member.get("derived_methods") or ()) if method
        }
        for source_id in source_ids:
            dataset_keys = [f"{timeframe_key}:adj"]
            if source_id is None and timeframe_key == Timeframe.D1.value and derived_methods:
                dataset_keys = [f"D1:adj:{method}" for method in sorted(derived_methods)]
            member_evidence.extend(
                states.get((instrument_id, source_id, dataset_key)) for dataset_key in dataset_keys
            )
        if any(item is None for item in member_evidence):
            unavailable_count += 1
            continue
        member_versions = {item[0] for item in member_evidence if item[0]}
        member_statuses = {item[1] for item in member_evidence}
        if len(member_versions) == 1 and all(
            item[0] is not None and item[1] in rebuildable_statuses for item in member_evidence
        ):
            versioned_count += 1
            versions.update(member_versions)
            statuses.update(member_statuses)
        elif len(member_versions) == 1 and all(
            item[0] is not None and item[1] == "inherited_from_canonical_d1"
            for item in member_evidence
        ):
            # Derived W1/MN states carry a verified canonical D1 version but
            # retain their lineage label rather than pretending to be a
            # provider state.
            versioned_count += 1
            versions.update(member_versions)
            statuses.update(member_statuses)
        else:
            opaque_count += 1

    if not covered_count:
        return None
    evidence: dict[str, object] = {
        "factor_versioned_member_count": versioned_count,
        "factor_opaque_member_count": opaque_count,
        "factor_unavailable_member_count": unavailable_count,
    }
    if versioned_count == covered_count and len(versions) == 1:
        evidence["factor_version"] = next(iter(versions))
        if "rebuildable_provider_factors" in statuses:
            evidence["factor_status"] = "rebuildable_provider_factors"
        elif "rebuildable_split_factors" in statuses:
            evidence["factor_status"] = "rebuildable_split_factors"
        else:
            evidence["factor_status"] = "inherited_from_canonical_d1"
    elif versioned_count:
        evidence["factor_status"] = "partially_rebuildable"
    return evidence


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
                    "member_disposition": dict.fromkeys(MEMBER_DISPOSITION_KEYS, 0),
                    "membership_version": None,
                    "effective_at": None,
                    "known_at": None,
                    "timing_provenance": {},
                    "published_at": None,
                    "cadence": None,
                    "parser_version": None,
                    "source_identifier": None,
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
        timing_provenance = provenance.get("timing_provenance")
        if not isinstance(timing_provenance, dict):
            timing_provenance = provenance.get("snapshot_timing_provenance")
        if not isinstance(timing_provenance, dict):
            timing_provenance = {}
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
                "member_disposition": member_disposition_counts(
                    members, resolved.descriptor, list(resolved.exclusions)
                ),
                "membership_version": resolved.descriptor.membership_version,
                "effective_at": getattr(resolved.descriptor, "effective_at", None),
                "known_at": getattr(resolved.descriptor, "known_at", None),
                "timing_provenance": timing_provenance,
                "published_at": provenance.get("snapshot_published_at"),
                "cadence": provenance.get("snapshot_cadence"),
                "parser_version": provenance.get("snapshot_parser_version"),
                "source_identifier": provenance.get("snapshot_source_identifier"),
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
                    OHLCVBar.is_derived,
                    OHLCVBar.data_source_id,
                    OHLCVBar.derivation_method,
                )
                .where(
                    OHLCVBar.instrument_id.in_(instrument_ids),
                    OHLCVBar.timeframe.in_(normalized_timeframes),
                    OHLCVBar.is_adjusted.is_(True),
                    *([OHLCVBar.ts <= as_of] if as_of is not None else []),
                )
                .group_by(
                    OHLCVBar.instrument_id,
                    OHLCVBar.timeframe,
                    OHLCVBar.is_derived,
                    OHLCVBar.data_source_id,
                    OHLCVBar.derivation_method,
                )
            )
        ).all()
        if instrument_ids
        else []
    )
    covered_instruments_by_timeframe: dict[str, set[int]] = {}
    analysis_ready_instruments_by_timeframe: dict[str, set[int]] = {}
    lineage_by_timeframe: dict[str, dict[int, dict[str, Any]]] = {}
    for row in covered_rows:
        # Keep compatibility with lightweight test doubles and older callers
        # that return the pre-floor two-column shape. Production SQL returns
        # the grouped count and lineage needed for analysis readiness.
        instrument_id, timeframe = row[0], row[1]
        timeframe_key = timeframe.value
        covered_instruments_by_timeframe.setdefault(timeframe_key, set()).add(instrument_id)
        bar_count = int(row[2]) if len(row) > 2 and row[2] is not None else 0
        member = lineage_by_timeframe.setdefault(timeframe_key, {}).setdefault(
            int(instrument_id),
            {
                "instrument_id": int(instrument_id),
                "bar_count": 0,
                "provider_bar_count": 0,
                "derived_bar_count": 0,
                "provider_source_ids": set(),
                "derived_methods": set(),
            },
        )
        member["bar_count"] += bar_count
        is_derived = bool(row[3]) if len(row) > 3 else False
        member["derived_bar_count" if is_derived else "provider_bar_count"] += bar_count
        if not is_derived and len(row) > 4 and row[4] is not None:
            member["provider_source_ids"].add(int(row[4]))
        if is_derived and len(row) > 5 and row[5]:
            member["derived_methods"].add(str(row[5]))

    # Dataset state is the authoritative source for adjustment-factor
    # provenance. Restrict provider states to source IDs actually represented
    # by the covered bars and include null-source derived states only when a
    # derived bar is present. Older fixtures may return the pre-state query
    # shape; the evidence helper safely ignores those rows.
    provider_source_ids = {
        source_id
        for members in lineage_by_timeframe.values()
        for member in members.values()
        for source_id in member.get("provider_source_ids", set())
    }
    has_derived_rows = any(
        member.get("derived_bar_count", 0) > 0
        for members in lineage_by_timeframe.values()
        for member in members.values()
    )
    state_rows: list[tuple[Any, ...]] = []
    if instrument_ids and (provider_source_ids or has_derived_rows):
        state_filters = [InstrumentDatasetState.data_source_id.is_(None)]
        if provider_source_ids:
            state_filters.append(InstrumentDatasetState.data_source_id.in_(provider_source_ids))
        state_dataset_keys = [f"{timeframe.value}:adj" for timeframe in normalized_timeframes]
        if Timeframe.D1.value in normalized_timeframes:
            state_dataset_keys.extend(
                [
                    "D1:adj:local_split_ratio",
                    "D1:adj:provider_adjustment_factor",
                ]
            )
        state_rows = (
            await db.execute(
                select(
                    InstrumentDatasetState.instrument_id,
                    InstrumentDatasetState.data_source_id,
                    InstrumentDatasetState.dataset_key,
                    InstrumentDatasetState.extra_data,
                    InstrumentDatasetState.coverage_end,
                    InstrumentDatasetState.fetched_at,
                ).where(
                    InstrumentDatasetState.instrument_id.in_(instrument_ids),
                    InstrumentDatasetState.dataset_type == "ohlcv",
                    or_(*state_filters),
                    InstrumentDatasetState.dataset_key.in_(state_dataset_keys),
                )
            )
        ).all()
    for timeframe_key, members in lineage_by_timeframe.items():
        required = ANALYSIS_REQUIRED_BAR_COUNTS.get(timeframe_key)
        if required is None:
            continue
        analysis_ready_instruments_by_timeframe[timeframe_key] = {
            instrument_id
            for instrument_id, member in members.items()
            if member["bar_count"] >= required
        }
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
        lineage_rows = list(lineage_by_timeframe.get(timeframe.value, {}).values())
        provider_member_count = sum(1 for item in lineage_rows if item["provider_bar_count"] > 0)
        derived_member_count = sum(1 for item in lineage_rows if item["derived_bar_count"] > 0)
        provider_only_member_count = sum(
            1
            for item in lineage_rows
            if item["provider_bar_count"] > 0 and item["derived_bar_count"] == 0
        )
        derived_only_member_count = sum(
            1
            for item in lineage_rows
            if item["derived_bar_count"] > 0 and item["provider_bar_count"] == 0
        )
        mixed_member_count = sum(
            1
            for item in lineage_rows
            if item["provider_bar_count"] > 0 and item["derived_bar_count"] > 0
        )
        provider_bar_count = sum(item["provider_bar_count"] for item in lineage_rows)
        derived_bar_count = sum(item["derived_bar_count"] for item in lineage_rows)
        source_lineage = (
            "provider_and_derived"
            if provider_member_count and derived_member_count
            else "provider_only"
            if provider_member_count
            else "derived_only"
            if derived_member_count
            else "unavailable"
        )
        adjustment_provenance = adjustment_provenance_for_lineage(
            provider_member_count, derived_member_count
        )
        factor_evidence = state_factor_evidence(
            lineage_rows,
            state_rows,
            timeframe.value,
            as_of=as_of,
        )
        if factor_evidence:
            adjustment_provenance.update(factor_evidence)
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
                "provider_member_count": provider_member_count,
                "derived_member_count": derived_member_count,
                "provider_only_member_count": provider_only_member_count,
                "derived_only_member_count": derived_only_member_count,
                "mixed_member_count": mixed_member_count,
                "provider_bar_count": provider_bar_count,
                "derived_bar_count": derived_bar_count,
                "source_lineage": source_lineage,
                "adjustment_provenance": adjustment_provenance,
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

    # Keep the historical ``overall_status`` semantics stable for existing
    # callers, while exposing an independent aggregate that applies the
    # declared D1/W1/MN technical-history floors.  This is deliberately based
    # on every requested timeframe: daily readiness cannot hide an empty
    # weekly/monthly leg.
    if not instrument_ids:
        analysis_ready = False
        analysis_ready_status = "pending" if source.get("status") == "pending" else "unavailable"
    elif all(
        item["analysis_ready_member_count"] == len(instrument_ids) for item in timeframe_statuses
    ):
        analysis_ready = True
        analysis_ready_status = "ready"
    elif any(item["analysis_ready_member_count"] for item in timeframe_statuses):
        analysis_ready = False
        analysis_ready_status = "partial"
    else:
        analysis_ready = False
        analysis_ready_status = "pending"

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
        "member_disposition": source.get(
            "member_disposition", dict.fromkeys(MEMBER_DISPOSITION_KEYS, 0)
        ),
        "effective_at": source.get("effective_at"),
        "known_at": source.get("known_at"),
        "timing_provenance": source.get("timing_provenance", {}),
        "published_at": source.get("published_at"),
        "cadence": source.get("cadence"),
        "parser_version": source.get("parser_version"),
        "source_identifier": source.get("source_identifier"),
        "overall_status": overall_status,
        "analysis_ready": analysis_ready,
        "analysis_ready_status": analysis_ready_status,
        "timeframes": timeframe_statuses,
        "message": source.get("message"),
    }
