"""Capability- and quota-aware provider selection.

The existing runtime resolver remains the compatibility entry point.  This
module adds durable reservations and an explanation row so workers can share a
budget without silently exceeding a provider's declared limits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data_foundation import (
    ProviderQuotaIdentity,
    ProviderQuotaWindow,
    ProviderRoutingDecision,
    ProviderWorkloadLease,
)
from app.models.provider_runtime import ProviderCapability
from app.services.provider_runtime import (
    ResolvedProvider,
    policy_has_known_quota,
    provider_contract_operation_cost_known,
    quota_dimensions,
    resolve_provider_chain,
)

_DISTINCT_IDENTITY_UNITS = {"symbol", "symbols", "unique_symbol", "unique_symbols"}
_IN_FLIGHT_UNITS = {"concurrent_requests", "concurrency"}


def quota_group_for_dimension(capability: str, dimension: dict[str, Any]) -> str:
    """Return the explicitly reviewed bucket key for one provider dimension.

    Providers sometimes publish an account/key-wide allowance used by several
    capabilities.  Contracts must opt into that sharing with ``quota_group``;
    otherwise the legacy capability key remains the isolated bucket.  This
    fallback is a compatibility key, not a guessed provider limit.
    """

    configured = dimension.get("quota_group")
    if configured is not None and str(configured).strip():
        return str(configured).strip()
    return str(capability).strip()


def _window_start_for_dimension(
    dimension: dict[str, Any],
    *,
    reset: str,
    now: datetime,
) -> tuple[datetime | None, bool]:
    """Resolve a documented fixed/calendar boundary or rolling window."""

    window_start = None
    dimension_reset = str(dimension.get("reset") or reset)
    window_seconds = int(dimension["window_seconds"])
    if dimension_reset == "calendar_month_est" and window_seconds >= 2_500_000:
        eastern = now.astimezone(ZoneInfo("America/New_York"))
        reset_local = eastern.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        window_start = reset_local.astimezone(UTC)
    elif "calendar_month" in dimension_reset and window_seconds >= 2_500_000:
        window_start = datetime(now.year, now.month, 1, tzinfo=UTC)
    elif dimension_reset in {"calendar_day_utc", "calendar_day_gmt"} and window_seconds >= 86400:
        window_start = datetime(now.year, now.month, now.day, tzinfo=UTC)
    elif dimension_reset == "calendar_day_est" and window_seconds >= 86400:
        eastern = now.astimezone(ZoneInfo("America/New_York"))
        reset_local = eastern.replace(hour=0, minute=0, second=0, microsecond=0)
        window_start = reset_local.astimezone(UTC)
    elif dimension_reset.startswith("09:30") and window_seconds >= 86400:
        eastern = now.astimezone(ZoneInfo("America/New_York"))
        reset_local = eastern.replace(hour=9, minute=30, second=0, microsecond=0)
        if eastern < reset_local:
            reset_local -= timedelta(days=1)
        window_start = reset_local.astimezone(UTC)
    rolling = window_start is None and (
        "rolling" in dimension_reset
        or dimension_reset in {"provider_defined", "provider_defined_daily", "per_dimension"}
    )
    return window_start, rolling


async def _claim_distinct_identity(
    db: AsyncSession,
    *,
    data_source_id: int,
    capability: str,
    quota_group: str,
    dimension: str,
    window_started_at: datetime,
    window_seconds: int,
    identity_key: str,
) -> bool:
    """Claim one distinct provider identity, coordinating concurrent workers."""

    normalized = identity_key.strip().upper()
    if not normalized:
        return False
    query = select(ProviderQuotaIdentity).where(
        ProviderQuotaIdentity.data_source_id == data_source_id,
        ProviderQuotaIdentity.quota_group == quota_group,
        ProviderQuotaIdentity.dimension == dimension,
        ProviderQuotaIdentity.window_started_at == window_started_at,
        ProviderQuotaIdentity.window_seconds == window_seconds,
        ProviderQuotaIdentity.identity_key == normalized,
    )
    existing = (await db.execute(query)).scalar_one_or_none()
    if existing is not None:
        return False
    candidate = ProviderQuotaIdentity(
        data_source_id=data_source_id,
        capability=capability,
        quota_group=quota_group,
        dimension=dimension,
        window_started_at=window_started_at,
        window_seconds=window_seconds,
        identity_key=normalized,
    )
    try:
        savepoint = db.begin_nested()
        if hasattr(savepoint, "__aenter__"):
            async with savepoint:
                db.add(candidate)
                await db.flush()
        else:
            with savepoint:
                db.add(candidate)
                await db.flush()
        return True
    except IntegrityError:
        # Another worker claimed the same identity between the SELECT and
        # INSERT. The savepoint keeps the caller transaction usable.
        existing = (await db.execute(query)).scalar_one_or_none()
        if existing is None:
            raise
        return False
@dataclass(frozen=True, slots=True)
class ProviderRequirements:
    capability: ProviderCapability
    operation: str | None = None
    instrument_id: int | None = None
    asset_class: str | None = None
    venue: str | None = None
    session_code: str | None = None
    timeframe: str | None = None
    feed_scope: str | None = None
    history_start: datetime | None = None
    terms: set[str] = field(default_factory=set)
    units: int = 1
    priority: int = 100
    usage_identity: str | None = None


def _entitlement_matches(
    entitlement: Any, requirements: ProviderRequirements
) -> tuple[bool, str | None]:
    """Check optional structured entitlement declarations without guessing."""

    policy = dict(entitlement.quota_policy or {})
    for field_name, expected in (
        ("asset_classes", requirements.asset_class),
        ("venues", requirements.venue),
        ("sessions", requirements.session_code),
        ("timeframes", requirements.timeframe),
        ("feeds", requirements.feed_scope),
    ):
        if expected is None:
            continue
        declared = policy.get(field_name)
        if declared and str(expected).lower() not in {str(item).lower() for item in declared}:
            return False, f"{field_name}_not_entitled"
    if requirements.history_start is not None:
        raw_depth = entitlement.history_depth or policy.get("history_depth")
        if not raw_depth:
            return False, "history_depth_unknown"
    if requirements.terms:
        declared_terms = {str(value) for value in (policy.get("terms") or [])}
        missing = requirements.terms - declared_terms
        if missing:
            return False, "terms_not_declared"
    return True, None


async def reserve_provider_quota(
    db: AsyncSession,
    *,
    data_source_id: int,
    capability: str,
    quota_group: str | None = None,
    units: int,
    limit_units: int,
    window_seconds: int = 60,
    dimension: str = "default",
    window_started_at: datetime | None = None,
    now: datetime | None = None,
    rolling: bool = False,
    release_only: bool = False,
) -> ProviderQuotaWindow | None:
    """Atomically reserve units in a durable fixed or rolling window."""

    if units <= 0 or limit_units <= 0:
        return None
    effective_quota_group = str(quota_group or capability).strip() or str(capability)
    current = now or datetime.now(UTC)
    if rolling:
        # Rolling provider limits are enforced over all second buckets that
        # overlap the active interval. Each bucket remains durable so workers
        # can lock and settle their own reservation without a process-local
        # counter or an invented fixed-window reset.
        cutoff = current - timedelta(seconds=window_seconds)
        active_query = (
            select(ProviderQuotaWindow)
            .where(
                ProviderQuotaWindow.data_source_id == data_source_id,
                ProviderQuotaWindow.quota_group == effective_quota_group,
                ProviderQuotaWindow.dimension == dimension,
                ProviderQuotaWindow.window_started_at >= cutoff,
                ProviderQuotaWindow.window_seconds == window_seconds,
            )
            .with_for_update()
        )
        active = (await db.execute(active_query)).scalars().all()
        start = datetime.fromtimestamp(int(current.timestamp()), tz=UTC)
        window = next((row for row in active if row.window_started_at == start), None)
        if window is None:
            candidate = ProviderQuotaWindow(
                data_source_id=data_source_id,
                capability=capability,
                quota_group=effective_quota_group,
                dimension=dimension,
                window_started_at=start,
                window_seconds=window_seconds,
                limit_units=limit_units,
                reserved_units=0,
                consumed_units=0,
            )
            try:
                savepoint = db.begin_nested()
                if hasattr(savepoint, "__aenter__"):
                    async with savepoint:
                        db.add(candidate)
                        await db.flush()
                else:
                    with savepoint:
                        db.add(candidate)
                        await db.flush()
                window = candidate
            except IntegrityError:
                window = (
                    await db.execute(
                        select(ProviderQuotaWindow)
                        .where(
                            ProviderQuotaWindow.data_source_id == data_source_id,
                            ProviderQuotaWindow.quota_group == effective_quota_group,
                            ProviderQuotaWindow.dimension == dimension,
                            ProviderQuotaWindow.window_started_at == start,
                            ProviderQuotaWindow.window_seconds == window_seconds,
                        )
                        .with_for_update()
                    )
                ).scalar_one_or_none()
                if window is None:
                    raise
            active = (await db.execute(active_query)).scalars().all()
        available = window.limit_units - sum(
            row.reserved_units + (0 if release_only else row.consumed_units) for row in active
        )
        if available < units:
            return None
        window.reserved_units += units
        return window
    if window_started_at is not None:
        start = window_started_at.astimezone(UTC)
    else:
        epoch = int(current.timestamp())
        start = datetime.fromtimestamp(epoch - (epoch % window_seconds), tz=UTC)
    query = (
        select(ProviderQuotaWindow)
        .where(
            ProviderQuotaWindow.data_source_id == data_source_id,
            ProviderQuotaWindow.quota_group == effective_quota_group,
            ProviderQuotaWindow.dimension == dimension,
            ProviderQuotaWindow.window_started_at == start,
            ProviderQuotaWindow.window_seconds == window_seconds,
        )
        .with_for_update()
    )
    window = (await db.execute(query)).scalar_one_or_none()
    if window is None:
        candidate = ProviderQuotaWindow(
            data_source_id=data_source_id,
            capability=capability,
            quota_group=effective_quota_group,
            dimension=dimension,
            window_started_at=start,
            window_seconds=window_seconds,
            limit_units=limit_units,
            reserved_units=0,
            consumed_units=0,
        )
        try:
            # The initial SELECT cannot lock a row that does not exist. Two
            # workers can therefore reach this branch for the same provider
            # window. Keep the INSERT inside a savepoint so a concurrent
            # unique-key winner does not poison the caller's transaction;
            # then lock and reuse the row that won the race.
            savepoint = db.begin_nested()
            if hasattr(savepoint, "__aenter__"):
                async with savepoint:
                    db.add(candidate)
                    await db.flush()
            else:
                # The unit-test AsyncSessionAdapter deliberately exposes the
                # synchronous SQLite transaction API behind an async facade.
                with savepoint:
                    db.add(candidate)
                    await db.flush()
            window = candidate
        except IntegrityError:
            window = (await db.execute(query)).scalar_one_or_none()
            if window is None:
                raise
    available = window.limit_units - window.reserved_units - (
        0 if release_only else window.consumed_units
    )
    if available < units:
        return None
    window.reserved_units += units
    return window


async def reserve_provider_contract(
    db: AsyncSession,
    *,
    resolved: ResolvedProvider,
    capability: str,
    units: int,
    dimension_units: dict[str, int] | None = None,
    usage_identity: str | None = None,
    now: datetime,
) -> list[ProviderQuotaWindow] | None:
    """Reserve every documented quota dimension or none of them."""

    if not policy_has_known_quota(resolved.policy):
        return None
    windows: list[ProviderQuotaWindow] = []
    reset = str((resolved.policy.quota_contract or {}).get("reset") or "")
    in_flight_dimensions = {
        str(item["name"])
        for item in quota_dimensions(resolved.policy)
        if str(item.get("unit") or "").strip().lower() in _IN_FLIGHT_UNITS
    }
    distinct_identity_dimensions = {
        str(item["name"])
        for item in quota_dimensions(resolved.policy)
        if str(item.get("unit") or "").strip().lower() in _DISTINCT_IDENTITY_UNITS
    }
    for dimension in quota_dimensions(resolved.policy):
        dimension_name = str(dimension["name"])
        dimension_unit = str(dimension.get("unit") or "").strip().lower()
        is_distinct_identity = dimension_unit in _DISTINCT_IDENTITY_UNITS
        is_in_flight = dimension_unit in _IN_FLIGHT_UNITS
        quota_group = quota_group_for_dimension(capability, dimension)
        if is_distinct_identity and not usage_identity:
            return None
        raw_reserved_units = (dimension_units or {}).get(dimension_name, units)
        if int(raw_reserved_units) <= 0:
            continue
        # One invocation occupies one concurrent slot regardless of how many
        # request/credit units the provider-specific operation costs.
        reserved_units = 1 if is_in_flight else max(1, int(raw_reserved_units))
        window_start, rolling = _window_start_for_dimension(dimension, reset=reset, now=now)
        window = await reserve_provider_quota(
            db,
            data_source_id=resolved.data_source.id,
            capability=capability,
            quota_group=quota_group,
            dimension=dimension_name,
            units=reserved_units,
            limit_units=int(dimension["limit"]),
            window_seconds=int(dimension["window_seconds"]),
            window_started_at=window_start,
            now=now,
            rolling=rolling,
            release_only=is_in_flight,
        )
        if window is None:
            for prior in windows:
                prior_name = str(prior.dimension)
                # Roll back the actual reservation amount. In-flight
                # dimensions always reserve one slot, independent of an
                # operation's request/credit workload units.
                prior_units = 1 if prior_name in in_flight_dimensions else max(
                    0, int((dimension_units or {}).get(prior_name, units))
                )
                if prior_name in distinct_identity_dimensions:
                    # The identity row is intentionally retained, so convert
                    # its reservation into consumption instead of releasing
                    # the window and allowing another symbol to overrun it.
                    prior.reserved_units = max(0, prior.reserved_units - prior_units)
                    prior.consumed_units += prior_units
                else:
                    prior.reserved_units = max(0, prior.reserved_units - prior_units)
            return None
        if is_distinct_identity:
            # A symbol claim is retained once admitted. If the subsequent
            # provider call fails, settling the distinct dimension still
            # consumes the one claimed identity; this avoids under-counting
            # against a provider pool that meters attempted symbols.
            identity_start = window.window_started_at
            claimed = await _claim_distinct_identity(
                db,
                data_source_id=resolved.data_source.id,
                capability=capability,
                quota_group=quota_group,
                dimension=dimension_name,
                window_started_at=identity_start,
                window_seconds=int(dimension["window_seconds"]),
                identity_key=str(usage_identity),
            )
            if not claimed:
                window.reserved_units = max(0, window.reserved_units - reserved_units)
                continue
        windows.append(window)
    return windows


def settle_provider_contract(
    windows: list[ProviderQuotaWindow],
    *,
    units: int,
    success: bool = True,
    reserved_dimension_units: dict[str, int] | None = None,
    consumed_dimension_units: dict[str, int] | None = None,
    observed_dimension_totals: dict[str, int] | None = None,
    consume_on_failure_dimensions: set[str] | None = None,
    release_only_dimensions: set[str] | None = None,
) -> None:
    """Move one runtime reservation into consumption without a separate lease."""

    settled_units = max(0, units)
    for window in windows:
        dimension = str(window.dimension)
        reserved = max(
            0,
            int((reserved_dimension_units or {}).get(dimension, settled_units)),
        )
        consumed = max(
            0,
            int((consumed_dimension_units or {}).get(dimension, settled_units)),
        )
        window.reserved_units = max(0, window.reserved_units - reserved)
        if dimension in (release_only_dimensions or set()):
            continue
        if success or dimension in (consume_on_failure_dimensions or set()):
            window.consumed_units += consumed
            observed_total = (observed_dimension_totals or {}).get(dimension)
            if observed_total is not None:
                # Provider-native usage headers may include calls made by
                # other workers/processes. Never let a stale or malformed
                # observation reduce locally recorded consumption.
                window.consumed_units = max(window.consumed_units, int(observed_total))


async def select_provider(
    db: AsyncSession,
    requirements: ProviderRequirements,
    *,
    request_key: str,
    workload_key: str | None = None,
    now: datetime | None = None,
) -> tuple[ResolvedProvider, ProviderWorkloadLease] | None:
    """Select, reserve, and explain one provider decision."""

    providers = await resolve_provider_chain(
        db,
        requirements.capability,
        instrument_id=requirements.instrument_id,
        operation=requirements.operation,
    )
    candidates: list[dict[str, Any]] = []
    rejected: dict[str, str] = {}
    current = now or datetime.now(UTC)
    selected: tuple[ResolvedProvider, ProviderWorkloadLease] | None = None
    for resolved in providers:
        entitlement = getattr(resolved, "entitlement", None)
        if entitlement is not None:
            allowed, reason = _entitlement_matches(entitlement, requirements)
            if not allowed:
                rejected[resolved.provider_name] = reason or "not_entitled"
                continue
        if not policy_has_known_quota(resolved.policy):
            rejected[resolved.provider_name] = "quota_unknown"
            continue
        if not provider_contract_operation_cost_known(
            resolved.policy,
            resolved.data_source,
            requirements.operation,
            usage_identity=requirements.usage_identity,
        ):
            rejected[resolved.provider_name] = "operation_cost_unknown"
            continue
        reservations = await reserve_provider_contract(
            db,
            resolved=resolved,
            capability=requirements.capability.value,
            units=requirements.units,
            usage_identity=requirements.usage_identity,
            now=current,
        )
        if reservations is None:
            rejected[resolved.provider_name] = "quota_exhausted"
            continue
        lease = ProviderWorkloadLease(
            workload_key=workload_key or request_key,
            capability=requirements.capability.value,
            data_source_id=resolved.data_source.id,
            units=requirements.units,
            status="reserved",
            lease_expires_at=current + timedelta(minutes=5),
            priority=requirements.priority,
            request_metadata={
                "request_key": request_key,
                # Keep the exact durable windows reserved for this lease. A
                # calendar-month or provider-reset window can overlap the
                # fixed-size interval of an older window, so settling by
                # timestamp alone could debit the wrong reservation.
                "quota_window_ids": [window.id for window in reservations],
                "release_only_dimensions": [
                    str(dimension["name"])
                    for dimension in quota_dimensions(resolved.policy)
                    if str(dimension.get("unit") or "").lower() in _IN_FLIGHT_UNITS
                ],
            },
        )
        db.add(lease)
        candidates.append(
            {"provider": resolved.provider_name, "score": str(resolved.policy.effective_score)}
        )
        selected = (resolved, lease)
        break
    if selected is None:
        candidates.extend(
            {"provider": item.provider_name, "score": str(item.policy.effective_score)}
            for item in providers
        )
    decision = ProviderRoutingDecision(
        request_key=request_key,
        capability=requirements.capability.value,
        instrument_id=requirements.instrument_id,
        selected_data_source_id=selected[0].data_source.id if selected else None,
        candidates=candidates,
        rejected=rejected,
        workload_key=workload_key,
        created_at=current,
    )
    db.add(decision)
    if selected:
        await db.flush()
    return selected


async def settle_workload_lease(
    db: AsyncSession,
    lease: ProviderWorkloadLease,
    *,
    consumed_units: int | None = None,
    cost_cents: Decimal = Decimal("0"),
    success: bool = True,
) -> None:
    """Close a lease and move reserved units into durable consumption."""

    units = max(0, consumed_units if consumed_units is not None else lease.units)
    lease_created_at = lease.created_at or datetime.now(UTC)
    metadata = dict(lease.request_metadata or {})
    release_only_dimensions = {
        str(value)
        for value in (metadata.get("release_only_dimensions") or [])
        if str(value).strip()
    }
    raw_window_ids = metadata.get("quota_window_ids")
    if isinstance(raw_window_ids, list) and raw_window_ids:
        window_ids: list[int] = []
        for value in raw_window_ids:
            try:
                window_ids.append(int(value))
            except (TypeError, ValueError):
                continue
        windows = (
            (
                await db.execute(
                    select(ProviderQuotaWindow)
                    .where(ProviderQuotaWindow.id.in_(window_ids))
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        active_windows = list(windows)
    else:
        # Compatibility path for leases created before exact window IDs were
        # persisted. New leases always take the branch above.
        windows = (
            (
                await db.execute(
                    select(ProviderQuotaWindow)
                    .where(
                        ProviderQuotaWindow.data_source_id == lease.data_source_id,
                        ProviderQuotaWindow.capability == lease.capability,
                        ProviderQuotaWindow.window_started_at <= lease_created_at,
                    )
                    .order_by(ProviderQuotaWindow.window_started_at.desc())
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        active_windows = [
            window
            for window in windows
            if lease_created_at
            < window.window_started_at + timedelta(seconds=window.window_seconds)
        ]
    for window in active_windows:
        window.reserved_units = max(0, window.reserved_units - lease.units)
        if str(window.dimension) in release_only_dimensions:
            continue
        if success:
            window.consumed_units += units
            window.cost_cents += cost_cents
    lease.status = "completed" if success else "failed"
    lease.lease_expires_at = datetime.now(UTC)
    await db.flush()
