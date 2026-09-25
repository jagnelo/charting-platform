"""Forward-worker capacity settlement after durable handoff completion."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Protocol

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.forward_worker_authorization import (
    ForwardWorkerAuthorization,
    ForwardWorkerAuthorizationDecision,
    ForwardWorkerAuthorizationResolver,
    resolve_forward_worker_authorization,
)
from app.strategy_lab_v2.forward_worker_handoff import ForwardEventWorkItem
from app.strategy_lab_v2.lease_observations import (
    LeaseObservation,
    LeaseObservationKind,
)
from app.strategy_lab_v2.postgres_worker_state import (
    WorkerCapacityDecision,
    WorkerCapacityResolution,
)
from app.strategy_lab_v2.redis_transport import RedisStreamEntry
from app.strategy_lab_v2.worker_consumer import WorkerHandleDecision, WorkerHandleResult
from app.strategy_lab_v2.workers import WorkerProfile


class ForwardCapacityReleaseStore(Protocol):
    """Durable worker-state boundary used to release one forward slot."""

    async def release_capacity(
        self,
        *,
        profile: WorkerProfile,
        reservation_id: str,
        lease_id: str,
        observation: LeaseObservation,
    ) -> WorkerCapacityResolution: ...


ForwardReleaseObservationResolver = Callable[
    [RedisStreamEntry, ForwardEventWorkItem, ForwardWorkerAuthorization],
    Awaitable[LeaseObservation] | LeaseObservation,
]
ForwardEventHandler = Callable[
    [RedisStreamEntry, ForwardEventWorkItem],
    Awaitable[WorkerHandleResult] | WorkerHandleResult,
]


class ForwardWorkerCapacityReleaseHandler:
    """Release capacity only after the delegated forward handoff is durable."""

    def __init__(
        self,
        authorization_resolver: ForwardWorkerAuthorizationResolver,
        handler: ForwardEventHandler,
        release_store: ForwardCapacityReleaseStore,
        *,
        profile: WorkerProfile,
        observation_resolver: ForwardReleaseObservationResolver,
        clock: Callable[[], datetime],
    ) -> None:
        if not callable(authorization_resolver):
            raise TypeError("authorization_resolver must be callable")
        if not callable(handler):
            raise TypeError("handler must be callable")
        if not callable(getattr(release_store, "release_capacity", None)):
            raise TypeError("release_store must expose release_capacity")
        if not isinstance(profile, WorkerProfile):
            raise TypeError("profile must be a WorkerProfile")
        if not callable(observation_resolver):
            raise TypeError("observation_resolver must be callable")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._authorization_resolver = authorization_resolver
        self._handler = handler
        self._release_store = release_store
        self._profile = profile
        self._observation_resolver = observation_resolver
        self._clock = clock

    async def __call__(
        self, entry: RedisStreamEntry, work_item: ForwardEventWorkItem
    ) -> WorkerHandleResult:
        resolved = self._authorization_resolver(entry, work_item)
        authorization = await resolved if inspect.isawaitable(resolved) else resolved
        if not isinstance(authorization, ForwardWorkerAuthorization):
            return _reject(entry, "worker authorization resolver returned an invalid record")
        authorization_resolution = resolve_forward_worker_authorization(
            authorization,
            work_item,
            now=self._clock(),
        )
        if authorization_resolution.decision is ForwardWorkerAuthorizationDecision.EXPIRED:
            return _retry(
                entry,
                authorization_resolution.rejection_reason or "worker lease has expired",
            )
        if authorization_resolution.decision is ForwardWorkerAuthorizationDecision.REJECT:
            return _reject(
                entry,
                authorization_resolution.rejection_reason or "worker authorization rejected",
            )
        result = self._handler(entry, work_item)
        result = await result if inspect.isawaitable(result) else result
        if not isinstance(result, WorkerHandleResult):
            return _reject(entry, "forward handler returned an invalid receipt")
        if result.entry_fingerprint != entry.fingerprint:
            return _reject(entry, "forward handler receipt references a different entry")
        if result.decision is not WorkerHandleDecision.COMPLETE:
            return result
        observation_result = self._observation_resolver(entry, work_item, authorization)
        observation = (
            await observation_result
            if inspect.isawaitable(observation_result)
            else observation_result
        )
        if not isinstance(observation, LeaseObservation):
            return _retry(entry, "forward release resolver returned an invalid observation")
        if observation.kind is not LeaseObservationKind.RELEASE:
            return _reject(entry, "forward release observation must be a release")
        if observation.lease_id != authorization.lease.lease_id:
            return _reject(entry, "forward release observation lease identity does not match")
        if observation.worker_id != authorization.lease.worker_id:
            return _reject(entry, "forward release observation worker identity does not match")
        if observation.attempt_id != authorization.lease.attempt_id:
            return _reject(entry, "forward release observation attempt identity does not match")
        if observation.observed_at < authorization.reservation.acquired_at:
            return _reject(entry, "forward release observation precedes reservation acquisition")
        release = await self._release_store.release_capacity(
            profile=self._profile,
            reservation_id=authorization.reservation.reservation_id,
            lease_id=authorization.lease.lease_id,
            observation=observation,
        )
        if not isinstance(release, WorkerCapacityResolution):
            return _retry(entry, "forward release store returned an invalid resolution")
        if release.decision not in {
            WorkerCapacityDecision.RELEASED,
            WorkerCapacityDecision.REPLAY_EXISTING,
        }:
            return _retry(entry, release.rejection_reason or "forward worker capacity release failed")
        return WorkerHandleResult(
            entry.fingerprint,
            WorkerHandleDecision.COMPLETE,
            content_digest(
                {
                    "kind": "forward-worker-settlement",
                    "entry_fingerprint": entry.fingerprint,
                    "handoff_receipt": result.receipt_digest,
                    "release_fingerprint": release.fingerprint,
                }
            ),
        )


def _retry(entry: RedisStreamEntry, reason: str) -> WorkerHandleResult:
    return WorkerHandleResult(
        entry.fingerprint,
        WorkerHandleDecision.RETRY,
        rejection_reason=reason,
    )


def _reject(entry: RedisStreamEntry, reason: str) -> WorkerHandleResult:
    return WorkerHandleResult(
        entry.fingerprint,
        WorkerHandleDecision.REJECT,
        rejection_reason=reason,
    )


__all__ = [
    "ForwardCapacityReleaseStore",
    "ForwardReleaseObservationResolver",
    "ForwardWorkerCapacityReleaseHandler",
]
