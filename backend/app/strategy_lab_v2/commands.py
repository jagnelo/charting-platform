"""Idempotent retry/cancellation command intents for execution adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.outcomes import ExecutionOutcome, OutcomeStatus
from app.strategy_lab_v2.progress import ExecutionProgressState, ProgressPhase


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


class ExecutionCommandKind(StrEnum):
    CANCEL = "cancel"
    RETRY = "retry"


@dataclass(frozen=True, slots=True)
class ExecutionCommand:
    """Client intent; accepted commands still require an adapter-side effect."""

    command_id: str
    attempt_id: str
    kind: ExecutionCommandKind
    requested_at: datetime
    reason: str

    def __post_init__(self) -> None:
        require_sha256_digest(self.command_id, field_name="command_id")
        _nonempty(self.attempt_id, "attempt_id")
        if not isinstance(self.kind, ExecutionCommandKind):
            raise TypeError("kind must be an ExecutionCommandKind")
        _aware(self.requested_at, "requested_at")
        _nonempty(self.reason, "reason")

    @property
    def fingerprint(self) -> str:
        """Stable identity independent of transport/request timing."""

        return content_digest(
            {
                "attempt_id": self.attempt_id,
                "command_id": self.command_id,
                "kind": self.kind,
                "reason": self.reason,
            }
        )


class CommandEffect(StrEnum):
    CANCELLATION_REQUESTED = "cancellation_requested"
    RETRY_REQUESTED = "retry_requested"


@dataclass(frozen=True, slots=True)
class ExecutionCommandReceipt:
    command_id: str
    command_fingerprint: str
    attempt_id: str
    kind: ExecutionCommandKind
    effect: CommandEffect
    accepted_at: datetime

    def __post_init__(self) -> None:
        require_sha256_digest(self.command_id, field_name="command_id")
        require_sha256_digest(self.command_fingerprint, field_name="command_fingerprint")
        _nonempty(self.attempt_id, "attempt_id")
        if not isinstance(self.kind, ExecutionCommandKind):
            raise TypeError("kind must be an ExecutionCommandKind")
        if not isinstance(self.effect, CommandEffect):
            raise TypeError("effect must be a CommandEffect")
        _aware(self.accepted_at, "accepted_at")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ExecutionCommandLedger:
    receipts: tuple[ExecutionCommandReceipt, ...] = ()

    def __post_init__(self) -> None:
        receipts = tuple(self.receipts)
        if any(not isinstance(item, ExecutionCommandReceipt) for item in receipts):
            raise TypeError("receipts must contain ExecutionCommandReceipt values")
        ids = [item.command_id for item in receipts]
        if len(ids) != len(set(ids)):
            raise ValueError("command ids must be unique")
        object.__setattr__(self, "receipts", tuple(sorted(receipts, key=lambda item: item.command_id)))

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class ExecutionCommandDecision(StrEnum):
    ACCEPT = "accept"
    REPLAY_EXISTING = "replay_existing"
    CONFLICT = "conflict"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class ExecutionCommandResolution:
    decision: ExecutionCommandDecision
    ledger: ExecutionCommandLedger
    command_fingerprint: str
    receipt: ExecutionCommandReceipt | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ExecutionCommandDecision):
            raise TypeError("decision must be an ExecutionCommandDecision")
        if not isinstance(self.ledger, ExecutionCommandLedger):
            raise TypeError("ledger must be an ExecutionCommandLedger")
        require_sha256_digest(self.command_fingerprint, field_name="command_fingerprint")
        if self.receipt is not None and not isinstance(self.receipt, ExecutionCommandReceipt):
            raise TypeError("receipt must be an ExecutionCommandReceipt")
        if self.decision in {
            ExecutionCommandDecision.ACCEPT,
            ExecutionCommandDecision.REPLAY_EXISTING,
        } and self.receipt is None:
            raise ValueError("accepted command resolutions require a receipt")
        if self.decision in {
            ExecutionCommandDecision.CONFLICT,
            ExecutionCommandDecision.REJECT,
        } and not self.rejection_reason:
            raise ValueError("conflicts and rejections require a reason")
        if self.decision not in {
            ExecutionCommandDecision.CONFLICT,
            ExecutionCommandDecision.REJECT,
        } and self.rejection_reason:
            raise ValueError("successful command resolutions cannot contain a reason")


def resolve_execution_command(
    ledger: ExecutionCommandLedger,
    command: ExecutionCommand,
    outcome: ExecutionOutcome,
    progress: ExecutionProgressState,
    *,
    accepted_at: datetime,
) -> ExecutionCommandResolution:
    """Resolve command idempotency and preconditions without applying effects."""

    if not isinstance(ledger, ExecutionCommandLedger):
        raise TypeError("ledger must be an ExecutionCommandLedger")
    if not isinstance(command, ExecutionCommand):
        raise TypeError("command must be an ExecutionCommand")
    if not isinstance(outcome, ExecutionOutcome):
        raise TypeError("outcome must be an ExecutionOutcome")
    if not isinstance(progress, ExecutionProgressState):
        raise TypeError("progress must be an ExecutionProgressState")
    _aware(accepted_at, "accepted_at")
    if accepted_at < command.requested_at:
        raise ValueError("command acceptance cannot precede request")
    if command.attempt_id != outcome.attempt_id or command.attempt_id != progress.attempt_id:
        return ExecutionCommandResolution(
            ExecutionCommandDecision.REJECT,
            ledger,
            command.fingerprint,
            rejection_reason="command attempt does not match outcome and progress",
        )
    existing = next((item for item in ledger.receipts if item.command_id == command.command_id), None)
    if existing is not None:
        if existing.command_fingerprint == command.fingerprint:
            return ExecutionCommandResolution(
                ExecutionCommandDecision.REPLAY_EXISTING,
                ledger,
                command.fingerprint,
                existing,
            )
        return ExecutionCommandResolution(
            ExecutionCommandDecision.CONFLICT,
            ledger,
            command.fingerprint,
            rejection_reason="command id is already bound to different content",
        )
    if command.kind is ExecutionCommandKind.CANCEL:
        if outcome.status in {
            OutcomeStatus.SUCCEEDED,
            OutcomeStatus.FAILED,
            OutcomeStatus.CANCELLED,
        } or progress.phase in {
            ProgressPhase.SUCCEEDED,
            ProgressPhase.FAILED,
            ProgressPhase.CANCELLED,
        }:
            return ExecutionCommandResolution(
                ExecutionCommandDecision.REJECT,
                ledger,
                command.fingerprint,
                rejection_reason="terminal executions cannot be cancelled",
            )
        effect = CommandEffect.CANCELLATION_REQUESTED
    else:
        if outcome.status is not OutcomeStatus.FAILED or progress.phase is not ProgressPhase.FAILED:
            return ExecutionCommandResolution(
                ExecutionCommandDecision.REJECT,
                ledger,
                command.fingerprint,
                rejection_reason="retry requires a failed execution",
            )
        effect = CommandEffect.RETRY_REQUESTED
    receipt = ExecutionCommandReceipt(
        command_id=command.command_id,
        command_fingerprint=command.fingerprint,
        attempt_id=command.attempt_id,
        kind=command.kind,
        effect=effect,
        accepted_at=accepted_at,
    )
    return ExecutionCommandResolution(
        ExecutionCommandDecision.ACCEPT,
        ExecutionCommandLedger(ledger.receipts + (receipt,)),
        command.fingerprint,
        receipt,
    )
