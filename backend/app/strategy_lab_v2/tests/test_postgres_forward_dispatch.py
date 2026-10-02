from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import ForwardState
from app.strategy_lab_v2.dispatch import DispatchRequest
from app.strategy_lab_v2.forward_event_dispatch import ForwardEventDispatchDecision
from app.strategy_lab_v2.lifecycle import (
    CanonicalForwardEvent,
    ForwardCursor,
    observe_forward_event,
)
from app.strategy_lab_v2.postgres_forward_dispatch import (
    PostgresForwardEventDispatchAdapter,
    PostgresForwardEventDispatchSchema,
)
from app.strategy_lab_v2.postgres_forward_state import PostgresForwardStateAdapter
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
                    if owner == values["owner_id"]
                    and row["instance_id"] == values["instance_id"]
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
    )
    assert warming.instance is not None
    await state.complete_warmup(principal="owner-1", receipt=_receipt(warming.instance))


@pytest.mark.asyncio
async def test_forward_dispatch_persists_payload_dispatch_and_outbox_then_replays() -> None:
    session = DispatchSession()
    await _active_state(session)
    adapter = PostgresForwardEventDispatchAdapter(lambda: session)
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
