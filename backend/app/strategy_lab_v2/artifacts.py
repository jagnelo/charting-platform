"""Pure content-integrity checks for immutable Strategy Lab artifacts.

The artifact store owns retrieval and atomic publication. This module only
checks an already-read byte payload against its typed manifest, so workers and
storage adapters can share one deterministic verification contract without
introducing filesystem or network access into the engine-neutral package.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import ArtifactManifest


def artifact_content_digest(payload: bytes) -> str:
    """Return the raw-byte SHA-256 content address for an artifact payload."""

    if not isinstance(payload, bytes):
        raise TypeError("artifact payload must be bytes")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


@dataclass(frozen=True, slots=True)
class ArtifactIntegrityReceipt:
    """Deterministic verification evidence without retaining artifact bytes."""

    manifest_fingerprint: str
    expected_digest: str
    observed_digest: str
    expected_byte_length: int
    observed_byte_length: int
    failure_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("manifest_fingerprint", "expected_digest", "observed_digest"):
            require_sha256_digest(getattr(self, name), field_name=name)
        for name in ("expected_byte_length", "observed_byte_length"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        reasons = tuple(self.failure_reasons)
        if any(not isinstance(reason, str) or not reason.strip() for reason in reasons):
            raise ValueError("failure_reasons must contain non-empty strings")
        canonical_reasons = tuple(sorted(set(reasons)))
        if len(canonical_reasons) != len(reasons):
            raise ValueError("failure_reasons must be unique")
        if not reasons and (
            self.expected_digest != self.observed_digest
            or self.expected_byte_length != self.observed_byte_length
        ):
            raise ValueError("verified artifact integrity must match digest and byte length")
        object.__setattr__(self, "failure_reasons", canonical_reasons)

    @property
    def verified(self) -> bool:
        return not self.failure_reasons


def verify_artifact_payload(
    manifest: ArtifactManifest, payload: bytes
) -> ArtifactIntegrityReceipt:
    """Compare an in-memory payload with its manifest's digest and length.

    A mismatch is returned as typed evidence rather than raised, allowing a
    worker to classify corrupt or truncated storage reads and keep the
    authoritative manifest unchanged. Invalid argument types still fail fast.
    """

    if not isinstance(manifest, ArtifactManifest):
        raise TypeError("artifact manifest must be an ArtifactManifest")
    if not isinstance(payload, bytes):
        raise TypeError("artifact payload must be bytes")

    observed_digest = artifact_content_digest(payload)
    observed_byte_length = len(payload)
    failures: list[str] = []
    if observed_digest != manifest.content_digest:
        failures.append("digest_mismatch")
    if observed_byte_length != manifest.byte_length:
        failures.append("byte_length_mismatch")
    return ArtifactIntegrityReceipt(
        manifest_fingerprint=content_digest(manifest),
        expected_digest=manifest.content_digest,
        observed_digest=observed_digest,
        expected_byte_length=manifest.byte_length,
        observed_byte_length=observed_byte_length,
        failure_reasons=tuple(failures),
    )
