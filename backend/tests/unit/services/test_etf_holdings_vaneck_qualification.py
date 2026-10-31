from __future__ import annotations

import asyncio
import hashlib
import sqlite3
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import insert

from app.config import settings
from app.models.data_source import DataSource
from app.models.provider_runtime import ProviderEntitlement, ProviderPolicy
from app.services import etf_holdings_provider_bridge as bridge
from app.services import etf_holdings_vaneck_qualification as qualification
from app.services import provider_quota_coordinator as quota
from app.services.etf_holdings_provider_bridge import (
    ETFHoldingsRouteHeldError,
    ETFVaneckInitialQualificationBudget,
)
from app.services.etf_holdings_vaneck_qualification import (
    VANECK_OIH_INITIAL_QUALIFICATION_JOB_TYPE,
    VANECK_OIH_INITIAL_QUALIFICATION_OPERATION,
    VANECK_OIH_INITIAL_QUOTA_DIMENSION,
    VANECK_OIH_INITIAL_QUOTA_GROUP,
    VANECK_OIH_INITIAL_URL,
    VANECK_OIH_PRODUCT_SLUG,
    _current_vaneck_application_usage_projection,
    _lock_and_validate_current_provider_review,
    _posttransport_request_fingerprint,
    _provider_review_fingerprint,
    _quota_activity_exists_since_attempt,
    _verified_posttransport_spent_reservation,
)
from app.services.provider_runtime import (
    ProviderCapability,
    bind_vaneck_initial_etf_qualification,
)


def test_posttransport_request_fingerprint_keeps_legacy_default_and_separates_job4_contract():
    shared = {
        "predecessor_job_id": 4,
        "request_id": "d6b08d78-ea66-4b2c-b1b1-0871634219ba",
        "review_evidence_reference": "root-review:job4-settlement-successor-2026-10-30",
        "review_evidence_sha256": "e" * 64,
        "requested_by_user_id": 7,
    }
    omitted_contract = _posttransport_request_fingerprint(**shared)
    explicit_legacy = _posttransport_request_fingerprint(
        **shared,
        predecessor_contract="job3_posttransport_linkage_v1",
        predecessor_extra_data_sha256=None,
    )
    job4_contract = _posttransport_request_fingerprint(
        **shared,
        predecessor_contract="job4_settlement_projection_v1",
        predecessor_extra_data_sha256="a" * 64,
    )

    assert omitted_contract == explicit_legacy
    assert job4_contract != omitted_contract
    assert job4_contract != _posttransport_request_fingerprint(
        **shared,
        predecessor_contract="job4_settlement_projection_v1",
        predecessor_extra_data_sha256="b" * 64,
    )


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ({}, ("call_count", "requests")),
        (
            {"usage_tracking": {"mode": "call_count", "unit_label": "requests"}},
            ("call_count", "requests"),
        ),
        (
            {"usage_tracking": {"mode": "call_count", "unit_label": "physical_http_requests"}},
            None,
        ),
        ({"usage_tracking": {"mode": "native_usage", "unit_label": "requests"}}, None),
        ({"usage_tracking": "invalid"}, ("call_count", "requests")),
    ],
)
def test_job4_continuation_requires_current_request_count_projection(config, expected):
    assert _current_vaneck_application_usage_projection(SimpleNamespace(config=config)) == expected


def _seed_quota_ledger_history(monkeypatch, path, *, matching_activity=None):
    url = f"sqlite:///{path}"
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_DATABASE_URL", url)
    engine = quota._engine_for(url)
    now = datetime.now(UTC)
    with engine.begin() as connection:
        connection.execute(
            insert(quota._reservations).values(
                reservation_id="00000000-0000-4000-8000-000000000001",
                provider_name="other-provider",
                account_scope="other-account",
                operation="unrelated_operation",
                quota_group="unrelated",
                dimension="requests",
                unit="requests",
                window_started_at=now - timedelta(days=2),
                window_seconds=60,
                reserved_units=1,
                release_only=False,
                lease_expires_at=None,
                identity_digest=None,
                state="settled",
                created_at=now - timedelta(days=2),
                settled_at=now - timedelta(days=2),
            )
        )
        if matching_activity in {"pending", "uncertain"}:
            connection.execute(
                insert(quota._reservations).values(
                    reservation_id="00000000-0000-4000-8000-000000000002",
                    provider_name="vaneck",
                    account_scope="reviewed-oih-account",
                    operation=VANECK_OIH_INITIAL_QUALIFICATION_OPERATION,
                    quota_group="etf_holdings",
                    dimension="requests",
                    unit="requests",
                    window_started_at=now - timedelta(minutes=1),
                    window_seconds=60,
                    reserved_units=1,
                    release_only=False,
                    lease_expires_at=None,
                    identity_digest=None,
                    state=matching_activity,
                    created_at=now - timedelta(seconds=5),
                    settled_at=None,
                )
            )
        elif matching_activity in {
            "receipt",
            "receipt_linked_target",
            "other_account_receipt",
            "orphan_receipt",
            "mismatched_receipt",
            "mismatched_operation_receipt",
        }:
            receipt_reservation_id = "00000000-0000-4000-8000-000000000003"
            if matching_activity != "orphan_receipt":
                connection.execute(
                    insert(quota._reservations).values(
                        reservation_id=receipt_reservation_id,
                        provider_name=(
                            "other-provider"
                            if matching_activity == "mismatched_receipt"
                            else "vaneck"
                        ),
                        account_scope=(
                            "another-account"
                            if matching_activity == "other_account_receipt"
                            else "reviewed-oih-account"
                        ),
                        operation=VANECK_OIH_INITIAL_QUALIFICATION_OPERATION,
                        quota_group="etf_holdings",
                        dimension="requests",
                        unit="requests",
                        window_started_at=now - timedelta(minutes=1),
                        window_seconds=60,
                        reserved_units=1,
                        release_only=False,
                        lease_expires_at=None,
                        identity_digest=None,
                        state="uncertain",
                        created_at=(
                            now - timedelta(minutes=2)
                            if matching_activity == "receipt_linked_target"
                            else now - timedelta(seconds=5)
                        ),
                        settled_at=None,
                    )
                )
            connection.execute(
                insert(quota._live_receipts).values(
                    reservation_id=receipt_reservation_id,
                    provider_name="vaneck",
                    operation=(
                        "other_operation"
                        if matching_activity == "mismatched_operation_receipt"
                        else VANECK_OIH_INITIAL_QUALIFICATION_OPERATION
                    ),
                    run_id="synthetic-run",
                    # Receipt usage_scope is deliberately not the ledger's
                    # account_scope; only reservation linkage proves account.
                    usage_scope="synthetic-provider-usage-label",
                    receipt_status="observed",
                    reconciliation_state="uncertain",
                    created_at=now - timedelta(seconds=5),
                    reconciled_at=None,
                    error=None,
                )
            )
    engine.dispose()
    return url, now


def test_recovery_ledger_check_does_not_create_missing_file(tmp_path, monkeypatch):
    missing_path = tmp_path / "missing-ledger.sqlite3"
    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_DATABASE_URL",
        f"sqlite:///{missing_path}",
    )

    with pytest.raises(ETFHoldingsRouteHeldError, match="ledger is unavailable"):
        _quota_activity_exists_since_attempt(
            account_scope="reviewed-oih-account",
            started_at=datetime.now(UTC) - timedelta(minutes=1),
            completed_at=datetime.now(UTC),
        )

    assert not missing_path.exists()


@pytest.mark.parametrize(
    ("quota_group", "dimension", "accepted"),
    [
        ("oih_first_sample", "vaneck_oih_first_sample_requests_120s", True),
        ("requests", "vaneck_oih_first_sample_requests_120s", False),
        ("oih_first_sample", "requests", False),
        ("requests", "requests", False),
    ],
)
def test_posttransport_spent_reservation_requires_exact_retained_oih_scope(
    tmp_path, monkeypatch, quota_group, dimension, accepted
):
    """Only the actual historical VanEck group/dimension pair proves spent use."""
    path = tmp_path / "posttransport-spent-oih.sqlite3"
    url = f"sqlite:///{path}"
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_DATABASE_URL", url)
    engine = quota._engine_for(url)
    quota.metadata.create_all(engine)
    created_at = datetime(2026, 10, 30, 0, 38, 48, 483760, tzinfo=UTC)
    settled_at = datetime(2026, 10, 30, 0, 38, 48, 836210, tzinfo=UTC)
    started_at = created_at - timedelta(seconds=8)
    completed_at = settled_at + timedelta(seconds=1)
    with engine.begin() as connection:
        connection.execute(
            insert(quota._reservations).values(
                id=41361,
                reservation_id="78b87a43-d20e-4155-9faa-923be65b4653",
                provider_name="vaneck",
                account_scope="reviewed-oih-account",
                operation=VANECK_OIH_INITIAL_QUALIFICATION_OPERATION,
                quota_group=quota_group,
                dimension=dimension,
                unit="requests",
                window_started_at=started_at,
                window_seconds=120,
                reserved_units=1,
                release_only=False,
                lease_expires_at=None,
                identity_digest=None,
                state="settled",
                created_at=created_at,
                settled_at=settled_at,
            )
        )
    engine.dispose()
    ledger_before = hashlib.sha256(path.read_bytes()).hexdigest()

    if accepted:
        proof = _verified_posttransport_spent_reservation(
            account_scope="reviewed-oih-account",
            started_at=started_at,
            completed_at=completed_at,
        )
        assert proof["reservation_id"] == "78b87a43-d20e-4155-9faa-923be65b4653"
        assert proof["quota_group"] == VANECK_OIH_INITIAL_QUOTA_GROUP
        assert proof["dimension"] == VANECK_OIH_INITIAL_QUOTA_DIMENSION
        assert proof["unit"] == "requests"
        assert proof["reserved_units"] == 1
        assert proof["state"] == "settled"
        assert proof["live_receipt_present"] is False
    else:
        with pytest.raises(ETFHoldingsRouteHeldError, match="settled OIH usage unit"):
            _verified_posttransport_spent_reservation(
                account_scope="reviewed-oih-account",
                started_at=started_at,
                completed_at=completed_at,
            )

    assert hashlib.sha256(path.read_bytes()).hexdigest() == ledger_before


@pytest.mark.parametrize("activity", ["pending", "uncertain", "receipt", "receipt_linked_target"])
def test_recovery_ledger_check_rejects_matching_reservation_or_receipt(
    tmp_path, monkeypatch, activity
):
    path = tmp_path / f"ledger-{activity}.sqlite3"
    _, now = _seed_quota_ledger_history(monkeypatch, path, matching_activity=activity)
    before = hashlib.sha256(path.read_bytes()).hexdigest()

    assert _quota_activity_exists_since_attempt(
        account_scope="reviewed-oih-account",
        started_at=now - timedelta(seconds=10),
        completed_at=now,
    )
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_recovery_ledger_ignores_receipt_only_when_linkage_proves_other_account(
    tmp_path, monkeypatch
):
    path = tmp_path / "ledger-other-account-receipt.sqlite3"
    _, now = _seed_quota_ledger_history(
        monkeypatch, path, matching_activity="other_account_receipt"
    )
    before = hashlib.sha256(path.read_bytes()).hexdigest()

    assert not _quota_activity_exists_since_attempt(
        account_scope="reviewed-oih-account",
        started_at=now - timedelta(seconds=10),
        completed_at=now,
    )
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


@pytest.mark.parametrize(
    "activity", ["orphan_receipt", "mismatched_receipt", "mismatched_operation_receipt"]
)
def test_recovery_ledger_rejects_orphan_or_mismatched_receipt_linkage(
    tmp_path, monkeypatch, activity
):
    path = tmp_path / f"ledger-{activity}.sqlite3"
    _, now = _seed_quota_ledger_history(monkeypatch, path, matching_activity=activity)
    before = hashlib.sha256(path.read_bytes()).hexdigest()

    assert _quota_activity_exists_since_attempt(
        account_scope="reviewed-oih-account",
        started_at=now - timedelta(seconds=10),
        completed_at=now,
    )
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_recovery_ledger_check_allows_only_unrelated_prior_history(tmp_path, monkeypatch):
    path = tmp_path / "ledger-history.sqlite3"
    _, now = _seed_quota_ledger_history(monkeypatch, path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()

    assert not _quota_activity_exists_since_attempt(
        account_scope="reviewed-oih-account",
        started_at=now - timedelta(seconds=10),
        completed_at=now,
    )
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_recovery_ledger_rejects_memory_sqlite_config(monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_DATABASE_URL", "sqlite:///:memory:")
    with pytest.raises(ETFHoldingsRouteHeldError, match="URI is unsupported"):
        _quota_activity_exists_since_attempt(
            account_scope="reviewed-oih-account",
            started_at=datetime.now(UTC) - timedelta(minutes=1),
            completed_at=datetime.now(UTC),
        )


@pytest.mark.parametrize("uri_style", ["file_uri", "path_query"])
def test_recovery_ledger_rejects_sqlite_uri_options_without_creating_file(
    tmp_path, monkeypatch, uri_style
):
    uri_path = tmp_path / "uri-ledger.sqlite3"
    ledger_url = (
        f"sqlite:///file:{uri_path}?mode=ro&uri=true"
        if uri_style == "file_uri"
        else f"sqlite:///{uri_path}?immutable=1"
    )
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_DATABASE_URL", ledger_url)

    with pytest.raises(ETFHoldingsRouteHeldError, match="URI is unsupported"):
        _quota_activity_exists_since_attempt(
            account_scope="reviewed-oih-account",
            started_at=datetime.now(UTC) - timedelta(minutes=1),
            completed_at=datetime.now(UTC),
        )
    assert not uri_path.exists()


def test_recovery_ledger_rejects_incomplete_schema_without_mutating_file(tmp_path, monkeypatch):
    path = tmp_path / "incomplete-ledger.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_DATABASE_URL", f"sqlite:///{path}")

    with pytest.raises(ETFHoldingsRouteHeldError, match="schema is incomplete"):
        _quota_activity_exists_since_attempt(
            account_scope="reviewed-oih-account",
            started_at=datetime.now(UTC) - timedelta(minutes=1),
            completed_at=datetime.now(UTC),
        )
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_recovery_ledger_fails_closed_on_unreadable_existing_ledger(tmp_path, monkeypatch):
    path = tmp_path / "ledger-connection-error.sqlite3"
    _seed_quota_ledger_history(monkeypatch, path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_DATABASE_URL", f"sqlite:///{path}")

    def fail_connection(*args, **kwargs):
        raise PermissionError("fixture-only unreadable ledger")

    monkeypatch.setattr(qualification, "create_engine", fail_connection)
    with pytest.raises(ETFHoldingsRouteHeldError, match="could not be verified read-only"):
        _quota_activity_exists_since_attempt(
            account_scope="reviewed-oih-account",
            started_at=datetime.now(UTC) - timedelta(minutes=1),
            completed_at=datetime.now(UTC),
        )
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


@pytest.mark.asyncio
async def test_review_revision_changed_during_fetch_denies_positive_finalization(monkeypatch):
    """A post-fetch lock must observe and reject a concurrent review revision."""

    source = SimpleNamespace(
        id=17,
        name="vaneck",
        base_url="https://www.vaneck.com",
        supported_capabilities=["etf_holdings"],
        is_active=True,
        config={"etf_holdings_review": {"revision": 4}, "usage_tracking": True},
    )
    policy = SimpleNamespace(
        is_enabled=False,
        quota_scope="oih-reviewed-account",
        quota_source="operator-reviewed account record",
        quota_verified_at="2026-10-27T00:00:00+00:00",
        quota_contract={"status": "reviewed"},
        max_concurrency=1,
        tokens_per_minute=2,
        burst_capacity=1,
        cooldown_seconds=30,
        freshness_seconds=3600,
    )
    entitlement = SimpleNamespace(
        revision=4,
        configured_plan="application-only",
        is_free=True,
        authentication_required=False,
        usage_terms="personal-use review",
        redistribution_allowed=False,
        quota_policy={"scope": "oih-reviewed-account"},
        history_depth=None,
        venue_coverage="US-listed ETF holdings",
        freshness_semantics="issuer composition date",
        enabled_environments=["application"],
        effective_at=None,
        review_due_at=None,
        live_probe_status="not_run",
    )
    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_ACCOUNT_SCOPES",
        {"vaneck:oih-reviewed-account": "oih-reviewed-account"},
    )
    initial_fingerprint = _provider_review_fingerprint(source, policy, entitlement)

    class SessionAfterFetch:
        def __init__(self):
            self.rows = {
                DataSource: source,
                ProviderPolicy: policy,
                ProviderEntitlement: entitlement,
            }
            self.statements = []

        async def scalar(self, statement):
            self.statements.append(statement)
            assert statement._execution_options.get("populate_existing") is True
            assert statement._for_update_arg is not None
            return self.rows[statement.column_descriptions[0]["entity"]]

    db = SessionAfterFetch()

    # Simulate an operator committing a new review while the workbook request
    # is in flight. The in-memory objects are the changed database values that
    # the locked populate_existing reads must use.
    entitlement.revision = 5
    entitlement.usage_terms = "revised after request began"

    with pytest.raises(ETFHoldingsRouteHeldError, match="review changed during qualification"):
        await _lock_and_validate_current_provider_review(
            db,  # type: ignore[arg-type]
            source_id=source.id,
            expected_fingerprint=initial_fingerprint,
            expected_revision=4,
            expected_account_scope="oih-reviewed-account",
        )

    assert len(db.statements) == 3
    assert policy.is_enabled is False
    assert entitlement.live_probe_status == "not_run"
    assert entitlement.revision == 5


def _vaneck_job_fixture(authority):
    return SimpleNamespace(
        id=authority.job_id,
        job_type=VANECK_OIH_INITIAL_QUALIFICATION_JOB_TYPE,
        source_provider="vaneck",
        etf_profile_id=authority.fund_profile_id,
        status="running",
        started_at=datetime.now(UTC) - timedelta(seconds=1),
        extra_data={
            "qualification_scope": {
                "provider": "vaneck",
                "capability": ProviderCapability.ETF_HOLDINGS.value,
                "operation": VANECK_OIH_INITIAL_QUALIFICATION_OPERATION,
                "profile_id": authority.fund_profile_id,
                "instrument_id": authority.instrument_id,
                "provider_symbol": authority.provider_symbol,
                "product_slug": VANECK_OIH_PRODUCT_SLUG,
                "request_url": VANECK_OIH_INITIAL_URL,
                "allowed_initial_host": "www.vaneck.com",
                "account_scope": authority.account_scope,
                "review_revision": authority.review_revision,
                "expires_at": authority.expires_at.isoformat(),
            },
            "provider_request_log_ids": [],
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tamper",
    [
        "job_id",
        "job_type",
        "source_provider",
        "job_profile",
        "job_status",
        "scope_provider",
        "scope_operation",
        "scope_profile",
        "scope_instrument",
        "scope_symbol",
        "scope_account",
        "scope_revision",
        "scope_expiry",
        "scope_url",
        "existing_request_ids",
        "entitlement_revision",
        "authority_account",
    ],
)
async def test_disabled_vaneck_pre_review_requires_exact_sealed_running_job_scope(
    monkeypatch, tamper
):
    """The pre-review exception is limited to the committed one-shot OIH job."""

    account_scope = "synthetic-oih-account"
    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_ACCOUNT_SCOPES",
        {"vaneck:reviewed": account_scope},
    )
    now = datetime.now(UTC)
    revision = 7
    authority_scope = "other-synthetic-account" if tamper == "authority_account" else account_scope
    policy = SimpleNamespace(is_enabled=False, quota_scope="reviewed")
    entitlement = SimpleNamespace(live_probe_status="not_run", revision=revision)

    class FakeDB:
        def __init__(self):
            self.job = None

        async def get(self, model, job_id):
            assert model.__name__ == "ETFHoldingsBackfillJob"
            return self.job if self.job and self.job.id == job_id else None

    db = FakeDB()
    with bind_vaneck_initial_etf_qualification(
        job_id=41,
        fund_profile_id=10,
        instrument_id=20,
        provider_symbol="OIH",
        account_scope=authority_scope,
        review_revision=revision,
        expires_at=now + timedelta(minutes=1),
    ) as authority:
        job = _vaneck_job_fixture(authority)
        db.job = job
        scope = job.extra_data["qualification_scope"]
        if tamper == "job_id":
            job.id += 1
        elif tamper == "job_type":
            job.job_type = "ordinary_etf_refresh"
        elif tamper == "source_provider":
            job.source_provider = "edgar"
        elif tamper == "job_profile":
            job.etf_profile_id += 1
        elif tamper == "job_status":
            job.status = "interrupted"
        elif tamper == "scope_provider":
            scope["provider"] = "edgar"
        elif tamper == "scope_operation":
            scope["operation"] = "fetch_etf_holdings_for_date"
        elif tamper == "scope_profile":
            scope["profile_id"] += 1
        elif tamper == "scope_instrument":
            scope["instrument_id"] += 1
        elif tamper == "scope_symbol":
            scope["provider_symbol"] = "SPY"
        elif tamper == "scope_account":
            scope["account_scope"] = "different-account"
        elif tamper == "scope_revision":
            scope["review_revision"] += 1
        elif tamper == "scope_expiry":
            scope["expires_at"] = (authority.expires_at + timedelta(seconds=1)).isoformat()
        elif tamper == "scope_url":
            scope["request_url"] = "https://www.vaneck.com/other-fund.xlsx"
        elif tamper == "existing_request_ids":
            job.extra_data["provider_request_log_ids"] = [999]
        elif tamper == "entitlement_revision":
            entitlement.revision += 1

        with bridge.bind_etf_holdings_request_context(
            db=db,  # type: ignore[arg-type]
            adapter=SimpleNamespace(source_provider="vaneck"),
            profile_id=10,
            instrument_id=20,
            provider_symbol="OIH",
            operation=VANECK_OIH_INITIAL_QUALIFICATION_OPERATION,
            vaneck_initial_qualification_budget=ETFVaneckInitialQualificationBudget(
                expected_url=VANECK_OIH_INITIAL_URL,
                deadline_monotonic=10**12,
            ),
            vaneck_initial_qualification_job_id=authority.job_id,
            vaneck_initial_qualification_authority=authority,
        ):
            if tamper == "authority_account":
                assert not await bridge._vaneck_initial_job_scope_matches(
                    db,  # type: ignore[arg-type]
                    provider_name="vaneck",
                    profile_id=10,
                    instrument_id=20,
                    provider_symbol="OIH",
                    operation=VANECK_OIH_INITIAL_QUALIFICATION_OPERATION,
                    request_url=VANECK_OIH_INITIAL_URL,
                    account_scope=account_scope,
                    policy=policy,
                    entitlement=entitlement,
                )
            else:
                assert not await bridge._vaneck_initial_job_scope_matches(
                    db,  # type: ignore[arg-type]
                    provider_name="vaneck",
                    profile_id=10,
                    instrument_id=20,
                    provider_symbol="OIH",
                    operation=VANECK_OIH_INITIAL_QUALIFICATION_OPERATION,
                    request_url=VANECK_OIH_INITIAL_URL,
                    account_scope=account_scope,
                    policy=policy,
                    entitlement=entitlement,
                )


@pytest.mark.asyncio
async def test_expired_vaneck_authority_cannot_open_disabled_policy_pre_review(monkeypatch):
    account_scope = "synthetic-oih-account"
    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_ACCOUNT_SCOPES",
        {"vaneck:reviewed": account_scope},
    )
    now = datetime.now(UTC)
    policy = SimpleNamespace(is_enabled=False, quota_scope="reviewed")
    entitlement = SimpleNamespace(live_probe_status="not_run", revision=7)

    class FakeDB:
        async def get(self, _model, _job_id):
            raise AssertionError("expired authority must be rejected before job lookup")

    with bind_vaneck_initial_etf_qualification(
        job_id=41,
        fund_profile_id=10,
        instrument_id=20,
        provider_symbol="OIH",
        account_scope=account_scope,
        review_revision=7,
        expires_at=now + timedelta(milliseconds=1),
    ) as authority:
        await asyncio.sleep(0.01)
        with bridge.bind_etf_holdings_request_context(
            db=FakeDB(),  # type: ignore[arg-type]
            adapter=SimpleNamespace(source_provider="vaneck"),
            profile_id=10,
            instrument_id=20,
            provider_symbol="OIH",
            operation=VANECK_OIH_INITIAL_QUALIFICATION_OPERATION,
            vaneck_initial_qualification_budget=ETFVaneckInitialQualificationBudget(
                expected_url=VANECK_OIH_INITIAL_URL,
                deadline_monotonic=10**12,
            ),
            vaneck_initial_qualification_job_id=authority.job_id,
            vaneck_initial_qualification_authority=authority,
        ):
            assert not await bridge._vaneck_initial_job_scope_matches(
                FakeDB(),  # type: ignore[arg-type]
                provider_name="vaneck",
                profile_id=10,
                instrument_id=20,
                provider_symbol="OIH",
                operation=VANECK_OIH_INITIAL_QUALIFICATION_OPERATION,
                request_url=VANECK_OIH_INITIAL_URL,
                account_scope=account_scope,
                policy=policy,
                entitlement=entitlement,
            )


def test_vaneck_review_expiry_guard_preserves_nullable_schedule_semantics():
    qualification._assert_provider_review_not_expired(
        SimpleNamespace(review_due_at=None)  # type: ignore[arg-type]
    )
    qualification._assert_provider_review_not_expired(
        SimpleNamespace(review_due_at=datetime.now(UTC) + timedelta(days=1))  # type: ignore[arg-type]
    )
    with pytest.raises(ETFHoldingsRouteHeldError, match="review is expired"):
        qualification._assert_provider_review_not_expired(
            SimpleNamespace(review_due_at=datetime.now(UTC) - timedelta(seconds=1))  # type: ignore[arg-type]
        )
