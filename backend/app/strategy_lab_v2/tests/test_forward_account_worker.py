from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.dispatch import DispatchRequest
from app.strategy_lab_v2.dispatch_payload import DispatchPayload
from app.strategy_lab_v2.forward_account import (
    ForwardAccountEvent,
    ForwardRuntimeExecutionReceipt,
    initial_forward_account_state,
)
from app.strategy_lab_v2.forward_account_worker import (
    ForwardAccountEventBinding,
    ForwardAccountWorkerHandler,
)
from app.strategy_lab_v2.forward_worker_handoff import (
    ForwardEventDispatchPayload,
    ForwardEventWorkItem,
)
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.postgres_forward_account import (
    ForwardAccountStateDecision,
    ForwardAccountStateResolution,
)
from app.strategy_lab_v2.postgres_forward_dispatch import ForwardEventDispatchRecord
from app.strategy_lab_v2.redis_transport import RedisStreamEntry
from app.strategy_lab_v2.worker_consumer import WorkerHandleDecision

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)


class Store:
    def __init__(self, resolution: ForwardAccountStateResolution) -> None:
        self.resolution = resolution
        self.events: list[ForwardAccountEvent] = []
        self.execution_receipts: list[ForwardRuntimeExecutionReceipt | None] = []

    async def apply(
        self,
        *,
        principal: Any,
        event: ForwardAccountEvent,
        execution_receipt: ForwardRuntimeExecutionReceipt | None = None,
    ) -> ForwardAccountStateResolution:
        assert principal == "owner-1"
        self.events.append(event)
        self.execution_receipts.append(execution_receipt)
        return self.resolution


def _canonical_event() -> CanonicalForwardEvent:
    return CanonicalForwardEvent("event-1", 0, NOW, NOW, content_digest("source"))


def _work() -> tuple[RedisStreamEntry, ForwardEventWorkItem, CanonicalForwardEvent]:
    canonical_event = _canonical_event()
    event_fingerprint = content_digest(canonical_event)
    payload = DispatchPayload.from_mapping(
        {"event_fingerprint": event_fingerprint, "replay_plan_fingerprint": None}
    )
    request = DispatchRequest(
        "forward-key", "forward-1", payload.payload_digest, "forward-events", NOW
    )
    record = ForwardEventDispatchRecord("owner-1", "forward-1", event_fingerprint, request)
    entry = RedisStreamEntry(
        "strategy-lab:v2:stream:forward-events",
        "1-0",
        content_digest("message"),
        request.attempt_id,
        request.payload_digest,
        request.fingerprint,
    )
    return (
        entry,
        ForwardEventWorkItem(record, ForwardEventDispatchPayload(event_fingerprint)),
        canonical_event,
    )


def _event(
    work_item: ForwardEventWorkItem,
    canonical_event: CanonicalForwardEvent,
    *,
    event_fingerprint: str | None = None,
) -> ForwardAccountEvent:
    return ForwardAccountEvent(
        work_item.dispatch.instance_id,
        canonical_event.event_id,
        event_fingerprint or content_digest(canonical_event),
        canonical_event.sequence,
        canonical_event.event_time,
    )


@pytest.mark.asyncio
async def test_account_worker_settles_before_returning_complete_receipt() -> None:
    entry, work_item, canonical_event = _work()
    event = _event(work_item, canonical_event)
    state = initial_forward_account_state("forward-1", base_currency="USD")
    store = Store(
        ForwardAccountStateResolution(
            ForwardAccountStateDecision.APPLIED,
            state,
            event.event_fingerprint,
        )
    )
    handler = ForwardAccountWorkerHandler(
        store,
        principal="owner-1",
        event_resolver=lambda _entry, _item: ForwardAccountEventBinding(canonical_event, event),
    )

    result = await handler(entry, work_item)

    assert result.decision is WorkerHandleDecision.COMPLETE
    assert store.events == [event]
    assert result.receipt_digest is not None


@pytest.mark.asyncio
async def test_account_worker_rejects_event_identity_drift_without_store_write() -> None:
    entry, work_item, _canonical_event_value = _work()
    other_event = CanonicalForwardEvent("event-2", 1, NOW, NOW, content_digest("other-source"))
    state = initial_forward_account_state("forward-1", base_currency="USD")
    store = Store(
        ForwardAccountStateResolution(
            ForwardAccountStateDecision.APPLIED,
            state,
            work_item.payload.event_fingerprint,
        )
    )
    handler = ForwardAccountWorkerHandler(
        store,
        principal="owner-1",
        event_resolver=lambda _entry, item: ForwardAccountEventBinding(
            other_event, _event(item, other_event)
        ),
    )

    result = await handler(entry, work_item)

    assert result.decision is WorkerHandleDecision.REJECT
    assert (
        result.rejection_reason == "forward account canonical fingerprint does not match dispatch"
    )
    assert store.events == []


@pytest.mark.asyncio
async def test_account_worker_retries_missing_or_out_of_order_account_state() -> None:
    entry, work_item, canonical_event = _work()
    event = _event(work_item, canonical_event)
    state = initial_forward_account_state("forward-1", base_currency="USD")
    store = Store(
        ForwardAccountStateResolution(
            ForwardAccountStateDecision.NOT_FOUND,
            None,
            event.event_fingerprint,
            "forward account was not initialized",
        )
    )
    handler = ForwardAccountWorkerHandler(
        store,
        principal="owner-1",
        event_resolver=lambda _entry, _item: ForwardAccountEventBinding(canonical_event, event),
    )

    result = await handler(entry, work_item)

    assert result.decision is WorkerHandleDecision.RETRY
    assert result.rejection_reason == "forward account was not initialized"
    assert state.instance_id == "forward-1"


@pytest.mark.asyncio
async def test_account_worker_does_not_complete_without_durable_execution_receipt() -> None:
    entry, work_item, canonical_event = _work()
    event = _event(work_item, canonical_event)
    receipt = ForwardRuntimeExecutionReceipt(
        instance_id=event.instance_id,
        event_id=event.event_id,
        event_fingerprint=event.event_fingerprint,
        delivery_binding_fingerprint=content_digest("delivery-binding"),
        context_preparation_fingerprint=content_digest("context-preparation"),
        pre_event_checkpoint_fingerprint=content_digest("pre-event-checkpoint"),
        runtime_session_fingerprint=content_digest("runtime-session"),
        native_output_fingerprint=content_digest("native-output"),
    )
    store = Store(
        ForwardAccountStateResolution(
            ForwardAccountStateDecision.APPLIED,
            initial_forward_account_state("forward-1", base_currency="USD"),
            event.event_fingerprint,
        )
    )
    handler = ForwardAccountWorkerHandler(
        store,
        principal="owner-1",
        event_resolver=lambda _entry, _item: ForwardAccountEventBinding(
            canonical_event, event, receipt
        ),
    )

    result = await handler(entry, work_item)

    assert result.decision is WorkerHandleDecision.REJECT
    assert result.rejection_reason == (
        "forward account store did not durably confirm the execution receipt"
    )
    assert store.execution_receipts == [receipt]
