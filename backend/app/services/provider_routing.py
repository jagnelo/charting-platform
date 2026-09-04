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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data_foundation import (
    ProviderQuotaWindow,
    ProviderRoutingDecision,
    ProviderWorkloadLease,
)
from app.models.provider_runtime import ProviderCapability
from app.services.provider_runtime import ResolvedProvider, resolve_provider_chain


@dataclass(frozen=True, slots=True)
class ProviderRequirements:
    capability: ProviderCapability
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


def _entitlement_matches(entitlement: Any, requirements: ProviderRequirements) -> tuple[bool, str | None]:
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
    units: int,
    limit_units: int,
    window_seconds: int = 60,
    now: datetime | None = None,
) -> ProviderQuotaWindow | None:
    """Atomically reserve units in a durable rolling window."""

    if units <= 0 or limit_units <= 0:
        return None
    current = now or datetime.now(UTC)
    epoch = int(current.timestamp())
    start = datetime.fromtimestamp(epoch - (epoch % window_seconds), tz=UTC)
    query = select(ProviderQuotaWindow).where(
        ProviderQuotaWindow.data_source_id == data_source_id,
        ProviderQuotaWindow.capability == capability,
        ProviderQuotaWindow.window_started_at == start,
        ProviderQuotaWindow.window_seconds == window_seconds,
    ).with_for_update()
    window = (await db.execute(query)).scalar_one_or_none()
    if window is None:
        window = ProviderQuotaWindow(
            data_source_id=data_source_id,
            capability=capability,
            window_started_at=start,
            window_seconds=window_seconds,
            limit_units=limit_units,
            reserved_units=0,
            consumed_units=0,
        )
        db.add(window)
        await db.flush()
    available = window.limit_units - window.reserved_units - window.consumed_units
    if available < units:
        return None
    window.reserved_units += units
    return window


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
        db, requirements.capability, instrument_id=requirements.instrument_id
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
        limit = int(getattr(resolved.policy, "tokens_per_minute", 0) or 0)
        if limit <= 0:
            rejected[resolved.provider_name] = "quota_unknown"
            continue
        reservation = await reserve_provider_quota(
            db,
            data_source_id=resolved.data_source.id,
            capability=requirements.capability.value,
            units=requirements.units,
            limit_units=limit,
            now=current,
        )
        if reservation is None:
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
            request_metadata={"request_key": request_key},
        )
        db.add(lease)
        candidates.append({"provider": resolved.provider_name, "score": str(resolved.policy.effective_score)})
        selected = (resolved, lease)
        break
    if selected is None:
        candidates.extend({"provider": item.provider_name, "score": str(item.policy.effective_score)} for item in providers)
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
    window = (
        await db.execute(
            select(ProviderQuotaWindow)
            .where(
                ProviderQuotaWindow.data_source_id == lease.data_source_id,
                ProviderQuotaWindow.capability == lease.capability,
                ProviderQuotaWindow.window_started_at <= lease_created_at,
            )
            .order_by(ProviderQuotaWindow.window_started_at.desc())
            .limit(1)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if window is not None and lease_created_at >= window.window_started_at + timedelta(seconds=window.window_seconds):
        window = None
    if window is not None:
        window.reserved_units = max(0, window.reserved_units - lease.units)
        window.consumed_units += units
        window.cost_cents += cost_cents
    lease.status = "completed" if success else "failed"
    lease.lease_expires_at = datetime.now(UTC)
    await db.flush()
