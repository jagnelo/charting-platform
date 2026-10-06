from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.forward_worker_authorization import ForwardWorkerAuthorization
from app.strategy_lab_v2.forward_worker_settlement import ForwardWorkerCapacityReleaseHandler
from app.strategy_lab_v2.lease_observations import (
    LeaseObservation,
    LeaseObservationKind,
    LeaseObservationResolution,
    LeaseObservationState,
    apply_lease_observation,
)
from app.strategy_lab_v2.postgres_worker_state import (
    WorkerCapacityDecision,
    WorkerCapacityResolution,
)
from app.strategy_lab_v2.tests.test_forward_worker_authorization import _authorization
from app.strategy_lab_v2.tests.test_forward_worker_service import _work
from app.strategy_lab_v2.worker_consumer import WorkerHandleDecision, WorkerHandleResult
from app.strategy_lab_v2.workers import WorkerKind, WorkerPoolState, WorkerProfile

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)


def _release_observation(authorization: ForwardWorkerAuthorization) -> LeaseObservation:
    return LeaseObservation(
        content_digest("release"),
        authorization.lease.lease_id,
        authorization.lease.worker_id,
        authorization.lease.attempt_id,
        1,
        LeaseObservationKind.RELEASE,
        NOW + timedelta(minutes=1),
    )


class ReleaseStore:
    def __init__(self, resolution: WorkerCapacityResolution) -> None:
        self.resolution = resolution
        self.calls: list[dict[str, Any]] = []

    async def release_capacity(self, **kwargs: Any) -> WorkerCapacityResolution:
        self.calls.append(kwargs)
        return self.resolution

    async def observe(self, *, lease_id: str, observation: LeaseObservation) -> Any:
        del lease_id, observation
        raise AssertionError("unexpected heartbeat observation")


def _resolution(
    authorization: ForwardWorkerAuthorization,
    observation: LeaseObservation,
    decision: WorkerCapacityDecision,
) -> WorkerCapacityResolution:
    profile = WorkerProfile("worker-1", WorkerKind.FORWARD, content_digest("runtime"))
    pool = WorkerPoolState(profile, (authorization.reservation,))
    lease_state = LeaseObservationState(authorization.lease)
    if decision is WorkerCapacityDecision.RELEASED:
        lease_state = apply_lease_observation(lease_state, observation).state
    return WorkerCapacityResolution(
        decision,
        pool,
        lease_state,
        observation,
        None if decision is WorkerCapacityDecision.RELEASED else "capacity release rejected",
    )


@pytest.mark.asyncio
async def test_forward_worker_capacity_release_follows_durable_handoff() -> None:
    entry, _, work_item = _work()
    authorization = _authorization()
    observation = _release_observation(authorization)
    store = ReleaseStore(_resolution(authorization, observation, WorkerCapacityDecision.RELEASED))

    async def handler(received_entry, _item):
        return WorkerHandleResult(
            received_entry.fingerprint,
            WorkerHandleDecision.COMPLETE,
            content_digest("handoff"),
        )

    wrapper = ForwardWorkerCapacityReleaseHandler(
        lambda _entry, _item: authorization,
        handler,
        store,
        profile=WorkerProfile("worker-1", WorkerKind.FORWARD, content_digest("runtime")),
        observation_resolver=lambda _entry, _item, _authorization: observation,
        clock=lambda: NOW + timedelta(minutes=1),
    )

    result = await wrapper(entry, work_item)

    assert result.decision is WorkerHandleDecision.COMPLETE
    assert len(store.calls) == 1
    assert store.calls[0]["observation"] == observation


@pytest.mark.asyncio
async def test_forward_worker_heartbeats_during_long_handoff_and_sequences_release() -> None:
    entry, _, work_item = _work()
    authorization = _authorization()

    class HeartbeatReleaseStore:
        def __init__(self) -> None:
            self.state = LeaseObservationState(authorization.lease)
            self.heartbeats: list[LeaseObservation] = []
            self.release: LeaseObservation | None = None

        async def observe(self, *, lease_id: str, observation: LeaseObservation):
            assert lease_id == authorization.lease.lease_id
            self.heartbeats.append(observation)
            resolution = apply_lease_observation(self.state, observation)
            self.state = resolution.state
            return LeaseObservationResolution(
                resolution.decision,
                self.state,
                resolution.expected_sequence,
                resolution.rejection_reason,
            )

        async def release_capacity(self, *, profile, reservation_id, lease_id, observation):
            assert profile.worker_id == authorization.lease.worker_id
            assert reservation_id == authorization.reservation.reservation_id
            assert lease_id == authorization.lease.lease_id
            self.release = observation
            resolution = apply_lease_observation(self.state, observation)
            self.state = resolution.state
            return WorkerCapacityResolution(
                WorkerCapacityDecision.RELEASED,
                WorkerPoolState(profile, (authorization.reservation,)),
                self.state,
                observation,
            )

    store = HeartbeatReleaseStore()
    sleep_count = 0
    clock_count = 0

    async def heartbeat_sleep(_seconds: float) -> None:
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count == 1:
            await asyncio.sleep(0)
        else:
            await asyncio.Event().wait()

    def clock() -> datetime:
        nonlocal clock_count
        clock_count += 1
        return NOW + timedelta(seconds=clock_count)

    async def handler(received_entry, _item):
        await asyncio.sleep(0.01)
        return WorkerHandleResult(
            received_entry.fingerprint,
            WorkerHandleDecision.COMPLETE,
            content_digest("long-handoff"),
        )

    def release_observation(_entry, _item, updated_authorization):
        sequence = updated_authorization.observation_sequence + 1
        observed_at = NOW + timedelta(seconds=clock_count + 1)
        return LeaseObservation(
            content_digest({"release": sequence, "at": observed_at}),
            updated_authorization.lease.lease_id,
            updated_authorization.lease.worker_id,
            updated_authorization.lease.attempt_id,
            sequence,
            LeaseObservationKind.RELEASE,
            observed_at,
        )

    wrapper = ForwardWorkerCapacityReleaseHandler(
        lambda _entry, _item: authorization,
        handler,
        store,
        profile=WorkerProfile("worker-1", WorkerKind.FORWARD, content_digest("runtime")),
        observation_resolver=release_observation,
        clock=clock,
        heartbeat_interval_seconds=0.001,
        heartbeat_extension=timedelta(seconds=20),
        sleep=heartbeat_sleep,
    )

    result = await wrapper(entry, work_item)

    assert result.decision is WorkerHandleDecision.COMPLETE
    assert len(store.heartbeats) == 1
    assert store.heartbeats[0].sequence == 1
    assert store.release is not None
    assert store.release.sequence == 2
    assert store.state.lease.released_at == store.release.observed_at


@pytest.mark.asyncio
async def test_forward_worker_capacity_release_retries_when_store_rejects() -> None:
    entry, _, work_item = _work()
    authorization = _authorization()
    observation = _release_observation(authorization)
    store = ReleaseStore(_resolution(authorization, observation, WorkerCapacityDecision.REJECT))

    async def handler(received_entry, _item):
        return WorkerHandleResult(
            received_entry.fingerprint,
            WorkerHandleDecision.COMPLETE,
            content_digest("handoff"),
        )

    wrapper = ForwardWorkerCapacityReleaseHandler(
        lambda _entry, _item: authorization,
        handler,
        store,
        profile=WorkerProfile("worker-1", WorkerKind.FORWARD, content_digest("runtime")),
        observation_resolver=lambda _entry, _item, _authorization: observation,
        clock=lambda: NOW + timedelta(minutes=1),
    )

    result = await wrapper(entry, work_item)

    assert result.decision is WorkerHandleDecision.RETRY
    assert result.rejection_reason == "capacity release rejected"
