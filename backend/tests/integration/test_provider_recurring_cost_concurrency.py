"""PostgreSQL concurrency and restart-durability contract for cost admission."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

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


def test_concurrent_near_ceiling_admissions_are_serialized_and_durable(db_engine):
    now = datetime.now(UTC)
    suffix = uuid4().hex

    def configure(index: int):
        with Session(db_engine) as session:
            decision = configure_provider_recurring_cost_budget(
                session,
                monthly_ceiling="20.00",
                currency="USD",
                evidence_source="concurrent reviewed integration budget",
                evidence_version=f"{suffix}-{index}",
                reviewed_at=now,
            )
            if decision.allowed:
                session.commit()
            else:
                session.rollback()
            return decision

    with ThreadPoolExecutor(max_workers=2) as pool:
        budget_decisions = list(pool.map(configure, (0, 1)))
    assert all(decision.allowed for decision in budget_decisions)
    with Session(db_engine) as verify_budget:
        configured = verify_budget.get(ProviderRecurringCostBudget, 1)
        assert configured is not None
        assert configured.revision == 2
        assert len(configured.revisions) == 2

    sources: list[DataSource] = []
    with Session(db_engine) as setup:
        sources = [
            DataSource(name=f"cost-race-{suffix}-{index}", is_active=True) for index in range(2)
        ]
        setup.add_all(sources)
        setup.flush()
        source_ids = [source.id for source in sources]
        setup.commit()

    def attempt(index: int, amount: str):
        with Session(db_engine) as session:
            decision = admit_provider_recurring_cost(
                session,
                data_source_id=source_ids[index],
                environment="test",
                billing_account_scope=f"opaque-race-account-{suffix}-{index}",
                configured_plan="reviewed-integration-plan",
                state="proposed",
                amount=amount,
                currency="USD",
                interval_unit="month",
                interval_count=1,
                evidence_source="integration fixture pricing source",
                evidence_version=suffix,
                evidence_observed_at=now,
                effective_at=now,
            )
            if decision.allowed:
                session.commit()
            else:
                session.rollback()
            return decision

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(attempt, 0, "12.00")
            second = pool.submit(attempt, 1, "11.00")
            decisions = [first.result(timeout=30), second.result(timeout=30)]

        assert sum(decision.allowed for decision in decisions) == 1, decisions
        assert {decision.reason_code for decision in decisions} == {
            "commitment_admitted",
            "monthly_ceiling_exceeded",
        }
        with Session(db_engine) as verify:
            status = provider_recurring_cost_status(verify)
            assert status.allowed
            assert status.committed_monthly in {11, 12}
            assert status.remaining_monthly in {8, 9}
            assert len(list(verify.scalars(select(ProviderRecurringCostCommitment)))) == 1
            assert len(list(verify.scalars(select(ProviderRecurringCostCommitmentRevision)))) == 1
    finally:
        with Session(db_engine) as cleanup:
            cleanup.execute(delete(ProviderRecurringCostCommitmentRevision))
            cleanup.execute(delete(ProviderRecurringCostCommitment))
            cleanup.execute(delete(ProviderRecurringCostBudgetRevision))
            cleanup.execute(delete(ProviderRecurringCostBudget))
            cleanup.execute(delete(DataSource).where(DataSource.id.in_(source_ids)))
            cleanup.commit()
