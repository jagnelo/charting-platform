from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.strategy_lab_v2.admission import ExecutionAdmissionLedger
from app.strategy_lab_v2.api_contracts import ApiErrorCode
from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.api_router import ApiAdapterError, ResourceMutationServiceResult
from app.strategy_lab_v2.application import (
    PostgresStrategyLabV2Adapter,
    ResultPublicationCompletionResolution,
    SearchDispatchEvidence,
    _principal_identity,
    create_registered_strategy_lab_v2_router,
    get_strategy_lab_v2_adapter,
)
from app.strategy_lab_v2.artifact_commit import ArtifactCommitLedger
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capability_summary import CapabilitySummary, CapabilitySummaryDecision
from app.strategy_lab_v2.contracts import ForwardState
from app.strategy_lab_v2.dispatch import DispatchRequest
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
from app.strategy_lab_v2.search_dispatch import SearchDispatchResolution, resolve_search_dispatch
from app.strategy_lab_v2.search_state import SearchCandidatePhase, new_search_execution_state
from app.strategy_lab_v2.storage import (
    StorageTransactionDecision,
    resolve_storage_transaction,
)
from app.strategy_lab_v2.tests.test_admission import _fixture, _reservation
from app.strategy_lab_v2.tests.test_execution_summary import (
    _outcome,
    _progress,
    _publication,
    _receipt,
)
from app.strategy_lab_v2.tests.test_postgres_forward_state import _instance
from app.strategy_lab_v2.tests.test_postgres_forward_state import _receipt as _forward_receipt
from app.strategy_lab_v2.tests.test_result_completion import _runtime_success


@dataclass
class _User:
    id: int


NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)


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

    assert await adapter.load_search_state(
        principal=_User(42), experiment_fingerprint=experiment
    ) == search_state
    assert await adapter.load_forward_instance(
        principal=_User(42), instance_id=instance.instance_id
    ) == forward_instance
    assert await adapter.load_forward_state(
        principal=_User(42), instance_id=instance.instance_id
    ) == forward_state

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
            dispatch_request=kwargs["dispatch_request"],
            prior_dispatches=(),
            now=NOW,
        )

    adapter = cast(Any, object.__new__(PostgresStrategyLabV2Adapter))
    adapter._search_dispatch = resolve
    dispatch = DispatchRequest(
        "dispatch-key",
        "attempt-1",
        content_digest("payload"),
        "strategy-backtest",
        NOW,
    )
    resolved = await adapter.dispatch_search_candidate(
        principal=_User(42),
        request_id="request-1",
        experiment_fingerprint=content_digest("experiment"),
        candidate_index=0,
        attempt_id="attempt-1",
        dispatch_request=dispatch,
        payload={"payload_digest": dispatch.payload_digest},
    )

    assert resolved.decision.value == "enqueue"
    assert observed["principal"].id == "42"
    assert observed["dispatch_request"] == dispatch


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
            dispatch_request=DispatchRequest(
                "dispatch-key",
                "attempt-1",
                content_digest("payload"),
                "strategy-backtest",
                NOW,
            ),
            payload={},
        )

    assert raised.value.error.code is ApiErrorCode.PRECONDITION_FAILED
    assert raised.value.error.status_code == 501


@pytest.mark.asyncio
async def test_application_search_dispatch_evidence_resolver_uses_durable_store() -> None:
    authorization, runtime_request, runtime_preflight, pool = _fixture()
    dispatch = DispatchRequest(
        "dispatch-key",
        "attempt-1",
        content_digest("payload"),
        "strategy-backtest",
        NOW,
    )
    observed: dict[str, Any] = {}

    async def evidence(**kwargs: Any) -> SearchDispatchEvidence:
        observed.update(kwargs)
        return SearchDispatchEvidence(
            authorization,
            runtime_request,
            runtime_preflight,
            _reservation("application-evidence"),
            NOW,
        )

    expected = resolve_search_dispatch(
        new_search_execution_state(
            content_digest("experiment-evidence"),
            (content_digest("trial-1"),),
            now=NOW,
        ),
        candidate_index=0,
        attempt_id="attempt-1",
        authorization=authorization,
        runtime_request=runtime_request,
        runtime_preflight=runtime_preflight,
        admission_ledger=ExecutionAdmissionLedger(),
        pool=pool,
        reservation_id=_reservation("application-evidence"),
        dispatch_request=dispatch,
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
        experiment_fingerprint=content_digest("experiment-evidence"),
        candidate_index=0,
        attempt_id="attempt-1",
        dispatch_request=dispatch,
        payload={},
    )

    assert resolved == expected
    assert observed["principal"].id == "42"
    assert observed["store"]["principal"].id == "42"
    assert observed["store"]["reservation_id"] == _reservation("application-evidence")
    assert observed["store"]["payload"] == {}


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
    experiment_clock = NOW.replace(hour=18)
    attempt_clock = NOW.replace(hour=19)
    clocks = iter(
        (
            accepted_at,
            conflict_clock,
            strategy_clock,
            package_clock,
            portfolio_clock,
            experiment_clock,
            attempt_clock,
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

    experiment = await adapter.create_resource(
        principal=_User(42),
        request_id="request-7",
        request=ResourceMutationRequest(
            ApiResourceType.EXPERIMENT,
            "experiment-key",
            {
                "attributes": {
                    "experiment_id": "momentum-search",
                    "portfolio_fingerprint": portfolio.receipt.resource.meta[
                        "domain_fingerprint"
                    ],
                    "strategy_fingerprints": [
                        strategy.receipt.resource.meta["domain_fingerprint"]
                    ],
                    "snapshot_fingerprint": content_digest("snapshot-v1"),
                    "capability_contract_digest": content_digest("capability-v1"),
                    "seed": 42,
                    "metric_definition_version": "strategy-lab.metrics.v1",
                    "engine_contract": {"engine": "nautilus", "version": "v2"},
                }
            },
            NOW,
        ),
    )
    assert experiment.resolution.decision.value == "accept"
    assert experiment.receipt is not None
    assert experiment.receipt.resource.attributes["seed"] == 42
    assert experiment.receipt.resource.meta["domain_fingerprint"].startswith("sha256:")

    attempt = await adapter.create_resource(
        principal=_User(42),
        request_id="request-8",
        request=ResourceMutationRequest(
            ApiResourceType.ATTEMPT,
            "attempt-key",
            {
                "attributes": {
                    "attempt_id": content_digest("attempt-1"),
                    "trial_id": content_digest("trial-1"),
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
