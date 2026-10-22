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
import stat
import subprocess
import threading
import time
from dataclasses import dataclass
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.sandbox import (
    SandboxCommandPlan,
    sandbox_output_path,
    validate_sandbox_command_plan,
)


class SandboxRunStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    OUTPUT_LIMIT_EXCEEDED = "output_limit_exceeded"
    START_FAILED = "start_failed"


SANDBOX_ERROR_EVIDENCE_VERSION = "strategy-lab.sandbox.error.v1"


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
    result_digest: str | None = None
    result_bytes: int | None = None

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
        if self.result_digest is not None:
            require_sha256_digest(self.result_digest, field_name="result_digest")
        if self.result_bytes is not None and (
            not isinstance(self.result_bytes, int)
            or isinstance(self.result_bytes, bool)
            or self.result_bytes < 0
        ):
            raise ValueError("result_bytes must be a non-negative integer or None")
        if (self.result_digest is None) != (self.result_bytes is None):
            raise ValueError("result digest and byte count must be provided together")
        if self.status is SandboxRunStatus.SUCCEEDED and self.exit_code != 0:
            raise ValueError("successful sandbox runs require exit_code 0")
        if self.status is SandboxRunStatus.FAILED and self.exit_code in {None, 0}:
            raise ValueError("failed sandbox runs require a non-zero exit_code")
        if (
            self.status
            in {
                SandboxRunStatus.TIMED_OUT,
                SandboxRunStatus.OUTPUT_LIMIT_EXCEEDED,
                SandboxRunStatus.START_FAILED,
            }
            and self.error_digest is None
        ):
            raise ValueError("bounded or start failures require an error digest")

    @property
    def output_bytes(self) -> int:
        return self.stdout_bytes + self.stderr_bytes

    @property
    def terminal_output_digest(self) -> str:
        """Return the result-file identity, falling back to bounded stdout."""

        return self.result_digest or self.stdout_digest

    @property
    def terminal_output_bytes(self) -> int:
        """Return result-file bytes, falling back to bounded stdout bytes."""

        return self.result_bytes if self.result_bytes is not None else self.stdout_bytes

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
    try:
        _prepare_writable_output_mounts(
            plan,
            require_private_parent=os.path.basename(docker_binary) == "docker",
            allow_existing_sources=os.path.basename(docker_binary) != "docker",
        )
    except OSError as error:
        return _result(
            plan,
            SandboxRunStatus.START_FAILED,
            None,
            bytearray(),
            bytearray(),
            error_digest=_error_digest(error),
        )
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
            error_digest=_error_digest(error),
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
    result_digest, result_bytes = _capture_result_file(plan, status)
    return _result(
        plan,
        status,
        exit_code,
        stdout,
        stderr,
        error_digest=error_digest,
        result_digest=result_digest,
        result_bytes=result_bytes,
    )


def _prepare_writable_output_mounts(
    plan: SandboxCommandPlan,
    *,
    require_private_parent: bool,
    allow_existing_sources: bool,
) -> None:
    """Create private, writable file sources for Docker's output bind mounts.

    Docker's ``--mount`` form requires each bind source to exist before the
    container starts. The sandbox runs as UID/GID 65532, so its output files
    need read/write permission for that identity. Requiring an owner-only
    parent directory keeps those writable files private from other host users.
    """

    created: list[str] = []
    observed_sources: set[str] = set()
    try:
        for argument in plan.argv:
            prefix = "--mount=type=bind,src="
            if not argument.startswith(prefix) or argument.endswith(",readonly"):
                continue
            source_and_destination = argument.removeprefix(prefix)
            source, marker, destination = source_and_destination.partition(",dst=")
            if not marker:
                continue
            destination_path = destination.split(",", maxsplit=1)[0]
            if not destination_path.startswith("/outputs/"):
                continue
            if source in observed_sources:
                continue
            observed_sources.add(source)

            if require_private_parent:
                parent = os.path.dirname(source)
                parent_stat = os.stat(parent, follow_symlinks=False)
                if (
                    not stat.S_ISDIR(parent_stat.st_mode)
                    or parent_stat.st_uid != os.getuid()
                    or stat.S_IMODE(parent_stat.st_mode) & 0o077
                ):
                    raise PermissionError("sandbox output parent must be a private owned directory")

            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            flags |= getattr(os, "O_NOFOLLOW", 0)
            try:
                descriptor = os.open(source, flags, 0o666)
            except FileExistsError:
                existing_flags = os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(source, existing_flags)
                try:
                    existing_stat = os.fstat(descriptor)
                    if (
                        not stat.S_ISREG(existing_stat.st_mode)
                        or existing_stat.st_nlink != 1
                        or (not allow_existing_sources and existing_stat.st_uid != os.getuid())
                    ):
                        raise PermissionError(
                            "sandbox output source must be a regular, singly linked owned file"
                        )
                    if not allow_existing_sources:
                        path_stat = os.stat(source, follow_symlinks=False)
                        if (path_stat.st_dev, path_stat.st_ino) != (
                            existing_stat.st_dev,
                            existing_stat.st_ino,
                        ):
                            raise PermissionError(
                                "sandbox output source changed during retry setup"
                            )
                finally:
                    os.close(descriptor)
                if allow_existing_sources:
                    continue
                os.unlink(source)
                descriptor = os.open(source, flags, 0o666)
            created.append(source)
            try:
                output_stat = os.fstat(descriptor)
                if not stat.S_ISREG(output_stat.st_mode) or output_stat.st_nlink != 1:
                    raise PermissionError("sandbox output source must be a new regular file")
                os.fchmod(descriptor, 0o666)
            finally:
                os.close(descriptor)
    except OSError:
        for source in reversed(created):
            try:
                os.unlink(source)
            except OSError:
                pass
        raise


def _result(
    plan: SandboxCommandPlan,
    status: SandboxRunStatus,
    exit_code: int | None,
    stdout: bytes | bytearray,
    stderr: bytes | bytearray,
    *,
    error_digest: str | None = None,
    result_digest: str | None = None,
    result_bytes: int | None = None,
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
        result_digest=result_digest,
        result_bytes=result_bytes,
    )


def _capture_result_file(
    plan: SandboxCommandPlan,
    status: SandboxRunStatus,
) -> tuple[str | None, int | None]:
    """Hash a successful mounted result without loading it into memory.

    The application-owned publication adapter still owns reading and publishing
    bytes.  This bounded evidence lets it verify that the file it publishes is
    the exact file produced by the sandbox process.
    """

    if status is not SandboxRunStatus.SUCCEEDED:
        return None, None
    path = sandbox_output_path(plan)
    try:
        if path.is_symlink() or not path.is_file():
            return None, None
        size = path.stat().st_size
        if size > plan.output_limit_bytes:
            return None, None
        digest = hashlib.sha256()
        observed = 0
        with path.open("rb") as stream:
            while chunk := stream.read(65536):
                observed += len(chunk)
                if observed > plan.output_limit_bytes:
                    return None, None
                digest.update(chunk)
        return f"sha256:{digest.hexdigest()}", observed
    except (OSError, ValueError):
        return None, None


def _raw_digest(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _error_digest(error: BaseException) -> str:
    """Keep process-start evidence deterministic and free of host paths."""

    return content_digest(
        {
            "type": f"{type(error).__module__}.{type(error).__qualname__}",
            "version": SANDBOX_ERROR_EVIDENCE_VERSION,
        }
    )


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
