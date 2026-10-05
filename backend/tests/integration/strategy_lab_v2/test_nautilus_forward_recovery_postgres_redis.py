from __future__ import annotations

import asyncio
import json
import os
import subprocess
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import CarryInMode, ForwardInstance, ForwardState
from app.strategy_lab_v2.dispatch import DispatchRequest, build_dispatch_envelope
from app.strategy_lab_v2.dispatch_payload import DispatchPayload
from app.strategy_lab_v2.forward_account import (
    ForwardAccountEventBinding,
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
from app.strategy_lab_v2.lifecycle import ForwardCursor, observe_forward_event
from app.strategy_lab_v2.nautilus_forward_bootstrap import NautilusForwardRuntimeBootstrap
from app.strategy_lab_v2.nautilus_forward_delivery import (
    create_nautilus_forward_delivery_callback_factory,
)
from app.strategy_lab_v2.nautilus_forward_process import (
    HardenedNautilusForwardSessionProcessFactory,
    NautilusForwardSessionProcess,
)
from app.strategy_lab_v2.nautilus_forward_recovery import (
    AuthenticatedNautilusForwardCheckpointResolver,
)
from app.strategy_lab_v2.nautilus_forward_session import NautilusForwardSessionEventHandler
from app.strategy_lab_v2.nautilus_forward_wire import NautilusForwardJsonWireCodec
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
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile, RuntimeIsolationRequest
from app.strategy_lab_v2.runtime_execution import StrategyRuntimeRequest
from app.strategy_lab_v2.sandbox import build_nautilus_forward_runtime_sandbox_command
from app.strategy_lab_v2.worker_consumer import (
    RedisDispatchWorker,
    WorkerEntryDecision,
    WorkerHandleDecision,
)

_IMAGE_DIGEST = os.environ.get("STRATEGY_LAB_V2_NAUTILUS_RC_IMAGE_DIGEST")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _IMAGE_DIGEST,
        reason="requires the exact-source Nautilus RC5 image and explicit Docker opt-in",
    ),
]


def _async_postgres_url(raw_url: str) -> str:
    if raw_url.startswith("postgresql+asyncpg://"):
        return raw_url
    if raw_url.startswith("postgresql+psycopg2://"):
        return raw_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    raise ValueError("integration database URL must use PostgreSQL")


def _manifest(directory: Path) -> dict[str, Any]:
    value = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("RC5 forward fixture manifest must be an object")
    return value


def _fixture_payload(directory: Path):
    value = json.loads((directory / "execute.json").read_text(encoding="utf-8"))
    return NautilusForwardJsonWireCodec().decode_execute_payload(value)


def _rebind_bootstrap(
    directory: Path,
    *,
    checkpoint_fingerprint: str,
    warmup_receipt_fingerprint: str,
    previous_checkpoint_fingerprint: str | None = None,
) -> None:
    manifest = _manifest(directory)
    bootstrap = NautilusForwardRuntimeBootstrap.from_json_bytes(
        (directory / "bootstrap.json").read_bytes(),
        expected_fingerprint=str(manifest["bootstrap_fingerprint"]),
    )
    if bootstrap.processed_events:
        if previous_checkpoint_fingerprint is None:
            raise ValueError("processed RC5 fixture requires its actual prior checkpoint")
        rebound = replace(
            bootstrap,
            processed_checkpoint_fingerprint=checkpoint_fingerprint,
            warmup_receipt_fingerprint=warmup_receipt_fingerprint,
            processed_prefix_fingerprint=content_digest(
                {
                    "prior_checkpoint": previous_checkpoint_fingerprint,
                    "events": list(bootstrap.processed_events),
                }
            ),
        )
    else:
        rebound = replace(
            bootstrap,
            processed_checkpoint_fingerprint=checkpoint_fingerprint,
            warmup_receipt_fingerprint=warmup_receipt_fingerprint,
        )
    (directory / "bootstrap.json").write_bytes(rebound.to_json_bytes())
    manifest["bootstrap_fingerprint"] = rebound.fingerprint
    manifest["checkpoint_fingerprint"] = checkpoint_fingerprint
    (directory / "manifest.json").write_text(
        json.dumps(manifest, allow_nan=False, separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )


async def _kill_process(process: NautilusForwardSessionProcess) -> None:
    child = process._transport._process
    if child.poll() is None:
        child.kill()
    await asyncio.to_thread(child.wait, timeout=10)


def _sandbox_plan_factory(
    *,
    directories: dict[str, Path],
    image_digest: str,
    principal: str,
    resolver: AuthenticatedNautilusForwardCheckpointResolver,
    event_loop: asyncio.AbstractEventLoop,
    output_directory: Path,
    starts: list[str],
):
    require_sha256_digest(image_digest, field_name="image_digest")

    def resolve(instance_id: str, checkpoint_fingerprint: str):
        resolved = asyncio.run_coroutine_threadsafe(
            resolver.resolve(
                instance_id=instance_id,
                checkpoint_fingerprint=checkpoint_fingerprint,
            ),
            event_loop,
        ).result(timeout=30)
        if (
            resolved.admission_state.checkpoint.instance.instance_id != instance_id
            or resolved.checkpoint_fingerprint != checkpoint_fingerprint
        ):
            raise ValueError("persisted PostgreSQL checkpoint differs from the process request")
        directory = directories.get(checkpoint_fingerprint)
        if directory is None:
            raise ValueError("RC5 fixture catalog has no requested PostgreSQL checkpoint")
        starts.append(checkpoint_fingerprint)
        manifest = _manifest(directory)
        bootstrap_path = directory / "bootstrap.json"
        bootstrap = NautilusForwardRuntimeBootstrap.from_json_bytes(
            bootstrap_path.read_bytes(),
            expected_fingerprint=str(manifest["bootstrap_fingerprint"]),
        )
        if (
            manifest.get("instance_id") != instance_id
            or manifest.get("checkpoint_fingerprint") != checkpoint_fingerprint
            or bootstrap.instance_id != instance_id
            or bootstrap.processed_checkpoint_fingerprint != checkpoint_fingerprint
            or bootstrap.warmup_receipt_fingerprint != resolved.warmup_receipt.fingerprint
        ):
            raise ValueError("RC5 bootstrap differs from authenticated PostgreSQL recovery state")

        component = bootstrap.components[0]
        bundle_path = directory / "bundle.json"
        bundle = json.loads(bundle_path.read_bytes())
        engine_input = bundle.get("engine_input")
        if not isinstance(engine_input, dict) or not isinstance(
            engine_input.get("attempt_id"), str
        ):
            raise ValueError("RC5 bundle has no bound runtime attempt")
        attempt_id = engine_input["attempt_id"]
        profile = RuntimeIsolationProfile(
            runtime_image_digest=image_digest,
            runtime_abi="python-3.12.4-manylinux_2_34_x86_64",
            network_disabled=True,
            allowed_dependency_digests=frozenset({component.dependency_lock_digest}),
        )
        request = StrategyRuntimeRequest(
            request_id=content_digest(
                {"instance_id": instance_id, "checkpoint": checkpoint_fingerprint}
            ),
            attempt_id=attempt_id,
            package_fingerprint=component.package_fingerprint,
            source_digest=component.source_digest,
            input_bundle_digest=bootstrap.runtime_input_bundle_digest,
            runtime_profile_fingerprint=profile.fingerprint,
            entrypoint="strategy.main:Strategy",
            isolation_request=RuntimeIsolationRequest(
                attempt_id,
                (component.dependency_lock_digest,),
            ),
            submitted_at=datetime(2024, 1, 2, tzinfo=UTC),
        )
        context_path = directory / "contexts.ndjson"
        native_path = directory / "native-events.parquet"
        output_path = output_directory / f"{checkpoint_fingerprint.removeprefix('sha256:')}.json"
        output_path.write_bytes(b"")
        return build_nautilus_forward_runtime_sandbox_command(
            request,
            profile,
            image_name="strategy-lab-v2/nautilus-rc5",
            input_bundle_path=bundle_path,
            forward_bootstrap_path=bootstrap_path,
            bootstrap_fingerprint=bootstrap.fingerprint,
            context_stream_path=context_path,
            context_stream_digest=artifact_content_digest(context_path.read_bytes()),
            native_event_stream_path=native_path,
            native_event_stream_digest=artifact_content_digest(native_path.read_bytes()),
            output_path=output_path,
            instance_id=instance_id,
            expected_version="2.0.0rc5",
            snapshot_fingerprint=bootstrap.snapshot_fingerprint,
        )

    return resolve


class _UnexpectedNativeExecution:
    def execute(self, *_args, **_kwargs):
        raise AssertionError("a settled Redis redelivery must not invoke Nautilus")

    async def restore(self, **_kwargs):
        raise AssertionError("a settled Redis redelivery must not restore Nautilus")


@pytest.mark.asyncio
async def test_exact_rc5_forward_recovery_settles_postgres_then_acks_redis_without_rerun(
    pg_container,
    test_database_url: str | None,
    redis_url: str,
    tmp_path: Path,
) -> None:
    assert _IMAGE_DIGEST is not None
    image_digest = str(_IMAGE_DIGEST)
    require_sha256_digest(image_digest, field_name="image_digest")
    tmp_path.chmod(0o755)
    exports = tmp_path / "exports"
    exports.mkdir(mode=0o755)
    emitted = subprocess.run(
        (
            "docker",
            "run",
            "--rm",
            "--network=none",
            "--read-only",
            f"--user={os.getuid()}:{os.getgid()}",
            f"--mount=type=bind,src={exports},dst=/outputs",
            "strategy-lab-v2/nautilus-rc5@" + image_digest,
            "python",
            "-m",
            "app.strategy_lab_v2.nautilus_rc_fixture_probe",
            "--emit-forward-process-fixture",
            "/outputs",
        ),
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert json.loads(emitted.stdout)["passed"] is True
    before_dir = exports / "before"
    after_dir = exports / "after"
    bootstrap = NautilusForwardRuntimeBootstrap.from_json_bytes(
        (before_dir / "bootstrap.json").read_bytes(),
        expected_fingerprint=str(_manifest(before_dir)["bootstrap_fingerprint"]),
    )
    fixture_delivery, fixture_preparation = _fixture_payload(before_dir)
    canonical = fixture_delivery.tape.envelopes[0].canonical_event
    warmup_time = canonical.event_time - timedelta(seconds=1)
    created_at = canonical.event_time - timedelta(days=1)

    raw_url = test_database_url or pg_container.get_connection_url()
    engine = create_async_engine(_async_postgres_url(raw_url), pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    redis = Redis.from_url(redis_url, decode_responses=True)
    suffix = uuid4().hex
    instance_id = bootstrap.instance_id
    principal = f"rc5-forward-owner-{suffix}"
    namespace = f"strategy-lab:v2:rc5-forward-recovery:{suffix}"
    queue_name = "forward-events"
    state_schema = PostgresForwardStateSchema(
        instance_table=f"slv2_r5_instances_{suffix}",
        warmup_table=f"slv2_r5_warmups_{suffix}",
        event_table=f"slv2_r5_events_{suffix}",
        replay_table=f"slv2_r5_replays_{suffix}",
        lifecycle_table=f"slv2_r5_lifecycle_{suffix}",
        checkpoint_history_table=f"slv2_r5_checkpoints_{suffix}",
    )
    account_schema = PostgresForwardAccountSchema(
        account_table=f"slv2_r5_accounts_{suffix}",
        history_table=f"slv2_r5_account_history_{suffix}",
    )
    tables = (
        state_schema.checkpoint_history_table,
        state_schema.lifecycle_table,
        state_schema.replay_table,
        state_schema.event_table,
        state_schema.warmup_table,
        state_schema.instance_table,
        account_schema.history_table,
        account_schema.account_table,
    )
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
            bootstrap.portfolio_fingerprint,
            bootstrap.snapshot_fingerprint,
            CarryInMode.FLAT,
            ForwardState.CREATED,
            None,
            0,
            0,
            created_at,
            created_at,
        )
        await state_store.ensure_instance(principal=principal, instance=instance)
        warming = await state_store.transition(
            principal=principal,
            instance_id=instance_id,
            target=ForwardState.WARMING_UP,
            now=created_at + timedelta(seconds=1),
            idempotency_key=f"rc5-warmup-{suffix}",
        )
        assert warming.instance is not None
        warmup = ForwardWarmupReceipt(
            instance_id,
            bootstrap.snapshot_fingerprint,
            CarryInMode.FLAT,
            bootstrap.warmup_result_fingerprint,
            warmup_time,
            final_event_id=bootstrap.warmup_cursor_event_id,
            final_event_sequence=bootstrap.warmup_cursor_sequence,
            final_event_fingerprint=bootstrap.warmup_cursor_event_fingerprint,
        )
        await state_store.complete_warmup(principal=principal, receipt=warmup)
        pre_event = await state_store.load_state(principal=principal, instance_id=instance_id)
        assert pre_event is not None
        await account_store.initialize(
            principal=principal,
            state=initial_forward_account_state(instance_id, base_currency="USD"),
            admission_state=pre_event,
        )
        cursor = ForwardCursor(
            last_sequence=bootstrap.warmup_cursor_sequence,
            last_event_id=bootstrap.warmup_cursor_event_id,
            last_event_time=warmup_time,
        )
        admitted = await state_store.admit(
            principal=principal,
            instance_id=instance_id,
            event=canonical,
            observation=observe_forward_event(cursor, canonical),
        )
        assert admitted.decision is ForwardAdmissionDecision.ACCEPTED
        post_event_checkpoint = admitted.state.checkpoint.fingerprint
        before_checkpoint = pre_event.checkpoint.fingerprint
        _rebind_bootstrap(
            before_dir,
            checkpoint_fingerprint=before_checkpoint,
            warmup_receipt_fingerprint=warmup.fingerprint,
        )
        _rebind_bootstrap(
            after_dir,
            checkpoint_fingerprint=post_event_checkpoint,
            warmup_receipt_fingerprint=warmup.fingerprint,
            previous_checkpoint_fingerprint=before_checkpoint,
        )

        dispatch_payload = DispatchPayload.from_mapping(
            {"event_fingerprint": content_digest(canonical), "replay_plan_fingerprint": None}
        )
        request = DispatchRequest(
            f"{instance_id}:{canonical.event_id}",
            instance_id,
            dispatch_payload.payload_digest,
            queue_name,
            canonical.arrived_at,
        )
        await transport.enqueue(build_dispatch_envelope(request))
        dispatch = ForwardEventDispatchRecord(
            principal,
            instance_id,
            content_digest(canonical),
            request,
            pre_event_checkpoint_fingerprint=before_checkpoint,
            warmup_receipt_fingerprint=warmup.fingerprint,
            admission_decision="enqueue",
        )
        work_item = ForwardEventWorkItem(
            dispatch,
            ForwardEventDispatchPayload(content_digest(canonical)),
        )
        first_worker = RedisDispatchWorker(
            transport,
            queue_name=queue_name,
            group_name="rc5-forward-workers",
            consumer_name="crashed-before-settlement",
            reclaim_idle_ms=0,
        )
        first_poll = await first_worker.poll()
        assert len(first_poll.entries) == 1
        first_entry = first_poll.entries[0]

        verified_payload = fixture_delivery.verified_market_payload
        dependency = fixture_delivery.market_event.dependency_id
        event_type = fixture_delivery.tape.envelopes[0].record.event_type
        delivery_factory = create_nautilus_forward_delivery_callback_factory(
            lambda *, instance_id, event_fingerprint: verified_payload,
            event_type_by_dependency={dependency: event_type},
        )
        delivery = await delivery_factory(first_entry, work_item)
        assert delivery.delivery_binding.pre_event_checkpoint_fingerprint == before_checkpoint
        assert delivery.delivery_binding.warmup_receipt_fingerprint == warmup.fingerprint
        preparation = replace(
            fixture_preparation,
            delivery_binding_fingerprint=delivery.delivery_binding.fingerprint,
            dispatch_fingerprint=delivery.delivery_binding.dispatch_record_fingerprint,
            pre_event_checkpoint_fingerprint=before_checkpoint,
            warmup_receipt_fingerprint=warmup.fingerprint,
        )

        resolver = AuthenticatedNautilusForwardCheckpointResolver(
            state_store,
            account_store,
            principal=principal,
        )
        event_loop = asyncio.get_running_loop()
        starts: list[str] = []
        output_directory = tmp_path / "private-output"
        output_directory.mkdir(mode=0o700)
        process_factory = HardenedNautilusForwardSessionProcessFactory(
            _sandbox_plan_factory(
                directories={before_checkpoint: before_dir, post_event_checkpoint: after_dir},
                image_digest=image_digest,
                principal=principal,
                resolver=resolver,
                event_loop=event_loop,
                output_directory=output_directory,
                starts=starts,
            ),
            response_timeout_seconds=90,
        )

        first_process = await process_factory.start(
            instance_id=instance_id,
            checkpoint_fingerprint=before_checkpoint,
        )
        first_result = await first_process.execute(delivery, preparation)
        await _kill_process(
            first_process
        )  # Native output existed, but PostgreSQL had not settled it.

        retry_worker = RedisDispatchWorker(
            transport,
            queue_name=queue_name,
            group_name="rc5-forward-workers",
            consumer_name="retry-before-settlement",
            reclaim_idle_ms=0,
        )
        retry_poll = await retry_worker.poll()
        assert len(retry_poll.entries) == 1
        retry_entry = retry_poll.entries[0]
        retry_delivery = await delivery_factory(retry_entry, work_item)
        retry_preparation = replace(
            fixture_preparation,
            delivery_binding_fingerprint=retry_delivery.delivery_binding.fingerprint,
            dispatch_fingerprint=retry_delivery.delivery_binding.dispatch_record_fingerprint,
            pre_event_checkpoint_fingerprint=before_checkpoint,
            warmup_receipt_fingerprint=warmup.fingerprint,
        )
        retry_process = await process_factory.start(
            instance_id=instance_id,
            checkpoint_fingerprint=before_checkpoint,
        )
        retry_result = await retry_process.execute(retry_delivery, retry_preparation)
        assert retry_result.native_output_fingerprint == first_result.native_output_fingerprint
        assert retry_result.account_event_binding.fingerprint == (
            first_result.account_event_binding.fingerprint
        )

        canonical_event = retry_delivery.tape.envelopes[0].canonical_event
        native_binding = retry_result.account_event_binding
        receipt = ForwardRuntimeExecutionReceipt(
            instance_id,
            canonical_event.event_id,
            content_digest(canonical_event),
            retry_delivery.delivery_binding.fingerprint,
            retry_preparation.fingerprint,
            before_checkpoint,
            retry_result.runtime_session_fingerprint,
            retry_result.native_output_fingerprint,
        )
        persisted_binding = ForwardAccountEventBinding(
            canonical_event,
            native_binding.account_event,
            receipt,
        )
        account_handler = ForwardAccountWorkerHandler(
            account_store,
            principal=principal,
            event_resolver=lambda _entry, _item: persisted_binding,
        )
        committed = await account_handler(retry_entry, work_item)
        assert committed.decision is WorkerHandleDecision.COMPLETE
        await _kill_process(retry_process)  # PostgreSQL committed; Redis ACK is still pending.
        assert await redis.xpending(stream_key, "rc5-forward-workers") == {
            "pending": 1,
            "min": retry_entry.stream_id,
            "max": retry_entry.stream_id,
            "consumers": [{"name": "retry-before-settlement", "pending": 1}],
        }
        resolved_after = await resolver.resolve(
            instance_id=instance_id,
            checkpoint_fingerprint=post_event_checkpoint,
        )
        assert resolved_after.account_state.last_event_id == canonical.event_id
        assert resolved_after.account_state.applied_events[-1].event_id == canonical.event_id
        assert len(starts) == 2

        redelivery_handler = NautilusForwardSessionEventHandler(
            delivery_factory,
            lambda _delivery: (_ for _ in ()).throw(
                AssertionError("settled redelivery must bypass context reconstruction")
            ),
            _UnexpectedNativeExecution(),
            account_store,
            principal=principal,
        )
        ack_worker = RedisDispatchWorker(
            transport,
            queue_name=queue_name,
            group_name="rc5-forward-workers",
            consumer_name="post-commit-restart",
            reclaim_idle_ms=0,
        )

        async def handle_redelivery(entry):
            return await redelivery_handler(entry, work_item)

        replay_cycle = await ack_worker.handle_once(handle_redelivery)
        assert len(replay_cycle.entries) == 1
        assert replay_cycle.entries[0].decision is WorkerEntryDecision.ACKNOWLEDGED
        assert replay_cycle.entries[0].handler.decision is WorkerHandleDecision.COMPLETE
        assert replay_cycle.entries[0].acknowledgement is not None
        assert replay_cycle.entries[0].acknowledgement.acknowledged
        assert len(starts) == 2  # receipt-first handler did not launch Nautilus again
        assert await redis.xpending(stream_key, "rc5-forward-workers") == {
            "pending": 0,
            "min": None,
            "max": None,
            "consumers": [],
        }

        # Once the first event is ACKed, the next exact RC5 process must rebuild
        # from the newly committed PostgreSQL account/admission checkpoint.
        next_fixture_delivery, next_fixture_preparation = _fixture_payload(after_dir)
        next_canonical = next_fixture_delivery.tape.envelopes[0].canonical_event
        next_cursor = ForwardCursor(
            last_sequence=canonical.sequence,
            last_event_id=canonical.event_id,
            last_event_time=canonical.event_time,
        )
        next_admission = await state_store.admit(
            principal=principal,
            instance_id=instance_id,
            event=next_canonical,
            observation=observe_forward_event(next_cursor, next_canonical),
        )
        assert next_admission.decision is ForwardAdmissionDecision.ACCEPTED
        next_checkpoint = post_event_checkpoint
        next_payload = DispatchPayload.from_mapping(
            {
                "event_fingerprint": content_digest(next_canonical),
                "replay_plan_fingerprint": None,
            }
        )
        next_request = DispatchRequest(
            f"{instance_id}:{next_canonical.event_id}",
            instance_id,
            next_payload.payload_digest,
            queue_name,
            next_canonical.arrived_at,
        )
        await transport.enqueue(build_dispatch_envelope(next_request))
        next_dispatch = ForwardEventDispatchRecord(
            principal,
            instance_id,
            content_digest(next_canonical),
            next_request,
            pre_event_checkpoint_fingerprint=next_checkpoint,
            warmup_receipt_fingerprint=warmup.fingerprint,
            admission_decision="enqueue",
        )
        next_work_item = ForwardEventWorkItem(
            next_dispatch,
            ForwardEventDispatchPayload(content_digest(next_canonical)),
        )
        next_dependency = next_fixture_delivery.market_event.dependency_id
        next_event_type = next_fixture_delivery.tape.envelopes[0].record.event_type
        next_delivery_factory = create_nautilus_forward_delivery_callback_factory(
            lambda *, instance_id, event_fingerprint: next_fixture_delivery.verified_market_payload,
            event_type_by_dependency={next_dependency: next_event_type},
        )
        next_worker = RedisDispatchWorker(
            transport,
            queue_name=queue_name,
            group_name="rc5-forward-workers",
            consumer_name="post-ack-continuation",
            reclaim_idle_ms=0,
        )
        next_poll = await next_worker.poll()
        assert len(next_poll.entries) == 1
        next_entry = next_poll.entries[0]
        next_delivery = await next_delivery_factory(next_entry, next_work_item)
        assert next_delivery.delivery_binding.pre_event_checkpoint_fingerprint == next_checkpoint
        next_preparation = replace(
            next_fixture_preparation,
            delivery_binding_fingerprint=next_delivery.delivery_binding.fingerprint,
            dispatch_fingerprint=next_delivery.delivery_binding.dispatch_record_fingerprint,
            pre_event_checkpoint_fingerprint=next_checkpoint,
            warmup_receipt_fingerprint=warmup.fingerprint,
        )
        continuation = await process_factory.start(
            instance_id=instance_id,
            checkpoint_fingerprint=next_checkpoint,
        )
        continuation_result = await continuation.execute(next_delivery, next_preparation)
        assert continuation_result.account_event_binding.canonical_event == next_canonical
        continuation_receipt = ForwardRuntimeExecutionReceipt(
            instance_id,
            next_canonical.event_id,
            content_digest(next_canonical),
            next_delivery.delivery_binding.fingerprint,
            next_preparation.fingerprint,
            next_checkpoint,
            continuation_result.runtime_session_fingerprint,
            continuation_result.native_output_fingerprint,
        )
        continuation_binding = ForwardAccountEventBinding(
            next_canonical,
            continuation_result.account_event_binding.account_event,
            continuation_receipt,
        )
        continuation_handler = ForwardAccountWorkerHandler(
            account_store,
            principal=principal,
            event_resolver=lambda _entry, _item: continuation_binding,
        )

        async def settle_continuation(entry):
            return await continuation_handler(entry, next_work_item)

        continuation_cycle = await next_worker.handle_once(settle_continuation)
        assert len(continuation_cycle.entries) == 1
        assert continuation_cycle.entries[0].decision is WorkerEntryDecision.ACKNOWLEDGED
        assert continuation_cycle.entries[0].handler.decision is WorkerHandleDecision.COMPLETE
        assert continuation_cycle.entries[0].acknowledgement is not None
        assert continuation_cycle.entries[0].acknowledgement.acknowledged
        assert len(starts) == 3
        assert await redis.xpending(stream_key, "rc5-forward-workers") == {
            "pending": 0,
            "min": None,
            "max": None,
            "consumers": [],
        }
        await _kill_process(continuation)
    finally:
        await redis.aclose()
        async with engine.begin() as connection:
            for table in (*tables,):
                await connection.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
        await engine.dispose()
