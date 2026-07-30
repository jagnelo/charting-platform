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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.data_source import DataSource
from app.models.provider_runtime import (
    ProviderCapability,
    ProviderEntitlement,
    ProviderHealthState,
    ProviderPolicy,
    ProviderRequestLog,
)
from app.providers import (
    ensure_data_source,
    get_provider,
    list_provider_capabilities,
    supported_provider_names,
)
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


@dataclass(slots=True)
class ResolvedProvider:
    provider_name: str
    provider: Any
    data_source: DataSource
    policy: ProviderPolicy
    health: ProviderHealthState
    support_status: str = SUPPORT_STATUS_UNKNOWN
    has_symbol_binding: bool = False


@dataclass(slots=True)
class ProviderExecutionResult:
    provider_name: str
    data_source: DataSource
    policy: ProviderPolicy
    health: ProviderHealthState
    result: Any


class ProviderNoDataError(LookupError):
    """Raised when providers resolve successfully but none return usable data."""


def _operation_family(operation: str) -> str:
    return operation.split(":", 1)[0].strip() or operation


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
    rate_seed: dict[str, int],
) -> None:
    if not policy.is_pinned:
        policy.base_priority = _base_priority(provider_name, providers)
    policy.max_concurrency = _int_or(
        policy.max_concurrency,
        rate_seed.get("max_concurrency", settings.PROVIDER_MAX_CONCURRENCY),
    )
    policy.tokens_per_minute = _int_or(
        policy.tokens_per_minute, rate_seed.get("tokens_per_minute", 60)
    )
    policy.burst_capacity = _int_or(policy.burst_capacity, rate_seed.get("burst_capacity", 15))
    policy.cooldown_seconds = _int_or(policy.cooldown_seconds, 30)
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
    key = _bucket_key(provider_name, policy.capability)
    cached = _semaphores.get(key)
    if cached is None or cached[0] != max(1, policy.max_concurrency):
        sem = asyncio.Semaphore(max(1, policy.max_concurrency))
        _semaphores[key] = (max(1, policy.max_concurrency), sem)
        return sem
    sem = cached[1]
    return sem


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

    for capability, supported_providers in capability_providers.items():
        preferred_order = ordered.get(capability, [])
        providers = preferred_order + [
            provider_name
            for provider_name in supported_providers
            if provider_name not in preferred_order
        ]
        for provider_name in providers:
            data_source = await ensure_data_source(db, provider_name)
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
                    max_concurrency=rate_seed.get(
                        "max_concurrency", settings.PROVIDER_MAX_CONCURRENCY
                    ),
                    tokens_per_minute=rate_seed.get("tokens_per_minute", 60),
                    burst_capacity=rate_seed.get("burst_capacity", 15),
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
            if entitlement is None:
                db.add(
                    ProviderEntitlement(
                        data_source_id=data_source.id,
                        capability=capability,
                        configured_plan="unreviewed",
                        is_free=True,
                        live_probe_status="not_run",
                    )
                )
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
) -> list[ResolvedProvider]:
    await seed_provider_runtime(db)
    rows = (
        await db.execute(
            select(ProviderPolicy, ProviderHealthState, DataSource)
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
                ProviderEntitlement.is_free.is_(True),
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
    for policy, health, data_source in rows:
        if health.circuit_open_until and health.circuit_open_until > now:
            continue
        support_state = support_map.get(data_source.id)
        effective_support = (
            support_state.status if support_state is not None else SUPPORT_STATUS_UNKNOWN
        )
        if effective_support == SUPPORT_STATUS_UNSUPPORTED:
            continue
        provider = get_provider(data_source.name)
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
        if health.failure_streak >= 3:
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
    chain = await resolve_provider_chain(db, capability, instrument_id=instrument_id)
    if provider_name is not None:
        chain = [resolved for resolved in chain if resolved.provider_name == provider_name]
    loop = asyncio.get_event_loop()
    last_error: Exception | None = None

    for resolved in chain:
        if not _get_bucket(resolved.policy, resolved.provider_name).try_acquire():
            continue

        usage_mode, usage_unit_label, usage_units = _usage_cost_for_operation(
            resolved.data_source,
            operation,
        )
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
            last_error = exc
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
            await asyncio.sleep(
                min(1.0, 0.2 * (resolved.health.failure_streak + 1)) + random.random() * 0.15
            )
            continue

    if not chain and instrument_id is not None:
        raise ProviderNoDataError(
            f"No currently-supported providers available for {capability.value}/{operation}"
        )
    if last_error is not None:
        logger.error(
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
            select(ProviderPolicy, ProviderHealthState, DataSource)
            .join(DataSource, DataSource.id == ProviderPolicy.data_source_id)
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
        for policy, health, data_source in rows
    ]
