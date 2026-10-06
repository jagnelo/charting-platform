from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.api_router import ApiAdapterError
from app.strategy_lab_v2.application import PostgresStrategyLabV2Adapter
from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import MetricBasis, MetricValue, ScientificTrial
from app.strategy_lab_v2.dispatch import DispatchRequest
from app.strategy_lab_v2.experiments import WalkForwardMode, WalkForwardSpec
from app.strategy_lab_v2.postgres_search_dispatch import SearchDispatchRecord
from app.strategy_lab_v2.postgres_walk_forward_plan import (
    WalkForwardDefinitionDecision,
    WalkForwardDefinitionResolution,
)
from app.strategy_lab_v2.postgres_walk_forward_summary import (
    PostgresWalkForwardNativeMetricsAdapter,
    PostgresWalkForwardSummaryAdapter,
)
from app.strategy_lab_v2.resource_domains import normalize_resource_attributes
from app.strategy_lab_v2.search_dispatch import SearchDispatchDecision
from app.strategy_lab_v2.search_state import (
    SearchCandidatePhase,
    SearchStateDecision,
    SearchStateResolution,
    append_search_candidates,
    record_search_candidate_terminal,
    start_search_candidate,
)
from app.strategy_lab_v2.tests.test_nautilus_trial_assembly import _inputs
from app.strategy_lab_v2.tests.test_walk_forward_plan_persistence import MemoryAggregateStore
from app.strategy_lab_v2.tests.test_walk_forward_search import _authoritative_result
from app.strategy_lab_v2.walk_forward_queue import initialize_walk_forward_training_queue
from app.strategy_lab_v2.walk_forward_search import (
    SelectionDirection,
    WalkForwardDefinitionRequest,
    WalkForwardExecutionDefinition,
    select_walk_forward_oos_tasks,
)
from app.strategy_lab_v2.walk_forward_trials import (
    materialize_walk_forward_oos_trials,
    materialize_walk_forward_training_trials,
    training_score_from_result_manifest,
)


class User:
    id = 42


def _setup(*, second_experiment: str | None = None):
    values = _inputs()
    original: ScientificTrial = values["trial"]
    second_experiment_fingerprint = second_experiment or original.experiment_fingerprint
    second = ScientificTrial.create(
        experiment_fingerprint=second_experiment_fingerprint,
        snapshot_fingerprint=original.snapshot_fingerprint,
        preflight_report=original.preflight_report,
        parameter_set={"window": 21},
        scenario=original.scenario,
        seed=original.seed,
        randomization=(original.randomization if second_experiment is None else None),
    )
    series = values["snapshot"].series[0]
    boundaries = (
        series.start,
        datetime(2024, 1, 3, tzinfo=UTC),
        series.end,
    )
    definition = WalkForwardExecutionDefinition(
        experiment_fingerprint=values["experiment"].fingerprint,
        candidate_fingerprints=(original.trial_id, second.trial_id),
        observation_boundaries=boundaries,
        spec=WalkForwardSpec(1, 1, 1, WalkForwardMode.ROLLING),
        metric_id="net_return",
        direction=SelectionDirection.MAXIMIZE,
    )
    contracts = {
        (ApiResourceType.EXPERIMENT, values["experiment"].fingerprint): values["experiment"],
        (ApiResourceType.SNAPSHOT, values["snapshot"].fingerprint): values["snapshot"],
        (ApiResourceType.TRIAL, original.trial_id): original,
        (ApiResourceType.TRIAL, second.trial_id): second,
    }

    class Reader:
        def __init__(self) -> None:
            self.missing: set[tuple[ApiResourceType, str]] = set()
            self.contracts = contracts

        async def get_domain_contract_by_fingerprint(self, **kwargs: Any) -> Any:
            assert kwargs["principal"].id == "42"
            key = (kwargs["resource_type"], kwargs["fingerprint"])
            return None if key in self.missing else self.contracts.get(key)

        async def get_domain_contracts_by_fingerprint(self, **kwargs: Any) -> Any:
            assert kwargs["principal"].id == "42"
            return {
                fingerprint: self.contracts[(kwargs["resource_type"], fingerprint)]
                for fingerprint in kwargs["fingerprints"]
                if (kwargs["resource_type"], fingerprint) in self.contracts
                and (kwargs["resource_type"], fingerprint) not in self.missing
            }

    class PlanStore:
        def __init__(self) -> None:
            self.received: tuple[str, WalkForwardExecutionDefinition] | None = None

        async def persist(self, *, principal: Any, definition: WalkForwardExecutionDefinition):
            self.received = (principal.id, definition)
            return WalkForwardDefinitionResolution(
                WalkForwardDefinitionDecision.APPLY,
                definition,
                aggregate_version=1,
            )

        async def load(self, *, principal: Any, experiment_fingerprint: str):
            assert principal.id == "42"
            assert experiment_fingerprint == definition.experiment_fingerprint
            return definition

    class SearchStateStore:
        def __init__(self) -> None:
            self.states: dict[str, Any] = {}

        async def initialize(self, *, principal: Any, state: Any):
            assert principal.id == "42"
            current = self.states.get(state.experiment_fingerprint)
            if current is not None and current != state:
                return SearchStateResolution(
                    SearchStateDecision.REJECT,
                    current,
                    rejection_reason="different search state",
                )
            self.states[state.experiment_fingerprint] = state
            return SearchStateResolution(
                SearchStateDecision.REPLAY_EXISTING if current else SearchStateDecision.APPLY,
                current or state,
            )

        async def load(self, *, principal: Any, experiment_fingerprint: str):
            assert principal.id == "42"
            return self.states.get(experiment_fingerprint)

        async def append_candidates(
            self,
            *,
            principal: Any,
            experiment_fingerprint: str,
            expected_state_fingerprint: str,
            trial_fingerprints: tuple[str, ...],
            now: datetime,
        ):
            assert principal.id == "42"
            current = self.states[experiment_fingerprint]
            if current.fingerprint != expected_state_fingerprint:
                replay = append_search_candidates(current, trial_fingerprints, now=now)
                if replay.decision is SearchStateDecision.REPLAY_EXISTING:
                    return replay
                return SearchStateResolution(
                    SearchStateDecision.REJECT,
                    current,
                    rejection_reason="search state changed before phase append",
                )
            resolution = append_search_candidates(current, trial_fingerprints, now=now)
            if resolution.decision is not SearchStateDecision.REJECT:
                self.states[experiment_fingerprint] = resolution.state
            return resolution

    class ResultMaterialization:
        def __init__(self) -> None:
            self.manifests: dict[str, Any] = {}

        async def load_manifest(self, *, principal: Any, attempt_id: str):
            assert principal.id == "42"
            return self.manifests.get(attempt_id)

    reader = Reader()
    plan_store = PlanStore()
    search_state_store = SearchStateStore()
    result_materialization = ResultMaterialization()
    adapter = cast(Any, object.__new__(PostgresStrategyLabV2Adapter))
    adapter._resources = reader
    adapter._persistence = SimpleNamespace(
        walk_forward_plans=plan_store,
        search_state=search_state_store,
        result_materialization=result_materialization,
        walk_forward_summaries=PostgresWalkForwardSummaryAdapter(MemoryAggregateStore()),
        walk_forward_native_metrics=PostgresWalkForwardNativeMetricsAdapter(MemoryAggregateStore()),
    )
    adapter._walk_forward_artifact_store = None
    adapter._clock = lambda: datetime(2026, 10, 6, tzinfo=UTC)
    published_trials: list[str] = []

    async def create_resource(*, principal: Any, request_id: str, request: Any):
        assert principal.id == "42"
        attributes = request.payload["attributes"]
        normalized = normalize_resource_attributes(request.resource_type, attributes)
        if request.resource_type is ApiResourceType.TRIAL:
            trial = normalized.typed_contract
            assert isinstance(trial, ScientificTrial)
            assert trial.trial_id == attributes["trial_id"]
            reader.contracts[(ApiResourceType.TRIAL, trial.trial_id)] = trial
            if trial.trial_id not in published_trials:
                published_trials.append(trial.trial_id)
        elif request.resource_type is ApiResourceType.ATTEMPT:
            attempt = normalized.typed_contract
            reader.contracts[(ApiResourceType.ATTEMPT, normalized.domain_fingerprint)] = attempt
        else:
            raise AssertionError("unexpected walk-forward resource type")
        return SimpleNamespace(
            receipt=SimpleNamespace(
                resource=SimpleNamespace(
                    attributes=normalized.attributes,
                    meta={"domain_fingerprint": normalized.domain_fingerprint},
                )
            )
        )

    adapter.create_resource = create_resource
    adapter._published_trials = published_trials
    adapter._result_materialization = result_materialization
    return adapter, reader, plan_store, definition, original, second


@pytest.mark.asyncio
async def test_application_persists_only_owner_bound_base_trials() -> None:
    adapter, _reader, plan_store, definition, _first, _second = _setup()

    result = await adapter.persist_walk_forward_definition(
        principal=User(),
        definition=definition,
    )

    assert result.decision is WalkForwardDefinitionDecision.APPLY
    assert plan_store.received == ("42", definition)


@pytest.mark.asyncio
async def test_application_rejects_missing_or_rebound_base_trials_before_persisting() -> None:
    adapter, reader, plan_store, definition, _first, second = _setup()
    reader.missing.add((ApiResourceType.TRIAL, second.trial_id))

    with pytest.raises(ValueError, match="unavailable to this owner"):
        await adapter.persist_walk_forward_definition(principal=User(), definition=definition)
    assert plan_store.received is None

    adapter, _reader, plan_store, definition, _first, _second = _setup(
        second_experiment=content_digest("foreign experiment")
    )
    with pytest.raises(ValueError, match="differs from its experiment snapshot"):
        await adapter.persist_walk_forward_definition(principal=User(), definition=definition)
    assert plan_store.received is None


@pytest.mark.asyncio
async def test_application_builds_definition_only_from_host_verified_calendar() -> None:
    adapter, _reader, plan_store, definition, first, second = _setup()
    observed: dict[str, Any] = {}
    boundaries = definition.observation_boundaries

    async def resolve_calendar(**kwargs: Any):
        observed.update(kwargs)
        return boundaries

    adapter._walk_forward_observation_calendar = resolve_calendar
    request = WalkForwardDefinitionRequest(
        candidate_fingerprints=(first.trial_id, second.trial_id),
        spec=definition.spec,
        metric_id=definition.metric_id,
        direction=definition.direction,
        max_tasks=definition.max_tasks,
    )

    result = await adapter.create_walk_forward_definition(
        principal=User(),
        request_id="request-1",
        idempotency_key="walk-forward-create-1",
        experiment_fingerprint=definition.experiment_fingerprint,
        request=request,
    )

    assert result.decision is WalkForwardDefinitionDecision.APPLY
    assert plan_store.received == ("42", result.definition)
    assert result.definition.fingerprint == definition.fingerprint
    assert observed["principal"].id == "42"
    assert observed["snapshot"].fingerprint == first.snapshot_fingerprint
    assert tuple(item.trial_id for item in observed["candidates"]) == request.candidate_fingerprints
    queue = adapter._persistence.search_state.states[definition.experiment_fingerprint]
    assert tuple(item.trial_fingerprint for item in queue.candidates) == tuple(
        adapter._published_trials
    )
    assert queue.updated_at is None
    replay = await adapter.initialize_walk_forward_training(
        principal=User(),
        request_id="request-replay",
        definition=result.definition,
    )
    assert replay.decision is SearchStateDecision.REPLAY_EXISTING
    assert adapter._persistence.search_state.states[definition.experiment_fingerprint] == queue
    assert len(adapter._published_trials) == len(queue.candidates)

    progressed = start_search_candidate(
        queue,
        0,
        attempt_id="training-attempt-0",
        now=datetime(2026, 10, 6, 1, tzinfo=UTC),
    ).state
    adapter._persistence.search_state.states[definition.experiment_fingerprint] = progressed
    resumed = await adapter.initialize_walk_forward_training(
        principal=User(),
        request_id="request-resume",
        definition=result.definition,
    )
    assert resumed.decision is SearchStateDecision.REPLAY_EXISTING
    assert resumed.state == progressed
    assert resumed.state.candidates[0].phase is SearchCandidatePhase.RUNNING


@pytest.mark.asyncio
async def test_application_fails_closed_without_verified_calendar_binding() -> None:
    adapter, _reader, plan_store, definition, first, second = _setup()
    request = WalkForwardDefinitionRequest(
        candidate_fingerprints=(first.trial_id, second.trial_id),
        spec=definition.spec,
        metric_id=definition.metric_id,
        direction=definition.direction,
    )

    with pytest.raises(ApiAdapterError, match="calendar resolution is not configured"):
        await adapter.create_walk_forward_definition(
            principal=User(),
            request_id="request-1",
            idempotency_key="walk-forward-create-1",
            experiment_fingerprint=definition.experiment_fingerprint,
            request=request,
        )
    assert plan_store.received is None


@pytest.mark.asyncio
async def test_training_dispatch_persists_and_replays_attempt_before_host_dispatch() -> None:
    adapter, reader, _plan_store, definition, first, second = _setup()
    boundaries = definition.observation_boundaries

    async def resolve_calendar(**_kwargs: Any):
        return boundaries

    observed: list[dict[str, Any]] = []

    async def dispatch(**kwargs: Any):
        observed.append(kwargs)
        return SimpleNamespace(decision="captured")

    adapter._walk_forward_observation_calendar = resolve_calendar
    adapter.dispatch_search_candidate = dispatch
    request = WalkForwardDefinitionRequest(
        candidate_fingerprints=(first.trial_id, second.trial_id),
        spec=definition.spec,
        metric_id=definition.metric_id,
        direction=definition.direction,
        max_tasks=definition.max_tasks,
    )
    await adapter.create_walk_forward_definition(
        principal=User(),
        request_id="create-for-dispatch",
        idempotency_key="walk-forward-create-for-dispatch",
        experiment_fingerprint=definition.experiment_fingerprint,
        request=request,
    )

    first_result = await adapter.dispatch_walk_forward_training_candidate(
        principal=User(),
        request_id="dispatch-1",
        idempotency_key="walk-forward-dispatch-0",
        experiment_fingerprint=definition.experiment_fingerprint,
        candidate_index=0,
        queue_name="strategy-backtest",
    )
    second_result = await adapter.dispatch_walk_forward_training_candidate(
        principal=User(),
        request_id="dispatch-replay",
        idempotency_key="walk-forward-dispatch-0",
        experiment_fingerprint=definition.experiment_fingerprint,
        candidate_index=0,
        queue_name="strategy-backtest",
    )

    assert first_result == second_result
    assert len(observed) == 2
    first_intent = observed[0]["dispatch_intent"]
    replay_intent = observed[1]["dispatch_intent"]
    assert first_intent == replay_intent
    assert first_intent.idempotency_key == "walk-forward-dispatch-0"
    assert first_intent.attempt_id == observed[0]["attempt_id"]
    assert observed[0]["candidate_index"] == 0
    assert observed[0]["experiment_fingerprint"] == definition.experiment_fingerprint
    state = adapter._persistence.search_state.states[definition.experiment_fingerprint]
    started = start_search_candidate(
        state,
        0,
        attempt_id=first_intent.attempt_id,
        now=datetime(2026, 10, 6, 1, tzinfo=UTC),
    )
    failed = record_search_candidate_terminal(
        started.state,
        0,
        attempt_id=first_intent.attempt_id,
        phase=SearchCandidatePhase.FAILED,
        now=datetime(2026, 10, 6, 1, 1, tzinfo=UTC),
    )
    adapter._persistence.search_state.states[definition.experiment_fingerprint] = failed.state
    await adapter.dispatch_walk_forward_training_candidate(
        principal=User(),
        request_id="dispatch-retry",
        idempotency_key="walk-forward-dispatch-retry",
        experiment_fingerprint=definition.experiment_fingerprint,
        candidate_index=0,
        queue_name="strategy-backtest",
    )
    assert observed[2]["attempt_id"] != first_intent.attempt_id
    assert any(
        getattr(attempt, "ordinal", None) == 2
        and getattr(attempt, "attempt_id", None) == observed[2]["attempt_id"]
        for (resource_type, _fingerprint), attempt in reader.contracts.items()
        if resource_type is ApiResourceType.ATTEMPT
    )


@pytest.mark.asyncio
async def test_bulk_dispatch_replays_each_slot_with_stable_distinct_idempotency_keys() -> None:
    adapter, _reader, _plan_store, definition, first, second = _setup()

    async def resolve_calendar(**_kwargs: Any):
        return definition.observation_boundaries

    observed: list[dict[str, Any]] = []

    async def dispatch(**kwargs: Any):
        observed.append(kwargs)
        return SimpleNamespace(decision=SearchDispatchDecision.ENQUEUE)

    adapter._walk_forward_observation_calendar = resolve_calendar
    adapter.dispatch_search_candidate = dispatch
    await adapter.create_walk_forward_definition(
        principal=User(),
        request_id="bulk-create",
        idempotency_key="bulk-create-key",
        experiment_fingerprint=definition.experiment_fingerprint,
        request=WalkForwardDefinitionRequest(
            candidate_fingerprints=(first.trial_id, second.trial_id),
            spec=definition.spec,
            metric_id=definition.metric_id,
            direction=definition.direction,
            max_tasks=definition.max_tasks,
        ),
    )

    first_batch = await adapter.dispatch_walk_forward_ready_candidates(
        principal=User(),
        request_id="bulk-request",
        idempotency_key="bulk-key",
        experiment_fingerprint=definition.experiment_fingerprint,
        queue_name="strategy-backtest",
    )
    replay = await adapter.dispatch_walk_forward_ready_candidates(
        principal=User(),
        request_id="bulk-request-replay",
        idempotency_key="bulk-key",
        experiment_fingerprint=definition.experiment_fingerprint,
        queue_name="strategy-backtest",
    )

    assert tuple(index for index, _ in first_batch) == (0, 1)
    assert tuple(index for index, _ in replay) == (0, 1)
    first_keys = tuple(item["dispatch_intent"].idempotency_key for item in observed[:2])
    replay_keys = tuple(item["dispatch_intent"].idempotency_key for item in observed[2:])
    assert len(set(first_keys)) == 2
    assert replay_keys == first_keys
    assert tuple(item["attempt_id"] for item in observed[2:]) == tuple(
        item["attempt_id"] for item in observed[:2]
    )


@pytest.mark.asyncio
async def test_terminal_reconciliation_authenticates_receipt_and_dispatches_remaining_training() -> (
    None
):
    adapter, _reader, _plan_store, definition, first, second = _setup()

    async def resolve_calendar(**_kwargs: Any):
        return definition.observation_boundaries

    observed: list[dict[str, Any]] = []

    async def dispatch(**kwargs: Any):
        observed.append(kwargs)
        return SimpleNamespace(decision=SearchDispatchDecision.ENQUEUE)

    adapter._walk_forward_observation_calendar = resolve_calendar
    adapter.dispatch_search_candidate = dispatch
    await adapter.create_walk_forward_definition(
        principal=User(),
        request_id="reconcile-create",
        idempotency_key="reconcile-create-key",
        experiment_fingerprint=definition.experiment_fingerprint,
        request=WalkForwardDefinitionRequest(
            candidate_fingerprints=(first.trial_id, second.trial_id),
            spec=definition.spec,
            metric_id=definition.metric_id,
            direction=definition.direction,
            max_tasks=definition.max_tasks,
        ),
    )

    state = adapter._persistence.search_state.states[definition.experiment_fingerprint]
    attempt_id = "finished-training-attempt"
    completed_at = datetime(2026, 10, 6, tzinfo=UTC)
    started = start_search_candidate(state, 0, attempt_id=attempt_id, now=completed_at)
    result_fingerprint = content_digest("finished-training-result")
    succeeded = record_search_candidate_terminal(
        started.state,
        0,
        attempt_id=attempt_id,
        phase=SearchCandidatePhase.SUCCEEDED,
        result_fingerprint=result_fingerprint,
        now=completed_at,
    )
    adapter._persistence.search_state.states[definition.experiment_fingerprint] = succeeded.state
    dispatch_request = DispatchRequest(
        "finished-dispatch-key",
        attempt_id,
        content_digest("finished-payload"),
        "strategy-backtest",
        completed_at,
    )

    class DispatchStore:
        async def load_by_request_fingerprint(self, fingerprint: str):
            assert fingerprint == dispatch_request.fingerprint
            return SearchDispatchRecord(
                "42",
                definition.experiment_fingerprint,
                0,
                dispatch_request,
            )

    class CompletionStore:
        async def load_completion_ledger(self, *, principal: Any):
            assert principal.id == "42"
            return SimpleNamespace(
                records=(
                    SimpleNamespace(
                        attempt_id=attempt_id,
                        result_fingerprint=result_fingerprint,
                    ),
                )
            )

    adapter._persistence.search_dispatch = DispatchStore()
    adapter._persistence.result_completion = CompletionStore()
    progress = await adapter.reconcile_walk_forward_terminal(
        principal=User(),
        request_id="reconcile-finished-attempt",
        experiment_fingerprint=definition.experiment_fingerprint,
        attempt_id=attempt_id,
        dispatch_request_fingerprint=dispatch_request.fingerprint,
        queue_name="strategy-backtest",
    )

    assert progress["decision"] == "dispatched"
    assert progress["dispatched_candidate_indices"] == (1,)
    assert [item["candidate_index"] for item in observed] == [1]


@pytest.mark.asyncio
async def test_oos_phase_hydrates_owner_manifests_appends_and_replays_exact_trials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    adapter, reader, _plan_store, definition, first, second = _setup()
    adapter._clock = lambda: datetime(2026, 10, 6, 5, tzinfo=UTC)
    training = materialize_walk_forward_training_trials(
        definition.training_plan,
        (first, second),
        definition.folds,
        definition.observation_boundaries,
    )
    state, bindings = initialize_walk_forward_training_queue(
        definition.training_plan, training, now=None
    )
    trial_by_id = {trial.trial_id: trial for trial in training.trials}
    result_store = adapter._result_materialization
    for index, candidate in enumerate(state.candidates):
        attempt_id = f"persisted-training-attempt-{index}"
        result_fingerprint = content_digest({"training-result": index})
        manifest = _authoritative_result(
            trial_by_id[candidate.trial_fingerprint],
            definition.metric_id,
            Decimal(index + 1),
            attempt_id=attempt_id,
            snapshot=reader.contracts[(ApiResourceType.SNAPSHOT, first.snapshot_fingerprint)],
        )
        result_store.manifests[attempt_id] = manifest
        state = start_search_candidate(
            state,
            index,
            attempt_id=attempt_id,
            now=datetime(2026, 10, 6, 1 + index, tzinfo=UTC),
        ).state
        state = record_search_candidate_terminal(
            state,
            index,
            attempt_id=attempt_id,
            phase=SearchCandidatePhase.SUCCEEDED,
            result_fingerprint=result_fingerprint,
            now=datetime(2026, 10, 6, 2 + index, tzinfo=UTC),
        ).state
    adapter._persistence.search_state.states[definition.experiment_fingerprint] = state

    appended = await adapter.append_walk_forward_oos_candidates(
        principal=User(),
        request_id="append-oos",
        experiment_fingerprint=definition.experiment_fingerprint,
    )
    assert appended.resolution.decision is SearchStateDecision.APPLY
    assert len(appended.oos_task_bindings) == len(definition.folds)
    assert all(binding.purpose == "out_of_sample" for binding in appended.oos_task_bindings)
    expected_selection = select_walk_forward_oos_tasks(
        definition.training_plan,
        definition.folds,
        tuple(
            training_score_from_result_manifest(
                task_binding,
                result_store.manifests[
                    f"persisted-training-attempt-{queue_binding.candidate_index}"
                ],
                metric_id=definition.metric_id,
            )
            for task_binding, queue_binding in zip(training.bindings, bindings, strict=True)
        ),
    )
    expected_oos = materialize_walk_forward_oos_trials(
        expected_selection,
        (first, second),
        definition.folds,
        definition.observation_boundaries,
    )
    assert tuple(binding.trial_fingerprint for binding in appended.oos_task_bindings) == tuple(
        trial.trial_id for trial in expected_oos.trials
    )
    replay = await adapter.append_walk_forward_oos_candidates(
        principal=User(),
        request_id="append-oos-replay",
        experiment_fingerprint=definition.experiment_fingerprint,
    )
    assert replay.resolution.decision is SearchStateDecision.REPLAY_EXISTING
    assert replay.resolution.state == appended.resolution.state
    assert replay.oos_task_bindings == appended.oos_task_bindings
    resumed = await adapter.initialize_walk_forward_training(
        principal=User(),
        request_id="resume-after-oos-append",
        definition=definition,
    )
    assert resumed.decision is SearchStateDecision.REPLAY_EXISTING
    assert resumed.state == appended.resolution.state
    with pytest.raises(ApiAdapterError, match="all selected OOS folds must succeed"):
        await adapter.persist_walk_forward_oos_summary(
            principal=User(),
            request_id="premature-oos-summary",
            experiment_fingerprint=definition.experiment_fingerprint,
        )
    assert (
        await adapter._persistence.walk_forward_summaries.load(
            principal=User(),
            experiment_fingerprint=definition.experiment_fingerprint,
        )
        is None
    )

    state = resumed.state
    oos_by_id = {trial.trial_id: trial for trial in expected_oos.trials}
    expected_values = tuple(Decimal(10 + index) for index in range(len(expected_oos.trials)))
    for offset, binding in enumerate(appended.oos_task_bindings):
        attempt_id = f"persisted-oos-attempt-{offset}"
        result_fingerprint = content_digest({"oos-result": offset})
        result_store.manifests[attempt_id] = _authoritative_result(
            oos_by_id[binding.trial_fingerprint],
            definition.metric_id,
            expected_values[offset],
            attempt_id=attempt_id,
            snapshot=reader.contracts[(ApiResourceType.SNAPSHOT, first.snapshot_fingerprint)],
        )
        state = start_search_candidate(
            state,
            binding.candidate_index,
            attempt_id=attempt_id,
            now=datetime(2026, 10, 6, 6 + offset, tzinfo=UTC),
        ).state
        state = record_search_candidate_terminal(
            state,
            binding.candidate_index,
            attempt_id=attempt_id,
            phase=SearchCandidatePhase.SUCCEEDED,
            result_fingerprint=result_fingerprint,
            now=datetime(2026, 10, 6, 7 + offset, tzinfo=UTC),
        ).state
    adapter._persistence.search_state.states[definition.experiment_fingerprint] = state
    hydrated = await adapter.collect_walk_forward_oos_results(
        principal=User(),
        request_id="collect-oos-results",
        experiment_fingerprint=definition.experiment_fingerprint,
    )
    assert tuple(result.value for result in hydrated) == expected_values
    assert tuple(result.oos_task_fingerprint for result in hydrated) == tuple(
        task.fingerprint for task in expected_selection.oos_tasks
    )
    metric = MetricValue(
        "total_return",
        Decimal("0.075"),
        "fraction",
        "strategy-lab.metrics.v2",
        MetricBasis.NET,
        10,
    )
    observed_native: dict[str, Any] = {}

    def native_metrics(manifests, *, artifact_store, selection_fingerprint):
        observed_native["manifests"] = manifests
        observed_native["artifact_store"] = artifact_store
        observed_native["selection_fingerprint"] = selection_fingerprint
        return (metric,)

    monkeypatch.setattr(
        "app.strategy_lab_v2.application.calculate_walk_forward_native_oos_metrics",
        native_metrics,
    )
    store = LocalArtifactStore(tmp_path / "artifacts")
    adapter._walk_forward_artifact_store = store
    persisted_summary = await adapter.persist_walk_forward_oos_summary(
        principal=User(),
        request_id="persist-oos-summary",
        experiment_fingerprint=definition.experiment_fingerprint,
    )
    assert persisted_summary.decision.value == "persisted"
    assert persisted_summary.summary.metric_id == definition.metric_id
    assert len(persisted_summary.summary.aggregate_metrics) == 5
    assert persisted_summary.native_metrics is not None
    assert persisted_summary.native_metrics.metrics == (metric,)
    assert len(observed_native["manifests"]) == len(definition.folds)
    assert observed_native["artifact_store"] is store
    assert (
        observed_native["selection_fingerprint"] == persisted_summary.summary.selection.fingerprint
    )
    restored_native = await adapter._persistence.walk_forward_native_metrics.load(
        principal=User(),
        experiment_fingerprint=definition.experiment_fingerprint,
    )
    assert restored_native == persisted_summary.native_metrics
    replay_summary = await adapter.persist_walk_forward_oos_summary(
        principal=User(),
        request_id="persist-oos-summary-replay",
        experiment_fingerprint=definition.experiment_fingerprint,
    )
    assert replay_summary.decision.value == "replay_existing"
    assert replay_summary.summary == persisted_summary.summary
