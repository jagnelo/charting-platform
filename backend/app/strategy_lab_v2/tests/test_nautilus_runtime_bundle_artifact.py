from __future__ import annotations

import hashlib
from dataclasses import replace
from io import BytesIO

import pytest

from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import ArtifactManifest, ArtifactRetention
from app.strategy_lab_v2.nautilus_runtime_bundle import (
    NautilusInvocationResultStreamReference,
    load_materialized_nautilus_runtime_bundle,
    materialize_nautilus_runtime_bundle,
    verify_nautilus_context_stream_artifact_file,
    verify_nautilus_invocation_result_stream_file,
    verify_nautilus_runtime_artifact_file,
)
from app.strategy_lab_v2.nautilus_runtime_protocol import (
    NAUTILUS_INVOCATION_RESULT_STREAM_MEDIA_TYPE,
    NAUTILUS_INVOCATION_RESULT_STREAM_SCHEMA,
)
from app.strategy_lab_v2.tests.test_nautilus_runtime_cli import _runtime_bundle
from strategy_runtime import (
    InvocationResultStreamWriter,
    InvocationStatus,
    StrategyInvocationResult,
)


def test_runtime_bundle_is_published_and_reloaded_by_raw_and_semantic_identity(tmp_path) -> None:
    bundle = _runtime_bundle()
    store = LocalArtifactStore(tmp_path / "artifacts")

    reference = materialize_nautilus_runtime_bundle(bundle, store)
    replay = materialize_nautilus_runtime_bundle(bundle, store)

    assert replay == reference
    assert reference.input_bundle_digest == bundle.input_bundle_digest
    assert reference.artifact.content_digest == artifact_content_digest(bundle.wire_bytes)
    assert reference.artifact.byte_length == len(bundle.wire_bytes)
    assert store.path_for(reference.artifact.storage_key).read_bytes() == bundle.wire_bytes
    assert (
        load_materialized_nautilus_runtime_bundle(
            reference,
            store,
            max_input_bytes=len(bundle.wire_bytes),
        )
        == bundle
    )


def test_runtime_bundle_load_rejects_semantic_digest_and_size_drift(tmp_path) -> None:
    bundle = _runtime_bundle()
    store = LocalArtifactStore(tmp_path / "artifacts")
    reference = materialize_nautilus_runtime_bundle(bundle, store)

    with pytest.raises(ValueError, match="semantic digest differs"):
        load_materialized_nautilus_runtime_bundle(
            replace(reference, input_bundle_digest=artifact_content_digest(b"other")),
            store,
            max_input_bytes=len(bundle.wire_bytes),
        )
    with pytest.raises(ValueError, match="configured bound"):
        load_materialized_nautilus_runtime_bundle(
            reference,
            store,
            max_input_bytes=len(bundle.wire_bytes) - 1,
        )


def test_worker_mount_verification_rejects_changed_artifact_bytes(tmp_path) -> None:
    bundle = _runtime_bundle()
    store = LocalArtifactStore(tmp_path / "artifacts")
    reference = materialize_nautilus_runtime_bundle(bundle, store)
    mounted_file = tmp_path / "mounted-input.json"
    mounted_file.write_bytes(b"x" * len(bundle.wire_bytes))

    with pytest.raises(ValueError, match="digest differs"):
        verify_nautilus_runtime_artifact_file(
            reference,
            mounted_file,
            max_input_bytes=len(bundle.wire_bytes),
        )


def test_context_sidecar_is_content_addressed_and_verified_with_its_bundle(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    bundle = _runtime_bundle(context_stream_store=store)
    assert bundle.context_stream is not None

    reference = materialize_nautilus_runtime_bundle(bundle, store)
    reloaded = load_materialized_nautilus_runtime_bundle(
        reference,
        store,
        max_input_bytes=len(bundle.wire_bytes),
    )
    mounted_path = store.path_for(bundle.context_stream.artifact.storage_key)

    assert reloaded == bundle
    assert reference.context_stream == bundle.context_stream
    verify_nautilus_context_stream_artifact_file(
        bundle.context_stream,
        mounted_path,
        max_input_bytes=bundle.context_stream.artifact.byte_length,
    )
    mounted_path.chmod(0o644)
    mounted_path.write_bytes(b"drifted")
    with pytest.raises(ValueError, match="byte length differs|digest differs"):
        verify_nautilus_context_stream_artifact_file(
            bundle.context_stream,
            mounted_path,
            max_input_bytes=bundle.context_stream.artifact.byte_length,
        )


def test_invocation_result_stream_requires_valid_digest_trailer_and_status(tmp_path) -> None:
    result = StrategyInvocationResult(
        content_digest("source"),
        content_digest("manifest"),
        content_digest("context"),
        "strategy.main:Strategy",
        InvocationStatus.SUCCEEDED,
    )
    output = BytesIO()
    writer = InvocationResultStreamWriter(output)
    writer.write(result)
    summary = writer.finish()
    payload = output.getvalue()
    path = tmp_path / "invocations.ndjson"
    path.write_bytes(payload)
    digest = f"sha256:{hashlib.sha256(payload).hexdigest()}"
    manifest = ArtifactManifest(
        digest,
        len(payload),
        NAUTILUS_INVOCATION_RESULT_STREAM_MEDIA_TYPE,
        NAUTILUS_INVOCATION_RESULT_STREAM_SCHEMA,
        digest,
        ArtifactRetention.PINNED_RESULT,
    )
    reference = NautilusInvocationResultStreamReference(
        manifest,
        summary.result_count,
        summary.all_succeeded,
    )

    verify_nautilus_invocation_result_stream_file(
        reference,
        path,
        max_result_bytes=len(payload),
    )
    path.write_bytes(b"x" * len(payload))
    with pytest.raises(ValueError, match="digest differs"):
        verify_nautilus_invocation_result_stream_file(
            reference,
            path,
            max_result_bytes=len(payload),
        )
