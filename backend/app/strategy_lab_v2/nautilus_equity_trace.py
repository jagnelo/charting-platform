"""Content-addressed Arrow trace of native Nautilus account equity marks.

The trace records the simulator's account valuation at canonical market-event
callbacks. When an evaluation window is present, warm-up rows are omitted and
every emitted row is constrained to its half-open scoring interval. The writer
is row-group bounded so large runs do not retain the equity series in memory.
"""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.strategy_lab_v2.canonical import require_sha256_digest
from app.strategy_lab_v2.contracts import ArtifactManifest, ArtifactRetention

NAUTILUS_ACCOUNT_EQUITY_TRACE_MEDIA_TYPE = (
    "application/vnd.charting.strategy-lab.nautilus-account-equity+parquet"
)
NAUTILUS_ACCOUNT_EQUITY_TRACE_SCHEMA = "strategy-lab.nautilus.account-equity-trace.v1"
NAUTILUS_ACCOUNT_EQUITY_TRACE_PROTOCOL = "strategy-lab.nautilus.account-equity-trace.v1"
MAX_NAUTILUS_ACCOUNT_EQUITY_TRACE_BYTES = 1_099_511_627_776  # 1 TiB hard ceiling
_ROW_GROUP_SIZE = 8_192
_DECIMAL_TYPE = "decimal128(38, 18)"
_SCHEMA_FIELDS = (
    "event_id",
    "event_time_ns",
    "event_index",
    "source_sequence",
    "account_equity",
    "account_cash_balance",
)


def _positive_integer(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _decimal(value: Any, field_name: str, *, non_negative: bool = False) -> Decimal:
    if isinstance(value, str):
        try:
            value = Decimal(value)
        except ArithmeticError as error:
            raise ValueError(f"{field_name} must be a finite Decimal") from error
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{field_name} must be a finite Decimal")
    if non_negative and value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    # The fixed Arrow decimal scale is part of the persisted protocol. Reject
    # rather than silently round an engine value the trace cannot represent.
    decimal_tuple = value.as_tuple()
    if (
        not isinstance(decimal_tuple.exponent, int)
        or decimal_tuple.exponent < -18
        or len(decimal_tuple.digits) + decimal_tuple.exponent + 18 > 38
    ):
        raise ValueError(f"{field_name} exceeds the account-equity Arrow precision")
    return value


def _valid_scoring_bounds(start_ns: Any, end_ns: Any) -> bool:
    return (
        isinstance(start_ns, int)
        and not isinstance(start_ns, bool)
        and start_ns >= 0
        and isinstance(end_ns, int)
        and not isinstance(end_ns, bool)
        and end_ns > start_ns
    )


@dataclass(frozen=True, slots=True)
class NautilusAccountEquityTraceReference:
    """Verified result-artifact identity and the exact trial/window it covers."""

    artifact: ArtifactManifest
    trial_id: str
    attempt_id: str
    portfolio_fingerprint: str
    snapshot_fingerprint: str
    source_tape_fingerprint: str
    evaluation_window_fingerprint: str | None
    scoring_start_ns: int | None
    scoring_end_ns: int | None
    base_currency: str
    initial_capital: Decimal
    observation_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, ArtifactManifest):
            raise TypeError("artifact must be an ArtifactManifest")
        if (
            self.artifact.media_type != NAUTILUS_ACCOUNT_EQUITY_TRACE_MEDIA_TYPE
            or self.artifact.schema_version != NAUTILUS_ACCOUNT_EQUITY_TRACE_SCHEMA
            or self.artifact.retention_class is not ArtifactRetention.PINNED_RESULT
        ):
            raise ValueError("Nautilus account-equity trace artifact identity is unsupported")
        if not isinstance(self.trial_id, str) or not self.trial_id.strip():
            raise ValueError("trial_id must not be empty")
        if not isinstance(self.attempt_id, str) or not self.attempt_id.strip():
            raise ValueError("attempt_id must not be empty")
        for name in (
            "portfolio_fingerprint",
            "snapshot_fingerprint",
            "source_tape_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        if self.evaluation_window_fingerprint is not None:
            require_sha256_digest(
                self.evaluation_window_fingerprint,
                field_name="evaluation_window_fingerprint",
            )
        bounds = (self.scoring_start_ns, self.scoring_end_ns)
        if self.evaluation_window_fingerprint is None:
            if bounds != (None, None):
                raise ValueError("unwindowed traces must not carry scoring bounds")
        elif not _valid_scoring_bounds(self.scoring_start_ns, self.scoring_end_ns):
            raise ValueError("windowed traces require valid half-open scoring bounds")
        if (
            not isinstance(self.base_currency, str)
            or len(self.base_currency) != 3
            or not self.base_currency.isascii()
            or not self.base_currency.isalpha()
        ):
            raise ValueError("base_currency must be a three-letter currency code")
        _decimal(self.initial_capital, "initial_capital")
        if self.initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        if self.artifact.byte_length < 1:
            raise ValueError("native account-equity trace artifact must not be empty")
        _positive_integer(self.observation_count, "observation_count")

    @property
    def fingerprint(self) -> str:
        from app.strategy_lab_v2.canonical import content_digest

        return content_digest(self)

    def metadata(self) -> dict[str, str]:
        return {
            "protocol": NAUTILUS_ACCOUNT_EQUITY_TRACE_PROTOCOL,
            "trial_id": self.trial_id,
            "attempt_id": self.attempt_id,
            "portfolio_fingerprint": self.portfolio_fingerprint,
            "snapshot_fingerprint": self.snapshot_fingerprint,
            "source_tape_fingerprint": self.source_tape_fingerprint,
            "evaluation_window_fingerprint": self.evaluation_window_fingerprint or "",
            "scoring_start_ns": "" if self.scoring_start_ns is None else str(self.scoring_start_ns),
            "scoring_end_ns": "" if self.scoring_end_ns is None else str(self.scoring_end_ns),
            "base_currency": self.base_currency.upper(),
            "initial_capital": format(self.initial_capital, "f"),
        }

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
            "trial_id": self.trial_id,
            "attempt_id": self.attempt_id,
            "portfolio_fingerprint": self.portfolio_fingerprint,
            "snapshot_fingerprint": self.snapshot_fingerprint,
            "source_tape_fingerprint": self.source_tape_fingerprint,
            "evaluation_window_fingerprint": self.evaluation_window_fingerprint,
            "scoring_start_ns": self.scoring_start_ns,
            "scoring_end_ns": self.scoring_end_ns,
            "base_currency": self.base_currency,
            "initial_capital": format(self.initial_capital, "f"),
            "observation_count": self.observation_count,
        }

    @classmethod
    def from_wire(cls, value: Any) -> NautilusAccountEquityTraceReference:
        if not isinstance(value, Mapping) or set(value) != {
            "artifact",
            "trial_id",
            "attempt_id",
            "portfolio_fingerprint",
            "snapshot_fingerprint",
            "source_tape_fingerprint",
            "evaluation_window_fingerprint",
            "scoring_start_ns",
            "scoring_end_ns",
            "base_currency",
            "initial_capital",
            "observation_count",
        }:
            raise ValueError("Nautilus account-equity trace receipt fields are invalid")
        raw_artifact = value["artifact"]
        if not isinstance(raw_artifact, Mapping) or set(raw_artifact) != {
            "content_digest",
            "byte_length",
            "media_type",
            "schema_version",
            "storage_key",
            "retention_class",
        }:
            raise ValueError("Nautilus account-equity trace artifact fields are invalid")
        if not isinstance(value["initial_capital"], str):
            raise ValueError("Nautilus account-equity initial capital must be a decimal string")
        try:
            artifact = ArtifactManifest(
                content_digest=raw_artifact["content_digest"],
                byte_length=raw_artifact["byte_length"],
                media_type=raw_artifact["media_type"],
                schema_version=raw_artifact["schema_version"],
                storage_key=raw_artifact["storage_key"],
                retention_class=ArtifactRetention(raw_artifact["retention_class"]),
            )
            initial_capital = Decimal(value["initial_capital"])
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
                base_currency=value["base_currency"],
                initial_capital=initial_capital,
                observation_count=value["observation_count"],
            )
        except (TypeError, ValueError, ArithmeticError) as error:
            raise ValueError("Nautilus account-equity trace receipt is invalid") from error


class NautilusAccountEquityTraceWriter:
    """Write native marks in bounded compressed Parquet row groups."""

    _evaluation_window_fingerprint: str | None
    _scoring_start_ns: int | None
    _scoring_end_ns: int | None
    _trial_id: str
    _attempt_id: str
    _portfolio_fingerprint: str
    _snapshot_fingerprint: str
    _source_tape_fingerprint: str
    _base_currency: str
    _initial_capital: Decimal
    _max_stream_bytes: int
    _path: Path
    _schema: Any
    _writer: Any
    _buffer: list[dict[str, Any]]
    _observation_count: int
    _previous_index: int
    _previous_time_ns: int
    _finished: bool

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        engine_input: Mapping[str, Any],
        portfolio: Any,
        max_stream_bytes: int = MAX_NAUTILUS_ACCOUNT_EQUITY_TRACE_BYTES,
    ) -> None:
        if not isinstance(engine_input, Mapping):
            raise TypeError("engine_input must be a mapping")
        if not isinstance(portfolio, Mapping):
            raise TypeError("portfolio must be a portfolio composition mapping")
        if (
            not isinstance(max_stream_bytes, int)
            or isinstance(max_stream_bytes, bool)
            or max_stream_bytes < 1
        ):
            raise ValueError("max_stream_bytes must be a positive integer")
        import pyarrow as pa  # type: ignore[import-untyped]
        import pyarrow.parquet as pq  # type: ignore[import-untyped]

        tape = engine_input.get("event_tape")
        if not isinstance(tape, Mapping):
            raise ValueError("equity trace requires the authenticated event-tape identity")
        portfolio_fingerprint = portfolio.get("fingerprint")
        if not isinstance(portfolio_fingerprint, str):
            raise ValueError("equity trace requires a portfolio fingerprint")
        trial_id = engine_input.get("trial_id")
        attempt_id = engine_input.get("attempt_id")
        snapshot_fingerprint = engine_input.get("data_snapshot_fingerprint")
        source_tape_fingerprint = tape.get("source_tape_fingerprint")
        if (
            not isinstance(trial_id, str)
            or not trial_id.strip()
            or not isinstance(attempt_id, str)
            or not attempt_id.strip()
        ):
            raise ValueError("equity trace trial and attempt identities are required")
        if not isinstance(snapshot_fingerprint, str):
            raise ValueError("equity trace snapshot fingerprint is required")
        if not isinstance(source_tape_fingerprint, str):
            raise ValueError("equity trace source tape fingerprint is required")
        for name, item in (
            ("snapshot_fingerprint", snapshot_fingerprint),
            ("source_tape_fingerprint", source_tape_fingerprint),
            ("portfolio_fingerprint", portfolio_fingerprint),
        ):
            require_sha256_digest(item, field_name=name)
        raw_window = engine_input.get("evaluation_window")
        if raw_window is None:
            self._evaluation_window_fingerprint = None
            self._scoring_start_ns = None
            self._scoring_end_ns = None
        elif isinstance(raw_window, Mapping):
            window_fingerprint = raw_window.get("fingerprint")
            start_ns = raw_window.get("start_ns")
            end_ns = raw_window.get("end_ns")
            if not isinstance(window_fingerprint, str):
                raise ValueError("equity trace evaluation window fingerprint is invalid")
            if not _valid_scoring_bounds(start_ns, end_ns):
                raise ValueError("equity trace scoring bounds are invalid")
            self._evaluation_window_fingerprint = window_fingerprint
            self._scoring_start_ns = start_ns
            self._scoring_end_ns = end_ns
            require_sha256_digest(
                self._evaluation_window_fingerprint,
                field_name="evaluation_window_fingerprint",
            )
        else:
            raise ValueError("equity trace evaluation window is invalid")
        self._trial_id = trial_id
        self._attempt_id = attempt_id
        self._portfolio_fingerprint = portfolio_fingerprint
        self._snapshot_fingerprint = snapshot_fingerprint
        self._source_tape_fingerprint = source_tape_fingerprint
        self._base_currency = str(portfolio.get("base_currency", "")).upper()
        if len(self._base_currency) != 3 or not self._base_currency.isalpha():
            raise ValueError("equity trace base currency is invalid")
        self._initial_capital = _decimal(portfolio.get("initial_capital"), "initial_capital")
        if self._initial_capital <= 0:
            raise ValueError("equity trace initial capital must be positive")
        self._max_stream_bytes = max_stream_bytes
        self._path = Path(path)
        self._schema = pa.schema(
            [
                pa.field("event_id", pa.string(), nullable=False),
                pa.field("event_time_ns", pa.int64(), nullable=False),
                pa.field("event_index", pa.int64(), nullable=False),
                pa.field("source_sequence", pa.int64(), nullable=False),
                pa.field("account_equity", pa.decimal128(38, 18), nullable=False),
                pa.field("account_cash_balance", pa.decimal128(38, 18), nullable=False),
            ],
            metadata={key.encode(): value.encode() for key, value in self._metadata().items()},
        )
        self._writer = pq.ParquetWriter(
            str(self._path),
            self._schema,
            compression="zstd",
            use_dictionary=False,
            write_statistics=True,
            data_page_version="2.0",
        )
        self._buffer: list[dict[str, Any]] = []
        self._observation_count = 0
        self._previous_index = -1
        self._previous_time_ns = -1
        self._finished = False

    def _metadata(self) -> dict[str, str]:
        return {
            "protocol": NAUTILUS_ACCOUNT_EQUITY_TRACE_PROTOCOL,
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
            "base_currency": self._base_currency,
            "initial_capital": format(self._initial_capital, "f"),
        }

    def write(
        self,
        *,
        event_id: str,
        event_time_ns: int,
        event_index: int,
        source_sequence: int,
        account_equity: Decimal,
        account_cash_balance: Decimal,
    ) -> None:
        """Append one native mark, silently excluding authenticated warm-up."""

        if self._finished:
            raise ValueError("equity trace writer is already finished")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("equity trace event_id must not be empty")
        for name, value in (
            ("event_time_ns", event_time_ns),
            ("event_index", event_index),
            ("source_sequence", source_sequence),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"equity trace {name} must be a non-negative integer")
        if self._scoring_start_ns is not None:
            assert self._scoring_end_ns is not None
            if event_time_ns < self._scoring_start_ns:
                return
            if event_time_ns >= self._scoring_end_ns:
                raise ValueError("native equity mark is outside the scoring interval")
        if event_index <= self._previous_index or event_time_ns < self._previous_time_ns:
            raise ValueError("native equity marks must preserve canonical event order")
        equity = _decimal(account_equity, "account_equity", non_negative=True)
        cash = _decimal(account_cash_balance, "account_cash_balance")
        self._buffer.append(
            {
                "event_id": event_id,
                "event_time_ns": event_time_ns,
                "event_index": event_index,
                "source_sequence": source_sequence,
                "account_equity": equity,
                "account_cash_balance": cash,
            }
        )
        self._observation_count += 1
        self._previous_index = event_index
        self._previous_time_ns = event_time_ns
        if len(self._buffer) >= _ROW_GROUP_SIZE:
            self._flush()

    def _flush(self) -> None:
        if not self._buffer:
            return
        import pyarrow as pa  # type: ignore[import-untyped]

        table = pa.Table.from_pylist(self._buffer, schema=self._schema)
        self._writer.write_table(table, row_group_size=_ROW_GROUP_SIZE)
        self._buffer.clear()

    def finish(self) -> NautilusAccountEquityTraceReference:
        """Close, bound, and hash the completed OOS trace artifact."""

        if self._finished:
            raise ValueError("equity trace writer is already finished")
        self._flush()
        self._writer.close()
        self._finished = True
        if self._observation_count < 1:
            raise ValueError("native account-equity trace contains no scoring observations")
        descriptor = os.open(
            self._path,
            os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            stat_result = os.fstat(descriptor)
            if not stat.S_ISREG(stat_result.st_mode) or stat_result.st_size < 1:
                raise ValueError("native account-equity trace output is not a regular file")
            if stat_result.st_size > self._max_stream_bytes:
                raise ValueError("native account-equity trace exceeds its byte bound")
            digest = hashlib.sha256()
            while chunk := os.read(descriptor, 1_048_576):
                digest.update(chunk)
        finally:
            os.close(descriptor)
        artifact_digest = f"sha256:{digest.hexdigest()}"
        artifact = ArtifactManifest(
            content_digest=artifact_digest,
            byte_length=stat_result.st_size,
            media_type=NAUTILUS_ACCOUNT_EQUITY_TRACE_MEDIA_TYPE,
            schema_version=NAUTILUS_ACCOUNT_EQUITY_TRACE_SCHEMA,
            storage_key=artifact_digest,
            retention_class=ArtifactRetention.PINNED_RESULT,
        )
        return NautilusAccountEquityTraceReference(
            artifact=artifact,
            trial_id=self._trial_id,
            attempt_id=self._attempt_id,
            portfolio_fingerprint=self._portfolio_fingerprint,
            snapshot_fingerprint=self._snapshot_fingerprint,
            source_tape_fingerprint=self._source_tape_fingerprint,
            evaluation_window_fingerprint=self._evaluation_window_fingerprint,
            scoring_start_ns=self._scoring_start_ns,
            scoring_end_ns=self._scoring_end_ns,
            base_currency=self._base_currency,
            initial_capital=self._initial_capital,
            observation_count=self._observation_count,
        )


def iter_verified_nautilus_account_equity_marks(
    reference: NautilusAccountEquityTraceReference,
    path: str | os.PathLike[str],
    *,
    expected_events: Iterable[Mapping[str, Any]] | None,
    max_stream_bytes: int = MAX_NAUTILUS_ACCOUNT_EQUITY_TRACE_BYTES,
) -> Iterator[Decimal]:
    """Yield marks only after validating their exact artifact and OOS binding.

    The digest is checked over the same no-follow descriptor that PyArrow reads.
    Validation continues as the consumer streams the marks and the iterator
    raises if the final count or frozen-tape comparison is incomplete.
    """

    if not isinstance(reference, NautilusAccountEquityTraceReference):
        raise TypeError("reference must be a NautilusAccountEquityTraceReference")
    if (
        not isinstance(max_stream_bytes, int)
        or isinstance(max_stream_bytes, bool)
        or max_stream_bytes < 1
    ):
        raise ValueError("max_stream_bytes must be a positive integer")
    import pyarrow.parquet as pq  # type: ignore[import-untyped]

    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    try:
        stat_result = os.fstat(descriptor)
        if (
            not stat.S_ISREG(stat_result.st_mode)
            or stat_result.st_size != reference.artifact.byte_length
        ):
            raise ValueError("native account-equity trace file length differs")
        if stat_result.st_size > max_stream_bytes:
            raise ValueError("native account-equity trace exceeds its byte bound")
        stream = os.fdopen(descriptor, "rb")
        descriptor = -1
        try:
            digest = hashlib.sha256()
            while chunk := stream.read(1_048_576):
                digest.update(chunk)
            if f"sha256:{digest.hexdigest()}" != reference.artifact.content_digest:
                raise ValueError("native account-equity trace digest differs")
            stream.seek(0)
            parquet = pq.ParquetFile(stream)
            schema = parquet.schema_arrow
            if tuple(schema.names) != _SCHEMA_FIELDS:
                raise ValueError("native account-equity trace columns are invalid")
            expected_types = (
                "string",
                "int64",
                "int64",
                "int64",
                _DECIMAL_TYPE,
                _DECIMAL_TYPE,
            )
            if tuple(str(field.type) for field in schema) != expected_types or any(
                field.nullable for field in schema
            ):
                raise ValueError("native account-equity trace field types are invalid")
            metadata = schema.metadata or {}
            decoded_metadata = {key.decode(): value.decode() for key, value in metadata.items()}
            if decoded_metadata != reference.metadata():
                raise ValueError("native account-equity trace metadata differs from its receipt")
            expected_iterator = None if expected_events is None else iter(expected_events)
            expected_index = 0
            observed_count = 0
            previous_index = -1
            previous_time = -1
            previous_sequence = -1
            for batch in parquet.iter_batches(batch_size=_ROW_GROUP_SIZE):
                for row in batch.to_pylist():
                    event_id = row["event_id"]
                    event_time_ns = row["event_time_ns"]
                    event_index = row["event_index"]
                    source_sequence = row["source_sequence"]
                    if (
                        not isinstance(event_id, str)
                        or not event_id
                        or any(
                            not isinstance(value, int) or isinstance(value, bool) or value < 0
                            for value in (event_time_ns, event_index, source_sequence)
                        )
                    ):
                        raise ValueError("native account-equity mark identity is invalid")
                    if expected_iterator is None:
                        if reference.scoring_start_ns is not None:
                            assert reference.scoring_end_ns is not None
                            if not (
                                reference.scoring_start_ns
                                <= event_time_ns
                                < reference.scoring_end_ns
                            ):
                                raise ValueError(
                                    "native account-equity mark is outside its scoring interval"
                                )
                    else:
                        while True:
                            expected = next(expected_iterator, None)
                            if expected is None:
                                raise ValueError(
                                    "equity trace has marks outside its frozen event tape"
                                )
                            event = expected.get("event", expected)
                            if not isinstance(event, Mapping):
                                raise ValueError("expected native tape event is invalid")
                            current_index = expected.get("index", expected_index)
                            expected_index += 1
                            expected_time_ns = event.get("event_time_ns")
                            if (
                                not isinstance(current_index, int)
                                or isinstance(current_index, bool)
                                or not isinstance(expected_time_ns, int)
                                or isinstance(expected_time_ns, bool)
                            ):
                                raise ValueError("expected native tape event ordering is invalid")
                            if reference.scoring_start_ns is None:
                                inside = True
                            else:
                                assert reference.scoring_end_ns is not None
                                inside = (
                                    reference.scoring_start_ns
                                    <= expected_time_ns
                                    < reference.scoring_end_ns
                                )
                            if inside:
                                break
                        if (
                            event_id != event.get("event_id")
                            or event_time_ns != expected_time_ns
                            or event_index != current_index
                            or source_sequence != event.get("sequence")
                        ):
                            raise ValueError(
                                "native account-equity mark differs from its tape event"
                            )
                    equity = row["account_equity"]
                    cash = row["account_cash_balance"]
                    if (
                        not isinstance(equity, Decimal)
                        or equity < 0
                        or not isinstance(cash, Decimal)
                    ):
                        raise ValueError("native account-equity mark values are invalid")
                    if (
                        event_index <= previous_index
                        or event_time_ns < previous_time
                        or (event_time_ns == previous_time and source_sequence < previous_sequence)
                    ):
                        raise ValueError("native account-equity marks are not canonically ordered")
                    previous_index = event_index
                    previous_time = event_time_ns
                    previous_sequence = source_sequence
                    observed_count += 1
                    yield equity
            if expected_iterator is not None:
                for expected in expected_iterator:
                    event = expected.get("event", expected)
                    if not isinstance(event, Mapping):
                        raise ValueError("expected native tape event is invalid")
                    event_time_ns = event.get("event_time_ns")
                    if not isinstance(event_time_ns, int) or isinstance(event_time_ns, bool):
                        raise ValueError("expected native tape event time is invalid")
                    if reference.scoring_start_ns is None:
                        raise ValueError("native account-equity trace omitted scoring tape events")
                    assert reference.scoring_end_ns is not None
                    if reference.scoring_start_ns <= event_time_ns < reference.scoring_end_ns:
                        raise ValueError("native account-equity trace omitted scoring tape events")
            if observed_count != reference.observation_count:
                raise ValueError("native account-equity observation count differs")
        finally:
            stream.close()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def verify_nautilus_account_equity_trace_file(
    reference: NautilusAccountEquityTraceReference,
    path: str | os.PathLike[str],
    *,
    expected_events: Iterable[Mapping[str, Any]] | None,
    max_stream_bytes: int = MAX_NAUTILUS_ACCOUNT_EQUITY_TRACE_BYTES,
) -> None:
    """Verify bytes, schema, scope, and optionally every mark against the tape."""

    for _ in iter_verified_nautilus_account_equity_marks(
        reference,
        path,
        expected_events=expected_events,
        max_stream_bytes=max_stream_bytes,
    ):
        pass


__all__ = [
    "MAX_NAUTILUS_ACCOUNT_EQUITY_TRACE_BYTES",
    "NAUTILUS_ACCOUNT_EQUITY_TRACE_MEDIA_TYPE",
    "NAUTILUS_ACCOUNT_EQUITY_TRACE_PROTOCOL",
    "NAUTILUS_ACCOUNT_EQUITY_TRACE_SCHEMA",
    "NautilusAccountEquityTraceReference",
    "NautilusAccountEquityTraceWriter",
    "iter_verified_nautilus_account_equity_marks",
    "verify_nautilus_account_equity_trace_file",
]
