"""Verification of provider coverage attestations for frozen data series."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import AdjustmentMode, DataSeriesManifest, EventGranularity


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class CoverageAttestation:
    """Adapter-provided claims for one already-frozen series."""

    evidence_digest: str
    series_content_digest: str
    instrument_id: str
    event_type: str
    event_granularity: EventGranularity
    timeframe: str
    session: str
    feed: str
    adjustment: AdjustmentMode
    corporate_action_semantics: str
    start: datetime
    end: datetime
    row_count: int
    calendar_digest: str
    complete: bool
    gap_free: bool
    provider_adapter: str
    attested_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "evidence_digest",
            "series_content_digest",
            "calendar_digest",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        for name in (
            "instrument_id",
            "event_type",
            "timeframe",
            "session",
            "feed",
            "corporate_action_semantics",
            "provider_adapter",
        ):
            _nonempty(getattr(self, name), name)
        if not isinstance(self.event_granularity, EventGranularity):
            raise TypeError("event_granularity must be an EventGranularity")
        if not isinstance(self.adjustment, AdjustmentMode):
            raise TypeError("adjustment must be an AdjustmentMode")
        _aware(self.start, "start")
        _aware(self.end, "end")
        if self.start >= self.end:
            raise ValueError("coverage start must be earlier than end")
        if not isinstance(self.row_count, int) or isinstance(self.row_count, bool) or self.row_count <= 0:
            raise ValueError("coverage row_count must be a positive integer")
        for name in ("complete", "gap_free"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"coverage {name} must be a bool")
        _aware(self.attested_at, "attested_at")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class CoverageVerificationDecision(StrEnum):
    VERIFIED = "verified"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class CoverageVerificationReport:
    """Evidence-bound data decision; it does not fetch or repair observations."""

    decision: CoverageVerificationDecision
    manifest_fingerprint: str
    attestation_fingerprint: str
    mismatches: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.decision, CoverageVerificationDecision):
            raise TypeError("decision must be a CoverageVerificationDecision")
        require_sha256_digest(self.manifest_fingerprint, field_name="manifest_fingerprint")
        require_sha256_digest(self.attestation_fingerprint, field_name="attestation_fingerprint")
        mismatches = tuple(self.mismatches)
        if any(not isinstance(item, str) or not item.strip() for item in mismatches):
            raise ValueError("coverage mismatches must contain non-empty strings")
        if len(set(mismatches)) != len(mismatches):
            raise ValueError("coverage mismatches must be unique")
        if self.decision is CoverageVerificationDecision.VERIFIED and mismatches:
            raise ValueError("verified coverage cannot contain mismatches")
        if self.decision is CoverageVerificationDecision.REJECTED and not mismatches:
            raise ValueError("rejected coverage requires mismatches")
        object.__setattr__(self, "mismatches", mismatches)

    @property
    def verified(self) -> bool:
        return self.decision is CoverageVerificationDecision.VERIFIED

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def verify_coverage_attestation(
    manifest: DataSeriesManifest,
    attestation: CoverageAttestation,
) -> CoverageVerificationReport:
    """Compare an adapter attestation with every declared series dimension."""

    if not isinstance(manifest, DataSeriesManifest):
        raise TypeError("manifest must be a DataSeriesManifest")
    if not isinstance(attestation, CoverageAttestation):
        raise TypeError("attestation must be a CoverageAttestation")
    mismatches: list[str] = []
    comparisons = (
        ("evidence_digest", manifest.coverage_evidence_digest, attestation.evidence_digest),
        ("series_content_digest", manifest.content_digest, attestation.series_content_digest),
        ("instrument_id", manifest.instrument_id, attestation.instrument_id),
        ("event_type", manifest.event_type, attestation.event_type),
        ("event_granularity", manifest.event_granularity, attestation.event_granularity),
        ("timeframe", manifest.timeframe, attestation.timeframe),
        ("session", manifest.session, attestation.session),
        ("feed", manifest.feed, attestation.feed),
        ("adjustment", manifest.adjustment, attestation.adjustment),
        (
            "corporate_action_semantics",
            manifest.corporate_action_semantics,
            attestation.corporate_action_semantics,
        ),
        ("start", manifest.start, attestation.start),
        ("end", manifest.end, attestation.end),
        ("row_count", manifest.row_count, attestation.row_count),
    )
    mismatches.extend(
        field_name for field_name, expected, observed in comparisons if expected != observed
    )
    if not attestation.complete:
        mismatches.append("coverage_not_complete")
    if not attestation.gap_free:
        mismatches.append("coverage_contains_gaps")
    mismatches = sorted(set(mismatches))
    decision = (
        CoverageVerificationDecision.VERIFIED
        if not mismatches
        else CoverageVerificationDecision.REJECTED
    )
    return CoverageVerificationReport(
        decision,
        manifest_fingerprint=content_digest(manifest),
        attestation_fingerprint=attestation.fingerprint,
        mismatches=tuple(mismatches),
    )
