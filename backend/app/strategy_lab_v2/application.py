"""Application wiring for the Strategy Lab v2 API.

The package-level router and PostgreSQL adapters deliberately remain
registration-neutral.  This module is the small application-owned seam that
connects them to the existing authenticated user dependency and async session
factory.  It does not run migrations, start workers, or import an execution
engine; those lifecycle concerns remain explicit follow-up gates.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from typing import Any

from app.strategy_lab_v2.api_contracts import ApiError, ApiErrorCode
from app.strategy_lab_v2.api_resources import (
    ApiResourceType,
    ResourceCollection,
    ResourceDocument,
)
from app.strategy_lab_v2.api_router import (
    ApiAdapterError,
    ResourceMutationServiceResult,
    StrategyLabApiAdapter,
    SubmissionServiceResult,
    create_strategy_lab_router,
)
from app.strategy_lab_v2.artifact_publication import ArtifactPublicationPlan
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capability_summary import CapabilitySummary
from app.strategy_lab_v2.commands import ExecutionCommand, ExecutionCommandResolution
from app.strategy_lab_v2.contracts import ArtifactManifest, ForwardInstance, ForwardState
from app.strategy_lab_v2.dispatch import DispatchRequest
from app.strategy_lab_v2.execution import ExecutionAuthorization
from app.strategy_lab_v2.forward_account import (
    ForwardAccountEvent,
    ForwardAccountState,
)
from app.strategy_lab_v2.forward_admission import ForwardLiveAdmissionState
from app.strategy_lab_v2.forward_corrections import ForwardCorrectionCommand
from app.strategy_lab_v2.forward_event_dispatch import ForwardEventDispatchResolution
from app.strategy_lab_v2.forward_event_transaction import ForwardEventTransactionResolution
from app.strategy_lab_v2.forward_warmup import (
    ForwardWarmupReceipt,
    ForwardWarmupResolution,
)
from app.strategy_lab_v2.forward_worker_authorization import ForwardWorkerAuthorization
from app.strategy_lab_v2.legacy import (
    LegacyCompatibilityAssessment,
    LegacyImportRequest,
    LegacyImportResolution,
)
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent, ForwardEventObservation
from app.strategy_lab_v2.outcomes import ExecutionOutcome
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.postgres_forward_account import ForwardAccountStateResolution
from app.strategy_lab_v2.postgres_forward_state import (
    ForwardInstanceResolution,
    ForwardStateMutationResolution,
)
from app.strategy_lab_v2.postgres_result_publication import PublicationStateResolution
from app.strategy_lab_v2.progress import ExecutionProgressState
from app.strategy_lab_v2.resource_domains import normalize_resource_attributes
from app.strategy_lab_v2.resource_mutations import (
    ResourceMutationDecision,
    ResourceMutationRequest,
    ResourceMutationResolution,
    create_resource_mutation_receipt,
)
from app.strategy_lab_v2.result_completion import ResultCompletionResolution
from app.strategy_lab_v2.result_publication import (
    ResultPublicationDecision,
    ResultPublicationPlan,
)
from app.strategy_lab_v2.runtime_execution import (
    RuntimeExecutionState,
    StrategyRuntimePreflight,
    StrategyRuntimeRequest,
)
from app.strategy_lab_v2.search_dispatch import SearchDispatchResolution
from app.strategy_lab_v2.search_state import (
    SearchCandidatePhase,
    SearchExecutionState,
    SearchStateResolution,
)
from app.strategy_lab_v2.storage import (
    AggregateKey,
    AggregateMutation,
    StorageTransactionDecision,
    StorageTransactionRequest,
)
from app.strategy_lab_v2.submissions import SubmissionReceipt, SubmissionRequest
from app.strategy_lab_v2.workers import WorkerProfile


@dataclass(frozen=True, slots=True)
class _PrincipalIdentity:
    """String owner identity shared by every v2 persistence adapter."""

    id: str


CapabilityPreflightResolver = Callable[
    ..., Awaitable[CapabilitySummary] | CapabilitySummary
]
SearchDispatchResolver = Callable[..., Awaitable[SearchDispatchResolution] | SearchDispatchResolution]


@dataclass(frozen=True, slots=True)
class SearchDispatchEvidence:
    """Host-owned evidence required before durable candidate dispatch."""

    authorization: ExecutionAuthorization
    runtime_request: StrategyRuntimeRequest
    runtime_preflight: StrategyRuntimePreflight
    reservation_id: str
    now: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.authorization, ExecutionAuthorization):
            raise TypeError("authorization must be an ExecutionAuthorization")
        if not isinstance(self.runtime_request, StrategyRuntimeRequest):
            raise TypeError("runtime_request must be a StrategyRuntimeRequest")
        if not isinstance(self.runtime_preflight, StrategyRuntimePreflight):
            raise TypeError("runtime_preflight must be a StrategyRuntimePreflight")
        if not isinstance(self.reservation_id, str) or not self.reservation_id.strip():
            raise ValueError("reservation_id must not be empty")
        if self.now.tzinfo is None or self.now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")


SearchDispatchEvidenceResolver = Callable[
    ..., Awaitable[SearchDispatchEvidence] | SearchDispatchEvidence
]


@dataclass(frozen=True, slots=True)
class ResultPublicationCompletionResolution:
    """Application-owned result publication and terminal completion outcome.

    Publication-plan registration is deliberately a separate durable step from
    completion.  This lets the worker evidence resolver authenticate an
    accepted plan before terminal execution while the completion adapter still
    owns its atomic artifact/completion transaction.
    """

    publication: PublicationStateResolution
    completion: ResultCompletionResolution | None

    def __post_init__(self) -> None:
        if not isinstance(self.publication, PublicationStateResolution):
            raise TypeError("publication must be a PublicationStateResolution")
        if self.completion is not None and not isinstance(
            self.completion, ResultCompletionResolution
        ):
            raise TypeError("completion must be a ResultCompletionResolution or None")


def _principal_identity(principal: Any) -> _PrincipalIdentity:
    """Convert the existing integer-backed ``User.id`` to the storage key.

    The package contracts use opaque string owner keys.  Keeping this
    conversion at the application boundary avoids leaking ORM identity types
    into the engine-neutral adapters and makes all reads/writes use the same
    representation.
    """

    value = getattr(principal, "id", principal)
    if value is None or isinstance(value, bool) or not isinstance(value, str | int):
        raise ValueError("authenticated principal identity is required")
    identity = str(value).strip()
    if not identity:
        raise ValueError("authenticated principal identity is required")
    return _PrincipalIdentity(identity)


class PostgresStrategyLabV2Adapter(StrategyLabApiAdapter):
    """Compose the v2 API operations over the additive PostgreSQL adapters."""

    def __init__(
        self,
        session_factory: Callable[[], Any],
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        capability_preflight: CapabilityPreflightResolver | None = None,
        search_dispatch: SearchDispatchResolver | None = None,
        search_dispatch_evidence: SearchDispatchEvidenceResolver | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        if not callable(clock):
            raise TypeError("clock must be callable")
        if capability_preflight is not None and not callable(capability_preflight):
            raise TypeError("capability_preflight must be callable")
        if search_dispatch is not None and not callable(search_dispatch):
            raise TypeError("search_dispatch must be callable")
        if search_dispatch_evidence is not None and not callable(search_dispatch_evidence):
            raise TypeError("search_dispatch_evidence must be callable")
        if search_dispatch is not None and search_dispatch_evidence is not None:
            raise ValueError("search_dispatch and search_dispatch_evidence are mutually exclusive")
        self._clock = clock
        self._capability_preflight = capability_preflight
        self._search_dispatch = search_dispatch
        self._search_dispatch_evidence = search_dispatch_evidence
        self._persistence = PostgresStrategyLabV2Persistence.build(session_factory, clock=clock)
        self._resources = self._persistence.resources
        self._capabilities = self._persistence.capability
        self._search_dispatch_store = self._persistence.search_dispatch
        self._submissions = self._persistence.submissions
        self._execution_state = self._persistence.execution_state
        self._commands = self._persistence.commands

    async def list_resources(
        self,
        *,
        principal: Any,
        resource_type: ApiResourceType,
        limit: int,
        cursor: Any,
        request_id: str,
    ) -> ResourceCollection:
        return await self._resources.list_resources(
            principal=_principal_identity(principal),
            resource_type=resource_type,
            limit=limit,
            cursor=cursor,
            request_id=request_id,
        )

    async def get_resource(
        self,
        *,
        principal: Any,
        resource_type: ApiResourceType,
        resource_id: str,
    ) -> ResourceDocument | None:
        return await self._resources.get_resource(
            principal=_principal_identity(principal),
            resource_type=resource_type,
            resource_id=resource_id,
        )

    async def preflight_capability(
        self,
        *,
        principal: Any,
        request_id: str,
        idempotency_key: str,
        payload: Mapping[str, Any],
        payload_digest: str,
    ) -> CapabilitySummary:
        """Resolve and durably register one application-owned capability summary.

        Provider entitlement and engine registration remain outside this module;
        the injected resolver supplies that typed result. The persistence
        adapter then authenticates and replays the immutable owner-scoped
        summary so the API response is backed by durable state.
        """

        owner = _principal_identity(principal)
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must not be empty")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValueError("idempotency_key must not be empty")
        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping")
        if not isinstance(payload_digest, str) or not payload_digest.strip():
            raise ValueError("payload_digest must not be empty")
        if self._capability_preflight is None:
            raise ApiAdapterError(
                ApiError(
                    ApiErrorCode.CAPABILITY_UNSUPPORTED,
                    "capability preflight is not configured",
                    request_id,
                    501,
                    False,
                    {"reason": "the host has not supplied a capability binding"},
                )
            )
        resolved = self._capability_preflight(
            principal=owner,
            request_id=request_id,
            idempotency_key=idempotency_key,
            payload=payload,
            payload_digest=payload_digest,
        )
        summary = await resolved if inspect.isawaitable(resolved) else resolved
        if not isinstance(summary, CapabilitySummary):
            raise TypeError("capability_preflight must return a CapabilitySummary")
        registered = await self._capabilities.ensure(principal=owner, summary=summary)
        return registered.summary

    async def initialize_search(
        self,
        *,
        principal: Any,
        request_id: str,
        idempotency_key: str,
        state: SearchExecutionState,
    ) -> SearchStateResolution:
        """Persist or replay one owner-scoped resumable search queue."""

        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must not be empty")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValueError("idempotency_key must not be empty")
        if not isinstance(state, SearchExecutionState):
            raise TypeError("state must be a SearchExecutionState")
        return await self._persistence.search_state.initialize(
            principal=_principal_identity(principal), state=state
        )

    async def cancel_search(
        self,
        *,
        principal: Any,
        request_id: str,
        idempotency_key: str,
        experiment_fingerprint: str,
        cancellation_request_id: str,
        now: datetime,
    ) -> SearchStateResolution:
        """Persist or replay cancellation for one search queue."""

        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must not be empty")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValueError("idempotency_key must not be empty")
        return await self._persistence.search_state.cancel(
            principal=_principal_identity(principal),
            experiment_fingerprint=experiment_fingerprint,
            request_id=cancellation_request_id,
            now=now,
        )

    async def start_search_candidate(
        self,
        *,
        principal: Any,
        experiment_fingerprint: str,
        candidate_index: int,
        attempt_id: str,
        now: datetime,
    ) -> SearchStateResolution:
        """Start or retry one owner-scoped search candidate."""

        if not isinstance(experiment_fingerprint, str) or not experiment_fingerprint.strip():
            raise ValueError("experiment_fingerprint must not be empty")
        if not isinstance(candidate_index, int) or isinstance(candidate_index, bool) or candidate_index < 0:
            raise ValueError("candidate_index must be a non-negative integer")
        if not isinstance(attempt_id, str) or not attempt_id.strip():
            raise ValueError("attempt_id must not be empty")
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be a timezone-aware datetime")
        return await self._persistence.search_state.start_candidate(
            principal=_principal_identity(principal),
            experiment_fingerprint=experiment_fingerprint,
            candidate_index=candidate_index,
            attempt_id=attempt_id,
            now=now.astimezone(UTC),
        )

    async def record_search_candidate_terminal(
        self,
        *,
        principal: Any,
        experiment_fingerprint: str,
        candidate_index: int,
        attempt_id: str,
        phase: SearchCandidatePhase,
        now: datetime,
        result_fingerprint: str | None = None,
    ) -> SearchStateResolution:
        """Persist one terminal search-candidate receipt with replay semantics."""

        if not isinstance(experiment_fingerprint, str) or not experiment_fingerprint.strip():
            raise ValueError("experiment_fingerprint must not be empty")
        if not isinstance(candidate_index, int) or isinstance(candidate_index, bool) or candidate_index < 0:
            raise ValueError("candidate_index must be a non-negative integer")
        if not isinstance(attempt_id, str) or not attempt_id.strip():
            raise ValueError("attempt_id must not be empty")
        if not isinstance(phase, SearchCandidatePhase):
            raise TypeError("phase must be a SearchCandidatePhase")
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be a timezone-aware datetime")
        return await self._persistence.search_state.record_terminal(
            principal=_principal_identity(principal),
            experiment_fingerprint=experiment_fingerprint,
            candidate_index=candidate_index,
            attempt_id=attempt_id,
            phase=phase,
            now=now.astimezone(UTC),
            result_fingerprint=result_fingerprint,
        )

    async def load_search_state(
        self, *, principal: Any, experiment_fingerprint: str
    ) -> SearchExecutionState | None:
        """Read one authenticated resumable search checkpoint."""

        if not isinstance(experiment_fingerprint, str) or not experiment_fingerprint.strip():
            raise ValueError("experiment_fingerprint must not be empty")
        return await self._persistence.search_state.load(
            principal=_principal_identity(principal),
            experiment_fingerprint=experiment_fingerprint,
        )

    async def dispatch_search_candidate(
        self,
        *,
        principal: Any,
        request_id: str,
        experiment_fingerprint: str,
        candidate_index: int,
        attempt_id: str,
        dispatch_request: DispatchRequest,
        payload: Mapping[str, Any],
    ) -> SearchDispatchResolution:
        """Delegate atomic candidate/admission/dispatch staging to the host.

        Constructing authorization, runtime preflight, and worker admission
        requires the application/provider boundary. The package therefore
        accepts one typed host resolver and fails closed until it is supplied;
        no partial search-state or worker mutation is attempted here.
        """

        owner = _principal_identity(principal)
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must not be empty")
        if not isinstance(experiment_fingerprint, str) or not experiment_fingerprint.strip():
            raise ValueError("experiment_fingerprint must not be empty")
        if not isinstance(candidate_index, int) or isinstance(candidate_index, bool) or candidate_index < 0:
            raise ValueError("candidate_index must be a non-negative integer")
        if not isinstance(attempt_id, str) or not attempt_id.strip():
            raise ValueError("attempt_id must not be empty")
        if not isinstance(dispatch_request, DispatchRequest):
            raise TypeError("dispatch_request must be a DispatchRequest")
        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping")
        search_dispatch_evidence = getattr(self, "_search_dispatch_evidence", None)
        if self._search_dispatch is None and search_dispatch_evidence is None:
            raise ApiAdapterError(
                ApiError(
                    ApiErrorCode.PRECONDITION_FAILED,
                    "search dispatch is not configured",
                    request_id,
                    501,
                    False,
                    {"reason": "the host has not supplied atomic worker persistence"},
                )
            )
        callback_kwargs = {
            "principal": owner,
            "request_id": request_id,
            "experiment_fingerprint": experiment_fingerprint,
            "candidate_index": candidate_index,
            "attempt_id": attempt_id,
            "dispatch_request": dispatch_request,
            "payload": payload,
        }
        if self._search_dispatch is not None:
            resolved = self._search_dispatch(**callback_kwargs)
            resolution = await resolved if inspect.isawaitable(resolved) else resolved
            if not isinstance(resolution, SearchDispatchResolution):
                raise TypeError("search_dispatch must return a SearchDispatchResolution")
            return resolution
        evidence_resolver = search_dispatch_evidence
        if evidence_resolver is None:  # pragma: no cover - guarded above
            raise AssertionError("search dispatch evidence resolver unexpectedly missing")
        evidence_result = evidence_resolver(**callback_kwargs)
        evidence = await evidence_result if inspect.isawaitable(evidence_result) else evidence_result
        if not isinstance(evidence, SearchDispatchEvidence):
            raise TypeError("search_dispatch_evidence must return SearchDispatchEvidence")
        return await self._search_dispatch_store.dispatch(
            principal=owner,
            experiment_fingerprint=experiment_fingerprint,
            candidate_index=candidate_index,
            attempt_id=attempt_id,
            authorization=evidence.authorization,
            runtime_request=evidence.runtime_request,
            runtime_preflight=evidence.runtime_preflight,
            reservation_id=evidence.reservation_id,
            dispatch_request=dispatch_request,
            payload=payload,
            now=evidence.now,
        )

    async def create_resource(
        self,
        *,
        principal: Any,
        request_id: str,
        request: ResourceMutationRequest,
    ) -> ResourceMutationServiceResult:
        """Persist one generic resource envelope through aggregate CAS storage.

        Domain-specific validation remains owned by future command adapters.
        This bridge nevertheless supplies a durable owner-bound create/replay
        boundary for the registration-neutral API resource envelope.
        """

        owner = _principal_identity(principal)
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must not be empty")
        if not isinstance(request, ResourceMutationRequest):
            raise TypeError("request must be a ResourceMutationRequest")
        attributes = request.payload.get("attributes")
        relationships = request.payload.get("relationships", {})
        meta = request.payload.get("meta", {})
        if not isinstance(attributes, Mapping):
            raise ValueError("resource attributes must be a mapping")
        if not isinstance(relationships, Mapping) or not isinstance(meta, Mapping):
            raise ValueError("resource relationships and meta must be mappings")
        normalized_domain = normalize_resource_attributes(request.resource_type, attributes)
        attributes = normalized_domain.attributes
        state_meta = dict(meta)
        if normalized_domain.domain_fingerprint is not None:
            declared_domain_fingerprint = state_meta.get("domain_fingerprint")
            if (
                declared_domain_fingerprint is not None
                and declared_domain_fingerprint != normalized_domain.domain_fingerprint
            ):
                raise ValueError("resource meta domain_fingerprint does not match its attributes")
            state_meta["domain_fingerprint"] = normalized_domain.domain_fingerprint
        requested_id = attributes.get("resource_id", attributes.get("id"))
        if requested_id is not None and (
            not isinstance(requested_id, str) or not requested_id.strip()
        ):
            raise ValueError("resource_id must be a non-empty string when supplied")
        resource_identity_payload: dict[str, Any] = {
            "resource_type": request.resource_type,
            "attributes": attributes,
        }
        if normalized_domain.domain_fingerprint is None:
            resource_identity_payload.update({"relationships": relationships, "meta": meta})
        resource_id = requested_id or content_digest(resource_identity_payload)
        aggregate_key = AggregateKey(request.resource_type.value, resource_id)
        existing = await self._persistence.aggregate_store.get(aggregate_key)
        existing_state = existing.state if existing is not None else None
        replaying_known_mutation = (
            isinstance(existing_state, Mapping)
            and str(existing_state.get("owner_id")) == owner.id
            and existing_state.get("mutation_fingerprint") == request.fingerprint
        )
        if replaying_known_mutation:
            accepted_at = existing_state.get("mutation_accepted_at")
            if not isinstance(accepted_at, datetime):
                return ResourceMutationServiceResult(
                    ResourceMutationResolution(
                        ResourceMutationDecision.REJECT,
                        request.fingerprint,
                        rejection_reason=(
                            "replayed resource aggregate is missing its accepted timestamp"
                        ),
                    )
                )
            if accepted_at.tzinfo is None or accepted_at.utcoffset() is None:
                return ResourceMutationServiceResult(
                    ResourceMutationResolution(
                        ResourceMutationDecision.REJECT,
                        request.fingerprint,
                        rejection_reason=(
                            "replayed resource aggregate has an invalid accepted timestamp"
                        ),
                    )
                )
            accepted_at = accepted_at.astimezone(UTC)
        else:
            accepted_at = self._clock()
            if not isinstance(accepted_at, datetime):
                raise TypeError("clock must return a datetime")
            if accepted_at.tzinfo is None or accepted_at.utcoffset() is None:
                raise ValueError("clock must return a timezone-aware datetime")
            accepted_at = accepted_at.astimezone(UTC)
            if accepted_at < request.requested_at:
                raise ValueError("clock cannot precede the mutation request")
        state = {
            "owner_id": owner.id,
            "resource_type": request.resource_type.value,
            "resource_id": resource_id,
            "schema_version": 1,
            "sort_value": resource_id,
            "mutation_fingerprint": request.fingerprint,
            "domain_fingerprint": normalized_domain.domain_fingerprint,
            # Keep the response timestamp in the aggregate so a replay can
            # reconstruct the exact durable receipt after a process restart.
            "mutation_accepted_at": accepted_at,
            "attributes": attributes,
            "relationships": relationships,
            "meta": state_meta,
        }
        storage_request_id = content_digest(
            {
                "idempotency_key": request.idempotency_key,
                "resource_type": request.resource_type,
                "owner_id": owner.id,
            }
        )
        storage_request = StorageTransactionRequest(
            storage_request_id,
            (
                AggregateMutation(
                    aggregate_key,
                    state,
                ),
            ),
        )
        resolved = await self._persistence.aggregate_store.apply(storage_request)
        committed = next(
            (
                aggregate
                for aggregate in resolved.aggregates
                if aggregate.key == aggregate_key
            ),
            None,
        )
        if committed is None:
            return ResourceMutationServiceResult(
                ResourceMutationResolution(
                    ResourceMutationDecision.REJECT,
                    request.fingerprint,
                    rejection_reason=resolved.rejection_reason
                    or "resource mutation did not return a committed aggregate",
                )
            )
        aggregate_state = committed.state
        if not isinstance(aggregate_state, Mapping):
            return ResourceMutationServiceResult(
                ResourceMutationResolution(
                    ResourceMutationDecision.REJECT,
                    request.fingerprint,
                    rejection_reason="resource aggregate state is not a mapping",
                )
            )
        if str(aggregate_state.get("owner_id")) != owner.id:
            return ResourceMutationServiceResult(
                ResourceMutationResolution(
                    ResourceMutationDecision.REJECT,
                    request.fingerprint,
                    rejection_reason="resource aggregate is owned by another principal",
                )
            )
        document = self._resources._project(committed, request.resource_type)
        if resolved.decision is StorageTransactionDecision.APPLY:
            receipt = create_resource_mutation_receipt(
                request,
                document,
                accepted_at=accepted_at,
            )
            return ResourceMutationServiceResult(
                ResourceMutationResolution(
                    ResourceMutationDecision.ACCEPT,
                    request.fingerprint,
                ),
                receipt,
            )
        if resolved.decision is StorageTransactionDecision.REPLAY_EXISTING:
            persisted_accepted_at = aggregate_state.get("mutation_accepted_at")
            if not isinstance(persisted_accepted_at, datetime):
                return ResourceMutationServiceResult(
                    ResourceMutationResolution(
                        ResourceMutationDecision.REJECT,
                        request.fingerprint,
                        rejection_reason=(
                            "replayed resource aggregate is missing its accepted timestamp"
                        ),
                    )
                )
            receipt = create_resource_mutation_receipt(
                request,
                document,
                accepted_at=persisted_accepted_at,
            )
            return ResourceMutationServiceResult(
                ResourceMutationResolution(
                    ResourceMutationDecision.REPLAY_EXISTING,
                    request.fingerprint,
                    receipt,
                ),
                receipt,
            )
        return ResourceMutationServiceResult(
            ResourceMutationResolution(
                ResourceMutationDecision.REJECT,
                request.fingerprint,
                rejection_reason=resolved.rejection_reason
                or "resource mutation conflicts with existing state",
            )
        )

    async def submit(
        self,
        *,
        principal: Any,
        request_id: str,
        request: SubmissionRequest,
        payload: Mapping[str, Any],
    ) -> SubmissionServiceResult:
        return await self._submissions.submit(
            principal=_principal_identity(principal),
            request_id=request_id,
            request=request,
            payload=payload,
        )

    async def command(
        self,
        *,
        principal: Any,
        request_id: str,
        idempotency_key: str,
        command: ExecutionCommand,
    ) -> ExecutionCommandResolution:
        return await self._commands.command(
            principal=_principal_identity(principal),
            request_id=request_id,
            idempotency_key=idempotency_key,
            command=command,
        )

    async def import_legacy(
        self,
        *,
        principal: Any,
        request_id: str,
        request: LegacyImportRequest,
        assessment: LegacyCompatibilityAssessment,
    ) -> LegacyImportResolution:
        """Preserve and assess one owner-scoped legacy record."""

        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must not be empty")
        return await self._persistence.legacy_imports.import_record(
            principal=_principal_identity(principal),
            request=request,
            assessment=assessment,
        )

    async def register_forward_instance(
        self, *, principal: Any, instance: ForwardInstance
    ) -> ForwardInstanceResolution:
        """Register or replay one authenticated broker-free forward instance."""

        if not isinstance(instance, ForwardInstance):
            raise TypeError("instance must be a ForwardInstance")
        return await self._persistence.forward_state.ensure_instance(
            principal=_principal_identity(principal), instance=instance
        )

    async def load_forward_instance(
        self, *, principal: Any, instance_id: str
    ) -> ForwardInstance | None:
        """Read one authenticated forward-instance definition."""

        if not isinstance(instance_id, str) or not instance_id.strip():
            raise ValueError("instance_id must not be empty")
        return await self._persistence.forward_state.load_instance(
            principal=_principal_identity(principal), instance_id=instance_id
        )

    async def load_forward_state(
        self, *, principal: Any, instance_id: str
    ) -> ForwardLiveAdmissionState | None:
        """Read one restart-safe live admission checkpoint with event identities."""

        if not isinstance(instance_id, str) or not instance_id.strip():
            raise ValueError("instance_id must not be empty")
        return await self._persistence.forward_state.load_state(
            principal=_principal_identity(principal), instance_id=instance_id
        )

    async def transition_forward_instance(
        self,
        *,
        principal: Any,
        instance_id: str,
        target: ForwardState,
        now: datetime,
    ) -> ForwardStateMutationResolution:
        """Apply one owner-scoped forward lifecycle transition."""

        if not isinstance(instance_id, str) or not instance_id.strip():
            raise ValueError("instance_id must not be empty")
        if not isinstance(target, ForwardState):
            raise TypeError("target must be a ForwardState")
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be a timezone-aware datetime")
        return await self._persistence.forward_state.transition(
            principal=_principal_identity(principal),
            instance_id=instance_id,
            target=target,
            now=now.astimezone(UTC),
        )

    async def complete_forward_warmup(
        self, *, principal: Any, receipt: ForwardWarmupReceipt
    ) -> ForwardWarmupResolution:
        """Persist the one-time warm-up receipt for an authenticated instance."""

        if not isinstance(receipt, ForwardWarmupReceipt):
            raise TypeError("receipt must be a ForwardWarmupReceipt")
        return await self._persistence.forward_state.complete_warmup(
            principal=_principal_identity(principal), receipt=receipt
        )

    async def transact_forward_event(
        self,
        *,
        principal: Any,
        instance_id: str,
        event: CanonicalForwardEvent,
        observation: ForwardEventObservation,
        correction_command: ForwardCorrectionCommand | None = None,
    ) -> ForwardEventTransactionResolution:
        """Atomically admit a canonical event and optional correction replay."""

        if not isinstance(instance_id, str) or not instance_id.strip():
            raise ValueError("instance_id must not be empty")
        if not isinstance(event, CanonicalForwardEvent):
            raise TypeError("event must be a CanonicalForwardEvent")
        if not isinstance(observation, ForwardEventObservation):
            raise TypeError("observation must be a ForwardEventObservation")
        if correction_command is not None and not isinstance(
            correction_command, ForwardCorrectionCommand
        ):
            raise TypeError("correction_command must be a ForwardCorrectionCommand")
        return await self._persistence.forward_state.transact(
            principal=_principal_identity(principal),
            instance_id=instance_id,
            event=event,
            observation=observation,
            correction_command=correction_command,
        )

    async def dispatch_forward_event(
        self,
        *,
        principal: Any,
        instance_id: str,
        event: CanonicalForwardEvent,
        observation: ForwardEventObservation,
        dispatch_request: DispatchRequest,
        payload: Mapping[str, Any],
        correction_command: ForwardCorrectionCommand | None = None,
    ) -> ForwardEventDispatchResolution:
        """Atomically stage forward admission, payload, dispatch, and outbox evidence."""

        if not isinstance(instance_id, str) or not instance_id.strip():
            raise ValueError("instance_id must not be empty")
        if not isinstance(event, CanonicalForwardEvent):
            raise TypeError("event must be a CanonicalForwardEvent")
        if not isinstance(observation, ForwardEventObservation):
            raise TypeError("observation must be a ForwardEventObservation")
        if not isinstance(dispatch_request, DispatchRequest):
            raise TypeError("dispatch_request must be a DispatchRequest")
        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping")
        if correction_command is not None and not isinstance(
            correction_command, ForwardCorrectionCommand
        ):
            raise TypeError("correction_command must be a ForwardCorrectionCommand")
        return await self._persistence.forward_dispatch.dispatch(
            principal=_principal_identity(principal),
            instance_id=instance_id,
            event=event,
            observation=observation,
            dispatch_request=dispatch_request,
            payload=payload,
            correction_command=correction_command,
        )

    async def initialize_forward_account(
        self, *, principal: Any, state: ForwardAccountState
    ) -> ForwardAccountStateResolution:
        """Register or replay one owner-scoped broker-free shadow account."""

        if not isinstance(state, ForwardAccountState):
            raise TypeError("state must be a ForwardAccountState")
        return await self._persistence.forward_account.initialize(
            principal=_principal_identity(principal), state=state
        )

    async def load_forward_account(
        self, *, principal: Any, instance_id: str
    ) -> ForwardAccountState | None:
        """Read one authenticated forward shadow account."""

        if not isinstance(instance_id, str) or not instance_id.strip():
            raise ValueError("instance_id must not be empty")
        return await self._persistence.forward_account.load(
            principal=_principal_identity(principal), instance_id=instance_id
        )

    async def load_forward_worker_authorization(
        self,
        *,
        profile: WorkerProfile,
        reservation_id: str,
        lease_id: str,
    ) -> ForwardWorkerAuthorization | None:
        """Load the reservation/lease pair used by the forward-worker gate."""

        if not isinstance(profile, WorkerProfile):
            raise TypeError("profile must be a WorkerProfile")
        if not isinstance(reservation_id, str) or not reservation_id.strip():
            raise ValueError("reservation_id must not be empty")
        if not isinstance(lease_id, str) or not lease_id.strip():
            raise ValueError("lease_id must not be empty")
        pool = await self._persistence.worker_state.load_pool(profile)
        reservation = next(
            (item for item in pool.reservations if item.reservation_id == reservation_id),
            None,
        )
        lease_state = await self._persistence.worker_state.load_lease(lease_id)
        if reservation is None or lease_state is None:
            return None
        return ForwardWorkerAuthorization(reservation, lease_state.lease)

    async def apply_forward_account_event(
        self, *, principal: Any, event: ForwardAccountEvent
    ) -> ForwardAccountStateResolution:
        """Persist one idempotent engine-produced forward account observation."""

        if not isinstance(event, ForwardAccountEvent):
            raise TypeError("event must be a ForwardAccountEvent")
        return await self._persistence.forward_account.apply(
            principal=_principal_identity(principal), event=event
        )

    async def publish_and_complete_result(
        self,
        *,
        principal: Any,
        submission: SubmissionReceipt,
        runtime_state: RuntimeExecutionState,
        outcome: ExecutionOutcome,
        progress: ExecutionProgressState,
        publication: ResultPublicationPlan,
        artifact_plans: Sequence[ArtifactPublicationPlan],
        completed_at: datetime,
        result_artifacts: Sequence[ArtifactManifest] | None = None,
    ) -> ResultPublicationCompletionResolution:
        """Register authenticated publication evidence and complete a result.

        The publication adapter is intentionally called first: worker terminal
        evidence can subsequently load the immutable plan by owner and
        attempt.  Accepted plans then flow into the PostgreSQL completion
        adapter, which atomically commits artifact ledgers and the completion
        receipt.  Rejected plans are durably recorded but cannot enter the
        successful completion path.
        """

        if not isinstance(submission, SubmissionReceipt):
            raise TypeError("submission must be a SubmissionReceipt")
        if not isinstance(runtime_state, RuntimeExecutionState):
            raise TypeError("runtime_state must be a RuntimeExecutionState")
        if not isinstance(outcome, ExecutionOutcome):
            raise TypeError("outcome must be an ExecutionOutcome")
        if not isinstance(progress, ExecutionProgressState):
            raise TypeError("progress must be an ExecutionProgressState")
        if not isinstance(publication, ResultPublicationPlan):
            raise TypeError("publication must be a ResultPublicationPlan")
        plans = tuple(artifact_plans)
        if any(not isinstance(item, ArtifactPublicationPlan) for item in plans):
            raise TypeError("artifact_plans must contain ArtifactPublicationPlan values")
        if result_artifacts is not None:
            artifacts = tuple(result_artifacts)
            if any(not isinstance(item, ArtifactManifest) for item in artifacts):
                raise TypeError("result_artifacts must contain ArtifactManifest values")
            result_artifacts = artifacts
        if not isinstance(completed_at, datetime):
            raise TypeError("completed_at must be a datetime")
        if completed_at.tzinfo is None or completed_at.utcoffset() is None:
            raise ValueError("completed_at must be timezone-aware")
        owner = _principal_identity(principal)
        registered = await self._persistence.result_publication.ensure(
            principal=owner, plan=publication
        )
        if registered.plan.decision is ResultPublicationDecision.REJECT:
            return ResultPublicationCompletionResolution(registered, None)
        completion = await self._persistence.result_completion.finalize(
            principal=owner,
            submission=submission,
            runtime_state=runtime_state,
            outcome=outcome,
            progress=progress,
            publication=registered.plan,
            artifact_plans=plans,
            completed_at=completed_at.astimezone(UTC),
            result_artifacts=result_artifacts,
        )
        return ResultPublicationCompletionResolution(registered, completion)


_default_adapter: PostgresStrategyLabV2Adapter | None = None


def get_strategy_lab_v2_adapter() -> StrategyLabApiAdapter:
    """FastAPI dependency returning the process-local v2 adapter."""

    global _default_adapter
    if _default_adapter is None:
        # Keep the package import-safe for contract tests and worker tooling;
        # the application graph is resolved only when FastAPI asks for the
        # registered dependency.
        session_factory = getattr(import_module("app.database"), "AsyncSessionLocal")
        _default_adapter = PostgresStrategyLabV2Adapter(session_factory)
    return _default_adapter


def create_registered_strategy_lab_v2_router():
    """Build the authenticated, application-registered v2 router."""

    principal_dependency = getattr(
        import_module("app.auth.dependencies"), "get_current_user"
    )

    return create_strategy_lab_router(
        adapter_dependency=get_strategy_lab_v2_adapter,
        principal_dependency=principal_dependency,
    )


__all__ = [
    "CapabilityPreflightResolver",
    "PostgresStrategyLabV2Adapter",
    "ResultPublicationCompletionResolution",
    "create_registered_strategy_lab_v2_router",
    "get_strategy_lab_v2_adapter",
]
