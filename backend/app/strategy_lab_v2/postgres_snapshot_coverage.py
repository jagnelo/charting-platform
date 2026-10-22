"""Owner-scoped PostgreSQL persistence for snapshot coverage receipts."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from app.strategy_lab_v2.canonical import require_sha256_digest
from app.strategy_lab_v2.coverage import (
    CoverageVerificationDecision,
    CoverageVerificationReport,
)
from app.strategy_lab_v2.snapshot_coverage import (
    SnapshotCoverageDecision,
    SnapshotCoverageResolution,
)


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


class SnapshotCoverageStateDecision(StrEnum):
    REGISTERED = "registered"
    REPLAY_EXISTING = "replay_existing"


@dataclass(frozen=True, slots=True)
class SnapshotCoverageStateResolution:
    decision: SnapshotCoverageStateDecision
    resolution: SnapshotCoverageResolution

    def __post_init__(self) -> None:
        if not isinstance(self.decision, SnapshotCoverageStateDecision):
            raise TypeError("decision must be a SnapshotCoverageStateDecision")
        if not isinstance(self.resolution, SnapshotCoverageResolution):
            raise TypeError("resolution must be a SnapshotCoverageResolution")


@dataclass(frozen=True, slots=True)
class PostgresSnapshotCoverageSchema:
    """Explicit additive DDL for snapshot-bound coverage receipts."""

    resolution_table: str = "strategy_lab_v2_snapshot_coverage"

    def __post_init__(self) -> None:
        if not isinstance(self.resolution_table, str) or not re.fullmatch(
            r"[a-z_][a-z0-9_]*", self.resolution_table
        ):
            raise ValueError("resolution_table must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.resolution_table} (
                owner_id TEXT NOT NULL,
                snapshot_fingerprint TEXT NOT NULL,
                decision TEXT NOT NULL,
                reports_json TEXT NOT NULL,
                missing_series_digests_json TEXT NOT NULL,
                unexpected_series_digests_json TEXT NOT NULL,
                rejection_reason TEXT NULL,
                resolution_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, snapshot_fingerprint)
            )
            """,
        )


class PostgresSnapshotCoverageAdapter:
    """Persist and authenticate snapshot-bound coverage resolutions."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresSnapshotCoverageSchema | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresSnapshotCoverageSchema()

    @property
    def schema(self) -> PostgresSnapshotCoverageSchema:
        return self._schema

    async def ensure(
        self, *, principal: Any, resolution: SnapshotCoverageResolution
    ) -> SnapshotCoverageStateResolution:
        """Register one resolution or replay its exact snapshot identity."""

        if not isinstance(resolution, SnapshotCoverageResolution):
            raise TypeError("resolution must be a SnapshotCoverageResolution")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_one(session, owner_id, resolution.snapshot_fingerprint)
                if current is None:
                    await self._insert(session, owner_id, resolution)
                    return SnapshotCoverageStateResolution(
                        SnapshotCoverageStateDecision.REGISTERED, resolution
                    )
                if current != resolution:
                    raise ValueError("PostgreSQL snapshot coverage identity is already bound")
                return SnapshotCoverageStateResolution(
                    SnapshotCoverageStateDecision.REPLAY_EXISTING, current
                )

    async def load(
        self, *, principal: Any, snapshot_fingerprint: str
    ) -> SnapshotCoverageResolution | None:
        """Read and authenticate one snapshot-bound resolution."""

        require_sha256_digest(snapshot_fingerprint, field_name="snapshot_fingerprint")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                return await self._load_one(session, owner_id, snapshot_fingerprint)

    async def load_all(self, *, principal: Any) -> tuple[SnapshotCoverageResolution, ...]:
        """Read all resolutions for a principal in snapshot order."""

        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                result = await session.execute(
                    _statement(
                        f"""
                        SELECT owner_id, snapshot_fingerprint, decision, reports_json,
                               missing_series_digests_json,
                               unexpected_series_digests_json, rejection_reason,
                               resolution_fingerprint
                        FROM {self._schema.resolution_table}
                        WHERE owner_id = :owner_id
                        ORDER BY snapshot_fingerprint ASC
                        FOR UPDATE
                        """
                    ),
                    {"owner_id": owner_id},
                )
                resolutions = tuple(_authenticate_row(row, owner_id) for row in result.mappings())
                ordered = tuple(sorted(resolutions, key=lambda item: item.snapshot_fingerprint))
                if resolutions != ordered:
                    raise ValueError("PostgreSQL snapshot coverage rows are not deterministically ordered")
                return resolutions

    async def _load_one(
        self, session: AsyncSessionLike, owner_id: str, snapshot_fingerprint: str
    ) -> SnapshotCoverageResolution | None:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, snapshot_fingerprint, decision, reports_json,
                       missing_series_digests_json,
                       unexpected_series_digests_json, rejection_reason,
                       resolution_fingerprint
                FROM {self._schema.resolution_table}
                WHERE owner_id = :owner_id AND snapshot_fingerprint = :snapshot_fingerprint
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id, "snapshot_fingerprint": snapshot_fingerprint},
        )
        rows = list(result.mappings())
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("PostgreSQL snapshot coverage query returned duplicate keys")
        return _authenticate_row(rows[0], owner_id, snapshot_fingerprint)

    async def _insert(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        resolution: SnapshotCoverageResolution,
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.resolution_table}
                    (owner_id, snapshot_fingerprint, decision, reports_json,
                     missing_series_digests_json, unexpected_series_digests_json,
                     rejection_reason, resolution_fingerprint)
                VALUES (:owner_id, :snapshot_fingerprint, :decision, :reports_json,
                        :missing_series_digests_json, :unexpected_series_digests_json,
                        :rejection_reason, :resolution_fingerprint)
                ON CONFLICT (owner_id, snapshot_fingerprint) DO NOTHING
                """
            ),
            {
                "owner_id": owner_id,
                "snapshot_fingerprint": resolution.snapshot_fingerprint,
                "decision": resolution.decision.value,
                "reports_json": json.dumps(
                    [
                        {
                            "decision": report.decision.value,
                            "manifest_fingerprint": report.manifest_fingerprint,
                            "attestation_fingerprint": report.attestation_fingerprint,
                            "mismatches": list(report.mismatches),
                        }
                        for report in resolution.reports
                    ],
                    separators=(",", ":"),
                ),
                "missing_series_digests_json": json.dumps(
                    list(resolution.missing_series_digests), separators=(",", ":")
                ),
                "unexpected_series_digests_json": json.dumps(
                    list(resolution.unexpected_series_digests), separators=(",", ":")
                ),
                "rejection_reason": resolution.rejection_reason,
                "resolution_fingerprint": resolution.fingerprint,
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL snapshot coverage insert lost a uniqueness race")


def _principal_id(principal: Any) -> str:
    value = getattr(principal, "id", principal)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("authenticated principal identity is required")
    return value.strip()


def _authenticate_row(
    row: Mapping[str, Any], owner_id: str, snapshot_fingerprint: str | None = None
) -> SnapshotCoverageResolution:
    resolution = _decode_resolution(row)
    if row.get("owner_id") != owner_id:
        raise ValueError("PostgreSQL snapshot coverage owner identity drifted")
    if row.get("snapshot_fingerprint") != resolution.snapshot_fingerprint:
        raise ValueError("PostgreSQL snapshot coverage snapshot identity does not match bytes")
    if snapshot_fingerprint is not None and resolution.snapshot_fingerprint != snapshot_fingerprint:
        raise ValueError("PostgreSQL snapshot coverage snapshot identity drifted")
    if row.get("resolution_fingerprint") != resolution.fingerprint:
        raise ValueError("PostgreSQL snapshot coverage fingerprint does not match bytes")
    return resolution


def _decode_resolution(row: Mapping[str, Any]) -> SnapshotCoverageResolution:
    try:
        raw_reports = json.loads(row["reports_json"])
        if not isinstance(raw_reports, list):
            raise ValueError("reports_json must contain a list")
        reports: list[CoverageVerificationReport] = []
        for item in raw_reports:
            if not isinstance(item, dict):
                raise ValueError("reports_json contains malformed entries")
            reports.append(
                CoverageVerificationReport(
                    CoverageVerificationDecision(item["decision"]),
                    item["manifest_fingerprint"],
                    item["attestation_fingerprint"],
                    tuple(item["mismatches"]),
                )
            )
        missing = _decode_digest_list(row["missing_series_digests_json"], "missing_series_digests_json")
        unexpected = _decode_digest_list(
            row["unexpected_series_digests_json"], "unexpected_series_digests_json"
        )
        return SnapshotCoverageResolution(
            SnapshotCoverageDecision(row["decision"]),
            row["snapshot_fingerprint"],
            tuple(reports),
            missing,
            unexpected,
            row.get("rejection_reason"),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("PostgreSQL snapshot coverage row is malformed") from error


def _decode_digest_list(value: Any, field_name: str) -> tuple[str, ...]:
    values = json.loads(value)
    if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
        raise ValueError(f"{field_name} must contain a string list")
    for item in values:
        require_sha256_digest(item, field_name=f"{field_name} item")
    return tuple(values)


def _statement(sql: str) -> Any:
    from sqlalchemy import text

    return text(sql)


__all__ = [
    "PostgresSnapshotCoverageAdapter",
    "PostgresSnapshotCoverageSchema",
    "SnapshotCoverageStateDecision",
    "SnapshotCoverageStateResolution",
]
