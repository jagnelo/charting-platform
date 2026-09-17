"""PostgreSQL persistence for resumable, cancellable search experiments."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.strategy_lab_v2.search_state import (
    SearchCandidatePhase,
    SearchCandidateState,
    SearchExecutionState,
    SearchStateDecision,
    SearchStateResolution,
    record_search_candidate_terminal,
    request_search_cancellation,
    start_search_candidate,
)


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


@dataclass(frozen=True, slots=True)
class PostgresSearchStateSchema:
    """Explicit additive DDL for search queue and candidate checkpoints."""

    search_table: str = "strategy_lab_v2_search_states"
    candidate_table: str = "strategy_lab_v2_search_candidates"

    def __post_init__(self) -> None:
        for name, value in (
            ("search_table", self.search_table),
            ("candidate_table", self.candidate_table),
        ):
            if not isinstance(value, str) or not re.fullmatch(r"[a-z_][a-z0-9_]*", value):
                raise ValueError(f"{name} must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.search_table} (
                owner_id TEXT NOT NULL,
                experiment_fingerprint TEXT NOT NULL,
                cancellation_requested BOOLEAN NOT NULL,
                cancellation_request_id TEXT NULL,
                updated_at TEXT NULL,
                state_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, experiment_fingerprint)
            )
            """,
            f"""
            CREATE TABLE {self.candidate_table} (
                owner_id TEXT NOT NULL,
                experiment_fingerprint TEXT NOT NULL,
                candidate_index BIGINT NOT NULL,
                trial_fingerprint TEXT NOT NULL,
                phase TEXT NOT NULL,
                attempt_id TEXT NULL,
                attempt_count BIGINT NOT NULL,
                result_fingerprint TEXT NULL,
                updated_at TEXT NULL,
                state_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, experiment_fingerprint, candidate_index)
            )
            """,
        )


class PostgresSearchStateAdapter:
    """Persist search queue transitions through pure state resolvers and CAS."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresSearchStateSchema | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresSearchStateSchema()

    @property
    def schema(self) -> PostgresSearchStateSchema:
        return self._schema

    async def initialize(
        self, *, principal: Any, state: SearchExecutionState
    ) -> SearchStateResolution:
        """Create one immutable experiment queue or replay its exact state."""

        if not isinstance(state, SearchExecutionState):
            raise TypeError("state must be a SearchExecutionState")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_state(
                    session, owner_id, state.experiment_fingerprint
                )
                if current is not None:
                    if current == state:
                        return SearchStateResolution(SearchStateDecision.REPLAY_EXISTING, current)
                    return SearchStateResolution(
                        SearchStateDecision.REJECT,
                        current,
                        rejection_reason="search experiment is already bound to different content",
                    )
                await self._insert_search(session, owner_id, state)
                for candidate in state.candidates:
                    await self._insert_candidate(session, owner_id, state.experiment_fingerprint, candidate)
                return SearchStateResolution(SearchStateDecision.APPLY, state)

    async def load(
        self, *, principal: Any, experiment_fingerprint: str
    ) -> SearchExecutionState | None:
        _validate_digest(experiment_fingerprint, "experiment_fingerprint")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                return await self._load_state(session, owner_id, experiment_fingerprint)

    async def start_candidate(
        self,
        *,
        principal: Any,
        experiment_fingerprint: str,
        candidate_index: int,
        attempt_id: str,
        now: datetime,
    ) -> SearchStateResolution:
        """Start or retry a candidate and atomically persist the queue change."""

        return await self._mutate_candidate(
            principal=principal,
            experiment_fingerprint=experiment_fingerprint,
            resolver=lambda state: start_search_candidate(
                state, candidate_index, attempt_id=attempt_id, now=now
            ),
        )

    async def record_terminal(
        self,
        *,
        principal: Any,
        experiment_fingerprint: str,
        candidate_index: int,
        attempt_id: str,
        phase: SearchCandidatePhase,
        now: datetime,
        result_fingerprint: str | None = None,
    ) -> SearchStateResolution:
        """Persist one candidate terminal receipt with exact replay semantics."""

        return await self._mutate_candidate(
            principal=principal,
            experiment_fingerprint=experiment_fingerprint,
            resolver=lambda state: record_search_candidate_terminal(
                state,
                candidate_index,
                attempt_id=attempt_id,
                phase=phase,
                now=now,
                result_fingerprint=result_fingerprint,
            ),
        )

    async def cancel(
        self,
        *,
        principal: Any,
        experiment_fingerprint: str,
        request_id: str,
        now: datetime,
    ) -> SearchStateResolution:
        """Persist one idempotent experiment cancellation request."""

        _validate_digest(experiment_fingerprint, "experiment_fingerprint")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_state(session, owner_id, experiment_fingerprint)
                if current is None:
                    raise ValueError("search experiment was not found")
                resolution = request_search_cancellation(current, request_id=request_id, now=now)
                if resolution.decision is SearchStateDecision.APPLY:
                    await self._update_state(session, owner_id, current, resolution.state)
                return resolution

    async def _mutate_candidate(
        self,
        *,
        principal: Any,
        experiment_fingerprint: str,
        resolver: Any,
    ) -> SearchStateResolution:
        _validate_digest(experiment_fingerprint, "experiment_fingerprint")
        if not callable(resolver):
            raise TypeError("resolver must be callable")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_state(session, owner_id, experiment_fingerprint)
                if current is None:
                    raise ValueError("search experiment was not found")
                resolution = resolver(current)
                if not isinstance(resolution, SearchStateResolution):
                    raise TypeError("search resolver must return SearchStateResolution")
                if resolution.decision is SearchStateDecision.APPLY:
                    await self._update_state(session, owner_id, current, resolution.state)
                return resolution

    async def _load_state(
        self, session: AsyncSessionLike, owner_id: str, experiment_fingerprint: str
    ) -> SearchExecutionState | None:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, experiment_fingerprint, cancellation_requested,
                       cancellation_request_id, updated_at, state_fingerprint
                FROM {self._schema.search_table}
                WHERE owner_id = :owner_id AND experiment_fingerprint = :experiment_fingerprint
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id, "experiment_fingerprint": experiment_fingerprint},
        )
        search_rows = list(result.mappings())
        if not search_rows:
            return None
        if len(search_rows) != 1:
            raise ValueError("PostgreSQL search query returned duplicate keys")
        search = search_rows[0]
        if search.get("owner_id") != owner_id or search.get("experiment_fingerprint") != experiment_fingerprint:
            raise ValueError("PostgreSQL search owner/identity drifted")
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, experiment_fingerprint, candidate_index,
                       trial_fingerprint, phase, attempt_id, attempt_count,
                       result_fingerprint, updated_at, state_fingerprint
                FROM {self._schema.candidate_table}
                WHERE owner_id = :owner_id AND experiment_fingerprint = :experiment_fingerprint
                ORDER BY candidate_index ASC
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id, "experiment_fingerprint": experiment_fingerprint},
        )
        candidates: list[SearchCandidateState] = []
        candidate_rows: list[Mapping[str, Any]] = []
        for row in result.mappings():
            candidate = _decode_candidate(row)
            if row.get("owner_id") != owner_id or row.get("experiment_fingerprint") != experiment_fingerprint:
                raise ValueError("PostgreSQL candidate owner/identity drifted")
            if row.get("state_fingerprint") != candidate.fingerprint:
                raise ValueError("PostgreSQL candidate fingerprint does not match bytes")
            candidates.append(candidate)
            candidate_rows.append(row)
        ordered = tuple(sorted(candidates, key=lambda item: item.candidate_index))
        if tuple(candidates) != ordered:
            raise ValueError("PostgreSQL candidates are not deterministically ordered")
        if not ordered:
            raise ValueError("PostgreSQL search is missing candidate rows")
        state = SearchExecutionState(
            experiment_fingerprint,
            ordered,
            bool(search["cancellation_requested"]),
            search.get("cancellation_request_id"),
            _decode_optional_datetime(search.get("updated_at"), "updated_at"),
        )
        if search.get("state_fingerprint") != state.fingerprint:
            raise ValueError("PostgreSQL search fingerprint does not match bytes")
        return state

    async def _insert_search(
        self, session: AsyncSessionLike, owner_id: str, state: SearchExecutionState
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.search_table}
                    (owner_id, experiment_fingerprint, cancellation_requested,
                     cancellation_request_id, updated_at, state_fingerprint)
                VALUES (:owner_id, :experiment_fingerprint, :cancellation_requested,
                        :cancellation_request_id, :updated_at, :state_fingerprint)
                ON CONFLICT (owner_id, experiment_fingerprint) DO NOTHING
                """
            ),
            _search_values(owner_id, state),
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL search insert lost a uniqueness race")

    async def _insert_candidate(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        experiment_fingerprint: str,
        candidate: SearchCandidateState,
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.candidate_table}
                    (owner_id, experiment_fingerprint, candidate_index,
                     trial_fingerprint, phase, attempt_id, attempt_count,
                     result_fingerprint, updated_at, state_fingerprint)
                VALUES (:owner_id, :experiment_fingerprint, :candidate_index,
                        :trial_fingerprint, :phase, :attempt_id, :attempt_count,
                        :result_fingerprint, :updated_at, :state_fingerprint)
                ON CONFLICT (owner_id, experiment_fingerprint, candidate_index) DO NOTHING
                """
            ),
            _candidate_values(owner_id, experiment_fingerprint, candidate),
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL candidate insert lost a uniqueness race")

    async def _update_state(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        current: SearchExecutionState,
        next_state: SearchExecutionState,
    ) -> None:
        if current.experiment_fingerprint != next_state.experiment_fingerprint:
            raise ValueError("search experiment identity cannot change")
        for before, after in zip(current.candidates, next_state.candidates, strict=True):
            if before != after:
                values = _candidate_values(owner_id, current.experiment_fingerprint, after)
                values["expected_state_fingerprint"] = before.fingerprint
                result = await session.execute(
                    _statement(
                        f"""
                        UPDATE {self._schema.candidate_table}
                        SET trial_fingerprint = :trial_fingerprint, phase = :phase,
                            attempt_id = :attempt_id, attempt_count = :attempt_count,
                            result_fingerprint = :result_fingerprint, updated_at = :updated_at,
                            state_fingerprint = :state_fingerprint
                        WHERE owner_id = :owner_id
                          AND experiment_fingerprint = :experiment_fingerprint
                          AND candidate_index = :candidate_index
                          AND state_fingerprint = :expected_state_fingerprint
                        """
                    ),
                    values,
                )
                if getattr(result, "rowcount", 0) != 1:
                    raise ValueError("PostgreSQL candidate compare-and-set lost a race")
        values = _search_values(owner_id, next_state)
        values["expected_state_fingerprint"] = current.fingerprint
        result = await session.execute(
            _statement(
                f"""
                UPDATE {self._schema.search_table}
                SET cancellation_requested = :cancellation_requested,
                    cancellation_request_id = :cancellation_request_id,
                    updated_at = :updated_at, state_fingerprint = :state_fingerprint
                WHERE owner_id = :owner_id
                  AND experiment_fingerprint = :experiment_fingerprint
                  AND state_fingerprint = :expected_state_fingerprint
                """
            ),
            values,
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL search compare-and-set lost a race")


def _search_values(owner_id: str, state: SearchExecutionState) -> dict[str, Any]:
    return {
        "owner_id": owner_id,
        "experiment_fingerprint": state.experiment_fingerprint,
        "cancellation_requested": state.cancellation_requested,
        "cancellation_request_id": state.cancellation_request_id,
        "updated_at": _encode_optional_datetime(state.updated_at),
        "state_fingerprint": state.fingerprint,
    }


def _candidate_values(
    owner_id: str, experiment_fingerprint: str, candidate: SearchCandidateState
) -> dict[str, Any]:
    return {
        "owner_id": owner_id,
        "experiment_fingerprint": experiment_fingerprint,
        "candidate_index": candidate.candidate_index,
        "trial_fingerprint": candidate.trial_fingerprint,
        "phase": candidate.phase.value,
        "attempt_id": candidate.attempt_id,
        "attempt_count": candidate.attempt_count,
        "result_fingerprint": candidate.result_fingerprint,
        "updated_at": _encode_optional_datetime(candidate.updated_at),
        "state_fingerprint": candidate.fingerprint,
    }


def _decode_candidate(row: Mapping[str, Any]) -> SearchCandidateState:
    try:
        return SearchCandidateState(
            int(row["candidate_index"]),
            row["trial_fingerprint"],
            SearchCandidatePhase(row["phase"]),
            row.get("attempt_id"),
            int(row["attempt_count"]),
            row.get("result_fingerprint"),
            _decode_optional_datetime(row.get("updated_at"), "updated_at"),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL candidate row is malformed") from error


def _validate_digest(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise ValueError(f"{field_name} must be a sha256 content digest")


def _principal_id(principal: Any) -> str:
    value = getattr(principal, "id", principal)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("authenticated principal identity is required")
    return value.strip()


def _encode_optional_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _decode_optional_datetime(value: Any, field_name: str) -> datetime | None:
    if value is None:
        return None
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


__all__ = ["PostgresSearchStateAdapter", "PostgresSearchStateSchema"]
