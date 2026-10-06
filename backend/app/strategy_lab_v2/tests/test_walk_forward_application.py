from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.api_router import ApiAdapterError
from app.strategy_lab_v2.application import PostgresStrategyLabV2Adapter
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import ScientificTrial
from app.strategy_lab_v2.experiments import WalkForwardMode, WalkForwardSpec
from app.strategy_lab_v2.postgres_walk_forward_plan import (
    WalkForwardDefinitionDecision,
    WalkForwardDefinitionResolution,
)
from app.strategy_lab_v2.tests.test_nautilus_trial_assembly import _inputs
from app.strategy_lab_v2.walk_forward_search import (
    SelectionDirection,
    WalkForwardDefinitionRequest,
    WalkForwardExecutionDefinition,
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

        async def get_domain_contract_by_fingerprint(self, **kwargs: Any) -> Any:
            assert kwargs["principal"].id == "42"
            key = (kwargs["resource_type"], kwargs["fingerprint"])
            return None if key in self.missing else contracts.get(key)

        async def get_domain_contracts_by_fingerprint(self, **kwargs: Any) -> Any:
            assert kwargs["principal"].id == "42"
            return {
                fingerprint: contracts[(kwargs["resource_type"], fingerprint)]
                for fingerprint in kwargs["fingerprints"]
                if (kwargs["resource_type"], fingerprint) in contracts
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

    reader = Reader()
    plan_store = PlanStore()
    adapter = cast(Any, object.__new__(PostgresStrategyLabV2Adapter))
    adapter._resources = reader
    adapter._persistence = SimpleNamespace(walk_forward_plans=plan_store)
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
