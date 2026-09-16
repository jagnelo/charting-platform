from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.strategy_lab_v2.admission import ExecutionAdmission, ExecutionAdmissionRequest
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.engine_execution import EngineExecutionDecision, NautilusExecutionPlan
from app.strategy_lab_v2.execution import ExecutionAuthorization
from app.strategy_lab_v2.execution_orchestration import (
    ExecutionOrchestrationDecision,
    plan_execution_orchestration,
)
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile, RuntimeIsolationRequest
from app.strategy_lab_v2.runtime_execution import (
    RuntimeExecutionPhase,
    StrategyRuntimeRequest,
    new_runtime_execution_state,
    preflight_strategy_runtime,
)
from app.strategy_lab_v2.sandbox import SandboxCommandPlan
from app.strategy_lab_v2.workers import WorkerKind

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _fixtures() -> tuple:
    profile = RuntimeIsolationProfile(
        content_digest("runtime-image"),
        "python-3.12",
        allowed_dependency_digests=frozenset({content_digest("dependency")}),
    )
    request = StrategyRuntimeRequest(
        content_digest("request"),
        "attempt-1",
        content_digest("package"),
        content_digest("source"),
        content_digest("inputs"),
        profile.fingerprint,
        "strategy.main:run",
        RuntimeIsolationRequest("attempt-1", (content_digest("dependency"),)),
        NOW,
    )
    preflight = preflight_strategy_runtime(request, profile)
    state = new_runtime_execution_state(
        preflight,
        attempt_id="attempt-1",
        output_limit_bytes=1024,
        accepted_at=NOW,
    )
    sandbox = SandboxCommandPlan(
        request.fingerprint,
        profile.fingerprint,
        ("docker", "run", "--rm"),
        60,
        1024,
    )
    authorization = ExecutionAuthorization(
        "trial-1",
        "attempt-1",
        request.source_digest,
        content_digest("trial-preflight"),
        content_digest("capability"),
        "lease-1",
        "worker-1",
        NOW,
        True,
    )
    admission_request = ExecutionAdmissionRequest(
        authorization.fingerprint,
        request.fingerprint,
        "attempt-1",
        "worker-1",
        WorkerKind.BACKTEST,
        profile.fingerprint,
        content_digest("reservation"),
        NOW,
    )
    admission = ExecutionAdmission(
        admission_request.fingerprint,
        authorization.fingerprint,
        request.fingerprint,
        "attempt-1",
        "worker-1",
        WorkerKind.BACKTEST,
        profile.fingerprint,
        content_digest("reservation"),
        NOW,
        True,
    )
    engine = NautilusExecutionPlan(
        "trial-1",
        "attempt-1",
        content_digest("snapshot"),
        "nautilus",
        "2.0.0",
        content_digest("build"),
        authorization.fingerprint,
        preflight.fingerprint,
        content_digest("conformance-report"),
        sandbox.fingerprint,
        # The plan is directly constructed here; the orchestration gate still
        # verifies all identities and the ready decision.
        EngineExecutionDecision.READY,
        True,
    )
    return authorization, admission, request, preflight, state, sandbox, engine


def test_orchestration_binds_all_evidence_for_one_ready_worker_handoff() -> None:
    values = _fixtures()
    plan = plan_execution_orchestration(*values)
    assert plan.decision is ExecutionOrchestrationDecision.READY
    assert plan.accepted
    assert plan.authoritative
    assert plan.worker_id == "worker-1"
    assert plan.trial_id == "trial-1"
    assert plan.fingerprint.startswith("sha256:")


def test_orchestration_rejects_identity_drift_and_started_runtime() -> None:
    values = _fixtures()
    authorization, admission, request, preflight, state, sandbox, engine = values
    drifted = replace(engine, sandbox_plan_fingerprint=content_digest("different"))
    rejected = plan_execution_orchestration(
        authorization, admission, request, preflight, state, sandbox, drifted
    )
    assert rejected.decision is ExecutionOrchestrationDecision.REJECT
    assert "execution_plan_sandbox_mismatch" in rejected.rejection_reasons

    started = replace(state, phase=RuntimeExecutionPhase.RUNNING, sequence=1)
    rejected_started = plan_execution_orchestration(
        authorization, admission, request, preflight, started, sandbox, engine
    )
    assert rejected_started.decision is ExecutionOrchestrationDecision.REJECT
    assert "runtime_state_already_started" in rejected_started.rejection_reasons


def test_orchestration_rejects_authority_and_limit_drift() -> None:
    values = _fixtures()
    authorization, admission, request, preflight, state, sandbox, engine = values
    not_authorized = replace(admission, authoritative=False)
    rejected_authority = plan_execution_orchestration(
        authorization, not_authorized, request, preflight, state, sandbox, engine
    )
    assert rejected_authority.decision is ExecutionOrchestrationDecision.REJECT
    assert "authoritative_execution_not_admitted" in rejected_authority.rejection_reasons

    wrong_limit = replace(sandbox, output_limit_bytes=512)
    rejected_limit = plan_execution_orchestration(
        authorization, admission, request, preflight, state, wrong_limit, engine
    )
    assert rejected_limit.decision is ExecutionOrchestrationDecision.REJECT
    assert "runtime_output_limit_mismatch" in rejected_limit.rejection_reasons


def test_orchestration_validates_argument_types() -> None:
    values = _fixtures()
    with pytest.raises(TypeError, match="authorization"):
        plan_execution_orchestration("bad", *values[1:])  # type: ignore[arg-type]
