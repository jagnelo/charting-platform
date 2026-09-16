"""Explicit compatibility reports for inspecting and importing legacy records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


class LegacyRecordKind(StrEnum):
    DEFINITION = "definition"
    RESULT = "result"


@dataclass(frozen=True, slots=True)
class LegacyRecord:
    """Digest-only representation of an original legacy record."""

    legacy_id: str
    kind: LegacyRecordKind
    source_version: str
    payload_digest: str
    observed_at: datetime

    def __post_init__(self) -> None:
        _nonempty(self.legacy_id, "legacy_id")
        if not isinstance(self.kind, LegacyRecordKind):
            raise TypeError("kind must be a LegacyRecordKind")
        _nonempty(self.source_version, "source_version")
        require_sha256_digest(self.payload_digest, field_name="payload_digest")
        _aware(self.observed_at, "observed_at")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class LegacyImportRequest:
    """Explicit request to preserve and assess one legacy record."""

    request_id: str
    legacy_id: str
    kind: LegacyRecordKind
    source_version: str
    payload_digest: str
    requested_at: datetime
    preserve_original: bool = True

    def __post_init__(self) -> None:
        require_sha256_digest(self.request_id, field_name="request_id")
        _nonempty(self.legacy_id, "legacy_id")
        if not isinstance(self.kind, LegacyRecordKind):
            raise TypeError("kind must be a LegacyRecordKind")
        _nonempty(self.source_version, "source_version")
        require_sha256_digest(self.payload_digest, field_name="payload_digest")
        _aware(self.requested_at, "requested_at")
        if not isinstance(self.preserve_original, bool):
            raise TypeError("preserve_original must be a bool")

    @property
    def original(self) -> LegacyRecord:
        return LegacyRecord(
            self.legacy_id,
            self.kind,
            self.source_version,
            self.payload_digest,
            self.requested_at,
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(
            {
                "kind": self.kind,
                "legacy_id": self.legacy_id,
                "payload_digest": self.payload_digest,
                "source_version": self.source_version,
            }
        )


@dataclass(frozen=True, slots=True)
class LegacyCompatibilityAssessment:
    """Adapter-supplied conversion evidence; it never asserts replay parity."""

    mapping_version: str
    supported: bool
    conversion_fingerprint: str | None
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _nonempty(self.mapping_version, "mapping_version")
        if not isinstance(self.supported, bool):
            raise TypeError("supported must be a bool")
        if self.supported:
            if self.conversion_fingerprint is None:
                raise ValueError("supported assessments require conversion_fingerprint")
            require_sha256_digest(self.conversion_fingerprint, field_name="conversion_fingerprint")
        elif self.conversion_fingerprint is not None:
            raise ValueError("unsupported assessments cannot contain conversion_fingerprint")
        normalized = tuple(self.notes)
        if any(not isinstance(note, str) or not note.strip() for note in normalized):
            raise ValueError("assessment notes must contain non-empty strings")
        object.__setattr__(self, "notes", normalized)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class LegacyImportRecord:
    """Preserved original plus the exact compatibility assessment used."""

    original: LegacyRecord
    request_fingerprint: str
    assessment: LegacyCompatibilityAssessment

    def __post_init__(self) -> None:
        if not isinstance(self.original, LegacyRecord):
            raise TypeError("original must be a LegacyRecord")
        require_sha256_digest(self.request_fingerprint, field_name="request_fingerprint")
        if not isinstance(self.assessment, LegacyCompatibilityAssessment):
            raise TypeError("assessment must be a LegacyCompatibilityAssessment")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class LegacyImportRegistry:
    records: tuple[LegacyImportRecord, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.records, tuple):
            raise TypeError("records must be a tuple")
        identities = [record.original.legacy_id for record in self.records]
        if any(not isinstance(record, LegacyImportRecord) for record in self.records):
            raise TypeError("records must contain LegacyImportRecord values")
        if len(set(identities)) != len(identities):
            raise ValueError("legacy ids must be unique in the import registry")
        if tuple(sorted(self.records, key=lambda item: item.original.legacy_id)) != self.records:
            raise ValueError("legacy records must be deterministically ordered")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class LegacyImportDecision(StrEnum):
    ACCEPT = "accept"
    REPLAY_EXISTING = "replay_existing"
    UNSUPPORTED = "unsupported"
    CONFLICT = "conflict"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class LegacyImportReport:
    decision: LegacyImportDecision
    original: LegacyRecord
    supported: bool
    conversion_fingerprint: str | None
    compatibility_notes: tuple[str, ...]
    replay_equivalent: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.decision, LegacyImportDecision):
            raise TypeError("decision must be a LegacyImportDecision")
        if not isinstance(self.original, LegacyRecord):
            raise TypeError("original must be a LegacyRecord")
        if not isinstance(self.supported, bool):
            raise TypeError("supported must be a bool")
        if self.supported:
            if self.conversion_fingerprint is None:
                raise ValueError("supported reports require conversion_fingerprint")
            require_sha256_digest(self.conversion_fingerprint, field_name="conversion_fingerprint")
        elif self.conversion_fingerprint is not None:
            raise ValueError("unsupported reports cannot contain conversion_fingerprint")
        if not isinstance(self.replay_equivalent, bool):
            raise TypeError("replay_equivalent must be a bool")
        if self.replay_equivalent:
            raise ValueError("legacy imports cannot claim replay equivalence")
        notes = tuple(self.compatibility_notes)
        if any(not isinstance(note, str) or not note.strip() for note in notes):
            raise ValueError("compatibility_notes must contain non-empty strings")
        object.__setattr__(self, "compatibility_notes", notes)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class LegacyImportResolution:
    decision: LegacyImportDecision
    registry: LegacyImportRegistry
    report: LegacyImportReport
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, LegacyImportDecision):
            raise TypeError("decision must be a LegacyImportDecision")
        if not isinstance(self.registry, LegacyImportRegistry):
            raise TypeError("registry must be a LegacyImportRegistry")
        if not isinstance(self.report, LegacyImportReport):
            raise TypeError("report must be a LegacyImportReport")
        if self.decision in {LegacyImportDecision.CONFLICT, LegacyImportDecision.REJECT} and not self.rejection_reason:
            raise ValueError("conflicts and rejections require a reason")
        if self.decision not in {LegacyImportDecision.CONFLICT, LegacyImportDecision.REJECT} and self.rejection_reason:
            raise ValueError("successful import resolutions cannot contain a reason")


def resolve_legacy_import(
    registry: LegacyImportRegistry,
    request: LegacyImportRequest,
    assessment: LegacyCompatibilityAssessment,
) -> LegacyImportResolution:
    """Preserve one original record and return an explicit compatibility report."""

    if not isinstance(registry, LegacyImportRegistry):
        raise TypeError("registry must be a LegacyImportRegistry")
    if not isinstance(request, LegacyImportRequest):
        raise TypeError("request must be a LegacyImportRequest")
    if not isinstance(assessment, LegacyCompatibilityAssessment):
        raise TypeError("assessment must be a LegacyCompatibilityAssessment")
    original = request.original
    if not request.preserve_original:
        report = LegacyImportReport(
            LegacyImportDecision.REJECT, original, False, None,
            ("preserving the original legacy record is mandatory",),
        )
        return LegacyImportResolution(
            LegacyImportDecision.REJECT, registry, report,
            "preserving the original legacy record is mandatory",
        )
    existing = next(
        (record for record in registry.records if record.original.legacy_id == original.legacy_id),
        None,
    )
    if existing is not None:
        same_request = existing.request_fingerprint == request.fingerprint
        same_assessment = existing.assessment.fingerprint == assessment.fingerprint
        if not same_request or not same_assessment:
            report = LegacyImportReport(
                LegacyImportDecision.CONFLICT,
                original,
                assessment.supported,
                assessment.conversion_fingerprint,
                assessment.notes,
            )
            return LegacyImportResolution(
                LegacyImportDecision.CONFLICT, registry, report,
                "legacy id is already bound to different import content",
            )
        report = LegacyImportReport(
            LegacyImportDecision.REPLAY_EXISTING,
            existing.original,
            existing.assessment.supported,
            existing.assessment.conversion_fingerprint,
            existing.assessment.notes,
        )
        return LegacyImportResolution(LegacyImportDecision.REPLAY_EXISTING, registry, report)
    record = LegacyImportRecord(original, request.fingerprint, assessment)
    next_registry = LegacyImportRegistry(
        tuple(sorted((*registry.records, record), key=lambda item: item.original.legacy_id))
    )
    decision = LegacyImportDecision.ACCEPT if assessment.supported else LegacyImportDecision.UNSUPPORTED
    report = LegacyImportReport(
        decision, original, assessment.supported, assessment.conversion_fingerprint, assessment.notes
    )
    return LegacyImportResolution(decision, next_registry, report)
