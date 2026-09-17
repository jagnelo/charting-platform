from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.postgres_artifact_commit import PostgresArtifactCommitAdapter
from app.strategy_lab_v2.postgres_commands import PostgresCommandAdapter
from app.strategy_lab_v2.postgres_execution_state import PostgresExecutionStateAdapter
from app.strategy_lab_v2.postgres_forward_state import PostgresForwardStateAdapter
from app.strategy_lab_v2.postgres_resources import PostgresResourceReader
from app.strategy_lab_v2.postgres_storage import PostgresAggregateStore
from app.strategy_lab_v2.postgres_submission import PostgresSubmissionDispatchAdapter


def test_persistence_bundle_shares_store_and_wires_all_initial_api_dependencies() -> None:
    bundle = PostgresStrategyLabV2Persistence.build(lambda: object())

    assert isinstance(bundle.aggregate_store, PostgresAggregateStore)
    assert isinstance(bundle.resources, PostgresResourceReader)
    assert bundle.resources._store is bundle.aggregate_store
    assert isinstance(bundle.execution_state, PostgresExecutionStateAdapter)
    assert isinstance(bundle.forward_state, PostgresForwardStateAdapter)
    assert isinstance(bundle.commands, PostgresCommandAdapter)
    assert isinstance(bundle.submissions, PostgresSubmissionDispatchAdapter)
    assert isinstance(bundle.artifact_commits, PostgresArtifactCommitAdapter)
