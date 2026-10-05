"""Resolve verified snapshot artifacts into the immutable replay event tape.

The provider platform owns Parquet/Arrow schema and decoding. This module owns
the local content-addressed read boundary and validates decoded rows against
the frozen snapshot and one strategy SDK manifest without fetching or
inferring market data.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, BinaryIO, Protocol

from app.strategy_lab_v2.artifact_store import ArtifactStoreDecision, LocalArtifactStore
from app.strategy_lab_v2.canonical import (
    canonical_json,
    content_digest,
    freeze_json,
    require_sha256_digest,
)
from app.strategy_lab_v2.contracts import (
    ArtifactManifest,
    ArtifactRetention,
    DataSeriesManifest,
    DataSnapshot,
)
from app.strategy_lab_v2.event_tape import (
    EVENT_TAPE_DEFINITION_VERSION,
    EventTapeBinding,
    FrozenEventTape,
    bind_event_tape,
    select_snapshot_series,
)
from app.strategy_lab_v2.sdk import MarketEvent, StrategySdkManifest
from strategy_runtime.protocol import _decode_value, _encode_value

FROZEN_EVENT_TAPE_STREAM_MEDIA_TYPE = "application/x-ndjson"
FROZEN_EVENT_TAPE_STREAM_SCHEMA = "strategy-lab.frozen-event-tape-stream.v1"
_DEFAULT_STREAM_EVENT_BYTES = 1_048_576
_DEFAULT_STREAM_SPOOL_BYTES = 16 * 1024 * 1024 * 1024


def _time_key(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _event_tape_digest_prefix(snapshot_fingerprint: str) -> bytes:
    type_name = f"{FrozenEventTape.__module__}.{FrozenEventTape.__qualname__}"
    return (
        f'["dataclass",{json.dumps(type_name, separators=(",", ":"))},'
        f'[["snapshot_fingerprint",{canonical_json(snapshot_fingerprint)}],'
        '["events",["tuple",['
    ).encode()


def _event_tape_digest_suffix() -> bytes:
    return (
        ']]],["definition_version",' f"{canonical_json(EVENT_TAPE_DEFINITION_VERSION)}" "]]]"
    ).encode()


def _new_event_tape_digest(snapshot_fingerprint: str) -> Any:
    digest = hashlib.sha256()
    digest.update(_event_tape_digest_prefix(snapshot_fingerprint))
    return digest


def _event_time_key(event: MarketEvent) -> str:
    return _time_key(event.event_time)


def _encode_stream_event(event: MarketEvent) -> bytes:
    payload = {
        "dependency_id": event.dependency_id,
        "event_id": event.event_id,
        "event_time": _time_key(event.event_time),
        "instrument_id": event.instrument_id,
        "sequence": event.sequence,
        "values": _encode_value(event.values),
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _decode_stream_event(payload: bytes) -> MarketEvent:
    try:
        item = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("frozen event-tape stream contains malformed JSON") from error
    if not isinstance(item, Mapping) or set(item) != {
        "dependency_id",
        "event_id",
        "event_time",
        "instrument_id",
        "sequence",
        "values",
    }:
        raise ValueError("frozen event-tape stream event fields are invalid")
    timestamp = item["event_time"]
    if not isinstance(timestamp, str):
        raise ValueError("frozen event-tape stream event time must be text")
    try:
        event_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("frozen event-tape stream event time is invalid") from error
    values = _decode_value(item["values"])
    if not isinstance(values, Mapping):
        raise ValueError("frozen event-tape stream values must be a mapping")
    return MarketEvent(
        dependency_id=item["dependency_id"],
        event_id=item["event_id"],
        instrument_id=item["instrument_id"],
        event_time=event_time,
        sequence=item["sequence"],
        values=values,
    )


@dataclass(frozen=True, slots=True)
class FrozenSeriesRow:
    """One decoder-produced source row with stable source identity and ordering."""

    event_id: str
    event_time: datetime
    sequence: int
    values: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, str) or not self.event_id.strip():
            raise ValueError("source event_id must not be empty")
        if not isinstance(self.event_time, datetime):
            raise TypeError("source event_time must be a datetime")
        if self.event_time.tzinfo is None or self.event_time.utcoffset() is None:
            raise ValueError("source event_time must be timezone-aware")
        object.__setattr__(self, "event_time", self.event_time.astimezone(UTC))
        if (
            not isinstance(self.sequence, int)
            or isinstance(self.sequence, bool)
            or self.sequence < 0
        ):
            raise ValueError("source sequence must be a non-negative integer")
        if not isinstance(self.values, Mapping):
            raise TypeError("source values must be a mapping")
        if any(not isinstance(key, str) or not key.strip() for key in self.values):
            raise ValueError("source value names must be non-empty strings")
        frozen_values = freeze_json(self.values)
        if not isinstance(frozen_values, Mapping):
            raise TypeError("source values must be JSON-shaped")
        object.__setattr__(self, "values", frozen_values)


class FrozenSeriesDecoder(Protocol):
    """Injected provider-owned Parquet/Arrow row decoder."""

    def iter_rows(
        self,
        series: DataSeriesManifest,
        source: BinaryIO,
    ) -> Iterable[FrozenSeriesRow]: ...


@dataclass(frozen=True, slots=True)
class FrozenEventTapeArtifactResolution:
    """Verified source artifact lineage and its SDK-bound canonical tape."""

    snapshot_fingerprint: str
    manifest_fingerprint: str
    tape: FrozenEventTape
    binding: EventTapeBinding
    source_artifact_digests: tuple[str, ...]

    def __post_init__(self) -> None:
        require_sha256_digest(self.snapshot_fingerprint, field_name="snapshot_fingerprint")
        require_sha256_digest(self.manifest_fingerprint, field_name="manifest_fingerprint")
        if not isinstance(self.tape, FrozenEventTape):
            raise TypeError("tape must be a FrozenEventTape")
        if not isinstance(self.binding, EventTapeBinding):
            raise TypeError("binding must be an EventTapeBinding")
        if self.tape.snapshot_fingerprint != self.snapshot_fingerprint:
            raise ValueError("resolved tape references a different snapshot")
        if self.binding.event_tape_fingerprint != self.tape.fingerprint:
            raise ValueError("event-tape binding references different tape content")
        if self.binding.snapshot_fingerprint != self.snapshot_fingerprint:
            raise ValueError("event-tape binding references a different snapshot")
        if self.binding.manifest_fingerprint != self.manifest_fingerprint:
            raise ValueError("event-tape binding references a different SDK manifest")
        digests = tuple(self.source_artifact_digests)
        for digest in digests:
            require_sha256_digest(digest, field_name="source_artifact_digest")
        if digests != tuple(sorted(set(digests))):
            raise ValueError("source artifact digests must be unique and ordered")
        object.__setattr__(self, "source_artifact_digests", digests)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class FrozenEventTapeStreamResolution:
    """Disk-backed, content-addressed tape whose events are not retained in RAM."""

    snapshot_fingerprint: str
    manifest_fingerprint: str
    tape_fingerprint: str
    binding: EventTapeBinding
    artifact: ArtifactManifest
    event_count: int
    source_artifact_digests: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("snapshot_fingerprint", "manifest_fingerprint", "tape_fingerprint"):
            require_sha256_digest(getattr(self, name), field_name=name)
        if not isinstance(self.binding, EventTapeBinding):
            raise TypeError("binding must be an EventTapeBinding")
        if self.binding.snapshot_fingerprint != self.snapshot_fingerprint:
            raise ValueError("stream binding references a different snapshot")
        if self.binding.manifest_fingerprint != self.manifest_fingerprint:
            raise ValueError("stream binding references a different SDK manifest")
        if self.binding.event_tape_fingerprint != self.tape_fingerprint:
            raise ValueError("stream binding references different tape content")
        if not isinstance(self.artifact, ArtifactManifest):
            raise TypeError("artifact must be an ArtifactManifest")
        if self.artifact.media_type != FROZEN_EVENT_TAPE_STREAM_MEDIA_TYPE:
            raise ValueError("event-tape stream artifact media type is unsupported")
        if self.artifact.schema_version != FROZEN_EVENT_TAPE_STREAM_SCHEMA:
            raise ValueError("event-tape stream artifact schema is unsupported")
        if self.artifact.retention_class is not ArtifactRetention.PINNED_INPUT:
            raise ValueError("event-tape stream artifacts must use pinned-input retention")
        if (
            not isinstance(self.event_count, int)
            or isinstance(self.event_count, bool)
            or self.event_count <= 0
        ):
            raise ValueError("event_count must be a positive integer")
        if sum(count for _dependency, count in self.binding.dependency_event_counts) != (
            self.event_count
        ):
            raise ValueError("event_count differs from the stream binding")
        digests = tuple(self.source_artifact_digests)
        for digest in digests:
            require_sha256_digest(digest, field_name="source_artifact_digest")
        if digests != tuple(sorted(set(digests))):
            raise ValueError("source artifact digests must be unique and ordered")
        object.__setattr__(self, "source_artifact_digests", digests)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class FrozenEventTapeWindowResolution:
    """A bounded, verified per-dependency tail of one frozen event tape.

    This is the history slice needed to seed declared SDK context windows; it
    is deliberately distinct from the full tape required for Nautilus replay.
    ``through_event_id`` lets a caller bind the slice to an exact completed
    warm-up cursor instead of implicitly using the latest snapshot row.
    """

    snapshot_fingerprint: str
    manifest_fingerprint: str
    tape_fingerprint: str
    source_artifact_digests: tuple[str, ...]
    dependency_event_limits: tuple[tuple[str, int], ...]
    events: tuple[MarketEvent, ...]
    through_event_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("snapshot_fingerprint", "manifest_fingerprint", "tape_fingerprint"):
            require_sha256_digest(getattr(self, name), field_name=name)
        source_digests = tuple(self.source_artifact_digests)
        for digest in source_digests:
            require_sha256_digest(digest, field_name="source_artifact_digest")
        if source_digests != tuple(sorted(set(source_digests))):
            raise ValueError("source artifact digests must be unique and ordered")
        limits = tuple(self.dependency_event_limits)
        if not limits or limits != tuple(sorted(limits)):
            raise ValueError("dependency event limits must be non-empty and ordered")
        if len({dependency_id for dependency_id, _limit in limits}) != len(limits):
            raise ValueError("dependency event limits must have unique dependency ids")
        if any(
            not isinstance(dependency_id, str)
            or not dependency_id.strip()
            or not isinstance(limit, int)
            or isinstance(limit, bool)
            or limit < 1
            for dependency_id, limit in limits
        ):
            raise ValueError("dependency event limits must be positive keyed values")
        if self.through_event_id is not None and (
            not isinstance(self.through_event_id, str) or not self.through_event_id.strip()
        ):
            raise ValueError("through_event_id must be non-empty when provided")
        events = tuple(self.events)
        if not events or any(not isinstance(event, MarketEvent) for event in events):
            raise ValueError("bounded event window must contain MarketEvent values")
        if events != tuple(
            sorted(
                events,
                key=lambda event: (
                    event.event_time,
                    event.sequence,
                    event.dependency_id,
                    event.event_id,
                ),
            )
        ):
            raise ValueError("bounded event window must preserve canonical tape ordering")
        limits_by_dependency = dict(limits)
        counts: dict[str, int] = {}
        event_ids: set[str] = set()
        for event in events:
            if event.event_id in event_ids:
                raise ValueError("bounded event window event ids must be unique")
            event_ids.add(event.event_id)
            if event.dependency_id not in limits_by_dependency:
                raise ValueError("bounded event window contains an undeclared dependency")
            counts[event.dependency_id] = counts.get(event.dependency_id, 0) + 1
            if counts[event.dependency_id] > limits_by_dependency[event.dependency_id]:
                raise ValueError("bounded event window exceeds a dependency lookback")
        if set(counts) != set(limits_by_dependency):
            raise ValueError("bounded event window is missing a declared dependency")
        object.__setattr__(self, "source_artifact_digests", source_digests)
        object.__setattr__(self, "dependency_event_limits", limits)
        object.__setattr__(self, "events", events)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)

    @property
    def events_by_dependency(self) -> Mapping[str, tuple[MarketEvent, ...]]:
        grouped: dict[str, list[MarketEvent]] = {
            dependency_id: [] for dependency_id, _limit in self.dependency_event_limits
        }
        for event in self.events:
            grouped[event.dependency_id].append(event)
        return {dependency_id: tuple(events) for dependency_id, events in grouped.items()}


def _validate_stream_limits(max_event_bytes: int) -> None:
    if (
        not isinstance(max_event_bytes, int)
        or isinstance(max_event_bytes, bool)
        or max_event_bytes < 1
        or max_event_bytes > 64 * 1024 * 1024
    ):
        raise ValueError("max_event_bytes must be between 1 byte and 64 MiB")


def _check_stream_spool_limit(
    database_path: str,
    output_path: str,
    *,
    max_spool_bytes: int,
) -> None:
    observed = sum(
        os.path.getsize(path) for path in (database_path, output_path) if os.path.exists(path)
    )
    if observed > max_spool_bytes:
        raise ValueError("frozen event-tape sort spool exceeds its configured disk bound")


def _iter_artifact_events(
    resolution: FrozenEventTapeStreamResolution,
    store: LocalArtifactStore,
    *,
    max_event_bytes: int,
) -> Iterable[MarketEvent]:
    _validate_stream_limits(max_event_bytes)
    with store.open_verified(
        resolution.artifact.storage_key,
        max_bytes=resolution.artifact.byte_length,
    ) as source:
        while line := source.readline(max_event_bytes + 2):
            if len(line) > max_event_bytes + 1:
                raise ValueError("frozen event-tape stream row exceeds its configured bound")
            if not line.endswith(b"\n"):
                raise ValueError("frozen event-tape stream rows must end with a newline")
            yield _decode_stream_event(line[:-1])


def _verify_stream_semantics(
    resolution: FrozenEventTapeStreamResolution,
    store: LocalArtifactStore,
    *,
    max_event_bytes: int,
) -> None:
    digest = _new_event_tape_digest(resolution.snapshot_fingerprint)
    dependency_counts: dict[str, int] = {}
    previous_by_dependency: dict[str, tuple[datetime, int]] = {}
    prior_sort_key: tuple[datetime, int, str, str] | None = None
    observed = 0
    for event in _iter_artifact_events(resolution, store, max_event_bytes=max_event_bytes):
        sort_key = (event.event_time, event.sequence, event.dependency_id, event.event_id)
        if prior_sort_key is not None and sort_key < prior_sort_key:
            raise ValueError("frozen event-tape stream is not in canonical event order")
        prior_sort_key = sort_key
        previous = previous_by_dependency.get(event.dependency_id)
        if previous is not None and (
            event.sequence <= previous[1] or event.event_time < previous[0]
        ):
            raise ValueError(
                f"dependency {event.dependency_id!r} events must advance sequence and time"
            )
        previous_by_dependency[event.dependency_id] = (event.event_time, event.sequence)
        dependency_counts[event.dependency_id] = dependency_counts.get(event.dependency_id, 0) + 1
        if observed:
            digest.update(b",")
        digest.update(canonical_json(event).encode("utf-8"))
        observed += 1
    digest.update(_event_tape_digest_suffix())
    if observed != resolution.event_count:
        raise ValueError("frozen event-tape stream count differs from its manifest")
    if tuple(sorted(dependency_counts.items())) != resolution.binding.dependency_event_counts:
        raise ValueError("frozen event-tape stream dependency counts differ from its binding")
    if f"sha256:{digest.hexdigest()}" != resolution.tape_fingerprint:
        raise ValueError("frozen event-tape stream differs from its tape fingerprint")


def iter_verified_event_tape_stream(
    resolution: FrozenEventTapeStreamResolution,
    store: LocalArtifactStore,
    *,
    max_event_bytes: int = _DEFAULT_STREAM_EVENT_BYTES,
) -> Iterable[MarketEvent]:
    """Verify a complete tape stream before yielding its events in a second pass.

    The first pass validates the semantic tape fingerprint, ordering, counts,
    and raw artifact digest. A second bounded pass yields rows for a consumer
    which stages them before publishing any execution result.
    """

    if not isinstance(resolution, FrozenEventTapeStreamResolution):
        raise TypeError("resolution must be a FrozenEventTapeStreamResolution")
    if not isinstance(store, LocalArtifactStore):
        raise TypeError("store must be a LocalArtifactStore")
    _verify_stream_semantics(resolution, store, max_event_bytes=max_event_bytes)
    return _iter_artifact_events(resolution, store, max_event_bytes=max_event_bytes)


def select_bounded_verified_event_tape_window(
    resolution: FrozenEventTapeStreamResolution,
    store: LocalArtifactStore,
    manifest: StrategySdkManifest,
    *,
    through_event_id: str | None = None,
    max_event_bytes: int = _DEFAULT_STREAM_EVENT_BYTES,
) -> FrozenEventTapeWindowResolution:
    """Select each dependency's bounded verified tail without retaining its tape.

    The content-addressed stream is fully verified before iteration. Selection
    then retains at most ``lookback_periods + 1`` events per manifest
    dependency, optionally stopping at the exact frozen event that completed
    warm-up. A missing cursor or dependency fails closed.
    """

    if not isinstance(resolution, FrozenEventTapeStreamResolution):
        raise TypeError("resolution must be a FrozenEventTapeStreamResolution")
    if not isinstance(store, LocalArtifactStore):
        raise TypeError("store must be a LocalArtifactStore")
    if not isinstance(manifest, StrategySdkManifest):
        raise TypeError("manifest must be a StrategySdkManifest")
    if resolution.manifest_fingerprint != manifest.fingerprint:
        raise ValueError("frozen event-tape stream belongs to a different SDK manifest")
    if through_event_id is not None and (
        not isinstance(through_event_id, str) or not through_event_id.strip()
    ):
        raise ValueError("through_event_id must be non-empty when provided")

    dependencies = {
        dependency.dependency_id: dependency for dependency in manifest.data_dependencies
    }
    if tuple(sorted(dependencies)) != tuple(
        dependency_id for dependency_id, _count in resolution.binding.dependency_event_counts
    ):
        raise ValueError("frozen event tape does not cover the requested SDK dependencies")
    limits = {
        dependency_id: dependency.lookback_periods + 1
        for dependency_id, dependency in dependencies.items()
    }
    tails: dict[str, deque[MarketEvent]] = {
        dependency_id: deque(maxlen=limit) for dependency_id, limit in limits.items()
    }
    cursor_found = through_event_id is None
    for event in iter_verified_event_tape_stream(
        resolution,
        store,
        max_event_bytes=max_event_bytes,
    ):
        if through_event_id is not None and cursor_found:
            break
        if event.dependency_id not in tails:
            raise ValueError("frozen event tape contains an undeclared dependency")
        tails[event.dependency_id].append(event)
        if through_event_id is not None and event.event_id == through_event_id:
            cursor_found = True

    if not cursor_found:
        raise ValueError("warm-up cursor event is absent from the verified frozen tape")
    if any(not events for events in tails.values()):
        raise ValueError("verified frozen history is missing a declared dependency")
    selected = tuple(
        sorted(
            (event for events in tails.values() for event in events),
            key=lambda event: (
                event.event_time,
                event.sequence,
                event.dependency_id,
                event.event_id,
            ),
        )
    )
    return FrozenEventTapeWindowResolution(
        snapshot_fingerprint=resolution.snapshot_fingerprint,
        manifest_fingerprint=resolution.manifest_fingerprint,
        tape_fingerprint=resolution.tape_fingerprint,
        source_artifact_digests=resolution.source_artifact_digests,
        dependency_event_limits=tuple(sorted(limits.items())),
        events=selected,
        through_event_id=through_event_id,
    )


class FrozenEventTapeArtifactResolver:
    """Stream and verify all snapshot series required by one SDK manifest."""

    def __init__(
        self,
        artifact_store: LocalArtifactStore,
        decoder: FrozenSeriesDecoder,
        *,
        max_artifact_bytes: int | None = None,
    ) -> None:
        if not isinstance(artifact_store, LocalArtifactStore):
            raise TypeError("artifact_store must be a LocalArtifactStore")
        if not callable(getattr(decoder, "iter_rows", None)):
            raise TypeError("decoder must provide iter_rows(series, source)")
        if max_artifact_bytes is not None and (
            not isinstance(max_artifact_bytes, int)
            or isinstance(max_artifact_bytes, bool)
            or max_artifact_bytes < 1
        ):
            raise ValueError("max_artifact_bytes must be a positive integer or None")
        self._artifact_store = artifact_store
        self._decoder = decoder
        self._max_artifact_bytes = max_artifact_bytes

    def resolve(
        self,
        snapshot: DataSnapshot,
        manifest: StrategySdkManifest,
    ) -> FrozenEventTapeStreamResolution:
        """Resolve one snapshot to a verified disk-backed tape by default.

        Event histories may be very large, so the ordinary entry point must
        not retain decoded rows or the complete tape in memory. Small-fixture
        callers that explicitly need an in-memory ``FrozenEventTape`` can use
        :meth:`resolve_materialized`.
        """

        return self.resolve_streaming(snapshot, manifest)

    def resolve_materialized(
        self,
        snapshot: DataSnapshot,
        manifest: StrategySdkManifest,
    ) -> FrozenEventTapeArtifactResolution:
        """Explicit compatibility path that retains the complete tape in RAM."""

        if not isinstance(snapshot, DataSnapshot):
            raise TypeError("snapshot must be a DataSnapshot")
        if not isinstance(manifest, StrategySdkManifest):
            raise TypeError("manifest must be a StrategySdkManifest")

        decoded: dict[str, tuple[FrozenSeriesRow, ...]] = {}
        source_digests: set[str] = set()
        events: list[MarketEvent] = []
        for dependency in manifest.data_dependencies:
            series_candidates, effective_start, effective_end = select_snapshot_series(
                snapshot, dependency
            )
            if not series_candidates:
                raise ValueError(
                    f"snapshot has no matching series for dependency {dependency.dependency_id!r}"
                )
            for series in series_candidates:
                rows = decoded.get(series.content_digest)
                if rows is None:
                    rows = self._read_rows(series)
                    decoded[series.content_digest] = rows
                source_digests.add(series.content_digest)
                for row in rows:
                    if not effective_start <= row.event_time < effective_end:
                        continue
                    missing_fields = set(dependency.fields) - set(row.values)
                    if missing_fields:
                        raise ValueError(
                            f"snapshot row for dependency {dependency.dependency_id!r} "
                            f"is missing declared fields: {', '.join(sorted(missing_fields))}"
                        )
                    selected_values = {name: row.values[name] for name in dependency.fields}
                    events.append(
                        MarketEvent(
                            dependency_id=dependency.dependency_id,
                            event_id=content_digest(
                                {
                                    "dependency_id": dependency.dependency_id,
                                    "source_event_id": row.event_id,
                                }
                            ),
                            instrument_id=series.instrument_id,
                            event_time=row.event_time,
                            sequence=row.sequence,
                            values=selected_values,
                        )
                    )

        tape = FrozenEventTape(snapshot.fingerprint, tuple(events))
        binding = bind_event_tape(tape, snapshot, manifest)
        return FrozenEventTapeArtifactResolution(
            snapshot_fingerprint=snapshot.fingerprint,
            manifest_fingerprint=manifest.fingerprint,
            tape=tape,
            binding=binding,
            source_artifact_digests=tuple(sorted(source_digests)),
        )

    def resolve_bounded_window(
        self,
        snapshot: DataSnapshot,
        manifest: StrategySdkManifest,
        *,
        through_event_id: str | None = None,
        max_event_bytes: int = _DEFAULT_STREAM_EVENT_BYTES,
    ) -> FrozenEventTapeWindowResolution:
        """Resolve only the bounded SDK history tail from a frozen snapshot."""

        resolution = self.resolve_streaming(
            snapshot,
            manifest,
            max_event_bytes=max_event_bytes,
        )
        return select_bounded_verified_event_tape_window(
            resolution,
            self._artifact_store,
            manifest,
            through_event_id=through_event_id,
            max_event_bytes=max_event_bytes,
        )

    def resolve_streaming(
        self,
        snapshot: DataSnapshot,
        manifest: StrategySdkManifest,
        *,
        max_event_bytes: int = _DEFAULT_STREAM_EVENT_BYTES,
        sqlite_cache_kib: int = 4096,
        max_spool_bytes: int = _DEFAULT_STREAM_SPOOL_BYTES,
    ) -> FrozenEventTapeStreamResolution:
        """Resolve snapshot rows to an ordered, disk-spooled event artifact.

        Decoded rows are inserted into a temporary SQLite sort spool with a
        bounded page cache and a unique event-id key. The final canonical tape
        is then serialized one event at a time into a pinned content-addressed
        NDJSON artifact. Memory use is proportional to one decoded event plus
        the SQLite cache, not total tape length.
        """

        if not isinstance(snapshot, DataSnapshot):
            raise TypeError("snapshot must be a DataSnapshot")
        if not isinstance(manifest, StrategySdkManifest):
            raise TypeError("manifest must be a StrategySdkManifest")
        _validate_stream_limits(max_event_bytes)
        if (
            not isinstance(sqlite_cache_kib, int)
            or isinstance(sqlite_cache_kib, bool)
            or sqlite_cache_kib < 64
            or sqlite_cache_kib > 65_536
        ):
            raise ValueError("sqlite_cache_kib must be between 64 KiB and 64 MiB")
        if (
            not isinstance(max_spool_bytes, int)
            or isinstance(max_spool_bytes, bool)
            or max_spool_bytes < 1_048_576
        ):
            raise ValueError("max_spool_bytes must be an integer of at least 1 MiB")

        source_digests: set[str] = set()
        dependency_counts = {item.dependency_id: 0 for item in manifest.data_dependencies}
        dependency_instruments: dict[str, str] = {}
        check_batch_rows = max(1, min(512, max_spool_bytes // max_event_bytes // 8))
        with tempfile.TemporaryDirectory(prefix="strategy-lab-event-tape-") as workspace:
            database_path = f"{workspace}/sort.sqlite3"
            output_path = f"{workspace}/event-tape.ndjson"
            connection = sqlite3.connect(database_path)
            try:
                connection.execute("PRAGMA journal_mode=OFF")
                connection.execute("PRAGMA synchronous=OFF")
                connection.execute("PRAGMA temp_store=FILE")
                connection.execute(f"PRAGMA cache_size=-{sqlite_cache_kib}")
                connection.execute(
                    "CREATE TABLE tape_events ("
                    "event_time TEXT NOT NULL, sequence INTEGER NOT NULL, "
                    "dependency_id TEXT NOT NULL, event_id TEXT NOT NULL, "
                    "wire_event BLOB NOT NULL, "
                    "PRIMARY KEY(event_time, sequence, dependency_id, event_id), "
                    "UNIQUE(event_id)) WITHOUT ROWID"
                )
                pending_rows = 0
                for dependency in manifest.data_dependencies:
                    candidates, effective_start, effective_end = select_snapshot_series(
                        snapshot, dependency
                    )
                    if not candidates:
                        raise ValueError(
                            "snapshot has no matching series for dependency "
                            f"{dependency.dependency_id!r}"
                        )
                    for series in candidates:
                        source_digests.add(series.content_digest)
                        decoded_count = 0
                        with self._artifact_store.open_verified(
                            series.content_digest,
                            max_bytes=self._max_artifact_bytes,
                        ) as source:
                            for row in self._decoder.iter_rows(series, source):
                                if not isinstance(row, FrozenSeriesRow):
                                    raise TypeError(
                                        "frozen series decoder must yield FrozenSeriesRow values"
                                    )
                                if decoded_count >= series.row_count:
                                    raise ValueError(
                                        "decoded snapshot row count exceeds its frozen manifest"
                                    )
                                decoded_count += 1
                                if not series.start <= row.event_time < series.end:
                                    raise ValueError(
                                        "decoded snapshot row falls outside its frozen series interval"
                                    )
                                if not effective_start <= row.event_time < effective_end:
                                    continue
                                missing_fields = set(dependency.fields) - set(row.values)
                                if missing_fields:
                                    raise ValueError(
                                        f"snapshot row for dependency {dependency.dependency_id!r} "
                                        "is missing declared fields: "
                                        f"{', '.join(sorted(missing_fields))}"
                                    )
                                event = MarketEvent(
                                    dependency_id=dependency.dependency_id,
                                    event_id=content_digest(
                                        {
                                            "dependency_id": dependency.dependency_id,
                                            "source_event_id": row.event_id,
                                        }
                                    ),
                                    instrument_id=series.instrument_id,
                                    event_time=row.event_time,
                                    sequence=row.sequence,
                                    values={name: row.values[name] for name in dependency.fields},
                                )
                                prior_instrument = dependency_instruments.setdefault(
                                    dependency.dependency_id, event.instrument_id
                                )
                                if prior_instrument != event.instrument_id:
                                    raise ValueError(
                                        f"dependency {dependency.dependency_id!r} contains "
                                        "multiple instruments"
                                    )
                                wire_event = _encode_stream_event(event)
                                if len(wire_event) > max_event_bytes:
                                    raise ValueError(
                                        "frozen event-tape stream row exceeds its configured bound"
                                    )
                                try:
                                    connection.execute(
                                        "INSERT INTO tape_events "
                                        "(event_time, sequence, dependency_id, event_id, wire_event) "
                                        "VALUES (?, ?, ?, ?, ?)",
                                        (
                                            _event_time_key(event),
                                            event.sequence,
                                            event.dependency_id,
                                            event.event_id,
                                            wire_event,
                                        ),
                                    )
                                except sqlite3.IntegrityError as error:
                                    raise ValueError(
                                        "event ids must be unique within a frozen tape"
                                    ) from error
                                dependency_counts[dependency.dependency_id] += 1
                                pending_rows += 1
                                if pending_rows >= check_batch_rows:
                                    connection.commit()
                                    _check_stream_spool_limit(
                                        database_path,
                                        output_path,
                                        max_spool_bytes=max_spool_bytes,
                                    )
                                    pending_rows = 0
                        if decoded_count != series.row_count:
                            raise ValueError(
                                "decoded snapshot row count differs from its frozen manifest"
                            )

                if any(count == 0 for count in dependency_counts.values()):
                    raise ValueError("every SDK dependency must have frozen events")
                connection.commit()
                _check_stream_spool_limit(
                    database_path,
                    output_path,
                    max_spool_bytes=max_spool_bytes,
                )

                tape_digest = _new_event_tape_digest(snapshot.fingerprint)
                event_count = 0
                previous_by_dependency: dict[str, tuple[str, int]] = {}
                raw_digest = hashlib.sha256()
                byte_length = 0
                with open(output_path, "wb") as output:
                    cursor = connection.execute(
                        "SELECT event_time, sequence, dependency_id, event_id, wire_event "
                        "FROM tape_events "
                        "ORDER BY event_time, sequence, dependency_id, event_id"
                    )
                    for _event_time, sequence, dependency_id, _event_id, wire_event in cursor:
                        event = _decode_stream_event(wire_event)
                        prior = previous_by_dependency.get(dependency_id)
                        if prior is not None and (
                            sequence <= prior[1]
                            or event.event_time
                            < datetime.fromisoformat(prior[0].replace("Z", "+00:00"))
                        ):
                            raise ValueError(
                                f"dependency {dependency_id!r} events must advance sequence and time"
                            )
                        previous_by_dependency[dependency_id] = (_event_time, sequence)
                        if event_count:
                            tape_digest.update(b",")
                        tape_digest.update(canonical_json(event).encode("utf-8"))
                        line = wire_event + b"\n"
                        output.write(line)
                        raw_digest.update(line)
                        byte_length += len(line)
                        event_count += 1
                        if event_count % check_batch_rows == 0:
                            output.flush()
                            _check_stream_spool_limit(
                                database_path,
                                output_path,
                                max_spool_bytes=max_spool_bytes,
                            )
                    tape_digest.update(_event_tape_digest_suffix())
                    output.flush()
                    os.fsync(output.fileno())
            finally:
                connection.close()

            tape_fingerprint = f"sha256:{tape_digest.hexdigest()}"
            dependency_event_counts = tuple(sorted(dependency_counts.items()))
            binding = EventTapeBinding(
                event_tape_fingerprint=tape_fingerprint,
                snapshot_fingerprint=snapshot.fingerprint,
                manifest_fingerprint=manifest.fingerprint,
                dependency_event_counts=dependency_event_counts,
            )
            stream_digest = f"sha256:{raw_digest.hexdigest()}"
            artifact = ArtifactManifest(
                content_digest=stream_digest,
                byte_length=byte_length,
                media_type=FROZEN_EVENT_TAPE_STREAM_MEDIA_TYPE,
                schema_version=FROZEN_EVENT_TAPE_STREAM_SCHEMA,
                storage_key=stream_digest,
                retention_class=ArtifactRetention.PINNED_INPUT,
            )
            publication = self._artifact_store.publish_file(artifact, output_path)
            if publication.decision not in {
                ArtifactStoreDecision.WRITTEN,
                ArtifactStoreDecision.REUSED,
            }:
                raise ValueError("frozen event-tape stream failed content-addressed publication")

        return FrozenEventTapeStreamResolution(
            snapshot_fingerprint=snapshot.fingerprint,
            manifest_fingerprint=manifest.fingerprint,
            tape_fingerprint=tape_fingerprint,
            binding=binding,
            artifact=artifact,
            event_count=event_count,
            source_artifact_digests=tuple(sorted(source_digests)),
        )

    def _read_rows(self, series: DataSeriesManifest) -> tuple[FrozenSeriesRow, ...]:
        rows: list[FrozenSeriesRow] = []
        with self._artifact_store.open_verified(
            series.content_digest,
            max_bytes=self._max_artifact_bytes,
        ) as source:
            for row in self._decoder.iter_rows(series, source):
                if not isinstance(row, FrozenSeriesRow):
                    raise TypeError("frozen series decoder must yield FrozenSeriesRow values")
                if len(rows) >= series.row_count:
                    raise ValueError("decoded snapshot row count exceeds its frozen manifest")
                if not series.start <= row.event_time < series.end:
                    raise ValueError(
                        "decoded snapshot row falls outside its frozen series interval"
                    )
                rows.append(row)
        if len(rows) != series.row_count:
            raise ValueError("decoded snapshot row count differs from its frozen manifest")
        return tuple(rows)


__all__ = [
    "FROZEN_EVENT_TAPE_STREAM_MEDIA_TYPE",
    "FROZEN_EVENT_TAPE_STREAM_SCHEMA",
    "FrozenEventTapeArtifactResolution",
    "FrozenEventTapeArtifactResolver",
    "FrozenEventTapeStreamResolution",
    "FrozenEventTapeWindowResolution",
    "FrozenSeriesDecoder",
    "FrozenSeriesRow",
    "iter_verified_event_tape_stream",
    "select_bounded_verified_event_tape_window",
]
