from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import AttemptState, RunAttempt
from app.strategy_lab_v2.lease_observations import (
    LeaseObservation,
    LeaseObservationDecision,
    LeaseObservationKind,
)
from app.strategy_lab_v2.lifecycle import acquire_attempt_lease
from app.strategy_lab_v2.postgres_worker_state import (
    PostgresWorkerStateAdapter,
    PostgresWorkerStateSchema,
    WorkerCapacityDecision,
    WorkerProfileDecision,
)
from app.strategy_lab_v2.workers import WorkerKind, WorkerProfile, WorkerReservationDecision

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
RUNTIME = content_digest({"runtime": "strategy-v2"})


class FakeResult:
    def __init__(self, rows=(), rowcount: int = 0) -> None:
        self._rows = list(rows)
        self.rowcount = rowcount

    def mappings(self):
        return iter(self._rows)


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeSession:
    """Small SQL-shape fake; rows retain the exact adapter parameters."""

    def __init__(self) -> None:
        self.profiles: dict[str, dict[str, Any]] = {}
        self.reservations: dict[str, dict[str, Any]] = {}
        self.leases: dict[str, dict[str, Any]] = {}
        self.observations: dict[str, dict[str, Any]] = {}
        self.calls: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def begin(self):
        return FakeTransaction()

    async def execute(self, statement, params=None):
        sql = str(statement)
        values = dict(params or {})
        normalized = sql.lstrip()
        self.calls.append(sql)
        if normalized.startswith("SELECT worker_id"):
            row = self.profiles.get(values["worker_id"])
            return FakeResult([] if row is None else [row])
        if normalized.startswith("SELECT reservation_id"):
            rows = [
                row
                for row in self.reservations.values()
                if row["worker_id"] == values["worker_id"]
            ]
            return FakeResult(sorted(rows, key=lambda row: row["reservation_id"]))
        if normalized.startswith("SELECT lease_id"):
            row = self.leases.get(values["lease_id"])
            return FakeResult([] if row is None else [row])
        if normalized.startswith("SELECT observation_id"):
            rows = [
                row
                for row in self.observations.values()
                if row["lease_id"] == values["lease_id"]
            ]
            return FakeResult(sorted(rows, key=lambda row: row["sequence"]))
        if normalized.startswith("INSERT INTO") and "profile_fingerprint" in sql:
            key = values["worker_id"]
            if key in self.profiles:
                return FakeResult(rowcount=0)
            self.profiles[key] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("INSERT INTO") and "reservation_fingerprint" in sql:
            key = values["reservation_id"]
            if key in self.reservations:
                return FakeResult(rowcount=0)
            self.reservations[key] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("INSERT INTO") and "lease_fingerprint" in sql:
            key = values["lease_id"]
            if key in self.leases:
                return FakeResult(rowcount=0)
            self.leases[key] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("INSERT INTO") and "observation_fingerprint" in sql:
            key = values["observation_id"]
            if key in self.observations:
                return FakeResult(rowcount=0)
            self.observations[key] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("UPDATE") and "reservation_fingerprint" in sql:
            row = self.reservations.get(values["reservation_id"])
            if row is None or row["reservation_fingerprint"] != values["expected_fingerprint"]:
                return FakeResult(rowcount=0)
            row.update(
                released_at=values["released_at"],
                reservation_fingerprint=values["next_fingerprint"],
            )
            return FakeResult(rowcount=1)
        if normalized.startswith("UPDATE") and "lease_fingerprint" in sql:
            row = self.leases.get(values["lease_id"])
            if row is None or row["lease_fingerprint"] != values["expected_fingerprint"]:
                return FakeResult(rowcount=0)
            row.update(
                heartbeat_at=values["heartbeat_at"],
                expires_at=values["expires_at"],
                released_at=values["released_at"],
                lease_fingerprint=values["next_fingerprint"],
            )
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


def _profile() -> WorkerProfile:
    return WorkerProfile("worker-1", WorkerKind.BACKTEST, RUNTIME)


def _reservation_id(value: str) -> str:
    return content_digest({"reservation": value})


def _observation(
    value: str,
    sequence: int,
    kind: LeaseObservationKind = LeaseObservationKind.HEARTBEAT,
    *,
    observed_at: datetime = NOW + timedelta(minutes=1),
    expires_at: datetime | None = NOW + timedelta(minutes=6),
) -> LeaseObservation:
    return LeaseObservation(
        content_digest({"observation": value}),
        "lease-1",
        "worker-1",
        "attempt-1",
        sequence,
        kind,
        observed_at,
        expires_at,
    )


@pytest.mark.asyncio
async def test_worker_state_adapter_registers_reserves_releases_and_replays() -> None:
    session = FakeSession()
    adapter = PostgresWorkerStateAdapter(lambda: session)
    profile = _profile()

    registered = await adapter.ensure_profile(profile)
    assert registered.decision is WorkerProfileDecision.REGISTERED
    replayed = await adapter.ensure_profile(profile)
    assert replayed.decision is WorkerProfileDecision.REPLAY_EXISTING

    first_id = _reservation_id("one")
    accepted = await adapter.reserve(
        profile=profile,
        attempt_id="attempt-1",
        reservation_id=first_id,
        acquired_at=NOW,
    )
    assert accepted.decision is WorkerReservationDecision.ACCEPT
    assert accepted.reservation is not None
    replay = await adapter.reserve(
        profile=profile,
        attempt_id="attempt-1",
        reservation_id=_reservation_id("retry"),
        acquired_at=NOW + timedelta(seconds=1),
    )
    assert replay.decision is WorkerReservationDecision.REPLAY_EXISTING
    assert replay.reservation == accepted.reservation

    saturated = await adapter.reserve(
        profile=profile,
        attempt_id="attempt-2",
        reservation_id=_reservation_id("two"),
        acquired_at=NOW + timedelta(seconds=2),
    )
    assert saturated.decision is WorkerReservationDecision.SATURATED
    released = await adapter.release(
        profile=profile,
        reservation_id=first_id,
        released_at=NOW + timedelta(seconds=3),
    )
    assert not released.active_reservations
    assert await adapter.release(
        profile=profile,
        reservation_id=first_id,
        released_at=NOW + timedelta(seconds=4),
    ) == released
    reopened = await adapter.reserve(
        profile=profile,
        attempt_id="attempt-2",
        reservation_id=_reservation_id("two"),
        acquired_at=NOW + timedelta(seconds=5),
    )
    assert reopened.decision is WorkerReservationDecision.ACCEPT
    assert len(session.reservations) == 2


@pytest.mark.asyncio
async def test_worker_state_adapter_persists_ordered_lease_observations() -> None:
    session = FakeSession()
    adapter = PostgresWorkerStateAdapter(lambda: session)
    attempt = RunAttempt("attempt-1", "trial-1", 1, AttemptState.RUNNING, NOW)
    lease = acquire_attempt_lease(
        attempt,
        worker_id="worker-1",
        lease_id="lease-1",
        now=NOW,
        lease_duration=timedelta(minutes=5),
    )
    persisted = await adapter.persist_lease(lease)
    assert persisted.lease == lease
    heartbeat = _observation("heartbeat", 1)
    applied = await adapter.observe(lease_id="lease-1", observation=heartbeat)
    assert applied.decision is LeaseObservationDecision.APPLY
    replay = await adapter.observe(lease_id="lease-1", observation=heartbeat)
    assert replay.decision is LeaseObservationDecision.REPLAY_EXISTING
    release = _observation(
        "release",
        2,
        LeaseObservationKind.RELEASE,
        observed_at=NOW + timedelta(minutes=2),
        expires_at=None,
    )
    released = await adapter.observe(lease_id="lease-1", observation=release)
    assert released.decision is LeaseObservationDecision.APPLY
    assert released.state.last_sequence == 2
    assert released.state.lease.released_at == release.observed_at
    assert len(session.observations) == 2


@pytest.mark.asyncio
async def test_worker_state_adapter_releases_lease_and_capacity_atomically() -> None:
    session = FakeSession()
    adapter = PostgresWorkerStateAdapter(lambda: session)
    profile = _profile()
    reservation_id = _reservation_id("one")
    await adapter.ensure_profile(profile)
    await adapter.reserve(
        profile=profile,
        attempt_id="attempt-1",
        reservation_id=reservation_id,
        acquired_at=NOW,
    )
    attempt = RunAttempt("attempt-1", "trial-1", 1, AttemptState.RUNNING, NOW)
    lease = acquire_attempt_lease(
        attempt,
        worker_id="worker-1",
        lease_id="lease-1",
        now=NOW,
        lease_duration=timedelta(minutes=5),
    )
    await adapter.persist_lease(lease)
    release = _observation(
        "release",
        1,
        LeaseObservationKind.RELEASE,
        observed_at=NOW + timedelta(minutes=1),
        expires_at=None,
    )

    resolved = await adapter.release_capacity(
        profile=profile,
        reservation_id=reservation_id,
        lease_id="lease-1",
        observation=release,
    )
    assert resolved.decision is WorkerCapacityDecision.RELEASED
    assert resolved.lease_state is not None
    assert resolved.lease_state.lease.released_at == release.observed_at
    assert not resolved.pool.active_reservations

    replay = await adapter.release_capacity(
        profile=profile,
        reservation_id=reservation_id,
        lease_id="lease-1",
        observation=release,
    )
    assert replay.decision is WorkerCapacityDecision.REPLAY_EXISTING
    assert replay.pool == resolved.pool
    assert replay.lease_state == resolved.lease_state
    assert len(session.observations) == 1


@pytest.mark.asyncio
async def test_worker_state_adapter_rejects_non_release_without_mutation() -> None:
    session = FakeSession()
    adapter = PostgresWorkerStateAdapter(lambda: session)
    profile = _profile()
    reservation_id = _reservation_id("one")
    await adapter.ensure_profile(profile)
    await adapter.reserve(
        profile=profile,
        attempt_id="attempt-1",
        reservation_id=reservation_id,
        acquired_at=NOW,
    )
    attempt = RunAttempt("attempt-1", "trial-1", 1, AttemptState.RUNNING, NOW)
    lease = acquire_attempt_lease(
        attempt,
        worker_id="worker-1",
        lease_id="lease-1",
        now=NOW,
        lease_duration=timedelta(minutes=5),
    )
    await adapter.persist_lease(lease)
    heartbeat = _observation("heartbeat", 1)
    with pytest.raises(ValueError, match="requires a release"):
        await adapter.release_capacity(
            profile=profile,
            reservation_id=reservation_id,
            lease_id="lease-1",
            observation=heartbeat,
        )
    assert not session.observations
    assert session.reservations[reservation_id]["released_at"] is None


@pytest.mark.asyncio
async def test_worker_state_adapter_rejects_tampered_rows_and_foreign_profiles() -> None:
    session = FakeSession()
    adapter = PostgresWorkerStateAdapter(lambda: session)
    profile = _profile()
    await adapter.ensure_profile(profile)
    with pytest.raises(ValueError, match="profile identity"):
        await adapter.ensure_profile(
            WorkerProfile("worker-1", WorkerKind.FORWARD, RUNTIME)
        )
    session.profiles[profile.worker_id]["profile_fingerprint"] = content_digest("tampered")
    with pytest.raises(ValueError, match="profile fingerprint"):
        await adapter.load_pool(profile)


@pytest.mark.asyncio
async def test_worker_state_adapter_rejects_tampered_reservation_and_lease_rows() -> None:
    session = FakeSession()
    adapter = PostgresWorkerStateAdapter(lambda: session)
    profile = _profile()
    reservation_id = _reservation_id("one")
    await adapter.reserve(
        profile=profile,
        attempt_id="attempt-1",
        reservation_id=reservation_id,
        acquired_at=NOW,
    )
    session.reservations[reservation_id]["reservation_fingerprint"] = content_digest("tampered")
    with pytest.raises(ValueError, match="reservation fingerprint"):
        await adapter.load_pool(profile)

    lease_session = FakeSession()
    lease_adapter = PostgresWorkerStateAdapter(lambda: lease_session)
    attempt = RunAttempt("attempt-1", "trial-1", 1, AttemptState.RUNNING, NOW)
    lease = acquire_attempt_lease(
        attempt,
        worker_id="worker-1",
        lease_id="lease-1",
        now=NOW,
        lease_duration=timedelta(minutes=5),
    )
    await lease_adapter.persist_lease(lease)
    lease_session.leases["lease-1"]["lease_fingerprint"] = content_digest("tampered")
    with pytest.raises(ValueError, match="lease fingerprint"):
        await lease_adapter.persist_lease(lease)


def test_worker_state_schema_is_explicit_but_not_applied() -> None:
    schema = PostgresWorkerStateSchema()
    assert len(schema.statements) == 5
    assert all("CREATE TABLE" in statement for statement in schema.statements[:4])
    assert "UNIQUE (lease_id, sequence)" in schema.statements[3]
    assert "WHERE released_at IS NULL" in schema.statements[4]
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresWorkerStateSchema(lease_table="unsafe;drop")
