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
from app.strategy_lab_v2.capability_summary import (
    CapabilitySummary,
    CapabilitySummaryDecision,
)
from app.strategy_lab_v2.dispatch import DispatchRequest
from app.strategy_lab_v2.legacy import (
    LegacyCompatibilityAssessment,
    LegacyImportRecord,
    LegacyImportRegistry,
    LegacyRecord,
    LegacyRecordKind,
)
from app.strategy_lab_v2.outbox_application import OutboxRelayService
from app.strategy_lab_v2.outcomes import new_execution_outcome
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.postgres_artifact_commit import PostgresArtifactCommitAdapter
from app.strategy_lab_v2.postgres_commands import ExecutionCommandContext, PostgresCommandAdapter
from app.strategy_lab_v2.postgres_execution_state import PostgresExecutionStateAdapter
from app.strategy_lab_v2.postgres_forward_dispatch import PostgresForwardEventDispatchAdapter
from app.strategy_lab_v2.postgres_forward_state import PostgresForwardStateAdapter
from app.strategy_lab_v2.postgres_resources import PostgresResourceReader
from app.strategy_lab_v2.postgres_search_dispatch import (
    PostgresSearchDispatchAdapter,
    SearchDispatchRecord,
)
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
    assert isinstance(bundle.forward_dispatch, PostgresForwardEventDispatchAdapter)
    assert isinstance(bundle.commands, PostgresCommandAdapter)
    assert isinstance(bundle.submissions, PostgresSubmissionDispatchAdapter)
    assert isinstance(bundle.search_dispatch, PostgresSearchDispatchAdapter)
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
        ApiResourceType.CAPABILITY_SUMMARY,
        ApiResourceType.LEGACY_IMPORT,
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
async def test_capability_summary_projection_uses_authenticated_summary_reads() -> None:
    bundle = PostgresStrategyLabV2Persistence.build(lambda: object())
    summary = CapabilitySummary(
        report_fingerprint=content_digest("capability-report"),
        binding_fingerprint=content_digest("capability-binding"),
        decision=CapabilitySummaryDecision.RIGOROUS,
        data_gaps=(),
        execution_gaps=(),
        degradations=(),
        ranking_eligible=True,
        executable=True,
        authoritative=True,
        can_publish_authoritative_results=True,
    )

    async def load_all(*, principal: Any) -> tuple[CapabilitySummary, ...]:
        assert principal == "owner-a"
        return (summary,)

    bundle.capability.load_all = load_all  # type: ignore[method-assign]
    projection = bundle.resources._projections[ApiResourceType.CAPABILITY_SUMMARY]
    documents = await cast(Any, projection)(principal="owner-a")

    assert len(documents) == 1
    assert documents[0].id == summary.fingerprint
    assert documents[0].attributes["decision"] == CapabilitySummaryDecision.RIGOROUS
    assert documents[0].attributes["ranking_eligible"] is True
    assert documents[0].meta["report_fingerprint"] == summary.report_fingerprint


@pytest.mark.asyncio
async def test_legacy_import_projection_preserves_digest_only_records() -> None:
    bundle = PostgresStrategyLabV2Persistence.build(lambda: object())
    original = LegacyRecord(
        "legacy-definition-1",
        LegacyRecordKind.DEFINITION,
        "strategy-lab-v1",
        content_digest("legacy-payload"),
        NOW,
    )
    assessment = LegacyCompatibilityAssessment(
        "mapping-v1",
        True,
        content_digest("conversion"),
        ("converted without replay equivalence",),
    )
    record = LegacyImportRecord(original, content_digest("legacy-request"), assessment)

    async def load_registry(*, principal: Any) -> LegacyImportRegistry:
        assert principal == "owner-a"
        return LegacyImportRegistry((record,))

    bundle.legacy_imports.load_registry = load_registry  # type: ignore[method-assign]
    projection = bundle.resources._projections[ApiResourceType.LEGACY_IMPORT]
    documents = await cast(Any, projection)(principal="owner-a")

    assert len(documents) == 1
    assert documents[0].id == original.legacy_id
    assert documents[0].attributes["original"]["payload_digest"] == original.payload_digest
    assert documents[0].meta["replay_equivalent"] is False


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

    async def load_dispatch_binding(
        *, request_fingerprint: str, attempt_id: str
    ) -> WorkerSubmissionBinding:
        assert request_fingerprint == content_digest("dispatch-request")
        assert attempt_id == manifest.attempt_id
        return WorkerSubmissionBinding("owner-a", receipt)

    bundle.submissions.load_dispatch_binding = load_dispatch_binding  # type: ignore[method-assign]
    lookup = await bundle.load_worker_terminal_evidence_for_request(
        request_fingerprint=content_digest("dispatch-request"),
        attempt_id=manifest.attempt_id,
    )
    assert lookup is not None
    assert lookup.owner_id == "owner-a"
    assert lookup.inputs == inputs


@pytest.mark.asyncio
async def test_persistence_bundle_resolves_search_dispatch_terminal_identity() -> None:
    bundle = PostgresStrategyLabV2Persistence.build(lambda: object())
    manifest, *_ = _result()
    request = SubmissionRequest(
        idempotency_key="search-authoritative-key",
        operation="strategy-search",
        attempt_id=manifest.attempt_id,
        payload_digest=content_digest("search-authoritative-payload"),
        submitted_at=NOW,
    )
    receipt = SubmissionReceipt(request, NOW)
    execution = ExecutionCommandContext(
        new_execution_outcome(
            receipt.submission_id,
            manifest.attempt_id,
            accepted_at=NOW,
        ),
        new_progress_state(manifest.attempt_id, total_units=1, now=NOW),
    )
    dispatch_request = DispatchRequest(
        "search-dispatch-key",
        manifest.attempt_id,
        content_digest("search-payload"),
        "strategy-backtest",
        NOW,
    )
    record = SearchDispatchRecord(
        "owner-search",
        content_digest("search-experiment"),
        3,
        dispatch_request,
    )

    async def no_submission_binding(**_kwargs: Any) -> None:
        return None

    async def load_dispatch(request_fingerprint: str) -> SearchDispatchRecord | None:
        assert request_fingerprint == dispatch_request.fingerprint
        return record

    async def unexpected_submission(**_kwargs: Any) -> None:
        raise AssertionError("search dispatch binding should supply the authoritative receipt")

    async def resolve_binding(dispatch: SearchDispatchRecord) -> WorkerSubmissionBinding:
        assert dispatch == record
        return WorkerSubmissionBinding("owner-search", receipt)

    async def read_context(*, principal: Any, attempt_id: str) -> ExecutionCommandContext:
        assert principal == "owner-search"
        assert attempt_id == manifest.attempt_id
        return execution

    async def load_manifest(*, principal: Any, attempt_id: str) -> Any:
        assert principal == "owner-search"
        assert attempt_id == manifest.attempt_id
        return manifest

    async def load_for_attempt(*, principal: Any, attempt_id: str) -> tuple[Any, ...]:
        assert principal == "owner-search"
        assert attempt_id == manifest.attempt_id
        return ()

    bundle.submissions.load_dispatch_binding = no_submission_binding  # type: ignore[method-assign]
    bundle.search_dispatch.load_by_request_fingerprint = load_dispatch  # type: ignore[method-assign]
    bundle.submissions.load_submission = unexpected_submission  # type: ignore[method-assign]
    bundle.execution_state.read_context = read_context  # type: ignore[method-assign]
    bundle.result_materialization.load_manifest = load_manifest  # type: ignore[method-assign]
    bundle.result_publication.load_for_attempt = load_for_attempt  # type: ignore[method-assign]

    assert (
        await bundle.load_worker_terminal_evidence_for_request(
            request_fingerprint=dispatch_request.fingerprint,
            attempt_id=manifest.attempt_id,
        )
        is None
    )
    lookup = await bundle.load_worker_terminal_evidence_for_request(
        request_fingerprint=dispatch_request.fingerprint,
        attempt_id=manifest.attempt_id,
        search_dispatch_binding_resolver=resolve_binding,
    )

    assert lookup is not None
    assert lookup.owner_id == "owner-search"
    assert lookup.inputs.submission == receipt


def test_persistence_bundle_composes_terminal_evidence_resolver() -> None:
    bundle = PostgresStrategyLabV2Persistence.build(lambda: object())

    async def artifacts(_context: Any, _lookup: Any) -> tuple[Any, ...]:
        return ()

    resolver = bundle.worker_terminal_evidence_resolver(artifacts)
    assert callable(resolver)
