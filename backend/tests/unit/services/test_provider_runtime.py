from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.data_source import DataSource
from app.models.provider_runtime import ProviderCapability, ProviderHealthState, ProviderPolicy
from app.services.provider_runtime import _get_bucket, _get_semaphore, seed_provider_runtime
from tests.unit.conftest import AsyncSessionAdapter


@pytest.mark.asyncio
async def test_seed_provider_runtime_creates_policies_for_supported_non_seeded_providers(db):
    async_db = AsyncSessionAdapter(db)

    await seed_provider_runtime(async_db)

    data_source = db.execute(select(DataSource).where(DataSource.name == "alpaca")).scalar_one()
    policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == data_source.id,
            ProviderPolicy.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one_or_none()

    assert policy is not None
    assert policy.base_priority >= 10


@pytest.mark.asyncio
async def test_seed_provider_runtime_backfills_missing_policy_defaults(db):
    async_db = AsyncSessionAdapter(db)
    data_source = DataSource(name="yfinance")
    db.add(data_source)
    db.flush()

    db.add(
        ProviderPolicy(
            data_source_id=data_source.id,
            capability=ProviderCapability.INSTRUMENT_SEARCH,
            base_priority=None,
            max_concurrency=None,
            tokens_per_minute=None,
            burst_capacity=None,
            cooldown_seconds=None,
            freshness_seconds=None,
            score_floor=None,
            score_ceiling=None,
            learned_weight=None,
            effective_score=None,
        )
    )
    db.add(
        ProviderHealthState(
            data_source_id=data_source.id,
            capability=ProviderCapability.INSTRUMENT_SEARCH,
            ewma_latency_ms=None,
            ewma_success_rate=None,
            ewma_completeness=None,
            ewma_freshness=None,
            ewma_consistency=None,
            observed_score=None,
        )
    )
    db.commit()

    await seed_provider_runtime(async_db)

    policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == data_source.id,
            ProviderPolicy.capability == ProviderCapability.INSTRUMENT_SEARCH,
        )
    ).scalar_one()
    health = db.execute(
        select(ProviderHealthState).where(
            ProviderHealthState.data_source_id == data_source.id,
            ProviderHealthState.capability == ProviderCapability.INSTRUMENT_SEARCH,
        )
    ).scalar_one()

    assert policy.base_priority is not None
    assert policy.max_concurrency is not None
    assert policy.tokens_per_minute is not None
    assert policy.burst_capacity is not None
    assert policy.cooldown_seconds is not None
    assert policy.freshness_seconds is not None
    assert policy.score_floor == Decimal("0")
    assert policy.score_ceiling == Decimal("100")
    assert policy.learned_weight == Decimal("0")
    assert policy.effective_score is not None
    assert health.ewma_latency_ms == Decimal("0")
    assert health.ewma_success_rate == Decimal("1")
    assert health.ewma_completeness == Decimal("1")
    assert health.ewma_freshness == Decimal("1")
    assert health.ewma_consistency == Decimal("1")
    assert health.observed_score == policy.effective_score


@pytest.mark.asyncio
async def test_seed_provider_runtime_resyncs_unpinned_base_priority(db):
    async_db = AsyncSessionAdapter(db)
    data_source = DataSource(name="coingecko")
    db.add(data_source)
    db.flush()

    db.add(
        ProviderPolicy(
            data_source_id=data_source.id,
            capability=ProviderCapability.INSTRUMENT_SEARCH,
            base_priority=10,
            is_pinned=False,
        )
    )
    db.add(
        ProviderHealthState(
            data_source_id=data_source.id,
            capability=ProviderCapability.INSTRUMENT_SEARCH,
        )
    )
    db.commit()

    await seed_provider_runtime(async_db)

    policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == data_source.id,
            ProviderPolicy.capability == ProviderCapability.INSTRUMENT_SEARCH,
        )
    ).scalar_one()

    assert policy.base_priority == 20


def test_bucket_rebuilds_when_policy_limits_change():
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        tokens_per_minute=60,
        burst_capacity=15,
    )
    first = _get_bucket(policy, "alpaca")

    policy.tokens_per_minute = 120
    policy.burst_capacity = 30
    second = _get_bucket(policy, "alpaca")

    assert second is not first
    assert second.capacity == 30
    assert second.rate_per_second == pytest.approx(2.0)


def test_semaphore_rebuilds_when_policy_concurrency_changes():
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.OPTION_CHAIN,
        max_concurrency=2,
        base_priority=10,
        score_floor=Decimal("0"),
        score_ceiling=Decimal("100"),
        learned_weight=Decimal("0"),
        effective_score=Decimal("0"),
    )
    first = _get_semaphore(policy, "yfinance")

    policy.max_concurrency = 5
    second = _get_semaphore(policy, "yfinance")

    assert second is not first
    assert second._value == 5
