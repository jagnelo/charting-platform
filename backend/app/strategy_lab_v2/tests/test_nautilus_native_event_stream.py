from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from io import BytesIO

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.nautilus_event_adapter import NautilusEventRecord
from app.strategy_lab_v2.nautilus_native_event_stream import (
    NautilusNativeEventStreamCursor,
    deserialize_nautilus_native_event_stream,
    serialize_nautilus_native_event_stream,
)


def _event(event_id: str, *, event_time_ns: int, sequence: int) -> NautilusEventRecord:
    return NautilusEventRecord(
        "quotes",
        event_id,
        "AAPL.SIM",
        "quote",
        event_time_ns,
        sequence,
        {
            "bid": Decimal("100.00"),
            "ask": Decimal("100.01"),
            "bid_size": Decimal("10"),
            "ask_size": Decimal("12"),
        },
    )


def _wire(events: tuple[NautilusEventRecord, ...]) -> bytes:
    output = BytesIO()
    serialize_nautilus_native_event_stream(
        output,
        events,
        source_tape_fingerprint=content_digest("source-tape"),
        adapter_version="strategy-lab.nautilus-event-adapter.v1",
        expected_event_count=len(events),
    )
    return output.getvalue()


def _decode(wire: bytes, *, count: int = 2):
    return tuple(
        deserialize_nautilus_native_event_stream(
            BytesIO(wire),
            expected_source_tape_fingerprint=content_digest("source-tape"),
            expected_adapter_version="strategy-lab.nautilus-event-adapter.v1",
            expected_event_count=count,
        )
    )


def _legacy_v1_wire() -> bytes:
    event = {
        "dependency_id": "quotes",
        "event_id": "event-1",
        "instrument_id": "AAPL.SIM",
        "event_type": "quote",
        "event_time_ns": 100,
        "sequence": 1,
        "values": {"bid": "100.00", "ask": "100.01"},
    }
    record = {
        "record_type": "event",
        "index": 0,
        "native_init_time_ns": 101,
        "event": event,
    }

    def encode(value: object) -> bytes:
        return (json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n").encode()

    record_wire = encode(record)
    header = {
        "protocol_version": "strategy-lab.nautilus.native-event-stream.v1",
        "record_type": "header",
        "source_tape_fingerprint": content_digest("source-tape"),
        "adapter_version": "strategy-lab.nautilus-event-adapter.v1",
        "event_count": 1,
    }
    trailer = {
        "record_type": "trailer",
        "event_count": 1,
        "records_sha256": f"sha256:{hashlib.sha256(record_wire).hexdigest()}",
    }
    return encode(header) + record_wire + encode(trailer)


def test_native_event_stream_is_reproducible_and_preserves_same_time_order() -> None:
    events = (
        _event("event-1", event_time_ns=100, sequence=1),
        _event("event-2", event_time_ns=100, sequence=2),
    )

    first = _wire(events)
    second = _wire(events)

    assert first == second
    observed = _decode(first)
    assert [event["event_id"] for event in observed] == ["event-1", "event-2"]
    assert [event["native_init_time_ns"] for event in observed] == [101, 102]
    assert [event["event_time_ns"] for event in observed] == [100, 100]
    assert observed[0]["values"]["bid"] == Decimal("100.00")
    assert observed[0]["values"]["ask_size"] == Decimal("12")


def test_native_event_stream_still_reads_legacy_v1_artifacts() -> None:
    observed = _decode(_legacy_v1_wire(), count=1)

    assert observed[0]["event_id"] == "event-1"
    assert observed[0]["values"] == {"bid": "100.00", "ask": "100.01"}


def test_native_event_stream_cursors_keep_independent_positions() -> None:
    events = (
        _event("event-1", event_time_ns=100, sequence=1),
        _event("event-2", event_time_ns=100, sequence=2),
    )
    source = BytesIO(_wire(events))
    cursor_a = NautilusNativeEventStreamCursor(source)
    cursor_b = NautilusNativeEventStreamCursor(source)
    iterator_a = deserialize_nautilus_native_event_stream(
        cursor_a,
        expected_source_tape_fingerprint=content_digest("source-tape"),
        expected_adapter_version="strategy-lab.nautilus-event-adapter.v1",
        expected_event_count=2,
    )
    iterator_b = deserialize_nautilus_native_event_stream(
        cursor_b,
        expected_source_tape_fingerprint=content_digest("source-tape"),
        expected_adapter_version="strategy-lab.nautilus-event-adapter.v1",
        expected_event_count=2,
    )

    assert next(iterator_a)["event_id"] == "event-1"
    assert next(iterator_b)["event_id"] == "event-1"
    assert next(iterator_a)["event_id"] == "event-2"
    assert next(iterator_b)["event_id"] == "event-2"
    with pytest.raises(StopIteration):
        next(iterator_a)
    with pytest.raises(StopIteration):
        next(iterator_b)


def test_native_event_stream_rejects_wrong_source_and_missing_trailer() -> None:
    wire = _wire(
        (
            _event("event-1", event_time_ns=100, sequence=1),
            _event("event-2", event_time_ns=100, sequence=2),
        )
    )

    with pytest.raises(ValueError, match="header differs"):
        tuple(
            deserialize_nautilus_native_event_stream(
                BytesIO(wire),
                expected_source_tape_fingerprint=content_digest("different"),
                expected_adapter_version="strategy-lab.nautilus-event-adapter.v1",
                expected_event_count=2,
            )
        )
    with pytest.raises(ValueError, match="trailer is missing"):
        _decode(wire.rsplit(b"{", 1)[0], count=2)


def test_native_event_stream_rejects_order_digest_and_trailing_drift() -> None:
    events = (
        _event("event-1", event_time_ns=100, sequence=1),
        _event("event-2", event_time_ns=100, sequence=2),
    )
    wire = _wire(events)

    with pytest.raises(ValueError, match="record digest differs"):
        _decode(wire.replace(b"100.00", b"100.02", 1))
    with pytest.raises(ValueError, match="trailing bytes"):
        _decode(wire + b"{}\n")
    with pytest.raises(ValueError, match="canonical event order"):
        _wire((events[1], events[0]))


def test_native_event_stream_enforces_count_row_and_total_bounds() -> None:
    events = (
        _event("event-1", event_time_ns=100, sequence=1),
        _event("event-2", event_time_ns=100, sequence=2),
    )
    with pytest.raises(ValueError, match="expected_event_count"):
        serialize_nautilus_native_event_stream(
            BytesIO(),
            events,
            source_tape_fingerprint=content_digest("source-tape"),
            adapter_version="strategy-lab.nautilus-event-adapter.v1",
            expected_event_count=3,
        )
    with pytest.raises(ValueError, match="byte bound"):
        serialize_nautilus_native_event_stream(
            BytesIO(),
            events,
            source_tape_fingerprint=content_digest("source-tape"),
            adapter_version="strategy-lab.nautilus-event-adapter.v1",
            expected_event_count=2,
            max_stream_bytes=32,
        )


def test_native_event_stream_rejects_duplicate_json_keys() -> None:
    with pytest.raises(ValueError, match="duplicate object fields"):
        _decode(
            b'{"protocol_version":"x","protocol_version":"y"}\n',
            count=2,
        )
