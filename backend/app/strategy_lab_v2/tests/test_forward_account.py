from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.forward_account import (
    ForwardAccountDecision,
    ForwardAccountEvent,
    ShadowFill,
    ShadowOrder,
    apply_forward_account_event,
    initial_forward_account_state,
)
from app.strategy_lab_v2.sdk import OrderIntent, OrderSide

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)


def _order(event_id: str = "event-1") -> ShadowOrder:
    intent = OrderIntent("US.AAPL", OrderSide.BUY, Decimal("2"))
    return ShadowOrder(content_digest("order-1"), event_id, intent)


def _fill(order: ShadowOrder, *, fill_id: str = "fill-1", quantity: str = "2") -> ShadowFill:
    return ShadowFill(
        content_digest(fill_id),
        order.order_id,
        Decimal(quantity),
        Decimal("100"),
        Decimal("0.25"),
        "USD",
        NOW,
    )


def _event(
    order: ShadowOrder,
    *,
    event_id: str = "event-1",
    sequence: int = 0,
    fills: tuple[ShadowFill, ...] | None = None,
) -> ForwardAccountEvent:
    return ForwardAccountEvent(
        event_id,
        content_digest({"canonical": event_id}),
        sequence,
        NOW + timedelta(seconds=sequence),
        (order,),
        fills if fills is not None else (_fill(order),),
        {"USD": Decimal("-200.25")},
    )


def test_forward_account_applies_fill_to_positions_and_cash() -> None:
    state = initial_forward_account_state(
        "forward-1", base_currency="USD", initial_cash={"USD": Decimal("1000")}
    )
    order = _order()
    resolution = apply_forward_account_event(state, _event(order))

    assert resolution.decision is ForwardAccountDecision.APPLIED
    assert resolution.state.positions[0].quantity == Decimal("2")
    assert resolution.state.positions[0].average_price == Decimal("100")
    assert resolution.state.cash[0].amount == Decimal("799.75")
    assert len(resolution.state.orders) == 1
    assert len(resolution.state.fills) == 1


def test_forward_account_replays_exact_event_and_rejects_changed_content() -> None:
    state = initial_forward_account_state("forward-1", base_currency="USD")
    order = _order()
    event = _event(order)
    applied = apply_forward_account_event(state, event)

    replay = apply_forward_account_event(applied.state, event)
    assert replay.decision is ForwardAccountDecision.REPLAY_EXISTING
    assert replay.state == applied.state

    changed = _event(order, fills=(_fill(order, quantity="1"),))
    conflict = apply_forward_account_event(applied.state, changed)
    assert conflict.decision is ForwardAccountDecision.CONFLICT


def test_forward_account_rejects_unknown_or_overfilled_orders() -> None:
    state = initial_forward_account_state("forward-1", base_currency="USD")
    unknown = ShadowFill(
        content_digest("unknown-fill"),
        content_digest("unknown-order"),
        Decimal("1"),
        Decimal("100"),
        Decimal("0"),
        "USD",
        NOW,
    )
    unknown_event = ForwardAccountEvent(
        "event-1",
        content_digest("event-1"),
        0,
        NOW,
        fills=(unknown,),
    )
    rejected = apply_forward_account_event(state, unknown_event)
    assert rejected.decision is ForwardAccountDecision.REJECT

    order = _order()
    overfilled = apply_forward_account_event(
        state,
        _event(order, fills=(_fill(order, quantity="3"),)),
    )
    assert overfilled.decision is ForwardAccountDecision.REJECT


def test_forward_account_rejects_out_of_order_events() -> None:
    state = initial_forward_account_state("forward-1", base_currency="USD")
    order = _order()
    applied = apply_forward_account_event(state, _event(order))
    next_order = _order("event-2")
    out_of_order = apply_forward_account_event(
        applied.state,
        _event(next_order, event_id="event-2", sequence=0),
    )
    assert out_of_order.decision is ForwardAccountDecision.OUT_OF_ORDER
