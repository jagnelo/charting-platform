"""Resolve one exact durable forward checkpoint before native process recovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.forward_account import (
    ForwardAccountState,
    ForwardAppliedAccountExecutionEvent,
)
from app.strategy_lab_v2.forward_admission import ForwardLiveAdmissionState
from app.strategy_lab_v2.forward_warmup import ForwardWarmupReceipt


class ForwardNautilusAdmissionStore(Protocol):
    """Owner-scoped persistent admission reads used to reconstruct a runtime."""

    async def load_state_at_checkpoint(
        self,
        *,
        principal: Any,
        instance_id: str,
        checkpoint_fingerprint: str,
    ) -> ForwardLiveAdmissionState | None: ...

    async def load_warmup_receipt(
        self, *, principal: Any, instance_id: str
    ) -> ForwardWarmupReceipt | None: ...


class ForwardNautilusAccountStore(Protocol):
    """Durable account history replayed to the same admission checkpoint."""

    async def load_at_checkpoint(
        self,
        *,
        principal: Any,
        admission_state: ForwardLiveAdmissionState,
    ) -> ForwardAccountState | None: ...


@dataclass(frozen=True, slots=True)
class ResolvedNautilusForwardCheckpoint:
    """Authenticated inputs from which a host may build a process bootstrap."""

    admission_state: ForwardLiveAdmissionState
    warmup_receipt: ForwardWarmupReceipt
    account_state: ForwardAccountState

    def __post_init__(self) -> None:
        if not isinstance(self.admission_state, ForwardLiveAdmissionState):
            raise TypeError("admission_state must use ForwardLiveAdmissionState")
        if not isinstance(self.warmup_receipt, ForwardWarmupReceipt):
            raise TypeError("warmup_receipt must use ForwardWarmupReceipt")
        if not isinstance(self.account_state, ForwardAccountState):
            raise TypeError("account_state must use ForwardAccountState")
        checkpoint = self.admission_state.checkpoint
        instance = checkpoint.instance
        if self.admission_state.warmup_receipt_fingerprint != self.warmup_receipt.fingerprint:
            raise ValueError("recovery admission differs from its durable warm-up receipt")
        if (
            self.warmup_receipt.instance_id != instance.instance_id
            or self.warmup_receipt.warmup_snapshot_fingerprint
            != instance.warmup_snapshot_fingerprint
            or self.warmup_receipt.carry_in_mode is not instance.carry_in_mode
        ):
            raise ValueError("recovery warm-up receipt differs from the checkpoint instance")
        if self.account_state.instance_id != instance.instance_id:
            raise ValueError("recovery account state belongs to another forward instance")

        warmup_event_id = self.warmup_receipt.final_event_id
        expected_live_ids = checkpoint.processed_event_ids - (
            frozenset() if warmup_event_id is None else frozenset({warmup_event_id})
        )
        applied_by_id = {item.event_id: item for item in self.account_state.applied_events}
        if set(applied_by_id) != expected_live_ids:
            raise ValueError(
                "durable account history does not cover the exact processed checkpoint"
            )
        seen_by_id = {item.event_id: item for item in self.admission_state.seen_events}
        if not expected_live_ids.issubset(seen_by_id):
            raise ValueError("processed checkpoint is missing canonical admission evidence")
        for event_id in expected_live_ids:
            seen = seen_by_id[event_id]
            applied = applied_by_id[event_id]
            if (
                not isinstance(applied, ForwardAppliedAccountExecutionEvent)
                or applied.event_fingerprint != seen.event_fingerprint
                or applied.sequence != seen.sequence
                or applied.execution_receipt.instance_id != instance.instance_id
                or applied.execution_receipt.event_fingerprint != seen.event_fingerprint
            ):
                raise ValueError(
                    "durable account event lacks its matching native execution receipt"
                )

        latest = max(
            (seen_by_id[event_id] for event_id in expected_live_ids),
            key=lambda item: (item.sequence, item.event_id),
            default=None,
        )
        expected_cursor = (None, -1) if latest is None else (latest.event_id, latest.sequence)
        if (self.account_state.last_event_id, self.account_state.last_event_sequence) != (
            expected_cursor
        ):
            raise ValueError("durable account cursor differs from the processed checkpoint")

    @property
    def checkpoint_fingerprint(self) -> str:
        return self.admission_state.checkpoint.fingerprint

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class AuthenticatedNautilusForwardCheckpointResolver:
    """Load admission, warm-up, and native account state at one exact cursor."""

    def __init__(
        self,
        admission_store: ForwardNautilusAdmissionStore,
        account_store: ForwardNautilusAccountStore,
        *,
        principal: Any,
    ) -> None:
        if not callable(getattr(admission_store, "load_state_at_checkpoint", None)):
            raise TypeError("admission_store must load exact forward checkpoints")
        if not callable(getattr(admission_store, "load_warmup_receipt", None)):
            raise TypeError("admission_store must load durable warm-up receipts")
        if not callable(getattr(account_store, "load_at_checkpoint", None)):
            raise TypeError("account_store must replay account history at a checkpoint")
        self._admission_store = admission_store
        self._account_store = account_store
        self._principal = principal

    async def resolve(
        self, *, instance_id: str, checkpoint_fingerprint: str
    ) -> ResolvedNautilusForwardCheckpoint:
        """Resolve one checkpoint or fail closed if any durable row is missing."""

        if not isinstance(instance_id, str) or not instance_id.strip():
            raise ValueError("instance_id must not be empty")
        require_sha256_digest(checkpoint_fingerprint, field_name="checkpoint_fingerprint")
        admission = await self._admission_store.load_state_at_checkpoint(
            principal=self._principal,
            instance_id=instance_id,
            checkpoint_fingerprint=checkpoint_fingerprint,
        )
        if not isinstance(admission, ForwardLiveAdmissionState):
            raise ValueError("durable forward admission checkpoint is unavailable")
        if (
            admission.checkpoint.instance.instance_id != instance_id
            or admission.checkpoint.fingerprint != checkpoint_fingerprint
        ):
            raise ValueError("durable forward admission differs from the requested checkpoint")

        receipt = await self._admission_store.load_warmup_receipt(
            principal=self._principal,
            instance_id=instance_id,
        )
        if not isinstance(receipt, ForwardWarmupReceipt):
            raise ValueError("durable forward warm-up receipt is unavailable")
        account = await self._account_store.load_at_checkpoint(
            principal=self._principal,
            admission_state=admission,
        )
        if not isinstance(account, ForwardAccountState):
            raise ValueError("forward account history is not settled at the requested checkpoint")
        return ResolvedNautilusForwardCheckpoint(admission, receipt, account)


__all__ = [
    "AuthenticatedNautilusForwardCheckpointResolver",
    "ForwardNautilusAccountStore",
    "ForwardNautilusAdmissionStore",
    "ResolvedNautilusForwardCheckpoint",
]
