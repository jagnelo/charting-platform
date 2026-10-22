from __future__ import annotations

from dataclasses import replace

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.coverage import CoverageVerificationDecision
from app.strategy_lab_v2.snapshot_coverage import (
    SnapshotCoverageDecision,
    verify_snapshot_coverage,
)
from app.strategy_lab_v2.tests.test_coverage import _attestation
from app.strategy_lab_v2.tests.test_result_publication import _result as result_fixture


def _snapshot_and_attestation():
    result, *_ = result_fixture()
    snapshot = result.snapshot
    return snapshot, _attestation(snapshot.series[0])


def test_snapshot_coverage_requires_and_verifies_every_series_attestation() -> None:
    snapshot, attestation = _snapshot_and_attestation()
    resolved = verify_snapshot_coverage(snapshot, (attestation,))

    assert resolved.decision is SnapshotCoverageDecision.VERIFIED
    assert resolved.verified
    assert resolved.snapshot_fingerprint == snapshot.fingerprint
    assert len(resolved.reports) == 1
    assert resolved.reports[0].decision is CoverageVerificationDecision.VERIFIED
    assert resolved.attestation_fingerprints == (attestation.fingerprint,)


def test_missing_extra_and_duplicate_attestations_fail_closed() -> None:
    snapshot, attestation = _snapshot_and_attestation()
    missing = verify_snapshot_coverage(snapshot, ())
    assert missing.decision is SnapshotCoverageDecision.REJECTED
    assert missing.missing_series_digests == (snapshot.series[0].content_digest,)
    assert missing.reports == ()

    duplicate = verify_snapshot_coverage(snapshot, (attestation, attestation))
    assert duplicate.decision is SnapshotCoverageDecision.REJECTED
    assert duplicate.unexpected_series_digests == (snapshot.series[0].content_digest,)
    assert "unexpected_series" in (duplicate.rejection_reason or "")

    extra = replace(attestation, series_content_digest=content_digest("foreign-series"))
    unexpected = verify_snapshot_coverage(snapshot, (extra,))
    assert unexpected.decision is SnapshotCoverageDecision.REJECTED
    assert unexpected.unexpected_series_digests == (content_digest("foreign-series"),)


def test_mismatched_attestation_is_reported_without_advancing_snapshot() -> None:
    snapshot, attestation = _snapshot_and_attestation()
    rejected = verify_snapshot_coverage(
        snapshot,
        (replace(attestation, row_count=attestation.row_count + 1),),
    )

    assert rejected.decision is SnapshotCoverageDecision.REJECTED
    assert rejected.reports[0].decision is CoverageVerificationDecision.REJECTED
    assert "row_count" in (rejected.rejection_reason or "")
    assert rejected.snapshot_fingerprint == snapshot.fingerprint


def test_snapshot_coverage_rejects_untyped_inputs() -> None:
    snapshot, attestation = _snapshot_and_attestation()
    with pytest.raises(TypeError, match="snapshot"):
        verify_snapshot_coverage("bad", (attestation,))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="attestations"):
        verify_snapshot_coverage(snapshot, "bad")  # type: ignore[arg-type]
