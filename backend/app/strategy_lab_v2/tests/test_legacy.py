from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.legacy import (
    LegacyCompatibilityAssessment,
    LegacyImportDecision,
    LegacyImportRegistry,
    LegacyImportReport,
    LegacyImportRequest,
    LegacyRecordKind,
    resolve_legacy_import,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _request(kind: LegacyRecordKind = LegacyRecordKind.DEFINITION, *, requested_at: datetime = NOW, preserve_original: bool = True) -> LegacyImportRequest:
    return LegacyImportRequest(
        content_digest("request"), "legacy-1", kind, "legacy-v1",
        content_digest("payload"), requested_at, preserve_original,
    )


def _assessment(*, supported: bool = True, notes: tuple[str, ...] = ("mapped parameters",)) -> LegacyCompatibilityAssessment:
    return LegacyCompatibilityAssessment(
        "strategy-lab.legacy-map.v1", supported,
        content_digest("converted") if supported else None, notes,
    )


def test_supported_definition_import_preserves_original_and_reports_no_parity() -> None:
    result = resolve_legacy_import(LegacyImportRegistry(), _request(), _assessment())
    assert result.decision is LegacyImportDecision.ACCEPT
    assert len(result.registry.records) == 1
    assert result.report.supported is True
    assert result.report.conversion_fingerprint == content_digest("converted")
    assert result.report.replay_equivalent is False
    assert result.report.original.legacy_id == "legacy-1"


def test_exact_import_retry_replays_without_rewriting_preserved_record() -> None:
    request = _request()
    applied = resolve_legacy_import(LegacyImportRegistry(), request, _assessment())
    replay = resolve_legacy_import(
        applied.registry,
        _request(requested_at=NOW + timedelta(hours=1)),
        _assessment(),
    )
    assert replay.decision is LegacyImportDecision.REPLAY_EXISTING
    assert replay.registry == applied.registry
    assert replay.report.original == applied.registry.records[0].original


def test_unsupported_import_is_preserved_and_explicitly_labelled() -> None:
    result = resolve_legacy_import(LegacyImportRegistry(), _request(LegacyRecordKind.RESULT), _assessment(supported=False, notes=("unsupported order model",)))
    assert result.decision is LegacyImportDecision.UNSUPPORTED
    assert result.registry.records[0].original.kind is LegacyRecordKind.RESULT
    assert result.report.conversion_fingerprint is None
    assert "unsupported" in result.report.compatibility_notes[0]


def test_changed_payload_or_mapping_conflicts_without_mutation() -> None:
    applied = resolve_legacy_import(LegacyImportRegistry(), _request(), _assessment())
    changed_request = LegacyImportRequest(
        content_digest("request-2"), "legacy-1", LegacyRecordKind.DEFINITION,
        "legacy-v1", content_digest("different"), NOW, True,
    )
    conflict = resolve_legacy_import(applied.registry, changed_request, _assessment())
    assert conflict.decision is LegacyImportDecision.CONFLICT
    assert conflict.registry == applied.registry
    changed_mapping = resolve_legacy_import(applied.registry, _request(), LegacyCompatibilityAssessment("other-map", True, content_digest("converted"), ("changed",)))
    assert changed_mapping.decision is LegacyImportDecision.CONFLICT


def test_preservation_is_mandatory() -> None:
    result = resolve_legacy_import(LegacyImportRegistry(), _request(preserve_original=False), _assessment())
    assert result.decision is LegacyImportDecision.REJECT
    assert result.registry.records == ()
    assert "preserving" in (result.rejection_reason or "")


def test_assessment_and_report_reject_replay_equivalence_claims() -> None:
    with pytest.raises(ValueError, match="unsupported assessments"):
        LegacyCompatibilityAssessment("map", False, content_digest("converted"))
    with pytest.raises(ValueError, match="replay equivalence"):
        LegacyImportReport(
            LegacyImportDecision.ACCEPT,
            _request().original,
            True,
            content_digest("converted"),
            (),
            True,
        )


def test_registry_and_request_validate_types_and_identity() -> None:
    with pytest.raises(ValueError, match="request_id"):
        LegacyImportRequest("bad", "legacy-1", LegacyRecordKind.DEFINITION, "v1", content_digest("p"), NOW)
    with pytest.raises(ValueError, match="deterministically ordered"):
        first = resolve_legacy_import(LegacyImportRegistry(), _request(), _assessment()).registry.records[0]
        second = resolve_legacy_import(LegacyImportRegistry(), LegacyImportRequest(content_digest("r2"), "legacy-2", LegacyRecordKind.DEFINITION, "v1", content_digest("p2"), NOW), _assessment()).registry.records[0]
        LegacyImportRegistry((second, first))

