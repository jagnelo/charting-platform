"""Immutable forward-state checkpoints and idempotent event application."""

from __future__ import annotations

from dataclasses import dataclass

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import ForwardInstance
from app.strategy_lab_v2.lifecycle import (
    CanonicalForwardEvent,
    ForwardEventDisposition,
    ForwardEventObservation,
    apply_forward_event_observation,
)


def _event_ids(values: frozenset[str], field_name: str) -> frozenset[str]:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError(f"{field_name} must contain non-empty event ids")
    return frozenset(values)


@dataclass(frozen=True, slots=True)
class ForwardStateCheckpoint:
    """Storage-neutral snapshot of all state needed for forward idempotency."""

    instance: ForwardInstance
    processed_event_ids: frozenset[str] = frozenset()
    buffered_event_ids: frozenset[str] = frozenset()
    correction_event_ids: frozenset[str] = frozenset()
    duplicate_count: int = 0
    out_of_order_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.instance, ForwardInstance):
            raise TypeError("checkpoint instance must be a ForwardInstance")
        processed = _event_ids(self.processed_event_ids, "processed_event_ids")
        buffered = _event_ids(self.buffered_event_ids, "buffered_event_ids")
        corrections = _event_ids(self.correction_event_ids, "correction_event_ids")
        if processed & buffered or processed & corrections or buffered & corrections:
            raise ValueError("checkpoint event-id sets must be disjoint")
        if self.instance.last_event_id is not None and self.instance.last_event_id not in processed:
            raise ValueError("checkpoint processed events must include the instance cursor event")
        if self.instance.correction_count != len(corrections):
            raise ValueError("checkpoint corrections must match the instance correction count")
        for name in ("duplicate_count", "out_of_order_count"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"checkpoint {name} must be a non-negative integer")
        object.__setattr__(self, "processed_event_ids", processed)
        object.__setattr__(self, "buffered_event_ids", buffered)
        object.__setattr__(self, "correction_event_ids", corrections)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def apply_checkpoint_observation(
    checkpoint: ForwardStateCheckpoint,
    event: CanonicalForwardEvent,
    observation: ForwardEventObservation,
) -> ForwardStateCheckpoint:
    """Apply one observation, making state-changing records idempotent."""

    if not isinstance(checkpoint, ForwardStateCheckpoint):
        raise TypeError("checkpoint must be a ForwardStateCheckpoint")
    if not isinstance(event, CanonicalForwardEvent):
        raise TypeError("event must be a CanonicalForwardEvent")
    if not isinstance(observation, ForwardEventObservation):
        raise TypeError("observation must be a ForwardEventObservation")

    disposition = observation.disposition
    if disposition is ForwardEventDisposition.ACCEPTED and event.event_id in checkpoint.processed_event_ids:
        return checkpoint
    if disposition is ForwardEventDisposition.GAP and event.event_id in checkpoint.buffered_event_ids:
        return checkpoint
    if disposition is ForwardEventDisposition.CORRECTION and event.event_id in checkpoint.correction_event_ids:
        return checkpoint

    instance = apply_forward_event_observation(checkpoint.instance, event, observation)
    processed = checkpoint.processed_event_ids
    buffered = checkpoint.buffered_event_ids
    corrections = checkpoint.correction_event_ids
    duplicate_count = checkpoint.duplicate_count
    out_of_order_count = checkpoint.out_of_order_count
    if disposition is ForwardEventDisposition.ACCEPTED:
        processed = processed | {event.event_id}
        buffered = buffered - {event.event_id}
    elif disposition is ForwardEventDisposition.GAP:
        buffered = buffered | {event.event_id}
    elif disposition is ForwardEventDisposition.CORRECTION:
        corrections = corrections | {event.event_id}
    elif disposition is ForwardEventDisposition.DUPLICATE:
        duplicate_count += 1
    elif disposition is ForwardEventDisposition.OUT_OF_ORDER:
        out_of_order_count += 1
    return ForwardStateCheckpoint(
        instance=instance,
        processed_event_ids=processed,
        buffered_event_ids=buffered,
        correction_event_ids=corrections,
        duplicate_count=duplicate_count,
        out_of_order_count=out_of_order_count,
    )
