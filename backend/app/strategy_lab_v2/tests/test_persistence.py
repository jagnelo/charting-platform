from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.artifact_application import (
    LocalArtifactCleanupService,
    LocalArtifactRetentionService,
)
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.outbox_application import OutboxRelayService
from app.strategy_lab_v2.outcomes import new_execution_outcome
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.postgres_artifact_commit import PostgresArtifactCommitAdapter
from app.strategy_lab_v2.postgres_commands import ExecutionCommandContext, PostgresCommandAdapter
from app.strategy_lab_v2.postgres_execution_state import PostgresExecutionStateAdapter
from app.strategy_lab_v2.postgres_forward_state import PostgresForwardStateAdapter
from app.strategy_lab_v2.postgres_resources import PostgresResourceReader
from app.strategy_lab_v2.postgres_storage import PostgresAggregateStore
from app.strategy_lab_v2.postgres_submission import PostgresSubmissionDispatchAdapter
from app.strategy_lab_v2.progress import new_progress_state
from app.strategy_lab_v2.redis_transport import RedisDispatchTransport
from app.strategy_lab_v2.submissions import SubmissionReceipt, SubmissionRequest
from app.strategy_lab_v2.tests.test_result_publication import _result
from app.strategy_lab_v2.worker_evidence import (
    WorkerSubmissionBinding,
    WorkerTerminalEvidenceInputs,
)

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)


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


@pytest.mark.asyncio
async def test_metric_resource_projection_uses_typed_metric_set_reads() -> None:
    bundle = PostgresStrategyLabV2Persistence.build(lambda: object())
    manifest, *_ = _result()
    metric_set = manifest.metric_set

    async def load_all_metric_sets(*, principal: Any) -> tuple[Any, ...]:
        assert principal == "owner-a"
        return (metric_set,)

    bundle.metrics.load_all_metric_sets = load_all_metric_sets  # type: ignore[method-assign]
    projection = bundle.resources._projections[ApiResourceType.METRIC_SET]
    documents = await cast(Any, projection)(principal="owner-a")

    assert len(documents) == 1
    assert documents[0].id == metric_set.metric_set_id
    assert documents[0].attributes["metric_set_id"] == metric_set.metric_set_id
    assert documents[0].meta["record_fingerprint"] == metric_set.fingerprint


@pytest.mark.asyncio
async def test_persistence_bundle_loads_terminal_evidence_inputs() -> None:
    bundle = PostgresStrategyLabV2Persistence.build(lambda: object())
    manifest, *_ = _result()
    request = SubmissionRequest(
        "terminal-evidence-key",
        "backtest",
        manifest.attempt_id,
        content_digest("terminal-evidence-payload"),
        NOW,
    )
    receipt = SubmissionReceipt(request, NOW)
    execution = ExecutionCommandContext(
        new_execution_outcome(receipt.submission_id, manifest.attempt_id, accepted_at=NOW),
        new_progress_state(manifest.attempt_id, total_units=1, now=NOW),
    )
    calls: list[tuple[str, Any, str]] = []

    async def load_submission(*, principal: Any, attempt_id: str) -> SubmissionReceipt:
        calls.append(("submission", principal, attempt_id))
        return receipt

    async def read_context(*, principal: Any, attempt_id: str) -> ExecutionCommandContext:
        calls.append(("execution", principal, attempt_id))
        return execution

    async def load_manifest(*, principal: Any, attempt_id: str) -> Any:
        calls.append(("manifest", principal, attempt_id))
        return manifest

    async def load_for_attempt(*, principal: Any, attempt_id: str) -> tuple[Any, ...]:
        calls.append(("publication", principal, attempt_id))
        return ()

    bundle.submissions.load_submission = load_submission  # type: ignore[method-assign]
    bundle.execution_state.read_context = read_context  # type: ignore[method-assign]
    bundle.result_materialization.load_manifest = load_manifest  # type: ignore[method-assign]
    bundle.result_publication.load_for_attempt = load_for_attempt  # type: ignore[method-assign]

    inputs = await bundle.load_worker_terminal_evidence_inputs(
        principal="owner-a", attempt_id=manifest.attempt_id
    )

    assert isinstance(inputs, WorkerTerminalEvidenceInputs)
    assert inputs.submission == receipt
    assert inputs.execution == execution
    assert inputs.manifest == manifest
    assert calls == [
        ("submission", "owner-a", "attempt-1"),
        ("execution", "owner-a", "attempt-1"),
        ("manifest", "owner-a", "attempt-1"),
        ("publication", "owner-a", "attempt-1"),
    ]

    async def load_submission_binding(
        *, request_fingerprint: str, attempt_id: str
    ) -> WorkerSubmissionBinding:
        assert request_fingerprint == request.fingerprint
        assert attempt_id == manifest.attempt_id
        return WorkerSubmissionBinding("owner-a", receipt)

    bundle.submissions.load_submission_binding = load_submission_binding  # type: ignore[method-assign]
    lookup = await bundle.load_worker_terminal_evidence_for_request(
        request_fingerprint=request.fingerprint,
        attempt_id=manifest.attempt_id,
    )
    assert lookup is not None
    assert lookup.owner_id == "owner-a"
    assert lookup.inputs == inputs
