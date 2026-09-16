"""Engine-neutral authorization gate for future strategy execution adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import AttemptState, RunAttempt, ScientificTrial
from app.strategy_lab_v2.execution_capabilities import ExecutionCapabilityPreflight
from app.strategy_lab_v2.lifecycle import (
    AttemptLeaseStatus,
    ExecutionAttemptLease,
)
from app.strategy_lab_v2.strategy_validation import StrategySourceValidation


@dataclass(frozen=True, slots=True)
class ExecutionAuthorization:
    """Immutable evidence that one attempt passed all pre-execution gates."""

    trial_id: str
    attempt_id: str
    source_digest: str
    trial_preflight_fingerprint: str
    capability_preflight_fingerprint: str
    lease_id: str
    lease_worker_id: str
    authorized_at: datetime
    authoritative: bool

    def __post_init__(self) -> None:
        for name in (
            "trial_id",
            "attempt_id",
            "source_digest",
            "trial_preflight_fingerprint",
            "capability_preflight_fingerprint",
            "lease_id",
            "lease_worker_id",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"authorization {name} must not be empty")
        require_sha256_digest(self.source_digest, field_name="source_digest")
        require_sha256_digest(
            self.trial_preflight_fingerprint,
            field_name="trial_preflight_fingerprint",
        )
        require_sha256_digest(
            self.capability_preflight_fingerprint,
            field_name="capability_preflight_fingerprint",
        )
        if self.authorized_at.tzinfo is None or self.authorized_at.utcoffset() is None:
            raise ValueError("authorization time must be timezone-aware")
        if not isinstance(self.authoritative, bool):
            raise TypeError("authoritative must be a boolean")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def authorize_execution(
    trial: ScientificTrial,
    attempt: RunAttempt,
    source_validation: StrategySourceValidation,
    capability: ExecutionCapabilityPreflight,
    lease: ExecutionAttemptLease,
    *,
    now: datetime,
) -> ExecutionAuthorization:
    """Compose all pre-execution gates without importing or invoking an engine."""

    if not isinstance(trial, ScientificTrial):
        raise TypeError("trial must be a ScientificTrial")
    if not isinstance(attempt, RunAttempt):
        raise TypeError("attempt must be a RunAttempt")
    if not isinstance(source_validation, StrategySourceValidation):
        raise TypeError("source_validation must be a StrategySourceValidation")
    if not isinstance(capability, ExecutionCapabilityPreflight):
        raise TypeError("capability must be an ExecutionCapabilityPreflight")
    if not isinstance(lease, ExecutionAttemptLease):
        raise TypeError("lease must be an ExecutionAttemptLease")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("authorization time must be timezone-aware")
    if attempt.state is not AttemptState.RUNNING:
        raise ValueError("execution authorization requires a running attempt")
    if attempt.trial_id != trial.trial_id:
        raise ValueError("execution attempt must reference the scientific trial")
    if source_validation.violations:
        raise ValueError("execution authorization requires accepted strategy source")
    if capability.report_fingerprint != trial.preflight_fingerprint:
        raise ValueError("execution capability must reference the trial preflight")
    if not capability.executable:
        raise ValueError("execution capability preflight is not executable")
    if lease.attempt_id != attempt.attempt_id:
        raise ValueError("execution lease must reference the running attempt")
    if lease.status_at(now) is not AttemptLeaseStatus.ACTIVE:
        raise ValueError("execution authorization requires an active lease")
    return ExecutionAuthorization(
        trial_id=trial.trial_id,
        attempt_id=attempt.attempt_id,
        source_digest=source_validation.source_digest,
        trial_preflight_fingerprint=trial.preflight_fingerprint,
        capability_preflight_fingerprint=capability.binding_fingerprint,
        lease_id=lease.lease_id,
        lease_worker_id=lease.worker_id,
        authorized_at=now,
        authoritative=capability.can_publish_authoritative_results,
    )
