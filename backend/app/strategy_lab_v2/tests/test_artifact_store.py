from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.artifact_retention import (
    ArtifactRetentionState,
    resolve_artifact_retention,
)
from app.strategy_lab_v2.artifact_store import (
    ArtifactByteDecision,
    ArtifactStoreCorruptionError,
    ArtifactStoreDecision,
    LocalArtifactStore,
)
from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.contracts import ArtifactManifest, ArtifactRetention

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _manifest(payload: bytes) -> ArtifactManifest:
    digest = artifact_content_digest(payload)
    return ArtifactManifest(
        digest,
        len(payload),
        "application/octet-stream",
        "1",
        digest,
    )


def test_publish_is_atomic_deduplicated_and_read_only(tmp_path) -> None:
    payload = b"immutable artifact"
    manifest = _manifest(payload)
    store = LocalArtifactStore(tmp_path / "artifacts")

    written = store.publish(manifest, payload)
    assert written.decision is ArtifactStoreDecision.WRITTEN
    target = store.path_for(manifest.storage_key)
    assert target.read_bytes() == payload
    assert target.stat().st_mode & 0o222 == 0

    reused = store.publish(manifest, payload)
    assert reused.decision is ArtifactStoreDecision.REUSED
    assert reused.integrity is not None and reused.integrity.verified
    assert store.read(manifest.storage_key) == payload
    read_payload, receipt = store.read_manifest(manifest)
    assert read_payload == payload
    assert receipt.verified


def test_publish_rejects_bad_payload_without_creating_a_file(tmp_path) -> None:
    payload = b"expected"
    manifest = _manifest(payload)
    store = LocalArtifactStore(tmp_path / "artifacts")
    rejected = store.publish(manifest, b"different")
    assert rejected.decision is ArtifactStoreDecision.REJECT
    assert rejected.integrity is not None
    assert not rejected.integrity.verified
    assert not store.path_for(manifest.storage_key).exists()


def test_reads_fail_closed_after_content_is_tampered(tmp_path) -> None:
    payload = b"durable bytes"
    manifest = _manifest(payload)
    store = LocalArtifactStore(tmp_path / "artifacts")
    store.publish(manifest, payload)
    target = store.path_for(manifest.storage_key)
    target.chmod(0o644)
    target.write_bytes(b"tampered")
    with pytest.raises(ArtifactStoreCorruptionError, match="wrong digest"):
        store.read(manifest.storage_key)


def test_existing_non_regular_targets_and_symlink_shards_are_rejected(tmp_path) -> None:
    payload = b"target"
    manifest = _manifest(payload)
    store = LocalArtifactStore(tmp_path / "artifacts")
    target = store.path_for(manifest.storage_key)
    target.parent.mkdir(parents=True)
    target.mkdir()
    with pytest.raises(ArtifactStoreCorruptionError, match="regular"):
        store.publish(manifest, payload)

    other = tmp_path / "outside"
    other.mkdir()
    symlink_root = LocalArtifactStore(tmp_path / "symlink-store")
    shard = symlink_root.root / "aa"
    shard.symlink_to(other, target_is_directory=True)
    with pytest.raises(ArtifactStoreCorruptionError, match="symlink"):
        symlink_root.path_for("sha256:" + "aa" * 32)

    target_symlink_store = LocalArtifactStore(tmp_path / "target-symlink-store")
    target = target_symlink_store.path_for(manifest.storage_key)
    target.parent.mkdir(parents=True)
    target.symlink_to(tmp_path / "missing-artifact")
    with pytest.raises(ArtifactStoreCorruptionError, match="regular"):
        target_symlink_store.read(manifest.storage_key)


def test_invalid_roots_and_keys_fail_closed(tmp_path) -> None:
    with pytest.raises(ValueError, match="directory"):
        file_path = tmp_path / "file"
        file_path.write_text("not a directory")
        LocalArtifactStore(file_path)
    store = LocalArtifactStore(tmp_path / "artifacts")
    with pytest.raises(ValueError, match="sha256"):
        store.path_for("../../outside")
    with pytest.raises(TypeError, match="manifest"):
        store.publish("bad", b"payload")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="payload"):
        store.publish(_manifest(b"payload"), bytearray(b"payload"))  # type: ignore[arg-type]


def test_store_root_is_resolved_and_stable(tmp_path) -> None:
    store = LocalArtifactStore(os.fspath(tmp_path / "nested"))
    assert store.root.is_absolute()


def test_collect_deletes_only_when_retention_is_explicitly_eligible(tmp_path) -> None:
    payload = b"tiered artifact"
    manifest = ArtifactManifest(
        artifact_content_digest(payload),
        len(payload),
        "application/octet-stream",
        "v1",
        artifact_content_digest(payload),
        retention_class=ArtifactRetention.TIERED_RESULT,
    )
    store = LocalArtifactStore(tmp_path / "artifacts")
    store.publish(manifest, payload)
    eligible_at = NOW + timedelta(days=1)
    state = ArtifactRetentionState.from_manifest(manifest, retention_eligible_at=eligible_at)

    retained = store.collect(
        manifest,
        resolve_artifact_retention(state, observed_at=NOW),
    )
    assert retained.decision is ArtifactByteDecision.RETAINED
    assert store.read(manifest.storage_key) == payload

    deleted = store.collect(
        manifest,
        resolve_artifact_retention(state, observed_at=eligible_at),
    )
    assert deleted.decision is ArtifactByteDecision.DELETED
    assert deleted.byte_length == len(payload)
    assert not store.path_for(manifest.storage_key).exists()
    assert store.collect(
        manifest,
        resolve_artifact_retention(state, observed_at=eligible_at),
    ).decision is ArtifactByteDecision.NOT_FOUND


def test_collect_preserves_pinned_bytes_and_rejects_foreign_retention(tmp_path) -> None:
    payload = b"pinned artifact"
    manifest = _manifest(payload)
    store = LocalArtifactStore(tmp_path / "artifacts")
    store.publish(manifest, payload)
    state = ArtifactRetentionState.from_manifest(manifest)
    retained = store.collect(
        manifest,
        resolve_artifact_retention(state, observed_at=NOW),
    )
    assert retained.decision is ArtifactByteDecision.RETAINED
    assert store.read(manifest.storage_key) == payload

    other_manifest = _manifest(b"other")
    with pytest.raises(ValueError, match="different manifest"):
        store.collect(other_manifest, resolve_artifact_retention(state, observed_at=NOW))
