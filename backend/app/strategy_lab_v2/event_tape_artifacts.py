"""Resolve verified snapshot artifacts into the immutable replay event tape.

The provider platform owns Parquet/Arrow schema and decoding. This module owns
the local content-addressed read boundary and validates decoded rows against
the frozen snapshot and one strategy SDK manifest without fetching or
inferring market data.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, BinaryIO, Protocol

from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.canonical import content_digest, freeze_json, require_sha256_digest
from app.strategy_lab_v2.contracts import DataSeriesManifest, DataSnapshot
from app.strategy_lab_v2.event_tape import (
    EventTapeBinding,
    FrozenEventTape,
    bind_event_tape,
    select_snapshot_series,
)
from app.strategy_lab_v2.sdk import MarketEvent, StrategySdkManifest


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
    ) -> FrozenEventTapeArtifactResolution:
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
    "FrozenEventTapeArtifactResolution",
    "FrozenEventTapeArtifactResolver",
    "FrozenSeriesDecoder",
    "FrozenSeriesRow",
]
