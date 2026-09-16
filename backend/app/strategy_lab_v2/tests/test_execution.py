from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import AttemptState, RunAttempt, ScientificTrial
from app.strategy_lab_v2.execution import authorize_execution
from app.strategy_lab_v2.execution_capabilities import (
    ExecutionCapabilityPreflight,
    preflight_execution_capability,
)
from app.strategy_lab_v2.lifecycle import (
    ExecutionAttemptLease,
    acquire_attempt_lease,
    transition_attempt,
)
from app.strategy_lab_v2.strategy_validation import (
    StrategySourceValidation,
    validate_strategy_source,
)
from app.strategy_lab_v2.tests.test_execution_capabilities import _binding, _report

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _execution_fixture(
    *, authoritative: bool = True
) -> tuple[
    ScientificTrial,
    RunAttempt,
    StrategySourceValidation,
    ExecutionCapabilityPreflight,
    ExecutionAttemptLease,
]:
    report = _report()
    trial = ScientificTrial.create(
        experiment_fingerprint=content_digest("experiment"),
        snapshot_fingerprint=content_digest("snapshot"),
        preflight_report=report,
        parameter_set={"lookback": 20},
        seed=7,
    )
    queued = RunAttempt("attempt-1", trial.trial_id, 1, AttemptState.QUEUED, NOW)
    running = transition_attempt(queued, AttemptState.RUNNING, now=NOW + timedelta(seconds=1))
    capability = preflight_execution_capability(report, _binding(authoritative=authoritative))
    validation = validate_strategy_source("def signal(value):\n    return value\n")
    lease = acquire_attempt_lease(
        running,
        worker_id="worker-1",
        lease_id="lease-1",
        now=NOW + timedelta(seconds=2),
        lease_duration=timedelta(seconds=30),
    )
    return trial, running, validation, capability, lease


def test_authorize_execution_composes_all_pre_execution_gates() -> None:
    trial, attempt, validation, capability, lease = _execution_fixture(authoritative=True)

    authorization = authorize_execution(
        trial,
        attempt,
        validation,
        capability,
        lease,
        now=NOW + timedelta(seconds=3),
    )

    assert authorization.trial_id == trial.trial_id
    assert authorization.attempt_id == attempt.attempt_id
    assert authorization.lease_id == lease.lease_id
    assert authorization.authoritative
    assert authorization.fingerprint == content_digest(authorization)


def test_authorize_execution_rejects_invalid_source_capability_or_lease() -> None:
    trial, attempt, validation, capability, lease = _execution_fixture()
    invalid_source = validate_strategy_source("import os\n")
    with pytest.raises(ValueError, match="accepted strategy source"):
        authorize_execution(
            trial,
            attempt,
            invalid_source,
            capability,
            lease,
            now=NOW + timedelta(seconds=3),
        )

    unsupported = _execution_fixture(authoritative=True)[3]
    unsupported = unsupported.__class__(
        report_fingerprint=unsupported.report_fingerprint,
        binding_fingerprint=unsupported.binding_fingerprint,
        classification=unsupported.classification,
        gaps=("engine_conformance",),
        authoritative=unsupported.authoritative,
    )
    with pytest.raises(ValueError, match="not executable"):
        authorize_execution(
            trial,
            attempt,
            validation,
            unsupported,
            lease,
            now=NOW + timedelta(seconds=3),
        )

    expired = lease.renew(now=NOW + timedelta(seconds=20), lease_duration=timedelta(seconds=1))
    with pytest.raises(ValueError, match="active lease"):
        authorize_execution(
            trial,
            attempt,
            validation,
            capability,
            expired,
            now=NOW + timedelta(seconds=22),
        )


def test_non_authoritative_capability_can_run_but_cannot_publish_authoritative_results() -> None:
    trial, attempt, validation, capability, lease = _execution_fixture(authoritative=False)

    authorization = authorize_execution(
        trial,
        attempt,
        validation,
        capability,
        lease,
        now=NOW + timedelta(seconds=3),
    )

    assert not authorization.authoritative
