"""Durable shadow-account settlement for forward worker handoffs.

The forward engine/host resolves one authenticated work item into immutable
account effects.  This adapter validates that the effects belong to the
transport identity, persists them through the owner-scoped account store, and
only returns a completed worker receipt after the account transition is
durable.  It performs no provider, broker, or Nautilus I/O.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.forward_account import ForwardAccountEvent
from app.strategy_lab_v2.forward_worker_handoff import ForwardEventWorkItem
from app.strategy_lab_v2.postgres_forward_account import (
    ForwardAccountStateDecision,
    ForwardAccountStateResolution,
)
from app.strategy_lab_v2.redis_transport import RedisStreamEntry
from app.strategy_lab_v2.worker_consumer import WorkerHandleDecision, WorkerHandleResult


class ForwardAccountStore(Protocol):
    """Minimal durable account transition contract used by the worker."""

    async def apply(
        self, *, principal: Any, event: ForwardAccountEvent
    ) -> ForwardAccountStateResolution: ...


ForwardAccountEventResolver = Callable[
    [RedisStreamEntry, ForwardEventWorkItem],
    Awaitable[ForwardAccountEvent] | ForwardAccountEvent,
]


class ForwardAccountWorkerHandler:
    """Settle host-produced account effects before acknowledging Redis work."""

    def __init__(
        self,
        account_store: ForwardAccountStore,
        *,
        principal: Any,
        event_resolver: ForwardAccountEventResolver,
    ) -> None:
        if not callable(getattr(account_store, "apply", None)):
            raise TypeError("account_store must expose an async apply method")
        if not callable(event_resolver):
            raise TypeError("event_resolver must be callable")
        self._account_store = account_store
        self._principal = principal
        self._event_resolver = event_resolver

    @property
    def account_store(self) -> ForwardAccountStore:
        return self._account_store

    @property
    def event_resolver(self) -> ForwardAccountEventResolver:
        return self._event_resolver

    async def __call__(
        self, entry: RedisStreamEntry, work_item: ForwardEventWorkItem
    ) -> WorkerHandleResult:
        if not isinstance(entry, RedisStreamEntry):
            raise TypeError("entry must be a RedisStreamEntry")
        if not isinstance(work_item, ForwardEventWorkItem):
            raise TypeError("work_item must be a ForwardEventWorkItem")
        resolved = self._event_resolver(entry, work_item)
        event = await resolved if inspect.isawaitable(resolved) else resolved
        if not isinstance(event, ForwardAccountEvent):
            return _reject(entry, "forward account resolver returned an invalid event")
        if event.instance_id != work_item.dispatch.instance_id:
            return _reject(entry, "forward account event instance identity does not match dispatch")
        if event.event_fingerprint != work_item.payload.event_fingerprint:
            return _reject(entry, "forward account event fingerprint does not match dispatch")
        resolution = await self._account_store.apply(principal=self._principal, event=event)
        if not isinstance(resolution, ForwardAccountStateResolution):
            return _reject(entry, "forward account store returned an invalid resolution")
        if resolution.event_fingerprint != event.event_fingerprint:
            return _reject(entry, "forward account resolution identity does not match event")
        if resolution.decision in {
            ForwardAccountStateDecision.APPLIED,
            ForwardAccountStateDecision.REPLAY_EXISTING,
        }:
            return WorkerHandleResult(
                entry.fingerprint,
                WorkerHandleDecision.COMPLETE,
                content_digest(
                    {
                        "kind": "forward-account-settlement",
                        "entry_fingerprint": entry.fingerprint,
                        "work_item_fingerprint": work_item.fingerprint,
                        "account_resolution_fingerprint": resolution.fingerprint,
                    }
                ),
            )
        if resolution.decision in {
            ForwardAccountStateDecision.NOT_FOUND,
            ForwardAccountStateDecision.OUT_OF_ORDER,
        }:
            return _retry(entry, resolution.rejection_reason or resolution.decision.value)
        return _reject(entry, resolution.rejection_reason or resolution.decision.value)


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
    "ForwardAccountEventResolver",
    "ForwardAccountStore",
    "ForwardAccountWorkerHandler",
]
