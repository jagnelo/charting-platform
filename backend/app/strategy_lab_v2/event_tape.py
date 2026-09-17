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
from app.strategy_lab_v2.capabilities import PreflightClass
from app.strategy_lab_v2.contracts import DataSnapshot
from app.strategy_lab_v2.sdk import MarketEvent, StrategySdkManifest

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


@dataclass(frozen=True, slots=True)
class EventTapeBinding:
    """Verified tape/snapshot/SDK identity for an execution adapter."""

    event_tape_fingerprint: str
    snapshot_fingerprint: str
    manifest_fingerprint: str
    dependency_event_counts: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        for name in (
            "event_tape_fingerprint",
            "snapshot_fingerprint",
            "manifest_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        counts = tuple(self.dependency_event_counts)
        if not counts:
            raise ValueError("event-tape bindings require dependency event counts")
        if any(
            not isinstance(dependency_id, str)
            or not dependency_id.strip()
            or not isinstance(count, int)
            or isinstance(count, bool)
            or count <= 0
            for dependency_id, count in counts
        ):
            raise ValueError("dependency event counts must contain positive keyed counts")
        if counts != tuple(sorted(counts)) or len({item[0] for item in counts}) != len(counts):
            raise ValueError("dependency event counts must be unique and ordered")
        object.__setattr__(self, "dependency_event_counts", counts)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def bind_event_tape(
    tape: FrozenEventTape,
    snapshot: DataSnapshot,
    manifest: StrategySdkManifest,
) -> EventTapeBinding:
    """Verify a frozen tape against snapshot semantics and SDK dependencies.

    The provider adapter remains responsible for obtaining the snapshot and its
    coverage attestation. This function only checks that the already-frozen
    event payloads are the declared series, fields, and effective time interval
    for one SDK manifest. Degraded preflight substitutions are honored exactly
    as recorded by the snapshot; unsupported requirements fail closed.
    """

    if not isinstance(tape, FrozenEventTape):
        raise TypeError("tape must be a FrozenEventTape")
    if not isinstance(snapshot, DataSnapshot):
        raise TypeError("snapshot must be a DataSnapshot")
    if not isinstance(manifest, StrategySdkManifest):
        raise TypeError("manifest must be a StrategySdkManifest")
    if tape.snapshot_fingerprint != snapshot.fingerprint:
        raise ValueError("event tape does not belong to the supplied snapshot")
    if not tape.events:
        raise ValueError("event tape cannot bind an empty event set")

    decisions = {
        decision.requirement: decision for decision in snapshot.preflight_report.decisions
    }
    dependency_ids = {item.dependency_id for item in manifest.data_dependencies}
    tape_dependency_ids = {event.dependency_id for event in tape.events}
    if tape_dependency_ids != dependency_ids:
        missing = sorted(dependency_ids - tape_dependency_ids)
        extra = sorted(tape_dependency_ids - dependency_ids)
        raise ValueError(f"event-tape dependency mismatch; missing={missing}, extra={extra}")

    counts: list[tuple[str, int]] = []
    for dependency in manifest.data_dependencies:
        decision = decisions.get(dependency.requirement)
        if decision is None:
            raise ValueError(
                f"snapshot preflight has no decision for dependency {dependency.dependency_id!r}"
            )
        if decision.classification is PreflightClass.UNSUPPORTED:
            raise ValueError(
                f"dependency {dependency.dependency_id!r} uses an unsupported preflight"
            )
        replacements = {
            item.field: item.substituted_value for item in decision.degradations
        }
        effective_granularity = replacements.get(
            "event_granularity", dependency.requirement.event_granularity.value
        )
        effective_event_type = replacements.get(
            "event_type", dependency.requirement.event_type
        )
        effective_timeframe = replacements.get("timeframe", dependency.requirement.timeframe)
        effective_adjustment = replacements.get(
            "adjustment", dependency.requirement.adjustment.value
        )
        effective_session = replacements.get("session", dependency.requirement.session)
        effective_feed = replacements.get("feed", dependency.requirement.feed)
        effective_actions = replacements.get(
            "corporate_action_semantics",
            dependency.requirement.corporate_action_semantics,
        )
        effective_start = _replacement_time(
            replacements.get("history_start"), dependency.requirement.start
        )
        effective_end = _replacement_time(
            replacements.get("history_end"), dependency.requirement.end
        )
        candidates = tuple(
            item
            for item in snapshot.series
            if item.instrument_id == dependency.requirement.instrument_id
            and item.event_granularity.value == effective_granularity
            and item.event_type == effective_event_type
            and item.timeframe == effective_timeframe
            and item.adjustment.value == effective_adjustment
            and item.session == effective_session
            and item.feed == effective_feed
            and item.corporate_action_semantics == effective_actions
            and item.start < effective_end
            and item.end > effective_start
        )
        if not candidates:
            raise ValueError(
                f"snapshot has no matching series for dependency {dependency.dependency_id!r}"
            )
        events = tuple(
            event for event in tape.events if event.dependency_id == dependency.dependency_id
        )
        if not events:
            raise ValueError(f"dependency {dependency.dependency_id!r} has no tape events")
        allowed_fields = set(dependency.fields)
        for event in events:
            if event.instrument_id != dependency.requirement.instrument_id:
                raise ValueError(
                    f"dependency {dependency.dependency_id!r} contains an undeclared instrument"
                )
            if set(event.values) != allowed_fields:
                raise ValueError(
                    f"dependency {dependency.dependency_id!r} event fields do not match its declaration"
                )
            event_time = event.event_time.astimezone(UTC)
            if not any(item.start <= event_time < item.end for item in candidates):
                raise ValueError(
                    f"dependency {dependency.dependency_id!r} event falls outside snapshot coverage"
                )
        counts.append((dependency.dependency_id, len(events)))

    return EventTapeBinding(
        event_tape_fingerprint=tape.fingerprint,
        snapshot_fingerprint=snapshot.fingerprint,
        manifest_fingerprint=manifest.fingerprint,
        dependency_event_counts=tuple(sorted(counts)),
    )


def _replacement_time(value: str | None, fallback: datetime) -> datetime:
    if value is None:
        return fallback
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("history replacement must be an ISO-8601 timestamp") from error
    _aware(result, "history replacement")
    return result.astimezone(UTC)


__all__ = [
    "EVENT_TAPE_DEFINITION_VERSION",
    "EventTapeBatch",
    "EventTapeBinding",
    "FrozenEventTape",
    "bind_event_tape",
]
