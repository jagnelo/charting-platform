from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.forward_worker_authorization import ForwardWorkerAuthorization
from app.strategy_lab_v2.forward_worker_lifecycle import (
    ForwardWorkerCapacityUnavailable,
    ForwardWorkerFleetLifecycleCoordinator,
    ForwardWorkerLifecycleCoordinator,
)
from app.strategy_lab_v2.lease_observations import (
    LeaseObservation,
    LeaseObservationDecision,
    LeaseObservationResolution,
    LeaseObservationState,
    apply_lease_observation,
)
from app.strategy_lab_v2.lifecycle import ExecutionAttemptLease
from app.strategy_lab_v2.postgres_worker_state import (
    WorkerCapacityDecision,
    WorkerCapacityResolution,
    WorkerReservationDecision,
)
from app.strategy_lab_v2.workers import (
    WorkerKind,
    WorkerPoolState,
    WorkerProfile,
    forward_worker_profile_from_environment,
    release_worker_slot,
    reserve_worker_slot,
)

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
RUNTIME = content_digest("runtime")


class MemoryForwardWorkerStore:
    def __init__(self, profile: WorkerProfile) -> None:
        self.profile = profile
        self.pool = WorkerPoolState(profile)
        self.leases: dict[str, LeaseObservationState] = {}

    async def ensure_profile(self, profile: WorkerProfile) -> object:
        assert profile == self.profile
        return self.pool

    async def reserve(self, *, profile, attempt_id, reservation_id, acquired_at):
        resolution = reserve_worker_slot(
            self.pool,
            attempt_id=attempt_id,
            reservation_id=reservation_id,
            acquired_at=acquired_at,
        )
        if resolution.decision is WorkerReservationDecision.ACCEPT:
            self.pool = resolution.pool
        return resolution

    async def load_forward_authorization(self, *, profile, reservation_id, lease_id):
        reservation = next(
            (item for item in self.pool.reservations if item.reservation_id == reservation_id),
            None,
        )
        state = self.leases.get(lease_id)
        if reservation is None or state is None:
            return None
        return ForwardWorkerAuthorization(reservation, state.lease, state.last_sequence)

    async def load_forward_authorization_for_attempt(self, *, profile, attempt_id):
        reservations = tuple(
            item for item in self.pool.active_reservations if item.attempt_id == attempt_id
        )
        leases = tuple(
            state
            for state in self.leases.values()
            if state.lease.attempt_id == attempt_id
            and state.lease.worker_id == self.profile.worker_id
            and state.lease.released_at is None
        )
        if not reservations or not leases:
            return None
        assert len(reservations) == len(leases) == 1
        return ForwardWorkerAuthorization(reservations[0], leases[0].lease, leases[0].last_sequence)

    async def load_pool(self, profile: WorkerProfile) -> WorkerPoolState:
        assert profile == self.profile
        return self.pool

    async def list_profiles(self, *, kind, runtime_profile_fingerprint):
        assert kind is self.profile.kind
        assert runtime_profile_fingerprint == self.profile.runtime_profile_fingerprint
        return (self.profile,)

    async def load_lease(self, lease_id: str) -> LeaseObservationState | None:
        return self.leases.get(lease_id)

    async def persist_lease(self, lease: ExecutionAttemptLease) -> LeaseObservationState:
        current = self.leases.get(lease.lease_id)
        if current is not None:
            if current.lease != lease:
                raise ValueError("lease id collision")
            return current
        state = LeaseObservationState(lease)
        self.leases[lease.lease_id] = state
        return state

    async def observe(self, *, lease_id: str, observation: LeaseObservation):
        state = self.leases[lease_id]
        resolution = apply_lease_observation(state, observation)
        self.leases[lease_id] = resolution.state
        return LeaseObservationResolution(
            resolution.decision,
            resolution.state,
            resolution.expected_sequence,
            resolution.rejection_reason,
        )

    async def release_capacity(
        self, *, profile, reservation_id, lease_id, observation
    ) -> WorkerCapacityResolution:
        state = self.leases[lease_id]
        resolution = apply_lease_observation(state, observation)
        if resolution.decision is LeaseObservationDecision.APPLY:
            self.leases[lease_id] = resolution.state
            self.pool = release_worker_slot(
                self.pool,
                reservation_id=reservation_id,
                released_at=observation.observed_at,
            )
            return WorkerCapacityResolution(
                WorkerCapacityDecision.RELEASED,
                self.pool,
                resolution.state,
                observation,
            )
        return WorkerCapacityResolution(
            WorkerCapacityDecision.REJECT,
            self.pool,
            state,
            observation,
            resolution.rejection_reason or resolution.decision.value,
        )


def _coordinator(store: MemoryForwardWorkerStore) -> ForwardWorkerLifecycleCoordinator:
    return ForwardWorkerLifecycleCoordinator(
        store,
        profile=store.profile,
        lease_duration=timedelta(seconds=30),
    )


@pytest.mark.asyncio
async def test_forward_worker_lifecycle_acquires_replays_heartbeats_and_releases() -> None:
    profile = WorkerProfile("forward-worker", WorkerKind.FORWARD, RUNTIME)
    store = MemoryForwardWorkerStore(profile)
    coordinator = _coordinator(store)

    acquired = await coordinator.acquire(
        instance_id="instance-1", activation_key="activate-1", now=NOW
    )
    replay = await coordinator.acquire(
        instance_id="instance-1",
        activation_key="activate-1",
        now=NOW + timedelta(seconds=1),
    )

    assert replay == acquired
    assert acquired.reservation.active
    assert acquired.lease.expires_at == NOW + timedelta(seconds=30)

    heartbeats = await coordinator.heartbeat_active(now=NOW + timedelta(seconds=10))
    assert len(heartbeats) == 1
    renewed = heartbeats[0]
    assert renewed.observation_sequence == 1
    assert renewed.lease.expires_at == NOW + timedelta(seconds=40)

    assert await coordinator.release(instance_id="instance-1", now=NOW + timedelta(seconds=11))
    assert not store.pool.active_reservations
    assert not await coordinator.release(instance_id="instance-1", now=NOW + timedelta(seconds=12))

    resumed = await coordinator.acquire(
        instance_id="instance-1",
        activation_key="activate-2",
        now=NOW + timedelta(seconds=13),
    )
    assert resumed.reservation.reservation_id != acquired.reservation.reservation_id
    assert resumed.lease.lease_id != acquired.lease.lease_id


@pytest.mark.asyncio
async def test_forward_worker_lifecycle_fails_closed_when_serial_slot_is_busy() -> None:
    profile = WorkerProfile("forward-worker", WorkerKind.FORWARD, RUNTIME)
    store = MemoryForwardWorkerStore(profile)
    coordinator = _coordinator(store)
    await coordinator.acquire(instance_id="instance-1", activation_key="one", now=NOW)

    with pytest.raises(ForwardWorkerCapacityUnavailable, match="no forward worker slot"):
        await coordinator.acquire(
            instance_id="instance-2",
            activation_key="two",
            now=NOW + timedelta(seconds=1),
        )


def test_forward_worker_profile_environment_requires_exact_shared_identity() -> None:
    assert forward_worker_profile_from_environment({}) is None
    profile = forward_worker_profile_from_environment(
        {
            "STRATEGY_LAB_V2_FORWARD_WORKER_ID": "worker-1",
            "STRATEGY_LAB_V2_FORWARD_RUNTIME_PROFILE_FINGERPRINT": RUNTIME,
        }
    )
    assert profile == WorkerProfile("worker-1", WorkerKind.FORWARD, RUNTIME)

    replica_profile = forward_worker_profile_from_environment(
        {
            "HOSTNAME": "forward-replica-2",
            "STRATEGY_LAB_V2_FORWARD_RUNTIME_PROFILE_FINGERPRINT": RUNTIME,
        }
    )
    assert replica_profile == WorkerProfile("forward-replica-2", WorkerKind.FORWARD, RUNTIME)


@pytest.mark.asyncio
async def test_forward_worker_fleet_assigns_instances_to_separate_local_replicas() -> None:
    profile_one = WorkerProfile("forward-1", WorkerKind.FORWARD, RUNTIME)
    profile_two = WorkerProfile("forward-2", WorkerKind.FORWARD, RUNTIME)
    store_one = MemoryForwardWorkerStore(profile_one)
    store_two = MemoryForwardWorkerStore(profile_two)

    class FleetStore:
        stores = {profile_one.worker_id: store_one, profile_two.worker_id: store_two}

        async def list_profiles(self, *, kind, runtime_profile_fingerprint):
            return tuple(
                profile
                for profile in (profile_one, profile_two)
                if profile.kind is kind
                and profile.runtime_profile_fingerprint == runtime_profile_fingerprint
            )

        async def load_pool(self, profile):
            return await self.stores[profile.worker_id].load_pool(profile)

        async def ensure_profile(self, profile):
            return await self.stores[profile.worker_id].ensure_profile(profile)

        async def reserve(self, **kwargs):
            return await self.stores[kwargs["profile"].worker_id].reserve(**kwargs)

        async def load_forward_authorization(self, *, profile, reservation_id, lease_id):
            return await self.stores[profile.worker_id].load_forward_authorization(
                profile=profile,
                reservation_id=reservation_id,
                lease_id=lease_id,
            )

        async def load_forward_authorization_for_attempt(self, *, profile, attempt_id):
            return await self.stores[profile.worker_id].load_forward_authorization_for_attempt(
                profile=profile,
                attempt_id=attempt_id,
            )

        async def load_lease(self, lease_id):
            for store in self.stores.values():
                state = await store.load_lease(lease_id)
                if state is not None:
                    return state
            return None

        async def persist_lease(self, lease):
            return await self.stores[lease.worker_id].persist_lease(lease)

        async def observe(self, **kwargs):
            lease_id = kwargs["lease_id"]
            store = next(store for store in self.stores.values() if lease_id in store.leases)
            return await store.observe(**kwargs)

        async def release_capacity(self, *, profile, **kwargs):
            return await self.stores[profile.worker_id].release_capacity(
                profile=profile,
                **kwargs,
            )

    fleet_store = FleetStore()
    fleet = ForwardWorkerFleetLifecycleCoordinator(
        fleet_store,
        runtime_profile_fingerprint=RUNTIME,
        lease_duration=timedelta(seconds=30),
    )
    first = await fleet.acquire(instance_id="instance-one", activation_key="one", now=NOW)

    assigned = await fleet.acquire(
        instance_id="instance-two",
        activation_key="two",
        now=NOW + timedelta(seconds=1),
    )

    assert assigned.lease.worker_id != first.lease.worker_id
