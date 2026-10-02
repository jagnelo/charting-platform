from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.artifact_application import (
    ArtifactCleanupScheduler,
    ArtifactPublicationDecision,
    LocalArtifactCleanupService,
    LocalArtifactPublicationService,
    LocalArtifactRetentionService,
    create_local_artifact_cleanup_service,
    create_local_artifact_publication_service,
    create_local_artifact_retention_service,
)
from app.strategy_lab_v2.artifact_commit import (
    ArtifactCommitDecision,
    ArtifactCommitLedger,
    ArtifactCommitResolution,
    finalize_artifact_commit,
)
from app.strategy_lab_v2.artifact_publication import ArtifactPublicationPlan
from app.strategy_lab_v2.artifact_retention import (
    ArtifactRetentionState,
    resolve_artifact_retention,
)
from app.strategy_lab_v2.artifact_store import (
    ArtifactCleanupResolution,
    ArtifactStoreDecision,
    LocalArtifactStore,
)
from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import ArtifactManifest, ArtifactRetention
from app.strategy_lab_v2.nautilus_runner import NautilusRunResult, NautilusRunStatus
from app.strategy_lab_v2.nautilus_runtime_bundle import (
    NautilusInvocationResultStreamReference,
)
from app.strategy_lab_v2.nautilus_runtime_protocol import (
    NAUTILUS_INVOCATION_RESULT_STREAM_MEDIA_TYPE,
    NAUTILUS_INVOCATION_RESULT_STREAM_SCHEMA,
)
from app.strategy_lab_v2.sandbox import sandbox_invocation_result_stream_path
from app.strategy_lab_v2.sandbox_execution import SandboxRunResult, SandboxRunStatus
from app.strategy_lab_v2.tests.test_sandbox_execution import _plan as sandbox_plan
from strategy_runtime import (
    InvocationResultStreamWriter,
    InvocationStatus,
    StrategyInvocationResult,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _manifest(payload: bytes) -> ArtifactManifest:
    digest = artifact_content_digest(payload)
    return ArtifactManifest(digest, len(payload), "application/octet-stream", "v1", digest)


class _RetentionResolver:
    def __init__(self, resolution) -> None:
        self.resolution = resolution
        self.calls: list[tuple[str, datetime]] = []

    async def resolve(self, *, manifest_fingerprint: str, observed_at: datetime):
        self.calls.append((manifest_fingerprint, observed_at))
        return self.resolution


class _Committer:
    def __init__(self) -> None:
        self.ledger = ArtifactCommitLedger()
        self.plans: list[ArtifactPublicationPlan] = []

    async def load_ledger(self) -> ArtifactCommitLedger:
        return self.ledger

    async def finalize(
        self,
        plan: ArtifactPublicationPlan,
        *,
        committed_at: datetime,
    ) -> ArtifactCommitResolution:
        self.plans.append(plan)
        resolution = finalize_artifact_commit(self.ledger, plan, committed_at=committed_at)
        if resolution.decision is ArtifactCommitDecision.COMMIT:
            self.ledger = resolution.ledger
        return resolution


async def test_publish_coordinates_bytes_and_commit_then_replays(tmp_path) -> None:
    payload = b"durable result"
    committer = _Committer()
    service = LocalArtifactPublicationService(LocalArtifactStore(tmp_path / "artifacts"), committer)

    committed = await service.publish(_manifest(payload), payload, committed_at=NOW)
    assert committed.decision is ArtifactPublicationDecision.COMMITTED
    assert committed.storage.decision is ArtifactStoreDecision.WRITTEN
    assert committed.commit is not None
    assert committed.commit.decision is ArtifactCommitDecision.COMMIT
    assert committed.artifact_plan is not None
    assert committed.artifact_plan.content_digest == _manifest(payload).content_digest

    replay = await service.publish(
        _manifest(payload), payload, committed_at=NOW + timedelta(days=1)
    )
    assert replay.decision is ArtifactPublicationDecision.REPLAY_EXISTING
    assert replay.storage.decision is ArtifactStoreDecision.REUSED
    assert replay.commit is not None
    assert replay.commit.decision is ArtifactCommitDecision.REPLAY_EXISTING
    assert len(committer.ledger.records) == 1
    assert [plan.action.value for plan in committer.plans] == ["create_if_absent", "reuse_existing"]


async def test_publish_file_coordinates_streamed_bytes_and_commit(tmp_path) -> None:
    payload = b"mounted result"
    source = tmp_path / "result.bin"
    source.write_bytes(payload)
    committer = _Committer()
    service = LocalArtifactPublicationService(LocalArtifactStore(tmp_path / "artifacts"), committer)

    published = await service.publish_file(_manifest(payload), source, committed_at=NOW)

    assert published.decision is ArtifactPublicationDecision.COMMITTED
    assert published.storage.decision is ArtifactStoreDecision.WRITTEN
    assert published.commit is not None
    assert published.commit.decision is ArtifactCommitDecision.COMMIT
    assert published.artifact_plan is not None
    assert published.artifact_plan.byte_length == len(payload)


async def test_publish_sandbox_result_binds_plan_evidence_and_manifest(tmp_path) -> None:
    payload = b"sandbox result"
    source = tmp_path / "result.bin"
    source.write_bytes(payload)
    plan = sandbox_plan(output_path=os.fspath(source))
    sandbox_result = SandboxRunResult(
        plan.fingerprint,
        plan.request_fingerprint,
        SandboxRunStatus.SUCCEEDED,
        0,
        content_digest("stdout"),
        content_digest("stderr"),
        6,
        0,
        result_digest=artifact_content_digest(payload),
        result_bytes=len(payload),
    )
    service = LocalArtifactPublicationService(
        LocalArtifactStore(tmp_path / "artifacts"), _Committer()
    )

    published = await service.publish_sandbox_result(
        _manifest(payload), plan, sandbox_result, committed_at=NOW
    )

    assert published.decision is ArtifactPublicationDecision.COMMITTED
    assert published.storage.decision is ArtifactStoreDecision.WRITTEN
    assert published.artifact_plan is not None
    assert published.artifact_plan.content_digest == artifact_content_digest(payload)


async def test_publish_sandbox_result_rejects_manifest_identity_drift(tmp_path) -> None:
    payload = b"sandbox result"
    source = tmp_path / "result.bin"
    source.write_bytes(payload)
    plan = sandbox_plan(output_path=os.fspath(source))
    sandbox_result = SandboxRunResult(
        plan.fingerprint,
        plan.request_fingerprint,
        SandboxRunStatus.SUCCEEDED,
        0,
        content_digest("stdout"),
        content_digest("stderr"),
        6,
        0,
        result_digest=artifact_content_digest(payload),
        result_bytes=len(payload),
    )
    service = LocalArtifactPublicationService(
        LocalArtifactStore(tmp_path / "artifacts"), _Committer()
    )

    with pytest.raises(ValueError, match="manifest.*digest"):
        await service.publish_sandbox_result(
            _manifest(b"different"), plan, sandbox_result, committed_at=NOW
        )


async def test_publish_nautilus_invocation_result_stream_revalidates_and_streams_file(
    tmp_path,
) -> None:
    output_path = tmp_path / "result.json"
    output_path.write_bytes(b"result")
    stream_path = tmp_path / "invocations.ndjson"
    invocation = StrategyInvocationResult(
        content_digest("source"),
        content_digest("manifest"),
        content_digest("context"),
        "strategy.main:Strategy",
        InvocationStatus.SUCCEEDED,
    )
    stream = stream_path.open("w+b")
    writer = InvocationResultStreamWriter(stream)
    writer.write(invocation)
    summary = writer.finish()
    stream.close()
    payload = stream_path.read_bytes()
    stream_manifest = ArtifactManifest(
        summary.content_digest,
        summary.byte_length,
        NAUTILUS_INVOCATION_RESULT_STREAM_MEDIA_TYPE,
        NAUTILUS_INVOCATION_RESULT_STREAM_SCHEMA,
        summary.content_digest,
        ArtifactRetention.PINNED_RESULT,
    )

    plan = sandbox_plan(output_limit=2048, output_path=os.fspath(output_path))
    argv = list(plan.argv)
    argv.insert(16, "--mount=type=bind,src=/tmp/contexts,dst=/inputs/contexts,readonly")
    argv.insert(18, f"--mount=type=bind,src={stream_path},dst=/outputs/invocations")
    argv.insert(21, f"--env=STRATEGY_CONTEXT_STREAM_DIGEST={content_digest('contexts')}")
    plan = replace(plan, argv=tuple(argv))
    assert sandbox_invocation_result_stream_path(plan) == stream_path
    sandbox_result = SandboxRunResult(
        plan.fingerprint,
        plan.request_fingerprint,
        SandboxRunStatus.SUCCEEDED,
        0,
        content_digest("stdout"),
        content_digest("stderr"),
        0,
        0,
        result_digest=artifact_content_digest(output_path.read_bytes()),
        result_bytes=output_path.stat().st_size,
    )
    run_result = NautilusRunResult(
        content_digest("execution plan"),
        plan.fingerprint,
        NautilusRunStatus.SUCCEEDED,
        False,
        sandbox_result,
        NautilusInvocationResultStreamReference(stream_manifest, 1, True),
    )
    service = LocalArtifactPublicationService(
        LocalArtifactStore(tmp_path / "artifacts"), _Committer()
    )

    published = await service.publish_nautilus_invocation_result_stream(
        stream_manifest,
        plan,
        run_result,
        committed_at=NOW,
    )

    assert published.decision is ArtifactPublicationDecision.COMMITTED
    assert published.storage.integrity is not None
    assert published.storage.integrity.observed_digest == summary.content_digest
    assert published.storage.integrity.observed_byte_length == len(payload)
    stream_path.write_bytes(b"drifted")
    with pytest.raises(ValueError, match="byte length differs|digest differs"):
        await service.publish_nautilus_invocation_result_stream(
            stream_manifest,
            plan,
            run_result,
            committed_at=NOW,
        )


async def test_bad_payload_is_rejected_before_commit(tmp_path) -> None:
    payload = b"expected"
    committer = _Committer()
    store = LocalArtifactStore(tmp_path / "artifacts")
    service = LocalArtifactPublicationService(store, committer)

    rejected = await service.publish(_manifest(payload), b"different", committed_at=NOW)
    assert rejected.decision is ArtifactPublicationDecision.REJECT
    assert rejected.commit is None
    assert committer.plans == []
    assert not store.path_for(artifact_content_digest(payload)).exists()


def test_local_factory_uses_explicit_root_and_postgres_commit_adapter(tmp_path) -> None:
    service = create_local_artifact_publication_service(tmp_path / "artifacts", lambda: object())

    assert isinstance(service, LocalArtifactPublicationService)
    assert service.store.root == (tmp_path / "artifacts").resolve()

    retention_service = create_local_artifact_retention_service(
        tmp_path / "retention-artifacts", lambda: object()
    )
    assert isinstance(retention_service, LocalArtifactRetentionService)
    assert retention_service.store.root == (tmp_path / "retention-artifacts").resolve()
    cleanup_service = create_local_artifact_cleanup_service(
        tmp_path / "cleanup-artifacts", lambda: object()
    )
    assert isinstance(cleanup_service, LocalArtifactCleanupService)
    assert cleanup_service.store.root == (tmp_path / "cleanup-artifacts").resolve()


async def test_retention_service_deletes_only_after_resolver_authorizes(tmp_path) -> None:
    payload = b"ephemeral result"
    digest = artifact_content_digest(payload)
    manifest = ArtifactManifest(
        digest,
        len(payload),
        "application/octet-stream",
        "v1",
        digest,
        ArtifactRetention.EPHEMERAL,
    )
    eligible_at = NOW + timedelta(days=1)
    state = ArtifactRetentionState.from_manifest(manifest, retention_eligible_at=eligible_at)
    resolver = _RetentionResolver(resolve_artifact_retention(state, observed_at=eligible_at))
    store = LocalArtifactStore(tmp_path / "artifacts")
    store.publish(manifest, payload)
    service = LocalArtifactRetentionService(store, resolver)

    collected = await service.collect(manifest, observed_at=eligible_at)

    assert collected.decision.value == "deleted"
    assert resolver.calls == [(content_digest(manifest), eligible_at)]
    assert not store.path_for(manifest.storage_key).exists()


async def test_cleanup_service_uses_commit_ledger_as_authority(tmp_path) -> None:
    payload = b"orphan from interrupted publish"
    manifest = _manifest(payload)
    committer = _Committer()
    store = LocalArtifactStore(tmp_path / "artifacts")
    store.publish(manifest, payload)
    old = NOW - timedelta(days=2)
    target = store.path_for(manifest.storage_key)
    os.utime(target, (old.timestamp(), old.timestamp()))
    service = LocalArtifactCleanupService(store, committer)

    resolution = await service.cleanup_uncommitted(
        observed_at=NOW,
        minimum_age=timedelta(days=1),
    )

    assert isinstance(resolution, ArtifactCleanupResolution)
    assert resolution.deleted_count == 1
    assert not target.exists()


async def test_cleanup_scheduler_is_cancellable_and_bounded(tmp_path) -> None:
    payload = b"scheduled cleanup"
    manifest = _manifest(payload)
    committer = _Committer()
    store = LocalArtifactStore(tmp_path / "artifacts")
    store.publish(manifest, payload)
    old = NOW - timedelta(days=2)
    os.utime(store.path_for(manifest.storage_key), (old.timestamp(), old.timestamp()))
    service = LocalArtifactCleanupService(store, committer)
    sleeps: list[float] = []
    scheduler = ArtifactCleanupScheduler(
        service,
        clock=lambda: NOW,
        minimum_age=timedelta(days=1),
        interval_seconds=2,
        sleep=lambda seconds: _record_sleep(sleeps, seconds),
    )

    results = await scheduler.run(_NeverStop(), max_cycles=1)

    assert len(results) == 1
    assert results[0].deleted_count == 1
    assert sleeps == []


async def _record_sleep(sleeps: list[float], seconds: float) -> None:
    sleeps.append(seconds)


class _NeverStop:
    def is_set(self) -> bool:
        return False
