from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.sandbox import SandboxCommandPlan
from app.strategy_lab_v2.sandbox_execution import (
    SandboxRunStatus,
    run_sandbox_command,
)


def _plan(*, timeout: int = 2, output_limit: int = 64) -> SandboxCommandPlan:
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
            f"--ulimit=cpu={timeout}",
            f"--ulimit=fsize={output_limit}",
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
        timeout,
        output_limit,
    )


def _fake_binary(tmp_path: Path, body: str) -> str:
    script = tmp_path / "fake-docker"
    script.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    script.chmod(0o755)
    return os.fspath(script)


def test_success_captures_bounded_output_without_inheriting_secrets(tmp_path) -> None:
    binary = _fake_binary(tmp_path, "printf 'ok'")
    result = run_sandbox_command(_plan(), docker_binary=binary)
    assert result.status is SandboxRunStatus.SUCCEEDED
    assert result.exit_code == 0
    assert result.stdout_bytes == 2
    assert result.stderr_bytes == 0
    assert result.output_bytes == 2
    assert result.error_digest is None
    assert result.stdout_digest == f"sha256:{hashlib.sha256(b'ok').hexdigest()}"


def test_nonzero_exit_is_failed_and_start_error_is_typed(tmp_path) -> None:
    failed_binary = _fake_binary(tmp_path, "printf 'bad' >&2; exit 7")
    failed = run_sandbox_command(_plan(), docker_binary=failed_binary)
    assert failed.status is SandboxRunStatus.FAILED
    assert failed.exit_code == 7
    assert failed.stderr_bytes == 3
    missing = run_sandbox_command(_plan(), docker_binary=os.fspath(tmp_path / "missing"))
    assert missing.status is SandboxRunStatus.START_FAILED
    assert missing.exit_code is None
    assert missing.error_digest is not None


def test_wall_timeout_kills_process_group(tmp_path) -> None:
    binary = _fake_binary(tmp_path, "sleep 5")
    result = run_sandbox_command(_plan(timeout=1), docker_binary=binary)
    assert result.status is SandboxRunStatus.TIMED_OUT
    assert result.exit_code is not None
    assert result.error_digest is not None


def test_output_limit_kills_process_and_keeps_capture_bounded(tmp_path) -> None:
    binary = _fake_binary(tmp_path, "printf '0123456789abcdef0123456789abcdef'")
    result = run_sandbox_command(_plan(output_limit=8), docker_binary=binary)
    assert result.status is SandboxRunStatus.OUTPUT_LIMIT_EXCEEDED
    assert result.output_bytes <= 8
    assert result.error_digest is not None


def test_invalid_plan_or_binary_arguments_fail_closed() -> None:
    with pytest.raises(TypeError, match="plan"):
        run_sandbox_command("bad")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="docker_binary"):
        run_sandbox_command(_plan(), docker_binary="\n")


def test_forged_plan_with_missing_or_unsafe_docker_controls_is_rejected(tmp_path) -> None:
    unsafe = SandboxCommandPlan(
        content_digest("request"),
        content_digest("profile"),
        ("docker", "run", "--rm", "--network=host", "--privileged"),
        2,
        64,
    )
    with pytest.raises(ValueError, match="complete hardened|isolation controls"):
        run_sandbox_command(unsafe, docker_binary=os.fspath(tmp_path / "missing"))
