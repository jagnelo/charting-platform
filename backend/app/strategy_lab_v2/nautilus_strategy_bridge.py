"""Bind the engine-neutral strategy runtime to native Nautilus callbacks.

This module is imported by the isolated RC image only. Strategy code receives
the existing typed SDK context through ``StrategyInvocationSession``; the
bridge maps each serialized context to one canonical input event and replaces
its position snapshot with positions read from the running Nautilus portfolio.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.nautilus_runtime_data import NautilusRuntimeDataError


def _datetime_microsecond_ns(value: datetime) -> int:
    normalized = value.astimezone(UTC)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = normalized - epoch
    return (delta.days * 86_400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1_000


def _record_time_bucket(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise NautilusRuntimeDataError("event.event_time_ns must be a non-negative integer")
    return value // 1_000


def _match_contexts_to_events(
    contexts: Sequence[Any],
    event_definitions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    records_by_id = {record["event_id"]: record for record in event_definitions}
    if len(records_by_id) != len(event_definitions):
        raise NautilusRuntimeDataError("event ids must be unique")
    matched: dict[str, Any] = {}
    for context in contexts:
        current: list[tuple[Any, Any]] = []
        for dependency_id, market_events in context.market_events.items():
            for market_event in market_events:
                if (
                    market_event.event_time == context.event_time
                    and market_event.sequence == context.event_sequence
                ):
                    record = records_by_id.get(market_event.event_id)
                    if record is None:
                        raise NautilusRuntimeDataError(
                            "strategy context references an event outside the native tape"
                        )
                    if (
                        record["dependency_id"] != dependency_id
                        or record["instrument_id"] != market_event.instrument_id
                        or record["sequence"] != market_event.sequence
                        or _record_time_bucket(record["event_time_ns"])
                        != _datetime_microsecond_ns(market_event.event_time)
                    ):
                        raise NautilusRuntimeDataError(
                            "strategy context event identity differs from the native tape"
                        )
                    current.append((market_event, record))
        if len(current) != 1:
            raise NautilusRuntimeDataError(
                "each strategy context must identify exactly one current native event"
            )
        market_event, record = current[0]
        if record is None:
            raise NautilusRuntimeDataError("strategy context event is absent from the native tape")
        event_id = record["event_id"]
        if event_id in matched:
            raise NautilusRuntimeDataError("multiple strategy contexts map to one native event")
        matched[event_id] = context

        for dependency_id, market_events in context.market_events.items():
            for history_event in market_events:
                history_record = records_by_id.get(history_event.event_id)
                if history_record is None or (
                    history_record["dependency_id"] != dependency_id
                    or history_record["instrument_id"] != history_event.instrument_id
                    or history_record["sequence"] != history_event.sequence
                    or _record_time_bucket(history_record["event_time_ns"])
                    != _datetime_microsecond_ns(history_event.event_time)
                ):
                    raise NautilusRuntimeDataError(
                        "strategy history contains an event outside its authenticated tape"
                    )

    if set(matched) != set(records_by_id):
        raise NautilusRuntimeDataError(
            "serialized strategy batch must cover every native event exactly once"
        )
    return matched


@dataclass(frozen=True, slots=True)
class NativeStrategyBridge:
    """Native strategy instance and its typed invocation-result wire output."""

    strategy: Any
    result_wire: Any
    input_fingerprint: str


def build_native_strategy_bridge(
    engine_input: Mapping[str, Any],
    instrument_definitions: Sequence[Mapping[str, Any]],
    event_definitions: Sequence[Mapping[str, Any]],
    serialized_invocation_batch: str,
) -> NativeStrategyBridge:
    """Decode and bind one existing strategy batch to native event callbacks."""

    from app.strategy_lab_v2.sdk import (
        OrderIntent,
        PositionSnapshot,
        TargetPositionIntent,
    )
    from strategy_runtime import (
        InvocationStatus,
        StrategyInvocationSession,
        deserialize_invocation_batch,
        serialize_invocation_batch_result,
    )

    if not isinstance(serialized_invocation_batch, str) or not serialized_invocation_batch.strip():
        raise NautilusRuntimeDataError("serialized strategy invocation batch is required")
    source, manifest, contexts, entrypoint, max_intents = deserialize_invocation_batch(
        serialized_invocation_batch
    )
    if content_digest(source) != engine_input["strategy_source_digest"]:
        raise NautilusRuntimeDataError("strategy batch source digest differs from engine input")
    if manifest.fingerprint != engine_input["strategy_manifest_fingerprint"]:
        raise NautilusRuntimeDataError("strategy batch manifest differs from engine input")
    if entrypoint != engine_input["entrypoint"]:
        raise NautilusRuntimeDataError("strategy batch entrypoint differs from engine input")
    if any(context.parameters != engine_input["parameters"] for context in contexts):
        raise NautilusRuntimeDataError("strategy batch parameters differ from engine input")
    if any(context.random_seed != engine_input["random_seed"] for context in contexts):
        raise NautilusRuntimeDataError("strategy batch seed differs from engine input")

    instrument_by_id = {item["instrument_id"]: item for item in instrument_definitions}
    declared_instruments = {
        requirement.instrument_id for requirement in manifest.capability_requirements
    }
    if not declared_instruments.issubset(instrument_by_id):
        raise NautilusRuntimeDataError(
            "strategy manifest instrument ids must match the native instrument catalog"
        )
    contexts_by_event = _match_contexts_to_events(contexts, event_definitions)

    native_by_event_key: dict[tuple[str, str, int], deque[Any]] = defaultdict(deque)
    ordered_records = sorted(
        event_definitions,
        key=lambda item: (
            item["event_time_ns"],
            item["sequence"],
            item["dependency_id"],
            item["event_id"],
        ),
    )
    if list(event_definitions) != ordered_records:
        raise NautilusRuntimeDataError("native event tape is not in canonical order")
    for record in event_definitions:
        native_by_event_key[
            (record["event_type"], record["instrument_id"], record["event_time_ns"])
        ].append(contexts_by_event[record["event_id"]])

    invocation_session = StrategyInvocationSession(
        source,
        manifest=manifest,
        entrypoint=entrypoint,
        max_intents_per_event=max_intents,
    )
    invocation_results: list[Any] = []
    callback_failure_types: list[str] = []

    from nautilus_trader.model import (  # type: ignore[import-not-found,attr-defined]
        BarType,
        InstrumentId,
        Price,
        Quantity,
        StrategyId,
    )
    from nautilus_trader.model import OrderSide as NativeOrderSide  # type: ignore[attr-defined]
    from nautilus_trader.model import TimeInForce as NativeTimeInForce  # type: ignore[attr-defined]
    from nautilus_trader.trading import (  # type: ignore[import-not-found,attr-defined]
        Strategy,
        StrategyConfig,
    )

    class _InvocationStrategyConfig(StrategyConfig):
        def __new__(cls) -> Any:
            strategy_id = StrategyId(f"SL2-{content_digest(engine_input)[-8:]}")
            return StrategyConfig.__new__(cls, strategy_id)

    class _InvocationStrategy(Strategy):
        def on_start(self) -> None:
            subscriptions: set[tuple[str, str]] = set()
            for record in event_definitions:
                subscriptions.add((record["event_type"], record["instrument_id"]))
            for event_type, instrument_id in sorted(subscriptions):
                native_id = InstrumentId.from_str(instrument_id)
                if event_type == "quote":
                    self.subscribe_quotes(native_id)
                elif event_type == "trade":
                    self.subscribe_trades(native_id)
                elif event_type == "ohlcv":
                    bar_type = instrument_by_id[instrument_id].get("bar_type")
                    if not isinstance(bar_type, str) or not bar_type:
                        raise NautilusRuntimeDataError(
                            "OHLCV execution requires a catalog bar_type"
                        )
                    self.subscribe_bars(BarType.from_str(bar_type))
                else:
                    raise NautilusRuntimeDataError(
                        f"unsupported native strategy event type {event_type!r}"
                    )

        def on_quote(self, event: Any) -> None:
            self._on_native_event("quote", event.instrument_id, event.ts_event)

        def on_trade(self, event: Any) -> None:
            self._on_native_event("trade", event.instrument_id, event.ts_event)

        def on_bar(self, event: Any) -> None:
            self._on_native_event(
                "ohlcv",
                event.bar_type.instrument_id,
                event.ts_event,
            )

        def _on_native_event(self, event_type: str, instrument_id: Any, ts_event: int) -> None:
            try:
                self._dispatch_native_event(event_type, instrument_id, ts_event)
            except Exception as error:
                callback_failure_types.append(
                    f"{type(error).__module__}.{type(error).__qualname__}"
                )

        def _dispatch_native_event(
            self,
            event_type: str,
            instrument_id: Any,
            ts_event: int,
        ) -> None:
            instrument_key = str(instrument_id)
            key = (event_type, instrument_key, int(ts_event))
            contexts_for_key = native_by_event_key.get(key)
            if not contexts_for_key:
                raise NautilusRuntimeDataError("Nautilus callback has no bound strategy context")
            context = contexts_for_key.popleft()
            positions: dict[str, Any] = {}
            for requirement in manifest.capability_requirements:
                sdk_instrument_id = requirement.instrument_id
                native_id = InstrumentId.from_str(sdk_instrument_id)
                native_quantity = self.portfolio.net_position(native_id)
                if native_quantity is None:
                    quantity = Decimal(0)
                elif isinstance(native_quantity, Decimal):
                    quantity = native_quantity
                else:
                    quantity = native_quantity.as_decimal()
                positions[sdk_instrument_id] = PositionSnapshot(
                    instrument_id=sdk_instrument_id,
                    quantity=quantity,
                    average_price=None,
                    market_value=None,
                )
            runtime_context = replace(context, positions=positions)
            result = invocation_session.invoke(runtime_context)
            invocation_results.append(result)
            if result.status is not InvocationStatus.SUCCEEDED:
                return
            for intent in result.intents:
                if isinstance(intent, TargetPositionIntent):
                    raise NautilusRuntimeDataError(
                        "target-position intents require the platform portfolio allocation and risk adapter"
                    )
                if not isinstance(intent, OrderIntent):
                    raise NautilusRuntimeDataError("strategy emitted an unsupported typed intent")
                definition = instrument_by_id[intent.instrument_id]
                native_instrument_id = InstrumentId.from_str(intent.instrument_id)
                native_side = NativeOrderSide.from_str(intent.side.value.upper())
                native_quantity = Quantity(intent.quantity, definition["size_precision"])
                native_tif = NativeTimeInForce.from_str(intent.time_in_force.value.upper())
                tag_values = [intent.client_tag] if intent.client_tag else None
                order_arguments = {
                    "instrument_id": native_instrument_id,
                    "order_side": native_side,
                    "quantity": native_quantity,
                    "time_in_force": native_tif,
                    "tags": tag_values,
                }
                if intent.order_type.value == "market":
                    order = self.order_factory.market(**order_arguments)
                elif intent.order_type.value == "limit":
                    order = self.order_factory.limit(
                        **order_arguments,
                        price=Price(intent.limit_price, definition["price_precision"]),
                    )
                elif intent.order_type.value == "stop_market":
                    order = self.order_factory.stop_market(
                        **order_arguments,
                        trigger_price=Price(intent.stop_price, definition["price_precision"]),
                    )
                elif intent.order_type.value == "stop_limit":
                    order = self.order_factory.stop_limit(
                        **order_arguments,
                        price=Price(intent.limit_price, definition["price_precision"]),
                        trigger_price=Price(intent.stop_price, definition["price_precision"]),
                    )
                else:
                    raise NautilusRuntimeDataError("strategy emitted an unsupported order type")
                self.submit_order(order)

    strategy = _InvocationStrategy(_InvocationStrategyConfig())

    def result_wire() -> str:
        if callback_failure_types:
            failure_types = ",".join(sorted(set(callback_failure_types)))
            raise NautilusRuntimeDataError(f"native strategy callback failed with {failure_types}")
        if any(queue for queue in native_by_event_key.values()):
            raise NautilusRuntimeDataError(
                "Nautilus did not invoke the strategy for every serialized event context"
            )
        return serialize_invocation_batch_result(invocation_results)

    return NativeStrategyBridge(
        strategy=strategy,
        result_wire=result_wire,
        input_fingerprint=content_digest(serialized_invocation_batch),
    )


__all__ = ["NativeStrategyBridge", "build_native_strategy_bridge"]
