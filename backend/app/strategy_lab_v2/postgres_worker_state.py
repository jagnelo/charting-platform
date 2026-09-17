"""PostgreSQL persistence for serial worker reservations and lease evidence.

Worker capacity and lease observations are resolved by the pure
:mod:`workers` and :mod:`lease_observations` contracts.  This adapter locks the
profile/lease rows, re-authenticates every stored content identity, and makes
reservation or heartbeat/release changes durable in one async transaction. It
does not start processes, enqueue jobs, or publish Redis messages.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.lease_observations import (
    LeaseObservation,
    LeaseObservationDecision,
    LeaseObservationKind,
    LeaseObservationResolution,
    LeaseObservationState,
    apply_lease_observation,
)
from app.strategy_lab_v2.lifecycle import ExecutionAttemptLease
from app.strategy_lab_v2.workers import (
    WorkerKind,
    WorkerPoolState,
    WorkerProfile,
    WorkerReservation,
    WorkerReservationDecision,
    WorkerReservationResolution,
    release_worker_slot,
    reserve_worker_slot,
)


class AsyncSessionFactory(Protocol):
    def __call__(self) -> Any: ...


class AsyncSessionLike(Protocol):
    async def __aenter__(self) -> Any: ...

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> Any: ...

    def begin(self) -> Any: ...

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any: ...


class WorkerProfileDecision(StrEnum):
    REGISTERED = "registered"
    REPLAY_EXISTING = "replay_existing"


@dataclass(frozen=True, slots=True)
class WorkerProfileResolution:
    """Profile registration result and the currently persisted pool."""

    decision: WorkerProfileDecision
    pool: WorkerPoolState

    def __post_init__(self) -> None:
        if not isinstance(self.decision, str):
            raise TypeError("decision must be a string")
        if not isinstance(self.pool, WorkerPoolState):
            raise TypeError("pool must be a WorkerPoolState")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class WorkerCapacityDecision(StrEnum):
    RELEASED = "released"
    REPLAY_EXISTING = "replay_existing"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class WorkerCapacityResolution:
    """Atomic release of one lease observation and its worker reservation."""

    decision: WorkerCapacityDecision
    pool: WorkerPoolState
    lease_state: LeaseObservationState | None
    observation: LeaseObservation
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, WorkerCapacityDecision):
            raise TypeError("decision must be a WorkerCapacityDecision")
        if not isinstance(self.pool, WorkerPoolState):
            raise TypeError("pool must be a WorkerPoolState")
        if self.lease_state is not None and not isinstance(
            self.lease_state, LeaseObservationState
        ):
            raise TypeError("lease_state must be a LeaseObservationState or None")
        if not isinstance(self.observation, LeaseObservation):
            raise TypeError("observation must be a LeaseObservation")
        if self.decision is WorkerCapacityDecision.REJECT and not self.rejection_reason:
            raise ValueError("rejected capacity resolutions require a reason")
        if self.decision is not WorkerCapacityDecision.REJECT and self.rejection_reason:
            raise ValueError("successful capacity resolutions cannot contain a reason")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class PostgresWorkerStateSchema:
    """Explicit additive DDL for worker profiles, reservations, and leases."""

    profile_table: str = "strategy_lab_v2_worker_profiles"
    reservation_table: str = "strategy_lab_v2_worker_reservations"
    lease_table: str = "strategy_lab_v2_execution_leases"
    observation_table: str = "strategy_lab_v2_lease_observations"

    def __post_init__(self) -> None:
        for name, value in (
            ("profile_table", self.profile_table),
            ("reservation_table", self.reservation_table),
            ("lease_table", self.lease_table),
            ("observation_table", self.observation_table),
        ):
            if not isinstance(value, str) or not re.fullmatch(r"[a-z_][a-z0-9_]*", value):
                raise ValueError(f"{name} must be a safe SQL identifier")

    @property
    def statements(self) -> tuple[str, ...]:
        return (
            f"""
            CREATE TABLE {self.profile_table} (
                worker_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                runtime_profile_fingerprint TEXT NOT NULL,
                isolation_required BOOLEAN NOT NULL,
                engine_disposal_required BOOLEAN NOT NULL,
                max_concurrent_nodes BIGINT NOT NULL,
                profile_fingerprint TEXT NOT NULL
            )
            """,
            f"""
            CREATE TABLE {self.reservation_table} (
                reservation_id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                acquired_at TEXT NOT NULL,
                released_at TEXT NULL,
                reservation_fingerprint TEXT NOT NULL,
                UNIQUE (worker_id, attempt_id, released_at)
            )
            """,
            f"""
            CREATE TABLE {self.lease_table} (
                lease_id TEXT PRIMARY KEY,
                attempt_id TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                leased_at TEXT NOT NULL,
                heartbeat_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                released_at TEXT NULL,
                lease_fingerprint TEXT NOT NULL
            )
            """,
            f"""
            CREATE TABLE {self.observation_table} (
                observation_id TEXT PRIMARY KEY,
                lease_id TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                sequence BIGINT NOT NULL,
                kind TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                expires_at TEXT NULL,
                observation_fingerprint TEXT NOT NULL,
                UNIQUE (lease_id, sequence)
            )
            """,
            f"""
            CREATE UNIQUE INDEX {self.reservation_table}_active_attempt_key
            ON {self.reservation_table} (worker_id, attempt_id)
            WHERE released_at IS NULL
            """,
        )


class PostgresWorkerStateAdapter:
    """Persist worker reservations and ordered lease observations."""

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        schema: PostgresWorkerStateSchema | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory
        self._schema = schema or PostgresWorkerStateSchema()

    @property
    def schema(self) -> PostgresWorkerStateSchema:
        return self._schema

    async def ensure_profile(self, profile: WorkerProfile) -> WorkerProfileResolution:
        """Register one immutable worker profile or replay the exact profile."""

        _validate_profile(profile)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                persisted = await self._load_profile(session, profile.worker_id)
                if persisted is None:
                    await self._insert_profile(session, profile)
                    return WorkerProfileResolution(
                        WorkerProfileDecision.REGISTERED,
                        WorkerPoolState(profile),
                    )
                if persisted != profile:
                    raise ValueError("PostgreSQL worker profile identity is already bound")
                pool = await self._load_pool(session, persisted)
                return WorkerProfileResolution(WorkerProfileDecision.REPLAY_EXISTING, pool)

    async def reserve(
        self,
        *,
        profile: WorkerProfile,
        attempt_id: str,
        reservation_id: str,
        acquired_at: datetime,
    ) -> WorkerReservationResolution:
        """Atomically claim one serial slot for an attempt."""

        _validate_profile(profile)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                persisted = await self._load_profile(session, profile.worker_id)
                if persisted is None:
                    await self._insert_profile(session, profile)
                    persisted = profile
                elif persisted != profile:
                    return WorkerReservationResolution(
                        WorkerReservationDecision.REJECT,
                        WorkerPoolState(persisted),
                        rejection_reason="worker profile identity is already bound",
                    )
                pool = await self._load_pool(session, persisted)
                resolution = reserve_worker_slot(
                    pool,
                    attempt_id=attempt_id,
                    reservation_id=reservation_id,
                    acquired_at=acquired_at,
                )
                if resolution.decision is WorkerReservationDecision.ACCEPT:
                    if resolution.reservation is None:  # pragma: no cover - pure guard
                        raise ValueError("worker reservation resolution omitted its reservation")
                    await self._insert_reservation(session, resolution.reservation)
                return resolution

    async def release(
        self,
        *,
        profile: WorkerProfile,
        reservation_id: str,
        released_at: datetime,
    ) -> WorkerPoolState:
        """Release one slot with a fingerprint-guarded update."""

        _validate_profile(profile)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                persisted = await self._load_profile(session, profile.worker_id)
                if persisted is None:
                    raise ValueError("worker profile is not registered")
                if persisted != profile:
                    raise ValueError("PostgreSQL worker profile identity is already bound")
                pool = await self._load_pool(session, persisted)
                next_pool = release_worker_slot(
                    pool,
                    reservation_id=reservation_id,
                    released_at=released_at,
                )
                if next_pool == pool:
                    return pool
                current = next(
                    item for item in pool.reservations if item.reservation_id == reservation_id
                )
                updated = next(
                    item for item in next_pool.reservations if item.reservation_id == reservation_id
                )
                result = await session.execute(
                    _statement(
                        f"""
                        UPDATE {self._schema.reservation_table}
                        SET released_at = :released_at, reservation_fingerprint = :next_fingerprint
                        WHERE reservation_id = :reservation_id
                          AND reservation_fingerprint = :expected_fingerprint
                        """
                    ),
                    {
                        "released_at": _encode_datetime(updated.released_at),
                        "next_fingerprint": updated.fingerprint,
                        "reservation_id": reservation_id,
                        "expected_fingerprint": current.fingerprint,
                    },
                )
                if getattr(result, "rowcount", 0) != 1:
                    raise ValueError("PostgreSQL worker reservation compare-and-set lost a race")
                return next_pool

    async def load_pool(self, profile: WorkerProfile) -> WorkerPoolState:
        """Read and authenticate one complete worker pool snapshot."""

        _validate_profile(profile)
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                persisted = await self._load_profile(session, profile.worker_id)
                if persisted is None:
                    return WorkerPoolState(profile)
                if persisted != profile:
                    raise ValueError("PostgreSQL worker profile identity is already bound")
                return await self._load_pool(session, persisted)

    async def persist_lease(self, lease: ExecutionAttemptLease) -> LeaseObservationState:
        """Persist one newly acquired lease or replay the exact lease."""

        if not isinstance(lease, ExecutionAttemptLease):
            raise TypeError("lease must be an ExecutionAttemptLease")
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_lease(session, lease.lease_id)
                if current is not None:
                    if current.lease != lease:
                        raise ValueError("PostgreSQL lease identity is already bound")
                    return current
                await self._insert_lease(session, lease)
                return LeaseObservationState(lease)

    async def observe(
        self, *, lease_id: str, observation: LeaseObservation
    ) -> LeaseObservationResolution:
        """Apply one heartbeat/release and persist its evidence atomically."""

        if not isinstance(lease_id, str) or not lease_id.strip():
            raise ValueError("lease_id must not be empty")
        if not isinstance(observation, LeaseObservation):
            raise TypeError("observation must be a LeaseObservation")
        if observation.lease_id != lease_id:
            raise ValueError("observation must reference lease_id")
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                current = await self._load_lease(session, lease_id)
                if current is None:
                    raise ValueError("lease is not persisted")
                resolution = apply_lease_observation(current, observation)
                if resolution.decision is LeaseObservationDecision.APPLY:
                    await self._insert_observation(session, observation)
                    next_lease = resolution.state.lease
                    result = await session.execute(
                        _statement(
                            f"""
                            UPDATE {self._schema.lease_table}
                            SET heartbeat_at = :heartbeat_at, expires_at = :expires_at,
                                released_at = :released_at, lease_fingerprint = :next_fingerprint
                            WHERE lease_id = :lease_id AND lease_fingerprint = :expected_fingerprint
                            """
                        ),
                        {
                            "heartbeat_at": _encode_datetime(next_lease.heartbeat_at),
                            "expires_at": _encode_datetime(next_lease.expires_at),
                            "released_at": _encode_datetime(next_lease.released_at),
                            "next_fingerprint": _lease_fingerprint(next_lease),
                            "lease_id": lease_id,
                            "expected_fingerprint": _lease_fingerprint(current.lease),
                        },
                    )
                    if getattr(result, "rowcount", 0) != 1:
                        raise ValueError("PostgreSQL lease compare-and-set lost a race")
                return resolution

    async def release_capacity(
        self,
        *,
        profile: WorkerProfile,
        reservation_id: str,
        lease_id: str,
        observation: LeaseObservation,
    ) -> WorkerCapacityResolution:
        """Atomically apply a release observation and free its serial slot.

        This is the durable boundary used by a completion/recovery adapter.
        The release observation and reservation update share one transaction;
        exact retries replay both states and no partial lease/capacity release
        can become visible.  Heartbeats remain available through :meth:`observe`.
        """

        _validate_profile(profile)
        if not isinstance(reservation_id, str) or not reservation_id.strip():
            raise ValueError("reservation_id must not be empty")
        require_sha256_digest(reservation_id, field_name="reservation_id")
        if not isinstance(lease_id, str) or not lease_id.strip():
            raise ValueError("lease_id must not be empty")
        if not isinstance(observation, LeaseObservation):
            raise TypeError("observation must be a LeaseObservation")
        if observation.kind is not LeaseObservationKind.RELEASE:
            raise ValueError("capacity release requires a release observation")
        if observation.lease_id != lease_id:
            raise ValueError("release observation must reference lease_id")
        if observation.worker_id != profile.worker_id:
            raise ValueError("release observation must reference the worker profile")
        session: AsyncSessionLike = self._session_factory()
        async with session:
            async with session.begin():
                persisted = await self._load_profile(session, profile.worker_id)
                if persisted is None:
                    return _capacity_reject(
                        profile,
                        observation,
                        "worker profile is not registered",
                    )
                if persisted != profile:
                    return _capacity_reject(
                        persisted,
                        observation,
                        "PostgreSQL worker profile identity is already bound",
                    )
                pool = await self._load_pool(session, persisted)
                reservation = next(
                    (item for item in pool.reservations if item.reservation_id == reservation_id),
                    None,
                )
                if reservation is None:
                    return WorkerCapacityResolution(
                        WorkerCapacityDecision.REJECT,
                        pool,
                        None,
                        observation,
                        "worker reservation is not persisted",
                    )
                if reservation.attempt_id != observation.attempt_id:
                    return WorkerCapacityResolution(
                        WorkerCapacityDecision.REJECT,
                        pool,
                        None,
                        observation,
                        "release observation and reservation reference different attempts",
                    )
                current = await self._load_lease(session, lease_id)
                if current is None:
                    return WorkerCapacityResolution(
                        WorkerCapacityDecision.REJECT,
                        pool,
                        None,
                        observation,
                        "lease is not persisted",
                    )
                if current.lease.worker_id != profile.worker_id or current.lease.attempt_id != reservation.attempt_id:
                    return WorkerCapacityResolution(
                        WorkerCapacityDecision.REJECT,
                        pool,
                        current,
                        observation,
                        "lease and reservation identities do not match",
                    )
                if reservation.active is False:
                    existing = next(
                        (
                            item
                            for item in current.applied_observations
                            if item.observation_id == observation.observation_id
                        ),
                        None,
                    )
                    if existing is not None and existing == observation:
                        return WorkerCapacityResolution(
                            WorkerCapacityDecision.REPLAY_EXISTING,
                            pool,
                            current,
                            observation,
                        )
                    return WorkerCapacityResolution(
                        WorkerCapacityDecision.REJECT,
                        pool,
                        current,
                        observation,
                        "worker reservation is already released",
                    )
                lease_resolution = apply_lease_observation(current, observation)
                if lease_resolution.decision not in {
                    LeaseObservationDecision.APPLY,
                    LeaseObservationDecision.REPLAY_EXISTING,
                }:
                    return WorkerCapacityResolution(
                        WorkerCapacityDecision.REJECT,
                        pool,
                        current,
                        observation,
                        lease_resolution.rejection_reason
                        or f"lease release {lease_resolution.decision.value}",
                    )
                next_lease_state = lease_resolution.state
                if lease_resolution.decision is LeaseObservationDecision.APPLY:
                    await self._insert_observation(session, observation)
                    next_lease = next_lease_state.lease
                    result = await session.execute(
                        _statement(
                            f"""
                            UPDATE {self._schema.lease_table}
                            SET heartbeat_at = :heartbeat_at, expires_at = :expires_at,
                                released_at = :released_at, lease_fingerprint = :next_fingerprint
                            WHERE lease_id = :lease_id AND lease_fingerprint = :expected_fingerprint
                            """
                        ),
                        {
                            "heartbeat_at": _encode_datetime(next_lease.heartbeat_at),
                            "expires_at": _encode_datetime(next_lease.expires_at),
                            "released_at": _encode_datetime(next_lease.released_at),
                            "next_fingerprint": _lease_fingerprint(next_lease),
                            "lease_id": lease_id,
                            "expected_fingerprint": _lease_fingerprint(current.lease),
                        },
                    )
                    if getattr(result, "rowcount", 0) != 1:
                        raise ValueError("PostgreSQL lease compare-and-set lost a race")
                next_pool = release_worker_slot(
                    pool,
                    reservation_id=reservation_id,
                    released_at=observation.observed_at,
                )
                if next_pool != pool:
                    current_reservation = reservation
                    updated_reservation = next(
                        item
                        for item in next_pool.reservations
                        if item.reservation_id == reservation_id
                    )
                    result = await session.execute(
                        _statement(
                            f"""
                            UPDATE {self._schema.reservation_table}
                            SET released_at = :released_at, reservation_fingerprint = :next_fingerprint
                            WHERE reservation_id = :reservation_id
                              AND reservation_fingerprint = :expected_fingerprint
                            """
                        ),
                        {
                            "released_at": _encode_datetime(updated_reservation.released_at),
                            "next_fingerprint": updated_reservation.fingerprint,
                            "reservation_id": reservation_id,
                            "expected_fingerprint": current_reservation.fingerprint,
                        },
                    )
                    if getattr(result, "rowcount", 0) != 1:
                        raise ValueError("PostgreSQL worker reservation compare-and-set lost a race")
                return WorkerCapacityResolution(
                    WorkerCapacityDecision.RELEASED,
                    next_pool,
                    next_lease_state,
                    observation,
                )

    async def _load_profile(
        self, session: AsyncSessionLike, worker_id: str
    ) -> WorkerProfile | None:
        result = await session.execute(
            _statement(
                f"""
                SELECT worker_id, kind, runtime_profile_fingerprint,
                       isolation_required, engine_disposal_required,
                       max_concurrent_nodes, profile_fingerprint
                FROM {self._schema.profile_table}
                WHERE worker_id = :worker_id
                FOR UPDATE
                """
            ),
            {"worker_id": worker_id},
        )
        rows = list(result.mappings())
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("PostgreSQL worker profile query returned duplicate keys")
        row = rows[0]
        try:
            profile = WorkerProfile(
                row["worker_id"],
                WorkerKind(row["kind"]),
                row["runtime_profile_fingerprint"],
                row["isolation_required"],
                row["engine_disposal_required"],
                int(row["max_concurrent_nodes"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("PostgreSQL worker profile row is malformed") from error
        if row.get("worker_id") != worker_id:
            raise ValueError("PostgreSQL worker profile identity drifted")
        if row.get("profile_fingerprint") != profile.fingerprint:
            raise ValueError("PostgreSQL worker profile fingerprint does not match bytes")
        return profile

    async def _load_pool(
        self, session: AsyncSessionLike, profile: WorkerProfile
    ) -> WorkerPoolState:
        result = await session.execute(
            _statement(
                f"""
                SELECT reservation_id, worker_id, kind, attempt_id, acquired_at,
                       released_at, reservation_fingerprint
                FROM {self._schema.reservation_table}
                WHERE worker_id = :worker_id
                ORDER BY reservation_id ASC
                FOR UPDATE
                """
            ),
            {"worker_id": profile.worker_id},
        )
        reservations: list[WorkerReservation] = []
        for row in result.mappings():
            reservation = _decode_reservation(row)
            if row.get("reservation_fingerprint") != reservation.fingerprint:
                raise ValueError("PostgreSQL worker reservation fingerprint does not match bytes")
            reservations.append(reservation)
        ordered = tuple(sorted(reservations, key=lambda item: item.reservation_id))
        if tuple(reservations) != ordered:
            raise ValueError("PostgreSQL worker reservations are not deterministically ordered")
        return WorkerPoolState(profile, ordered)

    async def _load_lease(
        self, session: AsyncSessionLike, lease_id: str
    ) -> LeaseObservationState | None:
        lease_result = await session.execute(
            _statement(
                f"""
                SELECT lease_id, attempt_id, worker_id, leased_at, heartbeat_at,
                       expires_at, released_at, lease_fingerprint
                FROM {self._schema.lease_table}
                WHERE lease_id = :lease_id
                FOR UPDATE
                """
            ),
            {"lease_id": lease_id},
        )
        lease_rows = list(lease_result.mappings())
        if not lease_rows:
            return None
        if len(lease_rows) != 1:
            raise ValueError("PostgreSQL lease query returned duplicate keys")
        row = lease_rows[0]
        lease = _decode_lease(row)
        if row.get("lease_id") != lease_id:
            raise ValueError("PostgreSQL lease identity drifted")
        if row.get("lease_fingerprint") != _lease_fingerprint(lease):
            raise ValueError("PostgreSQL lease fingerprint does not match bytes")
        observation_result = await session.execute(
            _statement(
                f"""
                SELECT observation_id, lease_id, worker_id, attempt_id, sequence,
                       kind, observed_at, expires_at, observation_fingerprint
                FROM {self._schema.observation_table}
                WHERE lease_id = :lease_id
                ORDER BY sequence ASC
                FOR UPDATE
                """
            ),
            {"lease_id": lease_id},
        )
        observations: list[LeaseObservation] = []
        for observation_row in observation_result.mappings():
            observation = _decode_observation(observation_row)
            if observation_row.get("observation_fingerprint") != observation.fingerprint:
                raise ValueError("PostgreSQL lease observation fingerprint does not match bytes")
            observations.append(observation)
        ordered = tuple(sorted(observations, key=lambda item: item.sequence))
        if tuple(observations) != ordered:
            raise ValueError("PostgreSQL lease observations are not deterministically ordered")
        return LeaseObservationState(lease, ordered)

    async def _insert_profile(self, session: AsyncSessionLike, profile: WorkerProfile) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.profile_table}
                    (worker_id, kind, runtime_profile_fingerprint, isolation_required,
                     engine_disposal_required, max_concurrent_nodes, profile_fingerprint)
                VALUES (:worker_id, :kind, :runtime_profile_fingerprint, :isolation_required,
                        :engine_disposal_required, :max_concurrent_nodes, :profile_fingerprint)
                ON CONFLICT (worker_id) DO NOTHING
                """
            ),
            {
                "worker_id": profile.worker_id,
                "kind": profile.kind.value,
                "runtime_profile_fingerprint": profile.runtime_profile_fingerprint,
                "isolation_required": profile.isolation_required,
                "engine_disposal_required": profile.engine_disposal_required,
                "max_concurrent_nodes": profile.max_concurrent_nodes,
                "profile_fingerprint": profile.fingerprint,
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL worker profile insert lost a uniqueness race")

    async def _insert_reservation(
        self, session: AsyncSessionLike, reservation: WorkerReservation
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.reservation_table}
                    (reservation_id, worker_id, kind, attempt_id, acquired_at,
                     released_at, reservation_fingerprint)
                VALUES (:reservation_id, :worker_id, :kind, :attempt_id, :acquired_at,
                        :released_at, :reservation_fingerprint)
                ON CONFLICT (reservation_id) DO NOTHING
                """
            ),
            {
                "reservation_id": reservation.reservation_id,
                "worker_id": reservation.worker_id,
                "kind": reservation.kind.value,
                "attempt_id": reservation.attempt_id,
                "acquired_at": _encode_datetime(reservation.acquired_at),
                "released_at": _encode_datetime(reservation.released_at),
                "reservation_fingerprint": reservation.fingerprint,
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL worker reservation insert lost a uniqueness race")

    async def _insert_lease(
        self, session: AsyncSessionLike, lease: ExecutionAttemptLease
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.lease_table}
                    (lease_id, attempt_id, worker_id, leased_at, heartbeat_at,
                     expires_at, released_at, lease_fingerprint)
                VALUES (:lease_id, :attempt_id, :worker_id, :leased_at, :heartbeat_at,
                        :expires_at, :released_at, :lease_fingerprint)
                ON CONFLICT (lease_id) DO NOTHING
                """
            ),
            {
                "lease_id": lease.lease_id,
                "attempt_id": lease.attempt_id,
                "worker_id": lease.worker_id,
                "leased_at": _encode_datetime(lease.leased_at),
                "heartbeat_at": _encode_datetime(lease.heartbeat_at),
                "expires_at": _encode_datetime(lease.expires_at),
                "released_at": _encode_datetime(lease.released_at),
                "lease_fingerprint": _lease_fingerprint(lease),
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL lease insert lost a uniqueness race")

    async def _insert_observation(
        self, session: AsyncSessionLike, observation: LeaseObservation
    ) -> None:
        result = await session.execute(
            _statement(
                f"""
                INSERT INTO {self._schema.observation_table}
                    (observation_id, lease_id, worker_id, attempt_id, sequence,
                     kind, observed_at, expires_at, observation_fingerprint)
                VALUES (:observation_id, :lease_id, :worker_id, :attempt_id, :sequence,
                        :kind, :observed_at, :expires_at, :observation_fingerprint)
                ON CONFLICT (observation_id) DO NOTHING
                """
            ),
            {
                "observation_id": observation.observation_id,
                "lease_id": observation.lease_id,
                "worker_id": observation.worker_id,
                "attempt_id": observation.attempt_id,
                "sequence": observation.sequence,
                "kind": observation.kind.value,
                "observed_at": _encode_datetime(observation.observed_at),
                "expires_at": _encode_datetime(observation.expires_at),
                "observation_fingerprint": observation.fingerprint,
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ValueError("PostgreSQL lease observation insert lost a uniqueness race")


def _validate_profile(profile: WorkerProfile) -> None:
    if not isinstance(profile, WorkerProfile):
        raise TypeError("profile must be a WorkerProfile")


def _capacity_reject(
    profile: WorkerProfile,
    observation: LeaseObservation,
    reason: str,
) -> WorkerCapacityResolution:
    return WorkerCapacityResolution(
        WorkerCapacityDecision.REJECT,
        WorkerPoolState(profile),
        None,
        observation,
        reason,
    )


def _lease_fingerprint(lease: ExecutionAttemptLease) -> str:
    """Return the canonical identity for a lease value (leases lack a property)."""

    return content_digest(lease)


def _decode_reservation(row: Mapping[str, Any]) -> WorkerReservation:
    try:
        return WorkerReservation(
            row["reservation_id"],
            row["worker_id"],
            WorkerKind(row["kind"]),
            row["attempt_id"],
            _decode_datetime(row["acquired_at"], "acquired_at"),
            _decode_datetime(row["released_at"], "released_at")
            if row.get("released_at") is not None
            else None,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL worker reservation row is malformed") from error


def _decode_lease(row: Mapping[str, Any]) -> ExecutionAttemptLease:
    try:
        return ExecutionAttemptLease(
            row["attempt_id"],
            row["worker_id"],
            row["lease_id"],
            _decode_datetime(row["leased_at"], "leased_at"),
            _decode_datetime(row["heartbeat_at"], "heartbeat_at"),
            _decode_datetime(row["expires_at"], "expires_at"),
            _decode_datetime(row["released_at"], "released_at")
            if row.get("released_at") is not None
            else None,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL lease row is malformed") from error


def _decode_observation(row: Mapping[str, Any]) -> LeaseObservation:
    try:
        return LeaseObservation(
            row["observation_id"],
            row["lease_id"],
            row["worker_id"],
            row["attempt_id"],
            int(row["sequence"]),
            LeaseObservationKind(row["kind"]),
            _decode_datetime(row["observed_at"], "observed_at"),
            _decode_datetime(row["expires_at"], "expires_at")
            if row.get("expires_at") is not None
            else None,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PostgreSQL lease observation row is malformed") from error


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
    "PostgresWorkerStateAdapter",
    "PostgresWorkerStateSchema",
    "WorkerProfileDecision",
    "WorkerProfileResolution",
    "WorkerCapacityDecision",
    "WorkerCapacityResolution",
]
