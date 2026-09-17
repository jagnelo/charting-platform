from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import CarryInMode, ForwardInstance, ForwardState
from app.strategy_lab_v2.forward_admission import ForwardAdmissionDecision
from app.strategy_lab_v2.forward_warmup import ForwardWarmupDecision, ForwardWarmupReceipt
from app.strategy_lab_v2.lifecycle import (
    CanonicalForwardEvent,
    ForwardCursor,
    observe_forward_event,
)
from app.strategy_lab_v2.postgres_forward_state import (
    ForwardInstanceDecision,
    ForwardStateMutationDecision,
    PostgresForwardStateAdapter,
    PostgresForwardStateSchema,
)

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
DIGEST = content_digest({"fixture": "forward"})


class FakeResult:
    def __init__(self, rows=(), rowcount: int = 0) -> None:
        self._rows = list(rows)
        self.rowcount = rowcount

    def mappings(self):
        return iter(self._rows)


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeSession:
    def __init__(self) -> None:
        self.instances: dict[tuple[str, str], dict[str, Any]] = {}
        self.warmups: dict[tuple[str, str], dict[str, Any]] = {}
        self.events: dict[tuple[str, str, str], dict[str, Any]] = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def begin(self):
        return FakeTransaction()

    async def execute(self, statement, params=None):
        sql = str(statement)
        values = dict(params or {})
        if "FROM strategy_lab_v2_forward_instances" in sql:
            row = self.instances.get((values["owner_id"], values["instance_id"]))
            return FakeResult([] if row is None else [row])
        if "FROM strategy_lab_v2_forward_warmups" in sql:
            row = self.warmups.get((values["owner_id"], values["instance_id"]))
            return FakeResult([] if row is None else [row])
        if "FROM strategy_lab_v2_forward_seen_events" in sql:
            rows = [
                row
                for (owner, instance_id, _), row in self.events.items()
                if owner == values["owner_id"] and instance_id == values["instance_id"]
            ]
            return FakeResult(sorted(rows, key=lambda row: row["event_id"]))
        if sql.lstrip().startswith("INSERT INTO") and "instance_fingerprint" in sql:
            key = (values["owner_id"], values["instance_id"])
            if key in self.instances:
                return FakeResult(rowcount=0)
            self.instances[key] = values
            return FakeResult(rowcount=1)
        if sql.lstrip().startswith("INSERT INTO") and "receipt_fingerprint" in sql:
            key = (values["owner_id"], values["instance_id"])
            if key in self.warmups:
                return FakeResult(rowcount=0)
            self.warmups[key] = values
            return FakeResult(rowcount=1)
        if sql.lstrip().startswith("INSERT INTO") and "seen_fingerprint" in sql:
            key = (values["owner_id"], values["instance_id"], values["event_id"])
            if key in self.events:
                return FakeResult(rowcount=0)
            self.events[key] = values
            return FakeResult(rowcount=1)
        if sql.lstrip().startswith("UPDATE") and "checkpoint_fingerprint" in sql:
            key = (values["owner_id"], values["instance_id"])
            row = self.instances.get(key)
            if row is None:
                return FakeResult(rowcount=0)
            if row["checkpoint_fingerprint"] != values["expected_checkpoint_fingerprint"]:
                return FakeResult(rowcount=0)
            if row["instance_fingerprint"] != values["expected_instance_fingerprint"]:
                return FakeResult(rowcount=0)
            self.instances[key] = values
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


def _instance(state: ForwardState = ForwardState.CREATED) -> ForwardInstance:
    return ForwardInstance(
        "instance-1",
        content_digest({"portfolio": "one"}),
        content_digest({"snapshot": "warmup"}),
        CarryInMode.FLAT,
        state,
        None,
        0,
        0,
        NOW,
        NOW,
    )


def _receipt(instance: ForwardInstance, *, completed_at: datetime = NOW + timedelta(minutes=1)):
    return ForwardWarmupReceipt(
        instance.instance_id,
        instance.warmup_snapshot_fingerprint,
        instance.carry_in_mode,
        content_digest({"warmup": instance.instance_id}),
        completed_at,
    )


@pytest.mark.asyncio
async def test_forward_adapter_transitions_completes_warmup_and_replays() -> None:
    session = FakeSession()
    adapter = PostgresForwardStateAdapter(lambda: session)
    instance = _instance()
    registered = await adapter.ensure_instance(principal="owner-1", instance=instance)
    assert registered.decision is ForwardInstanceDecision.REGISTERED
    transitioned = await adapter.transition(
        principal="owner-1",
        instance_id=instance.instance_id,
        target=ForwardState.WARMING_UP,
        now=NOW + timedelta(seconds=1),
    )
    assert transitioned.decision is ForwardStateMutationDecision.APPLIED
    warming = transitioned.instance
    assert warming is not None and warming.state is ForwardState.WARMING_UP
    receipt = _receipt(warming)
    completed = await adapter.complete_warmup(principal="owner-1", receipt=receipt)
    assert completed.decision is ForwardWarmupDecision.COMPLETE
    replay = await adapter.complete_warmup(principal="owner-1", receipt=receipt)
    assert replay.decision is ForwardWarmupDecision.REPLAY_EXISTING
    loaded = await adapter.load_instance(principal="owner-1", instance_id="instance-1")
    assert loaded is not None
    assert loaded.state is ForwardState.ACTIVE


@pytest.mark.asyncio
async def test_forward_adapter_admits_events_idempotently_and_persists_counters() -> None:
    session = FakeSession()
    adapter = PostgresForwardStateAdapter(lambda: session)
    instance = _instance(ForwardState.WARMING_UP)
    await adapter.ensure_instance(principal="owner-1", instance=instance)
    await adapter.complete_warmup(principal="owner-1", receipt=_receipt(instance))
    event = CanonicalForwardEvent(
        "event-1", 0, NOW + timedelta(minutes=2), NOW + timedelta(minutes=2), DIGEST
    )
    observation = observe_forward_event(cursor=ForwardCursor(), event=event)
    accepted = await adapter.admit(
        principal="owner-1", instance_id=instance.instance_id, event=event, observation=observation
    )
    assert accepted.decision is ForwardAdmissionDecision.ACCEPTED
    replay = await adapter.admit(
        principal="owner-1", instance_id=instance.instance_id, event=event, observation=observation
    )
    assert replay.decision is ForwardAdmissionDecision.REPLAY_EXISTING
    state = await adapter.load_state(principal="owner-1", instance_id=instance.instance_id)
    assert state is not None
    assert event.event_id in state.checkpoint.processed_event_ids
    assert len(state.seen_events) == 1


@pytest.mark.asyncio
async def test_forward_adapter_rejects_tampered_checkpoint_and_owner_conflicts() -> None:
    session = FakeSession()
    adapter = PostgresForwardStateAdapter(lambda: session)
    instance = _instance(ForwardState.WARMING_UP)
    await adapter.ensure_instance(principal="owner-1", instance=instance)
    conflict = await adapter.ensure_instance(
        principal="owner-1",
        instance=ForwardInstance(
            instance.instance_id,
            instance.portfolio_fingerprint,
            instance.warmup_snapshot_fingerprint,
            instance.carry_in_mode,
            instance.state,
            None,
            0,
            0,
            NOW,
            NOW + timedelta(seconds=1),
        ),
    )
    assert conflict.decision is ForwardInstanceDecision.CONFLICT
    session.instances[("owner-1", instance.instance_id)]["checkpoint_fingerprint"] = content_digest("tampered")
    with pytest.raises(ValueError, match="checkpoint fingerprint"):
        await adapter.load_instance(principal="owner-1", instance_id=instance.instance_id)


def test_forward_state_schema_is_explicit_and_safe() -> None:
    schema = PostgresForwardStateSchema()
    assert len(schema.statements) == 3
    assert all("CREATE TABLE" in statement for statement in schema.statements)
    assert "PRIMARY KEY (owner_id, instance_id, event_id)" in schema.statements[2]
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresForwardStateSchema(event_table="unsafe;drop")
