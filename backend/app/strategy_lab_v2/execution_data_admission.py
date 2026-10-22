"""Bind verified data acquisition to the final engine execution plan."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import DataSnapshot, ScientificTrial
from app.strategy_lab_v2.data_acquisition import (
    DataAcquisitionRequest,
    DataAcquisitionVerification,
)
from app.strategy_lab_v2.engine_execution import (
    EngineExecutionDecision,
    NautilusExecutionPlan,
)


class DataExecutionAdmissionDecision(StrEnum):
    READY = "ready"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class DataExecutionAdmission:
    """Immutable evidence that an engine plan is bound to verified snapshot data."""

    trial_id: str
    attempt_id: str
    snapshot_fingerprint: str
    acquisition_verification_fingerprint: str
    execution_plan_fingerprint: str
    decision: DataExecutionAdmissionDecision
    rejection_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("trial_id", "attempt_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        for name in (
            "snapshot_fingerprint",
            "acquisition_verification_fingerprint",
            "execution_plan_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        if not isinstance(self.decision, DataExecutionAdmissionDecision):
            raise TypeError("decision must be a DataExecutionAdmissionDecision")
        reasons = tuple(self.rejection_reasons)
        if len(reasons) != len(set(reasons)) or any(
            not isinstance(reason, str) or not reason.strip() for reason in reasons
        ):
            raise ValueError("data admission rejection reasons must be unique and non-empty")
        if self.decision is DataExecutionAdmissionDecision.READY and reasons:
            raise ValueError("ready data admissions cannot contain rejection reasons")
        if self.decision is DataExecutionAdmissionDecision.REJECTED and not reasons:
            raise ValueError("rejected data admissions require rejection reasons")
        object.__setattr__(self, "rejection_reasons", reasons)

    @property
    def accepted(self) -> bool:
        return self.decision is DataExecutionAdmissionDecision.READY

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def admit_data_bound_execution(
    trial: ScientificTrial,
    request: DataAcquisitionRequest,
    snapshot: DataSnapshot,
    acquisition: DataAcquisitionVerification,
    execution_plan: NautilusExecutionPlan,
) -> DataExecutionAdmission:
    """Require verified acquisition evidence before consuming an engine plan.

    This final pure gate does not start an engine or submit work.  It exists so
    a later worker cannot accidentally bypass provider coverage verification by
    passing only a snapshot digest to the lower-level Nautilus planner.
    """

    values = (trial, request, snapshot, acquisition, execution_plan)
    expected = (
        ScientificTrial,
        DataAcquisitionRequest,
        DataSnapshot,
        DataAcquisitionVerification,
        NautilusExecutionPlan,
    )
    names = ("trial", "request", "snapshot", "acquisition", "execution_plan")
    for name, value, expected_type in zip(names, values, expected, strict=True):
        if not isinstance(value, expected_type):
            raise TypeError(f"{name} must be a {expected_type.__name__}")

    reasons: list[str] = []
    if not acquisition.verified:
        reasons.append("data_acquisition_not_verified")
    if acquisition.request_fingerprint != request.fingerprint:
        reasons.append("acquisition_request_mismatch")
    if acquisition.snapshot_fingerprint != snapshot.fingerprint:
        reasons.append("acquisition_snapshot_mismatch")
    if request.preflight_fingerprint != trial.preflight_fingerprint:
        reasons.append("request_trial_preflight_mismatch")
    if trial.snapshot_fingerprint != snapshot.fingerprint:
        reasons.append("trial_snapshot_mismatch")
    if execution_plan.data_snapshot_fingerprint != snapshot.fingerprint:
        reasons.append("execution_plan_snapshot_mismatch")
    if execution_plan.trial_id != trial.trial_id:
        reasons.append("execution_plan_trial_mismatch")
    if execution_plan.decision is not EngineExecutionDecision.READY:
        reasons.append("execution_plan_not_ready")
    reasons_tuple = tuple(sorted(set(reasons)))
    decision = (
        DataExecutionAdmissionDecision.REJECTED
        if reasons_tuple
        else DataExecutionAdmissionDecision.READY
    )
    return DataExecutionAdmission(
        trial_id=trial.trial_id,
        attempt_id=execution_plan.attempt_id,
        snapshot_fingerprint=snapshot.fingerprint,
        acquisition_verification_fingerprint=acquisition.fingerprint,
        execution_plan_fingerprint=execution_plan.fingerprint,
        decision=decision,
        rejection_reasons=reasons_tuple,
    )
