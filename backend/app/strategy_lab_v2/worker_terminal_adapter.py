"""Concrete worker terminal writer over the Strategy Lab v2 adapters.

The Redis worker only hands this adapter an immutable process receipt.  An
application-owned evidence resolver supplies the authenticated submission and
result publication evidence; this coordinator then replays the pure terminal
gate and commits runtime, public outcome/progress, result, summary, settlement
receipt, and worker capacity in a deterministic, retry-safe order.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from app.strategy_lab_v2.api_contracts import ApiError
from app.strategy_lab_v2.artifact_publication import ArtifactPublicationPlan
from app.strategy_lab_v2.contracts import RunResultManifest
from app.strategy_lab_v2.execution_summary import ExecutionSummary
from app.strategy_lab_v2.outcomes import ExecutionOutcome, OutcomeUpdate
from app.strategy_lab_v2.postgres_execution_state import (
    PostgresExecutionStateAdapter,
    StateMutationDecision,
)
from app.strategy_lab_v2.postgres_result_completion import PostgresResultCompletionAdapter
from app.strategy_lab_v2.postgres_runtime_execution import (
    PostgresRuntimeExecutionAdapter,
    RuntimeStateDecision,
)
from app.strategy_lab_v2.postgres_worker_settlement import (
    PostgresWorkerSettlementAdapter,
)
from app.strategy_lab_v2.postgres_worker_state import (
    PostgresWorkerStateAdapter,
    WorkerCapacityDecision,
)
from app.strategy_lab_v2.progress import ExecutionProgressState, ExecutionProgressUpdate
from app.strategy_lab_v2.result_completion import ResultCompletionDecision
from app.strategy_lab_v2.result_publication import ResultPublicationPlan
from app.strategy_lab_v2.worker_consumer import WorkerHandleDecision, WorkerHandleResult
from app.strategy_lab_v2.worker_process import WorkerProcessDecision
from app.strategy_lab_v2.worker_settlement import WorkerSettlementLedger
from app.strategy_lab_v2.worker_terminal import (
    WorkerTerminalDecision,
    WorkerTerminalResolution,
    materialize_worker_terminal,
)

if TYPE_CHECKING:
    from app.strategy_lab_v2.worker_service import WorkerCompletionContext


class WorkerSettlementLedgerReader(Protocol):
    async def load_ledger(self, *, principal: Any): ...


class WorkerSettlementLedgerWriter(Protocol):
    async def ensure(self, *, principal: Any, record: Any): ...


@dataclass(frozen=True, slots=True)
class WorkerTerminalEvidence:
    """Authenticated application evidence required after process execution."""

    principal: Any
    submission: Any
    outcome: ExecutionOutcome
    progress: ExecutionProgressState
    result: RunResultManifest | None = None
    error: ApiError | None = None
    publication: ResultPublicationPlan | None = None
    artifact_plans: tuple[ArtifactPublicationPlan, ...] = ()
    released_at: datetime | None = None

    def __post_init__(self) -> None:
        from app.strategy_lab_v2.submissions import SubmissionReceipt

        if not isinstance(self.submission, SubmissionReceipt):
            raise TypeError("submission must be a SubmissionReceipt")
        if not isinstance(self.outcome, ExecutionOutcome):
            raise TypeError("outcome must be an ExecutionOutcome")
        if not isinstance(self.progress, ExecutionProgressState):
            raise TypeError("progress must be an ExecutionProgressState")
        if self.result is not None and not isinstance(self.result, RunResultManifest):
            raise TypeError("result must be a RunResultManifest")
        if self.error is not None and not isinstance(self.error, ApiError):
            raise TypeError("error must be an ApiError")
        if self.publication is not None and not isinstance(
            self.publication, ResultPublicationPlan
        ):
            raise TypeError("publication must be a ResultPublicationPlan")
        plans = tuple(self.artifact_plans)
        if any(not isinstance(item, ArtifactPublicationPlan) for item in plans):
            raise TypeError("artifact_plans must contain ArtifactPublicationPlan values")
        object.__setattr__(self, "artifact_plans", plans)
        if self.released_at is not None:
            if self.released_at.tzinfo is None or self.released_at.utcoffset() is None:
                raise ValueError("released_at must be timezone-aware")
            object.__setattr__(self, "released_at", self.released_at.astimezone(UTC))


WorkerTerminalEvidenceResolver = Callable[
    ["WorkerCompletionContext"], Awaitable[WorkerTerminalEvidence]
]


class PostgresWorkerTerminalAdapter:
    """Implement ``WorkerTerminalWriter`` with explicit retry boundaries."""

    def __init__(
        self,
        evidence_resolver: WorkerTerminalEvidenceResolver,
        *,
        runtime_execution: PostgresRuntimeExecutionAdapter,
        execution_state: PostgresExecutionStateAdapter,
        execution_summaries: Any,
        result_completion: PostgresResultCompletionAdapter,
        worker_state: PostgresWorkerStateAdapter,
        settlements: PostgresWorkerSettlementAdapter,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not callable(evidence_resolver):
            raise TypeError("evidence_resolver must be callable")
        for name, value in (
            ("runtime_execution", runtime_execution),
            ("execution_state", execution_state),
            ("execution_summaries", execution_summaries),
            ("result_completion", result_completion),
            ("worker_state", worker_state),
            ("settlements", settlements),
        ):
            if value is None:
                raise TypeError(f"{name} is required")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._evidence_resolver = evidence_resolver
        self._runtime_execution = runtime_execution
        self._execution_state = execution_state
        self._execution_summaries = execution_summaries
        self._result_completion = result_completion
        self._worker_state = worker_state
        self._settlements = settlements
        self._clock = clock

    async def __call__(self, context: WorkerCompletionContext) -> WorkerHandleResult:
        return await self.write(context)

    async def write(self, context: WorkerCompletionContext) -> WorkerHandleResult:
        """Persist one terminal receipt, leaving Redis pending on uncertainty."""

        if not hasattr(context, "entry") or not hasattr(context, "request"):
            raise TypeError("context must be a WorkerCompletionContext")
        entry_fingerprint = context.entry.fingerprint
        process = context.process
        if process.decision is not WorkerProcessDecision.COMPLETED or process.execution is None:
            return _retry(entry_fingerprint, "worker process did not produce terminal evidence")
        execution = process.execution
        if execution.decision.value == "rejected":
            return _reject(entry_fingerprint, execution.rejection_reason or "worker execution rejected")
        if execution.nautilus_result is None:
            return _retry(entry_fingerprint, "worker execution omitted Nautilus evidence")
        try:
            evidence = await self._evidence_resolver(context)
        except Exception as error:  # pragma: no cover - application boundary
            return _retry(entry_fingerprint, f"terminal evidence lookup failed: {type(error).__name__}")
        if not isinstance(evidence, WorkerTerminalEvidence):
            return _reject(entry_fingerprint, "terminal evidence resolver returned an invalid record")
        request = context.request
        if evidence.submission.request.attempt_id != request.admission.attempt_id:
            return _reject(entry_fingerprint, "terminal evidence references a different attempt")
        released_at = evidence.released_at or context.observed_at
        try:
            runtime = await self._runtime_execution.materialize_nautilus_result(
                principal=evidence.principal,
                execution_plan=request.execution_plan,
                sandbox_plan=request.sandbox_plan,
                run_result=execution.nautilus_result,
                observed_at=context.observed_at,
            )
        except Exception as error:  # pragma: no cover - persistence boundary
            return _retry(entry_fingerprint, f"runtime evidence persistence failed: {type(error).__name__}")
        if runtime.decision in {RuntimeStateDecision.REJECT, RuntimeStateDecision.NOT_FOUND}:
            return _reject(entry_fingerprint, runtime.rejection_reason or "runtime evidence was rejected")
        if runtime.state is None:
            return _retry(entry_fingerprint, "runtime evidence persistence returned no state")
        try:
            pool = await self._worker_state.load_pool(request.worker_pool.profile)
            lease_state = await self._worker_state.load_lease(request.lease_state.lease.lease_id)
            if lease_state is None:
                return _retry(entry_fingerprint, "worker lease is not persisted")
            ledger = await self._settlements.load_ledger(principal=evidence.principal)
            projection_ledger = ledger
            existing_settlement = next(
                (item for item in ledger.records if item.attempt_id == request.admission.attempt_id),
                None,
            )
            reservation_active = any(
                item.reservation_id == request.admission.reservation_id and item.active
                for item in pool.reservations
            )
            if existing_settlement is not None and reservation_active:
                # The immutable receipt may have committed immediately before
                # the capacity transaction.  Recompute the proposal from an
                # empty pure ledger; ``ensure`` below still verifies that the
                # resulting record exactly matches the persisted receipt.
                projection_ledger = WorkerSettlementLedger()
            terminal = materialize_worker_terminal(
                projection_ledger,
                pool,
                lease_state,
                request.admission,
                execution,
                evidence.submission,
                evidence.outcome,
                evidence.progress,
                result=evidence.result,
                error=evidence.error,
                observed_at=context.observed_at,
                released_at=released_at,
            )
        except Exception as error:  # pragma: no cover - application boundary
            return _retry(entry_fingerprint, f"terminal projection failed: {type(error).__name__}")
        if terminal.decision in {WorkerTerminalDecision.REJECT, WorkerTerminalDecision.CONFLICT}:
            return _reject(entry_fingerprint, terminal.rejection_reason or "terminal projection rejected")
        settlement = terminal.settlement_resolution
        if settlement is None or settlement.record is None or settlement.observation is None:
            return _retry(entry_fingerprint, "terminal projection omitted settlement evidence")
        try:
            settlement_receipt = await self._settlements.ensure(
                principal=evidence.principal, record=settlement.record
            )
        except Exception as error:  # pragma: no cover - persistence boundary
            return _retry(entry_fingerprint, f"settlement receipt persistence failed: {type(error).__name__}")

        state_resolution = await self._persist_public_state(
            evidence, terminal
        )
        if state_resolution is None:
            return _retry(entry_fingerprint, "public terminal state persistence failed")
        persisted_outcome, persisted_progress = state_resolution
        completion = None
        if persisted_outcome.status.value == "succeeded":
            if evidence.publication is None or evidence.result is None:
                return _reject(entry_fingerprint, "successful terminal evidence is missing publication")
            try:
                completion = await self._result_completion.finalize(
                    principal=evidence.principal,
                    submission=evidence.submission,
                    runtime_state=runtime.state,
                    outcome=persisted_outcome,
                    progress=persisted_progress,
                    publication=evidence.publication,
                    artifact_plans=evidence.artifact_plans,
                    completed_at=context.observed_at,
                )
            except Exception as error:  # pragma: no cover - persistence boundary
                return _retry(entry_fingerprint, f"result completion persistence failed: {type(error).__name__}")
            if completion.decision in {
                ResultCompletionDecision.CONFLICT,
                ResultCompletionDecision.REJECT,
            }:
                return _reject(entry_fingerprint, completion.rejection_reason or "result completion rejected")
        publication = evidence.publication if persisted_outcome.status.value == "succeeded" else None
        try:
            summary = await self._execution_summaries.ensure(
                principal=evidence.principal,
                summary=_summary(evidence.submission, persisted_outcome, persisted_progress, publication),
            )
            capacity = await self._worker_state.release_capacity(
                profile=pool.profile,
                reservation_id=request.admission.reservation_id,
                lease_id=lease_state.lease.lease_id,
                observation=settlement.observation,
            )
        except Exception as error:  # pragma: no cover - persistence boundary
            return _retry(entry_fingerprint, f"terminal settlement persistence failed: {type(error).__name__}")
        if capacity.decision is WorkerCapacityDecision.REJECT:
            return _retry(entry_fingerprint, capacity.rejection_reason or "worker capacity release was rejected")
        receipt_digest = _digest(
            context,
            terminal,
            runtime.state,
            settlement_receipt,
            summary,
            capacity,
            completion,
        )
        return WorkerHandleResult(entry_fingerprint, WorkerHandleDecision.COMPLETE, receipt_digest)

    async def _persist_public_state(
        self,
        evidence: WorkerTerminalEvidence,
        terminal: WorkerTerminalResolution,
    ) -> tuple[ExecutionOutcome, ExecutionProgressState] | None:
        outcome = terminal.outcome
        progress = terminal.progress
        # A process retry may arrive after public state was committed but
        # before settlement/capacity completed.  Do not manufacture a new
        # progress fingerprint for an already-terminal pair.
        if terminal.decision is WorkerTerminalDecision.REPLAY_EXISTING or (
            evidence.outcome == outcome and evidence.progress == progress
        ):
            return outcome, progress
        outcome_update = OutcomeUpdate(
            outcome.submission_id,
            outcome.attempt_id,
            outcome.sequence,
            outcome.status,
            outcome.updated_at,
            result_digest=outcome.result_digest,
            error=outcome.error,
        )
        progress_update = ExecutionProgressUpdate(
            progress.attempt_id,
            progress.sequence,
            progress.phase,
            progress.completed_units,
            progress.total_units,
            progress.updated_at,
            detail="worker terminal persisted",
        )
        resolution = await self._execution_state.transition(
            principal=evidence.principal,
            outcome_update=outcome_update,
            progress_update=progress_update,
        )
        if resolution.decision in {
            StateMutationDecision.CONFLICT,
            StateMutationDecision.NOT_FOUND,
            StateMutationDecision.REJECT,
        }:
            return None
        if resolution.outcome is None or resolution.progress is None:
            return None
        return resolution.outcome, resolution.progress


def _summary(
    receipt: Any,
    outcome: ExecutionOutcome,
    progress: ExecutionProgressState,
    publication: ResultPublicationPlan | None,
) -> ExecutionSummary:
    from app.strategy_lab_v2.execution_summary import build_execution_summary

    return build_execution_summary(receipt, outcome, progress, publication)


def _digest(*values: Any) -> str:
    from app.strategy_lab_v2.canonical import content_digest

    return content_digest(values)


def _retry(entry_fingerprint: str, reason: str) -> WorkerHandleResult:
    return WorkerHandleResult(entry_fingerprint, WorkerHandleDecision.RETRY, rejection_reason=reason)


def _reject(entry_fingerprint: str, reason: str) -> WorkerHandleResult:
    return WorkerHandleResult(entry_fingerprint, WorkerHandleDecision.REJECT, rejection_reason=reason)


__all__ = [
    "PostgresWorkerTerminalAdapter",
    "WorkerTerminalEvidence",
    "WorkerTerminalEvidenceResolver",
]
