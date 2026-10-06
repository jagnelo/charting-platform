"""Serial worker-capacity reservations for backtest and forward execution."""

from __future__ import annotations

import os
import socket
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


class WorkerKind(StrEnum):
    BACKTEST = "backtest"
    FORWARD = "forward"


@dataclass(frozen=True, slots=True)
class WorkerProfile:
    """One isolated process slot; scale by adding separate worker replicas."""

    worker_id: str
    kind: WorkerKind
    runtime_profile_fingerprint: str
    isolation_required: bool = True
    engine_disposal_required: bool = True
    max_concurrent_nodes: int = 1

    def __post_init__(self) -> None:
        _nonempty(self.worker_id, "worker_id")
        if not isinstance(self.kind, WorkerKind):
            raise TypeError("worker kind must be a WorkerKind")
        require_sha256_digest(
            self.runtime_profile_fingerprint, field_name="runtime_profile_fingerprint"
        )
        for name in ("isolation_required", "engine_disposal_required"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a boolean")
        if (
            not isinstance(self.max_concurrent_nodes, int)
            or isinstance(self.max_concurrent_nodes, bool)
            or self.max_concurrent_nodes != 1
        ):
            raise ValueError("each worker process must permit exactly one concurrent engine node")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def forward_worker_profile_from_environment(
    environment: Mapping[str, str] | None = None,
) -> WorkerProfile | None:
    """Resolve the shared API/worker profile identity from local environment.

    Each replica receives a process-specific id from Compose's ``HOSTNAME``
    unless an explicit id is set. The API discovers all such profiles by the
    shared runtime fingerprint, so replica scaling remains possible.
    """

    env = os.environ if environment is None else environment
    runtime_fingerprint = forward_worker_runtime_profile_fingerprint_from_environment(env)
    if runtime_fingerprint is None:
        return None
    worker_id = env.get("STRATEGY_LAB_V2_FORWARD_WORKER_ID") or env.get("HOSTNAME")
    if not worker_id:
        worker_id = f"forward-worker-{socket.gethostname()}"
    return WorkerProfile(
        worker_id=worker_id,
        kind=WorkerKind.FORWARD,
        runtime_profile_fingerprint=runtime_fingerprint,
    )


def forward_worker_runtime_profile_fingerprint_from_environment(
    environment: Mapping[str, str] | None = None,
) -> str | None:
    """Resolve the shared, immutable runtime profile fingerprint."""

    env = os.environ if environment is None else environment
    runtime_fingerprint = env.get("STRATEGY_LAB_V2_FORWARD_RUNTIME_PROFILE_FINGERPRINT")
    if runtime_fingerprint is None or not runtime_fingerprint.strip():
        return None
    require_sha256_digest(
        runtime_fingerprint,
        field_name="STRATEGY_LAB_V2_FORWARD_RUNTIME_PROFILE_FINGERPRINT",
    )
    return runtime_fingerprint


@dataclass(frozen=True, slots=True)
class WorkerReservation:
    """A pure reservation record; the adapter owns the atomic claim."""

    reservation_id: str
    worker_id: str
    kind: WorkerKind
    attempt_id: str
    acquired_at: datetime
    released_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in ("reservation_id", "worker_id", "attempt_id"):
            _nonempty(getattr(self, name), name)
        require_sha256_digest(self.reservation_id, field_name="reservation_id")
        if not isinstance(self.kind, WorkerKind):
            raise TypeError("reservation kind must be a WorkerKind")
        for name in ("acquired_at", "released_at"):
            value = getattr(self, name)
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"reservation {name} must be timezone-aware")
        acquired_at = self.acquired_at.astimezone(UTC)
        released_at = self.released_at.astimezone(UTC) if self.released_at is not None else None
        if released_at is not None and released_at < acquired_at:
            raise ValueError("reservation release cannot precede acquisition")
        object.__setattr__(self, "acquired_at", acquired_at)
        object.__setattr__(self, "released_at", released_at)

    @property
    def active(self) -> bool:
        return self.released_at is None

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class WorkerPoolState:
    profile: WorkerProfile
    reservations: tuple[WorkerReservation, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.profile, WorkerProfile):
            raise TypeError("worker pool profile must be a WorkerProfile")
        reservations = tuple(self.reservations)
        if any(not isinstance(item, WorkerReservation) for item in reservations):
            raise TypeError("reservations must contain WorkerReservation values")
        if any(
            item.worker_id != self.profile.worker_id or item.kind is not self.profile.kind
            for item in reservations
        ):
            raise ValueError("reservations must reference the pool worker and kind")
        ids = [item.reservation_id for item in reservations]
        if len(ids) != len(set(ids)):
            raise ValueError("reservation ids must be unique")
        active_attempts = [item.attempt_id for item in reservations if item.active]
        if len(active_attempts) > self.profile.max_concurrent_nodes:
            raise ValueError("worker pool exceeds its serial capacity")
        if len(active_attempts) != len(set(active_attempts)):
            raise ValueError("an attempt cannot hold multiple active worker reservations")
        object.__setattr__(
            self,
            "reservations",
            tuple(sorted(reservations, key=lambda item: item.reservation_id)),
        )

    @property
    def active_reservations(self) -> tuple[WorkerReservation, ...]:
        return tuple(item for item in self.reservations if item.active)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class WorkerReservationDecision(StrEnum):
    ACCEPT = "accept"
    REPLAY_EXISTING = "replay_existing"
    SATURATED = "saturated"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class WorkerReservationResolution:
    decision: WorkerReservationDecision
    pool: WorkerPoolState
    reservation: WorkerReservation | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, WorkerReservationDecision):
            raise TypeError("decision must be a WorkerReservationDecision")
        if not isinstance(self.pool, WorkerPoolState):
            raise TypeError("pool must be a WorkerPoolState")
        if self.reservation is not None and not isinstance(self.reservation, WorkerReservation):
            raise TypeError("reservation must be a WorkerReservation")
        if (
            self.decision
            in {
                WorkerReservationDecision.ACCEPT,
                WorkerReservationDecision.REPLAY_EXISTING,
            }
            and self.reservation is None
        ):
            raise ValueError("accepted and replay resolutions require a reservation")
        if self.decision is WorkerReservationDecision.REJECT and not self.rejection_reason:
            raise ValueError("rejected reservations require a reason")
        if self.decision is not WorkerReservationDecision.REJECT and self.rejection_reason:
            raise ValueError("non-rejected reservations cannot contain a rejection reason")


def reserve_worker_slot(
    pool: WorkerPoolState,
    *,
    attempt_id: str,
    reservation_id: str,
    acquired_at: datetime,
) -> WorkerReservationResolution:
    """Resolve a serial worker reservation without a queue or database write."""

    if not isinstance(pool, WorkerPoolState):
        raise TypeError("pool must be a WorkerPoolState")
    _nonempty(attempt_id, "attempt_id")
    require_sha256_digest(reservation_id, field_name="reservation_id")
    if acquired_at.tzinfo is None or acquired_at.utcoffset() is None:
        raise ValueError("reservation acquired_at must be timezone-aware")
    acquired_at = acquired_at.astimezone(UTC)
    if not pool.profile.isolation_required:
        return WorkerReservationResolution(
            WorkerReservationDecision.REJECT, pool, rejection_reason="worker isolation is required"
        )
    if not pool.profile.engine_disposal_required:
        return WorkerReservationResolution(
            WorkerReservationDecision.REJECT,
            pool,
            rejection_reason="engine disposal is required",
        )
    for reservation in pool.reservations:
        if reservation.reservation_id == reservation_id:
            if reservation.attempt_id != attempt_id or not reservation.active:
                return WorkerReservationResolution(
                    WorkerReservationDecision.REJECT,
                    pool,
                    rejection_reason="reservation id is already bound",
                )
            return WorkerReservationResolution(
                WorkerReservationDecision.REPLAY_EXISTING, pool, reservation
            )
    existing = next(
        (item for item in pool.active_reservations if item.attempt_id == attempt_id), None
    )
    if existing is not None:
        return WorkerReservationResolution(
            WorkerReservationDecision.REPLAY_EXISTING, pool, existing
        )
    if len(pool.active_reservations) >= pool.profile.max_concurrent_nodes:
        return WorkerReservationResolution(WorkerReservationDecision.SATURATED, pool)
    reservation = WorkerReservation(
        reservation_id=reservation_id,
        worker_id=pool.profile.worker_id,
        kind=pool.profile.kind,
        attempt_id=attempt_id,
        acquired_at=acquired_at,
    )
    return WorkerReservationResolution(
        WorkerReservationDecision.ACCEPT,
        replace(pool, reservations=pool.reservations + (reservation,)),
        reservation,
    )


def rank_available_backtest_worker_pools(
    pools: tuple[WorkerPoolState, ...] | list[WorkerPoolState],
    *,
    attempt_id: str,
) -> tuple[WorkerPoolState, ...]:
    """Rank free serial backtest slots deterministically, least-recently-used first.

    An already-reserved attempt is returned only on its existing pool so an
    idempotent replay cannot silently migrate between workers. The database
    still owns the final reservation transaction; this ranking is a dispatch
    preparation hint, not a capacity claim.
    """

    _nonempty(attempt_id, "attempt_id")
    pools = tuple(pools)
    if any(not isinstance(pool, WorkerPoolState) for pool in pools):
        raise TypeError("pools must contain WorkerPoolState values")
    worker_ids = [pool.profile.worker_id for pool in pools]
    if len(worker_ids) != len(set(worker_ids)):
        raise ValueError("worker pools must have unique profile identities")

    already_reserved = tuple(
        pool
        for pool in pools
        if any(item.active and item.attempt_id == attempt_id for item in pool.reservations)
    )
    if len(already_reserved) > 1:
        raise ValueError("an attempt cannot be reserved on multiple worker profiles")
    if already_reserved:
        pool = already_reserved[0]
        if (
            pool.profile.kind is not WorkerKind.BACKTEST
            or not pool.profile.isolation_required
            or not pool.profile.engine_disposal_required
        ):
            raise ValueError("existing attempt reservation is not on a safe backtest worker")
        return already_reserved

    available = tuple(
        pool
        for pool in pools
        if pool.profile.kind is WorkerKind.BACKTEST
        and pool.profile.isolation_required
        and pool.profile.engine_disposal_required
        and not pool.active_reservations
    )

    def rank(pool: WorkerPoolState) -> tuple[datetime, str]:
        last_used = max(
            (item.acquired_at for item in pool.reservations),
            default=datetime.min.replace(tzinfo=UTC),
        )
        stable_tie_break = content_digest(
            {
                "attempt_id": attempt_id,
                "purpose": "strategy-lab-v2-worker-profile-selection-v1",
                "worker_id": pool.profile.worker_id,
            }
        )
        return last_used, stable_tie_break

    return tuple(sorted(available, key=rank))


def rank_available_forward_worker_pools(
    pools: tuple[WorkerPoolState, ...] | list[WorkerPoolState],
    *,
    attempt_id: str,
) -> tuple[WorkerPoolState, ...]:
    """Rank idle, safe, one-node forward worker profiles deterministically."""

    _nonempty(attempt_id, "attempt_id")
    pools = tuple(pools)
    if any(not isinstance(pool, WorkerPoolState) for pool in pools):
        raise TypeError("pools must contain WorkerPoolState values")
    worker_ids = [pool.profile.worker_id for pool in pools]
    if len(worker_ids) != len(set(worker_ids)):
        raise ValueError("worker pools must have unique profile identities")
    already_reserved = tuple(
        pool
        for pool in pools
        if any(item.active and item.attempt_id == attempt_id for item in pool.reservations)
    )
    if len(already_reserved) > 1:
        raise ValueError("a forward instance cannot be reserved on multiple worker profiles")
    if already_reserved:
        pool = already_reserved[0]
        if (
            pool.profile.kind is not WorkerKind.FORWARD
            or not pool.profile.isolation_required
            or not pool.profile.engine_disposal_required
        ):
            raise ValueError("existing forward reservation is not on a safe forward worker")
        return already_reserved
    available = tuple(
        pool
        for pool in pools
        if pool.profile.kind is WorkerKind.FORWARD
        and pool.profile.isolation_required
        and pool.profile.engine_disposal_required
        and not pool.active_reservations
    )

    def rank(pool: WorkerPoolState) -> tuple[datetime, str]:
        last_used = max(
            (item.acquired_at for item in pool.reservations),
            default=datetime.min.replace(tzinfo=UTC),
        )
        stable_tie_break = content_digest(
            {
                "attempt_id": attempt_id,
                "purpose": "strategy-lab-v2-forward-worker-profile-selection-v1",
                "worker_id": pool.profile.worker_id,
            }
        )
        return last_used, stable_tie_break

    return tuple(sorted(available, key=rank))


def release_worker_slot(
    pool: WorkerPoolState,
    *,
    reservation_id: str,
    released_at: datetime,
) -> WorkerPoolState:
    """Release one reservation idempotently; adapters persist the new state."""

    if not isinstance(pool, WorkerPoolState):
        raise TypeError("pool must be a WorkerPoolState")
    require_sha256_digest(reservation_id, field_name="reservation_id")
    if released_at.tzinfo is None or released_at.utcoffset() is None:
        raise ValueError("reservation released_at must be timezone-aware")
    released_at = released_at.astimezone(UTC)
    for index, reservation in enumerate(pool.reservations):
        if reservation.reservation_id == reservation_id:
            if not reservation.active:
                return pool
            updated = replace(reservation, released_at=released_at)
            reservations = pool.reservations[:index] + (updated,) + pool.reservations[index + 1 :]
            return replace(pool, reservations=reservations)
    raise ValueError("reservation_id is not present in the worker pool")
