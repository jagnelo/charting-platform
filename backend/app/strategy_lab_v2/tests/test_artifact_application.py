from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.strategy_lab_v2.artifact_application import (
    ArtifactPublicationDecision,
    LocalArtifactPublicationService,
    create_local_artifact_publication_service,
)
from app.strategy_lab_v2.artifact_commit import (
    ArtifactCommitDecision,
    ArtifactCommitLedger,
    ArtifactCommitResolution,
    finalize_artifact_commit,
)
from app.strategy_lab_v2.artifact_publication import ArtifactPublicationPlan
from app.strategy_lab_v2.artifact_store import ArtifactStoreDecision, LocalArtifactStore
from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.contracts import ArtifactManifest

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _manifest(payload: bytes) -> ArtifactManifest:
    digest = artifact_content_digest(payload)
    return ArtifactManifest(digest, len(payload), "application/octet-stream", "v1", digest)


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
