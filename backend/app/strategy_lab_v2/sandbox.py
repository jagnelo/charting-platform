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
from dataclasses import dataclass
from pathlib import Path

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile
from app.strategy_lab_v2.runtime_execution import (
    StrategyRuntimeDecision,
    StrategyRuntimeRequest,
    preflight_strategy_runtime,
)


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


def build_sandbox_command(
    request: StrategyRuntimeRequest,
    profile: RuntimeIsolationProfile,
    *,
    image_name: str,
    input_bundle_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    command: Sequence[str],
) -> SandboxCommandPlan:
    """Build a shell-free Docker argv after enforcing the runtime preflight."""

    if not isinstance(request, StrategyRuntimeRequest):
        raise TypeError("request must be a StrategyRuntimeRequest")
    if not isinstance(profile, RuntimeIsolationProfile):
        raise TypeError("profile must be a RuntimeIsolationProfile")
    _safe_text(image_name, "image_name")
    if image_name.startswith("-") or "@" in image_name or any(char.isspace() for char in image_name):
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

    preflight = preflight_strategy_runtime(request, profile)
    if preflight.decision is not StrategyRuntimeDecision.ALLOW:
        reasons = ", ".join(preflight.rejection_reasons)
        raise ValueError(f"sandbox runtime preflight rejected: {reasons}")

    input_path = _mount_path(input_bundle_path, "input_bundle_path")
    result_path = _mount_path(output_path, "output_path")
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
        "--workdir=/workspace",
        f"--memory={profile.memory_limit_bytes}",
        f"--ulimit=cpu={profile.cpu_limit_seconds}",
        f"--ulimit=fsize={profile.output_limit_bytes}",
        "--pids-limit=256",
        "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=67108864",
        f"--mount=type=bind,src={input_path},dst=/inputs/bundle,readonly",
        f"--mount=type=bind,src={result_path},dst=/outputs/result,rw",
        f"--env=STRATEGY_ATTEMPT_ID={request.attempt_id}",
        f"--env=STRATEGY_INPUT_BUNDLE_DIGEST={request.input_bundle_digest}",
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
