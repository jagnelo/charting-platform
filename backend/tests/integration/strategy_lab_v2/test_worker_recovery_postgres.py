from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.strategy_lab_v2.contracts import AttemptState
from app.strategy_lab_v2.lease_observations import LeaseObservation
from app.strategy_lab_v2.lifecycle import transition_attempt
from app.strategy_lab_v2.postgres_worker_recovery import (
    PostgresWorkerRecoveryAdapter,
    PostgresWorkerRecoverySchema,
)
from app.strategy_lab_v2.postgres_worker_state import (
    PostgresWorkerStateAdapter,
    PostgresWorkerStateSchema,
    WorkerCapacityResolution,
)
from app.strategy_lab_v2.recovery import RecoveryReason
from app.strategy_lab_v2.tests.test_worker_recovery import _admitted
from app.strategy_lab_v2.worker_recovery import WorkerRecoveryDecision
from app.strategy_lab_v2.workers import WorkerProfile

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _async_postgres_url(raw_url: str) -> str:
    if raw_url.startswith("postgresql+asyncpg://"):
        return raw_url
    if raw_url.startswith("postgresql+psycopg2://"):
        return raw_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    raise ValueError("integration database URL must use PostgreSQL")


class FailOnceBeforeCapacityRelease(PostgresWorkerStateAdapter):
    def __init__(self, session_factory, *, schema: PostgresWorkerStateSchema) -> None:
        super().__init__(session_factory, schema=schema)
        self.fail_once = True

    async def release_capacity(
        self,
        *,
        profile: WorkerProfile,
        reservation_id: str,
        lease_id: str,
        observation: LeaseObservation,
    ) -> WorkerCapacityResolution:
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("simulated recovery process interruption")
        return await super().release_capacity(
            profile=profile,
            reservation_id=reservation_id,
            lease_id=lease_id,
            observation=observation,
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_worker_recovery_resumes_after_postgres_receipt_commit(
    pg_container,
    test_database_url: str | None,
) -> None:
    raw_url = test_database_url or pg_container.get_connection_url()
    engine = create_async_engine(_async_postgres_url(raw_url), pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex
    worker_schema = PostgresWorkerStateSchema(
        profile_table=f"slv2_recovery_profiles_{suffix}",
        reservation_table=f"slv2_recovery_reservations_{suffix}",
        lease_table=f"slv2_recovery_leases_{suffix}",
        observation_table=f"slv2_recovery_observations_{suffix}",
    )
    recovery_schema = PostgresWorkerRecoverySchema(
        recovery_table=f"slv2_recovery_receipts_{suffix}"
    )
    tables = (
        recovery_schema.recovery_table,
        worker_schema.observation_table,
        worker_schema.lease_table,
        worker_schema.reservation_table,
        worker_schema.profile_table,
    )
    try:
        async with engine.begin() as connection:
            for statement in worker_schema.statements:
                await connection.execute(text(statement))
            for statement in recovery_schema.statements:
                await connection.execute(text(statement))

        running, lease, admissions, pool = _admitted()
        state = PostgresWorkerStateAdapter(session_factory, schema=worker_schema)
        await state.ensure_profile(pool.profile)
        reservation = pool.active_reservations[0]
        reserved = await state.reserve(
            profile=pool.profile,
            attempt_id=reservation.attempt_id,
            reservation_id=reservation.reservation_id,
            acquired_at=reservation.acquired_at,
        )
        assert reserved.reservation == reservation
        await state.persist_lease(lease)

        failed = transition_attempt(running, AttemptState.FAILED, now=NOW + timedelta(seconds=5))
        interrupted = FailOnceBeforeCapacityRelease(session_factory, schema=worker_schema)
        first = PostgresWorkerRecoveryAdapter(
            session_factory,
            worker_state=interrupted,
            schema=recovery_schema,
        )
        with pytest.raises(RuntimeError, match="interruption"):
            await first.recover(
                principal="postgres-recovery-owner",
                prior_attempts=(failed,),
                admission_ledger=admissions,
                profile=pool.profile,
                lease_id=lease.lease_id,
                reason=RecoveryReason.LEASE_EXPIRED,
                observed_at=NOW + timedelta(seconds=40),
                next_attempt_id="attempt-2",
            )

        receipts = await first.load_ledger(principal="postgres-recovery-owner")
        assert len(receipts.records) == 1
        assert (await state.load_pool(pool.profile)).active_reservations

        restarted_state = PostgresWorkerStateAdapter(session_factory, schema=worker_schema)
        restarted = PostgresWorkerRecoveryAdapter(
            session_factory,
            worker_state=restarted_state,
            schema=recovery_schema,
        )
        recovered = await restarted.recover(
            principal="postgres-recovery-owner",
            prior_attempts=(failed,),
            admission_ledger=admissions,
            profile=pool.profile,
            lease_id=lease.lease_id,
            reason=RecoveryReason.LEASE_EXPIRED,
            observed_at=NOW + timedelta(seconds=41),
        )
        replay = await restarted.recover(
            principal="postgres-recovery-owner",
            prior_attempts=(failed,),
            admission_ledger=admissions,
            profile=pool.profile,
            lease_id=lease.lease_id,
            reason=RecoveryReason.LEASE_EXPIRED,
            observed_at=NOW + timedelta(seconds=42),
        )

        assert recovered.decision is WorkerRecoveryDecision.REPLAY_EXISTING
        assert recovered.next_attempt is not None
        assert recovered.next_attempt.attempt_id == "attempt-2"
        assert replay.decision is WorkerRecoveryDecision.REPLAY_EXISTING
        assert replay.next_attempt == recovered.next_attempt
        assert replay.pool == recovered.pool
        assert not replay.pool.active_reservations
        assert replay.lease_state == recovered.lease_state
        assert replay.lease_state.lease.released_at == NOW + timedelta(seconds=40)
        assert len((await restarted.load_ledger(principal="postgres-recovery-owner")).records) == 1
    finally:
        async with engine.begin() as connection:
            for table in tables:
                await connection.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
        await engine.dispose()
