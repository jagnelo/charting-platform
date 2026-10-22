"""Immutable forward-state checkpoints and idempotent event application."""

from __future__ import annotations

from dataclasses import dataclass

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import ForwardInstance
from app.strategy_lab_v2.lifecycle import (
    CanonicalForwardEvent,
    ForwardEventDisposition,
    ForwardEventObservation,
    apply_forward_event_observation,
)


def _event_ids(values: frozenset[str], field_name: str) -> frozenset[str]:
    if not isinstance(values, set | frozenset):
        raise TypeError(f"{field_name} must be a set of event ids")
    normalized = frozenset(values)
    if any(not isinstance(value, str) or not value.strip() for value in normalized):
        raise ValueError(f"{field_name} must contain non-empty event ids")
    return normalized


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


@dataclass(frozen=True, slots=True)
class ForwardCheckpointTransition:
    """Compact append-only delta linking one durable checkpoint to its parent.

    Persisting a full checkpoint after every event would duplicate the growing
    event-id sets quadratically. This record stores only set changes and the
    small instance snapshot; replay reconstructs and verifies each checkpoint
    fingerprint from the chain.
    """

    checkpoint_fingerprint: str
    previous_checkpoint_fingerprint: str | None
    instance: ForwardInstance
    processed_added: frozenset[str] = frozenset()
    processed_removed: frozenset[str] = frozenset()
    buffered_added: frozenset[str] = frozenset()
    buffered_removed: frozenset[str] = frozenset()
    corrections_added: frozenset[str] = frozenset()
    corrections_removed: frozenset[str] = frozenset()
    duplicate_count: int = 0
    out_of_order_count: int = 0

    def __post_init__(self) -> None:
        require_sha256_digest(self.checkpoint_fingerprint, field_name="checkpoint_fingerprint")
        if self.previous_checkpoint_fingerprint is not None:
            require_sha256_digest(
                self.previous_checkpoint_fingerprint,
                field_name="previous_checkpoint_fingerprint",
            )
            if self.previous_checkpoint_fingerprint == self.checkpoint_fingerprint:
                raise ValueError("checkpoint transition cannot reference itself as its parent")
        if not isinstance(self.instance, ForwardInstance):
            raise TypeError("instance must be a ForwardInstance")
        set_fields = (
            "processed_added",
            "processed_removed",
            "buffered_added",
            "buffered_removed",
            "corrections_added",
            "corrections_removed",
        )
        for name in set_fields:
            values = _event_ids(getattr(self, name), name)
            object.__setattr__(self, name, values)
        for added, removed in (
            (self.processed_added, self.processed_removed),
            (self.buffered_added, self.buffered_removed),
            (self.corrections_added, self.corrections_removed),
        ):
            if added & removed:
                raise ValueError("checkpoint transition cannot add and remove the same event id")
        if (
            not isinstance(self.duplicate_count, int)
            or isinstance(self.duplicate_count, bool)
            or self.duplicate_count < 0
        ):
            raise ValueError("duplicate_count must be a non-negative integer")
        if (
            not isinstance(self.out_of_order_count, int)
            or isinstance(self.out_of_order_count, bool)
            or self.out_of_order_count < 0
        ):
            raise ValueError("out_of_order_count must be a non-negative integer")

    @classmethod
    def between(
        cls,
        previous: ForwardStateCheckpoint | None,
        current: ForwardStateCheckpoint,
    ) -> ForwardCheckpointTransition:
        """Create the minimal state delta needed to reconstruct ``current``."""

        if not isinstance(current, ForwardStateCheckpoint):
            raise TypeError("current must be a ForwardStateCheckpoint")
        if previous is not None and not isinstance(previous, ForwardStateCheckpoint):
            raise TypeError("previous must be a ForwardStateCheckpoint or None")
        if previous is not None and previous.instance.instance_id != current.instance.instance_id:
            raise ValueError("checkpoint transition cannot change instance identity")
        if previous is not None and previous == current:
            raise ValueError("identical checkpoints do not require a transition")

        def added(name: str) -> frozenset[str]:
            values = getattr(current, name)
            return values if previous is None else values - getattr(previous, name)

        def removed(name: str) -> frozenset[str]:
            return (
                frozenset()
                if previous is None
                else getattr(previous, name) - getattr(current, name)
            )

        transition = cls(
            checkpoint_fingerprint=current.fingerprint,
            previous_checkpoint_fingerprint=None if previous is None else previous.fingerprint,
            instance=current.instance,
            processed_added=added("processed_event_ids"),
            processed_removed=removed("processed_event_ids"),
            buffered_added=added("buffered_event_ids"),
            buffered_removed=removed("buffered_event_ids"),
            corrections_added=added("correction_event_ids"),
            corrections_removed=removed("correction_event_ids"),
            duplicate_count=current.duplicate_count,
            out_of_order_count=current.out_of_order_count,
        )
        if transition.apply(previous) != current:
            raise ValueError("checkpoint transition does not reconstruct its target")
        return transition

    def apply(self, previous: ForwardStateCheckpoint | None) -> ForwardStateCheckpoint:
        """Reconstruct and fingerprint-check this checkpoint from its parent."""

        if self.previous_checkpoint_fingerprint is None:
            if previous is not None:
                raise ValueError("root checkpoint transition cannot have a parent")
            prior_processed: frozenset[str] = frozenset()
            prior_buffered: frozenset[str] = frozenset()
            prior_corrections: frozenset[str] = frozenset()
            prior_duplicates = 0
            prior_out_of_order = 0
        else:
            if previous is None or previous.fingerprint != self.previous_checkpoint_fingerprint:
                raise ValueError("checkpoint transition parent fingerprint differs")
            if previous.instance.instance_id != self.instance.instance_id:
                raise ValueError("checkpoint transition parent belongs to another instance")
            prior_processed = previous.processed_event_ids
            prior_buffered = previous.buffered_event_ids
            prior_corrections = previous.correction_event_ids
            prior_duplicates = previous.duplicate_count
            prior_out_of_order = previous.out_of_order_count
        if self.duplicate_count < prior_duplicates or self.out_of_order_count < prior_out_of_order:
            raise ValueError("checkpoint transition counters cannot regress")

        def apply_set(
            prior: frozenset[str], added: frozenset[str], removed: frozenset[str]
        ) -> frozenset[str]:
            if not removed.issubset(prior) or prior & added:
                raise ValueError("checkpoint transition event-set delta is inconsistent")
            return (prior - removed) | added

        result = ForwardStateCheckpoint(
            instance=self.instance,
            processed_event_ids=apply_set(
                prior_processed, self.processed_added, self.processed_removed
            ),
            buffered_event_ids=apply_set(
                prior_buffered, self.buffered_added, self.buffered_removed
            ),
            correction_event_ids=apply_set(
                prior_corrections, self.corrections_added, self.corrections_removed
            ),
            duplicate_count=self.duplicate_count,
            out_of_order_count=self.out_of_order_count,
        )
        if result.fingerprint != self.checkpoint_fingerprint:
            raise ValueError("checkpoint transition target fingerprint differs")
        return result

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
    if (
        disposition is ForwardEventDisposition.ACCEPTED
        and event.event_id in checkpoint.processed_event_ids
    ):
        return checkpoint
    if (
        disposition is ForwardEventDisposition.GAP
        and event.event_id in checkpoint.buffered_event_ids
    ):
        return checkpoint
    if (
        disposition is ForwardEventDisposition.CORRECTION
        and event.event_id in checkpoint.correction_event_ids
    ):
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
