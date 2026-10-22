"""Fail-closed isolated-side forward IPC handler around one native session."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Protocol

from app.strategy_lab_v2.canonical import require_sha256_digest
from app.strategy_lab_v2.nautilus_forward_result import NautilusForwardExecutionResult

if TYPE_CHECKING:
    from app.strategy_lab_v2.forward_context import (
        ForwardPortfolioContextPreparation,
        ForwardStrategyContextPreparation,
    )
    from app.strategy_lab_v2.nautilus_forward_delivery import NautilusForwardDeliveryInput

    ForwardPreparation = ForwardStrategyContextPreparation | ForwardPortfolioContextPreparation


class NautilusNativeForwardSession(Protocol):
    """One exact-plan BacktestEngine session owned by the isolated process."""

    instance_id: str
    runtime_session_fingerprint: str

    @property
    def base_checkpoint_fingerprint(self) -> str: ...

    def execute(
        self,
        delivery: NautilusForwardDeliveryInput,
        preparation: ForwardPreparation,
    ) -> NautilusForwardExecutionResult: ...

    def restore(self, *, checkpoint_fingerprint: str) -> str: ...

    def close(self) -> None: ...


NativeForwardSessionFactory = Callable[[str], NautilusNativeForwardSession]


class NautilusForwardRuntimeWireCodec(Protocol):
    """DTO operations needed inside the isolated process, independent of Docker host code."""

    def decode_open_payload(self, payload: Mapping[str, object]) -> tuple[str, str]: ...

    def open_result_payload(
        self,
        *,
        instance_id: str,
        runtime_session_fingerprint: str,
        base_checkpoint_fingerprint: str,
    ) -> Mapping[str, object]: ...

    def decode_execute_payload(
        self, payload: Mapping[str, object]
    ) -> tuple[
        NautilusForwardDeliveryInput,
        ForwardPreparation,
    ]: ...

    def execution_result_payload(
        self, result: NautilusForwardExecutionResult
    ) -> Mapping[str, object]: ...

    def decode_restore_payload(self, payload: Mapping[str, object]) -> tuple[str, str]: ...

    def restore_result_payload(
        self, *, instance_id: str, checkpoint_fingerprint: str
    ) -> Mapping[str, object]: ...

    def decode_close_payload(self, payload: Mapping[str, object]) -> str: ...

    def close_result_payload(self, *, instance_id: str) -> Mapping[str, object]: ...


class NautilusForwardRuntimeOperationHandler:
    """Validate IPC identities and delegate to exactly one native session.

    The supplied session factory is the only engine integration seam. The
    handler never synthesizes account state or accepts an execution result that
    is not bound to its current instance, event, preparation, checkpoint, and
    native-session fingerprint.
    """

    def __init__(
        self,
        *,
        instance_id: str,
        session_factory: NativeForwardSessionFactory,
        codec: NautilusForwardRuntimeWireCodec,
    ) -> None:
        if not isinstance(instance_id, str) or not instance_id.strip():
            raise ValueError("instance_id must not be empty")
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._instance_id = instance_id
        self._session_factory = session_factory
        self._codec = codec
        self._session: NautilusNativeForwardSession | None = None
        self._opened = False
        self._closed = False

    def open(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        if self._opened or self._closed:
            raise ValueError("forward runtime lifecycle cannot be reopened")
        requested_instance_id, requested_checkpoint = self._codec.decode_open_payload(payload)
        if requested_instance_id != self._instance_id:
            raise ValueError("forward runtime open request names another instance")
        require_sha256_digest(requested_checkpoint, field_name="requested_checkpoint")
        session = self._session_factory(self._instance_id)
        try:
            if session.instance_id != self._instance_id:
                raise ValueError("native forward session belongs to another instance")
            if session.base_checkpoint_fingerprint != requested_checkpoint:
                raise ValueError("native forward session bootstrapped another durable checkpoint")
            require_sha256_digest(
                session.runtime_session_fingerprint,
                field_name="runtime_session_fingerprint",
            )
            response = self._codec.open_result_payload(
                instance_id=self._instance_id,
                runtime_session_fingerprint=session.runtime_session_fingerprint,
                base_checkpoint_fingerprint=session.base_checkpoint_fingerprint,
            )
        except BaseException:
            try:
                session.close()
            except Exception:
                pass
            raise
        self._session = session
        self._opened = True
        return response

    def execute(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        session = self._require_open()
        delivery, preparation = self._codec.decode_execute_payload(payload)
        binding = delivery.delivery_binding
        if binding.instance_id != self._instance_id:
            raise ValueError("forward delivery belongs to another runtime instance")
        if (
            preparation.instance_id != self._instance_id
            or preparation.delivery_binding_fingerprint != binding.fingerprint
        ):
            raise ValueError("forward preparation is not bound to this instance and delivery")
        result = session.execute(delivery, preparation)
        if not isinstance(result, NautilusForwardExecutionResult):
            raise TypeError("native forward session returned an invalid execution result")
        if (
            result.delivery_binding_fingerprint != binding.fingerprint
            or result.context_preparation_fingerprint != preparation.fingerprint
            or result.pre_event_checkpoint_fingerprint != binding.pre_event_checkpoint_fingerprint
            or result.runtime_session_fingerprint != session.runtime_session_fingerprint
            or result.account_event_binding.canonical_event
            != delivery.tape.envelopes[0].canonical_event
            or result.account_event_binding.account_event.instance_id != self._instance_id
        ):
            raise ValueError("native forward result differs from its authenticated execution input")
        return self._codec.execution_result_payload(result)

    def restore(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        session = self._require_open()
        instance_id, checkpoint_fingerprint = self._codec.decode_restore_payload(payload)
        if instance_id != self._instance_id:
            raise ValueError("forward restore request names another instance")
        restored_checkpoint = session.restore(checkpoint_fingerprint=checkpoint_fingerprint)
        require_sha256_digest(restored_checkpoint, field_name="restored_checkpoint_fingerprint")
        if restored_checkpoint != checkpoint_fingerprint:
            raise ValueError("native session restored a different checkpoint")
        return self._codec.restore_result_payload(
            instance_id=self._instance_id,
            checkpoint_fingerprint=restored_checkpoint,
        )

    def close(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        instance_id = (
            self._instance_id if not payload else self._codec.decode_close_payload(payload)
        )
        if instance_id != self._instance_id:
            raise ValueError("forward close request names another instance")
        session, self._session = self._session, None
        self._closed = True
        if session is not None:
            session.close()
        return self._codec.close_result_payload(instance_id=self._instance_id)

    def _require_open(self) -> NautilusNativeForwardSession:
        if self._session is None:
            raise ValueError("forward runtime session is not open")
        return self._session


__all__ = [
    "NautilusNativeForwardSession",
    "NautilusForwardRuntimeOperationHandler",
]
