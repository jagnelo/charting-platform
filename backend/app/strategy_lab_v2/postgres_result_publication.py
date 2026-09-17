"""Owner-scoped PostgreSQL persistence for result-publication decisions.

Publication plans are immutable evidence produced by the pure authoritative
result gate.  This adapter stores publish, replay, and reject plans without
publishing bytes or changing execution state.  Exact plan retries replay;
changed plans remain separate immutable evidence and can be audited by
attempt.  Result publication and completion are intentionally separate so an
application wiring layer can require both records before exposing a result.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from app.strategy_lab_v2.canonical import require_sha256_digest
from app.strategy_lab_v2.result_publication import (
    ResultPublicationDecision,
    ResultPublicationPlan,
)


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


class PublicationStateDecision(StrEnum):
    REGISTERED = "registered"
    REPLAY_EXISTING = "replay_existing"


@dataclass(frozen=True, slots=True)
class PublicationStateResolution:
    """Registration result for one immutable publication plan."""

    decision: PublicationStateDecision
    plan: ResultPublicationPlan

    def __post_init__(self) -> None:
        if not isinstance(self.decision, PublicationStateDecision):
            raise TypeError("decision must be a PublicationStateDecision")
        if not isinstance(self.plan, ResultPublicationPlan):
            raise TypeError("plan must be a ResultPublicationPlan")


@dataclass(frozen=True, slots=True)
class PostgresResultPublicationSchema:
    """Explicit additive DDL for immutable publication-plan evidence."""

    publication_table: str = "strategy_lab_v2_result_publications"

    def __post_init__(self) -> None:
        if not isinstance(self.publication_table, str) or not re.fullmatch(
            r"[a-z_][a-z0-9_]*", self.publication_table
        ):
            raise ValueError("publication_table must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.publication_table} (
                owner_id TEXT NOT NULL,
                publication_fingerprint TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                result_fingerprint TEXT NOT NULL,
                reproduction_fingerprint TEXT NOT NULL,
                engine_build_digest TEXT NOT NULL,
                decision TEXT NOT NULL,
                rejection_reasons_json TEXT NOT NULL,
                PRIMARY KEY (owner_id, publication_fingerprint),
                UNIQUE (owner_id, attempt_id, publication_fingerprint)
            )
            """,
        )


class PostgresResultPublicationAdapter:
    """Persist and authenticate owner-scoped publication-plan evidence."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresResultPublicationSchema | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresResultPublicationSchema()

    @property
    def schema(self) -> PostgresResultPublicationSchema:
        return self._schema

    async def ensure(
        self, *, principal: Any, plan: ResultPublicationPlan
    ) -> PublicationStateResolution:
        """Register one plan or replay its exact immutable fingerprint."""

        if not isinstance(plan, ResultPublicationPlan):
            raise TypeError("plan must be a ResultPublicationPlan")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_one(session, owner_id, plan.fingerprint)
                if current is None:
                    await self._insert(session, owner_id, plan)
                    return PublicationStateResolution(
                        PublicationStateDecision.REGISTERED, plan
                    )
                if current != plan:
                    raise ValueError("PostgreSQL result publication identity is already bound")
                return PublicationStateResolution(
                    PublicationStateDecision.REPLAY_EXISTING, current
                )

    async def load(
        self, *, principal: Any, publication_fingerprint: str
    ) -> ResultPublicationPlan | None:
        """Read and authenticate one immutable plan for an owner."""

        require_sha256_digest(
            publication_fingerprint, field_name="publication_fingerprint"
        )
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                return await self._load_one(session, owner_id, publication_fingerprint)

    async def load_for_attempt(
        self, *, principal: Any, attempt_id: str
    ) -> tuple[ResultPublicationPlan, ...]:
        """Read all immutable plans for an attempt in fingerprint order."""

        _validate_attempt(attempt_id)
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                result = await session.execute(
                    _statement(
                        f"""
                        SELECT owner_id, publication_fingerprint, attempt_id,
                               result_fingerprint, reproduction_fingerprint,
                               engine_build_digest, decision, rejection_reasons_json
                        FROM {self._schema.publication_table}
                        WHERE owner_id = :owner_id AND attempt_id = :attempt_id
                        ORDER BY publication_fingerprint ASC
                        FOR UPDATE
                        """
                    ),
                    {"owner_id": owner_id, "attempt_id": attempt_id},
                )
                plans = tuple(
                    _authenticate_row(row, owner_id, attempt_id=attempt_id)
                    for row in result.mappings()
                )
                ordered = tuple(sorted(plans, key=lambda item: item.fingerprint))
                if plans != ordered:
                    raise ValueError(
                        "PostgreSQL result publications are not deterministically ordered"
                    )
                return plans

    async def load_all(self, *, principal: Any) -> tuple[ResultPublicationPlan, ...]:
        """Read all owner plans in attempt/fingerprint order."""

        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                result = await session.execute(
                    _statement(
                        f"""
                        SELECT owner_id, publication_fingerprint, attempt_id,
                               result_fingerprint, reproduction_fingerprint,
                               engine_build_digest, decision, rejection_reasons_json
                        FROM {self._schema.publication_table}
                        WHERE owner_id = :owner_id
                        ORDER BY attempt_id ASC, publication_fingerprint ASC
                        FOR UPDATE
                        """
                    ),
                    {"owner_id": owner_id},
                )
                plans = tuple(_authenticate_row(row, owner_id) for row in result.mappings())
                ordered = tuple(
                    sorted(plans, key=lambda item: (item.attempt_id, item.fingerprint))
                )
                if plans != ordered:
                    raise ValueError(
                        "PostgreSQL result publications are not deterministically ordered"
                    )
                return plans

    async def _load_one(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        publication_fingerprint: str,
    ) -> ResultPublicationPlan | None:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, publication_fingerprint, attempt_id,
                       result_fingerprint, reproduction_fingerprint,
                       engine_build_digest, decision, rejection_reasons_json
                FROM {self._schema.publication_table}
                WHERE owner_id = :owner_id
                  AND publication_fingerprint = :publication_fingerprint
                FOR UPDATE
                """
            ),
            {
                "owner_id": owner_id,
                "publication_fingerprint": publication_fingerprint,
            },
        )
        rows = list(result.mappings())
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("PostgreSQL result publication query returned duplicate keys")
        return _authenticate_row(rows[0], owner_id, publication_fingerprint=publication_fingerprint)

    async def _insert(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        plan: ResultPublicationPlan,
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.publication_table}
                    (owner_id, publication_fingerprint, attempt_id, result_fingerprint,
                     reproduction_fingerprint, engine_build_digest, decision,
                     rejection_reasons_json)
                VALUES (:owner_id, :publication_fingerprint, :attempt_id, :result_fingerprint,
                        :reproduction_fingerprint, :engine_build_digest, :decision,
                        :rejection_reasons_json)
                ON CONFLICT (owner_id, publication_fingerprint) DO NOTHING
                """
            ),
            {
                "owner_id": owner_id,
                "publication_fingerprint": plan.fingerprint,
                "attempt_id": plan.attempt_id,
                "result_fingerprint": plan.result_fingerprint,
                "reproduction_fingerprint": plan.reproduction_fingerprint,
                "engine_build_digest": plan.engine_build_digest,
                "decision": plan.decision.value,
                "rejection_reasons_json": json.dumps(
                    list(plan.rejection_reasons), separators=(",", ":")
                ),
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL result publication insert lost a uniqueness race")


def _principal_id(principal: Any) -> str:
    value = getattr(principal, "id", principal)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("authenticated principal identity is required")
    return value.strip()


def _validate_attempt(attempt_id: str) -> None:
    if not isinstance(attempt_id, str) or not attempt_id.strip():
        raise ValueError("attempt_id must not be empty")


def _authenticate_row(
    row: Mapping[str, Any],
    owner_id: str,
    *,
    publication_fingerprint: str | None = None,
    attempt_id: str | None = None,
) -> ResultPublicationPlan:
    plan = _decode_plan(row)
    if row.get("owner_id") != owner_id:
        raise ValueError("PostgreSQL result publication owner identity drifted")
    if row.get("publication_fingerprint") != plan.fingerprint:
        raise ValueError("PostgreSQL result publication fingerprint does not match bytes")
    if publication_fingerprint is not None and plan.fingerprint != publication_fingerprint:
        raise ValueError("PostgreSQL result publication identity drifted")
    if attempt_id is not None and plan.attempt_id != attempt_id:
        raise ValueError("PostgreSQL result publication attempt identity drifted")
    return plan


def _decode_plan(row: Mapping[str, Any]) -> ResultPublicationPlan:
    try:
        raw_reasons = row["rejection_reasons_json"]
        if isinstance(raw_reasons, str):
            raw_reasons = json.loads(raw_reasons)
        if not isinstance(raw_reasons, list) or any(
            not isinstance(item, str) for item in raw_reasons
        ):
            raise ValueError("rejection_reasons_json must contain a string list")
        return ResultPublicationPlan(
            result_fingerprint=row["result_fingerprint"],
            reproduction_fingerprint=row["reproduction_fingerprint"],
            attempt_id=row["attempt_id"],
            engine_build_digest=row["engine_build_digest"],
            decision=ResultPublicationDecision(row["decision"]),
            rejection_reasons=tuple(raw_reasons),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("PostgreSQL result publication row is malformed") from error


def _statement(sql: str) -> Any:
    from sqlalchemy import text

    return text(sql)


__all__ = [
    "PostgresResultPublicationAdapter",
    "PostgresResultPublicationSchema",
    "PublicationStateDecision",
    "PublicationStateResolution",
]
