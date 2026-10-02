"""Nautilus plan execution through the bounded sandbox adapter.

This is the last process boundary before a future isolated Nautilus v2 worker.
It does not discover engines, fetch data, or bypass conformance: callers must
provide the immutable :class:`NautilusExecutionPlan` produced by the gate.
Rejected plans never reach ``subprocess``; successful execution evidence keeps
the plan and sandbox fingerprints together for result publication.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import ArtifactManifest, ArtifactRetention
from app.strategy_lab_v2.engine_execution import (
    EngineExecutionDecision,
    NautilusExecutionPlan,
)
from app.strategy_lab_v2.nautilus_native_event_stream import (
    MAX_NAUTILUS_NATIVE_EVENT_STREAM_BYTES,
)
from app.strategy_lab_v2.nautilus_runtime_bundle import (
    NautilusInvocationResultStreamReference,
    NautilusNativeEventStreamArtifactReference,
    NautilusRuntimeInputArtifactReference,
    verify_nautilus_context_stream_artifact_file,
    verify_nautilus_invocation_result_stream_file,
    verify_nautilus_native_event_stream_artifact_file,
    verify_nautilus_runtime_artifact_file,
)
from app.strategy_lab_v2.nautilus_runtime_protocol import (
    NAUTILUS_INVOCATION_RESULT_STREAM_MEDIA_TYPE,
    NAUTILUS_INVOCATION_RESULT_STREAM_SCHEMA,
)
from app.strategy_lab_v2.sandbox import (
    SandboxCommandPlan,
    nautilus_runtime_command,
    sandbox_attempt_id,
    sandbox_context_stream_digest,
    sandbox_context_stream_path,
    sandbox_engine_id,
    sandbox_input_bundle_digest,
    sandbox_input_path,
    sandbox_invocation_result_stream_path,
    sandbox_memory_limit_bytes,
    sandbox_native_event_stream_digest,
    sandbox_native_event_stream_path,
    sandbox_output_path,
    sandbox_runtime_command,
)
from app.strategy_lab_v2.sandbox_execution import (
    SandboxRunResult,
    SandboxRunStatus,
    run_sandbox_command,
)
from strategy_runtime import INVOCATION_RESULT_STREAM_PROTOCOL_VERSION


class NautilusRunStatus(StrEnum):
    REJECTED = "rejected"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    OUTPUT_LIMIT_EXCEEDED = "output_limit_exceeded"
    START_FAILED = "start_failed"


@dataclass(frozen=True, slots=True)
class NautilusRunResult:
    """Content-addressed outcome of one gated Nautilus process attempt."""

    execution_plan_fingerprint: str
    sandbox_plan_fingerprint: str
    status: NautilusRunStatus
    authoritative: bool
    sandbox_result: SandboxRunResult | None = None
    invocation_result_stream: NautilusInvocationResultStreamReference | None = None
    result_failure_digest: str | None = None
    rejection_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_sha256_digest(
            self.execution_plan_fingerprint,
            field_name="execution_plan_fingerprint",
        )
        require_sha256_digest(
            self.sandbox_plan_fingerprint,
            field_name="sandbox_plan_fingerprint",
        )
        if not isinstance(self.status, NautilusRunStatus):
            raise TypeError("status must be a NautilusRunStatus")
        if not isinstance(self.authoritative, bool):
            raise TypeError("authoritative must be a boolean")
        if self.sandbox_result is not None and not isinstance(
            self.sandbox_result, SandboxRunResult
        ):
            raise TypeError("sandbox_result must be a SandboxRunResult")
        if self.invocation_result_stream is not None and not isinstance(
            self.invocation_result_stream, NautilusInvocationResultStreamReference
        ):
            raise TypeError(
                "invocation_result_stream must be a NautilusInvocationResultStreamReference"
            )
        if self.result_failure_digest is not None:
            require_sha256_digest(self.result_failure_digest, field_name="result_failure_digest")
        reasons = tuple(self.rejection_reasons)
        if len(reasons) != len(set(reasons)) or any(
            not isinstance(reason, str) or not reason.strip() for reason in reasons
        ):
            raise ValueError("Nautilus rejection reasons must be unique and non-empty")
        if self.status is NautilusRunStatus.REJECTED:
            if (
                self.sandbox_result is not None
                or self.invocation_result_stream is not None
                or self.result_failure_digest is not None
                or self.authoritative
                or not reasons
            ):
                raise ValueError("rejected Nautilus runs require reasons and no process result")
        else:
            if self.sandbox_result is None or reasons:
                raise ValueError(
                    "executed Nautilus runs require a sandbox result and no rejection reasons"
                )
            if self.authoritative and self.status is not NautilusRunStatus.SUCCEEDED:
                raise ValueError("only successful Nautilus runs can be authoritative")
            process_succeeded = self.sandbox_result.status is SandboxRunStatus.SUCCEEDED
            if process_succeeded and self.status is NautilusRunStatus.FAILED:
                if self.result_failure_digest is None:
                    raise ValueError(
                        "post-process Nautilus failures require a result failure digest"
                    )
            elif self.result_failure_digest is not None:
                raise ValueError("result failure digests require a failed post-process result")
        if self.sandbox_result is not None and (
            self.sandbox_result.plan_fingerprint != self.sandbox_plan_fingerprint
        ):
            raise ValueError("sandbox result does not reference the execution sandbox plan")
        object.__setattr__(self, "rejection_reasons", reasons)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def run_nautilus_plan(
    execution_plan: NautilusExecutionPlan,
    sandbox_plan: SandboxCommandPlan,
    *,
    docker_binary: str = "docker",
    runtime_input_artifact: NautilusRuntimeInputArtifactReference | None = None,
) -> NautilusRunResult:
    """Execute only a ready, Nautilus-bound plan through the sandbox adapter."""

    if not isinstance(execution_plan, NautilusExecutionPlan):
        raise TypeError("execution_plan must be a NautilusExecutionPlan")
    if not isinstance(sandbox_plan, SandboxCommandPlan):
        raise TypeError("sandbox_plan must be a SandboxCommandPlan")
    reasons: list[str] = []
    if execution_plan.decision is not EngineExecutionDecision.READY:
        reasons.append("execution_plan_rejected")
    if execution_plan.engine_id.lower() != "nautilus":
        reasons.append("only_nautilus_engine_is_supported")
    if execution_plan.sandbox_plan_fingerprint != sandbox_plan.fingerprint:
        reasons.append("sandbox_plan_identity_mismatch")
    if runtime_input_artifact is not None and not isinstance(
        runtime_input_artifact, NautilusRuntimeInputArtifactReference
    ):
        raise TypeError("runtime_input_artifact must be a NautilusRuntimeInputArtifactReference")
    result_stream_path = None
    try:
        engine_marker = sandbox_engine_id(sandbox_plan)
        attempt_id = sandbox_attempt_id(sandbox_plan)
        input_digest = sandbox_input_bundle_digest(sandbox_plan)
        context_digest = sandbox_context_stream_digest(sandbox_plan)
        context_path = sandbox_context_stream_path(sandbox_plan)
        native_event_digest = sandbox_native_event_stream_digest(sandbox_plan)
        native_event_path = sandbox_native_event_stream_path(sandbox_plan)
        result_stream_path = sandbox_invocation_result_stream_path(sandbox_plan)
        memory_limit_bytes = sandbox_memory_limit_bytes(sandbox_plan)
    except (TypeError, ValueError):
        reasons.append("sandbox_plan_not_hardened")
    else:
        if engine_marker != "nautilus":
            reasons.append("nautilus_sandbox_engine_marker_required")
        if attempt_id != execution_plan.attempt_id:
            reasons.append("nautilus_sandbox_attempt_mismatch")
        if runtime_input_artifact is not None:
            if runtime_input_artifact.attempt_id != execution_plan.attempt_id:
                reasons.append("nautilus_input_artifact_attempt_mismatch")
            if runtime_input_artifact.input_bundle_digest != input_digest:
                reasons.append("nautilus_input_artifact_digest_mismatch")
            try:
                verify_nautilus_runtime_artifact_file(
                    runtime_input_artifact,
                    sandbox_input_path(sandbox_plan),
                    max_input_bytes=max(1, memory_limit_bytes // 8),
                )
            except (OSError, TypeError, ValueError):
                reasons.append("nautilus_input_artifact_integrity_failed")
            context_reference = runtime_input_artifact.context_stream
            if context_reference is None:
                if (
                    context_digest is not None
                    or context_path is not None
                    or native_event_digest is not None
                    or native_event_path is not None
                    or result_stream_path is not None
                ):
                    reasons.append("nautilus_stream_artifact_unbound")
            else:
                if context_digest != context_reference.artifact.content_digest:
                    reasons.append("nautilus_context_stream_digest_mismatch")
                if context_path is None:
                    reasons.append("nautilus_context_stream_mount_required")
                else:
                    try:
                        verify_nautilus_context_stream_artifact_file(
                            context_reference,
                            context_path,
                            max_input_bytes=max(1, memory_limit_bytes // 8),
                        )
                    except (OSError, TypeError, ValueError):
                        reasons.append("nautilus_context_stream_integrity_failed")
                if result_stream_path is None:
                    reasons.append("nautilus_invocation_result_stream_mount_required")
            native_event_reference = runtime_input_artifact.native_event_stream
            if native_event_reference is None:
                if native_event_digest is not None or native_event_path is not None:
                    reasons.append("nautilus_native_event_stream_unbound")
            else:
                if not isinstance(
                    native_event_reference, NautilusNativeEventStreamArtifactReference
                ):
                    reasons.append("nautilus_native_event_stream_reference_invalid")
                if native_event_digest != native_event_reference.artifact.content_digest:
                    reasons.append("nautilus_native_event_stream_digest_mismatch")
                if native_event_path is None:
                    reasons.append("nautilus_native_event_stream_mount_required")
                else:
                    try:
                        verify_nautilus_native_event_stream_artifact_file(
                            native_event_reference,
                            native_event_path,
                            max_input_bytes=MAX_NAUTILUS_NATIVE_EVENT_STREAM_BYTES,
                        )
                    except (OSError, TypeError, ValueError):
                        reasons.append("nautilus_native_event_stream_integrity_failed")
        elif context_digest is not None or context_path is not None:
            reasons.append("nautilus_context_stream_reference_required")
        elif native_event_digest is not None or native_event_path is not None:
            reasons.append("nautilus_native_event_stream_reference_required")
        try:
            expected_command = nautilus_runtime_command(
                expected_version=execution_plan.engine_version,
                snapshot_fingerprint=execution_plan.data_snapshot_fingerprint,
                max_input_bytes=max(1, memory_limit_bytes // 8),
                context_stream_digest=(
                    context_digest
                    if runtime_input_artifact is not None
                    and runtime_input_artifact.context_stream is not None
                    else None
                ),
                native_event_stream_digest=(
                    native_event_digest
                    if runtime_input_artifact is not None
                    and runtime_input_artifact.native_event_stream is not None
                    else None
                ),
                max_result_bytes=(
                    sandbox_plan.output_limit_bytes if context_digest is not None else None
                ),
            )
            if sandbox_runtime_command(sandbox_plan) != expected_command:
                reasons.append("nautilus_runtime_command_required")
        except (TypeError, ValueError):
            reasons.append("nautilus_runtime_command_required")
    if reasons:
        return NautilusRunResult(
            execution_plan.fingerprint,
            sandbox_plan.fingerprint,
            NautilusRunStatus.REJECTED,
            False,
            rejection_reasons=tuple(sorted(set(reasons))),
        )

    sandbox_result = run_sandbox_command(sandbox_plan, docker_binary=docker_binary)
    status = _status(sandbox_result.status)
    invocation_result_stream = None
    result_failure_digest = None
    if status is NautilusRunStatus.SUCCEEDED and runtime_input_artifact is not None:
        context_reference = runtime_input_artifact.context_stream
        if context_reference is not None:
            try:
                if result_stream_path is None:
                    raise ValueError("invocation result stream mount is missing")
                invocation_result_stream = _verified_result_stream_reference(
                    sandbox_plan,
                    sandbox_result,
                    result_stream_path,
                    expected_result_count=context_reference.context_count,
                )
                if not invocation_result_stream.all_succeeded:
                    status = NautilusRunStatus.FAILED
                    result_failure_digest = content_digest("strategy invocation result failure")
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                status = NautilusRunStatus.FAILED
                result_failure_digest = content_digest(
                    "Nautilus result stream verification failure"
                )
    return NautilusRunResult(
        execution_plan.fingerprint,
        sandbox_plan.fingerprint,
        status,
        execution_plan.authoritative and status is NautilusRunStatus.SUCCEEDED,
        sandbox_result,
        invocation_result_stream,
        result_failure_digest,
    )


def _verified_result_stream_reference(
    sandbox_plan: SandboxCommandPlan,
    sandbox_result: SandboxRunResult,
    stream_path: os.PathLike[str] | str,
    *,
    expected_result_count: int,
) -> NautilusInvocationResultStreamReference:
    """Authenticate the main receipt and its mounted result stream."""

    result_path = sandbox_output_path(sandbox_plan)
    if sandbox_result.result_digest is None or sandbox_result.result_bytes is None:
        raise ValueError("Nautilus sandbox is missing its main result file")
    if sandbox_result.result_bytes > sandbox_plan.output_limit_bytes:
        raise ValueError("Nautilus main result exceeds the sandbox output bound")
    descriptor = os.open(
        result_path,
        os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != sandbox_result.result_bytes:
            raise ValueError("Nautilus main result file identity differs")
        raw = bytearray()
        digest = hashlib.sha256()
        while True:
            remaining = sandbox_plan.output_limit_bytes + 1 - len(raw)
            if remaining <= 0:
                raise ValueError("Nautilus main result exceeds the sandbox output bound")
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            raw.extend(chunk)
            digest.update(chunk)
            if len(raw) > sandbox_plan.output_limit_bytes:
                raise ValueError("Nautilus main result exceeds the sandbox output bound")
    finally:
        os.close(descriptor)
    if f"sha256:{digest.hexdigest()}" != sandbox_result.result_digest:
        raise ValueError("Nautilus main result changed after sandbox capture")
    result = json.loads(
        raw,
        object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
    )
    if not isinstance(result, Mapping):
        raise ValueError("Nautilus main result must be a JSON object")
    receipt = result.get("strategy_invocation_result_stream")
    receipt_fields = {
        "protocol_version",
        "content_digest",
        "byte_length",
        "result_count",
        "all_succeeded",
    }
    if not isinstance(receipt, Mapping) or set(receipt) != receipt_fields:
        raise ValueError("Nautilus invocation result stream receipt fields are invalid")
    if receipt["protocol_version"] != INVOCATION_RESULT_STREAM_PROTOCOL_VERSION:
        raise ValueError("Nautilus invocation result stream protocol is unsupported")
    digest_value = receipt["content_digest"]
    require_sha256_digest(digest_value, field_name="invocation result stream digest")
    byte_length = receipt["byte_length"]
    result_count = receipt["result_count"]
    all_succeeded = receipt["all_succeeded"]
    if not isinstance(byte_length, int) or isinstance(byte_length, bool) or byte_length <= 0:
        raise ValueError("Nautilus invocation result stream byte length must be positive")
    if (
        not isinstance(result_count, int)
        or isinstance(result_count, bool)
        or result_count != expected_result_count
    ):
        raise ValueError("Nautilus invocation result stream count differs from its input")
    if not isinstance(all_succeeded, bool):
        raise ValueError("Nautilus invocation result stream success flag is invalid")
    manifest = ArtifactManifest(
        content_digest=digest_value,
        byte_length=byte_length,
        media_type=NAUTILUS_INVOCATION_RESULT_STREAM_MEDIA_TYPE,
        schema_version=NAUTILUS_INVOCATION_RESULT_STREAM_SCHEMA,
        storage_key=digest_value,
        retention_class=ArtifactRetention.PINNED_RESULT,
    )
    reference = NautilusInvocationResultStreamReference(
        manifest,
        result_count,
        all_succeeded,
    )
    verify_nautilus_invocation_result_stream_file(
        reference,
        stream_path,
        max_result_bytes=sandbox_plan.output_limit_bytes,
    )
    return reference


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Nautilus runtime result contains duplicate object fields")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError("Nautilus runtime result contains a non-finite JSON number")


def _status(status: SandboxRunStatus) -> NautilusRunStatus:
    return NautilusRunStatus(status.value)
