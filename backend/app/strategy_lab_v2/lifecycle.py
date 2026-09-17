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


class AttemptLeaseStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    RELEASED = "released"


@dataclass(frozen=True, slots=True)
class ExecutionAttemptLease:
    """Worker lease metadata for one running attempt.

    Persistence and clock scheduling stay outside this module. A worker may
    renew only an active lease and must treat an expired or released lease as
    non-authoritative before publishing results.
    """

    attempt_id: str
    worker_id: str
    lease_id: str
    leased_at: datetime
    heartbeat_at: datetime
    expires_at: datetime
    released_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in ("attempt_id", "worker_id", "lease_id"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"lease {name} must not be empty")
        for name in ("leased_at", "heartbeat_at", "expires_at", "released_at"):
            value = getattr(self, name)
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"lease {name} must be timezone-aware")
        if self.heartbeat_at < self.leased_at:
            raise ValueError("lease heartbeat cannot precede lease acquisition")
        if self.expires_at <= self.heartbeat_at:
            raise ValueError("lease expiry must follow the latest heartbeat")
        if self.released_at is not None and self.released_at < self.heartbeat_at:
            raise ValueError("lease release cannot precede the latest heartbeat")

    def status_at(self, now: datetime) -> AttemptLeaseStatus:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("lease status time must be timezone-aware")
        if now < self.leased_at:
            raise ValueError("lease status time cannot precede lease acquisition")
        if self.released_at is not None and now >= self.released_at:
            return AttemptLeaseStatus.RELEASED
        return AttemptLeaseStatus.ACTIVE if now < self.expires_at else AttemptLeaseStatus.EXPIRED

    def renew(self, *, now: datetime, lease_duration: timedelta) -> ExecutionAttemptLease:
        if lease_duration <= timedelta(0):
            raise ValueError("lease duration must be positive")
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("lease heartbeat time must be timezone-aware")
        if now < self.heartbeat_at:
            raise ValueError("lease heartbeat cannot move backwards")
        if self.status_at(now) is not AttemptLeaseStatus.ACTIVE:
            raise ValueError("only an active lease can be renewed")
        return replace(self, heartbeat_at=now, expires_at=now + lease_duration)

    def release(self, *, now: datetime) -> ExecutionAttemptLease:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("lease release time must be timezone-aware")
        if now < self.heartbeat_at:
            raise ValueError("lease release cannot move backwards")
        if self.released_at is not None:
            raise ValueError("lease is already released")
        return replace(self, released_at=now)


def acquire_attempt_lease(
    attempt: RunAttempt,
    *,
    worker_id: str,
    lease_id: str,
    now: datetime,
    lease_duration: timedelta,
) -> ExecutionAttemptLease:
    """Create a lease only for a running attempt; no persistence is performed."""

    if attempt.state is not AttemptState.RUNNING:
        raise ValueError("only a running attempt can acquire a worker lease")
    if lease_duration <= timedelta(0):
        raise ValueError("lease duration must be positive")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("lease acquisition time must be timezone-aware")
    return ExecutionAttemptLease(
        attempt_id=attempt.attempt_id,
        worker_id=worker_id,
        lease_id=lease_id,
        leased_at=now,
        heartbeat_at=now,
        expires_at=now + lease_duration,
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

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, ForwardEventDisposition):
            raise TypeError("disposition must be a ForwardEventDisposition")
        if not isinstance(self.stale, bool):
            raise TypeError("stale must be a boolean")
        for name in ("missing_sequence_start", "missing_sequence_end"):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError(f"{name} must be a non-negative integer or None")
        missing_start = self.missing_sequence_start
        missing_end = self.missing_sequence_end
        if (missing_start is None) != (missing_end is None):
            raise ValueError("missing sequence bounds must be provided together")
        if (
            missing_start is not None
            and missing_end is not None
            and missing_start > missing_end
        ):
            raise ValueError("missing sequence start must not exceed its end")
        if not isinstance(self.correction_requires_counterfactual_replay, bool):
            raise TypeError("correction replay flag must be a boolean")
        if not isinstance(self.next_cursor, ForwardCursor):
            raise TypeError("next_cursor must be a ForwardCursor")
        if not isinstance(self.buffer_event, bool):
            raise TypeError("buffer_event must be a boolean")
        if self.disposition is ForwardEventDisposition.GAP:
            if missing_start is None or not self.buffer_event:
                raise ValueError("gap observations require missing bounds and buffering")
        elif missing_start is not None or self.buffer_event:
            raise ValueError("only gap observations may contain missing bounds or buffering")
        if self.disposition is ForwardEventDisposition.CORRECTION:
            if not self.correction_requires_counterfactual_replay:
                raise ValueError("correction observations require counterfactual replay")
        elif self.correction_requires_counterfactual_replay:
            raise ValueError("only correction observations may require replay")


def apply_forward_event_observation(
    instance: ForwardInstance,
    event: CanonicalForwardEvent,
    observation: ForwardEventObservation,
) -> ForwardInstance:
    """Apply one classified event without rewriting prior forward decisions.

    Only a contiguous ``ACCEPTED`` event advances the instance cursor. Gaps,
    duplicates, and out-of-order events leave it unchanged so a worker can
    buffer or audit them. Corrections increment the append-only correction
    count and never advance the decision cursor.
    """

    if not isinstance(instance, ForwardInstance):
        raise TypeError("instance must be a ForwardInstance")
    if not isinstance(event, CanonicalForwardEvent):
        raise TypeError("event must be a CanonicalForwardEvent")
    if not isinstance(observation, ForwardEventObservation):
        raise TypeError("observation must be a ForwardEventObservation")
    if observation.disposition is ForwardEventDisposition.ACCEPTED:
        if observation.next_cursor.last_sequence != event.sequence:
            raise ValueError("accepted observation cursor must end at the event sequence")
        if observation.next_cursor.last_event_id != event.event_id:
            raise ValueError("accepted observation cursor must end at the event identity")
        if instance.last_event_id is not None and event.sequence <= instance.last_event_sequence:
            raise ValueError("accepted event sequence must advance the instance cursor")
        if event.arrived_at < instance.updated_at:
            raise ValueError("event arrival time cannot move instance time backwards")
        return replace(
            instance,
            last_event_id=event.event_id,
            last_event_sequence=event.sequence,
            updated_at=event.arrived_at,
        )
    if observation.disposition is ForwardEventDisposition.CORRECTION:
        if event.correction_of is None or not observation.correction_requires_counterfactual_replay:
            raise ValueError("correction observations require counterfactual replay evidence")
        return replace(
            instance,
            correction_count=instance.correction_count + 1,
            updated_at=max(instance.updated_at, event.arrived_at),
        )
    # A non-advancing observation may still carry a richer cursor time; the
    # instance contract stores only identity/sequence, so reject accidental
    # cursor movement rather than silently dropping it.
    instance_has_event = instance.last_event_id is not None
    cursor_matches = (
        observation.next_cursor.last_event_id == instance.last_event_id
        and (
            observation.next_cursor.last_sequence == instance.last_event_sequence
            if instance_has_event
            else observation.next_cursor.last_sequence in {-1, instance.last_event_sequence}
        )
    )
    if not cursor_matches:
        raise ValueError("non-accepted observation must not advance the instance cursor")
    return instance


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
