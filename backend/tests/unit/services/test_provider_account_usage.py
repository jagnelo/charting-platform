from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.data_source import DataSource
from app.models.provider_runtime import ProviderAccountUsageObservation
from app.providers.base import ProviderAccountUsage
from app.services import provider_account_usage
from tests.unit.conftest import AsyncSessionAdapter


@pytest.mark.asyncio
async def test_refresh_persists_provider_native_counters_and_stops_after_first_provider(
    db, monkeypatch
):
    source = DataSource(name="marketdata_app", base_url="https://api.marketdata.app/v1")
    db.add(source)
    db.flush()
    observed_at = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    reset_at = observed_at + timedelta(days=1)
    resolved = SimpleNamespace(provider_name="marketdata_app")
    execution = SimpleNamespace(
        provider_name="marketdata_app",
        data_source=source,
        result=ProviderAccountUsage(
            provider="marketdata_app",
            observed_at=observed_at,
            unit="credits",
            limit=10000,
            remaining=9994,
            consumed=6,
            reset_at=reset_at,
            options_data_permissions="delayed",
        ),
    )
    calls = []

    async def fake_chain(*args, **kwargs):
        return [resolved]

    async def fake_execute(*args, **kwargs):
        calls.append(kwargs["provider_name"])
        return execution

    monkeypatch.setattr(provider_account_usage, "resolve_provider_chain", fake_chain)
    monkeypatch.setattr(provider_account_usage, "execute_provider_call", fake_execute)

    result = await provider_account_usage.refresh_provider_account_usage(
        AsyncSessionAdapter(db), provider_name="marketdata_app"
    )

    assert result["status"] == "refreshed"
    assert result["providers"] == ["marketdata_app"]
    assert calls == ["marketdata_app"]
    row = db.execute(
        select(ProviderAccountUsageObservation).where(
            ProviderAccountUsageObservation.data_source_id == source.id
        )
    ).scalar_one()
    assert row.limit == 10000
    assert row.remaining == 9994
    assert row.consumed == 6
    assert row.reset_at.replace(tzinfo=UTC) == reset_at


@pytest.mark.asyncio
async def test_refresh_is_fail_closed_when_no_provider_is_qualified(db, monkeypatch):
    async def fake_chain(*args, **kwargs):
        return []

    monkeypatch.setattr(provider_account_usage, "resolve_provider_chain", fake_chain)
    result = await provider_account_usage.refresh_provider_account_usage(AsyncSessionAdapter(db))
    assert result == {"status": "no_qualified_provider", "providers": [], "observations": []}


@pytest.mark.asyncio
async def test_refresh_rejects_malformed_native_counters_without_persisting(db, monkeypatch):
    source = DataSource(name="marketdata_app")
    db.add(source)
    db.flush()
    resolved = SimpleNamespace(provider_name="marketdata_app")
    execution = SimpleNamespace(
        provider_name="marketdata_app",
        data_source=source,
        result=ProviderAccountUsage(
            provider="marketdata_app",
            observed_at=datetime.now(UTC),
            unit="credits",
            limit=10,
            remaining=11,
        ),
    )

    async def fake_chain(*args, **kwargs):
        return [resolved]

    async def fake_execute(*args, **kwargs):
        return execution

    monkeypatch.setattr(provider_account_usage, "resolve_provider_chain", fake_chain)
    monkeypatch.setattr(provider_account_usage, "execute_provider_call", fake_execute)
    result = await provider_account_usage.refresh_provider_account_usage(AsyncSessionAdapter(db))

    assert result["status"] == "failed"
    assert result["observations"] == []
    assert db.execute(select(ProviderAccountUsageObservation)).scalars().all() == []


@pytest.mark.asyncio
async def test_list_returns_latest_durable_observations(db):
    source = DataSource(name="marketdata_app", base_url="https://api.marketdata.app/v1")
    db.add(source)
    db.flush()
    db.add_all(
        [
            ProviderAccountUsageObservation(
                data_source_id=source.id,
                observed_at=datetime(2026, 9, 11, tzinfo=UTC),
                unit="credits",
                limit=100,
                remaining=90,
            ),
            ProviderAccountUsageObservation(
                data_source_id=source.id,
                observed_at=datetime(2026, 9, 12, tzinfo=UTC),
                unit="credits",
                limit=100,
                remaining=80,
            ),
        ]
    )
    db.flush()

    rows = await provider_account_usage.list_provider_account_usage(
        AsyncSessionAdapter(db), provider_name="marketdata_app", limit=1
    )
    assert len(rows) == 1
    assert rows[0]["remaining"] == 80
