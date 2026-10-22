"""Pure result-manifest checks for referenced artifact integrity evidence."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.strategy_lab_v2.artifacts import ArtifactIntegrityReceipt
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import RunResultManifest


@dataclass(frozen=True, slots=True)
class ResultIntegrityReceipt:
    """Digest-bound coverage of every immutable output in a run result."""

    result_fingerprint: str
    expected_artifact_digests: tuple[str, ...]
    verified_artifact_digests: tuple[str, ...]
    missing_artifact_digests: tuple[str, ...]
    unexpected_artifact_digests: tuple[str, ...]
    unverified_artifact_digests: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        return not (
            self.missing_artifact_digests
            or self.unexpected_artifact_digests
            or self.unverified_artifact_digests
        )


def verify_run_result_artifacts(
    result: RunResultManifest,
    receipts: Sequence[ArtifactIntegrityReceipt],
) -> ResultIntegrityReceipt:
    """Verify complete, one-to-one payload evidence for a result manifest.

    The function does not read storage. It checks that supplied integrity
    receipts cover exactly the result outputs and that each receipt's manifest
    identity, digest, length, and verified bit agree with the result.
    """

    if not isinstance(result, RunResultManifest):
        raise TypeError("result must be a RunResultManifest")
    if not isinstance(receipts, Sequence):
        raise TypeError("artifact receipts must be a sequence")
    receipt_values = tuple(receipts)
    if any(not isinstance(item, ArtifactIntegrityReceipt) for item in receipt_values):
        raise TypeError("artifact receipts must use ArtifactIntegrityReceipt records")

    expected = {
        artifact.content_digest: content_digest(artifact)
        for artifact in result.output_artifacts
    }
    receipt_digests = tuple(item.expected_digest for item in receipt_values)
    if len(receipt_digests) != len(set(receipt_digests)):
        raise ValueError("artifact integrity receipts must be unique by expected digest")

    verified: list[str] = []
    unexpected: list[str] = []
    unverified: list[str] = []
    for receipt in receipt_values:
        expected_manifest_fingerprint = expected.get(receipt.expected_digest)
        if expected_manifest_fingerprint is None:
            unexpected.append(receipt.expected_digest)
            continue
        if (
            not receipt.verified
            or receipt.manifest_fingerprint != expected_manifest_fingerprint
            or receipt.observed_digest != receipt.expected_digest
            or receipt.observed_byte_length != receipt.expected_byte_length
        ):
            unverified.append(receipt.expected_digest)
            continue
        verified.append(receipt.expected_digest)

    expected_digests = tuple(sorted(expected))
    verified_digests = tuple(sorted(verified))
    observed_expected = set(receipt_digests) & set(expected)
    missing = tuple(sorted(set(expected) - observed_expected))
    return ResultIntegrityReceipt(
        result_fingerprint=content_digest(result),
        expected_artifact_digests=expected_digests,
        verified_artifact_digests=verified_digests,
        missing_artifact_digests=missing,
        unexpected_artifact_digests=tuple(sorted(unexpected)),
        unverified_artifact_digests=tuple(sorted(unverified)),
    )
