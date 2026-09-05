from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, TypeVar

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.data_source import DataSource
from app.models.provider_runtime import (
    ProviderCapability,
    ProviderEntitlement,
    ProviderEntitlementRevision,
    ProviderHealthState,
    ProviderPolicy,
    ProviderRequestLog,
)
from app.providers import (
    ensure_data_source,
    get_provider,
    list_provider_capabilities,
    provider_configuration_required,
    provider_is_configured,
    supported_provider_names,
)
from app.providers.errors import ProviderNotConfiguredError, ProviderRateLimitError
from app.services.provider_support import (
    SUPPORT_STATUS_SUPPORTED,
    SUPPORT_STATUS_UNKNOWN,
    SUPPORT_STATUS_UNSUPPORTED,
    get_provider_binding_ids,
    get_provider_support_map,
    record_provider_support,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

_ALPHA = Decimal("0.2")
_token_buckets: dict[tuple[str, str], tuple[tuple[int, int], TokenBucket]] = {}
_semaphores: dict[tuple[str, str], tuple[int, asyncio.Semaphore]] = {}
_DEFAULT_SCORE_FLOOR = Decimal("0")
_DEFAULT_SCORE_CEILING = Decimal("100")
_DEFAULT_LEARNED_WEIGHT = Decimal("0")
_DEFAULT_EFFECTIVE_SCORE = Decimal("0")
_DEFAULT_BASE_PRIORITY = 100

_ENTITLEMENT_FIELDS = (
    "configured_plan",
    "is_free",
    "authentication_required",
    "usage_terms",
    "redistribution_allowed",
    "quota_policy",
    "history_depth",
    "venue_coverage",
    "freshness_semantics",
    "enabled_environments",
    "effective_at",
    "review_due_at",
    "live_probe_status",
)


async def record_entitlement_revision(
    db: AsyncSession,
    entitlement: ProviderEntitlement,
    *,
    change_reason: str | None = None,
) -> ProviderEntitlementRevision:
    """Persist the current entitlement state once for its immutable revision."""
    revision = int(entitlement.revision or 1)
    existing = (
        await db.execute(
            select(ProviderEntitlementRevision).where(
                ProviderEntitlementRevision.data_source_id == entitlement.data_source_id,
                ProviderEntitlementRevision.capability == entitlement.capability,
                ProviderEntitlementRevision.revision == revision,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    snapshot = ProviderEntitlementRevision(
        data_source_id=entitlement.data_source_id,
        capability=entitlement.capability,
        revision=revision,
        **{
            field_name: (
                dict(getattr(entitlement, field_name) or {})
                if field_name == "quota_policy"
                else list(getattr(entitlement, field_name) or [])
                if field_name == "enabled_environments"
                else getattr(entitlement, field_name)
            )
            for field_name in _ENTITLEMENT_FIELDS
        },
        change_reason=change_reason,
    )
    db.add(snapshot)
    await db.flush()
    return snapshot


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite's naive datetimes before entitlement comparisons."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


@dataclass(slots=True)
class ResolvedProvider:
    provider_name: str
    provider: Any
    data_source: DataSource
    policy: ProviderPolicy
    health: ProviderHealthState
    support_status: str = SUPPORT_STATUS_UNKNOWN
    has_symbol_binding: bool = False
    entitlement: ProviderEntitlement | None = None


@dataclass(slots=True)
class ProviderExecutionResult:
    provider_name: str
    data_source: DataSource
    policy: ProviderPolicy
    health: ProviderHealthState
    result: Any


class ProviderNoDataError(LookupError):
    """Raised when providers resolve successfully but none return usable data."""


class ProviderQuotaUnknownError(RuntimeError):
    """Raised when no documentation-backed quota contract is available."""


def _operation_family(operation: str) -> str:
    return operation.split(":", 1)[0].strip() or operation


def _entitlement_seed(provider_name: str, capability: ProviderCapability) -> dict[str, Any]:
    """Return the reviewed free-source declaration for one capability."""
    raw = settings.PROVIDER_ENTITLEMENT_SEEDS.get(provider_name) or {}
    if not isinstance(raw, dict):
        return {}
    base = {key: value for key, value in raw.items() if key != "capabilities"}
    capability_overrides = raw.get("capabilities")
    if isinstance(capability_overrides, dict):
        override = capability_overrides.get(capability.value)
        if isinstance(override, dict):
            base.update(override)
    return {
        key: value
        for key, value in base.items()
        if key
        in {
            "configured_plan",
            "is_free",
            "authentication_required",
            "usage_terms",
            "redistribution_allowed",
            "quota_policy",
            "history_depth",
            "venue_coverage",
            "freshness_semantics",
            "enabled_environments",
            "effective_at",
            "review_due_at",
            "live_probe_status",
        }
    }


def _usage_tracking_config(data_source: DataSource) -> dict[str, Any]:
    config = dict(data_source.config or {})
    tracking = config.get("usage_tracking") or {}
    return tracking if isinstance(tracking, dict) else {}


def _usage_cost_for_operation(data_source: DataSource, operation: str) -> tuple[str, str, Decimal]:
    tracking = _usage_tracking_config(data_source)
    mode = str(tracking.get("mode") or "call_count")
    unit_label = str(tracking.get("unit_label") or "requests")
    operation_costs = tracking.get("operation_costs") or {}
    family = _operation_family(operation)
    raw_cost = 1
    if isinstance(operation_costs, dict):
        raw_cost = operation_costs.get(family, operation_costs.get(operation, 1))
    try:
        cost = Decimal(str(raw_cost))
    except Exception:
        cost = Decimal("1")
    if cost <= 0:
        cost = Decimal("1")
    return mode, unit_label, cost


def provider_contract_operation_cost_known(
    policy: ProviderPolicy,
    data_source: DataSource,
    operation: str | None = None,
) -> bool:
    """Return whether a quota contract can be safely charged for this call.

    Providers whose allowance is weighted per endpoint, or whose contract
    explicitly requires credit costs, must not silently fall back to one
    request == one unit. They remain visible to operators but are non-routable
    until the operation-cost map is populated.
    """

    contract = dict(policy.quota_contract or {})
    if not (
        contract.get("dynamic_endpoint_weights")
        or contract.get("operation_costs_required")
    ):
        return True
    tracking = _usage_tracking_config(data_source)
    costs = tracking.get("operation_costs")
    if not isinstance(costs, dict) or not costs:
        return False
    if operation is None:
        # A provider may have a cost table while the caller has not named the
        # operation.  Selecting it anyway would silently charge one request
        # for an unknown endpoint weight, so generic workload selection stays
        # fail-closed.
        return False
    family = _operation_family(operation)
    return family in costs or operation in costs


class TokenBucket:
    def __init__(self, rate_per_minute: int, burst_capacity: int):
        self.rate_per_second = max(rate_per_minute, 1) / 60.0
        self.capacity = max(burst_capacity, 1)
        self.tokens = float(self.capacity)
        self.last_refill = time.monotonic()

    def try_acquire(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.last_refill = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_per_second)
        if self.tokens < 1:
            return False
        self.tokens -= 1
        return True


def _ewma(previous: Decimal, current: Decimal) -> Decimal:
    if previous == Decimal("0"):
        return current
    return (previous * (Decimal("1") - _ALPHA)) + (current * _ALPHA)


def _capability_seed_order() -> dict[ProviderCapability, list[str]]:
    seeds: dict[ProviderCapability, list[str]] = {
        ProviderCapability.INSTRUMENT_SEARCH: [settings.DEFAULT_METADATA_PROVIDER],
        ProviderCapability.INSTRUMENT_METADATA: [settings.DEFAULT_METADATA_PROVIDER],
        ProviderCapability.PRICE_HISTORY: [settings.DEFAULT_MARKET_DATA_PROVIDER],
        ProviderCapability.LATEST_PRICE: [settings.DEFAULT_MARKET_DATA_PROVIDER],
        ProviderCapability.INSTRUMENT_EVENTS: [settings.DEFAULT_EVENT_PROVIDER],
        ProviderCapability.INSTRUMENT_IDENTIFIERS: list(settings.IDENTIFIER_PROVIDER_PRIORITY),
        ProviderCapability.UNIVERSE_DISCOVERY: [settings.DEFAULT_DISCOVERY_PROVIDER],
        ProviderCapability.OPTION_CHAIN: [settings.DEFAULT_OPTIONS_PROVIDER],
        ProviderCapability.OPTION_QUOTE_HISTORY: list(
            settings.OPTION_QUOTE_HISTORY_PROVIDER_PRIORITY
        )
        or [settings.DEFAULT_OPTIONS_PROVIDER],
    }
    for key, providers in settings.PROVIDER_CHAIN_SEEDS.items():
        try:
            capability = ProviderCapability(key)
        except ValueError:
            continue
        seeds[capability] = providers
    return seeds


def _base_priority(provider_name: str, ordered_providers: list[str]) -> int:
    try:
        return (ordered_providers.index(provider_name) + 1) * 10
    except ValueError:
        return 999


def _decimal_or(value: Decimal | None, default: Decimal) -> Decimal:
    return default if value is None else value


def _int_or(value: int | None, default: int) -> int:
    return default if value is None else value


def _effective_score(policy: ProviderPolicy, health: ProviderHealthState) -> Decimal:
    base_priority = _int_or(policy.base_priority, _DEFAULT_BASE_PRIORITY)
    score_floor = _decimal_or(policy.score_floor, _DEFAULT_SCORE_FLOOR)
    score_ceiling = _decimal_or(policy.score_ceiling, _DEFAULT_SCORE_CEILING)
    base_score = Decimal(max(0, 100 - base_priority))
    if not policy.auto_weight_enabled:
        return max(score_floor, min(score_ceiling, base_score))

    success_rate = health.ewma_success_rate or Decimal("0")
    completeness = health.ewma_completeness or Decimal("0")
    freshness = health.ewma_freshness or Decimal("0")
    consistency = health.ewma_consistency or Decimal("0")
    learned_weight = _decimal_or(policy.learned_weight, _DEFAULT_LEARNED_WEIGHT)
    latency_ms = health.ewma_latency_ms or Decimal("0")
    latency_penalty = min(Decimal("30"), latency_ms / Decimal("1000"))
    health_bonus = (
        (success_rate * Decimal("25"))
        + (completeness * Decimal("20"))
        + (freshness * Decimal("10"))
        + (consistency * Decimal("10"))
        - latency_penalty
    )
    candidate = base_score + learned_weight + health_bonus
    return max(score_floor, min(score_ceiling, candidate))


def _apply_policy_defaults(
    policy: ProviderPolicy,
    *,
    provider_name: str,
    providers: list[str],
    freshness_seconds: int,
    rate_seed: dict[str, Any],
) -> None:
    if not policy.is_pinned:
        policy.base_priority = _base_priority(provider_name, providers)
    # Quota and concurrency values are external-provider facts, not local
    # tuning defaults.  Leave them NULL when the seed does not explicitly
    # declare a documented value; the resolver will then fail closed.
    for field_name in ("max_concurrency", "tokens_per_minute", "burst_capacity", "cooldown_seconds"):
        if getattr(policy, field_name) is None and rate_seed.get(field_name) is not None:
            setattr(policy, field_name, rate_seed[field_name])
    if policy.quota_contract is None and rate_seed.get("quota_contract"):
        policy.quota_contract = dict(rate_seed["quota_contract"])
    if policy.quota_scope is None and rate_seed.get("quota_scope"):
        policy.quota_scope = str(rate_seed["quota_scope"])
    if policy.quota_source is None and rate_seed.get("quota_source"):
        policy.quota_source = str(rate_seed["quota_source"])
    if policy.quota_verified_at is None and policy.quota_contract:
        policy.quota_verified_at = datetime.now(UTC)
    policy.freshness_seconds = _int_or(policy.freshness_seconds, freshness_seconds)
    if policy.score_floor is None:
        policy.score_floor = _DEFAULT_SCORE_FLOOR
    if policy.score_ceiling is None:
        policy.score_ceiling = _DEFAULT_SCORE_CEILING
    if policy.learned_weight is None:
        policy.learned_weight = _DEFAULT_LEARNED_WEIGHT
    if policy.effective_score is None:
        policy.effective_score = _DEFAULT_EFFECTIVE_SCORE


def _bucket_key(provider_name: str, capability: ProviderCapability) -> tuple[str, str]:
    return (provider_name, capability.value)


def _get_bucket(policy: ProviderPolicy, provider_name: str) -> TokenBucket:
    if policy.tokens_per_minute is None or policy.burst_capacity is None:
        raise ProviderQuotaUnknownError(
            f"{provider_name}/{policy.capability.value} has no verified minute bucket"
        )
    key = _bucket_key(provider_name, policy.capability)
    config = (policy.tokens_per_minute, policy.burst_capacity)
    cached = _token_buckets.get(key)
    if cached is None or cached[0] != config:
        bucket = TokenBucket(policy.tokens_per_minute, policy.burst_capacity)
        _token_buckets[key] = (config, bucket)
        return bucket
    bucket = cached[1]
    return bucket


def _get_semaphore(policy: ProviderPolicy, provider_name: str) -> asyncio.Semaphore:
    # Serialising an unknown-concurrency provider is a local safety measure,
    # not a claim about the vendor's entitlement.  The external quota contract
    # remains the source of truth for admission and is never populated with 1.
    configured_concurrency = policy.max_concurrency if policy.max_concurrency and policy.max_concurrency > 0 else 1
    key = _bucket_key(provider_name, policy.capability)
    cached = _semaphores.get(key)
    if cached is None or cached[0] != configured_concurrency:
        sem = asyncio.Semaphore(configured_concurrency)
        _semaphores[key] = (configured_concurrency, sem)
        return sem
    sem = cached[1]
    return sem


def quota_dimensions(policy: ProviderPolicy) -> list[dict[str, Any]]:
    """Return only complete, positive, explicitly documented dimensions.

    A partial contract is not safer than an unknown contract: silently
    discarding one malformed dimension could admit requests that exceed the
    provider's real allowance. Require reset semantics plus source/scope/unit
    evidence for every declared dimension before routing.
    """

    contract = policy.quota_contract or {}
    if not isinstance(contract, dict) or not str(contract.get("reset") or "").strip():
        return []
    dimensions = contract.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        return []
    result: list[dict[str, Any]] = []
    for item in dimensions:
        if not isinstance(item, dict):
            return []
        try:
            limit = int(item.get("limit"))
            window_seconds = int(item.get("window_seconds"))
        except (TypeError, ValueError):
            return []
        if (
            limit <= 0
            or window_seconds <= 0
            or not str(item.get("name") or "").strip()
            or not str(item.get("unit") or "").strip()
            or not str(item.get("source") or "").strip()
            or not str(item.get("scope") or policy.quota_scope or "").strip()
        ):
            return []
        result.append(
            {
                **item,
                "name": str(item["name"]),
                "limit": limit,
                "window_seconds": window_seconds,
                "unit": str(item.get("unit") or "requests"),
                "scope": str(item.get("scope") or policy.quota_scope or "unknown"),
            }
        )
    return result


def quota_contract_missing_dimensions(policy: ProviderPolicy) -> list[str]:
    """Return exact quota-contract fields that prevent safe admission."""

    contract = policy.quota_contract
    if not isinstance(contract, dict):
        return ["quota_contract", "quota_scope", "quota_source"]

    missing: list[str] = []
    if not str(contract.get("reset") or "").strip():
        missing.append("quota_contract.reset")
    dimensions = contract.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        missing.append("quota_contract.dimensions")
        return missing

    for index, item in enumerate(dimensions):
        prefix = f"quota_contract.dimensions[{index}]"
        if not isinstance(item, dict):
            missing.append(prefix)
            continue
        for field_name in ("name", "limit", "window_seconds", "unit", "scope", "source"):
            value = item.get(field_name)
            if field_name in {"limit", "window_seconds"}:
                try:
                    valid = int(value) > 0
                except (TypeError, ValueError):
                    valid = False
            else:
                valid = bool(str(value or "").strip())
            if not valid:
                missing.append(f"{prefix}.{field_name}")
    return missing


def provider_contract_operation_costs_configured(
    policy: ProviderPolicy, data_source: DataSource
) -> bool:
    """Whether a weighted/credit contract has an operation-cost map."""

    contract = dict(policy.quota_contract or {})
    if not (contract.get("dynamic_endpoint_weights") or contract.get("operation_costs_required")):
        return True
    tracking = _usage_tracking_config(data_source)
    costs = tracking.get("operation_costs")
    return bool(isinstance(costs, dict) and costs)


def policy_has_known_quota(policy: ProviderPolicy) -> bool:
    """Whether this policy has a complete contract suitable for routing."""

    return bool(quota_dimensions(policy))


def _retry_at_from_headers(headers: Any, *, now: datetime | None = None) -> datetime | None:
    """Parse standard retry/reset headers without inventing a provider delay."""

    if headers is None:
        return None
    normalized = {str(key).lower(): str(value) for key, value in headers.items()}
    current = now or datetime.now(UTC)
    retry_after = normalized.get("retry-after")
    if retry_after:
        try:
            seconds = float(retry_after)
            if seconds >= 0:
                return current + timedelta(seconds=seconds)
        except ValueError:
            try:
                parsed = datetime.strptime(retry_after, "%a, %d %b %Y %H:%M:%S GMT")
                return parsed.replace(tzinfo=UTC)
            except ValueError:
                pass
    for name in ("x-ratelimit-reset", "x-rate-limit-reset", "ratelimit-reset"):
        value = normalized.get(name)
        if not value:
            continue
        try:
            raw = float(value)
        except ValueError:
            continue
        # Providers use both Unix epochs and relative seconds for this header.
        return datetime.fromtimestamp(raw, tz=UTC) if raw > 1_000_000_000 else current + timedelta(seconds=max(0, raw))
    return None


def provider_rate_limit_error(provider_name: str, exc: Exception, *, scope: str | None = None) -> ProviderRateLimitError | None:
    """Convert an HTTP 429/418/quota response to a typed capacity error."""

    response = exc.response if isinstance(exc, httpx.HTTPStatusError) else None
    status_code = getattr(response, "status_code", None)
    message = str(exc)
    lower = message.lower()
    is_quota = status_code in {418, 429} or any(
        marker in lower for marker in ("rate limit", "rate_limit", "too many requests", "quota exceeded", "quota limit")
    )
    if not is_quota:
        return None
    headers = dict(getattr(response, "headers", {}) or {})
    return ProviderRateLimitError(
        provider_name,
        message or f"{provider_name} rate limit exceeded",
        retry_at=_retry_at_from_headers(headers),
        status_code=status_code,
        scope=scope,
        headers=headers,
    )


async def seed_provider_runtime(db: AsyncSession) -> None:
    ordered = _capability_seed_order()
    for provider_name in supported_provider_names():
        await ensure_data_source(db, provider_name)

    capability_providers: dict[ProviderCapability, list[str]] = {
        capability: [] for capability in ProviderCapability
    }
    for provider_name in supported_provider_names():
        provider_capabilities = set(list_provider_capabilities(provider_name))
        for capability in ProviderCapability:
            if capability.value in provider_capabilities:
                capability_providers[capability].append(provider_name)

    # Provider adapters can lose a capability between deployments while the
    # policy row remains in the database. Disable those stale rows during the
    # normal seed pass so diagnostics and future resolution agree with the
    # registry; resolution also applies the same check defensively.
    existing_policies = (
        await db.execute(select(ProviderPolicy, DataSource).join(DataSource))
    ).all()
    for policy, data_source in existing_policies:
        if policy.capability.value not in set(
            list_provider_capabilities(data_source.name)
            if data_source.name in supported_provider_names()
            else []
        ):
            policy.is_enabled = False

    for capability, supported_providers in capability_providers.items():
        preferred_order = ordered.get(capability, [])
        providers = preferred_order + [
            provider_name
            for provider_name in supported_providers
            if provider_name not in preferred_order
        ]
        for provider_name in providers:
            data_source = await ensure_data_source(db, provider_name)
            entitlement_seed = _entitlement_seed(provider_name, capability)
            policy = (
                await db.execute(
                    select(ProviderPolicy).where(
                        ProviderPolicy.data_source_id == data_source.id,
                        ProviderPolicy.capability == capability,
                    )
                )
            ).scalar_one_or_none()
            rate_seed = settings.PROVIDER_RATE_LIMIT_SEEDS.get(provider_name, {})
            freshness = settings.PROVIDER_FRESHNESS_SEEDS.get(
                capability.value,
                3600
                if capability
                not in {ProviderCapability.PRICE_HISTORY, ProviderCapability.LATEST_PRICE}
                else 300,
            )
            if policy is None:
                policy = ProviderPolicy(
                    data_source_id=data_source.id,
                    capability=capability,
                    is_enabled=True,
                    base_priority=_base_priority(provider_name, providers),
                    max_concurrency=rate_seed.get("max_concurrency"),
                    tokens_per_minute=rate_seed.get("tokens_per_minute"),
                    burst_capacity=rate_seed.get("burst_capacity"),
                    cooldown_seconds=rate_seed.get("cooldown_seconds"),
                    quota_contract=rate_seed.get("quota_contract"),
                    quota_scope=rate_seed.get("quota_scope"),
                    quota_source=rate_seed.get("quota_source"),
                    quota_verified_at=datetime.now(UTC)
                    if rate_seed.get("quota_contract")
                    else None,
                    freshness_seconds=freshness,
                )
                db.add(policy)
            entitlement = (
                await db.execute(
                    select(ProviderEntitlement).where(
                        ProviderEntitlement.data_source_id == data_source.id,
                        ProviderEntitlement.capability == capability,
                    )
                )
            ).scalar_one_or_none()
            entitlement_was_new = entitlement is None
            if entitlement is None:
                entitlement = ProviderEntitlement(
                    data_source_id=data_source.id,
                    capability=capability,
                    configured_plan=str(entitlement_seed.get("configured_plan") or "unreviewed"),
                    # Unknown terms must never become an implicitly usable
                    # free source. Only an explicit entitlement seed opts a
                    # capability into a runtime chain.
                    is_free=bool(entitlement_seed.get("is_free", False)),
                    authentication_required=bool(
                        entitlement_seed.get("authentication_required", False)
                    ),
                    usage_terms=entitlement_seed.get("usage_terms"),
                    redistribution_allowed=bool(
                        entitlement_seed.get("redistribution_allowed", False)
                    ),
                    quota_policy=dict(entitlement_seed.get("quota_policy") or {}),
                    history_depth=entitlement_seed.get("history_depth"),
                    venue_coverage=entitlement_seed.get("venue_coverage"),
                    freshness_semantics=entitlement_seed.get("freshness_semantics"),
                    enabled_environments=list(entitlement_seed.get("enabled_environments") or []),
                    effective_at=entitlement_seed.get("effective_at"),
                    review_due_at=entitlement_seed.get("review_due_at"),
                    live_probe_status=str(entitlement_seed.get("live_probe_status") or "not_run"),
                )
                db.add(entitlement)
                await db.flush()
            if rate_seed.get("quota_contract"):
                quota_policy = dict(entitlement.quota_policy or {})
                quota_policy.setdefault("contract", dict(rate_seed["quota_contract"]))
                entitlement.quota_policy = quota_policy
            if (
                not entitlement_was_new
                and entitlement.configured_plan == "unreviewed"
                and entitlement_seed
            ):
                # Upgrade rows created by older builds without overwriting an
                # operator-reviewed entitlement.
                prior_values = {
                    field_name: getattr(entitlement, field_name) for field_name in entitlement_seed
                }
                for field_name, value in entitlement_seed.items():
                    setattr(entitlement, field_name, value)
                if any(
                    prior_values[field_name] != value
                    for field_name, value in entitlement_seed.items()
                ):
                    entitlement.revision = int(entitlement.revision or 1) + 1
            elif entitlement.revision is None or entitlement.revision < 1:
                entitlement.revision = 1
            if entitlement.revision is None or entitlement.revision < 1:
                entitlement.revision = 1
            await record_entitlement_revision(db, entitlement, change_reason="runtime_seed")
            _apply_policy_defaults(
                policy,
                provider_name=provider_name,
                providers=providers,
                freshness_seconds=freshness,
                rate_seed=rate_seed,
            )

            health = (
                await db.execute(
                    select(ProviderHealthState).where(
                        ProviderHealthState.data_source_id == data_source.id,
                        ProviderHealthState.capability == capability,
                    )
                )
            ).scalar_one_or_none()
            if health is None:
                health = ProviderHealthState(
                    data_source_id=data_source.id,
                    capability=capability,
                    observed_score=Decimal("0"),
                )
                db.add(health)
            if health.ewma_latency_ms is None:
                health.ewma_latency_ms = Decimal("0")
            if health.ewma_success_rate is None:
                health.ewma_success_rate = Decimal("1")
            if health.ewma_completeness is None:
                health.ewma_completeness = Decimal("1")
            if health.ewma_freshness is None:
                health.ewma_freshness = Decimal("1")
            if health.ewma_consistency is None:
                health.ewma_consistency = Decimal("1")
            if health.observed_score is None:
                health.observed_score = Decimal("0")
            policy.effective_score = _effective_score(policy, health)
            health.observed_score = policy.effective_score

    await db.flush()


async def resolve_provider_chain(
    db: AsyncSession,
    capability: ProviderCapability,
    *,
    instrument_id: int | None = None,
    operation: str | None = None,
) -> list[ResolvedProvider]:
    await seed_provider_runtime(db)
    rows = (
        await db.execute(
            select(ProviderPolicy, ProviderHealthState, DataSource, ProviderEntitlement)
            .join(DataSource, DataSource.id == ProviderPolicy.data_source_id)
            .join(
                ProviderEntitlement,
                (ProviderEntitlement.data_source_id == ProviderPolicy.data_source_id)
                & (ProviderEntitlement.capability == ProviderPolicy.capability),
            )
            .join(
                ProviderHealthState,
                (ProviderHealthState.data_source_id == ProviderPolicy.data_source_id)
                & (ProviderHealthState.capability == ProviderPolicy.capability),
            )
            .where(
                ProviderPolicy.capability == capability,
                ProviderPolicy.is_enabled.is_(True),
                or_(
                    ProviderEntitlement.is_free.is_(True),
                    settings.ALLOW_PAID_PROVIDER_ROUTING,
                ),
            )
        )
    ).all()
    now = datetime.now(UTC)
    support_map = (
        await get_provider_support_map(db, instrument_id, capability)
        if instrument_id is not None
        else {}
    )
    binding_ids = (
        await get_provider_binding_ids(db, instrument_id) if instrument_id is not None else set()
    )
    resolved: list[ResolvedProvider] = []
    current_environment = settings.APP_ENV.strip().lower()
    for policy, health, data_source, entitlement in rows:
        # ``ALLOW_PAID_PROVIDER_ROUTING`` only controls whether a *reviewed*
        # paid plan may participate.  It must never turn an unreviewed
        # descriptor (the default for optional adapters) into a usable route.
        # Keep this guard in the resolver rather than relying only on the
        # ``is_free`` query predicate so a broad paid-routing switch cannot
        # bypass the operator entitlement review boundary.
        configured_plan = str(entitlement.configured_plan or "").strip().lower()
        if not configured_plan or configured_plan == "unreviewed":
            continue
        if (
            provider_configuration_required(data_source.name)
            and not provider_is_configured(data_source.name)
        ) or (
            entitlement.authentication_required and not provider_is_configured(data_source.name)
        ):
            continue
        if (
            data_source.name == "yfinance"
            and capability
            not in {ProviderCapability.OPTION_CHAIN, ProviderCapability.OPTION_QUOTE_HISTORY}
            and not settings.ENABLE_LEGACY_YFINANCE_FALLBACK
        ):
            # Keep the legacy adapter registered for explicit compatibility and
            # options, but never let it become an implicit fallback for the new
            # workstation's identity, history, event, or universe paths.
            continue
        # Policies may outlive a provider capability after a configuration or
        # adapter change. Never let a stale row invoke a method the provider
        # does not implement (for example Alpaca has discovery, not search).
        try:
            provider = get_provider(data_source.name)
        except KeyError:
            continue
        if capability.value not in list_provider_capabilities(data_source.name):
            continue
        allowed_environments = {
            str(value).strip().lower() for value in entitlement.enabled_environments
        }
        if allowed_environments and current_environment not in allowed_environments:
            continue
        if entitlement.review_due_at and _as_utc(entitlement.review_due_at) <= now:
            continue
        if not policy_has_known_quota(policy):
            # An adapter may be perfectly valid code while its current plan,
            # key/IP scope, or window is unknown.  That is an observable
            # configuration state, never a reason to guess a safe default.
            continue
        if operation is not None and not provider_contract_operation_cost_known(
            policy, data_source, operation
        ):
            # Weighted/credit providers are not candidates until this exact
            # operation has a documented charge in the local usage profile.
            continue
        if health.circuit_open_until and health.circuit_open_until > now:
            continue
        support_state = support_map.get(data_source.id)
        effective_support = (
            support_state.status if support_state is not None else SUPPORT_STATUS_UNKNOWN
        )
        if effective_support == SUPPORT_STATUS_UNSUPPORTED:
            continue
        policy.effective_score = _effective_score(policy, health)
        health.observed_score = policy.effective_score
        resolved.append(
            ResolvedProvider(
                provider_name=data_source.name,
                provider=provider,
                data_source=data_source,
                policy=policy,
                health=health,
                support_status=effective_support,
                has_symbol_binding=data_source.id in binding_ids,
                entitlement=entitlement,
            )
        )
    resolved.sort(
        key=lambda item: (
            0 if item.policy.is_pinned else 1,
            0 if item.support_status == SUPPORT_STATUS_SUPPORTED else 1,
            0 if item.has_symbol_binding else 1,
            -float(item.policy.effective_score),
            item.policy.base_priority,
            item.provider_name,
        )
    )
    return resolved


async def _record_result(
    db: AsyncSession,
    *,
    resolved: ResolvedProvider,
    log_row: ProviderRequestLog,
    success: bool,
    latency_ms: int,
    response_items: int | None = None,
    error: Exception | None = None,
) -> None:
    health = resolved.health
    policy = resolved.policy
    now = datetime.now(UTC)

    log_row.completed_at = now
    log_row.latency_ms = latency_ms
    log_row.success = success
    log_row.response_items = response_items
    if error is not None:
        log_row.error_type = error.__class__.__name__
        log_row.error_message = str(error)

    health.ewma_latency_ms = _ewma(health.ewma_latency_ms, Decimal(str(latency_ms)))
    health.ewma_success_rate = _ewma(
        health.ewma_success_rate, Decimal("1") if success else Decimal("0")
    )
    health.ewma_completeness = _ewma(
        health.ewma_completeness,
        Decimal("1") if (response_items or 0) > 0 else Decimal("0.35" if success else "0"),
    )
    health.ewma_freshness = _ewma(health.ewma_freshness, Decimal("1") if success else Decimal("0"))
    health.ewma_consistency = _ewma(
        health.ewma_consistency, Decimal("1") if success else Decimal("0.25")
    )

    if success:
        health.failure_streak = 0
        health.last_success_at = now
        health.circuit_open_until = None
        policy.learned_weight = _ewma(policy.learned_weight, Decimal("2"))
    else:
        health.failure_streak += 1
        health.last_failure_at = now
        health.last_error_type = error.__class__.__name__ if error else "ProviderError"
        health.last_error_message = str(error) if error else "Provider call failed"
        policy.learned_weight = _ewma(policy.learned_weight, Decimal("-4"))
        if health.failure_streak >= 3 and policy.cooldown_seconds:
            health.circuit_open_until = now + timedelta(seconds=policy.cooldown_seconds)

    policy.effective_score = _effective_score(policy, health)
    health.observed_score = policy.effective_score
    await db.flush()


async def execute_provider_call(
    db: AsyncSession,
    capability: ProviderCapability,
    operation: str,
    *,
    instrument_id: int | None = None,
    provider_symbol: str | None = None,
    provider_name: str | None = None,
    invoke: Callable[[Any, str | None], T],
    response_items: Callable[[T], int | None] | None = None,
    treat_empty_as_failure: bool = False,
) -> ProviderExecutionResult:
    chain = await resolve_provider_chain(
        db,
        capability,
        instrument_id=instrument_id,
        operation=operation,
    )
    if provider_name is not None:
        chain = [resolved for resolved in chain if resolved.provider_name == provider_name]
    loop = asyncio.get_event_loop()
    last_error: Exception | None = None

    for resolved in chain:
        if not provider_contract_operation_cost_known(
            resolved.policy, resolved.data_source, operation
        ):
            continue
        usage_mode, usage_unit_label, usage_units = _usage_cost_for_operation(
            resolved.data_source,
            operation,
        )
        # A runtime call participates in the same durable multi-dimensional
        # budget used by queued workloads.  This prevents concurrent workers
        # from multiplying a provider/IP/key allowance in process-local
        # buckets.  The import is intentionally lazy because provider_routing
        # imports the resolver for its candidate selection.
        from app.services.provider_routing import (
            reserve_provider_contract,
            settle_provider_contract,
        )

        reservations = await reserve_provider_contract(
            db,
            resolved=resolved,
            capability=capability.value,
            units=max(1, int(usage_units.to_integral_value())),
            now=datetime.now(UTC),
        )
        if reservations is None:
            continue
        if resolved.policy.tokens_per_minute is not None and resolved.policy.burst_capacity is not None:
            if not _get_bucket(resolved.policy, resolved.provider_name).try_acquire():
                settle_provider_contract(reservations, units=max(1, int(usage_units.to_integral_value())), success=False)
                continue
        log_row = ProviderRequestLog(
            data_source_id=resolved.data_source.id,
            capability=capability,
            operation=operation,
            operation_family=_operation_family(operation),
            instrument_id=instrument_id,
            provider_symbol=provider_symbol,
            requested_at=datetime.now(UTC),
            usage_mode=usage_mode,
            usage_unit_label=usage_unit_label,
            usage_units=usage_units,
        )
        db.add(log_row)
        await db.flush()

        semaphore = _get_semaphore(resolved.policy, resolved.provider_name)
        started = time.perf_counter()
        try:
            async with semaphore:
                result = await loop.run_in_executor(
                    None, lambda: invoke(resolved.provider, provider_symbol)
                )
            count = response_items(result) if response_items is not None else None
            is_empty = result is None or count == 0
            if treat_empty_as_failure and is_empty:
                raise ProviderNoDataError(
                    f"{resolved.provider_name} returned no usable data for {operation}"
                )
            latency_ms = int((time.perf_counter() - started) * 1000)
            await _record_result(
                db,
                resolved=resolved,
                log_row=log_row,
                success=True,
                latency_ms=latency_ms,
                response_items=count,
            )
            settle_provider_contract(
                reservations,
                units=max(1, int(usage_units.to_integral_value())),
                success=True,
            )
            if instrument_id is not None:
                await record_provider_support(
                    db,
                    instrument_id=instrument_id,
                    data_source_id=resolved.data_source.id,
                    capability=capability,
                    status=SUPPORT_STATUS_SUPPORTED,
                    provider_symbol=provider_symbol,
                )
            return ProviderExecutionResult(
                provider_name=resolved.provider_name,
                data_source=resolved.data_source,
                policy=resolved.policy,
                health=resolved.health,
                result=result,
            )
        except Exception as exc:
            rate_error = provider_rate_limit_error(
                resolved.provider_name,
                exc,
                scope=resolved.policy.quota_scope,
            )
            if rate_error is not None:
                exc = rate_error
                last_error = rate_error
                # A provider-supplied reset is authoritative.  Do not sleep
                # blindly or retry the same provider in a tight loop.
                if rate_error.retry_at is not None:
                    resolved.health.circuit_open_until = rate_error.retry_at
                else:
                    resolved.health.circuit_open_until = datetime.now(UTC) + timedelta(
                        seconds=resolved.policy.cooldown_seconds or 0
                    ) if resolved.policy.cooldown_seconds else None
            last_error = exc
            settle_provider_contract(
                reservations,
                units=max(1, int(usage_units.to_integral_value())),
                success=False,
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            await _record_result(
                db,
                resolved=resolved,
                log_row=log_row,
                success=False,
                latency_ms=latency_ms,
                response_items=0,
                error=exc,
            )
            should_mark_unsupported = (
                instrument_id is not None
                and isinstance(exc, ProviderNoDataError)
                and (
                    capability != ProviderCapability.PRICE_HISTORY
                    or operation.startswith("fetch_latest_ohlcv:")
                    or operation.startswith("bulk_fetch:")
                )
            )
            if should_mark_unsupported:
                await record_provider_support(
                    db,
                    instrument_id=instrument_id,
                    data_source_id=resolved.data_source.id,
                    capability=capability,
                    status=SUPPORT_STATUS_UNSUPPORTED,
                    provider_symbol=provider_symbol,
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                )
            remaining = [
                r.provider_name for r in chain if r.provider_name != resolved.provider_name
            ]
            if remaining:
                logger.warning(
                    "provider_runtime: %s failed for %s/%s (%s) — falling back to [%s]",
                    resolved.provider_name,
                    capability.value,
                    operation,
                    exc,
                    ", ".join(remaining),
                )
            else:
                logger.warning(
                    "provider_runtime: %s failed for %s/%s (%s) — no further providers in chain",
                    resolved.provider_name,
                    capability.value,
                    operation,
                    exc,
                )
            if not isinstance(exc, ProviderRateLimitError | ProviderNotConfiguredError):
                await asyncio.sleep(
                    min(1.0, 0.2 * (resolved.health.failure_streak + 1)) + random.random() * 0.15
                )
            continue

    if not chain and instrument_id is not None:
        raise ProviderNoDataError(
            f"No currently-supported providers available for {capability.value}/{operation}"
        )
    if last_error is not None:
        # Exhaustion is an expected, user-visible coverage outcome when every
        # entitled provider has no usable observations. Keep it distinguishable
        # from an unhandled runtime fault while preserving the original typed
        # exception for the caller's structured unavailable/partial response.
        log_method = logger.warning if isinstance(last_error, ProviderNoDataError) else logger.error
        log_method(
            "provider_runtime: all providers exhausted for %s/%s — last error: %s",
            capability.value,
            operation,
            last_error,
        )
        raise last_error
    raise RuntimeError(f"No enabled providers available for capability '{capability.value}'")


async def list_provider_status(db: AsyncSession) -> list[dict[str, Any]]:
    await seed_provider_runtime(db)
    rows = (
        await db.execute(
            select(ProviderPolicy, ProviderHealthState, DataSource, ProviderEntitlement)
            .join(DataSource, DataSource.id == ProviderPolicy.data_source_id)
            .join(
                ProviderEntitlement,
                (ProviderEntitlement.data_source_id == ProviderPolicy.data_source_id)
                & (ProviderEntitlement.capability == ProviderPolicy.capability),
            )
            .join(
                ProviderHealthState,
                (ProviderHealthState.data_source_id == ProviderPolicy.data_source_id)
                & (ProviderHealthState.capability == ProviderPolicy.capability),
            )
            .order_by(DataSource.name, ProviderPolicy.capability)
        )
    ).all()
    return [
        {
            "provider": data_source.name,
            "capability": policy.capability.value,
            "supported_capabilities": data_source.supported_capabilities or [],
            "is_enabled": policy.is_enabled,
            "is_pinned": policy.is_pinned,
            "auto_weight_enabled": policy.auto_weight_enabled,
            "base_priority": policy.base_priority,
            "effective_score": float(policy.effective_score),
            "learned_weight": float(policy.learned_weight),
            "max_concurrency": policy.max_concurrency,
            "tokens_per_minute": policy.tokens_per_minute,
            "burst_capacity": policy.burst_capacity,
            "cooldown_seconds": policy.cooldown_seconds,
            "quota_contract": policy.quota_contract,
            "quota_scope": policy.quota_scope,
            "quota_source": policy.quota_source,
            "quota_verified_at": policy.quota_verified_at,
            "quota_state": "known" if policy_has_known_quota(policy) else "unknown",
            "quota_missing_dimensions": quota_contract_missing_dimensions(policy),
            "operation_costs_configured": provider_contract_operation_costs_configured(
                policy, data_source
            ),
            "credentials_configured": provider_is_configured(data_source.name),
            "entitlement_state": (
                "reviewed"
                if str(entitlement.configured_plan or "").strip().lower() != "unreviewed"
                else "unreviewed"
            ),
            "routing_eligible": bool(
                policy.is_enabled
                and policy_has_known_quota(policy)
                and provider_is_configured(data_source.name)
                and str(entitlement.configured_plan or "").strip().lower() != "unreviewed"
                and (entitlement.is_free or settings.ALLOW_PAID_PROVIDER_ROUTING)
                and provider_contract_operation_costs_configured(policy, data_source)
            ),
            "freshness_seconds": policy.freshness_seconds,
            "failure_streak": health.failure_streak,
            "last_success_at": health.last_success_at,
            "last_failure_at": health.last_failure_at,
            "circuit_open_until": health.circuit_open_until,
            "ewma_latency_ms": float(health.ewma_latency_ms),
            "ewma_success_rate": float(health.ewma_success_rate),
            "ewma_completeness": float(health.ewma_completeness),
            "ewma_freshness": float(health.ewma_freshness),
            "ewma_consistency": float(health.ewma_consistency),
            "last_error_type": health.last_error_type,
            "last_error_message": health.last_error_message,
        }
        for policy, health, data_source, entitlement in rows
    ]
