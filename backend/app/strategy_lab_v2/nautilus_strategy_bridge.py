"""Bind the engine-neutral strategy runtime to native Nautilus callbacks.

This module is imported by the isolated RC image only. Strategy code receives
the existing typed SDK context through ``StrategyInvocationSession``; the
bridge maps each serialized context to one canonical input event and replaces
its position snapshot with positions read from the running Nautilus portfolio.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from itertools import groupby
from typing import Any, BinaryIO

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.nautilus_runtime_data import NautilusRuntimeDataError


def _datetime_microsecond_ns(value: datetime) -> int:
    normalized = value.astimezone(UTC)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = normalized - epoch
    return (delta.days * 86_400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1_000


def _datetime_microsecond_bucket(value: datetime) -> int:
    """Return the event-time bucket used by the SDK's microsecond timestamps."""

    return _datetime_microsecond_ns(value) // 1_000


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
    records_by_time: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    contexts_by_time: dict[int, list[Any]] = defaultdict(list)
    for record in event_definitions:
        records_by_time[_record_time_bucket(record["event_time_ns"])].append(record)
    for context in contexts:
        contexts_by_time[_datetime_microsecond_bucket(context.event_time)].append(context)

    if set(contexts_by_time) != set(records_by_time):
        raise NautilusRuntimeDataError("strategy contexts do not cover every native event time")

    matched: dict[str, Any] = {}
    for time_bucket, records in records_by_time.items():
        time_contexts = contexts_by_time[time_bucket]
        ordered_records = sorted(
            records,
            key=lambda item: (item["sequence"], item["dependency_id"], item["event_id"]),
        )
        batch_context = len(time_contexts) == 1
        event_contexts = len(time_contexts) == len(ordered_records)
        if not batch_context and not event_contexts:
            raise NautilusRuntimeDataError(
                "same-time strategy contexts must use one batch or one context per native event"
            )

        selected: list[tuple[Any, Mapping[str, Any]]] = []
        for context in time_contexts:
            current: list[tuple[Any, Mapping[str, Any]]] = []
            for dependency_id, market_events in context.market_events.items():
                for market_event in market_events:
                    history_record = records_by_id.get(market_event.event_id)
                    if history_record is None or (
                        history_record["dependency_id"] != dependency_id
                        or history_record["instrument_id"] != market_event.instrument_id
                        or history_record["sequence"] != market_event.sequence
                        or _record_time_bucket(history_record["event_time_ns"])
                        != _datetime_microsecond_bucket(market_event.event_time)
                    ):
                        raise NautilusRuntimeDataError(
                            "strategy history contains an event outside its authenticated tape"
                        )
                    if _datetime_microsecond_bucket(market_event.event_time) == time_bucket:
                        current.append((market_event, history_record))

            if not current:
                raise NautilusRuntimeDataError(
                    "strategy context does not identify a current native event"
                )
            current_ids = [record["event_id"] for _event, record in current]
            if len(current_ids) != len(set(current_ids)):
                raise NautilusRuntimeDataError("strategy context repeats a current native event")
            if batch_context:
                expected_ids = {record["event_id"] for record in ordered_records}
                if set(current_ids) != expected_ids:
                    raise NautilusRuntimeDataError(
                        "batched strategy context must expose every same-time native event"
                    )
                if context.event_sequence != max(record["sequence"] for record in ordered_records):
                    raise NautilusRuntimeDataError(
                        "batched strategy context sequence differs from its native events"
                    )
                # Nautilus emits same-time records in canonical order. Invoke once,
                # on the final callback, after every event in the SDK batch is visible.
                selected.append((context, ordered_records[-1]))
            else:
                current_at_sequence = [
                    pair for pair in current if pair[0].sequence == context.event_sequence
                ]
                if len(current_at_sequence) != 1:
                    raise NautilusRuntimeDataError(
                        "event strategy context must identify exactly one current native event"
                    )
                selected.append((context, current_at_sequence[0][1]))

        for context, record in selected:
            event_id = record["event_id"]
            if event_id in matched:
                raise NautilusRuntimeDataError("multiple strategy contexts map to one native event")
            matched[event_id] = context

    return matched


def _iter_context_trigger_indexes(
    contexts: Iterable[Any],
    event_definitions: Sequence[Mapping[str, Any]],
) -> Iterator[tuple[int, Any]]:
    """Validate ordered context groups and yield only their native trigger indexes.

    The iterator holds one same-time group at a time. For the current SDK batch
    protocol that is one context per timestamp, so historical context objects
    are never retained for the duration of a backtest.
    """

    records_by_id: dict[str, Mapping[str, Any]] = {}
    prior_native_key: tuple[int, int, str, str] | None = None
    for record in event_definitions:
        event_id = record.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            raise NautilusRuntimeDataError("event ids must be non-empty strings")
        if event_id in records_by_id:
            raise NautilusRuntimeDataError("event ids must be unique")
        event_time_ns = record.get("event_time_ns")
        if not isinstance(event_time_ns, int) or isinstance(event_time_ns, bool):
            raise NautilusRuntimeDataError("event.event_time_ns must be a non-negative integer")
        sort_key = (
            event_time_ns,
            record["sequence"],
            record["dependency_id"],
            event_id,
        )
        if prior_native_key is not None and sort_key < prior_native_key:
            raise NautilusRuntimeDataError("native event tape is not in canonical event order")
        prior_native_key = sort_key
        records_by_id[event_id] = record

    def group_current_events(context: Any, time_bucket: int) -> list[Mapping[str, Any]]:
        current: list[Mapping[str, Any]] = []
        seen_current_ids: set[str] = set()
        for dependency_id, market_events in context.market_events.items():
            for market_event in market_events:
                history_record = records_by_id.get(market_event.event_id)
                if history_record is None or (
                    history_record["dependency_id"] != dependency_id
                    or history_record["instrument_id"] != market_event.instrument_id
                    or history_record["sequence"] != market_event.sequence
                    or _record_time_bucket(history_record["event_time_ns"])
                    != _datetime_microsecond_bucket(market_event.event_time)
                ):
                    raise NautilusRuntimeDataError(
                        "strategy history contains an event outside its authenticated tape"
                    )
                history_bucket = _datetime_microsecond_bucket(market_event.event_time)
                if history_bucket > time_bucket:
                    raise NautilusRuntimeDataError("strategy context contains a future event")
                if history_bucket == time_bucket:
                    if market_event.event_id in seen_current_ids:
                        raise NautilusRuntimeDataError(
                            "strategy context repeats a current native event"
                        )
                    seen_current_ids.add(market_event.event_id)
                    current.append(history_record)
        return current

    event_groups = iter(
        groupby(event_definitions, key=lambda record: _record_time_bucket(record["event_time_ns"]))
    )
    context_groups = iter(
        groupby(contexts, key=lambda context: _datetime_microsecond_bucket(context.event_time))
    )
    event_group = next(event_groups, None)
    context_group = next(context_groups, None)
    event_offset = 0
    previous_context_key: tuple[datetime, int] | None = None

    while event_group is not None or context_group is not None:
        if event_group is None or context_group is None or event_group[0] != context_group[0]:
            raise NautilusRuntimeDataError("strategy contexts do not cover every native event time")
        time_bucket = event_group[0]
        records = list(event_group[1])
        grouped_contexts = list(context_group[1])
        if not records or not grouped_contexts:
            raise NautilusRuntimeDataError("native event and context groups must not be empty")
        ordered_records = records
        expected_ids = {record["event_id"] for record in ordered_records}
        is_batch = len(grouped_contexts) == 1
        is_per_event = len(grouped_contexts) == len(ordered_records)
        if not is_batch and not is_per_event:
            raise NautilusRuntimeDataError(
                "same-time strategy contexts must use one batch or one context per native event"
            )

        current_context_ids: set[str] = set()
        for context in grouped_contexts:
            context_key = (context.event_time, context.event_sequence)
            if previous_context_key is not None and context_key <= previous_context_key:
                raise NautilusRuntimeDataError("strategy contexts must be strictly chronological")
            previous_context_key = context_key
            current = group_current_events(context, time_bucket)
            if not current:
                raise NautilusRuntimeDataError(
                    "strategy context does not identify a current native event"
                )
            current_ids = {record["event_id"] for record in current}
            if is_batch:
                if current_ids != expected_ids:
                    raise NautilusRuntimeDataError(
                        "batched strategy context must expose every same-time native event"
                    )
                if context.event_sequence != max(record["sequence"] for record in ordered_records):
                    raise NautilusRuntimeDataError(
                        "batched strategy context sequence differs from its native events"
                    )
                yield event_offset + len(ordered_records) - 1, context
            else:
                current_at_sequence = [
                    record for record in current if record["sequence"] == context.event_sequence
                ]
                if len(current_at_sequence) != 1:
                    raise NautilusRuntimeDataError(
                        "event strategy context must identify exactly one current native event"
                    )
                event_id = current_at_sequence[0]["event_id"]
                if event_id in current_context_ids:
                    raise NautilusRuntimeDataError(
                        "multiple strategy contexts map to one native event"
                    )
                current_context_ids.add(event_id)
                local_index = next(
                    index
                    for index, record in enumerate(ordered_records)
                    if record["event_id"] == event_id
                )
                yield event_offset + local_index, context

        if is_per_event and not is_batch and current_context_ids != expected_ids:
            raise NautilusRuntimeDataError(
                "strategy contexts do not cover every native event at their timestamp"
            )
        event_offset += len(records)
        event_group = next(event_groups, None)
        context_group = next(context_groups, None)


@dataclass(frozen=True, slots=True)
class NativeStrategyBridge:
    """Native strategy instance and its typed invocation-result wire output."""

    strategy: Any
    result_wire: Any
    input_fingerprint: str
    input_protocol: str


def build_native_strategy_bridge(
    engine_input: Mapping[str, Any],
    instrument_definitions: Sequence[Mapping[str, Any]],
    event_definitions: Sequence[Mapping[str, Any]],
    serialized_invocation_batch: str | None = None,
    *,
    invocation_context_stream: BinaryIO | None = None,
    expected_context_count: int | None = None,
) -> NativeStrategyBridge:
    """Bind a legacy batch or verified context stream to native callbacks."""

    from app.strategy_lab_v2.sdk import (
        OrderIntent,
        PositionSnapshot,
        TargetPositionIntent,
    )
    from strategy_runtime import (
        InvocationStatus,
        StrategyInvocationSession,
        deserialize_invocation_batch,
        deserialize_invocation_context_stream,
        serialize_invocation_batch_result,
    )

    if (serialized_invocation_batch is None) == (invocation_context_stream is None):
        raise NautilusRuntimeDataError(
            "provide exactly one strategy invocation batch or context stream"
        )
    if invocation_context_stream is not None:
        if not callable(getattr(invocation_context_stream, "seek", None)):
            raise NautilusRuntimeDataError("strategy context stream must be seekable")
        invocation_context_stream.seek(0)
        input_digest = hashlib.sha256()
        while chunk := invocation_context_stream.read(1024 * 1024):
            if not isinstance(chunk, bytes):
                raise NautilusRuntimeDataError("strategy context stream must be binary")
            input_digest.update(chunk)
        raw_digest = input_digest.hexdigest()
        invocation_context_stream.seek(0)
        source, manifest, stream_contexts, entrypoint, max_intents = (
            deserialize_invocation_context_stream(
                invocation_context_stream,
                expected_context_count=expected_context_count,
            )
        )

        def validate_context_inputs(source_contexts: Iterable[Any]) -> Iterator[Any]:
            for context in source_contexts:
                if context.parameters != engine_input["parameters"]:
                    raise NautilusRuntimeDataError(
                        "strategy context parameters differ from engine input"
                    )
                if context.random_seed != engine_input["random_seed"]:
                    raise NautilusRuntimeDataError(
                        "strategy context seed differs from engine input"
                    )
                yield context

        stream_context_count = sum(
            1
            for _trigger in _iter_context_trigger_indexes(
                validate_context_inputs(stream_contexts), event_definitions
            )
        )
        if expected_context_count is not None and stream_context_count != expected_context_count:
            raise NautilusRuntimeDataError(
                "strategy context stream count differs from its authenticated bundle"
            )
        invocation_context_stream.seek(0)
        (
            source,
            manifest,
            stream_contexts,
            entrypoint,
            max_intents,
        ) = deserialize_invocation_context_stream(
            invocation_context_stream,
            expected_context_count=stream_context_count,
        )
        stream_contexts = validate_context_inputs(stream_contexts)
        input_fingerprint = f"sha256:{raw_digest}"
        input_protocol = "context-stream"
        expected_contexts = stream_context_count
        context_triggers = _iter_context_trigger_indexes(stream_contexts, event_definitions)
    else:
        if (
            not isinstance(serialized_invocation_batch, str)
            or not serialized_invocation_batch.strip()
        ):
            raise NautilusRuntimeDataError("serialized strategy invocation batch is required")
        source, manifest, batch_contexts, entrypoint, max_intents = deserialize_invocation_batch(
            serialized_invocation_batch
        )
        input_fingerprint = content_digest(serialized_invocation_batch)
        input_protocol = "batch"

    if content_digest(source) != engine_input["strategy_source_digest"]:
        raise NautilusRuntimeDataError("strategy source digest differs from engine input")
    if manifest.fingerprint != engine_input["strategy_manifest_fingerprint"]:
        raise NautilusRuntimeDataError("strategy manifest differs from engine input")
    if entrypoint != engine_input["entrypoint"]:
        raise NautilusRuntimeDataError("strategy entrypoint differs from engine input")

    instrument_by_id = {item["instrument_id"]: item for item in instrument_definitions}
    declared_instruments = {
        requirement.instrument_id for requirement in manifest.capability_requirements
    }
    if not declared_instruments.issubset(instrument_by_id):
        raise NautilusRuntimeDataError(
            "strategy manifest instrument ids must match the native instrument catalog"
        )

    ordered_records = event_definitions
    if invocation_context_stream is None:
        if any(context.parameters != engine_input["parameters"] for context in batch_contexts):
            raise NautilusRuntimeDataError("strategy batch parameters differ from engine input")
        if any(context.random_seed != engine_input["random_seed"] for context in batch_contexts):
            raise NautilusRuntimeDataError("strategy batch seed differs from engine input")
        expected_contexts = len(batch_contexts)
        # Exhaust once so malformed same-time mappings are rejected before a
        # native callback can submit any orders, then recreate from the tuple.
        if sum(
            1 for _trigger in _iter_context_trigger_indexes(batch_contexts, ordered_records)
        ) != (expected_contexts):
            raise NautilusRuntimeDataError("strategy context count differs from its native tape")
        context_triggers = _iter_context_trigger_indexes(batch_contexts, ordered_records)

    current_trigger = next(context_triggers, None)
    callback_index = 0

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
            nonlocal callback_index, current_trigger
            if callback_index >= len(ordered_records):
                raise NautilusRuntimeDataError("Nautilus emitted an unexpected extra event")
            expected_record = ordered_records[callback_index]
            expected_key = (
                expected_record["event_type"],
                expected_record["instrument_id"],
                expected_record["event_time_ns"],
            )
            observed_key = (event_type, str(instrument_id), int(ts_event))
            if observed_key != expected_key:
                raise NautilusRuntimeDataError(
                    "Nautilus callback order differs from the authenticated event tape"
                )
            context = None
            if current_trigger is not None:
                trigger_index, next_context = current_trigger
                if trigger_index < callback_index:
                    raise NautilusRuntimeDataError(
                        "Nautilus did not invoke the expected strategy context callback"
                    )
                if trigger_index == callback_index:
                    context = next_context
                    current_trigger = next(context_triggers, None)
            callback_index += 1
            if context is None:
                return
            if context.parameters != engine_input["parameters"]:
                raise NautilusRuntimeDataError(
                    "strategy context parameters differ from engine input"
                )
            if context.random_seed != engine_input["random_seed"]:
                raise NautilusRuntimeDataError("strategy context seed differs from engine input")
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
        if callback_index != len(ordered_records):
            raise NautilusRuntimeDataError(
                "Nautilus did not invoke every event in the authenticated event tape"
            )
        if current_trigger is not None:
            raise NautilusRuntimeDataError(
                "Nautilus did not invoke every serialized event strategy context"
            )
        if len(invocation_results) != expected_contexts:
            raise NautilusRuntimeDataError(
                "Nautilus did not invoke every serialized strategy context"
            )
        return serialize_invocation_batch_result(invocation_results)

    return NativeStrategyBridge(
        strategy=strategy,
        result_wire=result_wire,
        input_fingerprint=input_fingerprint,
        input_protocol=input_protocol,
    )


__all__ = ["NativeStrategyBridge", "build_native_strategy_bridge"]
