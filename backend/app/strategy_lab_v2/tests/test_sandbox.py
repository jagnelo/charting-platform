from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile, RuntimeIsolationRequest
from app.strategy_lab_v2.runtime_execution import StrategyRuntimeRequest
from app.strategy_lab_v2.sandbox import (
    SandboxCommandPlan,
    build_nautilus_forward_runtime_sandbox_command,
    build_nautilus_runtime_sandbox_command,
    build_nautilus_sandbox_command,
    build_sandbox_command,
    sandbox_account_equity_trace_path,
    sandbox_context_stream_digest,
    sandbox_context_stream_path,
    sandbox_engine_id,
    sandbox_forward_bootstrap_digest,
    sandbox_forward_bootstrap_path,
    sandbox_invocation_result_stream_path,
    sandbox_memory_limit_bytes,
    sandbox_native_event_stream_digest,
    sandbox_native_event_stream_path,
    sandbox_runtime_command,
    sandbox_runtime_image_digest,
)

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
    assert sandbox_runtime_image_digest(plan) == profile.runtime_image_digest
    assert sandbox_memory_limit_bytes(plan) == profile.memory_limit_bytes
    assert sandbox_runtime_command(plan) == ("python", "-m", "runner")
    assert "--env=STRATEGY_ATTEMPT_ID=attempt-1" in plan.argv
    assert not any("SECRET" in value for value in plan.argv)
    assert plan.wall_timeout_seconds == profile.wall_timeout_seconds
    assert plan.output_limit_bytes == 1234
    assert plan.fingerprint.startswith("sha256:")


def test_runtime_preflight_rejection_prevents_command_creation(tmp_path) -> None:
    profile = _profile(network_disabled=False)
    with pytest.raises(ValueError, match="network_must_be_disabled"):
        build_sandbox_command(
            _request(profile),
            profile,
            image_name="runtime",
            input_bundle_path=tmp_path / "input",
            output_path=tmp_path / "output",
            command=("python", "runner.py"),
        )
    with pytest.raises(ValueError, match="strategy_requested_network_access"):
        build_sandbox_command(
            _request(_profile(), network_requested=True),
            _profile(),
            image_name="runtime",
            input_bundle_path=tmp_path / "input",
            output_path=tmp_path / "output",
            command=("python", "runner.py"),
        )


def test_nautilus_builder_binds_engine_identity_and_preserves_image_validation(tmp_path) -> None:
    profile = _profile()
    plan = build_nautilus_sandbox_command(
        _request(profile),
        profile,
        image_name="strategy-lab/runtime",
        input_bundle_path=tmp_path / "input",
        output_path=tmp_path / "output",
        command=("python", "-m", "runner"),
    )
    assert sandbox_engine_id(plan) == "nautilus"
    assert plan.argv[19] == "--env=STRATEGY_ENGINE_ID=nautilus"
    assert "--workdir=/opt/strategy-lab-v2" in plan.argv
    assert sandbox_runtime_image_digest(plan) == profile.runtime_image_digest

    generic = build_sandbox_command(
        _request(profile),
        profile,
        image_name="strategy-lab/runtime",
        input_bundle_path=tmp_path / "input",
        output_path=tmp_path / "output",
        command=("python", "-m", "runner"),
    )
    assert sandbox_engine_id(generic) is None


def test_nautilus_runtime_builder_binds_fixed_cli_and_snapshot(tmp_path) -> None:
    profile = _profile()
    plan = build_nautilus_runtime_sandbox_command(
        _request(profile),
        profile,
        image_name="strategy-lab/runtime",
        input_bundle_path=tmp_path / "bundle.json",
        output_path=tmp_path / "result.json",
        expected_version="2.0.0rc5",
        snapshot_fingerprint=content_digest("snapshot"),
    )
    command = sandbox_runtime_command(plan)
    assert command[:3] == ("python", "-m", "app.strategy_lab_v2.nautilus_runtime_cli")
    assert command[-2:] == ("--max-input-bytes", str(profile.memory_limit_bytes // 8))


def test_nautilus_runtime_builder_binds_readonly_context_stream_sidecar(tmp_path) -> None:
    profile = _profile()
    context_digest = content_digest("context stream")
    native_event_digest = content_digest("native event stream")
    context_path = tmp_path / "contexts.ndjson"
    native_event_path = tmp_path / "native-events.ndjson"
    invocation_result_path = tmp_path / "invocations.ndjson"
    equity_trace_path = tmp_path / "account-equity.parquet"
    native_reports_path = tmp_path / "native-reports.parquet"
    plan = build_nautilus_runtime_sandbox_command(
        _request(profile),
        profile,
        image_name="strategy-lab/runtime",
        input_bundle_path=tmp_path / "bundle.json",
        output_path=tmp_path / "result.json",
        expected_version="2.0.0rc5",
        snapshot_fingerprint=content_digest("snapshot"),
        context_stream_path=context_path,
        context_stream_digest=context_digest,
        native_event_stream_path=native_event_path,
        native_event_stream_digest=native_event_digest,
        invocation_result_stream_path=invocation_result_path,
        account_equity_trace_path=equity_trace_path,
        native_reports_path=native_reports_path,
    )

    command = sandbox_runtime_command(plan)
    assert command[-16:] == (
        "--context-stream",
        "/inputs/contexts",
        "--native-event-stream",
        "/inputs/native-events",
        "--invocation-results",
        "/outputs/invocations",
        "--max-result-bytes",
        str(profile.output_limit_bytes),
        "--account-equity-trace",
        "/outputs/account-equity",
        "--max-account-equity-trace-bytes",
        str(profile.output_limit_bytes),
        "--native-reports",
        "/outputs/native-reports",
        "--max-native-reports-bytes",
        str(profile.output_limit_bytes),
    )
    assert sandbox_context_stream_path(plan) == context_path
    assert sandbox_context_stream_digest(plan) == context_digest
    assert sandbox_native_event_stream_path(plan) == native_event_path
    assert sandbox_native_event_stream_digest(plan) == native_event_digest
    assert sandbox_invocation_result_stream_path(plan) == invocation_result_path
    assert sandbox_account_equity_trace_path(plan) == equity_trace_path
    assert f"--mount=type=bind,src={context_path},dst=/inputs/contexts,readonly" in plan.argv
    assert (
        f"--mount=type=bind,src={native_event_path},dst=/inputs/native-events,readonly" in plan.argv
    )
    assert f"--mount=type=bind,src={invocation_result_path},dst=/outputs/invocations" in plan.argv
    assert f"--mount=type=bind,src={equity_trace_path},dst=/outputs/account-equity" in plan.argv
    assert f"--env=STRATEGY_CONTEXT_STREAM_DIGEST={context_digest}" in plan.argv
    assert f"--env=STRATEGY_NATIVE_EVENT_STREAM_DIGEST={native_event_digest}" in plan.argv


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


def test_forward_runtime_builder_binds_instance_and_persistent_cli_mode(tmp_path) -> None:
    profile = _profile()
    bootstrap_path = tmp_path / "forward-bootstrap.json"
    bootstrap_path.write_text("{}", encoding="utf-8")
    bootstrap_fingerprint = content_digest("forward bootstrap")
    context_path = tmp_path / "strategy-contexts.ndjson"
    context_path.write_bytes(b"strategy context artifact")
    context_digest = artifact_content_digest(context_path.read_bytes())
    native_event_path = tmp_path / "native-events.parquet"
    native_event_path.write_bytes(b"native event bytes")
    native_event_digest = artifact_content_digest(native_event_path.read_bytes())
    plan = build_nautilus_forward_runtime_sandbox_command(
        _request(profile),
        profile,
        image_name="nautilus-runtime",
        input_bundle_path=tmp_path / "input.json",
        forward_bootstrap_path=bootstrap_path,
        bootstrap_fingerprint=bootstrap_fingerprint,
        context_stream_path=context_path,
        context_stream_digest=context_digest,
        native_event_stream_path=native_event_path,
        native_event_stream_digest=native_event_digest,
        output_path=tmp_path / "output.json",
        instance_id="forward-instance-1",
        expected_version="2.0.0rc5",
        snapshot_fingerprint=content_digest("snapshot"),
    )

    command = sandbox_runtime_command(plan)
    assert "--serve-forward" in command
    assert command[command.index("--bootstrap") + 1] == "/inputs/forward-bootstrap"
    assert command[command.index("--bootstrap-fingerprint") + 1] == bootstrap_fingerprint
    assert command[command.index("--context-stream") + 1] == "/inputs/contexts"
    assert command[command.index("--native-event-stream") + 1] == "/inputs/native-events"
    instance_index = command.index("--instance-id")
    assert command[instance_index + 1] == "forward-instance-1"
    assert command[command.index("--expected-version") + 1] == "2.0.0rc5"
    assert sandbox_forward_bootstrap_path(plan) == bootstrap_path
    assert sandbox_forward_bootstrap_digest(plan) == bootstrap_fingerprint
    assert sandbox_context_stream_path(plan) == context_path
    assert sandbox_context_stream_digest(plan) == context_digest
    assert (
        f"--mount=type=bind,src={bootstrap_path},dst=/inputs/forward-bootstrap,readonly"
        in plan.argv
    )
    assert (
        f"--mount=type=bind,src={native_event_path},dst=/inputs/native-events,readonly" in plan.argv
    )
    assert f"--mount=type=bind,src={context_path},dst=/inputs/contexts,readonly" in plan.argv
