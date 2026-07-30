from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.data_source import DataSource
from app.models.provider_runtime import ProviderCapability, ProviderEntitlement, ProviderPolicy
from app.models.user import User
from app.services.provider_maintenance import (
    list_stale_dataset_states,
    prune_provider_observations,
    reset_provider_health_state,
    summarize_provider_observations,
)
from app.services.provider_runtime import list_provider_status, seed_provider_runtime
from app.services.provider_usage import summarize_provider_usage

router = APIRouter(prefix="/providers", tags=["providers"])


class ProviderPolicyUpdate(BaseModel):
    is_enabled: bool | None = None
    is_pinned: bool | None = None
    auto_weight_enabled: bool | None = None
    base_priority: int | None = None
    max_concurrency: int | None = None
    tokens_per_minute: int | None = None
    burst_capacity: int | None = None
    cooldown_seconds: int | None = None
    freshness_seconds: int | None = None


class ProviderEntitlementUpdate(BaseModel):
    configured_plan: str | None = None
    is_free: bool | None = None
    authentication_required: bool | None = None
    usage_terms: str | None = None
    redistribution_allowed: bool | None = None
    quota_policy: dict | None = None
    history_depth: str | None = None
    venue_coverage: str | None = None
    freshness_semantics: str | None = None
    enabled_environments: list[str] | None = None
    live_probe_status: str | None = None


@router.get("")
async def get_providers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await seed_provider_runtime(db)
    rows = await list_provider_status(db)
    grouped: dict[str, dict] = {}
    for row in rows:
        entry = grouped.setdefault(
            row["provider"],
            {
                "provider": row["provider"],
                "supported_capabilities": row["supported_capabilities"],
                "capabilities": [],
                "updated_at": datetime.now(),
            },
        )
        entry["capabilities"].append(row["capability"])
    return list(grouped.values())


@router.get("/policies")
async def get_provider_policies(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await list_provider_status(db)


@router.get("/entitlements")
async def get_provider_entitlements(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    await seed_provider_runtime(db)
    rows = (
        await db.execute(
            select(ProviderEntitlement, DataSource)
            .join(DataSource, DataSource.id == ProviderEntitlement.data_source_id)
            .order_by(DataSource.name, ProviderEntitlement.capability)
        )
    ).all()
    return [
        {
            "provider": source.name,
            "capability": entitlement.capability.value,
            "configured_plan": entitlement.configured_plan,
            "is_free": entitlement.is_free,
            "authentication_required": entitlement.authentication_required,
            "usage_terms": entitlement.usage_terms,
            "redistribution_allowed": entitlement.redistribution_allowed,
            "quota_policy": entitlement.quota_policy,
            "history_depth": entitlement.history_depth,
            "venue_coverage": entitlement.venue_coverage,
            "freshness_semantics": entitlement.freshness_semantics,
            "enabled_environments": entitlement.enabled_environments,
            "effective_at": entitlement.effective_at,
            "review_due_at": entitlement.review_due_at,
            "live_probe_status": entitlement.live_probe_status,
        }
        for entitlement, source in rows
    ]


@router.patch("/entitlements/{provider_name}/{capability}")
async def update_provider_entitlement(
    provider_name: str,
    capability: str,
    body: ProviderEntitlementUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        capability_enum = ProviderCapability(capability)
    except ValueError as exc:
        raise HTTPException(400, f"Unknown provider capability '{capability}'") from exc
    await seed_provider_runtime(db)
    entitlement = (
        await db.execute(
            select(ProviderEntitlement)
            .join(DataSource)
            .where(
                DataSource.name == provider_name, ProviderEntitlement.capability == capability_enum
            )
        )
    ).scalar_one_or_none()
    if entitlement is None:
        raise HTTPException(404, f"No entitlement found for '{provider_name}' / '{capability}'")
    for field_name, value in body.model_dump(exclude_unset=True).items():
        setattr(entitlement, field_name, value)
    await db.flush()
    return {"ok": True}


@router.get("/health")
async def get_provider_health(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = await list_provider_status(db)
    return [
        {
            "provider": row["provider"],
            "capability": row["capability"],
            "failure_streak": row["failure_streak"],
            "last_success_at": row["last_success_at"],
            "last_failure_at": row["last_failure_at"],
            "circuit_open_until": row["circuit_open_until"],
            "ewma_latency_ms": row["ewma_latency_ms"],
            "ewma_success_rate": row["ewma_success_rate"],
            "ewma_completeness": row["ewma_completeness"],
            "ewma_freshness": row["ewma_freshness"],
            "ewma_consistency": row["ewma_consistency"],
            "last_error_type": row["last_error_type"],
            "last_error_message": row["last_error_message"],
        }
        for row in rows
    ]


@router.get("/observations/summary")
async def get_provider_observation_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await summarize_provider_observations(db)


@router.get("/usage")
async def get_provider_usage(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await summarize_provider_usage(db)


@router.get("/datasets/stale")
async def get_stale_provider_datasets(
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await list_stale_dataset_states(db, limit=limit)


@router.patch("/policies/{provider_name}/{capability}")
async def update_provider_policy(
    provider_name: str,
    capability: str,
    body: ProviderPolicyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await seed_provider_runtime(db)
    try:
        capability_enum = ProviderCapability(capability)
    except ValueError as exc:
        raise HTTPException(400, f"Unknown provider capability '{capability}'") from exc

    data_source = (
        await db.execute(select(DataSource).where(DataSource.name == provider_name))
    ).scalar_one_or_none()
    if data_source is None:
        raise HTTPException(404, f"Unknown provider '{provider_name}'")

    policy = (
        await db.execute(
            select(ProviderPolicy).where(
                ProviderPolicy.data_source_id == data_source.id,
                ProviderPolicy.capability == capability_enum,
            )
        )
    ).scalar_one_or_none()
    if policy is None:
        raise HTTPException(404, f"No policy found for '{provider_name}' / '{capability}'")

    for field_name, value in body.model_dump(exclude_unset=True).items():
        setattr(policy, field_name, value)
    if body.base_priority is not None and body.is_pinned is None:
        policy.is_pinned = True
    await db.flush()
    return {"ok": True}


@router.post("/maintenance/prune")
async def run_provider_observation_prune(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deleted = await prune_provider_observations(db)
    return {"ok": True, "deleted": deleted}


@router.post("/health/{provider_name}/{capability}/reset")
async def reset_provider_health(
    provider_name: str,
    capability: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        capability_enum = ProviderCapability(capability)
    except ValueError as exc:
        raise HTTPException(400, f"Unknown provider capability '{capability}'") from exc
    reset = await reset_provider_health_state(
        db,
        provider_name=provider_name,
        capability=capability_enum,
    )
    if not reset:
        raise HTTPException(404, f"No health state found for '{provider_name}' / '{capability}'")
    return {"ok": True}
