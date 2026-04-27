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

logger = logging.getLogger(__name__)

T = TypeVar("T")

_ALPHA = Decimal("0.2")
_token_buckets: dict[tuple[str, str], tuple[tuple[int, int], TokenBucket]] = {}
_semaphores: dict[tuple[str, str], tuple[int, asyncio.Semaphore]] = {}


@dataclass(slots=True)
class ResolvedProvider:
    provider_name: str
    provider: Any
    data_source: DataSource
    policy: ProviderPolicy
    health: ProviderHealthState


@dataclass(slots=True)
class ProviderExecutionResult:
    provider_name: str
    data_source: DataSource
    policy: ProviderPolicy
    health: ProviderHealthState
    result: Any


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
        ProviderCapability.OPTION_QUOTE_HISTORY: list(settings.OPTION_QUOTE_HISTORY_PROVIDER_PRIORITY)
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


def _effective_score(policy: ProviderPolicy, health: ProviderHealthState) -> Decimal:
    base_score = Decimal(max(0, 100 - policy.base_priority))
    if not policy.auto_weight_enabled:
        return max(policy.score_floor, min(policy.score_ceiling, base_score))

    success_rate = health.ewma_success_rate or Decimal("0")
    completeness = health.ewma_completeness or Decimal("0")
    freshness = health.ewma_freshness or Decimal("0")
    consistency = health.ewma_consistency or Decimal("0")
    learned_weight = policy.learned_weight or Decimal("0")
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
    return max(policy.score_floor, min(policy.score_ceiling, candidate))


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

    capability_providers: dict[ProviderCapability, list[str]] = {capability: [] for capability in ProviderCapability}
    for provider_name in supported_provider_names():
        provider_capabilities = set(list_provider_capabilities(provider_name))
        for capability in ProviderCapability:
            if capability.value in provider_capabilities:
                capability_providers[capability].append(provider_name)

    for capability, supported_providers in capability_providers.items():
        preferred_order = ordered.get(capability, [])
        providers = preferred_order + [
            provider_name for provider_name in supported_providers if provider_name not in preferred_order
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
                3600 if capability not in {ProviderCapability.PRICE_HISTORY, ProviderCapability.LATEST_PRICE} else 300,
            )
            if policy is None:
                policy = ProviderPolicy(
                    data_source_id=data_source.id,
                    capability=capability,
                    is_enabled=True,
                    base_priority=_base_priority(provider_name, providers),
                    max_concurrency=rate_seed.get("max_concurrency", settings.PROVIDER_MAX_CONCURRENCY),
                    tokens_per_minute=rate_seed.get("tokens_per_minute", 60),
                    burst_capacity=rate_seed.get("burst_capacity", 15),
                    freshness_seconds=freshness,
                )
                db.add(policy)
            else:
                if policy.base_priority == 100:
                    policy.base_priority = _base_priority(provider_name, providers)
                if not policy.freshness_seconds:
                    policy.freshness_seconds = freshness

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
            policy.effective_score = _effective_score(policy, health)
            health.observed_score = policy.effective_score

    await db.flush()


async def resolve_provider_chain(
    db: AsyncSession,
    capability: ProviderCapability,
) -> list[ResolvedProvider]:
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
            .where(ProviderPolicy.capability == capability, ProviderPolicy.is_enabled.is_(True))
        )
    ).all()
    now = datetime.now(UTC)
    resolved: list[ResolvedProvider] = []
    for policy, health, data_source in rows:
        if health.circuit_open_until and health.circuit_open_until > now:
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
            )
        )
    resolved.sort(
        key=lambda item: (
            0 if item.policy.is_pinned else 1,
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
    invoke: Callable[[Any, str | None], T],
    response_items: Callable[[T], int | None] | None = None,
    treat_empty_as_failure: bool = False,
) -> ProviderExecutionResult:
    chain = await resolve_provider_chain(db, capability)
    loop = asyncio.get_event_loop()
    last_error: Exception | None = None

    for resolved in chain:
        if not _get_bucket(resolved.policy, resolved.provider_name).try_acquire():
            continue

        log_row = ProviderRequestLog(
            data_source_id=resolved.data_source.id,
            capability=capability,
            operation=operation,
            instrument_id=instrument_id,
            provider_symbol=provider_symbol,
            requested_at=datetime.now(UTC),
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
                raise ValueError(f"{resolved.provider_name} returned no usable data for {operation}")
            latency_ms = int((time.perf_counter() - started) * 1000)
            await _record_result(
                db,
                resolved=resolved,
                log_row=log_row,
                success=True,
                latency_ms=latency_ms,
                response_items=count,
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
            remaining = [r.provider_name for r in chain if r.provider_name != resolved.provider_name]
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
            await asyncio.sleep(min(1.0, 0.2 * (resolved.health.failure_streak + 1)) + random.random() * 0.15)
            continue

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
