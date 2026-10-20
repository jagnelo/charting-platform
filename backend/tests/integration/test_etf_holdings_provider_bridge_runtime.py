"""Real shared Provider admission around offline ETF HTTPX attempts.

This module intentionally runs against TEST_DATABASE_URL (or the normal
integration Postgres fixture) and uses only HTTPX MockTransport. It never
contacts an issuer or provider.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.asset_class import AssetClass, InstrumentType
from app.models.data_source import DataSource
from app.models.instrument import Instrument
from app.models.market_data_foundation import ProviderQuotaWindow
from app.models.provider_recurring_cost import (
    ProviderRecurringCostBudget,
    ProviderRecurringCostCommitment,
)
from app.models.provider_runtime import (
    ProviderCapability,
    ProviderEntitlement,
    ProviderHealthState,
    ProviderPolicy,
    ProviderRequestLog,
)
from app.services import etf_holdings_provider_bridge as bridge
from app.services import provider_quota_coordinator as quota_coordinator
from app.services.etf_holdings_adapters import httpx as adapter_httpx
from app.services.etf_holdings_provider_bridge import (
    ETFHoldingsRouteHeldError,
    bind_etf_holdings_request_context,
)
from app.services.provider_quota_coordinator import ProviderQuotaAdmissionError
from app.services.provider_runtime import ProviderNoDataError


@pytest_asyncio.fixture
async def provider_db(db_engine):
    """Open a real async PostgreSQL session over the integration fixture DB."""

    async_url = db_engine.url.set(drivername="postgresql+asyncpg")
    engine = create_async_engine(async_url, pool_pre_ping=True)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


class _TransportRunner:
    """Run one real HTTPX attempt in the Provider worker's own event loop."""

    def __init__(self):
        self.transport = None
        self.calls = []

    def factory(self):
        return httpx.MockTransport(self.handle)

    def handle(self, request):
        self.calls.append((request.method, str(request.url)))
        if request.url.path == "/start":
            return httpx.Response(
                302,
                headers={"location": "/holdings.csv"},
                request=request,
            )
        return httpx.Response(
            200,
            text="Symbol,Weight\nAAA,1.0\n",
            headers={"content-type": "text/csv"},
            request=request,
        )


async def _seed_reviewed_fixture(session: AsyncSession, *, limit: int, monkeypatch):
    suffix = uuid4().hex[:10]
    provider_name = f"etf-fixture-{suffix}"
    account_scope = f"etf-offline-test-account-{suffix}"
    quota_scope = "api_key"
    operation = "fetch_etf_holdings_latest"
    now = datetime.now(UTC)
    dimension_source = "test-fixture:etf:synthetic-quota-contract"
    review_account_key = f"{provider_name}:{quota_scope}"
    configured_scopes = dict(settings.PROVIDER_QUOTA_ACCOUNT_SCOPES or {})
    configured_scopes[review_account_key] = account_scope
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_ACCOUNT_SCOPES", configured_scopes)

    asset_class = AssetClass(name=f"ETF-fixture-{suffix}", description="isolated integration")
    session.add(asset_class)
    await session.flush()
    instrument_type = InstrumentType(
        asset_class_id=asset_class.id,
        name="ETF",
        description="synthetic ETF bridge fixture",
    )
    session.add(instrument_type)
    await session.flush()
    instrument = Instrument(
        instrument_type_id=instrument_type.id,
        symbol=f"ZZ{suffix[:4].upper()}",
        name="Offline ETF bridge fixture",
        currency="USD",
        is_active=True,
    )
    session.add(instrument)
    await session.flush()

    source = DataSource(
        name=provider_name,
        is_active=True,
        config={
            "usage_tracking": {"operation_costs": {operation: 1}},
            "etf_holdings_review": {
                "https_hosts": ["publisher.example"],
                "account_scope": account_scope,
                "operations": {
                    operation: {
                        "evidence_source": "test-fixture:etf:offline-mocktransport",
                        "evidence_version": "synthetic-v1",
                        "reviewed_at": now.date().isoformat(),
                    }
                },
            },
        },
        supported_capabilities=[ProviderCapability.ETF_HOLDINGS.value],
    )
    session.add(source)
    await session.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.ETF_HOLDINGS,
        is_enabled=True,
        max_concurrency=2,
        quota_scope=quota_scope,
        quota_source=dimension_source,
        quota_verified_at=now,
        quota_contract={
            "reset": "rolling",
            "operation_costs": {operation: 1},
            "dimensions": [
                {
                    "name": "requests_per_minute",
                    "limit": limit,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": quota_scope,
                    "source": dimension_source,
                    "reset": "rolling",
                }
            ],
        },
    )
    entitlement = ProviderEntitlement(
        data_source_id=source.id,
        capability=ProviderCapability.ETF_HOLDINGS,
        configured_plan="reviewed-synthetic-free-fixture",
        is_free=True,
        authentication_required=False,
        usage_terms="Synthetic fixture only; not a publisher entitlement",
        redistribution_allowed=False,
        quota_policy={},
        enabled_environments=[settings.APP_ENV],
        review_due_at=now + timedelta(days=1),
        live_probe_status="passed",
    )
    health = ProviderHealthState(
        data_source_id=source.id,
        capability=ProviderCapability.ETF_HOLDINGS,
        ewma_latency_ms=Decimal("0"),
        ewma_success_rate=Decimal("1"),
        ewma_completeness=Decimal("1"),
        ewma_freshness=Decimal("1"),
        ewma_consistency=Decimal("1"),
        observed_score=Decimal("0"),
    )
    session.add_all([policy, entitlement, health])

    budget = await session.get(ProviderRecurringCostBudget, 1)
    if budget is None:
        session.add(
            ProviderRecurringCostBudget(
                id=1,
                currency="USD",
                monthly_ceiling=Decimal("0"),
                evidence_source="test fixture only",
                evidence_version="synthetic-v1",
                reviewed_at=now,
                revision=1,
            )
        )
    session.add(
        ProviderRecurringCostCommitment(
            data_source_id=source.id,
            environment=settings.APP_ENV.strip().lower(),
            billing_account_scope_digest=hashlib.sha256(
                account_scope.strip().encode("utf-8")
            ).hexdigest(),
            configured_plan="synthetic-free-fixture",
            state="active",
            amount=Decimal("0"),
            currency="USD",
            interval_unit="month",
            interval_count=1,
            monthly_equivalent=Decimal("0"),
            post_trial_amount=None,
            effective_at=now,
            ends_at=None,
            evidence_source="test fixture only",
            evidence_version="synthetic-v1",
            evidence_observed_at=now,
            revision=1,
        )
    )
    await session.flush()
    return SimpleNamespace(
        provider_name=provider_name,
        account_scope=account_scope,
        instrument_id=instrument.id,
        source_id=source.id,
        policy=policy,
        operation=operation,
        adapter=SimpleNamespace(
            source_provider=provider_name,
            fetch_latest=lambda *_args, **_kwargs: None,
            fetch_for_date=lambda *_args, **_kwargs: None,
        ),
    )


def _use_mocktransport(monkeypatch, runner: _TransportRunner):
    original_factory = bridge._make_loop_local_httpx_attempt

    def factory(**kwargs):
        return original_factory(**kwargs, transport_factory=runner.factory)

    monkeypatch.setattr(bridge, "_make_loop_local_httpx_attempt", factory)


def _assert_second_bucket_contract(windows, *, consumed_units: int, reserved_units: int):
    """Assert rolling rows are second buckets, not per-request records."""

    assert windows
    starts = []
    for row in windows:
        started_at = row["window_started_at"] if isinstance(row, dict) else row.window_started_at
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at)
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=UTC)
        starts.append(started_at.astimezone(UTC))
        assert started_at.microsecond == 0
        window_seconds = row["window_seconds"] if isinstance(row, dict) else row.window_seconds
        assert window_seconds == 60
    assert len(starts) == len(set(starts))
    assert len(windows) <= consumed_units + reserved_units
    actual_consumed = sum(
        row["consumed_units"] if isinstance(row, dict) else row.consumed_units for row in windows
    )
    actual_reserved = sum(
        row["reserved_units"] if isinstance(row, dict) else row.reserved_units for row in windows
    )
    assert actual_reserved == reserved_units
    assert actual_consumed == consumed_units


async def _fetch_two_hop_fixture(session, case, runner):
    with bind_etf_holdings_request_context(
        db=session,
        adapter=case.adapter,
        instrument_id=case.instrument_id,
        provider_symbol="AAA",
        operation=case.operation,
    ):
        async with adapter_httpx.AsyncClient(follow_redirects=True, timeout=2) as client:
            return await client.get("https://publisher.example/start")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_each_redirect_hop_uses_real_shared_admission_and_durable_settlement(
    db_engine, provider_db, monkeypatch, redis_url
):
    """A redirect is two real Provider calls, ledger rows, and settlements."""

    import redis

    # Redis is part of the assigned isolated slot and must be live, but current
    # Provider admission is SQL-backed; do not imply Redis owns quota state.
    redis_client = redis.Redis.from_url(redis_url, socket_timeout=1)
    assert redis_client.ping()
    redis_client.close()

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        db_engine.url.render_as_string(hide_password=False),
    )
    async with provider_db() as session:
        async with session.begin():
            case = await _seed_reviewed_fixture(session, limit=3, monkeypatch=monkeypatch)
            runner = _TransportRunner()
            _use_mocktransport(monkeypatch, runner)
            result = await _fetch_two_hop_fixture(session, case, runner)

            assert result.status_code == 200
            assert len(result.history) == 1
            assert runner.calls == [
                ("GET", "https://publisher.example/start"),
                ("GET", "https://publisher.example/holdings.csv"),
            ]
            logs = list(
                (
                    await session.scalars(
                        select(ProviderRequestLog)
                        .where(
                            ProviderRequestLog.data_source_id == case.source_id,
                            ProviderRequestLog.operation == case.operation,
                        )
                        .order_by(ProviderRequestLog.id)
                    )
                ).all()
            )
            assert len(logs) == 2
            assert all(row.success and row.http_requests == 1 for row in logs)
            assert all(row.completed_at is not None for row in logs)
            assert all(row.settled_usage_units == Decimal("1.0000") for row in logs)
            windows = list(
                (
                    await session.scalars(
                        select(ProviderQuotaWindow).where(
                            ProviderQuotaWindow.data_source_id == case.source_id,
                            ProviderQuotaWindow.dimension == "requests_per_minute",
                        )
                    )
                ).all()
            )
            _assert_second_bucket_contract(windows, consumed_units=2, reserved_units=0)

            # Re-open the independently committed shared coordinator engine to
            # verify durable per-hop settlement after a pool/connection restart.
            quota_engine = quota_coordinator._engine_for(quota_coordinator._engine_url())
            quota_engine.dispose()
            summary = quota_coordinator.provider_quota_coordinator_summary(
                provider_name=case.provider_name
            )
            with quota_engine.connect() as connection:
                provider_rows = (
                    connection.execute(
                        select(quota_coordinator._reservations).where(
                            quota_coordinator._reservations.c.provider_name == case.provider_name
                        )
                    )
                    .mappings()
                    .all()
                )
            assert len(provider_rows) == 2
            assert all(row["state"] == "settled" for row in provider_rows)
            assert all(row["settled_at"] is not None for row in provider_rows)
            assert all(row["reserved_units"] == 1 for row in provider_rows)
            matching_windows = [
                row
                for row in summary["windows"]
                if row["account_scope"] == case.account_scope
                and row["dimension"] == "requests_per_minute"
            ]
            _assert_second_bucket_contract(matching_windows, consumed_units=2, reserved_units=0)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unknown_held_and_exhausted_routes_never_start_transport(
    db_engine, provider_db, monkeypatch
):
    """Unknown/held routes and durable quota exhaustion are pre-transport."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        db_engine.url.render_as_string(hide_password=False),
    )
    async with provider_db() as session:
        async with session.begin():
            case = await _seed_reviewed_fixture(session, limit=2, monkeypatch=monkeypatch)
            runner = _TransportRunner()
            _use_mocktransport(monkeypatch, runner)

            with pytest.raises(ETFHoldingsRouteHeldError, match="not in the reviewed contract"):
                with bind_etf_holdings_request_context(
                    db=session,
                    adapter=case.adapter,
                    instrument_id=case.instrument_id,
                    provider_symbol="AAA",
                    operation="unknown_operation",
                ):
                    await adapter_httpx.AsyncClient().get("https://publisher.example/start")
            assert runner.calls == []

            # Provider's operation hold is exercised through the production
            # resolver. It must stop before request-log/reservation/transport.
            original_holds = dict(settings.PROVIDER_CHECKPOINT_OPERATION_HOLDS or {})
            test_holds = dict(original_holds)
            test_holds[case.provider_name] = {case.operation: "synthetic test hold"}
            monkeypatch.setattr(settings, "PROVIDER_CHECKPOINT_OPERATION_HOLDS", test_holds)
            with bind_etf_holdings_request_context(
                db=session,
                adapter=case.adapter,
                instrument_id=case.instrument_id,
                provider_symbol="AAA",
                operation=case.operation,
            ):
                async with adapter_httpx.AsyncClient(timeout=2) as client:
                    with pytest.raises(
                        ProviderNoDataError, match="No currently-supported providers"
                    ):
                        await client.get("https://publisher.example/start")
            monkeypatch.setattr(settings, "PROVIDER_CHECKPOINT_OPERATION_HOLDS", original_holds)
            assert runner.calls == []

            # Synthetic prior account usage is a local fixture fact, not a
            # publisher quota claim. It leaves one shared-coordinator unit
            # while the application runtime still has room for both calls.
            now = datetime.now(UTC)
            quota_coordinator.reconcile_provider_quota_baseline(
                provider_name=case.provider_name,
                capability=ProviderCapability.ETF_HOLDINGS.value,
                policy=case.policy,
                dimension_name="requests_per_minute",
                used_units=1,
                observed_at=now,
                evidence_reference="test-fixture:etf:synthetic-prior-usage",
                now=now,
            )

            # One admitted physical attempt consumes the last shared unit. The
            # next call must be denied by the actual durable coordinator before
            # transport even though its ProviderQuotaWindow still has capacity.
            with bind_etf_holdings_request_context(
                db=session,
                adapter=case.adapter,
                instrument_id=case.instrument_id,
                provider_symbol="AAA",
                operation=case.operation,
            ):
                async with adapter_httpx.AsyncClient(timeout=2) as client:
                    accepted = await client.get("https://publisher.example/holdings.csv")
                    assert accepted.status_code == 200
                    with pytest.raises(ProviderQuotaAdmissionError, match="quota admission denied"):
                        await client.get("https://publisher.example/holdings.csv")

            assert runner.calls == [("GET", "https://publisher.example/holdings.csv")]
            logs = list(
                (
                    await session.scalars(
                        select(ProviderRequestLog).where(
                            ProviderRequestLog.data_source_id == case.source_id
                        )
                    )
                ).all()
            )
            assert len(logs) == 1
            assert logs[0].success and logs[0].http_requests == 1
            assert logs[0].settled_usage_units == Decimal("1.0000")
            app_window = await session.scalar(
                select(ProviderQuotaWindow).where(
                    ProviderQuotaWindow.data_source_id == case.source_id,
                    ProviderQuotaWindow.dimension == "requests_per_minute",
                )
            )
            assert app_window is not None
            assert app_window.reserved_units == 0
            assert app_window.consumed_units == 1
