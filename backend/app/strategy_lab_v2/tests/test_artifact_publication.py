from __future__ import annotations

from dataclasses import replace

import pytest

from app.strategy_lab_v2.artifact_publication import (
    ArtifactPublicationAction,
    plan_artifact_publication,
)
from app.strategy_lab_v2.artifacts import (
    ArtifactIntegrityReceipt,
    artifact_content_digest,
    verify_artifact_payload,
)
from app.strategy_lab_v2.contracts import ArtifactManifest, ArtifactRetention


def _verified(
    payload: bytes,
    *,
    retention_class: ArtifactRetention = ArtifactRetention.PINNED_RESULT,
) -> tuple[ArtifactManifest, ArtifactIntegrityReceipt]:
    digest = artifact_content_digest(payload)
    manifest = ArtifactManifest(
        content_digest=digest,
        byte_length=len(payload),
        media_type="application/octet-stream",
        schema_version="1",
        storage_key=digest,
        retention_class=retention_class,
    )
    return manifest, verify_artifact_payload(manifest, payload)


def test_publication_plan_requires_verified_payload_and_is_create_if_absent() -> None:
    manifest, integrity = _verified(b"result")
    plan = plan_artifact_publication(manifest, integrity)

    assert plan.action is ArtifactPublicationAction.CREATE_IF_ABSENT
    assert plan.storage_key == manifest.content_digest
    assert plan.requires_pin


def test_publication_plan_reuses_existing_content_addressed_bytes() -> None:
    manifest, integrity = _verified(b"result")
    plan = plan_artifact_publication(manifest, integrity, already_present=True)

    assert plan.action is ArtifactPublicationAction.REUSE_EXISTING


def test_publication_plan_rejects_unverified_or_foreign_integrity_evidence() -> None:
    manifest, integrity = _verified(b"result")
    unverified = replace(integrity, failure_reasons=("digest_mismatch",))
    with pytest.raises(ValueError, match="verified payload"):
        plan_artifact_publication(manifest, unverified)

    _other_manifest, other_integrity = _verified(b"other")
    with pytest.raises(ValueError, match="reference this manifest"):
        plan_artifact_publication(manifest, other_integrity)

    assert not plan_artifact_publication(
        *_verified(b"ephemeral", retention_class=ArtifactRetention.EPHEMERAL)
    ).requires_pin
