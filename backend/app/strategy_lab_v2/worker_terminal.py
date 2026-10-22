"""Atomic public terminal projection plus worker-capacity settlement.

Workers produce runtime evidence first, while public outcome/progress records
and worker lease/capacity records are separate durable aggregates.  This
module composes their pure decisions and only returns a committed proposal
when both sides accept; any rejection preserves every original state for one
compare-and-set transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.admission import ExecutionAdmission
from app.strategy_lab_v2.api_contracts import ApiError
from app.strategy_lab_v2.contracts import RunResultManifest
from app.strategy_lab_v2.execution_terminal import (
    ExecutionTerminalDecision,
    ExecutionTerminalResolution,
    materialize_execution_terminal,
)
from app.strategy_lab_v2.lease_observations import LeaseObservationState
from app.strategy_lab_v2.outcomes import ExecutionOutcome
from app.strategy_lab_v2.progress import ExecutionProgressState
from app.strategy_lab_v2.runtime_execution import RuntimeExecutionState
from app.strategy_lab_v2.submissions import SubmissionReceipt
from app.strategy_lab_v2.worker_execution import WorkerExecutionResolution
from app.strategy_lab_v2.worker_settlement import (
    WorkerSettlementDecision,
    WorkerSettlementLedger,
    WorkerSettlementResolution,
    settle_worker_execution,
)
from app.strategy_lab_v2.workers import WorkerPoolState


class WorkerTerminalDecision(StrEnum):
    COMMITTED = "committed"
    REPLAY_EXISTING = "replay_existing"
    CONFLICT = "conflict"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class WorkerTerminalResolution:
    """One all-or-nothing terminal proposal for public and worker state."""

    decision: WorkerTerminalDecision
    outcome: ExecutionOutcome
    progress: ExecutionProgressState
    pool: WorkerPoolState
    lease_state: LeaseObservationState
    settlement_ledger: WorkerSettlementLedger
    terminal_resolution: ExecutionTerminalResolution
    settlement_resolution: WorkerSettlementResolution | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, WorkerTerminalDecision):
            raise TypeError("decision must be a WorkerTerminalDecision")
        if not isinstance(self.outcome, ExecutionOutcome):
            raise TypeError("outcome must be an ExecutionOutcome")
        if not isinstance(self.progress, ExecutionProgressState):
            raise TypeError("progress must be an ExecutionProgressState")
        if not isinstance(self.pool, WorkerPoolState):
            raise TypeError("pool must be a WorkerPoolState")
        if not isinstance(self.lease_state, LeaseObservationState):
            raise TypeError("lease_state must be a LeaseObservationState")
        if not isinstance(self.settlement_ledger, WorkerSettlementLedger):
            raise TypeError("settlement_ledger must be a WorkerSettlementLedger")
        if not isinstance(self.terminal_resolution, ExecutionTerminalResolution):
            raise TypeError("terminal_resolution must be an ExecutionTerminalResolution")
        if self.settlement_resolution is not None and not isinstance(
            self.settlement_resolution, WorkerSettlementResolution
        ):
            raise TypeError("settlement_resolution must be a WorkerSettlementResolution")
        if self.decision in {
            WorkerTerminalDecision.CONFLICT,
            WorkerTerminalDecision.REJECT,
        } and not self.rejection_reason:
            raise ValueError("conflicts and rejections require a reason")
        if self.decision in {
            WorkerTerminalDecision.COMMITTED,
            WorkerTerminalDecision.REPLAY_EXISTING,
        } and self.rejection_reason:
            raise ValueError("committed resolutions cannot contain a rejection reason")


def materialize_worker_terminal(
    settlement_ledger: WorkerSettlementLedger,
    pool: WorkerPoolState,
    lease_state: LeaseObservationState,
    admission: ExecutionAdmission,
    execution: WorkerExecutionResolution,
    receipt: SubmissionReceipt,
    outcome: ExecutionOutcome,
    progress: ExecutionProgressState,
    *,
    result: RunResultManifest | None = None,
    error: ApiError | None = None,
    observed_at: datetime,
    released_at: datetime,
) -> WorkerTerminalResolution:
    """Project terminal public state and release worker state atomically.

    A worker rejection without runtime terminal evidence is intentionally not
    converted into a public outcome here; the recovery planner owns that path.
    Successful, failed, and cancelled runtime states must pass the terminal
    projection before capacity and lease settlement are accepted.
    """

    values = (
        settlement_ledger,
        pool,
        lease_state,
        admission,
        execution,
        receipt,
        outcome,
        progress,
    )
    expected = (
        WorkerSettlementLedger,
        WorkerPoolState,
        LeaseObservationState,
        ExecutionAdmission,
        WorkerExecutionResolution,
        SubmissionReceipt,
        ExecutionOutcome,
        ExecutionProgressState,
    )
    names = (
        "settlement_ledger",
        "pool",
        "lease_state",
        "admission",
        "execution",
        "receipt",
        "outcome",
        "progress",
    )
    for name, value, expected_type in zip(names, values, expected, strict=True):
        if not isinstance(value, expected_type):
            raise TypeError(f"{name} must be a {expected_type.__name__}")
    if result is not None and not isinstance(result, RunResultManifest):
        raise TypeError("result must be a RunResultManifest")
    if error is not None and not isinstance(error, ApiError):
        raise TypeError("error must be an ApiError")
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    if released_at.tzinfo is None or released_at.utcoffset() is None:
        raise ValueError("released_at must be timezone-aware")
    if execution.runtime_result is None:
        return _reject(
            settlement_ledger,
            pool,
            lease_state,
            outcome,
            progress,
            "worker execution has no terminal runtime evidence",
        )

    runtime_state: RuntimeExecutionState = execution.runtime_result.state
    terminal = materialize_execution_terminal(
        receipt,
        runtime_state,
        outcome,
        progress,
        result=result,
        error=error,
        observed_at=observed_at,
    )
    if terminal.decision is ExecutionTerminalDecision.REJECT:
        return _reject(
            settlement_ledger,
            pool,
            lease_state,
            outcome,
            progress,
            terminal.rejection_reason or "terminal projection was rejected",
            terminal_resolution=terminal,
        )
    has_existing_settlement = any(
        record.attempt_id == admission.attempt_id
        for record in settlement_ledger.records
    )
    if released_at < observed_at and not (
        terminal.decision is ExecutionTerminalDecision.REPLAY_EXISTING
        and has_existing_settlement
    ):
        return _reject(
            settlement_ledger,
            pool,
            lease_state,
            outcome,
            progress,
            "worker release cannot precede terminal observation",
            terminal_resolution=terminal,
        )

    settlement = settle_worker_execution(
        settlement_ledger,
        pool,
        admission,
        execution,
        lease_state=lease_state,
        released_at=released_at,
    )
    if settlement.decision in {
        WorkerSettlementDecision.CONFLICT,
        WorkerSettlementDecision.REJECT,
    }:
        return _reject(
            settlement_ledger,
            pool,
            lease_state,
            outcome,
            progress,
            settlement.rejection_reason or "worker settlement was rejected",
            terminal_resolution=terminal,
            settlement_resolution=settlement,
            decision=(
                WorkerTerminalDecision.CONFLICT
                if settlement.decision is WorkerSettlementDecision.CONFLICT
                else WorkerTerminalDecision.REJECT
            ),
        )

    replay = (
        terminal.decision is ExecutionTerminalDecision.REPLAY_EXISTING
        and settlement.decision is WorkerSettlementDecision.REPLAY_EXISTING
    )
    return WorkerTerminalResolution(
        WorkerTerminalDecision.REPLAY_EXISTING if replay else WorkerTerminalDecision.COMMITTED,
        terminal.outcome,
        terminal.progress,
        settlement.pool,
        settlement.lease_state,
        settlement.ledger,
        terminal,
        settlement,
    )


def _reject(
    settlement_ledger: WorkerSettlementLedger,
    pool: WorkerPoolState,
    lease_state: LeaseObservationState,
    outcome: ExecutionOutcome,
    progress: ExecutionProgressState,
    reason: str,
    *,
    terminal_resolution: ExecutionTerminalResolution | None = None,
    settlement_resolution: WorkerSettlementResolution | None = None,
    decision: WorkerTerminalDecision = WorkerTerminalDecision.REJECT,
) -> WorkerTerminalResolution:
    if terminal_resolution is None:
        terminal_resolution = ExecutionTerminalResolution(
            ExecutionTerminalDecision.REJECT,
            outcome,
            progress,
            reason,
        )
    return WorkerTerminalResolution(
        decision,
        outcome,
        progress,
        pool,
        lease_state,
        settlement_ledger,
        terminal_resolution,
        settlement_resolution,
        reason,
    )
