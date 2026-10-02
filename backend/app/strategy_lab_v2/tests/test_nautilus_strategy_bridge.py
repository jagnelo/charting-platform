from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.nautilus_runtime_data import NautilusRuntimeDataError
from app.strategy_lab_v2.nautilus_strategy_bridge import (
    _iter_context_trigger_indexes,
    _match_contexts_to_events,
)
from app.strategy_lab_v2.sdk import MarketEvent, StrategyContext

EVENT_TIME = datetime(2024, 1, 1, tzinfo=UTC)
EVENT_TIME_NS = 1_704_067_200_000_000_000


def _event(
    event_id: str,
    dependency_id: str,
    instrument_id: str,
    sequence: int,
    event_time: datetime = EVENT_TIME,
) -> MarketEvent:
    return MarketEvent(
        dependency_id,
        event_id,
        instrument_id,
        event_time,
        sequence,
        {"close": sequence},
    )


def _record(event: MarketEvent) -> dict[str, object]:
    return {
        "dependency_id": event.dependency_id,
        "event_id": event.event_id,
        "instrument_id": event.instrument_id,
        "event_type": "ohlcv",
        "event_time_ns": int(event.event_time.timestamp()) * 1_000_000_000,
        "sequence": event.sequence,
    }


def _context(
    sequence: int,
    events: dict[str, tuple[MarketEvent, ...]],
    event_time: datetime = EVENT_TIME,
) -> StrategyContext:
    return StrategyContext(
        event_time=event_time,
        event_sequence=sequence,
        random_seed=7,
        parameters={},
        market_events=events,
    )


def test_same_time_batch_context_runs_once_on_last_native_event() -> None:
    first = _event("event-1", "prices-a", "US.AAPL", 1)
    second = _event("event-2", "prices-b", "US.MSFT", 2)
    context = _context(2, {"prices-a": (first,), "prices-b": (second,)})

    matched = _match_contexts_to_events((context,), (_record(first), _record(second)))

    assert matched == {"event-2": context}


def test_legacy_one_context_per_event_batch_remains_supported() -> None:
    first = _event("event-1", "prices-a", "US.AAPL", 1)
    second = _event("event-2", "prices-b", "US.MSFT", 2)
    first_context = _context(1, {"prices-a": (first,)})
    second_context = _context(2, {"prices-a": (first,), "prices-b": (second,)})

    matched = _match_contexts_to_events(
        (first_context, second_context),
        (_record(first), _record(second)),
    )

    assert matched == {"event-1": first_context, "event-2": second_context}


def test_batched_context_must_include_all_events_at_its_timestamp() -> None:
    first = _event("event-1", "prices-a", "US.AAPL", 1)
    second = _event("event-2", "prices-b", "US.MSFT", 2)
    incomplete_context = _context(2, {"prices-a": (first,)})

    with pytest.raises(NautilusRuntimeDataError, match="every same-time native event"):
        _match_contexts_to_events(
            (incomplete_context,),
            (_record(first), _record(second)),
        )


def test_event_time_binding_uses_sdk_microsecond_precision_for_modern_dates() -> None:
    event = _event("event-1", "prices-a", "US.AAPL", 1)
    context = _context(1, {"prices-a": (event,)})

    matched = _match_contexts_to_events((context,), (_record(event),))

    assert matched == {"event-1": context}


def test_stream_trigger_indexes_bind_batches_to_the_last_same_time_callback() -> None:
    first = _event("event-1", "prices-a", "US.AAPL", 1)
    second = _event("event-2", "prices-b", "US.MSFT", 2)
    context = _context(2, {"prices-a": (first,), "prices-b": (second,)})

    assert list(_iter_context_trigger_indexes((context,), (_record(first), _record(second)))) == [
        (1, context)
    ]


def test_stream_trigger_indexes_bind_per_event_contexts_to_native_order() -> None:
    first = _event("event-1", "prices-a", "US.AAPL", 1)
    second = _event("event-2", "prices-b", "US.MSFT", 2)
    first_context = _context(1, {"prices-a": (first,)})
    second_context = _context(2, {"prices-a": (first,), "prices-b": (second,)})

    assert list(
        _iter_context_trigger_indexes(
            (first_context, second_context), (_record(first), _record(second))
        )
    ) == [(0, first_context), (1, second_context)]


def test_stream_trigger_indexes_reject_incomplete_same_time_coverage() -> None:
    first = _event("event-1", "prices-a", "US.AAPL", 1)
    second = _event("event-2", "prices-b", "US.MSFT", 2)
    incomplete_context = _context(2, {"prices-a": (first,)})

    with pytest.raises(NautilusRuntimeDataError, match="every same-time native event"):
        list(
            _iter_context_trigger_indexes((incomplete_context,), (_record(first), _record(second)))
        )


def test_stream_trigger_indexes_reject_noncanonical_native_order() -> None:
    first = _event("event-1", "prices-a", "US.AAPL", 1)
    second = _event("event-2", "prices-b", "US.MSFT", 2)
    contexts = (
        _context(1, {"prices-a": (first,)}),
        _context(2, {"prices-a": (first,), "prices-b": (second,)}),
    )

    with pytest.raises(NautilusRuntimeDataError, match="canonical event order"):
        list(_iter_context_trigger_indexes(contexts, (_record(second), _record(first))))


def test_stream_trigger_indexes_consume_only_one_time_group_plus_lookahead() -> None:
    events = tuple(
        _event(
            f"event-{index}",
            f"prices-{index}",
            f"US.TEST{index}",
            index,
            EVENT_TIME + timedelta(seconds=index - 1),
        )
        for index in range(1, 4)
    )
    consumed: list[int] = []

    def contexts():
        for index, event in enumerate(events, start=1):
            consumed.append(index)
            yield _context(index, {event.dependency_id: (event,)}, event.event_time)

    triggers = _iter_context_trigger_indexes(contexts(), tuple(_record(event) for event in events))
    first_trigger_index, first_trigger_context = next(triggers)
    assert first_trigger_index == 0
    assert first_trigger_context.event_sequence == 1
    assert len(consumed) <= 2
    second_trigger_index, _second_trigger_context = next(triggers)
    assert second_trigger_index == 1
    assert len(consumed) <= 3
