from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import canonical_json, content_digest
from app.strategy_lab_v2.contracts import CarryInMode, ForwardInstance, ForwardState
from app.strategy_lab_v2.forward_account import (
    ForwardAccountEvent,
    ForwardAppliedAccountExecutionEvent,
    ForwardRuntimeExecutionReceipt,
    ShadowFill,
    ShadowOrder,
    initial_forward_account_state,
)
from app.strategy_lab_v2.forward_admission import ForwardLiveAdmissionState, ForwardSeenEvent
from app.strategy_lab_v2.forward_state import ForwardStateCheckpoint
from app.strategy_lab_v2.postgres_forward_account import (
    ForwardAccountStateDecision,
    PostgresForwardAccountAdapter,
    PostgresForwardAccountSchema,
)
from app.strategy_lab_v2.postgres_result_materialization import decode_canonical_contract
from app.strategy_lab_v2.sdk import OrderIntent, OrderSide

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)


class Result:
    def __init__(self, rows: list[dict[str, Any]] | None = None, rowcount: int = 0) -> None:
        self._rows = rows or []
        self.rowcount = rowcount

    def mappings(self) -> list[dict[str, Any]]:
        return self._rows


class Session:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict[str, Any]] = {}
        self.history_rows: list[dict[str, Any]] = []

    async def __aenter__(self) -> Session:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    def begin(self) -> Session:
        return self

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> Result:
        sql = str(statement).lstrip()
        values = dict(params or {})
        key = (values.get("owner_id", ""), values.get("instance_id", ""))
        if "strategy_lab_v2_forward_account_history" in sql:
            matching = [
                row
                for row in self.history_rows
                if (row.get("owner_id"), row.get("instance_id")) == key
            ]
            if "revision = :revision" in sql:
                matching = [row for row in matching if row.get("revision") == values["revision"]]
            if sql.startswith("SELECT"):
                return Result(sorted(matching, key=lambda row: row["revision"]))
            if sql.startswith("INSERT"):
                if any(row.get("revision") == values["revision"] for row in matching):
                    return Result(rowcount=0)
                self.history_rows.append(values)
                return Result(rowcount=1)
            raise AssertionError(sql)
        if sql.startswith("SELECT"):
            row = self.rows.get(key)
            return Result([] if row is None else [row])
        if sql.startswith("INSERT"):
            if key in self.rows:
                return Result(rowcount=0)
            self.rows[key] = values
            return Result(rowcount=1)
        if sql.startswith("UPDATE"):
            if key not in self.rows:
                return Result(rowcount=0)
            self.rows[key].update(values)
            return Result(rowcount=1)
        raise AssertionError(sql)


def _event() -> ForwardAccountEvent:
    return _event_at("event-1", 0)


def _event_at(event_id: str, sequence: int) -> ForwardAccountEvent:
    intent = OrderIntent("US.AAPL", OrderSide.BUY, Decimal("1"))
    order = ShadowOrder(content_digest(("order", event_id)), event_id, intent)
    fill = ShadowFill(
        content_digest(("fill", event_id)),
        order.order_id,
        Decimal("1"),
        Decimal("100"),
        Decimal("0"),
        "USD",
        NOW + timedelta(minutes=sequence),
    )
    return ForwardAccountEvent(
        "forward-1",
        event_id,
        content_digest(("canonical-event", event_id, sequence)),
        sequence,
        NOW + timedelta(minutes=sequence),
        (order,),
        (fill,),
        {"USD": Decimal("-100")},
    )


def _execution_receipt(
    event: ForwardAccountEvent,
    *,
    checkpoint_fingerprint: str | None = None,
) -> ForwardRuntimeExecutionReceipt:
    return ForwardRuntimeExecutionReceipt(
        instance_id=event.instance_id,
        event_id=event.event_id,
        event_fingerprint=event.event_fingerprint,
        delivery_binding_fingerprint=content_digest("delivery-binding"),
        context_preparation_fingerprint=content_digest("context-preparation"),
        pre_event_checkpoint_fingerprint=(
            checkpoint_fingerprint or content_digest("pre-event-checkpoint")
        ),
        runtime_session_fingerprint=content_digest("runtime-session"),
        native_output_fingerprint=content_digest("native-output"),
    )


def _admission_state(
    *,
    event_ids: tuple[ForwardSeenEvent, ...] = (),
    checkpoint_event_id: str | None = None,
    checkpoint_sequence: int = 0,
    processed_ids: frozenset[str] = frozenset(),
) -> ForwardLiveAdmissionState:
    instance = ForwardInstance(
        "forward-1",
        content_digest("portfolio"),
        content_digest("snapshot"),
        CarryInMode.FLAT,
        ForwardState.ACTIVE,
        checkpoint_event_id,
        checkpoint_sequence,
        0,
        NOW,
        NOW,
    )
    return ForwardLiveAdmissionState(
        ForwardStateCheckpoint(instance, processed_event_ids=processed_ids),
        content_digest("warmup-receipt"),
        event_ids,
    )


@pytest.mark.asyncio
async def test_postgres_forward_account_registers_applies_and_replays() -> None:
    session = Session()
    adapter = PostgresForwardAccountAdapter(lambda: session)
    initial = initial_forward_account_state(
        "forward-1", base_currency="USD", initial_cash={"USD": Decimal("1000")}
    )
    registered = await adapter.initialize(principal="owner-1", state=initial)
    assert registered.decision is ForwardAccountStateDecision.REGISTERED

    applied = await adapter.apply(principal="owner-1", event=_event())
    assert applied.decision is ForwardAccountStateDecision.APPLIED
    assert applied.state is not None
    assert applied.state.positions[0].quantity == Decimal("1")

    replay = await adapter.apply(principal="owner-1", event=_event())
    assert replay.decision is ForwardAccountStateDecision.REPLAY_EXISTING
    loaded = await adapter.load(principal="owner-1", instance_id="forward-1")
    assert loaded == applied.state


@pytest.mark.asyncio
async def test_native_execution_receipt_is_atomic_and_idempotently_replayed() -> None:
    session = Session()
    adapter = PostgresForwardAccountAdapter(lambda: session)
    await adapter.initialize(
        principal="owner-1",
        state=initial_forward_account_state(
            "forward-1", base_currency="USD", initial_cash={"USD": Decimal("1000")}
        ),
    )
    event = _event()
    receipt = _execution_receipt(event)

    applied = await adapter.apply(
        principal="owner-1",
        event=event,
        execution_receipt=receipt,
    )

    assert applied.decision is ForwardAccountStateDecision.APPLIED
    assert applied.execution_receipt_fingerprint == receipt.fingerprint
    assert applied.state is not None
    applied_event = applied.state.applied_events[0]
    assert isinstance(applied_event, ForwardAppliedAccountExecutionEvent)
    assert applied_event.execution_receipt == receipt
    assert (
        decode_canonical_contract(canonical_json(applied.state), type(applied.state))
        == applied.state
    )

    replay = await adapter.apply(
        principal="owner-1",
        event=event,
        execution_receipt=receipt,
    )
    assert replay.decision is ForwardAccountStateDecision.REPLAY_EXISTING
    assert replay.execution_receipt_fingerprint == receipt.fingerprint

    changed_receipt = replace(
        receipt,
        context_preparation_fingerprint=content_digest("different-context"),
    )
    drift = await adapter.apply(
        principal="owner-1",
        event=event,
        execution_receipt=changed_receipt,
    )
    assert drift.decision is ForwardAccountStateDecision.CONFLICT
    assert drift.execution_receipt_fingerprint is None


def test_postgres_forward_account_schema_is_additive_and_safe() -> None:
    schema = PostgresForwardAccountSchema()
    assert len(schema.statements) == 2
    assert "strategy_lab_v2_forward_accounts" in schema.statements[0]
    assert "strategy_lab_v2_forward_account_history" in schema.statements[1]
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresForwardAccountSchema(account_table="unsafe;drop")
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresForwardAccountSchema(history_table="unsafe;drop")


@pytest.mark.asyncio
async def test_account_history_replays_positions_at_exact_forward_checkpoint() -> None:
    session = Session()
    adapter = PostgresForwardAccountAdapter(lambda: session)
    baseline_admission = _admission_state()
    initial = initial_forward_account_state(
        "forward-1", base_currency="USD", initial_cash={"USD": Decimal("1000")}
    )
    await adapter.initialize(
        principal="owner-1",
        state=initial,
        admission_state=baseline_admission,
    )

    first = _event_at("event-1", 0)
    first_receipt = _execution_receipt(
        first,
        checkpoint_fingerprint=baseline_admission.checkpoint.fingerprint,
    )
    await adapter.apply(
        principal="owner-1",
        event=first,
        execution_receipt=first_receipt,
    )
    after_first = _admission_state(
        event_ids=(ForwardSeenEvent(first.event_id, first.event_fingerprint, first.sequence),),
        checkpoint_event_id=first.event_id,
        checkpoint_sequence=first.sequence,
        processed_ids=frozenset({first.event_id}),
    )

    second = _event_at("event-2", 1)
    second_receipt = _execution_receipt(
        second,
        checkpoint_fingerprint=after_first.checkpoint.fingerprint,
    )
    await adapter.apply(
        principal="owner-1",
        event=second,
        execution_receipt=second_receipt,
    )
    after_second = _admission_state(
        event_ids=(
            ForwardSeenEvent(first.event_id, first.event_fingerprint, first.sequence),
            ForwardSeenEvent(second.event_id, second.event_fingerprint, second.sequence),
        ),
        checkpoint_event_id=second.event_id,
        checkpoint_sequence=second.sequence,
        processed_ids=frozenset({first.event_id, second.event_id}),
    )

    historical = await adapter.load_at_checkpoint(
        principal="owner-1",
        admission_state=after_first,
    )
    latest = await adapter.load_at_checkpoint(
        principal="owner-1",
        admission_state=after_second,
    )
    assert historical is not None and latest is not None
    assert historical.last_event_id == first.event_id
    assert historical.positions[0].quantity == Decimal("1")
    assert historical.cash[0].amount == Decimal("900")
    assert latest.last_event_id == second.event_id
    assert latest.positions[0].quantity == Decimal("2")
    assert latest.cash[0].amount == Decimal("800")
    assert (
        await adapter.load_at_checkpoint(principal="owner-2", admission_state=after_first) is None
    )
    assert (
        await adapter.load_at_checkpoint(
            principal="owner-1",
            admission_state=replace(
                after_first,
                warmup_receipt_fingerprint=content_digest("different-warmup"),
            ),
        )
        is None
    )
    pending = _event_at("event-3", 2)
    pending_checkpoint = _admission_state(
        event_ids=(
            ForwardSeenEvent(first.event_id, first.event_fingerprint, first.sequence),
            ForwardSeenEvent(second.event_id, second.event_fingerprint, second.sequence),
            ForwardSeenEvent(pending.event_id, pending.event_fingerprint, pending.sequence),
        ),
        checkpoint_event_id=pending.event_id,
        checkpoint_sequence=pending.sequence,
        processed_ids=frozenset({first.event_id, second.event_id, pending.event_id}),
    )
    assert (
        await adapter.load_at_checkpoint(
            principal="owner-1",
            admission_state=pending_checkpoint,
        )
        is None
    )


def test_postgres_forward_account_state_payload_is_canonical() -> None:
    state = initial_forward_account_state("forward-1", base_currency="USD")
    assert canonical_json(state)
