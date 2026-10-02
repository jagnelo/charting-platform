from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.event_tape import FrozenEventTape
from app.strategy_lab_v2.nautilus_event_adapter import (
    NautilusEventRecord,
    NautilusEventTape,
    materialize_nautilus_event,
    materialize_nautilus_event_tape,
)
from app.strategy_lab_v2.sdk import MarketEvent
from app.strategy_lab_v2.tests.test_event_tape import _binding_inputs

BASE = datetime(2024, 1, 2, 14, 30, 0, 123456, tzinfo=UTC)


def _event(
    event_id: str = "bar-1",
    *,
    event_time: datetime = BASE,
    sequence: int = 4,
    values: dict[str, object] | None = None,
) -> MarketEvent:
    return MarketEvent(
        dependency_id="daily-bars",
        event_id=event_id,
        instrument_id="US.AAPL",
        event_time=event_time,
        sequence=sequence,
        values=values
        or {
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
            "volume": 1200,
        },
    )


def test_materialized_event_uses_exact_utc_nanoseconds_and_freezes_values() -> None:
    event = _event(event_time=BASE.astimezone(UTC) + timedelta(microseconds=7))

    record = materialize_nautilus_event(event, event_type="ohlcv")

    assert record.event_time_ns == 1_704_205_800_123_463_000
    assert record.values["close"] == 101.0
    with pytest.raises(TypeError):
        record.values["close"] = 99.0  # type: ignore[index]
    assert record.fingerprint.startswith("sha256:")


def test_event_tape_order_and_fingerprint_are_deterministic() -> None:
    first = materialize_nautilus_event(_event("bar-1", sequence=1), event_type="ohlcv")
    second = materialize_nautilus_event(
        _event("bar-2", event_time=BASE + timedelta(minutes=1), sequence=2),
        event_type="ohlcv",
    )
    source = content_digest("source-tape")

    tape = NautilusEventTape(source, (first, second))
    reversed_tape = NautilusEventTape(source, (second, first))

    assert tape.events == (first, second)
    assert tape.fingerprint == reversed_tape.fingerprint


def test_event_record_rejects_unsupported_type_and_missing_wire_fields() -> None:
    event = _event(values={"close": 100.0})

    with pytest.raises(ValueError, match="missing fields"):
        materialize_nautilus_event(event, event_type="ohlcv")
    with pytest.raises(ValueError, match="unsupported Nautilus event type"):
        materialize_nautilus_event(_event(), event_type="depth")


def test_event_tape_rejects_duplicate_ids_and_wrong_source_digest() -> None:
    record = materialize_nautilus_event(_event(), event_type="ohlcv")

    with pytest.raises(ValueError, match="event ids must be unique"):
        NautilusEventTape(content_digest("source"), (record, record))
    with pytest.raises(ValueError, match="source_tape_fingerprint"):
        NautilusEventTape("not-a-digest", (record,))


def test_materialize_event_tape_reuses_bound_snapshot_and_manifest_identity() -> None:
    source_tape, snapshot, manifest = _binding_inputs()
    dependency = manifest.data_dependencies[0]
    fields = ("close", "high", "low", "open", "volume")
    manifest = replace(manifest, data_dependencies=(replace(dependency, fields=fields),))
    events = tuple(
        replace(
            event,
            values={
                "close": event.values["close"],
                "high": event.values["close"],
                "low": event.values["close"],
                "open": event.values["close"],
                "volume": 1000,
            },
        )
        for event in source_tape.events
    )
    tape = FrozenEventTape(snapshot.fingerprint, events)

    materialized = materialize_nautilus_event_tape(tape, snapshot, manifest)

    assert materialized.source_tape_fingerprint == tape.fingerprint
    assert [event.event_id for event in materialized.events] == ["bar-1", "bar-2"]
    assert all(event.event_type == "ohlcv" for event in materialized.events)


def test_record_constructor_rejects_negative_wire_time() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        NautilusEventRecord(
            dependency_id="daily-bars",
            event_id="bar-1",
            instrument_id="US.AAPL",
            event_type="ohlcv",
            event_time_ns=-1,
            sequence=0,
            values={
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
                "volume": 1,
            },
        )
