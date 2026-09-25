"""Atomic PostgreSQL staging for search candidates and worker dispatch.

This adapter is the durable counterpart to :mod:`search_dispatch`.  It keeps
the provider/engine-owned authorization and runtime preflight inputs explicit,
but owns the transaction that locks search state, worker capacity, admission
receipts, dispatch identity, and the shared execution outbox.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.strategy_lab_v2.admission import (
    ExecutionAdmission,
    ExecutionAdmissionLedger,
)
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.dispatch import DispatchRequest
from app.strategy_lab_v2.execution import ExecutionAuthorization
from app.strategy_lab_v2.outbox import OutboxMessage
from app.strategy_lab_v2.postgres_search_state import PostgresSearchStateAdapter
from app.strategy_lab_v2.postgres_worker_state import PostgresWorkerStateAdapter
from app.strategy_lab_v2.runtime_execution import (
    StrategyRuntimePreflight,
    StrategyRuntimeRequest,
)
from app.strategy_lab_v2.search_dispatch import (
    SearchDispatchDecision,
    SearchDispatchResolution,
    resolve_search_dispatch,
)
from app.strategy_lab_v2.workers import WorkerReservation


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


@dataclass(frozen=True, slots=True)
class PostgresSearchDispatchSchema:
    """Additive tables for admission receipts and search dispatch intents.

    The outbox table is the existing shared
    ``strategy_lab_v2_execution_outbox`` table owned by the event transaction
    adapter.  This schema intentionally does not duplicate that DDL.
    """

    admission_table: str = "strategy_lab_v2_execution_admissions"
    dispatch_table: str = "strategy_lab_v2_search_dispatches"
    outbox_table: str = "strategy_lab_v2_execution_outbox"

    def __post_init__(self) -> None:
        for name, value in (
            ("admission_table", self.admission_table),
            ("dispatch_table", self.dispatch_table),
            ("outbox_table", self.outbox_table),
        ):
            if not isinstance(value, str) or not re.fullmatch(r"[a-z_][a-z0-9_]*", value):
                raise ValueError(f"{name} must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.admission_table} (
                owner_id TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL,
                authorization_fingerprint TEXT NOT NULL,
                runtime_request_fingerprint TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                worker_kind TEXT NOT NULL,
                worker_profile_fingerprint TEXT NOT NULL,
                reservation_id TEXT NOT NULL,
                admitted_at TEXT NOT NULL,
                authoritative BOOLEAN NOT NULL,
                admission_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, request_fingerprint),
                UNIQUE (owner_id, attempt_id),
                UNIQUE (owner_id, reservation_id)
            )
            """,
            f"""
            CREATE TABLE {self.dispatch_table} (
                owner_id TEXT NOT NULL,
                experiment_fingerprint TEXT NOT NULL,
                candidate_index BIGINT NOT NULL,
                idempotency_key TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                payload_digest TEXT NOT NULL,
                queue_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                dispatch_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, idempotency_key),
                UNIQUE (owner_id, experiment_fingerprint, candidate_index),
                UNIQUE (owner_id, request_fingerprint)
            )
            """,
        )


@dataclass(frozen=True, slots=True)
class SearchDispatchRecord:
    """Authenticated dispatch identity handed from Redis to a worker."""

    owner_id: str
    experiment_fingerprint: str
    candidate_index: int
    request: DispatchRequest

    def __post_init__(self) -> None:
        if not isinstance(self.owner_id, str) or not self.owner_id.strip():
            raise ValueError("owner_id must not be empty")
        require_sha256_digest(self.experiment_fingerprint, field_name="experiment_fingerprint")
        if (
            not isinstance(self.candidate_index, int)
            or isinstance(self.candidate_index, bool)
            or self.candidate_index < 0
        ):
            raise ValueError("candidate_index must be a non-negative integer")
        if not isinstance(self.request, DispatchRequest):
            raise TypeError("request must be a DispatchRequest")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class PostgresSearchDispatchAdapter:
    """Stage one candidate, admission, dispatch, and outbox atomically."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresSearchDispatchSchema | None = None,
        search_state: PostgresSearchStateAdapter | None = None,
        worker_state: PostgresWorkerStateAdapter | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresSearchDispatchSchema()
        self._search_state = search_state or PostgresSearchStateAdapter(session_factory)
        self._worker_state = worker_state or PostgresWorkerStateAdapter(session_factory)

    @property
    def schema(self) -> PostgresSearchDispatchSchema:
        return self._schema

    async def load(
        self,
        *,
        principal: Any,
        experiment_fingerprint: str,
        candidate_index: int,
    ) -> SearchDispatchRecord | None:
        """Load one owner-scoped dispatch identity for a worker or recovery task."""

        owner_id = _principal_id(principal)
        _validate_digest(experiment_fingerprint, "experiment_fingerprint")
        if (
            not isinstance(candidate_index, int)
            or isinstance(candidate_index, bool)
            or candidate_index < 0
        ):
            raise ValueError("candidate_index must be a non-negative integer")
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                rows = await self._select_dispatch_rows(
                    session,
                    "WHERE owner_id = :owner_id AND experiment_fingerprint = :experiment_fingerprint "
                    "AND candidate_index = :candidate_index",
                    {
                        "owner_id": owner_id,
                        "experiment_fingerprint": experiment_fingerprint,
                        "candidate_index": candidate_index,
                    },
                )
                return _single_dispatch_record(rows, owner_id=owner_id)

    async def load_by_request_fingerprint(
        self, request_fingerprint: str
    ) -> SearchDispatchRecord | None:
        """Resolve one dispatch from Redis content identity without guessing an owner."""

        _validate_digest(request_fingerprint, "request_fingerprint")
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                rows = await self._select_dispatch_rows(
                    session,
                    "WHERE request_fingerprint = :request_fingerprint",
                    {"request_fingerprint": request_fingerprint},
                )
                if len(rows) > 1:
                    raise ValueError("PostgreSQL search dispatch identity is ambiguous")
                return _single_dispatch_record(rows)

    async def dispatch(
        self,
        *,
        principal: Any,
        experiment_fingerprint: str,
        candidate_index: int,
        attempt_id: str,
        authorization: ExecutionAuthorization,
        runtime_request: StrategyRuntimeRequest,
        runtime_preflight: StrategyRuntimePreflight,
        reservation_id: str,
        dispatch_request: DispatchRequest,
        now: datetime,
    ) -> SearchDispatchResolution:
        """Resolve and persist one candidate dispatch in one SQL transaction."""

        owner_id = _principal_id(principal)
        _validate_digest(experiment_fingerprint, "experiment_fingerprint")
        if not isinstance(candidate_index, int) or isinstance(candidate_index, bool) or candidate_index < 0:
            raise ValueError("candidate_index must be a non-negative integer")
        if not isinstance(attempt_id, str) or not attempt_id.strip():
            raise ValueError("attempt_id must not be empty")
        if not isinstance(authorization, ExecutionAuthorization):
            raise TypeError("authorization must be an ExecutionAuthorization")
        if not isinstance(runtime_request, StrategyRuntimeRequest):
            raise TypeError("runtime_request must be a StrategyRuntimeRequest")
        if not isinstance(runtime_preflight, StrategyRuntimePreflight):
            raise TypeError("runtime_preflight must be a StrategyRuntimePreflight")
        if not isinstance(dispatch_request, DispatchRequest):
            raise TypeError("dispatch_request must be a DispatchRequest")
        _validate_digest(reservation_id, "reservation_id")
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("dispatch time must be timezone-aware")

        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                state = await self._search_state._load_state(
                    session, owner_id, experiment_fingerprint
                )
                if state is None:
                    raise ValueError("search experiment was not found")
                if authorization.attempt_id != attempt_id:
                    raise ValueError("authorization must reference the dispatch attempt")
                if runtime_request.attempt_id != attempt_id:
                    raise ValueError("runtime request must reference the dispatch attempt")
                profile = await self._worker_state._load_profile(
                    session, authorization.lease_worker_id
                )
                if profile is None:
                    raise ValueError("worker profile is not registered")
                pool = await self._worker_state._load_pool(session, profile)
                ledger = await self._load_admission_ledger(session, owner_id)
                prior_dispatches = await self._load_dispatches(
                    session, owner_id, experiment_fingerprint
                )
                resolution = resolve_search_dispatch(
                    state,
                    candidate_index=candidate_index,
                    attempt_id=attempt_id,
                    authorization=authorization,
                    runtime_request=runtime_request,
                    runtime_preflight=runtime_preflight,
                    admission_ledger=ledger,
                    pool=pool,
                    reservation_id=reservation_id,
                    dispatch_request=dispatch_request,
                    prior_dispatches=prior_dispatches,
                    now=now,
                )
                if resolution.decision not in {
                    SearchDispatchDecision.ENQUEUE,
                    SearchDispatchDecision.REPLAY_EXISTING,
                }:
                    return resolution
                if resolution.decision is SearchDispatchDecision.REPLAY_EXISTING:
                    return resolution
                await self._persist_resolution(
                    session,
                    owner_id,
                    candidate_index=candidate_index,
                    resolution=resolution,
                )
                return resolution

    async def _persist_resolution(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        *,
        candidate_index: int,
        resolution: SearchDispatchResolution,
    ) -> None:
        if resolution.dispatch_resolution is None or resolution.envelope is None:
            raise ValueError("enqueued search dispatch omitted dispatch evidence")
        current = await self._search_state._load_state(
            session, owner_id, resolution.search_state.experiment_fingerprint
        )
        if current is None:
            raise ValueError("search experiment disappeared during dispatch")
        if current != resolution.search_state:
            await self._search_state._update_state(
                session, owner_id, current, resolution.search_state
            )
        prior_admissions = await self._load_admission_ledger(session, owner_id)
        prior_fingerprints = {item.fingerprint for item in prior_admissions.admissions}
        new_admissions = tuple(
            item
            for item in resolution.admission_ledger.admissions
            if item.fingerprint not in prior_fingerprints
        )
        for admission in new_admissions:
            await self._insert_admission(session, owner_id, admission)
        if len(new_admissions) != 1:
            raise ValueError("enqueued search dispatch must add exactly one admission")
        reservation = next(
            (
                item
                for item in resolution.pool.reservations
                if item.reservation_id == new_admissions[0].reservation_id
            ),
            None,
        )
        if reservation is not None and reservation.active:
            existing = await self._load_reservation(
                session, resolution.pool.profile.worker_id, reservation.reservation_id
            )
            if existing is None:
                await self._worker_state._insert_reservation(session, reservation)
            elif existing != reservation:
                raise ValueError("worker reservation identity is already bound")
        await self._insert_dispatch(
            session,
            owner_id,
            resolution.search_state.experiment_fingerprint,
            candidate_index,
            resolution.envelope.request,
        )
        outbox = _search_outbox_message(
            owner_id,
            resolution.search_state.experiment_fingerprint,
            candidate_index,
            resolution.envelope.request,
        )
        await self._insert_outbox(session, outbox)

    async def _load_admission_ledger(
        self, session: AsyncSessionLike, owner_id: str
    ) -> ExecutionAdmissionLedger:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, request_fingerprint, authorization_fingerprint,
                       runtime_request_fingerprint, attempt_id, worker_id, worker_kind,
                       worker_profile_fingerprint, reservation_id, admitted_at,
                       authoritative, admission_fingerprint
                FROM {self._schema.admission_table}
                WHERE owner_id = :owner_id
                ORDER BY request_fingerprint ASC
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id},
        )
        admissions: list[ExecutionAdmission] = []
        for row in result.mappings():
            admission = _decode_admission(row)
            if row.get("owner_id") != owner_id:
                raise ValueError("PostgreSQL admission owner identity drifted")
            if row.get("admission_fingerprint") != admission.fingerprint:
                raise ValueError("PostgreSQL admission fingerprint does not match bytes")
            admissions.append(admission)
        return ExecutionAdmissionLedger(tuple(admissions))

    async def _load_dispatches(
        self, session: AsyncSessionLike, owner_id: str, experiment_fingerprint: str
    ) -> tuple[DispatchRequest, ...]:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, experiment_fingerprint, candidate_index,
                       idempotency_key, request_fingerprint, attempt_id,
                       payload_digest, queue_name, created_at, dispatch_fingerprint
                FROM {self._schema.dispatch_table}
                WHERE owner_id = :owner_id
                  AND experiment_fingerprint = :experiment_fingerprint
                ORDER BY request_fingerprint ASC
                FOR UPDATE
                """
            ),
            {"owner_id": owner_id, "experiment_fingerprint": experiment_fingerprint},
        )
        requests: list[DispatchRequest] = []
        for row in result.mappings():
            request = _decode_dispatch(row)
            if row.get("owner_id") != owner_id or row.get("experiment_fingerprint") != experiment_fingerprint:
                raise ValueError("PostgreSQL search dispatch owner/experiment drifted")
            if row.get("request_fingerprint") != request.fingerprint:
                raise ValueError("PostgreSQL search dispatch fingerprint does not match bytes")
            requests.append(request)
        return tuple(sorted(requests, key=lambda item: item.fingerprint))

    async def _select_dispatch_rows(
        self,
        session: AsyncSessionLike,
        predicate: str,
        params: Mapping[str, Any],
    ) -> list[Mapping[str, Any]]:
        result = await session.execute(
            _statement(
                f"""
                SELECT owner_id, experiment_fingerprint, candidate_index,
                       idempotency_key, request_fingerprint, attempt_id,
                       payload_digest, queue_name, created_at, dispatch_fingerprint
                FROM {self._schema.dispatch_table}
                {predicate}
                ORDER BY request_fingerprint ASC
                FOR SHARE
                """
            ),
            params,
        )
        return list(result.mappings())

    async def _load_reservation(
        self, session: AsyncSessionLike, worker_id: str, reservation_id: str
    ) -> WorkerReservation | None:
        result = await session.execute(
            _statement(
                f"""
                SELECT reservation_id, worker_id, kind, attempt_id, acquired_at,
                       released_at, reservation_fingerprint
                FROM {self._worker_state.schema.reservation_table}
                WHERE worker_id = :worker_id AND reservation_id = :reservation_id
                FOR UPDATE
                """
            ),
            {"worker_id": worker_id, "reservation_id": reservation_id},
        )
        rows = list(result.mappings())
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("PostgreSQL worker reservation query returned duplicate keys")
        row = rows[0]
        reservation = _decode_reservation(row)
        if row.get("reservation_fingerprint") != reservation.fingerprint:
            raise ValueError("PostgreSQL worker reservation fingerprint does not match bytes")
        return reservation

    async def _insert_admission(
        self, session: AsyncSessionLike, owner_id: str, admission: ExecutionAdmission
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.admission_table}
                    (owner_id, request_fingerprint, authorization_fingerprint,
                     runtime_request_fingerprint, attempt_id, worker_id, worker_kind,
                     worker_profile_fingerprint, reservation_id, admitted_at,
                     authoritative, admission_fingerprint)
                VALUES (:owner_id, :request_fingerprint, :authorization_fingerprint,
                        :runtime_request_fingerprint, :attempt_id, :worker_id, :worker_kind,
                        :worker_profile_fingerprint, :reservation_id, :admitted_at,
                        :authoritative, :admission_fingerprint)
                ON CONFLICT (owner_id, request_fingerprint) DO NOTHING
                """
            ),
            {
                "owner_id": owner_id,
                "request_fingerprint": admission.request_fingerprint,
                "authorization_fingerprint": admission.authorization_fingerprint,
                "runtime_request_fingerprint": admission.runtime_request_fingerprint,
                "attempt_id": admission.attempt_id,
                "worker_id": admission.worker_id,
                "worker_kind": admission.worker_kind.value,
                "worker_profile_fingerprint": admission.worker_profile_fingerprint,
                "reservation_id": admission.reservation_id,
                "admitted_at": _encode_datetime(admission.admitted_at),
                "authoritative": admission.authoritative,
                "admission_fingerprint": admission.fingerprint,
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL admission insert lost a uniqueness race")

    async def _insert_dispatch(
        self,
        session: AsyncSessionLike,
        owner_id: str,
        experiment_fingerprint: str,
        candidate_index: int,
        request: DispatchRequest,
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.dispatch_table}
                    (owner_id, experiment_fingerprint, candidate_index,
                     idempotency_key, request_fingerprint, attempt_id,
                     payload_digest, queue_name, created_at, dispatch_fingerprint)
                VALUES (:owner_id, :experiment_fingerprint, :candidate_index,
                        :idempotency_key, :request_fingerprint, :attempt_id,
                        :payload_digest, :queue_name, :created_at, :dispatch_fingerprint)
                ON CONFLICT (owner_id, idempotency_key) DO NOTHING
                """
            ),
            {
                "owner_id": owner_id,
                "experiment_fingerprint": experiment_fingerprint,
                "candidate_index": candidate_index,
                "idempotency_key": request.idempotency_key,
                "request_fingerprint": request.fingerprint,
                "attempt_id": request.attempt_id,
                "payload_digest": request.payload_digest,
                "queue_name": request.queue_name,
                "created_at": _encode_datetime(request.created_at),
                "dispatch_fingerprint": request.fingerprint,
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL search dispatch insert lost a uniqueness race")

    async def _insert_outbox(self, session: AsyncSessionLike, message: OutboxMessage) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.outbox_table}
                    (message_id, message_fingerprint, request_id, aggregate_type,
                     aggregate_id, event_id, topic, payload_digest, created_at,
                     available_at, published)
                VALUES (:message_id, :message_fingerprint, :request_id, :aggregate_type,
                        :aggregate_id, :event_id, :topic, :payload_digest, :created_at,
                        :available_at, FALSE)
                ON CONFLICT (message_id) DO NOTHING
                """
            ),
            {
                "message_id": message.message_id,
                "message_fingerprint": message.fingerprint,
                "request_id": message.request_id,
                "aggregate_type": message.aggregate_type,
                "aggregate_id": message.aggregate_id,
                "event_id": message.event_id,
                "topic": message.topic,
                "payload_digest": message.payload_digest,
                "created_at": _encode_datetime(message.created_at),
                "available_at": _encode_datetime(message.available_at),
            },
        )
        if getattr(result, "rowcount", 0) not in (0, 1):
            raise ValueError("PostgreSQL search outbox insert failed")


def _search_outbox_message(
    owner_id: str,
    experiment_fingerprint: str,
    candidate_index: int,
    request: DispatchRequest,
) -> OutboxMessage:
    event_id = content_digest(
        {
            "owner_id": owner_id,
            "experiment_fingerprint": experiment_fingerprint,
            "candidate_index": candidate_index,
            "dispatch_fingerprint": request.fingerprint,
        }
    )
    request_id = content_digest(
        {
            "owner_id": owner_id,
            "experiment_fingerprint": experiment_fingerprint,
            "candidate_index": candidate_index,
            "dispatch_fingerprint": request.fingerprint,
            "kind": "search-dispatch-outbox",
        }
    )
    return OutboxMessage(
        request_id=request_id,
        aggregate_type="strategy_search_candidate",
        aggregate_id=f"{experiment_fingerprint}:{candidate_index}",
        event_id=event_id,
        topic=request.queue_name,
        payload_digest=request.payload_digest,
        created_at=request.created_at,
        available_at=request.created_at,
    )


def _decode_admission(row: Mapping[str, Any]) -> ExecutionAdmission:
    from app.strategy_lab_v2.workers import WorkerKind

    try:
        admission = ExecutionAdmission(
            row["request_fingerprint"],
            row["authorization_fingerprint"],
            row["runtime_request_fingerprint"],
            row["attempt_id"],
            row["worker_id"],
            WorkerKind(row["worker_kind"]),
            row["worker_profile_fingerprint"],
            row["reservation_id"],
            _decode_datetime(row["admitted_at"], "admitted_at"),
            row["authoritative"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL admission row is malformed") from error
    return admission


def _decode_dispatch(row: Mapping[str, Any]) -> DispatchRequest:
    try:
        request = DispatchRequest(
            row["idempotency_key"],
            row["attempt_id"],
            row["payload_digest"],
            row["queue_name"],
            _decode_datetime(row["created_at"], "created_at"),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL search dispatch row is malformed") from error
    return request


def _single_dispatch_record(
    rows: list[Mapping[str, Any]], *, owner_id: str | None = None
) -> SearchDispatchRecord | None:
    if not rows:
        return None
    if len(rows) != 1:
        raise ValueError("PostgreSQL search dispatch query returned duplicate identities")
    row = rows[0]
    row_owner = row.get("owner_id")
    if not isinstance(row_owner, str) or not row_owner.strip():
        raise ValueError("PostgreSQL search dispatch owner is malformed")
    if owner_id is not None and row_owner != owner_id:
        raise ValueError("PostgreSQL search dispatch owner identity drifted")
    experiment = row.get("experiment_fingerprint")
    if not isinstance(experiment, str):
        raise ValueError("PostgreSQL search dispatch experiment identity is malformed")
    request = _decode_dispatch(row)
    if row.get("request_fingerprint") != request.fingerprint:
        raise ValueError("PostgreSQL search dispatch fingerprint does not match bytes")
    if row.get("dispatch_fingerprint") not in (None, request.fingerprint):
        raise ValueError("PostgreSQL search dispatch record fingerprint does not match bytes")
    try:
        candidate_index = int(row["candidate_index"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL search dispatch candidate index is malformed") from error
    return SearchDispatchRecord(row_owner, experiment, candidate_index, request)


def _decode_reservation(row: Mapping[str, Any]) -> WorkerReservation:
    from app.strategy_lab_v2.workers import WorkerKind

    try:
        return WorkerReservation(
            row["reservation_id"],
            row["worker_id"],
            WorkerKind(row["kind"]),
            row["attempt_id"],
            _decode_datetime(row["acquired_at"], "acquired_at"),
            _decode_optional_datetime(row.get("released_at"), "released_at"),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL reservation row is malformed") from error


def _validate_digest(value: str, field_name: str) -> None:
    require_sha256_digest(value, field_name=field_name)


def _principal_id(principal: Any) -> str:
    value = getattr(principal, "id", principal)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("authenticated principal identity is required")
    return value.strip()


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


def _decode_optional_datetime(value: Any, field_name: str) -> datetime | None:
    return None if value is None else _decode_datetime(value, field_name)


def _statement(sql: str) -> Any:
    from sqlalchemy import text

    return text(sql)


__all__ = [
    "PostgresSearchDispatchAdapter",
    "PostgresSearchDispatchSchema",
    "SearchDispatchRecord",
]
