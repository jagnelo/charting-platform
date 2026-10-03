"""Host-side composition of one immutable Nautilus trial worker handoff."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.strategy_lab_v2.admission import (
    ExecutionAdmissionDecision,
    ExecutionAdmissionLedger,
    resolve_execution_admission,
)
from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.conformance import (
    EngineConformanceEvidence,
    EngineConformanceReport,
)
from app.strategy_lab_v2.engine_execution import (
    EngineExecutionDecision,
    NautilusExecutionScope,
    plan_nautilus_execution,
)
from app.strategy_lab_v2.execution import ExecutionAuthorization
from app.strategy_lab_v2.execution_orchestration import plan_execution_orchestration
from app.strategy_lab_v2.lease_observations import LeaseObservationState
from app.strategy_lab_v2.lifecycle import AttemptLeaseStatus
from app.strategy_lab_v2.nautilus_trial_materializer import NautilusTrialRuntimeEvidence
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile
from app.strategy_lab_v2.runtime_execution import new_runtime_execution_state
from app.strategy_lab_v2.sandbox import build_nautilus_runtime_sandbox_command
from app.strategy_lab_v2.worker_process import WorkerExecutionRequest
from app.strategy_lab_v2.workers import WorkerKind, WorkerPoolState


def build_nautilus_trial_worker_request(
    runtime_evidence: NautilusTrialRuntimeEvidence,
    authorization: ExecutionAuthorization,
    *,
    artifact_store: LocalArtifactStore,
    runtime_profile: RuntimeIsolationProfile,
    worker_pool: WorkerPoolState,
    admission_ledger: ExecutionAdmissionLedger,
    reservation_id: str,
    lease_state: LeaseObservationState,
    conformance_evidence: EngineConformanceEvidence,
    conformance_report: EngineConformanceReport,
    image_name: str,
    output_path: str | Path,
    now: datetime,
    execution_scope: NautilusExecutionScope = NautilusExecutionScope.BACKTEST_AUTHORITATIVE,
    requested_authoritative: bool = True,
    docker_binary: str = "docker",
) -> WorkerExecutionRequest:
    """Derive request, admission, sandbox, engine plan, and handoff from one trial.

    The caller supplies live host evidence (worker pool, lease, exact conformance
    result, and immutable artifact store). No provider lookup or Nautilus import
    occurs here. Run this synchronously in the dedicated preparation process,
    not on FastAPI or a worker heartbeat loop.
    """

    if not isinstance(runtime_evidence, NautilusTrialRuntimeEvidence):
        raise TypeError("runtime_evidence must be NautilusTrialRuntimeEvidence")
    if not isinstance(authorization, ExecutionAuthorization):
        raise TypeError("authorization must be ExecutionAuthorization")
    if not isinstance(artifact_store, LocalArtifactStore):
        raise TypeError("artifact_store must be LocalArtifactStore")
    if not isinstance(runtime_profile, RuntimeIsolationProfile):
        raise TypeError("runtime_profile must be RuntimeIsolationProfile")
    if not isinstance(worker_pool, WorkerPoolState):
        raise TypeError("worker_pool must be WorkerPoolState")
    if not isinstance(admission_ledger, ExecutionAdmissionLedger):
        raise TypeError("admission_ledger must be ExecutionAdmissionLedger")
    if not isinstance(lease_state, LeaseObservationState):
        raise TypeError("lease_state must be LeaseObservationState")
    if not isinstance(conformance_evidence, EngineConformanceEvidence):
        raise TypeError("conformance_evidence must be EngineConformanceEvidence")
    if not isinstance(conformance_report, EngineConformanceReport):
        raise TypeError("conformance_report must be EngineConformanceReport")
    if not isinstance(execution_scope, NautilusExecutionScope):
        raise TypeError("execution_scope must be NautilusExecutionScope")
    if execution_scope not in {
        NautilusExecutionScope.BACKTEST_AUTHORITATIVE,
        NautilusExecutionScope.BACKTEST_COMPATIBILITY,
    }:
        raise ValueError("Nautilus trial worker requests require a backtest execution scope")
    if not isinstance(requested_authoritative, bool):
        raise TypeError("requested_authoritative must be a boolean")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("worker request time must be timezone-aware")
    now = now.astimezone(UTC)

    materialized = runtime_evidence.materialized_input
    graph = materialized.graph
    runtime_request = runtime_evidence.runtime_request
    runtime_preflight = runtime_evidence.runtime_preflight
    runtime_artifact = materialized.assembly.runtime_input_artifact
    if (
        authorization.attempt_id != graph.attempt.attempt_id
        or authorization.trial_id != graph.trial.trial_id
        or authorization.trial_preflight_fingerprint != graph.trial.preflight_fingerprint
        or authorization.source_digest != runtime_request.source_digest
    ):
        raise ValueError("execution authorization differs from the materialized trial graph")
    if runtime_profile.fingerprint != runtime_request.runtime_profile_fingerprint:
        raise ValueError("runtime profile differs from materialized runtime evidence")
    if worker_pool.profile.kind is not WorkerKind.BACKTEST:
        raise ValueError("Nautilus trial requests require a backtest worker")
    if worker_pool.profile.worker_id != authorization.lease_worker_id:
        raise ValueError("worker pool differs from the execution authorization lease")
    if worker_pool.profile.runtime_profile_fingerprint != runtime_profile.fingerprint:
        raise ValueError("worker pool runtime differs from the pinned runtime profile")
    if (
        not worker_pool.profile.isolation_required
        or not worker_pool.profile.engine_disposal_required
    ):
        raise ValueError("Nautilus trial workers require isolation and engine disposal")
    if conformance_evidence.engine_id.lower() != "nautilus":
        raise ValueError("Nautilus trial workers require Nautilus conformance evidence")
    if (
        conformance_evidence.release_pin is not None
        and conformance_evidence.release_pin.runtime_image_digest
        != runtime_profile.runtime_image_digest
    ):
        raise ValueError("conformance pin differs from the trial runtime image")

    lease = lease_state.lease
    if (
        lease.attempt_id != authorization.attempt_id
        or lease.worker_id != authorization.lease_worker_id
        or lease.lease_id != authorization.lease_id
    ):
        raise ValueError("worker lease differs from the execution authorization")
    if lease.status_at(now) is not AttemptLeaseStatus.ACTIVE:
        raise ValueError("execution authorization lease is not active")

    admission = resolve_execution_admission(
        admission_ledger,
        authorization,
        runtime_request,
        runtime_preflight,
        worker_pool,
        reservation_id=reservation_id,
        now=now,
    )
    if (
        admission.decision
        not in {
            ExecutionAdmissionDecision.ADMIT,
            ExecutionAdmissionDecision.REPLAY_EXISTING,
        }
        or admission.admission is None
    ):
        raise ValueError(admission.rejection_reason or "worker admission was not accepted")

    context_stream = runtime_artifact.context_stream
    native_event_stream = runtime_artifact.native_event_stream
    result_stream_path = None
    if context_stream is not None:
        output = Path(output_path)
        result_stream_path = output.with_name(f"{output.name}.invocations.ndjson")
    sandbox_plan = build_nautilus_runtime_sandbox_command(
        runtime_request,
        runtime_profile,
        image_name=image_name,
        input_bundle_path=artifact_store.path_for(runtime_artifact.artifact.storage_key),
        output_path=output_path,
        expected_version=conformance_evidence.engine_version,
        snapshot_fingerprint=graph.snapshot.fingerprint,
        context_stream_path=(
            artifact_store.path_for(context_stream.artifact.storage_key)
            if context_stream is not None
            else None
        ),
        context_stream_digest=(
            context_stream.artifact.content_digest if context_stream is not None else None
        ),
        native_event_stream_path=(
            artifact_store.path_for(native_event_stream.artifact.storage_key)
            if native_event_stream is not None
            else None
        ),
        native_event_stream_digest=(
            native_event_stream.artifact.content_digest if native_event_stream is not None else None
        ),
        invocation_result_stream_path=result_stream_path,
    )
    execution_plan = plan_nautilus_execution(
        authorization,
        runtime_preflight,
        conformance_evidence,
        conformance_report,
        sandbox_plan,
        data_snapshot_fingerprint=graph.snapshot.fingerprint,
        requested_authoritative=requested_authoritative,
        execution_scope=execution_scope,
    )
    if execution_plan.decision is not EngineExecutionDecision.READY:
        raise ValueError(
            "Nautilus execution plan rejected: " + ", ".join(execution_plan.rejection_reasons)
        )
    runtime_state = new_runtime_execution_state(
        runtime_preflight,
        attempt_id=authorization.attempt_id,
        output_limit_bytes=runtime_profile.output_limit_bytes,
        accepted_at=now,
    )
    orchestration_plan = plan_execution_orchestration(
        authorization,
        admission.admission,
        runtime_request,
        runtime_preflight,
        runtime_state,
        sandbox_plan,
        execution_plan,
    )
    if not orchestration_plan.accepted:
        raise ValueError(
            "Nautilus worker orchestration rejected: "
            + ", ".join(orchestration_plan.rejection_reasons)
        )
    return WorkerExecutionRequest(
        orchestration_plan,
        authorization,
        admission.admission,
        runtime_request,
        runtime_preflight,
        runtime_state,
        sandbox_plan,
        execution_plan,
        admission.pool,
        lease_state,
        now,
        now,
        runtime_input_artifact=runtime_artifact,
        docker_binary=docker_binary,
    )


__all__ = ["build_nautilus_trial_worker_request"]
