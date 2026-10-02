"""Hardened CLI for the isolated Nautilus runtime image."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.nautilus_runtime_adapter import (
    run_native_backtest,
    runtime_package_version,
)
from app.strategy_lab_v2.nautilus_runtime_probe import probe_nautilus_runtime
from app.strategy_lab_v2.nautilus_runtime_protocol import (
    NAUTILUS_CONTEXT_STREAM_MEDIA_TYPE,
    NAUTILUS_CONTEXT_STREAM_SCHEMA,
    NAUTILUS_RUNTIME_BUNDLE_SCHEMA,
    NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V1,
)

_LEGACY_BUNDLE_FIELDS = frozenset(
    {"schema", "engine_input", "serialized_strategy_invocation_batch"}
)
_STREAMING_BUNDLE_FIELDS = frozenset({"schema", "engine_input", "strategy_context_stream"})


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


def _context_stream_reference(bundle: Mapping[str, Any]) -> tuple[str, int, int]:
    value = bundle.get("strategy_context_stream")
    if not isinstance(value, Mapping) or set(value) != {"artifact", "context_count"}:
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
    if artifact_value["media_type"] != NAUTILUS_CONTEXT_STREAM_MEDIA_TYPE:
        raise ValueError("runtime bundle context stream media type is unsupported")
    if artifact_value["schema_version"] != NAUTILUS_CONTEXT_STREAM_SCHEMA:
        raise ValueError("runtime bundle context stream schema is unsupported")
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
    return digest, byte_length, context_count


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


def run_bundle(
    input_path: str,
    output_path: str,
    *,
    expected_version: str,
    expected_snapshot_fingerprint: str,
    max_input_bytes: int,
    context_stream_path: str | None = None,
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
    if engine_input["data_snapshot_fingerprint"] != expected_snapshot_fingerprint:
        raise ValueError("runtime bundle snapshot differs from the Nautilus execution plan")
    if runtime_package_version() != expected_version:
        raise ValueError("Nautilus package version differs from the execution plan")
    if bundle["schema"] == NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V1:
        if context_stream_path is not None or os.environ.get("STRATEGY_CONTEXT_STREAM_DIGEST"):
            raise ValueError("legacy runtime bundle cannot bind a context stream")
        result = run_native_backtest(
            engine_input,
            serialized_strategy_invocation_batch=bundle["serialized_strategy_invocation_batch"],
        )
    else:
        if context_stream_path is None:
            raise ValueError("streaming runtime bundle requires its mounted context stream")
        context_digest, context_byte_length, context_count = _context_stream_reference(bundle)
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
                result = run_native_backtest(
                    engine_input,
                    invocation_context_stream=stream,
                    expected_context_count=context_count,
                )
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
    args = parser.parse_args(argv)
    if args.probe:
        if any(
            value is not None
            for value in (
                args.output,
                args.snapshot_fingerprint,
                args.max_input_bytes,
                args.context_stream,
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
    )


if __name__ == "__main__":  # pragma: no cover - isolated image entrypoint
    raise SystemExit(main())


__all__ = ["main", "run_bundle"]
