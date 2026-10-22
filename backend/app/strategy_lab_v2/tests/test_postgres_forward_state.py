from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import CarryInMode, ForwardInstance, ForwardState
from app.strategy_lab_v2.forward_admission import ForwardAdmissionDecision
from app.strategy_lab_v2.forward_corrections import ForwardCorrectionCommand
from app.strategy_lab_v2.forward_event_transaction import ForwardEventTransactionDecision
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
        self.replays: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.lifecycle_requests: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.checkpoint_history: dict[tuple[str, str, str], dict[str, Any]] = {}

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
            if "instance_id" in values:
                row = self.instances.get((values["owner_id"], values["instance_id"]))
                return FakeResult([] if row is None else [row])
            rows = [
                row for (owner, _), row in self.instances.items() if owner == values["owner_id"]
            ]
            return FakeResult(sorted(rows, key=lambda row: row["instance_id"]))
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
        if "FROM strategy_lab_v2_forward_replays" in sql:
            rows = [
                row
                for (owner, instance_id, _), row in self.replays.items()
                if owner == values["owner_id"] and instance_id == values["instance_id"]
            ]
            return FakeResult(sorted(rows, key=lambda row: row["replay_id"]))
        if "FROM strategy_lab_v2_forward_lifecycle_requests" in sql:
            row = self.lifecycle_requests.get(
                (values["owner_id"], values["instance_id"], values["idempotency_key_digest"])
            )
            return FakeResult([] if row is None else [row])
        if "FROM strategy_lab_v2_forward_checkpoint_history" in sql:
            rows = [
                row
                for (owner, instance_id, _), row in self.checkpoint_history.items()
                if owner == values["owner_id"] and instance_id == values["instance_id"]
            ]
            checkpoint_fingerprint = values.get("checkpoint_fingerprint")
            if checkpoint_fingerprint is not None:
                rows = [
                    row for row in rows if row["checkpoint_fingerprint"] == checkpoint_fingerprint
                ]
            return FakeResult(sorted(rows, key=lambda row: row["checkpoint_fingerprint"]))
        if sql.lstrip().startswith("INSERT INTO strategy_lab_v2_forward_checkpoint_history"):
            key = (
                values["owner_id"],
                values["instance_id"],
                values["checkpoint_fingerprint"],
            )
            if key in self.checkpoint_history:
                return FakeResult(rowcount=0)
            self.checkpoint_history[key] = values
            return FakeResult(rowcount=1)
        if sql.lstrip().startswith("INSERT INTO strategy_lab_v2_forward_lifecycle_requests"):
            key = (values["owner_id"], values["instance_id"], values["idempotency_key_digest"])
            if key in self.lifecycle_requests:
                return FakeResult(rowcount=0)
            self.lifecycle_requests[key] = values
            return FakeResult(rowcount=1)
        if sql.lstrip().startswith("INSERT INTO strategy_lab_v2_forward_instances"):
            key = (values["owner_id"], values["instance_id"])
            if key in self.instances:
                return FakeResult(rowcount=0)
            self.instances[key] = values
            return FakeResult(rowcount=1)
        if sql.lstrip().startswith("INSERT INTO") and "replay_fingerprint" in sql:
            key = (values["owner_id"], values["instance_id"], values["replay_id"])
            if key in self.replays:
                return FakeResult(rowcount=0)
            self.replays[key] = values
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
        idempotency_key="lifecycle-transition-1",
    )
    assert transitioned.decision is ForwardStateMutationDecision.APPLIED
    warming = transitioned.instance
    assert warming is not None and warming.state is ForwardState.WARMING_UP
    receipt = _receipt(warming)
    completed = await adapter.complete_warmup(principal="owner-1", receipt=receipt)
    assert completed.decision is ForwardWarmupDecision.COMPLETE
    replay = await adapter.complete_warmup(principal="owner-1", receipt=receipt)
    assert replay.decision is ForwardWarmupDecision.REPLAY_EXISTING
    assert (
        await adapter.load_warmup_receipt(principal="owner-1", instance_id=instance.instance_id)
        == receipt
    )
    assert (
        await adapter.load_warmup_receipt(principal="other-owner", instance_id=instance.instance_id)
        is None
    )
    loaded = await adapter.load_instance(principal="owner-1", instance_id="instance-1")
    assert loaded is not None
    assert loaded.state is ForwardState.ACTIVE


@pytest.mark.asyncio
async def test_forward_lifecycle_idempotency_replays_original_snapshot_and_conflicts_on_reuse() -> (
    None
):
    session = FakeSession()
    adapter = PostgresForwardStateAdapter(lambda: session)
    instance = _instance()
    await adapter.ensure_instance(principal="owner-1", instance=instance)

    first = await adapter.transition(
        principal="owner-1",
        instance_id=instance.instance_id,
        target=ForwardState.WARMING_UP,
        now=NOW + timedelta(seconds=1),
        idempotency_key="lifecycle-key",
    )
    assert first.decision is ForwardStateMutationDecision.APPLIED
    assert first.instance is not None and first.instance.state is ForwardState.WARMING_UP

    assert first.instance is not None
    await adapter.complete_warmup(principal="owner-1", receipt=_receipt(first.instance))
    assert (
        await adapter.load_instance(principal="owner-1", instance_id=instance.instance_id)
    ).state is ForwardState.ACTIVE  # type: ignore[union-attr]

    replay = await adapter.transition(
        principal="owner-1",
        instance_id=instance.instance_id,
        target=ForwardState.WARMING_UP,
        now=NOW + timedelta(seconds=1),
        idempotency_key="lifecycle-key",
    )
    assert replay.decision is ForwardStateMutationDecision.REPLAY_EXISTING
    assert replay.instance == first.instance
    assert replay.instance is not None and replay.instance.state is ForwardState.WARMING_UP

    conflict = await adapter.transition(
        principal="owner-1",
        instance_id=instance.instance_id,
        target=ForwardState.PAUSED,
        now=NOW + timedelta(minutes=2),
        idempotency_key="lifecycle-key",
    )
    assert conflict.decision is ForwardStateMutationDecision.CONFLICT
    assert conflict.instance == first.instance
    assert "Idempotency-Key" in (conflict.rejection_reason or "")

    hidden = await adapter.transition(
        principal="owner-2",
        instance_id=instance.instance_id,
        target=ForwardState.WARMING_UP,
        now=NOW + timedelta(seconds=1),
        idempotency_key="lifecycle-key",
    )
    assert hidden.decision is ForwardStateMutationDecision.NOT_FOUND
    assert hidden.instance is None


@pytest.mark.asyncio
async def test_forward_adapter_lists_owner_instances_deterministically() -> None:
    session = FakeSession()
    adapter = PostgresForwardStateAdapter(lambda: session)
    first = _instance()
    second = ForwardInstance(
        "instance-2",
        first.portfolio_fingerprint,
        first.warmup_snapshot_fingerprint,
        first.carry_in_mode,
        first.state,
        None,
        0,
        0,
        NOW,
        NOW,
    )
    await adapter.ensure_instance(principal="owner-1", instance=first)
    await adapter.ensure_instance(principal="owner-1", instance=second)

    assert await adapter.load_all(principal="owner-1") == (first, second)
    assert await adapter.load_all(principal="owner-2") == ()


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
async def test_forward_adapter_reconstructs_exact_historical_checkpoint_prefix() -> None:
    session = FakeSession()
    adapter = PostgresForwardStateAdapter(lambda: session)
    instance = _instance(ForwardState.WARMING_UP)
    await adapter.ensure_instance(principal="owner-1", instance=instance)
    await adapter.complete_warmup(principal="owner-1", receipt=_receipt(instance))

    first = CanonicalForwardEvent(
        "event-1", 0, NOW + timedelta(minutes=2), NOW + timedelta(minutes=2), DIGEST
    )
    first_observation = observe_forward_event(cursor=ForwardCursor(), event=first)
    await adapter.admit(
        principal="owner-1",
        instance_id=instance.instance_id,
        event=first,
        observation=first_observation,
    )
    first_checkpoint = await adapter.load_state(
        principal="owner-1", instance_id=instance.instance_id
    )
    assert first_checkpoint is not None

    second = CanonicalForwardEvent(
        "event-2",
        1,
        NOW + timedelta(minutes=3),
        NOW + timedelta(minutes=3),
        content_digest({"event": 2}),
    )
    second_observation = observe_forward_event(
        cursor=ForwardCursor(0, first.event_id, first.event_time),
        event=second,
    )
    await adapter.admit(
        principal="owner-1",
        instance_id=instance.instance_id,
        event=second,
        observation=second_observation,
    )

    historical = await adapter.load_state_at_checkpoint(
        principal="owner-1",
        instance_id=instance.instance_id,
        checkpoint_fingerprint=first_checkpoint.checkpoint.fingerprint,
    )
    assert historical is not None
    assert historical.checkpoint == first_checkpoint.checkpoint
    assert tuple(item.event_id for item in historical.seen_events) == (first.event_id,)
    assert (
        await adapter.load_state_at_checkpoint(
            principal="owner-2",
            instance_id=instance.instance_id,
            checkpoint_fingerprint=first_checkpoint.checkpoint.fingerprint,
        )
        is None
    )
    assert (
        await adapter.load_checkpoint_at(
            principal="owner-1",
            instance_id=instance.instance_id,
            checkpoint_fingerprint=content_digest("unknown-checkpoint"),
        )
        is None
    )


@pytest.mark.asyncio
async def test_forward_adapter_seeds_checkpoint_history_for_preexisting_instances() -> None:
    session = FakeSession()
    adapter = PostgresForwardStateAdapter(lambda: session)
    instance = _instance()
    await adapter.ensure_instance(principal="owner-1", instance=instance)
    initial_fingerprint = session.instances[("owner-1", instance.instance_id)][
        "checkpoint_fingerprint"
    ]
    initial = await adapter.load_checkpoint_at(
        principal="owner-1",
        instance_id=instance.instance_id,
        checkpoint_fingerprint=initial_fingerprint,
    )
    assert initial is not None

    # Simulate an instance row created before the append-only checkpoint table.
    session.checkpoint_history.clear()
    transitioned = await adapter.transition(
        principal="owner-1",
        instance_id=instance.instance_id,
        target=ForwardState.WARMING_UP,
        now=NOW + timedelta(seconds=1),
        idempotency_key="seed-history-for-legacy-instance",
    )
    assert transitioned.decision is ForwardStateMutationDecision.APPLIED
    assert (
        await adapter.load_checkpoint_at(
            principal="owner-1",
            instance_id=instance.instance_id,
            checkpoint_fingerprint=initial.fingerprint,
        )
        == initial
    )


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
    session.instances[("owner-1", instance.instance_id)]["checkpoint_fingerprint"] = content_digest(
        "tampered"
    )
    with pytest.raises(ValueError, match="checkpoint fingerprint"):
        await adapter.load_instance(principal="owner-1", instance_id=instance.instance_id)


@pytest.mark.asyncio
async def test_forward_adapter_stages_correction_replay_atomically() -> None:
    session = FakeSession()
    adapter = PostgresForwardStateAdapter(lambda: session)
    instance = _instance(ForwardState.WARMING_UP)
    await adapter.ensure_instance(principal="owner-1", instance=instance)
    await adapter.complete_warmup(principal="owner-1", receipt=_receipt(instance))
    original = CanonicalForwardEvent(
        "event-1", 0, NOW + timedelta(minutes=2), NOW + timedelta(minutes=2), DIGEST
    )
    original_observation = observe_forward_event(ForwardCursor(), original)
    await adapter.admit(
        principal="owner-1",
        instance_id=instance.instance_id,
        event=original,
        observation=original_observation,
    )
    live = await adapter.load_state(principal="owner-1", instance_id=instance.instance_id)
    assert live is not None
    correction = CanonicalForwardEvent(
        "correction-1",
        1,
        NOW + timedelta(minutes=3),
        NOW + timedelta(minutes=3),
        content_digest({"correction": "one"}),
        correction_of=original.event_id,
    )
    correction_observation = observe_forward_event(
        ForwardCursor(0, original.event_id, original.event_time), correction
    )
    command = ForwardCorrectionCommand(
        content_digest("correction-command"),
        instance.instance_id,
        correction.event_id,
        original.event_id,
        live.checkpoint.fingerprint,
        NOW + timedelta(minutes=4),
        "audit correction",
    )
    accepted = await adapter.transact(
        principal="owner-1",
        instance_id=instance.instance_id,
        event=correction,
        observation=correction_observation,
        correction_command=command,
    )
    assert accepted.decision is ForwardEventTransactionDecision.CORRECTION_ACCEPTED
    assert accepted.replay_plan is not None
    replay = await adapter.transact(
        principal="owner-1",
        instance_id=instance.instance_id,
        event=correction,
        observation=correction_observation,
        correction_command=command,
    )
    assert replay.decision is ForwardEventTransactionDecision.CORRECTION_REPLAY
    assert replay.replay_plan == accepted.replay_plan
    assert len(session.replays) == 1
    loaded_replays = await adapter.load_replays(
        principal="owner-1", instance_id=instance.instance_id
    )
    assert loaded_replays == (accepted.replay_plan,)
    assert await adapter.load_replays(principal="owner-2", instance_id=instance.instance_id) is None


def test_forward_state_schema_is_explicit_and_safe() -> None:
    schema = PostgresForwardStateSchema()
    assert len(schema.statements) == 6
    assert all("CREATE TABLE" in statement for statement in schema.statements)
    assert "PRIMARY KEY (owner_id, instance_id, event_id)" in schema.statements[2]
    assert "PRIMARY KEY (owner_id, instance_id, idempotency_key_digest)" in schema.statements[4]
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresForwardStateSchema(event_table="unsafe;drop")
