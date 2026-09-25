"""Owner-scoped PostgreSQL persistence for the forward shadow account ledger."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from app.strategy_lab_v2.canonical import canonical_json, content_digest, require_sha256_digest
from app.strategy_lab_v2.forward_account import (
    ForwardAccountDecision,
    ForwardAccountEvent,
    ForwardAccountState,
    apply_forward_account_event,
)
from app.strategy_lab_v2.postgres_forward_state import _principal_id, _statement
from app.strategy_lab_v2.postgres_result_materialization import decode_canonical_contract


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


class ForwardAccountStateDecision(StrEnum):
    REGISTERED = "registered"
    APPLIED = "applied"
    REPLAY_EXISTING = "replay_existing"
    CONFLICT = "conflict"
    NOT_FOUND = "not_found"
    OUT_OF_ORDER = "out_of_order"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class ForwardAccountStateResolution:
    decision: ForwardAccountStateDecision
    state: ForwardAccountState | None
    event_fingerprint: str | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ForwardAccountStateDecision):
            raise TypeError("decision must be a ForwardAccountStateDecision")
        if self.state is not None and not isinstance(self.state, ForwardAccountState):
            raise TypeError("state must be a ForwardAccountState or None")
        if self.event_fingerprint is not None:
            require_sha256_digest(self.event_fingerprint, field_name="event_fingerprint")
        failed = {
            ForwardAccountStateDecision.CONFLICT,
            ForwardAccountStateDecision.NOT_FOUND,
            ForwardAccountStateDecision.OUT_OF_ORDER,
            ForwardAccountStateDecision.REJECT,
        }
        if self.decision in failed and not self.rejection_reason:
            raise ValueError("failed account persistence resolutions require a reason")
        if self.decision not in failed and self.rejection_reason:
            raise ValueError("successful account persistence resolutions cannot contain a reason")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class PostgresForwardAccountSchema:
    """Additive table contract for one serialized shadow-account state."""

    account_table: str = "strategy_lab_v2_forward_accounts"

    def __post_init__(self) -> None:
        if not isinstance(self.account_table, str) or not re.fullmatch(
            r"[a-z_][a-z0-9_]*", self.account_table
        ):
            raise ValueError("account_table must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.account_table} (
                owner_id TEXT NOT NULL,
                instance_id TEXT NOT NULL,
                state_json TEXT NOT NULL,
                state_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, instance_id)
            )
            """,
        )


class PostgresForwardAccountAdapter:
    """Persist and replay authenticated forward shadow-account transitions."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresForwardAccountSchema | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresForwardAccountSchema()

    @property
    def schema(self) -> PostgresForwardAccountSchema:
        return self._schema

    async def initialize(
        self, *, principal: Any, state: ForwardAccountState
    ) -> ForwardAccountStateResolution:
        if not isinstance(state, ForwardAccountState):
            raise TypeError("state must be a ForwardAccountState")
        if state.last_event_sequence != -1:
            raise ValueError("account initialization requires an empty state")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load(session, owner_id, state.instance_id)
                if current is not None:
                    if current == state:
                        return ForwardAccountStateResolution(
                            ForwardAccountStateDecision.REPLAY_EXISTING, current
                        )
                    return ForwardAccountStateResolution(
                        ForwardAccountStateDecision.CONFLICT,
                        current,
                        rejection_reason="forward account is already bound to different state",
                    )
                await self._insert(session, owner_id, state)
                return ForwardAccountStateResolution(
                    ForwardAccountStateDecision.REGISTERED, state
                )

    async def load(self, *, principal: Any, instance_id: str) -> ForwardAccountState | None:
        if not isinstance(instance_id, str) or not instance_id.strip():
            raise ValueError("instance_id must not be empty")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                return await self._load(session, owner_id, instance_id)

    async def apply(
        self,
        *,
        principal: Any,
        event: ForwardAccountEvent,
    ) -> ForwardAccountStateResolution:
        if not isinstance(event, ForwardAccountEvent):
            raise TypeError("event must be a ForwardAccountEvent")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load(session, owner_id, event.instance_id)
                if current is None:
                    return ForwardAccountStateResolution(
                        ForwardAccountStateDecision.NOT_FOUND,
                        None,
                        event.event_fingerprint,
                        "forward account was not initialized",
                    )
                resolution = apply_forward_account_event(current, event)
                if resolution.decision is ForwardAccountDecision.APPLIED:
                    await self._update(session, owner_id, resolution.state)
                    return ForwardAccountStateResolution(
                        ForwardAccountStateDecision.APPLIED,
                        resolution.state,
                        event.event_fingerprint,
                    )
                mapped = ForwardAccountStateDecision(resolution.decision.value)
                return ForwardAccountStateResolution(
                    mapped,
                    resolution.state,
                    event.event_fingerprint,
                    resolution.rejection_reason,
                )

    async def _load(
        self, session: AsyncSessionLike, owner_id: str, instance_id: str
    ) -> ForwardAccountState | None:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, instance_id, state_json, state_fingerprint
                FROM {self._schema.account_table}
                WHERE owner_id = :owner_id AND instance_id = :instance_id
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id, "instance_id": instance_id},
        )
        rows = list(result.mappings())
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("PostgreSQL forward account query returned duplicate rows")
        row = rows[0]
        try:
            state = decode_canonical_contract(row["state_json"], ForwardAccountState)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("PostgreSQL forward account state is malformed") from error
        if row.get("owner_id") != owner_id or row.get("instance_id") != state.instance_id:
            raise ValueError("PostgreSQL forward account owner/identity drifted")
        if row.get("state_fingerprint") != state.fingerprint:
            raise ValueError("PostgreSQL forward account fingerprint does not match bytes")
        return state

    async def _insert(
        self, session: AsyncSessionLike, owner_id: str, state: ForwardAccountState
    ) -> None:
        payload = canonical_json(state)
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.account_table}
                    (owner_id, instance_id, state_json, state_fingerprint)
                VALUES (:owner_id, :instance_id, :state_json, :state_fingerprint)
                """
            ),
            {
                "owner_id": owner_id,
                "instance_id": state.instance_id,
                "state_json": payload,
                "state_fingerprint": state.fingerprint,
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("forward account insert lost a uniqueness race")

    async def _update(
        self, session: AsyncSessionLike, owner_id: str, state: ForwardAccountState
    ) -> None:
        payload = canonical_json(state)
        result = await session.execute(
            _statement(
                f"""
                UPDATE {self._schema.account_table}
                SET state_json = :state_json, state_fingerprint = :state_fingerprint
                WHERE owner_id = :owner_id AND instance_id = :instance_id
                """
            ),
            {
                "owner_id": owner_id,
                "instance_id": state.instance_id,
                "state_json": payload,
                "state_fingerprint": state.fingerprint,
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("forward account update lost its compare-and-set row")


__all__ = [
    "ForwardAccountStateDecision",
    "ForwardAccountStateResolution",
    "PostgresForwardAccountAdapter",
    "PostgresForwardAccountSchema",
]
