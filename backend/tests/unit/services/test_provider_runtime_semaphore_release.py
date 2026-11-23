"""A provider's local concurrency permit covers only the outbound request.

Production (2026-11-22, 34-hour refresh-queue stall): the permit was taken
before quota admission and returned after result bookkeeping. A drain holding
Alpaca's single permit (unknown concurrency defaults to one) updated
``instrument_provider_capability_status`` and blocked on a row lock owned by
another drain's open transaction, while that drain waited for the permit: a
deadlock Postgres cannot see. Separately, a job-timeout cancellation while an
early-exit path awaited a quota settle skipped ``semaphore.release()`` and
leaked the permit for the life of the worker.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from app.models.data_source import DataSource
from app.models.provider_runtime import ProviderCapability, ProviderHealthState, ProviderPolicy
from app.services import provider_runtime
from app.services.provider_runtime import ResolvedProvider, execute_provider_call
from tests.unit.conftest import AsyncSessionAdapter


def _resolved_provider(db, name: str, *, bucket: bool = False) -> ResolvedProvider:
    source = DataSource(
        name=name,
        is_active=True,
        config={"usage_tracking": {"operation_costs": {"get_current_price": 1}}},
    )
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.LATEST_PRICE,
        is_enabled=True,
        max_concurrency=None,
        tokens_per_minute=60 if bucket else None,
        burst_capacity=1 if bucket else None,
        quota_scope="provider-account",
        quota_source="unit-test contract",
        quota_contract={
            "reset": "rolling",
            "operation_costs": {"get_current_price": 1},
            "dimensions": [
                {
                    "name": "requests_per_minute",
                    "limit": 60,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "provider-account",
                    "source": "unit-test contract",
                }
            ],
        },
    )
    health = ProviderHealthState(
        data_source_id=source.id,
        capability=ProviderCapability.LATEST_PRICE,
        ewma_latency_ms=Decimal("0"),
        ewma_success_rate=Decimal("1"),
        ewma_completeness=Decimal("1"),
        ewma_freshness=Decimal("1"),
        ewma_consistency=Decimal("1"),
        observed_score=Decimal("0"),
    )
    db.add_all([policy, health])
    db.flush()
    return ResolvedProvider(
        provider_name=source.name,
        provider=object(),
        data_source=source,
        policy=policy,
        health=health,
    )


def _settle_cancelled(*_args, **_kwargs):
    # The drain's job timeout cancels it while the settle is awaited.
    raise asyncio.CancelledError


async def _coordinator_denies(**_kwargs):
    return None


async def _coordinator_raises(**_kwargs):
    raise RuntimeError("ledger unavailable")


async def _coordinator_grants(**_kwargs):
    return object()


async def _noop_coordinator_settle(*_args, **_kwargs):
    return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "coordinator", "bucket"),
    [
        ("coordinator_denied", _coordinator_denies, False),
        ("coordinator_raised", _coordinator_raises, False),
        ("local_bucket_denied", _coordinator_grants, True),
    ],
)
async def test_cancelled_settle_does_not_leak_the_provider_permit(
    db, monkeypatch, path, coordinator, bucket
):
    async_db = AsyncSessionAdapter(db)
    resolved = _resolved_provider(db, f"semaphore-{path}", bucket=bucket)
    semaphore = provider_runtime._get_semaphore(resolved.policy, resolved.provider_name)
    if bucket:
        # Drain the one-token burst so this call takes the bucket-denied path.
        assert provider_runtime._get_bucket(resolved.policy, resolved.provider_name).try_acquire(1)

    async def fake_chain(*_args, **_kwargs):
        return [resolved]

    async def reserve_contract(*_args, **_kwargs):
        return [object()]

    monkeypatch.setattr("app.services.provider_runtime.resolve_provider_chain", fake_chain)
    monkeypatch.setattr("app.services.provider_routing.reserve_provider_contract", reserve_contract)
    monkeypatch.setattr(
        "app.services.provider_quota_coordinator.reserve_provider_quota_async", coordinator
    )
    monkeypatch.setattr(
        "app.services.provider_runtime._settle_coordinator_best_effort", _noop_coordinator_settle
    )
    monkeypatch.setattr("app.services.provider_routing.settle_provider_contract", _settle_cancelled)

    with pytest.raises(asyncio.CancelledError):
        await execute_provider_call(
            async_db,
            ProviderCapability.LATEST_PRICE,
            "get_current_price",
            provider_name=resolved.provider_name,
            invoke=lambda *_args: pytest.fail("no provider request may be sent"),
        )

    # The permit is back: the next caller is not blocked behind a leaked one.
    assert not semaphore.locked()
    await asyncio.wait_for(semaphore.acquire(), timeout=1)
    semaphore.release()


@pytest.mark.asyncio
async def test_result_bookkeeping_does_not_hold_the_provider_permit(db, monkeypatch):
    """Reproduces the production deadlock shape with a single permit.

    The first call's bookkeeping cannot finish until the second call has sent
    its request (in production: a row lock held by the second drain's open
    transaction). If the first call still held the permit there, the second
    could never send and both would wait forever.
    """

    async_db = AsyncSessionAdapter(db)
    resolved = _resolved_provider(db, "semaphore-bookkeeping-deadlock")
    semaphore = provider_runtime._get_semaphore(resolved.policy, resolved.provider_name)
    second_sent = asyncio.Event()
    permit_held_during = {}

    async def fake_chain(*_args, **_kwargs):
        return [resolved]

    async def reserve_contract(*_args, **_kwargs):
        permit_held_during.setdefault("admission", semaphore.locked())
        return [object()]

    async def record_result(*_args, **kwargs):
        permit_held_during.setdefault("bookkeeping", semaphore.locked())
        if kwargs["log_row"].provider_symbol == "FIRST":
            await second_sent.wait()

    def invoke(_provider, symbol):
        permit_held_during.setdefault("request", semaphore.locked())
        return [symbol]

    monkeypatch.setattr("app.services.provider_runtime.resolve_provider_chain", fake_chain)
    monkeypatch.setattr("app.services.provider_routing.reserve_provider_contract", reserve_contract)
    monkeypatch.setattr(
        "app.services.provider_quota_coordinator.reserve_provider_quota_async", _coordinator_grants
    )
    monkeypatch.setattr(
        "app.services.provider_runtime._settle_coordinator_best_effort", _noop_coordinator_settle
    )
    monkeypatch.setattr(
        "app.services.provider_routing.settle_provider_contract", lambda *_a, **_k: None
    )
    monkeypatch.setattr("app.services.provider_runtime._record_result", record_result)

    async def call(symbol):
        result = await execute_provider_call(
            async_db,
            ProviderCapability.LATEST_PRICE,
            "get_current_price",
            provider_name=resolved.provider_name,
            provider_symbol=symbol,
            invoke=invoke,
        )
        if symbol == "SECOND":
            second_sent.set()
        return result

    first = asyncio.create_task(call("FIRST"))
    await asyncio.sleep(0)
    second = asyncio.create_task(call("SECOND"))
    results = await asyncio.wait_for(asyncio.gather(first, second), timeout=5)

    assert [result.result for result in results] == [["FIRST"], ["SECOND"]]
    assert permit_held_during == {"admission": False, "request": True, "bookkeeping": False}
    assert not semaphore.locked()
