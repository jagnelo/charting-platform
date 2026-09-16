from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile, RuntimeIsolationRequest
from app.strategy_lab_v2.runtime_execution import (
    RuntimeExecutionPhase,
    StrategyRuntimeRequest,
    new_runtime_execution_state,
    preflight_strategy_runtime,
)
from app.strategy_lab_v2.runtime_result_adapter import (
    RuntimeResultDecision,
    materialize_sandbox_result,
)
from app.strategy_lab_v2.sandbox import SandboxCommandPlan
from app.strategy_lab_v2.sandbox_execution import SandboxRunResult, SandboxRunStatus

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _fixtures() -> tuple:
    profile = RuntimeIsolationProfile(
        content_digest("runtime-image"),
        "python-3.12",
        allowed_dependency_digests=frozenset({content_digest("dep")}),
    )
    request = StrategyRuntimeRequest(
        content_digest("runtime-request"),
        "attempt-1",
        content_digest("package"),
        content_digest("source"),
        content_digest("inputs"),
        profile.fingerprint,
        "strategy.main:run",
        RuntimeIsolationRequest("attempt-1", (content_digest("dep"),)),
        NOW,
    )
    preflight = preflight_strategy_runtime(request, profile)
    state = new_runtime_execution_state(
        preflight,
        attempt_id="attempt-1",
        output_limit_bytes=1024,
        accepted_at=NOW,
    )
    plan = SandboxCommandPlan(
        request.fingerprint,
        profile.fingerprint,
        ("docker", "run", "--rm"),
        2,
        1024,
    )
    return state, plan


def _result(plan: SandboxCommandPlan, status: SandboxRunStatus) -> SandboxRunResult:
    return SandboxRunResult(
        plan.fingerprint,
        plan.request_fingerprint,
        status,
        0 if status is SandboxRunStatus.SUCCEEDED else 7,
        content_digest("stdout"),
        content_digest("stderr"),
        6,
        0,
        None if status is SandboxRunStatus.SUCCEEDED else content_digest("error"),
    )


def test_success_materializes_running_then_terminal_runtime_state() -> None:
    state, plan = _fixtures()
    result = materialize_sandbox_result(
        state,
        plan,
        _result(plan, SandboxRunStatus.SUCCEEDED),
        observed_at=NOW,
    )
    assert result.decision is RuntimeResultDecision.SUCCEEDED
    assert result.state.phase is RuntimeExecutionPhase.SUCCEEDED
    assert result.state.sequence == 2
    assert result.state.output_digest == content_digest("stdout")
    assert result.state.output_bytes == 6


def test_failed_sandbox_status_materializes_typed_runtime_failure() -> None:
    state, plan = _fixtures()
    result = materialize_sandbox_result(
        state,
        plan,
        _result(plan, SandboxRunStatus.FAILED),
        observed_at=NOW,
    )
    assert result.decision is RuntimeResultDecision.FAILED
    assert result.state.phase is RuntimeExecutionPhase.FAILED
    assert result.state.error_digest == content_digest("error")


def test_exact_terminal_retry_replays_and_drift_rejects() -> None:
    state, plan = _fixtures()
    sandbox_result = _result(plan, SandboxRunStatus.SUCCEEDED)
    applied = materialize_sandbox_result(state, plan, sandbox_result, observed_at=NOW)
    replay = materialize_sandbox_result(
        applied.state,
        plan,
        sandbox_result,
        observed_at=NOW,
    )
    assert replay.decision is RuntimeResultDecision.REPLAY_EXISTING
    conflicting_result = SandboxRunResult(
        plan.fingerprint,
        plan.request_fingerprint,
        SandboxRunStatus.SUCCEEDED,
        0,
        content_digest("different-stdout"),
        content_digest("stderr"),
        15,
        0,
    )
    conflict = materialize_sandbox_result(
        applied.state,
        plan,
        conflicting_result,
        observed_at=NOW,
    )
    assert conflict.decision is RuntimeResultDecision.REJECT
    mismatch = materialize_sandbox_result(
        state,
        SandboxCommandPlan(
            content_digest("different-request"),
            plan.profile_fingerprint,
            plan.argv,
            plan.wall_timeout_seconds,
            plan.output_limit_bytes,
        ),
        sandbox_result,
        observed_at=NOW,
    )
    assert mismatch.decision is RuntimeResultDecision.REJECT
    assert mismatch.rejection_reason


def test_invalid_arguments_and_time_fail_closed() -> None:
    state, plan = _fixtures()
    result = _result(plan, SandboxRunStatus.SUCCEEDED)
    with pytest.raises(TypeError, match="state"):
        materialize_sandbox_result("bad", plan, result, observed_at=NOW)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="timezone-aware"):
        materialize_sandbox_result(state, plan, result, observed_at=datetime(2024, 1, 1))
