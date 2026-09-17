"""Owner-scoped PostgreSQL persistence for versioned metric-set summaries."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from app.strategy_lab_v2.canonical import canonical_json, content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import MetricSet


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


class MetricSetStateDecision(StrEnum):
    REGISTERED = "registered"
    REPLAY_EXISTING = "replay_existing"


@dataclass(frozen=True, slots=True)
class PersistedMetricSet:
    metric_set_fingerprint: str
    metric_set_id: str
    trial_id: str
    attempt_id: str
    definition_version: str
    values_json: str
    created_at: datetime
    metric_set_json: str
    record_fingerprint: str

    def __post_init__(self) -> None:
        for name in ("metric_set_fingerprint", "trial_id", "record_fingerprint"):
            require_sha256_digest(getattr(self, name), field_name=name)
        for name in (
            "metric_set_id",
            "attempt_id",
            "definition_version",
            "values_json",
            "metric_set_json",
        ):
            _nonempty(getattr(self, name), name)
        _aware(self.created_at, "created_at")
        if self.metric_set_fingerprint != _payload_digest(self.metric_set_json):
            raise ValueError("metric-set fingerprint does not match canonical payload")

    @property
    def fingerprint(self) -> str:
        return content_digest(
            {
                "attempt_id": self.attempt_id,
                "created_at": self.created_at,
                "definition_version": self.definition_version,
                "metric_set_fingerprint": self.metric_set_fingerprint,
                "metric_set_id": self.metric_set_id,
                "metric_set_json": self.metric_set_json,
                "trial_id": self.trial_id,
                "values_json": self.values_json,
            }
        )


@dataclass(frozen=True, slots=True)
class MetricSetStateResolution:
    decision: str
    record: PersistedMetricSet

    def __post_init__(self) -> None:
        if self.decision not in {
            MetricSetStateDecision.REGISTERED,
            MetricSetStateDecision.REPLAY_EXISTING,
        }:
            raise ValueError("metric-set state decision is invalid")
        if not isinstance(self.record, PersistedMetricSet):
            raise TypeError("record must be a PersistedMetricSet")


@dataclass(frozen=True, slots=True)
class PostgresMetricsSchema:
    """Explicit additive DDL for immutable metric-set summaries."""

    metric_table: str = "strategy_lab_v2_metric_sets"

    def __post_init__(self) -> None:
        if not isinstance(self.metric_table, str) or not re.fullmatch(
            r"[a-z_][a-z0-9_]*", self.metric_table
        ):
            raise ValueError("metric_table must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.metric_table} (
                owner_id TEXT NOT NULL,
                metric_set_fingerprint TEXT NOT NULL,
                metric_set_id TEXT NOT NULL,
                trial_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                definition_version TEXT NOT NULL,
                values_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metric_set_json TEXT NOT NULL,
                record_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, metric_set_fingerprint),
                UNIQUE (owner_id, attempt_id)
            )
            """,
        )


class PostgresMetricsAdapter:
    """Persist and authenticate immutable metric-set summaries."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresMetricsSchema | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresMetricsSchema()

    @property
    def schema(self) -> PostgresMetricsSchema:
        return self._schema

    async def ensure(
        self, *, principal: Any, metric_set: MetricSet
    ) -> MetricSetStateResolution:
        if not isinstance(metric_set, MetricSet):
            raise TypeError("metric_set must be a MetricSet")
        owner_id = _principal_id(principal)
        candidate = _record(metric_set)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_by_fingerprint(
                    session, owner_id, metric_set.fingerprint
                )
                if current is None:
                    current = await self._load_by_attempt(
                        session, owner_id, metric_set.attempt_id
                    )
                if current is None:
                    await self._insert(session, owner_id, candidate)
                    return MetricSetStateResolution(
                        MetricSetStateDecision.REGISTERED, candidate
                    )
                if current != candidate:
                    raise ValueError("PostgreSQL metric-set attempt is already bound")
                return MetricSetStateResolution(
                    MetricSetStateDecision.REPLAY_EXISTING, current
                )

    async def load(
        self, *, principal: Any, metric_set_fingerprint: str
    ) -> PersistedMetricSet | None:
        require_sha256_digest(metric_set_fingerprint, field_name="metric_set_fingerprint")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                return await self._load_by_fingerprint(
                    session, owner_id, metric_set_fingerprint
                )

    async def load_all(self, *, principal: Any) -> tuple[PersistedMetricSet, ...]:
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                result = await session.execute(
                    _statement(
                        f"""
                        SELECT owner_id, metric_set_fingerprint, metric_set_id,
                               trial_id, attempt_id, definition_version, values_json,
                               created_at, metric_set_json, record_fingerprint
                        FROM {self._schema.metric_table}
                        WHERE owner_id = :owner_id
                        ORDER BY attempt_id ASC
                        FOR UPDATE
                        """
                    ),
                    {"owner_id": owner_id},
                )
                records = tuple(
                    self._authenticate(_decode(row), row, owner_id)
                    for row in result.mappings()
                )
                ordered = tuple(sorted(records, key=lambda item: item.attempt_id))
                if records != ordered:
                    raise ValueError("PostgreSQL metric sets are not deterministically ordered")
                return records

    async def _load_by_fingerprint(
        self, session: AsyncSessionLike, owner_id: str, fingerprint: str
    ) -> PersistedMetricSet | None:
        return await self._load(
            session, owner_id, fingerprint, where="metric_set_fingerprint"
        )

    async def _load_by_attempt(
        self, session: AsyncSessionLike, owner_id: str, attempt_id: str
    ) -> PersistedMetricSet | None:
        return await self._load(session, owner_id, attempt_id, where="attempt_id")

    async def _load(
        self, session: AsyncSessionLike, owner_id: str, key: str, *, where: str
    ) -> PersistedMetricSet | None:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, metric_set_fingerprint, metric_set_id,
                       trial_id, attempt_id, definition_version, values_json,
                       created_at, metric_set_json, record_fingerprint
                FROM {self._schema.metric_table}
                WHERE owner_id = :owner_id AND {where} = :lookup_key
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id, "lookup_key": key},
        )
        rows = list(result.mappings())
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("PostgreSQL metric-set query returned duplicate keys")
        row = rows[0]
        record = _decode(row)
        if row.get("owner_id") != owner_id:
            raise ValueError("PostgreSQL metric-set owner identity drifted")
        if where == "metric_set_fingerprint" and record.metric_set_fingerprint != key:
            raise ValueError("PostgreSQL metric-set identity drifted")
        if where == "attempt_id" and record.attempt_id != key:
            raise ValueError("PostgreSQL metric-set attempt identity drifted")
        return self._authenticate(record, row, owner_id)

    async def _insert(
        self, session: AsyncSessionLike, owner_id: str, record: PersistedMetricSet
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.metric_table}
                    (owner_id, metric_set_fingerprint, metric_set_id, trial_id,
                     attempt_id, definition_version, values_json, created_at,
                     metric_set_json, record_fingerprint)
                VALUES (:owner_id, :metric_set_fingerprint, :metric_set_id, :trial_id,
                        :attempt_id, :definition_version, :values_json, :created_at,
                        :metric_set_json, :record_fingerprint)
                ON CONFLICT (owner_id, metric_set_fingerprint) DO NOTHING
                """
            ),
            {
                "owner_id": owner_id,
                "metric_set_fingerprint": record.metric_set_fingerprint,
                "metric_set_id": record.metric_set_id,
                "trial_id": record.trial_id,
                "attempt_id": record.attempt_id,
                "definition_version": record.definition_version,
                "values_json": record.values_json,
                "created_at": _encode_datetime(record.created_at),
                "metric_set_json": record.metric_set_json,
                "record_fingerprint": record.record_fingerprint,
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL metric-set insert lost a uniqueness race")

    @staticmethod
    def _authenticate(
        record: PersistedMetricSet, row: Mapping[str, Any], owner_id: str
    ) -> PersistedMetricSet:
        if row.get("owner_id") != owner_id:
            raise ValueError("PostgreSQL metric-set owner identity drifted")
        if row.get("record_fingerprint") != record.fingerprint:
            raise ValueError("PostgreSQL metric-set fingerprint does not match bytes")
        return record


def _record(metric_set: MetricSet) -> PersistedMetricSet:
    metric_set_json = canonical_json(metric_set)
    return PersistedMetricSet(
        metric_set.fingerprint,
        metric_set.metric_set_id,
        metric_set.trial_id,
        metric_set.attempt_id,
        metric_set.definition_version,
        canonical_json(metric_set.values),
        metric_set.created_at,
        metric_set_json,
        content_digest(
            {
                "attempt_id": metric_set.attempt_id,
                "created_at": metric_set.created_at,
                "definition_version": metric_set.definition_version,
                "metric_set_fingerprint": metric_set.fingerprint,
                "metric_set_id": metric_set.metric_set_id,
                "metric_set_json": metric_set_json,
                "trial_id": metric_set.trial_id,
                "values_json": canonical_json(metric_set.values),
            }
        ),
    )


def _decode(row: Mapping[str, Any]) -> PersistedMetricSet:
    try:
        return PersistedMetricSet(
            row["metric_set_fingerprint"],
            row["metric_set_id"],
            row["trial_id"],
            row["attempt_id"],
            row["definition_version"],
            row["values_json"],
            _decode_datetime(row["created_at"], "created_at"),
            row["metric_set_json"],
            row["record_fingerprint"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL metric-set row is malformed") from error


def _payload_digest(payload: str) -> str:
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _principal_id(principal: Any) -> str:
    value = getattr(principal, "id", principal)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("authenticated principal identity is required")
    return value.strip()


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _encode_datetime(value: datetime) -> str:
    _aware(value, "datetime")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _decode_datetime(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name} is malformed") from error
    _aware(parsed, field_name)
    return parsed


def _statement(sql: str) -> Any:
    from sqlalchemy import text

    return text(sql)


__all__ = [
    "MetricSetStateResolution",
    "MetricSetStateDecision",
    "PersistedMetricSet",
    "PostgresMetricsAdapter",
    "PostgresMetricsSchema",
]
