"""Immutable, source-bound startup contract for a Nautilus forward session.

The host builds this value only after resolving an owner-scoped execution plan,
the frozen warm-up tape, its receipt, and the exact processed prefix. Large
market inputs remain content-addressed artifacts; the bounded processed prefix
is embedded so the isolated runtime can verify its canonical replay boundary.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.strategy_lab_v2.artifact_store import (
    ArtifactStoreDecision,
    LocalArtifactStore,
)
from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.canonical import content_digest, freeze_json, require_sha256_digest
from app.strategy_lab_v2.contracts import ArtifactManifest, ArtifactRetention
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.sdk import MarketEvent

if TYPE_CHECKING:
    from app.strategy_lab_v2.contracts import DataSnapshot
    from app.strategy_lab_v2.event_tape_artifacts import FrozenEventTapeArtifactResolution
    from app.strategy_lab_v2.forward_execution_plan_resolution import ResolvedForwardExecutionPlan
    from app.strategy_lab_v2.forward_processed_prefix import ForwardProcessedEventPrefix
    from app.strategy_lab_v2.forward_warmup import ForwardWarmupReceipt
    from app.strategy_lab_v2.nautilus_engine_input import NautilusEngineInput
    from app.strategy_lab_v2.nautilus_runtime_bundle import (
        NautilusNativeEventStreamArtifactReference,
    )

NAUTILUS_FORWARD_BOOTSTRAP_SCHEMA = "strategy-lab.nautilus-forward-bootstrap.v1"
NAUTILUS_FORWARD_BOOTSTRAP_MEDIA_TYPE = "application/vnd.strategy-lab.nautilus-forward-bootstrap+json"
MAX_NAUTILUS_FORWARD_BOOTSTRAP_BYTES = 16 * 1024 * 1024


def _timestamp(value: str, *, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a timestamp string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name} is not a valid timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return parsed.astimezone(UTC)


def _encode_value(value: Any) -> Any:
    """Encode the SDK's frozen scalar and sequence values without type loss."""
    if value is None or isinstance(value, bool | str | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("bootstrap values cannot contain non-finite floats")
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("bootstrap values cannot contain non-finite decimals")
        return {"$type": "decimal", "value": str(value)}
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("bootstrap datetime values must be timezone-aware")
        return {"$type": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"$type": "date", "value": value.isoformat()}
    if isinstance(value, timedelta):
        return {
            "$type": "timedelta",
            "days": value.days,
            "seconds": value.seconds,
            "microseconds": value.microseconds,
        }
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("bootstrap mapping keys must be strings")
        return {
            "$type": "mapping",
            "entries": [[key, _encode_value(value[key])] for key in sorted(value)],
        }
    if isinstance(value, tuple | list):
        return {
            "$type": "tuple" if isinstance(value, tuple) else "list",
            "items": [_encode_value(item) for item in value],
        }
    raise ValueError(f"unsupported bootstrap value type: {type(value).__name__}")


def _decode_value(value: Any) -> Any:
    if value is None or isinstance(value, bool | str | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("bootstrap values cannot contain non-finite floats")
        return value
    if isinstance(value, list):
        return [_decode_value(item) for item in value]
    if not isinstance(value, Mapping):
        raise ValueError("bootstrap value is not a supported wire type")
    tag = value.get("$type")
    if tag == "mapping" and set(value) == {"$type", "entries"}:
        entries = value["entries"]
        if not isinstance(entries, list):
            raise ValueError("bootstrap mapping wire value is invalid")
        result: dict[str, Any] = {}
        previous: str | None = None
        for entry in entries:
            if not isinstance(entry, list) or len(entry) != 2:
                raise ValueError("bootstrap mapping entry is invalid")
            key = entry[0]
            if not isinstance(key, str) or (previous is not None and key <= previous):
                raise ValueError("bootstrap mapping keys must be uniquely sorted strings")
            result[key] = _decode_value(entry[1])
            previous = key
        return result
    if tag == "decimal" and set(value) == {"$type", "value"}:
        raw = value["value"]
        if not isinstance(raw, str) or not raw:
            raise ValueError("bootstrap decimal wire value is invalid")
        try:
            parsed = Decimal(raw)
        except InvalidOperation as error:
            raise ValueError("bootstrap decimal wire value is invalid") from error
        if not parsed.is_finite() or str(parsed) != raw:
            raise ValueError("bootstrap decimal wire value is not canonical")
        return parsed
    if tag == "datetime" and set(value) == {"$type", "value"}:
        return _timestamp(value["value"], field_name="market value datetime")
    if tag == "date" and set(value) == {"$type", "value"}:
        raw = value["value"]
        if not isinstance(raw, str):
            raise ValueError("bootstrap date wire value is invalid")
        try:
            return date.fromisoformat(raw)
        except ValueError as error:
            raise ValueError("bootstrap date wire value is invalid") from error
    if tag == "timedelta" and set(value) == {
        "$type",
        "days",
        "seconds",
        "microseconds",
    }:
        parts = (value["days"], value["seconds"], value["microseconds"])
        if any(not isinstance(part, int) or isinstance(part, bool) for part in parts):
            raise ValueError("bootstrap timedelta wire value is invalid")
        return timedelta(days=parts[0], seconds=parts[1], microseconds=parts[2])
    if tag in {"tuple", "list"} and set(value) == {"$type", "items"}:
        items = value["items"]
        if not isinstance(items, list):
            raise ValueError("bootstrap sequence wire value is invalid")
        decoded = [_decode_value(item) for item in items]
        return tuple(decoded) if tag == "tuple" else decoded
    raise ValueError("bootstrap value type tag is invalid")


class _InvalidBootstrapJson(ValueError):
    """A syntactically valid JSON document that violates bootstrap wire rules."""


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _InvalidBootstrapJson("forward bootstrap JSON contains duplicate fields")
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> None:
    raise _InvalidBootstrapJson("forward bootstrap JSON contains a non-finite number")


@dataclass(frozen=True, slots=True)
class NautilusForwardBootstrapComponent:
    """One exact strategy/package recipe in a shared-account forward plan."""

    component_id: str
    execution_binding_fingerprint: str
    resolved_component_fingerprint: str
    strategy_fingerprint: str
    package_fingerprint: str
    package_archive_digest: str
    dependency_lock_digest: str
    manifest_fingerprint: str
    source_digest: str
    parameters_digest: str
    random_seed: int

    def __post_init__(self) -> None:
        if not isinstance(self.component_id, str) or not self.component_id.strip():
            raise ValueError("component_id must not be empty")
        for name in (
            "execution_binding_fingerprint",
            "resolved_component_fingerprint",
            "strategy_fingerprint",
            "package_fingerprint",
            "package_archive_digest",
            "dependency_lock_digest",
            "manifest_fingerprint",
            "source_digest",
            "parameters_digest",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        if not isinstance(self.random_seed, int) or isinstance(self.random_seed, bool):
            raise TypeError("random_seed must be an integer")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)

    def to_wire(self) -> dict[str, object]:
        return {
            "component_id": self.component_id,
            "execution_binding_fingerprint": self.execution_binding_fingerprint,
            "resolved_component_fingerprint": self.resolved_component_fingerprint,
            "strategy_fingerprint": self.strategy_fingerprint,
            "package_fingerprint": self.package_fingerprint,
            "package_archive_digest": self.package_archive_digest,
            "dependency_lock_digest": self.dependency_lock_digest,
            "manifest_fingerprint": self.manifest_fingerprint,
            "source_digest": self.source_digest,
            "parameters_digest": self.parameters_digest,
            "random_seed": self.random_seed,
        }

    @classmethod
    def from_wire(cls, value: Mapping[str, Any]) -> NautilusForwardBootstrapComponent:
        fields = {
            "component_id",
            "execution_binding_fingerprint",
            "resolved_component_fingerprint",
            "strategy_fingerprint",
            "package_fingerprint",
            "package_archive_digest",
            "dependency_lock_digest",
            "manifest_fingerprint",
            "source_digest",
            "parameters_digest",
            "random_seed",
        }
        if not isinstance(value, Mapping) or set(value) != fields:
            raise ValueError("forward bootstrap component fields are invalid")
        return cls(**dict(value))


@dataclass(frozen=True, slots=True)
class NautilusForwardBootstrapEvent:
    """One admitted canonical event plus its source-verified SDK payload."""

    canonical_event: CanonicalForwardEvent
    market_event: MarketEvent
    verified_source_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.canonical_event, CanonicalForwardEvent):
            raise TypeError("canonical_event must be a CanonicalForwardEvent")
        if not isinstance(self.market_event, MarketEvent):
            raise TypeError("market_event must be a MarketEvent")
        require_sha256_digest(self.verified_source_digest, field_name="verified_source_digest")
        if self.canonical_event.correction_of is not None:
            raise ValueError("correction events cannot enter the native forward bootstrap")
        if self.verified_source_digest != self.canonical_event.source_digest:
            raise ValueError("bootstrap source digest differs from canonical provenance")
        if (
            self.canonical_event.event_id != self.market_event.event_id
            or self.canonical_event.sequence != self.market_event.sequence
            or self.canonical_event.event_time != self.market_event.event_time
        ):
            raise ValueError("bootstrap market payload differs from canonical event identity")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)

    def to_wire(self) -> dict[str, object]:
        canonical = self.canonical_event
        market = self.market_event
        return {
            "canonical_event": {
                "event_id": canonical.event_id,
                "sequence": canonical.sequence,
                "event_time": canonical.event_time.isoformat().replace("+00:00", "Z"),
                "arrived_at": canonical.arrived_at.isoformat().replace("+00:00", "Z"),
                "source_digest": canonical.source_digest,
                "correction_of": canonical.correction_of,
            },
            "market_event": {
                "dependency_id": market.dependency_id,
                "event_id": market.event_id,
                "instrument_id": market.instrument_id,
                "event_time": market.event_time.isoformat().replace("+00:00", "Z"),
                "sequence": market.sequence,
                "values": _encode_value(market.values),
            },
            "verified_source_digest": self.verified_source_digest,
        }

    @classmethod
    def from_wire(cls, value: Mapping[str, Any]) -> NautilusForwardBootstrapEvent:
        if not isinstance(value, Mapping) or set(value) != {
            "canonical_event",
            "market_event",
            "verified_source_digest",
        }:
            raise ValueError("forward bootstrap event fields are invalid")
        canonical_value = value["canonical_event"]
        market_value = value["market_event"]
        if not isinstance(canonical_value, Mapping) or set(canonical_value) != {
            "event_id",
            "sequence",
            "event_time",
            "arrived_at",
            "source_digest",
            "correction_of",
        }:
            raise ValueError("forward bootstrap canonical event fields are invalid")
        if not isinstance(market_value, Mapping) or set(market_value) != {
            "dependency_id",
            "event_id",
            "instrument_id",
            "event_time",
            "sequence",
            "values",
        }:
            raise ValueError("forward bootstrap market event fields are invalid")
        values = market_value["values"]
        if not isinstance(values, Mapping):
            raise ValueError("forward bootstrap market values are invalid")
        decoded_values = _decode_value(values)
        frozen_values = freeze_json(decoded_values)
        if not isinstance(frozen_values, Mapping):
            raise ValueError("forward bootstrap market values are invalid")
        canonical = CanonicalForwardEvent(
            event_id=canonical_value["event_id"],
            sequence=canonical_value["sequence"],
            event_time=_timestamp(canonical_value["event_time"], field_name="event_time"),
            arrived_at=_timestamp(canonical_value["arrived_at"], field_name="arrived_at"),
            source_digest=canonical_value["source_digest"],
            correction_of=canonical_value["correction_of"],
        )
        market = MarketEvent(
            dependency_id=market_value["dependency_id"],
            event_id=market_value["event_id"],
            instrument_id=market_value["instrument_id"],
            event_time=_timestamp(market_value["event_time"], field_name="event_time"),
            sequence=market_value["sequence"],
            values=frozen_values,
        )
        return cls(canonical, market, value["verified_source_digest"])


@dataclass(frozen=True, slots=True)
class NautilusForwardRuntimeBootstrap:
    """Versioned identity envelope consumed before an isolated session opens."""

    instance_id: str
    execution_plan_fingerprint: str
    portfolio_fingerprint: str
    snapshot_fingerprint: str
    warmup_receipt_fingerprint: str
    warmup_result_fingerprint: str
    warmup_tape_fingerprint: str
    warmup_event_count: int
    warmup_source_artifact_digests: tuple[str, ...]
    warmup_cursor_event_id: str | None
    warmup_cursor_sequence: int
    warmup_cursor_event_fingerprint: str | None
    processed_checkpoint_fingerprint: str
    processed_prefix_fingerprint: str
    before_event_fingerprint: str
    engine_input_fingerprint: str
    runtime_input_bundle_digest: str
    native_event_stream_digest: str
    native_event_stream_adapter_version: str
    components: tuple[NautilusForwardBootstrapComponent, ...]
    processed_events: tuple[NautilusForwardBootstrapEvent, ...]
    schema: str = NAUTILUS_FORWARD_BOOTSTRAP_SCHEMA

    def __post_init__(self) -> None:
        if not isinstance(self.instance_id, str) or not self.instance_id.strip():
            raise ValueError("instance_id must not be empty")
        if self.schema != NAUTILUS_FORWARD_BOOTSTRAP_SCHEMA:
            raise ValueError("forward bootstrap schema is unsupported")
        for name in (
            "execution_plan_fingerprint",
            "portfolio_fingerprint",
            "snapshot_fingerprint",
            "warmup_receipt_fingerprint",
            "warmup_result_fingerprint",
            "warmup_tape_fingerprint",
            "processed_checkpoint_fingerprint",
            "processed_prefix_fingerprint",
            "before_event_fingerprint",
            "engine_input_fingerprint",
            "runtime_input_bundle_digest",
            "native_event_stream_digest",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        if not isinstance(self.native_event_stream_adapter_version, str) or not (
            self.native_event_stream_adapter_version.strip()
        ):
            raise ValueError("native event stream adapter version must not be empty")
        if (
            not isinstance(self.warmup_event_count, int)
            or isinstance(self.warmup_event_count, bool)
            or self.warmup_event_count < 0
        ):
            raise ValueError("warmup_event_count must be a non-negative integer")
        if (
            not isinstance(self.warmup_cursor_sequence, int)
            or isinstance(self.warmup_cursor_sequence, bool)
            or self.warmup_cursor_sequence < 0
        ):
            raise ValueError("warmup_cursor_sequence must be a non-negative integer")
        if (self.warmup_cursor_event_id is None) != (self.warmup_cursor_event_fingerprint is None):
            raise ValueError("warm-up cursor identity fields must be supplied together")
        if self.warmup_cursor_event_id is None:
            if self.warmup_cursor_sequence != 0:
                raise ValueError("an empty warm-up cursor must have sequence zero")
        else:
            if not isinstance(self.warmup_cursor_event_id, str) or not (
                self.warmup_cursor_event_id.strip()
            ):
                raise ValueError("warmup_cursor_event_id must not be empty")
            cursor_fingerprint = self.warmup_cursor_event_fingerprint
            if not isinstance(cursor_fingerprint, str):
                raise ValueError("warmup_cursor_event_fingerprint must not be empty")
            require_sha256_digest(
                cursor_fingerprint,
                field_name="warmup_cursor_event_fingerprint",
            )
        source_digests = tuple(self.warmup_source_artifact_digests)
        for digest in source_digests:
            require_sha256_digest(digest, field_name="warmup_source_artifact_digest")
        if source_digests != tuple(sorted(set(source_digests))):
            raise ValueError("warm-up source artifact digests must be unique and ordered")
        components = tuple(self.components)
        if not components or any(
            not isinstance(item, NautilusForwardBootstrapComponent) for item in components
        ):
            raise ValueError("forward bootstrap requires typed component bindings")
        component_ids = [item.component_id for item in components]
        if component_ids != sorted(set(component_ids)):
            raise ValueError("forward bootstrap components must have unique sorted ids")
        events = tuple(self.processed_events)
        if any(not isinstance(item, NautilusForwardBootstrapEvent) for item in events):
            raise TypeError("processed_events must contain typed bootstrap events")
        keys = [(item.canonical_event.event_time, item.canonical_event.sequence) for item in events]
        if any(current <= previous for previous, current in zip(keys, keys[1:])):
            raise ValueError("bootstrap processed events must preserve canonical event order")
        if len({item.canonical_event.event_id for item in events}) != len(events):
            raise ValueError("bootstrap processed event ids must be unique")
        if self.warmup_cursor_event_id is not None:
            if any(item.canonical_event.sequence <= self.warmup_cursor_sequence for item in events):
                raise ValueError("processed prefix must follow the warm-up cursor")
        if any(item.canonical_event.event_id == self.warmup_cursor_event_id for item in events):
            raise ValueError("processed prefix duplicates the warm-up cursor event")
        object.__setattr__(self, "warmup_source_artifact_digests", source_digests)
        object.__setattr__(self, "components", components)
        object.__setattr__(self, "processed_events", events)

    @property
    def fingerprint(self) -> str:
        return content_digest(self.to_wire())

    def to_wire(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "instance_id": self.instance_id,
            "execution_plan_fingerprint": self.execution_plan_fingerprint,
            "portfolio_fingerprint": self.portfolio_fingerprint,
            "snapshot_fingerprint": self.snapshot_fingerprint,
            "warmup_receipt_fingerprint": self.warmup_receipt_fingerprint,
            "warmup_result_fingerprint": self.warmup_result_fingerprint,
            "warmup_tape_fingerprint": self.warmup_tape_fingerprint,
            "warmup_event_count": self.warmup_event_count,
            "warmup_source_artifact_digests": list(self.warmup_source_artifact_digests),
            "warmup_cursor_event_id": self.warmup_cursor_event_id,
            "warmup_cursor_sequence": self.warmup_cursor_sequence,
            "warmup_cursor_event_fingerprint": self.warmup_cursor_event_fingerprint,
            "processed_checkpoint_fingerprint": self.processed_checkpoint_fingerprint,
            "processed_prefix_fingerprint": self.processed_prefix_fingerprint,
            "before_event_fingerprint": self.before_event_fingerprint,
            "engine_input_fingerprint": self.engine_input_fingerprint,
            "runtime_input_bundle_digest": self.runtime_input_bundle_digest,
            "native_event_stream_digest": self.native_event_stream_digest,
            "native_event_stream_adapter_version": self.native_event_stream_adapter_version,
            "components": [item.to_wire() for item in self.components],
            "processed_events": [item.to_wire() for item in self.processed_events],
        }

    def to_json_bytes(self) -> bytes:
        encoded = json.dumps(
            self.to_wire(),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(encoded) > MAX_NAUTILUS_FORWARD_BOOTSTRAP_BYTES:
            raise ValueError("forward bootstrap exceeds its bounded byte limit")
        return encoded

    @classmethod
    def from_json_bytes(
        cls,
        encoded: bytes,
        *,
        expected_fingerprint: str | None = None,
    ) -> NautilusForwardRuntimeBootstrap:
        """Decode one canonical bounded bootstrap and optionally bind its digest."""

        if not isinstance(encoded, bytes):
            raise TypeError("forward bootstrap JSON must be bytes")
        if not encoded or len(encoded) > MAX_NAUTILUS_FORWARD_BOOTSTRAP_BYTES:
            raise ValueError("forward bootstrap JSON is empty or exceeds its byte limit")
        try:
            decoded = json.loads(
                encoded.decode("utf-8"),
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
        except _InvalidBootstrapJson:
            raise
        except (UnicodeError, json.JSONDecodeError, ValueError) as error:
            raise ValueError("forward bootstrap JSON is malformed") from error
        if not isinstance(decoded, Mapping):
            raise ValueError("forward bootstrap JSON must contain an object")
        bootstrap = cls.from_wire(decoded)
        if bootstrap.to_json_bytes() != encoded:
            raise ValueError("forward bootstrap JSON is not canonically encoded")
        if expected_fingerprint is not None:
            require_sha256_digest(expected_fingerprint, field_name="expected_fingerprint")
            if bootstrap.fingerprint != expected_fingerprint:
                raise ValueError("forward bootstrap fingerprint differs from its artifact binding")
        return bootstrap


    @classmethod
    def from_wire(cls, value: Mapping[str, Any]) -> NautilusForwardRuntimeBootstrap:
        fields = {
            "schema",
            "instance_id",
            "execution_plan_fingerprint",
            "portfolio_fingerprint",
            "snapshot_fingerprint",
            "warmup_receipt_fingerprint",
            "warmup_result_fingerprint",
            "warmup_tape_fingerprint",
            "warmup_event_count",
            "warmup_source_artifact_digests",
            "warmup_cursor_event_id",
            "warmup_cursor_sequence",
            "warmup_cursor_event_fingerprint",
            "processed_checkpoint_fingerprint",
            "processed_prefix_fingerprint",
            "before_event_fingerprint",
            "engine_input_fingerprint",
            "runtime_input_bundle_digest",
            "native_event_stream_digest",
            "native_event_stream_adapter_version",
            "components",
            "processed_events",
        }
        if not isinstance(value, Mapping) or set(value) != fields:
            raise ValueError("forward bootstrap fields are invalid")
        source_digests = value["warmup_source_artifact_digests"]
        components = value["components"]
        events = value["processed_events"]
        if (
            not isinstance(source_digests, list)
            or not isinstance(components, list)
            or not isinstance(events, list)
        ):
            raise ValueError("forward bootstrap collection fields are invalid")
        return cls(
            schema=value["schema"],
            instance_id=value["instance_id"],
            execution_plan_fingerprint=value["execution_plan_fingerprint"],
            portfolio_fingerprint=value["portfolio_fingerprint"],
            snapshot_fingerprint=value["snapshot_fingerprint"],
            warmup_receipt_fingerprint=value["warmup_receipt_fingerprint"],
            warmup_result_fingerprint=value["warmup_result_fingerprint"],
            warmup_tape_fingerprint=value["warmup_tape_fingerprint"],
            warmup_event_count=value["warmup_event_count"],
            warmup_source_artifact_digests=tuple(source_digests),
            warmup_cursor_event_id=value["warmup_cursor_event_id"],
            warmup_cursor_sequence=value["warmup_cursor_sequence"],
            warmup_cursor_event_fingerprint=value["warmup_cursor_event_fingerprint"],
            processed_checkpoint_fingerprint=value["processed_checkpoint_fingerprint"],
            processed_prefix_fingerprint=value["processed_prefix_fingerprint"],
            before_event_fingerprint=value["before_event_fingerprint"],
            engine_input_fingerprint=value["engine_input_fingerprint"],
            runtime_input_bundle_digest=value["runtime_input_bundle_digest"],
            native_event_stream_digest=value["native_event_stream_digest"],
            native_event_stream_adapter_version=value["native_event_stream_adapter_version"],
            components=tuple(
                NautilusForwardBootstrapComponent.from_wire(item) for item in components
            ),
            processed_events=tuple(
                NautilusForwardBootstrapEvent.from_wire(item) for item in events
            ),
        )

    @classmethod
    def build(
        cls,
        *,
        execution_plan: ResolvedForwardExecutionPlan,
        snapshot: DataSnapshot,
        warmup_receipt: ForwardWarmupReceipt,
        warmup_tape: FrozenEventTapeArtifactResolution,
        processed_prefix: ForwardProcessedEventPrefix,
        engine_input: NautilusEngineInput,
        runtime_input_bundle_digest: str,
        native_event_stream: NautilusNativeEventStreamArtifactReference,
    ) -> NautilusForwardRuntimeBootstrap:
        """Bind authenticated domain inputs and exact RC engine artifacts."""

        from app.strategy_lab_v2.artifacts import artifact_content_digest
        from app.strategy_lab_v2.contracts import DataSnapshot
        from app.strategy_lab_v2.event_tape_artifacts import FrozenEventTapeArtifactResolution
        from app.strategy_lab_v2.forward_execution_plan_resolution import (
            ResolvedForwardExecutionPlan,
        )
        from app.strategy_lab_v2.forward_processed_prefix import ForwardProcessedEventPrefix
        from app.strategy_lab_v2.forward_warmup import ForwardWarmupReceipt
        from app.strategy_lab_v2.nautilus_engine_input import NautilusEngineInput
        from app.strategy_lab_v2.nautilus_runtime_bundle import (
            NautilusNativeEventStreamArtifactReference,
        )

        if not isinstance(execution_plan, ResolvedForwardExecutionPlan):
            raise TypeError("execution_plan must use ResolvedForwardExecutionPlan")
        if not isinstance(snapshot, DataSnapshot):
            raise TypeError("snapshot must use DataSnapshot")
        if not isinstance(warmup_receipt, ForwardWarmupReceipt):
            raise TypeError("warmup_receipt must use ForwardWarmupReceipt")
        if not isinstance(warmup_tape, FrozenEventTapeArtifactResolution):
            raise TypeError("warmup_tape must use FrozenEventTapeArtifactResolution")
        if not isinstance(processed_prefix, ForwardProcessedEventPrefix):
            raise TypeError("processed_prefix must use ForwardProcessedEventPrefix")
        if not isinstance(engine_input, NautilusEngineInput):
            raise TypeError("engine_input must use NautilusEngineInput")
        if not isinstance(native_event_stream, NautilusNativeEventStreamArtifactReference):
            raise TypeError(
                "native_event_stream must use NautilusNativeEventStreamArtifactReference"
            )
        require_sha256_digest(
            runtime_input_bundle_digest,
            field_name="runtime_input_bundle_digest",
        )

        instance = execution_plan.instance
        if (
            snapshot.fingerprint != instance.warmup_snapshot_fingerprint
            or warmup_receipt.warmup_snapshot_fingerprint != snapshot.fingerprint
            or warmup_receipt.instance_id != instance.instance_id
        ):
            raise ValueError("forward bootstrap warm-up receipt and frozen snapshot differ")
        if warmup_tape.snapshot_fingerprint != snapshot.fingerprint:
            raise ValueError("forward bootstrap tape differs from the frozen warm-up snapshot")
        if (
            engine_input.data_snapshot_fingerprint != snapshot.fingerprint
            or engine_input.portfolio.fingerprint != execution_plan.portfolio.fingerprint
        ):
            raise ValueError(
                "forward bootstrap engine input differs from its snapshot or portfolio"
            )
        if (
            engine_input.event_tape.source_tape_fingerprint != warmup_tape.tape.fingerprint
            or native_event_stream.source_tape_fingerprint != warmup_tape.tape.fingerprint
            or native_event_stream.event_count != warmup_tape.tape.event_count
            or native_event_stream.adapter_version != engine_input.event_tape.adapter_version
        ):
            raise ValueError("forward bootstrap native tape is not the exact frozen warm-up tape")
        if (
            processed_prefix.instance_id != instance.instance_id
            or processed_prefix.warmup_receipt_fingerprint != warmup_receipt.fingerprint
        ):
            raise ValueError(
                "forward bootstrap processed prefix differs from its instance or warm-up"
            )
        if processed_prefix.manifest_fingerprint not in {
            component.resolved_package.manifest.fingerprint
            for component in execution_plan.components.values()
        }:
            raise ValueError("forward bootstrap prefix manifest is not in the resolved plan")

        warmup_events = {event.event_id: event for event in warmup_tape.tape.events}
        if warmup_receipt.final_event_id is None:
            if warmup_receipt.final_event_sequence != 0 or warmup_events:
                raise ValueError("empty warm-up receipt differs from the frozen event tape")
        else:
            cursor = warmup_events.get(warmup_receipt.final_event_id)
            if cursor is None or cursor.sequence != warmup_receipt.final_event_sequence:
                raise ValueError("warm-up cursor differs from the frozen event tape")
        if any(
            event.canonical_event.sequence <= warmup_receipt.final_event_sequence
            for event in processed_prefix.events
        ):
            raise ValueError("processed prefix does not follow the frozen warm-up cursor")
        if set(warmup_events).intersection(
            event.canonical_event.event_id for event in processed_prefix.events
        ):
            raise ValueError("warm-up and processed prefix contain duplicate event identities")

        expected_component_ids = set(execution_plan.components)
        native_bindings = {item.component_id: item for item in engine_input.strategy_bindings}
        if set(native_bindings) != expected_component_ids:
            raise ValueError("forward bootstrap engine bindings do not cover its execution plan")
        component_rows: list[NautilusForwardBootstrapComponent] = []
        for component_id, resolved in execution_plan.components.items():
            native_binding = native_bindings[component_id]
            binding = resolved.binding
            if (
                native_binding.strategy_fingerprint != binding.strategy_fingerprint
                or native_binding.strategy_source_digest != resolved.strategy.source_digest
                or native_binding.strategy_manifest_fingerprint
                != resolved.resolved_package.manifest.fingerprint
                or native_binding.parameters_digest != content_digest(binding.parameters)
            ):
                raise ValueError(
                    f"forward bootstrap engine binding differs for component {component_id!r}"
                )
            component_rows.append(
                NautilusForwardBootstrapComponent(
                    component_id=component_id,
                    execution_binding_fingerprint=binding.fingerprint,
                    resolved_component_fingerprint=resolved.fingerprint,
                    strategy_fingerprint=resolved.strategy.fingerprint,
                    package_fingerprint=resolved.package.fingerprint,
                    package_archive_digest=resolved.resolved_package.archive_manifest.content_digest,
                    dependency_lock_digest=artifact_content_digest(
                        resolved.resolved_package.dependency_lock
                    ),
                    manifest_fingerprint=resolved.resolved_package.manifest.fingerprint,
                    source_digest=content_digest(resolved.resolved_package.source),
                    parameters_digest=content_digest(binding.parameters),
                    random_seed=binding.random_seed,
                )
            )
        snapshot_source_digests = tuple(
            sorted({series.content_digest for series in snapshot.series})
        )
        if not set(warmup_tape.source_artifact_digests).issubset(snapshot_source_digests):
            raise ValueError("warm-up tape references source artifacts outside its snapshot")
        return cls(
            instance_id=instance.instance_id,
            execution_plan_fingerprint=execution_plan.plan.fingerprint,
            portfolio_fingerprint=execution_plan.portfolio.fingerprint,
            snapshot_fingerprint=snapshot.fingerprint,
            warmup_receipt_fingerprint=warmup_receipt.fingerprint,
            warmup_result_fingerprint=warmup_receipt.warmup_result_fingerprint,
            warmup_tape_fingerprint=warmup_tape.tape.fingerprint,
            warmup_event_count=warmup_tape.tape.event_count,
            warmup_source_artifact_digests=warmup_tape.source_artifact_digests,
            warmup_cursor_event_id=warmup_receipt.final_event_id,
            warmup_cursor_sequence=warmup_receipt.final_event_sequence,
            warmup_cursor_event_fingerprint=warmup_receipt.final_event_fingerprint,
            processed_checkpoint_fingerprint=processed_prefix.pre_event_checkpoint_fingerprint,
            processed_prefix_fingerprint=processed_prefix.fingerprint,
            before_event_fingerprint=processed_prefix.before_event_fingerprint,
            engine_input_fingerprint=engine_input.fingerprint,
            runtime_input_bundle_digest=runtime_input_bundle_digest,
            native_event_stream_digest=native_event_stream.artifact.content_digest,
            native_event_stream_adapter_version=native_event_stream.adapter_version,
            components=tuple(component_rows),
            processed_events=tuple(
                NautilusForwardBootstrapEvent(
                    canonical_event=payload.canonical_event,
                    market_event=payload.market_event,
                    verified_source_digest=payload.verified_source_digest,
                )
                for payload in processed_prefix.events
            ),
        )


@dataclass(frozen=True, slots=True)
class NautilusForwardBootstrapArtifactReference:
    """Content-addressed immutable bytes for one exact forward bootstrap."""

    artifact: ArtifactManifest
    bootstrap_fingerprint: str
    path: Path

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, ArtifactManifest):
            raise TypeError("artifact must use ArtifactManifest")
        require_sha256_digest(self.bootstrap_fingerprint, field_name="bootstrap_fingerprint")
        if not isinstance(self.path, Path) or not self.path.is_absolute():
            raise ValueError("bootstrap artifact path must be absolute")
        if self.artifact.media_type != NAUTILUS_FORWARD_BOOTSTRAP_MEDIA_TYPE:
            raise ValueError("bootstrap artifact media type is invalid")
        if self.artifact.schema_version != NAUTILUS_FORWARD_BOOTSTRAP_SCHEMA:
            raise ValueError("bootstrap artifact schema is invalid")


def materialize_nautilus_forward_bootstrap_artifact(
    store: LocalArtifactStore,
    bootstrap: NautilusForwardRuntimeBootstrap,
) -> NautilusForwardBootstrapArtifactReference:
    """Publish exact bootstrap bytes under an immutable verified content address."""

    if not isinstance(store, LocalArtifactStore):
        raise TypeError("store must be a LocalArtifactStore")
    if not isinstance(bootstrap, NautilusForwardRuntimeBootstrap):
        raise TypeError("bootstrap must use NautilusForwardRuntimeBootstrap")
    encoded = bootstrap.to_json_bytes()
    digest = artifact_content_digest(encoded)
    artifact = ArtifactManifest(
        content_digest=digest,
        byte_length=len(encoded),
        media_type=NAUTILUS_FORWARD_BOOTSTRAP_MEDIA_TYPE,
        schema_version=NAUTILUS_FORWARD_BOOTSTRAP_SCHEMA,
        storage_key=digest,
        retention_class=ArtifactRetention.PINNED_INPUT,
    )
    publication = store.publish(artifact, encoded)
    if publication.decision not in {ArtifactStoreDecision.WRITTEN, ArtifactStoreDecision.REUSED}:
        raise ValueError("forward bootstrap artifact publication failed")
    path = store.path_for(artifact.storage_key)
    # Verify published bytes through the store boundary before handing a host
    # path to the sandbox planner.
    if store.read(artifact.storage_key) != encoded:
        raise ValueError("published forward bootstrap artifact differs from its source")
    return NautilusForwardBootstrapArtifactReference(
        artifact=artifact,
        bootstrap_fingerprint=bootstrap.fingerprint,
        path=path,
    )


__all__ = [
    "NAUTILUS_FORWARD_BOOTSTRAP_SCHEMA",
    "NAUTILUS_FORWARD_BOOTSTRAP_MEDIA_TYPE",
    "MAX_NAUTILUS_FORWARD_BOOTSTRAP_BYTES",
    "NautilusForwardBootstrapComponent",
    "NautilusForwardBootstrapEvent",
    "NautilusForwardBootstrapArtifactReference",
    "NautilusForwardRuntimeBootstrap",
    "materialize_nautilus_forward_bootstrap_artifact",
]
