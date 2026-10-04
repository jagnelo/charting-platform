"""Owner-authenticated Nautilus OOS result construction at worker completion."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from app.strategy_lab_v2.allocation import ALLOCATION_DEFINITION_VERSION
from app.strategy_lab_v2.artifact_application import (
    ArtifactPublicationDecision,
    ArtifactPublicationResolution,
)
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.conformance import evaluate_engine_conformance
from app.strategy_lab_v2.contracts import ArtifactManifest, AttemptState
from app.strategy_lab_v2.nautilus_equity_trace import (
    NautilusAccountEquityTraceReference,
)
from app.strategy_lab_v2.nautilus_native_reports import NautilusNativeReportsReference
from app.strategy_lab_v2.nautilus_rebalance_schedule import NautilusRebalanceScheduleAudit
from app.strategy_lab_v2.nautilus_result_materialization import (
    materialize_nautilus_oos_run_result,
)
from app.strategy_lab_v2.nautilus_runner import (
    NautilusRunStatus,
    expected_native_equity_events,
)
from app.strategy_lab_v2.result_integrity import verify_run_result_artifacts
from app.strategy_lab_v2.result_materialization import (
    EngineResultEvidence,
    ResultMaterializationDecision,
    build_nautilus_result_provenance,
)
from app.strategy_lab_v2.result_publication import (
    ResultPublicationDecision,
    ResultPublicationPlan,
    plan_result_publication,
)
from app.strategy_lab_v2.runtime_execution import RuntimeExecutionPhase
from app.strategy_lab_v2.sandbox import (
    sandbox_account_equity_trace_path,
    sandbox_invocation_result_stream_path,
    sandbox_native_reports_path,
)
from app.strategy_lab_v2.trial_hydration import (
    NautilusTrialDomainHydrator,
)
from app.strategy_lab_v2.worker_evidence import (
    WorkerTerminalEvidenceInputs,
    WorkerTerminalEvidenceLookup,
)
from app.strategy_lab_v2.worker_evidence_resolution import (
    EvidenceLookup,
    WorkerRuntimeErrorFactory,
    build_worker_terminal_evidence,
)
from app.strategy_lab_v2.worker_service import WorkerCompletionContext
from app.strategy_lab_v2.worker_terminal_adapter import (
    PermanentWorkerTerminalEvidenceError,
    WorkerTerminalEvidence,
)


class ResultArtifactPublisher(Protocol):
    async def publish(
        self,
        manifest: ArtifactManifest,
        payload: bytes,
        *,
        committed_at: datetime,
    ) -> ArtifactPublicationResolution: ...

    async def publish_file(
        self,
        manifest: ArtifactManifest,
        source: str | Path,
        *,
        committed_at: datetime,
    ) -> ArtifactPublicationResolution: ...


def create_nautilus_oos_worker_terminal_evidence_resolver(
    lookup_loader: EvidenceLookup,
    artifact_publisher: ResultArtifactPublisher,
    domain_hydrator: NautilusTrialDomainHydrator,
    *,
    runtime_error_factory: WorkerRuntimeErrorFactory | None = None,
) -> Callable[[WorkerCompletionContext], Awaitable[WorkerTerminalEvidence]]:
    """Build canonical OOS evidence from one completed, authenticated attempt.

    The worker supplies only its immutable execution receipt. The owner-scoped
    hydrator supplies the domain graph, while exact conformance evidence is
    carried in the parent-owned worker request and checked against its plan.
    All native result bytes are reverified and published before the terminal
    writer can acknowledge the queue entry.
    """

    if not callable(lookup_loader):
        raise TypeError("lookup_loader must be callable")
    if not callable(getattr(artifact_publisher, "publish_file", None)):
        raise TypeError("artifact_publisher must expose publish_file")
    if not isinstance(domain_hydrator, NautilusTrialDomainHydrator):
        raise TypeError("domain_hydrator must be a NautilusTrialDomainHydrator")
    if runtime_error_factory is not None and not callable(runtime_error_factory):
        raise TypeError("runtime_error_factory must be callable or None")

    async def resolve(context: WorkerCompletionContext) -> WorkerTerminalEvidence:
        if not isinstance(context, WorkerCompletionContext):
            raise TypeError("context must be a WorkerCompletionContext")
        request = context.request
        attempt_id = request.admission.attempt_id
        loaded = lookup_loader(
            request_fingerprint=context.entry.request_fingerprint,
            attempt_id=attempt_id,
        )
        lookup = await loaded if inspect.isawaitable(loaded) else loaded
        if lookup is None:
            raise LookupError("worker terminal evidence was not found")
        try:
            if not isinstance(lookup, WorkerTerminalEvidenceLookup):
                raise TypeError("lookup_loader returned an invalid evidence lookup")
            if lookup.inputs.attempt_id != attempt_id:
                raise ValueError("durable evidence references a different attempt")
            process_execution = context.process.execution
            if process_execution is None or process_execution.runtime_result is None:
                raise ValueError("completed worker process omitted runtime evidence")
        except (TypeError, ValueError) as error:
            raise PermanentWorkerTerminalEvidenceError(
                "worker terminal inputs failed validation"
            ) from error
        if process_execution.runtime_result.state.phase is not RuntimeExecutionPhase.SUCCEEDED:
            try:
                evidence = build_worker_terminal_evidence(
                    context,
                    lookup,
                    runtime_error_factory=runtime_error_factory,
                )
                run_result = process_execution.nautilus_result
                if (
                    run_result is not None
                    and run_result.status is NautilusRunStatus.FAILED
                    and run_result.rebalance_schedule_audit is not None
                ):
                    audit = run_result.rebalance_schedule_audit
                    if audit.attempt_id != attempt_id:
                        raise ValueError("failed rebalance audit references a different attempt")
                    artifact_details = await _publish_rebalance_audit_diagnostic(
                        artifact_publisher,
                        audit,
                        committed_at=process_execution.runtime_result.state.updated_at,
                    )
                    if evidence.error is None:
                        raise ValueError("failed rebalance run is missing its terminal error")
                    details = dict(evidence.error.details)
                    existing_diagnostics = details.get("diagnostic_artifacts", [])
                    if not isinstance(existing_diagnostics, list | tuple) or any(
                        not isinstance(item, Mapping) for item in existing_diagnostics
                    ):
                        raise ValueError("terminal error diagnostics are invalid")
                    details["diagnostic_artifacts"] = [
                        *existing_diagnostics,
                        artifact_details,
                    ]
                    evidence = replace(
                        evidence,
                        error=replace(evidence.error, details=details),
                    )
                return evidence
            except (TypeError, ValueError) as error:
                raise PermanentWorkerTerminalEvidenceError(
                    "worker terminal inputs failed validation"
                ) from error

        try:
            manifest, publication, artifact_plans = await _materialize_successful_oos_result(
                context,
                lookup,
                artifact_publisher,
                domain_hydrator,
            )
            updated_inputs = _inputs_with_result(lookup.inputs, manifest, publication)
            updated_lookup = WorkerTerminalEvidenceLookup(lookup.binding, updated_inputs)
            return build_worker_terminal_evidence(
                context,
                updated_lookup,
                artifact_plans=artifact_plans,
                runtime_error_factory=runtime_error_factory,
            )
        except (TypeError, ValueError) as error:
            raise PermanentWorkerTerminalEvidenceError(
                "authoritative Nautilus result evidence failed validation"
            ) from error

    return resolve


async def _publish_rebalance_audit_diagnostic(
    artifact_publisher: ResultArtifactPublisher,
    audit: NautilusRebalanceScheduleAudit,
    *,
    committed_at: datetime,
) -> dict[str, object]:
    """Durably publish a failed-run audit and return its authenticated error reference."""

    if not isinstance(audit, NautilusRebalanceScheduleAudit):
        raise TypeError("audit must be a NautilusRebalanceScheduleAudit")
    publish = getattr(artifact_publisher, "publish", None)
    if not callable(publish):
        raise ValueError("artifact publisher cannot persist failed rebalance diagnostics")
    manifest = audit.artifact_manifest()
    publication = await publish(
        manifest,
        audit.artifact_bytes(),
        committed_at=committed_at,
    )
    if not isinstance(publication, ArtifactPublicationResolution):
        raise TypeError("artifact publisher returned an invalid diagnostic publication")
    if publication.decision is ArtifactPublicationDecision.REJECT:
        raise ValueError(
            publication.rejection_reason or "failed rebalance audit publication was rejected"
        )
    artifact_plan = publication.artifact_plan
    integrity = publication.storage.integrity
    if artifact_plan is None or integrity is None or not integrity.verified:
        raise ValueError("failed rebalance audit publication omitted verified artifact evidence")
    if (
        artifact_plan.manifest_fingerprint != content_digest(manifest)
        or artifact_plan.content_digest != manifest.content_digest
        or artifact_plan.storage_key != manifest.storage_key
        or artifact_plan.byte_length != manifest.byte_length
        or integrity.manifest_fingerprint != content_digest(manifest)
    ):
        raise ValueError("failed rebalance audit publication differs from its manifest")
    return {
        "schema": "strategy-lab.rebalance-diagnostic-artifact.v1",
        "attempt_id": audit.attempt_id,
        "audit_fingerprint": audit.fingerprint,
        "manifest_fingerprint": content_digest(manifest),
        "content_digest": manifest.content_digest,
        "storage_key": manifest.storage_key,
        "media_type": manifest.media_type,
        "schema_version": manifest.schema_version,
        "byte_length": manifest.byte_length,
        "retention_class": manifest.retention_class.value,
    }


async def _materialize_successful_oos_result(
    context: WorkerCompletionContext,
    lookup: WorkerTerminalEvidenceLookup,
    artifact_publisher: ResultArtifactPublisher,
    domain_hydrator: NautilusTrialDomainHydrator,
) -> tuple[Any, ResultPublicationPlan, tuple[Any, ...]]:
    request = context.request
    execution = context.process.execution
    if execution is None or execution.nautilus_result is None:
        raise ValueError("successful Nautilus process omitted its run result")
    if execution.runtime_result is None:
        raise ValueError("successful Nautilus process omitted its runtime receipt")
    run_result = execution.nautilus_result
    terminal_at = execution.runtime_result.state.updated_at
    if run_result.status is not NautilusRunStatus.SUCCEEDED or not run_result.authoritative:
        raise ValueError("official OOS results require an authoritative successful Nautilus run")
    if not request.execution_plan.authoritative:
        raise ValueError("official OOS results require an authoritative execution plan")
    conformance_evidence = request.conformance_evidence
    if conformance_evidence is None:
        raise ValueError("authoritative OOS results require exact conformance evidence")
    conformance_report = evaluate_engine_conformance(conformance_evidence)
    if request.runtime_preflight.isolation_report.accepted is not True:
        raise ValueError("official OOS results require accepted runtime isolation evidence")

    equity_reference = run_result.account_equity_trace
    reports_reference = run_result.native_reports
    if not isinstance(equity_reference, NautilusAccountEquityTraceReference):
        raise ValueError("successful Nautilus run omitted its verified account-equity trace")
    if not isinstance(reports_reference, NautilusNativeReportsReference):
        raise ValueError("successful Nautilus run omitted its native execution reports")
    if request.runtime_input_artifact.trial_binding is None:
        raise ValueError("official OOS result requires a bound immutable trial input")

    existing = lookup.inputs.manifest
    if existing is None:
        graph = await domain_hydrator.hydrate_attempt(
            principal=lookup.owner_id,
            attempt_resource_id=request.admission.attempt_id,
        )
        attempt = replace(
            graph.attempt,
            state=AttemptState.SUCCEEDED,
            updated_at=terminal_at,
        )
        trial = graph.trial
        strategy_packages = tuple(graph.packages.values())
        portfolio = graph.portfolio
        snapshot = graph.snapshot
    else:
        attempt = existing.attempt
        trial = existing.trial
        strategy_packages = existing.strategy_packages
        portfolio = existing.portfolio
        snapshot = existing.snapshot

    binding = request.runtime_input_artifact.trial_binding
    if (
        binding.attempt_id != attempt.attempt_id
        or binding.trial_fingerprint != trial.trial_id
        or binding.portfolio_fingerprint != portfolio.fingerprint
        or binding.snapshot_fingerprint != snapshot.fingerprint
    ):
        raise ValueError("authenticated trial graph differs from the executed worker input")
    schedule_audit = run_result.rebalance_schedule_audit
    if (portfolio.rebalance_policy is None) != (schedule_audit is None):
        raise ValueError("Nautilus rebalance policy and schedule audit must be present together")
    if schedule_audit is not None:
        if schedule_audit.attempt_id != attempt.attempt_id:
            raise ValueError("Nautilus rebalance audit references a different attempt")
        if not callable(getattr(artifact_publisher, "publish", None)):
            raise ValueError("artifact publisher cannot persist rebalance schedule evidence")
    if (
        request.execution_plan.trial_id != trial.trial_id
        or request.execution_plan.attempt_id != attempt.attempt_id
        or request.execution_plan.data_snapshot_fingerprint != snapshot.fingerprint
    ):
        raise ValueError("Nautilus execution plan differs from the authenticated trial graph")

    provenance = build_nautilus_result_provenance(
        request.execution_plan,
        conformance_evidence,
        conformance_report,
        request.sandbox_plan,
    )
    invocation_reference = run_result.invocation_result_stream
    schedule_audit_artifact = (
        schedule_audit.artifact_manifest() if schedule_audit is not None else None
    )
    output_artifacts = tuple(
        item
        for item in (
            None if invocation_reference is None else invocation_reference.artifact,
            schedule_audit_artifact,
        )
        if item is not None
    )
    result_artifacts = _unique_artifacts(
        (*output_artifacts, equity_reference.artifact, reports_reference.artifact)
    )
    dependencies = tuple(sorted(request.runtime_request.isolation_request.dependency_digests))
    dependency_catalog_digest = content_digest(
        {
            "schema": "strategy-lab.nautilus-dependency-catalog.v1",
            "package_fingerprint": request.runtime_request.package_fingerprint,
            "dependency_digests": dependencies,
        }
    )
    assumptions_digest = content_digest(
        {
            "schema": "strategy-lab.nautilus-execution-assumptions.v1",
            "execution_plan_fingerprint": request.execution_plan.fingerprint,
            "runtime_input_artifact_fingerprint": request.runtime_input_artifact.fingerprint,
            "runtime_profile_fingerprint": request.runtime_preflight.profile_fingerprint,
        }
    )
    evidence = EngineResultEvidence(
        trial_id=trial.trial_id,
        attempt_id=attempt.attempt_id,
        engine_name=request.execution_plan.engine_id,
        engine_version=request.execution_plan.engine_version,
        engine_build_digest=request.execution_plan.engine_build_digest,
        allocation_definition_version=ALLOCATION_DEFINITION_VERSION,
        dependency_catalog_digest=dependency_catalog_digest,
        assumptions_digest=assumptions_digest,
        metric_set_fingerprint=content_digest("nautilus-oos-metrics-pending"),
        artifact_content_digests=tuple(item.content_digest for item in result_artifacts),
        observed_at=terminal_at,
        authoritative=run_result.authoritative,
        engine_provenance=provenance,
    )

    equity_path = sandbox_account_equity_trace_path(request.sandbox_plan)
    reports_path = sandbox_native_reports_path(request.sandbox_plan)
    if equity_path is None or reports_path is None:
        raise ValueError("Nautilus OOS output mounts are missing")
    materialized = materialize_nautilus_oos_run_result(
        trial,
        attempt,
        strategy_packages,
        portfolio,
        snapshot,
        evidence,
        equity_reference,
        equity_path,
        expected_native_equity_events(request.runtime_input_artifact, request.sandbox_plan),
        reports_reference,
        reports_path,
        output_artifacts,
        created_at=existing.created_at if existing is not None else terminal_at,
        existing=existing,
    )
    if (
        materialized.decision
        not in {
            ResultMaterializationDecision.MATERIALIZE,
            ResultMaterializationDecision.REPLAY_EXISTING,
        }
        or materialized.manifest is None
    ):
        raise ValueError(materialized.rejection_reason or "Nautilus OOS result was rejected")
    result = materialized.manifest

    artifact_sources = _artifact_sources(
        tuple(
            artifact
            for artifact in result.output_artifacts
            if schedule_audit_artifact is None or artifact != schedule_audit_artifact
        ),
        equity_reference,
        reports_reference,
        invocation_reference,
        request.sandbox_plan,
    )
    artifact_plans = []
    integrity_receipts = []
    for artifact in result.output_artifacts:
        if schedule_audit_artifact is not None and artifact == schedule_audit_artifact:
            assert schedule_audit is not None
            publication_result = await artifact_publisher.publish(
                artifact,
                schedule_audit.artifact_bytes(),
                committed_at=terminal_at,
            )
        else:
            publication_result = await artifact_publisher.publish_file(
                artifact,
                artifact_sources[artifact.content_digest],
                committed_at=terminal_at,
            )
        if not isinstance(publication_result, ArtifactPublicationResolution):
            raise TypeError("artifact publisher returned an invalid publication resolution")
        if publication_result.decision is ArtifactPublicationDecision.REJECT:
            raise ValueError(
                publication_result.rejection_reason or "Nautilus output artifact was rejected"
            )
        if publication_result.artifact_plan is None:
            raise ValueError("Nautilus output publication omitted its artifact plan")
        integrity = publication_result.storage.integrity
        if integrity is None or not integrity.verified:
            raise ValueError("Nautilus output publication omitted verified byte integrity")
        artifact_plans.append(publication_result.artifact_plan)
        integrity_receipts.append(integrity)

    result_integrity = verify_run_result_artifacts(result, tuple(integrity_receipts))
    prior_publications = tuple(
        item
        for item in lookup.inputs.publications
        if item.result_fingerprint == result.fingerprint
        and item.decision is not ResultPublicationDecision.REJECT
    )
    if len(prior_publications) > 1:
        raise ValueError("result has multiple accepted publication plans")
    if prior_publications:
        publication = prior_publications[0]
    else:
        publication = plan_result_publication(
            result,
            conformance_evidence,
            conformance_report,
            request.runtime_preflight.isolation_report,
            result_integrity,
            execution_plan=request.execution_plan,
        )
    if publication.decision is ResultPublicationDecision.REJECT:
        raise ValueError(
            "Nautilus OOS result publication rejected: " + ", ".join(publication.rejection_reasons)
        )
    return result, publication, tuple(artifact_plans)


def _artifact_sources(
    artifacts: Sequence[ArtifactManifest],
    equity_reference: NautilusAccountEquityTraceReference,
    reports_reference: NautilusNativeReportsReference,
    invocation_reference: Any,
    sandbox_plan: Any,
) -> dict[str, Path]:
    sources: dict[str, Path] = {}
    equity_path = sandbox_account_equity_trace_path(sandbox_plan)
    reports_path = sandbox_native_reports_path(sandbox_plan)
    if equity_path is None or reports_path is None:
        raise ValueError("Nautilus OOS output mounts are missing")
    sources[equity_reference.artifact.content_digest] = equity_path
    sources[reports_reference.artifact.content_digest] = reports_path
    if invocation_reference is not None:
        invocation_path = sandbox_invocation_result_stream_path(sandbox_plan)
        if invocation_path is None:
            raise ValueError("Nautilus invocation-result stream mount is missing")
        sources[invocation_reference.artifact.content_digest] = invocation_path
    expected = {item.content_digest for item in artifacts}
    if set(sources) != expected:
        raise ValueError(
            "result manifest contains an artifact without an authenticated worker path"
        )
    return sources


def _unique_artifacts(artifacts: Sequence[ArtifactManifest]) -> tuple[ArtifactManifest, ...]:
    by_digest: dict[str, ArtifactManifest] = {}
    for artifact in artifacts:
        previous = by_digest.get(artifact.content_digest)
        if previous is not None and previous != artifact:
            raise ValueError("Nautilus output artifact digest has conflicting manifests")
        by_digest[artifact.content_digest] = artifact
    return tuple(by_digest[key] for key in sorted(by_digest))


def _inputs_with_result(
    inputs: WorkerTerminalEvidenceInputs,
    manifest: Any,
    publication: ResultPublicationPlan,
) -> WorkerTerminalEvidenceInputs:
    publications = list(inputs.publications)
    if not any(item.fingerprint == publication.fingerprint for item in publications):
        publications.append(publication)
    return replace(
        inputs,
        manifest=manifest,
        publications=tuple(sorted(publications, key=lambda item: item.fingerprint)),
    )


__all__ = ["create_nautilus_oos_worker_terminal_evidence_resolver"]
