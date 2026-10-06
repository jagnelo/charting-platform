from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from fastapi import FastAPI

from app.strategy_lab_v2.admission import ExecutionAdmissionLedger
from app.strategy_lab_v2.api_contracts import ApiCursor
from app.strategy_lab_v2.api_resources import (
    ApiResourceType,
    ResourceCollection,
    ResourceDocument,
    ResourceIdentifier,
)
from app.strategy_lab_v2.api_router import (
    ApiAdapterError,
    ResourceMutationServiceResult,
    SubmissionServiceResult,
    _json_value,
    _parse_forward_dispatch,
    _parse_forward_lifecycle,
    _parse_forward_transaction,
    _parse_walk_forward_definition_request,
    _request_id,
    _safe_header_value,
    create_strategy_lab_router,
    serialize_forward_account,
    serialize_forward_event_dispatch,
    serialize_forward_event_transaction,
    serialize_forward_lifecycle,
    serialize_forward_replays,
    serialize_forward_warmup,
    serialize_resource,
    serialize_search_state_snapshot,
)
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capability_summary import (
    CapabilitySummary,
    CapabilitySummaryDecision,
)
from app.strategy_lab_v2.commands import (
    CommandEffect,
    ExecutionCommandDecision,
    ExecutionCommandKind,
    ExecutionCommandLedger,
    ExecutionCommandReceipt,
    ExecutionCommandResolution,
)
from app.strategy_lab_v2.contracts import (
    ArtifactManifest,
    ArtifactRetention,
    CarryInMode,
    ForwardInstance,
    ForwardState,
    MetricBasis,
    MetricValue,
)
from app.strategy_lab_v2.dispatch import DispatchRequest, SearchDispatchIntent
from app.strategy_lab_v2.experiments import WalkForwardMode, WalkForwardSpec
from app.strategy_lab_v2.forward_account import initial_forward_account_state
from app.strategy_lab_v2.forward_corrections import CounterfactualReplayPlan
from app.strategy_lab_v2.forward_event_dispatch import (
    ForwardEventDispatchResolution,
    resolve_forward_event_dispatch,
)
from app.strategy_lab_v2.forward_event_transaction import (
    ForwardEventTransactionDecision,
    ForwardEventTransactionResolution,
)
from app.strategy_lab_v2.forward_warmup import (
    ForwardWarmupDecision,
    ForwardWarmupReceipt,
    ForwardWarmupResolution,
    resolve_forward_warmup,
)
from app.strategy_lab_v2.legacy import (
    LegacyImportDecision,
    LegacyImportRecord,
    LegacyImportRegistry,
    LegacyImportReport,
    LegacyImportResolution,
)
from app.strategy_lab_v2.lifecycle import (
    ForwardCursor,
    ForwardEventDisposition,
    observe_forward_event,
)
from app.strategy_lab_v2.postgres_forward_state import (
    ForwardStateMutationDecision,
    ForwardStateMutationResolution,
)
from app.strategy_lab_v2.postgres_walk_forward_plan import (
    WalkForwardDefinitionDecision,
    WalkForwardDefinitionResolution,
)
from app.strategy_lab_v2.postgres_walk_forward_summary import (
    WalkForwardSummaryDecision,
    WalkForwardSummaryResolution,
)
from app.strategy_lab_v2.resource_mutations import (
    ResourceMutationDecision,
    ResourceMutationResolution,
    create_resource_mutation_receipt,
)
from app.strategy_lab_v2.search_dispatch import SearchDispatchResolution, resolve_search_dispatch
from app.strategy_lab_v2.search_state import (
    SearchExecutionState,
    SearchStateDecision,
    SearchStateResolution,
    new_search_execution_state,
    request_search_cancellation,
)
from app.strategy_lab_v2.submissions import (
    SubmissionDecision,
    SubmissionResolution,
    create_submission_receipt,
)
from app.strategy_lab_v2.tests.test_admission import _fixture, _reservation
from app.strategy_lab_v2.tests.test_forward_corrections import _event as correction_event
from app.strategy_lab_v2.tests.test_forward_corrections import _state as forward_state
from app.strategy_lab_v2.tests.test_walk_forward_summary import _summary_fixture
from app.strategy_lab_v2.walk_forward_search import (
    SelectionDirection,
    WalkForwardExecutionDefinition,
)
from app.strategy_lab_v2.walk_forward_summary import (
    WALK_FORWARD_NATIVE_EQUITY_CURVE_MEDIA_TYPE,
    WALK_FORWARD_NATIVE_EQUITY_CURVE_SCHEMA,
    WalkForwardNativeOosMetricSummary,
)

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
SNAPSHOT = content_digest({"snapshot": "one"})


def _document(resource_id: str = "trial-1") -> ResourceDocument:
    return ResourceDocument(
        ResourceIdentifier(
            ApiResourceType.TRIAL,
            resource_id,
            revision_digest=content_digest({"trial": resource_id}),
        ),
        attributes={"name": "mean-reversion", "ratio": Decimal("1.25")},
        relationships={
            "experiment": (ResourceIdentifier(ApiResourceType.EXPERIMENT, "experiment-1"),)
        },
        meta={"source": "test"},
    )


def test_read_only_state_serializers_preserve_typed_identity() -> None:
    state = new_search_execution_state(content_digest("experiment"), (content_digest("trial"),))
    payload = serialize_search_state_snapshot(state, request_id="request-1")
    assert payload["data"]["type"] == "search-experiments"
    assert payload["data"]["id"] == state.experiment_fingerprint
    assert payload["data"]["meta"]["decision"] == "read"
    assert payload["data"]["meta"]["state_fingerprint"] == state.fingerprint


def test_forward_account_serializer_preserves_authenticated_snapshot_identity() -> None:
    state = initial_forward_account_state(
        "forward-1", base_currency="USD", initial_cash={"USD": Decimal("1000")}
    )
    payload = serialize_forward_account(state, request_id="request-1")
    assert payload["data"]["type"] == "forward-accounts"
    assert payload["data"]["id"] == "forward-1"
    assert payload["data"]["attributes"]["cash"][0]["amount"] == "1000"
    assert payload["data"]["meta"]["state_fingerprint"] == state.fingerprint


def test_json_value_serializes_set_like_checkpoint_fields_deterministically() -> None:
    assert _json_value(frozenset({"event-b", "event-a"})) == ["event-a", "event-b"]


def test_forward_event_transaction_parser_requires_correction_evidence() -> None:
    event = correction_event("live-0", 0)
    body = {
        "event": {
            "event_id": event.event_id,
            "sequence": event.sequence,
            "event_time": event.event_time.isoformat(),
            "arrived_at": event.arrived_at.isoformat(),
            "source_digest": event.source_digest,
        },
        "observation": {
            "disposition": ForwardEventDisposition.CORRECTION.value,
            "stale": True,
            "missing_sequence_start": None,
            "missing_sequence_end": None,
            "correction_requires_counterfactual_replay": True,
            "next_cursor": {
                "last_sequence": -1,
                "last_event_id": None,
                "last_event_time": None,
            },
        },
    }
    with pytest.raises(ValueError, match="correction observations require"):
        _parse_forward_transaction(body, instance_id="forward-1")


def test_forward_event_transaction_serializer_preserves_state_and_resolution_identity() -> None:
    state = forward_state()
    event = correction_event("live-0", 0)
    resolution = ForwardEventTransactionResolution(
        ForwardEventTransactionDecision.ACCEPTED,
        state,
        content_digest(event),
    )
    payload = serialize_forward_event_transaction(resolution, request_id="request-1")
    assert payload["data"]["type"] == "forward-event-transactions"
    assert payload["data"]["id"] == resolution.event_fingerprint
    assert payload["data"]["meta"]["resolution_fingerprint"] == resolution.fingerprint
    assert payload["data"]["attributes"]["state"]["checkpoint"]["processed_event_ids"] == []


def test_forward_event_transaction_serializer_rejects_cross_instance_replay_plan() -> None:
    state = forward_state()
    event = correction_event("live-0", 0)
    replay_plan = CounterfactualReplayPlan(
        replay_id=content_digest("cross-instance-replay"),
        instance_id="forward-2",
        correction_event_id=event.event_id,
        original_event_id=event.event_id,
        base_checkpoint_fingerprint=state.checkpoint.fingerprint,
        warmup_receipt_fingerprint=state.warmup_receipt_fingerprint,
        planned_at=NOW,
    )
    resolution = ForwardEventTransactionResolution(
        ForwardEventTransactionDecision.CORRECTION_ACCEPTED,
        state,
        content_digest(event),
        replay_plan,
    )

    with pytest.raises(ValueError, match="replay plan instance"):
        serialize_forward_event_transaction(resolution, request_id="request-1")


def test_forward_event_dispatch_parser_and_serializer_preserve_outbox_identity() -> None:
    state = forward_state()
    event = correction_event("live-0", 0)
    observation = observe_forward_event(ForwardCursor(), event)
    event_fingerprint = content_digest(event)
    payload_digest = content_digest(
        {"event_fingerprint": event_fingerprint, "replay_plan_fingerprint": None}
    )
    dispatch = DispatchRequest(
        idempotency_key="forward-dispatch-1",
        attempt_id="forward-1",
        payload_digest=payload_digest,
        queue_name="forward",
        created_at=NOW,
    )
    body = {
        "event": {
            "event_id": event.event_id,
            "sequence": event.sequence,
            "event_time": event.event_time.isoformat(),
            "arrived_at": event.arrived_at.isoformat(),
            "source_digest": event.source_digest,
        },
        "observation": {
            "disposition": observation.disposition.value,
            "stale": observation.stale,
            "missing_sequence_start": observation.missing_sequence_start,
            "missing_sequence_end": observation.missing_sequence_end,
            "correction_requires_counterfactual_replay": observation.correction_requires_counterfactual_replay,
            "next_cursor": {
                "last_sequence": observation.next_cursor.last_sequence,
                "last_event_id": observation.next_cursor.last_event_id,
                "last_event_time": observation.next_cursor.last_event_time.isoformat()
                if observation.next_cursor.last_event_time is not None
                else None,
            },
            "buffer_event": observation.buffer_event,
        },
        "dispatch": {
            "idempotency_key": dispatch.idempotency_key,
            "attempt_id": dispatch.attempt_id,
            "payload_digest": dispatch.payload_digest,
            "queue_name": dispatch.queue_name,
            "created_at": dispatch.created_at.isoformat(),
        },
        "payload": {"event_fingerprint": event_fingerprint, "replay_plan_fingerprint": None},
    }
    parsed_event, parsed_observation, parsed_dispatch, parsed_payload, correction = (
        _parse_forward_dispatch(body, instance_id="forward-1")
    )
    assert parsed_event == event
    assert parsed_observation == observation
    assert parsed_dispatch == dispatch
    assert parsed_payload == body["payload"]
    assert correction is None
    resolution = resolve_forward_event_dispatch(
        state, parsed_event, parsed_observation, dispatch_request=parsed_dispatch
    )
    payload = serialize_forward_event_dispatch(resolution, request_id="request-1")
    assert payload["data"]["type"] == "forward-event-dispatches"
    assert payload["data"]["id"] == dispatch.fingerprint


def test_forward_event_dispatch_serializer_rejects_nested_state_mismatch() -> None:
    state = forward_state()
    event = correction_event("live-0", 0)
    observation = observe_forward_event(ForwardCursor(), event)
    dispatch_request = DispatchRequest(
        idempotency_key="forward-dispatch-mismatch",
        attempt_id="forward-1",
        payload_digest=content_digest(
            {"event_fingerprint": content_digest(event), "replay_plan_fingerprint": None}
        ),
        queue_name="forward",
        created_at=NOW,
    )
    resolution = resolve_forward_event_dispatch(
        state,
        event,
        observation,
        dispatch_request=dispatch_request,
    )
    mismatched_transaction = ForwardEventTransactionResolution(
        resolution.event_transaction.decision,
        replace(state, warmup_receipt_fingerprint=content_digest("different-warmup")),
        resolution.event_transaction.event_fingerprint,
        resolution.event_transaction.replay_plan,
    )
    mismatched = ForwardEventDispatchResolution(
        resolution.decision,
        state,
        mismatched_transaction,
        resolution.dispatch_resolution,
        resolution.envelope,
    )

    with pytest.raises(ValueError, match="transaction state"):
        serialize_forward_event_dispatch(mismatched, request_id="request-1")


def test_forward_warmup_parser_and_serializer_preserve_carry_in_identity() -> None:
    warming = ForwardInstance(
        "forward-1",
        content_digest("portfolio"),
        SNAPSHOT,
        CarryInMode.FLAT,
        ForwardState.WARMING_UP,
        None,
        0,
        0,
        NOW,
        NOW,
    )
    receipt = ForwardWarmupReceipt(
        "forward-1",
        SNAPSHOT,
        CarryInMode.FLAT,
        content_digest("warmup-result"),
        NOW,
    )
    body = {
        "instance_id": receipt.instance_id,
        "warmup_snapshot_fingerprint": receipt.warmup_snapshot_fingerprint,
        "carry_in_mode": receipt.carry_in_mode.value,
        "warmup_result_fingerprint": receipt.warmup_result_fingerprint,
        "completed_at": receipt.completed_at.isoformat(),
        "final_event_id": receipt.final_event_id,
        "final_event_sequence": receipt.final_event_sequence,
        "final_event_fingerprint": receipt.final_event_fingerprint,
    }
    from app.strategy_lab_v2.api_router import _parse_forward_warmup

    parsed = _parse_forward_warmup(body, instance_id="forward-1")
    assert parsed == receipt
    resolution = resolve_forward_warmup(warming, parsed)
    payload = serialize_forward_warmup(resolution, request_id="request-1")
    assert payload["data"]["type"] == "forward-warmups"
    assert payload["data"]["id"] == receipt.fingerprint
    assert payload["data"]["meta"]["decision"] == "complete"


def test_forward_warmup_serializer_rejects_cross_instance_receipt() -> None:
    instance = ForwardInstance(
        "forward-1",
        content_digest("portfolio"),
        SNAPSHOT,
        CarryInMode.FLAT,
        ForwardState.ACTIVE,
        None,
        0,
        0,
        NOW,
        NOW,
    )
    receipt = ForwardWarmupReceipt(
        "forward-2",
        SNAPSHOT,
        CarryInMode.FLAT,
        content_digest("warmup-result"),
        NOW,
    )

    with pytest.raises(ValueError, match="receipt instance"):
        serialize_forward_warmup(
            ForwardWarmupResolution(ForwardWarmupDecision.REPLAY_EXISTING, instance, receipt),
            request_id="request-1",
        )


def test_forward_lifecycle_parser_and_serializer_preserve_transition_identity() -> None:
    instance = forward_state().checkpoint.instance
    target, now = _parse_forward_lifecycle({"target": instance.state.value, "now": NOW.isoformat()})
    assert target is instance.state
    assert now == NOW
    resolution = ForwardStateMutationResolution(
        ForwardStateMutationDecision.APPLIED,
        instance,
    )
    payload = serialize_forward_lifecycle(resolution, request_id="request-1")
    assert payload["data"]["type"] == "forward-lifecycle-transitions"
    assert payload["data"]["attributes"]["decision"] == "applied"
    assert payload["data"]["attributes"]["instance"]["instance_id"] == instance.instance_id


def _capability_document() -> ResourceDocument:
    return ResourceDocument(
        ResourceIdentifier(
            ApiResourceType.CAPABILITY_SUMMARY,
            content_digest("capability-summary"),
            revision_digest=content_digest("capability-summary-revision"),
        ),
        attributes={
            "decision": "rigorous",
            "data_gaps": (),
            "execution_gaps": (),
            "degradations": (),
            "ranking_eligible": True,
            "executable": True,
            "authoritative": True,
            "can_publish_authoritative_results": True,
        },
        meta={
            "report_fingerprint": content_digest("capability-report"),
            "binding_fingerprint": content_digest("capability-binding"),
        },
    )


def _legacy_import_document() -> ResourceDocument:
    return ResourceDocument(
        ResourceIdentifier(
            ApiResourceType.LEGACY_IMPORT,
            "legacy-definition-1",
            revision_digest=content_digest("legacy-record"),
        ),
        attributes={
            "original": {
                "legacy_id": "legacy-definition-1",
                "kind": "definition",
                "source_version": "strategy-lab-v1",
                "payload_digest": content_digest("legacy-payload"),
            },
            "assessment": {
                "supported": True,
                "conversion_fingerprint": content_digest("conversion"),
                "notes": ("converted",),
            },
        },
        meta={"replay_equivalent": False},
    )


class FakeAdapter:
    def __init__(self) -> None:
        self.submissions: list[tuple[str, str, dict[str, Any]]] = []
        self.commands: list[tuple[str, str]] = []
        self.mutations: list[tuple[str, str, str]] = []
        self.legacy_imports: list[str] = []
        self.preflights: list[tuple[str, str, str]] = []
        self.search_states: dict[str, SearchExecutionState] = {}
        self.search_dispatches: list[SearchDispatchResolution] = []
        self.walk_forward_dispatch_requests: list[dict[str, Any]] = []
        self.walk_forward_bulk_dispatch_requests: list[dict[str, Any]] = []
        self.walk_forward_phase_requests: list[dict[str, Any]] = []
        self.walk_forward_result_requests: list[dict[str, Any]] = []
        self.document = _document()

    async def list_resources(self, **kwargs: Any) -> ResourceCollection:
        document = (
            _capability_document()
            if kwargs["resource_type"] is ApiResourceType.CAPABILITY_SUMMARY
            else _legacy_import_document()
            if kwargs["resource_type"] is ApiResourceType.LEGACY_IMPORT
            else self.document
        )
        return ResourceCollection(
            request_id=kwargs["request_id"],
            resource_type=kwargs["resource_type"],
            snapshot_digest=SNAPSHOT,
            items=(document,),
            has_more=False,
        )

    async def get_resource(self, **kwargs: Any) -> ResourceDocument | None:
        document = (
            _capability_document()
            if kwargs["resource_type"] is ApiResourceType.CAPABILITY_SUMMARY
            else _legacy_import_document()
            if kwargs["resource_type"] is ApiResourceType.LEGACY_IMPORT
            else self.document
        )
        if kwargs["resource_id"] == document.id:
            return document
        return None

    async def submit(self, **kwargs: Any) -> SubmissionServiceResult:
        request = kwargs["request"]
        payload = dict(kwargs["payload"])
        self.submissions.append((request.idempotency_key, request.operation, payload))
        receipt = create_submission_receipt(request, accepted_at=NOW)
        return SubmissionServiceResult(
            SubmissionResolution(SubmissionDecision.ACCEPT, request.fingerprint), receipt
        )

    async def create_resource(self, **kwargs: Any) -> ResourceMutationServiceResult:
        request = kwargs["request"]
        self.mutations.append(
            (request.resource_type.value, request.idempotency_key, request.payload_digest)
        )
        receipt = create_resource_mutation_receipt(request, self.document, accepted_at=NOW)
        return ResourceMutationServiceResult(
            ResourceMutationResolution(ResourceMutationDecision.ACCEPT, request.fingerprint),
            receipt,
        )

    async def command(self, **kwargs: Any) -> ExecutionCommandResolution:
        command = kwargs["command"]
        self.commands.append((kwargs["idempotency_key"], command.kind.value))
        receipt = ExecutionCommandReceipt(
            command_id=command.command_id,
            command_fingerprint=command.fingerprint,
            attempt_id=command.attempt_id,
            kind=command.kind,
            effect=(
                CommandEffect.CANCELLATION_REQUESTED
                if command.kind is ExecutionCommandKind.CANCEL
                else CommandEffect.RETRY_REQUESTED
            ),
            accepted_at=NOW,
        )
        return ExecutionCommandResolution(
            ExecutionCommandDecision.ACCEPT,
            ledger=ExecutionCommandLedger((receipt,)),
            command_fingerprint=command.fingerprint,
            receipt=receipt,
        )

    async def import_legacy(self, **kwargs: Any) -> LegacyImportResolution:
        request = kwargs["request"]
        assessment = kwargs["assessment"]
        self.legacy_imports.append(request.legacy_id)
        original = request.original
        report = LegacyImportReport(
            LegacyImportDecision.ACCEPT,
            original,
            assessment.supported,
            assessment.conversion_fingerprint,
            assessment.notes,
        )
        registry = LegacyImportRegistry(
            (LegacyImportRecord(original, request.fingerprint, assessment),)
        )
        return LegacyImportResolution(LegacyImportDecision.ACCEPT, registry, report)

    async def preflight_capability(self, **kwargs: Any) -> CapabilitySummary:
        self.preflights.append(
            (kwargs["idempotency_key"], kwargs["request_id"], kwargs["payload_digest"])
        )
        return CapabilitySummary(
            report_fingerprint=content_digest("capability-report"),
            binding_fingerprint=content_digest("capability-binding"),
            decision=CapabilitySummaryDecision.RIGOROUS,
            data_gaps=(),
            execution_gaps=(),
            degradations=(),
            ranking_eligible=True,
            executable=True,
            authoritative=True,
            can_publish_authoritative_results=True,
        )

    async def initialize_search(self, **kwargs: Any) -> SearchStateResolution:
        state = kwargs["state"]
        current = self.search_states.get(state.experiment_fingerprint)
        if current is not None:
            if current == state:
                return SearchStateResolution(SearchStateDecision.REPLAY_EXISTING, current)
            return SearchStateResolution(
                SearchStateDecision.REJECT,
                current,
                rejection_reason="search experiment is already bound to different content",
            )
        self.search_states[state.experiment_fingerprint] = state
        return SearchStateResolution(SearchStateDecision.APPLY, state)

    async def cancel_search(self, **kwargs: Any) -> SearchStateResolution:
        experiment_fingerprint = kwargs["experiment_fingerprint"]
        state = self.search_states[experiment_fingerprint]
        resolution = request_search_cancellation(
            state,
            request_id=kwargs["cancellation_request_id"],
            now=kwargs["now"],
        )
        if resolution.decision is SearchStateDecision.APPLY:
            self.search_states[experiment_fingerprint] = resolution.state
        return resolution

    async def dispatch_search_candidate(self, **kwargs: Any) -> SearchDispatchResolution:
        authorization, runtime_request, runtime_preflight, pool = _fixture()
        dispatch_request = kwargs["dispatch_intent"].bind_payload(
            content_digest("test-worker-payload")
        )
        state = new_search_execution_state(
            kwargs["experiment_fingerprint"],
            (content_digest("trial-1"),),
            now=NOW,
        )
        resolution = resolve_search_dispatch(
            state,
            candidate_index=kwargs["candidate_index"],
            attempt_id=kwargs["attempt_id"],
            authorization=authorization,
            runtime_request=runtime_request,
            runtime_preflight=runtime_preflight,
            admission_ledger=ExecutionAdmissionLedger(),
            pool=pool,
            reservation_id=_reservation("api"),
            dispatch_request=dispatch_request,
            prior_dispatches=(),
            now=NOW,
        )
        self.search_dispatches.append(resolution)
        return resolution

    async def dispatch_walk_forward_training_candidate(
        self, **kwargs: Any
    ) -> SearchDispatchResolution:
        self.walk_forward_dispatch_requests.append(kwargs)
        attempt_id = "walk-forward-generated-attempt"
        return await self.dispatch_search_candidate(
            principal=kwargs["principal"],
            request_id=kwargs["request_id"],
            experiment_fingerprint=kwargs["experiment_fingerprint"],
            candidate_index=kwargs["candidate_index"],
            attempt_id=attempt_id,
            dispatch_intent=SearchDispatchIntent(
                kwargs["idempotency_key"],
                attempt_id,
                kwargs["queue_name"],
                NOW,
            ),
        )

    async def dispatch_walk_forward_ready_candidates(
        self, **kwargs: Any
    ) -> tuple[tuple[int, SearchDispatchResolution], ...]:
        self.walk_forward_bulk_dispatch_requests.append(kwargs)
        result = await self.dispatch_walk_forward_training_candidate(
            principal=kwargs["principal"],
            request_id=kwargs["request_id"],
            idempotency_key=kwargs["idempotency_key"],
            experiment_fingerprint=kwargs["experiment_fingerprint"],
            candidate_index=0,
            queue_name=kwargs["queue_name"],
        )
        return ((0, result),)

    async def append_walk_forward_oos_candidates(self, **kwargs: Any) -> Any:
        self.walk_forward_phase_requests.append(kwargs)
        state = new_search_execution_state(
            kwargs["experiment_fingerprint"], (content_digest("training-trial"),), now=NOW
        )
        return SimpleNamespace(
            resolution=SearchStateResolution(SearchStateDecision.REPLAY_EXISTING, state),
            oos_task_bindings=(),
        )

    async def collect_walk_forward_oos_results(self, **kwargs: Any) -> Any:
        self.walk_forward_result_requests.append(kwargs)
        return (
            SimpleNamespace(
                oos_task_fingerprint=content_digest("oos-task-0"),
                result_fingerprint=content_digest("oos-result-0"),
                metric_id="net_return",
                value=Decimal("0.125"),
            ),
        )

    async def persist_walk_forward_oos_summary(self, **kwargs: Any) -> Any:
        self.walk_forward_result_requests.append(kwargs)
        return SimpleNamespace(
            summary=_summary_fixture(),
            decision=SimpleNamespace(value="persisted"),
            aggregate_version=1,
        )


class ConflictAdapter(FakeAdapter):
    async def submit(self, **kwargs: Any) -> SubmissionServiceResult:
        request = kwargs["request"]
        previous_request = type(request)(
            idempotency_key=request.idempotency_key,
            operation=request.operation,
            attempt_id=request.attempt_id,
            payload_digest=content_digest({"previous": True}),
            submitted_at=NOW,
        )
        previous_receipt = create_submission_receipt(previous_request, accepted_at=NOW)
        return SubmissionServiceResult(
            SubmissionResolution(
                SubmissionDecision.IDEMPOTENCY_CONFLICT,
                request.fingerprint,
                previous_receipt,
            ),
            previous_receipt,
        )


class WarmupRouteAdapter(FakeAdapter):
    async def complete_forward_warmup(self, **kwargs: Any):
        receipt = kwargs["receipt"]
        warming = ForwardInstance(
            receipt.instance_id,
            content_digest("portfolio"),
            receipt.warmup_snapshot_fingerprint,
            receipt.carry_in_mode,
            ForwardState.WARMING_UP,
            None,
            0,
            0,
            NOW,
            NOW,
        )
        return resolve_forward_warmup(warming, receipt)


class ForwardRouteAdapter(WarmupRouteAdapter):
    async def transact_forward_event(self, **kwargs: Any) -> ForwardEventTransactionResolution:
        return ForwardEventTransactionResolution(
            ForwardEventTransactionDecision.ACCEPTED,
            forward_state(),
            content_digest(kwargs["event"]),
        )

    async def dispatch_forward_event(self, **kwargs: Any) -> ForwardEventDispatchResolution:
        return resolve_forward_event_dispatch(
            forward_state(),
            kwargs["event"],
            kwargs["observation"],
            dispatch_request=kwargs["dispatch_request"],
            correction_command=kwargs.get("correction_command"),
        )

    async def transition_forward_instance(self, **kwargs: Any) -> ForwardStateMutationResolution:
        return ForwardStateMutationResolution(
            ForwardStateMutationDecision.APPLIED,
            forward_state().checkpoint.instance,
        )


class ReplayRouteAdapter(ForwardRouteAdapter):
    async def load_forward_replays(self, **kwargs: Any) -> tuple[CounterfactualReplayPlan, ...]:
        return (
            CounterfactualReplayPlan(
                replay_id=content_digest("replay-1"),
                instance_id=kwargs["instance_id"],
                correction_event_id="correction-1",
                original_event_id="live-0",
                base_checkpoint_fingerprint=forward_state().checkpoint.fingerprint,
                warmup_receipt_fingerprint=forward_state().warmup_receipt_fingerprint,
                planned_at=NOW,
            ),
        )


class ResourceConflictAdapter(FakeAdapter):
    async def create_resource(self, **kwargs: Any) -> ResourceMutationServiceResult:
        request = kwargs["request"]
        resolution = ResourceMutationResolution(
            ResourceMutationDecision.IDEMPOTENCY_CONFLICT,
            request.fingerprint,
        )
        return ResourceMutationServiceResult(resolution)


class RequestDriftAdapter(FakeAdapter):
    async def list_resources(self, **kwargs: Any) -> ResourceCollection:
        collection = await super().list_resources(**kwargs)
        return ResourceCollection(
            request_id="different-request",
            resource_type=collection.resource_type,
            snapshot_digest=collection.snapshot_digest,
            items=collection.items,
            has_more=collection.has_more,
            next_cursor=collection.next_cursor,
        )


class SnapshotDriftAdapter(FakeAdapter):
    async def list_resources(self, **kwargs: Any) -> ResourceCollection:
        collection = await super().list_resources(**kwargs)
        return ResourceCollection(
            request_id=collection.request_id,
            resource_type=collection.resource_type,
            snapshot_digest=content_digest({"snapshot": "different"}),
            items=collection.items,
            has_more=collection.has_more,
            next_cursor=collection.next_cursor,
        )


class _SyncASGIClient:
    """Synchronous test facade over the async ASGI transport.

    Starlette's synchronous ``TestClient`` can hang while entering its portal
    in this repository's constrained runtime. The route tests only need basic
    GET/POST calls, so keep the existing synchronous call sites while running
    each request through the same in-process transport used by the async tests.
    """

    def __init__(self, app: FastAPI) -> None:
        self._app = app

    def __enter__(self) -> _SyncASGIClient:
        return self

    def __exit__(self, *_: Any) -> None:
        return None

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._request("POST", url, **kwargs)

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        async def execute() -> httpx.Response:
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://strategy-lab.test"
            ) as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(execute())


def _client(adapter: Any) -> _SyncASGIClient:
    async def get_adapter() -> Any:
        return adapter

    async def get_principal() -> str:
        return "user-1"

    app = FastAPI()
    app.include_router(
        create_strategy_lab_router(
            adapter_dependency=get_adapter,
            principal_dependency=get_principal,
            request_id_factory=lambda: "request-generated",
            clock=lambda: NOW,
        ),
        prefix="/api/v1",
    )
    return _SyncASGIClient(app)


def _asgi_app(adapter: Any) -> FastAPI:
    async def get_adapter() -> Any:
        return adapter

    async def get_principal() -> str:
        return "user-1"

    app = FastAPI()
    app.include_router(
        create_strategy_lab_router(
            adapter_dependency=get_adapter,
            principal_dependency=get_principal,
            request_id_factory=lambda: "request-generated",
            clock=lambda: NOW,
        ),
        prefix="/api/v1",
    )
    return app


def test_walk_forward_wire_contract_accepts_policy_but_no_observation_calendar() -> None:
    experiment_fingerprint = content_digest("walk-forward-experiment")
    body = {
        "candidate_fingerprints": [content_digest("candidate-a")],
        "spec": {
            "train_periods": 30,
            "test_periods": 10,
            "step_periods": 10,
            "mode": "rolling",
            "gap_periods": 2,
            "embargo_periods": 1,
        },
        "metric_id": "net_return",
        "direction": "maximize",
        "max_tasks": 1000,
    }

    request = _parse_walk_forward_definition_request(
        body,
        experiment_fingerprint=experiment_fingerprint,
        request_id="walk-forward-request",
    )

    assert request.candidate_fingerprints == tuple(body["candidate_fingerprints"])
    assert request.spec.gap_periods == 2
    assert request.spec.embargo_periods == 1
    assert request.max_tasks == 1000

    with pytest.raises(ApiAdapterError, match="walk-forward body fields are invalid"):
        _parse_walk_forward_definition_request(
            {**body, "observation_boundaries": ["2024-01-01T00:00:00Z"]},
            experiment_fingerprint=experiment_fingerprint,
            request_id="walk-forward-request",
        )


def test_walk_forward_route_persists_and_returns_resolved_calendar_metadata() -> None:
    experiment_fingerprint = content_digest("walk-forward-route-experiment")
    candidate_fingerprint = content_digest("walk-forward-route-candidate")
    definition = WalkForwardExecutionDefinition(
        experiment_fingerprint=experiment_fingerprint,
        candidate_fingerprints=(candidate_fingerprint,),
        observation_boundaries=(NOW, NOW.replace(day=3), NOW.replace(day=3, microsecond=1)),
        spec=WalkForwardSpec(1, 1, 1, WalkForwardMode.ROLLING),
        metric_id="net_return",
        direction=SelectionDirection.MAXIMIZE,
    )

    class Adapter:
        async def create_walk_forward_definition(self, **kwargs: Any):
            assert kwargs["experiment_fingerprint"] == experiment_fingerprint
            assert kwargs["request"].candidate_fingerprints == (candidate_fingerprint,)
            return WalkForwardDefinitionResolution(
                WalkForwardDefinitionDecision.APPLY,
                definition,
                aggregate_version=1,
            )

    response = _client(Adapter()).post(
        f"/api/v1/strategy-lab/v2/experiments/{experiment_fingerprint}/walk-forward",
        headers={"Idempotency-Key": "walk-forward-route-1"},
        json={
            "candidate_fingerprints": [candidate_fingerprint],
            "spec": {
                "train_periods": 1,
                "test_periods": 1,
                "step_periods": 1,
                "mode": "rolling",
            },
            "metric_id": "net_return",
            "direction": "maximize",
        },
    )

    assert response.status_code == 202, response.text
    assert response.json()["data"]["id"] == definition.fingerprint
    assert response.json()["data"]["attributes"]["observation_count"] == 2


@pytest.mark.asyncio
async def test_warmup_route_executes_through_asgi_boundary() -> None:
    adapter = WarmupRouteAdapter()
    app = _asgi_app(adapter)
    receipt = ForwardWarmupReceipt(
        "forward-1",
        SNAPSHOT,
        CarryInMode.FLAT,
        content_digest("warmup-result"),
        NOW,
    )
    body = {
        "instance_id": receipt.instance_id,
        "warmup_snapshot_fingerprint": receipt.warmup_snapshot_fingerprint,
        "carry_in_mode": receipt.carry_in_mode.value,
        "warmup_result_fingerprint": receipt.warmup_result_fingerprint,
        "completed_at": receipt.completed_at.isoformat(),
        "final_event_id": receipt.final_event_id,
        "final_event_sequence": receipt.final_event_sequence,
        "final_event_fingerprint": receipt.final_event_fingerprint,
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://strategy-lab.test"
    ) as client:
        response = await client.post(
            "/api/v1/strategy-lab/v2/forward-instances/forward-1/warmup",
            json=body,
        )
    assert response.status_code == 202
    assert response.json()["data"]["type"] == "forward-warmups"
    assert response.json()["data"]["meta"]["decision"] == "complete"


def _ordinary_forward_dispatch_body() -> dict[str, Any]:
    event = correction_event("live-0", 0)
    observation = observe_forward_event(ForwardCursor(), event)
    event_fingerprint = content_digest(event)
    payload = {"event_fingerprint": event_fingerprint, "replay_plan_fingerprint": None}
    dispatch = DispatchRequest(
        idempotency_key="forward-dispatch-route",
        attempt_id="forward-1",
        payload_digest=content_digest(payload),
        queue_name="forward",
        created_at=NOW,
    )
    return {
        "event": {
            "event_id": event.event_id,
            "sequence": event.sequence,
            "event_time": event.event_time.isoformat(),
            "arrived_at": event.arrived_at.isoformat(),
            "source_digest": event.source_digest,
        },
        "observation": {
            "disposition": observation.disposition.value,
            "stale": observation.stale,
            "missing_sequence_start": observation.missing_sequence_start,
            "missing_sequence_end": observation.missing_sequence_end,
            "correction_requires_counterfactual_replay": observation.correction_requires_counterfactual_replay,
            "next_cursor": {
                "last_sequence": observation.next_cursor.last_sequence,
                "last_event_id": observation.next_cursor.last_event_id,
                "last_event_time": observation.next_cursor.last_event_time.isoformat()
                if observation.next_cursor.last_event_time is not None
                else None,
            },
            "buffer_event": observation.buffer_event,
        },
        "dispatch": {
            "idempotency_key": dispatch.idempotency_key,
            "attempt_id": dispatch.attempt_id,
            "payload_digest": dispatch.payload_digest,
            "queue_name": dispatch.queue_name,
            "created_at": dispatch.created_at.isoformat(),
        },
        "payload": payload,
    }


@pytest.mark.asyncio
async def test_dispatch_route_executes_atomic_forward_outbox_boundary() -> None:
    app = _asgi_app(ForwardRouteAdapter())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://strategy-lab.test"
    ) as client:
        response = await client.post(
            "/api/v1/strategy-lab/v2/forward-instances/forward-1/events/dispatch",
            json=_ordinary_forward_dispatch_body(),
        )
    assert response.status_code == 202
    assert response.json()["data"]["type"] == "forward-event-dispatches"
    assert response.json()["data"]["attributes"]["decision"] == "enqueue"


@pytest.mark.asyncio
async def test_lifecycle_route_executes_compare_and_set_boundary() -> None:
    app = _asgi_app(ForwardRouteAdapter())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://strategy-lab.test"
    ) as client:
        response = await client.post(
            "/api/v1/strategy-lab/v2/forward-instances/forward-1/lifecycle",
            json={"target": "active", "now": NOW.isoformat()},
            headers={"Idempotency-Key": "lifecycle-key"},
        )
    assert response.status_code == 202
    assert response.json()["data"]["type"] == "forward-lifecycle-transitions"
    assert response.json()["data"]["attributes"]["decision"] == "applied"


@pytest.mark.asyncio
async def test_lifecycle_route_requires_idempotency_key() -> None:
    app = _asgi_app(ForwardRouteAdapter())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://strategy-lab.test"
    ) as client:
        response = await client.post(
            "/api/v1/strategy-lab/v2/forward-instances/forward-1/lifecycle",
            json={"target": "active", "now": NOW.isoformat()},
        )
    assert response.status_code == 400
    assert response.json()["errors"][0]["message"] == "Idempotency-Key header is required"


@pytest.mark.asyncio
async def test_lifecycle_route_returns_conflicts_as_http_409() -> None:
    class ConflictAdapter(ForwardRouteAdapter):
        async def transition_forward_instance(
            self, **_kwargs: Any
        ) -> ForwardStateMutationResolution:
            return ForwardStateMutationResolution(
                ForwardStateMutationDecision.CONFLICT,
                forward_state().checkpoint.instance,
                "illegal forward transition",
            )

    app = _asgi_app(ConflictAdapter())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://strategy-lab.test"
    ) as client:
        response = await client.post(
            "/api/v1/strategy-lab/v2/forward-instances/forward-1/lifecycle",
            json={"target": "active", "now": NOW.isoformat()},
            headers={"Idempotency-Key": "lifecycle-key"},
        )
    assert response.status_code == 409
    assert response.json()["errors"][0]["message"] == "illegal forward transition"


def test_forward_replay_serializer_preserves_deterministic_plan_identity() -> None:
    replay_plan = CounterfactualReplayPlan(
        replay_id=content_digest("replay-serializer"),
        instance_id="forward-1",
        correction_event_id="correction-1",
        original_event_id="live-0",
        base_checkpoint_fingerprint=forward_state().checkpoint.fingerprint,
        warmup_receipt_fingerprint=forward_state().warmup_receipt_fingerprint,
        planned_at=NOW,
    )
    payload = serialize_forward_replays(
        (replay_plan,), instance_id="forward-1", request_id="request-1"
    )
    assert payload["data"][0]["type"] == "forward-replays"
    assert payload["data"][0]["id"] == replay_plan.replay_id
    assert payload["meta"]["count"] == 1


def test_forward_replay_serializer_rejects_plans_for_another_instance() -> None:
    replay_plan = CounterfactualReplayPlan(
        replay_id=content_digest("replay-serializer-other-instance"),
        instance_id="forward-2",
        correction_event_id="correction-1",
        original_event_id="live-0",
        base_checkpoint_fingerprint=forward_state().checkpoint.fingerprint,
        warmup_receipt_fingerprint=forward_state().warmup_receipt_fingerprint,
        planned_at=NOW,
    )

    with pytest.raises(ValueError, match="instance"):
        serialize_forward_replays((replay_plan,), instance_id="forward-1", request_id="request-1")


@pytest.mark.asyncio
async def test_replay_route_exposes_additive_counterfactual_plans() -> None:
    app = _asgi_app(ReplayRouteAdapter())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://strategy-lab.test"
    ) as client:
        response = await client.get("/api/v1/strategy-lab/v2/forward-instances/forward-1/replays")
    assert response.status_code == 200
    assert response.json()["data"][0]["type"] == "forward-replays"
    assert response.json()["meta"]["count"] == 1


def test_resource_serialization_preserves_decimal_as_exact_string() -> None:
    serialized = serialize_resource(_document())
    assert serialized["attributes"]["ratio"] == "1.25"
    assert serialized["relationships"]["experiment"]["data"] == [
        {"type": "experiments", "id": "experiment-1"}
    ]
    assert serialized["meta"]["schema_version"] == 1


def test_api_json_serialization_handles_dates_and_rejects_unsafe_scalars() -> None:
    assert _json_value(date(2024, 1, 2)) == "2024-01-02"
    assert _json_value(1.25) == 1.25
    with pytest.raises(ValueError, match="finite"):
        _json_value(float("nan"))
    with pytest.raises(TypeError, match="unsupported API JSON value"):
        _json_value(object())


def test_api_request_metadata_rejects_control_characters() -> None:
    request = SimpleNamespace(headers={"X-Request-ID": "request\nforged"})
    with pytest.raises(ValueError, match="control-free"):
        _request_id(cast(Any, request), lambda: "unused")
    with pytest.raises(ValueError, match="control characters"):
        _safe_header_value("key\r\nforged", "Idempotency-Key", 256)


def test_router_lists_and_reads_cursor_bound_resources() -> None:
    adapter = FakeAdapter()
    with _client(adapter) as client:
        response = client.get("/api/v1/strategy-lab/v2/trials?limit=1")
        assert response.status_code == 200
        assert response.json()["data"][0]["id"] == "trial-1"
        assert response.json()["data"][0]["attributes"]["ratio"] == "1.25"

        found = client.get("/api/v1/strategy-lab/v2/trials/trial-1")
        assert found.status_code == 200
        assert found.headers["content-type"].startswith("application/json")

        missing = client.get("/api/v1/strategy-lab/v2/trials/missing")
        assert missing.status_code == 404
        assert missing.json()["errors"][0]["code"] == "not_found"


def test_router_lists_capability_summary_projection_as_read_only_resource() -> None:
    with _client(FakeAdapter()) as client:
        response = client.get("/api/v1/strategy-lab/v2/capability-summaries")
        assert response.status_code == 200
        data = response.json()["data"][0]
        assert data["type"] == "capability-summaries"
        assert data["attributes"]["decision"] == "rigorous"
        assert data["attributes"]["can_publish_authoritative_results"] is True


def test_capability_preflight_delegates_and_returns_typed_summary() -> None:
    adapter = FakeAdapter()
    payload = {"requirements": [{"instrument_id": "AAPL", "field": "close"}]}
    with _client(adapter) as client:
        response = client.post(
            "/api/v1/strategy-lab/v2/capabilities/preflight",
            headers={"Idempotency-Key": "capability-key", "X-Request-ID": "capability-request"},
            json=payload,
        )

        assert response.status_code == 200
        assert response.headers["x-request-id"] == "capability-request"
        data = response.json()["data"]
        assert data["type"] == "capability-preflights"
        assert data["attributes"]["decision"] == "rigorous"
        assert data["attributes"]["ranking_eligible"] is True
        assert data["meta"]["request_id"] == "capability-request"
        assert data["meta"]["payload_digest"] == content_digest(payload)
        assert adapter.preflights == [
            ("capability-key", "capability-request", content_digest(payload))
        ]


def test_capability_preflight_fails_closed_until_host_binding_is_configured() -> None:
    with _client(object()) as client:
        response = client.post(
            "/api/v1/strategy-lab/v2/capabilities/preflight",
            headers={"Idempotency-Key": "capability-key"},
            json={"requirements": []},
        )

        assert response.status_code == 501
        error = response.json()["errors"][0]
        assert error["code"] == "capability_unsupported"
        assert error["request_id"] == "request-generated"


def test_capability_preflight_requires_idempotency_and_object_body() -> None:
    with _client(FakeAdapter()) as client:
        missing_key = client.post(
            "/api/v1/strategy-lab/v2/capabilities/preflight", json={"requirements": []}
        )
        assert missing_key.status_code == 400
        assert missing_key.json()["errors"][0]["code"] == "validation_error"

        invalid_body = client.post(
            "/api/v1/strategy-lab/v2/capabilities/preflight",
            headers={"Idempotency-Key": "capability-key"},
            json=["requirements"],
        )
        assert invalid_body.status_code == 422
        assert invalid_body.json()["errors"][0]["code"] == "validation_error"


def test_search_api_initializes_and_cancels_a_durable_candidate_queue() -> None:
    adapter = FakeAdapter()
    experiment = content_digest("search-experiment")
    trials = [content_digest("trial-1"), content_digest("trial-2")]
    with _client(adapter) as client:
        initialized = client.post(
            f"/api/v1/strategy-lab/v2/experiments/{experiment}/search",
            headers={"Idempotency-Key": "search-key", "X-Request-ID": "search-request"},
            json={"trial_fingerprints": trials},
        )
        assert initialized.status_code == 202
        assert initialized.headers["x-request-id"] == "search-request"
        data = initialized.json()["data"]
        assert data["type"] == "search-experiments"
        assert data["id"] == experiment
        assert [item["phase"] for item in data["attributes"]["candidates"]] == [
            "pending",
            "pending",
        ]
        assert initialized.json()["data"]["meta"]["decision"] == "apply"

        replay = client.post(
            f"/api/v1/strategy-lab/v2/experiments/{experiment}/search",
            headers={"Idempotency-Key": "search-key"},
            json={"trial_fingerprints": trials},
        )
        assert replay.status_code == 202
        assert replay.json()["data"]["meta"]["decision"] == "replay_existing"

        cancelled = client.post(
            f"/api/v1/strategy-lab/v2/experiments/{experiment}/search/cancel",
            headers={"Idempotency-Key": "cancel-key", "X-Request-ID": "cancel-request"},
        )
        assert cancelled.status_code == 202
        assert cancelled.json()["data"]["attributes"]["cancellation_requested"] is True
        assert cancelled.json()["data"]["meta"]["decision"] == "apply"

        cancel_replay = client.post(
            f"/api/v1/strategy-lab/v2/experiments/{experiment}/search/cancel",
            headers={"Idempotency-Key": "cancel-key"},
        )
        assert cancel_replay.status_code == 202
        assert cancel_replay.json()["data"]["meta"]["decision"] == "replay_existing"


def test_search_api_rejects_invalid_queue_definition_and_missing_adapter() -> None:
    experiment = content_digest("search-experiment")
    with _client(FakeAdapter()) as client:
        invalid = client.post(
            f"/api/v1/strategy-lab/v2/experiments/{experiment}/search",
            headers={"Idempotency-Key": "search-key"},
            json={"trial_fingerprints": ["not-a-digest"]},
        )
        assert invalid.status_code == 422
        assert invalid.json()["errors"][0]["code"] == "validation_error"

    with _client(object()) as client:
        unsupported = client.post(
            f"/api/v1/strategy-lab/v2/experiments/{experiment}/search",
            headers={"Idempotency-Key": "search-key"},
            json={"trial_fingerprints": [content_digest("trial-1")]},
        )
        assert unsupported.status_code == 501
        assert unsupported.json()["errors"][0]["code"] == "precondition_failed"


def test_search_dispatch_api_stages_candidate_evidence_and_fails_closed_without_binding() -> None:
    experiment = content_digest("search-experiment")
    body = {
        "candidate_index": 0,
        "attempt_id": "attempt-1",
        "queue_name": "strategy-backtest",
        "created_at": NOW.isoformat().replace("+00:00", "Z"),
    }
    adapter = FakeAdapter()
    with _client(adapter) as client:
        response = client.post(
            f"/api/v1/strategy-lab/v2/experiments/{experiment}/search/dispatch",
            headers={"Idempotency-Key": "dispatch-key", "X-Request-ID": "dispatch-request"},
            json=body,
        )
        assert response.status_code == 202
        assert response.headers["x-request-id"] == "dispatch-request"
        data = response.json()["data"]
        assert data["type"] == "search-dispatches"
        assert data["attributes"]["decision"] == "enqueue"
        assert data["attributes"]["search_state"]["candidates"][0]["phase"] == "running"
        assert data["attributes"]["envelope"]["request"]["idempotency_key"] == "dispatch-key"
        assert len(adapter.search_dispatches) == 1

    with _client(object()) as client:
        unsupported = client.post(
            f"/api/v1/strategy-lab/v2/experiments/{experiment}/search/dispatch",
            headers={"Idempotency-Key": "dispatch-key"},
            json=body,
        )
        assert unsupported.status_code == 501
        assert unsupported.json()["errors"][0]["code"] == "precondition_failed"


def test_search_dispatch_api_rejects_unknown_fields_and_missing_idempotency() -> None:
    experiment = content_digest("search-experiment")
    body = {
        "candidate_index": 0,
        "attempt_id": "attempt-1",
        "payload_digest": content_digest("client-cannot-bind-host-payload"),
        "queue_name": "strategy-backtest",
        "created_at": NOW.isoformat().replace("+00:00", "Z"),
        "unexpected": True,
    }
    with _client(FakeAdapter()) as client:
        invalid = client.post(
            f"/api/v1/strategy-lab/v2/experiments/{experiment}/search/dispatch",
            json=body,
        )
        assert invalid.status_code == 422
        assert invalid.json()["errors"][0]["code"] == "validation_error"


def test_walk_forward_dispatch_api_generates_attempt_through_search_dispatch_boundary() -> None:
    experiment = content_digest("walk-forward-dispatch-experiment")
    adapter = FakeAdapter()
    with _client(adapter) as client:
        response = client.post(
            f"/api/v1/strategy-lab/v2/experiments/{experiment}/walk-forward/dispatch",
            headers={"Idempotency-Key": "walk-forward-dispatch-key"},
            json={"candidate_index": 0, "queue_name": "strategy-backtest"},
        )

    assert response.status_code == 202, response.text
    assert response.json()["data"]["attributes"]["decision"] == "enqueue"
    assert len(adapter.walk_forward_dispatch_requests) == 1
    observed = adapter.walk_forward_dispatch_requests[0]
    assert observed["experiment_fingerprint"] == experiment
    assert observed["candidate_index"] == 0
    assert observed["idempotency_key"] == "walk-forward-dispatch-key"
    assert observed["queue_name"] == "strategy-backtest"

    with _client(object()) as client:
        unsupported = client.post(
            f"/api/v1/strategy-lab/v2/experiments/{experiment}/walk-forward/dispatch",
            headers={"Idempotency-Key": "walk-forward-dispatch-key"},
            json={"candidate_index": 0, "queue_name": "strategy-backtest"},
        )
    assert unsupported.status_code == 501


def test_walk_forward_dispatch_api_rejects_unknown_body_fields() -> None:
    experiment = content_digest("walk-forward-dispatch-experiment")
    with _client(FakeAdapter()) as client:
        response = client.post(
            f"/api/v1/strategy-lab/v2/experiments/{experiment}/walk-forward/dispatch",
            headers={"Idempotency-Key": "walk-forward-dispatch-key"},
            json={
                "candidate_index": 0,
                "queue_name": "strategy-backtest",
                "attempt_id": "caller-cannot-choose-attempt",
            },
        )
    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "validation_error"


def test_walk_forward_bulk_dispatch_api_uses_idempotent_owner_scoped_boundary() -> None:
    experiment = content_digest("walk-forward-bulk-dispatch-experiment")
    adapter = FakeAdapter()
    with _client(adapter) as client:
        response = client.post(
            f"/api/v1/strategy-lab/v2/experiments/{experiment}/walk-forward/dispatch-ready",
            headers={"Idempotency-Key": "walk-forward-batch-key"},
            json={"queue_name": "strategy-backtest"},
        )

    assert response.status_code == 202, response.text
    assert response.json()["meta"]["accepted_count"] == 1
    assert response.json()["meta"]["capacity_saturated"] is False
    assert response.json()["data"][0]["attributes"]["attempt_id"] == (
        "walk-forward-generated-attempt"
    )
    observed = adapter.walk_forward_bulk_dispatch_requests[0]
    assert observed["experiment_fingerprint"] == experiment
    assert observed["idempotency_key"] == "walk-forward-batch-key"
    assert observed["principal"] == "user-1"


def test_walk_forward_advance_api_hydrates_and_returns_durable_phase_transition() -> None:
    experiment = content_digest("walk-forward-advance-experiment")
    adapter = FakeAdapter()
    with _client(adapter) as client:
        response = client.post(
            f"/api/v1/strategy-lab/v2/experiments/{experiment}/walk-forward/advance"
        )

    assert response.status_code == 202, response.text
    assert response.json()["data"]["attributes"]["decision"] == "replay_existing"
    assert len(adapter.walk_forward_phase_requests) == 1
    assert adapter.walk_forward_phase_requests[0]["experiment_fingerprint"] == experiment
    assert adapter.walk_forward_phase_requests[0]["principal"] == "user-1"


def test_walk_forward_results_api_exposes_only_fold_ordered_oos_receipts() -> None:
    experiment = content_digest("walk-forward-results-experiment")
    adapter = FakeAdapter()
    with _client(adapter) as client:
        response = client.get(
            f"/api/v1/strategy-lab/v2/experiments/{experiment}/walk-forward/results"
        )

    assert response.status_code == 200, response.text
    assert response.json()["meta"]["result_scope"] == "selected_out_of_sample_only"
    assert response.json()["data"][0]["attributes"]["fold_index"] == 0
    assert response.json()["data"][0]["attributes"]["value"] == "0.125"
    assert adapter.walk_forward_result_requests[0]["experiment_fingerprint"] == experiment


def test_walk_forward_finalize_api_returns_versioned_fold_distribution() -> None:
    experiment = content_digest("walk-forward-finalize-experiment")
    adapter = FakeAdapter()
    with _client(adapter) as client:
        response = client.post(
            f"/api/v1/strategy-lab/v2/experiments/{experiment}/walk-forward/finalize"
        )

    assert response.status_code == 202, response.text
    attributes = response.json()["data"]["attributes"]
    assert attributes["aggregation_definition"] == "strategy-lab.walk-forward.fold-distribution.v1"
    assert attributes["result_scope"] == "selected_oos_fold_distribution_not_portfolio_compounding"
    assert attributes["native_portfolio_metrics"] is None
    assert attributes["native_metrics_status"] == "artifact_store_not_configured"
    assert len(attributes["aggregate_metrics"]) == 5
    assert response.json()["data"]["meta"]["decision"] == "persisted"


def test_walk_forward_finalize_api_exposes_persisted_native_portfolio_metrics() -> None:
    fold_summary = _summary_fixture()
    experiment = fold_summary.experiment_fingerprint
    native_summary = WalkForwardNativeOosMetricSummary(
        experiment_fingerprint=experiment,
        definition_fingerprint=fold_summary.definition_fingerprint,
        selection_fingerprint=fold_summary.selection.fingerprint,
        result_manifest_fingerprints=tuple(
            result.result_fingerprint for result in fold_summary.results
        ),
        metrics=(
            MetricValue(
                "total_return",
                Decimal("0.075"),
                "fraction",
                "strategy-lab.metrics.v2",
                MetricBasis.NET,
                10,
            ),
        ),
        curve_artifact=ArtifactManifest(
            content_digest("api-native-oos-curve"),
            256,
            WALK_FORWARD_NATIVE_EQUITY_CURVE_MEDIA_TYPE,
            WALK_FORWARD_NATIVE_EQUITY_CURVE_SCHEMA,
            content_digest("api-native-oos-curve"),
            ArtifactRetention.PINNED_RESULT,
        ),
    )
    resolution = WalkForwardSummaryResolution(
        WalkForwardSummaryDecision.PERSISTED,
        fold_summary,
        1,
        native_metrics=native_summary,
    )

    class NativeMetricsAdapter(FakeAdapter):
        async def persist_walk_forward_oos_summary(self, **_kwargs: Any) -> Any:
            return resolution

    with _client(NativeMetricsAdapter()) as client:
        response = client.post(
            f"/api/v1/strategy-lab/v2/experiments/{experiment}/walk-forward/finalize"
        )

    assert response.status_code == 202, response.text
    attributes = response.json()["data"]["attributes"]
    assert attributes["native_metrics_status"] == "available"
    assert attributes["native_metrics_summary_fingerprint"] == native_summary.fingerprint
    assert (
        attributes["native_portfolio_curve_artifact"]["content_digest"]
        == native_summary.curve_artifact.content_digest
    )
    assert attributes["native_portfolio_metrics"][0]["name"] == "total_return"
    assert (
        attributes["result_scope"]
        == "selected_oos_fold_distribution_and_native_portfolio_compounding"
    )


def test_router_lists_preserved_legacy_imports_without_payload_bytes() -> None:
    with _client(FakeAdapter()) as client:
        response = client.get("/api/v1/strategy-lab/v2/legacy-imports")
        assert response.status_code == 200
        data = response.json()["data"][0]
        assert data["type"] == "legacy-imports"
        assert data["attributes"]["original"]["legacy_id"] == "legacy-definition-1"
        assert data["meta"]["replay_equivalent"] is False


def test_router_rejects_invalid_cursor_and_unknown_resource_with_typed_errors() -> None:
    adapter = FakeAdapter()
    with _client(adapter) as client:
        invalid = client.get("/api/v1/strategy-lab/v2/trials?cursor=not-a-cursor")
        assert invalid.status_code == 400
        assert invalid.json()["errors"][0]["code"] == "validation_error"

        unknown = client.get("/api/v1/strategy-lab/v2/not-a-resource")
        assert unknown.status_code == 404
        assert unknown.json()["errors"][0]["details"]["resource"] == "not-a-resource"

        too_large = client.get("/api/v1/strategy-lab/v2/trials?limit=101")
        assert too_large.status_code == 400


def test_router_rejects_ambiguous_or_non_finite_raw_json_bodies() -> None:
    adapter = FakeAdapter()
    with _client(adapter) as client:
        duplicate = client.post(
            "/api/v1/strategy-lab/v2/submissions",
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": "submission-key",
            },
            content=(
                '{"operation":"backtest","operation":"retry",'
                '"attempt_id":"attempt-1","payload":{}}'
            ),
        )
        assert duplicate.status_code == 422
        assert duplicate.json()["errors"][0]["code"] == "validation_error"
        assert adapter.submissions == []

        non_finite = client.post(
            "/api/v1/strategy-lab/v2/submissions",
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": "submission-key",
            },
            content=(
                '{"operation":"backtest","attempt_id":"attempt-1",' '"payload":{"score":NaN}}'
            ),
        )
        assert non_finite.status_code == 422
        assert non_finite.json()["errors"][0]["code"] == "validation_error"
        assert adapter.submissions == []


def test_router_rejects_collection_request_identity_drift() -> None:
    with _client(RequestDriftAdapter()) as client:
        response = client.get("/api/v1/strategy-lab/v2/trials")
        assert response.status_code == 422
        assert response.json()["errors"][0]["code"] == "validation_error"


def test_router_rejects_collection_snapshot_drift_after_cursor_validation() -> None:
    cursor = ApiCursor(
        resource="trials",
        snapshot_digest=SNAPSHOT,
        sort_value="2024-01-01T00:00:00Z",
        item_id="trial-1",
    )
    with _client(SnapshotDriftAdapter()) as client:
        response = client.get("/api/v1/strategy-lab/v2/trials", params={"cursor": cursor.token})
        assert response.status_code == 422
        assert response.json()["errors"][0]["code"] == "validation_error"


def test_strategy_validation_route_is_static_and_authenticated_by_injected_dependency() -> None:
    with _client(FakeAdapter()) as client:
        accepted = client.post(
            "/api/v1/strategy-lab/v2/strategies/validate",
            json={"source": "def signal(inputs):\n    return inputs.close > 0\n"},
        )
        assert accepted.status_code == 200
        assert accepted.json()["data"]["attributes"]["accepted"] is True

        rejected = client.post(
            "/api/v1/strategy-lab/v2/strategies/validate",
            json={"source": "import os\nnow = datetime.now()\n"},
        )
        assert rejected.status_code == 200
        assert rejected.json()["data"]["attributes"]["accepted"] is False
        violations = rejected.json()["data"]["attributes"]["violations"]
        assert any("forbidden_import" in item for item in violations)
        assert any("forbidden_wall_clock" in item for item in violations)

        malformed = client.post(
            "/api/v1/strategy-lab/v2/strategies/validate",
            json=["source"],
        )
        assert malformed.status_code == 422
        assert malformed.json()["errors"][0]["code"] == "validation_error"


def test_strategy_validation_rejects_invalid_request_id_with_typed_error() -> None:
    with _client(FakeAdapter()) as client:
        response = client.post(
            "/api/v1/strategy-lab/v2/strategies/validate",
            headers={"X-Request-ID": "r" * 129},
            json={"source": "def signal(inputs):\n    return []\n"},
        )
        assert response.status_code == 400
        error = response.json()["errors"][0]
        assert error["code"] == "validation_error"
        assert error["request_id"] == "unknown"


def test_submission_requires_idempotency_and_returns_accepted_receipt() -> None:
    adapter = FakeAdapter()
    with _client(adapter) as client:
        missing = client.post(
            "/api/v1/strategy-lab/v2/submissions",
            json={"operation": "backtest", "attempt_id": "attempt-1", "payload": {}},
        )
        assert missing.status_code == 400
        assert missing.json()["errors"][0]["code"] == "validation_error"

        response = client.post(
            "/api/v1/strategy-lab/v2/submissions",
            headers={"Idempotency-Key": "submission-key", "X-Request-ID": "request-1"},
            json={"operation": "backtest", "attempt_id": "attempt-1", "payload": {"x": 1}},
        )
        assert response.status_code == 202
        assert response.headers["x-request-id"] == "request-1"
        assert response.json()["data"]["type"] == "submissions"
        assert response.json()["data"]["attributes"]["payload_digest"] == content_digest({"x": 1})
        assert adapter.submissions == [("submission-key", "backtest", {"x": 1})]


def test_submission_conflict_is_exposed_as_typed_idempotency_error() -> None:
    with _client(ConflictAdapter()) as client:
        response = client.post(
            "/api/v1/strategy-lab/v2/submissions",
            headers={"Idempotency-Key": "submission-key"},
            json={"operation": "backtest", "attempt_id": "attempt-1", "payload": {"x": 1}},
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "idempotency_conflict"


def test_resource_creation_is_idempotent_and_returns_a_resource_document() -> None:
    adapter = FakeAdapter()
    with _client(adapter) as client:
        response = client.post(
            "/api/v1/strategy-lab/v2/trials",
            headers={"Idempotency-Key": "resource-key", "X-Request-ID": "resource-request"},
            json={
                "attributes": {"name": "mean-reversion", "lookback": 20},
                "relationships": {"experiment": [{"type": "experiments", "id": "experiment-1"}]},
            },
        )
        assert response.status_code == 202
        assert response.headers["x-request-id"] == "resource-request"
        assert response.json()["data"]["type"] == "trials"
        assert response.json()["meta"]["decision"] == "accept"
        assert adapter.mutations[0][0:2] == ("trials", "resource-key")


def test_resource_creation_rejects_read_only_or_ambiguous_requests() -> None:
    adapter = FakeAdapter()
    with _client(adapter) as client:
        readonly = client.post(
            "/api/v1/strategy-lab/v2/artifacts",
            headers={"Idempotency-Key": "resource-key"},
            json={"attributes": {}},
        )
        assert readonly.status_code == 405
        assert readonly.json()["errors"][0]["code"] == "precondition_failed"

        duplicate = client.post(
            "/api/v1/strategy-lab/v2/trials",
            headers={"Idempotency-Key": "resource-key"},
            content='{"attributes":{},"attributes":{}}',
        )
        assert duplicate.status_code == 422
        assert duplicate.json()["errors"][0]["code"] == "validation_error"

        missing_key = client.post("/api/v1/strategy-lab/v2/trials", json={"attributes": {}})
        assert missing_key.status_code == 400
        assert missing_key.json()["errors"][0]["code"] == "validation_error"


def test_resource_creation_exposes_typed_idempotency_conflict() -> None:
    with _client(ResourceConflictAdapter()) as client:
        response = client.post(
            "/api/v1/strategy-lab/v2/trials",
            headers={"Idempotency-Key": "resource-key"},
            json={"attributes": {"name": "new"}},
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "idempotency_conflict"


def test_legacy_import_returns_explicit_compatibility_report() -> None:
    adapter = FakeAdapter()
    payload_digest = content_digest({"legacy": "payload"})
    conversion = content_digest({"conversion": "v1-to-v2"})
    with _client(adapter) as client:
        response = client.post(
            "/api/v1/strategy-lab/v2/legacy/imports",
            headers={"Idempotency-Key": "legacy-key", "X-Request-ID": "legacy-request"},
            json={
                "legacy_id": "legacy-definition-1",
                "kind": "definition",
                "source_version": "strategy-lab-v1",
                "payload_digest": payload_digest,
                "mapping_version": "mapping-v1",
                "supported": True,
                "conversion_fingerprint": conversion,
                "notes": ["converted without replay-equivalence"],
            },
        )

        assert response.status_code == 202
        assert response.headers["x-request-id"] == "legacy-request"
        data = response.json()["data"]
        assert data["type"] == "legacy-imports"
        assert data["id"] == "legacy-definition-1"
        assert data["attributes"]["decision"] == "accept"
        assert data["attributes"]["replay_equivalent"] is False
        assert data["attributes"]["conversion_fingerprint"] == conversion
        assert data["meta"]["request_id"] == "legacy-request"
        assert adapter.legacy_imports == ["legacy-definition-1"]


def test_legacy_import_requires_idempotency_and_rejects_invalid_assessment() -> None:
    with _client(FakeAdapter()) as client:
        missing_key = client.post(
            "/api/v1/strategy-lab/v2/legacy/imports",
            json={
                "legacy_id": "legacy-result-1",
                "kind": "result",
                "source_version": "strategy-lab-v1",
                "payload_digest": content_digest("payload"),
                "mapping_version": "mapping-v1",
                "supported": False,
            },
        )
        assert missing_key.status_code == 400
        assert missing_key.json()["errors"][0]["code"] == "validation_error"

        invalid = client.post(
            "/api/v1/strategy-lab/v2/legacy/imports",
            headers={"Idempotency-Key": "legacy-key"},
            json={
                "legacy_id": "legacy-result-1",
                "kind": "result",
                "source_version": "strategy-lab-v1",
                "payload_digest": content_digest("payload"),
                "mapping_version": "mapping-v1",
                "supported": True,
            },
        )
        assert invalid.status_code == 422
        assert invalid.json()["errors"][0]["code"] == "validation_error"


def test_command_route_constructs_typed_intent_and_returns_accepted_receipt() -> None:
    adapter = FakeAdapter()
    command_id = content_digest({"command": "cancel"})
    with _client(adapter) as client:
        response = client.post(
            "/api/v1/strategy-lab/v2/attempts/attempt-1/commands",
            headers={"Idempotency-Key": "command-key"},
            json={
                "command_id": command_id,
                "kind": "cancel",
                "reason": "user requested stop",
                "requested_at": NOW.isoformat(),
            },
        )
        assert response.status_code == 202
        assert response.json()["data"]["attributes"]["effect"] == "cancellation_requested"
        assert adapter.commands == [("command-key", "cancel")]
