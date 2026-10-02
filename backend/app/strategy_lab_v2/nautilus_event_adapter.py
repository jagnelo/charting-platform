"""Provider-neutral canonical-event materialization for Nautilus adapters.

This module deliberately stops before importing Nautilus or acquiring data. It
turns a verified engine-neutral event tape into a deterministic, typed wire
contract that a future Rust/PyO3 or host callback adapter can materialize as
Nautilus ``Bar``, ``QuoteTick``, or ``TradeTick`` values.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.strategy_lab_v2.canonical import content_digest, freeze_json, require_sha256_digest
from app.strategy_lab_v2.contracts import DataSnapshot
from app.strategy_lab_v2.event_tape import FrozenEventTape, bind_event_tape
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.sdk import MarketEvent, StrategySdkManifest

NAUTILUS_EVENT_ADAPTER_VERSION = "strategy-lab.nautilus-event-adapter.v1"
NAUTILUS_EVENT_PARITY_VERSION = "strategy-lab.nautilus-event-parity.v1"
NAUTILUS_FORWARD_TAPE_VERSION = "strategy-lab.nautilus-forward-tape.v1"

_WIRE_FIELDS = frozenset(
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


@dataclass(frozen=True, slots=True)
class NautilusEventParityReceipt:
    """Evidence comparing adapter output with one canonical event tape.

    This receipt proves only that an injected host/Rust adapter reproduced the
    canonical wire records. It is deliberately not engine conformance evidence
    and can never authorize publication or live shadow execution.
    """

    source_tape_fingerprint: str
    materialized_tape_fingerprint: str
    expected_event_count: int
    observed_event_count: int
    expected_wire_digest: str
    observed_wire_digest: str
    mismatches: tuple[str, ...] = ()
    passed: bool = False
    parity_version: str = NAUTILUS_EVENT_PARITY_VERSION

    def __post_init__(self) -> None:
        require_sha256_digest(self.source_tape_fingerprint, field_name="source_tape_fingerprint")
        require_sha256_digest(
            self.materialized_tape_fingerprint,
            field_name="materialized_tape_fingerprint",
        )
        require_sha256_digest(self.expected_wire_digest, field_name="expected_wire_digest")
        require_sha256_digest(self.observed_wire_digest, field_name="observed_wire_digest")
        for name in ("expected_event_count", "observed_event_count"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        mismatches = tuple(self.mismatches)
        if any(not isinstance(item, str) or not item.strip() for item in mismatches):
            raise ValueError("parity mismatches must contain non-empty strings")
        if mismatches != tuple(sorted(set(mismatches))):
            raise ValueError("parity mismatches must be unique and ordered")
        if not isinstance(self.passed, bool):
            raise TypeError("passed must be a boolean")
        if self.parity_version != NAUTILUS_EVENT_PARITY_VERSION:
            raise ValueError("unsupported Nautilus event parity version")
        equivalent = (
            self.expected_event_count == self.observed_event_count
            and self.expected_wire_digest == self.observed_wire_digest
            and not mismatches
        )
        if self.passed != equivalent:
            raise ValueError("parity pass state does not match the observed evidence")
        object.__setattr__(self, "mismatches", mismatches)

    @property
    def compatible(self) -> bool:
        return self.passed

    @property
    def authoritative(self) -> bool:
        return False

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class NautilusForwardEventEnvelope:
    """Canonical forward metadata bound to one Nautilus wire record."""

    canonical_event: CanonicalForwardEvent
    record: NautilusEventRecord

    def __post_init__(self) -> None:
        if not isinstance(self.canonical_event, CanonicalForwardEvent):
            raise TypeError("canonical_event must be a CanonicalForwardEvent")
        if not isinstance(self.record, NautilusEventRecord):
            raise TypeError("record must be a NautilusEventRecord")
        if self.canonical_event.event_id != self.record.event_id:
            raise ValueError("canonical and Nautilus event ids must match")
        if self.canonical_event.sequence != self.record.sequence:
            raise ValueError("canonical and Nautilus event sequences must match")
        if _event_time_ns(self.canonical_event.event_time) != self.record.event_time_ns:
            raise ValueError("canonical and Nautilus event times must match")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class NautilusForwardEventTape:
    """Ordered forward envelopes ready for a future host/Rust callback."""

    instance_id: str
    envelopes: tuple[NautilusForwardEventEnvelope, ...]
    definition_version: str = NAUTILUS_FORWARD_TAPE_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.instance_id, str) or not self.instance_id.strip():
            raise ValueError("instance_id must not be empty")
        if self.definition_version != NAUTILUS_FORWARD_TAPE_VERSION:
            raise ValueError("unsupported Nautilus forward tape version")
        envelopes = tuple(self.envelopes)
        if not envelopes:
            raise ValueError("Nautilus forward tapes require envelopes")
        if any(not isinstance(item, NautilusForwardEventEnvelope) for item in envelopes):
            raise TypeError("envelopes must contain NautilusForwardEventEnvelope values")
        event_ids = [item.record.event_id for item in envelopes]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("Nautilus forward event ids must be unique")
        sequences = [item.record.sequence for item in envelopes]
        if len(sequences) != len(set(sequences)):
            raise ValueError("Nautilus forward event sequences must be unique")
        object.__setattr__(
            self,
            "envelopes",
            tuple(
                sorted(
                    envelopes,
                    key=lambda item: (
                        item.record.sequence,
                        item.record.event_time_ns,
                        item.record.event_id,
                    ),
                )
            ),
        )

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


def materialize_nautilus_forward_event(
    canonical_event: CanonicalForwardEvent,
    market_event: MarketEvent,
    *,
    event_type: str,
) -> NautilusForwardEventEnvelope:
    """Bind admitted forward metadata and payload before engine handoff."""

    if not isinstance(canonical_event, CanonicalForwardEvent):
        raise TypeError("canonical_event must be a CanonicalForwardEvent")
    if not isinstance(market_event, MarketEvent):
        raise TypeError("market_event must be a MarketEvent")
    if canonical_event.event_id != market_event.event_id:
        raise ValueError("canonical and market event ids must match")
    if canonical_event.sequence != market_event.sequence:
        raise ValueError("canonical and market event sequences must match")
    if canonical_event.event_time != market_event.event_time:
        raise ValueError("canonical and market event times must match")
    return NautilusForwardEventEnvelope(
        canonical_event,
        materialize_nautilus_event(market_event, event_type=event_type),
    )


def materialize_nautilus_forward_tape(
    instance_id: str,
    canonical_events: Sequence[CanonicalForwardEvent],
    market_events: Sequence[MarketEvent],
    *,
    event_type_by_dependency: Mapping[str, str],
) -> NautilusForwardEventTape:
    """Materialize an admitted forward batch without provider or engine I/O."""

    if not isinstance(instance_id, str) or not instance_id.strip():
        raise ValueError("instance_id must not be empty")
    if not isinstance(canonical_events, Sequence) or isinstance(
        canonical_events, str | bytes
    ):
        raise TypeError("canonical_events must be a sequence")
    if not isinstance(market_events, Sequence) or isinstance(market_events, str | bytes):
        raise TypeError("market_events must be a sequence")
    if len(canonical_events) != len(market_events):
        raise ValueError("canonical and market event batches must have equal length")
    if not isinstance(event_type_by_dependency, Mapping):
        raise TypeError("event_type_by_dependency must be a mapping")
    if not event_type_by_dependency:
        raise ValueError("event_type_by_dependency must not be empty")
    envelopes: list[NautilusForwardEventEnvelope] = []
    observed_dependencies: set[str] = set()
    for canonical_event, market_event in zip(canonical_events, market_events, strict=True):
        if not isinstance(canonical_event, CanonicalForwardEvent):
            raise TypeError("canonical_events must contain CanonicalForwardEvent values")
        if not isinstance(market_event, MarketEvent):
            raise TypeError("market_events must contain MarketEvent values")
        observed_dependencies.add(market_event.dependency_id)
        try:
            event_type = event_type_by_dependency[market_event.dependency_id]
        except KeyError as error:
            raise ValueError(
                f"event type is missing for dependency {market_event.dependency_id!r}"
            ) from error
        envelopes.append(
            materialize_nautilus_forward_event(
                canonical_event,
                market_event,
                event_type=event_type,
            )
        )
    if set(event_type_by_dependency) != observed_dependencies:
        raise ValueError("event_type_by_dependency contains an unused dependency")
    return NautilusForwardEventTape(instance_id, tuple(envelopes))


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
    event_types = _effective_event_types(snapshot, manifest)
    records = tuple(
        materialize_nautilus_event(event, event_type=event_types[event.dependency_id])
        for event in tape.events
    )
    return NautilusEventTape(tape.fingerprint, records)


def _effective_event_types(
    snapshot: DataSnapshot,
    manifest: StrategySdkManifest,
) -> dict[str, str]:
    decisions = {decision.requirement: decision for decision in snapshot.preflight_report.decisions}
    event_types: dict[str, str] = {}
    for dependency in manifest.data_dependencies:
        decision = decisions.get(dependency.requirement)
        if decision is None:
            raise ValueError(
                f"snapshot preflight has no decision for dependency {dependency.dependency_id!r}"
            )
        replacements = {item.field: item.substituted_value for item in decision.degradations}
        event_types[dependency.dependency_id] = replacements.get(
            "event_type", dependency.requirement.event_type
        )
    return event_types


def verify_nautilus_event_tape_parity(
    tape: NautilusEventTape,
    observed_events: Sequence[Mapping[str, Any]],
) -> NautilusEventParityReceipt:
    """Compare injected adapter wire output with a canonical materialization.

    The observed payload is intentionally a strict mapping contract so a Rust,
    PyO3, or host callback adapter can be tested without importing Nautilus in
    the backend process. Event order is canonicalized before comparison; event
    identity or field differences are returned as failed evidence.
    """

    if not isinstance(tape, NautilusEventTape):
        raise TypeError("tape must be a NautilusEventTape")
    if not isinstance(observed_events, Sequence) or isinstance(observed_events, str | bytes):
        raise TypeError("observed_events must be a sequence of mappings")
    observed = tuple(_parse_wire_event(item) for item in observed_events)
    observed_ids = [item.event_id for item in observed]
    if len(observed_ids) != len(set(observed_ids)):
        raise ValueError("observed Nautilus event ids must be unique")
    ordered_observed = tuple(sorted(observed, key=_event_order))
    expected_payloads = tuple(_wire_payload(item) for item in tape.events)
    observed_payloads = tuple(_wire_payload(item) for item in ordered_observed)
    mismatches: list[str] = []
    for index in range(max(len(tape.events), len(ordered_observed))):
        if index >= len(tape.events) or index >= len(ordered_observed):
            mismatches.append(f"event[{index}]")
            continue
        expected = tape.events[index]
        observed_item = ordered_observed[index]
        for field in (
            "dependency_id",
            "event_id",
            "instrument_id",
            "event_type",
            "event_time_ns",
            "sequence",
        ):
            if getattr(expected, field) != getattr(observed_item, field):
                mismatches.append(f"event[{index}].{field}")
        if expected.values != observed_item.values:
            mismatches.append(f"event[{index}].values")
    expected_digest = content_digest(expected_payloads)
    observed_digest = content_digest(observed_payloads)
    ordered_mismatches = tuple(sorted(set(mismatches)))
    return NautilusEventParityReceipt(
        source_tape_fingerprint=tape.source_tape_fingerprint,
        materialized_tape_fingerprint=tape.fingerprint,
        expected_event_count=len(tape.events),
        observed_event_count=len(ordered_observed),
        expected_wire_digest=expected_digest,
        observed_wire_digest=observed_digest,
        mismatches=ordered_mismatches,
        passed=not ordered_mismatches,
    )


def _event_order(event: NautilusEventRecord) -> tuple[int, int, str, str]:
    return (event.event_time_ns, event.sequence, event.dependency_id, event.event_id)


def _wire_payload(event: NautilusEventRecord) -> Mapping[str, Any]:
    return {
        "dependency_id": event.dependency_id,
        "event_id": event.event_id,
        "instrument_id": event.instrument_id,
        "event_type": event.event_type,
        "event_time_ns": event.event_time_ns,
        "sequence": event.sequence,
        "values": event.values,
    }


def _parse_wire_event(payload: Mapping[str, Any]) -> NautilusEventRecord:
    if not isinstance(payload, Mapping):
        raise TypeError("observed Nautilus events must be mappings")
    if set(payload) != _WIRE_FIELDS:
        raise ValueError("observed Nautilus event fields must match the exact wire schema")
    return NautilusEventRecord(
        dependency_id=payload["dependency_id"],
        event_id=payload["event_id"],
        instrument_id=payload["instrument_id"],
        event_type=payload["event_type"],
        event_time_ns=payload["event_time_ns"],
        sequence=payload["sequence"],
        values=payload["values"],
    )


__all__ = [
    "NAUTILUS_EVENT_ADAPTER_VERSION",
    "NAUTILUS_EVENT_PARITY_VERSION",
    "NAUTILUS_FORWARD_TAPE_VERSION",
    "NautilusEventParityReceipt",
    "NautilusEventRecord",
    "NautilusEventTape",
    "NautilusForwardEventEnvelope",
    "NautilusForwardEventTape",
    "materialize_nautilus_event",
    "materialize_nautilus_forward_event",
    "materialize_nautilus_forward_tape",
    "materialize_nautilus_event_tape",
    "verify_nautilus_event_tape_parity",
]
