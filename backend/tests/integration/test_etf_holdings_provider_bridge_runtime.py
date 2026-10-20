"""Real shared Provider admission around offline ETF HTTPX attempts.

This module intentionally runs against TEST_DATABASE_URL (or the normal
integration Postgres fixture) and uses only HTTPX MockTransport. It never
contacts an issuer or provider.
"""

from __future__ import annotations

import asyncio
import hashlib
import threading
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.asset_class import AssetClass, InstrumentType
from app.models.data_source import DataSource
from app.models.etf_holdings import (
    ETFHoldingsAdapterState,
    ETFHoldingsRawArtifact,
    ETFHoldingsSnapshot,
    ETFProfile,
)
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
from app.services import etf_holdings_refresh as refresh
from app.services import provider_quota_coordinator as quota_coordinator
from app.services.etf_holdings import _hash_payload
from app.services.etf_holdings_adapters import (
    CiFinancialHoldingsAdapter,
    IssuerCsvAdapterConfig,
    IssuerCsvHoldingsAdapter,
)
from app.services.etf_holdings_adapters import httpx as adapter_httpx
from app.services.etf_holdings_capability import evaluate_capability
from app.services.etf_holdings_provider_bridge import (
    ETFHoldingsRouteHeldError,
    LoopLocalHTTPXAttempt,
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
        self.status_code = 200
        self.body = "Symbol,Weight\nAAA,1.0\n"
        self.started = None
        self.release = None
        self.raise_timeout = False
        self.redirect_location = "https://publisher.example/holdings.csv"

    def factory(self):
        return httpx.MockTransport(self.handle)

    def handle(self, request):
        self.calls.append((request.method, str(request.url)))
        if self.raise_timeout:
            raise httpx.ReadTimeout("synthetic MockTransport timeout", request=request)
        if self.started is not None:
            self.started.set()
            if not self.release.wait(3):
                raise httpx.ReadTimeout(
                    "bounded fixture transport release timed out", request=request
                )
        return httpx.Response(
            302 if request.url.path == "/start" else self.status_code,
            text=self.body,
            headers=(
                {"location": self.redirect_location}
                if request.url.path == "/start"
                else {"content-type": "text/csv"}
            ),
            request=request,
        )


async def _seed_reviewed_fixture(
    session: AsyncSession,
    *,
    limit: int,
    monkeypatch,
    reviewed_hosts: list[str] | None = None,
    operation: str = "fetch_etf_holdings_latest",
):
    suffix = uuid4().hex[:10]
    provider_name = f"etf-fixture-{suffix}"
    account_scope = f"etf-offline-test-account-{suffix}"
    quota_scope = "api_key"
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
                "https_hosts": reviewed_hosts
                or ["publisher.example", "cdn.publisher.example", "cisbh.com"],
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
        instrument_symbol=instrument.symbol,
        source_id=source.id,
        policy=policy,
        operation=operation,
        adapter=SimpleNamespace(
            source_provider=provider_name,
            adapter_key="synthetic_csv_fixture",
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


async def _fetch_two_hop_fixture(session, case, runner, profile_id):
    with bind_etf_holdings_request_context(
        db=session,
        adapter=case.adapter,
        profile_id=profile_id,
        instrument_id=case.instrument_id,
        provider_symbol=case.instrument_symbol,
        operation=case.operation,
    ):
        async with adapter_httpx.AsyncClient(follow_redirects=True, timeout=2) as client:
            return await client.get("https://publisher.example/start")


async def _seed_real_adapter_profile(
    session,
    case,
    monkeypatch,
    *,
    composition_date=None,
    route_url=None,
    dated_route_template=None,
):
    instrument = await session.get(Instrument, case.instrument_id)
    assert instrument is not None
    today = datetime.now(UTC).date()
    profile = ETFProfile(
        instrument_id=instrument.id,
        instrument=instrument,
        issuer="Synthetic test fixture publisher",
        adapter_key="synthetic_csv_fixture",
        adapter_status="pending",
        provider_aliases={
            "holdings_url": route_url or "https://publisher.example/holdings.csv",
            **(
                {"dated_holdings_url_template": dated_route_template}
                if dated_route_template
                else {}
            ),
            "expected_etf_symbol": instrument.symbol,
            "holdings_source_provider": case.provider_name,
            "holdings_completeness_status": "complete",
            "holdings_composition_date": (composition_date or today).isoformat(),
            "expected_cadence": "daily",
        },
    )
    adapter = IssuerCsvHoldingsAdapter(
        IssuerCsvAdapterConfig(
            adapter_key="synthetic_csv_fixture",
            source_provider=case.provider_name,
            source_access="synthetic_test_fixture_only",
            expected_cadence="daily",
            supports_sec_filing_fallback=False,
            terms_note="Synthetic fixture only; not a publisher entitlement.",
        )
    )
    session.add(profile)
    await session.flush()
    monkeypatch.setattr(refresh, "get_holdings_adapter", lambda _key: adapter)
    return profile, adapter


async def _create_committed_fixture(
    provider_db,
    monkeypatch,
    *,
    limit,
    with_profile=False,
    route_url=None,
    reviewed_hosts=None,
    operation="fetch_etf_holdings_latest",
    dated_route_template=None,
):
    """Commit only synthetic setup rows before isolated Provider attempts."""
    async with provider_db() as session:
        async with session.begin():
            case = await _seed_reviewed_fixture(
                session,
                limit=limit,
                monkeypatch=monkeypatch,
                reviewed_hosts=reviewed_hosts,
                operation=operation,
            )
            profile = None
            if with_profile:
                profile, _adapter = await _seed_real_adapter_profile(
                    session,
                    case,
                    monkeypatch,
                    route_url=route_url,
                    dated_route_template=dated_route_template,
                )
            profile_id = profile.id if profile is not None else None
    return case, profile_id


async def _load_profile(session: AsyncSession, profile_id: int) -> ETFProfile:
    profile = await session.scalar(
        select(ETFProfile)
        .options(selectinload(ETFProfile.instrument))
        .where(ETFProfile.id == profile_id)
    )
    assert profile is not None
    return profile


async def _assert_one_settled_attempt(
    session,
    case,
    *,
    expected_success: bool,
    expected_http_requests: int = 1,
    expected_settled_usage: Decimal = Decimal("1.0000"),
    expected_reservation_state: str = "settled",
):
    logs = list(
        (
            await session.scalars(
                select(ProviderRequestLog).where(
                    ProviderRequestLog.data_source_id == case.source_id,
                    ProviderRequestLog.operation == case.operation,
                )
            )
        ).all()
    )
    assert len(logs) == 1
    row = logs[0]
    assert row.success is expected_success
    assert row.http_requests == expected_http_requests
    assert row.completed_at is not None
    assert row.settled_usage_units == expected_settled_usage
    quota_engine = quota_coordinator._engine_for(quota_coordinator._engine_url())
    with quota_engine.connect() as connection:
        reservations = (
            connection.execute(
                select(quota_coordinator._reservations).where(
                    quota_coordinator._reservations.c.provider_name == case.provider_name
                )
            )
            .mappings()
            .all()
        )
    assert len(reservations) == 1
    assert reservations[0]["state"] == expected_reservation_state
    if expected_reservation_state == "settled":
        assert reservations[0]["settled_at"] is not None
    assert reservations[0]["reserved_units"] == 1
    return row


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
    case, profile_id = await _create_committed_fixture(
        provider_db,
        monkeypatch,
        limit=3,
        with_profile=True,
        route_url="https://publisher.example/start",
    )
    async with provider_db() as session:
        async with session.begin():
            runner = _TransportRunner()
            _use_mocktransport(monkeypatch, runner)
            result = await _fetch_two_hop_fixture(session, case, runner, profile_id)

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
async def test_real_adapter_params_are_admitted_as_effective_url_and_not_replayed_on_redirect(
    db_engine, provider_db, monkeypatch
):
    """Real adapter query params and redirects retain exact per-log URL binding."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        db_engine.url.render_as_string(hide_password=False),
    )
    initial_url = "https://publisher.example/start?seed=base"
    redirect_url = "https://cdn.publisher.example/holdings.csv?download=latest"
    client_params = {"account": "client-default", "api_key": "synthetic-query-secret"}
    url_builder = httpx.AsyncClient(params=client_params)
    try:
        actual_initial_url = str(
            url_builder.build_request(
                "GET", initial_url, params={"fund": CiFinancialHoldingsAdapter.FUND_ID}
            ).url
        )
    finally:
        await url_builder.aclose()
    case, profile_id = await _create_committed_fixture(
        provider_db,
        monkeypatch,
        limit=3,
        with_profile=True,
        route_url=initial_url,
        reviewed_hosts=["publisher.example", "cdn.publisher.example"],
    )
    monkeypatch.setattr(CiFinancialHoldingsAdapter, "HOLDINGS_ENDPOINT", initial_url)
    runner = _TransportRunner()
    runner.redirect_location = redirect_url
    _use_mocktransport(monkeypatch, runner)
    original_client = adapter_httpx.AsyncClient

    def client_with_reviewed_defaults(**kwargs):
        kwargs.setdefault("params", client_params)
        return original_client(**kwargs)

    monkeypatch.setattr(adapter_httpx, "AsyncClient", client_with_reviewed_defaults)
    async with provider_db() as session:
        async with session.begin():
            with bind_etf_holdings_request_context(
                db=session,
                adapter=case.adapter,
                profile_id=profile_id,
                instrument_id=case.instrument_id,
                provider_symbol=case.instrument_symbol,
                operation=case.operation,
            ) as binding:
                async with adapter_httpx.AsyncClient(timeout=2) as client:
                    response = await CiFinancialHoldingsAdapter._get_holdings_endpoint_with_retry(
                        client, product_page_url="https://publisher.example/product"
                    )
            assert response.status_code == 200
            assert [url for _method, url in runner.calls] == [actual_initial_url, redirect_url]
            bound_urls = [
                bridge._canonical_request_url(binding.request_urls_by_log_id[request_id])
                for request_id in binding.request_log_ids
            ]
            assert bound_urls == [
                bridge._canonical_request_url(actual_initial_url),
                bridge._canonical_request_url(redirect_url),
            ]
            request_logs = list(
                (
                    await session.scalars(
                        select(ProviderRequestLog)
                        .where(ProviderRequestLog.id.in_(binding.request_log_ids))
                        .order_by(ProviderRequestLog.id)
                    )
                ).all()
            )
            assert [row.id for row in request_logs] == binding.request_log_ids
            assert all(row.success and row.http_requests == 1 for row in request_logs)
            assert "synthetic-query-secret" in bound_urls[0]
            assert "api_key" not in bound_urls[1]
            assert "account" not in bound_urls[1]
            assert "fund" not in bound_urls[1]


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
    case, profile_id = await _create_committed_fixture(
        provider_db, monkeypatch, limit=2, with_profile=True
    )
    async with provider_db() as session:
        async with session.begin():
            runner = _TransportRunner()
            _use_mocktransport(monkeypatch, runner)

            # A flushed caller-owned profile row is not committed admission
            # evidence. The attempt-owned view rejects it before quota or IO.
            committed_profile = await session.get(ETFProfile, profile_id)
            assert committed_profile is not None
            await session.delete(committed_profile)
            await session.flush()
            pending_profile = ETFProfile(
                instrument_id=case.instrument_id,
                issuer="Uncommitted synthetic profile",
                adapter_key="synthetic_csv_fixture",
                provider_aliases={"holdings_source_provider": case.provider_name},
            )
            session.add(pending_profile)
            await session.flush()
            with bind_etf_holdings_request_context(
                db=session,
                adapter=case.adapter,
                profile_id=pending_profile.id,
                instrument_id=case.instrument_id,
                provider_symbol=case.instrument_symbol,
                operation=case.operation,
            ):
                async with adapter_httpx.AsyncClient(timeout=2) as client:
                    with pytest.raises(
                        ETFHoldingsRouteHeldError, match="committed profile and instrument"
                    ):
                        await client.get("https://publisher.example/holdings.csv")
            assert runner.calls == []

            with pytest.raises(ETFHoldingsRouteHeldError, match="not in the reviewed contract"):
                with bind_etf_holdings_request_context(
                    db=session,
                    adapter=case.adapter,
                    profile_id=profile_id,
                    instrument_id=case.instrument_id,
                    provider_symbol=case.instrument_symbol,
                    operation="unknown_operation",
                ):
                    await adapter_httpx.AsyncClient().get("https://publisher.example/start")
            assert runner.calls == []

            with bind_etf_holdings_request_context(
                db=session,
                adapter=case.adapter,
                profile_id=profile_id,
                instrument_id=case.instrument_id,
                provider_symbol="ARBITRARY-UNMAPPED",
                operation=case.operation,
            ):
                with pytest.raises(
                    ETFHoldingsRouteHeldError, match="does not match its committed instrument"
                ):
                    await adapter_httpx.AsyncClient(timeout=2).get(
                        "https://publisher.example/holdings.csv"
                    )
            assert runner.calls == []

            # Different sensitive values must never compare equal, even though
            # any eventual durable/display value would redact both.
            attempt = LoopLocalHTTPXAttempt(
                method="GET",
                url="https://publisher.example/holdings.csv?api_key=secret-a",
                request_kwargs={},
                client_kwargs={"timeout": 2},
                transport_factory=runner.factory,
            )
            with bind_etf_holdings_request_context(
                db=session,
                adapter=case.adapter,
                profile_id=profile_id,
                instrument_id=case.instrument_id,
                provider_symbol=case.instrument_symbol,
                operation=case.operation,
            ):
                with pytest.raises(ETFHoldingsRouteHeldError, match="full URL"):
                    await bridge.execute_etf_holdings_request_attempt(
                        session,
                        adapter=case.adapter,
                        instrument_id=case.instrument_id,
                        provider_symbol=case.instrument_symbol,
                        operation=case.operation,
                        request_url="https://publisher.example/holdings.csv?api_key=secret-b",
                        single_attempt=attempt,
                    )
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
                profile_id=profile_id,
                instrument_id=case.instrument_id,
                provider_symbol=case.instrument_symbol,
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
                profile_id=profile_id,
                instrument_id=case.instrument_id,
                provider_symbol=case.instrument_symbol,
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_adapter_refresh_retains_rejected_stale_payload_and_keeps_last_known(
    db_engine, provider_db, monkeypatch
):
    """A valid transport with stale content is evidence, not a current snapshot."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        db_engine.url.render_as_string(hide_password=False),
    )
    case, profile_id = await _create_committed_fixture(
        provider_db, monkeypatch, limit=5, with_profile=True
    )
    runner = _TransportRunner()
    async with provider_db() as session:
        async with session.begin():
            profile = await _load_profile(session, profile_id)
            runner.body = (
                f"Fund Ticker,{(await session.get(Instrument, case.instrument_id)).symbol}\n"
                "Symbol,Weight\nAAA,1.0\n"
            )
            _use_mocktransport(monkeypatch, runner)
            first_snapshot = await refresh._refresh_adapter_route(session, profile)
            await refresh._record_success(session, profile, snapshot=first_snapshot)
            current = evaluate_capability(
                profile,
                first_snapshot,
                await session.scalar(
                    select(ETFHoldingsAdapterState).where(
                        ETFHoldingsAdapterState.etf_profile_id == profile.id
                    )
                ),
            )
            assert current.availability == "current"
            assert current.identity_verified
            assert current.usable_for_current_analysis
            assert first_snapshot.source_artifact_id is not None
            old_composition_date = datetime.now(UTC).date() - timedelta(days=45)
            profile.provider_aliases = {
                **profile.provider_aliases,
                "holdings_composition_date": old_composition_date.isoformat(),
            }

    async with provider_db() as session:
        async with session.begin():
            profile = await _load_profile(session, profile_id)
            with pytest.raises(ValueError, match="composition .* is stale"):
                await refresh._refresh_adapter_route(session, profile)
            await refresh._record_failure(
                session,
                profile,
                ValueError("stale fixture rejected by refresh freshness gate"),
            )

            snapshots = list(
                (
                    await session.scalars(
                        select(ETFHoldingsSnapshot).where(
                            ETFHoldingsSnapshot.etf_profile_id == profile.id
                        )
                    )
                ).all()
            )
            assert [snapshot.id for snapshot in snapshots] == [first_snapshot.id]
            rejected = await session.scalar(
                select(ETFHoldingsRawArtifact).where(
                    ETFHoldingsRawArtifact.etf_profile_id == profile.id,
                    ETFHoldingsRawArtifact.source_kind == "issuer_adapter_rejected_fetch",
                )
            )
            assert rejected is not None
            assert rejected.payload_text == runner.body
            assert rejected.legal_metadata["provider_request_log_ids"]
            assert rejected.legal_metadata["validation"]["status"] == "stale"
            state = await session.scalar(
                select(ETFHoldingsAdapterState).where(
                    ETFHoldingsAdapterState.etf_profile_id == profile.id
                )
            )
            degraded = evaluate_capability(profile, first_snapshot, state)
            assert degraded.availability == "degraded"
            assert degraded.displayable_last_known
            assert not degraded.usable_for_current_analysis
            assert runner.calls == [
                ("GET", "https://publisher.example/holdings.csv"),
                ("GET", "https://publisher.example/holdings.csv"),
            ]
            assert len(set(rejected.legal_metadata["provider_request_log_ids"])) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_http_error_is_failed_shared_attempt_and_raw_body_is_retained(
    db_engine, provider_db, monkeypatch
):
    """HTTPX 4xx must fail Provider transport health and retain its response."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        db_engine.url.render_as_string(hide_password=False),
    )
    case, profile_id = await _create_committed_fixture(
        provider_db,
        monkeypatch,
        limit=3,
        with_profile=True,
        route_url="https://publisher.example/start?api_key=synthetic-secret-value",
    )
    with pytest.raises(httpx.HTTPStatusError):
        async with provider_db() as session:
            async with session.begin():
                profile = await _load_profile(session, profile_id)
                runner = _TransportRunner()
                runner.status_code = 403
                runner.body = "synthetic access denied body"
                _use_mocktransport(monkeypatch, runner)
                await refresh._refresh_adapter_route(session, profile)
    async with provider_db() as reopened:
        rows = list(
            (
                await reopened.scalars(
                    select(ProviderRequestLog)
                    .where(
                        ProviderRequestLog.data_source_id == case.source_id,
                        ProviderRequestLog.operation == case.operation,
                    )
                    .order_by(ProviderRequestLog.id)
                )
            ).all()
        )
        assert len(rows) == 2
        assert rows[0].success and rows[0].http_requests == 1
        assert not rows[1].success and rows[1].error_type == "HTTPStatusError"
        assert rows[1].response_payloads == [runner.body]
        artifact = await reopened.scalar(
            select(ETFHoldingsRawArtifact).where(
                ETFHoldingsRawArtifact.etf_profile_id == profile_id,
                ETFHoldingsRawArtifact.source_kind == "issuer_adapter_rejected_fetch",
            )
        )
        assert artifact is not None
        assert artifact.payload_text == runner.body
        assert artifact.content_hash == _hash_payload(runner.body)
        assert artifact.legal_metadata["provider_request_log_ids"] == [row.id for row in rows]
        assert artifact.legal_metadata["request_urls"] == [
            "https://publisher.example/start?api_key=<redacted>",
            "https://publisher.example/holdings.csv",
        ]
        assert "synthetic-secret-value" not in artifact.source_url
        assert "synthetic-secret-value" not in artifact.legal_metadata["failure_message"]
        assert runner.calls == [
            ("GET", "https://publisher.example/start?api_key=synthetic-secret-value"),
            ("GET", "https://publisher.example/holdings.csv"),
        ]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_timeout_preserves_uncertain_reservation_and_failed_attempt_lineage(
    db_engine, provider_db, monkeypatch
):
    """A transport timeout leaves a durable failed request record, not a leak."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        db_engine.url.render_as_string(hide_password=False),
    )
    case, profile_id = await _create_committed_fixture(
        provider_db, monkeypatch, limit=3, with_profile=True
    )
    async with provider_db() as session:
        async with session.begin():
            profile = await _load_profile(session, profile_id)
            runner = _TransportRunner()
            runner.raise_timeout = True
            _use_mocktransport(monkeypatch, runner)
            with pytest.raises(httpx.ReadTimeout, match="synthetic MockTransport timeout"):
                await refresh._refresh_adapter_route(session, profile)
            row = await _assert_one_settled_attempt(
                session,
                case,
                expected_success=False,
                expected_http_requests=0,
                expected_settled_usage=Decimal("0"),
                expected_reservation_state="uncertain",
            )
            assert row.error_type == "ReadTimeout"
            artifact = await session.scalar(
                select(ETFHoldingsRawArtifact).where(
                    ETFHoldingsRawArtifact.etf_profile_id == profile.id,
                    ETFHoldingsRawArtifact.source_kind == "issuer_adapter_rejected_fetch",
                )
            )
            assert artifact is not None
            assert artifact.legal_metadata["provider_request_log_ids"] == [row.id]
            assert artifact.payload_json["failure_type"] == "ReadTimeout"
            assert artifact.legal_metadata["request_urls"] == [
                "https://publisher.example/holdings.csv"
            ]
            assert runner.calls == [("GET", "https://publisher.example/holdings.csv")]
            assert (
                artifact.legal_metadata["failure_type"] == "ReadTimeout"
                and row.error_type == "ReadTimeout"
            )
            quota_window = await session.scalar(
                select(ProviderQuotaWindow).where(
                    ProviderQuotaWindow.data_source_id == case.source_id,
                    ProviderQuotaWindow.dimension == "requests_per_minute",
                )
            )
            assert quota_window is not None
            assert quota_window.reserved_units == 0
            assert quota_window.consumed_units == 0
            coordinator_summary = quota_coordinator.provider_quota_coordinator_summary(
                provider_name=case.provider_name
            )
            account_windows = [
                item
                for item in coordinator_summary["windows"]
                if item["account_scope"] == case.account_scope
                and item["dimension"] == "requests_per_minute"
            ]
            assert len(account_windows) == 1
            assert account_windows[0]["reserved_units"] == 1
            assert account_windows[0]["consumed_units"] == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_parser_rejection_keeps_transport_success_but_no_snapshot_and_raw_body(
    db_engine, provider_db, monkeypatch
):
    """Transport success is not content success when no holdings rows parse."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        db_engine.url.render_as_string(hide_password=False),
    )
    case, profile_id = await _create_committed_fixture(
        provider_db, monkeypatch, limit=3, with_profile=True
    )
    async with provider_db() as session:
        async with session.begin():
            profile = await _load_profile(session, profile_id)
            runner = _TransportRunner()
            runner.body = "challenge page; no holdings table"
            _use_mocktransport(monkeypatch, runner)
            with pytest.raises(ValueError, match="no parseable rows"):
                await refresh._refresh_adapter_route(session, profile)
            row = await _assert_one_settled_attempt(session, case, expected_success=True)
            assert row.response_payloads == [runner.body]
            assert (
                await session.scalar(
                    select(ETFHoldingsSnapshot.id).where(
                        ETFHoldingsSnapshot.etf_profile_id == profile.id
                    )
                )
                is None
            )
            artifact = await session.scalar(
                select(ETFHoldingsRawArtifact).where(
                    ETFHoldingsRawArtifact.etf_profile_id == profile.id,
                    ETFHoldingsRawArtifact.source_kind == "issuer_adapter_rejected_fetch",
                )
            )
            assert artifact is not None
            assert artifact.payload_text == runner.body
            assert artifact.legal_metadata["provider_request_log_ids"] == [row.id]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_latest_ingest_database_validation_failure_retains_body_after_rollback(
    db_engine, provider_db, monkeypatch
):
    """A real persistence constraint rejection keeps raw bytes beyond UOW rollback."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        db_engine.url.render_as_string(hide_password=False),
    )
    case, profile_id = await _create_committed_fixture(
        provider_db, monkeypatch, limit=3, with_profile=True
    )
    long_name = "Rejected holding name " + ("X" * 400)
    runner = _TransportRunner()
    runner.body = f"Symbol,Name,Weight,Fund\nAAA,{long_name},1.0,{case.instrument_symbol}\n"
    _use_mocktransport(monkeypatch, runner)

    with pytest.raises(DBAPIError):
        async with provider_db() as session:
            async with session.begin():
                profile = await _load_profile(session, profile_id)
                await refresh._refresh_adapter_route(session, profile)

    async with provider_db() as reopened:
        row = await _assert_one_settled_attempt(
            reopened,
            case,
            expected_success=True,
            expected_http_requests=1,
        )
        artifact = await reopened.scalar(
            select(ETFHoldingsRawArtifact).where(
                ETFHoldingsRawArtifact.etf_profile_id == profile_id,
                ETFHoldingsRawArtifact.source_kind == "issuer_adapter_rejected_fetch",
            )
        )
        assert artifact is not None
        assert artifact.payload_text == runner.body
        assert artifact.content_hash == _hash_payload(runner.body)
        assert artifact.legal_metadata["provider_request_log_ids"] == [row.id]
        assert artifact.legal_metadata["validation"]["status"] == "ingest_rejected"
        assert (
            await reopened.scalar(
                select(ETFHoldingsSnapshot.id).where(
                    ETFHoldingsSnapshot.etf_profile_id == profile_id
                )
            )
            is None
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dated_refresh_persists_the_requested_point_in_time_without_relabelling(
    db_engine, provider_db, monkeypatch
):
    """Dated issuer success preserves requested/as-of and composition dates."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        db_engine.url.render_as_string(hide_password=False),
    )
    dated_template = "https://publisher.example/archive/{symbol}/{date}.csv"
    case, profile_id = await _create_committed_fixture(
        provider_db,
        monkeypatch,
        limit=3,
        with_profile=True,
        operation="fetch_etf_holdings_for_date",
        dated_route_template=dated_template,
    )
    requested_date = date(2025, 6, 30)
    runner = _TransportRunner()
    runner.body = f"Symbol,Name,Weight,Fund\nAAA,Example Corp,1.0,{case.instrument_symbol}\n"
    _use_mocktransport(monkeypatch, runner)

    async with provider_db() as session:
        async with session.begin():
            profile = await _load_profile(session, profile_id)
            snapshot = await refresh.refresh_etf_holdings_for_date(
                session, profile, requested_date=requested_date
            )
            assert snapshot.composition_date == requested_date
            assert snapshot.as_of_date == requested_date
            assert snapshot.known_at is not None
            assert runner.calls == [
                (
                    "GET",
                    f"https://publisher.example/archive/{case.instrument_symbol}/2025-06-30.csv",
                )
            ]

    async with provider_db() as reopened:
        logs = list(
            (
                await reopened.scalars(
                    select(ProviderRequestLog).where(
                        ProviderRequestLog.data_source_id == case.source_id,
                        ProviderRequestLog.operation == "fetch_etf_holdings_for_date",
                    )
                )
            ).all()
        )
        assert len(logs) == 1
        assert logs[0].success and logs[0].http_requests == 1
        assert logs[0].settled_usage_units == Decimal("1.0000")
        persisted = await reopened.get(ETFHoldingsSnapshot, snapshot.id)
        assert persisted is not None
        assert persisted.composition_date == requested_date
        assert persisted.as_of_date == requested_date


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dated_refresh_rejection_retains_identical_body_attempt_links_after_rollback(
    db_engine, provider_db, monkeypatch
):
    """Dedup keeps one raw body while linking every repeated failed date attempt."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        db_engine.url.render_as_string(hide_password=False),
    )
    case, profile_id = await _create_committed_fixture(
        provider_db,
        monkeypatch,
        limit=4,
        with_profile=True,
        operation="fetch_etf_holdings_for_date",
        dated_route_template="https://publisher.example/archive/{symbol}/{date}.csv",
    )
    requested_date = date(2025, 6, 30)
    response_body = "archived publisher challenge response"
    runner = _TransportRunner()
    runner.status_code = 500
    runner.body = response_body
    _use_mocktransport(monkeypatch, runner)

    for _ in range(2):
        with pytest.raises(httpx.HTTPStatusError):
            async with provider_db() as session:
                async with session.begin():
                    profile = await _load_profile(session, profile_id)
                    await refresh.refresh_etf_holdings_for_date(
                        session, profile, requested_date=requested_date
                    )

    async with provider_db() as reopened:
        logs = list(
            (
                await reopened.scalars(
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
        assert all(not row.success and row.http_requests == 1 for row in logs)
        assert all(row.completed_at is not None for row in logs)
        assert all(row.settled_usage_units == Decimal("1.0000") for row in logs)
        artifacts = list(
            (
                await reopened.scalars(
                    select(ETFHoldingsRawArtifact).where(
                        ETFHoldingsRawArtifact.etf_profile_id == profile_id,
                        ETFHoldingsRawArtifact.source_kind == "issuer_adapter_rejected_fetch",
                    )
                )
            ).all()
        )
        assert len(artifacts) == 1
        artifact = artifacts[0]
        assert artifact.payload_text == response_body
        assert artifact.content_hash == _hash_payload(response_body)
        assert artifact.legal_metadata["provider_request_log_ids"] == [row.id for row in logs]
        assert artifact.legal_metadata["request_urls"] == [
            f"https://publisher.example/archive/{case.instrument_symbol}/2025-06-30.csv",
            f"https://publisher.example/archive/{case.instrument_symbol}/2025-06-30.csv",
        ]
        assert artifact.legal_metadata["rejected_requested_dates"] == ["2025-06-30"]
        assert [item["request_log_id"] for item in artifact.legal_metadata["request_attempts"]] == [
            row.id for row in logs
        ]
        assert runner.calls == [
            (
                "GET",
                f"https://publisher.example/archive/{case.instrument_symbol}/2025-06-30.csv",
            ),
            (
                "GET",
                f"https://publisher.example/archive/{case.instrument_symbol}/2025-06-30.csv",
            ),
        ]
        assert (
            await reopened.scalar(
                select(ETFHoldingsSnapshot.id).where(
                    ETFHoldingsSnapshot.etf_profile_id == profile_id
                )
            )
            is None
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dated_refresh_retains_future_composition_claim_without_snapshot(
    db_engine, provider_db, monkeypatch
):
    """A future-dated response is retained as rejected evidence, never a snapshot."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        db_engine.url.render_as_string(hide_password=False),
    )
    case, profile_id = await _create_committed_fixture(
        provider_db,
        monkeypatch,
        limit=3,
        with_profile=True,
        operation="fetch_etf_holdings_for_date",
        dated_route_template="https://publisher.example/archive/{symbol}/{date}.csv",
    )
    requested_date = date(2025, 6, 30)
    reported_date = date(2025, 7, 1)
    runner = _TransportRunner()
    runner.body = f"Symbol,Name,Weight,Fund\nAAA,Example Corp,1.0,{case.instrument_symbol}\n"
    _use_mocktransport(monkeypatch, runner)
    original_fetch_for_date = IssuerCsvHoldingsAdapter.fetch_for_date

    async def future_dated_fetch(adapter, **kwargs):
        result = await original_fetch_for_date(adapter, **kwargs)
        result.legal_metadata = {
            **(result.legal_metadata or {}),
            "composition_date": reported_date.isoformat(),
        }
        return result

    monkeypatch.setattr(IssuerCsvHoldingsAdapter, "fetch_for_date", future_dated_fetch)
    with pytest.raises(ValueError, match="after the requested date"):
        async with provider_db() as session:
            async with session.begin():
                profile = await _load_profile(session, profile_id)
                await refresh.refresh_etf_holdings_for_date(
                    session, profile, requested_date=requested_date
                )

    async with provider_db() as reopened:
        row = await _assert_one_settled_attempt(
            reopened,
            case,
            expected_success=True,
            expected_http_requests=1,
        )
        artifact = await reopened.scalar(
            select(ETFHoldingsRawArtifact).where(
                ETFHoldingsRawArtifact.etf_profile_id == profile_id,
                ETFHoldingsRawArtifact.source_kind == "issuer_adapter_rejected_fetch",
            )
        )
        assert artifact is not None
        assert artifact.payload_text == runner.body
        assert artifact.content_hash == _hash_payload(runner.body)
        assert artifact.composition_date is None
        assert artifact.as_of_date is None
        assert artifact.legal_metadata["provider_request_log_ids"] == [row.id]
        assert artifact.legal_metadata["rejected_requested_dates"] == [requested_date.isoformat()]
        assert artifact.legal_metadata["validation"] == {
            "status": "composition_after_requested_date",
            "reported_composition_date": reported_date.isoformat(),
        }
        assert (
            await reopened.scalar(
                select(ETFHoldingsSnapshot.id).where(
                    ETFHoldingsSnapshot.etf_profile_id == profile_id
                )
            )
            is None
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dated_ingest_validation_rejection_retains_raw_response(
    db_engine, provider_db, monkeypatch
):
    """Post-fetch ingest validation failure retains bytes outside caller UOW."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        db_engine.url.render_as_string(hide_password=False),
    )
    case, profile_id = await _create_committed_fixture(
        provider_db,
        monkeypatch,
        limit=3,
        with_profile=True,
        operation="fetch_etf_holdings_for_date",
        dated_route_template="https://publisher.example/archive/{symbol}/{date}.csv",
    )
    requested_date = date(2025, 6, 30)
    runner = _TransportRunner()
    runner.body = f"Symbol,Name,Weight,Fund\nAAA,Example Corp,1.0,{case.instrument_symbol}\n"
    _use_mocktransport(monkeypatch, runner)

    async def reject_ingest(*_args, **_kwargs):
        raise ValueError("synthetic ingest validation rejection")

    monkeypatch.setattr(refresh, "ingest_holdings_snapshot", reject_ingest)
    with pytest.raises(ValueError, match="synthetic ingest validation rejection"):
        async with provider_db() as session:
            async with session.begin():
                profile = await _load_profile(session, profile_id)
                await refresh.refresh_etf_holdings_for_date(
                    session, profile, requested_date=requested_date
                )

    async with provider_db() as reopened:
        row = await _assert_one_settled_attempt(
            reopened,
            case,
            expected_success=True,
            expected_http_requests=1,
        )
        artifact = await reopened.scalar(
            select(ETFHoldingsRawArtifact).where(
                ETFHoldingsRawArtifact.etf_profile_id == profile_id,
                ETFHoldingsRawArtifact.source_kind == "issuer_adapter_rejected_fetch",
            )
        )
        assert artifact is not None
        assert artifact.payload_text == runner.body
        assert artifact.content_hash == _hash_payload(runner.body)
        assert artifact.legal_metadata["provider_request_log_ids"] == [row.id]
        assert artifact.legal_metadata["validation"] == {
            "status": "ingest_rejected",
            "requested_date": requested_date.isoformat(),
            "composition_date": requested_date.isoformat(),
        }
        assert artifact.legal_metadata["rejected_requested_dates"] == [requested_date.isoformat()]
        assert (
            await reopened.scalar(
                select(ETFHoldingsSnapshot.id).where(
                    ETFHoldingsSnapshot.etf_profile_id == profile_id
                )
            )
            is None
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dated_database_validation_failure_preserves_original_error_and_raw_body(
    db_engine, provider_db, monkeypatch
):
    """A real dated persistence rejection survives caller rollback and reopen."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        db_engine.url.render_as_string(hide_password=False),
    )
    case, profile_id = await _create_committed_fixture(
        provider_db,
        monkeypatch,
        limit=3,
        with_profile=True,
        operation="fetch_etf_holdings_for_date",
        dated_route_template="https://publisher.example/archive/{symbol}/{date}.csv",
    )
    requested_date = date(2025, 6, 30)
    long_name = "Rejected dated holding name " + ("X" * 400)
    runner = _TransportRunner()
    runner.body = f"Symbol,Name,Weight,Fund\nAAA,{long_name},1.0,{case.instrument_symbol}\n"
    _use_mocktransport(monkeypatch, runner)

    with pytest.raises(DBAPIError, match="value too long"):
        async with provider_db() as session:
            async with session.begin():
                profile = await _load_profile(session, profile_id)
                await refresh.refresh_etf_holdings_for_date(
                    session, profile, requested_date=requested_date
                )

    async with provider_db() as reopened:
        row = await _assert_one_settled_attempt(
            reopened,
            case,
            expected_success=True,
            expected_http_requests=1,
        )
        artifact = await reopened.scalar(
            select(ETFHoldingsRawArtifact).where(
                ETFHoldingsRawArtifact.etf_profile_id == profile_id,
                ETFHoldingsRawArtifact.source_kind == "issuer_adapter_rejected_fetch",
            )
        )
        assert artifact is not None
        assert artifact.payload_text == runner.body
        assert artifact.content_hash == _hash_payload(runner.body)
        assert artifact.legal_metadata["provider_request_log_ids"] == [row.id]
        assert artifact.legal_metadata["validation"] == {
            "status": "ingest_rejected",
            "requested_date": requested_date.isoformat(),
            "composition_date": requested_date.isoformat(),
        }
        assert artifact.legal_metadata["rejected_requested_dates"] == [requested_date.isoformat()]
        assert (
            await reopened.scalar(
                select(ETFHoldingsSnapshot.id).where(
                    ETFHoldingsSnapshot.etf_profile_id == profile_id
                )
            )
            is None
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dated_cancellation_retains_response_after_real_caller_rollback(
    db_engine, provider_db, monkeypatch
):
    """Cancellation in the dated route leaves raw/request lineage after rollback."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        db_engine.url.render_as_string(hide_password=False),
    )
    case, profile_id = await _create_committed_fixture(
        provider_db,
        monkeypatch,
        limit=3,
        with_profile=True,
        operation="fetch_etf_holdings_for_date",
        dated_route_template="https://publisher.example/archive/{symbol}/{date}.csv",
    )
    runner = _TransportRunner()
    runner.started = threading.Event()
    runner.release = threading.Event()
    _use_mocktransport(monkeypatch, runner)
    requested_date = date(2025, 6, 30)

    with pytest.raises(asyncio.CancelledError):
        async with provider_db() as session:
            async with session.begin():
                profile = await _load_profile(session, profile_id)
                task = asyncio.create_task(
                    refresh.refresh_etf_holdings_for_date(
                        session, profile, requested_date=requested_date
                    )
                )
                assert await asyncio.to_thread(runner.started.wait, 3)
                task.cancel()
                await asyncio.sleep(0.02)
                assert not task.done()
                task.cancel()
                await asyncio.sleep(0.02)
                assert not task.done()
                runner.release.set()
                await task

    async with provider_db() as reopened:
        row = await _assert_one_settled_attempt(
            reopened,
            case,
            expected_success=True,
            expected_http_requests=1,
        )
        artifact = await reopened.scalar(
            select(ETFHoldingsRawArtifact).where(
                ETFHoldingsRawArtifact.etf_profile_id == profile_id,
                ETFHoldingsRawArtifact.source_kind == "issuer_adapter_rejected_fetch",
            )
        )
        assert artifact is not None
        assert artifact.payload_text == runner.body
        assert artifact.content_hash == _hash_payload(runner.body)
        assert artifact.legal_metadata["provider_request_log_ids"] == [row.id]
        assert artifact.legal_metadata["rejected_requested_dates"] == [requested_date.isoformat()]
        assert (
            await reopened.scalar(
                select(ETFHoldingsSnapshot.id).where(
                    ETFHoldingsSnapshot.etf_profile_id == profile_id
                )
            )
            is None
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_caller_cancellation_waits_for_shared_attempt_settlement_and_retains_lineage(
    db_engine, provider_db, monkeypatch
):
    """Caller cancellation cannot abandon an admitted executor reservation."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        db_engine.url.render_as_string(hide_password=False),
    )
    case, profile_id = await _create_committed_fixture(
        provider_db, monkeypatch, limit=3, with_profile=True
    )
    with pytest.raises(asyncio.CancelledError):
        async with provider_db() as session:
            async with session.begin():
                profile = await _load_profile(session, profile_id)
                runner = _TransportRunner()
                runner.started = threading.Event()
                runner.release = threading.Event()
                _use_mocktransport(monkeypatch, runner)
                # The public refresh call runs inside a real caller unit of
                # work. Its Provider request log is independently durable;
                # cancellation rolls back caller-owned ETF state/artifacts.
                refresh_task = asyncio.create_task(refresh._refresh_adapter_route(session, profile))
                assert await asyncio.to_thread(runner.started.wait, 3)
                refresh_task.cancel()
                await asyncio.sleep(0.02)
                assert not refresh_task.done()
                refresh_task.cancel()
                await asyncio.sleep(0.02)
                assert not refresh_task.done()
                runner.release.set()
                # Let CancelledError cross session.begin so its real rollback
                # path runs; catching it inside would commit this UOW.
                await refresh_task
    # Closing the cancelled UOW rolls back ETF artifacts/state, while the
    # independent Provider attempt remains inspectable after reopening.
    async with provider_db() as reopened:
        row = await _assert_one_settled_attempt(reopened, case, expected_success=True)
        assert row.response_payloads == [runner.body]
        assert (
            await reopened.scalar(
                select(ETFHoldingsSnapshot.id).where(
                    ETFHoldingsSnapshot.etf_profile_id == profile_id
                )
            )
            is None
        )
        artifact = await reopened.scalar(
            select(ETFHoldingsRawArtifact).where(
                ETFHoldingsRawArtifact.etf_profile_id == profile_id,
                ETFHoldingsRawArtifact.source_kind == "issuer_adapter_rejected_fetch",
            )
        )
        assert artifact is not None
        assert artifact.payload_text == runner.body
        assert artifact.content_hash == _hash_payload(runner.body)
        assert artifact.legal_metadata["provider_request_log_ids"] == [row.id]
        assert artifact.legal_metadata["request_urls"] == ["https://publisher.example/holdings.csv"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_same_account_calls_cannot_double_spend_after_runtime_restart(
    db_engine, provider_db, monkeypatch
):
    """One durable request unit admits one concurrent caller and survives reopen."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        db_engine.url.render_as_string(hide_password=False),
    )
    case, profile_id = await _create_committed_fixture(
        provider_db, monkeypatch, limit=1, with_profile=True
    )
    runner = _TransportRunner()
    _use_mocktransport(monkeypatch, runner)

    async def admitted_call():
        async with provider_db() as session:
            async with session.begin():
                with bind_etf_holdings_request_context(
                    db=session,
                    adapter=case.adapter,
                    profile_id=profile_id,
                    instrument_id=case.instrument_id,
                    provider_symbol=case.instrument_symbol,
                    operation=case.operation,
                ):
                    async with adapter_httpx.AsyncClient(timeout=2) as client:
                        return await client.get("https://publisher.example/holdings.csv")

    outcomes = await asyncio.gather(admitted_call(), admitted_call(), return_exceptions=True)
    responses = [item for item in outcomes if isinstance(item, httpx.Response)]
    denied = [item for item in outcomes if isinstance(item, ProviderQuotaAdmissionError)]
    assert len(responses) == 1 and responses[0].status_code == 200
    assert len(denied) == 1
    assert runner.calls == [("GET", "https://publisher.example/holdings.csv")]

    async with provider_db() as session:
        logs = list(
            (
                await session.scalars(
                    select(ProviderRequestLog).where(
                        ProviderRequestLog.data_source_id == case.source_id,
                        ProviderRequestLog.operation == case.operation,
                    )
                )
            ).all()
        )
        assert len(logs) == 1
        assert logs[0].success
        assert logs[0].settled_usage_units == Decimal("1.0000")
        window = await session.scalar(
            select(ProviderQuotaWindow).where(
                ProviderQuotaWindow.data_source_id == case.source_id,
                ProviderQuotaWindow.dimension == "requests_per_minute",
            )
        )
        assert window is not None
        assert window.reserved_units == 0
        assert window.consumed_units == 1

    quota_engine = quota_coordinator._engine_for(quota_coordinator._engine_url())
    quota_engine.dispose()
    with quota_engine.connect() as connection:
        reservations = (
            connection.execute(
                select(quota_coordinator._reservations).where(
                    quota_coordinator._reservations.c.provider_name == case.provider_name
                )
            )
            .mappings()
            .all()
        )
    assert len(reservations) == 1
    assert reservations[0]["state"] == "settled"
    assert reservations[0]["reserved_units"] == 1
    assert reservations[0]["settled_at"] is not None
