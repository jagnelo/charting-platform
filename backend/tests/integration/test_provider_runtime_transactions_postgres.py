from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _async_database_url(raw_url: str) -> str:
    return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1).replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://", 1
    )


@pytest_asyncio.fixture
async def provider_runtime_sessions(request, test_database_url):
    raw_url = test_database_url
    if not raw_url:
        raw_url = request.getfixturevalue("pg_container").get_connection_url()
    schema = f"provider_runtime_tx_{uuid4().hex}"
    import app.models  # noqa: F401
    from app.database import Base

    bootstrap_engine = create_async_engine(_async_database_url(raw_url))
    scoped_engine = None
    created = False
    try:
        async with bootstrap_engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            created = True
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection.execution_options(schema_translate_map={None: schema})
                )
            )
        scoped_engine = create_async_engine(
            _async_database_url(raw_url),
            pool_size=6,
            max_overflow=0,
            connect_args={"server_settings": {"search_path": schema}},
        )
        yield async_sessionmaker(
            scoped_engine,
            autoflush=False,
            expire_on_commit=False,
        )
    finally:
        if scoped_engine is not None:
            await scoped_engine.dispose()
        if created:
            async with bootstrap_engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await bootstrap_engine.dispose()


async def _seed_runtime_rows(sessions, *, source_name: str | None = None):
    from app.models.data_source import DataSource
    from app.models.provider_runtime import (
        ProviderCapability,
        ProviderHealthState,
        ProviderPolicy,
    )

    capability = ProviderCapability.PRICE_HISTORY
    async with sessions() as session:
        source = DataSource(
            name=source_name or f"telemetry-{uuid4().hex[:12]}",
            base_url="https://provider.example.invalid",
            is_active=True,
        )
        session.add(source)
        await session.flush()
        policy = ProviderPolicy(
            data_source_id=source.id,
            capability=capability,
            is_enabled=True,
            quota_scope="reviewed-pool",
            cooldown_seconds=300,
        )
        health = ProviderHealthState(
            data_source_id=source.id,
            capability=capability,
            failure_streak=0,
        )
        session.add_all([policy, health])
        await session.commit()
        return source.id, policy.id, health.id


def _resolved_provider(source, policy, health):
    from app.services.provider_runtime import ResolvedProvider

    return ResolvedProvider(
        provider_name=source.name,
        provider=SimpleNamespace(),
        data_source=source,
        policy=policy,
        health=health,
    )


def _request_log(data_source_id: int):
    from app.models.provider_runtime import ProviderCapability, ProviderRequestLog

    return ProviderRequestLog(
        data_source_id=data_source_id,
        capability=ProviderCapability.PRICE_HISTORY,
        operation="fetch_ohlcv:D1",
        operation_family="fetch_ohlcv",
        requested_at=datetime.now(UTC),
        usage_mode="call_count",
        usage_unit_label="requests",
        usage_units=Decimal("1"),
    )


@pytest.mark.asyncio
async def test_result_telemetry_commits_independently_and_concurrent_callers_progress(
    provider_runtime_sessions,
):
    from app.models.asset_class import AssetClass
    from app.models.data_source import DataSource
    from app.models.provider_runtime import (
        ProviderHealthState,
        ProviderPolicy,
        ProviderRequestLog,
    )
    from app.services.provider_runtime import _record_result

    source_id, policy_id, health_id = await _seed_runtime_rows(provider_runtime_sessions)
    first_recorded = asyncio.Event()
    release_first = asyncio.Event()

    async def caller(*, hold_after_record: bool):
        async with provider_runtime_sessions() as session:
            source = await session.get(DataSource, source_id)
            policy = await session.get(ProviderPolicy, policy_id)
            health = await session.get(ProviderHealthState, health_id)
            session.add(AssetClass(name=f"rollback-{uuid4().hex}", description="caller data"))
            log_row = _request_log(source_id)
            session.add(log_row)
            await session.flush()
            await _record_result(
                session,
                resolved=_resolved_provider(source, policy, health),
                log_row=log_row,
                success=False,
                latency_ms=17,
                response_items=0,
                error=RuntimeError("synthetic provider failure"),
            )
            assert not session.is_modified(policy)
            assert not session.is_modified(health)
            if hold_after_record:
                first_recorded.set()
                await release_first.wait()
            await session.rollback()

    first = asyncio.create_task(caller(hold_after_record=True))
    await asyncio.wait_for(first_recorded.wait(), timeout=5)
    second = asyncio.create_task(caller(hold_after_record=False))
    try:
        await asyncio.wait_for(second, timeout=5)
    finally:
        release_first.set()
        await first

    async with provider_runtime_sessions() as verify:
        policy = await verify.get(ProviderPolicy, policy_id)
        health = await verify.get(ProviderHealthState, health_id)
        assert health.failure_streak == 2
        assert health.last_error_type == "RuntimeError"
        assert policy.learned_weight < 0
        assert await verify.scalar(select(func.count()).select_from(AssetClass)) == 0
        assert await verify.scalar(select(func.count()).select_from(ProviderRequestLog)) == 0


@pytest.mark.asyncio
async def test_failed_provider_fallback_does_not_hold_shared_health_row_during_transport(
    provider_runtime_sessions, monkeypatch
):
    from app.models.data_source import DataSource
    from app.models.provider_runtime import (
        ProviderCapability,
        ProviderHealthState,
        ProviderPolicy,
    )
    from app.services import provider_quota_coordinator, provider_routing, provider_runtime

    sources = [
        DataSource(name=f"fallback-{suffix}-{uuid4().hex[:8]}", is_active=True)
        for suffix in ("first", "second")
    ]
    async with provider_runtime_sessions() as setup:
        setup.add_all(sources)
        await setup.flush()
        policies = [
            ProviderPolicy(
                data_source_id=source.id,
                capability=ProviderCapability.INSTRUMENT_SEARCH,
                is_enabled=True,
                quota_scope="synthetic-test-scope",
            )
            for source in sources
        ]
        health_rows = [
            ProviderHealthState(
                data_source_id=source.id,
                capability=ProviderCapability.INSTRUMENT_SEARCH,
            )
            for source in sources
        ]
        setup.add_all([*policies, *health_rows])
        await setup.commit()
    source_ids = [source.id for source in sources]

    async def resolve(db, _capability, **_kwargs):
        rows = (
            await db.execute(
                select(ProviderPolicy, ProviderHealthState, DataSource)
                .join(
                    ProviderHealthState,
                    (ProviderHealthState.data_source_id == ProviderPolicy.data_source_id)
                    & (ProviderHealthState.capability == ProviderPolicy.capability),
                )
                .join(DataSource, DataSource.id == ProviderPolicy.data_source_id)
                .where(ProviderPolicy.data_source_id.in_(source_ids))
                .order_by(ProviderPolicy.id)
            )
        ).all()
        return [
            provider_runtime.ResolvedProvider(
                provider_name=source.name,
                provider=SimpleNamespace(name=source.name),
                data_source=source,
                policy=policy,
                health=health,
            )
            for policy, health, source in rows
        ]

    async def reserve_contract(*_args, **_kwargs):
        return []

    def settle_contract(*_args, **_kwargs):
        return None

    async def reserve_account_quota(**_kwargs):
        return object()

    async def settle_account_quota(*_args, **_kwargs):
        return None

    monkeypatch.setattr(provider_runtime, "resolve_provider_chain", resolve)
    monkeypatch.setattr(provider_routing, "reserve_provider_contract", reserve_contract)
    monkeypatch.setattr(provider_routing, "settle_provider_contract", settle_contract)
    monkeypatch.setattr(
        provider_quota_coordinator, "reserve_provider_quota_async", reserve_account_quota
    )
    monkeypatch.setattr(provider_runtime, "_settle_coordinator_best_effort", settle_account_quota)

    fallback_started = threading.Event()
    release_fallback = threading.Event()

    def invoke(provider, _symbol):
        if provider.name == sources[0].name:
            if not fallback_started.is_set():
                raise RuntimeError("synthetic first-provider failure")
            return "concurrent success"
        fallback_started.set()
        if not release_fallback.wait(timeout=10):
            raise TimeoutError("test did not release fallback transport")
        return "fallback success"

    async def fallback_call():
        async with provider_runtime_sessions() as session:
            result = await provider_runtime.execute_provider_call(
                session,
                ProviderCapability.INSTRUMENT_SEARCH,
                "search_instruments",
                operation_cost_overrides={source.name: 1 for source in sources},
                invoke=invoke,
                response_items=lambda _value: 1,
            )
            await session.commit()
            return result

    owner_call = asyncio.create_task(fallback_call())
    assert await asyncio.to_thread(fallback_started.wait, 5)
    try:
        async with provider_runtime_sessions() as concurrent_session:
            concurrent_result = await asyncio.wait_for(
                provider_runtime.execute_provider_call(
                    concurrent_session,
                    ProviderCapability.INSTRUMENT_SEARCH,
                    "search_instruments",
                    provider_name=sources[0].name,
                    operation_cost_overrides={sources[0].name: 1},
                    invoke=invoke,
                    response_items=lambda _value: 1,
                ),
                timeout=5,
            )
            assert concurrent_result.provider_name == sources[0].name
            await concurrent_session.commit()
    finally:
        release_fallback.set()
    fallback_result = await owner_call
    assert fallback_result.provider_name == sources[1].name

    async with provider_runtime_sessions() as verify:
        first_health = await verify.scalar(
            select(ProviderHealthState).where(
                ProviderHealthState.data_source_id == source_ids[0],
                ProviderHealthState.capability == ProviderCapability.INSTRUMENT_SEARCH,
            )
        )
        assert first_health.failure_streak == 0


@pytest.mark.asyncio
async def test_first_use_uncommitted_runtime_rows_remain_owned_by_caller(
    provider_runtime_sessions,
):
    from app.models.data_source import DataSource
    from app.models.provider_runtime import (
        ProviderCapability,
        ProviderHealthState,
        ProviderPolicy,
    )
    from app.services.provider_runtime import _record_result

    source_name = f"uncommitted-{uuid4().hex[:12]}"
    async with provider_runtime_sessions() as session:
        source = DataSource(name=source_name, base_url="https://provider.example.invalid")
        session.add(source)
        await session.flush()
        policy = ProviderPolicy(
            data_source_id=source.id,
            capability=ProviderCapability.PRICE_HISTORY,
            is_enabled=True,
        )
        health = ProviderHealthState(
            data_source_id=source.id,
            capability=ProviderCapability.PRICE_HISTORY,
        )
        session.add_all([policy, health])
        await session.flush()
        log_row = _request_log(source.id)
        session.add(log_row)
        await session.flush()
        await _record_result(
            session,
            resolved=_resolved_provider(source, policy, health),
            log_row=log_row,
            success=True,
            latency_ms=8,
            response_items=1,
        )
        assert health.last_success_at is not None
        assert policy.learned_weight > 0
        await session.rollback()

    async with provider_runtime_sessions() as verify:
        assert await verify.scalar(select(DataSource).where(DataSource.name == source_name)) is None


def _transaction_test_quota_contract():
    return {
        "reset": "calendar_day_utc",
        "operation_costs": {"fetch_ohlcv": 1},
        "dimensions": [
            {
                "name": "requests_per_day",
                "limit": 5,
                "window_seconds": 86400,
                "unit": "requests",
                "scope": "api_key",
                "source": "test-fixture:provider-runtime-transaction",
                "reset": "calendar_day_utc",
            }
        ],
    }


def _configure_isolated_test_coordinator(monkeypatch, tmp_path, provider_name, policy, now):
    from app.services import provider_quota_coordinator

    ledger_url = f"sqlite:///{tmp_path / 'provider-quota-test.sqlite3'}"
    monkeypatch.setattr(provider_quota_coordinator, "_engine_url", lambda: ledger_url)
    engine = provider_quota_coordinator._engine_for(ledger_url)
    provider_quota_coordinator.reconcile_provider_quota_baseline(
        provider_name=provider_name,
        capability="price_history",
        policy=policy,
        dimension_name="requests_per_day",
        used_units=0,
        observed_at=now,
        evidence_reference="test-fixture:provider-runtime-transaction:2026-11-08",
        source="operator_owner_attestation",
        now=now,
    )
    baseline = provider_quota_coordinator.provider_quota_baseline_status(
        provider_name=provider_name,
        capability="price_history",
        policy=policy,
        dimension_name="requests_per_day",
        now=now,
    )
    assert baseline["status"] == "verified", baseline
    return engine


@pytest.mark.asyncio
async def test_execute_provider_call_commits_quota_before_slow_mock_transport(
    provider_runtime_sessions, tmp_path, monkeypatch
):
    """A slow call must not retain shared PostgreSQL quota-window row locks."""

    from app.config import settings
    from app.models.asset_class import AssetClass
    from app.models.data_source import DataSource
    from app.models.market_data_foundation import ProviderQuotaWindow
    from app.models.provider_runtime import (
        ProviderCapability,
        ProviderHealthState,
        ProviderPolicy,
        ProviderRequestLog,
    )
    from app.providers.telemetry import observe_response
    from app.services import provider_runtime
    from app.services.provider_quota_coordinator import _reservations, _windows

    monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", False)
    source = DataSource(
        name=f"quota-tx-{uuid4().hex[:12]}",
        base_url="https://provider.example.invalid",
        is_active=True,
        config={"usage_tracking": {"operation_costs": {"fetch_ohlcv": 1}}},
    )
    policy = ProviderPolicy(
        capability=ProviderCapability.PRICE_HISTORY,
        is_enabled=True,
        quota_scope="fixture-account",
        quota_source="test-fixture:provider-runtime-transaction",
        quota_verified_at=datetime.now(UTC),
        max_concurrency=2,
        quota_contract=_transaction_test_quota_contract(),
    )
    health = ProviderHealthState(capability=ProviderCapability.PRICE_HISTORY)
    async with provider_runtime_sessions() as setup:
        setup.add(source)
        await setup.flush()
        policy.data_source_id = source.id
        health.data_source_id = source.id
        setup.add_all([policy, health])
        await setup.commit()
        source_id = source.id

    now = datetime.now(UTC)
    coordinator_engine = _configure_isolated_test_coordinator(
        monkeypatch, tmp_path, source.name, policy, now
    )

    async def resolve_for_session(db, _capability, **_kwargs):
        local_source = await db.get(DataSource, source_id)
        local_policy = (
            await db.execute(
                select(ProviderPolicy).where(ProviderPolicy.data_source_id == source_id)
            )
        ).scalar_one()
        local_health = (
            await db.execute(
                select(ProviderHealthState).where(
                    ProviderHealthState.data_source_id == source_id,
                    ProviderHealthState.capability == ProviderCapability.PRICE_HISTORY,
                )
            )
        ).scalar_one()
        return [_resolved_provider(local_source, local_policy, local_health)]

    monkeypatch.setattr(provider_runtime, "resolve_provider_chain", resolve_for_session)
    original_reserve = provider_runtime._reserve_provider_contract_for_call

    async def require_application_reservation(*args, **kwargs):
        reservation = await original_reserve(*args, **kwargs)
        assert reservation is not None, "application quota-window reservation was denied"
        return reservation

    monkeypatch.setattr(
        provider_runtime, "_reserve_provider_contract_for_call", require_application_reservation
    )
    slow_started = threading.Event()
    release_slow = threading.Event()
    slow_finished = threading.Event()

    def invoke(_provider, symbol):
        observe_response(SimpleNamespace(content=b"mocked-provider-response", headers={}))
        if symbol == "SLOW":
            slow_started.set()
            if not release_slow.wait(timeout=10):
                raise TimeoutError("test did not release slow mocked transport")
            slow_finished.set()
        return [symbol]

    async def call(symbol):
        async with provider_runtime_sessions() as session:
            session.add(AssetClass(name=f"rolled-back-{uuid4().hex[:12]}"))
            result = await provider_runtime.execute_provider_call(
                session,
                ProviderCapability.PRICE_HISTORY,
                "fetch_ohlcv:D1",
                provider_symbol=symbol,
                usage_identity=symbol,
                invoke=invoke,
                response_items=len,
                seed_runtime=False,
            )
            assert result.result == [symbol]
            await session.rollback()

    slow_call = asyncio.create_task(call("SLOW"))
    try:
        assert await asyncio.wait_for(asyncio.to_thread(slow_started.wait, 5), timeout=6)
        # This is a full admitted execute_provider_call using the same real
        # PostgreSQL quota window while the first mocked transport is blocked.
        # It must finish without waiting for the first caller transaction.
        await asyncio.wait_for(call("FAST"), timeout=5)
        assert not slow_finished.is_set()
    finally:
        release_slow.set()
        await asyncio.wait_for(slow_call, timeout=10)

    async with provider_runtime_sessions() as verify:
        window = await verify.scalar(select(ProviderQuotaWindow))
        assert window is not None
        assert window.reserved_units == 0
        assert window.consumed_units == 2
        assert await verify.scalar(select(func.count()).select_from(AssetClass)) == 0
        assert await verify.scalar(select(func.count()).select_from(ProviderRequestLog)) == 0

    with coordinator_engine.connect() as connection:
        ledger_windows = connection.execute(select(_windows)).mappings().all()
        ledger_reservations = connection.execute(select(_reservations)).mappings().all()
    assert len(ledger_windows) == 1
    assert ledger_windows[0]["reserved_units"] == 0
    assert ledger_windows[0]["consumed_units"] == 2
    assert len(ledger_reservations) == 2
    assert {row["state"] for row in ledger_reservations} == {"settled"}
    coordinator_engine.dispose()


@pytest.mark.asyncio
async def test_execute_provider_call_first_use_keeps_uncommitted_source_in_caller_transaction(
    provider_runtime_sessions, tmp_path, monkeypatch
):
    """The short-session path falls back when first-use seed rows are uncommitted."""

    from app.config import settings
    from app.models.data_source import DataSource
    from app.models.market_data_foundation import ProviderQuotaWindow
    from app.models.provider_runtime import (
        ProviderCapability,
        ProviderHealthState,
        ProviderPolicy,
        ProviderRequestLog,
    )
    from app.providers.telemetry import observe_response
    from app.services import provider_runtime
    from app.services.provider_quota_coordinator import _reservations

    monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", False)
    source_name = f"first-use-{uuid4().hex[:10]}"
    source = DataSource(
        name=source_name,
        base_url="https://provider.example.invalid",
        is_active=True,
        config={"usage_tracking": {"operation_costs": {"fetch_ohlcv": 1}}},
    )
    policy = ProviderPolicy(
        capability=ProviderCapability.PRICE_HISTORY,
        is_enabled=True,
        quota_scope="fixture-first-use-account",
        quota_source="test-fixture:provider-runtime-transaction",
        quota_verified_at=datetime.now(UTC),
        max_concurrency=1,
        quota_contract=_transaction_test_quota_contract(),
    )
    health = ProviderHealthState(capability=ProviderCapability.PRICE_HISTORY)
    async with provider_runtime_sessions() as session:
        session.add(source)
        await session.flush()
        policy.data_source_id = source.id
        health.data_source_id = source.id
        session.add_all([policy, health])
        await session.flush()
        resolved = _resolved_provider(source, policy, health)

        now = datetime.now(UTC)
        coordinator_engine = _configure_isolated_test_coordinator(
            monkeypatch, tmp_path, source.name, policy, now
        )

        async def resolve_uncommitted(_db, _capability, **_kwargs):
            return [resolved]

        monkeypatch.setattr(provider_runtime, "resolve_provider_chain", resolve_uncommitted)

        def invoke(_provider, _symbol):
            observe_response(SimpleNamespace(content=b"first-use-response", headers={}))
            return ["OK"]

        result = await provider_runtime.execute_provider_call(
            session,
            ProviderCapability.PRICE_HISTORY,
            "fetch_ohlcv:D1",
            provider_symbol="FIRST",
            usage_identity="FIRST",
            invoke=invoke,
            response_items=len,
            seed_runtime=False,
        )
        assert result.result == ["OK"]
        assert await session.scalar(select(ProviderQuotaWindow)) is not None
        assert await session.scalar(select(ProviderRequestLog)) is not None
        await session.rollback()

    async with provider_runtime_sessions() as verify:
        assert await verify.scalar(select(DataSource).where(DataSource.name == source_name)) is None
        assert await verify.scalar(select(ProviderQuotaWindow)) is None
        assert await verify.scalar(select(ProviderRequestLog)) is None
    with coordinator_engine.connect() as connection:
        ledger_reservations = connection.execute(select(_reservations)).mappings().all()
    assert len(ledger_reservations) == 1
    assert ledger_reservations[0]["state"] == "settled"
    coordinator_engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("known_reset", [False, True])
async def test_capacity_hold_updates_same_caller_resolver_without_dirtying_stale_rows(
    provider_runtime_sessions, monkeypatch, known_reset
):
    from app.config import settings
    from app.models.provider_runtime import (
        ProviderCapability,
        ProviderHealthState,
        ProviderPolicy,
    )
    from app.providers.errors import ProviderRateLimitError
    from app.services.provider_runtime import (
        _apply_provider_capacity_hold,
        resolve_provider_chain,
        seed_provider_runtime,
    )

    monkeypatch.setattr(settings, "ALPACA_API_KEY", "offline-test-key")
    monkeypatch.setattr(settings, "ALPACA_SECRET_KEY", "offline-test-secret")
    monkeypatch.setattr(settings, "PROVIDER_ROUTING_ENABLED", True)
    monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", False)
    async with provider_runtime_sessions() as session:
        await seed_provider_runtime(session)
        chain = await resolve_provider_chain(
            session,
            ProviderCapability.ACCOUNT_USAGE,
            operation="fetch_account_usage",
        )
        target = next(item for item in chain if item.provider_name == "alpaca")
        await session.commit()

        retry_at = datetime(2099, 1, 1, tzinfo=UTC) if known_reset else None
        await _apply_provider_capacity_hold(
            session,
            data_source_id=target.data_source.id,
            policy=target.policy,
            error=ProviderRateLimitError(
                "alpaca",
                "synthetic account usage hold",
                retry_at=retry_at,
                scope=target.policy.quota_scope,
            ),
        )
        assert not session.is_modified(target.policy)
        assert not session.is_modified(target.health)
        if known_reset:
            assert target.health.circuit_open_until == retry_at
            assert target.policy.is_enabled is True
        else:
            assert target.policy.is_enabled is False

        repeated_chain = await resolve_provider_chain(
            session,
            ProviderCapability.ACCOUNT_USAGE,
            operation="fetch_account_usage",
        )
        assert all(item.provider_name != "alpaca" for item in repeated_chain)

        scoped_policies = list(
            (
                await session.execute(
                    select(ProviderPolicy).where(
                        ProviderPolicy.data_source_id == target.data_source.id,
                        ProviderPolicy.quota_scope == target.policy.quota_scope,
                    )
                )
            ).scalars()
        )
        assert scoped_policies
        if known_reset:
            assert all(item.is_enabled for item in scoped_policies)
            scoped_health = list(
                (
                    await session.execute(
                        select(ProviderHealthState)
                        .join(
                            ProviderPolicy,
                            (ProviderPolicy.data_source_id == ProviderHealthState.data_source_id)
                            & (ProviderPolicy.capability == ProviderHealthState.capability),
                        )
                        .where(
                            ProviderPolicy.data_source_id == target.data_source.id,
                            ProviderPolicy.quota_scope == target.policy.quota_scope,
                        )
                    )
                ).scalars()
            )
            assert scoped_health
            assert all(item.circuit_open_until == retry_at for item in scoped_health)
        else:
            assert all(not item.is_enabled for item in scoped_policies)
