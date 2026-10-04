"""Authenticated worker bundle for one isolated Nautilus invocation.

The host serializes an already-frozen engine input and the engine-neutral SDK
invocation batch into a read-only worker mount. The bundle digest is the
``StrategyRuntimeRequest.input_bundle_digest`` consumed by the normal sandbox
environment contract. This wire format is a bounded compatibility handoff;
large historical catalog streaming remains a separate data-plane concern.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, BinaryIO, cast

from app.strategy_lab_v2.artifact_store import (
    ArtifactStoreDecision,
    LocalArtifactStore,
)
from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import ArtifactManifest, ArtifactRetention
from app.strategy_lab_v2.nautilus_engine_input import (
    NautilusEngineInput,
    component_strategy_binding_to_wire,
)
from app.strategy_lab_v2.nautilus_event_adapter import NautilusEventRecord
from app.strategy_lab_v2.nautilus_native_event_stream import (
    MAX_NAUTILUS_NATIVE_EVENT_STREAM_BYTES,
    NautilusNativeEventStreamSummary,
    serialize_nautilus_native_event_stream,
)
from app.strategy_lab_v2.nautilus_portfolio_wire import portfolio_composition_to_wire
from app.strategy_lab_v2.nautilus_runtime_protocol import (
    NAUTILUS_CONTEXT_STREAM_MEDIA_TYPE,
    NAUTILUS_CONTEXT_STREAM_SCHEMA,
    NAUTILUS_INVOCATION_RESULT_STREAM_MEDIA_TYPE,
    NAUTILUS_INVOCATION_RESULT_STREAM_SCHEMA,
    NAUTILUS_NATIVE_EVENT_STREAM_MEDIA_TYPE,
    NAUTILUS_NATIVE_EVENT_STREAM_SCHEMA,
    NAUTILUS_RUNTIME_BUNDLE_SCHEMA,
    NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V1,
    NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V3,
)
from app.strategy_lab_v2.sdk import StrategyContext, StrategySdkManifest
from strategy_runtime import (
    MAX_INVOCATION_CONTEXT_STREAM_BYTES,
    InvocationStatus,
    deserialize_invocation_batch,
    deserialize_invocation_result_stream,
    serialize_invocation_context_stream,
)

NAUTILUS_RUNTIME_ARTIFACT_MEDIA_TYPE = "application/vnd.charting.strategy-lab.nautilus+json"
NAUTILUS_RUNTIME_ARTIFACT_SCHEMA = "strategy-lab.nautilus-runtime-bundle.v1"


class NautilusRuntimeBundleError(ValueError):
    """Malformed or inconsistent local Nautilus worker input."""


@dataclass(frozen=True, slots=True)
class NautilusContextStreamArtifactReference:
    """Pinned artifact identity for a bounded engine-neutral invocation stream."""

    artifact: ArtifactManifest
    context_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, ArtifactManifest):
            raise TypeError("artifact must be an ArtifactManifest")
        if self.artifact.media_type != NAUTILUS_CONTEXT_STREAM_MEDIA_TYPE:
            raise ValueError("strategy context stream media type is unsupported")
        if self.artifact.schema_version != NAUTILUS_CONTEXT_STREAM_SCHEMA:
            raise ValueError("strategy context stream schema is unsupported")
        if self.artifact.retention_class is not ArtifactRetention.PINNED_INPUT:
            raise ValueError("strategy context streams must use pinned-input retention")
        if (
            not isinstance(self.context_count, int)
            or isinstance(self.context_count, bool)
            or self.context_count < 1
        ):
            raise ValueError("context_count must be a positive integer")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)

    def to_wire(self) -> dict[str, Any]:
        return {
            "artifact": {
                "content_digest": self.artifact.content_digest,
                "byte_length": self.artifact.byte_length,
                "media_type": self.artifact.media_type,
                "schema_version": self.artifact.schema_version,
                "storage_key": self.artifact.storage_key,
                "retention_class": self.artifact.retention_class.value,
            },
            "context_count": self.context_count,
        }


@dataclass(frozen=True, slots=True)
class NautilusNativeEventStreamArtifactReference:
    """Pinned native-event stream identity bound to its canonical source tape."""

    artifact: ArtifactManifest
    source_tape_fingerprint: str
    adapter_version: str
    event_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, ArtifactManifest):
            raise TypeError("artifact must be an ArtifactManifest")
        if self.artifact.media_type != NAUTILUS_NATIVE_EVENT_STREAM_MEDIA_TYPE:
            raise ValueError("Nautilus native event stream media type is unsupported")
        if self.artifact.schema_version != NAUTILUS_NATIVE_EVENT_STREAM_SCHEMA:
            raise ValueError("Nautilus native event stream schema is unsupported")
        if self.artifact.retention_class is not ArtifactRetention.PINNED_INPUT:
            raise ValueError("Nautilus native event streams must use pinned-input retention")
        require_sha256_digest(self.source_tape_fingerprint, field_name="source_tape_fingerprint")
        if not isinstance(self.adapter_version, str) or not self.adapter_version.strip():
            raise ValueError("adapter_version must not be empty")
        if (
            not isinstance(self.event_count, int)
            or isinstance(self.event_count, bool)
            or self.event_count < 1
        ):
            raise ValueError("event_count must be a positive integer")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)

    def to_wire(self) -> dict[str, Any]:
        return {
            "artifact": {
                "content_digest": self.artifact.content_digest,
                "byte_length": self.artifact.byte_length,
                "media_type": self.artifact.media_type,
                "schema_version": self.artifact.schema_version,
                "storage_key": self.artifact.storage_key,
                "retention_class": self.artifact.retention_class.value,
            },
            "source_tape_fingerprint": self.source_tape_fingerprint,
            "adapter_version": self.adapter_version,
            "event_count": self.event_count,
        }


@dataclass(frozen=True, slots=True)
class NautilusInvocationResultStreamReference:
    """Verified content-addressed result records emitted by one RC worker."""

    artifact: ArtifactManifest
    result_count: int
    all_succeeded: bool

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, ArtifactManifest):
            raise TypeError("artifact must be an ArtifactManifest")
        if self.artifact.media_type != NAUTILUS_INVOCATION_RESULT_STREAM_MEDIA_TYPE:
            raise ValueError("Nautilus invocation result stream media type is unsupported")
        if self.artifact.schema_version != NAUTILUS_INVOCATION_RESULT_STREAM_SCHEMA:
            raise ValueError("Nautilus invocation result stream schema is unsupported")
        if self.artifact.retention_class is not ArtifactRetention.PINNED_RESULT:
            raise ValueError("Nautilus invocation results must use pinned-result retention")
        if (
            not isinstance(self.result_count, int)
            or isinstance(self.result_count, bool)
            or self.result_count < 1
        ):
            raise ValueError("result_count must be a positive integer")
        if not isinstance(self.all_succeeded, bool):
            raise TypeError("all_succeeded must be a boolean")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)

    def to_wire(self) -> dict[str, Any]:
        return {
            "artifact": {
                "content_digest": self.artifact.content_digest,
                "byte_length": self.artifact.byte_length,
                "media_type": self.artifact.media_type,
                "schema_version": self.artifact.schema_version,
                "storage_key": self.artifact.storage_key,
                "retention_class": self.artifact.retention_class.value,
            },
            "result_count": self.result_count,
            "all_succeeded": self.all_succeeded,
        }


def materialize_nautilus_context_stream_artifact(
    store: LocalArtifactStore,
    *,
    source: str,
    manifest: StrategySdkManifest,
    contexts: Iterable[StrategyContext],
    entrypoint: str,
    max_intents_per_event: int = 100,
    max_stream_bytes: int = MAX_INVOCATION_CONTEXT_STREAM_BYTES,
) -> NautilusContextStreamArtifactReference:
    """Serialize and publish SDK contexts directly to a pinned content artifact."""

    if not isinstance(store, LocalArtifactStore):
        raise TypeError("store must be a LocalArtifactStore")
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w+b",
            dir=store.root,
            prefix=".nautilus-context-stream-",
            delete=False,
        ) as stream:
            temporary_path = stream.name
            context_count = serialize_invocation_context_stream(
                cast(BinaryIO, stream),
                source=source,
                manifest=manifest,
                contexts=contexts,
                entrypoint=entrypoint,
                max_intents_per_event=max_intents_per_event,
                max_stream_bytes=max_stream_bytes,
            )
            stream.flush()
            os.fsync(stream.fileno())
            byte_length = os.fstat(stream.fileno()).st_size
            stream.seek(0)
            digest = hashlib.sha256()
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        content_address = f"sha256:{digest.hexdigest()}"
        artifact = ArtifactManifest(
            content_digest=content_address,
            byte_length=byte_length,
            media_type=NAUTILUS_CONTEXT_STREAM_MEDIA_TYPE,
            schema_version=NAUTILUS_CONTEXT_STREAM_SCHEMA,
            storage_key=content_address,
            retention_class=ArtifactRetention.PINNED_INPUT,
        )
        publication = store.publish_file(artifact, temporary_path)
        if publication.decision not in {
            ArtifactStoreDecision.WRITTEN,
            ArtifactStoreDecision.REUSED,
        }:
            raise NautilusRuntimeBundleError(
                "strategy context stream failed content-addressed publication"
            )
        return NautilusContextStreamArtifactReference(artifact, context_count)
    finally:
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass


def materialize_nautilus_native_event_stream_artifact(
    store: LocalArtifactStore,
    *,
    events: Iterable[NautilusEventRecord],
    source_tape_fingerprint: str,
    adapter_version: str,
    event_count: int,
    max_stream_bytes: int = MAX_NAUTILUS_NATIVE_EVENT_STREAM_BYTES,
) -> NautilusNativeEventStreamArtifactReference:
    """Publish canonical-order native event records without retaining the tape."""

    if not isinstance(store, LocalArtifactStore):
        raise TypeError("store must be a LocalArtifactStore")
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w+b",
            dir=store.root,
            prefix=".nautilus-native-events-",
            delete=False,
        ) as stream:
            temporary_path = stream.name
            summary: NautilusNativeEventStreamSummary = serialize_nautilus_native_event_stream(
                cast(BinaryIO, stream),
                events,
                source_tape_fingerprint=source_tape_fingerprint,
                adapter_version=adapter_version,
                expected_event_count=event_count,
                max_stream_bytes=max_stream_bytes,
            )
            stream.flush()
            os.fsync(stream.fileno())
            byte_length = os.fstat(stream.fileno()).st_size
            stream.seek(0)
            digest = hashlib.sha256()
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        content_address = f"sha256:{digest.hexdigest()}"
        if content_address != summary.content_digest or byte_length != summary.byte_length:
            raise NautilusRuntimeBundleError("native event stream receipt differs from its bytes")
        artifact = ArtifactManifest(
            content_digest=content_address,
            byte_length=byte_length,
            media_type=NAUTILUS_NATIVE_EVENT_STREAM_MEDIA_TYPE,
            schema_version=NAUTILUS_NATIVE_EVENT_STREAM_SCHEMA,
            storage_key=content_address,
            retention_class=ArtifactRetention.PINNED_INPUT,
        )
        publication = store.publish_file(artifact, temporary_path)
        if publication.decision not in {
            ArtifactStoreDecision.WRITTEN,
            ArtifactStoreDecision.REUSED,
        }:
            raise NautilusRuntimeBundleError("native event stream publication failed")
        return NautilusNativeEventStreamArtifactReference(
            artifact=artifact,
            source_tape_fingerprint=source_tape_fingerprint,
            adapter_version=adapter_version,
            event_count=event_count,
        )
    finally:
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass


def _wire_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise NautilusRuntimeBundleError("runtime bundle decimals must be finite")
        return str(value)
    if isinstance(value, Enum):
        return _wire_value(value.value)
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise NautilusRuntimeBundleError("runtime bundle mappings require string keys")
        return {key: _wire_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_wire_value(item) for item in value]
    if value is None or isinstance(value, str | bool | int):
        return value
    raise NautilusRuntimeBundleError(
        f"runtime bundle contains unsupported value type {type(value).__name__}"
    )


@dataclass(frozen=True, slots=True)
class NautilusRuntimeBundle:
    """Exact serialized inputs consumed by the isolated RC runtime CLI."""

    attempt_id: str
    input_bundle_digest: str
    wire_bytes: bytes
    context_stream: NautilusContextStreamArtifactReference | None = None
    native_event_stream: NautilusNativeEventStreamArtifactReference | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.attempt_id, str) or not self.attempt_id.strip():
            raise ValueError("attempt_id must not be empty")
        require_sha256_digest(self.input_bundle_digest, field_name="input_bundle_digest")
        if not isinstance(self.wire_bytes, bytes) or not self.wire_bytes:
            raise ValueError("wire_bytes must be non-empty bytes")
        _validate_runtime_bundle_wire_bytes(
            self.wire_bytes,
            attempt_id=self.attempt_id,
            input_bundle_digest=self.input_bundle_digest,
            context_stream=self.context_stream,
            native_event_stream=self.native_event_stream,
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class NautilusTrialInputBinding:
    """Domain lineage bound to the exact worker runtime-input reference."""

    attempt_id: str
    trial_fingerprint: str
    experiment_fingerprint: str
    portfolio_fingerprint: str
    snapshot_fingerprint: str
    strategy_package_fingerprint: str
    engine_input_fingerprint: str
    invocation_input_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.attempt_id, str) or not self.attempt_id.strip():
            raise ValueError("attempt_id must not be empty")
        for name in (
            "trial_fingerprint",
            "experiment_fingerprint",
            "portfolio_fingerprint",
            "snapshot_fingerprint",
            "strategy_package_fingerprint",
            "engine_input_fingerprint",
            "invocation_input_digest",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class NautilusRuntimeInputArtifactReference:
    """Small durable reference to the exact bytes for one runtime invocation.

    ``input_bundle_digest`` authenticates the parsed semantic payload expected
    by the sandbox CLI. The artifact manifest separately addresses the exact
    wire bytes stored in the shared content-addressed artifact volume.
    """

    attempt_id: str
    input_bundle_digest: str
    artifact: ArtifactManifest
    context_stream: NautilusContextStreamArtifactReference | None = None
    native_event_stream: NautilusNativeEventStreamArtifactReference | None = None
    trial_binding: NautilusTrialInputBinding | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.attempt_id, str) or not self.attempt_id.strip():
            raise ValueError("attempt_id must not be empty")
        require_sha256_digest(self.input_bundle_digest, field_name="input_bundle_digest")
        if not isinstance(self.artifact, ArtifactManifest):
            raise TypeError("artifact must be an ArtifactManifest")
        if self.artifact.media_type != NAUTILUS_RUNTIME_ARTIFACT_MEDIA_TYPE:
            raise ValueError("runtime input artifact media type is unsupported")
        if self.artifact.schema_version != NAUTILUS_RUNTIME_ARTIFACT_SCHEMA:
            raise ValueError("runtime input artifact schema is unsupported")
        if self.artifact.retention_class is not ArtifactRetention.PINNED_INPUT:
            raise ValueError("runtime input artifacts must use pinned-input retention")
        if self.context_stream is not None and not isinstance(
            self.context_stream, NautilusContextStreamArtifactReference
        ):
            raise TypeError("context_stream must be a NautilusContextStreamArtifactReference")
        if self.native_event_stream is not None and not isinstance(
            self.native_event_stream, NautilusNativeEventStreamArtifactReference
        ):
            raise TypeError(
                "native_event_stream must be a NautilusNativeEventStreamArtifactReference"
            )
        if self.native_event_stream is not None and self.context_stream is None:
            raise ValueError("native event streaming requires a strategy context stream")
        if self.trial_binding is not None and not isinstance(
            self.trial_binding, NautilusTrialInputBinding
        ):
            raise TypeError("trial_binding must be a NautilusTrialInputBinding")
        if self.trial_binding is not None and self.trial_binding.attempt_id != self.attempt_id:
            raise ValueError("trial input binding must reference the runtime attempt")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def materialize_nautilus_runtime_bundle(
    bundle: NautilusRuntimeBundle,
    store: LocalArtifactStore,
    *,
    trial_binding: NautilusTrialInputBinding | None = None,
) -> NautilusRuntimeInputArtifactReference:
    """Publish bundle bytes immutably and return only their durable identity."""

    if not isinstance(bundle, NautilusRuntimeBundle):
        raise TypeError("bundle must be a NautilusRuntimeBundle")
    if not isinstance(store, LocalArtifactStore):
        raise TypeError("store must be a LocalArtifactStore")
    if trial_binding is not None and not isinstance(trial_binding, NautilusTrialInputBinding):
        raise TypeError("trial_binding must be a NautilusTrialInputBinding")
    if trial_binding is not None and trial_binding.attempt_id != bundle.attempt_id:
        raise ValueError("trial input binding must reference the runtime bundle attempt")
    if bundle.context_stream is not None:
        with store.open_verified(
            bundle.context_stream.artifact.storage_key,
            max_bytes=bundle.context_stream.artifact.byte_length,
        ):
            pass
    if bundle.native_event_stream is not None:
        with store.open_verified(
            bundle.native_event_stream.artifact.storage_key,
            max_bytes=bundle.native_event_stream.artifact.byte_length,
        ):
            pass
    manifest = ArtifactManifest(
        content_digest=artifact_content_digest(bundle.wire_bytes),
        byte_length=len(bundle.wire_bytes),
        media_type=NAUTILUS_RUNTIME_ARTIFACT_MEDIA_TYPE,
        schema_version=NAUTILUS_RUNTIME_ARTIFACT_SCHEMA,
        storage_key=artifact_content_digest(bundle.wire_bytes),
        retention_class=ArtifactRetention.PINNED_INPUT,
    )
    publication = store.publish(manifest, bundle.wire_bytes)
    if publication.decision not in {ArtifactStoreDecision.WRITTEN, ArtifactStoreDecision.REUSED}:
        raise ValueError("Nautilus runtime input artifact failed content-addressed publication")
    return NautilusRuntimeInputArtifactReference(
        attempt_id=bundle.attempt_id,
        input_bundle_digest=bundle.input_bundle_digest,
        artifact=manifest,
        context_stream=bundle.context_stream,
        native_event_stream=bundle.native_event_stream,
        trial_binding=trial_binding,
    )


def load_materialized_nautilus_runtime_bundle(
    reference: NautilusRuntimeInputArtifactReference,
    store: LocalArtifactStore,
    *,
    max_input_bytes: int,
) -> NautilusRuntimeBundle:
    """Load and cross-check a durable bundle reference before worker launch."""

    if not isinstance(reference, NautilusRuntimeInputArtifactReference):
        raise TypeError("reference must be a NautilusRuntimeInputArtifactReference")
    if not isinstance(store, LocalArtifactStore):
        raise TypeError("store must be a LocalArtifactStore")
    if (
        not isinstance(max_input_bytes, int)
        or isinstance(max_input_bytes, bool)
        or max_input_bytes <= 0
    ):
        raise ValueError("max_input_bytes must be a positive integer")
    if reference.artifact.byte_length > max_input_bytes:
        raise ValueError("Nautilus runtime input artifact exceeds its configured bound")
    wire_bytes, _integrity = store.read_manifest(
        reference.artifact,
        max_bytes=max_input_bytes,
    )
    if reference.context_stream is not None:
        with store.open_verified(
            reference.context_stream.artifact.storage_key,
            max_bytes=reference.context_stream.artifact.byte_length,
        ):
            pass
    if reference.native_event_stream is not None:
        with store.open_verified(
            reference.native_event_stream.artifact.storage_key,
            max_bytes=reference.native_event_stream.artifact.byte_length,
        ):
            pass
    return NautilusRuntimeBundle(
        attempt_id=reference.attempt_id,
        input_bundle_digest=reference.input_bundle_digest,
        wire_bytes=wire_bytes,
        context_stream=reference.context_stream,
        native_event_stream=reference.native_event_stream,
    )


def verify_nautilus_runtime_artifact_file(
    reference: NautilusRuntimeInputArtifactReference,
    path: str | os.PathLike[str],
    *,
    max_input_bytes: int,
) -> None:
    """Verify the mounted source file against its durable raw-byte manifest."""

    if not isinstance(reference, NautilusRuntimeInputArtifactReference):
        raise TypeError("reference must be a NautilusRuntimeInputArtifactReference")
    if (
        not isinstance(max_input_bytes, int)
        or isinstance(max_input_bytes, bool)
        or max_input_bytes <= 0
    ):
        raise ValueError("max_input_bytes must be a positive integer")
    manifest = reference.artifact
    if manifest.byte_length > max_input_bytes:
        raise ValueError("Nautilus runtime input artifact exceeds its configured bound")
    descriptor = os.open(
        path,
        os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("Nautilus runtime input artifact must be a regular file")
        if metadata.st_size != manifest.byte_length:
            raise ValueError("Nautilus runtime input artifact byte length differs")
        total = 0
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, min(65_536, max_input_bytes + 1 - total)):
            total += len(chunk)
            if total > max_input_bytes:
                raise ValueError("Nautilus runtime input artifact exceeds its configured bound")
            digest.update(chunk)
    finally:
        os.close(descriptor)
    if f"sha256:{digest.hexdigest()}" != manifest.content_digest:
        raise ValueError("Nautilus runtime input artifact digest differs")


def verify_nautilus_context_stream_artifact_file(
    reference: NautilusContextStreamArtifactReference,
    path: str | os.PathLike[str],
    *,
    max_input_bytes: int,
) -> None:
    """Verify the exact mounted sidecar bytes without buffering the stream."""

    if not isinstance(reference, NautilusContextStreamArtifactReference):
        raise TypeError("reference must be a NautilusContextStreamArtifactReference")
    if (
        not isinstance(max_input_bytes, int)
        or isinstance(max_input_bytes, bool)
        or max_input_bytes <= 0
    ):
        raise ValueError("max_input_bytes must be a positive integer")
    manifest = reference.artifact
    if manifest.byte_length > max_input_bytes:
        raise ValueError("Nautilus context stream exceeds its configured bound")
    descriptor = os.open(
        path,
        os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("Nautilus context stream must be a regular file")
        if metadata.st_size != manifest.byte_length:
            raise ValueError("Nautilus context stream byte length differs")
        total = 0
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, min(65_536, max_input_bytes + 1 - total)):
            total += len(chunk)
            if total > max_input_bytes:
                raise ValueError("Nautilus context stream exceeds its configured bound")
            digest.update(chunk)
    finally:
        os.close(descriptor)
    if f"sha256:{digest.hexdigest()}" != manifest.content_digest:
        raise ValueError("Nautilus context stream digest differs")


def verify_nautilus_native_event_stream_artifact_file(
    reference: NautilusNativeEventStreamArtifactReference,
    path: str | os.PathLike[str],
    *,
    max_input_bytes: int,
) -> None:
    """Verify the exact mounted native-event bytes without buffering the stream."""

    if not isinstance(reference, NautilusNativeEventStreamArtifactReference):
        raise TypeError("reference must be a NautilusNativeEventStreamArtifactReference")
    if (
        not isinstance(max_input_bytes, int)
        or isinstance(max_input_bytes, bool)
        or max_input_bytes <= 0
    ):
        raise ValueError("max_input_bytes must be a positive integer")
    manifest = reference.artifact
    if manifest.byte_length > max_input_bytes:
        raise ValueError("Nautilus native event stream exceeds its configured bound")
    descriptor = os.open(
        path,
        os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("Nautilus native event stream must be a regular file")
        if metadata.st_size != manifest.byte_length:
            raise ValueError("Nautilus native event stream byte length differs")
        total = 0
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, min(65_536, max_input_bytes + 1 - total)):
            total += len(chunk)
            if total > max_input_bytes:
                raise ValueError("Nautilus native event stream exceeds its configured bound")
            digest.update(chunk)
    finally:
        os.close(descriptor)
    if f"sha256:{digest.hexdigest()}" != manifest.content_digest:
        raise ValueError("Nautilus native event stream digest differs")


def verify_nautilus_invocation_result_stream_file(
    reference: NautilusInvocationResultStreamReference,
    path: str | os.PathLike[str],
    *,
    max_result_bytes: int,
) -> None:
    """Verify mounted result bytes, JSONL integrity, count, and invocation status."""

    if not isinstance(reference, NautilusInvocationResultStreamReference):
        raise TypeError("reference must be a NautilusInvocationResultStreamReference")
    if (
        not isinstance(max_result_bytes, int)
        or isinstance(max_result_bytes, bool)
        or max_result_bytes <= 0
    ):
        raise ValueError("max_result_bytes must be a positive integer")
    manifest = reference.artifact
    if manifest.byte_length > max_result_bytes:
        raise ValueError("Nautilus invocation result stream exceeds its configured bound")
    descriptor = os.open(
        path,
        os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("Nautilus invocation result stream must be a regular file")
        if metadata.st_size != manifest.byte_length:
            raise ValueError("Nautilus invocation result stream byte length differs")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            observed = 0
            digest = hashlib.sha256()
            while chunk := stream.read(65_536):
                observed += len(chunk)
                if observed > max_result_bytes:
                    raise ValueError(
                        "Nautilus invocation result stream exceeds its configured bound"
                    )
                digest.update(chunk)
            raw_digest = f"sha256:{digest.hexdigest()}"
            if raw_digest != manifest.content_digest:
                raise ValueError("Nautilus invocation result stream digest differs")

            stream.seek(0)
            decoded_count = 0
            all_succeeded = True
            for result in deserialize_invocation_result_stream(
                stream,
                expected_result_count=reference.result_count,
                max_stream_bytes=max_result_bytes,
            ):
                decoded_count += 1
                all_succeeded = all_succeeded and result.status is InvocationStatus.SUCCEEDED
            if decoded_count != reference.result_count:
                raise ValueError("Nautilus invocation result stream count differs")
            if all_succeeded != reference.all_succeeded:
                raise ValueError("Nautilus invocation result stream status differs")

            stream.seek(0)
            verification_digest = hashlib.sha256()
            verification_length = 0
            while chunk := stream.read(65_536):
                verification_length += len(chunk)
                verification_digest.update(chunk)
            if (
                verification_length != observed
                or f"sha256:{verification_digest.hexdigest()}" != raw_digest
            ):
                raise ValueError("Nautilus invocation result stream changed during verification")
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("runtime bundle contains duplicate object fields")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError("runtime bundle contains a non-finite JSON number")


def _validate_runtime_bundle_wire_bytes(
    wire_bytes: bytes,
    *,
    attempt_id: str,
    input_bundle_digest: str,
    context_stream: NautilusContextStreamArtifactReference | None,
    native_event_stream: NautilusNativeEventStreamArtifactReference | None,
) -> None:
    try:
        payload = json.loads(
            wire_bytes,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("Nautilus runtime input artifact is malformed") from error
    if not isinstance(payload, Mapping):
        raise ValueError("Nautilus runtime input artifact fields are invalid")
    schema = payload.get("schema")
    if schema == NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V1:
        if (
            context_stream is not None
            or native_event_stream is not None
            or set(payload)
            != {
                "schema",
                "engine_input",
                "serialized_strategy_invocation_batch",
            }
        ):
            raise ValueError("legacy Nautilus runtime input artifact fields are invalid")
        if not isinstance(payload["serialized_strategy_invocation_batch"], str):
            raise ValueError("Nautilus runtime input artifact strategy batch is invalid")
    elif schema == NAUTILUS_RUNTIME_BUNDLE_SCHEMA:
        if (
            context_stream is None
            or native_event_stream is not None
            or set(payload)
            != {
                "schema",
                "engine_input",
                "strategy_context_stream",
            }
        ):
            raise ValueError("streaming Nautilus runtime input artifact fields are invalid")
        if payload["strategy_context_stream"] != context_stream.to_wire():
            raise ValueError("Nautilus context stream reference differs from the bundle")
    elif schema == NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V3:
        if (
            context_stream is None
            or native_event_stream is None
            or set(payload)
            != {
                "schema",
                "engine_input",
                "strategy_context_stream",
                "native_event_stream",
            }
        ):
            raise ValueError("native streaming Nautilus runtime bundle fields are invalid")
        if payload["strategy_context_stream"] != context_stream.to_wire():
            raise ValueError("Nautilus context stream reference differs from the bundle")
        if payload["native_event_stream"] != native_event_stream.to_wire():
            raise ValueError("Nautilus native event stream reference differs from the bundle")
        engine_input = payload["engine_input"]
        event_tape = engine_input.get("event_tape") if isinstance(engine_input, Mapping) else None
        if not isinstance(event_tape, Mapping) or set(event_tape) != {
            "source_tape_fingerprint",
            "adapter_version",
            "event_count",
        }:
            raise ValueError("streaming engine input must not inline native event records")
        if (
            event_tape["source_tape_fingerprint"] != native_event_stream.source_tape_fingerprint
            or event_tape["adapter_version"] != native_event_stream.adapter_version
            or not isinstance(event_tape["event_count"], int)
            or isinstance(event_tape["event_count"], bool)
            or event_tape["event_count"] != native_event_stream.event_count
        ):
            raise ValueError("native event stream identity differs from the engine input")
    else:
        raise ValueError("Nautilus runtime input artifact schema is unsupported")
    engine_input = payload["engine_input"]
    if not isinstance(engine_input, Mapping) or engine_input.get("attempt_id") != attempt_id:
        raise ValueError("Nautilus runtime input artifact attempt identity differs")
    if content_digest(payload) != input_bundle_digest:
        raise ValueError("Nautilus runtime input artifact semantic digest differs")


def build_nautilus_runtime_bundle(
    engine_input: NautilusEngineInput,
    serialized_strategy_invocation_batch: str | None = None,
    *,
    context_stream: NautilusContextStreamArtifactReference | None = None,
    native_event_stream: NautilusNativeEventStreamArtifactReference | None = None,
) -> NautilusRuntimeBundle:
    """Serialize frozen engine inputs with exactly one batch or stream reference."""

    if not isinstance(engine_input, NautilusEngineInput):
        raise TypeError("engine_input must be a NautilusEngineInput")
    if (serialized_strategy_invocation_batch is None) == (context_stream is None):
        raise TypeError("provide exactly one strategy invocation batch or context stream")
    if context_stream is not None:
        if not isinstance(context_stream, NautilusContextStreamArtifactReference):
            raise TypeError("context_stream must be a NautilusContextStreamArtifactReference")
    else:
        if not isinstance(serialized_strategy_invocation_batch, str):
            raise TypeError("serialized_strategy_invocation_batch must be a string")
        try:
            source, manifest, contexts, entrypoint, _max_intents = deserialize_invocation_batch(
                serialized_strategy_invocation_batch
            )
        except (TypeError, ValueError) as error:
            raise NautilusRuntimeBundleError("strategy invocation batch is malformed") from error
        if content_digest(source) != engine_input.strategy_source_digest:
            raise NautilusRuntimeBundleError(
                "strategy batch source digest differs from engine input"
            )
        if manifest.fingerprint != engine_input.strategy_manifest_fingerprint:
            raise NautilusRuntimeBundleError("strategy batch manifest differs from engine input")
        if entrypoint != engine_input.entrypoint:
            raise NautilusRuntimeBundleError("strategy batch entrypoint differs from engine input")
        if any(context.parameters != engine_input.parameters for context in contexts):
            raise NautilusRuntimeBundleError("strategy batch parameters differ from engine input")
        if any(context.random_seed != engine_input.random_seed for context in contexts):
            raise NautilusRuntimeBundleError("strategy batch seed differs from engine input")
    if native_event_stream is not None:
        if not isinstance(native_event_stream, NautilusNativeEventStreamArtifactReference):
            raise TypeError(
                "native_event_stream must be a NautilusNativeEventStreamArtifactReference"
            )
        if context_stream is None:
            raise TypeError("native event streaming requires a strategy context stream")
        if (
            native_event_stream.source_tape_fingerprint
            != engine_input.event_tape.source_tape_fingerprint
            or native_event_stream.adapter_version != engine_input.event_tape.adapter_version
        ):
            raise NautilusRuntimeBundleError("native event stream differs from the engine input")

    tape = engine_input.event_tape
    payload: dict[str, Any] = {
        "schema": (
            NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V3
            if native_event_stream is not None
            else (
                NAUTILUS_RUNTIME_BUNDLE_SCHEMA
                if context_stream is not None
                else NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V1
            )
        ),
        "engine_input": {
            "trial_id": engine_input.trial_id,
            "attempt_id": engine_input.attempt_id,
            "data_snapshot_fingerprint": engine_input.data_snapshot_fingerprint,
            "event_tape": {
                "source_tape_fingerprint": tape.source_tape_fingerprint,
                "adapter_version": tape.adapter_version,
                **(
                    {"event_count": native_event_stream.event_count}
                    if native_event_stream is not None
                    else {
                        "events": [
                            {
                                "dependency_id": event.dependency_id,
                                "event_id": event.event_id,
                                "instrument_id": event.instrument_id,
                                "event_type": event.event_type,
                                "event_time_ns": event.event_time_ns,
                                "sequence": event.sequence,
                                "values": _wire_value(event.values),
                            }
                            for event in tape.events
                        ]
                    }
                ),
            },
            "instruments": [
                {
                    "instrument_id": item.instrument_id,
                    "raw_symbol": item.raw_symbol,
                    "venue_id": item.venue_id,
                    "product_class": item.product_class.value,
                    "base_currency": item.base_currency,
                    "quote_currency": item.quote_currency,
                    "price_precision": item.price_precision,
                    "size_precision": item.size_precision,
                    "price_increment": str(item.price_increment),
                    "size_increment": str(item.size_increment),
                    "multiplier": str(item.multiplier),
                    "min_quantity": (None if item.min_quantity is None else str(item.min_quantity)),
                    "max_quantity": (None if item.max_quantity is None else str(item.max_quantity)),
                    "activation_ns": item.activation_ns,
                    "expiration_ns": item.expiration_ns,
                    "bar_type": item.bar_type,
                }
                for item in engine_input.instruments
            ],
            "venue": {
                "venue_id": engine_input.venue.venue_id,
                "oms_type": engine_input.venue.oms_type,
                "account_type": engine_input.venue.account_type,
                "base_currency": engine_input.venue.base_currency,
                "cash": [
                    {"currency": item.currency, "amount": str(item.amount)}
                    for item in engine_input.venue.cash
                ],
            },
            "portfolio": portfolio_composition_to_wire(engine_input.portfolio),
            "strategy_source_digest": engine_input.strategy_source_digest,
            "strategy_manifest_fingerprint": engine_input.strategy_manifest_fingerprint,
            "entrypoint": engine_input.entrypoint,
            "parameters": _wire_value(engine_input.parameters),
            "random_seed": engine_input.random_seed,
            "strategy_bindings": [
                component_strategy_binding_to_wire(binding)
                for binding in engine_input.strategy_bindings
            ],
            "input_version": engine_input.input_version,
        },
    }
    if context_stream is not None:
        payload["strategy_context_stream"] = context_stream.to_wire()
    else:
        payload["serialized_strategy_invocation_batch"] = serialized_strategy_invocation_batch
    if native_event_stream is not None:
        payload["native_event_stream"] = native_event_stream.to_wire()
    wire = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return NautilusRuntimeBundle(
        attempt_id=engine_input.attempt_id,
        input_bundle_digest=content_digest(payload),
        wire_bytes=wire,
        context_stream=context_stream,
        native_event_stream=native_event_stream,
    )


__all__ = [
    "NAUTILUS_RUNTIME_ARTIFACT_MEDIA_TYPE",
    "NAUTILUS_RUNTIME_ARTIFACT_SCHEMA",
    "NAUTILUS_RUNTIME_BUNDLE_SCHEMA",
    "NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V3",
    "NautilusContextStreamArtifactReference",
    "NautilusInvocationResultStreamReference",
    "NautilusNativeEventStreamArtifactReference",
    "NautilusRuntimeBundle",
    "NautilusRuntimeBundleError",
    "NautilusRuntimeInputArtifactReference",
    "NautilusTrialInputBinding",
    "build_nautilus_runtime_bundle",
    "load_materialized_nautilus_runtime_bundle",
    "materialize_nautilus_context_stream_artifact",
    "materialize_nautilus_native_event_stream_artifact",
    "materialize_nautilus_runtime_bundle",
    "verify_nautilus_context_stream_artifact_file",
    "verify_nautilus_invocation_result_stream_file",
    "verify_nautilus_native_event_stream_artifact_file",
    "verify_nautilus_runtime_artifact_file",
]
