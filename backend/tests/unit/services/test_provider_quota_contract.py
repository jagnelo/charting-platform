from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.config import settings
from app.models.data_source import DataSource
from app.models.market_data_foundation import ProviderQuotaWindow
from app.models.provider_runtime import ProviderCapability, ProviderPolicy
from app.services.provider_routing import (
    reserve_provider_contract,
    reserve_provider_quota,
    settle_provider_contract,
)
from app.services.provider_runtime import (
    ProviderRateLimitError,
    ResolvedProvider,
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
    source = db.execute(select(DataSource).where(DataSource.name == "fred")).scalar_one()
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


def test_known_request_limit_with_untracked_bandwidth_remains_non_routable():
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_contract={
            "dimensions": [
                {
                    "name": "requests_per_day",
                    "limit": 250,
                    "window_seconds": 86400,
                    "unit": "requests",
                    "scope": "api_key",
                    "source": "operator-dashboard",
                }
            ],
            "reset": "provider_defined_daily",
            "untracked_constraints": [
                {
                    "name": "bandwidth_per_30_days",
                    "limit": 512,
                    "unit": "megabytes",
                    "source": "operator-dashboard",
                }
            ],
        },
    )
    assert not policy_has_known_quota(policy)
    assert (
        "quota_contract.untracked_constraints.bandwidth_per_30_days"
        in quota_contract_missing_dimensions(policy)
    )


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


@pytest.mark.asyncio
async def test_rolling_quota_reservation_accumulates_across_second_buckets(db):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="rolling-provider", is_active=True)
    db.add(source)
    db.flush()
    now = datetime(2026, 9, 5, 12, 0, 10, tzinfo=UTC)
    first = await reserve_provider_quota(
        async_db,
        data_source_id=source.id,
        capability="latest_price",
        dimension="per_minute",
        units=2,
        limit_units=3,
        window_seconds=60,
        now=now,
        rolling=True,
    )
    second = await reserve_provider_quota(
        async_db,
        data_source_id=source.id,
        capability="latest_price",
        dimension="per_minute",
        units=1,
        limit_units=3,
        window_seconds=60,
        now=now + timedelta(seconds=1),
        rolling=True,
    )
    rejected = await reserve_provider_quota(
        async_db,
        data_source_id=source.id,
        capability="latest_price",
        dimension="per_minute",
        units=1,
        limit_units=3,
        window_seconds=60,
        now=now + timedelta(seconds=2),
        rolling=True,
    )
    after_expiry = await reserve_provider_quota(
        async_db,
        data_source_id=source.id,
        capability="latest_price",
        dimension="per_minute",
        units=1,
        limit_units=3,
        window_seconds=60,
        now=now + timedelta(seconds=61),
        rolling=True,
    )
    assert first is not None and second is not None
    assert rejected is None
    assert after_expiry is not None


def test_rate_limit_error_honors_retry_after_and_status():
    response = httpx.Response(
        429,
        headers={"Retry-After": "7", "X-RateLimit-Limit": "5"},
        request=httpx.Request("GET", "https://provider.example/data"),
    )
    exc = httpx.HTTPStatusError(
        "429 Too Many Requests", request=response.request, response=response
    )
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
            "dimensions": [
                {
                    "name": "weight",
                    "limit": 1200,
                    "window_seconds": 60,
                    "unit": "weight",
                    "scope": "ip",
                    "source": "unit-test",
                }
            ],
            "reset": "fixed_minute",
            "dynamic_endpoint_weights": True,
        },
    )
    assert not provider_contract_operation_cost_known(policy, source)
    assert not provider_contract_operation_cost_known(policy, source, "fetch_ohlcv")


def test_byte_dimension_requires_explicit_operation_bound():
    source = DataSource(
        name="byte-provider",
        config={
            "usage_tracking": {
                "operation_costs": {"fetch_short_interest": 1},
                "dimension_costs": {
                    "download_bytes_per_month": {"fetch_short_interest": 3_000_000}
                },
            }
        },
    )
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.SHORT_INTEREST,
        quota_contract={
            "dimensions": [
                {
                    "name": "requests_per_minute",
                    "limit": 1200,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "ip",
                    "source": "unit-test",
                },
                {
                    "name": "download_bytes_per_month",
                    "limit": 10_000_000,
                    "window_seconds": 2_678_400,
                    "unit": "bytes",
                    "scope": "api_key",
                    "source": "unit-test",
                },
                {
                    "name": "async_requests_per_minute",
                    "limit": 20,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "dataset",
                    "source": "unit-test",
                },
            ],
            "reset": "calendar_month",
            "dimension_costs_required": True,
        },
    )
    assert provider_contract_operation_cost_known(policy, source, "fetch_short_interest")
    source.config["usage_tracking"].pop("dimension_costs")
    assert not provider_contract_operation_cost_known(policy, source, "fetch_short_interest")


@pytest.mark.asyncio
async def test_dimension_reservation_settles_observed_bytes_without_charging_request_units(db):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="byte-provider", is_active=True)
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.SHORT_INTEREST,
        quota_scope="api_key",
        quota_contract={
            "dimensions": [
                {
                    "name": "requests_per_minute",
                    "limit": 10,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "api_key",
                    "source": "unit-test",
                },
                {
                    "name": "download_bytes_per_month",
                    "limit": 10_000,
                    "window_seconds": 2_678_400,
                    "unit": "bytes",
                    "scope": "api_key",
                    "source": "unit-test",
                },
                {
                    "name": "async_requests_per_minute",
                    "limit": 20,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "dataset",
                    "source": "unit-test",
                },
            ],
            "reset": "calendar_month",
        },
    )
    resolved = ResolvedProvider(
        provider_name="byte-provider",
        provider=object(),
        data_source=source,
        policy=policy,
        health=None,  # type: ignore[arg-type]
    )
    windows = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.SHORT_INTEREST.value,
        units=1,
        dimension_units={
            "requests_per_minute": 1,
            "download_bytes_per_month": 3_000,
            "async_requests_per_minute": 0,
        },
        now=datetime(2026, 9, 5, 12, 0, tzinfo=UTC),
    )
    assert windows is not None
    settle_provider_contract(
        windows,
        units=1,
        reserved_dimension_units={
            "requests_per_minute": 1,
            "download_bytes_per_month": 3_000,
            "async_requests_per_minute": 0,
        },
        consumed_dimension_units={
            "requests_per_minute": 1,
            "download_bytes_per_month": 1_200,
        },
    )
    rows = {
        row.dimension: row
        for row in db.execute(select(ProviderQuotaWindow)).scalars().all()
    }
    assert rows["requests_per_minute"].consumed_units == 1
    assert rows["download_bytes_per_month"].consumed_units == 1_200
    assert "async_requests_per_minute" not in rows
    assert all(row.reserved_units == 0 for row in rows.values())


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
    assert all(
        dimension["source"].startswith("https://ibkrcampus.com/")
        for dimension in ibkr["dimensions"]
    )


def test_marketdata_app_records_documented_daily_credit_and_concurrency_limits():
    seed = settings.PROVIDER_RATE_LIMIT_SEEDS["marketdata_app"]
    contract = seed["quota_contract"]
    assert contract["dimensions"][0]["limit"] == 100
    assert contract["reset"] == "09:30 America/New_York"
    assert contract["concurrent_requests"] == 50
    assert seed.get("max_concurrency") is None


def test_operator_plan_limits_are_recorded_without_ignoring_bandwidth_caps():
    finnhub = settings.PROVIDER_RATE_LIMIT_SEEDS["finnhub"]["quota_contract"]
    assert {item["limit"] for item in finnhub["dimensions"]} == {30, 60}

    finra = settings.PROVIDER_RATE_LIMIT_SEEDS["finra"]["quota_contract"]
    tiingo = settings.PROVIDER_RATE_LIMIT_SEEDS["tiingo"]["quota_contract"]
    fmp = settings.PROVIDER_RATE_LIMIT_SEEDS["fmp"]["quota_contract"]
    finra_bytes = next(
        item for item in finra["dimensions"] if item["unit"] == "bytes"
    )
    assert finra_bytes["limit"] == 10 * 1024**3
    assert finra["dimension_costs_required"] is True
    assert tiingo["untracked_constraints"][0]["limit"] == 1024**3
    assert fmp["dimensions"][0]["limit"] == 250
    assert fmp["untracked_constraints"][0]["limit"] == 512 * 1024**2


def test_finra_synchronous_budget_uses_documented_byte_reservation():
    seed = settings.PROVIDER_RATE_LIMIT_SEEDS["finra"]
    contract = seed["quota_contract"]
    bytes_dimension = next(item for item in contract["dimensions"] if item["unit"] == "bytes")
    assert bytes_dimension["limit"] == 10 * 1024**3
    assert contract["maximum_synchronous_response_bytes"] == 3 * 1024**2
    source = DataSource(
        name="finra",
        config={"usage_tracking": settings.PROVIDER_USAGE_PROFILE_SEEDS["finra"]},
    )
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.SHORT_INTEREST,
        quota_scope=seed["quota_scope"],
        quota_contract=contract,
    )
    assert policy_has_known_quota(policy)
    assert provider_contract_operation_cost_known(policy, source, "fetch_short_interest")


@pytest.mark.asyncio
async def test_seeded_finra_policy_contains_dimension_cost_profile(db):
    async_db = AsyncSessionAdapter(db)
    await seed_provider_runtime(async_db)
    source = db.execute(select(DataSource).where(DataSource.name == "finra")).scalar_one()
    policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == source.id,
            ProviderPolicy.capability == ProviderCapability.SHORT_INTEREST,
        )
    ).scalar_one()
    assert policy_has_known_quota(policy)
    assert provider_contract_operation_cost_known(policy, source, "fetch_short_interest")
    assert source.config["usage_tracking"]["dimension_costs"][
        "download_bytes_per_calendar_month"
    ]["fetch_short_interest"] == 3 * 1024**2


def test_credit_contract_requires_the_requested_operation_cost():
    source = DataSource(
        name="marketdata_app",
        config={"usage_tracking": {"operation_costs": {"fetch_ohlcv": 1}}},
    )
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_contract={
            "dimensions": [
                {
                    "name": "credits",
                    "limit": 100,
                    "window_seconds": 86400,
                    "unit": "credits",
                    "scope": "api_key",
                    "source": "unit-test",
                }
            ],
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
            "dimensions": [
                {
                    "name": "weight",
                    "limit": 10,
                    "window_seconds": 60,
                    "unit": "weight",
                    "scope": "ip",
                    "source": "unit-test",
                }
            ],
            "reset": "fixed_minute",
            "dynamic_endpoint_weights": True,
        },
    )
    assert not provider_contract_operation_costs_configured(policy, source)
