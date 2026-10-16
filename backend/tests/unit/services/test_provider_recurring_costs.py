from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.models.data_source import DataSource
from app.models.provider_recurring_cost import (
    ProviderRecurringCostBudget,
    ProviderRecurringCostBudgetRevision,
    ProviderRecurringCostCommitment,
    ProviderRecurringCostCommitmentRevision,
)
from app.services.provider_recurring_costs import (
    admit_provider_recurring_cost,
    configure_provider_recurring_cost_budget,
    provider_recurring_cost_status,
)

NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)


def _source(db, name: str) -> DataSource:
    source = DataSource(name=name, is_active=True)
    db.add(source)
    db.flush()
    return source


def _budget(db, ceiling="20.00", currency="USD"):
    return configure_provider_recurring_cost_budget(
        db,
        monthly_ceiling=ceiling,
        currency=currency,
        evidence_source="reviewed operator plan",
        evidence_version="2026-10-16",
        reviewed_at=NOW,
    )


def _admit(db, source_id, **overrides):
    values = {
        "data_source_id": source_id,
        "environment": "production",
        "billing_account_scope": "opaque-account-scope-1",
        "configured_plan": "reviewed-basic",
        "state": "active",
        "amount": "12.00",
        "currency": "USD",
        "interval_unit": "month",
        "interval_count": 1,
        "evidence_source": "provider pricing page",
        "evidence_version": "2026-10-16",
        "evidence_observed_at": NOW,
        "effective_at": NOW,
    }
    values.update(overrides)
    return admit_provider_recurring_cost(db, **values)


def test_recurring_cost_requires_an_explicit_budget_and_reviewed_evidence(db):
    source = _source(db, "cost-no-budget")
    decision = _admit(db, source.id)
    assert not decision.allowed
    assert decision.reason_code == "budget_not_configured"
    assert decision.paid_activation_authorized is False
    assert db.scalar(select(ProviderRecurringCostCommitment)) is None

    malformed = configure_provider_recurring_cost_budget(
        db,
        monthly_ceiling="20",
        currency="USD",
        evidence_source="",
        evidence_version="v1",
        reviewed_at=NOW,
    )
    assert not malformed.allowed
    assert malformed.reason_code == "budget_configuration_unreviewed"
    assert db.scalar(select(ProviderRecurringCostBudget)) is None


def test_account_plan_is_counted_once_across_keys_and_revisions_are_retained(db):
    source = _source(db, "cost-shared-account")
    assert _budget(db).allowed
    first = _admit(db, source.id, amount="120", interval_unit="year")
    assert first.allowed
    assert first.proposed_monthly == Decimal("10.0000")
    assert first.remaining_monthly == Decimal("10.0000")
    assert first.paid_activation_authorized is False

    # The same opaque provider account scope under another capability/key
    # revises the one account commitment instead of creating a second charge.
    second = _admit(
        db,
        source.id,
        environment="Production",
        amount="144",
        interval_unit="year",
        evidence_version="pricing-revision-2",
    )
    assert second.allowed
    assert second.commitment_id == first.commitment_id
    assert second.revision == 2
    assert second.proposed_monthly == Decimal("12.0000")
    assert second.remaining_monthly == Decimal("8.0000")
    assert len(list(db.scalars(select(ProviderRecurringCostCommitment)))) == 1
    assert len(list(db.scalars(select(ProviderRecurringCostCommitmentRevision)))) == 2
    assert provider_recurring_cost_status(db).committed_monthly == Decimal("12.0000")
    assert db.scalar(select(ProviderRecurringCostCommitment)).environment == "production"


def test_reviewed_free_forever_commitment_uses_zero_budget_and_never_activates_provider(db):
    source = _source(db, "cost-free-forever")
    assert _budget(db).allowed

    decision = _admit(db, source.id, configured_plan="free-forever", amount="0")

    assert decision.allowed
    assert decision.proposed_monthly == Decimal("0.0000")
    assert decision.committed_monthly == Decimal("0.0000")
    assert decision.remaining_monthly == Decimal("20.0000")
    assert decision.paid_activation_authorized is False
    stored = db.scalar(select(ProviderRecurringCostCommitment))
    assert stored is not None
    assert stored.configured_plan == "free-forever"
    assert stored.monthly_equivalent == Decimal("0.0000")
    assert provider_recurring_cost_status(db).committed_monthly == Decimal("0.0000")


def test_distinct_accounts_aggregate_and_over_ceiling_proposal_is_not_persisted(db):
    first_source = _source(db, "cost-provider-a")
    second_source = _source(db, "cost-provider-b")
    _budget(db)
    assert _admit(db, first_source.id, amount="12").allowed
    denied = _admit(
        db,
        second_source.id,
        billing_account_scope="opaque-account-scope-2",
        amount="9",
    )
    assert not denied.allowed
    assert denied.reason_code == "monthly_ceiling_exceeded"
    assert denied.committed_monthly == Decimal("12.0000")
    assert denied.proposed_monthly == Decimal("9.0000")
    assert len(list(db.scalars(select(ProviderRecurringCostCommitment)))) == 1


def test_currency_mismatch_and_unknown_price_or_interval_fail_closed(db):
    source = _source(db, "cost-currency")
    _budget(db)
    wrong_currency = _admit(db, source.id, currency="EUR")
    assert not wrong_currency.allowed
    assert wrong_currency.reason_code == "currency_conversion_unreviewed"
    unknown_price = _admit(db, source.id, amount=None)
    assert not unknown_price.allowed
    assert unknown_price.reason_code == "unknown_or_invalid_price"
    unknown_interval = _admit(db, source.id, interval_unit="quarter")
    assert not unknown_interval.allowed
    assert unknown_interval.reason_code == "unsupported_or_unknown_interval"
    assert db.scalar(select(ProviderRecurringCostCommitment)) is None


def test_trial_uses_known_post_trial_recurring_price_and_unknown_trial_is_denied(db):
    source = _source(db, "cost-trial")
    _budget(db)
    unknown = _admit(
        db,
        source.id,
        state="trial",
        amount="0",
        post_trial_amount=None,
        post_trial_currency=None,
        post_trial_interval_unit=None,
        post_trial_interval_count=None,
    )
    assert not unknown.allowed
    assert unknown.reason_code.startswith("trial_post_price_")
    assert db.scalar(select(ProviderRecurringCostCommitment)) is None

    known = _admit(
        db,
        source.id,
        state="trial",
        amount="0",
        post_trial_amount="120",
        post_trial_currency="USD",
        post_trial_interval_unit="year",
        post_trial_interval_count=1,
    )
    assert known.allowed
    assert known.proposed_monthly == Decimal("10.0000")
    assert known.paid_activation_authorized is False


def test_expired_or_cancelled_state_releases_cost_and_retains_revision(db):
    source = _source(db, "cost-state-transition")
    _budget(db)
    current = _admit(db, source.id, amount="18")
    assert current.allowed
    cancelled = _admit(
        db,
        source.id,
        state="cancelled",
        amount="18",
        effective_at=NOW + timedelta(days=1),
    )
    assert cancelled.allowed
    assert cancelled.proposed_monthly == Decimal("0.0000")
    assert provider_recurring_cost_status(db).committed_monthly == Decimal("0.0000")
    assert len(list(db.scalars(select(ProviderRecurringCostCommitmentRevision)))) == 2


def test_explicit_expired_transition_does_not_count_and_stale_active_quote_is_rejected(db):
    source = _source(db, "cost-expiry")
    _budget(db)
    active = _admit(db, source.id, amount="17")
    assert active.allowed
    stale = _admit(
        db,
        source.id,
        state="active",
        ends_at=NOW - timedelta(seconds=1),
        evidence_version="stale-active-state",
    )
    assert not stale.allowed
    assert stale.reason_code == "commitment_already_ended"
    expired = _admit(db, source.id, state="expired", amount=None)
    assert expired.allowed
    assert provider_recurring_cost_status(db).committed_monthly == Decimal("0.0000")


def test_unknown_plan_and_unreviewed_environment_are_not_admitted(db):
    source = _source(db, "cost-unreviewed")
    _budget(db)
    unknown_plan = _admit(db, source.id, configured_plan="unknown-plan")
    assert not unknown_plan.allowed
    assert unknown_plan.reason_code == "commitment_evidence_incomplete"
    unknown_environment = _admit(db, source.id, environment="unreviewed")
    assert not unknown_environment.allowed
    assert unknown_environment.reason_code == "commitment_evidence_incomplete"
    assert db.scalar(select(ProviderRecurringCostCommitment)) is None


def test_budget_revisions_are_retained_and_ceiling_cannot_drop_below_commitments(db):
    source = _source(db, "cost-budget-revisions")
    assert _budget(db).allowed
    assert _admit(db, source.id, amount="12").allowed
    denied = configure_provider_recurring_cost_budget(
        db,
        monthly_ceiling="10",
        currency="USD",
        evidence_source="operator-reviewed lower ceiling",
        evidence_version="test-v2",
        reviewed_at=NOW,
    )
    assert not denied.allowed
    assert denied.reason_code == "existing_commitments_exceed_proposed_ceiling"
    assert db.get(ProviderRecurringCostBudget, 1).monthly_ceiling == 20
    assert len(list(db.scalars(select(ProviderRecurringCostBudgetRevision)))) == 1

    accepted = configure_provider_recurring_cost_budget(
        db,
        monthly_ceiling="22",
        currency="USD",
        evidence_source="operator-reviewed updated ceiling",
        evidence_version="test-v3",
        reviewed_at=NOW,
    )
    assert accepted.allowed
    assert len(list(db.scalars(select(ProviderRecurringCostBudgetRevision)))) == 2


def test_revision_rows_prevent_budget_commitment_and_provider_scope_deletion(db):
    source = _source(db, "cost-append-only-audit")
    assert _budget(db).allowed
    assert _admit(db, source.id).allowed
    commitment = db.scalar(select(ProviderRecurringCostCommitment))

    for statement in (
        delete(ProviderRecurringCostBudget).where(ProviderRecurringCostBudget.id == 1),
        delete(ProviderRecurringCostCommitment).where(
            ProviderRecurringCostCommitment.id == commitment.id
        ),
        delete(DataSource).where(DataSource.id == source.id),
    ):
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.execute(statement)

    assert db.get(ProviderRecurringCostBudget, 1) is not None
    assert db.get(ProviderRecurringCostCommitment, commitment.id) is not None
    assert len(list(db.scalars(select(ProviderRecurringCostBudgetRevision)))) == 1
    assert len(list(db.scalars(select(ProviderRecurringCostCommitmentRevision)))) == 1
