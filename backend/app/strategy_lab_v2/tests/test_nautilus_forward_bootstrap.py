from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.strategy_lab_v2 import nautilus_runtime_cli
from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    ArtifactManifest,
    ArtifactRetention,
    CarryInMode,
    ForwardInstance,
    ForwardState,
)
from app.strategy_lab_v2.event_tape import bind_event_tape
from app.strategy_lab_v2.event_tape_artifacts import FrozenEventTapeArtifactResolution
from app.strategy_lab_v2.forward_execution_plan import (
    ForwardComponentExecutionPlan,
    ForwardExecutionPlan,
)
from app.strategy_lab_v2.forward_execution_plan_resolution import (
    ResolvedForwardExecutionComponent,
    ResolvedForwardExecutionPlan,
)
from app.strategy_lab_v2.forward_processed_prefix import ForwardProcessedEventPrefix
from app.strategy_lab_v2.forward_warmup import ForwardWarmupReceipt
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.nautilus_engine_input import (
    NautilusComponentStrategyBinding,
    NautilusEngineInput,
)
from app.strategy_lab_v2.nautilus_event_adapter import materialize_nautilus_event_tape
from app.strategy_lab_v2.nautilus_forward_bootstrap import (
    NAUTILUS_FORWARD_BOOTSTRAP_SCHEMA,
    NautilusForwardBootstrapComponent,
    NautilusForwardBootstrapEvent,
    NautilusForwardRuntimeBootstrap,
)
from app.strategy_lab_v2.nautilus_forward_delivery import VerifiedForwardMarketPayload
from app.strategy_lab_v2.nautilus_runtime_bundle import (
    materialize_nautilus_native_event_stream_artifact,
)
from app.strategy_lab_v2.nautilus_runtime_protocol import (
    NAUTILUS_CONTEXT_STREAM_MEDIA_TYPE,
    NAUTILUS_CONTEXT_STREAM_SCHEMA,
)
from app.strategy_lab_v2.sdk import MarketEvent
from app.strategy_lab_v2.strategy_package_resolution import (
    STRATEGY_SOURCE_ARCHIVE_MEDIA_TYPE,
    STRATEGY_SOURCE_ARCHIVE_SCHEMA,
    ResolvedStrategyPackage,
)
from app.strategy_lab_v2.strategy_validation import validate_strategy_source
from app.strategy_lab_v2.tests.test_nautilus_trial_assembly import _inputs as _engine_inputs

NOW = datetime(2026, 10, 5, 14, 30, tzinfo=UTC)


def _digest(value: str) -> str:
    return content_digest(value)


def _component(component_id: str = "momentum") -> NautilusForwardBootstrapComponent:
    return NautilusForwardBootstrapComponent(
        component_id=component_id,
        execution_binding_fingerprint=_digest("execution-binding"),
        resolved_component_fingerprint=_digest("resolved-component"),
        strategy_fingerprint=_digest("strategy"),
        package_fingerprint=_digest("package"),
        package_archive_digest=_digest("archive"),
        dependency_lock_digest=_digest("lock-bytes"),
        manifest_fingerprint=_digest("manifest"),
        source_digest=_digest("source"),
        parameters_digest=_digest("parameters"),
        random_seed=17,
    )


def _bootstrap() -> NautilusForwardRuntimeBootstrap:
    source_digest = _digest("verified-source")
    canonical = CanonicalForwardEvent(
        "live-9",
        9,
        NOW,
        NOW + timedelta(seconds=1),
        source_digest,
    )
    market = MarketEvent(
        "daily-bars",
        canonical.event_id,
        "US.AAPL",
        canonical.event_time,
        canonical.sequence,
        {
            "close": Decimal("101.25"),
            "labels": ("verified", "processed"),
            "observed_at": NOW,
        },
    )
    return NautilusForwardRuntimeBootstrap(
        instance_id="forward-1",
        execution_plan_fingerprint=_digest("plan"),
        portfolio_fingerprint=_digest("portfolio"),
        snapshot_fingerprint=_digest("snapshot"),
        warmup_receipt_fingerprint=_digest("warmup-receipt"),
        warmup_result_fingerprint=_digest("warmup-result"),
        warmup_tape_fingerprint=_digest("warmup-tape"),
        warmup_event_count=8,
        warmup_source_artifact_digests=(_digest("series-a"), _digest("series-b")),
        warmup_cursor_event_id="warmup-8",
        warmup_cursor_sequence=8,
        warmup_cursor_event_fingerprint=_digest("warmup-canonical-event"),
        processed_checkpoint_fingerprint=_digest("checkpoint"),
        processed_prefix_fingerprint=_digest("processed-prefix"),
        before_event_fingerprint=_digest("before-event"),
        engine_input_fingerprint=_digest("engine-input"),
        runtime_input_bundle_digest=_digest("runtime-bundle"),
        native_event_stream_digest=_digest("native-event-stream"),
        native_event_stream_adapter_version="adapter-v1",
        components=(_component(),),
        processed_events=(NautilusForwardBootstrapEvent(canonical, market, source_digest),),
    )


def _context_stream_reference(encoded: bytes) -> dict[str, object]:
    digest = artifact_content_digest(encoded)
    return {
        "artifact": {
            "content_digest": digest,
            "byte_length": len(encoded),
            "media_type": NAUTILUS_CONTEXT_STREAM_MEDIA_TYPE,
            "schema_version": NAUTILUS_CONTEXT_STREAM_SCHEMA,
            "storage_key": digest,
            "retention_class": "pinned_input",
        },
        "context_count": 1,
    }


def test_forward_bootstrap_roundtrips_immutable_replay_bindings() -> None:
    bootstrap = _bootstrap()

    decoded = NautilusForwardRuntimeBootstrap.from_wire(json.loads(bootstrap.to_json_bytes()))

    assert decoded == bootstrap
    assert decoded.fingerprint == bootstrap.fingerprint
    assert decoded.to_wire()["schema"] == NAUTILUS_FORWARD_BOOTSTRAP_SCHEMA
    assert decoded.processed_events[0].market_event.values["close"] == Decimal("101.25")
    assert decoded.processed_events[0].market_event.values["labels"] == (
        "verified",
        "processed",
    )


def test_forward_bootstrap_json_is_bounded_canonical_and_fingerprint_bound() -> None:
    bootstrap = _bootstrap()
    encoded = bootstrap.to_json_bytes()

    assert (
        NautilusForwardRuntimeBootstrap.from_json_bytes(
            encoded,
            expected_fingerprint=bootstrap.fingerprint,
        )
        == bootstrap
    )
    with pytest.raises(ValueError, match="differs from its artifact binding"):
        NautilusForwardRuntimeBootstrap.from_json_bytes(
            encoded,
            expected_fingerprint=_digest("different-bootstrap"),
        )
    with pytest.raises(ValueError, match="duplicate fields"):
        NautilusForwardRuntimeBootstrap.from_json_bytes(b'{"schema":"one","schema":"two"}')
    with pytest.raises(ValueError, match="canonically encoded"):
        NautilusForwardRuntimeBootstrap.from_json_bytes(b" " + encoded)


def test_runtime_cli_verifies_forward_bootstrap_and_native_artifact_bindings(
    tmp_path, monkeypatch
) -> None:
    native_bytes = b"native-history-artifact"
    native_digest = f"sha256:{hashlib.sha256(native_bytes).hexdigest()}"
    context_bytes = b"authenticated strategy context stream"
    context_reference = _context_stream_reference(context_bytes)
    context_digest = context_reference["artifact"]["content_digest"]
    bundle_digest = _digest("runtime-bundle")
    engine_input = {
        "data_snapshot_fingerprint": _bootstrap().snapshot_fingerprint,
        "event_tape": {"bound": True},
    }
    bootstrap = replace(
        _bootstrap(),
        engine_input_fingerprint=content_digest(engine_input),
        runtime_input_bundle_digest=bundle_digest,
        native_event_stream_digest=native_digest,
    )
    bootstrap_path = tmp_path / "bootstrap.json"
    bootstrap_path.write_bytes(bootstrap.to_json_bytes())
    context_path = tmp_path / "strategy-contexts.ndjson"
    context_path.write_bytes(context_bytes)
    native_path = tmp_path / "native-events.parquet"
    native_path.write_bytes(native_bytes)
    monkeypatch.setenv("STRATEGY_FORWARD_BOOTSTRAP_DIGEST", bootstrap.fingerprint)
    monkeypatch.setenv("STRATEGY_INPUT_BUNDLE_DIGEST", bundle_digest)
    monkeypatch.setenv("STRATEGY_CONTEXT_STREAM_DIGEST", context_digest)
    monkeypatch.setenv("STRATEGY_NATIVE_EVENT_STREAM_DIGEST", native_digest)
    monkeypatch.setattr(nautilus_runtime_cli, "runtime_package_version", lambda: "2.0.0rc5")
    runtime_bundle = {"engine_input": engine_input, "strategy_context_stream": context_reference}
    monkeypatch.setattr(
        nautilus_runtime_cli, "_read_bundle", lambda *_args, **_kwargs: runtime_bundle
    )
    monkeypatch.setattr(
        nautilus_runtime_cli,
        "_native_event_stream_reference",
        lambda _bundle: (
            native_digest,
            len(native_bytes),
            _digest("warmup-tape"),
            bootstrap.native_event_stream_adapter_version,
            8,
        ),
    )

    verified_bootstrap, verified_bundle = nautilus_runtime_cli._verify_forward_startup(
        bootstrap_path=str(bootstrap_path),
        bootstrap_fingerprint=bootstrap.fingerprint,
        input_path="/inputs/bundle",
        context_stream_path=str(context_path),
        native_event_stream_path=str(native_path),
        expected_version="2.0.0rc5",
        expected_instance_id=bootstrap.instance_id,
        expected_snapshot_fingerprint=bootstrap.snapshot_fingerprint,
        max_input_bytes=1024,
    )

    assert verified_bootstrap == bootstrap
    assert verified_bundle is runtime_bundle

    monkeypatch.setattr(nautilus_runtime_cli, "runtime_package_version", lambda: "2.0.0rc6")
    with pytest.raises(ValueError, match="package version differs from the forward runtime plan"):
        nautilus_runtime_cli._verify_forward_startup(
            bootstrap_path=str(bootstrap_path),
            bootstrap_fingerprint=bootstrap.fingerprint,
            input_path="/inputs/bundle",
            context_stream_path=str(context_path),
            native_event_stream_path=str(native_path),
            expected_version="2.0.0rc5",
            expected_instance_id=bootstrap.instance_id,
            expected_snapshot_fingerprint=bootstrap.snapshot_fingerprint,
            max_input_bytes=1024,
        )
    monkeypatch.setattr(nautilus_runtime_cli, "runtime_package_version", lambda: "2.0.0rc5")

    context_path.write_bytes(b"tampered strategy context stream")
    with pytest.raises(ValueError, match="context input differs from its artifact length"):
        nautilus_runtime_cli._verify_forward_startup(
            bootstrap_path=str(bootstrap_path),
            bootstrap_fingerprint=bootstrap.fingerprint,
            input_path="/inputs/bundle",
            context_stream_path=str(context_path),
            native_event_stream_path=str(native_path),
            expected_version="2.0.0rc5",
            expected_instance_id=bootstrap.instance_id,
            expected_snapshot_fingerprint=bootstrap.snapshot_fingerprint,
            max_input_bytes=1024,
        )
    context_path.write_bytes(context_bytes)

    monkeypatch.setattr(
        nautilus_runtime_cli,
        "_read_bundle",
        lambda *_args, **_kwargs: {"engine_input": {**engine_input, "unexpected": "tampered"}},
    )
    with pytest.raises(ValueError, match="engine input differs from its bootstrap binding"):
        nautilus_runtime_cli._verify_forward_startup(
            bootstrap_path=str(bootstrap_path),
            bootstrap_fingerprint=bootstrap.fingerprint,
            input_path="/inputs/bundle",
            context_stream_path=str(context_path),
            native_event_stream_path=str(native_path),
            expected_version="2.0.0rc5",
            expected_instance_id=bootstrap.instance_id,
            expected_snapshot_fingerprint=bootstrap.snapshot_fingerprint,
            max_input_bytes=1024,
        )

    monkeypatch.setattr(
        nautilus_runtime_cli,
        "_read_bundle",
        lambda *_args, **_kwargs: runtime_bundle,
    )
    monkeypatch.setattr(
        nautilus_runtime_cli,
        "_native_event_stream_reference",
        lambda _bundle: (
            native_digest,
            len(native_bytes),
            _digest("different-warmup-tape"),
            bootstrap.native_event_stream_adapter_version,
            8,
        ),
    )
    with pytest.raises(ValueError, match="native event stream differs from its runtime bundle"):
        nautilus_runtime_cli._verify_forward_startup(
            bootstrap_path=str(bootstrap_path),
            bootstrap_fingerprint=bootstrap.fingerprint,
            input_path="/inputs/bundle",
            context_stream_path=str(context_path),
            native_event_stream_path=str(native_path),
            expected_version="2.0.0rc5",
            expected_instance_id=bootstrap.instance_id,
            expected_snapshot_fingerprint=bootstrap.snapshot_fingerprint,
            max_input_bytes=1024,
        )

    monkeypatch.setattr(
        nautilus_runtime_cli,
        "_native_event_stream_reference",
        lambda _bundle: (
            native_digest,
            len(native_bytes),
            bootstrap.warmup_tape_fingerprint,
            bootstrap.native_event_stream_adapter_version,
            bootstrap.warmup_event_count - 1,
        ),
    )
    with pytest.raises(ValueError, match="native event stream differs from its runtime bundle"):
        nautilus_runtime_cli._verify_forward_startup(
            bootstrap_path=str(bootstrap_path),
            bootstrap_fingerprint=bootstrap.fingerprint,
            input_path="/inputs/bundle",
            context_stream_path=str(context_path),
            native_event_stream_path=str(native_path),
            expected_version="2.0.0rc5",
            expected_instance_id=bootstrap.instance_id,
            expected_snapshot_fingerprint=bootstrap.snapshot_fingerprint,
            max_input_bytes=1024,
        )


def test_runtime_cli_rejects_tampered_forward_native_artifact(tmp_path, monkeypatch) -> None:
    native_bytes = b"native-history-artifact"
    native_digest = f"sha256:{hashlib.sha256(native_bytes).hexdigest()}"
    context_bytes = b"authenticated strategy context stream"
    context_reference = _context_stream_reference(context_bytes)
    context_digest = context_reference["artifact"]["content_digest"]
    bundle_digest = _digest("runtime-bundle")
    engine_input = {
        "data_snapshot_fingerprint": _bootstrap().snapshot_fingerprint,
        "event_tape": {"bound": True},
    }
    bootstrap = replace(
        _bootstrap(),
        engine_input_fingerprint=content_digest(engine_input),
        runtime_input_bundle_digest=bundle_digest,
        native_event_stream_digest=native_digest,
    )
    bootstrap_path = tmp_path / "bootstrap.json"
    bootstrap_path.write_bytes(bootstrap.to_json_bytes())
    context_path = tmp_path / "strategy-contexts.ndjson"
    context_path.write_bytes(context_bytes)
    native_path = tmp_path / "native-events.parquet"
    native_path.write_bytes(b"tampered")
    monkeypatch.setenv("STRATEGY_FORWARD_BOOTSTRAP_DIGEST", bootstrap.fingerprint)
    monkeypatch.setenv("STRATEGY_INPUT_BUNDLE_DIGEST", bundle_digest)
    monkeypatch.setenv("STRATEGY_CONTEXT_STREAM_DIGEST", context_digest)
    monkeypatch.setenv("STRATEGY_NATIVE_EVENT_STREAM_DIGEST", native_digest)
    monkeypatch.setattr(nautilus_runtime_cli, "runtime_package_version", lambda: "2.0.0rc5")
    monkeypatch.setattr(
        nautilus_runtime_cli,
        "_read_bundle",
        lambda *_args, **_kwargs: {
            "engine_input": engine_input,
            "strategy_context_stream": context_reference,
        },
    )
    monkeypatch.setattr(
        nautilus_runtime_cli,
        "_native_event_stream_reference",
        lambda _bundle: (
            native_digest,
            len(native_bytes),
            _digest("warmup-tape"),
            bootstrap.native_event_stream_adapter_version,
            8,
        ),
    )

    with pytest.raises(ValueError, match="artifact length"):
        nautilus_runtime_cli._verify_forward_startup(
            bootstrap_path=str(bootstrap_path),
            bootstrap_fingerprint=bootstrap.fingerprint,
            input_path="/inputs/bundle",
            context_stream_path=str(context_path),
            native_event_stream_path=str(native_path),
            expected_version="2.0.0rc5",
            expected_instance_id=bootstrap.instance_id,
            expected_snapshot_fingerprint=bootstrap.snapshot_fingerprint,
            max_input_bytes=1024,
        )


def test_forward_bootstrap_rejects_extensions_and_reordered_components() -> None:
    wire = _bootstrap().to_wire()
    with pytest.raises(ValueError, match="fields are invalid"):
        NautilusForwardRuntimeBootstrap.from_wire({**wire, "unexpected": True})

    with pytest.raises(ValueError, match="unique sorted"):
        replace(
            _bootstrap(),
            components=(_component("zeta"), _component("alpha")),
        )


def test_forward_bootstrap_rejects_events_before_the_warmup_cursor() -> None:
    bootstrap = _bootstrap()
    with pytest.raises(ValueError, match="follow the warm-up cursor"):
        replace(bootstrap, warmup_cursor_sequence=10)


def test_forward_bootstrap_event_rejects_source_and_correction_mismatch() -> None:
    source_digest = _digest("verified-source")
    canonical = CanonicalForwardEvent(
        "correction-1",
        11,
        NOW,
        NOW,
        source_digest,
        correction_of="live-10",
    )
    market = MarketEvent("daily-bars", "correction-1", "US.AAPL", NOW, 11, {"close": 10})

    with pytest.raises(ValueError, match="correction events"):
        NautilusForwardBootstrapEvent(canonical, market, source_digest)


def test_build_binds_owner_plan_warmup_snapshot_prefix_and_native_inputs(tmp_path) -> None:
    fixture = _engine_inputs()
    snapshot = fixture["snapshot"]
    portfolio = fixture["portfolio"]
    strategy = fixture["strategy_manifest"].strategy
    package = fixture["strategy_package"]
    manifest = fixture["strategy_manifest"]
    source = fixture["strategy_source"]
    parameters = {"window": 20}
    forward_plan_component = ForwardComponentExecutionPlan(
        "component-1",
        strategy.fingerprint,
        package.fingerprint,
        parameters,
        13,
    )
    execution_plan = ForwardExecutionPlan(
        "forward-1",
        portfolio.fingerprint,
        (forward_plan_component,),
    )
    instance = ForwardInstance(
        "forward-1",
        portfolio.fingerprint,
        snapshot.fingerprint,
        CarryInMode.FLAT,
        ForwardState.WARMING_UP,
        None,
        0,
        0,
        NOW,
        NOW,
    )
    archive_manifest = ArtifactManifest(
        package.archive_digest,
        package.archive_byte_length,
        STRATEGY_SOURCE_ARCHIVE_MEDIA_TYPE,
        STRATEGY_SOURCE_ARCHIVE_SCHEMA,
        package.archive_digest,
        ArtifactRetention.PINNED_INPUT,
    )
    resolved_package = ResolvedStrategyPackage(
        package.fingerprint,
        strategy.fingerprint,
        source,
        manifest,
        b"[]",
        archive_manifest,
        validate_strategy_source(source),
    )
    resolved_component = ResolvedForwardExecutionComponent(
        forward_plan_component,
        strategy,
        package,
        resolved_package,
    )
    resolved_plan = ResolvedForwardExecutionPlan(
        instance,
        portfolio,
        execution_plan,
        {"component-1": resolved_component},
    )

    frozen_tape = fixture["event_tape"]
    snapshot_tape = FrozenEventTapeArtifactResolution(
        snapshot.fingerprint,
        manifest.fingerprint,
        frozen_tape,
        bind_event_tape(frozen_tape, snapshot, manifest),
        tuple(sorted({item.content_digest for item in snapshot.series})),
    )
    native_tape = materialize_nautilus_event_tape(frozen_tape, snapshot, manifest)
    store = LocalArtifactStore(tmp_path / "artifacts")
    native_reference = materialize_nautilus_native_event_stream_artifact(
        store,
        events=native_tape.events,
        source_tape_fingerprint=native_tape.source_tape_fingerprint,
        adapter_version=native_tape.adapter_version,
        event_count=len(native_tape.events),
    )
    native_binding = NautilusComponentStrategyBinding(
        "component-1",
        strategy.fingerprint,
        content_digest(source),
        manifest.fingerprint,
        package.entrypoint,
        content_digest(parameters),
    )
    engine_input = NautilusEngineInput(
        "warmup-trial",
        "warmup-attempt",
        snapshot.fingerprint,
        native_tape,
        fixture["instruments"],
        fixture["venue"],
        portfolio,
        content_digest(source),
        manifest.fingerprint,
        package.entrypoint,
        parameters,
        13,
        strategy_bindings=(native_binding,),
    )
    cursor_event = frozen_tape.events[-1]
    receipt = ForwardWarmupReceipt(
        "forward-1",
        snapshot.fingerprint,
        CarryInMode.FLAT,
        _digest("warmup-result"),
        NOW + timedelta(days=3),
        cursor_event.event_id,
        cursor_event.sequence,
        _digest("warmup-canonical-event"),
    )
    processed_canonical = CanonicalForwardEvent(
        "live-3",
        3,
        NOW + timedelta(days=2),
        NOW + timedelta(days=2, seconds=1),
        _digest("live-source"),
    )
    processed_market = MarketEvent(
        "daily-bars",
        processed_canonical.event_id,
        "AAPL.SIM",
        processed_canonical.event_time,
        processed_canonical.sequence,
        {"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
    )
    processed_prefix = ForwardProcessedEventPrefix(
        "forward-1",
        _digest("pre-event-checkpoint"),
        receipt.fingerprint,
        manifest.fingerprint,
        _digest("before-event"),
        (("daily-bars", 3),),
        (
            VerifiedForwardMarketPayload(
                processed_canonical,
                processed_market,
                processed_canonical.source_digest,
            ),
        ),
    )

    bootstrap = NautilusForwardRuntimeBootstrap.build(
        execution_plan=resolved_plan,
        snapshot=snapshot,
        warmup_receipt=receipt,
        warmup_tape=snapshot_tape,
        processed_prefix=processed_prefix,
        engine_input=engine_input,
        runtime_input_bundle_digest=_digest("runtime-bundle"),
        native_event_stream=native_reference,
    )

    assert bootstrap.instance_id == instance.instance_id
    assert bootstrap.portfolio_fingerprint == portfolio.fingerprint
    assert bootstrap.snapshot_fingerprint == snapshot.fingerprint
    assert bootstrap.warmup_tape_fingerprint == frozen_tape.fingerprint
    assert bootstrap.processed_events[0].canonical_event == processed_canonical
    assert bootstrap.components[0].random_seed == 13
