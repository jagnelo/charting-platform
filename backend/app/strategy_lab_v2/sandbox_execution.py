"""Bounded execution adapter for validated sandbox command plans.

Only a :class:`~app.strategy_lab_v2.sandbox.SandboxCommandPlan` can reach this
adapter. The command is executed without a shell, with a minimal environment
that deliberately excludes inherited secrets. Process-group termination,
wall-time enforcement, and bounded stdout/stderr capture happen here; the
strategy itself still runs inside the pinned Docker image described by the
plan.
"""

from __future__ import annotations

import hashlib
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.sandbox import SandboxCommandPlan, validate_sandbox_command_plan


class SandboxRunStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    OUTPUT_LIMIT_EXCEEDED = "output_limit_exceeded"
    START_FAILED = "start_failed"


@dataclass(frozen=True, slots=True)
class SandboxRunResult:
    """Bounded, content-addressed evidence from one sandbox process."""

    plan_fingerprint: str
    request_fingerprint: str
    status: SandboxRunStatus
    exit_code: int | None
    stdout_digest: str
    stderr_digest: str
    stdout_bytes: int
    stderr_bytes: int
    error_digest: str | None = None

    def __post_init__(self) -> None:
        require_sha256_digest(self.plan_fingerprint, field_name="plan_fingerprint")
        require_sha256_digest(self.request_fingerprint, field_name="request_fingerprint")
        if not isinstance(self.status, SandboxRunStatus):
            raise TypeError("status must be a SandboxRunStatus")
        if self.exit_code is not None and (
            not isinstance(self.exit_code, int) or isinstance(self.exit_code, bool)
        ):
            raise ValueError("exit_code must be an integer or None")
        require_sha256_digest(self.stdout_digest, field_name="stdout_digest")
        require_sha256_digest(self.stderr_digest, field_name="stderr_digest")
        for name in ("stdout_bytes", "stderr_bytes"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.error_digest is not None:
            require_sha256_digest(self.error_digest, field_name="error_digest")
        if self.status is SandboxRunStatus.SUCCEEDED and self.exit_code != 0:
            raise ValueError("successful sandbox runs require exit_code 0")
        if self.status is SandboxRunStatus.FAILED and self.exit_code in {None, 0}:
            raise ValueError("failed sandbox runs require a non-zero exit_code")
        if self.status in {
            SandboxRunStatus.TIMED_OUT,
            SandboxRunStatus.OUTPUT_LIMIT_EXCEEDED,
            SandboxRunStatus.START_FAILED,
        } and self.error_digest is None:
            raise ValueError("bounded or start failures require an error digest")

    @property
    def output_bytes(self) -> int:
        return self.stdout_bytes + self.stderr_bytes

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def run_sandbox_command(
    plan: SandboxCommandPlan,
    *,
    docker_binary: str = "docker",
) -> SandboxRunResult:
    """Execute a validated plan with bounded output and process-group cleanup.

    ``docker_binary`` exists only to make the adapter testable with a temporary
    local stand-in. Production callers leave it at ``docker``.
    """

    if not isinstance(plan, SandboxCommandPlan):
        raise TypeError("plan must be a SandboxCommandPlan")
    validate_sandbox_command_plan(plan)
    if not isinstance(docker_binary, str) or not docker_binary.strip():
        raise ValueError("docker_binary must not be empty")
    if any(character in docker_binary for character in "\x00\r\n"):
        raise ValueError("docker_binary must not contain control characters")
    argv = (docker_binary, *plan.argv[1:])
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": "/nonexistent",
        "LANG": "C",
        "LC_ALL": "C",
    }
    stdout = bytearray()
    stderr = bytearray()
    overflow = threading.Event()
    capture_lock = threading.Lock()

    def consume(stream, destination: bytearray) -> None:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                return
            with capture_lock:
                remaining = plan.output_limit_bytes - len(stdout) - len(stderr)
                if remaining > 0:
                    destination.extend(chunk[:remaining])
                if len(chunk) > max(remaining, 0):
                    overflow.set()

    try:
        process = subprocess.Popen(
            argv,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            start_new_session=True,
        )
    except OSError as error:
        return _result(
            plan,
            SandboxRunStatus.START_FAILED,
            None,
            stdout,
            stderr,
            error_digest=content_digest(str(error)),
        )

    assert process.stdout is not None
    assert process.stderr is not None
    stdout_thread = threading.Thread(target=consume, args=(process.stdout, stdout), daemon=True)
    stderr_thread = threading.Thread(target=consume, args=(process.stderr, stderr), daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    deadline = time.monotonic() + plan.wall_timeout_seconds
    status: SandboxRunStatus | None = None
    error_digest: str | None = None
    while process.poll() is None:
        if overflow.is_set():
            status = SandboxRunStatus.OUTPUT_LIMIT_EXCEEDED
            error_digest = content_digest("sandbox output limit exceeded")
            _terminate_process_group(process)
            break
        if time.monotonic() >= deadline:
            status = SandboxRunStatus.TIMED_OUT
            error_digest = content_digest("sandbox wall timeout exceeded")
            _terminate_process_group(process)
            break
        time.sleep(0.005)
    exit_code = process.wait()
    stdout_thread.join(timeout=1)
    stderr_thread.join(timeout=1)
    if status is None and overflow.is_set():
        status = SandboxRunStatus.OUTPUT_LIMIT_EXCEEDED
        error_digest = content_digest("sandbox output limit exceeded")
    if status is None:
        status = SandboxRunStatus.SUCCEEDED if exit_code == 0 else SandboxRunStatus.FAILED
    return _result(plan, status, exit_code, stdout, stderr, error_digest=error_digest)


def _result(
    plan: SandboxCommandPlan,
    status: SandboxRunStatus,
    exit_code: int | None,
    stdout: bytes | bytearray,
    stderr: bytes | bytearray,
    *,
    error_digest: str | None = None,
) -> SandboxRunResult:
    return SandboxRunResult(
        plan_fingerprint=plan.fingerprint,
        request_fingerprint=plan.request_fingerprint,
        status=status,
        exit_code=exit_code,
        stdout_digest=_raw_digest(bytes(stdout)),
        stderr_digest=_raw_digest(bytes(stderr)),
        stdout_bytes=len(stdout),
        stderr_bytes=len(stderr),
        error_digest=error_digest,
    )


def _raw_digest(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
