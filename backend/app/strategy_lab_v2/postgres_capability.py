"""Owner-scoped PostgreSQL persistence for capability summaries.

Capability summaries are immutable projections of data and engine preflight.
This adapter stores the projection for API/read-model use while leaving
provider entitlements, engine registration, and preflight calculation in their
engine-neutral or upstream-owned boundaries.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from app.strategy_lab_v2.canonical import require_sha256_digest
from app.strategy_lab_v2.capabilities import Degradation
from app.strategy_lab_v2.capability_summary import CapabilitySummary, CapabilitySummaryDecision


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


class CapabilitySummaryStateDecision(StrEnum):
    REGISTERED = "registered"
    REPLAY_EXISTING = "replay_existing"


@dataclass(frozen=True, slots=True)
class CapabilitySummaryStateResolution:
    decision: CapabilitySummaryStateDecision
    summary: CapabilitySummary

    def __post_init__(self) -> None:
        if not isinstance(self.decision, CapabilitySummaryStateDecision):
            raise TypeError("decision must be a CapabilitySummaryStateDecision")
        if not isinstance(self.summary, CapabilitySummary):
            raise TypeError("summary must be a CapabilitySummary")


@dataclass(frozen=True, slots=True)
class PostgresCapabilitySchema:
    """Explicit additive DDL for owner-scoped capability projections."""

    summary_table: str = "strategy_lab_v2_capability_summaries"

    def __post_init__(self) -> None:
        if not isinstance(self.summary_table, str) or not re.fullmatch(
            r"[a-z_][a-z0-9_]*", self.summary_table
        ):
            raise ValueError("summary_table must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.summary_table} (
                owner_id TEXT NOT NULL,
                report_fingerprint TEXT NOT NULL,
                binding_fingerprint TEXT NOT NULL,
                summary_fingerprint TEXT NOT NULL,
                decision TEXT NOT NULL,
                data_gaps_json TEXT NOT NULL,
                execution_gaps_json TEXT NOT NULL,
                degradations_json TEXT NOT NULL,
                ranking_eligible BOOLEAN NOT NULL,
                executable BOOLEAN NOT NULL,
                authoritative BOOLEAN NOT NULL,
                can_publish_authoritative_results BOOLEAN NOT NULL,
                PRIMARY KEY (owner_id, report_fingerprint, binding_fingerprint)
            )
            """,
        )


class PostgresCapabilityAdapter:
    """Persist and authenticate immutable owner-scoped capability summaries."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresCapabilitySchema | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresCapabilitySchema()

    @property
    def schema(self) -> PostgresCapabilitySchema:
        return self._schema

    async def ensure(
        self, *, principal: Any, summary: CapabilitySummary
    ) -> CapabilitySummaryStateResolution:
        """Register one summary or replay its exact immutable identity."""

        if not isinstance(summary, CapabilitySummary):
            raise TypeError("summary must be a CapabilitySummary")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_one(
                    session, owner_id, summary.report_fingerprint, summary.binding_fingerprint
                )
                if current is None:
                    await self._insert(session, owner_id, summary)
                    return CapabilitySummaryStateResolution(
                        CapabilitySummaryStateDecision.REGISTERED, summary
                    )
                if current != summary:
                    raise ValueError("PostgreSQL capability summary identity is already bound")
                return CapabilitySummaryStateResolution(
                    CapabilitySummaryStateDecision.REPLAY_EXISTING, current
                )

    async def load(
        self,
        *,
        principal: Any,
        report_fingerprint: str,
        binding_fingerprint: str,
    ) -> CapabilitySummary | None:
        """Read and authenticate one owner-scoped capability summary."""

        require_sha256_digest(report_fingerprint, field_name="report_fingerprint")
        require_sha256_digest(binding_fingerprint, field_name="binding_fingerprint")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                return await self._load_one(session, owner_id, report_fingerprint, binding_fingerprint)

    async def load_all(self, *, principal: Any) -> tuple[CapabilitySummary, ...]:
        """Read all summaries for a principal in fingerprint order."""

        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                result = await session.execute(
                    _statement(
                        f"""
                        SELECT owner_id, summary_fingerprint, report_fingerprint,
                               binding_fingerprint, decision, data_gaps_json,
                               execution_gaps_json, degradations_json, ranking_eligible,
                               executable, authoritative,
                               can_publish_authoritative_results
                        FROM {self._schema.summary_table}
                        WHERE owner_id = :owner_id
                        ORDER BY report_fingerprint ASC, binding_fingerprint ASC
                        FOR UPDATE
                        """
                    ),
                    {"owner_id": owner_id},
                )
                summaries = tuple(
                    _authenticate_row(row, owner_id) for row in result.mappings()
                )
                ordered = tuple(sorted(summaries, key=lambda item: item.fingerprint))
                if summaries != ordered:
                    raise ValueError("PostgreSQL capability summaries are not deterministically ordered")
                return summaries

    async def _load_one(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        report_fingerprint: str,
        binding_fingerprint: str,
    ) -> CapabilitySummary | None:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, summary_fingerprint, report_fingerprint,
                       binding_fingerprint, decision, data_gaps_json,
                       execution_gaps_json, degradations_json, ranking_eligible,
                       executable, authoritative,
                       can_publish_authoritative_results
                FROM {self._schema.summary_table}
                WHERE owner_id = :owner_id
                  AND report_fingerprint = :report_fingerprint
                  AND binding_fingerprint = :binding_fingerprint
                FOR UPDATE
                """
            ),
            {
                "owner_id": owner_id,
                "report_fingerprint": report_fingerprint,
                "binding_fingerprint": binding_fingerprint,
            },
        )
        rows = list(result.mappings())
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("PostgreSQL capability summary query returned duplicate keys")
        summary = _authenticate_row(rows[0], owner_id, report_fingerprint, binding_fingerprint)
        return summary

    async def _insert(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        summary: CapabilitySummary,
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.summary_table}
                    (owner_id, summary_fingerprint, report_fingerprint, binding_fingerprint,
                     decision, data_gaps_json, execution_gaps_json, degradations_json,
                     ranking_eligible, executable, authoritative,
                     can_publish_authoritative_results)
                VALUES (:owner_id, :summary_fingerprint, :report_fingerprint,
                        :binding_fingerprint, :decision, :data_gaps_json,
                        :execution_gaps_json, :degradations_json, :ranking_eligible,
                        :executable, :authoritative, :can_publish_authoritative_results)
                ON CONFLICT (owner_id, report_fingerprint, binding_fingerprint) DO NOTHING
                """
            ),
            _summary_values(owner_id, summary),
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL capability summary insert lost a uniqueness race")


def _principal_id(principal: Any) -> str:
    value = getattr(principal, "id", principal)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("authenticated principal identity is required")
    return value.strip()


def _summary_values(owner_id: str, summary: CapabilitySummary) -> dict[str, Any]:
    return {
        "owner_id": owner_id,
        "summary_fingerprint": summary.fingerprint,
        "report_fingerprint": summary.report_fingerprint,
        "binding_fingerprint": summary.binding_fingerprint,
        "decision": summary.decision.value,
        "data_gaps_json": json.dumps(list(summary.data_gaps), separators=(",", ":")),
        "execution_gaps_json": json.dumps(list(summary.execution_gaps), separators=(",", ":")),
        "degradations_json": json.dumps(
            [
                {
                    "instrument_id": item.instrument_id,
                    "field": item.field,
                    "substituted_value": item.substituted_value,
                    "reason": item.reason,
                }
                for item in summary.degradations
            ],
            separators=(",", ":"),
        ),
        "ranking_eligible": summary.ranking_eligible,
        "executable": summary.executable,
        "authoritative": summary.authoritative,
        "can_publish_authoritative_results": summary.can_publish_authoritative_results,
    }


def _authenticate_row(
    row: Mapping[str, Any],
    owner_id: str,
    report_fingerprint: str | None = None,
    binding_fingerprint: str | None = None,
) -> CapabilitySummary:
    summary = _decode_summary(row)
    if row.get("owner_id") != owner_id:
        raise ValueError("PostgreSQL capability summary owner identity drifted")
    if row.get("summary_fingerprint") != summary.fingerprint:
        raise ValueError("PostgreSQL capability summary fingerprint does not match bytes")
    if report_fingerprint is not None and summary.report_fingerprint != report_fingerprint:
        raise ValueError("PostgreSQL capability summary report identity drifted")
    if binding_fingerprint is not None and summary.binding_fingerprint != binding_fingerprint:
        raise ValueError("PostgreSQL capability summary binding identity drifted")
    return summary


def _decode_summary(row: Mapping[str, Any]) -> CapabilitySummary:
    try:
        data_gaps = _decode_string_list(row["data_gaps_json"], "data_gaps_json")
        execution_gaps = _decode_string_list(row["execution_gaps_json"], "execution_gaps_json")
        raw_degradations = json.loads(row["degradations_json"])
        if not isinstance(raw_degradations, list):
            raise ValueError("degradations_json must contain a list")
        degradations = tuple(
            Degradation(
                item["instrument_id"],
                item["field"],
                item["substituted_value"],
                item["reason"],
            )
            for item in raw_degradations
            if isinstance(item, dict)
        )
        if len(degradations) != len(raw_degradations):
            raise ValueError("degradations_json contains malformed entries")
        return CapabilitySummary(
            row["report_fingerprint"],
            row["binding_fingerprint"],
            CapabilitySummaryDecision(row["decision"]),
            data_gaps,
            execution_gaps,
            degradations,
            _decode_bool(row["ranking_eligible"], "ranking_eligible"),
            _decode_bool(row["executable"], "executable"),
            _decode_bool(row["authoritative"], "authoritative"),
            _decode_bool(
                row["can_publish_authoritative_results"],
                "can_publish_authoritative_results",
            ),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("PostgreSQL capability summary row is malformed") from error


def _decode_string_list(value: Any, field_name: str) -> tuple[str, ...]:
    values = json.loads(value)
    if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
        raise ValueError(f"{field_name} must contain a string list")
    return tuple(values)


def _decode_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _statement(sql: str) -> Any:
    from sqlalchemy import text

    return text(sql)


__all__ = [
    "CapabilitySummaryStateDecision",
    "CapabilitySummaryStateResolution",
    "PostgresCapabilityAdapter",
    "PostgresCapabilitySchema",
]
