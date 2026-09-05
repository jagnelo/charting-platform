from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.config import settings
from app.models.data_source import DataSource
from app.models.provider_runtime import (
    ProviderCapability,
    ProviderEntitlement,
    ProviderEntitlementRevision,
    ProviderHealthState,
    ProviderPolicy,
)
from app.services.provider_runtime import (
    _get_bucket,
    _get_semaphore,
    resolve_provider_chain,
    seed_provider_runtime,
)
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
async def test_provider_chain_excludes_non_free_entitlements(db):
    async_db = AsyncSessionAdapter(db)
    await seed_provider_runtime(async_db)
    data_source = db.execute(select(DataSource).where(DataSource.name == "alpaca")).scalar_one()
    entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == data_source.id,
            ProviderEntitlement.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    entitlement.is_free = False
    db.commit()

    chain = await resolve_provider_chain(async_db, ProviderCapability.PRICE_HISTORY)

    assert all(item.provider_name != "alpaca" for item in chain)


@pytest.mark.asyncio
async def test_unreviewed_provider_entitlement_is_not_runtime_usable(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    seeds = {
        name: value
        for name, value in settings.PROVIDER_ENTITLEMENT_SEEDS.items()
        if name != "alpaca"
    }
    monkeypatch.setattr(settings, "PROVIDER_ENTITLEMENT_SEEDS", seeds)

    await seed_provider_runtime(async_db)
    data_source = db.execute(select(DataSource).where(DataSource.name == "alpaca")).scalar_one()
    entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == data_source.id,
            ProviderEntitlement.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    assert entitlement.configured_plan == "unreviewed"
    assert entitlement.is_free is False

    chain = await resolve_provider_chain(async_db, ProviderCapability.PRICE_HISTORY)
    assert all(item.provider_name != "alpaca" for item in chain)


@pytest.mark.asyncio
async def test_paid_routing_switch_does_not_bypass_unreviewed_entitlement(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    seeds = {
        name: value
        for name, value in settings.PROVIDER_ENTITLEMENT_SEEDS.items()
        if name != "alpaca"
    }
    monkeypatch.setattr(settings, "PROVIDER_ENTITLEMENT_SEEDS", seeds)
    monkeypatch.setattr(settings, "ALLOW_PAID_PROVIDER_ROUTING", True)

    await seed_provider_runtime(async_db)
    data_source = db.execute(select(DataSource).where(DataSource.name == "alpaca")).scalar_one()
    entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == data_source.id,
            ProviderEntitlement.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    assert entitlement.configured_plan == "unreviewed"
    assert entitlement.is_free is False

    chain = await resolve_provider_chain(async_db, ProviderCapability.PRICE_HISTORY)
    assert all(item.provider_name != "alpaca" for item in chain)


@pytest.mark.asyncio
async def test_runtime_seeding_is_idempotent_for_entitlement_revisions(db):
    async_db = AsyncSessionAdapter(db)
    await seed_provider_runtime(async_db)
    alpaca = db.execute(select(DataSource).where(DataSource.name == "alpaca")).scalar_one()
    first_count = (
        db.execute(
            select(ProviderEntitlementRevision).where(
                ProviderEntitlementRevision.data_source_id == alpaca.id,
                ProviderEntitlementRevision.capability == ProviderCapability.PRICE_HISTORY,
            )
        )
        .scalars()
        .all()
    )
    await seed_provider_runtime(async_db)
    second_count = (
        db.execute(
            select(ProviderEntitlementRevision).where(
                ProviderEntitlementRevision.data_source_id == alpaca.id,
                ProviderEntitlementRevision.capability == ProviderCapability.PRICE_HISTORY,
            )
        )
        .scalars()
        .all()
    )
    assert len(first_count) == len(second_count) == 1


@pytest.mark.asyncio
async def test_reviewed_entitlement_upgrade_creates_next_revision(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    without_alpaca = {
        name: value
        for name, value in settings.PROVIDER_ENTITLEMENT_SEEDS.items()
        if name != "alpaca"
    }
    monkeypatch.setattr(settings, "PROVIDER_ENTITLEMENT_SEEDS", without_alpaca)
    await seed_provider_runtime(async_db)

    monkeypatch.setattr(
        settings,
        "PROVIDER_ENTITLEMENT_SEEDS",
        dict(
            settings.PROVIDER_ENTITLEMENT_SEEDS,
            alpaca={
                "configured_plan": "free-reviewed",
                "is_free": True,
                "authentication_required": True,
            },
        ),
    )
    await seed_provider_runtime(async_db)

    alpaca = db.execute(select(DataSource).where(DataSource.name == "alpaca")).scalar_one()
    entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == alpaca.id,
            ProviderEntitlement.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    revisions = (
        db.execute(
            select(ProviderEntitlementRevision)
            .where(
                ProviderEntitlementRevision.data_source_id == alpaca.id,
                ProviderEntitlementRevision.capability == ProviderCapability.PRICE_HISTORY,
            )
            .order_by(ProviderEntitlementRevision.revision)
        )
        .scalars()
        .all()
    )
    assert entitlement.revision == 2
    assert [row.revision for row in revisions] == [1, 2]
    assert revisions[0].is_free is False
    assert revisions[1].is_free is True


@pytest.mark.asyncio
async def test_new_workstation_chain_excludes_implicit_yfinance_fallback(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    await seed_provider_runtime(async_db)
    monkeypatch.setattr(settings, "ENABLE_LEGACY_YFINANCE_FALLBACK", False)

    chain = await resolve_provider_chain(async_db, ProviderCapability.PRICE_HISTORY)

    assert all(item.provider_name != "yfinance" for item in chain)


@pytest.mark.asyncio
async def test_otc_directory_requires_explicit_source_before_resolution(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", "")
    monkeypatch.setattr(
        settings,
        "PROVIDER_RATE_LIMIT_SEEDS",
        {
            **settings.PROVIDER_RATE_LIMIT_SEEDS,
            "finra_otc_directory": {
                "quota_contract": {
                    "reset": "fixed_minute",
                    "dimensions": [
                        {
                            "name": "requests",
                            "limit": 10,
                            "window_seconds": 60,
                            "unit": "requests",
                            "scope": "operator_source",
                            "source": "unit-test",
                        }
                    ],
                }
            },
        },
    )
    monkeypatch.setattr(
        settings,
        "PROVIDER_ENTITLEMENT_SEEDS",
        {
            **settings.PROVIDER_ENTITLEMENT_SEEDS,
            "finra_otc_directory": {
                "configured_plan": "operator-reviewed-directory",
                "is_free": True,
                "authentication_required": False,
            },
        },
    )

    await seed_provider_runtime(async_db)
    chain = await resolve_provider_chain(async_db, ProviderCapability.UNIVERSE_DISCOVERY)

    assert all(item.provider_name != "finra_otc_directory" for item in chain)

    monkeypatch.setattr(
        settings,
        "FINRA_OTC_SYMBOL_DIRECTORY_URL",
        "https://example.test/otc-directory.txt",
    )
    await seed_provider_runtime(async_db)
    chain = await resolve_provider_chain(async_db, ProviderCapability.UNIVERSE_DISCOVERY)

    assert any(item.provider_name == "finra_otc_directory" for item in chain)


@pytest.mark.asyncio
async def test_explicit_legacy_yfinance_requires_a_verified_quota(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    await seed_provider_runtime(async_db)
    monkeypatch.setattr(settings, "ENABLE_LEGACY_YFINANCE_FALLBACK", True)

    chain = await resolve_provider_chain(async_db, ProviderCapability.PRICE_HISTORY)

    assert all(item.provider_name != "yfinance" for item in chain)


@pytest.mark.asyncio
async def test_provider_chain_excludes_environment_ineligible_entitlements(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    await seed_provider_runtime(async_db)
    data_source = db.execute(select(DataSource).where(DataSource.name == "alpaca")).scalar_one()
    entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == data_source.id,
            ProviderEntitlement.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    entitlement.enabled_environments = ["production"]
    db.commit()
    monkeypatch.setattr("app.services.provider_runtime.settings.APP_ENV", "development")

    chain = await resolve_provider_chain(async_db, ProviderCapability.PRICE_HISTORY)

    assert all(item.provider_name != "alpaca" for item in chain)


@pytest.mark.asyncio
async def test_provider_chain_excludes_expired_entitlements(db):
    async_db = AsyncSessionAdapter(db)
    await seed_provider_runtime(async_db)
    data_source = db.execute(select(DataSource).where(DataSource.name == "alpaca")).scalar_one()
    entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == data_source.id,
            ProviderEntitlement.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    entitlement.review_due_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    chain = await resolve_provider_chain(async_db, ProviderCapability.PRICE_HISTORY)

    assert all(item.provider_name != "alpaca" for item in chain)


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
    assert policy.max_concurrency is None
    assert policy.tokens_per_minute is None
    assert policy.burst_capacity is None
    assert policy.cooldown_seconds is None
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
async def test_seed_provider_runtime_resyncs_unpinned_base_priority(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(
        settings,
        "PROVIDER_CHAIN_SEEDS",
        {"instrument_search": ["edgar", "coingecko"]},
    )
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

    expected_priority = (
        settings.PROVIDER_CHAIN_SEEDS["instrument_search"].index("coingecko") + 1
    ) * 10
    assert policy.base_priority == expected_priority


@pytest.mark.asyncio
async def test_provider_chain_ignores_stale_policy_for_unsupported_capability(db):
    """Old runtime rows must not call methods removed from a provider adapter."""
    async_db = AsyncSessionAdapter(db)
    await seed_provider_runtime(async_db)
    alpaca = db.execute(select(DataSource).where(DataSource.name == "alpaca")).scalar_one()
    stale_policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == alpaca.id,
            ProviderPolicy.capability == ProviderCapability.INSTRUMENT_SEARCH,
        )
    ).scalar_one_or_none()
    if stale_policy is None:
        stale_policy = ProviderPolicy(
            data_source_id=alpaca.id,
            capability=ProviderCapability.INSTRUMENT_SEARCH,
            is_enabled=True,
        )
        db.add(stale_policy)
    stale_policy.base_priority = 1
    # Runtime seeding creates entitlement/health rows for every adapter
    # capability.  Mutate those rows into a stale legacy record instead of
    # inserting a duplicate under the composite uniqueness constraint.
    stale_entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == alpaca.id,
            ProviderEntitlement.capability == ProviderCapability.INSTRUMENT_SEARCH,
        )
    ).scalar_one_or_none()
    if stale_entitlement is None:
        stale_entitlement = ProviderEntitlement(
            data_source_id=alpaca.id,
            capability=ProviderCapability.INSTRUMENT_SEARCH,
            is_free=True,
        )
        db.add(stale_entitlement)
    stale_entitlement.configured_plan = "legacy"
    db.commit()

    chain = await resolve_provider_chain(async_db, ProviderCapability.INSTRUMENT_SEARCH)

    assert all(item.provider_name != "alpaca" for item in chain)
    stale_policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == alpaca.id,
            ProviderPolicy.capability == ProviderCapability.INSTRUMENT_SEARCH,
        )
    ).scalar_one()
    assert stale_policy.is_enabled is False


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
