"""Owner-scoped PostgreSQL persistence for runtime request/preflight evidence.

Runtime requests and isolation reports are immutable admission evidence.  This
adapter retains their canonical payloads and compact identities so a later
worker can prove which package, source, inputs, profile, and fail-closed
decision it consumed.  It does not start a process or change runtime state.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from app.strategy_lab_v2.canonical import canonical_json, content_digest, require_sha256_digest
from app.strategy_lab_v2.runtime_execution import (
    StrategyRuntimePreflight,
    StrategyRuntimeRequest,
)


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


class RuntimeReceiptDecision(StrEnum):
    REGISTERED = "registered"
    REPLAY_EXISTING = "replay_existing"


@dataclass(frozen=True, slots=True)
class PersistedRuntimeRequest:
    request_fingerprint: str
    request_id: str
    attempt_id: str
    package_fingerprint: str
    source_digest: str
    input_bundle_digest: str
    runtime_profile_fingerprint: str
    entrypoint: str
    submitted_at: datetime
    request_json: str
    record_fingerprint: str

    def __post_init__(self) -> None:
        for name in (
            "request_fingerprint",
            "request_id",
            "package_fingerprint",
            "source_digest",
            "input_bundle_digest",
            "runtime_profile_fingerprint",
            "record_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        _nonempty(self.attempt_id, "attempt_id")
        _nonempty(self.entrypoint, "entrypoint")
        _aware(self.submitted_at, "submitted_at")
        _nonempty(self.request_json, "request_json")
        if self.request_fingerprint != _payload_digest(self.request_json):
            raise ValueError("runtime request fingerprint does not match canonical payload")

    @property
    def fingerprint(self) -> str:
        return content_digest(
            {
                "attempt_id": self.attempt_id,
                "input_bundle_digest": self.input_bundle_digest,
                "package_fingerprint": self.package_fingerprint,
                "request_fingerprint": self.request_fingerprint,
                "request_id": self.request_id,
                "runtime_profile_fingerprint": self.runtime_profile_fingerprint,
                "source_digest": self.source_digest,
                "submitted_at": self.submitted_at,
                "entrypoint": self.entrypoint,
                "request_json": self.request_json,
            }
        )


@dataclass(frozen=True, slots=True)
class PersistedRuntimePreflight:
    preflight_fingerprint: str
    request_fingerprint: str
    profile_fingerprint: str
    isolation_report_fingerprint: str
    decision: str
    rejection_reasons: tuple[str, ...]
    preflight_json: str
    record_fingerprint: str

    def __post_init__(self) -> None:
        for name in (
            "preflight_fingerprint",
            "request_fingerprint",
            "profile_fingerprint",
            "isolation_report_fingerprint",
            "record_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        if self.decision not in {"allow", "reject"}:
            raise ValueError("runtime preflight decision is invalid")
        reasons = tuple(self.rejection_reasons)
        if len(reasons) != len(set(reasons)) or any(not value.strip() for value in reasons):
            raise ValueError("runtime preflight rejection reasons must be unique and non-empty")
        object.__setattr__(self, "rejection_reasons", reasons)
        _nonempty(self.preflight_json, "preflight_json")
        if self.preflight_fingerprint != _payload_digest(self.preflight_json):
            raise ValueError("runtime preflight fingerprint does not match canonical payload")

    @property
    def fingerprint(self) -> str:
        return content_digest(
            {
                "decision": self.decision,
                "isolation_report_fingerprint": self.isolation_report_fingerprint,
                "preflight_fingerprint": self.preflight_fingerprint,
                "preflight_json": self.preflight_json,
                "profile_fingerprint": self.profile_fingerprint,
                "rejection_reasons": self.rejection_reasons,
                "request_fingerprint": self.request_fingerprint,
            }
        )


@dataclass(frozen=True, slots=True)
class RuntimeReceiptResolution:
    decision: RuntimeReceiptDecision
    receipt: PersistedRuntimeRequest | PersistedRuntimePreflight

    def __post_init__(self) -> None:
        if not isinstance(self.decision, RuntimeReceiptDecision):
            raise TypeError("decision must be a RuntimeReceiptDecision")
        if not isinstance(self.receipt, PersistedRuntimeRequest | PersistedRuntimePreflight):
            raise TypeError("receipt must be a persisted runtime request or preflight")


@dataclass(frozen=True, slots=True)
class PostgresRuntimeReceiptSchema:
    """Explicit additive DDL for immutable runtime admission receipts."""

    request_table: str = "strategy_lab_v2_runtime_requests"
    preflight_table: str = "strategy_lab_v2_runtime_preflights"

    def __post_init__(self) -> None:
        for name, value in (
            ("request_table", self.request_table),
            ("preflight_table", self.preflight_table),
        ):
            if not isinstance(value, str) or not re.fullmatch(r"[a-z_][a-z0-9_]*", value):
                raise ValueError(f"{name} must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.request_table} (
                owner_id TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL,
                request_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                package_fingerprint TEXT NOT NULL,
                source_digest TEXT NOT NULL,
                input_bundle_digest TEXT NOT NULL,
                runtime_profile_fingerprint TEXT NOT NULL,
                entrypoint TEXT NOT NULL,
                submitted_at TEXT NOT NULL,
                request_json TEXT NOT NULL,
                record_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, request_fingerprint),
                UNIQUE (owner_id, attempt_id)
            )
            """,
            f"""
            CREATE TABLE {self.preflight_table} (
                owner_id TEXT NOT NULL,
                preflight_fingerprint TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL,
                profile_fingerprint TEXT NOT NULL,
                isolation_report_fingerprint TEXT NOT NULL,
                decision TEXT NOT NULL,
                rejection_reasons_json TEXT NOT NULL,
                preflight_json TEXT NOT NULL,
                record_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, preflight_fingerprint),
                UNIQUE (owner_id, request_fingerprint)
            )
            """,
        )


class PostgresRuntimeReceiptAdapter:
    """Persist and authenticate runtime request and preflight receipts."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresRuntimeReceiptSchema | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresRuntimeReceiptSchema()

    @property
    def schema(self) -> PostgresRuntimeReceiptSchema:
        return self._schema

    async def ensure_request(
        self, *, principal: Any, request: StrategyRuntimeRequest
    ) -> RuntimeReceiptResolution:
        if not isinstance(request, StrategyRuntimeRequest):
            raise TypeError("request must be a StrategyRuntimeRequest")
        owner_id = _principal_id(principal)
        candidate = _request_record(request)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_request(session, owner_id, request.fingerprint)
                if current is None:
                    current = await self._load_request(
                        session, owner_id, request.attempt_id, by_attempt=True
                    )
                if current is None:
                    await self._insert_request(session, owner_id, candidate)
                    return RuntimeReceiptResolution(RuntimeReceiptDecision.REGISTERED, candidate)
                if current != candidate:
                    raise ValueError("PostgreSQL runtime request identity is already bound")
                return RuntimeReceiptResolution(RuntimeReceiptDecision.REPLAY_EXISTING, current)

    async def ensure_preflight(
        self, *, principal: Any, preflight: StrategyRuntimePreflight
    ) -> RuntimeReceiptResolution:
        if not isinstance(preflight, StrategyRuntimePreflight):
            raise TypeError("preflight must be a StrategyRuntimePreflight")
        owner_id = _principal_id(principal)
        candidate = _preflight_record(preflight)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_preflight(session, owner_id, preflight.fingerprint)
                if current is None:
                    current = await self._load_preflight(
                        session, owner_id, preflight.request_fingerprint, by_request=True
                    )
                if current is None:
                    await self._insert_preflight(session, owner_id, candidate)
                    return RuntimeReceiptResolution(RuntimeReceiptDecision.REGISTERED, candidate)
                if current != candidate:
                    raise ValueError("PostgreSQL runtime preflight identity is already bound")
                return RuntimeReceiptResolution(RuntimeReceiptDecision.REPLAY_EXISTING, current)

    async def load_request(
        self, *, principal: Any, request_fingerprint: str
    ) -> PersistedRuntimeRequest | None:
        require_sha256_digest(request_fingerprint, field_name="request_fingerprint")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                return await self._load_request(session, owner_id, request_fingerprint)

    async def load_preflight(
        self, *, principal: Any, preflight_fingerprint: str
    ) -> PersistedRuntimePreflight | None:
        require_sha256_digest(preflight_fingerprint, field_name="preflight_fingerprint")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                return await self._load_preflight(session, owner_id, preflight_fingerprint)

    async def _load_request(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        fingerprint: str,
        *,
        by_attempt: bool = False,
    ) -> PersistedRuntimeRequest | None:
        column = "attempt_id" if by_attempt else "request_fingerprint"
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, request_fingerprint, request_id, attempt_id,
                       package_fingerprint, source_digest, input_bundle_digest,
                       runtime_profile_fingerprint, entrypoint, submitted_at,
                       request_json, record_fingerprint
                FROM {self._schema.request_table}
                WHERE owner_id = :owner_id AND {column} = :fingerprint
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id, "fingerprint": fingerprint},
        )
        rows = list(result.mappings())
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("PostgreSQL runtime request query returned duplicate keys")
        row = rows[0]
        record = _decode_request(row)
        if row.get("owner_id") != owner_id:
            raise ValueError("PostgreSQL runtime request identity drifted")
        if by_attempt and record.attempt_id != fingerprint:
            raise ValueError("PostgreSQL runtime request attempt identity drifted")
        if not by_attempt and record.request_fingerprint != fingerprint:
            raise ValueError("PostgreSQL runtime request identity drifted")
        if row.get("record_fingerprint") != record.fingerprint:
            raise ValueError("PostgreSQL runtime request fingerprint does not match bytes")
        return record

    async def _load_preflight(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        fingerprint: str,
        *,
        by_request: bool = False,
    ) -> PersistedRuntimePreflight | None:
        column = "request_fingerprint" if by_request else "preflight_fingerprint"
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, preflight_fingerprint, request_fingerprint,
                       profile_fingerprint, isolation_report_fingerprint, decision,
                       rejection_reasons_json, preflight_json, record_fingerprint
                FROM {self._schema.preflight_table}
                WHERE owner_id = :owner_id AND {column} = :fingerprint
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id, "fingerprint": fingerprint},
        )
        rows = list(result.mappings())
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("PostgreSQL runtime preflight query returned duplicate keys")
        row = rows[0]
        record = _decode_preflight(row)
        if row.get("owner_id") != owner_id:
            raise ValueError("PostgreSQL runtime preflight identity drifted")
        if by_request and record.request_fingerprint != fingerprint:
            raise ValueError("PostgreSQL runtime preflight request identity drifted")
        if not by_request and record.preflight_fingerprint != fingerprint:
            raise ValueError("PostgreSQL runtime preflight identity drifted")
        if row.get("record_fingerprint") != record.fingerprint:
            raise ValueError("PostgreSQL runtime preflight fingerprint does not match bytes")
        return record

    async def _insert_request(
        self, session: AsyncSessionLike, owner_id: str, record: PersistedRuntimeRequest
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.request_table}
                    (owner_id, request_fingerprint, request_id, attempt_id,
                     package_fingerprint, source_digest, input_bundle_digest,
                     runtime_profile_fingerprint, entrypoint, submitted_at,
                     request_json, record_fingerprint)
                VALUES (:owner_id, :request_fingerprint, :request_id, :attempt_id,
                        :package_fingerprint, :source_digest, :input_bundle_digest,
                        :runtime_profile_fingerprint, :entrypoint, :submitted_at,
                        :request_json, :record_fingerprint)
                ON CONFLICT (owner_id, request_fingerprint) DO NOTHING
                """
            ),
            {
                "owner_id": owner_id,
                "request_fingerprint": record.request_fingerprint,
                "request_id": record.request_id,
                "attempt_id": record.attempt_id,
                "package_fingerprint": record.package_fingerprint,
                "source_digest": record.source_digest,
                "input_bundle_digest": record.input_bundle_digest,
                "runtime_profile_fingerprint": record.runtime_profile_fingerprint,
                "entrypoint": record.entrypoint,
                "submitted_at": _encode_datetime(record.submitted_at),
                "request_json": record.request_json,
                "record_fingerprint": record.record_fingerprint,
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL runtime request insert lost a uniqueness race")

    async def _insert_preflight(
        self, session: AsyncSessionLike, owner_id: str, record: PersistedRuntimePreflight
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.preflight_table}
                    (owner_id, preflight_fingerprint, request_fingerprint,
                     profile_fingerprint, isolation_report_fingerprint, decision,
                     rejection_reasons_json, preflight_json, record_fingerprint)
                VALUES (:owner_id, :preflight_fingerprint, :request_fingerprint,
                        :profile_fingerprint, :isolation_report_fingerprint, :decision,
                        :rejection_reasons_json, :preflight_json, :record_fingerprint)
                ON CONFLICT (owner_id, preflight_fingerprint) DO NOTHING
                """
            ),
            {
                "owner_id": owner_id,
                "preflight_fingerprint": record.preflight_fingerprint,
                "request_fingerprint": record.request_fingerprint,
                "profile_fingerprint": record.profile_fingerprint,
                "isolation_report_fingerprint": record.isolation_report_fingerprint,
                "decision": record.decision,
                "rejection_reasons_json": json.dumps(
                    list(record.rejection_reasons), separators=(",", ":")
                ),
                "preflight_json": record.preflight_json,
                "record_fingerprint": record.record_fingerprint,
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL runtime preflight insert lost a uniqueness race")


def _request_record(request: StrategyRuntimeRequest) -> PersistedRuntimeRequest:
    identity = {
        "attempt_id": request.attempt_id,
        "entrypoint": request.entrypoint,
        "input_bundle_digest": request.input_bundle_digest,
        "isolation_request": request.isolation_request,
        "package_fingerprint": request.package_fingerprint,
        "request_id": request.request_id,
        "runtime_profile_fingerprint": request.runtime_profile_fingerprint,
        "source_digest": request.source_digest,
    }
    payload = canonical_json(identity)
    return PersistedRuntimeRequest(
        request.fingerprint,
        request.request_id,
        request.attempt_id,
        request.package_fingerprint,
        request.source_digest,
        request.input_bundle_digest,
        request.runtime_profile_fingerprint,
        request.entrypoint,
        request.submitted_at,
        payload,
        content_digest(
            {
                "attempt_id": request.attempt_id,
                "input_bundle_digest": request.input_bundle_digest,
                "package_fingerprint": request.package_fingerprint,
                "request_fingerprint": request.fingerprint,
                "request_id": request.request_id,
                "runtime_profile_fingerprint": request.runtime_profile_fingerprint,
                "source_digest": request.source_digest,
                "submitted_at": request.submitted_at,
                "entrypoint": request.entrypoint,
                "request_json": payload,
            }
        ),
    )


def _preflight_record(preflight: StrategyRuntimePreflight) -> PersistedRuntimePreflight:
    payload = canonical_json(preflight)
    return PersistedRuntimePreflight(
        preflight.fingerprint,
        preflight.request_fingerprint,
        preflight.profile_fingerprint,
        preflight.isolation_report.fingerprint,
        preflight.decision.value,
        preflight.rejection_reasons,
        payload,
        content_digest(
            {
                "decision": preflight.decision.value,
                "isolation_report_fingerprint": preflight.isolation_report.fingerprint,
                "preflight_fingerprint": preflight.fingerprint,
                "preflight_json": payload,
                "profile_fingerprint": preflight.profile_fingerprint,
                "rejection_reasons": preflight.rejection_reasons,
                "request_fingerprint": preflight.request_fingerprint,
            }
        ),
    )


def _decode_request(row: Mapping[str, Any]) -> PersistedRuntimeRequest:
    try:
        return PersistedRuntimeRequest(
            row["request_fingerprint"],
            row["request_id"],
            row["attempt_id"],
            row["package_fingerprint"],
            row["source_digest"],
            row["input_bundle_digest"],
            row["runtime_profile_fingerprint"],
            row["entrypoint"],
            _decode_datetime(row["submitted_at"], "submitted_at"),
            row["request_json"],
            row["record_fingerprint"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL runtime request row is malformed") from error


def _decode_preflight(row: Mapping[str, Any]) -> PersistedRuntimePreflight:
    try:
        raw_reasons = row["rejection_reasons_json"]
        if isinstance(raw_reasons, str):
            raw_reasons = json.loads(raw_reasons)
        if not isinstance(raw_reasons, list) or any(not isinstance(item, str) for item in raw_reasons):
            raise ValueError("rejection reasons must be a string list")
        return PersistedRuntimePreflight(
            row["preflight_fingerprint"],
            row["request_fingerprint"],
            row["profile_fingerprint"],
            row["isolation_report_fingerprint"],
            row["decision"],
            tuple(raw_reasons),
            row["preflight_json"],
            row["record_fingerprint"],
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("PostgreSQL runtime preflight row is malformed") from error


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
    "PersistedRuntimePreflight",
    "PersistedRuntimeRequest",
    "PostgresRuntimeReceiptAdapter",
    "PostgresRuntimeReceiptSchema",
    "RuntimeReceiptDecision",
    "RuntimeReceiptResolution",
]
