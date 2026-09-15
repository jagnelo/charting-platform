"""Pure attempt/forward lifecycle transitions and canonical event observations."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum

from app.strategy_lab_v2.canonical import require_sha256_digest
from app.strategy_lab_v2.contracts import AttemptState, ForwardInstance, ForwardState, RunAttempt

_ATTEMPT_TRANSITIONS: dict[AttemptState, frozenset[AttemptState]] = {
    AttemptState.QUEUED: frozenset({AttemptState.RUNNING, AttemptState.CANCELLED}),
    AttemptState.RUNNING: frozenset(
        {AttemptState.SUCCEEDED, AttemptState.FAILED, AttemptState.CANCELLED}
    ),
    AttemptState.SUCCEEDED: frozenset(),
    AttemptState.FAILED: frozenset(),
    AttemptState.CANCELLED: frozenset(),
}

_FORWARD_TRANSITIONS: dict[ForwardState, frozenset[ForwardState]] = {
    ForwardState.CREATED: frozenset({ForwardState.WARMING_UP, ForwardState.STOPPED}),
    ForwardState.WARMING_UP: frozenset({ForwardState.ACTIVE, ForwardState.STOPPED}),
    ForwardState.ACTIVE: frozenset({ForwardState.PAUSED, ForwardState.STOPPED}),
    ForwardState.PAUSED: frozenset({ForwardState.ACTIVE, ForwardState.STOPPED}),
    ForwardState.STOPPED: frozenset(),
}


def transition_attempt(attempt: RunAttempt, target: AttemptState, *, now: datetime) -> RunAttempt:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("attempt transition time must be timezone-aware")
    if now < (attempt.updated_at or attempt.created_at):
        raise ValueError("attempt transition time cannot move backwards")
    if target not in _ATTEMPT_TRANSITIONS[attempt.state]:
        raise ValueError(f"illegal attempt transition: {attempt.state} -> {target}")
    return replace(attempt, state=target, updated_at=now)


def create_retry_attempt(
    prior_attempts: tuple[RunAttempt, ...], *, attempt_id: str, created_at: datetime
) -> RunAttempt:
    """Create an infrastructure retry against the existing scientific trial id."""

    if not prior_attempts:
        raise ValueError("a retry requires at least one prior attempt")
    trial_ids = {item.trial_id for item in prior_attempts}
    if len(trial_ids) != 1:
        raise ValueError("all attempts in a retry chain must reference one trial")
    ordered = sorted(prior_attempts, key=lambda item: item.ordinal)
    if [item.ordinal for item in ordered] != list(range(1, len(ordered) + 1)):
        raise ValueError("attempt ordinals must be contiguous from one")
    if ordered[-1].state not in {AttemptState.FAILED, AttemptState.CANCELLED}:
        raise ValueError("only failed or cancelled attempts may be retried")
    if any(
        item.state not in {AttemptState.SUCCEEDED, AttemptState.FAILED, AttemptState.CANCELLED}
        for item in ordered[:-1]
    ):
        raise ValueError("all earlier attempts must be terminal before retry")
    if created_at < (ordered[-1].updated_at or ordered[-1].created_at):
        raise ValueError("retry creation time cannot precede the prior attempt")
    if any(item.attempt_id == attempt_id for item in ordered):
        raise ValueError("attempt_id must be unique within its trial")
    return RunAttempt(
        attempt_id=attempt_id,
        trial_id=ordered[-1].trial_id,
        ordinal=len(ordered) + 1,
        state=AttemptState.QUEUED,
        created_at=created_at,
    )


def transition_forward_instance(
    instance: ForwardInstance, target: ForwardState, *, now: datetime
) -> ForwardInstance:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("forward transition time must be timezone-aware")
    if target not in _FORWARD_TRANSITIONS[instance.state]:
        raise ValueError(f"illegal forward transition: {instance.state} -> {target}")
    if now < instance.updated_at:
        raise ValueError("forward transition time cannot move backwards")
    return replace(instance, state=target, updated_at=now)


class ForwardEventDisposition(StrEnum):
    ACCEPTED = "accepted"
    GAP = "gap"
    DUPLICATE = "duplicate"
    OUT_OF_ORDER = "out_of_order"
    CORRECTION = "correction"


@dataclass(frozen=True, slots=True)
class CanonicalForwardEvent:
    event_id: str
    sequence: int
    event_time: datetime
    arrived_at: datetime
    source_digest: str
    correction_of: str | None = None

    def __post_init__(self) -> None:
        if not self.event_id.strip() or not self.source_digest.strip():
            raise ValueError("forward event identity and source digest must not be empty")
        require_sha256_digest(self.source_digest, field_name="source_digest")
        if self.correction_of is not None and not self.correction_of.strip():
            raise ValueError("correction_of must be non-empty when provided")
        if self.sequence < 0:
            raise ValueError("forward event sequence must be non-negative")
        for name in ("event_time", "arrived_at"):
            value = getattr(self, name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ForwardCursor:
    last_sequence: int = -1
    last_event_id: str | None = None
    last_event_time: datetime | None = None

    def __post_init__(self) -> None:
        if self.last_sequence < -1:
            raise ValueError("cursor sequence must be at least -1")
        if self.last_sequence == -1 and (
            self.last_event_id is not None or self.last_event_time is not None
        ):
            raise ValueError("an empty cursor cannot contain a last event")
        if self.last_sequence >= 0 and (not self.last_event_id or self.last_event_time is None):
            raise ValueError("a non-empty cursor requires the last event identity and time")
        if self.last_event_time is not None and (
            self.last_event_time.tzinfo is None or self.last_event_time.utcoffset() is None
        ):
            raise ValueError("cursor event time must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ForwardEventObservation:
    disposition: ForwardEventDisposition
    stale: bool
    missing_sequence_start: int | None
    missing_sequence_end: int | None
    correction_requires_counterfactual_replay: bool
    next_cursor: ForwardCursor
    buffer_event: bool = False


def observe_forward_event(
    cursor: ForwardCursor,
    event: CanonicalForwardEvent,
    *,
    processed_event_ids: frozenset[str] = frozenset(),
    stale_after: timedelta = timedelta(minutes=5),
) -> ForwardEventObservation:
    """Classify stream anomalies while preserving corrections as append-only work."""

    if stale_after < timedelta(0):
        raise ValueError("stale_after must not be negative")
    stale = event.arrived_at - event.event_time > stale_after
    unchanged = cursor
    if event.correction_of is not None:
        return ForwardEventObservation(
            disposition=ForwardEventDisposition.CORRECTION,
            stale=stale,
            missing_sequence_start=None,
            missing_sequence_end=None,
            correction_requires_counterfactual_replay=True,
            next_cursor=unchanged,
        )
    if event.event_id in processed_event_ids or event.event_id == cursor.last_event_id:
        return ForwardEventObservation(
            disposition=ForwardEventDisposition.DUPLICATE,
            stale=stale,
            missing_sequence_start=None,
            missing_sequence_end=None,
            correction_requires_counterfactual_replay=False,
            next_cursor=unchanged,
        )
    if event.sequence <= cursor.last_sequence or (
        cursor.last_event_time is not None and event.event_time < cursor.last_event_time
    ):
        return ForwardEventObservation(
            disposition=ForwardEventDisposition.OUT_OF_ORDER,
            stale=stale,
            missing_sequence_start=None,
            missing_sequence_end=None,
            correction_requires_counterfactual_replay=False,
            next_cursor=unchanged,
        )

    is_gap = event.sequence > cursor.last_sequence + 1
    missing_start = cursor.last_sequence + 1 if is_gap else None
    missing_end = event.sequence - 1 if is_gap else None
    next_cursor = (
        unchanged
        if is_gap
        else ForwardCursor(
            last_sequence=event.sequence,
            last_event_id=event.event_id,
            last_event_time=event.event_time,
        )
    )
    return ForwardEventObservation(
        disposition=ForwardEventDisposition.GAP if is_gap else ForwardEventDisposition.ACCEPTED,
        stale=stale,
        missing_sequence_start=missing_start,
        missing_sequence_end=missing_end,
        correction_requires_counterfactual_replay=False,
        next_cursor=next_cursor,
        buffer_event=is_gap,
    )
