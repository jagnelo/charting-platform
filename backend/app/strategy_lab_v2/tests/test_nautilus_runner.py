from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import ArtifactManifest, ArtifactRetention
from app.strategy_lab_v2.engine_execution import EngineExecutionDecision, NautilusExecutionPlan
from app.strategy_lab_v2.nautilus_runner import NautilusRunStatus, run_nautilus_plan
from app.strategy_lab_v2.nautilus_runtime_bundle import (
    NAUTILUS_RUNTIME_ARTIFACT_MEDIA_TYPE,
    NAUTILUS_RUNTIME_ARTIFACT_SCHEMA,
    NautilusRuntimeInputArtifactReference,
)
from app.strategy_lab_v2.sandbox import SandboxCommandPlan, nautilus_runtime_command


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
            "--mount=type=bind,src=/tmp/strategy-output,dst=/outputs/result",
            "--env=STRATEGY_ATTEMPT_ID=attempt-1",
            f"--env=STRATEGY_INPUT_BUNDLE_DIGEST={content_digest('inputs')}",
            "--env=STRATEGY_ENGINE_ID=nautilus",
            f"runtime@{content_digest('image')}",
            *nautilus_runtime_command(
                expected_version="2.0.0",
                snapshot_fingerprint=content_digest("snapshot"),
                max_input_bytes=536870912 // 8,
            ),
        ),
        2,
        1024,
    )


def _engine_plan(
    sandbox: SandboxCommandPlan,
    *,
    decision=EngineExecutionDecision.READY,
    authoritative=False,
    engine_id="nautilus",
) -> NautilusExecutionPlan:
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
def test_ready_plan_preserves_non_success_sandbox_status(
    tmp_path: Path, body: str, status: NautilusRunStatus
) -> None:
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


def test_runner_rejects_unmarked_or_non_nautilus_sandbox_before_spawn(tmp_path: Path) -> None:
    sandbox = _sandbox()
    unmarked = replace(sandbox, argv=(*sandbox.argv[:19], *sandbox.argv[20:]))
    unmarked_result = run_nautilus_plan(
        _engine_plan(unmarked),
        unmarked,
        docker_binary=os.fspath(tmp_path / "missing"),
    )
    assert unmarked_result.status is NautilusRunStatus.REJECTED
    assert "nautilus_sandbox_engine_marker_required" in unmarked_result.rejection_reasons

    other_engine = replace(
        sandbox,
        argv=(*sandbox.argv[:19], "--env=STRATEGY_ENGINE_ID=python", *sandbox.argv[20:]),
    )
    other_engine_result = run_nautilus_plan(
        _engine_plan(other_engine),
        other_engine,
        docker_binary=os.fspath(tmp_path / "missing"),
    )
    assert other_engine_result.status is NautilusRunStatus.REJECTED
    assert "nautilus_sandbox_engine_marker_required" in other_engine_result.rejection_reasons


def test_runner_rejects_unbound_command_and_attempt_before_spawn(tmp_path: Path) -> None:
    sandbox = _sandbox()
    arbitrary = replace(sandbox, argv=(*sandbox.argv[:-13], "python", "runner.py"))
    arbitrary_result = run_nautilus_plan(
        _engine_plan(arbitrary), arbitrary, docker_binary=os.fspath(tmp_path / "missing")
    )
    assert arbitrary_result.status is NautilusRunStatus.REJECTED
    assert "nautilus_runtime_command_required" in arbitrary_result.rejection_reasons

    wrong_attempt_argv = (
        *sandbox.argv[:17],
        "--env=STRATEGY_ATTEMPT_ID=attempt-other",
        *sandbox.argv[18:],
    )
    wrong_attempt = replace(sandbox, argv=wrong_attempt_argv)
    attempt_result = run_nautilus_plan(
        _engine_plan(wrong_attempt),
        wrong_attempt,
        docker_binary=os.fspath(tmp_path / "missing"),
    )
    assert attempt_result.status is NautilusRunStatus.REJECTED
    assert "nautilus_sandbox_attempt_mismatch" in attempt_result.rejection_reasons


def test_runner_rejects_runtime_input_artifact_byte_drift_before_spawn(tmp_path: Path) -> None:
    expected_bytes = b"expected bundle"
    mounted_bytes = b"x" * len(expected_bytes)
    assert len(expected_bytes) == len(mounted_bytes)
    input_path = tmp_path / "bundle.json"
    input_path.write_bytes(mounted_bytes)
    sandbox = _sandbox()
    sandbox_argv = list(sandbox.argv)
    sandbox_argv[15] = f"--mount=type=bind,src={input_path},dst=/inputs/bundle,readonly"
    sandbox = replace(sandbox, argv=tuple(sandbox_argv))
    digest = artifact_content_digest(expected_bytes)
    reference = NautilusRuntimeInputArtifactReference(
        "attempt-1",
        content_digest("inputs"),
        ArtifactManifest(
            digest,
            len(expected_bytes),
            NAUTILUS_RUNTIME_ARTIFACT_MEDIA_TYPE,
            NAUTILUS_RUNTIME_ARTIFACT_SCHEMA,
            digest,
            ArtifactRetention.PINNED_INPUT,
        ),
    )

    result = run_nautilus_plan(
        _engine_plan(sandbox),
        sandbox,
        docker_binary=os.fspath(tmp_path / "missing"),
        runtime_input_artifact=reference,
    )

    assert result.status is NautilusRunStatus.REJECTED
    assert "nautilus_input_artifact_integrity_failed" in result.rejection_reasons
    assert result.sandbox_result is None

    wrong_snapshot_command = nautilus_runtime_command(
        expected_version="2.0.0",
        snapshot_fingerprint=content_digest("different snapshot"),
        max_input_bytes=536870912 // 8,
    )
    wrong_snapshot = replace(
        sandbox,
        argv=(*sandbox.argv[: -len(wrong_snapshot_command)], *wrong_snapshot_command),
    )
    snapshot_result = run_nautilus_plan(
        _engine_plan(wrong_snapshot),
        wrong_snapshot,
        docker_binary=os.fspath(tmp_path / "missing"),
    )
    assert snapshot_result.status is NautilusRunStatus.REJECTED
    assert "nautilus_runtime_command_required" in snapshot_result.rejection_reasons
