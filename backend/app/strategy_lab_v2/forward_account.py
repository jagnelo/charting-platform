"""Engine-neutral broker-free forward account state.

The authoritative engine/host supplies immutable order and fill observations;
this module applies them to a restart-safe shadow account without broker I/O.
Every event is append-only and idempotent, while changed content under an
existing event identity fails closed.  Persistence and Nautilus execution stay
outside this pure contract.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.forward_state import ForwardStateCheckpoint
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.sdk import (
    OrderIntent,
    OrderSide,
    PositionSnapshot,
)


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _currency(value: str, field_name: str = "currency") -> str:
    if not isinstance(value, str) or len(value) != 3 or not value.isascii() or not value.isalpha():
        raise ValueError(f"{field_name} must be a three-letter currency code")
    return value.upper()


def _finite(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{field_name} must be a finite Decimal")


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class ShadowCashBalance:
    """One immutable cash balance in the forward shadow account."""

    currency: str
    amount: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", _currency(self.currency))
        _finite(self.amount, "cash amount")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ShadowOrder:
    """One engine-accepted order intent retained without broker submission."""

    order_id: str
    event_id: str
    intent: OrderIntent

    def __post_init__(self) -> None:
        require_sha256_digest(self.order_id, field_name="order_id")
        _nonempty(self.event_id, "event_id")
        if not isinstance(self.intent, OrderIntent):
            raise TypeError("intent must be an OrderIntent")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ShadowFill:
    """One authoritative engine fill observation for a shadow order."""

    fill_id: str
    order_id: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    fee_currency: str
    filled_at: datetime

    def __post_init__(self) -> None:
        require_sha256_digest(self.fill_id, field_name="fill_id")
        require_sha256_digest(self.order_id, field_name="order_id")
        for name in ("quantity", "price"):
            value = getattr(self, name)
            _finite(value, name)
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        _finite(self.fee, "fee")
        object.__setattr__(self, "fee_currency", _currency(self.fee_currency, "fee_currency"))
        object.__setattr__(self, "filled_at", _aware(self.filled_at, "filled_at"))

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ForwardAccountEvent:
    """Immutable account effects produced while processing one canonical event."""

    instance_id: str
    event_id: str
    event_fingerprint: str
    sequence: int
    event_time: datetime
    orders: tuple[ShadowOrder, ...] = ()
    fills: tuple[ShadowFill, ...] = ()
    cash_deltas: Mapping[str, Decimal] = MappingProxyType({})

    def __post_init__(self) -> None:
        _nonempty(self.instance_id, "instance_id")
        _nonempty(self.event_id, "event_id")
        require_sha256_digest(self.event_fingerprint, field_name="event_fingerprint")
        if (
            not isinstance(self.sequence, int)
            or isinstance(self.sequence, bool)
            or self.sequence < 0
        ):
            raise ValueError("account event sequence must be a non-negative integer")
        object.__setattr__(self, "event_time", _aware(self.event_time, "event_time"))
        orders = tuple(self.orders)
        fills = tuple(self.fills)
        if any(not isinstance(item, ShadowOrder) for item in orders):
            raise TypeError("orders must contain ShadowOrder values")
        if any(not isinstance(item, ShadowFill) for item in fills):
            raise TypeError("fills must contain ShadowFill values")
        order_ids = [item.order_id for item in orders]
        fill_ids = [item.fill_id for item in fills]
        if len(order_ids) != len(set(order_ids)):
            raise ValueError("account event order ids must be unique")
        if len(fill_ids) != len(set(fill_ids)):
            raise ValueError("account event fill ids must be unique")
        if any(item.event_id != self.event_id for item in orders):
            raise ValueError("account event orders must reference the event")
        cash: dict[str, Decimal] = {}
        if not isinstance(self.cash_deltas, Mapping):
            raise TypeError("cash_deltas must be a mapping")
        for currency, amount in self.cash_deltas.items():
            normalized = _currency(currency, "cash delta currency")
            _finite(amount, "cash delta")
            if normalized in cash:
                raise ValueError("cash delta currencies must be unique")
            cash[normalized] = amount
        object.__setattr__(self, "orders", tuple(sorted(orders, key=lambda item: item.order_id)))
        object.__setattr__(self, "fills", tuple(sorted(fills, key=lambda item: item.fill_id)))
        object.__setattr__(self, "cash_deltas", MappingProxyType(dict(sorted(cash.items()))))

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ForwardRuntimeExecutionReceipt:
    """Immutable runtime/context evidence bound to one canonical account event."""

    instance_id: str
    event_id: str
    event_fingerprint: str
    delivery_binding_fingerprint: str
    context_preparation_fingerprint: str
    pre_event_checkpoint_fingerprint: str
    runtime_session_fingerprint: str
    native_output_fingerprint: str

    def __post_init__(self) -> None:
        _nonempty(self.instance_id, "instance_id")
        _nonempty(self.event_id, "event_id")
        for name in (
            "event_fingerprint",
            "delivery_binding_fingerprint",
            "context_preparation_fingerprint",
            "pre_event_checkpoint_fingerprint",
            "runtime_session_fingerprint",
            "native_output_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ForwardAccountEventBinding:
    """Bind native account effects and runtime receipt to a canonical event."""

    canonical_event: CanonicalForwardEvent
    account_event: ForwardAccountEvent
    execution_receipt: ForwardRuntimeExecutionReceipt | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.canonical_event, CanonicalForwardEvent):
            raise TypeError("canonical_event must be a CanonicalForwardEvent")
        if not isinstance(self.account_event, ForwardAccountEvent):
            raise TypeError("account_event must be a ForwardAccountEvent")
        if content_digest(self.canonical_event) != self.account_event.event_fingerprint:
            raise ValueError("account event fingerprint does not match canonical event")
        if self.account_event.event_id != self.canonical_event.event_id:
            raise ValueError("account event id does not match canonical event")
        if self.account_event.sequence != self.canonical_event.sequence:
            raise ValueError("account event sequence does not match canonical event")
        if self.account_event.event_time != self.canonical_event.event_time:
            raise ValueError("account event time does not match canonical event")
        if self.execution_receipt is not None:
            if not isinstance(self.execution_receipt, ForwardRuntimeExecutionReceipt):
                raise TypeError("execution_receipt must use ForwardRuntimeExecutionReceipt")
            if (
                self.execution_receipt.instance_id != self.account_event.instance_id
                or self.execution_receipt.event_id != self.canonical_event.event_id
                or self.execution_receipt.event_fingerprint != content_digest(self.canonical_event)
            ):
                raise ValueError("execution receipt does not match the canonical account event")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ForwardAppliedAccountEvent:
    """Append-only event identity retained for account replay protection."""

    event_id: str
    event_fingerprint: str
    event_content_fingerprint: str
    sequence: int

    def __post_init__(self) -> None:
        _nonempty(self.event_id, "event_id")
        require_sha256_digest(self.event_fingerprint, field_name="event_fingerprint")
        require_sha256_digest(
            self.event_content_fingerprint, field_name="event_content_fingerprint"
        )
        if (
            not isinstance(self.sequence, int)
            or isinstance(self.sequence, bool)
            or self.sequence < 0
        ):
            raise ValueError("applied event sequence must be a non-negative integer")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ForwardAppliedAccountExecutionEvent:
    """Append-only account event plus the runtime receipt committed with it."""

    event_id: str
    event_fingerprint: str
    event_content_fingerprint: str
    sequence: int
    execution_receipt: ForwardRuntimeExecutionReceipt

    def __post_init__(self) -> None:
        _nonempty(self.event_id, "event_id")
        require_sha256_digest(self.event_fingerprint, field_name="event_fingerprint")
        require_sha256_digest(
            self.event_content_fingerprint, field_name="event_content_fingerprint"
        )
        if (
            not isinstance(self.sequence, int)
            or isinstance(self.sequence, bool)
            or self.sequence < 0
        ):
            raise ValueError("applied event sequence must be a non-negative integer")
        if not isinstance(self.execution_receipt, ForwardRuntimeExecutionReceipt):
            raise TypeError("execution_receipt must use ForwardRuntimeExecutionReceipt")
        if (
            self.execution_receipt.event_id != self.event_id
            or self.execution_receipt.event_fingerprint != self.event_fingerprint
        ):
            raise ValueError("execution receipt does not match the applied account event")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


ForwardAppliedAccountEventRecord = ForwardAppliedAccountEvent | ForwardAppliedAccountExecutionEvent


@dataclass(frozen=True, slots=True)
class ForwardAccountState:
    """Restart-safe broker-free orders, fills, positions, and cash."""

    instance_id: str
    base_currency: str
    last_event_id: str | None = None
    last_event_sequence: int = -1
    last_event_fingerprint: str | None = None
    cash: tuple[ShadowCashBalance, ...] = ()
    positions: tuple[PositionSnapshot, ...] = ()
    orders: tuple[ShadowOrder, ...] = ()
    fills: tuple[ShadowFill, ...] = ()
    applied_events: tuple[ForwardAppliedAccountEventRecord, ...] = ()

    def __post_init__(self) -> None:
        _nonempty(self.instance_id, "instance_id")
        object.__setattr__(self, "base_currency", _currency(self.base_currency, "base_currency"))
        if self.last_event_sequence < -1:
            raise ValueError("last_event_sequence must be at least -1")
        if self.last_event_sequence == -1 and (
            self.last_event_id is not None or self.last_event_fingerprint is not None
        ):
            raise ValueError("an empty account cursor cannot contain an event")
        if self.last_event_sequence >= 0 and (
            not self.last_event_id or self.last_event_fingerprint is None
        ):
            raise ValueError("a non-empty account cursor requires event identity")
        if self.last_event_sequence >= 0 and not self.applied_events:
            raise ValueError("a non-empty account cursor requires applied event evidence")
        if self.last_event_fingerprint is not None:
            require_sha256_digest(self.last_event_fingerprint, field_name="last_event_fingerprint")
        cash = tuple(self.cash)
        positions = tuple(self.positions)
        orders = tuple(self.orders)
        fills = tuple(self.fills)
        applied = tuple(self.applied_events)
        if any(not isinstance(item, ShadowCashBalance) for item in cash):
            raise TypeError("cash must contain ShadowCashBalance values")
        if any(not isinstance(item, PositionSnapshot) for item in positions):
            raise TypeError("positions must contain PositionSnapshot values")
        if any(not isinstance(item, ShadowOrder) for item in orders):
            raise TypeError("orders must contain ShadowOrder values")
        if any(not isinstance(item, ShadowFill) for item in fills):
            raise TypeError("fills must contain ShadowFill values")
        if any(
            not isinstance(item, ForwardAppliedAccountEvent | ForwardAppliedAccountExecutionEvent)
            for item in applied
        ):
            raise TypeError("applied_events must contain ForwardAppliedAccountEvent values")
        _unique([item.currency for item in cash], "cash currencies")
        _unique([item.instrument_id for item in positions], "position instruments")
        _unique([item.order_id for item in orders], "order ids")
        _unique([item.fill_id for item in fills], "fill ids")
        _unique([item.event_id for item in applied], "applied event ids")
        order_map = {item.order_id: item for item in orders}
        if any(item.order_id not in order_map for item in fills):
            raise ValueError("every fill must reference a retained order")
        if applied:
            latest = max(applied, key=lambda item: item.sequence)
            if latest.sequence != self.last_event_sequence or latest.event_id != self.last_event_id:
                raise ValueError("account cursor must reference the latest applied event")
        if any(
            isinstance(item, ForwardAppliedAccountExecutionEvent)
            and item.execution_receipt.instance_id != self.instance_id
            for item in applied
        ):
            raise ValueError("execution receipt instance differs from account state")
        object.__setattr__(self, "cash", tuple(sorted(cash, key=lambda item: item.currency)))
        object.__setattr__(
            self, "positions", tuple(sorted(positions, key=lambda item: item.instrument_id))
        )
        object.__setattr__(self, "orders", tuple(sorted(orders, key=lambda item: item.order_id)))
        object.__setattr__(self, "fills", tuple(sorted(fills, key=lambda item: item.fill_id)))
        object.__setattr__(
            self, "applied_events", tuple(sorted(applied, key=lambda item: item.sequence))
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ForwardAccountHistoryEntry:
    """One immutable account-history root or replayable event transition."""

    revision: int
    previous_state_fingerprint: str | None
    state_fingerprint: str
    snapshot: ForwardAccountState | None = None
    event: ForwardAccountEvent | None = None
    execution_receipt: ForwardRuntimeExecutionReceipt | None = None
    baseline_checkpoint: ForwardStateCheckpoint | None = None
    baseline_warmup_receipt_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.revision, int)
            or isinstance(self.revision, bool)
            or self.revision < 0
        ):
            raise ValueError("revision must be a non-negative integer")
        require_sha256_digest(self.state_fingerprint, field_name="state_fingerprint")
        if self.revision == 0:
            if self.previous_state_fingerprint is not None:
                raise ValueError("account history root cannot have a previous state")
            if not isinstance(self.snapshot, ForwardAccountState):
                raise TypeError("account history root requires a ForwardAccountState snapshot")
            if self.event is not None or self.execution_receipt is not None:
                raise ValueError("account history root cannot contain an event")
            if self.state_fingerprint != self.snapshot.fingerprint:
                raise ValueError("account history root fingerprint differs from its snapshot")
            if self.baseline_checkpoint is not None:
                if not isinstance(self.baseline_checkpoint, ForwardStateCheckpoint):
                    raise TypeError("baseline_checkpoint must use ForwardStateCheckpoint")
                if self.baseline_checkpoint.instance.instance_id != self.snapshot.instance_id:
                    raise ValueError("account history checkpoint belongs to another instance")
            if self.baseline_warmup_receipt_fingerprint is not None:
                require_sha256_digest(
                    self.baseline_warmup_receipt_fingerprint,
                    field_name="baseline_warmup_receipt_fingerprint",
                )
            if (self.baseline_checkpoint is None) != (
                self.baseline_warmup_receipt_fingerprint is None
            ):
                raise ValueError(
                    "account history baseline checkpoint and warm-up receipt are paired"
                )
            return

        if self.previous_state_fingerprint is None:
            raise ValueError("account history transition requires its previous state fingerprint")
        require_sha256_digest(
            self.previous_state_fingerprint,
            field_name="previous_state_fingerprint",
        )
        if not isinstance(self.event, ForwardAccountEvent):
            raise TypeError("account history transition requires a ForwardAccountEvent")
        if self.snapshot is not None or self.baseline_checkpoint is not None:
            raise ValueError("account history transitions cannot contain a snapshot")
        if self.baseline_warmup_receipt_fingerprint is not None:
            raise ValueError("account history transitions cannot replace their baseline")
        if self.execution_receipt is not None:
            if not isinstance(self.execution_receipt, ForwardRuntimeExecutionReceipt):
                raise TypeError("execution_receipt must use ForwardRuntimeExecutionReceipt")
            if (
                self.execution_receipt.instance_id != self.event.instance_id
                or self.execution_receipt.event_id != self.event.event_id
                or self.execution_receipt.event_fingerprint != self.event.event_fingerprint
            ):
                raise ValueError("account history receipt does not match its event")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class ForwardAccountDecision(StrEnum):
    APPLIED = "applied"
    REPLAY_EXISTING = "replay_existing"
    CONFLICT = "conflict"
    OUT_OF_ORDER = "out_of_order"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class ForwardAccountResolution:
    decision: ForwardAccountDecision
    state: ForwardAccountState
    event_fingerprint: str
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ForwardAccountDecision):
            raise TypeError("decision must be a ForwardAccountDecision")
        if not isinstance(self.state, ForwardAccountState):
            raise TypeError("state must be a ForwardAccountState")
        require_sha256_digest(self.event_fingerprint, field_name="event_fingerprint")
        failed = {
            ForwardAccountDecision.CONFLICT,
            ForwardAccountDecision.OUT_OF_ORDER,
            ForwardAccountDecision.REJECT,
        }
        if self.decision in failed and not self.rejection_reason:
            raise ValueError("failed account resolutions require a reason")
        if self.decision not in failed and self.rejection_reason:
            raise ValueError("successful account resolutions cannot contain a reason")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def initial_forward_account_state(
    instance_id: str,
    *,
    base_currency: str,
    initial_cash: Mapping[str, Decimal] | None = None,
) -> ForwardAccountState:
    """Create one empty account with explicit initial cash balances."""

    values = initial_cash or {}
    balances = tuple(ShadowCashBalance(currency, amount) for currency, amount in values.items())
    return ForwardAccountState(instance_id, base_currency, cash=balances)


def apply_forward_account_event(
    state: ForwardAccountState,
    event: ForwardAccountEvent,
    *,
    execution_receipt: ForwardRuntimeExecutionReceipt | None = None,
) -> ForwardAccountResolution:
    """Apply one engine-produced account observation without broker I/O."""

    if not isinstance(state, ForwardAccountState):
        raise TypeError("state must be a ForwardAccountState")
    if not isinstance(event, ForwardAccountEvent):
        raise TypeError("event must be a ForwardAccountEvent")
    if execution_receipt is not None:
        if not isinstance(execution_receipt, ForwardRuntimeExecutionReceipt):
            raise TypeError("execution_receipt must use ForwardRuntimeExecutionReceipt")
        if (
            execution_receipt.instance_id != event.instance_id
            or execution_receipt.event_id != event.event_id
            or execution_receipt.event_fingerprint != event.event_fingerprint
        ):
            raise ValueError("execution receipt does not match the account event")
    if event.instance_id != state.instance_id:
        return _reject(
            state,
            event,
            ForwardAccountDecision.REJECT,
            "account event references a different forward instance",
        )
    existing = next(
        (item for item in state.applied_events if item.event_id == event.event_id), None
    )
    if existing is not None:
        existing_execution_receipt = (
            existing.execution_receipt
            if isinstance(existing, ForwardAppliedAccountExecutionEvent)
            else None
        )
        if (
            existing.event_fingerprint != event.event_fingerprint
            or existing.event_content_fingerprint != event.fingerprint
            or existing_execution_receipt != execution_receipt
        ):
            return _reject(
                state,
                event,
                ForwardAccountDecision.CONFLICT,
                "account event identity is already bound to different content",
            )
        return ForwardAccountResolution(
            ForwardAccountDecision.REPLAY_EXISTING, state, event.event_fingerprint
        )
    if event.sequence <= state.last_event_sequence:
        return _reject(
            state,
            event,
            ForwardAccountDecision.OUT_OF_ORDER,
            "account event sequence does not advance the account cursor",
        )
    order_map = {item.order_id: item for item in state.orders}
    for order in event.orders:
        if order.order_id in order_map:
            return _reject(
                state,
                event,
                ForwardAccountDecision.CONFLICT,
                "account order identity is already bound",
            )
        order_map[order.order_id] = order
    fill_map = {item.fill_id: item for item in state.fills}
    position_map = {item.instrument_id: item for item in state.positions}
    cash_map = {item.currency: item.amount for item in state.cash}
    filled_quantities: dict[str, Decimal] = {}
    for fill in state.fills:
        filled_quantities[fill.order_id] = (
            filled_quantities.get(fill.order_id, Decimal(0)) + fill.quantity
        )
    for fill in event.fills:
        if fill.fill_id in fill_map:
            return _reject(
                state,
                event,
                ForwardAccountDecision.CONFLICT,
                "account fill identity is already bound",
            )
        fill_order = order_map.get(fill.order_id)
        if fill_order is None:
            return _reject(
                state,
                event,
                ForwardAccountDecision.REJECT,
                "account fill references an unknown order",
            )
        filled_quantity = filled_quantities.get(fill.order_id, Decimal(0)) + fill.quantity
        if filled_quantity > fill_order.intent.quantity:
            return _reject(
                state,
                event,
                ForwardAccountDecision.REJECT,
                "account fills exceed the retained order quantity",
            )
        filled_quantities[fill.order_id] = filled_quantity
        fill_map[fill.fill_id] = fill
        _apply_fill(position_map, fill_order.intent, fill)
    for currency, delta in event.cash_deltas.items():
        cash_map[currency] = cash_map.get(currency, Decimal(0)) + delta
    if execution_receipt is None:
        applied: ForwardAppliedAccountEventRecord = ForwardAppliedAccountEvent(
            event.event_id,
            event.event_fingerprint,
            event.fingerprint,
            event.sequence,
        )
    else:
        applied = ForwardAppliedAccountExecutionEvent(
            event.event_id,
            event.event_fingerprint,
            event.fingerprint,
            event.sequence,
            execution_receipt,
        )
    next_state = ForwardAccountState(
        instance_id=state.instance_id,
        base_currency=state.base_currency,
        last_event_id=event.event_id,
        last_event_sequence=event.sequence,
        last_event_fingerprint=event.event_fingerprint,
        cash=tuple(ShadowCashBalance(currency, amount) for currency, amount in cash_map.items()),
        positions=tuple(position_map.values()),
        orders=tuple(order_map.values()),
        fills=tuple(fill_map.values()),
        applied_events=state.applied_events + (applied,),
    )
    return ForwardAccountResolution(
        ForwardAccountDecision.APPLIED, next_state, event.event_fingerprint
    )


def _apply_fill(
    positions: dict[str, PositionSnapshot],
    intent: OrderIntent,
    fill: ShadowFill,
) -> None:
    signed = fill.quantity if intent.side is OrderSide.BUY else -fill.quantity
    current = positions.get(intent.instrument_id)
    quantity = current.quantity if current is not None else Decimal(0)
    average = current.average_price if current is not None else None
    next_quantity = quantity + signed
    if next_quantity == 0:
        next_average = None
    elif quantity == 0 or (quantity > 0) == (signed > 0):
        old_weight = abs(quantity) * (average or Decimal(0))
        next_average = (old_weight + abs(signed) * fill.price) / abs(next_quantity)
    elif (quantity > 0) == (next_quantity > 0):
        next_average = average
    else:
        next_average = fill.price
    positions[intent.instrument_id] = PositionSnapshot(
        intent.instrument_id,
        next_quantity,
        next_average,
        None,
    )


def _unique(values: list[str], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must be unique")


def _reject(
    state: ForwardAccountState,
    event: ForwardAccountEvent,
    decision: ForwardAccountDecision,
    reason: str,
) -> ForwardAccountResolution:
    return ForwardAccountResolution(decision, state, event.event_fingerprint, reason)


__all__ = [
    "ForwardAccountHistoryEntry",
    "ForwardAccountDecision",
    "ForwardAccountEvent",
    "ForwardAccountEventBinding",
    "ForwardAccountResolution",
    "ForwardAccountState",
    "ForwardAppliedAccountExecutionEvent",
    "ForwardAppliedAccountEvent",
    "ForwardRuntimeExecutionReceipt",
    "ShadowCashBalance",
    "ShadowFill",
    "ShadowOrder",
    "apply_forward_account_event",
    "initial_forward_account_state",
]
