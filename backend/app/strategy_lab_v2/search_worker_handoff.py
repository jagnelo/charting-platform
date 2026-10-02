"""Authenticated search-dispatch binding for dedicated worker handoffs.

Redis contains transport identities only.  Before a worker materializes the
execution request, this adapter rehydrates the corresponding PostgreSQL
search-dispatch record and checks every transport-visible identity against it.
The execution handoff remains engine-neutral and is still decoded by the
existing :mod:`worker_handoff` decoder.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from app.strategy_lab_v2.dispatch_payload import DispatchPayload
from app.strategy_lab_v2.postgres_search_dispatch import SearchDispatchRecord
from app.strategy_lab_v2.redis_transport import RedisStreamEntry
from app.strategy_lab_v2.worker_handoff import materialize_worker_handoff
from app.strategy_lab_v2.worker_process import WorkerExecutionRequest


class SearchDispatchRecordLoader(Protocol):
    """Worker-facing lookup contract for durable search dispatch identities."""

    async def load_by_request_fingerprint(
        self, request_fingerprint: str
    ) -> SearchDispatchRecord | None: ...


WorkerHandoffDecoder = Callable[
    [RedisStreamEntry, DispatchPayload], Awaitable[WorkerExecutionRequest]
]


class AuthenticatedSearchDispatchMaterializer:
    """Bind one Redis entry to its authenticated PostgreSQL dispatch record."""

    def __init__(
        self,
        dispatch_store: SearchDispatchRecordLoader,
        *,
        queue_name: str,
        decoder: WorkerHandoffDecoder = materialize_worker_handoff,
    ) -> None:
        if not callable(getattr(dispatch_store, "load_by_request_fingerprint", None)):
            raise TypeError(
                "dispatch_store must expose an async load_by_request_fingerprint method"
            )
        if not isinstance(queue_name, str) or not queue_name.strip():
            raise ValueError("queue_name must not be empty")
        if any(character in queue_name for character in "\x00\r\n"):
            raise ValueError("queue_name must not contain control characters")
        if not callable(decoder):
            raise TypeError("decoder must be callable")
        self._dispatch_store = dispatch_store
        self._queue_name = queue_name.strip()
        self._decoder = decoder

    @property
    def dispatch_store(self) -> SearchDispatchRecordLoader:
        return self._dispatch_store

    @property
    def queue_name(self) -> str:
        return self._queue_name

    async def __call__(
        self, entry: RedisStreamEntry, payload: DispatchPayload
    ) -> WorkerExecutionRequest:
        """Authenticate transport identities before decoding execution input."""

        if not isinstance(entry, RedisStreamEntry):
            raise TypeError("entry must be a RedisStreamEntry")
        if not isinstance(payload, DispatchPayload):
            raise TypeError("payload must be a DispatchPayload")
        record = await self._dispatch_store.load_by_request_fingerprint(entry.request_fingerprint)
        if record is None:
            raise ValueError("search dispatch record is not available")
        if not isinstance(record, SearchDispatchRecord):
            raise TypeError("dispatch store returned an invalid search dispatch record")
        request = record.request
        if request.fingerprint != entry.request_fingerprint:
            raise ValueError("Redis request identity does not match PostgreSQL dispatch")
        if request.attempt_id != entry.attempt_id:
            raise ValueError("Redis attempt identity does not match PostgreSQL dispatch")
        if request.payload_digest != entry.payload_digest:
            raise ValueError("Redis payload identity does not match PostgreSQL dispatch")
        if request.payload_digest != payload.payload_digest:
            raise ValueError("materialized payload identity does not match PostgreSQL dispatch")
        if request.queue_name != self._queue_name:
            raise ValueError("Redis queue identity does not match PostgreSQL dispatch")

        execution_request = await self._decoder(entry, payload)
        if not isinstance(execution_request, WorkerExecutionRequest):
            raise TypeError("worker handoff decoder returned an invalid request")
        _require_attempt_binding(execution_request, request.attempt_id)
        return execution_request


def _require_attempt_binding(request: WorkerExecutionRequest, attempt_id: str) -> None:
    """Ensure the decoded immutable execution request remains on the dispatch attempt."""

    bindings = (
        request.authorization.attempt_id,
        request.admission.attempt_id,
        request.runtime_request.attempt_id,
        request.runtime_state.attempt_id,
        request.lease_state.lease.attempt_id,
        request.execution_plan.attempt_id,
        request.orchestration_plan.attempt_id,
        request.runtime_input_artifact.attempt_id,
    )
    if any(value != attempt_id for value in bindings):
        raise ValueError("decoded worker handoff is bound to a different attempt")
    if request.runtime_preflight.request_fingerprint != request.runtime_request.fingerprint:
        raise ValueError("decoded worker runtime preflight is bound to different request bytes")
    if request.runtime_state.request_fingerprint != request.runtime_request.fingerprint:
        raise ValueError("decoded worker runtime state is bound to different request bytes")
    if (
        request.runtime_input_artifact.input_bundle_digest
        != request.runtime_request.input_bundle_digest
    ):
        raise ValueError(
            "decoded worker runtime input artifact is bound to different request bytes"
        )
    if request.sandbox_plan.request_fingerprint != request.runtime_request.fingerprint:
        raise ValueError("decoded worker sandbox plan is bound to different request bytes")
    expected_fingerprints = (
        (request.orchestration_plan.authorization_fingerprint, request.authorization.fingerprint),
        (request.orchestration_plan.admission_fingerprint, request.admission.fingerprint),
        (
            request.orchestration_plan.runtime_request_fingerprint,
            request.runtime_request.fingerprint,
        ),
        (
            request.orchestration_plan.runtime_preflight_fingerprint,
            request.runtime_preflight.fingerprint,
        ),
        (request.orchestration_plan.runtime_state_fingerprint, request.runtime_state.fingerprint),
        (request.orchestration_plan.sandbox_plan_fingerprint, request.sandbox_plan.fingerprint),
        (request.orchestration_plan.execution_plan_fingerprint, request.execution_plan.fingerprint),
    )
    if any(actual != expected for actual, expected in expected_fingerprints):
        raise ValueError("decoded worker orchestration fingerprints drifted")
    if request.orchestration_plan.worker_id != request.admission.worker_id:
        raise ValueError("decoded worker orchestration worker identity drifted")


def create_authenticated_search_dispatch_materializer(
    dispatch_store: SearchDispatchRecordLoader,
    *,
    queue_name: str,
    decoder: WorkerHandoffDecoder = materialize_worker_handoff,
) -> AuthenticatedSearchDispatchMaterializer:
    """Create the explicit worker callback used for search dispatch queues."""

    if not callable(getattr(dispatch_store, "load_by_request_fingerprint", None)):
        raise TypeError("dispatch_store must expose an async load_by_request_fingerprint method")
    return AuthenticatedSearchDispatchMaterializer(
        dispatch_store,
        queue_name=queue_name,
        decoder=decoder,
    )


__all__ = [
    "AuthenticatedSearchDispatchMaterializer",
    "SearchDispatchRecordLoader",
    "create_authenticated_search_dispatch_materializer",
]
