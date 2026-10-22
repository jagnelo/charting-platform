"""Durable capacity and lease lifecycle for one broker-free forward instance."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.forward_worker_authorization import ForwardWorkerAuthorization
from app.strategy_lab_v2.lease_observations import (
    LeaseObservation,
    LeaseObservationDecision,
    LeaseObservationKind,
    LeaseObservationResolution,
    LeaseObservationState,
)
from app.strategy_lab_v2.lifecycle import AttemptLeaseStatus, ExecutionAttemptLease
from app.strategy_lab_v2.postgres_worker_state import (
    WorkerCapacityDecision,
    WorkerCapacityResolution,
    WorkerReservationDecision,
    WorkerReservationResolution,
)
from app.strategy_lab_v2.workers import (
    WorkerKind,
    WorkerPoolState,
    WorkerProfile,
    rank_available_forward_worker_pools,
)

FORWARD_WORKER_LEASE_DURATION = timedelta(minutes=5)
FORWARD_WORKER_HEARTBEAT_INTERVAL_SECONDS = 60.0


class ForwardWorkerLifecycleStore(Protocol):
    """Persistence operations required to acquire and release instance capacity."""

    async def ensure_profile(self, profile: WorkerProfile) -> object: ...

    async def reserve(
        self,
        *,
        profile: WorkerProfile,
        attempt_id: str,
        reservation_id: str,
        acquired_at: datetime,
    ) -> WorkerReservationResolution: ...

    async def load_forward_authorization(
        self, *, profile: WorkerProfile, reservation_id: str, lease_id: str
    ) -> ForwardWorkerAuthorization | None: ...

    async def load_forward_authorization_for_attempt(
        self, *, profile: WorkerProfile, attempt_id: str
    ) -> ForwardWorkerAuthorization | None: ...

    async def load_lease(self, lease_id: str) -> LeaseObservationState | None: ...

    async def load_pool(self, profile: WorkerProfile) -> WorkerPoolState: ...

    async def list_profiles(
        self, *, kind: WorkerKind, runtime_profile_fingerprint: str
    ) -> tuple[WorkerProfile, ...]: ...

    async def persist_lease(self, lease: ExecutionAttemptLease) -> LeaseObservationState: ...

    async def observe(
        self, *, lease_id: str, observation: LeaseObservation
    ) -> LeaseObservationResolution: ...

    async def release_capacity(
        self,
        *,
        profile: WorkerProfile,
        reservation_id: str,
        lease_id: str,
        observation: LeaseObservation,
    ) -> WorkerCapacityResolution: ...


class ForwardWorkerCapacityUnavailable(RuntimeError):
    """No matching serial worker slot can currently host this instance."""


class ForwardWorkerLifecycleCoordinator:
    """Idempotently bind one forward instance to a reserved worker process."""

    def __init__(
        self,
        store: ForwardWorkerLifecycleStore,
        *,
        profile: WorkerProfile,
        lease_duration: timedelta,
    ) -> None:
        if not isinstance(profile, WorkerProfile) or profile.kind is not WorkerKind.FORWARD:
            raise TypeError("profile must be a FORWARD WorkerProfile")
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        self._store = store
        self._profile = profile
        self._lease_duration = lease_duration

    async def heartbeat(self, *, instance_id: str, now: datetime) -> ForwardWorkerAuthorization:
        """Extend an active lease using the next durable observation sequence."""

        _validate_instance_time(instance_id, now)
        authorization = await self._store.load_forward_authorization_for_attempt(
            profile=self._profile, attempt_id=instance_id
        )
        if authorization is None:
            raise ValueError("active forward worker authorization was not found")
        self._validate_authorization(authorization, instance_id, None, now)
        lease_state = await self._store.load_lease(authorization.lease.lease_id)
        if lease_state is None:
            raise ValueError("forward worker lease observation history is unavailable")
        if lease_state.lease != authorization.lease:
            raise ValueError("forward worker lease changed during heartbeat preparation")
        sequence = lease_state.last_sequence + 1
        observed_at = now.astimezone(UTC)
        expires_at = observed_at + self._lease_duration
        observation = LeaseObservation(
            observation_id=content_digest(
                {
                    "instance_id": instance_id,
                    "lease_id": authorization.lease.lease_id,
                    "kind": LeaseObservationKind.HEARTBEAT.value,
                    "observation_sequence": sequence,
                    "observed_at": observed_at,
                    "expires_at": expires_at,
                    "purpose": "strategy-lab-v2-forward-instance-heartbeat-v1",
                }
            ),
            lease_id=authorization.lease.lease_id,
            worker_id=self._profile.worker_id,
            attempt_id=instance_id,
            sequence=sequence,
            kind=LeaseObservationKind.HEARTBEAT,
            observed_at=observed_at,
            expires_at=expires_at,
        )
        resolution = await self._store.observe(
            lease_id=authorization.lease.lease_id,
            observation=observation,
        )
        if resolution.decision not in {
            LeaseObservationDecision.APPLY,
            LeaseObservationDecision.REPLAY_EXISTING,
        }:
            raise ForwardWorkerCapacityUnavailable(
                resolution.rejection_reason or "forward worker lease heartbeat was rejected"
            )
        refreshed = ForwardWorkerAuthorization(
            authorization.reservation,
            resolution.state.lease,
            resolution.state.last_sequence,
        )
        self._validate_authorization(refreshed, instance_id, None, now)
        return refreshed

    async def heartbeat_active(self, *, now: datetime) -> tuple[ForwardWorkerAuthorization, ...]:
        """Renew every instance assigned to this one-node worker profile."""

        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("forward worker heartbeat time must be timezone-aware")
        pool = await self._store.load_pool(self._profile)
        renewed: list[ForwardWorkerAuthorization] = []
        for reservation in pool.active_reservations:
            try:
                renewed.append(await self.heartbeat(instance_id=reservation.attempt_id, now=now))
            except ValueError:
                latest_pool = await self._store.load_pool(self._profile)
                if any(
                    item.active and item.reservation_id == reservation.reservation_id
                    for item in latest_pool.reservations
                ):
                    raise
        return tuple(renewed)

    async def acquire(
        self, *, instance_id: str, activation_key: str, now: datetime
    ) -> ForwardWorkerAuthorization:
        """Reserve capacity and persist its lease before instance activation."""

        _validate_instance_time(instance_id, now)
        if not isinstance(activation_key, str) or not activation_key.strip():
            raise ValueError("activation_key must not be empty")
        reservation_id = self._reservation_id(instance_id, activation_key)
        lease_id = self._lease_id(instance_id, activation_key)
        await self._store.ensure_profile(self._profile)

        existing = await self._store.load_forward_authorization(
            profile=self._profile,
            reservation_id=reservation_id,
            lease_id=lease_id,
        )
        if existing is not None:
            self._validate_authorization(existing, instance_id, activation_key, now)
            return existing

        reservation_resolution = await self._store.reserve(
            profile=self._profile,
            attempt_id=instance_id,
            reservation_id=reservation_id,
            acquired_at=now.astimezone(UTC),
        )
        decision = getattr(reservation_resolution, "decision", None)
        reservation = getattr(reservation_resolution, "reservation", None)
        if (
            decision
            not in {
                WorkerReservationDecision.ACCEPT,
                WorkerReservationDecision.REPLAY_EXISTING,
            }
            or reservation is None
        ):
            if decision is WorkerReservationDecision.SATURATED:
                raise ForwardWorkerCapacityUnavailable("no forward worker slot is available")
            raise ValueError("forward worker reservation was rejected")
        if reservation.reservation_id != reservation_id:
            raise ValueError("forward instance already has a different active reservation")

        lease_state = await self._store.load_lease(lease_id)
        if lease_state is None:
            lease = ExecutionAttemptLease(
                attempt_id=instance_id,
                worker_id=self._profile.worker_id,
                lease_id=lease_id,
                leased_at=now,
                heartbeat_at=now,
                expires_at=now + self._lease_duration,
            )
            lease_state = await self._store.persist_lease(lease)
        lease = lease_state.lease
        authorization = ForwardWorkerAuthorization(
            reservation,
            lease,
            lease_state.last_sequence,
        )
        self._validate_authorization(authorization, instance_id, activation_key, now)
        return authorization

    async def release(self, *, instance_id: str, now: datetime) -> bool:
        """Persist a sequenced release and free the instance's worker slot."""

        _validate_instance_time(instance_id, now)
        authorization = await self._store.load_forward_authorization_for_attempt(
            profile=self._profile,
            attempt_id=instance_id,
        )
        if authorization is None:
            pool = await self._store.load_pool(self._profile)
            reservation = next(
                (
                    item
                    for item in pool.reservations
                    if item.attempt_id == instance_id and item.active
                ),
                None,
            )
            if reservation is None or not reservation.active:
                return False
            raise ValueError("forward worker reservation has no matching persisted lease")
        reservation_id = authorization.reservation.reservation_id
        lease_id = authorization.lease.lease_id
        lease_state = await self._store.load_lease(lease_id)
        if lease_state is None:
            raise ValueError("forward worker lease is unavailable for release")
        if lease_state.lease.released_at is not None:
            return False
        sequence = lease_state.last_sequence + 1
        observation = LeaseObservation(
            observation_id=content_digest(
                {
                    "instance_id": instance_id,
                    "lease_id": lease_id,
                    "kind": LeaseObservationKind.RELEASE.value,
                    "observation_sequence": sequence,
                    "observed_at": now.astimezone(UTC),
                    "purpose": "strategy-lab-v2-forward-instance-release-v1",
                }
            ),
            lease_id=lease_id,
            worker_id=self._profile.worker_id,
            attempt_id=instance_id,
            sequence=sequence,
            kind=LeaseObservationKind.RELEASE,
            observed_at=now,
        )
        resolution = await self._store.release_capacity(
            profile=self._profile,
            reservation_id=reservation_id,
            lease_id=lease_id,
            observation=observation,
        )
        decision = getattr(resolution, "decision", None)
        if decision not in {
            WorkerCapacityDecision.RELEASED,
            WorkerCapacityDecision.REPLAY_EXISTING,
        }:
            raise ValueError(
                getattr(resolution, "rejection_reason", None)
                or "forward worker capacity release was rejected"
            )
        return True

    def _reservation_id(self, instance_id: str, activation_key: str) -> str:
        return content_digest(
            {
                "instance_id": instance_id,
                "activation_key": content_digest(activation_key),
                "purpose": "strategy-lab-v2-forward-instance-reservation-v1",
                "worker_id": self._profile.worker_id,
            }
        )

    def _lease_id(self, instance_id: str, activation_key: str) -> str:
        return content_digest(
            {
                "instance_id": instance_id,
                "activation_key": content_digest(activation_key),
                "purpose": "strategy-lab-v2-forward-instance-lease-v1",
                "worker_id": self._profile.worker_id,
            }
        )

    def _validate_authorization(
        self,
        authorization: ForwardWorkerAuthorization,
        instance_id: str,
        activation_key: str | None,
        now: datetime,
    ) -> None:
        if (
            authorization.reservation.attempt_id != instance_id
            or authorization.reservation.worker_id != self._profile.worker_id
            or (
                activation_key is not None
                and authorization.reservation.reservation_id
                != self._reservation_id(instance_id, activation_key)
            )
            or authorization.lease.attempt_id != instance_id
            or authorization.lease.worker_id != self._profile.worker_id
            or (
                activation_key is not None
                and authorization.lease.lease_id != self._lease_id(instance_id, activation_key)
            )
            or not authorization.reservation.active
        ):
            raise ValueError("forward worker authorization differs from this instance")
        if authorization.lease.status_at(now) is not AttemptLeaseStatus.ACTIVE:
            raise ForwardWorkerCapacityUnavailable(
                "forward instance lease is expired or released; explicit recovery is required"
            )


class ForwardWorkerFleetLifecycleCoordinator:
    """Assign forward instances over the registered local worker replica fleet."""

    def __init__(
        self,
        store: ForwardWorkerLifecycleStore,
        *,
        runtime_profile_fingerprint: str,
        lease_duration: timedelta = FORWARD_WORKER_LEASE_DURATION,
    ) -> None:
        require_sha256_digest(
            runtime_profile_fingerprint,
            field_name="runtime_profile_fingerprint",
        )
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        self._store = store
        self._runtime_profile_fingerprint = runtime_profile_fingerprint
        self._lease_duration = lease_duration

    async def acquire(
        self, *, instance_id: str, activation_key: str, now: datetime
    ) -> ForwardWorkerAuthorization:
        _validate_instance_time(instance_id, now)
        profiles = await self._profiles()
        for profile in profiles:
            existing = await self._store.load_forward_authorization_for_attempt(
                profile=profile,
                attempt_id=instance_id,
            )
            if existing is not None:
                coordinator = self._coordinator(profile)
                coordinator._validate_authorization(existing, instance_id, None, now)
                return existing

        pools = tuple([await self._store.load_pool(profile) for profile in profiles])
        for pool in rank_available_forward_worker_pools(pools, attempt_id=instance_id):
            coordinator = self._coordinator(pool.profile)
            try:
                return await coordinator.acquire(
                    instance_id=instance_id,
                    activation_key=activation_key,
                    now=now,
                )
            except ForwardWorkerCapacityUnavailable:
                continue
        raise ForwardWorkerCapacityUnavailable("no forward worker slot is available")

    async def heartbeat(self, *, instance_id: str, now: datetime) -> ForwardWorkerAuthorization:
        _validate_instance_time(instance_id, now)
        for profile in await self._profiles():
            authorization = await self._store.load_forward_authorization_for_attempt(
                profile=profile,
                attempt_id=instance_id,
            )
            if authorization is not None:
                return await self._coordinator(profile).heartbeat(instance_id=instance_id, now=now)
        raise ForwardWorkerCapacityUnavailable("active forward worker authorization was not found")

    async def release(self, *, instance_id: str, now: datetime) -> bool:
        _validate_instance_time(instance_id, now)
        for profile in await self._profiles():
            authorization = await self._store.load_forward_authorization_for_attempt(
                profile=profile,
                attempt_id=instance_id,
            )
            if authorization is not None:
                return await self._coordinator(profile).release(instance_id=instance_id, now=now)
        return False

    async def _profiles(self) -> tuple[WorkerProfile, ...]:
        profiles = await self._store.list_profiles(
            kind=WorkerKind.FORWARD,
            runtime_profile_fingerprint=self._runtime_profile_fingerprint,
        )
        if any(
            profile.kind is not WorkerKind.FORWARD
            or profile.runtime_profile_fingerprint != self._runtime_profile_fingerprint
            for profile in profiles
        ):
            raise ValueError("worker profile discovery returned an inexact runtime match")
        return profiles

    def _coordinator(self, profile: WorkerProfile) -> ForwardWorkerLifecycleCoordinator:
        return ForwardWorkerLifecycleCoordinator(
            self._store,
            profile=profile,
            lease_duration=self._lease_duration,
        )


def _validate_instance_time(instance_id: str, now: datetime) -> None:
    if not isinstance(instance_id, str) or not instance_id.strip():
        raise ValueError("instance_id must not be empty")
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("forward worker lifecycle time must be timezone-aware")


__all__ = [
    "FORWARD_WORKER_HEARTBEAT_INTERVAL_SECONDS",
    "FORWARD_WORKER_LEASE_DURATION",
    "ForwardWorkerCapacityUnavailable",
    "ForwardWorkerLifecycleCoordinator",
    "ForwardWorkerFleetLifecycleCoordinator",
    "ForwardWorkerLifecycleStore",
]
