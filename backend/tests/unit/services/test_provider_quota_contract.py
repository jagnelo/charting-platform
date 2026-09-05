from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select

from app.config import settings
from app.models.data_source import DataSource
from app.models.market_data_foundation import ProviderQuotaWindow
from app.models.provider_runtime import ProviderCapability, ProviderPolicy
from app.services.provider_routing import reserve_provider_quota
from app.services.provider_runtime import (
    ProviderRateLimitError,
    policy_has_known_quota,
    provider_contract_operation_cost_known,
    provider_contract_operation_costs_configured,
    provider_rate_limit_error,
    quota_contract_missing_dimensions,
    seed_provider_runtime,
)
from tests.unit.conftest import AsyncSessionAdapter


@pytest.mark.asyncio
async def test_seed_never_invents_generic_limits_for_unverified_provider(db):
    async_db = AsyncSessionAdapter(db)
    await seed_provider_runtime(async_db)
    source = db.execute(select(DataSource).where(DataSource.name == "finnhub")).scalar_one()
    policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == source.id,
            ProviderPolicy.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    assert policy.quota_contract is None
    assert policy.tokens_per_minute is None
    assert policy.burst_capacity is None
    assert policy.max_concurrency is None
    assert not policy_has_known_quota(policy)


@pytest.mark.asyncio
async def test_quota_windows_are_isolated_by_dimension(db):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="multi-window", is_active=True)
    db.add(source)
    db.flush()
    now = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
    minute = await reserve_provider_quota(
        async_db,
        data_source_id=source.id,
        capability="price_history",
        dimension="per_minute",
        units=1,
        limit_units=2,
        now=now,
    )
    month = await reserve_provider_quota(
        async_db,
        data_source_id=source.id,
        capability="price_history",
        dimension="per_month",
        units=1,
        limit_units=10,
        window_seconds=2_678_400,
        now=now,
    )
    assert minute is not None and month is not None
    rows = db.execute(select(ProviderQuotaWindow)).scalars().all()
    assert {row.dimension for row in rows} == {"per_minute", "per_month"}


def test_rate_limit_error_honors_retry_after_and_status():
    response = httpx.Response(
        429,
        headers={"Retry-After": "7", "X-RateLimit-Limit": "5"},
        request=httpx.Request("GET", "https://provider.example/data"),
    )
    exc = httpx.HTTPStatusError("429 Too Many Requests", request=response.request, response=response)
    typed = provider_rate_limit_error("example", exc, scope="api_key")
    assert isinstance(typed, ProviderRateLimitError)
    assert typed.status_code == 429
    assert typed.scope == "api_key"
    assert typed.retry_at is not None
    assert 6 <= (typed.retry_at - datetime.now(UTC)).total_seconds() <= 8


def test_ip_ban_status_is_typed_as_provider_capacity_failure():
    response = httpx.Response(
        418,
        headers={"Retry-After": "120"},
        request=httpx.Request("GET", "https://provider.example/data"),
    )
    exc = httpx.HTTPStatusError("418 IP banned", request=response.request, response=response)
    typed = provider_rate_limit_error("example", exc, scope="ip")
    assert isinstance(typed, ProviderRateLimitError)
    assert typed.status_code == 418
    assert typed.scope == "ip"


def test_existing_typed_capacity_error_is_preserved_for_durable_event_recording():
    typed = ProviderRateLimitError(
        "example",
        "provider quota exceeded",
        status_code=429,
        headers={"Authorization": "must-not-be-persisted", "Retry-After": "5"},
    )
    preserved = provider_rate_limit_error("example", typed, scope="api_key")
    assert preserved is typed
    assert preserved.scope == "api_key"


def test_non_capacity_http_error_is_not_misclassified():
    response = httpx.Response(500, request=httpx.Request("GET", "https://provider.example/data"))
    exc = httpx.HTTPStatusError("500 Server Error", request=response.request, response=response)
    assert provider_rate_limit_error("example", exc) is None


def test_dynamic_endpoint_contract_is_non_routable_without_operation_costs():
    source = DataSource(name="binance", config={"usage_tracking": {"operation_costs": {}}})
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.CRYPTO_HISTORY,
        quota_contract={
            "dimensions": [{"name": "weight", "limit": 1200, "window_seconds": 60, "unit": "weight", "scope": "ip", "source": "unit-test"}],
            "reset": "fixed_minute",
            "dynamic_endpoint_weights": True,
        },
    )
    assert not provider_contract_operation_cost_known(policy, source)
    assert not provider_contract_operation_cost_known(policy, source, "fetch_ohlcv")


def test_binance_seed_tracks_current_spot_ceiling_but_stays_dynamic_cost_gated():
    seed = settings.PROVIDER_RATE_LIMIT_SEEDS["binance"]
    contract = seed["quota_contract"]
    assert contract["dimensions"][0]["limit"] == 6000
    assert contract["dimensions"][0]["unit"] == "weight"
    assert contract["dynamic_endpoint_weights"] is True


def test_binance_only_admits_operations_with_exact_documented_weights():
    source = DataSource(name="binance")
    source.config = {"usage_tracking": settings.PROVIDER_USAGE_PROFILE_SEEDS["binance"]}
    seed = settings.PROVIDER_RATE_LIMIT_SEEDS["binance"]
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.LATEST_PRICE,
        quota_contract=seed["quota_contract"],
    )
    assert provider_contract_operation_cost_known(policy, source, "get_current_price")
    assert not provider_contract_operation_cost_known(policy, source, "fetch_ohlcv:1d")


def test_marketstack_and_ibkr_use_provider_specific_pacing_contracts():
    marketstack = settings.PROVIDER_RATE_LIMIT_SEEDS["marketstack"]["quota_contract"]
    assert marketstack["dimensions"][0]["limit"] == 100
    assert marketstack["dimensions"][0]["window_seconds"] == 2678400

    ibkr = settings.PROVIDER_RATE_LIMIT_SEEDS["ibkr"]["quota_contract"]
    assert {dimension["limit"] for dimension in ibkr["dimensions"]} == {5, 10}
    assert all(dimension["source"].startswith("https://ibkrcampus.com/") for dimension in ibkr["dimensions"])


def test_marketdata_app_records_documented_daily_credit_and_concurrency_limits():
    seed = settings.PROVIDER_RATE_LIMIT_SEEDS["marketdata_app"]
    contract = seed["quota_contract"]
    assert contract["dimensions"][0]["limit"] == 100
    assert contract["reset"] == "09:30 America/New_York"
    assert contract["concurrent_requests"] == 50
    assert seed.get("max_concurrency") is None


def test_credit_contract_requires_the_requested_operation_cost():
    source = DataSource(
        name="marketdata_app",
        config={"usage_tracking": {"operation_costs": {"fetch_ohlcv": 1}}},
    )
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_contract={
            "dimensions": [{"name": "credits", "limit": 100, "window_seconds": 86400, "unit": "credits", "scope": "api_key", "source": "unit-test"}],
            "reset": "provider_defined",
            "operation_costs_required": True,
        },
    )
    assert not provider_contract_operation_cost_known(policy, source)
    assert provider_contract_operation_cost_known(policy, source, "fetch_ohlcv")
    assert not provider_contract_operation_cost_known(policy, source, "get_current_price")


def test_partial_contract_is_non_routable_instead_of_dropping_a_dimension():
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_contract={
            "dimensions": [
                {
                    "name": "known",
                    "limit": 10,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "api_key",
                    "source": "unit-test",
                },
                {"name": "missing-source", "limit": 10, "window_seconds": 86400},
            ],
            "reset": "provider_defined",
        },
    )
    assert not policy_has_known_quota(policy)
    assert "quota_contract.dimensions[1].source" in quota_contract_missing_dimensions(policy)


def test_missing_quota_contract_is_operator_actionable():
    policy = ProviderPolicy(data_source_id=1, capability=ProviderCapability.PRICE_HISTORY)
    assert quota_contract_missing_dimensions(policy) == [
        "quota_contract",
        "quota_scope",
        "quota_source",
    ]


def test_dynamic_operation_cost_readiness_is_exposed_separately():
    source = DataSource(name="binance", config={"usage_tracking": {"operation_costs": {}}})
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.CRYPTO_HISTORY,
        quota_contract={
            "dimensions": [{"name": "weight", "limit": 10, "window_seconds": 60, "unit": "weight", "scope": "ip", "source": "unit-test"}],
            "reset": "fixed_minute",
            "dynamic_endpoint_weights": True,
        },
    )
    assert not provider_contract_operation_costs_configured(policy, source)
