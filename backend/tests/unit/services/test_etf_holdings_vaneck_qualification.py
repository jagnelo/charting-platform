from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.config import settings
from app.models.data_source import DataSource
from app.models.provider_runtime import ProviderEntitlement, ProviderPolicy
from app.services import etf_holdings_provider_bridge as bridge
from app.services.etf_holdings_provider_bridge import (
    ETFHoldingsRouteHeldError,
    ETFVaneckInitialQualificationBudget,
)
from app.services.etf_holdings_vaneck_qualification import (
    VANECK_OIH_INITIAL_QUALIFICATION_JOB_TYPE,
    VANECK_OIH_INITIAL_QUALIFICATION_OPERATION,
    VANECK_OIH_INITIAL_URL,
    VANECK_OIH_PRODUCT_SLUG,
    _lock_and_validate_current_provider_review,
    _provider_review_fingerprint,
)
from app.services.provider_runtime import (
    ProviderCapability,
    bind_vaneck_initial_etf_qualification,
)


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
