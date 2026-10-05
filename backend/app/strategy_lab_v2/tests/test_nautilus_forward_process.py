from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.nautilus_forward_process import (
    HardenedNautilusForwardSessionProcessFactory,
    _forward_session_argv,
)
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile, RuntimeIsolationRequest
from app.strategy_lab_v2.runtime_execution import StrategyRuntimeRequest
from app.strategy_lab_v2.sandbox import (
    build_nautilus_forward_runtime_sandbox_command,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _profile() -> RuntimeIsolationProfile:
    return RuntimeIsolationProfile(
        runtime_image_digest=content_digest("forward-image"),
        runtime_abi="python-3.12",
        network_disabled=True,
        allowed_dependency_digests=frozenset({content_digest("dependency")}),
        output_limit_bytes=4096,
    )


def _request(profile: RuntimeIsolationProfile) -> StrategyRuntimeRequest:
    dependency = content_digest("dependency")
    return StrategyRuntimeRequest(
        request_id=content_digest("forward-request"),
        attempt_id="forward-attempt",
        package_fingerprint=content_digest("package"),
        source_digest=content_digest("source"),
        input_bundle_digest=content_digest("bootstrap"),
        runtime_profile_fingerprint=profile.fingerprint,
        entrypoint="strategy.main:Strategy",
        isolation_request=RuntimeIsolationRequest("forward-attempt", (dependency,)),
        submitted_at=NOW,
    )


def _plan(tmp_path: Path, *, instance_id: str = "forward-1"):
    input_path = tmp_path / "bootstrap.json"
    input_path.write_text("{}", encoding="utf-8")
    forward_bootstrap_path = tmp_path / "forward-session-bootstrap.json"
    forward_bootstrap_path.write_text("{}", encoding="utf-8")
    native_event_stream_path = tmp_path / "native-events.parquet"
    native_event_stream_path.write_bytes(b"native event artifact")
    output_path = tmp_path / "result.json"
    output_path.write_text("", encoding="utf-8")
    profile = _profile()
    return build_nautilus_forward_runtime_sandbox_command(
        _request(profile),
        profile,
        image_name="nautilus-runtime",
        input_bundle_path=input_path,
        forward_bootstrap_path=forward_bootstrap_path,
        bootstrap_fingerprint=content_digest("forward-session-bootstrap"),
        native_event_stream_path=native_event_stream_path,
        native_event_stream_digest=artifact_content_digest(native_event_stream_path.read_bytes()),
        output_path=output_path,
        instance_id=instance_id,
        expected_version="2.0.0rc5",
        snapshot_fingerprint=content_digest("snapshot"),
    )


def _fake_runtime_binary(tmp_path: Path) -> Path:
    backend_path = Path(__file__).resolve().parents[3]
    script = tmp_path / "docker-stub"
    script.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        f"sys.path.insert(0, {str(backend_path)!r})\n"
        "from app.strategy_lab_v2.nautilus_runtime_ipc import serve_nautilus_runtime_ipc\n"
        "class Handler:\n"
        "    def open(self, payload): return {'schema': 'strategy-lab.nautilus-forward-dto.v1', 'instance_id': payload['instance_id'], 'runtime_session_fingerprint': 'sha256:' + '0' * 64}\n"
        "    def execute(self, payload): return {'executed': True}\n"
        "    def restore(self, payload): return {'schema': 'strategy-lab.nautilus-forward-dto.v1', 'instance_id': payload['instance_id'], 'checkpoint_fingerprint': payload['checkpoint_fingerprint']}\n"
        "    def close(self, payload): return {'schema': 'strategy-lab.nautilus-forward-dto.v1', 'instance_id': payload['instance_id'], 'closed': True}\n"
        "raise SystemExit(serve_nautilus_runtime_ipc(sys.stdin.buffer, sys.stdout.buffer, Handler()))\n",
        encoding="utf-8",
    )
    script.chmod(0o700)
    return script


def test_forward_process_factory_launches_persistent_hardened_ipc(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    docker_stub = _fake_runtime_binary(tmp_path)
    factory = HardenedNautilusForwardSessionProcessFactory(
        lambda _instance_id: plan,
        docker_binary=str(docker_stub),
        response_timeout_seconds=2.0,
    )

    async def exercise() -> None:
        process = await factory.start(instance_id="forward-1")
        await process.restore(
            instance_id="forward-1",
            checkpoint_fingerprint=content_digest("checkpoint"),
        )
        await process.close()
        await process.close()

    asyncio.run(exercise())


def test_forward_process_argv_requires_exact_instance_bound_server_command(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path)
    argv = _forward_session_argv(plan, "forward-1", "docker")

    assert argv[0] == "docker"
    assert "--interactive" in argv
    assert "--network=none" in argv
    assert argv[-1] == "forward-1"
    with pytest.raises(ValueError, match="instance id differs"):
        _forward_session_argv(plan, "another-instance", "docker")
