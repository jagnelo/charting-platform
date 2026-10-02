"""Authenticated worker bundle for one isolated Nautilus invocation.

The host serializes an already-frozen engine input and the engine-neutral SDK
invocation batch into a read-only worker mount. The bundle digest is the
``StrategyRuntimeRequest.input_bundle_digest`` consumed by the normal sandbox
environment contract. This wire format is a bounded compatibility handoff;
large historical catalog streaming remains a separate data-plane concern.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.nautilus_engine_input import NautilusEngineInput
from app.strategy_lab_v2.nautilus_runtime_protocol import NAUTILUS_RUNTIME_BUNDLE_SCHEMA
from strategy_runtime import deserialize_invocation_batch


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

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


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
    "NAUTILUS_RUNTIME_BUNDLE_SCHEMA",
    "NautilusRuntimeBundle",
    "NautilusRuntimeBundleError",
    "build_nautilus_runtime_bundle",
]
