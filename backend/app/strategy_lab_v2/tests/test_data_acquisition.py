from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.data_acquisition import (
    DataAcquisitionDecision,
    DataAcquisitionReceipt,
    DataAcquisitionRequest,
    verify_data_acquisition,
)
from app.strategy_lab_v2.snapshot_coverage import verify_snapshot_coverage
from app.strategy_lab_v2.tests.test_coverage import _attestation
from app.strategy_lab_v2.tests.test_result_publication import _result as result_fixture

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _fixture():
    result, *_ = result_fixture()
    snapshot = result.snapshot
    request = DataAcquisitionRequest("acquisition-1", snapshot.preflight_report, NOW)
    coverage = verify_snapshot_coverage(snapshot, (_attestation(snapshot.series[0]),))
    receipt = DataAcquisitionReceipt(
        request_fingerprint=request.fingerprint,
        snapshot_fingerprint=snapshot.fingerprint,
        snapshot_id=snapshot.snapshot_id,
        provider_snapshot_id=snapshot.provider_snapshot_id,
        coverage_resolution_fingerprint=coverage.fingerprint,
        provider_receipt_digest=content_digest({"provider_receipt": 1}),
        acquired_at=NOW + timedelta(minutes=1),
    )
    return request, snapshot, coverage, receipt


def test_verified_acquisition_binds_preflight_snapshot_and_coverage() -> None:
    request, snapshot, coverage, receipt = _fixture()

    report = verify_data_acquisition(request, snapshot, coverage, receipt)

    assert report.decision is DataAcquisitionDecision.VERIFIED
    assert report.verified
    assert report.mismatches == ()
    assert report.request_fingerprint == request.fingerprint
    assert report.snapshot_fingerprint == snapshot.fingerprint
    assert report.receipt_fingerprint == receipt.fingerprint
    assert report.coverage_resolution_fingerprint == coverage.fingerprint


@pytest.mark.parametrize(
    ("field", "expected"),
    (
        ("request_fingerprint", "receipt_request_fingerprint"),
        ("snapshot_fingerprint", "receipt_snapshot_fingerprint"),
        ("snapshot_id", "receipt_snapshot_id"),
        ("provider_snapshot_id", "receipt_provider_snapshot_id"),
        ("coverage_resolution_fingerprint", "receipt_coverage_resolution_fingerprint"),
        ("acquired_at", "acquisition_precedes_request"),
    ),
)
def test_receipt_identity_and_temporal_drift_rejects(field: str, expected: str) -> None:
    request, snapshot, coverage, receipt = _fixture()
    value: object = (
        content_digest("other")
        if field.endswith("fingerprint")
        else "other-id"
        if field.endswith("_id")
        else NOW - timedelta(seconds=1)
    )

    report = verify_data_acquisition(
        request,
        snapshot,
        coverage,
        replace(receipt, **{field: value}),
    )

    assert report.decision is DataAcquisitionDecision.REJECTED
    assert expected in report.mismatches


def test_unverified_or_misaligned_coverage_rejects_without_mutating_inputs() -> None:
    request, snapshot, coverage, receipt = _fixture()
    rejected_coverage = verify_snapshot_coverage(snapshot, ())
    rejected_receipt = replace(
        receipt,
        coverage_resolution_fingerprint=rejected_coverage.fingerprint,
    )

    report = verify_data_acquisition(request, snapshot, rejected_coverage, rejected_receipt)

    assert report.decision is DataAcquisitionDecision.REJECTED
    assert report.mismatches == ("coverage_not_verified",)
    assert coverage.verified
    assert receipt.coverage_resolution_fingerprint == coverage.fingerprint


def test_snapshot_and_preflight_identity_drift_is_reported() -> None:
    request, snapshot, coverage, receipt = _fixture()
    drifted_request = replace(request, request_id="acquisition-2")

    report = verify_data_acquisition(drifted_request, snapshot, coverage, receipt)

    assert report.decision is DataAcquisitionDecision.REJECTED
    assert report.mismatches == ("receipt_request_fingerprint",)


def test_acquisition_verifier_requires_typed_inputs() -> None:
    request, snapshot, coverage, receipt = _fixture()
    with pytest.raises(TypeError, match="request"):
        verify_data_acquisition("bad", snapshot, coverage, receipt)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="snapshot"):
        verify_data_acquisition(request, "bad", coverage, receipt)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="coverage"):
        verify_data_acquisition(request, snapshot, "bad", receipt)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="receipt"):
        verify_data_acquisition(request, snapshot, coverage, "bad")  # type: ignore[arg-type]
