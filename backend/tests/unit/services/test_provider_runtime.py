from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.data_source import DataSource
from app.models.provider_runtime import ProviderCapability, ProviderPolicy
from app.services.provider_runtime import _get_bucket, _get_semaphore, seed_provider_runtime
from tests.unit.conftest import AsyncSessionAdapter


@pytest.mark.asyncio
async def test_seed_provider_runtime_creates_policies_for_supported_non_seeded_providers(db):
    async_db = AsyncSessionAdapter(db)

    await seed_provider_runtime(async_db)

    data_source = db.execute(
        select(DataSource).where(DataSource.name == "alpaca")
    ).scalar_one()
    policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == data_source.id,
            ProviderPolicy.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one_or_none()

    assert policy is not None
    assert policy.base_priority >= 10


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
