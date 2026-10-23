from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_admin
from app.config import settings
from app.database import get_db
from app.models.data_source import DataSource
from app.models.instrument_reconciliation import InstrumentReconciliationIssue
from app.models.provider_runtime import (
    ProviderCapability,
    ProviderEntitlement,
    ProviderEntitlementRevision,
    ProviderHealthState,
    ProviderPolicy,
)
from app.models.user import User
from app.providers import supported_provider_names
from app.services.etf_holdings_adapters import get_holdings_adapter
from app.services.instrument_reconciliation import (
    list_reconciliation_issues,
    resolve_reconciliation_issue,
)
from app.services.provider_account_usage import (
    list_provider_account_usage,
    refresh_provider_account_usage,
)
from app.services.provider_availability import (
    latest_availability,
    recent_availability_runs,
    run_availability_probes,
)
from app.services.provider_maintenance import (
    list_stale_dataset_states,
    prune_provider_observations,
    reset_provider_health_state,
    summarize_provider_observations,
)
from app.services.provider_quota_coordinator import (
    ProviderQuotaCoordinatorError,
    account_scope_for_provider,
)
from app.services.provider_runtime import (
    list_provider_status,
    provider_contract_operation_cost_known,
    quota_contract_missing_dimensions,
    record_entitlement_revision,
    seed_provider_runtime,
)
from app.services.provider_usage import summarize_provider_usage

router = APIRouter(prefix="/providers", tags=["providers"])


class ProviderPolicyUpdate(BaseModel):
    is_enabled: bool | None = None
    is_pinned: bool | None = None
    auto_weight_enabled: bool | None = None
    base_priority: int | None = Field(default=None, ge=0)
    max_concurrency: int | None = Field(default=None, ge=1)
    tokens_per_minute: int | None = Field(default=None, ge=1)
    burst_capacity: int | None = Field(default=None, ge=1)
    cooldown_seconds: int | None = Field(default=None, ge=1)
    quota_contract: dict | None = None
    quota_scope: str | None = None
    quota_source: str | None = None
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
    effective_at: datetime | None = None
    review_due_at: datetime | None = None
    live_probe_status: str | None = None


class ETFPublisherOperationReview(BaseModel):
    evidence_source: str = Field(min_length=1, max_length=500)
    evidence_version: str = Field(min_length=1, max_length=120)
    reviewed_at: datetime

    @field_validator("evidence_source", "evidence_version")
    @classmethod
    def require_nonblank_evidence(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("operation evidence fields cannot be blank")
        return value

    @field_validator("reviewed_at")
    @classmethod
    def require_review_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("reviewed_at must include a timezone")
        if value > datetime.now(UTC):
            raise ValueError("reviewed_at cannot be in the future")
        return value


class ETFPublisherEntitlementReview(BaseModel):
    evidence_source: str = Field(min_length=1, max_length=500)
    evidence_version: str = Field(min_length=1, max_length=120)
    reviewed_at: datetime
    configured_plan: str = Field(min_length=1, max_length=80)
    is_free: bool
    authentication_required: bool
    usage_terms: str = Field(min_length=1)
    redistribution_allowed: bool
    quota_policy: dict
    history_depth: str = Field(min_length=1)
    venue_coverage: str = Field(min_length=1)
    freshness_semantics: str = Field(min_length=1)
    enabled_environments: list[str] = Field(min_length=1)
    effective_at: datetime
    review_due_at: datetime

    @field_validator(
        "evidence_source",
        "evidence_version",
        "configured_plan",
        "usage_terms",
        "history_depth",
        "venue_coverage",
        "freshness_semantics",
    )
    @classmethod
    def require_nonblank_review_values(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("entitlement review fields cannot be blank")
        return value

    @field_validator("enabled_environments")
    @classmethod
    def require_review_environments(cls, values: list[str]) -> list[str]:
        normalized = [value.strip().lower() for value in values]
        if any(not value for value in normalized) or len(set(normalized)) != len(normalized):
            raise ValueError("enabled_environments must be nonblank and unique")
        return normalized

    @field_validator("reviewed_at")
    @classmethod
    def require_review_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("entitlement review dates must include a timezone")
        if value > datetime.now(UTC):
            raise ValueError("entitlement review dates cannot be in the future")
        return value

    @field_validator("effective_at", "review_due_at")
    @classmethod
    def require_entitlement_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("entitlement effective/review dates must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_review_window(self):
        if self.review_due_at <= self.effective_at:
            raise ValueError("review_due_at must be later than effective_at")
        return self


class ETFPublisherUsageReview(BaseModel):
    mode: Literal["call_count", "weighted_request", "credit_count", "multi_dimensional"]
    unit_label: str = Field(min_length=1, max_length=80)
    operation_costs: dict[str, int | Decimal]
    dimension_costs: dict[str, dict] = Field(default_factory=dict)


class ETFPublisherProvisionRequest(BaseModel):
    """Admin-attested initial registration; it never enables the route."""

    provider_name: str = Field(min_length=2, max_length=50, pattern=r"^[a-z0-9][a-z0-9_-]+$")
    description: str = Field(min_length=1, max_length=300)
    https_hosts: list[str] = Field(min_length=1)
    operations: dict[str, ETFPublisherOperationReview] = Field(min_length=1)
    publisher_evidence_source: str = Field(min_length=1, max_length=500)
    publisher_evidence_version: str = Field(min_length=1, max_length=120)
    publisher_reviewed_at: datetime
    quota_scope: str = Field(min_length=1, max_length=80)
    quota_source: str = Field(min_length=1, max_length=240)
    quota_evidence_version: str = Field(min_length=1, max_length=120)
    quota_contract: dict
    quota_verified_at: datetime
    max_concurrency: int = Field(gt=0)
    tokens_per_minute: int = Field(gt=0)
    burst_capacity: int = Field(gt=0)
    cooldown_seconds: int | None = Field(default=None, gt=0)
    freshness_seconds: int = Field(gt=0)
    account_scope: str = Field(min_length=1, max_length=128)
    usage_tracking: ETFPublisherUsageReview
    entitlement: ETFPublisherEntitlementReview

    @field_validator(
        "description",
        "publisher_evidence_source",
        "publisher_evidence_version",
        "quota_scope",
        "quota_source",
        "quota_evidence_version",
        "account_scope",
    )
    @classmethod
    def require_nonblank_provision_values(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("publisher provisioning fields cannot be blank")
        return value

    @field_validator("publisher_reviewed_at", "quota_verified_at")
    @classmethod
    def require_review_timestamps(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("review timestamps must include a timezone")
        if value > datetime.now(UTC):
            raise ValueError("review timestamps cannot be in the future")
        return value

    @field_validator("https_hosts")
    @classmethod
    def require_hostnames_only(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            candidate = value.strip().lower().rstrip(".")
            parsed = urlsplit(f"https://{candidate}")
            if (
                not candidate
                or "*" in candidate
                or parsed.hostname != candidate
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.port is not None
                or "://" in value
            ):
                raise ValueError("https_hosts must contain exact hostnames, not URLs or wildcards")
            normalized.append(candidate)
        if len(set(normalized)) != len(normalized):
            raise ValueError("https_hosts cannot contain duplicates")
        return normalized

    @model_validator(mode="after")
    def validate_publisher_review(self):
        allowed_operations = {"fetch_etf_holdings_latest", "fetch_etf_holdings_for_date"}
        if not set(self.operations).issubset(allowed_operations):
            raise ValueError("operations contains an unreviewed ETF operation")
        if self.publisher_reviewed_at > datetime.now(UTC):
            raise ValueError("publisher_reviewed_at cannot be in the future")
        return self


class ReconciliationIssueUpdate(BaseModel):
    status: Literal["open", "resolved", "ignored"]
    resolution: dict | None = None


@router.post("/etf-publishers", status_code=status.HTTP_201_CREATED)
async def provision_etf_publisher(
    body: ETFPublisherProvisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Create reviewed ETF publisher rows in a deliberately disabled state.

    This is not a route-activation endpoint. Review inputs are retained as
    admin attestations; missing quota, account, entitlement, or operation
    evidence is rejected before any database row is created.
    """

    provider_name = body.provider_name.strip().lower()
    if provider_name in supported_provider_names():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Generic Provider sources must use their registered seed and review paths",
        )
    adapter = get_holdings_adapter(provider_name)
    if (
        adapter is None
        or str(getattr(adapter, "source_provider", "")).strip().lower() != provider_name
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ETF publisher must match a registered native holdings adapter",
        )

    account_scope_key = f"{provider_name}:{body.quota_scope.strip().lower()}"
    account_scopes = settings.PROVIDER_QUOTA_ACCOUNT_SCOPES
    if not isinstance(account_scopes, dict) or not (
        account_scope_key in account_scopes or provider_name in account_scopes
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Explicit provider/account-scope configuration is required",
        )
    try:
        expected_scope = account_scope_for_provider(provider_name, body.quota_scope)
    except ProviderQuotaCoordinatorError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provider/account-scope configuration is invalid",
        ) from exc
    if body.account_scope != expected_scope:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Review account scope does not match configured shared quota scope",
        )

    now = datetime.now(UTC)
    if body.quota_verified_at > now or body.publisher_reviewed_at > now:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Review timestamps cannot be in the future",
        )
    policy_contract = ProviderPolicy(
        capability=ProviderCapability.ETF_HOLDINGS,
        quota_contract=body.quota_contract,
        quota_scope=body.quota_scope,
        quota_source=body.quota_source,
        quota_verified_at=body.quota_verified_at,
    )
    missing_contract = quota_contract_missing_dimensions(policy_contract)
    if missing_contract:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"reason": "reviewed quota contract is incomplete", "missing": missing_contract},
        )

    reviewed_usage_tracking = body.usage_tracking.model_dump(mode="json")
    usage_source = DataSource(
        name=provider_name,
        config={"usage_tracking": reviewed_usage_tracking},
    )
    for operation in body.operations:
        if not provider_contract_operation_cost_known(
            policy_contract,
            usage_source,
            operation,
            usage_identity="provisioning-review-validation",
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Reviewed quota and operation costs are incomplete for {operation}",
            )

    existing = (
        await db.execute(select(DataSource).where(DataSource.name == provider_name))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Provider source already exists; provisioning never overwrites reviewed rows",
        )

    review = {
        "https_hosts": body.https_hosts,
        "operations": {
            operation: evidence.model_dump(mode="json")
            for operation, evidence in body.operations.items()
        },
        "account_scope": expected_scope,
        "evidence_source": body.publisher_evidence_source,
        "evidence_version": body.publisher_evidence_version,
        "reviewed_at": body.publisher_reviewed_at.isoformat(),
        "reviewed_by_user_id": current_user.id,
        "quota_review": {
            "evidence_source": body.quota_source,
            "evidence_version": body.quota_evidence_version,
            "verified_at": body.quota_verified_at.isoformat(),
            "reviewed_by_user_id": current_user.id,
        },
        "entitlement_review": {
            "evidence_source": body.entitlement.evidence_source,
            "evidence_version": body.entitlement.evidence_version,
            "reviewed_at": body.entitlement.reviewed_at.isoformat(),
            "reviewed_by_user_id": current_user.id,
        },
    }
    data_source = DataSource(
        name=provider_name,
        description=body.description,
        is_active=True,
        supported_capabilities=[ProviderCapability.ETF_HOLDINGS.value],
        config={
            "capabilities": [ProviderCapability.ETF_HOLDINGS.value],
            "usage_tracking": reviewed_usage_tracking,
            "etf_holdings_review": review,
        },
    )
    db.add(data_source)
    await db.flush()

    policy = ProviderPolicy(
        data_source_id=data_source.id,
        capability=ProviderCapability.ETF_HOLDINGS,
        is_enabled=False,
        is_pinned=False,
        auto_weight_enabled=False,
        max_concurrency=body.max_concurrency,
        tokens_per_minute=body.tokens_per_minute,
        burst_capacity=body.burst_capacity,
        cooldown_seconds=body.cooldown_seconds,
        quota_contract=body.quota_contract,
        quota_scope=body.quota_scope,
        quota_source=body.quota_source,
        quota_verified_at=body.quota_verified_at,
        freshness_seconds=body.freshness_seconds,
        effective_score=Decimal("0"),
    )
    entitlement = ProviderEntitlement(
        data_source_id=data_source.id,
        capability=ProviderCapability.ETF_HOLDINGS,
        configured_plan=body.entitlement.configured_plan,
        is_free=body.entitlement.is_free,
        authentication_required=body.entitlement.authentication_required,
        usage_terms=body.entitlement.usage_terms,
        redistribution_allowed=body.entitlement.redistribution_allowed,
        quota_policy=body.entitlement.quota_policy,
        history_depth=body.entitlement.history_depth,
        venue_coverage=body.entitlement.venue_coverage,
        freshness_semantics=body.entitlement.freshness_semantics,
        enabled_environments=body.entitlement.enabled_environments,
        effective_at=body.entitlement.effective_at,
        review_due_at=body.entitlement.review_due_at,
        live_probe_status="not_run",
        revision=1,
    )
    health = ProviderHealthState(
        data_source_id=data_source.id,
        capability=ProviderCapability.ETF_HOLDINGS,
        failure_streak=0,
        ewma_latency_ms=Decimal("0"),
        ewma_success_rate=Decimal("0"),
        ewma_completeness=Decimal("0"),
        ewma_freshness=Decimal("0"),
        ewma_consistency=Decimal("0"),
        observed_score=Decimal("0"),
    )
    db.add_all([policy, entitlement, health])
    await db.flush()
    await record_entitlement_revision(
        db,
        entitlement,
        change_reason=f"etf_publisher_provision:{body.entitlement.evidence_version}"[:240],
    )
    return {
        "provider": provider_name,
        "capability": ProviderCapability.ETF_HOLDINGS.value,
        "data_source_id": data_source.id,
        "policy_enabled": False,
        "live_probe_status": entitlement.live_probe_status,
        "routable": False,
    }


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
            "revision": entitlement.revision,
        }
        for entitlement, source in rows
    ]


@router.get("/entitlements/history/{provider_name}/{capability}")
async def get_provider_entitlement_history(
    provider_name: str,
    capability: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        capability_enum = ProviderCapability(capability)
    except ValueError as exc:
        raise HTTPException(400, f"Unknown provider capability '{capability}'") from exc
    await seed_provider_runtime(db)
    rows = (
        (
            await db.execute(
                select(ProviderEntitlementRevision)
                .join(DataSource, DataSource.id == ProviderEntitlementRevision.data_source_id)
                .where(
                    DataSource.name == provider_name,
                    ProviderEntitlementRevision.capability == capability_enum,
                )
                .order_by(ProviderEntitlementRevision.revision.desc())
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise HTTPException(
            404, f"No entitlement history found for '{provider_name}' / '{capability}'"
        )
    return [
        {
            "provider": provider_name,
            "capability": row.capability.value,
            "revision": row.revision,
            "configured_plan": row.configured_plan,
            "is_free": row.is_free,
            "authentication_required": row.authentication_required,
            "usage_terms": row.usage_terms,
            "redistribution_allowed": row.redistribution_allowed,
            "quota_policy": row.quota_policy,
            "history_depth": row.history_depth,
            "venue_coverage": row.venue_coverage,
            "freshness_semantics": row.freshness_semantics,
            "enabled_environments": row.enabled_environments,
            "effective_at": row.effective_at,
            "review_due_at": row.review_due_at,
            "live_probe_status": row.live_probe_status,
            "change_reason": row.change_reason,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.patch("/entitlements/{provider_name}/{capability}")
async def update_provider_entitlement(
    provider_name: str,
    capability: str,
    body: ProviderEntitlementUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
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
    changes = body.model_dump(exclude_unset=True)
    changed = any(
        getattr(entitlement, field_name) != value for field_name, value in changes.items()
    )
    for field_name, value in changes.items():
        setattr(entitlement, field_name, value)
    if changed:
        entitlement.revision = int(entitlement.revision or 1) + 1
        await db.flush()
        await record_entitlement_revision(db, entitlement, change_reason="api_patch")
    await db.flush()
    return {"ok": True, "revision": entitlement.revision}


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


@router.get("/usage/account")
async def get_provider_account_usage(
    provider: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Return provider-native account counters retained across sessions."""

    return await list_provider_account_usage(db, provider_name=provider, limit=limit)


@router.post("/usage/account/refresh")
async def refresh_provider_account_usage_endpoint(
    provider: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Explicitly poll one reviewed provider account-usage endpoint."""

    return await refresh_provider_account_usage(db, provider_name=provider)


@router.get("/availability")
async def get_provider_availability(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Latest durable daily/weekly probe result for Settings and operators."""
    return await latest_availability(db)


@router.get("/availability/runs")
async def get_provider_availability_runs(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return recent sweep status for the authenticated Settings operator view."""
    return await recent_availability_runs(db, limit=limit)


@router.post("/availability/run")
async def run_provider_availability(
    mode: Literal["daily_core", "weekly_supported_sweep"] = "daily_core",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if not settings.PROVIDER_AVAILABILITY_LIVE_ENABLED:
        raise HTTPException(409, "Live provider probes are disabled by deployment configuration")
    return await run_availability_probes(db, mode, application_version=settings.APP_ENV)


@router.get("/datasets/stale")
async def get_stale_provider_datasets(
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await list_stale_dataset_states(db, limit=limit)


@router.get("/reconciliation/issues")
async def get_reconciliation_issues(
    status: Literal["open", "resolved", "ignored"] = "open",
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Return provider observations that require explicit identity review."""
    issues = await list_reconciliation_issues(db, status=status, limit=limit)
    return [
        {
            "id": issue.id,
            "provider": issue.data_source.name if issue.data_source else None,
            "provider_symbol": issue.provider_symbol,
            "issue_type": issue.issue_type,
            "fingerprint": issue.fingerprint,
            "status": issue.status,
            "candidates": issue.candidates,
            "payload": issue.payload,
            "observed_at": issue.observed_at,
            "resolved_at": issue.resolved_at,
            "resolution": issue.resolution,
            "resolved_by": (
                {
                    "id": issue.resolved_by.id,
                    "username": issue.resolved_by.username,
                    "display_name": issue.resolved_by.display_name,
                }
                if issue.resolved_by
                else None
            ),
        }
        for issue in issues
    ]


@router.patch("/reconciliation/issues/{issue_id}")
async def update_reconciliation_issue(
    issue_id: int,
    body: ReconciliationIssueUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    issue = (
        await db.execute(
            select(InstrumentReconciliationIssue).where(
                InstrumentReconciliationIssue.id == issue_id
            )
        )
    ).scalar_one_or_none()
    if issue is None:
        raise HTTPException(404, f"Reconciliation issue {issue_id} was not found")
    await resolve_reconciliation_issue(
        db,
        issue,
        status=body.status,
        resolution=body.resolution,
        resolved_by_user_id=current_user.id,
    )
    return {
        "ok": True,
        "id": issue.id,
        "status": issue.status,
        "resolved_at": issue.resolved_at,
        "resolution": issue.resolution,
        "resolved_by": {
            "id": current_user.id,
            "username": current_user.username,
            "display_name": current_user.display_name,
        }
        if issue.resolved_by_user_id
        else None,
    }


@router.patch("/policies/{provider_name}/{capability}")
async def update_provider_policy(
    provider_name: str,
    capability: str,
    body: ProviderPolicyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
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

    changes = body.model_dump(exclude_unset=True)
    quota_fields = {"max_concurrency", "tokens_per_minute", "burst_capacity", "cooldown_seconds"}
    candidate_contract_missing: list[str] = []
    if "quota_contract" in changes and changes.get("quota_contract") is not None:
        candidate_contract = changes.get("quota_contract")
        if not isinstance(candidate_contract, dict):
            raise HTTPException(400, "quota_contract must be a JSON object")
        candidate_policy = ProviderPolicy(
            capability=capability_enum,
            quota_contract=candidate_contract,
            # Validate the complete replacement as it will exist after the
            # patch. Existing provenance may be reused when omitted, while
            # an explicit null remains a deliberate fail-closed removal.
            quota_scope=changes.get("quota_scope", policy.quota_scope),
            quota_source=changes.get("quota_source", policy.quota_source),
        )
        candidate_contract_missing = quota_contract_missing_dimensions(candidate_policy)
    candidate_structural_missing = [
        item
        for item in candidate_contract_missing
        if not item.startswith(
            (
                "quota_contract.unknown_dimensions.",
                "quota_contract.untracked_constraints.",
            )
        )
        and not item.endswith(".reset.unresolved")
    ]
    if quota_fields.intersection(changes):
        if "quota_contract" not in changes:
            raise HTTPException(
                400,
                "Provider limits require an explicit replacement documentation-backed "
                "quota_contract; individual numeric defaults are not accepted",
            )
        if candidate_structural_missing:
            raise HTTPException(
                400,
                "quota_contract is incomplete: " + ", ".join(candidate_structural_missing),
            )
    if "quota_contract" in changes and changes.get("quota_contract") is not None:
        if candidate_structural_missing:
            raise HTTPException(
                400,
                "quota_contract is incomplete: " + ", ".join(candidate_structural_missing),
            )
        if not candidate_contract_missing:
            quota_scope = str(changes.get("quota_scope", policy.quota_scope) or "").strip()
            quota_source = str(changes.get("quota_source", policy.quota_source) or "").strip()
            if not quota_scope:
                raise HTTPException(400, "Complete quota contracts require quota_scope")
            if not quota_source:
                raise HTTPException(400, "Complete quota contracts require quota_source provenance")
    for field_name, value in changes.items():
        setattr(policy, field_name, value)
    if "quota_contract" in changes:
        # A contract containing unknown/untracked dimensions is useful audit
        # evidence, but it is not a verified admission contract. Keep the
        # timestamp empty so admin diagnostics cannot present a fail-closed
        # policy as documentation-approved.
        policy.quota_verified_at = (
            datetime.now(UTC)
            if changes.get("quota_contract") is not None and not candidate_contract_missing
            else None
        )
    elif {"quota_scope", "quota_source"}.intersection(changes):
        # Provenance edits without an explicit complete replacement contract
        # cannot inherit the previous review timestamp. The policy may remain
        # useful audit state, but routing must wait for a new reviewed
        # contract to be submitted.
        policy.quota_verified_at = None
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
