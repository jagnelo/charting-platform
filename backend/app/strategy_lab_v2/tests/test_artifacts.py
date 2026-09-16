from __future__ import annotations

import pytest

from app.strategy_lab_v2.artifacts import artifact_content_digest, verify_artifact_payload
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import ArtifactManifest


def _manifest(
    payload: bytes,
    *,
    byte_length: int | None = None,
    digest: str | None = None,
) -> ArtifactManifest:
    content_digest = digest or artifact_content_digest(payload)
    return ArtifactManifest(
        content_digest=content_digest,
        byte_length=len(payload) if byte_length is None else byte_length,
        media_type="application/octet-stream",
        schema_version="1",
        storage_key=content_digest,
    )


def test_artifact_integrity_receipt_verifies_raw_bytes_and_binds_manifest() -> None:
    payload = b"immutable-result-payload"
    manifest = _manifest(payload)
    receipt = verify_artifact_payload(manifest, payload)

    assert receipt.verified
    assert receipt.failure_reasons == ()
    assert receipt.manifest_fingerprint == content_digest(manifest)
    assert receipt.observed_digest == manifest.content_digest
    assert receipt.observed_byte_length == len(payload)


def test_artifact_integrity_receipt_reports_digest_and_length_mismatches() -> None:
    manifest = _manifest(b"expected")
    receipt = verify_artifact_payload(manifest, b"different")

    assert not receipt.verified
    assert receipt.failure_reasons == ("digest_mismatch", "byte_length_mismatch")


def test_artifact_integrity_rejects_non_bytes_payloads() -> None:
    manifest = _manifest(b"expected")
    with pytest.raises(TypeError, match="payload must be bytes"):
        verify_artifact_payload(manifest, bytearray(b"expected"))


def test_artifact_content_digest_is_deterministic() -> None:
    payload = b"same-bytes"
    assert artifact_content_digest(payload) == artifact_content_digest(payload)
    with pytest.raises(TypeError, match="payload must be bytes"):
        artifact_content_digest("same-bytes")  # type: ignore[arg-type]
