"""Pure publication and retention decisions for content-addressed artifacts.

The future artifact adapter is responsible for implementing atomic create-if-
absent writes and durable retention. This module makes the decision inputs and
deduplication semantics explicit without touching storage or retaining bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.strategy_lab_v2.artifacts import ArtifactIntegrityReceipt
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import ArtifactManifest, ArtifactRetention


class ArtifactPublicationAction(StrEnum):
    CREATE_IF_ABSENT = "create_if_absent"
    REUSE_EXISTING = "reuse_existing"


@dataclass(frozen=True, slots=True)
class ArtifactPublicationPlan:
    """Storage-neutral intent emitted only after payload integrity succeeds."""

    manifest_fingerprint: str
    content_digest: str
    storage_key: str
    byte_length: int
    retention_class: ArtifactRetention
    action: ArtifactPublicationAction

    @property
    def requires_pin(self) -> bool:
        return self.retention_class in {
            ArtifactRetention.PERMANENT_MANIFEST,
            ArtifactRetention.PINNED_INPUT,
            ArtifactRetention.PINNED_RESULT,
        }


def plan_artifact_publication(
    manifest: ArtifactManifest,
    integrity: ArtifactIntegrityReceipt,
    *,
    already_present: bool = False,
) -> ArtifactPublicationPlan:
    """Plan an immutable create-or-reuse operation after integrity verification."""

    if not isinstance(manifest, ArtifactManifest):
        raise TypeError("artifact manifest must be an ArtifactManifest")
    if not isinstance(integrity, ArtifactIntegrityReceipt):
        raise TypeError("artifact integrity must be an ArtifactIntegrityReceipt")
    if not isinstance(already_present, bool):
        raise TypeError("already_present must be a bool")
    if not integrity.verified:
        raise ValueError("artifact publication requires a verified payload")
    manifest_fingerprint = content_digest(manifest)
    if integrity.manifest_fingerprint != manifest_fingerprint:
        raise ValueError("artifact integrity receipt must reference this manifest")
    if integrity.expected_digest != manifest.content_digest:
        raise ValueError("artifact integrity receipt digest must match the manifest")
    if integrity.expected_byte_length != manifest.byte_length:
        raise ValueError("artifact integrity receipt length must match the manifest")
    return ArtifactPublicationPlan(
        manifest_fingerprint=manifest_fingerprint,
        content_digest=manifest.content_digest,
        storage_key=manifest.storage_key,
        byte_length=manifest.byte_length,
        retention_class=manifest.retention_class,
        action=(
            ArtifactPublicationAction.REUSE_EXISTING
            if already_present
            else ArtifactPublicationAction.CREATE_IF_ABSENT
        ),
    )
