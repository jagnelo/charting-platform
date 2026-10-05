from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.strategy_lab_v2.contracts import ForwardState
from app.strategy_lab_v2.postgres_forward_state import (
    ForwardStateMutationDecision,
    PostgresForwardStateAdapter,
    PostgresForwardStateSchema,
)
from app.strategy_lab_v2.tests.test_postgres_forward_state import _instance, _receipt

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)


def _async_postgres_url(raw_url: str) -> str:
    if raw_url.startswith("postgresql+asyncpg://"):
        return raw_url
    if raw_url.startswith("postgresql+psycopg2://"):
        return raw_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    raise ValueError("integration database URL must use PostgreSQL")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_forward_lifecycle_receipt_replays_original_instance_snapshot(
    pg_container,
    test_database_url: str | None,
) -> None:
    raw_url = test_database_url or pg_container.get_connection_url()
    engine = create_async_engine(_async_postgres_url(raw_url), pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex
    schema = PostgresForwardStateSchema(
        instance_table=f"slv2_forward_instances_{suffix}",
        warmup_table=f"slv2_forward_warmups_{suffix}",
        event_table=f"slv2_forward_events_{suffix}",
        replay_table=f"slv2_forward_replays_{suffix}",
        lifecycle_table=f"slv2_forward_lifecycle_{suffix}",
    )
    tables = (
        schema.lifecycle_table,
        schema.replay_table,
        schema.event_table,
        schema.warmup_table,
        schema.instance_table,
    )
    try:
        async with engine.begin() as connection:
            for statement in schema.statements:
                await connection.execute(text(statement))

        owner = f"forward-owner-{suffix}"
        instance = _instance()
        adapter = PostgresForwardStateAdapter(session_factory, schema=schema)
        await adapter.ensure_instance(principal=owner, instance=instance)
        transitioned_at = NOW + timedelta(seconds=1)
        first = await adapter.transition(
            principal=owner,
            instance_id=instance.instance_id,
            target=ForwardState.WARMING_UP,
            now=transitioned_at,
            idempotency_key="warmup-transition",
        )
        assert first.decision is ForwardStateMutationDecision.APPLIED
        assert first.instance is not None
        await adapter.complete_warmup(principal=owner, receipt=_receipt(first.instance))

        restarted = PostgresForwardStateAdapter(session_factory, schema=schema)
        replay = await restarted.transition(
            principal=owner,
            instance_id=instance.instance_id,
            target=ForwardState.WARMING_UP,
            now=transitioned_at,
            idempotency_key="warmup-transition",
        )
        assert replay.decision is ForwardStateMutationDecision.REPLAY_EXISTING
        assert replay.instance == first.instance
        assert replay.instance is not None and replay.instance.state is ForwardState.WARMING_UP

        conflict = await restarted.transition(
            principal=owner,
            instance_id=instance.instance_id,
            target=ForwardState.PAUSED,
            now=NOW + timedelta(minutes=2),
            idempotency_key="warmup-transition",
        )
        assert conflict.decision is ForwardStateMutationDecision.CONFLICT
        assert "Idempotency-Key" in (conflict.rejection_reason or "")

        hidden = await restarted.transition(
            principal=f"foreign-{suffix}",
            instance_id=instance.instance_id,
            target=ForwardState.WARMING_UP,
            now=transitioned_at,
            idempotency_key="warmup-transition",
        )
        assert hidden.decision is ForwardStateMutationDecision.NOT_FOUND
        assert hidden.instance is None
    finally:
        async with engine.begin() as connection:
            for table in tables:
                await connection.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
        await engine.dispose()
