"""Deterministic assembly of authenticated worker terminal evidence.

The persistence bundle owns authenticated lookup, while the host application
owns how result files are mapped to artifact publication plans.  This module
bridges those two explicit inputs without loading untrusted state, selecting a
principal from the worker payload, or inventing missing terminal evidence.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Protocol

from app.strategy_lab_v2.artifact_publication import ArtifactPublicationPlan
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.outcomes import OutcomeStatus
from app.strategy_lab_v2.result_publication import ResultPublicationDecision
from app.strategy_lab_v2.runtime_execution import RuntimeExecutionPhase
from app.strategy_lab_v2.worker_evidence import WorkerTerminalEvidenceLookup
from app.strategy_lab_v2.worker_process import WorkerProcessDecision
from app.strategy_lab_v2.worker_service import WorkerCompletionContext
from app.strategy_lab_v2.worker_terminal_adapter import WorkerTerminalEvidence

ArtifactPlanResolver = Callable[
    [WorkerCompletionContext, WorkerTerminalEvidenceLookup],
    Sequence[ArtifactPublicationPlan]
    | Awaitable[Sequence[ArtifactPublicationPlan]],
]


class EvidenceLookup(Protocol):
    def __call__(
        self, *, request_fingerprint: str, attempt_id: str
    ) -> WorkerTerminalEvidenceLookup | None | Awaitable[WorkerTerminalEvidenceLookup | None]: ...


def build_worker_terminal_evidence(
    context: WorkerCompletionContext,
    lookup: WorkerTerminalEvidenceLookup,
    *,
    artifact_plans: Sequence[ArtifactPublicationPlan] = (),
    released_at: datetime | None = None,
) -> WorkerTerminalEvidence:
    """Combine one worker receipt with authenticated durable terminal state.

    Artifact plans are deliberately supplied by the caller because only the
    host application knows which mounted files correspond to each result
    manifest.  Successful evidence requires one accepted publication plan for
    the exact manifest; failed/cancelled evidence cannot carry result data or
    artifact plans.
    """

    if not isinstance(context, WorkerCompletionContext):
        raise TypeError("context must be a WorkerCompletionContext")
    if not isinstance(lookup, WorkerTerminalEvidenceLookup):
        raise TypeError("lookup must be a WorkerTerminalEvidenceLookup")
    if lookup.inputs.attempt_id != context.request.admission.attempt_id:
        raise ValueError("durable evidence references a different attempt")
    if context.process.decision is not WorkerProcessDecision.COMPLETED:
        raise ValueError("terminal evidence requires a completed worker process")
    process_execution = context.process.execution
    if process_execution is None or process_execution.runtime_result is None:
        raise ValueError("completed worker process is missing runtime evidence")
    submission = lookup.inputs.submission
    execution = lookup.inputs.execution
    if submission is None or execution is None:
        raise ValueError("durable worker terminal evidence is incomplete")
    if execution.outcome.submission_id != submission.submission_id:
        raise ValueError("durable outcome does not match the submission")

    plans = tuple(artifact_plans)
    if any(not isinstance(item, ArtifactPublicationPlan) for item in plans):
        raise TypeError("artifact_plans must contain ArtifactPublicationPlan values")
    if len({content_digest(item) for item in plans}) != len(plans):
        raise ValueError("artifact_plans must be unique")
    plans = tuple(sorted(plans, key=content_digest))
    if released_at is not None and (
        released_at.tzinfo is None or released_at.utcoffset() is None
    ):
        raise ValueError("released_at must be timezone-aware")

    runtime_phase = process_execution.runtime_result.state.phase
    if runtime_phase is RuntimeExecutionPhase.SUCCEEDED:
        manifest = lookup.inputs.manifest
        if manifest is None:
            raise ValueError("successful worker evidence is missing a result manifest")
        if execution.outcome.result_digest not in {None, manifest.fingerprint}:
            raise ValueError("durable outcome does not match the result manifest")
        candidates = tuple(
            item
            for item in lookup.inputs.publications
            if item.result_fingerprint == manifest.fingerprint
            and item.decision is not ResultPublicationDecision.REJECT
        )
        if len(candidates) != 1:
            raise ValueError("successful worker evidence requires one accepted publication plan")
        return WorkerTerminalEvidence(
            principal=lookup.owner_id,
            submission=submission,
            outcome=execution.outcome,
            progress=execution.progress,
            result=manifest,
            publication=candidates[0],
            artifact_plans=plans,
            released_at=released_at,
        )

    if plans:
        raise ValueError("non-successful worker evidence cannot carry artifact plans")
    if lookup.inputs.manifest is not None or lookup.inputs.publications:
        raise ValueError("non-successful worker evidence cannot carry result evidence")
    error = execution.outcome.error
    if runtime_phase is RuntimeExecutionPhase.FAILED and error is None:
        raise ValueError("failed worker evidence is missing an error")
    if runtime_phase is RuntimeExecutionPhase.CANCELLED and error is not None:
        raise ValueError("cancelled worker evidence cannot carry an error")
    if runtime_phase not in {
        RuntimeExecutionPhase.FAILED,
        RuntimeExecutionPhase.CANCELLED,
    }:
        raise ValueError("worker runtime evidence is not terminal")
    if execution.outcome.status not in {
        OutcomeStatus.ACCEPTED,
        OutcomeStatus.RUNNING,
        OutcomeStatus.FAILED,
        OutcomeStatus.CANCELLED,
    }:
        raise ValueError("non-successful worker outcome has an invalid status")
    return WorkerTerminalEvidence(
        principal=lookup.owner_id,
        submission=submission,
        outcome=execution.outcome,
        progress=execution.progress,
        error=error,
        released_at=released_at,
    )


def create_worker_terminal_evidence_resolver(
    lookup_loader: EvidenceLookup,
    artifact_plan_resolver: ArtifactPlanResolver,
) -> Callable[[WorkerCompletionContext], Awaitable[WorkerTerminalEvidence]]:
    """Create the callback shape consumed by ``PostgresWorkerTerminalAdapter``."""

    if not callable(lookup_loader):
        raise TypeError("lookup_loader must be callable")
    if not callable(artifact_plan_resolver):
        raise TypeError("artifact_plan_resolver must be callable")

    async def resolve(context: WorkerCompletionContext) -> WorkerTerminalEvidence:
        if not isinstance(context, WorkerCompletionContext):
            raise TypeError("context must be a WorkerCompletionContext")
        attempt_id = context.request.admission.attempt_id
        loaded = lookup_loader(
            request_fingerprint=context.request.request_fingerprint,
            attempt_id=attempt_id,
        )
        lookup = await loaded if inspect.isawaitable(loaded) else loaded
        if lookup is None:
            raise LookupError("worker terminal evidence was not found")
        if not isinstance(lookup, WorkerTerminalEvidenceLookup):
            raise TypeError("lookup_loader returned an invalid evidence lookup")
        resolved = artifact_plan_resolver(context, lookup)
        plans = await resolved if inspect.isawaitable(resolved) else resolved
        if not isinstance(plans, Sequence):
            raise TypeError("artifact_plan_resolver must return a sequence")
        return build_worker_terminal_evidence(context, lookup, artifact_plans=plans)

    return resolve


__all__ = [
    "ArtifactPlanResolver",
    "EvidenceLookup",
    "build_worker_terminal_evidence",
    "create_worker_terminal_evidence_resolver",
]
