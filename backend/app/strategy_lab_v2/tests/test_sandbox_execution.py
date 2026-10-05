from __future__ import annotations

import hashlib
import os
import shlex
from pathlib import Path

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.sandbox import SandboxCommandPlan
from app.strategy_lab_v2.sandbox_execution import (
    SandboxRunStatus,
    run_sandbox_command,
)


def _plan(
    *, timeout: int = 2, output_limit: int = 64, output_path: str = "/tmp/strategy-output"
) -> SandboxCommandPlan:
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
            f"--mount=type=bind,src={output_path},dst=/outputs/result",
            "--env=STRATEGY_ATTEMPT_ID=attempt-1",
            f"--env=STRATEGY_INPUT_BUNDLE_DIGEST={content_digest('inputs')}",
            f"runtime@{content_digest('image')}",
            "python",
            "runner",
        ),
        timeout,
        output_limit,
    )


def _fake_binary(tmp_path: Path, body: str, *, name: str = "fake-docker") -> str:
    script = tmp_path / name
    script.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    script.chmod(0o755)
    return os.fspath(script)


def test_success_captures_bounded_output_without_inheriting_secrets(tmp_path) -> None:
    binary = _fake_binary(tmp_path, "printf 'ok'")
    output_path = tmp_path / "result.bin"
    result = run_sandbox_command(_plan(output_path=os.fspath(output_path)), docker_binary=binary)
    assert result.status is SandboxRunStatus.SUCCEEDED
    assert result.exit_code == 0
    assert result.stdout_bytes == 2
    assert result.stderr_bytes == 0
    assert result.output_bytes == 2
    assert result.error_digest is None
    assert result.result_digest == f"sha256:{hashlib.sha256(b'').hexdigest()}"
    assert result.result_bytes == 0
    assert result.stdout_digest == f"sha256:{hashlib.sha256(b'ok').hexdigest()}"
    assert output_path.is_file()
    assert output_path.stat().st_mode & 0o777 == 0o666


def test_success_hashes_the_bounded_mounted_result_file(tmp_path) -> None:
    output_path = tmp_path / "result.bin"
    binary = _fake_binary(
        tmp_path,
        f"printf 'typed-result' > {shlex.quote(os.fspath(output_path))}",
    )
    result = run_sandbox_command(_plan(output_path=os.fspath(output_path)), docker_binary=binary)
    assert result.result_digest == f"sha256:{hashlib.sha256(b'typed-result').hexdigest()}"
    assert result.result_bytes == len(b"typed-result")


def test_result_file_over_limit_is_not_reported_as_valid_evidence(tmp_path) -> None:
    output_path = tmp_path / "result.bin"
    binary = _fake_binary(
        tmp_path,
        f"printf '0123456789' > {shlex.quote(os.fspath(output_path))}",
    )
    result = run_sandbox_command(
        _plan(output_path=os.fspath(output_path), output_limit=8), docker_binary=binary
    )
    assert result.status is SandboxRunStatus.SUCCEEDED
    assert result.result_digest is None
    assert result.result_bytes is None


def test_nonzero_exit_is_failed_and_start_error_is_typed(tmp_path) -> None:
    failed_binary = _fake_binary(tmp_path, "printf 'bad' >&2; exit 7")
    failed = run_sandbox_command(
        _plan(output_path=os.fspath(tmp_path / "failed-result")), docker_binary=failed_binary
    )
    assert failed.status is SandboxRunStatus.FAILED
    assert failed.exit_code == 7
    assert failed.stderr_bytes == 3
    missing = run_sandbox_command(
        _plan(output_path=os.fspath(tmp_path / "missing-result")),
        docker_binary=os.fspath(tmp_path / "missing"),
    )
    assert missing.status is SandboxRunStatus.START_FAILED
    assert missing.exit_code is None
    assert missing.error_digest is not None
    other_missing = run_sandbox_command(
        _plan(output_path=os.fspath(tmp_path / "other-missing-result")),
        docker_binary=os.fspath(tmp_path / "other-missing"),
    )
    assert other_missing.status is SandboxRunStatus.START_FAILED
    assert other_missing.error_digest == missing.error_digest


def test_wall_timeout_kills_process_group(tmp_path) -> None:
    binary = _fake_binary(tmp_path, "sleep 5")
    result = run_sandbox_command(
        _plan(timeout=1, output_path=os.fspath(tmp_path / "timeout-result")), docker_binary=binary
    )
    assert result.status is SandboxRunStatus.TIMED_OUT
    assert result.exit_code is not None
    assert result.error_digest is not None


def test_output_limit_kills_process_and_keeps_capture_bounded(tmp_path) -> None:
    binary = _fake_binary(tmp_path, "printf '0123456789abcdef0123456789abcdef'")
    result = run_sandbox_command(
        _plan(output_limit=8, output_path=os.fspath(tmp_path / "limited-result")),
        docker_binary=binary,
    )
    assert result.status is SandboxRunStatus.OUTPUT_LIMIT_EXCEEDED
    assert result.output_bytes <= 8
    assert result.error_digest is not None


def test_invalid_plan_or_binary_arguments_fail_closed() -> None:
    with pytest.raises(TypeError, match="plan"):
        run_sandbox_command("bad")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="docker_binary"):
        run_sandbox_command(_plan(), docker_binary="\n")


def test_output_mount_requires_private_parent_and_safely_replaces_retry_output(tmp_path) -> None:
    public_directory = tmp_path / "public"
    public_directory.mkdir(mode=0o755)
    public_output = public_directory / "result.bin"
    public_result = run_sandbox_command(_plan(output_path=os.fspath(public_output)))
    assert public_result.status is SandboxRunStatus.START_FAILED
    assert public_result.error_digest is not None
    assert not public_output.exists()

    private_output = tmp_path / "existing.bin"
    private_output.write_bytes(b"existing result")
    retry_binary = _fake_binary(
        tmp_path,
        f"printf 'retry-result' > {shlex.quote(os.fspath(private_output))}",
        name="docker",
    )
    retried = run_sandbox_command(
        _plan(output_path=os.fspath(private_output)), docker_binary=retry_binary
    )
    assert retried.status is SandboxRunStatus.SUCCEEDED
    assert retried.result_digest == f"sha256:{hashlib.sha256(b'retry-result').hexdigest()}"
    assert private_output.read_bytes() == b"retry-result"


def test_output_retry_does_not_follow_or_remove_symlink_sources(tmp_path) -> None:
    protected_target = tmp_path / "protected.bin"
    protected_target.write_bytes(b"must remain untouched")
    symlink_output = tmp_path / "output-link"
    symlink_output.symlink_to(protected_target)
    docker_binary = _fake_binary(tmp_path, "exit 0", name="docker")

    result = run_sandbox_command(
        _plan(output_path=os.fspath(symlink_output)), docker_binary=docker_binary
    )

    assert result.status is SandboxRunStatus.START_FAILED
    assert result.error_digest is not None
    assert symlink_output.is_symlink()
    assert protected_target.read_bytes() == b"must remain untouched"


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
