"""Owner-scoped PostgreSQL persistence for immutable result manifests.

Result-manifest construction remains pure in :mod:`result_materialization`.
This adapter retains the canonical manifest payload and a compact identity
projection, making successful engine evidence inspectable and retry-safe while
leaving artifact bytes and official publication to their existing gates.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from app.strategy_lab_v2.canonical import canonical_json, content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import (
    ArtifactManifest,
    DataSnapshot,
    MetricSet,
    PortfolioComposition,
    RunAttempt,
    RunResultManifest,
    ScientificTrial,
    StrategyPackage,
)
from app.strategy_lab_v2.result_materialization import (
    EngineResultEvidence,
    ResultMaterializationDecision,
    ResultMaterializationResolution,
    materialize_run_result,
)


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


class ResultManifestStateDecision(StrEnum):
    REGISTERED = "registered"
    REPLAY_EXISTING = "replay_existing"


@dataclass(frozen=True, slots=True)
class PersistedResultManifest:
    """Canonical manifest projection retained by PostgreSQL."""

    manifest_fingerprint: str
    attempt_id: str
    trial_id: str
    metric_set_fingerprint: str
    snapshot_fingerprint: str
    manifest_json: str
    record_fingerprint: str

    def __post_init__(self) -> None:
        for name in (
            "manifest_fingerprint",
            "trial_id",
            "metric_set_fingerprint",
            "snapshot_fingerprint",
            "record_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        for name in ("attempt_id", "manifest_json"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        if self.manifest_fingerprint != _payload_digest(self.manifest_json):
            raise ValueError("manifest fingerprint does not match canonical payload")

    @property
    def fingerprint(self) -> str:
        return content_digest(
            {
                "attempt_id": self.attempt_id,
                "manifest_fingerprint": self.manifest_fingerprint,
                "manifest_json": self.manifest_json,
                "metric_set_fingerprint": self.metric_set_fingerprint,
                "snapshot_fingerprint": self.snapshot_fingerprint,
                "trial_id": self.trial_id,
            }
        )


@dataclass(frozen=True, slots=True)
class ResultManifestStateResolution:
    decision: ResultManifestStateDecision
    manifest: RunResultManifest
    record: PersistedResultManifest

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ResultManifestStateDecision):
            raise TypeError("decision must be a ResultManifestStateDecision")
        if not isinstance(self.manifest, RunResultManifest):
            raise TypeError("manifest must be a RunResultManifest")
        if not isinstance(self.record, PersistedResultManifest):
            raise TypeError("record must be a PersistedResultManifest")


@dataclass(frozen=True, slots=True)
class PostgresResultMaterializationSchema:
    """Explicit additive DDL for immutable canonical result manifests."""

    manifest_table: str = "strategy_lab_v2_result_manifests"

    def __post_init__(self) -> None:
        if not isinstance(self.manifest_table, str) or not re.fullmatch(
            r"[a-z_][a-z0-9_]*", self.manifest_table
        ):
            raise ValueError("manifest_table must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.manifest_table} (
                owner_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                manifest_fingerprint TEXT NOT NULL,
                trial_id TEXT NOT NULL,
                metric_set_fingerprint TEXT NOT NULL,
                snapshot_fingerprint TEXT NOT NULL,
                manifest_json TEXT NOT NULL,
                record_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, attempt_id),
                UNIQUE (owner_id, manifest_fingerprint)
            )
            """,
        )


class PostgresResultMaterializationAdapter:
    """Persist and authenticate canonical result-manifest projections."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresResultMaterializationSchema | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresResultMaterializationSchema()

    @property
    def schema(self) -> PostgresResultMaterializationSchema:
        return self._schema

    async def ensure(
        self, *, principal: Any, manifest: RunResultManifest
    ) -> ResultManifestStateResolution:
        """Register a manifest or replay its exact immutable attempt identity."""

        if not isinstance(manifest, RunResultManifest):
            raise TypeError("manifest must be a RunResultManifest")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_one(session, owner_id, manifest.attempt_id)
                candidate = _record(manifest)
                if current is None:
                    await self._insert(session, owner_id, candidate)
                    return ResultManifestStateResolution(
                        ResultManifestStateDecision.REGISTERED, manifest, candidate
                    )
                if current.manifest_fingerprint != candidate.manifest_fingerprint:
                    raise ValueError("PostgreSQL result manifest attempt is already bound")
                if current != candidate:
                    raise ValueError("PostgreSQL result manifest payload is already bound")
                return ResultManifestStateResolution(
                    ResultManifestStateDecision.REPLAY_EXISTING, manifest, current
                )

    async def materialize(
        self,
        *,
        principal: Any,
        trial: ScientificTrial,
        attempt: RunAttempt,
        strategy_packages: Sequence[StrategyPackage],
        portfolio: PortfolioComposition,
        snapshot: DataSnapshot,
        evidence: EngineResultEvidence,
        metric_set: MetricSet,
        output_artifacts: Sequence[ArtifactManifest],
        created_at: datetime,
    ) -> ResultMaterializationResolution:
        """Build through the pure contract, then register its manifest atomically."""

        candidate = materialize_run_result(
            trial,
            attempt,
            strategy_packages,
            portfolio,
            snapshot,
            evidence,
            metric_set,
            output_artifacts,
            created_at=created_at,
        )
        if candidate.decision is not ResultMaterializationDecision.MATERIALIZE:
            return candidate
        if candidate.manifest is None:  # pragma: no cover - pure contract guard
            raise ValueError("materialization omitted its manifest")
        try:
            persisted = await self.ensure(principal=principal, manifest=candidate.manifest)
        except ValueError as error:
            if "already bound" not in str(error):
                raise
            return ResultMaterializationResolution(
                ResultMaterializationDecision.CONFLICT,
                candidate.candidate_fingerprint,
                candidate.manifest,
                str(error),
            )
        decision = (
            ResultMaterializationDecision.MATERIALIZE
            if persisted.decision is ResultManifestStateDecision.REGISTERED
            else ResultMaterializationDecision.REPLAY_EXISTING
        )
        return ResultMaterializationResolution(decision, candidate.candidate_fingerprint, candidate.manifest)

    async def load(
        self, *, principal: Any, attempt_id: str
    ) -> PersistedResultManifest | None:
        """Read the canonical manifest projection for one owner-scoped attempt."""

        _validate_attempt(attempt_id)
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                return await self._load_one(session, owner_id, attempt_id)

    async def load_all(self, *, principal: Any) -> tuple[PersistedResultManifest, ...]:
        """Read all retained manifest projections in deterministic attempt order."""

        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                result = await session.execute(
                    _statement(
                        f"""
                        SELECT owner_id, attempt_id, manifest_fingerprint, trial_id,
                               metric_set_fingerprint, snapshot_fingerprint,
                               manifest_json, record_fingerprint
                        FROM {self._schema.manifest_table}
                        WHERE owner_id = :owner_id
                        ORDER BY attempt_id ASC
                        FOR UPDATE
                        """
                    ),
                    {"owner_id": owner_id},
                )
                records = tuple(
                    self._authenticate(_decode_record(row), row, owner_id)
                    for row in result.mappings()
                )
                ordered = tuple(sorted(records, key=lambda item: item.attempt_id))
                if records != ordered:
                    raise ValueError("PostgreSQL result manifests are not deterministically ordered")
                return records

    async def _load_one(
        self, session: AsyncSessionLike, owner_id: str, attempt_id: str
    ) -> PersistedResultManifest | None:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, attempt_id, manifest_fingerprint, trial_id,
                       metric_set_fingerprint, snapshot_fingerprint,
                       manifest_json, record_fingerprint
                FROM {self._schema.manifest_table}
                WHERE owner_id = :owner_id AND attempt_id = :attempt_id
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id, "attempt_id": attempt_id},
        )
        rows = list(result.mappings())
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("PostgreSQL result manifest query returned duplicate keys")
        return self._authenticate(_decode_record(rows[0]), rows[0], owner_id, attempt_id)

    async def _insert(
        self, session: AsyncSessionLike, owner_id: str, record: PersistedResultManifest
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.manifest_table}
                    (owner_id, attempt_id, manifest_fingerprint, trial_id,
                     metric_set_fingerprint, snapshot_fingerprint, manifest_json,
                     record_fingerprint)
                VALUES (:owner_id, :attempt_id, :manifest_fingerprint, :trial_id,
                        :metric_set_fingerprint, :snapshot_fingerprint, :manifest_json,
                        :record_fingerprint)
                ON CONFLICT (owner_id, attempt_id) DO NOTHING
                """
            ),
            {
                "owner_id": owner_id,
                "attempt_id": record.attempt_id,
                "manifest_fingerprint": record.manifest_fingerprint,
                "trial_id": record.trial_id,
                "metric_set_fingerprint": record.metric_set_fingerprint,
                "snapshot_fingerprint": record.snapshot_fingerprint,
                "manifest_json": record.manifest_json,
                "record_fingerprint": record.record_fingerprint,
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL result manifest insert lost a uniqueness race")

    @staticmethod
    def _authenticate(
        record: PersistedResultManifest,
        row: Mapping[str, Any],
        owner_id: str,
        attempt_id: str | None = None,
    ) -> PersistedResultManifest:
        if row.get("owner_id") != owner_id:
            raise ValueError("PostgreSQL result manifest owner identity drifted")
        if attempt_id is not None and record.attempt_id != attempt_id:
            raise ValueError("PostgreSQL result manifest attempt identity drifted")
        if row.get("record_fingerprint") != record.fingerprint:
            raise ValueError("PostgreSQL result manifest fingerprint does not match bytes")
        return record


def _record(manifest: RunResultManifest) -> PersistedResultManifest:
    payload = canonical_json(manifest)
    record = PersistedResultManifest(
        manifest.fingerprint,
        manifest.attempt_id,
        manifest.trial_id,
        manifest.metric_set.fingerprint,
        manifest.snapshot_fingerprint,
        payload,
        content_digest(
            {
                "attempt_id": manifest.attempt_id,
                "manifest_fingerprint": manifest.fingerprint,
                "manifest_json": payload,
                "metric_set_fingerprint": manifest.metric_set.fingerprint,
                "snapshot_fingerprint": manifest.snapshot_fingerprint,
                "trial_id": manifest.trial_id,
            }
        ),
    )
    return record


def _payload_digest(payload: str) -> str:
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _decode_record(row: Mapping[str, Any]) -> PersistedResultManifest:
    try:
        return PersistedResultManifest(
            row["manifest_fingerprint"],
            row["attempt_id"],
            row["trial_id"],
            row["metric_set_fingerprint"],
            row["snapshot_fingerprint"],
            row["manifest_json"],
            row["record_fingerprint"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL result manifest row is malformed") from error


def _principal_id(principal: Any) -> str:
    value = getattr(principal, "id", principal)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("authenticated principal identity is required")
    return value.strip()


def _validate_attempt(attempt_id: str) -> None:
    if not isinstance(attempt_id, str) or not attempt_id.strip():
        raise ValueError("attempt_id must not be empty")


def _statement(sql: str) -> Any:
    from sqlalchemy import text

    return text(sql)


__all__ = [
    "PersistedResultManifest",
    "PostgresResultMaterializationAdapter",
    "PostgresResultMaterializationSchema",
    "ResultManifestStateDecision",
    "ResultManifestStateResolution",
]
