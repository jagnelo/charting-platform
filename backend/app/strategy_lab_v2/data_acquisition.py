"""Storage-neutral acquisition handoff for provider-backed data snapshots.

The provider platform owns fetching, repair, and coverage evidence.  This
module only binds the provider result to the engine-neutral preflight and
snapshot contracts so a later worker cannot accidentally execute against an
unverified or differently scoped snapshot.  It performs no I/O and does not
define provider-specific request fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.capabilities import PreflightClass, PreflightReport
from app.strategy_lab_v2.contracts import DataSnapshot
from app.strategy_lab_v2.snapshot_coverage import SnapshotCoverageResolution


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class DataAcquisitionRequest:
    """Immutable provider handoff derived from one capability preflight."""

    request_id: str
    preflight_report: PreflightReport
    requested_at: datetime

    def __post_init__(self) -> None:
        _nonempty(self.request_id, "request_id")
        if not isinstance(self.preflight_report, PreflightReport):
            raise TypeError("preflight_report must be a PreflightReport")
        _aware(self.requested_at, "requested_at")

    @property
    def preflight_fingerprint(self) -> str:
        return self.preflight_report.fingerprint

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class DataAcquisitionReceipt:
    """Provider evidence linking one acquisition to a frozen snapshot."""

    request_fingerprint: str
    snapshot_fingerprint: str
    snapshot_id: str
    provider_snapshot_id: str
    coverage_resolution_fingerprint: str
    provider_receipt_digest: str
    acquired_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "request_fingerprint",
            "snapshot_fingerprint",
            "coverage_resolution_fingerprint",
            "provider_receipt_digest",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        for name in ("snapshot_id", "provider_snapshot_id"):
            _nonempty(getattr(self, name), name)
        _aware(self.acquired_at, "acquired_at")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class DataAcquisitionDecision(StrEnum):
    VERIFIED = "verified"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class DataAcquisitionVerification:
    """Evidence-bound admission report for a provider acquisition handoff."""

    decision: DataAcquisitionDecision
    request_fingerprint: str
    snapshot_fingerprint: str
    receipt_fingerprint: str
    coverage_resolution_fingerprint: str
    mismatches: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.decision, DataAcquisitionDecision):
            raise TypeError("decision must be a DataAcquisitionDecision")
        for name in (
            "request_fingerprint",
            "snapshot_fingerprint",
            "receipt_fingerprint",
            "coverage_resolution_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        mismatches = tuple(self.mismatches)
        if any(not isinstance(item, str) or not item.strip() for item in mismatches):
            raise ValueError("acquisition mismatches must contain non-empty strings")
        if len(mismatches) != len(set(mismatches)):
            raise ValueError("acquisition mismatches must be unique")
        if self.decision is DataAcquisitionDecision.VERIFIED and mismatches:
            raise ValueError("verified acquisition cannot contain mismatches")
        if self.decision is DataAcquisitionDecision.REJECTED and not mismatches:
            raise ValueError("rejected acquisition requires mismatches")
        object.__setattr__(self, "mismatches", mismatches)

    @property
    def verified(self) -> bool:
        return self.decision is DataAcquisitionDecision.VERIFIED

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def verify_data_acquisition(
    request: DataAcquisitionRequest,
    snapshot: DataSnapshot,
    coverage: SnapshotCoverageResolution,
    receipt: DataAcquisitionReceipt,
) -> DataAcquisitionVerification:
    """Verify provider evidence before an execution adapter can consume a snapshot.

    The check is deliberately strict: unsupported preflight, identity drift,
    stale acquisition evidence, or incomplete coverage all reject the handoff.
    A rejected report never mutates any input and contains deterministic reason
    codes for persistence or API projection by a later adapter.
    """

    if not isinstance(request, DataAcquisitionRequest):
        raise TypeError("request must be a DataAcquisitionRequest")
    if not isinstance(snapshot, DataSnapshot):
        raise TypeError("snapshot must be a DataSnapshot")
    if not isinstance(coverage, SnapshotCoverageResolution):
        raise TypeError("coverage must be a SnapshotCoverageResolution")
    if not isinstance(receipt, DataAcquisitionReceipt):
        raise TypeError("receipt must be a DataAcquisitionReceipt")

    mismatches: list[str] = []
    if request.preflight_report.classification is PreflightClass.UNSUPPORTED:
        mismatches.append("preflight_unsupported")
    if snapshot.preflight_report.fingerprint != request.preflight_fingerprint:
        mismatches.append("snapshot_preflight_fingerprint")
    if coverage.snapshot_fingerprint != snapshot.fingerprint:
        mismatches.append("coverage_snapshot_fingerprint")
    if not coverage.verified:
        mismatches.append("coverage_not_verified")
    if receipt.request_fingerprint != request.fingerprint:
        mismatches.append("receipt_request_fingerprint")
    if receipt.snapshot_fingerprint != snapshot.fingerprint:
        mismatches.append("receipt_snapshot_fingerprint")
    if receipt.snapshot_id != snapshot.snapshot_id:
        mismatches.append("receipt_snapshot_id")
    if receipt.provider_snapshot_id != snapshot.provider_snapshot_id:
        mismatches.append("receipt_provider_snapshot_id")
    if receipt.coverage_resolution_fingerprint != coverage.fingerprint:
        mismatches.append("receipt_coverage_resolution_fingerprint")
    if receipt.acquired_at < request.requested_at:
        mismatches.append("acquisition_precedes_request")
    ordered_mismatches = tuple(sorted(set(mismatches)))
    decision = (
        DataAcquisitionDecision.VERIFIED
        if not ordered_mismatches
        else DataAcquisitionDecision.REJECTED
    )
    return DataAcquisitionVerification(
        decision=decision,
        request_fingerprint=request.fingerprint,
        snapshot_fingerprint=snapshot.fingerprint,
        receipt_fingerprint=receipt.fingerprint,
        coverage_resolution_fingerprint=coverage.fingerprint,
        mismatches=ordered_mismatches,
    )
