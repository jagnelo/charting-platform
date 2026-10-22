"""Snapshot-level verification of provider coverage attestations.

``DataSnapshot`` intentionally stores only the immutable reference to each
provider coverage document.  This module supplies the adapter-facing gate that
resolves those documents against every frozen series before an execution can be
admitted.  It performs no provider I/O, repair, or inference.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import DataSeriesManifest, DataSnapshot
from app.strategy_lab_v2.coverage import (
    CoverageAttestation,
    CoverageVerificationDecision,
    CoverageVerificationReport,
    verify_coverage_attestation,
)


class SnapshotCoverageDecision(StrEnum):
    VERIFIED = "verified"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class SnapshotCoverageResolution:
    """Evidence-bound result for all series in one frozen snapshot."""

    decision: SnapshotCoverageDecision
    snapshot_fingerprint: str
    reports: tuple[CoverageVerificationReport, ...]
    missing_series_digests: tuple[str, ...] = ()
    unexpected_series_digests: tuple[str, ...] = ()
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, SnapshotCoverageDecision):
            raise TypeError("decision must be a SnapshotCoverageDecision")
        require_sha256_digest(self.snapshot_fingerprint, field_name="snapshot_fingerprint")
        reports = tuple(self.reports)
        if any(not isinstance(item, CoverageVerificationReport) for item in reports):
            raise TypeError("reports must contain CoverageVerificationReport values")
        if tuple(sorted(reports, key=lambda item: item.manifest_fingerprint)) != reports:
            raise ValueError("coverage reports must be deterministically ordered")
        for name in ("missing_series_digests", "unexpected_series_digests"):
            values = tuple(getattr(self, name))
            if any(not isinstance(item, str) for item in values):
                raise TypeError(f"{name} must contain strings")
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must contain unique digests")
            for digest in values:
                require_sha256_digest(digest, field_name=f"{name} item")
            object.__setattr__(self, name, tuple(sorted(values)))
        if self.decision is SnapshotCoverageDecision.VERIFIED:
            if not reports or any(item.decision is not CoverageVerificationDecision.VERIFIED for item in reports):
                raise ValueError("verified snapshots require a verified report for every series")
            if self.missing_series_digests or self.unexpected_series_digests:
                raise ValueError("verified snapshots cannot have missing or unexpected series")
            if self.rejection_reason:
                raise ValueError("verified snapshots cannot contain a rejection reason")
        elif not self.rejection_reason:
            raise ValueError("rejected snapshots require a reason")
        object.__setattr__(self, "reports", reports)

    @property
    def verified(self) -> bool:
        return self.decision is SnapshotCoverageDecision.VERIFIED

    @property
    def attestation_fingerprints(self) -> tuple[str, ...]:
        return tuple(sorted(item.attestation_fingerprint for item in self.reports))

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def verify_snapshot_coverage(
    snapshot: DataSnapshot,
    attestations: Sequence[CoverageAttestation],
) -> SnapshotCoverageResolution:
    """Require one matching, complete attestation for every snapshot series."""

    if not isinstance(snapshot, DataSnapshot):
        raise TypeError("snapshot must be a DataSnapshot")
    if not isinstance(attestations, Sequence) or isinstance(attestations, str | bytes):
        raise TypeError("attestations must be a sequence")
    values = tuple(attestations)
    if any(not isinstance(item, CoverageAttestation) for item in values):
        raise TypeError("attestations must contain CoverageAttestation values")
    snapshot_digest = snapshot.fingerprint
    series_by_digest = {item.content_digest: item for item in snapshot.series}
    if len(series_by_digest) != len(snapshot.series):
        raise ValueError("snapshot series content digests must be unique")
    attestations_by_series: dict[str, CoverageAttestation] = {}
    duplicate_series: set[str] = set()
    for attestation in values:
        prior = attestations_by_series.get(attestation.series_content_digest)
        if prior is not None:
            duplicate_series.add(attestation.series_content_digest)
        else:
            attestations_by_series[attestation.series_content_digest] = attestation
    expected = set(series_by_digest)
    observed = set(attestations_by_series)
    missing = expected - observed
    unexpected = (observed - expected) | duplicate_series
    reports: list[CoverageVerificationReport] = []
    mismatches: list[str] = []
    for series_digest in sorted(expected & observed):
        series: DataSeriesManifest = series_by_digest[series_digest]
        report = verify_coverage_attestation(series, attestations_by_series[series_digest])
        reports.append(report)
        if not report.verified:
            mismatches.extend(
                f"{series_digest}:{mismatch}" for mismatch in report.mismatches
            )
    if missing:
        mismatches.extend(f"missing_series:{item}" for item in sorted(missing))
    if unexpected:
        mismatches.extend(f"unexpected_series:{item}" for item in sorted(unexpected))
    if mismatches:
        return SnapshotCoverageResolution(
            SnapshotCoverageDecision.REJECTED,
            snapshot_digest,
            tuple(sorted(reports, key=lambda item: item.manifest_fingerprint)),
            tuple(sorted(missing)),
            tuple(sorted(unexpected)),
            "; ".join(sorted(set(mismatches))),
        )
    return SnapshotCoverageResolution(
        SnapshotCoverageDecision.VERIFIED,
        snapshot_digest,
        tuple(sorted(reports, key=lambda item: item.manifest_fingerprint)),
    )
