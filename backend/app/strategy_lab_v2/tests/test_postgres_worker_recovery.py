from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.strategy_lab_v2.contracts import AttemptState
from app.strategy_lab_v2.lifecycle import transition_attempt
from app.strategy_lab_v2.postgres_worker_recovery import (
    PostgresWorkerRecoveryAdapter,
    PostgresWorkerRecoverySchema,
    WorkerRecoveryReceiptDecision,
)
from app.strategy_lab_v2.postgres_worker_state import (
    PostgresWorkerStateAdapter,
    WorkerCapacityDecision,
)
from app.strategy_lab_v2.recovery import RecoveryReason
from app.strategy_lab_v2.tests.test_postgres_worker_state import FakeSession as StateSession
from app.strategy_lab_v2.tests.test_worker_recovery import _admitted
from app.strategy_lab_v2.worker_recovery import WorkerRecoveryDecision

NOW = datetime(2024, 1, 1, tzinfo=UTC)


class RecoverySession(StateSession):
    def __init__(self) -> None:
        super().__init__()
        self.recoveries: dict[tuple[str, str], dict[str, Any]] = {}
        self.race_next_recovery_insert = False

    async def execute(self, statement, params=None):
        sql = str(statement)
        values = dict(params or {})
        normalized = sql.lstrip()
        if "strategy_lab_v2_worker_recoveries" in sql:
            if normalized.startswith("SELECT owner_id"):
                rows = [
                    row
                    for (owner_id, _), row in self.recoveries.items()
                    if owner_id == values["owner_id"]
                    and ("attempt_id" not in values or row["attempt_id"] == values["attempt_id"])
                ]
                return FakeResult(sorted(rows, key=lambda row: row["recovery_fingerprint"]))
            if normalized.startswith("INSERT INTO"):
                key = (values["owner_id"], values["recovery_fingerprint"])
                if self.race_next_recovery_insert:
                    self.race_next_recovery_insert = False
                    self.recoveries[key] = values
                    return FakeResult(rowcount=0)
                if any(
                    owner_id == values["owner_id"] and row["attempt_id"] == values["attempt_id"]
                    for (owner_id, _fingerprint), row in self.recoveries.items()
                ):
                    return FakeResult(rowcount=0)
                self.recoveries[key] = values
                return FakeResult(rowcount=1)
            raise AssertionError(f"unexpected recovery SQL: {sql}")
        return await super().execute(statement, params)


class FakeResult:
    def __init__(self, rows=(), rowcount: int = 0) -> None:
        self._rows = list(rows)
        self.rowcount = rowcount

    def mappings(self):
        return iter(self._rows)


class FailOnceBeforeCapacityRelease(PostgresWorkerStateAdapter):
    def __init__(self, session: RecoverySession) -> None:
        super().__init__(lambda: session)
        self.fail_once = True

    async def release_capacity(self, **kwargs):
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("simulated worker process interruption")
        return await super().release_capacity(**kwargs)


async def _persist_admission_state(session: RecoverySession):
    running, lease, admissions, pool = _admitted()
    worker_state = PostgresWorkerStateAdapter(lambda: session)
    await worker_state.ensure_profile(pool.profile)
    reservation = pool.active_reservations[0]
    reserved = await worker_state.reserve(
        profile=pool.profile,
        attempt_id=reservation.attempt_id,
        reservation_id=reservation.reservation_id,
        acquired_at=reservation.acquired_at,
    )
    assert reserved.reservation == reservation
    await worker_state.persist_lease(lease)
    return running, lease, admissions, pool.profile, worker_state


@pytest.mark.asyncio
async def test_expired_lease_recovery_resumes_after_receipt_before_capacity_release() -> None:
    session = RecoverySession()
    running, lease, admissions, profile, _ = await _persist_admission_state(session)
    failed = transition_attempt(running, AttemptState.FAILED, now=NOW + timedelta(seconds=5))
    reservation_id = admissions.admissions[0].reservation_id
    interrupted_state = FailOnceBeforeCapacityRelease(session)
    adapter = PostgresWorkerRecoveryAdapter(
        lambda: session,
        worker_state=interrupted_state,
    )

    with pytest.raises(RuntimeError, match="interruption"):
        await adapter.recover(
            principal="owner-a",
            prior_attempts=(failed,),
            admission_ledger=admissions,
            profile=profile,
            lease_id=lease.lease_id,
            reason=RecoveryReason.LEASE_EXPIRED,
            observed_at=NOW + timedelta(seconds=40),
            next_attempt_id="attempt-2",
        )

    assert len(session.recoveries) == 1
    assert session.reservations[reservation_id]["released_at"] is None
    interrupted_lease = await interrupted_state.load_lease(lease.lease_id)
    assert interrupted_lease is not None
    assert interrupted_lease.lease.released_at is None

    restarted_state = PostgresWorkerStateAdapter(lambda: session)
    restarted_adapter = PostgresWorkerRecoveryAdapter(
        lambda: session,
        worker_state=restarted_state,
    )
    recovered = await restarted_adapter.recover(
        principal="owner-a",
        prior_attempts=(failed,),
        admission_ledger=admissions,
        profile=profile,
        lease_id=lease.lease_id,
        reason=RecoveryReason.LEASE_EXPIRED,
        observed_at=NOW + timedelta(seconds=41),
    )

    assert recovered.decision is WorkerRecoveryDecision.REPLAY_EXISTING
    assert recovered.next_attempt is not None
    assert recovered.next_attempt.attempt_id == "attempt-2"
    assert recovered.next_attempt.trial_id == failed.trial_id
    assert recovered.release_observation is not None
    assert not recovered.pool.active_reservations
    assert recovered.lease_state.lease.released_at == NOW + timedelta(seconds=40)
    assert len(session.observations) == 1

    duplicate = await restarted_adapter.recover(
        principal="owner-a",
        prior_attempts=(failed,),
        admission_ledger=admissions,
        profile=profile,
        lease_id=lease.lease_id,
        reason=RecoveryReason.LEASE_EXPIRED,
        observed_at=NOW + timedelta(seconds=42),
    )
    assert duplicate.decision is WorkerRecoveryDecision.REPLAY_EXISTING
    assert duplicate.next_attempt == recovered.next_attempt
    assert duplicate.pool == recovered.pool
    assert duplicate.lease_state == recovered.lease_state
    assert len(session.recoveries) == 1
    assert len(session.observations) == 1
    assert (await restarted_adapter.load_ledger(principal="owner-a")).records == (
        recovered.ledger.records[0],
    )
    assert await restarted_adapter.load_ledger(principal="owner-b") == type(recovered.ledger)()


@pytest.mark.asyncio
async def test_cancelled_attempt_persists_terminal_recovery_and_replays() -> None:
    session = RecoverySession()
    running, lease, admissions, profile, worker_state = await _persist_admission_state(session)
    cancelled = transition_attempt(running, AttemptState.CANCELLED, now=NOW + timedelta(seconds=5))
    adapter = PostgresWorkerRecoveryAdapter(
        lambda: session,
        worker_state=worker_state,
    )
    first = await adapter.recover(
        principal="owner-a",
        prior_attempts=(cancelled,),
        admission_ledger=admissions,
        profile=profile,
        lease_id=lease.lease_id,
        reason=RecoveryReason.CANCELLED,
        observed_at=NOW + timedelta(seconds=7),
    )
    replay = await adapter.recover(
        principal="owner-a",
        prior_attempts=(cancelled,),
        admission_ledger=admissions,
        profile=profile,
        lease_id=lease.lease_id,
        reason=RecoveryReason.CANCELLED,
        observed_at=NOW + timedelta(seconds=8),
    )

    assert first.decision is WorkerRecoveryDecision.TERMINAL
    assert replay.decision is WorkerRecoveryDecision.REPLAY_EXISTING
    assert replay.plan == first.plan
    assert replay.next_attempt is None
    assert replay.pool == first.pool
    assert replay.lease_state == first.lease_state
    assert len(session.recoveries) == 1
    assert len(session.observations) == 1
    assert not replay.pool.active_reservations


@pytest.mark.asyncio
async def test_recovery_adapter_authenticates_receipts_and_scopes_owners() -> None:
    session = RecoverySession()
    running, lease, admissions, profile, worker_state = await _persist_admission_state(session)
    failed = transition_attempt(running, AttemptState.FAILED, now=NOW + timedelta(seconds=5))
    adapter = PostgresWorkerRecoveryAdapter(lambda: session, worker_state=worker_state)
    recovered = await adapter.recover(
        principal="owner-a",
        prior_attempts=(failed,),
        admission_ledger=admissions,
        profile=profile,
        lease_id=lease.lease_id,
        reason=RecoveryReason.WORKER_CRASH,
        observed_at=NOW + timedelta(seconds=6),
        next_attempt_id="attempt-2",
    )
    assert recovered.decision is WorkerRecoveryDecision.RETRY_SCHEDULED
    assert len((await adapter.load_ledger(principal="owner-a")).records) == 1
    assert not (await adapter.load_ledger(principal="owner-b")).records
    session.race_next_recovery_insert = True
    concurrent_replay = await adapter.ensure(
        principal="owner-b", record=recovered.ledger.records[0]
    )
    assert concurrent_replay.decision is WorkerRecoveryReceiptDecision.REPLAY_EXISTING
    assert len(session.recoveries) == 2
    row = next(iter(session.recoveries.values()))
    row["record_fingerprint"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="fingerprint"):
        await adapter.load_ledger(principal="owner-a")


def test_recovery_schema_is_explicit_and_rejects_unsafe_table_names() -> None:
    schema = PostgresWorkerRecoverySchema()
    assert "UNIQUE (owner_id, attempt_id)" in schema.statements[0]
    assert "reason TEXT NOT NULL" in schema.statements[0]
    assert "lease_observation_sequence BIGINT NOT NULL" in schema.statements[0]
    assert WorkerRecoveryReceiptDecision.REGISTERED.value == "registered"
    assert WorkerCapacityDecision.RELEASED.value == "released"
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresWorkerRecoverySchema(recovery_table="unsafe;drop")
