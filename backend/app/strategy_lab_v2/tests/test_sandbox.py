from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile, RuntimeIsolationRequest
from app.strategy_lab_v2.runtime_execution import StrategyRuntimeRequest
from app.strategy_lab_v2.sandbox import SandboxCommandPlan, build_sandbox_command

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _profile(*, network_disabled: bool = True) -> RuntimeIsolationProfile:
    return RuntimeIsolationProfile(
        runtime_image_digest=content_digest("image"),
        runtime_abi="python-3.12",
        network_disabled=network_disabled,
        allowed_dependency_digests=frozenset({content_digest("dep")}),
        output_limit_bytes=1234,
    )


def _request(profile: RuntimeIsolationProfile | None = None, **isolation) -> StrategyRuntimeRequest:
    profile = profile or _profile()
    return StrategyRuntimeRequest(
        content_digest("request"),
        "attempt-1",
        content_digest("package"),
        content_digest("source"),
        content_digest("inputs"),
        profile.fingerprint,
        "strategy.main:run",
        RuntimeIsolationRequest("attempt-1", (content_digest("dep"),), **isolation),
        NOW,
    )


def test_allowed_request_builds_deterministic_hardened_argv(tmp_path) -> None:
    profile = _profile()
    request = _request(profile)
    plan = build_sandbox_command(
        request,
        profile,
        image_name="strategy-lab/runtime",
        input_bundle_path=tmp_path / "input",
        output_path=tmp_path / "output",
        command=("python", "-m", "runner"),
    )
    same = build_sandbox_command(
        request,
        profile,
        image_name="strategy-lab/runtime",
        input_bundle_path=tmp_path / "input",
        output_path=tmp_path / "output",
        command=("python", "-m", "runner"),
    )
    assert plan == same
    assert plan.argv[0:2] == ("docker", "run")
    assert "--network=none" in plan.argv
    assert "--read-only" in plan.argv
    assert "--cap-drop=ALL" in plan.argv
    assert "--security-opt=no-new-privileges:true" in plan.argv
    assert "--user=65532:65532" in plan.argv
    assert f"strategy-lab/runtime@{profile.runtime_image_digest}" in plan.argv
    assert "--env=STRATEGY_ATTEMPT_ID=attempt-1" in plan.argv
    assert not any("SECRET" in value for value in plan.argv)
    assert plan.wall_timeout_seconds == profile.wall_timeout_seconds
    assert plan.output_limit_bytes == 1234
    assert plan.fingerprint.startswith("sha256:")


def test_runtime_preflight_rejection_prevents_command_creation(tmp_path) -> None:
    profile = _profile(network_disabled=False)
    with pytest.raises(ValueError, match="network_must_be_disabled"):
        build_sandbox_command(
            _request(profile), profile, image_name="runtime",
            input_bundle_path=tmp_path / "input", output_path=tmp_path / "output",
            command=("python", "runner.py"),
        )
    with pytest.raises(ValueError, match="strategy_requested_network_access"):
        build_sandbox_command(
            _request(_profile(), network_requested=True), _profile(), image_name="runtime",
            input_bundle_path=tmp_path / "input", output_path=tmp_path / "output",
            command=("python", "runner.py"),
        )


def test_paths_commands_and_image_references_are_validated(tmp_path) -> None:
    profile = _profile()
    request = _request(profile)
    kwargs = dict(
        request=request,
        profile=profile,
        image_name="runtime",
        input_bundle_path=tmp_path / "input",
        output_path=tmp_path / "output",
        command=("python", "runner.py"),
    )
    with pytest.raises(ValueError, match="absolute path"):
        build_sandbox_command(**{**kwargs, "input_bundle_path": "relative/input"})
    with pytest.raises(ValueError, match="commas"):
        build_sandbox_command(**{**kwargs, "output_path": str(tmp_path / "out,put")})
    with pytest.raises(ValueError, match="plain image"):
        build_sandbox_command(**{**kwargs, "image_name": "runtime@sha256:abc"})
    with pytest.raises(ValueError, match="executable"):
        build_sandbox_command(**{**kwargs, "command": ("--bad",)})
    with pytest.raises(ValueError, match="must not be empty"):
        build_sandbox_command(**{**kwargs, "command": ()})


def test_sandbox_command_plan_rejects_malformed_values() -> None:
    with pytest.raises(ValueError, match="must start with docker"):
        SandboxCommandPlan(content_digest("request"), content_digest("profile"), ("sh",), 1, 1)
    with pytest.raises(ValueError, match="positive integer"):
        SandboxCommandPlan(content_digest("request"), content_digest("profile"), ("docker",), 0, 1)
