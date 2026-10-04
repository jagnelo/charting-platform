"""Bounded content-addressed storage for native Nautilus execution reports.

Native report columns vary across product types and Nautilus releases. This
artifact preserves each native row as canonical JSON inside a fixed Arrow
schema, while binding the report set to one trial, attempt, portfolio, frozen
snapshot, event tape, and optional evaluation window.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from app.strategy_lab_v2.canonical import require_sha256_digest
from app.strategy_lab_v2.contracts import ArtifactManifest, ArtifactRetention

NAUTILUS_NATIVE_REPORTS_MEDIA_TYPE = (
    "application/vnd.charting.strategy-lab.nautilus-native-reports+parquet"
)
NAUTILUS_NATIVE_REPORTS_SCHEMA = "strategy-lab.nautilus.native-reports.v1"
NAUTILUS_NATIVE_REPORTS_PROTOCOL = "strategy-lab.nautilus.native-reports.v1"
NAUTILUS_NATIVE_REPORT_KINDS = ("account", "fills", "orders", "positions")
MAX_NAUTILUS_NATIVE_REPORTS_BYTES = 1_099_511_627_776  # 1 TiB hard ceiling
_ROW_GROUP_SIZE = 4_096
_ROW_GROUP_BYTES = 8_388_608
_MAX_RECORD_BYTES = 1_048_576
_MAX_JSON_DEPTH = 32
_MAX_JSON_VALUES = 50_000


def _identity(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value


def _bounds(start_ns: Any, end_ns: Any) -> bool:
    return (
        isinstance(start_ns, int)
        and not isinstance(start_ns, bool)
        and start_ns >= 0
        and isinstance(end_ns, int)
        and not isinstance(end_ns, bool)
        and end_ns > start_ns
    )


def _json_value(
    value: Any,
    *,
    _depth: int = 0,
    _remaining_values: list[int] | None = None,
) -> Any:
    """Normalize common pandas/NumPy report scalars without lossy repr()."""

    if _remaining_values is None:
        _remaining_values = [_MAX_JSON_VALUES]
    _remaining_values[0] -= 1
    if _remaining_values[0] < 0:
        raise ValueError("native report row exceeds its normalized-value bound")
    if _depth > _MAX_JSON_DEPTH:
        raise ValueError("native report row exceeds its JSON nesting bound")
    if type(value).__name__ in {"NAType", "NaTType"}:
        return None
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if not math.isfinite(value):
            raise ValueError("native report contains a non-finite number")
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("native report contains a non-finite decimal")
        return format(value, "f")
    if isinstance(value, Enum):
        return _json_value(value.value)
    if isinstance(value, datetime | date):
        if isinstance(value, datetime) and value.tzinfo is None:
            raise ValueError("native report contains a naive datetime")
        return value.isoformat()
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    if isinstance(value, Mapping):
        if len(value) > _MAX_JSON_VALUES:
            raise ValueError("native report mapping exceeds its value bound")
        normalized_mapping: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("native report mapping keys must be strings")
            normalized_mapping[key] = _json_value(
                item,
                _depth=_depth + 1,
                _remaining_values=_remaining_values,
            )
        return normalized_mapping
    if isinstance(value, list | tuple):
        if len(value) > _MAX_JSON_VALUES:
            raise ValueError("native report sequence exceeds its value bound")
        return [
            _json_value(
                item,
                _depth=_depth + 1,
                _remaining_values=_remaining_values,
            )
            for item in value
        ]
    # pandas/NumPy scalar values expose item(); reject arrays and unknown
    # objects rather than depending on process-specific repr output.
    item = getattr(value, "item", None)
    if callable(item):
        normalized = item()
        if normalized is value:
            raise ValueError("native report contains an unsupported scalar")
        return _json_value(
            normalized,
            _depth=_depth + 1,
            _remaining_values=_remaining_values,
        )
    # pandas NaN/NaT are null-like, but must be detected without importing
    # pandas into the runtime module.
    raise ValueError(f"native report contains unsupported value type {type(value).__name__}")


def _json_record(columns: tuple[str, ...], values: tuple[Any, ...]) -> str:
    if len(columns) != len(values) or any(not column for column in columns):
        raise ValueError("native report row does not match its column schema")
    if len(set(columns)) != len(columns):
        raise ValueError("native report contains duplicate column names")
    record = {column: _json_value(value) for column, value in zip(columns, values, strict=True)}
    encoded = json.dumps(
        record,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(encoded.encode("utf-8")) > _MAX_RECORD_BYTES:
        raise ValueError("native report row exceeds its byte bound")
    return encoded


@dataclass(frozen=True, slots=True)
class NautilusNativeReportsReference:
    """Verified identity and row counts for one set of native reports."""

    artifact: ArtifactManifest
    trial_id: str
    attempt_id: str
    portfolio_fingerprint: str
    snapshot_fingerprint: str
    source_tape_fingerprint: str
    evaluation_window_fingerprint: str | None
    scoring_start_ns: int | None
    scoring_end_ns: int | None
    row_counts: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, ArtifactManifest):
            raise TypeError("artifact must be an ArtifactManifest")
        if (
            self.artifact.media_type != NAUTILUS_NATIVE_REPORTS_MEDIA_TYPE
            or self.artifact.schema_version != NAUTILUS_NATIVE_REPORTS_SCHEMA
            or self.artifact.retention_class is not ArtifactRetention.PINNED_RESULT
        ):
            raise ValueError("Nautilus native-report artifact identity is unsupported")
        _identity(self.trial_id, "trial_id")
        _identity(self.attempt_id, "attempt_id")
        for name in (
            "portfolio_fingerprint",
            "snapshot_fingerprint",
            "source_tape_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        if self.evaluation_window_fingerprint is None:
            if (self.scoring_start_ns, self.scoring_end_ns) != (None, None):
                raise ValueError("unwindowed reports must not carry scoring bounds")
        else:
            require_sha256_digest(
                self.evaluation_window_fingerprint,
                field_name="evaluation_window_fingerprint",
            )
            if not _bounds(self.scoring_start_ns, self.scoring_end_ns):
                raise ValueError("windowed reports require valid half-open scoring bounds")
        counts = tuple(self.row_counts)
        if tuple(kind for kind, _ in counts) != NAUTILUS_NATIVE_REPORT_KINDS:
            raise ValueError("native report kinds or their order are invalid")
        if any(
            not isinstance(count, int) or isinstance(count, bool) or count < 0
            for _, count in counts
        ):
            raise ValueError("native report row counts must be non-negative integers")
        if sum(count for _, count in counts) < 1:
            raise ValueError("native report artifact must contain at least one report row")
        object.__setattr__(self, "row_counts", counts)

    def _metadata(self) -> dict[str, str]:
        return {
            "protocol": NAUTILUS_NATIVE_REPORTS_PROTOCOL,
            "trial_id": self.trial_id,
            "attempt_id": self.attempt_id,
            "portfolio_fingerprint": self.portfolio_fingerprint,
            "snapshot_fingerprint": self.snapshot_fingerprint,
            "source_tape_fingerprint": self.source_tape_fingerprint,
            "evaluation_window_fingerprint": self.evaluation_window_fingerprint or "",
            "scoring_start_ns": "" if self.scoring_start_ns is None else str(self.scoring_start_ns),
            "scoring_end_ns": "" if self.scoring_end_ns is None else str(self.scoring_end_ns),
            "row_counts_json": json.dumps(
                dict(self.row_counts), sort_keys=True, separators=(",", ":")
            ),
        }

    def to_wire(self) -> dict[str, Any]:
        return {
            "protocol": NAUTILUS_NATIVE_REPORTS_PROTOCOL,
            "artifact": {
                "content_digest": self.artifact.content_digest,
                "byte_length": self.artifact.byte_length,
                "media_type": self.artifact.media_type,
                "schema_version": self.artifact.schema_version,
                "storage_key": self.artifact.storage_key,
                "retention_class": self.artifact.retention_class.value,
            },
            "trial_id": self.trial_id,
            "attempt_id": self.attempt_id,
            "portfolio_fingerprint": self.portfolio_fingerprint,
            "snapshot_fingerprint": self.snapshot_fingerprint,
            "source_tape_fingerprint": self.source_tape_fingerprint,
            "evaluation_window_fingerprint": self.evaluation_window_fingerprint,
            "scoring_start_ns": self.scoring_start_ns,
            "scoring_end_ns": self.scoring_end_ns,
            "row_counts": dict(self.row_counts),
        }

    @classmethod
    def from_wire(cls, value: Any) -> NautilusNativeReportsReference:
        fields = {
            "protocol",
            "artifact",
            "trial_id",
            "attempt_id",
            "portfolio_fingerprint",
            "snapshot_fingerprint",
            "source_tape_fingerprint",
            "evaluation_window_fingerprint",
            "scoring_start_ns",
            "scoring_end_ns",
            "row_counts",
        }
        if not isinstance(value, Mapping) or set(value) != fields:
            raise ValueError("native report reference fields are invalid")
        if value["protocol"] != NAUTILUS_NATIVE_REPORTS_PROTOCOL:
            raise ValueError("native report protocol is unsupported")
        raw_artifact = value["artifact"]
        artifact_fields = {
            "content_digest",
            "byte_length",
            "media_type",
            "schema_version",
            "storage_key",
            "retention_class",
        }
        if not isinstance(raw_artifact, Mapping) or set(raw_artifact) != artifact_fields:
            raise ValueError("native report artifact fields are invalid")
        raw_counts = value["row_counts"]
        if not isinstance(raw_counts, Mapping) or set(raw_counts) != set(
            NAUTILUS_NATIVE_REPORT_KINDS
        ):
            raise ValueError("native report row counts are invalid")
        artifact = ArtifactManifest(
            content_digest=raw_artifact["content_digest"],
            byte_length=raw_artifact["byte_length"],
            media_type=raw_artifact["media_type"],
            schema_version=raw_artifact["schema_version"],
            storage_key=raw_artifact["storage_key"],
            retention_class=ArtifactRetention(raw_artifact["retention_class"]),
        )
        return cls(
            artifact=artifact,
            trial_id=value["trial_id"],
            attempt_id=value["attempt_id"],
            portfolio_fingerprint=value["portfolio_fingerprint"],
            snapshot_fingerprint=value["snapshot_fingerprint"],
            source_tape_fingerprint=value["source_tape_fingerprint"],
            evaluation_window_fingerprint=value["evaluation_window_fingerprint"],
            scoring_start_ns=value["scoring_start_ns"],
            scoring_end_ns=value["scoring_end_ns"],
            row_counts=tuple((kind, raw_counts[kind]) for kind in NAUTILUS_NATIVE_REPORT_KINDS),
        )


class NautilusNativeReportsWriter:
    """Stream variable-column native report rows into bounded Parquet groups."""

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        engine_input: Mapping[str, Any],
        portfolio: Mapping[str, Any],
        max_stream_bytes: int = MAX_NAUTILUS_NATIVE_REPORTS_BYTES,
    ) -> None:
        if not isinstance(engine_input, Mapping) or not isinstance(portfolio, Mapping):
            raise TypeError("engine_input and portfolio must be mappings")
        if (
            not isinstance(max_stream_bytes, int)
            or isinstance(max_stream_bytes, bool)
            or max_stream_bytes < 1
        ):
            raise ValueError("max_stream_bytes must be a positive integer")
        tape = engine_input.get("event_tape")
        if not isinstance(tape, Mapping):
            raise ValueError("native reports require authenticated event-tape identity")
        self._trial_id = _identity(engine_input.get("trial_id"), "trial_id")
        self._attempt_id = _identity(engine_input.get("attempt_id"), "attempt_id")
        self._portfolio_fingerprint = _identity(
            portfolio.get("fingerprint"), "portfolio.fingerprint"
        )
        self._snapshot_fingerprint = _identity(
            engine_input.get("data_snapshot_fingerprint"), "data_snapshot_fingerprint"
        )
        self._source_tape_fingerprint = _identity(
            tape.get("source_tape_fingerprint"), "source_tape_fingerprint"
        )
        for name in ("portfolio_fingerprint", "snapshot_fingerprint", "source_tape_fingerprint"):
            require_sha256_digest(getattr(self, f"_{name}"), field_name=name)
        raw_window = engine_input.get("evaluation_window")
        if raw_window is None:
            self._evaluation_window_fingerprint = None
            self._scoring_start_ns = None
            self._scoring_end_ns = None
        elif isinstance(raw_window, Mapping):
            self._evaluation_window_fingerprint = _identity(
                raw_window.get("fingerprint"), "evaluation_window.fingerprint"
            )
            self._scoring_start_ns = raw_window.get("start_ns")
            self._scoring_end_ns = raw_window.get("end_ns")
            require_sha256_digest(
                self._evaluation_window_fingerprint,
                field_name="evaluation_window_fingerprint",
            )
            if not _bounds(self._scoring_start_ns, self._scoring_end_ns):
                raise ValueError("native report scoring bounds are invalid")
        else:
            raise ValueError("native report evaluation window is invalid")
        self._path = Path(path)
        self._max_stream_bytes = max_stream_bytes
        self._finished = False
        self._buffer: list[dict[str, Any]] = []
        self._buffer_bytes = 0
        self._row_counts: tuple[tuple[str, int], ...] | None = None
        import pyarrow as pa  # type: ignore[import-untyped]
        import pyarrow.parquet as pq  # type: ignore[import-untyped]

        self._base_schema = pa.schema(
            [
                pa.field("report_kind", pa.string(), nullable=False),
                pa.field("row_index", pa.int64(), nullable=False),
                pa.field("record_json", pa.string(), nullable=False),
            ]
        )
        self._pa = pa
        self._pq = pq
        self._schema = self._base_schema
        self._writer: Any | None = None

    def write_reports(self, reports: Mapping[str, Any]) -> None:
        if self._finished or self._row_counts is not None:
            raise ValueError("native report writer is already used")
        if not isinstance(reports, Mapping) or set(reports) != set(NAUTILUS_NATIVE_REPORT_KINDS):
            raise ValueError("native report set must contain account, fills, orders, and positions")
        declared_counts: list[tuple[str, int]] = []
        for kind in NAUTILUS_NATIVE_REPORT_KINDS:
            frame = reports[kind]
            count = len(frame)
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise ValueError("native report frame length is invalid")
            declared_counts.append((kind, count))
        self._row_counts = tuple(declared_counts)
        metadata = self._metadata()
        self._schema = self._base_schema.with_metadata(
            {key.encode(): value.encode() for key, value in metadata.items()}
        )
        self._writer = self._pq.ParquetWriter(
            str(self._path),
            self._schema,
            compression="zstd",
            use_dictionary=False,
            write_statistics=True,
            data_page_version="2.0",
        )
        row_counts: list[tuple[str, int]] = []
        for kind in NAUTILUS_NATIVE_REPORT_KINDS:
            frame = reports[kind]
            columns = tuple(str(column) for column in frame.columns)
            if any(not column for column in columns) or len(set(columns)) != len(columns):
                raise ValueError("native report columns must be unique non-empty strings")
            count = 0
            for row_index, values in enumerate(frame.itertuples(index=False, name=None)):
                record_json = _json_record(columns, tuple(values))
                self._buffer.append(
                    {
                        "report_kind": kind,
                        "row_index": row_index,
                        "record_json": record_json,
                    }
                )
                self._buffer_bytes += len(record_json.encode("utf-8")) + len(kind) + 24
                count += 1
                if len(self._buffer) >= _ROW_GROUP_SIZE or self._buffer_bytes >= _ROW_GROUP_BYTES:
                    self._flush()
            row_counts.append((kind, count))
        if tuple(row_counts) != self._row_counts:
            raise ValueError("native report frame changed while it was being serialized")

    def _metadata(self) -> dict[str, str]:
        if self._row_counts is None:
            raise ValueError("native reports have not been written")
        return {
            "protocol": NAUTILUS_NATIVE_REPORTS_PROTOCOL,
            "trial_id": self._trial_id,
            "attempt_id": self._attempt_id,
            "portfolio_fingerprint": self._portfolio_fingerprint,
            "snapshot_fingerprint": self._snapshot_fingerprint,
            "source_tape_fingerprint": self._source_tape_fingerprint,
            "evaluation_window_fingerprint": self._evaluation_window_fingerprint or "",
            "scoring_start_ns": ""
            if self._scoring_start_ns is None
            else str(self._scoring_start_ns),
            "scoring_end_ns": "" if self._scoring_end_ns is None else str(self._scoring_end_ns),
            "row_counts_json": json.dumps(
                dict(self._row_counts), sort_keys=True, separators=(",", ":")
            ),
        }

    def _flush(self) -> None:
        if not self._buffer:
            return
        table = self._pa.Table.from_pylist(self._buffer, schema=self._schema)
        if self._writer is None:
            raise ValueError("native report writer was not initialized")
        self._writer.write_table(table, row_group_size=_ROW_GROUP_SIZE)
        self._buffer.clear()
        self._buffer_bytes = 0

    def finish(self) -> NautilusNativeReportsReference:
        if self._finished or self._row_counts is None:
            raise ValueError("native reports must be written exactly once before finish")
        if sum(count for _, count in self._row_counts) < 1:
            raise ValueError("native reports contain no rows")
        self._flush()
        if self._writer is None:
            raise ValueError("native report Parquet writer was not initialized")
        self._writer.close()
        self._finished = True
        descriptor = os.open(
            self._path,
            os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            file_stat = os.fstat(descriptor)
            if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_size < 1:
                raise ValueError("native report output is not a regular file")
            if file_stat.st_size > self._max_stream_bytes:
                raise ValueError("native report artifact exceeds its byte bound")
            digest = hashlib.sha256()
            while chunk := os.read(descriptor, 1_048_576):
                digest.update(chunk)
        finally:
            os.close(descriptor)
        artifact_digest = f"sha256:{digest.hexdigest()}"
        artifact = ArtifactManifest(
            content_digest=artifact_digest,
            byte_length=file_stat.st_size,
            media_type=NAUTILUS_NATIVE_REPORTS_MEDIA_TYPE,
            schema_version=NAUTILUS_NATIVE_REPORTS_SCHEMA,
            storage_key=artifact_digest,
            retention_class=ArtifactRetention.PINNED_RESULT,
        )
        return NautilusNativeReportsReference(
            artifact=artifact,
            trial_id=self._trial_id,
            attempt_id=self._attempt_id,
            portfolio_fingerprint=self._portfolio_fingerprint,
            snapshot_fingerprint=self._snapshot_fingerprint,
            source_tape_fingerprint=self._source_tape_fingerprint,
            evaluation_window_fingerprint=self._evaluation_window_fingerprint,
            scoring_start_ns=self._scoring_start_ns,
            scoring_end_ns=self._scoring_end_ns,
            row_counts=self._row_counts,
        )

    def abort(self) -> None:
        """Close an incomplete artifact after a failed native execution."""

        if self._finished:
            return
        if self._writer is not None:
            self._writer.close()
        self._finished = True


def iter_nautilus_native_report_records(
    reference: NautilusNativeReportsReference,
    path: str | os.PathLike[str],
    *,
    max_stream_bytes: int = MAX_NAUTILUS_NATIVE_REPORTS_BYTES,
) -> Iterator[tuple[str, int, Mapping[str, Any]]]:
    """Yield rows only from one fully verified native-report artifact.

    The digest is checked on the same no-follow file descriptor used by
    PyArrow, avoiding a path-replacement race between integrity verification
    and metric extraction.  The protocol is validated while rows are streamed,
    so callers need not materialize a report in memory.
    """

    if not isinstance(reference, NautilusNativeReportsReference):
        raise TypeError("reference must be a NautilusNativeReportsReference")
    if (
        not isinstance(max_stream_bytes, int)
        or isinstance(max_stream_bytes, bool)
        or max_stream_bytes < 1
    ):
        raise ValueError("max_stream_bytes must be a positive integer")
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    stream = None
    try:
        file_stat = os.fstat(descriptor)
        if (
            not stat.S_ISREG(file_stat.st_mode)
            or file_stat.st_size != reference.artifact.byte_length
        ):
            raise ValueError("native report file type or byte length differs from its reference")
        if file_stat.st_size > max_stream_bytes:
            raise ValueError("native report artifact exceeds its byte bound")
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, 1_048_576):
            digest.update(chunk)
        if f"sha256:{digest.hexdigest()}" != reference.artifact.content_digest:
            raise ValueError("native report digest differs from its reference")
        stream = os.fdopen(descriptor, "rb")
        descriptor = -1
        stream.seek(0)

        import pyarrow as pa  # type: ignore[import-untyped]
        import pyarrow.parquet as pq  # type: ignore[import-untyped]

        parquet = pq.ParquetFile(stream)
        expected_schema = pa.schema(
            [
                pa.field("report_kind", pa.string(), nullable=False),
                pa.field("row_index", pa.int64(), nullable=False),
                pa.field("record_json", pa.string(), nullable=False),
            ]
        )
        expected_metadata = reference._metadata()
        expected_schema = expected_schema.with_metadata(
            {key.encode(): value.encode() for key, value in expected_metadata.items()}
        )
        if not parquet.schema_arrow.equals(expected_schema, check_metadata=True):
            raise ValueError("native report Parquet schema differs from its protocol")
        expected_counts = dict(reference.row_counts)
        observed_counts = dict.fromkeys(NAUTILUS_NATIVE_REPORT_KINDS, 0)
        next_indices = dict.fromkeys(NAUTILUS_NATIVE_REPORT_KINDS, 0)
        for batch in parquet.iter_batches(batch_size=_ROW_GROUP_SIZE):
            for kind, row_index, record_json in zip(
                batch.column("report_kind").to_pylist(),
                batch.column("row_index").to_pylist(),
                batch.column("record_json").to_pylist(),
                strict=True,
            ):
                if kind not in observed_counts or row_index != next_indices[kind]:
                    raise ValueError("native report rows are not canonically ordered")
                if (
                    not isinstance(record_json, str)
                    or len(record_json.encode("utf-8")) > _MAX_RECORD_BYTES
                ):
                    raise ValueError("native report row is malformed or exceeds its bound")
                record = json.loads(record_json, object_pairs_hook=_unique_json_object)
                if not isinstance(record, Mapping):
                    raise ValueError("native report record must be a JSON object")
                if _canonical_json(record) != record_json:
                    raise ValueError("native report row JSON is not canonical")
                next_indices[kind] += 1
                observed_counts[kind] += 1
                yield kind, row_index, record
        if observed_counts != expected_counts:
            raise ValueError("native report row counts differ from their reference")
    finally:
        if stream is not None:
            stream.close()
        if descriptor >= 0:
            os.close(descriptor)


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("native report row contains a duplicate JSON key")
        result[key] = value
    return result


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def verify_nautilus_native_reports_file(
    reference: NautilusNativeReportsReference,
    path: str | os.PathLike[str],
    *,
    max_stream_bytes: int = MAX_NAUTILUS_NATIVE_REPORTS_BYTES,
) -> None:
    """Verify digest, Parquet schema, row ordering, counts, and scope metadata."""

    for _ in iter_nautilus_native_report_records(
        reference,
        path,
        max_stream_bytes=max_stream_bytes,
    ):
        pass


__all__ = [
    "MAX_NAUTILUS_NATIVE_REPORTS_BYTES",
    "NAUTILUS_NATIVE_REPORT_KINDS",
    "NAUTILUS_NATIVE_REPORTS_MEDIA_TYPE",
    "NAUTILUS_NATIVE_REPORTS_SCHEMA",
    "NautilusNativeReportsReference",
    "NautilusNativeReportsWriter",
    "iter_nautilus_native_report_records",
    "verify_nautilus_native_reports_file",
]
