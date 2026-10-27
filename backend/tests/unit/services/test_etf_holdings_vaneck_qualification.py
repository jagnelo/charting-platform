from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.config import settings
from app.models.data_source import DataSource
from app.models.provider_runtime import ProviderEntitlement, ProviderPolicy
from app.services.etf_holdings_provider_bridge import ETFHoldingsRouteHeldError
from app.services.etf_holdings_vaneck_qualification import (
    _lock_and_validate_current_provider_review,
    _provider_review_fingerprint,
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
