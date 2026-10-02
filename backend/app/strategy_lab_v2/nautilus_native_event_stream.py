"""Bounded NDJSON transport for authenticated Nautilus market-event inputs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, BinaryIO

from app.strategy_lab_v2.canonical import require_sha256_digest

NAUTILUS_NATIVE_EVENT_STREAM_PROTOCOL = "strategy-lab.nautilus.native-event-stream.v1"
MAX_NAUTILUS_NATIVE_EVENT_STREAM_BYTES = 1_099_511_627_776  # 1 TiB hard ceiling
MAX_NAUTILUS_NATIVE_EVENT_ROW_BYTES = 1_048_576
_EVENT_FIELDS = frozenset(
    {
        "dependency_id",
        "event_id",
        "instrument_id",
        "event_type",
        "event_time_ns",
        "sequence",
        "values",
    }
)
_EVENT_TYPES = frozenset({"ohlcv", "quote", "trade"})


@dataclass(frozen=True, slots=True)
class NautilusNativeEventStreamSummary:
    source_tape_fingerprint: str
    adapter_version: str
    event_count: int
    byte_length: int
    content_digest: str


def _wire_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("native event decimals must be finite")
        return str(value)
    if isinstance(value, Enum):
        return _wire_value(value.value)
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("native event mapping keys must be strings")
        return {key: _wire_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_wire_value(item) for item in value]
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("native event numbers must be finite")
        return value
    raise TypeError(f"unsupported native event value {type(value).__name__}")


def _dump(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            _wire_value(value),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("native event stream contains duplicate object fields")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError("native event stream contains a non-finite JSON number")


def _read_record(stream: BinaryIO) -> tuple[Mapping[str, Any], bytes] | None:
    line = stream.readline(MAX_NAUTILUS_NATIVE_EVENT_ROW_BYTES + 2)
    if not line:
        return None
    if len(line) > MAX_NAUTILUS_NATIVE_EVENT_ROW_BYTES + 1:
        raise ValueError("native event stream row exceeds its configured bound")
    if not line.endswith(b"\n"):
        raise ValueError("native event stream rows must end with a newline")
    decoded = json.loads(
        line,
        object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
    )
    if not isinstance(decoded, Mapping):
        raise ValueError("native event stream records must be JSON objects")
    return decoded, line


def _validate_event(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _EVENT_FIELDS:
        raise ValueError("native event stream event fields are invalid")
    for name in ("dependency_id", "event_id", "instrument_id"):
        if not isinstance(value[name], str) or not value[name].strip():
            raise ValueError(f"native event stream {name} must not be empty")
    if not isinstance(value["event_type"], str) or value["event_type"] not in _EVENT_TYPES:
        raise ValueError("native event stream event type is unsupported")
    for name in ("event_time_ns", "sequence"):
        item = value[name]
        if not isinstance(item, int) or isinstance(item, bool) or item < 0:
            raise ValueError(f"native event stream {name} must be a non-negative integer")
    if not isinstance(value["values"], Mapping) or any(
        not isinstance(key, str) for key in value["values"]
    ):
        raise ValueError("native event stream values must be a string-keyed object")
    return value


def _event_wire(event: Any) -> Mapping[str, Any]:
    try:
        value = {
            name: getattr(event, name)
            for name in (
                "dependency_id",
                "event_id",
                "instrument_id",
                "event_type",
                "event_time_ns",
                "sequence",
                "values",
            )
        }
    except AttributeError:
        if not isinstance(event, Mapping):
            raise TypeError("native event stream items must be event records or mappings") from None
        value = event
    return _validate_event(_wire_value(value))


def serialize_nautilus_native_event_stream(
    stream: BinaryIO,
    events: Iterable[Any],
    *,
    source_tape_fingerprint: str,
    adapter_version: str,
    expected_event_count: int,
    max_stream_bytes: int = MAX_NAUTILUS_NATIVE_EVENT_STREAM_BYTES,
) -> NautilusNativeEventStreamSummary:
    """Serialize verified records with deterministic callback and catalog order.

    ``native_init_time_ns`` is a monotonic tie-break timestamp derived from the
    authenticated canonical order. ``event_time_ns`` remains untouched as the
    market-event timestamp consumed by the SDK and matching engine.
    """

    require_sha256_digest(source_tape_fingerprint, field_name="source_tape_fingerprint")
    if not isinstance(adapter_version, str) or not adapter_version.strip():
        raise ValueError("adapter_version must not be empty")
    for name, value, minimum in (
        ("expected_event_count", expected_event_count, 1),
        ("max_stream_bytes", max_stream_bytes, 1),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            raise ValueError(f"{name} must be a positive integer")

    stream_digest = hashlib.sha256()
    records_digest = hashlib.sha256()
    byte_length = 0

    def write(record: Mapping[str, Any], *, record_digest: bool = False) -> None:
        nonlocal byte_length
        wire = _dump(record)
        if len(wire) > MAX_NAUTILUS_NATIVE_EVENT_ROW_BYTES + 1:
            raise ValueError("native event stream row exceeds its configured bound")
        if byte_length + len(wire) > max_stream_bytes:
            raise ValueError("native event stream exceeds its configured byte bound")
        written = stream.write(wire)
        if written is not None and written != len(wire):
            raise OSError("native event stream was only partially written")
        stream_digest.update(wire)
        if record_digest:
            records_digest.update(wire)
        byte_length += len(wire)

    write(
        {
            "protocol_version": NAUTILUS_NATIVE_EVENT_STREAM_PROTOCOL,
            "record_type": "header",
            "source_tape_fingerprint": source_tape_fingerprint,
            "adapter_version": adapter_version,
            "event_count": expected_event_count,
        }
    )
    count = 0
    prior_key: tuple[int, int, str, str] | None = None
    native_init_time_ns = -1
    for source_event in events:
        if count >= expected_event_count:
            raise ValueError("native event stream contains more records than expected")
        event = _event_wire(source_event)
        sort_key = (
            event["event_time_ns"],
            event["sequence"],
            event["dependency_id"],
            event["event_id"],
        )
        if prior_key is not None and sort_key < prior_key:
            raise ValueError("native event stream is not in canonical event order")
        prior_key = sort_key
        native_init_time_ns = max(event["event_time_ns"], native_init_time_ns + 1)
        if native_init_time_ns > 18_446_744_073_709_551_615:
            raise ValueError("native event sequence exceeds the supported timestamp range")
        write(
            {
                "record_type": "event",
                "index": count,
                "native_init_time_ns": native_init_time_ns,
                "event": event,
            },
            record_digest=True,
        )
        count += 1
    if count != expected_event_count:
        raise ValueError("native event stream count differs from expected_event_count")
    write(
        {
            "record_type": "trailer",
            "event_count": count,
            "records_sha256": f"sha256:{records_digest.hexdigest()}",
        }
    )
    return NautilusNativeEventStreamSummary(
        source_tape_fingerprint=source_tape_fingerprint,
        adapter_version=adapter_version,
        event_count=count,
        byte_length=byte_length,
        content_digest=f"sha256:{stream_digest.hexdigest()}",
    )


def deserialize_nautilus_native_event_stream(
    stream: BinaryIO,
    *,
    expected_source_tape_fingerprint: str,
    expected_adapter_version: str,
    expected_event_count: int,
    max_stream_bytes: int = MAX_NAUTILUS_NATIVE_EVENT_STREAM_BYTES,
) -> Iterator[Mapping[str, Any]]:
    """Yield validated records; trailer verification completes on exhaustion."""

    require_sha256_digest(
        expected_source_tape_fingerprint,
        field_name="expected_source_tape_fingerprint",
    )
    if not callable(getattr(stream, "readline", None)) or not callable(
        getattr(stream, "read", None)
    ):
        raise TypeError("native event stream must provide readline(size) and read(size)")
    for name, value, minimum in (
        ("expected_event_count", expected_event_count, 1),
        ("max_stream_bytes", max_stream_bytes, 1),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            raise ValueError(f"{name} must be a positive integer")
    header_line = _read_record(stream)
    if header_line is None:
        raise ValueError("native event stream header is missing")
    header, header_wire = header_line
    if set(header) != {
        "protocol_version",
        "record_type",
        "source_tape_fingerprint",
        "adapter_version",
        "event_count",
    }:
        raise ValueError("native event stream header fields are invalid")
    if (
        header["protocol_version"] != NAUTILUS_NATIVE_EVENT_STREAM_PROTOCOL
        or header["record_type"] != "header"
        or header["source_tape_fingerprint"] != expected_source_tape_fingerprint
        or header["adapter_version"] != expected_adapter_version
        or not isinstance(header["event_count"], int)
        or isinstance(header["event_count"], bool)
        or header["event_count"] != expected_event_count
    ):
        raise ValueError("native event stream header differs from its runtime bundle")
    observed_bytes = len(header_wire)
    if observed_bytes > max_stream_bytes:
        raise ValueError("native event stream exceeds its configured byte bound")

    def decoded() -> Iterator[Mapping[str, Any]]:
        nonlocal observed_bytes
        index = 0
        prior_key: tuple[int, int, str, str] | None = None
        prior_native_init_time = -1
        records_digest = hashlib.sha256()
        while line_record := _read_record(stream):
            record, wire = line_record
            observed_bytes += len(wire)
            if observed_bytes > max_stream_bytes:
                raise ValueError("native event stream exceeds its configured byte bound")
            if record.get("record_type") == "trailer":
                if set(record) != {"record_type", "event_count", "records_sha256"}:
                    raise ValueError("native event stream trailer fields are invalid")
                if (
                    not isinstance(record["event_count"], int)
                    or isinstance(record["event_count"], bool)
                    or record["event_count"] != index
                    or index != expected_event_count
                ):
                    raise ValueError("native event stream count differs from its reference")
                if record["records_sha256"] != f"sha256:{records_digest.hexdigest()}":
                    raise ValueError("native event stream record digest differs")
                if stream.read(1):
                    raise ValueError("native event stream contains trailing bytes")
                return
            if set(record) != {"record_type", "index", "native_init_time_ns", "event"}:
                raise ValueError("native event stream record fields are invalid")
            if (
                record["record_type"] != "event"
                or not isinstance(record["index"], int)
                or isinstance(record["index"], bool)
                or record["index"] != index
            ):
                raise ValueError("native event stream record index is not contiguous")
            event = _validate_event(record["event"])
            init_time = record["native_init_time_ns"]
            if not isinstance(init_time, int) or isinstance(init_time, bool):
                raise ValueError("native event stream init time must be an integer")
            if init_time < event["event_time_ns"] or init_time <= prior_native_init_time:
                raise ValueError("native event stream init times are not strictly chronological")
            if init_time > 18_446_744_073_709_551_615:
                raise ValueError("native event stream init time exceeds the supported range")
            sort_key = (
                event["event_time_ns"],
                event["sequence"],
                event["dependency_id"],
                event["event_id"],
            )
            if prior_key is not None and sort_key < prior_key:
                raise ValueError("native event stream is not in canonical event order")
            prior_key = sort_key
            prior_native_init_time = init_time
            records_digest.update(wire)
            index += 1
            yield {**event, "native_init_time_ns": init_time}
        raise ValueError("native event stream trailer is missing")

    return decoded()


__all__ = [
    "MAX_NAUTILUS_NATIVE_EVENT_ROW_BYTES",
    "MAX_NAUTILUS_NATIVE_EVENT_STREAM_BYTES",
    "NAUTILUS_NATIVE_EVENT_STREAM_PROTOCOL",
    "NautilusNativeEventStreamSummary",
    "deserialize_nautilus_native_event_stream",
    "serialize_nautilus_native_event_stream",
]
