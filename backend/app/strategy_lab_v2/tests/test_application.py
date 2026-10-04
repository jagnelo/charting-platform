from dataclasses import dataclass, replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest

import app.strategy_lab_v2.application as application_module
from app.strategy_lab_v2.admission import ExecutionAdmissionLedger
from app.strategy_lab_v2.api_contracts import ApiErrorCode
from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.api_router import ApiAdapterError, ResourceMutationServiceResult
from app.strategy_lab_v2.application import (
    PostgresStrategyLabV2Adapter,
    ResultPublicationCompletionResolution,
    SearchDispatchEvidence,
    StrategyLabV2ApiBindings,
    _load_api_bindings_factory,
    _principal_identity,
    create_registered_strategy_lab_v2_router,
    get_strategy_lab_v2_adapter,
)
from app.strategy_lab_v2.artifact_commit import ArtifactCommitLedger
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capability_summary import CapabilitySummary, CapabilitySummaryDecision
from app.strategy_lab_v2.conformance import EngineReleaseChannel
from app.strategy_lab_v2.contracts import ForwardState
from app.strategy_lab_v2.dispatch import SearchDispatchIntent
from app.strategy_lab_v2.dispatch_payload import DispatchPayload
from app.strategy_lab_v2.engine_execution import (
    NautilusExecutionScope,
)
from app.strategy_lab_v2.execution import ExecutionAuthorization
from app.strategy_lab_v2.forward_worker_authorization import ForwardWorkerAuthorization
from app.strategy_lab_v2.lease_observations import LeaseObservationState
from app.strategy_lab_v2.lifecycle import ExecutionAttemptLease
from app.strategy_lab_v2.nautilus_trial_materializer import (
    NautilusTrialMarketContext,
    NautilusTrialRuntimeInputMaterializer,
    build_nautilus_trial_runtime_evidence,
)
from app.strategy_lab_v2.nautilus_trial_worker_request import (
    build_nautilus_trial_worker_request,
)
from app.strategy_lab_v2.outcomes import OutcomeStatus
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.postgres_commands import PostgresCommandAdapter
from app.strategy_lab_v2.postgres_execution_state import PostgresExecutionStateAdapter
from app.strategy_lab_v2.postgres_resources import PostgresResourceReader
from app.strategy_lab_v2.postgres_result_publication import (
    PublicationStateDecision,
    PublicationStateResolution,
)
from app.strategy_lab_v2.postgres_submission import PostgresSubmissionDispatchAdapter
from app.strategy_lab_v2.progress import ProgressPhase
from app.strategy_lab_v2.resource_mutations import ResourceMutationRequest
from app.strategy_lab_v2.result_completion import (
    ResultCompletionDecision,
    ResultCompletionLedger,
    ResultCompletionResolution,
)
from app.strategy_lab_v2.result_publication import ResultPublicationDecision
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile
from app.strategy_lab_v2.search_dispatch import (
    SearchDispatchDecision,
    SearchDispatchResolution,
    resolve_search_dispatch,
)
from app.strategy_lab_v2.search_state import SearchCandidatePhase, new_search_execution_state
from app.strategy_lab_v2.storage import (
    StorageTransactionDecision,
    resolve_storage_transaction,
)
from app.strategy_lab_v2.strategy_package_resolution import StrategyPackageArtifactResolver
from app.strategy_lab_v2.tests.test_admission import _fixture, _reservation
from app.strategy_lab_v2.tests.test_engine_execution import _conformance
from app.strategy_lab_v2.tests.test_execution_summary import (
    _outcome,
    _progress,
    _publication,
    _receipt,
)
from app.strategy_lab_v2.tests.test_nautilus_trial_assembly import JsonFrozenSeriesDecoder
from app.strategy_lab_v2.tests.test_nautilus_trial_materializer import (
    RUNTIME_ABI,
    _build_inputs,
)
from app.strategy_lab_v2.tests.test_postgres_forward_state import _instance
from app.strategy_lab_v2.tests.test_postgres_forward_state import _receipt as _forward_receipt
from app.strategy_lab_v2.tests.test_resource_domains import _preflight_payload
from app.strategy_lab_v2.tests.test_result_completion import _runtime_success
from app.strategy_lab_v2.worker_handoff import encode_worker_handoff
from app.strategy_lab_v2.workers import (
    WorkerKind,
    WorkerPoolState,
    WorkerProfile,
    WorkerReservation,
)


@dataclass
class _User:
    id: int


NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)


def _worker_request_for_trial(
    tmp_path,
    *,
    runtime_evidence,
    authorization,
    runtime_profile,
    artifact_store,
    reservation_id,
):
    pool = WorkerPoolState(
        WorkerProfile(
            authorization.lease_worker_id,
            WorkerKind.BACKTEST,
            runtime_profile.fingerprint,
        )
    )
    lease = ExecutionAttemptLease(
        authorization.attempt_id,
        authorization.lease_worker_id,
        authorization.lease_id,
        NOW,
        NOW,
        NOW.replace(year=NOW.year + 1),
    )
    conformance_evidence, conformance_report = _conformance(
        channel=EngineReleaseChannel.RELEASE_CANDIDATE,
        checks=NautilusExecutionScope.BACKTEST_AUTHORITATIVE.required_checks,
    )
    return build_nautilus_trial_worker_request(
        runtime_evidence,
        authorization,
        artifact_store=artifact_store,
        runtime_profile=runtime_profile,
        worker_pool=pool,
        admission_ledger=ExecutionAdmissionLedger(),
        reservation_id=reservation_id,
        lease_state=LeaseObservationState(lease),
        conformance_evidence=conformance_evidence,
        conformance_report=conformance_report,
        image_name="nautilus-runtime",
        output_path=tmp_path / "worker-result.json",
        now=NOW,
    )


def test_principal_identity_normalizes_existing_integer_user_ids() -> None:
    assert _principal_identity(_User(42)).id == "42"
    assert _principal_identity("owner-a").id == "owner-a"


def test_principal_identity_rejects_missing_or_boolean_identity() -> None:
    for principal in (None, object(), True, " "):
        try:
            _principal_identity(principal)
        except ValueError as error:
            assert "principal identity" in str(error)
        else:  # pragma: no cover - assertion branch
            raise AssertionError("principal identity should be rejected")


@pytest.mark.asyncio
async def test_application_forward_lifecycle_is_owner_scoped_and_utc_normalized() -> None:
    instance = _instance()
    receipt = _forward_receipt(instance)
    observed: dict[str, Any] = {}

    class ForwardStore:
        async def ensure_instance(self, *, principal: Any, instance: Any) -> Any:
            observed["ensure_principal"] = principal
            observed["instance"] = instance
            return SimpleNamespace(instance=instance)

        async def transition(self, **kwargs: Any) -> Any:
            observed["transition"] = kwargs
            return SimpleNamespace(instance=instance)

        async def complete_warmup(self, **kwargs: Any) -> Any:
            observed["warmup"] = kwargs
            return SimpleNamespace(receipt=kwargs["receipt"])

    adapter = cast(Any, object.__new__(PostgresStrategyLabV2Adapter))
    adapter._persistence = SimpleNamespace(forward_state=ForwardStore())
    await adapter.register_forward_instance(principal=_User(42), instance=instance)
    await adapter.transition_forward_instance(
        principal=_User(42),
        instance_id=instance.instance_id,
        target=ForwardState.WARMING_UP,
        now=datetime(2024, 1, 2, 13, 0, tzinfo=UTC),
    )
    await adapter.complete_forward_warmup(principal=_User(42), receipt=receipt)

    assert observed["ensure_principal"].id == "42"
    assert observed["transition"]["principal"].id == "42"
    assert observed["transition"]["now"].tzinfo is UTC
    assert observed["warmup"]["principal"].id == "42"


@pytest.mark.asyncio
async def test_application_loads_forward_worker_authorization_from_durable_records() -> None:
    profile = WorkerProfile("forward-worker-1", WorkerKind.FORWARD, content_digest("runtime"))
    reservation = WorkerReservation(
        content_digest("reservation"),
        profile.worker_id,
        WorkerKind.FORWARD,
        "forward-instance",
        NOW,
    )
    lease = ExecutionAttemptLease(
        "forward-instance",
        profile.worker_id,
        "lease-1",
        NOW,
        NOW,
        NOW.replace(hour=13),
    )

    class WorkerStore:
        async def load_forward_authorization(
            self, *, profile: WorkerProfile, reservation_id: str, lease_id: str
        ) -> ForwardWorkerAuthorization:
            assert profile.worker_id == "forward-worker-1"
            assert reservation_id == reservation.reservation_id
            assert lease_id == lease.lease_id
            return ForwardWorkerAuthorization(reservation, lease)

        async def load_pool(self, received_profile: WorkerProfile) -> WorkerPoolState:
            assert received_profile == profile
            return WorkerPoolState(profile, (reservation,))

        async def load_lease(self, lease_id: str) -> LeaseObservationState:
            assert lease_id == lease.lease_id
            return LeaseObservationState(lease)

    adapter = cast(Any, object.__new__(PostgresStrategyLabV2Adapter))
    adapter._persistence = SimpleNamespace(worker_state=WorkerStore())
    authorization = await adapter.load_forward_worker_authorization(
        profile=profile,
        reservation_id=reservation.reservation_id,
        lease_id=lease.lease_id,
    )
    assert isinstance(authorization, ForwardWorkerAuthorization)
    assert authorization.reservation == reservation
    assert authorization.lease == lease


@pytest.mark.asyncio
async def test_application_search_candidate_lifecycle_is_owner_scoped_and_utc_normalized() -> None:
    observed: dict[str, Any] = {}
    experiment = content_digest("search-experiment")

    class SearchStore:
        async def start_candidate(self, **kwargs: Any) -> Any:
            observed["start"] = kwargs
            return SimpleNamespace()

        async def record_terminal(self, **kwargs: Any) -> Any:
            observed["terminal"] = kwargs
            return SimpleNamespace()

    adapter = cast(Any, object.__new__(PostgresStrategyLabV2Adapter))
    adapter._persistence = SimpleNamespace(search_state=SearchStore())
    await adapter.start_search_candidate(
        principal=_User(42),
        experiment_fingerprint=experiment,
        candidate_index=0,
        attempt_id="attempt-1",
        now=datetime(2024, 1, 2, 13, 0, tzinfo=UTC),
    )
    await adapter.record_search_candidate_terminal(
        principal=_User(42),
        experiment_fingerprint=experiment,
        candidate_index=0,
        attempt_id="attempt-1",
        phase=SearchCandidatePhase.SUCCEEDED,
        now=datetime(2024, 1, 2, 14, 0, tzinfo=UTC),
        result_fingerprint=content_digest("result"),
    )

    assert observed["start"]["principal"].id == "42"
    assert observed["start"]["now"].tzinfo is UTC
    assert observed["terminal"]["principal"].id == "42"
    assert observed["terminal"]["phase"] is SearchCandidatePhase.SUCCEEDED


@pytest.mark.asyncio
async def test_application_search_and_forward_reads_are_owner_scoped() -> None:
    experiment = content_digest("search-experiment")
    instance = _instance()
    observed: dict[str, Any] = {}
    search_state = new_search_execution_state(
        experiment,
        (content_digest("trial"),),
    )
    forward_instance = instance
    forward_state = SimpleNamespace(checkpoint=SimpleNamespace(instance=instance))

    class SearchStore:
        async def load(self, **kwargs: Any) -> Any:
            observed["search"] = kwargs
            return search_state

    class ForwardStore:
        async def load_instance(self, **kwargs: Any) -> Any:
            observed["instance"] = kwargs
            return forward_instance

        async def load_state(self, **kwargs: Any) -> Any:
            observed["state"] = kwargs
            return forward_state

    adapter = cast(Any, object.__new__(PostgresStrategyLabV2Adapter))
    adapter._persistence = SimpleNamespace(search_state=SearchStore(), forward_state=ForwardStore())

    assert (
        await adapter.load_search_state(principal=_User(42), experiment_fingerprint=experiment)
        == search_state
    )
    assert (
        await adapter.load_forward_instance(principal=_User(42), instance_id=instance.instance_id)
        == forward_instance
    )
    assert (
        await adapter.load_forward_state(principal=_User(42), instance_id=instance.instance_id)
        == forward_state
    )

    assert observed["search"]["principal"].id == "42"
    assert observed["search"]["experiment_fingerprint"] == experiment
    assert observed["instance"]["principal"].id == "42"
    assert observed["state"]["principal"].id == "42"


def test_application_adapter_composes_all_durable_api_adapters() -> None:
    adapter = PostgresStrategyLabV2Adapter(lambda: object())

    assert isinstance(adapter._persistence, PostgresStrategyLabV2Persistence)
    assert isinstance(adapter._resources, PostgresResourceReader)
    assert isinstance(adapter._submissions, PostgresSubmissionDispatchAdapter)
    assert adapter._search_dispatch_store is adapter._persistence.search_dispatch
    assert isinstance(adapter._execution_state, PostgresExecutionStateAdapter)
    assert isinstance(adapter._commands, PostgresCommandAdapter)


def test_application_adapter_reuses_injected_persistence_bundle() -> None:
    persistence = PostgresStrategyLabV2Persistence.build(lambda: object())

    adapter = PostgresStrategyLabV2Adapter(lambda: object(), persistence=persistence)

    assert adapter._persistence is persistence
    assert adapter._search_dispatch_store is persistence.search_dispatch


def test_application_adapter_composes_trusted_host_bindings_over_shared_persistence() -> None:
    def session_factory() -> object:
        return object()

    observed: dict[str, Any] = {}

    async def capability_preflight(**_kwargs: Any) -> CapabilitySummary:
        raise AssertionError("resolver is captured here, not invoked")

    async def search_dispatch(**_kwargs: Any) -> SearchDispatchResolution:
        raise AssertionError("resolver is captured here, not invoked")

    def build_bindings(
        supplied_session_factory: Any,
        persistence: PostgresStrategyLabV2Persistence,
    ) -> StrategyLabV2ApiBindings:
        observed["session_factory"] = supplied_session_factory
        observed["persistence"] = persistence
        return StrategyLabV2ApiBindings(
            capability_preflight=capability_preflight,
            search_dispatch=search_dispatch,
        )

    adapter = PostgresStrategyLabV2Adapter(
        session_factory,
        host_bindings_factory=build_bindings,
    )

    assert observed["session_factory"] is session_factory
    assert observed["persistence"] is adapter._persistence
    assert adapter._capability_preflight is capability_preflight
    assert adapter._search_dispatch is search_dispatch
    assert adapter._search_dispatch_evidence is None


def test_application_host_binding_factory_must_return_typed_bindings() -> None:
    with pytest.raises(TypeError, match="StrategyLabV2ApiBindings"):
        PostgresStrategyLabV2Adapter(
            lambda: object(),
            host_bindings_factory=lambda _session_factory, _persistence: {},  # type: ignore[arg-type,return-value]
        )


def test_application_host_binding_factory_rejects_async_factory_before_call() -> None:
    calls = 0

    async def build_bindings(_session_factory: Any, _persistence: Any) -> StrategyLabV2ApiBindings:
        nonlocal calls
        calls += 1
        return StrategyLabV2ApiBindings(capability_preflight=cast(Any, lambda: None))

    with pytest.raises(TypeError, match="host_bindings_factory must be synchronous"):
        PostgresStrategyLabV2Adapter(
            lambda: object(),
            host_bindings_factory=cast(Any, build_bindings),
        )

    assert calls == 0


def test_application_host_binding_factory_closes_awaitable_returned_by_sync_factory() -> None:
    async def build_bindings(_session_factory: Any, _persistence: Any) -> StrategyLabV2ApiBindings:
        return StrategyLabV2ApiBindings(capability_preflight=cast(Any, lambda: None))

    created: list[Any] = []

    def invalid_sync_factory(_session_factory: Any, _persistence: Any) -> Any:
        coroutine = build_bindings(None, None)
        created.append(coroutine)
        return coroutine

    with pytest.raises(TypeError, match="configure bindings synchronously"):
        PostgresStrategyLabV2Adapter(
            lambda: object(),
            host_bindings_factory=cast(Any, invalid_sync_factory),
        )

    assert len(created) == 1
    assert created[0].cr_frame is None


def test_api_host_bindings_reject_sync_request_resolvers() -> None:
    def synchronous_resolver(**_kwargs: Any) -> None:
        return None

    with pytest.raises(TypeError, match="must be asynchronous"):
        StrategyLabV2ApiBindings(capability_preflight=cast(Any, synchronous_resolver))
    with pytest.raises(TypeError, match="must be asynchronous"):
        StrategyLabV2ApiBindings(search_dispatch=cast(Any, synchronous_resolver))


def test_load_api_bindings_factory_uses_local_module_attribute(monkeypatch: Any) -> None:
    async def capability_preflight(**_kwargs: Any) -> CapabilitySummary:
        raise AssertionError("factory resolver is captured here, not invoked")

    def factory(_session_factory: Any, _persistence: Any) -> StrategyLabV2ApiBindings:
        return StrategyLabV2ApiBindings(capability_preflight=capability_preflight)

    module = SimpleNamespace(build_bindings=factory, invalid="not callable")
    monkeypatch.setattr("app.strategy_lab_v2.application.import_module", lambda _name: module)

    assert _load_api_bindings_factory(None) is None
    assert _load_api_bindings_factory(" ") is None
    assert _load_api_bindings_factory("local_host:build_bindings") is factory
    with pytest.raises(ValueError, match="module:attribute"):
        _load_api_bindings_factory("invalid")
    with pytest.raises(TypeError, match="target must be callable"):
        _load_api_bindings_factory("local_host:invalid")


def test_registered_adapter_loads_configured_local_host_bindings(monkeypatch: Any) -> None:
    def session_factory() -> object:
        return object()

    async def capability_preflight(**_kwargs: Any) -> CapabilitySummary:
        raise AssertionError("configured resolver must remain lazy")

    def build_bindings(
        supplied_session_factory: Any,
        persistence: PostgresStrategyLabV2Persistence,
    ) -> StrategyLabV2ApiBindings:
        assert supplied_session_factory is session_factory
        assert isinstance(persistence, PostgresStrategyLabV2Persistence)
        return StrategyLabV2ApiBindings(capability_preflight=capability_preflight)

    real_import_module = application_module.import_module

    def import_module(module_name: str) -> Any:
        if module_name == "app.database":
            return SimpleNamespace(AsyncSessionLocal=session_factory)
        if module_name == "local_strategy_lab_host":
            return SimpleNamespace(build_bindings=build_bindings)
        return real_import_module(module_name)

    monkeypatch.setattr(application_module, "_default_adapter", None)
    monkeypatch.setattr(application_module, "import_module", import_module)
    monkeypatch.setenv(
        "STRATEGY_LAB_V2_API_BINDINGS",
        "local_strategy_lab_host:build_bindings",
    )

    adapter = get_strategy_lab_v2_adapter()

    assert isinstance(adapter, PostgresStrategyLabV2Adapter)
    assert adapter._capability_preflight is capability_preflight


@pytest.mark.asyncio
async def test_application_capability_preflight_resolver_is_persisted_and_owner_scoped() -> None:
    summary = CapabilitySummary(
        report_fingerprint=content_digest("report"),
        binding_fingerprint=content_digest("binding"),
        decision=CapabilitySummaryDecision.RIGOROUS,
        data_gaps=(),
        execution_gaps=(),
        degradations=(),
        ranking_eligible=True,
        executable=True,
        authoritative=True,
        can_publish_authoritative_results=True,
    )
    observed: dict[str, Any] = {}

    async def resolve(**kwargs: Any) -> CapabilitySummary:
        observed.update(kwargs)
        return summary

    class CapabilityStore:
        async def ensure(self, *, principal: Any, summary: CapabilitySummary) -> Any:
            observed["stored_principal"] = principal
            observed["stored_summary"] = summary
            return SimpleNamespace(summary=summary)

    adapter = cast(Any, object.__new__(PostgresStrategyLabV2Adapter))
    adapter._capability_preflight = resolve
    adapter._capabilities = CapabilityStore()

    resolved = await adapter.preflight_capability(
        principal=_User(42),
        request_id="request-1",
        idempotency_key="capability-key",
        payload={"requirements": []},
        payload_digest=content_digest({"requirements": []}),
    )

    assert resolved == summary
    assert observed["principal"].id == "42"
    assert observed["stored_principal"].id == "42"
    assert observed["stored_summary"] == summary


@pytest.mark.asyncio
async def test_application_capability_preflight_fails_closed_without_host_binding() -> None:
    adapter = cast(Any, object.__new__(PostgresStrategyLabV2Adapter))
    adapter._capability_preflight = None

    with pytest.raises(ApiAdapterError) as raised:
        await adapter.preflight_capability(
            principal=_User(42),
            request_id="request-1",
            idempotency_key="capability-key",
            payload={"requirements": []},
            payload_digest=content_digest({"requirements": []}),
        )

    assert raised.value.error.code is ApiErrorCode.CAPABILITY_UNSUPPORTED
    assert raised.value.error.status_code == 501


@pytest.mark.asyncio
async def test_application_result_publication_completion_is_owner_scoped_and_idempotent() -> None:
    submission = _receipt()
    outcome = _outcome(OutcomeStatus.SUCCEEDED)
    progress = _progress(ProgressPhase.SUCCEEDED, sequence=1)
    publication = _publication(outcome.result_digest or "")
    observed: dict[str, Any] = {}

    class PublicationStore:
        async def ensure(self, *, principal: Any, plan: Any) -> PublicationStateResolution:
            observed["publication_principal"] = principal
            observed["publication_plan"] = plan
            return PublicationStateResolution(PublicationStateDecision.REGISTERED, plan)

    class CompletionStore:
        async def finalize(self, **kwargs: Any) -> ResultCompletionResolution:
            observed.update(kwargs)
            return ResultCompletionResolution(
                ResultCompletionDecision.REJECT,
                ResultCompletionLedger(),
                ArtifactCommitLedger(),
                content_digest("completion"),
                rejection_reason="fixture completion",
            )

    adapter = cast(Any, object.__new__(PostgresStrategyLabV2Adapter))
    adapter._persistence = SimpleNamespace(
        result_publication=PublicationStore(), result_completion=CompletionStore()
    )
    resolved = await adapter.publish_and_complete_result(
        principal=_User(42),
        submission=submission,
        runtime_state=_runtime_success(),
        outcome=outcome,
        progress=progress,
        publication=publication,
        artifact_plans=(),
        completed_at=datetime(2024, 1, 1, 13, 0, tzinfo=UTC),
    )

    assert isinstance(resolved, ResultPublicationCompletionResolution)
    assert resolved.publication.plan == publication
    assert resolved.completion is not None
    assert observed["publication_principal"].id == "42"
    assert observed["principal"].id == "42"
    assert observed["publication"] == publication
    assert observed["completed_at"].tzinfo is UTC


@pytest.mark.asyncio
async def test_application_rejected_publication_is_recorded_without_completion() -> None:
    publication = _publication(content_digest("result"))
    publication = publication.__class__(
        publication.result_fingerprint,
        publication.reproduction_fingerprint,
        publication.attempt_id,
        publication.engine_build_digest,
        ResultPublicationDecision.REJECT,
        ("authoritative evidence missing",),
    )
    observed: dict[str, Any] = {}

    class PublicationStore:
        async def ensure(self, *, principal: Any, plan: Any) -> PublicationStateResolution:
            observed["plan"] = plan
            return PublicationStateResolution(PublicationStateDecision.REGISTERED, plan)

    class CompletionStore:
        async def finalize(self, **kwargs: Any) -> Any:
            raise AssertionError("rejected publication must not finalize completion")

    adapter = cast(Any, object.__new__(PostgresStrategyLabV2Adapter))
    adapter._persistence = SimpleNamespace(
        result_publication=PublicationStore(), result_completion=CompletionStore()
    )
    resolved = await adapter.publish_and_complete_result(
        principal=_User(42),
        submission=_receipt(),
        runtime_state=_runtime_success(),
        outcome=_outcome(OutcomeStatus.SUCCEEDED),
        progress=_progress(ProgressPhase.SUCCEEDED, sequence=1),
        publication=publication,
        artifact_plans=(),
        completed_at=NOW,
    )

    assert resolved.completion is None
    assert observed["plan"] == publication


def test_registered_router_uses_versioned_prefix_and_application_dependencies() -> None:
    router = create_registered_strategy_lab_v2_router()

    assert router.prefix == "/strategy-lab/v2"
    assert {route.path for route in router.routes} >= {
        "/strategy-lab/v2/strategies/validate",
        "/strategy-lab/v2/capabilities/preflight",
        "/strategy-lab/v2/experiments/{experiment_id}/search",
        "/strategy-lab/v2/experiments/{experiment_id}/search/cancel",
        "/strategy-lab/v2/experiments/{experiment_id}/search/dispatch",
        "/strategy-lab/v2/submissions",
        "/strategy-lab/v2/attempts/{attempt_id}/commands",
    }
    assert get_strategy_lab_v2_adapter() is get_strategy_lab_v2_adapter()


@pytest.mark.asyncio
async def test_application_search_dispatch_callback_is_owner_scoped_and_typed() -> None:
    authorization, runtime_request, runtime_preflight, pool = _fixture()
    observed: dict[str, Any] = {}

    async def resolve(**kwargs: Any) -> SearchDispatchResolution:
        observed.update(kwargs)
        return resolve_search_dispatch(
            new_search_execution_state(
                kwargs["experiment_fingerprint"],
                (content_digest("trial-1"),),
                now=NOW,
            ),
            candidate_index=kwargs["candidate_index"],
            attempt_id=kwargs["attempt_id"],
            authorization=authorization,
            runtime_request=runtime_request,
            runtime_preflight=runtime_preflight,
            admission_ledger=ExecutionAdmissionLedger(),
            pool=pool,
            reservation_id=_reservation("application"),
            dispatch_request=kwargs["dispatch_intent"].bind_payload(
                content_digest("worker-payload")
            ),
            prior_dispatches=(),
            now=NOW,
        )

    adapter = cast(Any, object.__new__(PostgresStrategyLabV2Adapter))
    adapter._search_dispatch = resolve
    dispatch_intent = SearchDispatchIntent(
        "dispatch-key",
        "attempt-1",
        "strategy-backtest",
        NOW,
    )
    resolved = await adapter.dispatch_search_candidate(
        principal=_User(42),
        request_id="request-1",
        experiment_fingerprint=content_digest("experiment"),
        candidate_index=0,
        attempt_id="attempt-1",
        dispatch_intent=dispatch_intent,
    )

    assert resolved.decision.value == "enqueue"
    assert observed["principal"].id == "42"
    assert observed["dispatch_intent"] == dispatch_intent


@pytest.mark.asyncio
async def test_application_search_dispatch_fails_closed_without_host_binding() -> None:
    adapter = cast(Any, object.__new__(PostgresStrategyLabV2Adapter))
    adapter._search_dispatch = None

    with pytest.raises(ApiAdapterError) as raised:
        await adapter.dispatch_search_candidate(
            principal=_User(42),
            request_id="request-1",
            experiment_fingerprint=content_digest("experiment"),
            candidate_index=0,
            attempt_id="attempt-1",
            dispatch_intent=SearchDispatchIntent(
                "dispatch-key",
                "attempt-1",
                "strategy-backtest",
                NOW,
            ),
        )

    assert raised.value.error.code is ApiErrorCode.PRECONDITION_FAILED
    assert raised.value.error.status_code == 501


@pytest.mark.asyncio
async def test_application_search_dispatch_replays_before_building_runtime_evidence() -> None:
    _authorization, _runtime_request, _runtime_preflight, pool = _fixture()
    experiment_fingerprint = content_digest("experiment")
    attempt_id = "attempt-1"
    dispatch_intent = SearchDispatchIntent(
        "dispatch-key",
        attempt_id,
        "strategy-backtest",
        NOW,
    )
    replay = SearchDispatchResolution(
        SearchDispatchDecision.CONFLICT,
        new_search_execution_state(
            experiment_fingerprint,
            (content_digest("trial"),),
            now=NOW,
        ),
        ExecutionAdmissionLedger(),
        pool,
        rejection_reason="test replay conflict",
    )
    observed: dict[str, Any] = {}

    class Store:
        async def replay_idempotency(self, **kwargs: Any) -> SearchDispatchResolution:
            observed.update(kwargs)
            return replay

    adapter = cast(Any, object.__new__(PostgresStrategyLabV2Adapter))
    adapter._search_dispatch = None
    adapter._search_dispatch_evidence = None
    adapter._search_dispatch_store = Store()
    resolved = await adapter.dispatch_search_candidate(
        principal=_User(42),
        request_id="request-1",
        experiment_fingerprint=experiment_fingerprint,
        candidate_index=0,
        attempt_id=attempt_id,
        dispatch_intent=dispatch_intent,
    )

    assert resolved is replay
    assert observed["principal"].id == "42"
    assert observed["experiment_fingerprint"] == experiment_fingerprint
    assert observed["candidate_index"] == 0
    assert observed["attempt_id"] == attempt_id
    assert observed["dispatch_intent"] == dispatch_intent
    assert "request_id" not in observed


@pytest.mark.asyncio
async def test_application_search_dispatch_evidence_resolver_uses_durable_store(
    tmp_path,
) -> None:
    _values, graph, artifact_store = _build_inputs(tmp_path)
    materializer = NautilusTrialRuntimeInputMaterializer(
        artifact_store=artifact_store,
        strategy_package_resolver=StrategyPackageArtifactResolver(
            artifact_store,
            runtime_abi=RUNTIME_ABI,
        ),
        series_decoder=JsonFrozenSeriesDecoder(),
    )
    materialized_input = materializer.materialize(
        graph=graph,
        market_context=NautilusTrialMarketContext(_values["instruments"], _values["venue"]),
    )
    strategy = graph.strategies[0]
    runtime_profile = RuntimeIsolationProfile(
        runtime_image_digest=content_digest("runtime-image"),
        runtime_abi=RUNTIME_ABI,
        allowed_dependency_digests=frozenset(
            dependency.artifact_digest for dependency in strategy.dependencies
        ),
    )
    runtime_evidence = build_nautilus_trial_runtime_evidence(
        materialized_input,
        runtime_profile,
        request_id=content_digest("runtime-request"),
        submitted_at=NOW,
    )
    authorization = ExecutionAuthorization(
        graph.trial.trial_id,
        graph.attempt.attempt_id,
        strategy.source_digest,
        graph.trial.preflight_fingerprint,
        content_digest("capability-preflight"),
        "lease-1",
        "worker-1",
        NOW,
        True,
    )
    reservation_id = _reservation("application-evidence")
    worker_request = _worker_request_for_trial(
        tmp_path,
        runtime_evidence=runtime_evidence,
        authorization=authorization,
        runtime_profile=runtime_profile,
        artifact_store=artifact_store,
        reservation_id=reservation_id,
    )
    with pytest.raises(ValueError, match="authorization source"):
        SearchDispatchEvidence(
            authorization=replace(authorization, source_digest=content_digest("different-source")),
            trial_runtime_evidence=runtime_evidence,
            worker_request=worker_request,
            reservation_id=reservation_id,
            now=NOW,
        )
    pool = WorkerPoolState(
        WorkerProfile("worker-1", WorkerKind.BACKTEST, runtime_profile.fingerprint)
    )
    runtime_request = runtime_evidence.runtime_request
    runtime_preflight = runtime_evidence.runtime_preflight
    dispatch_intent = SearchDispatchIntent(
        "dispatch-key",
        graph.attempt.attempt_id,
        "strategy-backtest",
        NOW,
    )
    observed: dict[str, Any] = {}

    async def evidence(**kwargs: Any) -> SearchDispatchEvidence:
        observed.update(kwargs)
        return SearchDispatchEvidence(
            authorization=authorization,
            trial_runtime_evidence=runtime_evidence,
            worker_request=worker_request,
            reservation_id=reservation_id,
            now=NOW,
        )

    worker_payload = encode_worker_handoff(worker_request)
    dispatch_request = dispatch_intent.bind_payload(
        DispatchPayload.from_mapping(worker_payload).payload_digest
    )

    expected = resolve_search_dispatch(
        new_search_execution_state(
            graph.experiment.fingerprint,
            (graph.trial.trial_id,),
            now=NOW,
        ),
        candidate_index=0,
        attempt_id=graph.attempt.attempt_id,
        authorization=authorization,
        runtime_request=runtime_request,
        runtime_preflight=runtime_preflight,
        admission_ledger=ExecutionAdmissionLedger(),
        pool=pool,
        reservation_id=_reservation("application-evidence"),
        dispatch_request=dispatch_request,
        prior_dispatches=(),
        now=NOW,
    )

    class Store:
        async def dispatch(self, **kwargs: Any) -> SearchDispatchResolution:
            observed["store"] = kwargs
            return expected

    adapter = cast(Any, object.__new__(PostgresStrategyLabV2Adapter))
    adapter._search_dispatch = None
    adapter._search_dispatch_evidence = evidence
    adapter._search_dispatch_store = Store()
    resolved = await adapter.dispatch_search_candidate(
        principal=_User(42),
        request_id="request-1",
        experiment_fingerprint=graph.experiment.fingerprint,
        candidate_index=0,
        attempt_id=graph.attempt.attempt_id,
        dispatch_intent=dispatch_intent,
    )

    assert resolved == expected
    assert observed["principal"].id == "42"
    assert observed["store"]["principal"].id == "42"
    assert observed["store"]["reservation_id"] == _reservation("application-evidence")
    assert observed["store"]["runtime_request"] == runtime_request
    assert observed["store"]["runtime_preflight"] == runtime_preflight
    assert observed["store"]["payload"] == worker_payload
    assert observed["store"]["dispatch_request"] == dispatch_request

    with pytest.raises(ValueError, match="experiment differs from the materialized trial graph"):
        await adapter.dispatch_search_candidate(
            principal=_User(42),
            request_id="request-2",
            experiment_fingerprint=content_digest("different-experiment"),
            candidate_index=0,
            attempt_id=graph.attempt.attempt_id,
            dispatch_intent=dispatch_intent,
        )


@pytest.mark.asyncio
async def test_application_adapter_persists_and_replays_resource_mutations() -> None:
    class InMemoryAggregateStore:
        def __init__(self) -> None:
            self.current = ()
            self.receipts = ()

        async def get(self, key):
            return next((aggregate for aggregate in self.current if aggregate.key == key), None)

        async def list_type(self, aggregate_type):
            return tuple(
                aggregate
                for aggregate in self.current
                if aggregate.key.aggregate_type == aggregate_type
            )

        async def apply(self, request):
            resolved = resolve_storage_transaction(self.current, request, self.receipts)
            if resolved.decision is StorageTransactionDecision.APPLY:
                self.current = resolved.aggregates
                self.receipts = (*self.receipts, resolved.receipt)
            return resolved

    store = InMemoryAggregateStore()
    reader = PostgresResourceReader(store)
    adapter = cast(Any, object.__new__(PostgresStrategyLabV2Adapter))
    adapter._persistence = SimpleNamespace(aggregate_store=store)
    adapter._resources = reader
    accepted_at = NOW.replace(hour=13)
    conflict_clock = NOW.replace(hour=14)
    strategy_clock = NOW.replace(hour=15)
    package_clock = NOW.replace(hour=16)
    portfolio_clock = NOW.replace(hour=17)
    snapshot_clock = NOW.replace(hour=18)
    experiment_clock = NOW.replace(hour=19)
    trial_clock = NOW.replace(hour=20)
    attempt_clock = NOW.replace(hour=21)
    metric_clock = NOW.replace(hour=22)
    forward_clock = NOW.replace(hour=23)
    clocks = iter(
        (
            accepted_at,
            conflict_clock,
            strategy_clock,
            package_clock,
            portfolio_clock,
            snapshot_clock,
            experiment_clock,
            trial_clock,
            attempt_clock,
            metric_clock,
            forward_clock,
        )
    )
    adapter._clock = lambda: next(clocks)
    request = ResourceMutationRequest(
        ApiResourceType.ARTIFACT,
        "trial-key",
        {"attributes": {"resource_id": "trial-1", "name": "demo"}},
        NOW,
    )

    first = await adapter.create_resource(
        principal=_User(42), request_id="request-1", request=request
    )
    assert isinstance(first, ResourceMutationServiceResult)
    assert first.receipt is not None
    assert first.receipt.resource.id == "trial-1"
    assert first.receipt.resource.attributes["name"] == "demo"
    assert first.receipt.accepted_at == accepted_at

    replay = await adapter.create_resource(
        principal=_User(42), request_id="request-2", request=request
    )
    assert replay.resolution.decision.value == "replay_existing"
    assert replay.receipt == first.receipt

    owner_conflict = await adapter.create_resource(
        principal=_User(7), request_id="request-3", request=request
    )
    assert owner_conflict.resolution.decision.value == "reject"
    assert owner_conflict.receipt is None

    strategy = await adapter.create_resource(
        principal=_User(42),
        request_id="request-4",
        request=ResourceMutationRequest(
            ApiResourceType.STRATEGY,
            "strategy-key",
            {
                "attributes": {
                    "strategy_id": "momentum",
                    "version_id": "2026-09-17",
                    "sdk_version": "strategy-sdk.v2",
                    "source_digest": content_digest("strategy-source"),
                    "default_parameters": {"lookback": 20},
                }
            },
            NOW,
        ),
    )
    assert strategy.resolution.decision.value == "accept"
    assert strategy.receipt is not None
    assert strategy.receipt.resource.attributes["strategy_id"] == "momentum"
    assert strategy.receipt.resource.meta["domain_fingerprint"].startswith("sha256:")

    with pytest.raises(ValueError, match="referenced Strategy Lab domain object is unavailable"):
        await adapter.create_resource(
            principal=_User(7),
            request_id="request-cross-owner-package",
            request=ResourceMutationRequest(
                ApiResourceType.PACKAGE,
                "cross-owner-package-key",
                {
                    "attributes": {
                        "package_id": "unauthorized-package",
                        "strategy_fingerprint": strategy.receipt.resource.meta[
                            "domain_fingerprint"
                        ],
                        "package_format": "source_archive",
                        "archive_digest": content_digest("unauthorized-archive"),
                        "manifest_digest": content_digest("unauthorized-manifest"),
                        "dependency_lock_digest": content_digest("unauthorized-lock"),
                        "archive_byte_length": 128,
                        "entrypoint": "strategy.main:run",
                        "sdk_version": "strategy-sdk.v2",
                        "runtime_abi": "python3.12-linux-arm64",
                    }
                },
                NOW,
            ),
        )

    package = await adapter.create_resource(
        principal=_User(42),
        request_id="request-5",
        request=ResourceMutationRequest(
            ApiResourceType.PACKAGE,
            "package-key",
            {
                "attributes": {
                    "package_id": "momentum-package",
                    "strategy_fingerprint": strategy.receipt.resource.meta["domain_fingerprint"],
                    "package_format": "source_archive",
                    "archive_digest": content_digest("strategy-archive"),
                    "manifest_digest": content_digest("strategy-manifest"),
                    "dependency_lock_digest": content_digest("dependency-lock"),
                    "archive_byte_length": 128,
                    "entrypoint": "strategy.main:run",
                    "sdk_version": "strategy-sdk.v2",
                    "runtime_abi": "python3.12-linux-arm64",
                }
            },
            NOW,
        ),
    )
    assert package.resolution.decision.value == "accept"
    assert package.receipt is not None
    assert package.receipt.resource.attributes["package_format"] == "source_archive"
    assert package.receipt.resource.meta["domain_fingerprint"].startswith("sha256:")

    portfolio = await adapter.create_resource(
        principal=_User(42),
        request_id="request-6",
        request=ResourceMutationRequest(
            ApiResourceType.PORTFOLIO,
            "portfolio-key",
            {
                "attributes": {
                    "portfolio_id": "balanced",
                    "version_id": "v1",
                    "initial_capital": "100000",
                    "base_currency": "usd",
                    "components": [
                        {
                            "component_id": "momentum",
                            "strategy_fingerprint": strategy.receipt.resource.meta[
                                "domain_fingerprint"
                            ],
                            "instrument_ids": ["US.AAPL"],
                            "capital_weight": "1.0",
                        }
                    ],
                }
            },
            NOW,
        ),
    )
    assert portfolio.resolution.decision.value == "accept"
    assert portfolio.receipt is not None
    assert portfolio.receipt.resource.attributes["base_currency"] == "USD"
    assert portfolio.receipt.resource.meta["domain_fingerprint"].startswith("sha256:")

    snapshot = await adapter.create_resource(
        principal=_User(42),
        request_id="request-7",
        request=ResourceMutationRequest(
            ApiResourceType.SNAPSHOT,
            "snapshot-key",
            {
                "attributes": {
                    "snapshot_id": "snapshot-v1",
                    "provider_snapshot_id": "provider-snapshot-v1",
                    "preflight_report": _preflight_payload(),
                    "series": [
                        {
                            "instrument_id": "US.AAPL",
                            "event_type": "ohlcv",
                            "event_granularity": "bar",
                            "timeframe": "1d",
                            "session": "regular",
                            "feed": "consolidated",
                            "start": "2020-01-01T00:00:00Z",
                            "end": "2022-01-01T00:00:00Z",
                            "adjustment": "split_adjusted",
                            "corporate_action_semantics": "split-adjusted-v1",
                            "coverage_evidence_digest": content_digest("coverage-v1"),
                            "content_digest": content_digest("series-v1"),
                            "row_count": 500,
                        }
                    ],
                    "created_at": "2026-09-17T12:00:00Z",
                }
            },
            NOW,
        ),
    )
    assert snapshot.resolution.decision.value == "accept"
    assert snapshot.receipt is not None

    experiment = await adapter.create_resource(
        principal=_User(42),
        request_id="request-8",
        request=ResourceMutationRequest(
            ApiResourceType.EXPERIMENT,
            "experiment-key",
            {
                "attributes": {
                    "experiment_id": "momentum-search",
                    "portfolio_fingerprint": portfolio.receipt.resource.meta["domain_fingerprint"],
                    "strategy_fingerprints": [strategy.receipt.resource.meta["domain_fingerprint"]],
                    "snapshot_fingerprint": snapshot.receipt.resource.meta["domain_fingerprint"],
                    "capability_contract_digest": content_digest("capability-v1"),
                    "seed": 42,
                    "metric_definition_version": "strategy-lab.metrics.v1",
                    "engine_contract": {"engine": "nautilus", "version": "v2"},
                    "strategy_package_fingerprints": {
                        strategy.receipt.resource.meta[
                            "domain_fingerprint"
                        ]: package.receipt.resource.meta["domain_fingerprint"]
                    },
                }
            },
            NOW,
        ),
    )
    assert experiment.resolution.decision.value == "accept"
    assert experiment.receipt is not None
    assert experiment.receipt.resource.attributes["seed"] == 42
    assert experiment.receipt.resource.meta["domain_fingerprint"].startswith("sha256:")

    trial = await adapter.create_resource(
        principal=_User(42),
        request_id="request-9",
        request=ResourceMutationRequest(
            ApiResourceType.TRIAL,
            "trial-domain-key",
            {
                "attributes": {
                    "experiment_fingerprint": experiment.receipt.resource.meta[
                        "domain_fingerprint"
                    ],
                    "snapshot_fingerprint": snapshot.receipt.resource.meta["domain_fingerprint"],
                    "preflight_report": _preflight_payload(),
                    "parameter_set": {"lookback": 20},
                    "scenario": {"slippage_bps": 2},
                    "seed": 42,
                }
            },
            NOW,
        ),
    )
    assert trial.resolution.decision.value == "accept"
    assert trial.receipt is not None

    attempt = await adapter.create_resource(
        principal=_User(42),
        request_id="request-10",
        request=ResourceMutationRequest(
            ApiResourceType.ATTEMPT,
            "attempt-key",
            {
                "attributes": {
                    "attempt_id": content_digest("attempt-1"),
                    "trial_id": trial.receipt.resource.attributes["trial_id"],
                    "ordinal": 1,
                    "state": "queued",
                    "created_at": "2026-09-17T12:00:00Z",
                }
            },
            NOW,
        ),
    )
    assert attempt.resolution.decision.value == "accept"
    assert attempt.receipt is not None
    assert attempt.receipt.resource.attributes["state"] == "queued"
    assert attempt.receipt.resource.meta["domain_fingerprint"].startswith("sha256:")

    metric_set = await adapter.create_resource(
        principal=_User(42),
        request_id="request-11",
        request=ResourceMutationRequest(
            ApiResourceType.METRIC_SET,
            "metric-set-key",
            {
                "attributes": {
                    "metric_set_id": "metric-set-v1",
                    "trial_id": trial.receipt.resource.attributes["trial_id"],
                    "attempt_id": attempt.receipt.resource.attributes["attempt_id"],
                    "definition_version": "strategy-lab.metrics.v1",
                    "values": [
                        {
                            "name": "cumulative_net_return",
                            "value": "0.05",
                            "unit": "fraction",
                            "definition_version": "strategy-lab.metrics.v1",
                            "basis": "net",
                            "sample_size": 1,
                            "calculation_basis": "native_equity_trace",
                        }
                    ],
                    "created_at": "2026-09-17T12:00:00Z",
                }
            },
            NOW,
        ),
    )
    assert metric_set.resolution.decision.value == "accept"
    assert metric_set.receipt is not None

    forward_instance = await adapter.create_resource(
        principal=_User(42),
        request_id="request-12",
        request=ResourceMutationRequest(
            ApiResourceType.FORWARD_INSTANCE,
            "forward-instance-key",
            {
                "attributes": {
                    "instance_id": "forward-v1",
                    "portfolio_fingerprint": portfolio.receipt.resource.meta["domain_fingerprint"],
                    "warmup_snapshot_fingerprint": snapshot.receipt.resource.meta[
                        "domain_fingerprint"
                    ],
                    "carry_in_mode": "flat",
                    "state": "created",
                    "last_event_id": None,
                    "last_event_sequence": 0,
                    "correction_count": 0,
                    "created_at": "2026-09-17T12:00:00Z",
                    "updated_at": "2026-09-17T12:00:00Z",
                }
            },
            NOW,
        ),
    )
    assert forward_instance.resolution.decision.value == "accept"
    assert forward_instance.receipt is not None
