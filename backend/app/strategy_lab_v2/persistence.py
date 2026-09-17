"""Application-owned composition of the Strategy Lab v2 PostgreSQL adapters."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.strategy_lab_v2.artifact_application import LocalArtifactPublicationService
from app.strategy_lab_v2.artifact_store import LocalArtifactStore
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
from app.strategy_lab_v2.postgres_worker_state import PostgresWorkerStateAdapter


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
        return cls(
            aggregate_store=aggregate_store,
            resources=PostgresResourceReader(aggregate_store),
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
            execution_summaries=PostgresExecutionSummaryAdapter(session_factory),
            forward_state=PostgresForwardStateAdapter(session_factory),
            legacy_imports=PostgresLegacyImportAdapter(session_factory),
            lineage=PostgresLineageAdapter(session_factory),
            metrics=PostgresMetricsAdapter(session_factory),
            result_completion=PostgresResultCompletionAdapter(session_factory),
            result_materialization=PostgresResultMaterializationAdapter(session_factory),
            result_publication=PostgresResultPublicationAdapter(session_factory),
            runtime_execution=PostgresRuntimeExecutionAdapter(session_factory),
            runtime_receipts=PostgresRuntimeReceiptAdapter(session_factory),
            search_state=PostgresSearchStateAdapter(session_factory),
            snapshot_coverage=PostgresSnapshotCoverageAdapter(session_factory),
            submissions=PostgresSubmissionDispatchAdapter(session_factory, clock=clock),
            worker_state=PostgresWorkerStateAdapter(session_factory),
        )

    def artifact_publication(
        self, root: str | os.PathLike[str]
    ) -> LocalArtifactPublicationService:
        """Create a byte/commit publication service for an explicit artifact root."""

        return LocalArtifactPublicationService(
            LocalArtifactStore(root),
            self.artifact_commits,
        )


__all__ = ["PostgresStrategyLabV2Persistence"]
