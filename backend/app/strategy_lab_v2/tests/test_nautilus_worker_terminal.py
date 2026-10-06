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
from app.strategy_lab_v2.dispatch import DispatchRequest
from app.strategy_lab_v2.dispatch_payload import DispatchPayload
from app.strategy_lab_v2.engine_execution import (
    EngineExecutionDecision,
    NautilusExecutionPlan,
    NautilusExecutionScope,
)
from app.strategy_lab_v2.execution import ExecutionAuthorization
from app.strategy_lab_v2.execution_orchestration import plan_execution_orchestration
from app.strategy_lab_v2.lease_observations import (
    LeaseObservation,
    LeaseObservationDecision,
    LeaseObservationState,
    apply_lease_observation,
)
from app.strategy_lab_v2.lifecycle import ExecutionAttemptLease
from app.strategy_lab_v2.migration_startup import MigrationDecision, MigrationResolution
from app.strategy_lab_v2.nautilus_equity_trace import NautilusAccountEquityTraceWriter
from app.strategy_lab_v2.nautilus_equity_trace_receipt import (
    NAUTILUS_EQUITY_TRACE_RECEIPT_MEDIA_TYPE,
    decode_nautilus_equity_trace_receipt,
)
from app.strategy_lab_v2.nautilus_native_reports import NautilusNativeReportsWriter
from app.strategy_lab_v2.nautilus_rebalance_schedule import (
    NautilusRebalanceScheduleAudit,
    NautilusRebalanceScheduleCursor,
    RebalanceExecutionStatus,
    RebalanceScheduleOutcome,
)
from app.strategy_lab_v2.nautilus_runner import (
    NautilusRunResult,
    NautilusRunStatus,
    expected_native_equity_events,
)
from app.strategy_lab_v2.nautilus_runtime_bundle import load_materialized_nautilus_runtime_bundle
from app.strategy_lab_v2.nautilus_session_equity import (
    NAUTILUS_SESSION_EQUITY_INTERVALS_MEDIA_TYPE,
    NautilusSessionCloseEquityObservation,
)
from app.strategy_lab_v2.nautilus_trial_materializer import (
    NautilusTrialMarketContext,
    NautilusTrialRuntimeInputMaterializer,
    build_nautilus_trial_runtime_evidence,
)
from app.strategy_lab_v2.nautilus_worker_terminal import (
    create_nautilus_oos_worker_terminal_evidence_resolver,
)
from app.strategy_lab_v2.outcomes import (
    ExecutionOutcome,
    OutcomeStatus,
    OutcomeUpdate,
    apply_outcome_update,
)
from app.strategy_lab_v2.postgres_artifact_commit import PostgresArtifactCommitAdapter
from app.strategy_lab_v2.postgres_commands import ExecutionCommandContext
from app.strategy_lab_v2.postgres_execution_state import (
    PostgresExecutionStateAdapter,
    StateMutationDecision,
    StateMutationResolution,
)
from app.strategy_lab_v2.postgres_execution_summary import PostgresExecutionSummaryAdapter
from app.strategy_lab_v2.postgres_metrics import PostgresMetricsAdapter
from app.strategy_lab_v2.postgres_result_completion import PostgresResultCompletionAdapter
from app.strategy_lab_v2.postgres_result_materialization import (
    PostgresResultMaterializationAdapter,
)
from app.strategy_lab_v2.postgres_result_publication import PostgresResultPublicationAdapter
from app.strategy_lab_v2.postgres_runtime_execution import (
    PostgresRuntimeExecutionAdapter,
    RuntimeStateDecision,
    RuntimeStateResolution,
)
from app.strategy_lab_v2.postgres_search_dispatch import (
    PostgresSearchDispatchAdapter,
    SearchDispatchRecord,
)
from app.strategy_lab_v2.postgres_submission import PostgresSubmissionDispatchAdapter
from app.strategy_lab_v2.postgres_worker_settlement import PostgresWorkerSettlementAdapter
from app.strategy_lab_v2.postgres_worker_state import (
    PostgresWorkerStateAdapter,
    WorkerCapacityDecision,
    WorkerCapacityResolution,
)
from app.strategy_lab_v2.progress import (
    ExecutionProgressState,
    ExecutionProgressUpdate,
    ProgressPhase,
)
from app.strategy_lab_v2.progress_checkpoint import (
    ProgressCheckpoint,
    ProgressCheckpointDecision,
    apply_progress_checkpoint,
)
from app.strategy_lab_v2.rebalance import (
    CalendarDay,
    CalendarDayStatus,
    RebalanceExecutionPlan,
    RebalanceMisfirePolicy,
    RebalanceTrigger,
    ScheduledRebalance,
    SessionCalendarSnapshot,
    SessionSegment,
    TradingSession,
)
from app.strategy_lab_v2.redis_application import RedisDispatchRuntime
from app.strategy_lab_v2.redis_transport import RedisDispatchTransport, RedisStreamEntry
from app.strategy_lab_v2.result_completion import ResultCompletionLedger, finalize_execution_result
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
from app.strategy_lab_v2.search_state import (
    SearchCandidatePhase,
    SearchStateDecision,
    new_search_execution_state,
    record_search_candidate_terminal,
    start_search_candidate,
)
from app.strategy_lab_v2.strategy_package_resolution import StrategyPackageArtifactResolver
from app.strategy_lab_v2.submissions import SubmissionReceipt, SubmissionRequest
from app.strategy_lab_v2.tests.test_nautilus_trial_assembly import (
    BASE,
    JsonFrozenSeriesDecoder,
)
from app.strategy_lab_v2.tests.test_nautilus_trial_materializer import (
    _add_second_strategy,
    _build_inputs,
)
from app.strategy_lab_v2.tests.test_postgres_execution_state import (
    FakeSession as ExecutionStateFakeSession,
)
from app.strategy_lab_v2.tests.test_postgres_execution_summary import (
    FakeSession as ExecutionSummaryFakeSession,
)
from app.strategy_lab_v2.tests.test_postgres_metrics import FakeSession as MetricsFakeSession
from app.strategy_lab_v2.tests.test_postgres_result_completion import (
    FakeSession as ResultCompletionFakeSession,
)
from app.strategy_lab_v2.tests.test_postgres_result_materialization import (
    FakeSession as ResultMaterializationFakeSession,
)
from app.strategy_lab_v2.tests.test_postgres_result_publication import (
    FakeSession as ResultPublicationFakeSession,
)
from app.strategy_lab_v2.tests.test_postgres_runtime_execution import (
    FakeSession as RuntimeExecutionFakeSession,
)
from app.strategy_lab_v2.tests.test_postgres_worker_settlement import (
    FakeSession as WorkerSettlementFakeSession,
)
from app.strategy_lab_v2.tests.test_postgres_worker_state import (
    FakeSession as WorkerStateFakeSession,
)
from app.strategy_lab_v2.tests.test_trial_hydration import MemoryDomainReader
from app.strategy_lab_v2.tests.test_worker_consumer import FakeRedis, _raw_entry, _stream_response
from app.strategy_lab_v2.trial_hydration import NautilusTrialDomainHydrator
from app.strategy_lab_v2.worker_callbacks import create_search_dispatch
from app.strategy_lab_v2.worker_consumer import (
    WorkerHandleDecision,
    WorkerHandleResult,
)
from app.strategy_lab_v2.worker_entrypoint import (
    WorkerEntrypointConfig,
    WorkerEntrypointDecision,
    run_strategy_lab_v2_worker,
)
from app.strategy_lab_v2.worker_evidence import (
    WorkerSubmissionBinding,
    WorkerTerminalEvidenceInputs,
    WorkerTerminalEvidenceLookup,
)
from app.strategy_lab_v2.worker_execution import (
    WorkerExecutionDecision,
    WorkerExecutionResolution,
)
from app.strategy_lab_v2.worker_handoff import encode_worker_handoff
from app.strategy_lab_v2.worker_process import (
    SerialWorkerProcessExecutor,
    WorkerExecutionRequest,
    WorkerProcessDecision,
    WorkerProcessResolution,
)
from app.strategy_lab_v2.worker_service import WorkerCompletionContext
from app.strategy_lab_v2.worker_settlement import WorkerSettlementLedger
from app.strategy_lab_v2.worker_terminal_adapter import (
    PostgresWorkerTerminalAdapter,
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


def _runtime_setup(
    tmp_path: Path,
    *,
    stable: bool = True,
    multi_strategy: bool = False,
    session_calendar: SessionCalendarSnapshot | None = None,
):
    engine_version = "2.0.0" if stable else NAUTILUS_V2_RC_PACKAGE_VERSION
    release_tag = "v2.0.0" if stable else NAUTILUS_V2_RC_RELEASE_TAG
    release_channel = (
        EngineReleaseChannel.STABLE if stable else EngineReleaseChannel.RELEASE_CANDIDATE
    )
    wheel_digest = (
        content_digest("nautilus-stable-test-wheel") if stable else NAUTILUS_V2_RC_WHEEL_SHA256
    )
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
            start=BASE if session_calendar is not None else BASE - timedelta(hours=1),
            end=BASE + timedelta(days=3),
            purpose="out_of_sample",
        ),
    )
    graph = replace(
        graph,
        trial=trial,
        attempt=replace(graph.attempt, trial_id=trial.trial_id),
    )
    if multi_strategy:
        graph = _add_second_strategy(values, graph, source_store)
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
        market_context=NautilusTrialMarketContext(
            values["instruments"],
            values["venue"],
            session_calendar,
            252 if session_calendar is not None else None,
        ),
    )
    profile = RuntimeIsolationProfile(
        runtime_image_digest=content_digest({"nautilus-test-image": engine_version}),
        runtime_abi="worker-abi-v1",
        allowed_dependency_digests=frozenset(
            dependency.artifact_digest
            for strategy in graph.strategies
            for dependency in strategy.dependencies
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
        expected_version=engine_version,
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
        package_version=engine_version,
        release_tag=release_tag,
        source_digest=content_digest({"nautilus-source": engine_version}),
        wheel_digest=wheel_digest,
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
        engine_version=engine_version,
        build_digest=content_digest({"nautilus-build": engine_version}),
        release_channel=release_channel,
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
        engine_version=engine_version,
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


def _session_metrics_calendar() -> SessionCalendarSnapshot:
    labels = tuple(BASE.date() + timedelta(days=index) for index in range(4))
    sessions = tuple(
        TradingSession(
            f"terminal-session-{label.isoformat()}",
            label,
            (
                SessionSegment(
                    BASE + timedelta(days=index) - timedelta(hours=6),
                    BASE + timedelta(days=index),
                ),
            ),
        )
        for index, label in enumerate(labels)
    )
    return SessionCalendarSnapshot(
        calendar_id="TEST-TERMINAL-SESSION",
        definition_version="terminal-session-metrics-v1",
        timezone_name="UTC",
        timezone_database_version="test-fixed-utc",
        coverage_start=labels[0],
        coverage_end=labels[-1],
        days=tuple(
            CalendarDay(label, CalendarDayStatus.TRADING, session)
            for label, session in zip(labels, sessions, strict=True)
        ),
        source_evidence_digest=content_digest("terminal-session-metrics-calendar"),
    )


def _timestamp_ns(value: datetime) -> int:
    delta = value.astimezone(UTC) - datetime(1970, 1, 1, tzinfo=UTC)
    return (delta.days * 86_400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1_000


def _successful_context_and_lookup(
    tmp_path: Path,
    *,
    stable: bool = True,
    multi_strategy: bool = False,
    with_graph: bool = False,
    session_calendar: SessionCalendarSnapshot | None = None,
):
    graph, source_store, request, _conformance_evidence = _runtime_setup(
        tmp_path,
        stable=stable,
        multi_strategy=multi_strategy,
        session_calendar=session_calendar,
    )
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
    session_close_observations: tuple[NautilusSessionCloseEquityObservation, ...] = ()
    session_periods_per_year = None
    if bundle.session_calendar is not None:
        session_by_close_ns = {
            _timestamp_ns(day.session.close_time): day
            for day in bundle.session_calendar.days
            if day.session is not None
        }
        scoring_start_ns = engine_input["evaluation_window"]["start_ns"]
        closes = []
        for index, item in enumerate(expected_events):
            event = item.get("event", item)
            event_time_ns = event["event_time_ns"]
            day = session_by_close_ns.get(event_time_ns)
            if day is None or event_time_ns <= scoring_start_ns:
                continue
            closes.append(
                NautilusSessionCloseEquityObservation(
                    day.label,
                    event_time_ns,
                    index,
                    Decimal("100000") + Decimal(index * 10),
                    Decimal("100000"),
                )
            )
        session_close_observations = tuple(closes)
        session_periods_per_year = bundle.session_periods_per_year
    run_result = NautilusRunResult(
        request.execution_plan.fingerprint,
        sandbox.fingerprint,
        NautilusRunStatus.SUCCEEDED,
        True,
        sandbox_result=sandbox_result,
        account_equity_trace=equity_reference,
        native_reports=reports_reference,
        session_calendar=bundle.session_calendar,
        session_close_equity_observations=session_close_observations,
        session_periods_per_year=session_periods_per_year,
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
        "strategies": graph.strategies,
        "packages": graph.packages,
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
    result = (context, lookup, resolver, publisher)
    return (*result, graph) if with_graph else result


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
async def test_rc6_worker_receipt_materializes_authoritative_local_backtest(tmp_path):
    context, _lookup, resolver, publisher = _successful_context_and_lookup(tmp_path, stable=False)

    resolution = await resolver(context)

    assert resolution.result is not None
    assert resolution.result.engine_authoritative
    assert resolution.result.engine_provenance is not None
    assert (
        resolution.result.engine_provenance.release_channel
        is EngineReleaseChannel.RELEASE_CANDIDATE
    )
    assert resolution.result.engine_provenance.execution_scope == (
        NautilusExecutionScope.BACKTEST_AUTHORITATIVE.value
    )
    assert resolution.publication is not None and resolution.publication.accepted
    receipt_artifacts = tuple(
        artifact
        for artifact in resolution.result.output_artifacts
        if artifact.media_type == NAUTILUS_EQUITY_TRACE_RECEIPT_MEDIA_TYPE
    )
    assert len(receipt_artifacts) == 1
    receipt = decode_nautilus_equity_trace_receipt(
        receipt_artifacts[0],
        publisher.store.path_for(receipt_artifacts[0].storage_key).read_bytes(),
    )
    assert receipt.trial_id == resolution.result.trial_id
    assert receipt.attempt_id == resolution.result.attempt_id
    assert receipt.portfolio_fingerprint == resolution.result.portfolio_fingerprint
    assert receipt.snapshot_fingerprint == resolution.result.snapshot.fingerprint


@pytest.mark.asyncio
async def test_worker_terminal_publishes_native_session_interval_artifact(tmp_path):
    calendar = _session_metrics_calendar()
    context, _lookup, resolver, publisher = _successful_context_and_lookup(
        tmp_path,
        stable=False,
        session_calendar=calendar,
    )

    resolution = await resolver(context)

    assert resolution.result is not None and resolution.publication is not None
    assert resolution.publication.accepted
    session_artifacts = tuple(
        artifact
        for artifact in resolution.result.output_artifacts
        if artifact.media_type == NAUTILUS_SESSION_EQUITY_INTERVALS_MEDIA_TYPE
    )
    assert len(session_artifacts) == 1
    payload = json.loads(publisher.store.path_for(session_artifacts[0].storage_key).read_bytes())
    assert payload["calendar_fingerprint"] == calendar.fingerprint
    assert payload["expected_session_labels"] == [
        (BASE.date() + timedelta(days=1)).isoformat(),
        (BASE.date() + timedelta(days=2)).isoformat(),
    ]
    assert payload["observed_session_labels"] == [(BASE.date() + timedelta(days=1)).isoformat()]
    assert len(payload["intervals"]) == 1
    session_metric_evidence = {
        reference.digest
        for metric in resolution.result.metric_set.values
        for reference in metric.evidence_references
        if reference.role == "session_equity_intervals"
    }
    assert session_metric_evidence
    session_metrics = tuple(
        metric
        for metric in resolution.result.metric_set.values
        if any(
            reference.role == "session_equity_intervals" for reference in metric.evidence_references
        )
    )
    assert session_metrics
    assert all(metric.sample_size == 1 for metric in session_metrics)
    assert all(metric.value is None for metric in session_metrics)
    assert all(metric.null_reason is not None for metric in session_metrics)
    assert all(
        any(digest in metric.calculation_basis for digest in session_metric_evidence)
        for metric in session_metrics
    )


@pytest.mark.asyncio
async def test_failed_rebalance_misfire_publishes_authenticated_diagnostic_artifact(tmp_path):
    context, _lookup, resolver, publisher = _successful_context_and_lookup(tmp_path)
    policy_fingerprint = content_digest("failed-rebalance-policy")
    calendar_fingerprint = content_digest("failed-rebalance-calendar")
    occurrence = ScheduledRebalance(
        occurrence_id=content_digest("failed-rebalance-occurrence"),
        policy_fingerprint=policy_fingerprint,
        calendar_fingerprint=calendar_fingerprint,
        session_id="session-2024-01-03",
        session_label=(BASE + timedelta(days=1)).date(),
        event_time=BASE + timedelta(days=1),
        trigger=RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS,
        cadence_period="session:2024-01-03",
        misfire_policy=RebalanceMisfirePolicy.FAIL_RUN,
    )
    plan = RebalanceExecutionPlan(
        policy_fingerprint=policy_fingerprint,
        calendar_fingerprint=calendar_fingerprint,
        occurrences=(occurrence,),
    )
    transition = NautilusRebalanceScheduleCursor(plan).finish()[0]
    audit = NautilusRebalanceScheduleAudit(
        attempt_id=context.request.admission.attempt_id,
        plan_fingerprint=plan.fingerprint,
        outcomes=(
            RebalanceScheduleOutcome(
                transition=transition,
                execution_status=RebalanceExecutionStatus.FAILED_MISFIRE,
                submitted_order_count=0,
            ),
        ),
    )
    prior_execution = context.process.execution
    assert prior_execution is not None
    assert prior_execution.nautilus_result is not None
    failed_run_result = replace(
        prior_execution.nautilus_result,
        status=NautilusRunStatus.FAILED,
        authoritative=False,
        result_failure_digest=content_digest("rebalance misfire"),
        rebalance_schedule_audit=audit,
    )
    failed_runtime_result = materialize_nautilus_result(
        context.request.runtime_state,
        context.request.execution_plan,
        context.request.sandbox_plan,
        failed_run_result,
        observed_at=NOW,
    )
    failed_execution = WorkerExecutionResolution(
        WorkerExecutionDecision.FAILED,
        context.request.orchestration_plan,
        failed_run_result,
        failed_runtime_result,
    )
    failed_process = WorkerProcessResolution(
        context.request.request_fingerprint,
        WorkerProcessDecision.COMPLETED,
        execution=failed_execution,
        process_id=9001,
    )
    failed_context = replace(context, process=failed_process)

    evidence = await resolver(failed_context)
    replayed = await resolver(failed_context)

    assert evidence.result is None
    assert evidence.error is not None
    assert evidence.principal == "owner-terminal-test"
    assert replayed.error is not None
    assert replayed.error.details == evidence.error.details
    diagnostics = evidence.error.details["diagnostic_artifacts"]
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic["attempt_id"] == audit.attempt_id
    assert diagnostic["audit_fingerprint"] == audit.fingerprint
    manifest = audit.artifact_manifest()
    assert diagnostic["content_digest"] == manifest.content_digest
    assert publisher.store.path_for(manifest.storage_key).read_bytes() == audit.artifact_bytes()


@pytest.mark.asyncio
async def test_multi_strategy_terminal_persistence_replays_success_with_stable_receipt_identity(
    tmp_path,
    monkeypatch,
):
    context, lookup, _resolver, _publisher, graph = _successful_context_and_lookup(
        tmp_path,
        stable=False,
        multi_strategy=True,
        with_graph=True,
    )

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

        async def load(self, *, principal, attempt_id):
            assert principal == "owner-terminal-test"
            assert attempt_id == self.state.attempt_id
            return self.state

        async def initialize(self, *, principal, state):
            assert principal == "owner-terminal-test"
            decision = "replay_existing" if state == self.state else "registered"
            self.state = state
            return SimpleNamespace(decision=SimpleNamespace(value=decision))

    class ExecutionStatePort:
        def __init__(self):
            state = lookup.inputs.execution
            self.outcome = state.outcome
            self.progress = ProgressCheckpoint(
                state.progress,
                frozenset({content_digest("initial-progress-checkpoint")}),
            )
            self.context = None

        async def read_context(self, *, principal, attempt_id):
            assert principal == "owner-terminal-test"
            assert attempt_id == context.request.runtime_request.attempt_id
            return self.context

        async def initialize(self, *, principal, outcome, progress):
            assert principal == "owner-terminal-test"
            self.context = ExecutionCommandContext(outcome, progress)
            self.outcome = outcome
            self.progress = ProgressCheckpoint(
                progress,
                frozenset({content_digest("bootstrapped-progress-checkpoint")}),
            )
            return SimpleNamespace(decision=SimpleNamespace(value="applied"))

        async def transition(self, *, outcome_update, progress_update, **_kwargs):
            outcome_resolution = apply_outcome_update(self.outcome, outcome_update)
            progress_resolution = apply_progress_checkpoint(self.progress, progress_update)
            self.outcome = outcome_resolution.state
            self.progress = progress_resolution.checkpoint
            self.context = ExecutionCommandContext(self.outcome, self.progress.state)
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

        async def load_completion_ledger(self, *, principal):
            assert principal == "owner-terminal-test"
            return self.completions

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
    payload = DispatchPayload.from_mapping(encode_worker_handoff(context.request))
    trial_binding = context.request.runtime_input_artifact.trial_binding
    assert trial_binding is not None
    dispatch_request = DispatchRequest(
        "multi-strategy-terminal-dispatch",
        context.request.authorization.attempt_id,
        payload.payload_digest,
        "backtest",
        BASE,
    )
    dispatch_record = SearchDispatchRecord(
        "owner-terminal-test",
        trial_binding.experiment_fingerprint,
        0,
        dispatch_request,
    )
    search_state = new_search_execution_state(
        dispatch_record.experiment_fingerprint,
        (graph.trial.trial_id,),
        now=BASE,
    )
    search_state = start_search_candidate(
        search_state,
        dispatch_record.candidate_index,
        attempt_id=dispatch_request.attempt_id,
        now=BASE,
    ).state

    class SearchStatePort:
        def __init__(self) -> None:
            self.state = search_state

        async def load(self, *, principal, experiment_fingerprint):
            assert principal == "owner-terminal-test"
            assert experiment_fingerprint == dispatch_record.experiment_fingerprint
            return self.state

        async def record_terminal(self, **kwargs):
            resolution = record_search_candidate_terminal(
                self.state,
                kwargs["candidate_index"],
                attempt_id=kwargs["attempt_id"],
                phase=kwargs["phase"],
                now=kwargs["now"],
                result_fingerprint=kwargs.get("result_fingerprint"),
            )
            if resolution.decision is SearchStateDecision.APPLY:
                self.state = resolution.state
            return resolution

    search_state_port = SearchStatePort()

    class QueryResult:
        def __init__(self, rows: tuple[dict[str, Any], ...]) -> None:
            self._rows = rows

        def mappings(self) -> tuple[dict[str, Any], ...]:
            return self._rows

    class PersistedSession:
        async def __aenter__(self) -> PersistedSession:
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

        def begin(self) -> PersistedSession:
            return self

        async def execute(self, statement: Any, params: Any) -> QueryResult:
            sql = str(statement)
            if dispatch_adapter.schema.dispatch_table in sql:
                assert params in (
                    {"request_fingerprint": dispatch_request.fingerprint},
                    {"payload_digest": dispatch_request.payload_digest},
                )
                return QueryResult(
                    (
                        {
                            "owner_id": dispatch_record.owner_id,
                            "experiment_fingerprint": dispatch_record.experiment_fingerprint,
                            "candidate_index": dispatch_record.candidate_index,
                            "idempotency_key": dispatch_request.idempotency_key,
                            "request_fingerprint": dispatch_request.fingerprint,
                            "attempt_id": dispatch_request.attempt_id,
                            "payload_digest": dispatch_request.payload_digest,
                            "queue_name": dispatch_request.queue_name,
                            "created_at": dispatch_request.created_at.isoformat(),
                            "dispatch_fingerprint": dispatch_request.fingerprint,
                        },
                    )
                )
            if submission_adapter.schema.payload_table in sql:
                assert params == {"payload_digest": payload.payload_digest}
                return QueryResult(
                    (
                        {
                            "payload_digest": payload.payload_digest,
                            "payload_json": payload.payload_json,
                            "byte_length": payload.byte_length,
                            "payload_fingerprint": payload.fingerprint,
                        },
                    )
                )
            if submission_adapter.schema.submission_table in sql:
                receipt = lookup.binding.receipt
                assert params == {
                    "owner_id": lookup.binding.owner_id,
                    "attempt_id": dispatch_request.attempt_id,
                }
                return QueryResult(
                    (
                        {
                            "owner_id": lookup.binding.owner_id,
                            "idempotency_key": receipt.request.idempotency_key,
                            "request_fingerprint": receipt.request.fingerprint,
                            "operation": receipt.request.operation,
                            "attempt_id": receipt.request.attempt_id,
                            "payload_digest": receipt.request.payload_digest,
                            "submitted_at": receipt.request.submitted_at.isoformat(),
                            "accepted_at": receipt.accepted_at.isoformat(),
                        },
                    )
                )
            raise AssertionError(f"unexpected worker persistence query: {sql}")

    dispatch_adapter = PostgresSearchDispatchAdapter(lambda: PersistedSession())
    submission_adapter = PostgresSubmissionDispatchAdapter(lambda: PersistedSession())
    timeline: list[str] = []
    terminal_write_attempts = 0
    artifact_committer = _MemoryCommitter()
    domain_reader = MemoryDomainReader(
        {
            "attempt": graph.attempt,
            "trial": graph.trial,
            "experiment": graph.experiment,
            "portfolio": graph.portfolio,
            "snapshot": graph.snapshot,
            "strategies": graph.strategies,
            "packages": graph.packages,
        },
        owner="owner-terminal-test",
    )

    class Persistence:
        search_dispatch = dispatch_adapter
        submissions = submission_adapter
        resources = domain_reader
        worker_state = worker_state_port
        execution_state = execution_state_port
        runtime_execution = runtime_port
        search_state = search_state_port
        result_completion = completion_port
        worker_settlements = settlement_port
        worker_recoveries = SimpleNamespace(
            load_ledger=lambda **_kwargs: None,
            recover=lambda **_kwargs: None,
        )

        def __init__(self) -> None:
            self.terminal_adapter: PostgresWorkerTerminalAdapter | None = None
            self.publisher: LocalArtifactPublicationService | None = None

        async def persist_retry_attempt(self, **_kwargs: Any) -> None:
            raise AssertionError("successful terminal replay must not persist a retry attempt")

        def artifact_publication(self, root: Path) -> LocalArtifactPublicationService:
            self.publisher = LocalArtifactPublicationService(
                LocalArtifactStore(root),
                artifact_committer,
            )
            return self.publisher

        async def load_worker_terminal_evidence_for_request(
            self,
            *,
            request_fingerprint: str,
            attempt_id: str,
            payload_digest: str | None = None,
            search_dispatch_binding_resolver: Any,
        ) -> WorkerTerminalEvidenceLookup | None:
            record = (
                await self.search_dispatch.load_by_payload_digest(payload_digest)
                if payload_digest is not None
                else await self.search_dispatch.load_by_request_fingerprint(request_fingerprint)
            )
            if record is None or record.request.attempt_id != attempt_id:
                return None
            binding = await search_dispatch_binding_resolver(record)
            if binding != lookup.binding:
                return None
            assert execution_state_port.context is not None
            return replace(
                lookup,
                inputs=replace(lookup.inputs, execution=execution_state_port.context),
            )

        def worker_terminal_writer(self, evidence_resolver: Any) -> Any:
            self.terminal_adapter = PostgresWorkerTerminalAdapter(
                evidence_resolver,
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

            async def persist_terminal(
                completion_context: WorkerCompletionContext,
            ) -> WorkerHandleResult:
                nonlocal terminal_write_attempts
                terminal_write_attempts += 1
                assert self.terminal_adapter is not None
                receipt = await self.terminal_adapter.write(completion_context)
                if terminal_write_attempts == 1:
                    timeline.append("terminal-commit-response-lost")
                    raise TimeoutError("terminal receipt response was interrupted after commit")
                timeline.append("terminal-persisted")
                return receipt

            return persist_terminal

    monkeypatch.setenv(
        "STRATEGY_LAB_V2_EVIDENCE_RESOLVER",
        "app.strategy_lab_v2.worker_callbacks:default_evidence_resolver_factory",
    )
    monkeypatch.setenv("STRATEGY_LAB_V2_QUEUE", "backtest")
    monkeypatch.setenv(
        "STRATEGY_LAB_V2_PREPARATION_SOCKET_PATH",
        str(tmp_path / "unused-preparation.sock"),
    )
    monkeypatch.setenv(
        "STRATEGY_LAB_V2_PREPARATION_AUTH_TOKEN", "terminal-test-token-0123456789abcdef"
    )
    entry = RedisStreamEntry(
        "strategy-lab:v2:stream:backtest",
        "1-0",
        dispatch_request.fingerprint,
        dispatch_request.attempt_id,
        payload.payload_digest,
        dispatch_request.fingerprint,
    )

    class EvidenceProcessExecutor(SerialWorkerProcessExecutor):
        def __init__(self):
            self.calls = 0

        async def run_async(
            self,
            request,
            *,
            timeout_seconds=None,
            poll_interval_seconds=0.005,
        ):
            del timeout_seconds, poll_interval_seconds
            assert request == context.request
            self.calls += 1
            return context.process

    process_executor = EvidenceProcessExecutor()

    class OrderedRedis(FakeRedis):
        async def xack(self, *args):
            timeline.append("ack")
            return await super().xack(*args)

        async def aclose(self) -> None:
            timeline.append("runtime-closed")

    async def scheduler_sleep(_seconds):
        return None

    redis_clients = (
        OrderedRedis(fresh=_stream_response(entry)),
        OrderedRedis(reclaimed=(_raw_entry(entry),)),
        OrderedRedis(fresh=_stream_response(entry)),
    )
    migrations: list[MigrationDecision] = []

    class AppliedMigration:
        async def upgrade(self) -> MigrationResolution:
            decision = (
                MigrationDecision.APPLIED if not migrations else MigrationDecision.REPLAY_EXISTING
            )
            migrations.append(decision)
            return MigrationResolution(
                content_digest("worker-entrypoint-terminal-migration"),
                decision,
                "head",
            )

    async def runtime_factory(url: str, *, namespace: str) -> RedisDispatchRuntime:
        assert url == "redis://localhost:6379/0"
        client = redis_clients[len(migrations) - 1]
        return RedisDispatchRuntime(
            client,
            RedisDispatchTransport(client, namespace=namespace),
        )

    def install_signals(_stop_event: Any) -> Any:
        return lambda: timeline.append("signals-cleaned")

    async def progress_client(**_kwargs: Any) -> Any:
        timeline.append("progress-notified")
        return None

    async def callback_factory(persistence: Any, artifact_root: Path):
        return await create_search_dispatch(
            persistence,
            artifact_root,
            walk_forward_progress_client=progress_client,
        )

    async def run_worker():
        return await run_strategy_lab_v2_worker(
            WorkerEntrypointConfig(
                redis_url="redis://localhost:6379/0",
                database_url_sync="postgresql+psycopg2://localhost/chartingdb",
                artifact_root=tmp_path / "worker-artifacts",
                queue_name="backtest",
                group_name="workers",
                consumer_name="multi-strategy-terminal-test",
                migration_enabled=True,
            ),
            callback_factory=callback_factory,
            migration_service=AppliedMigration(),  # type: ignore[arg-type]
            session_factory=lambda: object(),
            persistence_factory=lambda _factory: Persistence(),  # type: ignore[arg-type]
            runtime_factory=runtime_factory,
            signal_installer=install_signals,
            process_executor=process_executor,
            # The retry clock must be at or after the process's persisted
            # terminal timestamp; the lease release uses that immutable time.
            clock=lambda: context.observed_at,
            sleep=scheduler_sleep,
            max_cycles=1,
        )

    failed_run = await run_worker()
    assert failed_run.decision is WorkerEntrypointDecision.STOPPED
    assert failed_run.runtime_closed is True
    assert failed_run.migration is not None
    assert failed_run.migration.decision is MigrationDecision.APPLIED
    assert len(failed_run.cycles) == 1
    failed_cycle = failed_run.cycles[0]
    assert len(failed_cycle.entries) == 1
    failed_resolution = failed_cycle.entries[0]
    assert failed_resolution.decision.value == "retry"
    assert failed_resolution.handler.rejection_reason == (
        "worker terminal completion failed: TimeoutError"
    )
    assert worker_state_port.lease.lease.released_at is not None
    assert timeline == [
        "terminal-commit-response-lost",
        "signals-cleaned",
        "runtime-closed",
    ]
    assert not any(call[0] == "xack" for call in redis_clients[0].calls)

    recovered_run = await run_worker()
    assert recovered_run.decision is WorkerEntrypointDecision.STOPPED
    assert recovered_run.runtime_closed is True
    assert recovered_run.migration is not None
    assert recovered_run.migration.decision is MigrationDecision.REPLAY_EXISTING
    assert len(recovered_run.cycles) == 1
    recovered_cycle = recovered_run.cycles[0]
    assert len(recovered_cycle.entries) == 1
    first_resolution = recovered_cycle.entries[0]
    assert (
        first_resolution.decision.value == "acknowledged"
    ), first_resolution.handler.rejection_reason
    assert timeline == [
        "terminal-commit-response-lost",
        "signals-cleaned",
        "runtime-closed",
        "progress-notified",
        "ack",
        "signals-cleaned",
        "runtime-closed",
    ]
    assert process_executor.calls == 1
    first = first_resolution.handler
    duplicate_run = await run_worker()
    assert duplicate_run.decision is WorkerEntrypointDecision.STOPPED
    assert duplicate_run.runtime_closed is True
    assert duplicate_run.migration is not None
    assert duplicate_run.migration.decision is MigrationDecision.REPLAY_EXISTING
    assert len(duplicate_run.cycles) == 1
    duplicate_cycle = duplicate_run.cycles[0]
    assert len(duplicate_cycle.entries) == 1
    duplicate_resolution = duplicate_cycle.entries[0]
    assert duplicate_resolution.decision.value == "acknowledged"
    assert process_executor.calls == 1
    redelivered = duplicate_resolution.handler
    assert timeline == [
        "terminal-commit-response-lost",
        "signals-cleaned",
        "runtime-closed",
        "progress-notified",
        "ack",
        "signals-cleaned",
        "runtime-closed",
        "progress-notified",
        "ack",
        "signals-cleaned",
        "runtime-closed",
    ]

    assert first.decision is WorkerHandleDecision.COMPLETE
    assert redelivered.decision is WorkerHandleDecision.COMPLETE
    assert redelivered.receipt_digest == first.receipt_digest
    assert len(runtime_port.observed_at) == 1
    assert len(worker_state_port.release_times) == 1
    assert len(completion_port.completed_at) == 1
    assert len(settlement_port.ledger.records) == 1
    assert len(completion_port.completions.records) == 1
    assert not worker_state_port.pool.active_reservations
    assert all(
        item.action is ArtifactPublicationAction.CREATE_IF_ABSENT
        for item in completion_port.inputs[0]["artifact_plans"]
    )
    candidate = search_state_port.state.candidates[dispatch_record.candidate_index]
    assert candidate.phase is SearchCandidatePhase.SUCCEEDED
    assert candidate.attempt_id == dispatch_request.attempt_id
    assert candidate.result_fingerprint == completion_port.completions.records[0].result_fingerprint
    assert timeline == [
        "terminal-commit-response-lost",
        "signals-cleaned",
        "runtime-closed",
        "progress-notified",
        "ack",
        "signals-cleaned",
        "runtime-closed",
        "progress-notified",
        "ack",
        "signals-cleaned",
        "runtime-closed",
    ]
    assert migrations == [
        MigrationDecision.APPLIED,
        MigrationDecision.REPLAY_EXISTING,
        MigrationDecision.REPLAY_EXISTING,
    ]


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
async def test_rc6_terminal_writer_composes_postgres_adapters_and_replays_durably(tmp_path):
    context, lookup, _resolver, _publisher, graph = _successful_context_and_lookup(
        tmp_path,
        stable=False,
        with_graph=True,
    )
    owner_id = lookup.owner_id
    attempt_id = context.request.admission.attempt_id
    completion_session = ResultCompletionFakeSession()
    artifact_commits = PostgresArtifactCommitAdapter(lambda: completion_session)
    artifact_publisher = LocalArtifactPublicationService(
        LocalArtifactStore(tmp_path / "postgres-backed-artifacts"),
        artifact_commits,
    )
    domain_reader = MemoryDomainReader(
        {
            "attempt": graph.attempt,
            "trial": graph.trial,
            "experiment": graph.experiment,
            "portfolio": graph.portfolio,
            "snapshot": graph.snapshot,
            "strategies": graph.strategies,
            "packages": graph.packages,
        },
        owner=owner_id,
    )
    resolver = create_nautilus_oos_worker_terminal_evidence_resolver(
        lambda **_kwargs: lookup,
        artifact_publisher,
        NautilusTrialDomainHydrator(domain_reader),
    )

    runtime_session = RuntimeExecutionFakeSession()
    execution_session = ExecutionStateFakeSession()
    worker_session = WorkerStateFakeSession()
    settlement_session = WorkerSettlementFakeSession()
    completion_session = ResultCompletionFakeSession()
    materialization_session = ResultMaterializationFakeSession()
    metrics_session = MetricsFakeSession()
    publication_session = ResultPublicationFakeSession()
    summary_session = ExecutionSummaryFakeSession()
    initial_execution = lookup.inputs.execution
    assert initial_execution is not None
    capacity_release_attempts: list[str] = []

    class FailOnceBeforePublicStatePersistence:
        def __init__(self, execution_state: PostgresExecutionStateAdapter) -> None:
            self.execution_state = execution_state
            self.fail_transition = True

        async def transition(self, **kwargs: Any) -> StateMutationResolution:
            if self.fail_transition:
                self.fail_transition = False
                raise RuntimeError("simulated crash before public state persistence")
            return await self.execution_state.transition(**kwargs)

    class CrashOnceBeforeCapacityRelease(PostgresWorkerStateAdapter):
        def __init__(self, *, fail_release: bool) -> None:
            super().__init__(lambda: worker_session)
            self.fail_release = fail_release
            self.release_attempts = 0

        async def release_capacity(
            self,
            *,
            profile: WorkerProfile,
            reservation_id: str,
            lease_id: str,
            observation: LeaseObservation,
        ) -> WorkerCapacityResolution:
            self.release_attempts += 1
            if self.fail_release:
                capacity_release_attempts.append("interrupted")
                self.fail_release = False
                raise RuntimeError("simulated crash before capacity release")
            capacity_release_attempts.append("delegated")
            return await super().release_capacity(
                profile=profile,
                reservation_id=reservation_id,
                lease_id=lease_id,
                observation=observation,
            )

    def build_terminal_stack(
        *, fail_public_state: bool = False, fail_capacity_release: bool = False
    ) -> SimpleNamespace:
        runtime_adapter = PostgresRuntimeExecutionAdapter(lambda: runtime_session)
        execution_adapter = PostgresExecutionStateAdapter(lambda: execution_session)
        execution_writer = (
            FailOnceBeforePublicStatePersistence(execution_adapter)
            if fail_public_state
            else execution_adapter
        )
        worker_adapter = CrashOnceBeforeCapacityRelease(fail_release=fail_capacity_release)
        settlement_adapter = PostgresWorkerSettlementAdapter(lambda: settlement_session)
        completion_adapter = PostgresResultCompletionAdapter(lambda: completion_session)
        materialization_adapter = PostgresResultMaterializationAdapter(
            lambda: materialization_session
        )
        metrics_adapter = PostgresMetricsAdapter(lambda: metrics_session)
        publication_adapter = PostgresResultPublicationAdapter(lambda: publication_session)
        summary_adapter = PostgresExecutionSummaryAdapter(lambda: summary_session)
        terminal_adapter = PostgresWorkerTerminalAdapter(
            resolver,
            runtime_execution=runtime_adapter,
            execution_state=cast(Any, execution_writer),
            execution_summaries=summary_adapter,
            result_publication=publication_adapter,
            result_completion=completion_adapter,
            result_materialization=materialization_adapter,
            metrics=metrics_adapter,
            worker_state=worker_adapter,
            settlements=settlement_adapter,
        )
        return SimpleNamespace(
            runtime=runtime_adapter,
            execution_state=execution_adapter,
            execution_state_writer=execution_writer,
            worker_state=worker_adapter,
            settlement=settlement_adapter,
            completion=completion_adapter,
            materialization=materialization_adapter,
            metrics=metrics_adapter,
            publication=publication_adapter,
            summaries=summary_adapter,
            terminal_writer=terminal_adapter,
        )

    stack = build_terminal_stack(fail_public_state=True, fail_capacity_release=True)
    runtime = stack.runtime
    execution_state = stack.execution_state
    worker_state = stack.worker_state
    settlement = stack.settlement
    completion = stack.completion
    materialization = stack.materialization
    metrics = stack.metrics
    publication = stack.publication
    summaries = stack.summaries
    terminal_writer = stack.terminal_writer

    initialized_runtime = await runtime.initialize(
        principal=owner_id,
        state=context.request.runtime_state,
    )
    assert initialized_runtime.decision is RuntimeStateDecision.REGISTERED
    initialized_execution = await execution_state.initialize(
        principal=owner_id,
        outcome=replace(initial_execution.outcome, sequence=0),
        progress=replace(
            initial_execution.progress,
            sequence=0,
            phase=ProgressPhase.QUEUED,
        ),
    )
    assert initialized_execution.decision is StateMutationDecision.APPLIED
    persisted_running = await execution_state.transition(
        principal=owner_id,
        outcome_update=OutcomeUpdate(
            initial_execution.outcome.submission_id,
            attempt_id,
            initial_execution.outcome.sequence,
            initial_execution.outcome.status,
            initial_execution.outcome.updated_at,
        ),
        progress_update=ExecutionProgressUpdate(
            attempt_id,
            initial_execution.progress.sequence,
            initial_execution.progress.phase,
            initial_execution.progress.completed_units,
            initial_execution.progress.total_units,
            initial_execution.progress.updated_at,
        ),
    )
    assert persisted_running.decision is StateMutationDecision.APPLIED
    assert persisted_running.outcome == initial_execution.outcome
    assert persisted_running.progress == initial_execution.progress
    profile = context.request.worker_pool.profile
    assert (await worker_state.ensure_profile(profile)).pool.profile == profile
    reservation = next(
        item
        for item in context.request.worker_pool.reservations
        if item.reservation_id == context.request.admission.reservation_id
    )
    reserved = await worker_state.reserve(
        profile=profile,
        attempt_id=attempt_id,
        reservation_id=reservation.reservation_id,
        acquired_at=reservation.acquired_at,
    )
    assert reserved.reservation == reservation
    await worker_state.persist_lease(context.request.lease_state.lease)

    interrupted_state = await terminal_writer.write(context)
    assert interrupted_state.decision is WorkerHandleDecision.RETRY
    assert interrupted_state.rejection_reason == (
        "public terminal state persistence failed: RuntimeError"
    )
    persisted_settlement = await settlement.load_ledger(principal=owner_id)
    assert len(persisted_settlement.records) == 1
    pre_state_runtime = await runtime.load(principal=owner_id, attempt_id=attempt_id)
    assert pre_state_runtime is not None
    assert pre_state_runtime.phase.value == "succeeded"
    pre_state_execution = await execution_state.read_context(
        principal=owner_id,
        attempt_id=attempt_id,
    )
    assert pre_state_execution == initial_execution
    assert (
        await materialization.load_manifest(
            principal=owner_id,
            attempt_id=attempt_id,
        )
        is None
    )
    assert await metrics.load_all_metric_sets(principal=owner_id) == ()
    assert len((await completion.load_completion_ledger(principal=owner_id)).records) == 0
    assert len((await artifact_commits.load_ledger()).records) > 0
    assert (
        await summaries.load(
            principal=owner_id,
            submission_id=lookup.binding.receipt.submission_id,
            attempt_id=attempt_id,
        )
        is None
    )
    active_pool = await worker_state.load_pool(profile)
    assert len(active_pool.active_reservations) == 1
    active_lease = await worker_state.load_lease(context.request.lease_state.lease.lease_id)
    assert active_lease is not None and active_lease.lease.released_at is None

    # Recreate every PostgreSQL adapter around the same durable SQL-session
    # state, as a restarted worker process would.
    stack = build_terminal_stack(fail_capacity_release=True)
    runtime = stack.runtime
    execution_state = stack.execution_state
    worker_state = stack.worker_state
    settlement = stack.settlement
    completion = stack.completion
    materialization = stack.materialization
    metrics = stack.metrics
    publication = stack.publication
    summaries = stack.summaries
    terminal_writer = stack.terminal_writer

    interrupted_capacity = await terminal_writer.write(context)
    assert interrupted_capacity.decision is WorkerHandleDecision.RETRY
    assert interrupted_capacity.rejection_reason == (
        "terminal settlement persistence failed: RuntimeError"
    )
    interrupted_execution = await execution_state.read_context(
        principal=owner_id,
        attempt_id=attempt_id,
    )
    assert interrupted_execution is not None
    assert interrupted_execution.outcome.status is OutcomeStatus.SUCCEEDED
    interrupted_manifest = await materialization.load_manifest(
        principal=owner_id,
        attempt_id=attempt_id,
    )
    assert interrupted_manifest is not None
    assert await metrics.load_all_metric_sets(principal=owner_id) == (
        interrupted_manifest.metric_set,
    )
    assert len((await completion.load_completion_ledger(principal=owner_id)).records) == 1
    interrupted_summary = await summaries.load(
        principal=owner_id,
        submission_id=lookup.binding.receipt.submission_id,
        attempt_id=attempt_id,
    )
    assert interrupted_summary is not None
    assert interrupted_summary.status == "succeeded"
    active_pool = await worker_state.load_pool(profile)
    assert len(active_pool.active_reservations) == 1
    active_lease = await worker_state.load_lease(context.request.lease_state.lease.lease_id)
    assert active_lease is not None and active_lease.lease.released_at is None

    stack = build_terminal_stack()
    runtime = stack.runtime
    execution_state = stack.execution_state
    worker_state = stack.worker_state
    settlement = stack.settlement
    completion = stack.completion
    materialization = stack.materialization
    metrics = stack.metrics
    publication = stack.publication
    summaries = stack.summaries
    terminal_writer = stack.terminal_writer
    recovered = await terminal_writer.write(context)

    # Restart again after commit but before transport acknowledgement; receipt
    # and all projections must replay from persisted rows without duplication.
    stack = build_terminal_stack()
    runtime = stack.runtime
    execution_state = stack.execution_state
    worker_state = stack.worker_state
    settlement = stack.settlement
    completion = stack.completion
    materialization = stack.materialization
    metrics = stack.metrics
    publication = stack.publication
    summaries = stack.summaries
    terminal_writer = stack.terminal_writer
    redelivered = await terminal_writer.write(context)

    assert recovered.decision is WorkerHandleDecision.COMPLETE
    assert redelivered.decision is WorkerHandleDecision.COMPLETE
    assert redelivered.receipt_digest == recovered.receipt_digest
    assert capacity_release_attempts == ["interrupted", "delegated", "delegated"]
    persisted_runtime = await runtime.load(principal=owner_id, attempt_id=attempt_id)
    assert persisted_runtime is not None
    assert persisted_runtime.phase.value == "succeeded"
    persisted_execution = await execution_state.read_context(
        principal=owner_id,
        attempt_id=attempt_id,
    )
    assert persisted_execution is not None
    assert persisted_execution.outcome.status is OutcomeStatus.SUCCEEDED
    assert persisted_execution.progress.phase is ProgressPhase.SUCCEEDED
    manifest = await materialization.load_manifest(principal=owner_id, attempt_id=attempt_id)
    assert manifest is not None
    persisted_metrics = await metrics.load_all_metric_sets(principal=owner_id)
    assert persisted_metrics == (manifest.metric_set,)
    persisted_publications = await publication.load_for_attempt(
        principal=owner_id,
        attempt_id=attempt_id,
    )
    assert len(persisted_publications) == 1
    assert persisted_publications[0].accepted
    summary = await summaries.load(
        principal=owner_id,
        submission_id=lookup.binding.receipt.submission_id,
        attempt_id=attempt_id,
    )
    assert summary is not None
    assert summary.status == "succeeded"
    completions = await completion.load_completion_ledger(principal=owner_id)
    assert len(completions.records) == 1
    assert len((await completion.load_artifact_commit_ledger()).records) == len(
        manifest.output_artifacts
    )
    assert len((await settlement.load_ledger(principal=owner_id)).records) == 1
    released_pool = await worker_state.load_pool(profile)
    assert not released_pool.active_reservations
    released_lease = await worker_state.load_lease(context.request.lease_state.lease.lease_id)
    assert released_lease is not None and released_lease.lease.released_at is not None


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
