from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from app.strategy_lab_v2.artifact_store import (
    ArtifactCleanupDecision,
    ArtifactCleanupKind,
    ArtifactCleanupRecord,
    ArtifactCleanupResolution,
)
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import CapabilityCell, CapabilityRequirement
from app.strategy_lab_v2.contracts import AdjustmentMode, EventGranularity, ProductClass
from app.strategy_lab_v2.coverage import CoverageAttestation

UTC_PLUS_TWO = timezone(timedelta(hours=2))
START = datetime(2024, 1, 1, tzinfo=UTC)
END = datetime(2024, 1, 2, tzinfo=UTC)


def _requirement(start: datetime, end: datetime) -> CapabilityRequirement:
    return CapabilityRequirement(
        "US.AAPL",
        ProductClass.EQUITY,
        EventGranularity.BAR,
        "ohlcv",
        "1d",
        start,
        end,
        AdjustmentMode.SPLIT_ADJUSTED,
        "regular",
        "consolidated",
        "bar-close-v1",
        "cash-equity-v1",
        "split-adjusted-v1",
    )


def _cell(history_start: datetime, history_end: datetime) -> CapabilityCell:
    return CapabilityCell(
        "US.AAPL",
        ProductClass.EQUITY,
        frozenset({EventGranularity.BAR}),
        frozenset({"ohlcv"}),
        frozenset({"1d"}),
        frozenset({AdjustmentMode.SPLIT_ADJUSTED}),
        frozenset({"regular"}),
        frozenset({"consolidated"}),
        frozenset({"bar-close-v1"}),
        frozenset({"cash-equity-v1"}),
        frozenset({"split-adjusted-v1"}),
        history_start,
        history_end,
        content_digest("capability-evidence"),
    )


def _attestation(start: datetime, end: datetime, attested_at: datetime) -> CoverageAttestation:
    return CoverageAttestation(
        content_digest("coverage-evidence"),
        content_digest("series"),
        "US.AAPL",
        "ohlcv",
        EventGranularity.BAR,
        "1d",
        "regular",
        "consolidated",
        AdjustmentMode.SPLIT_ADJUSTED,
        "split-adjusted-v1",
        start,
        end,
        100,
        content_digest("calendar"),
        True,
        True,
        "provider-fixture",
        attested_at,
    )


def _cleanup_record(modified_at: datetime) -> ArtifactCleanupRecord:
    return ArtifactCleanupRecord(
        ArtifactCleanupKind.CONTENT,
        content_digest("payload"),
        "ab/payload",
        7,
        modified_at,
        ArtifactCleanupDecision.RETAINED,
        "committed",
    )


def test_capability_requirement_and_cell_normalize_offset_equivalent_history() -> None:
    local_start = datetime(2024, 1, 1, 2, tzinfo=UTC_PLUS_TWO)
    local_end = datetime(2024, 1, 2, 2, tzinfo=UTC_PLUS_TWO)

    requirement = _requirement(local_start, local_end)
    cell = _cell(local_start, local_end)

    assert requirement.start == START
    assert requirement.end == END
    assert cell.history_start == START
    assert cell.history_end == END
    assert content_digest(requirement) == content_digest(_requirement(START, END))
    assert content_digest(cell) == content_digest(_cell(START, END))


def test_coverage_attestation_normalizes_series_and_evidence_timestamps() -> None:
    local_start = datetime(2024, 1, 1, 2, tzinfo=UTC_PLUS_TWO)
    local_end = datetime(2024, 1, 2, 2, tzinfo=UTC_PLUS_TWO)
    local_attested = datetime(2024, 1, 3, 2, tzinfo=UTC_PLUS_TWO)

    attestation = _attestation(local_start, local_end, local_attested)
    equivalent = _attestation(START, END, datetime(2024, 1, 3, tzinfo=UTC))

    assert attestation.start == START
    assert attestation.end == END
    assert attestation.attested_at == equivalent.attested_at
    assert attestation.fingerprint == equivalent.fingerprint


def test_artifact_cleanup_evidence_normalizes_record_and_observation_times() -> None:
    local_modified = datetime(2024, 1, 1, 2, tzinfo=UTC_PLUS_TWO)
    local_observed = datetime(2024, 1, 2, 2, tzinfo=UTC_PLUS_TWO)
    record = _cleanup_record(local_modified)
    resolution = ArtifactCleanupResolution(local_observed, timedelta(hours=1), (record,))
    equivalent = ArtifactCleanupResolution(
        START + timedelta(days=1),
        timedelta(hours=1),
        (_cleanup_record(START),),
    )

    assert record.modified_at == START
    assert resolution.observed_at == END
    assert resolution.fingerprint == equivalent.fingerprint
