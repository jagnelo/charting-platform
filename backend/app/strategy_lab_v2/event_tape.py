"""Frozen, deterministic event-tape boundaries for Strategy Lab replay.

The provider platform owns acquisition and snapshot coverage.  Once an adapter
has produced a frozen snapshot, this module gives a backtest/forward worker a
small immutable event tape that can be replayed in exactly the same order.  It
does not fetch data, infer missing observations, or model orders and fills.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.sdk import MarketEvent

EVENT_TAPE_DEFINITION_VERSION = "strategy-lab.event-tape.v1"


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class EventTapeBatch:
    """All frozen events available at one UTC event-time boundary."""

    batch_sequence: int
    event_time: datetime
    events: tuple[MarketEvent, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.batch_sequence, int)
            or isinstance(self.batch_sequence, bool)
            or self.batch_sequence < 0
        ):
            raise ValueError("batch_sequence must be a non-negative integer")
        _aware(self.event_time, "event_time")
        object.__setattr__(self, "event_time", self.event_time.astimezone(UTC))
        events = tuple(self.events)
        if not events:
            raise ValueError("event tape batches must contain events")
        if any(not isinstance(event, MarketEvent) for event in events):
            raise TypeError("events must contain MarketEvent values")
        if any(event.event_time != self.event_time for event in events):
            raise ValueError("batch events must share the batch event_time")
        if events != tuple(
            sorted(events, key=lambda item: (item.sequence, item.dependency_id, item.event_id))
        ):
            raise ValueError("batch events must be deterministically ordered")
        object.__setattr__(self, "events", events)


@dataclass(frozen=True, slots=True)
class FrozenEventTape:
    """Content-addressed event sequence bound to one frozen snapshot."""

    snapshot_fingerprint: str
    events: tuple[MarketEvent, ...] = ()
    definition_version: str = EVENT_TAPE_DEFINITION_VERSION

    def __post_init__(self) -> None:
        require_sha256_digest(self.snapshot_fingerprint, field_name="snapshot_fingerprint")
        if self.definition_version != EVENT_TAPE_DEFINITION_VERSION:
            raise ValueError("unsupported event-tape definition version")
        events = tuple(self.events)
        if any(not isinstance(event, MarketEvent) for event in events):
            raise TypeError("events must contain MarketEvent values")
        ids = [event.event_id for event in events]
        if len(ids) != len(set(ids)):
            raise ValueError("event ids must be unique within a frozen tape")

        # A dependency is a manifest-bound series. It cannot silently switch
        # instruments halfway through a replay.
        dependency_instruments: dict[str, str] = {}
        for event in events:
            prior_instrument = dependency_instruments.setdefault(
                event.dependency_id, event.instrument_id
            )
            if prior_instrument != event.instrument_id:
                raise ValueError(
                    f"dependency {event.dependency_id!r} contains multiple instruments"
                )

        ordered = tuple(
            sorted(
                events,
                key=lambda item: (
                    item.event_time,
                    item.sequence,
                    item.dependency_id,
                    item.event_id,
                ),
            )
        )
        previous_by_dependency: dict[str, MarketEvent] = {}
        for event in ordered:
            previous = previous_by_dependency.get(event.dependency_id)
            if previous is not None and (
                event.sequence <= previous.sequence or event.event_time < previous.event_time
            ):
                raise ValueError(
                    f"dependency {event.dependency_id!r} events must advance sequence and time"
                )
            previous_by_dependency[event.dependency_id] = event
        object.__setattr__(self, "events", ordered)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)

    @property
    def start_time(self) -> datetime | None:
        return self.events[0].event_time if self.events else None

    @property
    def end_time(self) -> datetime | None:
        return self.events[-1].event_time if self.events else None

    @property
    def event_count(self) -> int:
        return len(self.events)

    def batches(self) -> tuple[EventTapeBatch, ...]:
        """Group events by exact UTC timestamp in stable replay order."""

        if not self.events:
            return ()
        grouped: list[EventTapeBatch] = []
        current_time = self.events[0].event_time
        current_events: list[MarketEvent] = []
        batch_sequence = 0
        for event in self.events:
            if event.event_time != current_time:
                grouped.append(EventTapeBatch(batch_sequence, current_time, tuple(current_events)))
                batch_sequence += 1
                current_time = event.event_time
                current_events = []
            current_events.append(event)
        grouped.append(EventTapeBatch(batch_sequence, current_time, tuple(current_events)))
        return tuple(grouped)

    def iter_events_until(
        self,
        through: datetime,
        *,
        include_boundary: bool = True,
    ) -> Iterator[MarketEvent]:
        """Yield immutable events through a UTC boundary without interpolation."""

        _aware(through, "through")
        boundary = through.astimezone(UTC)
        for event in self.events:
            if event.event_time < boundary or (include_boundary and event.event_time == boundary):
                yield event
            else:
                break

    def slice(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        *,
        include_start: bool = True,
        include_end: bool = True,
    ) -> tuple[MarketEvent, ...]:
        """Return a deterministic time slice; no event is synthesized."""

        if start is not None:
            _aware(start, "start")
            start = start.astimezone(UTC)
        if end is not None:
            _aware(end, "end")
            end = end.astimezone(UTC)
        if start is not None and end is not None and start > end:
            raise ValueError("slice start must not follow end")
        result: list[MarketEvent] = []
        for event in self.events:
            after_start = start is None or event.event_time > start or (
                include_start and event.event_time == start
            )
            before_end = end is None or event.event_time < end or (
                include_end and event.event_time == end
            )
            if after_start and before_end:
                result.append(event)
        return tuple(result)


__all__ = ["EVENT_TAPE_DEFINITION_VERSION", "EventTapeBatch", "FrozenEventTape"]
