"""Bind the engine-neutral strategy runtime to native Nautilus callbacks.

This module is imported by the isolated RC image only. Strategy code receives
the existing typed SDK context through ``StrategyInvocationSession``; the
bridge maps each serialized context to one canonical input event and replaces
its position snapshot with positions read from the running Nautilus portfolio.
"""

from __future__ import annotations

import hashlib
import heapq
from collections import defaultdict, deque
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import groupby
from typing import Any, BinaryIO

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.nautilus_native_event_stream import (
    deserialize_nautilus_native_event_stream,
)
from app.strategy_lab_v2.nautilus_runtime_data import NautilusRuntimeDataError
from app.strategy_lab_v2.sdk import StrategyContext


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


def _native_decimal(value: Any, field_name: str) -> Decimal:
    if isinstance(value, Decimal):
        result = value
    else:
        as_decimal = getattr(value, "as_decimal", None)
        if not callable(as_decimal):
            raise NautilusRuntimeDataError(f"native {field_name} is not an exact decimal")
        result = as_decimal()
    if not isinstance(result, Decimal) or not result.is_finite():
        raise NautilusRuntimeDataError(f"native {field_name} is not a finite decimal")
    return result


def _native_event_mark_price(event_type: str, event: Any) -> Decimal:
    if event_type == "quote":
        bid = _native_decimal(event.bid_price, "quote bid")
        ask = _native_decimal(event.ask_price, "quote ask")
        price = (bid + ask) / Decimal(2)
    elif event_type == "trade":
        price = _native_decimal(event.price, "trade price")
    elif event_type == "ohlcv":
        price = _native_decimal(event.close, "bar close")
    else:
        raise NautilusRuntimeDataError("native event type has no supported valuation mark")
    if price <= 0:
        raise NautilusRuntimeDataError("native valuation mark must be positive")
    return price


def _native_money_amount_for_currency(values: Any, currency_code: str, field_name: str) -> Decimal:
    if not isinstance(values, Mapping):
        raise NautilusRuntimeDataError(f"native {field_name} is not a currency mapping")
    matches = [
        money
        for currency, money in values.items()
        if getattr(currency, "code", str(currency)) == currency_code
    ]
    if len(matches) != 1:
        raise NautilusRuntimeDataError(f"native {field_name} does not resolve to one base currency")
    return _native_decimal(matches[0], field_name)


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


def _datetime_from_unix_nanos(value: int) -> datetime:
    seconds, nanoseconds = divmod(value, 1_000_000_000)
    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(
        seconds=seconds,
        microseconds=nanoseconds // 1_000,
    )


def _iter_stream_context_trigger_indexes(
    contexts: Iterable[Any],
    native_event_records: Iterable[Mapping[str, Any]],
    manifest: Any,
) -> Iterator[tuple[int, Any]]:
    """Verify streamed SDK history against a rolling window of native events.

    Unlike the legacy batch path, this retains only one same-time event group
    and each declared dependency's bounded lookback. The authenticated native
    stream is replayed for validation and callback-order verification rather
    than expanded into an event-id dictionary proportional to history length.
    """

    from app.strategy_lab_v2.sdk import MarketEvent

    dependencies = {item.dependency_id: item for item in manifest.data_dependencies}
    if not dependencies:
        raise NautilusRuntimeDataError("strategy manifest has no market-data dependencies")
    histories: dict[str, deque[MarketEvent]] = {
        dependency_id: deque(maxlen=dependency.lookback_periods + 1)
        for dependency_id, dependency in dependencies.items()
    }
    observed_dependencies: set[str] = set()
    prior_by_dependency: dict[str, tuple[int, int]] = {}
    event_iterator = iter(native_event_records)
    context_iterator = iter(contexts)
    current_record = next(event_iterator, None)
    event_offset = 0
    previous_context_key: tuple[datetime, int] | None = None
    max_same_time_events = 100_000

    while current_record is not None:
        time_bucket = _record_time_bucket(current_record.get("event_time_ns"))
        records: list[Mapping[str, Any]] = []
        while (
            current_record is not None
            and _record_time_bucket(current_record.get("event_time_ns")) == time_bucket
        ):
            event_id = current_record.get("event_id")
            dependency_id = current_record.get("dependency_id")
            instrument_id = current_record.get("instrument_id")
            event_time_ns = current_record.get("event_time_ns")
            sequence = current_record.get("sequence")
            event_type = current_record.get("event_type")
            values = current_record.get("values")
            if (
                not isinstance(event_id, str)
                or not event_id
                or not isinstance(dependency_id, str)
                or not isinstance(instrument_id, str)
                or not isinstance(event_time_ns, int)
                or isinstance(event_time_ns, bool)
                or not isinstance(sequence, int)
                or isinstance(sequence, bool)
                or not isinstance(event_type, str)
                or not isinstance(values, Mapping)
            ):
                raise NautilusRuntimeDataError("native event stream record fields are invalid")
            dependency = dependencies.get(dependency_id)
            if dependency is None:
                raise NautilusRuntimeDataError(
                    "native event stream contains an undeclared SDK dependency"
                )
            requirement = dependency.requirement
            event_time = _datetime_from_unix_nanos(event_time_ns)
            if (
                instrument_id != requirement.instrument_id
                or event_type != requirement.event_type
                or set(values) != set(dependency.fields)
                or not requirement.start <= event_time < requirement.end
            ):
                raise NautilusRuntimeDataError(
                    "native event stream differs from its declared SDK dependency"
                )
            previous = prior_by_dependency.get(dependency_id)
            if previous is not None and (sequence <= previous[1] or event_time_ns < previous[0]):
                raise NautilusRuntimeDataError(
                    "native dependency events must advance sequence and time"
                )
            prior_by_dependency[dependency_id] = (event_time_ns, sequence)
            event = MarketEvent(
                dependency_id,
                event_id,
                instrument_id,
                event_time,
                sequence,
                values,
            )
            histories[dependency_id].append(event)
            observed_dependencies.add(dependency_id)
            records.append(current_record)
            if len(records) > max_same_time_events:
                raise NautilusRuntimeDataError(
                    "same-time native event group exceeds its configured bound"
                )
            current_record = next(event_iterator, None)

        context = next(context_iterator, None)
        if context is None or _datetime_microsecond_bucket(context.event_time) != time_bucket:
            raise NautilusRuntimeDataError("strategy contexts do not cover every native event time")
        context_key = (context.event_time, context.event_sequence)
        if previous_context_key is not None and context_key <= previous_context_key:
            raise NautilusRuntimeDataError("strategy contexts must be strictly chronological")
        previous_context_key = context_key
        if set(context.market_events) != set(dependencies):
            raise NautilusRuntimeDataError(
                "strategy context dependencies differ from the native event stream"
            )
        current_ids = {record["event_id"] for record in records}
        observed_current_ids: set[str] = set()
        for dependency_id, market_events in context.market_events.items():
            expected_history = tuple(histories[dependency_id])
            if len(market_events) != len(expected_history):
                raise NautilusRuntimeDataError(
                    "strategy context history length differs from its declared lookback"
                )
            for actual, expected in zip(market_events, expected_history, strict=True):
                if actual != expected:
                    raise NautilusRuntimeDataError(
                        "strategy history differs from its authenticated native event stream"
                    )
                if _datetime_microsecond_bucket(actual.event_time) == time_bucket:
                    if actual.event_id in observed_current_ids:
                        raise NautilusRuntimeDataError(
                            "strategy context repeats a same-time native event"
                        )
                    observed_current_ids.add(actual.event_id)
        if observed_current_ids != current_ids:
            raise NautilusRuntimeDataError(
                "batched strategy context must expose every same-time native event"
            )
        if context.event_sequence != max(record["sequence"] for record in records):
            raise NautilusRuntimeDataError(
                "strategy context sequence differs from its native event group"
            )
        yield event_offset + len(records) - 1, context
        event_offset += len(records)

    if next(context_iterator, None) is not None:
        raise NautilusRuntimeDataError("strategy context stream contains an extra event group")
    if observed_dependencies != set(dependencies):
        raise NautilusRuntimeDataError(
            "native event stream dependencies differ from the strategy manifest"
        )


def _iter_replayed_context_trigger_indexes(contexts: Iterable[Any]) -> Iterator[tuple[int, Any]]:
    """Recreate validated native callback indexes from the authenticated contexts.

    The first pass binds each context history to the native event sidecar. During
    engine callbacks, the sidecar is also being consumed as the expected native
    event sequence, so rereading it to advance contexts would interleave two
    parsers over one seekable file descriptor. Context histories already contain
    every event in their timestamp group; use that validated projection here.
    """

    event_offset = 0
    previous_bucket: int | None = None
    for context in contexts:
        time_bucket = _datetime_microsecond_bucket(context.event_time)
        if previous_bucket is not None and time_bucket <= previous_bucket:
            raise NautilusRuntimeDataError("strategy contexts must be strictly chronological")
        previous_bucket = time_bucket
        current_event_count = sum(
            1
            for market_events in context.market_events.values()
            for event in market_events
            if _datetime_microsecond_bucket(event.event_time) == time_bucket
        )
        if current_event_count < 1:
            raise NautilusRuntimeDataError(
                "strategy context does not expose its current native event group"
            )
        event_offset += current_event_count
        yield event_offset - 1, context


@dataclass(frozen=True, slots=True)
class NativeStrategyBridge:
    """Native strategy instance and its typed invocation-result wire output."""

    strategy: Any
    result_output: Any
    input_fingerprint: str
    input_protocol: str


@dataclass(frozen=True, slots=True)
class ComponentContextTrigger:
    """One component's SDK context scheduled on a native event callback."""

    component_id: str
    priority: int
    context: StrategyContext


@dataclass(frozen=True, slots=True)
class ComponentContextTriggerGroup:
    """Component callbacks sharing one native event, in deterministic order."""

    trigger_index: int
    contexts: tuple[ComponentContextTrigger, ...]


def iter_component_context_trigger_groups(
    triggers_by_component: Mapping[str, Iterable[tuple[int, StrategyContext]]],
    priorities: Mapping[str, int],
) -> Iterator[ComponentContextTriggerGroup]:
    """Merge per-component context streams by native event and portfolio priority.

    Each component may provide no more than one strategy context for a single
    native callback. Component streams must advance strictly; same-event
    contexts across different components are grouped and ordered by priority,
    then component id. The merge is streaming and retains at most one context
    from each component.
    """

    if not isinstance(triggers_by_component, Mapping) or not triggers_by_component:
        raise NautilusRuntimeDataError("component context trigger streams are required")
    if not isinstance(priorities, Mapping) or set(priorities) != set(triggers_by_component):
        raise NautilusRuntimeDataError("component context priorities do not match trigger streams")

    def checked_stream(
        component_id: str,
        source: Iterable[tuple[int, StrategyContext]],
    ) -> Iterator[tuple[int, StrategyContext]]:
        previous_index: int | None = None
        for item in source:
            if not isinstance(item, tuple) or len(item) != 2:
                raise NautilusRuntimeDataError("component context trigger record is invalid")
            trigger_index, context = item
            if (
                not isinstance(trigger_index, int)
                or isinstance(trigger_index, bool)
                or trigger_index < 0
                or (previous_index is not None and trigger_index <= previous_index)
            ):
                raise NautilusRuntimeDataError(
                    "component context triggers must advance one per native event"
                )
            if not isinstance(context, StrategyContext):
                raise NautilusRuntimeDataError("component trigger context is invalid")
            previous_index = trigger_index
            yield trigger_index, context

    streams: dict[str, Iterator[tuple[int, StrategyContext]]] = {}
    heap: list[tuple[int, int, str, StrategyContext]] = []
    for component_id, source in triggers_by_component.items():
        priority = priorities[component_id]
        if (
            not isinstance(component_id, str)
            or not component_id.strip()
            or not isinstance(priority, int)
            or isinstance(priority, bool)
            or priority < 0
            or not isinstance(source, Iterable)
            or isinstance(source, str | bytes)
        ):
            raise NautilusRuntimeDataError("component context trigger binding is invalid")
        stream = iter(checked_stream(component_id, source))
        streams[component_id] = stream
        first = next(stream, None)
        if first is not None:
            heapq.heappush(heap, (first[0], priority, component_id, first[1]))

    while heap:
        trigger_index = heap[0][0]
        group: list[ComponentContextTrigger] = []
        while heap and heap[0][0] == trigger_index:
            _index, priority, component_id, context = heapq.heappop(heap)
            group.append(ComponentContextTrigger(component_id, priority, context))
            following = next(streams[component_id], None)
            if following is not None:
                heapq.heappush(
                    heap,
                    (following[0], priority, component_id, following[1]),
                )
        group.sort(key=lambda item: (item.priority, item.component_id))
        yield ComponentContextTriggerGroup(trigger_index, tuple(group))


def build_native_strategy_bridge(
    engine_input: Mapping[str, Any],
    instrument_definitions: Sequence[Mapping[str, Any]],
    event_definitions: Sequence[Mapping[str, Any]],
    serialized_invocation_batch: str | None = None,
    *,
    invocation_context_stream: BinaryIO | None = None,
    native_event_stream: BinaryIO | None = None,
    expected_context_count: int | None = None,
    invocation_result_stream: BinaryIO | None = None,
    max_invocation_result_bytes: int | None = None,
) -> NativeStrategyBridge:
    """Bind invocation inputs to callbacks and optionally stream callback results."""

    from app.strategy_lab_v2.nautilus_order_routing import resolve_nautilus_order_intents
    from app.strategy_lab_v2.nautilus_portfolio_wire import portfolio_composition_from_wire
    from app.strategy_lab_v2.nautilus_target_allocation import (
        resolve_nautilus_target_position_intents,
    )
    from app.strategy_lab_v2.sdk import (
        OrderIntent,
        PositionSnapshot,
        TargetPositionIntent,
    )
    from strategy_runtime import (
        MAX_INVOCATION_RESULT_STREAM_BYTES,
        InvocationResultStreamWriter,
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
    if native_event_stream is not None and invocation_context_stream is None:
        raise NautilusRuntimeDataError(
            "native event streaming requires the authenticated strategy context stream"
        )
    if invocation_result_stream is not None and not callable(
        getattr(invocation_result_stream, "write", None)
    ):
        raise NautilusRuntimeDataError("strategy result stream must provide write(bytes)")
    raw_strategy_bindings = engine_input.get("strategy_bindings")
    if (
        not isinstance(raw_strategy_bindings, list)
        or len(raw_strategy_bindings) != 1
        or not isinstance(raw_strategy_bindings[0], Mapping)
    ):
        raise NautilusRuntimeDataError(
            "current native bridge requires one authenticated component strategy binding"
        )
    strategy_binding = raw_strategy_bindings[0]
    result_stream_writer = None
    if invocation_result_stream is not None:
        result_stream_writer = InvocationResultStreamWriter(
            invocation_result_stream,
            max_stream_bytes=(
                MAX_INVOCATION_RESULT_STREAM_BYTES
                if max_invocation_result_bytes is None
                else max_invocation_result_bytes
            ),
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

        event_tape = engine_input.get("event_tape")
        if not isinstance(event_tape, Mapping):
            raise NautilusRuntimeDataError("engine input event tape is invalid")
        native_event_count = event_tape.get("event_count")
        source_tape_fingerprint = event_tape.get("source_tape_fingerprint")
        adapter_version = event_tape.get("adapter_version")
        if native_event_stream is not None:
            if (
                not isinstance(native_event_count, int)
                or isinstance(native_event_count, bool)
                or native_event_count < 1
                or not isinstance(source_tape_fingerprint, str)
                or not isinstance(adapter_version, str)
            ):
                raise NautilusRuntimeDataError("native event stream binding is invalid")
            if not callable(getattr(native_event_stream, "seek", None)):
                raise NautilusRuntimeDataError("native event stream must be seekable")

        def iter_native_event_records() -> Iterator[Mapping[str, Any]]:
            if native_event_stream is None:
                yield from event_definitions
                return
            assert isinstance(native_event_count, int)
            assert isinstance(source_tape_fingerprint, str)
            assert isinstance(adapter_version, str)
            native_event_stream.seek(0)
            yield from deserialize_nautilus_native_event_stream(
                native_event_stream,
                expected_source_tape_fingerprint=source_tape_fingerprint,
                expected_adapter_version=adapter_version,
                expected_event_count=native_event_count,
            )

        def iter_context_triggers(contexts: Iterable[Any]) -> Iterator[tuple[int, Any]]:
            if native_event_stream is None:
                yield from _iter_context_trigger_indexes(contexts, event_definitions)
            else:
                yield from _iter_stream_context_trigger_indexes(
                    contexts,
                    iter_native_event_records(),
                    manifest,
                )

        def validate_context_inputs(source_contexts: Iterable[Any]) -> Iterator[Any]:
            for context in source_contexts:
                if content_digest(context.parameters) != strategy_binding.get("parameters_digest"):
                    raise NautilusRuntimeDataError(
                        "strategy context parameters differ from component binding"
                    )
                if context.random_seed != engine_input["random_seed"]:
                    raise NautilusRuntimeDataError(
                        "strategy context seed differs from engine input"
                    )
                yield context

        stream_context_count = sum(
            1 for _trigger in iter_context_triggers(validate_context_inputs(stream_contexts))
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
        replay_contexts = validate_context_inputs(stream_contexts)
        context_triggers = (
            iter_context_triggers(replay_contexts)
            if native_event_stream is None
            else _iter_replayed_context_trigger_indexes(replay_contexts)
        )
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
    if (
        content_digest(source) != strategy_binding.get("strategy_source_digest")
        or manifest.fingerprint != strategy_binding.get("strategy_manifest_fingerprint")
        or manifest.strategy.fingerprint != strategy_binding.get("strategy_fingerprint")
        or entrypoint != strategy_binding.get("entrypoint")
        or max_intents != strategy_binding.get("max_intents_per_event")
    ):
        raise NautilusRuntimeDataError("strategy invocation differs from its component binding")

    instrument_by_id = {item["instrument_id"]: item for item in instrument_definitions}
    try:
        portfolio = portfolio_composition_from_wire(engine_input.get("portfolio"))
    except (TypeError, ValueError) as error:
        raise NautilusRuntimeDataError("engine input portfolio policy is invalid") from error
    venue_definition = engine_input.get("venue")
    if not isinstance(venue_definition, Mapping) or portfolio.base_currency != venue_definition.get(
        "base_currency"
    ):
        raise NautilusRuntimeDataError("portfolio and native account base currencies differ")
    if len(portfolio.components) != 1:
        raise NautilusRuntimeDataError("native bridge currently requires one strategy component")
    allocation_component = portfolio.components[0]
    if strategy_binding.get("component_id") != allocation_component.component_id:
        raise NautilusRuntimeDataError("strategy binding component differs from the portfolio")
    if allocation_component.strategy_fingerprint != manifest.strategy.fingerprint:
        raise NautilusRuntimeDataError("native strategy differs from its portfolio component")
    declared_instruments = {
        requirement.instrument_id for requirement in manifest.capability_requirements
    }
    if not declared_instruments.issubset(instrument_by_id):
        raise NautilusRuntimeDataError(
            "strategy manifest instrument ids must match the native instrument catalog"
        )
    if set(allocation_component.instrument_ids) != declared_instruments:
        raise NautilusRuntimeDataError(
            "portfolio component scope differs from the strategy manifest"
        )

    expected_event_count = len(event_definitions)
    if invocation_context_stream is None:
        ordered_records = event_definitions
        if any(
            content_digest(context.parameters) != strategy_binding.get("parameters_digest")
            for context in batch_contexts
        ):
            raise NautilusRuntimeDataError(
                "strategy batch parameters differ from component binding"
            )
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
    else:
        if native_event_stream is None:
            expected_event_count = len(event_definitions)
        else:
            if (
                not isinstance(native_event_count, int)
                or isinstance(native_event_count, bool)
                or native_event_count < 1
            ):
                raise NautilusRuntimeDataError("native event stream count is invalid")
            expected_event_count = native_event_count

    native_event_callbacks = (
        iter_native_event_records()
        if invocation_context_stream is not None
        else iter(event_definitions)
    )

    component_trigger_stream = iter_component_context_trigger_groups(
        {allocation_component.component_id: context_triggers},
        {allocation_component.component_id: allocation_component.priority},
    )
    current_trigger = next(component_trigger_stream, None)
    callback_index = 0

    invocation_session = StrategyInvocationSession(
        source,
        manifest=manifest,
        entrypoint=entrypoint,
        max_intents_per_event=max_intents,
    )
    invocation_results: list[Any] | None = [] if result_stream_writer is None else None
    invocation_result_count = 0
    callback_failure_types: list[str] = []

    from nautilus_trader.model import (  # type: ignore[import-not-found,attr-defined]
        BarType,
        Currency,
        InstrumentId,
        Price,
        Quantity,
        StrategyId,
        Venue,
    )
    from nautilus_trader.model import OrderSide as NativeOrderSide  # type: ignore[attr-defined]
    from nautilus_trader.model import TimeInForce as NativeTimeInForce  # type: ignore[attr-defined]
    from nautilus_trader.trading import (  # type: ignore[import-not-found,attr-defined]
        Strategy,
        StrategyConfig,
    )

    assert isinstance(venue_definition, Mapping)
    native_venue_id = Venue.from_str(venue_definition["venue_id"])
    native_base_currency = Currency.from_str(portfolio.base_currency)
    latest_marks: dict[str, tuple[Decimal, int]] = {}

    def native_risk_state(
        strategy: Any,
        *,
        event_time: datetime,
        required_mark_ids: Sequence[str],
    ) -> dict[str, Any]:
        if venue_definition["account_type"].upper() != "CASH":
            raise NautilusRuntimeDataError(
                "native order-risk routing currently requires a cash account"
            )
        marks: dict[str, Decimal] = {}
        quantities: dict[str, Decimal] = {}
        exposures: dict[str, Decimal] = {}
        for sdk_instrument_id in allocation_component.instrument_ids:
            definition = instrument_by_id[sdk_instrument_id]
            native_id = InstrumentId.from_str(sdk_instrument_id)
            native_quantity = strategy.portfolio.net_position(native_id)
            quantity = (
                Decimal(0)
                if native_quantity is None
                else _native_decimal(native_quantity, "position quantity")
            )
            quantities[sdk_instrument_id] = quantity
            if quantity == 0:
                continue
            mark_entry = latest_marks.get(sdk_instrument_id)
            if mark_entry is None or _record_time_bucket(mark_entry[1]) != (
                _datetime_microsecond_bucket(event_time)
            ):
                raise NautilusRuntimeDataError(
                    "open holdings require event-aligned native marks for allocation"
                )
            mark = mark_entry[0]
            marks[sdk_instrument_id] = mark
            native_exposure = strategy.portfolio.net_exposure(
                native_id,
                price=Price(mark, definition["price_precision"]),
                target_currency=native_base_currency,
            )
            if native_exposure is None:
                raise NautilusRuntimeDataError(
                    "native portfolio could not value an open holding for allocation"
                )
            exposure_amount = abs(_native_decimal(native_exposure, "position exposure"))
            exposures[sdk_instrument_id] = exposure_amount if quantity > 0 else -exposure_amount

        for sdk_instrument_id in required_mark_ids:
            mark_entry = latest_marks.get(sdk_instrument_id)
            if mark_entry is None or _record_time_bucket(mark_entry[1]) != (
                _datetime_microsecond_bucket(event_time)
            ):
                raise NautilusRuntimeDataError(
                    "native orders require an event-aligned native valuation mark"
                )
            marks[sdk_instrument_id] = mark_entry[0]

        native_account = strategy.portfolio.account(venue=native_venue_id)
        if native_account is None:
            raise NautilusRuntimeDataError("native portfolio has no account for its venue")
        account_base = getattr(native_account, "base_currency", None)
        if getattr(account_base, "code", str(account_base)) != portfolio.base_currency:
            raise NautilusRuntimeDataError("native cash account base currency differs")
        return {
            "account_equity": _native_money_amount_for_currency(
                strategy.portfolio.equity(venue=native_venue_id),
                portfolio.base_currency,
                "account equity",
            ),
            "account_cash_balance": _native_money_amount_for_currency(
                native_account.balances_total(),
                portfolio.base_currency,
                "account cash balance",
            ),
            "current_base_exposures": exposures,
            "current_quantities": quantities,
            "mark_prices": marks,
        }

    class _InvocationStrategyConfig(StrategyConfig):
        def __new__(cls) -> Any:
            strategy_id = StrategyId(f"SL2-{content_digest(engine_input)[-8:]}")
            return StrategyConfig.__new__(cls, strategy_id)

    class _InvocationStrategy(Strategy):
        def on_start(self) -> None:
            subscriptions: set[tuple[str, str]] = (
                {
                    (dependency.requirement.event_type, dependency.requirement.instrument_id)
                    for dependency in manifest.data_dependencies
                }
                if native_event_stream is not None
                else {
                    (record["event_type"], record["instrument_id"]) for record in event_definitions
                }
            )
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
            self._on_native_event(
                "quote", event, event.instrument_id, event.ts_event, event.ts_init
            )

        def on_trade(self, event: Any) -> None:
            self._on_native_event(
                "trade", event, event.instrument_id, event.ts_event, event.ts_init
            )

        def on_bar(self, event: Any) -> None:
            self._on_native_event(
                "ohlcv",
                event,
                event.bar_type.instrument_id,
                event.ts_event,
                event.ts_init,
            )

        def _on_native_event(
            self,
            event_type: str,
            event: Any,
            instrument_id: Any,
            ts_event: int,
            ts_init: int,
        ) -> None:
            try:
                self._dispatch_native_event(event_type, event, instrument_id, ts_event, ts_init)
            except Exception as error:
                failure = f"{type(error).__module__}.{type(error).__qualname__}"
                if isinstance(error, NautilusRuntimeDataError):
                    failure = f"{failure}: {error}"
                callback_failure_types.append(failure)

        def _dispatch_native_event(
            self,
            event_type: str,
            event: Any,
            instrument_id: Any,
            ts_event: int,
            ts_init: int,
        ) -> None:
            nonlocal callback_index, current_trigger, invocation_result_count
            try:
                expected_record = next(native_event_callbacks)
            except StopIteration:
                raise NautilusRuntimeDataError("Nautilus emitted an unexpected extra event")
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
            if (
                native_event_stream is not None
                and int(ts_init) != expected_record["native_init_time_ns"]
            ):
                raise NautilusRuntimeDataError(
                    "Nautilus callback init order differs from the authenticated event stream"
                )
            context = None
            if current_trigger is not None:
                if current_trigger.trigger_index < callback_index:
                    raise NautilusRuntimeDataError(
                        "Nautilus did not invoke the expected strategy context callback"
                    )
                if current_trigger.trigger_index == callback_index:
                    if (
                        len(current_trigger.contexts) != 1
                        or current_trigger.contexts[0].component_id
                        != allocation_component.component_id
                    ):
                        raise NautilusRuntimeDataError(
                            "native component context multiplexer binding differs"
                        )
                    context = current_trigger.contexts[0].context
                    current_trigger = next(component_trigger_stream, None)
            callback_index += 1
            latest_marks[str(instrument_id)] = (
                _native_event_mark_price(event_type, event),
                int(ts_event),
            )
            if context is None:
                return
            if content_digest(context.parameters) != strategy_binding.get("parameters_digest"):
                raise NautilusRuntimeDataError(
                    "strategy context parameters differ from component binding"
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
            if result_stream_writer is None:
                assert invocation_results is not None
                invocation_results.append(result)
            else:
                result_stream_writer.write(result)
            invocation_result_count += 1
            if result.status is not InvocationStatus.SUCCEEDED:
                return
            submission_intents = result.intents
            target_intents = tuple(
                intent for intent in result.intents if isinstance(intent, TargetPositionIntent)
            )
            if target_intents:
                if len(target_intents) != len(result.intents):
                    raise NautilusRuntimeDataError(
                        "target-position and raw order intents cannot be mixed in one callback"
                    )
                assert isinstance(venue_definition, Mapping)
                if venue_definition["account_type"].upper() != "CASH":
                    raise NautilusRuntimeDataError(
                        "target-position sizing currently requires a cash account"
                    )
                marks: dict[str, Decimal] = {}
                quantities: dict[str, Decimal] = {}
                exposures: dict[str, Decimal] = {}
                for sdk_instrument_id in allocation_component.instrument_ids:
                    definition = instrument_by_id[sdk_instrument_id]
                    native_id = InstrumentId.from_str(sdk_instrument_id)
                    native_quantity = self.portfolio.net_position(native_id)
                    quantity = (
                        Decimal(0)
                        if native_quantity is None
                        else _native_decimal(native_quantity, "position quantity")
                    )
                    quantities[sdk_instrument_id] = quantity
                    if quantity == 0:
                        continue
                    mark_entry = latest_marks.get(sdk_instrument_id)
                    if mark_entry is None or _record_time_bucket(mark_entry[1]) != (
                        _datetime_microsecond_bucket(context.event_time)
                    ):
                        raise NautilusRuntimeDataError(
                            "open holdings require event-aligned native marks for allocation"
                        )
                    mark = mark_entry[0]
                    marks[sdk_instrument_id] = mark
                    native_exposure = self.portfolio.net_exposure(
                        native_id,
                        price=Price(mark, definition["price_precision"]),
                        target_currency=native_base_currency,
                    )
                    if native_exposure is None:
                        raise NautilusRuntimeDataError(
                            "native portfolio could not value an open target-position holding"
                        )
                    exposure_amount = abs(_native_decimal(native_exposure, "position exposure"))
                    exposures[sdk_instrument_id] = (
                        exposure_amount if quantity > 0 else -exposure_amount
                    )
                for target_intent in target_intents:
                    mark_entry = latest_marks.get(target_intent.instrument_id)
                    if mark_entry is None or _record_time_bucket(mark_entry[1]) != (
                        _datetime_microsecond_bucket(context.event_time)
                    ):
                        raise NautilusRuntimeDataError(
                            "target-position intents require an event-aligned native mark"
                        )
                    marks[target_intent.instrument_id] = mark_entry[0]
                native_account = self.portfolio.account(venue=native_venue_id)
                if native_account is None:
                    raise NautilusRuntimeDataError("native portfolio has no account for its venue")
                account_base = getattr(native_account, "base_currency", None)
                if getattr(account_base, "code", str(account_base)) != portfolio.base_currency:
                    raise NautilusRuntimeDataError("native cash account base currency differs")
                account_equity = _native_money_amount_for_currency(
                    self.portfolio.equity(venue=native_venue_id),
                    portfolio.base_currency,
                    "account equity",
                )
                account_cash = _native_money_amount_for_currency(
                    native_account.balances_total(),
                    portfolio.base_currency,
                    "account cash balance",
                )
                resolution = resolve_nautilus_target_position_intents(
                    portfolio=portfolio,
                    component_id=allocation_component.component_id,
                    intents=target_intents,
                    run_attempt_id=engine_input["attempt_id"],
                    event_time=context.event_time,
                    event_sequence=context.event_sequence,
                    account_equity=account_equity,
                    account_cash_balance=account_cash,
                    current_base_exposures=exposures,
                    current_quantities=quantities,
                    mark_prices=marks,
                    instruments=instrument_by_id,
                )
                submission_intents = resolution.order_intents
            elif result.intents:
                raw_order_intents = tuple(
                    intent for intent in result.intents if isinstance(intent, OrderIntent)
                )
                if len(raw_order_intents) != len(result.intents):
                    raise NautilusRuntimeDataError("strategy emitted an unsupported typed intent")
                native_state = native_risk_state(
                    self,
                    event_time=context.event_time,
                    required_mark_ids=tuple(intent.instrument_id for intent in raw_order_intents),
                )
                order_resolution = resolve_nautilus_order_intents(
                    portfolio=portfolio,
                    component_id=allocation_component.component_id,
                    intents=raw_order_intents,
                    run_attempt_id=engine_input["attempt_id"],
                    event_time=context.event_time,
                    event_sequence=context.event_sequence,
                    instruments=instrument_by_id,
                    **native_state,
                )
                submission_intents = order_resolution.order_intents
            for intent in submission_intents:
                if isinstance(intent, TargetPositionIntent):
                    raise NautilusRuntimeDataError("target-position conversion was incomplete")
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

    def result_output() -> Any:
        if callback_failure_types:
            failure_types = ",".join(sorted(set(callback_failure_types)))
            raise NautilusRuntimeDataError(f"native strategy callback failed with {failure_types}")
        if callback_index != expected_event_count:
            raise NautilusRuntimeDataError(
                "Nautilus did not invoke every event in the authenticated event tape"
            )
        if next(native_event_callbacks, None) is not None:
            raise NautilusRuntimeDataError(
                "native event stream contains records beyond the executed tape"
            )
        if current_trigger is not None:
            raise NautilusRuntimeDataError(
                "Nautilus did not invoke every serialized event strategy context"
            )
        if invocation_result_count != expected_contexts:
            raise NautilusRuntimeDataError(
                "Nautilus did not invoke every serialized strategy context"
            )
        if result_stream_writer is not None:
            return result_stream_writer.finish()
        assert invocation_results is not None
        return serialize_invocation_batch_result(invocation_results)

    return NativeStrategyBridge(
        strategy=strategy,
        result_output=result_output,
        input_fingerprint=input_fingerprint,
        input_protocol=input_protocol,
    )


__all__ = ["NativeStrategyBridge", "build_native_strategy_bridge"]
