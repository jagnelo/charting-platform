from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.strategy_lab_v2.api_contracts import ApiError, ApiErrorCode
from app.strategy_lab_v2.artifact_application import (
    ArtifactPublicationDecision,
    ArtifactPublicationResolution,
)
from app.strategy_lab_v2.artifact_commit import ArtifactCommitLedger, finalize_artifact_commit
from app.strategy_lab_v2.artifact_publication import plan_artifact_publication
from app.strategy_lab_v2.artifact_store import ArtifactStoreDecision, ArtifactStoreResolution
from app.strategy_lab_v2.artifacts import artifact_content_digest, verify_artifact_payload
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.dispatch_payload import DispatchPayload
from app.strategy_lab_v2.outcomes import ExecutionOutcome, OutcomeStatus
from app.strategy_lab_v2.postgres_commands import ExecutionCommandContext
from app.strategy_lab_v2.progress import ExecutionProgressState, ProgressPhase
from app.strategy_lab_v2.result_publication import plan_result_publication
from app.strategy_lab_v2.submissions import SubmissionReceipt, SubmissionRequest
from app.strategy_lab_v2.tests.test_result_publication import _result
from app.strategy_lab_v2.tests.test_worker_process import _request
from app.strategy_lab_v2.tests.test_worker_service import _entry
from app.strategy_lab_v2.worker_evidence import (
    WorkerSubmissionBinding,
    WorkerTerminalEvidenceInputs,
    WorkerTerminalEvidenceLookup,
)
from app.strategy_lab_v2.worker_evidence_resolution import (
    build_worker_terminal_evidence,
    create_sandbox_artifact_plan_resolver,
    create_worker_terminal_evidence_resolver,
    default_worker_failure_error,
)
from app.strategy_lab_v2.worker_process import SerialWorkerProcessExecutor
from app.strategy_lab_v2.worker_service import WorkerCompletionContext

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _context_and_lookup(
    tmp_path: Path, *, body: str = "printf 'ok'"
) -> tuple[WorkerCompletionContext, WorkerTerminalEvidenceLookup]:
    request = _request(tmp_path, body=body)
    process = SerialWorkerProcessExecutor(timeout_seconds=10).run(request)
    context = WorkerCompletionContext(
        _entry(DispatchPayload.from_mapping({"attempt_id": request.admission.attempt_id})),
        request,
        process,
        NOW,
    )
    result, evidence, conformance, runtime, integrity, execution_plan = _result()
    publication = plan_result_publication(
        result, evidence, conformance, runtime, integrity, execution_plan=execution_plan
    )
    submission_request = SubmissionRequest(
        "worker-evidence-key",
        "backtest",
        request.admission.attempt_id,
        content_digest("worker-evidence-payload"),
        NOW,
    )
    receipt = SubmissionReceipt(submission_request, NOW)
    outcome = ExecutionOutcome(
        receipt.submission_id,
        request.admission.attempt_id,
        1,
        OutcomeStatus.ACCEPTED,
        NOW,
    )
    progress = ExecutionProgressState(
        request.admission.attempt_id,
        1,
        ProgressPhase.RUNNING,
        0,
        1,
        False,
        NOW,
    )
    lookup = WorkerTerminalEvidenceLookup(
        WorkerSubmissionBinding("owner-a", receipt),
        WorkerTerminalEvidenceInputs(
            request.admission.attempt_id,
            receipt,
            ExecutionCommandContext(outcome, progress),
            result,
            (publication,),
        ),
    )
    return context, lookup


def _failed_lookup(lookup: WorkerTerminalEvidenceLookup) -> WorkerTerminalEvidenceLookup:
    assert lookup.inputs.execution is not None
    return WorkerTerminalEvidenceLookup(
        lookup.binding,
        replace(
            lookup.inputs,
            execution=lookup.inputs.execution,
            manifest=None,
            publications=(),
        ),
    )


def _artifact_plan(lookup: WorkerTerminalEvidenceLookup):
    assert lookup.inputs.manifest is not None
    artifact = lookup.inputs.manifest.output_artifacts[0]
    return _artifact_plan_for(artifact, b"result")


def _artifact_plan_for(artifact, payload: bytes):
    return plan_artifact_publication(
        artifact,
        verify_artifact_payload(artifact, payload),
    )


class _Publisher:
    def __init__(self, resolution: ArtifactPublicationResolution) -> None:
        self.resolution = resolution
        self.calls: list[tuple[object, object, object, datetime]] = []

    async def publish_sandbox_result(
        self, manifest, sandbox_plan, sandbox_result, *, committed_at: datetime
    ) -> ArtifactPublicationResolution:
        self.calls.append((manifest, sandbox_plan, sandbox_result, committed_at))
        return self.resolution

    async def publish_file(self, manifest, source, *, committed_at):
        raise AssertionError("single-artifact publisher should not publish files")


def _publication_resolution(lookup: WorkerTerminalEvidenceLookup) -> ArtifactPublicationResolution:
    assert lookup.inputs.manifest is not None
    artifact = lookup.inputs.manifest.output_artifacts[0]
    integrity = verify_artifact_payload(artifact, b"result")
    plan = plan_artifact_publication(artifact, integrity)
    commit = finalize_artifact_commit(ArtifactCommitLedger(), plan, committed_at=NOW)
    assert commit.record is not None
    return ArtifactPublicationResolution(
        ArtifactPublicationDecision.COMMITTED,
        ArtifactStoreResolution(
            ArtifactStoreDecision.WRITTEN,
            artifact.storage_key,
            artifact.byte_length,
            integrity,
        ),
        commit,
        artifact_plan=plan,
    )


def _publication_resolution_for_artifact(artifact, payload: bytes) -> ArtifactPublicationResolution:
    integrity = verify_artifact_payload(artifact, payload)
    plan = plan_artifact_publication(artifact, integrity)
    commit = finalize_artifact_commit(ArtifactCommitLedger(), plan, committed_at=NOW)
    assert commit.record is not None
    return ArtifactPublicationResolution(
        ArtifactPublicationDecision.COMMITTED,
        ArtifactStoreResolution(
            ArtifactStoreDecision.WRITTEN,
            artifact.storage_key,
            artifact.byte_length,
            integrity,
        ),
        commit,
        artifact_plan=plan,
    )


def test_builder_assembles_successful_typed_evidence(tmp_path: Path) -> None:
    context, lookup = _context_and_lookup(tmp_path)
    evidence = build_worker_terminal_evidence(
        context,
        lookup,
        artifact_plans=(_artifact_plan(lookup),),
    )

    assert evidence.principal == "owner-a"
    assert evidence.submission == lookup.inputs.submission
    assert evidence.result == lookup.inputs.manifest
    assert evidence.publication == lookup.inputs.publications[0]
    assert len(evidence.artifact_plans) == 1


def test_builder_requires_one_accepted_publication(tmp_path: Path) -> None:
    context, lookup = _context_and_lookup(tmp_path)
    missing = WorkerTerminalEvidenceLookup(
        lookup.binding,
        WorkerTerminalEvidenceInputs(
            lookup.inputs.attempt_id,
            lookup.inputs.submission,
            lookup.inputs.execution,
            lookup.inputs.manifest,
            (),
        ),
    )
    with pytest.raises(ValueError, match="one accepted publication"):
        build_worker_terminal_evidence(context, missing)


def test_builder_requires_exact_plan_for_every_result_artifact(tmp_path: Path) -> None:
    context, lookup = _context_and_lookup(tmp_path)

    with pytest.raises(ValueError, match="cover every result artifact"):
        build_worker_terminal_evidence(context, lookup)


def test_builder_rejects_plan_for_an_unknown_result_artifact(tmp_path: Path) -> None:
    context, lookup = _context_and_lookup(tmp_path)
    plan = _artifact_plan(lookup)
    unknown = replace(plan, manifest_fingerprint=content_digest("unknown-manifest"))

    with pytest.raises(ValueError, match="unknown result artifact"):
        build_worker_terminal_evidence(context, lookup, artifact_plans=(unknown,))


def test_builder_accepts_complete_multi_artifact_host_mapping(tmp_path: Path) -> None:
    context, lookup = _context_and_lookup(tmp_path)
    assert lookup.inputs.manifest is not None
    assert lookup.inputs.execution is not None
    assert lookup.inputs.publications
    first = lookup.inputs.manifest.output_artifacts[0]
    second_digest = artifact_content_digest(b"second")
    second = replace(
        first,
        content_digest=second_digest,
        storage_key=second_digest,
        byte_length=len(b"second"),
    )
    manifest = replace(lookup.inputs.manifest, output_artifacts=(first, second))
    publication = replace(
        lookup.inputs.publications[0],
        result_fingerprint=manifest.fingerprint,
        reproduction_fingerprint=manifest.reproduction_fingerprint,
    )
    multi = WorkerTerminalEvidenceLookup(
        lookup.binding,
        replace(lookup.inputs, manifest=manifest, publications=(publication,)),
    )

    evidence = build_worker_terminal_evidence(
        context,
        multi,
        artifact_plans=(
            _artifact_plan_for(first, b"result"),
            _artifact_plan_for(second, b"second"),
        ),
    )

    assert evidence.result == manifest
    assert {plan.manifest_fingerprint for plan in evidence.artifact_plans} == {
        content_digest(first),
        content_digest(second),
    }


def test_builder_maps_failed_runtime_to_typed_digest_only_error(tmp_path: Path) -> None:
    context, accepted_lookup = _context_and_lookup(tmp_path, body="exit 7")
    lookup = _failed_lookup(accepted_lookup)

    evidence = build_worker_terminal_evidence(context, lookup)

    assert evidence.result is None
    assert evidence.publication is None
    assert evidence.error is not None
    assert evidence.error.code is ApiErrorCode.INTERNAL_ERROR
    assert evidence.error.message == "strategy worker execution failed"
    assert evidence.error.request_id == context.request.request_fingerprint
    assert evidence.error.details == {
        "error_digest": context.process.execution.runtime_result.state.error_digest  # type: ignore[union-attr]
    }


def test_builder_uses_host_runtime_error_factory(tmp_path: Path) -> None:
    context, accepted_lookup = _context_and_lookup(tmp_path, body="exit 7")
    lookup = _failed_lookup(accepted_lookup)
    seen: list[str] = []

    def factory(received_context, runtime_state):
        seen.append(runtime_state.error_digest or "missing")
        return ApiError(
            ApiErrorCode.INTERNAL_ERROR,
            "host-classified worker failure",
            received_context.request.request_fingerprint,
            500,
            False,
            {"classification": "non-retryable"},
        )

    evidence = build_worker_terminal_evidence(
        context,
        lookup,
        runtime_error_factory=factory,
    )

    assert seen == [context.process.execution.runtime_result.state.error_digest]  # type: ignore[union-attr]
    assert evidence.error is not None
    assert evidence.error.message == "host-classified worker failure"
    assert evidence.error.retryable is False


def test_builder_rejects_host_runtime_error_for_a_different_request(tmp_path: Path) -> None:
    context, accepted_lookup = _context_and_lookup(tmp_path, body="exit 7")
    lookup = _failed_lookup(accepted_lookup)

    def factory(_received_context, _runtime_state):
        return ApiError(
            ApiErrorCode.INTERNAL_ERROR,
            "misbound worker failure",
            "different-request",
            500,
        )

    with pytest.raises(ValueError, match="different request"):
        build_worker_terminal_evidence(
            context,
            lookup,
            runtime_error_factory=factory,
        )


def test_default_worker_failure_error_rejects_non_failed_runtime(tmp_path: Path) -> None:
    context, _ = _context_and_lookup(tmp_path)
    assert context.process.execution is not None
    assert context.process.execution.runtime_result is not None
    with pytest.raises(ValueError, match="failed runtime state"):
        default_worker_failure_error(
            context,
            context.process.execution.runtime_result.state,
        )


@pytest.mark.asyncio
async def test_factory_loads_lookup_and_resolves_artifact_plans(tmp_path: Path) -> None:
    context, lookup = _context_and_lookup(tmp_path)
    calls: list[tuple[str, str]] = []

    async def load(*, request_fingerprint: str, attempt_id: str, payload_digest: str | None = None):
        calls.append((request_fingerprint, attempt_id))
        assert payload_digest == context.entry.payload_digest
        return lookup

    async def artifacts(_context: WorkerCompletionContext, received_lookup):
        assert received_lookup is lookup
        return (_artifact_plan(lookup),)

    resolver = create_worker_terminal_evidence_resolver(load, artifacts)
    evidence = await resolver(context)

    assert calls == [(context.entry.request_fingerprint, "attempt-1")]
    assert evidence.artifact_plans == (_artifact_plan(lookup),)


@pytest.mark.asyncio
async def test_factory_forwards_host_runtime_error_factory(tmp_path: Path) -> None:
    context, accepted_lookup = _context_and_lookup(tmp_path, body="exit 7")
    lookup = _failed_lookup(accepted_lookup)

    def factory(received_context, _runtime_state):
        return ApiError(
            ApiErrorCode.INTERNAL_ERROR,
            "factory failure",
            received_context.request.request_fingerprint,
            500,
        )

    async def load(*, request_fingerprint: str, attempt_id: str, payload_digest: str | None = None):
        assert request_fingerprint == context.entry.request_fingerprint
        assert attempt_id == context.request.admission.attempt_id
        assert payload_digest == context.entry.payload_digest
        return lookup

    async def artifacts(_context: WorkerCompletionContext, _lookup):
        return ()

    resolver = create_worker_terminal_evidence_resolver(
        load,
        artifacts,
        runtime_error_factory=factory,
    )
    evidence = await resolver(context)

    assert evidence.error is not None
    assert evidence.error.message == "factory failure"


@pytest.mark.asyncio
async def test_sandbox_artifact_resolver_returns_published_verified_plan(tmp_path: Path) -> None:
    context, lookup = _context_and_lookup(tmp_path)
    publication = _publication_resolution(lookup)
    publisher = _Publisher(publication)
    resolver = create_sandbox_artifact_plan_resolver(publisher)

    plans = await resolver(context, lookup)

    assert plans == (publication.artifact_plan,)
    assert publisher.calls == [
        (
            lookup.inputs.manifest,
            context.request.sandbox_plan,
            context.process.execution.nautilus_result.sandbox_result,  # type: ignore[union-attr]
            NOW,
        )
    ]


@pytest.mark.asyncio
async def test_sandbox_artifact_resolver_rejects_multi_artifact_manifest(tmp_path: Path) -> None:
    context, lookup = _context_and_lookup(tmp_path)
    assert lookup.inputs.manifest is not None
    artifact = lookup.inputs.manifest.output_artifacts[0]
    second = replace(
        artifact,
        content_digest=content_digest("second-artifact"),
        storage_key=content_digest("second-artifact"),
    )
    manifest = replace(lookup.inputs.manifest, output_artifacts=(artifact, second))
    multi = WorkerTerminalEvidenceLookup(
        lookup.binding,
        replace(lookup.inputs, manifest=manifest),
    )
    resolver = create_sandbox_artifact_plan_resolver(_Publisher(_publication_resolution(lookup)))

    with pytest.raises(ValueError, match="exactly one"):
        await resolver(context, multi)


@pytest.mark.asyncio
async def test_sandbox_artifact_resolver_accepts_explicit_multi_file_mapping(
    tmp_path: Path,
) -> None:
    context, lookup = _context_and_lookup(tmp_path)
    assert lookup.inputs.manifest is not None
    first = lookup.inputs.manifest.output_artifacts[0]
    second = replace(
        first,
        content_digest=artifact_content_digest(b"second"),
        storage_key=artifact_content_digest(b"second"),
    )
    manifest = replace(lookup.inputs.manifest, output_artifacts=(first, second))
    multi = WorkerTerminalEvidenceLookup(lookup.binding, replace(lookup.inputs, manifest=manifest))
    calls: list[tuple[object, object, datetime]] = []

    class MultiPublisher(_Publisher):
        async def publish_file(self, artifact, source, *, committed_at: datetime):
            calls.append((artifact, source, committed_at))
            payload = b"result" if source == "/tmp/first" else b"second"
            return _publication_resolution_for_artifact(artifact, payload)

    publisher = MultiPublisher(_publication_resolution(lookup))
    resolver = create_sandbox_artifact_plan_resolver(
        publisher,
        artifact_path_resolver=lambda _context, _lookup: {
            content_digest(first): "/tmp/first",
            content_digest(second): "/tmp/second",
        },
    )

    plans = await resolver(context, multi)

    assert tuple(plan.manifest_fingerprint for plan in plans) == tuple(
        content_digest(artifact) for artifact in manifest.output_artifacts
    )
    paths = {
        content_digest(first): "/tmp/first",
        content_digest(second): "/tmp/second",
    }
    assert [source for artifact, source, _at in calls] == [
        paths[content_digest(artifact)] for artifact in manifest.output_artifacts
    ]
