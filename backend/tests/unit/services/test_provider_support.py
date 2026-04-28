from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.data_source import DataSource
from app.models.instrument_identity import InstrumentProviderCapabilityStatus, InstrumentProviderSymbol
from app.models.provider_runtime import ProviderCapability, ProviderHealthState, ProviderPolicy
from app.services.provider_runtime import (
    ProviderExecutionResult,
    ResolvedProvider,
    execute_provider_call,
    resolve_provider_chain,
)
from app.services.provider_support import (
    SUPPORT_STATUS_SUPPORTED,
    SUPPORT_STATUS_UNKNOWN,
    SUPPORT_STATUS_UNSUPPORTED,
    get_provider_support_map,
)
from tests.unit.conftest import AsyncSessionAdapter


class _Provider:
    def __init__(self, result):
        self._result = result

    def run(self):
        return self._result


def _resolved_provider(db, *, provider_name: str, capability: ProviderCapability, provider: object) -> ResolvedProvider:
    data_source = DataSource(name=provider_name, is_active=True)
    db.add(data_source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=data_source.id,
        capability=capability,
        is_enabled=True,
        is_pinned=False,
        auto_weight_enabled=True,
        base_priority=100,
        max_concurrency=2,
        tokens_per_minute=60,
        burst_capacity=15,
        cooldown_seconds=30,
        freshness_seconds=300,
        score_floor=Decimal("0"),
        score_ceiling=Decimal("100"),
        learned_weight=Decimal("0"),
        effective_score=Decimal("90"),
    )
    health = ProviderHealthState(
        data_source_id=data_source.id,
        capability=capability,
        observed_score=Decimal("90"),
        ewma_latency_ms=Decimal("0"),
        ewma_success_rate=Decimal("1"),
        ewma_completeness=Decimal("1"),
        ewma_freshness=Decimal("1"),
        ewma_consistency=Decimal("1"),
    )
    db.add_all([policy, health])
    db.flush()
    return ResolvedProvider(
        provider_name=provider_name,
        provider=provider,
        data_source=data_source,
        policy=policy,
        health=health,
    )


@pytest.mark.asyncio
async def test_support_status_expires_back_to_unknown(db, instrument):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="yfinance", is_active=True)
    db.add(source)
    db.flush()
    db.add(
        InstrumentProviderCapabilityStatus(
            instrument_id=instrument.id,
            data_source_id=source.id,
            capability=ProviderCapability.LATEST_PRICE,
            support_status=SUPPORT_STATUS_UNSUPPORTED,
            status_expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    )
    db.commit()

    support_map = await get_provider_support_map(async_db, instrument.id, ProviderCapability.LATEST_PRICE)

    assert support_map[source.id].status == SUPPORT_STATUS_UNKNOWN


@pytest.mark.asyncio
async def test_execute_provider_call_downgrades_and_recovers_provider_support(db, instrument, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    primary = _resolved_provider(
        db,
        provider_name="alpaca",
        capability=ProviderCapability.LATEST_PRICE,
        provider=_Provider(None),
    )
    fallback = _resolved_provider(
        db,
        provider_name="yfinance",
        capability=ProviderCapability.LATEST_PRICE,
        provider=_Provider(123.45),
    )

    async def _fake_resolve(*_args, **_kwargs):
        return [primary, fallback]

    monkeypatch.setattr("app.services.provider_runtime.resolve_provider_chain", _fake_resolve)

    result = await execute_provider_call(
        async_db,
        ProviderCapability.LATEST_PRICE,
        "get_current_price",
        instrument_id=instrument.id,
        invoke=lambda provider, _provider_symbol: provider.run(),
        response_items=lambda payload: 1 if payload is not None else 0,
        treat_empty_as_failure=True,
    )

    rows = db.execute(
        select(InstrumentProviderCapabilityStatus).where(
            InstrumentProviderCapabilityStatus.instrument_id == instrument.id,
            InstrumentProviderCapabilityStatus.capability == ProviderCapability.LATEST_PRICE,
        )
    ).scalars().all()
    status_by_source = {row.data_source_id: row.support_status for row in rows}

    assert result.provider_name == "yfinance"
    assert status_by_source[primary.data_source.id] == SUPPORT_STATUS_UNSUPPORTED
    assert status_by_source[fallback.data_source.id] == SUPPORT_STATUS_SUPPORTED


@pytest.mark.asyncio
async def test_resolve_provider_chain_prefers_supported_then_bound_provider(db, instrument):
    async_db = AsyncSessionAdapter(db)
    alpha = _resolved_provider(
        db,
        provider_name="alpaca",
        capability=ProviderCapability.PRICE_HISTORY,
        provider=_Provider([]),
    )
    yahoo = _resolved_provider(
        db,
        provider_name="yfinance",
        capability=ProviderCapability.PRICE_HISTORY,
        provider=_Provider([]),
    )
    fred = _resolved_provider(
        db,
        provider_name="fred",
        capability=ProviderCapability.PRICE_HISTORY,
        provider=_Provider([]),
    )

    db.add(
        InstrumentProviderSymbol(
            instrument_id=instrument.id,
            data_source_id=yahoo.data_source.id,
            provider_symbol="AAPL",
            is_primary=True,
            is_active=True,
        )
    )
    db.add(
        InstrumentProviderCapabilityStatus(
            instrument_id=instrument.id,
            data_source_id=alpha.data_source.id,
            capability=ProviderCapability.PRICE_HISTORY,
            support_status=SUPPORT_STATUS_SUPPORTED,
            status_expires_at=datetime.now(UTC) + timedelta(days=30),
        )
    )
    db.add(
        InstrumentProviderCapabilityStatus(
            instrument_id=instrument.id,
            data_source_id=fred.data_source.id,
            capability=ProviderCapability.PRICE_HISTORY,
            support_status=SUPPORT_STATUS_UNSUPPORTED,
            status_expires_at=datetime.now(UTC) + timedelta(days=7),
        )
    )
    db.commit()

    chain = await resolve_provider_chain(async_db, ProviderCapability.PRICE_HISTORY, instrument_id=instrument.id)

    assert [item.provider_name for item in chain[:2]] == ["alpaca", "yfinance"]
    assert "fred" not in [item.provider_name for item in chain]
