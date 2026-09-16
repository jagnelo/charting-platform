"""PostgreSQL adapter for Strategy Lab v2 aggregate compare-and-set storage.

The adapter maps the package-owned :mod:`storage` contract to one SQLAlchemy
async transaction.  It does not create tables or register models; the additive
schema remains a separately reconciled migration.  Every state value is stored
as versioned canonical JSON so tuple, mapping, decimal, and timezone-aware
values retain the same content identity after a round trip.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Protocol

from sqlalchemy import text

from app.strategy_lab_v2.canonical import canonical_json, freeze_json
from app.strategy_lab_v2.storage import (
    AggregateKey,
    AggregateMutation,
    StorageTransactionDecision,
    StorageTransactionReceipt,
    StorageTransactionRequest,
    StorageTransactionResolution,
    StoredAggregate,
    resolve_storage_transaction,
)


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


class _ConcurrentWriteConflict(Exception):
    """Raised when a compare-and-set row changed after the initial lock."""


@dataclass(frozen=True, slots=True)
class PostgresStorageSchema:
    """Explicit DDL contract for a future additive migration."""

    aggregate_table: str = "strategy_lab_v2_aggregates"
    receipt_table: str = "strategy_lab_v2_storage_receipts"

    def __post_init__(self) -> None:
        for name, value in (
            ("aggregate_table", self.aggregate_table),
            ("receipt_table", self.receipt_table),
        ):
            if not isinstance(value, str) or not re.fullmatch(r"[a-z_][a-z0-9_]*", value):
                raise ValueError(f"{name} must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.aggregate_table} (
                aggregate_type TEXT NOT NULL,
                aggregate_id TEXT NOT NULL,
                version BIGINT NOT NULL,
                state_json TEXT NOT NULL,
                state_fingerprint TEXT NOT NULL,
                PRIMARY KEY (aggregate_type, aggregate_id)
            )
            """,
            f"""
            CREATE TABLE {self.receipt_table} (
                request_id TEXT PRIMARY KEY,
                request_fingerprint TEXT NOT NULL,
                outcome_fingerprint TEXT NOT NULL,
                committed_json TEXT NOT NULL
            )
            """,
        )


class PostgresAggregateStore:
    """Transactional PostgreSQL implementation of the storage contract."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresStorageSchema | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresStorageSchema()

    @property
    def schema(self) -> PostgresStorageSchema:
        return self._schema

    async def get(self, key: AggregateKey) -> StoredAggregate | None:
        """Read one aggregate snapshot without changing authoritative state.

        The row is read inside a short transaction so a future API adapter can
        bind the response to one database snapshot.  No receipt or mutation is
        created by this method; compare-and-set writes continue through
        :meth:`apply`.
        """

        if not isinstance(key, AggregateKey):
            raise TypeError("key must be an AggregateKey")
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                result = await session.execute(
                    text(
                        f"""
                        SELECT aggregate_type, aggregate_id, version, state_json, state_fingerprint
                        FROM {self._schema.aggregate_table}
                        WHERE aggregate_type = :aggregate_type
                          AND aggregate_id = :aggregate_id
                        """
                    ),
                    {"aggregate_type": key.aggregate_type, "aggregate_id": key.aggregate_id},
                )
                rows = list(result.mappings())
                if not rows:
                    return None
                if len(rows) != 1:
                    raise ValueError("PostgreSQL aggregate read returned duplicate keys")
                return _decode_aggregate_row(rows[0])

    async def list_type(self, aggregate_type: str) -> tuple[StoredAggregate, ...]:
        """Read all aggregates of one type in deterministic key order.

        The package-level adapter intentionally returns a complete immutable
        snapshot so a resource cursor can bind to its content digest.  A
        production query may replace this with a database snapshot token while
        preserving the same method contract.
        """

        if not isinstance(aggregate_type, str) or not aggregate_type.strip():
            raise ValueError("aggregate_type must not be empty")
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                result = await session.execute(
                    text(
                        f"""
                        SELECT aggregate_type, aggregate_id, version, state_json, state_fingerprint
                        FROM {self._schema.aggregate_table}
                        WHERE aggregate_type = :aggregate_type
                        ORDER BY aggregate_id ASC
                        """
                    ),
                    {"aggregate_type": aggregate_type},
                )
                rows = list(result.mappings())
                aggregates = tuple(_decode_aggregate_row(row) for row in rows)
                if tuple(sorted(aggregates, key=lambda item: item.key)) != aggregates:
                    raise ValueError("PostgreSQL aggregate list is not deterministically ordered")
                return aggregates

    async def apply(self, request: StorageTransactionRequest) -> StorageTransactionResolution:
        """Apply one request atomically, or return a typed rejection.

        Receipt and aggregate rows are locked before pure resolution.  A
        concurrent compare-and-set race rolls the SQL transaction back and
        returns the original aggregate snapshot, allowing the caller to retry
        from a fresh read.
        """

        if not isinstance(request, StorageTransactionRequest):
            raise TypeError("request must be a StorageTransactionRequest")
        current: tuple[StoredAggregate, ...] = ()
        try:
            session: AsyncSessionLike = self._session_factory()
            async with session:
                async with session.begin():
                    current = await self._load_current(session, request.mutations)
                    prior = await self._load_receipt(session, request.request_id)
                    resolved = resolve_storage_transaction(
                        current,
                        request,
                        (prior,) if prior is not None else (),
                    )
                    if resolved.decision is not StorageTransactionDecision.APPLY:
                        return resolved
                    if resolved.receipt is None:
                        return _reject(request, current, "storage resolution omitted its receipt")
                    await self._persist(session, request, resolved)
                    return resolved
        except _ConcurrentWriteConflict:
            return _reject(request, current, "storage compare-and-set lost a concurrent race")
        except Exception as error:  # pragma: no cover - live database boundary
            return _reject(request, current, f"PostgreSQL transaction failed: {type(error).__name__}")

    async def _load_current(
        self,
        session: AsyncSessionLike,
        mutations: Sequence[AggregateMutation],
    ) -> tuple[StoredAggregate, ...]:
        placeholders: list[str] = []
        params: dict[str, Any] = {}
        for index, mutation in enumerate(mutations):
            type_param = f"aggregate_type_{index}"
            id_param = f"aggregate_id_{index}"
            placeholders.append(f"(:{type_param}, :{id_param})")
            params[type_param] = mutation.key.aggregate_type
            params[id_param] = mutation.key.aggregate_id
        result = await session.execute(
            text(
                f"""
                SELECT aggregate_type, aggregate_id, version, state_json, state_fingerprint
                FROM {self._schema.aggregate_table}
                WHERE (aggregate_type, aggregate_id) IN ({', '.join(placeholders)})
                FOR UPDATE
                """
            ),
            params,
        )
        rows = list(result.mappings())
        aggregates: list[StoredAggregate] = []
        seen: set[AggregateKey] = set()
        for row in rows:
            key = AggregateKey(row["aggregate_type"], row["aggregate_id"])
            if key in seen:
                raise ValueError("PostgreSQL aggregate query returned duplicate keys")
            seen.add(key)
            state = _decode_state(row["state_json"])
            aggregate = StoredAggregate(key, int(row["version"]), state)
            if aggregate.state_fingerprint != row["state_fingerprint"]:
                raise ValueError("PostgreSQL aggregate state fingerprint does not match bytes")
            aggregates.append(aggregate)
        return tuple(sorted(aggregates, key=lambda item: item.key))

    async def _load_receipt(
        self,
        session: AsyncSessionLike,
        request_id: str,
    ) -> StorageTransactionReceipt | None:
        result = await session.execute(
            text(
                f"""
                SELECT request_id, request_fingerprint, outcome_fingerprint, committed_json
                FROM {self._schema.receipt_table}
                WHERE request_id = :request_id
                FOR UPDATE
                """
            ),
            {"request_id": request_id},
        )
        rows = list(result.mappings())
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("PostgreSQL receipt query returned duplicate request IDs")
        row = rows[0]
        committed_raw = row["committed_json"]
        if isinstance(committed_raw, str):
            committed_raw = json.loads(committed_raw)
        if not isinstance(committed_raw, list):
            raise ValueError("PostgreSQL receipt committed state is malformed")
        committed: list[StoredAggregate] = []
        for item in committed_raw:
            if not isinstance(item, Mapping):
                raise ValueError("PostgreSQL receipt aggregate is malformed")
            key = AggregateKey(item["aggregate_type"], item["aggregate_id"])
            aggregate = StoredAggregate(
                key,
                int(item["version"]),
                _decode_state(item["state_json"]),
            )
            if aggregate.state_fingerprint != item["state_fingerprint"]:
                raise ValueError("PostgreSQL receipt state fingerprint does not match bytes")
            committed.append(aggregate)
        return StorageTransactionReceipt(
            row["request_id"],
            row["request_fingerprint"],
            row["outcome_fingerprint"],
            tuple(sorted(committed, key=lambda item: item.key)),
        )

    async def _persist(
        self,
        session: AsyncSessionLike,
        request: StorageTransactionRequest,
        resolved: StorageTransactionResolution,
    ) -> None:
        by_key = {aggregate.key: aggregate for aggregate in resolved.aggregates}
        for mutation in request.mutations:
            aggregate = by_key[mutation.key]
            state_json = canonical_json(aggregate.state)
            if mutation.expected_version == 0:
                result = await session.execute(
                    text(
                        f"""
                        INSERT INTO {self._schema.aggregate_table}
                            (aggregate_type, aggregate_id, version, state_json, state_fingerprint)
                        VALUES (:aggregate_type, :aggregate_id, :version, :state_json, :state_fingerprint)
                        ON CONFLICT (aggregate_type, aggregate_id) DO NOTHING
                        """
                    ),
                    {
                        "aggregate_type": aggregate.key.aggregate_type,
                        "aggregate_id": aggregate.key.aggregate_id,
                        "version": aggregate.version,
                        "state_json": state_json,
                        "state_fingerprint": aggregate.state_fingerprint,
                    },
                )
            else:
                result = await session.execute(
                    text(
                        f"""
                        UPDATE {self._schema.aggregate_table}
                        SET version = :next_version,
                            state_json = :state_json,
                            state_fingerprint = :next_state_fingerprint
                        WHERE aggregate_type = :aggregate_type
                          AND aggregate_id = :aggregate_id
                          AND version = :expected_version
                          AND state_fingerprint = :expected_state_fingerprint
                        """
                    ),
                    {
                        "aggregate_type": aggregate.key.aggregate_type,
                        "aggregate_id": aggregate.key.aggregate_id,
                        "next_version": aggregate.version,
                        "state_json": state_json,
                        "next_state_fingerprint": aggregate.state_fingerprint,
                        "expected_version": mutation.expected_version,
                        "expected_state_fingerprint": mutation.expected_state_fingerprint,
                    },
                )
            if getattr(result, "rowcount", 0) != 1:
                raise _ConcurrentWriteConflict

        receipt = resolved.receipt
        if receipt is None:  # pragma: no cover - guarded by apply
            raise ValueError("storage resolution omitted its receipt")
        committed_json = json.dumps(
            [
                {
                    "aggregate_type": aggregate.key.aggregate_type,
                    "aggregate_id": aggregate.key.aggregate_id,
                    "version": aggregate.version,
                    "state_json": canonical_json(aggregate.state),
                    "state_fingerprint": aggregate.state_fingerprint,
                }
                for aggregate in receipt.committed
            ],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        result = await session.execute(
            text(
                f"""
                INSERT INTO {self._schema.receipt_table}
                    (request_id, request_fingerprint, outcome_fingerprint, committed_json)
                VALUES (:request_id, :request_fingerprint, :outcome_fingerprint, :committed_json)
                ON CONFLICT (request_id) DO NOTHING
                """
            ),
            {
                "request_id": receipt.request_id,
                "request_fingerprint": receipt.request_fingerprint,
                "outcome_fingerprint": receipt.outcome_fingerprint,
                "committed_json": committed_json,
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise _ConcurrentWriteConflict


def _reject(
    request: StorageTransactionRequest,
    current: Sequence[StoredAggregate],
    reason: str,
) -> StorageTransactionResolution:
    return StorageTransactionResolution(
        StorageTransactionDecision.REJECT,
        request.fingerprint,
        tuple(sorted(current, key=lambda item: item.key)),
        rejection_reason=reason,
    )


def _decode_aggregate_row(row: Mapping[str, Any]) -> StoredAggregate:
    """Decode and authenticate one aggregate row returned by PostgreSQL."""

    try:
        key = AggregateKey(row["aggregate_type"], row["aggregate_id"])
        aggregate = StoredAggregate(
            key,
            int(row["version"]),
            _decode_state(row["state_json"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL aggregate row is malformed") from error
    if aggregate.state_fingerprint != row["state_fingerprint"]:
        raise ValueError("PostgreSQL aggregate state fingerprint does not match bytes")
    return aggregate


def _decode_state(raw: Any) -> Any:
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, list):
        raise ValueError("PostgreSQL state JSON is malformed")
    return freeze_json(_decode_canonical(raw))


def _decode_canonical(value: Any) -> Any:
    if value == ["null"]:
        return None
    if not isinstance(value, list) or len(value) != 2 or not isinstance(value[0], str):
        raise ValueError("canonical state value is malformed")
    tag, payload = value
    if tag == "bool":
        if not isinstance(payload, bool):
            raise ValueError("canonical bool value is malformed")
        return payload
    if tag == "int":
        if not isinstance(payload, str):
            raise ValueError("canonical int value is malformed")
        return int(payload)
    if tag == "float":
        if not isinstance(payload, str):
            raise ValueError("canonical float value is malformed")
        return float.fromhex(payload)
    if tag == "str":
        if not isinstance(payload, str):
            raise ValueError("canonical string value is malformed")
        return payload
    if tag in {"tuple", "list", "set"}:
        if not isinstance(payload, list):
            raise ValueError("canonical sequence value is malformed")
        decoded = tuple(_decode_canonical(item) for item in payload)
        return decoded if tag != "list" else list(decoded)
    if tag == "mapping":
        if not isinstance(payload, list):
            raise ValueError("canonical mapping value is malformed")
        values: dict[str, Any] = {}
        for item in payload:
            if not isinstance(item, list) or len(item) != 2 or not isinstance(item[0], str):
                raise ValueError("canonical mapping entry is malformed")
            values[item[0]] = _decode_canonical(item[1])
        return MappingProxyType(values)
    if tag == "decimal":
        if not isinstance(payload, str):
            raise ValueError("canonical decimal value is malformed")
        try:
            sign, digits, exponent = payload.split(":")
            return Decimal((int(sign), tuple(int(item) for item in digits), int(exponent)))
        except (TypeError, ValueError) as error:
            raise ValueError("canonical decimal value is malformed") from error
    if tag == "datetime":
        if not isinstance(payload, str):
            raise ValueError("canonical datetime value is malformed")
        return datetime.fromisoformat(payload.replace("Z", "+00:00"))
    if tag == "date":
        if not isinstance(payload, str):
            raise ValueError("canonical date value is malformed")
        return date.fromisoformat(payload)
    raise ValueError(f"unsupported canonical state tag: {tag}")
