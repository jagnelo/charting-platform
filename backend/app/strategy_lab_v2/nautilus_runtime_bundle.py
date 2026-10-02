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
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

from app.strategy_lab_v2.artifact_store import (
    ArtifactStoreDecision,
    LocalArtifactStore,
)
from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import ArtifactManifest, ArtifactRetention
from app.strategy_lab_v2.nautilus_engine_input import NautilusEngineInput
from app.strategy_lab_v2.nautilus_runtime_protocol import NAUTILUS_RUNTIME_BUNDLE_SCHEMA
from strategy_runtime import deserialize_invocation_batch

NAUTILUS_RUNTIME_ARTIFACT_MEDIA_TYPE = "application/vnd.charting.strategy-lab.nautilus+json"
NAUTILUS_RUNTIME_ARTIFACT_SCHEMA = "strategy-lab.nautilus-runtime-bundle.v1"


class NautilusRuntimeBundleError(ValueError):
    """Malformed or inconsistent local Nautilus worker input."""


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
        )

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

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def materialize_nautilus_runtime_bundle(
    bundle: NautilusRuntimeBundle,
    store: LocalArtifactStore,
) -> NautilusRuntimeInputArtifactReference:
    """Publish bundle bytes immutably and return only their durable identity."""

    if not isinstance(bundle, NautilusRuntimeBundle):
        raise TypeError("bundle must be a NautilusRuntimeBundle")
    if not isinstance(store, LocalArtifactStore):
        raise TypeError("store must be a LocalArtifactStore")
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
    wire_bytes, _integrity = store.read_manifest(reference.artifact)
    return NautilusRuntimeBundle(
        attempt_id=reference.attempt_id,
        input_bundle_digest=reference.input_bundle_digest,
        wire_bytes=wire_bytes,
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
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
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
) -> None:
    try:
        payload = json.loads(
            wire_bytes,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("Nautilus runtime input artifact is malformed") from error
    if not isinstance(payload, Mapping) or set(payload) != {
        "schema",
        "engine_input",
        "serialized_strategy_invocation_batch",
    }:
        raise ValueError("Nautilus runtime input artifact fields are invalid")
    if payload["schema"] != NAUTILUS_RUNTIME_BUNDLE_SCHEMA:
        raise ValueError("Nautilus runtime input artifact schema is unsupported")
    engine_input = payload["engine_input"]
    if not isinstance(engine_input, Mapping) or engine_input.get("attempt_id") != attempt_id:
        raise ValueError("Nautilus runtime input artifact attempt identity differs")
    if not isinstance(payload["serialized_strategy_invocation_batch"], str):
        raise ValueError("Nautilus runtime input artifact strategy batch is invalid")
    if content_digest(payload) != input_bundle_digest:
        raise ValueError("Nautilus runtime input artifact semantic digest differs")


def build_nautilus_runtime_bundle(
    engine_input: NautilusEngineInput,
    serialized_strategy_invocation_batch: str,
) -> NautilusRuntimeBundle:
    """Serialize typed frozen inputs and authenticate their SDK batch binding."""

    if not isinstance(engine_input, NautilusEngineInput):
        raise TypeError("engine_input must be a NautilusEngineInput")
    if not isinstance(serialized_strategy_invocation_batch, str):
        raise TypeError("serialized_strategy_invocation_batch must be a string")
    try:
        source, manifest, contexts, entrypoint, _max_intents = deserialize_invocation_batch(
            serialized_strategy_invocation_batch
        )
    except (TypeError, ValueError) as error:
        raise NautilusRuntimeBundleError("strategy invocation batch is malformed") from error
    if content_digest(source) != engine_input.strategy_source_digest:
        raise NautilusRuntimeBundleError("strategy batch source digest differs from engine input")
    if manifest.fingerprint != engine_input.strategy_manifest_fingerprint:
        raise NautilusRuntimeBundleError("strategy batch manifest differs from engine input")
    if entrypoint != engine_input.entrypoint:
        raise NautilusRuntimeBundleError("strategy batch entrypoint differs from engine input")
    if any(context.parameters != engine_input.parameters for context in contexts):
        raise NautilusRuntimeBundleError("strategy batch parameters differ from engine input")
    if any(context.random_seed != engine_input.random_seed for context in contexts):
        raise NautilusRuntimeBundleError("strategy batch seed differs from engine input")

    tape = engine_input.event_tape
    payload = {
        "schema": NAUTILUS_RUNTIME_BUNDLE_SCHEMA,
        "engine_input": {
            "trial_id": engine_input.trial_id,
            "attempt_id": engine_input.attempt_id,
            "data_snapshot_fingerprint": engine_input.data_snapshot_fingerprint,
            "event_tape": {
                "source_tape_fingerprint": tape.source_tape_fingerprint,
                "adapter_version": tape.adapter_version,
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
                ],
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
            "strategy_source_digest": engine_input.strategy_source_digest,
            "strategy_manifest_fingerprint": engine_input.strategy_manifest_fingerprint,
            "entrypoint": engine_input.entrypoint,
            "parameters": _wire_value(engine_input.parameters),
            "random_seed": engine_input.random_seed,
            "input_version": engine_input.input_version,
        },
        "serialized_strategy_invocation_batch": serialized_strategy_invocation_batch,
    }
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
    )


__all__ = [
    "NAUTILUS_RUNTIME_ARTIFACT_MEDIA_TYPE",
    "NAUTILUS_RUNTIME_ARTIFACT_SCHEMA",
    "NAUTILUS_RUNTIME_BUNDLE_SCHEMA",
    "NautilusRuntimeBundle",
    "NautilusRuntimeBundleError",
    "NautilusRuntimeInputArtifactReference",
    "build_nautilus_runtime_bundle",
    "load_materialized_nautilus_runtime_bundle",
    "materialize_nautilus_runtime_bundle",
    "verify_nautilus_runtime_artifact_file",
]
