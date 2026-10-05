"""Application wiring for the Strategy Lab v2 API.

The package-level router and PostgreSQL adapters deliberately remain
registration-neutral.  This module is the small application-owned seam that
connects them to the existing authenticated user dependency and async session
factory.  It does not run migrations, start workers, or import an execution
engine; those lifecycle concerns remain explicit follow-up gates.
"""

from __future__ import annotations

import inspect
import os
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
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.capability_summary import CapabilitySummary
from app.strategy_lab_v2.commands import ExecutionCommand, ExecutionCommandResolution
from app.strategy_lab_v2.contracts import (
    ArtifactManifest,
    DataSnapshot,
    ExperimentDefinition,
    ForwardInstance,
    ForwardState,
    MetricSet,
    PortfolioComposition,
    RunAttempt,
    ScientificTrial,
    StrategyPackage,
    StrategyVersion,
)
from app.strategy_lab_v2.dispatch import DispatchRequest, SearchDispatchIntent
from app.strategy_lab_v2.dispatch_payload import DispatchPayload
from app.strategy_lab_v2.execution import ExecutionAuthorization
from app.strategy_lab_v2.forward_account import (
    ForwardAccountEvent,
    ForwardAccountState,
)
from app.strategy_lab_v2.forward_admission import ForwardLiveAdmissionState
from app.strategy_lab_v2.forward_corrections import (
    CounterfactualReplayPlan,
    ForwardCorrectionCommand,
)
from app.strategy_lab_v2.forward_event_dispatch import ForwardEventDispatchResolution
from app.strategy_lab_v2.forward_event_transaction import ForwardEventTransactionResolution
from app.strategy_lab_v2.forward_execution_plan import ForwardExecutionPlan
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
from app.strategy_lab_v2.nautilus_trial_materializer import NautilusTrialRuntimeEvidence
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
    STORAGE_REQUEST_ID_CONFLICT_REASON,
    AggregateKey,
    AggregateMutation,
    StorageTransactionDecision,
    StorageTransactionRequest,
)
from app.strategy_lab_v2.submissions import SubmissionReceipt, SubmissionRequest
from app.strategy_lab_v2.worker_handoff import encode_worker_handoff
from app.strategy_lab_v2.worker_process import WorkerExecutionRequest
from app.strategy_lab_v2.workers import WorkerProfile


@dataclass(frozen=True, slots=True)
class _PrincipalIdentity:
    """String owner identity shared by every v2 persistence adapter."""

    id: str


CapabilityPreflightResolver = Callable[..., Awaitable[CapabilitySummary] | CapabilitySummary]
SearchDispatchResolver = Callable[
    ..., Awaitable[SearchDispatchResolution] | SearchDispatchResolution
]


@dataclass(frozen=True, slots=True)
class SearchDispatchEvidence:
    """Materialized trial evidence required before durable candidate dispatch."""

    authorization: ExecutionAuthorization
    trial_runtime_evidence: NautilusTrialRuntimeEvidence
    worker_request: WorkerExecutionRequest
    reservation_id: str
    now: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.authorization, ExecutionAuthorization):
            raise TypeError("authorization must be an ExecutionAuthorization")
        if not isinstance(self.trial_runtime_evidence, NautilusTrialRuntimeEvidence):
            raise TypeError("trial_runtime_evidence must be a NautilusTrialRuntimeEvidence")
        if not isinstance(self.worker_request, WorkerExecutionRequest):
            raise TypeError("worker_request must be a WorkerExecutionRequest")
        if not isinstance(self.reservation_id, str) or not self.reservation_id.strip():
            raise ValueError("reservation_id must not be empty")
        if (
            not isinstance(self.now, datetime)
            or self.now.tzinfo is None
            or self.now.utcoffset() is None
        ):
            raise ValueError("now must be timezone-aware")
        graph = self.trial_runtime_evidence.materialized_input.graph
        runtime_request = self.trial_runtime_evidence.runtime_request
        if self.authorization.attempt_id != graph.attempt.attempt_id:
            raise ValueError("authorization must reference the materialized trial attempt")
        if self.authorization.trial_id != graph.trial.trial_id:
            raise ValueError("authorization must reference the materialized scientific trial")
        if self.authorization.trial_preflight_fingerprint != graph.trial.preflight_fingerprint:
            raise ValueError(
                "authorization preflight differs from the materialized scientific trial"
            )
        if self.authorization.source_digest != runtime_request.source_digest:
            raise ValueError("authorization source differs from materialized runtime evidence")
        worker = self.worker_request
        if worker.authorization != self.authorization:
            raise ValueError("worker request authorization differs from dispatch evidence")
        if worker.runtime_request != runtime_request:
            raise ValueError("worker request runtime differs from materialized runtime evidence")
        if worker.runtime_preflight != self.trial_runtime_evidence.runtime_preflight:
            raise ValueError("worker request preflight differs from materialized runtime evidence")
        if (
            worker.runtime_input_artifact
            != self.trial_runtime_evidence.materialized_input.assembly.runtime_input_artifact
        ):
            raise ValueError("worker request artifact differs from the materialized trial input")
        if worker.admission.authorization_fingerprint != self.authorization.fingerprint:
            raise ValueError("worker request admission differs from dispatch authorization")
        if worker.admission.runtime_request_fingerprint != runtime_request.fingerprint:
            raise ValueError("worker request admission differs from materialized runtime request")
        if worker.admission.reservation_id != self.reservation_id:
            raise ValueError("worker request admission differs from dispatch reservation")
        lease = worker.lease_state.lease
        if (
            lease.attempt_id != self.authorization.attempt_id
            or lease.worker_id != self.authorization.lease_worker_id
            or lease.lease_id != self.authorization.lease_id
        ):
            raise ValueError("worker request lease differs from dispatch authorization")
        if worker.observed_at != self.now or worker.started_at > self.now:
            raise ValueError("worker request time differs from dispatch evidence")
        if (
            worker.execution_plan.trial_id != graph.trial.trial_id
            or worker.execution_plan.attempt_id != graph.attempt.attempt_id
            or worker.execution_plan.data_snapshot_fingerprint != graph.snapshot.fingerprint
        ):
            raise ValueError("worker execution plan differs from the materialized trial graph")

    @property
    def runtime_request(self) -> StrategyRuntimeRequest:
        """Return the request derived from the verified runtime input bundle."""

        return self.trial_runtime_evidence.runtime_request

    @property
    def runtime_preflight(self) -> StrategyRuntimePreflight:
        """Return the isolation preflight bound to the derived runtime request."""

        return self.trial_runtime_evidence.runtime_preflight


SearchDispatchEvidenceResolver = Callable[
    ..., Awaitable[SearchDispatchEvidence] | SearchDispatchEvidence
]


@dataclass(frozen=True, slots=True)
class StrategyLabV2ApiBindings:
    """Trusted local capabilities installed by the application host.

    Production search dispatch is exposed as an asynchronous resolver so the
    host can proxy preparation to an isolated local service instead of running
    trial hydration and artifact materialization in the API process.
    """

    capability_preflight: CapabilityPreflightResolver | None = None
    search_dispatch: SearchDispatchResolver | None = None

    def __post_init__(self) -> None:
        if self.capability_preflight is not None and not callable(self.capability_preflight):
            raise TypeError("capability_preflight must be callable")
        if self.capability_preflight is not None and not _is_async_callable(
            self.capability_preflight
        ):
            raise TypeError("capability_preflight host binding must be asynchronous")
        if self.search_dispatch is not None and not callable(self.search_dispatch):
            raise TypeError("search_dispatch must be callable")
        if self.search_dispatch is not None and not _is_async_callable(self.search_dispatch):
            raise TypeError("search_dispatch host binding must be asynchronous")
        if self.capability_preflight is None and self.search_dispatch is None:
            raise ValueError("at least one Strategy Lab v2 API host binding is required")


StrategyLabV2ApiBindingsFactory = Callable[
    [Callable[[], Any], PostgresStrategyLabV2Persistence], StrategyLabV2ApiBindings
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
        host_bindings_factory: StrategyLabV2ApiBindingsFactory | None = None,
        persistence: PostgresStrategyLabV2Persistence | None = None,
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
        if host_bindings_factory is not None:
            if not callable(host_bindings_factory):
                raise TypeError("host_bindings_factory must be callable")
            if _is_async_callable(host_bindings_factory):
                raise TypeError("host_bindings_factory must be synchronous")
            if any(
                binding is not None
                for binding in (capability_preflight, search_dispatch, search_dispatch_evidence)
            ):
                raise ValueError(
                    "host bindings cannot be combined with explicit resolver arguments"
                )
        self._clock = clock
        if persistence is not None and not isinstance(
            persistence, PostgresStrategyLabV2Persistence
        ):
            raise TypeError("persistence must be a PostgresStrategyLabV2Persistence")
        self._persistence = persistence or PostgresStrategyLabV2Persistence.build(
            session_factory,
            clock=clock,
        )
        if host_bindings_factory is not None:
            bindings = host_bindings_factory(session_factory, self._persistence)
            if inspect.isawaitable(bindings):
                if inspect.iscoroutine(bindings):
                    bindings.close()
                raise TypeError("host_bindings_factory must configure bindings synchronously")
            if not isinstance(bindings, StrategyLabV2ApiBindings):
                raise TypeError("host_bindings_factory must return StrategyLabV2ApiBindings")
            capability_preflight = bindings.capability_preflight
            search_dispatch = bindings.search_dispatch
        self._capability_preflight = capability_preflight
        self._search_dispatch = search_dispatch
        self._search_dispatch_evidence = search_dispatch_evidence
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
        if (
            not isinstance(candidate_index, int)
            or isinstance(candidate_index, bool)
            or candidate_index < 0
        ):
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
        if (
            not isinstance(candidate_index, int)
            or isinstance(candidate_index, bool)
            or candidate_index < 0
        ):
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
        dispatch_intent: SearchDispatchIntent,
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
        if (
            not isinstance(candidate_index, int)
            or isinstance(candidate_index, bool)
            or candidate_index < 0
        ):
            raise ValueError("candidate_index must be a non-negative integer")
        if not isinstance(attempt_id, str) or not attempt_id.strip():
            raise ValueError("attempt_id must not be empty")
        if not isinstance(dispatch_intent, SearchDispatchIntent):
            raise TypeError("dispatch_intent must be a SearchDispatchIntent")
        if dispatch_intent.attempt_id != attempt_id:
            raise ValueError("search dispatch intent differs from the requested attempt")
        search_dispatch_evidence = getattr(self, "_search_dispatch_evidence", None)
        callback_kwargs = {
            "principal": owner,
            "request_id": request_id,
            "experiment_fingerprint": experiment_fingerprint,
            "candidate_index": candidate_index,
            "attempt_id": attempt_id,
            "dispatch_intent": dispatch_intent,
        }
        if self._search_dispatch is not None:
            resolved = self._search_dispatch(**callback_kwargs)
            resolution = await resolved if inspect.isawaitable(resolved) else resolved
            if not isinstance(resolution, SearchDispatchResolution):
                raise TypeError("search_dispatch must return a SearchDispatchResolution")
            return resolution
        dispatch_store = getattr(self, "_search_dispatch_store", None)
        replay_resolver = getattr(dispatch_store, "replay_idempotency", None)
        if callable(replay_resolver):
            replay_result = replay_resolver(
                principal=owner,
                experiment_fingerprint=experiment_fingerprint,
                candidate_index=candidate_index,
                attempt_id=attempt_id,
                dispatch_intent=dispatch_intent,
            )
            replay = await replay_result if inspect.isawaitable(replay_result) else replay_result
            if replay is not None:
                if not isinstance(replay, SearchDispatchResolution):
                    raise TypeError(
                        "replay_idempotency must return SearchDispatchResolution or None"
                    )
                return replay
        if search_dispatch_evidence is None:
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
        evidence_resolver = search_dispatch_evidence
        evidence_result = evidence_resolver(**callback_kwargs)
        evidence = (
            await evidence_result if inspect.isawaitable(evidence_result) else evidence_result
        )
        if not isinstance(evidence, SearchDispatchEvidence):
            raise TypeError("search_dispatch_evidence must return SearchDispatchEvidence")
        materialized_graph = evidence.trial_runtime_evidence.materialized_input.graph
        if materialized_graph.experiment.fingerprint != experiment_fingerprint:
            raise ValueError("search dispatch experiment differs from the materialized trial graph")
        if materialized_graph.attempt.attempt_id != attempt_id:
            raise ValueError("search dispatch attempt differs from the materialized trial graph")
        worker_payload = encode_worker_handoff(evidence.worker_request)
        payload = DispatchPayload.from_mapping(worker_payload)
        dispatch_request = dispatch_intent.bind_payload(payload.payload_digest)
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
            payload=worker_payload,
            now=evidence.now,
            available_at=max(dispatch_intent.created_at, materialized_graph.attempt.created_at),
        )

    async def _validate_domain_dependencies(
        self,
        principal: _PrincipalIdentity,
        contract: Any,
    ) -> None:
        """Require typed references to exist and agree within one owner scope."""

        if contract is None or isinstance(contract, StrategyVersion | DataSnapshot):
            return

        references: dict[ApiResourceType, set[str]] = {}

        def add(resource_type: ApiResourceType, fingerprint: str) -> None:
            references.setdefault(resource_type, set()).add(fingerprint)

        if isinstance(contract, StrategyPackage):
            add(ApiResourceType.STRATEGY, contract.strategy_fingerprint)
        elif isinstance(contract, PortfolioComposition):
            for component in contract.components:
                add(ApiResourceType.STRATEGY, component.strategy_fingerprint)
        elif isinstance(contract, ExperimentDefinition):
            add(ApiResourceType.PORTFOLIO, contract.portfolio_fingerprint)
            add(ApiResourceType.SNAPSHOT, contract.snapshot_fingerprint)
            for fingerprint in contract.strategy_fingerprints:
                add(ApiResourceType.STRATEGY, fingerprint)
            for fingerprint in contract.strategy_package_fingerprints.values():
                add(ApiResourceType.PACKAGE, fingerprint)
        elif isinstance(contract, ScientificTrial):
            add(ApiResourceType.EXPERIMENT, contract.experiment_fingerprint)
            add(ApiResourceType.SNAPSHOT, contract.snapshot_fingerprint)
        elif isinstance(contract, RunAttempt):
            add(ApiResourceType.TRIAL, contract.trial_id)
        elif isinstance(contract, MetricSet):
            add(ApiResourceType.TRIAL, contract.trial_id)
        elif isinstance(contract, ForwardInstance):
            add(ApiResourceType.PORTFOLIO, contract.portfolio_fingerprint)
            add(ApiResourceType.SNAPSHOT, contract.warmup_snapshot_fingerprint)
        elif isinstance(contract, ForwardExecutionPlan):
            instance = await self._resources.get_domain_contract(
                principal=principal,
                resource_type=ApiResourceType.FORWARD_INSTANCE,
                resource_id=contract.instance_id,
            )
            if not isinstance(instance, ForwardInstance):
                raise ValueError("forward execution plan instance is unavailable")
            if instance.portfolio_fingerprint != contract.portfolio_fingerprint:
                raise ValueError("forward execution plan differs from its instance portfolio")
            add(ApiResourceType.PORTFOLIO, contract.portfolio_fingerprint)
            for plan_component in contract.components:
                add(ApiResourceType.STRATEGY, plan_component.strategy_fingerprint)
                add(ApiResourceType.PACKAGE, plan_component.package_fingerprint)
        else:
            return

        resolved: dict[ApiResourceType, Mapping[str, Any]] = {}
        for resource_type, fingerprints in references.items():
            matches = await self._resources.get_domain_contracts_by_fingerprint(
                principal=principal,
                resource_type=resource_type,
                fingerprints=tuple(sorted(fingerprints)),
            )
            if set(matches) != fingerprints:
                # The same response covers missing objects and objects owned by
                # another principal; domain creation cannot probe existence.
                raise ValueError("a referenced Strategy Lab domain object is unavailable")
            resolved[resource_type] = matches

        def require(
            resource_type: ApiResourceType,
            fingerprint: str,
            expected_type: type[Any],
        ) -> Any:
            value = resolved[resource_type].get(fingerprint)
            if not isinstance(value, expected_type):
                raise ValueError("a referenced Strategy Lab domain object is unavailable")
            return value

        if isinstance(contract, StrategyPackage):
            strategy = require(
                ApiResourceType.STRATEGY,
                contract.strategy_fingerprint,
                StrategyVersion,
            )
            if strategy.sdk_version != contract.sdk_version:
                raise ValueError("package SDK version does not match its strategy")
        elif isinstance(contract, PortfolioComposition):
            for component in contract.components:
                require(ApiResourceType.STRATEGY, component.strategy_fingerprint, StrategyVersion)
        elif isinstance(contract, ExperimentDefinition):
            portfolio = require(
                ApiResourceType.PORTFOLIO,
                contract.portfolio_fingerprint,
                PortfolioComposition,
            )
            snapshot = require(
                ApiResourceType.SNAPSHOT,
                contract.snapshot_fingerprint,
                DataSnapshot,
            )
            if contract.capability_contract_digest != snapshot.capability_contract_digest:
                raise ValueError("experiment capability contract differs from its frozen snapshot")
            portfolio_strategies = {item.strategy_fingerprint for item in portfolio.components}
            if portfolio_strategies != set(contract.strategy_fingerprints):
                raise ValueError("experiment strategies do not match its portfolio composition")
            for strategy_fingerprint in contract.strategy_fingerprints:
                require(ApiResourceType.STRATEGY, strategy_fingerprint, StrategyVersion)
            for (
                strategy_fingerprint,
                package_fingerprint,
            ) in contract.strategy_package_fingerprints.items():
                package = require(ApiResourceType.PACKAGE, package_fingerprint, StrategyPackage)
                if package.strategy_fingerprint != strategy_fingerprint:
                    raise ValueError("experiment package binding does not match its strategy")
        elif isinstance(contract, ScientificTrial):
            experiment = require(
                ApiResourceType.EXPERIMENT,
                contract.experiment_fingerprint,
                ExperimentDefinition,
            )
            snapshot = require(
                ApiResourceType.SNAPSHOT,
                contract.snapshot_fingerprint,
                DataSnapshot,
            )
            if experiment.snapshot_fingerprint != contract.snapshot_fingerprint:
                raise ValueError("trial snapshot does not match its experiment")
            if snapshot.preflight_report.fingerprint != contract.preflight_report.fingerprint:
                raise ValueError("trial preflight does not match its frozen snapshot")
        elif isinstance(contract, RunAttempt):
            require(ApiResourceType.TRIAL, contract.trial_id, ScientificTrial)
        elif isinstance(contract, MetricSet):
            require(ApiResourceType.TRIAL, contract.trial_id, ScientificTrial)
            attempt = await self._resources.get_run_attempt_by_attempt_id(
                principal=principal,
                attempt_id=contract.attempt_id,
            )
            if attempt is None or attempt.trial_id != contract.trial_id:
                raise ValueError("metric set attempt is unavailable for its trial")
        elif isinstance(contract, ForwardInstance):
            require(
                ApiResourceType.PORTFOLIO,
                contract.portfolio_fingerprint,
                PortfolioComposition,
            )
            require(
                ApiResourceType.SNAPSHOT,
                contract.warmup_snapshot_fingerprint,
                DataSnapshot,
            )
        elif isinstance(contract, ForwardExecutionPlan):
            instance = await self._resources.get_domain_contract(
                principal=principal,
                resource_type=ApiResourceType.FORWARD_INSTANCE,
                resource_id=contract.instance_id,
            )
            portfolio = require(
                ApiResourceType.PORTFOLIO,
                contract.portfolio_fingerprint,
                PortfolioComposition,
            )
            if not isinstance(instance, ForwardInstance):
                raise ValueError("forward execution plan instance is unavailable")
            contract.validate_bindings(instance=instance, portfolio=portfolio)
            for plan_component in contract.components:
                strategy = require(
                    ApiResourceType.STRATEGY,
                    plan_component.strategy_fingerprint,
                    StrategyVersion,
                )
                package = require(
                    ApiResourceType.PACKAGE,
                    plan_component.package_fingerprint,
                    StrategyPackage,
                )
                if package.fingerprint != plan_component.package_fingerprint:
                    raise ValueError(
                        "forward execution plan package pin does not match its package"
                    )
                if package.strategy_fingerprint != strategy.fingerprint:
                    raise ValueError("forward execution plan package differs from its strategy")
                if package.sdk_version != strategy.sdk_version:
                    raise ValueError("forward execution plan package SDK differs from its strategy")

    async def create_resource(
        self,
        *,
        principal: Any,
        request_id: str,
        request: ResourceMutationRequest,
    ) -> ResourceMutationServiceResult:
        """Persist a validated resource envelope through aggregate CAS storage."""

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
        await self._validate_domain_dependencies(owner, normalized_domain.typed_contract)
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
            # Resource IDs are globally keyed in the aggregate store. Include
            # the owner for server-generated IDs so identical private domain
            # objects do not collide across principals.
            "owner_id": owner.id,
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
        domain_identity_key: AggregateKey | None = None
        domain_identity_state: dict[str, Any] | None = None
        if normalized_domain.domain_fingerprint is not None:
            domain_identity_key = AggregateKey(
                "resource_domain_identity",
                content_digest(
                    {
                        "owner_id": owner.id,
                        "resource_type": request.resource_type.value,
                        "domain_fingerprint": normalized_domain.domain_fingerprint,
                    }
                ),
            )
            domain_identity_state = {
                "owner_id": owner.id,
                "resource_type": request.resource_type.value,
                "domain_fingerprint": normalized_domain.domain_fingerprint,
                "resource_id": resource_id,
                "schema_version": 1,
            }
            reserved_identity = await self._persistence.aggregate_store.get(domain_identity_key)
            if reserved_identity is not None:
                reserved_state = reserved_identity.state
                if (
                    not isinstance(reserved_state, Mapping)
                    or str(reserved_state.get("owner_id")) != owner.id
                    or reserved_state.get("resource_type") != request.resource_type.value
                    or reserved_state.get("domain_fingerprint")
                    != normalized_domain.domain_fingerprint
                    or not isinstance(reserved_state.get("resource_id"), str)
                ):
                    return ResourceMutationServiceResult(
                        ResourceMutationResolution(
                            ResourceMutationDecision.REJECT,
                            request.fingerprint,
                            rejection_reason="persisted domain identity reservation is malformed",
                        )
                    )
                if reserved_state["resource_id"] != resource_id or not replaying_known_mutation:
                    return ResourceMutationServiceResult(
                        ResourceMutationResolution(
                            ResourceMutationDecision.REJECT,
                            request.fingerprint,
                            rejection_reason=(
                                "owner already has a resource for this domain fingerprint"
                            ),
                        )
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
        mutations = [AggregateMutation(aggregate_key, state)]
        if domain_identity_key is not None and domain_identity_state is not None:
            # Reserve the owner-scoped immutable identity in the same CAS
            # transaction as the public resource. The aggregate store's
            # primary key arbitrates concurrent creates without a read/write
            # race or a separate migration-owned index.
            mutations.append(AggregateMutation(domain_identity_key, domain_identity_state))
        storage_request = StorageTransactionRequest(storage_request_id, tuple(mutations))
        resolved = await self._persistence.aggregate_store.apply(storage_request)
        if (
            resolved.decision is StorageTransactionDecision.CONFLICT
            and resolved.rejection_reason == STORAGE_REQUEST_ID_CONFLICT_REASON
        ):
            return ResourceMutationServiceResult(
                ResourceMutationResolution(
                    ResourceMutationDecision.IDEMPOTENCY_CONFLICT,
                    request.fingerprint,
                )
            )
        committed = next(
            (aggregate for aggregate in resolved.aggregates if aggregate.key == aggregate_key),
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

    async def load_forward_state_at_checkpoint(
        self,
        *,
        principal: Any,
        instance_id: str,
        checkpoint_fingerprint: str,
    ) -> ForwardLiveAdmissionState | None:
        """Read owner-authenticated admission evidence at an exact old checkpoint."""

        if not isinstance(instance_id, str) or not instance_id.strip():
            raise ValueError("instance_id must not be empty")
        require_sha256_digest(checkpoint_fingerprint, field_name="checkpoint_fingerprint")
        return await self._persistence.forward_state.load_state_at_checkpoint(
            principal=_principal_identity(principal),
            instance_id=instance_id,
            checkpoint_fingerprint=checkpoint_fingerprint,
        )

    async def load_forward_replays(
        self, *, principal: Any, instance_id: str
    ) -> tuple[CounterfactualReplayPlan, ...] | None:
        """Read authenticated counterfactual replay plans for one instance."""

        if not isinstance(instance_id, str) or not instance_id.strip():
            raise ValueError("instance_id must not be empty")
        return await self._persistence.forward_state.load_replays(
            principal=_principal_identity(principal), instance_id=instance_id
        )

    async def transition_forward_instance(
        self,
        *,
        principal: Any,
        instance_id: str,
        target: ForwardState,
        now: datetime,
        idempotency_key: str,
    ) -> ForwardStateMutationResolution:
        """Apply one owner-scoped forward lifecycle transition."""

        if not isinstance(instance_id, str) or not instance_id.strip():
            raise ValueError("instance_id must not be empty")
        if not isinstance(target, ForwardState):
            raise TypeError("target must be a ForwardState")
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be a timezone-aware datetime")
        owner = _principal_identity(principal)
        if target is ForwardState.WARMING_UP:
            instance = await self._persistence.forward_state.load_instance(
                principal=owner,
                instance_id=instance_id,
            )
            if instance is not None:
                plan = await self._resources.get_domain_contract(
                    principal=owner,
                    resource_type=ApiResourceType.FORWARD_EXECUTION_PLAN,
                    resource_id=instance_id,
                )
                portfolio = await self._resources.get_domain_contract_by_fingerprint(
                    principal=owner,
                    resource_type=ApiResourceType.PORTFOLIO,
                    fingerprint=instance.portfolio_fingerprint,
                )
                if not isinstance(plan, ForwardExecutionPlan) or not isinstance(
                    portfolio, PortfolioComposition
                ):
                    raise ValueError(
                        "an exact forward execution plan must exist before warm-up activation"
                    )
                plan.validate_bindings(instance=instance, portfolio=portfolio)
        return await self._persistence.forward_state.transition(
            principal=owner,
            instance_id=instance_id,
            target=target,
            now=now.astimezone(UTC),
            idempotency_key=idempotency_key,
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
        return await self._persistence.worker_state.load_forward_authorization(
            profile=profile,
            reservation_id=reservation_id,
            lease_id=lease_id,
        )

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
        bindings_factory = _load_api_bindings_factory(
            os.environ.get("STRATEGY_LAB_V2_API_BINDINGS")
        )
        _default_adapter = PostgresStrategyLabV2Adapter(
            session_factory,
            host_bindings_factory=bindings_factory,
        )
    return _default_adapter


def _load_api_bindings_factory(spec: str | None) -> StrategyLabV2ApiBindingsFactory | None:
    """Load an explicitly configured local application adapter factory."""

    if spec is None or not spec.strip():
        return None
    module_name, separator, attribute = spec.partition(":")
    if not separator or not module_name.strip() or not attribute.strip():
        raise ValueError("Strategy Lab v2 API bindings must use module:attribute syntax")
    module = import_module(module_name.strip())
    factory = getattr(module, attribute.strip(), None)
    if not callable(factory):
        raise TypeError("Strategy Lab v2 API bindings target must be callable")
    return factory


def _is_async_callable(callback: Callable[..., Any]) -> bool:
    return inspect.iscoroutinefunction(callback) or inspect.iscoroutinefunction(
        getattr(callback, "__call__", None)
    )


def create_registered_strategy_lab_v2_router():
    """Build the authenticated, application-registered v2 router."""

    principal_dependency = getattr(import_module("app.auth.dependencies"), "get_current_user")

    return create_strategy_lab_router(
        adapter_dependency=get_strategy_lab_v2_adapter,
        principal_dependency=principal_dependency,
    )


__all__ = [
    "CapabilityPreflightResolver",
    "PostgresStrategyLabV2Adapter",
    "ResultPublicationCompletionResolution",
    "StrategyLabV2ApiBindings",
    "StrategyLabV2ApiBindingsFactory",
    "create_registered_strategy_lab_v2_router",
    "get_strategy_lab_v2_adapter",
]
