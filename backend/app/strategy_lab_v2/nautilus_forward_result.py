"""Small immutable result contract shared by host and isolated Nautilus runtime."""

from __future__ import annotations

from dataclasses import dataclass

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.forward_account import ForwardAccountEventBinding


@dataclass(frozen=True, slots=True)
class NautilusForwardExecutionResult:
    """Native effects tied to the exact accepted delivery and SDK context."""

    delivery_binding_fingerprint: str
    context_preparation_fingerprint: str
    pre_event_checkpoint_fingerprint: str
    runtime_session_fingerprint: str
    native_output_fingerprint: str
    account_event_binding: ForwardAccountEventBinding

    def __post_init__(self) -> None:
        for name in (
            "delivery_binding_fingerprint",
            "context_preparation_fingerprint",
            "pre_event_checkpoint_fingerprint",
            "runtime_session_fingerprint",
            "native_output_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        if not isinstance(self.account_event_binding, ForwardAccountEventBinding):
            raise TypeError("account_event_binding must use ForwardAccountEventBinding")
        if self.native_output_fingerprint != self.account_event_binding.fingerprint:
            raise ValueError("native output fingerprint differs from its typed account effects")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


__all__ = ["NautilusForwardExecutionResult"]
