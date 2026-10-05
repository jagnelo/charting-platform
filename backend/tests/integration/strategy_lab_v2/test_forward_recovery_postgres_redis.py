from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import CarryInMode, ForwardInstance, ForwardState
from app.strategy_lab_v2.dispatch import DispatchRequest, build_dispatch_envelope
from app.strategy_lab_v2.dispatch_payload import DispatchPayload
from app.strategy_lab_v2.forward_account import (
    ForwardAccountEvent,
    ForwardAccountEventBinding,
    ForwardAppliedAccountExecutionEvent,
    ForwardRuntimeExecutionReceipt,
    initial_forward_account_state,
)
from app.strategy_lab_v2.forward_account_worker import ForwardAccountWorkerHandler
from app.strategy_lab_v2.forward_admission import ForwardAdmissionDecision
from app.strategy_lab_v2.forward_warmup import ForwardWarmupReceipt
from app.strategy_lab_v2.forward_worker_handoff import (
    ForwardEventDispatchPayload,
    ForwardEventWorkItem,
)
from app.strategy_lab_v2.lifecycle import (
    CanonicalForwardEvent,
    ForwardCursor,
    observe_forward_event,
)
from app.strategy_lab_v2.nautilus_forward_recovery import (
    AuthenticatedNautilusForwardCheckpointResolver,
)
from app.strategy_lab_v2.postgres_forward_account import (
    PostgresForwardAccountAdapter,
    PostgresForwardAccountSchema,
)
from app.strategy_lab_v2.postgres_forward_dispatch import ForwardEventDispatchRecord
from app.strategy_lab_v2.postgres_forward_state import (
    PostgresForwardStateAdapter,
    PostgresForwardStateSchema,
)
from app.strategy_lab_v2.redis_transport import RedisDispatchTransport
from app.strategy_lab_v2.worker_consumer import (
    RedisDispatchWorker,
    WorkerEntryDecision,
    WorkerHandleDecision,
)

_NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)


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
async def test_forward_recovery_uses_postgres_receipt_before_redis_replay_ack(
    pg_container,
    test_database_url: str | None,
    redis_url: str,
) -> None:
    raw_url = test_database_url or pg_container.get_connection_url()
    engine = create_async_engine(_async_postgres_url(raw_url), pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    redis = Redis.from_url(redis_url, decode_responses=True)
    suffix = uuid4().hex
    instance_id = f"forward-recovery-{suffix}"
    owner = f"recovery-owner-{suffix}"
    namespace = f"strategy-lab:v2:forward-recovery:{suffix}"
    queue_name = "forward-events"
    state_schema = PostgresForwardStateSchema(
        instance_table=f"slv2_fr_instances_{suffix}",
        warmup_table=f"slv2_fr_warmups_{suffix}",
        event_table=f"slv2_fr_events_{suffix}",
        replay_table=f"slv2_fr_replays_{suffix}",
        lifecycle_table=f"slv2_fr_lifecycle_{suffix}",
        checkpoint_history_table=f"slv2_fr_checkpoints_{suffix}",
    )
    account_schema = PostgresForwardAccountSchema(
        account_table=f"slv2_fr_accounts_{suffix}",
        history_table=f"slv2_fr_account_history_{suffix}",
    )
    state_tables = (
        state_schema.checkpoint_history_table,
        state_schema.lifecycle_table,
        state_schema.replay_table,
        state_schema.event_table,
        state_schema.warmup_table,
        state_schema.instance_table,
    )
    account_tables = (account_schema.history_table, account_schema.account_table)
    transport = RedisDispatchTransport(redis, namespace=namespace)
    stream_key = transport.stream_key(queue_name)

    try:
        async with engine.begin() as connection:
            for statement in (*state_schema.statements, *account_schema.statements):
                await connection.execute(text(statement))

        state_store = PostgresForwardStateAdapter(session_factory, schema=state_schema)
        account_store = PostgresForwardAccountAdapter(session_factory, schema=account_schema)
        instance = ForwardInstance(
            instance_id,
            content_digest({"portfolio": instance_id}),
            content_digest({"warmup": instance_id}),
            CarryInMode.FLAT,
            ForwardState.CREATED,
            None,
            0,
            0,
            _NOW,
            _NOW,
        )
        await state_store.ensure_instance(principal=owner, instance=instance)
        warming = await state_store.transition(
            principal=owner,
            instance_id=instance_id,
            target=ForwardState.WARMING_UP,
            now=_NOW + timedelta(seconds=1),
            idempotency_key="recovery-warmup",
        )
        assert warming.instance is not None
        warmup = ForwardWarmupReceipt(
            instance_id,
            instance.warmup_snapshot_fingerprint,
            CarryInMode.FLAT,
            content_digest({"warmup-result": instance_id}),
            _NOW + timedelta(minutes=1),
        )
        await state_store.complete_warmup(principal=owner, receipt=warmup)
        before = await state_store.load_state(principal=owner, instance_id=instance_id)
        assert before is not None
        await account_store.initialize(
            principal=owner,
            state=initial_forward_account_state(instance_id, base_currency="USD"),
            admission_state=before,
        )

        canonical = CanonicalForwardEvent(
            "live-event-0",
            0,
            _NOW + timedelta(minutes=2),
            _NOW + timedelta(minutes=2, seconds=1),
            content_digest({"source": "live-event-0"}),
        )
        admission = await state_store.admit(
            principal=owner,
            instance_id=instance_id,
            event=canonical,
            observation=observe_forward_event(ForwardCursor(), canonical),
        )
        assert admission.decision is ForwardAdmissionDecision.ACCEPTED
        after = admission.state
        account_event = ForwardAccountEvent(
            instance_id,
            canonical.event_id,
            content_digest(canonical),
            canonical.sequence,
            canonical.event_time,
        )
        execution_receipt = ForwardRuntimeExecutionReceipt(
            instance_id,
            canonical.event_id,
            content_digest(canonical),
            content_digest("delivery-binding"),
            content_digest("context-preparation"),
            before.checkpoint.fingerprint,
            content_digest("native-session"),
            content_digest("native-output"),
        )

        payload = DispatchPayload.from_mapping(
            {"event_fingerprint": content_digest(canonical), "replay_plan_fingerprint": None}
        )
        request = DispatchRequest(
            f"{instance_id}:event-0",
            instance_id,
            payload.payload_digest,
            queue_name,
            _NOW,
        )
        queued = await transport.enqueue(build_dispatch_envelope(request))
        dispatch = ForwardEventDispatchRecord(
            owner,
            instance_id,
            content_digest(canonical),
            request,
            pre_event_checkpoint_fingerprint=before.checkpoint.fingerprint,
            warmup_receipt_fingerprint=warmup.fingerprint,
            admission_decision="enqueue",
        )
        work_item = ForwardEventWorkItem(
            dispatch,
            ForwardEventDispatchPayload(content_digest(canonical)),
        )
        handler = ForwardAccountWorkerHandler(
            account_store,
            principal=owner,
            event_resolver=lambda _entry, _item: ForwardAccountEventBinding(
                canonical,
                account_event,
                execution_receipt,
            ),
        )

        # Worker A receives the message and dies before durable settlement.
        worker_a = RedisDispatchWorker(
            transport,
            queue_name=queue_name,
            group_name="forward-workers",
            consumer_name="crashed-before-settlement",
            reclaim_idle_ms=0,
        )
        first_poll = await worker_a.poll()
        assert len(first_poll.entries) == 1
        first_entry = first_poll.entries[0]
        assert first_entry.message_id == queued.message_id

        # Worker B reclaims and commits Postgres state, then dies before XACK.
        worker_b = RedisDispatchWorker(
            transport,
            queue_name=queue_name,
            group_name="forward-workers",
            consumer_name="crashed-after-settlement",
            reclaim_idle_ms=0,
        )
        second_poll = await worker_b.poll()
        assert len(second_poll.entries) == 1
        second_entry = second_poll.entries[0]
        committed = await handler(second_entry, work_item)
        assert committed.decision is WorkerHandleDecision.COMPLETE
        assert await redis.xpending(stream_key, "forward-workers") == {
            "pending": 1,
            "min": second_entry.stream_id,
            "max": second_entry.stream_id,
            "consumers": [{"name": "crashed-after-settlement", "pending": 1}],
        }

        resolved = await AuthenticatedNautilusForwardCheckpointResolver(
            state_store,
            account_store,
            principal=owner,
        ).resolve(
            instance_id=instance_id,
            checkpoint_fingerprint=after.checkpoint.fingerprint,
        )
        assert resolved.account_state.last_event_id == canonical.event_id
        resolved_applied = resolved.account_state.applied_events[0]
        assert isinstance(resolved_applied, ForwardAppliedAccountExecutionEvent)
        assert resolved_applied.execution_receipt == execution_receipt
        persisted_settlement = await account_store.load_event_settlement(
            principal=owner,
            instance_id=instance_id,
            event_id=canonical.event_id,
        )
        assert persisted_settlement is not None
        assert persisted_settlement.event == account_event
        assert persisted_settlement.execution_receipt == execution_receipt

        # Worker C reclaims; Postgres reports REPLAY_EXISTING and only then Redis is ACKed.
        worker_c = RedisDispatchWorker(
            transport,
            queue_name=queue_name,
            group_name="forward-workers",
            consumer_name="restarted-worker",
            reclaim_idle_ms=0,
        )

        async def settle(entry):
            assert entry.message_id == queued.message_id
            return await handler(entry, work_item)

        replay_cycle = await worker_c.handle_once(settle)
        assert len(replay_cycle.entries) == 1
        replay = replay_cycle.entries[0]
        assert replay.decision is WorkerEntryDecision.ACKNOWLEDGED
        assert replay.handler.decision is WorkerHandleDecision.COMPLETE
        assert replay.acknowledgement is not None and replay.acknowledgement.acknowledged
        assert await redis.xpending(stream_key, "forward-workers") == {
            "pending": 0,
            "min": None,
            "max": None,
            "consumers": [],
        }

        replayed_state = await account_store.load_at_checkpoint(
            principal=owner,
            admission_state=after,
        )
        assert replayed_state == resolved.account_state
        replayed_applied = replayed_state.applied_events[0]
        assert isinstance(replayed_applied, ForwardAppliedAccountExecutionEvent)
        assert replayed_applied.execution_receipt == execution_receipt
    finally:
        await redis.delete(stream_key, f"{namespace}:idempotency")
        await redis.aclose()
        async with engine.begin() as connection:
            for table in (*account_tables, *state_tables):
                await connection.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
        await engine.dispose()
