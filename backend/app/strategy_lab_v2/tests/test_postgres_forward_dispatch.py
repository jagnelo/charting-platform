from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import ForwardState
from app.strategy_lab_v2.dispatch import DispatchRequest
from app.strategy_lab_v2.dispatch_payload import DispatchPayload
from app.strategy_lab_v2.forward_event_dispatch import ForwardEventDispatchDecision
from app.strategy_lab_v2.forward_worker_handoff import (
    ForwardEventDispatchPayload,
    ForwardEventWorkItem,
)
from app.strategy_lab_v2.lifecycle import (
    CanonicalForwardEvent,
    ForwardCursor,
    observe_forward_event,
)
from app.strategy_lab_v2.nautilus_forward_delivery import (
    materialize_nautilus_forward_delivery_binding,
)
from app.strategy_lab_v2.postgres_forward_dispatch import (
    PostgresForwardEventDispatchAdapter,
    PostgresForwardEventDispatchSchema,
)
from app.strategy_lab_v2.postgres_forward_state import PostgresForwardStateAdapter
from app.strategy_lab_v2.redis_transport import RedisStreamEntry
from app.strategy_lab_v2.tests.test_postgres_forward_state import (
    FakeResult,
    FakeSession,
    _instance,
    _receipt,
)

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)


class DispatchSession(FakeSession):
    def __init__(self) -> None:
        super().__init__()
        self.dispatches: dict[tuple[str, str], dict[str, Any]] = {}
        self.payloads: dict[str, dict[str, Any]] = {}
        self.outboxes: dict[str, dict[str, Any]] = {}

    async def execute(self, statement, params=None):
        sql = str(statement)
        values = dict(params or {})
        normalized = sql.lstrip()
        if "FROM strategy_lab_v2_forward_event_dispatches" in sql:
            if "request_fingerprint" in values:
                rows = [
                    row
                    for row in self.dispatches.values()
                    if row["request_fingerprint"] == values["request_fingerprint"]
                ]
            else:
                rows = [
                    row
                    for (owner, _), row in self.dispatches.items()
                    if owner == values["owner_id"] and row["instance_id"] == values["instance_id"]
                ]
            return FakeResult(sorted(rows, key=lambda row: row["request_fingerprint"]))
        if "FROM strategy_lab_v2_dispatch_payloads" in sql:
            row = self.payloads.get(values["payload_digest"])
            return FakeResult([] if row is None else [row])
        if normalized.startswith("INSERT INTO strategy_lab_v2_dispatch_payloads"):
            key = values["payload_digest"]
            if key in self.payloads:
                return FakeResult(rowcount=0)
            self.payloads[key] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("INSERT INTO strategy_lab_v2_forward_event_dispatches"):
            key = (values["owner_id"], values["idempotency_key"])
            if key in self.dispatches:
                return FakeResult(rowcount=0)
            self.dispatches[key] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("INSERT INTO strategy_lab_v2_execution_outbox"):
            key = values["message_id"]
            if key in self.outboxes:
                return FakeResult(rowcount=0)
            self.outboxes[key] = values
            return FakeResult(rowcount=1)
        return await super().execute(statement, params)


async def _active_state(session: DispatchSession) -> None:
    state = PostgresForwardStateAdapter(lambda: session)
    instance = _instance()
    await state.ensure_instance(principal="owner-1", instance=instance)
    warming = await state.transition(
        principal="owner-1",
        instance_id=instance.instance_id,
        target=ForwardState.WARMING_UP,
        now=NOW + timedelta(seconds=1),
        idempotency_key="forward-dispatch-active-setup",
    )
    assert warming.instance is not None
    await state.complete_warmup(principal="owner-1", receipt=_receipt(warming.instance))


@pytest.mark.asyncio
async def test_forward_dispatch_persists_payload_dispatch_and_outbox_then_replays() -> None:
    session = DispatchSession()
    await _active_state(session)
    adapter = PostgresForwardEventDispatchAdapter(lambda: session)
    state_store = PostgresForwardStateAdapter(lambda: session)
    pre_event_state = await state_store.load_state(
        principal="owner-1",
        instance_id="instance-1",
    )
    assert pre_event_state is not None
    event = CanonicalForwardEvent(
        "live-0",
        0,
        NOW + timedelta(minutes=2),
        NOW + timedelta(minutes=2),
        content_digest("forward-source"),
    )
    observation = observe_forward_event(ForwardCursor(), event)
    payload = {
        "event_fingerprint": content_digest(event),
        "replay_plan_fingerprint": None,
    }
    request = DispatchRequest(
        "forward-dispatch-1",
        "instance-1",
        content_digest(payload),
        "forward-events",
        NOW + timedelta(minutes=3),
    )

    accepted = await adapter.dispatch(
        principal="owner-1",
        instance_id="instance-1",
        event=event,
        observation=observation,
        dispatch_request=request,
        payload=payload,
    )
    assert accepted.decision is ForwardEventDispatchDecision.ENQUEUE
    assert len(session.payloads) == 1
    assert len(session.dispatches) == 1
    assert len(session.outboxes) == 1
    loaded = await adapter.load_by_request_fingerprint(request.fingerprint)
    assert loaded is not None
    assert loaded.request == request
    assert loaded.pre_event_checkpoint_fingerprint == pre_event_state.checkpoint.fingerprint
    assert loaded.warmup_receipt_fingerprint == pre_event_state.warmup_receipt_fingerprint
    assert loaded.admission_decision == "enqueue"
    persisted_dispatch = next(iter(session.dispatches.values()))
    assert persisted_dispatch["pre_event_checkpoint_fingerprint"] == (
        pre_event_state.checkpoint.fingerprint
    )
    assert persisted_dispatch["warmup_receipt_fingerprint"] == (
        pre_event_state.warmup_receipt_fingerprint
    )
    original_warmup_fingerprint = persisted_dispatch["warmup_receipt_fingerprint"]
    persisted_dispatch["warmup_receipt_fingerprint"] = content_digest("forged-warmup")
    with pytest.raises(ValueError, match="dispatch fingerprint"):
        await adapter.load_by_request_fingerprint(request.fingerprint)
    persisted_dispatch["warmup_receipt_fingerprint"] = original_warmup_fingerprint
    entry = RedisStreamEntry(
        "strategy-lab:v2:forward-events",
        "1704067200000-0",
        request.fingerprint,
        request.attempt_id,
        request.payload_digest,
        request.fingerprint,
    )
    work_item = ForwardEventWorkItem(
        loaded,
        ForwardEventDispatchPayload(
            loaded.event_fingerprint,
            loaded.replay_plan_fingerprint,
        ),
    )
    delivery_binding = materialize_nautilus_forward_delivery_binding(entry, work_item)
    assert delivery_binding.event_fingerprint == content_digest(event)
    assert delivery_binding.redis_entry_fingerprint == entry.fingerprint
    assert delivery_binding.dispatch_record_fingerprint == loaded.fingerprint
    assert (
        delivery_binding.pre_event_checkpoint_fingerprint == pre_event_state.checkpoint.fingerprint
    )
    assert delivery_binding.warmup_receipt_fingerprint == pre_event_state.warmup_receipt_fingerprint
    payload_record = DispatchPayload.from_mapping(payload)
    assert payload_record.payload_digest == entry.payload_digest
    with pytest.raises(ValueError, match="request identity"):
        materialize_nautilus_forward_delivery_binding(
            replace(entry, request_fingerprint=content_digest("different-request")),
            work_item,
        )
    legacy_record = replace(
        loaded,
        pre_event_checkpoint_fingerprint=None,
        warmup_receipt_fingerprint=None,
        admission_decision=None,
    )
    with pytest.raises(ValueError, match="lacks persisted admission checkpoint"):
        materialize_nautilus_forward_delivery_binding(
            entry,
            ForwardEventWorkItem(legacy_record, work_item.payload),
        )
    loaded_payload = await adapter.load_payload(request.payload_digest)
    assert loaded_payload is not None
    assert loaded_payload.payload_digest == request.payload_digest

    replay = await adapter.dispatch(
        principal="owner-1",
        instance_id="instance-1",
        event=event,
        observation=observation,
        dispatch_request=request,
        payload=payload,
    )
    assert replay.decision is ForwardEventDispatchDecision.REPLAY_EXISTING
    assert len(session.payloads) == 1
    assert len(session.dispatches) == 1
    assert len(session.outboxes) == 1


@pytest.mark.asyncio
async def test_forward_dispatch_payload_loader_rejects_malformed_digest_and_missing_rows() -> None:
    session = DispatchSession()
    adapter = PostgresForwardEventDispatchAdapter(lambda: session)

    assert await adapter.load_payload(content_digest("missing")) is None
    with pytest.raises(ValueError, match="payload_digest"):
        await adapter.load_payload("not-a-digest")


def test_forward_dispatch_schema_is_safe_and_additive() -> None:
    schema = PostgresForwardEventDispatchSchema()
    assert len(schema.statements) == 1
    assert "strategy_lab_v2_forward_event_dispatches" in schema.statements[0]
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresForwardEventDispatchSchema(dispatch_table="unsafe;drop")
