from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import canonical_json, content_digest
from app.strategy_lab_v2.forward_account import (
    ForwardAccountEvent,
    ForwardAppliedAccountExecutionEvent,
    ForwardRuntimeExecutionReceipt,
    ShadowFill,
    ShadowOrder,
    initial_forward_account_state,
)
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
    intent = OrderIntent("US.AAPL", OrderSide.BUY, Decimal("1"))
    order = ShadowOrder(content_digest("order"), "event-1", intent)
    fill = ShadowFill(
        content_digest("fill"),
        order.order_id,
        Decimal("1"),
        Decimal("100"),
        Decimal("0"),
        "USD",
        NOW,
    )
    return ForwardAccountEvent(
        "forward-1",
        "event-1",
        content_digest("canonical-event"),
        0,
        NOW,
        (order,),
        (fill,),
        {"USD": Decimal("-100")},
    )


def _execution_receipt(event: ForwardAccountEvent) -> ForwardRuntimeExecutionReceipt:
    return ForwardRuntimeExecutionReceipt(
        instance_id=event.instance_id,
        event_id=event.event_id,
        event_fingerprint=event.event_fingerprint,
        delivery_binding_fingerprint=content_digest("delivery-binding"),
        context_preparation_fingerprint=content_digest("context-preparation"),
        pre_event_checkpoint_fingerprint=content_digest("pre-event-checkpoint"),
        runtime_session_fingerprint=content_digest("runtime-session"),
        native_output_fingerprint=content_digest("native-output"),
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
    assert len(schema.statements) == 1
    assert "strategy_lab_v2_forward_accounts" in schema.statements[0]
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresForwardAccountSchema(account_table="unsafe;drop")


def test_postgres_forward_account_state_payload_is_canonical() -> None:
    state = initial_forward_account_state("forward-1", base_currency="USD")
    assert canonical_json(state)
