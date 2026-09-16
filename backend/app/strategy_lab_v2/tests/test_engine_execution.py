from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.conformance import (
    ConformanceCheck,
    EngineConformanceEvidence,
    EngineReleaseChannel,
    evaluate_engine_conformance,
)
from app.strategy_lab_v2.engine_execution import (
    EngineExecutionDecision,
    plan_nautilus_execution,
)
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile, RuntimeIsolationRequest
from app.strategy_lab_v2.runtime_execution import (
    StrategyRuntimeRequest,
    preflight_strategy_runtime,
)
from app.strategy_lab_v2.sandbox import SandboxCommandPlan
from app.strategy_lab_v2.tests.test_execution import _execution_fixture

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _runtime():
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
    return request, preflight_strategy_runtime(request, profile)


def _conformance(*, engine_id: str = "nautilus", channel: EngineReleaseChannel = EngineReleaseChannel.STABLE,
                 checks: frozenset[ConformanceCheck] = frozenset(ConformanceCheck)):
    evidence = EngineConformanceEvidence(
        engine_id,
        "2.0.0",
        content_digest("engine-build"),
        channel,
        content_digest("fixture"),
        checks,
        NOW,
    )
    return evidence, evaluate_engine_conformance(evidence)


def _plan(request: StrategyRuntimeRequest) -> SandboxCommandPlan:
    return SandboxCommandPlan(
        request.fingerprint,
        content_digest("profile"),
        (
            "docker",
            "run",
            "--rm",
            "--init",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--user=65532:65532",
            "--workdir=/workspace",
            "--memory=536870912",
            "--ulimit=cpu=300",
            "--ulimit=fsize=1024",
            "--pids-limit=256",
            "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=67108864",
            "--mount=type=bind,src=/tmp/strategy-input,dst=/inputs/bundle,readonly",
            "--mount=type=bind,src=/tmp/strategy-output,dst=/outputs/result,rw",
            "--env=STRATEGY_ATTEMPT_ID=attempt-1",
            f"--env=STRATEGY_INPUT_BUNDLE_DIGEST={content_digest('inputs')}",
            f"runtime@{content_digest('runtime-image')}",
            "python",
            "runner",
        ),
        10,
        1024,
    )


def test_complete_stable_nautilus_gate_is_ready_and_authoritative() -> None:
    trial, attempt, source, capability, lease = _execution_fixture(authoritative=True)
    from app.strategy_lab_v2.execution import authorize_execution

    authorization = authorize_execution(
        trial, attempt, source, capability, lease, now=NOW.replace(second=3)
    )
    request, runtime = _runtime()
    evidence, report = _conformance()
    result = plan_nautilus_execution(
        authorization,
        runtime,
        evidence,
        report,
        _plan(request),
        data_snapshot_fingerprint=content_digest("snapshot"),
    )
    assert result.decision is EngineExecutionDecision.READY
    assert result.authoritative
    assert result.engine_id == "nautilus"
    assert result.fingerprint.startswith("sha256:")


def test_release_candidate_or_non_nautilus_is_rejected_for_authoritative_runs() -> None:
    trial, attempt, source, capability, lease = _execution_fixture(authoritative=True)
    from app.strategy_lab_v2.execution import authorize_execution

    authorization = authorize_execution(
        trial, attempt, source, capability, lease, now=NOW.replace(second=3)
    )
    request, runtime = _runtime()
    evidence, report = _conformance(channel=EngineReleaseChannel.RELEASE_CANDIDATE)
    candidate = plan_nautilus_execution(
        authorization, runtime, evidence, report, _plan(request),
        data_snapshot_fingerprint=content_digest("snapshot"),
    )
    assert candidate.decision is EngineExecutionDecision.REJECT
    assert "stable_authoritative_conformance_required" in candidate.rejection_reasons

    foreign, foreign_report = _conformance(engine_id="other-engine")
    non_nautilus = plan_nautilus_execution(
        authorization, runtime, foreign, foreign_report, _plan(request),
        data_snapshot_fingerprint=content_digest("snapshot"),
    )
    assert non_nautilus.decision is EngineExecutionDecision.REJECT
    assert "only_nautilus_engine_is_supported" in non_nautilus.rejection_reasons


def test_non_authoritative_compatible_run_can_be_ready_but_is_not_authoritative() -> None:
    trial, attempt, source, capability, lease = _execution_fixture(authoritative=False)
    from app.strategy_lab_v2.execution import authorize_execution

    authorization = authorize_execution(
        trial, attempt, source, capability, lease, now=NOW.replace(second=3)
    )
    request, runtime = _runtime()
    evidence, report = _conformance(channel=EngineReleaseChannel.RELEASE_CANDIDATE)
    result = plan_nautilus_execution(
        authorization, runtime, evidence, report, _plan(request),
        data_snapshot_fingerprint=content_digest("snapshot"),
        requested_authoritative=False,
    )
    assert result.decision is EngineExecutionDecision.READY
    assert not result.authoritative


def test_mismatched_runtime_or_failed_conformance_rejects_before_invocation() -> None:
    trial, attempt, source, capability, lease = _execution_fixture(authoritative=True)
    from app.strategy_lab_v2.execution import authorize_execution

    authorization = authorize_execution(
        trial, attempt, source, capability, lease, now=NOW.replace(second=3)
    )
    request, runtime = _runtime()
    evidence, report = _conformance(
        checks=frozenset({ConformanceCheck.DETERMINISTIC_REPLAY})
    )
    mismatched_plan = SandboxCommandPlan(
        content_digest("different-request"), content_digest("profile"), ("docker", "run"), 10, 1024
    )
    result = plan_nautilus_execution(
        authorization, runtime, evidence, report, mismatched_plan,
        data_snapshot_fingerprint=content_digest("snapshot"),
    )
    assert result.decision is EngineExecutionDecision.REJECT
    assert "sandbox_runtime_request_mismatch" in result.rejection_reasons
    assert "engine_conformance_failed" in result.rejection_reasons


def test_engine_gate_rejects_forged_unhardened_sandbox_plan() -> None:
    trial, attempt, source, capability, lease = _execution_fixture(authoritative=True)
    from app.strategy_lab_v2.execution import authorize_execution

    authorization = authorize_execution(
        trial, attempt, source, capability, lease, now=NOW.replace(second=3)
    )
    request, runtime = _runtime()
    evidence, report = _conformance()
    forged = SandboxCommandPlan(
        request.fingerprint,
        content_digest("profile"),
        ("docker", "run", "--rm"),
        10,
        1024,
    )
    result = plan_nautilus_execution(
        authorization,
        runtime,
        evidence,
        report,
        forged,
        data_snapshot_fingerprint=content_digest("snapshot"),
    )
    assert result.decision is EngineExecutionDecision.REJECT
    assert result.authoritative is False
    assert "sandbox_plan_not_hardened" in result.rejection_reasons


def test_engine_plan_rejects_invalid_inputs_and_authority_shape() -> None:
    request, runtime = _runtime()
    evidence, report = _conformance()
    with pytest.raises(TypeError, match="authorization"):
        plan_nautilus_execution(
            "bad",  # type: ignore[arg-type]
            runtime, evidence, report, _plan(request),
            data_snapshot_fingerprint=content_digest("snapshot"),
        )
    with pytest.raises(ValueError, match="data_snapshot_fingerprint"):
        trial, attempt, source, capability, lease = _execution_fixture()
        from app.strategy_lab_v2.execution import authorize_execution

        authorization = authorize_execution(
            trial, attempt, source, capability, lease, now=NOW.replace(second=3)
        )
        plan_nautilus_execution(
            authorization, runtime, evidence, report, _plan(request),
            data_snapshot_fingerprint="bad",
        )
