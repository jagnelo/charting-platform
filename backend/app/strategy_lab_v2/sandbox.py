"""Deterministic hardened container invocation plans for strategy workers.

This module does not start Docker. It turns an already-allowed
``StrategyRuntimeRequest`` into an argv-only invocation that a worker adapter
can execute with an explicit timeout. Shell interpolation, arbitrary
environment, network access, root writes, capabilities, and secret mounts are
intentionally absent from the plan.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile
from app.strategy_lab_v2.runtime_execution import (
    StrategyRuntimeDecision,
    StrategyRuntimeRequest,
    preflight_strategy_runtime,
)

_HARDENED_ARG_PREFIX = (
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
)
_HARDENED_WORKDIRS = frozenset({"--workdir=/workspace", "--workdir=/opt/strategy-lab-v2"})
_HARDENED_TMPFS = "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=67108864"
_HARDENED_PIDS_LIMIT = "--pids-limit=256"
_ENGINE_ENV_PREFIX = "--env=STRATEGY_ENGINE_ID="
_CONTEXT_STREAM_ENV_PREFIX = "--env=STRATEGY_CONTEXT_STREAM_DIGEST="
_NATIVE_EVENT_STREAM_ENV_PREFIX = "--env=STRATEGY_NATIVE_EVENT_STREAM_DIGEST="
_FORWARD_BOOTSTRAP_ENV_PREFIX = "--env=STRATEGY_FORWARD_BOOTSTRAP_DIGEST="
NAUTILUS_RUNTIME_CLI_MODULE = "app.strategy_lab_v2.nautilus_runtime_cli"


def _safe_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if any(character in value for character in "\x00\r\n"):
        raise ValueError(f"{field_name} must not contain control characters")


def _mount_path(value: str | os.PathLike[str], field_name: str) -> str:
    raw = os.fspath(value)
    _safe_text(raw, field_name)
    path = Path(raw)
    if not path.is_absolute():
        raise ValueError(f"{field_name} must be an absolute path")
    if "," in raw:
        raise ValueError(f"{field_name} must not contain commas")
    return str(path)


@dataclass(frozen=True, slots=True)
class SandboxCommandPlan:
    """Validated argv and limits for one isolated strategy invocation."""

    request_fingerprint: str
    profile_fingerprint: str
    argv: tuple[str, ...]
    wall_timeout_seconds: int
    output_limit_bytes: int

    def __post_init__(self) -> None:
        require_sha256_digest(self.request_fingerprint, field_name="request_fingerprint")
        require_sha256_digest(self.profile_fingerprint, field_name="profile_fingerprint")
        if not isinstance(self.argv, tuple) or not self.argv:
            raise ValueError("sandbox argv must not be empty")
        if self.argv[0] != "docker":
            raise ValueError("sandbox argv must start with docker")
        if any(not isinstance(value, str) or not value or "\x00" in value for value in self.argv):
            raise ValueError("sandbox argv must contain non-empty strings without NUL bytes")
        for name in ("wall_timeout_seconds", "output_limit_bytes"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def validate_sandbox_command_plan(plan: SandboxCommandPlan) -> None:
    """Fail closed unless a command plan contains every isolation control.

    ``SandboxCommandPlan`` is intentionally a public immutable value object so
    adapters can persist and compare it.  That also means callers can bypass
    :func:`build_sandbox_command` by constructing one directly.  The executor
    must therefore validate the serialized argv again immediately before
    process creation; a digest alone proves identity, not safety.
    """

    if not isinstance(plan, SandboxCommandPlan):
        raise TypeError("plan must be a SandboxCommandPlan")
    argv = plan.argv
    if len(argv) < len(_HARDENED_ARG_PREFIX) + 10:
        raise ValueError("sandbox command plan is not a complete hardened invocation")
    if (
        argv[: len(_HARDENED_ARG_PREFIX) - 1] != _HARDENED_ARG_PREFIX[:-1]
        or argv[len(_HARDENED_ARG_PREFIX) - 1] not in _HARDENED_WORKDIRS
    ):
        raise ValueError("sandbox command plan is missing required isolation controls")

    memory_flag = argv[10]
    cpu_flag = argv[11]
    file_size_flag = argv[12]
    if not memory_flag.startswith("--memory="):
        raise ValueError("sandbox command plan must declare a memory limit")
    _require_positive_option(memory_flag.removeprefix("--memory="), "memory limit")
    if not cpu_flag.startswith("--ulimit=cpu="):
        raise ValueError("sandbox command plan must declare a CPU limit")
    _require_positive_option(cpu_flag.removeprefix("--ulimit=cpu="), "CPU limit")
    if file_size_flag != f"--ulimit=fsize={plan.output_limit_bytes}":
        raise ValueError("sandbox command plan file-size limit must match its output limit")
    _require_positive_option(file_size_flag.removeprefix("--ulimit=fsize="), "file-size limit")
    if argv[13] != _HARDENED_PIDS_LIMIT or argv[14] != _HARDENED_TMPFS:
        raise ValueError("sandbox command plan is missing bounded process controls")

    input_mount_index = _mount_index(argv, "/inputs/bundle")
    output_mount_index = _mount_index(argv, "/outputs/result")
    _validate_mount(argv[input_mount_index], "/inputs/bundle", "readonly")
    _validate_mount(argv[output_mount_index], "/outputs/result", "rw")
    context_mount = _optional_mount_index(argv, "/inputs/contexts")
    native_event_mount = _optional_mount_index(argv, "/inputs/native-events")
    forward_bootstrap_mount = _optional_mount_index(argv, "/inputs/forward-bootstrap")
    invocation_result_mount = _optional_mount_index(argv, "/outputs/invocations")
    account_equity_trace_mount = _optional_mount_index(argv, "/outputs/account-equity")
    native_reports_mount = _optional_mount_index(argv, "/outputs/native-reports")
    serves_forward = "--serve-forward" in argv
    context_digest = _optional_argument_index(argv, _CONTEXT_STREAM_ENV_PREFIX)
    native_event_digest = _optional_argument_index(argv, _NATIVE_EVENT_STREAM_ENV_PREFIX)
    forward_bootstrap_digest = _optional_argument_index(argv, _FORWARD_BOOTSTRAP_ENV_PREFIX)
    if (context_mount is None) != (context_digest is None):
        raise ValueError("sandbox context stream mount and digest must be bound together")
    if serves_forward:
        if context_mount is None:
            raise ValueError(
                "forward runtime command requires its immutable strategy context stream"
            )
        if any(
            mount is not None
            for mount in (
                invocation_result_mount,
                account_equity_trace_mount,
                native_reports_mount,
            )
        ):
            raise ValueError("forward runtime must not mount backtest-only result artifacts")
    elif (
        (context_mount is None) != (invocation_result_mount is None)
        or (context_mount is None) != (account_equity_trace_mount is None)
        or (context_mount is None) != (native_reports_mount is None)
    ):
        raise ValueError(
            "sandbox context, invocation-result, and equity-trace streams must be bound together"
        )
    if context_mount is not None:
        if context_digest is None:
            raise ValueError("sandbox context stream digest is required")
        _validate_mount(argv[context_mount], "/inputs/contexts", "readonly")
        require_sha256_digest(
            argv[context_digest].removeprefix(_CONTEXT_STREAM_ENV_PREFIX),
            field_name="context stream digest",
        )
    if (native_event_mount is None) != (native_event_digest is None):
        raise ValueError("sandbox native event stream mount and digest must be bound together")
    if native_event_mount is not None:
        if context_mount is None and not serves_forward:
            raise ValueError("sandbox native event stream requires strategy context streaming")
        if native_event_digest is None:
            raise ValueError("sandbox native event stream digest is required")
        _validate_mount(argv[native_event_mount], "/inputs/native-events", "readonly")
        require_sha256_digest(
            argv[native_event_digest].removeprefix(_NATIVE_EVENT_STREAM_ENV_PREFIX),
            field_name="native event stream digest",
        )
    if serves_forward and native_event_mount is None:
        raise ValueError("forward runtime command requires its immutable native event stream")
    if (forward_bootstrap_mount is None) != (forward_bootstrap_digest is None):
        raise ValueError("forward bootstrap mount and digest must be bound together")
    if serves_forward != (forward_bootstrap_mount is not None):
        raise ValueError("forward runtime command requires its authenticated bootstrap mount")
    if forward_bootstrap_mount is not None:
        _validate_mount(argv[forward_bootstrap_mount], "/inputs/forward-bootstrap", "readonly")
        if forward_bootstrap_digest is None:
            raise ValueError("forward bootstrap digest is required")
        require_sha256_digest(
            argv[forward_bootstrap_digest].removeprefix(_FORWARD_BOOTSTRAP_ENV_PREFIX),
            field_name="forward bootstrap digest",
        )
    if invocation_result_mount is not None:
        _validate_mount(argv[invocation_result_mount], "/outputs/invocations", "rw")
    if account_equity_trace_mount is not None:
        _validate_mount(argv[account_equity_trace_mount], "/outputs/account-equity", "rw")
    if native_reports_mount is not None:
        _validate_mount(argv[native_reports_mount], "/outputs/native-reports", "rw")
    attempt_index = _argument_index(argv, "--env=STRATEGY_ATTEMPT_ID=", "attempt identity")
    if not argv[attempt_index].startswith("--env=STRATEGY_ATTEMPT_ID="):
        raise ValueError("sandbox command plan must bind the attempt identity")
    attempt_value = argv[attempt_index].removeprefix("--env=STRATEGY_ATTEMPT_ID=")
    _safe_text(attempt_value, "strategy attempt identity")
    input_digest_index = _argument_index(
        argv, "--env=STRATEGY_INPUT_BUNDLE_DIGEST=", "input bundle digest"
    )
    if not argv[input_digest_index].startswith("--env=STRATEGY_INPUT_BUNDLE_DIGEST="):
        raise ValueError("sandbox command plan must bind the input bundle digest")
    require_sha256_digest(
        argv[input_digest_index].removeprefix("--env=STRATEGY_INPUT_BUNDLE_DIGEST="),
        field_name="input bundle digest",
    )

    image_index = _image_index(argv)
    engine_index = _optional_argument_index(argv, _ENGINE_ENV_PREFIX)
    expected_options = [argv[input_mount_index]]
    if forward_bootstrap_mount is not None:
        expected_options.append(argv[forward_bootstrap_mount])
    if context_mount is not None:
        expected_options.append(argv[context_mount])
    if native_event_mount is not None:
        expected_options.append(argv[native_event_mount])
    expected_options.extend(
        [
            argv[output_mount_index],
            *(() if invocation_result_mount is None else (argv[invocation_result_mount],)),
            *(() if account_equity_trace_mount is None else (argv[account_equity_trace_mount],)),
            *(() if native_reports_mount is None else (argv[native_reports_mount],)),
            argv[attempt_index],
            argv[input_digest_index],
        ]
    )
    if forward_bootstrap_digest is not None:
        expected_options.append(argv[forward_bootstrap_digest])
    if context_digest is not None:
        expected_options.append(argv[context_digest])
    if native_event_digest is not None:
        expected_options.append(argv[native_event_digest])
    if engine_index is not None:
        expected_options.append(argv[engine_index])
    if tuple(argv[15:image_index]) != tuple(expected_options):
        raise ValueError("sandbox command plan contains unapproved Docker options")
    image = argv[image_index]
    image_name, separator, image_digest = image.rpartition("@")
    if not separator or not image_name or any(char.isspace() for char in image_name):
        raise ValueError("sandbox command plan must pin its runtime image digest")
    require_sha256_digest(image_digest, field_name="runtime image digest")
    command = argv[image_index + 1 :]
    if not command or command[0].startswith("-"):
        raise ValueError("sandbox command plan must contain an executable command")
    if any(
        not isinstance(value, str)
        or not value
        or any(character in value for character in "\x00\r\n")
        for value in command
    ):
        raise ValueError("sandbox command arguments must be non-empty and control-free")


def sandbox_output_path(plan: SandboxCommandPlan) -> Path:
    """Return the host path bound to the sandbox result mount.

    The executor uses this only after re-validating the complete command plan.
    Keeping mount parsing here avoids a second, potentially divergent parser at
    the process boundary.
    """

    if not isinstance(plan, SandboxCommandPlan):
        raise TypeError("plan must be a SandboxCommandPlan")
    validate_sandbox_command_plan(plan)
    index = _mount_index(plan.argv, "/outputs/result")
    return Path(_mount_source(plan.argv[index], "/outputs/result", "rw"))


def sandbox_input_path(plan: SandboxCommandPlan) -> Path:
    """Return the host path bound to the read-only input bundle mount."""

    if not isinstance(plan, SandboxCommandPlan):
        raise TypeError("plan must be a SandboxCommandPlan")
    validate_sandbox_command_plan(plan)
    index = _mount_index(plan.argv, "/inputs/bundle")
    return Path(_mount_source(plan.argv[index], "/inputs/bundle", "readonly"))


def sandbox_input_bundle_digest(plan: SandboxCommandPlan) -> str:
    """Return the semantic digest bound to the sandbox input mount."""

    if not isinstance(plan, SandboxCommandPlan):
        raise TypeError("plan must be a SandboxCommandPlan")
    validate_sandbox_command_plan(plan)
    index = _argument_index(plan.argv, "--env=STRATEGY_INPUT_BUNDLE_DIGEST=", "input bundle digest")
    return plan.argv[index].removeprefix("--env=STRATEGY_INPUT_BUNDLE_DIGEST=")


def sandbox_runtime_image_digest(plan: SandboxCommandPlan) -> str:
    """Return the exact pinned runtime image digest from a validated plan."""

    if not isinstance(plan, SandboxCommandPlan):
        raise TypeError("plan must be a SandboxCommandPlan")
    validate_sandbox_command_plan(plan)
    _image_name, separator, image_digest = plan.argv[_image_index(plan.argv)].rpartition("@")
    if not separator:
        raise ValueError("sandbox command plan must pin its runtime image digest")
    require_sha256_digest(image_digest, field_name="runtime image digest")
    return image_digest


def sandbox_engine_id(plan: SandboxCommandPlan) -> str | None:
    """Return the optional engine identity bound into a sandbox command."""

    if not isinstance(plan, SandboxCommandPlan):
        raise TypeError("plan must be a SandboxCommandPlan")
    validate_sandbox_command_plan(plan)
    marker_index = _optional_argument_index(plan.argv, _ENGINE_ENV_PREFIX)
    if marker_index is None:
        return None
    marker = plan.argv[marker_index]
    value = marker.removeprefix(_ENGINE_ENV_PREFIX)
    _safe_text(value, "sandbox engine identity")
    return value


def sandbox_attempt_id(plan: SandboxCommandPlan) -> str:
    """Return the attempt identity bound into a validated sandbox plan."""

    if not isinstance(plan, SandboxCommandPlan):
        raise TypeError("plan must be a SandboxCommandPlan")
    validate_sandbox_command_plan(plan)
    index = _argument_index(plan.argv, "--env=STRATEGY_ATTEMPT_ID=", "attempt identity")
    return plan.argv[index].removeprefix("--env=STRATEGY_ATTEMPT_ID=")


def sandbox_context_stream_path(plan: SandboxCommandPlan) -> Path | None:
    """Return the optional host path bound to the read-only context sidecar."""

    if not isinstance(plan, SandboxCommandPlan):
        raise TypeError("plan must be a SandboxCommandPlan")
    validate_sandbox_command_plan(plan)
    index = _optional_mount_index(plan.argv, "/inputs/contexts")
    if index is None:
        return None
    return Path(_mount_source(plan.argv[index], "/inputs/contexts", "readonly"))


def sandbox_context_stream_digest(plan: SandboxCommandPlan) -> str | None:
    """Return the optional sidecar digest bound to the sandbox environment."""

    if not isinstance(plan, SandboxCommandPlan):
        raise TypeError("plan must be a SandboxCommandPlan")
    validate_sandbox_command_plan(plan)
    index = _optional_argument_index(plan.argv, _CONTEXT_STREAM_ENV_PREFIX)
    if index is None:
        return None
    return plan.argv[index].removeprefix(_CONTEXT_STREAM_ENV_PREFIX)


def sandbox_native_event_stream_path(plan: SandboxCommandPlan) -> Path | None:
    """Return the optional host path bound to the read-only native-event sidecar."""

    if not isinstance(plan, SandboxCommandPlan):
        raise TypeError("plan must be a SandboxCommandPlan")
    validate_sandbox_command_plan(plan)
    index = _optional_mount_index(plan.argv, "/inputs/native-events")
    if index is None:
        return None
    return Path(_mount_source(plan.argv[index], "/inputs/native-events", "readonly"))


def sandbox_native_event_stream_digest(plan: SandboxCommandPlan) -> str | None:
    """Return the optional native-event digest bound to the sandbox environment."""

    if not isinstance(plan, SandboxCommandPlan):
        raise TypeError("plan must be a SandboxCommandPlan")
    validate_sandbox_command_plan(plan)
    index = _optional_argument_index(plan.argv, _NATIVE_EVENT_STREAM_ENV_PREFIX)
    if index is None:
        return None
    return plan.argv[index].removeprefix(_NATIVE_EVENT_STREAM_ENV_PREFIX)


def sandbox_forward_bootstrap_path(plan: SandboxCommandPlan) -> Path | None:
    """Return the host path bound to the read-only forward bootstrap mount."""

    if not isinstance(plan, SandboxCommandPlan):
        raise TypeError("plan must be a SandboxCommandPlan")
    validate_sandbox_command_plan(plan)
    index = _optional_mount_index(plan.argv, "/inputs/forward-bootstrap")
    if index is None:
        return None
    return Path(_mount_source(plan.argv[index], "/inputs/forward-bootstrap", "readonly"))


def sandbox_forward_bootstrap_digest(plan: SandboxCommandPlan) -> str | None:
    """Return the optional forward bootstrap fingerprint bound to a plan."""

    if not isinstance(plan, SandboxCommandPlan):
        raise TypeError("plan must be a SandboxCommandPlan")
    validate_sandbox_command_plan(plan)
    index = _optional_argument_index(plan.argv, _FORWARD_BOOTSTRAP_ENV_PREFIX)
    if index is None:
        return None
    return plan.argv[index].removeprefix(_FORWARD_BOOTSTRAP_ENV_PREFIX)


def sandbox_invocation_result_stream_path(plan: SandboxCommandPlan) -> Path | None:
    """Return the optional host path bound to streamed invocation results."""

    if not isinstance(plan, SandboxCommandPlan):
        raise TypeError("plan must be a SandboxCommandPlan")
    validate_sandbox_command_plan(plan)
    index = _optional_mount_index(plan.argv, "/outputs/invocations")
    if index is None:
        return None
    return Path(_mount_source(plan.argv[index], "/outputs/invocations", "rw"))


def sandbox_account_equity_trace_path(plan: SandboxCommandPlan) -> Path | None:
    """Return the optional host path bound to native OOS equity output."""

    if not isinstance(plan, SandboxCommandPlan):
        raise TypeError("plan must be a SandboxCommandPlan")
    validate_sandbox_command_plan(plan)
    index = _optional_mount_index(plan.argv, "/outputs/account-equity")
    if index is None:
        return None
    return Path(_mount_source(plan.argv[index], "/outputs/account-equity", "rw"))


def sandbox_native_reports_path(plan: SandboxCommandPlan) -> Path | None:
    """Return the optional host path bound to native execution report output."""

    if not isinstance(plan, SandboxCommandPlan):
        raise TypeError("plan must be a SandboxCommandPlan")
    validate_sandbox_command_plan(plan)
    index = _optional_mount_index(plan.argv, "/outputs/native-reports")
    if index is None:
        return None
    return Path(_mount_source(plan.argv[index], "/outputs/native-reports", "rw"))


def sandbox_memory_limit_bytes(plan: SandboxCommandPlan) -> int:
    """Return the positive memory bound from a validated sandbox plan."""

    if not isinstance(plan, SandboxCommandPlan):
        raise TypeError("plan must be a SandboxCommandPlan")
    validate_sandbox_command_plan(plan)
    return int(plan.argv[10].removeprefix("--memory="))


def sandbox_runtime_command(plan: SandboxCommandPlan) -> tuple[str, ...]:
    """Return the command after the pinned image in a validated plan."""

    if not isinstance(plan, SandboxCommandPlan):
        raise TypeError("plan must be a SandboxCommandPlan")
    validate_sandbox_command_plan(plan)
    return plan.argv[_image_index(plan.argv) + 1 :]


def nautilus_runtime_command(
    *,
    expected_version: str,
    snapshot_fingerprint: str,
    max_input_bytes: int,
    context_stream_digest: str | None = None,
    native_event_stream_digest: str | None = None,
    max_result_bytes: int | None = None,
) -> tuple[str, ...]:
    """Build the only supported command for an isolated Nautilus strategy run."""

    _safe_text(expected_version, "expected_version")
    require_sha256_digest(snapshot_fingerprint, field_name="snapshot_fingerprint")
    if (
        not isinstance(max_input_bytes, int)
        or isinstance(max_input_bytes, bool)
        or max_input_bytes <= 0
    ):
        raise ValueError("max_input_bytes must be a positive integer")
    if context_stream_digest is not None:
        require_sha256_digest(context_stream_digest, field_name="context_stream_digest")
    if native_event_stream_digest is not None:
        require_sha256_digest(
            native_event_stream_digest,
            field_name="native_event_stream_digest",
        )
        if context_stream_digest is None:
            raise ValueError("native event streaming requires strategy context streaming")
    command = (
        "python",
        "-m",
        NAUTILUS_RUNTIME_CLI_MODULE,
        "--input",
        "/inputs/bundle",
        "--output",
        "/outputs/result",
        "--expected-version",
        expected_version,
        "--snapshot-fingerprint",
        snapshot_fingerprint,
        "--max-input-bytes",
        str(max_input_bytes),
    )
    if context_stream_digest is None:
        if max_result_bytes is not None:
            raise ValueError("max_result_bytes requires a streaming context input")
        return command
    if (
        not isinstance(max_result_bytes, int)
        or isinstance(max_result_bytes, bool)
        or max_result_bytes <= 0
    ):
        raise ValueError("max_result_bytes must be a positive integer")
    return (
        *command,
        "--context-stream",
        "/inputs/contexts",
        *(
            ()
            if native_event_stream_digest is None
            else ("--native-event-stream", "/inputs/native-events")
        ),
        "--invocation-results",
        "/outputs/invocations",
        "--max-result-bytes",
        str(max_result_bytes),
        "--account-equity-trace",
        "/outputs/account-equity",
        "--max-account-equity-trace-bytes",
        str(max_result_bytes),
        "--native-reports",
        "/outputs/native-reports",
        "--max-native-reports-bytes",
        str(max_result_bytes),
    )


def _argument_index(argv: tuple[str, ...], prefix: str, label: str) -> int:
    matches = [index for index, value in enumerate(argv) if value.startswith(prefix)]
    if len(matches) != 1:
        raise ValueError(f"sandbox command plan must bind exactly one {label}")
    return matches[0]


def _optional_argument_index(argv: tuple[str, ...], prefix: str) -> int | None:
    matches = [index for index, value in enumerate(argv) if value.startswith(prefix)]
    if len(matches) > 1:
        raise ValueError("sandbox command plan contains duplicate bound options")
    return matches[0] if matches else None


def _mount_index(argv: tuple[str, ...], destination: str) -> int:
    index = _optional_mount_index(argv, destination)
    if index is None:
        raise ValueError(f"sandbox command plan is missing the {destination} mount")
    return index


def _optional_mount_index(argv: tuple[str, ...], destination: str) -> int | None:
    suffixes = (f",dst={destination},readonly", f",dst={destination}")
    matches = [
        index
        for index, value in enumerate(argv)
        if value.startswith("--mount=type=bind,src=")
        and any(value.endswith(suffix) for suffix in suffixes)
    ]
    if len(matches) > 1:
        raise ValueError(f"sandbox command plan contains duplicate {destination} mounts")
    return matches[0] if matches else None


def _image_index(argv: tuple[str, ...]) -> int:
    """Locate the image after the optional engine marker."""
    prefixes = (
        "--env=STRATEGY_ATTEMPT_ID=",
        "--env=STRATEGY_INPUT_BUNDLE_DIGEST=",
        _FORWARD_BOOTSTRAP_ENV_PREFIX,
        _CONTEXT_STREAM_ENV_PREFIX,
        _NATIVE_EVENT_STREAM_ENV_PREFIX,
        _ENGINE_ENV_PREFIX,
    )
    indices = [
        index
        for index, value in enumerate(argv)
        if any(value.startswith(prefix) for prefix in prefixes)
    ]
    if not indices:
        raise ValueError("sandbox command plan is missing its bound runtime environment")
    return max(indices) + 1


def _require_positive_option(value: str, label: str) -> None:
    if not value.isdecimal() or int(value) <= 0:
        raise ValueError(f"sandbox {label} must be a positive integer")


def _validate_mount(value: str, destination: str, mode: str) -> None:
    _mount_source(value, destination, mode)


def _mount_source(value: str, destination: str, mode: str) -> str:
    prefix = "--mount=type=bind,src="
    suffix = f",dst={destination},readonly" if mode == "readonly" else f",dst={destination}"
    if not value.startswith(prefix) or not value.endswith(suffix):
        raise ValueError(f"sandbox command plan must contain a {mode} {destination} mount")
    source = value[len(prefix) : -len(suffix)]
    if not source.startswith("/") or "," in source or not source.strip():
        raise ValueError("sandbox command mount sources must be absolute and comma-free")
    return source


def build_sandbox_command(
    request: StrategyRuntimeRequest,
    profile: RuntimeIsolationProfile,
    *,
    image_name: str,
    input_bundle_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    command: Sequence[str],
    working_directory: str = "/workspace",
    context_stream_path: str | os.PathLike[str] | None = None,
    context_stream_digest: str | None = None,
    native_event_stream_path: str | os.PathLike[str] | None = None,
    native_event_stream_digest: str | None = None,
    invocation_result_stream_path: str | os.PathLike[str] | None = None,
    account_equity_trace_path: str | os.PathLike[str] | None = None,
    native_reports_path: str | os.PathLike[str] | None = None,
    forward_bootstrap_path: str | os.PathLike[str] | None = None,
    forward_bootstrap_digest: str | None = None,
) -> SandboxCommandPlan:
    """Build a shell-free Docker argv after enforcing the runtime preflight."""

    if not isinstance(request, StrategyRuntimeRequest):
        raise TypeError("request must be a StrategyRuntimeRequest")
    if not isinstance(profile, RuntimeIsolationProfile):
        raise TypeError("profile must be a RuntimeIsolationProfile")
    _safe_text(image_name, "image_name")
    if (
        image_name.startswith("-")
        or "@" in image_name
        or any(char.isspace() for char in image_name)
    ):
        raise ValueError("image_name must be a plain image reference without digest or whitespace")
    if not isinstance(command, Sequence) or isinstance(command, str | bytes):
        raise TypeError("command must be a sequence of argv strings")
    command_argv = tuple(command)
    if not command_argv:
        raise ValueError("command must not be empty")
    if any(not isinstance(value, str) or not value or "\x00" in value for value in command_argv):
        raise ValueError("command must contain non-empty strings without NUL bytes")
    if command_argv[0].startswith("-"):
        raise ValueError("command executable must not begin with an option")
    if working_directory not in {"/workspace", "/opt/strategy-lab-v2"}:
        raise ValueError("working_directory must be an approved sandbox path")

    preflight = preflight_strategy_runtime(request, profile)
    if preflight.decision is not StrategyRuntimeDecision.ALLOW:
        reasons = ", ".join(preflight.rejection_reasons)
        raise ValueError(f"sandbox runtime preflight rejected: {reasons}")

    input_path = _mount_path(input_bundle_path, "input_bundle_path")
    result_path = _mount_path(output_path, "output_path")
    if (forward_bootstrap_path is None) != (forward_bootstrap_digest is None):
        raise ValueError("forward bootstrap path and digest must be provided together")
    forward_bootstrap_mount_path = (
        None
        if forward_bootstrap_path is None
        else _mount_path(forward_bootstrap_path, "forward_bootstrap_path")
    )
    if forward_bootstrap_digest is not None:
        require_sha256_digest(forward_bootstrap_digest, field_name="forward_bootstrap_digest")
    if ("--serve-forward" in command_argv) != (forward_bootstrap_mount_path is not None):
        raise ValueError("forward runtime command requires its authenticated bootstrap mount")
    if (context_stream_path is None) != (context_stream_digest is None):
        raise ValueError("context stream path and digest must be provided together")
    if (native_event_stream_path is None) != (native_event_stream_digest is None):
        raise ValueError("native event stream path and digest must be provided together")
    serves_forward = "--serve-forward" in command_argv
    if serves_forward:
        if context_stream_path is None:
            raise ValueError(
                "forward runtime command requires its immutable strategy context stream"
            )
        if any(
            value is not None
            for value in (
                invocation_result_stream_path,
                account_equity_trace_path,
                native_reports_path,
            )
        ):
            raise ValueError("forward runtime must not mount backtest-only result artifacts")
    elif (
        (context_stream_path is None) != (invocation_result_stream_path is None)
        or (context_stream_path is None) != (account_equity_trace_path is None)
        or (context_stream_path is None) != (native_reports_path is None)
    ):
        raise ValueError("context and backtest result stream paths must be provided together")
    if (
        native_event_stream_path is not None
        and context_stream_path is None
        and "--serve-forward" not in command_argv
    ):
        raise ValueError("native event streaming requires strategy context streaming")
    context_path = (
        None
        if context_stream_path is None
        else _mount_path(context_stream_path, "context_stream_path")
    )
    native_event_path = (
        None
        if native_event_stream_path is None
        else _mount_path(native_event_stream_path, "native_event_stream_path")
    )
    invocation_result_path = (
        None
        if invocation_result_stream_path is None
        else _mount_path(invocation_result_stream_path, "invocation_result_stream_path")
    )
    account_equity_path = (
        None
        if account_equity_trace_path is None
        else _mount_path(account_equity_trace_path, "account_equity_trace_path")
    )
    native_reports_output_path = (
        None
        if native_reports_path is None
        else _mount_path(native_reports_path, "native_reports_path")
    )
    if context_stream_digest is not None:
        require_sha256_digest(context_stream_digest, field_name="context_stream_digest")
    if native_event_stream_digest is not None:
        require_sha256_digest(
            native_event_stream_digest,
            field_name="native_event_stream_digest",
        )
    image = f"{image_name}@{profile.runtime_image_digest}"
    argv = (
        "docker",
        "run",
        "--rm",
        "--init",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--user=65532:65532",
        f"--workdir={working_directory}",
        f"--memory={profile.memory_limit_bytes}",
        f"--ulimit=cpu={profile.cpu_limit_seconds}",
        f"--ulimit=fsize={profile.output_limit_bytes}",
        "--pids-limit=256",
        "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=67108864",
        f"--mount=type=bind,src={input_path},dst=/inputs/bundle,readonly",
        *(
            ()
            if forward_bootstrap_mount_path is None
            else (
                f"--mount=type=bind,src={forward_bootstrap_mount_path},dst=/inputs/forward-bootstrap,readonly",
            )
        ),
        *(
            ()
            if context_path is None
            else (f"--mount=type=bind,src={context_path},dst=/inputs/contexts,readonly",)
        ),
        *(
            ()
            if native_event_path is None
            else (f"--mount=type=bind,src={native_event_path},dst=/inputs/native-events,readonly",)
        ),
        f"--mount=type=bind,src={result_path},dst=/outputs/result",
        *(
            ()
            if invocation_result_path is None
            else (f"--mount=type=bind,src={invocation_result_path},dst=/outputs/invocations",)
        ),
        *(
            ()
            if account_equity_path is None
            else (f"--mount=type=bind,src={account_equity_path},dst=/outputs/account-equity",)
        ),
        *(
            ()
            if native_reports_output_path is None
            else (
                f"--mount=type=bind,src={native_reports_output_path},dst=/outputs/native-reports",
            )
        ),
        f"--env=STRATEGY_ATTEMPT_ID={request.attempt_id}",
        f"--env=STRATEGY_INPUT_BUNDLE_DIGEST={request.input_bundle_digest}",
        *(
            ()
            if forward_bootstrap_digest is None
            else (f"{_FORWARD_BOOTSTRAP_ENV_PREFIX}{forward_bootstrap_digest}",)
        ),
        *(
            ()
            if context_stream_digest is None
            else (f"{_CONTEXT_STREAM_ENV_PREFIX}{context_stream_digest}",)
        ),
        *(
            ()
            if native_event_stream_digest is None
            else (f"{_NATIVE_EVENT_STREAM_ENV_PREFIX}{native_event_stream_digest}",)
        ),
        image,
        *command_argv,
    )
    return SandboxCommandPlan(
        request_fingerprint=request.fingerprint,
        profile_fingerprint=profile.fingerprint,
        argv=argv,
        wall_timeout_seconds=profile.wall_timeout_seconds,
        output_limit_bytes=profile.output_limit_bytes,
    )


def build_nautilus_sandbox_command(
    request: StrategyRuntimeRequest,
    profile: RuntimeIsolationProfile,
    *,
    image_name: str,
    input_bundle_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    command: Sequence[str],
    context_stream_path: str | os.PathLike[str] | None = None,
    context_stream_digest: str | None = None,
    native_event_stream_path: str | os.PathLike[str] | None = None,
    native_event_stream_digest: str | None = None,
    invocation_result_stream_path: str | os.PathLike[str] | None = None,
    account_equity_trace_path: str | os.PathLike[str] | None = None,
    native_reports_path: str | os.PathLike[str] | None = None,
    forward_bootstrap_path: str | os.PathLike[str] | None = None,
    forward_bootstrap_digest: str | None = None,
) -> SandboxCommandPlan:
    """Build a hardened command explicitly bound to the Nautilus engine."""

    plan = build_sandbox_command(
        request,
        profile,
        image_name=image_name,
        input_bundle_path=input_bundle_path,
        output_path=output_path,
        command=command,
        working_directory="/opt/strategy-lab-v2",
        context_stream_path=context_stream_path,
        context_stream_digest=context_stream_digest,
        native_event_stream_path=native_event_stream_path,
        native_event_stream_digest=native_event_stream_digest,
        invocation_result_stream_path=invocation_result_stream_path,
        account_equity_trace_path=account_equity_trace_path,
        native_reports_path=native_reports_path,
        forward_bootstrap_path=forward_bootstrap_path,
        forward_bootstrap_digest=forward_bootstrap_digest,
    )
    image_index = _image_index(plan.argv)
    argv = (*plan.argv[:image_index], f"{_ENGINE_ENV_PREFIX}nautilus", *plan.argv[image_index:])
    return replace(plan, argv=argv)


def build_nautilus_runtime_sandbox_command(
    request: StrategyRuntimeRequest,
    profile: RuntimeIsolationProfile,
    *,
    image_name: str,
    input_bundle_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    expected_version: str,
    snapshot_fingerprint: str,
    context_stream_path: str | os.PathLike[str] | None = None,
    context_stream_digest: str | None = None,
    native_event_stream_path: str | os.PathLike[str] | None = None,
    native_event_stream_digest: str | None = None,
    invocation_result_stream_path: str | os.PathLike[str] | None = None,
    account_equity_trace_path: str | os.PathLike[str] | None = None,
    native_reports_path: str | os.PathLike[str] | None = None,
) -> SandboxCommandPlan:
    """Build a hardened invocation bound to the runtime's fixed Nautilus CLI."""

    return build_nautilus_sandbox_command(
        request,
        profile,
        image_name=image_name,
        input_bundle_path=input_bundle_path,
        output_path=output_path,
        command=nautilus_runtime_command(
            expected_version=expected_version,
            snapshot_fingerprint=snapshot_fingerprint,
            max_input_bytes=max(1, profile.memory_limit_bytes // 8),
            context_stream_digest=context_stream_digest,
            native_event_stream_digest=native_event_stream_digest,
            max_result_bytes=(
                profile.output_limit_bytes if context_stream_digest is not None else None
            ),
        ),
        context_stream_path=context_stream_path,
        context_stream_digest=context_stream_digest,
        native_event_stream_path=native_event_stream_path,
        native_event_stream_digest=native_event_stream_digest,
        invocation_result_stream_path=invocation_result_stream_path,
        account_equity_trace_path=account_equity_trace_path,
        native_reports_path=native_reports_path,
    )


def nautilus_forward_runtime_command(
    *,
    instance_id: str,
    expected_version: str,
    snapshot_fingerprint: str,
    max_input_bytes: int,
    bootstrap_fingerprint: str,
    context_stream_digest: str,
    native_event_stream_digest: str,
) -> tuple[str, ...]:
    """Build the fixed CLI invocation for one persistent forward instance."""

    _safe_text(instance_id, "instance_id")
    _safe_text(expected_version, "expected_version")
    require_sha256_digest(snapshot_fingerprint, field_name="snapshot_fingerprint")
    require_sha256_digest(bootstrap_fingerprint, field_name="bootstrap_fingerprint")
    require_sha256_digest(context_stream_digest, field_name="context_stream_digest")
    require_sha256_digest(native_event_stream_digest, field_name="native_event_stream_digest")
    if (
        not isinstance(max_input_bytes, int)
        or isinstance(max_input_bytes, bool)
        or max_input_bytes <= 0
    ):
        raise ValueError("max_input_bytes must be a positive integer")
    return (
        "python",
        "-m",
        NAUTILUS_RUNTIME_CLI_MODULE,
        "--input",
        "/inputs/bundle",
        "--output",
        "/outputs/result",
        "--expected-version",
        expected_version,
        "--snapshot-fingerprint",
        snapshot_fingerprint,
        "--max-input-bytes",
        str(max_input_bytes),
        "--serve-forward",
        "--bootstrap",
        "/inputs/forward-bootstrap",
        "--bootstrap-fingerprint",
        bootstrap_fingerprint,
        "--context-stream",
        "/inputs/contexts",
        "--native-event-stream",
        "/inputs/native-events",
        "--instance-id",
        instance_id,
    )


def build_nautilus_forward_runtime_sandbox_command(
    request: StrategyRuntimeRequest,
    profile: RuntimeIsolationProfile,
    *,
    image_name: str,
    input_bundle_path: str | os.PathLike[str],
    forward_bootstrap_path: str | os.PathLike[str],
    bootstrap_fingerprint: str,
    context_stream_path: str | os.PathLike[str],
    context_stream_digest: str,
    native_event_stream_path: str | os.PathLike[str],
    native_event_stream_digest: str,
    output_path: str | os.PathLike[str],
    instance_id: str,
    expected_version: str,
    snapshot_fingerprint: str,
) -> SandboxCommandPlan:
    """Build a hardened exact-image command for a persistent forward session."""

    return build_nautilus_sandbox_command(
        request,
        profile,
        image_name=image_name,
        input_bundle_path=input_bundle_path,
        output_path=output_path,
        forward_bootstrap_path=forward_bootstrap_path,
        forward_bootstrap_digest=bootstrap_fingerprint,
        context_stream_path=context_stream_path,
        context_stream_digest=context_stream_digest,
        native_event_stream_path=native_event_stream_path,
        native_event_stream_digest=native_event_stream_digest,
        command=nautilus_forward_runtime_command(
            instance_id=instance_id,
            expected_version=expected_version,
            snapshot_fingerprint=snapshot_fingerprint,
            max_input_bytes=max(1, profile.memory_limit_bytes // 8),
            bootstrap_fingerprint=bootstrap_fingerprint,
            context_stream_digest=context_stream_digest,
            native_event_stream_digest=native_event_stream_digest,
        ),
    )


__all__ = [
    "NAUTILUS_RUNTIME_CLI_MODULE",
    "SandboxCommandPlan",
    "build_nautilus_runtime_sandbox_command",
    "build_nautilus_forward_runtime_sandbox_command",
    "build_nautilus_sandbox_command",
    "build_sandbox_command",
    "nautilus_runtime_command",
    "nautilus_forward_runtime_command",
    "sandbox_attempt_id",
    "sandbox_account_equity_trace_path",
    "sandbox_context_stream_digest",
    "sandbox_context_stream_path",
    "sandbox_invocation_result_stream_path",
    "sandbox_engine_id",
    "sandbox_memory_limit_bytes",
    "sandbox_native_event_stream_digest",
    "sandbox_native_event_stream_path",
    "sandbox_forward_bootstrap_digest",
    "sandbox_forward_bootstrap_path",
    "sandbox_native_reports_path",
    "sandbox_output_path",
    "sandbox_input_path",
    "sandbox_input_bundle_digest",
    "sandbox_runtime_command",
    "sandbox_runtime_image_digest",
    "validate_sandbox_command_plan",
]
