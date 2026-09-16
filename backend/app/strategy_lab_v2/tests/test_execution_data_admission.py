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
from app.strategy_lab_v2.engine_execution import (
    EngineExecutionDecision,
    NautilusExecutionPlan,
)
from app.strategy_lab_v2.execution_data_admission import (
    DataExecutionAdmissionDecision,
    admit_data_bound_execution,
)
from app.strategy_lab_v2.snapshot_coverage import verify_snapshot_coverage
from app.strategy_lab_v2.tests.test_coverage import _attestation
from app.strategy_lab_v2.tests.test_result_publication import _result as result_fixture

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _fixtures():
    result, *_ = result_fixture()
    trial = result.trial
    snapshot = result.snapshot
    request = DataAcquisitionRequest("acquisition-1", snapshot.preflight_report, NOW)
    coverage = verify_snapshot_coverage(snapshot, (_attestation(snapshot.series[0]),))
    receipt = DataAcquisitionReceipt(
        request.fingerprint,
        snapshot.fingerprint,
        snapshot.snapshot_id,
        snapshot.provider_snapshot_id,
        coverage.fingerprint,
        content_digest("provider-receipt"),
        NOW + timedelta(minutes=1),
    )
    acquisition = verify_data_acquisition(request, snapshot, coverage, receipt)
    execution = NautilusExecutionPlan(
        trial.trial_id,
        "attempt-1",
        snapshot.fingerprint,
        "nautilus",
        "2.0.0",
        content_digest("engine-build"),
        content_digest("authorization"),
        trial.preflight_fingerprint,
        content_digest("conformance"),
        content_digest("sandbox"),
        EngineExecutionDecision.READY,
        True,
    )
    return trial, request, snapshot, acquisition, execution


def test_data_bound_execution_requires_matching_verified_acquisition() -> None:
    trial, request, snapshot, acquisition, execution = _fixtures()

    admission = admit_data_bound_execution(
        trial, request, snapshot, acquisition, execution
    )

    assert admission.decision is DataExecutionAdmissionDecision.READY
    assert admission.accepted
    assert admission.snapshot_fingerprint == snapshot.fingerprint
    assert admission.acquisition_verification_fingerprint == acquisition.fingerprint
    assert admission.execution_plan_fingerprint == execution.fingerprint


@pytest.mark.parametrize(
    ("change", "expected"),
    (
        ("acquisition", "data_acquisition_not_verified"),
        ("snapshot", "trial_snapshot_mismatch"),
        ("execution", "execution_plan_snapshot_mismatch"),
    ),
)
def test_data_bound_execution_rejects_unverified_or_identity_drift(
    change: str, expected: str
) -> None:
    trial, request, snapshot, acquisition, execution = _fixtures()
    if change == "acquisition":
        rejected = replace(
            acquisition,
            decision=DataAcquisitionDecision.REJECTED,
            mismatches=("coverage_not_verified",),
        )
        rejected_snapshot = snapshot
        rejected_trial = trial
        rejected_execution = execution
    elif change == "snapshot":
        rejected_series = replace(
            snapshot.series[0], content_digest=content_digest("other-series")
        )
        rejected = replace(snapshot, series=(rejected_series,))
        rejected_snapshot = rejected
        rejected_trial = trial
        rejected_execution = execution
    else:
        rejected = replace(execution, data_snapshot_fingerprint=content_digest("other"))
        rejected_snapshot = snapshot
        rejected_trial = trial
        rejected_execution = rejected
    admission = admit_data_bound_execution(
        rejected_trial,
        request,
        rejected_snapshot,
        rejected if change == "acquisition" else acquisition,
        rejected_execution,
    )

    assert admission.decision is DataExecutionAdmissionDecision.REJECTED
    assert expected in admission.rejection_reasons


def test_data_bound_execution_rejects_trial_and_request_preflight_drift() -> None:
    trial, request, snapshot, acquisition, execution = _fixtures()
    drifted_request = replace(request, request_id="other-request")

    admission = admit_data_bound_execution(
        trial, drifted_request, snapshot, acquisition, execution
    )

    assert admission.decision is DataExecutionAdmissionDecision.REJECTED
    assert admission.rejection_reasons == ("acquisition_request_mismatch",)


def test_data_bound_execution_requires_typed_inputs() -> None:
    values = _fixtures()
    for index, name in enumerate(
        ("trial", "request", "snapshot", "acquisition", "execution")
    ):
        invalid = list(values)
        invalid[index] = "bad"
        with pytest.raises(TypeError, match=name):
            admit_data_bound_execution(*invalid)  # type: ignore[arg-type]
