from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from app.config import provider_rate_limit_seed, settings
from app.models.data_source import DataSource
from app.models.market_data_foundation import ProviderQuotaIdentity, ProviderQuotaWindow
from app.models.provider_runtime import ProviderCapability, ProviderPolicy
from app.providers.registry import (
    get_provider_usage_profile,
    supported_provider_names,
)
from app.services.provider_routing import (
    reserve_provider_contract,
    reserve_provider_quota,
    settle_provider_contract,
)
from app.services.provider_runtime import (
    ProviderQuotaUnknownError,
    ProviderRateLimitError,
    ResolvedProvider,
    _dimension_costs_for_operation,
    _observed_dimension_totals,
    policy_has_known_quota,
    provider_contract_operation_cost_known,
    provider_contract_operation_costs_configured,
    provider_rate_limit_error,
    quota_contract_missing_dimensions,
    quota_dimensions,
    seed_provider_runtime,
)
from tests.unit.conftest import AsyncSessionAdapter

INTENTIONAL_QUOTA_UNKNOWN_PROVIDERS = {
    # Public/provider-internal surfaces without a complete reviewed contract
    # in this branch. They stay visible to diagnostics but cannot be routed.
    "etf_holdings_internal",
    "fred",
    "nasdaq",
    "yfinance",
    "ondo_global_markets",
    "dinari",
    "alpaca_itn",
    "xstocks",
}


def test_registered_providers_are_explicitly_quota_reviewed_or_intentionally_unknown():
    registered = set(supported_provider_names())
    assert INTENTIONAL_QUOTA_UNKNOWN_PROVIDERS <= registered

    for provider_name in registered:
        seed = settings.PROVIDER_RATE_LIMIT_SEEDS.get(provider_name)
        if provider_name in INTENTIONAL_QUOTA_UNKNOWN_PROVIDERS:
            if seed is None:
                continue
            contract = seed.get("quota_contract") or {}
            assert (
                not contract.get("dimensions")
                or contract.get("unknown_dimensions")
                or contract.get("untracked_constraints")
            ), provider_name
            continue

        assert isinstance(seed, dict), provider_name
        contract = seed.get("quota_contract")
        assert isinstance(contract, dict), provider_name
        dimensions = contract.get("dimensions")
        assert isinstance(dimensions, list) and dimensions, provider_name
        assert str(contract.get("reset") or "").strip(), provider_name
        for dimension in dimensions:
            assert all(
                str(dimension.get(field) or "").strip()
                for field in ("name", "unit", "scope", "source")
            ), (provider_name, dimension)
            assert int(dimension["limit"]) > 0, (provider_name, dimension)
            assert int(dimension["window_seconds"]) > 0, (provider_name, dimension)


def test_published_bandwidth_pools_use_conservative_decimal_byte_ceilings():
    assert (
        provider_rate_limit_seed("finra")["quota_contract"]["dimensions"][2]["limit"]
        == 10_000_000_000
    )
    assert (
        provider_rate_limit_seed("tiingo")["quota_contract"]["untracked_constraints"][0]["limit"]
        == 1_000_000_000
    )
    assert (
        provider_rate_limit_seed("fmp")["quota_contract"]["untracked_constraints"][0]["limit"]
        == 512_000_000
    )
    for provider_name in ("finra", "tiingo", "fmp"):
        contract = provider_rate_limit_seed(provider_name)["quota_contract"]
        dimensions = contract.get("dimensions", []) + contract.get("untracked_constraints", [])
        byte_pools = [item for item in dimensions if item.get("unit") == "bytes"]
        assert byte_pools
        assert all(str(item.get("limit_basis", "")).startswith("decimal_bytes_") for item in byte_pools)


@pytest.mark.asyncio
async def test_seed_records_fred_v1_numeric_limit_without_applying_v2(db):
    async_db = AsyncSessionAdapter(db)
    await seed_provider_runtime(async_db)
    source = db.execute(select(DataSource).where(DataSource.name == "fred")).scalar_one()
    policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == source.id,
            ProviderPolicy.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    assert policy.quota_contract is not None
    assert policy.quota_contract["dimensions"] == [
        {
            "name": "requests_per_minute",
            "limit": 120,
            "window_seconds": 60,
            "unit": "requests",
            "scope": "provider_defined",
            "source": "https://fred.stlouisfed.org/docs/api/fred/errors.html",
            "reset": "rolling",
        }
    ]
    assert {
        "v1_enforcement_scope",
        "provider_adjustable_limits",
        "series_terms_and_redistribution",
    } <= set(policy.quota_contract["unknown_dimensions"])
    assert {
        "quota_contract.unknown_dimensions.v1_enforcement_scope",
        "quota_contract.unknown_dimensions.provider_adjustable_limits",
        "quota_contract.unknown_dimensions.series_terms_and_redistribution",
    } <= set(quota_contract_missing_dimensions(policy))
    assert policy.tokens_per_minute is None
    assert policy.burst_capacity is None
    assert policy.max_concurrency is None
    assert policy.quota_verified_at is None
    assert not policy_has_known_quota(policy)


@pytest.mark.asyncio
async def test_reviewed_fred_controls_promote_only_the_explicit_conservative_contract(db, monkeypatch):
    monkeypatch.setattr(settings, "FRED_REVIEWED_LIMIT_SCOPE", "api_key")
    monkeypatch.setattr(settings, "FRED_REVIEWED_REQUESTS_PER_MINUTE", 60)
    monkeypatch.setattr(settings, "FRED_SERIES_TERMS_REVIEWED", True)
    async_db = AsyncSessionAdapter(db)
    await seed_provider_runtime(async_db)
    source = db.execute(select(DataSource).where(DataSource.name == "fred")).scalar_one()
    policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == source.id,
            ProviderPolicy.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    assert policy.quota_contract["unknown_dimensions"] == []
    assert policy.quota_contract["dimensions"][0]["limit"] == 60
    assert policy.quota_contract["dimensions"][0]["scope"] == "api_key"
    assert quota_contract_missing_dimensions(policy) == []
    assert policy_has_known_quota(policy)


@pytest.mark.asyncio
async def test_seeded_tiingo_and_fmp_bandwidth_pools_remain_non_routable(db):
    async_db = AsyncSessionAdapter(db)
    await seed_provider_runtime(async_db)

    for provider_name in ("tiingo", "fmp"):
        source = db.execute(select(DataSource).where(DataSource.name == provider_name)).scalar_one()
        policy = db.execute(
            select(ProviderPolicy).where(
                ProviderPolicy.data_source_id == source.id,
                ProviderPolicy.capability == ProviderCapability.PRICE_HISTORY,
            )
        ).scalar_one()
        assert not policy_has_known_quota(policy)
        assert policy.quota_verified_at is None
        assert any(
            item.startswith("quota_contract.untracked_constraints.bandwidth_bytes")
            for item in quota_contract_missing_dimensions(policy)
        )


@pytest.mark.asyncio
async def test_runtime_seed_refreshes_provider_generated_contract_after_byte_map_change(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    complete_bounds = {
        "fetch_ohlcv": 1_000_000,
        "fetch_latest_ohlcv": 1_000_000,
        "get_current_price": 100_000,
        "bulk_fetch": 1_000_000,
        "search_instruments": 100_000,
        "get_instrument_profile": 100_000,
    }
    monkeypatch.setattr(settings, "TIINGO_OPERATION_BYTE_BOUNDS", complete_bounds)
    await seed_provider_runtime(async_db)
    source = db.execute(select(DataSource).where(DataSource.name == "tiingo")).scalar_one()
    policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == source.id,
            ProviderPolicy.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    assert policy_has_known_quota(policy)

    monkeypatch.setattr(settings, "TIINGO_OPERATION_BYTE_BOUNDS", {})
    await seed_provider_runtime(async_db)
    db.refresh(policy)
    assert not policy_has_known_quota(policy)
    assert policy.quota_verified_at is None
    assert any(
        item.startswith("quota_contract.untracked_constraints.bandwidth_bytes")
        for item in quota_contract_missing_dimensions(policy)
    )


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


def test_tiingo_byte_pool_requires_complete_operator_bounds_before_promotion(monkeypatch):
    bounds = {
        "fetch_ohlcv": 1_000_000,
        "fetch_latest_ohlcv": 1_000_000,
        "get_current_price": 100_000,
        "bulk_fetch": 1_000_000,
        "search_instruments": 100_000,
        "get_instrument_profile": 100_000,
    }
    monkeypatch.setattr(settings, "TIINGO_OPERATION_BYTE_BOUNDS", bounds)
    seed = provider_rate_limit_seed("tiingo")
    contract = seed["quota_contract"]
    assert contract["untracked_constraints"] == []
    bytes_dimension = next(item for item in contract["dimensions"] if item["unit"] == "bytes")
    assert bytes_dimension["limit"] == 1_000_000_000
    assert contract["dimension_costs_required"] is True
    assert seed["_byte_reservation_bounds"] == bounds
    profile = get_provider_usage_profile("tiingo")
    assert profile["dimension_costs"][bytes_dimension["name"]] == bounds
    assert profile["operation_costs"]["fetch_ohlcv"] == 1
    assert profile["operation_costs"]["get_current_price"] == 1
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope=seed["quota_scope"],
        quota_source=seed["quota_source"],
        quota_contract=contract,
    )
    assert policy_has_known_quota(policy)
    source = DataSource(
        name="tiingo",
        config={"usage_tracking": get_provider_usage_profile("tiingo")},
    )
    assert not provider_contract_operation_cost_known(policy, source, "fetch_ohlcv")
    assert provider_contract_operation_cost_known(
        policy, source, "fetch_ohlcv", usage_identity="AAPL"
    )
    assert provider_contract_operation_cost_known(
        policy, source, "get_current_price", usage_identity="AAPL"
    )
    assert provider_contract_operation_cost_known(
        policy, source, "bulk_fetch:d1", usage_identity="AAPL"
    )

    monkeypatch.setattr(settings, "TIINGO_OPERATION_BYTE_BOUNDS", {"fetch_ohlcv": 1_000_000})
    assert provider_rate_limit_seed("tiingo")["quota_contract"].get("untracked_constraints")

    malformed = dict(bounds)
    malformed["get_current_price"] = True
    monkeypatch.setattr(settings, "TIINGO_OPERATION_BYTE_BOUNDS", malformed)
    seed = provider_rate_limit_seed("tiingo")
    assert seed["quota_contract"].get("untracked_constraints")


def test_finra_async_download_requires_positive_bound_for_monthly_reservation(monkeypatch):
    source = DataSource(
        name="finra",
        config={"usage_tracking": settings.PROVIDER_USAGE_PROFILE_SEEDS["finra"]},
    )
    seed = settings.PROVIDER_RATE_LIMIT_SEEDS["finra"]
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.SHORT_INTEREST,
        quota_contract=seed["quota_contract"],
    )
    assert not provider_contract_operation_cost_known(policy, source, "download_async_result")

    monkeypatch.setattr(settings, "FINRA_ASYNC_MAX_RESULT_BYTES", 4 * 1024 * 1024)
    source.config = {"usage_tracking": get_provider_usage_profile("finra")}
    profile = source.config["usage_tracking"]
    assert profile["operation_costs"]["download_async_result"] == 1
    assert (
        profile["dimension_costs"]["download_bytes_per_calendar_month"]["download_async_result"]
        == 4 * 1024 * 1024
    )
    assert provider_contract_operation_cost_known(policy, source, "download_async_result")


def test_finra_async_boolean_bound_does_not_promote_bandwidth_profile(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_ASYNC_MAX_RESULT_BYTES", True)
    profile = get_provider_usage_profile("finra")
    assert "download_async_result" not in profile["operation_costs"]
    assert (
        "download_async_result"
        not in profile["dimension_costs"]["download_bytes_per_calendar_month"]
    )


def test_fred_non_boolean_terms_flag_does_not_promote_reviewed_limit(monkeypatch):
    monkeypatch.setattr(settings, "FRED_REVIEWED_LIMIT_SCOPE", "api_key")
    monkeypatch.setattr(settings, "FRED_REVIEWED_REQUESTS_PER_MINUTE", 60)
    monkeypatch.setattr(settings, "FRED_SERIES_TERMS_REVIEWED", "true")
    seed = provider_rate_limit_seed("fred")
    assert seed["quota_contract"].get("unknown_dimensions")


def test_finra_authenticated_dataset_usage_covers_cold_oauth_token_request():
    profile = get_provider_usage_profile("finra")
    assert profile["operation_costs"]["fetch_short_interest"] == 2
    assert profile["operation_costs"]["fetch_market_events"] == 2


def test_edgar_metadata_and_events_cover_cold_ticker_directory_lookup():
    profile = get_provider_usage_profile("edgar")
    assert profile["operation_costs"]["get_instrument_profile"] == 2
    assert profile["operation_costs"]["fetch_instrument_events"] == 2


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
async def test_distinct_identity_dimension_is_durable_and_not_request_counted(db):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="distinct-symbol-provider", is_active=True)
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="api_key",
        quota_source="unit-test provider contract",
        quota_contract={
            "reset": "provider_defined",
            "dimensions": [
                {
                    "name": "unique_symbols_per_month",
                    "limit": 2,
                    "window_seconds": 2_678_400,
                    "unit": "symbols",
                    "scope": "api_key",
                    "source": "https://provider.example/pricing",
                    "reset": "calendar_month_est",
                }
            ],
        },
    )
    resolved = ResolvedProvider(
        provider_name="distinct-symbol-provider",
        provider=object(),
        data_source=source,
        policy=policy,
        health=None,  # type: ignore[arg-type]
    )
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    first = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        usage_identity="aapl",
        now=now,
    )
    repeat = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        usage_identity="AAPL",
        now=now,
    )
    second = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        usage_identity="MSFT",
        now=now,
    )
    exhausted = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        usage_identity="NVDA",
        now=now,
    )
    assert first is not None and len(first) == 1
    assert repeat == []
    assert second is not None and len(second) == 1
    assert exhausted is None
    identities = db.execute(select(ProviderQuotaIdentity)).scalars().all()
    assert {row.identity_key for row in identities} == {"AAPL", "MSFT"}
    settle_provider_contract(
        first,
        units=1,
        success=False,
        reserved_dimension_units={"unique_symbols_per_month": 1},
        consumed_dimension_units={"unique_symbols_per_month": 1},
        consume_on_failure_dimensions={"unique_symbols_per_month"},
    )
    db.flush()
    window = db.execute(
        select(ProviderQuotaWindow).where(
            ProviderQuotaWindow.dimension == "unique_symbols_per_month"
        )
    ).scalar_one()
    assert window.consumed_units == 1


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
    assert provider_contract_operation_cost_known(
        policy, source, "fetch_ohlcv", operation_cost_override=4
    )


def test_simple_request_contract_is_non_routable_without_operation_costs():
    source = DataSource(name="unprofiled-provider", config={"usage_tracking": {}})
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.LATEST_PRICE,
        quota_contract={
            "dimensions": [
                {
                    "name": "requests_per_minute",
                    "limit": 60,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "api_key",
                    "source": "unit-test",
                }
            ],
            "reset": "rolling",
        },
    )
    assert not provider_contract_operation_cost_known(policy, source, "get_current_price")
    source.config["usage_tracking"] = {"operation_costs": {"get_current_price": 1}}
    assert provider_contract_operation_cost_known(policy, source, "get_current_price")
    source.config["usage_tracking"]["operation_costs"]["get_current_price"] = 0
    assert not provider_contract_operation_cost_known(policy, source, "get_current_price")
    source.config["usage_tracking"]["operation_costs"]["get_current_price"] = "not-a-cost"
    assert not provider_contract_operation_cost_known(policy, source, "get_current_price")
    assert not provider_contract_operation_cost_known(
        policy, source, "get_current_price", operation_cost_override=0
    )


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
    source.config["usage_tracking"]["dimension_costs"]["requests_per_minute"] = {
        "fetch_short_interest": 0
    }
    assert not provider_contract_operation_cost_known(
        policy, source, "fetch_short_interest"
    )
    with pytest.raises(ProviderQuotaUnknownError):
        _dimension_costs_for_operation(
            policy, source, "fetch_short_interest", default_units=1
        )
    source.config["usage_tracking"]["dimension_costs"].pop("requests_per_minute")
    for invalid_bound in (0, -1, True, 1.5, "not-a-bound"):
        source.config["usage_tracking"]["dimension_costs"][
            "download_bytes_per_month"
        ]["fetch_short_interest"] = invalid_bound
        assert not provider_contract_operation_cost_known(
            policy, source, "fetch_short_interest"
        )
        with pytest.raises(ProviderQuotaUnknownError):
            _dimension_costs_for_operation(
                policy, source, "fetch_short_interest", default_units=1
            )
    source.config["usage_tracking"]["dimension_costs"][
        "download_bytes_per_month"
    ]["fetch_short_interest"] = 3_000_000
    source.config["usage_tracking"].pop("dimension_costs")
    assert not provider_contract_operation_cost_known(policy, source, "fetch_short_interest")


def test_operation_and_dimension_costs_may_be_carried_in_reviewed_contract():
    source = DataSource(name="contract-cost-provider", config={})
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.SHORT_INTEREST,
        quota_contract={
            "dimensions": [
                {
                    "name": "download_bytes",
                    "limit": 1000,
                    "window_seconds": 60,
                    "unit": "bytes",
                    "scope": "api_key",
                    "source": "operator-review",
                }
            ],
            "reset": "rolling",
            "operation_costs_required": True,
            "operation_costs": {"fetch_short_interest": 1},
            "dimension_costs_required": True,
            "dimension_costs": {"download_bytes": {"fetch_short_interest": 100}},
        },
    )
    assert provider_contract_operation_cost_known(policy, source, "fetch_short_interest")


def test_operation_cost_readiness_uses_reviewed_contract_map():
    source = DataSource(name="contract-cost-provider", config={})
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_contract={
            "dimensions": [
                {
                    "name": "request_weight",
                    "limit": 100,
                    "window_seconds": 60,
                    "unit": "weight",
                    "scope": "ip",
                    "source": "operator-review",
                }
            ],
            "reset": "rolling",
            "dynamic_endpoint_weights": True,
            "operation_costs": {"fetch_ohlcv": 4},
        },
    )
    assert provider_contract_operation_costs_configured(policy, source)


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
        quota_source="unit-test provider contract",
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
    assert {dimension["limit"] for dimension in ibkr["dimensions"]} == {5, 10, 50}
    assert all(
        dimension["source"].startswith("https://ibkrcampus.com/")
        for dimension in ibkr["dimensions"]
    )
    assert (
        ibkr["endpoint_constraints"]["iserver/marketdata/history"]["max_response_points"]
        == 1000
    )
    usage = settings.PROVIDER_USAGE_PROFILE_SEEDS["ibkr"]
    assert usage["operation_costs"]["get_current_price"] == 2
    assert usage["dimension_costs"]["historical_requests_per_minute"]["get_current_price"] == {}


def test_marketdata_app_records_documented_daily_credit_and_concurrency_limits():
    seed = settings.PROVIDER_RATE_LIMIT_SEEDS["marketdata_app"]
    contract = seed["quota_contract"]
    assert contract["dimensions"][0]["limit"] == 100
    assert contract["reset"] == "09:30 America/New_York"
    assert contract["dimensions"][1]["name"] == "concurrent_requests"
    assert contract["dimensions"][1]["limit"] == 50
    assert contract["dimensions"][1]["unit"] == "concurrent_requests"
    assert seed.get("max_concurrency") is None
    assert {item["quota_group"] for item in contract["dimensions"]} == {"account"}


def test_account_and_ip_scoped_provider_contracts_declare_cross_capability_groups():
    grouped_providers = {
        "alpaca",
        "massive",
        "alpha_vantage",
        "openfigi",
        "edgar",
        "finra",
        "finra_otc_directory",
        "coingecko",
        "binance",
        "coinbase",
        "robinhood_tokens",
        "bybit_xstocks",
        "gate_tradfi",
        "tiingo",
        "twelve_data",
        "finnhub",
        "eodhd",
        "fmp",
        "marketdata_app",
        "tradier",
        "marketstack",
        "ibkr",
    }
    for provider_name in grouped_providers:
        dimensions = settings.PROVIDER_RATE_LIMIT_SEEDS[provider_name]["quota_contract"][
            "dimensions"
        ]
        assert dimensions, provider_name
        assert all(str(item.get("quota_group") or "").strip() for item in dimensions), provider_name


@pytest.mark.asyncio
async def test_explicit_quota_group_shares_one_budget_across_capabilities(db):
    """Provider account budgets must not be multiplied by capability."""

    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="account-budget-provider", is_active=True)
    db.add(source)
    db.flush()
    contract = {
        "reset": "rolling",
        "dimensions": [
            {
                "name": "credits_per_day",
                "limit": 3,
                "window_seconds": 86400,
                "unit": "credits",
                "scope": "api_key",
                "quota_group": "account",
                "source": "https://provider.example/rate-limits",
            }
        ],
    }
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="api_key",
        quota_source="unit-test provider contract",
        quota_contract=contract,
    )
    resolved = ResolvedProvider(
        provider_name="account-budget-provider",
        provider=object(),
        data_source=source,
        policy=policy,
        health=None,  # type: ignore[arg-type]
    )
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)

    first = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=2,
        now=now,
    )
    second = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.LATEST_PRICE.value,
        units=2,
        now=now,
    )

    assert first is not None and len(first) == 1
    assert second is None
    row = db.execute(select(ProviderQuotaWindow)).scalar_one()
    assert row.quota_group == "account"
    assert row.reserved_units == 2


@pytest.mark.asyncio
async def test_ungrouped_quota_dimensions_remain_capability_scoped(db):
    """No provider grouping is inferred when a contract omits the marker."""

    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="capability-budget-provider", is_active=True)
    db.add(source)
    db.flush()
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    first = await reserve_provider_quota(
        async_db,
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY.value,
        dimension="requests_per_minute",
        units=1,
        limit_units=1,
        now=now,
    )
    second = await reserve_provider_quota(
        async_db,
        data_source_id=source.id,
        capability=ProviderCapability.LATEST_PRICE.value,
        dimension="requests_per_minute",
        units=1,
        limit_units=1,
        now=now,
    )

    assert first is not None and second is not None
    assert {row.quota_group for row in db.execute(select(ProviderQuotaWindow)).scalars()} == {
        ProviderCapability.PRICE_HISTORY.value,
        ProviderCapability.LATEST_PRICE.value,
    }


def test_marketdata_app_only_widens_daily_limit_for_exact_reviewed_plan_pair(monkeypatch):
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "")
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 0)
    conservative = provider_rate_limit_seed("marketdata_app")
    assert conservative["quota_contract"]["dimensions"][0]["limit"] == 100
    assert "account_plan" not in conservative["quota_contract"]["dimensions"][0]

    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "starter")
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 10000)
    reviewed = provider_rate_limit_seed("marketdata_app")
    dimension = reviewed["quota_contract"]["dimensions"][0]
    assert dimension["limit"] == 10000
    assert dimension["account_plan"] == "starter"
    assert dimension["account_limit_reviewed"] is True

    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 100)
    mismatched = provider_rate_limit_seed("marketdata_app")
    assert mismatched["quota_contract"]["dimensions"][0]["limit"] == 100
    assert "account_plan" not in mismatched["quota_contract"]["dimensions"][0]

    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "quant")
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 100000)
    unsupported = provider_rate_limit_seed("marketdata_app")
    assert unsupported["quota_contract"]["dimensions"][0]["limit"] == 100


def test_blank_explicit_quota_group_fails_closed():
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="api_key",
        quota_source="unit-test provider contract",
        quota_contract={
            "reset": "rolling",
            "dimensions": [
                {
                    "name": "requests_per_minute",
                    "limit": 1,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "api_key",
                    "quota_group": "   ",
                    "source": "https://provider.example/rate-limits",
                }
            ],
        },
    )

    assert quota_dimensions(policy) == []


def test_marketdata_app_option_chain_cost_requires_explicit_symbol_bound(monkeypatch):
    monkeypatch.setattr(settings, "MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS", 0)
    assert "fetch_option_chain" not in get_provider_usage_profile("marketdata_app")[
        "operation_costs"
    ]

    monkeypatch.setattr(settings, "MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS", 12)
    profile = get_provider_usage_profile("marketdata_app")
    assert profile["operation_costs"]["fetch_option_chain"] == 12


def test_marketdata_app_headers_settle_actual_credit_charge_and_cumulative_total():
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.OPTION_CHAIN,
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
    measurement = SimpleNamespace(
        response_headers={
            "x-api-ratelimit-limit": "100",
            "x-api-ratelimit-remaining": "87",
            "x-api-ratelimit-consumed": "4",
        }
    )
    from app.services.provider_runtime import _consumed_dimension_costs

    assert _consumed_dimension_costs(policy, measurement, {"credits_per_day": 12}) == {
        "credits_per_day": 4
    }
    assert _observed_dimension_totals(policy, measurement) == {"credits_per_day": 13}

    mismatched = SimpleNamespace(
        response_headers={
            "x-api-ratelimit-limit": "10",
            "x-api-ratelimit-remaining": "8",
            "x-api-ratelimit-consumed": "2",
        }
    )
    assert _observed_dimension_totals(policy, mismatched) == {}


def test_non_applicable_dimension_is_not_charged_during_runtime_settlement():
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.SHORT_INTEREST,
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
                    "name": "async_download_bytes",
                    "limit": 1000,
                    "window_seconds": 60,
                    "unit": "bytes",
                    "scope": "api_key",
                    "source": "unit-test contract",
                },
            ],
        },
    )
    from app.services.provider_runtime import _consumed_dimension_costs

    measurement = SimpleNamespace(http_requests=1, response_bytes=123)
    assert _consumed_dimension_costs(
        policy,
        measurement,
        {"requests_per_minute": 1, "async_download_bytes": 0},
    ) == {"requests_per_minute": 1, "async_download_bytes": 0}


@pytest.mark.asyncio
async def test_in_flight_concurrency_dimension_is_released_not_consumed(db):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="concurrency-provider", is_active=True)
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="api_key",
        quota_source="unit-test provider contract",
        quota_contract={
            "reset": "rolling",
            "dimensions": [
                {
                    "name": "concurrent_requests",
                    "limit": 2,
                    "window_seconds": 1,
                    "unit": "concurrent_requests",
                    "scope": "api_key",
                    "source": "https://provider.example/rate-limits",
                    "reset": "rolling",
                }
            ],
        },
    )
    resolved = ResolvedProvider(
        provider_name="concurrency-provider",
        provider=object(),
        data_source=source,
        policy=policy,
        health=None,  # type: ignore[arg-type]
    )
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    first = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=5,
        now=now,
    )
    second = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=7,
        now=now,
    )
    exhausted = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=2,
        now=now,
    )
    assert first is not None and second is not None and exhausted is None

    settle_provider_contract(
        first,
        units=1,
        success=True,
        reserved_dimension_units={"concurrent_requests": 1},
        consumed_dimension_units={"concurrent_requests": 1},
        release_only_dimensions={"concurrent_requests"},
    )
    released = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        now=now,
    )
    assert released is not None
    window = db.execute(select(ProviderQuotaWindow)).scalars().one()
    assert window.consumed_units == 0
    assert window.reserved_units == 2


@pytest.mark.asyncio
async def test_failed_contract_rolls_back_one_in_flight_slot(db):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="rollback-concurrency-provider", is_active=True)
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="api_key",
        quota_source="unit-test provider contract",
        quota_contract={
            "reset": "rolling",
            "dimensions": [
                {
                    "name": "concurrent_requests",
                    "limit": 2,
                    "window_seconds": 1,
                    "unit": "concurrent_requests",
                    "scope": "api_key",
                    "source": "https://provider.example/rate-limits",
                    "reset": "rolling",
                },
                {
                    "name": "requests_per_minute",
                    "limit": 1,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "api_key",
                    "source": "https://provider.example/rate-limits",
                    "reset": "rolling",
                },
            ],
        },
    )
    resolved = ResolvedProvider(
        provider_name="rollback-concurrency-provider",
        provider=object(),
        data_source=source,
        policy=policy,
        health=None,  # type: ignore[arg-type]
    )

    result = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=9,
        dimension_units={"concurrent_requests": 9, "requests_per_minute": 2},
        now=datetime(2026, 9, 9, 12, 0, tzinfo=UTC),
    )

    assert result is None
    db.flush()
    windows = db.execute(select(ProviderQuotaWindow)).scalars().all()
    assert {window.dimension: (window.reserved_units, window.consumed_units) for window in windows} == {
        "concurrent_requests": (0, 0),
        "requests_per_minute": (0, 0),
    }


def test_provider_reset_metadata_preserves_documented_calendar_boundaries():
    tiingo = settings.PROVIDER_RATE_LIMIT_SEEDS["tiingo"]["quota_contract"]
    assert tiingo["untracked_constraints"][0]["reset"] == "calendar_month_est"

    coingecko = settings.PROVIDER_RATE_LIMIT_SEEDS["coingecko"]["quota_contract"]
    assert [item["reset"] for item in coingecko["dimensions"]] == [
        "rolling",
        "provider_defined",
    ]

    twelve = settings.PROVIDER_RATE_LIMIT_SEEDS["twelve_data"]["quota_contract"]
    assert [item["reset"] for item in twelve["dimensions"]] == [
        "fixed_minute",
        "calendar_day_utc",
    ]

    eodhd = settings.PROVIDER_RATE_LIMIT_SEEDS["eodhd"]["quota_contract"]
    assert [item["reset"] for item in eodhd["dimensions"]] == [
        "rolling",
        "calendar_day_gmt",
    ]
    assert [item["limit"] for item in eodhd["dimensions"]] == [1000, 20]
    assert [item["unit"] for item in eodhd["dimensions"]] == ["requests", "calls"]
    assert eodhd["operation_costs_required"] is True
    assert settings.PROVIDER_USAGE_PROFILE_SEEDS["eodhd"]["operation_costs"]["get_instrument_profile"] == 10

    gate = settings.PROVIDER_RATE_LIMIT_SEEDS["gate_tradfi"]["quota_contract"]
    assert gate.get("untracked_constraints", []) == []
    assert gate["dimensions"] == [
        {
            "name": "stock_public_requests_per_second",
            "limit": 5,
            "window_seconds": 1,
                "unit": "requests",
                "scope": "ip",
                "quota_group": "ip",
                "source": "https://www.gate.com/docs/developers/apiv4/en/",
        }
    ]


def test_tokenized_quote_usage_profiles_charge_asset_and_quote_requests():
    for provider_name in (
        "xstocks",
        "robinhood_tokens",
        "bybit_xstocks",
        "gate_tradfi",
        "kraken_xstocks",
        "dinari",
        "ondo_global_markets",
    ):
        profile = get_provider_usage_profile(provider_name)
        assert profile["operation_costs"]["discover_tokenized_assets"] == 1
        assert profile["operation_costs"]["get_tokenized_asset"] == 1
        expected_price_cost = 4 if provider_name == "robinhood_tokens" else 2
        assert profile["operation_costs"]["get_tokenized_price"] == expected_price_cost
        if provider_name == "dinari":
            assert profile["operation_costs"]["get_tokenized_quote"] == 2


def test_tokenized_history_operations_charge_the_metadata_resolution_and_data_read():
    assert settings.PROVIDER_USAGE_PROFILE_SEEDS["dinari"]["operation_costs"] == {
        "discover_tokenized_assets": 1,
        "get_tokenized_asset": 1,
        "get_tokenized_price": 2,
        "get_tokenized_quote": 2,
        "fetch_tokenized_historical_prices": 2,
        "fetch_tokenized_news": 2,
        "fetch_tokenized_dividends": 2,
        "fetch_tokenized_splits": 2,
    }
    assert settings.PROVIDER_USAGE_PROFILE_SEEDS["ondo_global_markets"]["operation_costs"] == {
        "discover_tokenized_assets": 1,
        "get_tokenized_asset": 1,
        "get_tokenized_price": 2,
        "fetch_tokenized_market_data": 2,
        "fetch_tokenized_ohlc": 2,
    }


def test_coingecko_profile_usage_profile_covers_id_resolution_and_metadata():
    profile = get_provider_usage_profile("coingecko")
    assert profile["operation_costs"] == {
        "search_instruments": 1,
        "discover_universe_page": 1,
        "get_instrument_profile": 2,
    }


def test_alpha_vantage_profile_covers_each_single_query_operation():
    profile = get_provider_usage_profile("alpha_vantage")
    assert profile["operation_costs"] == {
        "search_instruments": 1,
        "fetch_ohlcv": 1,
        "fetch_latest_ohlcv": 1,
        "get_current_price": 1,
        "bulk_fetch": 1,
        "fetch_rfr_ohlcv": 1,
        "discover_universe_page": 1,
        "fetch_market_events": 1,
        "fetch_instrument_events": 1,
    }


def test_optional_latest_price_profiles_charge_the_actual_quote_operation():
    for provider_name in ("tiingo", "eodhd", "fmp", "marketstack", "marketdata_app"):
        assert get_provider_usage_profile(provider_name)["operation_costs"][
            "get_current_price"
        ] == 1


def test_fmp_profile_charges_market_event_calendar_operation():
    assert get_provider_usage_profile("fmp")["operation_costs"]["fetch_market_events"] == 1


def test_deep_history_profiles_charge_the_bulk_fetch_operation():
    for provider_name in (
        "alpha_vantage",
        "fred",
        "finnhub",
        "tradier",
        "tiingo",
        "eodhd",
        "fmp",
        "marketdata_app",
    ):
        assert get_provider_usage_profile(provider_name)["operation_costs"]["bulk_fetch"] == 1


def test_single_request_provider_profiles_are_explicit():
    expected = {
        "alpaca": {
            "get_current_price": 1,
            "fetch_rfr_ohlcv": 1,
            "discover_universe_page": 1,
        },
        "massive": {
            "search_instruments": 1,
            "discover_universe_page": 1,
            "fetch_market_events": 1,
            "fetch_market_holidays": 1,
        },
        "fred": {
            "fetch_ohlcv": 1,
            "fetch_latest_ohlcv": 1,
            "get_current_price": 1,
            "bulk_fetch": 1,
            "fetch_rfr_ohlcv": 1,
        },
        "openfigi": {
            "fetch_stable_identifiers": 1,
            "resolve_instrument_profile": 1,
        },
        "coinbase": {"get_current_price": 1, "discover_universe_page": 1},
        "kraken": {"get_current_price": 1, "discover_universe_page": 1},
        "marketstack": {"discover_universe_page": 1, "get_current_price": 1},
        "tradier": {
            "fetch_ohlcv": 1,
            "fetch_latest_ohlcv": 1,
            "get_current_price": 1,
            "search_instruments": 1,
            "bulk_fetch": 1,
            "list_option_expirations": 1,
            "fetch_option_chain": 1,
        },
    }
    for provider_name, operation_costs in expected.items():
        assert get_provider_usage_profile(provider_name)["operation_costs"] == operation_costs


def test_twelve_data_cumulative_credit_headers_update_only_matching_minute_window():
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_contract={
            "reset": "fixed_minute",
            "dimensions": [
                {
                    "name": "credits_per_minute",
                    "limit": 8,
                    "window_seconds": 60,
                    "unit": "credits",
                    "scope": "api_key",
                    "source": "https://support.twelvedata.com/en/articles/5713553-control-over-usage",
                }
            ]
        },
    )
    measurement = SimpleNamespace(
        response_headers={"Api-Credits-Used": "3", "api-credits-left": "5"}
    )
    assert _observed_dimension_totals(policy, measurement) == {"credits_per_minute": 3}

    mismatched = SimpleNamespace(
        response_headers={"api-credits-used": "3", "api-credits-left": "4"}
    )
    assert _observed_dimension_totals(policy, mismatched) == {}


def test_provider_native_tradier_and_binance_counters_require_contract_match():
    tradier_policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.LATEST_PRICE,
        quota_contract={
            "reset": "rolling",
            "dimensions": [
                {
                    "name": "market_data_requests_per_minute",
                    "limit": 120,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "production_token",
                    "source": "https://docs.tradier.com/docs/rate-limiting",
                }
            ],
        },
    )
    assert _observed_dimension_totals(
        tradier_policy,
        SimpleNamespace(
            response_headers={
                "x-ratelimit-allowed": "120",
                "x-ratelimit-used": "17",
                "x-ratelimit-available": "103",
            }
        ),
    ) == {"market_data_requests_per_minute": 17}
    assert _observed_dimension_totals(
        tradier_policy,
        SimpleNamespace(
            response_headers={
                "x-ratelimit-allowed": "60",
                "x-ratelimit-used": "17",
                "x-ratelimit-available": "43",
            }
        ),
    ) == {}

    binance_policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.LATEST_PRICE,
        quota_contract={
            "reset": "fixed_minute",
            "dimensions": [
                {
                    "name": "request_weight_per_minute",
                    "limit": 6000,
                    "window_seconds": 60,
                    "unit": "weight",
                    "scope": "ip",
                    "source": "https://developers.binance.com/en/docs/products/spot/rest-api",
                }
            ],
        },
    )
    assert _observed_dimension_totals(
        binance_policy,
        SimpleNamespace(response_headers={"x-mbx-used-weight-1m": "42"}),
    ) == {"request_weight_per_minute": 42}

    bybit_policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.TOKENIZED_ASSETS,
        quota_contract={
            "reset": "rolling",
            "dimensions": [
                {
                    "name": "http_requests_per_five_seconds",
                    "limit": 600,
                    "window_seconds": 5,
                    "unit": "requests",
                    "scope": "ip",
                    "source": "https://bybit-exchange.github.io/docs/v5/rate-limit",
                }
            ],
        },
    )
    assert _observed_dimension_totals(
        bybit_policy,
        SimpleNamespace(
            response_headers={
                "x-bapi-limit": "600",
                "x-bapi-limit-status": "587",
            }
        ),
    ) == {"http_requests_per_five_seconds": 13}
    assert _observed_dimension_totals(
        bybit_policy,
        SimpleNamespace(
            response_headers={
                "x-bapi-limit": "100",
                "x-bapi-limit-status": "87",
            }
        ),
    ) == {}

    gate_policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.TOKENIZED_ASSETS,
        quota_contract={
            "reset": "rolling",
            "dimensions": [
                {
                    "name": "stock_public_requests_per_second",
                    "limit": 5,
                    "window_seconds": 1,
                    "unit": "requests",
                    "scope": "ip",
                    "source": "https://www.gate.com/docs/developers/apiv4/en/stock/",
                }
            ],
        },
    )
    assert _observed_dimension_totals(
        gate_policy,
        SimpleNamespace(
            response_headers={
                "x-ratelimit-limit": "5",
                "x-ratelimit-remaining": "3",
            }
        ),
    ) == {"stock_public_requests_per_second": 2}
    assert _observed_dimension_totals(
        gate_policy,
        SimpleNamespace(
            response_headers={
                "x-ratelimit-limit": "10",
                "x-ratelimit-remaining": "8",
            }
        ),
    ) == {}


@pytest.mark.asyncio
async def test_calendar_day_reservation_changes_at_utc_midnight(db):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="calendar-day-provider", is_active=True)
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="api_key",
        quota_source="unit-test provider contract",
        quota_contract={
            "reset": "per_dimension",
            "dimensions": [
                {
                    "name": "credits_per_day",
                    "limit": 1,
                    "window_seconds": 86400,
                    "unit": "credits",
                    "scope": "api_key",
                    "source": "unit-test",
                    "reset": "calendar_day_utc",
                }
            ],
        },
    )
    resolved = ResolvedProvider(
        provider_name="calendar-day-provider",
        provider=object(),
        data_source=source,
        policy=policy,
        health=None,  # type: ignore[arg-type]
    )
    first = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        now=datetime(2026, 9, 5, 23, 59, tzinfo=UTC),
    )
    second = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        now=datetime(2026, 9, 6, 0, 1, tzinfo=UTC),
    )
    assert first is not None and second is not None
    assert first[0].window_started_at != second[0].window_started_at


@pytest.mark.asyncio
async def test_provider_defined_daily_reservation_uses_conservative_rolling_boundary(db):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="provider-defined-daily", is_active=True)
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="api_key",
        quota_source="unit-test provider contract",
        quota_contract={
            "reset": "provider_defined_daily",
            "dimensions": [
                {
                    "name": "requests_per_day",
                    "limit": 1,
                    "window_seconds": 86400,
                    "unit": "requests",
                    "scope": "api_key",
                    "source": "operator-dashboard",
                }
            ],
        },
    )
    resolved = ResolvedProvider(
        provider_name="provider-defined-daily",
        provider=object(),
        data_source=source,
        policy=policy,
        health=None,  # type: ignore[arg-type]
    )
    start = datetime(2026, 9, 5, 23, 59, tzinfo=UTC)
    first = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        now=start,
    )
    before_expiry = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        now=start + timedelta(seconds=86400 - 1),
    )
    after_expiry = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        now=start + timedelta(seconds=86400 + 1),
    )
    assert first is not None
    assert before_expiry is None
    assert after_expiry is not None


@pytest.mark.asyncio
async def test_eastern_calendar_month_reservation_follows_tiingo_reset_boundary(db):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="eastern-month-provider", is_active=True)
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="api_key",
        quota_source="unit-test provider contract",
        quota_contract={
            "reset": "provider_defined",
            "dimensions": [
                {
                    "name": "bandwidth_bytes_per_month",
                    "limit": 1000,
                    "window_seconds": 2_678_400,
                    "unit": "bytes",
                    "scope": "api_key",
                    "source": "https://www.tiingo.com/about/pricing",
                    "reset": "calendar_month_est",
                }
            ],
        },
    )
    resolved = ResolvedProvider(
        provider_name="eastern-month-provider",
        provider=object(),
        data_source=source,
        policy=policy,
        health=None,  # type: ignore[arg-type]
    )
    before_reset = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        now=datetime(2026, 10, 1, 3, 30, tzinfo=UTC),
    )
    after_reset = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        now=datetime(2026, 10, 1, 4, 30, tzinfo=UTC),
    )
    assert before_reset is not None and after_reset is not None
    assert before_reset[0].window_started_at == datetime(2026, 9, 1, 4, tzinfo=UTC)
    assert after_reset[0].window_started_at == datetime(2026, 10, 1, 4, tzinfo=UTC)


@pytest.mark.asyncio
async def test_eastern_calendar_day_reservation_follows_tiingo_reset_boundary(db):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="eastern-day-provider", is_active=True)
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="api_key",
        quota_source="unit-test provider contract",
        quota_contract={
            "reset": "provider_defined",
            "dimensions": [
                {
                    "name": "requests_per_day",
                    "limit": 1,
                    "window_seconds": 86400,
                    "unit": "requests",
                    "scope": "api_key",
                    "source": "https://www.tiingo.com/about/pricing",
                    "reset": "calendar_day_est",
                }
            ],
        },
    )
    resolved = ResolvedProvider(
        provider_name="eastern-day-provider",
        provider=object(),
        data_source=source,
        policy=policy,
        health=None,  # type: ignore[arg-type]
    )
    before_reset = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        now=datetime(2026, 9, 9, 3, 30, tzinfo=UTC),
    )
    after_reset = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        now=datetime(2026, 9, 9, 4, 30, tzinfo=UTC),
    )
    assert before_reset is not None and after_reset is not None
    assert before_reset[0].window_started_at == datetime(2026, 9, 8, 4, tzinfo=UTC)
    assert after_reset[0].window_started_at == datetime(2026, 9, 9, 4, tzinfo=UTC)


@pytest.mark.asyncio
async def test_rolling_thirty_day_reservation_expires_at_exact_fmp_boundary(db):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="rolling-thirty-day-provider", is_active=True)
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="api_key",
        quota_source="unit-test provider contract",
        quota_contract={
            "reset": "provider_defined",
            "dimensions": [
                {
                    "name": "bandwidth_bytes_per_30_days",
                    "limit": 1,
                    "window_seconds": 2_592_000,
                    "unit": "bytes",
                    "scope": "api_key",
                    "source": "operator_account_dashboard_2026-09-07",
                    "reset": "rolling_30_days",
                }
            ],
        },
    )
    resolved = ResolvedProvider(
        provider_name="rolling-thirty-day-provider",
        provider=object(),
        data_source=source,
        policy=policy,
        health=None,  # type: ignore[arg-type]
    )
    start = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    first = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        now=start,
    )
    still_active = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        now=start + timedelta(seconds=2_592_000 - 1),
    )
    expired = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        now=start + timedelta(seconds=2_592_000 + 1),
    )
    assert first is not None
    assert still_active is None
    assert expired is not None


def test_operator_plan_limits_are_recorded_without_ignoring_bandwidth_caps():
    finnhub = settings.PROVIDER_RATE_LIMIT_SEEDS["finnhub"]["quota_contract"]
    assert {item["limit"] for item in finnhub["dimensions"]} == {30, 60}

    finra = settings.PROVIDER_RATE_LIMIT_SEEDS["finra"]["quota_contract"]
    finra_otc = settings.PROVIDER_RATE_LIMIT_SEEDS["finra_otc_directory"]["quota_contract"]
    tiingo = settings.PROVIDER_RATE_LIMIT_SEEDS["tiingo"]["quota_contract"]
    fmp = settings.PROVIDER_RATE_LIMIT_SEEDS["fmp"]["quota_contract"]
    finra_bytes = next(
        item for item in finra["dimensions"] if item["unit"] == "bytes"
    )
    assert finra_bytes["limit"] == 10_000_000_000
    assert finra["dimension_costs_required"] is True
    assert finra_otc["dimensions"][0]["limit"] == 1200
    assert finra_otc["dimensions"][0]["scope"] == "ip"
    assert finra_otc["maximum_synchronous_response_bytes"] == 3 * 1024**2
    assert tiingo["dimensions"][0]["name"] == "unique_symbols_per_month"
    assert tiingo["dimensions"][0]["limit"] == 500
    assert tiingo["dimensions"][0]["reset"] == "calendar_month_est"
    assert tiingo["untracked_constraints"][0]["limit"] == 1_000_000_000
    assert fmp["dimensions"][0]["limit"] == 250
    assert fmp["untracked_constraints"][0]["limit"] == 512_000_000
    assert fmp["untracked_constraints"][0]["window_seconds"] == 2_592_000
    assert fmp["untracked_constraints"][0]["reset"] == "rolling_30_days"


def test_compound_directory_usage_is_not_undercharged_or_guessed():
    nasdaq_profile = get_provider_usage_profile("nasdaq")
    assert nasdaq_profile["operation_costs"]["discover_universe_page"] == 2
    assert nasdaq_profile["operation_costs"]["reconcile_universe_page"] == 2

    finra_seed = settings.PROVIDER_RATE_LIMIT_SEEDS["finra_otc_directory"]
    assert finra_seed["quota_contract"]["operation_costs_required"] is True
    finra_profile = get_provider_usage_profile("finra_otc_directory")
    assert finra_profile["operation_costs"] == {}
    source = DataSource(
        name="finra_otc_directory",
        config={"usage_tracking": finra_profile},
    )
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.UNIVERSE_DISCOVERY,
        quota_contract=finra_seed["quota_contract"],
    )
    assert not provider_contract_operation_cost_known(
        policy,
        source,
        "discover_universe_page",
    )


def test_finra_otc_reviewed_operation_costs_are_explicitly_admitted(monkeypatch):
    monkeypatch.setattr(
        settings,
        "FINRA_OTC_OPERATION_COSTS",
        {"discover_universe_page": 3, "reconcile_universe_page": 3},
    )
    profile = get_provider_usage_profile("finra_otc_directory")
    assert profile["operation_costs"] == {
        "discover_universe_page": 3,
        "reconcile_universe_page": 3,
    }
    source = DataSource(
        name="finra_otc_directory",
        config={"usage_tracking": profile},
    )
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.UNIVERSE_DISCOVERY,
        quota_contract=settings.PROVIDER_RATE_LIMIT_SEEDS["finra_otc_directory"][
            "quota_contract"
        ],
    )
    assert provider_contract_operation_cost_known(policy, source, "discover_universe_page:OTC:0")
    assert provider_contract_operation_cost_known(policy, source, "reconcile_universe_page:OTC:0")
    assert provider_contract_operation_costs_configured(policy, source)


def test_coinbase_public_token_bucket_matches_documented_burst():
    seed = settings.PROVIDER_RATE_LIMIT_SEEDS["coinbase"]
    assert seed["tokens_per_minute"] == 600
    assert seed["burst_capacity"] == 15
    dimension = seed["quota_contract"]["dimensions"][0]
    assert dimension["limit"] == 10
    assert dimension["window_seconds"] == 1
    assert dimension["scope"] == "ip"


def test_finra_synchronous_budget_uses_documented_byte_reservation():
    seed = settings.PROVIDER_RATE_LIMIT_SEEDS["finra"]
    contract = seed["quota_contract"]
    bytes_dimension = next(item for item in contract["dimensions"] if item["unit"] == "bytes")
    assert bytes_dimension["limit"] == 10_000_000_000
    assert contract["maximum_synchronous_response_bytes"] == 3 * 1024**2
    source = DataSource(
        name="finra",
        config={"usage_tracking": settings.PROVIDER_USAGE_PROFILE_SEEDS["finra"]},
    )
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.SHORT_INTEREST,
        quota_scope=seed["quota_scope"],
        quota_source=seed["quota_source"],
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


@pytest.mark.parametrize("invalid_value", [True, False, 1.5, "10"])
def test_quota_dimension_limits_and_windows_reject_non_strict_positive_integers(invalid_value):
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="api_key",
        quota_source="unit-test",
        quota_contract={
            "dimensions": [
                {
                    "name": "requests_per_minute",
                    "limit": invalid_value,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "api_key",
                    "source": "unit-test",
                }
            ],
            "reset": "rolling",
        },
    )
    assert not policy_has_known_quota(policy)
    assert "quota_contract.dimensions[0].limit" in quota_contract_missing_dimensions(policy)

    policy.quota_contract["dimensions"][0]["limit"] = 10
    policy.quota_contract["dimensions"][0]["window_seconds"] = invalid_value
    assert not policy_has_known_quota(policy)
    assert (
        "quota_contract.dimensions[0].window_seconds"
        in quota_contract_missing_dimensions(policy)
    )


def test_missing_quota_contract_is_operator_actionable():
    policy = ProviderPolicy(data_source_id=1, capability=ProviderCapability.PRICE_HISTORY)
    assert quota_contract_missing_dimensions(policy) == [
        "quota_contract",
        "quota_scope",
        "quota_source",
    ]


def test_complete_dimension_contract_without_policy_provenance_is_non_routable():
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_contract={
            "dimensions": [
                {
                    "name": "requests_per_minute",
                    "limit": 10,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "api_key",
                    "source": "unit-test provider contract",
                }
            ],
            "reset": "rolling",
        },
    )
    assert quota_contract_missing_dimensions(policy) == ["quota_scope", "quota_source"]
    assert not policy_has_known_quota(policy)


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
