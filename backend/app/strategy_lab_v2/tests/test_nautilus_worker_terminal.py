from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pandas as pd  # type: ignore[import-untyped]
import pytest

import app.strategy_lab_v2.nautilus_worker_terminal as terminal_module
from app.strategy_lab_v2.admission import ExecutionAdmission, ExecutionAdmissionRequest
from app.strategy_lab_v2.artifact_application import LocalArtifactPublicationService
from app.strategy_lab_v2.artifact_commit import ArtifactCommitLedger, finalize_artifact_commit
from app.strategy_lab_v2.artifact_publication import ArtifactPublicationAction
from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.conformance import (
    NAUTILUS_V2_RC_PACKAGE_VERSION,
    NAUTILUS_V2_RC_RELEASE_TAG,
    NAUTILUS_V2_RC_WHEEL_SHA256,
    ConformanceCheck,
    EngineConformanceEvidence,
    EngineReleaseChannel,
    NautilusReleasePin,
    evaluate_engine_conformance,
)
from app.strategy_lab_v2.contracts import EvaluationWindow, ScientificTrial
from app.strategy_lab_v2.dispatch_payload import DispatchPayload
from app.strategy_lab_v2.engine_execution import (
    EngineExecutionDecision,
    NautilusExecutionPlan,
    NautilusExecutionScope,
)
from app.strategy_lab_v2.execution import ExecutionAuthorization
from app.strategy_lab_v2.execution_orchestration import plan_execution_orchestration
from app.strategy_lab_v2.lease_observations import (
    LeaseObservationDecision,
    LeaseObservationState,
    apply_lease_observation,
)
from app.strategy_lab_v2.lifecycle import ExecutionAttemptLease
from app.strategy_lab_v2.nautilus_equity_trace import NautilusAccountEquityTraceWriter
from app.strategy_lab_v2.nautilus_native_reports import NautilusNativeReportsWriter
from app.strategy_lab_v2.nautilus_runner import (
    NautilusRunResult,
    NautilusRunStatus,
    expected_native_equity_events,
)
from app.strategy_lab_v2.nautilus_runtime_bundle import load_materialized_nautilus_runtime_bundle
from app.strategy_lab_v2.nautilus_trial_materializer import (
    NautilusTrialMarketContext,
    NautilusTrialRuntimeInputMaterializer,
    build_nautilus_trial_runtime_evidence,
)
from app.strategy_lab_v2.nautilus_worker_terminal import (
    create_nautilus_oos_worker_terminal_evidence_resolver,
)
from app.strategy_lab_v2.outcomes import ExecutionOutcome, OutcomeStatus, apply_outcome_update
from app.strategy_lab_v2.postgres_commands import ExecutionCommandContext
from app.strategy_lab_v2.postgres_execution_state import (
    StateMutationDecision,
    StateMutationResolution,
)
from app.strategy_lab_v2.postgres_runtime_execution import (
    RuntimeStateDecision,
    RuntimeStateResolution,
)
from app.strategy_lab_v2.postgres_worker_state import (
    WorkerCapacityDecision,
    WorkerCapacityResolution,
)
from app.strategy_lab_v2.progress import ExecutionProgressState, ProgressPhase
from app.strategy_lab_v2.progress_checkpoint import (
    ProgressCheckpoint,
    ProgressCheckpointDecision,
    apply_progress_checkpoint,
)
from app.strategy_lab_v2.redis_transport import RedisStreamEntry
from app.strategy_lab_v2.result_completion import ResultCompletionLedger, finalize_execution_result
from app.strategy_lab_v2.result_publication import ResultPublicationDecision
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile
from app.strategy_lab_v2.runtime_execution import new_runtime_execution_state
from app.strategy_lab_v2.runtime_result_adapter import materialize_nautilus_result
from app.strategy_lab_v2.sandbox import (
    build_nautilus_runtime_sandbox_command,
    sandbox_account_equity_trace_path,
    sandbox_memory_limit_bytes,
    sandbox_native_reports_path,
)
from app.strategy_lab_v2.sandbox_execution import SandboxRunResult, SandboxRunStatus
from app.strategy_lab_v2.strategy_package_resolution import StrategyPackageArtifactResolver
from app.strategy_lab_v2.submissions import SubmissionReceipt, SubmissionRequest
from app.strategy_lab_v2.tests.test_nautilus_trial_assembly import (
    BASE,
    JsonFrozenSeriesDecoder,
)
from app.strategy_lab_v2.tests.test_nautilus_trial_materializer import _build_inputs
from app.strategy_lab_v2.tests.test_trial_hydration import MemoryDomainReader
from app.strategy_lab_v2.trial_hydration import NautilusTrialDomainHydrator
from app.strategy_lab_v2.worker_consumer import WorkerHandleDecision
from app.strategy_lab_v2.worker_evidence import (
    WorkerSubmissionBinding,
    WorkerTerminalEvidenceInputs,
    WorkerTerminalEvidenceLookup,
)
from app.strategy_lab_v2.worker_execution import (
    WorkerExecutionDecision,
    WorkerExecutionResolution,
)
from app.strategy_lab_v2.worker_process import (
    WorkerExecutionRequest,
    WorkerProcessDecision,
    WorkerProcessResolution,
)
from app.strategy_lab_v2.worker_service import WorkerCompletionContext
from app.strategy_lab_v2.worker_settlement import WorkerSettlementLedger
from app.strategy_lab_v2.worker_terminal_adapter import (
    PostgresWorkerTerminalAdapter,
    WorkerTerminalEvidence,
)
from app.strategy_lab_v2.workers import (
    WorkerKind,
    WorkerPoolState,
    WorkerProfile,
    WorkerReservation,
    release_worker_slot,
)

NOW = datetime(2024, 1, 2, 14, 31, tzinfo=UTC)


class _MemoryCommitter:
    def __init__(self) -> None:
        self.ledger = ArtifactCommitLedger()

    async def load_ledger(self) -> ArtifactCommitLedger:
        return self.ledger

    async def finalize(self, plan, *, committed_at):
        resolution = finalize_artifact_commit(self.ledger, plan, committed_at=committed_at)
        self.ledger = resolution.ledger
        return resolution


def _runtime_setup(tmp_path: Path):
    values, graph, source_store = _build_inputs(tmp_path)
    trial = graph.trial
    trial = ScientificTrial.create(
        experiment_fingerprint=trial.experiment_fingerprint,
        snapshot_fingerprint=trial.snapshot_fingerprint,
        preflight_report=trial.preflight_report,
        parameter_set=trial.parameter_set,
        scenario=trial.scenario,
        seed=trial.seed,
        randomization=trial.randomization,
        evaluation_window=EvaluationWindow(
            start=BASE - timedelta(hours=1),
            end=BASE + timedelta(days=3),
            purpose="out_of_sample",
        ),
    )
    graph = replace(
        graph,
        trial=trial,
        attempt=replace(graph.attempt, trial_id=trial.trial_id),
    )
    materializer = NautilusTrialRuntimeInputMaterializer(
        artifact_store=source_store,
        strategy_package_resolver=StrategyPackageArtifactResolver(
            source_store,
            runtime_abi="worker-abi-v1",
        ),
        series_decoder=JsonFrozenSeriesDecoder(),
    )
    materialized = materializer.materialize(
        graph=graph,
        market_context=NautilusTrialMarketContext(values["instruments"], values["venue"]),
    )
    profile = RuntimeIsolationProfile(
        runtime_image_digest=content_digest("nautilus-rc5-test-image"),
        runtime_abi="worker-abi-v1",
        allowed_dependency_digests=frozenset(
            dependency.artifact_digest for dependency in graph.strategies[0].dependencies
        ),
    )
    runtime = build_nautilus_trial_runtime_evidence(
        materialized,
        profile,
        request_id=content_digest("terminal-test-request"),
        submitted_at=BASE,
    )
    runtime_input = materialized.assembly.runtime_input_artifact
    context_reference = runtime_input.context_stream
    assert context_reference is not None
    sandbox = build_nautilus_runtime_sandbox_command(
        runtime.runtime_request,
        profile,
        image_name="nautilus-strategy-runtime",
        input_bundle_path=source_store.path_for(runtime_input.artifact.storage_key),
        output_path=tmp_path / "runtime-result.json",
        expected_version=NAUTILUS_V2_RC_PACKAGE_VERSION,
        snapshot_fingerprint=graph.snapshot.fingerprint,
        context_stream_path=source_store.path_for(context_reference.artifact.storage_key),
        context_stream_digest=context_reference.artifact.content_digest,
        native_event_stream_path=(
            source_store.path_for(runtime_input.native_event_stream.artifact.storage_key)
            if runtime_input.native_event_stream is not None
            else None
        ),
        native_event_stream_digest=(
            runtime_input.native_event_stream.artifact.content_digest
            if runtime_input.native_event_stream is not None
            else None
        ),
        invocation_result_stream_path=tmp_path / "invocations.jsonl",
        account_equity_trace_path=tmp_path / "account-equity.parquet",
        native_reports_path=tmp_path / "native-reports.parquet",
    )
    pin = NautilusReleasePin(
        package_version=NAUTILUS_V2_RC_PACKAGE_VERSION,
        release_tag=NAUTILUS_V2_RC_RELEASE_TAG,
        source_digest=content_digest("nautilus-rc5-source"),
        wheel_digest=NAUTILUS_V2_RC_WHEEL_SHA256,
        runtime_image_digest=profile.runtime_image_digest,
        python_version="3.12.11",
        rust_version="1.88.0",
        legacy_runtime_isolated=True,
    )
    checks = frozenset(
        check
        for check in ConformanceCheck
        if check is not ConformanceCheck.FORWARD_EVENT_TAPE_PARITY
    )
    conformance_evidence = EngineConformanceEvidence(
        engine_id="nautilus",
        engine_version=NAUTILUS_V2_RC_PACKAGE_VERSION,
        build_digest=content_digest("nautilus-rc5-build"),
        release_channel=EngineReleaseChannel.RELEASE_CANDIDATE,
        fixture_digest=content_digest("four-backtest-conformance-fixtures"),
        passed_checks=checks,
        tested_at=BASE,
        release_pin=pin,
    )
    conformance = evaluate_engine_conformance(conformance_evidence)

    state = new_runtime_execution_state(
        runtime.runtime_preflight,
        attempt_id=graph.attempt.attempt_id,
        output_limit_bytes=profile.output_limit_bytes,
        accepted_at=BASE,
    )
    authorization = ExecutionAuthorization(
        trial_id=graph.trial.trial_id,
        attempt_id=graph.attempt.attempt_id,
        source_digest=runtime.runtime_request.source_digest,
        trial_preflight_fingerprint=graph.trial.preflight_report.fingerprint,
        capability_preflight_fingerprint=graph.snapshot.capability_contract_digest,
        lease_id="lease-terminal-test",
        lease_worker_id="worker-terminal-test",
        authorized_at=BASE,
        authoritative=True,
    )
    worker_profile = WorkerProfile("worker-terminal-test", WorkerKind.BACKTEST, profile.fingerprint)
    reservation_id = content_digest("terminal-test-reservation")
    admission_request = ExecutionAdmissionRequest(
        authorization.fingerprint,
        runtime.runtime_request.fingerprint,
        graph.attempt.attempt_id,
        worker_profile.worker_id,
        WorkerKind.BACKTEST,
        profile.fingerprint,
        reservation_id,
        BASE,
    )
    admission = ExecutionAdmission(
        admission_request.fingerprint,
        authorization.fingerprint,
        runtime.runtime_request.fingerprint,
        graph.attempt.attempt_id,
        worker_profile.worker_id,
        WorkerKind.BACKTEST,
        profile.fingerprint,
        reservation_id,
        BASE,
        True,
    )
    execution_plan = NautilusExecutionPlan(
        trial_id=graph.trial.trial_id,
        attempt_id=graph.attempt.attempt_id,
        data_snapshot_fingerprint=graph.snapshot.fingerprint,
        engine_id="nautilus",
        engine_version=NAUTILUS_V2_RC_PACKAGE_VERSION,
        engine_build_digest=conformance_evidence.build_digest,
        authorization_fingerprint=authorization.fingerprint,
        runtime_preflight_fingerprint=runtime.runtime_preflight.fingerprint,
        conformance_report_fingerprint=conformance.fingerprint,
        sandbox_plan_fingerprint=sandbox.fingerprint,
        decision=EngineExecutionDecision.READY,
        authoritative=True,
        execution_scope=NautilusExecutionScope.BACKTEST_AUTHORITATIVE,
    )
    orchestration = plan_execution_orchestration(
        authorization,
        admission,
        runtime.runtime_request,
        runtime.runtime_preflight,
        state,
        sandbox,
        execution_plan,
    )
    assert orchestration.accepted
    worker_pool = WorkerPoolState(
        worker_profile,
        (
            WorkerReservation(
                reservation_id,
                worker_profile.worker_id,
                WorkerKind.BACKTEST,
                graph.attempt.attempt_id,
                BASE,
            ),
        ),
    )
    lease = ExecutionAttemptLease(
        graph.attempt.attempt_id,
        worker_profile.worker_id,
        authorization.lease_id,
        BASE,
        BASE,
        BASE + timedelta(minutes=2),
    )
    request = WorkerExecutionRequest(
        orchestration,
        authorization,
        admission,
        runtime.runtime_request,
        runtime.runtime_preflight,
        state,
        sandbox,
        execution_plan,
        worker_pool,
        LeaseObservationState(lease),
        BASE,
        BASE,
        runtime_input_artifact=runtime_input,
        conformance_evidence=conformance_evidence,
        docker_binary="unused-in-test",
    )
    return graph, source_store, request, conformance_evidence


def _successful_context_and_lookup(tmp_path: Path):
    graph, source_store, request, _conformance_evidence = _runtime_setup(tmp_path)
    sandbox = request.sandbox_plan
    runtime_input = request.runtime_input_artifact
    bundle = load_materialized_nautilus_runtime_bundle(
        runtime_input,
        source_store,
        max_input_bytes=max(1, sandbox_memory_limit_bytes(sandbox) // 8),
    )
    engine_input = json.loads(bundle.wire_bytes)["engine_input"]
    expected_events = tuple(expected_native_equity_events(runtime_input, sandbox))
    assert expected_events

    equity_path = sandbox_account_equity_trace_path(sandbox)
    reports_path = sandbox_native_reports_path(sandbox)
    assert equity_path is not None and reports_path is not None
    equity_writer = NautilusAccountEquityTraceWriter(
        equity_path,
        engine_input=engine_input,
        portfolio=engine_input["portfolio"],
    )
    for index, item in enumerate(expected_events):
        event = item.get("event", item)
        equity_writer.write(
            event_id=event["event_id"],
            event_time_ns=event["event_time_ns"],
            event_index=index,
            source_sequence=event["sequence"],
            account_equity=Decimal("100000") + Decimal(index * 10),
            account_cash_balance=Decimal("100000"),
        )
    equity_reference = equity_writer.finish()

    report_writer = NautilusNativeReportsWriter(
        reports_path,
        engine_input=engine_input,
        portfolio={"fingerprint": graph.portfolio.fingerprint},
    )
    first_event = expected_events[0].get("event", expected_events[0])
    report_writer.write_reports(
        {
            "account": pd.DataFrame([{"currency": "USD", "total": "100000"}]),
            "fills": pd.DataFrame(
                [{"ts_event": first_event["event_time_ns"], "commission": "2.00 USD"}]
            ),
            "orders": pd.DataFrame([{"ts_init": first_event["event_time_ns"]}]),
            "positions": pd.DataFrame(columns=["ts_opened", "ts_closed", "realized_pnl"]),
        }
    )
    reports_reference = report_writer.finish()
    terminal_at = NOW
    sandbox_result = SandboxRunResult(
        plan_fingerprint=sandbox.fingerprint,
        request_fingerprint=request.runtime_request.fingerprint,
        status=SandboxRunStatus.SUCCEEDED,
        exit_code=0,
        stdout_digest=content_digest("stdout"),
        stderr_digest=content_digest("stderr"),
        stdout_bytes=0,
        stderr_bytes=0,
    )
    run_result = NautilusRunResult(
        request.execution_plan.fingerprint,
        sandbox.fingerprint,
        NautilusRunStatus.SUCCEEDED,
        True,
        sandbox_result=sandbox_result,
        account_equity_trace=equity_reference,
        native_reports=reports_reference,
    )
    runtime_result = materialize_nautilus_result(
        request.runtime_state,
        request.execution_plan,
        sandbox,
        run_result,
        observed_at=terminal_at,
    )
    worker_execution = WorkerExecutionResolution(
        WorkerExecutionDecision.SUCCEEDED,
        request.orchestration_plan,
        run_result,
        runtime_result,
    )
    process = WorkerProcessResolution(
        request.request_fingerprint,
        WorkerProcessDecision.COMPLETED,
        execution=worker_execution,
        process_id=9001,
    )
    payload = DispatchPayload.from_mapping({"attempt_id": graph.attempt.attempt_id})
    entry = RedisStreamEntry(
        "strategy-lab:v2:stream:backtest",
        "1-0",
        content_digest("terminal-test-message"),
        graph.attempt.attempt_id,
        payload.payload_digest,
        request.request_fingerprint,
    )
    context = WorkerCompletionContext(entry, request, process, NOW + timedelta(seconds=5))

    receipt = SubmissionReceipt(
        SubmissionRequest(
            "terminal-test-idempotency-key",
            "backtest",
            graph.attempt.attempt_id,
            content_digest("terminal-test-submission"),
            BASE,
        ),
        BASE,
    )
    outcome = ExecutionOutcome(
        receipt.submission_id,
        graph.attempt.attempt_id,
        1,
        OutcomeStatus.ACCEPTED,
        BASE,
    )
    progress = ExecutionProgressState(
        graph.attempt.attempt_id,
        1,
        ProgressPhase.RUNNING,
        0,
        1,
        False,
        BASE,
    )
    lookup = WorkerTerminalEvidenceLookup(
        WorkerSubmissionBinding("owner-terminal-test", receipt),
        WorkerTerminalEvidenceInputs(
            graph.attempt.attempt_id,
            receipt,
            ExecutionCommandContext(outcome, progress),
            None,
            (),
        ),
    )
    hydrator_values = {
        "attempt": graph.attempt,
        "trial": graph.trial,
        "experiment": graph.experiment,
        "portfolio": graph.portfolio,
        "snapshot": graph.snapshot,
        "strategy_manifest": SimpleNamespace(strategy=graph.strategies[0]),
        "strategy_package": graph.packages[graph.strategies[0].fingerprint],
    }
    reader = MemoryDomainReader(hydrator_values, owner="owner-terminal-test")
    publisher = LocalArtifactPublicationService(
        LocalArtifactStore(tmp_path / "published-artifacts"),
        _MemoryCommitter(),
    )
    resolver = create_nautilus_oos_worker_terminal_evidence_resolver(
        lambda **_kwargs: lookup,
        publisher,
        NautilusTrialDomainHydrator(reader),
    )
    return context, lookup, resolver, publisher


def _terminal_writer(resolver) -> PostgresWorkerTerminalAdapter:
    placeholder = cast(Any, object())
    return PostgresWorkerTerminalAdapter(
        resolver,
        runtime_execution=placeholder,
        execution_state=placeholder,
        execution_summaries=placeholder,
        result_publication=placeholder,
        result_completion=placeholder,
        result_materialization=placeholder,
        metrics=placeholder,
        worker_state=placeholder,
        settlements=placeholder,
    )


@pytest.mark.asyncio
async def test_successful_worker_receipt_materializes_and_publishes_rc5_backtest(tmp_path):
    context, _lookup, resolver, publisher = _successful_context_and_lookup(tmp_path)

    evidence = await resolver(context)

    assert isinstance(evidence, WorkerTerminalEvidence)
    assert evidence.principal == "owner-terminal-test"
    assert evidence.result is not None
    assert evidence.publication is not None
    assert evidence.publication.decision is ResultPublicationDecision.PUBLISH
    assert evidence.result.engine_version == NAUTILUS_V2_RC_PACKAGE_VERSION
    assert evidence.result.engine_provenance is not None
    assert evidence.result.engine_provenance.execution_scope == "backtest_authoritative"
    assert (
        evidence.result.engine_provenance.release_channel is EngineReleaseChannel.RELEASE_CANDIDATE
    )
    assert len(evidence.artifact_plans) == len(evidence.result.output_artifacts) == 2
    assert all(
        publisher.store.path_for(artifact.storage_key).is_file()
        for artifact in evidence.result.output_artifacts
    )

    metrics = {item.name: item for item in evidence.result.metric_set.values}
    assert metrics["oos_fill_count"].value == Decimal(1)
    assert metrics["oos_reported_commission:USD"].value == Decimal("2.00")


@pytest.mark.asyncio
async def test_terminal_persistence_replays_success_with_stable_receipt_identity(tmp_path):
    context, lookup, resolver, _publisher = _successful_context_and_lookup(tmp_path)

    class RuntimePort:
        def __init__(self):
            self.state = context.request.runtime_state
            self.observed_at = []

        async def materialize_nautilus_result(self, **kwargs):
            self.observed_at.append(kwargs["observed_at"])
            resolution = materialize_nautilus_result(
                self.state,
                kwargs["execution_plan"],
                kwargs["sandbox_plan"],
                kwargs["run_result"],
                observed_at=kwargs["observed_at"],
            )
            self.state = resolution.state
            decision = (
                RuntimeStateDecision.REPLAY_EXISTING
                if resolution.decision.value == "replay_existing"
                else RuntimeStateDecision.APPLIED
            )
            return RuntimeStateResolution(decision, self.state)

    class ExecutionStatePort:
        def __init__(self):
            state = lookup.inputs.execution
            self.outcome = state.outcome
            self.progress = ProgressCheckpoint(
                state.progress,
                frozenset({content_digest("initial-progress-checkpoint")}),
            )

        async def transition(self, *, outcome_update, progress_update, **_kwargs):
            outcome_resolution = apply_outcome_update(self.outcome, outcome_update)
            progress_resolution = apply_progress_checkpoint(self.progress, progress_update)
            self.outcome = outcome_resolution.state
            self.progress = progress_resolution.checkpoint
            replay = (
                outcome_resolution.decision.value == "replay_existing"
                and progress_resolution.decision is ProgressCheckpointDecision.REPLAY_EXISTING
            )
            return StateMutationResolution(
                StateMutationDecision.REPLAY_EXISTING if replay else StateMutationDecision.APPLIED,
                self.outcome,
                self.progress.state,
            )

    class WorkerStatePort:
        def __init__(self):
            self.pool = context.request.worker_pool
            self.lease = context.request.lease_state
            self.release_times = []

        async def load_pool(self, _profile):
            return self.pool

        async def load_lease(self, _lease_id):
            return self.lease

        async def release_capacity(self, *, profile, reservation_id, lease_id, observation):
            self.release_times.append(observation.observed_at)
            assert profile == self.pool.profile
            assert lease_id == self.lease.lease.lease_id
            self.pool = release_worker_slot(
                self.pool,
                reservation_id=reservation_id,
                released_at=observation.observed_at,
            )
            lease_resolution = apply_lease_observation(self.lease, observation)
            assert lease_resolution.decision in {
                LeaseObservationDecision.APPLY,
                LeaseObservationDecision.REPLAY_EXISTING,
            }
            self.lease = lease_resolution.state
            decision = (
                WorkerCapacityDecision.REPLAY_EXISTING
                if lease_resolution.decision is LeaseObservationDecision.REPLAY_EXISTING
                else WorkerCapacityDecision.RELEASED
            )
            return WorkerCapacityResolution(
                decision,
                self.pool,
                self.lease,
                observation,
            )

    class SettlementPort:
        def __init__(self):
            self.ledger = WorkerSettlementLedger()

        async def load_ledger(self, *, principal):
            assert principal == "owner-terminal-test"
            return self.ledger

        async def ensure(self, *, principal, record):
            assert principal == "owner-terminal-test"
            existing = next(
                (item for item in self.ledger.records if item.attempt_id == record.attempt_id),
                None,
            )
            assert existing in {None, record}
            if existing is None:
                self.ledger = WorkerSettlementLedger((*self.ledger.records, record))
            return record

    class CompletionPort:
        def __init__(self):
            self.completions = ResultCompletionLedger()
            self.artifact_commits = ArtifactCommitLedger()
            self.completed_at = []
            self.inputs = []

        async def finalize(self, *, principal, **kwargs):
            assert principal == "owner-terminal-test"
            self.completed_at.append(kwargs["completed_at"])
            self.inputs.append(kwargs)
            resolution = finalize_execution_result(
                self.completions,
                self.artifact_commits,
                **kwargs,
            )
            self.completions = resolution.completion_ledger
            self.artifact_commits = resolution.artifact_commit_ledger
            return resolution

    class EnsurePort:
        async def ensure(self, **kwargs):
            return SimpleNamespace(**kwargs)

    class SummaryPort:
        async def ensure(self, *, summary, **_kwargs):
            return summary

    class PublicationPort:
        async def ensure(self, *, principal, plan):
            assert principal == "owner-terminal-test"
            return SimpleNamespace(plan=plan)

    runtime_port = RuntimePort()
    execution_state_port = ExecutionStatePort()
    worker_state_port = WorkerStatePort()
    settlement_port = SettlementPort()
    completion_port = CompletionPort()
    adapter = PostgresWorkerTerminalAdapter(
        resolver,
        runtime_execution=runtime_port,
        execution_state=execution_state_port,
        execution_summaries=SummaryPort(),
        result_publication=PublicationPort(),
        result_completion=completion_port,
        result_materialization=EnsurePort(),
        metrics=EnsurePort(),
        worker_state=worker_state_port,
        settlements=settlement_port,
    )

    first = await adapter.write(context)
    redelivered = await adapter.write(
        replace(context, observed_at=context.observed_at + timedelta(seconds=30))
    )

    assert first.decision is WorkerHandleDecision.COMPLETE
    assert redelivered.decision is WorkerHandleDecision.COMPLETE
    assert redelivered.receipt_digest == first.receipt_digest
    assert runtime_port.observed_at == [NOW, NOW]
    assert worker_state_port.release_times == [NOW, NOW]
    assert completion_port.completed_at == [NOW, NOW]
    assert len(settlement_port.ledger.records) == 1
    assert len(completion_port.completions.records) == 1
    assert not worker_state_port.pool.active_reservations
    assert all(
        item.action is ArtifactPublicationAction.CREATE_IF_ABSENT
        for item in completion_port.inputs[0]["artifact_plans"]
    )
    assert all(
        item.action is ArtifactPublicationAction.REUSE_EXISTING
        for item in completion_port.inputs[1]["artifact_plans"]
    )


@pytest.mark.asyncio
async def test_successful_worker_result_identity_is_stable_across_terminal_redelivery(tmp_path):
    context, _lookup, resolver, _publisher = _successful_context_and_lookup(tmp_path)

    first = await resolver(context)
    redelivered = await resolver(
        replace(context, observed_at=context.observed_at + timedelta(seconds=30))
    )

    assert first.result is not None and redelivered.result is not None
    assert redelivered.result.fingerprint == first.result.fingerprint
    assert redelivered.result.created_at == first.result.created_at == NOW


@pytest.mark.asyncio
async def test_permanent_result_validation_failure_rejects_terminal_entry(tmp_path, monkeypatch):
    context, _lookup, resolver, _publisher = _successful_context_and_lookup(tmp_path)

    def invalid_materialization(*_args, **_kwargs):
        raise ValueError("invalid immutable result identity")

    monkeypatch.setattr(
        terminal_module,
        "materialize_nautilus_oos_run_result",
        invalid_materialization,
    )

    result = await _terminal_writer(resolver).write(context)

    assert result.decision is WorkerHandleDecision.REJECT
    assert result.rejection_reason == "authoritative Nautilus result evidence failed validation"
