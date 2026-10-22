"""Opt-in exact-image exercise of forward-process death and durable replay.

Set ``STRATEGY_LAB_V2_NAUTILUS_RC_IMAGE_DIGEST`` to an exact-source qualified
RC6 image ID and run this module with Docker API access to execute the test.
The default package suite skips it rather than substituting a fake process.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.nautilus_forward_bootstrap import NautilusForwardRuntimeBootstrap
from app.strategy_lab_v2.nautilus_forward_process import (
    HardenedNautilusForwardSessionProcessFactory,
    NautilusForwardSessionProcess,
)
from app.strategy_lab_v2.nautilus_forward_wire import NautilusForwardJsonWireCodec
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile, RuntimeIsolationRequest
from app.strategy_lab_v2.runtime_execution import StrategyRuntimeRequest
from app.strategy_lab_v2.sandbox import build_nautilus_forward_runtime_sandbox_command
from app.strategy_lab_v2.tests.forward_replay_ledger import DurableReplayLedger

_IMAGE_DIGEST = os.environ.get("STRATEGY_LAB_V2_NAUTILUS_RC_IMAGE_DIGEST")
pytestmark = pytest.mark.skipif(
    not _IMAGE_DIGEST,
    reason="requires an exact-source RC6 image and explicit Docker integration opt-in",
)


def _load_manifest(directory: Path) -> dict[str, Any]:
    value = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("forward process fixture manifest must be an object")
    return value


def _plan_factory(database: Path, image_digest: str):
    require_sha256_digest(image_digest, field_name="image_digest")
    output_directory = database.parent / "private-output"
    output_directory.mkdir(mode=0o700, exist_ok=True)

    def resolve(
        instance_id: str,
        checkpoint_fingerprint: str,
        delivery: Any,
        preparation: Any,
    ):
        if delivery.delivery_binding.instance_id != instance_id:
            raise ValueError("native plan builder received delivery for another instance")
        if delivery.delivery_binding.pre_event_checkpoint_fingerprint != checkpoint_fingerprint:
            raise ValueError("native plan builder received delivery for another checkpoint")
        if (
            preparation.instance_id != instance_id
            or preparation.pre_event_checkpoint_fingerprint != checkpoint_fingerprint
            or preparation.delivery_binding_fingerprint != delivery.delivery_binding.fingerprint
        ):
            raise ValueError("native plan builder received context rebound to another delivery")
        with sqlite3.connect(database) as connection:
            row = connection.execute(
                """SELECT fixture_directory FROM checkpoints
                   WHERE instance_id = ? AND checkpoint_fingerprint = ?""",
                (instance_id, checkpoint_fingerprint),
            ).fetchone()
        if row is None:
            raise ValueError("durable plan catalog has no requested forward checkpoint")
        directory = Path(str(row[0]))
        manifest = _load_manifest(directory)
        encoded_bootstrap = (directory / "bootstrap.json").read_bytes()
        bootstrap = NautilusForwardRuntimeBootstrap.from_json_bytes(
            encoded_bootstrap,
            expected_fingerprint=str(manifest["bootstrap_fingerprint"]),
        )
        if (
            manifest.get("instance_id") != instance_id
            or manifest.get("checkpoint_fingerprint") != checkpoint_fingerprint
            or bootstrap.instance_id != instance_id
            or bootstrap.processed_checkpoint_fingerprint != checkpoint_fingerprint
        ):
            raise ValueError("durable plan catalog returned a different forward checkpoint")

        component = bootstrap.components[0]
        bundle = json.loads((directory / "bundle.json").read_bytes())
        engine_input = bundle.get("engine_input")
        if not isinstance(engine_input, dict) or not isinstance(
            engine_input.get("attempt_id"), str
        ):
            raise ValueError("durable runtime bundle has no bound execution attempt")
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
        bundle_path = directory / "bundle.json"
        output_path = output_directory / f"{checkpoint_fingerprint.removeprefix('sha256:')}.json"
        output_path.write_bytes(b"")
        return build_nautilus_forward_runtime_sandbox_command(
            request,
            profile,
            image_name="strategy-lab-v2/nautilus-rc6",
            input_bundle_path=bundle_path,
            forward_bootstrap_path=directory / "bootstrap.json",
            bootstrap_fingerprint=bootstrap.fingerprint,
            context_stream_path=context_path,
            context_stream_digest=artifact_content_digest(context_path.read_bytes()),
            native_event_stream_path=native_path,
            native_event_stream_digest=artifact_content_digest(native_path.read_bytes()),
            output_path=output_path,
            instance_id=instance_id,
            expected_version="2.0.0rc6",
            snapshot_fingerprint=bootstrap.snapshot_fingerprint,
        )

    return resolve


def _kill_process(process: NautilusForwardSessionProcess) -> None:
    child = process._transport._process
    if child.poll() is None:
        child.kill()
        child.wait(timeout=10)
    asyncio.run(process.close())


def _fixture_payload(directory: Path):
    value = json.loads((directory / "execute.json").read_text(encoding="utf-8"))
    return NautilusForwardJsonWireCodec().decode_execute_payload(value)


def test_exact_rc6_forward_process_restarts_across_settlement_and_ack_windows(
    tmp_path: Path,
) -> None:
    image_digest = str(_IMAGE_DIGEST)
    require_sha256_digest(image_digest, field_name="image_digest")
    tmp_path.chmod(0o755)
    exports = tmp_path / "exports"
    exports.mkdir(mode=0o755)
    command = (
        "docker",
        "run",
        "--rm",
        "--network=none",
        "--read-only",
        f"--user={os.getuid()}:{os.getgid()}",
        f"--mount=type=bind,src={exports},dst=/outputs",
        "strategy-lab-v2/nautilus-rc6@" + image_digest,
        "python",
        "-m",
        "app.strategy_lab_v2.nautilus_rc_fixture_probe",
        "--emit-forward-process-fixture",
        "/outputs",
    )
    generated = subprocess.run(command, check=True, capture_output=True, text=True, timeout=180)
    receipt = json.loads(generated.stdout)
    assert receipt["passed"] is True
    before = exports / "before"
    after = exports / "after"
    before_manifest = _load_manifest(before)
    after_manifest = _load_manifest(after)
    instance_id = str(before_manifest["instance_id"])
    before_checkpoint = str(before_manifest["checkpoint_fingerprint"])
    after_checkpoint = str(after_manifest["checkpoint_fingerprint"])
    assert before_checkpoint != after_checkpoint

    ledger_path = tmp_path / "forward-recovery.sqlite3"
    DurableReplayLedger(ledger_path)
    with sqlite3.connect(ledger_path) as connection:
        connection.execute(
            """CREATE TABLE checkpoints (
                   instance_id TEXT NOT NULL,
                   checkpoint_fingerprint TEXT NOT NULL,
                   fixture_directory TEXT NOT NULL,
                   PRIMARY KEY (instance_id, checkpoint_fingerprint)
               )"""
        )
        connection.executemany(
            "INSERT INTO checkpoints VALUES (?, ?, ?)",
            (
                (instance_id, before_checkpoint, str(before)),
                (instance_id, after_checkpoint, str(after)),
            ),
        )

    factory = HardenedNautilusForwardSessionProcessFactory(
        _plan_factory(ledger_path, image_digest),
        response_timeout_seconds=90,
    )
    before_delivery, before_preparation = _fixture_payload(before)
    first = asyncio.run(
        factory.start(
            instance_id=instance_id,
            checkpoint_fingerprint=before_checkpoint,
            delivery=before_delivery,
            preparation=before_preparation,
        )
    )
    first_result = asyncio.run(first.execute(before_delivery, before_preparation))
    _kill_process(first)  # crash before durable account settlement

    replay = asyncio.run(
        factory.start(
            instance_id=instance_id,
            checkpoint_fingerprint=before_checkpoint,
            delivery=before_delivery,
            preparation=before_preparation,
        )
    )
    replay_result = asyncio.run(replay.execute(before_delivery, before_preparation))
    assert replay_result.fingerprint == first_result.fingerprint
    _kill_process(replay)

    canonical_event = before_delivery.tape.envelopes[0].canonical_event
    ledger = DurableReplayLedger(ledger_path)
    settled_receipt = ledger.settle_once(
        instance_id=instance_id,
        event_id=canonical_event.event_id,
        event_fingerprint=content_digest(canonical_event),
        result_fingerprint=replay_result.fingerprint,
        next_checkpoint=after_checkpoint,
    )
    assert settled_receipt == replay_result.fingerprint
    _kill_process(replay)  # crash after durable settlement but before Redis ACK

    # A committed-before-ACK redelivery reads the exact stored receipt and ACKs
    # without invoking Nautilus again; the process is already gone.
    committed_before_ack = ledger.receipt(
        instance_id=instance_id, event_id=canonical_event.event_id
    )
    assert committed_before_ack == (replay_result.fingerprint, False)
    assert ledger.acknowledge_once(instance_id=instance_id, event_id=canonical_event.event_id)
    assert not ledger.acknowledge_once(instance_id=instance_id, event_id=canonical_event.event_id)
    assert ledger.receipt(instance_id=instance_id, event_id=canonical_event.event_id) == (
        replay_result.fingerprint,
        True,
    )

    after_delivery, after_preparation = _fixture_payload(after)
    continuation = asyncio.run(
        factory.start(
            instance_id=instance_id,
            checkpoint_fingerprint=after_checkpoint,
            delivery=after_delivery,
            preparation=after_preparation,
        )
    )
    after_result = asyncio.run(continuation.execute(after_delivery, after_preparation))
    _kill_process(continuation)
    repeated = asyncio.run(
        factory.start(
            instance_id=instance_id,
            checkpoint_fingerprint=after_checkpoint,
            delivery=after_delivery,
            preparation=after_preparation,
        )
    )
    repeated_result = asyncio.run(repeated.execute(after_delivery, after_preparation))
    _kill_process(repeated)
    assert repeated_result.fingerprint == after_result.fingerprint
    assert after_delivery.delivery_binding.pre_event_checkpoint_fingerprint == after_checkpoint
