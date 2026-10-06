"""Bounded canonical join artifacts for immutable forward warm-up."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from app.strategy_lab_v2.artifact_store import ArtifactStoreDecision, LocalArtifactStore
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import ArtifactManifest, ArtifactRetention, DataSnapshot
from app.strategy_lab_v2.event_tape import select_snapshot_series
from app.strategy_lab_v2.event_tape_artifacts import (
    FrozenEventTapeStreamResolution,
    iter_verified_event_tape_stream,
    materialize_frozen_event_tape_stream,
)
from app.strategy_lab_v2.forward_warmup import ForwardWarmupReceipt
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.nautilus_forward_delivery import VerifiedForwardMarketPayload
from app.strategy_lab_v2.sdk import MarketEvent, StrategySdkManifest
from strategy_runtime.protocol import _decode_value, _encode_value

FORWARD_WARMUP_PAYLOAD_STREAM_MEDIA_TYPE = "application/x-ndjson"
FORWARD_WARMUP_PAYLOAD_STREAM_SCHEMA = "strategy-lab.forward-warmup-payload-stream.v1"
_MAX_ROW_BYTES = 1_048_576
_MAX_SPOOL_BYTES = 16 * 1024 * 1024 * 1024


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("forward warm-up timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _encode_payload(payload: VerifiedForwardMarketPayload) -> bytes:
    canonical = payload.canonical_event
    market = payload.market_event
    value = {
        "canonical_event": {
            "arrived_at": canonical.arrived_at.isoformat(timespec="microseconds"),
            "correction_of": canonical.correction_of,
            "event_id": canonical.event_id,
            "event_time": canonical.event_time.isoformat(timespec="microseconds"),
            "sequence": canonical.sequence,
            "source_digest": canonical.source_digest,
        },
        "market_event": {
            "dependency_id": market.dependency_id,
            "event_id": market.event_id,
            "event_time": market.event_time.isoformat(timespec="microseconds"),
            "instrument_id": market.instrument_id,
            "sequence": market.sequence,
            "values": _encode_value(market.values),
        },
        "verified_source_digest": payload.verified_source_digest,
    }
    return json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True).encode()


def _decode_payload(data: bytes) -> VerifiedForwardMarketPayload:
    try:
        value = json.loads(data)
        canonical_value = value["canonical_event"]
        market_value = value["market_event"]
        canonical = CanonicalForwardEvent(
            event_id=canonical_value["event_id"],
            sequence=canonical_value["sequence"],
            event_time=datetime.fromisoformat(canonical_value["event_time"]),
            arrived_at=datetime.fromisoformat(canonical_value["arrived_at"]),
            source_digest=canonical_value["source_digest"],
            correction_of=canonical_value["correction_of"],
        )
        decoded_values = _decode_value(market_value["values"])
        if not isinstance(decoded_values, Mapping):
            raise ValueError("market values must be a mapping")
        market = MarketEvent(
            dependency_id=market_value["dependency_id"],
            event_id=market_value["event_id"],
            instrument_id=market_value["instrument_id"],
            event_time=datetime.fromisoformat(market_value["event_time"]),
            sequence=market_value["sequence"],
            values=decoded_values,
        )
        return VerifiedForwardMarketPayload(
            canonical,
            market,
            value["verified_source_digest"],
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("forward warm-up payload stream contains an invalid row") from error


@dataclass(frozen=True, slots=True)
class ForwardWarmupStreamResolution:
    """Pinned disk-backed tape and canonical payload streams through one receipt."""

    snapshot_fingerprint: str
    manifest_fingerprint: str
    complete_source_tape_fingerprint: str
    warmup_receipt_fingerprint: str
    cursor_event_id: str
    cursor_event_fingerprint: str
    event_count: int
    tape: FrozenEventTapeStreamResolution
    payload_artifact: ArtifactManifest

    def __post_init__(self) -> None:
        for name in (
            "snapshot_fingerprint",
            "manifest_fingerprint",
            "complete_source_tape_fingerprint",
            "warmup_receipt_fingerprint",
            "cursor_event_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        if not isinstance(self.cursor_event_id, str) or not self.cursor_event_id.strip():
            raise ValueError("warm-up cursor event id must not be empty")
        if (
            not isinstance(self.event_count, int)
            or isinstance(self.event_count, bool)
            or self.event_count < 1
        ):
            raise ValueError("warm-up event_count must be a positive integer")
        if not isinstance(self.tape, FrozenEventTapeStreamResolution):
            raise TypeError("tape must use FrozenEventTapeStreamResolution")
        if self.tape.event_count != self.event_count:
            raise ValueError("warm-up tape and canonical stream counts differ")
        if (
            self.tape.snapshot_fingerprint != self.snapshot_fingerprint
            or self.tape.manifest_fingerprint != self.manifest_fingerprint
        ):
            raise ValueError("warm-up tape differs from its frozen snapshot or manifest")
        if not isinstance(self.payload_artifact, ArtifactManifest):
            raise TypeError("payload_artifact must use ArtifactManifest")
        if (
            self.payload_artifact.media_type != FORWARD_WARMUP_PAYLOAD_STREAM_MEDIA_TYPE
            or self.payload_artifact.schema_version != FORWARD_WARMUP_PAYLOAD_STREAM_SCHEMA
            or self.payload_artifact.retention_class is not ArtifactRetention.PINNED_INPUT
        ):
            raise ValueError("forward warm-up payload artifact contract is invalid")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def materialize_forward_warmup_stream(
    store: LocalArtifactStore,
    *,
    snapshot: DataSnapshot,
    manifest: StrategySdkManifest,
    complete_tape: FrozenEventTapeStreamResolution,
    payloads: Iterable[VerifiedForwardMarketPayload],
    receipt: ForwardWarmupReceipt,
    before_event: CanonicalForwardEvent,
    max_row_bytes: int = _MAX_ROW_BYTES,
    max_spool_bytes: int = _MAX_SPOOL_BYTES,
) -> ForwardWarmupStreamResolution:
    """Join canonical identities to a frozen tape using disk-bounded SQLite.

    The join rejects corrections, duplicate IDs/sequences, missing or extra
    canonical rows, invalid dependencies, source mismatches, and a cursor that
    is absent or does not precede the current delivery. It publishes selected
    payload and tape prefixes only after the complete join verifies.
    """

    if not isinstance(store, LocalArtifactStore):
        raise TypeError("store must be a LocalArtifactStore")
    if not isinstance(snapshot, DataSnapshot) or not isinstance(manifest, StrategySdkManifest):
        raise TypeError("snapshot and manifest must use their frozen domain contracts")
    if not isinstance(complete_tape, FrozenEventTapeStreamResolution):
        raise TypeError("complete_tape must use FrozenEventTapeStreamResolution")
    if not isinstance(receipt, ForwardWarmupReceipt):
        raise TypeError("receipt must use ForwardWarmupReceipt")
    if not isinstance(before_event, CanonicalForwardEvent):
        raise TypeError("before_event must use CanonicalForwardEvent")
    if (
        complete_tape.snapshot_fingerprint != snapshot.fingerprint
        or complete_tape.manifest_fingerprint != manifest.fingerprint
        or receipt.warmup_snapshot_fingerprint != snapshot.fingerprint
    ):
        raise ValueError("warm-up join inputs differ from the receipt's frozen snapshot")
    if receipt.final_event_id is None or receipt.final_event_fingerprint is None:
        raise ValueError("forward warm-up receipt must pin an exact final event")
    if not isinstance(payloads, Iterable) or isinstance(payloads, str | bytes):
        raise TypeError("payloads must be a one-pass iterable of verified canonical rows")
    if not isinstance(max_row_bytes, int) or isinstance(max_row_bytes, bool) or max_row_bytes < 1:
        raise ValueError("max_row_bytes must be positive")
    if (
        not isinstance(max_spool_bytes, int)
        or isinstance(max_spool_bytes, bool)
        or max_spool_bytes < 1_048_576
    ):
        raise ValueError("max_spool_bytes must be at least 1 MiB")

    dependencies = {item.dependency_id: item for item in manifest.data_dependencies}
    if not dependencies:
        raise ValueError("warm-up manifest must declare dependencies")
    dependency_coverage = {
        dependency_id: select_snapshot_series(snapshot, dependency)
        for dependency_id, dependency in dependencies.items()
    }
    payload_digest = hashlib.sha256()
    payload_bytes = 0
    selected_count = 0
    with tempfile.TemporaryDirectory(prefix="strategy-lab-forward-warmup-") as workspace:
        db_path = f"{workspace}/canonical-join.sqlite3"
        with sqlite3.connect(db_path) as database:
            database.execute(
                "CREATE TABLE payloads (event_id TEXT PRIMARY KEY, event_time TEXT NOT NULL, "
                "sequence INTEGER NOT NULL UNIQUE, dependency_id TEXT NOT NULL, "
                "instrument_id TEXT NOT NULL, values_json TEXT NOT NULL, wire BLOB NOT NULL, "
                "selected INTEGER NOT NULL DEFAULT 0)"
            )
            for payload in payloads:
                if not isinstance(payload, VerifiedForwardMarketPayload):
                    raise TypeError("canonical payload iterator yielded an invalid row")
                canonical = payload.canonical_event
                market = payload.market_event
                dependency = dependencies.get(market.dependency_id)
                if dependency is None:
                    raise ValueError("canonical warm-up payload uses an undeclared dependency")
                _series, effective_start, effective_end = dependency_coverage[market.dependency_id]
                if (
                    canonical.correction_of is not None
                    or dependency.requirement.instrument_id != market.instrument_id
                    or set(market.values) != set(dependency.fields)
                    or not effective_start <= market.event_time < effective_end
                ):
                    raise ValueError("canonical warm-up payload is outside its declared dependency")
                wire = _encode_payload(payload)
                if len(wire) > max_row_bytes:
                    raise ValueError("canonical warm-up payload exceeds its configured row bound")
                payload_bytes += len(wire) + 1
                if payload_bytes > max_spool_bytes:
                    raise ValueError("canonical warm-up payload stream exceeds its spool limit")
                time_key = _utc(canonical.event_time).isoformat(timespec="microseconds")
                values_wire = json.dumps(
                    _encode_value(market.values),
                    allow_nan=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                try:
                    database.execute(
                        "INSERT INTO payloads(event_id,event_time,sequence,dependency_id,"
                        "instrument_id,values_json,wire) VALUES(?,?,?,?,?,?,?)",
                        (
                            canonical.event_id,
                            time_key,
                            canonical.sequence,
                            market.dependency_id,
                            market.instrument_id,
                            values_wire,
                            wire,
                        ),
                    )
                except sqlite3.IntegrityError as error:
                    raise ValueError(
                        "canonical warm-up IDs and sequences must be unique"
                    ) from error

            cursor_row = database.execute(
                "SELECT wire,event_time,sequence FROM payloads WHERE event_id=?",
                (receipt.final_event_id,),
            ).fetchone()
            if cursor_row is None:
                raise ValueError("canonical warm-up payloads omit the exact durable cursor")
            cursor_payload = _decode_payload(cursor_row[0])
            if (
                content_digest(cursor_payload.canonical_event) != receipt.final_event_fingerprint
                or cursor_payload.canonical_event.sequence != receipt.final_event_sequence
                or (
                    cursor_payload.canonical_event.event_time,
                    cursor_payload.canonical_event.sequence,
                )
                >= (before_event.event_time, before_event.sequence)
            ):
                raise ValueError("canonical warm-up cursor differs from its durable receipt")
            cursor_key = (cursor_row[1], cursor_row[2])
            database.execute(
                "UPDATE payloads SET selected=1 WHERE (event_time,sequence) <= (?,?)",
                cursor_key,
            )
            source_count = int(database.execute("SELECT count(*) FROM payloads").fetchone()[0])
            if source_count != complete_tape.event_count:
                raise ValueError("canonical payloads do not exactly cover frozen snapshot events")

            tape_count = 0
            for event in iter_verified_event_tape_stream(complete_tape, store):
                row = database.execute(
                    "SELECT dependency_id,instrument_id,event_time,values_json FROM payloads "
                    "WHERE event_id=?",
                    (event.event_id,),
                ).fetchone()
                if row is None or (
                    row[0] != event.dependency_id
                    or row[1] != event.instrument_id
                    or row[2] != _utc(event.event_time).isoformat(timespec="microseconds")
                    or _decode_value(json.loads(row[3])) != event.values
                ):
                    raise ValueError("canonical warm-up payload differs from its frozen tape row")
                tape_count += 1
            if tape_count != source_count:
                raise ValueError("canonical warm-up join did not cover the exact frozen tape")

            selected_count = int(
                database.execute("SELECT count(*) FROM payloads WHERE selected=1").fetchone()[0]
            )
            if selected_count < 1:
                raise ValueError("canonical warm-up prefix is empty")
            output_path = f"{workspace}/canonical-warmup.ndjson"
            selected_payload_bytes = 0
            with open(output_path, "wb") as output:
                for (wire,) in database.execute(
                    "SELECT wire FROM payloads WHERE selected=1 ORDER BY event_time,sequence"
                ):
                    line = wire + b"\n"
                    output.write(line)
                    payload_digest.update(line)
                    selected_payload_bytes += len(line)
                output.flush()
                os.fsync(output.fileno())

            # Build the source-tape prefix in canonical selection order without
            # retaining either event rows or a complete identity map in RAM.
            def selected_tape_events() -> Iterator[MarketEvent]:
                for event in iter_verified_event_tape_stream(complete_tape, store):
                    if database.execute(
                        "SELECT 1 FROM payloads WHERE event_id=? AND selected=1",
                        (event.event_id,),
                    ).fetchone():
                        yield event

            prefix_tape = materialize_frozen_event_tape_stream(
                store,
                snapshot=snapshot,
                manifest=manifest,
                events=selected_tape_events(),
                source_artifact_digests=complete_tape.source_artifact_digests,
            )
            payload_manifest = ArtifactManifest(
                content_digest=f"sha256:{payload_digest.hexdigest()}",
                byte_length=selected_payload_bytes,
                media_type=FORWARD_WARMUP_PAYLOAD_STREAM_MEDIA_TYPE,
                schema_version=FORWARD_WARMUP_PAYLOAD_STREAM_SCHEMA,
                storage_key=f"sha256:{payload_digest.hexdigest()}",
                retention_class=ArtifactRetention.PINNED_INPUT,
            )
            publication = store.publish_file(payload_manifest, output_path)
            if publication.decision not in {
                ArtifactStoreDecision.WRITTEN,
                ArtifactStoreDecision.REUSED,
            }:
                raise ValueError("canonical warm-up payload artifact publication failed")

    return ForwardWarmupStreamResolution(
        snapshot_fingerprint=snapshot.fingerprint,
        manifest_fingerprint=manifest.fingerprint,
        complete_source_tape_fingerprint=complete_tape.tape_fingerprint,
        warmup_receipt_fingerprint=receipt.fingerprint,
        cursor_event_id=receipt.final_event_id,
        cursor_event_fingerprint=receipt.final_event_fingerprint,
        event_count=selected_count,
        tape=prefix_tape,
        payload_artifact=payload_manifest,
    )


def iter_verified_forward_warmup_payloads(
    resolution: ForwardWarmupStreamResolution,
    store: LocalArtifactStore,
    *,
    max_row_bytes: int = _MAX_ROW_BYTES,
) -> Iterable[VerifiedForwardMarketPayload]:
    """Verify a canonical warm-up artifact fully before returning a second-pass iterator."""

    if not isinstance(resolution, ForwardWarmupStreamResolution):
        raise TypeError("resolution must use ForwardWarmupStreamResolution")
    if not isinstance(max_row_bytes, int) or isinstance(max_row_bytes, bool) or max_row_bytes < 1:
        raise ValueError("max_row_bytes must be positive")
    digest = hashlib.sha256()
    count = 0
    byte_count = 0
    previous: tuple[datetime, int] | None = None
    cursor_found = False
    last_event_id: str | None = None
    with store.open_verified(
        resolution.payload_artifact.storage_key,
        max_bytes=resolution.payload_artifact.byte_length,
    ) as source:
        while line := source.readline(max_row_bytes + 2):
            if len(line) > max_row_bytes + 1 or not line.endswith(b"\n"):
                raise ValueError("forward warm-up payload row exceeds its configured bound")
            digest.update(line)
            byte_count += len(line)
            payload = _decode_payload(line[:-1])
            canonical = payload.canonical_event
            key = (canonical.event_time, canonical.sequence)
            if previous is not None and key <= previous:
                raise ValueError("forward warm-up payload stream ordering is invalid")
            previous = key
            if canonical.correction_of is not None:
                raise ValueError("corrections cannot enter immutable forward warm-up")
            if canonical.event_id == resolution.cursor_event_id:
                if content_digest(canonical) != resolution.cursor_event_fingerprint:
                    raise ValueError("forward warm-up cursor differs from its pinned fingerprint")
                cursor_found = True
            last_event_id = canonical.event_id
            count += 1
    if (
        count != resolution.event_count
        or byte_count != resolution.payload_artifact.byte_length
        or f"sha256:{digest.hexdigest()}" != resolution.payload_artifact.content_digest
        or not cursor_found
        or last_event_id != resolution.cursor_event_id
    ):
        raise ValueError("forward warm-up payload artifact differs from its manifest")

    def rows() -> Iterator[VerifiedForwardMarketPayload]:
        with store.open_verified(
            resolution.payload_artifact.storage_key,
            max_bytes=resolution.payload_artifact.byte_length,
        ) as source:
            while line := source.readline(max_row_bytes + 2):
                yield _decode_payload(line[:-1])

    return rows()


__all__ = [
    "FORWARD_WARMUP_PAYLOAD_STREAM_MEDIA_TYPE",
    "FORWARD_WARMUP_PAYLOAD_STREAM_SCHEMA",
    "ForwardWarmupStreamResolution",
    "iter_verified_forward_warmup_payloads",
    "materialize_forward_warmup_stream",
]
