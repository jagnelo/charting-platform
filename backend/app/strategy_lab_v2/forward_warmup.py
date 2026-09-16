"""Immutable forward warm-up receipts and one-time live handoff decisions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import CarryInMode, ForwardInstance, ForwardState


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ForwardWarmupReceipt:
    """Evidence that immutable historical warm-up completed exactly once."""

    instance_id: str
    warmup_snapshot_fingerprint: str
    carry_in_mode: CarryInMode
    warmup_result_fingerprint: str
    completed_at: datetime
    final_event_id: str | None = None
    final_event_sequence: int = 0

    def __post_init__(self) -> None:
        _nonempty(self.instance_id, "instance_id")
        require_sha256_digest(
            self.warmup_snapshot_fingerprint,
            field_name="warmup_snapshot_fingerprint",
        )
        if not isinstance(self.carry_in_mode, CarryInMode):
            raise TypeError("carry_in_mode must be a CarryInMode")
        require_sha256_digest(
            self.warmup_result_fingerprint,
            field_name="warmup_result_fingerprint",
        )
        _aware(self.completed_at, "completed_at")
        if self.final_event_sequence < 0:
            raise ValueError("final_event_sequence must be non-negative")
        if self.final_event_sequence > 0 and self.final_event_id is None:
            raise ValueError("a non-zero final event sequence requires final_event_id")
        if self.final_event_id is not None:
            _nonempty(self.final_event_id, "final_event_id")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class ForwardWarmupDecision(StrEnum):
    COMPLETE = "complete"
    REPLAY_EXISTING = "replay_existing"
    CONFLICT = "conflict"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class ForwardWarmupResolution:
    decision: ForwardWarmupDecision
    instance: ForwardInstance
    receipt: ForwardWarmupReceipt | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ForwardWarmupDecision):
            raise TypeError("decision must be a ForwardWarmupDecision")
        if not isinstance(self.instance, ForwardInstance):
            raise TypeError("instance must be a ForwardInstance")
        if self.receipt is not None and not isinstance(self.receipt, ForwardWarmupReceipt):
            raise TypeError("receipt must be a ForwardWarmupReceipt")
        if self.decision in {
            ForwardWarmupDecision.COMPLETE,
            ForwardWarmupDecision.REPLAY_EXISTING,
        } and self.receipt is None:
            raise ValueError("completed warm-up resolutions require a receipt")
        if self.decision in {
            ForwardWarmupDecision.CONFLICT,
            ForwardWarmupDecision.REJECT,
        } and not self.rejection_reason:
            raise ValueError("rejected warm-up resolutions require a reason")
        if self.decision not in {
            ForwardWarmupDecision.CONFLICT,
            ForwardWarmupDecision.REJECT,
        } and self.rejection_reason:
            raise ValueError("successful warm-up resolutions cannot contain a reason")


def resolve_forward_warmup(
    instance: ForwardInstance,
    receipt: ForwardWarmupReceipt,
    *,
    existing_receipt: ForwardWarmupReceipt | None = None,
) -> ForwardWarmupResolution:
    """Complete or replay one warm-up handoff without invoking an engine."""

    if not isinstance(instance, ForwardInstance):
        raise TypeError("instance must be a ForwardInstance")
    if not isinstance(receipt, ForwardWarmupReceipt):
        raise TypeError("receipt must be a ForwardWarmupReceipt")
    if existing_receipt is not None and not isinstance(
        existing_receipt, ForwardWarmupReceipt
    ):
        raise TypeError("existing_receipt must be a ForwardWarmupReceipt")
    if existing_receipt is not None:
        if existing_receipt.fingerprint == receipt.fingerprint:
            return ForwardWarmupResolution(
                ForwardWarmupDecision.REPLAY_EXISTING,
                instance,
                existing_receipt,
            )
        return ForwardWarmupResolution(
            ForwardWarmupDecision.CONFLICT,
            instance,
            rejection_reason="warm-up receipt identity is already bound to different content",
        )
    if receipt.instance_id != instance.instance_id:
        return ForwardWarmupResolution(
            ForwardWarmupDecision.REJECT,
            instance,
            receipt,
            rejection_reason="warm-up receipt instance does not match the forward instance",
        )
    if receipt.warmup_snapshot_fingerprint != instance.warmup_snapshot_fingerprint:
        return ForwardWarmupResolution(
            ForwardWarmupDecision.REJECT,
            instance,
            receipt,
            rejection_reason="warm-up receipt snapshot does not match the forward instance",
        )
    if receipt.carry_in_mode is not instance.carry_in_mode:
        return ForwardWarmupResolution(
            ForwardWarmupDecision.REJECT,
            instance,
            receipt,
            rejection_reason="warm-up receipt carry-in mode does not match the forward instance",
        )
    if instance.state is not ForwardState.WARMING_UP:
        return ForwardWarmupResolution(
            ForwardWarmupDecision.REJECT,
            instance,
            receipt,
            rejection_reason="forward instance must be warming_up for first warm-up completion",
        )
    if instance.last_event_id is not None or instance.last_event_sequence != 0:
        return ForwardWarmupResolution(
            ForwardWarmupDecision.REJECT,
            instance,
            receipt,
            rejection_reason="warm-up completion cannot overwrite an existing live cursor",
        )
    if receipt.completed_at < instance.updated_at:
        return ForwardWarmupResolution(
            ForwardWarmupDecision.REJECT,
            instance,
            receipt,
            rejection_reason="warm-up completion time cannot move backwards",
        )
    next_instance = replace(
        instance,
        state=ForwardState.ACTIVE,
        last_event_id=receipt.final_event_id,
        last_event_sequence=receipt.final_event_sequence,
        updated_at=receipt.completed_at,
    )
    return ForwardWarmupResolution(ForwardWarmupDecision.COMPLETE, next_instance, receipt)
