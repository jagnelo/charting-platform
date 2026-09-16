"""Ordered, idempotent worker lease heartbeat and release observations."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.lifecycle import AttemptLeaseStatus, ExecutionAttemptLease


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


class LeaseObservationKind(StrEnum):
    HEARTBEAT = "heartbeat"
    RELEASE = "release"


@dataclass(frozen=True, slots=True)
class LeaseObservation:
    """One worker-owned lease observation, sequenced per lease."""

    observation_id: str
    lease_id: str
    worker_id: str
    attempt_id: str
    sequence: int
    kind: LeaseObservationKind
    observed_at: datetime
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        require_sha256_digest(self.observation_id, field_name="observation_id")
        for name in ("lease_id", "worker_id", "attempt_id"):
            _nonempty(getattr(self, name), name)
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 1:
            raise ValueError("lease observation sequence must be positive")
        if not isinstance(self.kind, LeaseObservationKind):
            raise TypeError("lease observation kind must be a LeaseObservationKind")
        _aware(self.observed_at, "observed_at")
        if self.expires_at is not None:
            _aware(self.expires_at, "expires_at")
            if self.expires_at <= self.observed_at:
                raise ValueError("lease heartbeat expiry must follow observation time")
        if self.kind is LeaseObservationKind.HEARTBEAT and self.expires_at is None:
            raise ValueError("heartbeat observations require expires_at")
        if self.kind is LeaseObservationKind.RELEASE and self.expires_at is not None:
            raise ValueError("release observations cannot contain expires_at")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class LeaseObservationState:
    """Lease plus the contiguous observations already applied to it."""

    lease: ExecutionAttemptLease
    applied_observations: tuple[LeaseObservation, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.lease, ExecutionAttemptLease):
            raise TypeError("lease must be an ExecutionAttemptLease")
        observations = tuple(self.applied_observations)
        if any(not isinstance(item, LeaseObservation) for item in observations):
            raise TypeError("applied observations must contain LeaseObservation values")
        if any(
            item.lease_id != self.lease.lease_id
            or item.worker_id != self.lease.worker_id
            or item.attempt_id != self.lease.attempt_id
            for item in observations
        ):
            raise ValueError("observations must reference the state lease")
        ordered = tuple(sorted(observations, key=lambda item: item.sequence))
        sequences = [item.sequence for item in ordered]
        if sequences != list(range(1, len(sequences) + 1)):
            raise ValueError("applied lease observation sequences must be contiguous from one")
        ids = [item.observation_id for item in ordered]
        if len(ids) != len(set(ids)):
            raise ValueError("observation ids must be unique")
        if any(item.kind is LeaseObservationKind.RELEASE for item in ordered[:-1]):
            raise ValueError("no observations may follow a release")
        if any(
            current.observed_at < previous.observed_at
            for previous, current in zip(ordered, ordered[1:])
        ):
            raise ValueError("lease observation times must be monotonic")
        heartbeat_observations = tuple(
            item for item in ordered if item.kind is LeaseObservationKind.HEARTBEAT
        )
        if heartbeat_observations:
            latest_heartbeat = heartbeat_observations[-1]
            if (
                self.lease.heartbeat_at != latest_heartbeat.observed_at
                or self.lease.expires_at != latest_heartbeat.expires_at
            ):
                raise ValueError("lease must match its latest heartbeat observation")
        if ordered and ordered[-1].kind is LeaseObservationKind.RELEASE:
            if self.lease.released_at != ordered[-1].observed_at:
                raise ValueError("released lease must match the release observation")
        object.__setattr__(self, "applied_observations", ordered)

    @property
    def last_sequence(self) -> int:
        return len(self.applied_observations)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class LeaseObservationDecision(StrEnum):
    APPLY = "apply"
    REPLAY_EXISTING = "replay_existing"
    GAP = "gap"
    STALE = "stale"
    CONFLICT = "conflict"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class LeaseObservationResolution:
    decision: LeaseObservationDecision
    state: LeaseObservationState
    expected_sequence: int
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, LeaseObservationDecision):
            raise TypeError("decision must be a LeaseObservationDecision")
        if not isinstance(self.state, LeaseObservationState):
            raise TypeError("state must be a LeaseObservationState")
        if not isinstance(self.expected_sequence, int) or isinstance(
            self.expected_sequence, bool
        ) or self.expected_sequence < 1:
            raise ValueError("expected_sequence must be a positive integer")
        requires_reason = self.decision in {
            LeaseObservationDecision.CONFLICT,
            LeaseObservationDecision.REJECT,
        }
        if requires_reason and not self.rejection_reason:
            raise ValueError("conflicts and rejections require a reason")
        if not requires_reason and self.rejection_reason:
            raise ValueError("non-error resolutions cannot contain a rejection reason")


def apply_lease_observation(
    state: LeaseObservationState, observation: LeaseObservation
) -> LeaseObservationResolution:
    """Apply one ordered heartbeat/release without mutating the prior state."""

    if not isinstance(state, LeaseObservationState):
        raise TypeError("state must be a LeaseObservationState")
    if not isinstance(observation, LeaseObservation):
        raise TypeError("observation must be a LeaseObservation")
    if (
        observation.lease_id != state.lease.lease_id
        or observation.worker_id != state.lease.worker_id
        or observation.attempt_id != state.lease.attempt_id
    ):
        return LeaseObservationResolution(
            LeaseObservationDecision.REJECT,
            state,
            state.last_sequence + 1,
            rejection_reason="observation identity does not match the lease",
        )
    existing = next(
        (item for item in state.applied_observations if item.observation_id == observation.observation_id),
        None,
    )
    if existing is not None:
        if existing.fingerprint == observation.fingerprint:
            return LeaseObservationResolution(
                LeaseObservationDecision.REPLAY_EXISTING,
                state,
                state.last_sequence + 1,
            )
        return LeaseObservationResolution(
            LeaseObservationDecision.CONFLICT,
            state,
            state.last_sequence + 1,
            rejection_reason="observation id is already bound to different content",
        )
    expected = state.last_sequence + 1
    if observation.sequence > expected:
        return LeaseObservationResolution(LeaseObservationDecision.GAP, state, expected)
    if observation.sequence < expected:
        return LeaseObservationResolution(LeaseObservationDecision.STALE, state, expected)
    status = state.lease.status_at(observation.observed_at)
    if observation.kind is LeaseObservationKind.HEARTBEAT:
        if status is not AttemptLeaseStatus.ACTIVE:
            return LeaseObservationResolution(
                LeaseObservationDecision.REJECT,
                state,
                expected,
                rejection_reason=f"cannot heartbeat a {status.value} lease",
            )
        assert observation.expires_at is not None
        next_lease = replace(
            state.lease,
            heartbeat_at=observation.observed_at,
            expires_at=observation.expires_at,
        )
    else:
        if state.lease.released_at is not None:
            return LeaseObservationResolution(
                LeaseObservationDecision.REJECT,
                state,
                expected,
                rejection_reason="lease is already released",
            )
        next_lease = state.lease.release(now=observation.observed_at)
    next_state = LeaseObservationState(
        lease=next_lease,
        applied_observations=state.applied_observations + (observation,),
    )
    return LeaseObservationResolution(
        LeaseObservationDecision.APPLY,
        next_state,
        expected,
    )
