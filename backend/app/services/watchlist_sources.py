"""Unified descriptors and resolvers for selectable list universes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import func

from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
from app.models.instrument import Instrument
from app.models.user import User
from app.models.watchlist import Watchlist
from app.models.workstation import MarketGroup, WorkspaceLibraryItem
from app.schemas.watchlist import WatchlistSourceRead


@dataclass(frozen=True)
class ResolvedWatchlistMember:
    instrument_id: int
    position: int
    weight: float | None
    relationship_type: str
    source: str | None
    effective_at: datetime | None
    known_at: datetime | None


@dataclass(frozen=True)
class ResolvedWatchlistSource:
    descriptor: WatchlistSourceRead
    members: tuple[ResolvedWatchlistMember, ...]
    exclusions: tuple[dict, ...] = ()


def _version(prefix: str, identifier: object, effective_at: datetime | None = None) -> str:
    return f"{prefix}:{identifier}:{effective_at.isoformat() if effective_at else 'current'}"


def _membership_digest(items: list[object] | tuple[object, ...]) -> str:
    """Return a stable digest for the membership state, independent of ORM order."""

    payload = [
        {
            "instrument_id": getattr(item, "instrument_id", None),
            "position": getattr(item, "position", None),
            "weight": getattr(item, "weight", None),
            "relationship_type": getattr(item, "relationship_type", None),
            "source": getattr(item, "source", None),
            "verification_state": getattr(item, "verification_state", None),
            "added_at": (
                getattr(item, "added_at", None).isoformat()
                if getattr(item, "added_at", None) is not None
                else None
            ),
            "left_screener_at": (
                getattr(item, "left_screener_at", None).isoformat()
                if getattr(item, "left_screener_at", None) is not None
                else None
            ),
            "effective_at": (
                getattr(item, "effective_at", None).isoformat()
                if getattr(item, "effective_at", None) is not None
                else None
            ),
            "known_at": (
                getattr(item, "known_at", None).isoformat()
                if getattr(item, "known_at", None) is not None
                else None
            ),
        }
        for item in sorted(
            items,
            key=lambda value: (
                getattr(value, "position", 0),
                getattr(value, "instrument_id", 0),
                getattr(value, "id", 0),
            ),
        )
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def _watchlist_membership_version(watchlist: Watchlist | None) -> str:
    if watchlist is None:
        return "missing"
    return f"watchlist:{watchlist.id}:{_membership_digest(watchlist.items)}"


def _watchlist_item_active_at(item: object, as_of: datetime | None) -> bool:
    """Apply the item's known and active interval to a point-in-time lookup."""

    if as_of is None:
        return True
    added_at = getattr(item, "added_at", None)
    left_at = getattr(item, "left_screener_at", None)
    return bool(
        added_at is not None
        and added_at <= as_of
        and (left_at is None or left_at > as_of)
    )


def _watchlist_item_as_of_exclusion(item: object, as_of: datetime | None) -> dict | None:
    if as_of is None or _watchlist_item_active_at(item, as_of):
        return None
    added_at = getattr(item, "added_at", None)
    if added_at is not None and added_at > as_of:
        return {"instrument_id": getattr(item, "instrument_id", None), "reason": "membership_not_known_at_as_of"}
    left_at = getattr(item, "left_screener_at", None)
    if left_at is not None and left_at <= as_of:
        return {
            "instrument_id": getattr(item, "instrument_id", None),
            "reason": "membership_not_active_at_as_of",
            "left_screener_at": left_at.isoformat(),
        }
    return {"instrument_id": getattr(item, "instrument_id", None), "reason": "membership_not_known_at_as_of"}


def _watchlist_descriptor(watchlist: Watchlist) -> WatchlistSourceRead:
    locked = bool(watchlist.is_locked or watchlist.is_managed)
    return WatchlistSourceRead(
        source_id=f"watchlist:{watchlist.id}",
        source_kind="screener_managed" if watchlist.is_managed else "personal",
        name=watchlist.name,
        description=watchlist.description,
        locked=locked,
        can_edit_membership=not locked,
        watchlist_id=watchlist.id,
        membership_version=_watchlist_membership_version(watchlist),
        member_count=len(watchlist.items),
        source="user_watchlist",
        provenance={"watchlist_id": watchlist.id, "screener_id": watchlist.screener_id},
        known_at=watchlist.updated_at,
    )


def _market_group_descriptor(group: MarketGroup) -> WatchlistSourceRead:
    membership_digest = _membership_digest(group.members)
    return WatchlistSourceRead(
        source_id=f"market-group:{group.stable_key}",
        source_kind="index_membership" if group.group_type == "benchmark_family" else "market_group",
        name=group.name,
        description=f"System-managed {group.group_type.replace('_', ' ')} universe",
        locked=True,
        stable_key=group.stable_key,
        membership_version=(
            f"market-group:{group.stable_key}:"
            f"{group.effective_at.isoformat() if group.effective_at else 'current'}:{membership_digest}"
        ),
        member_count=len(group.members),
        source=group.source,
        provenance=dict(group.provenance or {}),
        effective_at=group.effective_at,
        known_at=group.known_at,
    )


_BENCHMARK_FAMILY_ROLES = ("cap_weight", "equal_weight", "value", "growth")


def _benchmark_family_role_selection(
    group: MarketGroup, role: str
) -> tuple[dict[str, object] | None, str | None, bool]:
    """Return the evidenced proxy leg for a family-role source.

    A family leg is a locked watchlist source in its own right.  A missing
    equal-weight ETF may use the explicitly declared point-in-time derived
    equal-weight policy, but no other missing role is inferred from names.
    """

    provenance = group.provenance or {}
    mappings = provenance.get("proxy_mappings")
    if not isinstance(mappings, Mapping):
        return None, None, False
    declared = mappings.get(role)
    if isinstance(declared, Mapping) and declared.get("symbol"):
        return dict(declared), str(declared["symbol"]).upper(), False
    if role != "equal_weight":
        return None, None, False
    derived = provenance.get("derived_equal_weight")
    cap = mappings.get("cap_weight")
    if (
        isinstance(derived, Mapping)
        and bool(derived.get("allowed"))
        and isinstance(cap, Mapping)
        and cap.get("symbol")
    ):
        return dict(cap), str(cap["symbol"]).upper(), True
    return None, None, False


def _benchmark_family_role_descriptor(
    group: MarketGroup,
    role: str,
    *,
    profile: ETFProfile | None = None,
    instrument: Instrument | None = None,
    snapshot: ETFHoldingsSnapshot | None = None,
) -> WatchlistSourceRead:
    declared_mappings = (group.provenance or {}).get("proxy_mappings")
    declared = (
        declared_mappings.get(role)
        if isinstance(declared_mappings, Mapping)
        else None
    )
    declared = dict(declared) if isinstance(declared, Mapping) else {}
    selected, proxy_symbol, derived = _benchmark_family_role_selection(group, role)
    derived_policy = (group.provenance or {}).get("derived_equal_weight") or {}
    role_label = {
        "cap_weight": "Cap weight",
        "equal_weight": "Equal weight",
        "value": "Value",
        "growth": "Growth",
    }.get(role, role.replace("_", " ").title())
    if selected is None:
        availability = "unavailable"
    elif profile is None:
        availability = "profile_not_loaded"
    elif snapshot is None:
        availability = "holdings_snapshot_not_loaded"
    else:
        availability = "available"
    if derived:
        membership_semantics = "derived_equal_weight_point_in_time_membership"
        source = snapshot.source_provider if snapshot is not None else "derived_equal_weight_policy"
        mapping_state = "derived_policy"
    else:
        membership_semantics = "etf_proxy_holdings"
        source = snapshot.source_provider if snapshot is not None else group.source
        mapping_state = declared.get("verification_state")
    mapping_label = declared.get("label") or (selected.get("label") if selected else None)
    snapshot_key = (
        snapshot.snapshot_hash
        or str(snapshot.id)
        if snapshot is not None
        else "unavailable"
    )
    membership_version = _version(
        "benchmark-family",
        f"{group.stable_key}:{role}:{snapshot_key}",
        snapshot.known_at if snapshot is not None else group.known_at,
    )
    composition = snapshot.composition_date if snapshot is not None else None
    return WatchlistSourceRead(
        source_id=f"benchmark-family:{group.stable_key}:{role}",
        source_kind="index_membership",
        name=f"{group.name} — {role_label}",
        description=(
            "Derived equal-weight constituent universe"
            if derived
            else "System-managed benchmark-family constituent universe"
        ),
        locked=True,
        can_edit_membership=False,
        stable_key=group.stable_key,
        instrument_id=instrument.id if instrument is not None else None,
        symbol=proxy_symbol,
        membership_version=membership_version,
        member_count=snapshot.row_count if snapshot is not None else 0,
        source=source,
        provenance={
            "family_key": group.stable_key,
            "role": role,
            "availability": availability,
            "mapping_label": mapping_label,
            "mapping_verification_state": mapping_state,
            "mapping_source_url": declared.get("source_url"),
            "proxy_symbol": proxy_symbol,
            "membership_semantics": membership_semantics,
            "point_in_time": True,
            "derived": derived,
            "derived_method": derived_policy.get("method") if derived else None,
            "snapshot_id": snapshot.id if snapshot is not None else None,
            "snapshot_hash": snapshot.snapshot_hash if snapshot is not None else None,
            "completeness_status": snapshot.completeness_status if snapshot is not None else "not_loaded",
        },
        effective_at=(
            datetime.combine(composition, datetime.min.time()) if composition else group.effective_at
        ),
        known_at=snapshot.known_at if snapshot is not None else group.known_at,
        composition_date=composition.isoformat() if composition else None,
    )


def _etf_descriptor(
    profile: ETFProfile,
    instrument: Instrument,
    snapshot: ETFHoldingsSnapshot | None,
) -> WatchlistSourceRead:
    composition = snapshot.composition_date if snapshot else None
    return WatchlistSourceRead(
        source_id=f"etf-holdings:{instrument.symbol}",
        source_kind="etf_holdings",
        name=f"{instrument.symbol} holdings",
        description="System-managed ETF-proxy holdings universe",
        locked=True,
        instrument_id=instrument.id,
        symbol=instrument.symbol,
        membership_version=_version("etf-holdings", profile.id, snapshot.known_at if snapshot else None),
        member_count=snapshot.row_count if snapshot else 0,
        source=snapshot.source_provider if snapshot else profile.adapter_key,
        provenance={
            "membership_semantics": "etf_proxy_holdings",
            "profile_id": profile.id,
            "snapshot_id": snapshot.id if snapshot else None,
            "snapshot_hash": snapshot.snapshot_hash if snapshot else None,
            "completeness_status": snapshot.completeness_status if snapshot else "not_loaded",
        },
        effective_at=datetime.combine(composition, datetime.min.time()) if composition else None,
        known_at=snapshot.known_at if snapshot else None,
        composition_date=composition.isoformat() if composition else None,
    )


def _combo_dependency_versions(
    watchlists: dict[int, Watchlist], payload: dict,
) -> dict[str, str]:
    referenced_ids = {
        *_combo_ids(payload, "union_watchlist_ids"),
        *_combo_ids(payload, "intersection_watchlist_ids"),
        *_combo_ids(payload, "exclude_watchlist_ids"),
    }
    return {
        str(watchlist_id): _watchlist_membership_version(watchlists.get(watchlist_id))
        for watchlist_id in sorted(referenced_ids)
    }


def _combo_descriptor(
    item: WorkspaceLibraryItem,
    member_count: int,
    dependency_versions: dict[str, str] | None = None,
) -> WatchlistSourceRead:
    """Describe a user-owned derived combo as a read-only membership source.

    The combo definition remains editable through the library editor, but the
    resolved membership is not a mutable watchlist itself.  Treating it as a
    locked derived source keeps maps, breadth, scans, and linked charts on one
    contract while preventing accidental per-member edits.
    """

    definition = {
        "stable_key": item.stable_key,
        "version": item.version,
        "payload": item.payload or {},
        "dependencies": dependency_versions or {},
    }
    encoded = json.dumps(definition, sort_keys=True, separators=(",", ":")).encode()
    membership_version = f"combo:{item.stable_key}:{hashlib.sha256(encoded).hexdigest()[:16]}"
    return WatchlistSourceRead(
        source_id=f"combo:{item.stable_key}",
        source_kind="combo",
        name=item.name,
        description="User-owned derived watchlist (union/intersection/exclusion)",
        locked=True,
        can_edit_membership=False,
        membership_version=membership_version,
        member_count=member_count,
        source="user_combo_definition",
        provenance={
            "library_item_id": item.id,
            "library_item_version": item.version,
            "membership_semantics": "derived_combo_watchlists",
        },
        known_at=item.updated_at,
    )


def _combo_ids(payload: dict, key: str) -> list[int]:
    values = payload.get(key, []) if isinstance(payload, dict) else []
    return list(dict.fromkeys(value for value in values if isinstance(value, int) and value > 0))


def _combo_member_ids(
    watchlists: dict[int, Watchlist], payload: dict, as_of: datetime | None = None
) -> list[int]:
    """Apply the same union/intersection/exclusion semantics as the UI combo list."""

    def member_ids(watchlist_id: int) -> set[int]:
        watchlist = watchlists.get(watchlist_id)
        return {
            item.instrument_id
            for item in (watchlist.items if watchlist else [])
            if _watchlist_item_active_at(item, as_of)
        }

    union_ids = _combo_ids(payload, "union_watchlist_ids")
    intersection_ids = _combo_ids(payload, "intersection_watchlist_ids")
    exclude_ids = _combo_ids(payload, "exclude_watchlist_ids")

    union: set[int]
    if union_ids:
        union = {
            instrument_id
            for watchlist_id in union_ids
            for instrument_id in member_ids(watchlist_id)
        }
    elif intersection_ids:
        union = member_ids(intersection_ids[0])
    else:
        union = set()

    intersection: set[int] | None = None
    for watchlist_id in intersection_ids:
        current = member_ids(watchlist_id)
        intersection = current if intersection is None else intersection & current

    excluded = {
        instrument_id
        for watchlist_id in exclude_ids
        for instrument_id in member_ids(watchlist_id)
    }
    selected = union - excluded
    if intersection is not None:
        selected &= intersection

    # Preserve the first contributing watchlist's position; instrument IDs are
    # the deterministic tie-break for members appearing at the same position.
    ordered: list[tuple[int, int, int]] = []
    for instrument_id in selected:
        candidates = [
            (watchlist.position, item.position, watchlist_id)
            for watchlist_id in [*union_ids, *intersection_ids]
            if (watchlist := watchlists.get(watchlist_id)) is not None
            for item in watchlist.items
            if item.instrument_id == instrument_id and _watchlist_item_active_at(item, as_of)
        ]
        position, item_position, _ = min(candidates) if candidates else (0, 0, 0)
        ordered.append((position, item_position, instrument_id))
    ordered.sort()
    return [instrument_id for _, _, instrument_id in ordered]


def _explicit_instrument_ids(source_id: str) -> list[int]:
    """Parse an ephemeral canonical-ID source without accepting ticker text."""

    raw = source_id.split(":", 1)[1] if ":" in source_id else ""
    tokens = raw.split(",") if raw else []
    if not tokens or len(tokens) > 500:
        raise ValueError("invalid_explicit_source_id")
    try:
        ids = [int(token) for token in tokens]
    except ValueError as exc:
        raise ValueError("invalid_explicit_source_id") from exc
    if any(instrument_id <= 0 for instrument_id in ids):
        raise ValueError("invalid_explicit_source_id")
    return list(dict.fromkeys(ids))


def _explicit_descriptor(instrument_ids: list[int]) -> WatchlistSourceRead:
    membership = ",".join(str(instrument_id) for instrument_id in instrument_ids)
    return WatchlistSourceRead(
        source_id=f"explicit:{membership}",
        source_kind="explicit",
        name=f"Explicit symbols ({len(instrument_ids)})",
        description="Ephemeral canonical-instrument selection; save it as a personal watchlist for durable membership.",
        locked=True,
        can_edit_membership=False,
        membership_version=_version("explicit", membership),
        member_count=len(instrument_ids),
        source="explicit_canonical_selection",
        provenance={
            "membership_semantics": "explicit_canonical_instruments",
            "point_in_time": False,
            "instrument_ids": instrument_ids,
            "durability": "ephemeral_until_saved_as_watchlist",
        },
    )


async def list_watchlist_sources(db: AsyncSession, user: User) -> list[WatchlistSourceRead]:
    """List source descriptors without provider calls or member-level fan-out."""

    watchlists = (
        (
            await db.execute(
                select(Watchlist)
                .where(Watchlist.user_id == user.id)
                .options(selectinload(Watchlist.items))
                .order_by(Watchlist.position, Watchlist.created_at)
            )
        )
        .scalars()
        .all()
    )
    groups = (
        (
            await db.execute(
                select(MarketGroup)
                .options(selectinload(MarketGroup.members))
                .order_by(MarketGroup.group_type, MarketGroup.name)
            )
        )
        .scalars()
        .all()
    )
    profiles = (
        (
            await db.execute(
                select(ETFProfile, Instrument)
                .join(Instrument, Instrument.id == ETFProfile.instrument_id)
                .order_by(Instrument.symbol)
            )
        )
        .all()
    )
    ranked_snapshots = (
        select(
            ETFHoldingsSnapshot.id.label("snapshot_id"),
            func.row_number()
            .over(
                partition_by=ETFHoldingsSnapshot.etf_profile_id,
                order_by=(
                    ETFHoldingsSnapshot.composition_date.desc(),
                    ETFHoldingsSnapshot.id.desc(),
                ),
            )
            .label("row_number"),
        )
        .subquery()
    )
    snapshots = (
        (
            await db.execute(
                select(ETFHoldingsSnapshot).join(
                    ranked_snapshots,
                    ranked_snapshots.c.snapshot_id == ETFHoldingsSnapshot.id,
                ).where(ranked_snapshots.c.row_number == 1)
            )
        )
        .scalars()
        .all()
    )
    latest = {snapshot.etf_profile_id: snapshot for snapshot in snapshots}

    combo_items = (
        (
            await db.execute(
                select(WorkspaceLibraryItem).where(
                    WorkspaceLibraryItem.user_id == user.id,
                    WorkspaceLibraryItem.kind == "combo_list",
                )
            )
        )
        .scalars()
        .all()
    )
    user_watchlists = {
        watchlist.id: watchlist
        for watchlist in watchlists
    }
    profiles_by_symbol = {instrument.symbol.upper(): (profile, instrument) for profile, instrument in profiles}
    sources = [
        *(_watchlist_descriptor(item) for item in watchlists),
        *(_market_group_descriptor(item) for item in groups),
        *(_etf_descriptor(profile, instrument, latest.get(profile.id)) for profile, instrument in profiles),
        *(
            _combo_descriptor(
                item,
                len(_combo_member_ids(user_watchlists, item.payload or {})),
                _combo_dependency_versions(user_watchlists, item.payload or {}),
            )
            for item in combo_items
        ),
    ]
    # A family root remains visible as a locked group, but each evidenced leg
    # is also a first-class source.  This is what lets the generic Market Map,
    # breadth, scan, and gauge surfaces consume ``SPY constituents`` or a
    # derived equal-weight family universe without a feature-specific route.
    for group in groups:
        if group.group_type != "benchmark_family":
            continue
        if not isinstance((group.provenance or {}).get("proxy_mappings"), Mapping):
            continue
        for role in _BENCHMARK_FAMILY_ROLES:
            _selected, proxy_symbol, _derived = _benchmark_family_role_selection(group, role)
            selected_profile, selected_instrument = profiles_by_symbol.get(proxy_symbol, (None, None)) if proxy_symbol else (None, None)
            sources.append(
                _benchmark_family_role_descriptor(
                    group,
                    role,
                    profile=selected_profile,
                    instrument=selected_instrument,
                    snapshot=latest.get(selected_profile.id) if selected_profile is not None else None,
                )
            )
    return sources


async def resolve_watchlist_source(
    db: AsyncSession,
    user_id: int,
    source_id: str,
    *,
    as_of: datetime | None = None,
) -> ResolvedWatchlistSource:
    """Resolve one source into members and explicit historical exclusions."""

    if source_id.startswith("watchlist:"):
        try:
            watchlist_id = int(source_id.split(":", 1)[1])
        except ValueError as exc:
            raise ValueError("invalid_watchlist_source_id") from exc
        watchlist = (
            await db.execute(
                select(Watchlist)
                .where(Watchlist.id == watchlist_id, Watchlist.user_id == user_id)
                .options(selectinload(Watchlist.items))
            )
        ).scalar_one_or_none()
        if watchlist is None:
            raise LookupError("watchlist_source_not_found")
        return ResolvedWatchlistSource(
            descriptor=_watchlist_descriptor(watchlist),
            members=tuple(
                ResolvedWatchlistMember(
                    instrument_id=item.instrument_id,
                    position=item.position,
                    weight=None,
                    relationship_type="watchlist_member",
                    source="user_watchlist",
                    effective_at=item.added_at,
                    known_at=item.added_at,
                )
                for item in watchlist.items
                if _watchlist_item_active_at(item, as_of)
            ),
            exclusions=tuple(
                exclusion
                for item in watchlist.items
                if (exclusion := _watchlist_item_as_of_exclusion(item, as_of)) is not None
            ),
        )

    if source_id.startswith("explicit:"):
        instrument_ids = _explicit_instrument_ids(source_id)
        instruments = (
            await db.execute(select(Instrument).where(Instrument.id.in_(instrument_ids)))
        ).scalars().all()
        by_id = {instrument.id: instrument for instrument in instruments}
        members = tuple(
            ResolvedWatchlistMember(
                instrument_id=instrument_id,
                position=position,
                weight=None,
                relationship_type="explicit_symbol",
                source="explicit_canonical_selection",
                effective_at=None,
                known_at=None,
            )
            for position, instrument_id in enumerate(instrument_ids)
            if instrument_id in by_id
        )
        exclusions = tuple(
            {"instrument_id": instrument_id, "reason": "canonical_instrument_not_found"}
            for instrument_id in instrument_ids
            if instrument_id not in by_id
        )
        return ResolvedWatchlistSource(
            descriptor=_explicit_descriptor(instrument_ids),
            members=members,
            exclusions=exclusions,
        )

    if source_id.startswith("combo:"):
        stable_key = source_id.split(":", 1)[1]
        combo = (
            await db.execute(
                select(WorkspaceLibraryItem).where(
                    WorkspaceLibraryItem.user_id == user_id,
                    WorkspaceLibraryItem.kind == "combo_list",
                    WorkspaceLibraryItem.stable_key == stable_key,
                )
            )
        ).scalar_one_or_none()
        if combo is None:
            raise LookupError("combo_source_not_found")

        payload = combo.payload or {}
        referenced_ids = {
            *_combo_ids(payload, "union_watchlist_ids"),
            *_combo_ids(payload, "intersection_watchlist_ids"),
            *_combo_ids(payload, "exclude_watchlist_ids"),
        }
        referenced = (
            (
                await db.execute(
                    select(Watchlist)
                    .where(Watchlist.user_id == user_id, Watchlist.id.in_(referenced_ids))
                    .options(selectinload(Watchlist.items))
                )
            )
            .scalars()
            .all()
            if referenced_ids
            else []
        )
        watchlists = {watchlist.id: watchlist for watchlist in referenced}
        dependency_versions = _combo_dependency_versions(watchlists, payload)
        selected_ids = _combo_member_ids(watchlists, payload)
        selected_at_as_of = _combo_member_ids(watchlists, payload, as_of=as_of)
        as_of_exclusions: list[dict] = []
        if as_of is not None and combo.updated_at > as_of:
            return ResolvedWatchlistSource(
                descriptor=_combo_descriptor(combo, 0, dependency_versions),
                members=(),
                exclusions=(
                    {
                        "reason": "combo_definition_not_known_at_as_of",
                        "known_at": combo.updated_at.isoformat(),
                    },
                ),
            )
        if as_of is not None:
            for instrument_id in sorted(set(selected_ids) - set(selected_at_as_of)):
                candidates = [
                    item
                    for watchlist in referenced
                    for item in watchlist.items
                    if item.instrument_id == instrument_id
                ]
                exclusion = next(
                    (
                        item_exclusion
                        for item in candidates
                        if (item_exclusion := _watchlist_item_as_of_exclusion(item, as_of))
                        is not None
                    ),
                    {"instrument_id": instrument_id, "reason": "membership_not_known_at_as_of"},
                )
                as_of_exclusions.append(exclusion)

        items_by_instrument = {
            item.instrument_id: item
            for watchlist in referenced
            for item in watchlist.items
            if item.instrument_id in selected_at_as_of
            and _watchlist_item_active_at(item, as_of)
        }
        members: list[ResolvedWatchlistMember] = []
        for position, instrument_id in enumerate(selected_at_as_of):
            item = items_by_instrument.get(instrument_id)
            if item is None:
                continue
            members.append(
                ResolvedWatchlistMember(
                    instrument_id=instrument_id,
                    position=position,
                    weight=None,
                    relationship_type="combo_watchlist_member",
                    source="user_combo_definition",
                    effective_at=item.added_at,
                    known_at=item.added_at,
                )
            )
        return ResolvedWatchlistSource(
            descriptor=_combo_descriptor(combo, len(members), dependency_versions),
            members=tuple(members),
            exclusions=tuple(as_of_exclusions),
        )

    if source_id.startswith("benchmark-family:"):
        raw = source_id.split(":", 1)[1]
        try:
            family_key, role = raw.split(":", 1)
        except ValueError as exc:
            raise ValueError("invalid_benchmark_family_source_id") from exc
        if role not in _BENCHMARK_FAMILY_ROLES or not family_key:
            raise ValueError("invalid_benchmark_family_source_id")
        group = (
            await db.execute(
                select(MarketGroup).where(
                    MarketGroup.stable_key == family_key,
                    MarketGroup.group_type == "benchmark_family",
                )
            )
        ).scalar_one_or_none()
        if group is None:
            raise LookupError("benchmark_family_source_not_found")
        _selected, proxy_symbol, derived = _benchmark_family_role_selection(group, role)
        if proxy_symbol is None:
            return ResolvedWatchlistSource(
                descriptor=_benchmark_family_role_descriptor(group, role),
                members=(),
                exclusions=({"reason": "benchmark_family_role_unavailable", "role": role},),
            )
        row = (
            await db.execute(
                select(ETFProfile, Instrument)
                .join(Instrument, Instrument.id == ETFProfile.instrument_id)
                .where(Instrument.symbol == proxy_symbol)
            )
        ).first()
        if row is None:
            return ResolvedWatchlistSource(
                descriptor=_benchmark_family_role_descriptor(group, role),
                members=(),
                exclusions=({"reason": "etf_profile_not_found", "symbol": proxy_symbol},),
            )
        profile, instrument = row
        statement = select(ETFHoldingsSnapshot).where(
            ETFHoldingsSnapshot.etf_profile_id == profile.id
        )
        if as_of is not None:
            statement = statement.where(
                ETFHoldingsSnapshot.composition_date <= as_of.date(),
                ETFHoldingsSnapshot.known_at.is_not(None),
                ETFHoldingsSnapshot.known_at <= as_of,
            )
        snapshot = (
            await db.execute(
                statement.order_by(
                    ETFHoldingsSnapshot.composition_date.desc(),
                    ETFHoldingsSnapshot.id.desc(),
                ).limit(1)
            )
        ).scalar_one_or_none()
        descriptor = _benchmark_family_role_descriptor(
            group, role, profile=profile, instrument=instrument, snapshot=snapshot
        )
        if snapshot is None:
            return ResolvedWatchlistSource(
                descriptor=descriptor,
                members=(),
                exclusions=(
                    {
                        "reason": (
                            "holdings_snapshot_not_available_at_as_of"
                            if as_of is not None
                            else "holdings_snapshot_not_loaded"
                        ),
                        "symbol": proxy_symbol,
                    },
                ),
            )
        rows = (
            await db.execute(
                select(ETFHolding)
                .where(ETFHolding.snapshot_id == snapshot.id)
                .order_by(ETFHolding.position)
            )
        ).scalars().all()
        valid_rows = [
            holding
            for holding in rows
            if holding.row_type == "security"
            and holding.holding_type in {"equity", "stock", "common_stock"}
            and holding.is_resolved
            and holding.constituent_instrument_id is not None
        ]
        equal_weight = 1.0 / len(valid_rows) if derived and valid_rows else None
        members: list[ResolvedWatchlistMember] = []
        exclusions: list[dict] = []
        for holding in rows:
            holding_type = str(holding.holding_type or "").casefold()
            row_type = str(holding.row_type or "").casefold()
            if row_type == "cash" or holding_type in {"cash", "currency", "collateral"}:
                exclusions.append({"holding_id": holding.id, "reason": "cash_holding"})
                continue
            if holding_type in {"derivative", "derivatives", "option", "future", "swap"}:
                exclusions.append({"holding_id": holding.id, "reason": "derivative_holding"})
                continue
            if row_type != "security" or holding_type not in {"equity", "stock", "common_stock"}:
                exclusions.append({"holding_id": holding.id, "reason": "non_equity_holding"})
                continue
            if not holding.is_resolved or holding.constituent_instrument_id is None:
                exclusions.append({"holding_id": holding.id, "reason": "unresolved_holding"})
                continue
            members.append(
                ResolvedWatchlistMember(
                    instrument_id=holding.constituent_instrument_id,
                    position=holding.position,
                    weight=equal_weight if derived else (float(holding.weight) if holding.weight is not None else None),
                    relationship_type="derived_equal_weight_constituent" if derived else "etf_proxy_constituent",
                    source=snapshot.source_provider,
                    effective_at=datetime.combine(snapshot.composition_date, datetime.min.time()),
                    known_at=snapshot.known_at,
                )
            )
        return ResolvedWatchlistSource(
            descriptor=descriptor,
            members=tuple(members),
            exclusions=tuple(exclusions),
        )

    if source_id.startswith("market-group:"):
        stable_key = source_id.split(":", 1)[1]
        group = (
            await db.execute(
                select(MarketGroup)
                .where(MarketGroup.stable_key == stable_key)
                .options(selectinload(MarketGroup.members))
            )
        ).scalar_one_or_none()
        if group is None:
            raise LookupError("market_group_source_not_found")
        members: list[ResolvedWatchlistMember] = []
        exclusions: list[dict] = []
        for item in group.members:
            if as_of is not None and (
                item.effective_at is None
                or item.known_at is None
                or item.effective_at > as_of
                or item.known_at > as_of
            ):
                exclusions.append({"instrument_id": item.instrument_id, "reason": "membership_not_known_at_as_of"})
                continue
            members.append(
                ResolvedWatchlistMember(
                    instrument_id=item.instrument_id,
                    position=item.position,
                    weight=item.weight,
                    relationship_type=item.relationship_type,
                    source=item.source,
                    effective_at=item.effective_at,
                    known_at=item.known_at,
                )
            )
        return ResolvedWatchlistSource(
            descriptor=_market_group_descriptor(group),
            members=tuple(members),
            exclusions=tuple(exclusions),
        )

    if source_id.startswith("etf-holdings:"):
        symbol = source_id.split(":", 1)[1].upper()
        row = (
            await db.execute(
                select(ETFProfile, Instrument)
                .join(Instrument, Instrument.id == ETFProfile.instrument_id)
                .where(Instrument.symbol == symbol)
            )
        ).first()
        if row is None:
            raise LookupError("etf_holdings_source_not_found")
        profile, instrument = row
        statement = select(ETFHoldingsSnapshot).where(
            ETFHoldingsSnapshot.etf_profile_id == profile.id
        )
        if as_of is not None:
            statement = statement.where(
                ETFHoldingsSnapshot.composition_date <= as_of.date(),
                ETFHoldingsSnapshot.known_at.is_not(None),
                ETFHoldingsSnapshot.known_at <= as_of,
            )
        snapshot = (
            await db.execute(
                statement.order_by(
                    ETFHoldingsSnapshot.composition_date.desc(), ETFHoldingsSnapshot.id.desc()
                ).limit(1)
            )
        ).scalar_one_or_none()
        if snapshot is None:
            return ResolvedWatchlistSource(
                descriptor=_etf_descriptor(profile, instrument, None),
                members=(),
                exclusions=(
                    {
                        "reason": "holdings_snapshot_not_available_at_as_of"
                        if as_of is not None
                        else "holdings_snapshot_not_loaded"
                    },
                ),
            )
        rows = (
            await db.execute(
                select(ETFHolding)
                .where(ETFHolding.snapshot_id == snapshot.id)
                .order_by(ETFHolding.position)
            )
        ).scalars().all()
        members: list[ResolvedWatchlistMember] = []
        exclusions: list[dict] = []
        for holding in rows:
            holding_type = str(holding.holding_type or "").casefold()
            row_type = str(holding.row_type or "").casefold()
            if row_type == "cash" or holding_type in {"cash", "currency", "collateral"}:
                exclusions.append({"holding_id": holding.id, "reason": "cash_holding"})
                continue
            if holding_type in {"derivative", "derivatives", "option", "future", "swap"}:
                exclusions.append({"holding_id": holding.id, "reason": "derivative_holding"})
                continue
            if row_type != "security" or holding_type not in {"equity", "stock", "common_stock"}:
                exclusions.append({"holding_id": holding.id, "reason": "non_equity_holding"})
                continue
            if not holding.is_resolved or holding.constituent_instrument_id is None:
                exclusions.append({"holding_id": holding.id, "reason": "unresolved_holding"})
                continue
            members.append(
                ResolvedWatchlistMember(
                    instrument_id=holding.constituent_instrument_id,
                    position=holding.position,
                    weight=float(holding.weight) if holding.weight is not None else None,
                    relationship_type="etf_proxy_constituent",
                    source=snapshot.source_provider,
                    effective_at=datetime.combine(snapshot.composition_date, datetime.min.time()),
                    known_at=snapshot.known_at,
                )
            )
        return ResolvedWatchlistSource(
            descriptor=_etf_descriptor(profile, instrument, snapshot),
            members=tuple(members),
            exclusions=tuple(exclusions),
        )

    raise ValueError("unsupported_watchlist_source_kind")
