"""Application-owned composition of the Strategy Lab v2 PostgreSQL adapters."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from app.strategy_lab_v2.api_resources import (
    ApiResourceType,
    ResourceDocument,
    ResourceIdentifier,
)
from app.strategy_lab_v2.artifact_application import (
    LocalArtifactCleanupService,
    LocalArtifactPublicationService,
    LocalArtifactRetentionService,
)
from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.outbox_application import OutboxRelayService
from app.strategy_lab_v2.postgres_acquisition import PostgresAcquisitionAdapter
from app.strategy_lab_v2.postgres_artifact_commit import PostgresArtifactCommitAdapter
from app.strategy_lab_v2.postgres_artifact_retention import PostgresArtifactRetentionAdapter
from app.strategy_lab_v2.postgres_capability import PostgresCapabilityAdapter
from app.strategy_lab_v2.postgres_commands import PostgresCommandAdapter
from app.strategy_lab_v2.postgres_coverage import PostgresCoverageAdapter
from app.strategy_lab_v2.postgres_event_transaction import (
    PostgresExecutionEventTransactionAdapter,
)
from app.strategy_lab_v2.postgres_execution_state import PostgresExecutionStateAdapter
from app.strategy_lab_v2.postgres_execution_summary import PostgresExecutionSummaryAdapter
from app.strategy_lab_v2.postgres_forward_account import PostgresForwardAccountAdapter
from app.strategy_lab_v2.postgres_forward_dispatch import PostgresForwardEventDispatchAdapter
from app.strategy_lab_v2.postgres_forward_state import PostgresForwardStateAdapter
from app.strategy_lab_v2.postgres_legacy import PostgresLegacyImportAdapter
from app.strategy_lab_v2.postgres_lineage import PostgresLineageAdapter
from app.strategy_lab_v2.postgres_metrics import PostgresMetricsAdapter
from app.strategy_lab_v2.postgres_resources import PostgresResourceReader
from app.strategy_lab_v2.postgres_result_completion import PostgresResultCompletionAdapter
from app.strategy_lab_v2.postgres_result_materialization import PostgresResultMaterializationAdapter
from app.strategy_lab_v2.postgres_result_publication import PostgresResultPublicationAdapter
from app.strategy_lab_v2.postgres_runtime_execution import PostgresRuntimeExecutionAdapter
from app.strategy_lab_v2.postgres_runtime_receipts import PostgresRuntimeReceiptAdapter
from app.strategy_lab_v2.postgres_search_dispatch import (
    PostgresSearchDispatchAdapter,
    SearchDispatchRecord,
)
from app.strategy_lab_v2.postgres_search_state import PostgresSearchStateAdapter
from app.strategy_lab_v2.postgres_snapshot_coverage import PostgresSnapshotCoverageAdapter
from app.strategy_lab_v2.postgres_storage import PostgresAggregateStore
from app.strategy_lab_v2.postgres_submission import PostgresSubmissionDispatchAdapter
from app.strategy_lab_v2.postgres_worker_recovery import PostgresWorkerRecoveryAdapter
from app.strategy_lab_v2.postgres_worker_settlement import PostgresWorkerSettlementAdapter
from app.strategy_lab_v2.postgres_worker_state import PostgresWorkerStateAdapter
from app.strategy_lab_v2.redis_transport import RedisDispatchTransport
from app.strategy_lab_v2.submissions import SubmissionReceipt
from app.strategy_lab_v2.worker_evidence import (
    WorkerSubmissionBinding,
    WorkerTerminalEvidenceInputs,
    WorkerTerminalEvidenceLookup,
)
from app.strategy_lab_v2.worker_evidence_resolution import (
    ArtifactPlanResolver,
    WorkerRuntimeErrorFactory,
    create_worker_terminal_evidence_resolver,
)
from app.strategy_lab_v2.worker_terminal_adapter import (
    PostgresWorkerTerminalAdapter,
    WorkerTerminalEvidenceResolver,
)


def _record_document(
    resource_type: ApiResourceType,
    resource_id: str,
    record: Any,
    revision_digest: str,
) -> ResourceDocument:
    """Project one authenticated relational read model into the REST envelope."""

    return ResourceDocument(
        ResourceIdentifier(resource_type, resource_id, revision_digest=revision_digest),
        attributes=asdict(record),
        meta={"projection": "postgres", "record_fingerprint": revision_digest},
    )


SearchDispatchBindingResolver = Callable[
    [SearchDispatchRecord],
    Awaitable[WorkerSubmissionBinding | None] | WorkerSubmissionBinding | None,
]


@dataclass(frozen=True, slots=True)
class PostgresStrategyLabV2Persistence:
    """All durable v2 adapters sharing one async SQLAlchemy session factory."""

    aggregate_store: PostgresAggregateStore
    resources: PostgresResourceReader
    acquisition: PostgresAcquisitionAdapter
    artifact_commits: PostgresArtifactCommitAdapter
    artifact_retention: PostgresArtifactRetentionAdapter
    capability: PostgresCapabilityAdapter
    commands: PostgresCommandAdapter
    coverage: PostgresCoverageAdapter
    execution_events: PostgresExecutionEventTransactionAdapter
    execution_state: PostgresExecutionStateAdapter
    execution_summaries: PostgresExecutionSummaryAdapter
    forward_state: PostgresForwardStateAdapter
    forward_dispatch: PostgresForwardEventDispatchAdapter
    forward_account: PostgresForwardAccountAdapter
    legacy_imports: PostgresLegacyImportAdapter
    lineage: PostgresLineageAdapter
    metrics: PostgresMetricsAdapter
    result_completion: PostgresResultCompletionAdapter
    result_materialization: PostgresResultMaterializationAdapter
    result_publication: PostgresResultPublicationAdapter
    runtime_execution: PostgresRuntimeExecutionAdapter
    runtime_receipts: PostgresRuntimeReceiptAdapter
    search_state: PostgresSearchStateAdapter
    search_dispatch: PostgresSearchDispatchAdapter
    snapshot_coverage: PostgresSnapshotCoverageAdapter
    submissions: PostgresSubmissionDispatchAdapter
    worker_state: PostgresWorkerStateAdapter
    worker_settlements: PostgresWorkerSettlementAdapter
    worker_recoveries: PostgresWorkerRecoveryAdapter

    @classmethod
    def build(
        cls,
        session_factory: Callable[[], Any],
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> PostgresStrategyLabV2Persistence:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        if not callable(clock):
            raise TypeError("clock must be callable")
        aggregate_store = PostgresAggregateStore(session_factory)
        execution_state = PostgresExecutionStateAdapter(session_factory)
        execution_summaries = PostgresExecutionSummaryAdapter(session_factory)
        forward_state = PostgresForwardStateAdapter(session_factory)
        forward_dispatch = PostgresForwardEventDispatchAdapter(
            session_factory, forward_state=forward_state
        )
        forward_account = PostgresForwardAccountAdapter(session_factory)
        result_materialization = PostgresResultMaterializationAdapter(session_factory)
        metrics = PostgresMetricsAdapter(session_factory)
        capability = PostgresCapabilityAdapter(session_factory)
        legacy_imports = PostgresLegacyImportAdapter(session_factory)

        async def attempt_projection(*, principal: Any) -> tuple[ResourceDocument, ...]:
            summaries = await execution_summaries.load_all(principal=principal)
            return tuple(
                _record_document(
                    ApiResourceType.ATTEMPT,
                    summary.attempt_id,
                    summary,
                    summary.fingerprint,
                )
                for summary in summaries
            )

        async def metric_set_projection(*, principal: Any) -> tuple[ResourceDocument, ...]:
            metric_sets = await metrics.load_all_metric_sets(principal=principal)
            return tuple(
                _record_document(
                    ApiResourceType.METRIC_SET,
                    metric_set.metric_set_id,
                    metric_set,
                    metric_set.fingerprint,
                )
                for metric_set in metric_sets
            )

        async def forward_instance_projection(*, principal: Any) -> tuple[ResourceDocument, ...]:
            instances = await forward_state.load_all(principal=principal)
            return tuple(
                _record_document(
                    ApiResourceType.FORWARD_INSTANCE,
                    instance.instance_id,
                    instance,
                    content_digest(instance),
                )
                for instance in instances
            )

        async def artifact_projection(*, principal: Any) -> tuple[ResourceDocument, ...]:
            references = await result_materialization.load_artifacts(principal=principal)
            grouped: dict[str, list[Any]] = {}
            for reference in references:
                grouped.setdefault(reference.content_digest, []).append(reference)
            documents: list[ResourceDocument] = []
            for digest in sorted(grouped):
                items = tuple(grouped[digest])
                artifact = items[0].artifact
                if any(item.artifact != artifact for item in items):
                    raise ValueError("artifact content identity is inconsistent across manifests")
                manifest_fingerprints = tuple(item.manifest_fingerprint for item in items)
                attempt_ids = tuple(item.attempt_id for item in items)
                trial_ids = tuple(item.trial_id for item in items)
                revision_digest = content_digest(
                    {
                        "artifact": artifact,
                        "manifest_fingerprints": manifest_fingerprints,
                        "attempt_ids": attempt_ids,
                        "trial_ids": trial_ids,
                    }
                )
                attributes = asdict(artifact)
                attributes.update(
                    {
                        "manifest_fingerprints": manifest_fingerprints,
                        "attempt_ids": attempt_ids,
                        "trial_ids": trial_ids,
                    }
                )
                documents.append(
                    ResourceDocument(
                        ResourceIdentifier(
                            ApiResourceType.ARTIFACT,
                            digest,
                            revision_digest=revision_digest,
                        ),
                        attributes=attributes,
                        relationships={
                            "attempts": tuple(
                                ResourceIdentifier(ApiResourceType.ATTEMPT, attempt_id)
                                for attempt_id in attempt_ids
                            )
                        },
                        meta={
                            "projection": "postgres",
                            "reference_count": len(items),
                        },
                    )
                )
            return tuple(documents)

        async def capability_summary_projection(*, principal: Any) -> tuple[ResourceDocument, ...]:
            summaries = await capability.load_all(principal=principal)
            return tuple(
                ResourceDocument(
                    ResourceIdentifier(
                        ApiResourceType.CAPABILITY_SUMMARY,
                        summary.fingerprint,
                        revision_digest=summary.fingerprint,
                    ),
                    attributes=asdict(summary),
                    meta={
                        "projection": "postgres",
                        "record_fingerprint": summary.fingerprint,
                        "report_fingerprint": summary.report_fingerprint,
                        "binding_fingerprint": summary.binding_fingerprint,
                    },
                )
                for summary in summaries
            )

        async def legacy_import_projection(*, principal: Any) -> tuple[ResourceDocument, ...]:
            registry = await legacy_imports.load_registry(principal=principal)
            return tuple(
                ResourceDocument(
                    ResourceIdentifier(
                        ApiResourceType.LEGACY_IMPORT,
                        record.original.legacy_id,
                        revision_digest=record.fingerprint,
                    ),
                    attributes=asdict(record),
                    meta={
                        "projection": "postgres",
                        "record_fingerprint": record.fingerprint,
                        "request_fingerprint": record.request_fingerprint,
                        "replay_equivalent": False,
                    },
                )
                for record in registry.records
            )

        search_state = PostgresSearchStateAdapter(session_factory)
        worker_state = PostgresWorkerStateAdapter(session_factory)
        return cls(
            aggregate_store=aggregate_store,
            resources=PostgresResourceReader(
                aggregate_store,
                projections={
                    ApiResourceType.ATTEMPT: attempt_projection,
                    ApiResourceType.METRIC_SET: metric_set_projection,
                    ApiResourceType.FORWARD_INSTANCE: forward_instance_projection,
                    ApiResourceType.ARTIFACT: artifact_projection,
                    ApiResourceType.CAPABILITY_SUMMARY: capability_summary_projection,
                    ApiResourceType.LEGACY_IMPORT: legacy_import_projection,
                },
            ),
            acquisition=PostgresAcquisitionAdapter(session_factory),
            artifact_commits=PostgresArtifactCommitAdapter(session_factory),
            artifact_retention=PostgresArtifactRetentionAdapter(session_factory),
            capability=capability,
            commands=PostgresCommandAdapter(
                session_factory,
                execution_state.read_context,
                clock=clock,
            ),
            coverage=PostgresCoverageAdapter(session_factory),
            execution_events=PostgresExecutionEventTransactionAdapter(session_factory),
            execution_state=execution_state,
            execution_summaries=execution_summaries,
            forward_state=forward_state,
            forward_dispatch=forward_dispatch,
            forward_account=forward_account,
            legacy_imports=legacy_imports,
            lineage=PostgresLineageAdapter(session_factory),
            metrics=metrics,
            result_completion=PostgresResultCompletionAdapter(session_factory),
            result_materialization=result_materialization,
            result_publication=PostgresResultPublicationAdapter(session_factory),
            runtime_execution=PostgresRuntimeExecutionAdapter(session_factory),
            runtime_receipts=PostgresRuntimeReceiptAdapter(session_factory),
            search_state=search_state,
            search_dispatch=PostgresSearchDispatchAdapter(
                session_factory, search_state=search_state, worker_state=worker_state
            ),
            snapshot_coverage=PostgresSnapshotCoverageAdapter(session_factory),
            submissions=PostgresSubmissionDispatchAdapter(session_factory, clock=clock),
            worker_state=worker_state,
            worker_settlements=PostgresWorkerSettlementAdapter(session_factory),
            worker_recoveries=PostgresWorkerRecoveryAdapter(
                session_factory,
                worker_state=worker_state,
            ),
        )

    def artifact_publication(self, root: str | os.PathLike[str]) -> LocalArtifactPublicationService:
        """Create a byte/commit publication service for an explicit artifact root."""

        return LocalArtifactPublicationService(
            LocalArtifactStore(root),
            self.artifact_commits,
        )

    def artifact_retention_service(
        self, root: str | os.PathLike[str]
    ) -> LocalArtifactRetentionService:
        """Create a retention-aware byte collector for an explicit artifact root."""

        return LocalArtifactRetentionService(
            LocalArtifactStore(root),
            self.artifact_retention,
        )

    def artifact_cleanup_service(self, root: str | os.PathLike[str]) -> LocalArtifactCleanupService:
        """Create an orphan reconciler over this bundle's commit ledger."""

        return LocalArtifactCleanupService(
            LocalArtifactStore(root),
            self.artifact_commits,
        )

    def outbox_relay(self, transport: RedisDispatchTransport) -> OutboxRelayService:
        """Create a Redis relay backed by this bundle's authoritative outbox."""

        return OutboxRelayService(self.execution_events, transport)

    def worker_terminal_writer(
        self,
        evidence_resolver: WorkerTerminalEvidenceResolver,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> PostgresWorkerTerminalAdapter:
        """Create the terminal callback used by the dedicated worker service.

        The resolver is the narrow application seam for authenticated
        principal/submission/result evidence.  All durable v2 adapters remain
        package-owned and share this persistence bundle.
        """

        return PostgresWorkerTerminalAdapter(
            evidence_resolver,
            runtime_execution=self.runtime_execution,
            execution_state=self.execution_state,
            execution_summaries=self.execution_summaries,
            result_publication=self.result_publication,
            result_completion=self.result_completion,
            result_materialization=self.result_materialization,
            metrics=self.metrics,
            worker_state=self.worker_state,
            settlements=self.worker_settlements,
            clock=clock,
        )

    async def load_worker_terminal_evidence_inputs(
        self,
        *,
        principal: Any,
        attempt_id: str,
        submission: SubmissionReceipt | None = None,
    ) -> WorkerTerminalEvidenceInputs:
        """Load authenticated durable inputs for an application resolver.

        The individual adapters retain their own transaction and integrity
        checks. This composition deliberately does not claim one cross-table
        transaction; the resolver must treat missing or changing state as a
        retry and keep the immutable attempt binding from its worker context.
        """

        if submission is None:
            submission = await self.submissions.load_submission(
                principal=principal, attempt_id=attempt_id
            )
        elif not isinstance(submission, SubmissionReceipt):
            raise TypeError("submission must be a SubmissionReceipt or None")
        execution = await self.execution_state.read_context(
            principal=principal, attempt_id=attempt_id
        )
        manifest = await self.result_materialization.load_manifest(
            principal=principal, attempt_id=attempt_id
        )
        publications = await self.result_publication.load_for_attempt(
            principal=principal, attempt_id=attempt_id
        )
        return WorkerTerminalEvidenceInputs(
            attempt_id=attempt_id,
            submission=submission,
            execution=execution,
            manifest=manifest,
            publications=publications,
        )

    async def load_worker_terminal_evidence_for_request(
        self,
        *,
        request_fingerprint: str,
        attempt_id: str,
        search_dispatch_binding_resolver: SearchDispatchBindingResolver | None = None,
    ) -> WorkerTerminalEvidenceLookup | None:
        """Resolve a Redis dispatch identity and load authenticated evidence.

        Submission-backed queues join their dispatch row to the accepted
        submission receipt. Search-dispatch queues require an explicit
        host-owned resolver to bind their dispatch record to that authoritative
        submission receipt; without that seam, the lookup fails closed.
        """

        if search_dispatch_binding_resolver is not None and not callable(
            search_dispatch_binding_resolver
        ):
            raise TypeError("search_dispatch_binding_resolver must be callable or None")

        binding = await self.submissions.load_dispatch_binding(
            request_fingerprint=request_fingerprint,
            attempt_id=attempt_id,
        )
        if binding is None:
            dispatch = await self.search_dispatch.load_by_request_fingerprint(request_fingerprint)
            if dispatch is None:
                return None
            if dispatch.request.attempt_id != attempt_id:
                raise ValueError("search dispatch attempt identity drifted")
            if search_dispatch_binding_resolver is None:
                return None
            resolved_binding = search_dispatch_binding_resolver(dispatch)
            if isinstance(resolved_binding, Awaitable):
                resolved_binding = await resolved_binding
            if resolved_binding is not None and not isinstance(
                resolved_binding, WorkerSubmissionBinding
            ):
                raise TypeError(
                    "search dispatch binding resolver must return WorkerSubmissionBinding or None"
                )
            if resolved_binding is None:
                return None
            if resolved_binding.owner_id != dispatch.owner_id:
                raise ValueError("search dispatch owner identity drifted")
            if resolved_binding.receipt.request.attempt_id != attempt_id:
                raise ValueError("search dispatch submission attempt identity drifted")
            binding = resolved_binding
        inputs = await self.load_worker_terminal_evidence_inputs(
            principal=binding.owner_id,
            attempt_id=attempt_id,
            submission=binding.receipt,
        )
        return WorkerTerminalEvidenceLookup(binding, inputs)

    def worker_terminal_evidence_resolver(
        self,
        artifact_plan_resolver: ArtifactPlanResolver,
        *,
        runtime_error_factory: WorkerRuntimeErrorFactory | None = None,
        search_dispatch_binding_resolver: SearchDispatchBindingResolver | None = None,
    ) -> WorkerTerminalEvidenceResolver:
        """Compose authenticated lookup with explicit artifact mapping.

        The bundle owns principal/attempt lookup and the caller owns mapping
        mounted result files to artifact publication plans. Keeping that
        mapping explicit prevents a worker from guessing paths or elevating a
        transport identity into an authenticated principal.
        """

        async def lookup(
            *, request_fingerprint: str, attempt_id: str
        ) -> WorkerTerminalEvidenceLookup | None:
            return await self.load_worker_terminal_evidence_for_request(
                request_fingerprint=request_fingerprint,
                attempt_id=attempt_id,
                search_dispatch_binding_resolver=search_dispatch_binding_resolver,
            )

        return create_worker_terminal_evidence_resolver(
            lookup,
            artifact_plan_resolver,
            runtime_error_factory=runtime_error_factory,
        )


__all__ = ["PostgresStrategyLabV2Persistence"]
