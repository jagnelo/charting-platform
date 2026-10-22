"""Forward-worker capacity settlement after durable handoff completion."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import datetime, timedelta
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
    LeaseObservationDecision,
    LeaseObservationKind,
    LeaseObservationResolution,
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

    async def observe(
        self, *, lease_id: str, observation: LeaseObservation
    ) -> LeaseObservationResolution: ...


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
        heartbeat_interval_seconds: float = 10.0,
        heartbeat_extension: timedelta = timedelta(seconds=30),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
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
        if heartbeat_interval_seconds <= 0:
            raise ValueError("heartbeat_interval_seconds must be positive")
        if heartbeat_extension <= timedelta(0):
            raise ValueError("heartbeat_extension must be positive")
        if not callable(sleep):
            raise TypeError("sleep must be callable")
        self._authorization_resolver = authorization_resolver
        self._handler = handler
        self._release_store = release_store
        self._profile = profile
        self._observation_resolver = observation_resolver
        self._clock = clock
        self._heartbeat_interval_seconds = heartbeat_interval_seconds
        self._heartbeat_extension = heartbeat_extension
        self._sleep = sleep

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
        authorization, result, heartbeat_error = await self._handle_with_heartbeats(
            entry, work_item, authorization
        )
        if heartbeat_error is not None:
            return _retry(entry, heartbeat_error)
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
        if observation.sequence != authorization.observation_sequence + 1:
            return _retry(entry, "forward release observation sequence does not follow heartbeats")
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
            return _retry(
                entry, release.rejection_reason or "forward worker capacity release failed"
            )
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

    async def _handle_with_heartbeats(
        self,
        entry: RedisStreamEntry,
        work_item: ForwardEventWorkItem,
        authorization: ForwardWorkerAuthorization,
    ) -> tuple[ForwardWorkerAuthorization, WorkerHandleResult, str | None]:
        """Keep a delegated event's lease alive until its durable handoff ends."""

        handler_task = asyncio.create_task(self._invoke_handler(entry, work_item))
        heartbeat_task: asyncio.Task[None] | None = None
        heartbeat_error: list[str] = []
        latest = [authorization]
        observe = getattr(self._release_store, "observe", None)
        if callable(observe):
            heartbeat_task = asyncio.create_task(
                self._heartbeat_loop(latest, observe, heartbeat_error)
            )
        try:
            if heartbeat_task is None:
                return authorization, await handler_task, None
            done, _ = await asyncio.wait(
                (handler_task, heartbeat_task), return_when=asyncio.FIRST_COMPLETED
            )
            if heartbeat_task in done:
                message = (
                    heartbeat_error[0] if heartbeat_error else "worker lease heartbeat stopped"
                )
                handler_task.cancel()
                try:
                    await handler_task
                except asyncio.CancelledError:
                    pass
                return latest[0], _retry(entry, message), message
            return latest[0], await handler_task, None
        finally:
            if not handler_task.done():
                handler_task.cancel()
                try:
                    await handler_task
                except asyncio.CancelledError:
                    pass
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

    async def _invoke_handler(
        self, entry: RedisStreamEntry, work_item: ForwardEventWorkItem
    ) -> WorkerHandleResult:
        result = self._handler(entry, work_item)
        result = await result if inspect.isawaitable(result) else result
        if not isinstance(result, WorkerHandleResult):
            raise TypeError("forward handler returned an invalid receipt")
        if result.entry_fingerprint != entry.fingerprint:
            raise ValueError("forward handler receipt references a different entry")
        return result

    async def _heartbeat_loop(
        self,
        latest: list[ForwardWorkerAuthorization],
        writer: Callable[..., Awaitable[LeaseObservationResolution]],
        failures: list[str],
    ) -> None:
        while True:
            await self._sleep(self._heartbeat_interval_seconds)
            current = latest[0]
            observed_at = self._clock()
            if observed_at.tzinfo is None or observed_at.utcoffset() is None:
                failures.append("forward worker lease heartbeat clock was not timezone-aware")
                return
            observed_at = observed_at.astimezone(current.lease.heartbeat_at.tzinfo)
            expires_at = observed_at + self._heartbeat_extension
            sequence = current.observation_sequence + 1
            observation = LeaseObservation(
                observation_id=content_digest(
                    {
                        "lease_id": current.lease.lease_id,
                        "worker_id": current.lease.worker_id,
                        "attempt_id": current.lease.attempt_id,
                        "sequence": sequence,
                        "kind": LeaseObservationKind.HEARTBEAT.value,
                        "observed_at": observed_at,
                        "expires_at": expires_at,
                    }
                ),
                lease_id=current.lease.lease_id,
                worker_id=current.lease.worker_id,
                attempt_id=current.lease.attempt_id,
                sequence=sequence,
                kind=LeaseObservationKind.HEARTBEAT,
                observed_at=observed_at,
                expires_at=expires_at,
            )
            try:
                resolution = await writer(lease_id=current.lease.lease_id, observation=observation)
            except Exception as error:  # pragma: no cover - persistence boundary
                failures.append(f"forward worker lease heartbeat failed: {type(error).__name__}")
                return
            if not isinstance(resolution, LeaseObservationResolution):
                failures.append("forward worker lease heartbeat returned an invalid resolution")
                return
            if (
                resolution.expected_sequence != sequence
                or resolution.decision
                not in {
                    LeaseObservationDecision.APPLY,
                    LeaseObservationDecision.REPLAY_EXISTING,
                }
                or resolution.state.last_sequence < sequence
            ):
                failures.append("forward worker lease heartbeat was rejected or out of sequence")
                return
            latest[0] = replace(
                current,
                lease=resolution.state.lease,
                observation_sequence=resolution.state.last_sequence,
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
