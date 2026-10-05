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
from app.strategy_lab_v2.contracts import PortfolioComposition
from app.strategy_lab_v2.forward_account import ForwardAccountEvent, ShadowFill, ShadowOrder
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.nautilus_equity_trace import NautilusAccountEquityTraceWriter
from app.strategy_lab_v2.nautilus_native_event_stream import (
    NautilusNativeEventStreamCursor,
    deserialize_nautilus_native_event_stream,
)
from app.strategy_lab_v2.nautilus_rebalance_schedule import (
    NautilusRebalanceScheduleCursor,
    RebalanceBoundaryAction,
    RebalanceBoundaryTransition,
)
from app.strategy_lab_v2.nautilus_runtime_data import NautilusRuntimeDataError
from app.strategy_lab_v2.nautilus_session_equity import NautilusSessionCloseEquityObservation
from app.strategy_lab_v2.rebalance import SessionCalendarSnapshot
from app.strategy_lab_v2.sdk import (
    MarketEvent,
    OrderIntent,
    OrderSide,
    PositionSnapshot,
    StrategyContext,
    TargetPositionIntent,
)

NAUTILUS_COMPONENT_ORDER_TAG_PREFIX = "strategy-lab-v2:component:"


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


def _evaluation_window_bounds(
    engine_input: Mapping[str, Any],
) -> tuple[int, int, int] | None:
    value = engine_input.get("evaluation_window")
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise NautilusRuntimeDataError("evaluation window must be a mapping")
    start_ns = value.get("start_ns")
    end_ns = value.get("end_ns")
    warmup_start_ns = value.get("warmup_start_ns")
    if (
        not isinstance(start_ns, int)
        or isinstance(start_ns, bool)
        or start_ns < 0
        or not isinstance(end_ns, int)
        or isinstance(end_ns, bool)
        or end_ns <= start_ns
        or (
            warmup_start_ns is not None
            and (
                not isinstance(warmup_start_ns, int)
                or isinstance(warmup_start_ns, bool)
                or warmup_start_ns < 0
                or warmup_start_ns > start_ns
            )
        )
    ):
        raise NautilusRuntimeDataError("evaluation window bounds are invalid")
    lower_ns = start_ns if warmup_start_ns is None else warmup_start_ns
    return lower_ns, start_ns, end_ns


def _suppress_warmup_intents(
    result: Any,
    event_time_ns: int,
    bounds: tuple[int, int, int] | None,
) -> Any:
    if bounds is not None and event_time_ns < bounds[1] and result.intents:
        return replace(result, intents=())
    return result


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


def _native_event_margin_price(event_type: str, event: Any) -> Decimal:
    """Use an adverse event-side price for native futures margin projection."""

    if event_type == "quote":
        price = _native_decimal(event.ask_price, "quote ask")
    elif event_type == "trade":
        price = _native_decimal(event.price, "trade price")
    elif event_type == "ohlcv":
        price = _native_decimal(event.high, "bar high")
    else:
        raise NautilusRuntimeDataError("native event type has no supported margin price")
    if price <= 0:
        raise NautilusRuntimeDataError("native futures margin price must be positive")
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


def _native_cash_balances(account: Any) -> dict[str, Decimal]:
    balances = account.balances_total()
    if not isinstance(balances, Mapping):
        raise NautilusRuntimeDataError("native account cash balances are not a currency mapping")
    result: dict[str, Decimal] = {}
    for currency, amount in balances.items():
        code = getattr(currency, "code", str(currency))
        if not isinstance(code, str) or len(code) != 3 or not code.isascii() or not code.isalpha():
            raise NautilusRuntimeDataError("native account cash currency is invalid")
        normalized_code = code.upper()
        if normalized_code in result:
            raise NautilusRuntimeDataError("native account cash currency is duplicated")
        result[normalized_code] = _native_decimal(amount, "account cash balance")
    return dict(sorted(result.items()))


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


def _iter_stream_component_context_trigger_groups(
    contexts: Iterable[tuple[str, StrategyContext]],
    native_event_records: Iterable[Mapping[str, Any]],
    bindings: Mapping[str, Any],
    priorities: Mapping[str, int],
) -> Iterator[ComponentContextTriggerGroup]:
    """Validate per-component histories and merge them on one native event tape."""

    if not isinstance(bindings, Mapping) or not bindings:
        raise NautilusRuntimeDataError("component context bindings are required")
    if not isinstance(priorities, Mapping) or set(priorities) != set(bindings):
        raise NautilusRuntimeDataError("component context priorities do not match bindings")

    dependencies_by_component: dict[str, dict[str, Any]] = {}
    shared_dependency_shapes: dict[str, tuple[Any, tuple[str, ...]]] = {}
    components_by_dependency: dict[str, list[str]] = defaultdict(list)
    histories: dict[str, dict[str, deque[MarketEvent]]] = {}
    prior_by_dependency: dict[tuple[str, str], tuple[int, int]] = {}
    observed_dependencies: dict[str, set[str]] = {}
    for component_id, binding in bindings.items():
        if not isinstance(component_id, str) or not component_id.strip():
            raise NautilusRuntimeDataError("component context binding id is invalid")
        manifest = getattr(binding, "manifest", None)
        raw_dependencies = getattr(manifest, "data_dependencies", None)
        if not isinstance(raw_dependencies, tuple) or not raw_dependencies:
            raise NautilusRuntimeDataError("component strategy manifest has no data dependencies")
        dependencies = {item.dependency_id: item for item in raw_dependencies}
        if len(dependencies) != len(raw_dependencies):
            raise NautilusRuntimeDataError("component strategy dependency ids are not unique")
        dependencies_by_component[component_id] = dependencies
        histories[component_id] = {
            dependency_id: deque(maxlen=dependency.lookback_periods + 1)
            for dependency_id, dependency in dependencies.items()
        }
        observed_dependencies[component_id] = set()
        for dependency_id, dependency in dependencies.items():
            shape = (dependency.requirement, dependency.fields)
            previous_shape = shared_dependency_shapes.get(dependency_id)
            if previous_shape is not None and previous_shape != shape:
                raise NautilusRuntimeDataError(
                    "components bind one dependency id to different market-data semantics"
                )
            shared_dependency_shapes[dependency_id] = shape
            components_by_dependency[dependency_id].append(component_id)
            prior_by_dependency[(component_id, dependency_id)] = (-1, -1)
        priority = priorities[component_id]
        if not isinstance(priority, int) or isinstance(priority, bool) or priority < 0:
            raise NautilusRuntimeDataError("component context priority is invalid")

    event_iterator = iter(native_event_records)
    context_iterator = iter(contexts)
    current_record = next(event_iterator, None)
    current_context = next(context_iterator, None)
    event_offset = 0
    previous_context_key: dict[str, tuple[datetime, int]] = {}
    max_same_time_events = 100_000

    while current_record is not None:
        time_bucket = _record_time_bucket(current_record.get("event_time_ns"))
        records: list[Mapping[str, Any]] = []
        event_ids: set[str] = set()
        records_by_component: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
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
                or event_id in event_ids
                or not isinstance(dependency_id, str)
                or not isinstance(instrument_id, str)
                or not isinstance(event_time_ns, int)
                or isinstance(event_time_ns, bool)
                or not isinstance(sequence, int)
                or isinstance(sequence, bool)
                or not isinstance(event_type, str)
                or not isinstance(values, Mapping)
            ):
                raise NautilusRuntimeDataError("native component event fields are invalid")
            dependency_shape = shared_dependency_shapes.get(dependency_id)
            if dependency_shape is None:
                raise NautilusRuntimeDataError(
                    "native event stream contains a dependency undeclared by every component"
                )
            requirement, fields = dependency_shape
            event_time = _datetime_from_unix_nanos(event_time_ns)
            if (
                instrument_id != requirement.instrument_id
                or event_type != requirement.event_type
                or set(values) != set(fields)
                or not requirement.start <= event_time < requirement.end
            ):
                raise NautilusRuntimeDataError(
                    "native event stream differs from a component data dependency"
                )
            event_ids.add(event_id)
            records.append(current_record)
            if len(records) > max_same_time_events:
                raise NautilusRuntimeDataError(
                    "same-time native event group exceeds its configured bound"
                )
            for component_id in components_by_dependency[dependency_id]:
                previous = prior_by_dependency[(component_id, dependency_id)]
                if previous != (-1, -1) and (
                    sequence <= previous[1] or event_time_ns < previous[0]
                ):
                    raise NautilusRuntimeDataError(
                        "component dependency events must advance sequence and time"
                    )
                prior_by_dependency[(component_id, dependency_id)] = (
                    event_time_ns,
                    sequence,
                )
                histories[component_id][dependency_id].append(
                    MarketEvent(
                        dependency_id,
                        event_id,
                        instrument_id,
                        event_time,
                        sequence,
                        values,
                    )
                )
                observed_dependencies[component_id].add(dependency_id)
                records_by_component[component_id].append(current_record)
            current_record = next(event_iterator, None)

        contexts_by_component: dict[str, StrategyContext] = {}
        if current_context is not None and (
            _datetime_microsecond_bucket(current_context[1].event_time) < time_bucket
        ):
            raise NautilusRuntimeDataError(
                "component context stream regresses behind native events"
            )
        while current_context is not None and (
            _datetime_microsecond_bucket(current_context[1].event_time) == time_bucket
        ):
            component_id, context = current_context
            if component_id not in bindings or not isinstance(context, StrategyContext):
                raise NautilusRuntimeDataError(
                    "component context record has no authenticated binding"
                )
            if component_id in contexts_by_component:
                raise NautilusRuntimeDataError(
                    "a component emitted multiple contexts for one native event time"
                )
            context_key = (context.event_time, context.event_sequence)
            previous_key = previous_context_key.get(component_id)
            if previous_key is not None and context_key <= previous_key:
                raise NautilusRuntimeDataError(
                    "component strategy contexts are not strictly chronological"
                )
            previous_context_key[component_id] = context_key
            contexts_by_component[component_id] = context
            current_context = next(context_iterator, None)

        relevant_components = {
            component_id
            for component_id, component_records in records_by_component.items()
            if component_records
        }
        if set(contexts_by_component) != relevant_components:
            raise NautilusRuntimeDataError(
                "component contexts do not cover their declared native event groups"
            )

        group: list[ComponentContextTrigger] = []
        for component_id, context in contexts_by_component.items():
            dependencies = dependencies_by_component[component_id]
            if set(context.market_events) != set(dependencies):
                raise NautilusRuntimeDataError(
                    "component context dependencies differ from its authenticated manifest"
                )
            component_records = records_by_component[component_id]
            current_ids = {record["event_id"] for record in component_records}
            observed_current_ids: set[str] = set()
            for dependency_id, market_events in context.market_events.items():
                expected_history = tuple(histories[component_id][dependency_id])
                if len(market_events) != len(expected_history):
                    raise NautilusRuntimeDataError(
                        "component context history length differs from its declared lookback"
                    )
                for actual, expected in zip(market_events, expected_history, strict=True):
                    if actual != expected:
                        raise NautilusRuntimeDataError(
                            "component strategy history differs from the authenticated event tape"
                        )
                    if _datetime_microsecond_bucket(actual.event_time) == time_bucket:
                        if actual.event_id in observed_current_ids:
                            raise NautilusRuntimeDataError(
                                "component context repeats a same-time native event"
                            )
                        observed_current_ids.add(actual.event_id)
            if observed_current_ids != current_ids:
                raise NautilusRuntimeDataError(
                    "component context does not expose every declared same-time event"
                )
            if context.event_sequence != max(record["sequence"] for record in component_records):
                raise NautilusRuntimeDataError(
                    "component context sequence differs from its native event group"
                )
            group.append(
                ComponentContextTrigger(
                    component_id,
                    priorities[component_id],
                    context,
                )
            )

        if not group:
            raise NautilusRuntimeDataError("native event group has no component invocation")
        group.sort(key=lambda item: (item.priority, item.component_id))
        yield ComponentContextTriggerGroup(event_offset + len(records) - 1, tuple(group))
        event_offset += len(records)

    if current_context is not None:
        raise NautilusRuntimeDataError("component context stream contains an extra event group")
    for component_id, dependencies in dependencies_by_component.items():
        if observed_dependencies[component_id] != set(dependencies):
            raise NautilusRuntimeDataError(
                "native event stream dependencies differ from a component manifest"
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


def _iter_replayed_component_context_trigger_groups(
    contexts: Iterable[tuple[str, StrategyContext]],
    priorities: Mapping[str, int],
) -> Iterator[ComponentContextTriggerGroup]:
    """Replay prevalidated component callbacks without reopening the native tape."""

    iterator = iter(contexts)
    current = next(iterator, None)
    event_offset = 0
    previous_bucket: int | None = None
    while current is not None:
        component_id, context = current
        if component_id not in priorities or not isinstance(context, StrategyContext):
            raise NautilusRuntimeDataError("replayed component context binding is invalid")
        time_bucket = _datetime_microsecond_bucket(context.event_time)
        if previous_bucket is not None and time_bucket <= previous_bucket:
            raise NautilusRuntimeDataError(
                "replayed component contexts are not strictly chronological by event time"
            )
        contexts_by_component: dict[str, StrategyContext] = {}
        event_ids: set[str] = set()
        while current is not None and (
            _datetime_microsecond_bucket(current[1].event_time) == time_bucket
        ):
            component_id, context = current
            if component_id not in priorities or not isinstance(context, StrategyContext):
                raise NautilusRuntimeDataError("replayed component context binding is invalid")
            if component_id in contexts_by_component:
                raise NautilusRuntimeDataError(
                    "replayed component stream has multiple contexts for one event time"
                )
            contexts_by_component[component_id] = context
            component_event_ids: set[str] = set()
            for market_events in context.market_events.values():
                for event in market_events:
                    if _datetime_microsecond_bucket(event.event_time) == time_bucket:
                        if event.event_id in component_event_ids:
                            raise NautilusRuntimeDataError(
                                "replayed component context repeats a same-time native event"
                            )
                        component_event_ids.add(event.event_id)
                        event_ids.add(event.event_id)
            current = next(iterator, None)
        if not event_ids:
            raise NautilusRuntimeDataError(
                "replayed component contexts do not expose their current native event group"
            )
        previous_bucket = time_bucket
        event_offset += len(event_ids)
        group = tuple(
            ComponentContextTrigger(component_id, priorities[component_id], context)
            for component_id, context in sorted(
                contexts_by_component.items(),
                key=lambda item: (priorities[item[0]], item[0]),
            )
        )
        yield ComponentContextTriggerGroup(event_offset - 1, group)


@dataclass(frozen=True, slots=True)
class NativeStrategyBridge:
    """Native strategy instance and its typed runtime-evidence outputs."""

    strategy: Any
    result_output: Any
    account_equity_trace_output: Any
    session_close_equity_output: Any
    rebalance_schedule_output: Any
    stage_forward_event: Any
    take_forward_account_event: Any
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


@dataclass(slots=True)
class _PendingComponentOrder:
    component_id: str
    instrument_id: str
    side: OrderSide
    remaining_quantity: Decimal


@dataclass(slots=True)
class _PendingForwardAccountEvent:
    instance_id: str
    canonical_event: CanonicalForwardEvent
    callback_index: int
    cash_before: Mapping[str, Decimal]
    orders: list[ShadowOrder]
    fills: list[ShadowFill]


class NautilusComponentFillLedger:
    """Attribute native order fills to portfolio components and reconcile net lots."""

    def __init__(self, portfolio: PortfolioComposition) -> None:
        if not isinstance(portfolio, PortfolioComposition):
            raise TypeError("portfolio must be a PortfolioComposition")
        self._instruments_by_component = {
            component.component_id: frozenset(component.instrument_ids)
            for component in portfolio.components
        }
        self._quantities = {
            component.component_id: {
                instrument_id: Decimal(0) for instrument_id in component.instrument_ids
            }
            for component in portfolio.components
        }
        self._pending_orders: dict[str, _PendingComponentOrder] = {}

    def quantity(self, component_id: str, instrument_id: str) -> Decimal:
        try:
            return self._quantities[component_id][instrument_id]
        except KeyError as error:
            raise NautilusRuntimeDataError(
                "component fill ledger references an undeclared position"
            ) from error

    def quantities_by_component(self) -> Mapping[str, Mapping[str, Decimal]]:
        return {
            component_id: dict(quantities) for component_id, quantities in self._quantities.items()
        }

    def register_order(
        self,
        *,
        client_order_id: str,
        component_id: str,
        instrument_id: str,
        side: OrderSide,
        quantity: Decimal,
    ) -> None:
        if (
            not isinstance(client_order_id, str)
            or not client_order_id.strip()
            or any(character in client_order_id for character in "\x00\r\n")
        ):
            raise NautilusRuntimeDataError("native client order id is invalid")
        if client_order_id in self._pending_orders:
            raise NautilusRuntimeDataError("native client order id is already attributed")
        if (
            component_id not in self._instruments_by_component
            or instrument_id not in (self._instruments_by_component[component_id])
        ):
            raise NautilusRuntimeDataError("native order is outside its portfolio component")
        if not isinstance(side, OrderSide):
            raise NautilusRuntimeDataError("native order side is invalid")
        if not isinstance(quantity, Decimal) or not quantity.is_finite() or quantity <= 0:
            raise NautilusRuntimeDataError("native order quantity must be positive and finite")
        self._pending_orders[client_order_id] = _PendingComponentOrder(
            component_id,
            instrument_id,
            side,
            quantity,
        )

    def record_fill(
        self,
        *,
        client_order_id: str,
        instrument_id: str,
        quantity: Decimal,
    ) -> bool:
        order = self._pending_orders.get(client_order_id)
        if order is None:
            raise NautilusRuntimeDataError("native fill has no component-attributed order")
        if instrument_id != order.instrument_id:
            raise NautilusRuntimeDataError(
                "native fill instrument differs from its attributed order"
            )
        if not isinstance(quantity, Decimal) or not quantity.is_finite() or quantity <= 0:
            raise NautilusRuntimeDataError("native fill quantity must be positive and finite")
        if quantity > order.remaining_quantity:
            raise NautilusRuntimeDataError("native fill exceeds its attributed order quantity")
        sign = Decimal(1) if order.side is OrderSide.BUY else Decimal(-1)
        self._quantities[order.component_id][instrument_id] += sign * quantity
        order.remaining_quantity -= quantity
        if order.remaining_quantity == 0:
            del self._pending_orders[client_order_id]
            return False
        return True

    def release_terminal_order(self, client_order_id: str) -> None:
        if client_order_id not in self._pending_orders:
            raise NautilusRuntimeDataError("terminal native order has no component attribution")
        del self._pending_orders[client_order_id]

    def reconcile(self, account_quantities: Mapping[str, Decimal]) -> None:
        declared = {
            instrument_id
            for instruments in self._instruments_by_component.values()
            for instrument_id in instruments
        }
        if not isinstance(account_quantities, Mapping) or any(
            instrument_id not in declared
            or not isinstance(quantity, Decimal)
            or not quantity.is_finite()
            for instrument_id, quantity in account_quantities.items()
        ):
            raise NautilusRuntimeDataError("native account position quantities are invalid")
        attributed: dict[str, Decimal] = {}
        for quantities in self._quantities.values():
            for instrument_id, quantity in quantities.items():
                if quantity:
                    attributed[instrument_id] = attributed.get(instrument_id, Decimal(0)) + quantity
        attributed = {
            instrument_id: quantity for instrument_id, quantity in attributed.items() if quantity
        }
        native = {
            instrument_id: quantity
            for instrument_id, quantity in account_quantities.items()
            if quantity
        }
        if attributed != native:
            raise NautilusRuntimeDataError(
                "component fill quantities do not reconcile to native account positions"
            )


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


def _route_component_callback_orders(
    *,
    portfolio: PortfolioComposition,
    raw_intents_by_component: Mapping[str, Sequence[OrderIntent]],
    target_intents_by_component: Mapping[str, Sequence[TargetPositionIntent]],
    run_attempt_id: str,
    event_time: datetime,
    event_sequence: int,
    native_state: Mapping[str, Any],
    instruments: Mapping[str, Mapping[str, object]],
) -> Any | None:
    """Convert and risk-check one event's complete, component-attributed batch.

    Target allocation is deliberately an intermediate sizing step here. Its
    candidate orders may reduce risk only after raw intents from other
    components are included, so the combined order router is the sole
    submission gate for shared-account limits.
    """

    from app.strategy_lab_v2.nautilus_order_routing import (
        resolve_nautilus_component_order_batches,
    )
    from app.strategy_lab_v2.nautilus_target_allocation import (
        resolve_nautilus_component_target_position_batches,
    )

    orders_by_component: dict[str, list[OrderIntent]] = {
        component_id: list(intents) for component_id, intents in raw_intents_by_component.items()
    }
    if target_intents_by_component:
        target_resolution = resolve_nautilus_component_target_position_batches(
            portfolio=portfolio,
            intents_by_component=target_intents_by_component,
            defer_shared_risk_validation=True,
            run_attempt_id=run_attempt_id,
            event_time=event_time,
            event_sequence=event_sequence,
            account_equity=native_state["account_equity"],
            account_cash_balance=native_state["account_cash_balance"],
            current_base_exposures=native_state["current_base_exposures"],
            current_quantities=native_state["current_quantities"],
            current_component_exposures=native_state["current_component_exposures"],
            current_component_quantities=native_state["current_component_quantities"],
            mark_prices=native_state["mark_prices"],
            instruments=instruments,
        )
        for component_id, intents in target_resolution.component_order_intents:
            orders_by_component.setdefault(component_id, []).extend(intents)

    order_batches = {
        component_id: tuple(intents)
        for component_id, intents in orders_by_component.items()
        if intents
    }
    if not order_batches:
        return None
    return resolve_nautilus_component_order_batches(
        portfolio=portfolio,
        intents_by_component=order_batches,
        run_attempt_id=run_attempt_id,
        event_time=event_time,
        event_sequence=event_sequence,
        instruments=instruments,
        **{
            key: value
            for key, value in native_state.items()
            if key != "current_component_quantities"
        },
    )


def _validate_target_account_product_scope(
    *,
    account_type: str,
    target_intents_by_component: Mapping[str, Sequence[TargetPositionIntent]],
    instruments: Mapping[str, Mapping[str, object]],
) -> None:
    """Limit margin target sizing to futures, whose native margin gate is bound."""

    normalized_account_type = account_type.upper()
    if normalized_account_type not in {"CASH", "MARGIN"}:
        raise NautilusRuntimeDataError("target-position account type is unsupported")
    target_product_classes = {
        instruments[intent.instrument_id].get("product_class")
        for intents in target_intents_by_component.values()
        for intent in intents
        if intent.instrument_id in instruments
    }
    if normalized_account_type == "MARGIN" and target_product_classes != {"future"}:
        raise NautilusRuntimeDataError(
            "margin-account target-position sizing currently supports listed futures only"
        )
    if normalized_account_type == "CASH" and "future" in target_product_classes:
        raise NautilusRuntimeDataError("futures target-position sizing requires a margin account")


def build_native_strategy_bridge(
    engine_input: Mapping[str, Any],
    instrument_definitions: Sequence[Mapping[str, Any]],
    event_definitions: Sequence[Mapping[str, Any]],
    serialized_invocation_batch: str | None = None,
    *,
    invocation_context_stream: BinaryIO | None = None,
    native_event_stream: BinaryIO | None = None,
    expected_context_count: int | None = None,
    expected_component_context_counts: Mapping[str, int] | None = None,
    invocation_result_stream: BinaryIO | None = None,
    max_invocation_result_bytes: int | None = None,
    account_equity_trace_writer: NautilusAccountEquityTraceWriter | None = None,
    session_calendar: SessionCalendarSnapshot | None = None,
    allow_forward_event_staging: bool = False,
    retain_invocation_results: bool = True,
) -> NativeStrategyBridge:
    """Bind invocation inputs to callbacks and optionally retain callback results.

    Persistent forward sessions disable retention because native strategy
    results have already been consumed for routing and must not accumulate for
    the lifetime of the session. ``result_output`` still validates callback
    parity in that mode, but returns ``None`` instead of a serialized batch.
    """

    from app.strategy_lab_v2.nautilus_portfolio_wire import portfolio_composition_from_wire
    from app.strategy_lab_v2.nautilus_rebalance_wire import rebalance_execution_plan_from_wire
    from strategy_runtime import (
        MAX_INVOCATION_RESULT_STREAM_BYTES,
        InvocationResultStreamWriter,
        InvocationStatus,
        StrategyInvocationSession,
        deserialize_component_invocation_context_stream,
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
    component_context_stream = expected_component_context_counts is not None
    if not isinstance(allow_forward_event_staging, bool):
        raise TypeError("allow_forward_event_staging must be a boolean")
    if not isinstance(retain_invocation_results, bool):
        raise TypeError("retain_invocation_results must be a boolean")
    if not retain_invocation_results and not allow_forward_event_staging:
        raise NautilusRuntimeDataError(
            "invocation result retention can only be disabled for staged forward sessions"
        )
    if allow_forward_event_staging and not component_context_stream:
        raise NautilusRuntimeDataError(
            "forward event staging requires authenticated component context bindings"
        )
    if component_context_stream and native_event_stream is None:
        raise NautilusRuntimeDataError(
            "component context streaming requires the authenticated native event stream"
        )
    if invocation_result_stream is not None and not callable(
        getattr(invocation_result_stream, "write", None)
    ):
        raise NautilusRuntimeDataError("strategy result stream must provide write(bytes)")
    if account_equity_trace_writer is not None and (
        not callable(getattr(account_equity_trace_writer, "write", None))
        or not callable(getattr(account_equity_trace_writer, "finish", None))
    ):
        raise NautilusRuntimeDataError("account-equity trace writer is invalid")
    raw_strategy_bindings = engine_input.get("strategy_bindings")
    if (
        not isinstance(raw_strategy_bindings, list)
        or not raw_strategy_bindings
        or any(not isinstance(item, Mapping) for item in raw_strategy_bindings)
    ):
        raise NautilusRuntimeDataError(
            "native bridge requires authenticated component strategy bindings"
        )
    evaluation_window_bounds = _evaluation_window_bounds(engine_input)
    if session_calendar is not None and not isinstance(session_calendar, SessionCalendarSnapshot):
        raise TypeError("session_calendar must be a SessionCalendarSnapshot or None")
    session_close_times: dict[int, Any] = {}
    if session_calendar is not None:
        for calendar_day in session_calendar.days:
            if calendar_day.session is None:
                continue
            close_ns = _datetime_microsecond_ns(calendar_day.session.close_time)
            if close_ns in session_close_times:
                raise NautilusRuntimeDataError("session calendar has ambiguous close instants")
            session_close_times[close_ns] = calendar_day.session
    session_close_equity_observations: list[NautilusSessionCloseEquityObservation] = []
    strategy_bindings: dict[str, Mapping[str, Any]] = {}
    for item in raw_strategy_bindings:
        assert isinstance(item, Mapping)
        component_id = item.get("component_id")
        if (
            not isinstance(component_id, str)
            or not component_id.strip()
            or component_id in strategy_bindings
        ):
            raise NautilusRuntimeDataError("native component strategy binding ids are invalid")
        strategy_bindings[component_id] = item
    if not component_context_stream and len(strategy_bindings) != 1:
        raise NautilusRuntimeDataError(
            "multiple strategy bindings require authenticated component context streams"
        )
    strategy_binding = strategy_bindings[min(strategy_bindings)]
    try:
        portfolio = portfolio_composition_from_wire(engine_input.get("portfolio"))
        rebalance_plan = rebalance_execution_plan_from_wire(engine_input.get("rebalance_plan"))
    except (TypeError, ValueError) as error:
        raise NautilusRuntimeDataError(
            "engine input portfolio or rebalance plan is invalid"
        ) from error
    rebalance_policy = portfolio.rebalance_policy
    if (rebalance_policy is None) != (rebalance_plan is None):
        raise NautilusRuntimeDataError(
            "engine input rebalance plan does not match portfolio policy"
        )
    if (
        rebalance_policy is not None
        and rebalance_plan is not None
        and (
            rebalance_plan.policy_fingerprint != rebalance_policy.fingerprint
            or rebalance_plan.calendar_fingerprint != rebalance_policy.calendar_fingerprint
        )
    ):
        raise NautilusRuntimeDataError("engine input rebalance plan identity is mismatched")
    portfolio_components = {item.component_id: item for item in portfolio.components}
    component_priorities = {item.component_id: item.priority for item in portfolio.components}
    if set(strategy_bindings) != set(portfolio_components):
        raise NautilusRuntimeDataError(
            "authenticated strategy bindings must cover the complete portfolio"
        )
    venue_definition = engine_input.get("venue")
    if not isinstance(venue_definition, Mapping) or portfolio.base_currency != venue_definition.get(
        "base_currency"
    ):
        raise NautilusRuntimeDataError("portfolio and native account base currencies differ")
    component_context_bindings: dict[str, Any] = {}
    if component_context_stream:
        if (
            not isinstance(expected_component_context_counts, Mapping)
            or not expected_component_context_counts
            or any(
                not isinstance(component_id, str)
                or not component_id.strip()
                or not isinstance(count, int)
                or isinstance(count, bool)
                or count < 1
                for component_id, count in expected_component_context_counts.items()
            )
        ):
            raise NautilusRuntimeDataError("component context counts are invalid")
        if sum(expected_component_context_counts.values()) != expected_context_count:
            raise NautilusRuntimeDataError(
                "component context counts differ from the runtime bundle"
            )

    def deserialize_stream_contexts() -> tuple[str, Any, Iterator[Any], str, int]:
        assert invocation_context_stream is not None
        if not component_context_stream:
            return deserialize_invocation_context_stream(
                invocation_context_stream,
                expected_context_count=expected_context_count,
            )
        assert expected_component_context_counts is not None
        bindings, component_records = deserialize_component_invocation_context_stream(
            invocation_context_stream,
            expected_component_counts=expected_component_context_counts,
        )
        if set(bindings) != set(strategy_bindings):
            raise NautilusRuntimeDataError(
                "component context streams differ from authenticated strategy bindings"
            )
        for component_id, binding in bindings.items():
            strategy_binding_for_component = strategy_bindings[component_id]
            if (
                content_digest(binding.source)
                != strategy_binding_for_component.get("strategy_source_digest")
                or binding.manifest.fingerprint
                != strategy_binding_for_component.get("strategy_manifest_fingerprint")
                or binding.manifest.strategy.fingerprint
                != strategy_binding_for_component.get("strategy_fingerprint")
                or binding.entrypoint != strategy_binding_for_component.get("entrypoint")
                or binding.max_intents_per_event
                != strategy_binding_for_component.get("max_intents_per_event")
            ):
                raise NautilusRuntimeDataError(
                    "component context stream metadata differs from its authenticated binding"
                )
        component_context_bindings.update(bindings)
        primary_binding = bindings[next(iter(sorted(bindings)))]
        return (
            primary_binding.source,
            primary_binding.manifest,
            component_records,
            primary_binding.entrypoint,
            primary_binding.max_intents_per_event,
        )

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
        source, manifest, stream_contexts, entrypoint, max_intents = deserialize_stream_contexts()

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
            yield from deserialize_nautilus_native_event_stream(
                NautilusNativeEventStreamCursor(native_event_stream),
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

        def iter_component_context_groups(
            contexts: Iterable[Any],
        ) -> Iterator[ComponentContextTriggerGroup]:
            if component_context_stream:
                yield from _iter_stream_component_context_trigger_groups(
                    contexts,
                    iter_native_event_records(),
                    component_context_bindings,
                    component_priorities,
                )
                return
            component_id = min(strategy_bindings)

            def checked_triggers() -> Iterator[tuple[int, StrategyContext]]:
                for trigger_index, context in iter_context_triggers(contexts):
                    if not isinstance(context, StrategyContext):
                        raise NautilusRuntimeDataError(
                            "strategy context stream contains an invalid context"
                        )
                    yield trigger_index, context

            yield from iter_component_context_trigger_groups(
                {component_id: checked_triggers()},
                component_priorities,
            )

        def validate_context_inputs(source_contexts: Iterable[Any]) -> Iterator[Any]:
            for record in source_contexts:
                if component_context_stream:
                    component_id, context = record
                    binding_for_context = strategy_bindings.get(component_id)
                    if binding_for_context is None:
                        raise NautilusRuntimeDataError(
                            "component context record has no authenticated strategy binding"
                        )
                else:
                    context = record
                    binding_for_context = strategy_binding
                if content_digest(context.parameters) != binding_for_context.get(
                    "parameters_digest"
                ):
                    raise NautilusRuntimeDataError(
                        "strategy context parameters differ from component binding"
                    )
                if context.random_seed != engine_input["random_seed"]:
                    raise NautilusRuntimeDataError(
                        "strategy context seed differs from engine input"
                    )
                yield record

        if component_context_stream:
            stream_context_count = sum(
                len(group.contexts)
                for group in iter_component_context_groups(validate_context_inputs(stream_contexts))
            )
        else:
            stream_context_count = sum(
                1 for _trigger in iter_context_triggers(validate_context_inputs(stream_contexts))
            )
        if expected_context_count is not None and stream_context_count != expected_context_count:
            raise NautilusRuntimeDataError(
                "strategy context stream count differs from its authenticated bundle"
            )
        invocation_context_stream.seek(0)
        source, manifest, stream_contexts, entrypoint, max_intents = deserialize_stream_contexts()
        stream_contexts = validate_context_inputs(stream_contexts)
        input_fingerprint = f"sha256:{raw_digest}"
        input_protocol = (
            "component-context-stream" if component_context_stream else "context-stream"
        )
        expected_contexts = stream_context_count
        replay_contexts = validate_context_inputs(stream_contexts)
        if component_context_stream:
            context_trigger_groups = _iter_replayed_component_context_trigger_groups(
                replay_contexts,
                component_priorities,
            )
        else:
            context_triggers = (
                iter_context_triggers(replay_contexts)
                if native_event_stream is None
                else _iter_replayed_context_trigger_indexes(replay_contexts)
            )
            component_id = min(strategy_bindings)

            def checked_replayed_triggers() -> Iterator[tuple[int, StrategyContext]]:
                for trigger_index, context in context_triggers:
                    if not isinstance(context, StrategyContext):
                        raise NautilusRuntimeDataError(
                            "strategy context stream contains an invalid context"
                        )
                    yield trigger_index, context

            context_trigger_groups = iter_component_context_trigger_groups(
                {component_id: checked_replayed_triggers()},
                component_priorities,
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

    instrument_by_id = {item["instrument_id"]: item for item in instrument_definitions}
    strategy_binding = strategy_bindings[min(strategy_bindings)]
    if (
        content_digest(source) != engine_input["strategy_source_digest"]
        or manifest.fingerprint != engine_input["strategy_manifest_fingerprint"]
        or entrypoint != engine_input["entrypoint"]
        or content_digest(source) != strategy_binding.get("strategy_source_digest")
        or manifest.fingerprint != strategy_binding.get("strategy_manifest_fingerprint")
        or manifest.strategy.fingerprint != strategy_binding.get("strategy_fingerprint")
        or entrypoint != strategy_binding.get("entrypoint")
        or max_intents != strategy_binding.get("max_intents_per_event")
    ):
        raise NautilusRuntimeDataError(
            "primary strategy invocation differs from its authenticated engine binding"
        )

    manifests_by_component: dict[str, Any] = {}
    declared_instruments: set[str] = set()
    if component_context_stream:
        for component_id, component_binding in component_context_bindings.items():
            manifests_by_component[component_id] = component_binding.manifest
    else:
        only_component_id = min(strategy_bindings)
        manifests_by_component[only_component_id] = manifest
    for component_id, component in portfolio_components.items():
        component_manifest = manifests_by_component.get(component_id)
        component_binding = strategy_bindings[component_id]
        if (
            component_manifest is None
            or component_binding.get("component_id") != component_id
            or component_binding.get("strategy_fingerprint") != component.strategy_fingerprint
            or component_manifest.strategy.fingerprint != component.strategy_fingerprint
            or component_manifest.fingerprint
            != component_binding.get("strategy_manifest_fingerprint")
        ):
            raise NautilusRuntimeDataError(
                "component strategy manifest differs from its authenticated portfolio binding"
            )
        component_instruments = {
            requirement.instrument_id for requirement in component_manifest.capability_requirements
        }
        if component_instruments != set(component.instrument_ids):
            raise NautilusRuntimeDataError(
                "portfolio component scope differs from its strategy manifest"
            )
        if not component_instruments.issubset(instrument_by_id):
            raise NautilusRuntimeDataError(
                "strategy manifest instrument ids must match the native instrument catalog"
            )
        declared_instruments.update(component_instruments)

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
        if (
            sum(1 for _trigger in _iter_context_trigger_indexes(batch_contexts, ordered_records))
            != expected_contexts
        ):
            raise NautilusRuntimeDataError("strategy context count differs from its native tape")
        context_triggers = _iter_context_trigger_indexes(batch_contexts, ordered_records)
        only_component_id = min(strategy_bindings)
        context_trigger_groups = iter_component_context_trigger_groups(
            {only_component_id: context_triggers},
            component_priorities,
        )
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

    native_event_callback_iterator = (
        iter_native_event_records()
        if invocation_context_stream is not None
        else iter(event_definitions)
    )
    next_native_event_record = next(native_event_callback_iterator, None)

    def take_native_event_record() -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
        nonlocal next_native_event_record
        current = next_native_event_record
        if current is None:
            if forward_event_records:
                current = forward_event_records.popleft()
                return current, forward_event_records[0] if forward_event_records else None
            return None, None
        if not isinstance(current, Mapping):
            raise NautilusRuntimeDataError("native event record is invalid")
        next_native_event_record = next(native_event_callback_iterator, None)
        following = next_native_event_record
        if following is not None and not isinstance(following, Mapping):
            raise NautilusRuntimeDataError("native event lookahead record is invalid")
        return current, following

    component_trigger_stream = context_trigger_groups
    current_trigger = next(component_trigger_stream, None)
    callback_index = 0
    native_callback_event_id: str | None = None
    forward_event_records: deque[Mapping[str, Any]] = deque()
    forward_context_groups: dict[int, tuple[ComponentContextTrigger, ...]] = {}
    fill_ledger = NautilusComponentFillLedger(portfolio)
    pending_forward_account_event: _PendingForwardAccountEvent | None = None
    forward_orders_by_client_id: dict[str, ShadowOrder] = {}

    def stage_forward_event(
        event_record: Mapping[str, Any],
        component_contexts: Mapping[str, StrategyContext],
        *,
        instance_id: str,
        canonical_event: CanonicalForwardEvent,
        native_init_time_ns: int,
    ) -> None:
        """Queue exactly one authenticated event/context group before engine input."""

        nonlocal expected_contexts, expected_event_count, pending_forward_account_event
        if not allow_forward_event_staging:
            raise NautilusRuntimeDataError("native bridge does not allow forward event staging")
        if not isinstance(event_record, Mapping) or not isinstance(component_contexts, Mapping):
            raise NautilusRuntimeDataError("forward event or context input is invalid")
        if not isinstance(instance_id, str) or not instance_id.strip():
            raise NautilusRuntimeDataError("forward event instance id is invalid")
        if not isinstance(canonical_event, CanonicalForwardEvent):
            raise NautilusRuntimeDataError("forward event canonical identity is invalid")
        if not isinstance(native_init_time_ns, int) or isinstance(native_init_time_ns, bool):
            raise NautilusRuntimeDataError("forward native init time must be an integer")
        if (
            next_native_event_record is not None
            or current_trigger is not None
            or callback_index != expected_event_count
            or invocation_result_count != expected_contexts
        ):
            raise NautilusRuntimeDataError(
                "forward events can only be staged after the immutable replay prefix"
            )
        if forward_event_records or forward_context_groups or pending_forward_account_event:
            raise NautilusRuntimeDataError("a forward event is already staged")
        if set(component_contexts) - set(strategy_bindings):
            raise NautilusRuntimeDataError(
                "forward context contains an unauthenticated portfolio component"
            )
        for component_id, context in component_contexts.items():
            if not isinstance(context, StrategyContext):
                raise NautilusRuntimeDataError(
                    "forward context contains an invalid strategy context"
                )
            binding = strategy_bindings[component_id]
            if content_digest(context.parameters) != binding.get("parameters_digest"):
                raise NautilusRuntimeDataError(
                    "forward strategy context parameters differ from component binding"
                )
            if context.random_seed != engine_input["random_seed"]:
                raise NautilusRuntimeDataError(
                    "forward strategy context seed differs from component binding"
                )
        event = dict(event_record)
        event["native_init_time_ns"] = native_init_time_ns
        if not isinstance(event.get("event_type"), str) or not isinstance(
            event.get("instrument_id"), str
        ):
            raise NautilusRuntimeDataError("forward event identity fields are invalid")
        event_time_ns = event.get("event_time_ns")
        if not isinstance(event_time_ns, int) or isinstance(event_time_ns, bool):
            raise NautilusRuntimeDataError("forward event time is invalid")
        event_sequence = event.get("sequence")
        if not isinstance(event_sequence, int) or isinstance(event_sequence, bool):
            raise NautilusRuntimeDataError("forward event sequence is invalid")
        if (
            event.get("event_id") != canonical_event.event_id
            or event_sequence != canonical_event.sequence
            or _datetime_from_unix_nanos(event_time_ns) != canonical_event.event_time
        ):
            raise NautilusRuntimeDataError(
                "forward native event differs from its canonical platform identity"
            )
        ordered_contexts = tuple(
            (component_id, context)
            for component_id, context in sorted(
                component_contexts.items(),
                key=lambda item: (component_priorities.get(item[0], 0), item[0]),
            )
        )
        groups = tuple(
            _iter_stream_component_context_trigger_groups(
                ordered_contexts,
                (event,),
                component_context_bindings,
                component_priorities,
            )
        )
        if len(groups) > 1:
            raise NautilusRuntimeDataError(
                "one forward event produced multiple component callback groups"
            )
        contexts = () if not groups else groups[0].contexts
        native_account = strategy.portfolio.account(venue=native_venue_id)
        if native_account is None:
            raise NautilusRuntimeDataError("native portfolio has no account for its venue")
        pending_forward_account_event = _PendingForwardAccountEvent(
            instance_id=instance_id,
            canonical_event=canonical_event,
            callback_index=callback_index,
            cash_before=_native_cash_balances(native_account),
            orders=[],
            fills=[],
        )
        forward_event_records.append(event)
        forward_context_groups[callback_index] = contexts
        expected_event_count += 1
        expected_contexts += len(contexts)

    invocation_sessions = {
        component_id: StrategyInvocationSession(
            component_binding.source,
            manifest=component_binding.manifest,
            entrypoint=component_binding.entrypoint,
            max_intents_per_event=component_binding.max_intents_per_event,
        )
        for component_id, component_binding in component_context_bindings.items()
    }
    if not invocation_sessions:
        only_component_id = min(strategy_bindings)
        invocation_sessions[only_component_id] = StrategyInvocationSession(
            source,
            manifest=manifest,
            entrypoint=entrypoint,
            max_intents_per_event=max_intents,
        )
    invocation_results: list[Any] | None = (
        [] if result_stream_writer is None and retain_invocation_results else None
    )
    invocation_result_count = 0
    callback_failure_types: list[str] = []
    rebalance_run_failed = False
    rebalance_cursor = (
        NautilusRebalanceScheduleCursor(rebalance_plan) if rebalance_plan is not None else None
    )
    rebalance_schedule_evidence: list[dict[str, object]] = []
    rebalance_targets_by_component: dict[str, dict[str, TargetPositionIntent]] = {
        component_id: {} for component_id in portfolio_components
    }
    rebalance_sequences = (
        {}
        if rebalance_plan is None
        else {
            occurrence.occurrence_id: index
            for index, occurrence in enumerate(rebalance_plan.occurrences)
        }
    )

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
    latest_margin_prices: dict[str, tuple[Decimal, int]] = {}

    def native_account_quantities(account: Any) -> dict[str, Decimal]:
        quantities: dict[str, Decimal] = {}
        for instrument_id in declared_instruments:
            native_quantity = account.net_position(InstrumentId.from_str(instrument_id))
            quantity = (
                Decimal(0)
                if native_quantity is None
                else _native_decimal(native_quantity, "position quantity")
            )
            if quantity:
                quantities[instrument_id] = quantity
        return quantities

    def native_risk_state(
        strategy: Any,
        *,
        event_time: datetime,
        required_mark_ids: Sequence[str],
        allow_asof_marks: bool = False,
        include_margin_state: bool = True,
    ) -> dict[str, Any]:
        account_type = str(venue_definition["account_type"]).upper()
        if account_type not in {"CASH", "MARGIN"}:
            raise NautilusRuntimeDataError(
                "native order-risk routing requires a supported cash or margin account"
            )
        account_quantities = native_account_quantities(strategy.portfolio)
        fill_ledger.reconcile(account_quantities)
        marks: dict[str, Decimal] = {}
        component_quantities: dict[str, dict[str, Decimal]] = {
            component_id: {
                sdk_instrument_id: fill_ledger.quantity(component_id, sdk_instrument_id)
                for sdk_instrument_id in component.instrument_ids
            }
            for component_id, component in portfolio_components.items()
        }
        component_exposures: dict[str, dict[str, Decimal]] = {
            component_id: {} for component_id in portfolio_components
        }
        required_ids = set(required_mark_ids)

        def mark_is_usable(mark_entry: tuple[Decimal, int] | None) -> bool:
            if mark_entry is None:
                return False
            if allow_asof_marks:
                return mark_entry[1] <= _datetime_microsecond_ns(event_time)
            return _record_time_bucket(mark_entry[1]) == _datetime_microsecond_bucket(event_time)

        for sdk_instrument_id in declared_instruments:
            definition = instrument_by_id[sdk_instrument_id]
            native_id = InstrumentId.from_str(sdk_instrument_id)
            total_quantity = account_quantities.get(sdk_instrument_id, Decimal(0))
            component_quantities_for_instrument = {
                component_id: values[sdk_instrument_id]
                for component_id, values in component_quantities.items()
                if sdk_instrument_id in values
            }
            if total_quantity == 0 and not any(component_quantities_for_instrument.values()):
                if sdk_instrument_id in required_ids:
                    mark_entry = latest_marks.get(sdk_instrument_id)
                    if not mark_is_usable(mark_entry):
                        raise NautilusRuntimeDataError(
                            "native orders require an event-aligned or prior valuation mark"
                        )
                    assert mark_entry is not None
                    marks[sdk_instrument_id] = mark_entry[0]
                continue
            mark_entry = latest_marks.get(sdk_instrument_id)
            if not mark_is_usable(mark_entry):
                raise NautilusRuntimeDataError(
                    "open component holdings require event-aligned or prior native marks"
                )
            assert mark_entry is not None
            mark = mark_entry[0]
            marks[sdk_instrument_id] = mark
            if total_quantity:
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
                native_signed_exposure = exposure_amount if total_quantity > 0 else -exposure_amount
                exposure_per_unit = exposure_amount / abs(total_quantity)
            else:
                native_signed_exposure = Decimal(0)
                exposure_per_unit = mark
            nonzero_components = [
                (component_id, quantity)
                for component_id, quantity in component_quantities_for_instrument.items()
                if quantity
            ]
            attributed_so_far = Decimal(0)
            for index, (component_id, quantity) in enumerate(nonzero_components):
                if index == len(nonzero_components) - 1:
                    component_exposure = native_signed_exposure - attributed_so_far
                else:
                    component_exposure = quantity * exposure_per_unit
                    attributed_so_far += component_exposure
                component_exposures[component_id][sdk_instrument_id] = component_exposure
            attributed_exposure = sum(
                (
                    component_exposures[component_id].get(sdk_instrument_id, Decimal(0))
                    for component_id in component_exposures
                ),
                Decimal(0),
            )
            if attributed_exposure != native_signed_exposure:
                raise NautilusRuntimeDataError(
                    "component exposure attribution differs from native account valuation"
                )
        quantities = {
            instrument_id: quantity
            for instrument_id, quantity in account_quantities.items()
            if quantity != 0
        }
        exposures = {
            instrument_id: sum(
                (values.get(instrument_id, Decimal(0)) for values in component_exposures.values()),
                Decimal(0),
            )
            for instrument_id in declared_instruments
        }
        exposures = {instrument_id: value for instrument_id, value in exposures.items() if value}

        native_account = strategy.portfolio.account(venue=native_venue_id)
        if native_account is None:
            raise NautilusRuntimeDataError("native portfolio has no account for its venue")
        account_base = getattr(native_account, "base_currency", None)
        if getattr(account_base, "code", str(account_base)) != portfolio.base_currency:
            raise NautilusRuntimeDataError("native account base currency differs")
        is_margin_account = getattr(native_account, "is_margin_account", None)
        if not callable(is_margin_account) or bool(is_margin_account()) != (
            account_type == "MARGIN"
        ):
            raise NautilusRuntimeDataError("native account type differs from its venue definition")
        native_margin_instruments: dict[str, Any] = {}
        margin_prices: dict[str, Decimal] = {}
        if account_type == "MARGIN" and include_margin_state:
            cache = getattr(strategy, "cache", None)
            get_instrument = getattr(cache, "instrument", None)
            for sdk_instrument_id in declared_instruments:
                definition = instrument_by_id[sdk_instrument_id]
                if definition.get("product_class") != "future":
                    continue
                quantity = account_quantities.get(sdk_instrument_id, Decimal(0))
                if not quantity and sdk_instrument_id not in required_ids:
                    continue
                margin_entry = latest_margin_prices.get(sdk_instrument_id)
                if not mark_is_usable(margin_entry):
                    raise NautilusRuntimeDataError(
                        "native futures orders require an event-aligned margin price"
                    )
                assert margin_entry is not None
                margin_prices[sdk_instrument_id] = margin_entry[0]
                if not callable(get_instrument):
                    raise NautilusRuntimeDataError("native strategy cache has no instrument lookup")
                native_instrument = get_instrument(InstrumentId.from_str(sdk_instrument_id))
                if native_instrument is None:
                    raise NautilusRuntimeDataError(
                        "native strategy cache omitted a declared futures contract"
                    )
                native_margin_instruments[sdk_instrument_id] = native_instrument
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
            "current_component_exposures": component_exposures,
            "current_component_quantities": component_quantities,
            "account_type": account_type,
            "margin_prices": margin_prices,
            "native_margin_account": (native_account if account_type == "MARGIN" else None),
            "native_instruments": native_margin_instruments,
        }

    class _InvocationStrategyConfig(StrategyConfig):
        def __new__(cls) -> Any:
            strategy_id = StrategyId(f"SL2-{content_digest(engine_input)[-8:]}")
            return StrategyConfig.__new__(cls, strategy_id)

    class _InvocationStrategy(Strategy):
        def on_start(self) -> None:
            subscriptions: set[tuple[str, str]] = set()
            if native_event_stream is not None:
                for component_manifest in manifests_by_component.values():
                    subscriptions.update(
                        (dependency.requirement.event_type, dependency.requirement.instrument_id)
                        for dependency in component_manifest.data_dependencies
                    )
            else:
                subscriptions.update(
                    (record["event_type"], record["instrument_id"]) for record in event_definitions
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

        def on_order_filled(self, event: Any) -> None:
            try:
                client_order_id = str(event.client_order_id)
                order_remains_open = fill_ledger.record_fill(
                    client_order_id=client_order_id,
                    instrument_id=str(event.instrument_id),
                    quantity=_native_decimal(event.last_qty, "fill quantity"),
                )
                pending = pending_forward_account_event
                if pending is not None:
                    if pending.canonical_event.event_id != native_callback_event_id:
                        raise NautilusRuntimeDataError(
                            "native forward fill escaped its staged canonical event"
                        )
                    order = forward_orders_by_client_id.get(client_order_id)
                    if order is None:
                        raise NautilusRuntimeDataError(
                            "native forward fill has no captured shadow order"
                        )
                    commission = event.commission
                    currency = getattr(commission.currency, "code", str(commission.currency))
                    trade_id_value = getattr(event, "trade_id", None)
                    if not isinstance(trade_id_value, str) or not trade_id_value.strip():
                        raise NautilusRuntimeDataError("native forward fill omitted its trade id")
                    trade_id = trade_id_value
                    fill_id = content_digest(
                        {
                            "schema": "strategy-lab.nautilus-forward-fill.v1",
                            "instance_id": pending.instance_id,
                            "event_id": pending.canonical_event.event_id,
                            "trade_id": trade_id,
                        }
                    )
                    pending.fills.append(
                        ShadowFill(
                            fill_id=fill_id,
                            order_id=order.order_id,
                            quantity=_native_decimal(event.last_qty, "fill quantity"),
                            price=_native_decimal(event.last_px, "fill price"),
                            fee=_native_decimal(commission, "fill commission"),
                            fee_currency=currency,
                            filled_at=_datetime_from_unix_nanos(int(event.ts_event)),
                        )
                    )
                if not order_remains_open:
                    forward_orders_by_client_id.pop(client_order_id, None)
            except Exception as error:
                self._record_callback_failure(error)

        def on_order_canceled(self, event: Any) -> None:
            self._release_terminal_order(event)

        def on_order_expired(self, event: Any) -> None:
            self._release_terminal_order(event)

        def on_order_rejected(self, event: Any) -> None:
            self._release_terminal_order(event)

        def on_order_denied(self, event: Any) -> None:
            self._release_terminal_order(event)

        def _release_terminal_order(self, event: Any) -> None:
            try:
                client_order_id = str(event.client_order_id)
                fill_ledger.release_terminal_order(client_order_id)
                forward_orders_by_client_id.pop(client_order_id, None)
            except Exception as error:
                self._record_callback_failure(error)

        def _record_callback_failure(self, error: Exception) -> None:
            failure = f"{type(error).__module__}.{type(error).__qualname__}"
            if isinstance(error, NautilusRuntimeDataError):
                failure = f"{failure}: {error}"
            callback_failure_types.append(failure)

        def _record_rebalance_transition(
            self,
            transition: RebalanceBoundaryTransition,
            *,
            execution_status: str,
            submitted_order_count: int = 0,
        ) -> None:
            rebalance_schedule_evidence.append(
                {
                    "transition": transition.to_wire(),
                    "execution_status": execution_status,
                    "submitted_order_count": submitted_order_count,
                }
            )

        def _submit_order_resolution(self, order_resolution: Any | None) -> int:
            if order_resolution is None:
                return 0
            submitted_order_count = 0
            for component_id, intents in order_resolution.component_order_intents:
                for intent in intents:
                    if isinstance(intent, TargetPositionIntent):
                        raise NautilusRuntimeDataError("target-position conversion was incomplete")
                    if not isinstance(intent, OrderIntent):
                        raise NautilusRuntimeDataError(
                            "strategy emitted an unsupported typed intent"
                        )
                    definition = instrument_by_id[intent.instrument_id]
                    native_instrument_id = InstrumentId.from_str(intent.instrument_id)
                    native_side = NativeOrderSide.from_str(intent.side.value.upper())
                    native_quantity = Quantity(intent.quantity, definition["size_precision"])
                    native_tif = NativeTimeInForce.from_str(intent.time_in_force.value.upper())
                    component_tag = f"{NAUTILUS_COMPONENT_ORDER_TAG_PREFIX}{component_id}"
                    tag_values = [component_tag]
                    if intent.client_tag and intent.client_tag != component_tag:
                        tag_values.append(intent.client_tag)
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
                    client_order_id = getattr(order, "client_order_id", None)
                    if client_order_id is None:
                        raise NautilusRuntimeDataError(
                            "native order factory omitted its client order id"
                        )
                    fill_ledger.register_order(
                        client_order_id=str(client_order_id),
                        component_id=component_id,
                        instrument_id=intent.instrument_id,
                        side=intent.side,
                        quantity=intent.quantity,
                    )
                    pending = pending_forward_account_event
                    if pending is not None:
                        if pending.canonical_event.event_id != native_callback_event_id:
                            raise NautilusRuntimeDataError(
                                "native forward order escaped its staged canonical event"
                            )
                        client_id_value = str(client_order_id)
                        if client_id_value in forward_orders_by_client_id:
                            raise NautilusRuntimeDataError(
                                "native forward client order id was already captured"
                            )
                        order_id = content_digest(
                            {
                                "schema": "strategy-lab.nautilus-forward-order.v1",
                                "instance_id": pending.instance_id,
                                "event_id": pending.canonical_event.event_id,
                                "ordinal": len(pending.orders),
                                "component_id": component_id,
                                "intent": intent,
                            }
                        )
                        shadow_order = ShadowOrder(
                            order_id=order_id,
                            event_id=pending.canonical_event.event_id,
                            intent=intent,
                        )
                        pending.orders.append(shadow_order)
                        forward_orders_by_client_id[client_id_value] = shadow_order
                    self.submit_order(order)
                    submitted_order_count += 1
            return submitted_order_count

        def _apply_rebalance_transition(
            self,
            transition: RebalanceBoundaryTransition,
        ) -> None:
            nonlocal rebalance_run_failed
            if transition.action is RebalanceBoundaryAction.SKIP_MISFIRE:
                self._record_rebalance_transition(
                    transition,
                    execution_status="skipped_misfire",
                )
                return
            if transition.action is RebalanceBoundaryAction.FAIL_MISFIRE:
                rebalance_run_failed = True
                self._record_rebalance_transition(
                    transition,
                    execution_status="failed_misfire",
                )
                return

            if rebalance_cursor is None or rebalance_plan is None:
                raise NautilusRuntimeDataError("rebalance callback has no authenticated plan")
            if rebalance_run_failed:
                self._record_rebalance_transition(
                    transition,
                    execution_status="not_applied_run_aborted",
                )
                return
            occurrence = transition.occurrence
            intents_by_component = {
                component_id: tuple(targets.values())
                for component_id, targets in rebalance_targets_by_component.items()
                if targets
            }
            if not intents_by_component:
                self._record_rebalance_transition(
                    transition,
                    execution_status="applied_without_cached_targets",
                )
                return
            required_mark_ids = tuple(
                sorted(
                    {
                        intent.instrument_id
                        for intents in intents_by_component.values()
                        for intent in intents
                    }
                )
            )
            native_state = native_risk_state(
                self,
                event_time=occurrence.event_time,
                required_mark_ids=required_mark_ids,
                allow_asof_marks=True,
            )
            order_resolution = _route_component_callback_orders(
                portfolio=portfolio,
                raw_intents_by_component={},
                target_intents_by_component=intents_by_component,
                run_attempt_id=engine_input["attempt_id"],
                event_time=occurrence.event_time,
                event_sequence=rebalance_sequences[occurrence.occurrence_id],
                native_state=native_state,
                instruments=instrument_by_id,
            )
            submitted = self._submit_order_resolution(order_resolution)
            self._record_rebalance_transition(
                transition,
                execution_status=("orders_submitted" if submitted else "applied_without_orders"),
                submitted_order_count=submitted,
            )

        def _after_event_group(
            self,
            event_time_ns: int,
            following_record: Mapping[str, Any] | None,
        ) -> None:
            following_time_ns = (
                None if following_record is None else following_record.get("event_time_ns")
            )
            if following_time_ns == event_time_ns:
                return
            if following_time_ns is not None and (
                not isinstance(following_time_ns, int) or isinstance(following_time_ns, bool)
            ):
                raise NautilusRuntimeDataError("rebalance lookahead timestamp is invalid")
            if rebalance_cursor is not None:
                transitions = rebalance_cursor.after_event_group(
                    event_time_ns,
                    next_event_time_ns=following_time_ns,
                )
                for transition in transitions:
                    self._apply_rebalance_transition(transition)

            session = session_close_times.get(event_time_ns)
            if session is None or session_calendar is None:
                return
            if evaluation_window_bounds is None:
                return
            _input_start_ns, scoring_start_ns, scoring_end_ns = evaluation_window_bounds
            if not scoring_start_ns < event_time_ns < scoring_end_ns:
                return
            account = self.portfolio.account(venue=native_venue_id)
            if account is None:
                raise NautilusRuntimeDataError("native portfolio has no account for its venue")
            account_base = getattr(account, "base_currency", None)
            if getattr(account_base, "code", str(account_base)) != portfolio.base_currency:
                raise NautilusRuntimeDataError("native cash account base currency differs")
            if callback_index < 1:
                raise NautilusRuntimeDataError("session-close boundary has no native event index")
            session_close_equity_observations.append(
                NautilusSessionCloseEquityObservation(
                    session_label=session.session_label,
                    event_time_ns=event_time_ns,
                    event_index=callback_index - 1,
                    account_equity=_native_money_amount_for_currency(
                        self.portfolio.equity(venue=native_venue_id),
                        portfolio.base_currency,
                        "session-close account equity",
                    ),
                    account_cash_balance=_native_money_amount_for_currency(
                        account.balances_total(),
                        portfolio.base_currency,
                        "session-close account cash balance",
                    ),
                )
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
                if isinstance(error, NautilusRuntimeDataError | ValueError):
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
            nonlocal native_callback_event_id
            expected_record, following_record = take_native_event_record()
            if expected_record is None:
                raise NautilusRuntimeDataError("Nautilus emitted an unexpected extra event")
            native_callback_event_id = str(expected_record["event_id"])
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
            if evaluation_window_bounds is not None:
                lower_ns, _evaluation_start_ns, end_ns = evaluation_window_bounds
                if not lower_ns <= int(ts_event) < end_ns:
                    raise NautilusRuntimeDataError(
                        "Nautilus callback is outside the authenticated evaluation input window"
                    )
            if (
                native_event_stream is not None
                and int(ts_init) != expected_record["native_init_time_ns"]
            ):
                raise NautilusRuntimeDataError(
                    "Nautilus callback init order differs from the authenticated event stream "
                    f"for {expected_record['event_id']}: expected "
                    f"{expected_record['native_init_time_ns']}, observed {int(ts_init)}"
                )
            if rebalance_cursor is not None:
                for transition in rebalance_cursor.before_event(int(ts_event)):
                    self._apply_rebalance_transition(transition)
            fill_ledger.reconcile(native_account_quantities(self.portfolio))
            contexts: tuple[ComponentContextTrigger, ...] = ()
            if current_trigger is not None:
                if current_trigger.trigger_index < callback_index:
                    raise NautilusRuntimeDataError(
                        "Nautilus did not invoke the expected strategy context callback"
                    )
                if current_trigger.trigger_index == callback_index:
                    contexts = current_trigger.contexts
                    current_trigger = next(component_trigger_stream, None)
            elif allow_forward_event_staging:
                contexts = forward_context_groups.pop(callback_index, ())
            native_event_index = callback_index
            callback_index += 1
            latest_marks[str(instrument_id)] = (
                _native_event_mark_price(event_type, event),
                int(ts_event),
            )
            latest_margin_prices[str(instrument_id)] = (
                _native_event_margin_price(event_type, event),
                int(ts_event),
            )
            if account_equity_trace_writer is not None:
                # This runs before strategy invocation/order routing. Therefore
                # the first in-window mark is the OOS opening valuation, not a
                # warm-up-contaminated comparison against initial portfolio cash.
                native_account = self.portfolio.account(venue=native_venue_id)
                if native_account is None:
                    raise NautilusRuntimeDataError("native portfolio has no account for its venue")
                account_base = getattr(native_account, "base_currency", None)
                if getattr(account_base, "code", str(account_base)) != portfolio.base_currency:
                    raise NautilusRuntimeDataError("native cash account base currency differs")
                gross_base_exposure: Decimal | None = None
                signed_net_base_exposure: Decimal | None = None
                try:
                    exposure_state = native_risk_state(
                        self,
                        event_time=_datetime_from_unix_nanos(int(ts_event)),
                        required_mark_ids=(),
                        allow_asof_marks=True,
                        include_margin_state=False,
                    )
                except NautilusRuntimeDataError as error:
                    if str(error) not in {
                        "open component holdings require event-aligned or prior native marks",
                        "native portfolio could not value an open holding for allocation",
                    }:
                        raise
                else:
                    base_exposures = tuple(exposure_state["current_base_exposures"].values())
                    gross_base_exposure = sum((abs(value) for value in base_exposures), Decimal(0))
                    signed_net_base_exposure = sum(base_exposures, Decimal(0))
                account_equity_trace_writer.write(
                    event_id=expected_record["event_id"],
                    event_time_ns=int(ts_event),
                    event_index=native_event_index,
                    source_sequence=expected_record["sequence"],
                    account_equity=_native_money_amount_for_currency(
                        self.portfolio.equity(venue=native_venue_id),
                        portfolio.base_currency,
                        "account equity",
                    ),
                    account_cash_balance=_native_money_amount_for_currency(
                        native_account.balances_total(),
                        portfolio.base_currency,
                        "account cash balance",
                    ),
                    gross_base_exposure=gross_base_exposure,
                    signed_net_base_exposure=signed_net_base_exposure,
                )
            if not contexts:
                self._after_event_group(int(ts_event), following_record)
                return
            callback_results: list[tuple[str, Any]] = []
            raw_intents_by_component: dict[str, tuple[Any, ...]] = {}
            target_intents_by_component: dict[str, tuple[Any, ...]] = {}
            for trigger in contexts:
                component_id = trigger.component_id
                context = trigger.context
                strategy_binding_for_component = strategy_bindings[component_id]
                component_manifest = manifests_by_component[component_id]
                if content_digest(context.parameters) != strategy_binding_for_component.get(
                    "parameters_digest"
                ):
                    raise NautilusRuntimeDataError(
                        "strategy context parameters differ from component binding"
                    )
                if context.random_seed != engine_input["random_seed"]:
                    raise NautilusRuntimeDataError(
                        "strategy context seed differs from engine input"
                    )
                positions: dict[str, Any] = {}
                for requirement in component_manifest.capability_requirements:
                    sdk_instrument_id = requirement.instrument_id
                    quantity = fill_ledger.quantity(component_id, sdk_instrument_id)
                    positions[sdk_instrument_id] = PositionSnapshot(
                        instrument_id=sdk_instrument_id,
                        quantity=quantity,
                        average_price=None,
                        market_value=None,
                    )
                result = invocation_sessions[component_id].invoke(
                    replace(context, positions=positions)
                )
                if rebalance_cursor is not None:
                    if result.status is not InvocationStatus.SUCCEEDED:
                        raise NautilusRuntimeDataError(
                            "calendar rebalance strategy invocation did not succeed"
                        )
                    if any(not isinstance(item, TargetPositionIntent) for item in result.intents):
                        raise NautilusRuntimeDataError(
                            "calendar rebalance policies support target-position intents only"
                        )
                    instrument_ids = [item.instrument_id for item in result.intents]
                    if len(instrument_ids) != len(set(instrument_ids)):
                        raise NautilusRuntimeDataError(
                            "strategy repeated a target instrument in one rebalance callback"
                        )
                # Warm-up advances strategy-local state, but neither native orders nor
                # strategy-output artifacts may treat those intents as OOS decisions.
                result = _suppress_warmup_intents(
                    result,
                    int(ts_event),
                    evaluation_window_bounds,
                )
                if rebalance_cursor is not None and not rebalance_run_failed:
                    for intent in result.intents:
                        if not isinstance(intent, TargetPositionIntent):
                            raise NautilusRuntimeDataError(
                                "calendar rebalance policy emitted an unsupported intent"
                            )
                        rebalance_targets_by_component[component_id][intent.instrument_id] = intent
                callback_results.append((component_id, result))
                if result_stream_writer is None:
                    if invocation_results is not None:
                        invocation_results.append(result)
                else:
                    result_stream_writer.write(result)
                invocation_result_count += 1
                if result.status is InvocationStatus.SUCCEEDED and result.intents:
                    target_intents = tuple(
                        intent
                        for intent in result.intents
                        if isinstance(intent, TargetPositionIntent)
                    )
                    if target_intents:
                        if len(target_intents) != len(result.intents):
                            raise NautilusRuntimeDataError(
                                "target-position and raw order intents cannot be mixed"
                                " for one component callback"
                            )
                        target_intents_by_component[component_id] = target_intents
                    else:
                        raw_intents = tuple(
                            intent for intent in result.intents if isinstance(intent, OrderIntent)
                        )
                        if len(raw_intents) != len(result.intents):
                            raise NautilusRuntimeDataError(
                                "strategy emitted an unsupported typed intent"
                            )
                        raw_intents_by_component[component_id] = raw_intents
            if any(
                result.status is not InvocationStatus.SUCCEEDED
                for _component_id, result in callback_results
            ):
                return
            if rebalance_cursor is not None:
                self._after_event_group(int(ts_event), following_record)
                return
            if not raw_intents_by_component and not target_intents_by_component:
                self._after_event_group(int(ts_event), following_record)
                return

            event_time = contexts[0].context.event_time
            event_sequence = max(trigger.context.event_sequence for trigger in contexts)
            required_mark_ids = tuple(
                intent.instrument_id
                for intents in (
                    *raw_intents_by_component.values(),
                    *target_intents_by_component.values(),
                )
                for intent in intents
            )
            native_state = native_risk_state(
                self,
                event_time=event_time,
                required_mark_ids=required_mark_ids,
            )
            if target_intents_by_component:
                assert isinstance(venue_definition, Mapping)
                _validate_target_account_product_scope(
                    account_type=venue_definition["account_type"],
                    target_intents_by_component=target_intents_by_component,
                    instruments=instrument_by_id,
                )
            order_resolution = _route_component_callback_orders(
                portfolio=portfolio,
                raw_intents_by_component=raw_intents_by_component,
                target_intents_by_component=target_intents_by_component,
                run_attempt_id=engine_input["attempt_id"],
                event_time=event_time,
                event_sequence=event_sequence,
                native_state=native_state,
                instruments=instrument_by_id,
            )
            self._submit_order_resolution(order_resolution)
            self._after_event_group(int(ts_event), following_record)

    strategy = _InvocationStrategy(_InvocationStrategyConfig())

    def result_output() -> Any:
        if rebalance_cursor is not None:
            for transition in rebalance_cursor.finish():
                strategy._apply_rebalance_transition(transition)
        if callback_failure_types:
            failure_types = ",".join(sorted(set(callback_failure_types)))
            raise NautilusRuntimeDataError(f"native strategy callback failed with {failure_types}")
        fill_ledger.reconcile(native_account_quantities(strategy.portfolio))
        if callback_index != expected_event_count:
            raise NautilusRuntimeDataError(
                "Nautilus did not invoke every event in the authenticated event tape"
            )
        if next_native_event_record is not None:
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
        if invocation_results is None:
            return None
        assert invocation_results is not None
        return serialize_invocation_batch_result(invocation_results)

    def take_forward_account_event() -> ForwardAccountEvent:
        nonlocal pending_forward_account_event
        pending = pending_forward_account_event
        if pending is None:
            raise NautilusRuntimeDataError("no staged forward account event is available")
        if (
            callback_index != pending.callback_index + 1
            or native_callback_event_id != pending.canonical_event.event_id
        ):
            raise NautilusRuntimeDataError(
                "Nautilus did not process the staged canonical event exactly once"
            )
        native_account = strategy.portfolio.account(venue=native_venue_id)
        if native_account is None:
            raise NautilusRuntimeDataError("native portfolio has no account for its venue")
        cash_after = _native_cash_balances(native_account)
        cash_deltas = {
            currency: cash_after.get(currency, Decimal(0))
            - pending.cash_before.get(currency, Decimal(0))
            for currency in sorted(set(pending.cash_before) | set(cash_after))
        }
        event = ForwardAccountEvent(
            instance_id=pending.instance_id,
            event_id=pending.canonical_event.event_id,
            event_fingerprint=content_digest(pending.canonical_event),
            sequence=pending.canonical_event.sequence,
            event_time=pending.canonical_event.event_time,
            orders=tuple(pending.orders),
            fills=tuple(pending.fills),
            cash_deltas={currency: delta for currency, delta in cash_deltas.items() if delta},
        )
        pending_forward_account_event = None
        return event

    def account_equity_trace_output() -> Any:
        if account_equity_trace_writer is None:
            return None
        return account_equity_trace_writer.finish()

    def session_close_equity_output() -> tuple[NautilusSessionCloseEquityObservation, ...]:
        return tuple(session_close_equity_observations)

    def rebalance_schedule_output() -> list[dict[str, object]]:
        return list(rebalance_schedule_evidence)

    return NativeStrategyBridge(
        strategy=strategy,
        result_output=result_output,
        account_equity_trace_output=account_equity_trace_output,
        session_close_equity_output=session_close_equity_output,
        rebalance_schedule_output=rebalance_schedule_output,
        stage_forward_event=stage_forward_event,
        take_forward_account_event=take_forward_account_event,
        input_fingerprint=input_fingerprint,
        input_protocol=input_protocol,
    )


__all__ = ["NativeStrategyBridge", "build_native_strategy_bridge"]
