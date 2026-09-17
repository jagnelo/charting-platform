"""Application-owned composition of the Strategy Lab v2 PostgreSQL adapters."""

from __future__ import annotations

import os
from collections.abc import Callable
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
from app.strategy_lab_v2.postgres_search_state import PostgresSearchStateAdapter
from app.strategy_lab_v2.postgres_snapshot_coverage import PostgresSnapshotCoverageAdapter
from app.strategy_lab_v2.postgres_storage import PostgresAggregateStore
from app.strategy_lab_v2.postgres_submission import PostgresSubmissionDispatchAdapter
from app.strategy_lab_v2.postgres_worker_settlement import PostgresWorkerSettlementAdapter
from app.strategy_lab_v2.postgres_worker_state import PostgresWorkerStateAdapter
from app.strategy_lab_v2.redis_transport import RedisDispatchTransport
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
    legacy_imports: PostgresLegacyImportAdapter
    lineage: PostgresLineageAdapter
    metrics: PostgresMetricsAdapter
    result_completion: PostgresResultCompletionAdapter
    result_materialization: PostgresResultMaterializationAdapter
    result_publication: PostgresResultPublicationAdapter
    runtime_execution: PostgresRuntimeExecutionAdapter
    runtime_receipts: PostgresRuntimeReceiptAdapter
    search_state: PostgresSearchStateAdapter
    snapshot_coverage: PostgresSnapshotCoverageAdapter
    submissions: PostgresSubmissionDispatchAdapter
    worker_state: PostgresWorkerStateAdapter
    worker_settlements: PostgresWorkerSettlementAdapter

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
        result_materialization = PostgresResultMaterializationAdapter(session_factory)
        metrics = PostgresMetricsAdapter(session_factory)

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
            metric_sets = await metrics.load_all(principal=principal)
            return tuple(
                _record_document(
                    ApiResourceType.METRIC_SET,
                    metric_set.metric_set_fingerprint,
                    metric_set,
                    metric_set.record_fingerprint,
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

        return cls(
            aggregate_store=aggregate_store,
            resources=PostgresResourceReader(
                aggregate_store,
                projections={
                    ApiResourceType.ATTEMPT: attempt_projection,
                    ApiResourceType.METRIC_SET: metric_set_projection,
                    ApiResourceType.FORWARD_INSTANCE: forward_instance_projection,
                    ApiResourceType.ARTIFACT: artifact_projection,
                },
            ),
            acquisition=PostgresAcquisitionAdapter(session_factory),
            artifact_commits=PostgresArtifactCommitAdapter(session_factory),
            artifact_retention=PostgresArtifactRetentionAdapter(session_factory),
            capability=PostgresCapabilityAdapter(session_factory),
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
            legacy_imports=PostgresLegacyImportAdapter(session_factory),
            lineage=PostgresLineageAdapter(session_factory),
            metrics=metrics,
            result_completion=PostgresResultCompletionAdapter(session_factory),
            result_materialization=result_materialization,
            result_publication=PostgresResultPublicationAdapter(session_factory),
            runtime_execution=PostgresRuntimeExecutionAdapter(session_factory),
            runtime_receipts=PostgresRuntimeReceiptAdapter(session_factory),
            search_state=PostgresSearchStateAdapter(session_factory),
            snapshot_coverage=PostgresSnapshotCoverageAdapter(session_factory),
            submissions=PostgresSubmissionDispatchAdapter(session_factory, clock=clock),
            worker_state=PostgresWorkerStateAdapter(session_factory),
            worker_settlements=PostgresWorkerSettlementAdapter(session_factory),
        )

    def artifact_publication(
        self, root: str | os.PathLike[str]
    ) -> LocalArtifactPublicationService:
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

    def artifact_cleanup_service(
        self, root: str | os.PathLike[str]
    ) -> LocalArtifactCleanupService:
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
            result_completion=self.result_completion,
            metrics=self.metrics,
            worker_state=self.worker_state,
            settlements=self.worker_settlements,
            clock=clock,
        )


__all__ = ["PostgresStrategyLabV2Persistence"]
