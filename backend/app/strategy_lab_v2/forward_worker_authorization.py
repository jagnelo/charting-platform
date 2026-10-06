"""Pure authorization boundary for isolated forward workers.

Forward dispatch is allowed to run only while a dedicated ``FORWARD`` worker
reservation and its execution lease both bind the same worker and forward
instance.  Persistence owns loading these records; this module validates the
cross-aggregate identity and time boundary before a host handler can settle
account state or invoke an engine.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.forward_worker_handoff import ForwardEventWorkItem
from app.strategy_lab_v2.lifecycle import AttemptLeaseStatus, ExecutionAttemptLease
from app.strategy_lab_v2.redis_transport import RedisStreamEntry
from app.strategy_lab_v2.worker_consumer import WorkerHandleDecision, WorkerHandleResult
from app.strategy_lab_v2.workers import WorkerKind, WorkerProfile, WorkerReservation


@dataclass(frozen=True, slots=True)
class ForwardWorkerAuthorization:
    """One host-loaded reservation/lease pair for a forward work item."""

    reservation: WorkerReservation
    lease: ExecutionAttemptLease
    observation_sequence: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.reservation, WorkerReservation):
            raise TypeError("reservation must be a WorkerReservation")
        if not isinstance(self.lease, ExecutionAttemptLease):
            raise TypeError("lease must be an ExecutionAttemptLease")
        if (
            not isinstance(self.observation_sequence, int)
            or isinstance(self.observation_sequence, bool)
            or self.observation_sequence < 0
        ):
            raise ValueError("observation_sequence must be a non-negative integer")
        if self.reservation.kind is not WorkerKind.FORWARD:
            raise ValueError("forward authorization requires a FORWARD reservation")
        if self.reservation.worker_id != self.lease.worker_id:
            raise ValueError("reservation and lease worker identities do not match")
        if self.reservation.attempt_id != self.lease.attempt_id:
            raise ValueError("reservation and lease attempt identities do not match")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class ForwardWorkerAuthorizationDecision(StrEnum):
    ACCEPT = "accept"
    EXPIRED = "expired"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class ForwardWorkerAuthorizationResolution:
    decision: ForwardWorkerAuthorizationDecision
    authorization: ForwardWorkerAuthorization
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ForwardWorkerAuthorizationDecision):
            raise TypeError("decision must be a ForwardWorkerAuthorizationDecision")
        if not isinstance(self.authorization, ForwardWorkerAuthorization):
            raise TypeError("authorization must be a ForwardWorkerAuthorization")
        if self.decision is ForwardWorkerAuthorizationDecision.ACCEPT:
            if self.rejection_reason:
                raise ValueError("accepted authorization cannot contain a rejection reason")
        elif not self.rejection_reason:
            raise ValueError("rejected authorization requires a reason")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def resolve_forward_worker_authorization(
    authorization: ForwardWorkerAuthorization,
    work_item: ForwardEventWorkItem,
    *,
    now: datetime,
) -> ForwardWorkerAuthorizationResolution:
    """Validate worker kind, identity, reservation activity, and lease time."""

    if not isinstance(authorization, ForwardWorkerAuthorization):
        raise TypeError("authorization must be a ForwardWorkerAuthorization")
    if not isinstance(work_item, ForwardEventWorkItem):
        raise TypeError("work_item must be a ForwardEventWorkItem")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("authorization time must be timezone-aware")
    now = now.astimezone(UTC)
    if authorization.reservation.attempt_id != work_item.dispatch.instance_id:
        return _reject_authorization(
            authorization, "worker reservation is bound to a different forward instance"
        )
    if not authorization.reservation.active:
        return _reject_authorization(authorization, "worker reservation has been released")
    status = authorization.lease.status_at(now)
    if status is AttemptLeaseStatus.EXPIRED:
        return ForwardWorkerAuthorizationResolution(
            ForwardWorkerAuthorizationDecision.EXPIRED,
            authorization,
            "worker lease has expired",
        )
    if status is AttemptLeaseStatus.RELEASED:
        return _reject_authorization(authorization, "worker lease has been released")
    return ForwardWorkerAuthorizationResolution(
        ForwardWorkerAuthorizationDecision.ACCEPT,
        authorization,
    )


ForwardWorkerAuthorizationResolver = Callable[
    [RedisStreamEntry, ForwardEventWorkItem],
    Awaitable[ForwardWorkerAuthorization | None] | ForwardWorkerAuthorization | None,
]


class ForwardWorkerAuthorizationStore(Protocol):
    """Durable lookup for the unique active worker lease on one instance."""

    async def load_forward_authorization_for_attempt(
        self, *, profile: WorkerProfile, attempt_id: str
    ) -> ForwardWorkerAuthorization | None: ...


class DurableForwardWorkerAuthorizationResolver:
    """Resolve a dispatched instance against its persisted worker rows."""

    def __init__(self, store: ForwardWorkerAuthorizationStore, *, profile: WorkerProfile) -> None:
        if not callable(getattr(store, "load_forward_authorization_for_attempt", None)):
            raise TypeError("store must load forward authorization by attempt")
        if not isinstance(profile, WorkerProfile) or profile.kind is not WorkerKind.FORWARD:
            raise TypeError("profile must be a FORWARD WorkerProfile")
        self._store = store
        self._profile = profile

    async def __call__(
        self, entry: RedisStreamEntry, work_item: ForwardEventWorkItem
    ) -> ForwardWorkerAuthorization | None:
        if not isinstance(entry, RedisStreamEntry):
            raise TypeError("entry must be a RedisStreamEntry")
        if not isinstance(work_item, ForwardEventWorkItem):
            raise TypeError("work_item must be a ForwardEventWorkItem")
        instance_id = work_item.dispatch.instance_id
        if entry.attempt_id != instance_id:
            return None
        return await self._store.load_forward_authorization_for_attempt(
            profile=self._profile,
            attempt_id=instance_id,
        )


ForwardEventHandler = Callable[
    [RedisStreamEntry, ForwardEventWorkItem],
    Awaitable[WorkerHandleResult] | WorkerHandleResult,
]


class AuthorizedForwardEventHandler:
    """Gate a forward handler with host-loaded reservation/lease evidence."""

    def __init__(
        self,
        authorization_resolver: ForwardWorkerAuthorizationResolver,
        handler: ForwardEventHandler,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        if not callable(authorization_resolver):
            raise TypeError("authorization_resolver must be callable")
        if not callable(handler):
            raise TypeError("handler must be callable")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._authorization_resolver = authorization_resolver
        self._handler = handler
        self._clock = clock

    async def __call__(
        self, entry: RedisStreamEntry, work_item: ForwardEventWorkItem
    ) -> WorkerHandleResult:
        resolved = self._authorization_resolver(entry, work_item)
        authorization = await resolved if inspect.isawaitable(resolved) else resolved
        if authorization is None:
            return _retry(entry, "forward worker reservation/lease is not yet persisted")
        if not isinstance(authorization, ForwardWorkerAuthorization):
            return _reject(entry, "worker authorization resolver returned an invalid record")
        resolution = resolve_forward_worker_authorization(
            authorization,
            work_item,
            now=self._clock(),
        )
        if resolution.decision is ForwardWorkerAuthorizationDecision.EXPIRED:
            return _retry(entry, resolution.rejection_reason or "worker lease has expired")
        if resolution.decision is ForwardWorkerAuthorizationDecision.REJECT:
            return _reject(entry, resolution.rejection_reason or "worker authorization rejected")
        result = self._handler(entry, work_item)
        result = await result if inspect.isawaitable(result) else result
        if not isinstance(result, WorkerHandleResult):
            return _reject(entry, "forward handler returned an invalid receipt")
        if result.entry_fingerprint != entry.fingerprint:
            return _reject(entry, "forward handler receipt references a different entry")
        return result


def _reject_authorization(
    authorization: ForwardWorkerAuthorization, reason: str
) -> ForwardWorkerAuthorizationResolution:
    return ForwardWorkerAuthorizationResolution(
        ForwardWorkerAuthorizationDecision.REJECT,
        authorization,
        reason,
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
    "AuthorizedForwardEventHandler",
    "DurableForwardWorkerAuthorizationResolver",
    "ForwardWorkerAuthorization",
    "ForwardWorkerAuthorizationDecision",
    "ForwardWorkerAuthorizationResolution",
    "ForwardWorkerAuthorizationResolver",
    "ForwardWorkerAuthorizationStore",
    "resolve_forward_worker_authorization",
]
