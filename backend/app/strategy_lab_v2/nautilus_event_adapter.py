"""Provider-neutral canonical-event materialization for Nautilus adapters.

This module deliberately stops before importing Nautilus or acquiring data. It
turns a verified engine-neutral event tape into a deterministic, typed wire
contract that a future Rust/PyO3 or host callback adapter can materialize as
Nautilus ``Bar``, ``QuoteTick``, or ``TradeTick`` values.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.strategy_lab_v2.canonical import content_digest, freeze_json, require_sha256_digest
from app.strategy_lab_v2.contracts import DataSnapshot
from app.strategy_lab_v2.event_tape import FrozenEventTape, bind_event_tape
from app.strategy_lab_v2.sdk import MarketEvent, StrategySdkManifest

NAUTILUS_EVENT_ADAPTER_VERSION = "strategy-lab.nautilus-event-adapter.v1"

_REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    "ohlcv": frozenset({"open", "high", "low", "close", "volume"}),
    "quote": frozenset({"bid", "ask", "bid_size", "ask_size"}),
    "trade": frozenset({"price", "size", "aggressor_side"}),
}


def _event_time_ns(value: datetime) -> int:
    normalized = value.astimezone(UTC)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = normalized - epoch
    return (delta.days * 86_400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1_000


@dataclass(frozen=True, slots=True)
class NautilusEventRecord:
    """One canonical event in the Nautilus-neutral wire representation."""

    dependency_id: str
    event_id: str
    instrument_id: str
    event_type: str
    event_time_ns: int
    sequence: int
    values: Mapping[str, Any]

    def __post_init__(self) -> None:
        for name in ("dependency_id", "event_id", "instrument_id", "event_type"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if self.event_type not in _REQUIRED_FIELDS:
            raise ValueError(f"unsupported Nautilus event type: {self.event_type}")
        if not isinstance(self.event_time_ns, int) or isinstance(self.event_time_ns, bool):
            raise TypeError("event_time_ns must be an integer")
        if self.event_time_ns < 0:
            raise ValueError("event_time_ns must be non-negative")
        if (
            not isinstance(self.sequence, int)
            or isinstance(self.sequence, bool)
            or self.sequence < 0
        ):
            raise ValueError("sequence must be a non-negative integer")
        if not isinstance(self.values, Mapping):
            raise TypeError("values must be a mapping")
        frozen = freeze_json(self.values)
        if not isinstance(frozen, Mapping):
            raise TypeError("values must be a mapping")
        missing = _REQUIRED_FIELDS[self.event_type] - set(frozen)
        if missing:
            raise ValueError(f"{self.event_type} event is missing fields: {sorted(missing)}")
        object.__setattr__(self, "values", frozen)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class NautilusEventTape:
    """Deterministic materialization input for a Nautilus data adapter."""

    source_tape_fingerprint: str
    events: tuple[NautilusEventRecord, ...]
    adapter_version: str = NAUTILUS_EVENT_ADAPTER_VERSION

    def __post_init__(self) -> None:
        require_sha256_digest(self.source_tape_fingerprint, field_name="source_tape_fingerprint")
        if self.adapter_version != NAUTILUS_EVENT_ADAPTER_VERSION:
            raise ValueError("unsupported Nautilus event adapter version")
        events = tuple(self.events)
        if any(not isinstance(event, NautilusEventRecord) for event in events):
            raise TypeError("events must contain NautilusEventRecord values")
        event_ids = [event.event_id for event in events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("Nautilus event ids must be unique")
        ordered = tuple(
            sorted(
                events,
                key=lambda item: (
                    item.event_time_ns,
                    item.sequence,
                    item.dependency_id,
                    item.event_id,
                ),
            )
        )
        object.__setattr__(self, "events", ordered)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def materialize_nautilus_event(
    event: MarketEvent,
    *,
    event_type: str,
) -> NautilusEventRecord:
    """Convert one validated engine-neutral event without I/O or inference."""

    if not isinstance(event, MarketEvent):
        raise TypeError("event must be a MarketEvent")
    if not isinstance(event_type, str) or not event_type.strip():
        raise ValueError("event_type must not be empty")
    return NautilusEventRecord(
        dependency_id=event.dependency_id,
        event_id=event.event_id,
        instrument_id=event.instrument_id,
        event_type=event_type,
        event_time_ns=_event_time_ns(event.event_time),
        sequence=event.sequence,
        values=event.values,
    )


def materialize_nautilus_event_tape(
    tape: FrozenEventTape,
    snapshot: DataSnapshot,
    manifest: StrategySdkManifest,
) -> NautilusEventTape:
    """Bind and materialize one frozen tape for a future Nautilus adapter."""

    if not isinstance(tape, FrozenEventTape):
        raise TypeError("tape must be a FrozenEventTape")
    if not isinstance(snapshot, DataSnapshot):
        raise TypeError("snapshot must be a DataSnapshot")
    if not isinstance(manifest, StrategySdkManifest):
        raise TypeError("manifest must be a StrategySdkManifest")
    bind_event_tape(tape, snapshot, manifest)
    event_types = {
        item.dependency_id: item.requirement.event_type for item in manifest.data_dependencies
    }
    records = tuple(
        materialize_nautilus_event(event, event_type=event_types[event.dependency_id])
        for event in tape.events
    )
    return NautilusEventTape(tape.fingerprint, records)


__all__ = [
    "NAUTILUS_EVENT_ADAPTER_VERSION",
    "NautilusEventRecord",
    "NautilusEventTape",
    "materialize_nautilus_event",
    "materialize_nautilus_event_tape",
]
