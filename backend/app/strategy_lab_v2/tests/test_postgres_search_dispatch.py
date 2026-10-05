from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.strategy_lab_v2.admission import ExecutionAdmissionLedger, resolve_execution_admission
from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.dispatch import DispatchRequest, SearchDispatchIntent
from app.strategy_lab_v2.dispatch_payload import DispatchPayload
from app.strategy_lab_v2.engine_execution import (
    EngineExecutionDecision,
    NautilusExecutionPlan,
    NautilusExecutionScope,
)
from app.strategy_lab_v2.execution_orchestration import plan_execution_orchestration
from app.strategy_lab_v2.lease_observations import LeaseObservationState
from app.strategy_lab_v2.lifecycle import ExecutionAttemptLease
from app.strategy_lab_v2.nautilus_runtime_bundle import NautilusTrialInputBinding
from app.strategy_lab_v2.postgres_search_dispatch import (
    PostgresSearchDispatchAdapter,
    PostgresSearchDispatchSchema,
)
from app.strategy_lab_v2.postgres_search_state import PostgresSearchStateAdapter
from app.strategy_lab_v2.postgres_worker_state import PostgresWorkerStateAdapter
from app.strategy_lab_v2.runtime_execution import (
    new_runtime_execution_state,
    preflight_strategy_runtime,
)
from app.strategy_lab_v2.sandbox import build_nautilus_runtime_sandbox_command
from app.strategy_lab_v2.search_dispatch import SearchDispatchDecision
from app.strategy_lab_v2.search_dispatch_preparation import (
    NautilusTrialSearchDispatchEvidenceResolver,
)
from app.strategy_lab_v2.search_state import new_search_execution_state
from app.strategy_lab_v2.strategy_validation import validate_strategy_source_set
from app.strategy_lab_v2.tests.test_admission import _fixture, _reservation
from app.strategy_lab_v2.tests.test_nautilus_trial_assembly import _inputs
from app.strategy_lab_v2.tests.test_nautilus_trial_materializer import _add_second_strategy
from app.strategy_lab_v2.tests.test_runtime_execution import _profile
from app.strategy_lab_v2.tests.test_search_dispatch_preparation import _setup as _preparation_setup
from app.strategy_lab_v2.tests.test_trial_hydration import MemoryDomainReader
from app.strategy_lab_v2.tests.test_worker_process import _request as _worker_request_fixture
from app.strategy_lab_v2.trial_hydration import NautilusTrialDomainHydrator
from app.strategy_lab_v2.worker_handoff import decode_worker_handoff, encode_worker_handoff
from app.strategy_lab_v2.worker_process import WorkerExecutionRequest
from app.strategy_lab_v2.workers import (
    WorkerKind,
    WorkerPoolState,
    WorkerProfile,
    reserve_worker_slot,
)

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
EXPERIMENT = content_digest("experiment")


def _worker_payload(
    tmp_path,
    *,
    authorization,
    runtime_request,
    runtime_preflight,
    pool: WorkerPoolState,
    reservation_id,
):
    template = _worker_request_fixture(tmp_path)
    profile = _profile()
    input_artifact = template.runtime_input_artifact
    binding = NautilusTrialInputBinding(
        attempt_id=authorization.attempt_id,
        trial_fingerprint=authorization.trial_id,
        experiment_fingerprint=EXPERIMENT,
        portfolio_fingerprint=content_digest("portfolio"),
        snapshot_fingerprint=content_digest("snapshot"),
        strategy_package_fingerprint=runtime_request.package_fingerprint,
        engine_input_fingerprint=content_digest("engine-input"),
        invocation_input_digest=content_digest("invocation-input"),
    )
    input_artifact = replace(input_artifact, trial_binding=binding)
    admission = resolve_execution_admission(
        ExecutionAdmissionLedger(),
        authorization,
        runtime_request,
        runtime_preflight,
        pool,
        reservation_id=reservation_id,
        now=NOW,
    )
    assert admission.admission is not None
    sandbox_plan = build_nautilus_runtime_sandbox_command(
        runtime_request,
        profile,
        image_name="nautilus-runtime",
        input_bundle_path=tmp_path / "runtime-input.json",
        output_path=tmp_path / "worker-result.json",
        expected_version="2.0.0",
        snapshot_fingerprint=binding.snapshot_fingerprint,
    )
    runtime_state = new_runtime_execution_state(
        runtime_preflight,
        attempt_id=authorization.attempt_id,
        output_limit_bytes=profile.output_limit_bytes,
        accepted_at=NOW,
    )
    execution_plan = NautilusExecutionPlan(
        authorization.trial_id,
        authorization.attempt_id,
        binding.snapshot_fingerprint,
        "nautilus",
        "2.0.0",
        content_digest("nautilus-build"),
        authorization.fingerprint,
        runtime_preflight.fingerprint,
        content_digest("conformance-report"),
        sandbox_plan.fingerprint,
        EngineExecutionDecision.READY,
        False,
        execution_scope=NautilusExecutionScope.BACKTEST_COMPATIBILITY,
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
    lease = ExecutionAttemptLease(
        authorization.attempt_id,
        authorization.lease_worker_id,
        authorization.lease_id,
        authorization.authorized_at,
        authorization.authorized_at,
        NOW + timedelta(days=1),
    )
    request = WorkerExecutionRequest(
        orchestration_plan,
        authorization,
        admission.admission,
        runtime_request,
        runtime_preflight,
        runtime_state,
        sandbox_plan,
        execution_plan,
        admission.pool,
        LeaseObservationState(lease),
        NOW,
        NOW,
        runtime_input_artifact=input_artifact,
        docker_binary=template.docker_binary,
    )
    return encode_worker_handoff(request)


class FakeResult:
    def __init__(self, rows=(), rowcount: int = 0) -> None:
        self._rows = list(rows)
        self.rowcount = rowcount

    def mappings(self):
        return iter(self._rows)


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeSession:
    """SQL-shape fake covering all rows touched by the atomic adapter."""

    def __init__(self) -> None:
        self.searches: dict[tuple[str, str], dict[str, Any]] = {}
        self.candidates: dict[tuple[str, str, int], dict[str, Any]] = {}
        self.profiles: dict[str, dict[str, Any]] = {}
        self.reservations: dict[str, dict[str, Any]] = {}
        self.leases: dict[str, dict[str, Any]] = {}
        self.lease_observations: dict[str, dict[str, Any]] = {}
        self.admissions: dict[tuple[str, str], dict[str, Any]] = {}
        self.dispatches: dict[tuple[str, str], dict[str, Any]] = {}
        self.payloads: dict[str, dict[str, Any]] = {}
        self.outboxes: dict[str, dict[str, Any]] = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def begin(self):
        return FakeTransaction()

    async def execute(self, statement, params=None):
        sql = str(statement)
        values = dict(params or {})
        normalized = sql.lstrip()
        if "FROM strategy_lab_v2_search_states" in sql:
            row = self.searches.get((values["owner_id"], values["experiment_fingerprint"]))
            return FakeResult([] if row is None else [row])
        if "FROM strategy_lab_v2_search_candidates" in sql:
            rows = [
                row
                for (owner, experiment, _), row in self.candidates.items()
                if owner == values["owner_id"] and experiment == values["experiment_fingerprint"]
            ]
            return FakeResult(sorted(rows, key=lambda row: row["candidate_index"]))
        if normalized.startswith("SELECT worker_id"):
            row = self.profiles.get(values["worker_id"])
            return FakeResult([] if row is None else [row])
        if "FROM strategy_lab_v2_execution_leases" in sql:
            row = self.leases.get(values["lease_id"])
            return FakeResult([] if row is None else [row])
        if "FROM strategy_lab_v2_lease_observations" in sql:
            rows = [
                row
                for row in self.lease_observations.values()
                if row["lease_id"] == values["lease_id"]
            ]
            return FakeResult(sorted(rows, key=lambda row: row["sequence"]))
        if normalized.startswith("SELECT reservation_id"):
            rows = [
                row
                for row in self.reservations.values()
                if row["worker_id"] == values["worker_id"]
                and row.get("reservation_id") == values.get("reservation_id", row["reservation_id"])
            ]
            return FakeResult(sorted(rows, key=lambda row: row["reservation_id"]))
        if "FROM strategy_lab_v2_execution_admissions" in sql:
            rows = [
                row for (owner, _), row in self.admissions.items() if owner == values["owner_id"]
            ]
            return FakeResult(sorted(rows, key=lambda row: row["request_fingerprint"]))
        if "FROM strategy_lab_v2_search_dispatches" in sql:
            rows = [
                row
                for (owner, _), row in self.dispatches.items()
                if ("owner_id" not in values or owner == values["owner_id"])
                and (
                    "experiment_fingerprint" not in values
                    or row["experiment_fingerprint"] == values["experiment_fingerprint"]
                )
                and (
                    "candidate_index" not in values
                    or row["candidate_index"] == values["candidate_index"]
                )
                and (
                    "request_fingerprint" not in values
                    or row["request_fingerprint"] == values["request_fingerprint"]
                )
                and (
                    "idempotency_key" not in values
                    or row["idempotency_key"] == values["idempotency_key"]
                )
            ]
            return FakeResult(sorted(rows, key=lambda row: row["request_fingerprint"]))
        if "FROM strategy_lab_v2_dispatch_payloads" in sql:
            row = self.payloads.get(values["payload_digest"])
            return FakeResult([] if row is None else [row])
        if normalized.startswith("INSERT INTO strategy_lab_v2_search_states"):
            key = (values["owner_id"], values["experiment_fingerprint"])
            if key in self.searches:
                return FakeResult(rowcount=0)
            self.searches[key] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("INSERT INTO strategy_lab_v2_search_candidates"):
            key = (values["owner_id"], values["experiment_fingerprint"], values["candidate_index"])
            if key in self.candidates:
                return FakeResult(rowcount=0)
            self.candidates[key] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("INSERT INTO strategy_lab_v2_worker_profiles"):
            if values["worker_id"] in self.profiles:
                return FakeResult(rowcount=0)
            self.profiles[values["worker_id"]] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("INSERT INTO strategy_lab_v2_worker_reservations"):
            if values["reservation_id"] in self.reservations:
                return FakeResult(rowcount=0)
            self.reservations[values["reservation_id"]] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("INSERT INTO strategy_lab_v2_execution_leases"):
            if values["lease_id"] in self.leases:
                return FakeResult(rowcount=0)
            self.leases[values["lease_id"]] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("INSERT INTO strategy_lab_v2_lease_observations"):
            if values["observation_id"] in self.lease_observations:
                return FakeResult(rowcount=0)
            self.lease_observations[values["observation_id"]] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("INSERT INTO strategy_lab_v2_execution_admissions"):
            key = (values["owner_id"], values["request_fingerprint"])
            if key in self.admissions:
                return FakeResult(rowcount=0)
            self.admissions[key] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("INSERT INTO strategy_lab_v2_search_dispatches"):
            key = (values["owner_id"], values["idempotency_key"])
            if key in self.dispatches:
                return FakeResult(rowcount=0)
            self.dispatches[key] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("INSERT INTO strategy_lab_v2_dispatch_payloads"):
            key = values["payload_digest"]
            if key in self.payloads:
                return FakeResult(rowcount=0)
            self.payloads[key] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("INSERT INTO strategy_lab_v2_execution_outbox"):
            key = values["message_id"]
            if key in self.outboxes:
                return FakeResult(rowcount=0)
            self.outboxes[key] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("UPDATE") and "strategy_lab_v2_search_candidates" in sql:
            key = (values["owner_id"], values["experiment_fingerprint"], values["candidate_index"])
            row = self.candidates.get(key)
            if row is None or row["state_fingerprint"] != values["expected_state_fingerprint"]:
                return FakeResult(rowcount=0)
            self.candidates[key] = values
            return FakeResult(rowcount=1)
        if normalized.startswith("UPDATE") and "strategy_lab_v2_search_states" in sql:
            key = (values["owner_id"], values["experiment_fingerprint"])
            row = self.searches.get(key)
            if row is None or row["state_fingerprint"] != values["expected_state_fingerprint"]:
                return FakeResult(rowcount=0)
            self.searches[key] = values
            return FakeResult(rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")


async def _persist_handoff_lease(worker_state: PostgresWorkerStateAdapter, payload) -> None:
    request = decode_worker_handoff(DispatchPayload.from_mapping(payload))
    await worker_state.persist_lease(request.lease_state.lease)


@pytest.mark.asyncio
async def test_postgres_search_dispatch_stages_and_replays_all_rows_atomically(tmp_path) -> None:
    session = FakeSession()
    search_state = PostgresSearchStateAdapter(lambda: session)
    worker_state = PostgresWorkerStateAdapter(lambda: session)
    adapter = PostgresSearchDispatchAdapter(
        lambda: session, search_state=search_state, worker_state=worker_state
    )
    authorization, runtime_request, runtime_preflight, pool = _fixture()
    await search_state.initialize(
        principal="owner-1",
        state=new_search_execution_state(EXPERIMENT, (content_digest("trial-1"),), now=NOW),
    )
    await worker_state.ensure_profile(pool.profile)
    reservation_id = _reservation("one")
    payload = _worker_payload(
        tmp_path,
        authorization=authorization,
        runtime_request=runtime_request,
        runtime_preflight=runtime_preflight,
        pool=pool,
        reservation_id=reservation_id,
    )
    await _persist_handoff_lease(worker_state, payload)
    request = DispatchRequest(
        "dispatch-key",
        authorization.attempt_id,
        DispatchPayload.from_mapping(payload).payload_digest,
        "strategy-backtest",
        NOW,
    )

    first = await adapter.dispatch(
        principal="owner-1",
        experiment_fingerprint=EXPERIMENT,
        candidate_index=0,
        attempt_id=authorization.attempt_id,
        authorization=authorization,
        runtime_request=runtime_request,
        runtime_preflight=runtime_preflight,
        reservation_id=reservation_id,
        dispatch_request=request,
        payload=payload,
        now=NOW,
    )
    assert first.decision is SearchDispatchDecision.ENQUEUE
    assert len(session.admissions) == 1
    assert len(session.reservations) == 1
    assert len(session.dispatches) == 1
    assert len(session.payloads) == 1
    assert len(session.outboxes) == 1
    assert session.candidates[("owner-1", EXPERIMENT, 0)]["phase"] == "running"

    replay_before_preparation = await adapter.replay_idempotency(
        principal="owner-1",
        experiment_fingerprint=EXPERIMENT,
        candidate_index=0,
        attempt_id=authorization.attempt_id,
        dispatch_intent=SearchDispatchIntent(
            request.idempotency_key,
            request.attempt_id,
            request.queue_name,
            request.created_at,
        ),
    )
    assert replay_before_preparation is not None
    assert replay_before_preparation.decision is SearchDispatchDecision.REPLAY_EXISTING
    assert replay_before_preparation.envelope is not None
    assert replay_before_preparation.envelope.request == request

    conflicting_retry = await adapter.replay_idempotency(
        principal="owner-1",
        experiment_fingerprint=EXPERIMENT,
        candidate_index=1,
        attempt_id=authorization.attempt_id,
        dispatch_intent=SearchDispatchIntent(
            request.idempotency_key,
            request.attempt_id,
            request.queue_name,
            request.created_at,
        ),
    )
    assert conflicting_retry is not None
    assert conflicting_retry.decision is SearchDispatchDecision.CONFLICT

    replay = await adapter.dispatch(
        principal="owner-1",
        experiment_fingerprint=EXPERIMENT,
        candidate_index=0,
        attempt_id=authorization.attempt_id,
        authorization=authorization,
        runtime_request=runtime_request,
        runtime_preflight=runtime_preflight,
        reservation_id=reservation_id,
        dispatch_request=request,
        payload=payload,
        now=NOW,
    )
    assert replay.decision is SearchDispatchDecision.REPLAY_EXISTING
    assert len(session.admissions) == 1
    assert len(session.reservations) == 1
    assert len(session.dispatches) == 1
    assert len(session.payloads) == 1
    assert len(session.outboxes) == 1


@pytest.mark.asyncio
async def test_postgres_search_dispatch_rejects_admission_drift_before_any_insert(tmp_path) -> None:
    session = FakeSession()
    search_state = PostgresSearchStateAdapter(lambda: session)
    worker_state = PostgresWorkerStateAdapter(lambda: session)
    adapter = PostgresSearchDispatchAdapter(
        lambda: session, search_state=search_state, worker_state=worker_state
    )
    authorization, runtime_request, runtime_preflight, pool = _fixture()
    await search_state.initialize(
        principal="owner-1",
        state=new_search_execution_state(EXPERIMENT, (authorization.trial_id,), now=NOW),
    )
    await worker_state.ensure_profile(pool.profile)
    reservation_id = _reservation("atomic-drift")
    worker_payload = _worker_payload(
        tmp_path,
        authorization=authorization,
        runtime_request=runtime_request,
        runtime_preflight=runtime_preflight,
        pool=pool,
        reservation_id=reservation_id,
    )
    await _persist_handoff_lease(worker_state, worker_payload)
    worker_request = decode_worker_handoff(DispatchPayload.from_mapping(worker_payload))
    drifted_admission = replace(
        worker_request.admission,
        admitted_at=NOW - timedelta(seconds=1),
    )
    drifted_orchestration = plan_execution_orchestration(
        worker_request.authorization,
        drifted_admission,
        worker_request.runtime_request,
        worker_request.runtime_preflight,
        worker_request.runtime_state,
        worker_request.sandbox_plan,
        worker_request.execution_plan,
    )
    drifted_request = replace(
        worker_request,
        admission=drifted_admission,
        orchestration_plan=drifted_orchestration,
    )
    payload = encode_worker_handoff(drifted_request)
    dispatch_request = DispatchRequest(
        "dispatch-key",
        authorization.attempt_id,
        DispatchPayload.from_mapping(payload).payload_digest,
        "strategy-backtest",
        NOW,
    )

    with pytest.raises(ValueError, match="differs from atomic PostgreSQL admission"):
        await adapter.dispatch(
            principal="owner-1",
            experiment_fingerprint=EXPERIMENT,
            candidate_index=0,
            attempt_id=authorization.attempt_id,
            authorization=authorization,
            runtime_request=runtime_request,
            runtime_preflight=runtime_preflight,
            reservation_id=reservation_id,
            dispatch_request=dispatch_request,
            payload=payload,
            now=NOW,
        )

    assert not session.admissions
    assert not session.reservations
    assert not session.dispatches
    assert not session.payloads
    assert not session.outboxes
    assert session.candidates[("owner-1", EXPERIMENT, 0)]["phase"] == "pending"


@pytest.mark.asyncio
async def test_postgres_search_dispatch_rejects_persisted_lease_drift_before_any_insert(
    tmp_path,
) -> None:
    session = FakeSession()
    search_state = PostgresSearchStateAdapter(lambda: session)
    worker_state = PostgresWorkerStateAdapter(lambda: session)
    adapter = PostgresSearchDispatchAdapter(
        lambda: session,
        search_state=search_state,
        worker_state=worker_state,
    )
    authorization, runtime_request, runtime_preflight, pool = _fixture()
    await search_state.initialize(
        principal="owner-1",
        state=new_search_execution_state(EXPERIMENT, (authorization.trial_id,), now=NOW),
    )
    await worker_state.ensure_profile(pool.profile)
    reservation_id = _reservation("lease-drift")
    original_payload = _worker_payload(
        tmp_path,
        authorization=authorization,
        runtime_request=runtime_request,
        runtime_preflight=runtime_preflight,
        pool=pool,
        reservation_id=reservation_id,
    )
    original = decode_worker_handoff(DispatchPayload.from_mapping(original_payload))
    await worker_state.persist_lease(original.lease_state.lease)

    drifted_lease = replace(
        original.lease_state.lease,
        expires_at=original.lease_state.lease.expires_at + timedelta(days=1),
    )
    drifted_request = replace(
        original,
        lease_state=LeaseObservationState(drifted_lease),
    )
    payload = encode_worker_handoff(drifted_request)
    dispatch_request = DispatchRequest(
        "dispatch-key",
        authorization.attempt_id,
        DispatchPayload.from_mapping(payload).payload_digest,
        "strategy-backtest",
        NOW,
    )

    with pytest.raises(ValueError, match="differs from persisted PostgreSQL lease"):
        await adapter.dispatch(
            principal="owner-1",
            experiment_fingerprint=EXPERIMENT,
            candidate_index=0,
            attempt_id=authorization.attempt_id,
            authorization=authorization,
            runtime_request=runtime_request,
            runtime_preflight=runtime_preflight,
            reservation_id=reservation_id,
            dispatch_request=dispatch_request,
            payload=payload,
            now=NOW,
        )

    assert not session.admissions
    assert not session.reservations
    assert not session.dispatches
    assert not session.payloads
    assert not session.outboxes
    assert session.candidates[("owner-1", EXPERIMENT, 0)]["phase"] == "pending"


@pytest.mark.asyncio
async def test_postgres_search_dispatch_loads_owner_scoped_and_worker_request_identity(
    tmp_path,
) -> None:
    session = FakeSession()
    search_state = PostgresSearchStateAdapter(lambda: session)
    worker_state = PostgresWorkerStateAdapter(lambda: session)
    adapter = PostgresSearchDispatchAdapter(
        lambda: session, search_state=search_state, worker_state=worker_state
    )
    authorization, runtime_request, runtime_preflight, pool = _fixture()
    source_validation = validate_strategy_source_set(
        {
            content_digest("strategy-a"): "def run(context):\n    return None\n",
            content_digest("strategy-b"): "def run(context):\n    return None\n",
        }
    )
    assert source_validation.accepted
    authorization = replace(authorization, source_digest=source_validation.source_digest)
    runtime_request = replace(runtime_request, source_digest=source_validation.source_digest)
    runtime_preflight = preflight_strategy_runtime(runtime_request, _profile())
    await search_state.initialize(
        principal="owner-1",
        state=new_search_execution_state(EXPERIMENT, (content_digest("trial-1"),), now=NOW),
    )
    await worker_state.ensure_profile(pool.profile)
    reservation_id = _reservation("one")
    payload = _worker_payload(
        tmp_path,
        authorization=authorization,
        runtime_request=runtime_request,
        runtime_preflight=runtime_preflight,
        pool=pool,
        reservation_id=reservation_id,
    )
    await _persist_handoff_lease(worker_state, payload)
    request = DispatchRequest(
        "dispatch-key",
        authorization.attempt_id,
        DispatchPayload.from_mapping(payload).payload_digest,
        "strategy-backtest",
        NOW,
    )
    await adapter.dispatch(
        principal="owner-1",
        experiment_fingerprint=EXPERIMENT,
        candidate_index=0,
        attempt_id=authorization.attempt_id,
        authorization=authorization,
        runtime_request=runtime_request,
        runtime_preflight=runtime_preflight,
        reservation_id=reservation_id,
        dispatch_request=request,
        payload=payload,
        now=NOW,
    )

    owner_record = await adapter.load(
        principal="owner-1", experiment_fingerprint=EXPERIMENT, candidate_index=0
    )
    worker_record = await adapter.load_by_request_fingerprint(request.fingerprint)
    assert owner_record is not None
    assert worker_record == owner_record
    assert worker_record.request.attempt_id == authorization.attempt_id
    stored_payload = session.payloads[worker_record.request.payload_digest]
    stored_worker_request = decode_worker_handoff(
        DispatchPayload(
            stored_payload["payload_digest"],
            stored_payload["payload_json"],
            stored_payload["byte_length"],
        )
    )
    assert stored_worker_request.authorization.source_digest == source_validation.source_digest
    assert stored_worker_request.runtime_request.source_digest == source_validation.source_digest

    replay = await adapter.replay_idempotency(
        principal="owner-1",
        experiment_fingerprint=EXPERIMENT,
        candidate_index=0,
        attempt_id=authorization.attempt_id,
        dispatch_intent=SearchDispatchIntent(
            request.idempotency_key,
            request.attempt_id,
            request.queue_name,
            request.created_at,
        ),
    )
    assert replay is not None
    assert replay.decision is SearchDispatchDecision.REPLAY_EXISTING
    assert replay.envelope is not None
    assert replay.envelope.request.payload_digest == request.payload_digest
    assert (
        await adapter.load(
            principal="owner-2", experiment_fingerprint=EXPERIMENT, candidate_index=0
        )
        is None
    )


@pytest.mark.asyncio
async def test_owner_hydrated_multi_strategy_trial_reaches_persisted_dispatch_and_replay(
    tmp_path,
) -> None:
    graph, store, package_resolver, materializer, context, worker_state_reader = _preparation_setup(
        tmp_path
    )
    original_pool = next(iter(worker_state_reader.pools.values()))
    busy_pool = reserve_worker_slot(
        original_pool,
        attempt_id="other-attempt",
        reservation_id=content_digest("postgres-search-dispatch-busy-slot"),
        acquired_at=context.now,
    ).pool
    selected_profile = WorkerProfile(
        "dispatch-preparation-worker-2",
        WorkerKind.BACKTEST,
        original_pool.profile.runtime_profile_fingerprint,
    )
    worker_state_reader.pools = {
        busy_pool.profile.worker_id: busy_pool,
        selected_profile.worker_id: WorkerPoolState(selected_profile),
    }
    graph = _add_second_strategy(_inputs(), graph, store)
    reader = MemoryDomainReader(
        {
            "attempt": graph.attempt,
            "trial": graph.trial,
            "experiment": graph.experiment,
            "portfolio": graph.portfolio,
            "snapshot": graph.snapshot,
            "strategies": graph.strategies,
            "packages": graph.packages,
        },
        owner="owner-1",
    )
    resolver = NautilusTrialSearchDispatchEvidenceResolver(
        domain_hydrator=NautilusTrialDomainHydrator(reader),
        runtime_materializer=materializer,
        strategy_package_resolver=package_resolver,
        artifact_store=store,
        worker_state_reader=worker_state_reader,
        context_resolver=lambda _request, _graph: context,
    )
    session = FakeSession()
    search_state = PostgresSearchStateAdapter(lambda: session)
    worker_state = PostgresWorkerStateAdapter(lambda: session)
    adapter = PostgresSearchDispatchAdapter(
        lambda: session,
        search_state=search_state,
        worker_state=worker_state,
    )
    await search_state.initialize(
        principal="owner-1",
        state=new_search_execution_state(
            graph.experiment.fingerprint,
            (graph.trial.trial_id,),
            now=context.now,
        ),
    )
    await worker_state.ensure_profile(selected_profile)
    intent = SearchDispatchIntent(
        "owner-hydrated-multi-strategy-dispatch",
        graph.attempt.attempt_id,
        "strategy-backtest",
        context.now,
    )
    evidence = await resolver(
        principal="owner-1",
        request_id="owner-hydrated-multi-strategy-request",
        experiment_fingerprint=graph.experiment.fingerprint,
        candidate_index=0,
        attempt_id=graph.attempt.attempt_id,
        dispatch_intent=intent,
    )
    await worker_state.persist_lease(evidence.worker_request.lease_state.lease)
    payload = encode_worker_handoff(evidence.worker_request)
    payload_record = DispatchPayload.from_mapping(payload)
    request = intent.bind_payload(payload_record.payload_digest)

    resolution = await adapter.dispatch(
        principal="owner-1",
        experiment_fingerprint=graph.experiment.fingerprint,
        candidate_index=0,
        attempt_id=graph.attempt.attempt_id,
        authorization=evidence.authorization,
        runtime_request=evidence.trial_runtime_evidence.runtime_request,
        runtime_preflight=evidence.trial_runtime_evidence.runtime_preflight,
        reservation_id=evidence.reservation_id,
        dispatch_request=request,
        payload=payload,
        now=evidence.now,
    )

    assert len(graph.strategies) == 2
    assert evidence.worker_request.worker_pool.profile == selected_profile
    assert reader.calls[0] == ("id", ApiResourceType.ATTEMPT, (graph.attempt.attempt_id,))
    assert evidence.authorization.source_digest != graph.strategies[0].source_digest
    assert resolution.decision is SearchDispatchDecision.ENQUEUE
    dispatch_record = await adapter.load(
        principal="owner-1",
        experiment_fingerprint=graph.experiment.fingerprint,
        candidate_index=0,
    )
    assert dispatch_record is not None
    persisted_payload = session.payloads[dispatch_record.request.payload_digest]
    decoded_worker_request = decode_worker_handoff(
        DispatchPayload(
            persisted_payload["payload_digest"],
            persisted_payload["payload_json"],
            persisted_payload["byte_length"],
        )
    )
    assert decoded_worker_request.authorization == evidence.authorization
    assert (
        decoded_worker_request.runtime_request.source_digest == evidence.authorization.source_digest
    )

    replay = await adapter.replay_idempotency(
        principal="owner-1",
        experiment_fingerprint=graph.experiment.fingerprint,
        candidate_index=0,
        attempt_id=graph.attempt.attempt_id,
        dispatch_intent=intent,
    )
    assert replay is not None
    assert replay.decision is SearchDispatchDecision.REPLAY_EXISTING
    assert replay.envelope is not None
    assert replay.envelope.request.payload_digest == request.payload_digest


def test_postgres_search_dispatch_schema_is_additive_and_safe() -> None:
    schema = PostgresSearchDispatchSchema()
    assert len(schema.statements) == 3
    assert all("CREATE TABLE" in statement for statement in schema.statements)
    with pytest.raises(ValueError, match="safe SQL identifier"):
        PostgresSearchDispatchSchema(dispatch_table="unsafe;drop")
