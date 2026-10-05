"""Hardened CLI for the isolated Nautilus runtime image."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO, Protocol

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.nautilus_calendar_wire import session_calendar_from_wire
from app.strategy_lab_v2.nautilus_native_event_stream import (
    MAX_NAUTILUS_NATIVE_EVENT_STREAM_BYTES,
)
from app.strategy_lab_v2.nautilus_runtime_adapter import (
    run_native_backtest,
    runtime_package_version,
)
from app.strategy_lab_v2.nautilus_runtime_probe import probe_nautilus_runtime
from app.strategy_lab_v2.nautilus_runtime_protocol import (
    NAUTILUS_COMPONENT_CONTEXT_STREAM_MEDIA_TYPE,
    NAUTILUS_COMPONENT_CONTEXT_STREAM_SCHEMA,
    NAUTILUS_CONTEXT_STREAM_MEDIA_TYPE,
    NAUTILUS_CONTEXT_STREAM_SCHEMA,
    NAUTILUS_NATIVE_EVENT_STREAM_MEDIA_TYPE,
    NAUTILUS_NATIVE_EVENT_STREAM_SCHEMA,
    NAUTILUS_RUNTIME_BUNDLE_SCHEMA,
    NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V1,
    NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V3,
    NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V4,
    NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V5,
)

if TYPE_CHECKING:
    from app.strategy_lab_v2.nautilus_forward_bootstrap import NautilusForwardRuntimeBootstrap
    from app.strategy_lab_v2.nautilus_forward_runtime_server import NativeForwardSessionFactory

_LEGACY_BUNDLE_FIELDS = frozenset(
    {"schema", "engine_input", "serialized_strategy_invocation_batch"}
)
_STREAMING_BUNDLE_FIELDS = frozenset({"schema", "engine_input", "strategy_context_stream"})
_NATIVE_STREAMING_BUNDLE_FIELDS = frozenset(
    {"schema", "engine_input", "strategy_context_stream", "native_event_stream"}
)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("runtime bundle contains duplicate object fields")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError("runtime bundle contains a non-finite JSON number")


def _read_bundle(path_value: str, *, max_bytes: int) -> Mapping[str, Any]:
    path = Path(path_value)
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("runtime bundle input must be a regular file")
        if metadata.st_size <= 0 or metadata.st_size > max_bytes:
            raise ValueError("runtime bundle input is empty or exceeds its memory-derived limit")
        chunks: list[bytes] = []
        total = 0
        while chunk := os.read(descriptor, min(65_536, max_bytes + 1 - total)):
            total += len(chunk)
            if total > max_bytes:
                raise ValueError("runtime bundle input exceeds its memory-derived limit")
            chunks.append(chunk)
    finally:
        os.close(descriptor)
    decoded = json.loads(
        b"".join(chunks),
        object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
    )
    if not isinstance(decoded, Mapping):
        raise ValueError("runtime bundle fields are invalid")
    schema = decoded.get("schema")
    if schema == NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V1:
        if set(decoded) != _LEGACY_BUNDLE_FIELDS:
            raise ValueError("legacy runtime bundle fields are invalid")
        if not isinstance(decoded["serialized_strategy_invocation_batch"], str):
            raise ValueError("runtime bundle strategy batch is invalid")
    elif schema == NAUTILUS_RUNTIME_BUNDLE_SCHEMA:
        if set(decoded) != _STREAMING_BUNDLE_FIELDS:
            raise ValueError("streaming runtime bundle fields are invalid")
    elif schema == NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V3:
        if set(decoded) != _NATIVE_STREAMING_BUNDLE_FIELDS:
            raise ValueError("native streaming runtime bundle fields are invalid")
        _native_event_stream_reference(decoded)
    elif schema == NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V4:
        if set(decoded) != _NATIVE_STREAMING_BUNDLE_FIELDS:
            raise ValueError("component streaming runtime bundle fields are invalid")
        _native_event_stream_reference(decoded)
        _context_stream_reference(decoded)
    elif schema == NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V5:
        expected_fields = {
            "schema",
            "engine_input",
            "strategy_context_stream",
            "session_calendar",
            "session_periods_per_year",
        }
        if "native_event_stream" in decoded:
            expected_fields.add("native_event_stream")
            _native_event_stream_reference(decoded)
        if set(decoded) != expected_fields:
            raise ValueError("session-metric runtime bundle fields are invalid")
        _context_stream_reference(decoded)
        calendar = session_calendar_from_wire(decoded["session_calendar"])
        if calendar is None:
            raise ValueError("session-metric runtime bundle calendar is missing")
        periods = decoded["session_periods_per_year"]
        if not isinstance(periods, int) or isinstance(periods, bool) or periods < 1:
            raise ValueError("session-metric annualization must be a positive integer")
        context_reference = decoded["strategy_context_stream"]
        if isinstance(context_reference, Mapping) and "component_counts" in context_reference:
            if "native_event_stream" not in decoded:
                raise ValueError("component session-metric bundles require native event streaming")
    else:
        raise ValueError("runtime bundle schema is unsupported")
    if not isinstance(decoded["engine_input"], Mapping):
        raise ValueError("runtime bundle engine input is invalid")
    expected_digest = os.environ.get("STRATEGY_INPUT_BUNDLE_DIGEST")
    if expected_digest is None:
        raise ValueError("sandbox input bundle digest is not configured")
    require_sha256_digest(expected_digest, field_name="STRATEGY_INPUT_BUNDLE_DIGEST")
    if content_digest(decoded) != expected_digest:
        raise ValueError("runtime bundle digest differs from the sandbox request")
    expected_attempt = os.environ.get("STRATEGY_ATTEMPT_ID")
    engine_attempt = decoded["engine_input"].get("attempt_id")
    if not isinstance(expected_attempt, str) or engine_attempt != expected_attempt:
        raise ValueError("runtime bundle attempt differs from the sandbox request")
    return decoded


def _verify_forward_startup(
    *,
    bootstrap_path: str,
    bootstrap_fingerprint: str,
    input_path: str,
    context_stream_path: str,
    native_event_stream_path: str,
    expected_version: str,
    expected_instance_id: str,
    expected_snapshot_fingerprint: str,
    max_input_bytes: int,
) -> tuple[NautilusForwardRuntimeBootstrap, Mapping[str, Any]]:
    """Verify all immutable artifacts needed before opening a forward process."""

    from app.strategy_lab_v2.nautilus_forward_bootstrap import (
        MAX_NAUTILUS_FORWARD_BOOTSTRAP_BYTES,
        NautilusForwardRuntimeBootstrap,
    )

    require_sha256_digest(bootstrap_fingerprint, field_name="bootstrap_fingerprint")
    if os.environ.get("STRATEGY_FORWARD_BOOTSTRAP_DIGEST") != bootstrap_fingerprint:
        raise ValueError("forward bootstrap fingerprint differs from the sandbox request")
    descriptor = os.open(
        Path(bootstrap_path),
        os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("forward bootstrap input must be a regular file")
        if metadata.st_size <= 0 or metadata.st_size > MAX_NAUTILUS_FORWARD_BOOTSTRAP_BYTES:
            raise ValueError("forward bootstrap input is empty or exceeds its byte limit")
        encoded = bytearray()
        while chunk := os.read(descriptor, 65_536):
            encoded.extend(chunk)
            if len(encoded) > MAX_NAUTILUS_FORWARD_BOOTSTRAP_BYTES:
                raise ValueError("forward bootstrap input exceeds its byte limit")
    finally:
        os.close(descriptor)
    bootstrap = NautilusForwardRuntimeBootstrap.from_json_bytes(
        bytes(encoded),
        expected_fingerprint=bootstrap_fingerprint,
    )
    if runtime_package_version() != expected_version:
        raise ValueError("Nautilus package version differs from the forward runtime plan")
    if bootstrap.instance_id != expected_instance_id:
        raise ValueError("forward bootstrap belongs to another instance")
    require_sha256_digest(
        expected_snapshot_fingerprint,
        field_name="expected_snapshot_fingerprint",
    )
    if bootstrap.snapshot_fingerprint != expected_snapshot_fingerprint:
        raise ValueError("forward bootstrap snapshot differs from the execution plan")

    bundle = _read_bundle(input_path, max_bytes=max_input_bytes)
    expected_bundle_digest = os.environ.get("STRATEGY_INPUT_BUNDLE_DIGEST")
    if bootstrap.runtime_input_bundle_digest != expected_bundle_digest:
        raise ValueError("forward bootstrap runtime bundle differs from its artifact binding")
    engine_input = bundle["engine_input"]
    if content_digest(engine_input) != bootstrap.engine_input_fingerprint:
        raise ValueError("forward runtime engine input differs from its bootstrap binding")
    if engine_input.get("data_snapshot_fingerprint") != bootstrap.snapshot_fingerprint:
        raise ValueError("forward runtime bundle snapshot differs from its bootstrap")
    context_digest, context_length, _context_count, _component_counts = _context_stream_reference(
        bundle
    )
    if os.environ.get("STRATEGY_CONTEXT_STREAM_DIGEST") != context_digest:
        raise ValueError("forward context stream digest differs from the runtime bundle")
    context_descriptor = os.open(
        Path(context_stream_path),
        os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        context_metadata = os.fstat(context_descriptor)
        if not stat.S_ISREG(context_metadata.st_mode):
            raise ValueError("forward strategy context input must be a regular file")
        if context_metadata.st_size != context_length or context_metadata.st_size > max_input_bytes:
            raise ValueError("forward strategy context input differs from its artifact length")
        context_file_digest = hashlib.sha256()
        context_total = 0
        while chunk := os.read(context_descriptor, 65_536):
            context_total += len(chunk)
            if context_total > max_input_bytes:
                raise ValueError("forward strategy context input exceeds its byte limit")
            context_file_digest.update(chunk)
    finally:
        os.close(context_descriptor)
    if (
        context_total != context_length
        or f"sha256:{context_file_digest.hexdigest()}" != context_digest
    ):
        raise ValueError("forward strategy context input differs from its artifact digest")
    native_digest, native_length, tape_fingerprint, adapter_version, event_count = (
        _native_event_stream_reference(bundle)
    )
    if (
        native_digest != bootstrap.native_event_stream_digest
        or tape_fingerprint != bootstrap.warmup_tape_fingerprint
        or event_count != bootstrap.warmup_event_count
        or adapter_version != bootstrap.native_event_stream_adapter_version
        or os.environ.get("STRATEGY_NATIVE_EVENT_STREAM_DIGEST") != native_digest
    ):
        raise ValueError("forward bootstrap native event stream differs from its runtime bundle")
    native_descriptor = os.open(
        Path(native_event_stream_path),
        os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        metadata = os.fstat(native_descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != native_length:
            raise ValueError("forward native event input differs from its artifact length")
        digest = hashlib.sha256()
        total = 0
        while chunk := os.read(native_descriptor, 65_536):
            digest.update(chunk)
            total += len(chunk)
    finally:
        os.close(native_descriptor)
    if total != native_length or f"sha256:{digest.hexdigest()}" != native_digest:
        raise ValueError("forward native event input differs from its artifact digest")
    return bootstrap, bundle


def _context_stream_reference(
    bundle: Mapping[str, Any],
) -> tuple[str, int, int, Mapping[str, int] | None]:
    value = bundle.get("strategy_context_stream")
    if not isinstance(value, Mapping) or frozenset(value) not in {
        frozenset({"artifact", "context_count"}),
        frozenset({"artifact", "context_count", "component_counts"}),
    }:
        raise ValueError("runtime bundle context stream reference is invalid")
    artifact_value = value["artifact"]
    if not isinstance(artifact_value, Mapping) or set(artifact_value) != {
        "content_digest",
        "byte_length",
        "media_type",
        "schema_version",
        "storage_key",
        "retention_class",
    }:
        raise ValueError("runtime bundle context stream artifact is invalid")
    component_counts: dict[str, int] | None = None
    if "component_counts" in value:
        if (
            artifact_value["media_type"] != NAUTILUS_COMPONENT_CONTEXT_STREAM_MEDIA_TYPE
            or artifact_value["schema_version"] != NAUTILUS_COMPONENT_CONTEXT_STREAM_SCHEMA
        ):
            raise ValueError("runtime bundle component context stream type is unsupported")
        raw_counts = value["component_counts"]
        if not isinstance(raw_counts, list) or not raw_counts:
            raise ValueError("runtime bundle component context counts are invalid")
        component_counts = {}
        previous_component_id: str | None = None
        for item in raw_counts:
            if not isinstance(item, Mapping) or set(item) != {
                "component_id",
                "context_count",
            }:
                raise ValueError("runtime bundle component context count fields are invalid")
            component_id = item["component_id"]
            count = item["context_count"]
            if (
                not isinstance(component_id, str)
                or not component_id.strip()
                or (previous_component_id is not None and component_id <= previous_component_id)
            ):
                raise ValueError("runtime bundle component context ids must be uniquely sorted")
            if not isinstance(count, int) or isinstance(count, bool) or count < 1:
                raise ValueError("runtime bundle component context count must be positive")
            previous_component_id = component_id
            component_counts[component_id] = count
    elif (
        artifact_value["media_type"] != NAUTILUS_CONTEXT_STREAM_MEDIA_TYPE
        or artifact_value["schema_version"] != NAUTILUS_CONTEXT_STREAM_SCHEMA
    ):
        raise ValueError("runtime bundle context stream media type or schema is unsupported")
    if artifact_value["retention_class"] != "pinned_input":
        raise ValueError("runtime bundle context stream retention is unsupported")
    digest = artifact_value["content_digest"]
    storage_key = artifact_value["storage_key"]
    require_sha256_digest(digest, field_name="context stream content digest")
    require_sha256_digest(storage_key, field_name="context stream storage key")
    if storage_key != digest:
        raise ValueError("runtime bundle context stream key differs from its content digest")
    byte_length = artifact_value["byte_length"]
    if not isinstance(byte_length, int) or isinstance(byte_length, bool) or byte_length <= 0:
        raise ValueError("runtime bundle context stream byte length must be positive")
    context_count = value["context_count"]
    if not isinstance(context_count, int) or isinstance(context_count, bool) or context_count < 1:
        raise ValueError("runtime bundle context count must be positive")
    if component_counts is not None and sum(component_counts.values()) != context_count:
        raise ValueError("runtime bundle component context counts differ from context_count")
    return digest, byte_length, context_count, component_counts


def _native_event_stream_reference(
    bundle: Mapping[str, Any],
) -> tuple[str, int, str, str, int]:
    value = bundle.get("native_event_stream")
    if not isinstance(value, Mapping) or set(value) != {
        "artifact",
        "source_tape_fingerprint",
        "adapter_version",
        "event_count",
    }:
        raise ValueError("runtime bundle native event stream reference is invalid")
    artifact = value["artifact"]
    if not isinstance(artifact, Mapping) or set(artifact) != {
        "content_digest",
        "byte_length",
        "media_type",
        "schema_version",
        "storage_key",
        "retention_class",
    }:
        raise ValueError("runtime bundle native event stream artifact is invalid")
    if artifact["media_type"] != NAUTILUS_NATIVE_EVENT_STREAM_MEDIA_TYPE:
        raise ValueError("runtime bundle native event stream media type is unsupported")
    if artifact["schema_version"] != NAUTILUS_NATIVE_EVENT_STREAM_SCHEMA:
        raise ValueError("runtime bundle native event stream schema is unsupported")
    if artifact["retention_class"] != "pinned_input":
        raise ValueError("runtime bundle native event stream retention is unsupported")
    digest = artifact["content_digest"]
    storage_key = artifact["storage_key"]
    require_sha256_digest(digest, field_name="native event stream content digest")
    require_sha256_digest(storage_key, field_name="native event stream storage key")
    if storage_key != digest:
        raise ValueError("runtime bundle native event stream key differs from its digest")
    byte_length = artifact["byte_length"]
    if (
        not isinstance(byte_length, int)
        or isinstance(byte_length, bool)
        or byte_length <= 0
        or byte_length > MAX_NAUTILUS_NATIVE_EVENT_STREAM_BYTES
    ):
        raise ValueError("runtime bundle native event stream byte length is invalid")
    source_fingerprint = value["source_tape_fingerprint"]
    require_sha256_digest(source_fingerprint, field_name="native event source fingerprint")
    adapter_version = value["adapter_version"]
    if not isinstance(adapter_version, str) or not adapter_version.strip():
        raise ValueError("runtime bundle native event adapter version is invalid")
    event_count = value["event_count"]
    if not isinstance(event_count, int) or isinstance(event_count, bool) or event_count < 1:
        raise ValueError("runtime bundle native event count is invalid")
    engine_input = bundle.get("engine_input")
    if not isinstance(engine_input, Mapping):
        raise ValueError("runtime bundle engine input is invalid")
    engine_tape = engine_input.get("event_tape")
    if not isinstance(engine_tape, Mapping) or set(engine_tape) != {
        "source_tape_fingerprint",
        "adapter_version",
        "event_count",
    }:
        raise ValueError("runtime bundle must not inline its streamed native events")
    if (
        engine_tape["source_tape_fingerprint"] != source_fingerprint
        or engine_tape["adapter_version"] != adapter_version
        or not isinstance(engine_tape["event_count"], int)
        or isinstance(engine_tape["event_count"], bool)
        or engine_tape["event_count"] != event_count
    ):
        raise ValueError("runtime bundle native event stream differs from the engine input")
    return digest, byte_length, source_fingerprint, adapter_version, event_count


def _open_verified_native_event_stream(
    path_value: str,
    *,
    expected_digest: str,
    byte_length: int,
) -> BinaryIO:
    descriptor = os.open(
        path_value,
        os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("runtime native event stream must be a regular file")
        if metadata.st_size != byte_length:
            raise ValueError("runtime native event stream byte length differs")
        digest = hashlib.sha256()
        stream = os.fdopen(descriptor, "rb")
        descriptor = -1
        try:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
            if f"sha256:{digest.hexdigest()}" != expected_digest:
                raise ValueError("runtime native event stream artifact digest differs")
            stream.seek(0)
            return stream
        except BaseException:
            stream.close()
            raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _open_verified_context_stream(
    path_value: str,
    *,
    expected_digest: str,
    byte_length: int,
    max_bytes: int,
) -> BinaryIO:
    """Open and verify the immutable strategy context sidecar without following links."""

    descriptor = os.open(
        path_value,
        os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("runtime strategy context stream must be a regular file")
        if metadata.st_size != byte_length or metadata.st_size > max_bytes:
            raise ValueError("runtime strategy context stream byte length differs")
        stream = os.fdopen(descriptor, "rb")
        descriptor = -1
        try:
            digest = hashlib.sha256()
            total = 0
            while chunk := stream.read(65_536):
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("runtime strategy context stream exceeds its byte limit")
                digest.update(chunk)
            if total != byte_length or f"sha256:{digest.hexdigest()}" != expected_digest:
                raise ValueError("runtime strategy context stream artifact digest differs")
            stream.seek(0)
            return stream
        except BaseException:
            stream.close()
            raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)


class ForwardSessionFactoryBuilder(Protocol):
    """Build one per-instance native session factory from verified read-only inputs."""

    def __call__(
        self,
        bootstrap: NautilusForwardRuntimeBootstrap,
        bundle: Mapping[str, Any],
        context_stream: BinaryIO,
        native_event_stream: BinaryIO,
    ) -> NativeForwardSessionFactory: ...


def serve_forward_runtime(
    *,
    bootstrap_path: str,
    bootstrap_fingerprint: str,
    input_path: str,
    context_stream_path: str,
    native_event_stream_path: str,
    expected_version: str,
    instance_id: str,
    snapshot_fingerprint: str,
    max_input_bytes: int,
    session_factory_builder: ForwardSessionFactoryBuilder,
    input_stream: BinaryIO,
    output_stream: BinaryIO,
) -> int:
    """Verify mounted state, then serve the bounded IPC protocol for one instance.

    The builder runs only after every immutable input and the exact Nautilus
    package version have been verified. Its file handles remain open for the
    lifetime of the IPC session so the native session can replay warm-up state
    without reopening mutable paths.
    """

    from app.strategy_lab_v2.nautilus_forward_runtime_server import (
        NautilusForwardRuntimeOperationHandler,
    )
    from app.strategy_lab_v2.nautilus_forward_wire import NautilusForwardJsonWireCodec
    from app.strategy_lab_v2.nautilus_runtime_ipc import serve_nautilus_runtime_ipc

    if not callable(session_factory_builder):
        raise TypeError("session_factory_builder must be callable")
    bootstrap, bundle = _verify_forward_startup(
        bootstrap_path=bootstrap_path,
        bootstrap_fingerprint=bootstrap_fingerprint,
        input_path=input_path,
        context_stream_path=context_stream_path,
        native_event_stream_path=native_event_stream_path,
        expected_version=expected_version,
        expected_instance_id=instance_id,
        expected_snapshot_fingerprint=snapshot_fingerprint,
        max_input_bytes=max_input_bytes,
    )
    context_digest, context_length, _context_count, _component_counts = _context_stream_reference(
        bundle
    )
    native_digest, native_length, *_ = _native_event_stream_reference(bundle)
    with (
        _open_verified_context_stream(
            context_stream_path,
            expected_digest=context_digest,
            byte_length=context_length,
            max_bytes=max_input_bytes,
        ) as context_stream,
        _open_verified_native_event_stream(
            native_event_stream_path,
            expected_digest=native_digest,
            byte_length=native_length,
        ) as native_event_stream,
    ):
        session_factory = session_factory_builder(
            bootstrap,
            bundle,
            context_stream,
            native_event_stream,
        )
        handler = NautilusForwardRuntimeOperationHandler(
            instance_id=instance_id,
            session_factory=session_factory,
            codec=NautilusForwardJsonWireCodec(),
        )
        return serve_nautilus_runtime_ipc(input_stream, output_stream, handler)


def _write_result(path_value: str, result: Mapping[str, Any]) -> None:
    path = Path(path_value)
    flags = os.O_WRONLY | os.O_TRUNC | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("runtime result target must be a regular file")
        wire = json.dumps(
            result,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(wire)
            stream.write(b"\n")
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)


def _open_result_stream(path_value: str, *, max_bytes: int) -> Any:
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
        raise ValueError("max_result_bytes must be a positive integer")
    descriptor = os.open(
        path_value,
        os.O_WRONLY | os.O_TRUNC | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("runtime invocation result target must be a regular file")
        return os.fdopen(descriptor, "wb")
    except BaseException:
        os.close(descriptor)
        raise


def _prepare_equity_trace_target(path_value: str, *, max_bytes: int) -> None:
    """Safely clear one pre-created writable target before Parquet opens it."""

    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
        raise ValueError("max_account_equity_trace_bytes must be positive")
    descriptor = os.open(
        path_value,
        os.O_WRONLY | os.O_TRUNC | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("runtime account-equity trace target must be a regular file")
    finally:
        os.close(descriptor)


def _prepare_native_reports_target(path_value: str, *, max_bytes: int) -> None:
    """Safely clear the pre-created report artifact target before Parquet opens it."""
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
        raise ValueError("max_native_reports_bytes must be positive")
    descriptor = os.open(
        path_value,
        os.O_WRONLY | os.O_TRUNC | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("runtime native reports target must be a regular file")
    finally:
        os.close(descriptor)


def run_bundle(
    input_path: str,
    output_path: str,
    *,
    expected_version: str,
    expected_snapshot_fingerprint: str,
    max_input_bytes: int,
    context_stream_path: str | None = None,
    native_event_stream_path: str | None = None,
    invocation_result_stream_path: str | None = None,
    max_result_bytes: int | None = None,
    account_equity_trace_path: str | None = None,
    max_account_equity_trace_bytes: int | None = None,
    native_reports_path: str | None = None,
    max_native_reports_bytes: int | None = None,
) -> int:
    """Run one bundle-bound SDK batch or verified stream into the result file."""

    if (
        not isinstance(max_input_bytes, int)
        or isinstance(max_input_bytes, bool)
        or max_input_bytes <= 0
    ):
        raise ValueError("max_input_bytes must be a positive integer")
    require_sha256_digest(
        expected_snapshot_fingerprint,
        field_name="expected_snapshot_fingerprint",
    )
    bundle = _read_bundle(input_path, max_bytes=max_input_bytes)
    engine_input = bundle["engine_input"]
    session_calendar = session_calendar_from_wire(bundle.get("session_calendar"))
    session_calendar_options: dict[str, Any] = (
        {} if session_calendar is None else {"session_calendar": session_calendar}
    )
    if engine_input["data_snapshot_fingerprint"] != expected_snapshot_fingerprint:
        raise ValueError("runtime bundle snapshot differs from the Nautilus execution plan")
    if runtime_package_version() != expected_version:
        raise ValueError("Nautilus package version differs from the execution plan")
    if bundle["schema"] == NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V1:
        if (
            context_stream_path is not None
            or native_event_stream_path is not None
            or invocation_result_stream_path is not None
            or max_result_bytes is not None
            or account_equity_trace_path is not None
            or max_account_equity_trace_bytes is not None
            or native_reports_path is not None
            or max_native_reports_bytes is not None
            or os.environ.get("STRATEGY_CONTEXT_STREAM_DIGEST")
            or os.environ.get("STRATEGY_NATIVE_EVENT_STREAM_DIGEST")
        ):
            raise ValueError("legacy runtime bundle cannot bind strategy streams")
        result = run_native_backtest(
            engine_input,
            serialized_strategy_invocation_batch=bundle["serialized_strategy_invocation_batch"],
        )
    else:
        native_stream_binding: tuple[str, int] | None = None
        component_stream_bundle = bundle["schema"] == NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V4
        if bundle["schema"] == NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V5:
            context_reference = bundle["strategy_context_stream"]
            component_stream_bundle = (
                isinstance(context_reference, Mapping) and "component_counts" in context_reference
            )
        if bundle["schema"] in {
            NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V3,
            NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V4,
        } or (
            bundle["schema"] == NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V5
            and "native_event_stream" in bundle
        ):
            if native_event_stream_path is None:
                raise ValueError(
                    "native streaming runtime bundle requires its mounted event stream"
                )
            (
                native_digest,
                native_byte_length,
                source_tape_fingerprint,
                adapter_version,
                native_event_count,
            ) = _native_event_stream_reference(bundle)
            if os.environ.get("STRATEGY_NATIVE_EVENT_STREAM_DIGEST") != native_digest:
                raise ValueError("native event stream digest differs from the sandbox request")
            native_stream_binding = (native_digest, native_byte_length)
        elif native_event_stream_path is not None or os.environ.get(
            "STRATEGY_NATIVE_EVENT_STREAM_DIGEST"
        ):
            raise ValueError("legacy event-tape runtime bundle cannot bind a native event stream")
        if context_stream_path is None:
            raise ValueError("streaming runtime bundle requires its mounted context stream")
        if (
            invocation_result_stream_path is None
            or max_result_bytes is None
            or account_equity_trace_path is None
            or max_account_equity_trace_bytes is None
        ):
            raise ValueError("streaming runtime bundle requires its bounded result stream")
        if (
            not isinstance(max_result_bytes, int)
            or isinstance(max_result_bytes, bool)
            or max_result_bytes < 1
        ):
            raise ValueError("max_result_bytes must be a positive integer")
        if (
            not isinstance(max_account_equity_trace_bytes, int)
            or isinstance(max_account_equity_trace_bytes, bool)
            or max_account_equity_trace_bytes < 1
        ):
            raise ValueError("max_account_equity_trace_bytes must be a positive integer")
        _prepare_equity_trace_target(
            account_equity_trace_path,
            max_bytes=max_account_equity_trace_bytes,
        )
        if (native_reports_path is None) != (max_native_reports_bytes is None):
            raise ValueError("native report path and byte bound must be provided together")
        if native_reports_path is not None:
            if (
                not isinstance(max_native_reports_bytes, int)
                or isinstance(max_native_reports_bytes, bool)
                or max_native_reports_bytes < 1
            ):
                raise ValueError("max_native_reports_bytes must be a positive integer")
            _prepare_native_reports_target(
                native_reports_path,
                max_bytes=max_native_reports_bytes,
            )
        (
            context_digest,
            context_byte_length,
            context_count,
            component_context_counts,
        ) = _context_stream_reference(bundle)
        if component_stream_bundle != (component_context_counts is not None):
            raise ValueError("runtime bundle context stream protocol differs from its schema")
        expected_context_digest = os.environ.get("STRATEGY_CONTEXT_STREAM_DIGEST")
        if expected_context_digest != context_digest:
            raise ValueError("context stream digest differs from the sandbox request")
        descriptor = os.open(
            context_stream_path,
            os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("runtime context stream must be a regular file")
            if metadata.st_size != context_byte_length:
                raise ValueError("runtime context stream byte length differs")
            if metadata.st_size > max_input_bytes:
                raise ValueError("runtime context stream exceeds its memory-derived limit")
            with os.fdopen(descriptor, "rb") as stream:
                descriptor = -1
                stream_digest = hashlib.sha256()
                total = 0
                while chunk := stream.read(65_536):
                    total += len(chunk)
                    if total > max_input_bytes:
                        raise ValueError("runtime context stream exceeds its memory-derived limit")
                    stream_digest.update(chunk)
                if f"sha256:{stream_digest.hexdigest()}" != context_digest:
                    raise ValueError("runtime context stream artifact digest differs")
                stream.seek(0)
                native_event_stream = None
                if native_stream_binding is not None:
                    native_digest, native_byte_length = native_stream_binding
                    if native_event_stream_path is None:
                        raise ValueError("runtime native event stream path is required")
                    native_event_stream = _open_verified_native_event_stream(
                        native_event_stream_path,
                        expected_digest=native_digest,
                        byte_length=native_byte_length,
                    )
                try:
                    native_report_options: dict[str, Any] = (
                        {}
                        if native_reports_path is None
                        else {
                            "native_reports_path": native_reports_path,
                            "max_native_reports_bytes": max_native_reports_bytes,
                        }
                    )
                    with _open_result_stream(
                        invocation_result_stream_path,
                        max_bytes=max_result_bytes,
                    ) as result_stream:
                        if native_event_stream is None:
                            result = run_native_backtest(
                                engine_input,
                                invocation_context_stream=stream,
                                expected_context_count=context_count,
                                invocation_result_stream=result_stream,
                                max_invocation_result_bytes=max_result_bytes,
                                account_equity_trace_path=account_equity_trace_path,
                                max_account_equity_trace_bytes=max_account_equity_trace_bytes,
                                **session_calendar_options,
                                **native_report_options,
                            )
                        else:
                            if component_context_counts is None:
                                result = run_native_backtest(
                                    engine_input,
                                    invocation_context_stream=stream,
                                    native_event_stream=native_event_stream,
                                    native_event_stream_digest=native_digest,
                                    expected_context_count=context_count,
                                    invocation_result_stream=result_stream,
                                    max_invocation_result_bytes=max_result_bytes,
                                    account_equity_trace_path=account_equity_trace_path,
                                    max_account_equity_trace_bytes=max_account_equity_trace_bytes,
                                    **session_calendar_options,
                                    **native_report_options,
                                )
                            else:
                                result = run_native_backtest(
                                    engine_input,
                                    invocation_context_stream=stream,
                                    native_event_stream=native_event_stream,
                                    native_event_stream_digest=native_digest,
                                    expected_context_count=context_count,
                                    expected_component_context_counts=component_context_counts,
                                    invocation_result_stream=result_stream,
                                    max_invocation_result_bytes=max_result_bytes,
                                    account_equity_trace_path=account_equity_trace_path,
                                    max_account_equity_trace_bytes=max_account_equity_trace_bytes,
                                    **session_calendar_options,
                                    **native_report_options,
                                )
                        result_stream.flush()
                        os.fsync(result_stream.fileno())
                finally:
                    if native_event_stream is not None:
                        native_event_stream.close()
        finally:
            if descriptor >= 0:
                os.close(descriptor)
    if result["engine_version"] != expected_version:
        raise ValueError("Nautilus package version differs from the execution plan")
    _write_result(output_path, result)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--probe", action="store_true")
    mode.add_argument("--input")
    parser.add_argument("--output")
    parser.add_argument("--expected-version", default="2.0.0rc5")
    parser.add_argument("--snapshot-fingerprint")
    parser.add_argument("--max-input-bytes", type=int)
    parser.add_argument("--context-stream")
    parser.add_argument("--native-event-stream")
    parser.add_argument("--invocation-results")
    parser.add_argument("--max-result-bytes", type=int)
    parser.add_argument("--account-equity-trace")
    parser.add_argument("--max-account-equity-trace-bytes", type=int)
    parser.add_argument("--native-reports")
    parser.add_argument("--max-native-reports-bytes", type=int)
    args = parser.parse_args(argv)
    if args.probe:
        if any(
            value is not None
            for value in (
                args.output,
                args.snapshot_fingerprint,
                args.max_input_bytes,
                args.context_stream,
                args.native_event_stream,
                args.invocation_results,
                args.max_result_bytes,
                args.account_equity_trace,
                args.max_account_equity_trace_bytes,
                args.native_reports,
                args.max_native_reports_bytes,
            )
        ):
            parser.error("--probe cannot be combined with runtime bundle options")
        probe = probe_nautilus_runtime(expected_version=args.expected_version)
        print(json.dumps(probe, sort_keys=True, separators=(",", ":")))
        return 0
    if args.output is None or args.snapshot_fingerprint is None or args.max_input_bytes is None:
        parser.error("--input requires --output, --snapshot-fingerprint, and --max-input-bytes")
    return run_bundle(
        args.input,
        args.output,
        expected_version=args.expected_version,
        expected_snapshot_fingerprint=args.snapshot_fingerprint,
        max_input_bytes=args.max_input_bytes,
        context_stream_path=args.context_stream,
        native_event_stream_path=args.native_event_stream,
        invocation_result_stream_path=args.invocation_results,
        max_result_bytes=args.max_result_bytes,
        account_equity_trace_path=args.account_equity_trace,
        max_account_equity_trace_bytes=args.max_account_equity_trace_bytes,
        native_reports_path=args.native_reports,
        max_native_reports_bytes=args.max_native_reports_bytes,
    )


if __name__ == "__main__":  # pragma: no cover - isolated image entrypoint
    raise SystemExit(main())


__all__ = ["main", "run_bundle", "serve_forward_runtime"]
