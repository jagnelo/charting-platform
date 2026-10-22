"""PostgreSQL persistence for immutable artifact retention decisions.

This adapter keeps retention state separate from artifact bytes and manifest
publication. It re-authenticates every stored fingerprint and applies pin
changes under row locks with a fingerprint-guarded update. Expiry and tiering
remain explicit, clock-free decisions in :mod:`artifact_retention`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from app.strategy_lab_v2.artifact_retention import (
    ArtifactRetentionPin,
    ArtifactRetentionResolution,
    ArtifactRetentionState,
    RetentionPinDecision,
    RetentionPinResolution,
    add_retention_pin,
    release_retention_pin,
    resolve_artifact_retention,
)
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import ArtifactRetention


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


class RetentionStateDecision(StrEnum):
    REGISTERED = "registered"
    REPLAY_EXISTING = "replay_existing"


@dataclass(frozen=True, slots=True)
class RetentionStateResolution:
    """Registration result for one manifest-bound retention state."""

    decision: RetentionStateDecision
    state: ArtifactRetentionState

    def __post_init__(self) -> None:
        if not isinstance(self.decision, RetentionStateDecision):
            raise TypeError("decision must be a RetentionStateDecision")
        if not isinstance(self.state, ArtifactRetentionState):
            raise TypeError("state must be an ArtifactRetentionState")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class PostgresArtifactRetentionSchema:
    """Explicit additive DDL for manifest retention rows and pins."""

    retention_table: str = "strategy_lab_v2_artifact_retention"
    pin_table: str = "strategy_lab_v2_artifact_retention_pins"

    def __post_init__(self) -> None:
        for name, value in (("retention_table", self.retention_table), ("pin_table", self.pin_table)):
            if not isinstance(value, str) or not re.fullmatch(r"[a-z_][a-z0-9_]*", value):
                raise ValueError(f"{name} must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.retention_table} (
                manifest_fingerprint TEXT PRIMARY KEY,
                content_digest TEXT NOT NULL,
                retention_class TEXT NOT NULL,
                retention_eligible_at TEXT NULL,
                state_fingerprint TEXT NOT NULL
            )
            """,
            f"""
            CREATE TABLE {self.pin_table} (
                pin_id TEXT PRIMARY KEY,
                manifest_fingerprint TEXT NOT NULL,
                artifact_manifest_fingerprint TEXT NOT NULL,
                owner_type TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NULL,
                released_at TEXT NULL,
                pin_fingerprint TEXT NOT NULL,
                UNIQUE (manifest_fingerprint, pin_id)
            )
            """,
        )


class PostgresArtifactRetentionAdapter:
    """Persist manifest retention state and idempotent owner-scoped pins."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresArtifactRetentionSchema | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresArtifactRetentionSchema()

    @property
    def schema(self) -> PostgresArtifactRetentionSchema:
        return self._schema

    async def ensure_state(self, state: ArtifactRetentionState) -> RetentionStateResolution:
        """Register one immutable retention state or replay its exact identity."""

        _validate_state(state)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                persisted = await self._load_state(session, state.manifest_fingerprint)
                if persisted is None:
                    await self._insert_state(session, state)
                    for pin in state.pins:
                        await self._insert_pin(session, pin)
                    return RetentionStateResolution(RetentionStateDecision.REGISTERED, state)
                if persisted != state:
                    raise ValueError("PostgreSQL retention state identity is already bound")
                return RetentionStateResolution(
                    RetentionStateDecision.REPLAY_EXISTING,
                    persisted,
                )

    async def read_state(self, manifest_fingerprint: str) -> ArtifactRetentionState | None:
        """Read and authenticate one manifest-bound retention state."""

        require_sha256_digest(manifest_fingerprint, field_name="manifest_fingerprint")
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                return await self._load_state(session, manifest_fingerprint)

    async def add_pin(self, pin: ArtifactRetentionPin) -> RetentionPinResolution:
        """Add or replay one pin while retaining the manifest state atomically."""

        if not isinstance(pin, ArtifactRetentionPin):
            raise TypeError("pin must be an ArtifactRetentionPin")
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                state = await self._load_state(session, pin.artifact_manifest_fingerprint)
                if state is None:
                    raise ValueError("retention state is not registered")
                resolution = add_retention_pin(state, pin)
                if resolution.decision is RetentionPinDecision.ADD:
                    await self._insert_pin(session, pin)
                    await self._update_state(session, state, resolution.state)
                return resolution

    async def release_pin(
        self,
        *,
        manifest_fingerprint: str,
        pin_id: str,
        released_at: datetime,
    ) -> ArtifactRetentionState:
        """Release one pin idempotently with a fingerprint-guarded update."""

        require_sha256_digest(manifest_fingerprint, field_name="manifest_fingerprint")
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                state = await self._load_state(session, manifest_fingerprint)
                if state is None:
                    raise ValueError("retention state is not registered")
                next_state = release_retention_pin(
                    state,
                    pin_id=pin_id,
                    released_at=released_at,
                )
                if next_state == state:
                    return state
                current = next(item for item in state.pins if item.pin_id == pin_id)
                updated = next(item for item in next_state.pins if item.pin_id == pin_id)
                result = await session.execute(
                    _statement(
                        f"""
                        UPDATE {self._schema.pin_table}
                        SET released_at = :released_at, pin_fingerprint = :next_fingerprint
                        WHERE pin_id = :pin_id
                          AND manifest_fingerprint = :manifest_fingerprint
                          AND pin_fingerprint = :expected_fingerprint
                        """
                    ),
                    {
                        "released_at": _encode_datetime(updated.released_at),
                        "next_fingerprint": updated.fingerprint,
                        "pin_id": pin_id,
                        "manifest_fingerprint": manifest_fingerprint,
                        "expected_fingerprint": current.fingerprint,
                    },
                )
                if getattr(result, "rowcount", 0) != 1:
                    raise ValueError("PostgreSQL retention pin compare-and-set lost a race")
                await self._update_state(session, state, next_state)
                return next_state

    async def resolve(
        self, *, manifest_fingerprint: str, observed_at: datetime
    ) -> ArtifactRetentionResolution:
        """Resolve retention at an explicit instant without mutating state."""

        require_sha256_digest(manifest_fingerprint, field_name="manifest_fingerprint")
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                state = await self._load_state(session, manifest_fingerprint)
                if state is None:
                    raise ValueError("retention state is not registered")
                return resolve_artifact_retention(state, observed_at=observed_at)

    async def _load_state(
        self, session: AsyncSessionLike, manifest_fingerprint: str
    ) -> ArtifactRetentionState | None:
        result = await session.execute(
            _statement(
                f"""
                SELECT manifest_fingerprint, content_digest, retention_class,
                       retention_eligible_at, state_fingerprint
                FROM {self._schema.retention_table}
                WHERE manifest_fingerprint = :manifest_fingerprint
                FOR UPDATE
                """
            ),
            {"manifest_fingerprint": manifest_fingerprint},
        )
        rows = list(result.mappings())
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("PostgreSQL retention query returned duplicate keys")
        row = rows[0]
        state = _decode_state(row)
        if row.get("manifest_fingerprint") != manifest_fingerprint:
            raise ValueError("PostgreSQL retention manifest identity drifted")

        pin_result = await session.execute(
            _statement(
                f"""
                SELECT pin_id, manifest_fingerprint, artifact_manifest_fingerprint,
                       owner_type, owner_id, created_at, expires_at, released_at,
                       pin_fingerprint
                FROM {self._schema.pin_table}
                WHERE manifest_fingerprint = :manifest_fingerprint
                ORDER BY pin_id ASC
                FOR UPDATE
                """
            ),
            {"manifest_fingerprint": manifest_fingerprint},
        )
        pins: list[ArtifactRetentionPin] = []
        for pin_row in pin_result.mappings():
            pin = _decode_pin(pin_row)
            if pin_row.get("manifest_fingerprint") != manifest_fingerprint:
                raise ValueError("PostgreSQL retention pin manifest identity drifted")
            if pin_row.get("pin_fingerprint") != pin.fingerprint:
                raise ValueError("PostgreSQL retention pin fingerprint does not match bytes")
            pins.append(pin)
        ordered = tuple(sorted(pins, key=lambda item: item.pin_id))
        if tuple(pins) != ordered:
            raise ValueError("PostgreSQL retention pins are not deterministically ordered")
        authenticated = ArtifactRetentionState(
            state.manifest_fingerprint,
            state.content_digest,
            state.retention_class,
            state.retention_eligible_at,
            ordered,
        )
        if row.get("state_fingerprint") != authenticated.fingerprint:
            raise ValueError("PostgreSQL retention state fingerprint does not match bytes")
        return authenticated

    async def _insert_state(self, session: AsyncSessionLike, state: ArtifactRetentionState) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.retention_table}
                    (manifest_fingerprint, content_digest, retention_class,
                     retention_eligible_at, state_fingerprint)
                VALUES (:manifest_fingerprint, :content_digest, :retention_class,
                        :retention_eligible_at, :state_fingerprint)
                ON CONFLICT (manifest_fingerprint) DO NOTHING
                """
            ),
            {
                "manifest_fingerprint": state.manifest_fingerprint,
                "content_digest": state.content_digest,
                "retention_class": state.retention_class.value,
                "retention_eligible_at": _encode_datetime(state.retention_eligible_at),
                "state_fingerprint": state.fingerprint,
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL retention state insert lost a uniqueness race")

    async def _insert_pin(self, session: AsyncSessionLike, pin: ArtifactRetentionPin) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.pin_table}
                    (pin_id, manifest_fingerprint, artifact_manifest_fingerprint,
                     owner_type, owner_id, created_at, expires_at, released_at,
                     pin_fingerprint)
                VALUES (:pin_id, :manifest_fingerprint, :artifact_manifest_fingerprint,
                        :owner_type, :owner_id, :created_at, :expires_at, :released_at,
                        :pin_fingerprint)
                ON CONFLICT (pin_id) DO NOTHING
                """
            ),
            {
                "pin_id": pin.pin_id,
                "manifest_fingerprint": pin.artifact_manifest_fingerprint,
                "artifact_manifest_fingerprint": pin.artifact_manifest_fingerprint,
                "owner_type": pin.owner_type,
                "owner_id": pin.owner_id,
                "created_at": _encode_datetime(pin.created_at),
                "expires_at": _encode_datetime(pin.expires_at),
                "released_at": _encode_datetime(pin.released_at),
                "pin_fingerprint": pin.fingerprint,
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL retention pin insert lost a uniqueness race")

    async def _update_state(
        self,
        session: AsyncSessionLike,
        current: ArtifactRetentionState,
        next_state: ArtifactRetentionState,
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                UPDATE {self._schema.retention_table}
                SET state_fingerprint = :next_fingerprint
                WHERE manifest_fingerprint = :manifest_fingerprint
                  AND state_fingerprint = :expected_fingerprint
                """
            ),
            {
                "manifest_fingerprint": current.manifest_fingerprint,
                "next_fingerprint": next_state.fingerprint,
                "expected_fingerprint": current.fingerprint,
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL retention state compare-and-set lost a race")


def _validate_state(state: ArtifactRetentionState) -> None:
    if not isinstance(state, ArtifactRetentionState):
        raise TypeError("state must be an ArtifactRetentionState")


def _decode_state(row: Mapping[str, Any]) -> ArtifactRetentionState:
    try:
        return ArtifactRetentionState(
            row["manifest_fingerprint"],
            row["content_digest"],
            ArtifactRetention(row["retention_class"]),
            _decode_datetime(row["retention_eligible_at"], "retention_eligible_at")
            if row.get("retention_eligible_at") is not None
            else None,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL retention state row is malformed") from error


def _decode_pin(row: Mapping[str, Any]) -> ArtifactRetentionPin:
    try:
        return ArtifactRetentionPin(
            row["pin_id"],
            row["artifact_manifest_fingerprint"],
            row["owner_type"],
            row["owner_id"],
            _decode_datetime(row["created_at"], "created_at"),
            _decode_datetime(row["expires_at"], "expires_at")
            if row.get("expires_at") is not None
            else None,
            _decode_datetime(row["released_at"], "released_at")
            if row.get("released_at") is not None
            else None,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL retention pin row is malformed") from error


def _encode_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _decode_datetime(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name} is malformed") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return parsed


def _statement(sql: str) -> Any:
    from sqlalchemy import text

    return text(sql)


__all__ = [
    "PostgresArtifactRetentionAdapter",
    "PostgresArtifactRetentionSchema",
    "RetentionStateDecision",
    "RetentionStateResolution",
]
