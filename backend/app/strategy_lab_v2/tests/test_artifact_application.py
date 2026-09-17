from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

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
    service = LocalArtifactPublicationService(
        LocalArtifactStore(tmp_path / "artifacts"), committer
    )

    committed = await service.publish(_manifest(payload), payload, committed_at=NOW)
    assert committed.decision is ArtifactPublicationDecision.COMMITTED
    assert committed.storage.decision is ArtifactStoreDecision.WRITTEN
    assert committed.commit is not None
    assert committed.commit.decision is ArtifactCommitDecision.COMMIT

    replay = await service.publish(
        _manifest(payload), payload, committed_at=NOW + timedelta(days=1)
    )
    assert replay.decision is ArtifactPublicationDecision.REPLAY_EXISTING
    assert replay.storage.decision is ArtifactStoreDecision.REUSED
    assert replay.commit is not None
    assert replay.commit.decision is ArtifactCommitDecision.REPLAY_EXISTING
    assert len(committer.ledger.records) == 1
    assert [plan.action.value for plan in committer.plans] == ["create_if_absent", "reuse_existing"]


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
    resolver = _RetentionResolver(
        resolve_artifact_retention(state, observed_at=eligible_at)
    )
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
