from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.engine_execution import EngineExecutionDecision, NautilusExecutionPlan
from app.strategy_lab_v2.nautilus_runner import NautilusRunStatus, run_nautilus_plan
from app.strategy_lab_v2.sandbox import SandboxCommandPlan


def _sandbox() -> SandboxCommandPlan:
    return SandboxCommandPlan(
        content_digest("request"),
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
            "--ulimit=cpu=2",
            "--ulimit=fsize=1024",
            "--pids-limit=256",
            "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=67108864",
            "--mount=type=bind,src=/tmp/strategy-input,dst=/inputs/bundle,readonly",
            "--mount=type=bind,src=/tmp/strategy-output,dst=/outputs/result,rw",
            "--env=STRATEGY_ATTEMPT_ID=attempt-1",
            f"--env=STRATEGY_INPUT_BUNDLE_DIGEST={content_digest('inputs')}",
            f"runtime@{content_digest('image')}",
            "python",
            "runner",
        ),
        2,
        1024,
    )


def _engine_plan(sandbox: SandboxCommandPlan, *, decision=EngineExecutionDecision.READY, authoritative=False, engine_id="nautilus") -> NautilusExecutionPlan:
    reasons = () if decision is EngineExecutionDecision.READY else ("gate rejected",)
    return NautilusExecutionPlan(
        "trial-1",
        "attempt-1",
        content_digest("snapshot"),
        engine_id,
        "2.0.0",
        content_digest("build"),
        content_digest("authorization"),
        content_digest("runtime"),
        content_digest("conformance"),
        sandbox.fingerprint,
        decision,
        authoritative,
        reasons,
    )


def _fake_binary(tmp_path: Path, body: str) -> str:
    path = tmp_path / "fake-docker"
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return os.fspath(path)


def test_rejected_or_mismatched_plans_never_spawn_a_process(tmp_path: Path) -> None:
    sandbox = _sandbox()
    rejected = run_nautilus_plan(
        _engine_plan(sandbox, decision=EngineExecutionDecision.REJECT),
        sandbox,
        docker_binary=os.fspath(tmp_path / "missing"),
    )
    assert rejected.status is NautilusRunStatus.REJECTED
    assert rejected.sandbox_result is None
    mismatch = run_nautilus_plan(
        _engine_plan(sandbox),
        SandboxCommandPlan(
            content_digest("other-request"),
            sandbox.profile_fingerprint,
            sandbox.argv,
            sandbox.wall_timeout_seconds,
            sandbox.output_limit_bytes,
        ),
        docker_binary=os.fspath(tmp_path / "missing"),
    )
    assert mismatch.status is NautilusRunStatus.REJECTED
    assert "sandbox_plan_identity_mismatch" in mismatch.rejection_reasons


def test_ready_plan_maps_sandbox_success_and_preserves_authority(tmp_path: Path) -> None:
    sandbox = _sandbox()
    result = run_nautilus_plan(
        _engine_plan(sandbox, authoritative=True),
        sandbox,
        docker_binary=_fake_binary(tmp_path, "printf 'ok'"),
    )
    assert result.status is NautilusRunStatus.SUCCEEDED
    assert result.authoritative
    assert result.sandbox_result is not None
    assert result.sandbox_result.stdout_bytes == 2
    assert result.fingerprint.startswith("sha256:")


@pytest.mark.parametrize(
    ("body", "status"),
    [("exit 7", NautilusRunStatus.FAILED), ("sleep 5", NautilusRunStatus.TIMED_OUT)],
)
def test_ready_plan_preserves_non_success_sandbox_status(tmp_path: Path, body: str, status: NautilusRunStatus) -> None:
    request_digest = content_digest("request")
    sandbox = replace(_sandbox(), request_fingerprint=request_digest, wall_timeout_seconds=1)
    result = run_nautilus_plan(
        _engine_plan(sandbox, authoritative=True),
        sandbox,
        docker_binary=_fake_binary(tmp_path, body),
    )
    assert sandbox.request_fingerprint == request_digest
    assert result.status is status
    assert not result.authoritative


def test_runner_rejects_invalid_argument_types() -> None:
    sandbox = _sandbox()
    with pytest.raises(TypeError, match="execution_plan"):
        run_nautilus_plan("bad", sandbox)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="sandbox_plan"):
        run_nautilus_plan(_engine_plan(sandbox), "bad")  # type: ignore[arg-type]
