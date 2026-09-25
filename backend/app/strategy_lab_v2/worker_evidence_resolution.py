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
from typing import Any, Protocol

from app.strategy_lab_v2.api_contracts import ApiError, ApiErrorCode
from app.strategy_lab_v2.artifact_application import (
    ArtifactPublicationDecision,
    ArtifactPublicationResolution,
)
from app.strategy_lab_v2.artifact_publication import ArtifactPublicationPlan
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import RunResultManifest
from app.strategy_lab_v2.outcomes import OutcomeStatus
from app.strategy_lab_v2.result_publication import ResultPublicationDecision
from app.strategy_lab_v2.runtime_execution import RuntimeExecutionPhase, RuntimeExecutionState
from app.strategy_lab_v2.worker_evidence import WorkerTerminalEvidenceLookup
from app.strategy_lab_v2.worker_process import WorkerProcessDecision
from app.strategy_lab_v2.worker_service import WorkerCompletionContext
from app.strategy_lab_v2.worker_terminal_adapter import WorkerTerminalEvidence

ArtifactPlanResolver = Callable[
    [WorkerCompletionContext, WorkerTerminalEvidenceLookup],
    Sequence[ArtifactPublicationPlan]
    | Awaitable[Sequence[ArtifactPublicationPlan]],
]
WorkerRuntimeErrorFactory = Callable[[WorkerCompletionContext, RuntimeExecutionState], ApiError]


class EvidenceLookup(Protocol):
    def __call__(
        self, *, request_fingerprint: str, attempt_id: str
    ) -> WorkerTerminalEvidenceLookup | None | Awaitable[WorkerTerminalEvidenceLookup | None]: ...


class SandboxArtifactPublisher(Protocol):
    async def publish_sandbox_result(
        self,
        manifest: Any,
        sandbox_plan: Any,
        sandbox_result: Any,
        *,
        committed_at: datetime,
    ) -> ArtifactPublicationResolution: ...


def default_worker_failure_error(
    context: WorkerCompletionContext,
    runtime_state: RuntimeExecutionState,
) -> ApiError:
    """Map a failed runtime receipt to a stable, non-leaking API error.

    The worker process persists only a content digest for sandbox failure
    details.  The package therefore exposes that digest as typed diagnostic
    metadata and never reconstructs exception text or paths at the terminal
    boundary.  An application may still supply a richer authenticated error
    in ``ExecutionCommandContext``; this helper is only the deterministic
    fallback when the durable outcome has not yet been projected.
    """

    if not isinstance(context, WorkerCompletionContext):
        raise TypeError("context must be a WorkerCompletionContext")
    if not isinstance(runtime_state, RuntimeExecutionState):
        raise TypeError("runtime_state must be a RuntimeExecutionState")
    if runtime_state.phase is not RuntimeExecutionPhase.FAILED:
        raise ValueError("default worker failure errors require a failed runtime state")
    if runtime_state.error_digest is None:
        raise ValueError("failed runtime state is missing its error digest")
    return ApiError(
        ApiErrorCode.INTERNAL_ERROR,
        "strategy worker execution failed",
        context.request.request_fingerprint,
        500,
        True,
        {"error_digest": runtime_state.error_digest},
    )


def build_worker_terminal_evidence(
    context: WorkerCompletionContext,
    lookup: WorkerTerminalEvidenceLookup,
    *,
    artifact_plans: Sequence[ArtifactPublicationPlan] = (),
    released_at: datetime | None = None,
    runtime_error_factory: WorkerRuntimeErrorFactory | None = None,
) -> WorkerTerminalEvidence:
    """Combine one worker receipt with authenticated durable terminal state.

    Artifact plans are deliberately supplied by the caller because only the
    host application knows which mounted files correspond to each result
    manifest.  Successful evidence requires one accepted publication plan for
    the exact manifest; failed/cancelled evidence cannot carry result data or
    artifact plans. A host runtime-error factory may classify failed runtime
    evidence; when omitted, the package uses the digest-only fallback.
    """

    if not isinstance(context, WorkerCompletionContext):
        raise TypeError("context must be a WorkerCompletionContext")
    if not isinstance(lookup, WorkerTerminalEvidenceLookup):
        raise TypeError("lookup must be a WorkerTerminalEvidenceLookup")
    if runtime_error_factory is not None and not callable(runtime_error_factory):
        raise TypeError("runtime_error_factory must be callable")
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
        plans = _validate_artifact_plans(manifest, plans)
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
        factory = runtime_error_factory or default_worker_failure_error
        error = factory(context, process_execution.runtime_result.state)
        if not isinstance(error, ApiError):
            raise TypeError("runtime_error_factory must return an ApiError")
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


def _validate_artifact_plans(
    manifest: RunResultManifest,
    plans: tuple[ArtifactPublicationPlan, ...],
) -> tuple[ArtifactPublicationPlan, ...]:
    """Require one exact publication plan for every manifest output artifact."""

    expected = {
        content_digest(artifact): (
            artifact.content_digest,
            artifact.storage_key,
            artifact.byte_length,
            artifact.retention_class,
        )
        for artifact in manifest.output_artifacts
    }
    observed: dict[str, ArtifactPublicationPlan] = {}
    for plan in plans:
        if plan.manifest_fingerprint not in expected:
            raise ValueError("artifact plan references an unknown result artifact")
        if plan.manifest_fingerprint in observed:
            raise ValueError("artifact plans must contain one plan per result artifact")
        if (
            plan.content_digest,
            plan.storage_key,
            plan.byte_length,
            plan.retention_class,
        ) != expected[plan.manifest_fingerprint]:
            raise ValueError("artifact plan does not match its result artifact")
        observed[plan.manifest_fingerprint] = plan
    if set(observed) != set(expected):
        raise ValueError("artifact plans must cover every result artifact")
    return tuple(observed[key] for key in sorted(observed))


def create_worker_terminal_evidence_resolver(
    lookup_loader: EvidenceLookup,
    artifact_plan_resolver: ArtifactPlanResolver,
    *,
    runtime_error_factory: WorkerRuntimeErrorFactory | None = None,
) -> Callable[[WorkerCompletionContext], Awaitable[WorkerTerminalEvidence]]:
    """Create the callback shape consumed by ``PostgresWorkerTerminalAdapter``.

    ``runtime_error_factory`` is intentionally injected rather than discovered
    from worker payloads, preserving application ownership of retry policy and
    typed error classification.
    """

    if not callable(lookup_loader):
        raise TypeError("lookup_loader must be callable")
    if not callable(artifact_plan_resolver):
        raise TypeError("artifact_plan_resolver must be callable")
    if runtime_error_factory is not None and not callable(runtime_error_factory):
        raise TypeError("runtime_error_factory must be callable")

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
        return build_worker_terminal_evidence(
            context,
            lookup,
            artifact_plans=plans,
            runtime_error_factory=runtime_error_factory,
        )

    return resolve


def create_sandbox_artifact_plan_resolver(
    publisher: SandboxArtifactPublisher,
) -> Callable[
    [WorkerCompletionContext, WorkerTerminalEvidenceLookup],
    Awaitable[tuple[ArtifactPublicationPlan, ...]],
]:
    """Map one mounted sandbox result to its verified publication plan.

    The current sandbox contract exposes one mounted ``/outputs/result`` file.
    Manifests with multiple output artifacts are rejected here so callers must
    supply an explicit multi-file mapping rather than accidentally publishing
    one file for several identities.
    """

    if not callable(getattr(publisher, "publish_sandbox_result", None)):
        raise TypeError("publisher must provide publish_sandbox_result")

    async def resolve(
        context: WorkerCompletionContext,
        lookup: WorkerTerminalEvidenceLookup,
    ) -> tuple[ArtifactPublicationPlan, ...]:
        if not isinstance(context, WorkerCompletionContext):
            raise TypeError("context must be a WorkerCompletionContext")
        if not isinstance(lookup, WorkerTerminalEvidenceLookup):
            raise TypeError("lookup must be a WorkerTerminalEvidenceLookup")
        manifest = lookup.inputs.manifest
        if manifest is None:
            return ()
        if len(manifest.output_artifacts) != 1:
            raise ValueError(
                "sandbox artifact resolver requires exactly one result output artifact"
            )
        process_execution = context.process.execution
        if process_execution is None or process_execution.nautilus_result is None:
            raise ValueError("sandbox artifact resolver requires Nautilus evidence")
        sandbox_result = process_execution.nautilus_result.sandbox_result
        if sandbox_result is None:
            raise ValueError("sandbox artifact resolver requires sandbox evidence")
        publication = await publisher.publish_sandbox_result(
            manifest,
            context.request.sandbox_plan,
            sandbox_result,
            committed_at=context.observed_at,
        )
        if not isinstance(publication, ArtifactPublicationResolution):
            raise TypeError("publisher returned an invalid artifact publication resolution")
        if publication.decision is ArtifactPublicationDecision.REJECT:
            raise ValueError(
                publication.rejection_reason or "sandbox artifact publication was rejected"
            )
        if publication.artifact_plan is None:
            raise ValueError("sandbox artifact publication omitted its verified plan")
        return (publication.artifact_plan,)

    return resolve


__all__ = [
    "ArtifactPlanResolver",
    "EvidenceLookup",
    "SandboxArtifactPublisher",
    "WorkerRuntimeErrorFactory",
    "build_worker_terminal_evidence",
    "create_sandbox_artifact_plan_resolver",
    "create_worker_terminal_evidence_resolver",
    "default_worker_failure_error",
]
