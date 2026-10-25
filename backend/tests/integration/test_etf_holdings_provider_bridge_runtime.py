"""Real shared Provider admission around offline ETF HTTPX attempts.

This module intentionally runs against TEST_DATABASE_URL (or the normal
integration Postgres fixture) and uses only HTTPX MockTransport. It never
contacts an issuer or provider.
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import threading
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
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
from app.models.instrument_identity import InstrumentProviderCapabilityStatus
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
from app.services.etf_holdings import _hash_payload, holdings_capability_for_symbol
from app.services.etf_holdings_adapters import (
    CiFinancialHoldingsAdapter,
    IssuerCsvAdapterConfig,
    IssuerCsvHoldingsAdapter,
    get_holdings_adapter,
)
from app.services.etf_holdings_adapters import httpx as adapter_httpx
from app.services.etf_holdings_capability import evaluate_capability, load_canary_history
from app.services.etf_holdings_provider_bridge import (
    ETFHoldingsRouteHeldError,
    LoopLocalHTTPXAttempt,
    bind_etf_holdings_request_context,
)
from app.services.provider_quota_coordinator import ProviderQuotaAdmissionError
from app.services.provider_recurring_costs import provider_recurring_cost_status
from app.services.provider_runtime import (
    ProviderNoDataError,
    policy_allows_account_usage_bootstrap,
    provider_checkpoint_operation_hold_reason,
    seed_provider_runtime,
)


class _ProviderDB:
    """Session factory and owned schema URL for committed Provider tests."""

    def __init__(self, session_factory, url):
        self._session_factory = session_factory
        self.url = url

    def __call__(self):
        return self._session_factory()


@pytest_asyncio.fixture
async def provider_db(db_engine):
    """Use a per-test schema for commits outside the shared rollback fixture."""

    from app.database import Base

    schema = f"etf_provider_runtime_{uuid4().hex}"
    with db_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    schema_url = db_engine.url.set(
        query={**dict(db_engine.url.query), "options": f"-csearch_path={schema}"}
    )
    async_url = schema_url.set(
        drivername="postgresql+asyncpg",
        query={key: value for key, value in schema_url.query.items() if key != "options"},
    )
    engine = create_async_engine(
        async_url,
        pool_pre_ping=True,
        connect_args={"server_settings": {"search_path": schema}},
    )
    quota_url = schema_url.render_as_string(hide_password=False)
    quota_engine = None
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            assert await session.scalar(text("SELECT current_schema()")) == schema
        quota_engine = quota_coordinator._engine_for(quota_url)
        with quota_engine.connect() as connection:
            assert connection.execute(text("SELECT current_schema()")).scalar_one() == schema
        yield _ProviderDB(
            session_factory,
            schema_url,
        )
    finally:
        await engine.dispose()
        if quota_engine is not None:
            quota_engine.dispose()
        with db_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


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
    provider_name_override: str | None = None,
    instrument_symbol_override: str | None = None,
    quota_scope_override: str = "api_key",
):
    suffix = uuid4().hex[:10]
    provider_name = provider_name_override or f"etf-fixture-{suffix}"
    account_scope = f"etf-offline-test-account-{suffix}"
    quota_scope = quota_scope_override
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
        symbol=instrument_symbol_override or f"ZZ{suffix[:4].upper()}",
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
    provider_db, monkeypatch, redis_url
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
        provider_db.url.render_as_string(hide_password=False),
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
async def test_nsi_real_adapter_submits_product_redirect_and_csv_to_shared_admission(
    provider_db, monkeypatch
):
    """The native NSI adapter sends every physical page/file request via Provider."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
    )
    adapter = get_holdings_adapter("nsi")
    assert adapter is not None
    product_page_url = "https://www.nationalsecurityindex.com/catalog/nsi"
    csv_url = "https://www.nationalsecurityindex.com/f/holdings.csv"
    product_page = "<title>National Security Emerging Markets Index ETF</title> NSI /f/holdings.csv"
    raw_csv = (
        "National Security Emerging Markets Index ETF NSI\n"
        "Holdings as of 10/21/2026\n"
        "Name,Security Identifier,Symbol,Net Assets %,Market Price,Shares Held,Market Value,Market Value %\n"
        "Example Corp,037833100,AAA,1.0,10,100,1000,1.0\n"
    )
    calls = []

    def handle(request):
        calls.append((request.method, str(request.url)))
        if request.url.path == "/":
            return httpx.Response(302, headers={"location": product_page_url}, request=request)
        if request.url.path == "/catalog/nsi":
            return httpx.Response(200, text=product_page, request=request)
        if request.url.path == "/f/holdings.csv":
            assert request.headers.get("referer") == product_page_url
            return httpx.Response(200, text=raw_csv, request=request)
        raise AssertionError(f"Unexpected NSI MockTransport URL: {request.url}")

    original_factory = bridge._make_loop_local_httpx_attempt

    def nsi_mocktransport_factory(**kwargs):
        return original_factory(**kwargs, transport_factory=lambda: httpx.MockTransport(handle))

    monkeypatch.setattr(bridge, "_make_loop_local_httpx_attempt", nsi_mocktransport_factory)

    profile_id = None
    async with provider_db() as session:
        async with session.begin():
            case = await _seed_reviewed_fixture(
                session,
                limit=3,
                monkeypatch=monkeypatch,
                reviewed_hosts=["www.nationalsecurityindex.com"],
                provider_name_override=adapter.source_provider,
                instrument_symbol_override="NSI",
            )
            instrument = await session.get(Instrument, case.instrument_id)
            assert instrument is not None
            profile = ETFProfile(
                instrument_id=instrument.id,
                instrument=instrument,
                issuer="Synthetic test fixture; not publisher evidence",
                adapter_key=adapter.adapter_key,
                adapter_status="pending",
                provider_aliases={"holdings_source_provider": adapter.source_provider},
            )
            session.add(profile)
            await session.flush()
            profile_id = profile.id

    assert case is not None and profile_id is not None
    async with provider_db() as session:
        async with session.begin():
            profile = await _load_profile(session, profile_id)
            instrument = profile.instrument
            assert instrument is not None
            with bind_etf_holdings_request_context(
                db=session,
                adapter=adapter,
                profile_id=profile.id,
                instrument_id=instrument.id,
                provider_symbol=instrument.symbol,
                operation=case.operation,
            ) as binding:
                result = await adapter.fetch_latest(symbol=instrument.symbol)

            assert len(result.rows) == 1
            assert result.rows[0].symbol == "AAA"
            assert [url for method, url in calls if method == "GET"] == [
                "https://www.nationalsecurityindex.com/",
                product_page_url,
                csv_url,
            ]
            assert len(binding.request_log_ids) == 3
            assert [
                binding.request_urls_by_log_id[log_id] for log_id in binding.request_log_ids
            ] == [
                "https://www.nationalsecurityindex.com/",
                product_page_url,
                csv_url,
            ]
            logs = list(
                (
                    await session.scalars(
                        select(ProviderRequestLog)
                        .where(ProviderRequestLog.id.in_(binding.request_log_ids))
                        .order_by(ProviderRequestLog.id)
                    )
                ).all()
            )
            assert [row.id for row in logs] == binding.request_log_ids
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
            _assert_second_bucket_contract(windows, consumed_units=3, reserved_units=0)

    quota_engine = quota_coordinator._engine_for(quota_coordinator._engine_url())
    with quota_engine.connect() as connection:
        reservations = (
            connection.execute(
                select(quota_coordinator._reservations)
                .where(quota_coordinator._reservations.c.provider_name == case.provider_name)
                .order_by(
                    quota_coordinator._reservations.c.created_at,
                    quota_coordinator._reservations.c.id,
                )
            )
            .mappings()
            .all()
        )
    assert len(reservations) == 3
    assert all(row["state"] == "settled" and row["settled_at"] is not None for row in reservations)
    assert all(row["reserved_units"] == 1 for row in reservations)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_adapter_params_are_admitted_as_effective_url_and_not_replayed_on_redirect(
    provider_db, monkeypatch
):
    """Real adapter query params and redirects retain exact per-log URL binding."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
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
async def test_unknown_held_and_exhausted_routes_never_start_transport(provider_db, monkeypatch):
    """Unknown/held routes and durable quota exhaustion are pre-transport."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
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
    provider_db, monkeypatch
):
    """A valid transport with stale content is evidence, not a current snapshot."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
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
    provider_db, monkeypatch
):
    """HTTPX 4xx must fail Provider transport health and retain its response."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
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
    provider_db, monkeypatch
):
    """A transport timeout leaves a durable failed request record, not a leak."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
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
async def test_sec_fund_deadline_cancels_worker_transport_before_durable_settlement(
    provider_db, monkeypatch
):
    """Fund expiry cancels the worker I/O, then persists its uncertain attempt."""

    from app.services import etf_holdings_edgar as edgar

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
    )
    operation = "fetch_etf_holdings_sec_submissions"
    admission_allowance_seconds = 30.0
    in_flight_budget_seconds = 2.0
    worker_attempt_cap = 5.0
    monkeypatch.setattr(edgar, "ETF_SEC_FUND_DEADLINE_SECONDS", admission_allowance_seconds)
    monkeypatch.setattr(bridge, "ETF_SEC_FUND_DEADLINE_SECONDS", admission_allowance_seconds)
    # Admission gets a finite test-only allowance; the actual worker boundary
    # below clamps the shared budget to two seconds without extending an
    # earlier deadline. The attempt cap remains five seconds.
    monkeypatch.setattr(bridge, "ETF_SEC_ATTEMPT_TIMEOUT_SECONDS", worker_attempt_cap)
    budgets = []
    budget_type = bridge.ETFSECExecutionBudget

    def new_budget(initial_qualification_authority=None):
        assert initial_qualification_authority is None
        budget = budget_type(initial_qualification_authority)
        budgets.append(budget)
        return budget

    monkeypatch.setattr(edgar, "ETFSECExecutionBudget", new_budget)
    deadline_clamps = []
    original_execute = bridge.LoopLocalHTTPXAttempt.execute

    async def execute_with_in_flight_deadline(attempt):
        budget = attempt.sec_budget
        if budget is not None:
            prior_deadline = budget.deadline_at
            requested_deadline = time.monotonic() + in_flight_budget_seconds
            budget.deadline_at = min(prior_deadline, requested_deadline)
            deadline_clamps.append((prior_deadline, requested_deadline, budget.deadline_at))
        return await original_execute(attempt)

    monkeypatch.setattr(bridge.LoopLocalHTTPXAttempt, "execute", execute_with_in_flight_deadline)
    async with provider_db() as setup:
        async with setup.begin():
            case = await _seed_reviewed_fixture(
                setup,
                limit=3,
                monkeypatch=monkeypatch,
                reviewed_hosts=["data.sec.gov"],
                operation=operation,
                provider_name_override="edgar",
                instrument_symbol_override="IWM",
                quota_scope_override="ip",
            )
            instrument = await setup.get(Instrument, case.instrument_id)
            assert instrument is not None
            profile = ETFProfile(
                instrument_id=instrument.id,
                instrument=instrument,
                adapter_key="ishares",
                sec_cik="0001100663",
                sec_series_id="S000004344",
                sec_class_id="C000012074",
                provider_aliases={"holdings_source_provider": "ishares"},
            )
            setup.add(profile)
            await setup.flush()
            profile_id = profile.id

    class WaitingSECTransport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.started = threading.Event()
            self.cancelled = threading.Event()
            self.started_at = None
            self.cancelled_at = None
            self.calls = []

        async def handle_async_request(self, request):
            self.calls.append(str(request.url))
            self.started_at = time.monotonic()
            self.started.set()
            try:
                # A real HTTPX transport coroutine that cannot finish by itself.
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled_at = time.monotonic()
                self.cancelled.set()
                raise

        async def aclose(self):
            return None

    transports = []

    def transport_factory():
        transport = WaitingSECTransport()
        transports.append(transport)
        return transport

    original_attempt_factory = bridge._make_loop_local_httpx_attempt

    def attempt_factory(**kwargs):
        return original_attempt_factory(**kwargs, transport_factory=transport_factory)

    monkeypatch.setattr(bridge, "_make_loop_local_httpx_attempt", attempt_factory)
    quota_coordinator.ensure_provider_quota_coordinator(require_persistent_coordinator=True)
    request_url = "https://data.sec.gov/submissions/CIK0001100663.json"

    async with provider_db() as session:
        profile = await _load_profile(session, profile_id)
        identity = await edgar._resolve_request_identity(db=session, profile=profile)
        with pytest.raises(ETFHoldingsRouteHeldError, match="execution deadline exceeded"):
            await edgar._run_in_sec_fund_scope(
                lambda: edgar._sec_get(
                    identity,
                    operation=operation,
                    url=request_url,
                )
            )

    assert len(budgets) == 1
    budget = budgets[0]
    assert len(deadline_clamps) == 1
    prior_deadline, requested_deadline, effective_deadline = deadline_clamps[0]
    assert effective_deadline == min(prior_deadline, requested_deadline)
    assert effective_deadline <= prior_deadline
    assert effective_deadline - time.monotonic() <= in_flight_budget_seconds
    assert len(transports) == 1
    transport = transports[0]
    assert transport.started.wait(1)
    assert transport.cancelled.wait(1), "fund expiry did not cancel the active HTTPX transport"
    assert transport.calls == [request_url]
    assert transport.started_at is not None
    assert transport.cancelled_at is not None
    assert transport.started_at < effective_deadline
    assert transport.cancelled_at <= budget.deadline_at + 0.5
    assert budget._terminal_failure == "SEC one-fund execution deadline exceeded"
    with pytest.raises(ETFHoldingsRouteHeldError, match="terminal response"):
        await budget.before_attempt()

    async with provider_db() as reopened:
        row = await _assert_one_settled_attempt(
            reopened,
            case,
            expected_success=False,
            expected_http_requests=0,
            expected_settled_usage=Decimal("0"),
            expected_reservation_state="uncertain",
        )
        assert row.completed_at is not None
        assert row.error_type == "TimeoutError"
        assert "deadline" in (row.error_message or "").lower()
        assert row.response_bytes == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_parser_rejection_keeps_transport_success_but_no_snapshot_and_raw_body(
    provider_db, monkeypatch
):
    """Transport success is not content success when no holdings rows parse."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
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
    provider_db, monkeypatch
):
    """A real persistence constraint rejection keeps raw bytes beyond UOW rollback."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
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
    provider_db, monkeypatch
):
    """Dated issuer success preserves requested/as-of and composition dates."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
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
    provider_db, monkeypatch
):
    """Dedup keeps one raw body while linking every repeated failed date attempt."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
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
    provider_db, monkeypatch
):
    """A future-dated response is retained as rejected evidence, never a snapshot."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
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
async def test_dated_ingest_validation_rejection_retains_raw_response(provider_db, monkeypatch):
    """Post-fetch ingest validation failure retains bytes outside caller UOW."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
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
    provider_db, monkeypatch
):
    """A real dated persistence rejection survives caller rollback and reopen."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
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
    provider_db, monkeypatch
):
    """Cancellation in the dated route leaves raw/request lineage after rollback."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
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
                try:
                    started = await asyncio.to_thread(runner.started.wait, 30)
                    if not started and task.done():
                        # Surface an admission/runtime exception rather than
                        # disguising it as a slow transport start.
                        await task
                    assert started
                    task.cancel()
                    await asyncio.sleep(0.02)
                    assert not task.done()
                    task.cancel()
                    await asyncio.sleep(0.02)
                    assert not task.done()
                    runner.release.set()
                    await task
                finally:
                    # Never leave the worker blocked if an assertion fails.
                    runner.release.set()
                    if not task.done():
                        task.cancel()
                        try:
                            await asyncio.wait_for(task, timeout=10)
                        except asyncio.CancelledError:
                            pass

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
    provider_db, monkeypatch
):
    """Caller cancellation cannot abandon an admitted executor reservation."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
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
                try:
                    started = await asyncio.to_thread(runner.started.wait, 30)
                    if not started and refresh_task.done():
                        # Surface an admission/runtime exception rather than
                        # disguising it as a slow transport start.
                        await refresh_task
                    assert started
                    refresh_task.cancel()
                    await asyncio.sleep(0.02)
                    assert not refresh_task.done()
                    refresh_task.cancel()
                    await asyncio.sleep(0.02)
                    assert not refresh_task.done()
                    runner.release.set()
                    # Let CancelledError cross session.begin so its real
                    # rollback path runs; catching it here would commit this UOW.
                    await refresh_task
                finally:
                    # Never leave the worker blocked if an assertion fails.
                    runner.release.set()
                    if not refresh_task.done():
                        refresh_task.cancel()
                        try:
                            await asyncio.wait_for(refresh_task, timeout=10)
                        except asyncio.CancelledError:
                            pass
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
    provider_db, monkeypatch
):
    """One durable request unit admits one concurrent caller and survives reopen."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
    )
    # Match normal application startup: finish canonical registry seeding
    # before concurrent requests share this fresh test schema. Otherwise both
    # requests race to insert the same default DataSource rows, obscuring the
    # quota-admission concurrency contract this test is intended to exercise.
    async with provider_db() as startup_session:
        async with startup_session.begin():
            await seed_provider_runtime(startup_session)
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
    assert len(denied) == 1, [
        (
            type(item).__name__,
            str(getattr(item, "orig", item)),
            getattr(item, "statement", None),
        )
        for item in outcomes
    ]
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


async def _attempt_counts(session: AsyncSession, case) -> tuple[int, int, int]:
    request_logs = await session.scalar(
        select(func.count())
        .select_from(ProviderRequestLog)
        .where(
            ProviderRequestLog.data_source_id == case.source_id,
            ProviderRequestLog.operation == case.operation,
        )
    )
    quota_windows = await session.scalar(
        select(func.count())
        .select_from(ProviderQuotaWindow)
        .where(
            ProviderQuotaWindow.data_source_id == case.source_id,
            ProviderQuotaWindow.dimension == "requests_per_minute",
        )
    )
    reservation_count = await session.run_sync(
        lambda sync_session: sync_session.execute(
            select(func.count())
            .select_from(quota_coordinator._reservations)
            .where(
                quota_coordinator._reservations.c.provider_name == case.provider_name,
                quota_coordinator._reservations.c.operation == case.operation,
            )
        ).scalar_one()
    )
    return int(request_logs or 0), int(quota_windows or 0), int(reservation_count or 0)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "denial",
    (
        "missing_commitment",
        "expired_commitment",
        "proposed_nonzero_commitment",
        "trial_commitment",
        "disabled_capability_policy",
        "exact_operation_hold",
        "wildcard_operation_hold",
        "malformed_operation_hold",
        "shared_provider_circuit",
        "account_usage_bootstrap_is_not_holdings_admission",
    ),
)
async def test_real_refresh_denials_have_zero_dispatch_and_unavailable_without_prior_data(
    denial, provider_db, monkeypatch
):
    """Refresh entry persists truthful unavailability without partial admission."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
    )
    monkeypatch.setattr(settings, "PROVIDER_FREE_ONLY_CHECKPOINT", True)
    case, profile_id = await _create_committed_fixture(
        provider_db, monkeypatch, limit=5, with_profile=True
    )
    runner = _TransportRunner()
    _use_mocktransport(monkeypatch, runner)
    quota_coordinator.ensure_provider_quota_coordinator(require_persistent_coordinator=True)

    async with provider_db() as setup:
        commitment = await setup.scalar(
            select(ProviderRecurringCostCommitment).where(
                ProviderRecurringCostCommitment.data_source_id == case.source_id
            )
        )
        policy = await setup.scalar(
            select(ProviderPolicy).where(
                ProviderPolicy.data_source_id == case.source_id,
                ProviderPolicy.capability == ProviderCapability.ETF_HOLDINGS,
            )
        )
        entitlement = await setup.scalar(
            select(ProviderEntitlement).where(
                ProviderEntitlement.data_source_id == case.source_id,
                ProviderEntitlement.capability == ProviderCapability.ETF_HOLDINGS,
            )
        )
        health = await setup.scalar(
            select(ProviderHealthState).where(
                ProviderHealthState.data_source_id == case.source_id,
                ProviderHealthState.capability == ProviderCapability.ETF_HOLDINGS,
            )
        )
        assert commitment is not None and policy is not None

        if denial == "missing_commitment":
            await setup.delete(commitment)
        elif denial == "expired_commitment":
            commitment.ends_at = datetime.now(UTC) - timedelta(seconds=1)
        elif denial == "proposed_nonzero_commitment":
            # Synthetic-only fixture values exercise the shared aggregate
            # ceiling; they do not describe or price any real publisher.
            commitment.state = "proposed"
            commitment.amount = Decimal("0.0100")
            commitment.monthly_equivalent = Decimal("0.0100")
        elif denial == "trial_commitment":
            commitment.state = "trial"
        elif denial == "disabled_capability_policy":
            policy.is_enabled = False
        elif denial == "shared_provider_circuit":
            assert health is not None
            health.circuit_open_until = datetime.now(UTC) + timedelta(minutes=5)
        elif denial == "account_usage_bootstrap_is_not_holdings_admission":
            assert entitlement is not None
            entitlement.configured_plan = "unreviewed"
            policy.quota_contract = {
                **(policy.quota_contract or {}),
                "account_usage_bootstrap": {
                    "enabled": True,
                    "source": "test fixture only",
                    "reconciled_dimensions": ["requests_per_minute"],
                },
            }
            assert not policy_allows_account_usage_bootstrap(policy, "fetch_etf_holdings_latest")
        elif denial in {
            "exact_operation_hold",
            "wildcard_operation_hold",
            "malformed_operation_hold",
        }:
            if denial == "exact_operation_hold":
                configured_holds = {case.operation: "synthetic exact hold"}
                expected_hold_reason = "synthetic exact hold"
            elif denial == "wildcard_operation_hold":
                configured_holds = {"*": "synthetic wildcard hold"}
                expected_hold_reason = "synthetic wildcard hold"
            else:
                configured_holds = {case.operation: ""}
                expected_hold_reason = "checkpoint operation hold configuration is invalid"
            monkeypatch.setattr(
                settings,
                "PROVIDER_CHECKPOINT_OPERATION_HOLDS",
                {case.provider_name: configured_holds},
            )
            assert (
                provider_checkpoint_operation_hold_reason(case.provider_name, case.operation)
                == expected_hold_reason
            )
        await setup.commit()

    before = (0, 0, 0)
    async with provider_db() as session:
        async with session.begin():
            profile = await _load_profile(session, profile_id)
            if denial in {
                "exact_operation_hold",
                "wildcard_operation_hold",
                "malformed_operation_hold",
                "shared_provider_circuit",
                "account_usage_bootstrap_is_not_holdings_admission",
            }:
                with pytest.raises(ProviderNoDataError) as raised:
                    await refresh._refresh_adapter_route(session, profile)
                assert str(raised.value).startswith("No currently-supported providers")
            else:
                with pytest.raises(ETFHoldingsRouteHeldError) as raised:
                    await refresh._refresh_adapter_route(session, profile)
                if denial == "disabled_capability_policy":
                    assert str(raised.value) == "ETF publisher capability is not explicitly enabled"
                else:
                    assert str(raised.value) == (
                        "ETF publisher lacks an active verified-free shared recurring-cost commitment"
                    )
            await refresh._record_failure(session, profile, raised.value)
            state = await session.scalar(
                select(ETFHoldingsAdapterState).where(
                    ETFHoldingsAdapterState.etf_profile_id == profile.id,
                    ETFHoldingsAdapterState.adapter_key == profile.adapter_key,
                )
            )
            assert state is not None and state.failure_reason == str(raised.value)
            capability = evaluate_capability(profile, None, state)
            assert capability.availability == "unavailable"
            assert not capability.displayable_last_known
            before = await _attempt_counts(session, case)

    assert runner.calls == []
    assert before == (0, 0, 0)

    # The over-ceiling setup exists only in this synthetic test row. Restore
    # that owned row so it cannot influence a later fixture in the shared DB.
    if denial == "proposed_nonzero_commitment":
        async with provider_db() as cleanup:
            async with cleanup.begin():
                commitment = await cleanup.scalar(
                    select(ProviderRecurringCostCommitment).where(
                        ProviderRecurringCostCommitment.data_source_id == case.source_id
                    )
                )
                assert commitment is not None
                commitment.state = "cancelled"
                commitment.amount = Decimal("0")
                commitment.monthly_equivalent = Decimal("0")


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("has_prior_snapshot", (False, True))
async def test_shared_provider_circuit_denial_preserves_truthful_consumer_outcome(
    has_prior_snapshot, provider_db, monkeypatch
):
    """An open shared circuit yields degraded last-known or unavailable, never current."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
    )
    case, profile_id = await _create_committed_fixture(
        provider_db, monkeypatch, limit=5, with_profile=True
    )
    runner = _TransportRunner()
    _use_mocktransport(monkeypatch, runner)
    quota_coordinator.ensure_provider_quota_coordinator(require_persistent_coordinator=True)

    if has_prior_snapshot:
        async with provider_db() as session:
            async with session.begin():
                profile = await _load_profile(session, profile_id)
                runner.body = f"Fund Ticker,{case.instrument_symbol}\n" "Symbol,Weight\nAAA,1.0\n"
                snapshot = await refresh._refresh_adapter_route(session, profile)
                await refresh._record_success(session, profile, snapshot=snapshot)
        runner.calls.clear()

    async with provider_db() as setup:
        health = await setup.scalar(
            select(ProviderHealthState).where(
                ProviderHealthState.data_source_id == case.source_id,
                ProviderHealthState.capability == ProviderCapability.ETF_HOLDINGS,
            )
        )
        assert health is not None
        health.circuit_open_until = datetime.now(UTC) + timedelta(minutes=5)
        await setup.commit()

    async with provider_db() as session:
        before = await _attempt_counts(session, case)

    # Exercise the production worker/canary entry point: it owns failure-state
    # persistence and the diagnostic observation. The caller commits its
    # returned operational outcome, just as the scheduled task does.
    async with provider_db() as session:
        summary = await refresh.run_etf_holdings_capability_canaries(
            session,
            symbols=[case.instrument_symbol],
            max_symbols=1,
            timeout_seconds=5,
        )
        assert summary["failed"] == 1
        assert summary["reports"][0]["status"] == "failure"
        await session.commit()

    # Reopen and use the actual consumer read services; do not synthesize the
    # degraded/unavailable status from an in-memory failure helper.
    async with provider_db() as reopened:
        capability = await holdings_capability_for_symbol(reopened, case.instrument_symbol)
        history = await load_canary_history(reopened, profile_id)
        assert history
        latest_observation = history[-1]
        expected_availability = "degraded" if has_prior_snapshot else "unavailable"
        assert capability["availability"] == expected_availability
        assert latest_observation["availability"] == expected_availability
        assert capability["displayable_last_known"] is has_prior_snapshot
        assert not capability["usable_for_current_analysis"]
        persisted_snapshot = await reopened.scalar(
            select(ETFHoldingsSnapshot).where(ETFHoldingsSnapshot.etf_profile_id == profile_id)
        )
        if has_prior_snapshot:
            assert persisted_snapshot is not None
        else:
            assert persisted_snapshot is None
        after = await _attempt_counts(reopened, case)

    assert runner.calls == []
    assert after == before
    assert after[0] == (1 if has_prior_snapshot else 0)
    assert after[2] == (1 if has_prior_snapshot else 0)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_other_account_nonzero_commitment_denies_zero_cost_etf_route_under_shared_budget(
    provider_db, monkeypatch
):
    """A second account's synthetic cost cannot bypass the shared monthly ceiling."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
    )
    case, profile_id = await _create_committed_fixture(
        provider_db, monkeypatch, limit=5, with_profile=True
    )
    runner = _TransportRunner()
    _use_mocktransport(monkeypatch, runner)
    quota_coordinator.ensure_provider_quota_coordinator(require_persistent_coordinator=True)
    other_source_name = f"etf-budget-fixture-{uuid4().hex[:12]}"
    other_scope = f"synthetic-other-account-{uuid4().hex}"
    other_source_id = None

    async with provider_db() as setup:
        budget = await setup.get(ProviderRecurringCostBudget, 1)
        assert budget is not None
        assert Decimal(budget.monthly_ceiling) == Decimal("0")
        other_source = DataSource(
            name=other_source_name,
            description="Synthetic test-only budget fixture; not a real publisher.",
            config={"test_fixture_only": True},
        )
        setup.add(other_source)
        await setup.flush()
        other_source_id = other_source.id
        setup.add(
            ProviderRecurringCostCommitment(
                data_source_id=other_source.id,
                environment=settings.APP_ENV.strip().lower(),
                billing_account_scope_digest=hashlib.sha256(
                    other_scope.encode("utf-8")
                ).hexdigest(),
                configured_plan="synthetic-test-only",
                state="active",
                amount=Decimal("0.0100"),
                currency=budget.currency,
                interval_unit="month",
                interval_count=1,
                monthly_equivalent=Decimal("0.0100"),
                post_trial_amount=None,
                effective_at=datetime.now(UTC),
                ends_at=None,
                evidence_source="synthetic test fixture only",
                evidence_version="not-publisher-evidence-v1",
                evidence_observed_at=datetime.now(UTC),
                revision=1,
            )
        )
        await setup.commit()

    try:
        async with provider_db() as session:
            decision = await session.run_sync(provider_recurring_cost_status)
            assert not decision.allowed
            assert decision.reason_code == "monthly_ceiling_exceeded"
            assert decision.monthly_ceiling == Decimal("0")
            assert decision.committed_monthly == Decimal("0.0100")
        async with provider_db() as session:
            async with session.begin():
                profile = await _load_profile(session, profile_id)
                with pytest.raises(ETFHoldingsRouteHeldError) as raised:
                    await refresh._refresh_adapter_route(session, profile)
                assert str(raised.value) == (
                    "ETF publisher lacks an active verified-free shared recurring-cost commitment"
                )
                own_commitment = await session.scalar(
                    select(ProviderRecurringCostCommitment).where(
                        ProviderRecurringCostCommitment.data_source_id == case.source_id
                    )
                )
                assert own_commitment is not None
                assert own_commitment.state == "active"
                assert own_commitment.amount == Decimal("0.0000")
                assert own_commitment.monthly_equivalent == Decimal("0.0000")
                assert await _attempt_counts(session, case) == (0, 0, 0)
        assert runner.calls == []
    finally:
        if other_source_id is not None:
            async with provider_db() as cleanup:
                async with cleanup.begin():
                    synthetic_commitment = await cleanup.scalar(
                        select(ProviderRecurringCostCommitment).where(
                            ProviderRecurringCostCommitment.data_source_id == other_source_id
                        )
                    )
                    if synthetic_commitment is not None:
                        await cleanup.delete(synthetic_commitment)
                    synthetic_source = await cleanup.get(DataSource, other_source_id)
                    if synthetic_source is not None:
                        await cleanup.delete(synthetic_source)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discovery_and_sec_entry_points_cannot_inherit_latest_refresh_binding(
    provider_db, monkeypatch
):
    """Unreviewed discovery/SEC paths cannot borrow an admitted latest operation."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
    )
    case, profile_id = await _create_committed_fixture(
        provider_db,
        monkeypatch,
        limit=5,
        with_profile=True,
        reviewed_hosts=["publisher.example", "data.sec.gov", "www.sec.gov"],
    )
    runner = _TransportRunner()
    _use_mocktransport(monkeypatch, runner)
    quota_coordinator.ensure_provider_quota_coordinator(require_persistent_coordinator=True)
    source_url = "https://publisher.example/discovery.csv"

    async with provider_db() as session:
        async with session.begin():
            profile = await _load_profile(session, profile_id)
            with bind_etf_holdings_request_context(
                db=session,
                adapter=case.adapter,
                profile_id=profile_id,
                instrument_id=case.instrument_id,
                provider_symbol=case.instrument_symbol,
                operation="fetch_etf_holdings_latest",
            ):
                with pytest.raises(
                    ETFHoldingsRouteHeldError,
                    match="issuer discovery cannot reuse an ambient",
                ):
                    await refresh.discover_etf_profiles_from_issuer_feed(
                        session,
                        adapter_key="synthetic_csv_fixture",
                        source_url=source_url,
                    )
                with pytest.raises(
                    ETFHoldingsRouteHeldError,
                    match="fund-ticker discovery cannot reuse an ambient",
                ):
                    await refresh.discover_etf_profiles_from_sec_fund_tickers(
                        session,
                        source_url=source_url,
                    )
                with pytest.raises(
                    ETFHoldingsRouteHeldError,
                    match="fund-ticker enrichment cannot reuse an ambient",
                ):
                    await refresh.enrich_etf_profile_from_sec_fund_tickers(
                        session,
                        profile=profile,
                        source_url=source_url,
                    )

                # SEC N-PORT/legacy fallback and a real requests-based issuer
                # adapter remain held at their own transports; the ambient
                # latest binding cannot turn either into an admitted attempt.
                from app.services import etf_holdings_edgar as edgar

                with pytest.raises(
                    ETFHoldingsRouteHeldError,
                    match="explicit committed ETF request identity",
                ):
                    await edgar.discover_holdings_filings(
                        cik="0000000001",
                        forms={"NPORT-P"},
                        max_filings=1,
                    )
                # A different native adapter cannot borrow the currently
                # bound synthetic fixture's shared-admission identity.
                legacy_adapter = get_holdings_adapter("cohen_steers")
                assert legacy_adapter is not None
                with pytest.raises(
                    ETFHoldingsRouteHeldError,
                    match="does not match the bound shared-admission context",
                ):
                    await legacy_adapter.fetch_latest(
                        symbol=case.instrument_symbol,
                        issuer_product_id="synthetic-test-fund-id",
                    )

                profile.sec_cik = "0000000001"
                await session.flush()
                sec_fallback = await refresh._bootstrap_from_sec_filings(
                    session,
                    profile=profile,
                )
                assert sec_fallback is not None
                assert not sec_fallback.refresh_succeeded
            assert runner.calls == []
            assert await _attempt_counts(session, case) == (0, 0, 0)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sec_invalid_http_200_is_failed_and_measured_before_sticky_denial(
    provider_db, monkeypatch
):
    """A bounded but parseable SEC body cannot be logged as Provider success."""

    from app.services import etf_holdings_edgar as edgar

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
    )
    operation = "fetch_etf_holdings_sec_submissions"
    async with provider_db() as setup:
        async with setup.begin():
            case = await _seed_reviewed_fixture(
                setup,
                limit=4,
                monkeypatch=monkeypatch,
                reviewed_hosts=["data.sec.gov"],
                operation=operation,
                provider_name_override="edgar",
                instrument_symbol_override="IWM",
                quota_scope_override="ip",
            )
            instrument = await setup.get(Instrument, case.instrument_id)
            assert instrument is not None
            profile = ETFProfile(
                instrument_id=instrument.id,
                instrument=instrument,
                adapter_key="ishares",
                sec_cik="0001100663",
                sec_series_id="S000004344",
                sec_class_id="C000012074",
                provider_aliases={"holdings_source_provider": "ishares"},
            )
            setup.add(profile)
            await setup.flush()
            profile_id = profile.id

    valid_partial_json = (
        b'{"filings":{"recent":{"form":[],"accessionNumber":[],"filingDate":[],'
        b'"reportDate":[],"acceptanceDateTime":[],"primaryDocument":[]},"files":[]}}'
    )
    invalid_gzip_body = gzip.compress(valid_partial_json, mtime=0) + gzip.compress(
        b'{"extra":"second member"}', mtime=0
    )

    class CappedSECTransport:
        def __init__(self):
            self.calls: list[str] = []

        def factory(self):
            return httpx.MockTransport(self.handle)

        def handle(self, request):
            self.calls.append(str(request.url))
            return httpx.Response(
                200,
                headers={
                    "content-type": "application/json",
                    "content-encoding": "gzip",
                },
                stream=httpx.ByteStream(invalid_gzip_body),
                request=request,
            )

    runner = CappedSECTransport()
    _use_mocktransport(monkeypatch, runner)
    quota_coordinator.ensure_provider_quota_coordinator(require_persistent_coordinator=True)
    first_url = "https://data.sec.gov/submissions/CIK0001100663.json"
    second_url = "https://data.sec.gov/Archives/edgar/data/1100663/candidate.xml"

    async with provider_db() as session:
        profile = await _load_profile(session, profile_id)
        request_identity = await edgar._resolve_request_identity(
            db=session,
            profile=profile,
        )

        async def request_candidates():
            with pytest.raises(ETFHoldingsRouteHeldError, match="concatenated"):
                await edgar._sec_get(
                    request_identity,
                    operation=operation,
                    url=first_url,
                )
            with pytest.raises(ETFHoldingsRouteHeldError, match="terminal response"):
                await edgar._sec_get(
                    request_identity,
                    operation=operation,
                    url=second_url,
                )

        await edgar._run_in_sec_fund_scope(request_candidates)

    assert runner.calls == [first_url]
    async with provider_db() as readback:
        row = await _assert_one_settled_attempt(
            readback,
            case,
            expected_success=False,
            expected_http_requests=1,
        )
        assert row.error_type == "ETFHoldingsRouteHeldError"
        assert "concatenated" in (row.error_message or "")
        assert row.response_bytes == len(valid_partial_json)
        assert row.response_items == 0
        # The bounded document may be retained as failed-attempt evidence, but
        # must never be reported as a successful response or current support.
        assert row.response_payloads == [
            {
                "filings": {
                    "recent": {
                        "form": [],
                        "accessionNumber": [],
                        "filingDate": [],
                        "reportDate": [],
                        "acceptanceDateTime": [],
                        "primaryDocument": [],
                    },
                    "files": [],
                }
            }
        ]

        health = await readback.scalar(
            select(ProviderHealthState).where(
                ProviderHealthState.data_source_id == case.source_id,
                ProviderHealthState.capability == ProviderCapability.ETF_HOLDINGS,
            )
        )
        assert health is not None
        assert health.failure_streak == 1
        assert health.last_failure_at is not None
        assert health.last_success_at is None
        assert health.ewma_success_rate < Decimal("1")

        support = await readback.scalar(
            select(InstrumentProviderCapabilityStatus).where(
                InstrumentProviderCapabilityStatus.instrument_id == case.instrument_id,
                InstrumentProviderCapabilityStatus.data_source_id == case.source_id,
                InstrumentProviderCapabilityStatus.capability == ProviderCapability.ETF_HOLDINGS,
            )
        )
        assert support is None

        assert await _attempt_counts(readback, case) == (1, 1, 1)
        windows = list(
            (
                await readback.scalars(
                    select(ProviderQuotaWindow).where(
                        ProviderQuotaWindow.data_source_id == case.source_id,
                        ProviderQuotaWindow.dimension == "requests_per_minute",
                    )
                )
            ).all()
        )
        _assert_second_bucket_contract(windows, consumed_units=1, reserved_units=0)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario",
    ["wrong_fund_then_match", "cross_session_job_link", "no_match", "real_failure"],
)
async def test_initial_sec_qualification_is_one_shot_and_leaves_policy_disabled(
    provider_db, monkeypatch, scenario
):
    """Qualification links child-session logs without deadlocking the parent job transaction."""

    from app.models.etf_holdings import ETFHoldingsBackfillFiling, ETFHoldingsBackfillJob
    from app.services import etf_holdings_edgar as edgar

    monkeypatch.setattr(settings, "PROVIDER_ROUTING_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
    )
    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_ACCOUNT_SCOPES",
        {"edgar:ip": "synthetic-initial-qualification-account"},
    )
    operations = {
        "fetch_etf_holdings_sec_submissions",
        "fetch_etf_holdings_sec_submissions_file",
        "fetch_etf_holdings_sec_filing",
    }
    operation_reviews = {
        operation: {
            "evidence_source": "test-fixture:etf:offline-mocktransport",
            "evidence_version": "synthetic-v1",
            "reviewed_at": datetime.now(UTC).date().isoformat(),
        }
        for operation in operations
    }
    submissions_url = "https://data.sec.gov/submissions/CIK0001100663.json"
    wrong_accession = "000110066326000002"
    wrong_filing_url = (
        "https://www.sec.gov/Archives/edgar/data/1100663/" f"{wrong_accession}/wrong_doc.xml"
    )
    matching_accession = "000110066326000001"
    filing_url = (
        "https://www.sec.gov/Archives/edgar/data/1100663/" f"{matching_accession}/primary_doc.xml"
    )
    if scenario == "wrong_fund_then_match":
        recent = {
            "form": ["NPORT-P", "NPORT-P"],
            "accessionNumber": [wrong_accession, matching_accession],
            "filingDate": ["2026-10-02", "2026-10-01"],
            "reportDate": ["2026-09-30", "2026-09-30"],
            "acceptanceDateTime": [
                "2026-10-02T12:00:00.000Z",
                "2026-10-01T12:00:00.000Z",
            ],
            "primaryDocument": ["wrong_doc.xml", "primary_doc.xml"],
        }
    elif scenario == "no_match":
        recent = {
            "form": ["NPORT-P"],
            "accessionNumber": [wrong_accession],
            "filingDate": ["2026-10-02"],
            "reportDate": ["2026-09-30"],
            "acceptanceDateTime": ["2026-10-02T12:00:00.000Z"],
            "primaryDocument": ["wrong_doc.xml"],
        }
    else:
        recent = {
            "form": ["NPORT-P"],
            "accessionNumber": [matching_accession],
            "filingDate": ["2026-10-01"],
            "reportDate": ["2026-09-30"],
            "acceptanceDateTime": ["2026-10-01T12:00:00.000Z"],
            "primaryDocument": ["primary_doc.xml"],
        }
    submissions = {
        "filings": {
            "recent": recent,
            "files": [],
        }
    }
    wrong_filing_xml = """<edgarSubmission><formData><genInfo>
      <seriesId>S000009999</seriesId><classId>C000099999</classId>
      <repPdDate>2026-09-30</repPdDate></genInfo><invstOrSecs>
      <invstOrSec><name>Non-target issuer</name><ticker>ZZZ</ticker>
      <pctVal>1</pctVal><assetCat>EC</assetCat></invstOrSec>
      </invstOrSecs></formData></edgarSubmission>"""
    filing_xml = """<edgarSubmission><formData><genInfo>
      <seriesId>S000004344</seriesId><classId>C000012074</classId>
      <repPdDate>2026-09-30</repPdDate></genInfo><invstOrSecs>
      <invstOrSec><name>Example Issuer</name><ticker>AAA</ticker>
      <pctVal>1</pctVal><assetCat>EC</assetCat></invstOrSec>
      </invstOrSecs></formData></edgarSubmission>"""

    class InitialQualificationTransport:
        def __init__(self):
            self.calls = []

        def factory(self):
            return httpx.MockTransport(self.handle)

        def handle(self, request):
            url = str(request.url)
            self.calls.append(url)
            if url == submissions_url:
                body = json.dumps(submissions).encode()
                content_type = "application/json"
                status_code = 200
            elif url == wrong_filing_url:
                body = wrong_filing_xml.encode()
                content_type = "application/xml"
                status_code = 200
            elif url == filing_url:
                body = (
                    b"SEC filing unavailable" if scenario == "real_failure" else filing_xml.encode()
                )
                content_type = "application/xml"
                status_code = 503 if scenario == "real_failure" else 200
            else:
                raise AssertionError(f"Unexpected offline SEC URL: {url}")
            return httpx.Response(
                status_code,
                headers={"content-type": content_type},
                stream=httpx.ByteStream(body),
                request=request,
            )

    runner = InitialQualificationTransport()
    _use_mocktransport(monkeypatch, runner)
    quota_coordinator.ensure_provider_quota_coordinator(require_persistent_coordinator=True)

    async with provider_db() as setup:
        async with setup.begin():
            case = await _seed_reviewed_fixture(
                setup,
                limit=9,
                monkeypatch=monkeypatch,
                reviewed_hosts=["data.sec.gov", "www.sec.gov"],
                operation="fetch_etf_holdings_sec_submissions",
                provider_name_override="edgar",
                instrument_symbol_override="IWM",
                quota_scope_override="ip",
            )
            source = await setup.get(DataSource, case.source_id)
            policy = await setup.scalar(
                select(ProviderPolicy).where(
                    ProviderPolicy.data_source_id == case.source_id,
                    ProviderPolicy.capability == ProviderCapability.ETF_HOLDINGS,
                )
            )
            entitlement = await setup.scalar(
                select(ProviderEntitlement).where(
                    ProviderEntitlement.data_source_id == case.source_id,
                    ProviderEntitlement.capability == ProviderCapability.ETF_HOLDINGS,
                )
            )
            instrument = await setup.get(Instrument, case.instrument_id)
            assert source is not None and policy is not None and entitlement is not None
            assert instrument is not None
            source_config = dict(source.config)
            source_config["usage_tracking"] = {"operation_costs": dict.fromkeys(operations, 1)}
            source_config["etf_holdings_review"] = {
                "https_hosts": ["data.sec.gov", "www.sec.gov"],
                "account_scope": case.account_scope,
                "operations": operation_reviews,
            }
            source.config = source_config
            policy.is_enabled = False
            policy.quota_contract = {
                **dict(policy.quota_contract),
                "operation_costs": dict.fromkeys(operations, 1),
            }
            entitlement.live_probe_status = "not_run"
            profile = ETFProfile(
                instrument_id=instrument.id,
                instrument=instrument,
                adapter_key="edgar_sec_holdings",
                sec_cik="0001100663",
                sec_series_id="S000004344",
                sec_class_id="C000012074",
                provider_aliases={"holdings_source_provider": "edgar"},
            )
            setup.add(profile)
            await setup.flush()
            profile_id = profile.id

    async with provider_db() as ordinary:
        profile = await _load_profile(ordinary, profile_id)
        request_identity = await edgar._resolve_request_identity(
            db=ordinary,
            profile=profile,
        )
        with pytest.raises(ETFHoldingsRouteHeldError, match="not explicitly enabled"):
            await edgar._run_in_sec_fund_scope(
                lambda: edgar._sec_get(
                    request_identity,
                    operation="fetch_etf_holdings_sec_submissions",
                    url=submissions_url,
                )
            )
    assert runner.calls == []
    quota_engine = quota_coordinator._engine_for(quota_coordinator._engine_url())
    with quota_engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count())
                .select_from(quota_coordinator._reservations)
                .where(
                    quota_coordinator._reservations.c.provider_name == "edgar",
                    quota_coordinator._reservations.c.account_scope == case.account_scope,
                )
            ).scalar_one()
            == 0
        )

    async def qualify_once():
        async with provider_db() as invocation:
            return await edgar.qualify_sec_nport_fund(
                invocation,
                profile_id=profile_id,
                requested_by_user_id=None,
            )

    outcomes = await asyncio.gather(qualify_once(), qualify_once(), return_exceptions=True)
    summaries = [value for value in outcomes if isinstance(value, dict)]
    concurrent_denials = [
        value for value in outcomes if isinstance(value, ETFHoldingsRouteHeldError)
    ]
    assert len(summaries) == 1, outcomes
    assert len(concurrent_denials) == 1, outcomes
    summary = summaries[0]
    qualification_succeeded = scenario in {
        "wrong_fund_then_match",
        "cross_session_job_link",
    }
    if qualification_succeeded:
        assert summary["status"] == "completed"
        assert summary["ingested"] == 1
        if scenario == "wrong_fund_then_match":
            assert len(summary["expected_non_target_fund_discards"]) == 1
        expected_calls = [submissions_url]
        if scenario == "wrong_fund_then_match":
            expected_calls.append(wrong_filing_url)
        expected_calls.append(filing_url)
        assert runner.calls == expected_calls
    elif scenario == "no_match":
        assert summary["status"] == "partial"
        assert summary["ingested"] == 0
        assert len(summary["expected_non_target_fund_discards"]) == 1
        assert runner.calls == [submissions_url, wrong_filing_url]
    else:
        assert summary["status"] == "failed"
        assert summary["ingested"] == 0
        assert runner.calls == [submissions_url, filing_url]

    async with provider_db() as readback:
        policy = await readback.scalar(
            select(ProviderPolicy).where(
                ProviderPolicy.data_source_id == case.source_id,
                ProviderPolicy.capability == ProviderCapability.ETF_HOLDINGS,
            )
        )
        entitlement = await readback.scalar(
            select(ProviderEntitlement).where(
                ProviderEntitlement.data_source_id == case.source_id,
                ProviderEntitlement.capability == ProviderCapability.ETF_HOLDINGS,
            )
        )
        attempt = await readback.scalar(
            select(ETFHoldingsBackfillJob).where(
                ETFHoldingsBackfillJob.etf_profile_id == profile_id,
                ETFHoldingsBackfillJob.job_type == edgar.SEC_INITIAL_QUALIFICATION_JOB_TYPE,
            )
        )
        snapshots = list(
            (
                await readback.scalars(
                    select(ETFHoldingsSnapshot).where(
                        ETFHoldingsSnapshot.etf_profile_id == profile_id
                    )
                )
            ).all()
        )
        artifacts = list(
            (
                await readback.scalars(
                    select(ETFHoldingsRawArtifact).where(
                        ETFHoldingsRawArtifact.etf_profile_id == profile_id
                    )
                )
            ).all()
        )
        logs = list(
            (
                await readback.scalars(
                    select(ProviderRequestLog)
                    .where(ProviderRequestLog.data_source_id == case.source_id)
                    .order_by(ProviderRequestLog.id)
                )
            ).all()
        )
        assert policy is not None and not policy.is_enabled
        assert entitlement is not None
        assert attempt is not None
        assert len(logs) == len(runner.calls)
        if qualification_succeeded:
            assert entitlement.live_probe_status == "passed"
            assert attempt.status == "completed"
            assert len(snapshots) == 1
            snapshot = snapshots[0]
            assert snapshot.row_count == 1
            assert snapshot.known_at is not None
            assert snapshot.published_at is None
            artifact = next(
                item for item in artifacts if item.source_identifier == matching_accession
            )
            assert artifact.payload_text == filing_xml
            assert artifact.content_hash == _hash_payload(filing_xml)
            linked_request_ids = attempt.extra_data["qualification_request_log_ids"]
            assert len(linked_request_ids) == len(set(linked_request_ids)) == len(logs)
            assert set(linked_request_ids) == {row.id for row in logs}
            assert attempt.extra_data["qualification_snapshot_id"] == snapshot.id
            assert attempt.extra_data["qualification_raw_artifact_id"] == artifact.id
            discarded_row = await readback.scalar(
                select(ETFHoldingsBackfillFiling).where(
                    ETFHoldingsBackfillFiling.etf_profile_id == profile_id,
                    ETFHoldingsBackfillFiling.accession_number == wrong_accession,
                )
            )
            if scenario == "wrong_fund_then_match":
                assert discarded_row is not None and discarded_row.status == "skipped"
                assert (
                    discarded_row.extra_data["identity_validation"]["qualification_disposition"]
                    == "expected_non_target_fund_candidate"
                )
                discarded_artifact = next(
                    item for item in artifacts if item.source_identifier == wrong_accession
                )
                assert discarded_artifact.payload_text == wrong_filing_xml
                assert discarded_artifact.content_hash == _hash_payload(wrong_filing_xml)
            else:
                assert scenario == "cross_session_job_link"
                assert discarded_row is None
                assert all(item.source_identifier != wrong_accession for item in artifacts)
        else:
            assert entitlement.live_probe_status == "not_run"
            assert attempt.status in {"partial", "failed"}
            assert snapshots == []
            assert "qualification_outcome" in attempt.extra_data
            assert attempt.extra_data["qualification_outcome"]["status"] == "not_qualified"
        assert {row.operation for row in logs} == {
            "fetch_etf_holdings_sec_submissions",
            "fetch_etf_holdings_sec_filing",
        }
        assert all(row.http_requests == 1 for row in logs)
        if qualification_succeeded:
            assert all(row.success and row.settled_usage_units == Decimal("1.0000") for row in logs)

    with pytest.raises(ETFHoldingsRouteHeldError, match="already has a latched"):
        async with provider_db() as replay:
            await edgar.qualify_sec_nport_fund(
                replay,
                profile_id=profile_id,
                requested_by_user_id=None,
            )
    if qualification_succeeded:
        expected_calls = [submissions_url]
        if scenario == "wrong_fund_then_match":
            expected_calls.append(wrong_filing_url)
        expected_calls.append(filing_url)
        assert runner.calls == expected_calls
    with quota_engine.connect() as connection:
        reservations = (
            connection.execute(
                select(quota_coordinator._reservations).where(
                    quota_coordinator._reservations.c.provider_name == "edgar",
                    quota_coordinator._reservations.c.account_scope == case.account_scope,
                )
            )
            .mappings()
            .all()
        )
    assert len(reservations) == len(runner.calls)
    if qualification_succeeded:
        assert all(row["state"] == "settled" for row in reservations)
    assert all(row["reserved_units"] == 1 for row in reservations)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sec_discovery_uses_shared_per_hop_admission_and_rejects_wrong_cik(
    provider_db, monkeypatch, redis_url
):
    """Dedicated SEC discovery uses the shared ledger and binds every redirect hop."""

    import redis

    from app.services import etf_holdings_edgar as edgar

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
    )
    operation = "fetch_etf_holdings_sec_submissions"
    async with provider_db() as setup:
        async with setup.begin():
            case = await _seed_reviewed_fixture(
                setup,
                limit=4,
                monkeypatch=monkeypatch,
                reviewed_hosts=["data.sec.gov", "www.sec.gov"],
                operation=operation,
                provider_name_override="edgar",
                instrument_symbol_override="IWM",
                quota_scope_override="ip",
            )
            instrument = await setup.get(Instrument, case.instrument_id)
            assert instrument is not None
            profile = ETFProfile(
                instrument_id=instrument.id,
                instrument=instrument,
                adapter_key="ishares",
                sec_cik="0001100663",
                sec_series_id="S000004344",
                sec_class_id="C000012074",
                provider_aliases={"holdings_source_provider": "ishares"},
            )
            setup.add(profile)
            await setup.flush()
            profile_id = profile.id
    redis_client = redis.Redis.from_url(redis_url, socket_timeout=1)
    assert redis_client.ping()
    redis_client.close()
    quota_coordinator.ensure_provider_quota_coordinator(require_persistent_coordinator=True)

    class SECTransport:
        def __init__(self):
            self.calls = []

        def factory(self):
            return httpx.MockTransport(self.handle)

        def handle(self, request):
            self.calls.append(str(request.url))
            assert request.headers.get("user-agent") == settings.EDGAR_USER_AGENT
            if request.url.host == "data.sec.gov":
                return httpx.Response(
                    302,
                    headers={
                        "location": "https://www.sec.gov" + request.url.path,
                    },
                    stream=httpx.ByteStream(b""),
                    request=request,
                )
            return httpx.Response(
                200,
                stream=httpx.ByteStream(
                    b'{"filings":{"recent":{"form":[],"accessionNumber":[],'
                    b'"filingDate":[],"reportDate":[],"acceptanceDateTime":[],'
                    b'"primaryDocument":[]},"files":[]}}'
                ),
                request=request,
            )

    runner = SECTransport()
    _use_mocktransport(monkeypatch, runner)
    captured_bindings = []
    original_sec_get = edgar._sec_get

    async def capture_binding(*args, **kwargs):
        response = await original_sec_get(*args, **kwargs)
        captured_bindings.append(response.extensions["etf_holdings_request_binding"])
        return response

    monkeypatch.setattr(edgar, "_sec_get", capture_binding)
    async with provider_db() as session:
        async with session.begin():
            profile = await _load_profile(session, profile_id)
            request_identity = await edgar._resolve_request_identity(
                db=session,
                profile=profile,
            )
            filings = await edgar.discover_holdings_filings(
                cik=profile.sec_cik,
                forms={"NPORT-P"},
                request_identity=request_identity,
                max_filings=1,
            )
            assert filings == []
            assert runner.calls == [
                "https://data.sec.gov/submissions/CIK0001100663.json",
                "https://www.sec.gov/submissions/CIK0001100663.json",
            ]
            assert len(captured_bindings) == 1
            binding = captured_bindings[0]
            assert len(binding.request_log_ids) == 2
            assert [
                binding.request_urls_by_log_id[request_id] for request_id in binding.request_log_ids
            ] == runner.calls
            logs = list(
                (
                    await session.scalars(
                        select(ProviderRequestLog)
                        .where(
                            ProviderRequestLog.id.in_(binding.request_log_ids),
                            ProviderRequestLog.data_source_id == case.source_id,
                            ProviderRequestLog.operation == operation,
                        )
                        .order_by(ProviderRequestLog.id)
                    )
                ).all()
            )
            assert [row.id for row in logs] == binding.request_log_ids
            assert all(row.success and row.http_requests == 1 for row in logs)
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

            calls_before_mismatch = list(runner.calls)
            with pytest.raises(
                ETFHoldingsRouteHeldError, match="does not match the committed ETF CIK"
            ):
                await edgar._run_in_sec_fund_scope(
                    lambda: edgar._sec_get(
                        request_identity,
                        operation=operation,
                        url="https://data.sec.gov/submissions/CIK0000000001.json",
                    )
                )
            assert runner.calls == calls_before_mismatch
            assert (
                await session.scalar(
                    select(func.count(ProviderRequestLog.id)).where(
                        ProviderRequestLog.data_source_id == case.source_id,
                        ProviderRequestLog.operation == operation,
                    )
                )
                == 2
            )
    quota_engine = quota_coordinator._engine_for(quota_coordinator._engine_url())
    with quota_engine.connect() as connection:
        reservations = (
            connection.execute(
                select(quota_coordinator._reservations).where(
                    quota_coordinator._reservations.c.provider_name == "edgar"
                )
            )
            .mappings()
            .all()
        )
    assert len(reservations) == 2
    assert all(row["state"] == "settled" and row["reserved_units"] == 1 for row in reservations)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bootstrap_treats_held_optional_sec_enrichment_separately_from_issuer_route(
    provider_db, monkeypatch
):
    """A held optional SEC enrichment neither inherits nor blocks issuer fetch."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
    )
    case, profile_id = await _create_committed_fixture(
        provider_db,
        monkeypatch,
        limit=5,
        with_profile=True,
        reviewed_hosts=["publisher.example", "data.sec.gov", "www.sec.gov"],
    )
    runner = _TransportRunner()
    runner.body = f"Fund Ticker,{case.instrument_symbol}\n" "Symbol,Weight\nAAA,1.0\n"
    _use_mocktransport(monkeypatch, runner)
    quota_coordinator.ensure_provider_quota_coordinator(require_persistent_coordinator=True)

    async with provider_db() as session:
        async with session.begin():
            profile = await _load_profile(session, profile_id)
            with bind_etf_holdings_request_context(
                db=session,
                adapter=case.adapter,
                profile_id=profile_id,
                instrument_id=case.instrument_id,
                provider_symbol=case.instrument_symbol,
                operation="fetch_etf_holdings_latest",
            ):
                result = await refresh.bootstrap_etf_holdings_profile(
                    session,
                    symbol=case.instrument_symbol,
                    name=profile.instrument.name,
                )
            assert result.refresh_attempted
            assert result.refresh_succeeded
            assert runner.calls == [("GET", "https://publisher.example/holdings.csv")]

    async with provider_db() as reopened:
        capability = await holdings_capability_for_symbol(reopened, case.instrument_symbol)
        assert capability["availability"] == "current"
        assert capability["usable_for_current_analysis"]
        assert await _attempt_counts(reopened, case) == (1, 1, 1)
