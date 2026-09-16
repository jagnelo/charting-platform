from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.artifact_commit import (
    ArtifactCommitDecision,
    ArtifactCommitLedger,
    finalize_artifact_commit,
)
from app.strategy_lab_v2.artifact_publication import plan_artifact_publication
from app.strategy_lab_v2.artifacts import artifact_content_digest, verify_artifact_payload
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import ArtifactManifest, ArtifactRetention

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _plan(payload: bytes = b"artifact", *, already_present: bool = False):
    digest = artifact_content_digest(payload)
    manifest = ArtifactManifest(
        content_digest=digest,
        byte_length=len(payload),
        media_type="application/octet-stream",
        schema_version="v1",
        storage_key=digest,
        retention_class=ArtifactRetention.PINNED_RESULT,
    )
    receipt = verify_artifact_payload(manifest, payload)
    return plan_artifact_publication(manifest, receipt, already_present=already_present)


def test_create_if_absent_commit_and_exact_retry_replay() -> None:
    ledger = ArtifactCommitLedger()
    plan = _plan()
    committed = finalize_artifact_commit(ledger, plan, committed_at=NOW)
    assert committed.decision is ArtifactCommitDecision.COMMIT
    assert committed.record is not None
    replay = finalize_artifact_commit(committed.ledger, plan, committed_at=NOW + timedelta(days=1))
    assert replay.decision is ArtifactCommitDecision.REPLAY_EXISTING
    assert replay.record == committed.record


def test_reuse_existing_requires_prior_commit_record() -> None:
    rejected = finalize_artifact_commit(
        ArtifactCommitLedger(), _plan(already_present=True), committed_at=NOW
    )
    assert rejected.decision is ArtifactCommitDecision.REJECT
    assert "committed artifact" in (rejected.rejection_reason or "")


def test_storage_key_collision_with_different_manifest_is_conflict() -> None:
    first_plan = _plan()
    first = finalize_artifact_commit(ArtifactCommitLedger(), first_plan, committed_at=NOW)
    assert first.record is not None
    changed_plan = type(first_plan)(
        manifest_fingerprint=first_plan.manifest_fingerprint.replace("a", "b", 1),
        content_digest=first_plan.content_digest,
        storage_key=first_plan.storage_key,
        byte_length=first_plan.byte_length,
        retention_class=first_plan.retention_class,
        action=first_plan.action,
    )
    conflict = finalize_artifact_commit(first.ledger, changed_plan, committed_at=NOW)
    assert conflict.decision is ArtifactCommitDecision.CONFLICT


def test_ledger_orders_records_and_rejects_duplicate_storage_keys() -> None:
    first = finalize_artifact_commit(ArtifactCommitLedger(), _plan(b"one"), committed_at=NOW)
    second = finalize_artifact_commit(first.ledger, _plan(b"two"), committed_at=NOW)
    assert second.decision is ArtifactCommitDecision.COMMIT
    assert [item.commit_key for item in second.ledger.records] == sorted(
        item.commit_key for item in second.ledger.records
    )
    changed_manifest = replace(
        second.ledger.records[0], manifest_fingerprint=content_digest("different-manifest")
    )
    with pytest.raises(ValueError, match="storage keys"):
        ArtifactCommitLedger(second.ledger.records + (changed_manifest,))


def test_commit_record_rejects_bad_digest_length_and_time() -> None:
    from app.strategy_lab_v2.artifact_commit import ArtifactCommitRecord
    from app.strategy_lab_v2.canonical import content_digest

    with pytest.raises(ValueError, match="storage_key"):
        ArtifactCommitRecord(content_digest("manifest"), content_digest("content"), "bad", 1, NOW)
    with pytest.raises(ValueError, match="timezone"):
        ArtifactCommitRecord(
            content_digest("manifest"),
            content_digest("content"),
            content_digest("content"),
            1,
            datetime(2024, 1, 1),
        )
