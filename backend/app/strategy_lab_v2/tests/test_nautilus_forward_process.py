from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.forward_context import ForwardPortfolioContextPreparation
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.nautilus_event_adapter import (
    NautilusForwardDeliveryBinding,
    materialize_nautilus_forward_tape,
)
from app.strategy_lab_v2.nautilus_forward_bootstrap import (
    NautilusForwardBootstrapComponent,
    NautilusForwardRuntimeBootstrap,
)
from app.strategy_lab_v2.nautilus_forward_input import NautilusForwardDeliveryInput
from app.strategy_lab_v2.nautilus_forward_process import (
    HardenedNautilusForwardSessionProcessFactory,
    _forward_session_argv,
    _validate_forward_launch_context,
)
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile, RuntimeIsolationRequest
from app.strategy_lab_v2.runtime_execution import StrategyRuntimeRequest
from app.strategy_lab_v2.sandbox import (
    build_nautilus_forward_runtime_sandbox_command,
)
from app.strategy_lab_v2.sdk import MarketEvent

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


def _bootstrap(instance_id: str, checkpoint_fingerprint: str) -> NautilusForwardRuntimeBootstrap:
    digest = content_digest
    component = NautilusForwardBootstrapComponent(
        component_id="component-1",
        execution_binding_fingerprint=digest("execution-binding"),
        resolved_component_fingerprint=digest("resolved-component"),
        strategy_fingerprint=digest("strategy"),
        package_fingerprint=digest("package"),
        package_archive_digest=digest("package-archive"),
        dependency_lock_digest=digest("dependency-lock"),
        manifest_fingerprint=digest("manifest"),
        source_digest=digest("source"),
        parameters_digest=digest("parameters"),
        random_seed=17,
    )
    return NautilusForwardRuntimeBootstrap(
        instance_id=instance_id,
        execution_plan_fingerprint=digest("execution-plan"),
        portfolio_fingerprint=digest("portfolio"),
        snapshot_fingerprint=digest("snapshot"),
        warmup_receipt_fingerprint=digest("warmup-receipt"),
        warmup_result_fingerprint=digest("warmup-result"),
        warmup_tape_fingerprint=digest("warmup-tape"),
        warmup_event_count=0,
        warmup_source_artifact_digests=(),
        warmup_cursor_event_id=None,
        warmup_cursor_sequence=0,
        warmup_cursor_event_fingerprint=None,
        processed_checkpoint_fingerprint=checkpoint_fingerprint,
        processed_prefix_fingerprint=digest("processed-prefix"),
        before_event_fingerprint=digest("before-event"),
        engine_input_fingerprint=digest("engine-input"),
        runtime_input_bundle_digest=digest("runtime-bundle"),
        native_event_stream_digest=digest("native-event-stream"),
        native_event_stream_adapter_version="adapter-v1",
        components=(component,),
        processed_events=(),
    )


def _plan(
    tmp_path: Path,
    *,
    instance_id: str = "forward-1",
    checkpoint_fingerprint: str | None = None,
):
    input_path = tmp_path / "bootstrap.json"
    input_path.write_text("{}", encoding="utf-8")
    forward_bootstrap_path = tmp_path / "forward-session-bootstrap.json"
    checkpoint = checkpoint_fingerprint or content_digest("checkpoint")
    bootstrap = _bootstrap(instance_id, checkpoint)
    forward_bootstrap_path.write_bytes(bootstrap.to_json_bytes())
    context_stream_path = tmp_path / "strategy-contexts.ndjson"
    context_stream_path.write_bytes(b"strategy context artifact")
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
        bootstrap_fingerprint=bootstrap.fingerprint,
        context_stream_path=context_stream_path,
        context_stream_digest=artifact_content_digest(context_stream_path.read_bytes()),
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
        "    def open(self, payload): return {'schema': 'strategy-lab.nautilus-forward-dto.v2', 'instance_id': payload['instance_id'], 'runtime_session_fingerprint': 'sha256:' + '0' * 64, 'base_checkpoint_fingerprint': payload['checkpoint_fingerprint']}\n"
        "    def execute(self, payload): return {'executed': True}\n"
        "    def restore(self, payload): return {'schema': 'strategy-lab.nautilus-forward-dto.v2', 'instance_id': payload['instance_id'], 'checkpoint_fingerprint': payload['checkpoint_fingerprint']}\n"
        "    def close(self, payload): return {'schema': 'strategy-lab.nautilus-forward-dto.v2', 'instance_id': payload['instance_id'], 'closed': True}\n"
        "raise SystemExit(serve_nautilus_runtime_ipc(sys.stdin.buffer, sys.stdout.buffer, Handler()))\n",
        encoding="utf-8",
    )
    script.chmod(0o700)
    return script


def _delivery_input() -> NautilusForwardDeliveryInput:
    canonical = CanonicalForwardEvent(
        "event-1",
        1,
        NOW,
        NOW,
        content_digest("canonical-source"),
    )
    market = MarketEvent(
        "dependency-1",
        canonical.event_id,
        "US.ABC",
        canonical.event_time,
        canonical.sequence,
        {"open": 10, "high": 10, "low": 10, "close": 10, "volume": 1},
    )
    binding = NautilusForwardDeliveryBinding(
        "forward-1",
        content_digest(canonical),
        "1-0",
        content_digest("redis-entry"),
        content_digest("dispatch"),
        content_digest("request"),
        content_digest("checkpoint"),
        content_digest("warmup"),
        "enqueue",
    )
    tape = materialize_nautilus_forward_tape(
        "forward-1",
        (canonical,),
        (market,),
        event_type_by_dependency={"dependency-1": "ohlcv"},
        delivery_bindings=(binding,),
    )
    return NautilusForwardDeliveryInput(binding, tape, market, canonical.source_digest)


def _portfolio_preparation(
    delivery: NautilusForwardDeliveryInput,
) -> ForwardPortfolioContextPreparation:
    binding = delivery.delivery_binding
    return ForwardPortfolioContextPreparation(
        instance_id=binding.instance_id,
        payload_fingerprint=delivery.verified_market_payload.fingerprint,
        delivery_binding_fingerprint=binding.fingerprint,
        dispatch_fingerprint=binding.dispatch_record_fingerprint,
        pre_event_checkpoint_fingerprint=binding.pre_event_checkpoint_fingerprint,
        warmup_receipt_fingerprint=binding.warmup_receipt_fingerprint,
        component_preparations={},
    )


def test_forward_process_factory_launches_persistent_hardened_ipc(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    docker_stub = _fake_runtime_binary(tmp_path)
    checkpoint_fingerprint = content_digest("checkpoint")
    factory = HardenedNautilusForwardSessionProcessFactory(
        lambda _instance_id, _checkpoint_fingerprint: plan,
        docker_binary=str(docker_stub),
        response_timeout_seconds=2.0,
    )

    async def exercise() -> None:
        process = await factory.start(
            instance_id="forward-1",
            checkpoint_fingerprint=checkpoint_fingerprint,
        )
        assert process.base_checkpoint_fingerprint == checkpoint_fingerprint
        await process.restore(
            instance_id="forward-1",
            checkpoint_fingerprint=content_digest("checkpoint"),
        )
        await process.close()
        await process.close()

    asyncio.run(exercise())


def test_forward_process_factory_requires_delivery_and_preparation_together(
    tmp_path: Path,
) -> None:
    factory = HardenedNautilusForwardSessionProcessFactory(
        lambda _instance_id, _checkpoint: pytest.fail("plan builder must not run"),
        docker_binary=str(tmp_path / "must-not-launch"),
    )

    with pytest.raises(ValueError, match="both delivery and preparation"):
        asyncio.run(
            factory.start(
                instance_id="forward-1",
                checkpoint_fingerprint=content_digest("checkpoint"),
                delivery=object(),  # type: ignore[arg-type]
            )
        )


def test_forward_process_launch_context_rejects_rebound_payload() -> None:
    delivery = _delivery_input()
    preparation = _portfolio_preparation(delivery)
    _validate_forward_launch_context(
        delivery.delivery_binding.instance_id,
        delivery.delivery_binding.pre_event_checkpoint_fingerprint,
        delivery=delivery,
        preparation=preparation,
    )

    rebound = ForwardPortfolioContextPreparation(
        instance_id=preparation.instance_id,
        payload_fingerprint=content_digest("different-payload"),
        delivery_binding_fingerprint=preparation.delivery_binding_fingerprint,
        dispatch_fingerprint=preparation.dispatch_fingerprint,
        pre_event_checkpoint_fingerprint=preparation.pre_event_checkpoint_fingerprint,
        warmup_receipt_fingerprint=preparation.warmup_receipt_fingerprint,
        component_preparations={},
    )
    with pytest.raises(ValueError, match="payload_fingerprint differs"):
        _validate_forward_launch_context(
            delivery.delivery_binding.instance_id,
            delivery.delivery_binding.pre_event_checkpoint_fingerprint,
            delivery=delivery,
            preparation=rebound,
        )


def test_forward_process_factory_rejects_stale_durable_checkpoint_before_launch(
    tmp_path: Path,
) -> None:
    requested_checkpoint = content_digest("new durable checkpoint")
    stale_plan = _plan(tmp_path, checkpoint_fingerprint=content_digest("old checkpoint"))
    requested: list[tuple[str, str]] = []

    def build_plan(instance_id: str, checkpoint: str):
        requested.append((instance_id, checkpoint))
        return stale_plan

    factory = HardenedNautilusForwardSessionProcessFactory(
        build_plan,
        docker_binary=str(tmp_path / "must-not-launch"),
    )

    with pytest.raises(ValueError, match="requested durable checkpoint"):
        asyncio.run(
            factory.start(
                instance_id="forward-1",
                checkpoint_fingerprint=requested_checkpoint,
            )
        )
    assert requested == [("forward-1", requested_checkpoint)]


def test_forward_process_factory_rejects_bootstrap_for_another_instance(
    tmp_path: Path,
) -> None:
    checkpoint = content_digest("checkpoint")
    other_instance_plan = _plan(
        tmp_path,
        instance_id="another-forward",
        checkpoint_fingerprint=checkpoint,
    )
    factory = HardenedNautilusForwardSessionProcessFactory(
        lambda _instance_id, _checkpoint: other_instance_plan,
        docker_binary=str(tmp_path / "must-not-launch"),
    )

    with pytest.raises(ValueError, match="another instance"):
        asyncio.run(factory.start(instance_id="forward-1", checkpoint_fingerprint=checkpoint))


def test_forward_process_factory_rejects_symlinked_bootstrap_before_launch(
    tmp_path: Path,
) -> None:
    checkpoint = content_digest("checkpoint")
    plan = _plan(tmp_path, checkpoint_fingerprint=checkpoint)
    bootstrap_path = tmp_path / "forward-session-bootstrap.json"
    payload_path = tmp_path / "durable-bootstrap.json"
    bootstrap_path.replace(payload_path)
    bootstrap_path.symlink_to(payload_path)
    factory = HardenedNautilusForwardSessionProcessFactory(
        lambda _instance_id, _checkpoint: plan,
        docker_binary=str(tmp_path / "must-not-launch"),
    )

    with pytest.raises(ValueError, match="could not be read"):
        asyncio.run(factory.start(instance_id="forward-1", checkpoint_fingerprint=checkpoint))


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
