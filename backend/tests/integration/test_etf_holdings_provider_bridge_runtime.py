"""Real shared Provider admission around offline ETF HTTPX attempts.

This module intentionally runs against TEST_DATABASE_URL (or the normal
integration Postgres fixture) and uses only HTTPX MockTransport. It never
contacts an issuer or provider.
"""

from __future__ import annotations

import asyncio
import base64
import gzip
import hashlib
import json
import threading
import time
import zipfile
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4
from xml.sax.saxutils import escape

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import event, func, insert, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.asset_class import AssetClass, InstrumentType
from app.models.data_source import DataSource
from app.models.etf_holdings import (
    ETFHolding,
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
from app.models.user import User
from app.services import etf_holdings_provider_bridge as bridge
from app.services import etf_holdings_refresh as refresh
from app.services import provider_quota_coordinator as quota_coordinator
from app.services.etf_holdings import (
    ETF_HOLDINGS_INTERNAL_PROVIDER,
    _hash_payload,
    holdings_capability_for_symbol,
)
from app.services.etf_holdings_adapters import (
    CanonicalHoldingRow,
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_admin_reparse_response_uses_fresh_eager_session_and_is_idempotent(
    provider_db, monkeypatch
):
    """The real HTTP response serializes rows after reparsing in a fresh AsyncSession."""

    from app.auth.jwt import create_access_token
    from app.database import get_db
    from app.main import app as api_app
    from app.models.etf_holdings import ETFHoldingsSnapshot
    from app.services import etf_holdings as etf_service

    suffix = uuid4().hex[:10].upper()
    symbol = f"ET{suffix}"
    constituent_symbol = f"R{suffix}"
    composition_date = date(2026, 3, 31)
    imported_at = datetime(2026, 10, 25, 18, 31, tzinfo=UTC)
    correction_at = datetime.now(UTC)
    accession = "0002071691-26-012507"
    filing_url = (
        "https://www.sec.gov/Archives/edgar/data/1100663/" "000207169126012507/primary_doc.xml"
    )
    raw_xml = (
        "<edgarSubmission><formData><genInfo>"
        "<repPdDate>2026-03-31</repPdDate>"
        "<seriesId>S000004344</seriesId><classId>C000012074</classId>"
        "</genInfo></formData></edgarSubmission>"
    )
    identity = {"series_id": "S000004344", "class_id": "C000012074"}
    legal_metadata = {
        "source_access": "sec_filing",
        "form": "NPORT-P",
        "fund_identity": identity,
    }
    monkeypatch.setattr(etf_service, "_now", lambda: correction_at)
    monkeypatch.setattr(
        etf_service,
        "parse_sec_nport_xml",
        lambda _raw: (
            composition_date,
            [
                CanonicalHoldingRow(
                    symbol=constituent_symbol,
                    name="Retained Filing Test Company",
                    cusip="123456789",
                    weight=Decimal("0.00648126"),
                    holding_type="common_stock",
                    row_type="security",
                    source_row_id="1",
                    extra_data={"assetCat": "EC"},
                )
            ],
        ),
    )

    async with provider_db() as seed:
        asset_class = AssetClass(name=f"ETF-reparse-{suffix}", description="test only")
        seed.add(asset_class)
        await seed.flush()
        etf_type = InstrumentType(
            asset_class_id=asset_class.id, name="ETF", description="test only"
        )
        stock_type = InstrumentType(
            asset_class_id=asset_class.id, name="Stock", description="test only"
        )
        seed.add_all([etf_type, stock_type])
        await seed.flush()
        etf_instrument = Instrument(
            instrument_type_id=etf_type.id,
            symbol=symbol,
            name="Retained Filing Test ETF",
            currency="USD",
            is_active=True,
        )
        constituent = Instrument(
            instrument_type_id=stock_type.id,
            symbol=constituent_symbol,
            name="Retained Filing Test Company",
            currency="USD",
            is_active=True,
        )
        seed.add_all([etf_instrument, constituent])
        await seed.flush()
        profile = ETFProfile(
            instrument_id=etf_instrument.id,
            sec_cik="0001100663",
            sec_series_id=identity["series_id"],
            sec_class_id=identity["class_id"],
            legal_metadata={"operator_context": "preserve during correction"},
        )
        admin = User(
            username=f"reparse-{suffix.lower()}",
            email=f"reparse-{suffix.lower()}@example.test",
            hashed_password="test-only-not-used",
            is_active=True,
            is_admin=True,
        )
        seed.add_all([profile, admin])
        await seed.flush()
        raw = ETFHoldingsRawArtifact(
            etf_profile_id=profile.id,
            source_kind="sec_nport_reconstructed_holdings",
            source_url=filing_url,
            source_identifier=accession,
            content_type="text/xml",
            content_hash=_hash_payload(raw_xml),
            composition_date=composition_date,
            as_of_date=composition_date,
            fetched_at=imported_at,
            parser_version="sec-nport-v1",
            payload_text=raw_xml,
            payload_json=None,
            legal_metadata=legal_metadata,
        )
        seed.add(raw)
        await seed.flush()
        original = ETFHoldingsSnapshot(
            etf_profile_id=profile.id,
            source_artifact_id=raw.id,
            composition_date=composition_date,
            as_of_date=composition_date,
            known_at=imported_at,
            published_at=None,
            provenance="sec_nport_reconstructed_holdings",
            source_provider="edgar",
            source_url=filing_url,
            source_identifier=accession,
            source_quality="filing_reconstructed_holdings",
            completeness_status="complete",
            row_count=1,
            resolved_count=1,
            unresolved_count=0,
            total_weight=Decimal("0.06481263"),
            parser_version="sec-nport-v1",
            snapshot_hash="original-version-hash",
            extra_data={"legal_metadata": {"operator_context": "preserve during correction"}},
        )
        seed.add(original)
        await seed.flush()
        seed.add(
            ETFHolding(
                snapshot_id=original.id,
                constituent_instrument_id=constituent.id,
                position=1,
                reported_symbol=constituent_symbol,
                reported_name="Retained Filing Test Company",
                cusip="123456789",
                weight=Decimal("0.06481263"),
                holding_type="common_stock",
                row_type="security",
                source_row_id="1",
                source_row_hash="original-row-hash",
                is_resolved=True,
            )
        )
        await seed.commit()
        profile_id = profile.id
        original_id = original.id
        raw_id = raw.id
        admin_id = admin.id
        original_hash = original.snapshot_hash

    request_sessions = []

    async def fresh_request_db():
        async with provider_db() as session:
            request_sessions.append(session)
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    prior_overrides = dict(api_app.dependency_overrides)
    api_app.dependency_overrides[get_db] = fresh_request_db
    token = create_access_token(admin_id)
    headers = {"Authorization": f"Bearer {token}"}
    transport = httpx.ASGITransport(app=api_app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://etf.test") as client:
            first = await client.post(
                f"/api/v1/etf-holdings/{symbol}/snapshots/{original_id}/reparse-sec-nport",
                headers=headers,
            )
            assert first.status_code == 200, first.text
            body = first.json()
            corrected_id = body["id"]
            assert corrected_id != original_id
            assert body["row_count"] == 1
            assert len(body["holdings"]) == 1
            assert body["holdings"][0]["reported_symbol"] == constituent_symbol
            assert body["holdings"][0]["constituent_symbol"] == constituent_symbol
            assert body["holdings"][0]["weight"] == "0.00648126"
            correction = body["extra_data"]["parser_correction"]
            assert correction["source_snapshot_id"] == original_id
            assert correction["raw_artifact_id"] == raw_id
            assert correction["source_snapshot_known_at"] == imported_at.isoformat()
            assert body["known_at"] == correction_at.isoformat().replace("+00:00", "Z")

            second = await client.post(
                f"/api/v1/etf-holdings/{symbol}/snapshots/{original_id}/reparse-sec-nport",
                headers=headers,
            )
            assert second.status_code == 200, second.text
            assert second.json()["id"] == corrected_id

            dates = await client.get(f"/api/v1/etf-holdings/{symbol}/dates", headers=headers)
            assert dates.status_code == 200, dates.text
            assert [row["snapshot_id"] for row in dates.json()[:2]] == [
                corrected_id,
                original_id,
            ]
    finally:
        api_app.dependency_overrides.clear()
        api_app.dependency_overrides.update(prior_overrides)

    assert len(request_sessions) == 3
    assert len({id(session) for session in request_sessions}) == 3
    async with provider_db() as readback:
        snapshots = (
            (
                await readback.execute(
                    select(ETFHoldingsSnapshot)
                    .options(
                        selectinload(ETFHoldingsSnapshot.rows).selectinload(
                            ETFHolding.constituent_instrument
                        )
                    )
                    .where(ETFHoldingsSnapshot.etf_profile_id == profile_id)
                    .order_by(ETFHoldingsSnapshot.id.asc())
                )
            )
            .scalars()
            .all()
        )
        assert [snapshot.id for snapshot in snapshots] == [original_id, corrected_id]
        assert snapshots[0].snapshot_hash == original_hash
        assert snapshots[0].known_at == imported_at
        assert snapshots[0].source_artifact_id == raw_id
        assert snapshots[0].rows[0].weight == Decimal("0.06481263")
        assert snapshots[1].rows[0].weight == Decimal("0.00648126")
        assert snapshots[1].rows[0].constituent_instrument.symbol == constituent_symbol
        assert snapshots[1].extra_data["parser_correction"]["source_snapshot_id"] == original_id
        assert snapshots[1].extra_data["parser_correction"]["raw_artifact_id"] == raw_id
        profile = await readback.get(ETFProfile, profile_id)
        assert profile.legal_metadata == {"operator_context": "preserve during correction"}
        retained_raw = await readback.get(ETFHoldingsRawArtifact, raw_id)
        assert retained_raw is not None
        assert retained_raw.fetched_at == imported_at
        assert retained_raw.content_hash == _hash_payload(raw_xml)
        assert retained_raw.payload_text == raw_xml
        assert retained_raw.source_identifier == accession
        assert retained_raw.source_url == filing_url


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


def _vaneck_initial_qualification_workbook(
    *, fund_title: str = "VanEck Oil Services ETF (OIH)"
) -> bytes:
    rows = [
        [f"As of {date.today():%m/%d/%Y}"],
        [fund_title],
        [
            "Number",
            "Ticker",
            "Holding Name",
            "Identifier (FIGI)",
            "Shares",
            "Asset Class",
            "Market Value (US$)",
            "% of Net Assets",
        ],
        ["1", "XOM", "Exxon Mobil Corporation", "BBG0000000001", "10", "Equity", "1000", "1.0%"],
    ]

    def cell_ref(column_index: int, row_index: int) -> str:
        column = ""
        value = column_index + 1
        while value:
            value, remainder = divmod(value - 1, 26)
            column = chr(ord("A") + remainder) + column
        return f"{column}{row_index}"

    sheet_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row):
            cells.append(
                f'<c r="{cell_ref(column_index, row_index)}" t="inlineStr">'
                f"<is><t>{escape(value)}</t></is></c>"
            )
        cell_xml = "".join(cells)
        sheet_rows.append(f'<row r="{row_index}">{cell_xml}</row>')
    worksheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(sheet_rows)}</sheetData>"
        "</worksheet>"
    )
    output = BytesIO()
    with zipfile.ZipFile(output, mode="w") as workbook:
        workbook.writestr("xl/worksheets/sheet1.xml", worksheet)
    return output.getvalue()


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

    # This compatibility regression covers the pre-request-driven dated route;
    # explicit request-driven ETF scope remains tested separately and stays
    # fail-closed for unsupported operations.
    monkeypatch.setattr(settings, "PROVIDER_ROUTING_ENABLED", True)
    monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", False)
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
    ("fund_title", "expected_status"),
    (
        ("VanEck Oil Services ETF (OIH)", "completed"),
        ("VanEck Semiconductor ETF (SMH)", "failed"),
    ),
)
async def test_vaneck_initial_qualification_uses_disabled_policy_and_durably_links_real_runtime_log(
    provider_db, monkeypatch, fund_title, expected_status
):
    """The real OIH qualifier crosses bridge pre-review and Provider using independent sessions."""

    from app.models.etf_holdings import ETFHoldingsBackfillJob
    from app.services import provider_runtime
    from app.services.etf_holdings_vaneck_qualification import (
        VANECK_OIH_INITIAL_QUALIFICATION_JOB_TYPE,
        VANECK_OIH_INITIAL_QUALIFICATION_OPERATION,
        VANECK_OIH_INITIAL_URL,
        VANECK_OIH_PRODUCT_SLUG,
        qualify_vaneck_oih_fund,
    )

    monkeypatch.setattr(settings, "PROVIDER_ROUTING_ENABLED", True)
    monkeypatch.setattr(settings, "ALLOW_PAID_PROVIDER_ROUTING", False)
    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
    )
    workbook = _vaneck_initial_qualification_workbook(fund_title=fund_title)

    class WorkbookTransport:
        def __init__(self):
            self.calls = []

        def factory(self):
            return httpx.MockTransport(self.handle)

        def handle(self, request):
            self.calls.append((request.method, str(request.url)))
            return httpx.Response(
                200,
                content=workbook,
                headers={
                    "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                },
                request=request,
            )

    runner = WorkbookTransport()
    _use_mocktransport(monkeypatch, runner)
    suffix = uuid4().hex[:10]
    async with provider_db() as setup:
        async with setup.begin():
            case = await _seed_reviewed_fixture(
                setup,
                limit=3,
                monkeypatch=monkeypatch,
                reviewed_hosts=["www.vaneck.com"],
                operation=VANECK_OIH_INITIAL_QUALIFICATION_OPERATION,
                provider_name_override="vaneck",
                instrument_symbol_override="OIH",
            )
            instrument = await setup.get(Instrument, case.instrument_id)
            assert instrument is not None
            instrument.identity_status = "resolved"
            profile = ETFProfile(
                instrument_id=instrument.id,
                instrument=instrument,
                issuer="VanEck",
                adapter_key="vaneck",
                adapter_status="ready",
                provider_aliases={
                    "product_slug": VANECK_OIH_PRODUCT_SLUG,
                    "holdings_adapter": "vaneck",
                    "holdings_source_provider": "vaneck",
                    "expected_fund_symbol": "OIH",
                },
            )
            setup.add(profile)
            case.policy.is_enabled = False
            entitlement = await setup.scalar(
                select(ProviderEntitlement).where(
                    ProviderEntitlement.data_source_id == case.source_id,
                    ProviderEntitlement.capability == ProviderCapability.ETF_HOLDINGS,
                )
            )
            assert entitlement is not None
            entitlement.live_probe_status = "not_run"
            entitlement.revision = 7
            admin = User(
                username=f"vaneck-fqc-{suffix}",
                email=f"vaneck-fqc-{suffix}@example.test",
                hashed_password="synthetic-test-only",
                is_active=True,
                is_admin=True,
            )
            setup.add(admin)
            await setup.flush()
            profile_id = profile.id
            admin_id = admin.id

    # An ordinary disabled-policy route remains denied before any transport.
    async with provider_db() as ordinary:
        ordinary_profile = await _load_profile(ordinary, profile_id)
        with pytest.raises(ETFHoldingsRouteHeldError, match="not explicitly enabled"):
            await refresh._refresh_adapter_route(ordinary, ordinary_profile)
    assert runner.calls == []

    async with provider_db() as request_session:
        completed = await qualify_vaneck_oih_fund(
            request_session,
            requested_by_user_id=admin_id,
        )
    assert completed.status == expected_status
    assert completed.job_type == VANECK_OIH_INITIAL_QUALIFICATION_JOB_TYPE
    assert runner.calls == [("GET", VANECK_OIH_INITIAL_URL)]
    assert bridge._REQUEST_BINDING.get() is None
    assert provider_runtime._VANECK_INITIAL_QUALIFICATION_CONTEXT.get() is None
    assert provider_runtime._EXPLICIT_ACQUISITION_CONTEXT.get() is None

    async with provider_db() as reopened:
        job = await reopened.get(ETFHoldingsBackfillJob, completed.id)
        assert job is not None and job.status == expected_status
        assert job.etf_profile_id == profile_id and job.source_provider == "vaneck"
        logs = list(
            (
                await reopened.scalars(
                    select(ProviderRequestLog)
                    .where(
                        ProviderRequestLog.data_source_id == case.source_id,
                        ProviderRequestLog.operation == VANECK_OIH_INITIAL_QUALIFICATION_OPERATION,
                    )
                    .order_by(ProviderRequestLog.id)
                )
            ).all()
        )
        assert len(logs) == 1
        log = logs[0]
        assert log.success is True and log.http_requests == 1
        assert log.completed_at is not None and log.settled_usage_units is not None
        assert job.extra_data["provider_request_log_ids"] == [log.id]
        policy = await reopened.get(ProviderPolicy, case.policy.id)
        entitlement = await reopened.scalar(
            select(ProviderEntitlement).where(
                ProviderEntitlement.data_source_id == case.source_id,
                ProviderEntitlement.capability == ProviderCapability.ETF_HOLDINGS,
            )
        )
        assert policy is not None and policy.is_enabled is False
        if expected_status == "completed":
            assert job.extra_data["qualification_outcome"]["request_log_ids"] == [log.id]
            snapshot_id = job.extra_data["qualification_outcome"]["snapshot_id"]
            snapshot = await reopened.scalar(
                select(ETFHoldingsSnapshot)
                .options(selectinload(ETFHoldingsSnapshot.rows))
                .where(ETFHoldingsSnapshot.id == snapshot_id)
            )
            assert snapshot is not None
            assert snapshot.etf_profile_id == profile_id
            assert snapshot.source_provider == "vaneck"
            assert snapshot.source_url == VANECK_OIH_INITIAL_URL
            assert snapshot.composition_date == date.today()
            assert snapshot.row_count == 1 and len(snapshot.rows) == 1
            assert snapshot.source_artifact_id is not None
            artifact = await reopened.get(ETFHoldingsRawArtifact, snapshot.source_artifact_id)
            assert artifact is not None
            assert artifact.etf_profile_id == profile_id
            assert artifact.data_source_id == snapshot.data_source_id
            assert artifact.data_source_id == await reopened.scalar(
                select(DataSource.id).where(DataSource.name == ETF_HOLDINGS_INTERNAL_PROVIDER)
            )
            assert artifact.legal_metadata["source_provider"] == "vaneck"
            assert artifact.legal_metadata["provider_request_log_ids"] == [log.id]
            assert (
                artifact.payload_json["raw_workbook_sha256"] == hashlib.sha256(workbook).hexdigest()
            )
        else:
            assert job.extra_data["qualification_outcome"]["status"] == "not_qualified"
            assert job.failure_reason is not None
            assert "ETF identity validation" in job.failure_reason
            assert entitlement is not None and entitlement.live_probe_status == "not_run"
            assert (
                await reopened.scalar(
                    select(func.count(ETFHoldingsSnapshot.id)).where(
                        ETFHoldingsSnapshot.etf_profile_id == profile_id
                    )
                )
                == 0
            )
            rejected_artifacts = list(
                (
                    await reopened.scalars(
                        select(ETFHoldingsRawArtifact).where(
                            ETFHoldingsRawArtifact.etf_profile_id == profile_id
                        )
                    )
                ).all()
            )
            rejected_artifact = next(
                (
                    artifact
                    for artifact in rejected_artifacts
                    if isinstance(artifact.payload_json, dict)
                    and artifact.payload_json.get("raw_workbook_sha256")
                    == hashlib.sha256(workbook).hexdigest()
                ),
                None,
            )
            assert rejected_artifact is not None
            assert rejected_artifact.legal_metadata["failure_type"] == "ValueError"
            assert "ETF identity validation" in rejected_artifact.legal_metadata["failure_message"]
            assert rejected_artifact.legal_metadata["provider_request_log_ids"] == [log.id]
            assert (
                rejected_artifact.payload_json["raw_workbook_sha256"]
                == hashlib.sha256(workbook).hexdigest()
            )
        if expected_status == "completed":
            # The fixture records positive probe evidence but leaves the ordinary policy disabled.
            assert entitlement is not None and entitlement.live_probe_status == "passed"

    # The completed one-shot job cannot be replayed and cannot issue a second request.
    async with provider_db() as replay_session:
        replay_reason = (
            "unprobed entitlement" if expected_status == "completed" else "already latched"
        )
        with pytest.raises(ETFHoldingsRouteHeldError, match=replay_reason):
            await qualify_vaneck_oih_fund(replay_session, requested_by_user_id=admin_id)
    assert runner.calls == [("GET", VANECK_OIH_INITIAL_URL)]


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario",
    [
        "failed_pretransport",
        "successful_with_filing",
        "settlement_link_rejected",
        "http_error_response",
        "transport_error_before_response",
        "outer_request_rollback",
        "caller_cancel_after_admission",
    ],
)
async def test_vaneck_qualification_response_eagerly_serializes_after_session_close(
    provider_db, monkeypatch, scenario
):
    """Failure and successful nonempty relationships serialize after operation-session close."""

    from app.auth.jwt import create_access_token
    from app.database import get_auth_session_factory, get_db
    from app.main import app as api_app
    from app.models.etf_holdings import (
        ETFHoldingsBackfillFiling,
        ETFHoldingsBackfillJob,
        ETFHoldingsRawArtifact,
    )
    from app.services import etf_holdings_vaneck_qualification as qualification
    from app.services import provider_runtime

    monkeypatch.setattr(settings, "PROVIDER_ROUTING_ENABLED", True)
    monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", True)
    monkeypatch.setattr(settings, "PROVIDER_FREE_ONLY_CHECKPOINT", True)
    monkeypatch.setattr(settings, "ALLOW_PAID_PROVIDER_ROUTING", False)
    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
    )
    seeds = dict(settings.PROVIDER_ENTITLEMENT_SEEDS or {})
    seeds.pop("vaneck", None)
    monkeypatch.setattr(settings, "PROVIDER_ENTITLEMENT_SEEDS", seeds)

    workbook = _vaneck_initial_qualification_workbook()
    if scenario in {
        "successful_with_filing",
        "settlement_link_rejected",
        "http_error_response",
        "outer_request_rollback",
        "caller_cancel_after_admission",
    }:

        class WorkbookRunner:
            def __init__(self):
                self.calls = []
                self.started = threading.Event()
                self.release = threading.Event()

            def factory(self):
                return httpx.MockTransport(self.handle)

            def handle(self, request):
                self.calls.append((request.method, str(request.url)))
                if scenario == "caller_cancel_after_admission":
                    self.started.set()
                    if not self.release.wait(5):
                        raise httpx.ReadTimeout(
                            "bounded cancellation fixture timed out", request=request
                        )
                return httpx.Response(
                    503 if scenario == "http_error_response" else 200,
                    content=workbook,
                    headers={
                        "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    },
                    request=request,
                )

        runner = WorkbookRunner()
        if scenario == "caller_cancel_after_admission":

            class AsyncWorkbookTransport(httpx.AsyncBaseTransport):
                async def handle_async_request(self, request):
                    runner.calls.append((request.method, str(request.url)))
                    runner.started.set()
                    if not await asyncio.to_thread(runner.release.wait, 5):
                        raise httpx.ReadTimeout(
                            "bounded asynchronous cancellation fixture timed out",
                            request=request,
                        )
                    return httpx.Response(
                        200,
                        content=workbook,
                        headers={
                            "content-type": (
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                        },
                        request=request,
                    )

                async def aclose(self):
                    return None

            runner.factory = lambda: AsyncWorkbookTransport()
    else:
        runner = _TransportRunner()
        if scenario == "transport_error_before_response":
            runner.raise_timeout = True
    _use_mocktransport(monkeypatch, runner)
    if scenario == "settlement_link_rejected":
        # Force exactly one named positive-link predicate to fail after the
        # real Provider executor has measured and completed its controlled
        # response. The request log itself must still survive the link error.
        monkeypatch.setattr(provider_runtime, "_settled_usage_units", lambda *_a, **_k: None)
    suffix = uuid4().hex[:10]
    async with provider_db() as setup:
        case = await _seed_reviewed_fixture(
            setup,
            limit=3,
            monkeypatch=monkeypatch,
            reviewed_hosts=["www.vaneck.com"],
            provider_name_override="vaneck",
            instrument_symbol_override="OIH",
            quota_scope_override="application",
        )
        instrument = await setup.get(Instrument, case.instrument_id)
        assert instrument is not None
        instrument.identity_status = "resolved"
        profile = ETFProfile(
            instrument_id=instrument.id,
            instrument=instrument,
            issuer="VanEck",
            adapter_key="vaneck",
            adapter_status="ready",
            provider_aliases={
                "product_slug": "oil-services-etf-oih",
                "holdings_adapter": "vaneck",
                "holdings_source_provider": "vaneck",
                "expected_fund_symbol": "OIH",
            },
        )
        entitlement = await setup.scalar(
            select(ProviderEntitlement).where(
                ProviderEntitlement.data_source_id == case.source_id,
                ProviderEntitlement.capability == ProviderCapability.ETF_HOLDINGS,
            )
        )
        assert entitlement is not None
        entitlement.configured_plan = (
            "public-download-no-paid-activation"
            if scenario == "failed_pretransport"
            else "reviewed-public-download"
        )
        entitlement.live_probe_status = "not_run"
        entitlement.revision = 1 if scenario == "failed_pretransport" else 2
        case.policy.is_enabled = False
        admin = User(
            username=f"vaneck-http-failure-{suffix}",
            email=f"vaneck-http-failure-{suffix}@example.test",
            hashed_password="synthetic-test-only",
            is_active=True,
            is_admin=True,
        )
        setup.add_all([profile, admin])
        await setup.commit()
        admin_id = admin.id
        profile_id = profile.id
        instrument_id = instrument.id

    if scenario in {"successful_with_filing", "outer_request_rollback"}:
        original_record_success = qualification._record_success

        async def add_fixture_related_filing(db, profile, *, snapshot):
            await original_record_success(db, profile, snapshot=snapshot)
            running_job = await db.scalar(
                select(ETFHoldingsBackfillJob).where(
                    ETFHoldingsBackfillJob.etf_profile_id == profile.id,
                    ETFHoldingsBackfillJob.job_type == "vaneck_oih_initial_qualification",
                    ETFHoldingsBackfillJob.status == "running",
                )
            )
            assert running_job is not None
            db.add(
                ETFHoldingsBackfillFiling(
                    etf_profile_id=profile.id,
                    last_job_id=running_job.id,
                    accession_number=f"FIXTURE-{suffix}",
                    form="FIXTURE",
                    filing_date=date.today(),
                    status="fixture_only",
                    extra_data={"fixture_only": True, "purpose": "response relationship test"},
                )
            )

        monkeypatch.setattr(qualification, "_record_success", add_fixture_related_filing)

    request_sessions: list[AsyncSession] = []
    request_backend_pids: list[int] = []

    async def fresh_request_db():
        async with provider_db() as request_db:
            request_sessions.append(request_db)
            request_backend_pids.append(
                int(await request_db.scalar(text("SELECT pg_backend_pid()")))
            )
            try:
                yield request_db
                if scenario == "outer_request_rollback":
                    await request_db.rollback()
                else:
                    await request_db.commit()
            except BaseException:
                await request_db.rollback()
                raise

    original_async_session = qualification.AsyncSession
    operation_backend_pids: list[int] = []

    class TrackingAsyncSession(original_async_session):
        async def execute(self, statement, *args, **kwargs):
            info = self.sync_session.info
            if info.get("tracked_role") == "qualification_operation" and not info.get(
                "tracked_backend_pid"
            ):
                info["tracked_backend_pid"] = True
                result = await super().execute(text("SELECT pg_backend_pid()"))
                operation_backend_pids.append(int(result.scalar_one()))
            return await super().execute(statement, *args, **kwargs)

    created_service_sessions: list[str] = []

    def tracking_async_session(*args, **kwargs):
        role = (
            "qualification_operation"
            if not created_service_sessions
            else "qualification_lock"
            if len(created_service_sessions) == 1
            else "failed_job_finalizer"
        )
        created_service_sessions.append(role)
        session = TrackingAsyncSession(*args, **kwargs)
        session.sync_session.info["tracked_role"] = role
        return session

    monkeypatch.setattr(qualification, "AsyncSession", tracking_async_session)
    token = create_access_token(admin_id)
    headers = {"Authorization": f"Bearer {token}"}
    transport = httpx.ASGITransport(app=api_app)
    cancelled = False
    response = None
    if scenario == "caller_cancel_after_admission":
        with pytest.raises(asyncio.CancelledError):
            async with provider_db() as caller_db:
                async with caller_db.begin():
                    request_sessions.append(caller_db)
                    request_backend_pids.append(
                        int(await caller_db.scalar(text("SELECT pg_backend_pid()")))
                    )
                    request_task = asyncio.create_task(
                        qualification.qualify_vaneck_oih_fund(
                            caller_db,
                            requested_by_user_id=admin_id,
                        )
                    )
                    try:
                        assert await asyncio.to_thread(runner.started.wait, 10)
                        request_task.cancel()
                        await asyncio.sleep(0.02)
                        assert not request_task.done()
                        runner.release.set()
                        await request_task
                    finally:
                        runner.release.set()
                        if not request_task.done():
                            request_task.cancel()
                            try:
                                await asyncio.wait_for(request_task, timeout=10)
                            except asyncio.CancelledError:
                                pass
        cancelled = True
    else:
        prior_overrides = dict(api_app.dependency_overrides)
        api_app.dependency_overrides[get_db] = fresh_request_db
        api_app.dependency_overrides[get_auth_session_factory] = lambda: provider_db
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://etf.test") as client:
                response = await client.post(
                    "/api/v1/etf-holdings/OIH/vaneck-initial-qualification",
                    headers=headers,
                )
        finally:
            api_app.dependency_overrides.clear()
            api_app.dependency_overrides.update(prior_overrides)

    if not cancelled:
        assert response is not None and response.status_code == 200, (
            response.text if response else None
        )
        body = response.json()
        assert body["etf_profile_id"] == profile_id
        assert body["source_provider"] == "vaneck"
        assert body["job_type"] == "vaneck_oih_initial_qualification"
    else:
        body = None
    if cancelled:
        assert runner.calls == [
            (
                "GET",
                "https://www.vaneck.com/us/en/investments/oil-services-etf-oih/downloads/holdings/?cken=true",
            )
        ]
    elif scenario == "failed_pretransport":
        assert body["status"] == "failed"
        assert body["failure_reason"] == (
            "No currently-supported providers available for "
            "etf_holdings/fetch_etf_holdings_latest"
        )
        assert body["filings"] == []
        assert runner.calls == []
    elif scenario in {"successful_with_filing", "outer_request_rollback"}:
        assert body["status"] == "completed"
        assert body["failure_reason"] is None
        assert len(body["filings"]) == 1
        assert body["filings"][0]["accession_number"] == f"FIXTURE-{suffix}"
        assert body["filings"][0]["extra_data"]["fixture_only"] is True
        assert runner.calls == [
            (
                "GET",
                "https://www.vaneck.com/us/en/investments/oil-services-etf-oih/downloads/holdings/?cken=true",
            )
        ]
    else:
        assert body["status"] == "failed"
        assert body["failure_reason"]
        assert runner.calls == [
            (
                "GET",
                "https://www.vaneck.com/us/en/investments/oil-services-etf-oih/downloads/holdings/?cken=true",
            )
        ]
        if scenario == "settlement_link_rejected":
            assert "settled_usage_units_missing" in body["failure_reason"]
    assert len(request_sessions) == 1
    expected_service_session_roles = ["qualification_operation", "qualification_lock"]
    if scenario not in {"successful_with_filing", "outer_request_rollback"}:
        expected_service_session_roles.append("failed_job_finalizer")
    assert created_service_sessions == expected_service_session_roles
    assert len(operation_backend_pids) == 1
    assert operation_backend_pids[0] != request_backend_pids[0]

    async with provider_db() as readback:
        job = (
            await readback.get(ETFHoldingsBackfillJob, body["id"])
            if body is not None
            else await readback.scalar(
                select(ETFHoldingsBackfillJob)
                .where(
                    ETFHoldingsBackfillJob.etf_profile_id == profile_id,
                    ETFHoldingsBackfillJob.job_type == "vaneck_oih_initial_qualification",
                )
                .order_by(ETFHoldingsBackfillJob.id.desc())
            )
        )
        assert job is not None
        expected_success = scenario in {"successful_with_filing", "outer_request_rollback"}
        expected_status = (
            "interrupted" if cancelled else "completed" if expected_success else "failed"
        )
        assert job.status == expected_status
        assert job.etf_profile_id == profile_id
        if not expected_success:
            evidence = job.extra_data["qualification_outcome"]["provider_attempt_evidence"]
            assert evidence["positive_qualification_linked"] is False
            if scenario == "failed_pretransport":
                assert job.extra_data["provider_request_log_ids"] == []
                assert evidence["admitted_attempt_recorded"] is False
                assert evidence["request_log_callback_ids"] == []
                assert evidence["persisted_request_log_ids"] == []
                assert evidence["all_callback_logs_persisted"] is False
            else:
                # A cancelled but fully measured attempt remains linked for
                # audit if the Provider call completed before cancellation.
                # Ordinary failure finalization retains those IDs in the
                # nested attempt evidence without applying the success link.
                expected_job_log_ids = evidence["persisted_request_log_ids"] if cancelled else []
                assert job.extra_data["provider_request_log_ids"] == expected_job_log_ids
                assert evidence["admitted_attempt_recorded"] is True
                assert len(evidence["request_log_callback_ids"]) == 1
                assert evidence["persisted_request_log_ids"] == evidence["request_log_callback_ids"]
                assert evidence["all_callback_logs_persisted"] is True
            log_rows = list(
                (
                    await readback.scalars(
                        select(ProviderRequestLog)
                        .where(
                            ProviderRequestLog.data_source_id == case.source_id,
                            ProviderRequestLog.capability == ProviderCapability.ETF_HOLDINGS,
                            ProviderRequestLog.operation == "fetch_etf_holdings_latest",
                            ProviderRequestLog.instrument_id == instrument_id,
                        )
                        .order_by(ProviderRequestLog.id)
                    )
                ).all()
            )
            if scenario == "failed_pretransport":
                assert log_rows == []
            else:
                assert len(log_rows) == 1
                log = log_rows[0]
                assert log.id == evidence["persisted_request_log_ids"][0]
                assert log.completed_at is not None
                assert log.settled_usage_units is not None or scenario == "settlement_link_rejected"
                if scenario == "settlement_link_rejected":
                    assert log.success is True and log.http_requests == 1
                    assert log.settled_usage_units is None
                elif scenario == "http_error_response":
                    assert log.success is False and log.http_requests == 1
                    assert log.error_type is not None
                elif scenario == "transport_error_before_response":
                    assert log.success is False and log.http_requests == 0
                    assert log.error_type is not None
                elif cancelled:
                    assert log.success is True and log.http_requests == 1
                if scenario in {"settlement_link_rejected", "http_error_response"}:
                    raw_response = log.response_payloads[-1]
                    assert raw_response["kind"] == "vaneck_initial_response_body"
                    assert raw_response["encoding"] == "base64"
                    assert raw_response["complete"] is True
                    assert raw_response["bytes_received"] == len(workbook)
                    assert raw_response["sha256"] == hashlib.sha256(workbook).hexdigest()
                    assert base64.b64decode(raw_response["body_base64"], validate=True) == workbook
            assert (
                await readback.scalar(
                    select(func.count(ETFHoldingsSnapshot.id)).where(
                        ETFHoldingsSnapshot.etf_profile_id == profile_id
                    )
                )
                == 0
            )
            assert (
                await readback.scalar(
                    select(func.count(ETFHoldingsRawArtifact.id)).where(
                        ETFHoldingsRawArtifact.etf_profile_id == profile_id
                    )
                )
                == 1
            )
            diagnostic = await readback.scalar(
                select(ETFHoldingsRawArtifact).where(
                    ETFHoldingsRawArtifact.etf_profile_id == profile_id
                )
            )
            assert diagnostic is not None
            assert diagnostic.source_kind == "issuer_adapter_rejected_fetch"
            assert diagnostic.source_url == (
                ""
                if scenario == "failed_pretransport"
                else "https://www.vaneck.com/us/en/investments/oil-services-etf-oih/downloads/holdings/?cken=true"
            )
            assert diagnostic.source_identifier is None
            if scenario in {"settlement_link_rejected", "http_error_response"}:
                assert diagnostic.content_type == "application/json"
                assert diagnostic.payload_text is None
                assert diagnostic.payload_json == log.response_payloads[-1]
                assert diagnostic.content_hash == _hash_payload(diagnostic.payload_json)
            if scenario == "failed_pretransport":
                expected_payload = {
                    "failure_type": "ProviderNoDataError",
                    "failure_message": body["failure_reason"],
                    "validation": None,
                }
                assert diagnostic.content_type == "application/json"
                assert diagnostic.content_hash == _hash_payload(expected_payload)
                assert diagnostic.payload_text is None
                assert diagnostic.payload_json == expected_payload
            assert diagnostic.legal_metadata["provider_request_log_ids"] == (
                [] if scenario == "failed_pretransport" else evidence["persisted_request_log_ids"]
            )
            assert len(diagnostic.legal_metadata["request_attempts"]) == (
                0 if scenario == "failed_pretransport" else 1
            )
        else:
            assert len(job.extra_data["provider_request_log_ids"]) == 1
            assert (
                await readback.scalar(
                    select(func.count(ETFHoldingsSnapshot.id)).where(
                        ETFHoldingsSnapshot.etf_profile_id == profile_id
                    )
                )
                == 1
            )
            fixture_filing = await readback.scalar(
                select(ETFHoldingsBackfillFiling).where(
                    ETFHoldingsBackfillFiling.last_job_id == job.id
                )
            )
            assert fixture_filing is not None
            assert fixture_filing.extra_data["fixture_only"] is True


async def _seed_failed_vaneck_pretransport_attempt(
    provider_db, monkeypatch, *, include_no_body_diagnostic=False
):
    from app.models.etf_holdings import ETFHoldingsBackfillJob, ETFHoldingsRawArtifact
    from app.services.etf_holdings import _hash_payload
    from app.services.etf_holdings_vaneck_qualification import (
        VANECK_OIH_INITIAL_DEADLINE_SECONDS,
        VANECK_OIH_INITIAL_MAX_BODY_BYTES,
        VANECK_OIH_INITIAL_MAX_PHYSICAL_REQUESTS,
        VANECK_OIH_INITIAL_MIN_INTERVAL_SECONDS,
        VANECK_OIH_INITIAL_QUALIFICATION_JOB_TYPE,
        VANECK_OIH_INITIAL_QUALIFICATION_OPERATION,
        VANECK_OIH_INITIAL_URL,
        VANECK_OIH_PRODUCT_SLUG,
        VANECK_PRETRANSPORT_FAILURE_REASON,
        _provider_review_fingerprint,
    )

    case = await _seed_reviewed_fixture(
        provider_db,
        limit=3,
        monkeypatch=monkeypatch,
        reviewed_hosts=["www.vaneck.com"],
        provider_name_override="vaneck",
        instrument_symbol_override="OIH",
        quota_scope_override="application",
    )
    source = await provider_db.get(DataSource, case.source_id)
    entitlement = await provider_db.scalar(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == case.source_id,
            ProviderEntitlement.capability == ProviderCapability.ETF_HOLDINGS,
        )
    )
    instrument = await provider_db.get(Instrument, case.instrument_id)
    assert source is not None and entitlement is not None and instrument is not None
    instrument.identity_status = "resolved"
    profile = ETFProfile(
        instrument_id=instrument.id,
        instrument=instrument,
        issuer="VanEck",
        adapter_key="vaneck",
        adapter_status="ready",
        provider_aliases={
            "product_slug": VANECK_OIH_PRODUCT_SLUG,
            "holdings_adapter": "vaneck",
            "holdings_source_provider": "vaneck",
            "expected_fund_symbol": "OIH",
        },
    )
    case.policy.is_enabled = False
    entitlement.configured_plan = "reviewed-public-download"
    entitlement.live_probe_status = "not_run"
    entitlement.revision = 2
    prior_fields = (
        "revision",
        "configured_plan",
        "is_free",
        "authentication_required",
        "usage_terms",
        "redistribution_allowed",
        "quota_policy",
        "history_depth",
        "venue_coverage",
        "freshness_semantics",
        "enabled_environments",
        "effective_at",
        "review_due_at",
        "live_probe_status",
    )
    prior_entitlement = SimpleNamespace(
        **{field: getattr(entitlement, field) for field in prior_fields}
    )
    prior_entitlement.revision = 1
    prior_entitlement.configured_plan = "public-download-no-paid-activation"
    prior_entitlement.live_probe_status = "not_run"
    old_fingerprint = _provider_review_fingerprint(source, case.policy, prior_entitlement)
    admin = User(
        username=f"vaneck-recovery-{uuid4().hex[:10]}",
        email=f"vaneck-recovery-{uuid4().hex[:10]}@example.test",
        hashed_password="synthetic-test-only",
        is_active=True,
        is_admin=True,
    )
    provider_db.add_all([profile, admin])
    await provider_db.flush()
    started_at = datetime.now(UTC) - timedelta(minutes=2)
    completed_at = started_at + timedelta(seconds=1)
    predecessor = ETFHoldingsBackfillJob(
        etf_profile_id=profile.id,
        requested_by_user_id=admin.id,
        source_provider="vaneck",
        job_type=VANECK_OIH_INITIAL_QUALIFICATION_JOB_TYPE,
        status="failed",
        started_at=started_at,
        completed_at=completed_at,
        failure_reason=VANECK_PRETRANSPORT_FAILURE_REASON,
        discovered_count=0,
        ingested_count=0,
        skipped_count=0,
        failed_count=0,
        extra_data={
            "qualification_scope": {
                "provider": "vaneck",
                "capability": ProviderCapability.ETF_HOLDINGS.value,
                "operation": VANECK_OIH_INITIAL_QUALIFICATION_OPERATION,
                "profile_id": profile.id,
                "instrument_id": instrument.id,
                "provider_symbol": "OIH",
                "product_slug": VANECK_OIH_PRODUCT_SLUG,
                "request_url": VANECK_OIH_INITIAL_URL,
                "allowed_initial_host": "www.vaneck.com",
                "account_scope": case.account_scope,
                "review_revision": 1,
                "expires_at": (
                    started_at + timedelta(seconds=VANECK_OIH_INITIAL_DEADLINE_SECONDS)
                ).isoformat(),
                "concurrency": 1,
                "minimum_physical_interval_seconds": VANECK_OIH_INITIAL_MIN_INTERVAL_SECONDS,
                "burst_capacity": 1,
                "max_physical_requests": VANECK_OIH_INITIAL_MAX_PHYSICAL_REQUESTS,
                "deadline_seconds": VANECK_OIH_INITIAL_DEADLINE_SECONDS,
                "max_response_bytes": VANECK_OIH_INITIAL_MAX_BODY_BYTES,
                "automatic_retries": 0,
                "follow_redirects": False,
                "provider_review_fingerprint": old_fingerprint,
            },
            "qualification_outcome": {
                "status": "not_qualified",
                "reason": VANECK_PRETRANSPORT_FAILURE_REASON,
            },
            "provider_request_log_ids": [],
        },
    )
    provider_db.add(predecessor)
    await provider_db.commit()

    diagnostic_artifact = None
    if include_no_body_diagnostic:
        diagnostic_payload = {
            "failure_type": "ProviderNoDataError",
            "failure_message": VANECK_PRETRANSPORT_FAILURE_REASON,
            "validation": None,
        }
        diagnostic_artifact = ETFHoldingsRawArtifact(
            etf_profile_id=profile.id,
            data_source_id=source.id,
            source_kind="issuer_adapter_rejected_fetch",
            source_url="",
            source_identifier=None,
            content_type="application/json",
            content_hash=_hash_payload(diagnostic_payload),
            composition_date=None,
            as_of_date=None,
            published_at=None,
            fetched_at=completed_at - timedelta(milliseconds=100),
            parser_version="vaneck",
            payload_text=None,
            payload_json=diagnostic_payload,
            legal_metadata={
                "provider_request_log_ids": [],
                "request_urls": [],
                "request_attempts": [],
                "failure_type": "ProviderNoDataError",
                "failure_message": VANECK_PRETRANSPORT_FAILURE_REASON,
                "validation": None,
                "evidence_source": "shared_provider_request_log_and_refresh_rejection",
            },
        )
        provider_db.add(diagnostic_artifact)
        await provider_db.commit()

    ledger_url = settings.PROVIDER_QUOTA_LEDGER_DATABASE_URL
    ledger_engine = quota_coordinator._engine_for(ledger_url)
    ledger_time = datetime.now(UTC) - timedelta(days=1)
    with ledger_engine.begin() as connection:
        if (
            connection.execute(
                select(func.count()).select_from(quota_coordinator._reservations)
            ).scalar_one()
            == 0
        ):
            connection.execute(
                insert(quota_coordinator._reservations).values(
                    reservation_id=str(uuid4()),
                    provider_name="fixture-unrelated-provider",
                    account_scope="fixture-unrelated-account",
                    operation="fixture_unrelated_operation",
                    quota_group="fixture-unrelated",
                    dimension="requests",
                    unit="requests",
                    window_started_at=ledger_time,
                    window_seconds=60,
                    reserved_units=1,
                    release_only=False,
                    lease_expires_at=None,
                    identity_digest=None,
                    state="settled",
                    created_at=ledger_time,
                    settled_at=ledger_time,
                )
            )
    return (
        case,
        profile.id,
        admin.id,
        predecessor.id,
        predecessor.extra_data,
        started_at,
        completed_at,
        (
            {
                "artifact_id": diagnostic_artifact.id,
                "content_hash": diagnostic_artifact.content_hash,
            }
            if diagnostic_artifact is not None
            else None
        ),
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_admin_vaneck_recovery_creates_one_linked_successor_and_preserves_predecessor(
    provider_db, monkeypatch
):
    """Only the explicit admin recovery action can replace exact pretransport job 2."""

    from app.auth.jwt import create_access_token
    from app.database import get_auth_session_factory, get_db
    from app.main import app as api_app
    from app.models.etf_holdings import ETFHoldingsBackfillJob
    from app.services.etf_holdings_vaneck_qualification import recover_vaneck_oih_fund

    monkeypatch.setattr(settings, "PROVIDER_ROUTING_ENABLED", True)
    monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", True)
    monkeypatch.setattr(settings, "PROVIDER_FREE_ONLY_CHECKPOINT", True)
    monkeypatch.setattr(settings, "ALLOW_PAID_PROVIDER_ROUTING", False)
    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
    )
    seeds = dict(settings.PROVIDER_ENTITLEMENT_SEEDS or {})
    seeds.pop("vaneck", None)
    monkeypatch.setattr(settings, "PROVIDER_ENTITLEMENT_SEEDS", seeds)
    workbook = _vaneck_initial_qualification_workbook()

    class WorkbookRunner:
        def __init__(self):
            self.calls = []

        def factory(self):
            return httpx.MockTransport(self.handle)

        def handle(self, request):
            self.calls.append((request.method, str(request.url)))
            return httpx.Response(
                200,
                content=workbook,
                headers={
                    "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                },
                request=request,
            )

    runner = WorkbookRunner()
    _use_mocktransport(monkeypatch, runner)
    async with provider_db() as setup:
        (
            case,
            profile_id,
            admin_id,
            predecessor_id,
            predecessor_extra,
            _,
            _,
            diagnostic_ref,
        ) = await _seed_failed_vaneck_pretransport_attempt(
            setup, monkeypatch, include_no_body_diagnostic=True
        )

    prior_overrides = dict(api_app.dependency_overrides)

    async def fresh_request_db():
        async with provider_db() as request_db:
            try:
                yield request_db
                await request_db.commit()
            except BaseException:
                await request_db.rollback()
                raise

    api_app.dependency_overrides[get_db] = fresh_request_db
    api_app.dependency_overrides[get_auth_session_factory] = lambda: provider_db
    token = create_access_token(admin_id)
    payload = {
        "predecessor_job_id": predecessor_id,
        "review_evidence_reference": "operator-note:root-2026-10-29",
        "review_evidence_sha256": "a" * 64,
        "operator_reason": "The reviewed entitlement label was corrected; prior attempt was held before transport.",
    }
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api_app), base_url="http://etf.test"
        ) as client:
            responses = await asyncio.gather(
                *(
                    client.post(
                        "/api/v1/etf-holdings/OIH/vaneck-initial-qualification/recover",
                        headers={"Authorization": f"Bearer {token}"},
                        json=payload,
                    )
                    for _ in range(2)
                )
            )
    finally:
        api_app.dependency_overrides.clear()
        api_app.dependency_overrides.update(prior_overrides)

    successful_responses = [response for response in responses if response.status_code == 200]
    denied_responses = [response for response in responses if response.status_code == 409]
    assert len(successful_responses) == 1
    assert len(denied_responses) == 1, [response.text for response in responses]
    response = successful_responses[0]
    body = response.json()
    assert body["id"] != predecessor_id
    assert body["etf_profile_id"] == profile_id
    assert body["status"] == "completed"
    assert len(body["extra_data"]["provider_request_log_ids"]) == 1
    assert runner.calls == [
        (
            "GET",
            "https://www.vaneck.com/us/en/investments/oil-services-etf-oih/downloads/holdings/?cken=true",
        )
    ]

    async with provider_db() as readback:
        predecessor = await readback.get(ETFHoldingsBackfillJob, predecessor_id)
        successor = await readback.get(ETFHoldingsBackfillJob, body["id"])
        assert predecessor is not None and successor is not None
        assert predecessor.status == "failed"
        assert predecessor.extra_data == predecessor_extra
        assert successor.status == "completed"
        recovery = successor.extra_data["pretransport_recovery"]
        assert recovery["predecessor_job_id"] == predecessor_id
        assert recovery["review_evidence_reference"] == payload["review_evidence_reference"]
        assert recovery["review_evidence_sha256"] == payload["review_evidence_sha256"]
        assert recovery["review_revision"] == 2
        assert recovery["predecessor_diagnostic_artifacts"] == [diagnostic_ref]
        assert len(successor.extra_data["provider_request_log_ids"]) == 1
        assert (
            await readback.scalar(
                select(func.count(ETFHoldingsBackfillJob.id)).where(
                    ETFHoldingsBackfillJob.etf_profile_id == profile_id,
                    ETFHoldingsBackfillJob.job_type == "vaneck_oih_initial_qualification",
                )
            )
            == 2
        )
        policy = await readback.get(ProviderPolicy, case.policy.id)
        entitlement = await readback.scalar(
            select(ProviderEntitlement).where(
                ProviderEntitlement.data_source_id == case.source_id,
                ProviderEntitlement.capability == ProviderCapability.ETF_HOLDINGS,
            )
        )
        assert policy is not None and policy.is_enabled is False
        assert entitlement is not None and entitlement.live_probe_status == "passed"

    with pytest.raises(ETFHoldingsRouteHeldError):
        async with provider_db() as replay_session:
            await recover_vaneck_oih_fund(
                replay_session,
                requested_by_user_id=admin_id,
                predecessor_job_id=predecessor_id,
                review_evidence_reference=payload["review_evidence_reference"],
                review_evidence_sha256=payload["review_evidence_sha256"],
                operator_reason=payload["operator_reason"],
            )
    assert len(runner.calls) == 1


def _configure_vaneck_quota_test_ledger(provider_db, monkeypatch, *, backend, tmp_path):
    if backend == "postgres":
        ledger_url = provider_db.url.render_as_string(hide_password=False)
        ledger_path = None
    elif backend == "sqlite":
        ledger_path = tmp_path / "provider-quota.sqlite3"
        ledger_url = f"sqlite:///{ledger_path}"
        ledger_engine = quota_coordinator._engine_for(ledger_url)
        quota_coordinator.metadata.create_all(ledger_engine)
        ledger_engine.dispose()
    else:
        raise AssertionError(f"unknown quota test ledger backend: {backend}")
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_DATABASE_URL", ledger_url)
    return ledger_path


async def _seed_failed_vaneck_posttransport_attempt(provider_db, setup, monkeypatch):
    """Create the retained job2 -> job3 diagnostic chain without inventing wire bytes."""

    from app.models.etf_holdings import ETFHoldingsBackfillJob, ETFHoldingsRawArtifact
    from app.services.etf_holdings_vaneck_qualification import (
        VANECK_OIH_INITIAL_DEADLINE_SECONDS,
        VANECK_OIH_INITIAL_MAX_BODY_BYTES,
        VANECK_OIH_INITIAL_MIN_INTERVAL_SECONDS,
        VANECK_OIH_INITIAL_QUALIFICATION_JOB_TYPE,
        VANECK_OIH_INITIAL_QUALIFICATION_OPERATION,
        VANECK_OIH_INITIAL_QUOTA_DIMENSION,
        VANECK_OIH_INITIAL_QUOTA_GROUP,
        VANECK_OIH_INITIAL_URL,
        VANECK_OIH_PRODUCT_SLUG,
        VANECK_POSTTRANSPORT_LINK_FAILURE_REASON,
        _provider_review_fingerprint,
    )

    (
        case,
        profile_id,
        admin_id,
        job2_id,
        job2_extra,
        job2_started_at,
        job2_completed_at,
        diagnostic3,
    ) = await _seed_failed_vaneck_pretransport_attempt(
        setup, monkeypatch, include_no_body_diagnostic=True
    )
    source = await setup.get(DataSource, case.source_id)
    profile = await setup.get(ETFProfile, profile_id)
    entitlement = await setup.scalar(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == case.source_id,
            ProviderEntitlement.capability == ProviderCapability.ETF_HOLDINGS,
        )
    )
    job2 = await setup.get(ETFHoldingsBackfillJob, job2_id)
    assert (
        source is not None and profile is not None and entitlement is not None and job2 is not None
    )
    current_fingerprint = _provider_review_fingerprint(source, case.policy, entitlement)
    started_at = job2_completed_at + timedelta(seconds=3)
    completed_at = started_at + timedelta(seconds=2)
    request_log_id = 13
    scope = {
        "provider": "vaneck",
        "capability": ProviderCapability.ETF_HOLDINGS.value,
        "operation": VANECK_OIH_INITIAL_QUALIFICATION_OPERATION,
        "profile_id": profile_id,
        "instrument_id": profile.instrument_id,
        "provider_symbol": "OIH",
        "product_slug": VANECK_OIH_PRODUCT_SLUG,
        "request_url": VANECK_OIH_INITIAL_URL,
        "allowed_initial_host": "www.vaneck.com",
        "account_scope": case.account_scope,
        "review_revision": int(entitlement.revision or 1),
        "expires_at": (
            started_at + timedelta(seconds=VANECK_OIH_INITIAL_DEADLINE_SECONDS)
        ).isoformat(),
        "concurrency": 1,
        "minimum_physical_interval_seconds": VANECK_OIH_INITIAL_MIN_INTERVAL_SECONDS,
        "burst_capacity": 1,
        "max_physical_requests": 3,
        "deadline_seconds": VANECK_OIH_INITIAL_DEADLINE_SECONDS,
        "max_response_bytes": VANECK_OIH_INITIAL_MAX_BODY_BYTES,
        "automatic_retries": 0,
        "follow_redirects": False,
        "provider_review_fingerprint": current_fingerprint,
    }
    job3 = ETFHoldingsBackfillJob(
        etf_profile_id=profile_id,
        requested_by_user_id=admin_id,
        source_provider="vaneck",
        job_type=VANECK_OIH_INITIAL_QUALIFICATION_JOB_TYPE,
        status="failed",
        started_at=started_at,
        completed_at=completed_at,
        failure_reason=VANECK_POSTTRANSPORT_LINK_FAILURE_REASON,
        discovered_count=0,
        ingested_count=0,
        skipped_count=0,
        failed_count=1,
        extra_data={
            "qualification_scope": scope,
            "qualification_outcome": {
                "status": "not_qualified",
                "reason": VANECK_POSTTRANSPORT_LINK_FAILURE_REASON,
            },
            "provider_request_log_ids": [],
            "pretransport_recovery": {
                "predecessor_job_id": job2_id,
                "review_evidence_reference": "vaneck-oih-fresh-bounded-recovery-review-20261030.json",
                "review_evidence_sha256": "6d2b76ecfc4e2ea545b83c800233bfcf0338c5b1402021aba9136821a8f4e9fb",
                "operator_reason": "Root accepted the fully qualified private release and freshly reviewed the exact pretransport failure, immutable diagnostic artifact, current free admission, shared quota ledger and bounded one-successor recovery.",
                "created_at": started_at.isoformat(),
                "review_revision": int(entitlement.revision or 1),
                "provider_review_fingerprint": current_fingerprint,
                "predecessor_diagnostic_artifacts": [diagnostic3],
            },
        },
    )
    setup.add(job3)
    await setup.flush()
    diagnostic_payload = {
        "failure_type": "ETFHoldingsRouteHeldError",
        "failure_message": VANECK_POSTTRANSPORT_LINK_FAILURE_REASON,
        "validation": None,
    }
    assert _hash_payload(diagnostic_payload) == (
        "25c2d92366c306c378fab29a91dd201ffc5366ef273719ad03e41182ac9675dc"
    )
    artifact4 = ETFHoldingsRawArtifact(
        etf_profile_id=profile_id,
        data_source_id=source.id,
        source_kind="issuer_adapter_rejected_fetch",
        source_url=VANECK_OIH_INITIAL_URL,
        source_identifier=None,
        content_type="application/json",
        content_hash=_hash_payload(diagnostic_payload),
        composition_date=None,
        as_of_date=None,
        published_at=None,
        fetched_at=completed_at - timedelta(milliseconds=100),
        parser_version="vaneck",
        payload_text=None,
        payload_json=diagnostic_payload,
        legal_metadata={
            "provider_request_log_ids": [request_log_id],
            "request_urls": [VANECK_OIH_INITIAL_URL],
            "request_attempts": [],
            "failure_type": "ETFHoldingsRouteHeldError",
            "failure_message": VANECK_POSTTRANSPORT_LINK_FAILURE_REASON,
            "validation": None,
            "evidence_source": "shared_provider_request_log_and_refresh_rejection",
        },
    )
    setup.add(artifact4)
    await setup.commit()

    ledger_engine = quota_coordinator._engine_for(settings.PROVIDER_QUOTA_LEDGER_DATABASE_URL)
    reservation_id = str(uuid4())
    with ledger_engine.begin() as connection:
        connection.execute(
            insert(quota_coordinator._reservations).values(
                reservation_id=reservation_id,
                provider_name="vaneck",
                account_scope=case.account_scope,
                operation="fetch_etf_holdings_latest",
                quota_group=VANECK_OIH_INITIAL_QUOTA_GROUP,
                dimension=VANECK_OIH_INITIAL_QUOTA_DIMENSION,
                unit="requests",
                window_started_at=started_at - timedelta(seconds=30),
                window_seconds=60,
                reserved_units=1,
                release_only=False,
                lease_expires_at=None,
                identity_digest=None,
                state="settled",
                created_at=started_at + timedelta(milliseconds=250),
                settled_at=started_at + timedelta(milliseconds=900),
            )
        )
    ledger_engine.dispose()
    return {
        "case": case,
        "profile_id": profile_id,
        "admin_id": admin_id,
        "job2_id": job2_id,
        "job2_extra": job2_extra,
        "job2_started_at": job2_started_at,
        "job2_completed_at": job2_completed_at,
        "job3_id": job3.id,
        "job3_completed_at": completed_at,
        "job3_extra": job3.extra_data,
        "artifact4_id": artifact4.id,
        "artifact4_hash": artifact4.content_hash,
        "missing_request_log_id": request_log_id,
        "reservation_id": reservation_id,
    }


@pytest.mark.integration
@pytest.mark.parametrize("ledger_backend", ["postgres", "sqlite"])
@pytest.mark.asyncio
async def test_admin_vaneck_posttransport_continuation_is_one_shot_and_idempotent(
    provider_db, monkeypatch, tmp_path, ledger_backend
):
    """A reviewed successor can qualify once while preserving job2/job3 and spent use."""

    from app.auth.jwt import create_access_token
    from app.database import get_auth_session_factory, get_db
    from app.main import app as api_app
    from app.models.etf_holdings import ETFHoldingsBackfillJob, ETFHoldingsRawArtifact
    from app.services import etf_holdings_vaneck_qualification as vaneck_qualification
    from app.services.etf_holdings_vaneck_qualification import (
        VANECK_POSTTRANSPORT_CONTINUATION_KEY,
        _provider_review_fingerprint,
        _validate_posttransport_predecessor,
    )

    monkeypatch.setattr(settings, "PROVIDER_ROUTING_ENABLED", True)
    monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", True)
    monkeypatch.setattr(settings, "PROVIDER_FREE_ONLY_CHECKPOINT", True)
    monkeypatch.setattr(settings, "ALLOW_PAID_PROVIDER_ROUTING", False)
    sqlite_ledger_path = _configure_vaneck_quota_test_ledger(
        provider_db, monkeypatch, backend=ledger_backend, tmp_path=tmp_path
    )
    sqlite_read_transaction_states = []
    if sqlite_ledger_path is not None:
        original_create_engine = vaneck_qualification.create_engine

        def create_engine_with_read_transaction_observer(*args, **kwargs):
            engine = original_create_engine(*args, **kwargs)

            @event.listens_for(engine, "before_cursor_execute")
            def record_sqlite_driver_transaction(
                connection, _cursor, statement, _parameters, _context, _executemany
            ):
                if statement.lstrip().upper().startswith("SELECT"):
                    sqlite_read_transaction_states.append(
                        connection.connection.driver_connection.in_transaction
                    )

            return engine

        monkeypatch.setattr(
            vaneck_qualification, "create_engine", create_engine_with_read_transaction_observer
        )
    seeds = dict(settings.PROVIDER_ENTITLEMENT_SEEDS or {})
    seeds.pop("vaneck", None)
    monkeypatch.setattr(settings, "PROVIDER_ENTITLEMENT_SEEDS", seeds)
    async with provider_db() as setup:
        fixture = await _seed_failed_vaneck_posttransport_attempt(provider_db, setup, monkeypatch)
        non_admin = User(
            username=f"vaneck-reader-{uuid4().hex[:10]}",
            email=f"vaneck-reader-{uuid4().hex[:10]}@example.test",
            hashed_password="unused-test-password-hash",
            is_admin=False,
        )
        setup.add(non_admin)
        await setup.commit()
        non_admin_id = non_admin.id
        if sqlite_ledger_path is not None:
            ledger_bytes_before_read = sqlite_ledger_path.read_bytes()
            ledger_stat_before_read = sqlite_ledger_path.stat()
            source = await setup.get(DataSource, fixture["case"].source_id)
            profile = await setup.get(ETFProfile, fixture["profile_id"])
            entitlement = await setup.scalar(
                select(ProviderEntitlement).where(
                    ProviderEntitlement.data_source_id == fixture["case"].source_id,
                    ProviderEntitlement.capability == ProviderCapability.ETF_HOLDINGS,
                )
            )
            assert source is not None and profile is not None and entitlement is not None
            lineage_preflight = await _validate_posttransport_predecessor(
                setup,
                predecessor_job_id=fixture["job3_id"],
                profile=profile,
                source=source,
                entitlement=entitlement,
                account_scope=fixture["case"].account_scope,
                current_fingerprint=_provider_review_fingerprint(
                    source, fixture["case"].policy, entitlement
                ),
            )
            assert lineage_preflight[1]["settled_prior_usage"]["unit"] == "requests"
            assert sqlite_read_transaction_states and all(sqlite_read_transaction_states)
            assert sqlite_ledger_path.read_bytes() == ledger_bytes_before_read
            ledger_stat_after_read = sqlite_ledger_path.stat()
            assert ledger_stat_after_read.st_ino == ledger_stat_before_read.st_ino
            assert ledger_stat_after_read.st_size == ledger_stat_before_read.st_size
    workbook = _vaneck_initial_qualification_workbook()

    class WorkbookRunner:
        def __init__(self):
            self.calls = []

        def factory(self):
            return httpx.MockTransport(self.handle)

        def handle(self, request):
            self.calls.append((request.method, str(request.url)))
            return httpx.Response(
                200,
                content=workbook,
                headers={
                    "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                },
                request=request,
            )

    runner = WorkbookRunner()
    _use_mocktransport(monkeypatch, runner)
    previous_overrides = dict(api_app.dependency_overrides)

    async def fresh_request_db():
        async with provider_db() as request_db:
            try:
                yield request_db
                await request_db.commit()
            except BaseException:
                await request_db.rollback()
                raise

    api_app.dependency_overrides[get_db] = fresh_request_db
    api_app.dependency_overrides[get_auth_session_factory] = lambda: provider_db
    token = create_access_token(fixture["admin_id"])
    non_admin_token = create_access_token(non_admin_id)
    request_uuid = str(uuid4())
    payload = {
        "predecessor_job_id": fixture["job3_id"],
        "request_id": request_uuid,
        "review_evidence_reference": "root-review:job3-successor-2026-10-30",
        "review_evidence_sha256": "c" * 64,
    }
    endpoint = "/api/v1/etf-holdings/OIH/vaneck-initial-qualification/continue"
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api_app), base_url="http://etf.test"
        ) as client:
            non_admin_response = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {non_admin_token}"},
                json=payload,
            )
            assert non_admin_response.status_code == 403
            assert runner.calls == []
            responses = await asyncio.gather(
                *(
                    client.post(
                        endpoint,
                        headers={"Authorization": f"Bearer {token}"},
                        json=payload,
                    )
                    for _ in range(2)
                )
            )
            changed_body = {**payload, "review_evidence_sha256": "d" * 64}
            changed = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {token}"},
                json=changed_body,
            )
            second_successor = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {token}"},
                json={**payload, "request_id": str(uuid4())},
            )
    finally:
        api_app.dependency_overrides.clear()
        api_app.dependency_overrides.update(previous_overrides)

    assert [response.status_code for response in responses] == [200, 200]
    bodies = [response.json() for response in responses]
    assert bodies[0]["id"] == bodies[1]["id"] != fixture["job3_id"]
    assert all(body["status"] == "completed" for body in bodies)
    assert changed.status_code == 409
    assert second_successor.status_code == 409
    assert runner.calls == [
        (
            "GET",
            "https://www.vaneck.com/us/en/investments/oil-services-etf-oih/downloads/holdings/?cken=true",
        )
    ]
    body = bodies[0]
    continuation = body["extra_data"][VANECK_POSTTRANSPORT_CONTINUATION_KEY]
    assert continuation["request_id"] == request_uuid
    assert continuation["predecessor_job_id"] == fixture["job3_id"]
    assert continuation["predecessor_lineage"]["physical_outcome"] == (
        "unknown_after_admission_and_settlement"
    )
    assert continuation["predecessor_lineage"]["missing_request_log_ids"] == [
        fixture["missing_request_log_id"]
    ]
    assert (
        continuation["predecessor_lineage"]["settled_prior_usage"]["reservation_id"]
        == (fixture["reservation_id"])
    )
    spent = continuation["predecessor_lineage"]["settled_prior_usage"]
    assert spent["quota_group"] == "oih_first_sample"
    assert spent["dimension"] == "vaneck_oih_first_sample_requests_120s"
    assert spent["unit"] == "requests"
    assert fixture["job3_extra"]["provider_request_log_ids"] == []
    assert fixture["job3_extra"]["qualification_outcome"] == {
        "status": "not_qualified",
        "reason": "VanEck qualification request logs are incomplete or outside its exact scope",
    }
    assert continuation["physical_request_limit"] == 1
    assert continuation["status"] == "completed"
    assert continuation["positive_qualification"] is True
    assert body["extra_data"]["qualification_scope"]["max_physical_requests"] == 1

    async with provider_db() as readback:
        job2 = await readback.get(ETFHoldingsBackfillJob, fixture["job2_id"])
        job3 = await readback.get(ETFHoldingsBackfillJob, fixture["job3_id"])
        successor = await readback.get(ETFHoldingsBackfillJob, body["id"])
        artifact4 = await readback.get(ETFHoldingsRawArtifact, fixture["artifact4_id"])
        assert (
            job2 is not None
            and job3 is not None
            and successor is not None
            and artifact4 is not None
        )
        assert job2.status == "failed" and job2.extra_data == fixture["job2_extra"]
        assert job3.status == "failed" and job3.extra_data == fixture["job3_extra"]
        assert artifact4.content_hash == fixture["artifact4_hash"]
        assert successor.status == "completed"
        assert len(successor.extra_data["provider_request_log_ids"]) == 1
        assert (
            await readback.scalar(
                select(func.count(ETFHoldingsBackfillJob.id)).where(
                    ETFHoldingsBackfillJob.etf_profile_id == fixture["profile_id"],
                    ETFHoldingsBackfillJob.job_type == "vaneck_oih_initial_qualification",
                )
            )
            == 3
        )
        policy = await readback.get(ProviderPolicy, fixture["case"].policy.id)
        entitlement = await readback.scalar(
            select(ProviderEntitlement).where(
                ProviderEntitlement.data_source_id == fixture["case"].source_id,
                ProviderEntitlement.capability == ProviderCapability.ETF_HOLDINGS,
            )
        )
        assert policy is not None and policy.is_enabled is False
        assert entitlement is not None and entitlement.live_probe_status == "passed"


@pytest.mark.integration
@pytest.mark.parametrize("ledger_backend", ["postgres", "sqlite"])
@pytest.mark.parametrize(
    ("ledger_field", "bad_value"),
    [
        # The old verifier accepted these generic values. They are not the
        # immutable first-sample quota scope and must remain a denial.
        ("quota_group", "requests"),
        ("dimension", "requests"),
        ("quota_group", "bytes"),
        ("dimension", "bytes"),
        ("unit", "bytes"),
        ("settled_at", "after_job"),
    ],
)
@pytest.mark.asyncio
async def test_vaneck_posttransport_continuation_denies_mismatched_spent_reservation(
    provider_db, monkeypatch, tmp_path, ledger_backend, ledger_field, bad_value
):
    """Only the exact settled request unit can justify this successor."""

    from app.models.etf_holdings import ETFHoldingsBackfillJob, ETFHoldingsRawArtifact
    from app.services.etf_holdings_vaneck_qualification import continue_vaneck_oih_fund

    monkeypatch.setattr(settings, "PROVIDER_ROUTING_ENABLED", True)
    monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", True)
    monkeypatch.setattr(settings, "PROVIDER_FREE_ONLY_CHECKPOINT", True)
    monkeypatch.setattr(settings, "ALLOW_PAID_PROVIDER_ROUTING", False)
    sqlite_ledger_path = _configure_vaneck_quota_test_ledger(
        provider_db, monkeypatch, backend=ledger_backend, tmp_path=tmp_path
    )
    seeds = dict(settings.PROVIDER_ENTITLEMENT_SEEDS or {})
    seeds.pop("vaneck", None)
    monkeypatch.setattr(settings, "PROVIDER_ENTITLEMENT_SEEDS", seeds)
    async with provider_db() as setup:
        fixture = await _seed_failed_vaneck_posttransport_attempt(provider_db, setup, monkeypatch)

    quota_engine = quota_coordinator._engine_for(settings.PROVIDER_QUOTA_LEDGER_DATABASE_URL)
    invalid_value = (
        fixture["job3_completed_at"] + timedelta(seconds=1)
        if bad_value == "after_job"
        else bad_value
    )
    with quota_engine.begin() as connection:
        connection.execute(
            quota_coordinator._reservations.update()
            .where(quota_coordinator._reservations.c.reservation_id == fixture["reservation_id"])
            .values(**{ledger_field: invalid_value})
        )
    quota_engine.dispose()
    sqlite_ledger_before = sqlite_ledger_path.read_bytes() if sqlite_ledger_path else None

    class ForbiddenTransport:
        def __init__(self):
            self.calls = []

        def factory(self):
            return httpx.MockTransport(self.handle)

        def handle(self, request):
            self.calls.append((request.method, str(request.url)))
            raise AssertionError("invalid spent-reservation evidence must stop before transport")

    transport = ForbiddenTransport()
    _use_mocktransport(monkeypatch, transport)
    async with provider_db() as request_db:
        with pytest.raises(ETFHoldingsRouteHeldError, match="settled OIH usage unit"):
            await continue_vaneck_oih_fund(
                request_db,
                requested_by_user_id=fixture["admin_id"],
                predecessor_job_id=fixture["job3_id"],
                request_id=str(uuid4()),
                review_evidence_reference="root-review:job3-successor-2026-10-30",
                review_evidence_sha256="c" * 64,
            )
    assert transport.calls == []
    if sqlite_ledger_path is not None:
        assert sqlite_ledger_path.read_bytes() == sqlite_ledger_before

    async with provider_db() as readback:
        assert (
            await readback.scalar(
                select(func.count(ETFHoldingsBackfillJob.id)).where(
                    ETFHoldingsBackfillJob.etf_profile_id == fixture["profile_id"],
                    ETFHoldingsBackfillJob.job_type == "vaneck_oih_initial_qualification",
                )
            )
            == 2
        )
        job3 = await readback.get(ETFHoldingsBackfillJob, fixture["job3_id"])
        artifact4 = await readback.get(ETFHoldingsRawArtifact, fixture["artifact4_id"])
        assert job3 is not None and job3.extra_data == fixture["job3_extra"]
        assert artifact4 is not None and artifact4.content_hash == fixture["artifact4_hash"]


@pytest.mark.integration
@pytest.mark.parametrize(
    "invalid_state", ["predecessor_scope", "expired_review", "unreviewed_plan", "enabled_policy"]
)
@pytest.mark.asyncio
async def test_vaneck_posttransport_continuation_denies_stale_or_invalid_preflight(
    provider_db, monkeypatch, tmp_path, invalid_state
):
    """Invalid lineage/review/admission is denied before successor admission or transport."""

    from app.models.etf_holdings import ETFHoldingsBackfillJob, ETFHoldingsRawArtifact
    from app.services.etf_holdings_vaneck_qualification import continue_vaneck_oih_fund

    monkeypatch.setattr(settings, "PROVIDER_ROUTING_ENABLED", True)
    monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", True)
    monkeypatch.setattr(settings, "PROVIDER_FREE_ONLY_CHECKPOINT", True)
    monkeypatch.setattr(settings, "ALLOW_PAID_PROVIDER_ROUTING", False)
    _configure_vaneck_quota_test_ledger(
        provider_db, monkeypatch, backend="postgres", tmp_path=tmp_path
    )
    seeds = dict(settings.PROVIDER_ENTITLEMENT_SEEDS or {})
    seeds.pop("vaneck", None)
    monkeypatch.setattr(settings, "PROVIDER_ENTITLEMENT_SEEDS", seeds)
    async with provider_db() as setup:
        fixture = await _seed_failed_vaneck_posttransport_attempt(provider_db, setup, monkeypatch)
        job3 = await setup.get(ETFHoldingsBackfillJob, fixture["job3_id"])
        entitlement = await setup.scalar(
            select(ProviderEntitlement).where(
                ProviderEntitlement.data_source_id == fixture["case"].source_id,
                ProviderEntitlement.capability == ProviderCapability.ETF_HOLDINGS,
            )
        )
        assert job3 is not None and entitlement is not None
        if invalid_state == "predecessor_scope":
            extra = dict(job3.extra_data)
            scope = dict(extra["qualification_scope"])
            scope["request_url"] = "https://unreviewed.invalid/holdings.xlsx"
            extra["qualification_scope"] = scope
            job3.extra_data = extra
        elif invalid_state == "expired_review":
            entitlement.review_due_at = datetime.now(UTC) - timedelta(seconds=1)
        elif invalid_state == "unreviewed_plan":
            entitlement.configured_plan = "public-download-no-paid-activation"
        elif invalid_state == "enabled_policy":
            fixture["case"].policy.is_enabled = True
        await setup.commit()

    class ForbiddenTransport:
        def __init__(self):
            self.calls = []

        def factory(self):
            return httpx.MockTransport(self.handle)

        def handle(self, request):
            self.calls.append((request.method, str(request.url)))
            raise AssertionError("invalid predecessor/review must deny before transport")

    transport = ForbiddenTransport()
    _use_mocktransport(monkeypatch, transport)
    expected_rejection = "review.*expired" if invalid_state == "expired_review" else None
    async with provider_db() as request_db:
        with pytest.raises(ETFHoldingsRouteHeldError, match=expected_rejection):
            await continue_vaneck_oih_fund(
                request_db,
                requested_by_user_id=fixture["admin_id"],
                predecessor_job_id=fixture["job3_id"],
                request_id=str(uuid4()),
                review_evidence_reference="root-review:job3-successor-2026-10-30",
                review_evidence_sha256="c" * 64,
            )
    assert transport.calls == []

    async with provider_db() as readback:
        jobs = list(
            (
                await readback.scalars(
                    select(ETFHoldingsBackfillJob).where(
                        ETFHoldingsBackfillJob.etf_profile_id == fixture["profile_id"],
                        ETFHoldingsBackfillJob.job_type == "vaneck_oih_initial_qualification",
                    )
                )
            ).all()
        )
        assert {job.id for job in jobs} == {fixture["job2_id"], fixture["job3_id"]}
        job3 = await readback.get(ETFHoldingsBackfillJob, fixture["job3_id"])
        artifact4 = await readback.get(ETFHoldingsRawArtifact, fixture["artifact4_id"])
        assert job3 is not None and job3.status == "failed"
        assert artifact4 is not None and artifact4.content_hash == fixture["artifact4_hash"]


@pytest.mark.integration
@pytest.mark.parametrize("late_denial", ["global_routing_stop", "operation_hold", "positive_cost"])
@pytest.mark.asyncio
async def test_vaneck_posttransport_late_admission_denial_is_durable_and_nonpositive(
    provider_db, monkeypatch, tmp_path, late_denial
):
    """A shared-runtime denial after admission retains a failed successor, never a success."""

    from app.models.etf_holdings import ETFHoldingsBackfillJob, ETFHoldingsSnapshot
    from app.services.etf_holdings_vaneck_qualification import (
        VANECK_POSTTRANSPORT_CONTINUATION_KEY,
        continue_vaneck_oih_fund,
    )

    monkeypatch.setattr(settings, "PROVIDER_ROUTING_ENABLED", True)
    monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", True)
    monkeypatch.setattr(settings, "PROVIDER_FREE_ONLY_CHECKPOINT", True)
    monkeypatch.setattr(settings, "ALLOW_PAID_PROVIDER_ROUTING", False)
    _configure_vaneck_quota_test_ledger(
        provider_db, monkeypatch, backend="postgres", tmp_path=tmp_path
    )
    seeds = dict(settings.PROVIDER_ENTITLEMENT_SEEDS or {})
    seeds.pop("vaneck", None)
    monkeypatch.setattr(settings, "PROVIDER_ENTITLEMENT_SEEDS", seeds)
    async with provider_db() as setup:
        fixture = await _seed_failed_vaneck_posttransport_attempt(provider_db, setup, monkeypatch)
        if late_denial == "positive_cost":
            commitment = await setup.scalar(
                select(ProviderRecurringCostCommitment).where(
                    ProviderRecurringCostCommitment.data_source_id == fixture["case"].source_id,
                    ProviderRecurringCostCommitment.environment == settings.APP_ENV.strip().lower(),
                )
            )
            assert commitment is not None
            commitment.amount = Decimal("1.00")
            commitment.monthly_equivalent = Decimal("1.00")
            await setup.commit()

    if late_denial == "global_routing_stop":
        monkeypatch.setattr(settings, "PROVIDER_ROUTING_ENABLED", False)
    elif late_denial == "operation_hold":
        holds = dict(settings.PROVIDER_CHECKPOINT_OPERATION_HOLDS or {})
        holds["vaneck"] = {"fetch_etf_holdings_latest": "focused continuation hold"}
        monkeypatch.setattr(settings, "PROVIDER_CHECKPOINT_OPERATION_HOLDS", holds)

    class ForbiddenTransport:
        def __init__(self):
            self.calls = []

        def factory(self):
            return httpx.MockTransport(self.handle)

        def handle(self, request):
            self.calls.append((request.method, str(request.url)))
            raise AssertionError("held admission must stop before issuer transport")

    transport = ForbiddenTransport()
    _use_mocktransport(monkeypatch, transport)
    async with provider_db() as request_db:
        result = await continue_vaneck_oih_fund(
            request_db,
            requested_by_user_id=fixture["admin_id"],
            predecessor_job_id=fixture["job3_id"],
            request_id=str(uuid4()),
            review_evidence_reference="root-review:job3-successor-2026-10-30",
            review_evidence_sha256="c" * 64,
        )
    assert transport.calls == []
    assert result.status == "failed"
    extra = result.extra_data
    outcome = extra["qualification_outcome"]
    continuation = extra[VANECK_POSTTRANSPORT_CONTINUATION_KEY]
    assert outcome["status"] == "not_qualified"
    assert outcome["provider_attempt_evidence"]["positive_qualification_linked"] is False
    assert continuation["status"] == "failed"
    assert continuation["positive_qualification"] is False

    async with provider_db() as readback:
        persisted = await readback.get(ETFHoldingsBackfillJob, result.id)
        assert persisted is not None and persisted.status == "failed"
        assert (
            await readback.scalar(
                select(func.count(ETFHoldingsSnapshot.id)).where(
                    ETFHoldingsSnapshot.etf_profile_id == fixture["profile_id"]
                )
            )
            == 0
        )
        policy = await readback.get(ProviderPolicy, fixture["case"].policy.id)
        entitlement = await readback.scalar(
            select(ProviderEntitlement).where(
                ProviderEntitlement.data_source_id == fixture["case"].source_id,
                ProviderEntitlement.capability == ProviderCapability.ETF_HOLDINGS,
            )
        )
        assert policy is not None and policy.is_enabled is False
        assert entitlement is not None and entitlement.live_probe_status == "not_run"


@pytest.mark.integration
@pytest.mark.parametrize("scenario", ["http_error", "caller_cancel", "review_expires_during_fetch"])
@pytest.mark.asyncio
async def test_vaneck_posttransport_transport_error_and_cancellation_remain_audited(
    provider_db, monkeypatch, tmp_path, scenario
):
    """Transport failures and caller cancellation retain logs without positive output."""

    from app.models.etf_holdings import ETFHoldingsBackfillJob, ETFHoldingsSnapshot
    from app.services import etf_holdings_vaneck_qualification as vaneck_qualification
    from app.services.etf_holdings_vaneck_qualification import (
        VANECK_POSTTRANSPORT_CONTINUATION_KEY,
        continue_vaneck_oih_fund,
    )

    monkeypatch.setattr(settings, "PROVIDER_ROUTING_ENABLED", True)
    monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", True)
    monkeypatch.setattr(settings, "PROVIDER_FREE_ONLY_CHECKPOINT", True)
    monkeypatch.setattr(settings, "ALLOW_PAID_PROVIDER_ROUTING", False)
    review_clock_shift = {"value": timedelta(0)}
    real_datetime = vaneck_qualification.datetime

    class ShiftableReviewDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime.now(tz) + review_clock_shift["value"]

    monkeypatch.setattr(vaneck_qualification, "datetime", ShiftableReviewDateTime)
    _configure_vaneck_quota_test_ledger(
        provider_db, monkeypatch, backend="postgres", tmp_path=tmp_path
    )
    seeds = dict(settings.PROVIDER_ENTITLEMENT_SEEDS or {})
    seeds.pop("vaneck", None)
    monkeypatch.setattr(settings, "PROVIDER_ENTITLEMENT_SEEDS", seeds)
    async with provider_db() as setup:
        fixture = await _seed_failed_vaneck_posttransport_attempt(provider_db, setup, monkeypatch)
    workbook = _vaneck_initial_qualification_workbook()

    class ControlledTransport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.calls = []
            self.started = threading.Event()
            self.release = threading.Event()

        async def handle_async_request(self, request):
            self.calls.append((request.method, str(request.url)))
            self.started.set()
            if scenario == "caller_cancel":
                if not await asyncio.to_thread(self.release.wait, 5):
                    raise httpx.ReadTimeout("cancellation fixture timed out", request=request)
                return httpx.Response(
                    200,
                    content=workbook,
                    headers={
                        "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    },
                    request=request,
                )
            if scenario == "review_expires_during_fetch":
                review_clock_shift["value"] = timedelta(days=2)
                return httpx.Response(
                    200,
                    content=workbook,
                    headers={
                        "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    },
                    request=request,
                )
            return httpx.Response(503, content=b"controlled publisher failure", request=request)

        async def aclose(self):
            return None

    controlled = ControlledTransport()
    _use_mocktransport(monkeypatch, SimpleNamespace(factory=lambda: controlled))
    kwargs = {
        "requested_by_user_id": fixture["admin_id"],
        "predecessor_job_id": fixture["job3_id"],
        "request_id": str(uuid4()),
        "review_evidence_reference": "root-review:job3-successor-2026-10-30",
        "review_evidence_sha256": "c" * 64,
    }
    if scenario == "caller_cancel":
        async with provider_db() as caller_db:
            with pytest.raises(asyncio.CancelledError):
                async with caller_db.begin():
                    request_task = asyncio.create_task(
                        continue_vaneck_oih_fund(caller_db, **kwargs)
                    )
                    try:
                        assert await asyncio.to_thread(controlled.started.wait, 10)
                        request_task.cancel()
                        await asyncio.sleep(0.02)
                        assert not request_task.done()
                        controlled.release.set()
                        await request_task
                    finally:
                        controlled.release.set()
                        if not request_task.done():
                            request_task.cancel()
                            try:
                                await asyncio.wait_for(request_task, timeout=10)
                            except asyncio.CancelledError:
                                pass
        expected_status = "interrupted"
    else:
        async with provider_db() as request_db:
            result = await continue_vaneck_oih_fund(request_db, **kwargs)
        assert result.status == "failed"
        expected_status = "failed"
    assert controlled.calls == [
        (
            "GET",
            "https://www.vaneck.com/us/en/investments/oil-services-etf-oih/downloads/holdings/?cken=true",
        )
    ]

    async with provider_db() as readback:
        successor = await readback.scalar(
            select(ETFHoldingsBackfillJob).where(
                ETFHoldingsBackfillJob.etf_profile_id == fixture["profile_id"],
                ETFHoldingsBackfillJob.id != fixture["job2_id"],
                ETFHoldingsBackfillJob.id != fixture["job3_id"],
            )
        )
        assert successor is not None and successor.status == expected_status
        outcome = successor.extra_data["qualification_outcome"]
        continuation = successor.extra_data[VANECK_POSTTRANSPORT_CONTINUATION_KEY]
        assert outcome["status"] == "not_qualified"
        assert outcome["provider_attempt_evidence"]["positive_qualification_linked"] is False
        assert continuation["status"] == expected_status
        assert continuation["positive_qualification"] is False
        evidence = outcome["provider_attempt_evidence"]
        callback_ids = evidence["request_log_callback_ids"]
        persisted_ids = evidence["persisted_request_log_ids"]
        assert evidence["all_callback_logs_persisted"] is True
        assert len(callback_ids) == len(persisted_ids) == 1
        assert callback_ids == persisted_ids
        job_scope_ids = successor.extra_data["provider_request_log_ids"]
        if scenario == "http_error":
            # A failed physical attempt is durable evidence, not a positively
            # scope-linked qualification request.
            assert job_scope_ids == []
        else:
            assert job_scope_ids == callback_ids
        log = await readback.get(ProviderRequestLog, persisted_ids[0])
        assert log is not None and log.completed_at is not None
        assert log.http_requests == 1
        assert log.success is (scenario != "http_error")
        if scenario == "http_error":
            assert log.error_type is not None
            assert any(
                "controlled publisher failure" in str(item) for item in log.response_payloads
            )
        assert (
            await readback.scalar(
                select(func.count(ETFHoldingsSnapshot.id)).where(
                    ETFHoldingsSnapshot.etf_profile_id == fixture["profile_id"]
                )
            )
            == 0
        )
        job3 = await readback.get(ETFHoldingsBackfillJob, fixture["job3_id"])
        assert job3 is not None and job3.extra_data == fixture["job3_extra"]
        policy = await readback.get(ProviderPolicy, fixture["case"].policy.id)
        entitlement = await readback.scalar(
            select(ProviderEntitlement).where(
                ProviderEntitlement.data_source_id == fixture["case"].source_id,
                ProviderEntitlement.capability == ProviderCapability.ETF_HOLDINGS,
            )
        )
        assert policy is not None and policy.is_enabled is False
        assert entitlement is not None and entitlement.live_probe_status == "not_run"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ambiguous_evidence",
    [
        "request_log",
        "raw_body",
        "snapshot",
        "filing",
        "diagnostic_hash_mismatch",
        "diagnostic_lineage",
        "diagnostic_payload_altered",
    ],
)
async def test_vaneck_recovery_rejects_any_prior_attempt_artifact(
    provider_db, monkeypatch, ambiguous_evidence
):
    """A sent, retained, or otherwise linked predecessor is never recoverable."""

    from app.models.etf_holdings import (
        ETFHoldingsBackfillFiling,
        ETFHoldingsBackfillJob,
        ETFHoldingsRawArtifact,
    )
    from app.services.etf_holdings_vaneck_qualification import recover_vaneck_oih_fund

    monkeypatch.setattr(settings, "PROVIDER_ROUTING_ENABLED", True)
    monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", True)
    monkeypatch.setattr(settings, "PROVIDER_FREE_ONLY_CHECKPOINT", True)
    monkeypatch.setattr(settings, "ALLOW_PAID_PROVIDER_ROUTING", False)
    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        provider_db.url.render_as_string(hide_password=False),
    )
    runner = _TransportRunner()
    _use_mocktransport(monkeypatch, runner)
    async with provider_db() as setup:
        (
            case,
            profile_id,
            admin_id,
            predecessor_id,
            _,
            started_at,
            completed_at,
            diagnostic_ref,
        ) = await _seed_failed_vaneck_pretransport_attempt(
            setup,
            monkeypatch,
            include_no_body_diagnostic=ambiguous_evidence.startswith("diagnostic_"),
        )
        predecessor = await setup.get(ETFHoldingsBackfillJob, predecessor_id)
        assert predecessor is not None
        evidence_at = started_at + timedelta(milliseconds=250)
        assert evidence_at < completed_at
        if ambiguous_evidence.startswith("diagnostic_"):
            artifact = await setup.get(ETFHoldingsRawArtifact, diagnostic_ref["artifact_id"])
            assert artifact is not None
            if ambiguous_evidence == "diagnostic_hash_mismatch":
                artifact.content_hash = "f" * 64
            elif ambiguous_evidence == "diagnostic_lineage":
                metadata = dict(artifact.legal_metadata)
                metadata["provider_request_log_ids"] = [999999]
                artifact.legal_metadata = metadata
            else:
                payload = dict(artifact.payload_json)
                payload["validation"] = {"fixture_only": True}
                artifact.payload_json = payload
                artifact.content_hash = _hash_payload(payload)
        elif ambiguous_evidence == "request_log":
            setup.add(
                ProviderRequestLog(
                    data_source_id=case.source_id,
                    capability=ProviderCapability.ETF_HOLDINGS,
                    operation="fetch_etf_holdings_latest",
                    instrument_id=case.instrument_id,
                    provider_symbol="OIH",
                    operation_family="etf_holdings",
                    requested_at=evidence_at,
                    completed_at=evidence_at,
                    success=True,
                    http_requests=1,
                    created_at=evidence_at,
                )
            )
        elif ambiguous_evidence == "raw_body":
            setup.add(
                ETFHoldingsRawArtifact(
                    etf_profile_id=profile_id,
                    source_kind="vaneck_initial_qualification",
                    source_url="https://www.vaneck.com/fixture-only",
                    source_identifier="fixture-only",
                    content_hash="f" * 64,
                    fetched_at=evidence_at,
                    parser_version="fixture-only",
                    payload_text="retained fixture body",
                    legal_metadata={"fixture_only": True},
                    created_at=evidence_at,
                )
            )
        elif ambiguous_evidence == "snapshot":
            setup.add(
                ETFHoldingsSnapshot(
                    etf_profile_id=profile_id,
                    composition_date=date.today(),
                    known_at=evidence_at,
                    provenance="fixture-only",
                    source_provider="vaneck",
                    source_quality="fixture-only",
                    completeness_status="complete",
                    row_count=1,
                    resolved_count=0,
                    unresolved_count=1,
                    snapshot_hash=f"fixture-{uuid4().hex}",
                    created_at=evidence_at,
                )
            )
        else:
            setup.add(
                ETFHoldingsBackfillFiling(
                    etf_profile_id=profile_id,
                    last_job_id=predecessor_id,
                    accession_number=f"FIXTURE-{uuid4().hex[:12]}",
                    form="FIXTURE",
                    status="fixture_only",
                    created_at=evidence_at,
                )
            )
        await setup.commit()
        old_extra = dict(predecessor.extra_data)

        with pytest.raises(ETFHoldingsRouteHeldError, match="cannot be recovered|ambiguous"):
            await recover_vaneck_oih_fund(
                setup,
                requested_by_user_id=admin_id,
                predecessor_job_id=predecessor_id,
                review_evidence_reference="operator-note:root-2026-10-29",
                review_evidence_sha256="a" * 64,
                operator_reason="Reject because the predecessor has ambiguous evidence.",
            )

    assert runner.calls == []
    async with provider_db() as readback:
        old = await readback.get(ETFHoldingsBackfillJob, predecessor_id)
        assert old is not None and old.status == "failed"
        assert old.extra_data == old_extra
        assert (
            await readback.scalar(
                select(func.count(ETFHoldingsBackfillJob.id)).where(
                    ETFHoldingsBackfillJob.etf_profile_id == profile_id,
                    ETFHoldingsBackfillJob.job_type == "vaneck_oih_initial_qualification",
                )
            )
            == 1
        )


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
    [
        "wrong_fund_then_match",
        "cross_session_job_link",
        "no_match",
        "real_failure",
        "committed_reference",
        "committed_reference_wrong_body_identity",
        "committed_reference_tampered_audit",
        "invalid_reference_cross_fund",
    ],
)
async def test_initial_sec_qualification_is_one_shot_and_leaves_policy_disabled(
    provider_db, monkeypatch, scenario
):
    """Qualification links child-session logs without deadlocking the parent job transaction."""

    from app.models.etf_holdings import ETFHoldingsBackfillFiling, ETFHoldingsBackfillJob
    from app.services import etf_holdings_edgar as edgar

    # The SEC qualification compatibility matrix predates the issuer-only
    # request-driven scope and has its own sealed SEC authority. Keep that
    # source path on its canonical legacy setting in this fixture.
    monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", False)
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
                if scenario == "real_failure":
                    body = b"SEC filing unavailable"
                elif scenario == "committed_reference_wrong_body_identity":
                    body = wrong_filing_xml.encode()
                else:
                    body = filing_xml.encode()
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
            profile_metadata = {"existing_provenance": {"owner": "preserved"}}
            if scenario in {
                "committed_reference",
                "committed_reference_wrong_body_identity",
                "committed_reference_tampered_audit",
                "invalid_reference_cross_fund",
            }:
                profile_metadata.update(
                    {"source_access": "stale-hint", "fund_identity": {"series_id": "stale"}}
                )
                reference = {
                    "cik": "0001100663",
                    "series_id": "S000004344",
                    "class_id": "C000012074",
                    "form": "NPORT-P",
                    "accession_number": matching_accession,
                    "primary_document": "primary_doc.xml",
                    "filing_date": "2026-10-01",
                    "report_date": "2026-09-30",
                    "acceptance_datetime": "2026-10-01T12:00:00.000Z",
                    "review_provenance": "offline MockTransport fixture review",
                    "reviewed_at": datetime.now(UTC).isoformat(),
                }
                if scenario == "invalid_reference_cross_fund":
                    reference["class_id"] = "C000099999"
                profile_metadata["sec_initial_qualification"] = {"filing_reference": reference}
            profile = ETFProfile(
                instrument_id=instrument.id,
                instrument=instrument,
                adapter_key="edgar_sec_holdings",
                sec_cik="0001100663",
                sec_series_id="S000004344",
                sec_class_id="C000012074",
                provider_aliases={"holdings_source_provider": "edgar"},
                legal_metadata=profile_metadata,
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

    if scenario == "committed_reference_tampered_audit":
        original_backfill = edgar._backfill_sec_holdings

        async def tamper_selection_after_real_backfill(*args, **kwargs):
            summary = await original_backfill(*args, **kwargs)
            job = kwargs["qualification_job"]
            # Isolate the selection mutation from the child's durable request IDs.
            await args[0].refresh(job, attribute_names=["extra_data"])
            extra_data = dict(job.extra_data or {})
            linked_request_ids = list(extra_data.get("provider_request_log_ids") or [])
            assert linked_request_ids
            selection = dict(extra_data["qualification_filing_selection"])
            reference = dict(selection["reference"])
            reference["accession_number"] = wrong_accession
            selection["reference"] = reference
            extra_data["qualification_filing_selection"] = selection
            job.extra_data = extra_data
            await args[0].flush()
            await args[0].refresh(job, attribute_names=["extra_data"])
            assert job.extra_data["provider_request_log_ids"] == linked_request_ids
            return summary

        monkeypatch.setattr(edgar, "_backfill_sec_holdings", tamper_selection_after_real_backfill)

    if scenario == "invalid_reference_cross_fund":
        with pytest.raises(ETFHoldingsRouteHeldError, match="does not match this ETF profile"):
            await qualify_once()
        assert runner.calls == []
        async with provider_db() as readback:
            assert (
                await readback.scalar(
                    select(func.count())
                    .select_from(ETFHoldingsBackfillJob)
                    .where(
                        ETFHoldingsBackfillJob.etf_profile_id == profile_id,
                        ETFHoldingsBackfillJob.job_type == edgar.SEC_INITIAL_QUALIFICATION_JOB_TYPE,
                    )
                )
                == 0
            )
            assert (
                await readback.scalar(
                    select(func.count())
                    .select_from(ProviderRequestLog)
                    .where(ProviderRequestLog.data_source_id == case.source_id)
                )
                == 0
            )
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
            assert policy is not None and policy.is_enabled is False
            assert entitlement is not None and entitlement.live_probe_status == "not_run"
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
        return

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
        "committed_reference",
    }
    if qualification_succeeded:
        assert summary["status"] == "completed"
        assert summary["ingested"] == 1
        if scenario == "wrong_fund_then_match":
            assert len(summary["expected_non_target_fund_discards"]) == 1
        if scenario in {"committed_reference", "committed_reference_wrong_body_identity"}:
            assert runner.calls == [filing_url]
        else:
            expected_calls = [submissions_url]
            if scenario == "wrong_fund_then_match":
                expected_calls.append(wrong_filing_url)
            expected_calls.append(filing_url)
            assert runner.calls == expected_calls
    elif scenario == "committed_reference_wrong_body_identity":
        assert summary["status"] == "partial"
        assert summary["ingested"] == 0
        assert summary.get("expected_non_target_fund_discards", []) == []
        assert runner.calls == [filing_url]
    elif scenario == "committed_reference_tampered_audit":
        assert summary["status"] == "failed"
        assert summary["ingested"] == 1
        assert runner.calls == [filing_url]
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
            if scenario == "committed_reference":
                selection = attempt.extra_data["qualification_filing_selection"]
                assert selection["selection_method"] == "committed_profile_reference"
                assert selection["reference"]["accession_number"] == matching_accession
                assert selection["reference"]["filing_url"] == filing_url
                assert (await readback.get(ETFProfile, profile_id)).legal_metadata[
                    "existing_provenance"
                ] == {"owner": "preserved"}
                committed_profile = await readback.get(ETFProfile, profile_id)
                assert committed_profile.legal_metadata["source_access"] == "sec_filing"
                assert committed_profile.legal_metadata["fund_identity"] == {
                    "series_id": "S000004344",
                    "class_id": "C000012074",
                }
                assert (
                    committed_profile.legal_metadata["sec_initial_qualification"][
                        "filing_reference"
                    ]["accession_number"]
                    == matching_accession
                )
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
                assert scenario in {"cross_session_job_link", "committed_reference"}
                assert discarded_row is None
                if scenario in {"cross_session_job_link", "committed_reference"}:
                    assert all(item.source_identifier != wrong_accession for item in artifacts)
        else:
            assert entitlement.live_probe_status == "not_run"
            assert attempt.status in {"partial", "failed"}
            if scenario == "committed_reference_tampered_audit":
                assert len(snapshots) == 1
            else:
                assert snapshots == []
            assert "qualification_outcome" in attempt.extra_data
            assert attempt.extra_data["qualification_outcome"]["status"] == "not_qualified"
        expected_operations = {"fetch_etf_holdings_sec_filing"}
        if scenario not in {
            "committed_reference",
            "committed_reference_wrong_body_identity",
            "committed_reference_tampered_audit",
        }:
            expected_operations.add("fetch_etf_holdings_sec_submissions")
        assert {row.operation for row in logs} == expected_operations
        assert all(row.http_requests == 1 for row in logs)
        if qualification_succeeded:
            assert all(row.success and row.settled_usage_units == Decimal("1.0000") for row in logs)
        if scenario == "committed_reference_wrong_body_identity":
            assert len(logs) == 1
            assert logs[0].operation == "fetch_etf_holdings_sec_filing"
            assert (
                logs[0].success is True
            )  # HTTP 200 succeeded; the returned fund identity did not.
            assert logs[0].settled_usage_units == Decimal("1.0000")
            assert attempt.status == "partial"
            assert entitlement.live_probe_status == "not_run"
            assert snapshots == []
            selection = attempt.extra_data["qualification_filing_selection"]
            assert selection["selection_method"] == "committed_profile_reference"
            assert selection["reference"]["accession_number"] == matching_accession
            assert selection["reference"]["filing_url"] == filing_url
            profile_after_ingest = await readback.get(ETFProfile, profile_id)
            assert profile_after_ingest.legal_metadata == profile_metadata
            rejected = next(
                item for item in artifacts if item.source_identifier == matching_accession
            )
            assert rejected.payload_text == wrong_filing_xml
            assert rejected.content_hash == _hash_payload(wrong_filing_xml)
            rejected_filing = await readback.scalar(
                select(ETFHoldingsBackfillFiling).where(
                    ETFHoldingsBackfillFiling.etf_profile_id == profile_id,
                    ETFHoldingsBackfillFiling.accession_number == matching_accession,
                )
            )
            assert rejected_filing is not None and rejected_filing.status == "skipped"
            assert rejected_filing.extra_data["identity_validation"]["observed"] == {
                "series_id": "S000009999",
                "class_id": "C000099999",
            }
            assert (
                rejected_filing.extra_data["identity_validation"]["qualification_disposition"]
                is None
            )
            rejected_raw = next(
                item for item in artifacts if item.source_identifier == matching_accession
            )
            assert rejected_raw.legal_metadata["validation"]["observed_filing_identity"] == {
                "series_id": "S000009999",
                "class_id": "C000099999",
            }
            assert rejected_raw.legal_metadata["provider_request_log_ids"] == [logs[0].id]
            assert attempt.extra_data["provider_request_log_ids"] == [logs[0].id]
        if scenario == "committed_reference_tampered_audit":
            assert attempt.status == "failed"
            assert entitlement.live_probe_status == "not_run"
            selection = attempt.extra_data["qualification_filing_selection"]
            assert selection["reference"]["accession_number"] == wrong_accession
            assert attempt.extra_data["qualification_outcome"]["status"] == "not_qualified"
            assert "selection_audit_is_missing_or_tampered" in attempt.failure_reason
            committed_profile = await readback.get(ETFProfile, profile_id)
            assert committed_profile.legal_metadata["existing_provenance"] == {"owner": "preserved"}
            assert committed_profile.legal_metadata["source_access"] == "sec_filing"
            assert committed_profile.legal_metadata["fund_identity"] == {
                "series_id": "S000004344",
                "class_id": "C000012074",
            }
            assert (
                committed_profile.legal_metadata["sec_initial_qualification"]["filing_reference"][
                    "accession_number"
                ]
                == matching_accession
            )
            assert len(logs) == 1
            assert logs[0].operation == "fetch_etf_holdings_sec_filing"
            assert logs[0].success is True
            assert logs[0].settled_usage_units == Decimal("1.0000")

    with pytest.raises(ETFHoldingsRouteHeldError, match="already has a latched"):
        async with provider_db() as replay:
            await edgar.qualify_sec_nport_fund(
                replay,
                profile_id=profile_id,
                requested_by_user_id=None,
            )
    if qualification_succeeded:
        if scenario in {
            "committed_reference",
            "committed_reference_wrong_body_identity",
            "committed_reference_tampered_audit",
        }:
            assert runner.calls == [filing_url]
        else:
            expected_calls = [submissions_url]
            if scenario == "wrong_fund_then_match":
                expected_calls.append(wrong_filing_url)
            expected_calls.append(filing_url)
            assert runner.calls == expected_calls
    elif scenario in {
        "committed_reference_wrong_body_identity",
        "committed_reference_tampered_audit",
    }:
        assert runner.calls == [filing_url]
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
    if scenario in {
        "committed_reference_wrong_body_identity",
        "committed_reference_tampered_audit",
    }:
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
