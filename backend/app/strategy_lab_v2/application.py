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
from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path
from typing import Any, cast

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
from app.strategy_lab_v2.artifact_retention import ArtifactRetentionPin, ArtifactRetentionState
from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.canonical import content_digest, freeze_json, require_sha256_digest
from app.strategy_lab_v2.capability_summary import CapabilitySummary
from app.strategy_lab_v2.commands import ExecutionCommand, ExecutionCommandResolution
from app.strategy_lab_v2.contracts import (
    ArtifactManifest,
    AttemptState,
    DataSnapshot,
    ExperimentDefinition,
    ForwardInstance,
    ForwardState,
    MetricSet,
    MetricValue,
    PortfolioComposition,
    RunAttempt,
    RunResultManifest,
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
from app.strategy_lab_v2.forward_worker_lifecycle import (
    FORWARD_WORKER_LEASE_DURATION,
    ForwardWorkerCapacityUnavailable,
    ForwardWorkerFleetLifecycleCoordinator,
)
from app.strategy_lab_v2.legacy import (
    LegacyCompatibilityAssessment,
    LegacyImportRequest,
    LegacyImportResolution,
)
from app.strategy_lab_v2.lifecycle import (
    CanonicalForwardEvent,
    ForwardEventObservation,
)
from app.strategy_lab_v2.lifecycle import (
    transition_forward_instance as validate_forward_transition,
)
from app.strategy_lab_v2.nautilus_trial_materializer import NautilusTrialRuntimeEvidence
from app.strategy_lab_v2.outcomes import ExecutionOutcome
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.postgres_forward_account import ForwardAccountStateResolution
from app.strategy_lab_v2.postgres_forward_state import (
    ForwardInstanceResolution,
    ForwardStateMutationDecision,
    ForwardStateMutationResolution,
)
from app.strategy_lab_v2.postgres_result_publication import PublicationStateResolution
from app.strategy_lab_v2.postgres_search_dispatch import SearchDispatchRecord
from app.strategy_lab_v2.postgres_walk_forward_plan import WalkForwardDefinitionResolution
from app.strategy_lab_v2.postgres_walk_forward_summary import WalkForwardSummaryResolution
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
from app.strategy_lab_v2.search_dispatch import SearchDispatchDecision, SearchDispatchResolution
from app.strategy_lab_v2.search_state import (
    SearchCandidatePhase,
    SearchExecutionState,
    SearchStateDecision,
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
from app.strategy_lab_v2.walk_forward_native_metrics import (
    calculate_walk_forward_native_oos_metrics,
)
from app.strategy_lab_v2.walk_forward_queue import (
    WalkForwardQueueResultEvidence,
    WalkForwardQueueTransition,
    append_selected_oos_queue,
    initialize_walk_forward_training_queue,
    oos_results_from_search_queue,
    training_scores_from_search_queue,
)
from app.strategy_lab_v2.walk_forward_search import (
    WalkForwardDefinitionRequest,
    WalkForwardExecutionDefinition,
    WalkForwardOosResult,
    WalkForwardSelection,
    collect_walk_forward_oos_results,
    select_walk_forward_oos_tasks,
)
from app.strategy_lab_v2.walk_forward_summary import (
    WalkForwardNativeOosMetricSummary,
    build_walk_forward_oos_summary,
)
from app.strategy_lab_v2.walk_forward_trials import (
    materialize_walk_forward_oos_trials,
    materialize_walk_forward_training_trials,
)
from app.strategy_lab_v2.worker_handoff import encode_worker_handoff
from app.strategy_lab_v2.worker_process import WorkerExecutionRequest
from app.strategy_lab_v2.workers import WorkerProfile


@dataclass(frozen=True, slots=True)
class _PrincipalIdentity:
    """String owner identity shared by every v2 persistence adapter."""

    id: str


@dataclass(frozen=True, slots=True)
class _WalkForwardOosCompletion:
    experiment_fingerprint: str
    definition_fingerprint: str
    selection: WalkForwardSelection
    results: tuple[WalkForwardOosResult, ...]
    source_metrics: tuple[MetricValue, ...]
    native_portfolio_metrics: tuple[MetricValue, ...] | None = None
    native_metric_summary: WalkForwardNativeOosMetricSummary | None = None


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
WalkForwardObservationCalendarResolver = Callable[..., Awaitable[Sequence[datetime]]]


@dataclass(frozen=True, slots=True)
class StrategyLabV2ApiBindings:
    """Trusted local capabilities installed by the application host.

    Production search dispatch is exposed as an asynchronous resolver so the
    host can proxy preparation to an isolated local service instead of running
    trial hydration and artifact materialization in the API process.
    """

    capability_preflight: CapabilityPreflightResolver | None = None
    search_dispatch: SearchDispatchResolver | None = None
    walk_forward_observation_calendar: WalkForwardObservationCalendarResolver | None = None
    walk_forward_artifact_store: LocalArtifactStore | None = None
    forward_worker_runtime_profile_fingerprint: str | None = None

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
        if self.walk_forward_observation_calendar is not None and not callable(
            self.walk_forward_observation_calendar
        ):
            raise TypeError("walk_forward_observation_calendar must be callable")
        if self.walk_forward_observation_calendar is not None and not _is_async_callable(
            self.walk_forward_observation_calendar
        ):
            raise TypeError("walk-forward observation calendar binding must be asynchronous")
        if self.walk_forward_artifact_store is not None and not isinstance(
            self.walk_forward_artifact_store, LocalArtifactStore
        ):
            raise TypeError("walk_forward_artifact_store must be a LocalArtifactStore")
        if self.forward_worker_runtime_profile_fingerprint is not None:
            require_sha256_digest(
                self.forward_worker_runtime_profile_fingerprint,
                field_name="forward_worker_runtime_profile_fingerprint",
            )
        if (
            self.capability_preflight is None
            and self.search_dispatch is None
            and self.walk_forward_observation_calendar is None
        ):
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
        walk_forward_observation_calendar: WalkForwardObservationCalendarResolver | None = None,
        walk_forward_artifact_store: LocalArtifactStore | None = None,
        host_bindings_factory: StrategyLabV2ApiBindingsFactory | None = None,
        persistence: PostgresStrategyLabV2Persistence | None = None,
        forward_worker_runtime_profile_fingerprint: str | None = None,
        forward_worker_lease_duration: timedelta = FORWARD_WORKER_LEASE_DURATION,
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
        if walk_forward_observation_calendar is not None and not callable(
            walk_forward_observation_calendar
        ):
            raise TypeError("walk_forward_observation_calendar must be callable")
        if walk_forward_observation_calendar is not None and not _is_async_callable(
            walk_forward_observation_calendar
        ):
            raise TypeError("walk-forward observation calendar binding must be asynchronous")
        if walk_forward_artifact_store is not None and not isinstance(
            walk_forward_artifact_store, LocalArtifactStore
        ):
            raise TypeError("walk_forward_artifact_store must be a LocalArtifactStore")
        if search_dispatch is not None and search_dispatch_evidence is not None:
            raise ValueError("search_dispatch and search_dispatch_evidence are mutually exclusive")
        if forward_worker_runtime_profile_fingerprint is not None:
            require_sha256_digest(
                forward_worker_runtime_profile_fingerprint,
                field_name="forward_worker_runtime_profile_fingerprint",
            )
        if forward_worker_lease_duration <= timedelta(0):
            raise ValueError("forward_worker_lease_duration must be positive")
        if host_bindings_factory is not None:
            if not callable(host_bindings_factory):
                raise TypeError("host_bindings_factory must be callable")
            if _is_async_callable(host_bindings_factory):
                raise TypeError("host_bindings_factory must be synchronous")
            if any(
                binding is not None
                for binding in (
                    capability_preflight,
                    search_dispatch,
                    search_dispatch_evidence,
                    walk_forward_observation_calendar,
                    walk_forward_artifact_store,
                    forward_worker_runtime_profile_fingerprint,
                )
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
            walk_forward_observation_calendar = bindings.walk_forward_observation_calendar
            walk_forward_artifact_store = bindings.walk_forward_artifact_store
            forward_worker_runtime_profile_fingerprint = (
                bindings.forward_worker_runtime_profile_fingerprint
            )
        self._capability_preflight = capability_preflight
        self._search_dispatch = search_dispatch
        self._search_dispatch_evidence = search_dispatch_evidence
        self._walk_forward_observation_calendar = walk_forward_observation_calendar
        self._walk_forward_artifact_store = walk_forward_artifact_store
        self._forward_worker_lifecycle = (
            ForwardWorkerFleetLifecycleCoordinator(
                self._persistence.worker_state,
                runtime_profile_fingerprint=forward_worker_runtime_profile_fingerprint,
                lease_duration=forward_worker_lease_duration,
            )
            if forward_worker_runtime_profile_fingerprint is not None
            else None
        )
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

    async def persist_walk_forward_definition(
        self,
        *,
        principal: Any,
        definition: WalkForwardExecutionDefinition,
    ) -> WalkForwardDefinitionResolution:
        """Persist a walk-forward plan only after owner-scoped graph validation.

        This is a host/application boundary, not an HTTP wire endpoint. The
        caller must first create the experiment and base trial resources; this
        operation binds a deterministic fold schedule to those exact immutable
        domain objects before any search queue is initialized or dispatched.
        """

        if not isinstance(definition, WalkForwardExecutionDefinition):
            raise TypeError("definition must be a WalkForwardExecutionDefinition")
        owner = _principal_identity(principal)
        experiment = await self._resources.get_domain_contract_by_fingerprint(
            principal=owner,
            resource_type=ApiResourceType.EXPERIMENT,
            fingerprint=definition.experiment_fingerprint,
        )
        if not isinstance(experiment, ExperimentDefinition):
            raise ValueError("walk-forward experiment is unavailable to this owner")
        if experiment.fingerprint != definition.experiment_fingerprint:
            raise ValueError("walk-forward definition is rebound to a different experiment")
        snapshot = await self._resources.get_domain_contract_by_fingerprint(
            principal=owner,
            resource_type=ApiResourceType.SNAPSHOT,
            fingerprint=experiment.snapshot_fingerprint,
        )
        if not isinstance(snapshot, DataSnapshot):
            raise ValueError("walk-forward experiment snapshot is unavailable to this owner")
        if (
            snapshot.fingerprint != experiment.snapshot_fingerprint
            or snapshot.capability_contract_digest != experiment.capability_contract_digest
        ):
            raise ValueError("walk-forward experiment snapshot binding is inconsistent")

        candidates = await self._resources.get_domain_contracts_by_fingerprint(
            principal=owner,
            resource_type=ApiResourceType.TRIAL,
            fingerprints=definition.candidate_fingerprints,
        )
        if set(candidates) != set(definition.candidate_fingerprints):
            raise ValueError("one or more walk-forward base trials are unavailable to this owner")
        for fingerprint in definition.candidate_fingerprints:
            trial = candidates[fingerprint]
            if not isinstance(trial, ScientificTrial):
                raise ValueError("walk-forward base trial has an invalid domain contract")
            if trial.trial_id != fingerprint:
                raise ValueError("walk-forward base trial identity does not match its resource key")
            if (
                trial.experiment_fingerprint != definition.experiment_fingerprint
                or trial.snapshot_fingerprint != snapshot.fingerprint
                or trial.preflight_fingerprint != snapshot.preflight_report.fingerprint
            ):
                raise ValueError("walk-forward base trial differs from its experiment snapshot")
            if trial.evaluation_window is not None:
                raise ValueError("walk-forward base candidates must not have a pre-bound window")

        return await self._persistence.walk_forward_plans.persist(
            principal=owner,
            definition=definition,
        )

    async def create_walk_forward_definition(
        self,
        *,
        principal: Any,
        request_id: str,
        idempotency_key: str,
        experiment_fingerprint: str,
        request: WalkForwardDefinitionRequest,
    ) -> WalkForwardDefinitionResolution:
        """Resolve the frozen calendar internally, then persist an owner-bound plan.

        The HTTP caller supplies fold policy and immutable candidate identities,
        never timestamps. The configured asynchronous host resolver must load
        the exact SDK manifests pinned by the experiment and use the canonical
        local frozen-series decoder; its observation calendar is therefore
        derived from verified snapshot bytes rather than caller assertions.
        """

        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must not be empty")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValueError("idempotency_key must not be empty")
        if not isinstance(request, WalkForwardDefinitionRequest):
            raise TypeError("request must be a WalkForwardDefinitionRequest")
        require_sha256_digest(experiment_fingerprint, field_name="experiment_fingerprint")
        resolver = getattr(self, "_walk_forward_observation_calendar", None)
        if resolver is None:
            raise ApiAdapterError(
                ApiError(
                    ApiErrorCode.PRECONDITION_FAILED,
                    "walk-forward calendar resolution is not configured",
                    request_id,
                    501,
                    False,
                    {
                        "reason": (
                            "the host must bind exact strategy packages to the verified "
                            "frozen snapshot event tape"
                        )
                    },
                )
            )

        owner = _principal_identity(principal)
        experiment = await self._resources.get_domain_contract_by_fingerprint(
            principal=owner,
            resource_type=ApiResourceType.EXPERIMENT,
            fingerprint=experiment_fingerprint,
        )
        if not isinstance(experiment, ExperimentDefinition):
            raise ValueError("walk-forward experiment is unavailable to this owner")
        snapshot = await self._resources.get_domain_contract_by_fingerprint(
            principal=owner,
            resource_type=ApiResourceType.SNAPSHOT,
            fingerprint=experiment.snapshot_fingerprint,
        )
        if not isinstance(snapshot, DataSnapshot):
            raise ValueError("walk-forward experiment snapshot is unavailable to this owner")
        if (
            snapshot.fingerprint != experiment.snapshot_fingerprint
            or snapshot.capability_contract_digest != experiment.capability_contract_digest
        ):
            raise ValueError("walk-forward experiment snapshot binding is inconsistent")
        candidates = await self._resources.get_domain_contracts_by_fingerprint(
            principal=owner,
            resource_type=ApiResourceType.TRIAL,
            fingerprints=request.candidate_fingerprints,
        )
        if set(candidates) != set(request.candidate_fingerprints):
            raise ValueError("one or more walk-forward base trials are unavailable to this owner")
        typed_candidates: list[ScientificTrial] = []
        for fingerprint in request.candidate_fingerprints:
            trial = candidates[fingerprint]
            if not isinstance(trial, ScientificTrial) or trial.trial_id != fingerprint:
                raise ValueError("walk-forward base trial identity does not match its resource key")
            if (
                trial.experiment_fingerprint != experiment_fingerprint
                or trial.snapshot_fingerprint != snapshot.fingerprint
                or trial.preflight_fingerprint != snapshot.preflight_report.fingerprint
                or trial.evaluation_window is not None
            ):
                raise ValueError(
                    "walk-forward base trial is not an unwindowed experiment candidate"
                )
            typed_candidates.append(trial)

        resolved = resolver(
            principal=owner,
            experiment=experiment,
            snapshot=snapshot,
            candidates=tuple(typed_candidates),
        )
        observation_boundaries = await resolved
        if not isinstance(observation_boundaries, Sequence) or isinstance(
            observation_boundaries, str | bytes
        ):
            raise TypeError("verified observation calendar must be a datetime sequence")
        boundaries = tuple(observation_boundaries)
        if len(boundaries) < 2 or any(
            not isinstance(boundary, datetime)
            or boundary.tzinfo is None
            or boundary.utcoffset() is None
            for boundary in boundaries
        ):
            raise ValueError("verified observation calendar must contain aware boundaries")

        definition = WalkForwardExecutionDefinition(
            experiment_fingerprint=experiment_fingerprint,
            candidate_fingerprints=request.candidate_fingerprints,
            observation_boundaries=boundaries,
            spec=request.spec,
            metric_id=request.metric_id,
            direction=request.direction,
            max_tasks=request.max_tasks,
        )
        resolution = await self.persist_walk_forward_definition(
            principal=owner,
            definition=definition,
        )
        if resolution.decision.value in {"apply", "replay_existing"}:
            await self.initialize_walk_forward_training(
                principal=owner,
                request_id=request_id,
                definition=definition,
            )
        return resolution

    async def initialize_walk_forward_training(
        self,
        *,
        principal: Any,
        request_id: str,
        definition: WalkForwardExecutionDefinition,
    ) -> SearchStateResolution:
        """Persist fold-local trials and initialize their resumable search queue.

        Every trial resource uses its immutable fingerprint as identity and an
        idempotency key derived from the immutable walk-forward definition. If
        the process stops between trial publication and queue creation, replaying
        the same plan repairs the missing suffix before the queue is accepted.
        """

        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must not be empty")
        if not isinstance(definition, WalkForwardExecutionDefinition):
            raise TypeError("definition must be a WalkForwardExecutionDefinition")
        owner = _principal_identity(principal)
        persisted = await self._persistence.walk_forward_plans.load(
            principal=owner,
            experiment_fingerprint=definition.experiment_fingerprint,
        )
        if persisted != definition:
            raise ValueError("walk-forward definition is not the persisted owner-scoped plan")
        experiment = await self._resources.get_domain_contract_by_fingerprint(
            principal=owner,
            resource_type=ApiResourceType.EXPERIMENT,
            fingerprint=definition.experiment_fingerprint,
        )
        if not isinstance(experiment, ExperimentDefinition):
            raise ValueError("walk-forward experiment is unavailable to this owner")
        snapshot = await self._resources.get_domain_contract_by_fingerprint(
            principal=owner,
            resource_type=ApiResourceType.SNAPSHOT,
            fingerprint=experiment.snapshot_fingerprint,
        )
        if (
            not isinstance(snapshot, DataSnapshot)
            or snapshot.fingerprint != experiment.snapshot_fingerprint
            or snapshot.capability_contract_digest != experiment.capability_contract_digest
        ):
            raise ValueError("walk-forward experiment snapshot binding is inconsistent")
        loaded = await self._resources.get_domain_contracts_by_fingerprint(
            principal=owner,
            resource_type=ApiResourceType.TRIAL,
            fingerprints=definition.candidate_fingerprints,
        )
        if set(loaded) != set(definition.candidate_fingerprints):
            raise ValueError("one or more walk-forward base trials are unavailable to this owner")
        candidates = tuple(loaded[fingerprint] for fingerprint in definition.candidate_fingerprints)
        if any(not isinstance(trial, ScientificTrial) for trial in candidates):
            raise ValueError("walk-forward base trial has an invalid domain contract")
        typed_candidates = cast(tuple[ScientificTrial, ...], candidates)
        if tuple(trial.trial_id for trial in typed_candidates) != definition.candidate_fingerprints:
            raise ValueError("walk-forward candidates differ from the persisted plan")
        if any(
            trial.experiment_fingerprint != definition.experiment_fingerprint
            or trial.snapshot_fingerprint != snapshot.fingerprint
            or trial.preflight_fingerprint != snapshot.preflight_report.fingerprint
            or trial.evaluation_window is not None
            for trial in typed_candidates
        ):
            raise ValueError("walk-forward candidates must be exact unwindowed experiment trials")

        plan = definition.training_plan
        training = materialize_walk_forward_training_trials(
            plan,
            typed_candidates,
            definition.folds,
            definition.observation_boundaries,
        )
        published: set[str] = set()
        for trial in training.trials:
            if trial.trial_id in published:
                continue
            published.add(trial.trial_id)
            raw_attributes = freeze_json(trial)
            if not isinstance(raw_attributes, Mapping):
                raise TypeError("walk-forward trial did not encode as a domain mapping")
            attributes = dict(raw_attributes)
            attributes["trial_id"] = trial.trial_id
            mutation = ResourceMutationRequest(
                ApiResourceType.TRIAL,
                f"walk-forward:{definition.fingerprint}:{trial.trial_id}",
                {"attributes": attributes},
                self._clock(),
            )
            created = await self.create_resource(
                principal=owner,
                request_id=content_digest(
                    {
                        "walk_forward_definition": definition.fingerprint,
                        "trial_id": trial.trial_id,
                        "operation": "publish_training_trial",
                    }
                ),
                request=mutation,
            )
            if (
                created.receipt is None
                or created.receipt.resource.meta.get("domain_fingerprint") != trial.trial_id
            ):
                raise ValueError("walk-forward training trial was not durably published")

        state, _bindings = initialize_walk_forward_training_queue(
            plan,
            training,
            now=None,
        )
        existing = await self._persistence.search_state.load(
            principal=owner,
            experiment_fingerprint=definition.experiment_fingerprint,
        )
        if existing is not None:
            if (
                existing.experiment_fingerprint == definition.experiment_fingerprint
                and len(existing.candidates) == len(state.candidates)
                and tuple(item.trial_fingerprint for item in existing.candidates)
                == tuple(item.trial_fingerprint for item in state.candidates)
            ):
                return SearchStateResolution(SearchStateDecision.REPLAY_EXISTING, existing)
            if len(existing.candidates) > len(state.candidates) and tuple(
                item.trial_fingerprint for item in existing.candidates[: len(state.candidates)]
            ) == tuple(item.trial_fingerprint for item in state.candidates):
                oos_replay = await self.append_walk_forward_oos_candidates(
                    principal=owner,
                    request_id=request_id,
                    experiment_fingerprint=definition.experiment_fingerprint,
                )
                if oos_replay.resolution.decision is not SearchStateDecision.REJECT:
                    return oos_replay.resolution
            raise ApiAdapterError(
                ApiError(
                    ApiErrorCode.CONFLICT,
                    "walk-forward training queue conflicts with existing search state",
                    request_id,
                    409,
                    False,
                    {"experiment_fingerprint": definition.experiment_fingerprint},
                )
            )
        resolution = await self._persistence.search_state.initialize(
            principal=owner,
            state=state,
        )
        if resolution.decision is SearchStateDecision.REJECT:
            raced = await self._persistence.search_state.load(
                principal=owner,
                experiment_fingerprint=definition.experiment_fingerprint,
            )
            if (
                raced is not None
                and len(raced.candidates) == len(state.candidates)
                and tuple(item.trial_fingerprint for item in raced.candidates)
                == tuple(item.trial_fingerprint for item in state.candidates)
            ):
                return SearchStateResolution(SearchStateDecision.REPLAY_EXISTING, raced)
            if (
                raced is not None
                and len(raced.candidates) > len(state.candidates)
                and tuple(
                    item.trial_fingerprint for item in raced.candidates[: len(state.candidates)]
                )
                == tuple(item.trial_fingerprint for item in state.candidates)
            ):
                oos_replay = await self.append_walk_forward_oos_candidates(
                    principal=owner,
                    request_id=request_id,
                    experiment_fingerprint=definition.experiment_fingerprint,
                )
                if oos_replay.resolution.decision is not SearchStateDecision.REJECT:
                    return oos_replay.resolution
            raise ApiAdapterError(
                ApiError(
                    ApiErrorCode.CONFLICT,
                    resolution.rejection_reason
                    or "walk-forward training queue conflicts with existing search state",
                    request_id,
                    409,
                    False,
                    {"experiment_fingerprint": definition.experiment_fingerprint},
                )
            )
        if resolution.state != state:
            raise ValueError(
                "persisted walk-forward training queue differs from its immutable plan"
            )
        return resolution

    async def append_walk_forward_oos_candidates(
        self,
        *,
        principal: Any,
        request_id: str,
        experiment_fingerprint: str,
    ) -> WalkForwardQueueTransition:
        """Select and append OOS trials from owner-authenticated training results.

        This phase is safe to invoke after every training completion and after a
        process restart. Training manifests are loaded by their durable attempt
        IDs, the selection is recomputed from training-only metrics, and the
        immutable OOS trials are published before the search-state CAS append.
        """

        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must not be empty")
        require_sha256_digest(experiment_fingerprint, field_name="experiment_fingerprint")
        owner = _principal_identity(principal)
        definition = await self._persistence.walk_forward_plans.load(
            principal=owner,
            experiment_fingerprint=experiment_fingerprint,
        )
        if not isinstance(definition, WalkForwardExecutionDefinition):
            raise ApiAdapterError(
                ApiError(
                    ApiErrorCode.NOT_FOUND,
                    "walk-forward plan is unavailable to this owner",
                    request_id,
                    404,
                )
            )
        experiment = await self._resources.get_domain_contract_by_fingerprint(
            principal=owner,
            resource_type=ApiResourceType.EXPERIMENT,
            fingerprint=experiment_fingerprint,
        )
        if not isinstance(experiment, ExperimentDefinition):
            raise ValueError("walk-forward experiment is unavailable to this owner")
        snapshot = await self._resources.get_domain_contract_by_fingerprint(
            principal=owner,
            resource_type=ApiResourceType.SNAPSHOT,
            fingerprint=experiment.snapshot_fingerprint,
        )
        if (
            not isinstance(snapshot, DataSnapshot)
            or snapshot.fingerprint != experiment.snapshot_fingerprint
            or snapshot.capability_contract_digest != experiment.capability_contract_digest
        ):
            raise ValueError("walk-forward experiment snapshot binding is inconsistent")
        loaded = await self._resources.get_domain_contracts_by_fingerprint(
            principal=owner,
            resource_type=ApiResourceType.TRIAL,
            fingerprints=definition.candidate_fingerprints,
        )
        if set(loaded) != set(definition.candidate_fingerprints):
            raise ValueError("one or more walk-forward base trials are unavailable to this owner")
        candidates = tuple(loaded[fingerprint] for fingerprint in definition.candidate_fingerprints)
        if any(not isinstance(trial, ScientificTrial) for trial in candidates):
            raise ValueError("walk-forward base trial has an invalid domain contract")
        typed_candidates = cast(tuple[ScientificTrial, ...], candidates)
        if tuple(trial.trial_id for trial in typed_candidates) != definition.candidate_fingerprints:
            raise ValueError("walk-forward candidates differ from the persisted plan")
        if any(
            trial.experiment_fingerprint != experiment_fingerprint
            or trial.snapshot_fingerprint != snapshot.fingerprint
            or trial.preflight_fingerprint != snapshot.preflight_report.fingerprint
            or trial.evaluation_window is not None
            for trial in typed_candidates
        ):
            raise ValueError("walk-forward candidates must be exact unwindowed experiment trials")

        plan = definition.training_plan
        training_trials = materialize_walk_forward_training_trials(
            plan,
            typed_candidates,
            definition.folds,
            definition.observation_boundaries,
        )
        training_state, training_bindings = initialize_walk_forward_training_queue(
            plan, training_trials, now=None
        )
        state = await self._persistence.search_state.load(
            principal=owner,
            experiment_fingerprint=experiment_fingerprint,
        )
        if state is None:
            raise ValueError("walk-forward training queue is not initialized")
        training_count = len(training_state.candidates)
        if (
            state.experiment_fingerprint != experiment_fingerprint
            or len(state.candidates) < training_count
            or tuple(item.trial_fingerprint for item in state.candidates[:training_count])
            != tuple(item.trial_fingerprint for item in training_state.candidates)
        ):
            raise ValueError("durable search queue does not match the walk-forward training plan")
        if state.cancellation_requested:
            return WalkForwardQueueTransition(
                SearchStateResolution(
                    SearchStateDecision.REJECT,
                    state,
                    rejection_reason="walk-forward training cancellation has been requested",
                )
            )
        if any(
            candidate.phase is not SearchCandidatePhase.SUCCEEDED or candidate.attempt_id is None
            for candidate in state.candidates[:training_count]
        ):
            return WalkForwardQueueTransition(
                SearchStateResolution(
                    SearchStateDecision.REJECT,
                    state,
                    rejection_reason="all training candidates must succeed before OOS selection",
                )
            )

        evidence: dict[str, WalkForwardQueueResultEvidence] = {}
        for candidate in state.candidates[:training_count]:
            assert candidate.attempt_id is not None
            manifest = await self._persistence.result_materialization.load_manifest(
                principal=owner,
                attempt_id=candidate.attempt_id,
            )
            if manifest is None or candidate.result_fingerprint is None:
                return WalkForwardQueueTransition(
                    SearchStateResolution(
                        SearchStateDecision.REJECT,
                        state,
                        rejection_reason="a successful training attempt has no durable result manifest",
                    )
                )
            evidence[candidate.attempt_id] = WalkForwardQueueResultEvidence(
                search_result_fingerprint=candidate.result_fingerprint,
                manifest=manifest,
            )

        scores = training_scores_from_search_queue(
            plan, training_trials, training_bindings, state, evidence
        )
        selection = select_walk_forward_oos_tasks(plan, definition.folds, scores)
        oos_trials = materialize_walk_forward_oos_trials(
            selection,
            typed_candidates,
            definition.folds,
            definition.observation_boundaries,
        )
        transition = append_selected_oos_queue(
            state,
            plan,
            definition.folds,
            training_trials,
            training_bindings,
            evidence,
            selection,
            oos_trials,
            now=self._clock(),
        )
        if transition.resolution.decision is SearchStateDecision.REJECT:
            return transition

        for trial in oos_trials.trials:
            raw_attributes = freeze_json(trial)
            if not isinstance(raw_attributes, Mapping):
                raise TypeError("walk-forward OOS trial did not encode as a domain mapping")
            attributes = dict(raw_attributes)
            attributes["trial_id"] = trial.trial_id
            created = await self.create_resource(
                principal=owner,
                request_id=content_digest(
                    {
                        "walk_forward_definition": definition.fingerprint,
                        "trial_id": trial.trial_id,
                        "operation": "publish_oos_trial",
                    }
                ),
                request=ResourceMutationRequest(
                    ApiResourceType.TRIAL,
                    f"walk-forward-oos:{definition.fingerprint}:{trial.trial_id}",
                    {"attributes": attributes},
                    self._clock(),
                ),
            )
            if (
                created.receipt is None
                or created.receipt.resource.meta.get("domain_fingerprint") != trial.trial_id
            ):
                raise ValueError("walk-forward OOS trial was not durably published")

        persisted = await self._persistence.search_state.append_candidates(
            principal=owner,
            experiment_fingerprint=experiment_fingerprint,
            expected_state_fingerprint=state.fingerprint,
            trial_fingerprints=tuple(trial.trial_id for trial in oos_trials.trials),
            now=self._clock(),
        )
        if persisted.decision is SearchStateDecision.REJECT:
            return WalkForwardQueueTransition(persisted)
        if persisted.state != transition.resolution.state:
            raise ValueError("persisted walk-forward OOS queue differs from its deterministic plan")
        return WalkForwardQueueTransition(persisted, transition.oos_task_bindings)

    async def _collect_walk_forward_oos_completion(
        self,
        *,
        principal: Any,
        request_id: str,
        experiment_fingerprint: str,
    ) -> _WalkForwardOosCompletion:
        """Rehydrate the complete fold-ordered OOS result set for an owner.

        This deliberately returns fold receipts rather than pretending that a
        scalar per-fold selection metric is a portfolio return series. Every
        receipt is rebuilt from its successful durable attempt and authoritative
        result manifest; incomplete or mismatched folds fail closed.
        """

        transition = await self.append_walk_forward_oos_candidates(
            principal=principal,
            request_id=request_id,
            experiment_fingerprint=experiment_fingerprint,
        )
        state_resolution = transition.resolution
        if state_resolution.decision is SearchStateDecision.REJECT:
            raise ApiAdapterError(
                ApiError(
                    ApiErrorCode.CONFLICT,
                    state_resolution.rejection_reason or "walk-forward OOS phase is not ready",
                    request_id,
                    409,
                    True,
                    {"experiment_fingerprint": experiment_fingerprint},
                )
            )
        state = state_resolution.state
        owner = _principal_identity(principal)
        definition = await self._persistence.walk_forward_plans.load(
            principal=owner,
            experiment_fingerprint=experiment_fingerprint,
        )
        if not isinstance(definition, WalkForwardExecutionDefinition):
            raise ValueError("walk-forward definition disappeared during result hydration")
        loaded = await self._resources.get_domain_contracts_by_fingerprint(
            principal=owner,
            resource_type=ApiResourceType.TRIAL,
            fingerprints=definition.candidate_fingerprints,
        )
        if set(loaded) != set(definition.candidate_fingerprints) or any(
            not isinstance(loaded.get(fingerprint), ScientificTrial)
            for fingerprint in definition.candidate_fingerprints
        ):
            raise ValueError("walk-forward base trials are unavailable during result hydration")
        candidates = tuple(
            cast(ScientificTrial, loaded[fingerprint])
            for fingerprint in definition.candidate_fingerprints
        )
        plan = definition.training_plan
        training_trials = materialize_walk_forward_training_trials(
            plan,
            candidates,
            definition.folds,
            definition.observation_boundaries,
        )
        training_state, training_bindings = initialize_walk_forward_training_queue(
            plan, training_trials, now=None
        )
        training_evidence: dict[str, WalkForwardQueueResultEvidence] = {}
        for candidate in state.candidates[: len(training_state.candidates)]:
            if candidate.attempt_id is None or candidate.result_fingerprint is None:
                raise ValueError("successful training queue slot is missing its attempt receipt")
            manifest = await self._persistence.result_materialization.load_manifest(
                principal=owner,
                attempt_id=candidate.attempt_id,
            )
            if manifest is None:
                raise ValueError("training result manifest is unavailable to this owner")
            training_evidence[candidate.attempt_id] = WalkForwardQueueResultEvidence(
                candidate.result_fingerprint,
                manifest,
            )
        scores = training_scores_from_search_queue(
            plan,
            training_trials,
            training_bindings,
            state,
            training_evidence,
        )
        selection = select_walk_forward_oos_tasks(plan, definition.folds, scores)
        oos_trials = materialize_walk_forward_oos_trials(
            selection,
            candidates,
            definition.folds,
            definition.observation_boundaries,
        )
        expected_oos_ids = tuple(trial.trial_id for trial in oos_trials.trials)
        actual_oos = state.candidates[len(training_state.candidates) :]
        if tuple(candidate.trial_fingerprint for candidate in actual_oos) != expected_oos_ids:
            raise ValueError("persisted OOS queue differs from deterministic training selection")
        oos_evidence: dict[str, WalkForwardQueueResultEvidence] = {}
        source_metrics: list[MetricValue] = []
        oos_manifests: list[RunResultManifest] = []
        for offset, candidate in enumerate(actual_oos):
            if (
                candidate.phase is not SearchCandidatePhase.SUCCEEDED
                or candidate.attempt_id is None
                or candidate.result_fingerprint is None
            ):
                raise ApiAdapterError(
                    ApiError(
                        ApiErrorCode.CONFLICT,
                        "all selected OOS folds must succeed before results are available",
                        request_id,
                        409,
                        True,
                        {"candidate_index": len(training_state.candidates) + offset},
                    )
                )
            manifest = await self._persistence.result_materialization.load_manifest(
                principal=owner,
                attempt_id=candidate.attempt_id,
            )
            if manifest is None:
                raise ApiAdapterError(
                    ApiError(
                        ApiErrorCode.CONFLICT,
                        "a successful OOS attempt has no durable result manifest yet",
                        request_id,
                        409,
                        True,
                        {"candidate_index": len(training_state.candidates) + offset},
                    )
                )
            source_metric = next(
                (
                    metric
                    for metric in manifest.metric_set.values
                    if metric.name == definition.metric_id
                ),
                None,
            )
            if source_metric is None or source_metric.value is None:
                raise ApiAdapterError(
                    ApiError(
                        ApiErrorCode.CONFLICT,
                        "a successful OOS result lacks the declared non-null selection metric",
                        request_id,
                        409,
                        False,
                        {"candidate_index": len(training_state.candidates) + offset},
                    )
                )
            source_metrics.append(source_metric)
            oos_manifests.append(manifest)
            oos_evidence[candidate.attempt_id] = WalkForwardQueueResultEvidence(
                candidate.result_fingerprint,
                manifest,
            )
        results = oos_results_from_search_queue(
            plan,
            selection,
            training_bindings,
            oos_trials,
            transition.oos_task_bindings,
            state,
            oos_evidence,
        )
        ordered_results = collect_walk_forward_oos_results(
            selection,
            results,
            metric_id=definition.metric_id,
        )
        native_calculation = (
            None
            if self._walk_forward_artifact_store is None
            else calculate_walk_forward_native_oos_metrics(
                tuple(oos_manifests),
                artifact_store=self._walk_forward_artifact_store,
                selection_fingerprint=selection.fingerprint,
            )
        )
        native_metrics = None if native_calculation is None else native_calculation.metrics
        native_metric_summary = (
            None
            if native_calculation is None
            else WalkForwardNativeOosMetricSummary(
                experiment_fingerprint=experiment_fingerprint,
                definition_fingerprint=definition.fingerprint,
                selection_fingerprint=selection.fingerprint,
                result_manifest_fingerprints=tuple(item.fingerprint for item in oos_manifests),
                metrics=native_calculation.metrics,
                curve_artifact=native_calculation.curve_artifact,
            )
        )
        return _WalkForwardOosCompletion(
            experiment_fingerprint=experiment_fingerprint,
            definition_fingerprint=definition.fingerprint,
            selection=selection,
            results=ordered_results,
            source_metrics=tuple(source_metrics),
            native_portfolio_metrics=native_metrics,
            native_metric_summary=native_metric_summary,
        )

    async def collect_walk_forward_oos_results(
        self,
        *,
        principal: Any,
        request_id: str,
        experiment_fingerprint: str,
    ) -> tuple[WalkForwardOosResult, ...]:
        """Expose the verified OOS-only fold receipts in deterministic order."""

        completion = await self._collect_walk_forward_oos_completion(
            principal=principal,
            request_id=request_id,
            experiment_fingerprint=experiment_fingerprint,
        )
        return completion.results

    async def persist_walk_forward_oos_summary(
        self,
        *,
        principal: Any,
        request_id: str,
        experiment_fingerprint: str,
    ) -> WalkForwardSummaryResolution:
        """Persist the immutable fold-distribution summary after OOS completion."""

        completion = await self._collect_walk_forward_oos_completion(
            principal=principal,
            request_id=request_id,
            experiment_fingerprint=experiment_fingerprint,
        )
        summary = build_walk_forward_oos_summary(
            experiment_fingerprint=completion.experiment_fingerprint,
            definition_fingerprint=completion.definition_fingerprint,
            selection=completion.selection,
            results=completion.results,
            source_metrics=completion.source_metrics,
        )
        resolution = await self._persistence.walk_forward_summaries.persist(
            principal=principal,
            summary=summary,
        )
        if resolution.decision.value == "reject":
            raise ApiAdapterError(
                ApiError(
                    ApiErrorCode.CONFLICT,
                    resolution.rejection_reason or "walk-forward OOS summary conflicts",
                    request_id,
                    409,
                    False,
                    {"experiment_fingerprint": experiment_fingerprint},
                )
            )
        native_summary = completion.native_metric_summary
        if native_summary is not None:
            await self._pin_walk_forward_curve(
                principal=principal,
                experiment_fingerprint=experiment_fingerprint,
                manifest=native_summary.curve_artifact,
            )
            native_resolution = await self._persistence.walk_forward_native_metrics.persist(
                principal=principal,
                summary=native_summary,
            )
            if native_resolution.decision.value == "reject":
                raise ApiAdapterError(
                    ApiError(
                        ApiErrorCode.CONFLICT,
                        native_resolution.rejection_reason
                        or "native walk-forward metrics conflict",
                        request_id,
                        409,
                        False,
                        {"experiment_fingerprint": experiment_fingerprint},
                    )
                )
        return WalkForwardSummaryResolution(
            resolution.decision,
            resolution.summary,
            resolution.aggregate_version,
            resolution.rejection_reason,
            native_summary,
        )

    async def _pin_walk_forward_curve(
        self,
        *,
        principal: Any,
        experiment_fingerprint: str,
        manifest: ArtifactManifest,
    ) -> ArtifactRetentionPin:
        owner_id = _principal_identity(principal).id
        manifest_fingerprint = content_digest(manifest)
        pin_id = content_digest(
            {
                "owner_id": owner_id,
                "experiment_fingerprint": experiment_fingerprint,
                "artifact_manifest_fingerprint": manifest_fingerprint,
                "purpose": "walk-forward-native-oos-curve",
            }
        )
        pin = ArtifactRetentionPin(
            pin_id=pin_id,
            artifact_manifest_fingerprint=manifest_fingerprint,
            owner_type="walk_forward_native_oos_metrics",
            owner_id=owner_id,
            created_at=self._clock(),
        )
        state = await self._persistence.artifact_retention.read_state(manifest_fingerprint)
        if state is None:
            initial = ArtifactRetentionState.from_manifest(manifest, pins=(pin,))
            try:
                await self._persistence.artifact_retention.ensure_state(initial)
                return pin
            except ValueError:
                # A concurrent finalizer may have registered the same immutable
                # manifest first; authenticate the winner before reusing it.
                state = await self._persistence.artifact_retention.read_state(manifest_fingerprint)
                if state is None:
                    raise
        if (
            state.manifest_fingerprint != manifest_fingerprint
            or state.content_digest != manifest.content_digest
            or state.retention_class is not manifest.retention_class
        ):
            raise ValueError("persisted curve retention state differs from its manifest")
        existing = next((item for item in state.pins if item.pin_id == pin.pin_id), None)
        if existing is not None:
            if (
                existing.owner_type != pin.owner_type
                or existing.owner_id != pin.owner_id
                or existing.released_at is not None
                or existing.expires_at is not None
            ):
                raise ValueError("native walk-forward curve retention pin is no longer active")
            return existing
        await self._persistence.artifact_retention.add_pin(pin)
        return pin

    async def dispatch_walk_forward_training_candidate(
        self,
        *,
        principal: Any,
        request_id: str,
        idempotency_key: str,
        experiment_fingerprint: str,
        candidate_index: int,
        queue_name: str,
    ) -> SearchDispatchResolution:
        """Create/replay the exact fold trial attempt and stage its normal dispatch.

        Attempt IDs are derived from the immutable experiment, queue slot, trial,
        and retry ordinal. The attempt resource is persisted before dispatch so
        the existing isolated preparation, worker admission, and transactional
        outbox path remains the only route to Nautilus execution.
        """

        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must not be empty")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValueError("idempotency_key must not be empty")
        if not isinstance(queue_name, str) or not queue_name.strip():
            raise ValueError("queue_name must not be empty")
        require_sha256_digest(experiment_fingerprint, field_name="experiment_fingerprint")
        if (
            not isinstance(candidate_index, int)
            or isinstance(candidate_index, bool)
            or candidate_index < 0
        ):
            raise ValueError("candidate_index must be a non-negative integer")
        owner = _principal_identity(principal)
        definition = await self._persistence.walk_forward_plans.load(
            principal=owner,
            experiment_fingerprint=experiment_fingerprint,
        )
        if not isinstance(definition, WalkForwardExecutionDefinition):
            raise ApiAdapterError(
                ApiError(
                    ApiErrorCode.NOT_FOUND,
                    "walk-forward plan is unavailable to this owner",
                    request_id,
                    404,
                )
            )
        initialized = await self.initialize_walk_forward_training(
            principal=owner,
            request_id=request_id,
            definition=definition,
        )
        state = initialized.state
        if candidate_index >= len(state.candidates):
            raise ValueError("candidate_index is outside the walk-forward training queue")
        candidate = state.candidates[candidate_index]
        if state.cancellation_requested:
            raise ApiAdapterError(
                ApiError(
                    ApiErrorCode.CONFLICT,
                    "walk-forward training cancellation has been requested",
                    request_id,
                    409,
                    False,
                    {"experiment_fingerprint": experiment_fingerprint},
                )
            )
        if candidate.phase in {SearchCandidatePhase.SUCCEEDED, SearchCandidatePhase.CANCELLED}:
            raise ApiAdapterError(
                ApiError(
                    ApiErrorCode.CONFLICT,
                    "walk-forward training candidate is already terminal",
                    request_id,
                    409,
                    False,
                    {"candidate_index": candidate_index},
                )
            )

        if candidate.phase is SearchCandidatePhase.RUNNING:
            if candidate.attempt_id is None:
                raise ValueError("running walk-forward candidate has no durable attempt identity")
            attempt_id = candidate.attempt_id
            ordinal = candidate.attempt_count
        else:
            ordinal = candidate.attempt_count + 1
            attempt_id = content_digest(
                {
                    "schema": "strategy-lab.walk-forward-training-attempt.v1",
                    "owner_id": owner.id,
                    "experiment_fingerprint": experiment_fingerprint,
                    "candidate_index": candidate_index,
                    "trial_fingerprint": candidate.trial_fingerprint,
                    "ordinal": ordinal,
                }
            )
        attempt_domain_fingerprint = content_digest(
            {"attempt_id": attempt_id, "trial_id": candidate.trial_fingerprint, "ordinal": ordinal}
        )
        attempt = await self._resources.get_domain_contract_by_fingerprint(
            principal=owner,
            resource_type=ApiResourceType.ATTEMPT,
            fingerprint=attempt_domain_fingerprint,
        )
        if attempt is None:
            created_at = self._clock()
            proposed = RunAttempt(
                attempt_id=attempt_id,
                trial_id=candidate.trial_fingerprint,
                ordinal=ordinal,
                state=AttemptState.QUEUED,
                created_at=created_at,
            )
            attributes = dict(freeze_json(proposed))
            attributes["resource_id"] = proposed.attempt_id
            mutation = ResourceMutationRequest(
                ApiResourceType.ATTEMPT,
                f"walk-forward-attempt:{attempt_id}",
                {"attributes": attributes},
                created_at,
            )
            created = await self.create_resource(
                principal=owner,
                request_id=content_digest(
                    {"attempt_id": attempt_id, "purpose": "publish_walk_forward_attempt"}
                ),
                request=mutation,
            )
            attempt = (
                normalize_resource_attributes(
                    ApiResourceType.ATTEMPT,
                    created.receipt.resource.attributes,
                ).typed_contract
                if created.receipt is not None
                else None
            )
            if attempt is None:
                # Another request may have won the immutable attempt-identity
                # reservation; accept only that exact owner-visible winner.
                attempt = await self._resources.get_domain_contract_by_fingerprint(
                    principal=owner,
                    resource_type=ApiResourceType.ATTEMPT,
                    fingerprint=attempt_domain_fingerprint,
                )
        if (
            not isinstance(attempt, RunAttempt)
            or attempt.attempt_id != attempt_id
            or attempt.trial_id != candidate.trial_fingerprint
            or attempt.ordinal != ordinal
            or attempt.state is not AttemptState.QUEUED
        ):
            raise ValueError(
                "walk-forward attempt resource is missing or differs from its queue slot"
            )

        intent = SearchDispatchIntent(
            idempotency_key=idempotency_key,
            attempt_id=attempt_id,
            queue_name=queue_name,
            created_at=attempt.created_at,
        )
        return await self.dispatch_search_candidate(
            principal=owner,
            request_id=request_id,
            experiment_fingerprint=experiment_fingerprint,
            candidate_index=candidate_index,
            attempt_id=attempt_id,
            dispatch_intent=intent,
        )

    async def dispatch_walk_forward_ready_candidates(
        self,
        *,
        principal: Any,
        request_id: str,
        idempotency_key: str,
        experiment_fingerprint: str,
        queue_name: str,
        replay_running: bool = True,
    ) -> tuple[tuple[int, SearchDispatchResolution], ...]:
        """Dispatch every nonterminal slot in the current persisted phase.

        Each candidate gets a deterministic idempotency key derived from the
        request key and its attempt ordinal. A capacity-saturated result stops
        the batch; retrying the same request replays already accepted slots and
        continues admitting the remainder as capacity becomes available.
        """

        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must not be empty")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValueError("idempotency_key must not be empty")
        if not isinstance(queue_name, str) or not queue_name.strip():
            raise ValueError("queue_name must not be empty")
        if not isinstance(replay_running, bool):
            raise TypeError("replay_running must be a boolean")
        require_sha256_digest(experiment_fingerprint, field_name="experiment_fingerprint")
        owner = _principal_identity(principal)
        definition = await self._persistence.walk_forward_plans.load(
            principal=owner,
            experiment_fingerprint=experiment_fingerprint,
        )
        if not isinstance(definition, WalkForwardExecutionDefinition):
            raise ApiAdapterError(
                ApiError(
                    ApiErrorCode.NOT_FOUND,
                    "walk-forward plan is unavailable to this owner",
                    request_id,
                    404,
                )
            )
        initialized = await self.initialize_walk_forward_training(
            principal=owner,
            request_id=request_id,
            definition=definition,
        )
        if initialized.state.cancellation_requested:
            raise ApiAdapterError(
                ApiError(
                    ApiErrorCode.CONFLICT,
                    "walk-forward cancellation has been requested",
                    request_id,
                    409,
                    False,
                    {"experiment_fingerprint": experiment_fingerprint},
                )
            )

        dispatched: list[tuple[int, SearchDispatchResolution]] = []
        for candidate in initialized.state.candidates:
            if candidate.phase in {
                SearchCandidatePhase.SUCCEEDED,
                SearchCandidatePhase.CANCELLED,
            }:
                continue
            if candidate.phase is SearchCandidatePhase.RUNNING and not replay_running:
                continue
            ordinal = (
                candidate.attempt_count
                if candidate.phase is SearchCandidatePhase.RUNNING
                else candidate.attempt_count + 1
            )
            slot_key = content_digest(
                {
                    "schema": "strategy-lab.walk-forward-bulk-dispatch.v1",
                    "request_key": idempotency_key,
                    "experiment_fingerprint": experiment_fingerprint,
                    "candidate_index": candidate.candidate_index,
                    "attempt_ordinal": ordinal,
                }
            )
            slot_request_id = content_digest(
                {
                    "request_id": request_id,
                    "candidate_index": candidate.candidate_index,
                    "attempt_ordinal": ordinal,
                }
            )
            resolution = await self.dispatch_walk_forward_training_candidate(
                principal=owner,
                request_id=slot_request_id,
                idempotency_key=slot_key,
                experiment_fingerprint=experiment_fingerprint,
                candidate_index=candidate.candidate_index,
                queue_name=queue_name,
            )
            dispatched.append((candidate.candidate_index, resolution))
            if resolution.decision is SearchDispatchDecision.SATURATED:
                break
            if resolution.decision in {
                SearchDispatchDecision.CONFLICT,
                SearchDispatchDecision.REJECT,
            }:
                break
        return tuple(dispatched)

    async def reconcile_walk_forward_terminal(
        self,
        *,
        principal: Any,
        request_id: str,
        experiment_fingerprint: str,
        attempt_id: str,
        dispatch_request_fingerprint: str,
        queue_name: str,
    ) -> dict[str, Any]:
        """Advance, dispatch, or finalize walk-forward from durable completion.

        The internal worker notification is only a wake-up hint. This method
        authenticates it against PostgreSQL dispatch, search-state, and result
        completion records before changing any walk-forward state.
        """

        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must not be empty")
        require_sha256_digest(experiment_fingerprint, field_name="experiment_fingerprint")
        require_sha256_digest(
            dispatch_request_fingerprint,
            field_name="dispatch_request_fingerprint",
        )
        if not isinstance(attempt_id, str) or not attempt_id.strip():
            raise ValueError("attempt_id must not be empty")
        if not isinstance(queue_name, str) or not queue_name.strip():
            raise ValueError("queue_name must not be empty")
        owner = _principal_identity(principal)
        dispatch = await self._persistence.search_dispatch.load_by_request_fingerprint(
            dispatch_request_fingerprint
        )
        if (
            not isinstance(dispatch, SearchDispatchRecord)
            or dispatch.owner_id != owner.id
            or dispatch.experiment_fingerprint != experiment_fingerprint
            or dispatch.request.attempt_id != attempt_id
        ):
            raise ApiAdapterError(
                ApiError(
                    ApiErrorCode.AUTHORIZATION_REQUIRED,
                    "terminal progress notification differs from its durable dispatch",
                    request_id,
                    403,
                    False,
                )
            )

        definition = await self._persistence.walk_forward_plans.load(
            principal=owner,
            experiment_fingerprint=experiment_fingerprint,
        )
        if not isinstance(definition, WalkForwardExecutionDefinition):
            return {
                "decision": "not_walk_forward",
                "dispatched_candidate_indices": (),
                "summary_fingerprint": None,
            }

        state = await self._persistence.search_state.load(
            principal=owner,
            experiment_fingerprint=experiment_fingerprint,
        )
        if state is None or dispatch.candidate_index >= len(state.candidates):
            raise ValueError("terminal walk-forward candidate state is unavailable")
        candidate = state.candidates[dispatch.candidate_index]
        if (
            candidate.phase is not SearchCandidatePhase.SUCCEEDED
            or candidate.attempt_id != attempt_id
            or candidate.result_fingerprint is None
        ):
            raise ApiAdapterError(
                ApiError(
                    ApiErrorCode.CONFLICT,
                    "terminal progress notification has no successful durable queue receipt",
                    request_id,
                    409,
                    True,
                    {"candidate_index": dispatch.candidate_index},
                )
            )
        completion_ledger = await self._persistence.result_completion.load_completion_ledger(
            principal=owner
        )
        completion = next(
            (item for item in completion_ledger.records if item.attempt_id == attempt_id),
            None,
        )
        if completion is None or completion.result_fingerprint != candidate.result_fingerprint:
            raise ValueError("terminal progress notification lacks matching completion evidence")
        if state.cancellation_requested:
            return {
                "decision": "waiting",
                "dispatched_candidate_indices": (),
                "summary_fingerprint": None,
            }

        transition = await self.append_walk_forward_oos_candidates(
            principal=owner,
            request_id=request_id,
            experiment_fingerprint=experiment_fingerprint,
        )
        state = transition.resolution.state
        expected_training_count = len(definition.training_plan.tasks)
        if transition.resolution.decision is SearchStateDecision.REJECT:
            reason = transition.resolution.rejection_reason or ""
            if "all training candidates must succeed" not in reason:
                raise ApiAdapterError(
                    ApiError(
                        ApiErrorCode.CONFLICT,
                        reason or "walk-forward phase could not be reconciled",
                        request_id,
                        409,
                        True,
                        {"experiment_fingerprint": experiment_fingerprint},
                    )
                )
        elif len(state.candidates) < expected_training_count:
            raise ValueError("walk-forward phase queue lost training candidates")

        batch_key = content_digest(
            {
                "schema": "strategy-lab.walk-forward-completion-batch.v1",
                "definition_fingerprint": definition.fingerprint,
            }
        )
        batch = await self.dispatch_walk_forward_ready_candidates(
            principal=owner,
            request_id=request_id,
            idempotency_key=batch_key,
            experiment_fingerprint=experiment_fingerprint,
            queue_name=queue_name,
            replay_running=False,
        )
        state = await self._persistence.search_state.load(
            principal=owner,
            experiment_fingerprint=experiment_fingerprint,
        )
        if state is None:
            raise ValueError("walk-forward search queue disappeared during reconciliation")
        accepted_batch = tuple(
            (index, resolution)
            for index, resolution in batch
            if resolution.decision
            in {SearchDispatchDecision.ENQUEUE, SearchDispatchDecision.REPLAY_EXISTING}
        )
        summary_fingerprint = None
        decision = "dispatched" if accepted_batch else "waiting"
        if len(state.candidates) > expected_training_count and all(
            item.phase is SearchCandidatePhase.SUCCEEDED for item in state.candidates
        ):
            summary = await self.persist_walk_forward_oos_summary(
                principal=owner,
                request_id=request_id,
                experiment_fingerprint=experiment_fingerprint,
            )
            summary_fingerprint = summary.summary.fingerprint
            decision = "finalized"
        return {
            "decision": decision,
            "dispatched_candidate_indices": tuple(index for index, _ in accepted_batch),
            "summary_fingerprint": summary_fingerprint,
        }

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
        instance = await self._persistence.forward_state.load_instance(
            principal=owner,
            instance_id=instance_id,
        )
        if target is ForwardState.WARMING_UP:
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
        should_acquire = target in {ForwardState.WARMING_UP, ForwardState.ACTIVE}
        if instance is not None and target is not instance.state:
            try:
                validate_forward_transition(instance, target, now=now.astimezone(UTC))
            except ValueError:
                # Let the durable transition adapter return its canonical
                # conflict receipt without reserving capacity for an invalid
                # state change.
                should_acquire = False
        if should_acquire and instance is not None:
            if self._forward_worker_lifecycle is None:
                raise ApiAdapterError(
                    ApiError(
                        ApiErrorCode.PRECONDITION_FAILED,
                        "forward worker lifecycle is not configured",
                        "forward-lifecycle-" + content_digest(idempotency_key)[:32],
                        412,
                        False,
                        {"reason": "a dedicated FORWARD worker profile is required"},
                    )
                )
            try:
                await self._forward_worker_lifecycle.acquire(
                    instance_id=instance_id,
                    activation_key=idempotency_key,
                    now=now.astimezone(UTC),
                )
            except ForwardWorkerCapacityUnavailable as error:
                raise ApiAdapterError(
                    ApiError(
                        ApiErrorCode.CONFLICT,
                        str(error),
                        "forward-lifecycle-" + content_digest(idempotency_key)[:32],
                        409,
                        True,
                        {"instance_id": instance_id},
                    )
                ) from error
        resolution = await self._persistence.forward_state.transition(
            principal=owner,
            instance_id=instance_id,
            target=target,
            now=now.astimezone(UTC),
            idempotency_key=idempotency_key,
        )
        if (
            target in {ForwardState.PAUSED, ForwardState.STOPPED}
            and resolution.decision
            in {
                ForwardStateMutationDecision.APPLIED,
                ForwardStateMutationDecision.REPLAY_EXISTING,
            }
            and self._forward_worker_lifecycle is not None
        ):
            await self._forward_worker_lifecycle.release(
                instance_id=instance_id,
                now=now.astimezone(UTC),
            )
        return resolution

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
            walk_forward_artifact_store=(
                None if bindings_factory is not None else _artifact_store_from_environment()
            ),
        )
    return _default_adapter


def _artifact_store_from_environment() -> LocalArtifactStore | None:
    value = os.environ.get("STRATEGY_LAB_V2_ARTIFACT_ROOT", "").strip()
    if not value:
        return None
    root = Path(value).expanduser()
    if not root.is_absolute():
        raise ValueError("STRATEGY_LAB_V2_ARTIFACT_ROOT must be absolute")
    return LocalArtifactStore(root)


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
