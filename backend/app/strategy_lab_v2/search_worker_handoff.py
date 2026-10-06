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
from app.strategy_lab_v2.nautilus_runtime_bundle import NautilusRuntimeInputArtifactReference
from app.strategy_lab_v2.nautilus_trial_assembly import strategy_runtime_identity
from app.strategy_lab_v2.postgres_search_dispatch import SearchDispatchRecord
from app.strategy_lab_v2.redis_transport import RedisStreamEntry
from app.strategy_lab_v2.runtime_execution import StrategyRuntimeRequest
from app.strategy_lab_v2.trial_hydration import HydratedNautilusTrial
from app.strategy_lab_v2.worker_handoff import materialize_worker_handoff
from app.strategy_lab_v2.worker_process import WorkerExecutionRequest


class SearchDispatchRecordLoader(Protocol):
    """Worker-facing lookup contract for durable search dispatch identities."""

    async def load_by_request_fingerprint(
        self, request_fingerprint: str
    ) -> SearchDispatchRecord | None: ...


class TrialGraphHydrator(Protocol):
    async def hydrate_attempt(
        self,
        *,
        principal: object,
        attempt_resource_id: str,
    ) -> HydratedNautilusTrial: ...


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
        domain_hydrator: TrialGraphHydrator | None = None,
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
        if domain_hydrator is not None and not callable(
            getattr(domain_hydrator, "hydrate_attempt", None)
        ):
            raise TypeError("domain_hydrator must expose hydrate_attempt()")
        self._dispatch_store = dispatch_store
        self._queue_name = queue_name.strip()
        self._decoder = decoder
        self._domain_hydrator = domain_hydrator

    @property
    def dispatch_store(self) -> SearchDispatchRecordLoader:
        return self._dispatch_store

    @property
    def queue_name(self) -> str:
        return self._queue_name

    @property
    def domain_hydrator(self) -> TrialGraphHydrator | None:
        return self._domain_hydrator

    async def __call__(
        self, entry: RedisStreamEntry, payload: DispatchPayload
    ) -> WorkerExecutionRequest:
        """Authenticate transport identities before decoding execution input."""

        if not isinstance(entry, RedisStreamEntry):
            raise TypeError("entry must be a RedisStreamEntry")
        if not isinstance(payload, DispatchPayload):
            raise TypeError("payload must be a DispatchPayload")
        payload_loader = getattr(self._dispatch_store, "load_by_payload_digest", None)
        if callable(payload_loader):
            payload_bound = True
            record = await payload_loader(entry.payload_digest)
        else:
            payload_bound = False
            record = await self._dispatch_store.load_by_request_fingerprint(
                entry.request_fingerprint
            )
        if record is None:
            raise ValueError("search dispatch record is not available")
        if not isinstance(record, SearchDispatchRecord):
            raise TypeError("dispatch store returned an invalid search dispatch record")
        request = record.request
        if not payload_bound and request.fingerprint != entry.request_fingerprint:
            raise ValueError("Redis request identity does not match PostgreSQL dispatch")
        if not payload_bound and request.attempt_id != entry.attempt_id:
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
        if self._domain_hydrator is not None:
            hydrated = await self._domain_hydrator.hydrate_attempt(
                principal=record.owner_id,
                attempt_resource_id=request.attempt_id,
            )
            _require_persisted_trial_binding(
                hydrated,
                experiment_fingerprint=record.experiment_fingerprint,
                runtime_request=execution_request.runtime_request,
                runtime_input_artifact=execution_request.runtime_input_artifact,
            )
        return execution_request


def _require_persisted_trial_binding(
    hydrated: HydratedNautilusTrial,
    *,
    experiment_fingerprint: str,
    runtime_request: StrategyRuntimeRequest,
    runtime_input_artifact: NautilusRuntimeInputArtifactReference,
) -> None:
    """Bind a decoded runtime request to the dispatch owner's persisted graph."""

    if not isinstance(hydrated, HydratedNautilusTrial):
        raise TypeError("domain hydrator returned an invalid trial graph")
    if hydrated.experiment.fingerprint != experiment_fingerprint:
        raise ValueError("search dispatch experiment differs from the owner's persisted trial")
    if not isinstance(runtime_request, StrategyRuntimeRequest):
        raise TypeError("runtime_request must be a StrategyRuntimeRequest")
    if not isinstance(runtime_input_artifact, NautilusRuntimeInputArtifactReference):
        raise TypeError("runtime_input_artifact must be a NautilusRuntimeInputArtifactReference")
    if runtime_input_artifact.input_bundle_digest != runtime_request.input_bundle_digest:
        raise ValueError("worker runtime artifact differs from the runtime request bundle")
    identity = strategy_runtime_identity(hydrated.strategies, hydrated.packages)
    if runtime_request.package_fingerprint != identity.package_fingerprint:
        raise ValueError(
            "worker runtime package is not pinned by the persisted experiment package set"
        )
    if runtime_request.source_digest != identity.source_digest:
        raise ValueError("worker runtime source differs from the persisted strategy set")
    if runtime_request.entrypoint != identity.entrypoint:
        raise ValueError("worker runtime entrypoint differs from the pinned package set")
    if runtime_request.isolation_request.dependency_digests != identity.dependency_digests:
        raise ValueError("worker runtime dependencies differ from the persisted package set")
    trial_binding = runtime_input_artifact.trial_binding
    if trial_binding is None:
        raise ValueError("worker runtime artifact is missing its persisted trial-input binding")
    expected_domain_binding = (
        runtime_request.attempt_id,
        hydrated.trial.trial_id,
        hydrated.experiment.fingerprint,
        hydrated.portfolio.fingerprint,
        hydrated.snapshot.fingerprint,
        identity.package_fingerprint,
    )
    actual_domain_binding = (
        trial_binding.attempt_id,
        trial_binding.trial_fingerprint,
        trial_binding.experiment_fingerprint,
        trial_binding.portfolio_fingerprint,
        trial_binding.snapshot_fingerprint,
        trial_binding.strategy_package_fingerprint,
    )
    if actual_domain_binding != expected_domain_binding:
        raise ValueError("worker runtime artifact differs from the persisted trial graph")


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
    domain_hydrator: TrialGraphHydrator | None = None,
) -> AuthenticatedSearchDispatchMaterializer:
    """Create the explicit worker callback used for search dispatch queues."""

    if not callable(getattr(dispatch_store, "load_by_request_fingerprint", None)):
        raise TypeError("dispatch_store must expose an async load_by_request_fingerprint method")
    return AuthenticatedSearchDispatchMaterializer(
        dispatch_store,
        queue_name=queue_name,
        decoder=decoder,
        domain_hydrator=domain_hydrator,
    )


__all__ = [
    "AuthenticatedSearchDispatchMaterializer",
    "SearchDispatchRecordLoader",
    "TrialGraphHydrator",
    "create_authenticated_search_dispatch_materializer",
]
