from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.config import settings
from app.models.data_source import DataSource
from app.models.market_data_foundation import ProviderQuotaWindow
from app.models.provider_runtime import (
    ProviderCapability,
    ProviderEntitlement,
    ProviderEntitlementRevision,
    ProviderHealthState,
    ProviderPolicy,
    ProviderRequestLog,
)
from app.providers.registry import get_provider_usage_profile
from app.providers.telemetry import observe_response
from app.services.provider_runtime import (
    ResolvedProvider,
    TokenBucket,
    _capacity_response_headers,
    _get_bucket,
    _get_semaphore,
    execute_provider_call,
    resolve_provider_chain,
    seed_provider_runtime,
)
from tests.unit.conftest import AsyncSessionAdapter


def test_capacity_response_headers_retain_provider_native_usage_state_only():
    assert _capacity_response_headers(
        {
            "X-Bapi-Limit": "50",
            "X-Bapi-Limit-Status": "49",
            "X-Bapi-Limit-Reset-Timestamp": "1700000000000",
            "X-Api-Ratelimit-Limit": "100",
            "X-Api-Ratelimit-Remaining": "87",
            "X-Api-Ratelimit-Reset": "1700000000",
            "X-Api-Ratelimit-Consumed": "4",
            "Authorization": "secret",
        }
    ) == {
        "x-bapi-limit": "50",
        "x-bapi-limit-status": "49",
        "x-bapi-limit-reset-timestamp": "1700000000000",
        "x-api-ratelimit-limit": "100",
        "x-api-ratelimit-remaining": "87",
        "x-api-ratelimit-reset": "1700000000",
        "x-api-ratelimit-consumed": "4",
    }


@pytest.mark.asyncio
async def test_execute_provider_call_persists_transport_measurement(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(
        name="measured-provider",
        is_active=True,
        config={
            "usage_tracking": {
                "operation_costs": {"get_current_price": 1},
                "dimension_costs": {
                    "response_bytes": {"get_current_price": 100},
                    "credits_per_minute": {"get_current_price": 1},
                },
            }
        },
    )
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.LATEST_PRICE,
        is_enabled=True,
        max_concurrency=1,
        quota_scope="api_key",
        quota_source="unit-test contract",
        quota_contract={
            "reset": "rolling",
            "dimensions": [
                {
                    "name": "requests_per_minute",
                    "limit": 10,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "api_key",
                    "source": "unit-test contract",
                },
                {
                    "name": "response_bytes",
                    "limit": 10_000,
                    "window_seconds": 60,
                    "unit": "bytes",
                    "scope": "api_key",
                    "source": "unit-test contract",
                },
                {
                    "name": "credits_per_minute",
                    "limit": 8,
                    "window_seconds": 60,
                    "unit": "credits",
                    "scope": "api_key",
                    "source": "https://support.twelvedata.com/en/articles/5713553-control-over-usage",
                },
            ],
            "dimension_costs_required": True,
        },
        score_floor=Decimal("0"),
        score_ceiling=Decimal("100"),
        learned_weight=Decimal("0"),
        effective_score=Decimal("0"),
    )
    health = ProviderHealthState(
        data_source_id=source.id,
        capability=ProviderCapability.LATEST_PRICE,
        ewma_latency_ms=Decimal("0"),
        ewma_success_rate=Decimal("1"),
        ewma_completeness=Decimal("1"),
        ewma_freshness=Decimal("1"),
        ewma_consistency=Decimal("1"),
        observed_score=Decimal("0"),
    )
    resolved = ResolvedProvider(
        provider_name="measured-provider",
        provider=object(),
        data_source=source,
        policy=policy,
        health=health,
    )

    async def fake_chain(*_args, **_kwargs):
        return [resolved]

    monkeypatch.setattr("app.services.provider_runtime.resolve_provider_chain", fake_chain)

    def invoke(_provider, _symbol):
        response = type(
            "Response",
            (),
            {
                "content": b"measured-response",
                "headers": {
                    "x-ratelimit-remaining": "9",
                    "api-credits-used": "3",
                    "api-credits-left": "5",
                },
            },
        )()
        observe_response(response)
        return 123.45

    await execute_provider_call(
        async_db,
        ProviderCapability.LATEST_PRICE,
        "get_current_price",
        invoke=invoke,
    )
    row = db.execute(select(ProviderRequestLog)).scalar_one()
    assert row.http_requests == 1
    assert row.response_bytes == len(b"measured-response")
    assert row.response_headers == {
        "x-ratelimit-remaining": "9",
        "api-credits-used": "3",
        "api-credits-left": "5",
    }
    windows = {
        item.dimension: item
        for item in db.execute(select(ProviderQuotaWindow)).scalars().all()
    }
    assert windows["requests_per_minute"].consumed_units == 1
    assert windows["response_bytes"].consumed_units == len(b"measured-response")
    assert windows["credits_per_minute"].consumed_units == 3
    assert all(item.reserved_units == 0 for item in windows.values())


@pytest.mark.asyncio
async def test_execute_provider_call_settles_marketdata_app_native_credit_charge(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(
        name="marketdata_app",
        is_active=True,
        config={
            "usage_tracking": {
                "mode": "credit_count",
                "unit_label": "credits",
                "operation_costs": {"get_current_price": 12},
            }
        },
    )
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.LATEST_PRICE,
        is_enabled=True,
        max_concurrency=1,
        quota_scope="api_key",
        quota_source="MarketData.app rate-limiting documentation",
        quota_contract={
            "reset": "09:30 America/New_York",
            "dimensions": [
                {
                    "name": "credits_per_day",
                    "limit": 100,
                    "window_seconds": 86400,
                    "unit": "credits",
                    "scope": "api_key",
                    "source": "https://www.marketdata.app/docs/api/rate-limiting/",
                }
            ],
        },
    )
    db.add(policy)
    db.flush()
    health = ProviderHealthState(
        data_source_id=source.id,
        capability=ProviderCapability.LATEST_PRICE,
        ewma_latency_ms=Decimal("0"),
        ewma_success_rate=Decimal("1"),
        ewma_completeness=Decimal("1"),
        ewma_freshness=Decimal("1"),
        ewma_consistency=Decimal("1"),
        observed_score=Decimal("0"),
    )
    db.add(health)
    db.flush()
    resolved = ResolvedProvider(
        provider_name="marketdata_app",
        provider=object(),
        data_source=source,
        policy=policy,
        health=health,
    )

    async def fake_chain(*_args, **_kwargs):
        return [resolved]

    monkeypatch.setattr("app.services.provider_runtime.resolve_provider_chain", fake_chain)

    def invoke(_provider, _symbol):
        response = type(
            "Response",
            (),
            {
                "content": b"marketdata-response",
                "headers": {
                    "x-api-ratelimit-limit": "100",
                    "x-api-ratelimit-remaining": "87",
                    "x-api-ratelimit-reset": "1700000000",
                    "x-api-ratelimit-consumed": "4",
                },
            },
        )()
        observe_response(response)
        return 123.45

    await execute_provider_call(
        async_db,
        ProviderCapability.LATEST_PRICE,
        "get_current_price",
        invoke=invoke,
    )
    row = db.execute(select(ProviderRequestLog)).scalar_one()
    assert row.response_headers == {
        "x-api-ratelimit-limit": "100",
        "x-api-ratelimit-remaining": "87",
        "x-api-ratelimit-reset": "1700000000",
        "x-api-ratelimit-consumed": "4",
    }
    window = db.execute(select(ProviderQuotaWindow)).scalar_one()
    assert window.consumed_units == 13
    assert window.reserved_units == 0


@pytest.mark.asyncio
async def test_execute_provider_call_applies_dynamic_operation_override(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(
        name="binance",
        is_active=True,
        config={
            "usage_tracking": {
                "mode": "weighted_request",
                "unit_label": "request_weight",
                "operation_costs": {"get_current_price": 2},
            }
        },
    )
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
        is_enabled=True,
        max_concurrency=1,
        tokens_per_minute=6000,
        burst_capacity=6000,
        quota_scope="ip",
        quota_source="unit-test Binance contract",
        quota_contract={
            "reset": "fixed_minute",
            "dynamic_endpoint_weights": True,
            "dimensions": [
                {
                    "name": "request_weight_per_minute",
                    "limit": 6000,
                    "window_seconds": 60,
                    "unit": "weight",
                    "scope": "ip",
                    "source": "unit-test Binance contract",
                }
            ],
        },
        score_floor=Decimal("0"),
        score_ceiling=Decimal("100"),
        learned_weight=Decimal("0"),
        effective_score=Decimal("0"),
    )
    health = ProviderHealthState(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
        ewma_latency_ms=Decimal("0"),
        ewma_success_rate=Decimal("1"),
        ewma_completeness=Decimal("1"),
        ewma_freshness=Decimal("1"),
        ewma_consistency=Decimal("1"),
        observed_score=Decimal("0"),
    )
    resolved = ResolvedProvider(
        provider_name="binance",
        provider=object(),
        data_source=source,
        policy=policy,
        health=health,
    )

    async def fake_chain(*_args, **_kwargs):
        return [resolved]

    monkeypatch.setattr("app.services.provider_runtime.resolve_provider_chain", fake_chain)

    await execute_provider_call(
        async_db,
        ProviderCapability.PRICE_HISTORY,
        "fetch_ohlcv:1d",
        operation_cost_overrides={"binance": 4},
        invoke=lambda _provider, _symbol: [1],
        response_items=len,
    )

    request = db.execute(select(ProviderRequestLog)).scalar_one()
    assert request.usage_units == Decimal("4")
    windows = db.execute(select(ProviderQuotaWindow)).scalars().all()
    assert [item.dimension for item in windows] == ["request_weight_per_minute"]
    window = windows[0]
    assert window.reserved_units == 0
    assert window.consumed_units == 4


@pytest.mark.asyncio
async def test_finra_async_download_settles_measured_bytes_in_monthly_window(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(settings, "FINRA_ASYNC_MAX_RESULT_BYTES", 4 * 1024 * 1024)
    source = DataSource(
        name="finra",
        is_active=True,
        config={"usage_tracking": get_provider_usage_profile("finra")},
    )
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.SHORT_INTEREST,
        is_enabled=True,
        max_concurrency=1,
        quota_scope="ip",
        quota_source="unit-test FINRA contract",
        quota_contract=settings.PROVIDER_RATE_LIMIT_SEEDS["finra"]["quota_contract"],
        score_floor=Decimal("0"),
        score_ceiling=Decimal("100"),
        learned_weight=Decimal("0"),
        effective_score=Decimal("0"),
    )
    health = ProviderHealthState(
        data_source_id=source.id,
        capability=ProviderCapability.SHORT_INTEREST,
        ewma_latency_ms=Decimal("0"),
        ewma_success_rate=Decimal("1"),
        ewma_completeness=Decimal("1"),
        ewma_freshness=Decimal("1"),
        ewma_consistency=Decimal("1"),
        observed_score=Decimal("0"),
    )
    resolved = ResolvedProvider(
        provider_name="finra",
        provider=object(),
        data_source=source,
        policy=policy,
        health=health,
    )

    async def fake_chain(*_args, **_kwargs):
        return [resolved]

    monkeypatch.setattr("app.services.provider_runtime.resolve_provider_chain", fake_chain)

    def invoke(_provider, _symbol):
        response = type(
            "Response",
            (),
            {"content": b"async-result", "headers": {"content-length": "12"}},
        )()
        observe_response(response)
        return response.content

    await execute_provider_call(
        async_db,
        ProviderCapability.SHORT_INTEREST,
        "download_async_result",
        invoke=invoke,
        response_items=len,
    )

    windows = db.execute(select(ProviderQuotaWindow)).scalars().all()
    assert [item.dimension for item in windows] == ["download_bytes_per_calendar_month"]
    window = windows[0]
    assert window.dimension == "download_bytes_per_calendar_month"
    assert window.consumed_units == len(b"async-result")
    assert window.reserved_units == 0


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
async def test_provider_chain_requires_positive_live_probe_evidence(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(settings, "ALPACA_API_KEY", "configured-key")
    monkeypatch.setattr(settings, "ALPACA_SECRET_KEY", "configured-secret")
    # The repository seed records positive bounded live evidence now. Keep
    # this test focused on the resolver gate by explicitly starting from the
    # pre-evidence state.
    monkeypatch.setattr(
        settings,
        "PROVIDER_LIVE_PROBE_STATUS_SEEDS",
        {**settings.PROVIDER_LIVE_PROBE_STATUS_SEEDS, "alpaca": "not_run"},
    )
    await seed_provider_runtime(async_db)

    chain = await resolve_provider_chain(async_db, ProviderCapability.PRICE_HISTORY)
    assert all(item.provider_name != "alpaca" for item in chain)

    source = db.execute(select(DataSource).where(DataSource.name == "alpaca")).scalar_one()
    entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == source.id,
            ProviderEntitlement.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    entitlement.live_probe_status = "passed"
    db.commit()

    chain = await resolve_provider_chain(async_db, ProviderCapability.PRICE_HISTORY)
    assert any(item.provider_name == "alpaca" for item in chain)


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
async def test_marketdata_app_entitlement_and_quota_follow_explicit_reviewed_plan(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "starter")
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 10000)

    await seed_provider_runtime(async_db)

    source = db.execute(
        select(DataSource).where(DataSource.name == "marketdata_app")
    ).scalar_one()
    entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == source.id,
            ProviderEntitlement.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == source.id,
            ProviderPolicy.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()

    assert entitlement.configured_plan == "marketdata-starter-operator-reviewed"
    assert policy.quota_contract["dimensions"][0]["limit"] == 10000
    assert policy.quota_contract["dimensions"][0]["account_plan"] == "starter"


@pytest.mark.asyncio
async def test_marketstack_history_route_does_not_require_discovery_scope(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(settings, "MARKETSTACK_API_KEY", "configured-key")
    monkeypatch.setattr(settings, "MARKETSTACK_DISCOVERY_EXCHANGE", "")

    await seed_provider_runtime(async_db)

    history_chain = await resolve_provider_chain(
        async_db,
        ProviderCapability.PRICE_HISTORY,
        operation="fetch_ohlcv:D1",
        operation_cost_overrides={"marketstack": 1},
    )
    assert any(item.provider_name == "marketstack" for item in history_chain)

    discovery_chain = await resolve_provider_chain(
        async_db,
        ProviderCapability.UNIVERSE_DISCOVERY,
        operation="discover_universe_page",
    )
    assert all(item.provider_name != "marketstack" for item in discovery_chain)


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
                },
                "quota_scope": "operator_source",
                "quota_source": "unit-test FINRA OTC contract",
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
                "live_probe_status": "passed",
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

    # A source URL is necessary but not sufficient: response-dependent DAPI
    # pagination also requires the reviewed operation/terms controls.
    assert all(item.provider_name != "finra_otc_directory" for item in chain)

    monkeypatch.setattr(
        settings,
        "FINRA_OTC_OPERATION_COSTS",
        {"discover_universe_page": 3, "reconcile_universe_page": 3},
    )
    monkeypatch.setattr(settings, "FINRA_OTC_TERMS_REVIEWED", True)
    monkeypatch.setattr(settings, "FINRA_OTC_COMPLETENESS_REVIEWED", True)
    monkeypatch.setattr(settings, "FINRA_OTC_REDISTRIBUTION_REVIEWED", True)
    monkeypatch.setattr(settings, "FINRA_OTC_POLL_INTERVAL_SECONDS", 900)
    await seed_provider_runtime(async_db)
    chain = await resolve_provider_chain(async_db, ProviderCapability.UNIVERSE_DISCOVERY)

    assert any(item.provider_name == "finra_otc_directory" for item in chain)


@pytest.mark.asyncio
async def test_otc_directory_default_entitlement_remains_unreviewed(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(
        settings,
        "FINRA_OTC_SYMBOL_DIRECTORY_URL",
        "https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster",
    )
    await seed_provider_runtime(async_db)
    chain = await resolve_provider_chain(async_db, ProviderCapability.UNIVERSE_DISCOVERY)

    assert all(item.provider_name != "finra_otc_directory" for item in chain)
    entitlement = db.execute(
        select(ProviderEntitlement).join(DataSource).where(DataSource.name == "finra_otc_directory")
    ).scalar_one()
    assert entitlement.configured_plan == "unreviewed"
    assert entitlement.live_probe_status == "passed"


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


def test_local_admission_controls_share_explicit_quota_group_across_capabilities():
    contract = {
        "reset": "rolling",
        "dimensions": [
            {
                "name": "requests_per_minute",
                "limit": 120,
                "window_seconds": 60,
                "unit": "requests",
                "scope": "api_key",
                "quota_group": "account",
                "source": "unit-test contract",
            },
            {
                "name": "concurrent_requests",
                "limit": 2,
                "window_seconds": 1,
                "unit": "concurrent_requests",
                "scope": "api_key",
                "quota_group": "account",
                "source": "unit-test contract",
            },
        ],
    }
    first_policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        tokens_per_minute=120,
        burst_capacity=4,
        max_concurrency=2,
        quota_scope="api_key",
        quota_source="unit-test contract",
        quota_contract=contract,
    )
    second_policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.LATEST_PRICE,
        tokens_per_minute=120,
        burst_capacity=4,
        max_concurrency=2,
        quota_scope="api_key",
        quota_source="unit-test contract",
        quota_contract=contract,
    )

    assert _get_bucket(first_policy, "shared-provider") is _get_bucket(
        second_policy, "shared-provider"
    )
    assert _get_semaphore(first_policy, "shared-provider") is _get_semaphore(
        second_policy, "shared-provider"
    )


def test_local_admission_controls_keep_ungrouped_capabilities_isolated():
    contract = {
        "reset": "rolling",
        "dimensions": [
            {
                "name": "requests_per_minute",
                "limit": 120,
                "window_seconds": 60,
                "unit": "requests",
                "scope": "api_key",
                "source": "unit-test contract",
            }
        ],
    }
    first_policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        tokens_per_minute=120,
        burst_capacity=4,
        quota_scope="api_key",
        quota_source="unit-test contract",
        quota_contract=contract,
    )
    second_policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.LATEST_PRICE,
        tokens_per_minute=120,
        burst_capacity=4,
        quota_scope="api_key",
        quota_source="unit-test contract",
        quota_contract=contract,
    )

    assert _get_bucket(first_policy, "isolated-provider") is not _get_bucket(
        second_policy, "isolated-provider"
    )


def test_token_bucket_charges_weighted_units():
    bucket = TokenBucket(rate_per_minute=60, burst_capacity=4)

    assert bucket.try_acquire(2)
    assert bucket.try_acquire(2)
    assert not bucket.try_acquire(2)


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
