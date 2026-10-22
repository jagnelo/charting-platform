"""Owner-scoped PostgreSQL persistence for provider coverage attestations.

Coverage evidence is supplied by the provider-platform adapter and verified by
the pure coverage contracts.  This module persists only the attestation
metadata and its digests; it performs no provider fetch, repair, or snapshot
admission and remains registration-neutral until shared migrations are open.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from app.strategy_lab_v2.canonical import require_sha256_digest
from app.strategy_lab_v2.contracts import AdjustmentMode, EventGranularity
from app.strategy_lab_v2.coverage import CoverageAttestation


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


class CoverageStateDecision(StrEnum):
    """Registration result for one immutable coverage attestation."""

    REGISTERED = "registered"
    REPLAY_EXISTING = "replay_existing"


@dataclass(frozen=True, slots=True)
class CoverageStateResolution:
    decision: CoverageStateDecision
    attestation: CoverageAttestation

    def __post_init__(self) -> None:
        if not isinstance(self.decision, CoverageStateDecision):
            raise TypeError("decision must be a CoverageStateDecision")
        if not isinstance(self.attestation, CoverageAttestation):
            raise TypeError("attestation must be a CoverageAttestation")


@dataclass(frozen=True, slots=True)
class PostgresCoverageSchema:
    """Explicit additive DDL for provider coverage attestations."""

    attestation_table: str = "strategy_lab_v2_coverage_attestations"

    def __post_init__(self) -> None:
        if not isinstance(self.attestation_table, str) or not re.fullmatch(
            r"[a-z_][a-z0-9_]*", self.attestation_table
        ):
            raise ValueError("attestation_table must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.attestation_table} (
                owner_id TEXT NOT NULL,
                series_content_digest TEXT NOT NULL,
                evidence_digest TEXT NOT NULL,
                instrument_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_granularity TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                session TEXT NOT NULL,
                feed TEXT NOT NULL,
                adjustment TEXT NOT NULL,
                corporate_action_semantics TEXT NOT NULL,
                start_at TEXT NOT NULL,
                end_at TEXT NOT NULL,
                row_count BIGINT NOT NULL,
                calendar_digest TEXT NOT NULL,
                complete BOOLEAN NOT NULL,
                gap_free BOOLEAN NOT NULL,
                provider_adapter TEXT NOT NULL,
                attested_at TEXT NOT NULL,
                attestation_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, series_content_digest)
            )
            """,
        )


class PostgresCoverageAdapter:
    """Persist and authenticate owner-scoped coverage evidence."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresCoverageSchema | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresCoverageSchema()

    @property
    def schema(self) -> PostgresCoverageSchema:
        return self._schema

    async def ensure(
        self, *, principal: Any, attestation: CoverageAttestation
    ) -> CoverageStateResolution:
        """Register one attestation or replay its exact immutable identity."""

        if not isinstance(attestation, CoverageAttestation):
            raise TypeError("attestation must be a CoverageAttestation")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_one(session, owner_id, attestation.series_content_digest)
                if current is None:
                    await self._insert(session, owner_id, attestation)
                    return CoverageStateResolution(CoverageStateDecision.REGISTERED, attestation)
                if current != attestation:
                    raise ValueError("PostgreSQL coverage attestation identity is already bound")
                return CoverageStateResolution(CoverageStateDecision.REPLAY_EXISTING, current)

    async def load(
        self, *, principal: Any, series_content_digest: str
    ) -> CoverageAttestation | None:
        """Read and authenticate one owner-scoped attestation."""

        require_sha256_digest(series_content_digest, field_name="series_content_digest")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                return await self._load_one(session, owner_id, series_content_digest)

    async def load_all(self, *, principal: Any) -> tuple[CoverageAttestation, ...]:
        """Read all owner attestations in deterministic series-digest order."""

        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                result = await session.execute(
                    _statement(
                        f"""
                        SELECT owner_id, series_content_digest, evidence_digest,
                               instrument_id, event_type, event_granularity, timeframe,
                               session, feed, adjustment, corporate_action_semantics,
                               start_at, end_at, row_count, calendar_digest, complete,
                               gap_free, provider_adapter, attested_at,
                               attestation_fingerprint
                        FROM {self._schema.attestation_table}
                        WHERE owner_id = :owner_id
                        ORDER BY series_content_digest ASC
                        FOR UPDATE
                        """
                    ),
                    {"owner_id": owner_id},
                )
                attestations: list[CoverageAttestation] = []
                for row in result.mappings():
                    attestations.append(_authenticate_row(row, owner_id))
                ordered = tuple(sorted(attestations, key=lambda item: item.series_content_digest))
                if tuple(attestations) != ordered:
                    raise ValueError("PostgreSQL coverage attestations are not deterministically ordered")
                return ordered

    async def _load_one(
        self, session: AsyncSessionLike, owner_id: str, series_content_digest: str
    ) -> CoverageAttestation | None:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, series_content_digest, evidence_digest,
                       instrument_id, event_type, event_granularity, timeframe,
                       session, feed, adjustment, corporate_action_semantics,
                       start_at, end_at, row_count, calendar_digest, complete,
                       gap_free, provider_adapter, attested_at,
                       attestation_fingerprint
                FROM {self._schema.attestation_table}
                WHERE owner_id = :owner_id AND series_content_digest = :series_content_digest
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id, "series_content_digest": series_content_digest},
        )
        rows = list(result.mappings())
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("PostgreSQL coverage query returned duplicate keys")
        return _authenticate_row(rows[0], owner_id, series_content_digest)

    async def _insert(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        attestation: CoverageAttestation,
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.attestation_table}
                    (owner_id, series_content_digest, evidence_digest, instrument_id,
                     event_type, event_granularity, timeframe, session, feed, adjustment,
                     corporate_action_semantics, start_at, end_at, row_count,
                     calendar_digest, complete, gap_free, provider_adapter, attested_at,
                     attestation_fingerprint)
                VALUES (:owner_id, :series_content_digest, :evidence_digest, :instrument_id,
                        :event_type, :event_granularity, :timeframe, :session, :feed,
                        :adjustment, :corporate_action_semantics, :start_at, :end_at,
                        :row_count, :calendar_digest, :complete, :gap_free,
                        :provider_adapter, :attested_at, :attestation_fingerprint)
                ON CONFLICT (owner_id, series_content_digest) DO NOTHING
                """
            ),
            _attestation_values(owner_id, attestation),
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL coverage insert lost a uniqueness race")


def _principal_id(principal: Any) -> str:
    value = getattr(principal, "id", principal)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("authenticated principal identity is required")
    return value.strip()


def _attestation_values(owner_id: str, attestation: CoverageAttestation) -> dict[str, Any]:
    return {
        "owner_id": owner_id,
        "series_content_digest": attestation.series_content_digest,
        "evidence_digest": attestation.evidence_digest,
        "instrument_id": attestation.instrument_id,
        "event_type": attestation.event_type,
        "event_granularity": attestation.event_granularity.value,
        "timeframe": attestation.timeframe,
        "session": attestation.session,
        "feed": attestation.feed,
        "adjustment": attestation.adjustment.value,
        "corporate_action_semantics": attestation.corporate_action_semantics,
        "start_at": _encode_datetime(attestation.start),
        "end_at": _encode_datetime(attestation.end),
        "row_count": attestation.row_count,
        "calendar_digest": attestation.calendar_digest,
        "complete": attestation.complete,
        "gap_free": attestation.gap_free,
        "provider_adapter": attestation.provider_adapter,
        "attested_at": _encode_datetime(attestation.attested_at),
        "attestation_fingerprint": attestation.fingerprint,
    }


def _authenticate_row(
    row: Mapping[str, Any], owner_id: str, series_content_digest: str | None = None
) -> CoverageAttestation:
    attestation = _decode_attestation(row)
    if row.get("owner_id") != owner_id:
        raise ValueError("PostgreSQL coverage owner identity drifted")
    if row.get("series_content_digest") != attestation.series_content_digest:
        raise ValueError("PostgreSQL coverage series identity does not match bytes")
    if series_content_digest is not None and attestation.series_content_digest != series_content_digest:
        raise ValueError("PostgreSQL coverage series identity drifted")
    if row.get("attestation_fingerprint") != attestation.fingerprint:
        raise ValueError("PostgreSQL coverage attestation fingerprint does not match bytes")
    return attestation


def _decode_attestation(row: Mapping[str, Any]) -> CoverageAttestation:
    try:
        return CoverageAttestation(
            row["evidence_digest"],
            row["series_content_digest"],
            row["instrument_id"],
            row["event_type"],
            EventGranularity(row["event_granularity"]),
            row["timeframe"],
            row["session"],
            row["feed"],
            AdjustmentMode(row["adjustment"]),
            row["corporate_action_semantics"],
            _decode_datetime(row["start_at"], "start_at"),
            _decode_datetime(row["end_at"], "end_at"),
            int(row["row_count"]),
            row["calendar_digest"],
            bool(row["complete"]),
            bool(row["gap_free"]),
            row["provider_adapter"],
            _decode_datetime(row["attested_at"], "attested_at"),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL coverage attestation row is malformed") from error


def _encode_datetime(value: datetime) -> str:
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
    "CoverageStateDecision",
    "CoverageStateResolution",
    "PostgresCoverageAdapter",
    "PostgresCoverageSchema",
]
