from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models.data_source import DataSource
from app.models.instrument_reconciliation import InstrumentReconciliationIssue
from app.models.user import User
from app.services.instrument_reconciliation import (
    list_reconciliation_issues,
    record_discovery_ambiguities,
    resolve_reconciliation_issue,
)
from tests.unit.conftest import AsyncSessionAdapter


@pytest.mark.asyncio
async def test_record_discovery_ambiguity_is_idempotent(db):
    source = DataSource(name="edgar", is_active=True)
    db.add(source)
    db.flush()
    rows = [
        {
            "symbol": "ABC",
            "exchange": "NASDAQ",
            "sec_cik": "0000000001",
            "identity_ambiguity": [
                {"cik": "0000000001", "name": "ABC Holdings", "exchange": "NASDAQ"},
                {"cik": "0000000002", "name": "ABC Corp", "exchange": "NYSE"},
            ],
        }
    ]
    async_db = AsyncSessionAdapter(db)
    observed_at = datetime(2026, 8, 11, tzinfo=UTC)

    assert (
        await record_discovery_ambiguities(
            async_db,
            data_source_id=source.id,
            provider_symbol_rows=rows,
            quote_type="EQUITY",
            offset=0,
            observed_at=observed_at,
        )
        == 1
    )
    assert (
        await record_discovery_ambiguities(
            async_db,
            data_source_id=source.id,
            provider_symbol_rows=rows,
            quote_type="EQUITY",
            offset=0,
            observed_at=datetime(2026, 8, 12, tzinfo=UTC),
        )
        == 0
    )

    issues = await list_reconciliation_issues(async_db)
    assert len(issues) == 1
    assert issues[0].provider_symbol == "ABC"
    assert issues[0].status == "open"
    assert issues[0].data_source.name == "edgar"
    assert db.execute(select(InstrumentReconciliationIssue)).scalars().all()


@pytest.mark.asyncio
async def test_reconciliation_issue_can_be_resolved_and_reopened(db):
    source = DataSource(name="edgar", is_active=True)
    reviewer = User(
        username="reconciliation-reviewer",
        email="reconciliation-reviewer@example.com",
        hashed_password="test",
        is_admin=True,
    )
    db.add(source)
    db.add(reviewer)
    db.flush()
    async_db = AsyncSessionAdapter(db)
    await record_discovery_ambiguities(
        async_db,
        data_source_id=source.id,
        provider_symbol_rows=[
            {
                "symbol": "XYZ",
                "identity_ambiguity": [{"cik": "1", "name": "One"}, {"cik": "2", "name": "Two"}],
            }
        ],
        quote_type="EQUITY",
        offset=0,
    )
    issue = (await list_reconciliation_issues(async_db))[0]

    await resolve_reconciliation_issue(
        async_db,
        issue,
        status="resolved",
        resolution={"canonical_cik": "1", "reviewer": "test"},
        resolved_by_user_id=reviewer.id,
    )
    assert issue.status == "resolved"
    assert issue.resolved_at is not None
    assert issue.resolution["canonical_cik"] == "1"
    assert issue.resolved_by_user_id == reviewer.id

    await resolve_reconciliation_issue(async_db, issue, status="open")
    assert issue.status == "open"
    assert issue.resolved_at is None
    assert issue.resolved_by_user_id is None

    with pytest.raises(ValueError, match="status must be"):
        await resolve_reconciliation_issue(async_db, issue, status="bad")
