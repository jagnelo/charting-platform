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
    ForwardAccountHistoryEntry,
    ForwardAccountState,
    ForwardRuntimeExecutionReceipt,
    apply_forward_account_event,
)
from app.strategy_lab_v2.forward_admission import ForwardLiveAdmissionState
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
    execution_receipt_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ForwardAccountStateDecision):
            raise TypeError("decision must be a ForwardAccountStateDecision")
        if self.state is not None and not isinstance(self.state, ForwardAccountState):
            raise TypeError("state must be a ForwardAccountState or None")
        if self.event_fingerprint is not None:
            require_sha256_digest(self.event_fingerprint, field_name="event_fingerprint")
        if self.execution_receipt_fingerprint is not None:
            require_sha256_digest(
                self.execution_receipt_fingerprint,
                field_name="execution_receipt_fingerprint",
            )
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
        if self.decision in failed and self.execution_receipt_fingerprint is not None:
            raise ValueError("failed account persistence resolutions cannot confirm a receipt")
        if self.execution_receipt_fingerprint is not None and self.decision not in {
            ForwardAccountStateDecision.APPLIED,
            ForwardAccountStateDecision.REPLAY_EXISTING,
        }:
            raise ValueError("only applied account events can confirm an execution receipt")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class PostgresForwardAccountSchema:
    """Additive table contract for shadow-account state and replay history."""

    account_table: str = "strategy_lab_v2_forward_accounts"
    history_table: str = "strategy_lab_v2_forward_account_history"

    def __post_init__(self) -> None:
        for name, value in (
            ("account_table", self.account_table),
            ("history_table", self.history_table),
        ):
            if not isinstance(value, str) or not re.fullmatch(r"[a-z_][a-z0-9_]*", value):
                raise ValueError(f"{name} must be a safe SQL identifier")

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
            f"""
            CREATE TABLE {self.history_table} (
                owner_id TEXT NOT NULL,
                instance_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                entry_json TEXT NOT NULL,
                entry_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, instance_id, revision)
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
        self,
        *,
        principal: Any,
        state: ForwardAccountState,
        admission_state: ForwardLiveAdmissionState | None = None,
    ) -> ForwardAccountStateResolution:
        if not isinstance(state, ForwardAccountState):
            raise TypeError("state must be a ForwardAccountState")
        if state.last_event_sequence != -1:
            raise ValueError("account initialization requires an empty state")
        if admission_state is not None:
            if not isinstance(admission_state, ForwardLiveAdmissionState):
                raise TypeError("admission_state must use ForwardLiveAdmissionState")
            if admission_state.checkpoint.instance.instance_id != state.instance_id:
                raise ValueError("account baseline checkpoint belongs to another instance")
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load(session, owner_id, state.instance_id)
                if current is not None:
                    if current == state:
                        history = await self._load_history(session, owner_id, state.instance_id)
                        if not history:
                            await self._insert_history(
                                session,
                                owner_id,
                                ForwardAccountHistoryEntry(
                                    0,
                                    None,
                                    state.fingerprint,
                                    snapshot=state,
                                    baseline_checkpoint=(
                                        admission_state.checkpoint
                                        if admission_state is not None
                                        else None
                                    ),
                                    baseline_warmup_receipt_fingerprint=(
                                        admission_state.warmup_receipt_fingerprint
                                        if admission_state is not None
                                        else None
                                    ),
                                ),
                            )
                        return ForwardAccountStateResolution(
                            ForwardAccountStateDecision.REPLAY_EXISTING, current
                        )
                    return ForwardAccountStateResolution(
                        ForwardAccountStateDecision.CONFLICT,
                        current,
                        rejection_reason="forward account is already bound to different state",
                    )
                await self._insert(session, owner_id, state)
                await self._insert_history(
                    session,
                    owner_id,
                    ForwardAccountHistoryEntry(
                        0,
                        None,
                        state.fingerprint,
                        snapshot=state,
                        baseline_checkpoint=(
                            admission_state.checkpoint if admission_state is not None else None
                        ),
                        baseline_warmup_receipt_fingerprint=(
                            admission_state.warmup_receipt_fingerprint
                            if admission_state is not None
                            else None
                        ),
                    ),
                )
                return ForwardAccountStateResolution(ForwardAccountStateDecision.REGISTERED, state)

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
        execution_receipt: ForwardRuntimeExecutionReceipt | None = None,
    ) -> ForwardAccountStateResolution:
        if not isinstance(event, ForwardAccountEvent):
            raise TypeError("event must be a ForwardAccountEvent")
        if execution_receipt is not None:
            if not isinstance(execution_receipt, ForwardRuntimeExecutionReceipt):
                raise TypeError("execution_receipt must use ForwardRuntimeExecutionReceipt")
            if (
                execution_receipt.instance_id != event.instance_id
                or execution_receipt.event_id != event.event_id
                or execution_receipt.event_fingerprint != event.event_fingerprint
            ):
                raise ValueError("execution receipt does not match the account event")
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
                resolution = apply_forward_account_event(
                    current,
                    event,
                    execution_receipt=execution_receipt,
                )
                if resolution.decision is ForwardAccountDecision.APPLIED:
                    history = await self._load_history(session, owner_id, event.instance_id)
                    if not history:
                        await self._insert_history(
                            session,
                            owner_id,
                            ForwardAccountHistoryEntry(
                                0,
                                None,
                                current.fingerprint,
                                snapshot=current,
                            ),
                        )
                        history = await self._load_history(session, owner_id, event.instance_id)
                    if self._replay_history(history) != current:
                        raise ValueError("forward account history differs from stored state")
                    await self._update(
                        session,
                        owner_id,
                        resolution.state,
                        expected_fingerprint=current.fingerprint,
                    )
                    await self._insert_history(
                        session,
                        owner_id,
                        ForwardAccountHistoryEntry(
                            len(history),
                            current.fingerprint,
                            resolution.state.fingerprint,
                            event=event,
                            execution_receipt=execution_receipt,
                        ),
                    )
                    return ForwardAccountStateResolution(
                        ForwardAccountStateDecision.APPLIED,
                        resolution.state,
                        event.event_fingerprint,
                        execution_receipt_fingerprint=(
                            execution_receipt.fingerprint if execution_receipt is not None else None
                        ),
                    )
                if resolution.decision is ForwardAccountDecision.REPLAY_EXISTING:
                    return ForwardAccountStateResolution(
                        ForwardAccountStateDecision.REPLAY_EXISTING,
                        resolution.state,
                        event.event_fingerprint,
                        execution_receipt_fingerprint=(
                            execution_receipt.fingerprint if execution_receipt is not None else None
                        ),
                    )
                mapped = ForwardAccountStateDecision(resolution.decision.value)
                return ForwardAccountStateResolution(
                    mapped,
                    resolution.state,
                    event.event_fingerprint,
                    resolution.rejection_reason,
                )

    async def load_at_checkpoint(
        self,
        *,
        principal: Any,
        admission_state: ForwardLiveAdmissionState,
    ) -> ForwardAccountState | None:
        """Replay account effects through one authenticated admission checkpoint."""

        if not isinstance(admission_state, ForwardLiveAdmissionState):
            raise TypeError("admission_state must use ForwardLiveAdmissionState")
        checkpoint = admission_state.checkpoint
        instance_id = checkpoint.instance.instance_id
        owner_id = _principal_id(principal)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load(session, owner_id, instance_id)
                if current is None:
                    return None
                history = await self._load_history(session, owner_id, instance_id)
                if not history:
                    return None
                latest = self._replay_history(history)
                if latest != current:
                    raise ValueError("forward account history differs from stored state")
                root = history[0]
                baseline = root.snapshot
                baseline_checkpoint = root.baseline_checkpoint
                if baseline is None or baseline_checkpoint is None:
                    return None
                if (
                    root.baseline_warmup_receipt_fingerprint
                    != admission_state.warmup_receipt_fingerprint
                ):
                    return None
                if baseline.instance_id != instance_id:
                    raise ValueError("forward account history baseline belongs to another instance")

                base_checkpoint = baseline_checkpoint
                if (
                    base_checkpoint.instance.portfolio_fingerprint
                    != checkpoint.instance.portfolio_fingerprint
                    or base_checkpoint.instance.warmup_snapshot_fingerprint
                    != checkpoint.instance.warmup_snapshot_fingerprint
                    or base_checkpoint.instance.carry_in_mode != checkpoint.instance.carry_in_mode
                ):
                    return None
                base_event_ids = (
                    base_checkpoint.processed_event_ids
                    | base_checkpoint.buffered_event_ids
                    | base_checkpoint.correction_event_ids
                )
                target_event_ids = (
                    checkpoint.processed_event_ids
                    | checkpoint.buffered_event_ids
                    | checkpoint.correction_event_ids
                )
                if not base_event_ids.issubset(target_event_ids):
                    return None
                if (
                    checkpoint.instance.last_event_sequence
                    < base_checkpoint.instance.last_event_sequence
                ):
                    return None
                if checkpoint.fingerprint == base_checkpoint.fingerprint:
                    return baseline

                required = checkpoint.processed_event_ids - base_checkpoint.processed_event_ids
                if not required:
                    if (
                        checkpoint.instance.last_event_id == base_checkpoint.instance.last_event_id
                        and checkpoint.instance.last_event_sequence
                        == base_checkpoint.instance.last_event_sequence
                    ):
                        return baseline
                    return None

                transitions: dict[str, ForwardAccountHistoryEntry] = {}
                for item in history[1:]:
                    assert item.event is not None
                    if item.event.event_id in transitions:
                        raise ValueError("forward account history contains duplicate events")
                    transitions[item.event.event_id] = item
                if not required.issubset(transitions):
                    return None

                seen_by_id = {item.event_id: item for item in admission_state.seen_events}
                state = baseline
                for item in history[1:]:
                    event = item.event
                    assert event is not None
                    if event.event_id not in required:
                        continue
                    seen = seen_by_id.get(event.event_id)
                    if (
                        seen is None
                        or seen.event_fingerprint != event.event_fingerprint
                        or seen.sequence != event.sequence
                        or item.execution_receipt is None
                    ):
                        return None
                    resolution = apply_forward_account_event(
                        state,
                        event,
                        execution_receipt=item.execution_receipt,
                    )
                    if (
                        resolution.decision is not ForwardAccountDecision.APPLIED
                        or resolution.state.fingerprint != item.state_fingerprint
                    ):
                        raise ValueError(
                            "forward account checkpoint replay differs from its journal"
                        )
                    state = resolution.state
                if (
                    state.last_event_id != checkpoint.instance.last_event_id
                    or state.last_event_sequence != checkpoint.instance.last_event_sequence
                ):
                    return None
                return state

    async def _load_history(
        self, session: AsyncSessionLike, owner_id: str, instance_id: str
    ) -> tuple[ForwardAccountHistoryEntry, ...]:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, instance_id, revision, entry_json, entry_fingerprint
                FROM {self._schema.history_table}
                WHERE owner_id = :owner_id AND instance_id = :instance_id
                ORDER BY revision ASC
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id, "instance_id": instance_id},
        )
        entries: list[ForwardAccountHistoryEntry] = []
        for expected_revision, row in enumerate(result.mappings()):
            try:
                entry = decode_canonical_contract(row["entry_json"], ForwardAccountHistoryEntry)
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("PostgreSQL forward account history is malformed") from error
            if (
                row.get("owner_id") != owner_id
                or row.get("instance_id") != instance_id
                or row.get("revision") != expected_revision
                or entry.revision != expected_revision
                or entry.fingerprint != row.get("entry_fingerprint")
            ):
                raise ValueError("PostgreSQL forward account history identity drifted")
            entries.append(entry)
        return tuple(entries)

    async def _insert_history(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        entry: ForwardAccountHistoryEntry,
    ) -> None:
        if entry.snapshot is not None:
            instance_id = entry.snapshot.instance_id
        else:
            assert entry.event is not None
            instance_id = entry.event.instance_id
        entry_json = canonical_json(entry)
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.history_table}
                    (owner_id, instance_id, revision, entry_json, entry_fingerprint)
                VALUES (:owner_id, :instance_id, :revision, :entry_json, :entry_fingerprint)
                ON CONFLICT (owner_id, instance_id, revision) DO NOTHING
                """
            ),
            {
                "owner_id": owner_id,
                "instance_id": instance_id,
                "revision": entry.revision,
                "entry_json": entry_json,
                "entry_fingerprint": entry.fingerprint,
            },
        )
        if getattr(result, "rowcount", 0) == 1:
            return
        existing = await session.execute(
            _statement(
                f"""
                SELECT entry_json, entry_fingerprint
                FROM {self._schema.history_table}
                WHERE owner_id = :owner_id AND instance_id = :instance_id
                  AND revision = :revision
                """
            ),
            {"owner_id": owner_id, "instance_id": instance_id, "revision": entry.revision},
        )
        rows = list(existing.mappings())
        if (
            len(rows) != 1
            or rows[0].get("entry_json") != entry_json
            or rows[0].get("entry_fingerprint") != entry.fingerprint
        ):
            raise ValueError("PostgreSQL forward account history conflicted with other bytes")

    @staticmethod
    def _replay_history(entries: tuple[ForwardAccountHistoryEntry, ...]) -> ForwardAccountState:
        if not entries or entries[0].revision != 0 or entries[0].snapshot is None:
            raise ValueError("PostgreSQL forward account history is missing its root")
        state = entries[0].snapshot
        for expected_revision, entry in enumerate(entries[1:], start=1):
            if (
                entry.revision != expected_revision
                or entry.previous_state_fingerprint != state.fingerprint
            ):
                raise ValueError("PostgreSQL forward account history chain is discontinuous")
            if entry.event is None:
                raise ValueError("PostgreSQL forward account history transition omitted its event")
            resolution = apply_forward_account_event(
                state,
                entry.event,
                execution_receipt=entry.execution_receipt,
            )
            if (
                resolution.decision is not ForwardAccountDecision.APPLIED
                or resolution.state.fingerprint != entry.state_fingerprint
            ):
                raise ValueError("PostgreSQL forward account history replay is inconsistent")
            state = resolution.state
        return state

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
        self,
        session: AsyncSessionLike,
        owner_id: str,
        state: ForwardAccountState,
        *,
        expected_fingerprint: str | None = None,
    ) -> None:
        if expected_fingerprint is not None:
            require_sha256_digest(expected_fingerprint, field_name="expected_fingerprint")
        payload = canonical_json(state)
        result = await session.execute(
            _statement(
                f"""
                UPDATE {self._schema.account_table}
                SET state_json = :state_json, state_fingerprint = :state_fingerprint
                WHERE owner_id = :owner_id AND instance_id = :instance_id
                  AND (:expected_fingerprint IS NULL OR state_fingerprint = :expected_fingerprint)
                """
            ),
            {
                "owner_id": owner_id,
                "instance_id": state.instance_id,
                "expected_fingerprint": expected_fingerprint,
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
