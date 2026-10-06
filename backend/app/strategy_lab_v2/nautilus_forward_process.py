"""Hardened Docker process factory for persistent Nautilus forward sessions."""

from __future__ import annotations

import asyncio
import os
import select
import signal
import stat
import subprocess
import threading
import time
from collections.abc import Callable, Mapping
from typing import BinaryIO, Protocol

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.forward_context import (
    ForwardPortfolioContextPreparation,
    ForwardStrategyContextPreparation,
)
from app.strategy_lab_v2.nautilus_forward_bootstrap import (
    MAX_NAUTILUS_FORWARD_BOOTSTRAP_BYTES,
    NautilusForwardRuntimeBootstrap,
)
from app.strategy_lab_v2.nautilus_forward_delivery import NautilusForwardDeliveryInput
from app.strategy_lab_v2.nautilus_forward_session import NautilusForwardExecutionResult
from app.strategy_lab_v2.nautilus_forward_wire import NautilusForwardJsonWireCodec
from app.strategy_lab_v2.nautilus_runtime_ipc import (
    MAX_NAUTILUS_RUNTIME_IPC_FRAME_BYTES,
    NautilusRuntimeIpcClient,
    NautilusRuntimeIpcError,
    NautilusRuntimeIpcOperation,
)
from app.strategy_lab_v2.sandbox import (
    NAUTILUS_RUNTIME_CLI_MODULE,
    SandboxCommandPlan,
    sandbox_forward_bootstrap_digest,
    sandbox_forward_bootstrap_path,
    sandbox_runtime_command,
    validate_sandbox_command_plan,
)
from app.strategy_lab_v2.sandbox_execution import _prepare_writable_output_mounts

ForwardPreparation = ForwardStrategyContextPreparation | ForwardPortfolioContextPreparation


class _FileDescriptorReader(Protocol):
    def fileno(self) -> int: ...


class NautilusForwardRuntimeWireCodec(Protocol):
    """Explicit DTO codec between host-owned contracts and bounded IPC JSON."""

    def open_payload(
        self, *, instance_id: str, checkpoint_fingerprint: str
    ) -> Mapping[str, object]: ...

    def decode_open_payload(self, payload: Mapping[str, object]) -> tuple[str, str]: ...

    def open_result_payload(
        self,
        *,
        instance_id: str,
        runtime_session_fingerprint: str,
        base_checkpoint_fingerprint: str,
    ) -> Mapping[str, object]: ...

    def validate_open_result(
        self,
        payload: Mapping[str, object],
        *,
        instance_id: str,
        expected_base_checkpoint_fingerprint: str,
    ) -> str: ...

    def execute_payload(
        self,
        delivery: NautilusForwardDeliveryInput,
        preparation: ForwardPreparation,
    ) -> Mapping[str, object]: ...

    def decode_execute_payload(
        self, payload: Mapping[str, object]
    ) -> tuple[NautilusForwardDeliveryInput, ForwardPreparation]: ...

    def execution_result(self, payload: Mapping[str, object]) -> NautilusForwardExecutionResult: ...

    def execution_result_payload(
        self, result: NautilusForwardExecutionResult
    ) -> Mapping[str, object]: ...

    def restore_payload(
        self,
        *,
        instance_id: str,
        checkpoint_fingerprint: str,
    ) -> Mapping[str, object]: ...

    def decode_restore_payload(self, payload: Mapping[str, object]) -> tuple[str, str]: ...

    def restore_result_payload(
        self, *, instance_id: str, checkpoint_fingerprint: str
    ) -> Mapping[str, object]: ...

    def validate_restore_result(
        self,
        payload: Mapping[str, object],
        *,
        instance_id: str,
        checkpoint_fingerprint: str,
    ) -> None: ...

    def close_payload(self, *, instance_id: str) -> Mapping[str, object]: ...

    def decode_close_payload(self, payload: Mapping[str, object]) -> str: ...

    def close_result_payload(self, *, instance_id: str) -> Mapping[str, object]: ...

    def validate_close_result(self, payload: Mapping[str, object], *, instance_id: str) -> None: ...


class _TimedPipeLineReader:
    """Read one stdout line with select-based deadlines and a bounded buffer."""

    def __init__(self, stream: _FileDescriptorReader, *, timeout_seconds: float) -> None:
        if not isinstance(timeout_seconds, int | float) or isinstance(timeout_seconds, bool):
            raise TypeError("timeout_seconds must be numeric")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._descriptor = stream.fileno()
        os.set_blocking(self._descriptor, False)
        self._timeout_seconds = float(timeout_seconds)
        self._buffer = bytearray()

    def readline(self, size: int = -1) -> bytes:
        if not isinstance(size, int) or isinstance(size, bool) or size < 1:
            raise ValueError("readline size must be positive")
        deadline = time.monotonic() + self._timeout_seconds
        while True:
            newline = self._buffer.find(b"\n")
            if newline >= 0:
                end = newline + 1
                line = bytes(self._buffer[:end])
                del self._buffer[:end]
                return line
            if len(self._buffer) >= size:
                line = bytes(self._buffer[:size])
                del self._buffer[:size]
                return line
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("isolated Nautilus runtime response timed out")
            ready, _, _ = select.select([self._descriptor], [], [], remaining)
            if not ready:
                raise TimeoutError("isolated Nautilus runtime response timed out")
            chunk = os.read(self._descriptor, min(65_536, size - len(self._buffer)))
            if not chunk:
                line = bytes(self._buffer)
                self._buffer.clear()
                return line
            self._buffer.extend(chunk)


class NautilusRuntimeIpcSubprocess:
    """One persistent isolated Docker process with framed stdin/stdout IPC."""

    def __init__(
        self,
        process: subprocess.Popen[bytes],
        *,
        instance_id: str,
        response_timeout_seconds: float,
        stderr_limit_bytes: int,
    ) -> None:
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise RuntimeError("persistent Docker process pipes were not created")
        self.instance_id = instance_id
        self._process = process
        self._reader = _TimedPipeLineReader(
            process.stdout,
            timeout_seconds=response_timeout_seconds,
        )
        self._client = NautilusRuntimeIpcClient(
            self._reader,
            process.stdin,
            max_frame_bytes=MAX_NAUTILUS_RUNTIME_IPC_FRAME_BYTES,
        )
        self._stderr_limit_bytes = stderr_limit_bytes
        self._stderr_count = 0
        self._stderr_overflow = threading.Event()
        self._closed = False
        self._close_response: Mapping[str, object] | None = None
        self._lock = threading.Lock()
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr,
            args=(process.stderr,),
            daemon=True,
            name=f"nautilus-forward-stderr-{process.pid}",
        )
        self._stderr_thread.start()

    def request(
        self,
        operation: NautilusRuntimeIpcOperation,
        payload: Mapping[str, object],
        *,
        request_id: str,
    ) -> Mapping[str, object]:
        with self._lock:
            if self._closed:
                raise RuntimeError("isolated Nautilus process is closed")
            if self._stderr_overflow.is_set():
                self._terminate()
                raise RuntimeError("isolated Nautilus stderr exceeded its output limit")
            if self._process.poll() is not None:
                raise RuntimeError("isolated Nautilus process exited before the request")
            try:
                return self._client.request(operation, payload, request_id=request_id)
            except NautilusRuntimeIpcError:
                raise
            except Exception:
                self._terminate()
                raise

    def close(
        self,
        *,
        payload: Mapping[str, object],
        timeout_seconds: float = 5.0,
    ) -> Mapping[str, object] | None:
        with self._lock:
            if self._closed:
                return self._close_response
            response: Mapping[str, object] | None = None
            try:
                if self._process.poll() is None:
                    response = self._client.request(
                        NautilusRuntimeIpcOperation.CLOSE,
                        payload,
                        request_id=content_digest(
                            {"operation": "close", "instance_id": self.instance_id}
                        ),
                    )
                    self._process.wait(timeout=timeout_seconds)
            except Exception:
                self._terminate()
                raise
            finally:
                self._closed = True
                self._close_response = response
                if self._process.poll() is None:
                    self._terminate()
                self._close_pipes()
            return response

    def _drain_stderr(self, stream: BinaryIO) -> None:
        while chunk := stream.read(65_536):
            self._stderr_count += len(chunk)
            if self._stderr_count > self._stderr_limit_bytes:
                self._stderr_overflow.set()
                self._terminate()
                return

    def _terminate(self) -> None:
        if self._process.poll() is not None:
            return
        try:
            os.killpg(self._process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            self._process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self._process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self._process.wait()

    def _close_pipes(self) -> None:
        for stream in (self._process.stdin, self._process.stdout, self._process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        self._stderr_thread.join(timeout=1.0)


class NautilusForwardSessionProcess:
    """Typed host adapter implementing the forward-session process contract."""

    def __init__(
        self,
        transport: NautilusRuntimeIpcSubprocess,
        codec: NautilusForwardRuntimeWireCodec,
        *,
        base_checkpoint_fingerprint: str,
    ) -> None:
        self.instance_id = transport.instance_id
        self.base_checkpoint_fingerprint = base_checkpoint_fingerprint
        self._transport = transport
        self._codec = codec

    async def execute(
        self,
        delivery: NautilusForwardDeliveryInput,
        preparation: ForwardPreparation,
    ) -> NautilusForwardExecutionResult:
        payload = self._codec.execute_payload(delivery, preparation)
        request_id = content_digest(
            {
                "operation": "execute",
                "instance_id": self.instance_id,
                "delivery": delivery.fingerprint,
                "preparation": preparation.fingerprint,
            }
        )
        response = await asyncio.to_thread(
            self._transport.request,
            NautilusRuntimeIpcOperation.EXECUTE,
            payload,
            request_id=request_id,
        )
        result = self._codec.execution_result(response)
        if not isinstance(result, NautilusForwardExecutionResult):
            raise TypeError("forward runtime codec returned an invalid native result")
        return result

    async def restore(self, *, instance_id: str, checkpoint_fingerprint: str) -> None:
        if instance_id != self.instance_id:
            raise ValueError("restore instance differs from the process instance")
        require_sha256_digest(checkpoint_fingerprint, field_name="checkpoint_fingerprint")
        payload = self._codec.restore_payload(
            instance_id=instance_id,
            checkpoint_fingerprint=checkpoint_fingerprint,
        )
        request_id = content_digest(
            {
                "operation": "restore",
                "instance_id": instance_id,
                "checkpoint": checkpoint_fingerprint,
            }
        )
        response = await asyncio.to_thread(
            self._transport.request,
            NautilusRuntimeIpcOperation.RESTORE,
            payload,
            request_id=request_id,
        )
        self._codec.validate_restore_result(
            response,
            instance_id=instance_id,
            checkpoint_fingerprint=checkpoint_fingerprint,
        )

    async def close(self) -> None:
        response = await asyncio.to_thread(
            self._transport.close,
            payload=self._codec.close_payload(instance_id=self.instance_id),
        )
        if response is not None:
            self._codec.validate_close_result(response, instance_id=self.instance_id)


class HardenedNautilusForwardSessionProcessFactory:
    """Launch one hardened, exact-image forward runtime for each instance."""

    def __init__(
        self,
        plan_factory: Callable[..., SandboxCommandPlan],
        codec: NautilusForwardRuntimeWireCodec | None = None,
        *,
        docker_binary: str = "docker",
        response_timeout_seconds: float = 30.0,
    ) -> None:
        if not callable(plan_factory):
            raise TypeError("plan_factory must be callable")
        if not isinstance(docker_binary, str) or not docker_binary.strip():
            raise ValueError("docker_binary must not be empty")
        if any(character in docker_binary for character in "\x00\r\n"):
            raise ValueError("docker_binary must not contain control characters")
        if response_timeout_seconds <= 0:
            raise ValueError("response_timeout_seconds must be positive")
        self._plan_factory = plan_factory
        self._codec = NautilusForwardJsonWireCodec() if codec is None else codec
        self._docker_binary = docker_binary
        self._response_timeout_seconds = response_timeout_seconds

    async def start(
        self,
        *,
        instance_id: str,
        checkpoint_fingerprint: str,
        delivery: NautilusForwardDeliveryInput | None = None,
        preparation: ForwardPreparation | None = None,
    ) -> NautilusForwardSessionProcess:
        if not isinstance(instance_id, str) or not instance_id.strip():
            raise ValueError("instance_id must not be empty")
        require_sha256_digest(checkpoint_fingerprint, field_name="checkpoint_fingerprint")
        _validate_forward_launch_context(
            instance_id,
            checkpoint_fingerprint,
            delivery=delivery,
            preparation=preparation,
        )
        return await asyncio.to_thread(
            self._start_sync,
            instance_id,
            checkpoint_fingerprint,
            delivery,
            preparation,
        )

    def _start_sync(
        self,
        instance_id: str,
        checkpoint_fingerprint: str,
        delivery: NautilusForwardDeliveryInput | None,
        preparation: ForwardPreparation | None,
    ) -> NautilusForwardSessionProcess:
        if delivery is None:
            plan = self._plan_factory(instance_id, checkpoint_fingerprint)
        else:
            assert preparation is not None
            plan = self._plan_factory(
                instance_id,
                checkpoint_fingerprint,
                delivery,
                preparation,
            )
        _validate_forward_checkpoint_plan(plan, instance_id, checkpoint_fingerprint)
        argv = _forward_session_argv(plan, instance_id, self._docker_binary)
        _prepare_writable_output_mounts(
            plan,
            require_private_parent=os.path.basename(self._docker_binary) == "docker",
            allow_existing_sources=os.path.basename(self._docker_binary) != "docker",
        )
        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": "/nonexistent",
            "LANG": "C",
            "LC_ALL": "C",
        }
        try:
            process = subprocess.Popen(
                argv,
                shell=False,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
                start_new_session=True,
                bufsize=0,
            )
        except OSError as error:
            raise RuntimeError("hardened Nautilus forward process could not start") from error
        transport = NautilusRuntimeIpcSubprocess(
            process,
            instance_id=instance_id,
            response_timeout_seconds=self._response_timeout_seconds,
            stderr_limit_bytes=plan.output_limit_bytes,
        )
        try:
            open_payload = self._codec.open_payload(
                instance_id=instance_id,
                checkpoint_fingerprint=checkpoint_fingerprint,
            )
            open_response = transport.request(
                NautilusRuntimeIpcOperation.OPEN,
                open_payload,
                request_id=content_digest(
                    {
                        "operation": "open",
                        "instance_id": instance_id,
                        "checkpoint_fingerprint": checkpoint_fingerprint,
                    }
                ),
            )
            self._codec.validate_open_result(
                open_response,
                instance_id=instance_id,
                expected_base_checkpoint_fingerprint=checkpoint_fingerprint,
            )
        except Exception:
            try:
                transport._terminate()
            finally:
                transport._close_pipes()
            raise
        return NautilusForwardSessionProcess(
            transport,
            self._codec,
            base_checkpoint_fingerprint=checkpoint_fingerprint,
        )


def _validate_forward_launch_context(
    instance_id: str,
    checkpoint_fingerprint: str,
    *,
    delivery: NautilusForwardDeliveryInput | None,
    preparation: ForwardPreparation | None,
) -> None:
    """Reject partial or rebound delivery context before invoking a plan builder."""

    if (delivery is None) != (preparation is None):
        raise ValueError("forward process launch requires both delivery and preparation")
    if delivery is None:
        return
    if not isinstance(delivery, NautilusForwardDeliveryInput):
        raise TypeError("delivery must use NautilusForwardDeliveryInput")
    if not isinstance(
        preparation,
        ForwardStrategyContextPreparation | ForwardPortfolioContextPreparation,
    ):
        raise TypeError("preparation must use an authenticated forward context")
    binding = delivery.delivery_binding
    if binding.instance_id != instance_id:
        raise ValueError("forward process delivery belongs to another instance")
    if binding.pre_event_checkpoint_fingerprint != checkpoint_fingerprint:
        raise ValueError("forward process delivery differs from its requested checkpoint")
    expected = {
        "instance_id": binding.instance_id,
        "payload_fingerprint": delivery.verified_market_payload.fingerprint,
        "delivery_binding_fingerprint": binding.fingerprint,
        "dispatch_fingerprint": binding.dispatch_record_fingerprint,
        "pre_event_checkpoint_fingerprint": binding.pre_event_checkpoint_fingerprint,
        "warmup_receipt_fingerprint": binding.warmup_receipt_fingerprint,
    }
    for name, value in expected.items():
        if getattr(preparation, name) != value:
            raise ValueError(f"forward process context {name} differs from its delivery")


def _validate_forward_checkpoint_plan(
    plan: SandboxCommandPlan,
    instance_id: str,
    checkpoint_fingerprint: str,
) -> None:
    """Require host-resolved launch inputs to match the requested durable cursor."""

    validate_sandbox_command_plan(plan)
    bootstrap_path = sandbox_forward_bootstrap_path(plan)
    bootstrap_fingerprint = sandbox_forward_bootstrap_digest(plan)
    if bootstrap_path is None or bootstrap_fingerprint is None:
        raise ValueError("forward process plan must bind its durable bootstrap artifact")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(bootstrap_path, flags)
    except OSError as error:
        raise ValueError("forward process bootstrap artifact could not be read") from error
    with os.fdopen(descriptor, "rb") as source:
        metadata = os.fstat(source.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("forward process bootstrap artifact must be a regular file")
        encoded = source.read(MAX_NAUTILUS_FORWARD_BOOTSTRAP_BYTES + 1)
    if not encoded or len(encoded) > MAX_NAUTILUS_FORWARD_BOOTSTRAP_BYTES:
        raise ValueError("forward process bootstrap artifact is empty or exceeds its byte limit")
    bootstrap = NautilusForwardRuntimeBootstrap.from_json_bytes(
        encoded,
        expected_fingerprint=bootstrap_fingerprint,
    )
    if bootstrap.instance_id != instance_id:
        raise ValueError("forward process bootstrap belongs to another instance")
    if bootstrap.processed_checkpoint_fingerprint != checkpoint_fingerprint:
        raise ValueError("forward process bootstrap differs from the requested durable checkpoint")


def _forward_session_argv(
    plan: SandboxCommandPlan,
    instance_id: str,
    docker_binary: str,
) -> tuple[str, ...]:
    validate_sandbox_command_plan(plan)
    command = sandbox_runtime_command(plan)
    if command[:3] != ("python", "-m", NAUTILUS_RUNTIME_CLI_MODULE):
        raise ValueError("forward process plan must use the fixed Nautilus runtime CLI")
    if "--serve-forward" not in command:
        raise ValueError("forward process plan must select the persistent runtime mode")
    instance_indexes = [index for index, value in enumerate(command) if value == "--instance-id"]
    if len(instance_indexes) != 1 or instance_indexes[0] + 1 >= len(command):
        raise ValueError("forward process plan must bind exactly one instance id")
    if command[instance_indexes[0] + 1] != instance_id:
        raise ValueError("forward process plan instance id differs from its process factory")
    image_index = len(plan.argv) - len(command) - 1
    docker_argv = list(plan.argv)
    docker_argv[0] = docker_binary
    docker_argv.insert(3, "--interactive")
    if (
        image_index < 0
        or image_index + 2 >= len(docker_argv)
        or docker_argv[image_index + 2] != "python"
    ):
        raise ValueError("forward process plan does not contain its fixed runtime command")
    return tuple(docker_argv)


__all__ = [
    "NautilusForwardRuntimeWireCodec",
    "NautilusForwardJsonWireCodec",
    "NautilusForwardSessionProcess",
    "HardenedNautilusForwardSessionProcessFactory",
    "NautilusRuntimeIpcSubprocess",
]
