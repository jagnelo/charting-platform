from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.strategy_lab_v2.nautilus_runtime_data import NautilusRuntimeDataError
from app.strategy_lab_v2.nautilus_strategy_bridge import _match_contexts_to_events
from app.strategy_lab_v2.sdk import MarketEvent, StrategyContext

EVENT_TIME = datetime(2024, 1, 1, tzinfo=UTC)
EVENT_TIME_NS = 1_704_067_200_000_000_000


def _event(event_id: str, dependency_id: str, instrument_id: str, sequence: int) -> MarketEvent:
    return MarketEvent(
        dependency_id,
        event_id,
        instrument_id,
        EVENT_TIME,
        sequence,
        {"close": sequence},
    )


def _record(event: MarketEvent) -> dict[str, object]:
    return {
        "dependency_id": event.dependency_id,
        "event_id": event.event_id,
        "instrument_id": event.instrument_id,
        "event_type": "ohlcv",
        "event_time_ns": EVENT_TIME_NS,
        "sequence": event.sequence,
    }


def _context(sequence: int, events: dict[str, tuple[MarketEvent, ...]]) -> StrategyContext:
    return StrategyContext(
        event_time=EVENT_TIME,
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
