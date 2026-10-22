"""Owner-scoped preparation of authenticated Nautilus search dispatch evidence.

This resolver belongs in the dedicated local preparation process. It hydrates
and materializes frozen inputs synchronously, then composes the complete worker
handoff before the application performs its atomic PostgreSQL/outbox dispatch.
The API process may proxy to this resolver, but must not run this resolver
inline on its event loop.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from app.strategy_lab_v2.admission import ExecutionAdmissionLedger
from app.strategy_lab_v2.application import SearchDispatchEvidence
from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.conformance import EngineConformanceEvidence, EngineConformanceReport
from app.strategy_lab_v2.conformance_fixtures import (
    ConformanceExecutionResolution,
    NautilusRcConformanceResolution,
    build_nautilus_backtest_compatibility_binding,
    build_nautilus_backtest_execution_binding,
)
from app.strategy_lab_v2.contracts import ProductClass
from app.strategy_lab_v2.dispatch import SearchDispatchIntent
from app.strategy_lab_v2.engine_execution import NautilusExecutionScope
from app.strategy_lab_v2.execution import authorize_execution
from app.strategy_lab_v2.execution_capabilities import (
    ExecutionCapabilityBinding,
    preflight_execution_capability,
)
from app.strategy_lab_v2.lease_observations import LeaseObservationState
from app.strategy_lab_v2.lifecycle import (
    AttemptLeaseStatus,
    ExecutionAttemptLease,
    acquire_attempt_lease,
)
from app.strategy_lab_v2.local_conformance_source import (
    LocalNautilusRcConformanceEvidenceSource,
)
from app.strategy_lab_v2.nautilus_trial_materializer import (
    NautilusTrialMarketContext,
    NautilusTrialRuntimeEvidence,
    NautilusTrialRuntimeInputMaterializer,
    build_nautilus_trial_runtime_evidence,
)
from app.strategy_lab_v2.nautilus_trial_worker_request import (
    build_nautilus_trial_worker_request,
)
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile
from app.strategy_lab_v2.strategy_package_resolution import StrategyPackageArtifactResolver
from app.strategy_lab_v2.trial_hydration import HydratedNautilusTrial
from app.strategy_lab_v2.workers import (
    WorkerKind,
    WorkerPoolState,
    WorkerProfile,
    rank_available_backtest_worker_pools,
)


class NautilusTrialHydrator(Protocol):
    async def hydrate_attempt(
        self,
        *,
        principal: Any,
        attempt_resource_id: str,
    ) -> HydratedNautilusTrial: ...


class NautilusWorkerStateReader(Protocol):
    async def list_profiles(
        self,
        *,
        kind: WorkerKind,
        runtime_profile_fingerprint: str,
    ) -> tuple[WorkerProfile, ...]: ...

    async def load_pool(self, profile: WorkerProfile) -> WorkerPoolState: ...

    async def load_lease(self, lease_id: str) -> LeaseObservationState | None: ...

    async def persist_lease(self, lease: ExecutionAttemptLease) -> LeaseObservationState: ...


@dataclass(frozen=True, slots=True)
class SearchDispatchPreparationRequest:
    """Validated coordinates for resolving one owner-scoped search candidate."""

    principal: Any
    request_id: str
    experiment_fingerprint: str
    candidate_index: int
    attempt_id: str
    dispatch_intent: SearchDispatchIntent

    def __post_init__(self) -> None:
        owner = getattr(self.principal, "id", self.principal)
        if owner is None or isinstance(owner, bool) or not isinstance(owner, str | int):
            raise ValueError("authenticated principal identity is required")
        if not str(owner).strip():
            raise ValueError("authenticated principal identity is required")
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise ValueError("request_id must not be empty")
        require_sha256_digest(self.experiment_fingerprint, field_name="experiment_fingerprint")
        if (
            not isinstance(self.candidate_index, int)
            or isinstance(self.candidate_index, bool)
            or self.candidate_index < 0
        ):
            raise ValueError("candidate_index must be a non-negative integer")
        if not isinstance(self.attempt_id, str) or not self.attempt_id.strip():
            raise ValueError("attempt_id must not be empty")
        if not isinstance(self.dispatch_intent, SearchDispatchIntent):
            raise TypeError("dispatch_intent must be a SearchDispatchIntent")
        if self.dispatch_intent.attempt_id != self.attempt_id:
            raise ValueError("dispatch intent must reference the preparation attempt")

    @property
    def owner_id(self) -> str:
        return str(getattr(self.principal, "id", self.principal)).strip()

    @property
    def runtime_request_id(self) -> str:
        """Stable runtime-request identity across retries of one dispatch key."""

        return content_digest(
            {
                "owner_id": self.owner_id,
                "attempt_id": self.attempt_id,
                "idempotency_key": self.dispatch_intent.idempotency_key,
                "purpose": "strategy-lab-v2-search-runtime",
            }
        )


@dataclass(frozen=True, slots=True)
class NautilusTrialPreparationContext:
    """Trusted host/runtime evidence needed to prepare one backtest handoff.

    The context resolver supplies canonical market metadata, conformance, and
    runtime configuration from authoritative local sources. Worker profiles,
    leases, and serial-slot selection are discovered and owned by the platform
    preparation package. This value itself is never accepted from an HTTP client.
    """

    market_context: NautilusTrialMarketContext
    runtime_profile: RuntimeIsolationProfile
    admission_ledger: ExecutionAdmissionLedger
    capability_binding: ExecutionCapabilityBinding
    conformance_evidence: EngineConformanceEvidence
    conformance_report: EngineConformanceReport
    image_name: str
    output_path: str | Path
    now: datetime
    lease_duration: timedelta
    execution_scope: NautilusExecutionScope = NautilusExecutionScope.BACKTEST_AUTHORITATIVE
    requested_authoritative: bool = True
    docker_binary: str = "docker"

    @classmethod
    def from_authoritative_backtest_conformance(
        cls,
        *,
        conformance_resolution: ConformanceExecutionResolution | NautilusRcConformanceResolution,
        product_classes: frozenset[ProductClass],
        execution_models: frozenset[str],
        account_models: frozenset[str],
        market_context: NautilusTrialMarketContext,
        runtime_profile: RuntimeIsolationProfile,
        admission_ledger: ExecutionAdmissionLedger,
        image_name: str,
        output_path: str | Path,
        now: datetime,
        lease_duration: timedelta,
        docker_binary: str = "docker",
    ) -> NautilusTrialPreparationContext:
        """Construct a backtest-only host context from one exact conformance result.

        The engine binding, evidence/report pair, and isolated runtime image are
        derived together. Stable v2 or an exact-pinned release candidate can
        construct this local-backtest context; compatibility remains available
        for candidates that have not passed the required backtest checks.
        """

        if not isinstance(
            conformance_resolution,
            ConformanceExecutionResolution | NautilusRcConformanceResolution,
        ):
            raise TypeError("conformance_resolution must be a complete or Nautilus RC resolution")
        if not isinstance(runtime_profile, RuntimeIsolationProfile):
            raise TypeError("runtime_profile must be a RuntimeIsolationProfile")
        release_pin = conformance_resolution.evidence.release_pin
        if (
            release_pin is None
            or runtime_profile.runtime_image_digest != release_pin.runtime_image_digest
        ):
            raise ValueError("runtime profile differs from the exact Nautilus release pin")
        capability_binding = build_nautilus_backtest_execution_binding(
            conformance_resolution,
            product_classes=product_classes,
            execution_models=execution_models,
            account_models=account_models,
        )
        return cls(
            market_context=market_context,
            runtime_profile=runtime_profile,
            admission_ledger=admission_ledger,
            capability_binding=capability_binding,
            conformance_evidence=conformance_resolution.evidence,
            conformance_report=conformance_resolution.report,
            image_name=image_name,
            output_path=output_path,
            now=now,
            lease_duration=lease_duration,
            execution_scope=NautilusExecutionScope.BACKTEST_AUTHORITATIVE,
            requested_authoritative=True,
            docker_binary=docker_binary,
        )

    @classmethod
    def from_compatibility_backtest_conformance(
        cls,
        *,
        conformance_resolution: ConformanceExecutionResolution | NautilusRcConformanceResolution,
        product_classes: frozenset[ProductClass],
        execution_models: frozenset[str],
        account_models: frozenset[str],
        market_context: NautilusTrialMarketContext,
        runtime_profile: RuntimeIsolationProfile,
        admission_ledger: ExecutionAdmissionLedger,
        image_name: str,
        output_path: str | Path,
        now: datetime,
        lease_duration: timedelta,
        docker_binary: str = "docker",
    ) -> NautilusTrialPreparationContext:
        """Construct a non-authoritative search context for an exact pinned build."""

        if not isinstance(
            conformance_resolution,
            ConformanceExecutionResolution | NautilusRcConformanceResolution,
        ):
            raise TypeError("conformance_resolution must be a complete or Nautilus RC resolution")
        if not isinstance(runtime_profile, RuntimeIsolationProfile):
            raise TypeError("runtime_profile must be a RuntimeIsolationProfile")
        release_pin = conformance_resolution.evidence.release_pin
        if (
            release_pin is None
            or runtime_profile.runtime_image_digest != release_pin.runtime_image_digest
        ):
            raise ValueError("runtime profile differs from the exact Nautilus release pin")
        capability_binding = build_nautilus_backtest_compatibility_binding(
            conformance_resolution,
            product_classes=product_classes,
            execution_models=execution_models,
            account_models=account_models,
        )
        return cls(
            market_context=market_context,
            runtime_profile=runtime_profile,
            admission_ledger=admission_ledger,
            capability_binding=capability_binding,
            conformance_evidence=conformance_resolution.evidence,
            conformance_report=conformance_resolution.report,
            image_name=image_name,
            output_path=output_path,
            now=now,
            lease_duration=lease_duration,
            execution_scope=NautilusExecutionScope.BACKTEST_COMPATIBILITY,
            requested_authoritative=False,
            docker_binary=docker_binary,
        )

    @classmethod
    def from_operator_pinned_local_backtest_evidence(
        cls,
        *,
        conformance_source: LocalNautilusRcConformanceEvidenceSource,
        product_classes: frozenset[ProductClass],
        execution_models: frozenset[str],
        account_models: frozenset[str],
        market_context: NautilusTrialMarketContext,
        runtime_profile: RuntimeIsolationProfile,
        admission_ledger: ExecutionAdmissionLedger,
        image_name: str,
        output_path: str | Path,
        now: datetime,
        lease_duration: timedelta,
        docker_binary: str = "docker",
    ) -> NautilusTrialPreparationContext:
        """Bind search preparation to content-addressed RC evidence as non-authoritative."""

        if not isinstance(conformance_source, LocalNautilusRcConformanceEvidenceSource):
            raise TypeError("conformance_source must be a LocalNautilusRcConformanceEvidenceSource")
        return cls.from_compatibility_backtest_conformance(
            conformance_resolution=conformance_source.load(),
            product_classes=product_classes,
            execution_models=execution_models,
            account_models=account_models,
            market_context=market_context,
            runtime_profile=runtime_profile,
            admission_ledger=admission_ledger,
            image_name=image_name,
            output_path=output_path,
            now=now,
            lease_duration=lease_duration,
            docker_binary=docker_binary,
        )

    def __post_init__(self) -> None:
        expected = {
            "market_context": NautilusTrialMarketContext,
            "runtime_profile": RuntimeIsolationProfile,
            "admission_ledger": ExecutionAdmissionLedger,
            "capability_binding": ExecutionCapabilityBinding,
            "conformance_evidence": EngineConformanceEvidence,
            "conformance_report": EngineConformanceReport,
            "execution_scope": NautilusExecutionScope,
        }
        for name, value_type in expected.items():
            if not isinstance(getattr(self, name), value_type):
                raise TypeError(f"{name} must be a {value_type.__name__}")
        if not isinstance(self.lease_duration, timedelta) or self.lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        if not isinstance(self.image_name, str) or not self.image_name.strip():
            raise ValueError("image_name must not be empty")
        if not isinstance(self.output_path, str | Path) or not str(self.output_path).strip():
            raise ValueError("output_path must not be empty")
        if not isinstance(self.now, datetime):
            raise TypeError("now must be a datetime")
        if self.now.tzinfo is None or self.now.utcoffset() is None:
            raise ValueError("preparation time must be timezone-aware")
        if not isinstance(self.requested_authoritative, bool):
            raise TypeError("requested_authoritative must be a boolean")
        if not isinstance(self.docker_binary, str) or not self.docker_binary.strip():
            raise ValueError("docker_binary must not be empty")
        if (
            self.capability_binding.engine_name.lower()
            != self.conformance_evidence.engine_id.lower()
            or self.capability_binding.engine_version != self.conformance_evidence.engine_version
            or self.capability_binding.engine_build_digest != self.conformance_evidence.build_digest
            or self.capability_binding.conformance_fingerprint
            != self.conformance_evidence.fingerprint
        ):
            raise ValueError("capability binding differs from exact engine conformance evidence")
        object.__setattr__(self, "now", self.now.astimezone(UTC))


PreparationContextResolver = Callable[
    [SearchDispatchPreparationRequest, HydratedNautilusTrial],
    NautilusTrialPreparationContext | Awaitable[NautilusTrialPreparationContext],
]


class NautilusTrialSearchDispatchEvidenceResolver:
    """Resolve and compose complete typed evidence for one search dispatch.

    ``context_resolver`` is the explicit host adapter boundary for canonical
    market metadata and current execution authority. Database-backed hosts can
    use their resource, worker-state, and conformance adapters there. Frozen
    artifact decoding and worker request construction remain owned here.
    """

    def __init__(
        self,
        *,
        domain_hydrator: NautilusTrialHydrator,
        runtime_materializer: NautilusTrialRuntimeInputMaterializer,
        strategy_package_resolver: StrategyPackageArtifactResolver,
        artifact_store: LocalArtifactStore,
        worker_state_reader: NautilusWorkerStateReader,
        context_resolver: PreparationContextResolver,
    ) -> None:
        if not callable(getattr(domain_hydrator, "hydrate_attempt", None)):
            raise TypeError("domain_hydrator must provide hydrate_attempt()")
        if not isinstance(runtime_materializer, NautilusTrialRuntimeInputMaterializer):
            raise TypeError("runtime_materializer must be a NautilusTrialRuntimeInputMaterializer")
        if not isinstance(strategy_package_resolver, StrategyPackageArtifactResolver):
            raise TypeError("strategy_package_resolver must be a StrategyPackageArtifactResolver")
        if not isinstance(artifact_store, LocalArtifactStore):
            raise TypeError("artifact_store must be a LocalArtifactStore")
        if any(
            not callable(getattr(worker_state_reader, method, None))
            for method in ("list_profiles", "load_pool", "load_lease", "persist_lease")
        ):
            raise TypeError(
                "worker_state_reader must provide list_profiles(), load_pool(), "
                "load_lease(), and persist_lease()"
            )
        if not callable(context_resolver):
            raise TypeError("context_resolver must be callable")
        if runtime_materializer.artifact_store is not artifact_store:
            raise ValueError(
                "runtime materializer and dispatch resolver must share one artifact store"
            )
        if strategy_package_resolver.store is not artifact_store:
            raise ValueError(
                "strategy package resolver and dispatch resolver must share one artifact store"
            )
        if runtime_materializer.strategy_package_resolver is not strategy_package_resolver:
            raise ValueError(
                "runtime materializer and dispatch resolver must share one package resolver"
            )
        self._domain_hydrator = domain_hydrator
        self._runtime_materializer = runtime_materializer
        self._artifact_store = artifact_store
        self._worker_state_reader = worker_state_reader
        self._context_resolver = context_resolver

    async def __call__(
        self,
        *,
        principal: Any,
        request_id: str,
        experiment_fingerprint: str,
        candidate_index: int,
        attempt_id: str,
        dispatch_intent: SearchDispatchIntent,
    ) -> SearchDispatchEvidence:
        """Hydrate, materialize, authorize, and compose one immutable handoff."""

        request = SearchDispatchPreparationRequest(
            principal,
            request_id,
            experiment_fingerprint,
            candidate_index,
            attempt_id,
            dispatch_intent,
        )
        graph = await self._domain_hydrator.hydrate_attempt(
            principal=request.principal,
            attempt_resource_id=request.attempt_id,
        )
        if not isinstance(graph, HydratedNautilusTrial):
            raise TypeError("domain hydrator must return a HydratedNautilusTrial")
        if graph.experiment.fingerprint != request.experiment_fingerprint:
            raise ValueError("search candidate experiment differs from its owner-hydrated trial")
        if graph.attempt.attempt_id != request.attempt_id:
            raise ValueError("search candidate attempt differs from its owner-hydrated trial")

        context_result = self._context_resolver(request, graph)
        context = await context_result if inspect.isawaitable(context_result) else context_result
        if not isinstance(context, NautilusTrialPreparationContext):
            raise TypeError("context_resolver must return NautilusTrialPreparationContext")
        materialized = self._runtime_materializer.materialize(
            graph=graph,
            market_context=context.market_context,
        )
        source_validation = materialized.source_validation
        capability_preflight = preflight_execution_capability(
            graph.trial.preflight_report,
            context.capability_binding,
        )
        worker_pool, lease_state, reservation_id = await self._select_worker_assignment(
            request=request,
            graph=graph,
            context=context,
        )
        authorization = authorize_execution(
            graph.trial,
            graph.attempt,
            source_validation,
            capability_preflight,
            lease_state.lease,
            now=context.now,
        )
        runtime_evidence: NautilusTrialRuntimeEvidence = build_nautilus_trial_runtime_evidence(
            materialized,
            context.runtime_profile,
            request_id=request.runtime_request_id,
            submitted_at=dispatch_intent.created_at,
        )
        worker_request = build_nautilus_trial_worker_request(
            runtime_evidence,
            authorization,
            artifact_store=self._artifact_store,
            runtime_profile=context.runtime_profile,
            worker_pool=worker_pool,
            admission_ledger=context.admission_ledger,
            reservation_id=reservation_id,
            lease_state=lease_state,
            conformance_evidence=context.conformance_evidence,
            conformance_report=context.conformance_report,
            image_name=context.image_name,
            output_path=context.output_path,
            now=context.now,
            execution_scope=context.execution_scope,
            requested_authoritative=context.requested_authoritative,
            docker_binary=context.docker_binary,
        )
        return SearchDispatchEvidence(
            authorization=authorization,
            trial_runtime_evidence=runtime_evidence,
            worker_request=worker_request,
            reservation_id=reservation_id,
            now=context.now,
        )

    async def _select_worker_assignment(
        self,
        *,
        request: SearchDispatchPreparationRequest,
        graph: HydratedNautilusTrial,
        context: NautilusTrialPreparationContext,
    ) -> tuple[WorkerPoolState, LeaseObservationState, str]:
        profiles = tuple(
            await self._worker_state_reader.list_profiles(
                kind=WorkerKind.BACKTEST,
                runtime_profile_fingerprint=context.runtime_profile.fingerprint,
            )
        )
        if any(not isinstance(profile, WorkerProfile) for profile in profiles):
            raise TypeError("worker profile discovery must return WorkerProfile values")
        if len({profile.worker_id for profile in profiles}) != len(profiles):
            raise ValueError("worker profile discovery returned duplicate worker identities")
        if tuple(sorted(profiles, key=lambda profile: profile.worker_id)) != profiles:
            raise ValueError("worker profile discovery must be deterministically ordered")
        if any(
            profile.kind is not WorkerKind.BACKTEST
            or profile.runtime_profile_fingerprint != context.runtime_profile.fingerprint
            for profile in profiles
        ):
            raise ValueError("worker profile discovery returned an inexact runtime match")

        pools: list[WorkerPoolState] = []
        for profile in profiles:
            pool = await self._worker_state_reader.load_pool(profile)
            if not isinstance(pool, WorkerPoolState):
                raise TypeError("worker state reader must return WorkerPoolState")
            if pool.profile != profile:
                raise ValueError("persisted worker pool differs from its discovered profile")
            pools.append(pool)

        existing_admission = next(
            (
                item
                for item in context.admission_ledger.admissions
                if item.attempt_id == request.attempt_id
            ),
            None,
        )
        ranked_pools: tuple[WorkerPoolState, ...]
        if existing_admission is not None:
            assigned_profile: WorkerProfile | None = next(
                (
                    item
                    for item in profiles
                    if item.worker_id == existing_admission.worker_id
                    and item.fingerprint == existing_admission.worker_profile_fingerprint
                ),
                None,
            )
            if assigned_profile is None:
                raise ValueError("existing attempt admission references an unavailable worker")
            pool = next(item for item in pools if item.profile == assigned_profile)
            if not any(
                reservation.active
                and reservation.attempt_id == request.attempt_id
                and reservation.reservation_id == existing_admission.reservation_id
                for reservation in pool.reservations
            ):
                raise ValueError("existing attempt admission has no matching active reservation")
            ranked_pools = (pool,)
        else:
            if any(
                reservation.active and reservation.attempt_id == request.attempt_id
                for pool in pools
                for reservation in pool.reservations
            ):
                raise ValueError("active worker reservation is missing its admission receipt")
            ranked_pools = rank_available_backtest_worker_pools(
                pools,
                attempt_id=request.attempt_id,
            )

        lease_started_at = max(
            request.dispatch_intent.created_at,
            graph.attempt.updated_at or graph.attempt.created_at,
        )
        if lease_started_at > context.now:
            raise ValueError("worker lease start cannot follow preparation time")
        for pool in ranked_pools:
            profile = pool.profile
            lease_id = content_digest(
                {
                    "attempt_id": request.attempt_id,
                    "idempotency_key": request.dispatch_intent.idempotency_key,
                    "purpose": "strategy-lab-v2-search-worker-lease-v1",
                    "worker_id": profile.worker_id,
                }
            )
            reservation_id = content_digest(
                {
                    "attempt_id": request.attempt_id,
                    "idempotency_key": request.dispatch_intent.idempotency_key,
                    "purpose": "strategy-lab-v2-search-worker-reservation-v1",
                    "worker_id": profile.worker_id,
                }
            )
            if existing_admission is not None and (
                existing_admission.reservation_id != reservation_id
            ):
                raise ValueError("existing admission differs from deterministic worker assignment")

            lease_state = await self._worker_state_reader.load_lease(lease_id)
            if lease_state is None:
                lease = acquire_attempt_lease(
                    graph.attempt,
                    worker_id=profile.worker_id,
                    lease_id=lease_id,
                    now=lease_started_at,
                    lease_duration=context.lease_duration,
                )
                if lease.status_at(context.now) is not AttemptLeaseStatus.ACTIVE:
                    continue
                lease_state = await self._worker_state_reader.persist_lease(lease)
            if not isinstance(lease_state, LeaseObservationState):
                raise TypeError("worker state reader must return LeaseObservationState")
            lease = lease_state.lease
            if (
                lease.attempt_id != request.attempt_id
                or lease.worker_id != profile.worker_id
                or lease.lease_id != lease_id
            ):
                raise ValueError("persisted worker lease differs from its deterministic identity")
            if lease.status_at(context.now) is not AttemptLeaseStatus.ACTIVE:
                if existing_admission is not None:
                    raise ValueError("persisted execution lease is not active at preparation time")
                continue
            return pool, lease_state, reservation_id

        raise RuntimeError("no available serial backtest worker profile matches this runtime")


__all__ = [
    "NautilusTrialPreparationContext",
    "NautilusTrialSearchDispatchEvidenceResolver",
    "PreparationContextResolver",
    "SearchDispatchPreparationRequest",
]
