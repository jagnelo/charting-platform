from pathlib import Path
from typing import Any, cast

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.artifact_application import (
    LocalArtifactCleanupService,
    LocalArtifactRetentionService,
)
from app.strategy_lab_v2.outbox_application import OutboxRelayService
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.postgres_artifact_commit import PostgresArtifactCommitAdapter
from app.strategy_lab_v2.postgres_commands import PostgresCommandAdapter
from app.strategy_lab_v2.postgres_execution_state import PostgresExecutionStateAdapter
from app.strategy_lab_v2.postgres_forward_state import PostgresForwardStateAdapter
from app.strategy_lab_v2.postgres_resources import PostgresResourceReader
from app.strategy_lab_v2.postgres_storage import PostgresAggregateStore
from app.strategy_lab_v2.postgres_submission import PostgresSubmissionDispatchAdapter
from app.strategy_lab_v2.redis_transport import RedisDispatchTransport


def test_persistence_bundle_shares_store_and_wires_all_initial_api_dependencies(
    tmp_path: Path,
) -> None:
    bundle = PostgresStrategyLabV2Persistence.build(lambda: object())

    assert isinstance(bundle.aggregate_store, PostgresAggregateStore)
    assert isinstance(bundle.resources, PostgresResourceReader)
    assert bundle.resources._store is bundle.aggregate_store
    assert isinstance(bundle.execution_state, PostgresExecutionStateAdapter)
    assert isinstance(bundle.forward_state, PostgresForwardStateAdapter)
    assert isinstance(bundle.commands, PostgresCommandAdapter)
    assert isinstance(bundle.submissions, PostgresSubmissionDispatchAdapter)
    assert isinstance(bundle.artifact_commits, PostgresArtifactCommitAdapter)
    assert isinstance(
        bundle.artifact_retention_service(tmp_path / "artifacts"), LocalArtifactRetentionService
    )
    assert isinstance(
        bundle.artifact_cleanup_service(tmp_path / "cleanup-artifacts"), LocalArtifactCleanupService
    )
    assert set(bundle.resources._projections) == {
        ApiResourceType.ATTEMPT,
        ApiResourceType.METRIC_SET,
        ApiResourceType.FORWARD_INSTANCE,
        ApiResourceType.ARTIFACT,
    }

    class _Redis:
        pass

    # Construction is explicit; the caller owns the concrete Redis client.
    assert isinstance(
        bundle.outbox_relay(RedisDispatchTransport(cast(Any, _Redis()))),
        OutboxRelayService,
    )
